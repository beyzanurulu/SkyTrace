import json
from pathlib import Path

import pytest
import yaml

from skytrace import FlightLog
from skytrace.agent import (
    TOOL_SCHEMAS,
    TOOLS,
    AgentContext,
    FlightAgent,
    call_tool,
    verify_answer,
)
from skytrace.agent.verify import annotate
from skytrace.config import load_config
from skytrace.detectors import run_detectors
from skytrace.evaluation.agent_questions import check_reply

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = yaml.safe_load((ROOT / "eval" / "agent_questions.yaml").read_text("utf-8"))["questions"]


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    cfg = load_config()
    log = FlightLog.from_file(ROOT / "tests" / "fixtures" / "sample_log_small.ulg", cfg)
    return AgentContext(log, run_detectors(log, cfg), cfg, tmp_path_factory.mktemp("plots"))


class ScriptedModel:
    """Plays a fixed list of tool calls / answers; records what it was given."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, tools):
        self.calls.append((list(messages), tools))
        step = self.script.pop(0)
        if "answer" in step:
            return {"role": "assistant", "content": step["answer"]}
        call = {
            "id": f"call_{len(self.calls)}",
            "type": "function",
            "function": {"name": step["tool"], "arguments": json.dumps(step.get("args", {}))},
        }
        return {"role": "assistant", "content": "", "tool_calls": [call]}


# --- the ten example questions -------------------------------------------------


@pytest.mark.parametrize("case", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_example_questions(ctx, case):
    model = ScriptedModel(case["script"])
    reply = FlightAgent(ctx, model).ask(case["question"])
    assert check_reply(case, reply) == [], reply.answer
    if case["expect"]["verified"]:
        assert reply.answer == reply.raw_answer
    else:
        assert "Not backed by any tool output" in reply.answer
    assert not model.script  # the whole script was used


def test_key_facts_reject_an_empty_no_data_answer(ctx):
    case = next(q for q in QUESTIONS if q["id"] == "battery_min")
    model = ScriptedModel([case["script"][0], {"answer": "Batarya verisi bulunamadı."}])
    reply = FlightAgent(ctx, model).ask(case["question"])
    assert reply.verification.ok  # nothing unbacked ...
    assert check_reply(case, reply) == ["missing key number 23.3362"]  # ... but still a fail


def test_tool_alternatives_and_column_prefix(ctx):
    case = next(q for q in QUESTIONS if q["id"] == "flight_modes")
    model = ScriptedModel(
        [{"tool": "get_events", "args": {"kinds": ["mode"]}}, {"answer": "MANUAL modunda."}]
    )
    assert check_reply(case, FlightAgent(ctx, model).ask(case["question"])) == []
    out = json.loads(
        call_tool(ctx, "query_series", {"table": "battery", "columns": ["battery:voltage"]})
    )
    assert "voltage" in out["columns"]


def test_question_set_has_ten_questions():
    assert len(QUESTIONS) == 10
    assert len({q["id"] for q in QUESTIONS}) == 10


# --- graph behaviour -----------------------------------------------------------


def test_system_prompt_and_tools_are_sent(ctx):
    model = ScriptedModel([{"answer": "Sadece bu log."}])
    FlightAgent(ctx, model).ask("merhaba")
    messages, tools = model.calls[0]
    assert messages[0]["role"] == "system" and "Never compute" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "merhaba"}
    assert tools == TOOL_SCHEMAS


def test_follow_up_question_can_use_earlier_tool_results(ctx):
    model = ScriptedModel(
        [
            {"tool": "list_findings", "args": {}},
            {"answer": "F001 ve F002."},
            {"answer": "F001 daha uzun sürdü: 1.59 s; F002 1.50 s."},
        ]
    )
    agent = FlightAgent(ctx, model)
    agent.ask("Hangi bulgular var?")
    reply = agent.ask("Hangisi daha uzun sürdü?")
    assert reply.tool_calls == []
    assert reply.verification.ok, reply.answer
    assert any(m["role"] == "tool" for m in model.calls[-1][0])  # history kept


def test_tool_round_limit_forces_an_answer(ctx):
    rounds = ctx.config.agent.max_tool_rounds
    script = [{"tool": "get_flight_summary", "args": {}}] * rounds + [{"answer": "Log 6.5 s."}]
    model = ScriptedModel(script)
    reply = FlightAgent(ctx, model).ask("?")
    assert reply.tool_calls == ["get_flight_summary"] * rounds
    _, last_tools = model.calls[-1]
    assert last_tools == []  # no tools offered once the limit is reached
    assert "limit reached" in model.calls[-1][0][-1]["content"]
    assert reply.verification.ok


def test_tool_errors_go_back_to_the_model(ctx):
    model = ScriptedModel(
        [
            {"tool": "query_series", "args": {"table": "battery", "columns": ["nope"]}},
            {"answer": "Bu sütun yok."},
        ]
    )
    reply = FlightAgent(ctx, model).ask("?")
    tool_msg = next(m for m in reply.messages if m["role"] == "tool")
    assert "error" in json.loads(tool_msg["content"])


# --- tools -----------------------------------------------------------------------


def test_every_schema_has_a_tool_and_back():
    assert {s["function"]["name"] for s in TOOL_SCHEMAS} == set(TOOLS)


def test_query_series_returns_degrees_and_times(ctx):
    out = json.loads(
        call_tool(ctx, "query_series", {"table": "signals", "columns": ["pitch_error_deg"]})
    )
    col = out["columns"]["pitch_error_deg"]
    assert col["max"] == pytest.approx(19.9343, abs=1e-3)
    assert 3.3 <= col["t_max_s"] <= 4.9
    att = json.loads(call_tool(ctx, "query_series", {"table": "attitude", "columns": ["yaw"]}))
    assert att["columns"]["yaw"]["unit"] == "deg"
    assert abs(att["columns"]["yaw"]["max"]) > 3.2  # degrees, not radians


def test_query_series_samples_are_capped(ctx):
    out = json.loads(
        call_tool(ctx, "query_series", {"table": "attitude", "columns": ["roll"], "agg": "samples"})
    )
    assert len(out["columns"]["roll"]["samples"]) <= ctx.config.agent.max_series_points


@pytest.mark.parametrize(
    "name,args",
    [
        ("query_series", {"table": "nope", "columns": ["x"]}),
        ("query_series", {"table": "signals", "columns": ["nope"]}),
        ("query_series", {"table": "battery", "columns": ["voltage"], "agg": "median"}),
        ("list_findings", {"colour": "red"}),
        ("no_such_tool", {}),
    ],
)
def test_bad_tool_calls_return_errors(ctx, name, args):
    assert "error" in json.loads(call_tool(ctx, name, args))


def test_make_plot_writes_html(ctx):
    out = json.loads(
        call_tool(ctx, "make_plot", {"table": "battery", "columns": ["voltage"], "t_end": 3})
    )
    path = Path(out["path"])
    assert path.is_file() and path.read_text(encoding="utf-8").lower().startswith("<!doctype html>")


def test_search_docs_is_a_stub(ctx):
    assert json.loads(call_tool(ctx, "search_docs", {"query": "vibration"}))["available"] is False


# --- verification ------------------------------------------------------------------


def test_verify_rounding_comma_percent_and_sign():
    tools = ['{"min": 23.3362, "remaining": 0.739838, "vz": -0.31, "id": "F002"}']
    assert verify_answer("23.34 V, 23,3 V, %74, 74%, 0.3 m/s drop, F002", tools).ok
    bad = verify_answer("23.5 V, F009", tools)
    assert bad.unverified == ["23.5"] and bad.unknown_ids == ["F009"]


def test_verify_ignores_question_numbers_and_list_numbering():
    tools = ['{"max": 19.9343}']
    answer = "1. 3 ile 5 arasında en fazla 19.9°.\n2. Başka bulgu yok."
    assert verify_answer(answer, tools, question="3 ile 5. saniyeler arasında?").ok


def test_annotate_only_when_needed():
    v = verify_answer("12.5 V", ['{"v": 12.5}'])
    assert annotate("12.5 V", v) == "12.5 V"
    v = verify_answer("99 V", ['{"v": 12.5}'])
    assert "99" in annotate("99 V", v).split("⚠")[1]


def test_litellm_tool_call_path_imports():
    # litellm imports its MCP handler (needs the `mcp` package) whenever tools= is
    # passed; the scripted tests never reach it. mock_response: no network.
    import litellm

    response = litellm.completion(
        model="ollama_chat/qwen2.5:3b",
        messages=[{"role": "user", "content": "hi"}],
        tools=TOOL_SCHEMAS,
        mock_response="ok",
    )
    assert response.choices[0].message.content == "ok"


def test_verify_numbers_glued_to_units():
    tools = ['{"min": 23.3362, "eph": 3.26}']
    assert verify_answer("23.3362V ve 3.26m", tools).ok  # backed, even without a space
    bad = verify_answer("23.3362V ama 99V", tools)
    assert bad.unverified == ["99"]  # an invented glued number is not missed either


def test_out_of_scope_must_not_call_tools(ctx):
    case = next(q for q in QUESTIONS if q["id"] == "out_of_scope")
    model = ScriptedModel([{"tool": "get_flight_summary", "args": {}}, {"answer": "Bilmiyorum."}])
    problems = check_reply(case, FlightAgent(ctx, model).ask(case["question"]))
    assert problems == ["no tool expected, called ['get_flight_summary']"]


def test_digits_inside_hashes_do_not_back_numbers():
    tools = ['{"firmware": "8583f1da30b63154", "summary": "EPH 3.26 m (limit 3.00)"}']
    v = verify_answer("8583 and 30, EPH 3.26 m, limit 3.00", tools)
    assert v.unverified == ["8583", "30"]  # hash digits are not evidence; text numbers are


def test_prefetch_puts_summary_and_findings_in_context(ctx):
    model = ScriptedModel([{"answer": "F001 ve F002; log 6.5 s."}])
    reply = FlightAgent(ctx, model).ask("Özetle?")
    system = model.calls[0][0][0]["content"]
    assert "get_flight_summary:" in system and "list_findings:" in system
    assert reply.tool_calls == [] and reply.verification.ok  # backed by the prefetched outputs


def test_prefetch_caps_findings_and_can_be_disabled(ctx):
    from dataclasses import replace

    from skytrace.agent.graph import prefetch_outputs

    capped = replace(
        ctx, config=replace(ctx.config, agent=replace(ctx.config.agent, prefetch_max_findings=1))
    )
    findings = json.loads(prefetch_outputs(capped)[1])
    assert len(findings["findings"]) == 1 and findings["not_shown"] == 1
    off = replace(ctx, config=replace(ctx.config, agent=replace(ctx.config.agent, prefetch=False)))
    model = ScriptedModel([{"answer": "?"}])
    FlightAgent(off, model).ask("?")
    assert "list_findings:" not in model.calls[0][0][0]["content"]


def test_prefetched_tools_count_as_called(ctx):
    case = next(q for q in QUESTIONS if q["id"] == "duration")
    model = ScriptedModel([{"answer": "Log 6.5 saniye sürüyor."}])  # no tool call needed
    reply = FlightAgent(ctx, model).ask(case["question"])
    assert reply.tool_calls == [] and "get_flight_summary" in reply.prefetched
    assert check_reply(case, reply) == []

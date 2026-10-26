import json

from typer.testing import CliRunner

from skytrace import __version__
from skytrace.cli import app

runner = CliRunner()


def test_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert __version__ in res.output


def test_analyze_html(sample_ulog, tmp_path):
    out = tmp_path / "report.html"
    res = runner.invoke(app, ["analyze", str(sample_ulog), "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert out.read_text(encoding="utf-8").startswith("<!")
    assert "F001" in res.output


def test_analyze_json(sample_ulog, tmp_path):
    out = tmp_path / "report.json"
    res = runner.invoke(app, ["analyze", str(sample_ulog), "-f", "json", "-o", str(out), "-q"])
    assert res.exit_code == 0, res.output
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == 1


def test_unknown_detector(sample_ulog, tmp_path):
    res = runner.invoke(
        app, ["analyze", str(sample_ulog), "--only", "nope", "-o", str(tmp_path / "r.html")]
    )
    assert res.exit_code == 2


def test_chat_ask_one_question(monkeypatch, sample_ulog):
    import json as _json

    import skytrace.agent.graph as graph

    steps = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_flight_summary", "arguments": _json.dumps({})},
                }
            ],
        },
        {"role": "assistant", "content": "Log 6.5 saniye sürüyor."},
    ]
    monkeypatch.setattr(graph, "litellm_complete", lambda cfg: lambda messages, tools: steps.pop(0))
    res = CliRunner().invoke(app, ["chat", str(sample_ulog), "--ask", "Uçuş ne kadar sürdü?"])
    assert res.exit_code == 0, res.output
    assert "6.5 saniye" in res.output and "get_flight_summary" in res.output
    assert "Not backed" not in res.output


def test_chat_reports_an_unreachable_model(monkeypatch, sample_ulog):
    import skytrace.agent.graph as graph

    def boom(messages, tools):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(graph, "litellm_complete", lambda cfg: boom)
    res = CliRunner().invoke(app, ["chat", str(sample_ulog), "--ask", "?"])
    assert res.exit_code == 1
    assert "connection refused" in res.output and "Ollama" in res.output

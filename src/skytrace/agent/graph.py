"""LangGraph Q&A agent: model <-> tools loop, then a verification node.

    llm --(tool calls, rounds left)--> tools --> llm
    llm --(final answer)-------------> verify --> END

The model is reached through a ``Complete`` function (messages, tool schemas)
-> assistant message, in OpenAI / LiteLLM format. ``litellm_complete`` is the
real one; tests pass a scripted function, so no model is needed to test the
graph. The verify node checks the answer's numbers and finding ids against the
tool outputs of the turn (``skytrace.agent.verify``) and marks what it cannot
back.
"""

from __future__ import annotations

import json
import operator
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Annotated, Any, Final, TypedDict

from skytrace.agent.tools import TOOL_SCHEMAS, AgentContext, call_tool
from skytrace.agent.verify import Verification, annotate, verify_answer
from skytrace.config import AgentConfig

Message = dict[str, Any]
Complete = Callable[[list[Message], list[dict[str, Any]]], Message]

SYSTEM_PROMPT: Final = """\
You are SkyTrace, an assistant that answers questions about ONE drone flight log \
(PX4 or ArduPilot) that has already been parsed and analysed.

Rules, without exception:
1. For any question about the log, call at least one tool before answering. Never \
say that data is missing unless a tool returned an error or an empty result.
2. Every number, time and finding id in your answer must come from a tool output \
in this conversation. Never compute, convert, estimate or invent a number. If you \
need a value, call a tool (query_series already returns angles in degrees, and \
min/max with their times).
3. Use table and column names exactly as listed in the tool descriptions (for \
example table "battery", columns ["voltage"]). If a tool returns an error, fix the \
arguments and call it again.
4. Cite findings by id and time range, e.g. "F002 (3.3-4.8 s)". Times are seconds \
since log start.
5. Questions that are not about this log (weather, other flights, general chat): \
say that you only answer questions about this log, without calling tools.
6. Skipped checks (e.g. uncalibrated thresholds) mean "not checked", not "fine": \
mention them when relevant (get_flight_summary lists them).
7. For why / how-to-fix questions, call search_docs and cite the url of every passage \
you use; never write a url that search_docs did not return. Documentation values \
(e.g. recommended limits) are guidance, not values \
from this log: say where they come from.
8. Write the whole answer in the language of the question (a Turkish question gets \
a Turkish answer, an English one an English answer). Be brief.
"""

FORCE_ANSWER: Final = (
    "Tool-call limit reached. Answer now with the tool outputs you already have, "
    "following the rules."
)


class AgentState(TypedDict):
    messages: Annotated[list[Message], operator.add]
    tool_outputs: Annotated[list[str], operator.add]
    rounds: int
    question: str
    answer: str
    verification: Verification | None


@dataclass
class AgentReply:
    answer: str  # with a warning appended if something is not backed
    raw_answer: str
    verification: Verification
    tool_calls: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    prefetched: list[str] = field(default_factory=list)
    """Tools whose outputs were in the context from the start (agent.prefetch)."""


def litellm_complete(cfg: AgentConfig) -> Complete:
    """The real model, through LiteLLM (local Ollama by default)."""

    def complete(messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        import litellm

        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "timeout": cfg.timeout_s,
        }
        if tools:
            kwargs["tools"] = tools
        if cfg.api_base:
            kwargs["api_base"] = cfg.api_base
        response = litellm.completion(**kwargs)
        message = response.choices[0].message
        out: Message = {"role": "assistant", "content": message.content or ""}
        if getattr(message, "tool_calls", None):
            out["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls
            ]
        return out

    return complete


def build_graph(ctx: AgentContext, complete: Complete) -> Any:  # noqa: ANN401 (LangGraph type)
    from langgraph.graph import END, START, StateGraph

    cfg = ctx.config.agent

    def llm(state: AgentState) -> dict[str, Any]:
        exhausted = state["rounds"] >= cfg.max_tool_rounds
        messages = state["messages"]
        if exhausted:
            messages = [*messages, {"role": "user", "content": FORCE_ANSWER}]
        reply = complete(messages, [] if exhausted else TOOL_SCHEMAS)
        if exhausted:
            reply.pop("tool_calls", None)
        return {"messages": [reply]}

    def route(state: AgentState) -> str:
        return "tools" if state["messages"][-1].get("tool_calls") else "verify"

    def tools(state: AgentState) -> dict[str, Any]:
        results: list[Message] = []
        outputs: list[str] = []
        for call in state["messages"][-1]["tool_calls"]:
            output = call_tool(ctx, call["function"]["name"], call["function"].get("arguments"))
            outputs.append(output)
            results.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        return {"messages": results, "tool_outputs": outputs, "rounds": state["rounds"] + 1}

    def verify(state: AgentState) -> dict[str, Any]:
        raw = str(state["messages"][-1].get("content") or "")
        v = verify_answer(raw, state["tool_outputs"], state["question"], cfg.number_rel_tol)
        return {"answer": annotate(raw, v), "verification": v}

    graph = StateGraph(AgentState)
    graph.add_node("llm", llm)
    graph.add_node("tools", tools)
    graph.add_node("verify", verify)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", route, {"tools": "tools", "verify": "verify"})
    graph.add_edge("tools", "llm")
    graph.add_edge("verify", END)
    return graph.compile()


PREFETCH_TOOLS: Final = ("get_flight_summary", "list_findings")
PREFETCH_HEADER: Final = (
    "\nThese tool outputs are already available; use them directly and call tools "
    "only for anything else (time series, events, plots):\n"
)


def prefetch_outputs(ctx: AgentContext) -> list[str]:
    """Outputs of get_flight_summary and list_findings, findings capped for long logs."""
    summary = call_tool(ctx, "get_flight_summary", {})
    findings = json.loads(call_tool(ctx, "list_findings", {}))
    limit = ctx.config.agent.prefetch_max_findings
    if findings["count"] > limit:
        findings["findings"] = findings["findings"][:limit]
        findings["not_shown"] = findings["count"] - limit
        findings["note"] = "call list_findings (filter by severity / detector) for the rest"
    return [summary, json.dumps(findings, ensure_ascii=False)]


DOCS_PREFETCH_ID: Final = "prefetch_search_docs"


def wants_docs(question: str, terms: list[str]) -> bool:
    """A term starts a word of the question ("azalt" in "azaltmak", not "niye" in "saniye")."""
    q = question.casefold()
    return any(re.search(rf"(?<!\w){re.escape(t.casefold())}", q) for t in terms)


SOURCES_HEADER: Final = "Documentation searched (search_docs):"


def with_doc_sources(answer: str, messages: list[Message]) -> str:
    """Append the searched pages if the answer cites none of them.

    Small local models often use the passages but drop the links; the links are
    tool output, so the agent adds them instead of the model.
    """
    urls: list[str] = []
    for m in messages:
        if m.get("role") != "tool":
            continue
        try:
            results = json.loads(str(m["content"])).get("results", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        urls += [r["url"] for r in results if isinstance(r, dict) and "url" in r]
    pages = list(dict.fromkeys(u.split("#", 1)[0] for u in urls))
    if not pages or any(p in answer for p in pages):
        return answer
    listing = "\n".join(f"- {u}" for u in dict.fromkeys(urls))
    return f"{answer}\n\n{SOURCES_HEADER}\n{listing}"


def docs_prefetch(ctx: AgentContext, question: str) -> list[Message]:
    """A search_docs call with the question, as if the model had made it.

    Nothing if the best passage scores below ``agent.docs_prefetch_min_score``
    (off-topic questions like "how will the weather be" match a term too).
    """
    args = json.dumps({"query": question}, ensure_ascii=False)
    output = call_tool(ctx, "search_docs", args)
    results = json.loads(output).get("results") or []
    if not results or results[0]["score"] < ctx.config.agent.docs_prefetch_min_score:
        return []
    call: Message = {
        "id": DOCS_PREFETCH_ID,
        "type": "function",
        "function": {"name": "search_docs", "arguments": args},
    }
    return [
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": DOCS_PREFETCH_ID, "content": output},
    ]


@dataclass(frozen=True)
class ToolStep:
    """A tool call in progress (for progress display while the model works)."""

    name: str
    arguments: dict[str, Any]


def _new_tool_calls(update: dict[str, Any]) -> Iterator[ToolStep]:
    for message in (update.get("llm") or {}).get("messages", []):
        for call in message.get("tool_calls") or []:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            yield ToolStep(call["function"]["name"], args if isinstance(args, dict) else {})


class FlightAgent:
    """Multi-turn chat about one log; each question is verified on its own tools."""

    def __init__(self, ctx: AgentContext, complete: Complete | None = None) -> None:
        self.ctx = ctx
        self.graph = build_graph(ctx, complete or litellm_complete(ctx.config.agent))
        self.prefetched = prefetch_outputs(ctx) if ctx.config.agent.prefetch else []
        system = SYSTEM_PROMPT
        if self.prefetched:
            system += PREFETCH_HEADER + "\n".join(
                f"{name}: {out}" for name, out in zip(PREFETCH_TOOLS, self.prefetched, strict=True)
            )
        self.history: list[Message] = [{"role": "system", "content": system}]

    def ask(self, question: str) -> AgentReply:
        for item in self.ask_stream(question):
            if isinstance(item, AgentReply):
                return item
        raise RuntimeError("agent graph ended without an answer")  # pragma: no cover

    def ask_stream(self, question: str) -> Iterator[ToolStep | AgentReply]:
        """Like ``ask``, but yields each tool call as it is made, then the reply.

        Only the final, verified answer is yielded as text: streaming the model's
        tokens would show numbers before the verification node has checked them.
        """
        start = len(self.history)
        # Earlier tool results stay valid evidence for follow-up questions.
        earlier = self.prefetched + [
            str(m["content"]) for m in self.history if m.get("role") == "tool"
        ]
        cfg = self.ctx.config.agent
        pre: list[Message] = []
        if self.ctx.docs is not None and wants_docs(question, cfg.docs_prefetch_terms):
            yield ToolStep("search_docs", {"query": question})
            pre = docs_prefetch(self.ctx, question)
        state: dict[str, Any] = {}
        for mode, chunk in self.graph.stream(
            {
                "messages": [*self.history, {"role": "user", "content": question}, *pre],
                "tool_outputs": earlier + [str(m["content"]) for m in pre if m["role"] == "tool"],
                "rounds": 0,
                "question": question,
                "answer": "",
                "verification": None,
            },
            {"recursion_limit": 4 * self.ctx.config.agent.max_tool_rounds + 10},
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                state = chunk
                continue
            yield from _new_tool_calls(chunk)
        messages: list[Message] = state["messages"]
        # Keep the conversation (incl. tool results) for follow-up questions.
        self.history = messages
        calls = [
            c["function"]["name"]
            for m in messages[start:]
            for c in (m.get("tool_calls") or [])
            if c["id"] != DOCS_PREFETCH_ID
        ]
        prefetched = list(PREFETCH_TOOLS) if self.prefetched else []
        yield AgentReply(
            answer=with_doc_sources(state["answer"], messages[start:]),
            raw_answer=str(messages[-1].get("content") or ""),
            verification=state["verification"],
            tool_calls=calls,
            messages=messages[start:],
            prefetched=prefetched + (["search_docs"] if pre else []),
        )

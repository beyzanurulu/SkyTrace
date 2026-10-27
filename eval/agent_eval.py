"""Ask the real model the example questions (eval/agent_questions.yaml) and score it.

A question passes when skytrace.evaluation.agent_questions.check_reply finds no
problem: expected tools called, nothing unbacked, key facts present.
Replay-only questions (scripted hallucinations) are skipped. Needs the model of
``agent.model`` (local Ollama by default) to be reachable.

    uv run python eval/agent_eval.py
    uv run python eval/agent_eval.py --model ollama_chat/qwen2.5:3b

Output: eval/results/agent_eval_<model>.md (pass/fail, latency, answers).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from skytrace import FlightLog, load_config
from skytrace.agent import AgentContext, FlightAgent
from skytrace.agent.graph import Complete, Message, litellm_complete
from skytrace.agent.rag import DocSearch, DocsError
from skytrace.config import with_model
from skytrace.detectors import run_detectors
from skytrace.evaluation.agent_questions import check_reply

ROOT = Path(__file__).resolve().parents[1]
RATE_LIMIT_RETRIES = 6


class Throttled:
    """A Complete that keeps to ``rpm`` calls per minute and retries rate limits."""

    def __init__(self, complete: Complete, rpm: float) -> None:
        self.complete = complete
        self.interval = 60.0 / rpm
        self.last = 0.0
        self.waited = 0.0  # seconds slept, subtracted from the latency

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)
        self.waited += seconds

    def __call__(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        from litellm.exceptions import RateLimitError, ServiceUnavailableError

        for attempt in range(RATE_LIMIT_RETRIES + 1):
            gap = self.last + self.interval - time.monotonic()
            if gap > 0:
                self._sleep(gap)
            self.last = time.monotonic()
            try:
                return self.complete(messages, tools)
            except (RateLimitError, ServiceUnavailableError):
                if attempt == RATE_LIMIT_RETRIES:
                    raise
                self._sleep(min(60.0, 10.0 * 2**attempt))
        raise AssertionError("unreachable")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model", default=None, help="LiteLLM model string (default: agent.model)")
    p.add_argument("--questions", type=Path, default=ROOT / "eval" / "agent_questions.yaml")
    p.add_argument("--log", type=Path, default=ROOT / "tests" / "fixtures" / "sample_log_small.ulg")
    p.add_argument("--out-dir", type=Path, default=ROOT / "eval" / "results")
    p.add_argument(
        "--rpm",
        type=float,
        default=0,
        help="At most this many model calls per minute, retrying after rate limits "
        "(free cloud tiers). Waiting is not counted in the latency.",
    )
    p.add_argument(
        "--only",
        nargs="+",
        default=None,
        metavar="ID",
        help="Ask only these question ids (e.g. to finish a run within a daily quota).",
    )
    a = p.parse_args()

    cfg = load_config()
    if a.model:
        cfg = with_model(cfg, a.model)
    log = FlightLog.from_file(a.log, cfg)
    result = run_detectors(log, cfg)
    cases = [
        q
        for q in yaml.safe_load(a.questions.read_text("utf-8"))["questions"]
        if not q.get("replay_only") and (a.only is None or q["id"] in a.only)
    ]
    # Documentation questions need the index (`skytrace docs build`); without it
    # they fail, which is the honest score.
    try:
        docs: DocSearch | None = DocSearch(cfg.rag)
    except DocsError as exc:
        print(f"documentation search off: {exc}", file=sys.stderr)
        docs = None

    complete = Throttled(litellm_complete(cfg.agent), a.rpm) if a.rpm else None
    rows = []
    for case in cases:
        # A fresh agent per question: no answer depends on an earlier one.
        ctx = AgentContext(log, result, cfg, a.out_dir / "agent_plots", docs)
        agent = FlightAgent(ctx, complete)
        waited = complete.waited if complete else 0.0
        t0 = time.perf_counter()
        try:
            reply = agent.ask(case["question"])
            error = ""
        except Exception as exc:  # model unreachable, timeout, bad tool-call format ...
            reply, error = None, f"{type(exc).__name__}: {exc}"
        seconds = time.perf_counter() - t0 - ((complete.waited - waited) if complete else 0.0)
        problems = check_reply(case, reply) if reply is not None else [error]
        passed = not problems
        rows.append((case, reply, error, seconds, problems, passed))
        status = "PASS" if passed else "FAIL"
        called = reply.tool_calls if reply else "-"
        print(f"[{status}] {case['id']:24s} {seconds:6.1f} s  tools={called}")
        if error:
            print(f"        {error}", file=sys.stderr)
            if "Connection" in error or "connect" in error.lower():
                print("        Model not reachable; stopping.", file=sys.stderr)
                break

    n_pass = sum(r[-1] for r in rows)
    lines = [
        f"# Agent evaluation: `{cfg.agent.model}`",
        "",
        f"{date.today().isoformat()}, log `{a.log.name}`, {len(rows)} questions "
        f"(replay-only ones skipped). Pass = expected tools called, nothing unbacked and the "
        f"key facts present (skytrace.evaluation.agent_questions). "
        f"**{n_pass} / {len(rows)} passed**, median latency "
        f"{sorted(r[3] for r in rows)[len(rows) // 2]:.1f} s."
        if rows
        else "No questions run.",
        "",
        "| Question | Result | Latency (s) | Tools called | Problems |",
        "|---|---|---:|---|---|",
    ]
    for case, reply, _error, seconds, problems, passed in rows:
        called = ", ".join(reply.tool_calls) if reply else ""
        lines.append(
            f"| {case['id']} | {'PASS' if passed else 'FAIL'} | {seconds:.1f} | {called} "
            f"| {'; '.join(problems)} |"
        )
    lines += ["", "## Answers", ""]
    for case, reply, error, *_ in rows:
        answer = reply.answer if reply else f"(error) {error}"
        lines += [f"**{case['question']}**", "", answer.replace("\n", "  \n"), ""]

    a.out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9.]+", "_", cfg.agent.model).strip("_")
    # a partial run (--only) does not overwrite the full one
    out = a.out_dir / f"agent_eval_{slug}{'_only' if a.only else ''}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{n_pass} / {len(rows)} passed -> {out}")
    return 0 if rows and n_pass == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

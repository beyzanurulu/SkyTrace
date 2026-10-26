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
from dataclasses import replace
from datetime import date
from pathlib import Path

import yaml

from skytrace import FlightLog, load_config
from skytrace.agent import AgentContext, FlightAgent
from skytrace.detectors import run_detectors
from skytrace.evaluation.agent_questions import check_reply

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model", default=None, help="LiteLLM model string (default: agent.model)")
    p.add_argument("--questions", type=Path, default=ROOT / "eval" / "agent_questions.yaml")
    p.add_argument("--log", type=Path, default=ROOT / "tests" / "fixtures" / "sample_log_small.ulg")
    p.add_argument("--out-dir", type=Path, default=ROOT / "eval" / "results")
    a = p.parse_args()

    cfg = load_config()
    if a.model:
        cfg = replace(cfg, agent=replace(cfg.agent, model=a.model))
    log = FlightLog.from_file(a.log, cfg)
    result = run_detectors(log, cfg)
    cases = [
        q
        for q in yaml.safe_load(a.questions.read_text("utf-8"))["questions"]
        if not q.get("replay_only")
    ]

    rows = []
    for case in cases:
        # A fresh agent per question: no answer depends on an earlier one.
        agent = FlightAgent(AgentContext(log, result, cfg, a.out_dir / "agent_plots"))
        t0 = time.perf_counter()
        try:
            reply = agent.ask(case["question"])
            error = ""
        except Exception as exc:  # model unreachable, timeout, bad tool-call format ...
            reply, error = None, f"{type(exc).__name__}: {exc}"
        seconds = time.perf_counter() - t0
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
    out = a.out_dir / f"agent_eval_{slug}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{n_pass} / {len(rows)} passed -> {out}")
    return 0 if rows and n_pass == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

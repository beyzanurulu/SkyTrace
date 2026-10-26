"""End-to-end check of offline mode, meant for a container with no network.

    docker run --rm --network none -v "$PWD/eval/results:/app/eval/results" \
        skytrace:bundle python eval/offline_e2e.py

Runs every user-facing path once in offline mode (SKYTRACE_MODE=offline):
analyze + HTML report, documentation search, two agent questions (one about the
log, one that needs the docs), the web API, and a deliberate connection to the
internet that must be refused. Fails (exit 1) if any step fails or if anything
other than the deliberate probe tried to leave the machine.

Output: eval/results/offline_e2e.md
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import socket
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_log_small.ulg"
PROBE = ("pypi.org", 443)
QUESTIONS = (
    ("log", "Bu uçuşta hangi sorunlar tespit edildi?"),
    ("docs", "Titreşimi nasıl azaltırım?"),  # noqa: RUF001 (Turkish)
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "offline_e2e.md")
    a = p.parse_args()

    from skytrace import offline

    if not offline.is_offline():
        print("set SKYTRACE_MODE=offline", file=sys.stderr)
        return 2
    from skytrace import FlightLog, load_config

    cfg = load_config()
    offline.activate(cfg)

    rows: list[tuple[str, bool, float, str]] = []
    details: list[str] = []

    def step(name: str, fn: Callable[[], str]) -> Any:  # noqa: ANN401
        t0 = time.perf_counter()
        try:
            note, ok = fn(), True
        except Exception as exc:  # report every failure, keep going
            note, ok = f"{type(exc).__name__}: {exc}", False
        rows.append((name, ok, time.perf_counter() - t0, note))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {note}", flush=True)

    state: dict[str, Any] = {}

    def analyze() -> str:
        from skytrace.detectors import run_detectors
        from skytrace.report import render_html

        log = FlightLog.from_file(FIXTURE, cfg)
        result = run_detectors(log, cfg)
        html = render_html(log, result, cfg)
        if re.search(r"<(script|link)[^>]+(src|href)=[\"']https?:", html):
            raise AssertionError("report loads an external script or stylesheet")
        state.update(log=log, result=result)
        ids = ", ".join(f.id for f in result.findings)
        return f"{len(result.findings)} findings ({ids}), report {len(html) // 1024} kB"

    def docs() -> str:
        from skytrace.agent.rag import DocSearch

        state["docs"] = DocSearch(cfg.rag)
        hits = state["docs"].search("vibration too high")
        return f"top hit {hits[0]['url']} (score {hits[0]['score']:.2f})"

    def agent(kind: str, question: str) -> Callable[[], str]:
        def run() -> str:
            from skytrace.agent import AgentContext, FlightAgent

            ctx = AgentContext(
                state["log"],
                state["result"],
                cfg,
                ROOT / "eval" / "results" / "offline_plots",
                state.get("docs"),
            )
            reply = FlightAgent(ctx).ask(question)
            details.append(f"**{question}**\n\n{reply.answer}\n")
            if not reply.verification.ok:
                raise AssertionError(f"answer not verified: {reply.verification}")
            if kind == "docs" and "search_docs" not in reply.tool_calls + reply.prefetched:
                raise AssertionError("documentation was not searched")
            used = ", ".join(reply.prefetched + reply.tool_calls) or "none"
            return f"verified; tools: {used}"

        return run

    def api() -> str:
        from fastapi.testclient import TestClient

        from skytrace.api import create_app

        client = TestClient(create_app(cfg, docs=state.get("docs")))  # in-process, no socket
        status = client.get("/api/status").json()
        if status["mode"] != "offline":
            raise AssertionError(f"status mode {status['mode']}")
        with FIXTURE.open("rb") as f:
            res = client.post("/analyze", files={"file": (FIXTURE.name, f)})
        res.raise_for_status()
        page = client.get("/").text
        if re.search(r"(src|href)=[\"']https?:", page):
            raise AssertionError("web UI loads an external resource")
        n = len(res.json()["findings"])
        return f"status ok, upload -> {n} findings, UI self-contained"

    def probe() -> str:
        before = len(offline.BLOCKED)
        try:
            socket.create_connection(PROBE, timeout=3).close()
        except offline.OfflineNetworkError:
            return f"{PROBE[0]}:{PROBE[1]} refused by the network guard"
        except OSError as exc:
            if len(offline.BLOCKED) > before:
                return "refused by the network guard"
            raise AssertionError(
                f"not refused by the guard (the network refused it: {exc})"
            ) from exc
        raise AssertionError(f"connected to {PROBE[0]}: the guard did not stop it")

    network = "none" if not _has_route() else "available"
    step("analyze + HTML report", analyze)
    step("documentation search", docs)
    for kind, question in QUESTIONS:
        step(f"agent ({kind} question)", agent(kind, question))
    step("web API (in process)", api)
    leaked = list(offline.BLOCKED)  # anything refused so far was not deliberate
    step("internet probe refused", probe)
    if leaked:
        rows.append(("no other outgoing connection", False, 0.0, ", ".join(leaked)))
    else:
        rows.append(("no other outgoing connection", True, 0.0, "nothing else tried to connect"))

    passed = sum(ok for _, ok, _, _ in rows)
    lines = [
        "# Offline mode, end to end",
        "",
        f"{date.today().isoformat()}, `SKYTRACE_MODE=offline`, model `{cfg.agent.model}`, "
        f"embeddings `{cfg.rag.embedding_model}`, network: **{network}**, "
        f"{platform.system()} {platform.machine()}, GPU: {_gpu()}. "
        f"**{passed} / {len(rows)} passed.**",
        "",
        "| Step | Result | Time (s) | Notes |",
        "|---|---|---:|---|",
        *(f"| {n} | {'PASS' if ok else 'FAIL'} | {t:.1f} | {note} |" for n, ok, t, note in rows),
        "",
        "## Answers",
        "",
        *details,
    ]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{passed} / {len(rows)} passed -> {a.out}")
    return 0 if passed == len(rows) else 1


def _has_route() -> bool:
    """Whether the container has any non-loopback interface (``--network none`` has not)."""
    try:
        names = os.listdir("/sys/class/net")
    except OSError:
        return True  # not Linux: assume a network
    return any(n != "lo" for n in names)


def _gpu() -> str:
    return "yes" if Path("/dev/nvidia0").exists() or Path("/dev/dxg").exists() else "no (CPU)"


if __name__ == "__main__":
    sys.exit(main())

"""Record the model's answers to the sample flights' suggested questions.

    GEMINI_API_KEY=... uv run python eval/record_sample_answers.py --rpm 5

For every question in samples/samples.yaml the real agent answers once; answers
that pass the verification (every number, finding id and link backed by a tool
output) are stored in samples/answers.json with the model and the date. The demo
shows them instantly, labelled as recorded, so it keeps working when the cloud
model's free quota is used up. Answers that fail verification are not stored.
Already recorded questions are skipped unless --force.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

from skytrace import FlightLog, load_config
from skytrace.agent import AgentContext, FlightAgent
from skytrace.agent.graph import litellm_complete
from skytrace.api.app import ANSWERS_FILE, load_samples, reply_payload
from skytrace.config import with_model
from skytrace.detectors import run_detectors
from skytrace.evaluation.throttle import Throttled

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model", default="gemini/gemini-3.5-flash")
    p.add_argument("--rpm", type=float, default=5, help="model calls per minute (free tiers)")
    p.add_argument("--samples-dir", type=Path, default=ROOT / "samples")
    p.add_argument("--force", action="store_true", help="re-record already recorded questions")
    a = p.parse_args()

    cfg = with_model(load_config(), a.model)
    samples = load_samples(replace(cfg.demo, samples_dir=str(a.samples_dir)))
    out_file = a.samples_dir / ANSWERS_FILE
    stored: dict[str, list[dict[str, object]]] = (
        json.loads(out_file.read_text("utf-8")) if out_file.is_file() else {}
    )
    complete = Throttled(litellm_complete(cfg.agent), a.rpm)
    plots = Path(tempfile.mkdtemp())
    failed = 0
    for sample_id, sample in samples.items():
        done = {str(x["question"]) for x in stored.get(sample_id, [])}
        todo = [q for q in sample.questions if a.force or q not in done]
        if not todo:
            continue
        log = FlightLog.from_file(sample.path, cfg)
        result = run_detectors(log, cfg)
        known = {f.id for f in result.findings}
        for question in todo:
            agent = FlightAgent(AgentContext(log, result, cfg, plots, None), complete)
            try:
                reply = agent.ask(question)
            except Exception as exc:  # quota, network: keep what was recorded so far
                print(f"[ERR ] {sample_id}: {question} -> {type(exc).__name__}: {exc}")
                failed += 1
                continue
            if not reply.verification.ok:
                print(f"[SKIP] {sample_id}: {question} -> not verified {reply.verification}")
                failed += 1
                continue
            entry = {
                "question": question,
                "model": cfg.agent.model,
                "recorded_at": date.today().isoformat(),
                **reply_payload(reply, known),
                "plots": [],  # plot files are not kept with recorded answers
            }
            kept = [x for x in stored.get(sample_id, []) if x["question"] != question]
            stored[sample_id] = [*kept, entry]
            out_file.write_text(json.dumps(stored, ensure_ascii=False, indent=1), "utf-8")
            print(f"[OK  ] {sample_id}: {question}")
    total = sum(len(v) for v in stored.values())
    print(f"{total} recorded answers in {out_file} ({failed} not recorded this run)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Evaluate the rule detectors on the labeled log set.

Every ``data/labels/<log_id>.yaml`` (format: see ``skytrace.evaluation.labels``)
is paired with its log in ``--logs``: the ``log:`` field if set, otherwise
``<log_id>.ulg`` / ``<log_id>.bin``. All detectors run with the given config;
a finding matches a label of the same detector when IoU >= ``--iou``.

Output: a markdown report (per-detector precision / recall / F1, then every
missed fault and false positive) in --out, default eval/results/detector_eval.md.

    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --config my.yaml --iou 0.5 --min-severity critical
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from skytrace import FlightLog, load_config
from skytrace.config import SkyTraceConfig
from skytrace.detectors import DETECTORS, run_detectors
from skytrace.detectors.base import Severity
from skytrace.evaluation.labels import (
    DetectorCounts,
    LabelError,
    LogLabels,
    LogMatch,
    load_labels,
    match_log,
    total_counts,
)

LOG_SUFFIXES = (".ulg", ".bin")


def find_log(labels: LogLabels, logs: Path) -> Path | None:
    names = [labels.log] if labels.log else [labels.log_id + s for s in LOG_SUFFIXES]
    for name in names:
        if (logs / name).is_file():
            return logs / name
    return None


def evaluate(
    label_dir: Path,
    logs: Path,
    cfg: SkyTraceConfig,
    iou_threshold: float,
    min_severity: Severity,
) -> tuple[list[LogMatch], list[str]]:
    matches: list[LogMatch] = []
    skipped: list[str] = []
    for path in sorted(label_dir.glob("*.yaml")):
        try:
            labels = load_labels(path)
        except LabelError as exc:
            skipped.append(f"{path.name}: {exc}")
            continue
        log_path = find_log(labels, logs)
        if log_path is None:
            skipped.append(f"{path.name}: log not found in {logs}")
            continue
        result = run_detectors(FlightLog.from_file(log_path, cfg), cfg)
        matches.append(
            match_log(
                labels.log_id,
                labels.faults,
                result.findings,
                iou_threshold=iou_threshold,
                min_severity=min_severity,
            )
        )
    return matches, skipped


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def render_markdown(
    matches: list[LogMatch],
    skipped: list[str],
    iou_threshold: float,
    min_severity: Severity,
) -> str:
    totals = total_counts(matches)
    overall = DetectorCounts()
    for c in totals.values():
        overall.add(c)
    lines = [
        "# Detector evaluation",
        "",
        f"Generated {date.today().isoformat()} by `eval/run_eval.py`. "
        f"{len(matches)} labeled logs, match = same detector and IoU ≥ {iou_threshold:g}, "
        f"findings below `{min_severity}` ignored. Precision is per finding, recall per "
        "labeled fault; `-` = undefined (no findings / no labels).",
        "",
        "| Detector | Labels | Detected | Findings | Correct | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for det in DETECTORS:
        c = totals.get(det, DetectorCounts())
        lines.append(
            f"| {det} | {c.labels} | {c.labels_detected} | {c.findings} | {c.findings_correct} "
            f"| {_fmt(c.precision)} | {_fmt(c.recall)} | {_fmt(c.f1)} |"
        )
    lines.append(
        f"| **all** | {overall.labels} | {overall.labels_detected} | {overall.findings} "
        f"| {overall.findings_correct} | {_fmt(overall.precision)} | {_fmt(overall.recall)} "
        f"| {_fmt(overall.f1)} |"
    )

    missed = [(m.log_id, lb) for m in matches for lb in m.missed]
    lines += ["", "## Missed faults", ""]
    if missed:
        lines += ["| Log | Type | Interval (s) | Note |", "|---|---|---|---|"]
        lines += [
            f"| {log_id} | {lb.type} | {lb.t_start:.1f}-{lb.t_end:.1f} | {lb.note} |"
            for log_id, lb in missed
        ]
    else:
        lines.append("None.")

    fps = [(m.log_id, f) for m in matches for f in m.false_positives]
    lines += ["", "## False positives", ""]
    if fps:
        lines += ["| Log | Detector | Severity | Interval (s) | Summary |", "|---|---|---|---|---|"]
        lines += [
            f"| {log_id} | {f.detector} | {f.severity} | {f.t_start:.1f}-{f.t_end:.1f} "
            f"| {f.summary} |"
            for log_id, f in fps
        ]
    else:
        lines.append("None.")

    if skipped:
        lines += ["", "## Skipped label files", ""] + [f"- {s}" for s in skipped]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--labels", type=Path, default=Path("data/labels"))
    p.add_argument("--logs", type=Path, default=Path("data/raw"))
    p.add_argument("--out", type=Path, default=Path("eval/results/detector_eval.md"))
    p.add_argument("--config", type=Path, default=None, help="YAML config override")
    p.add_argument("--iou", type=float, default=0.3, help="min IoU for a match (default 0.3)")
    p.add_argument("--min-severity", choices=["info", "warn", "critical"], default="warn")
    args = p.parse_args(argv)

    if not args.labels.is_dir():
        print(f"no label directory: {args.labels}", file=sys.stderr)
        return 2
    cfg = load_config(args.config)
    matches, skipped = evaluate(args.labels, args.logs, cfg, args.iou, args.min_severity)
    report = render_markdown(matches, skipped, args.iou, args.min_severity)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

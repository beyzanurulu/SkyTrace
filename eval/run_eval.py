"""Evaluate the rule detectors on the labeled log set.

Every ``data/labels/<log_id>.yaml`` (format: see ``skytrace.evaluation.labels``)
is paired with its log in ``--logs``: the ``log:`` field if set, otherwise
``<log_id>.ulg`` / ``<log_id>.bin``. All detectors run with the given config;
a finding matches a label of the same detector when IoU >= ``--iou``.

Output: a markdown report (per-detector precision / recall / F1, then every
missed fault and false positive) in --out, default eval/results/detector_eval.md.

``--ml`` also runs the unsupervised anomaly detector (skytrace.anomaly). There
are no ``ml_anomaly`` labels, so its findings stay out of the table above and
get their own section: how many fall inside a labeled fault (any type), outside
one, or on a clean flight, and how many were merged into rule findings.

    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --config my.yaml --iou 0.5 --min-severity critical
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from skytrace import FlightLog, load_config
from skytrace.anomaly import NAME as ML_DETECTOR
from skytrace.anomaly import detect as anomaly_detect
from skytrace.config import SkyTraceConfig
from skytrace.detectors import DETECTORS, run_detectors
from skytrace.detectors.base import Finding, Severity
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
    ml: bool = False,
) -> tuple[list[LogMatch], list[str], list[MlRow]]:
    matches: list[LogMatch] = []
    skipped: list[str] = []
    ml_rows: list[MlRow] = []
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
        log = FlightLog.from_file(log_path, cfg)
        result = run_detectors(log, cfg, ml=ml)
        rule_findings = [f for f in result.findings if f.detector != ML_DETECTOR]
        matches.append(
            match_log(
                labels.log_id,
                labels.faults,
                rule_findings,
                iou_threshold=iou_threshold,
                min_severity=min_severity,
            )
        )
        if ml:
            # Unmerged ML findings: would ML alone have flagged the labeled faults?
            standalone = anomaly_detect(log, cfg, [])
            ml_rows.append(ml_row(labels, result.findings, result.notes, standalone))
    return matches, skipped, ml_rows


@dataclass
class MlRow:
    log_id: str
    clean: bool
    faults: int
    in_fault: list[Finding] = field(default_factory=list)
    outside: list[Finding] = field(default_factory=list)
    merged: int = 0
    faults_hit: int = 0


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 <= b1 and b0 <= a1


def ml_row(
    labels: LogLabels,
    findings: list[Finding],
    notes: list[str],
    standalone: list[Finding] | None = None,
) -> MlRow:
    """Where the ML findings of one log fall relative to its labeled faults.

    ``findings`` are after merging with rule findings (what a user sees);
    ``standalone`` are the ML findings before merging, used for ``faults_hit``.
    """
    row = MlRow(labels.log_id, clean=not labels.faults, faults=len(labels.faults))
    ml_findings = [f for f in findings if f.detector == ML_DETECTOR]
    for f in ml_findings:
        inside = any(_overlaps(f.t_start, f.t_end, lb.t_start, lb.t_end) for lb in labels.faults)
        (row.in_fault if inside else row.outside).append(f)
    seen = standalone if standalone is not None else ml_findings
    row.faults_hit = sum(
        any(_overlaps(f.t_start, f.t_end, lb.t_start, lb.t_end) for f in seen)
        for lb in labels.faults
    )
    row.merged = sum(
        int(n.split(":", 1)[1].split()[0]) for n in notes if "overlapped rule findings" in n
    )
    return row


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


def render_ml_markdown(rows: list[MlRow]) -> str:
    """ML anomaly section: no ml_anomaly labels exist, so report where findings fall."""
    clean = [r for r in rows if r.clean]
    faulty = [r for r in rows if not r.clean]
    in_fault = sum(len(r.in_fault) for r in rows)
    outside = sum(len(r.outside) for r in faulty)
    on_clean = sum(len(r.outside) for r in clean)
    merged = sum(r.merged for r in rows)
    faults = sum(r.faults for r in rows)
    hit = sum(r.faults_hit for r in rows)
    lines = [
        "",
        "## ML anomaly detection (`--ml`)",
        "",
        "Not part of the table above (there are no `ml_anomaly` labels). Findings of any "
        "severity; ML findings overlapping a rule finding are merged into it and only "
        "counted in the merged column.",
        "",
        "| Logs | Clean logs | ML findings in a labeled fault | outside a fault "
        "| on clean flights | merged into rule findings "
        "| labeled faults ML alone would flag |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {len(rows)} | {len(clean)} | {in_fault} | {outside} | {on_clean} | {merged} "
        f"| {hit} / {faults} |",
    ]
    listed = [
        (r.log_id, f, "clean flight" if r.clean else "outside fault")
        for r in rows
        for f in r.outside
    ]
    if listed:
        lines += [
            "",
            "| Log | Where | Severity | Interval (s) | Summary |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {log_id} | {where} | {f.severity} | {f.t_start:.1f}-{f.t_end:.1f} | {f.summary} |"
            for log_id, f, where in listed
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--labels", type=Path, default=Path("data/labels"))
    p.add_argument("--logs", type=Path, default=Path("data/raw"))
    p.add_argument("--out", type=Path, default=Path("eval/results/detector_eval.md"))
    p.add_argument("--config", type=Path, default=None, help="YAML config override")
    p.add_argument("--iou", type=float, default=0.3, help="min IoU for a match (default 0.3)")
    p.add_argument("--min-severity", choices=["info", "warn", "critical"], default="warn")
    p.add_argument("--ml", action="store_true", help="also run ML anomaly detection")
    args = p.parse_args(argv)

    if not args.labels.is_dir():
        print(f"no label directory: {args.labels}", file=sys.stderr)
        return 2
    cfg = load_config(args.config)
    matches, skipped, ml_rows = evaluate(
        args.labels, args.logs, cfg, args.iou, args.min_severity, ml=args.ml
    )
    report = render_markdown(matches, skipped, args.iou, args.min_severity)
    if args.ml:
        report += render_ml_markdown(ml_rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

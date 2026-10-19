"""Labeled fault intervals and interval matching for detector evaluation.

Label file ``data/labels/<log_id>.yaml``::

    log: 2024-05-01_hover.ulg   # optional, file name in the log directory
    source: sitl                # optional, free text (sitl / real / ...)
    faults:
      - type: gps               # a detector name, see skytrace.detectors.DETECTORS
        t_start: 120.0          # seconds since log start, same time base as FlightLog.t
        t_end: 150.0
        note: "failure gps off" # optional; quote text (YAML reads bare off/on as booleans)
    # faults: []                # a clean flight (only produces false positives)

Matching: a finding and a label of the same detector match when their
intersection-over-union (IoU) is at least ``iou_threshold``. Recall is counted
per label (detected if any finding matches it), precision per finding
(correct if it matches any label), so several findings of one detector
covering one fault (e.g. GPS fix and satellite count) are all correct.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from skytrace.detectors import DETECTORS
from skytrace.detectors.base import SEVERITY_RANK, Finding, Severity


class LabelError(ValueError):
    """Raised when a label file is malformed."""


@dataclass(frozen=True)
class FaultLabel:
    type: str
    t_start: float
    t_end: float
    note: str = ""


@dataclass(frozen=True)
class LogLabels:
    log_id: str
    faults: list[FaultLabel]
    log: str | None = None
    source: str | None = None


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LabelError(f"{where}: expected a number, got {value!r}")
    return float(value)


def load_labels(path: str | Path) -> LogLabels:
    p = Path(path)
    raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LabelError(f"{p}: expected a mapping")
    faults: list[FaultLabel] = []
    for i, item in enumerate(raw.get("faults") or []):
        where = f"{p}: faults[{i}]"
        if not isinstance(item, dict):
            raise LabelError(f"{where}: expected a mapping")
        kind = item.get("type")
        if kind not in DETECTORS:
            raise LabelError(f"{where}: type must be one of {sorted(DETECTORS)}, got {kind!r}")
        t0 = _number(item.get("t_start"), f"{where}.t_start")
        t1 = _number(item.get("t_end"), f"{where}.t_end")
        if t1 < t0:
            raise LabelError(f"{where}: t_end < t_start")
        faults.append(FaultLabel(str(kind), t0, t1, str(item.get("note", ""))))
    log = raw.get("log")
    source = raw.get("source")
    return LogLabels(
        log_id=p.stem,
        faults=faults,
        log=None if log is None else str(log),
        source=None if source is None else str(source),
    )


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Intersection over union of two closed intervals; zero-length intervals use a point test."""
    inter = min(a[1], b[1]) - max(a[0], b[0])
    if inter < 0:
        return 0.0
    union = max(a[1], b[1]) - min(a[0], b[0])
    return 1.0 if union == 0 else inter / union


@dataclass
class DetectorCounts:
    labels: int = 0
    labels_detected: int = 0
    findings: int = 0
    findings_correct: int = 0

    @property
    def precision(self) -> float | None:
        return None if self.findings == 0 else self.findings_correct / self.findings

    @property
    def recall(self) -> float | None:
        return None if self.labels == 0 else self.labels_detected / self.labels

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)

    def add(self, other: DetectorCounts) -> None:
        self.labels += other.labels
        self.labels_detected += other.labels_detected
        self.findings += other.findings
        self.findings_correct += other.findings_correct


@dataclass(frozen=True)
class LogMatch:
    log_id: str
    counts: dict[str, DetectorCounts]
    missed: list[FaultLabel] = field(default_factory=list)
    false_positives: list[Finding] = field(default_factory=list)


def match_log(
    log_id: str,
    labels: Sequence[FaultLabel],
    findings: Iterable[Finding],
    *,
    iou_threshold: float,
    min_severity: Severity = "warn",
    detectors: Iterable[str] = DETECTORS,
) -> LogMatch:
    """Per-detector counts for one log. Findings below ``min_severity`` are ignored."""
    kept = [f for f in findings if SEVERITY_RANK[f.severity] >= SEVERITY_RANK[min_severity]]
    counts: dict[str, DetectorCounts] = {}
    missed: list[FaultLabel] = []
    false_positives: list[Finding] = []
    for det in detectors:
        det_labels = [lb for lb in labels if lb.type == det]
        det_findings = [f for f in kept if f.detector == det]
        hit = [
            [
                iou((lb.t_start, lb.t_end), (f.t_start, f.t_end)) >= iou_threshold
                for f in det_findings
            ]
            for lb in det_labels
        ]
        c = DetectorCounts(labels=len(det_labels), findings=len(det_findings))
        for lb, row in zip(det_labels, hit, strict=True):
            if any(row):
                c.labels_detected += 1
            else:
                missed.append(lb)
        for j, f in enumerate(det_findings):
            if any(row[j] for row in hit):
                c.findings_correct += 1
            else:
                false_positives.append(f)
        counts[det] = c
    return LogMatch(log_id, counts, missed, false_positives)


def total_counts(matches: Iterable[LogMatch]) -> dict[str, DetectorCounts]:
    out: dict[str, DetectorCounts] = {}
    for m in matches:
        for det, c in m.counts.items():
            out.setdefault(det, DetectorCounts()).add(c)
    return out

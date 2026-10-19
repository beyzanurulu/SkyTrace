"""Threshold calibration on a labeled log set.

The procedure is deliberately simple and fully reproducible:

1. Every log gets one per-log statistic (e.g. the 95th percentile of a metric
   over armed samples).
2. Logs are split into a *calibration* and a *test* half by **group** (vehicle),
   so the same airframe never appears on both sides, stratified by label and
   deterministic (hash of a salt + group key, no RNG state).
3. Thresholds are percentiles of the calibration half only:
   ``warn`` = a high percentile of the negatives (clean flights),
   ``critical`` = a percentile of the positives, if that lies above ``warn``.
4. The test half is used only to measure precision / recall.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

import numpy as np

T = TypeVar("T")


def _hash01(salt: str, key: str) -> float:
    digest = hashlib.sha256(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


@dataclass(frozen=True)
class Split(Generic[T]):
    calibration: list[T]
    test: list[T]


def split_by_group(
    items: Sequence[T],
    *,
    group: Callable[[T], str],
    label: Callable[[T], bool],
    calibration_fraction: float = 0.5,
    salt: str = "skytrace-split-v1",
) -> Split[T]:
    """Deterministic, group-aware, label-stratified split.

    A group is positive if any of its items is positive. Within each class the
    groups are ordered by ``hash(salt, group)`` and the first
    ``ceil(fraction * n_groups)`` go to calibration.
    """
    if not 0 < calibration_fraction < 1:
        raise ValueError("calibration_fraction must be in (0, 1)")
    groups: dict[str, list[T]] = {}
    for item in items:
        groups.setdefault(group(item), []).append(item)
    calib_groups: set[str] = set()
    for cls in (True, False):
        keys = sorted(
            (g for g, members in groups.items() if any(map(label, members)) == cls),
            key=lambda g: _hash01(salt, g),
        )
        calib_groups.update(keys[: math.ceil(calibration_fraction * len(keys))])
    calibration = [i for i in items if group(i) in calib_groups]
    test = [i for i in items if group(i) not in calib_groups]
    return Split(calibration=calibration, test=test)


@dataclass(frozen=True)
class ThresholdChoice:
    warn: float
    critical: float | None
    warn_rule: str
    critical_rule: str
    n_negative: int
    n_positive: int


def choose_thresholds(
    negatives: Sequence[float],
    positives: Sequence[float],
    *,
    warn_percentile: float = 95.0,
    critical_percentile: float = 50.0,
) -> ThresholdChoice:
    """``warn`` = P{warn_percentile} of negatives; ``critical`` = P{critical_percentile}
    of positives when it is above ``warn``, else ``None`` (warn level only)."""
    neg = np.asarray([v for v in negatives if np.isfinite(v)], dtype=np.float64)
    pos = np.asarray([v for v in positives if np.isfinite(v)], dtype=np.float64)
    if neg.size == 0:
        raise ValueError("need at least one finite negative statistic")
    warn = float(np.percentile(neg, warn_percentile))
    warn_rule = f"P{warn_percentile:g} of {neg.size} negative calibration logs"
    critical: float | None = None
    critical_rule = "none (no positives)"
    if pos.size:
        candidate = float(np.percentile(pos, critical_percentile))
        if candidate > warn:
            critical = candidate
            critical_rule = f"P{critical_percentile:g} of {pos.size} positive calibration logs"
        else:
            critical_rule = f"none: P{critical_percentile:g} of positives ({candidate:.3g}) <= warn"
    return ThresholdChoice(warn, critical, warn_rule, critical_rule, int(neg.size), int(pos.size))


@dataclass(frozen=True)
class BinaryMetrics:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else float("nan")

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def false_positive_rate(self) -> float:
        return self.fp / (self.fp + self.tn) if self.fp + self.tn else float("nan")


def binary_metrics(pairs: Iterable[tuple[bool, bool]]) -> BinaryMetrics:
    """Confusion counts from ``(predicted, actual)`` pairs (log level)."""
    tp = fp = fn = tn = 0
    for predicted, actual in pairs:
        if predicted and actual:
            tp += 1
        elif predicted:
            fp += 1
        elif actual:
            fn += 1
        else:
            tn += 1
    return BinaryMetrics(tp, fp, fn, tn)

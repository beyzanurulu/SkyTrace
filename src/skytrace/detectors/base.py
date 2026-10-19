"""Shared detector machinery: the Finding type and interval helpers.

Every number in a Finding (times, value, threshold, numbers in ``summary``)
comes straight from the log data and the config; nothing is estimated.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from skytrace.parsers.schema import FlightLog, time_index

Severity = Literal["info", "warn", "critical"]
Direction = Literal["above", "below"]

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

Describe = Callable[[Severity, float, float, float, float], str]
"""``describe(severity, value, threshold, t_start, t_end) -> summary``."""

SEVERITY_RANK: dict[Severity, int] = {"info": 0, "warn": 1, "critical": 2}


@dataclass(frozen=True)
class Finding:
    """One detected issue. ``id`` is assigned by :func:`skytrace.detectors.run_detectors`."""

    detector: str
    severity: Severity
    t_start: float
    t_end: float
    metric: str
    value: float
    threshold: float
    summary: str
    id: str = ""
    evidence_plot: str | None = None

    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start


def intervals(
    t: FloatArray, mask: BoolArray, *, min_duration_s: float, merge_gap_s: float
) -> list[tuple[int, int]]:
    """Inclusive index ranges ``(i, j)`` where ``mask`` is true.

    Runs separated by at most ``merge_gap_s`` seconds are merged first; runs
    shorter than ``min_duration_s`` (``t[j] - t[i]``) are then dropped.
    """
    if len(t) != len(mask):
        raise ValueError("t and mask must have the same length")
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    # Split where consecutive true samples are not adjacent or are too far apart in time.
    breaks = np.flatnonzero((np.diff(idx) > 1) & (np.diff(t[idx]) > merge_gap_s))
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))
    return [
        (int(i), int(j)) for i, j in zip(starts, ends, strict=True) if t[j] - t[i] >= min_duration_s
    ]


def armed_mask(log: FlightLog, t: FloatArray) -> BoolArray:
    """True where the vehicle is armed at time ``t``.

    Uses arm/disarm events. A log without any is treated as armed throughout.
    Before the first event the state is the opposite of that event.
    """
    ev = log.events[log.events["kind"].isin(["arm", "disarm"])]
    if ev.empty:
        return np.ones(len(t), dtype=bool)
    ev_t = ev["t"].to_numpy(dtype=np.float64)
    ev_armed = (ev["kind"] == "arm").to_numpy()
    pos = np.searchsorted(ev_t, t, side="right") - 1
    initial = not bool(ev_armed[0])
    state: BoolArray = np.where(pos >= 0, ev_armed[np.clip(pos, 0, None)], initial)
    return state


def active_mask(log: FlightLog, df: pd.DataFrame, only_when_armed: bool) -> BoolArray:
    t = df["t"].to_numpy(dtype=np.float64)
    if only_when_armed:
        return armed_mask(log, t)
    return np.ones(len(t), dtype=bool)


def rolling_time(values: pd.Series, t: pd.Series, window_s: float, how: str) -> FloatArray:
    """Time-based trailing rolling ``mean``/``max``/``min``/``std`` over ``window_s``."""
    s = pd.Series(values.to_numpy(dtype=np.float64), index=time_index(t))
    r = s.rolling(pd.Timedelta(seconds=window_s), min_periods=1)
    out: pd.Series = getattr(r, how)()
    return out.to_numpy(dtype=np.float64)


def threshold_findings(
    *,
    detector: str,
    metric: str,
    t: FloatArray,
    values: FloatArray,
    active: BoolArray,
    warn: float,
    critical: float | None,
    direction: Direction,
    min_duration_s: float,
    merge_gap_s: float,
    describe: Describe,
) -> list[Finding]:
    """Findings where ``values`` cross ``warn`` (and optionally ``critical``).

    An interval opens where the warn threshold is violated for at least
    ``min_duration_s``; it is ``critical`` if any sample inside also violates
    ``critical``. ``value`` is the worst sample in the interval.
    ``describe(severity, value, threshold, t_start, t_end)`` builds the summary.
    NaN samples never violate a threshold.
    """
    valid = active & ~np.isnan(values)
    bad = valid & ((values > warn) if direction == "above" else (values < warn))

    findings: list[Finding] = []
    for i, j in intervals(t, bad, min_duration_s=min_duration_s, merge_gap_s=merge_gap_s):
        seg = values[i : j + 1]
        seg = seg[~np.isnan(seg)]
        worst = float(seg.max() if direction == "above" else seg.min())
        is_critical = critical is not None and (
            worst > critical if direction == "above" else worst < critical
        )
        severity: Severity = "critical" if is_critical else "warn"
        threshold = critical if is_critical and critical is not None else warn
        t0, t1 = float(t[i]), float(t[j])
        findings.append(
            Finding(
                detector=detector,
                severity=severity,
                t_start=t0,
                t_end=t1,
                metric=metric,
                value=worst,
                threshold=threshold,
                summary=describe(severity, worst, threshold, t0, t1),
            )
        )
    return findings

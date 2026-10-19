"""High vibration and accelerometer clipping."""

from __future__ import annotations

import numpy as np

from skytrace.config import DetectorsConfig
from skytrace.detectors.base import (
    BoolArray,
    Finding,
    FloatArray,
    Severity,
    active_mask,
    intervals,
    threshold_findings,
)
from skytrace.parsers.schema import FlightLog

NAME = "vibration"


def detect(log: FlightLog, cfg: DetectorsConfig, notes: list[str]) -> list[Finding]:
    vib = log.vibration
    if vib.empty:
        notes.append("vibration: no vibration data, detector skipped")
        return []
    c = cfg.vibration
    t = vib["t"].to_numpy(dtype=np.float64)
    active = active_mask(log, vib, cfg.only_when_armed)
    findings: list[Finding] = []

    for axis in ("vib_x", "vib_y", "vib_z"):

        def describe(
            sev: Severity, value: float, thr: float, t0: float, t1: float, axis: str = axis
        ) -> str:
            return (
                f"High vibration on {axis[-1].upper()} axis: peak {value:.1f} m/s² "
                f"(threshold {thr:.1f}) over {t1 - t0:.1f} s"
            )

        findings += threshold_findings(
            detector=NAME,
            metric=axis,
            t=t,
            values=vib[axis].to_numpy(dtype=np.float64),
            active=active,
            warn=c.accel_std_warn,
            critical=c.accel_std_critical,
            direction="above",
            min_duration_s=c.min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=describe,
        )

    findings += _clipping(log, cfg, t, active, notes)
    return findings


def _clipping(
    log: FlightLog,
    cfg: DetectorsConfig,
    t: FloatArray,
    active: BoolArray,
    notes: list[str],
) -> list[Finding]:
    counts = log.vibration["clip_count"].to_numpy(dtype=np.float64)
    if np.isnan(counts).all():
        notes.append("vibration: no clipping counters, clipping check skipped")
        return []
    # Increments of the cumulative counter; NaN gaps and counter resets count as 0.
    inc = np.diff(counts, prepend=np.nan)
    inc = np.where(np.isnan(inc) | (inc < 0), 0.0, inc)
    mask = active & (inc > 0)

    c = cfg.vibration
    findings: list[Finding] = []
    for i, j in intervals(t, mask, min_duration_s=0.0, merge_gap_s=c.clip_merge_gap_s):
        total = float(inc[i : j + 1].sum())
        critical = total >= c.clip_critical_count
        severity: Severity = "critical" if critical else "warn"
        threshold = float(c.clip_critical_count) if critical else 0.0
        t0, t1 = float(t[i]), float(t[j])
        findings.append(
            Finding(
                detector=NAME,
                severity=severity,
                t_start=t0,
                t_end=t1,
                metric="clip_count",
                value=total,
                threshold=threshold,
                summary=(
                    f"Accelerometer clipping: {total:.0f} events between {t0:.1f} s and {t1:.1f} s"
                ),
            )
        )
    return findings

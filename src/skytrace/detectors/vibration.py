"""High vibration and accelerometer clipping.

Both checks use thresholds chosen by ``LogMetadata.vib_metric_source``: PX4's
``accel_vibration_metric`` and ArduPilot's ``VIBE`` are on different scales,
so a log is never compared against another source's thresholds.
"""

from __future__ import annotations

import numpy as np

from skytrace.config import DetectorsConfig, VibrationSourceThresholds
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
    source = log.metadata.vib_metric_source
    if source is None:
        notes.append("vibration: vibration metric source unknown, detector skipped")
        return []
    thr = cfg.vibration.for_source(source)
    t = vib["t"].to_numpy(dtype=np.float64)
    active = active_mask(log, vib, cfg.only_when_armed)
    findings = _metric(log, cfg, thr, source, t, active, notes)
    findings += _clipping(log, cfg, thr, source, t, active, notes)
    return findings


def _metric(
    log: FlightLog,
    cfg: DetectorsConfig,
    thr: VibrationSourceThresholds,
    source: str,
    t: FloatArray,
    active: BoolArray,
    notes: list[str],
) -> list[Finding]:
    values = log.vibration["accel_vib_metric"].to_numpy(dtype=np.float64)
    if np.isnan(values).all():
        notes.append("vibration: no accel vibration metric, vibration level check skipped")
        return []
    if thr.metric_warn is None:
        notes.append(
            f"vibration: no calibrated thresholds for {source} "
            f"(detectors.vibration.{source}.metric_warn), vibration level check skipped"
        )
        return []

    def describe(sev: Severity, value: float, threshold: float, t0: float, t1: float) -> str:
        return (
            f"High vibration: accel vibration metric {value:.2f} ({source}, "
            f"threshold {threshold:.2f}) for {t1 - t0:.1f} s"
        )

    return threshold_findings(
        detector=NAME,
        metric="accel_vib_metric",
        t=t,
        values=values,
        active=active,
        warn=thr.metric_warn,
        critical=thr.metric_critical,
        direction="above",
        min_duration_s=cfg.vibration.min_duration_s,
        merge_gap_s=cfg.merge_gap_s,
        describe=describe,
    )


def _clipping(
    log: FlightLog,
    cfg: DetectorsConfig,
    thr: VibrationSourceThresholds,
    source: str,
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

    findings: list[Finding] = []
    for i, j in intervals(t, mask, min_duration_s=0.0, merge_gap_s=cfg.vibration.clip_merge_gap_s):
        total = float(inc[i : j + 1].sum())
        critical = total >= thr.clip_critical_count
        severity: Severity = "critical" if critical else "warn"
        threshold = float(thr.clip_critical_count) if critical else 0.0
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
                    f"Accelerometer clipping: {total:.0f} clipped samples ({source}) between "
                    f"{t0:.1f} s and {t1:.1f} s"
                ),
            )
        )
    return findings

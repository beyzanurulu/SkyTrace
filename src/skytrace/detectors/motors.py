"""Motor saturation and imbalance."""

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
    rolling_time,
    threshold_findings,
)
from skytrace.parsers.schema import FlightLog

NAME = "motors"


def detect(log: FlightLog, cfg: DetectorsConfig, notes: list[str]) -> list[Finding]:
    motors = log.motors
    if motors.empty or log.motor_count == 0:
        notes.append("motors: no motor data, detector skipped")
        return []
    t = motors["t"].to_numpy(dtype=np.float64)
    active = active_mask(log, motors, cfg.only_when_armed)
    findings = _saturation(log, cfg, t, active)
    if not log.metadata.motor_count_known:
        notes.append(
            "motors: motor count unknown (outputs may include servos), imbalance check "
            "skipped; set parser.motors.count"
        )
    elif log.motor_count < 2:
        notes.append("motors: fewer than 2 motors, imbalance check skipped")
    else:
        findings += _imbalance(log, cfg, t, active)
    return findings


def imbalance_deviation(log: FlightLog, window_s: float) -> FloatArray:
    """Per-motor rolling mean minus the mean over all motors; shape (samples, motors)."""
    cols = [f"m{n}" for n in range(1, log.motor_count + 1)]
    smooth = np.column_stack(
        [rolling_time(log.motors[col], log.motors["t"], window_s, "mean") for col in cols]
    )
    deviation: FloatArray = smooth - np.nanmean(smooth, axis=1, keepdims=True)
    return deviation


def _saturation(
    log: FlightLog, cfg: DetectorsConfig, t: FloatArray, active: BoolArray
) -> list[Finding]:
    c = cfg.motors
    findings: list[Finding] = []
    for n in range(1, log.motor_count + 1):
        out = log.motors[f"m{n}"].to_numpy(dtype=np.float64)
        mask = active & (out >= c.saturation_level)  # NaN compares False
        for i, j in intervals(
            t, mask, min_duration_s=c.saturation_warn_s, merge_gap_s=cfg.merge_gap_s
        ):
            t0, t1 = float(t[i]), float(t[j])
            duration = t1 - t0
            critical = duration >= c.saturation_critical_s
            severity: Severity = "critical" if critical else "warn"
            findings.append(
                Finding(
                    detector=NAME,
                    severity=severity,
                    t_start=t0,
                    t_end=t1,
                    metric=f"m{n}_saturated_s",
                    value=duration,
                    threshold=c.saturation_critical_s if critical else c.saturation_warn_s,
                    summary=(
                        f"Motor {n} saturated (output >= {c.saturation_level * 100:.0f}%) "
                        f"for {duration:.1f} s"
                    ),
                )
            )
    return findings


def _imbalance(
    log: FlightLog, cfg: DetectorsConfig, t: FloatArray, active: BoolArray
) -> list[Finding]:
    c = cfg.motors
    cols = [f"m{n}" for n in range(1, log.motor_count + 1)]
    deviation = imbalance_deviation(log, c.imbalance_window_s)
    findings: list[Finding] = []
    for k, col in enumerate(cols):
        signed = deviation[:, k]
        n = k + 1

        def describe(
            sev: Severity,
            v: float,
            thr: float,
            t0: float,
            t1: float,
            n: int = n,
            signed: FloatArray = signed,
        ) -> str:
            seg = signed[(t >= t0) & (t <= t1)]
            side = "above" if np.nanmean(seg) > 0 else "below"
            return (
                f"Motor {n} runs {side} the motor average by up to {v:.2f} "
                f"(threshold {thr:.2f}, {c.imbalance_window_s:.0f} s mean) for {t1 - t0:.1f} s"
            )

        findings += threshold_findings(
            detector=NAME,
            metric=f"{col}_imbalance",
            t=t,
            values=np.abs(signed),
            active=active,
            warn=c.imbalance_warn,
            critical=c.imbalance_critical,
            direction="above",
            min_duration_s=c.imbalance_min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=describe,
        )
    return findings

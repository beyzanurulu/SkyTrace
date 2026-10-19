"""Attitude tracking error: roll / pitch setpoint vs. estimated attitude."""

from __future__ import annotations

import numpy as np

from skytrace.config import DetectorsConfig
from skytrace.detectors.base import (
    Finding,
    FloatArray,
    Severity,
    active_mask,
    threshold_findings,
)
from skytrace.parsers.schema import FlightLog

NAME = "attitude"


def wrapped_error_deg(setpoint: FloatArray, actual: FloatArray) -> FloatArray:
    """|setpoint - actual| in degrees, wrapped to [0, 180]."""
    diff = (setpoint - actual + np.pi) % (2 * np.pi) - np.pi
    out: FloatArray = np.abs(np.degrees(diff))
    return out


def detect(log: FlightLog, cfg: DetectorsConfig, notes: list[str]) -> list[Finding]:
    att = log.attitude
    if att.empty:
        notes.append("attitude: no attitude data, detector skipped")
        return []
    if att[["roll_sp", "pitch_sp"]].isna().all().all():
        notes.append("attitude: no attitude setpoints, detector skipped")
        return []
    c = cfg.attitude
    t = att["t"].to_numpy(dtype=np.float64)
    active = active_mask(log, att, cfg.only_when_armed)
    findings: list[Finding] = []

    for axis in ("roll", "pitch"):
        err = wrapped_error_deg(
            att[f"{axis}_sp"].to_numpy(dtype=np.float64), att[axis].to_numpy(dtype=np.float64)
        )

        def describe(
            sev: Severity, v: float, thr: float, t0: float, t1: float, axis: str = axis
        ) -> str:
            return (
                f"{axis.capitalize()} not following setpoint: error up to {v:.1f}° "
                f"(threshold {thr:.1f}°) for {t1 - t0:.1f} s"
            )

        findings += threshold_findings(
            detector=NAME,
            metric=f"{axis}_error_deg",
            t=t,
            values=err,
            active=active,
            warn=c.error_warn_deg,
            critical=c.error_critical_deg,
            direction="above",
            min_duration_s=c.min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=describe,
        )
    return findings

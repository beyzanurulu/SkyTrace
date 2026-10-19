"""GPS problems: fix loss, low satellite count, high EPH / HDOP."""

from __future__ import annotations

import numpy as np

from skytrace.config import DetectorsConfig
from skytrace.detectors.base import (
    BoolArray,
    Describe,
    Direction,
    Finding,
    FloatArray,
    Severity,
    active_mask,
    intervals,
    threshold_findings,
)
from skytrace.parsers.schema import FlightLog

NAME = "gps"


def detect(log: FlightLog, cfg: DetectorsConfig, notes: list[str]) -> list[Finding]:
    gps = log.gps
    if gps.empty:
        notes.append("gps: no GPS data, detector skipped")
        return []
    c = cfg.gps
    t = gps["t"].to_numpy(dtype=np.float64)
    active = active_mask(log, gps, cfg.only_when_armed)

    fix = gps["fix_type"].to_numpy(dtype=np.float64)
    has_fix = fix >= c.min_fix_type  # NaN compares False

    findings = _fix_findings(t, fix, has_fix, active, cfg)

    def sats_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"Low satellite count: {v:.0f} (minimum {thr:.0f}) for {t1 - t0:.1f} s"

    def eph_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"High GPS horizontal error: EPH {v:.2f} m (limit {thr:.2f}) for {t1 - t0:.1f} s"

    def hdop_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"High HDOP: {v:.2f} (limit {thr:.2f}) for {t1 - t0:.1f} s"

    # Quality metrics are only meaningful with a fix; without one, receivers report
    # sentinels (e.g. EPH 4294967.5 m, HDOP 99.99) that the fix check already covers.
    checks: list[tuple[str, float, Direction, Describe]] = [
        ("satellites", c.min_satellites, "below", sats_text),
        ("eph", c.max_eph_m, "above", eph_text),
        ("hdop", c.max_hdop, "above", hdop_text),
    ]
    for metric, warn, direction, describe in checks:
        findings += threshold_findings(
            detector=NAME,
            metric=metric,
            t=t,
            values=gps[metric].to_numpy(dtype=np.float64),
            active=active & has_fix,
            warn=float(warn),
            critical=None,
            direction=direction,
            min_duration_s=c.min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=describe,
        )
    return findings


def _fix_findings(
    t: FloatArray, fix: FloatArray, has_fix: BoolArray, active: BoolArray, cfg: DetectorsConfig
) -> list[Finding]:
    """No 3D fix while armed: critical if a fix existed earlier (lost), else warn."""
    c = cfg.gps
    findings: list[Finding] = []
    bad = active & ~np.isnan(fix) & ~has_fix
    for i, j in intervals(t, bad, min_duration_s=c.min_duration_s, merge_gap_s=cfg.merge_gap_s):
        t0, t1 = float(t[i]), float(t[j])
        worst = float(np.nanmin(fix[i : j + 1]))
        lost = bool(has_fix[:i].any())
        severity: Severity = "critical" if lost else "warn"
        what = "GPS fix lost" if lost else "No 3D GPS fix yet (armed before fix)"
        findings.append(
            Finding(
                detector=NAME,
                severity=severity,
                t_start=t0,
                t_end=t1,
                metric="fix_type",
                value=worst,
                threshold=float(c.min_fix_type),
                summary=f"{what}: fix_type {worst:.0f} (< {c.min_fix_type}) for {t1 - t0:.1f} s",
            )
        )
    return findings

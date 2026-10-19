"""GPS problems: fix loss, low satellite count, high EPH / HDOP."""

from __future__ import annotations

import numpy as np

from skytrace.config import DetectorsConfig
from skytrace.detectors.base import (
    Describe,
    Direction,
    Finding,
    Severity,
    active_mask,
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

    def fix_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"GPS fix lost: fix_type {v:.0f} (< {thr:.0f}) for {t1 - t0:.1f} s"

    def sats_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"Low satellite count: {v:.0f} (minimum {thr:.0f}) for {t1 - t0:.1f} s"

    def eph_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"High GPS horizontal error: EPH {v:.2f} m (limit {thr:.2f}) for {t1 - t0:.1f} s"

    def hdop_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"High HDOP: {v:.2f} (limit {thr:.2f}) for {t1 - t0:.1f} s"

    checks: list[tuple[str, float, float | None, Direction, Describe]] = [
        # Losing the 3D fix is always critical: warn == critical threshold.
        ("fix_type", c.min_fix_type, c.min_fix_type, "below", fix_text),
        ("satellites", c.min_satellites, None, "below", sats_text),
        ("eph", c.max_eph_m, None, "above", eph_text),
        ("hdop", c.max_hdop, None, "above", hdop_text),
    ]
    findings: list[Finding] = []
    for metric, warn, critical, direction, describe in checks:
        findings += threshold_findings(
            detector=NAME,
            metric=metric,
            t=t,
            values=gps[metric].to_numpy(dtype=np.float64),
            active=active,
            warn=float(warn),
            critical=None if critical is None else float(critical),
            direction=direction,
            min_duration_s=c.min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=describe,
        )
    return findings

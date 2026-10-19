"""Rule-based detectors producing :class:`Finding` objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Final

from skytrace.config import DetectorsConfig, SkyTraceConfig, load_config
from skytrace.detectors import attitude, battery, gps, motors, vibration
from skytrace.detectors.base import SEVERITY_RANK, Finding, Severity
from skytrace.parsers.schema import FlightLog

DetectorFn = Callable[[FlightLog, DetectorsConfig, list[str]], list[Finding]]

DETECTORS: Final[dict[str, DetectorFn]] = {
    vibration.NAME: vibration.detect,
    gps.NAME: gps.detect,
    battery.NAME: battery.detect,
    attitude.NAME: attitude.detect,
    motors.NAME: motors.detect,
}


@dataclass(frozen=True)
class DetectionResult:
    findings: list[Finding]
    notes: list[str] = field(default_factory=list)
    """Checks that were skipped and why (missing data, unknown cell count, ...)."""

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]


def run_detectors(
    log: FlightLog,
    config: SkyTraceConfig | None = None,
    only: list[str] | None = None,
) -> DetectionResult:
    """Run all (or ``only`` the named) detectors; findings get ids F001, F002, ... by time."""
    cfg = (config if config is not None else load_config()).detectors
    names = list(DETECTORS) if only is None else only
    unknown = set(names) - set(DETECTORS)
    if unknown:
        raise KeyError(f"unknown detectors: {sorted(unknown)}")

    notes: list[str] = []
    findings: list[Finding] = []
    for name in names:
        findings += DETECTORS[name](log, cfg, notes)
    findings.sort(key=lambda f: (f.t_start, -SEVERITY_RANK[f.severity], f.detector, f.metric))
    numbered = [replace(f, id=f"F{i:03d}") for i, f in enumerate(findings, start=1)]
    return DetectionResult(findings=numbered, notes=notes)


__all__ = ["DETECTORS", "DetectionResult", "Finding", "run_detectors"]

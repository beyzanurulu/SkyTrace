"""Battery: low cell voltage, voltage sag under load, low remaining capacity."""

from __future__ import annotations

import numpy as np

from skytrace.config import DetectorsConfig
from skytrace.detectors.base import Finding, Severity, active_mask, rolling_time, threshold_findings
from skytrace.parsers.schema import FlightLog

NAME = "battery"


def detect(log: FlightLog, cfg: DetectorsConfig, notes: list[str]) -> list[Finding]:
    bat = log.battery
    if bat.empty:
        notes.append("battery: no battery data, detector skipped")
        return []
    c = cfg.battery
    t = bat["t"].to_numpy(dtype=np.float64)
    active = active_mask(log, bat, cfg.only_when_armed)
    findings: list[Finding] = []

    cells = c.cells if c.cells is not None else log.metadata.battery_cells
    if cells is None:
        notes.append(
            "battery: cell count unknown (set detectors.battery.cells), "
            "per-cell voltage and sag checks skipped"
        )
    else:
        voltage = bat["voltage"]
        per_cell = voltage.to_numpy(dtype=np.float64) / cells
        # Drop below the recent maximum: fast sag under load, not slow discharge.
        peak = rolling_time(voltage, bat["t"], c.sag_window_s, "max")
        sag = (peak - voltage.to_numpy(dtype=np.float64)) / cells

        def low_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
            return (
                f"Low battery voltage: {v:.2f} V/cell ({v * cells:.2f} V, {cells}S), "
                f"threshold {thr:.2f} V/cell, for {t1 - t0:.1f} s"
            )

        def sag_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
            return (
                f"Voltage sag under load: {v:.2f} V/cell drop within {c.sag_window_s:.1f} s "
                f"(threshold {thr:.2f} V/cell)"
            )

        findings += threshold_findings(
            detector=NAME,
            metric="cell_voltage",
            t=t,
            values=per_cell,
            active=active,
            warn=c.cell_voltage_warn,
            critical=c.cell_voltage_critical,
            direction="below",
            min_duration_s=c.min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=low_text,
        )
        findings += threshold_findings(
            detector=NAME,
            metric="voltage_sag_per_cell",
            t=t,
            values=sag,
            active=active,
            warn=c.sag_warn_v_per_cell,
            critical=c.sag_critical_v_per_cell,
            direction="above",
            min_duration_s=c.sag_min_duration_s,
            merge_gap_s=cfg.merge_gap_s,
            describe=sag_text,
        )

    def remaining_text(sev: Severity, v: float, thr: float, t0: float, t1: float) -> str:
        return f"Low remaining capacity: {v * 100:.0f}% (threshold {thr * 100:.0f}%)"

    findings += threshold_findings(
        detector=NAME,
        metric="remaining",
        t=t,
        values=bat["remaining"].to_numpy(dtype=np.float64),
        active=active,
        warn=c.remaining_warn,
        critical=c.remaining_critical,
        direction="below",
        min_duration_s=c.min_duration_s,
        merge_gap_s=cfg.merge_gap_s,
        describe=remaining_text,
    )
    return findings

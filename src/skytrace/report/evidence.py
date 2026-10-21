"""Evidence series for a Finding: exactly what the detector looked at.

Derived series (attitude error, battery sag, motor imbalance) are computed with
the detectors' own functions, so a plot can never disagree with the finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from skytrace.config import SkyTraceConfig
from skytrace.detectors.attitude import wrapped_error_deg
from skytrace.detectors.base import Finding, FloatArray
from skytrace.detectors.battery import resolve_cells, sag_per_cell
from skytrace.detectors.motors import imbalance_deviation
from skytrace.parsers.schema import FlightLog


@dataclass(frozen=True)
class Trace:
    name: str
    t: FloatArray
    y: FloatArray


@dataclass(frozen=True)
class Evidence:
    title: str
    y_label: str
    traces: tuple[Trace, ...]
    threshold: float | None
    threshold_label: str
    window: tuple[float, float]


_MOTOR_METRIC = re.compile(r"^m(\d+)_(saturated_s|imbalance)$")


def decimate(t: FloatArray, y: FloatArray, max_points: int) -> tuple[FloatArray, FloatArray]:
    """At most ``max_points`` samples, keeping each bucket's min and max (peaks survive)."""
    n = len(t)
    if n <= max_points:
        return t, y
    buckets = max(1, max_points // 2)
    keep: list[int] = []
    for chunk in np.array_split(np.arange(n), buckets):
        seg = y[chunk]
        if np.isnan(seg).all():
            keep.append(int(chunk[0]))
            continue
        keep.extend(sorted({int(chunk[np.nanargmin(seg)]), int(chunk[np.nanargmax(seg)])}))
    idx = np.asarray(keep, dtype=np.int64)
    return t[idx], y[idx]


def _window(finding: Finding, cfg: SkyTraceConfig) -> tuple[float, float]:
    pad = cfg.report.evidence_padding_s
    return finding.t_start - pad, finding.t_end + pad


def _trace(
    name: str, t: FloatArray, y: FloatArray, window: tuple[float, float], cfg: SkyTraceConfig
) -> Trace:
    mask = (t >= window[0]) & (t <= window[1])
    td, yd = decimate(t[mask], y[mask], cfg.report.max_points_per_trace)
    return Trace(name, td, yd)


def evidence_for(log: FlightLog, finding: Finding, cfg: SkyTraceConfig) -> Evidence | None:
    """Series, threshold and window for ``finding``; ``None`` if the metric is unknown."""
    win = _window(finding, cfg)
    det, metric = finding.detector, finding.metric

    def col(table: str, column: str) -> tuple[FloatArray, FloatArray]:
        df = log.table(table)
        return df["t"].to_numpy(dtype=np.float64), df[column].to_numpy(dtype=np.float64)

    def make(
        title: str, y_label: str, traces: list[Trace], threshold: float | None, label: str
    ) -> Evidence:
        return Evidence(title, y_label, tuple(traces), threshold, label, win)

    if det == "vibration" and metric == "accel_vib_metric":
        t, y = col("vibration", "accel_vib_metric")
        source = log.metadata.vib_metric_source or "unknown source"
        return make(
            "Accel vibration metric",
            f"accel vibration metric ({source})",
            [_trace("accel_vib_metric", t, y, win, cfg)],
            finding.threshold,
            f"{finding.severity} threshold",
        )
    if det == "vibration" and metric == "clip_count":
        t, y = col("vibration", "clip_count")
        # The threshold is a count per burst, not a level of this cumulative series.
        return make(
            "Accelerometer clipping (cumulative)",
            "clipped samples (cumulative)",
            [_trace("clip_count", t, y, win, cfg)],
            None,
            "",
        )
    if det == "gps" and metric == "data_gap_s":
        # Satellites over time: the shaded interval is where no sample exists at all.
        # The threshold is a gap length, not a level of this series, so no line.
        t, y = col("gps", "satellites")
        # Break the line inside gaps; otherwise the plot connects across them.
        cut = np.flatnonzero(np.diff(t) > cfg.detectors.gps.max_data_gap_s) + 1
        t = np.insert(t, cut, (t[cut - 1] + t[cut]) / 2)
        y = np.insert(y, cut, np.nan)
        return make(
            "GPS data gap",
            "satellites (no line = no GPS samples)",
            [_trace("satellites", t, y, win, cfg)],
            None,
            "",
        )
    if det == "gps" and metric in ("fix_type", "satellites", "eph", "hdop"):
        t, y = col("gps", metric)
        units = {
            "fix_type": "fix type",
            "satellites": "satellites",
            "eph": "EPH (m)",
            "hdop": "HDOP",
        }
        return make(
            f"GPS {metric}",
            units[metric],
            [_trace(metric, t, y, win, cfg)],
            finding.threshold,
            "limit",
        )
    if det == "battery":
        t, v = col("battery", "voltage")
        cells = resolve_cells(log, cfg.detectors)
        if metric == "cell_voltage" and cells:
            return make(
                "Cell voltage",
                "V per cell",
                [_trace("voltage / cell", t, v / cells, win, cfg)],
                finding.threshold,
                f"{finding.severity} threshold",
            )
        if metric == "voltage_sag_per_cell" and cells:
            sag = sag_per_cell(log, cells, cfg.detectors.battery.sag_window_s)
            return make(
                "Voltage sag under load",
                f"drop below {cfg.detectors.battery.sag_window_s:g} s max (V per cell)",
                [_trace("sag / cell", t, sag, win, cfg)],
                finding.threshold,
                f"{finding.severity} threshold",
            )
        if metric == "remaining":
            _, r = col("battery", "remaining")
            return make(
                "Remaining capacity",
                "remaining (%)",
                [_trace("remaining", t, r * 100, win, cfg)],
                finding.threshold * 100,
                f"{finding.severity} threshold",
            )
        return None
    if det == "attitude" and metric in ("roll_error_deg", "pitch_error_deg"):
        axis = metric.removesuffix("_error_deg")
        t, actual = col("attitude", axis)
        _, setpoint = col("attitude", f"{axis}_sp")
        err = wrapped_error_deg(setpoint, actual)
        return make(
            f"{axis.capitalize()} tracking error",
            "|setpoint - actual| (deg)",
            [_trace(f"{axis} error", t, err, win, cfg)],
            finding.threshold,
            f"{finding.severity} threshold",
        )
    match = _MOTOR_METRIC.match(metric) if det == "motors" else None
    if match:
        n, kind = int(match.group(1)), match.group(2)
        t = log.motors["t"].to_numpy(dtype=np.float64)
        if n > log.motor_count:
            return None
        if kind == "saturated_s":
            y = log.motors[f"m{n}"].to_numpy(dtype=np.float64)
            level = cfg.detectors.motors.saturation_level
            return make(
                f"Motor {n} output",
                "normalized output (0-1)",
                [_trace(f"m{n}", t, y, win, cfg)],
                level,
                "saturation level",
            )
        dev = np.abs(imbalance_deviation(log, cfg.detectors.motors.imbalance_window_s)[:, n - 1])
        return make(
            f"Motor {n} imbalance",
            f"|motor {n} - motor mean| ({cfg.detectors.motors.imbalance_window_s:g} s mean)",
            [_trace(f"m{n} deviation", t, dev, win, cfg)],
            finding.threshold,
            f"{finding.severity} threshold",
        )
    return None

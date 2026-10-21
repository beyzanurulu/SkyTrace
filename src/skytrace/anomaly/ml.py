"""Unsupervised anomaly detection for what the rule detectors do not cover.

Everything runs inside one log; no training data, no model files.

1. **Signals** are derived from the unified schema (attitude tracking error,
   vibration metric, battery, motor mean / spread, vertical speed, GPS EPH) and
   binned onto a common grid (``anomaly.resample_hz``) over armed, in-air periods
   (takeoff / landing events; armed periods if a log has none).
   Each armed period is split at flight-mode changes and analysed per mode.
2. **Rolling robust z-score** per signal (trailing window): ``(x - rolling
   median) / max(1.4826 * rolling MAD, noise floor)``. Sustained ``|z| > info``
   -> finding.
3. **Isolation Forest** per flight mode on sliding windows; per signal features
   level (window mean minus the median of neighbouring windows, so slow trends
   such as battery discharge are not anomalies), std, slope and high-frequency
   energy share. Anomalous windows -> findings that name the most deviating
   features.

Findings use ``detector = "ml_anomaly"`` and severity ``info`` (``warn`` for very
strong deviations). Every number in a summary comes from the data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from itertools import pairwise
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from skytrace.config import AnomalyConfig, SkyTraceConfig
from skytrace.detectors.attitude import wrapped_error_deg
from skytrace.detectors.base import (
    Finding,
    FloatArray,
    Severity,
    flight_intervals,
    intervals,
)
from skytrace.parsers.schema import FlightLog

NAME: Final = "ml_anomaly"
MAD_TO_SIGMA: Final = 1.4826  # MAD of a normal distribution -> standard deviation
MIN_FIX_TYPE_FOR_EPH: Final = 3  # EPH is a sentinel without a 3D fix

SIGNAL_LABELS: Final[dict[str, str]] = {
    "roll_error_deg": "roll tracking error (deg)",
    "pitch_error_deg": "pitch tracking error (deg)",
    "accel_vib_metric": "vibration metric",
    "battery_voltage": "battery voltage (V)",
    "battery_current": "battery current (A)",
    "motor_mean": "mean motor output",
    "motor_spread": "motor output spread (max - min)",
    "vz": "vertical speed (m/s)",
    "gps_eph": "GPS EPH (m)",
}
FEATURES: Final = ("level", "std", "slope", "hf_energy")

Series = tuple[FloatArray, FloatArray]  # (t, value)


# --- signals ------------------------------------------------------------------


def _cols(df: pd.DataFrame, *names: str) -> tuple[FloatArray, ...]:
    return tuple(df[n].to_numpy(dtype=np.float64) for n in names)


def _attitude_error(axis: str) -> Callable[[FlightLog], Series | None]:
    def get(log: FlightLog) -> Series | None:
        a = log.attitude
        if a.empty or a[f"{axis}_sp"].isna().all():
            return None
        t, sp, actual = _cols(a, "t", f"{axis}_sp", axis)
        return t, wrapped_error_deg(sp, actual)

    return get


def _column(table: str, column: str) -> Callable[[FlightLog], Series | None]:
    def get(log: FlightLog) -> Series | None:
        df = log.table(table)
        if df.empty or df[column].isna().all():
            return None
        t, v = _cols(df, "t", column)
        return t, v

    return get


def _motors(how: str) -> Callable[[FlightLog], Series | None]:
    def get(log: FlightLog) -> Series | None:
        if log.motor_count == 0 or log.motors.empty:
            return None
        m = log.motors.drop(columns="t").to_numpy(dtype=np.float64)
        t = log.motors["t"].to_numpy(dtype=np.float64)
        if how == "mean":
            return t, np.nanmean(m, axis=1)
        if log.motor_count < 2 or not log.metadata.motor_count_known:
            return None  # spread of servos + motors would be meaningless
        return t, np.nanmax(m, axis=1) - np.nanmin(m, axis=1)

    return get


def _gps_eph(log: FlightLog) -> Series | None:
    g = log.gps
    if g.empty:
        return None
    t, eph, fix = _cols(g, "t", "eph", "fix_type")
    return t, np.where(fix >= MIN_FIX_TYPE_FOR_EPH, eph, np.nan)


SIGNALS: Final[dict[str, Callable[[FlightLog], Series | None]]] = {
    "roll_error_deg": _attitude_error("roll"),
    "pitch_error_deg": _attitude_error("pitch"),
    "accel_vib_metric": _column("vibration", "accel_vib_metric"),
    "battery_voltage": _column("battery", "voltage"),
    "battery_current": _column("battery", "current"),
    "motor_mean": _motors("mean"),
    "motor_spread": _motors("spread"),
    "vz": _column("position", "vz"),
    "gps_eph": _gps_eph,
}


def enabled_signals(cfg: AnomalyConfig) -> dict[str, float]:
    """Signal name -> noise floor for every signal not disabled (``null``) in the config."""
    floors = {f.name: getattr(cfg.signals, f.name) for f in fields(cfg.signals)}
    return {name: floor for name, floor in floors.items() if floor is not None}


def signal_series(log: FlightLog, name: str) -> Series | None:
    """The raw (not resampled) series of one anomaly signal, or ``None`` if unavailable."""
    return SIGNALS[name](log)


# --- resampling -----------------------------------------------------------------


@dataclass(frozen=True)
class Grid:
    """Signals binned onto a common time grid for one armed, single-mode segment."""

    t: FloatArray
    values: dict[str, FloatArray]
    mode: str = "unknown"


def _bin(series: Series, t0: float, n: int, hz: float, max_fill: int) -> FloatArray:
    t, v = series
    idx = np.floor((t - t0) * hz).astype(np.int64)
    ok = (idx >= 0) & (idx < n) & np.isfinite(v)
    sums = np.bincount(idx[ok], weights=v[ok], minlength=n)[:n]
    counts = np.bincount(idx[ok], minlength=n)[:n]
    with np.errstate(invalid="ignore", divide="ignore"):
        binned: FloatArray = np.asarray(
            np.where(counts > 0, sums / np.maximum(counts, 1), np.nan), dtype=np.float64
        )
    if max_fill <= 0:
        return binned
    out: FloatArray = np.asarray(pd.Series(binned).ffill(limit=max_fill), dtype=np.float64)
    return out


def mode_segments(log: FlightLog, only_when_armed: bool) -> list[tuple[float, float, str]]:
    """In-air active periods split at flight-mode changes: ``(t_start, t_end, mode)``.

    In-air comes from takeoff / landing events (armed only if a log has none), so
    the time on the ground before a manual takeoff is never analysed.

    Analysing each mode on its own keeps normal phase changes (climb in takeoff,
    descent in land) from looking like anomalies against a hover-dominated log.
    """
    ev = log.events[log.events["kind"] == "mode"]
    times = ev["t"].to_numpy(dtype=np.float64)
    names = [str(m) for m in ev["message"]]
    out: list[tuple[float, float, str]] = []
    for start, end in flight_intervals(log, only_when_armed):
        cuts = [start, *[float(t) for t in times if start < t < end], end]
        for a, b in pairwise(cuts):
            k = int(np.searchsorted(times, a, side="right")) - 1
            out.append((a, b, names[k] if k >= 0 else "unknown"))
    return out


def make_grids(log: FlightLog, cfg: SkyTraceConfig) -> list[Grid]:
    a = cfg.anomaly
    raw = {name: s for name in enabled_signals(a) if (s := signal_series(log, name)) is not None}
    grids: list[Grid] = []
    max_fill = round(a.max_fill_s * a.resample_hz)
    for start, end, mode in mode_segments(log, cfg.detectors.only_when_armed):
        # Transients right after arming / a mode switch and before disarm are normal.
        t0, t1 = start + a.trim_s, end - a.trim_s
        n = int(np.floor((t1 - t0) * a.resample_hz)) + 1
        if n < 2:
            continue
        t = t0 + np.arange(n, dtype=np.float64) / a.resample_hz
        values = {name: _bin(s, t0, n, a.resample_hz, max_fill) for name, s in raw.items()}
        grids.append(Grid(t, values, mode))
    return grids


# --- rolling robust z-score ---------------------------------------------------


def robust_zscore(values: FloatArray, window: int, floor: float) -> FloatArray:
    """Trailing rolling ``(x - median) / max(1.4826 * MAD, floor)``; NaN stays NaN.

    Trailing (past samples only), so an onset is flagged when it happens, not
    a window earlier as a centred median would.
    """
    s = pd.Series(values)
    min_periods = max(3, window // 4)
    med = s.rolling(window, min_periods=min_periods).median()
    mad = (s - med).abs().rolling(window, min_periods=min_periods).median()
    scale = np.maximum(MAD_TO_SIGMA * mad.to_numpy(dtype=np.float64), floor)
    z: FloatArray = (s.to_numpy(dtype=np.float64) - med.to_numpy(dtype=np.float64)) / scale
    return z


def zscore_findings(grids: list[Grid], cfg: AnomalyConfig) -> list[Finding]:
    c = cfg.zscore
    floors = enabled_signals(cfg)
    window = max(3, round(c.window_s * cfg.resample_hz))
    out: list[Finding] = []
    for grid in grids:
        for name, values in grid.values.items():
            z = np.abs(robust_zscore(values, window, floors[name]))
            hot = np.isfinite(z) & (z > c.info)
            for i, j in intervals(grid.t, hot, min_duration_s=c.min_duration_s, merge_gap_s=0.0):
                peak = float(np.nanmax(z[i : j + 1]))
                k = i + int(np.nanargmax(z[i : j + 1]))
                severity: Severity = "warn" if peak > c.warn else "info"
                t0, t1 = float(grid.t[i]), float(grid.t[j])
                out.append(
                    Finding(
                        detector=NAME,
                        severity=severity,
                        t_start=t0,
                        t_end=t1,
                        metric=f"zscore:{name}",
                        value=peak,
                        threshold=c.warn if severity == "warn" else c.info,
                        summary=(
                            f"Unusual {SIGNAL_LABELS[name]} in {grid.mode}: {values[k]:.3g} at "
                            f"{grid.t[k]:.1f} s, robust z-score {peak:.1f} "
                            f"(threshold {c.info:g}) for {t1 - t0:.1f} s"
                        ),
                    )
                )
    return out


# --- Isolation Forest -----------------------------------------------------------


def window_features(
    values: FloatArray, hz: float, hf_cutoff_hz: float, noise_floor: float = 0.0
) -> FloatArray:
    """mean, std, slope (units/s) and high-frequency energy share of one window.

    The mean becomes the ``level`` feature after :func:`_relative_level`. When the
    detrended window varies less than the signal's noise floor its spectrum is
    just quantisation / noise, so the high-frequency share is 0 (not random).
    """
    v = values[np.isfinite(values)]
    if v.size < 3:
        return np.full(len(FEATURES), np.nan)
    t = np.arange(v.size) / hz
    slope = float(np.polyfit(t, v, 1)[0])
    detrended = v - np.polyval(np.polyfit(t, v, 1), t)
    hf = 0.0
    if float(detrended.std()) > noise_floor:
        power = np.abs(np.fft.rfft(detrended)) ** 2
        freqs = np.fft.rfftfreq(v.size, d=1.0 / hz)
        total = float(power[1:].sum())
        hf = float(power[freqs >= hf_cutoff_hz].sum()) / total if total > 0 else 0.0
    return np.array([float(v.mean()), float(v.std()), slope, hf])


@dataclass(frozen=True)
class WindowTable:
    t_start: FloatArray
    t_end: FloatArray
    names: list[str]  # "<signal>.<feature>"
    x: FloatArray  # (windows, features)


def build_windows(grids: list[Grid], cfg: AnomalyConfig) -> WindowTable:
    c = cfg.iforest
    size = max(3, round(c.window_s * cfg.resample_hz))
    step = max(1, round(c.step_s * cfg.resample_hz))
    signals = sorted({n for g in grids for n in g.values})
    floors = enabled_signals(cfg)
    names = [f"{s}.{f}" for s in signals for f in FEATURES]
    starts: list[float] = []
    ends: list[float] = []
    rows: list[FloatArray] = []
    grid_of_row: list[int] = []
    for g, grid in enumerate(grids):
        for i in range(0, len(grid.t) - size + 1, step):
            grid_of_row.append(g)
            row = [
                window_features(
                    grid.values[s][i : i + size], cfg.resample_hz, c.hf_cutoff_hz, floors[s]
                )
                if s in grid.values
                else np.full(len(FEATURES), np.nan)
                for s in signals
            ]
            rows.append(np.concatenate(row) if row else np.empty(0))
            starts.append(float(grid.t[i]))
            ends.append(float(grid.t[i + size - 1]))
    x = np.vstack(rows) if rows else np.empty((0, len(names)))
    if len(x):
        neighbours = max(3, round(c.baseline_s / c.step_s))
        x = _relative_level(x, np.asarray(grid_of_row), signals, neighbours)
    return WindowTable(np.asarray(starts), np.asarray(ends), names, x)


def _relative_level(
    x: FloatArray, grid_of_row: npt.NDArray[np.int64], signals: list[str], neighbours: int
) -> FloatArray:
    """Replace each window mean by (mean - centred rolling median of window means).

    Windows near a segment edge, without enough neighbours on both sides, get
    NaN (-> neutral after imputation): a one-sided baseline would make the first
    windows of a trending signal look anomalous.
    """
    out = x.copy()
    for k in range(len(signals)):
        col = k * len(FEATURES)  # "level" is the first feature of each signal
        for g in np.unique(grid_of_row):
            rows = grid_of_row == g
            means = pd.Series(x[rows, col])
            base = means.rolling(neighbours, center=True, min_periods=neighbours).median()
            out[rows, col] = (means - base).to_numpy(dtype=np.float64)
    return out


def _robust_columns(x: FloatArray) -> FloatArray:
    """Column-wise (x - median) / IQR, NaN -> 0 (median), for fitting and explanation."""
    med = np.nanmedian(x, axis=0)
    q75, q25 = np.nanpercentile(x, [75, 25], axis=0)
    # A near-zero IQR (e.g. a constant voltage) would turn noise into z ~ 1e4:
    # floor it at a tenth of the column's standard deviation, and 1 if constant.
    spread = np.maximum(q75 - q25, 0.1 * np.nanstd(x, axis=0))
    iqr = np.where(spread > 0, spread, 1.0)
    z: FloatArray = np.nan_to_num((x - med) / iqr, nan=0.0)
    return z


def iforest_findings(grids: list[Grid], cfg: AnomalyConfig, notes: list[str]) -> list[Finding]:
    """One Isolation Forest per flight mode: windows are only compared with the same mode."""
    out: list[Finding] = []
    skipped: list[str] = []
    for mode in sorted({g.mode for g in grids}):
        table = build_windows([g for g in grids if g.mode == mode], cfg)
        found = _iforest_mode(table, mode, cfg)
        if found is None:
            skipped.append(f"{mode} ({len(table.t_start)})")
        else:
            out += found
    if skipped:
        notes.append(
            f"{NAME}: Isolation Forest skipped for modes with < {cfg.iforest.min_windows} "
            f"windows: {', '.join(skipped)}"
        )
    return out


@dataclass(frozen=True)
class ModeScores:
    """Isolation Forest output for the windows of one flight mode."""

    names: list[str]  # usable feature names
    z: FloatArray  # robust feature z per window
    score: FloatArray  # anomaly score per window (~0.5 normal, -> 1 very anomalous)
    threshold: float  # the model's contamination threshold on score
    max_z: FloatArray  # largest |feature z| per window


def score_mode(table: WindowTable, cfg: AnomalyConfig) -> ModeScores | None:
    """Fit one forest on a mode's windows; ``None`` if there are too few windows."""
    from sklearn.ensemble import IsolationForest

    c = cfg.iforest
    usable = ~np.all(np.isnan(table.x), axis=0) if table.x.size else np.zeros(0, dtype=bool)
    if len(table.t_start) < c.min_windows or not usable.any():
        return None
    z = _robust_columns(table.x[:, usable])
    model = IsolationForest(
        n_estimators=c.n_estimators, contamination=c.contamination, random_state=c.random_state
    ).fit(z)
    return ModeScores(
        names=[n for n, ok in zip(table.names, usable, strict=True) if ok],
        z=z,
        score=-model.score_samples(z),
        threshold=float(-model.offset_),
        max_z=np.max(np.abs(z), axis=1),
    )


def _iforest_mode(table: WindowTable, mode: str, cfg: AnomalyConfig) -> list[Finding] | None:
    c = cfg.iforest
    scored = score_mode(table, cfg)
    if scored is None:
        return None
    names, z, score, threshold, max_z = (
        scored.names,
        scored.z,
        scored.score,
        scored.threshold,
        scored.max_z,
    )
    # contamination makes the model flag its most extreme windows in *every* log,
    # and the score itself is a poor gate (clustered anomalies mask each other).
    # So a flagged window also needs one clearly deviating feature.
    flagged = (score > threshold) & (max_z >= c.min_feature_z)

    out: list[Finding] = []
    mid = (table.t_start + table.t_end) / 2
    gap = c.step_s + 1e-9  # adjacent windows belong to one finding
    for i, j in intervals(mid, flagged, min_duration_s=0.0, merge_gap_s=gap):
        candidates = np.arange(i, j + 1)[flagged[i : j + 1]]
        peak_k = int(candidates[np.argmax(score[candidates])])
        peak = float(score[peak_k])
        top = np.argsort(-np.abs(z[peak_k]))[: c.top_features]
        reasons = ", ".join(f"{names[k]} (robust z {z[peak_k, k]:+.1f})" for k in top)
        strongest = float(np.max(max_z[candidates]))
        severity: Severity = "warn" if strongest >= c.warn_feature_z else "info"
        t0, t1 = float(table.t_start[i]), float(table.t_end[j])
        out.append(
            Finding(
                detector=NAME,
                severity=severity,
                t_start=t0,
                t_end=t1,
                metric=f"iforest:{names[top[0]].split('.')[0]}",
                value=peak,
                threshold=threshold,
                summary=(
                    f"Isolation Forest anomaly in {mode}: score {peak:.2f} "
                    f"(threshold {threshold:.2f}) over {t1 - t0:.1f} s; most unusual: {reasons}"
                ),
            )
        )
    return out


# --- per-log statistics for calibration ----------------------------------------


def zscore_log_statistic(grids: list[Grid], cfg: AnomalyConfig) -> float:
    """Highest robust |z| held for at least ``zscore.min_duration_s`` in this log.

    A z-score finding exists exactly when this exceeds ``zscore.info``, so its
    distribution over clean flights calibrates ``info`` / ``warn`` directly.
    """
    floors = enabled_signals(cfg)
    window = max(3, round(cfg.zscore.window_s * cfg.resample_hz))
    hold = max(1, round(cfg.zscore.min_duration_s * cfg.resample_hz) + 1)
    best = 0.0
    for grid in grids:
        for name, values in grid.values.items():
            z = pd.Series(np.abs(robust_zscore(values, window, floors[name])))
            sustained = z.rolling(hold, min_periods=hold).min().max()
            if np.isfinite(sustained):
                best = max(best, float(sustained))
    return best


def iforest_log_statistic(grids: list[Grid], cfg: AnomalyConfig) -> float:
    """Largest feature |z| among windows the forest flags (score > its threshold).

    A forest finding exists exactly when this reaches ``iforest.min_feature_z``.
    0 if no window is flagged or no mode has enough windows.
    """
    best = 0.0
    for mode in sorted({g.mode for g in grids}):
        scored = score_mode(build_windows([g for g in grids if g.mode == mode], cfg), cfg)
        if scored is None:
            continue
        flagged = scored.score > scored.threshold
        if flagged.any():
            best = max(best, float(np.max(scored.max_z[flagged])))
    return best


# --- entry point --------------------------------------------------------------


def detect(log: FlightLog, cfg: SkyTraceConfig, notes: list[str]) -> list[Finding]:
    grids = make_grids(log, cfg)
    if not grids or not any(g.values for g in grids):
        notes.append(f"{NAME}: no usable signals in active periods, skipped")
        return []
    findings = zscore_findings(grids, cfg.anomaly)
    if cfg.anomaly.iforest.enabled:
        findings += iforest_findings(grids, cfg.anomaly, notes)
    return findings


def merge_with_rules(ml: list[Finding], rules: list[Finding], notes: list[str]) -> list[Finding]:
    """Drop ML findings that overlap any rule finding in time; say so in ``notes``."""
    kept: list[Finding] = []
    merged = 0
    hit: dict[tuple[str, float, float], None] = {}  # ordered set of overlapped rule findings
    for f in ml:
        overlapping = [r for r in rules if f.t_start <= r.t_end and r.t_start <= f.t_end]
        if overlapping:
            merged += 1
            hit.update({(r.detector, r.t_start, r.t_end): None for r in overlapping})
        else:
            kept.append(f)
    if merged:
        where = ", ".join(f"{d} {a:.1f}-{b:.1f} s" for d, a, b in hit)
        notes.append(f"{NAME}: {merged} finding(s) overlapped rule findings ({where}), merged")
    return kept

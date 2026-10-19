"""Unified flight log schema shared by all parsers.

Every table is a ``pandas.DataFrame`` whose first column ``t`` is seconds since
the start of the log (float, non-decreasing). Missing data is represented by an
empty table (or NaN values), never by a missing column.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from skytrace.config import SkyTraceConfig

LogFormat = Literal["px4_ulog", "ardupilot_dataflash"]
VibMetricSource = Literal["px4_imu_status", "ardupilot_vibe"]
"""Where ``vibration.accel_vib_metric`` / ``clip_count`` come from. The scales differ
per source, so detectors pick thresholds by source and never mix them."""

TABLE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "attitude": ("t", "roll", "pitch", "yaw", "roll_sp", "pitch_sp", "yaw_sp"),
    "gps": ("t", "fix_type", "satellites", "eph", "hdop", "lat", "lon", "alt"),
    "battery": ("t", "voltage", "current", "remaining"),
    "vibration": (
        "t",
        "vib_x",
        "vib_y",
        "vib_z",
        "accel_vib_metric",
        "gyro_vib_metric",
        "clip_count",
    ),
    "position": ("t", "x", "y", "z", "vx", "vy", "vz", "z_sp"),
    "events": ("t", "kind", "message"),
}
"""Fixed column contracts. ``motors`` is variable-width: ``t, m1 ... mN``."""

TABLE_NAMES: Final[tuple[str, ...]] = (
    "attitude",
    "gps",
    "battery",
    "motors",
    "vibration",
    "position",
    "events",
)

EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {"mode", "arm", "disarm", "failsafe", "error", "warning", "info"}
)


def time_index(t: pd.Series) -> pd.TimedeltaIndex:
    """``t`` (float seconds) as a nanosecond TimedeltaIndex for time-based rolling windows.

    The resolution is pinned explicitly: pandas may otherwise infer second
    resolution for whole-number times and silently round sub-second windows.
    """
    ns = np.round(t.to_numpy(dtype=np.float64) * 1e9).astype(np.int64)
    return pd.TimedeltaIndex(ns.astype("timedelta64[ns]"))


class SchemaError(ValueError):
    """Raised when a table does not match the unified schema."""


def empty_table(name: str, motor_count: int = 0) -> pd.DataFrame:
    """Return an empty table with the correct columns for ``name``."""
    if name == "motors":
        cols = ["t", *[f"m{i}" for i in range(1, motor_count + 1)]]
    else:
        cols = list(TABLE_COLUMNS[name])
    return pd.DataFrame(
        {c: pd.Series(dtype="object" if c in ("kind", "message") else "float64") for c in cols}
    )


def validate_table(name: str, df: pd.DataFrame) -> None:
    """Check column contract and time column of one table."""
    cols = list(df.columns)
    if name == "motors":
        if not cols or cols[0] != "t":
            raise SchemaError("motors: first column must be 't'")
        expected = [f"m{i}" for i in range(1, len(cols))]
        if cols[1:] != expected:
            raise SchemaError(f"motors: columns must be t, m1..mN, got {cols}")
    else:
        expected_cols = list(TABLE_COLUMNS[name])
        if cols != expected_cols:
            raise SchemaError(f"{name}: expected columns {expected_cols}, got {cols}")

    if df.empty:
        return
    t = df["t"]
    if not pd.api.types.is_float_dtype(t):
        raise SchemaError(f"{name}: 't' must be float seconds, got {t.dtype}")
    if t.isna().any():
        raise SchemaError(f"{name}: 't' contains NaN")
    if not t.is_monotonic_increasing:
        raise SchemaError(f"{name}: 't' must be non-decreasing")
    if name == "events":
        unknown = set(df["kind"]) - EVENT_KINDS
        if unknown:
            raise SchemaError(f"events: unknown kinds {sorted(unknown)}")


@dataclass(frozen=True)
class LogMetadata:
    format: LogFormat
    source: str
    duration_s: float
    firmware: str | None = None
    hardware: str | None = None
    vehicle_type: str | None = None
    battery_cells: int | None = None
    motor_count_known: bool = True
    """False when the parser had to assume every output is a motor."""
    vib_metric_source: VibMetricSource | None = None


@dataclass
class FlightLog:
    """A parsed flight log in the unified schema."""

    metadata: LogMetadata
    attitude: pd.DataFrame
    gps: pd.DataFrame
    battery: pd.DataFrame
    motors: pd.DataFrame
    vibration: pd.DataFrame
    position: pd.DataFrame
    events: pd.DataFrame
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name in TABLE_NAMES:
            validate_table(name, self.table(name))

    def table(self, name: str) -> pd.DataFrame:
        if name not in TABLE_NAMES:
            raise KeyError(f"unknown table: {name}")
        df: pd.DataFrame = getattr(self, name)
        return df

    @property
    def motor_count(self) -> int:
        return len(self.motors.columns) - 1

    @classmethod
    def from_file(cls, path: str | Path, config: SkyTraceConfig | None = None) -> FlightLog:
        """Parse a log file, choosing the parser from the file extension."""
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix == ".ulg":
            from skytrace.parsers.ulog import parse_ulog

            return parse_ulog(p, config)
        if suffix == ".bin":
            from skytrace.parsers.dataflash import parse_dataflash

            return parse_dataflash(p, config)
        raise ValueError(f"unsupported log format: {p.suffix!r} (expected .ulg or .bin)")

"""PX4 ULog (.ulg) parser.

Maps PX4 uORB topics onto the unified schema. Topic and field names changed
across PX4 releases, so every table tries a list of candidate topics / fields
(see ``TOPIC_CANDIDATES``) and records a warning instead of failing when data
is missing.

Units: angles in radians, positions in metres (NED), voltage in V, current in A,
``remaining`` in 0..1, lat/lon in degrees, GPS altitude in metres MSL, motors
normalized to 0..1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import pandas as pd
from pyulog import ULog

from skytrace.config import MotorConfig, SkyTraceConfig, load_config
from skytrace.parsers.schema import FlightLog, LogMetadata, empty_table, time_index

TOPIC_CANDIDATES: Final[dict[str, tuple[str, ...]]] = {
    "attitude": ("vehicle_attitude",),
    "attitude_sp": ("vehicle_attitude_setpoint",),
    "gps": ("vehicle_gps_position", "sensor_gps"),
    "battery": ("battery_status",),
    "motors": ("actuator_motors", "actuator_outputs"),
    "accel": ("sensor_combined",),
    "imu_status": ("vehicle_imu_status",),
    "position": ("vehicle_local_position",),
    "position_sp": ("vehicle_local_position_setpoint",),
    "status": ("vehicle_status",),
}
"""Schema source -> PX4 topic names, in priority order."""

# PX4 vehicle_status.nav_state values (stable across releases; unknown -> NAV_STATE_<n>).
NAV_STATE_NAMES: Final[dict[int, str]] = {
    0: "MANUAL",
    1: "ALTCTL",
    2: "POSCTL",
    3: "AUTO_MISSION",
    4: "AUTO_LOITER",
    5: "AUTO_RTL",
    8: "AUTO_LANDENGFAIL",
    10: "ACRO",
    12: "DESCEND",
    13: "TERMINATION",
    14: "OFFBOARD",
    15: "STAB",
    16: "RATTITUDE",
    17: "AUTO_TAKEOFF",
    18: "AUTO_LAND",
    19: "AUTO_FOLLOW_TARGET",
    20: "AUTO_PRECLAND",
    21: "ORBIT",
    22: "AUTO_VTOL_TAKEOFF",
}

_ARMING_STATE_ARMED: Final = 2
_VEHICLE_TYPES: Final[dict[int, str]] = {
    1: "rotary_wing",
    2: "fixed_wing",
    3: "rover",
    4: "airship",
}
# ULog log levels: 0 EMERG .. 3 ERR, 4 WARNING, 5+ NOTICE/INFO/DEBUG.
_LEVEL_ERROR_MAX: Final = 3
_LEVEL_WARNING: Final = 4


class _ULogLike(Protocol):
    """The subset of ``pyulog.ULog`` used here (pyulog ships no type hints)."""

    start_timestamp: int
    last_timestamp: int
    data_list: list[Any]
    initial_parameters: dict[str, Any]
    logged_messages: list[Any]
    msg_info_dict: dict[str, Any]


class _Topics:
    """Lookup helper over a loaded ULog with times relative to log start."""

    def __init__(self, ulog: _ULogLike) -> None:
        self._ulog = ulog
        self._start = int(ulog.start_timestamp)
        self._data: dict[tuple[str, int], dict[str, np.ndarray]] = {
            (d.name, int(d.multi_id)): d.data for d in ulog.data_list
        }

    def rel_time(self, timestamps: np.ndarray) -> np.ndarray:
        return (timestamps.astype(np.int64) - self._start).astype(np.float64) / 1e6

    def instances(self, name: str) -> list[int]:
        return sorted(mid for (n, mid) in self._data if n == name)

    def get(self, source: str, multi_id: int | None = None) -> tuple[str, pd.DataFrame] | None:
        """First available candidate topic for ``source`` as a DataFrame with ``t``."""
        for name in TOPIC_CANDIDATES[source]:
            ids = self.instances(name)
            if not ids:
                continue
            mid = multi_id if multi_id is not None and multi_id in ids else ids[0]
            raw = self._data[(name, mid)]
            df = pd.DataFrame({k: v for k, v in raw.items() if k != "timestamp"})
            df.insert(0, "t", self.rel_time(raw["timestamp"]))
            return name, df.sort_values("t", kind="stable").reset_index(drop=True)
        return None

    def param(self, key: str) -> float | None:
        value = self._ulog.initial_parameters.get(key)
        return None if value is None else float(value)


def _col(df: pd.DataFrame, *names: str, scale: float = 1.0) -> pd.Series:
    """First existing column among ``names`` as float, else all-NaN."""
    for n in names:
        if n in df.columns:
            return df[n].astype("float64") * scale
    return pd.Series(np.nan, index=df.index, dtype="float64")


def _quat_to_euler(df: pd.DataFrame, prefix: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    w, x, y, z = (df[f"{prefix}[{i}]"].to_numpy(dtype=np.float64) for i in range(4))
    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1.0, 1.0))
    yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def _has_quat(df: pd.DataFrame, prefix: str) -> bool:
    return all(f"{prefix}[{i}]" in df.columns for i in range(4))


def _asof(left: pd.DataFrame, right: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """Attach the latest ``right`` row at or before each ``left`` time within ``tolerance``."""
    # pandas accepts a float tolerance for a float key; pandas-stubs only allow int/timedelta.
    return pd.merge_asof(
        left,
        right,
        on="t",
        direction="backward",
        tolerance=tolerance,  # type: ignore[arg-type]
    )


def _attitude(topics: _Topics, cfg: SkyTraceConfig, warnings: list[str]) -> pd.DataFrame:
    found = topics.get("attitude")
    if found is None:
        warnings.append("attitude: no vehicle_attitude topic")
        return empty_table("attitude")
    _, att = found
    roll, pitch, yaw = _quat_to_euler(att, "q")
    out = pd.DataFrame({"t": att["t"], "roll": roll, "pitch": pitch, "yaw": yaw})

    sp_found = topics.get("attitude_sp")
    if sp_found is None:
        warnings.append("attitude: no vehicle_attitude_setpoint topic, setpoints are NaN")
        for c in ("roll_sp", "pitch_sp", "yaw_sp"):
            out[c] = np.nan
        return out

    _, sp = sp_found
    if _has_quat(sp, "q_d"):
        r_sp, p_sp, y_sp = _quat_to_euler(sp, "q_d")
    else:
        r_sp = _col(sp, "roll_body").to_numpy()
        p_sp = _col(sp, "pitch_body").to_numpy()
        y_sp = _col(sp, "yaw_body").to_numpy()
    sp_df = pd.DataFrame({"t": sp["t"], "roll_sp": r_sp, "pitch_sp": p_sp, "yaw_sp": y_sp})
    return _asof(out, sp_df, cfg.parser.merge_tolerance_s)


def _gps(topics: _Topics, warnings: list[str]) -> pd.DataFrame:
    found = topics.get("gps")
    if found is None:
        warnings.append("gps: no vehicle_gps_position / sensor_gps topic")
        return empty_table("gps")
    _, g = found
    # PX4 >= 1.14 uses float degrees / metres; older releases use int 1e-7 deg / mm.
    if "latitude_deg" in g.columns:
        lat, lon = _col(g, "latitude_deg"), _col(g, "longitude_deg")
        alt = _col(g, "altitude_msl_m")
    else:
        lat, lon = _col(g, "lat", scale=1e-7), _col(g, "lon", scale=1e-7)
        alt = _col(g, "alt", scale=1e-3)
    return pd.DataFrame(
        {
            "t": g["t"],
            "fix_type": _col(g, "fix_type"),
            "satellites": _col(g, "satellites_used"),
            "eph": _col(g, "eph"),
            "hdop": _col(g, "hdop"),
            "lat": lat,
            "lon": lon,
            "alt": alt,
        }
    )


def _battery_frame(topics: _Topics) -> pd.DataFrame | None:
    """The first battery_status instance reporting a connected battery, else instance 0."""
    frames = [
        f[1]
        for mid in topics.instances("battery_status")
        if (f := topics.get("battery", mid)) is not None
    ]
    if not frames:
        return None
    connected = [f for f in frames if "connected" in f and f["connected"].astype(bool).any()]
    return connected[0] if connected else frames[0]


def _battery_cells(topics: _Topics) -> int | None:
    """Cell count from battery_status.cell_count, else the BAT1_N_CELLS / BAT_N_CELLS param."""
    b = _battery_frame(topics)
    if b is not None and "cell_count" in b:
        counts = b["cell_count"][b["cell_count"] > 0]
        if len(counts):
            return int(counts.mode().iloc[0])
    for key in ("BAT1_N_CELLS", "BAT_N_CELLS"):
        v = topics.param(key)
        if v is not None and v > 0:
            return int(v)
    return None


def _battery(topics: _Topics, warnings: list[str]) -> pd.DataFrame:
    b = _battery_frame(topics)
    if b is None:
        warnings.append("battery: no battery_status topic")
        return empty_table("battery")
    remaining = _col(b, "remaining")
    remaining = remaining.where(remaining >= 0)  # PX4 uses -1 for "unknown"
    return pd.DataFrame(
        {
            "t": b["t"],
            "voltage": _col(b, "voltage_v", "voltage_filtered_v"),
            "current": _col(b, "current_a", "current_filtered_a"),
            "remaining": remaining,
        }
    )


def _indexed_columns(df: pd.DataFrame, prefix: str) -> list[str]:
    cols = []
    i = 0
    while f"{prefix}[{i}]" in df.columns:
        cols.append(f"{prefix}[{i}]")
        i += 1
    return cols


def _motor_count(topics: _Topics, mcfg: MotorConfig, available: int) -> int:
    if mcfg.count is not None:
        return min(mcfg.count, available)
    rotors = topics.param("CA_ROTOR_COUNT")
    if rotors is not None and rotors > 0:
        return min(int(rotors), available)
    return available


def _motor_count_known(topics: _Topics, mcfg: MotorConfig) -> bool:
    """False when actuator_outputs is the source and nothing says how many are motors."""
    found = topics.get("motors", 0)
    if found is None or found[0] == "actuator_motors" or mcfg.count is not None:
        return True
    rotors = topics.param("CA_ROTOR_COUNT")
    return rotors is not None and rotors > 0


def _pwm_range(topics: _Topics, mcfg: MotorConfig, channel: int) -> tuple[float, float]:
    """PWM (min, max) for 1-based ``channel``: per-channel param, global param, config."""
    lo, hi = mcfg.pwm_min_us, mcfg.pwm_max_us
    if mcfg.use_log_params:
        for key in (f"PWM_MAIN_MIN{channel}", "PWM_MIN"):
            v = topics.param(key)
            if v is not None and v > 0:
                lo = v
                break
        for key in (f"PWM_MAIN_MAX{channel}", "PWM_MAX"):
            v = topics.param(key)
            if v is not None and v > 0:
                hi = v
                break
    return lo, hi


def _motors(topics: _Topics, cfg: SkyTraceConfig, warnings: list[str]) -> pd.DataFrame:
    mcfg = cfg.parser.motors
    found = topics.get("motors", 0)
    if found is None:
        warnings.append("motors: no actuator_motors / actuator_outputs topic")
        return empty_table("motors")
    name, m = found
    out = pd.DataFrame({"t": m["t"]})

    if name == "actuator_motors":
        # Already normalized; unused channels are NaN for the whole log.
        cols = [c for c in _indexed_columns(m, "control") if m[c].notna().any()]
        n = _motor_count(topics, mcfg, len(cols))
        for i, c in enumerate(cols[:n], start=1):
            out[f"m{i}"] = m[c].astype("float64").clip(0.0, 1.0)
        return out

    cols = _indexed_columns(m, "output")
    available = len(cols)
    if "noutputs" in m.columns and len(m):
        available = min(available, int(m["noutputs"].max()))
    n = _motor_count(topics, mcfg, available)
    if not _motor_count_known(topics, mcfg):
        warnings.append(
            f"motors: motor count unknown, using all {n} outputs (set parser.motors.count)"
        )
    for i, c in enumerate(cols[:n], start=1):
        lo, hi = _pwm_range(topics, mcfg, i)
        out[f"m{i}"] = ((m[c].astype("float64") - lo) / (hi - lo)).clip(0.0, 1.0)
    return out


def _vibration(topics: _Topics, cfg: SkyTraceConfig, warnings: list[str]) -> pd.DataFrame:
    found = topics.get("accel")
    if found is None:
        warnings.append("vibration: no sensor_combined topic")
        return empty_table("vibration")
    _, acc = found
    window = pd.Timedelta(seconds=cfg.parser.vibration_window_s)
    idx = time_index(acc["t"])
    out = pd.DataFrame({"t": acc["t"]})
    for axis, i in (("vib_x", 0), ("vib_y", 1), ("vib_z", 2)):
        series = pd.Series(_col(acc, f"accelerometer_m_s2[{i}]").to_numpy(), index=idx)
        out[axis] = series.rolling(window, min_periods=2).std().to_numpy()

    imu = topics.get("imu_status", 0)
    if imu is None or not _indexed_columns(imu[1], "accel_clipping"):
        warnings.append("vibration: no vehicle_imu_status clipping counters, clip_count is NaN")
        out["clip_count"] = np.nan
        return out
    _, st = imu
    clip_cols = _indexed_columns(st, "accel_clipping")
    clips = pd.DataFrame({"t": st["t"], "clip_count": st[clip_cols].astype("float64").sum(axis=1)})
    # Cumulative counter: the last value stays valid until the next update, so no tolerance.
    return pd.merge_asof(out, clips, on="t", direction="backward")


def _position(topics: _Topics, cfg: SkyTraceConfig, warnings: list[str]) -> pd.DataFrame:
    found = topics.get("position")
    if found is None:
        warnings.append("position: no vehicle_local_position topic")
        return empty_table("position")
    _, p = found
    out = pd.DataFrame({"t": p["t"]})
    for c in ("x", "y", "z", "vx", "vy", "vz"):
        out[c] = _col(p, c)
    sp = topics.get("position_sp")
    if sp is None:
        warnings.append("position: no vehicle_local_position_setpoint topic, z_sp is NaN")
        out["z_sp"] = np.nan
        return out
    sp_df = pd.DataFrame({"t": sp[1]["t"], "z_sp": _col(sp[1], "z")})
    return _asof(out, sp_df, cfg.parser.merge_tolerance_s)


def _events(topics: _Topics, ulog: _ULogLike, warnings: list[str]) -> pd.DataFrame:
    rows: list[tuple[float, str, str]] = []

    found = topics.get("status")
    if found is None:
        warnings.append("events: no vehicle_status topic, no mode/arm/failsafe events")
    else:
        _, st = found
        prev_mode: int | None = None
        prev_armed = False
        prev_failsafe = False
        times = st["t"].to_numpy(dtype=np.float64).tolist()
        modes = st["nav_state"].to_numpy(dtype=np.int64).tolist()
        arming = st["arming_state"].to_numpy(dtype=np.int64).tolist()
        failsafes: list[bool] | None = None
        if "failsafe" in st.columns:
            failsafes = st["failsafe"].to_numpy(dtype=bool).tolist()
        for i, t in enumerate(times):
            mode = modes[i]
            if mode != prev_mode:
                rows.append((t, "mode", NAV_STATE_NAMES.get(mode, f"NAV_STATE_{mode}")))
                prev_mode = mode
            armed = arming[i] == _ARMING_STATE_ARMED
            if armed != prev_armed:
                rows.append((t, "arm" if armed else "disarm", "armed" if armed else "disarmed"))
                prev_armed = armed
            if failsafes is not None:
                fs = failsafes[i]
                if fs != prev_failsafe:
                    rows.append((t, "failsafe", "failsafe activated" if fs else "failsafe cleared"))
                    prev_failsafe = fs

    messages = list(ulog.logged_messages)
    for tagged in getattr(ulog, "logged_messages_tagged", {}).values():
        messages.extend(tagged)
    for msg in messages:
        level = int(msg.log_level)
        if level <= _LEVEL_ERROR_MAX:
            kind = "error"
        elif level == _LEVEL_WARNING:
            kind = "warning"
        else:
            kind = "info"
        t = float(topics.rel_time(np.array([msg.timestamp]))[0])
        rows.append((t, kind, str(msg.message).strip()))

    if not rows:
        return empty_table("events")
    df = pd.DataFrame(rows, columns=["t", "kind", "message"])
    return df.sort_values("t", kind="stable").reset_index(drop=True)


def _metadata(path: Path, ulog: _ULogLike, topics: _Topics, cfg: SkyTraceConfig) -> LogMetadata:
    info: dict[str, Any] = ulog.msg_info_dict
    vehicle_type: str | None = None
    status = topics.get("status")
    if status is not None and len(status[1]):
        first = status[1].iloc[0]
        if "is_vtol" in first and bool(first["is_vtol"]):
            vehicle_type = "vtol"
        elif "vehicle_type" in first:
            vehicle_type = _VEHICLE_TYPES.get(int(first["vehicle_type"]))
    duration = (int(ulog.last_timestamp) - int(ulog.start_timestamp)) / 1e6
    fw = info.get("ver_sw")
    hw = info.get("ver_hw")
    return LogMetadata(
        format="px4_ulog",
        source=str(path),
        duration_s=duration,
        firmware=None if fw is None else str(fw),
        hardware=None if hw is None else str(hw),
        vehicle_type=vehicle_type,
        battery_cells=_battery_cells(topics),
        motor_count_known=_motor_count_known(topics, cfg.parser.motors),
    )


def parse_ulog(path: str | Path, config: SkyTraceConfig | None = None) -> FlightLog:
    """Parse a PX4 ``.ulg`` file into a :class:`FlightLog`."""
    cfg = config if config is not None else load_config()
    p = Path(path)
    wanted = sorted({name for names in TOPIC_CANDIDATES.values() for name in names})
    ulog = ULog(str(p), wanted)
    topics = _Topics(ulog)
    warnings: list[str] = []

    return FlightLog(
        metadata=_metadata(p, ulog, topics, cfg),
        attitude=_attitude(topics, cfg, warnings),
        gps=_gps(topics, warnings),
        battery=_battery(topics, warnings),
        motors=_motors(topics, cfg, warnings),
        vibration=_vibration(topics, cfg, warnings),
        position=_position(topics, cfg, warnings),
        events=_events(topics, ulog, warnings),
        warnings=warnings,
    )

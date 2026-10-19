"""ArduPilot DataFlash (.bin) parser.

Maps ArduPilot log messages onto the unified schema, read with pymavlink's
``DFReader``. Message and field names differ between ArduPilot releases (VIBE
per IMU instance vs. Clip0/1/2, BAT vs. CURR, ARM vs. EV), so each table looks
for the known variants and records a warning instead of failing when data is
missing.

Units follow the PX4 parser: angles in radians, positions in metres (NED, so
altitude is ``-z``), ``remaining`` in 0..1, motors normalized to 0..1.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
from pymavlink import mavutil

from skytrace.config import MotorConfig, SkyTraceConfig, load_config
from skytrace.parsers.schema import FlightLog, LogMetadata, VibMetricSource, empty_table

WANTED: Final[tuple[str, ...]] = (
    "PARM",
    "ATT",
    "GPS",
    "GPA",
    "BAT",
    "CURR",
    "RCOU",
    "VIBE",
    "CTUN",
    "MODE",
    "ARM",
    "EV",
    "ERR",
    "MSG",
)

# EV ids for arming (AP_Logger LogEvent).
_EV_ARMED: Final = 10
_EV_DISARMED: Final = 11

# ERR Subsys ids (Copter LogErrorSubsystem). Names starting with FAILSAFE_ become failsafe events.
ERR_SUBSYSTEMS: Final[dict[int, str]] = {
    1: "MAIN",
    2: "RADIO",
    3: "COMPASS",
    4: "OPTFLOW",
    5: "FAILSAFE_RADIO",
    6: "FAILSAFE_BATT",
    7: "FAILSAFE_GPS",
    8: "FAILSAFE_GCS",
    9: "FAILSAFE_FENCE",
    10: "FLIGHT_MODE",
    11: "GPS",
    12: "CRASH_CHECK",
    13: "FLIP",
    14: "AUTOTUNE",
    15: "PARACHUTES",
    16: "EKFCHECK",
    17: "FAILSAFE_EKFINAV",
    18: "BARO",
    19: "CPU",
    20: "FAILSAFE_ADSB",
    21: "TERRAIN",
    22: "NAVIGATION",
    23: "FAILSAFE_TERRAIN",
    24: "EKF_PRIMARY",
    25: "THRUST_LOSS_CHECK",
    26: "FAILSAFE_SENSORS",
    27: "FAILSAFE_LEAK",
    28: "PILOT_INPUT",
    29: "FAILSAFE_VIBE",
}

# FRAME_CLASS -> motor count (multicopter frames only).
FRAME_CLASS_MOTORS: Final[dict[int, int]] = {
    1: 4,  # quad
    2: 6,  # hexa
    3: 8,  # octa
    4: 8,  # octaquad
    5: 6,  # Y6
    7: 3,  # tri
    10: 1,  # single
    11: 2,  # coax
    12: 12,  # dodecahexa
    14: 10,  # deca
}

_FIRMWARE_RE: Final = re.compile(r"^(ArduCopter|ArduPlane|ArduRover|Rover|ArduSub|Blimp)\s+V\S+")
_VEHICLE_TYPES: Final[dict[str, str]] = {
    "ArduCopter": "rotary_wing",
    "ArduPlane": "fixed_wing",
    "ArduRover": "rover",
    "Rover": "rover",
    "ArduSub": "submarine",
    "Blimp": "airship",
}
_MODE_NAMES: Final[dict[str, dict[int, str]]] = {
    "rotary_wing": mavutil.mode_mapping_acm,
    "fixed_wing": mavutil.mode_mapping_apm,
    "rover": mavutil.mode_mapping_rover,
}


class _Messages:
    """All wanted messages of a log as DataFrames, with ``t`` relative to the first sample."""

    def __init__(self, path: Path) -> None:
        reader = mavutil.mavlink_connection(str(path))
        rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        while (msg := reader.recv_match(type=list(WANTED))) is not None:
            d = msg.to_dict()
            if "TimeUS" in d:
                rows[d.pop("mavpackettype")].append(d)
        starts = [r[0]["TimeUS"] for r in rows.values() if r]
        ends = [r[-1]["TimeUS"] for r in rows.values() if r]
        self._t0 = min(starts) if starts else 0
        self.duration_s = (max(ends) - self._t0) / 1e6 if ends else 0.0
        self._frames: dict[str, pd.DataFrame] = {}
        for name, r in rows.items():
            df = pd.DataFrame(r)
            df.insert(0, "t", (df.pop("TimeUS").astype(np.int64) - self._t0) / 1e6)
            self._frames[name] = df.sort_values("t", kind="stable").reset_index(drop=True)
        parm = self._frames.get("PARM")
        # First value of each parameter, like PX4 initial_parameters.
        self.params: dict[str, float] = (
            {}
            if parm is None
            else {str(k): float(v) for k, v in parm.groupby("Name")["Value"].first().items()}
        )

    def get(self, name: str) -> pd.DataFrame | None:
        df = self._frames.get(name)
        return None if df is None or df.empty else df

    def param(self, key: str) -> float | None:
        return self.params.get(key)


def _col(df: pd.DataFrame, *names: str, scale: float = 1.0) -> pd.Series:
    """First existing column among ``names`` as float, else all-NaN."""
    for n in names:
        if n in df.columns:
            return df[n].astype("float64") * scale
    return pd.Series(np.nan, index=df.index, dtype="float64")


def _instance(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Rows of the lowest instance when ``column`` (I / Inst / IMU) is present."""
    if column not in df.columns:
        return df
    first: pd.DataFrame = df[df[column] == df[column].min()]
    return first.reset_index(drop=True)


def _attitude(msgs: _Messages, warnings: list[str]) -> pd.DataFrame:
    att = msgs.get("ATT")
    if att is None:
        warnings.append("attitude: no ATT messages")
        return empty_table("attitude")
    return pd.DataFrame(
        {
            "t": att["t"],
            "roll": np.radians(_col(att, "Roll")),
            "pitch": np.radians(_col(att, "Pitch")),
            "yaw": np.radians(_col(att, "Yaw")),
            "roll_sp": np.radians(_col(att, "DesRoll")),
            "pitch_sp": np.radians(_col(att, "DesPitch")),
            "yaw_sp": np.radians(_col(att, "DesYaw")),
        }
    )


def _gps(msgs: _Messages, cfg: SkyTraceConfig, warnings: list[str]) -> pd.DataFrame:
    g = msgs.get("GPS")
    if g is None:
        warnings.append("gps: no GPS messages")
        return empty_table("gps")
    g = _instance(g, "I")
    out = pd.DataFrame(
        {
            "t": g["t"],
            # ArduPilot GPS Status uses the same 0..6 scale as PX4 fix_type (3 = 3D fix).
            "fix_type": _col(g, "Status"),
            "satellites": _col(g, "NSats"),
            "hdop": _col(g, "HDop"),
            "lat": _col(g, "Lat"),
            "lon": _col(g, "Lng"),
            "alt": _col(g, "Alt"),
        }
    )
    gpa = msgs.get("GPA")
    if gpa is None:
        warnings.append("gps: no GPA messages, eph is NaN")
        out["eph"] = np.nan
    else:
        gpa = _instance(gpa, "I")
        eph = pd.DataFrame({"t": gpa["t"], "eph": _col(gpa, "HAcc")})
        out = pd.merge_asof(
            out,
            eph,
            on="t",
            direction="backward",
            tolerance=cfg.parser.merge_tolerance_s,  # type: ignore[arg-type]
        )
    return out[["t", "fix_type", "satellites", "eph", "hdop", "lat", "lon", "alt"]]


def _battery(msgs: _Messages, warnings: list[str]) -> pd.DataFrame:
    b = msgs.get("BAT")
    if b is None:
        b = msgs.get("CURR")
    if b is None:
        warnings.append("battery: no BAT / CURR messages")
        return empty_table("battery")
    b = _instance(b, "Inst")
    remaining = _col(b, "RemPct", scale=0.01)
    return pd.DataFrame(
        {
            "t": b["t"],
            "voltage": _col(b, "Volt"),
            "current": _col(b, "Curr"),
            "remaining": remaining.where(remaining >= 0),
        }
    )


def _motor_count(msgs: _Messages, mcfg: MotorConfig, available: int) -> int:
    if mcfg.count is not None:
        return min(mcfg.count, available)
    frame = msgs.param("FRAME_CLASS")
    if frame is not None and int(frame) in FRAME_CLASS_MOTORS:
        return min(FRAME_CLASS_MOTORS[int(frame)], available)
    return available


def _motor_count_known(msgs: _Messages, mcfg: MotorConfig) -> bool:
    frame = msgs.param("FRAME_CLASS")
    return mcfg.count is not None or (frame is not None and int(frame) in FRAME_CLASS_MOTORS)


def _pwm_range(msgs: _Messages, mcfg: MotorConfig) -> tuple[float, float]:
    """MOT_PWM_MIN/MAX; 0 means ArduPilot uses the throttle channel (RC3) range; else config."""
    lo, hi = mcfg.pwm_min_us, mcfg.pwm_max_us
    if mcfg.use_log_params:
        for key in ("MOT_PWM_MIN", "RC3_MIN"):
            v = msgs.param(key)
            if v is not None and v > 0:
                lo = v
                break
        for key in ("MOT_PWM_MAX", "RC3_MAX"):
            v = msgs.param(key)
            if v is not None and v > 0:
                hi = v
                break
    return lo, hi


def _motors(msgs: _Messages, cfg: SkyTraceConfig, warnings: list[str]) -> pd.DataFrame:
    mcfg = cfg.parser.motors
    m = msgs.get("RCOU")
    if m is None:
        warnings.append("motors: no RCOU messages")
        return empty_table("motors")
    cols: list[str] = []
    while f"C{len(cols) + 1}" in m.columns:
        cols.append(f"C{len(cols) + 1}")
    n = _motor_count(msgs, mcfg, len(cols))
    if not _motor_count_known(msgs, mcfg):
        warnings.append(
            f"motors: motor count unknown, using all {n} outputs (set parser.motors.count)"
        )
    lo, hi = _pwm_range(msgs, mcfg)
    out = pd.DataFrame({"t": m["t"]})
    for i, c in enumerate(cols[:n], start=1):
        out[f"m{i}"] = ((m[c].astype("float64") - lo) / (hi - lo)).clip(0.0, 1.0)
    return out


def _vibration(msgs: _Messages, warnings: list[str]) -> pd.DataFrame:
    v = msgs.get("VIBE")
    if v is None:
        warnings.append("vibration: no VIBE messages")
        return empty_table("vibration")

    if "IMU" not in v.columns:
        # Older releases: one row for all IMUs, cumulative Clip0/1/2 per IMU.
        clips = [c for c in ("Clip0", "Clip1", "Clip2") if c in v.columns]
        out = pd.DataFrame(
            {
                "t": v["t"],
                "vib_x": _col(v, "VibeX"),
                "vib_y": _col(v, "VibeY"),
                "vib_z": _col(v, "VibeZ"),
            }
        )
        out["clip_count"] = v[clips].astype("float64").max(axis=1) if clips else np.nan
    else:
        # Newer releases: one row per IMU instance. Align instances on the union of
        # times (last value of each IMU) and keep the worst IMU at each step.
        times = pd.DataFrame({"t": np.unique(v["t"].to_numpy(dtype=np.float64))})
        per_axis: dict[str, list[str]] = defaultdict(list)
        for k, imu in v.groupby("IMU"):
            part = pd.DataFrame(
                {
                    "t": imu["t"],
                    f"_x{k}": _col(imu, "VibeX"),
                    f"_y{k}": _col(imu, "VibeY"),
                    f"_z{k}": _col(imu, "VibeZ"),
                    f"_c{k}": _col(imu, "Clip"),
                }
            ).reset_index(drop=True)
            times = pd.merge_asof(times, part, on="t", direction="backward")
            for axis in ("x", "y", "z", "c"):
                per_axis[axis].append(f"_{axis}{k}")
        out = pd.DataFrame({"t": times["t"]})
        for axis in ("x", "y", "z"):
            out[f"vib_{axis}"] = times[per_axis[axis]].max(axis=1)
        out["clip_count"] = times[per_axis["c"]].max(axis=1)

    out["accel_vib_metric"] = out[["vib_x", "vib_y", "vib_z"]].max(axis=1)
    out["gyro_vib_metric"] = np.nan
    return out[
        ["t", "vib_x", "vib_y", "vib_z", "accel_vib_metric", "gyro_vib_metric", "clip_count"]
    ]


def _position(msgs: _Messages, warnings: list[str]) -> pd.DataFrame:
    c = msgs.get("CTUN")
    if c is None:
        warnings.append("position: no CTUN messages")
        return empty_table("position")
    warnings.append("position: CTUN has altitude only, x/y/vx/vy are NaN")
    nan = pd.Series(np.nan, index=c.index, dtype="float64")
    # CTUN altitudes are up-positive; the schema is NED (z down). CRt is cm/s.
    return pd.DataFrame(
        {
            "t": c["t"],
            "x": nan,
            "y": nan,
            "z": -_col(c, "Alt"),
            "vx": nan,
            "vy": nan,
            "vz": -_col(c, "CRt", scale=0.01),
            "z_sp": -_col(c, "DAlt"),
        }
    )


def _events(msgs: _Messages, vehicle_type: str | None, warnings: list[str]) -> pd.DataFrame:
    rows: list[tuple[float, str, str]] = []

    mode = msgs.get("MODE")
    if mode is None:
        warnings.append("events: no MODE messages")
    else:
        names = _MODE_NAMES.get(vehicle_type or "rotary_wing", mavutil.mode_mapping_acm)
        nums = _col(mode, "ModeNum", "Mode").to_numpy()
        for t, num in zip(mode["t"].tolist(), nums.tolist(), strict=True):
            n = int(num)
            rows.append((float(t), "mode", names.get(n, f"MODE_{n}")))

    arm = msgs.get("ARM")
    ev = msgs.get("EV")
    if arm is not None:
        for t, state in zip(arm["t"].tolist(), arm["ArmState"].tolist(), strict=True):
            armed = bool(state)
            rows.append((float(t), "arm" if armed else "disarm", "armed" if armed else "disarmed"))
    elif ev is not None:
        for t, ev_id in zip(ev["t"].tolist(), ev["Id"].tolist(), strict=True):
            if ev_id == _EV_ARMED:
                rows.append((float(t), "arm", "armed"))
            elif ev_id == _EV_DISARMED:
                rows.append((float(t), "disarm", "disarmed"))
    else:
        warnings.append("events: no ARM / EV messages, no arm/disarm events")

    err = msgs.get("ERR")
    if err is not None:
        for t, sub, code in zip(
            err["t"].tolist(), err["Subsys"].tolist(), err["ECode"].tolist(), strict=True
        ):
            name = ERR_SUBSYSTEMS.get(int(sub), f"SUBSYS_{int(sub)}")
            if name.startswith("FAILSAFE_"):
                state = "cleared" if code == 0 else f"activated (code {int(code)})"
                rows.append((float(t), "failsafe", f"{name} {state}"))
            elif code == 0:
                rows.append((float(t), "info", f"{name} error resolved"))
            else:
                rows.append((float(t), "error", f"{name} error code {int(code)}"))

    msg = msgs.get("MSG")
    if msg is not None:
        for t, text in zip(msg["t"].tolist(), msg["Message"].tolist(), strict=True):
            rows.append((float(t), "info", str(text).strip()))

    if not rows:
        return empty_table("events")
    df = pd.DataFrame(rows, columns=["t", "kind", "message"])
    return df.sort_values("t", kind="stable").reset_index(drop=True)


def _firmware(msgs: _Messages) -> tuple[str | None, str | None]:
    """(firmware string, vehicle type) from the version line ArduPilot logs at boot."""
    msg = msgs.get("MSG")
    if msg is None:
        return None, None
    for text in msg["Message"].astype(str):
        match = _FIRMWARE_RE.match(text.strip())
        if match:
            return text.strip(), _VEHICLE_TYPES.get(match.group(1))
    return None, None


def parse_dataflash(path: str | Path, config: SkyTraceConfig | None = None) -> FlightLog:
    """Parse an ArduPilot ``.bin`` DataFlash log into a :class:`FlightLog`."""
    cfg = config if config is not None else load_config()
    p = Path(path)
    msgs = _Messages(p)
    warnings: list[str] = []
    firmware, vehicle_type = _firmware(msgs)
    vibration = _vibration(msgs, warnings)
    vib_source: VibMetricSource | None = None if vibration.empty else "ardupilot_vibe"

    return FlightLog(
        metadata=LogMetadata(
            format="ardupilot_dataflash",
            source=str(p),
            duration_s=msgs.duration_s,
            firmware=firmware,
            vehicle_type=vehicle_type,
            # ArduPilot has no cell-count parameter; set detectors.battery.cells.
            battery_cells=None,
            motor_count_known=_motor_count_known(msgs, cfg.parser.motors),
            vib_metric_source=vib_source,
        ),
        attitude=_attitude(msgs, warnings),
        gps=_gps(msgs, cfg, warnings),
        battery=_battery(msgs, warnings),
        motors=_motors(msgs, cfg, warnings),
        vibration=vibration,
        position=_position(msgs, warnings),
        events=_events(msgs, vehicle_type, warnings),
        warnings=warnings,
    )

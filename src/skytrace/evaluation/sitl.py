"""PX4 SITL fault-injection campaign: run plan and automatic labels.

``eval/sitl/run_scenarios.sh`` flies the plan written by :func:`write_plan`;
``eval/label_sitl.py`` turns each recorded log into a label file with
:func:`label_log`.

Labels never use SkyTrace's own thresholds (that would measure a detector
against itself). They come from what was injected and from PX4's own state:

- ``gps``     ``failure gps off`` -> ``failure gps ok`` (vehicle_command 420), or
              disarm if the failure was never cleared.
- ``motor``   a *weak motor*: ``SIM_GZ_EC_MAX1`` (max rpm of motor 1 in Gazebo)
              lowered mid-flight -> restored (parameter changes are logged with
              timestamps), or disarm. Gazebo ignores ``failure motor off``, so
              the cap is used instead; the controller then saturates motor 1 and
              throttles the opposite motor down. The ESC rpm must actually drop
              to the cap, otherwise the run is not labelled.
- ``battery`` first ``battery_status.warning >= LOW`` (PX4's BAT_LOW_THR
              decision) -> disarm.
- ``clean``   no injected fault: ``faults: []``.

In every scenario, ``attitude`` is labelled from PX4's own failure detector
(``failure_detector_status.fd_roll`` / ``fd_pitch``, FD_FAIL_R / FD_FAIL_P) to
disarm: a weak motor sometimes only saturates, sometimes flips the vehicle.
"""

from __future__ import annotations

import csv
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

SCENARIOS: Final = ("clean", "gps", "battery", "motor")

# MAVLink VEHICLE_CMD_INJECT_FAILURE and its FAILURE_UNIT / FAILURE_TYPE values.
CMD_INJECT_FAILURE: Final = 420
UNIT_GPS: Final = 4
TYPE_OK: Final = 0
TYPE_OFF: Final = 1
# battery_status.warning: 0 NONE, 1 LOW, 2 CRITICAL, 3 EMERGENCY, ...
BATTERY_WARNING_LOW: Final = 1
ARMING_STATE_ARMED: Final = 2
# Gazebo motor 1 max rpm parameter and its default (gz_x500).
MOTOR_CAP_PARAM: Final = "SIM_GZ_EC_MAX1"
MOTOR_CAP_DEFAULT: Final = 1000.0
# The ESC must reach the cap (+ this margin) within this time after the change.
MOTOR_CAP_MARGIN: Final = 1.05
MOTOR_CAP_SETTLE_S: Final = 2.0

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Range:
    low: float
    high: float

    def draw(self, rng: random.Random) -> float:
        return round(rng.uniform(self.low, self.high), 1)


@dataclass(frozen=True)
class PlanRanges:
    """Seconds. ``hover``: after takeoff, before the fault (or before landing if clean).

    ``fault``: gps = time until ``failure gps ok``; battery = SIM_BAT_DRAIN (full
    drain time); motor = how long motor 1 stays capped. ``motor_cap``: the cap
    in rpm (gz_x500 hovers at ~770 rpm with a 1000 rpm limit).
    """

    hover: Range = Range(10.0, 30.0)
    clean_hover: Range = Range(40.0, 90.0)
    gps_fault: Range = Range(15.0, 45.0)
    battery_drain: Range = Range(60.0, 120.0)
    motor_fault: Range = Range(15.0, 30.0)
    motor_cap: Range = Range(550.0, 700.0)


@dataclass(frozen=True)
class PlannedRun:
    run_id: str
    scenario: str
    hover_s: float
    fault_s: float
    value: float = 0.0
    """Scenario parameter: motor = rpm cap of motor 1; unused otherwise."""


def make_plan(
    counts: Mapping[str, int],
    *,
    seed: int = 1,
    prefix: str = "sitl_auto",
    ranges: PlanRanges | None = None,
) -> list[PlannedRun]:
    """Deterministic plan; scenarios are interleaved so a crash late in the
    campaign does not wipe out one scenario entirely."""
    unknown = set(counts) - set(SCENARIOS)
    if unknown:
        raise ValueError(f"unknown scenarios: {sorted(unknown)}")
    r = ranges or PlanRanges()
    rng = random.Random(seed)
    runs: list[PlannedRun] = []
    index = {s: 0 for s in SCENARIOS}
    remaining = {s: int(counts.get(s, 0)) for s in SCENARIOS}
    while any(remaining.values()):
        for s in SCENARIOS:
            if remaining[s] <= 0:
                continue
            remaining[s] -= 1
            index[s] += 1
            value = 0.0
            if s == "clean":
                hover, fault = r.clean_hover.draw(rng), 0.0
            else:
                hover = r.hover.draw(rng)
                fault = {"gps": r.gps_fault, "battery": r.battery_drain, "motor": r.motor_fault}[
                    s
                ].draw(rng)
                if s == "motor":
                    value = float(round(r.motor_cap.draw(rng)))
            runs.append(PlannedRun(f"{prefix}_{s}_{index[s]:02d}", s, hover, fault, value))
    return runs


PLAN_FIELDS: Final = ("run_id", "scenario", "hover_s", "fault_s", "value")


def write_plan(runs: Sequence[PlannedRun], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="\n", encoding="utf-8") as fh:  # read by bash: LF only
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(PLAN_FIELDS)
        for run in runs:
            writer.writerow(
                [run.run_id, run.scenario, f"{run.hover_s:g}", f"{run.fault_s:g}", f"{run.value:g}"]
            )
    return out


def read_manifest(path: str | Path) -> list[dict[str, str]]:
    """Rows written by run_scenarios.sh: run_id, scenario, status, hover_s, fault_s, value."""
    with Path(path).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


# --- labels ------------------------------------------------------------------


@dataclass(frozen=True)
class Injection:
    t: float
    unit: int
    type: int


def injections(
    t: FloatArray, command: Sequence[int], param1: Sequence[float], param2: Sequence[float]
) -> list[Injection]:
    return [
        Injection(float(t[i]), int(param1[i]), int(param2[i]))
        for i in range(len(t))
        if int(command[i]) == CMD_INJECT_FAILURE
    ]


def disarm_time(t: FloatArray, arming_state: Sequence[int], log_end: float) -> float:
    """First armed -> not armed transition after having been armed; else log end."""
    armed_seen = False
    for ti, state in zip(t, arming_state, strict=True):
        if int(state) == ARMING_STATE_ARMED:
            armed_seen = True
        elif armed_seen:
            return float(ti)
    return log_end


def _fault(kind: str, t0: float, t1: float, note: str) -> dict[str, Any]:
    return {"type": kind, "t_start": round(t0, 2), "t_end": round(max(t1, t0), 2), "note": note}


def gps_faults(inj: Sequence[Injection], disarm: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    start: float | None = None
    for i in sorted((x for x in inj if x.unit == UNIT_GPS), key=lambda x: x.t):
        if i.type == TYPE_OFF and start is None:
            start = i.t
        elif i.type == TYPE_OK and start is not None:
            out.append(_fault("gps", start, i.t, "failure gps off / ok"))
            start = None
    if start is not None:
        out.append(_fault("gps", start, disarm, "failure gps off, not cleared before disarm"))
    return out


def motor_cap_faults(
    changes: Sequence[tuple[float, str, float]], disarm: float
) -> list[dict[str, Any]]:
    """Intervals where motor 1's rpm cap is below the default, from parameter changes."""
    out: list[dict[str, Any]] = []
    start: float | None = None
    cap = MOTOR_CAP_DEFAULT
    for t, name, value in sorted(changes):
        if name != MOTOR_CAP_PARAM:
            continue
        if value < MOTOR_CAP_DEFAULT and start is None:
            start, cap = t, value
        elif value >= MOTOR_CAP_DEFAULT and start is not None:
            out.append(_fault("motors", start, t, f"{MOTOR_CAP_PARAM} {cap:g} rpm (weak motor 1)"))
            start = None
    if start is not None:
        note = f"{MOTOR_CAP_PARAM} {cap:g} rpm (weak motor 1), until disarm"
        out.append(_fault("motors", start, disarm, note))
    return out


def motor_cap_applied(
    t: FloatArray, rpm: npt.ArrayLike, t_start: float, t_end: float, cap: float
) -> bool:
    """ESC rpm of motor 1 reaches the cap after the change (the sim really applied it)."""
    window = (t >= t_start + MOTOR_CAP_SETTLE_S) & (t <= t_end)
    values = np.asarray(rpm, dtype=np.float64)[window]
    return values.size > 0 and float(np.nanmax(values)) <= cap * MOTOR_CAP_MARGIN


def battery_faults(t: FloatArray, warning: Sequence[int], disarm: float) -> list[dict[str, Any]]:
    for ti, w in zip(t, warning, strict=True):
        if int(w) >= BATTERY_WARNING_LOW and ti <= disarm:
            return [_fault("battery", float(ti), disarm, "battery_status.warning >= LOW")]
    return []


def attitude_faults(
    t: FloatArray, fd_roll: npt.ArrayLike, fd_pitch: npt.ArrayLike, disarm: float
) -> list[dict[str, Any]]:
    """PX4 failure detector roll/pitch failure while armed -> disarm."""
    failed = np.asarray(fd_roll, dtype=bool) | np.asarray(fd_pitch, dtype=bool)
    hits = np.flatnonzero(failed & (t <= disarm))
    if hits.size == 0:
        return []
    return [_fault("attitude", float(t[hits[0]]), disarm, "PX4 failure detector: roll/pitch")]


class LabelingError(RuntimeError):
    """The log does not show the planned fault (e.g. the injection was rejected)."""


def label_log(path: str | Path, scenario: str, run_id: str) -> dict[str, Any]:
    """Label file content (see ``skytrace.evaluation.labels``) for one SITL run."""
    from pyulog import ULog

    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    topics = [
        "vehicle_command",
        "vehicle_status",
        "battery_status",
        "esc_status",
        "failure_detector_status",
    ]
    ulog = ULog(str(path), topics)
    t0 = int(ulog.start_timestamp)
    end = (int(ulog.last_timestamp) - t0) / 1e6
    data = {d.name: d.data for d in ulog.data_list if d.multi_id == 0}

    def rel(name: str) -> FloatArray:
        stamps = np.asarray(data[name]["timestamp"], dtype=np.int64)
        out: FloatArray = (stamps - t0).astype(np.float64) / 1e6
        return out

    disarm = end
    if "vehicle_status" in data:
        disarm = disarm_time(rel("vehicle_status"), data["vehicle_status"]["arming_state"], end)
    inj: list[Injection] = []
    if "vehicle_command" in data:
        c = data["vehicle_command"]
        inj = injections(rel("vehicle_command"), c["command"], c["param1"], c["param2"])

    if scenario == "clean":
        faults: list[dict[str, Any]] = []
    elif scenario == "gps":
        faults = gps_faults(inj, disarm)
    elif scenario == "motor":
        changes = [((ts - t0) / 1e6, str(n), float(v)) for ts, n, v in ulog.changed_parameters]
        faults = motor_cap_faults(changes, disarm)
        caps = [v for _, n, v in changes if n == MOTOR_CAP_PARAM and v < MOTOR_CAP_DEFAULT]
        if faults and "esc_status" not in data:
            raise LabelingError(f"{run_id}: no esc_status to verify the motor cap")
        for f, cap in zip(faults, caps, strict=False):
            if not motor_cap_applied(
                rel("esc_status"),
                data["esc_status"]["esc[0].esc_rpm"],
                f["t_start"],
                f["t_end"],
                cap,
            ):
                raise LabelingError(f"{run_id}: motor 1 rpm never reached the {cap:g} rpm cap")
    else:
        if "battery_status" not in data:
            raise LabelingError(f"{run_id}: no battery_status topic")
        b = data["battery_status"]
        faults = battery_faults(rel("battery_status"), b["warning"], disarm)
    if scenario != "clean" and not faults:
        raise LabelingError(f"{run_id}: planned {scenario} fault not found in the log")
    if "failure_detector_status" in data:
        fd = data["failure_detector_status"]
        faults += attitude_faults(
            rel("failure_detector_status"), fd["fd_roll"], fd["fd_pitch"], disarm
        )
    return {"log": f"{run_id}.ulg", "source": f"sitl auto ({scenario})", "faults": faults}

import math

import numpy as np
import pytest
from typer.testing import CliRunner

from skytrace import FlightLog
from skytrace.cli import app
from skytrace.detectors import run_detectors
from tests.dataflash_writer import DataFlashWriter
from tests.factories import override

RATE = 10  # Hz
DURATION = 60.0


def flight(**faults):
    """A 60 s armed hover (quad, 4S) with optional faults, as a DataFlashWriter.

    faults: vibe=(t0, t1), gps_loss=(t0, t1), sag=(t0, t1), motor_sat=(t0, t1), att=(t0, t1)
    """

    def during(name, t):
        span = faults.get(name)
        return span is not None and span[0] <= t <= span[1]

    w = DataFlashWriter()
    w.add("MSG", 0.0, Message="ArduCopter V4.5.7 (2a3dc4b7)")
    for name, value in (("FRAME_CLASS", 1), ("MOT_PWM_MIN", 1000), ("MOT_PWM_MAX", 2000)):
        w.add("PARM", 0.0, Name=name, Value=value)
    w.add("MODE", 1.0, Mode=5, ModeNum=5, Rsn=1)
    w.add("ARM", 1.0, ArmState=1)
    for i in range(int(DURATION * RATE)):
        t = i / RATE
        roll = 25.0 if during("att", t) else 1.0
        w.add("ATT", t, DesRoll=0.0, Roll=roll, DesPitch=0.0, Pitch=0.5, DesYaw=90, Yaw=90)
        lost = during("gps_loss", t)
        w.add(
            "GPS",
            t,
            I=0,
            Status=1 if lost else 3,
            NSats=3 if lost else 14,
            HDop=9.9 if lost else 0.7,
            Lat=47.39,
            Lng=8.54,
            Alt=488.0,
        )
        w.add("GPA", t, I=0, HAcc=20.0 if lost else 0.8)
        volt = 13.2 if during("sag", t) else 16.0
        w.add("BAT", t, Inst=0, Volt=volt, Curr=12.0, RemPct=80)
        sat = during("motor_sat", t)
        w.add("RCOU", t, C1=2000 if sat else 1550, C2=1550, C3=1550, C4=1550, C5=1100)
        vibe = 45.0 if during("vibe", t) else 8.0
        for imu in (0, 1):
            w.add("VIBE", t, IMU=imu, VibeX=vibe, VibeY=6.0, VibeZ=10.0, Clip=0)
        w.add("CTUN", t, Alt=10.0, DAlt=10.0, CRt=0)
    w.add("ARM", DURATION - 0.5, ArmState=0)
    return w


CFG = override(battery={"cells": 4})


@pytest.fixture
def write(tmp_path):
    def _write(writer, name="flight.bin"):
        return writer.write(tmp_path / name)

    return _write


def test_parses_into_schema(write):
    log = FlightLog.from_file(write(flight()), CFG)
    m = log.metadata
    assert m.format == "ardupilot_dataflash"
    assert m.firmware == "ArduCopter V4.5.7 (2a3dc4b7)"
    assert m.vehicle_type == "rotary_wing"
    assert m.vib_metric_source == "ardupilot_vibe"
    assert m.motor_count_known
    assert m.duration_s == pytest.approx(59.9)
    assert log.motor_count == 4  # FRAME_CLASS 1 = quad, C5 is not a motor
    assert log.motors["m1"].iloc[0] == pytest.approx(0.55)
    assert log.attitude["yaw"].iloc[0] == pytest.approx(math.pi / 2)
    assert log.battery["remaining"].iloc[0] == pytest.approx(0.8)
    assert log.gps["eph"].iloc[0] == pytest.approx(0.8)
    assert log.position["z"].iloc[0] == pytest.approx(-10.0)
    kinds = log.events.set_index("kind")["message"]
    assert kinds["mode"] == "LOITER"
    assert kinds["arm"] == "armed"
    assert kinds["disarm"] == "disarmed"


def test_healthy_flight_has_no_findings(write):
    log = FlightLog.from_file(write(flight()), CFG)
    assert run_detectors(log, CFG).findings == []


@pytest.mark.parametrize(
    ("fault", "detector", "metric"),
    [
        ("vibe", "vibration", "accel_vib_metric"),
        ("gps_loss", "gps", "fix_type"),
        ("sag", "battery", "cell_voltage"),
        ("motor_sat", "motors", "m1_saturated_s"),
        ("att", "attitude", "roll_error_deg"),
    ],
)
def test_existing_detectors_find_fault(write, fault, detector, metric):
    log = FlightLog.from_file(write(flight(**{fault: (20.0, 30.0)})), CFG)
    findings = run_detectors(log, CFG, only=[detector]).findings
    hit = [f for f in findings if f.metric == metric]
    assert hit, findings
    assert hit[0].t_start == pytest.approx(20.0, abs=0.2)
    assert hit[0].t_end == pytest.approx(30.0, abs=0.2)


def test_vibe_takes_worst_imu(write):
    w = DataFlashWriter()
    for i in range(10):
        w.add("VIBE", i / 10, IMU=0, VibeX=5, VibeY=5, VibeZ=5, Clip=0)
        w.add("VIBE", i / 10, IMU=1, VibeX=7, VibeY=40, VibeZ=5, Clip=i)
    vib = FlightLog.from_file(write(w)).vibration
    assert (vib["accel_vib_metric"] == 40.0).all()
    assert vib["clip_count"].iloc[-1] == 9.0
    assert vib["gyro_vib_metric"].isna().all()


def test_old_message_variants(write):
    # Older ArduPilot: VIBE with Clip0/1/2, CURR instead of BAT, EV instead of ARM.
    w = DataFlashWriter()
    for i in range(10):
        t = i / 10
        w.add("VIBE_OLD", t, VibeX=1, VibeY=2, VibeZ=3, Clip0=0, Clip1=i, Clip2=1)
        w.add("CURR", t, Volt=12.0, Curr=5.0)
    w.add("EV", 0.2, Id=10)
    w.add("EV", 0.8, Id=11)
    log = FlightLog.from_file(write(w))
    assert log.vibration["clip_count"].tolist()[-1] == 9.0
    assert log.vibration["accel_vib_metric"].iloc[0] == 3.0
    assert log.battery["voltage"].iloc[0] == 12.0
    assert log.battery["remaining"].isna().all()
    assert log.events["kind"].tolist() == ["arm", "disarm"]


def test_ev_takeoff_and_landing(write):
    w = DataFlashWriter()
    w.add("ARM", 1.0, ArmState=1)
    w.add("EV", 2.0, Id=28)  # NOT_LANDED
    w.add("EV", 9.0, Id=17)  # LAND_COMPLETE_MAYBE: not final, ignored
    w.add("EV", 9.5, Id=18)  # LAND_COMPLETE
    w.add("ARM", 10.0, ArmState=0)
    ev = FlightLog.from_file(write(w)).events
    assert ev["kind"].tolist() == ["arm", "takeoff", "landing", "disarm"]
    t = ev["t"].to_numpy()
    assert (t - t[0]).tolist() == [0.0, 1.0, 8.5, 9.0]  # times relative to the log start


def test_err_messages_become_events(write):
    w = DataFlashWriter()
    w.add("ERR", 1.0, Subsys=6, ECode=1)
    w.add("ERR", 2.0, Subsys=6, ECode=0)
    w.add("ERR", 3.0, Subsys=11, ECode=2)
    w.add("ERR", 4.0, Subsys=99, ECode=0)
    ev = FlightLog.from_file(write(w)).events
    assert ev["kind"].tolist() == ["failsafe", "failsafe", "error", "info"]
    assert ev["message"].tolist() == [
        "FAILSAFE_BATT activated (code 1)",
        "FAILSAFE_BATT cleared",
        "GPS error code 2",
        "SUBSYS_99 error resolved",
    ]


def test_missing_messages_leave_empty_tables(write):
    w = DataFlashWriter()
    w.add("MSG", 0.0, Message="hello")
    log = FlightLog.from_file(write(w))
    for name in ("attitude", "gps", "battery", "motors", "vibration", "position"):
        assert log.table(name).empty, name
    assert log.metadata.vib_metric_source is None
    assert any("no ATT" in warning for warning in log.warnings)
    assert run_detectors(log).findings == []


def test_motor_count_unknown_uses_all_outputs(write):
    w = DataFlashWriter()
    w.add("RCOU", 0.0, C1=1500, C2=1500)
    log = FlightLog.from_file(write(w))
    assert not log.metadata.motor_count_known
    assert log.motor_count == 14
    assert any("motor count unknown" in warning for warning in log.warnings)


def test_pwm_falls_back_to_rc3_range(write):
    w = DataFlashWriter()
    for name, value in (("FRAME_CLASS", 1), ("MOT_PWM_MIN", 0), ("RC3_MIN", 1100)):
        w.add("PARM", 0.0, Name=name, Value=value)
    w.add("PARM", 0.0, Name="RC3_MAX", Value=1900)
    w.add("RCOU", 0.0, C1=1500)
    log = FlightLog.from_file(write(w))
    assert log.motors["m1"].iloc[0] == pytest.approx(0.5)
    assert np.isclose(log.motors["m2"].iloc[0], 0.0)


def test_cli_analyze_bin(write, tmp_path):
    path = write(flight(vibe=(20.0, 30.0)))
    out = tmp_path / "r.json"
    res = CliRunner().invoke(app, ["analyze", str(path), "-f", "json", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert "vibration" in res.output

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from skytrace import FlightLog
from skytrace.config import load_config
from skytrace.parsers import ulog as ulog_mod
from skytrace.parsers.ulog import _quat_to_euler, parse_ulog

START_US = 1_000_000


def _topic(name, data, multi_id=0):
    arrays = {k: np.asarray(v) for k, v in data.items()}
    return SimpleNamespace(name=name, multi_id=multi_id, data=arrays)


def _fake_ulog(topics, params=None, messages=()):
    return SimpleNamespace(
        start_timestamp=START_US,
        last_timestamp=START_US + 10_000_000,
        data_list=list(topics),
        initial_parameters=params or {},
        logged_messages=list(messages),
        msg_info_dict={"ver_sw": "abc123", "ver_hw": "TEST_HW"},
    )


def _parse_fake(monkeypatch, fake, config=None):
    monkeypatch.setattr(ulog_mod, "ULog", lambda *_args, **_kw: fake)
    return parse_ulog("fake.ulg", config)


def _ts(*seconds):
    return [START_US + int(s * 1e6) for s in seconds]


# --- fixture log (real PX4 data) -------------------------------------------------


def test_fixture_parses(sample_ulog):
    log = FlightLog.from_file(sample_ulog)
    meta = log.metadata
    assert meta.format == "px4_ulog"
    assert meta.hardware == "CUBEPILOT_CUBEORANGE"
    assert meta.vehicle_type == "vtol"
    assert meta.duration_s == pytest.approx(6.51, abs=0.01)

    for name in ("attitude", "gps", "battery", "motors", "vibration", "position", "events"):
        assert not log.table(name).empty, name


def test_fixture_values_in_physical_range(sample_ulog):
    log = FlightLog.from_file(sample_ulog)
    att = log.attitude
    assert att[["roll", "pitch", "yaw"]].abs().max().max() <= np.pi
    assert att["roll_sp"].notna().any()

    gps = log.gps
    assert gps["lat"].between(-90, 90).all()
    assert gps["lon"].between(-180, 180).all()
    assert (gps["fix_type"] == 3).all()
    assert gps["satellites"].min() >= 4

    assert log.battery["voltage"].between(20, 26).all()  # 6S pack
    assert log.battery["remaining"].between(0, 1).all()

    motors = log.motors.drop(columns="t")
    assert ((motors >= 0) & (motors <= 1)).all().all()

    assert (log.vibration[["vib_x", "vib_y", "vib_z"]].dropna() >= 0).all().all()


def test_fixture_events(sample_ulog):
    ev = FlightLog.from_file(sample_ulog).events
    assert list(ev["kind"]) == ["mode", "arm", "info", "info", "info", "disarm"]
    assert ev.iloc[0]["message"] == "MANUAL"
    assert "Takeoff detected" in ev.iloc[2]["message"]
    assert ev["t"].is_monotonic_increasing


def test_fixture_motor_count_from_config(sample_ulog):
    base = load_config()
    cfg = replace(base, parser=replace(base.parser, motors=replace(base.parser.motors, count=4)))
    log = FlightLog.from_file(sample_ulog, cfg)
    assert log.motor_count == 4
    assert not any(w.startswith("motors:") for w in log.warnings)


# --- unit tests on synthetic data ------------------------------------------------


def test_quat_to_euler_known_rotations():
    half = np.pi / 8  # rotations of 45 deg
    df = pd.DataFrame(
        {
            "q[0]": [1.0, np.cos(half), np.cos(half), np.cos(half)],
            "q[1]": [0.0, np.sin(half), 0.0, 0.0],
            "q[2]": [0.0, 0.0, np.sin(half), 0.0],
            "q[3]": [0.0, 0.0, 0.0, np.sin(half)],
        }
    )
    roll, pitch, yaw = _quat_to_euler(df, "q")
    q45 = np.pi / 4
    np.testing.assert_allclose(roll, [0, q45, 0, 0], atol=1e-12)
    np.testing.assert_allclose(pitch, [0, 0, q45, 0], atol=1e-12)
    np.testing.assert_allclose(yaw, [0, 0, 0, q45], atol=1e-12)


def test_missing_topics_give_empty_tables_and_warnings(monkeypatch):
    log = _parse_fake(monkeypatch, _fake_ulog([]))
    for name in ("attitude", "gps", "battery", "motors", "vibration", "position", "events"):
        assert log.table(name).empty, name
    assert len(log.warnings) >= 6
    assert log.metadata.firmware == "abc123"


def test_new_style_gps_fields(monkeypatch):
    gps = _topic(
        "sensor_gps",
        {
            "timestamp": _ts(0, 1),
            "fix_type": [3, 2],
            "satellites_used": [12, 5],
            "eph": [0.8, 4.0],
            "hdop": [0.7, 2.5],
            "latitude_deg": [41.0, 41.0001],
            "longitude_deg": [29.0, 29.0001],
            "altitude_msl_m": [120.5, 121.0],
        },
    )
    log = _parse_fake(monkeypatch, _fake_ulog([gps]))
    assert log.gps["lat"].tolist() == [41.0, 41.0001]
    assert log.gps["alt"].tolist() == [120.5, 121.0]
    assert log.gps["t"].tolist() == [0.0, 1.0]


def test_old_style_gps_units(monkeypatch):
    gps = _topic(
        "vehicle_gps_position",
        {
            "timestamp": _ts(0),
            "fix_type": [3],
            "satellites_used": [10],
            "eph": [1.0],
            "hdop": [0.9],
            "lat": [410000000],
            "lon": [290000000],
            "alt": [120500],
        },
    )
    log = _parse_fake(monkeypatch, _fake_ulog([gps]))
    assert log.gps["lat"].iloc[0] == pytest.approx(41.0)
    assert log.gps["alt"].iloc[0] == pytest.approx(120.5)


def test_pwm_normalization_uses_params_then_config(monkeypatch):
    outputs = _topic(
        "actuator_outputs",
        {
            "timestamp": _ts(0, 1),
            "noutputs": [2, 2],
            "output[0]": [1100.0, 1900.0],
            "output[1]": [1000.0, 2500.0],
            "output[2]": [0.0, 0.0],
        },
    )
    params = {"PWM_MAIN_MIN1": 1100, "PWM_MAIN_MAX1": 1900, "PWM_MAIN_MIN2": -1}
    log = _parse_fake(monkeypatch, _fake_ulog([outputs], params))
    assert log.motor_count == 2  # noutputs limits the channels
    assert log.motors["m1"].tolist() == [0.0, 1.0]  # per-channel params
    assert log.motors["m2"].tolist() == [0.0, 1.0]  # config fallback 1000..2000, clipped


def test_pwm_ignores_log_params_when_disabled(monkeypatch):
    outputs = _topic("actuator_outputs", {"timestamp": _ts(0), "output[0]": [1500.0]})
    base = load_config()
    cfg = replace(
        base,
        parser=replace(base.parser, motors=replace(base.parser.motors, use_log_params=False)),
    )
    log = _parse_fake(monkeypatch, _fake_ulog([outputs], {"PWM_MAIN_MIN1": 1400}), cfg)
    assert log.motors["m1"].iloc[0] == pytest.approx(0.5)


def test_actuator_motors_preferred_and_rotor_count(monkeypatch):
    motors = _topic(
        "actuator_motors",
        {
            "timestamp": _ts(0, 1),
            "control[0]": [0.2, 0.9],
            "control[1]": [0.3, 1.2],
            "control[2]": [0.4, 0.4],
            "control[3]": [np.nan, np.nan],
        },
    )
    outputs = _topic("actuator_outputs", {"timestamp": _ts(0), "output[0]": [1500.0]})
    log = _parse_fake(monkeypatch, _fake_ulog([motors, outputs], {"CA_ROTOR_COUNT": 2}))
    assert list(log.motors.columns) == ["t", "m1", "m2"]
    assert log.motors["m2"].tolist() == [0.3, 1.0]


def test_status_events_and_message_levels(monkeypatch):
    status = _topic(
        "vehicle_status",
        {
            "timestamp": _ts(0, 1, 2, 3, 4),
            "nav_state": [2, 2, 5, 5, 99],
            "arming_state": [1, 2, 2, 2, 1],
            "failsafe": [False, False, True, False, False],
        },
    )
    messages = [
        SimpleNamespace(timestamp=_ts(1.5)[0], log_level=3, message="ekf error"),
        SimpleNamespace(timestamp=_ts(2.5)[0], log_level=4, message="low battery"),
        SimpleNamespace(timestamp=_ts(0.5)[0], log_level=6, message="hello"),
    ]
    log = _parse_fake(monkeypatch, _fake_ulog([status], messages=messages))
    ev = log.events
    assert list(zip(ev["kind"], ev["message"], strict=True)) == [
        ("mode", "POSCTL"),
        ("info", "hello"),
        ("arm", "armed"),
        ("error", "ekf error"),
        ("mode", "AUTO_RTL"),
        ("failsafe", "failsafe activated"),
        ("warning", "low battery"),
        ("failsafe", "failsafe cleared"),
        ("mode", "NAV_STATE_99"),
        ("disarm", "disarmed"),
    ]


def test_setpoint_merge_respects_tolerance(monkeypatch):
    att = _topic(
        "vehicle_attitude",
        {
            "timestamp": _ts(0, 0.2, 2.0),
            "q[0]": [1.0, 1.0, 1.0],
            "q[1]": [0.0, 0.0, 0.0],
            "q[2]": [0.0, 0.0, 0.0],
            "q[3]": [0.0, 0.0, 0.0],
        },
    )
    sp = _topic(
        "vehicle_attitude_setpoint",
        {"timestamp": _ts(0.1), "roll_body": [0.3], "pitch_body": [0.0], "yaw_body": [0.0]},
    )
    log = _parse_fake(monkeypatch, _fake_ulog([att, sp]))
    roll_sp = log.attitude["roll_sp"].tolist()
    assert np.isnan(roll_sp[0])  # before first setpoint
    assert roll_sp[1] == 0.3  # 0.1 s old, within 0.5 s tolerance
    assert np.isnan(roll_sp[2])  # 1.9 s old, stale

from types import SimpleNamespace

import numpy as np
import pytest
import pyulog

from skytrace.evaluation.labels import load_labels
from skytrace.evaluation.sitl import (
    Injection,
    LabelingError,
    attitude_faults,
    battery_faults,
    disarm_time,
    gps_faults,
    injections,
    label_log,
    make_plan,
    motor_cap_applied,
    motor_cap_faults,
    read_manifest,
    write_plan,
)

COUNTS = {"clean": 3, "gps": 2, "battery": 1, "motor": 2}


# --- plan --------------------------------------------------------------------


def test_plan_is_deterministic_counted_and_interleaved():
    a, b = make_plan(COUNTS, seed=7), make_plan(COUNTS, seed=7)
    assert a == b
    assert a != make_plan(COUNTS, seed=8)
    assert {s: sum(r.scenario == s for r in a) for s in COUNTS} == COUNTS
    assert [r.scenario for r in a[:4]] == ["clean", "gps", "battery", "motor"]
    assert a[0].run_id == "sitl_auto_clean_01" and a[4].run_id == "sitl_auto_clean_02"
    assert len({r.run_id for r in a}) == len(a)


def test_plan_timings_within_ranges():
    for r in make_plan({"clean": 20, "gps": 20, "battery": 20, "motor": 20}, seed=3):
        if r.scenario == "clean":
            assert 40 <= r.hover_s <= 90 and r.fault_s == 0
        else:
            assert 10 <= r.hover_s <= 30
        if r.scenario == "gps":
            assert 15 <= r.fault_s <= 45
        if r.scenario == "battery":
            assert 60 <= r.fault_s <= 120
        if r.scenario == "motor":
            assert 15 <= r.fault_s <= 30 and 550 <= r.value <= 700
        else:
            assert r.value == 0


def test_plan_rejects_unknown_scenario():
    with pytest.raises(ValueError):
        make_plan({"vibration": 2})


def test_write_plan_is_lf_tsv_for_bash(tmp_path):
    path = write_plan(make_plan({"gps": 1}), tmp_path / "sitl" / "plan.tsv")
    raw = path.read_bytes()
    assert b"\r" not in raw
    header, row = raw.decode().splitlines()
    assert header.split("\t") == ["run_id", "scenario", "hover_s", "fault_s", "value"]
    assert row.split("\t")[:2] == ["sitl_auto_gps_01", "gps"]


def test_read_manifest(tmp_path):
    m = tmp_path / "manifest.tsv"
    m.write_text("run_id\tscenario\tstatus\thover_s\tfault_s\nr1\tgps\tok\t12\t20\n", "utf-8")
    assert read_manifest(m) == [
        {"run_id": "r1", "scenario": "gps", "status": "ok", "hover_s": "12", "fault_s": "20"}
    ]


# --- label building blocks ---------------------------------------------------


def test_injections_keep_only_inject_failure_commands():
    t = np.array([1.0, 2.0, 3.0])
    got = injections(t, [176, 420, 420], [0, 4, 4], [0, 1, 0])
    assert got == [Injection(2.0, 4, 1), Injection(3.0, 4, 0)]


def test_disarm_time():
    t = np.array([0.0, 1.0, 2.0, 3.0])
    assert disarm_time(t, [1, 2, 2, 1], 9.0) == 3.0
    assert disarm_time(t, [1, 1, 1, 1], 9.0) == 9.0  # never armed
    assert disarm_time(t, [1, 2, 2, 2], 9.0) == 9.0  # armed until log end


def test_gps_faults_pairs_off_ok_and_uncleared():
    inj = [
        Injection(10.0, 4, 1),
        Injection(40.0, 4, 0),
        Injection(50.0, 4, 1),
        Injection(55.0, 101, 1),
    ]
    faults = gps_faults(inj, disarm=70.0)
    assert [(f["type"], f["t_start"], f["t_end"]) for f in faults] == [
        ("gps", 10.0, 40.0),
        ("gps", 50.0, 70.0),  # never cleared -> ends at disarm
    ]


def test_motor_cap_faults_from_parameter_changes():
    changes = [
        (5.0, "SIM_BAT_DRAIN", 60.0),
        (20.0, "SIM_GZ_EC_MAX1", 620.0),
        (40.0, "SIM_GZ_EC_MAX1", 1000.0),  # reset to default
        (50.0, "SIM_GZ_EC_MAX1", 580.0),  # capped again, never reset
    ]
    faults = motor_cap_faults(changes, disarm=58.0)
    assert [(f["type"], f["t_start"], f["t_end"]) for f in faults] == [
        ("motors", 20.0, 40.0),
        ("motors", 50.0, 58.0),
    ]
    assert "620 rpm" in faults[0]["note"]
    assert motor_cap_faults([(5.0, "SIM_GZ_EC_MAX1", 1000.0)], 30.0) == []


def test_motor_cap_applied_requires_esc_at_cap():
    t = np.arange(0.0, 30.0, 0.5)
    rpm = np.where(t < 21.0, 768.0, 600.0)  # settles at the 600 rpm cap
    assert motor_cap_applied(t, rpm, 20.0, 29.0, 600.0)
    assert not motor_cap_applied(t, np.full_like(t, 768.0), 20.0, 29.0, 600.0)  # ignored
    assert not motor_cap_applied(t, rpm, 40.0, 50.0, 600.0)  # no samples in window


def test_battery_fault_starts_at_px4_low_warning():
    t = np.array([0.0, 10.0, 20.0, 30.0])
    faults = battery_faults(t, [0, 0, 1, 2], disarm=35.0)
    assert [(f["type"], f["t_start"], f["t_end"]) for f in faults] == [("battery", 20.0, 35.0)]
    assert battery_faults(t, [0, 0, 0, 0], 35.0) == []


# --- label_log on a fake ULog ------------------------------------------------

START = 1_000_000


def _ts(*seconds):
    return np.array([START + int(s * 1e6) for s in seconds])


def _fake_ulog(topics, end_s=100.0, changed=()):
    data_list = [SimpleNamespace(name=n, multi_id=0, data=d) for n, d in topics.items()]
    return SimpleNamespace(
        start_timestamp=START,
        last_timestamp=START + int(end_s * 1e6),
        data_list=data_list,
        changed_parameters=[(START + int(t * 1e6), n, v) for t, n, v in changed],
    )


STATUS = {"timestamp": _ts(0, 5, 90), "arming_state": np.array([1, 2, 1])}


def _patch(monkeypatch, topics, changed=()):
    monkeypatch.setattr(pyulog, "ULog", lambda *a, **k: _fake_ulog(topics, changed=changed))


def test_label_log_gps_round_trips_through_label_loader(monkeypatch, tmp_path):
    import yaml

    cmd = {
        "timestamp": _ts(30, 60),
        "command": np.array([420, 420]),
        "param1": np.array([4.0, 4.0]),
        "param2": np.array([1.0, 0.0]),
    }
    _patch(monkeypatch, {"vehicle_status": STATUS, "vehicle_command": cmd})
    content = label_log("x.ulg", "gps", "sitl_auto_gps_01")
    assert content["faults"][0] | {} == {
        "type": "gps",
        "t_start": 30.0,
        "t_end": 60.0,
        "note": "failure gps off / ok",
    }
    path = tmp_path / "sitl_auto_gps_01.yaml"
    path.write_text(yaml.safe_dump(content, sort_keys=False), "utf-8")
    labels = load_labels(path)
    assert labels.log == "sitl_auto_gps_01.ulg"
    assert [(f.type, f.t_start, f.t_end) for f in labels.faults] == [("gps", 30.0, 60.0)]


def test_label_log_clean_and_battery(monkeypatch):
    _patch(monkeypatch, {"vehicle_status": STATUS})
    assert label_log("x.ulg", "clean", "c1")["faults"] == []
    bat = {"timestamp": _ts(10, 50, 70), "warning": np.array([0, 1, 2])}
    _patch(monkeypatch, {"vehicle_status": STATUS, "battery_status": bat})
    (f,) = label_log("x.ulg", "battery", "b1")["faults"]
    assert (f["t_start"], f["t_end"]) == (50.0, 90.0)  # PX4 LOW warning -> disarm


def test_label_log_missing_injection_is_an_error(monkeypatch):
    _patch(monkeypatch, {"vehicle_status": STATUS})
    with pytest.raises(LabelingError, match="not found"):
        label_log("x.ulg", "gps", "g1")
    with pytest.raises(ValueError):
        label_log("x.ulg", "vibration", "v1")


def _esc(rpm_after, t_change=30.0):
    t = np.arange(0.0, 90.0, 0.5)
    return {"timestamp": _ts(*t), "esc[0].esc_rpm": np.where(t < t_change + 1, 768.0, rpm_after)}


def test_label_log_motor_cap_verified_by_esc(monkeypatch):
    changed = [(30.0, "SIM_GZ_EC_MAX1", 600.0), (55.0, "SIM_GZ_EC_MAX1", 1000.0)]
    _patch(monkeypatch, {"vehicle_status": STATUS, "esc_status": _esc(600.0)}, changed)
    (f,) = label_log("x.ulg", "motor", "m1")["faults"]
    assert (f["type"], f["t_start"], f["t_end"]) == ("motors", 30.0, 55.0)


def test_label_log_motor_cap_ignored_by_sim_is_not_labelled(monkeypatch):
    changed = [(30.0, "SIM_GZ_EC_MAX1", 600.0), (55.0, "SIM_GZ_EC_MAX1", 1000.0)]
    _patch(monkeypatch, {"vehicle_status": STATUS, "esc_status": _esc(768.0)}, changed)
    with pytest.raises(LabelingError, match="never reached"):
        label_log("x.ulg", "motor", "m1")


def test_attitude_faults_from_px4_failure_detector():
    t = np.array([0.0, 10.0, 20.0, 30.0])
    (f,) = attitude_faults(t, [0, 0, 1, 1], [0, 0, 0, 0], disarm=40.0)
    assert (f["type"], f["t_start"], f["t_end"]) == ("attitude", 20.0, 40.0)
    assert attitude_faults(t, [0, 0, 0, 0], [0, 0, 0, 1], disarm=25.0) == []  # after disarm


def test_label_log_adds_attitude_when_px4_reports_flip(monkeypatch):
    changed = [(30.0, "SIM_GZ_EC_MAX1", 600.0), (55.0, "SIM_GZ_EC_MAX1", 1000.0)]
    fd = {
        "timestamp": _ts(0, 33, 60),
        "fd_roll": np.array([0, 1, 1]),
        "fd_pitch": np.array([0, 0, 0]),
    }
    topics = {"vehicle_status": STATUS, "esc_status": _esc(600.0), "failure_detector_status": fd}
    _patch(monkeypatch, topics, changed)
    faults = label_log("x.ulg", "motor", "m1")["faults"]
    assert [(f["type"], f["t_start"], f["t_end"]) for f in faults] == [
        ("motors", 30.0, 55.0),
        ("attitude", 33.0, 90.0),
    ]

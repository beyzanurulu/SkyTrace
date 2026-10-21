from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from skytrace.anomaly import ml
from skytrace.config import ConfigError, load_config
from skytrace.detectors import Finding, run_detectors
from skytrace.report.evidence import evidence_for
from tests.factories import events, make_log

DURATION = 300.0
HZ = 20.0
ARMED_POSCTL = events(
    (0.0, "arm", "armed"), (0.0, "mode", "POSCTL"), (DURATION - 1, "disarm", "disarmed")
)


def _t():
    return np.arange(0.0, DURATION, 1.0 / HZ)


def _battery(t, rng, current=None, voltage=None):
    return pd.DataFrame(
        {
            "t": t,
            # slow discharge: a trend, not an anomaly
            "voltage": np.linspace(16.4, 15.2, len(t)) + rng.normal(0, 0.01, len(t))
            if voltage is None
            else voltage,
            "current": 12.0 + rng.normal(0, 0.3, len(t)) if current is None else current,
            "remaining": np.linspace(0.9, 0.5, len(t)),
        }
    )


def _motors(t, rng, level=0.55):
    cols = {f"m{i}": level + rng.normal(0, 0.005, len(t)) for i in range(1, 5)}
    return pd.DataFrame({"t": t, **cols})


def _position(t, rng, vz=None):
    z = np.zeros(len(t))
    return pd.DataFrame(
        {
            "t": t,
            "x": z,
            "y": z,
            "z": z - 10,
            "vx": z,
            "vy": z,
            "vz": rng.normal(0, 0.05, len(t)) if vz is None else vz,
            "z_sp": z - 10,
        }
    )


def _log(seed=0, **tables):
    rng = np.random.default_rng(seed)
    t = _t()
    base = {
        "battery": _battery(t, rng),
        "motors": _motors(t, rng),
        "position": _position(t, rng),
        "events": ARMED_POSCTL,
        "metadata": {"battery_cells": 4},
    }
    base.update(tables)
    return make_log(**base)


def _ml(log, cfg=None):
    r = run_detectors(log, cfg, ml=True)
    return [f for f in r.findings if f.detector == ml.NAME], r.notes


def _anomaly_cfg(**sections):
    cfg = load_config()
    a = cfg.anomaly
    for name, changes in sections.items():
        a = replace(a, **{name: replace(getattr(a, name), **changes)})
    return replace(cfg, anomaly=a)


# --- robust z-score -----------------------------------------------------------


def test_robust_zscore_trailing_spike_and_noise_floor():
    v = np.full(200, 5.0)
    v[150:160] = 9.0
    z = ml.robust_zscore(v, window=50, floor=0.1)
    assert np.all(np.abs(z[60:150]) < 1e-9)  # nothing before the onset (trailing window)
    assert z[150] == pytest.approx(40.0)  # (9 - 5) / floor
    # A constant signal plus tiny noise stays small thanks to the floor.
    noisy = 5.0 + np.random.default_rng(1).normal(0, 1e-4, 200)
    assert np.nanmax(np.abs(ml.robust_zscore(noisy, 50, 0.1))) < 0.1


# --- end to end on synthetic logs ----------------------------------------------


def test_clean_synthetic_flight_has_no_ml_findings():
    found, _ = _ml(_log())
    assert found == []


def test_ml_is_off_by_default():
    log = _log()
    r = run_detectors(log)
    assert not [f for f in r.findings if f.detector == ml.NAME]
    assert not [n for n in r.notes if n.startswith(ml.NAME)]


def test_zscore_finds_a_current_step_the_rules_do_not_cover():
    t = _t()
    rng = np.random.default_rng(0)
    current = 12.0 + rng.normal(0, 0.3, len(t))
    current[(t >= 150) & (t < 160)] += 15.0  # 15 A step for 10 s: no rule watches current
    found, _ = _ml(_log(battery=_battery(t, rng, current=current)))
    z = [f for f in found if f.metric == "zscore:battery_current"]
    assert z, found
    assert 149.5 <= z[0].t_start <= 151.0  # flagged at the onset, not a window earlier
    assert z[0].severity == "warn"
    assert "POSCTL" in z[0].summary and "battery current" in z[0].summary


def test_iforest_finds_an_oscillation_window():
    t = _t()
    rng = np.random.default_rng(0)
    vz = rng.normal(0, 0.05, len(t))
    burst = (t >= 200) & (t < 210)
    vz[burst] += 1.5 * np.sin(2 * np.pi * 3.0 * t[burst])  # 3 Hz oscillation
    # isolate the forest; explicit gates: this tests the mechanism, not calibrated values
    cfg = _anomaly_cfg(
        zscore={"info": 1e6, "warn": 1e6},
        iforest={"enabled": True, "min_feature_z": 6.0, "warn_feature_z": 20.0},
    )
    found, _ = _ml(_log(position=_position(t, rng, vz=vz)), cfg)
    forest = [f for f in found if f.metric.startswith("iforest:")]
    assert len(forest) == 1, found
    f = forest[0]
    assert f.t_start < 210 and f.t_end > 200
    assert f.metric == "iforest:vz"
    assert "vz.std" in f.summary and f.severity == "warn"  # robust z ~ 50


def test_slow_trend_and_takeoff_spinup_are_not_anomalies():
    t = _t()
    rng = np.random.default_rng(3)
    motors = _motors(t, rng)
    for i in range(1, 5):  # spin-up from 0 during the first 3 s after arming
        motors.loc[t < 3, f"m{i}"] = np.linspace(0, 0.55, int((t < 3).sum()))
    found, _ = _ml(_log(motors=motors))
    assert found == []


def test_results_are_deterministic():
    t = _t()
    rng = np.random.default_rng(0)
    vz = rng.normal(0, 0.05, len(t))
    vz[(t >= 200) & (t < 210)] += 1.0
    log = _log(position=_position(t, rng, vz=vz))
    a, _ = _ml(log)
    b, _ = _ml(log)
    assert [(f.t_start, f.metric, f.value) for f in a] == [
        (f.t_start, f.metric, f.value) for f in b
    ]


def test_short_modes_skip_the_forest_with_a_note():
    # 30 s of AUTO_TAKEOFF -> 20 s after trimming -> fewer windows than min_windows
    ev = events(
        (0.0, "arm", "armed"),
        (0.0, "mode", "AUTO_TAKEOFF"),
        (30.0, "mode", "POSCTL"),
        (DURATION - 1, "disarm", "disarmed"),
    )
    _, notes = _ml(_log(events=ev), _anomaly_cfg(iforest={"enabled": True}))
    assert any("skipped for modes" in n and "AUTO_TAKEOFF" in n for n in notes)


def test_isolation_forest_is_off_by_default():
    assert load_config().anomaly.iforest.enabled is False
    t = _t()
    rng = np.random.default_rng(0)
    vz = rng.normal(0, 0.05, len(t))
    burst = (t >= 200) & (t < 210)
    vz[burst] += 1.5 * np.sin(2 * np.pi * 3.0 * t[burst])
    log = _log(position=_position(t, rng, vz=vz))
    found, notes = _ml(log, _anomaly_cfg(zscore={"info": 1e6, "warn": 1e6}))
    assert not [f for f in found if f.metric.startswith("iforest:")]
    assert not [n for n in notes if "Isolation Forest" in n]


def test_mode_segments_split_armed_periods():
    log = _log(
        events=events(
            (10.0, "arm", "armed"),
            (10.0, "mode", "AUTO_TAKEOFF"),
            (20.0, "mode", "POSCTL"),
            (100.0, "disarm", "disarmed"),
        )
    )
    assert ml.mode_segments(log, True) == [
        (10.0, 20.0, "AUTO_TAKEOFF"),
        (20.0, 100.0, "POSCTL"),
    ]


def test_no_signals_is_a_note():
    log = make_log(events=ARMED_POSCTL)
    found, notes = _ml(log)
    assert found == []
    assert any("no usable signals" in n for n in notes)


# --- merging with rule findings ------------------------------------------------


def _finding(det, t0, t1):
    return Finding(det, "warn", t0, t1, "m", 1.0, 1.0, "s")


def test_merge_with_rules_drops_overlaps_and_notes_them():
    notes: list[str] = []
    mlf = [_finding(ml.NAME, 10, 12), _finding(ml.NAME, 50, 55)]
    rules = [_finding("gps", 11, 30)]
    kept = ml.merge_with_rules(mlf, rules, notes)
    assert [(f.t_start, f.t_end) for f in kept] == [(50, 55)]
    assert notes == ["ml_anomaly: 1 finding(s) overlapped rule findings (gps 11.0-30.0 s), merged"]


def test_ml_finding_inside_rule_finding_is_merged_end_to_end():
    t = _t()
    rng = np.random.default_rng(0)
    voltage = np.linspace(16.4, 15.2, len(t))
    voltage[(t >= 150) & (t < 152)] -= 2.4  # 0.6 V/cell sag: battery rule fires too
    current = 12.0 + rng.normal(0, 0.3, len(t))
    log = _log(battery=_battery(t, rng, voltage=voltage, current=current))
    r = run_detectors(log, ml=True)
    assert any(f.detector == "battery" for f in r.findings)
    assert not [f for f in r.findings if f.detector == ml.NAME and 148 < f.t_start < 153]
    assert any("overlapped rule findings" in n and "battery" in n for n in r.notes)


# --- report / config ------------------------------------------------------------


def test_evidence_plots_the_anomalous_signal():
    t = _t()
    log = _log()
    f = Finding(ml.NAME, "warn", 150, 160, "zscore:battery_current", 20.0, 15.0, "s")
    ev = evidence_for(log, f, load_config())
    assert ev is not None and ev.threshold is None
    assert "battery current" in ev.title
    (trace,) = ev.traces
    assert trace.t.min() >= 140 and trace.t.max() <= 170
    assert len(t) > len(trace.t)


@pytest.mark.parametrize(
    "section,changes",
    [
        ("zscore", {"info": 10.0, "warn": 5.0}),
        ("iforest", {"contamination": 0.7}),
        ("iforest", {"step_s": 10.0}),
        ("iforest", {"hf_cutoff_hz": 6.0}),  # >= Nyquist of 10 Hz
        ("iforest", {"min_feature_z": 30.0, "warn_feature_z": 20.0}),
    ],
)
def test_anomaly_config_checks(tmp_path, section, changes):
    body = "\n".join(f"    {k}: {v}" for k, v in changes.items())
    path = tmp_path / "c.yaml"
    path.write_text(f"anomaly:\n  {section}:\n{body}\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_disabling_a_signal(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("anomaly:\n  signals:\n    vz: null\n", encoding="utf-8")
    cfg = load_config(path)
    assert "vz" not in ml.enabled_signals(cfg.anomaly)
    assert "battery_current" in ml.enabled_signals(cfg.anomaly)


def test_ground_time_before_a_manual_takeoff_is_not_analysed():
    t = _t()
    rng = np.random.default_rng(4)
    motors = _motors(t, rng)
    idle = t < 60  # armed on the ground for 60 s, then a manual takeoff in POSCTL
    for i in range(1, 5):
        motors.loc[idle, f"m{i}"] = 0.05 + rng.normal(0, 0.005, int(idle.sum()))
        motors.loc[(t >= 60) & (t < 63), f"m{i}"] = np.linspace(
            0.05, 0.55, int(((t >= 60) & (t < 63)).sum())
        )
    ev = events(
        (0.0, "arm", "armed"),
        (0.0, "mode", "POSCTL"),
        (61.0, "takeoff", "t"),
        (DURATION - 3, "landing", "l"),
        (DURATION - 1, "disarm", "disarmed"),
    )
    assert ml.mode_segments(_log(events=ev), True) == [(61.0, DURATION - 3, "POSCTL")]
    found, _ = _ml(_log(motors=motors, events=ev))
    assert found == []


# --- calibration statistics match detection -----------------------------------


@pytest.mark.parametrize("step_a", [0.0, 3.0, 15.0])
def test_zscore_statistic_decides_exactly_like_detection(step_a):
    t = _t()
    rng = np.random.default_rng(0)
    current = 12.0 + rng.normal(0, 0.3, len(t))
    current[(t >= 150) & (t < 160)] += step_a
    log = _log(battery=_battery(t, rng, current=current))
    cfg = load_config()
    stat = ml.zscore_log_statistic(ml.make_grids(log, cfg), cfg.anomaly)
    found = ml.zscore_findings(ml.make_grids(log, cfg), cfg.anomaly)
    assert bool(found) == (stat > cfg.anomaly.zscore.info)
    # Raising info just above / below the statistic flips the decision.
    above = _anomaly_cfg(zscore={"info": stat + 0.01, "warn": stat + 1})
    assert ml.zscore_findings(ml.make_grids(log, above), above.anomaly) == []


def test_iforest_statistic_decides_exactly_like_detection():
    t = _t()
    rng = np.random.default_rng(0)
    vz = rng.normal(0, 0.05, len(t))
    burst = (t >= 200) & (t < 210)
    vz[burst] += 1.5 * np.sin(2 * np.pi * 3.0 * t[burst])
    log = _log(position=_position(t, rng, vz=vz))
    cfg = load_config()
    grids = ml.make_grids(log, cfg)
    stat = ml.iforest_log_statistic(grids, cfg.anomaly)
    assert stat > 6.0  # the oscillation stands out (robust z ~ 50)
    for gate, expected in ((stat - 0.01, True), (stat + 0.01, False)):
        c = _anomaly_cfg(iforest={"min_feature_z": gate, "warn_feature_z": gate + 1})
        assert bool(ml.iforest_findings(grids, c.anomaly, [])) is expected

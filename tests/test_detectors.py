import numpy as np
import pandas as pd
import pytest

from skytrace import FlightLog
from skytrace.detectors import DETECTORS, run_detectors
from tests.factories import events, make_log, override, step, time_axis

ARMED_0_60 = events((0.0, "arm", "armed"), (59.0, "disarm", "disarmed"))


def _only(log, name, config=None):
    return run_detectors(log, config, only=[name])


# --- vibration ---------------------------------------------------------------


def _vibration(t, z, clips=None):
    return pd.DataFrame(
        {
            "t": t,
            "vib_x": np.full(len(t), 5.0),
            "vib_y": np.full(len(t), 5.0),
            "vib_z": z,
            "clip_count": np.zeros(len(t)) if clips is None else clips,
        }
    )


def test_vibration_clean():
    t = time_axis(60)
    r = _only(
        make_log(vibration=_vibration(t, np.full(len(t), 10.0)), events=ARMED_0_60), "vibration"
    )
    assert r.findings == []


@pytest.mark.parametrize(("level", "severity"), [(40.0, "warn"), (70.0, "critical")])
def test_vibration_levels(level, severity):
    t = time_axis(60)
    z = step(t, 10.0, level, 10.0, 15.0)
    r = _only(make_log(vibration=_vibration(t, z), events=ARMED_0_60), "vibration")
    (f,) = r.findings
    assert (f.severity, f.metric, f.value) == (severity, "vib_z", level)
    assert f.t_start == pytest.approx(10.0)
    assert f.t_end == pytest.approx(15.0)
    assert "Z axis" in f.summary


def test_vibration_short_spike_ignored():
    t = time_axis(60)
    z = step(t, 10.0, 90.0, 10.0, 10.5)  # shorter than min_duration_s = 1.0
    r = _only(make_log(vibration=_vibration(t, z), events=ARMED_0_60), "vibration")
    assert r.findings == []


def test_vibration_ignored_while_disarmed():
    t = time_axis(60)
    z = step(t, 10.0, 90.0, 10.0, 20.0)
    log = make_log(
        vibration=_vibration(t, z),
        events=events((30.0, "arm", "armed"), (50.0, "disarm", "disarmed")),
    )
    assert _only(log, "vibration").findings == []
    no_arm_filter = override(detectors={"only_when_armed": False})
    assert len(_only(log, "vibration", no_arm_filter).findings) == 1


def test_clipping_warn_and_critical():
    t = time_axis(60)
    clips = np.zeros(len(t))
    clips[t >= 5] += 3  # small burst -> warn
    clips[t >= 30] += 200  # big burst -> critical
    r = _only(
        make_log(vibration=_vibration(t, np.full(len(t), 5.0), clips), events=ARMED_0_60),
        "vibration",
    )
    assert [(f.metric, f.severity, f.value) for f in r.findings] == [
        ("clip_count", "warn", 3.0),
        ("clip_count", "critical", 200.0),
    ]


def test_clipping_missing_counter_is_a_note():
    t = time_axis(10)
    log = make_log(vibration=_vibration(t, np.full(len(t), 5.0), np.full(len(t), np.nan)))
    r = _only(log, "vibration")
    assert r.findings == []
    assert any("clipping" in n for n in r.notes)


# --- gps ---------------------------------------------------------------------


def _gps(t, **cols):
    base = {
        "t": t,
        "fix_type": np.full(len(t), 3.0),
        "satellites": np.full(len(t), 14.0),
        "eph": np.full(len(t), 0.8),
        "hdop": np.full(len(t), 0.7),
        "lat": np.full(len(t), 41.0),
        "lon": np.full(len(t), 29.0),
        "alt": np.full(len(t), 100.0),
    }
    base.update(cols)
    return pd.DataFrame(base)


def test_gps_clean():
    t = time_axis(60)
    assert _only(make_log(gps=_gps(t), events=ARMED_0_60), "gps").findings == []


def test_gps_fix_loss_is_critical():
    t = time_axis(60)
    log = make_log(gps=_gps(t, fix_type=step(t, 3, 1, 20, 25)), events=ARMED_0_60)
    (f,) = _only(log, "gps").findings
    assert (f.metric, f.severity, f.value, f.threshold) == ("fix_type", "critical", 1.0, 3.0)


def test_gps_quality_warnings():
    t = time_axis(60)
    log = make_log(
        gps=_gps(
            t,
            satellites=step(t, 14, 4, 10, 12),
            eph=step(t, 0.8, 6.0, 30, 35),
            hdop=step(t, 0.7, 3.0, 40, 42),
        ),
        events=ARMED_0_60,
    )
    found = _only(log, "gps").findings
    assert [(f.metric, f.severity, f.value) for f in found] == [
        ("satellites", "warn", 4.0),
        ("eph", "warn", 6.0),
        ("hdop", "warn", 3.0),
    ]


# --- battery -----------------------------------------------------------------


def _battery(t, voltage, remaining=None):
    return pd.DataFrame(
        {
            "t": t,
            "voltage": voltage,
            "current": np.full(len(t), 10.0),
            "remaining": np.full(len(t), 0.8) if remaining is None else remaining,
        }
    )


def test_battery_clean_4s():
    t = time_axis(60)
    log = make_log(
        battery=_battery(t, np.full(len(t), 16.0)), events=ARMED_0_60, metadata={"battery_cells": 4}
    )
    r = _only(log, "battery")
    assert r.findings == []
    assert r.notes == []


def test_battery_low_cell_voltage():
    t = time_axis(60)
    v = np.linspace(16.0, 13.0, len(t))  # 4.0 -> 3.25 V/cell, slow discharge
    log = make_log(battery=_battery(t, v), events=ARMED_0_60, metadata={"battery_cells": 4})
    found = _only(log, "battery").findings
    (low,) = [f for f in found if f.metric == "cell_voltage"]
    assert low.severity == "critical"
    # Lowest armed sample: the sample at the disarm time (59.0 s) is already disarmed.
    assert low.value == pytest.approx(v[t < 58.95].min() / 4)
    assert "4S" in low.summary
    assert not [f for f in found if f.metric == "voltage_sag_per_cell"]  # slow, not sag


@pytest.mark.parametrize(("drop", "severity"), [(1.6, "warn"), (2.4, "critical")])
def test_battery_sag(drop, severity):
    t = time_axis(60)
    v = step(t, 16.0, 16.0 - drop, 20.0, 20.3)  # 0.4 / 0.6 V per cell, 4S
    log = make_log(battery=_battery(t, v), events=ARMED_0_60, metadata={"battery_cells": 4})
    (f,) = _only(log, "battery").findings
    assert (f.metric, f.severity) == ("voltage_sag_per_cell", severity)
    assert f.value == pytest.approx(drop / 4)


def test_battery_cells_from_config_override_metadata():
    t = time_axis(60)
    v = np.full(len(t), 16.0)  # fine as 4S, 2.67 V/cell if (wrongly) 6S
    log = make_log(battery=_battery(t, v), events=ARMED_0_60, metadata={"battery_cells": 4})
    assert _only(log, "battery").findings == []
    found = _only(log, "battery", override(battery={"cells": 6})).findings
    assert [f.severity for f in found] == ["critical"]


def test_battery_unknown_cells_skips_voltage_checks():
    t = time_axis(60)
    log = make_log(battery=_battery(t, np.full(len(t), 9.0)), events=ARMED_0_60)
    r = _only(log, "battery")
    assert r.findings == []
    assert any("cell count unknown" in n for n in r.notes)


def test_battery_remaining():
    t = time_axis(60)
    rem = np.linspace(0.3, 0.05, len(t))
    log = make_log(
        battery=_battery(t, np.full(len(t), 16.0), rem),
        events=ARMED_0_60,
        metadata={"battery_cells": 4},
    )
    (f,) = _only(log, "battery").findings
    assert (f.metric, f.severity) == ("remaining", "critical")
    assert "%" in f.summary


# --- attitude ----------------------------------------------------------------


def _attitude(t, roll, roll_sp, pitch_sp=None):
    zeros = np.zeros(len(t))
    return pd.DataFrame(
        {
            "t": t,
            "roll": roll,
            "pitch": zeros,
            "yaw": zeros,
            "roll_sp": roll_sp,
            "pitch_sp": zeros if pitch_sp is None else pitch_sp,
            "yaw_sp": zeros,
        }
    )


@pytest.mark.parametrize(("err_deg", "severity"), [(5.0, None), (15.0, "warn"), (30.0, "critical")])
def test_attitude_error(err_deg, severity):
    t = time_axis(60)
    roll = np.zeros(len(t))
    roll_sp = step(t, 0.0, np.radians(err_deg), 10.0, 13.0)
    found = _only(
        make_log(attitude=_attitude(t, roll, roll_sp), events=ARMED_0_60), "attitude"
    ).findings
    if severity is None:
        assert found == []
    else:
        (f,) = found
        assert (f.metric, f.severity) == ("roll_error_deg", severity)
        assert f.value == pytest.approx(err_deg)


def test_attitude_error_wraps_around_pi():
    t = time_axis(60)
    roll = np.full(len(t), np.radians(179.0))
    roll_sp = np.full(len(t), np.radians(-179.0))  # 2 degrees apart, not 358
    log = make_log(attitude=_attitude(t, roll, roll_sp), events=ARMED_0_60)
    assert _only(log, "attitude").findings == []


def test_attitude_without_setpoints_is_a_note():
    t = time_axis(10)
    nan = np.full(len(t), np.nan)
    log = make_log(attitude=_attitude(t, np.zeros(len(t)), nan, nan))
    r = _only(log, "attitude")
    assert r.findings == []
    assert r.notes


# --- motors ------------------------------------------------------------------


def _motors(t, *cols):
    return pd.DataFrame({"t": t, **{f"m{i}": c for i, c in enumerate(cols, start=1)}})


def test_motors_balanced_hover_is_clean():
    t = time_axis(60)
    hover = np.full(len(t), 0.5)
    log = make_log(motors=_motors(t, hover, hover, hover, hover), events=ARMED_0_60)
    assert _only(log, "motors").findings == []


@pytest.mark.parametrize(("dur", "severity"), [(0.3, None), (1.0, "warn"), (3.0, "critical")])
def test_motor_saturation(dur, severity):
    t = time_axis(60)
    hover = np.full(len(t), 0.5)
    m2 = step(t, 0.5, 1.0, 20.0, 20.0 + dur)
    log = make_log(motors=_motors(t, hover, m2, hover, hover), events=ARMED_0_60)
    found = [f for f in _only(log, "motors").findings if f.metric.endswith("saturated_s")]
    if severity is None:
        assert found == []
    else:
        (f,) = found
        assert (f.metric, f.severity) == ("m2_saturated_s", severity)
        assert f.value == pytest.approx(dur, abs=0.11)


def test_motor_imbalance():
    t = time_axis(60)
    others = np.full(len(t), 0.45)
    high = np.full(len(t), 0.75)  # 0.3 above m1..m3 -> 0.225 above the 4-motor mean
    log = make_log(motors=_motors(t, others, others, others, high), events=ARMED_0_60)
    found = [f for f in _only(log, "motors").findings if f.metric.endswith("imbalance")]
    m4 = [f for f in found if f.metric == "m4_imbalance"]
    assert len(m4) == 1
    assert m4[0].severity == "warn"
    assert m4[0].value == pytest.approx(0.225)
    assert "above" in m4[0].summary


def test_motor_imbalance_skipped_when_count_unknown():
    t = time_axis(60)
    others = np.full(len(t), 0.45)
    high = np.full(len(t), 0.9)
    log = make_log(
        motors=_motors(t, others, others, others, high),
        events=ARMED_0_60,
        metadata={"motor_count_known": False},
    )
    r = _only(log, "motors")
    assert not [f for f in r.findings if f.metric.endswith("imbalance")]
    assert any("parser.motors.count" in n for n in r.notes)


# --- registry / integration --------------------------------------------------


def test_run_detectors_ids_sorted_by_time():
    t = time_axis(60)
    log = make_log(
        gps=_gps(t, fix_type=step(t, 3, 1, 40, 45)),
        vibration=_vibration(t, step(t, 10.0, 70.0, 5.0, 8.0)),
        events=ARMED_0_60,
    )
    r = run_detectors(log)
    assert [f.id for f in r.findings] == ["F001", "F002"]
    assert [f.detector for f in r.findings] == ["vibration", "gps"]


def test_run_detectors_unknown_name():
    with pytest.raises(KeyError):
        run_detectors(make_log(), only=["nope"])


def test_empty_log_produces_only_notes():
    r = run_detectors(make_log())
    assert r.findings == []
    assert len(r.notes) == len(DETECTORS)


def test_fixture_log_runs_all_detectors(sample_ulog):
    r = run_detectors(FlightLog.from_file(sample_ulog))
    for f in r.findings:
        assert f.id.startswith("F")
        assert f.t_start <= f.t_end
        assert f.severity in ("warn", "critical")
        assert np.isfinite(f.value)
    # VTOL log without CA_ROTOR_COUNT: imbalance must not produce servo-driven findings.
    assert not [f for f in r.findings if f.metric.endswith("imbalance")]

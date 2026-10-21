import numpy as np
import pandas as pd
import pytest

from skytrace.detectors.base import (
    active_intervals,
    armed_mask,
    intervals,
    rolling_time,
    threshold_findings,
)
from tests.factories import events, make_log, time_axis


def _iv(t, mask, min_d=0.0, gap=0.0):
    return intervals(
        np.asarray(t, float), np.asarray(mask, bool), min_duration_s=min_d, merge_gap_s=gap
    )


def test_intervals_basic_runs():
    t = [0, 1, 2, 3, 4, 5]
    assert _iv(t, [0, 1, 1, 0, 1, 0]) == [(1, 2), (4, 4)]
    assert _iv(t, [0] * 6) == []
    assert _iv(t, [1] * 6) == [(0, 5)]


def test_intervals_min_duration_drops_short_runs():
    t = [0, 1, 2, 3, 4, 5]
    assert _iv(t, [0, 1, 1, 0, 1, 0], min_d=1.0) == [(1, 2)]


def test_intervals_merge_gap():
    t = [0.0, 0.1, 0.2, 0.3, 0.4, 2.0, 2.1]
    mask = [1, 1, 0, 1, 1, 0, 1]
    assert _iv(t, mask, gap=0.0) == [(0, 1), (3, 4), (6, 6)]
    assert _iv(t, mask, gap=0.25) == [(0, 4), (6, 6)]
    assert _iv(t, mask, gap=5.0) == [(0, 6)]


def test_intervals_length_mismatch():
    with pytest.raises(ValueError):
        _iv([0, 1], [1])


def test_armed_mask_from_events():
    log = make_log(events=events((2.0, "arm", "armed"), (5.0, "disarm", "disarmed")))
    t = np.array([0.0, 1.9, 2.0, 4.9, 5.0, 9.0])
    assert armed_mask(log, t).tolist() == [False, False, True, True, False, False]


def test_armed_mask_log_starting_armed():
    log = make_log(events=events((5.0, "disarm", "disarmed")))
    assert armed_mask(log, np.array([0.0, 6.0])).tolist() == [True, False]


def test_armed_mask_without_events_is_all_true():
    log = make_log(events=events((1.0, "mode", "POSCTL")))
    assert armed_mask(log, np.array([0.0, 6.0])).all()


def test_rolling_time_max():
    t = pd.Series([0.0, 1.0, 2.0, 3.0])
    v = pd.Series([1.0, 5.0, 2.0, 2.0])
    np.testing.assert_allclose(rolling_time(v, t, 1.5, "max"), [1, 5, 5, 2])


def _describe(sev, v, thr, t0, t1):
    return f"{sev} {v} {thr}"


def test_threshold_findings_warn_and_critical():
    t = time_axis(10)
    values = np.zeros_like(t)
    values[(t >= 1) & (t <= 3)] = 5.0  # warn only
    values[(t >= 6) & (t <= 8)] = 5.0
    values[70] = 12.0  # one critical spike inside the second interval
    found = threshold_findings(
        detector="x",
        metric="m",
        t=t,
        values=values,
        active=np.ones_like(t, bool),
        warn=4.0,
        critical=10.0,
        direction="above",
        min_duration_s=1.0,
        merge_gap_s=0.0,
        describe=_describe,
    )
    assert [(f.severity, f.value, f.threshold) for f in found] == [
        ("warn", 5.0, 4.0),
        ("critical", 12.0, 10.0),
    ]
    assert found[0].t_start == pytest.approx(1.0)
    assert found[0].t_end == pytest.approx(3.0)
    assert found[1].summary == "critical 12.0 10.0"


def test_threshold_findings_below_ignores_nan_and_inactive():
    t = time_axis(10)
    values = np.full_like(t, 10.0)
    values[t < 4] = 1.0
    values[(t >= 6) & (t < 9)] = np.nan
    active = t >= 2
    found = threshold_findings(
        detector="x",
        metric="m",
        t=t,
        values=values,
        active=active,
        warn=5.0,
        critical=None,
        direction="below",
        min_duration_s=0.5,
        merge_gap_s=0.0,
        describe=_describe,
    )
    assert len(found) == 1
    assert found[0].t_start == pytest.approx(2.0)
    assert found[0].severity == "warn"


def _log_with_events(*rows):
    gps_t = np.arange(0.0, 60.0, 1.0)
    gps = pd.DataFrame(
        {
            "t": gps_t,
            **{
                c: np.zeros(len(gps_t))
                for c in ("fix_type", "satellites", "eph", "hdop", "lat", "lon", "alt")
            },
        }
    )
    return make_log(gps=gps, events=events(*rows))


def test_active_intervals_follow_arm_disarm():
    log = _log_with_events(
        (5.0, "arm", "armed"), (20.0, "disarm", "disarmed"), (30.0, "arm", "armed")
    )
    assert active_intervals(log, True) == [(5.0, 20.0), (30.0, 60.0)]  # open until log end
    assert active_intervals(log, False) == [(0.0, 60.0)]


def test_active_intervals_log_starting_armed_and_no_events():
    assert active_intervals(_log_with_events((10.0, "disarm", "disarmed")), True) == [(0.0, 10.0)]
    assert active_intervals(_log_with_events(), True) == [(0.0, 60.0)]


def test_airborne_and_flight_intervals():
    from skytrace.detectors.base import airborne_intervals, flight_intervals

    log = _log_with_events(
        (5.0, "arm", "armed"), (12.0, "takeoff", "t"), (40.0, "landing", "l"), (45.0, "disarm", "d")
    )
    assert airborne_intervals(log) == [(12.0, 40.0)]
    assert flight_intervals(log, True) == [(12.0, 40.0)]
    no_air = _log_with_events((5.0, "arm", "armed"), (45.0, "disarm", "d"))
    assert airborne_intervals(no_air) is None
    assert flight_intervals(no_air, True) == [(5.0, 45.0)]  # fallback: armed
    started_flying = _log_with_events((30.0, "landing", "l"))
    assert airborne_intervals(started_flying) == [(0.0, 30.0)]

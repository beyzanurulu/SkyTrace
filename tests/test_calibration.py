import math

import pytest

from skytrace.evaluation.calibration import binary_metrics, choose_thresholds, split_by_group


def _items():
    # (id, vehicle, positive)
    items = []
    for v in range(10):
        items.append((f"p{v}a", f"vp{v}", True))
        items.append((f"p{v}b", f"vp{v}", True))
    for v in range(12):
        items.append((f"n{v}", f"vn{v}", False))
    items.append(("mixed_pos", "vmixed", True))
    items.append(("mixed_neg", "vmixed", False))
    return items


def _split(items, **kw):
    return split_by_group(items, group=lambda i: i[1], label=lambda i: i[2], **kw)


def test_split_is_deterministic_and_group_aware():
    items = _items()
    a, b = _split(items), _split(items)
    assert a == b
    calib_groups = {i[1] for i in a.calibration}
    test_groups = {i[1] for i in a.test}
    assert calib_groups.isdisjoint(test_groups)  # no vehicle on both sides
    assert sorted(a.calibration + a.test) == sorted(items)


def test_split_is_stratified():
    s = _split(_items())
    # 11 positive groups (incl. mixed) -> 6 calib; 12 negative groups -> 6 calib
    pos_groups = {i[1] for i in s.calibration if i[1].startswith(("vp", "vmixed"))}
    neg_groups = {i[1] for i in s.calibration if i[1].startswith("vn")}
    assert len(pos_groups) == 6
    assert len(neg_groups) == 6


def test_split_salt_changes_assignment():
    items = _items()
    assert _split(items) != _split(items, salt="other")


def test_split_rejects_bad_fraction():
    with pytest.raises(ValueError):
        _split(_items(), calibration_fraction=1.0)


def test_choose_thresholds_percentiles():
    neg = [float(v) for v in range(1, 21)]  # 1..20
    pos = [30.0, 40.0, 50.0, float("nan")]
    c = choose_thresholds(neg, pos, warn_percentile=95, critical_percentile=50)
    assert c.warn == pytest.approx(19.05)
    assert c.critical == 40.0
    assert (c.n_negative, c.n_positive) == (20, 3)
    assert "P95 of 20 negative" in c.warn_rule
    assert "P50 of 3 positive" in c.critical_rule


def test_choose_thresholds_no_critical_when_positives_overlap():
    c = choose_thresholds([1.0, 2.0, 10.0], [2.0, 3.0])
    assert c.critical is None
    assert "<= warn" in c.critical_rule


def test_choose_thresholds_needs_negatives():
    with pytest.raises(ValueError):
        choose_thresholds([float("nan")], [1.0])


def test_binary_metrics():
    m = binary_metrics([(True, True), (True, False), (False, True), (False, False), (True, True)])
    assert (m.tp, m.fp, m.fn, m.tn) == (2, 1, 1, 1)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.false_positive_rate == pytest.approx(0.5)
    assert math.isnan(binary_metrics([]).precision)

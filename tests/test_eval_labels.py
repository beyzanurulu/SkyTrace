import importlib.util
from pathlib import Path

import pytest

from skytrace.detectors import Finding
from skytrace.evaluation.labels import (
    DetectorCounts,
    FaultLabel,
    LabelError,
    iou,
    load_labels,
    match_log,
    total_counts,
)
from tests.factories import override
from tests.test_dataflash import flight

ROOT = Path(__file__).resolve().parents[1]


def _run_eval_module():
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _f(det, t0, t1, severity="warn"):
    return Finding(det, severity, t0, t1, "m", 1.0, 0.5, "s")


def test_iou():
    assert iou((0, 10), (0, 10)) == 1.0
    assert iou((0, 10), (5, 15)) == pytest.approx(5 / 15)
    assert iou((0, 10), (11, 12)) == 0.0
    assert iou((3, 3), (0, 10)) == 0.0  # zero-length inside: intersection 0
    assert iou((3, 3), (3, 3)) == 1.0


def test_load_labels(tmp_path):
    p = tmp_path / "abc.yaml"
    p.write_text(
        "log: x.bin\nsource: sitl\nfaults:\n"
        '  - {type: gps, t_start: 10, t_end: 20.5, note: "failure gps off"}\n'
    )
    lb = load_labels(p)
    assert lb.log_id == "abc"
    assert lb.log == "x.bin"
    assert lb.faults == [FaultLabel("gps", 10.0, 20.5, "failure gps off")]


def test_load_labels_clean_flight(tmp_path):
    p = tmp_path / "clean.yaml"
    p.write_text("faults: []\n")
    assert load_labels(p).faults == []


@pytest.mark.parametrize(
    "fault",
    [
        "{type: wind, t_start: 1, t_end: 2}",
        "{type: gps, t_start: 5, t_end: 2}",
        "{type: gps, t_start: x, t_end: 2}",
    ],
)
def test_load_labels_rejects(tmp_path, fault):
    p = tmp_path / "bad.yaml"
    p.write_text(f"faults:\n  - {fault}\n")
    with pytest.raises(LabelError):
        load_labels(p)


def test_match_log_counts():
    labels = [FaultLabel("gps", 10, 20), FaultLabel("gps", 100, 110), FaultLabel("battery", 50, 60)]
    findings = [
        _f("gps", 11, 19),  # matches first gps label
        _f("gps", 12, 20),  # second finding on the same fault: also correct
        _f("gps", 200, 210),  # false positive
        _f("battery", 59, 70),  # IoU 1/20 < 0.3: false positive, battery label missed
        _f("motors", 0, 5, severity="info"),  # below min severity: ignored
    ]
    m = match_log("log", labels, findings, iou_threshold=0.3)
    gps = m.counts["gps"]
    assert (gps.labels, gps.labels_detected, gps.findings, gps.findings_correct) == (2, 1, 3, 2)
    assert gps.precision == pytest.approx(2 / 3)
    assert gps.recall == pytest.approx(0.5)
    assert m.counts["battery"].recall == 0.0
    assert m.counts["motors"].findings == 0
    assert [lb.t_start for lb in m.missed] == [100, 50]
    assert len(m.false_positives) == 2


def test_detector_counts_undefined():
    c = DetectorCounts()
    assert c.precision is None and c.recall is None and c.f1 is None
    c = DetectorCounts(labels=2, labels_detected=0, findings=1, findings_correct=0)
    assert c.f1 == 0.0


def test_total_counts_sums_logs():
    a = match_log("a", [FaultLabel("gps", 0, 10)], [_f("gps", 0, 10)], iou_threshold=0.3)
    b = match_log("b", [FaultLabel("gps", 0, 10)], [], iou_threshold=0.3)
    t = total_counts([a, b])["gps"]
    assert (t.labels, t.labels_detected, t.findings_correct) == (2, 1, 1)


def test_run_eval_end_to_end(tmp_path):
    logs, labels, out = tmp_path / "raw", tmp_path / "labels", tmp_path / "res" / "eval.md"
    logs.mkdir()
    labels.mkdir()
    flight(gps_loss=(20.0, 30.0)).write(logs / "gpsfail.bin")
    flight().write(logs / "clean.bin")
    (labels / "gpsfail.yaml").write_text("faults:\n  - {type: gps, t_start: 20, t_end: 30}\n")
    (labels / "clean.yaml").write_text("faults: []\n")
    (labels / "orphan.yaml").write_text("faults: []\n")
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("detectors:\n  battery:\n    cells: 4\n")

    mod = _run_eval_module()
    matches, skipped = mod.evaluate(labels, logs, override(battery={"cells": 4}), 0.3, "warn")
    assert [m.log_id for m in matches] == ["clean", "gpsfail"]
    assert skipped == [f"orphan.yaml: log not found in {logs}"]
    gps = total_counts(matches)["gps"]
    assert gps.recall == 1.0
    assert gps.precision == 1.0

    rc = mod.main(
        ["--labels", str(labels), "--logs", str(logs), "--out", str(out), "--config", str(cfg_path)]
    )
    assert rc == 0
    text = out.read_text()
    assert "| gps | 1 | 1 |" in text
    assert "orphan.yaml" in text

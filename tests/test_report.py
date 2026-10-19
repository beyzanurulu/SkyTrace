import json
import re

import pytest

from skytrace import FlightLog
from skytrace.detectors import DetectionResult, Finding, run_detectors
from skytrace.report import render_html, report_dict, write_json
from skytrace.report.evidence import decimate
from tests.factories import events, make_log


@pytest.fixture
def analyzed(sample_ulog):
    log = FlightLog.from_file(sample_ulog)
    return log, run_detectors(log)


def test_html_is_offline_and_has_evidence(analyzed):
    log, result = analyzed
    html = render_html(log, result)
    assert not re.search(r"<script[^>]+src=", html)
    assert len(re.findall(r"<script", html)) >= 2  # plotly bundle inlined
    assert result.findings
    for f in result.findings:
        assert f.id in html
        assert f"plot-{f.id}" in html


def test_log_text_cannot_break_out_of_script():
    log = make_log(events=events((0.0, "mode", "</script><b>x</b>")))
    html = render_html(log, DetectionResult(findings=[]))
    assert "</script><b>" not in html


def test_json_report_is_strict(analyzed, tmp_path):
    log, result = analyzed
    path = write_json(log, result, tmp_path / "r.json")
    data = json.loads(path.read_text())
    assert data["summary"]["findings"] == len(result.findings)
    assert [f["id"] for f in data["findings"]] == [f.id for f in result.findings]


def test_json_nan_becomes_null():
    log = make_log()
    f = Finding("gps", "warn", 0.0, 1.0, "eph", float("nan"), 3.0, "x", id="F001")
    assert report_dict(log, DetectionResult([f]))["findings"][0]["value"] is None


def test_decimate_keeps_peak():
    import numpy as np

    t = np.arange(10_000, dtype=float)
    y = np.zeros_like(t)
    y[5_123] = 9.0
    td, yd = decimate(t, y, 100)
    assert len(td) <= 100
    assert yd.max() == 9.0

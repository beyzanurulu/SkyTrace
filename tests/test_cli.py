import json

from typer.testing import CliRunner

from skytrace import __version__
from skytrace.cli import app

runner = CliRunner()


def test_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert __version__ in res.output


def test_analyze_html(sample_ulog, tmp_path):
    out = tmp_path / "report.html"
    res = runner.invoke(app, ["analyze", str(sample_ulog), "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert out.read_text().startswith("<!")
    assert "F001" in res.output


def test_analyze_json(sample_ulog, tmp_path):
    out = tmp_path / "report.json"
    res = runner.invoke(app, ["analyze", str(sample_ulog), "-f", "json", "-o", str(out), "-q"])
    assert res.exit_code == 0, res.output
    assert json.loads(out.read_text())["schema_version"] == 1


def test_unknown_detector(sample_ulog, tmp_path):
    res = runner.invoke(
        app, ["analyze", str(sample_ulog), "--only", "nope", "-o", str(tmp_path / "r.html")]
    )
    assert res.exit_code == 2

from pathlib import Path

import pytest

from skytrace.config import ConfigError, load_config


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_defaults_load():
    cfg = load_config()
    assert cfg.parser.merge_tolerance_s == 0.5
    assert cfg.parser.vibration_window_s == 0.5
    assert cfg.parser.motors.use_log_params is True
    assert cfg.parser.motors.pwm_min_us == 1000
    assert cfg.parser.motors.pwm_max_us == 2000
    assert cfg.parser.motors.count is None


def test_partial_override_keeps_other_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, "parser:\n  motors:\n    count: 4\n"))
    assert cfg.parser.motors.count == 4
    assert cfg.parser.motors.pwm_max_us == 2000
    assert cfg.parser.merge_tolerance_s == 0.5


def test_empty_file_is_defaults(tmp_path):
    assert load_config(_write(tmp_path, "")) == load_config()


@pytest.mark.parametrize(
    "text",
    [
        "parser:\n  typo_key: 1\n",
        "unknown: {}\n",
        "parser: 3\n",
        "- a\n- b\n",
        "parser:\n  merge_tolerance_s: -1\n",
        "parser:\n  merge_tolerance_s: fast\n",
        "parser:\n  motors:\n    count: 0\n",
        "parser:\n  motors:\n    count: true\n",
        "parser:\n  motors:\n    use_log_params: 1\n",
        "parser:\n  motors:\n    pwm_min_us: 2000\n    pwm_max_us: 1000\n",
        "detectors:\n  vibration:\n    ardupilot_vibe:\n      metric_critical: 10\n",  # < warn
        "detectors:\n  vibration:\n    px4_imu_status:\n      metric_critical: 5\n",  # no warn
        "detectors:\n  vibration:\n    accel_std_critical: 10\n",  # removed key
        "detectors:\n  battery:\n    cell_voltage_critical: 3.8\n",  # below-check reversed
        "detectors:\n  battery:\n    remaining_warn: 15\n",  # percent instead of fraction
        "detectors:\n  motors:\n    saturation_level: 1.5\n",
        "detectors:\n  gps:\n    min_satellites: 5.5\n",  # must be an integer
        "detectors:\n  merge_gap_s: -0.1\n",
    ],
)
def test_invalid_config_rejected(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, text))


def test_zero_allowed_only_where_marked(tmp_path):
    cfg = load_config(_write(tmp_path, "detectors:\n  merge_gap_s: 0\n"))
    assert cfg.detectors.merge_gap_s == 0.0
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "detectors:\n  attitude:\n    min_duration_s: 0\n"))


def test_detector_overrides(tmp_path):
    cfg = load_config(_write(tmp_path, "detectors:\n  battery:\n    cells: 6\n"))
    assert cfg.detectors.battery.cells == 6
    assert cfg.detectors.battery.cell_voltage_warn == 3.5


def test_vibration_thresholds_per_source(tmp_path):
    cfg = load_config()
    assert cfg.detectors.vibration.for_source("px4_imu_status").metric_warn is None
    assert cfg.detectors.vibration.for_source("ardupilot_vibe").metric_warn == 30.0
    with pytest.raises(KeyError):
        cfg.detectors.vibration.for_source("unknown")
    text = "detectors:\n  vibration:\n    px4_imu_status:\n      metric_warn: 4.5\n"
    custom = load_config(_write(tmp_path, text))
    assert custom.detectors.vibration.px4_imu_status.metric_warn == 4.5
    assert custom.detectors.vibration.ardupilot_vibe.metric_warn == 30.0

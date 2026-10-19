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
    ],
)
def test_invalid_config_rejected(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, text))

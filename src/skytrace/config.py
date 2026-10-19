"""Configuration loading.

All tunable values (thresholds, tolerances, fallbacks) live in ``defaults.yaml``
and are documented in ``docs/thresholds.md``. A user YAML file overrides only
the keys it sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a configuration file is malformed."""


@dataclass(frozen=True)
class MotorConfig:
    use_log_params: bool
    pwm_min_us: float
    pwm_max_us: float
    count: int | None


@dataclass(frozen=True)
class ParserConfig:
    merge_tolerance_s: float
    vibration_window_s: float
    motors: MotorConfig


@dataclass(frozen=True)
class SkyTraceConfig:
    parser: ParserConfig


def _read_defaults() -> dict[str, Any]:
    text = resources.files("skytrace").joinpath("defaults.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError("defaults.yaml must be a mapping")
    return data


def _merge(base: dict[str, Any], override: dict[str, Any], path: str = "") -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base``, rejecting unknown keys."""
    merged = dict(base)
    for key, value in override.items():
        full = f"{path}.{key}" if path else key
        if key not in base:
            raise ConfigError(f"unknown config key: {full}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f"config key {full} must be a mapping")
            merged[key] = _merge(base[key], value, full)
        else:
            merged[key] = value
    return merged


def _number(data: dict[str, Any], key: str, path: str, *, positive: bool = True) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{path}.{key} must be a number, got {value!r}")
    if positive and value <= 0:
        raise ConfigError(f"{path}.{key} must be > 0, got {value!r}")
    return float(value)


def _build(data: dict[str, Any]) -> SkyTraceConfig:
    p = data["parser"]
    m = p["motors"]

    if not isinstance(m["use_log_params"], bool):
        raise ConfigError("parser.motors.use_log_params must be a boolean")
    count = m["count"]
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 1):
        raise ConfigError(f"parser.motors.count must be null or a positive integer, got {count!r}")

    motors = MotorConfig(
        use_log_params=m["use_log_params"],
        pwm_min_us=_number(m, "pwm_min_us", "parser.motors"),
        pwm_max_us=_number(m, "pwm_max_us", "parser.motors"),
        count=count,
    )
    if motors.pwm_max_us <= motors.pwm_min_us:
        raise ConfigError("parser.motors.pwm_max_us must be greater than pwm_min_us")

    parser = ParserConfig(
        merge_tolerance_s=_number(p, "merge_tolerance_s", "parser"),
        vibration_window_s=_number(p, "vibration_window_s", "parser"),
        motors=motors,
    )
    return SkyTraceConfig(parser=parser)


def load_config(path: str | Path | None = None) -> SkyTraceConfig:
    """Load the default config, optionally overridden by a user YAML file."""
    data = _read_defaults()
    if path is not None:
        user = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(user, dict):
            raise ConfigError(f"{path}: top level must be a mapping")
        data = _merge(data, user)
    return _build(data)

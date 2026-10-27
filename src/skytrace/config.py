"""Configuration loading.

All tunable values (thresholds, tolerances, fallbacks) live in ``defaults.yaml``
and are documented in ``docs/thresholds.md``. A user YAML file overrides only
the keys it sets.

The YAML tree maps 1:1 onto the frozen dataclasses below. Numbers must be > 0
unless the field is marked with ``_ZERO_OK``.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar

import yaml


class ConfigError(ValueError):
    """Raised when a configuration file is malformed."""


_ZERO_OK: dict[str, Any] = {"zero_ok": True}


@dataclass(frozen=True)
class MotorConfig:
    use_log_params: bool
    pwm_min_us: float
    pwm_max_us: float
    count: int | None


@dataclass(frozen=True)
class ParserConfig:
    merge_tolerance_s: float
    status_tolerance_s: float
    vibration_window_s: float
    motors: MotorConfig


@dataclass(frozen=True)
class VibrationSourceThresholds:
    """Thresholds for one vibration metric source. ``None`` = not calibrated: check skipped."""

    metric_warn: float | None
    metric_critical: float | None
    clip_critical_count: int


@dataclass(frozen=True)
class VibrationDetectorConfig:
    min_duration_s: float
    clip_merge_gap_s: float
    px4_imu_status: VibrationSourceThresholds
    ardupilot_vibe: VibrationSourceThresholds

    def for_source(self, source: str) -> VibrationSourceThresholds:
        """Thresholds for ``LogMetadata.vib_metric_source``; never falls back to another source."""
        if source not in ("px4_imu_status", "ardupilot_vibe"):
            raise KeyError(f"unknown vibration metric source: {source}")
        result: VibrationSourceThresholds = getattr(self, source)
        return result


@dataclass(frozen=True)
class GpsDetectorConfig:
    min_fix_type: int
    min_satellites: int
    max_eph_m: float
    max_hdop: float
    min_duration_s: float
    max_data_gap_s: float


@dataclass(frozen=True)
class BatteryDetectorConfig:
    cells: int | None
    cell_voltage_warn: float
    cell_voltage_critical: float
    sag_window_s: float
    sag_warn_v_per_cell: float
    sag_critical_v_per_cell: float
    sag_min_duration_s: float = field(metadata=_ZERO_OK)
    remaining_warn: float
    remaining_critical: float
    min_duration_s: float


@dataclass(frozen=True)
class AttitudeDetectorConfig:
    error_warn_deg: float
    error_critical_deg: float
    min_duration_s: float


@dataclass(frozen=True)
class MotorDetectorConfig:
    saturation_level: float
    saturation_warn_s: float
    saturation_critical_s: float
    imbalance_window_s: float
    imbalance_warn: float
    imbalance_critical: float
    imbalance_min_duration_s: float


@dataclass(frozen=True)
class DetectorsConfig:
    only_when_armed: bool
    merge_gap_s: float = field(metadata=_ZERO_OK)
    vibration: VibrationDetectorConfig
    gps: GpsDetectorConfig
    battery: BatteryDetectorConfig
    attitude: AttitudeDetectorConfig
    motors: MotorDetectorConfig


@dataclass(frozen=True)
class ReportConfig:
    evidence_padding_s: float
    max_points_per_trace: int


@dataclass(frozen=True)
class AnomalySignalsConfig:
    """Signals for ML anomaly detection, each with its noise floor (signal units).

    The robust z-score divides by max(1.4826 * MAD, floor), so a nearly constant
    signal cannot turn measurement noise into a huge score. ``None`` disables it.
    """

    roll_error_deg: float | None
    pitch_error_deg: float | None
    accel_vib_metric: float | None
    battery_voltage: float | None
    battery_current: float | None
    motor_mean: float | None
    motor_spread: float | None
    vz: float | None
    gps_eph: float | None


@dataclass(frozen=True)
class ZScoreConfig:
    window_s: float
    info: float
    warn: float
    min_duration_s: float


@dataclass(frozen=True)
class IsolationForestConfig:
    enabled: bool
    window_s: float
    step_s: float
    baseline_s: float
    hf_cutoff_hz: float
    n_estimators: int
    contamination: float
    random_state: int = field(metadata=_ZERO_OK)
    min_windows: int
    min_feature_z: float
    warn_feature_z: float
    top_features: int


@dataclass(frozen=True)
class AnomalyConfig:
    resample_hz: float
    max_fill_s: float = field(metadata=_ZERO_OK)
    trim_s: float = field(metadata=_ZERO_OK)
    signals: AnomalySignalsConfig
    zscore: ZScoreConfig
    iforest: IsolationForestConfig


@dataclass(frozen=True)
class AgentConfig:
    """Q&A agent (skytrace.agent). The model is any LiteLLM model string."""

    model: str
    api_base: str | None
    temperature: float = field(metadata=_ZERO_OK)
    timeout_s: float
    max_tool_rounds: int
    max_series_points: int
    number_rel_tol: float = field(metadata=_ZERO_OK)
    prefetch: bool
    prefetch_max_findings: int
    docs_prefetch_terms: list[str]  # question contains one -> search_docs runs up front
    docs_prefetch_min_score: float  # ... and is kept only if the best passage scores this


@dataclass(frozen=True)
class DocSourceConfig:
    """One documentation repository (sparse, shallow git checkout of text files)."""

    repo: str
    ref: str
    include: list[str]  # git sparse-checkout patterns (no-cone)
    url_base: str  # public docs URL the file paths map to


@dataclass(frozen=True)
class RagConfig:
    """Documentation search (search_docs): local embeddings + Qdrant local mode."""

    embedding_model: str
    api_base: str | None
    docs_dir: str
    index_dir: str
    keywords: list[str]  # a file is indexed if its path or title matches one of these
    chunk_chars: int
    top_k: int
    excerpt_chars: int
    batch_size: int
    px4: DocSourceConfig
    ardupilot: DocSourceConfig


@dataclass(frozen=True)
class DemoConfig:
    """Public demo (Hugging Face Space): sample logs, chat only on them."""

    enabled: bool
    samples_dir: str  # sample logs + samples.yaml (title, description per file)
    chat_on_uploads: bool  # demo: False = chat only on the sample logs
    local_install_url: str  # shown where chat is not offered


@dataclass(frozen=True)
class OfflineConfig:
    """SKYTRACE_MODE=offline (skytrace.offline)."""

    allowed_hosts: list[str]  # besides loopback; the model server must be one of these


@dataclass(frozen=True)
class ApiConfig:
    """Web API + UI (skytrace serve)."""

    host: str
    port: int
    storage_dir: str  # uploaded logs, one folder per analysis
    max_upload_mb: float
    retention_hours: float  # uploads older than this are deleted
    cleanup_interval_s: float
    max_loaded: int  # parsed logs / chat sessions kept in memory


@dataclass(frozen=True)
class SkyTraceConfig:
    parser: ParserConfig
    detectors: DetectorsConfig
    report: ReportConfig
    anomaly: AnomalyConfig
    agent: AgentConfig
    rag: RagConfig
    api: ApiConfig
    offline: OfflineConfig
    demo: DemoConfig


T = TypeVar("T")


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


def _convert(value: object, tp: object, path: str, zero_ok: bool) -> object:
    """Validate ``value`` against the annotation ``tp`` and convert it."""
    args = typing.get_args(tp)
    if isinstance(tp, types.UnionType) and type(None) in args:
        if value is None:
            return None
        (inner,) = (a for a in args if a is not type(None))
        return _convert(value, inner, path, zero_ok)
    if dataclasses.is_dataclass(tp):
        if not isinstance(value, dict):
            raise ConfigError(f"{path} must be a mapping")
        return _build(tp, value, path)  # type: ignore[arg-type]
    if tp is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{path} must be a boolean, got {value!r}")
        return value
    if tp is str:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{path} must be a non-empty string, got {value!r}")
        return value
    if typing.get_origin(tp) is list:
        (item,) = args
        if not isinstance(value, list) or not value:
            raise ConfigError(f"{path} must be a non-empty list, got {value!r}")
        return [_convert(v, item, f"{path}[{i}]", zero_ok) for i, v in enumerate(value)]
    if tp in (int, float):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{path} must be a number, got {value!r}")
        if tp is int and not isinstance(value, int):
            raise ConfigError(f"{path} must be an integer, got {value!r}")
        if value < 0 or (value == 0 and not zero_ok):
            raise ConfigError(f"{path} must be {'>= 0' if zero_ok else '> 0'}, got {value!r}")
        return tp(value)
    raise TypeError(f"unsupported config annotation {tp!r} at {path}")


def _build(cls: type[T], data: dict[str, Any], path: str = "") -> T:
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        full = f"{path}.{f.name}" if path else f.name
        if f.name not in data:
            raise ConfigError(f"missing config key: {full}")
        kwargs[f.name] = _convert(
            data[f.name], hints[f.name], full, f.metadata.get("zero_ok", False)
        )
    extra = set(data) - set(kwargs)
    if extra:
        raise ConfigError(f"unknown config keys under {path or '<root>'}: {sorted(extra)}")
    return cls(**kwargs)


def _check(cfg: SkyTraceConfig) -> None:
    """Cross-field constraints that a per-field type check cannot express."""
    a = cfg.anomaly
    if a.zscore.warn < a.zscore.info:
        raise ConfigError("anomaly.zscore: warn must be >= info")
    if a.iforest.warn_feature_z < a.iforest.min_feature_z:
        raise ConfigError("anomaly.iforest: warn_feature_z must be >= min_feature_z")
    if not 0 < a.iforest.contamination <= 0.5:
        raise ConfigError("anomaly.iforest.contamination must be in (0, 0.5]")
    if a.iforest.step_s > a.iforest.window_s:
        raise ConfigError("anomaly.iforest.step_s must be <= window_s")
    if a.iforest.hf_cutoff_hz >= a.resample_hz / 2:
        raise ConfigError("anomaly.iforest.hf_cutoff_hz must be below resample_hz / 2 (Nyquist)")
    m = cfg.parser.motors
    if m.pwm_max_us <= m.pwm_min_us:
        raise ConfigError("parser.motors.pwm_max_us must be greater than pwm_min_us")

    d = cfg.detectors
    for src in ("px4_imu_status", "ardupilot_vibe"):
        v = d.vibration.for_source(src)
        if v.metric_critical is not None and v.metric_warn is None:
            raise ConfigError(f"detectors.vibration.{src}: metric_critical needs metric_warn")
        if (
            v.metric_warn is not None
            and v.metric_critical is not None
            and v.metric_critical < v.metric_warn
        ):
            raise ConfigError(f"detectors.vibration.{src}: critical must be >= warn")
    pairs = [
        (
            "battery.sag_*_v_per_cell",
            d.battery.sag_warn_v_per_cell,
            d.battery.sag_critical_v_per_cell,
        ),
        ("attitude.error_*_deg", d.attitude.error_warn_deg, d.attitude.error_critical_deg),
        ("motors.saturation_*_s", d.motors.saturation_warn_s, d.motors.saturation_critical_s),
        ("motors.imbalance", d.motors.imbalance_warn, d.motors.imbalance_critical),
    ]
    for name, warn, critical in pairs:
        if critical < warn:
            raise ConfigError(f"detectors.{name}: critical must be >= warn")
    # "Below" thresholds: critical is the lower value.
    low_pairs = [
        ("battery.cell_voltage", d.battery.cell_voltage_warn, d.battery.cell_voltage_critical),
        ("battery.remaining", d.battery.remaining_warn, d.battery.remaining_critical),
    ]
    for name, warn, critical in low_pairs:
        if critical > warn:
            raise ConfigError(f"detectors.{name}: critical must be <= warn")
    if d.battery.remaining_warn > 1:
        raise ConfigError("detectors.battery.remaining_warn must be a fraction in 0..1")
    if not 0 < d.motors.saturation_level <= 1:
        raise ConfigError("detectors.motors.saturation_level must be in (0, 1]")


def load_config(path: str | Path | None = None) -> SkyTraceConfig:
    """Load the default config, optionally overridden by a user YAML file."""
    data = _read_defaults()
    if path is not None:
        user = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(user, dict):
            raise ConfigError(f"{path}: top level must be a mapping")
        data = _merge(data, user)
    cfg = _build(SkyTraceConfig, data)
    _check(cfg)
    return cfg


LOCAL_MODEL_PREFIXES = ("ollama/", "ollama_chat/")


def with_model(cfg: SkyTraceConfig, model: str) -> SkyTraceConfig:
    """``cfg`` with another chat model (``--model``).

    ``agent.api_base`` is the Ollama server of the default config: a cloud model
    (``gemini/...``) must not be sent there, so it gets the provider's default.
    """
    api_base = cfg.agent.api_base if model.startswith(LOCAL_MODEL_PREFIXES) else None
    return replace(cfg, agent=replace(cfg.agent, model=model, api_base=api_base))

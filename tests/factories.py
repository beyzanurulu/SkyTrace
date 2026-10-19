"""Builders for synthetic FlightLogs used by detector tests."""

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from skytrace.config import SkyTraceConfig, load_config
from skytrace.parsers.schema import TABLE_NAMES, FlightLog, LogMetadata, empty_table

RATE_HZ = 10.0


def time_axis(duration_s: float, rate_hz: float = RATE_HZ) -> np.ndarray:
    return np.arange(0.0, duration_s, 1.0 / rate_hz)


def step(t: np.ndarray, base: float, value: float, t0: float, t1: float) -> np.ndarray:
    """``base`` everywhere, ``value`` for t0 <= t <= t1."""
    out = np.full(len(t), base, dtype=np.float64)
    out[(t >= t0) & (t <= t1)] = value
    return out


def events(*rows: tuple[float, str, str]) -> pd.DataFrame:
    if not rows:
        return empty_table("events")
    return pd.DataFrame(rows, columns=["t", "kind", "message"])


def make_log(**tables: Any) -> FlightLog:
    """FlightLog with empty tables except the ones given. ``metadata=`` kwargs are merged."""
    meta_kwargs = tables.pop("metadata", {})
    full: dict[str, Any] = {name: empty_table(name) for name in TABLE_NAMES}
    full.update(tables)
    meta = LogMetadata(format="px4_ulog", source="synthetic", duration_s=60.0, **meta_kwargs)
    return FlightLog(metadata=meta, **full)


def override(**sections: dict[str, Any]) -> SkyTraceConfig:
    """Default config with ``detectors.<section>`` fields replaced.

    Example: ``override(battery={"cells": 4}, detectors={"only_when_armed": False})``.
    """

    cfg = load_config()
    det = cfg.detectors
    for name, fields in sections.items():
        if name == "detectors":
            det = replace(det, **fields)
        else:
            det = replace(det, **{name: replace(getattr(det, name), **fields)})
    return replace(cfg, detectors=det)

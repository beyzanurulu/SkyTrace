"""Machine-readable analysis output."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from skytrace import __version__
from skytrace.detectors import DetectionResult
from skytrace.parsers.schema import FlightLog

SCHEMA_VERSION = 1


def _clean(value: Any) -> Any:  # noqa: ANN401 (recursive JSON value)
    """NaN / inf -> None so the output is strict JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def report_dict(log: FlightLog, result: DetectionResult) -> dict[str, Any]:
    severities = [f.severity for f in result.findings]
    return _clean(
        {
            "schema_version": SCHEMA_VERSION,
            "skytrace_version": __version__,
            "metadata": asdict(log.metadata),
            "summary": {
                "findings": len(result.findings),
                "critical": severities.count("critical"),
                "warn": severities.count("warn"),
                "info": severities.count("info"),
            },
            "findings": [asdict(f) for f in result.findings],
            "notes": list(result.notes),
            "parser_warnings": list(log.warnings),
        }
    )


def write_json(log: FlightLog, result: DetectionResult, path: str | Path) -> Path:
    out = Path(path)
    out.write_text(json.dumps(report_dict(log, result), indent=2, allow_nan=False), "utf-8")
    return out

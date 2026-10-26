"""Tools the Q&A agent may call. Every number the agent can cite comes from here.

Each tool is plain Python over one analysed log and returns a JSON-serialisable
dict. Unit conversions the model would otherwise do itself (radians -> degrees,
fraction -> percent) happen here, so the model never has to produce a number.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from skytrace.anomaly.ml import SIGNAL_LABELS, signal_series
from skytrace.config import SkyTraceConfig
from skytrace.detectors import DetectionResult
from skytrace.detectors.base import log_end
from skytrace.parsers.schema import TABLE_COLUMNS, TABLE_NAMES, FlightLog
from skytrace.report.evidence import decimate

# Angles are stored in radians; the agent sees degrees (no conversion by the model).
DEGREE_COLUMNS: Final = {
    "attitude": ("roll", "pitch", "yaw", "roll_sp", "pitch_sp", "yaw_sp"),
}
UNITS: Final[dict[str, dict[str, str]]] = {
    "attitude": {c: "deg" for c in DEGREE_COLUMNS["attitude"]},
    "gps": {"eph": "m", "hdop": "", "lat": "deg", "lon": "deg", "alt": "m MSL"},
    "battery": {"voltage": "V", "current": "A", "remaining": "fraction 0-1"},
    "vibration": {"vib_x": "m/s^2", "vib_y": "m/s^2", "vib_z": "m/s^2"},
    "position": {c: "m" for c in ("x", "y", "z", "z_sp")} | {c: "m/s" for c in ("vx", "vy", "vz")},
}
SIGNALS_TABLE: Final = "signals"  # derived series (tracking error, motor mean, ...)
AGGREGATES: Final = ("stats", "samples")


class ToolError(ValueError):
    """Bad tool arguments; the message is returned to the model so it can retry."""


def _num(x: float) -> float | None:
    """JSON-safe, compact number (6 significant digits); NaN / inf -> None."""
    if x is None or not math.isfinite(x):
        return None
    return float(f"{x:.6g}")


@dataclass
class AgentContext:
    log: FlightLog
    result: DetectionResult
    config: SkyTraceConfig
    plot_dir: Path = field(default_factory=lambda: Path("skytrace_plots"))


# --- tools ----------------------------------------------------------------------


def get_flight_summary(ctx: AgentContext) -> dict[str, Any]:
    m = ctx.log.metadata
    ev = ctx.log.events
    modes = ev[ev["kind"] == "mode"]
    sev = [f.severity for f in ctx.result.findings]
    return {
        "metadata": {k: (_num(v) if isinstance(v, float) else v) for k, v in asdict(m).items()},
        "duration_s": _num(m.duration_s),
        "log_end_s": _num(log_end(ctx.log)),
        "motor_count": ctx.log.motor_count,
        "modes": [
            {"t": _num(float(t)), "mode": str(name)}
            for t, name in zip(modes["t"], modes["message"], strict=True)
        ],
        "findings": {
            "total": len(sev),
            "critical": sev.count("critical"),
            "warn": sev.count("warn"),
            "info": sev.count("info"),
        },
        "skipped_checks": list(ctx.result.notes),
        "parser_warnings": list(ctx.log.warnings),
    }


def list_findings(
    ctx: AgentContext, severity: str | None = None, detector: str | None = None
) -> dict[str, Any]:
    found = [
        f
        for f in ctx.result.findings
        if (severity is None or f.severity == severity)
        and (detector is None or f.detector == detector)
    ]
    return {
        "count": len(found),
        "findings": [
            {
                "id": f.id,
                "detector": f.detector,
                "severity": f.severity,
                "t_start_s": _num(f.t_start),
                "t_end_s": _num(f.t_end),
                "duration_s": _num(f.t_end - f.t_start),
                "metric": f.metric,
                "value": _num(f.value),
                "threshold": _num(f.threshold),
                "summary": f.summary,
            }
            for f in found
        ],
    }


def _column_name(table: str, column: str) -> str:
    """Small models often write "battery:voltage" / "battery.voltage": drop the table."""
    for sep in (":", "."):
        column = column.removeprefix(f"{table}{sep}")
    return column


def _series(ctx: AgentContext, table: str, column: str) -> tuple[np.ndarray, np.ndarray, str]:
    column = _column_name(table, column)
    if table == SIGNALS_TABLE:
        if column not in SIGNAL_LABELS:
            raise ToolError(f"unknown signal {column!r}; available: {sorted(SIGNAL_LABELS)}")
        s = signal_series(ctx.log, column)
        if s is None:
            raise ToolError(f"signal {column!r} is not available in this log")
        return s[0], s[1], SIGNAL_LABELS[column]
    if table not in TABLE_NAMES or table == "events":
        raise ToolError(f"unknown table {table!r}; use one of {[*TABLE_NAMES[:-1], SIGNALS_TABLE]}")
    df = ctx.log.table(table)
    if column == "t" or column not in df.columns:
        cols = [c for c in df.columns if c != "t"]
        raise ToolError(f"table {table!r} has no column {column!r}; columns: {cols}")
    t = df["t"].to_numpy(dtype=np.float64)
    y = df[column].to_numpy(dtype=np.float64)
    if column in DEGREE_COLUMNS.get(table, ()):
        y = np.degrees(y)
    return t, y, UNITS.get(table, {}).get(column, "")


def query_series(
    ctx: AgentContext,
    table: str,
    columns: list[str],
    t_start: float | None = None,
    t_end: float | None = None,
    agg: str = "stats",
) -> dict[str, Any]:
    """Statistics (default) or a reduced sample list of columns in a time range."""
    if agg not in AGGREGATES:
        raise ToolError(f"agg must be one of {AGGREGATES}")
    if not columns:
        raise ToolError("give at least one column")
    out: dict[str, Any] = {"table": table, "t_start_s": t_start, "t_end_s": t_end, "columns": {}}
    for column in (_column_name(table, c) for c in columns):
        t, y, unit = _series(ctx, table, column)
        mask = np.ones(len(t), dtype=bool)
        if t_start is not None:
            mask &= t >= t_start
        if t_end is not None:
            mask &= t <= t_end
        t, y = t[mask], y[mask]
        ok = np.isfinite(y)
        entry: dict[str, Any] = {"unit": unit, "n": int(ok.sum())}
        if not ok.any():
            entry["note"] = "no valid samples in this range"
        elif agg == "stats":
            k_min, k_max = int(np.nanargmin(y)), int(np.nanargmax(y))
            entry |= {
                "mean": _num(float(np.nanmean(y))),
                "min": _num(float(y[k_min])),
                "t_min_s": _num(float(t[k_min])),
                "max": _num(float(y[k_max])),
                "t_max_s": _num(float(t[k_max])),
                "std": _num(float(np.nanstd(y))),
                "first": _num(float(y[ok][0])),
                "last": _num(float(y[ok][-1])),
            }
        else:
            ts, ys = decimate(t[ok], y[ok], ctx.config.agent.max_series_points)
            entry["samples"] = [
                [_num(float(a)), _num(float(b))] for a, b in zip(ts, ys, strict=True)
            ]
        out["columns"][column] = entry
    return out


def get_events(
    ctx: AgentContext,
    t_start: float | None = None,
    t_end: float | None = None,
    kinds: list[str] | None = None,
) -> dict[str, Any]:
    ev = ctx.log.events
    if t_start is not None:
        ev = ev[ev["t"] >= t_start]
    if t_end is not None:
        ev = ev[ev["t"] <= t_end]
    if kinds:
        ev = ev[ev["kind"].isin(kinds)]
    return {
        "count": len(ev),
        "events": [
            {"t_s": _num(float(t)), "kind": str(k), "message": str(m)}
            for t, k, m in zip(ev["t"], ev["kind"], ev["message"], strict=True)
        ],
    }


def make_plot(
    ctx: AgentContext,
    table: str,
    columns: list[str],
    t_start: float | None = None,
    t_end: float | None = None,
) -> dict[str, Any]:
    """Write a small standalone HTML plot and return its path."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for column in (_column_name(table, c) for c in columns):
        t, y, unit = _series(ctx, table, column)
        mask = np.ones(len(t), dtype=bool)
        if t_start is not None:
            mask &= t >= t_start
        if t_end is not None:
            mask &= t <= t_end
        ts, ys = decimate(t[mask], y[mask], ctx.config.report.max_points_per_trace)
        label = f"{column} ({unit})" if unit else column
        y_plot = [float(v) if np.isfinite(v) else None for v in ys]  # None = gap in the line
        fig.add_scatter(x=ts, y=y_plot, mode="lines", name=label)
    fig.update_layout(
        title=f"{table}: {', '.join(columns)}", xaxis_title="time since log start (s)"
    )
    ctx.plot_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{table}_{'_'.join(columns)}_{t_start or 0:g}-{t_end if t_end is not None else 'end'}"
    path = ctx.plot_dir / f"{stem}.html".replace(" ", "")
    fig.write_html(path, include_plotlyjs=True, full_html=True)
    return {"path": str(path.resolve())}


def search_docs(ctx: AgentContext, query: str) -> dict[str, Any]:
    """Documentation search (RAG) is added in step 10; until then nothing is found."""
    return {"available": False, "results": [], "message": "documentation search is not set up"}


# --- registry and JSON schemas (OpenAI / LiteLLM function-calling format) ----------

_TIME = {"type": "number", "description": "seconds since log start"}
_TABLES = [*[t for t in TABLE_NAMES if t != "events"], SIGNALS_TABLE]
_COLUMN_HELP = "; ".join(
    [
        f"{t}: {', '.join(c for c in TABLE_COLUMNS[t] if c != 't')}"
        for t in TABLE_COLUMNS
        if t != "events"
    ]
    + ["motors: m1..mN", f"{SIGNALS_TABLE}: {', '.join(SIGNAL_LABELS)}"]
)
_COLUMNS_DESC = 'Column names of the chosen table, without the table name, e.g. ["voltage"].'

TOOLS: Final[dict[str, Callable[..., dict[str, Any]]]] = {
    "get_flight_summary": get_flight_summary,
    "list_findings": list_findings,
    "query_series": query_series,
    "get_events": get_events,
    "make_plot": make_plot,
    "search_docs": search_docs,
}

TOOL_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "get_flight_summary",
            "description": "Vehicle, firmware, duration, modes, finding counts, skipped checks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_findings",
            "description": "Detected problems with id, time range, value, threshold and summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warn", "critical"]},
                    "detector": {
                        "type": "string",
                        "enum": ["vibration", "gps", "battery", "attitude", "motors", "ml_anomaly"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_series",
            "description": (
                "Statistics (mean/min/max with their times, std, first/last) or reduced samples of "
                f"log columns in a time range. Angles are in degrees. Columns: {_COLUMN_HELP}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "enum": _TABLES},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": _COLUMNS_DESC,
                    },
                    "t_start": _TIME,
                    "t_end": _TIME,
                    "agg": {"type": "string", "enum": list(AGGREGATES)},
                },
                "required": ["table", "columns"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "Mode changes, arming, takeoff/landing, failsafes and log messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "t_start": _TIME,
                    "t_end": _TIME,
                    "kinds": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "mode",
                                "arm",
                                "disarm",
                                "takeoff",
                                "landing",
                                "failsafe",
                                "error",
                                "warning",
                                "info",
                            ],
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_plot",
            "description": "Save an interactive plot of columns in a time range; returns its path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "enum": _TABLES},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": _COLUMNS_DESC,
                    },
                    "t_start": _TIME,
                    "t_end": _TIME,
                },
                "required": ["table", "columns"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search PX4 / ArduPilot documentation (not available yet).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


def call_tool(ctx: AgentContext, name: str, arguments: str | dict[str, Any] | None) -> str:
    """Run one tool call; errors are returned as JSON so the model can correct itself."""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
        if name not in TOOLS:
            raise ToolError(f"unknown tool {name!r}; tools: {sorted(TOOLS)}")
        result = TOOLS[name](ctx, **args)
    except (ToolError, TypeError, json.JSONDecodeError, KeyError) as err:
        result = {"error": str(err)}
    return json.dumps(result, ensure_ascii=False, default=_json_default)


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp | Path):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")

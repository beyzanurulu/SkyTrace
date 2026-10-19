"""Single-file, offline HTML report (Plotly + Jinja2).

Plotly JS is embedded once (no CDN). Figure data is serialized by us with
``<``, ``>`` and ``&`` escaped, so text that originates in a log (mode names,
messages) can never close the surrounding ``<script>`` element. Everything
rendered as HTML goes through Jinja2 autoescaping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
from jinja2 import Environment, PackageLoader, select_autoescape
from plotly.offline import get_plotlyjs
from plotly.utils import PlotlyJSONEncoder

from skytrace import __version__
from skytrace.config import SkyTraceConfig, load_config
from skytrace.detectors import DetectionResult, Finding
from skytrace.parsers.schema import FlightLog
from skytrace.report.evidence import Evidence, evidence_for

# Status colours are fixed in both themes (dataviz reference palette).
SEVERITY_COLORS = {"critical": "#d03b3b", "warn": "#fab219", "info": "#898781"}
SEVERITY_LABELS = {"critical": "Critical", "warn": "Warning", "info": "Info"}
# Categorical slots available to the mode timeline; more modes fold into "other".
MODE_SLOTS = 8
NEUTRAL = "#898781"


@dataclass(frozen=True)
class PlotBlock:
    div_id: str
    figure_json: str


@dataclass(frozen=True)
class EvidenceBlock:
    finding: Finding
    plot: PlotBlock | None
    title: str


def _script_safe_json(fig: go.Figure) -> str:
    raw = json.dumps(fig.to_plotly_json(), cls=PlotlyJSONEncoder)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _base_layout(height: int) -> dict[str, Any]:
    # Colours are themed in the browser from CSS variables (see the template script).
    return {
        "height": height,
        "margin": {"l": 64, "r": 24, "t": 16, "b": 44},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter, system-ui, sans-serif", "size": 12},
        "showlegend": False,
        "hoverlabel": {"namelength": -1},
    }


def _log_end(log: FlightLog) -> float:
    ends = [log.metadata.duration_s]
    for name in ("attitude", "vibration", "gps", "battery", "motors", "position", "events"):
        df = log.table(name)
        if not df.empty:
            ends.append(float(df["t"].max()))
    return max(ends)


def _intervals_from_events(
    log: FlightLog, kinds: tuple[str, ...], end: float
) -> list[tuple[float, float, str]]:
    ev = log.events[log.events["kind"].isin(kinds)].reset_index(drop=True)
    out = []
    for i, row in ev.iterrows():
        t0 = float(row["t"])
        t1 = float(ev.loc[i + 1, "t"]) if i + 1 < len(ev) else end
        out.append((t0, max(t1, t0), str(row["message"]) if kinds == ("mode",) else row["kind"]))
    return out


def timeline_figure(log: FlightLog, findings: list[Finding]) -> go.Figure:
    end = _log_end(log)
    fig = go.Figure()

    modes = _intervals_from_events(log, ("mode",), end)
    slot_of: dict[str, int] = {}
    for _, _, name in modes:
        if name not in slot_of:
            slot_of[name] = len(slot_of) if len(slot_of) < MODE_SLOTS else -1
    if modes:
        fig.add_bar(
            y=["Mode"] * len(modes),
            x=[t1 - t0 for t0, t1, _ in modes],
            base=[t0 for t0, _, _ in modes],
            orientation="h",
            text=[name for _, _, name in modes],
            textposition="inside",
            insidetextanchor="middle",
            marker={"line": {"width": 2}},
            meta={"role": "modes", "slots": [slot_of[name] for _, _, name in modes]},
            hovertemplate="%{text}<br>%{base:.1f} s - %{x:.1f} s long<extra></extra>",
        )

    armed = [iv for iv in _intervals_from_events(log, ("arm", "disarm"), end) if iv[2] == "arm"]
    if armed:
        fig.add_bar(
            y=["Armed"] * len(armed),
            x=[t1 - t0 for t0, t1, _ in armed],
            base=[t0 for t0, _, _ in armed],
            orientation="h",
            marker={"color": NEUTRAL, "line": {"width": 2}},
            meta={"role": "armed"},
            hovertemplate="armed %{base:.1f} s, %{x:.1f} s long<extra></extra>",
        )

    if findings:
        # Zero-length findings still get a visible sliver.
        min_width = max(end, 1.0) / 400
        fig.add_bar(
            y=["Findings"] * len(findings),
            x=[max(f.t_end - f.t_start, min_width) for f in findings],
            base=[f.t_start for f in findings],
            orientation="h",
            marker={"color": [SEVERITY_COLORS[f.severity] for f in findings], "line": {"width": 2}},
            customdata=[[f.id, SEVERITY_LABELS[f.severity], f.summary] for f in findings],
            meta={"role": "findings"},
            hovertemplate="%{customdata[0]} %{customdata[1]}<br>%{customdata[2]}<extra></extra>",
        )

    rows = [
        r for r, present in (("Findings", findings), ("Armed", armed), ("Mode", modes)) if present
    ]
    layout = _base_layout(56 + 36 * max(len(rows), 1))
    layout.update(
        barmode="overlay",
        bargap=0.35,
        xaxis={"title": {"text": "time since log start (s)"}, "range": [0, end], "zeroline": False},
        yaxis={"categoryorder": "array", "categoryarray": rows, "fixedrange": True},
    )
    fig.update_layout(**layout)
    return fig


def evidence_figure(ev: Evidence, finding: Finding) -> go.Figure:
    fig = go.Figure()
    for tr in ev.traces:
        fig.add_scatter(
            x=tr.t,
            y=np.where(np.isfinite(tr.y), tr.y, None),
            mode="lines",
            name=tr.name,
            line={"width": 2},
            meta={"role": "series"},
            connectgaps=False,
            hovertemplate=f"{tr.name}: %{{y:.3~f}}<extra></extra>",
        )
    color = SEVERITY_COLORS[finding.severity]
    fig.add_vrect(
        x0=finding.t_start,
        x1=max(finding.t_end, finding.t_start + 1e-3),
        fillcolor=color,
        opacity=0.18,
        line_width=0,
        layer="below",
    )
    if ev.threshold is not None:
        fig.add_hline(
            y=ev.threshold,
            line={"dash": "dash", "width": 1.5},
            name="threshold",
            annotation={"text": f"{ev.threshold_label} {ev.threshold:.3g}", "name": "threshold"},
            annotation_position="top left",
        )
    layout = _base_layout(280)
    layout.update(
        hovermode="x unified",
        xaxis={"title": {"text": "time since log start (s)"}, "range": list(ev.window)},
        yaxis={"title": {"text": ev.y_label}},
    )
    fig.update_layout(**layout)
    return fig


def _summary_rows(log: FlightLog, cfg: SkyTraceConfig) -> list[tuple[str, str]]:
    m = log.metadata
    cells = cfg.detectors.battery.cells or m.battery_cells
    motors = f"{log.motor_count}" + ("" if m.motor_count_known else " (count assumed)")
    minutes, seconds = divmod(int(round(m.duration_s)), 60)
    return [
        ("Log", Path(m.source).name),
        ("Format", m.format),
        ("Duration", f"{minutes} min {seconds:02d} s ({m.duration_s:.1f} s)"),
        ("Vehicle", m.vehicle_type or "unknown"),
        ("Hardware", m.hardware or "unknown"),
        ("Firmware", (m.firmware or "unknown")[:12]),
        ("Battery", f"{cells}S" if cells else "cell count unknown"),
        ("Motors", motors),
        ("Vibration source", m.vib_metric_source or "none"),
    ]


def render_html(
    log: FlightLog,
    result: DetectionResult,
    config: SkyTraceConfig | None = None,
) -> str:
    cfg = config if config is not None else load_config()
    findings = [replace(f, evidence_plot=f"evidence-{f.id}") for f in result.findings]

    blocks: list[EvidenceBlock] = []
    for f in findings:
        ev = evidence_for(log, f, cfg)
        if ev is None:
            blocks.append(EvidenceBlock(f, None, f.metric))
            continue
        plot = PlotBlock(f"plot-{f.id}", _script_safe_json(evidence_figure(ev, f)))
        blocks.append(EvidenceBlock(f, plot, ev.title))

    env = Environment(
        loader=PackageLoader("skytrace.report", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.j2")
    counts = {s: sum(f.severity == s for f in findings) for s in ("critical", "warn", "info")}
    return template.render(
        title=f"SkyTrace report - {Path(log.metadata.source).name}",
        summary=_summary_rows(log, cfg),
        counts=counts,
        findings=findings,
        blocks=blocks,
        notes=result.notes,
        warnings=log.warnings,
        events=log.events.to_dict("records"),
        timeline=PlotBlock("plot-timeline", _script_safe_json(timeline_figure(log, findings))),
        severity_labels=SEVERITY_LABELS,
        plotly_js=get_plotlyjs(),
        version=__version__,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )


def write_html(
    log: FlightLog,
    result: DetectionResult,
    path: str | Path,
    config: SkyTraceConfig | None = None,
) -> Path:
    out = Path(path)
    out.write_text(render_html(log, result, config), encoding="utf-8")
    return out

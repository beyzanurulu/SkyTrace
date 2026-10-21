"""Command line interface: ``skytrace analyze <log> --out report.html``."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from skytrace import __version__
from skytrace.config import ConfigError, load_config
from skytrace.detectors import DETECTORS, DetectionResult, run_detectors
from skytrace.parsers.schema import FlightLog
from skytrace.report import write_html, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

SEVERITY_STYLES = {"critical": "bold red", "warn": "yellow", "info": "dim"}


class OutputFormat(StrEnum):
    html = "html"
    json = "json"


def _version(value: bool) -> None:
    if value:
        typer.echo(f"skytrace {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    """PX4 / ArduPilot flight log analysis."""


def findings_table(result: DetectionResult) -> Table:
    table = Table(title="Findings", show_lines=False)
    for name in ("ID", "Severity", "Detector"):
        table.add_column(name, no_wrap=True)
    table.add_column("Time (s)", justify="right", no_wrap=True)
    table.add_column("Summary")
    for f in result.findings:
        table.add_row(
            f.id,
            f"[{SEVERITY_STYLES[f.severity]}]{f.severity}[/]",
            f.detector,
            f"{f.t_start:.1f}-{f.t_end:.1f}",
            f.summary,
        )
    return table


@app.command()
def analyze(
    log_path: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, readable=True, help="Flight log (.ulg / .bin)."
        ),
    ],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output file (default: <log>.html / <log>.json)."),
    ] = None,
    fmt: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.html,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", exists=True, dir_okay=False, help="YAML config override."),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help=f"Run only these detectors ({', '.join(DETECTORS)})."),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="No terminal table.")] = False,
    ml: Annotated[
        bool,
        typer.Option("--ml", help="Also run unsupervised ML anomaly detection (slower)."),
    ] = False,
) -> None:
    """Run all detectors on a log and write an HTML or JSON report."""
    console = Console(stderr=True)
    try:
        cfg = load_config(config_path)
        log = FlightLog.from_file(log_path, cfg)
        result = run_detectors(log, cfg, only=only, ml=ml)
    except (ConfigError, KeyError, ValueError) as exc:
        console.print(f"[red]error:[/] {exc}")
        raise typer.Exit(code=2) from exc

    target = out if out is not None else log_path.with_suffix(f".{fmt.value}")
    if fmt is OutputFormat.html:
        write_html(log, result, target, cfg)
    else:
        write_json(log, result, target)

    if not quiet:
        if result.findings:
            console.print(findings_table(result))
        else:
            console.print("[green]No findings.[/]")
        for note in result.notes:
            console.print(f"[dim]note: {note}[/]")
    console.print(f"Report written to {target}")

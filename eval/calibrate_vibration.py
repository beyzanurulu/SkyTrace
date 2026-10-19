"""Calibrate PX4 vibration thresholds (px4_imu_status) on the labeled Flight Review set.

Labels come from ``data/raw/index.jsonl`` (written by skytrace.data.flight_review):

- positive: the uploader tagged the log with the "Vibration" error label
- negative: no error label at all and rated "good" / "great" by the uploader
- everything else is ignored; SITL logs are excluded (no physical vibration)

Per-log statistic: P{--stat-quantile} of ``vibration.accel_vib_metric`` over armed
samples. The split, threshold rule and metrics live in
``skytrace.evaluation.calibration``; the test half is only used for measuring.

Outputs (in --out, default eval/results/):
  vibration_calibration.json   every log, its split / label / statistic, thresholds, metrics
  vibration_calibration.png    per-log distribution with the chosen thresholds
  vibration_thresholds.yaml    snippet for src/skytrace/defaults.yaml

    uv run --group eval python eval/calibrate_vibration.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from skytrace import FlightLog, load_config
from skytrace.config import SkyTraceConfig, VibrationSourceThresholds
from skytrace.detectors import run_detectors
from skytrace.detectors.base import armed_mask
from skytrace.evaluation.calibration import (
    BinaryMetrics,
    ThresholdChoice,
    binary_metrics,
    choose_thresholds,
    split_by_group,
)
from skytrace.parsers.schema import TABLE_NAMES, empty_table

SOURCE = "px4_imu_status"
NEGATIVE_RATINGS = {"good", "great"}


@dataclass
class Sample:
    log_id: str
    vehicle: str
    positive: bool
    hardware: str | None
    statistic: float
    log: FlightLog
    split: str = ""
    predicted: bool | None = None


def _read_index(path: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            entries[item["log_id"]] = item  # later lines win (re-downloads)
    return entries


def _label(entry: dict[str, Any]) -> bool | None:
    labels = entry.get("error_labels") or []
    if "Vibration" in labels:
        return True
    if not labels and str(entry.get("rating", "")).lower() in NEGATIVE_RATINGS:
        return False
    return None


def _slim(log: FlightLog) -> FlightLog:
    """Keep only what the vibration detector needs (memory)."""
    keep = {"vibration", "events"}
    empty: dict[str, Any] = {name: empty_table(name) for name in TABLE_NAMES if name not in keep}
    return replace(log, **empty)


def _load(data: Path, quantile: float) -> tuple[list[Sample], list[dict[str, str]]]:
    index = _read_index(data / "index.jsonl")
    samples: list[Sample] = []
    skipped: list[dict[str, str]] = []
    for log_id, entry in sorted(index.items()):
        path = data / f"{log_id}.ulg"
        label = _label(entry)
        if label is None:
            skipped.append({"log_id": log_id, "reason": "not a clear positive/negative"})
            continue
        if not path.exists():
            skipped.append({"log_id": log_id, "reason": "file missing"})
            continue
        try:
            log = FlightLog.from_file(path)
        except Exception as err:  # corrupt / truncated public logs exist
            skipped.append({"log_id": log_id, "reason": f"parse error: {err}"[:200]})
            continue
        hw = log.metadata.hardware
        if hw is not None and "SITL" in hw.upper():
            skipped.append({"log_id": log_id, "reason": f"simulation ({hw})"})
            continue
        if log.metadata.vib_metric_source != SOURCE:
            skipped.append({"log_id": log_id, "reason": "no px4_imu_status vibration metric"})
            continue
        vib = log.vibration
        armed = armed_mask(log, vib["t"].to_numpy(dtype=np.float64))
        values = vib["accel_vib_metric"].to_numpy(dtype=np.float64)[armed]
        values = values[np.isfinite(values)]
        if values.size == 0:
            skipped.append({"log_id": log_id, "reason": "no armed vibration samples"})
            continue
        samples.append(
            Sample(
                log_id=log_id,
                vehicle=entry.get("vehicle_uuid") or f"log:{log_id}",
                positive=label,
                hardware=hw,
                statistic=float(np.percentile(values, quantile)),
                log=_slim(log),
            )
        )
    return samples, skipped


def _config_with(choice: ThresholdChoice) -> SkyTraceConfig:
    base = load_config()
    current = base.detectors.vibration.px4_imu_status
    thresholds = VibrationSourceThresholds(
        metric_warn=choice.warn,
        metric_critical=choice.critical,
        clip_critical_count=current.clip_critical_count,
    )
    vib = replace(base.detectors.vibration, px4_imu_status=thresholds)
    return replace(base, detectors=replace(base.detectors, vibration=vib))


def _predict(samples: list[Sample], cfg: SkyTraceConfig) -> None:
    for s in samples:
        result = run_detectors(s.log, cfg, only=["vibration"])
        s.predicted = any(f.metric == "accel_vib_metric" for f in result.findings)


def _metrics_dict(m: BinaryMetrics) -> dict[str, float | int]:
    return {
        "tp": m.tp,
        "fp": m.fp,
        "fn": m.fn,
        "tn": m.tn,
        "precision": m.precision,
        "recall": m.recall,
        "false_positive_rate": m.false_positive_rate,
    }


def _jitter(log_id: str, width: float = 0.28) -> float:
    h = int(hashlib.sha256(log_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return (h - 0.5) * 2 * width


def _plot(samples: list[Sample], choice: ThresholdChoice, quantile: float, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Reference palette (dataviz skill): categorical slots 1-2, text and surface tokens.
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    colors = {False: "#2a78d6", True: "#eb6834"}
    names = {False: "Clean (no label, rated good/great)", True: "Vibration-labeled"}

    fig, axes = plt.subplots(1, 2, figsize=(10, 5.2), sharey=True, facecolor=surface)
    stats = [s.statistic for s in samples]
    use_log = max(stats) / max(min(stats), 1e-9) > 30
    for ax, split in zip(axes, ("calibration", "test"), strict=True):
        ax.set_facecolor(surface)
        subset = [s for s in samples if s.split == split]
        for cls in (False, True):
            pts = [s for s in subset if s.positive == cls]
            ax.scatter(
                [int(cls) + _jitter(s.log_id) for s in pts],
                [s.statistic for s in pts],
                s=56,
                color=colors[cls],
                edgecolors=surface,
                linewidths=1.5,
                zorder=3,
                label=f"{names[cls]}",
            )
        ax.set_xticks([0, 1], ["Clean", "Vibration-labeled"], color=ink2)
        ax.set_xlim(-0.6, 1.6)
        n_neg = sum(not s.positive for s in subset)
        n_pos = sum(s.positive for s in subset)
        ax.set_title(
            f"{split.capitalize()} half  (clean n={n_neg}, vibration n={n_pos})",
            color=ink,
            fontsize=11,
            loc="left",
        )
        ax.grid(axis="y", color=grid, linewidth=0.8, zorder=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
        ax.tick_params(colors=ink2)
        if use_log:
            ax.set_yscale("log")
        lines = [(choice.warn, "--", f"warn {choice.warn:.2f}")]
        if choice.critical is not None:
            lines.append((choice.critical, ":", f"critical {choice.critical:.2f}"))
        for y, style, text in lines:
            ax.axhline(y, color=ink, linestyle=style, linewidth=1.2, zorder=2)
            if split == "test":
                ax.annotate(
                    text,
                    (1.6, y),
                    xytext=(4, 0),
                    textcoords="offset points",
                    va="center",
                    ha="left",
                    color=ink,
                    fontsize=9,
                    annotation_clip=False,
                )
    axes[0].set_ylabel(f"P{quantile:g} of accel_vibration_metric while armed", color=ink2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=2,
        frameon=False,
        labelcolor=ink2,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(
        "PX4 vibration thresholds: chosen on the calibration half, measured on the test half",
        color=ink,
        fontsize=12,
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.905,
        f"warn = {choice.warn_rule};  critical = {choice.critical_rule}",
        color=ink2,
        fontsize=9,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.06, 0.93, 0.89))
    fig.savefig(out, dpi=150, facecolor=surface)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--data", type=Path, default=Path("data/raw"))
    p.add_argument("--out", type=Path, default=Path("eval/results"))
    p.add_argument("--stat-quantile", type=float, default=95.0)
    p.add_argument("--warn-percentile", type=float, default=95.0)
    p.add_argument("--critical-percentile", type=float, default=50.0)
    args = p.parse_args()

    samples, skipped = _load(args.data, args.stat_quantile)
    split = split_by_group(samples, group=lambda s: s.vehicle, label=lambda s: s.positive)
    for s in split.calibration:
        s.split = "calibration"
    for s in split.test:
        s.split = "test"

    choice = choose_thresholds(
        [s.statistic for s in split.calibration if not s.positive],
        [s.statistic for s in split.calibration if s.positive],
        warn_percentile=args.warn_percentile,
        critical_percentile=args.critical_percentile,
    )
    _predict(samples, _config_with(choice))
    metrics = {
        name: _metrics_dict(binary_metrics((bool(s.predicted), s.positive) for s in part))
        for name, part in (("calibration", split.calibration), ("test", split.test))
    }

    args.out.mkdir(parents=True, exist_ok=True)
    result = {
        "date": date.today().isoformat(),
        "source": SOURCE,
        "statistic": f"P{args.stat_quantile:g} of accel_vib_metric over armed samples",
        "split": "by vehicle_uuid, stratified, sha256(salt) order, 50/50",
        "thresholds": asdict(choice),
        "metrics": metrics,
        "logs": [
            {
                "log_id": s.log_id,
                "vehicle": s.vehicle,
                "hardware": s.hardware,
                "label": "vibration" if s.positive else "clean",
                "split": s.split,
                "statistic": s.statistic,
                "predicted_vibration": s.predicted,
            }
            for s in sorted(samples, key=lambda s: (s.split, s.positive, s.statistic))
        ],
        "skipped": skipped,
    }
    (args.out / "vibration_calibration.json").write_text(json.dumps(result, indent=2), "utf-8")
    _plot(samples, choice, args.stat_quantile, args.out / "vibration_calibration.png")

    calib_ids = sorted(s.log_id for s in split.calibration)
    crit = "null" if choice.critical is None else f"{choice.critical:.3f}"
    snippet = "\n".join(
        [
            f"# Calibrated {result['date']} with eval/calibrate_vibration.py "
            f"(eval/results/vibration_calibration.json).",
            f"# Statistic: {result['statistic']}; split {result['split']}.",
            f"# metric_warn: {choice.warn_rule}.",
            f"# metric_critical: {choice.critical_rule}.",
            f"# Calibration logs ({len(calib_ids)}): " + ", ".join(i[:8] for i in calib_ids),
            f"# Test half: precision {metrics['test']['precision']:.2f}, "
            f"recall {metrics['test']['recall']:.2f}, "
            f"FPR {metrics['test']['false_positive_rate']:.2f} "
            f"(n={len(split.test)}).",
            f"metric_warn: {choice.warn:.3f}",
            f"metric_critical: {crit}",
        ]
    )
    (args.out / "vibration_thresholds.yaml").write_text(snippet + "\n", "utf-8")

    print(
        f"{len(samples)} logs used ({sum(s.positive for s in samples)} vibration), "
        f"{len(skipped)} skipped"
    )
    print(json.dumps({"thresholds": asdict(choice), "metrics": metrics}, indent=2))
    print("\n" + snippet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

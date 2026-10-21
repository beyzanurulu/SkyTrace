"""Calibrate the ML anomaly thresholds by false-alarm rate on clean real flights.

There are no labels for "unknown" anomalies, so recall cannot be measured. What
can be controlled is how often the detector speaks up on flights that are fine:

- clean = real PX4 multicopter log with no Flight Review error label, rated
  "good" / "great" by the uploader; SITL and HITL/SIH (SYS_HITL != 0) excluded.
- Per log, with the thresholds out of the way: the highest robust |z| held for
  zscore.min_duration_s, and the largest feature |z| among windows the forest
  flags (skytrace.anomaly.ml.*_log_statistic; same code path as detection).
- Calibration half (split by vehicle): info = P{--info-percentile}, warn =
  P{--warn-percentile} of those per-log values, i.e. roughly 20 % / 5 % of clean
  flights get an info / warn finding.
- Test half: the false-alarm rates actually reached. Vibration-labeled logs are
  reported too, as a sanity check only (not a recall).

Outputs (in --out, default eval/results/):
  ml_calibration.json   every log, split, statistics, chosen thresholds, rates
  ml_calibration.png    per-log statistics with the chosen thresholds
  ml_thresholds.yaml    snippet for src/skytrace/defaults.yaml

    uv run --group eval python eval/calibrate_ml.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from skytrace import FlightLog, load_config
from skytrace.anomaly.ml import iforest_log_statistic, make_grids, zscore_log_statistic
from skytrace.evaluation.calibration import split_by_group

CLEAN_RATINGS = {"good", "great"}


@dataclass
class Sample:
    log_id: str
    vehicle: str
    group: str  # "clean" | "vibration"
    zscore: float
    iforest: float
    split: str = ""


def _read_index(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            out[item["log_id"]] = item
    return out


def _group(entry: dict[str, Any]) -> str | None:
    labels = entry.get("error_labels") or []
    if not labels and str(entry.get("rating", "")).lower() in CLEAN_RATINGS:
        return "clean"
    if "Vibration" in labels:
        return "vibration"
    return None


def _is_simulated(path: Path) -> bool:
    from pyulog import ULog

    params = ULog(str(path), []).initial_parameters
    return int(params.get("SYS_HITL", 0)) != 0


def _load(data: Path) -> tuple[list[Sample], list[dict[str, str]]]:
    cfg = load_config()
    samples: list[Sample] = []
    skipped: list[dict[str, str]] = []
    for log_id, entry in sorted(_read_index(data / "index.jsonl").items()):
        group = _group(entry)
        path = data / f"{log_id}.ulg"
        if group is None or not path.exists():
            continue
        if (entry.get("sys_hw") or "").upper() == "PX4_SITL" or _is_simulated(path):
            skipped.append({"log_id": log_id, "reason": "simulation (SITL / HITL / SIH)"})
            continue
        try:
            log = FlightLog.from_file(path, cfg)
        except Exception as err:  # corrupt / truncated public logs exist
            skipped.append({"log_id": log_id, "reason": f"parse error: {err}"[:200]})
            continue
        grids = make_grids(log, cfg)
        if not grids:
            skipped.append({"log_id": log_id, "reason": "no in-air armed data"})
            continue
        samples.append(
            Sample(
                log_id=log_id,
                vehicle=entry.get("vehicle_uuid") or f"log:{log_id}",
                group=group,
                zscore=zscore_log_statistic(grids, cfg.anomaly),
                iforest=iforest_log_statistic(grids, cfg.anomaly),
            )
        )
    return samples, skipped


def _rate(values: list[float], threshold: float) -> float:
    return float(np.mean([v > threshold for v in values])) if values else float("nan")


def _plot(samples: list[Sample], chosen: dict[str, dict[str, float]], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # dataviz reference palette: categorical slots 1-3, text / surface tokens
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    groups = [
        ("clean", "calibration", "#2a78d6", "Clean, calibration half"),
        ("clean", "test", "#1baf7a", "Clean, test half"),
        ("vibration", "", "#eb6834", "Vibration-labeled (sanity check)"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 5.0), facecolor=surface)
    for ax, (stat, title) in zip(
        axes,
        (
            ("zscore", "Rolling z-score: max sustained robust |z|"),
            ("iforest", "Isolation Forest: max feature |z| of flagged windows"),
        ),
        strict=True,
    ):
        ax.set_facecolor(surface)
        for x, (group, split, color, label) in enumerate(groups):
            pts = [s for s in samples if s.group == group and (not split or s.split == split)]
            rng = np.random.default_rng(x)
            ax.scatter(
                x + rng.uniform(-0.25, 0.25, len(pts)),
                [max(getattr(s, stat), 0.1) for s in pts],
                s=56,
                color=color,
                edgecolors=surface,
                linewidths=1.5,
                zorder=3,
                label=f"{label} (n={len(pts)})",
            )
        for level, style in (("info", "--"), ("warn", ":")):
            y = chosen[stat][level]
            ax.axhline(y, color=ink, linestyle=style, linewidth=1.2, zorder=2)
            ax.annotate(
                f"{level} {y:.1f}",
                (2.45, y),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                color=ink,
                fontsize=9,
                annotation_clip=False,
            )
        ax.set_yscale("log")
        ax.set_xticks([0, 1, 2], ["clean\ncalib.", "clean\ntest", "vibration"], color=ink2)
        ax.set_xlim(-0.6, 2.45)
        ax.set_title(title, color=ink, fontsize=10.5, loc="left")
        ax.grid(axis="y", color=grid, linewidth=0.8, zorder=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
        ax.tick_params(colors=ink2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, labelcolor=ink2)
    fig.suptitle(
        "ML anomaly thresholds from clean real flights (per-log maximum, log scale)",
        color=ink,
        fontsize=12,
        x=0.02,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.07, 0.95, 0.94))
    fig.savefig(out, dpi=150, facecolor=surface)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--data", type=Path, default=Path("data/raw"))
    p.add_argument("--out", type=Path, default=Path("eval/results"))
    p.add_argument("--info-percentile", type=float, default=80.0)
    p.add_argument("--warn-percentile", type=float, default=95.0)
    a = p.parse_args()

    samples, skipped = _load(a.data)
    clean = [s for s in samples if s.group == "clean"]
    split = split_by_group(clean, group=lambda s: s.vehicle, label=lambda s: False)
    for s in split.calibration:
        s.split = "calibration"
    for s in split.test:
        s.split = "test"

    chosen: dict[str, dict[str, float]] = {}
    rates: dict[str, dict[str, float]] = {}
    for stat in ("zscore", "iforest"):
        calib = [getattr(s, stat) for s in split.calibration]
        info, warn = np.percentile(calib, [a.info_percentile, a.warn_percentile])
        chosen[stat] = {"info": float(info), "warn": float(warn)}
        rates[stat] = {}
        for name, part in (
            ("clean_calibration", split.calibration),
            ("clean_test", split.test),
            ("vibration", [s for s in samples if s.group == "vibration"]),
        ):
            values = [getattr(s, stat) for s in part]
            rates[stat][f"{name}_info"] = _rate(values, info)
            rates[stat][f"{name}_warn"] = _rate(values, warn)

    a.out.mkdir(parents=True, exist_ok=True)
    result = {
        "date": date.today().isoformat(),
        "rule": f"info = P{a.info_percentile:g}, warn = P{a.warn_percentile:g} of per-log "
        "statistics on the clean calibration half (split by vehicle_uuid)",
        "thresholds": chosen,
        "false_alarm_rates": rates,
        "logs": [
            {
                "log_id": s.log_id,
                "vehicle": s.vehicle,
                "group": s.group,
                "split": s.split,
                "zscore_stat": s.zscore,
                "iforest_stat": s.iforest,
            }
            for s in sorted(samples, key=lambda s: (s.group, s.split, s.log_id))
        ],
        "skipped": skipped,
    }
    (a.out / "ml_calibration.json").write_text(json.dumps(result, indent=2), "utf-8")
    _plot(samples, chosen, a.out / "ml_calibration.png")

    n_cal, n_test = len(split.calibration), len(split.test)
    lines = [
        f"# Calibrated {result['date']} with eval/calibrate_ml.py "
        "(eval/results/ml_calibration.json).",
        f"# {result['rule']}; {n_cal} calibration / {n_test} test clean real flights.",
    ]
    for stat, keys in (
        ("zscore", ("info", "warn")),
        ("iforest", ("min_feature_z", "warn_feature_z")),
    ):
        r = rates[stat]
        lines.append(
            f"# {stat}: test-half false alarms info {r['clean_test_info']:.0%}, "
            f"warn {r['clean_test_warn']:.0%}"
        )
        lines.append(f"{stat}.{keys[0]}: {chosen[stat]['info']:.1f}")
        lines.append(f"{stat}.{keys[1]}: {chosen[stat]['warn']:.1f}")
    (a.out / "ml_thresholds.yaml").write_text("\n".join(lines) + "\n", "utf-8")

    print(
        f"{len(samples)} logs ({len(clean)} clean, {len(samples) - len(clean)} vibration), "
        f"{len(skipped)} skipped"
    )
    print(json.dumps({"thresholds": chosen, "false_alarm_rates": rates}, indent=2))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

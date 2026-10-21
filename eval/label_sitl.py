"""Write data/labels/<run_id>.yaml for every recorded run in data/sitl/manifest.tsv.

    uv run python eval/label_sitl.py [--overwrite]

Labels come from the injected commands and PX4's own state, never from
SkyTrace's thresholds (see skytrace.evaluation.sitl). Runs whose fault cannot
be found in the log (e.g. a rejected injection) are reported and not labelled,
so they never enter the evaluation as a silently wrong label.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from skytrace.evaluation.sitl import LabelingError, label_log, read_manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--manifest", type=Path, default=Path("data/sitl/manifest.tsv"))
    p.add_argument("--logs", type=Path, default=Path("data/raw"))
    p.add_argument("--labels", type=Path, default=Path("data/labels"))
    p.add_argument("--overwrite", action="store_true")
    a = p.parse_args()

    a.labels.mkdir(parents=True, exist_ok=True)
    written = skipped = problems = 0
    for row in read_manifest(a.manifest):
        run_id, scenario, status = row["run_id"], row["scenario"], row["status"]
        target = a.labels / f"{run_id}.yaml"
        if not status.startswith("ok"):
            print(f"  {run_id}: run {status}, no label")
            problems += 1
            continue
        if target.exists() and not a.overwrite:
            skipped += 1
            continue
        try:
            content = label_log(a.logs / f"{run_id}.ulg", scenario, run_id)
        except (LabelingError, FileNotFoundError) as err:
            print(f"  {run_id}: {err}")
            problems += 1
            continue
        target.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
        intervals = ", ".join(
            f"{f['type']} {f['t_start']}-{f['t_end']} s" for f in content["faults"]
        )
        print(f"  {run_id}: {intervals or 'clean'}")
        written += 1
    print(f"{written} labels written, {skipped} already present, {problems} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

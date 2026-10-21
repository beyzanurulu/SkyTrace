"""Write a SITL fault-injection plan for eval/sitl/run_scenarios.sh.

    uv run python eval/sitl_plan.py --clean 10 --gps 6 --battery 6 --motor 6 --seed 1

Timings (hover before the fault, fault duration, battery drain) are drawn from
the ranges in skytrace.evaluation.sitl.PlanRanges with a fixed seed, so the same
command always produces the same plan.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skytrace.evaluation.sitl import SCENARIOS, make_plan, write_plan


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    defaults = {"clean": 10, "gps": 6, "battery": 6, "motor": 6}
    for s in SCENARIOS:
        p.add_argument(
            f"--{s}", type=int, default=defaults[s], help=f"runs (default {defaults[s]})"
        )
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--prefix", default="sitl_auto")
    p.add_argument("--out", type=Path, default=Path("data/sitl/plan.tsv"))
    a = p.parse_args()

    runs = make_plan({s: getattr(a, s) for s in SCENARIOS}, seed=a.seed, prefix=a.prefix)
    write_plan(runs, a.out)
    minutes = sum(r.hover_s + r.fault_s + 90 for r in runs) / 60  # ~90 s start/takeoff/land
    print(f"{len(runs)} runs -> {a.out} (roughly {minutes:.0f} min of flying)")
    for r in runs:
        print(
            f"  {r.run_id:24s} {r.scenario:8s} hover {r.hover_s:5.1f} s  fault {r.fault_s:5.1f} s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

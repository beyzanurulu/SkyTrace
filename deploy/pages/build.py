"""Build the GitHub Pages site: a landing page and the report of every sample flight.

    uv run python deploy/pages/build.py --out site [--demo-url https://...]

The reports are the normal offline HTML reports (`skytrace analyze`), one per
sample in samples/samples.yaml. The live demo button is shown only when a demo
URL is given (the workflow passes the repository variable DEMO_URL).
"""

from __future__ import annotations

import argparse
import html
import shutil
import sys
from pathlib import Path

import yaml

from skytrace import FlightLog, __version__, load_config
from skytrace.detectors import run_detectors
from skytrace.report import render_html

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SEV = {"critical": "WARNING", "warn": "CAUTION", "info": "ADVISORY"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--out", type=Path, default=ROOT / "site")
    p.add_argument("--demo-url", default="")
    a = p.parse_args()

    cfg = load_config()
    out: Path = a.out
    shutil.rmtree(out, ignore_errors=True)
    (out / "reports").mkdir(parents=True)
    shutil.copytree(ROOT / "docs" / "images", out / "images")

    cards = []
    samples = yaml.safe_load((ROOT / "samples" / "samples.yaml").read_text("utf-8"))
    for s in samples:
        path = ROOT / "samples" / s["file"]
        log = FlightLog.from_file(path, cfg)
        result = run_detectors(log, cfg)
        (out / "reports" / f"{path.stem}.html").write_text(
            render_html(log, result, cfg), encoding="utf-8"
        )
        counts = {k: sum(f.severity == k for f in result.findings) for k in SEV}
        lamps = "".join(
            f'<span class="lamp {k}{" lit" if n else ""}"><b>{n}</b>{SEV[k]}</span>'
            for k, n in counts.items()
        )
        meta = f"{log.metadata.duration_s:.0f} s flight · {len(result.findings)} findings"
        cards.append(
            f'<a class="card" href="reports/{path.stem}.html">'
            f"<small>{meta}</small>"
            f"<b>{html.escape(s['title'])}</b><span>{html.escape(s['description'])}</span>"
            f'<div class="lamps">{lamps}</div><em>Open the report →</em></a>'
        )
        print(f"report: {path.stem} ({len(result.findings)} findings)")

    demo = a.demo_url.strip()
    page = (HERE / "index.html").read_text("utf-8")
    page = page.replace("{{cards}}", "\n".join(cards)).replace("{{version}}", __version__)
    page = page.replace("{{demo_url}}", html.escape(demo))
    page = page.replace("{{demo_hidden}}", "" if demo else "hidden")
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site written to {out} (demo button {'on' if demo else 'off'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

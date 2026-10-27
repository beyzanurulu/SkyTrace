"""The sample flights listed in samples/samples.yaml are in the repository.

They are used by the web UI, the release workflow (sample report) and the
Hugging Face Space, which downloads them from the release tag. A log that is
listed but not committed (e.g. caught by a *.ulg ignore rule) fails here in CI,
where only committed files exist.
"""

from dataclasses import replace
from pathlib import Path

import yaml

from skytrace.api.app import load_samples
from skytrace.config import load_config

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_every_listed_sample_exists():
    entries = yaml.safe_load((SAMPLES / "samples.yaml").read_text("utf-8"))
    missing = [e["file"] for e in entries if not (SAMPLES / e["file"]).is_file()]
    assert entries and not missing, f"listed in samples.yaml but not in the repo: {missing}"


def test_all_samples_are_offered():
    demo = replace(load_config().demo, samples_dir=str(SAMPLES))
    entries = yaml.safe_load((SAMPLES / "samples.yaml").read_text("utf-8"))
    assert len(load_samples(demo)) == len(entries)

"""A tiny documentation index for tests: no embedding model, no network."""

import math
import re

from skytrace.agent.rag import Chunk, DocSearch, build_index
from skytrace.config import RagConfig


def fake_embed(texts):
    """Deterministic bag-of-words hashing embedding."""
    out = []
    for text in texts:
        v = [0.0] * 64
        for w in re.findall(r"[a-z]+", text.lower()):
            v[sum(map(ord, w)) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


PX4 = "https://docs.px4.io/main/en/"
DOC_CHUNKS = [
    Chunk(
        "px4",
        "docs/en/assembly/vibration_isolation.md",
        "Vibration Isolation",
        PX4 + "assembly/vibration_isolation.html",
        "Vibration damping mounts reduce accelerometer vibration and clipping. "
        "Mount the flight controller on foam and balance the propellers.",
    ),
    Chunk(
        "px4",
        "docs/en/config/battery.md",
        "Battery Estimation Tuning",
        PX4 + "config/battery.html",
        "Battery voltage sag under load and cell count configuration.",
    ),
    Chunk(
        "px4",
        "docs/en/gps_compass/index.md",
        "GPS & Compass",
        PX4 + "gps_compass/index.html",
        "GPS EPH accuracy improves with a clear sky view; mount the GPS away from "
        "power cables and wait for enough satellites before arming.",
    ),
    Chunk(
        "ardupilot",
        "common/source/docs/common-measuring-vibration.rst",
        "Measuring Vibration",
        "https://ardupilot.org/copter/docs/common-measuring-vibration.html",
        "Vibration levels below 30 m/s/s are normally acceptable.",
    ),
]


def fake_docs(cfg: RagConfig) -> DocSearch:
    build_index(DOC_CHUNKS, cfg, fake_embed, location=":memory:")
    return DocSearch(cfg, fake_embed, location=":memory:")

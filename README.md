# SkyTrace

PX4 / ArduPilot flight log analysis, anomaly detection and Q&A. See [docs/PLAN.md](docs/PLAN.md).

## Usage

```
skytrace analyze flight.ulg --out report.html          # PX4
skytrace analyze flight.bin --format json -o out.json  # ArduPilot
```

Questions about a log (local model via Ollama by default, see `docs/thresholds.md`):

```
ollama pull qwen2.5:7b
skytrace chat flight.ulg                                # interactive
skytrace chat flight.ulg --ask "When did the GPS fail?"  # one question
```

Every number in an answer is checked against the tool outputs; anything the
model did not get from the log is marked as not backed.

For "why / how do I fix it" questions the agent can search the PX4 and ArduPilot
documentation and cite the pages. Build the local index once (about 3 minutes;
the docs and the index stay in `data/`):

```
ollama pull bge-m3
skytrace docs build
skytrace docs search "vibration too high"   # try the index without the agent
```

The HTML report is a single offline file (Plotly embedded). Findings are also
printed as a table in the terminal.

`--ml` adds unsupervised anomaly detection (a rolling robust z-score per signal and
flight mode; an Isolation Forest is available but off by default) for problems the
rule detectors do not cover; see `docs/thresholds.md`.

## Development

```
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

```python
from skytrace import FlightLog

log = FlightLog.from_file("flight.ulg")
print(log.metadata, log.attitude.head())
```

Detector evaluation on labeled logs: `uv run python eval/run_eval.py`
(label format and SITL fault injection guide: [eval/SITL_GUIDE.md](eval/SITL_GUIDE.md)).

Configurable defaults are documented in [docs/thresholds.md](docs/thresholds.md).

## Sources and licenses

Test fixture `tests/fixtures/sample_log_small.ulg` is taken from
[PX4/pyulog](https://github.com/PX4/pyulog) (BSD-3-Clause).

`skytrace docs build` downloads documentation to the user's machine; none of it
is part of this repository. Passages returned by `search_docs` link to their source page.

- [PX4 User Guide](https://docs.px4.io/) (`docs/` of
  [PX4/PX4-Autopilot](https://github.com/PX4/PX4-Autopilot)) by the PX4
  contributors, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
  (`docs/LICENSE` in that repository).
- [ArduPilot documentation](https://ardupilot.org/copter/)
  ([ArduPilot/ardupilot_wiki](https://github.com/ArduPilot/ardupilot_wiki)),
  by the ArduPilot contributors,
  [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) (`LICENSE` in that
  repository).

Excerpts are split at headings and markup (links, images, directives) is removed;
the text is otherwise unchanged.

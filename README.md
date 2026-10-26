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

Test fixture `tests/fixtures/sample_log_small.ulg` is taken from
[PX4/pyulog](https://github.com/PX4/pyulog) (BSD-3-Clause).

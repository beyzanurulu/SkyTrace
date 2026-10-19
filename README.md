# SkyTrace

PX4 / ArduPilot flight log analysis, anomaly detection and Q&A. See [docs/PLAN.md](docs/PLAN.md).

## Usage

```
skytrace analyze flight.ulg --out report.html          # PX4
skytrace analyze flight.bin --format json -o out.json  # ArduPilot
```

The HTML report is a single offline file (Plotly embedded). Findings are also
printed as a table in the terminal.

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

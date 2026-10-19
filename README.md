# SkyTrace

PX4 / ArduPilot flight log analysis, anomaly detection and Q&A. See [docs/PLAN.md](docs/PLAN.md).

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

Configurable defaults are documented in [docs/thresholds.md](docs/thresholds.md).

Test fixture `tests/fixtures/sample_log_small.ulg` is taken from
[PX4/pyulog](https://github.com/PX4/pyulog) (BSD-3-Clause).

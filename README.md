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

Web UI (upload a log, findings with plots, chat panel; works on phones too):

```
uv sync                      # or: pip install 'skytrace[web]'
skytrace serve               # http://127.0.0.1:8000
```

The UI is served by the same FastAPI app (`POST /analyze`, `GET /report/{id}`,
`POST /chat/{id}` as server-sent events, ...; see `src/skytrace/api/app.py`). It
makes no external requests (Plotly is served locally). Uploads are kept in
`data/uploads/` and deleted after 24 hours. There is no authentication: it is
meant for local use and listens on localhost only by default.

## Offline mode

`SKYTRACE_MODE=offline` guarantees that nothing leaves the machine: the chat and
embedding models must be local (Ollama), every outgoing connection except to the
model server is refused (and shows up as an error instead of a silent leak), and
LiteLLM uses its bundled data instead of downloading it. `skytrace docs build`
needs the internet once; build the index before going offline.

```
$env:SKYTRACE_MODE = "offline"     # PowerShell; bash: export SKYTRACE_MODE=offline
skytrace serve
```

With Docker (Ollama + SkyTrace; the first start downloads the models):

```
docker compose up --build                                               # CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build  # NVIDIA GPU
```

All-in-one image with the models and the documentation index inside (about
7 GB), which runs with no network at all:

```
skytrace docs build
docker build -f docker/Dockerfile.bundle -t skytrace:bundle .
docker run --rm --network none skytrace:bundle python eval/offline_e2e.py
docker run --rm -p 127.0.0.1:8000:8000 skytrace:bundle
```

Results of the network-isolated run and the cloud vs. local comparison:
[eval/results/offline_e2e.md](eval/results/offline_e2e.md),
[eval/results/agent_eval_notes.md](eval/results/agent_eval_notes.md).

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

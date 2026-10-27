# Contributing to SkyTrace

Bug reports, logs that SkyTrace gets wrong, and pull requests are welcome.
Please open an issue first for larger changes, so the approach can be agreed on.

## Setup

[uv](https://docs.astral.sh/uv/) and Python 3.11 or 3.12:

```
git clone https://github.com/beyzanurulu/SkyTrace.git
cd SkyTrace
uv sync                  # dev + eval groups and the web extra
```

For the assistant: [Ollama](https://ollama.com) with `ollama pull qwen2.5:7b`
(and `bge-m3` for the documentation index). The tests do not need a model.

## Checks

All four must pass; CI runs them on Python 3.11 and 3.12.

```
uv run ruff check . ; uv run ruff format --check .
uv run mypy              # strict for src/, normal for tests/ and eval/
uv run pytest
```

## Ground rules

- Type hints everywhere in `src/`; every new module gets tests.
- **No thresholds in code.** Every threshold and default lives in
  `src/skytrace/defaults.yaml` and is documented in `docs/thresholds.md`, with
  where the value comes from (calibration script, documentation, heuristic).
- **The language model never produces a number.** Tools return the numbers from
  the log; the verification step (`skytrace.agent.verify`) flags anything in an
  answer that no tool returned. New tools return JSON with numbers only from the
  log or the config.
- Keep test data small. `tests/fixtures/` only holds the pyulog sample log;
  logs for evaluation go to `data/raw/` and are never committed.

## Layout

```
src/skytrace/
  parsers/     ULog (pyulog) and DataFlash (pymavlink) -> FlightLog schema
  detectors/   rule-based detectors -> Finding
  anomaly/     unsupervised anomaly detection (--ml)
  report/      HTML (Plotly, Jinja2) and JSON reports
  agent/       LangGraph agent: tools, verification, documentation search (RAG)
  api/         FastAPI backend of the web UI
  web/         the web UI (HTML / CSS / JS, no build step)
  offline.py   SKYTRACE_MODE=offline
  evaluation/  labels, calibration helpers, agent question scoring
eval/          evaluation and calibration scripts, results
```

## Adding a detector

1. Add `src/skytrace/detectors/<name>.py` with a function
   `detect(log: FlightLog, cfg: DetectorsConfig, notes: list[str]) -> list[Finding]`.
   Use the helpers in `detectors/base.py` (`intervals`, ...) to turn a boolean
   mask over time into findings. If the data a check needs is missing, append a
   note ("<name>: no ... data, detector skipped") instead of returning nothing
   silently: skipped checks are shown to the user and to the assistant.
2. Add its config dataclass to `config.py`, its defaults to `defaults.yaml` and a
   section to `docs/thresholds.md`.
3. Register it in `DETECTORS` in `detectors/__init__.py`.
4. Tests in `tests/` (synthetic `FlightLog` data is usually enough), and, if the
   fault can be simulated, a SITL scenario (see `eval/SITL_GUIDE.md`) so that
   `eval/run_eval.py` measures it.

## Evaluation

- Detectors: `uv run python eval/run_eval.py` on the labelled logs in
  `data/raw/` (labels in `data/labels/`, format in `eval/labels.example.yaml`).
- Assistant: `uv run python eval/agent_eval.py [--model ...]` asks the questions
  in `eval/agent_questions.yaml`; the same questions are replayed in the tests
  with a scripted model.
- Offline: `eval/offline_e2e.py` in the bundle image with `--network none`.

## Pull requests

One topic per pull request, with tests and updated docs; PRs are squash-merged
into `master`. Describe what changed and how you checked it (commands, logs).

## Releasing

Maintainers. One-time setup:

1. **PyPI:** on <https://pypi.org/manage/account/publishing/> add a *pending
   publisher*: project `skytrace`, owner `beyzanurulu`, repository `SkyTrace`,
   workflow `release.yml`, environment `pypi`. In the GitHub repository create
   the environment `pypi` (Settings → Environments).
2. **GHCR:** nothing to set up; after the first release make the package
   `skytrace` public (GitHub profile → Packages → skytrace → Package settings).
3. **Hugging Face Space:** create a Docker Space, add the secret
   `GEMINI_API_KEY` (Settings → Variables and secrets) and push the files of
   `deploy/hf-space/` to it. Raise `SKYTRACE_VERSION` in its Dockerfile for a
   new release.

Each release:

1. Move the changes in `CHANGELOG.md` under a new `## [X.Y.Z] - date` heading
   and set `version` in `pyproject.toml`.
2. Merge to `master`, then `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` tests, builds, publishes to PyPI and GHCR and
   creates the GitHub release (notes from the changelog, packages, sample report).

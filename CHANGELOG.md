# Changelog

All notable changes to SkyTrace. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-10-27

### Fixed

- The sample flight logs in `samples/` were missing from the repository (a
  `*.ulg` ignore rule caught them): the web UI showed no samples, and the sample
  report and the Hugging Face demo could not be built. A test now checks that
  every listed sample is committed. The package itself is unchanged.
- Release workflow: the image vulnerability scan referred to a non-existent
  action version, so v1.0.0 got no image and no GitHub release; a release can now
  be re-run for an existing tag (without publishing to PyPI again).

## [1.0.0] - 2026-10-27

First public release.

### Added

- **Parsing:** PX4 ULog (`.ulg`, pyulog) and ArduPilot DataFlash (`.bin`,
  pymavlink) into one `FlightLog` schema: attitude and setpoints, GPS, battery,
  vibration and clipping, motor outputs, position, events (modes, arming,
  takeoff / landing). Renamed PX4 GNSS topics are supported.
- **Rule-based detectors:** vibration level (per metric source) and
  accelerometer clipping; GPS accuracy, fix type, satellites and data loss;
  battery voltage sag, low voltage per cell and low remaining charge; attitude
  tracking error; motor saturation and imbalance. All thresholds configurable
  (`defaults.yaml`, documented in `docs/thresholds.md`); checks without data or
  without calibrated thresholds are reported as skipped.
- **Anomaly detection** (`--ml`): rolling robust z-score per signal and flight
  mode, calibrated on clean real flights; Isolation Forest available, off by
  default.
- **Reports:** single-file offline HTML report (timeline, evidence plot per
  finding, day / night theme), JSON, terminal table (`skytrace analyze`).
- **Assistant** (`skytrace chat`): LangGraph agent with tools over the parsed
  log (summary, findings, time series, events, plots, documentation search);
  local model by default (Ollama, `qwen2.5:7b`), any LiteLLM model with
  `--model`. A verification step flags every number, finding id and link in an
  answer that no tool returned.
- **Documentation search (RAG):** `skytrace docs build` indexes the PX4 and
  ArduPilot documentation locally (bge-m3, Qdrant local mode); answers cite the
  pages. How-to questions search the documentation up front.
- **Web UI and API** (`skytrace serve`, extra `web`): FastAPI backend, upload,
  findings, interactive plots, chat streamed as server-sent events; uploads are
  deleted after 24 h; no external requests; mobile layout.
- **Offline mode** (`SKYTRACE_MODE=offline`): local models enforced, every
  outgoing connection except to the model server refused; Docker image,
  docker-compose with Ollama, all-in-one image for network-isolated use.
- **Demo mode** for the Hugging Face Space: sample flights, chat on the samples
  only (an uploaded log is never sent to the cloud model), clear message when the
  model quota is used up.
- **Evaluation:** labelled PX4 SITL fault-injection campaign, detector
  evaluation, threshold calibration on public Flight Review logs, agent question
  set (local vs. cloud model), network-isolated end-to-end check.
- Sample flights in `samples/`; release workflow for PyPI, GHCR and GitHub
  releases; Apache-2.0 license.

### Known issues

- `filelock` 3.x (a dependency of LiteLLM) has known vulnerabilities
  (CVE-2026-112940 and two related ones: a local attacker who can write to the
  lock directory can make the process overwrite its own files). The fix is in
  filelock 4.2.1, which LiteLLM 1.106 does not allow yet (`filelock<4.0`); it will
  be picked up once LiteLLM lifts that limit.
- See *Limitations* in the README for the evaluation and detector limits.

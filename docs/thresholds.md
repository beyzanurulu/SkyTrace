# Configuration & Default Values

All tunable values live in [`src/skytrace/defaults.yaml`](../src/skytrace/defaults.yaml).
Nothing is hard-coded in the parsers or detectors. To override, pass a YAML
file that contains only the keys you want to change:

```yaml
# my_quad.yaml
parser:
  motors:
    count: 4
```

```python
from skytrace import FlightLog, load_config

log = FlightLog.from_file("flight.ulg", load_config("my_quad.yaml"))
```

Unknown keys are rejected so a typo does not silently fall back to the default.

## `parser`

| Key | Default | Unit | Meaning |
|---|---|---|---|
| `merge_tolerance_s` | `0.5` | s | When a slower topic (attitude setpoint, position setpoint) is aligned onto a faster time base, the latest sample at or before `t` is used only if it is at most this old. Older samples become NaN instead of a stale value. Cumulative counters (`clip_count`) ignore this tolerance. |
| `status_tolerance_s` | `1.5` | s | Same as `merge_tolerance_s`, but for ~1 Hz status topics (`vehicle_imu_status` vibration metrics). |
| `vibration_window_s` | `0.5` | s | Rolling window for the per-axis accelerometer standard deviation that becomes `vib_x/y/z` on PX4 logs. It is informational only (plots); no detector thresholds it, because `sensor_combined` is downsampled and filtered and therefore under-reads vibration. |
| `motors.use_log_params` | `true` | – | Read the PWM range from the log parameters. PX4: `PWM_MAIN_MINn`/`PWM_MAIN_MAXn` first, then the global `PWM_MIN`/`PWM_MAX`. ArduPilot: `MOT_PWM_MIN`/`MOT_PWM_MAX`, then `RC3_MIN`/`RC3_MAX` (what ArduPilot itself uses when `MOT_PWM_*` is 0). Values ≤ 0 ("unset") are skipped. |
| `motors.pwm_min_us` | `1000` | µs | Fallback PWM value for 0 % throttle when no log parameter is usable. |
| `motors.pwm_max_us` | `2000` | µs | Fallback PWM value for 100 % throttle. |
| `motors.count` | `null` | – | Number of motor channels. `null` means: use `CA_ROTOR_COUNT` (PX4) or the motor count of `FRAME_CLASS` (ArduPilot) from the log, otherwise all active outputs (and emit a warning). Set it explicitly for older logs that mix motors and servos on the same output group. |

## Schema notes (ArduPilot)

- Messages: `ATT`, `GPS` + `GPA` (EPH = `GPA.HAcc`), `BAT` (fallback `CURR`), `RCOU`, `VIBE`, `CTUN`, `MODE`, `ARM` (fallback `EV` 10/11), `ERR`, `MSG`, `PARM`. Only the lowest GPS / battery instance is used.
- `t` is seconds relative to the first `TimeUS` in the log. Angles are converted from degrees to radians; altitudes are negated into NED `z`.
- `vibration`: `vib_x/y/z` are `VibeX/Y/Z`, `accel_vib_metric` is their maximum, `clip_count` is the cumulative clip counter; with several IMUs the worst IMU wins at each time step. `gyro_vib_metric` is NaN. Thresholds come from the `ardupilot_vibe` block.
- `position` only has `z`, `vz` and `z_sp` (from `CTUN`); `x/y/vx/vy` are NaN.
- `ERR` subsystems named `FAILSAFE_*` become `failsafe` events, other non-zero codes `error`, code 0 on a non-failsafe subsystem `info` (resolved).
- ArduPilot has no cell-count parameter: set `detectors.battery.cells` to enable the per-cell battery checks.
- Firmware and vehicle type come from the version line ArduPilot logs at boot (`MSG`, e.g. `ArduCopter V4.5.7`).

## Schema notes (PX4)

- `t` is seconds relative to the ULog start timestamp. The first samples can be slightly negative because some topics are logged at subscription time.
- Angles are in radians. The attitude setpoint is taken from `q_d` when present, otherwise from `roll_body`/`pitch_body`/`yaw_body`.
- `motors` uses `actuator_motors` (already 0–1) when available, otherwise normalizes `actuator_outputs` (PWM) to 0–1. Values are clipped to [0, 1]. DShot outputs are not handled yet.
- `vibration` columns: `vib_x/y/z` (informational), `accel_vib_metric`, `gyro_vib_metric` and `clip_count` (cumulative). With several IMUs the value at each time step is the maximum over instances (the worst IMU). See the vibration source table below.
- Event kinds are `mode`, `arm`, `disarm`, `takeoff`, `landing`, `failsafe`, `error` (log level ≤ ERR), `warning` and `info`. `takeoff` / `landing` come from PX4's land detector (`vehicle_land_detected.landed`) and ArduPilot's `EV` NOT_LANDED (28) / LAND_COMPLETE (18).

## `detectors`

How every detector works:

- A finding opens when a value crosses the **warn** threshold for at least `min_duration_s`. Violations separated by at most `detectors.merge_gap_s` are merged first.
- The finding is **critical** if any sample inside it also crosses the **critical** threshold.
- `value` is the worst sample in the interval and `threshold` is the threshold that was crossed. The `summary` text is built only from these numbers.
- With `only_when_armed: true`, only samples between arm and disarm events are checked. A log without any arm/disarm events is checked in full.
- When a check cannot run (missing data, unknown cell count, unknown motor count), it is skipped and the reason is added to `DetectionResult.notes` instead of producing a finding.

**Source** says where a default comes from. *Heuristic* means it is our own starting value, to be calibrated on the labeled evaluation set.

| Key | Default | Unit | Source / meaning |
|---|---|---|---|
| `only_when_armed` | `true` | – | Ignore samples while disarmed. |
| `merge_gap_s` | `0.5` | s | Merge violations closer than this gap. `0` is allowed. |
| **vibration** | | | |
| `min_duration_s` | `1.0` | s | Applies to the vibration-level check. Heuristic. |
| `clip_merge_gap_s` | `5.0` | s | Clipping increments closer than this gap are reported as one finding. |
| `<source>.metric_warn` / `<source>.metric_critical` | see below | source units | Applied to `vibration.accel_vib_metric`. `null` means the source is not calibrated: the check is skipped and a note is added. A log is never compared with another source's thresholds. |
| `<source>.clip_critical_count` | `100` | clipped samples | A separate condition from the vibration level. Any clipping increment while armed is a warning; a burst totalling at least this many is critical. Heuristic for both sources, because PX4 counts clipped samples per axis and ArduPilot counts clip events per IMU. |

Vibration metric sources (`LogMetadata.vib_metric_source`):

| Source | `accel_vib_metric` | `gyro_vib_metric` | `clip_count` | Default thresholds |
|---|---|---|---|---|
| `px4_imu_status` | `vehicle_imu_status.accel_vibration_metric`, max over IMU instances | `gyro_vibration_metric`, max over instances | Per instance, the sum of `accel_clipping[0..2]`; max over instances | `null` until calibrated with `eval/calibrate_vibration.py`. The selection rule and the logs used are written as a comment in `defaults.yaml`. |
| `ardupilot_vibe` | `VIBE`: max of VibeX/Y/Z (m/s²) | – (NaN) | `VIBE` Clip0/1/2, max over IMUs | 30 / 60 from the ArduPilot vibration guidance (below 30 is acceptable, above 60 almost always causes problems) |

| **gps** | | | |
| `min_fix_type` | `3` | – | No fix of at least this type while armed is a finding: **critical** if a fix existed earlier in the log (fix lost), **warn** if the vehicle was armed before the first fix (e.g. ALTCTL takeoff without GPS). Satellite, EPH and HDOP checks only run while the fix is valid, because receivers report sentinel values without a fix. |
| `min_satellites` | `6` | – | PX4 `EKF2_REQ_NSATS` default. |
| `max_eph_m` | `3.0` | m | PX4 `EKF2_REQ_EPH` default. |
| `max_hdop` | `2.5` | – | Adapted from PX4 `EKF2_REQ_PDOP` (2.5). HDOP ≤ PDOP, so this limit is slightly lenient. |
| `min_duration_s` | `1.0` | s | Heuristic. |
| **battery** | | | |
| `cells` | `null` | – | Cell count. `null` means it is read from the log (`battery_status.cell_count`, then `BAT1_N_CELLS`/`BAT_N_CELLS`). If it is still unknown, the per-cell checks are skipped because a guessed count could produce false findings. |
| `cell_voltage_warn` / `cell_voltage_critical` | `3.5` / `3.3` | V/cell | 3.5 V corresponds to PX4's `BAT_V_EMPTY` (3.5 V in the fixture log; check the default for your firmware). 3.3 V is a heuristic for LiPo. |
| `sag_window_s` | `2.0` | s | Sag = rolling max over this window minus the current voltage. A fast drop counts as sag; slow discharge does not. |
| `sag_warn_v_per_cell` / `sag_critical_v_per_cell` | `0.3` / `0.5` | V/cell | 0.3 V is PX4's `BAT_V_LOAD_DROP` default. 0.5 V is a heuristic. |
| `sag_min_duration_s` | `0.0` | s | Sag is short by nature, so a single sample is enough. |
| `remaining_warn` / `remaining_critical` | `0.15` / `0.07` | fraction | PX4 `BAT_LOW_THR` / `BAT_CRIT_THR` defaults. |
| `min_duration_s` | `1.0` | s | Applies to the low-voltage and remaining checks. Heuristic. |
| **attitude** | | | |
| `error_warn_deg` / `error_critical_deg` | `10` / `20` | ° | \|setpoint − actual\| for roll and pitch, wrapped to ±180°. Heuristic. |
| `min_duration_s` | `1.0` | s | Heuristic. |
| **motors** | | | |
| `saturation_level` | `0.95` | 0–1 | A normalized output at or above this level counts as saturated. |
| `saturation_warn_s` / `saturation_critical_s` | `0.5` / `2.0` | s | How long a single motor must stay saturated. Heuristic. |
| `imbalance_window_s` | `5.0` | s | Rolling mean per motor. Imbalance = that mean minus the mean across all motors. |
| `imbalance_warn` / `imbalance_critical` | `0.15` / `0.25` | 0–1 | Heuristic. |
| `imbalance_min_duration_s` | `5.0` | s | Heuristic. The imbalance check is skipped when the motor count is unknown (`LogMetadata.motor_count_known = false`), because servo outputs would show up as imbalance. |

## `report`

| Key | Default | Unit | Meaning |
|---|---|---|---|
| `evidence_padding_s` | `10.0` | s | Context shown on each side of a finding's interval in its evidence plot. |
| `max_points_per_trace` | `4000` | points | Long series are reduced to at most this many points per trace. Each bucket keeps its minimum and maximum, so short peaks stay visible. |

## `anomaly` (ML anomaly detection, step 8)

Off by default: `run_detectors(log, ml=True)`, `skytrace analyze --ml`,
`eval/run_eval.py --ml`. Unsupervised and per log (`skytrace.anomaly.ml`); findings
use `detector = "ml_anomaly"`. ML findings that overlap a rule finding are dropped
and listed in `notes`, so a fault is reported once, by the rule that explains it.
The four alarm thresholds (`zscore.info` / `warn`, `iforest.min_feature_z` /
`warn_feature_z`) are **calibrated by false-alarm rate on clean real flights**
(`eval/calibrate_ml.py`, `eval/results/ml_calibration.{json,png}`): P80 / P95 of
the per-log statistic over 28 clean PX4 quadrotor flights, checked on 31 others.
There are no labels for unknown anomalies, so recall is not measured. The other
values are heuristic.

How the data is prepared:

- Armed, in-air periods (between `takeoff` and `landing` events; armed periods if a
  log has none) are split at flight-mode changes and every mode is analysed on its own, so a climb in takeoff or a descent in land is not
  compared with hover.
- `trim_s` seconds after the start and before the end of each segment are skipped
  (motor spin-up, touchdown, mode-switch transients).
- Signals are binned onto a `resample_hz` grid; gaps up to `max_fill_s` are
  forward-filled (1 Hz status topics).

| Key | Default | Unit | Meaning |
|---|---|---|---|
| `resample_hz` | `10.0` | Hz | Common grid for all signals. |
| `max_fill_s` | `2.0` | s | Forward-fill limit for slow topics. `0` is allowed. |
| `trim_s` | `5.0` | s | Skipped at both ends of each in-air single-mode segment (lift-off, touchdown, mode switches). `0` is allowed. |
| `signals.<name>` | see `defaults.yaml` | signal units | Noise floor per signal; `null` disables the signal. Signals: `roll_error_deg`, `pitch_error_deg`, `accel_vib_metric`, `battery_voltage`, `battery_current`, `motor_mean`, `motor_spread` (only with a known motor count), `vz`, `gps_eph` (only with a 3D fix). |
| **zscore** | | | Robust z = (x − trailing rolling median) / max(1.4826 × rolling MAD, noise floor). A trailing window flags an onset when it happens. |
| `window_s` | `30.0` | s | Rolling window. |
| `info` / `warn` | `13.3` / `25.0` | robust z | **Calibrated**: on the test flights info fired on 19 %, warn on 10 % (targets 20 % / 5 %). \|z\| above `info` for `min_duration_s` → `info` finding; above `warn` anywhere inside → `warn`. |
| `min_duration_s` | `1.0` | s | |
| **iforest** | | | One Isolation Forest per flight mode, on sliding windows. Features per signal: level (window mean minus the median of window means within `baseline_s`, so slow trends such as battery discharge do not count), std, slope, and the share of spectral energy above `hf_cutoff_hz`. The share is 0 when the window varies less than the signal's noise floor. |
| `enabled` | `false` | – | **Off by default**: after calibration it still flagged about a third of clean real flights (normal manoeuvres look anomalous). `--ml` then runs the rolling z-score only. Set `true` to try the forest. |
| `window_s` / `step_s` | `5.0` / `2.5` | s | Window length and step. |
| `baseline_s` | `60.0` | s | Span of neighbouring windows for the level feature. Windows without enough neighbours on both sides get a neutral level. |
| `hf_cutoff_hz` | `1.0` | Hz | Must be below `resample_hz / 2`. |
| `n_estimators` / `contamination` / `random_state` | `200` / `0.02` / `0` | – | scikit-learn parameters. The fixed seed makes results reproducible. |
| `min_windows` | `20` | windows | Modes with fewer windows are skipped and listed in a note. |
| `min_feature_z` | `59.7` | robust z | **Calibrated** (P80). Generalises poorly: info on 32 % of the test flights; real-flight variability alone reaches \|z\| 30-150. A window flagged by the forest is reported only if one feature deviates at least this much (feature vs. median / IQR of all windows of that mode). `contamination` alone flags some windows in every log, and the forest's score is a weak gate because adjacent anomalous windows mask each other. |
| `warn_feature_z` | `91.1` | robust z | **Calibrated** (P95); warn on 13 % of the test flights. |
| `top_features` | `3` | – | Most deviating features named in the summary. |

## `agent` (Q&A agent, step 9)

`skytrace chat <log>` (or `--ask "..."` for one question). LangGraph loop
model ⇄ tools, then a verification node; the model is reached through LiteLLM.
The tools (`skytrace.agent.tools`) return only numbers from the log and the
detectors, and do unit conversions themselves (angles in degrees), so the model
never has to compute a number. The verification node checks every number and
finding id in the answer against the tool outputs of the conversation and
appends a visible warning for anything it cannot back.

| Key | Default | Unit | Meaning |
|---|---|---|---|
| `model` | `ollama_chat/qwen2.5:7b` | – | Any LiteLLM model string. The local default keeps log data on the machine; a cloud model (e.g. `gemini/...` with `GEMINI_API_KEY`) receives the tool outputs. |
| `api_base` | `http://localhost:11434` | – | Model server (Ollama); `null` = the provider's default. |
| `temperature` | `0.0` | – | Deterministic answers. |
| `timeout_s` | `300` | s | Per model call; local models on a laptop GPU are slow. |
| `max_tool_rounds` | `6` | rounds | After this many tool rounds the model has to answer without more tools. |
| `max_series_points` | `200` | points | `query_series(agg="samples")` returns at most this many (min/max-preserving). |
| `number_rel_tol` | `0.005` | fraction | Verification: a number is backed if it equals a tool number rounded to the answer's decimals, or is within this relative tolerance of one (`%`: tool fraction × 100; signs ignored). |
| `prefetch` | `true` | – | The outputs of `get_flight_summary` and `list_findings` go into the system message up front (and count as evidence for the verification). Small local models often failed to call them or to read them back. |
| `prefetch_max_findings` | `30` | findings | At most this many findings up front; the model is told how many are not shown and can call `list_findings`. |
| `docs_prefetch_terms` | nasıl, neden, düzelt, azalt, how to, why, fix, reduce, ... (20) | – | If a word of the question starts with one (case-insensitive), `search_docs` runs with the question before the model is asked: qwen2.5:7b often answered how-to questions from memory, with made-up links. Needs the docs index. If the answer then cites none of the returned pages, the agent appends them ("Documentation searched"). |
| `docs_prefetch_min_score` | `0.5` | cosine score | The up-front search is used only if its best passage scores at least this (bge-m3). **Rough** calibration on 5 questions: off-topic ones ("Yarın hava nasıl olacak?", a recipe) reached at most 0.45, drone questions at least 0.52. Depends on the embedding model. |

Known limits of the verification: a small integer that happens to appear in a
tool output (a count, an index, a 3.0 threshold) is accepted even if the model used
it wrongly; digits glued to letters inside tool strings (firmware hashes) are not
evidence;
numbers derived by the model (sums, unit conversions it was not given) are
flagged even when correct, which is intended.

## `rag` (documentation search, step 10)

`skytrace docs build` fetches the PX4 user guide and the ArduPilot wiki (shallow,
sparse git checkout, text files only), keeps the pages whose path or title
matches a keyword, splits them at headings, embeds the chunks with a local model
and stores them in a Qdrant local-mode index. The agent's `search_docs` tool
returns the best chunks with their page url; the answer has to cite it. Values
found in the documentation (e.g. "below 30 m/s/s is acceptable") are guidance,
not measurements from the log. The verification node accepts them because they
are in a tool output, and it flags any url that no tool returned.

| Key | Default | Unit | Meaning |
|---|---|---|---|
| `embedding_model` | `ollama/bge-m3` | – | LiteLLM embedding model. Multilingual, so Turkish questions find English pages. The index records the model; searching with another model asks for a rebuild. |
| `api_base` | `http://localhost:11434` | – | Embedding server (Ollama); `null` = the provider's default. |
| `docs_dir` / `index_dir` | `data/docs` / `data/rag` | – | Checkouts and index; under `data/`, never committed. |
| `keywords` | log, vibration, tuning, pid, gps, battery, failsafe, ekf, imu, compass, esc, motor, crash, ... (25) | – | A page is indexed if its path or title contains one (case-insensitive). With the defaults: 3369 chunks (PX4 1945, ArduPilot 1424). |
| `chunk_chars` | `1500` | characters | Longer sections are split at paragraphs; chunks under 40 characters (navigation stubs) are dropped. |
| `top_k` | `4` | chunks | Results per `search_docs` call. |
| `excerpt_chars` | `800` | characters | Text per result handed to the model (keeps the context small for local models). |
| `batch_size` | `32` | chunks | Chunks per embedding request while building. |
| `px4` / `ardupilot` | see `defaults.yaml` | – | `repo`, `ref` (branch), sparse-checkout `include` patterns and the public `url_base` that page urls are built from. The commit of each checkout is stored in `data/rag/manifest.json`. |

## `api` (web API + UI, step 11)

`skytrace serve` starts FastAPI with the web UI. Uploads live in one folder per
analysis; parsed logs and chat sessions stay in memory for the most recently used
analyses and are rebuilt from the stored upload when needed (the chat history
then starts over). One chat question runs at a time. The chat stream sends each
tool call as it happens and then the verified answer in one piece; the model's
tokens are not streamed, because the numbers in them are not verified yet.

| Key | Default | Unit | Meaning |
|---|---|---|---|
| `host` / `port` | `127.0.0.1` / `8000` | – | Bind address. No authentication: keep it on localhost unless the network is trusted. |
| `storage_dir` | `data/uploads` | – | Uploaded logs (`<id>/meta.json`, the log, `plots/`); never committed. |
| `max_upload_mb` | `300` | MB | Larger uploads get 413, from the Content-Length header before the body is read, or while copying. |
| `retention_hours` | `24` | h | After this an analysis is no longer served (404) and its folder is deleted by the next sweep. |
| `cleanup_interval_s` | `600` | s | How often expired folders are swept (also once at startup). |
| `max_loaded` | `4` | analyses | Parsed logs + chat sessions kept in memory; the least recently used are dropped. |
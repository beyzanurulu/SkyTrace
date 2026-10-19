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
| `vibration_window_s` | `0.5` | s | Rolling window for the per-axis accelerometer standard deviation that becomes `vib_x/y/z` on PX4 logs. It is applied to the raw (logged) accelerometer samples, so the effective number of samples depends on the logging rate. |
| `motors.use_log_params` | `true` | – | Read the PWM range from the log parameters: `PWM_MAIN_MINn`/`PWM_MAIN_MAXn` first, then the global `PWM_MIN`/`PWM_MAX`. Values ≤ 0 (PX4's "unset") are skipped. |
| `motors.pwm_min_us` | `1000` | µs | Fallback PWM value for 0 % throttle when no log parameter is usable. |
| `motors.pwm_max_us` | `2000` | µs | Fallback PWM value for 100 % throttle. |
| `motors.count` | `null` | – | Number of motor channels. `null` means: use `CA_ROTOR_COUNT` from the log, otherwise all active outputs (and emit a warning). Set it explicitly for older logs that mix motors and servos on the same output group. |

## Schema notes (PX4)

- `t` is seconds relative to the ULog start timestamp. The first samples can be slightly negative because some topics are logged at subscription time.
- Angles are in radians. The attitude setpoint is taken from `q_d` when present, otherwise from `roll_body`/`pitch_body`/`yaw_body`.
- `motors` uses `actuator_motors` (already 0–1) when available, otherwise normalizes `actuator_outputs` (PWM) to 0–1. Values are clipped to [0, 1]. DShot outputs are not handled yet.
- `vibration.clip_count` is the cumulative sum of `vehicle_imu_status.accel_clipping[0..2]` for IMU instance 0.
- Event kinds are `mode`, `arm`, `disarm`, `failsafe`, `error` (log level ≤ ERR), `warning` and `info`.

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
| `accel_std_warn` / `accel_std_critical` | `30` / `60` | m/s² | ArduPilot vibration guidance for `VIBE` (below 30 is acceptable, above 60 almost always causes problems). On PX4 logs `vib_*` is the rolling std of the logged accelerometer, which only approximates `VIBE`. |
| `min_duration_s` | `1.0` | s | Heuristic. |
| `clip_critical_count` | `100` | events | Any clipping while armed is a warning. A burst of at least this many events is critical. Heuristic. |
| `clip_merge_gap_s` | `5.0` | s | Clipping events closer than this gap are reported as one finding. |
| **gps** | | | |
| `min_fix_type` | `3` | – | A fix below 3D while armed is always critical. |
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

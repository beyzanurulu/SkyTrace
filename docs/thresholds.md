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

Detector thresholds will be added to this file as detectors are implemented.

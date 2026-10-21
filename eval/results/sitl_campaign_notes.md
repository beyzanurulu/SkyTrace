# SITL campaign 2026-10-20: notes on `detector_eval.md`

Data: 35 labeled PX4 SITL logs (gz_x500, PX4 main 2026-10): 28 from the automated
plan (`eval/sitl_plan.py --seed 1`: 10 clean, 6 gps, 6 battery, 6 weak motor),
5 automated trial runs, 2 manual flights. Labels: `eval/label_sitl.py`
(injected commands, parameter changes and PX4's own battery / failure-detector
state; never SkyTrace thresholds). Matching rule unchanged: same detector, IoU >= 0.3.

## Result

- Recall 1.00 for every detector that has labels (24 / 24 faults found).
- gps and battery: precision 1.00.
- On the 13 clean flights, gps / battery / attitude / motors produced **no**
  findings; every false positive there is accelerometer clipping.
- Vibration has no SITL labels by design (Gazebo has no mechanical vibration);
  PX4 vibration thresholds stay uncalibrated (`null`).

## Where the 270 false positives come from

| Count | Cause |
|---:|---|
| 205 | One trial run (`sitl_try_motor_01`) where the weak motor flipped the vehicle; it lay armed upside down for ~3 min (forced disarm). Its motors label ends when the rpm cap was lifted, so all saturation / attitude findings after that count as false. |
| 36 | Accelerometer clipping, mostly 1-6 samples at touchdown or during a fault; 8 on clean flights. Any clipping is a warning today. |
| 14 | Attitude findings during a weak-motor fault: a real side effect, but the attitude ground truth is PX4's failure detector (60 deg), which did not trip. |
| 11 | Motor saturation bursts inside a motors label: correct in time, but a 1-2 s finding inside a 20-30 s label has IoU < 0.3. |
| 4 | Not near any label (2 motors, 2 attitude). |

## Known limitations (not fixed in this iteration)

- Crashed runs: labels end at the injection's end, not at disarm.
- IoU per finding penalises detectors that report one fault as several bursts.
- Attitude ground truth in SITL is PX4's failure detector, far stricter than
  the attitude detector's 10 / 20 deg thresholds.
- Clipping at touchdown is reported; a minimum clip count for `warn` would
  need real-flight data to choose.
- SITL only: no wind, no mechanical vibration, ideal sensors. Real-flight
  labels are still needed for vibration and for realistic noise.

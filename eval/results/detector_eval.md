# Detector evaluation

Generated 2026-10-21 by `eval/run_eval.py`. 35 labeled logs, match = same detector and IoU ≥ 0.3, findings below `warn` ignored. Precision is per finding, recall per labeled fault; `-` = undefined (no findings / no labels).

| Detector | Labels | Detected | Findings | Correct | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| vibration | 0 | 0 | 37 | 0 | 0.00 | - | - |
| gps | 8 | 8 | 8 | 8 | 1.00 | 1.00 | 1.00 |
| battery | 7 | 7 | 7 | 7 | 1.00 | 1.00 | 1.00 |
| attitude | 1 | 1 | 34 | 1 | 0.03 | 1.00 | 0.06 |
| motors | 8 | 8 | 223 | 23 | 0.10 | 1.00 | 0.19 |
| **all** | 24 | 24 | 309 | 39 | 0.13 | 1.00 | 0.22 |

## Missed faults

None.

## False positives

| Log | Detector | Severity | Interval (s) | Summary |
|---|---|---|---|---|
| sitl_auto_battery_01 | vibration | warn | 101.8-101.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 101.8 s and 101.8 s |
| sitl_auto_battery_03 | vibration | warn | 75.8-75.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 75.8 s and 75.8 s |
| sitl_auto_battery_04 | vibration | warn | 98.8-98.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 98.8 s and 98.8 s |
| sitl_auto_battery_05 | vibration | warn | 120.8-120.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 120.8 s and 120.8 s |
| sitl_auto_battery_06 | vibration | warn | 114.8-114.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 114.8 s and 114.8 s |
| sitl_auto_clean_01 | vibration | warn | 61.8-61.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 61.8 s and 61.8 s |
| sitl_auto_clean_02 | vibration | warn | 58.8-58.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 58.8 s and 58.8 s |
| sitl_auto_clean_04 | vibration | warn | 64.7-64.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 64.7 s and 64.7 s |
| sitl_auto_clean_05 | vibration | warn | 64.8-64.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 64.8 s and 64.8 s |
| sitl_auto_clean_06 | vibration | warn | 103.7-103.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 103.7 s and 103.7 s |
| sitl_auto_clean_08 | vibration | warn | 87.8-87.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 87.8 s and 87.8 s |
| sitl_auto_clean_09 | vibration | warn | 69.8-69.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 69.8 s and 69.8 s |
| sitl_auto_clean_10 | vibration | warn | 83.8-83.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 83.8 s and 83.8 s |
| sitl_auto_gps_01 | vibration | warn | 45.8-45.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 45.8 s and 45.8 s |
| sitl_auto_gps_02 | vibration | warn | 29.8-29.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 29.8 s and 29.8 s |
| sitl_auto_gps_03 | vibration | warn | 47.7-47.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 47.7 s and 47.7 s |
| sitl_auto_gps_04 | vibration | warn | 36.8-36.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 36.8 s and 36.8 s |
| sitl_auto_gps_05 | vibration | warn | 37.8-37.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 37.8 s and 37.8 s |
| sitl_auto_gps_06 | vibration | warn | 45.8-45.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 45.8 s and 45.8 s |
| sitl_auto_motor_01 | vibration | warn | 30.8-34.8 | Accelerometer clipping: 12 clipped samples (px4_imu_status) between 30.8 s and 34.8 s |
| sitl_auto_motor_01 | vibration | warn | 62.8-62.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 62.8 s and 62.8 s |
| sitl_auto_motor_01 | attitude | critical | 29.0-31.9 | Pitch not following setpoint: error up to 46.3° (threshold 20.0°) for 3.0 s |
| sitl_auto_motor_01 | attitude | critical | 30.1-32.4 | Roll not following setpoint: error up to 75.5° (threshold 20.0°) for 2.3 s |
| sitl_auto_motor_01 | attitude | warn | 44.5-53.6 | Roll not following setpoint: error up to 13.1° (threshold 10.0°) for 9.1 s |
| sitl_auto_motor_01 | attitude | critical | 52.5-54.8 | Pitch not following setpoint: error up to 21.3° (threshold 20.0°) for 2.3 s |
| sitl_auto_motor_01 | motors | critical | 28.8-31.4 | Motor 1 saturated (output >= 95%) for 2.6 s |
| sitl_auto_motor_01 | motors | warn | 31.5-33.2 | Motor 3 saturated (output >= 95%) for 1.7 s |
| sitl_auto_motor_01 | motors | warn | 31.7-33.1 | Motor 4 saturated (output >= 95%) for 1.4 s |
| sitl_auto_motor_01 | motors | warn | 53.7-54.6 | Motor 2 saturated (output >= 95%) for 0.9 s |
| sitl_auto_motor_02 | vibration | warn | 21.8-21.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 21.8 s and 21.8 s |
| sitl_auto_motor_02 | vibration | warn | 50.8-50.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 50.8 s and 50.8 s |
| sitl_auto_motor_02 | attitude | critical | 31.6-43.2 | Pitch not following setpoint: error up to 39.2° (threshold 20.0°) for 11.6 s |
| sitl_auto_motor_02 | attitude | critical | 31.9-43.2 | Roll not following setpoint: error up to 27.4° (threshold 20.0°) for 11.3 s |
| sitl_auto_motor_02 | motors | warn | 20.0-21.2 | Motor 1 saturated (output >= 95%) for 1.2 s |
| sitl_auto_motor_03 | vibration | warn | 32.7-33.8 | Accelerometer clipping: 7 clipped samples (px4_imu_status) between 32.7 s and 33.8 s |
| sitl_auto_motor_03 | vibration | warn | 68.8-68.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 68.8 s and 68.8 s |
| sitl_auto_motor_03 | attitude | critical | 31.0-33.2 | Pitch not following setpoint: error up to 25.3° (threshold 20.0°) for 2.2 s |
| sitl_auto_motor_03 | attitude | critical | 48.0-61.5 | Roll not following setpoint: error up to 34.1° (threshold 20.0°) for 13.5 s |
| sitl_auto_motor_03 | attitude | critical | 59.5-61.2 | Pitch not following setpoint: error up to 31.9° (threshold 20.0°) for 1.8 s |
| sitl_auto_motor_03 | motors | critical | 30.8-33.2 | Motor 1 saturated (output >= 95%) for 2.4 s |
| sitl_auto_motor_03 | motors | warn | 33.2-34.1 | Motor 4 saturated (output >= 95%) for 0.9 s |
| sitl_auto_motor_03 | motors | warn | 54.2-61.1 | Motor 4 runs below the motor average by up to 0.21 (threshold 0.15, 5 s mean) for 6.9 s |
| sitl_auto_motor_04 | vibration | warn | 31.8-31.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 31.8 s and 31.8 s |
| sitl_auto_motor_04 | vibration | warn | 57.8-57.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 57.8 s and 57.8 s |
| sitl_auto_motor_04 | attitude | critical | 40.6-49.8 | Roll not following setpoint: error up to 31.0° (threshold 20.0°) for 9.2 s |
| sitl_auto_motor_04 | attitude | critical | 48.8-49.9 | Pitch not following setpoint: error up to 35.8° (threshold 20.0°) for 1.1 s |
| sitl_auto_motor_04 | motors | warn | 29.9-30.9 | Motor 1 saturated (output >= 95%) for 1.0 s |
| sitl_auto_motor_05 | vibration | warn | 33.8-33.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 33.8 s and 33.8 s |
| sitl_auto_motor_05 | vibration | warn | 65.8-65.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 65.8 s and 65.8 s |
| sitl_auto_motor_05 | attitude | critical | 43.4-57.9 | Roll not following setpoint: error up to 30.4° (threshold 20.0°) for 14.5 s |
| sitl_auto_motor_05 | attitude | critical | 56.9-58.0 | Pitch not following setpoint: error up to 37.1° (threshold 20.0°) for 1.1 s |
| sitl_auto_motor_05 | motors | warn | 31.8-32.9 | Motor 1 saturated (output >= 95%) for 1.1 s |
| sitl_auto_motor_05 | motors | warn | 51.3-57.3 | Motor 4 runs below the motor average by up to 0.18 (threshold 0.15, 5 s mean) for 6.0 s |
| sitl_auto_motor_06 | vibration | warn | 35.7-36.7 | Accelerometer clipping: 10 clipped samples (px4_imu_status) between 35.7 s and 36.7 s |
| sitl_auto_motor_06 | vibration | warn | 72.7-72.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 72.7 s and 72.7 s |
| sitl_auto_motor_06 | attitude | critical | 36.5-64.4 | Roll not following setpoint: error up to 37.2° (threshold 20.0°) for 27.9 s |
| sitl_auto_motor_06 | motors | warn | 63.2-63.8 | Motor 2 saturated (output >= 95%) for 0.6 s |
| sitl_gps_01 | vibration | warn | 377.8-377.8 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 377.8 s and 377.8 s |
| sitl_try_battery_01 | vibration | warn | 102.7-102.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 102.7 s and 102.7 s |
| sitl_try_gps_01 | vibration | warn | 46.7-46.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 46.7 s and 46.7 s |
| sitl_try_motor_01 | vibration | warn | 34.8-38.8 | Accelerometer clipping: 50 clipped samples (px4_imu_status) between 34.8 s and 38.8 s |
| sitl_try_motor_01 | attitude | critical | 35.2-41.4 | Pitch not following setpoint: error up to 106.3° (threshold 20.0°) for 6.2 s |
| sitl_try_motor_01 | attitude | warn | 41.9-45.6 | Pitch not following setpoint: error up to 17.3° (threshold 10.0°) for 3.6 s |
| sitl_try_motor_01 | attitude | warn | 46.2-57.5 | Pitch not following setpoint: error up to 17.6° (threshold 10.0°) for 11.3 s |
| sitl_try_motor_01 | attitude | warn | 58.6-72.6 | Pitch not following setpoint: error up to 17.6° (threshold 10.0°) for 14.0 s |
| sitl_try_motor_01 | attitude | warn | 75.1-83.1 | Pitch not following setpoint: error up to 17.7° (threshold 10.0°) for 8.0 s |
| sitl_try_motor_01 | attitude | warn | 84.6-106.7 | Pitch not following setpoint: error up to 17.7° (threshold 10.0°) for 22.1 s |
| sitl_try_motor_01 | attitude | warn | 108.1-122.4 | Pitch not following setpoint: error up to 17.6° (threshold 10.0°) for 14.3 s |
| sitl_try_motor_01 | attitude | warn | 123.6-130.0 | Pitch not following setpoint: error up to 17.7° (threshold 10.0°) for 6.4 s |
| sitl_try_motor_01 | attitude | warn | 130.5-132.1 | Pitch not following setpoint: error up to 12.1° (threshold 10.0°) for 1.6 s |
| sitl_try_motor_01 | attitude | warn | 152.1-153.8 | Pitch not following setpoint: error up to 16.7° (threshold 10.0°) for 1.7 s |
| sitl_try_motor_01 | attitude | warn | 156.9-161.3 | Pitch not following setpoint: error up to 17.4° (threshold 10.0°) for 4.4 s |
| sitl_try_motor_01 | attitude | warn | 161.9-167.0 | Pitch not following setpoint: error up to 17.6° (threshold 10.0°) for 5.1 s |
| sitl_try_motor_01 | attitude | warn | 167.6-178.0 | Pitch not following setpoint: error up to 17.6° (threshold 10.0°) for 10.4 s |
| sitl_try_motor_01 | attitude | warn | 180.0-183.3 | Pitch not following setpoint: error up to 17.2° (threshold 10.0°) for 3.3 s |
| sitl_try_motor_01 | attitude | warn | 185.4-225.8 | Pitch not following setpoint: error up to 17.8° (threshold 10.0°) for 40.4 s |
| sitl_try_motor_01 | attitude | warn | 226.7-243.1 | Pitch not following setpoint: error up to 17.8° (threshold 10.0°) for 16.4 s |
| sitl_try_motor_01 | attitude | warn | 244.0-245.7 | Pitch not following setpoint: error up to 16.0° (threshold 10.0°) for 1.7 s |
| sitl_try_motor_01 | motors | critical | 33.4-36.3 | Motor 1 saturated (output >= 95%) for 2.9 s |
| sitl_try_motor_01 | motors | warn | 35.4-36.5 | Motor 2 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | critical | 36.4-39.0 | Motor 4 saturated (output >= 95%) for 2.6 s |
| sitl_try_motor_01 | motors | warn | 36.9-37.7 | Motor 3 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 37.0-38.1 | Motor 1 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | critical | 37.1-39.8 | Motor 2 saturated (output >= 95%) for 2.7 s |
| sitl_try_motor_01 | motors | warn | 39.1-40.5 | Motor 3 saturated (output >= 95%) for 1.4 s |
| sitl_try_motor_01 | motors | warn | 39.5-40.8 | Motor 1 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | warn | 41.2-42.5 | Motor 3 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | warn | 41.5-42.5 | Motor 1 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | critical | 42.7-46.1 | Motor 2 saturated (output >= 95%) for 3.4 s |
| sitl_try_motor_01 | motors | critical | 43.2-45.9 | Motor 4 saturated (output >= 95%) for 2.7 s |
| sitl_try_motor_01 | motors | critical | 45.6-53.4 | Motor 2 runs above the motor average by up to 0.44 (threshold 0.25, 5 s mean) for 7.8 s |
| sitl_try_motor_01 | motors | critical | 45.7-52.6 | Motor 3 runs below the motor average by up to 0.41 (threshold 0.25, 5 s mean) for 6.9 s |
| sitl_try_motor_01 | motors | critical | 45.7-52.6 | Motor 4 runs above the motor average by up to 0.40 (threshold 0.25, 5 s mean) for 6.9 s |
| sitl_try_motor_01 | motors | critical | 46.6-51.0 | Motor 4 saturated (output >= 95%) for 4.4 s |
| sitl_try_motor_01 | motors | critical | 46.7-51.0 | Motor 2 saturated (output >= 95%) for 4.3 s |
| sitl_try_motor_01 | motors | warn | 51.1-52.9 | Motor 3 saturated (output >= 95%) for 1.8 s |
| sitl_try_motor_01 | motors | warn | 51.8-52.6 | Motor 1 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | critical | 53.0-55.4 | Motor 2 saturated (output >= 95%) for 2.4 s |
| sitl_try_motor_01 | motors | warn | 53.5-55.4 | Motor 4 saturated (output >= 95%) for 1.9 s |
| sitl_try_motor_01 | motors | warn | 55.6-56.9 | Motor 1 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | warn | 57.3-58.8 | Motor 2 saturated (output >= 95%) for 1.5 s |
| sitl_try_motor_01 | motors | warn | 58.0-58.8 | Motor 4 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 58.9-59.9 | Motor 3 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | warn | 60.0-61.2 | Motor 4 saturated (output >= 95%) for 1.2 s |
| sitl_try_motor_01 | motors | warn | 60.1-61.6 | Motor 2 saturated (output >= 95%) for 1.5 s |
| sitl_try_motor_01 | motors | warn | 60.7-65.7 | Motor 1 runs below the motor average by up to 0.24 (threshold 0.15, 5 s mean) for 5.0 s |
| sitl_try_motor_01 | motors | warn | 61.1-62.4 | Motor 3 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | critical | 62.7-65.7 | Motor 2 saturated (output >= 95%) for 3.0 s |
| sitl_try_motor_01 | motors | warn | 63.2-63.8 | Motor 4 saturated (output >= 95%) for 0.6 s |
| sitl_try_motor_01 | motors | warn | 65.3-65.9 | Motor 1 saturated (output >= 95%) for 0.6 s |
| sitl_try_motor_01 | motors | warn | 65.6-66.5 | Motor 3 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | warn | 66.3-67.0 | Motor 4 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | critical | 67.1-69.9 | Motor 1 saturated (output >= 95%) for 2.8 s |
| sitl_try_motor_01 | motors | critical | 67.5-70.1 | Motor 3 saturated (output >= 95%) for 2.6 s |
| sitl_try_motor_01 | motors | critical | 69.4-74.5 | Motor 1 runs above the motor average by up to 0.32 (threshold 0.25, 5 s mean) for 5.1 s |
| sitl_try_motor_01 | motors | critical | 69.4-74.6 | Motor 2 runs below the motor average by up to 0.32 (threshold 0.25, 5 s mean) for 5.2 s |
| sitl_try_motor_01 | motors | critical | 69.4-75.1 | Motor 3 runs above the motor average by up to 0.38 (threshold 0.25, 5 s mean) for 5.7 s |
| sitl_try_motor_01 | motors | critical | 69.5-75.0 | Motor 4 runs below the motor average by up to 0.37 (threshold 0.25, 5 s mean) for 5.5 s |
| sitl_try_motor_01 | motors | warn | 70.2-71.1 | Motor 2 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | critical | 70.5-73.5 | Motor 1 saturated (output >= 95%) for 3.0 s |
| sitl_try_motor_01 | motors | critical | 71.4-73.7 | Motor 3 saturated (output >= 95%) for 2.3 s |
| sitl_try_motor_01 | motors | critical | 73.8-78.9 | Motor 2 saturated (output >= 95%) for 5.1 s |
| sitl_try_motor_01 | motors | critical | 74.1-78.2 | Motor 4 saturated (output >= 95%) for 4.1 s |
| sitl_try_motor_01 | motors | warn | 78.6-79.8 | Motor 1 saturated (output >= 95%) for 1.2 s |
| sitl_try_motor_01 | motors | warn | 79.9-80.9 | Motor 2 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | warn | 80.4-81.3 | Motor 4 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | warn | 81.0-82.8 | Motor 1 saturated (output >= 95%) for 1.8 s |
| sitl_try_motor_01 | motors | warn | 82.1-82.6 | Motor 3 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 82.7-84.5 | Motor 4 saturated (output >= 95%) for 1.8 s |
| sitl_try_motor_01 | motors | warn | 83.2-84.5 | Motor 2 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | critical | 84.6-88.5 | Motor 3 saturated (output >= 95%) for 3.9 s |
| sitl_try_motor_01 | motors | critical | 85.0-88.5 | Motor 1 saturated (output >= 95%) for 3.5 s |
| sitl_try_motor_01 | motors | critical | 88.6-94.5 | Motor 2 saturated (output >= 95%) for 5.9 s |
| sitl_try_motor_01 | motors | critical | 89.4-94.6 | Motor 4 saturated (output >= 95%) for 5.2 s |
| sitl_try_motor_01 | motors | critical | 92.0-97.1 | Motor 1 runs below the motor average by up to 0.46 (threshold 0.25, 5 s mean) for 5.1 s |
| sitl_try_motor_01 | motors | warn | 94.9-95.6 | Motor 1 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | warn | 95.7-97.3 | Motor 3 saturated (output >= 95%) for 1.6 s |
| sitl_try_motor_01 | motors | warn | 96.7-97.2 | Motor 1 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 97.4-98.6 | Motor 2 saturated (output >= 95%) for 1.2 s |
| sitl_try_motor_01 | motors | critical | 99.1-104.7 | Motor 1 saturated (output >= 95%) for 5.6 s |
| sitl_try_motor_01 | motors | critical | 99.2-116.9 | Motor 3 runs above the motor average by up to 0.47 (threshold 0.25, 5 s mean) for 17.7 s |
| sitl_try_motor_01 | motors | critical | 99.3-117.1 | Motor 4 runs below the motor average by up to 0.47 (threshold 0.25, 5 s mean) for 17.8 s |
| sitl_try_motor_01 | motors | critical | 99.5-104.6 | Motor 3 saturated (output >= 95%) for 5.1 s |
| sitl_try_motor_01 | motors | critical | 101.1-117.2 | Motor 1 runs above the motor average by up to 0.48 (threshold 0.25, 5 s mean) for 16.1 s |
| sitl_try_motor_01 | motors | critical | 101.2-117.0 | Motor 2 runs below the motor average by up to 0.48 (threshold 0.25, 5 s mean) for 15.8 s |
| sitl_try_motor_01 | motors | warn | 104.8-105.9 | Motor 4 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | critical | 106.0-114.1 | Motor 1 saturated (output >= 95%) for 8.1 s |
| sitl_try_motor_01 | motors | critical | 106.7-114.6 | Motor 3 saturated (output >= 95%) for 7.9 s |
| sitl_try_motor_01 | motors | warn | 114.7-115.6 | Motor 2 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | warn | 115.7-116.5 | Motor 3 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 115.8-116.6 | Motor 1 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | critical | 116.7-120.4 | Motor 4 saturated (output >= 95%) for 3.7 s |
| sitl_try_motor_01 | motors | critical | 117.3-120.7 | Motor 2 saturated (output >= 95%) for 3.4 s |
| sitl_try_motor_01 | motors | critical | 118.6-124.2 | Motor 3 runs below the motor average by up to 0.30 (threshold 0.25, 5 s mean) for 5.6 s |
| sitl_try_motor_01 | motors | critical | 118.7-124.0 | Motor 2 runs above the motor average by up to 0.30 (threshold 0.25, 5 s mean) for 5.3 s |
| sitl_try_motor_01 | motors | critical | 118.7-124.4 | Motor 4 runs above the motor average by up to 0.30 (threshold 0.25, 5 s mean) for 5.7 s |
| sitl_try_motor_01 | motors | critical | 118.8-124.2 | Motor 1 runs below the motor average by up to 0.30 (threshold 0.25, 5 s mean) for 5.4 s |
| sitl_try_motor_01 | motors | warn | 120.6-121.8 | Motor 1 saturated (output >= 95%) for 1.2 s |
| sitl_try_motor_01 | motors | warn | 120.8-121.9 | Motor 3 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | warn | 121.6-122.1 | Motor 2 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 122.2-123.9 | Motor 4 saturated (output >= 95%) for 1.7 s |
| sitl_try_motor_01 | motors | critical | 124.2-127.2 | Motor 3 saturated (output >= 95%) for 3.0 s |
| sitl_try_motor_01 | motors | critical | 124.8-127.7 | Motor 1 saturated (output >= 95%) for 2.9 s |
| sitl_try_motor_01 | motors | critical | 127.4-130.7 | Motor 4 saturated (output >= 95%) for 3.3 s |
| sitl_try_motor_01 | motors | critical | 128.1-130.5 | Motor 2 saturated (output >= 95%) for 2.4 s |
| sitl_try_motor_01 | motors | warn | 130.8-131.3 | Motor 1 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 131.4-132.7 | Motor 4 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | warn | 131.7-132.5 | Motor 2 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | critical | 132.8-134.8 | Motor 1 saturated (output >= 95%) for 2.0 s |
| sitl_try_motor_01 | motors | warn | 133.5-134.8 | Motor 3 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | warn | 135.1-136.0 | Motor 4 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | warn | 136.1-137.0 | Motor 1 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | warn | 137.7-138.7 | Motor 3 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | warn | 137.9-138.7 | Motor 1 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | critical | 138.8-141.3 | Motor 2 saturated (output >= 95%) for 2.5 s |
| sitl_try_motor_01 | motors | warn | 140.0-141.1 | Motor 4 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | warn | 141.4-142.4 | Motor 3 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | warn | 142.5-143.3 | Motor 2 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 142.6-143.3 | Motor 4 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | critical | 143.6-146.1 | Motor 1 saturated (output >= 95%) for 2.5 s |
| sitl_try_motor_01 | motors | critical | 144.1-146.2 | Motor 3 saturated (output >= 95%) for 2.1 s |
| sitl_try_motor_01 | motors | critical | 146.5-151.5 | Motor 4 saturated (output >= 95%) for 5.0 s |
| sitl_try_motor_01 | motors | critical | 147.6-151.3 | Motor 2 saturated (output >= 95%) for 3.7 s |
| sitl_try_motor_01 | motors | warn | 151.6-152.3 | Motor 1 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | critical | 153.1-155.7 | Motor 1 saturated (output >= 95%) for 2.6 s |
| sitl_try_motor_01 | motors | warn | 153.6-154.4 | Motor 3 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 155.1-155.6 | Motor 3 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 155.8-156.7 | Motor 4 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | warn | 157.0-157.7 | Motor 3 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | warn | 157.8-158.6 | Motor 4 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 158.7-159.2 | Motor 1 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 159.3-161.2 | Motor 4 saturated (output >= 95%) for 1.9 s |
| sitl_try_motor_01 | motors | warn | 159.6-160.6 | Motor 2 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | warn | 160.8-161.6 | Motor 1 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | warn | 161.7-163.3 | Motor 2 saturated (output >= 95%) for 1.6 s |
| sitl_try_motor_01 | motors | warn | 162.1-163.4 | Motor 4 saturated (output >= 95%) for 1.3 s |
| sitl_try_motor_01 | motors | warn | 164.0-165.1 | Motor 3 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | warn | 165.8-166.5 | Motor 1 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | warn | 166.1-167.7 | Motor 3 saturated (output >= 95%) for 1.6 s |
| sitl_try_motor_01 | motors | warn | 167.1-167.6 | Motor 1 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | critical | 167.4-174.1 | Motor 2 runs below the motor average by up to 0.34 (threshold 0.25, 5 s mean) for 6.7 s |
| sitl_try_motor_01 | motors | critical | 167.5-173.2 | Motor 3 runs above the motor average by up to 0.41 (threshold 0.25, 5 s mean) for 5.7 s |
| sitl_try_motor_01 | motors | critical | 167.6-174.1 | Motor 1 runs above the motor average by up to 0.33 (threshold 0.25, 5 s mean) for 6.5 s |
| sitl_try_motor_01 | motors | critical | 167.7-173.4 | Motor 4 runs below the motor average by up to 0.38 (threshold 0.25, 5 s mean) for 5.7 s |
| sitl_try_motor_01 | motors | critical | 168.3-171.4 | Motor 1 saturated (output >= 95%) for 3.1 s |
| sitl_try_motor_01 | motors | critical | 168.7-171.0 | Motor 3 saturated (output >= 95%) for 2.3 s |
| sitl_try_motor_01 | motors | warn | 171.5-173.4 | Motor 4 saturated (output >= 95%) for 1.9 s |
| sitl_try_motor_01 | motors | warn | 171.7-173.3 | Motor 2 saturated (output >= 95%) for 1.6 s |
| sitl_try_motor_01 | motors | warn | 174.2-174.9 | Motor 4 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | warn | 174.3-174.9 | Motor 2 saturated (output >= 95%) for 0.6 s |
| sitl_try_motor_01 | motors | critical | 175.0-177.9 | Motor 3 saturated (output >= 95%) for 2.9 s |
| sitl_try_motor_01 | motors | critical | 175.4-177.8 | Motor 1 saturated (output >= 95%) for 2.4 s |
| sitl_try_motor_01 | motors | critical | 177.4-182.5 | Motor 3 runs above the motor average by up to 0.31 (threshold 0.25, 5 s mean) for 5.1 s |
| sitl_try_motor_01 | motors | critical | 177.5-184.1 | Motor 2 runs below the motor average by up to 0.37 (threshold 0.25, 5 s mean) for 6.6 s |
| sitl_try_motor_01 | motors | critical | 177.6-182.6 | Motor 1 runs above the motor average by up to 0.36 (threshold 0.25, 5 s mean) for 5.0 s |
| sitl_try_motor_01 | motors | warn | 178.6-180.5 | Motor 1 saturated (output >= 95%) for 1.9 s |
| sitl_try_motor_01 | motors | warn | 179.5-180.9 | Motor 3 saturated (output >= 95%) for 1.4 s |
| sitl_try_motor_01 | motors | warn | 180.8-181.5 | Motor 4 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | warn | 181.4-182.5 | Motor 1 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | warn | 182.0-182.5 | Motor 3 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | critical | 182.6-186.9 | Motor 4 saturated (output >= 95%) for 4.3 s |
| sitl_try_motor_01 | motors | critical | 184.2-186.9 | Motor 2 saturated (output >= 95%) for 2.7 s |
| sitl_try_motor_01 | motors | critical | 187.0-193.0 | Motor 1 saturated (output >= 95%) for 6.0 s |
| sitl_try_motor_01 | motors | critical | 189.1-193.2 | Motor 3 saturated (output >= 95%) for 4.1 s |
| sitl_try_motor_01 | motors | warn | 193.3-195.1 | Motor 2 saturated (output >= 95%) for 1.8 s |
| sitl_try_motor_01 | motors | critical | 194.6-197.6 | Motor 4 saturated (output >= 95%) for 3.0 s |
| sitl_try_motor_01 | motors | critical | 195.7-197.7 | Motor 2 saturated (output >= 95%) for 2.0 s |
| sitl_try_motor_01 | motors | warn | 197.8-199.7 | Motor 3 saturated (output >= 95%) for 1.9 s |
| sitl_try_motor_01 | motors | warn | 198.7-199.8 | Motor 1 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | warn | 199.9-200.8 | Motor 4 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | critical | 201.1-204.0 | Motor 3 saturated (output >= 95%) for 2.9 s |
| sitl_try_motor_01 | motors | critical | 201.6-204.1 | Motor 1 saturated (output >= 95%) for 2.5 s |
| sitl_try_motor_01 | motors | critical | 204.3-206.9 | Motor 4 saturated (output >= 95%) for 2.6 s |
| sitl_try_motor_01 | motors | warn | 206.3-207.0 | Motor 2 saturated (output >= 95%) for 0.7 s |
| sitl_try_motor_01 | motors | warn | 207.2-207.8 | Motor 3 saturated (output >= 95%) for 0.6 s |
| sitl_try_motor_01 | motors | warn | 207.9-208.9 | Motor 2 saturated (output >= 95%) for 1.0 s |
| sitl_try_motor_01 | motors | warn | 209.0-210.2 | Motor 3 saturated (output >= 95%) for 1.2 s |
| sitl_try_motor_01 | motors | warn | 209.5-210.3 | Motor 1 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | critical | 210.4-213.4 | Motor 4 saturated (output >= 95%) for 3.0 s |
| sitl_try_motor_01 | motors | critical | 210.9-213.3 | Motor 2 saturated (output >= 95%) for 2.4 s |
| sitl_try_motor_01 | motors | warn | 213.5-215.1 | Motor 1 saturated (output >= 95%) for 1.6 s |
| sitl_try_motor_01 | motors | warn | 214.5-215.6 | Motor 3 saturated (output >= 95%) for 1.1 s |
| sitl_try_motor_01 | motors | warn | 215.9-216.4 | Motor 4 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | warn | 216.4-217.3 | Motor 2 saturated (output >= 95%) for 0.9 s |
| sitl_try_motor_01 | motors | critical | 217.2-219.4 | Motor 3 saturated (output >= 95%) for 2.2 s |
| sitl_try_motor_01 | motors | critical | 218.7-221.3 | Motor 1 saturated (output >= 95%) for 2.6 s |
| sitl_try_motor_01 | motors | warn | 220.1-221.3 | Motor 3 saturated (output >= 95%) for 1.2 s |
| sitl_try_motor_01 | motors | critical | 221.4-230.6 | Motor 4 saturated (output >= 95%) for 9.2 s |
| sitl_try_motor_01 | motors | warn | 222.1-223.7 | Motor 2 saturated (output >= 95%) for 1.6 s |
| sitl_try_motor_01 | motors | critical | 224.5-229.6 | Motor 2 saturated (output >= 95%) for 5.1 s |
| sitl_try_motor_01 | motors | critical | 224.5-232.5 | Motor 4 runs above the motor average by up to 0.51 (threshold 0.25, 5 s mean) for 8.0 s |
| sitl_try_motor_01 | motors | critical | 224.6-232.4 | Motor 3 runs below the motor average by up to 0.49 (threshold 0.25, 5 s mean) for 7.8 s |
| sitl_try_motor_01 | motors | critical | 225.2-232.3 | Motor 1 runs below the motor average by up to 0.47 (threshold 0.25, 5 s mean) for 7.1 s |
| sitl_try_motor_01 | motors | critical | 225.3-232.2 | Motor 2 runs above the motor average by up to 0.45 (threshold 0.25, 5 s mean) for 6.9 s |
| sitl_try_motor_01 | motors | warn | 230.2-230.7 | Motor 2 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | critical | 230.8-239.5 | Motor 3 saturated (output >= 95%) for 8.7 s |
| sitl_try_motor_01 | motors | warn | 231.8-232.3 | Motor 1 saturated (output >= 95%) for 0.5 s |
| sitl_try_motor_01 | motors | critical | 232.9-237.3 | Motor 1 saturated (output >= 95%) for 4.4 s |
| sitl_try_motor_01 | motors | critical | 233.9-241.5 | Motor 3 runs above the motor average by up to 0.45 (threshold 0.25, 5 s mean) for 7.6 s |
| sitl_try_motor_01 | motors | critical | 234.1-241.1 | Motor 4 runs below the motor average by up to 0.44 (threshold 0.25, 5 s mean) for 7.0 s |
| sitl_try_motor_01 | motors | critical | 234.2-241.0 | Motor 2 runs below the motor average by up to 0.44 (threshold 0.25, 5 s mean) for 6.8 s |
| sitl_try_motor_01 | motors | critical | 234.3-240.7 | Motor 1 runs above the motor average by up to 0.44 (threshold 0.25, 5 s mean) for 6.4 s |
| sitl_try_motor_01 | motors | warn | 238.6-239.4 | Motor 1 saturated (output >= 95%) for 0.8 s |
| sitl_try_motor_01 | motors | critical | 239.8-245.6 | Motor 4 saturated (output >= 95%) for 5.8 s |
| sitl_try_motor_01 | motors | critical | 240.7-245.6 | Motor 2 saturated (output >= 95%) for 4.9 s |
| sitl_try_motor_02 | vibration | warn | 41.8-41.8 | Accelerometer clipping: 6 clipped samples (px4_imu_status) between 41.8 s and 41.8 s |
| sitl_try_motor_02 | vibration | warn | 75.7-75.7 | Accelerometer clipping: 1 clipped samples (px4_imu_status) between 75.7 s and 75.7 s |
| sitl_try_motor_02 | attitude | critical | 47.1-67.2 | Pitch not following setpoint: error up to 34.0° (threshold 20.0°) for 20.0 s |
| sitl_try_motor_02 | attitude | critical | 48.8-67.1 | Roll not following setpoint: error up to 33.5° (threshold 20.0°) for 18.3 s |
| sitl_try_motor_02 | motors | warn | 39.6-41.1 | Motor 1 saturated (output >= 95%) for 1.5 s |

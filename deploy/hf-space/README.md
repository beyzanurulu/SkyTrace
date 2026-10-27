---
title: SkyTrace
emoji: 🛩️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
license: apache-2.0
short_description: PX4 / ArduPilot flight log analysis and Q&A
---

# SkyTrace demo

Upload a PX4 `.ulg` or ArduPilot `.bin` flight log, or open one of the sample
flights, to see the findings of the rule and anomaly detectors with their plots.

- **Chat** is available on the sample flights (simulated PX4 flights with a GPS
  loss, a weak motor and a low battery). It uses a cloud model with a small free
  quota; if the quota is used up, try again later.
- **Your own logs** are analysed here but never sent to the cloud model, and are
  deleted after one hour. To ask questions about them, run SkyTrace on your own
  machine with a local model: <https://github.com/beyzanurulu/SkyTrace#quick-start>.

Source, documentation and evaluation: <https://github.com/beyzanurulu/SkyTrace>

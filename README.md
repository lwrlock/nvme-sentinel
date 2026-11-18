# NVMe Sentinel

[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)
[![Engine: C + NVMe Sysfs](https://img.shields.io/badge/Engine-C%20%2B%20PCIe%20Gen4%20APST-fb923c.svg)](#)
[![UI: GTK4 Titanium-Copper](https://img.shields.io/badge/UI-GTK4%20%2B%20Cairo-fdba74.svg)](#)

**Real-time Linux NVMe controller thermal monitor, APST PS4 sleep-latency auditor, PCIe link speed probe, and multi-queue IOPS telemetry cockpit in C and Python/GTK4.**

<p align="center">
  <img src="docs/screenshots/showcase.gif" alt="NVMe Sentinel Telemetry" width="900"/>
</p>

## Highlights

- **PCIe & Controller Telemetry:** Inspects live Gen4/Gen5 link speed/width (`16.0 GT/s PCIe x4`), Runtime PM status, and `hwmon` Composite temperatures (`°C`).
- **APST Deep Sleep Budget:** Tracks `nvme_core.default_ps_max_latency_us` (`5500 µs` PS4 readiness) and block queue knobs (`scheduler`, `read_ahead_kb`, `rq_affinity`, `nr_requests`).
- **Live Block IOPS & Throughput:** Measures `/sys/block/nvme*/stat` deltas for Read/Write IOPS and MB/s waveforms without triggering root I/O stalls.

## Build & Run

```bash
make test
./nvme-sentinel-probe --json
PYTHONPATH=src /usr/bin/python3 -m nvme_sentinel.gui
```

MIT License — Copyright (c) 2026 Furkan (**lwrlock**). Built with assistance from Google DeepMind Antigravity.

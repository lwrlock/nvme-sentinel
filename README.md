# NVMe Sentinel

[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)
[![Engine: C + NVMe Sysfs](https://img.shields.io/badge/Engine-C%20%2B%20PCIe%20Gen4%20APST-fb923c.svg)](#architecture)
[![UI: GTK4 Titanium-Copper](https://img.shields.io/badge/UI-GTK4%20%2B%20Cairo-fdba74.svg)](#gallery)
[![Suite: FF Systems](https://img.shields.io/badge/Suite-FF%20Linux%20Systems-6366f1.svg)](https://github.com/lwrlock/ff-power-manager)

**Real-time Linux NVMe controller thermal monitor, APST PS4 sleep-latency auditor, PCIe link speed probe, and multi-queue IOPS telemetry cockpit in C and Python/GTK4.**

<p align="center">
  <img src="docs/screenshots/showcase.gif" alt="NVMe Sentinel Telemetry" width="900"/>
</p>

## Architecture

```mermaid
flowchart LR
  NV["/sys/class/nvme/nvme0 + hwmon temps"] --> C["nvme-sentinel-probe Native C Engine"]
  BLK["/sys/block/nvme0n1/stat + queue/*"] --> C
  APST["nvme_core.default_ps_max_latency_us"] --> C
  C -->|IOPS, MB/s & Link State| UI["GTK4 Titanium-Copper Storage Cockpit"]
```

## Highlights

- **PCIe & Controller Telemetry:** Inspects live Gen4/Gen5 link speed/width (`16.0 GT/s PCIe x4`), Runtime PM status, and `hwmon` Composite temperatures (`°C`).
- **APST Deep Sleep Budget:** Tracks `nvme_core.default_ps_max_latency_us` (`5500 µs` PS4 readiness) and block queue knobs (`scheduler`, `read_ahead_kb`, `rq_affinity`, `nr_requests`).
- **Live Block IOPS & Throughput:** Measures `/sys/block/nvme*/stat` deltas for Read/Write IOPS and MB/s waveforms cleanly.

<details>
<summary><b>Full-Resolution UI Screenshot</b></summary>

<p align="center">
  <img src="docs/screenshots/overview.png" alt="NVMe Sentinel Overview" width="880"/>
</p>

</details>

## Build & Run

```bash
make test
./nvme-sentinel-probe --json
PYTHONPATH=src /usr/bin/python3 -m nvme_sentinel.gui
```

---

### FF Linux Kernel & Systems Suite
[FF Power Manager](https://github.com/lwrlock/ff-power-manager) · [eBPF Latency Guard](https://github.com/lwrlock/ebpf-latency-guard) · [VRAM Atlas](https://github.com/lwrlock/vram-atlas) · [Waylens Privacy](https://github.com/lwrlock/waylens-privacy) · [MemPulse](https://github.com/lwrlock/mempulse) · [NetPulse BPF](https://github.com/lwrlock/netpulse-bpf) · **NVMe Sentinel**

MIT License — Copyright (c) 2026 Furkan (**lwrlock**). Built with assistance from Google DeepMind Antigravity.

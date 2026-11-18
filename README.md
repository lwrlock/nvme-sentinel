# nvme-sentinel

Linux NVMe controller thermal, APST latency, PCIe link, and block I/O monitor in C and Python/GTK4.

![nvme-sentinel screenshot](docs/screenshots/overview.png)

## What it reads

- **Controller & PCIe Link:** Reads `/sys/class/nvme/nvme0/{model,firmware_rev}`, `device/current_link_speed`, `current_link_width`, and `power/runtime_status`.
- **Thermal & APST:** Reads NVMe `hwmon` temperature (`°C`) and `/sys/module/nvme_core/parameters/default_ps_max_latency_us` to classify APST sleep policy.
- **Block Queue & IOPS:** Samples `/sys/block/nvme0n1/stat` deltas for read/write IOPS and MB/s, along with `queue/{scheduler,read_ahead_kb,rq_affinity,nr_requests}`.

## Build & Run

```bash
make all
make test
./nvme-sentinel-probe --sample-ms 80 --json
PYTHONPATH=src /usr/bin/python3 -m nvme_sentinel.gui
```

## Related

[ff-power-manager](https://github.com/lwrlock/ff-power-manager) · [ebpf-latency-guard](https://github.com/lwrlock/ebpf-latency-guard) · [vram-atlas](https://github.com/lwrlock/vram-atlas) · [waylens-privacy](https://github.com/lwrlock/waylens-privacy) · [mempulse](https://github.com/lwrlock/mempulse) · [netpulse-bpf](https://github.com/lwrlock/netpulse-bpf)

## License

MIT — see [LICENSE](LICENSE).

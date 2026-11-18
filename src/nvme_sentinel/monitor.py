from __future__ import annotations

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]


def evaluate_apst_status(apst_us: int, temp_c: int) -> str:
    if temp_c >= 72:
        return "THERMAL_WARN"
    if apst_us >= 5500 or apst_us == -1:
        return "DEEP_PS4_OPTIMAL"
    if apst_us > 0:
        return "LIGHT_APST"
    return "APST_DISABLED"


def sample_nvme(sample_ms: int = 120) -> dict:
    probe = ROOT / "nvme-sentinel-probe"
    out = subprocess.check_output([str(probe), "--sample-ms", str(sample_ms), "--json"], text=True, timeout=4.0)
    data = json.loads(out)
    data["apst_grade"] = evaluate_apst_status(
        int(data.get("apst_max_latency_us", -1)),
        int(data.get("temp_c", 0)),
    )
    return data

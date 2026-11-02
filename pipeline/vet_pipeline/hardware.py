"""Read-only Linux inventory and host-level resource sampling. Never loads a model."""

from __future__ import annotations
import os
import platform
import shutil
import threading
import time
from pathlib import Path
import httpx


def memory():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0]) * 1024
    return values


def gpu_stats():
    result = []
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        if "-" in card.name or not (card / "device/vendor").exists():
            continue
        device = card / "device"

        def read(name):
            try:
                return (device / name).read_text().strip()
            except OSError:
                return None

        def number(name):
            value = read(name)
            return int(value) if value and value.isdigit() else None

        result.append(
            {
                "card": card.name,
                "vendor": read("vendor"),
                "device": read("device"),
                "vramTotalBytes": number("mem_info_vram_total"),
                "vramUsedBytes": number("mem_info_vram_used"),
                "busyPercent": number("gpu_busy_percent"),
                "driver": (device / "driver").resolve().name,
            }
        )
    return result


def inventory(ollama_url="http://127.0.0.1:11434"):
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        platform.processor(),
    )
    mem = memory()
    disk = shutil.disk_usage(Path.home())
    result = {
        "os": platform.freedesktop_os_release().get("PRETTY_NAME"),
        "kernel": platform.release(),
        "cpu": cpu,
        "logicalCpus": os.cpu_count(),
        "ramTotalBytes": mem["MemTotal"],
        "ramAvailableBytes": mem["MemAvailable"],
        "diskFreeBytes": disk.free,
        "gpus": gpu_stats(),
        "systemRocmSdkPresent": Path("/opt/rocm").exists(),
        "tools": {
            name: bool(shutil.which(name))
            for name in [
                "rocminfo",
                "hipcc",
                "vulkaninfo",
                "cmake",
                "ninja",
                "whisper-cli",
            ]
        },
    }
    # Inventory is local only; never send system metadata to an arbitrary inference endpoint.
    if ollama_url not in ["http://127.0.0.1:11434", "http://localhost:11434"]:
        return result
    try:
        with httpx.Client(base_url=ollama_url, timeout=3, trust_env=False) as c:
            result["ollama"] = {
                "version": c.get("/api/version").json().get("version"),
                "models": [
                    {k: m.get(k) for k in ["name", "digest", "size", "details"]}
                    for m in c.get("/api/tags").json().get("models", [])
                ],
                "loaded": [
                    {
                        k: m.get(k)
                        for k in ["name", "size", "size_vram", "context_length"]
                    }
                    for m in c.get("/api/ps").json().get("models", [])
                ],
            }
    except (httpx.HTTPError, ValueError):
        result["ollama"] = {"available": False}
    return result


def _cpu():
    values = [
        int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]
    ]
    return sum(values), values[3] + values[4]


class ResourceSampler:
    """Host metrics include desktop/MMM/FCC activity. RSS is this Python process only."""

    def __init__(self, interval=0.5):
        self.interval = interval
        self.samples = []
        self.stop = threading.Event()
        self.previous = None

    def sample(self):
        total, idle = _cpu()
        util = None
        if self.previous and total > self.previous[0]:
            util = 100 * (1 - (idle - self.previous[1]) / (total - self.previous[0]))
        self.previous = (total, idle)
        rss = next(
            int(line.split()[1]) * 1024
            for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith("VmRSS:")
        )
        self.samples.append(
            {
                "atMonotonic": time.monotonic(),
                "hostCpuPercent": util,
                "hostRamAvailableBytes": memory()["MemAvailable"],
                "pythonRssBytes": rss,
                "gpus": gpu_stats(),
            }
        )

    def __enter__(self):
        self.sample()

        def loop():
            while not self.stop.wait(self.interval):
                try:
                    self.sample()
                except (OSError, ValueError, StopIteration):
                    pass

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=2)
        self.sample()

    def summary(self):
        cpu = [
            s["hostCpuPercent"] for s in self.samples if s["hostCpuPercent"] is not None
        ]
        return {
            "scope": "Host-wide CPU/RAM/GPU; Python RSS excludes the separate Ollama server. GPU activity alone does not prove model offload.",
            "sampleCount": len(self.samples),
            "meanHostCpuPercent": sum(cpu) / len(cpu) if cpu else None,
            "peakPythonRssBytes": max(s["pythonRssBytes"] for s in self.samples),
            "minimumHostRamAvailableBytes": min(
                s["hostRamAvailableBytes"] for s in self.samples
            ),
            "gpus": [
                {
                    "card": name,
                    "peakBusyPercent": max(
                        (
                            g["busyPercent"] or 0
                            for s in self.samples
                            for g in s["gpus"]
                            if g["card"] == name
                        ),
                        default=0,
                    ),
                    "peakVramUsedBytes": max(
                        (
                            g["vramUsedBytes"] or 0
                            for s in self.samples
                            for g in s["gpus"]
                            if g["card"] == name
                        ),
                        default=0,
                    ),
                }
                for name in {g["card"] for s in self.samples for g in s["gpus"]}
            ],
        }

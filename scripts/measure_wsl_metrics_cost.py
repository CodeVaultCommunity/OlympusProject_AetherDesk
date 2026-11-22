"""Sample metrics request latency and service/daemon CPU cost in WSL."""

from __future__ import annotations

import math
import os
import statistics
import subprocess
import time
from pathlib import Path

import httpx
import psutil


BASE = "https://localhost"
CA = "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"


def main_pid(unit: str) -> int:
    return int(subprocess.check_output(
        ["systemctl", "show", "-p", "MainPID", "--value", unit], text=True).strip())


def cpu_seconds(process: psutil.Process) -> float:
    times = process.cpu_times()
    return times.user + times.system


def main() -> None:
    processes = [psutil.Process(main_pid(unit)) for unit in ("aetherdesk", "docker")]
    password = Path("/etc/aetherdesk/test-admin.password").read_text()
    with httpx.Client(base_url=BASE, verify=CA, trust_env=False, timeout=20) as client:
        client.post("/api/v1/login", json={"username": "admin", "password": password}).raise_for_status()
        before = sum(cpu_seconds(process) for process in processes)
        start = time.perf_counter()
        samples = []
        for _ in range(30):
            requested = time.perf_counter()
            client.get("/api/v1/metrics/self").raise_for_status()
            samples.append((time.perf_counter() - requested) * 1000)
            time.sleep(0.2)
        elapsed = time.perf_counter() - start
        cpu = sum(cpu_seconds(process) for process in processes) - before
    cpu_percent = 100 * cpu / (elapsed * (os.cpu_count() or 1))
    ordered = sorted(samples)
    p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
    print(f"métricas: amostras=30, p50={statistics.median(samples):.1f}ms, "
          f"p95={p95:.1f}ms, CPU aetherdesk+dockerd={cpu_percent:.2f}% "
          f"de {os.cpu_count()} CPUs durante {elapsed:.1f}s")


if __name__ == "__main__":
    main()

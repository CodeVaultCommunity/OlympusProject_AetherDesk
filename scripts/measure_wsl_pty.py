"""Measure interactive terminal echo over trusted WSS in the WSL install."""

from __future__ import annotations

import math
import ssl
import statistics
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect


BASE = "https://localhost"
CA = "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"


def main() -> None:
    password = Path("/etc/aetherdesk/test-admin.password").read_text()
    with httpx.Client(base_url=BASE, verify=CA, trust_env=False, timeout=20) as client:
        client.post("/api/v1/login", json={"username": "admin", "password": password}).raise_for_status()
        headers = {"X-CSRF-Token": client.cookies["aether_csrf"], "Origin": BASE}
        terminal = client.post("/api/v1/terminals", json={"columns": 80, "rows": 24},
                               headers=headers)
        terminal.raise_for_status()
        terminal_id = terminal.json()["data"]["id"]
        cookies = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        context = ssl.create_default_context(cafile=CA)
        try:
            with connect(f"wss://localhost/api/v1/ws/terminals/{terminal_id}",
                         origin=BASE, additional_headers={"Cookie": cookies},
                         ssl=context, open_timeout=10) as ws:
                while True:
                    try:
                        ws.recv(timeout=0.2)
                    except TimeoutError:
                        break
                samples = []
                for _ in range(20):
                    start = time.perf_counter()
                    ws.send(b"Z")
                    while True:
                        value = ws.recv(timeout=5)
                        if b"Z" in value:
                            samples.append((time.perf_counter() - start) * 1000)
                            break
                ws.send(b"\x03")
            ordered = sorted(samples)
            p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
            print(f"PTY WSS eco: amostras={len(samples)}, p50={statistics.median(samples):.1f}ms, "
                  f"p95={p95:.1f}ms, max={max(samples):.1f}ms")
        finally:
            client.delete(f"/api/v1/terminals/{terminal_id}", headers=headers)


if __name__ == "__main__":
    main()

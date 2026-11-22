"""Measure eight simultaneous users against the installed WSL HTTPS service.

This local workload is deliberately bounded and does not establish production
capacity on an independent Linux server.
"""

from __future__ import annotations

import json
import math
import secrets
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx


BASE = "https://localhost"
CA = "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"
USERS = 8
FILES_PER_USER = 100
ROUNDS = 20
# WSL regression guard, revised after the first measured baseline. The proposed
# independent-server goals remain in docs/L3_Vulcan/architecture.md.
TARGET_P95_MS = {"login": 6000, "list100": 2500, "download1m": 2000, "metrics": 3000}


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, verify=CA, trust_env=False, timeout=30)


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return round(ordered[math.ceil(len(ordered) * fraction) - 1], 1)


def measure(function):
    start = time.perf_counter()
    response = function()
    response.raise_for_status()
    return (time.perf_counter() - start) * 1000, response


def main() -> None:
    password = Path("/etc/aetherdesk/test-admin.password").read_text()
    administrator = client()
    members: list[httpx.Client] = []
    accounts: list[dict] = []
    resources: list[tuple[str, str]] = []
    account_password = secrets.token_urlsafe(24)
    prefix = "load" + secrets.token_hex(4)
    admin_headers: dict[str, str] = {}
    try:
        administrator.post("/api/v1/login", json={"username": "admin",
                                                  "password": password}).raise_for_status()
        admin_headers = {"X-CSRF-Token": administrator.cookies["aether_csrf"], "Origin": BASE}
        for index in range(USERS):
            name = f"{prefix}_{index}"
            created = administrator.post("/api/v1/admin/accounts",
                                         json={"username": name, "password": account_password,
                                               "role": "member"}, headers=admin_headers)
            created.raise_for_status()
            account = created.json()["data"]
            accounts.append(account)
            suffix = account["environment_id"].replace("-", "")
            container = "aetherdesk-e-" + suffix
            volume = "aetherdesk-v-" + suffix
            resources.append((container, volume))
            member = client()
            member.post("/api/v1/login", json={"username": name,
                                               "password": account_password}).raise_for_status()
            members.append(member)
            seeded = subprocess.run(["docker", "exec", container, "bash", "-lc",
                "for i in $(seq 1 100); do printf x > /persist/item-$i.txt; done"],
                capture_output=True, check=True, timeout=30)
            assert seeded.returncode == 0
            upload = member.put("/api/v1/files/upload", params={"path": "/persist/payload.bin"},
                                content=b"x" * (1024 * 1024),
                                headers={"X-CSRF-Token": member.cookies["aether_csrf"],
                                         "Origin": BASE})
            upload.raise_for_status()

        samples: dict[str, list[float]] = {name: [] for name in TARGET_P95_MS}
        routes = {
            "list100": lambda item: item.get("/api/v1/files/list", params={"path": "/persist"}),
            "download1m": lambda item: item.get("/api/v1/files/download",
                                                params={"path": "/persist/payload.bin"}),
            "metrics": lambda item: item.get("/api/v1/metrics/self"),
        }
        with ThreadPoolExecutor(max_workers=USERS) as pool:
            for _ in range(3):
                futures = [pool.submit(measure, lambda item=item, account=account:
                    item.post("/api/v1/login", json={"username": account["username"],
                                                    "password": account_password}))
                    for item, account in zip(members, accounts)]
                for future in futures:
                    elapsed, _ = future.result()
                    samples["login"].append(elapsed)
            for label, request in routes.items():
                for _ in range(ROUNDS):
                    futures = [pool.submit(measure, lambda item=item: request(item))
                               for item in members]
                    for future in futures:
                        elapsed, response = future.result()
                        if label == "list100":
                            assert len(response.json()["data"]) >= FILES_PER_USER
                        elif label == "download1m":
                            assert len(response.content) == 1024 * 1024
                        samples[label].append(elapsed)
        results = {label: {"samples": len(values), "p50_ms": percentile(values, 0.5),
                           "p95_ms": percentile(values, 0.95),
                           "max_ms": round(max(values), 1),
                           "target_p95_ms": TARGET_P95_MS[label],
                           "passed": percentile(values, 0.95) < TARGET_P95_MS[label]}
                   for label, values in samples.items()}
        print(json.dumps({"environment": "Ubuntu 24.04.5 WSL 2, Docker Engine native",
                          "users": USERS, "files_per_user": FILES_PER_USER,
                          "rounds": ROUNDS, "results": results}, indent=2))
    finally:
        for member in members:
            member.close()
        for account in accounts:
            try:
                administrator.patch(f"/api/v1/admin/accounts/{account['id']}",
                                    json={"revision": account["revision"], "state": "deleted"},
                                    headers=admin_headers)
            except Exception:
                pass
        administrator.close()
        for container, volume in resources:
            subprocess.run(["docker", "container", "rm", "--force", container], capture_output=True)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    main()

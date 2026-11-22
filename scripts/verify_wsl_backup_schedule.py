"""Verify that the installed service performs a configured backup on schedule."""

from __future__ import annotations

import sys
import tarfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, "/opt/aetherdesk")
from apps.AetherDesk.backup.service import verify_snapshot


BASE = "https://localhost"
CA = "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"
DESTINATION = Path("/var/backups/aetherdesk")


def main() -> None:
    password = Path("/etc/aetherdesk/test-admin.password").read_text()
    with httpx.Client(base_url=BASE, verify=CA, trust_env=False, timeout=20) as client:
        response = client.post("/api/v1/login", json={"username": "admin", "password": password})
        response.raise_for_status()
        csrf = client.cookies["aether_csrf"]
        headers = {"X-CSRF-Token": csrf, "Origin": BASE}
        current = client.get("/api/v1/admin/backup")
        current.raise_for_status()
        assert current.json()["data"]["enabled"] == 0
        marker = f"backup-scheduled-{time.time_ns()}".encode()
        uploaded = client.put("/api/v1/files/upload", params={"path": "/persist/scheduled.txt"},
                              content=marker, headers=headers)
        uploaded.raise_for_status()
        before = set(DESTINATION.glob("aetherdesk-*"))
        policy = {"enabled": True, "frequency_hours": 1,
                  "destination": str(DESTINATION), "retention_mode": "replace",
                  "retention_days": None}
        configured = client.put("/api/v1/admin/backup", json=policy, headers=headers)
        configured.raise_for_status()
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                snapshots = set(DESTINATION.glob("aetherdesk-*")) - before
                if snapshots:
                    snapshot = max(snapshots, key=lambda path: path.stat().st_mtime)
                    manifest = verify_snapshot(snapshot)
                    for entry in manifest["volumes"]:
                        archive = snapshot / (entry["volume"] + ".tar")
                        with tarfile.open(archive) as contents:
                            try:
                                data = contents.extractfile("./scheduled.txt")
                            except KeyError:
                                continue
                            assert data is not None and data.read() == marker
                            print(f"Backup agendado verificado: {snapshot.name}")
                            return
                time.sleep(2)
            raise RuntimeError("backup agendado não ocorreu em 90 segundos")
        finally:
            policy["enabled"] = False
            client.put("/api/v1/admin/backup", json=policy, headers=headers).raise_for_status()


if __name__ == "__main__":
    main()

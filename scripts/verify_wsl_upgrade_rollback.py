"""Exercise a reversible code update of the disposable WSL installation."""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path

import httpx


BASE = "https://localhost"
CA = "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"
PACKAGE = Path("/opt/aetherdesk")
SOURCE = PACKAGE / "launch.py"
TRIAL = b'version="0.1.0-wsl-trial"'
CURRENT = b'version="0.1.0"'


def service(*args: str) -> None:
    subprocess.run(["systemctl", *args, "aetherdesk"], check=True, timeout=30)


def ready(client: httpx.Client) -> None:
    for _ in range(40):
        try:
            if client.get("/healthz").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    raise RuntimeError("AetherDesk não reiniciou em 20 segundos")


def check(client: httpx.Client, expected_version: str, expected_file: str) -> None:
    ready(client)
    version = client.get("/openapi.json")
    version.raise_for_status()
    assert version.json()["info"]["version"] == expected_version
    password = Path("/etc/aetherdesk/test-admin.password").read_text()
    client.post("/api/v1/login", json={"username": "admin", "password": password}).raise_for_status()
    content = client.get("/api/v1/files/content", params={"path": "/persist/scheduled.txt"})
    content.raise_for_status()
    assert content.json()["data"]["content"] == expected_file


def main() -> None:
    original = SOURCE.read_bytes()
    if original.count(CURRENT) != 1:
        raise RuntimeError("versão de origem inesperada; não modificar a instalação")
    old_hash = hashlib.sha256(original).hexdigest()
    backup = PACKAGE / ".launch.py.wsl-original"
    if backup.exists():
        raise RuntimeError("cópia de reversão já existe; investigar antes de continuar")
    snapshots = sorted(Path("/var/backups/aetherdesk").glob("aetherdesk-*"))
    if not snapshots:
        raise RuntimeError("falta snapshot verificado antes da atualização")
    backup.write_bytes(original)
    backup.chmod(0o600)
    try:
        with httpx.Client(base_url=BASE, verify=CA, trust_env=False, timeout=20) as client:
            ready(client)
            version = client.get("/openapi.json")
            version.raise_for_status()
            assert version.json()["info"]["version"] == "0.1.0"
            password = Path("/etc/aetherdesk/test-admin.password").read_text()
            client.post("/api/v1/login", json={"username": "admin", "password": password}).raise_for_status()
            content = client.get("/api/v1/files/content", params={"path": "/persist/scheduled.txt"})
            content.raise_for_status()
            expected_file = content.json()["data"]["content"]
            service("stop")
            SOURCE.write_bytes(original.replace(CURRENT, TRIAL))
            service("start")
            check(client, "0.1.0-wsl-trial", expected_file)

            service("stop")
            SOURCE.write_bytes(original)
            service("start")
            check(client, "0.1.0", expected_file)
            assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == old_hash
            print("Atualização de código, serviço e reversão com arquivo preservado: OK")
    finally:
        if SOURCE.read_bytes() != original:
            service("stop")
            SOURCE.write_bytes(original)
        service("start")
        backup.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

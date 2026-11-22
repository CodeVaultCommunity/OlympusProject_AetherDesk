"""Exercise the installed WSL service through trusted local HTTPS and WSS."""

from __future__ import annotations

import secrets
import ssl
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect


BASE = "https://localhost"
CONFIG = Path("/etc/aetherdesk")
CA = Path("/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt")


def bootstrap_token() -> str:
    for line in (CONFIG / "aetherdesk.env").read_text().splitlines():
        if line.startswith("AETHERDESK_BOOTSTRAP_TOKEN="):
            return line.split("=", 1)[1]
    raise RuntimeError("token de bootstrap ausente")


def main() -> None:
    password_file = CONFIG / "test-admin.password"
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(32))
        password_file.chmod(0o600)
    password = password_file.read_text()

    with httpx.Client(base_url=BASE, verify=str(CA), trust_env=False, timeout=20) as client:
        for _ in range(20):
            try:
                if client.get("/healthz").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("serviço não ficou pronto após reabrir a distribuição")
        response = client.post("/api/v1/login", json={"username": "admin", "password": password})
        if response.status_code == 401:
            bootstrap = client.post("/api/v1/bootstrap", json={
                "token": bootstrap_token(), "username": "admin", "password": password,
            })
            bootstrap.raise_for_status()
            response = client.post("/api/v1/login", json={"username": "admin", "password": password})
        response.raise_for_status()
        assert all("secure" in value.lower() for value in response.headers.get_list("set-cookie"))
        assert client.get("/api/v1/me").json()["data"]["role"] == "admin"
        assert client.get("/api/v1/admin/backup").json()["data"]["enabled"] == 0
        assert client.get("/api/v1/desktop/state").status_code == 200

        csrf = client.cookies["aether_csrf"]
        response = client.post("/api/v1/terminals", json={"columns": 80, "rows": 24},
                               headers={"X-CSRF-Token": csrf, "Origin": BASE})
        response.raise_for_status()
        terminal_id = response.json()["data"]["id"]
        context = ssl.create_default_context(cafile=str(CA))
        cookies = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        try:
            with connect(f"wss://localhost/api/v1/ws/terminals/{terminal_id}",
                         origin=BASE, additional_headers={"Cookie": cookies},
                         ssl=context, open_timeout=10) as ws:
                ws.send(b"pwd\n")
                chunks = []
                for _ in range(12):
                    chunks.append(ws.recv(timeout=5))
                    if b"/persist" in b"".join(chunks):
                        break
                assert b"/persist" in b"".join(chunks), "PTY não respondeu pwd"
        finally:
            client.delete(f"/api/v1/terminals/{terminal_id}",
                          headers={"X-CSRF-Token": csrf, "Origin": BASE})
    print("HTTPS, cookies Secure, login, backup padrão e terminal WSS: OK")


if __name__ == "__main__":
    main()

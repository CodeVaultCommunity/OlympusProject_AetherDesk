"""Configure a disposable WSL 2 installation for local acceptance tests.

Run as root inside the dedicated Ubuntu distribution after copying the package
to /opt/aetherdesk and installing its Linux dependencies.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> None:
    if os.geteuid() != 0 or "microsoft" not in Path("/proc/version").read_text().lower():
        raise SystemExit("Execute como root em uma distribuição WSL 2 descartável")

    package = Path("/opt/aetherdesk")
    if not (package / ".venv/bin/uvicorn").exists() or not (package / "web/dist/index.html").exists():
        raise SystemExit("Copie e prepare o pacote em /opt/aetherdesk antes da configuração")

    config = Path("/etc/aetherdesk")
    config.mkdir(mode=0o700, exist_ok=True)
    environment = config / "aetherdesk.env"
    if not environment.exists():
        environment.write_text(
            "AETHERDESK_BOOTSTRAP_TOKEN=" + secrets.token_urlsafe(48) + "\n"
            "AETHERDESK_CSRF_SECRET=" + secrets.token_urlsafe(48) + "\n"
            "AETHERDESK_DATA_DIR=/var/lib/aetherdesk\n"
            "AETHERDESK_RUNTIME_IMAGE=aetherdesk-files:w003\n"
        )
    environment.chmod(0o600)

    shutil.copy2(package / "deploy/aetherdesk.service", "/etc/systemd/system/aetherdesk.service")
    Path("/etc/caddy/Caddyfile").write_text(
        "localhost {\n"
        "    tls internal\n"
        "    encode zstd gzip\n"
        '    header Strict-Transport-Security "max-age=31536000"\n'
        "    reverse_proxy 127.0.0.1:8174\n"
        "}\n"
    )
    run("caddy", "validate", "--config", "/etc/caddy/Caddyfile")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "docker", "caddy", "aetherdesk")
    run("systemctl", "restart", "caddy")
    print("Serviços WSL configurados; segredos preservados em /etc/aetherdesk/aetherdesk.env")


if __name__ == "__main__":
    main()

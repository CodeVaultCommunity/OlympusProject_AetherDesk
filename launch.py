"""Registro explícito da aplicação AetherDesk."""

from __future__ import annotations

import os
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.files.gateway import ContainerFileGateway
from apps.AetherDesk.files.http import files_router
from apps.AetherDesk.terminal import TerminalService
from apps.AetherDesk.terminal.http import terminal_router
from apps.AetherDesk.monitor.service import MonitorService
from apps.AetherDesk.monitor.http import monitor_router
from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.administration.http import administration_router
from apps.AetherDesk.backup.service import BackupService


def create_app() -> FastAPI:
    token = os.environ.get("AETHERDESK_BOOTSTRAP_TOKEN", "")
    csrf_secret = os.environ.get("AETHERDESK_CSRF_SECRET", "")
    if len(token) < 16 or len(csrf_secret) < 32:
        raise RuntimeError("Configure AETHERDESK_BOOTSTRAP_TOKEN e AETHERDESK_CSRF_SECRET")
    data_dir = Path(os.environ.get("AETHERDESK_DATA_DIR", "/var/lib/aetherdesk"))
    data_dir.mkdir(parents=True, exist_ok=True)
    identity = IdentityService(data_dir / "identity.sqlite3", token)
    runtime = DockerEnvironmentBroker(os.environ.get("AETHERDESK_RUNTIME_IMAGE", "aetherdesk-files:w003"))
    composition = AppComposition(identity, runtime)
    files = ContainerFileGateway(identity, runtime)
    terminals = TerminalService(data_dir / "terminals.sqlite3", identity, runtime)
    composition.terminal = terminals
    monitor = MonitorService(identity, runtime)
    administration = AdministrationService(data_dir / "identity.sqlite3", identity, composition)
    backup = BackupService(data_dir, administration, runtime)

    @asynccontextmanager
    async def lifespan(_app):
        stopped = threading.Event()

        def backup_worker():
            while not stopped.is_set():
                try:
                    backup.run_due()
                except Exception:
                    logging.getLogger("aetherdesk.backup").exception("Backup falhou")
                stopped.wait(60)

        worker = threading.Thread(target=backup_worker, name="aetherdesk-backup", daemon=True)
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join(timeout=5)

    app = FastAPI(title="AetherDesk", version="0.1.0", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.include_router(identity_router(identity, csrf_secret,
                                       secure_cookie=os.environ.get("AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP") != "1"))
    app.include_router(files_router(files, identity, csrf_secret))
    app.include_router(terminal_router(terminals, identity, csrf_secret))
    app.include_router(monitor_router(monitor, identity, administration.accounts))
    app.include_router(administration_router(administration, identity, csrf_secret))

    @app.middleware("http")
    async def account_events(request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            composition.process_account_events()
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    static_dir = Path(__file__).parent / "web" / "dist"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8080)

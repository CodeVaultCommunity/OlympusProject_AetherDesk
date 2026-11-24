"""Registro explícito da aplicação AetherDesk."""

from __future__ import annotations

import os
import base64
import logging
import re
import uuid
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerEnvironmentAdapter, BrokerError
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.files.broker_gateway import BrokerFileGateway
from apps.AetherDesk.files.http import files_router
from apps.AetherDesk.terminal import TerminalService
from apps.AetherDesk.terminal.http import terminal_router
from apps.AetherDesk.monitor.service import MonitorService
from apps.AetherDesk.monitor.broker_source import BrokerMetricsSource
from apps.AetherDesk.monitor.http import monitor_router
from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.administration.http import administration_router
from apps.AetherDesk.support.leases import LeaseStore
from apps.AetherDesk.support.workers import LeasedJob
from apps.AetherDesk.support.http import error_response, install_http_policy
from apps.AetherDesk.ai.chat import ChatService, Provider
from apps.AetherDesk.ai.http import ai_router
from apps.AetherDesk.ai.tools import NativeTools
from apps.AetherDesk.workloads.http import workloads_router
from apps.AetherDesk.workloads.gateway import RouteGateway
from apps.AetherDesk.workspace.http import workspace_router


def create_app() -> FastAPI:
    features = frozenset(part.strip() for part in os.environ.get('AETHERDESK_FEATURES', '').split(',') if part.strip())
    if not features.issubset({'ide', 'workloads', 'ai'}):
        raise RuntimeError('AETHERDESK_FEATURES inválido')
    safe_mode = os.environ.get('AETHERDESK_SAFE_MODE') == '1'
    if safe_mode or os.environ.get('AETHERDESK_KILL_AI') == '1':
        features = features - {'ai'}
    token = os.environ.get("AETHERDESK_BOOTSTRAP_TOKEN", "")
    csrf_secret = os.environ.get("AETHERDESK_CSRF_SECRET", "")
    if len(token) < 16 or len(csrf_secret) < 32:
        raise RuntimeError("Configure AETHERDESK_BOOTSTRAP_TOKEN e AETHERDESK_CSRF_SECRET")
    data_dir = Path(os.environ.get("AETHERDESK_DATA_DIR", "/var/lib/aetherdesk"))
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        broker_secret = base64.b64decode(os.environ.get('AETHERDESK_BROKER_SECRET_B64', ''),
                                         validate=True)
    except ValueError as exc:
        raise RuntimeError('Configure AETHERDESK_BROKER_SECRET_B64') from exc
    if len(broker_secret) < 32:
        raise RuntimeError('Configure AETHERDESK_BROKER_SECRET_B64')
    configured_retention = os.environ.get('AETHERDESK_ACCOUNT_RETENTION_SECONDS', '').strip()
    try:
        account_retention = int(configured_retention) if configured_retention else None
    except ValueError as exc:
        raise RuntimeError('AETHERDESK_ACCOUNT_RETENTION_SECONDS inválido') from exc
    try:
        terminal_limit = int(os.environ.get('AETHERDESK_MAX_TERMINAL_SESSIONS_PER_ACCOUNT', '8'))
    except ValueError as exc:
        raise RuntimeError('AETHERDESK_MAX_TERMINAL_SESSIONS_PER_ACCOUNT inválido') from exc
    if not 1 <= terminal_limit <= 64:
        raise RuntimeError('AETHERDESK_MAX_TERMINAL_SESSIONS_PER_ACCOUNT inválido')
    broker = BrokerClient(os.environ.get('AETHERDESK_BROKER_SOCKET',
                                        '/run/aetherdesk-broker/broker.sock'), broker_secret)
    identity = IdentityService(data_dir / "identity.sqlite3", token, account_retention,
                               enabled_features=features,
                               kill_deploys=os.environ.get('AETHERDESK_KILL_DEPLOYS') == '1',
                               safe_mode=safe_mode)
    runtime = BrokerEnvironmentAdapter(broker)
    composition = AppComposition(identity, runtime)
    files = BrokerFileGateway(identity, broker)
    terminals = TerminalService(data_dir / "terminals.sqlite3", identity, runtime,
                                broker=broker, max_sessions_per_account=terminal_limit)
    composition.terminal = terminals
    monitor = MonitorService(identity, runtime, source=BrokerMetricsSource(broker))
    administration = AdministrationService(data_dir / "identity.sqlite3", identity, composition)
    account_events = LeasedJob(LeaseStore(data_dir / 'identity.sqlite3'), 'account.events')

    @asynccontextmanager
    async def lifespan(_app):
        stopped = threading.Event()

        def process_events():
            while not stopped.is_set():
                try:
                    account_events.run(composition.process_account_events)
                except Exception:
                    logging.getLogger('aetherdesk.events').warning('Evento de conta pendente')
                stopped.wait(10)

        worker = threading.Thread(target=process_events, name='aetherdesk-account-events', daemon=True)
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join(timeout=5)

    app = FastAPI(title="AetherDesk", version="0.1.0", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    install_http_policy(app)
    proxy_enabled = 'workloads' in features and not safe_mode and os.environ.get('AETHERDESK_ENABLE_WORKLOAD_PROXY') == '1'
    gateway = RouteGateway(data_dir / 'identity.sqlite3', identity, broker,
        secure_cookie=os.environ.get('AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP') != '1') if proxy_enabled else None

    @app.middleware('http')
    async def route_origin(request, call_next):
        host = request.headers.get('host', '').split(':', 1)[0].lower()
        if host.endswith('.apps.local'):
            if gateway is None:
                return JSONResponse({'detail': 'ROUTE_DISABLED'}, status_code=503,
                                    headers={'Cache-Control': 'no-store'})
            return await gateway.handle(request)
        return await call_next(request)

    @app.exception_handler(BrokerError)
    async def broker_unavailable(request, error: BrokerError):
        code = str(error)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', code):
            code = 'BROKER_UNAVAILABLE'
        return error_response(request, 503, code)
    app.include_router(identity_router(identity, csrf_secret,
                                       secure_cookie=os.environ.get("AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP") != "1"))
    app.include_router(files_router(files, identity, csrf_secret))
    app.include_router(terminal_router(terminals, identity, csrf_secret))
    app.include_router(monitor_router(monitor, identity, administration.accounts))
    app.include_router(administration_router(administration, identity, csrf_secret))
    if 'workloads' in features:
        app.include_router(workloads_router(broker, identity, csrf_secret, gateway))
    if 'ide' in features:
        app.include_router(workspace_router(broker, identity, csrf_secret))
    if 'ai' in features:
        def session_active(actor):
            try:
                identity.assert_active(actor)
                return True
            except IdentityError:
                return False
        ai = ChatService(data_dir / 'ai.sqlite3', identity.require, session_active,
                         providers={'local-demo': Provider('local-demo', False,
                             'Mensagem e histórico da conversa permanecem neste servidor.',
                             lambda _messages, _credential: ('Demonstração local: resposta gerada sem provedor externo.',))},
                         enabled_providers=frozenset({'local-demo'}))
        native_tools = NativeTools(data_dir / 'ai.sqlite3', identity, broker) if 'workloads' in features else None
        app.include_router(ai_router(ai, identity, csrf_secret, native_tools))

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get('/readyz')
    def ready():
        try:
            if not Path(identity.db_path).is_file():
                raise OSError('identity database missing')
            result = broker.call('ping', str(uuid.UUID(int=0)), str(uuid.UUID(int=0)))
            if result != {'protocol': 1, 'ready': True}:
                raise BrokerError('BROKER_PROTOCOL')
            return {'status': 'ready', 'broker_protocol': 1}
        except (OSError, BrokerError):
            raise HTTPException(503, 'NOT_READY')

    static_dir = Path(__file__).parent / "web" / "dist"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8080)

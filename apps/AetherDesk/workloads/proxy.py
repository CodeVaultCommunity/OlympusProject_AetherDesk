"""Proxy HTTP interno de workloads com destino preso ao broker e ao dono.

Não segue redirects, não aceita URL do navegador e remove headers de conexão,
credenciais e cookies de infraestrutura antes de alcançar a aplicação.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Callable

import httpx

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.migrations import apply_migration

from .proxy_policy import ProxyRoute, authorize_route
from .service import WorkloadError


_HOST = re.compile(r'^[a-z0-9][a-z0-9.-]{0,100}\.apps\.local$')
_DROP_REQUEST = frozenset({'host', 'connection', 'upgrade', 'proxy-authorization',
                            'authorization', 'cookie', 'forwarded', 'x-forwarded-for',
                            'x-forwarded-host', 'x-forwarded-proto', 'transfer-encoding',
                            'content-length'})
_DROP_RESPONSE = frozenset({'connection', 'upgrade', 'transfer-encoding', 'content-length',
                             'content-encoding',
                             'set-cookie', 'location', 'www-authenticate'})


class WorkloadProxy:
    def __init__(self, db_path: str | Path,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 container_ip: Callable[[str, str], str],
                 transport: httpx.BaseTransport | None = None):
        self.db_path = str(db_path)
        self.authorize, self.session_active = authorize, session_active
        self.container_ip, self.transport = container_ip, transport
        apply_migration(self.db_path, 'workloads.routes.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS workload_routes (
                hostname TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                workload_id TEXT NOT NULL UNIQUE, port INTEGER NOT NULL,
                container_ip TEXT NOT NULL, network_cidr TEXT NOT NULL)'''))

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def register(self, route: ProxyRoute) -> None:
        # Só o reconciliador do broker invoca este método com IP da rede Docker.
        if not _HOST.fullmatch(route.hostname) or not route.hostname.startswith(
            route.workload_id.replace('-', '')[:12] + '.'):
            raise WorkloadError('INVALID_ROUTE')
        authorize_route(route, owner_id=route.owner_id, workload_id=route.workload_id,
                        host_header=route.hostname, current_container_ip=route.container_ip)
        with closing(self._db()) as db, db:
            existing = db.execute('SELECT * FROM workload_routes WHERE hostname=? OR workload_id=?',
                                  (route.hostname, route.workload_id)).fetchall()
            if existing:
                if (len(existing) != 1 or existing[0]['owner_id'] != route.owner_id or
                        existing[0]['workload_id'] != route.workload_id or
                        existing[0]['hostname'] != route.hostname):
                    raise WorkloadError('ROUTE_COLLISION')
                db.execute('''UPDATE workload_routes SET port=?,container_ip=?,network_cidr=?
                    WHERE hostname=? AND owner_id=? AND workload_id=?''',
                    (route.port, route.container_ip, route.network_cidr,
                     route.hostname, route.owner_id, route.workload_id))
                return
            db.execute('INSERT INTO workload_routes VALUES(?,?,?,?,?,?)',
                       (route.hostname, route.owner_id, route.workload_id, route.port,
                        route.container_ip, route.network_cidr))

    def unregister(self, owner_id: str, workload_id: str) -> None:
        with closing(self._db()) as db, db:
            db.execute('DELETE FROM workload_routes WHERE owner_id=? AND workload_id=?',
                       (owner_id, workload_id))

    def request(self, actor: ActorContext, host: str, method: str, path: str,
                headers: dict[str, str], body: bytes = b'') -> tuple[int, dict[str, str], bytes]:
        if not self.session_active(actor):
            raise WorkloadError('SESSION_REVOKED')
        self.authorize(actor, 'workloads.route')
        if (method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE') or
                not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or
                '\\' in path or '\0' in path or len(path) > 4096 or
                type(body) is not bytes or len(body) > 1024 * 1024):
            raise WorkloadError('PROXY_INVALID_REQUEST')
        with closing(self._db()) as db:
            row = db.execute('SELECT * FROM workload_routes WHERE hostname=? AND owner_id=?',
                             (host, actor.account_id)).fetchone()
        if row is None:
            raise WorkloadError('PROXY_DENIED')
        route = ProxyRoute(**dict(row))
        current = self.container_ip(route.owner_id, route.workload_id)
        ip, port = authorize_route(route, owner_id=actor.account_id,
            workload_id=route.workload_id, host_header=host, current_container_ip=current)
        safe_headers = {name: value for name, value in headers.items()
                        if name.lower() not in _DROP_REQUEST and len(name) <= 100 and len(value) <= 8192}
        safe_headers['Host'] = host
        safe_headers['Accept-Encoding'] = 'identity'
        try:
            with httpx.Client(transport=self.transport, timeout=httpx.Timeout(5.0),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream(method, f'http://{ip}:{port}{path}',
                                   headers=safe_headers, content=body) as response:
                    if 300 <= response.status_code < 400:
                        raise WorkloadError('PROXY_REDIRECT_DENIED')
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 4 * 1024 * 1024:
                            raise WorkloadError('PROXY_RESPONSE_LIMIT')
                        chunks.append(chunk)
                    safe_response = {name: value for name, value in response.headers.items()
                                     if name.lower() not in _DROP_RESPONSE}
                    return response.status_code, safe_response, b''.join(chunks)
        except httpx.HTTPError as exc:
            raise WorkloadError('PROXY_UPSTREAM_UNAVAILABLE') from exc

"""Credenciais curtas para abrir workloads em origem separada do desktop."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse, Response

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError
from apps.AetherDesk.support.migrations import apply_migration


_HOST = re.compile(r'^[0-9a-f]{12}\.apps\.local$')
_SAFE_RESPONSE = frozenset({'content-type', 'cache-control',
                            'etag', 'last-modified', 'vary'})


class RouteGateway:
    def __init__(self, db_path: str | Path, identity: IdentityService,
                 broker: BrokerClient, secure_cookie: bool = True):
        self.db_path = str(db_path)
        self.identity, self.broker = identity, broker
        self.secure_cookie = secure_cookie
        self.cookie_name = '__Host-aether_route' if secure_cookie else 'aether_route_local'
        apply_migration(self.db_path, 'workloads.gateway.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS workload_route_tokens (
                token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, host TEXT NOT NULL,
                account_id TEXT NOT NULL, session_id TEXT NOT NULL, expires_at REAL NOT NULL)'''))

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def host_for(workload_id: str) -> str:
        try:
            canonical = str(uuid.UUID(workload_id))
        except (TypeError, ValueError) as exc:
            raise ValueError('INVALID_WORKLOAD_ID') from exc
        if canonical != workload_id:
            raise ValueError('INVALID_WORKLOAD_ID')
        return canonical.replace('-', '')[:12] + '.apps.local'

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode('ascii')).hexdigest()

    def issue(self, actor: ActorContext, workload_id: str) -> dict[str, str]:
        self.identity.require(actor, 'workloads.route')
        host = self.host_for(workload_id)
        account = self.identity.account(actor, actor.account_id)
        state = self.broker.call('workload', actor.account_id, account['environment_id'],
                                 {'operation': 'state', 'session_id': actor.session_id,
                                  'workload_id': workload_id})
        if state.get('observed') not in ('running', 'rolled_back'):
            raise ValueError('WORKLOAD_NOT_RUNNING')
        token = secrets.token_urlsafe(32)
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM workload_route_tokens WHERE expires_at<?', (time.time(),))
            outstanding = db.execute('''SELECT COUNT(*) FROM workload_route_tokens
                WHERE account_id=? AND kind='ticket' ''', (actor.account_id,)).fetchone()[0]
            if outstanding >= 20:
                db.rollback()
                raise ValueError('ROUTE_RATE_LIMITED')
            db.execute('''INSERT INTO workload_route_tokens VALUES(?,?,?,?,?,?)''',
                       (self._hash(token), 'ticket', host, actor.account_id,
                        actor.session_id, time.time() + 60))
            db.commit()
        return {'host': host, 'ticket': token}

    def _exchange(self, host: str, ticket: str) -> str | None:
        if not re.fullmatch(r'[A-Za-z0-9_-]{30,100}', ticket):
            return None
        now = time.time()
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT * FROM workload_route_tokens
                WHERE token_hash=? AND kind='ticket' AND host=? AND expires_at>?''',
                (self._hash(ticket), host, now)).fetchone()
            if row is None:
                db.rollback()
                return None
            db.execute('DELETE FROM workload_route_tokens WHERE token_hash=?',
                       (self._hash(ticket),))
            actor = ActorContext(row['account_id'], row['session_id'], 'member', 0)
            try:
                self.identity.require(actor, 'workloads.route')
            except IdentityError:
                db.rollback()
                return None
            cookie = secrets.token_urlsafe(32)
            db.execute('''INSERT INTO workload_route_tokens VALUES(?,?,?,?,?,?)''',
                       (self._hash(cookie), 'session', host, row['account_id'],
                        row['session_id'], now + 3600))
            db.execute('''DELETE FROM workload_route_tokens WHERE token_hash IN (
                SELECT token_hash FROM workload_route_tokens
                WHERE account_id=? AND kind='session' ORDER BY rowid DESC LIMIT -1 OFFSET 64)''',
                (row['account_id'],))
            db.commit()
            return cookie

    def _actor(self, host: str, cookie: str | None) -> ActorContext | None:
        if not cookie or not re.fullmatch(r'[A-Za-z0-9_-]{30,100}', cookie):
            return None
        with closing(self._db()) as db:
            row = db.execute('''SELECT account_id,session_id FROM workload_route_tokens
                WHERE token_hash=? AND kind='session' AND host=? AND expires_at>?''',
                (self._hash(cookie), host, time.time())).fetchone()
        if row is None:
            return None
        actor = ActorContext(row['account_id'], row['session_id'], 'member', 0)
        try:
            self.identity.require(actor, 'workloads.route')
        except IdentityError:
            return None
        return actor

    @staticmethod
    def _error(status: int, code: str) -> JSONResponse:
        return JSONResponse({'detail': code}, status_code=status,
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})

    async def handle(self, request: Request) -> Response:
        host = request.headers.get('host', '').split(':', 1)[0].lower()
        if not _HOST.fullmatch(host):
            return self._error(404, 'ROUTE_NOT_FOUND')
        if request.url.path == '/__aetherdesk/open':
            if request.method != 'POST' or request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
                return self._error(405, 'ROUTE_TICKET_METHOD')
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 2048:
                    return self._error(413, 'ROUTE_TICKET_LIMIT')
            try:
                fields = parse_qs(body.decode('ascii'), strict_parsing=True)
                ticket = fields['ticket'][0] if set(fields) == {'ticket'} and len(fields['ticket']) == 1 else ''
            except (UnicodeError, ValueError, KeyError):
                ticket = ''
            cookie = await run_in_threadpool(self._exchange, host, ticket)
            if cookie is None:
                return self._error(403, 'ROUTE_TICKET_DENIED')
            response = RedirectResponse('/', status_code=303,
                headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
            response.set_cookie(self.cookie_name, cookie, httponly=True,
                secure=self.secure_cookie, samesite='lax', path='/', max_age=3600)
            return response
        if request.url.path.startswith('/__aetherdesk/'):
            return self._error(404, 'ROUTE_NOT_FOUND')
        actor = await run_in_threadpool(self._actor, host,
                                       request.cookies.get(self.cookie_name))
        if actor is None:
            return self._error(401, 'ROUTE_UNAUTHENTICATED')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024 * 1024:
                return self._error(413, 'PROXY_BODY_LIMIT')
        path = request.url.path
        if request.url.query:
            path += '?' + request.url.query
        try:
            account = await run_in_threadpool(self.identity.account, actor, actor.account_id)
            result = await run_in_threadpool(self.broker.call, 'workload', actor.account_id,
                account['environment_id'], {'operation': 'proxy', 'session_id': actor.session_id,
                'host': host, 'method': request.method, 'path': path,
                'headers': dict(request.headers),
                'body': base64.b64encode(body).decode('ascii')})
            content = base64.b64decode(result['body'], validate=True)
            headers = {key: value for key, value in result['headers'].items()
                       if key.lower() in _SAFE_RESPONSE}
            headers['Referrer-Policy'] = 'no-referrer'
            headers['X-Content-Type-Options'] = 'nosniff'
            headers['X-Frame-Options'] = 'DENY'
            return Response(content, status_code=result['status'], headers=headers)
        except (BrokerError, IdentityError, ValueError, KeyError):
            return self._error(502, 'PROXY_UNAVAILABLE')

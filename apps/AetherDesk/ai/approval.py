"""Registry tipado e tickets vinculados à sessão, argumentos, TTL e nonce.

O executor recebe apenas ActorContext validado e callbacks de autorização/revogação.
Nenhum texto de chat, arquivo ou saída de tool é interpretado como instrução.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.migrations import apply_migration


class AiError(Exception):
    pass


Risk = Literal['read', 'write', 'destructive']


def _canonical(arguments: dict) -> bytes:
    if type(arguments) is not dict:
        raise AiError('INVALID_ARGUMENTS')
    try:
        encoded = json.dumps(arguments, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise AiError('INVALID_ARGUMENTS') from exc
    if len(encoded) > 65536:
        raise AiError('ARGUMENTS_TOO_LARGE')
    return encoded


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    version: str
    capability: str
    risk: Risk
    validate: Callable[[dict], dict]
    execute: Callable[[ActorContext, dict], object]
    source: str = 'native'
    fingerprint: str = ''
    server_version: str = ''
    schema_digest: str = ''


@dataclass(frozen=True)
class TrustedSource:
    fingerprint: str
    server_version: str
    tool_policies: dict[str, str]
    enabled: bool = False


def tool_policy_digest(tool: ToolDescriptor) -> str:
    policy = {'name': tool.name, 'version': tool.version, 'capability': tool.capability,
              'risk': tool.risk, 'schema_digest': tool.schema_digest}
    return hashlib.sha256(_canonical(policy)).hexdigest()


class ToolRegistry:
    def __init__(self, trusted_external: dict[str, TrustedSource] | None = None):
        self._tools: dict[str, ToolDescriptor] = {}
        self._trusted = dict(trusted_external or {})
        self._disabled_sources: set[str] = set()

    def register(self, tool: ToolDescriptor) -> None:
        if not tool.name or not tool.version or not tool.capability or tool.risk not in ('read', 'write', 'destructive'):
            raise AiError('INVALID_TOOL')
        if tool.name in self._tools:
            raise AiError('TOOL_NAME_COLLISION')
        if tool.source != 'native':
            trusted = self._trusted.get(tool.source)
            if (not isinstance(trusted, TrustedSource) or not trusted.enabled or
                    tool.source in self._disabled_sources or
                    not tool.name.startswith(tool.source + '.') or
                    not re.fullmatch(r'sha256:[0-9a-f]{64}', tool.fingerprint) or
                    not re.fullmatch(r'[0-9a-f]{64}', tool.schema_digest) or
                    not hmac.compare_digest(trusted.fingerprint, tool.fingerprint) or
                    trusted.server_version != tool.server_version or
                    not hmac.compare_digest(trusted.tool_policies.get(tool.name, ''),
                                            tool_policy_digest(tool))):
                raise AiError('UNTRUSTED_TOOL_SOURCE')
        self._tools[tool.name] = tool

    def disable_source(self, source: str) -> None:
        if source == 'native':
            raise AiError('INVALID_TOOL_SOURCE')
        self._disabled_sources.add(source)

    def get(self, name: str) -> ToolDescriptor:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise AiError('TOOL_NOT_FOUND') from exc
        if tool.source in self._disabled_sources:
            raise AiError('TOOL_SOURCE_DISABLED')
        return tool

    def list(self) -> list[dict]:
        return [{'name': tool.name, 'version': tool.version, 'capability': tool.capability,
                 'risk': tool.risk, 'source': tool.source} for tool in self._tools.values()
                if tool.source not in self._disabled_sources]


class ApprovalEngine:
    def __init__(self, db_path: str | Path, registry: ToolRegistry,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 clock: Callable[[], float] = time.time):
        self.db_path = str(db_path)
        self.registry = registry
        self.authorize = authorize
        self.session_active = session_active
        self.clock = clock
        schema = '''
            CREATE TABLE IF NOT EXISTS ai_approvals (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, session_id TEXT NOT NULL,
                tool TEXT NOT NULL, tool_version TEXT NOT NULL, arguments_hash TEXT NOT NULL,
                nonce TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL,
                approved_at REAL, consumed_at REAL);
            CREATE TABLE IF NOT EXISTS ai_executions (
                account_id TEXT NOT NULL, operation_id TEXT NOT NULL, tool TEXT NOT NULL,
                arguments_hash TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT,
                PRIMARY KEY(account_id,operation_id));
            CREATE TABLE IF NOT EXISTS ai_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, account_id TEXT NOT NULL,
                session_id TEXT NOT NULL, tool TEXT NOT NULL, operation_id TEXT,
                result TEXT NOT NULL);
        '''
        apply_migration(self.db_path, 'ai.approvals.v1',
                        lambda db: [db.execute(statement) for statement in schema.split(';') if statement.strip()])

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def _check(self, actor: ActorContext, tool: ToolDescriptor) -> None:
        if not self.session_active(actor):
            raise AiError('SESSION_REVOKED')
        self.authorize(actor, tool.capability)

    def _args(self, tool: ToolDescriptor, arguments: dict) -> tuple[dict, str]:
        data = tool.validate(arguments)
        return data, hashlib.sha256(_canonical(data)).hexdigest()

    def request(self, actor: ActorContext, tool_name: str, arguments: dict,
                ttl_seconds: int = 120) -> dict:
        tool = self.registry.get(tool_name)
        self._check(actor, tool)
        if tool.risk == 'read' or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise AiError('APPROVAL_NOT_REQUIRED' if tool.risk == 'read' else 'INVALID_APPROVAL_TTL')
        _, args_hash = self._args(tool, arguments)
        ticket_id, nonce = str(uuid.uuid4()), str(uuid.uuid4())
        expires = self.clock() + ttl_seconds
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT INTO ai_approvals VALUES(?,?,?,?,?,?,?,?,NULL,NULL)''',
                       (ticket_id, actor.account_id, actor.session_id, tool.name,
                        tool.version, args_hash, nonce, expires))
            db.execute('INSERT INTO ai_audit(at,account_id,session_id,tool,result) VALUES(?,?,?,?,?)',
                       (self.clock(), actor.account_id, actor.session_id, tool.name, 'approval_requested'))
            db.commit()
        return {'id': ticket_id, 'tool': tool.name, 'version': tool.version,
                'arguments_hash': args_hash, 'expires_at': expires, 'nonce': nonce}

    def approve(self, actor: ActorContext, ticket_id: str, nonce: str) -> None:
        with closing(self._db()) as db:
            row = db.execute('SELECT * FROM ai_approvals WHERE id=? AND account_id=? AND session_id=?',
                             (ticket_id, actor.account_id, actor.session_id)).fetchone()
        if row is None or not isinstance(nonce, str) or not hmac.compare_digest(row['nonce'], nonce):
            raise AiError('APPROVAL_NOT_FOUND')
        tool = self.registry.get(row['tool'])
        self._check(actor, tool)
        if row['expires_at'] <= self.clock() or row['consumed_at'] is not None:
            raise AiError('APPROVAL_EXPIRED')
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            updated = db.execute('''UPDATE ai_approvals SET approved_at=? WHERE id=? AND account_id=?
                AND session_id=? AND approved_at IS NULL AND consumed_at IS NULL AND expires_at>?''',
                (self.clock(), ticket_id, actor.account_id, actor.session_id, self.clock()))
            if updated.rowcount != 1:
                raise AiError('APPROVAL_REPLAY')
            db.execute('INSERT INTO ai_audit(at,account_id,session_id,tool,result) VALUES(?,?,?,?,?)',
                       (self.clock(), actor.account_id, actor.session_id, tool.name, 'approval_granted'))
            db.commit()

    def invoke(self, actor: ActorContext, tool_name: str, arguments: dict,
               operation_id: str, ticket_id: str | None = None,
               approval_nonce: str | None = None) -> object:
        tool = self.registry.get(tool_name)
        self._check(actor, tool)
        if not isinstance(operation_id, str):
            raise AiError('INVALID_OPERATION_ID')
        try:
            operation_id = str(uuid.UUID(operation_id))
        except ValueError as exc:
            raise AiError('INVALID_OPERATION_ID') from exc
        data, args_hash = self._args(tool, arguments)
        if tool.risk != 'read' and not ticket_id:
            raise AiError('APPROVAL_REQUIRED')
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if tool.risk != 'read':
                    row = db.execute('''SELECT * FROM ai_approvals WHERE id=? AND account_id=?
                        AND session_id=?''', (ticket_id, actor.account_id, actor.session_id)).fetchone()
                    if (row is None or row['tool'] != tool.name or row['tool_version'] != tool.version or
                            not isinstance(approval_nonce, str) or not hmac.compare_digest(row['nonce'], approval_nonce) or
                            not hmac.compare_digest(row['arguments_hash'], args_hash)):
                        raise AiError('APPROVAL_MISMATCH')
                    if row['consumed_at'] is not None:
                        raise AiError('APPROVAL_REPLAY')
                    if row['approved_at'] is None or row['expires_at'] <= self.clock():
                        raise AiError('APPROVAL_EXPIRED')
                previous = db.execute('SELECT * FROM ai_executions WHERE account_id=? AND operation_id=?',
                                      (actor.account_id, operation_id)).fetchone()
                if previous:
                    if previous['tool'] != tool.name or not hmac.compare_digest(previous['arguments_hash'], args_hash):
                        raise AiError('OPERATION_CONFLICT')
                    raise AiError('OPERATION_ALREADY_USED')
                if tool.risk != 'read':
                    db.execute('UPDATE ai_approvals SET consumed_at=? WHERE id=?', (self.clock(), ticket_id))
                db.execute('INSERT INTO ai_executions VALUES(?,?,?,?,?,NULL)',
                           (actor.account_id, operation_id, tool.name, args_hash, 'running'))
                db.execute('''INSERT INTO ai_audit(at,account_id,session_id,tool,operation_id,result)
                    VALUES(?,?,?,?,?,?)''', (self.clock(), actor.account_id, actor.session_id,
                                            tool.name, operation_id, 'started'))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        # Revalidação antes do efeito: o ticket não contorna revogação concorrente.
        effect_started = False
        try:
            self._check(actor, tool)
            effect_started = True
            result = tool.execute(actor, data)
            encoded = _canonical({'result': result}).decode('utf-8')
            if len(encoded) > 65536:
                raise AiError('RESULT_TOO_LARGE')
        except BaseException as exc:
            # Após entrar no executor o efeito pode ter ocorrido, inclusive se a
            # conexão cair antes da resposta. Nunca anunciar falha reexecutável.
            outcome = 'unknown' if effect_started else 'failed'
            with closing(self._db()) as db, db:
                db.execute('UPDATE ai_executions SET status=? WHERE account_id=? AND operation_id=?',
                           (outcome, actor.account_id, operation_id))
                db.execute('''INSERT INTO ai_audit(at,account_id,session_id,tool,operation_id,result)
                    VALUES(?,?,?,?,?,?)''', (self.clock(), actor.account_id, actor.session_id,
                                            tool.name, operation_id, outcome))
            if isinstance(exc, AiError):
                raise
            raise AiError('TOOL_FAILED') from exc
        with closing(self._db()) as db, db:
            db.execute('UPDATE ai_executions SET status=?,result_json=? WHERE account_id=? AND operation_id=?',
                       ('completed', encoded, actor.account_id, operation_id))
            db.execute('''INSERT INTO ai_audit(at,account_id,session_id,tool,operation_id,result)
                VALUES(?,?,?,?,?,?)''', (self.clock(), actor.account_id, actor.session_id,
                                        tool.name, operation_id, 'completed'))
        return result

    def execution_status(self, actor: ActorContext, operation_id: str) -> dict:
        if not self.session_active(actor):
            raise AiError('SESSION_REVOKED')
        with closing(self._db()) as db:
            row = db.execute('SELECT status,tool FROM ai_executions WHERE account_id=? AND operation_id=?',
                             (actor.account_id, operation_id)).fetchone()
        if row is None:
            raise AiError('OPERATION_NOT_FOUND')
        self.authorize(actor, self.registry.get(row['tool']).capability)
        return dict(row)

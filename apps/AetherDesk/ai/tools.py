"""Propostas nativas criadas pelo servidor; nenhum texto de chat executa ferramentas."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerClient
from apps.AetherDesk.support.migrations import apply_migration

from .approval import AiError, ApprovalEngine, ToolDescriptor, ToolRegistry


_SCHEMA = {'type': 'object', 'required': ['workload_id', 'operation_id'],
           'properties': {'workload_id': {'type': 'string', 'format': 'uuid'},
                          'operation_id': {'type': 'string', 'format': 'uuid'}},
           'additionalProperties': False}
_SCHEMA_DIGEST = hashlib.sha256(json.dumps(_SCHEMA, sort_keys=True,
    separators=(',', ':')).encode()).hexdigest()


def _validate_stop(arguments: dict) -> dict:
    if type(arguments) is not dict or set(arguments) != {'workload_id', 'operation_id'}:
        raise AiError('INVALID_ARGUMENTS')
    try:
        return {key: str(uuid.UUID(value)) for key, value in arguments.items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise AiError('INVALID_ARGUMENTS') from exc


class NativeTools:
    def __init__(self, db_path: str | Path, identity: IdentityService,
                 broker: BrokerClient, clock=time.time):
        self.db_path = str(db_path)
        self.identity, self.broker, self.clock = identity, broker, clock
        registry = ToolRegistry()
        registry.register(ToolDescriptor(
            name='workload.stop', version='1', capability='workloads.control',
            risk='destructive', validate=_validate_stop, execute=self._stop,
            schema_digest=_SCHEMA_DIGEST))
        def session_active(actor):
            try:
                identity.assert_active(actor)
                return True
            except Exception:
                return False
        self.approvals = ApprovalEngine(self.db_path, registry, identity.require,
                                        session_active, clock=clock)
        apply_migration(self.db_path, 'ai.proposals.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS ai_proposals (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, session_id TEXT NOT NULL,
                workload_id TEXT NOT NULL, tool TEXT NOT NULL,
                arguments_json TEXT NOT NULL, expires_at REAL NOT NULL, used_at REAL)'''))

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def _broker(self, actor: ActorContext, operation: str, **kwargs):
        account = self.identity.account(actor, actor.account_id)
        return self.broker.call('workload', actor.account_id, account['environment_id'],
                                {'operation': operation, 'session_id': actor.session_id, **kwargs})

    def _stop(self, actor: ActorContext, arguments: dict):
        return self._broker(actor, 'request', workload_id=arguments['workload_id'],
                            action='stop', operation_id=arguments['operation_id'],
                            template=None)

    def proposals(self, actor: ActorContext) -> list[dict]:
        self.identity.require(actor, 'ai.tools')
        self.identity.require(actor, 'workloads.control')
        workloads = self._broker(actor, 'list_mine')['items']
        now = self.clock()
        results = []
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM ai_proposals WHERE expires_at<?', (now,))
            for workload in workloads:
                if workload['observed'] != 'running' or workload['desired'] != 'running':
                    continue
                row = db.execute('''SELECT * FROM ai_proposals WHERE account_id=? AND session_id=?
                    AND workload_id=? AND used_at IS NULL AND expires_at>? ORDER BY expires_at DESC LIMIT 1''',
                    (actor.account_id, actor.session_id, workload['id'], now)).fetchone()
                if row is None:
                    arguments = {'workload_id': workload['id'], 'operation_id': str(uuid.uuid4())}
                    proposal_id = str(uuid.uuid4())
                    db.execute('INSERT INTO ai_proposals VALUES(?,?,?,?,?,?,?,NULL)',
                               (proposal_id, actor.account_id, actor.session_id, workload['id'],
                                'workload.stop', json.dumps(arguments, sort_keys=True), now + 120))
                else:
                    proposal_id = row['id']
                    arguments = json.loads(row['arguments_json'])
                results.append({'id': proposal_id, 'name': 'workload.stop', 'version': '1',
                                'source': 'native', 'risk': 'destructive',
                                'target': f"{workload['project']} / {workload['name']}",
                                'consequence': 'Parar a aplicação e interromper conexões ativas.',
                                'arguments': arguments, 'schemaDigest': _SCHEMA_DIGEST})
            db.commit()
        return results

    def _proposal(self, actor: ActorContext, proposal_id: str) -> dict:
        self.identity.require(actor, 'ai.tools')
        with closing(self._db()) as db:
            row = db.execute('''SELECT * FROM ai_proposals WHERE id=? AND account_id=?
                AND session_id=? AND used_at IS NULL AND expires_at>?''',
                (proposal_id, actor.account_id, actor.session_id, self.clock())).fetchone()
        if row is None:
            raise AiError('PROPOSAL_NOT_FOUND')
        return dict(row)

    def request(self, actor: ActorContext, proposal_id: str) -> dict:
        row = self._proposal(actor, proposal_id)
        return self.approvals.request(actor, row['tool'], json.loads(row['arguments_json']))

    def approve(self, actor: ActorContext, ticket_id: str, nonce: str) -> None:
        self.identity.require(actor, 'ai.tools')
        self.approvals.approve(actor, ticket_id, nonce)

    def invoke(self, actor: ActorContext, proposal_id: str, ticket_id: str,
               nonce: str, operation_id: str):
        row = self._proposal(actor, proposal_id)
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            claimed = db.execute('''UPDATE ai_proposals SET used_at=? WHERE id=? AND account_id=?
                AND session_id=? AND used_at IS NULL AND expires_at>?''',
                (self.clock(), proposal_id, actor.account_id, actor.session_id, self.clock()))
            if claimed.rowcount != 1:
                db.rollback()
                raise AiError('PROPOSAL_NOT_FOUND')
            db.commit()
        return self.approvals.invoke(actor, row['tool'], json.loads(row['arguments_json']),
                                     operation_id, ticket_id, nonce)

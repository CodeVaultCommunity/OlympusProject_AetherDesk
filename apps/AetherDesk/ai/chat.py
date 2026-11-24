"""Conversas privadas com provider explícito, disclosure, quota e cancelamento.

Providers externos ficam desabilitados por padrão. O resultado do provider é dado
não confiável e nunca é convertido automaticamente em chamada de ferramenta.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.migrations import apply_migration
from apps.AetherDesk.support.secrets import SecretError, SecretVault

from .approval import AiError


@dataclass(frozen=True)
class Provider:
    name: str
    external: bool
    disclosure: str
    stream: Callable[[list[dict], bytes | None], Iterable[str]]
    credential_ref: str | None = None
    cost_micros_per_1000_chars: int = 0


class ChatService:
    def __init__(self, db_path: str | Path,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 providers: dict[str, Provider] | None = None,
                 enabled_providers: frozenset[str] = frozenset(),
                 vault: SecretVault | None = None, daily_character_budget: int = 100_000,
                 daily_cost_budget_micros: int = 1_000_000,
                 requests_per_minute: int = 30,
                 retention_days: int = 30, clock: Callable[[], float] = time.time):
        if type(daily_character_budget) is not int or daily_character_budget < 1 or daily_character_budget > 10_000_000:
            raise AiError('INVALID_QUOTA')
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise AiError('INVALID_RETENTION')
        if type(daily_cost_budget_micros) is not int or daily_cost_budget_micros < 0:
            raise AiError('INVALID_COST_BUDGET')
        if type(requests_per_minute) is not int or not 1 <= requests_per_minute <= 600:
            raise AiError('INVALID_RATE_LIMIT')
        self.db_path = str(db_path)
        self.authorize = authorize
        self.session_active = session_active
        self.providers = dict(providers or {})
        self.enabled_providers = enabled_providers
        self.vault = vault
        self.daily_character_budget = daily_character_budget
        self.daily_cost_budget_micros = daily_cost_budget_micros
        self.requests_per_minute = requests_per_minute
        self.retention_days = retention_days
        self.clock = clock
        schema = '''
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, provider TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL,
                created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS ai_messages_conversation ON ai_messages(conversation_id,created_at);
            CREATE TABLE IF NOT EXISTS ai_daily_usage (
                owner_id TEXT NOT NULL, day INTEGER NOT NULL, used_chars INTEGER NOT NULL,
                reserved_chars INTEGER NOT NULL, used_cost_micros INTEGER NOT NULL,
                reserved_cost_micros INTEGER NOT NULL, PRIMARY KEY(owner_id,day));
            CREATE TABLE IF NOT EXISTS ai_chat_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, owner_id TEXT NOT NULL,
                session_id TEXT NOT NULL, provider TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_chat_rate (
                owner_id TEXT NOT NULL, minute INTEGER NOT NULL, requests INTEGER NOT NULL,
                PRIMARY KEY(owner_id,minute));
        '''
        apply_migration(self.db_path, 'ai.chat.v1',
                        lambda db: [db.execute(statement) for statement in schema.split(';') if statement.strip()])
        apply_migration(self.db_path, 'ai.chat.rate.v2', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS ai_chat_rate (
                owner_id TEXT NOT NULL, minute INTEGER NOT NULL, requests INTEGER NOT NULL,
                PRIMARY KEY(owner_id,minute))'''))

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def _check(self, actor: ActorContext) -> None:
        if not self.session_active(actor):
            raise AiError('SESSION_REVOKED')
        self.authorize(actor, 'ai.chat')

    def _provider(self, name: str) -> Provider:
        provider = self.providers.get(name)
        if provider is None or name not in self.enabled_providers:
            raise AiError('PROVIDER_DISABLED')
        if type(provider.cost_micros_per_1000_chars) is not int or provider.cost_micros_per_1000_chars < 0:
            raise AiError('INVALID_PROVIDER_COST')
        return provider

    def disclosure(self, actor: ActorContext, provider_name: str) -> dict:
        self._check(actor)
        provider = self._provider(provider_name)
        return {'provider': provider.name, 'external': provider.external,
                'data_sent': provider.disclosure, 'retention_days': self.retention_days}

    def create(self, actor: ActorContext, provider_name: str) -> str:
        self._check(actor)
        self._provider(provider_name)
        conversation_id, now = str(uuid.uuid4()), self.clock()
        with closing(self._db()) as db:
            db.execute('INSERT INTO ai_conversations VALUES(?,?,?,?,?)',
                       (conversation_id, actor.account_id, provider_name, now, now))
        return conversation_id

    def conversations(self, actor: ActorContext, limit: int = 100) -> list[dict]:
        self._check(actor)
        if type(limit) is not int or not 1 <= limit <= 200:
            raise AiError('INVALID_PAGE')
        with closing(self._db()) as db:
            rows = db.execute('''SELECT id,provider,created_at,updated_at FROM ai_conversations
                WHERE owner_id=? ORDER BY updated_at DESC,id DESC LIMIT ?''',
                (actor.account_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def usage(self, actor: ActorContext) -> dict:
        self._check(actor)
        day = int(self.clock() // 86400)
        with closing(self._db()) as db:
            row = db.execute('''SELECT used_chars,used_cost_micros FROM ai_daily_usage
                WHERE owner_id=? AND day=?''', (actor.account_id, day)).fetchone()
        return {'used_chars': row['used_chars'] if row else 0,
                'limit_chars': self.daily_character_budget,
                'used_cost_micros': row['used_cost_micros'] if row else 0,
                'limit_cost_micros': self.daily_cost_budget_micros}

    def messages(self, actor: ActorContext, conversation_id: str) -> list[dict]:
        self._check(actor)
        with closing(self._db()) as db:
            exists = db.execute('SELECT 1 FROM ai_conversations WHERE id=? AND owner_id=?',
                                (conversation_id, actor.account_id)).fetchone()
            if not exists:
                raise AiError('CONVERSATION_NOT_FOUND')
            rows = db.execute('''SELECT id,role,content,status,created_at FROM ai_messages
                WHERE conversation_id=? AND owner_id=? ORDER BY created_at,id''',
                (conversation_id, actor.account_id)).fetchall()
        return [dict(row) for row in rows]

    def export(self, actor: ActorContext, conversation_id: str) -> dict:
        self._check(actor)
        with closing(self._db()) as db:
            row = db.execute('SELECT id,provider,created_at FROM ai_conversations WHERE id=? AND owner_id=?',
                             (conversation_id, actor.account_id)).fetchone()
        if not row:
            raise AiError('CONVERSATION_NOT_FOUND')
        return {**dict(row), 'messages': self.messages(actor, conversation_id)}

    def delete(self, actor: ActorContext, conversation_id: str) -> None:
        self._check(actor)
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('DELETE FROM ai_conversations WHERE id=? AND owner_id=?',
                             (conversation_id, actor.account_id))
            if row.rowcount != 1:
                db.rollback()
                raise AiError('CONVERSATION_NOT_FOUND')
            db.execute('DELETE FROM ai_messages WHERE conversation_id=? AND owner_id=?',
                       (conversation_id, actor.account_id))
            db.commit()

    @staticmethod
    def _cost(amount: int, provider: Provider) -> int:
        return (amount * provider.cost_micros_per_1000_chars + 999) // 1000

    def _reserve(self, actor: ActorContext, amount: int, provider: Provider) -> int:
        day = int(self.clock() // 86400)
        minute = int(self.clock() // 60)
        cost = self._cost(amount, provider)
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR IGNORE INTO ai_daily_usage VALUES(?,?,0,0,0,0)''', (actor.account_id, day))
            row = db.execute('SELECT * FROM ai_daily_usage WHERE owner_id=? AND day=?',
                             (actor.account_id, day)).fetchone()
            if row['used_chars'] + row['reserved_chars'] + amount > self.daily_character_budget:
                db.rollback()
                raise AiError('CHAT_QUOTA')
            if row['used_cost_micros'] + row['reserved_cost_micros'] + cost > self.daily_cost_budget_micros:
                db.rollback()
                raise AiError('CHAT_COST_QUOTA')
            db.execute('INSERT OR IGNORE INTO ai_chat_rate VALUES(?,?,0)', (actor.account_id, minute))
            used = db.execute('SELECT requests FROM ai_chat_rate WHERE owner_id=? AND minute=?',
                              (actor.account_id, minute)).fetchone()['requests']
            if used >= self.requests_per_minute:
                db.rollback()
                raise AiError('CHAT_RATE_LIMIT')
            db.execute('UPDATE ai_chat_rate SET requests=requests+1 WHERE owner_id=? AND minute=?',
                       (actor.account_id, minute))
            db.execute('''UPDATE ai_daily_usage SET reserved_chars=reserved_chars+?,
                reserved_cost_micros=reserved_cost_micros+? WHERE owner_id=? AND day=?''',
                (amount, cost, actor.account_id, day))
            db.commit()
        return day

    def _settle(self, actor: ActorContext, day: int, reserved: int, used: int, provider: Provider) -> None:
        with closing(self._db()) as db:
            db.execute('''UPDATE ai_daily_usage SET reserved_chars=reserved_chars-?,used_chars=used_chars+?,
                reserved_cost_micros=reserved_cost_micros-?,used_cost_micros=used_cost_micros+?
                WHERE owner_id=? AND day=?''', (reserved, used, self._cost(reserved, provider),
                                               self._cost(used, provider), actor.account_id, day))

    def stream(self, actor: ActorContext, conversation_id: str, prompt: str,
               *, disclosure_accepted: bool, cancel: threading.Event,
               max_output_chars: int = 8192):
        self._check(actor)
        if not isinstance(prompt, str) or not prompt or len(prompt) > 16384:
            raise AiError('INVALID_PROMPT')
        if type(max_output_chars) is not int or not 1 <= max_output_chars <= 16384:
            raise AiError('INVALID_OUTPUT_LIMIT')
        with closing(self._db()) as db:
            row = db.execute('SELECT provider FROM ai_conversations WHERE id=? AND owner_id=?',
                             (conversation_id, actor.account_id)).fetchone()
        if row is None:
            raise AiError('CONVERSATION_NOT_FOUND')
        provider = self._provider(row['provider'])
        if provider.external and not disclosure_accepted:
            raise AiError('DISCLOSURE_REQUIRED')
        reserved = len(prompt) + max_output_chars
        day = self._reserve(actor, reserved, provider)
        chunks: list[str] = []
        status = 'failed'
        try:
            if cancel.is_set():
                status = 'cancelled'
                return
            history = self.messages(actor, conversation_id)
            messages = [{'role': item['role'], 'content': item['content']} for item in history]
            messages.append({'role': 'user', 'content': prompt})
            if provider.credential_ref and self.vault is None:
                raise AiError('CREDENTIAL_UNAVAILABLE')
            try:
                credential = self.vault.read(actor.account_id, provider.credential_ref, 'ai') if provider.credential_ref else None
            except SecretError as exc:
                raise AiError('CREDENTIAL_UNAVAILABLE') from exc
            for chunk in provider.stream(messages, credential):
                self._check(actor)
                if provider.credential_ref:
                    try:
                        self.vault.read(actor.account_id, provider.credential_ref, 'ai')
                    except SecretError as exc:
                        raise AiError('CREDENTIAL_REVOKED') from exc
                if cancel.is_set():
                    status = 'cancelled'
                    break
                if type(chunk) is not str or sum(map(len, chunks)) + len(chunk) > max_output_chars:
                    raise AiError('PROVIDER_OUTPUT_LIMIT')
                chunks.append(chunk)
                yield chunk
            else:
                status = 'completed'
            if status in ('completed', 'cancelled'):
                now = self.clock()
                with closing(self._db()) as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('INSERT INTO ai_messages VALUES(?,?,?,?,?,?,?)',
                               (str(uuid.uuid4()), conversation_id, actor.account_id, 'user', prompt, 'completed', now))
                    db.execute('INSERT INTO ai_messages VALUES(?,?,?,?,?,?,?)',
                               (str(uuid.uuid4()), conversation_id, actor.account_id, 'assistant',
                                ''.join(chunks), status, now + .000001))
                    db.execute('UPDATE ai_conversations SET updated_at=? WHERE id=? AND owner_id=?',
                               (now, conversation_id, actor.account_id))
                    db.commit()
        finally:
            self._settle(actor, day, reserved, len(prompt) + sum(map(len, chunks)), provider)
            with closing(self._db()) as db:
                db.execute('INSERT INTO ai_chat_audit(at,owner_id,session_id,provider,result) VALUES(?,?,?,?,?)',
                           (self.clock(), actor.account_id, actor.session_id, provider.name, status))

    def prune(self) -> int:
        cutoff = self.clock() - self.retention_days * 86400
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT id FROM ai_conversations WHERE updated_at<?', (cutoff,)).fetchall()
            for row in rows:
                db.execute('DELETE FROM ai_messages WHERE conversation_id=?', (row['id'],))
                db.execute('DELETE FROM ai_conversations WHERE id=?', (row['id'],))
            db.execute('DELETE FROM ai_chat_rate WHERE minute<?',
                       (int(self.clock() // 60) - 1440,))
            db.commit()
        return len(rows)

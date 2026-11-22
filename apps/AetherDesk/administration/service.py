"""Consultas administrativas e estado pessoal persistente."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import ActorContext, IdentityService


class AdministrationError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class AdministrationService:
    def __init__(self, db_path: str | Path, identity: IdentityService, composition: AppComposition):
        self.db_path = str(db_path)
        self.identity = identity
        self.composition = composition
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS desktop_states(account_id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS backup_settings(id INTEGER PRIMARY KEY CHECK(id=1),
                    enabled INTEGER NOT NULL DEFAULT 0, frequency_hours INTEGER NOT NULL DEFAULT 24,
                    destination TEXT NOT NULL DEFAULT '', retention_mode TEXT NOT NULL DEFAULT 'replace',
                    retention_days INTEGER);
                INSERT OR IGNORE INTO backup_settings(id) VALUES(1);
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def accounts(self, actor: ActorContext):
        self.identity.require(actor, 'accounts.view')
        with self.identity._connect() as db:
            return [dict(row) for row in db.execute('''SELECT id,username,role,state,environment_id,
                revision,created_at FROM accounts ORDER BY username COLLATE NOCASE''')]

    def permissions(self, actor: ActorContext, account_id: str):
        self.identity.require(actor, 'permissions.view')
        account = self.identity.account(actor, account_id)
        from apps.AetherDesk.identity.service import ADMIN_CAPABILITIES, MEMBER_CAPABILITIES
        capabilities = set(ADMIN_CAPABILITIES if account['role'] == 'admin' else MEMBER_CAPABILITIES)
        with self.identity._connect() as db:
            for row in db.execute('SELECT capability,allowed FROM permission_overrides WHERE account_id=?', (account_id,)):
                if row['allowed']:
                    capabilities.add(row['capability'])
                else:
                    capabilities.discard(row['capability'])
        return sorted(capabilities)

    def sessions(self, actor: ActorContext, account_id: str):
        self.identity.require(actor, 'sessions.revoke')
        self.identity.account(actor, account_id)
        with self.identity._connect() as db:
            return [dict(row) for row in db.execute('''SELECT id,created_at,revoked_at FROM sessions
                WHERE account_id=? ORDER BY created_at DESC''', (account_id,))]

    def audit(self, actor: ActorContext, limit: int = 100):
        self.identity.require(actor, 'audit.view')
        with self.identity._connect() as db:
            return [dict(row) for row in db.execute('''SELECT id,actor_id,operation,target_id,at,result
                FROM audit_events ORDER BY at DESC LIMIT ?''', (min(max(limit, 1), 500),))]

    def environment(self, actor: ActorContext, account_id: str):
        self.identity.require(actor, 'environment.manage')
        account = self.identity.account(actor, account_id)
        env = self.composition.runtime.state(account_id, account['environment_id'])
        return {'account_id': account_id, 'state': env.state}

    def retry_environment(self, actor: ActorContext, account_id: str):
        self.identity.require(actor, 'environment.manage')
        account = self.identity.account(actor, account_id)
        env = self.composition.runtime.ensure(account_id, account['environment_id'])
        with self.identity._connect() as db:
            self.identity._audit(db, actor.account_id, 'environment.retry', account_id)
        return {'account_id': account_id, 'state': env.state}

    def stop_session(self, actor: ActorContext, account_id: str):
        self.composition.stop_account_session(actor, account_id)
        return {'stopped': True}

    def get_desktop(self, actor: ActorContext):
        self.identity.require(actor, 'preferences.read')
        with self._db() as db:
            row = db.execute('SELECT body FROM desktop_states WHERE account_id=?', (actor.account_id,)).fetchone()
        return json.loads(row['body']) if row else {'windows': [], 'activeId': None, 'theme': 'dark'}

    def put_desktop(self, actor: ActorContext, state: dict):
        self.identity.require(actor, 'preferences.write')
        if state.get('theme') not in ('dark', 'light') or not isinstance(state.get('windows'), list) or len(state['windows']) > 40:
            raise AdministrationError('INVALID_DESKTOP')
        for window in state['windows']:
            if window.get('kind') not in ('explorer', 'editor', 'terminal', 'monitor', 'admin', 'settings'):
                raise AdministrationError('INVALID_DESKTOP')
            for key in ('x', 'y', 'width', 'height', 'z'):
                if not isinstance(window.get(key), (int, float)) or abs(window[key]) > 10000:
                    raise AdministrationError('INVALID_DESKTOP')
        body = json.dumps(state, separators=(',', ':'))
        if len(body) > 65536:
            raise AdministrationError('TOO_LARGE')
        with self._db() as db:
            db.execute('''INSERT INTO desktop_states VALUES(?,?)
                ON CONFLICT(account_id) DO UPDATE SET body=excluded.body''', (actor.account_id, body))
        return state

    def backup_settings(self, actor: ActorContext):
        self.identity.require(actor, 'backup.view')
        with self._db() as db:
            return dict(db.execute('SELECT enabled,frequency_hours,destination,retention_mode,retention_days FROM backup_settings WHERE id=1').fetchone())

    def configure_backup(self, actor: ActorContext, *, enabled: bool, frequency_hours: int,
                         destination: str, retention_mode: str, retention_days: int | None):
        self.identity.require(actor, 'backup.manage')
        if not 1 <= frequency_hours <= 8760 or retention_mode not in ('replace', 'days'):
            raise AdministrationError('INVALID_BACKUP_POLICY')
        if retention_mode == 'days' and (retention_days is None or not 1 <= retention_days <= 3650):
            raise AdministrationError('INVALID_BACKUP_POLICY')
        if enabled and (not destination.startswith('/') or '..' in Path(destination).parts or len(destination) > 512):
            raise AdministrationError('INVALID_BACKUP_DESTINATION')
        with self._db() as db:
            db.execute('''UPDATE backup_settings SET enabled=?,frequency_hours=?,destination=?,
                retention_mode=?,retention_days=? WHERE id=1''',
                (int(enabled), frequency_hours, destination, retention_mode,
                 retention_days if retention_mode == 'days' else None))
            self.identity._audit(db, actor.account_id, 'backup.configure', 'backup')
        return self.backup_settings(actor)

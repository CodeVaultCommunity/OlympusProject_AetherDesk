"""Consultas administrativas e estado pessoal persistente."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.support.migrations import apply_migration


class AdministrationError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class AdministrationService:
    def __init__(self, db_path: str | Path, identity: IdentityService, composition: AppComposition):
        self.db_path = str(db_path)
        self.identity = identity
        self.composition = composition
        def migrate(db: sqlite3.Connection):
            db.execute('CREATE TABLE IF NOT EXISTS desktop_states(account_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS backup_settings(id INTEGER PRIMARY KEY CHECK(id=1),
                    enabled INTEGER NOT NULL DEFAULT 0, frequency_hours INTEGER NOT NULL DEFAULT 24,
                    destination TEXT NOT NULL DEFAULT '', retention_mode TEXT NOT NULL DEFAULT 'replace',
                    retention_days INTEGER)''')
            db.execute('INSERT OR IGNORE INTO backup_settings(id) VALUES(1)')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(desktop_states)')}
            if 'revision' not in columns:
                db.execute('ALTER TABLE desktop_states ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
            if 'updated_at' not in columns:
                db.execute("ALTER TABLE desktop_states ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        apply_migration(self.db_path, 'administration.desktop.v2', migrate)
        def add_backup_objectives(db: sqlite3.Connection):
            db.execute('ALTER TABLE backup_settings ADD COLUMN rpo_hours INTEGER')
            db.execute('ALTER TABLE backup_settings ADD COLUMN rto_hours INTEGER')
        apply_migration(self.db_path, 'administration.backup.objectives.v1', add_backup_objectives)

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
        return self.get_desktop_record(actor)['state']

    def get_desktop_record(self, actor: ActorContext):
        self.identity.require(actor, 'preferences.read')
        with self._db() as db:
            row = db.execute('SELECT body,revision FROM desktop_states WHERE account_id=?',
                             (actor.account_id,)).fetchone()
        return {'state': json.loads(row['body']), 'revision': row['revision']} if row else {
            'state': {'windows': [], 'activeId': None, 'theme': 'dark'}, 'revision': 0}

    def put_desktop(self, actor: ActorContext, state: dict,
                    expected_revision: int | None = None):
        self.identity.require(actor, 'preferences.write')
        if not isinstance(state, dict) or state.get('theme') not in ('dark', 'light') or not isinstance(state.get('windows'), list) or len(state['windows']) > 40:
            raise AdministrationError('INVALID_DESKTOP')
        version = state.get('schemaVersion', 1)
        if version not in (1, 2) or isinstance(version, bool):
            raise AdministrationError('INVALID_DESKTOP')
        if version == 2 and expected_revision is None:
            raise AdministrationError('PRECONDITION_REQUIRED')
        if version == 2 and set(state) != {'schemaVersion', 'windows', 'activeId', 'theme'}:
            raise AdministrationError('INVALID_DESKTOP')
        if expected_revision is not None and (isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0):
            raise AdministrationError('INVALID_REVISION')
        ids = set()
        for window in state['windows']:
            if not isinstance(window, dict):
                raise AdministrationError('INVALID_DESKTOP')
            if window.get('kind') not in ('explorer', 'editor', 'terminal', 'monitor', 'admin', 'settings'):
                raise AdministrationError('INVALID_DESKTOP')
            for key in ('x', 'y', 'width', 'height', 'z'):
                value = window.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 10000:
                    raise AdministrationError('INVALID_DESKTOP')
            if version == 2:
                if set(window) != {'id', 'kind', 'x', 'y', 'width', 'height', 'z', 'minimized', 'maximized'}:
                    raise AdministrationError('INVALID_DESKTOP')
                if not isinstance(window.get('id'), str) or not 1 <= len(window['id']) <= 100 or window['id'] in ids:
                    raise AdministrationError('INVALID_DESKTOP')
                ids.add(window['id'])
                if window['width'] < 200 or window['height'] < 160 or not isinstance(window['z'], int) or window['z'] < 1:
                    raise AdministrationError('INVALID_DESKTOP')
                if not isinstance(window.get('minimized'), bool) or not isinstance(window.get('maximized'), bool):
                    raise AdministrationError('INVALID_DESKTOP')
        active_id = state.get('activeId')
        if version == 2 and active_id is not None and (
            not isinstance(active_id, str) or active_id not in ids
        ):
            raise AdministrationError('INVALID_DESKTOP')
        body = json.dumps(state, separators=(',', ':'))
        if len(body) > 65536:
            raise AdministrationError('TOO_LARGE')
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision,body FROM desktop_states WHERE account_id=?',
                             (actor.account_id,)).fetchone()
            revision = row['revision'] if row else 0
            if version == 1 and row and json.loads(row['body']).get('schemaVersion') == 2:
                raise AdministrationError('CLIENT_UPGRADE_REQUIRED')
            if expected_revision is not None and expected_revision != revision:
                raise AdministrationError('STALE_REVISION')
            if row:
                db.execute('UPDATE desktop_states SET body=?,revision=?,updated_at=? WHERE account_id=?',
                           (body, revision + 1, now, actor.account_id))
            else:
                db.execute('INSERT INTO desktop_states(account_id,body,revision,updated_at) VALUES(?,?,?,?)',
                           (actor.account_id, body, 1, now))
        return state

    def backup_settings(self, actor: ActorContext):
        self.identity.require(actor, 'backup.view')
        with self._db() as db:
            return dict(db.execute('''SELECT enabled,frequency_hours,destination,retention_mode,
                retention_days,rpo_hours,rto_hours FROM backup_settings WHERE id=1''').fetchone())

    def configure_backup(self, actor: ActorContext, *, enabled: bool, frequency_hours: int,
                         destination: str, retention_mode: str, retention_days: int | None,
                         rpo_hours: int | None = None, rto_hours: int | None = None):
        self.identity.require(actor, 'backup.manage')
        if not 1 <= frequency_hours <= 8760 or retention_mode not in ('replace', 'days'):
            raise AdministrationError('INVALID_BACKUP_POLICY')
        if retention_mode == 'days' and (retention_days is None or not 1 <= retention_days <= 3650):
            raise AdministrationError('INVALID_BACKUP_POLICY')
        if any(value is not None and (type(value) is not int or not 1 <= value <= 8760)
               for value in (rpo_hours, rto_hours)):
            raise AdministrationError('INVALID_BACKUP_OBJECTIVE')
        if enabled and rpo_hours is not None and frequency_hours > rpo_hours:
            raise AdministrationError('INVALID_BACKUP_OBJECTIVE')
        if enabled and (not destination.startswith('/') or '..' in Path(destination).parts or len(destination) > 512):
            raise AdministrationError('INVALID_BACKUP_DESTINATION')
        with self._db() as db:
            db.execute('''UPDATE backup_settings SET enabled=?,frequency_hours=?,destination=?,
                retention_mode=?,retention_days=?,rpo_hours=?,rto_hours=? WHERE id=1''',
                (int(enabled), frequency_hours, destination, retention_mode,
                 retention_days if retention_mode == 'days' else None, rpo_hours, rto_hours))
            self.identity._audit(db, actor.account_id, 'backup.configure', 'backup')
        return self.backup_settings(actor)

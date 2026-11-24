"""Estado desejado/observado e jobs idempotentes para imagens aprovadas.

Build de Dockerfile arbitrário, portas públicas, egress e secrets em env ficam
desabilitados no MVP; o runtime tipado é executado exclusivamente no broker.
"""

from __future__ import annotations

import re
import json
import hashlib
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.leases import LeaseStore
from apps.AetherDesk.support.migrations import apply_migration
from apps.AetherDesk.support.workers import LeasedJob
from apps.AetherDesk.support.secrets import SecretError, SecretVault


class WorkloadError(Exception):
    pass


@dataclass(frozen=True)
class ApprovedTemplate:
    name: str
    image: str
    sbom_sha256: str
    provenance_sha256: str
    scan_passed: bool
    command: tuple[str, ...] = ()
    health_command: str | None = None
    port: int | None = None

    def validate(self) -> None:
        if (not re.fullmatch(r'[a-z][a-z0-9_-]{0,40}', self.name) or
                not (re.fullmatch(r'[a-zA-Z0-9_./:-]+@sha256:[0-9a-f]{64}', self.image) or
                     re.fullmatch(r'sha256:[0-9a-f]{64}', self.image)) or
                not re.fullmatch(r'[0-9a-f]{64}', self.sbom_sha256) or
                not re.fullmatch(r'[0-9a-f]{64}', self.provenance_sha256) or
                not self.scan_passed or any(not isinstance(part, str) or not part or '\0' in part for part in self.command) or
                (self.health_command is not None and (not isinstance(self.health_command, str) or
                 not 1 <= len(self.health_command) <= 200 or any(char in self.health_command for char in '\0\r\n'))) or
                (self.port is not None and (type(self.port) is not int or not 1 <= self.port <= 65535))):
            raise WorkloadError('UNAPPROVED_TEMPLATE')


class Runtime(Protocol):
    def ensure(self, owner_id: str, workload_id: str, template: ApprovedTemplate,
               revision: int | None = None) -> str: ...
    def state(self, owner_id: str, workload_id: str) -> str: ...
    def healthy(self, owner_id: str, workload_id: str) -> bool: ...
    def stop(self, owner_id: str, workload_id: str) -> None: ...
    def remove(self, owner_id: str, workload_id: str) -> None: ...
    def remove_volume(self, owner_id: str, workload_id: str) -> None: ...
    def logs(self, owner_id: str, workload_id: str, limit: int) -> str: ...
    def metrics(self, owner_id: str, workload_id: str) -> dict: ...
    def ensure_secrets(self, owner_id: str, workload_id: str, template: ApprovedTemplate,
                       secrets: dict[str, bytes], revision: int) -> str: ...


class WorkloadService:
    def __init__(self, db_path: str | Path, runtime: Runtime,
                 templates: dict[str, ApprovedTemplate],
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 vault: SecretVault | None = None,
                 clock: Callable[[], float] = time.time,
                 removed_retention_seconds: int = 604800):
        if type(removed_retention_seconds) is not int or removed_retention_seconds < 0:
            raise WorkloadError('INVALID_RETENTION')
        for name, template in templates.items():
            template.validate()
            if name != template.name:
                raise WorkloadError('UNAPPROVED_TEMPLATE')
        self.db_path = str(db_path)
        self.runtime = runtime
        self.templates = dict(templates)
        self.authorize = authorize
        self.session_active = session_active
        self.vault = vault
        self.clock = clock
        self.removed_retention_seconds = removed_retention_seconds
        schema = '''
            CREATE TABLE IF NOT EXISTS workload_projects (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
                created_at REAL NOT NULL, UNIQUE(owner_id,name));
            CREATE TABLE IF NOT EXISTS workloads (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                name TEXT NOT NULL, desired TEXT NOT NULL, observed TEXT NOT NULL,
                template TEXT, previous_template TEXT, revision INTEGER NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(project_id,name));
            CREATE TABLE IF NOT EXISTS workload_jobs (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, workload_id TEXT NOT NULL,
                operation_id TEXT NOT NULL, action TEXT NOT NULL, template TEXT,
                status TEXT NOT NULL, error_code TEXT, created_at REAL NOT NULL,
                UNIQUE(owner_id,operation_id));
            CREATE TABLE IF NOT EXISTS workload_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                actor_id TEXT NOT NULL, workload_id TEXT NOT NULL,
                action TEXT NOT NULL, result TEXT NOT NULL);
        '''
        apply_migration(self.db_path, 'workloads.core.v1',
                        lambda db: [db.execute(statement) for statement in schema.split(';') if statement.strip()])
        apply_migration(self.db_path, 'workloads.secrets.v2', lambda db: db.execute(
            "ALTER TABLE workloads ADD COLUMN secret_refs TEXT NOT NULL DEFAULT '{}'"))
        apply_migration(self.db_path, 'workloads.secret_ops.v3', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS workload_secret_ops (
                owner_id TEXT NOT NULL, operation_id TEXT NOT NULL, workload_id TEXT NOT NULL,
                references_hash TEXT NOT NULL, PRIMARY KEY(owner_id,operation_id))'''))
        self.leases = LeaseStore(self.db_path)

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def _check(self, actor: ActorContext, capability: str) -> None:
        if not self.session_active(actor):
            raise WorkloadError('SESSION_REVOKED')
        self.authorize(actor, capability)

    def approved_templates(self, actor: ActorContext) -> list[str]:
        self._check(actor, 'workloads.deploy')
        return sorted(self.templates)

    def project(self, actor: ActorContext, name: str) -> str:
        self._check(actor, 'workloads.create')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,60}', name):
            raise WorkloadError('INVALID_PROJECT')
        project_id = str(uuid.uuid4())
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO workload_projects VALUES(?,?,?,?)',
                       (project_id, actor.account_id, name, self.clock()))
            row = db.execute('SELECT id FROM workload_projects WHERE owner_id=? AND name=?',
                             (actor.account_id, name)).fetchone()
            db.commit()
        return row['id']

    def create(self, actor: ActorContext, project_id: str, name: str) -> str:
        self._check(actor, 'workloads.create')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,50}', name):
            raise WorkloadError('INVALID_WORKLOAD')
        workload_id, now = str(uuid.uuid4()), self.clock()
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            project = db.execute('SELECT 1 FROM workload_projects WHERE id=? AND owner_id=?',
                                 (project_id, actor.account_id)).fetchone()
            if project is None:
                db.rollback()
                raise WorkloadError('PROJECT_NOT_FOUND')
            db.execute('''INSERT OR IGNORE INTO workloads(id,project_id,owner_id,name,desired,
                observed,template,previous_template,revision,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                       (workload_id, project_id, actor.account_id, name, 'stopped',
                        'absent', None, None, 1, now, now))
            row = db.execute('SELECT id FROM workloads WHERE project_id=? AND owner_id=? AND name=?',
                             (project_id, actor.account_id, name)).fetchone()
            db.commit()
        return row['id']

    def configure_secrets(self, actor: ActorContext, workload_id: str,
                          references: dict[str, str], operation_id: str) -> None:
        self._check(actor, 'workloads.secrets')
        if self.vault is None:
            raise WorkloadError('SECRETS_DISABLED')
        if (type(references) is not dict or len(references) > 16 or
                any(not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,40}', name)
                    for name in references)):
            raise WorkloadError('INVALID_SECRET_REFS')
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (TypeError, ValueError) as exc:
            raise WorkloadError('INVALID_OPERATION_ID') from exc
        normalized = {}
        for name, reference in references.items():
            try:
                reference = str(uuid.UUID(reference))
            except (TypeError, ValueError) as exc:
                raise WorkloadError('SECRET_REF_UNAVAILABLE') from exc
            normalized[name] = reference
        serialized = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM workload_secret_ops WHERE owner_id=? AND operation_id=?',
                                  (actor.account_id, operation_id)).fetchone()
            if existing:
                db.commit()
                if existing['workload_id'] != workload_id or existing['references_hash'] != digest:
                    raise WorkloadError('OPERATION_CONFLICT')
                return
            try:
                for reference in normalized.values():
                    self.vault.read(actor.account_id, reference, 'workload')
            except SecretError as exc:
                db.rollback()
                raise WorkloadError('SECRET_REF_UNAVAILABLE') from exc
            changed = db.execute('''UPDATE workloads SET secret_refs=?,revision=revision+1,
                updated_at=? WHERE id=? AND owner_id=? AND desired!='removed' ''',
                (serialized, self.clock(), workload_id, actor.account_id))
            if changed.rowcount != 1:
                db.rollback()
                raise WorkloadError('WORKLOAD_NOT_FOUND')
            db.execute('INSERT INTO workload_audit(at,actor_id,workload_id,action,result) VALUES(?,?,?,?,?)',
                       (self.clock(), actor.account_id, workload_id, 'configure_secrets', 'updated'))
            db.execute('INSERT INTO workload_secret_ops VALUES(?,?,?,?)',
                       (actor.account_id, operation_id, workload_id, digest))
            db.commit()

    def state(self, actor: ActorContext, workload_id: str) -> dict:
        self._check(actor, 'workloads.read')
        with closing(self._db()) as db:
            row = db.execute('''SELECT id,project_id,name,desired,observed,template,
                revision,created_at,updated_at FROM workloads WHERE id=? AND owner_id=?''',
                (workload_id, actor.account_id)).fetchone()
        if row is None:
            raise WorkloadError('WORKLOAD_NOT_FOUND')
        return dict(row)

    def list_mine(self, actor: ActorContext, limit: int = 100) -> list[dict]:
        self._check(actor, 'workloads.read')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise WorkloadError('INVALID_PAGE')
        with closing(self._db()) as db:
            rows = db.execute('''SELECT w.id,w.name,w.desired,w.observed,w.template,w.updated_at,
                p.name AS project FROM workloads w JOIN workload_projects p ON p.id=w.project_id
                WHERE w.owner_id=? AND w.desired!='removed' ORDER BY w.updated_at DESC,w.id LIMIT ?''',
                (actor.account_id, limit)).fetchall()
        return [self._summary(dict(row), 'self') for row in rows]

    def list_controllable(self, actor: ActorContext, limit: int = 100) -> list[dict]:
        self._check(actor, 'workloads.control.other')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise WorkloadError('INVALID_PAGE')
        with closing(self._db()) as db:
            rows = db.execute('''SELECT w.id,w.name,w.desired,w.observed,w.template,w.updated_at,
                'Conta alheia' AS project FROM workloads w
                WHERE w.owner_id!=? AND w.desired!='removed' ORDER BY w.updated_at DESC,w.id LIMIT ?''',
                (actor.account_id, limit)).fetchall()
        return [self._summary(dict(row), 'other') for row in rows]

    def _summary(self, row: dict, owner: str) -> dict:
        template = self.templates.get(row['template'])
        return {'id': row['id'], 'owner': owner, 'name': row['name'],
                'project': row['project'], 'desired': row['desired'],
                'observed': row['observed'], 'template': row['template'],
                'health': row['observed'], 'port': template.port if template else None,
                'route': None, 'volume': f'Retenção {self.removed_retention_seconds // 86400} dias',
                'updatedAt': row['updated_at']}

    def job(self, actor: ActorContext, job_id: str) -> dict:
        if not self.session_active(actor):
            raise WorkloadError('SESSION_REVOKED')
        with closing(self._db()) as db:
            row = db.execute('''SELECT id,owner_id,workload_id,action,status,error_code,created_at
                FROM workload_jobs WHERE id=?''', (job_id,)).fetchone()
        if row is None:
            raise WorkloadError('JOB_NOT_FOUND')
        self.authorize(actor, 'workloads.read' if row['owner_id'] == actor.account_id
                       else 'workloads.control.other')
        return {key: row[key] for key in ('id', 'workload_id', 'action', 'status',
                                          'error_code', 'created_at')}

    def cancel(self, actor: ActorContext, job_id: str) -> dict:
        if not self.session_active(actor):
            raise WorkloadError('SESSION_REVOKED')
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT j.*,w.desired,w.observed,w.template AS current_template,
                w.previous_template,w.revision,w.owner_id AS workload_owner FROM workload_jobs j
                JOIN workloads w ON w.id=j.workload_id
                WHERE j.id=?''', (job_id,)).fetchone()
            if row is None:
                db.rollback()
                raise WorkloadError('JOB_NOT_FOUND')
            try:
                self.authorize(actor, 'workloads.control' if row['workload_owner'] == actor.account_id
                               else 'workloads.control.other')
            except BaseException:
                db.rollback()
                raise
            if row['status'] != 'pending':
                db.commit()
                return {'id': job_id, 'status': row['status']}
            desired = 'running' if row['observed'] in ('running', 'rolled_back') else 'stopped'
            template = row['previous_template'] if row['action'] == 'deploy' else row['current_template']
            if row['action'] == 'deploy' and not template:
                desired = 'stopped'
            db.execute('''UPDATE workloads SET desired=?,template=?,revision=revision+1,
                updated_at=? WHERE id=? AND revision=?''',
                (desired, template, self.clock(), row['workload_id'], row['revision']))
            db.execute("UPDATE workload_jobs SET status='cancelled' WHERE id=? AND status='pending'",
                       (job_id,))
            db.execute('INSERT INTO workload_audit(at,actor_id,workload_id,action,result) VALUES(?,?,?,?,?)',
                       (self.clock(), actor.account_id, row['workload_id'], 'cancel', 'cancelled'))
            db.commit()
        return {'id': job_id, 'status': 'cancelled'}

    def request(self, actor: ActorContext, workload_id: str, action: str,
                operation_id: str, template_name: str | None = None) -> dict:
        if action not in ('deploy', 'start', 'stop', 'restart', 'remove'):
            raise WorkloadError('INVALID_ACTION')
        self._check(actor, 'workloads.deploy' if action in ('deploy', 'restart') else 'workloads.control')
        return self._request(actor, actor.account_id, workload_id, action, operation_id, template_name)

    def admin_state(self, actor: ActorContext, workload_id: str) -> dict:
        self._check(actor, 'workloads.control.other')
        with closing(self._db()) as db:
            row = db.execute('SELECT id,name,desired,observed,template FROM workloads WHERE id=?',
                             (workload_id,)).fetchone()
        if row is None:
            raise WorkloadError('WORKLOAD_NOT_FOUND')
        return dict(row)

    def admin_request(self, actor: ActorContext, workload_id: str, action: str,
                      operation_id: str) -> dict:
        if action not in ('stop', 'restart', 'remove'):
            raise WorkloadError('INVALID_ACTION')
        self._check(actor, 'workloads.control.other')
        if action == 'restart':
            self._check(actor, 'workloads.deploy')
        with closing(self._db()) as db:
            row = db.execute('SELECT owner_id FROM workloads WHERE id=?', (workload_id,)).fetchone()
        if row is None:
            raise WorkloadError('WORKLOAD_NOT_FOUND')
        return self._request(actor, row['owner_id'], workload_id, action, operation_id, None)

    def _request(self, actor: ActorContext, owner_id: str, workload_id: str,
                 action: str, operation_id: str, template_name: str | None) -> dict:
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (TypeError, ValueError) as exc:
            raise WorkloadError('INVALID_OPERATION_ID') from exc
        if action == 'deploy' and template_name not in self.templates:
            raise WorkloadError('UNAPPROVED_TEMPLATE')
        if action != 'deploy' and template_name is not None:
            raise WorkloadError('INVALID_TEMPLATE')
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM workloads WHERE id=? AND owner_id=?',
                             (workload_id, owner_id)).fetchone()
            if row is None:
                db.rollback()
                raise WorkloadError('WORKLOAD_NOT_FOUND')
            existing = db.execute('SELECT * FROM workload_jobs WHERE owner_id=? AND operation_id=?',
                                  (owner_id, operation_id)).fetchone()
            if existing:
                if existing['workload_id'] != workload_id or existing['action'] != action or existing['template'] != template_name:
                    db.rollback()
                    raise WorkloadError('OPERATION_CONFLICT')
                db.commit()
                return {'id': existing['id'], 'status': existing['status']}
            if row['desired'] == 'removed':
                db.rollback()
                raise WorkloadError('WORKLOAD_REMOVED')
            if action in ('start', 'restart') and not row['template']:
                db.rollback()
                raise WorkloadError('NO_DEPLOYMENT')
            desired = 'running' if action in ('deploy', 'start', 'restart') else 'stopped' if action == 'stop' else 'removed'
            previous = row['template'] if action == 'deploy' else row['previous_template']
            current_template = template_name if action == 'deploy' else row['template']
            now, job_id = self.clock(), str(uuid.uuid4())
            db.execute('''UPDATE workload_jobs SET status='superseded',
                error_code='SUPERSEDED_BY_NEWER_REQUEST'
                WHERE workload_id=? AND status='pending' ''', (workload_id,))
            db.execute('''UPDATE workloads SET desired=?,template=?,previous_template=?,
                revision=revision+1,updated_at=? WHERE id=?''',
                (desired, current_template, previous, now, workload_id))
            db.execute('INSERT INTO workload_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                       (job_id, owner_id, workload_id, operation_id, action,
                        template_name, 'pending', None, now))
            db.execute('INSERT INTO workload_audit(at,actor_id,workload_id,action,result) VALUES(?,?,?,?,?)',
                       (now, actor.account_id, workload_id, action, 'requested'))
            db.commit()
        return {'id': job_id, 'status': 'pending'}

    def suspend_pending_deploys(self) -> int:
        """Reverte deploy/restart ainda pendentes quando o kill switch é acionado."""
        return self._suspend_pending(False)

    def suspend_pending_mutations(self) -> int:
        """Safe mode congela a fila sem executar pedidos antigos ao voltar."""
        return self._suspend_pending(True)

    def _suspend_pending(self, all_actions: bool) -> int:
        action_filter = '' if all_actions else " AND action IN ('deploy','restart')"
        with closing(self._db()) as db:
            ids = [row['id'] for row in db.execute('''SELECT DISTINCT w.id FROM workloads w
                JOIN workload_jobs j ON j.workload_id=w.id
                WHERE j.status='pending' ''' + action_filter)]
        suspended = 0
        for workload_id in ids:
            def operation(guard):
                nonlocal suspended
                if not guard():
                    return
                with closing(self._db()) as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('''SELECT w.*,j.action FROM workloads w
                        JOIN workload_jobs j ON j.workload_id=w.id
                        WHERE w.id=? AND j.status='pending' ''' + action_filter,
                        (workload_id,)).fetchone()
                    if row is None or not guard():
                        db.rollback()
                        return
                    previous = row['previous_template'] if row['action'] == 'deploy' else row['template']
                    desired = 'running' if row['observed'] in ('running', 'rolled_back') else 'stopped'
                    if previous is None:
                        desired = 'stopped'
                    db.execute('''UPDATE workloads SET desired=?,template=?,revision=revision+1,
                        updated_at=? WHERE id=?''',
                        (desired, previous, self.clock(), workload_id))
                    changed = db.execute('''UPDATE workload_jobs SET status='failed',
                        error_code=? WHERE workload_id=? AND status='pending' ''' + action_filter,
                        ('SAFE_MODE' if all_actions else 'DEPLOY_DISABLED', workload_id)).rowcount
                    db.execute('''INSERT INTO workload_audit(at,actor_id,workload_id,action,result)
                        VALUES(?,?,?,?,?)''', (self.clock(), row['owner_id'], workload_id,
                                            'safe_mode' if all_actions else 'deploy.kill', 'disabled'))
                    db.commit()
                    suspended += changed
            LeasedJob(self.leases, f'workload.{workload_id}').run(operation)
        return suspended

    def reconcile(self, workload_id: str) -> bool:
        def operation(guard):
            with closing(self._db()) as db:
                row = db.execute('SELECT * FROM workloads WHERE id=?', (workload_id,)).fetchone()
            if not row or not guard():
                return
            desired, template_name = row['desired'], row['template']
            observed = 'absent'
            error = None
            try:
                if desired == 'running':
                    template = self.templates[template_name]
                    refs = json.loads(row['secret_refs'])
                    if refs:
                        if self.vault is None:
                            raise WorkloadError('SECRETS_DISABLED')
                        secrets = {name: self.vault.read(row['owner_id'], reference, 'workload')
                                   for name, reference in refs.items()}
                        observed = self.runtime.ensure_secrets(row['owner_id'], workload_id,
                                                                template, secrets, row['revision'])
                    else:
                        observed = self.runtime.ensure(row['owner_id'], workload_id, template,
                                                       revision=row['revision'])
                    if not self.runtime.healthy(row['owner_id'], workload_id):
                        if row['previous_template'] in self.templates:
                            prior = self.templates[row['previous_template']]
                            if refs:
                                self.runtime.ensure_secrets(row['owner_id'], workload_id, prior,
                                                            secrets, row['revision'])
                            else:
                                self.runtime.ensure(row['owner_id'], workload_id, prior,
                                                    revision=row['revision'])
                            observed, error = 'rolled_back', 'HEALTH_FAILED'
                            template_name = prior.name
                        else:
                            self.runtime.stop(row['owner_id'], workload_id)
                            observed, error = 'failed', 'HEALTH_FAILED'
                elif desired == 'stopped':
                    self.runtime.stop(row['owner_id'], workload_id)
                    observed = 'stopped'
                else:
                    self.runtime.remove(row['owner_id'], workload_id)
                    observed = 'removed'
            except SecretError:
                self.runtime.stop(row['owner_id'], workload_id)
                observed, error = 'failed', 'SECRETS_UNAVAILABLE'
            except Exception:
                observed, error = 'error', 'RUNTIME_UNAVAILABLE'
            if not guard():
                return
            with closing(self._db()) as db:
                db.execute('BEGIN IMMEDIATE')
                updated = db.execute('''UPDATE workloads SET observed=?,template=?,updated_at=?
                    WHERE id=? AND revision=?''',
                    (observed, template_name, self.clock(), workload_id, row['revision']))
                if updated.rowcount:
                    status = 'completed' if error is None else 'failed'
                    db.execute('''UPDATE workload_jobs SET status=?,error_code=?
                        WHERE workload_id=? AND status='pending' ''', (status, error, workload_id))
                    db.execute('INSERT INTO workload_audit(at,actor_id,workload_id,action,result) VALUES(?,?,?,?,?)',
                               (self.clock(), row['owner_id'], workload_id, 'reconcile', observed))
                db.commit()

        return LeasedJob(self.leases, f'workload.{workload_id}').run(operation)

    def logs(self, actor: ActorContext, workload_id: str, limit: int = 4096) -> str:
        state = self.state(actor, workload_id)
        if type(limit) is not int or not 1 <= limit <= 65536:
            raise WorkloadError('INVALID_LIMIT')
        return self.runtime.logs(actor.account_id, state['id'], limit)[:limit]

    def metrics(self, actor: ActorContext, workload_id: str) -> dict:
        state = self.state(actor, workload_id)
        return self.runtime.metrics(actor.account_id, state['id'])

    def gc(self) -> int:
        cutoff = self.clock() - self.removed_retention_seconds
        with closing(self._db()) as db:
            rows = db.execute('''SELECT id FROM workloads WHERE desired='removed' AND observed='removed'
                AND updated_at<=?''', (cutoff,)).fetchall()
        cleaned = 0
        for candidate in rows:
            workload_id = candidate['id']
            def operation(guard):
                nonlocal cleaned
                with closing(self._db()) as db:
                    row = db.execute('SELECT * FROM workloads WHERE id=?', (workload_id,)).fetchone()
                if not row or row['desired'] != 'removed' or row['observed'] != 'removed' or row['updated_at'] > cutoff or not guard():
                    return
                self.runtime.remove_volume(row['owner_id'], workload_id)
                if not guard():
                    return
                with closing(self._db()) as db:
                    db.execute('BEGIN IMMEDIATE')
                    removed = db.execute('''DELETE FROM workloads WHERE id=? AND revision=?
                        AND desired='removed' AND observed='removed' AND updated_at<=?''',
                        (workload_id, row['revision'], cutoff))
                    if removed.rowcount:
                        db.execute('DELETE FROM workload_jobs WHERE workload_id=?', (workload_id,))
                        cleaned += 1
                    db.commit()
            LeasedJob(self.leases, f'workload.{workload_id}').run(operation)
        return cleaned

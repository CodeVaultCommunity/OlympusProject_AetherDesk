"""Snapshots verificáveis de SQLite e volumes Docker.

Backups de arquivos ativos são best-effort; o ensaio de restauração usa cargas
quiescentes. Uma política de snapshot do storage é necessária para atomicidade
de arquivos modificados durante a cópia.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import tempfile
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from apps.AetherDesk.workloads.docker_runtime import DockerWorkloadRuntime
from apps.AetherDesk.support.leases import LeaseStore
from apps.AetherDesk.support.migrations import apply_migration
from .sealed import seal_snapshot, unseal_snapshot


class BackupError(Exception):
    pass


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    resolved, resolved_root = path.resolve(), root.resolve()
    return resolved != resolved_root and resolved.is_relative_to(resolved_root)


class BackupService:
    def __init__(self, data_dir: str | Path, administration: AdministrationService,
                 runtime: DockerEnvironmentBroker, encryption_key: bytes | None = None,
                 require_encryption: bool = False):
        if encryption_key is not None and (type(encryption_key) is not bytes or len(encryption_key) != 32):
            raise BackupError('INVALID_BACKUP_KEY')
        self.data_dir = Path(data_dir)
        self.administration, self.runtime = administration, runtime
        self.encryption_key, self.require_encryption = encryption_key, require_encryption
        self._lock = threading.Lock()
        apply_migration(self.administration.db_path, 'backup.runs.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS backup_runs (
                id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
                status TEXT NOT NULL, snapshot TEXT)'''))
        self.leases = LeaseStore(self.administration.db_path)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.administration.db_path, timeout=10)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _volumes(self):
        with closing(sqlite3.connect(self.administration.identity.db_path)) as db:
            rows = db.execute('SELECT id,environment_id FROM accounts').fetchall()
        volumes = [{'kind': 'account', 'account_id': account_id,
                    'environment_id': environment_id,
                    'volume': self.runtime._names(environment_id)[1]}
                   for account_id, environment_id in rows]
        workload_db = self.data_dir / 'workloads.sqlite3'
        if workload_db.exists():
            with closing(sqlite3.connect(workload_db)) as db:
                workloads = db.execute('SELECT id,owner_id,observed FROM workloads').fetchall()
            for workload_id, owner_id, observed in workloads:
                volume = DockerWorkloadRuntime._names(workload_id)[1]
                inspected = subprocess.run(['docker', 'volume', 'inspect', '--format',
                    '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}',
                    volume], capture_output=True, text=True, timeout=30)
                if inspected.returncode:
                    if ('No such volume' in inspected.stderr and observed in ('absent', 'removed')):
                        continue  # Aplicação criada, mas ainda sem volume.
                    raise BackupError('WORKLOAD_VOLUME_UNAVAILABLE')
                if inspected.stdout.strip() != f'{owner_id}|{workload_id}':
                    raise BackupError('WORKLOAD_VOLUME_OWNERSHIP_MISMATCH')
                volumes.append({'kind': 'workload', 'account_id': owner_id,
                                'workload_id': workload_id, 'volume': volume})
        return volumes

    def run_due(self, actor: ActorContext | None = None):
        if actor:
            policy = self.administration.backup_settings(actor)
        else:
            with self._db() as db:
                row = db.execute('''SELECT enabled,frequency_hours,destination,retention_mode,
                    retention_days FROM backup_settings WHERE id=1''').fetchone()
            policy = dict(zip(('enabled', 'frequency_hours', 'destination', 'retention_mode', 'retention_days'), row))
        if not policy['enabled']:
            return None
        lease = self.leases.acquire('backup.schedule', ttl_seconds=45)
        if lease is None:
            return None
        stopped = threading.Event()
        lost = threading.Event()

        def heartbeat():
            current = lease
            while not stopped.wait(10):
                renewed = self.leases.renew(current, ttl_seconds=45)
                if renewed is None:
                    lost.set()
                    return
                current = renewed

        worker = threading.Thread(target=heartbeat, name='aetherdesk-backup-lease', daemon=True)
        worker.start()
        try:
            with self._db() as db:
                row = db.execute("SELECT finished_at FROM backup_runs WHERE status='ok' ORDER BY finished_at DESC LIMIT 1").fetchone()
            now = datetime.now(timezone.utc)
            if row and now - datetime.fromisoformat(row[0]) < timedelta(hours=policy['frequency_hours']):
                return None
            return self.run_once(Path(policy['destination']), policy['retention_mode'],
                                 policy['retention_days'],
                                 lease_guard=lambda: not lost.is_set() and self.leases.valid(lease))
        finally:
            stopped.set()
            worker.join(timeout=5)
            self.leases.release(lease)

    def run_once(self, destination: Path, retention_mode: str = 'replace',
                 retention_days: int | None = None,
                 lease_guard: Callable[[], bool] | None = None):
        if self.require_encryption and self.encryption_key is None:
            raise BackupError('BACKUP_KEY_REQUIRED')
        if retention_mode not in ('replace', 'days'):
            raise BackupError('INVALID_RETENTION')
        if not self._lock.acquire(blocking=False):
            raise BackupError('ALREADY_RUNNING')
        run_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)
        try:
            destination = destination.resolve()
            destination.mkdir(parents=True, exist_ok=True)
            pending = destination / ('.partial-' + run_id)
            pending.mkdir(mode=0o700)
        except BaseException:
            self._lock.release()
            raise
        try:
            with self._db() as db:
                db.execute('INSERT INTO backup_runs VALUES(?,?,?,?,NULL)',
                           (run_id, timestamp.isoformat(), None, 'running'))
            manifest = {'format': 2, 'created_at': timestamp.isoformat(),
                        'files': {}, 'volumes': self._volumes()}
            for name in ('identity.sqlite3', 'terminals.sqlite3', 'workloads.sqlite3',
                         'workload-secrets.sqlite3', 'ai.sqlite3', 'broker-nonces.sqlite3'):
                source = self.data_dir / name
                if not source.exists():
                    continue
                target = pending / name
                with closing(sqlite3.connect(source)) as read, closing(sqlite3.connect(target)) as write:
                    read.backup(write)
                manifest['files'][name] = _hash(target)
            for volume in manifest['volumes']:
                target = pending / (volume['volume'] + '.tar')
                with target.open('wb') as out:
                    process = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                        '--read-only', '--mount', f"type=volume,source={volume['volume']},target=/data,readonly",
                        self.runtime.image, 'tar', '-C', '/data', '-cf', '-', '.'],
                        stdout=out, stderr=subprocess.PIPE, timeout=600)
                if process.returncode:
                    raise BackupError('VOLUME_COPY_FAILED')
                manifest['files'][target.name] = _hash(target)
            (pending / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            if lease_guard is not None and not lease_guard():
                raise BackupError('LEASE_LOST')
            final = destination / ('aetherdesk-' + timestamp.strftime('%Y%m%dT%H%M%SZ') + '-' + run_id[:8])
            if self.encryption_key is not None:
                final = final.with_suffix('.adbackup')
                seal_snapshot(pending, final, self.encryption_key)
                shutil.rmtree(pending)
            else:
                pending.rename(final)
            with self._db() as db:
                db.execute("UPDATE backup_runs SET finished_at=?,status='ok',snapshot=? WHERE id=?",
                           (datetime.now(timezone.utc).isoformat(), str(final), run_id))
                self.administration.identity._audit(db, None, 'backup.run', run_id, 'ok')
            self.prune(destination, retention_mode, retention_days, current=final)
            return final
        except BaseException:
            with self._db() as db:
                db.execute("UPDATE backup_runs SET finished_at=?,status='failed' WHERE id=?",
                           (datetime.now(timezone.utc).isoformat(), run_id))
                self.administration.identity._audit(db, None, 'backup.run', run_id, 'failed')
            if _inside(pending, destination):
                shutil.rmtree(pending, ignore_errors=True)
            raise
        finally:
            self._lock.release()

    @staticmethod
    def prune(destination: Path, mode: str, days: int | None, current: Path):
        snapshots = [item for item in destination.iterdir()
                     if (item.is_dir() or item.is_file() and item.suffix == '.adbackup')
                     and item.name.startswith('aetherdesk-') and _inside(item, destination)]
        threshold = datetime.now(timezone.utc) - timedelta(days=days or 1)
        for item in snapshots:
            if item == current:
                continue
            if mode == 'replace' or (mode == 'days' and datetime.fromtimestamp(item.stat().st_mtime, timezone.utc) < threshold):
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()


def verify_snapshot(snapshot: Path, encryption_key: bytes | None = None) -> dict:
    if snapshot.is_file():
        if encryption_key is None:
            raise BackupError('BACKUP_KEY_REQUIRED')
        with tempfile.TemporaryDirectory(prefix='aetherdesk-verify-') as temp:
            return unseal_snapshot(snapshot, Path(temp) / 'snapshot', encryption_key)
    manifest = json.loads((snapshot / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') not in (1, 2):
        raise BackupError('INVALID_FORMAT')
    for name, digest in manifest['files'].items():
        if '/' in name or '\\' in name or name.startswith('.'):
            raise BackupError('INVALID_FILE_NAME')
        if _hash(snapshot / name) != digest:
            raise BackupError('HASH_MISMATCH')
    return manifest


def restore_snapshot(snapshot: Path, data_dir: Path, runtime: DockerEnvironmentBroker,
                     encryption_key: bytes | None = None):
    """Operação offline: serviço parado, destino descartável ou aprovado pelo operador."""
    if snapshot.is_file():
        if encryption_key is None:
            raise BackupError('BACKUP_KEY_REQUIRED')
        with tempfile.TemporaryDirectory(prefix='aetherdesk-restore-') as temp:
            extracted = Path(temp) / 'snapshot'
            unseal_snapshot(snapshot, extracted, encryption_key)
            return restore_snapshot(extracted, data_dir, runtime)
    manifest = verify_snapshot(snapshot)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ('identity.sqlite3', 'terminals.sqlite3', 'workloads.sqlite3',
                 'workload-secrets.sqlite3', 'ai.sqlite3', 'broker-nonces.sqlite3'):
        if name in manifest['files']:
            shutil.copy2(snapshot / name, data_dir / name)
    for volume in manifest['volumes']:
        kind = volume.get('kind', 'account')
        if kind == 'account':
            expected = runtime._names(volume['environment_id'])[1]
            labels = ['--label', f"aetherdesk.account_id={volume['account_id']}",
                      '--label', f"aetherdesk.environment_id={volume['environment_id']}"]
        elif kind == 'workload':
            expected = DockerWorkloadRuntime._names(volume['workload_id'])[1]
            with closing(sqlite3.connect(data_dir / 'workloads.sqlite3')) as db:
                row = db.execute('SELECT owner_id FROM workloads WHERE id=?',
                                 (volume['workload_id'],)).fetchone()
            if row is None or row[0] != volume['account_id']:
                raise BackupError('INVALID_WORKLOAD_OWNER')
            labels = ['--label', f"aetherdesk.owner_id={volume['account_id']}",
                      '--label', f"aetherdesk.workload_id={volume['workload_id']}"]
        else:
            raise BackupError('INVALID_VOLUME_KIND')
        if expected != volume['volume']:
            raise BackupError('INVALID_VOLUME')
        subprocess.run(['docker', 'volume', 'create', *labels, expected],
            check=True, capture_output=True)
        subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--user', '0:0', '--mount', f'type=volume,source={expected},target=/data',
            runtime.image, 'chown', '10001:10001', '/data'],
            check=True, capture_output=True, timeout=60)
        with (snapshot / (expected + '.tar')).open('rb') as archive:
            result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none', '--read-only',
                '--mount', f'type=volume,source={expected},target=/data',
                runtime.image, 'tar', '--no-same-owner', '--no-same-permissions', '-m',
                '-C', '/data', '-xf', '-'],
                stdin=archive, capture_output=True, timeout=600)
        if result.returncode:
            raise BackupError('VOLUME_RESTORE_FAILED: ' + result.stderr.decode(errors='replace')[:300])
    return manifest

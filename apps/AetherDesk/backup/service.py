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
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.runtime import DockerEnvironmentBroker


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
                 runtime: DockerEnvironmentBroker):
        self.data_dir = Path(data_dir)
        self.administration, self.runtime = administration, runtime
        self._lock = threading.Lock()
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS backup_runs (
                id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
                status TEXT NOT NULL, snapshot TEXT)''')

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
        return [{'account_id': account_id, 'environment_id': environment_id,
                 'volume': self.runtime._names(environment_id)[1]} for account_id, environment_id in rows]

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
        with self._db() as db:
            row = db.execute("SELECT finished_at FROM backup_runs WHERE status='ok' ORDER BY finished_at DESC LIMIT 1").fetchone()
        now = datetime.now(timezone.utc)
        if row and now - datetime.fromisoformat(row[0]) < timedelta(hours=policy['frequency_hours']):
            return None
        return self.run_once(Path(policy['destination']), policy['retention_mode'], policy['retention_days'])

    def run_once(self, destination: Path, retention_mode: str = 'replace', retention_days: int | None = None):
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
            manifest = {'format': 1, 'created_at': timestamp.isoformat(),
                        'files': {}, 'volumes': self._volumes()}
            for name in ('identity.sqlite3', 'terminals.sqlite3'):
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
            final = destination / ('aetherdesk-' + timestamp.strftime('%Y%m%dT%H%M%SZ') + '-' + run_id[:8])
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
                     if item.is_dir() and item.name.startswith('aetherdesk-') and _inside(item, destination)]
        threshold = datetime.now(timezone.utc) - timedelta(days=days or 1)
        for item in snapshots:
            if item == current:
                continue
            if mode == 'replace' or (mode == 'days' and datetime.fromtimestamp(item.stat().st_mtime, timezone.utc) < threshold):
                shutil.rmtree(item)


def verify_snapshot(snapshot: Path) -> dict:
    manifest = json.loads((snapshot / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1:
        raise BackupError('INVALID_FORMAT')
    for name, digest in manifest['files'].items():
        if '/' in name or '\\' in name or name.startswith('.'):
            raise BackupError('INVALID_FILE_NAME')
        if _hash(snapshot / name) != digest:
            raise BackupError('HASH_MISMATCH')
    return manifest


def restore_snapshot(snapshot: Path, data_dir: Path, runtime: DockerEnvironmentBroker):
    """Operação offline: serviço parado, destino descartável ou aprovado pelo operador."""
    manifest = verify_snapshot(snapshot)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ('identity.sqlite3', 'terminals.sqlite3'):
        if name in manifest['files']:
            shutil.copy2(snapshot / name, data_dir / name)
    for volume in manifest['volumes']:
        expected = runtime._names(volume['environment_id'])[1]
        if expected != volume['volume']:
            raise BackupError('INVALID_VOLUME')
        subprocess.run(['docker', 'volume', 'create', '--label',
            f"aetherdesk.account_id={volume['account_id']}", '--label',
            f"aetherdesk.environment_id={volume['environment_id']}", expected],
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

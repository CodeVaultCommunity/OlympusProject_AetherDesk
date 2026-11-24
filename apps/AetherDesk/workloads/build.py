"""Build de snapshot limitado com Dockerfile fixo e atestações obrigatórias.

O código do usuário nunca fornece instruções Dockerfile. O builder não aceita
contexto remoto, RUN, network, mounts, cache compartilhado ou pull implícito.
Um scanner externo obrigatório decide o gate antes de assinar o template.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import stat
import subprocess
import tarfile
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Callable, Protocol

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.migrations import apply_migration

from .service import ApprovedTemplate, WorkloadError
from .template_registry import TemplateRegistry


class ImageBuilder(Protocol):
    def build(self, owner_id: str, build_id: str, base_image: str, context: bytes) -> str: ...
    def remove(self, owner_id: str, image: str) -> None: ...


class ImageScanner(Protocol):
    def scan(self, image: str) -> dict: ...


def snapshot(root: str | Path, base_image: str, owner_id: str, build_id: str) -> tuple[bytes, dict]:
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not re.fullmatch(r'[a-zA-Z0-9_./:-]+@sha256:[0-9a-f]{64}', base_image):
        raise WorkloadError('INVALID_BUILD_CONTEXT')
    files: list[tuple[str, bytes]] = []
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in ('.git', '.aetherdesk', 'node_modules'))
        for name in [*dirs, *names]:
            path = Path(directory) / name
            if path.is_symlink():
                raise WorkloadError('BUILD_SYMLINK_DENIED')
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name.lower() in ('dockerfile', 'compose.yaml', 'docker-compose.yml') or relative.startswith('/'):
                raise WorkloadError('BUILD_INSTRUCTIONS_DENIED')
            if len(files) >= 5000:
                raise WorkloadError('BUILD_FILE_QUOTA')
            descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            try:
                details = os.fstat(descriptor)
                if not stat.S_ISREG(details.st_mode) or details.st_size > 2 * 1024 * 1024:
                    raise WorkloadError('BUILD_FILE_QUOTA')
                total += details.st_size
                if total > 32 * 1024 * 1024:
                    raise WorkloadError('BUILD_SIZE_QUOTA')
                with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                    data = stream.read(2 * 1024 * 1024 + 1)
                if len(data) != details.st_size:
                    raise WorkloadError('BUILD_CONTEXT_CHANGED')
            finally:
                os.close(descriptor)
            files.append((relative, data))
    if not files:
        raise WorkloadError('EMPTY_BUILD_CONTEXT')
    dockerfile = (f'FROM {base_image}\n'
                  f'LABEL aetherdesk.owner_id="{owner_id}" aetherdesk.build_id="{build_id}"\n'
                  'COPY --chown=10001:10001 . /app/\nUSER 10001:10001\nWORKDIR /app\n').encode()
    source = [{'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
              for name, data in files]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, data in [('Dockerfile', dockerfile), *files]:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue(), {'base': base_image, 'files': source}


class DockerImageBuilder:
    def __init__(self, timeout_seconds: int = 120):
        if not 10 <= timeout_seconds <= 600:
            raise WorkloadError('INVALID_BUILD_TIMEOUT')
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _run(args: list[str], *, data: bytes | None = None, timeout: int = 30) -> str:
        try:
            result = subprocess.run(['docker', *args], input=data, capture_output=True,
                                    timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkloadError('BUILD_UNAVAILABLE') from exc
        if result.returncode:
            # Docker stdout/stderr can contain source, registry credentials or secrets.
            raise WorkloadError('BUILD_FAILED')
        return result.stdout.decode('utf-8', 'replace').strip()

    def build(self, owner_id: str, build_id: str, base_image: str, context: bytes) -> str:
        before = self._run(['image', 'inspect', '--format', '{{json .Config.OnBuild}}', base_image])
        if before not in ('null', '[]'):
            raise WorkloadError('BASE_ONBUILD_DENIED')
        tag = 'aetherdesk-b-' + uuid.UUID(owner_id).hex + '-' + uuid.UUID(build_id).hex + ':local'
        self._run(['build', '--network', 'none', '--pull=false', '--no-cache',
                   '-t', tag, '-'], data=context,
                  timeout=self.timeout_seconds)
        image = self._run(['image', 'inspect', '--format', '{{.Id}}', tag])
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise WorkloadError('BUILD_DIGEST_INVALID')
        return image

    def remove(self, owner_id: str, image: str) -> None:
        labels = self._run(['image', 'inspect', '--format',
                            '{{index .Config.Labels "aetherdesk.owner_id"}}', image])
        if labels != owner_id:
            raise WorkloadError('OWNERSHIP_MISMATCH')
        self._run(['image', 'rm', '--force', image])


class BuildService:
    def __init__(self, db_path: str | Path, owner_root: str | Path, builder: ImageBuilder,
                 scanner: ImageScanner, signing_key: bytes,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 clock: Callable[[], float] = time.time):
        if len(signing_key) < 32:
            raise WorkloadError('INVALID_SIGNING_KEY')
        self.db_path, self.root = str(db_path), Path(owner_root).resolve(strict=True)
        self.builder, self.scanner, self.key = builder, scanner, signing_key
        self.authorize, self.session_active, self.clock = authorize, session_active, clock
        apply_migration(self.db_path, 'workloads.build.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS workload_builds (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                context_digest TEXT NOT NULL, base_image TEXT NOT NULL, status TEXT NOT NULL,
                image TEXT, manifest BLOB, sbom BLOB, provenance BLOB, scan BLOB,
                created_at REAL NOT NULL, UNIQUE(owner_id,operation_id))'''))

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def build(self, actor: ActorContext, operation_id: str, base_image: str,
              command: tuple[str, ...] = (), port: int | None = None) -> dict:
        if not self.session_active(actor):
            raise WorkloadError('SESSION_REVOKED')
        self.authorize(actor, 'workloads.build')
        try:
            operation_id = str(uuid.UUID(operation_id))
            owner_id = str(uuid.UUID(actor.account_id))
        except (TypeError, ValueError) as exc:
            raise WorkloadError('INVALID_OPERATION_ID') from exc
        if (type(command) is not tuple or len(command) > 20 or
                any(not isinstance(part, str) or not part or '\0' in part or len(part) > 1024
                    for part in command) or
                (port is not None and (type(port) is not int or not 1 <= port <= 65535))):
            raise WorkloadError('INVALID_BUILD_COMMAND')
        try:
            owner_root = (self.root / owner_id).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise WorkloadError('BUILD_CONTEXT_NOT_FOUND') from exc
        if not owner_root.is_dir() or not owner_root.is_relative_to(self.root):
            raise WorkloadError('BUILD_CONTEXT_NOT_FOUND')
        build_id = str(uuid.uuid4())
        context, provenance_data = snapshot(owner_root, base_image, owner_id, build_id)
        provenance_data['command'] = command
        provenance_data['port'] = port
        context_digest = hashlib.sha256(json.dumps(provenance_data, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM workload_builds WHERE owner_id=? AND operation_id=?',
                                  (owner_id, operation_id)).fetchone()
            if existing:
                db.commit()
                if existing['base_image'] != base_image or existing['context_digest'] != context_digest:
                    raise WorkloadError('OPERATION_CONFLICT')
                return self._result(existing)
            db.execute('''INSERT INTO workload_builds(id,owner_id,operation_id,context_digest,
                base_image,status,created_at) VALUES(?,?,?,?,?,'pending',?)''',
                (build_id, owner_id, operation_id, context_digest, base_image, self.clock()))
            db.commit()
        image = None
        try:
            image = self.builder.build(owner_id, build_id, base_image, context)
            scan_data = self.scanner.scan(image)
            if (scan_data.get('subject') != image or scan_data.get('critical') != 0 or
                    scan_data.get('high') != 0):
                raise WorkloadError('SCAN_POLICY_DENIED')
            sbom = json.dumps({'spdxVersion': 'SPDX-2.3', 'packages': provenance_data['files']},
                              sort_keys=True).encode()
            provenance = json.dumps({'subject': image, **provenance_data}, sort_keys=True).encode()
            scan = json.dumps(scan_data, sort_keys=True).encode()
            manifest = {'name': 'build_' + uuid.UUID(build_id).hex,
                        'image': image, 'sbom_sha256': hashlib.sha256(sbom).hexdigest(),
                        'provenance_sha256': hashlib.sha256(provenance).hexdigest(),
                        'scan_sha256': hashlib.sha256(scan).hexdigest(),
                        'command': list(command), 'port': port}
            canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
            manifest['signature'] = hmac.new(self.key, canonical, hashlib.sha256).hexdigest()
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
            TemplateRegistry(self.key).load(manifest_bytes, sbom, provenance, scan)
            with closing(self._db()) as db, db:
                db.execute('''UPDATE workload_builds SET status='completed',image=?,manifest=?,
                    sbom=?,provenance=?,scan=? WHERE id=?''',
                    (image, manifest_bytes, sbom, provenance, scan, build_id))
            return {'id': build_id, 'status': 'completed', 'image': image,
                    'template': TemplateRegistry(self.key).load(manifest_bytes, sbom, provenance, scan)}
        except BaseException:
            if image:
                try:
                    self.builder.remove(owner_id, image)
                except WorkloadError:
                    pass
            with closing(self._db()) as db, db:
                db.execute("UPDATE workload_builds SET status='failed' WHERE id=?", (build_id,))
            raise

    def _result(self, row: sqlite3.Row) -> dict:
        if row['status'] != 'completed':
            raise WorkloadError('BUILD_' + row['status'].upper())
        template = TemplateRegistry(self.key).load(row['manifest'], row['sbom'],
                                                   row['provenance'], row['scan'])
        return {'id': row['id'], 'status': row['status'], 'image': row['image'], 'template': template}

    def gc(self, active_images: frozenset[str], retention_seconds: int = 604800) -> int:
        if type(retention_seconds) is not int or retention_seconds < 0:
            raise WorkloadError('INVALID_RETENTION')
        cutoff = self.clock() - retention_seconds
        with closing(self._db()) as db:
            rows = db.execute('''SELECT id,owner_id,image FROM workload_builds
                WHERE status='completed' AND created_at<=?''', (cutoff,)).fetchall()
        removed = 0
        for row in rows:
            if row['image'] in active_images:
                continue
            self.builder.remove(row['owner_id'], row['image'])
            with closing(self._db()) as db, db:
                removed += db.execute('''UPDATE workload_builds SET status='expired',image=NULL,
                    manifest=NULL,sbom=NULL,provenance=NULL,scan=NULL
                    WHERE id=? AND status='completed' AND created_at<=?''',
                    (row['id'], cutoff)).rowcount
        return removed

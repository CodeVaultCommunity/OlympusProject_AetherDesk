"""Envelope AES-256-GCM para snapshots de fixture e destinos privados."""

from __future__ import annotations

import os
import re
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


MAGIC = b'AETHERDESK-SNAPSHOT\x01'
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,200}$')


class SealedBackupError(Exception):
    pass


def _key(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) != 32:
        raise SealedBackupError('INVALID_BACKUP_KEY')
    return value


class _EncryptWriter:
    def __init__(self, output, encryptor):
        self.output, self.encryptor = output, encryptor

    def write(self, value):
        self.output.write(self.encryptor.update(value))
        return len(value)

    def flush(self):
        self.output.flush()


def seal_snapshot(snapshot: Path, destination: Path, key: bytes) -> Path:
    from .service import verify_snapshot
    key = _key(key)
    snapshot, destination = Path(snapshot), Path(destination)
    manifest = verify_snapshot(snapshot)
    if destination.exists() or not destination.parent.is_dir():
        raise SealedBackupError('INVALID_BACKUP_DESTINATION')
    names = sorted([*manifest['files'], 'manifest.json'])
    if any(not _NAME.fullmatch(name) for name in names):
        raise SealedBackupError('INVALID_BACKUP_ENTRY')
    pending = destination.parent / ('.sealed-' + uuid.uuid4().hex)
    nonce = os.urandom(12)
    try:
        with pending.open('xb') as output:
            os.chmod(pending, 0o600)
            output.write(MAGIC + nonce)
            encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            with tarfile.open(fileobj=_EncryptWriter(output, encryptor), mode='w|') as archive:
                for name in names:
                    path = snapshot / name
                    if path.is_symlink() or not path.is_file():
                        raise SealedBackupError('INVALID_BACKUP_ENTRY')
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = path.stat().st_size, 0o600, 0
                    with path.open('rb') as source:
                        archive.addfile(info, source)
            output.write(encryptor.finalize() + encryptor.tag)
            output.flush()
            os.fsync(output.fileno())
        pending.replace(destination)
        return destination
    finally:
        pending.unlink(missing_ok=True)


def unseal_snapshot(source: Path, destination: Path, key: bytes) -> dict:
    from .service import verify_snapshot
    key = _key(key)
    source, destination = Path(source), Path(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise SealedBackupError('INVALID_BACKUP_DESTINATION')
    scratch = Path(tempfile.mkdtemp(prefix='.unseal-', dir=destination.parent))
    try:
        raw_tar, extracted = scratch / 'snapshot.tar', scratch / 'snapshot'
        extracted.mkdir(mode=0o700)
        with source.open('rb') as encrypted:
            if encrypted.read(len(MAGIC)) != MAGIC:
                raise SealedBackupError('INVALID_BACKUP_FORMAT')
            nonce = encrypted.read(12)
            size = source.stat().st_size
            ciphertext_size = size - len(MAGIC) - 12 - 16
            if len(nonce) != 12 or ciphertext_size < 0:
                raise SealedBackupError('INVALID_BACKUP_FORMAT')
            encrypted.seek(size - 16)
            tag = encrypted.read(16)
            encrypted.seek(len(MAGIC) + 12)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            with raw_tar.open('xb') as output:
                os.chmod(raw_tar, 0o600)
                remaining = ciphertext_size
                while remaining:
                    block = encrypted.read(min(1024 * 1024, remaining))
                    if not block:
                        raise SealedBackupError('TRUNCATED_BACKUP')
                    output.write(decryptor.update(block))
                    remaining -= len(block)
                try:
                    output.write(decryptor.finalize())
                except InvalidTag as exc:
                    raise SealedBackupError('BACKUP_AUTH_FAILED') from exc
        with tarfile.open(raw_tar, 'r:') as archive:
            members = archive.getmembers()
            if len(members) > 10000 or any(not item.isfile() or not _NAME.fullmatch(item.name)
                                           or item.size > 100 * 1024 * 1024 * 1024
                                           for item in members):
                raise SealedBackupError('INVALID_BACKUP_ENTRY')
            for member in members:
                stream = archive.extractfile(member)
                if stream is None:
                    raise SealedBackupError('INVALID_BACKUP_ENTRY')
                with (extracted / member.name).open('xb') as output, stream:
                    shutil.copyfileobj(stream, output, 1024 * 1024)
        manifest = verify_snapshot(extracted)
        raw_tar.unlink()
        extracted.replace(destination)
        return manifest
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

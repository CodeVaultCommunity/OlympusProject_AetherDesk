"""Cofre interno com criptografia autenticada e chave mestra versionada.

O chamador deve derivar owner_id de ActorContext após autorização. Nenhuma chave é
gerada nem persistida aqui: a operação fornece chaves por configuração externa.
"""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .migrations import apply_migration


class SecretError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(secret_id: str, owner_id: str, scope: str, name: str) -> bytes:
    return '\0'.join((secret_id, owner_id, scope, name)).encode()


class Keyring:
    def __init__(self, keys: dict[int, bytes], active_version: int):
        if not keys or active_version not in keys or any(
            not isinstance(version, int) or version < 1 or not isinstance(key, bytes) or len(key) != 32
            for version, key in keys.items()
        ):
            raise SecretError('INVALID_MASTER_KEY')
        self.keys = dict(keys)
        self.active_version = active_version

    def active(self) -> tuple[int, bytes]:
        return self.active_version, self.keys[self.active_version]

    def key(self, version: int) -> bytes:
        try:
            return self.keys[version]
        except KeyError as exc:
            raise SecretError('MASTER_KEY_UNAVAILABLE') from exc


class SecretVault:
    def __init__(self, db_path: str | Path, keyring: Keyring):
        self.db_path = str(db_path)
        self.keyring = keyring
        apply_migration(self.db_path, 'support.secrets.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS secrets (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, scope TEXT NOT NULL,
                name TEXT NOT NULL, key_version INTEGER NOT NULL, nonce BLOB NOT NULL,
                ciphertext BLOB NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, revoked_at TEXT,
                UNIQUE(owner_id,scope,name))'''))

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _metadata(value: sqlite3.Row) -> dict:
        return {field: value[field] for field in
                ('id', 'owner_id', 'scope', 'name', 'key_version', 'created_at', 'updated_at', 'revoked_at')}

    def store(self, owner_id: str, scope: str, name: str, value: bytes) -> dict:
        if not owner_id or not scope or not name or not isinstance(value, bytes) or len(value) > 65536:
            raise SecretError('INVALID_SECRET')
        secret_id = str(uuid.uuid4())
        version, key = self.keyring.active()
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(nonce, value, _aad(secret_id, owner_id, scope, name))
        now = _now()
        try:
            with closing(self._db()) as db, db:
                db.execute('''INSERT INTO secrets VALUES(?,?,?,?,?,?,?,?,?,NULL)''',
                           (secret_id, owner_id, scope, name, version, nonce, ciphertext, now, now))
                row = db.execute('SELECT * FROM secrets WHERE id=?', (secret_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise SecretError('CONFLICT') from exc
        return self._metadata(row)

    def read(self, owner_id: str, secret_id: str, scope: str | None = None) -> bytes:
        with closing(self._db()) as db:
            row = db.execute('''SELECT * FROM secrets WHERE id=? AND owner_id=? AND revoked_at IS NULL''',
                             (secret_id, owner_id)).fetchone()
        if row is None or (scope is not None and row['scope'] != scope):
            raise SecretError('NOT_FOUND')
        try:
            return AESGCM(self.keyring.key(row['key_version'])).decrypt(
                row['nonce'], row['ciphertext'], _aad(row['id'], row['owner_id'], row['scope'], row['name']))
        except (InvalidTag, ValueError) as exc:
            raise SecretError('SECRET_UNAVAILABLE') from exc

    def verify_restore(self) -> dict:
        """Valida todas as entradas ativas após restore sem devolver valores ou donos."""
        versions: set[int] = set()
        count = 0
        with closing(self._db()) as db, db:
            db.execute('BEGIN')
            rows = db.execute('''SELECT id,owner_id,scope,name,key_version,nonce,ciphertext
                FROM secrets WHERE revoked_at IS NULL''')
            for row in rows:
                try:
                    AESGCM(self.keyring.key(row['key_version'])).decrypt(
                        row['nonce'], row['ciphertext'],
                        _aad(row['id'], row['owner_id'], row['scope'], row['name']))
                except (InvalidTag, ValueError) as exc:
                    raise SecretError('SECRET_UNAVAILABLE') from exc
                versions.add(row['key_version'])
                count += 1
        return {'active_secrets': count, 'key_versions': sorted(versions)}

    def revoke(self, owner_id: str, secret_id: str) -> bool:
        with closing(self._db()) as db, db:
            changed = db.execute('''UPDATE secrets SET revoked_at=?,updated_at=?
                WHERE id=? AND owner_id=? AND revoked_at IS NULL''',
                (_now(), _now(), secret_id, owner_id)).rowcount
        return bool(changed)

    def rotate(self, version: int, key: bytes) -> int:
        if not isinstance(version, int) or version <= self.keyring.active_version or not isinstance(key, bytes) or len(key) != 32:
            raise SecretError('INVALID_MASTER_KEY')
        updated = 0
        with closing(self._db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT * FROM secrets WHERE revoked_at IS NULL').fetchall()
            for row in rows:
                try:
                    plaintext = AESGCM(self.keyring.key(row['key_version'])).decrypt(
                        row['nonce'], row['ciphertext'], _aad(row['id'], row['owner_id'], row['scope'], row['name']))
                except (InvalidTag, ValueError) as exc:
                    raise SecretError('SECRET_UNAVAILABLE') from exc
                nonce = secrets.token_bytes(12)
                ciphertext = AESGCM(key).encrypt(nonce, plaintext,
                                                 _aad(row['id'], row['owner_id'], row['scope'], row['name']))
                db.execute('''UPDATE secrets SET key_version=?,nonce=?,ciphertext=?,updated_at=?
                    WHERE id=?''', (version, nonce, ciphertext, _now(), row['id']))
                updated += 1
        self.keyring.keys[version] = key
        self.keyring.active_version = version
        return updated

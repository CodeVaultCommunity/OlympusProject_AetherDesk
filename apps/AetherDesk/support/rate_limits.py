"""Limites persistentes para endpoints sensíveis, sem guardar IP ou usuário em claro."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .migrations import apply_migration


class RateLimiter:
    def __init__(self, db_path: str | Path, secret: str, clock=time.time):
        if len(secret) < 32:
            raise ValueError('WEAK_RATE_LIMIT_SECRET')
        self.db_path, self.secret, self.clock = str(db_path), secret.encode(), clock
        apply_migration(self.db_path, 'support.rate_limits.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                key_hash TEXT PRIMARY KEY, attempts INTEGER NOT NULL,
                resets_at REAL NOT NULL)'''))

    def consume(self, category: str, identity: str, limit: int, window_seconds: int) -> bool:
        if not category or not identity or limit < 1 or window_seconds < 1:
            raise ValueError('INVALID_RATE_LIMIT')
        digest = hmac.new(self.secret, f'{category}\0{identity}'.encode(), hashlib.sha256).hexdigest()
        now = self.clock()
        with closing(sqlite3.connect(self.db_path, timeout=10, isolation_level=None)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT attempts,resets_at FROM rate_limits WHERE key_hash=?',
                             (digest,)).fetchone()
            if row and row[1] > now:
                if row[0] >= limit:
                    return False
                db.execute('UPDATE rate_limits SET attempts=attempts+1 WHERE key_hash=?', (digest,))
            else:
                db.execute('''INSERT INTO rate_limits(key_hash,attempts,resets_at) VALUES(?,1,?)
                    ON CONFLICT(key_hash) DO UPDATE SET attempts=1,resets_at=excluded.resets_at''',
                    (digest, now + window_seconds))
            db.execute('DELETE FROM rate_limits WHERE resets_at<=?', (now,))
            return True

"""Leases SQLite com fencing monotônico para trabalhos de processo único."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .migrations import apply_migration


@dataclass(frozen=True)
class Lease:
    name: str
    owner: str
    fence: int
    expires_at: float


class LeaseStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        apply_migration(self.db_path, 'support.leases.v1', lambda db: db.execute('''
            CREATE TABLE IF NOT EXISTS worker_leases (
                name TEXT PRIMARY KEY, owner TEXT NOT NULL, fence INTEGER NOT NULL,
                expires_at REAL NOT NULL)'''))

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def acquire(self, name: str, ttl_seconds: float = 45, *, now: float | None = None) -> Lease | None:
        if not name or ttl_seconds <= 0:
            raise ValueError('INVALID_LEASE')
        current = time.time() if now is None else now
        owner = str(uuid.uuid4())
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT fence,expires_at FROM worker_leases WHERE name=?', (name,)).fetchone()
            if row and row['expires_at'] > current:
                return None
            fence = row['fence'] + 1 if row else 1
            db.execute('''INSERT INTO worker_leases(name,owner,fence,expires_at) VALUES(?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,fence=excluded.fence,
                    expires_at=excluded.expires_at''', (name, owner, fence, current + ttl_seconds))
            return Lease(name, owner, fence, current + ttl_seconds)

    def renew(self, lease: Lease, ttl_seconds: float = 45, *, now: float | None = None) -> Lease | None:
        if ttl_seconds <= 0:
            raise ValueError('INVALID_LEASE')
        current = time.time() if now is None else now
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('''UPDATE worker_leases SET expires_at=? WHERE
                name=? AND owner=? AND fence=? AND expires_at>?''',
                (current + ttl_seconds, lease.name, lease.owner, lease.fence, current)).rowcount
        return Lease(lease.name, lease.owner, lease.fence, current + ttl_seconds) if changed else None

    def valid(self, lease: Lease, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with closing(self._connect()) as db, db:
            row = db.execute('''SELECT 1 FROM worker_leases WHERE name=? AND owner=?
                AND fence=? AND expires_at>?''',
                (lease.name, lease.owner, lease.fence, current)).fetchone()
        return row is not None

    def release(self, lease: Lease) -> bool:
        with closing(self._connect()) as db, db:
            changed = db.execute('''UPDATE worker_leases SET expires_at=0 WHERE
                name=? AND owner=? AND fence=?''',
                (lease.name, lease.owner, lease.fence)).rowcount
        return bool(changed)

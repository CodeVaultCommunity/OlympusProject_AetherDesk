"""Tombstones transacionais; a exclusão física exige um worker e política explícita."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .migrations import apply_migration


class LifecycleStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        apply_migration(self.db_path, 'support.lifecycle.v1', lambda db: db.execute('''
            CREATE TABLE lifecycle_tombstones (
                kind TEXT NOT NULL, resource_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                deleted_at REAL NOT NULL, purge_after REAL, hold INTEGER NOT NULL DEFAULT 0,
                purged_at REAL, PRIMARY KEY(kind,resource_id))'''))

    @staticmethod
    def record(db: sqlite3.Connection, kind: str, resource_id: str, owner_id: str,
               retention_seconds: int | None, *, now: float | None = None) -> None:
        if not kind or not resource_id or not owner_id or (
            retention_seconds is not None and (type(retention_seconds) is not int or retention_seconds < 0)
        ):
            raise ValueError('INVALID_LIFECYCLE_POLICY')
        existing = db.execute('''SELECT owner_id FROM lifecycle_tombstones
            WHERE kind=? AND resource_id=?''', (kind, resource_id)).fetchone()
        if existing:
            if existing[0] != owner_id:
                raise ValueError('OWNER_MISMATCH')
            return
        current = time.time() if now is None else now
        purge_after = current + retention_seconds if retention_seconds is not None else None
        db.execute('''INSERT INTO lifecycle_tombstones
            (kind,resource_id,owner_id,deleted_at,purge_after)
            VALUES(?,?,?,?,?)''', (kind, resource_id, owner_id, current, purge_after))

    def due(self, *, now: float | None = None) -> list[dict]:
        current = time.time() if now is None else now
        with closing(sqlite3.connect(self.db_path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('''SELECT * FROM lifecycle_tombstones
                WHERE purge_after IS NOT NULL AND purge_after<=? AND hold=0 AND purged_at IS NULL
                ORDER BY purge_after,kind,resource_id''', (current,))]

    def set_hold(self, kind: str, resource_id: str, held: bool) -> bool:
        with closing(sqlite3.connect(self.db_path)) as db, db:
            return bool(db.execute('''UPDATE lifecycle_tombstones SET hold=?
                WHERE kind=? AND resource_id=? AND purged_at IS NULL''',
                (int(held), kind, resource_id)).rowcount)

    def confirm_purged(self, kind: str, resource_id: str, *, now: float | None = None) -> bool:
        """Registrar somente depois que um executor externo concluiu a purga autorizada."""
        current = time.time() if now is None else now
        with closing(sqlite3.connect(self.db_path)) as db, db:
            return bool(db.execute('''UPDATE lifecycle_tombstones SET purged_at=?
                WHERE kind=? AND resource_id=? AND purge_after IS NOT NULL
                  AND purge_after<=? AND hold=0 AND purged_at IS NULL''',
                (current, kind, resource_id, current)).rowcount)

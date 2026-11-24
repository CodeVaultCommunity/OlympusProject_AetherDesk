"""Migrações pequenas e transacionais, identificadas por domínio."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path


def apply_migration(db_path: str | Path, name: str,
                    migrate: Callable[[sqlite3.Connection], None]) -> bool:
    """Aplica uma migração uma vez; a operação e seu registro são atômicos."""
    if not name or len(name) > 120:
        raise ValueError('INVALID_MIGRATION_NAME')
    db = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        if db.execute('SELECT 1 FROM schema_migrations WHERE name=?', (name,)).fetchone():
            db.commit()
            return False
        migrate(db)
        db.execute('INSERT INTO schema_migrations(name) VALUES(?)', (name,))
        db.commit()
        return True
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()

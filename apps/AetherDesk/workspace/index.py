"""Índice FTS5 privado do workspace, atualizado por eventos, sem polling."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Callable

from apps.AetherDesk.identity import ActorContext

from .files import WorkspaceError


class WorkspaceIndex:
    def __init__(self, root: str | Path, db_path: str | Path, owner_id: str,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool]):
        self.root = Path(root).resolve(strict=True)
        self.db_path = Path(db_path).resolve()
        if not self.root.is_dir() or self.db_path.is_relative_to(self.root):
            raise WorkspaceError('INVALID_INDEX_PATH')
        self.owner_id = owner_id
        self.authorize = authorize
        self.session_active = session_active
        with closing(self._db()) as db:
            db.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS workspace_fts USING fts5(
                path UNINDEXED, content, tokenize='trigram')''')

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def _check(self, actor: ActorContext) -> None:
        if actor.account_id != self.owner_id:
            raise WorkspaceError('NOT_FOUND')
        if not self.session_active(actor):
            raise WorkspaceError('SESSION_REVOKED')
        self.authorize(actor, 'files.read')

    def _read(self, path: Path) -> str | None:
        if path.is_symlink() or not path.is_file():
            return None
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                return None
            with path.open('rb') as stream:
                content = stream.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                return None
            text = content.decode('utf-8', errors='strict')
            if '\0' in text:
                return None
            return text
        except (OSError, UnicodeError):
            return None

    def rebuild(self, actor: ActorContext, cancel: threading.Event) -> dict:
        self._check(actor)
        files, total = 0, 0
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('DELETE FROM workspace_fts')
                for directory, dirs, names in os.walk(self.root, followlinks=False):
                    if cancel.is_set():
                        raise WorkspaceError('INDEX_CANCELLED')
                    dirs[:] = [name for name in dirs if name != '.git' and not (Path(directory) / name).is_symlink()]
                    for name in names:
                        if cancel.is_set():
                            raise WorkspaceError('INDEX_CANCELLED')
                        path = Path(directory) / name
                        text = self._read(path)
                        if text is None:
                            continue
                        files += 1
                        total += len(text.encode('utf-8'))
                        if files > 10000 or total > 32 * 1024 * 1024:
                            raise WorkspaceError('INDEX_BUDGET')
                        db.execute('INSERT INTO workspace_fts(path,content) VALUES(?,?)',
                                   (path.relative_to(self.root).as_posix(), text))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {'files': files, 'bytes': total}

    def apply_events(self, actor: ActorContext, events: list[dict],
                     cancel: threading.Event) -> None:
        self._check(actor)
        if len(events) > 1000 or any(event.get('kind') == 'overflow' or event.get('directory') for event in events):
            self.rebuild(actor, cancel)
            return
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                for event in events:
                    if cancel.is_set():
                        raise WorkspaceError('INDEX_CANCELLED')
                    relative = event.get('path')
                    if not isinstance(relative, str) or not relative or '..' in Path(relative).parts:
                        raise WorkspaceError('INVALID_EVENT')
                    path = (self.root / relative).resolve()
                    if not path.is_relative_to(self.root):
                        raise WorkspaceError('INVALID_EVENT')
                    db.execute('DELETE FROM workspace_fts WHERE path=?', (relative,))
                    if event.get('kind') != 'deleted':
                        text = self._read(path)
                        if text is not None:
                            db.execute('INSERT INTO workspace_fts(path,content) VALUES(?,?)',
                                       (relative, text))
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def search(self, actor: ActorContext, needle: str, max_results: int = 200) -> dict:
        self._check(actor)
        if (not isinstance(needle, str) or not 3 <= len(needle) <= 200 or
                '\0' in needle or type(max_results) is not int or not 1 <= max_results <= 200):
            raise WorkspaceError('INVALID_SEARCH')
        phrase = '"' + needle.replace('"', '""') + '"'
        matches = []
        with closing(self._db()) as db:
            try:
                rows = db.execute('SELECT path,content FROM workspace_fts WHERE workspace_fts MATCH ? LIMIT ?',
                                  (phrase, max_results + 1)).fetchall()
            except sqlite3.OperationalError as exc:
                raise WorkspaceError('INVALID_SEARCH') from exc
        for row in rows[:max_results]:
            for number, line in enumerate(row['content'].splitlines(), start=1):
                if needle.casefold() in line.casefold():
                    matches.append({'path': row['path'], 'line': number, 'preview': line[:300]})
                    break
        return {'matches': matches, 'truncated': len(rows) > max_results}

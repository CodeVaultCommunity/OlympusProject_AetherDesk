"""Contratos de árvore, leitura segura e busca limitada para workspace isolado."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.AetherDesk.identity import ActorContext


class WorkspaceError(Exception):
    pass


class WorkspaceFiles:
    def __init__(self, root: str | Path, owner_id: str,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool]):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not owner_id:
            raise WorkspaceError('INVALID_WORKSPACE')
        self.owner_id = owner_id
        self.authorize = authorize
        self.session_active = session_active

    def _check(self, actor: ActorContext, capability: str) -> None:
        if actor.account_id != self.owner_id:
            raise WorkspaceError('NOT_FOUND')
        if not self.session_active(actor):
            raise WorkspaceError('SESSION_REVOKED')
        self.authorize(actor, capability)

    def _path(self, relative: str, *, allow_root: bool = False) -> Path:
        if not isinstance(relative, str) or '\0' in relative or relative.startswith(('/', '\\')):
            raise WorkspaceError('INVALID_PATH')
        if not relative and not allow_root:
            raise WorkspaceError('INVALID_PATH')
        candidate = self.root / relative
        if '..' in Path(relative).parts:
            raise WorkspaceError('INVALID_PATH')
        current = self.root
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise WorkspaceError('INVALID_PATH')
        path = candidate.resolve()
        if not path.is_relative_to(self.root) or (path == self.root and not allow_root):
            raise WorkspaceError('INVALID_PATH')
        return path

    def list_tree(self, actor: ActorContext, relative: str = '', cursor: int = 0,
                  limit: int = 100) -> dict:
        self._check(actor, 'files.read')
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise WorkspaceError('INVALID_PAGE')
        directory = self._path(relative, allow_root=True)
        if not directory.is_dir():
            raise WorkspaceError('NOT_DIRECTORY')
        names = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
        if len(names) > 10000:
            raise WorkspaceError('TOO_MANY_ENTRIES')
        entries = []
        for path in names[cursor:cursor + limit]:
            stat = path.lstat()
            entries.append({'name': path.name, 'kind': 'link' if path.is_symlink() else
                            'directory' if path.is_dir() else 'file', 'size': stat.st_size})
        next_cursor = cursor + limit if cursor + limit < len(names) else None
        return {'entries': entries, 'next_cursor': next_cursor}

    @staticmethod
    def _revision(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def read(self, actor: ActorContext, relative: str) -> dict:
        self._check(actor, 'files.read')
        path = self._path(relative)
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError('NOT_FILE')
        size = path.stat().st_size
        if size > 2 * 1024 * 1024:
            return {'mode': 'download', 'reason': 'TOO_LARGE', 'size': size}
        with path.open('rb') as stream:
            content = stream.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            return {'mode': 'download', 'reason': 'TOO_LARGE', 'size': len(content)}
        revision = self._revision(content)
        try:
            text = content.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            return {'mode': 'download', 'reason': 'INVALID_ENCODING', 'size': size,
                    'revision': revision}
        if '\0' in text or any(ord(char) < 32 and char not in '\r\n\t\f' for char in text):
            return {'mode': 'download', 'reason': 'BINARY', 'size': size, 'revision': revision}
        crlf = text.count('\r\n')
        lf = text.count('\n') - crlf
        eol = 'mixed' if crlf and lf else 'crlf' if crlf else 'lf'
        return {'mode': 'text', 'text': text, 'revision': revision, 'encoding': 'utf-8',
                'line_endings': eol, 'size': size}

    def write(self, actor: ActorContext, relative: str, text: str, expected_revision: str) -> str:
        self._check(actor, 'files.write')
        if not isinstance(text, str) or '\0' in text or len(text.encode('utf-8')) > 2 * 1024 * 1024:
            raise WorkspaceError('INVALID_CONTENT')
        path = self._path(relative)
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError('NOT_FILE')
        if path.stat().st_size > 2 * 1024 * 1024:
            raise WorkspaceError('TOO_LARGE')
        current = path.read_bytes()
        if self._revision(current) != expected_revision:
            raise WorkspaceError('STALE_REVISION')
        content = text.encode('utf-8')
        handle, name = tempfile.mkstemp(prefix='.aetherdesk-', dir=path.parent)
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return self._revision(content)

    def search(self, actor: ActorContext, needle: str, cancel: threading.Event,
               max_results: int = 200) -> dict:
        self._check(actor, 'files.read')
        if (not isinstance(needle, str) or not 1 <= len(needle) <= 200 or
                '\0' in needle or type(max_results) is not int or not 1 <= max_results <= 200):
            raise WorkspaceError('INVALID_SEARCH')
        matches: list[dict] = []
        files, scanned = 0, 0
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            if cancel.is_set():
                raise WorkspaceError('SEARCH_CANCELLED')
            dirs[:] = sorted(name for name in dirs if not (Path(directory) / name).is_symlink() and name != '.git')
            for name in sorted(names):
                if cancel.is_set():
                    raise WorkspaceError('SEARCH_CANCELLED')
                path = Path(directory) / name
                if path.is_symlink() or not path.is_file():
                    continue
                files += 1
                if files > 10000:
                    return {'matches': matches, 'truncated': True, 'files': files, 'bytes': scanned}
                size = path.stat().st_size
                if size > 2 * 1024 * 1024:
                    continue
                if scanned + size > 32 * 1024 * 1024:
                    return {'matches': matches, 'truncated': True, 'files': files, 'bytes': scanned}
                with path.open('rb') as stream:
                    content = stream.read(2 * 1024 * 1024 + 1)
                if len(content) > 2 * 1024 * 1024:
                    continue
                scanned += len(content)
                try:
                    text = content.decode('utf-8', errors='strict')
                except UnicodeDecodeError:
                    continue
                for number, line in enumerate(text.splitlines(), start=1):
                    if needle.casefold() in line.casefold():
                        matches.append({'path': path.relative_to(self.root).as_posix(),
                                        'line': number, 'preview': line[:300]})
                        if len(matches) >= max_results:
                            return {'matches': matches, 'truncated': True, 'files': files, 'bytes': scanned}
        return {'matches': matches, 'truncated': False, 'files': files, 'bytes': scanned}

"""Eventos inotify sob a raiz do workspace, sem loop de varredura periódica."""

from __future__ import annotations

import ctypes
import os
import select
import struct
import sys
import time
from pathlib import Path

from .files import WorkspaceError


_CREATE = 0x00000100
_DELETE = 0x00000200
_MODIFY = 0x00000002
_CLOSE_WRITE = 0x00000008
_MOVED_FROM = 0x00000040
_MOVED_TO = 0x00000080
_IS_DIR = 0x40000000
_Q_OVERFLOW = 0x00004000
_IGNORED = 0x00008000
_MASK = _CREATE | _DELETE | _MODIFY | _CLOSE_WRITE | _MOVED_FROM | _MOVED_TO
_HEADER = struct.Struct('iIII')


class LinuxWatcher:
    def __init__(self, root: str | Path, max_directories: int = 2048):
        if sys.platform != 'linux':
            raise WorkspaceError('LINUX_REQUIRED')
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not 1 <= max_directories <= 8192:
            raise WorkspaceError('INVALID_WATCH')
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._libc.inotify_init1.argtypes = [ctypes.c_int]
        self._libc.inotify_init1.restype = ctypes.c_int
        self._libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._libc.inotify_add_watch.restype = ctypes.c_int
        self.fd = self._libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise WorkspaceError('WATCH_UNAVAILABLE')
        self.max_directories = max_directories
        self.directories: dict[int, Path] = {}
        try:
            for directory, dirs, _ in os.walk(self.root, followlinks=False):
                dirs[:] = [name for name in dirs if name != '.git' and not (Path(directory) / name).is_symlink()]
                self._add(Path(directory))
        except BaseException:
            self.close()
            raise

    def _add(self, directory: Path) -> None:
        path = directory.resolve()
        if not path.is_relative_to(self.root) or path.is_symlink():
            return
        if len(self.directories) >= self.max_directories:
            raise WorkspaceError('WATCH_LIMIT')
        descriptor = self._libc.inotify_add_watch(self.fd, os.fsencode(path), _MASK)
        if descriptor < 0:
            raise WorkspaceError('WATCH_UNAVAILABLE')
        self.directories[descriptor] = path

    def next_events(self, timeout: float = 10) -> list[dict]:
        if self.fd < 0:
            raise WorkspaceError('WATCH_CLOSED')
        if not 0 <= timeout <= 30:
            raise WorkspaceError('INVALID_TIMEOUT')
        started = time.monotonic()
        while True:
            remaining = max(0, timeout - (time.monotonic() - started))
            readable, _, _ = select.select((self.fd,), (), (), remaining)
            if not readable:
                return []
            try:
                buffer = os.read(self.fd, 65536)
            except BlockingIOError:
                if not remaining:
                    return []
                continue
            events = []
            offset = 0
            while offset + _HEADER.size <= len(buffer):
                wd, mask, _cookie, length = _HEADER.unpack_from(buffer, offset)
                offset += _HEADER.size
                name = buffer[offset:offset + length].split(b'\0', 1)[0]
                offset += length
                if mask & _Q_OVERFLOW:
                    events.append({'kind': 'overflow', 'path': ''})
                    continue
                directory = self.directories.get(wd)
                if mask & _IGNORED:
                    self.directories.pop(wd, None)
                if directory is None:
                    continue
                target = directory / os.fsdecode(name) if name else directory
                if target.name == '.git':
                    continue
                if target.is_symlink() or not target.resolve().is_relative_to(self.root):
                    continue
                if mask & _CREATE and mask & _IS_DIR and target.is_dir() and target.name != '.git':
                    self._add(target)
                kind = ('created' if mask & (_CREATE | _MOVED_TO) else
                        'deleted' if mask & (_DELETE | _MOVED_FROM) else
                        'changed' if mask & (_MODIFY | _CLOSE_WRITE) else None)
                if kind:
                    events.append({'kind': kind, 'path': target.relative_to(self.root).as_posix(),
                                   'directory': bool(mask & _IS_DIR)})
                if len(events) >= 1000:
                    return events
            if events:
                return events

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

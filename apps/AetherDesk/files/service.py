"""Operações de arquivo dentro do namespace Linux do ambiente pessoal.

O serviço deve ser instanciado dentro do contêiner do usuário, com root='/' e
sem mounts de outras contas. openat2 impede fuga por caminho e magic links.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import uuid
from pathlib import PurePosixPath


SYS_OPENAT2 = 437  # Linux x86_64; arquitetura de homologação W001: amd64.
SYS_RENAMEAT2 = 316
RESOLVE_NO_MAGICLINKS = 0x02
RESOLVE_IN_ROOT = 0x10
RENAME_NOREPLACE = 1


class FileError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class OpenHow(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_ulonglong), ("mode", ctypes.c_ulonglong),
                ("resolve", ctypes.c_ulonglong)]


_libc = ctypes.CDLL(None, use_errno=True) if os.name == "posix" else None


def _path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path or "\\" in path:
        raise FileError("INVALID_PATH")
    parts = PurePosixPath(path).parts
    if ".." in parts:
        raise FileError("INVALID_PATH")
    return path


def _map_error(exc: OSError) -> FileError:
    return FileError({
        errno.ENOENT: "NOT_FOUND", errno.EEXIST: "CONFLICT",
        errno.EACCES: "FORBIDDEN", errno.EPERM: "FORBIDDEN",
        errno.ELOOP: "INVALID_PATH", errno.EXDEV: "INVALID_PATH",
        errno.ENOSPC: "QUOTA", errno.ENOTDIR: "INVALID_PATH",
    }.get(exc.errno, "UNAVAILABLE"))


class LinuxFileService:
    def __init__(self, root: str = "/", max_read_bytes: int = 8 * 1024 * 1024,
                 max_list_entries: int = 10_000):
        if os.name != "posix":
            raise FileError("LINUX_REQUIRED")
        if type(max_list_entries) is not int or max_list_entries < 1:
            raise FileError("INVALID_REQUEST")
        self.root_fd = os.open(root, os.O_PATH | os.O_DIRECTORY)
        self.max_read_bytes = max_read_bytes
        self.max_list_entries = max_list_entries

    def close(self) -> None:
        os.close(self.root_fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _open(self, path: str, flags: int, mode: int = 0) -> int:
        normalized = _path(path).lstrip("/") or "."
        how = OpenHow(flags, mode, RESOLVE_IN_ROOT | RESOLVE_NO_MAGICLINKS)
        fd = _libc.syscall(SYS_OPENAT2, self.root_fd, normalized.encode(),
                           ctypes.byref(how), ctypes.sizeof(how))
        if fd < 0:
            error = ctypes.get_errno()
            raise _map_error(OSError(error, os.strerror(error)))
        return fd

    def _parent(self, path: str) -> tuple[int, str]:
        normalized = _path(path)
        if normalized == "/":
            raise FileError("INVALID_PATH")
        parent, _, name = normalized.rpartition("/")
        if not name or name in (".", ".."):
            raise FileError("INVALID_PATH")
        return self._open(parent or "/", os.O_RDONLY | os.O_DIRECTORY), name

    def metadata(self, path: str) -> dict:
        fd = self._open(path, os.O_PATH | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            return {"path": path, "kind": "link" if stat.S_ISLNK(info.st_mode) else
                    "directory" if stat.S_ISDIR(info.st_mode) else "file",
                    "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                    "revision": f"{info.st_dev:x}-{info.st_ino:x}-{info.st_mtime_ns:x}-{info.st_size:x}"}
        finally:
            os.close(fd)

    def list(self, path: str) -> list[dict]:
        fd = self._open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            result = []
            with os.scandir(fd) as entries:
                for entry in entries:
                    if len(result) >= self.max_list_entries:
                        raise FileError("TOO_LARGE")
                    info = entry.stat(follow_symlinks=False)
                    result.append({"name": entry.name,
                                   "kind": "link" if stat.S_ISLNK(info.st_mode) else
                                           "directory" if stat.S_ISDIR(info.st_mode) else "file",
                                   "size": info.st_size, "mtime_ns": info.st_mtime_ns})
            return sorted(result, key=lambda item: (item["kind"] != "directory", item["name"].casefold()))
        except OSError as exc:
            raise _map_error(exc) from exc
        finally:
            os.close(fd)

    def read(self, path: str) -> tuple[bytes, str]:
        fd = self._open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise FileError("INVALID_PATH")
            if info.st_size > self.max_read_bytes:
                raise FileError("TOO_LARGE")
            data = bytearray()
            while chunk := os.read(fd, min(65536, self.max_read_bytes + 1 - len(data))):
                data.extend(chunk)
                if len(data) > self.max_read_bytes:
                    raise FileError("TOO_LARGE")
            return bytes(data), hashlib.sha256(data).hexdigest()
        finally:
            os.close(fd)

    def write(self, path: str, data: bytes, expected_hash: str | None = None,
              replace: bool = False) -> str:
        if len(data) > self.max_read_bytes:
            raise FileError("TOO_LARGE")
        parent_fd, name = self._parent(path)
        temp = ".aether-write-" + uuid.uuid4().hex
        try:
            try:
                existing, current_hash = self.read(path)
                del existing
                if expected_hash is not None and current_hash != expected_hash:
                    raise FileError("STALE_REVISION")
                if expected_hash is None and not replace:
                    raise FileError("CONFLICT")
            except FileError as exc:
                if exc.code != "NOT_FOUND":
                    raise
                if expected_hash is not None:
                    raise FileError("STALE_REVISION") from exc
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            if expected_hash is None and not replace:
                self._rename_noreplace(parent_fd, temp, parent_fd, name)
            else:
                if expected_hash is not None and self.read(path)[1] != expected_hash:
                    raise FileError("STALE_REVISION")
                os.replace(temp, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
            return hashlib.sha256(data).hexdigest()
        except OSError as exc:
            raise _map_error(exc) from exc
        finally:
            try:
                os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)

    @staticmethod
    def _rename_noreplace(src_fd: int, src: str, dst_fd: int, dst: str) -> None:
        result = _libc.syscall(SYS_RENAMEAT2, src_fd, src.encode(), dst_fd, dst.encode(),
                               RENAME_NOREPLACE)
        if result < 0:
            error = ctypes.get_errno()
            raise _map_error(OSError(error, os.strerror(error)))

    def mkdir(self, path: str) -> None:
        parent_fd, name = self._parent(path)
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except OSError as exc:
            raise _map_error(exc) from exc
        finally:
            os.close(parent_fd)

    def move(self, source: str, destination: str) -> None:
        source, destination = _path(source), _path(destination)
        if destination == source or destination.startswith(source.rstrip("/") + "/"):
            raise FileError("INVALID_PATH")
        src_fd, src_name = self._parent(source)
        dst_fd, dst_name = self._parent(destination)
        try:
            self._rename_noreplace(src_fd, src_name, dst_fd, dst_name)
        finally:
            os.close(src_fd)
            os.close(dst_fd)

    def copy(self, source: str, destination: str) -> None:
        source, destination = _path(source), _path(destination)
        if destination == source or destination.startswith(source.rstrip("/") + "/"):
            raise FileError("INVALID_PATH")
        info = self.metadata(source)
        if info["kind"] == "directory":
            self.mkdir(destination)
            for child in self.list(source):
                self.copy(source.rstrip("/") + "/" + child["name"],
                          destination.rstrip("/") + "/" + child["name"])
        else:
            data, _ = self.read(source)
            self.write(destination, data)

    def delete(self, path: str) -> None:
        info = self.metadata(path)
        if info["kind"] == "directory":
            for child in self.list(path):
                self.delete(path.rstrip("/") + "/" + child["name"])
        parent_fd, name = self._parent(path)
        try:
            if info["kind"] == "directory":
                os.rmdir(name, dir_fd=parent_fd)
            else:
                os.unlink(name, dir_fd=parent_fd)
        except OSError as exc:
            raise _map_error(exc) from exc
        finally:
            os.close(parent_fd)

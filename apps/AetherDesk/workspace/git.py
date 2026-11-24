"""Operações Git tipadas, sem hooks, prompts, config global ou shell arbitrário."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import subprocess
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse
from urllib.request import url2pathname

if TYPE_CHECKING:
    from apps.AetherDesk.identity import ActorContext
    from .credentials import GitCredentials


class GitError(Exception):
    pass


_BRANCH = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,100}$')


class GitWorkspace:
    def __init__(self, root: str | Path, owner_id: str,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 allowed_remote_hosts: frozenset[str] = frozenset(),
                 fixture_remote_root: str | Path | None = None,
                 known_hosts_file: str | Path | None = None,
                 credentials: GitCredentials | None = None):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not owner_id:
            raise GitError('INVALID_WORKSPACE')
        git_dir = self.root / '.git'
        if not git_dir.is_dir() or not git_dir.resolve().is_relative_to(self.root):
            raise GitError('UNTRUSTED_REPOSITORY')
        self.owner_id = owner_id
        self.authorize = authorize
        self.session_active = session_active
        self.allowed_remote_hosts = allowed_remote_hosts
        self.fixture_remote_root = Path(fixture_remote_root).resolve() if fixture_remote_root else None
        self.known_hosts_file = Path(known_hosts_file).resolve(strict=True) if known_hosts_file else None
        self.credentials = credentials
        if self.known_hosts_file and (not self.known_hosts_file.is_file() or
                                      not re.fullmatch(r'[A-Za-z0-9_./:\\-]+', str(self.known_hosts_file))):
            raise GitError('INVALID_KNOWN_HOSTS')

    def _check(self, actor: ActorContext, capability: str) -> None:
        if actor.account_id != self.owner_id:
            raise GitError('NOT_FOUND')
        if not self.session_active(actor):
            raise GitError('SESSION_REVOKED')
        self.authorize(actor, capability)

    def _path(self, relative: str) -> str:
        if not isinstance(relative, str) or not relative or '\0' in relative or relative.startswith(('/', '\\')):
            raise GitError('INVALID_PATH')
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise GitError('INVALID_PATH')
        return path.relative_to(self.root).as_posix()

    @staticmethod
    def _env() -> dict[str, str]:
        allowed = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL')
        env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                    'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0',
                    'GIT_ALLOW_PROTOCOL': 'file:https:ssh', 'GIT_LFS_SKIP_SMUDGE': '1'})
        return env

    def _repo_policy(self) -> None:
        config = self.root / '.git' / 'config'
        if config.is_symlink() or not config.is_file() or config.stat().st_size > 65536:
            raise GitError('UNTRUSTED_REPOSITORY')
        try:
            contents = config.read_text(encoding='utf-8').lower()
        except (OSError, UnicodeError) as exc:
            raise GitError('UNTRUSTED_REPOSITORY') from exc
        for section in re.findall(r'^\s*\[([^]]+)\]', contents, re.MULTILINE):
            if section.split()[0] in {'filter', 'diff', 'merge', 'include', 'includeif'}:
                raise GitError('UNTRUSTED_REPOSITORY')
        if re.search(r'^\s*(?:sshcommand|hookspath|fsmonitor)\s*=', contents, re.MULTILINE):
            raise GitError('UNTRUSTED_REPOSITORY')

    def _run(self, *args: str, timeout: int = 20, check: bool = True,
             extra_env: dict[str, str] | None = None,
             cancel: threading.Event | None = None) -> str:
        self._repo_policy()
        command = ['git', '-C', str(self.root), '-c', 'core.hooksPath=' + os.devnull,
                   '-c', 'core.fsmonitor=false', '-c', 'credential.helper=',
                   '-c', 'protocol.ext.allow=never', *args]
        environment = self._env()
        if self.known_hosts_file:
            environment['GIT_SSH_COMMAND'] = ('ssh -oBatchMode=yes -oStrictHostKeyChecking=yes '
                '-oUserKnownHostsFile=' + self.known_hosts_file.as_posix())
        if extra_env:
            environment.update(extra_env)
        if cancel and cancel.is_set():
            raise GitError('GIT_CANCELLED')
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=environment)
            stdout_data, stderr_data = bytearray(), bytearray()
            overflow = threading.Event()

            def drain(stream, target: bytearray, limit: int) -> None:
                while chunk := stream.read(65536):
                    if len(target) + len(chunk) > limit:
                        overflow.set()
                        try:
                            process.kill()
                        except OSError:
                            pass
                        return
                    target.extend(chunk)

            readers = [threading.Thread(target=drain, args=(process.stdout, stdout_data,
                       2 * 1024 * 1024), daemon=True),
                       threading.Thread(target=drain, args=(process.stderr, stderr_data,
                       65536), daemon=True)]
            for reader in readers:
                reader.start()
            deadline = time.monotonic() + timeout
            outcome = None
            while process.poll() is None:
                if cancel and cancel.is_set():
                    process.kill()
                    outcome = 'GIT_CANCELLED'
                    break
                if overflow.is_set():
                    outcome = 'GIT_OUTPUT_LIMIT'
                    break
                if time.monotonic() >= deadline:
                    process.kill()
                    outcome = 'GIT_TIMEOUT'
                    break
                time.sleep(.05)
            process.wait()
            for reader in readers:
                reader.join(timeout=1)
            if any(reader.is_alive() for reader in readers):
                raise GitError(outcome or 'GIT_UNAVAILABLE')
            process.stdout.close()
            process.stderr.close()
            if overflow.is_set():
                raise GitError('GIT_OUTPUT_LIMIT')
            if outcome:
                raise GitError(outcome)
        except OSError as exc:
            raise GitError('GIT_UNAVAILABLE') from exc
        try:
            stdout = stdout_data.decode('utf-8', errors='strict')
            stderr = stderr_data.decode('utf-8', errors='replace')
        except UnicodeDecodeError as exc:
            raise GitError('GIT_PROTOCOL') from exc
        if process.returncode and check:
            stderr = stderr.lower()
            if 'conflict' in stderr or 'not possible to fast-forward' in stderr:
                raise GitError('GIT_CONFLICT')
            if 'authentication failed' in stderr or 'could not read username' in stderr or 'permission denied' in stderr:
                raise GitError('AUTH_REQUIRED')
            raise GitError('GIT_FAILED')
        return stdout

    def status(self, actor: ActorContext) -> list[dict]:
        self._check(actor, 'git.read')
        raw = self._run('status', '--porcelain=v1', '-z', '--untracked-files=normal')
        entries = raw.split('\0')
        result = []
        index = 0
        while index < len(entries) and entries[index]:
            item = entries[index]
            if len(item) < 4:
                raise GitError('GIT_PROTOCOL')
            code, path = item[:2], item[3:]
            original = None
            if code[0] in 'RC' or code[1] in 'RC':
                index += 1
                original = entries[index]
            result.append({'path': path, 'code': code, 'original': original})
            if len(result) > 10000:
                raise GitError('GIT_OUTPUT_LIMIT')
            index += 1
        return result

    def diff(self, actor: ActorContext, relative: str | None = None, staged: bool = False) -> str:
        self._check(actor, 'git.read')
        arguments = ['diff', '--no-ext-diff', '--no-textconv', '--unified=3']
        if staged:
            arguments.append('--cached')
        if relative:
            arguments.extend(('--', self._path(relative)))
        return self._run(*arguments)

    def stage(self, actor: ActorContext, paths: list[str]) -> None:
        self._check(actor, 'git.write')
        if not paths or len(paths) > 100:
            raise GitError('INVALID_PATHS')
        self._run('add', '--', *(self._path(path) for path in paths))

    def unstage(self, actor: ActorContext, paths: list[str]) -> None:
        self._check(actor, 'git.write')
        if not paths or len(paths) > 100:
            raise GitError('INVALID_PATHS')
        self._run('reset', '-q', 'HEAD', '--', *(self._path(path) for path in paths))

    def commit(self, actor: ActorContext, message: str, author_name: str,
               author_email: str) -> str:
        self._check(actor, 'git.write')
        if (not isinstance(message, str) or not 1 <= len(message) <= 2000 or '\0' in message or
                not isinstance(author_name, str) or not 1 <= len(author_name) <= 100 or '\n' in author_name or
                not isinstance(author_email, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+', author_email)):
            raise GitError('INVALID_COMMIT')
        env = {'GIT_AUTHOR_NAME': author_name, 'GIT_AUTHOR_EMAIL': author_email,
               'GIT_COMMITTER_NAME': author_name, 'GIT_COMMITTER_EMAIL': author_email}
        self._run('commit', '--no-verify', '-m', message, extra_env=env, timeout=60)
        return self._run('rev-parse', 'HEAD').strip()

    def branches(self, actor: ActorContext) -> list[str]:
        self._check(actor, 'git.read')
        return self._run('for-each-ref', '--format=%(refname:short)', 'refs/heads').splitlines()[:200]

    def create_branch(self, actor: ActorContext, name: str) -> None:
        self._check(actor, 'git.write')
        if not isinstance(name, str) or not _BRANCH.fullmatch(name) or name.endswith(('.', '/', '.lock')) or '..' in name:
            raise GitError('INVALID_BRANCH')
        self._run('branch', name)

    def history(self, actor: ActorContext, limit: int = 30) -> list[dict]:
        self._check(actor, 'git.read')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise GitError('INVALID_LIMIT')
        lines = self._run('log', f'-{limit}', '--format=%H%x1f%an%x1f%at%x1f%s').splitlines()
        return [dict(zip(('hash', 'author', 'timestamp', 'subject'), line.split('\x1f', 3))) for line in lines]

    def _remote(self, name: str) -> None:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name):
            raise GitError('INVALID_REMOTE')
        url = self._run('remote', 'get-url', name).strip()
        if self.fixture_remote_root and Path(url).is_absolute():
            if Path(url).resolve().is_relative_to(self.fixture_remote_root):
                return
        parsed = urlparse(url)
        if parsed.scheme == 'file' and self.fixture_remote_root:
            target = Path(url2pathname(parsed.path)).resolve()
            if target.is_relative_to(self.fixture_remote_root):
                return
        if not parsed.scheme and self.fixture_remote_root:
            target = Path(url).resolve()
            if target.is_relative_to(self.fixture_remote_root):
                return
        if parsed.scheme == 'ssh' and parsed.hostname in self.allowed_remote_hosts:
            if not self.known_hosts_file:
                raise GitError('HOST_KEY_UNVERIFIED')
            return
        if parsed.scheme == 'https' and parsed.hostname in self.allowed_remote_hosts:
            return
        raise GitError('REMOTE_DENIED')

    def pull(self, actor: ActorContext, remote: str = 'origin', branch: str = 'main',
             cancel: threading.Event | None = None) -> None:
        self._check(actor, 'git.remote')
        self._remote(remote)
        if not _BRANCH.fullmatch(branch):
            raise GitError('INVALID_BRANCH')
        context = self.credentials.environment(actor, remote) if self.credentials else nullcontext({})
        with context as environment:
            self._run('pull', '--ff-only', '--no-rebase', remote, branch, timeout=90,
                      extra_env=environment, cancel=cancel)

    def push(self, actor: ActorContext, remote: str = 'origin', branch: str = 'main',
             cancel: threading.Event | None = None) -> None:
        self._check(actor, 'git.remote')
        self._remote(remote)
        if not _BRANCH.fullmatch(branch):
            raise GitError('INVALID_BRANCH')
        context = self.credentials.environment(actor, remote) if self.credentials else nullcontext({})
        with context as environment:
            self._run('push', remote, branch, timeout=90, extra_env=environment, cancel=cancel)

    def discard_preview(self, actor: ActorContext, relative: str) -> dict:
        self._check(actor, 'git.write')
        path = self._path(relative)
        diff = self.diff(actor, relative)
        head = self._run('rev-parse', 'HEAD').strip()
        digest = hashlib.sha256((head + '\0' + path + '\0' + diff).encode()).hexdigest()
        return {'path': path, 'diff': diff, 'preview_token': digest}

    def discard(self, actor: ActorContext, relative: str, preview_token: str) -> None:
        self._check(actor, 'git.write')
        preview = self.discard_preview(actor, relative)
        if not isinstance(preview_token, str) or not hmac.compare_digest(preview['preview_token'], preview_token):
            raise GitError('STALE_PREVIEW')
        self._run('restore', '--worktree', '--', preview['path'])

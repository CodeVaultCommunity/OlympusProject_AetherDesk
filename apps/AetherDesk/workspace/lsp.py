"""Contrato opcional de LSP: somente requests tipados para o broker isolado.

O processo da API nunca lança servidor de linguagem ou formatter. A implantação
deve fornecer um runner que imponha isolamento de workspace, UID, quotas e egress.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from apps.AetherDesk.identity import ActorContext


class LspError(Exception):
    pass


@dataclass(frozen=True)
class LanguageServer:
    language: str
    image_digest: str
    max_memory_mb: int = 256
    timeout_seconds: int = 30


class IsolatedLanguageRunner(Protocol):
    def request(self, owner_id: str, workspace_id: str, server: LanguageServer,
                relative_path: str, action: str, content: str) -> dict: ...


class LspService:
    def __init__(self, root: str | Path, owner_id: str, workspace_id: str,
                 authorize: Callable[[ActorContext, str], None],
                 session_active: Callable[[ActorContext], bool],
                 runner: IsolatedLanguageRunner | None = None,
                 servers: dict[str, LanguageServer] | None = None,
                 enabled_languages: frozenset[str] = frozenset()):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not owner_id or not workspace_id:
            raise LspError('INVALID_WORKSPACE')
        self.owner_id, self.workspace_id = owner_id, workspace_id
        self.authorize, self.session_active = authorize, session_active
        self.runner, self.servers = runner, dict(servers or {})
        self.enabled_languages = enabled_languages
        for language, server in self.servers.items():
            if (language != server.language or not server.image_digest.startswith('sha256:') or
                    len(server.image_digest) != 71 or
                    any(char not in '0123456789abcdef' for char in server.image_digest[7:]) or
                    not 64 <= server.max_memory_mb <= 1024 or
                    not 1 <= server.timeout_seconds <= 60):
                raise LspError('UNAPPROVED_SERVER')

    def request(self, actor: ActorContext, language: str, relative_path: str,
                action: str, content: str) -> dict:
        if actor.account_id != self.owner_id:
            raise LspError('NOT_FOUND')
        if not self.session_active(actor):
            raise LspError('SESSION_REVOKED')
        self.authorize(actor, 'workspace.lsp')
        if language not in self.enabled_languages or language not in self.servers or self.runner is None:
            raise LspError('LSP_DISABLED')
        if action not in ('diagnostics', 'format'):
            raise LspError('INVALID_ACTION')
        if not isinstance(content, str) or len(content.encode('utf-8')) > 1024 * 1024:
            raise LspError('CONTENT_LIMIT')
        if not isinstance(relative_path, str) or not relative_path or '\0' in relative_path:
            raise LspError('INVALID_PATH')
        candidate = self.root / relative_path
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(self.root) or candidate.resolve() == self.root:
            raise LspError('INVALID_PATH')
        for parent in candidate.parents:
            if parent == self.root:
                break
            if parent.is_symlink():
                raise LspError('INVALID_PATH')
        # O runner recebe somente caminho relativo e texto, jamais um comando.
        return self.runner.request(self.owner_id, self.workspace_id, self.servers[language],
                                   candidate.relative_to(self.root).as_posix(), action, content)

"""Token Git por referência ao cofre; helper readonly, sem token em arquivo/argv."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.secrets import SecretVault

from .git import GitError


class GitCredentials:
    def __init__(self, vault: SecretVault, refs_by_remote: dict[str, str],
                 helper_path: str | Path = '/usr/local/bin/aetherdesk-git-askpass'):
        self.vault = vault
        self.refs_by_remote = dict(refs_by_remote)
        self.helper_path = Path(helper_path)

    @contextmanager
    def environment(self, actor: ActorContext, remote: str):
        if sys.platform != 'linux':
            raise GitError('LINUX_REQUIRED')
        reference = self.refs_by_remote.get(remote)
        if reference is None:
            yield {}
            return
        try:
            token = self.vault.read(actor.account_id, reference, 'git').decode('utf-8', errors='strict')
        except Exception as exc:
            raise GitError('CREDENTIAL_UNAVAILABLE') from exc
        if not token or '\0' in token or '\n' in token or len(token) > 8192:
            raise GitError('CREDENTIAL_UNAVAILABLE')
        if not self.helper_path.is_absolute() or not self.helper_path.is_file() or not os.access(self.helper_path, os.X_OK):
            raise GitError('CREDENTIAL_UNAVAILABLE')
        yield {'GIT_ASKPASS': str(self.helper_path),
               'AETHERDESK_GIT_TOKEN': token}

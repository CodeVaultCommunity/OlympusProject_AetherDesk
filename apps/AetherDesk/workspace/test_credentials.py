import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.secrets import Keyring, SecretVault
from .credentials import GitCredentials
from .git import GitError


@unittest.skipUnless(sys.platform == 'linux', 'askpass privado requer Linux')
class GitCredentialTests(unittest.TestCase):
    def test_reference_is_resolved_only_for_remote_and_never_written_to_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            vault = SecretVault(path / 'secrets.sqlite3', Keyring({1: b'a' * 32}, 1))
            metadata = vault.store(actor.account_id, 'git', 'origin', b'fixture-token-not-in-file')
            adapter = GitCredentials(vault, {'origin': metadata['id']})
            with adapter.environment(actor, 'origin') as environment:
                helper = Path(environment['GIT_ASKPASS'])
                self.assertNotIn('fixture-token-not-in-file', helper.read_text())
                result = subprocess.run(['git', 'credential', 'fill'],
                    input='protocol=https\nhost=example.test\n\n',
                    env={**os.environ, **environment, 'GIT_CONFIG_NOSYSTEM': '1',
                         'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0'},
                    check=False, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('username=oauth2', result.stdout)
                self.assertIn('password=fixture-token-not-in-file', result.stdout)
            vault.revoke(actor.account_id, metadata['id'])
            with self.assertRaisesRegex(GitError, 'CREDENTIAL_UNAVAILABLE'):
                with adapter.environment(actor, 'origin'):
                    pass


if __name__ == '__main__':
    unittest.main()

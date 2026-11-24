import subprocess
import tempfile
import threading
import time
import unittest
import uuid
import sys
from unittest.mock import patch
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from .git import GitError, GitWorkspace


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class GitWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'workspace'
        self.root.mkdir()
        git(self.root, 'init', '-b', 'main')
        self.actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.other = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.capabilities = []
        self.service = GitWorkspace(self.root, self.actor.account_id,
            lambda _actor, cap: self.capabilities.append(cap), lambda _actor: True,
            fixture_remote_root=self.base)

    def test_local_status_stage_commit_diff_branch_and_discard_preview(self):
        (self.root / 'a.txt').write_text('one\n', encoding='utf-8')
        self.assertEqual(self.service.status(self.actor)[0]['code'], '??')
        self.service.stage(self.actor, ['a.txt'])
        commit = self.service.commit(self.actor, 'Initial', 'Fixture', 'fixture@example.test')
        self.assertEqual(len(commit), 40)
        self.assertEqual(self.service.status(self.actor), [])
        (self.root / 'a.txt').write_text('two\n', encoding='utf-8')
        self.assertIn('-one', self.service.diff(self.actor, 'a.txt'))
        preview = self.service.discard_preview(self.actor, 'a.txt')
        (self.root / 'a.txt').write_text('three\n', encoding='utf-8')
        with self.assertRaisesRegex(GitError, 'STALE_PREVIEW'):
            self.service.discard(self.actor, 'a.txt', preview['preview_token'])
        self.service.discard(self.actor, 'a.txt', self.service.discard_preview(self.actor, 'a.txt')['preview_token'])
        self.assertEqual((self.root / 'a.txt').read_text(encoding='utf-8'), 'one\n')
        self.service.create_branch(self.actor, 'feature/test')
        self.assertIn('feature/test', self.service.branches(self.actor))
        self.assertEqual(self.service.history(self.actor)[0]['hash'], commit)
        self.assertIn('git.write', self.capabilities)

    def test_owner_path_and_untrusted_config_are_denied(self):
        (self.root / 'a.txt').write_text('safe\n', encoding='utf-8')
        with self.assertRaisesRegex(GitError, 'NOT_FOUND'):
            self.service.status(self.other)
        with self.assertRaisesRegex(GitError, 'INVALID_PATH'):
            self.service.stage(self.actor, ['../escape'])
        with self.assertRaisesRegex(GitError, 'INVALID_BRANCH'):
            self.service.create_branch(self.actor, '--exec=evil')
        with (self.root / '.git' / 'config').open('a', encoding='utf-8') as stream:
            stream.write('\n[filter "evil"]\n clean = echo unsafe\n')
        with self.assertRaisesRegex(GitError, 'UNTRUSTED_REPOSITORY'):
            self.service.stage(self.actor, ['a.txt'])

    def test_remote_fixture_works_but_unknown_host_is_denied(self):
        (self.root / 'a.txt').write_text('one\n', encoding='utf-8')
        self.service.stage(self.actor, ['a.txt'])
        self.service.commit(self.actor, 'Initial', 'Fixture', 'fixture@example.test')
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        git(self.root, 'remote', 'add', 'origin', str(remote))
        self.service.push(self.actor, 'origin', 'main')
        self.assertEqual(git(remote, 'rev-parse', 'refs/heads/main'), git(self.root, 'rev-parse', 'HEAD'))
        self.service.pull(self.actor, 'origin', 'main')
        git(self.root, 'remote', 'set-url', 'origin', 'ssh://unknown.example/repo.git')
        with self.assertRaisesRegex(GitError, 'REMOTE_DENIED'):
            self.service.push(self.actor, 'origin', 'main')

    def test_diverged_remote_reports_conflict_without_merging(self):
        (self.root / 'a.txt').write_text('base\n', encoding='utf-8')
        self.service.stage(self.actor, ['a.txt'])
        self.service.commit(self.actor, 'Base', 'Fixture', 'fixture@example.test')
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        git(self.root, 'remote', 'add', 'origin', str(remote))
        self.service.push(self.actor, 'origin', 'main')
        git(remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        other = self.base / 'other'
        subprocess.run(['git', 'clone', str(remote), str(other)], check=True, capture_output=True)
        (self.root / 'a.txt').write_text('local\n', encoding='utf-8')
        self.service.stage(self.actor, ['a.txt'])
        local_head = self.service.commit(self.actor, 'Local', 'Fixture', 'fixture@example.test')
        (other / 'a.txt').write_text('remote\n', encoding='utf-8')
        git(other, 'add', 'a.txt')
        git(other, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-m', 'Remote')
        git(other, 'push', 'origin', 'main')
        with self.assertRaisesRegex(GitError, 'GIT_CONFLICT'):
            self.service.pull(self.actor, 'origin', 'main')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), local_head)

    def test_ssh_allowed_host_without_known_key_is_explicitly_denied(self):
        git(self.root, 'remote', 'add', 'origin', 'ssh://git.example.test/repo.git')
        service = GitWorkspace(self.root, self.actor.account_id, lambda *_: None,
            lambda _actor: True, allowed_remote_hosts=frozenset({'git.example.test'}))
        with self.assertRaisesRegex(GitError, 'HOST_KEY_UNVERIFIED'):
            service.pull(self.actor)

    @unittest.skipUnless(sys.platform == 'linux', 'subprocesso bloqueado da fixture Unix')
    def test_git_subprocess_can_be_cancelled_while_in_flight(self):
        cancel = threading.Event()
        error = []
        original = subprocess.Popen
        with patch('apps.AetherDesk.workspace.git.subprocess.Popen',
                   side_effect=lambda _command, **options: original(['/bin/sleep', '3'], **options)):
            worker = threading.Thread(target=lambda: self._capture_git(cancel, error))
            worker.start()
            time.sleep(.4)
            cancel.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(error, ['GIT_CANCELLED'])

    def _capture_git(self, cancel, error):
        try:
            self.service._run('status', cancel=cancel)
        except GitError as exc:
            error.append(str(exc))

    def test_git_output_is_bounded_while_process_is_running(self):
        original = subprocess.Popen
        with patch('apps.AetherDesk.workspace.git.subprocess.Popen',
                   side_effect=lambda _command, **options: original(
                       [sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"x"*3000000)'],
                       **options)):
            with self.assertRaisesRegex(GitError, 'GIT_OUTPUT_LIMIT'):
                self.service._run('status')


if __name__ == '__main__':
    unittest.main()

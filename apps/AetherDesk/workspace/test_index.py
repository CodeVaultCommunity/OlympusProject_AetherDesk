import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from .files import WorkspaceError
from .index import WorkspaceIndex


class IndexTests(unittest.TestCase):
    def test_rebuild_event_update_owner_and_cancel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'workspace'; root.mkdir()
            (root / 'a.txt').write_text('old needle\n', encoding='utf-8')
            owner = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            other = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            index = WorkspaceIndex(root, Path(directory) / 'index.sqlite3', owner.account_id,
                                   lambda _actor, _cap: None, lambda _actor: True)
            index.rebuild(owner, threading.Event())
            self.assertEqual(index.search(owner, 'needle')['matches'][0]['path'], 'a.txt')
            (root / 'a.txt').write_text('new content\n', encoding='utf-8')
            index.apply_events(owner, [{'kind': 'changed', 'path': 'a.txt', 'directory': False}], threading.Event())
            self.assertEqual(index.search(owner, 'needle')['matches'], [])
            self.assertEqual(index.search(owner, 'content')['matches'][0]['line'], 1)
            with self.assertRaisesRegex(WorkspaceError, 'NOT_FOUND'):
                index.search(other, 'content')
            cancelled = threading.Event(); cancelled.set()
            with self.assertRaisesRegex(WorkspaceError, 'INDEX_CANCELLED'):
                index.rebuild(owner, cancelled)
            self.assertEqual(index.search(owner, 'content')['matches'][0]['path'], 'a.txt')


if __name__ == '__main__':
    unittest.main()

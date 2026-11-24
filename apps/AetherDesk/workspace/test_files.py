import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from .files import WorkspaceError, WorkspaceFiles


class WorkspaceFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        self.actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.other = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.service = WorkspaceFiles(self.root, self.actor.account_id,
            lambda _actor, _cap: None, lambda _actor: True)

    def test_text_revision_encoding_binary_and_line_endings(self):
        path = self.root / 'a.txt'
        path.write_bytes(b'one\r\ntwo\r\n')
        current = self.service.read(self.actor, 'a.txt')
        self.assertEqual(current['line_endings'], 'crlf')
        self.assertEqual(current['text'], 'one\r\ntwo\r\n')
        new_revision = self.service.write(self.actor, 'a.txt', 'three\r\nfour\r\n', current['revision'])
        self.assertEqual(path.read_bytes(), b'three\r\nfour\r\n')
        with self.assertRaisesRegex(WorkspaceError, 'STALE_REVISION'):
            self.service.write(self.actor, 'a.txt', 'lost', current['revision'])
        self.assertEqual(self.service.read(self.actor, 'a.txt')['revision'], new_revision)
        (self.root / 'binary').write_bytes(b'\0\1\2')
        self.assertEqual(self.service.read(self.actor, 'binary')['reason'], 'BINARY')
        (self.root / 'invalid').write_bytes(b'\xff\xfe')
        self.assertEqual(self.service.read(self.actor, 'invalid')['reason'], 'INVALID_ENCODING')
        (self.root / 'large').write_bytes(b'a' * (2 * 1024 * 1024 + 1))
        self.assertEqual(self.service.read(self.actor, 'large')['mode'], 'download')

    def test_owner_symlink_escape_paging_and_bounded_search(self):
        (self.root / 'a.txt').write_text('needle first\n', encoding='utf-8')
        (self.root / 'b.txt').write_text('needle second\n', encoding='utf-8')
        (self.root / 'c.txt').write_text('third\n', encoding='utf-8')
        page = self.service.list_tree(self.actor, limit=2)
        self.assertEqual(len(page['entries']), 2)
        self.assertIsNotNone(page['next_cursor'])
        self.assertEqual(len(self.service.list_tree(self.actor, cursor=page['next_cursor'])['entries']), 1)
        with self.assertRaisesRegex(WorkspaceError, 'NOT_FOUND'):
            self.service.list_tree(self.other)
        with self.assertRaisesRegex(WorkspaceError, 'INVALID_PATH'):
            self.service.read(self.actor, '../outside')
        outside = Path(self.temp.name) / 'outside'
        outside.write_text('secret', encoding='utf-8')
        try:
            (self.root / 'link').symlink_to(outside)
        except OSError:
            pass  # Windows sem privilégio de symlink; cenário coberto na fixture Linux.
        else:
            with self.assertRaisesRegex(WorkspaceError, 'INVALID_PATH'):
                self.service.read(self.actor, 'link')
        result = self.service.search(self.actor, 'needle', threading.Event(), max_results=1)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['matches'][0]['path'], 'a.txt')
        cancelled = threading.Event(); cancelled.set()
        with self.assertRaisesRegex(WorkspaceError, 'SEARCH_CANCELLED'):
            self.service.search(self.actor, 'needle', cancelled)


if __name__ == '__main__':
    unittest.main()

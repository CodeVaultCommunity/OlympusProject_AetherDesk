import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from .lifecycle import LifecycleStore


class LifecycleTests(unittest.TestCase):
    def test_tombstone_is_idempotent_and_retention_requires_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lifecycle.sqlite3'
            store = LifecycleStore(path)
            with closing(sqlite3.connect(path)) as db, db:
                store.record(db, 'account', 'a', 'a', None, now=100)
                store.record(db, 'account', 'a', 'a', 0, now=200)
                store.record(db, 'workload', 'w', 'a', 3600, now=100)
                with self.assertRaisesRegex(ValueError, 'OWNER_MISMATCH'):
                    store.record(db, 'workload', 'w', 'other', 3600, now=100)
            self.assertEqual(store.due(now=3700)[0]['resource_id'], 'w')
            self.assertEqual(len(store.due(now=10_000)), 1)
            self.assertTrue(store.set_hold('workload', 'w', True))
            self.assertEqual(store.due(now=10_000), [])
            self.assertTrue(store.set_hold('workload', 'w', False))
            self.assertEqual(len(store.due(now=10_000)), 1)
            self.assertFalse(store.confirm_purged('account', 'a', now=10_000))
            self.assertTrue(store.confirm_purged('workload', 'w', now=10_000))
            self.assertEqual(store.due(now=10_000), [])


if __name__ == '__main__':
    unittest.main()

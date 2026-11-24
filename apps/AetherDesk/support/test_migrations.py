import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from .migrations import apply_migration


class MigrationTests(unittest.TestCase):
    def test_snapshot_restore_and_forward_recovery_preserve_fixture_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.sqlite3'
            snapshot = Path(directory) / 'before-v2.sqlite3'
            self.assertTrue(apply_migration(path, 'fixture.v1',
                lambda db: db.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT NOT NULL)')))
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("INSERT INTO records(value) VALUES('kept')")
                db.commit()
                with closing(sqlite3.connect(snapshot)) as backup:
                    db.backup(backup)

            def version_two(db):
                db.execute("ALTER TABLE records ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'")

            self.assertTrue(apply_migration(path, 'fixture.v2', version_two))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT value,status FROM records').fetchone(),
                                 ('kept', 'ready'))
            with closing(sqlite3.connect(snapshot)) as backup, closing(sqlite3.connect(path)) as db:
                backup.backup(db)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT value FROM records').fetchone(), ('kept',))
                self.assertIsNone(db.execute(
                    "SELECT 1 FROM schema_migrations WHERE name='fixture.v2'").fetchone())
            self.assertTrue(apply_migration(path, 'fixture.v2', version_two))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT value,status FROM records').fetchone(),
                                 ('kept', 'ready'))

    def test_failed_migration_rolls_back_schema_and_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite3'

            def fail(db):
                db.execute('CREATE TABLE temporary_data(id INTEGER)')
                raise RuntimeError('fixture failure')

            with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                apply_migration(path, 'fixture.v1', fail)
            with closing(sqlite3.connect(path)) as db:
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='temporary_data'").fetchone())
            self.assertTrue(apply_migration(path, 'fixture.v1',
                                            lambda db: db.execute('CREATE TABLE temporary_data(id INTEGER)')))
            self.assertFalse(apply_migration(path, 'fixture.v1',
                                             lambda _db: self.fail('migration ran twice')))


if __name__ == '__main__':
    unittest.main()

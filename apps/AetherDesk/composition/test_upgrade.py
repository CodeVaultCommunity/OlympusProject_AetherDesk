"""Upgrade e restauração de uma fixture com os schemas do release v1."""

import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from argon2 import PasswordHasher

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.backup.service import BackupService
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.terminal.service import TerminalService


class UpgradeTests(unittest.TestCase):
    def test_legacy_account_desktop_terminal_and_backup_survive_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'legacy'
            legacy.mkdir()
            account_id, environment_id, terminal_id = (str(uuid.uuid4()) for _ in range(3))
            desktop = {'windows': [], 'activeId': None, 'theme': 'light'}
            identity_sql = Path(__file__).parents[1] / 'identity' / 'migrations'
            with closing(sqlite3.connect(legacy / 'identity.sqlite3')) as db, db:
                db.executescript((identity_sql / '001_initial.sql').read_text(encoding='utf-8'))
                db.executescript((identity_sql / '002_session_expiry.sql').read_text(encoding='utf-8'))
                db.execute('PRAGMA user_version=2')
                db.execute('''INSERT INTO accounts
                    (id,username,password_hash,role,state,environment_id,
                     permissions_version,revision,created_at)
                    VALUES(?,?,?,?,?,?,1,1,?)''',
                    (account_id, 'legacyadmin', PasswordHasher().hash('legacy-password-123'),
                     'admin', 'active', environment_id, '2026-11-22T00:00:00+00:00'))
                db.executescript('''
                    CREATE TABLE desktop_states(account_id TEXT PRIMARY KEY, body TEXT NOT NULL);
                    CREATE TABLE backup_settings(id INTEGER PRIMARY KEY CHECK(id=1),
                        enabled INTEGER NOT NULL DEFAULT 0, frequency_hours INTEGER NOT NULL DEFAULT 24,
                        destination TEXT NOT NULL DEFAULT '', retention_mode TEXT NOT NULL DEFAULT 'replace',
                        retention_days INTEGER);
                    INSERT INTO backup_settings(id,enabled,frequency_hours,destination,retention_mode)
                        VALUES(1,0,12,'','replace');
                    CREATE TABLE backup_runs(id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
                        finished_at TEXT, status TEXT NOT NULL, snapshot TEXT);
                ''')
                db.execute('INSERT INTO desktop_states VALUES(?,?)',
                           (account_id, json.dumps(desktop)))
                db.execute('''INSERT INTO backup_runs(id,started_at,status)
                    VALUES(?,?,?)''', (str(uuid.uuid4()), '2026-11-22T00:00:00+00:00', 'completed'))
            with closing(sqlite3.connect(legacy / 'terminals.sqlite3')) as db, db:
                db.execute('''CREATE TABLE terminals (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, environment_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('open','closed')),
                    created_at TEXT NOT NULL, closed_at TEXT)''')
                db.execute('INSERT INTO terminals VALUES(?,?,?,?,?,NULL)',
                           (terminal_id, account_id, environment_id, 'open',
                            '2026-11-22T00:00:00+00:00'))

            def restore_snapshot(destination: Path) -> None:
                destination.mkdir()
                for name in ('identity.sqlite3', 'terminals.sqlite3'):
                    with closing(sqlite3.connect(legacy / name)) as source, closing(sqlite3.connect(destination / name)) as target:
                        source.backup(target)

            def verify_upgrade(data_dir: Path) -> None:
                identity = IdentityService(data_dir / 'identity.sqlite3', 'fixture-bootstrap-token')
                runtime = object()  # Nenhuma chamada Docker é necessária para verificar os registros.
                administration = AdministrationService(data_dir / 'identity.sqlite3', identity,
                                                       AppComposition(identity, runtime))
                terminals = TerminalService(data_dir / 'terminals.sqlite3', identity, runtime,
                                            api=object())
                BackupService(data_dir, administration, runtime)
                _, actor = identity.login('legacyadmin', 'legacy-password-123')
                self.assertEqual(actor.account_id, account_id)
                self.assertEqual(administration.get_desktop_record(actor),
                                 {'state': desktop, 'revision': 1})
                policy = administration.backup_settings(actor)
                self.assertEqual((policy['enabled'], policy['frequency_hours']), (0, 12))
                self.assertIsNone(policy['rpo_hours'])
                self.assertIsNone(policy['rto_hours'])
                self.assertEqual([row['id'] for row in terminals.list(actor)], [terminal_id])
                with closing(sqlite3.connect(data_dir / 'identity.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM backup_runs').fetchone()[0], 1)
                    self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
                    names = {row[0] for row in db.execute('SELECT name FROM schema_migrations')}
                    self.assertIn('administration.desktop.v2', names)
                    self.assertIn('administration.backup.objectives.v1', names)
                with closing(sqlite3.connect(data_dir / 'terminals.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM terminals').fetchone()[0], 1)
                    self.assertIn('terminal.records.v2',
                                  {row[0] for row in db.execute('SELECT name FROM schema_migrations')})
                    # O binário v1 insere por posição com seis campos; o schema v2 tem oito.
                    # Reversão de código exige o snapshot v1, nunca reutilizar este banco.
                    with self.assertRaises(sqlite3.OperationalError):
                        db.execute('INSERT INTO terminals VALUES(?,?,?,?,?,NULL)',
                                   (str(uuid.uuid4()), account_id, environment_id,
                                    'open', '2026-11-22T00:00:00+00:00'))

            upgraded = root / 'upgraded'
            restored = root / 'restored'
            restore_snapshot(upgraded)
            verify_upgrade(upgraded)
            verify_upgrade(upgraded)  # Reexecução não altera os registros legados.
            restore_snapshot(restored)
            verify_upgrade(restored)  # Snapshot N-1 pode seguir pelo forward recovery.


if __name__ == '__main__':
    unittest.main()

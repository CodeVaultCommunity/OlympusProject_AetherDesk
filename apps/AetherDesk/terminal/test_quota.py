import tempfile
import threading
import unittest
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerError
from apps.AetherDesk.runtime.docker import Environment

from .service import TerminalError, TerminalService


class RuntimeStub:
    def ensure(self, account_id, environment_id):
        return Environment(account_id, environment_id, 'fixture', 'fixture', 'running')

    def state(self, account_id, environment_id):
        return Environment(account_id, environment_id, 'fixture', 'fixture', 'stopped')


class BrokerStub:
    def __init__(self):
        self.calls = []
        self.fail_next = False

    def call(self, operation, account_id, environment_id, payload):
        if self.fail_next:
            self.fail_next = False
            raise BrokerError('BROKER_UNAVAILABLE')
        self.calls.append((operation, account_id, environment_id, payload))
        return {'ok': True}


class TerminalQuotaTests(unittest.TestCase):
    def test_two_services_share_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = IdentityService(Path(directory) / 'identity.sqlite3', 'fixture-bootstrap-token')
            identity.bootstrap('fixture-bootstrap-token', 'admin', 'fixture-admin-password')
            _, actor = identity.login('admin', 'fixture-admin-password')
            broker = BrokerStub()
            database = Path(directory) / 'terminals.sqlite3'
            first = TerminalService(database, identity, RuntimeStub(), broker=broker,
                                    max_sessions_per_account=1)
            second = TerminalService(database, identity, RuntimeStub(), broker=broker,
                                     max_sessions_per_account=1)
            start = threading.Barrier(3)

            def attempt(service):
                start.wait(timeout=5)
                try:
                    return service.create(actor)
                except TerminalError as exc:
                    return exc.code

            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(attempt, first)
                b = pool.submit(attempt, second)
                start.wait(timeout=5)
                results = [a.result(timeout=10), b.result(timeout=10)]
            rejected = [value for value in results if value in ('TERMINAL_QUOTA', 'TERMINAL_RECOVERING')]
            self.assertEqual(len(rejected), 1)
            created = next(value for value in results if value not in rejected)
            self.assertEqual(len(first.list(actor)), 1)
            self.assertEqual(len(broker.calls), 1)
            first.close(actor, created)
            self.assertNotEqual(second.create(actor), 'TERMINAL_QUOTA')

    def test_failed_or_interrupted_create_retries_same_durable_id(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = IdentityService(Path(directory) / 'identity.sqlite3', 'fixture-bootstrap-token')
            identity.bootstrap('fixture-bootstrap-token', 'admin', 'fixture-admin-password')
            _, actor = identity.login('admin', 'fixture-admin-password')
            broker = BrokerStub()
            database = Path(directory) / 'terminals.sqlite3'
            first = TerminalService(database, identity, RuntimeStub(), broker=broker,
                                    max_sessions_per_account=1)
            broker.fail_next = True
            with self.assertRaisesRegex(TerminalError, 'BROKER_UNAVAILABLE'):
                first.create(actor)
            with self.assertRaisesRegex(TerminalError, 'TERMINAL_RECOVERING'):
                first.create(actor)
            self.assertEqual(first.list(actor), [])
            with closing(sqlite3.connect(database)) as db:
                with db:
                    reserved_id = db.execute("SELECT id FROM terminals WHERE state='pending'").fetchone()[0]
                    db.execute("UPDATE terminals SET retry_at=? WHERE id=?",
                               ((datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(), reserved_id))
            second = TerminalService(database, identity, RuntimeStub(), broker=broker,
                                     max_sessions_per_account=1)
            self.assertEqual(second.create(actor), reserved_id)
            self.assertEqual(len(second.list(actor)), 1)
            self.assertEqual(broker.calls[-1][3]['terminal_id'], reserved_id)

    def test_quota_configuration_is_bounded(self):
        with self.assertRaisesRegex(TerminalError, 'INVALID_TERMINAL_QUOTA'):
            TerminalService('/unused', None, None, broker=BrokerStub(),
                            max_sessions_per_account=0)

    def test_legacy_open_session_survives_pending_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = IdentityService(Path(directory) / 'identity.sqlite3', 'fixture-bootstrap-token')
            identity.bootstrap('fixture-bootstrap-token', 'admin', 'fixture-admin-password')
            _, actor = identity.login('admin', 'fixture-admin-password')
            environment_id = identity.account(actor, actor.account_id)['environment_id']
            database = Path(directory) / 'terminals.sqlite3'
            terminal_id = '123e4567-e89b-12d3-a456-426614174000'
            with closing(sqlite3.connect(database)) as db:
                with db:
                    db.execute("""CREATE TABLE terminals (
                        id TEXT PRIMARY KEY, account_id TEXT NOT NULL, environment_id TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN ('open','closed')),
                        created_at TEXT NOT NULL, closed_at TEXT)""")
                    db.execute("INSERT INTO terminals VALUES(?,?,?,'open',?,NULL)",
                               (terminal_id, actor.account_id, environment_id, datetime.now(timezone.utc).isoformat()))
            service = TerminalService(database, identity, RuntimeStub(), broker=BrokerStub())
            self.assertEqual(service.list(actor)[0]['id'], terminal_id)
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute("SELECT state FROM terminals WHERE id=?",
                                            (terminal_id,)).fetchone()[0], 'open')


if __name__ == '__main__':
    unittest.main()

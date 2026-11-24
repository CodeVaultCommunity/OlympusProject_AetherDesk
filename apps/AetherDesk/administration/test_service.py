import tempfile
import unittest
import sqlite3
import json
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.administration.service import AdministrationService, AdministrationError
from apps.AetherDesk.administration.http import administration_router
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService, IdentityError
from apps.AetherDesk.identity.http import identity_router


class RuntimeStub:
    def __init__(self):
        self.stopped = []

    def stop_session(self, account_id, environment_id):
        self.stopped.append(account_id)


class AdministrationTests(unittest.TestCase):
    def test_legacy_desktop_table_migrates_once_without_losing_state(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'db.sqlite3'
            identity = IdentityService(db, 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, actor = identity.login('admin', 'strong-admin-password')
            old = {'windows': [], 'activeId': None, 'theme': 'light'}
            with closing(sqlite3.connect(db)) as connection:
                connection.execute('CREATE TABLE desktop_states(account_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
                connection.execute('INSERT INTO desktop_states VALUES(?,?)', (actor.account_id, json.dumps(old)))
                connection.commit()
            first = AdministrationService(db, identity, AppComposition(identity, RuntimeStub()))
            self.assertEqual(first.get_desktop_record(actor), {'state': old, 'revision': 1})
            second = AdministrationService(db, identity, AppComposition(identity, RuntimeStub()))
            self.assertEqual(second.get_desktop_record(actor), {'state': old, 'revision': 1})
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM schema_migrations WHERE name='administration.desktop.v2'").fetchone()[0], 1)

    def test_desktop_http_etag_conflict_and_legacy_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'db.sqlite3'
            identity = IdentityService(db, 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            service = AdministrationService(db, identity, AppComposition(identity, RuntimeStub()))
            app = FastAPI()
            app.include_router(identity_router(identity, 'csrf-secret-with-at-least-32-characters', secure_cookie=False))
            app.include_router(administration_router(service, identity, 'csrf-secret-with-at-least-32-characters'))
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/v1/login', json={
                    'username': 'admin', 'password': 'strong-admin-password'}).status_code, 200)
                response = client.get('/api/v1/desktop/state')
                self.assertEqual(response.json()['revision'], 0)
                self.assertEqual(response.headers['etag'], '"0"')
                csrf = client.cookies.get('aether_csrf')
                headers = {'X-CSRF-Token': csrf}
                legacy = {'windows': [], 'activeId': None, 'theme': 'dark'}
                self.assertEqual(client.put('/api/v1/desktop/state', json=legacy,
                    headers=headers).status_code, 200)
                self.assertEqual(client.get('/api/v1/desktop/state').json()['data'], legacy)
                desktop = {'schemaVersion': 2, 'windows': [], 'activeId': None, 'theme': 'light'}
                self.assertEqual(client.put('/api/v1/desktop/state', json=desktop,
                    headers=headers).status_code, 428)
                saved = client.put('/api/v1/desktop/state', json=desktop,
                    headers={**headers, 'If-Match': '"1"'})
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()['revision'], 2)
                self.assertEqual(client.put('/api/v1/desktop/state', json=desktop,
                    headers={**headers, 'If-Match': '"1"'}).status_code, 412)
                blocked = client.put('/api/v1/desktop/state', json=legacy,
                    headers=headers)
                self.assertEqual(blocked.status_code, 409)
                self.assertEqual(blocked.json()['detail'], 'CLIENT_UPGRADE_REQUIRED')
                self.assertEqual(client.get('/api/v1/desktop/state').json()['data'], desktop)

    def test_desktop_revision_rejects_stale_or_invalid_state(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'db.sqlite3'
            identity = IdentityService(db, 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, actor = identity.login('admin', 'strong-admin-password')
            service = AdministrationService(db, identity, AppComposition(identity, RuntimeStub()))
            self.assertEqual(service.get_desktop_record(actor)['revision'], 0)
            desktop = {'schemaVersion': 2, 'windows': [{'id': 'terminal-1', 'kind': 'terminal',
                'x': 20, 'y': 30, 'width': 700, 'height': 400, 'z': 1,
                'minimized': False, 'maximized': False}], 'activeId': 'terminal-1', 'theme': 'dark'}
            with self.assertRaisesRegex(AdministrationError, 'PRECONDITION_REQUIRED'):
                service.put_desktop(actor, desktop)
            service.put_desktop(actor, desktop, expected_revision=0)
            self.assertEqual(service.get_desktop_record(actor)['revision'], 1)
            changed = {**desktop, 'theme': 'light'}
            service.put_desktop(actor, changed, expected_revision=1)
            with self.assertRaisesRegex(AdministrationError, 'STALE_REVISION'):
                service.put_desktop(actor, desktop, expected_revision=1)
            self.assertEqual(service.get_desktop_record(actor)['state']['theme'], 'light')
            invalid = {**desktop, 'windows': [{**desktop['windows'][0], 'x': float('nan')}]}
            with self.assertRaisesRegex(AdministrationError, 'INVALID_DESKTOP'):
                service.put_desktop(actor, invalid, expected_revision=2)
            for active_id in ([], {}, 1, True):
                with self.subTest(active_id=active_id), self.assertRaisesRegex(
                    AdministrationError, 'INVALID_DESKTOP'
                ):
                    service.put_desktop(actor, {**desktop, 'activeId': active_id},
                                        expected_revision=2)
            self.assertEqual(service.get_desktop_record(actor)['revision'], 2)

    def test_backup_desktop_and_session_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'db.sqlite3'
            identity = IdentityService(db, 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, admin = identity.login('admin', 'strong-admin-password')
            member_id = identity.create_account(admin, 'alice', 'strong-alice-password')
            _, alice = identity.login('alice', 'strong-alice-password')
            runtime = RuntimeStub()
            service = AdministrationService(db, identity, AppComposition(identity, runtime))
            self.assertEqual(service.backup_settings(admin)['enabled'], 0)
            self.assertIsNone(service.backup_settings(admin)['rpo_hours'])
            self.assertIsNone(service.backup_settings(admin)['rto_hours'])
            with self.assertRaises(IdentityError):
                service.backup_settings(alice)
            policy = service.configure_backup(admin, enabled=True, frequency_hours=12,
                destination='/var/backups/aetherdesk', retention_mode='days', retention_days=7,
                rpo_hours=24, rto_hours=4)
            self.assertEqual(policy['retention_days'], 7)
            self.assertEqual((policy['rpo_hours'], policy['rto_hours']), (24, 4))
            with self.assertRaisesRegex(AdministrationError, 'INVALID_BACKUP_OBJECTIVE'):
                service.configure_backup(admin, enabled=True, frequency_hours=24,
                    destination='/var/backups/aetherdesk', retention_mode='days', retention_days=7,
                    rpo_hours=12, rto_hours=4)
            policy = service.configure_backup(admin, enabled=True, frequency_hours=24,
                destination='/var/backups/aetherdesk', retention_mode='replace', retention_days=None)
            self.assertIsNone(policy['retention_days'])
            self.assertIsNone(policy['rpo_hours'])
            self.assertIsNone(policy['rto_hours'])
            with self.assertRaises(AdministrationError):
                service.configure_backup(admin, enabled=True, frequency_hours=1,
                    destination='relative', retention_mode='replace', retention_days=None)
            desktop = {'windows': [{'kind': 'terminal', 'x': 11, 'y': 22,
                'width': 700, 'height': 400, 'z': 1}], 'activeId': None, 'theme': 'light'}
            service.put_desktop(alice, desktop)
            self.assertEqual(service.get_desktop(alice), desktop)
            self.assertEqual(service.accounts(admin)[1]['id'], member_id)
            self.assertTrue(service.permissions(admin, member_id))
            self.assertEqual(len(service.sessions(admin, member_id)), 1)
            service.stop_session(admin, member_id)
            self.assertEqual(runtime.stopped, [member_id])
            self.assertIn('backup.configure', [event['operation'] for event in service.audit(admin)])
            self.assertIn('session.stop', [event['operation'] for event in service.audit(admin)])
            with self.assertRaises(IdentityError):
                service.get_desktop(alice)


if __name__ == '__main__':
    unittest.main()

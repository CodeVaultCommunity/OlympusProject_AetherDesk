import tempfile
import unittest
from pathlib import Path

from apps.AetherDesk.administration.service import AdministrationService, AdministrationError
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService, IdentityError


class RuntimeStub:
    def __init__(self):
        self.stopped = []

    def stop_session(self, account_id, environment_id):
        self.stopped.append(account_id)


class AdministrationTests(unittest.TestCase):
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
            with self.assertRaises(IdentityError):
                service.backup_settings(alice)
            policy = service.configure_backup(admin, enabled=True, frequency_hours=12,
                destination='/var/backups/aetherdesk', retention_mode='days', retention_days=7)
            self.assertEqual(policy['retention_days'], 7)
            policy = service.configure_backup(admin, enabled=True, frequency_hours=24,
                destination='/var/backups/aetherdesk', retention_mode='replace', retention_days=None)
            self.assertIsNone(policy['retention_days'])
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

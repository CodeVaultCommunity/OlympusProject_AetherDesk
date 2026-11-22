import os
import subprocess
import tempfile
import unittest
import time
from pathlib import Path

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.backup.service import BackupService, verify_snapshot, restore_snapshot
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.files.gateway import ContainerFileGateway
from apps.AetherDesk.identity import IdentityError, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


@unittest.skipUnless(os.environ.get('AETHERDESK_DOCKER_TEST') == '1', 'requer Docker Linux descartável')
class BackupTests(unittest.TestCase):
    def test_snapshot_retention_and_restore_files_accounts_desktop(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            data_dir, backup_dir, restored = base / 'data', base / 'backups', base / 'restored'
            data_dir.mkdir()
            identity = IdentityService(data_dir / 'identity.sqlite3', 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, admin = identity.login('admin', 'strong-admin-password')
            account_id = identity.create_account(admin, 'alice', 'strong-alice-password')
            _, alice = identity.login('alice', 'strong-alice-password')
            bob_id = identity.create_account(admin, 'bobby', 'strong-bobby-password')
            _, bob = identity.login('bobby', 'strong-bobby-password')
            identity.set_permission(admin, account_id, 'terminal.open', False)
            runtime = DockerEnvironmentBroker('aetherdesk-files:w003')
            composition = AppComposition(identity, runtime)
            administration = AdministrationService(data_dir / 'identity.sqlite3', identity, composition)
            administration.put_desktop(alice, {'windows': [{'kind': 'editor', 'x': 17, 'y': 19,
                'width': 720, 'height': 470, 'z': 1}], 'activeId': None, 'theme': 'light'})
            env_id = identity.account(admin, account_id)['environment_id']
            bob_env_id = identity.account(admin, bob_id)['environment_id']
            admin_env_id = identity.account(admin, admin.account_id)['environment_id']
            account_resources = [runtime._names(env_id), runtime._names(bob_env_id),
                                 runtime._names(admin_env_id)]
            gateway = ContainerFileGateway(identity, runtime)
            try:
                gateway.write(alice, '/persist/remember.txt', b'stored-data')
                gateway.write(bob, '/persist/remember.txt', b'bobby-data')
                backup = BackupService(data_dir, administration, runtime)
                first = backup.run_once(backup_dir, 'days', 7)
                self.assertEqual(verify_snapshot(first)['format'], 1)
                old_snapshot = backup_dir / 'aetherdesk-old-fixture'
                old_snapshot.mkdir()
                old_time = time.time() - 10 * 24 * 3600
                os.utime(old_snapshot, (old_time, old_time))
                retained = backup.run_once(backup_dir, 'days', 7)
                self.assertFalse(old_snapshot.exists())
                self.assertTrue(first.exists())
                self.assertTrue(retained.exists())
                second = backup.run_once(backup_dir, 'replace')
                self.assertFalse(first.exists())
                self.assertFalse(retained.exists())
                self.assertTrue(second.exists())
                for container, volume in account_resources:
                    subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, check=True)
                restore_snapshot(second, restored, runtime)
                restored_identity = IdentityService(restored / 'identity.sqlite3', 'bootstrap-secret-long')
                _, restored_alice = restored_identity.login('alice', 'strong-alice-password')
                _, restored_bob = restored_identity.login('bobby', 'strong-bobby-password')
                with self.assertRaises(IdentityError):
                    restored_identity.require(restored_alice, 'terminal.open')
                restored_admin = AdministrationService(restored / 'identity.sqlite3', restored_identity,
                    AppComposition(restored_identity, runtime))
                self.assertEqual(restored_admin.get_desktop(restored_alice)['theme'], 'light')
                self.assertEqual(ContainerFileGateway(restored_identity, runtime).read(
                    restored_alice, '/persist/remember.txt')[0], b'stored-data')
                self.assertEqual(ContainerFileGateway(restored_identity, runtime).read(
                    restored_bob, '/persist/remember.txt')[0], b'bobby-data')
            finally:
                for container, volume in account_resources:
                    subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    unittest.main()

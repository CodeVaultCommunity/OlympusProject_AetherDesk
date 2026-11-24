import tempfile
import threading
import unittest
from pathlib import Path

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.backup.service import BackupService
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService


class RuntimeStub:
    pass


class BackupSchedulerTests(unittest.TestCase):
    def test_two_process_facades_schedule_one_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'identity.sqlite3'
            identity = IdentityService(path, 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, actor = identity.login('admin', 'strong-admin-password')
            administration = AdministrationService(path, identity, AppComposition(identity, RuntimeStub()))
            administration.configure_backup(actor, enabled=True, frequency_hours=1,
                destination='/fixture/backup', retention_mode='replace', retention_days=None)
            first = BackupService(temp, administration, RuntimeStub())
            second = BackupService(temp, administration, RuntimeStub())
            entered, finish = threading.Event(), threading.Event()
            calls = []

            def fake_snapshot(*args, **kwargs):
                calls.append(1)
                self.assertTrue(kwargs['lease_guard']())
                entered.set()
                self.assertTrue(finish.wait(5))
                return Path('/fixture/snapshot')

            first.run_once = fake_snapshot
            second.run_once = fake_snapshot
            result = []
            worker = threading.Thread(target=lambda: result.append(first.run_due()))
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertIsNone(second.run_due())
                self.assertEqual(len(calls), 1)
            finally:
                finish.set()
                worker.join(timeout=5)
            self.assertEqual(result, [Path('/fixture/snapshot')])


if __name__ == '__main__':
    unittest.main()

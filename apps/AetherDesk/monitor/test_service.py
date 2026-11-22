import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from apps.AetherDesk.identity import IdentityService, IdentityError
from apps.AetherDesk.monitor.service import MonitorService


class RuntimeStub:
    def state(self, account_id, environment_id):
        return SimpleNamespace(state='running', container_name='container-' + account_id)


class MetricsStub:
    def __init__(self):
        self.fail = False
        self.calls = 0

    def server(self):
        return {'cpu_percent': 80, 'memory_bytes': 1000, 'memory_limit_bytes': 2000,
                'storage_bytes': 5000, 'storage_limit_bytes': 10000}

    def environment(self, name):
        self.calls += 1
        if self.fail:
            raise OSError('stats offline')
        return {'state': 'running', 'cpu_percent': 10, 'memory_bytes': 100,
                'memory_limit_bytes': 500}


class MonitorTests(unittest.TestCase):
    def test_ownership_authorization_and_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = IdentityService(Path(temp) / 'id.sqlite3', 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, admin = identity.login('admin', 'strong-admin-password')
            account_id = identity.create_account(admin, 'alice', 'strong-alice-password')
            _, alice = identity.login('alice', 'strong-alice-password')
            source = MetricsStub()
            service = MonitorService(identity, RuntimeStub(), source, cache_seconds=0)
            self.assertEqual(service.self(alice)['current']['reference'], account_id)
            with self.assertRaises(IdentityError):
                service.server(alice)
            rows = [{'id': account_id, 'username': 'alice', 'environment_id': 'unused'}]
            self.assertEqual(service.server(admin, rows)['shared']['values']['memory_bytes'], 900)
            source.fail = True
            self.assertEqual(service.self(alice)['current']['status'], 'unavailable')
            self.assertIsNone(service.self(alice)['current']['values']['cpu_percent'])

    def test_cache_keeps_original_timestamp_and_limits_collection(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = IdentityService(Path(temp) / 'id.sqlite3', 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, admin = identity.login('admin', 'strong-admin-password')
            source = MetricsStub()
            service = MonitorService(identity, RuntimeStub(), source, cache_seconds=60)
            first = service.self(admin)['current']
            second = service.self(admin)['current']
            self.assertEqual(first['sampled_at'], second['sampled_at'])
            self.assertEqual(source.calls, 1)


if __name__ == '__main__':
    unittest.main()

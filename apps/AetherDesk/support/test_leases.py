import tempfile
import unittest
from pathlib import Path

from .leases import LeaseStore


class LeaseTests(unittest.TestCase):
    def test_two_workers_and_expired_owner_fencing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'leases.sqlite3'
            first, second = LeaseStore(path), LeaseStore(path)
            lease = first.acquire('backup', ttl_seconds=10, now=100)
            self.assertIsNotNone(lease)
            self.assertIsNone(second.acquire('backup', ttl_seconds=10, now=101))
            self.assertIsNone(first.renew(lease, ttl_seconds=10, now=111))
            successor = second.acquire('backup', ttl_seconds=10, now=111)
            self.assertGreater(successor.fence, lease.fence)
            self.assertFalse(first.release(lease))
            self.assertFalse(first.valid(lease, now=112))
            self.assertTrue(second.valid(successor, now=112))
            self.assertTrue(second.release(successor))


if __name__ == '__main__':
    unittest.main()

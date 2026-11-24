import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from .rate_limits import RateLimiter


class RateLimitTests(unittest.TestCase):
    def test_limit_is_atomic_hashed_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'identity.sqlite3'
            now = [100.0]
            first = RateLimiter(path, 'fixture-secret-at-least-32-characters', lambda: now[0])
            second = RateLimiter(path, 'fixture-secret-at-least-32-characters', lambda: now[0])
            self.assertTrue(first.consume('login', '127.0.0.1\0alice', 2, 60))
            self.assertTrue(second.consume('login', '127.0.0.1\0alice', 2, 60))
            self.assertFalse(first.consume('login', '127.0.0.1\0alice', 2, 60))
            self.assertTrue(first.consume('login', '127.0.0.1\0bob', 2, 60))
            with closing(sqlite3.connect(path)) as db:
                keys = [row[0] for row in db.execute('SELECT key_hash FROM rate_limits')]
            self.assertTrue(all('alice' not in value and '127.0.0.1' not in value for value in keys))
            now[0] = 161.0
            self.assertTrue(second.consume('login', '127.0.0.1\0alice', 2, 60))


if __name__ == '__main__':
    unittest.main()

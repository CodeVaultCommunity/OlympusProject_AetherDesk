import secrets
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from .secrets import Keyring, SecretError, SecretVault


class SecretTests(unittest.TestCase):
    def test_snapshot_restore_requires_matching_rotated_key(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'vault.sqlite3'
            snapshot = Path(temp) / 'snapshot.sqlite3'
            first_key, second_key = secrets.token_bytes(32), secrets.token_bytes(32)
            vault = SecretVault(source, Keyring({1: first_key}, 1))
            alice = vault.store('alice', 'ai', 'provider', b'alice-fixture-secret')
            bob = vault.store('bob', 'git', 'remote', b'bob-fixture-secret')
            self.assertEqual(vault.rotate(2, second_key), 2)
            with closing(sqlite3.connect(source)) as db, closing(sqlite3.connect(snapshot)) as backup:
                db.backup(backup)
            self.assertNotIn(b'alice-fixture-secret', snapshot.read_bytes())
            self.assertNotIn(b'bob-fixture-secret', snapshot.read_bytes())

            without_rotated_key = SecretVault(snapshot, Keyring({1: first_key}, 1))
            with self.assertRaisesRegex(SecretError, 'MASTER_KEY_UNAVAILABLE'):
                without_rotated_key.read('alice', alice['id'])
            with self.assertRaisesRegex(SecretError, 'MASTER_KEY_UNAVAILABLE'):
                without_rotated_key.verify_restore()
            restored = SecretVault(snapshot, Keyring({2: second_key}, 2))
            self.assertEqual(restored.verify_restore(),
                             {'active_secrets': 2, 'key_versions': [2]})
            self.assertEqual(restored.read('alice', alice['id']), b'alice-fixture-secret')
            self.assertEqual(restored.read('bob', bob['id']), b'bob-fixture-secret')
            with self.assertRaisesRegex(SecretError, 'NOT_FOUND'):
                restored.read('alice', bob['id'])

    def test_owner_isolation_tamper_rotation_and_revocation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'vault.sqlite3'
            key = secrets.token_bytes(32)
            vault = SecretVault(path, Keyring({1: key}, 1))
            metadata = vault.store('alice', 'ai', 'provider', b'fixture-token')
            self.assertNotIn('fixture-token', str(metadata))
            self.assertEqual(vault.read('alice', metadata['id']), b'fixture-token')
            with self.assertRaisesRegex(SecretError, 'NOT_FOUND'):
                vault.read('bob', metadata['id'])
            self.assertEqual(vault.rotate(2, secrets.token_bytes(32)), 1)
            self.assertEqual(vault.read('alice', metadata['id']), b'fixture-token')
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('UPDATE secrets SET ciphertext=? WHERE id=?', (b'bad', metadata['id']))
            with self.assertRaisesRegex(SecretError, 'SECRET_UNAVAILABLE'):
                vault.read('alice', metadata['id'])
            with self.assertRaisesRegex(SecretError, 'SECRET_UNAVAILABLE'):
                vault.verify_restore()
            self.assertTrue(vault.revoke('alice', metadata['id']))
            with self.assertRaisesRegex(SecretError, 'NOT_FOUND'):
                vault.read('alice', metadata['id'])

    def test_missing_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'vault.sqlite3'
            original = SecretVault(path, Keyring({1: secrets.token_bytes(32)}, 1))
            metadata = original.store('alice', 'git', 'remote', b'fixture')
            unavailable = SecretVault(path, Keyring({2: secrets.token_bytes(32)}, 2))
            with self.assertRaisesRegex(SecretError, 'MASTER_KEY_UNAVAILABLE'):
                unavailable.read('alice', metadata['id'])


if __name__ == '__main__':
    unittest.main()

import sqlite3
import hashlib
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from apps.AetherDesk.identity import IdentityError, IdentityService


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "identity.sqlite3"
        self.service = IdentityService(self.db_path, "bootstrap-secret")
        self.admin_id = self.service.bootstrap("bootstrap-secret", "admin", "strong-admin-password")
        self.admin_token, self.admin = self.service.login("admin", "strong-admin-password")

    def test_bootstrap_unique_and_password_hashed(self):
        with self.assertRaises(IdentityError) as raised:
            self.service.bootstrap("bootstrap-secret", "other", "another-strong-password")
        self.assertEqual(raised.exception.code, "CONFLICT")
        with sqlite3.connect(self.db_path) as db:
            stored = db.execute("SELECT password_hash FROM accounts WHERE id=?", (self.admin_id,)).fetchone()[0]
        db.close()
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertNotIn("strong-admin-password", stored)

    def test_rename_and_delete_keep_identity_and_environment(self):
        account_id = self.service.create_account(self.admin, "alice", "strong-alice-password")
        original = self.service.account(self.admin, account_id)
        changed = self.service.update_account(self.admin, account_id, username="alice_2",
                                              revision=original["revision"])
        self.assertEqual(changed["id"], original["id"])
        self.assertEqual(changed["environment_id"], original["environment_id"])
        token, actor = self.service.login("alice_2", "strong-alice-password")
        self.service.update_account(self.admin, account_id, state="deleted",
                                    revision=changed["revision"])
        self.assertEqual(self.service.account(self.admin, account_id)["environment_id"],
                         original["environment_id"])
        with self.assertRaises(IdentityError):
            self.service.actor(token)
        with self.assertRaises(IdentityError):
            self.service.login("alice_2", "strong-alice-password")
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual([row[0] for row in db.execute(
                "SELECT event FROM account_events WHERE account_id=? ORDER BY rowid",
                (actor.account_id,))], ["account.created", "account.deleted"])
        db.close()

    def test_revocation_and_permission_change_affect_open_context(self):
        account_id = self.service.create_account(self.admin, "alice", "strong-alice-password")
        token, actor = self.service.login("alice", "strong-alice-password")
        self.service.require(actor, "files.read")
        self.service.set_permission(self.admin, account_id, "files.read", False)
        with self.assertRaises(IdentityError):
            self.service.require(actor, "files.read")
        self.service.require(actor, "terminal.open")
        self.service.revoke_session(self.admin, actor.session_id)
        with self.assertRaises(IdentityError):
            self.service.require(actor, "terminal.open")
        with self.assertRaises(IdentityError):
            self.service.actor(token)

    def test_member_cannot_manage_or_read_other_account(self):
        account_id = self.service.create_account(self.admin, "alice", "strong-alice-password")
        _, actor = self.service.login("alice", "strong-alice-password")
        with self.assertRaises(IdentityError):
            self.service.create_account(actor, "mallory", "strong-mallory-password")
        with self.assertRaises(IdentityError):
            self.service.account(actor, self.admin_id)
        self.assertEqual(self.service.account(actor, account_id)["id"], account_id)

    def test_expired_session_is_rejected_without_stopping_environment(self):
        token, actor = self.service.login("admin", "strong-admin-password")
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                       (actor.session_id,))
            db.commit()
        with self.assertRaises(IdentityError):
            self.service.actor(token)
        with self.assertRaises(IdentityError):
            self.service.require(actor, "files.read")

    def test_v1_session_migration_expires_legacy_tokens(self):
        legacy = Path(self.tmp.name) / 'legacy.sqlite3'
        account_id, environment_id, session_id = (str(uuid.uuid4()) for _ in range(3))
        token = 'legacy-token'
        with closing(sqlite3.connect(legacy)) as db:
            db.executescript((Path(__file__).parent / 'migrations' / '001_initial.sql').read_text())
            db.execute('PRAGMA user_version=1')
            db.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?,1,1,?)",
                       (account_id, 'legacy', 'old-hash', 'member', 'active', environment_id,
                        '2026-01-01T00:00:00+00:00'))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)",
                       (session_id, account_id, hashlib.sha256(token.encode()).hexdigest(),
                        None, '2026-01-01T00:00:00+00:00'))
            db.commit()
        migrated = IdentityService(legacy, 'bootstrap-secret')
        with self.assertRaises(IdentityError):
            migrated.actor(token)
        with closing(sqlite3.connect(legacy)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM accounts').fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()

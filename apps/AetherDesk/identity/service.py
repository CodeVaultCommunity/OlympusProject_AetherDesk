"""Conta, sessão e autorização. Nenhuma operação pessoal aceita dono do cliente."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


class IdentityError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ActorContext:
    account_id: str
    session_id: str
    role: str
    permissions_version: int


MEMBER_CAPABILITIES = frozenset({
    "files.read", "files.write", "terminal.open", "terminal.control",
    "metrics.self", "preferences.read", "preferences.write",
})
ADMIN_CAPABILITIES = MEMBER_CAPABILITIES | frozenset({
    "metrics.server", "metrics.accounts", "accounts.view", "accounts.manage",
    "permissions.view", "permissions.manage", "audit.view", "backup.view",
    "backup.manage", "backup.restore", "environment.manage",
    "sessions.revoke", "sessions.stop",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IdentityService:
    def __init__(self, db_path: str | Path, bootstrap_token: str):
        if len(bootstrap_token) < 16:
            raise IdentityError("WEAK_BOOTSTRAP_TOKEN")
        self.db_path = str(db_path)
        self._bootstrap_hash = _token_hash(bootstrap_token)
        self._hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                migration = Path(__file__).parent / "migrations" / "001_initial.sql"
                db.executescript(migration.read_text(encoding="utf-8"))
                db.execute("PRAGMA user_version=1")
                version = 1
            if version == 1:
                migration = Path(__file__).parent / "migrations" / "002_session_expiry.sql"
                db.executescript(migration.read_text(encoding="utf-8"))
                # Sessões antigas não tinham validade; migração as expira.
                db.execute("UPDATE sessions SET expires_at=? WHERE expires_at IS NULL", (_now(),))
                db.execute("PRAGMA user_version=2")
            elif version != 2:
                raise IdentityError("UNSUPPORTED_SCHEMA")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _audit(self, db: sqlite3.Connection, actor_id: str | None, operation: str,
               target_id: str | None, result: str = "ok") -> None:
        db.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?)",
                   (str(uuid.uuid4()), actor_id, operation, target_id, _now(), result))

    def _event(self, db: sqlite3.Connection, account_id: str, event: str) -> None:
        db.execute("INSERT INTO account_events VALUES(?,?,?,?,NULL)",
                   (str(uuid.uuid4()), account_id, event, _now()))

    def bootstrap(self, token: str, username: str, password: str) -> str:
        if not secrets.compare_digest(_token_hash(token), self._bootstrap_hash):
            raise IdentityError("FORBIDDEN")
        self._validate_credentials(username, password)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
                raise IdentityError("CONFLICT")
            account_id = str(uuid.uuid4())
            db.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?,1,1,?)",
                       (account_id, username, self._hasher.hash(password), "admin",
                        "active", str(uuid.uuid4()), _now()))
            self._audit(db, account_id, "bootstrap", account_id)
            self._event(db, account_id, "account.created")
            db.commit()
            return account_id

    @staticmethod
    def _validate_credentials(username: str, password: str) -> None:
        if not 3 <= len(username) <= 64 or not username.replace("_", "").replace("-", "").isalnum():
            raise IdentityError("INVALID_USERNAME")
        if len(password) < 12:
            raise IdentityError("WEAK_PASSWORD")

    def login(self, username: str, password: str) -> tuple[str, ActorContext]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            if row is None or row["state"] != "active":
                raise IdentityError("UNAUTHENTICATED")
            try:
                self._hasher.verify(row["password_hash"], password)
            except VerifyMismatchError as exc:
                raise IdentityError("UNAUTHENTICATED") from exc
            token = secrets.token_urlsafe(48)
            session_id = str(uuid.uuid4())
            db.execute("INSERT INTO sessions(id,account_id,token_hash,revoked_at,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                       (session_id, row["id"], _token_hash(token), None, _now(),
                        (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()))
            return token, ActorContext(row["id"], session_id, row["role"], row["permissions_version"])

    def actor(self, token: str) -> ActorContext:
        with self._connect() as db:
            row = db.execute("""SELECT s.id AS session_id,a.id AS account_id,a.role,
                       a.permissions_version FROM sessions s JOIN accounts a ON a.id=s.account_id
                       WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?
                         AND a.state='active'""",
                       (_token_hash(token), _now())).fetchone()
            if row is None:
                raise IdentityError("UNAUTHENTICATED")
            return ActorContext(**dict(row))

    def logout(self, token: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                       (_now(), _token_hash(token)))

    def capabilities(self, actor: ActorContext) -> frozenset[str]:
        with self._connect() as db:
            row = db.execute("SELECT role,state FROM accounts WHERE id=?", (actor.account_id,)).fetchone()
            if row is None or row["state"] != "active":
                raise IdentityError("UNAUTHENTICATED")
            caps = set(ADMIN_CAPABILITIES if row["role"] == "admin" else MEMBER_CAPABILITIES)
            for override in db.execute("SELECT capability,allowed FROM permission_overrides WHERE account_id=?",
                                       (actor.account_id,)):
                if override["allowed"]:
                    caps.add(override["capability"])
                else:
                    caps.discard(override["capability"])
            return frozenset(caps)

    def _require_active_session(self, actor: ActorContext) -> None:
        with self._connect() as db:
            active = db.execute("""SELECT 1 FROM sessions s JOIN accounts a ON a.id=s.account_id
                                   WHERE s.id=? AND s.account_id=? AND s.revoked_at IS NULL
                                     AND s.expires_at>? AND a.state='active'""",
                                (actor.session_id, actor.account_id, _now())).fetchone()
        if not active:
            raise IdentityError("UNAUTHENTICATED")

    def assert_active(self, actor: ActorContext) -> None:
        self._require_active_session(actor)

    def require(self, actor: ActorContext, capability: str) -> None:
        # Revalida a sessão e permissões em toda ação, inclusive mensagens WS.
        self._require_active_session(actor)
        if capability not in self.capabilities(actor):
            raise IdentityError("FORBIDDEN")

    def create_account(self, actor: ActorContext, username: str, password: str,
                       role: str = "member") -> str:
        self.require(actor, "accounts.manage")
        self._validate_credentials(username, password)
        if role not in ("member", "admin"):
            raise IdentityError("INVALID_ROLE")
        account_id = str(uuid.uuid4())
        with self._connect() as db:
            try:
                db.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?,1,1,?)",
                           (account_id, username, self._hasher.hash(password), role,
                            "active", str(uuid.uuid4()), _now()))
            except sqlite3.IntegrityError as exc:
                raise IdentityError("CONFLICT") from exc
            self._audit(db, actor.account_id, "account.create", account_id)
            self._event(db, account_id, "account.created")
        return account_id

    def account(self, actor: ActorContext, account_id: str) -> dict:
        self._require_active_session(actor)
        if account_id != actor.account_id:
            self.require(actor, "accounts.view")
        with self._connect() as db:
            row = db.execute("""SELECT id,username,role,state,environment_id,
                              permissions_version,revision,created_at FROM accounts WHERE id=?""",
                             (account_id,)).fetchone()
            if row is None:
                raise IdentityError("NOT_FOUND")
            return dict(row)

    def update_account(self, actor: ActorContext, account_id: str, *,
                       username: str | None = None, password: str | None = None,
                       state: str | None = None, revision: int) -> dict:
        self.require(actor, "accounts.manage")
        if state not in (None, "active", "disabled", "deleted"):
            raise IdentityError("INVALID_STATE")
        if username is not None:
            self._validate_credentials(username, password or "placeholder-password")
        if password is not None and len(password) < 12:
            raise IdentityError("WEAK_PASSWORD")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            if old is None:
                raise IdentityError("NOT_FOUND")
            if old["revision"] != revision:
                raise IdentityError("STALE_REVISION")
            if old["state"] == "deleted":
                raise IdentityError("CONFLICT")
            if old["role"] == "admin" and state in ("disabled", "deleted"):
                count = db.execute("SELECT count(*) FROM accounts WHERE role='admin' AND state='active'").fetchone()[0]
                if count <= 1:
                    raise IdentityError("LAST_ADMIN")
            try:
                db.execute("""UPDATE accounts SET username=?,password_hash=?,state=?,revision=revision+1
                              WHERE id=?""", (username or old["username"],
                                self._hasher.hash(password) if password else old["password_hash"],
                                state or old["state"], account_id))
            except sqlite3.IntegrityError as exc:
                raise IdentityError("CONFLICT") from exc
            if state in ("disabled", "deleted"):
                db.execute("UPDATE sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                           (_now(), account_id))
                self._event(db, account_id, "account." + state)
            self._audit(db, actor.account_id, "account.update", account_id)
            db.commit()
        return self.account(actor, account_id)

    def revoke_session(self, actor: ActorContext, session_id: str) -> None:
        self.require(actor, "sessions.revoke")
        with self._connect() as db:
            row = db.execute("SELECT account_id FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise IdentityError("NOT_FOUND")
            db.execute("UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (_now(), session_id))
            self._audit(db, actor.account_id, "session.revoke", row["account_id"])

    def revoke_all_sessions(self, actor: ActorContext, account_id: str) -> None:
        self.require(actor, "sessions.stop")
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
                raise IdentityError("NOT_FOUND")
            db.execute("UPDATE sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                       (_now(), account_id))
            self._audit(db, actor.account_id, "session.stop", account_id)

    def pending_account_events(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("""SELECT e.id,e.account_id,e.event,a.environment_id
                FROM account_events e JOIN accounts a ON a.id=e.account_id
                WHERE e.consumed_at IS NULL ORDER BY e.at,e.id""")]

    def mark_account_event_consumed(self, event_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE account_events SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                       (_now(), event_id))

    def set_permission(self, actor: ActorContext, account_id: str, capability: str,
                       allowed: bool) -> None:
        self.require(actor, "permissions.manage")
        if capability not in ADMIN_CAPABILITIES:
            raise IdentityError("INVALID_CAPABILITY")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM accounts WHERE id=? AND state!='deleted'", (account_id,)).fetchone():
                raise IdentityError("NOT_FOUND")
            db.execute("""INSERT INTO permission_overrides VALUES(?,?,?)
                          ON CONFLICT(account_id,capability) DO UPDATE SET allowed=excluded.allowed""",
                       (account_id, capability, int(allowed)))
            db.execute("UPDATE accounts SET permissions_version=permissions_version+1 WHERE id=?",
                       (account_id,))
            self._audit(db, actor.account_id, "permission.set", account_id)
            db.commit()

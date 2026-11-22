"""PTY Bash persistente em tmux, com conexão transportada pelo Docker Engine."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import docker

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


class TerminalError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError) as exc:
        raise TerminalError("INVALID_ID") from exc


class TerminalConnection:
    def __init__(self, service: "TerminalService", actor: ActorContext,
                 terminal_id: str, exec_id: str, stream):
        self.service = service
        self.actor = actor
        self.terminal_id = terminal_id
        self.exec_id = exec_id
        self.stream = stream
        self.socket = getattr(stream, "_sock", stream)

    def read(self, size: int = 4096) -> bytes:
        self.service._owned(self.actor, self.terminal_id, "terminal.control")
        return self.socket.recv(size)

    def write(self, data: bytes) -> None:
        self.service._owned(self.actor, self.terminal_id, "terminal.control")
        if len(data) > 65536:
            raise TerminalError("TOO_LARGE")
        self.socket.sendall(data)

    def resize(self, columns: int, rows: int) -> None:
        self.service._owned(self.actor, self.terminal_id, "terminal.control")
        if not 20 <= columns <= 400 or not 5 <= rows <= 200:
            raise TerminalError("INVALID_SIZE")
        self.service.api.exec_resize(self.exec_id, height=rows, width=columns)

    def close(self) -> None:
        self.stream.close()


class TerminalService:
    def __init__(self, db_path: str | Path, identity: IdentityService,
                 runtime: DockerEnvironmentBroker, api=None):
        self.db_path = str(db_path)
        self.identity = identity
        self.runtime = runtime
        self.api = api or docker.from_env().api
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS terminals (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, environment_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('open','closed')),
                created_at TEXT NOT NULL, closed_at TEXT
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _owned(self, actor: ActorContext, terminal_id: str, capability: str) -> dict:
        self.identity.require(actor, capability)
        with self._connect() as db:
            row = db.execute("SELECT * FROM terminals WHERE id=? AND account_id=?",
                             (_uuid(terminal_id), actor.account_id)).fetchone()
            if row is None or row["state"] != "open":
                raise TerminalError("NOT_FOUND")
            return dict(row)

    def create(self, actor: ActorContext, columns: int = 80, rows: int = 24) -> str:
        self.identity.require(actor, "terminal.open")
        if not 20 <= columns <= 400 or not 5 <= rows <= 200:
            raise TerminalError("INVALID_SIZE")
        account = self.identity.account(actor, actor.account_id)
        env = self.runtime.ensure(actor.account_id, account["environment_id"])
        terminal_id = str(uuid.uuid4())
        self.runtime.exec(actor.account_id, env.environment_id, [
            "tmux", "-L", "aether", "-f", "/dev/null", "new-session", "-d",
            "-s", terminal_id, "-c", "/persist", "-x", str(columns), "-y", str(rows), "/bin/bash"])
        with self._connect() as db:
            db.execute("INSERT INTO terminals VALUES(?,?,?,?,?,NULL)",
                       (terminal_id, actor.account_id, env.environment_id, "open", _now()))
        return terminal_id

    def list(self, actor: ActorContext) -> list[dict]:
        self.identity.require(actor, "terminal.open")
        with self._connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,state,created_at FROM terminals
                WHERE account_id=? ORDER BY created_at""", (actor.account_id,))]

    def attach(self, actor: ActorContext, terminal_id: str) -> TerminalConnection:
        row = self._owned(actor, terminal_id, "terminal.control")
        env = self.runtime.state(actor.account_id, row["environment_id"])
        if env.state != "running":
            raise TerminalError("ENVIRONMENT_STOPPED")
        command = ["tmux", "-L", "aether", "-f", "/dev/null", "attach-session", "-t", terminal_id]
        execution = self.api.exec_create(env.container_name, command, stdin=True, tty=True,
                                         stdout=True, stderr=True, user="10001:10001")
        stream = self.api.exec_start(execution["Id"], tty=True, socket=True)
        return TerminalConnection(self, actor, terminal_id, execution["Id"], stream)

    def close(self, actor: ActorContext, terminal_id: str) -> None:
        row = self._owned(actor, terminal_id, "terminal.control")
        env = self.runtime.state(actor.account_id, row["environment_id"])
        if env.state == "running":
            self.runtime.exec(actor.account_id, row["environment_id"],
                              ["tmux", "-L", "aether", "kill-session", "-t", terminal_id])
        with self._connect() as db:
            db.execute("UPDATE terminals SET state='closed',closed_at=? WHERE id=?",
                       (_now(), terminal_id))

    def close_all_for_account(self, account_id: str) -> None:
        """Transição interna após parada/exclusão do ambiente; não aceita dono do cliente."""
        with self._connect() as db:
            db.execute("UPDATE terminals SET state='closed',closed_at=? WHERE account_id=? AND state='open'",
                       (_now(), _uuid(account_id)))

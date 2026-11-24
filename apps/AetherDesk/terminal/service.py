"""PTY Bash persistente em tmux, com conexão transportada pelo Docker Engine."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import docker

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError
from apps.AetherDesk.support.migrations import apply_migration


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
        if self.service.broker:
            row = self.service._owned(self.actor, self.terminal_id, "terminal.control")
            try:
                self.service.broker.call('terminal_resize', self.actor.account_id,
                    row['environment_id'], {'exec_id': self.exec_id, 'columns': columns, 'rows': rows})
            except BrokerError as exc:
                raise TerminalError(str(exc)) from exc
        else:
            self.service.api.exec_resize(self.exec_id, height=rows, width=columns)

    def close(self) -> None:
        self.stream.close()


class TerminalService:
    def __init__(self, db_path: str | Path, identity: IdentityService,
                 runtime: DockerEnvironmentBroker, api=None, broker: BrokerClient | None = None,
                 max_sessions_per_account: int = 8):
        if type(max_sessions_per_account) is not int or not 1 <= max_sessions_per_account <= 64:
            raise TerminalError('INVALID_TERMINAL_QUOTA')
        self.db_path = str(db_path)
        self.identity = identity
        self.runtime = runtime
        self.broker = broker
        self.max_sessions_per_account = max_sessions_per_account
        self._docker_client = docker.from_env() if api is None and broker is None else None
        self.api = api if api is not None else (self._docker_client.api if self._docker_client else None)
        apply_migration(self.db_path, 'terminal.records.v1', lambda db: db.execute("""
            CREATE TABLE IF NOT EXISTS terminals (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, environment_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('open','closed')),
                created_at TEXT NOT NULL, closed_at TEXT
            )"""))
        def add_pending(db):
            db.execute("""CREATE TABLE terminals_v2 (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, environment_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','open','closed')),
                created_at TEXT NOT NULL, closed_at TEXT,
                columns INTEGER NOT NULL DEFAULT 80, rows INTEGER NOT NULL DEFAULT 24,
                retry_at TEXT NOT NULL
            )""")
            db.execute("""INSERT INTO terminals_v2
                (id,account_id,environment_id,state,created_at,closed_at,retry_at)
                SELECT id,account_id,environment_id,state,created_at,closed_at,created_at FROM terminals""")
            db.execute('DROP TABLE terminals')
            db.execute('ALTER TABLE terminals_v2 RENAME TO terminals')
        apply_migration(self.db_path, 'terminal.records.v2', add_pending)

    def shutdown(self) -> None:
        if self._docker_client is not None:
            self._docker_client.close()

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
        with self._connect() as db:
            # Reserva durável antes do IPC. Uma queda após a criação remota deixa
            # um ID recuperável, sem abrir sessão fora da quota.
            db.execute('BEGIN IMMEDIATE')
            retry_before = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
            pending = db.execute("""SELECT id,environment_id,columns,rows FROM terminals
                WHERE account_id=? AND state='pending' AND retry_at<=?
                ORDER BY created_at LIMIT 1""",
                (actor.account_id, retry_before)).fetchone()
            active = db.execute("SELECT COUNT(*) FROM terminals WHERE account_id=? AND state IN ('open','pending')",
                                (actor.account_id,)).fetchone()[0]
            if pending is None and active >= self.max_sessions_per_account:
                recovering = db.execute("SELECT 1 FROM terminals WHERE account_id=? AND state='pending'",
                                        (actor.account_id,)).fetchone()
                raise TerminalError('TERMINAL_RECOVERING' if recovering else 'TERMINAL_QUOTA')
            if pending is None:
                terminal_id = str(uuid.uuid4())
                db.execute("""INSERT INTO terminals
                    (id,account_id,environment_id,state,created_at,columns,rows,retry_at)
                    VALUES(?,?,?,'pending',?,?,?,?)""",
                    (terminal_id, actor.account_id, env.environment_id, _now(), columns, rows, _now()))
            else:
                terminal_id = pending['id']
                if pending['environment_id'] != env.environment_id:
                    raise TerminalError('ENVIRONMENT_MISMATCH')
                columns, rows = pending['columns'], pending['rows']
                db.execute("UPDATE terminals SET retry_at=? WHERE id=?", (_now(), terminal_id))
        if self.broker:
            try:
                self.broker.call('terminal_create', actor.account_id, env.environment_id,
                    {'terminal_id': terminal_id, 'columns': columns, 'rows': rows})
            except BrokerError as exc:
                raise TerminalError(str(exc)) from exc
        else:
            existing = self.runtime.exec_status(actor.account_id, env.environment_id, [
                'tmux', '-L', 'aether', '-f', '/dev/null', 'has-session', '-t', terminal_id])
            if existing.returncode == 1:
                self.runtime.exec(actor.account_id, env.environment_id, [
                    "tmux", "-L", "aether", "-f", "/dev/null", "new-session", "-d",
                    "-s", terminal_id, "-c", "/persist", "-x", str(columns), "-y", str(rows), "/bin/bash"])
            elif existing.returncode != 0:
                raise TerminalError('RUNTIME_UNAVAILABLE')
        with self._connect() as db:
            changed = db.execute("UPDATE terminals SET state='open' WHERE id=? AND state='pending'",
                                 (terminal_id,)).rowcount
            if changed != 1:
                raise TerminalError('TERMINAL_REVOKED')
        return terminal_id

    def list(self, actor: ActorContext) -> list[dict]:
        self.identity.require(actor, "terminal.open")
        with self._connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,state,created_at FROM terminals
                WHERE account_id=? AND state!='pending' ORDER BY created_at""", (actor.account_id,))]

    def attach(self, actor: ActorContext, terminal_id: str) -> TerminalConnection:
        row = self._owned(actor, terminal_id, "terminal.control")
        env = self.runtime.state(actor.account_id, row["environment_id"])
        if env.state != "running":
            raise TerminalError("ENVIRONMENT_STOPPED")
        if self.broker:
            try:
                exec_id, stream = self.broker.open_terminal(actor.account_id,
                    row["environment_id"], terminal_id)
            except BrokerError as exc:
                raise TerminalError(str(exc)) from exc
        else:
            command = ["tmux", "-L", "aether", "-f", "/dev/null", "attach-session", "-t", terminal_id]
            execution = self.api.exec_create(env.container_name, command, stdin=True, tty=True,
                                             stdout=True, stderr=True, user="10001:10001")
            stream = self.api.exec_start(execution["Id"], tty=True, socket=True)
            exec_id = execution["Id"]
        return TerminalConnection(self, actor, terminal_id, exec_id, stream)

    def close(self, actor: ActorContext, terminal_id: str) -> None:
        row = self._owned(actor, terminal_id, "terminal.control")
        env = self.runtime.state(actor.account_id, row["environment_id"])
        if env.state == "running":
            if self.broker:
                try:
                    self.broker.call('terminal_kill', actor.account_id, row['environment_id'],
                                     {'terminal_id': terminal_id})
                except BrokerError as exc:
                    raise TerminalError(str(exc)) from exc
            else:
                self.runtime.exec(actor.account_id, row["environment_id"],
                                  ["tmux", "-L", "aether", "kill-session", "-t", terminal_id])
        with self._connect() as db:
            db.execute("UPDATE terminals SET state='closed',closed_at=? WHERE id=?",
                       (_now(), terminal_id))

    def close_all_for_account(self, account_id: str) -> None:
        """Transição interna após parada/exclusão do ambiente; não aceita dono do cliente."""
        with self._connect() as db:
            db.execute("UPDATE terminals SET state='closed',closed_at=? WHERE account_id=? AND state IN ('open','pending')",
                       (_now(), _uuid(account_id)))

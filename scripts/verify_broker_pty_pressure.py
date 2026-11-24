"""Exercita backpressure do relay PTY com Docker real na fixture W002."""

from __future__ import annotations

import base64
import os
import socket
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError


def main() -> None:
    data_dir = Path(os.environ['AETHERDESK_DATA_DIR'])
    if data_dir != Path('/data') or not Path('/ipc/broker.sock').is_socket():
        raise RuntimeError('PTY pressure requires the disposable W002 fixture')
    identity = IdentityService(data_dir / 'identity.sqlite3',
                               os.environ['AETHERDESK_BOOTSTRAP_TOKEN'])
    _token, actor = identity.login('w002fixture', 'w002-fixture-password')
    with closing(sqlite3.connect(data_dir / 'identity.sqlite3')) as db:
        environment_id = db.execute('SELECT environment_id FROM accounts WHERE id=?',
                                    (actor.account_id,)).fetchone()[0]
    with closing(sqlite3.connect(data_dir / 'terminals.sqlite3')) as db:
        row = db.execute("""SELECT id FROM terminals WHERE account_id=? AND state='open'
            ORDER BY created_at LIMIT 1""", (actor.account_id,)).fetchone()
    if row is None:
        raise RuntimeError('No fixture terminal')
    terminal_id = row[0]
    client = BrokerClient(os.environ['AETHERDESK_BROKER_SOCKET'],
                          base64.b64decode(os.environ['AETHERDESK_BROKER_SECRET_B64']))
    _exec_id, channel = client.open_terminal(actor.account_id, environment_id, terminal_id)
    attachments = []
    try:
        channel.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        started = time.monotonic()
        channel.sendall(b'python3 -c "import sys;sys.stdout.buffer.write(b\'x\'*8388608)"\n')
        # O cliente intencionalmente não drena o canal por mais que o timeout
        # de envio do relay (10 s na fixture). A saída é limitada a 8 MiB.
        time.sleep(13)
        channel.settimeout(3)
        received = 0
        while True:
            chunk = channel.recv(65536)
            if not chunk:
                break
            received += len(chunk)
            if received > 8 * 1024 * 1024:
                raise RuntimeError('PTY relay buffered unbounded output')
        if received == 0 or received >= 8 * 1024 * 1024:
            raise RuntimeError('PTY pressure did not stop the stream early')
        # O primeiro anexo deve ter liberado a quota de quatro por conta.
        for _ in range(4):
            _new_exec, attached = client.open_terminal(actor.account_id,
                                                       environment_id, terminal_id)
            attachments.append(attached)
        try:
            client.open_terminal(actor.account_id, environment_id, terminal_id)
        except BrokerError as exc:
            if str(exc) != 'TERMINAL_QUOTA':
                raise
        else:
            raise RuntimeError('PTY attachment quota was not enforced')
        print('AETHERDESK_PTY_PRESSURE=' + str({
            'sent_limit_bytes': 8 * 1024 * 1024, 'received_before_close': received,
            'relay_closed_after_seconds': round(time.monotonic() - started, 2),
            'attachment_slots_recovered': 4,
        }), flush=True)
    finally:
        channel.close()
        for attached in attachments:
            attached.close()


if __name__ == '__main__':
    main()

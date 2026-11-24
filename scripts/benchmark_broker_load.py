"""Mede oito contas simultâneas em uma fixture W002 com 20 contas ao todo.

Executar somente no contêiner web descartável de verify_broker_containers.ps1.
As contas extras não geram eventos de provisionamento; só oito ambientes são
ativados. O harness identifica todos os IDs no banco para limpeza por label.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from apps.AetherDesk.files.broker_gateway import BrokerFileGateway
from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerEnvironmentAdapter


def _percentiles(values: list[float]) -> dict:
    ordered = sorted(values)
    return {'count': len(ordered), 'p50_ms': round(statistics.median(ordered), 2),
            'p95_ms': round(ordered[round((len(ordered) - 1) * .95)], 2),
            'p99_ms': round(ordered[round((len(ordered) - 1) * .99)], 2)}


def main() -> None:
    data_dir = Path(os.environ['AETHERDESK_DATA_DIR'])
    if data_dir != Path('/data') or not Path('/ipc/broker.sock').is_socket():
        raise RuntimeError('Benchmark requires the disposable W002 fixture')
    identity = IdentityService(data_dir / 'identity.sqlite3',
                               os.environ['AETHERDESK_BOOTSTRAP_TOKEN'])
    database = data_dir / 'identity.sqlite3'
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        accounts = db.execute('SELECT username,password_hash FROM accounts').fetchall()
        if len(accounts) != 2 or {row[0] for row in accounts} != {'w002fixture', 'w002other'}:
            raise RuntimeError('Unexpected fixture accounts')
        password_hash = next(row[1] for row in accounts if row[0] == 'w002other')
        created_at = datetime.now(timezone.utc).isoformat()
        for index in range(18):
            db.execute('''INSERT INTO accounts
                (id,username,password_hash,role,state,environment_id,created_at)
                VALUES(?,?,?,'member','active',?,?)''',
                (str(uuid.uuid4()), f'w002load{index:02d}', password_hash,
                 str(uuid.uuid4()), created_at))

    actors = [identity.login(f'w002load{index:02d}', 'w002-other-password')[1]
              for index in range(8)]
    client = BrokerClient(os.environ['AETHERDESK_BROKER_SOCKET'],
                          base64.b64decode(os.environ['AETHERDESK_BROKER_SECRET_B64']))
    runtime = BrokerEnvironmentAdapter(client)
    files = BrokerFileGateway(identity, client)
    for actor in actors:
        account = identity.account(actor, actor.account_id)
        environment_id = account['environment_id']
        runtime.ensure(actor.account_id, environment_id)
        print('AETHERDESK_FIXTURE_ENV=' + environment_id, flush=True)
        files.call(actor, 'mkdir', '/persist/bench100')
        for index in range(100):
            files.write(actor, f'/persist/bench100/item{index:03d}.txt', b'x')
        files.write(actor, '/persist/bench-1mib.bin', b'x' * (1024 * 1024))

    def measure(actor, operation):
        started = time.perf_counter()
        if operation == 'list':
            result = files.call(actor, 'list', '/persist/bench100')
            if len(result) != 100:
                raise RuntimeError('Incorrect listing size')
        elif operation == 'read_1mib':
            result, _revision = files.read(actor, '/persist/bench-1mib.bin')
            if len(result) != 1024 * 1024:
                raise RuntimeError('Incorrect file size')
        else:
            raise RuntimeError('Invalid operation')
        return (time.perf_counter() - started) * 1000

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for operation in ('list', 'read_1mib'):
            samples = []
            for _ in range(30):
                futures = [pool.submit(measure, actor, operation) for actor in actors]
                samples.extend(future.result(timeout=45) for future in futures)
            results[operation] = _percentiles(samples)
    print('AETHERDESK_LOAD_MANIFEST=' + json.dumps({
        'accounts': 20, 'active_accounts': 8, 'concurrency': 8,
        'samples_per_account_per_operation': 30, 'cache': 'warm',
        'files_per_account': 100, 'read_bytes': 1024 * 1024,
    }, sort_keys=True), flush=True)
    print('AETHERDESK_LOAD_BENCHMARK=' + json.dumps(results, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()

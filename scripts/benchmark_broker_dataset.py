"""Compara gateway direto v1 e broker W002 no mesmo dataset descartável.

Executar somente dentro do contêiner broker da fixture W002, após a criação
dos ambientes. O script confere as labels antes de escrever no volume pessoal.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import sqlite3
import statistics
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

from apps.AetherDesk.files.broker_gateway import BrokerFileGateway
from apps.AetherDesk.files.gateway import ContainerFileGateway
from apps.AetherDesk.files.service import FileError
from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerClient
from apps.AetherDesk.runtime.docker import DockerEnvironmentBroker


def percentile(samples: list[float], percentage: float) -> float:
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentage)))
    return round(ordered[index], 2)


def main() -> None:
    data_dir = Path(os.environ['AETHERDESK_DATA_DIR'])
    identity = IdentityService(data_dir / 'identity.sqlite3', os.environ['AETHERDESK_BOOTSTRAP_TOKEN'])
    _, actor = identity.login('w002fixture', 'w002-fixture-password')
    account = identity.account(actor, actor.account_id)
    environment_id = account['environment_id']
    runtime = DockerEnvironmentBroker(os.environ['AETHERDESK_RUNTIME_IMAGE'])
    environment = runtime.state(actor.account_id, environment_id)
    if environment.state != 'running':
        raise RuntimeError('Fixture environment is not running')
    with closing(sqlite3.connect(data_dir / 'identity.sqlite3')) as db:
        other = db.execute("SELECT COUNT(*) FROM accounts WHERE username='w002other'").fetchone()[0]
    if other != 1:
        raise RuntimeError('Fixture accounts missing')

    # O runtime.state valida labels de owner/environment antes de obter o nome.
    seed = "from pathlib import Path; root=Path('/persist'); [(root / ('bench'+str(n))).mkdir(exist_ok=True) for n in (100,10000)]; [(root / ('bench'+str(n)) / ('item%05d.txt'%i)).touch() for n in (100,10000) for i in range(n)]"
    subprocess.run(['docker', 'exec', '--user', '10001:10001', environment.container_name,
                    'python3', '-c', seed], check=True, timeout=90)

    secret = base64.b64decode(os.environ['AETHERDESK_BROKER_SECRET_B64'])
    broker = BrokerClient(os.environ['AETHERDESK_BROKER_SOCKET'], secret)
    gateways = {
        'direct_v1': ContainerFileGateway(identity, runtime),
        'broker_w002': BrokerFileGateway(identity, broker),
    }
    print('AETHERDESK_DATASET_MANIFEST=' + json.dumps({
        'kernel': platform.release(), 'architecture': platform.machine(),
        'python': sys.version.split()[0], 'image': os.environ['AETHERDESK_RUNTIME_IMAGE'],
        'account_count': 2, 'measured_accounts': 1,
        'datasets': [100, 10_000], 'samples_per_path': 30,
        'order': 'alternating ABBA', 'cache': 'warm',
    }, sort_keys=True), flush=True)
    results = {}
    for count in (100, 10_000):
        path = f'/persist/bench{count}'
        samples = {name: [] for name in gateways}
        errors = {name: 0 for name in gateways}
        for gateway in gateways.values():
            assert len(gateway.call(actor, 'list', path)) == count
        # Blocos ABBA alternam a ordem, para reduzir viés de aquecimento.
        for block in range(15):
            order = ('direct_v1', 'broker_w002', 'broker_w002', 'direct_v1') if block % 2 == 0 else (
                'broker_w002', 'direct_v1', 'direct_v1', 'broker_w002')
            for name in order:
                started = time.perf_counter()
                try:
                    entries = gateways[name].call(actor, 'list', path)
                    if len(entries) != count:
                        raise AssertionError(f'{name}: expected {count}, got {len(entries)}')
                except Exception:
                    errors[name] += 1
                finally:
                    samples[name].append((time.perf_counter() - started) * 1000)
        results[str(count)] = {name: {'count': len(values), 'errors': errors[name],
            'p50_ms': percentile(values, .5), 'p95_ms': percentile(values, .95),
            'p99_ms': percentile(values, .99)} for name, values in samples.items()}
    print('AETHERDESK_DATASET_BENCHMARK=' + json.dumps(results, sort_keys=True), flush=True)
    if any(item['errors'] for dataset in results.values() for item in dataset.values()):
        raise RuntimeError('Dataset benchmark returned errors')
    if ':w002-fixture-' in os.environ['AETHERDESK_RUNTIME_IMAGE']:
        subprocess.run(['docker', 'exec', '--user', '10001:10001', environment.container_name,
                        'python3', '-c',
                        "from pathlib import Path; Path('/persist/bench10000/item10000.txt').touch()"],
                       check=True, timeout=30)
        try:
            gateways['broker_w002'].call(actor, 'list', '/persist/bench10000')
        except FileError as exc:
            if exc.code != 'TOO_LARGE':
                raise
        else:
            raise RuntimeError('Agent accepted more than 10,000 directory entries')
        print('AETHERDESK_FILE_LIST_LIMIT=ok', flush=True)


if __name__ == '__main__':
    main()

"""Measure synthetic Argon2 login under the W006 20/8 profile."""

from __future__ import annotations

import json
import platform
import sqlite3
import statistics
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from apps.AetherDesk.identity import IdentityService


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    return round(ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low])
                 * (position - low), 2)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aetherdesk-login-') as directory:
        password = 'fixture-password-123'
        service = IdentityService(Path(directory) / 'identity.sqlite3', 'fixture-bootstrap-token')
        service.bootstrap('fixture-bootstrap-token', 'login00', password)
        with sqlite3.connect(service.db_path) as db:
            password_hash = db.execute(
                "SELECT password_hash FROM accounts WHERE username='login00'").fetchone()[0]
            for index in range(1, 20):
                db.execute('''INSERT INTO accounts
                    (id,username,password_hash,role,state,environment_id,created_at)
                    VALUES(?,?,?,'member','active',?,?)''',
                    (str(uuid.uuid4()), f'login{index:02d}', password_hash,
                     str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()))
        users = [f'login{index:02d}' for index in range(8)]

        def attempt(username: str) -> float:
            start = time.perf_counter()
            _token, actor = service.login(username, password)
            assert actor.account_id
            return (time.perf_counter() - start) * 1000

        with ThreadPoolExecutor(max_workers=8) as pool:
            cold = list(pool.map(attempt, users))
            warm = []
            for _ in range(30):
                warm.extend(pool.map(attempt, users))
        print(json.dumps({
            'platform': platform.platform(), 'python': platform.python_version(),
            'profile': {'accounts': 20, 'active': 8, 'workers': 8,
                        'warm_samples_per_account': 30, 'algorithm': 'Argon2id',
                        'layer': 'IdentityService.login; no HTTP or Docker'},
            'cold_ms': {'p50': percentile(cold, .5), 'p95': percentile(cold, .95),
                        'p99': percentile(cold, .99)},
            'warm_ms': {'count': len(warm), 'p50': percentile(warm, .5),
                        'p95': percentile(warm, .95), 'p99': percentile(warm, .99),
                        'mean': round(statistics.mean(warm), 2)},
        }, sort_keys=True))


if __name__ == '__main__':
    main()

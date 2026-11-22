"""Amostra provisória de latência; não substitui orçamento no host Linux."""

import json
import os
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import psutil
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from launch import create_app


def summary(samples):
    ordered = sorted(samples)
    return {'samples': len(samples), 'p50_ms': round(statistics.median(ordered), 1),
            'p95_ms': round(ordered[int(0.95 * (len(ordered) - 1))], 1),
            'max_ms': round(max(ordered), 1)}


def main():
    with tempfile.TemporaryDirectory() as temp:
        keys = ('AETHERDESK_DATA_DIR', 'AETHERDESK_BOOTSTRAP_TOKEN',
                'AETHERDESK_CSRF_SECRET', 'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP')
        old = {key: os.environ.get(key) for key in keys}
        os.environ.update({'AETHERDESK_DATA_DIR': temp,
            'AETHERDESK_BOOTSTRAP_TOKEN': 'bootstrap-secret-long',
            'AETHERDESK_CSRF_SECRET': 'csrf-secret-long-enough-for-testing-12345',
            'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1'})
        resource = None
        try:
            with TestClient(create_app()) as client:
                client.post('/api/v1/bootstrap', json={'token': 'bootstrap-secret-long',
                    'username': 'admin', 'password': 'strong-admin-password'}).raise_for_status()
                client.post('/api/v1/login', json={'username': 'admin',
                    'password': 'strong-admin-password'}).raise_for_status()
                identity = IdentityService(Path(temp) / 'identity.sqlite3', 'bootstrap-secret-long')
                actor = identity.actor(client.cookies.get('aether_session'))
                account = identity.account(actor, actor.account_id)
                resource = DockerEnvironmentBroker._names(account['environment_id'])
                routes = {'desktop': '/api/v1/desktop/state', 'files': '/api/v1/files/list?path=%2Fpersist',
                          'metrics': '/api/v1/metrics/self'}
                values = {}
                for label, route in routes.items():
                    times = []
                    for _ in range(20):
                        start = time.perf_counter()
                        response = client.get(route)
                        response.raise_for_status()
                        times.append((time.perf_counter() - start) * 1000)
                    values[label] = summary(times)
                version = subprocess.run(['docker', 'version', '--format', '{{.Server.Version}}'],
                                         capture_output=True, text=True).stdout.strip()
                print(json.dumps({'environment': {'host_os': platform.platform(),
                    'docker_server': version, 'logical_cpus': psutil.cpu_count(),
                    'memory_bytes': psutil.virtual_memory().total}, 'routes': values}, indent=2))
        finally:
            if resource:
                container, volume = resource
                subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == '__main__':
    main()

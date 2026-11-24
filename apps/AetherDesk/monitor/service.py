"""Coleta atual sem confundir ausência de medição com zero."""

from __future__ import annotations

from datetime import datetime, timezone
from collections import deque
from threading import RLock
from time import monotonic

import docker
import psutil

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


class MetricsSource:
    def __init__(self, docker_client=None):
        self._owns_docker = docker_client is None
        self.docker = docker_client or docker.from_env()

    def close(self):
        if self._owns_docker:
            self.docker.close()

    def server(self):
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        io = psutil.disk_io_counters()
        return {
            'cpu_percent': psutil.cpu_percent(interval=None),
            'memory_bytes': memory.used, 'memory_limit_bytes': memory.total,
            'storage_bytes': disk.used, 'storage_limit_bytes': disk.total,
            'read_bytes': io.read_bytes if io else None,
            'write_bytes': io.write_bytes if io else None,
            'network_rx_bytes': network.bytes_recv if network else None,
            'network_tx_bytes': network.bytes_sent if network else None,
        }

    def environment(self, container_name: str):
        container = self.docker.containers.get(container_name)
        if container.status != 'running':
            return {'state': container.status, 'cpu_percent': None, 'memory_bytes': None,
                    'memory_limit_bytes': None, 'read_bytes': None, 'write_bytes': None,
                    'network_rx_bytes': None, 'network_tx_bytes': None}
        data = container.stats(stream=False)
        cpu = data.get('cpu_stats', {}).get('cpu_usage', {})
        prior = data.get('precpu_stats', {}).get('cpu_usage', {})
        current_total = cpu.get('total_usage', 0)
        prior_total = prior.get('total_usage', 0)
        current_system = data.get('cpu_stats', {}).get('system_cpu_usage', 0)
        prior_system = data.get('precpu_stats', {}).get('system_cpu_usage', 0)
        delta = current_total - prior_total
        system_delta = current_system - prior_system
        cores = data.get('cpu_stats', {}).get('online_cpus') or len(cpu.get('percpu_usage') or []) or 1
        blk = data.get('blkio_stats', {}).get('io_service_bytes_recursive') or []
        networks = data.get('networks') or {}
        return {
            'state': 'running',
            'cpu_percent': round(delta / system_delta * cores * 100, 2) if delta >= 0 and system_delta > 0 else None,
            'memory_bytes': data.get('memory_stats', {}).get('usage'),
            'memory_limit_bytes': data.get('memory_stats', {}).get('limit'),
            'read_bytes': sum(int(row.get('value', 0)) for row in blk if row.get('op', '').lower() == 'read'),
            'write_bytes': sum(int(row.get('value', 0)) for row in blk if row.get('op', '').lower() == 'write'),
            'network_rx_bytes': sum(int(row.get('rx_bytes', 0)) for row in networks.values()),
            'network_tx_bytes': sum(int(row.get('tx_bytes', 0)) for row in networks.values()),
        }


class MonitorService:
    def __init__(self, identity: IdentityService, runtime: DockerEnvironmentBroker,
                 source: MetricsSource | None = None, history_size: int = 30,
                 cache_seconds: float = 4.0):
        self.identity, self.runtime = identity, runtime
        self.source = source or MetricsSource()
        self.history = deque(maxlen=history_size)
        self.lock = RLock()
        self.cache_seconds = cache_seconds
        self.cache = {}

    def _environment_metrics(self, account_id: str, environment_id: str, container_name: str):
        if hasattr(self.source, 'environment_for'):
            return self.source.environment_for(account_id, environment_id)
        return self.source.environment(container_name)

    def _sample(self, category: str, reference: str, read, cache_state: str | None = None):
        key = (category, reference, cache_state)
        if cache_state == 'running' and self.cache_seconds > 0:
            with self.lock:
                cached = self.cache.get(key)
                if cached and monotonic() - cached[0] < self.cache_seconds:
                    return cached[1]
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            values = read()
            status = 'available'
        except Exception:
            values = {'cpu_percent': None, 'memory_bytes': None, 'memory_limit_bytes': None,
                      'storage_bytes': None, 'storage_limit_bytes': None, 'read_bytes': None,
                      'write_bytes': None, 'network_rx_bytes': None, 'network_tx_bytes': None}
            status = 'unavailable'
        sample = {'category': category, 'reference': reference, 'sampled_at': timestamp,
                'status': status, 'units': {'cpu_percent': '%', 'memory_bytes': 'B',
                'memory_limit_bytes': 'B', 'storage_bytes': 'B', 'storage_limit_bytes': 'B',
                'read_bytes': 'B', 'write_bytes': 'B', 'network_rx_bytes': 'B',
                'network_tx_bytes': 'B'}, 'values': values}
        if cache_state == 'running' and self.cache_seconds > 0:
            with self.lock:
                self.cache[key] = (monotonic(), sample)
        return sample

    def self(self, actor: ActorContext):
        self.identity.require(actor, 'metrics.self')
        account = self.identity.account(actor, actor.account_id)
        env = self.runtime.state(actor.account_id, account['environment_id'])
        sample = self._sample('environment', actor.account_id,
                              lambda: self._environment_metrics(actor.account_id, account['environment_id'], env.container_name) if env.state == 'running'
                              else {'state': env.state, 'cpu_percent': None, 'memory_bytes': None}, env.state)
        if env.state != 'running':
            sample['status'] = 'unavailable'
        with self.lock:
            self.history.append((actor.account_id, sample))
            recent = [entry for owner, entry in self.history if owner == actor.account_id]
        return {'current': sample, 'recent': recent}

    def server(self, actor: ActorContext, accounts: list[dict] | None = None):
        self.identity.require(actor, 'metrics.server')
        host = self._sample('server', 'host', self.source.server)
        shared = self._sample('shared', 'host-minus-containers', lambda: {})
        shared['status'] = 'unavailable'
        shared['values'] = {key: None for key in host['values']}
        if (accounts is not None and host['status'] == 'available' and
                'metrics.accounts' in self.identity.capabilities(actor)):
            environment_samples = self.accounts(actor, accounts)
            if all(row['sample']['status'] == 'available' for row in environment_samples):
                # CPU de contêiner e CPU do host usam denominadores distintos.
                # Só a memória permite um restante aproximado neste coletor.
                for key in ('memory_bytes',):
                    values = [row['sample']['values'].get(key) for row in environment_samples]
                    if host['values'].get(key) is not None and all(value is not None for value in values):
                        shared['values'][key] = max(0, host['values'][key] - sum(values))
                if any(value is not None for value in shared['values'].values()):
                    shared['status'] = 'partial'
        return {'server': host, 'shared': shared}

    def accounts(self, actor: ActorContext, accounts: list[dict]):
        self.identity.require(actor, 'metrics.accounts')
        results = []
        for account in sorted(accounts, key=lambda row: row['username'].casefold()):
            env = self.runtime.state(account['id'], account['environment_id'])
            sample = self._sample('environment', account['id'],
                            lambda owner=account['id'], eid=account['environment_id'], name=env.container_name: self._environment_metrics(owner, eid, name) if env.state == 'running'
                            else {'state': env.state, 'cpu_percent': None, 'memory_bytes': None}, env.state)
            if env.state != 'running':
                sample['status'] = 'unavailable'
            results.append({'account_id': account['id'], 'username': account['username'],
                            'sample': sample})
        return results

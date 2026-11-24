"""Mede request/idempotency/reconcile de workloads em SQLite local descartável."""

from __future__ import annotations

import json
import statistics
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.workloads.service import ApprovedTemplate, WorkloadService


class Runtime:
    def __init__(self):
        self.lock = threading.Lock()
        self.starts: dict[str, int] = {}

    def ensure(self, _owner, workload, _template, revision=None):
        with self.lock:
            self.starts[workload] = self.starts.get(workload, 0) + 1
        return 'running'

    def healthy(self, _owner, _workload):
        return True

    def stop(self, _owner, _workload):
        pass

    def remove(self, _owner, _workload):
        pass

    def remove_volume(self, _owner, _workload):
        pass

    def logs(self, _owner, _workload, _limit):
        return ''


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = Runtime()
        service = WorkloadService(Path(directory) / 'jobs.sqlite3', runtime,
            {'fixture': ApprovedTemplate('fixture', 'example/app@sha256:' + 'a' * 64,
                                          'b' * 64, 'c' * 64, True)},
            lambda _actor, _cap: None, lambda _actor: True)
        work = []
        for _ in range(20):
            actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            project = service.project(actor, 'benchmark')
            for index in range(5):
                work.append((actor, service.create(actor, project, f'api-{index}')))

        def one(item):
            actor, workload = item
            operation = str(uuid.uuid4())
            started = time.perf_counter()
            first = service.request(actor, workload, 'deploy', operation, 'fixture')
            repeated = service.request(actor, workload, 'deploy', operation, 'fixture')
            request_ms = (time.perf_counter() - started) * 1000
            assert first == repeated
            started = time.perf_counter()
            assert service.reconcile(workload)
            reconcile_ms = (time.perf_counter() - started) * 1000
            assert service.state(actor, workload)['observed'] == 'running'
            return request_ms, reconcile_ms

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as pool:
            samples = list(pool.map(one, work))
        wall_seconds = round(time.perf_counter() - started, 3)
        assert len(runtime.starts) == 100 and all(count == 1 for count in runtime.starts.values())
        requests = [sample[0] for sample in samples]
        reconciles = [sample[1] for sample in samples]
        print(json.dumps({'owners': 20, 'workloads': 100, 'parallel_workers': 8,
                          'fixture': 'SQLite temp + fake runtime; no Docker latency',
                          'wall_seconds': wall_seconds,
                          'request_ms': {'p50': percentile(requests, .5),
                                         'p95': percentile(requests, .95),
                                         'p99': percentile(requests, .99)},
                          'reconcile_ms': {'p50': percentile(reconciles, .5),
                                           'p95': percentile(reconciles, .95),
                                           'p99': percentile(reconciles, .99)},
                          'mean_request_ms': round(statistics.mean(requests), 3),
                          'unique_starts': len(runtime.starts)}))


if __name__ == '__main__':
    main()

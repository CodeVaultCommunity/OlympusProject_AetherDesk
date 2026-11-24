"""Benchmark reproduzível da árvore e busca com 10.000 arquivos descartáveis."""

import json
import platform
import statistics
import tempfile
import threading
import time
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.workspace.files import WorkspaceFiles
from apps.AetherDesk.workspace.index import WorkspaceIndex


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    return round(ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low), 2)


def measure(operation, samples):
    durations = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        durations.append((time.perf_counter() - started) * 1000)
    return {'samples': samples, 'p50_ms': percentile(durations, .5),
            'p95_ms': percentile(durations, .95), 'p99_ms': percentile(durations, .99),
            'mean_ms': round(statistics.mean(durations), 2)}


def main():
    with tempfile.TemporaryDirectory(prefix='aetherdesk-w003-benchmark-') as directory:
        root = Path(directory) / 'workspace'
        root.mkdir()
        for index in range(10_000):
            (root / f'file-{index:05d}.txt').write_text(f'record {index:05d}\n', encoding='utf-8')
        actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        service = WorkspaceFiles(root, actor.account_id, lambda _actor, _cap: None, lambda _actor: True)
        index = WorkspaceIndex(root, Path(directory) / 'index.sqlite3', actor.account_id,
                               lambda _actor, _cap: None, lambda _actor: True)
        service.list_tree(actor, limit=200)
        started = time.perf_counter()
        indexed = index.rebuild(actor, threading.Event())
        index_build_ms = round((time.perf_counter() - started) * 1000, 2)
        assert index.search(actor, 'record 09999')['matches'][0]['path'] == 'file-09999.txt'
        report = {
            'platform': platform.platform(), 'python': platform.python_version(),
            'dataset': {'files': 10_000, 'bytes_per_file': (root / 'file-00000.txt').stat().st_size,
                        'storage': str(root)},
            'list_first_page': measure(lambda: service.list_tree(actor, limit=200), 30),
            'index_build': {**indexed, 'milliseconds': index_build_ms},
            'indexed_search_last_file': measure(lambda: index.search(actor, 'record 09999'), 30),
            'scan_search_last_file': measure(lambda: service.search(actor, 'record 09999', threading.Event()), 3),
        }
        print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()

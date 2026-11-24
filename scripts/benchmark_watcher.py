"""Baseline inotify com 10.000 arquivos e alterações pontuais."""

from __future__ import annotations

import json
import resource
import tempfile
import time
from pathlib import Path

from apps.AetherDesk.workspace.watcher import LinuxWatcher


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index in range(10_000):
            (root / f'f{index:05d}.txt').write_bytes(b'fixture\n')
        started = time.perf_counter()
        with LinuxWatcher(root) as watcher:
            startup_ms = (time.perf_counter() - started) * 1000
            samples = []
            for index in range(100):
                name = f'f{index:05d}.txt'
                started = time.perf_counter()
                (root / name).write_bytes(f'changed {index}\n'.encode())
                events = watcher.next_events(timeout=2)
                if not any(event['path'] == name for event in events):
                    raise RuntimeError('WATCH_EVENT_MISSING')
                samples.append((time.perf_counter() - started) * 1000)
        print(json.dumps({'files': 10_000, 'samples': 100,
                          'environment': 'Linux container fixture, tmpfs /tmp',
                          'startup_ms': round(startup_ms, 3),
                          'event_ms': {'p50': percentile(samples, .5),
                                       'p95': percentile(samples, .95),
                                       'p99': percentile(samples, .99)},
                          'maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))


if __name__ == '__main__':
    main()

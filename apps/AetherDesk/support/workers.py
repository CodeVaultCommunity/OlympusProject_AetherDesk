"""Execução de jobs de outbox com lease renovável e fencing."""

from __future__ import annotations

import threading

from .leases import LeaseStore


class LeasedJob:
    def __init__(self, store: LeaseStore, name: str, ttl_seconds: float = 45):
        self.store, self.name, self.ttl_seconds = store, name, ttl_seconds

    def run(self, operation):
        lease = self.store.acquire(self.name, self.ttl_seconds)
        if lease is None:
            return False
        stopped = threading.Event()
        lost = threading.Event()

        def heartbeat():
            current = lease
            while not stopped.wait(self.ttl_seconds / 3):
                renewed = self.store.renew(current, self.ttl_seconds)
                if renewed is None:
                    lost.set()
                    return
                current = renewed

        worker = threading.Thread(target=heartbeat, name=f'{self.name}-heartbeat', daemon=True)
        worker.start()
        try:
            operation(lambda: not lost.is_set() and self.store.valid(lease))
            return True
        finally:
            stopped.set()
            worker.join(timeout=5)
            self.store.release(lease)

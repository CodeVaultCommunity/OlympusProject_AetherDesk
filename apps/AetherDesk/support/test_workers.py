import multiprocessing
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

from .leases import Lease, LeaseStore
from .workers import LeasedJob


def _crash_with_lease(path: str, ready) -> None:
    lease = LeaseStore(path).acquire('events', ttl_seconds=0.4)
    if lease is None:
        os._exit(2)
    ready.set()
    os._exit(0)


class WorkerTests(unittest.TestCase):
    def test_crashed_process_expires_and_stale_owner_is_fenced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'jobs.sqlite3'
            context = multiprocessing.get_context('spawn')
            ready = context.Event()
            process = context.Process(target=_crash_with_lease, args=(str(path), ready))
            process.start()
            try:
                self.assertTrue(ready.wait(5))
                with closing(sqlite3.connect(path)) as db:
                    owner, fence, expiry = db.execute(
                        "SELECT owner,fence,expires_at FROM worker_leases WHERE name='events'"
                    ).fetchone()
                stale = Lease('events', owner, fence, expiry)
                store = LeaseStore(path)
                self.assertIsNone(store.acquire('events', ttl_seconds=1))
                process.join(timeout=5)
                self.assertEqual(process.exitcode, 0)
                time.sleep(max(0, expiry - time.time()) + 0.02)
                successor = store.acquire('events', ttl_seconds=1)
                self.assertIsNotNone(successor)
                self.assertEqual(successor.fence, fence + 1)
                self.assertFalse(store.release(stale))
                self.assertFalse(store.valid(stale))
                self.assertTrue(store.valid(successor))
                self.assertTrue(store.release(successor))
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)

    def test_concurrent_workers_run_one_logical_job(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'jobs.sqlite3'
            first = LeasedJob(LeaseStore(path), 'events')
            second = LeasedJob(LeaseStore(path), 'events')
            started = threading.Event()
            release = threading.Event()
            calls = []

            def long_job(guard):
                calls.append('first')
                started.set()
                self.assertTrue(guard())
                self.assertTrue(release.wait(5))

            thread = threading.Thread(target=lambda: first.run(long_job))
            thread.start()
            self.assertTrue(started.wait(5))
            try:
                self.assertFalse(second.run(lambda _guard: calls.append('second')))
            finally:
                release.set()
                thread.join(timeout=5)
            self.assertEqual(calls, ['first'])
            self.assertTrue(second.run(lambda guard: self.assertTrue(guard())))


if __name__ == '__main__':
    unittest.main()

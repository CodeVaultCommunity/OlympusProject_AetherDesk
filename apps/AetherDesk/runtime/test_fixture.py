"""Broker real para testes Linux descartáveis; dados e socket ficam na fixture."""

import base64
import os
import subprocess
import sys
import time
from pathlib import Path


class BrokerFixture:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.process = None
        self.previous = {}

    def start(self):
        values = {
            'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(os.urandom(48)).decode(),
            'AETHERDESK_BROKER_SOCKET': str(self.directory / 'broker.sock'),
            'AETHERDESK_BROKER_AUDIT_LOG': str(self.directory / 'broker-audit.log'),
            'AETHERDESK_RUNTIME_IMAGE': 'aetherdesk-files:w003',
        }
        self.previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        self.process = subprocess.Popen(
            [sys.executable, '-B', '-m', 'apps.AetherDesk.runtime.broker_main'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ.copy())
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if (self.directory / 'broker.sock').exists():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        self.stop()
        raise RuntimeError('broker de teste não iniciou')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.previous = {}

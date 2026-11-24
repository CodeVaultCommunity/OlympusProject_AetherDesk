"""Força rotação do log apenas no broker descartável da W002."""

from __future__ import annotations

import os

from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError


def main() -> None:
    assert os.environ.get('AETHERDESK_DATA_DIR') == '/data'
    client = BrokerClient(os.environ['AETHERDESK_BROKER_SOCKET'], b'0' * 32)
    account = '00000000-0000-4000-8000-000000000001'
    environment = '00000000-0000-4000-8000-000000000002'
    for _ in range(12_000):
        try:
            client.call('state', account, environment)
        except BrokerError as exc:
            if str(exc) != 'UNAUTHENTICATED':
                raise
        else:
            raise AssertionError('Broker accepted invalid HMAC')
    print('AETHERDESK_AUDIT_ROTATION_REQUESTS=12000', flush=True)


if __name__ == '__main__':
    main()

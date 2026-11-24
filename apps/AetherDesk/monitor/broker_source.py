"""Métricas de ambiente pelo broker; host por psutil sem abrir Docker no ASGI."""

from apps.AetherDesk.runtime.broker_ipc import BrokerClient
from .service import MetricsSource


class BrokerMetricsSource:
    def __init__(self, broker: BrokerClient):
        self.broker = broker
        self.host = MetricsSource(docker_client=object())

    def server(self):
        return self.host.server()

    def environment_for(self, account_id: str, environment_id: str):
        return self.broker.call('environment_metrics', account_id, environment_id)

"""Gateway de arquivos via broker sem subprocesso Docker no serviço web."""

import base64

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError
from .service import FileError


class BrokerFileGateway:
    def __init__(self, identity: IdentityService, broker: BrokerClient):
        self.identity, self.broker = identity, broker

    def call(self, actor: ActorContext, operation: str, path: str, **parameters):
        self.identity.require(actor, 'files.read' if operation in ('list', 'metadata', 'read') else 'files.write')
        account = self.identity.account(actor, actor.account_id)
        try:
            return self.broker.call('file_agent', actor.account_id, account['environment_id'],
                                    {'operation': operation, 'path': path, **parameters})
        except BrokerError as exc:
            raise FileError(str(exc)) from exc

    def read(self, actor: ActorContext, path: str):
        data = self.call(actor, 'read', path)
        return base64.b64decode(data['content']), data['revision']

    def write(self, actor: ActorContext, path: str, data: bytes,
              revision: str | None = None, replace: bool = False):
        return self.call(actor, 'write', path, content=base64.b64encode(data).decode(),
                         revision=revision, replace=replace)['revision']

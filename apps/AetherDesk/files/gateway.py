"""Chama o agente de arquivos apenas no contêiner da conta autenticada."""

import base64
import json
import subprocess

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from .service import FileError


class ContainerFileGateway:
    def __init__(self, identity: IdentityService, runtime: DockerEnvironmentBroker):
        self.identity, self.runtime = identity, runtime

    def call(self, actor: ActorContext, operation: str, path: str, **parameters):
        self.identity.require(actor, 'files.read' if operation in ('list', 'metadata', 'read') else 'files.write')
        account = self.identity.account(actor, actor.account_id)
        environment = self.runtime.ensure(actor.account_id, account['environment_id'])
        request = {'operation': operation, 'path': path, **parameters}
        encoded = json.dumps(request, separators=(',', ':')).encode()
        if len(encoded) > 12 * 1024 * 1024:
            raise FileError('TOO_LARGE')
        process = subprocess.run(['docker', 'exec', '-i', '--user', '10001:10001',
            environment.container_name, 'python3', '/opt/aetherdesk/file_agent.py'],
            input=encoded, capture_output=True, timeout=30)
        try:
            result = json.loads(process.stdout)
        except ValueError as exc:
            raise FileError('UNAVAILABLE') from exc
        if process.returncode or 'error' in result:
            raise FileError(result.get('error', 'UNAVAILABLE'))
        return result['data']

    def read(self, actor: ActorContext, path: str):
        data = self.call(actor, 'read', path)
        return base64.b64decode(data['content']), data['revision']

    def write(self, actor: ActorContext, path: str, data: bytes, revision: str | None = None,
              replace: bool = False):
        return self.call(actor, 'write', path, content=base64.b64encode(data).decode(),
                         revision=revision, replace=replace)['revision']

"""Adapter Docker de broker para templates por digest, sem flags do cliente."""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from collections.abc import Callable, Sequence

from .service import ApprovedTemplate, WorkloadError


def _runner(args: Sequence[str]):
    return subprocess.run(['docker', *args], capture_output=True, text=True,
                          encoding='utf-8', timeout=30, check=False)


class DockerWorkloadRuntime:
    def __init__(self, runner: Callable = _runner):
        self.runner = runner

    @staticmethod
    def _names(workload_id: str) -> tuple[str, str]:
        try:
            suffix = uuid.UUID(workload_id).hex
        except (TypeError, ValueError) as exc:
            raise WorkloadError('INVALID_WORKLOAD_ID') from exc
        return 'aetherdesk-w-' + suffix, 'aetherdesk-wv-' + suffix

    def _docker(self, *args: str, missing_ok: bool = False) -> str:
        try:
            result = self.runner(args)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkloadError('RUNTIME_UNAVAILABLE') from exc
        if result.returncode:
            if missing_ok and ('No such container' in result.stderr or 'No such object' in result.stderr or
                               'not found' in result.stderr.lower()):
                return ''
            raise WorkloadError('RUNTIME_UNAVAILABLE')
        return result.stdout.strip()

    def _inspect(self, owner_id: str, workload_id: str) -> tuple[str, str, str] | None:
        name, _ = self._names(workload_id)
        try:
            owner_id = str(uuid.UUID(owner_id))
        except (TypeError, ValueError) as exc:
            raise WorkloadError('INVALID_OWNER') from exc
        raw = self._docker('container', 'inspect', '--format',
            '{{.State.Status}}|{{index .Config.Labels "aetherdesk.owner_id"}}|{{index .Config.Labels "aetherdesk.workload_id"}}|{{index .Config.Labels "aetherdesk.template"}}|{{.Config.Image}}',
            name, missing_ok=True)
        if not raw:
            return None
        parts = raw.split('|')
        if len(parts) != 5 or parts[1:3] != [owner_id, workload_id]:
            raise WorkloadError('OWNERSHIP_MISMATCH')
        return parts[0], parts[3], parts[4]

    def _verify_volume(self, owner_id: str, workload_id: str, volume: str) -> None:
        raw = self._docker('volume', 'inspect', '--format',
            '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', volume)
        if raw != f'{owner_id}|{workload_id}':
            raise WorkloadError('OWNERSHIP_MISMATCH')

    def _network(self, owner_id: str, workload_id: str, create: bool = False) -> tuple[str, dict] | None:
        name = 'aetherdesk-wn-' + uuid.UUID(workload_id).hex
        raw = self._docker('network', 'inspect', name, missing_ok=True)
        if not raw and create:
            try:
                self._docker('network', 'create', '--internal', '--driver', 'bridge',
                             '--label', f'aetherdesk.owner_id={owner_id}',
                             '--label', f'aetherdesk.workload_id={workload_id}', name)
            except WorkloadError:
                pass  # corrida com outro reconciliador; inspecionar sempre.
            raw = self._docker('network', 'inspect', name)
        if not raw:
            return None
        try:
            details = json.loads(raw)[0]
            labels = details['Labels']
            if (labels.get('aetherdesk.owner_id') != owner_id or
                    labels.get('aetherdesk.workload_id') != workload_id or
                    not details['Internal'] or details['Driver'] != 'bridge'):
                raise WorkloadError('OWNERSHIP_MISMATCH')
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise WorkloadError('RUNTIME_UNAVAILABLE') from exc
        return name, details

    def ensure(self, owner_id: str, workload_id: str, template: ApprovedTemplate,
               revision: int | None = None) -> str:
        if revision is not None and (type(revision) is not int or revision < 1):
            raise WorkloadError('INVALID_REVISION')
        return self._ensure(owner_id, workload_id, template, None, revision)

    def ensure_secrets(self, owner_id: str, workload_id: str, template: ApprovedTemplate,
                       secrets: dict[str, bytes], revision: int) -> str:
        if (type(secrets) is not dict or not secrets or len(secrets) > 16 or
                type(revision) is not int or revision < 1 or not template.command or
                any(not re.fullmatch(r'[a-z][a-z0-9_]{0,40}', name) or type(value) is not bytes or
                    len(value) > 65536 for name, value in secrets.items()) or
                sum(map(len, secrets.values())) > 1024 * 1024):
            raise WorkloadError('INVALID_SECRET_REFS')
        return self._ensure(owner_id, workload_id, template, secrets, revision)

    def _ensure(self, owner_id: str, workload_id: str, template: ApprovedTemplate,
                secrets: dict[str, bytes] | None, revision: int | None) -> str:
        template.validate()
        name, volume = self._names(workload_id)
        existing = self._inspect(owner_id, workload_id)
        labels = json.loads(self._docker('container', 'inspect', name))[0]['Config']['Labels'] if existing else {}
        secret_label = labels.get('aetherdesk.secrets_revision')
        revision_label = labels.get('aetherdesk.revision')
        expected_label = str(revision) if secrets else None
        if existing and (existing[1] != template.name or existing[2] != template.image or
                         secret_label != expected_label or
                         revision_label != (str(revision) if revision is not None else None)):
            self.stop(owner_id, workload_id)
            self._docker('container', 'rm', name)
            existing = None
        if existing:
            if existing[0] != 'running':
                self._docker('container', 'start', name)
            return 'running'
        # Imagem deve estar presente localmente: nenhuma busca implícita no registry.
        self._docker('image', 'inspect', template.image)
        self._docker('volume', 'create', '--label', f'aetherdesk.owner_id={owner_id}',
                     '--label', f'aetherdesk.workload_id={workload_id}', volume)
        self._verify_volume(owner_id, workload_id, volume)
        network = self._network(owner_id, workload_id, create=True) if template.port else None
        health_args = ('--health-cmd', template.health_command,
                       '--health-interval', '1s', '--health-retries', '2') if template.health_command else ()
        secret_args = ('--tmpfs', '/run/secrets:rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=10001,gid=10001',
                       '--label', f'aetherdesk.secrets_revision={revision}',
                       '--entrypoint', '/bin/sh') if secrets else ()
        revision_args = ('--label', f'aetherdesk.revision={revision}') if revision is not None else ()
        launch = ('-c', 'while [ ! -f /run/secrets/.ready ]; do sleep .1; done; exec "$@"',
                  '--', *template.command) if secrets else template.command
        command = ('run', '--detach', '--pull', 'never', '--name', name,
                   '--network', network[0] if network else 'none', '--read-only', '--user', '10001:10001',
                   '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--pids-limit', '128', '--memory', '512m', '--cpus', '1',
                   '--log-driver', 'local', '--log-opt', 'max-size=1m',
                   '--log-opt', 'max-file=2',
                   '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
                   '--mount', f'type=volume,source={volume},target=/data',
                   '--label', f'aetherdesk.owner_id={owner_id}',
                   '--label', f'aetherdesk.workload_id={workload_id}',
                   '--label', f'aetherdesk.template={template.name}',
                   *health_args, *revision_args, *secret_args, template.image, *launch)
        try:
            self._docker(*command)
        except WorkloadError:
            # Corrida entre workers: aceitar somente nome e labels idênticos.
            recovered = self._inspect(owner_id, workload_id)
            if not recovered or recovered[1] != template.name:
                raise
        if secrets:
            try:
                for secret_name, value in sorted(secrets.items()):
                    self._secret_exec(name, 'umask 077; cat > "$1"',
                                      '/run/secrets/' + secret_name, data=value)
                self._secret_exec(name, 'touch /run/secrets/.ready')
            except WorkloadError:
                self._docker('container', 'rm', '-f', name)
                raise
        return 'running'

    @staticmethod
    def _secret_exec(container_name: str, script: str, path: str | None = None,
                     data: bytes = b'') -> None:
        command = ['docker', 'exec', '-i', '--user', '10001:10001', container_name,
                   'sh', '-c', script, '--']
        if path:
            command.append(path)
        try:
            result = subprocess.run(command, input=data, capture_output=True,
                                    timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkloadError('SECRET_INJECTION_FAILED') from exc
        if result.returncode:
            raise WorkloadError('SECRET_INJECTION_FAILED')

    def state(self, owner_id: str, workload_id: str) -> str:
        existing = self._inspect(owner_id, workload_id)
        return existing[0] if existing else 'absent'

    def healthy(self, owner_id: str, workload_id: str) -> bool:
        if self.state(owner_id, workload_id) != 'running':
            return False
        name, _ = self._names(workload_id)
        deadline = time.monotonic() + 12
        while True:
            health = self._docker('container', 'inspect', '--format',
                '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', name)
            if health in ('none', 'healthy'):
                return True
            if health == 'unhealthy' or time.monotonic() >= deadline:
                return False
            time.sleep(.5)

    def stop(self, owner_id: str, workload_id: str) -> None:
        existing = self._inspect(owner_id, workload_id)
        if existing and existing[0] == 'running':
            self._docker('container', 'stop', '--time', '5', self._names(workload_id)[0])

    def remove(self, owner_id: str, workload_id: str) -> None:
        existing = self._inspect(owner_id, workload_id)
        if existing:
            self.stop(owner_id, workload_id)
            self._docker('container', 'rm', self._names(workload_id)[0])
        network = self._network(owner_id, workload_id)
        if network:
            self._docker('network', 'rm', network[0])

    def remove_volume(self, owner_id: str, workload_id: str) -> None:
        if self._inspect(owner_id, workload_id) is not None:
            raise WorkloadError('WORKLOAD_STILL_PRESENT')
        _, volume = self._names(workload_id)
        raw = self._docker('volume', 'inspect', '--format',
            '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}',
            volume, missing_ok=True)
        if raw:
            if raw != f'{owner_id}|{workload_id}':
                raise WorkloadError('OWNERSHIP_MISMATCH')
            self._docker('volume', 'rm', volume)

    def logs(self, owner_id: str, workload_id: str, limit: int) -> str:
        if self._inspect(owner_id, workload_id) is None:
            raise WorkloadError('WORKLOAD_NOT_FOUND')
        return self._docker('container', 'logs', '--tail', '100', self._names(workload_id)[0])[:limit]

    def metrics(self, owner_id: str, workload_id: str) -> dict:
        if self._inspect(owner_id, workload_id) is None:
            raise WorkloadError('WORKLOAD_NOT_FOUND')
        raw = self._docker('stats', '--no-stream', '--format',
                           '{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.PIDs}}',
                           self._names(workload_id)[0])
        values = raw.split('|')
        if len(values) != 4:
            raise WorkloadError('RUNTIME_UNAVAILABLE')
        return dict(zip(('cpu', 'memory', 'network', 'pids'), values))

    def proxy_route(self, owner_id: str, workload_id: str, port: int):
        from .proxy_policy import ProxyRoute, authorize_route
        if type(port) is not int or not 1 <= port <= 65535:
            raise WorkloadError('INVALID_PORT')
        if self._inspect(owner_id, workload_id) is None:
            raise WorkloadError('WORKLOAD_NOT_FOUND')
        network = self._network(owner_id, workload_id)
        if network is None:
            raise WorkloadError('ROUTE_DISABLED')
        name, details = network
        raw = self._docker('container', 'inspect', self._names(workload_id)[0])
        container = json.loads(raw)[0]
        ip = container['NetworkSettings']['Networks'][name]['IPAddress']
        cidr = details['IPAM']['Config'][0]['Subnet']
        hostname = uuid.UUID(workload_id).hex[:12] + '.apps.local'
        route = ProxyRoute(owner_id, workload_id, hostname, port, ip, cidr)
        authorize_route(route, owner_id=owner_id, workload_id=workload_id,
                        host_header=hostname, current_container_ip=ip)
        return route

    def container_ip(self, owner_id: str, workload_id: str) -> str:
        route = self.proxy_route(owner_id, workload_id, 1)
        return route.container_ip

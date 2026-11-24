import json
import os
import subprocess
import time
import unittest
import uuid

from .docker_runtime import DockerWorkloadRuntime
from .service import ApprovedTemplate, WorkloadError
from .service import WorkloadService
from apps.AetherDesk.identity import ActorContext
from pathlib import Path
import tempfile


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True,
                          timeout=30, check=False)


def await_secret_output(container: str, expected: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = docker('exec', container, 'cat', '/tmp/output')
        if result.returncode == 0 and result.stdout.strip() == expected:
            return
        time.sleep(.1)
    raise AssertionError(f'secret output did not reach expected revision: {expected!r}')


@unittest.skipUnless(os.getenv('AETHERDESK_DOCKER_TEST') == '1', 'fixture Docker Linux descartável')
class DockerWorkloadTests(unittest.TestCase):
    def test_revision_change_recreates_once_and_preserves_volume(self):
        image_result = docker('image', 'inspect', '--format', '{{index .RepoDigests 0}}', 'python:3.13-slim')
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        owner, workload = str(uuid.uuid4()), str(uuid.uuid4())
        runtime = DockerWorkloadRuntime()
        name, volume = runtime._names(workload)
        template = ApprovedTemplate('revision_fixture', image_result.stdout.strip(), 'a' * 64,
                                    'b' * 64, True, ('sleep', '60'))
        try:
            runtime.ensure(owner, workload, template, revision=1)
            first = docker('container', 'inspect', '--format', '{{.Id}}', name).stdout.strip()
            runtime.ensure(owner, workload, template, revision=1)
            self.assertEqual(docker('container', 'inspect', '--format', '{{.Id}}', name).stdout.strip(), first)
            runtime.ensure(owner, workload, template, revision=2)
            self.assertNotEqual(docker('container', 'inspect', '--format', '{{.Id}}', name).stdout.strip(), first)
            self.assertEqual(docker('volume', 'inspect', '--format',
                '{{index .Labels "aetherdesk.owner_id"}}', volume).stdout.strip(), owner)
        finally:
            metadata = docker('container', 'inspect', '--format',
                '{{index .Config.Labels "aetherdesk.owner_id"}}|{{index .Config.Labels "aetherdesk.workload_id"}}', name)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('container', 'rm', '-f', name)
            metadata = docker('volume', 'inspect', '--format',
                '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', volume)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('volume', 'rm', volume)

    def test_secret_bytes_enter_only_private_tmpfs_and_rotate_by_revision(self):
        image_result = docker('image', 'inspect', '--format', '{{index .RepoDigests 0}}', 'python:3.13-slim')
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        owner, workload = str(uuid.uuid4()), str(uuid.uuid4())
        runtime = DockerWorkloadRuntime()
        name, volume = runtime._names(workload)
        template = ApprovedTemplate('secret_fixture', image_result.stdout.strip(), 'a' * 64,
            'b' * 64, True, ('sh', '-c', 'cat /run/secrets/token > /tmp/output; sleep 60'))
        try:
            self.assertEqual(runtime.ensure_secrets(owner, workload, template,
                                                    {'token': b'fixture-secret-1'}, 2), 'running')
            inspect = json.loads(docker('container', 'inspect', name).stdout)[0]
            self.assertIn('/run/secrets', inspect['HostConfig']['Tmpfs'])
            self.assertFalse(any('fixture-secret-1' in part for part in inspect['Config']['Env']))
            self.assertNotIn('fixture-secret-1', json.dumps(inspect['Config']))
            self.assertFalse(any(mount.get('Type') == 'bind' for mount in inspect['Mounts']))
            await_secret_output(name, 'fixture-secret-1')
            self.assertEqual(runtime.ensure_secrets(owner, workload, template,
                                                    {'token': b'fixture-secret-2'}, 3), 'running')
            await_secret_output(name, 'fixture-secret-2')
        finally:
            metadata = docker('container', 'inspect', '--format',
                '{{index .Config.Labels "aetherdesk.owner_id"}}|{{index .Config.Labels "aetherdesk.workload_id"}}', name)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('container', 'rm', '-f', name)
            metadata = docker('volume', 'inspect', '--format',
                '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', volume)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('volume', 'rm', volume)

    def test_routed_container_uses_private_internal_network_without_host_port(self):
        image_result = docker('image', 'inspect', '--format', '{{index .RepoDigests 0}}', 'python:3.13-slim')
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        owner, workload = str(uuid.uuid4()), str(uuid.uuid4())
        runtime = DockerWorkloadRuntime()
        name, volume = runtime._names(workload)
        network = 'aetherdesk-wn-' + uuid.UUID(workload).hex
        template = ApprovedTemplate('routed', image_result.stdout.strip(), 'a' * 64,
                                    'b' * 64, True, ('sleep', '60'), port=8000)
        try:
            runtime.ensure(owner, workload, template)
            route = runtime.proxy_route(owner, workload, 8000)
            self.assertEqual(route.owner_id, owner)
            self.assertEqual(route.hostname, uuid.UUID(workload).hex[:12] + '.apps.local')
            details = json.loads(docker('container', 'inspect', name).stdout)[0]
            self.assertEqual(details['HostConfig']['NetworkMode'], network)
            self.assertEqual(details['NetworkSettings']['Ports'], {})
            network_details = json.loads(docker('network', 'inspect', network).stdout)[0]
            self.assertTrue(network_details['Internal'])
            with self.assertRaisesRegex(WorkloadError, 'OWNERSHIP_MISMATCH'):
                runtime.proxy_route(str(uuid.uuid4()), workload, 8000)
        finally:
            metadata = docker('container', 'inspect', '--format',
                '{{index .Config.Labels "aetherdesk.owner_id"}}|{{index .Config.Labels "aetherdesk.workload_id"}}', name)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('container', 'rm', '-f', name)
            metadata = docker('network', 'inspect', '--format',
                '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', network)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('network', 'rm', network)
            metadata = docker('volume', 'inspect', '--format',
                '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', volume)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('volume', 'rm', volume)

    def test_approved_container_is_isolated_and_ownership_checked(self):
        image_result = docker('image', 'inspect', '--format', '{{index .RepoDigests 0}}', 'python:3.13-slim')
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        image = image_result.stdout.strip()
        self.assertIn('@sha256:', image)
        owner, workload = str(uuid.uuid4()), str(uuid.uuid4())
        runtime = DockerWorkloadRuntime()
        template = ApprovedTemplate('fixture', image, 'a' * 64, 'b' * 64, True, ('sleep', '60'))
        name, volume = runtime._names(workload)
        try:
            self.assertEqual(runtime.ensure(owner, workload, template), 'running')
            self.assertEqual(runtime.ensure(owner, workload, template), 'running')
            self.assertTrue(runtime.healthy(owner, workload))
            inspect = docker('container', 'inspect', name)
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            details = json.loads(inspect.stdout)[0]
            host = details['HostConfig']
            self.assertFalse(host['Privileged'])
            self.assertTrue(host['ReadonlyRootfs'])
            self.assertEqual(host['NetworkMode'], 'none')
            self.assertIn('ALL', host['CapDrop'])
            self.assertEqual(host['LogConfig']['Type'], 'local')
            self.assertEqual(host['LogConfig']['Config']['max-size'], '1m')
            self.assertEqual(details['Config']['User'], '10001:10001')
            self.assertFalse(any(mount.get('Type') == 'bind' for mount in details['Mounts']))
            self.assertIn('cpu', runtime.metrics(owner, workload))
            with self.assertRaisesRegex(WorkloadError, 'OWNERSHIP_MISMATCH'):
                runtime.stop(str(uuid.uuid4()), workload)
            with self.assertRaisesRegex(WorkloadError, 'OWNERSHIP_MISMATCH'):
                runtime.metrics(str(uuid.uuid4()), workload)
        finally:
            metadata = docker('container', 'inspect', '--format',
                '{{index .Config.Labels "aetherdesk.owner_id"}}|{{index .Config.Labels "aetherdesk.workload_id"}}', name)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('container', 'rm', '-f', name)
            metadata = docker('volume', 'inspect', '--format',
                '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', volume)
            if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                docker('volume', 'rm', volume)

    def test_real_health_failure_rolls_back_to_previous_digest(self):
        image_result = docker('image', 'inspect', '--format', '{{index .RepoDigests 0}}', 'python:3.13-slim')
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        image = image_result.stdout.strip()
        owner = str(uuid.uuid4())
        actor = ActorContext(owner, str(uuid.uuid4()), 'member', 1)
        runtime = DockerWorkloadRuntime()
        with tempfile.TemporaryDirectory() as directory:
            service = WorkloadService(Path(directory) / 'workloads.sqlite3', runtime,
                {'stable': ApprovedTemplate('stable', image, 'a' * 64, 'b' * 64, True,
                                            ('sleep', '60'), 'exit 0'),
                 'broken': ApprovedTemplate('broken', image, 'a' * 64, 'b' * 64, True,
                                            ('sleep', '60'), 'exit 1')},
                lambda _actor, _cap: None, lambda _actor: True)
            project = service.project(actor, 'fixture')
            workload = service.create(actor, project, 'api')
            name, volume = runtime._names(workload)
            try:
                service.request(actor, workload, 'deploy', str(uuid.uuid4()), 'stable')
                self.assertTrue(service.reconcile(workload))
                self.assertEqual(service.state(actor, workload)['observed'], 'running')
                service.request(actor, workload, 'deploy', str(uuid.uuid4()), 'broken')
                self.assertTrue(service.reconcile(workload))
                state = service.state(actor, workload)
                self.assertEqual((state['observed'], state['template']), ('rolled_back', 'stable'))
                self.assertEqual(runtime._inspect(owner, workload)[1], 'stable')
                self.assertTrue(runtime.healthy(owner, workload))
            finally:
                metadata = docker('container', 'inspect', '--format',
                    '{{index .Config.Labels "aetherdesk.owner_id"}}|{{index .Config.Labels "aetherdesk.workload_id"}}', name)
                if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                    docker('container', 'rm', '-f', name)
                metadata = docker('volume', 'inspect', '--format',
                    '{{index .Labels "aetherdesk.owner_id"}}|{{index .Labels "aetherdesk.workload_id"}}', volume)
                if metadata.returncode == 0 and metadata.stdout.strip() == f'{owner}|{workload}':
                    docker('volume', 'rm', volume)

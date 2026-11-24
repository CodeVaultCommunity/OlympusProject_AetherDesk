import io
import os
import subprocess
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from .build import BuildService, DockerImageBuilder
from .service import WorkloadError


class Builder:
    def __init__(self):
        self.calls = []
        self.removed = []

    def build(self, owner, build_id, base, context):
        self.calls.append((owner, build_id, base, context))
        return 'sha256:' + 'c' * 64

    def remove(self, owner, image):
        self.removed.append((owner, image))


class Scanner:
    def __init__(self):
        self.high = 0

    def scan(self, image):
        return {'subject': image, 'critical': 0, 'high': self.high}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.other = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.owner_root = self.root / self.actor.account_id
        self.owner_root.mkdir()
        (self.owner_root / 'app.txt').write_bytes(b'safe\n')
        self.builder, self.scanner = Builder(), Scanner()
        self.service = BuildService(self.root / 'build.sqlite3', self.root, self.builder,
            self.scanner, b'k' * 32, lambda _actor, _cap: None, lambda _actor: True)
        self.base = 'registry.example/base@sha256:' + 'a' * 64

    def test_fixed_dockerfile_scan_gate_idempotency_and_owner(self):
        operation = str(uuid.uuid4())
        result = self.service.build(self.actor, operation, self.base, ('python', 'app.py'), 8080)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['template'].image, 'sha256:' + 'c' * 64)
        self.assertEqual(result['template'].command, ('python', 'app.py'))
        self.assertEqual(result['template'].port, 8080)
        with tarfile.open(fileobj=io.BytesIO(self.builder.calls[0][3])) as archive:
            dockerfile = archive.extractfile('Dockerfile').read().decode()
            self.assertIn('COPY --chown=10001:10001', dockerfile)
            self.assertNotIn('RUN ', dockerfile)
            self.assertEqual(archive.extractfile('app.txt').read(), b'safe\n')
        self.assertEqual(self.service.build(self.actor, operation, self.base,
                                            ('python', 'app.py'), 8080)['id'], result['id'])
        with self.assertRaisesRegex(WorkloadError, 'OPERATION_CONFLICT'):
            self.service.build(self.actor, operation, self.base, ('python', 'other.py'), 8080)
        self.assertEqual(len(self.builder.calls), 1)
        self.assertEqual(self.service.gc(frozenset({result['image']}), 0), 0)
        self.assertEqual(self.service.gc(frozenset(), 0), 1)
        self.assertEqual(self.builder.removed, [(self.actor.account_id, result['image'])])
        with self.assertRaisesRegex(WorkloadError, 'BUILD_EXPIRED'):
            self.service.build(self.actor, operation, self.base, ('python', 'app.py'), 8080)
        self.assertEqual(len(self.builder.calls), 1)
        with self.assertRaisesRegex(WorkloadError, 'BUILD_CONTEXT_NOT_FOUND'):
            self.service.build(self.other, str(uuid.uuid4()), self.base)
        (self.owner_root / 'Dockerfile').write_text('FROM scratch\nRUN cat /etc/shadow')
        with self.assertRaisesRegex(WorkloadError, 'BUILD_INSTRUCTIONS_DENIED'):
            self.service.build(self.actor, str(uuid.uuid4()), self.base)

    def test_scan_denial_removes_image_and_retry_never_rebuilds(self):
        self.scanner.high = 1
        operation = str(uuid.uuid4())
        with self.assertRaisesRegex(WorkloadError, 'SCAN_POLICY_DENIED'):
            self.service.build(self.actor, operation, self.base)
        self.assertEqual(self.builder.removed, [(self.actor.account_id, 'sha256:' + 'c' * 64)])
        with self.assertRaisesRegex(WorkloadError, 'BUILD_FAILED'):
            self.service.build(self.actor, operation, self.base)
        self.assertEqual(len(self.builder.calls), 1)

    @unittest.skipUnless(os.environ.get('AETHERDESK_DOCKER_TEST') == '1', 'Docker descartável Linux')
    def test_real_docker_build_uses_only_generated_instructions(self):
        probe = subprocess.run(['docker', 'image', 'inspect', 'python:3.13-slim', '--format',
            '{{index .RepoDigests 0}}'], capture_output=True, text=True)
        if probe.returncode or '@sha256:' not in probe.stdout:
            self.skipTest('base por digest indisponível no daemon da fixture')
        base = probe.stdout.strip()
        builder = DockerImageBuilder()
        service = BuildService(self.root / 'real.sqlite3', self.root, builder,
            self.scanner, b'k' * 32, lambda _actor, _cap: None, lambda _actor: True)
        result = service.build(self.actor, str(uuid.uuid4()), base)
        try:
            labels = subprocess.run(['docker', 'image', 'inspect', result['image'], '--format',
                '{{index .Config.Labels "aetherdesk.owner_id"}}'], capture_output=True,
                text=True, check=True).stdout.strip()
            self.assertEqual(labels, self.actor.account_id)
        finally:
            builder.remove(self.actor.account_id, result['image'])


if __name__ == '__main__':
    unittest.main()

"""Jornada integrada v2 sobre socket real em fixture Linux descartável."""

import base64
import os
import sqlite3
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerServer
from apps.AetherDesk.runtime.docker import DockerEnvironmentBroker
from apps.AetherDesk.workloads.service import ApprovedTemplate, WorkloadService
from apps.AetherDesk.workloads.test_service import FakeRuntime
from launch import create_app


@unittest.skipUnless(os.name == 'posix' and os.environ.get('AETHERDESK_DOCKER_TEST') == '1',
                     'requer Linux e Docker descartável')
class ProductJourneyTests(unittest.TestCase):
    def test_login_ide_git_deploy_containers_and_local_ai(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = b'fixture-broker-secret-32-bytes-long!!'
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(secret).decode(),
                'AETHERDESK_BROKER_SOCKET': str(root / 'broker.sock'),
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
                'AETHERDESK_FEATURES': 'ide,workloads,ai',
                'AETHERDESK_SAFE_MODE': '0', 'AETHERDESK_KILL_AI': '0',
                'AETHERDESK_KILL_DEPLOYS': '0',
                'AETHERDESK_ENABLE_WORKLOAD_PROXY': '0',
            }
            with patch.dict(os.environ, config):
                identity = IdentityService(root / 'identity.sqlite3',
                    config['AETHERDESK_BOOTSTRAP_TOKEN'],
                    enabled_features=frozenset({'ide', 'workloads', 'ai'}))
                account_id = identity.bootstrap(config['AETHERDESK_BOOTSTRAP_TOKEN'],
                                                'journey', 'fixture-password-123')
                with sqlite3.connect(identity.db_path) as db:
                    environment_id = db.execute('SELECT environment_id FROM accounts WHERE id=?',
                                                (account_id,)).fetchone()[0]
                runtime = DockerEnvironmentBroker('aetherdesk-files:w003')
                template = ApprovedTemplate('stable', 'fixture/app@sha256:' + 'a' * 64,
                                            'b' * 64, 'c' * 64, True)
                workloads = WorkloadService(root / 'workloads.sqlite3', FakeRuntime(),
                    {'stable': template}, identity.require,
                    lambda actor: self._active(identity, actor))
                server = BrokerServer(root / 'broker.sock', secret, runtime,
                    account_resolver=lambda _id: {'environment_id': environment_id,
                                                   'state': 'active'},
                    nonce_db_path=root / 'broker-nonces.sqlite3',
                    workload_service=workloads, identity=identity)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    with TestClient(create_app()) as client:
                        self.assertEqual(client.get('/readyz').status_code, 200)
                        login = client.post('/api/v1/login', json={
                            'username': 'journey', 'password': 'fixture-password-123'})
                        self.assertEqual(login.status_code, 200, login.text)
                        csrf = {'x-csrf-token': client.cookies['aether_csrf'],
                                'x-aetherdesk-api-version': '2'}
                        self.assertEqual(client.get('/api/v1/desktop/state').status_code, 200)
                        self.assertEqual(client.get('/api/v2/workspace/tree', headers=csrf).status_code, 200)
                        runtime.exec(account_id, environment_id, ['git', 'init', '-b', 'main', '/persist'])
                        runtime.exec(account_id, environment_id,
                                     ['sh', '-c', 'printf original > /persist/hello.txt'])
                        read = client.get('/api/v2/workspace/file?path=hello.txt', headers=csrf)
                        self.assertEqual(read.status_code, 200, read.text)
                        revision = read.json()['data']['revision']
                        saved = client.put('/api/v2/workspace/file', headers={**csrf, 'if-match': revision},
                                           json={'path': 'hello.txt', 'content': 'updated\n'})
                        self.assertEqual(saved.status_code, 200, saved.text)
                        self.assertEqual(client.get('/api/v2/workspace/git/status',
                                                    headers=csrf).status_code, 200)
                        staged = client.post('/api/v2/workspace/git/stage', headers=csrf,
                                             json={'paths': ['hello.txt']})
                        self.assertEqual(staged.status_code, 200, staged.text)
                        committed = client.post('/api/v2/workspace/git/commit', headers=csrf,
                            json={'message': 'fixture commit', 'operationId': str(uuid.uuid4())})
                        self.assertEqual(committed.status_code, 200, committed.text)
                        self.assertEqual(len(committed.json()['data']['message']), 40)
                        self.assertEqual(client.get('/api/v2/workloads/templates',
                                                    headers=csrf).json()['data'], ['stable'])
                        created = client.post('/api/v2/workloads', headers=csrf,
                            json={'project': 'Fixture', 'name': 'api'})
                        self.assertEqual(created.status_code, 200, created.text)
                        workload_id = created.json()['data']['id']
                        deployed = client.post(f'/api/v2/workloads/{workload_id}/actions',
                            headers=csrf, json={'action': 'deploy',
                                                'operationId': str(uuid.uuid4()), 'template': 'stable'})
                        self.assertEqual(deployed.status_code, 200, deployed.text)
                        self.assertTrue(workloads.reconcile(workload_id))
                        job_id = deployed.json()['data']['id']
                        self.assertEqual(client.get(f'/api/v2/jobs/{job_id}',
                                                    headers=csrf).json()['data']['status'], 'completed')
                        items = client.get('/api/v2/workloads/mine', headers=csrf).json()['data']
                        self.assertEqual((items[0]['id'], items[0]['observed']),
                                         (workload_id, 'running'))
                        self.assertEqual(client.get('/api/v2/ai/providers', headers=csrf).status_code, 200)
                        conversation = client.post('/api/v2/ai/conversations', headers=csrf,
                            json={'provider': 'local-demo'})
                        self.assertEqual(conversation.status_code, 200, conversation.text)
                        conversation_id = conversation.json()['data']['id']
                        answer = client.post(f'/api/v2/ai/conversations/{conversation_id}/stream',
                            headers=csrf, json={'prompt': 'Olá', 'disclosureAccepted': True})
                        self.assertEqual(answer.status_code, 200, answer.text)
                        self.assertIn('Demonstração local', answer.text)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
                    server.server_close()
                    runtime.delete_account(account_id, environment_id)

    @staticmethod
    def _active(identity, actor):
        try:
            identity.assert_active(actor)
            return True
        except Exception:
            return False


if __name__ == '__main__':
    unittest.main()

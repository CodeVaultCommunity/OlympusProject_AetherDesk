import base64
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from launch import create_app


class GatewayTests(unittest.TestCase):
    def test_one_use_ticket_is_host_scoped_and_revocation_blocks_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
                'AETHERDESK_FEATURES': 'workloads',
                'AETHERDESK_ENABLE_WORKLOAD_PROXY': '1',
            }
            workload_id = str(uuid.uuid4())
            observed = []
            def broker_call(_broker, kind, account, environment, payload):
                observed.append((kind, account, environment, payload))
                if payload['operation'] == 'state':
                    return {'observed': 'running'}
                if payload['operation'] == 'proxy':
                    self.assertEqual(payload['method'], 'GET')
                    self.assertEqual(payload['path'], '/hello?q=1')
                    return {'status': 200, 'headers': {'content-type': 'text/plain',
                            'set-cookie': 'upstream=bad'},
                            'body': base64.b64encode(b'owner app').decode()}
                self.fail(payload['operation'])
            with patch.dict(os.environ, config), patch(
                    'apps.AetherDesk.runtime.broker_ipc.BrokerClient.call', broker_call):
                identity = IdentityService(os.path.join(directory, 'identity.sqlite3'),
                                           config['AETHERDESK_BOOTSTRAP_TOKEN'],
                                           enabled_features=frozenset({'workloads'}))
                identity.bootstrap(config['AETHERDESK_BOOTSTRAP_TOKEN'], 'owner',
                                   'fixture-password-123')
                with TestClient(create_app(), follow_redirects=False) as client:
                    self.assertEqual(client.get('http://aaaaaaaaaaaa.apps.local/api/v1/me').status_code, 401)
                    self.assertEqual(client.post('/api/v1/login', json={
                        'username': 'owner', 'password': 'fixture-password-123'}).status_code, 200)
                    csrf = {'x-csrf-token': client.cookies['aether_csrf']}
                    issued = client.post(f'/api/v2/workloads/{workload_id}/route-ticket',
                                         headers=csrf)
                    self.assertEqual(issued.status_code, 200, issued.text)
                    host, ticket = issued.json()['data'].values()
                    self.assertTrue(host.endswith('.apps.local'))
                    self.assertEqual(client.get(f'http://{host}/__aetherdesk/open?ticket={ticket}').status_code, 405)
                    opened = client.post(f'http://{host}/__aetherdesk/open', data={'ticket': ticket})
                    self.assertEqual(opened.status_code, 303, opened.text)
                    self.assertEqual(opened.headers['location'], '/')
                    self.assertEqual(client.post(f'http://{host}/__aetherdesk/open',
                                                 data={'ticket': ticket}).status_code, 403)
                    result = client.get(f'http://{host}/hello?q=1')
                    self.assertEqual((result.status_code, result.content), (200, b'owner app'))
                    self.assertNotIn('upstream=bad', result.headers.get('set-cookie', ''))
                    self.assertEqual(client.get('http://ffffffffffff.apps.local/hello').status_code, 401)
                    self.assertEqual(observed[-1][3]['host'], host)
                    for _ in range(20):
                        self.assertEqual(client.post(
                            f'/api/v2/workloads/{workload_id}/route-ticket', headers=csrf).status_code, 200)
                    self.assertEqual(client.post(
                        f'/api/v2/workloads/{workload_id}/route-ticket', headers=csrf).status_code, 429)
                    client.post('/api/v1/logout', headers=csrf)
                    self.assertEqual(client.get(f'http://{host}/hello').status_code, 401)


if __name__ == '__main__':
    unittest.main()

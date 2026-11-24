"""A composição web não deve abrir o daemon Docker ao iniciar."""

import base64
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime.broker_ipc import BrokerError
from apps.AetherDesk.terminal.service import TerminalError
from launch import create_app


class LaunchTests(unittest.TestCase):
    def test_readiness_requires_matching_broker_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
            }
            with patch.dict(os.environ, config):
                app = create_app()
                with TestClient(app) as client:
                    self.assertEqual(client.get('/readyz').status_code, 503)
                    with patch('apps.AetherDesk.runtime.broker_ipc.BrokerClient.call',
                               return_value={'protocol': 1, 'ready': True}):
                        self.assertEqual(client.get('/readyz').json()['status'], 'ready')
                    with patch('apps.AetherDesk.runtime.broker_ipc.BrokerClient.call',
                               return_value={'protocol': 0, 'ready': True}):
                        self.assertEqual(client.get('/readyz').status_code, 503)

    def test_safe_mode_and_kill_switches_remove_new_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            base = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
                'AETHERDESK_FEATURES': 'ide,workloads,ai',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
            }
            identity = IdentityService(os.path.join(directory, 'identity.sqlite3'),
                                       base['AETHERDESK_BOOTSTRAP_TOKEN'])
            identity.bootstrap(base['AETHERDESK_BOOTSTRAP_TOKEN'], 'fixture',
                               'fixture-password-123')
            for switches, expected in [
                ({'AETHERDESK_KILL_DEPLOYS': '1', 'AETHERDESK_KILL_AI': '1'},
                 {'workloads.deploy': False, 'ai.chat': False, 'workloads.read': True}),
                ({'AETHERDESK_SAFE_MODE': '1'},
                 {'workloads.deploy': False, 'ai.chat': False, 'workloads.read': True,
                  'workloads.control': False, 'workloads.route': False}),
            ]:
                with self.subTest(switches=switches), patch.dict(os.environ, {**base, **switches}):
                    with TestClient(create_app()) as client:
                        self.assertEqual(client.post('/api/v1/login', json={
                            'username': 'fixture', 'password': 'fixture-password-123'}).status_code, 200)
                        caps = client.get('/api/v1/me').json()['data']['permissions']
                        for capability, enabled in expected.items():
                            self.assertEqual(capability in caps, enabled)
                        self.assertEqual(client.get('/api/v2/ai/providers').status_code, 404)

    def test_domain_errors_keep_v1_detail_and_add_correlated_v2_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
            }
            with patch.dict(os.environ, config), patch(
                    'apps.AetherDesk.runtime.broker_ipc.BrokerClient.call',
                    side_effect=BrokerError('BROKER_UNAVAILABLE')) as broker_call:
                identity = IdentityService(os.path.join(directory, 'identity.sqlite3'),
                                           config['AETHERDESK_BOOTSTRAP_TOKEN'])
                identity.bootstrap(config['AETHERDESK_BOOTSTRAP_TOKEN'], 'fixture',
                                   'fixture-password-123')
                with TestClient(create_app()) as client:
                    def check(response, status, code, retryable=False):
                        self.assertEqual(response.status_code, status)
                        body = response.json()
                        self.assertEqual(body['detail'], code)
                        self.assertEqual(body['error']['code'], code)
                        self.assertEqual(body['error']['request_id'], response.headers['X-Request-ID'])
                        self.assertEqual(body['error']['event_id'], response.headers['X-Request-ID'])
                        self.assertTrue(body['error']['message'])
                        self.assertEqual(body['error']['retryable'], retryable)

                    check(client.post('/api/v1/login', json={
                        'username': 'fixture', 'password': 'wrong-password'}),
                        401, 'UNAUTHENTICATED')
                    self.assertEqual(client.post('/api/v1/login', json={
                        'username': 'fixture', 'password': 'fixture-password-123'}).status_code, 200)
                    headers = {'x-csrf-token': client.cookies['aether_csrf']}
                    state = {'schemaVersion': 2, 'windows': [],
                             'activeId': None, 'theme': 'dark'}
                    check(client.put('/api/v1/desktop/state', json=state, headers=headers),
                          428, 'PRECONDITION_REQUIRED')
                    first = client.put('/api/v1/desktop/state', json=state,
                                       headers={**headers, 'if-match': '"0"'})
                    self.assertEqual(first.status_code, 200)
                    check(client.put('/api/v1/desktop/state', json={**state, 'activeId': []},
                                     headers={**headers, 'if-match': '"1"'}),
                          422, 'INVALID_DESKTOP')
                    self.assertEqual(client.get('/api/v1/desktop/state').json()['revision'], 1)
                    check(client.put('/api/v1/desktop/state', json=state,
                                     headers={**headers, 'if-match': '"0"'}),
                          412, 'STALE_REVISION')
                    oversized_legacy_state = {'windows': [], 'activeId': None,
                                              'theme': 'dark', 'note': 'x' * 66_000}
                    check(client.put('/api/v1/desktop/state', json=oversized_legacy_state,
                                     headers=headers), 413, 'TOO_LARGE')
                    check(client.put('/api/v1/desktop/state', json={
                        'windows': [], 'activeId': None, 'theme': 'light'},
                        headers=headers), 409, 'CLIENT_UPGRADE_REQUIRED')
                    self.assertEqual(client.get('/api/v1/desktop/state').json()['data'], state)
                    check(client.get('/api/v1/files/list?path=%2Fpersist'),
                          503, 'BROKER_UNAVAILABLE', True)
                    account_id = client.get('/api/v1/me').json()['data']['account_id']
                    check(client.get(f'/api/v1/admin/accounts/{account_id}/environment'),
                          503, 'BROKER_UNAVAILABLE', True)
                    broker_call.side_effect = BrokerError('private broker detail\n')
                    check(client.get(f'/api/v1/admin/accounts/{account_id}/environment'),
                          503, 'BROKER_UNAVAILABLE', True)
                    broker_call.side_effect = BrokerError('BROKER_PROTOCOL')
                    check(client.get('/api/v1/files/list?path=%2Fpersist'),
                          503, 'BROKER_PROTOCOL', True)
                    broker_call.side_effect = BrokerError('UNAVAILABLE')
                    check(client.get('/api/v1/files/list?path=%2Fpersist'),
                          503, 'UNAVAILABLE', True)
                    broker_call.side_effect = BrokerError('UNKNOWN_WRITE_OUTCOME')
                    check(client.put('/api/v1/files/content', json={
                        'path': '/persist/note.txt', 'content': 'fixture'}, headers=headers),
                          503, 'UNKNOWN_WRITE_OUTCOME', False)
                    with patch('apps.AetherDesk.terminal.service.TerminalService.create',
                               side_effect=TerminalError('BROKER_UNAVAILABLE')):
                        check(client.post('/api/v1/terminals', json={'columns': 80, 'rows': 24},
                                          headers=headers), 503, 'BROKER_UNAVAILABLE', True)
                    with patch('apps.AetherDesk.terminal.service.TerminalService.close',
                               side_effect=TerminalError('BROKER_BUSY')):
                        check(client.delete('/api/v1/terminals/123e4567-e89b-12d3-a456-426614174000',
                                            headers=headers), 503, 'BROKER_BUSY', True)

    def test_web_app_starts_without_docker_client(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
            }
            with patch.dict(os.environ, config), patch('docker.from_env',
                    side_effect=AssertionError('Docker client opened in ASGI')):
                app = create_app()
            self.assertTrue(any(getattr(route, 'path', None) == '/healthz' for route in app.routes))

    def test_login_survives_broker_outage_and_keeps_outbox_event(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
            }
            with patch.dict(os.environ, config):
                app = create_app()
                identity = IdentityService(os.path.join(directory, 'identity.sqlite3'),
                                           config['AETHERDESK_BOOTSTRAP_TOKEN'])
                identity.bootstrap(config['AETHERDESK_BOOTSTRAP_TOKEN'], 'fixture',
                                   'fixture-password-123')
                with patch('apps.AetherDesk.runtime.broker_ipc.BrokerClient.call',
                           side_effect=BrokerError('BROKER_UNAVAILABLE')):
                    with TestClient(app) as client:
                        response = client.post('/api/v1/login', json={
                            'username': 'fixture', 'password': 'fixture-password-123'})
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(client.get('/api/v1/me').status_code, 200)
                self.assertEqual(len(identity.pending_account_events()), 1)

    def test_mutation_domains_share_origin_csrf_error_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
            }
            with patch.dict(os.environ, config):
                app = create_app()
                identity = IdentityService(os.path.join(directory, 'identity.sqlite3'),
                                           config['AETHERDESK_BOOTSTRAP_TOKEN'])
                identity.bootstrap(config['AETHERDESK_BOOTSTRAP_TOKEN'], 'fixture',
                                   'fixture-password-123')
                with patch('apps.AetherDesk.runtime.broker_ipc.BrokerClient.call',
                           side_effect=BrokerError('BROKER_UNAVAILABLE')):
                    with TestClient(app) as client:
                        self.assertEqual(client.post('/api/v1/login', json={
                            'username': 'fixture', 'password': 'fixture-password-123'
                        }).status_code, 200)
                        invalid_origin = {'origin': 'https://untrusted.example',
                                          'x-csrf-token': client.cookies['aether_csrf']}
                        account_id = client.get('/api/v1/me').json()['data']['account_id']
                        session_id = '123e4567-e89b-12d3-a456-426614174000'
                        cases = [
                            ('post', '/api/v1/logout', {}),
                            ('post', '/api/v1/admin/accounts', {'username': 'other',
                                'password': 'fixture-password-456', 'role': 'member'}),
                            ('patch', f'/api/v1/admin/accounts/{account_id}', {'revision': 1}),
                            ('put', f'/api/v1/admin/accounts/{account_id}/permissions',
                             {'capability': 'metrics.self', 'allowed': True}),
                            ('post', f'/api/v1/admin/sessions/{session_id}/revoke', {}),
                            ('put', '/api/v1/desktop/state', {}),
                            ('post', f'/api/v1/admin/accounts/{account_id}/environment/retry', {}),
                            ('post', f'/api/v1/admin/accounts/{account_id}/sessions/stop', {}),
                            ('put', '/api/v1/admin/backup', {}),
                            ('put', '/api/v1/files/content', {'path': '/persist/new', 'content': 'x'}),
                            ('post', '/api/v1/files/mkdir', {'path': '/persist/new'}),
                            ('post', '/api/v1/files/move', {'path': '/persist/new',
                                                           'destination': '/persist/other'}),
                            ('post', '/api/v1/files/copy', {'path': '/persist/new',
                                                           'destination': '/persist/other'}),
                            ('delete', '/api/v1/files/entry', {'path': '/persist/new'}),
                            ('put', '/api/v1/files/upload?path=%2Fpersist%2Fnew', {}),
                            ('post', '/api/v1/terminals', {'columns': 80, 'rows': 24}),
                            ('delete', f'/api/v1/terminals/{session_id}', {}),
                        ]
                        for method, path, body in cases:
                            for headers, code in ((invalid_origin, 'INVALID_ORIGIN'),
                                                  ({}, 'INVALID_CSRF')):
                                with self.subTest(path=path, code=code):
                                    response = client.request(method.upper(), path, json=body,
                                                              headers=headers)
                                    self.assertEqual(response.status_code, 403)
                                    self.assertEqual(response.json()['detail'], code)
                                    self.assertEqual(response.json()['error']['code'], code)
                                    self.assertEqual(response.json()['error']['request_id'],
                                                     response.headers['X-Request-ID'])

    def test_read_routes_preserve_v1_unauthenticated_error_and_correlation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                'AETHERDESK_DATA_DIR': directory,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
                'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'b' * 32).decode(),
                'AETHERDESK_BROKER_SOCKET': '/tmp/aetherdesk-test-unused.sock',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1',
            }
            with patch.dict(os.environ, config), patch(
                    'apps.AetherDesk.runtime.broker_ipc.BrokerClient.call',
                    side_effect=BrokerError('BROKER_UNAVAILABLE')):
                with TestClient(create_app()) as client:
                    account_id = '123e4567-e89b-12d3-a456-426614174000'
                    paths = [
                        '/api/v1/me', '/api/v1/desktop/state', '/api/v1/admin/accounts',
                        f'/api/v1/admin/accounts/{account_id}',
                        f'/api/v1/admin/accounts/{account_id}/permissions',
                        f'/api/v1/admin/accounts/{account_id}/sessions',
                        f'/api/v1/admin/accounts/{account_id}/environment',
                        '/api/v1/admin/audit', '/api/v1/admin/backup',
                        '/api/v1/files/list?path=%2Fpersist',
                        '/api/v1/files/metadata?path=%2Fpersist',
                        '/api/v1/files/content?path=%2Fpersist%2Fnote.txt',
                        '/api/v1/files/download?path=%2Fpersist%2Fnote.txt',
                        '/api/v1/terminals', '/api/v1/metrics/self',
                        '/api/v1/metrics/server', '/api/v1/metrics/accounts',
                    ]
                    for path in paths:
                        with self.subTest(path=path):
                            response = client.get(path)
                            self.assertEqual(response.status_code, 401)
                            self.assertEqual(response.json()['detail'], 'UNAUTHENTICATED')
                            self.assertEqual(response.json()['error']['code'], 'UNAUTHENTICATED')
                            self.assertEqual(response.json()['error']['request_id'],
                                             response.headers['X-Request-ID'])
                            self.assertEqual(response.headers['cache-control'], 'no-store')
                            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
                            self.assertIn("frame-ancestors 'none'",
                                          response.headers['content-security-policy'])
                    mismatch = client.get('/api/v2/workspace/tree', headers={
                        'X-AetherDesk-API-Version': '1'})
                    self.assertEqual(mismatch.status_code, 426)
                    self.assertEqual(mismatch.json()['error']['code'], 'API_VERSION_UNSUPPORTED')
                    self.assertEqual(mismatch.headers['X-AetherDesk-API-Version'], '2')


if __name__ == '__main__':
    unittest.main()

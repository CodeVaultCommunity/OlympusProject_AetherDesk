import os
import subprocess
import tempfile
import unittest

from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from launch import create_app


@unittest.skipUnless(os.environ.get('AETHERDESK_DOCKER_TEST') == '1', 'requer Docker Linux descartável')
class TerminalHttpTests(unittest.TestCase):
    def test_socket_revocation_keeps_process_and_reconnects(self):
        with tempfile.TemporaryDirectory() as temp:
            keys = ('AETHERDESK_DATA_DIR', 'AETHERDESK_BOOTSTRAP_TOKEN',
                    'AETHERDESK_CSRF_SECRET', 'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP')
            old = {key: os.environ.get(key) for key in keys}
            os.environ.update({'AETHERDESK_DATA_DIR': temp,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'bootstrap-secret-long',
                'AETHERDESK_CSRF_SECRET': 'csrf-secret-long-enough-for-testing-12345',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1'})
            container = volume = None
            try:
                app = create_app()
                with TestClient(app) as administrator, TestClient(app) as member:
                    administrator.post('/api/v1/bootstrap', json={'token': 'bootstrap-secret-long',
                        'username': 'admin', 'password': 'strong-admin-password'})
                    administrator.post('/api/v1/login', json={'username': 'admin',
                        'password': 'strong-admin-password'})
                    csrf = administrator.cookies.get('aether_csrf')
                    created = administrator.post('/api/v1/admin/accounts', json={'username': 'alice',
                        'password': 'strong-alice-password', 'role': 'member'},
                        headers={'X-CSRF-Token': csrf})
                    self.assertEqual(created.status_code, 200, created.text)
                    account_id = created.json()['data']['id']
                    identity = IdentityService(os.path.join(temp, 'identity.sqlite3'), 'bootstrap-secret-long')
                    env_id = identity.account(identity.actor(administrator.cookies.get('aether_session')),
                                              account_id)['environment_id']
                    container, volume = DockerEnvironmentBroker._names(env_id)
                    member.post('/api/v1/login', json={'username': 'alice', 'password': 'strong-alice-password'})
                    alice_csrf = member.cookies.get('aether_csrf')
                    terminal = member.post('/api/v1/terminals', json={'columns': 80, 'rows': 24},
                                           headers={'X-CSRF-Token': alice_csrf})
                    self.assertEqual(terminal.status_code, 200, terminal.text)
                    terminal_id = terminal.json()['data']['id']
                    with member.websocket_connect('/api/v1/ws/terminals/' + terminal_id) as ws:
                        self.assertTrue(ws.receive_bytes())
                        session = administrator.get('/api/v1/admin/accounts/' + account_id + '/sessions').json()['data'][0]
                        revoked = administrator.post('/api/v1/admin/sessions/' + session['id'] + '/revoke',
                            headers={'X-CSRF-Token': csrf})
                        self.assertEqual(revoked.status_code, 200)
                        message = ws.receive()
                        while message['type'] == 'websocket.send':
                            message = ws.receive()
                        self.assertEqual(message['type'], 'websocket.close')
                    self.assertEqual(member.get('/api/v1/terminals').status_code, 401)
                    member.post('/api/v1/login', json={'username': 'alice', 'password': 'strong-alice-password'})
                    self.assertEqual(member.get('/api/v1/terminals').json()['data'][0]['state'], 'open')
                    with member.websocket_connect('/api/v1/ws/terminals/' + terminal_id) as ws:
                        self.assertTrue(ws.receive_bytes())
            finally:
                if container:
                    subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                if volume:
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == '__main__':
    unittest.main()

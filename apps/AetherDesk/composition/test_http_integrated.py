import os
import base64
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from launch import create_app


class IntegratedHttpTests(unittest.TestCase):
    def test_login_desktop_backup_and_denial(self):
        with tempfile.TemporaryDirectory() as temp:
            previous = {key: os.environ.get(key) for key in ('AETHERDESK_DATA_DIR',
                'AETHERDESK_BOOTSTRAP_TOKEN', 'AETHERDESK_CSRF_SECRET',
                'AETHERDESK_BROKER_SECRET_B64', 'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP')}
            os.environ.update({'AETHERDESK_DATA_DIR': temp,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'bootstrap-secret-long',
                'AETHERDESK_CSRF_SECRET': 'csrf-secret-long-enough-for-testing-12345',
                'AETHERDESK_BROKER_SECRET_B64': base64.b64encode(b'integrated-test-secret-32-bytes!!!').decode(),
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1'})
            try:
                with patch('launch.BrokerClient') as broker_factory:
                    broker_factory.return_value.call.side_effect = lambda operation, account, environment, payload=None: {
                        'account_id': account, 'environment_id': environment, 'container_name': 'fixture',
                        'volume_name': 'fixture', 'state': 'running'} if operation in ('ensure', 'state') else {}
                    with TestClient(create_app()) as client:
                        self.assertEqual(client.post('/api/v1/bootstrap', json={'token': 'bootstrap-secret-long',
                            'username': 'admin', 'password': 'strong-admin-password'}).status_code, 200)
                        self.assertEqual(client.post('/api/v1/login', json={'username': 'admin',
                            'password': 'strong-admin-password'}).status_code, 200)
                        csrf = client.cookies.get('aether_csrf')
                        self.assertEqual(client.get('/api/v1/desktop/state').json()['data']['windows'], [])
                        state = {'windows': [{'id': 'window-1', 'kind': 'terminal', 'x': 13, 'y': 30,
                            'width': 720, 'height': 470, 'z': 1, 'minimized': False,
                            'maximized': False}], 'activeId': 'window-1', 'theme': 'dark'}
                        self.assertEqual(client.put('/api/v1/desktop/state', json=state,
                            headers={'X-CSRF-Token': csrf}).status_code, 200)
                        self.assertEqual(client.get('/api/v1/desktop/state').json()['data'], state)
                        self.assertEqual(client.get('/api/v1/admin/backup').json()['data']['enabled'], 0)
                        self.assertEqual(client.put('/api/v1/admin/backup', json={'enabled': True,
                            'frequency_hours': 12, 'destination': '/var/backups/aetherdesk',
                            'retention_mode': 'replace'}, headers={'X-CSRF-Token': csrf}).status_code, 200)
                        self.assertEqual(client.put('/api/v1/desktop/state', json=state).status_code, 403)
                        self.assertEqual(client.post('/api/v1/logout', headers={'X-CSRF-Token': csrf}).status_code, 200)
                        self.assertEqual(client.get('/api/v1/desktop/state').status_code, 401)
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == '__main__':
    unittest.main()

import os
import subprocess
import tempfile
import unittest

from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from launch import create_app


@unittest.skipUnless(os.environ.get('AETHERDESK_DOCKER_TEST') == '1', 'requer Docker Linux descartável')
class FileHttpTests(unittest.TestCase):
    def test_upload_read_conflict_and_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            keys = ('AETHERDESK_DATA_DIR', 'AETHERDESK_BOOTSTRAP_TOKEN',
                    'AETHERDESK_CSRF_SECRET', 'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP')
            old = {key: os.environ.get(key) for key in keys}
            os.environ.update({'AETHERDESK_DATA_DIR': temp,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'bootstrap-secret-long',
                'AETHERDESK_CSRF_SECRET': 'csrf-secret-long-enough-for-testing-12345',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1'})
            resources = []
            try:
                app = create_app()
                with TestClient(app) as administrator, TestClient(app) as alice, TestClient(app) as bob:
                    administrator.post('/api/v1/bootstrap', json={'token': 'bootstrap-secret-long',
                        'username': 'admin', 'password': 'strong-admin-password'})
                    administrator.post('/api/v1/login', json={'username': 'admin',
                        'password': 'strong-admin-password'})
                    admin_csrf = administrator.cookies.get('aether_csrf')
                    identity = IdentityService(os.path.join(temp, 'identity.sqlite3'), 'bootstrap-secret-long')
                    admin = identity.actor(administrator.cookies.get('aether_session'))
                    admin_env = identity.account(admin, admin.account_id)['environment_id']
                    resources.append(DockerEnvironmentBroker._names(admin_env))
                    for name, client in (('alice', alice), ('bobby', bob)):
                        created = administrator.post('/api/v1/admin/accounts', json={'username': name,
                            'password': 'strong-member-password', 'role': 'member'},
                            headers={'X-CSRF-Token': admin_csrf})
                        self.assertEqual(created.status_code, 200, created.text)
                        env_id = identity.account(admin, created.json()['data']['id'])['environment_id']
                        resources.append(DockerEnvironmentBroker._names(env_id))
                        client.post('/api/v1/login', json={'username': name, 'password': 'strong-member-password'})
                    for client, data in ((alice, b'alice'), (bob, b'bobby')):
                        response = client.put('/api/v1/files/upload?path=%2Fpersist%2Fsame.txt',
                            content=data, headers={'X-CSRF-Token': client.cookies.get('aether_csrf')})
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(client.get('/api/v1/files/download?path=%2Fpersist%2Fsame.txt').content, data)
                    self.assertEqual(alice.get('/api/v1/files/content?path=%2Fpersist%2Fsame.txt').json()['data']['content'], 'alice')
                    self.assertEqual(bob.get('/api/v1/files/content?path=%2Fpersist%2Fsame.txt').json()['data']['content'], 'bobby')
                    self.assertEqual(alice.get('/api/v1/files/content?path=%2Fpersist%2F..%2F..%2Fetc%2Fpasswd').status_code, 422)
                    self.assertEqual(alice.put('/api/v1/files/upload?path=%2Fpersist%2Fsame.txt',
                        content=b'again', headers={'X-CSRF-Token': alice.cookies.get('aether_csrf')}).status_code, 409)
                    self.assertEqual(alice.put('/api/v1/files/upload?path=%2Fpersist%2Ftoo-big.bin',
                        content=b'x' * (8 * 1024 * 1024 + 1),
                        headers={'X-CSRF-Token': alice.cookies.get('aether_csrf')}).status_code, 413)
            finally:
                for container, volume in resources:
                    subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == '__main__':
    unittest.main()

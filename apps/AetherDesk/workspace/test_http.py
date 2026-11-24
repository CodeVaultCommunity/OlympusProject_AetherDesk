import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.runtime.broker_ipc import BrokerError
from apps.AetherDesk.support.http import install_http_policy
from .http import workspace_router


class FakeBroker:
    def __init__(self, identity):
        self.identity = identity
        self.calls = []
        self.content = 'print(1)\n'
        self.revision = 'r1'

    def call(self, operation, account_id, _environment_id, payload):
        assert operation == 'workspace'
        current = type('Actor', (), {'account_id': account_id,
                                     'session_id': payload['session_id']})()
        cap = 'files.write' if payload['operation'] == 'write' else 'files.read'
        self.identity.require(current, cap)
        self.calls.append((account_id, payload['operation']))
        if payload['operation'] == 'tree':
            return [{'path': 'main.py', 'name': 'main.py', 'kind': 'file'}]
        if payload['operation'] == 'read':
            return {'mode': 'text', 'text': self.content, 'revision': self.revision}
        if payload['operation'] == 'write':
            if payload['revision'] != self.revision:
                raise BrokerError('STALE_REVISION')
            self.content = payload['content']
            self.revision = 'r2'
            return {'revision': self.revision}
        if payload['operation'] == 'search':
            return {'matches': [{'path': 'main.py', 'line': 1, 'preview': self.content}]}
        raise BrokerError('GIT_UNAVAILABLE')


class WorkspaceHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        secret = 'csrf-secret-with-at-least-32-characters'
        identity = IdentityService(root / 'identity.sqlite3', 'bootstrap-secret-long',
                                   enabled_features=frozenset({'ide'}))
        identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
        admin = identity.actor(identity.login('admin', 'strong-admin-password')[0])
        identity.create_account(admin, 'alice', 'strong-alice-password')
        self.identity = identity
        self.broker = FakeBroker(identity)
        app = FastAPI()
        install_http_policy(app)
        app.include_router(identity_router(identity, secret, secure_cookie=False))
        app.include_router(workspace_router(self.broker, identity, secret))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.assertEqual(self.client.post('/api/v1/login', json={
            'username': 'alice', 'password': 'strong-alice-password'}).status_code, 200)

    def test_tree_edit_search_and_csrf_revision(self):
        self.assertEqual(self.client.get('/api/v2/workspace/tree').json()['data'][0]['name'], 'main.py')
        read = self.client.get('/api/v2/workspace/file?path=main.py').json()['data']
        self.assertEqual((read['content'], read['revision']), ('print(1)\n', 'r1'))
        self.assertEqual(read['language'], 'python')
        path = '/api/v2/workspace/file'
        self.assertEqual(self.client.put(path, json={'path': 'main.py', 'content': 'print(2)\n'},
                                         headers={'If-Match': 'r1'}).status_code, 403)
        csrf = {'If-Match': 'r1', 'X-CSRF-Token': self.client.cookies.get('aether_csrf')}
        saved = self.client.put(path, json={'path': 'main.py', 'content': 'print(2)\n'}, headers=csrf)
        self.assertEqual(saved.json()['data']['revision'], 'r2')
        self.assertEqual(self.client.put(path, json={'path': 'main.py', 'content': 'stale'},
                                         headers=csrf).status_code, 412)
        self.assertEqual(self.client.get('/api/v2/workspace/search?q=print').json()['data'][0]['snippet'], 'print(2)\n')
        self.assertTrue(all(account_id == self.identity.actor(self.client.cookies.get('aether_session')).account_id
                            for account_id, _ in self.broker.calls))

    def test_feature_revocation_blocks_before_broker(self):
        self.identity.enabled_features = frozenset()
        before = len(self.broker.calls)
        self.assertEqual(self.client.get('/api/v2/workspace/tree').status_code, 403)
        self.assertEqual(len(self.broker.calls), before)

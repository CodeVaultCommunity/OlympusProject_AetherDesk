import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.support.http import install_http_policy
from .chat import ChatService, Provider
from .http import ai_router


class AiHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        secret = 'csrf-secret-with-at-least-32-characters'
        identity = IdentityService(root / 'id.sqlite3', 'bootstrap-secret-long',
                                   enabled_features=frozenset({'ai'}))
        identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
        self.identity = identity
        service = ChatService(root / 'ai.sqlite3', identity.require,
                              lambda actor: self._active(actor),
                              providers={'local-demo': Provider('local-demo', False, 'Dados locais',
                                  lambda messages, _credential: ('resposta local',))},
                              enabled_providers=frozenset({'local-demo'}))
        app = FastAPI()
        install_http_policy(app)
        app.include_router(identity_router(identity, secret, secure_cookie=False))
        app.include_router(ai_router(service, identity, secret))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _active(self, actor):
        self.identity.assert_active(actor)
        return True

    def login(self, username, password):
        response = self.client.post('/api/v1/login', json={'username': username, 'password': password})
        self.assertEqual(response.status_code, 200)
        return {'X-CSRF-Token': self.client.cookies.get('aether_csrf')}

    def test_chat_http_csrf_owner_and_no_external_provider(self):
        csrf = self.login('admin', 'strong-admin-password')
        self.assertEqual(self.client.get('/api/v2/ai/providers').json()['data'][0]['name'], 'local-demo')
        self.assertEqual(self.client.post('/api/v2/ai/conversations',
                                          json={'provider': 'local-demo'}).status_code, 403)
        created = self.client.post('/api/v2/ai/conversations',
                                   json={'provider': 'local-demo'}, headers=csrf)
        self.assertEqual(created.status_code, 200)
        cid = created.json()['data']['id']
        self.assertEqual(len(self.client.get('/api/v2/ai/conversations').json()['data']), 1)
        streamed = self.client.post(f'/api/v2/ai/conversations/{cid}/stream',
                                    json={'prompt': 'olá', 'disclosureAccepted': False}, headers=csrf)
        self.assertEqual(streamed.status_code, 200)
        self.assertIn('resposta local', streamed.text)
        self.assertEqual(len(self.client.get(f'/api/v2/ai/conversations/{cid}/messages').json()['data']), 2)
        self.assertEqual(self.client.get('/api/v2/ai/usage').json()['data']['usedChars'] > 0, True)
        self.assertEqual(self.client.post('/api/v2/ai/conversations',
                                          json={'provider': 'externo'}, headers=csrf).status_code, 403)
        self.assertEqual(self.client.post('/api/v2/ai/provider', json={
            'name': 'local-demo', 'model': 'demo', 'secret': 'test-secret'}, headers=csrf).status_code, 422)
        actor = self.identity.actor(self.client.cookies.get('aether_session'))
        self.identity.create_account(actor, 'alice', 'strong-alice-password')
        self.login('alice', 'strong-alice-password')
        self.assertEqual(self.client.get(f'/api/v2/ai/conversations/{cid}/messages').status_code, 404)
        self.assertEqual(self.client.get('/api/v2/ai/conversations').json()['data'], [])

    def test_disabled_feature_denies_even_with_capability_override(self):
        self.identity.enabled_features = frozenset()
        self.login('admin', 'strong-admin-password')
        self.assertEqual(self.client.get('/api/v2/ai/providers').status_code, 403)

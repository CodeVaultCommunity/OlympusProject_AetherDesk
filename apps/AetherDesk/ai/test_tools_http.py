import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.support.http import install_http_policy
from .chat import ChatService, Provider
from .http import ai_router
from .tools import NativeTools


class FakeBroker:
    def __init__(self, owner):
        self.owner = owner
        self.workload = str(uuid.uuid4())
        self.effects = []

    def call(self, operation, account, environment, payload):
        assert operation == 'workload'
        if payload['operation'] == 'list_mine':
            return {'items': [{'id': self.workload, 'name': 'api', 'project': 'Portal',
                               'desired': 'running', 'observed': 'running'}] if account == self.owner else []}
        if payload['operation'] == 'request':
            self.effects.append((account, payload))
            return {'id': str(uuid.uuid4()), 'status': 'pending'}
        raise AssertionError(payload)


class NativeToolsHttpTests(unittest.TestCase):
    def test_server_proposal_approval_exact_args_owner_replay_and_kill_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = 'csrf-secret-with-at-least-32-characters'
            identity = IdentityService(root / 'id.sqlite3', 'bootstrap-secret-long',
                                       enabled_features=frozenset({'ai', 'workloads'}))
            admin_id = identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            broker = FakeBroker(admin_id)
            service = ChatService(root / 'ai.sqlite3', identity.require,
                                  lambda actor: bool(identity.assert_active(actor) is None),
                                  providers={'local-demo': Provider('local-demo', False, 'Local',
                                      lambda _messages, _credential: ('local',))},
                                  enabled_providers=frozenset({'local-demo'}))
            app = FastAPI()
            install_http_policy(app)
            app.include_router(identity_router(identity, secret, secure_cookie=False))
            app.include_router(ai_router(service, identity, secret,
                                         NativeTools(root / 'ai.sqlite3', identity, broker)))
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/v1/login', json={
                    'username': 'admin', 'password': 'strong-admin-password'}).status_code, 200)
                csrf = {'X-CSRF-Token': client.cookies['aether_csrf']}
                proposals = client.get('/api/v2/ai/tools/proposals').json()['data']
                self.assertEqual(len(proposals), 1)
                proposal = proposals[0]
                self.assertEqual(proposal['source'], 'native')
                self.assertEqual(proposal['arguments']['workload_id'], broker.workload)
                self.assertEqual(client.post('/api/v2/ai/tools/approvals', json={
                    'proposalId': proposal['id']}).status_code, 403)
                ticket_response = client.post('/api/v2/ai/tools/approvals', json={
                    'proposalId': proposal['id']}, headers=csrf)
                self.assertEqual(ticket_response.status_code, 200)
                ticket = ticket_response.json()['data']
                self.assertNotEqual(client.post(f"/api/v2/ai/tools/approvals/{ticket['id']}/approve",
                    json={'nonce': str(uuid.uuid4())}, headers=csrf).status_code, 200)
                self.assertEqual(client.post(f"/api/v2/ai/tools/approvals/{ticket['id']}/approve",
                    json={'nonce': ticket['nonce']}, headers=csrf).status_code, 200)
                operation_id = str(uuid.uuid4())
                invoke = {'proposalId': proposal['id'], 'ticketId': ticket['id'],
                          'nonce': ticket['nonce'], 'operationId': operation_id}
                self.assertEqual(client.post('/api/v2/ai/tools/invoke', json=invoke,
                                             headers=csrf).status_code, 200)
                self.assertEqual(len(broker.effects), 1)
                self.assertEqual(broker.effects[0][1]['workload_id'], broker.workload)
                self.assertEqual(client.post('/api/v2/ai/tools/invoke', json=invoke,
                                             headers=csrf).status_code, 404)
                self.assertEqual(len(broker.effects), 1)
                next_proposal = client.get('/api/v2/ai/tools/proposals').json()['data'][0]
                identity.enabled_features = frozenset()
                self.assertEqual(client.post('/api/v2/ai/tools/approvals', json={
                    'proposalId': next_proposal['id']}, headers=csrf).status_code, 403)
                self.assertEqual(len(broker.effects), 1)

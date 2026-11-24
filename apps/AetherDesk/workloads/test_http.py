import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.runtime.broker_ipc import BrokerDispatch, BrokerError
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.support.http import install_http_policy
from .http import workloads_router
from .service import ApprovedTemplate, WorkloadService, WorkloadError
from .test_service import FakeRuntime


class FakeBroker:
    def __init__(self, dispatch):
        self.dispatch = dispatch

    def call(self, operation, account_id, _environment_id, payload):
        assert operation == 'workload'
        try:
            return self.dispatch._workload(account_id, payload)
        except (IdentityError, WorkloadError) as exc:
            raise BrokerError(str(exc)) from exc


class WorkloadHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        secret = 'csrf-secret-with-at-least-32-characters'
        identity = IdentityService(root / 'identity.sqlite3', 'bootstrap-secret-long',
                                   enabled_features=frozenset({'workloads'}))
        identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
        admin = identity.actor(identity.login('admin', 'strong-admin-password')[0])
        identity.create_account(admin, 'alice', 'strong-alice-password')
        identity.create_account(admin, 'bob', 'strong-bob-password')
        self.identity = identity
        self.runtime = FakeRuntime()
        self.service = WorkloadService(root / 'workloads.sqlite3', self.runtime, {
            'stable': ApprovedTemplate('stable', 'example/app@sha256:' + 'a' * 64,
                                       'b' * 64, 'c' * 64, True)},
            identity.require, lambda actor: self._active(actor))
        dispatch = BrokerDispatch(b's' * 32, self.runtime, workload_service=self.service,
                                  identity=identity)
        app = FastAPI()
        install_http_policy(app)
        app.include_router(identity_router(identity, secret, secure_cookie=False))
        app.include_router(workloads_router(FakeBroker(dispatch), identity, secret))
        self.clients = {}
        for username in ('admin', 'alice', 'bob'):
            client = TestClient(app)
            self.addCleanup(client.close)
            login = client.post('/api/v1/login', json={
                'username': username, 'password': f'strong-{username}-password'})
            self.assertEqual(login.status_code, 200)
            self.clients[username] = client

    def _active(self, actor):
        self.identity.assert_active(actor)
        return True

    def post(self, who, path, payload):
        client = self.clients[who]
        return client.post(path, json=payload,
                           headers={'X-CSRF-Token': client.cookies.get('aether_csrf')})

    def test_owner_admin_idor_cancel_and_csrf(self):
        alice = self.clients['alice']
        denied = alice.post('/api/v2/workloads', json={'project': 'Portal', 'name': 'api'})
        self.assertEqual(denied.status_code, 403)
        created = self.post('alice', '/api/v2/workloads', {'project': 'Portal', 'name': 'api'})
        self.assertEqual(created.status_code, 200)
        workload_id = created.json()['data']['id']
        self.assertEqual(alice.get('/api/v2/workloads/templates').json()['data'], ['stable'])
        self.assertEqual([row['id'] for row in alice.get('/api/v2/workloads/mine').json()['data']], [workload_id])
        self.assertEqual(self.clients['bob'].get('/api/v2/workloads/mine').json()['data'], [])
        self.assertEqual(self.clients['bob'].get(f'/api/v2/workloads/{workload_id}/logs').status_code, 404)
        admin = self.clients['admin']
        self.assertEqual([row['id'] for row in admin.get('/api/v2/workloads/controllable').json()['data']], [workload_id])
        self.assertEqual(admin.get(f'/api/v2/workloads/{workload_id}/logs').status_code, 404)
        self.assertEqual(self.post('alice', '/api/v2/workloads/build', {}).status_code, 403)

        operation = str(uuid.uuid4())
        request = {'action': 'deploy', 'operationId': operation, 'template': 'stable'}
        first = self.post('alice', f'/api/v2/workloads/{workload_id}/actions', request)
        self.assertEqual(first.status_code, 200)
        second = self.post('alice', f'/api/v2/workloads/{workload_id}/actions', request)
        self.assertEqual(second.json()['data']['id'], first.json()['data']['id'])
        job_id = first.json()['data']['id']
        self.assertEqual(self.clients['bob'].get(f'/api/v2/jobs/{job_id}').status_code, 403)
        cancelled = self.post('alice', f'/api/v2/jobs/{job_id}/cancel', {})
        self.assertEqual(cancelled.json()['data']['status'], 'cancelled')
        self.assertEqual(self.service.state(self.identity.actor(alice.cookies.get('aether_session')),
                                            workload_id)['desired'], 'stopped')
        self.assertEqual(self.runtime.calls, [])

        next_job = self.post('alice', f'/api/v2/workloads/{workload_id}/actions', {
            'action': 'deploy', 'operationId': str(uuid.uuid4()), 'template': 'stable'})
        self.assertEqual(next_job.status_code, 200)
        self.service.reconcile(workload_id)
        self.assertEqual(alice.get(f'/api/v2/jobs/{next_job.json()["data"]["id"]}').json()['data']['status'], 'completed')
        self.assertEqual(alice.get(f'/api/v2/workloads/{workload_id}/logs').json()['data'], 'private logs')
        admin_stop = self.post('admin', f'/api/v2/workloads/{workload_id}/actions', {
            'action': 'stop', 'operationId': str(uuid.uuid4())})
        self.assertEqual(admin_stop.status_code, 200)

import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router
from apps.AetherDesk.support.http import install_http_policy


class HttpIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        service = IdentityService(Path(self.temp.name) / "id.sqlite3", "bootstrap-secret-long")
        self.service = service
        service.bootstrap("bootstrap-secret-long", "admin", "strong-admin-password")
        app = FastAPI()
        install_http_policy(app)
        app.include_router(identity_router(service, "csrf-secret-with-at-least-32-characters", secure_cookie=False))
        self.client = TestClient(app, base_url="http://testserver")
        self.addCleanup(self.client.close)

    def test_cookie_csrf_and_account_authorization(self):
        response = self.client.post("/api/v1/login", json={"username": "admin", "password": "strong-admin-password"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies.get("aether_session"))
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/v1/me").json()["data"]["role"], "admin")
        payload = {"username": "alice", "password": "strong-alice-password"}
        self.assertEqual(self.client.post("/api/v1/admin/accounts", json=payload).status_code, 403)
        csrf = self.client.cookies.get("aether_csrf")
        created = self.client.post("/api/v1/admin/accounts", json=payload,
                                   headers={"X-CSRF-Token": csrf})
        self.assertEqual(created.status_code, 200)
        account_id = created.json()["data"]["id"]
        self.client.post("/api/v1/logout", headers={"X-CSRF-Token": csrf})
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.client.post("/api/v1/login", json={"username": "alice", "password": "strong-alice-password"})
        self.assertEqual(self.client.get(f"/api/v1/admin/accounts/{account_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/accounts/00000000-0000-0000-0000-000000000001").status_code, 403)

    def test_login_rate_limit_and_origin(self):
        credentials = {"username": "unknown", "password": "incorrect-password"}
        self.assertEqual(self.client.post('/api/v1/bootstrap', json={
            'token': 'bootstrap-secret-long', 'username': 'other',
            'password': 'strong-other-password'},
            headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/login', json=credentials,
                                          headers={'Origin': 'https://other.example'}).status_code, 403)
        for _ in range(10):
            self.assertEqual(self.client.post('/api/v1/login', json=credentials).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/login', json=credentials).status_code, 429)

    def test_error_envelope_correlation_and_validation_redaction(self):
        denied = self.client.get('/api/v1/me')
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(denied.json()['detail'], 'UNAUTHENTICATED')
        self.assertEqual(denied.json()['error']['code'], 'UNAUTHENTICATED')
        self.assertEqual(denied.json()['error']['request_id'], denied.headers['X-Request-ID'])
        self.assertEqual(denied.json()['error']['event_id'], denied.headers['X-Request-ID'])
        self.assertFalse(denied.json()['error']['retryable'])
        self.assertIsInstance(denied.json()['error']['message'], str)
        invalid = self.client.post('/api/v1/login', json={'username': 'admin',
                                                           'password': ['sensitive-fixture']})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()['error']['code'], 'VALIDATION_ERROR')
        self.assertFalse(invalid.json()['error']['retryable'])
        self.assertNotIn('sensitive-fixture', invalid.text)

    def test_admin_permission_rate_limit_is_persistent(self):
        self.assertEqual(self.client.post('/api/v1/login', json={
            'username': 'admin', 'password': 'strong-admin-password'}).status_code, 200)
        account_id = self.client.get('/api/v1/me').json()['data']['account_id']
        csrf = self.client.cookies.get('aether_csrf')
        path = f'/api/v1/admin/accounts/{account_id}/permissions'
        body = {'capability': 'metrics.server', 'allowed': True}
        for _ in range(30):
            response = self.client.put(path, json=body, headers={'X-CSRF-Token': csrf})
            self.assertEqual(response.status_code, 200)
        blocked = self.client.put(path, json=body, headers={'X-CSRF-Token': csrf})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()['error']['code'], 'RATE_LIMITED')
        self.assertTrue(blocked.json()['error']['retryable'])

    def test_permissions_version_signals_revocation_to_client(self):
        self.client.post('/api/v1/login', json={
            'username': 'admin', 'password': 'strong-admin-password'})
        before = self.client.get('/api/v1/me').json()['data']
        self.assertIn('metrics.server', before['permissions'])
        changed = self.client.put(
            f"/api/v1/admin/accounts/{before['account_id']}/permissions",
            json={'capability': 'metrics.server', 'allowed': False},
            headers={'X-CSRF-Token': self.client.cookies.get('aether_csrf')})
        self.assertEqual(changed.status_code, 200)
        after = self.client.get('/api/v1/me').json()['data']
        self.assertEqual(after['permissions_version'], before['permissions_version'] + 1)
        self.assertNotIn('metrics.server', after['permissions'])

    def test_expired_session_preserves_v1_detail_and_structured_error(self):
        self.client.post('/api/v1/login', json={
            'username': 'admin', 'password': 'strong-admin-password'})
        self.assertEqual(self.client.get('/api/v1/me').status_code, 200)
        with closing(sqlite3.connect(self.service.db_path)) as db, db:
            db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
        expired = self.client.get('/api/v1/me')
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.json()['detail'], 'UNAUTHENTICATED')
        self.assertEqual(expired.json()['error']['code'], 'UNAUTHENTICATED')


if __name__ == "__main__":
    unittest.main()

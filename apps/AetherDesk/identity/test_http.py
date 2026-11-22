import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.identity.http import identity_router


class HttpIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        service = IdentityService(Path(self.temp.name) / "id.sqlite3", "bootstrap-secret-long")
        service.bootstrap("bootstrap-secret-long", "admin", "strong-admin-password")
        app = FastAPI()
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


if __name__ == "__main__":
    unittest.main()

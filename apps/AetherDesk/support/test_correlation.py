import unittest
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.AetherDesk.runtime.broker_ipc import BrokerClient
from apps.AetherDesk.support.http import install_http_policy


class CorrelationTests(unittest.TestCase):
    def test_request_id_reaches_threadpool_ipc_and_is_cleared(self):
        app = FastAPI()
        install_http_policy(app)
        client = BrokerClient('/unused', b'test-secret-with-at-least-32-bytes!!')
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())

        @app.get('/probe')
        def probe():
            return {'request_id': client._message('state', account, environment, None).get('request_id')}

        with TestClient(app) as http:
            first = http.get('/probe')
            second = http.get('/probe')
        self.assertEqual(first.json()['request_id'], first.headers['X-Request-ID'])
        self.assertEqual(second.json()['request_id'], second.headers['X-Request-ID'])
        self.assertNotEqual(first.json()['request_id'], second.json()['request_id'])
        self.assertNotIn('request_id', client._message('state', account, environment, None))


if __name__ == '__main__':
    unittest.main()

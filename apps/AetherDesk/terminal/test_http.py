import threading
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from apps.AetherDesk.identity import ActorContext, IdentityError

from .http import parse_terminal_control, terminal_router
from .service import TerminalError


class TerminalControlTests(unittest.TestCase):
    def test_websocket_requires_same_origin_before_attaching(self):
        class ServiceStub:
            def attach(self, *_args):
                raise AssertionError('terminal attached despite invalid origin')

        app = FastAPI()
        app.include_router(terminal_router(ServiceStub(), object(), 'fixture-secret' * 3))
        with TestClient(app) as client:
            for headers in ({'cookie': 'aether_session=fixture'},
                            {'origin': 'https://other.example', 'cookie': 'aether_session=fixture'}):
                with self.subTest(headers=headers), self.assertRaises(WebSocketDisconnect) as caught:
                    with client.websocket_connect('/api/v1/ws/terminals/fixture', headers=headers):
                        pass
                self.assertEqual(caught.exception.code, 4403)

    def test_accepts_only_typed_bounded_control_messages(self):
        self.assertEqual(parse_terminal_control('{"type":"resize","columns":80,"rows":24}'),
                         {'type': 'resize', 'columns': 80, 'rows': 24})
        self.assertEqual(parse_terminal_control('{"type":"signal","name":"INT"}')['name'], 'INT')
        self.assertEqual(parse_terminal_control('{"type":"close"}')['type'], 'close')
        for raw in ('{', '[]', '{"type":"resize","columns":true,"rows":24}',
                    '{"type":"resize","columns":999,"rows":24}',
                    '{"type":"signal","name":"KILL"}',
                    '{"type":"close","command":"docker ps"}', 'x' * 4097):
            with self.subTest(raw=raw[:60]), self.assertRaisesRegex(TerminalError,
                                                                     'INVALID_CONTROL_MESSAGE'):
                parse_terminal_control(raw)

    def test_open_websocket_closes_after_capability_revocation(self):
        waiting = threading.Event()
        release = threading.Event()

        class IdentityStub:
            revoked = False

            def actor(self, _token):
                return ActorContext('account', 'session', 'member', 1)

            def require(self, _actor, _capability):
                if self.revoked:
                    raise IdentityError('FORBIDDEN')

        class ConnectionStub:
            def read(self):
                waiting.set()
                release.wait(5)
                return b''

            def close(self):
                release.set()

        class ServiceStub:
            def attach(self, _actor, _terminal_id):
                return ConnectionStub()

        identity = IdentityStub()
        app = FastAPI()
        app.include_router(terminal_router(ServiceStub(), identity, 'fixture-secret' * 3))
        try:
            with TestClient(app) as client:
                with client.websocket_connect('/api/v1/ws/terminals/fixture',
                    headers={'origin': 'http://testserver', 'cookie': 'aether_session=fixture'}) as ws:
                    self.assertTrue(waiting.wait(5))
                    identity.revoked = True
                    self.assertEqual(ws.receive(), {'type': 'websocket.close', 'code': 4403, 'reason': ''})
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()

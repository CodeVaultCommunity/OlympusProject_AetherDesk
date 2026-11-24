import tempfile
import gzip
import unittest
import uuid
from pathlib import Path

import httpx

from apps.AetherDesk.identity import ActorContext
from .proxy import WorkloadProxy
from .proxy_policy import ProxyRoute
from .service import WorkloadError


class ProxyTests(unittest.TestCase):
    def test_owner_route_host_pin_headers_redirect_and_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            other = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            workload_id = str(uuid.uuid4())
            host = workload_id.replace('-', '')[:12] + '.apps.local'
            seen = []
            def upstream(request):
                seen.append(request)
                if request.url.path == '/redirect':
                    return httpx.Response(302, headers={'Location': 'http://169.254.169.254/'})
                if request.url.path == '/compressed':
                    return httpx.Response(200, content=gzip.compress(b'plain'),
                                          headers={'Content-Encoding': 'gzip'})
                return httpx.Response(200, content=b'hello', headers={'Set-Cookie': 'token=unsafe'})
            current = ['172.30.0.2']
            proxy = WorkloadProxy(Path(directory) / 'route.sqlite3', lambda _a, _c: None,
                lambda _a: True, lambda _owner, _id: current[0], httpx.MockTransport(upstream))
            route = ProxyRoute(actor.account_id, workload_id, host, 8080,
                               '172.30.0.2', '172.30.0.0/24')
            proxy.register(route)
            proxy.register(route)
            status, headers, data = proxy.request(actor, host, 'GET', '/ok',
                {'Authorization': 'secret', 'Cookie': 'private=1', 'X-Test': 'safe'})
            self.assertEqual((status, data), (200, b'hello'))
            self.assertNotIn('set-cookie', headers)
            self.assertEqual(seen[0].headers['host'], host)
            self.assertNotIn('authorization', seen[0].headers)
            self.assertNotIn('cookie', seen[0].headers)
            compressed_status, compressed_headers, compressed_data = proxy.request(
                actor, host, 'GET', '/compressed', {})
            self.assertEqual((compressed_status, compressed_data), (200, b'plain'))
            self.assertNotIn('content-encoding', compressed_headers)
            self.assertEqual(seen[-1].headers['accept-encoding'], 'identity')
            with self.assertRaisesRegex(WorkloadError, 'PROXY_DENIED'):
                proxy.request(other, host, 'GET', '/', {})
            with self.assertRaisesRegex(WorkloadError, 'PROXY_REDIRECT_DENIED'):
                proxy.request(actor, host, 'GET', '/redirect', {})
            current[0] = '172.30.0.3'
            with self.assertRaisesRegex(WorkloadError, 'PROXY_DENIED'):
                proxy.request(actor, host, 'GET', '/', {})
            with self.assertRaisesRegex(WorkloadError, 'ROUTE_COLLISION'):
                proxy.register(ProxyRoute(other.account_id, workload_id, host, 8080,
                                          '172.30.0.2', '172.30.0.0/24'))


if __name__ == '__main__':
    unittest.main()

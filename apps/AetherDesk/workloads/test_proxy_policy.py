import unittest

from .proxy_policy import ProxyRoute, authorize_route
from .service import WorkloadError


class ProxyPolicyTests(unittest.TestCase):
    def test_owner_host_and_ip_are_pinned_against_ssrf_and_rebinding(self):
        route = ProxyRoute('owner', 'workload', 'api.example.test', 8080,
                           '172.28.5.10', '172.28.0.0/16')
        self.assertEqual(authorize_route(route, owner_id='owner', workload_id='workload',
            host_header='api.example.test', current_container_ip='172.28.5.10'), ('172.28.5.10', 8080))
        for kwargs in ({'owner_id': 'other'}, {'host_header': '169.254.169.254'},
                       {'current_container_ip': '172.28.5.11'}):
            values = {'owner_id': 'owner', 'workload_id': 'workload',
                      'host_header': 'api.example.test', 'current_container_ip': '172.28.5.10'}
            values.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(WorkloadError, 'PROXY_DENIED'):
                authorize_route(route, **values)
        metadata = ProxyRoute('owner', 'workload', 'api.example.test', 8080,
                              '169.254.169.254', '169.254.0.0/16')
        with self.assertRaisesRegex(WorkloadError, 'PROXY_DENIED'):
            authorize_route(metadata, owner_id='owner', workload_id='workload',
                            host_header='api.example.test', current_container_ip='169.254.169.254')


if __name__ == '__main__':
    unittest.main()

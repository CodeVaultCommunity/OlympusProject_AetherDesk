import unittest

from .manifest import parse_manifest
from .service import WorkloadError


class ManifestTests(unittest.TestCase):
    def test_restricted_manifest_and_hostile_features(self):
        approved = frozenset({'python-approved'})
        self.assertEqual(parse_manifest('version: 1\nname: api\ntemplate: python-approved\nport: 8080\nhealth_path: /health\n', approved),
                         {'version': 1, 'name': 'api', 'template': 'python-approved',
                          'port': 8080, 'health_path': '/health'})
        for text in ('version: 1\nname: api\ntemplate: !shell evil',
                     'version: 1\nname: api\ntemplate: python-approved\nprivileged: true',
                     'version: 1\nname: api\ntemplate: python-approved\nport: 80\nport: 81',
                     'version: 1\nname: api\ntemplate: python-approved\nhealth_path: //metadata'):
            with self.subTest(text=text), self.assertRaises(WorkloadError):
                parse_manifest(text, approved)


if __name__ == '__main__':
    unittest.main()

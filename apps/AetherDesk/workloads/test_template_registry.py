import hashlib
import hmac
import json
import unittest

from .service import WorkloadError
from .template_registry import TemplateRegistry


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


class TemplateRegistryTests(unittest.TestCase):
    def test_signed_attestations_bind_digest_and_scan_policy(self):
        key = b'fixture-key-with-at-least-32-bytes!!'
        registry = TemplateRegistry(key)
        image = 'example/app@sha256:' + 'a' * 64
        sbom = encoded({'spdxVersion': 'SPDX-2.3', 'packages': []})
        provenance = encoded({'subject': image, 'builder': 'fixture'})
        scan = encoded({'subject': image, 'critical': 0, 'high': 0})
        manifest = {'name': 'approved', 'image': image, 'command': ['sleep', '60'],
                    'sbom_sha256': hashlib.sha256(sbom).hexdigest(),
                    'provenance_sha256': hashlib.sha256(provenance).hexdigest(),
                    'scan_sha256': hashlib.sha256(scan).hexdigest()}
        manifest['signature'] = hmac.new(key, encoded(manifest), hashlib.sha256).hexdigest()
        payload = encoded(manifest)
        self.assertEqual(registry.load(payload, sbom, provenance, scan).image, image)
        with self.assertRaisesRegex(WorkloadError, 'ATTESTATION_MISMATCH'):
            registry.load(payload, sbom + b' ', provenance, scan)
        bad_scan = encoded({'subject': image, 'critical': 1, 'high': 0})
        manifest['scan_sha256'] = hashlib.sha256(bad_scan).hexdigest()
        manifest['signature'] = hmac.new(key, encoded({key: value for key, value in manifest.items() if key != 'signature'}), hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(WorkloadError, 'SCAN_POLICY_DENIED'):
            registry.load(encoded(manifest), sbom, provenance, bad_scan)


if __name__ == '__main__':
    unittest.main()

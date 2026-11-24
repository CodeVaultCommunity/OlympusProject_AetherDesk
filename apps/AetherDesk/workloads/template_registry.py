"""Entrada de template com digest, SBOM, provenance e scan atestados."""

from __future__ import annotations

import hashlib
import hmac
import json

from .service import ApprovedTemplate, WorkloadError


def _json(value: bytes) -> dict:
    if len(value) > 1024 * 1024:
        raise WorkloadError('INVALID_ATTESTATION')
    try:
        parsed = json.loads(value)
    except (UnicodeError, ValueError) as exc:
        raise WorkloadError('INVALID_ATTESTATION') from exc
    if type(parsed) is not dict:
        raise WorkloadError('INVALID_ATTESTATION')
    return parsed


class TemplateRegistry:
    def __init__(self, trusted_signing_key: bytes):
        if not isinstance(trusted_signing_key, bytes) or len(trusted_signing_key) < 32:
            raise WorkloadError('INVALID_SIGNING_KEY')
        self.key = trusted_signing_key

    def load(self, manifest_bytes: bytes, sbom_bytes: bytes,
             provenance_bytes: bytes, scan_bytes: bytes) -> ApprovedTemplate:
        manifest = _json(manifest_bytes)
        signature = manifest.pop('signature', None)
        if not isinstance(signature, str):
            raise WorkloadError('UNTRUSTED_TEMPLATE')
        canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False).encode('utf-8')
        expected = hmac.new(self.key, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise WorkloadError('UNTRUSTED_TEMPLATE')
        if set(manifest) - {'name', 'image', 'sbom_sha256', 'provenance_sha256',
                            'scan_sha256', 'command', 'health_command', 'port'} or not {'name', 'image', 'sbom_sha256',
                            'provenance_sha256', 'scan_sha256', 'command'} <= set(manifest):
            raise WorkloadError('INVALID_ATTESTATION')
        for blob, field in ((sbom_bytes, 'sbom_sha256'), (provenance_bytes, 'provenance_sha256'),
                            (scan_bytes, 'scan_sha256')):
            if not hmac.compare_digest(hashlib.sha256(blob).hexdigest(), manifest[field]):
                raise WorkloadError('ATTESTATION_MISMATCH')
        sbom, provenance, scan = _json(sbom_bytes), _json(provenance_bytes), _json(scan_bytes)
        if (sbom.get('spdxVersion') != 'SPDX-2.3' or type(sbom.get('packages')) is not list or
                provenance.get('subject') != manifest['image'] or
                scan.get('subject') != manifest['image'] or
                type(scan.get('critical')) is not int or type(scan.get('high')) is not int or
                scan['critical'] != 0 or scan['high'] != 0):
            raise WorkloadError('SCAN_POLICY_DENIED')
        command = manifest['command']
        if type(command) is not list or len(command) > 20:
            raise WorkloadError('INVALID_ATTESTATION')
        template = ApprovedTemplate(manifest['name'], manifest['image'], manifest['sbom_sha256'],
                                    manifest['provenance_sha256'], True, tuple(command),
                                    manifest.get('health_command'), manifest.get('port'))
        template.validate()
        return template

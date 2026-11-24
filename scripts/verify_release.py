"""Confere integridade e licenças diretas do candidate, sem consultar a rede."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'MIT', 'MIT-0', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause',
           'Apache-2.0 OR BSD-3-Clause', 'ISC', 'MPL-2.0'}


def verify(directory: Path) -> dict:
    archive = directory / 'aetherdesk-candidate.zip'
    expected_hash, expected_name = (directory / 'SHA256SUMS').read_text().split()
    if expected_name != archive.name or hashlib.sha256(archive.read_bytes()).hexdigest() != expected_hash:
        raise RuntimeError('RELEASE_DIGEST_MISMATCH')
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(names) != len(set(names)) or any(name.startswith('/') or '..' in Path(name).parts
                                               for name in names):
            raise RuntimeError('RELEASE_INVALID_ENTRY')
        manifest = json.loads(package.read('release/manifest.json'))
        sbom = json.loads(package.read('release/sbom.spdx.json'))
        if names != sorted(names) or set(names) != set(manifest['files']) | {
                'release/manifest.json', 'release/sbom.spdx.json'}:
            raise RuntimeError('RELEASE_MANIFEST_MISMATCH')
        for name, expected in manifest['files'].items():
            if hashlib.sha256(package.read(name)).hexdigest() != expected:
                raise RuntimeError('RELEASE_FILE_MISMATCH: ' + name)
        if package.read('release/manifest.json') != (directory / 'manifest.json').read_bytes():
            raise RuntimeError('RELEASE_MANIFEST_MISMATCH')
        if package.read('release/sbom.spdx.json') != (directory / 'sbom.spdx.json').read_bytes():
            raise RuntimeError('RELEASE_SBOM_MISMATCH')
    if sbom.get('spdxVersion') != 'SPDX-2.3':
        raise RuntimeError('INVALID_SBOM')
    if any(item.get('licenseDeclared') in (None, '', 'NOASSERTION') for item in sbom['packages']):
        raise RuntimeError('LICENSE_REVIEW_REQUIRED: unresolved package')
    versions = {}
    for item in sbom['packages']:
        versions.setdefault(item['name'].lower().replace('_', '-'), []).append(item)
    web = json.loads((ROOT / 'web/package.json').read_text())
    python = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    direct = set(web['dependencies']) | {
        requirement.split('>=', 1)[0].split('==', 1)[0].lower().replace('_', '-')
        for requirement in python['project']['dependencies']}
    for name in direct:
        matches = versions.get(name.lower().replace('_', '-'), [])
        if not matches or any(item['licenseDeclared'] not in ALLOWED for item in matches):
            raise RuntimeError('LICENSE_REVIEW_REQUIRED: ' + name)
    return {'sha256': expected_hash, 'files': len(manifest['files']),
            'packages': len(sbom['packages']), 'licensesDeclared': len(sbom['packages']),
            'directLicensesChecked': len(direct)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=ROOT / '.tmp/release-candidate')
    print(json.dumps(verify(parser.parse_args().directory.resolve()), sort_keys=True))

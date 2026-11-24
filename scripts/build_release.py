"""Produz candidate local reproduzível com hashes e inventário SPDX dos locks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from importlib import metadata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILE_TYPES = {'.py', '.sql', '.service', '.txt'}
PLATFORM_LICENSES = {('pywin32', '312'): 'PSF'}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def license_index() -> dict[tuple[str, str], str]:
    result = {}
    stores = ROOT / 'web/node_modules/.pnpm'
    if not stores.is_dir():
        return result
    for store in stores.iterdir():
        modules = store / 'node_modules'
        if not modules.is_dir():
            continue
        for entry in modules.iterdir():
            paths = entry.iterdir() if entry.name.startswith('@') and entry.is_dir() else (entry,)
            for package in paths:
                path = package / 'package.json'
                if not path.is_file():
                    continue
                try:
                    info = json.loads(path.read_text(encoding='utf-8'))
                except (ValueError, UnicodeError):
                    continue
                declared = info.get('license', 'NOASSERTION')
                if isinstance(declared, dict):
                    declared = declared.get('type', 'NOASSERTION')
                result[(info.get('name'), info.get('version'))] = str(declared)
    return result


def npm_license(name: str, version: str, installed: dict[tuple[str, str], str]) -> tuple[str, str | None]:
    declared = installed.get((name, version))
    if declared:
        return declared, None
    # Binários opcionais são publicados com a mesma licença do pacote-fonte
    # na versão exata. Metadados upstream: github.com/evanw/esbuild e
    # github.com/rollup/rollup (diretórios npm/ da plataforma).
    for prefix, parent in (('@esbuild/', 'esbuild'), ('@rollup/rollup-', 'rollup')):
        if name.startswith(prefix) and installed.get((parent, version)) == 'MIT':
            return 'MIT', f'Licença do pacote-fonte {parent}@{version} (mesma versão)'
    # Metadados do pacote oficial: github.com/fsevents/fsevents/blob/master/package.json
    if name == 'fsevents' and version == '2.3.3':
        return 'MIT', 'Licença declarada nos metadados upstream de fsevents@2.3.3'
    return 'NOASSERTION', None


def sbom() -> dict:
    packages = []
    requirements = (ROOT / 'deploy/requirements.txt').read_text(encoding='utf-8')
    for name, version in re.findall(r'^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.-]+)',
                                    requirements, re.MULTILINE):
        try:
            distribution = metadata.distribution(name)
            license_name = distribution.metadata.get('License-Expression') or distribution.metadata.get('License')
        except metadata.PackageNotFoundError:
            license_name = None
        # pywin32 is pinned in the cross-platform lock but absent on Linux runners.
        license_name = license_name or PLATFORM_LICENSES.get((name.lower(), version))
        packages.append({'SPDXID': f'SPDXRef-Py-{name.replace("_", "-")}',
                         'name': name, 'versionInfo': version, 'downloadLocation': 'NOASSERTION',
                         'filesAnalyzed': False, 'licenseDeclared': license_name or 'NOASSERTION',
                         'externalRefs': [{'referenceCategory': 'PACKAGE-MANAGER',
                                           'referenceType': 'purl',
                                           'referenceLocator': f'pkg:pypi/{name.lower()}@{version}'}]})
    lock = (ROOT / 'web/pnpm-lock.yaml').read_text(encoding='utf-8')
    package_section = lock.split('\npackages:\n', 1)[1].split('\nsnapshots:\n', 1)[0]
    npm_licenses = license_index()
    for item in re.findall(r"^  ['\"]?([^\n'\"]+@[^\n'\"]+)['\"]?:\s*$",
                           package_section, re.MULTILINE):
        name, version = item.rsplit('@', 1)
        name = name.lstrip('/')
        if not name or not version:
            continue
        slug = re.sub(r'[^A-Za-z0-9.-]', '-', name + '-' + version)
        license_name, source = npm_license(name, version, npm_licenses)
        entry = {'SPDXID': f'SPDXRef-Npm-{slug}', 'name': name,
                         'versionInfo': version, 'downloadLocation': 'NOASSERTION',
                         'filesAnalyzed': False,
                         'licenseDeclared': license_name,
                         'externalRefs': [{'referenceCategory': 'PACKAGE-MANAGER',
                                           'referenceType': 'purl',
                                           'referenceLocator': f'pkg:npm/{name}@{version}'}]}
        if source:
            entry['sourceInfo'] = source
        packages.append(entry)
    lock_hash = digest((requirements + lock).encode())
    return {'spdxVersion': 'SPDX-2.3', 'dataLicense': 'CC0-1.0',
            'SPDXID': 'SPDXRef-DOCUMENT', 'name': 'AetherDesk release candidate dependencies',
            'documentNamespace': f'https://aetherdesk.invalid/spdx/{lock_hash}',
            'creationInfo': {'created': '1980-01-01T00:00:00Z', 'creators': ['Tool: build_release.py']},
            'packages': packages}


def candidate_files() -> list[Path]:
    files = [ROOT / name for name in ('launch.py', 'pyproject.toml', 'uv.lock',
             'web/package.json', 'web/pnpm-lock.yaml', 'docs/L3_Vulcan/operations.md')]
    files.extend(path for path in (ROOT / 'deploy').rglob('*') if path.is_file())
    files.extend(path for path in (ROOT / 'apps/AetherDesk').rglob('*') if path.is_file()
                 and (path.suffix in FILE_TYPES or path.name == 'Dockerfile')
                 and not path.name.startswith('test_') and '__pycache__' not in path.parts)
    distribution = ROOT / 'web/dist'
    if not (distribution / 'index.html').is_file():
        raise RuntimeError('Execute pnpm build antes de criar o candidate')
    files.extend(path for path in distribution.rglob('*') if path.is_file())
    for path in files:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError(f'Entrada inválida: {path}')
    return sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())


def build(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source = candidate_files()
    manifest = {'format': 1, 'apiVersion': 2,
                'files': {path.relative_to(ROOT).as_posix(): digest(path.read_bytes())
                          for path in source}}
    bom = sbom()
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    bom_bytes = (json.dumps(bom, sort_keys=True, indent=2) + '\n').encode()
    archive = output / 'aetherdesk-candidate.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as package:
        for name, data in sorted({**{path.relative_to(ROOT).as_posix(): path.read_bytes()
                                         for path in source},
                                  'release/manifest.json': manifest_bytes,
                                  'release/sbom.spdx.json': bom_bytes}.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            package.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    (output / 'manifest.json').write_bytes(manifest_bytes)
    (output / 'sbom.spdx.json').write_bytes(bom_bytes)
    archive_hash = digest(archive.read_bytes())
    (output / 'SHA256SUMS').write_text(f'{archive_hash}  {archive.name}\n', encoding='utf-8')
    return {'archive': str(archive), 'sha256': archive_hash,
            'files': len(source), 'packages': len(bom['packages'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.tmp/release-candidate')
    print(json.dumps(build(parser.parse_args().output.resolve()), sort_keys=True))

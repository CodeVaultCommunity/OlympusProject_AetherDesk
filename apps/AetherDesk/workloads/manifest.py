"""Subset explícito de .aetherdesk/deploy.yaml; nenhuma tag ou âncora YAML."""

from __future__ import annotations

import re

from .service import WorkloadError


def parse_manifest(contents: str, approved_templates: frozenset[str]) -> dict:
    if not isinstance(contents, str) or len(contents.encode('utf-8')) > 4096:
        raise WorkloadError('INVALID_MANIFEST')
    values: dict[str, str] = {}
    for line in contents.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if ('\t' in line or any(marker in line for marker in ('&', '*', '!', '|', '>', '{', '}', '[', ']')) or
                not re.fullmatch(r'[a-z_]+: [A-Za-z0-9_./-]+', line)):
            raise WorkloadError('INVALID_MANIFEST')
        key, value = line.split(': ', 1)
        if key in values or key not in {'version', 'name', 'template', 'port', 'health_path'}:
            raise WorkloadError('INVALID_MANIFEST')
        values[key] = value
    if values.get('version') != '1' or not re.fullmatch(r'[a-z][a-z0-9-]{0,50}', values.get('name', '')):
        raise WorkloadError('INVALID_MANIFEST')
    if values.get('template') not in approved_templates:
        raise WorkloadError('UNAPPROVED_TEMPLATE')
    port = values.get('port')
    if port is not None and (not port.isdigit() or not 1 <= int(port) <= 65535):
        raise WorkloadError('INVALID_PORT')
    health = values.get('health_path')
    if health is not None and (not health.startswith('/') or health.startswith('//') or
                               '..' in health or not re.fullmatch(r'/[A-Za-z0-9_./-]*', health)):
        raise WorkloadError('INVALID_HEALTH_PATH')
    return {'version': 1, 'name': values['name'], 'template': values['template'],
            'port': int(port) if port else None, 'health_path': health}

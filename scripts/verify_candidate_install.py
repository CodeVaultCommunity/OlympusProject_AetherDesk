"""Importa o candidate extraído fora da árvore de desenvolvimento."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


CHECK = '''
import importlib.util
from pathlib import Path
from launch import create_app
app = create_app()
paths = {route.path for route in app.routes if hasattr(route, 'path')}
paths.update(route.path for included in app.routes if hasattr(included, 'original_router')
             for route in included.original_router.routes)
assert {'/healthz', '/readyz', '/api/v1/login', '/api/v2/workloads/mine',
        '/api/v2/workspace/tree', '/api/v2/ai/providers'} <= paths, paths
assert (Path.cwd() / 'web/dist/index.html').is_file()
assert importlib.util.find_spec('apps.AetherDesk.workloads.gateway') is not None
print('CANDIDATE_IMPORT_OK', len(paths))
'''


def verify(archive: Path) -> str:
    with tempfile.TemporaryDirectory(prefix='aetherdesk-candidate-') as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive) as package:
            package.extractall(root)
        env = os.environ.copy()
        env.update({
            'AETHERDESK_DATA_DIR': str(root / 'data'),
            'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
            'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
            'AETHERDESK_BROKER_SECRET_B64': 'YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=',
            'AETHERDESK_FEATURES': 'ide,workloads,ai',
            'AETHERDESK_ENABLE_WORKLOAD_PROXY': '1',
            'AETHERDESK_SAFE_MODE': '0',
            'AETHERDESK_KILL_AI': '0',
            'PYTHONPATH': str(root),
        })
        result = subprocess.run([sys.executable, '-c', CHECK], cwd=root, env=env,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('CANDIDATE_IMPORT_FAILED: ' + result.stderr[-1000:])
        return result.stdout.strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, default=Path('.tmp/release-candidate/aetherdesk-candidate.zip'))
    print(verify(parser.parse_args().archive.resolve()))

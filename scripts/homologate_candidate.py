"""Run the complete regression against modules extracted from an immutable ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def homologate(archive: Path, expected_sha256: str, selected: list[str] | None = None) -> None:
    actual_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(f'CANDIDATE_DIGEST_MISMATCH: {actual_sha256}')
    with tempfile.TemporaryDirectory(prefix='aetherdesk-w006-') as directory:
        candidate = Path(directory)
        with zipfile.ZipFile(archive) as package:
            manifest = json.loads(package.read('release/manifest.json'))
            for name, expected in manifest['files'].items():
                if hashlib.sha256(package.read(name)).hexdigest() != expected:
                    raise RuntimeError(f'CANDIDATE_FILE_MISMATCH: {name}')
            package.extractall(candidate)
        tests = sorted((ROOT / 'apps/AetherDesk').rglob('test_*.py'))
        for source in tests:
            target = candidate / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        sys.path.insert(0, str(candidate))
        os.chdir(candidate)
        from launch import create_app
        import apps.AetherDesk.identity as identity

        for module in (sys.modules['launch'], identity):
            if not Path(module.__file__).resolve().is_relative_to(candidate):
                raise RuntimeError(f'Non-candidate module loaded: {module.__file__}')
        with patch.dict(os.environ, {
            'AETHERDESK_DATA_DIR': str(candidate / 'data'),
            'AETHERDESK_BOOTSTRAP_TOKEN': 'fixture-bootstrap-token',
            'AETHERDESK_CSRF_SECRET': 'fixture-csrf-secret-with-32-characters',
            'AETHERDESK_BROKER_SECRET_B64': 'YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=',
            'AETHERDESK_FEATURES': 'ide,workloads,ai',
        }):
            if not create_app():
                raise RuntimeError('Candidate app unavailable')
        names = selected or ['.'.join(source.relative_to(ROOT).with_suffix('').parts)
                             for source in tests]
        suite = unittest.defaultTestLoader.loadTestsFromNames(names)
        outcome = unittest.TextTestRunner(verbosity=1).run(suite)
        expected_count = len(selected) if selected else 138
        if not outcome.wasSuccessful() or outcome.skipped or outcome.testsRun < expected_count:
            raise RuntimeError('CANDIDATE_REGRESSION_FAILED_OR_INCOMPLETE')
        print(json.dumps({'status': 'CANDIDATE_REGRESSION_OK',
                          'sha256': actual_sha256, 'tests': outcome.testsRun,
                          'skipped': len(outcome.skipped)}, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--test', action='append')
    args = parser.parse_args()
    homologate(args.archive.resolve(), args.sha256, args.test)

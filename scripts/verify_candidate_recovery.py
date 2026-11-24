"""Exercise packaged production modules with disposable recovery fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    'apps/AetherDesk/composition/test_upgrade.py',
    'apps/AetherDesk/backup/test_service.py',
    'apps/AetherDesk/workloads/test_service.py',
)
TESTS = (
    'apps.AetherDesk.composition.test_upgrade.UpgradeTests',
    'apps.AetherDesk.backup.test_service.BackupTests',
)


class TimedResult(unittest.TextTestResult):
    def startTest(self, test: unittest.TestCase) -> None:
        self._started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test: unittest.TestCase) -> None:
        elapsed = time.perf_counter() - self._started
        print(f'CANDIDATE_RECOVERY_DURATION test={test.id()} seconds={elapsed:.3f}')
        super().stopTest(test)


def verify(archive: Path) -> None:
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='aetherdesk-recovery-') as directory:
        candidate = Path(directory)
        with zipfile.ZipFile(archive) as package:
            manifest = json.loads(package.read('release/manifest.json'))
            for name, expected in manifest['files'].items():
                if hashlib.sha256(package.read(name)).hexdigest() != expected:
                    raise RuntimeError(f'Candidate hash mismatch: {name}')
            package.extractall(candidate)
        for relative in FIXTURES:
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

        sys.path.insert(0, str(candidate))
        os.chdir(candidate)
        import apps.AetherDesk.backup.service as backup_service
        import apps.AetherDesk.identity as identity

        for module in (backup_service, identity):
            if not Path(module.__file__).resolve().is_relative_to(candidate):
                raise RuntimeError(f'Source tree imported instead of candidate: {module.__file__}')
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name)
                                   for name in TESTS)
        outcome = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(suite)
        if not outcome.wasSuccessful() or outcome.testsRun != 3 or outcome.skipped:
            raise RuntimeError('Candidate recovery suite failed or was incomplete')
        print(f'CANDIDATE_RECOVERY_OK sha256={archive_hash} tests={outcome.testsRun}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    verify(parser.parse_args().archive.resolve())

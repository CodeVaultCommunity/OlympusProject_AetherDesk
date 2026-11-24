import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from apps.AetherDesk.files import FileError, LinuxFileService


@unittest.skipUnless(os.name == "posix", "requer Linux")
class LinuxFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.files = LinuxFileService(self.temp.name)
        self.addCleanup(self.files.close)

    def test_operations_conflict_and_external_change(self):
        self.files.mkdir("/project")
        self.assertEqual(self.files.write("/project/main.py", b"print('a')\n"),
                         self.files.read("/project/main.py")[1])
        self.assertEqual(self.files.list("/project")[0]["name"], "main.py")
        with self.assertRaises(FileError) as raised:
            self.files.write("/project/main.py", b"overwrite")
        self.assertEqual(raised.exception.code, "CONFLICT")
        old_hash = self.files.read("/project/main.py")[1]
        subprocess.run(["bash", "-c", "printf external > main.py"],
                       cwd=Path(self.temp.name) / "project", check=True)
        self.assertEqual(self.files.read("/project/main.py")[0], b"external")
        with self.assertRaises(FileError) as raised:
            self.files.write("/project/main.py", b"editor", expected_hash=old_hash)
        self.assertEqual(raised.exception.code, "STALE_REVISION")
        current_hash = self.files.read("/project/main.py")[1]
        self.files.write("/project/main.py", b"editor", expected_hash=current_hash)
        self.files.copy("/project/main.py", "/project/copy.py")
        self.files.move("/project/copy.py", "/project/moved.py")
        self.assertEqual(self.files.read("/project/moved.py")[0], b"editor")
        self.files.delete("/project")
        with self.assertRaises(FileError):
            self.files.list("/project")

    def test_traversal_and_symlink_cannot_leave_root(self):
        (Path(self.temp.name) / "outside").symlink_to("/etc/passwd")
        with self.assertRaises(FileError):
            self.files.read("/../etc/passwd")
        with self.assertRaises(FileError):
            self.files.read("/outside")
        with self.assertRaises(FileError):
            self.files.write("/outside", b"no")
        self.files.delete("/outside")
        self.assertFalse((Path(self.temp.name) / "outside").exists())

    def test_listing_limit_bounds_agent_output(self):
        root = Path(self.temp.name)
        for name in ('one', 'two', 'three'):
            (root / name).touch()
        with LinuxFileService(root, max_list_entries=3) as files:
            self.assertEqual(len(files.list('/')), 3)
        with LinuxFileService(root, max_list_entries=2) as files:
            with self.assertRaises(FileError) as raised:
                files.list('/')
            self.assertEqual(raised.exception.code, 'TOO_LARGE')


if __name__ == "__main__":
    unittest.main()

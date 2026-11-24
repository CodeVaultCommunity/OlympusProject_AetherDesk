import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .watcher import LinuxWatcher


@unittest.skipUnless(sys.platform == 'linux', 'inotify requer Linux')
class WatcherTests(unittest.TestCase):
    def test_bash_change_arrives_as_event_without_polling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with LinuxWatcher(root) as watcher:
                subprocess.run(['bash', '-c', 'printf hello > changed.txt'],
                               cwd=root, check=True, timeout=5)
                events = watcher.next_events(timeout=3)
                self.assertTrue(any(event['path'] == 'changed.txt' and
                                    event['kind'] in ('created', 'changed') for event in events))


if __name__ == '__main__':
    unittest.main()

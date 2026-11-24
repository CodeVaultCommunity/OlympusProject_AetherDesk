import tempfile
import unittest
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from .lsp import LanguageServer, LspError, LspService


class Runner:
    def __init__(self):
        self.calls = []

    def request(self, *args):
        self.calls.append(args)
        return {'diagnostics': []}


class LspTests(unittest.TestCase):
    def test_disabled_by_default_and_broker_contract_is_path_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'ws'
            root.mkdir()
            actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
            runner = Runner()
            server = LanguageServer('python', 'sha256:' + 'a' * 64)
            disabled = LspService(root, actor.account_id, 'ws1', lambda *_: None, lambda _: True,
                                  runner, {'python': server})
            with self.assertRaisesRegex(LspError, 'LSP_DISABLED'):
                disabled.request(actor, 'python', 'main.py', 'diagnostics', 'x')
            service = LspService(root, actor.account_id, 'ws1', lambda *_: None, lambda _: True,
                                 runner, {'python': server}, frozenset({'python'}))
            for path in ('../escape.py', '/tmp/escape.py'):
                with self.assertRaisesRegex(LspError, 'INVALID_PATH'):
                    service.request(actor, 'python', path, 'diagnostics', 'x')
            self.assertEqual(service.request(actor, 'python', 'main.py', 'diagnostics', 'x'), {'diagnostics': []})
            self.assertEqual(runner.calls[0][3:], ('main.py', 'diagnostics', 'x'))


if __name__ == '__main__':
    unittest.main()

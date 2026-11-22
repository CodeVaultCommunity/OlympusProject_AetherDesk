import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from apps.AetherDesk.identity import IdentityError, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from apps.AetherDesk.terminal import TerminalService


@unittest.skipUnless(os.environ.get("AETHERDESK_DOCKER_TEST") == "1", "requer Docker Linux descartável")
class TerminalTests(unittest.TestCase):
    def test_pty_reconnect_and_revocation(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = IdentityService(Path(temp) / "identity.sqlite3", "bootstrap-secret-long")
            identity.bootstrap("bootstrap-secret-long", "admin", "strong-admin-password")
            _, admin = identity.login("admin", "strong-admin-password")
            account_id = identity.create_account(admin, "alice", "strong-alice-password")
            token, alice = identity.login("alice", "strong-alice-password")
            env_id = identity.account(admin, account_id)["environment_id"]
            runtime = DockerEnvironmentBroker("aetherdesk-terminal:w003")
            container, volume = runtime._names(env_id)
            terminal = TerminalService(Path(temp) / "terminal.sqlite3", identity, runtime)
            try:
                terminal_id = terminal.create(alice)
                self.assertEqual(len(terminal.list(alice)), 1)
                connection = terminal.attach(alice, terminal_id)
                connection.socket.settimeout(5)
                connection.write(b"cd /; echo AETHER_MARK; pwd\r")
                self.assertTrue(connection.read())
                screen = runtime.exec(account_id, env_id, ["tmux", "-L", "aether", "capture-pane", "-p", "-t", terminal_id])
                self.assertIn("AETHER_MARK", screen)
                self.assertIn("\n/\n", screen)
                second_id = terminal.create(alice)
                second = terminal.attach(alice, second_id)
                second.socket.settimeout(5)
                second.write(b"cd /persist; pwd\r")
                self.assertTrue(second.read())
                second_screen = runtime.exec(account_id, env_id, ["tmux", "-L", "aether", "capture-pane", "-p", "-t", second_id])
                self.assertIn("/persist", second_screen)
                second.close()
                connection.resize(100, 30)
                connection.write(b"sleep 30\r")
                time.sleep(0.4)
                connection.write(b"\x03echo AFTER_INT\r")
                time.sleep(0.4)
                screen = runtime.exec(account_id, env_id, ["tmux", "-L", "aether", "capture-pane", "-p", "-t", terminal_id])
                self.assertIn("AFTER_INT", screen)
                connection.close()
                identity.logout(token)
                _, alice2 = identity.login("alice", "strong-alice-password")
                reconnected = terminal.attach(alice2, terminal_id)
                reconnected.socket.settimeout(5)
                reconnected.write(b"pwd\r")
                self.assertTrue(reconnected.read())
                screen = runtime.exec(account_id, env_id, ["tmux", "-L", "aether", "capture-pane", "-p", "-t", terminal_id])
                self.assertIn("pwd\n/", screen)
                identity.revoke_session(admin, alice2.session_id)
                with self.assertRaises(IdentityError):
                    reconnected.write(b"echo denied\r")
                reconnected.close()
                _, alice3 = identity.login("alice", "strong-alice-password")
                terminal.close(alice3, terminal_id)
                self.assertEqual(terminal.list(alice3)[0]["state"], "closed")
            finally:
                subprocess.run(["docker", "container", "rm", "--force", container], capture_output=True)
                subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    unittest.main()

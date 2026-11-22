import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from apps.AetherDesk.composition import AppComposition
from apps.AetherDesk.identity import IdentityError, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


@unittest.skipUnless(os.environ.get("AETHERDESK_DOCKER_TEST") == "1", "requer Docker Linux descartável")
class CompositionTests(unittest.TestCase):
    def test_logout_revoke_stop_and_delete_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = IdentityService(Path(temp) / "db.sqlite3", "bootstrap-token-long-enough")
            identity.bootstrap("bootstrap-token-long-enough", "admin", "strong-admin-password")
            _, admin = identity.login("admin", "strong-admin-password")
            account_id = identity.create_account(admin, "alice", "strong-alice-password")
            token, alice = identity.login("alice", "strong-alice-password")
            runtime = DockerEnvironmentBroker("aetherdesk-runtime:w002")
            app = AppComposition(identity, runtime)
            environment_id = identity.account(admin, account_id)["environment_id"]
            container, volume = runtime._names(environment_id)
            try:
                app.ensure_personal_environment(alice)
                runtime.exec(account_id, environment_id, ["bash", "-lc", "printf dados >/dados.txt"])
                pid = runtime.exec(account_id, environment_id,
                                   ["bash", "-lc", "sleep 120 </dev/null >/persist/bg.log 2>&1 & echo $!"])
                identity.logout(token)
                runtime.exec(account_id, environment_id, ["bash", "-lc", f"kill -0 {pid}"])
                _, alice2 = identity.login("alice", "strong-alice-password")
                identity.revoke_session(admin, alice2.session_id)
                runtime.exec(account_id, environment_id, ["bash", "-lc", f"kill -0 {pid}"])
                _, alice3 = identity.login("alice", "strong-alice-password")
                self.assertEqual(app.ensure_personal_environment(alice3).container_name, container)
                app.stop_account_session(admin, account_id)
                self.assertEqual(runtime.state(account_id, environment_id).state, "exited")
                with self.assertRaises(IdentityError):
                    identity.require(alice3, "terminal.open")
                _, alice4 = identity.login("alice", "strong-alice-password")
                app.ensure_personal_environment(alice4)
                self.assertEqual(runtime.exec(account_id, environment_id, ["bash", "-lc", "cat /dados.txt"]), "dados")
                revision = identity.account(admin, account_id)["revision"]
                identity.update_account(admin, account_id, state="deleted", revision=revision)
                app.process_account_events()
                self.assertEqual(runtime.state(account_id, environment_id).state, "absent")
                self.assertEqual(subprocess.run(["docker", "volume", "inspect", volume],
                                                capture_output=True).returncode, 0)
            finally:
                subprocess.run(["docker", "container", "rm", "--force", container], capture_output=True)
                subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    unittest.main()

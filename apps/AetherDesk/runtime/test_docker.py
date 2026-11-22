import os
import subprocess
import threading
import unittest
import uuid

from apps.AetherDesk.runtime import DockerEnvironmentBroker


@unittest.skipUnless(os.environ.get("AETHERDESK_DOCKER_TEST") == "1", "requer Docker Linux descartável")
class DockerRuntimeTests(unittest.TestCase):
    def test_isolation_reuse_and_stop_preserve_volume(self):
        broker = DockerEnvironmentBroker("aetherdesk-runtime:w002")
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        ea, eb = str(uuid.uuid4()), str(uuid.uuid4())
        names = [broker._names(ea), broker._names(eb)]
        try:
            result = []
            threads = [threading.Thread(target=lambda: result.append(broker.ensure(a, ea)))
                       for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0].container_name, result[1].container_name)
            broker.ensure(b, eb)
            self.assertEqual(broker.exec(a, ea, ["bash", "-lc", "cd /; printf alice >/dados.txt; pwd; cat /dados.txt"]),
                             "/\nalice")
            self.assertEqual(broker.exec(b, eb, ["bash", "-lc", "cd /; printf bob >/dados.txt; pwd; cat /dados.txt"]),
                             "/\nbob")
            self.assertEqual(broker.exec(a, ea, ["bash", "-lc", "cat /dados.txt"]), "alice")
            pid = broker.exec(a, ea, ["bash", "-lc", "sleep 120 </dev/null >/persist/background.log 2>&1 & echo $!"])
            self.assertTrue(pid.isdigit())
            # Reabrir o ambiente simula retorno após desconexão; o processo continua.
            broker.ensure(a, ea)
            broker.exec(a, ea, ["bash", "-lc", f"kill -0 {pid}"])
            broker.stop_session(a, ea)
            self.assertEqual(broker.state(a, ea).state, "exited")
            broker.ensure(a, ea)
            with self.assertRaises(Exception):
                broker.exec(a, ea, ["bash", "-lc", f"kill -0 {pid}"])
            self.assertEqual(broker.exec(a, ea, ["bash", "-lc", "cat /dados.txt"]), "alice")
            self.assertEqual(broker.exec(b, eb, ["bash", "-lc", "cat /dados.txt"]), "bob")
        finally:
            for container, volume in names:
                subprocess.run(["docker", "container", "rm", "--force", container],
                               capture_output=True, check=False)
                subprocess.run(["docker", "volume", "rm", volume],
                               capture_output=True, check=False)


if __name__ == "__main__":
    unittest.main()

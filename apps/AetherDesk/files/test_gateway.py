import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from apps.AetherDesk.files.gateway import ContainerFileGateway
from apps.AetherDesk.files.service import FileError
from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


@unittest.skipUnless(os.environ.get('AETHERDESK_DOCKER_TEST') == '1', 'requer Docker Linux descartável')
class GatewayTests(unittest.TestCase):
    def test_bash_and_files_share_isolated_root(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = IdentityService(Path(temp) / 'identity.sqlite3', 'bootstrap-secret-long')
            identity.bootstrap('bootstrap-secret-long', 'admin', 'strong-admin-password')
            _, admin = identity.login('admin', 'strong-admin-password')
            alice_id = identity.create_account(admin, 'alice', 'strong-alice-password')
            bob_id = identity.create_account(admin, 'bobby', 'strong-bobby-password')
            _, alice = identity.login('alice', 'strong-alice-password')
            _, bob = identity.login('bobby', 'strong-bobby-password')
            runtime = DockerEnvironmentBroker('aetherdesk-files:w003')
            gateway = ContainerFileGateway(identity, runtime)
            names = [runtime._names(identity.account(admin, account_id)['environment_id'])
                     for account_id in (alice_id, bob_id)]
            try:
                for actor, content in ((alice, b'alice'), (bob, b'bobby')):
                    revision = gateway.write(actor, '/persist/same.txt', content)
                    self.assertTrue(revision)
                    self.assertEqual(gateway.read(actor, '/persist/same.txt')[0], content)
                    with self.assertRaises(FileError):
                        gateway.call(actor, 'read', '/persist/../../etc/passwd')
                alice_env = identity.account(admin, alice_id)['environment_id']
                runtime.exec(alice_id, alice_env, ['bash', '-c', 'printf bash > /persist/from-bash.txt'])
                self.assertEqual(gateway.read(alice, '/persist/from-bash.txt')[0], b'bash')
                self.assertEqual(gateway.call(alice, 'metadata', '/')['kind'], 'directory')
                self.assertIn('from-bash.txt', [entry['name'] for entry in gateway.call(alice, 'list', '/persist')])
                self.assertEqual(gateway.read(bob, '/persist/same.txt')[0], b'bobby')
                with self.assertRaises(FileError):
                    gateway.write(alice, '/persist/same.txt', b'conflict', revision='wrong')
            finally:
                for container, volume in names:
                    subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    unittest.main()

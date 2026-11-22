"""Matriz S01–S14 no Docker Linux local; não substitui homologação em host Linux."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker
from apps.AetherDesk.terminal.service import TerminalService, TerminalError
from launch import create_app


@unittest.skipUnless(os.environ.get('AETHERDESK_DOCKER_TEST') == '1', 'requer Docker Linux descartável')
class LocalScenarios(unittest.TestCase):
    def test_s01_to_s14(self):
        with tempfile.TemporaryDirectory() as temp:
            keys = ('AETHERDESK_DATA_DIR', 'AETHERDESK_BOOTSTRAP_TOKEN',
                    'AETHERDESK_CSRF_SECRET', 'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP')
            old = {key: os.environ.get(key) for key in keys}
            os.environ.update({'AETHERDESK_DATA_DIR': temp,
                'AETHERDESK_BOOTSTRAP_TOKEN': 'bootstrap-secret-long',
                'AETHERDESK_CSRF_SECRET': 'csrf-secret-long-enough-for-testing-12345',
                'AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP': '1'})
            resources = []
            try:
                app = create_app()
                with TestClient(app) as administrator, TestClient(app) as alice_client, TestClient(app) as bob_client, TestClient(app) as alice_second:
                    administrator.post('/api/v1/bootstrap', json={'token': 'bootstrap-secret-long',
                        'username': 'admin', 'password': 'strong-admin-password'}).raise_for_status()
                    administrator.post('/api/v1/login', json={'username': 'admin',
                        'password': 'strong-admin-password'}).raise_for_status()
                    admin_csrf = administrator.cookies.get('aether_csrf')
                    identity = IdentityService(Path(temp) / 'identity.sqlite3', 'bootstrap-secret-long')
                    admin = identity.actor(administrator.cookies.get('aether_session'))
                    runtime = DockerEnvironmentBroker('aetherdesk-files:w003')
                    terminals = TerminalService(Path(temp) / 'terminals.sqlite3', identity, runtime)
                    composition = AppComposition(identity, runtime, terminals)
                    admin_env = identity.account(admin, admin.account_id)['environment_id']
                    resources.append(runtime._names(admin_env))
                    accounts = {}
                    for name, client in (('alice', alice_client), ('bobby', bob_client)):
                        response = administrator.post('/api/v1/admin/accounts',
                            json={'username': name, 'password': 'strong-member-password', 'role': 'member'},
                            headers={'X-CSRF-Token': admin_csrf})
                        self.assertEqual(response.status_code, 200, response.text)
                        account_id = response.json()['data']['id']
                        env_id = identity.account(admin, account_id)['environment_id']
                        resources.append(runtime._names(env_id))
                        accounts[name] = (account_id, env_id)
                        client.post('/api/v1/login', json={'username': name,
                            'password': 'strong-member-password'}).raise_for_status()
                    alice_id, alice_env = accounts['alice']
                    bob_id, bob_env = accounts['bobby']
                    alice = identity.actor(alice_client.cookies.get('aether_session'))
                    bob = identity.actor(bob_client.cookies.get('aether_session'))
                    # S01: conta nova provisionada pelo evento após a mutação HTTP.
                    self.assertEqual(runtime.state(alice_id, alice_env).state, 'running')
                    # S02/S03: mesma URL, raízes e conteúdo independentes.
                    for client, content in ((alice_client, b'alice'), (bob_client, b'bobby')):
                        response = client.put('/api/v1/files/upload?path=%2Fpersist%2Fsame.txt',
                            content=content, headers={'X-CSRF-Token': client.cookies.get('aether_csrf')})
                        self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(alice_client.get('/api/v1/files/download?path=%2Fpersist%2Fsame.txt').content, b'alice')
                    self.assertEqual(bob_client.get('/api/v1/files/download?path=%2Fpersist%2Fsame.txt').content, b'bobby')
                    # S04/S06: Bash e programas veem a raiz própria.
                    self.assertEqual(runtime.exec(alice_id, alice_env, ['bash', '-lc', 'cd /; pwd; cat /persist/same.txt']), '/\nalice')
                    self.assertEqual(runtime.exec(bob_id, bob_env, ['bash', '-lc', 'cd /; pwd; cat /persist/same.txt']), '/\nbobby')
                    # S05: alteração externa do Bash aparece no Explorer/editor.
                    runtime.exec(alice_id, alice_env, ['bash', '-lc', 'printf "print(7)\n" >/persist/from-bash.py'])
                    names = [entry['name'] for entry in alice_client.get('/api/v1/files/list?path=%2Fpersist').json()['data']]
                    self.assertIn('from-bash.py', names)
                    self.assertIn('print(7)', alice_client.get('/api/v1/files/content?path=%2Fpersist%2Ffrom-bash.py').json()['data']['content'])
                    # S07: dois PTYs, cwd independente e arquivos comuns.
                    first_id, second_id = terminals.create(alice), terminals.create(alice)
                    first, second = terminals.attach(alice, first_id), terminals.attach(alice, second_id)
                    try:
                        first.socket.settimeout(5)
                        second.socket.settimeout(5)
                        first.write(b'cd /; pwd\r')
                        second.write(b'cd /persist; pwd\r')
                        self.assertTrue(first.read())
                        self.assertTrue(second.read())
                        first_screen = runtime.exec(alice_id, alice_env, ['tmux', '-L', 'aether', 'capture-pane', '-p', '-t', first_id])
                        second_screen = runtime.exec(alice_id, alice_env, ['tmux', '-L', 'aether', 'capture-pane', '-p', '-t', second_id])
                        self.assertIn('pwd\n/', first_screen)
                        self.assertIn('pwd\n/persist', second_screen)
                    finally:
                        first.close(); second.close()
                    self.assertEqual(runtime.exec(alice_id, alice_env, ['cat', '/persist/same.txt']), 'alice')
                    # S08: segundo acesso à mesma conta conserva ambiente e arquivos.
                    alice_second.post('/api/v1/login', json={'username': 'alice',
                        'password': 'strong-member-password'}).raise_for_status()
                    self.assertEqual(identity.actor(alice_second.cookies.get('aether_session')).account_id, alice_id)
                    self.assertEqual(runtime.ensure(alice_id, alice_env).container_name, runtime.state(alice_id, alice_env).container_name)
                    # S09: parada do contêiner mantém volume, fecha registros PTY.
                    composition.stop_account_session(admin, alice_id)
                    self.assertEqual(runtime.state(alice_id, alice_env).state, 'exited')
                    self.assertEqual([row['state'] for row in terminals.list(identity.login('alice', 'strong-member-password')[1])], ['closed', 'closed'])
                    runtime.ensure(alice_id, alice_env)
                    self.assertEqual(runtime.exec(alice_id, alice_env, ['cat', '/persist/same.txt']), 'alice')
                    alice_client.post('/api/v1/login', json={'username': 'alice',
                        'password': 'strong-member-password'}).raise_for_status()
                    alice = identity.actor(alice_client.cookies.get('aether_session'))
                    # S10: alteração de ID não concede conta ou PTY alheio.
                    self.assertEqual(alice_client.get('/api/v1/admin/accounts/' + bob_id).status_code, 403)
                    bob_terminal = terminals.create(bob)
                    with self.assertRaises(TerminalError):
                        terminals.attach(alice, bob_terminal)
                    # S11/S12: referência própria e visão global negada a membro.
                    metrics = alice_client.get('/api/v1/metrics/self')
                    self.assertEqual(metrics.status_code, 200)
                    self.assertEqual(metrics.json()['data']['current']['reference'], alice_id)
                    self.assertEqual(alice_client.get('/api/v1/metrics/accounts').status_code, 403)
                    self.assertEqual(alice_client.get('/api/v1/metrics/server').status_code, 403)
                    # S13: revogar capacidade fecha WS aberto.
                    active_terminal = terminals.create(alice)
                    with alice_client.websocket_connect('/api/v1/ws/terminals/' + active_terminal) as ws:
                        self.assertTrue(ws.receive_bytes())
                        identity.set_permission(admin, alice_id, 'terminal.control', False)
                        message = ws.receive()
                        while message['type'] == 'websocket.send':
                            message = ws.receive()
                        self.assertEqual(message['type'], 'websocket.close')
                    # S14: via Bash, Bob não encontra o volume de Alice no host.
                    alice_volume = runtime._names(alice_env)[1]
                    result = subprocess.run(['docker', 'exec', runtime.state(bob_id, bob_env).container_name,
                        'bash', '-lc', f'cat /var/lib/docker/volumes/{alice_volume}/_data/same.txt'],
                        capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(runtime.exec(bob_id, bob_env, ['cat', '/persist/same.txt']), 'bobby')
            finally:
                for container, volume in resources:
                    subprocess.run(['docker', 'container', 'rm', '--force', container], capture_output=True)
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == '__main__':
    unittest.main()

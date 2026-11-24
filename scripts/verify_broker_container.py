"""Ensaio integrado W002 executado somente no contêiner web descartável."""

from __future__ import annotations

import json
import os
import grp
import sqlite3
import statistics
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path

from apps.AetherDesk.files.broker_gateway import BrokerFileGateway
from apps.AetherDesk.identity import IdentityError, IdentityService
from apps.AetherDesk.monitor.broker_source import BrokerMetricsSource
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerEnvironmentAdapter, BrokerError
from apps.AetherDesk.terminal.service import TerminalError, TerminalService


def main() -> None:
    data_dir = Path(os.environ['AETHERDESK_DATA_DIR'])
    if '--broker-down' in sys.argv or '--broker-up' in sys.argv:
        import httpx
        expected = 503 if '--broker-down' in sys.argv else 200
        with httpx.Client(base_url='http://127.0.0.1:8174', timeout=8) as http:
            login = http.post('/api/v1/login', json={
                'username': 'w002fixture', 'password': 'w002-fixture-password'})
            assert login.status_code == 200, ('login', login.status_code, login.text)
            for path in ('/api/v1/me', '/api/v1/desktop/state'):
                response = http.get(path)
                assert response.status_code == 200, (path, response.status_code, response.text)
            files = http.get('/api/v1/files/list', params={'path': '/persist'})
            assert files.status_code == expected, ('files', files.status_code, files.text)
        print('AETHERDESK_BROKER_' + ('DOWN' if expected == 503 else 'RESTORED') + '=ok', flush=True)
        return
    if '--lookup-env' in sys.argv:
        database = data_dir / 'identity.sqlite3'
        if not database.exists():
            print('')
            return
        try:
            with closing(sqlite3.connect(database)) as db:
                rows = db.execute("""SELECT environment_id FROM accounts
                    WHERE username IN ('w002fixture','w002other')
                       OR username LIKE 'w002load%'""").fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            print(row[0])
        return
    if '--reconcile' in sys.argv:
        with closing(sqlite3.connect(data_dir / 'identity.sqlite3')) as db:
            row = db.execute("SELECT id,environment_id FROM accounts WHERE username='w002fixture'").fetchone()
        assert row is not None
        client = BrokerClient(os.environ['AETHERDESK_BROKER_SOCKET'],
                              __import__('base64').b64decode(os.environ['AETHERDESK_BROKER_SECRET_B64']))
        state = BrokerEnvironmentAdapter(client).ensure(row[0], row[1])
        assert state.state == 'running'
        print(json.dumps({'reconciled_after_restart': True, 'environment_id': row[1]}))
        return
    assert not Path('/var/run/docker.sock').exists(), 'web recebeu socket Docker'
    with open('/proc/1/status', encoding='utf-8') as status:
        group_line = next(line for line in status if line.startswith('Groups:'))
    web_groups = {int(value) for value in group_line.split(':', 1)[1].split()}
    assert 0 not in web_groups, 'web recebeu grupo root'
    try:
        docker_gid = grp.getgrnam('docker').gr_gid
    except KeyError:
        docker_gid = None
    assert docker_gid not in web_groups, 'web recebeu grupo docker'
    assert '/var/run/docker.sock' not in Path('/proc/1/mountinfo').read_text(), 'web montou socket Docker'
    assert not Path('/audit').exists(), 'web recebeu volume de auditoria'
    fd_targets = []
    for fd in Path('/proc/1/fd').iterdir():
        try:
            fd_targets.append(os.readlink(fd))
        except OSError:
            pass
    assert not any('docker.sock' in target for target in fd_targets), 'web abriu FD Docker'
    assert urllib.request.urlopen('http://127.0.0.1:8174/healthz', timeout=5).status == 200
    identity = IdentityService(data_dir / 'identity.sqlite3', os.environ['AETHERDESK_BOOTSTRAP_TOKEN'])
    identity.bootstrap(os.environ['AETHERDESK_BOOTSTRAP_TOKEN'], 'w002fixture',
                       'w002-fixture-password')
    token, actor = identity.login('w002fixture', 'w002-fixture-password')
    account = identity.account(actor, actor.account_id)
    environment_id = account['environment_id']
    print('AETHERDESK_FIXTURE_ENV=' + environment_id, flush=True)
    client = BrokerClient(os.environ['AETHERDESK_BROKER_SOCKET'],
                          __import__('base64').b64decode(os.environ['AETHERDESK_BROKER_SECRET_B64']))
    runtime = BrokerEnvironmentAdapter(client)
    first = runtime.ensure(actor.account_id, environment_id)
    second = runtime.ensure(actor.account_id, environment_id)
    assert first.container_name == second.container_name and second.state == 'running'
    try:
        client.call('delete_account', actor.account_id, environment_id)
    except BrokerError as exc:
        assert str(exc) == 'OPERATION_DENIED'
    else:
        raise AssertionError('broker aceitou exclusão de conta ativa')

    files = BrokerFileGateway(identity, client)
    revision = files.write(actor, '/persist/w002-fixture.txt', b'broker fixture', replace=True)
    content, read_revision = files.read(actor, '/persist/w002-fixture.txt')
    assert content == b'broker fixture' and read_revision == revision
    other_id = identity.create_account(actor, 'w002other', 'w002-other-password', 'member')
    _other_token, other = identity.login('w002other', 'w002-other-password')
    other_account = identity.account(other, other_id)
    other_environment = other_account['environment_id']
    print('AETHERDESK_FIXTURE_ENV=' + other_environment, flush=True)
    other_state = runtime.ensure(other_id, other_environment)
    assert other_state.container_name != first.container_name
    files.write(other, '/persist/w002-fixture.txt', b'other account', replace=True)
    assert files.read(other, '/persist/w002-fixture.txt')[0] == b'other account'
    assert files.read(actor, '/persist/w002-fixture.txt')[0] == b'broker fixture'

    metrics = BrokerMetricsSource(client).environment_for(actor.account_id, environment_id)
    assert metrics['state'] == 'running'

    def latency(call):
        samples = []
        for _ in range(5):
            call()
        for _ in range(30):
            started = time.perf_counter()
            call()
            samples.append((time.perf_counter() - started) * 1000)
        ordered = sorted(samples)
        return {'count': len(ordered), 'p50_ms': round(statistics.median(ordered), 1),
                'p95_ms': round(ordered[28], 1), 'p99_ms': round(ordered[29], 1)}

    benchmark = {
        'state': latency(lambda: runtime.state(actor.account_id, environment_id)),
        'files_list': latency(lambda: files.call(actor, 'list', '/persist')),
        'metrics': latency(lambda: BrokerMetricsSource(client).environment_for(
            actor.account_id, environment_id)),
    }
    print('AETHERDESK_BENCHMARK=' + json.dumps(benchmark), flush=True)

    terminals = TerminalService(data_dir / 'terminals.sqlite3', identity, runtime, broker=client,
                                max_sessions_per_account=2)
    terminal_id = terminals.create(actor)
    second_terminal_id = terminals.create(actor)
    try:
        terminals.create(actor)
    except TerminalError as exc:
        assert exc.code == 'TERMINAL_QUOTA'
    else:
        raise AssertionError('quota de sessões tmux persistentes não aplicada')
    terminals.close(actor, second_terminal_id)

    child = os.fork()
    if child == 0:
        class ExitAfterCreate:
            def call(self, operation, account_id, environment_id, payload):
                result = client.call(operation, account_id, environment_id, payload)
                if operation == 'terminal_create':
                    os._exit(47)
                return result

        TerminalService(data_dir / 'terminals.sqlite3', identity, runtime,
                        broker=ExitAfterCreate(), max_sessions_per_account=2).create(actor)
        os._exit(48)
    _, child_status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(child_status) == 47, 'filho não caiu após criar tmux'
    with closing(sqlite3.connect(data_dir / 'terminals.sqlite3')) as db:
        with db:
            interrupted_id = db.execute("SELECT id FROM terminals WHERE state='pending'").fetchone()[0]
            db.execute("UPDATE terminals SET retry_at=? WHERE id=?",
                       ('2000-01-01T00:00:00+00:00', interrupted_id))
    assert terminals.create(actor) == interrupted_id, 'reconciliação da reserva não reutilizou ID'
    connection = terminals.attach(actor, terminal_id)
    try:
        connection.socket.settimeout(8)
        connection.write(b"printf 'W002_PTY_OK\\n'\n")
        output = bytearray()
        deadline = time.monotonic() + 8
        while b'W002_PTY_OK' not in output and time.monotonic() < deadline:
            output.extend(connection.read())
        assert b'W002_PTY_OK' in output
        identity.logout(token)
        try:
            connection.write(b'echo should-not-run\n')
        except IdentityError as exc:
            assert exc.code == 'UNAUTHENTICATED'
        else:
            raise AssertionError('PTY não respeitou revogação')
    finally:
        connection.close()
    print(json.dumps({'web_docker_socket': False, 'web_docker_group': False,
                      'web_docker_fd': False, 'environment': 'running',
                      'files': 'ok', 'metrics': 'ok', 'terminal': 'ok',
                      'terminal_quota': 'ok', 'terminal_crash_recovery': 'ok',
                      'revocation': 'ok', 'account_isolation': 'ok',
                      'account_id': actor.account_id}), flush=True)


if __name__ == '__main__':
    main()

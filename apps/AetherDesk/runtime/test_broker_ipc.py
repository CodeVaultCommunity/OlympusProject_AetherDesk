import tempfile
import base64
import threading
import unittest
import uuid
import socketserver
import socket
import hashlib
import hmac
import json
import sqlite3
import time
import multiprocessing
import subprocess
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from pathlib import Path

from apps.AetherDesk.support.correlation import request_id_context
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerDispatch, BrokerEnvironmentAdapter, BrokerError, BrokerServer, _FileAgentPool, _file_result, _canonical, _MAX_CONNECTIONS, _MAX_FILE_OPERATIONS


@dataclass
class EnvironmentStub:
    account_id: str
    environment_id: str
    container_name: str = 'fixture'
    volume_name: str = 'fixture-volume'
    state: str = 'running'


class RuntimeStub:
    def __init__(self):
        self.calls = []
        self.sessions = set()

    def ensure(self, account, environment):
        self.calls.append(('ensure', account, environment))
        return EnvironmentStub(account, environment)

    def state(self, account, environment):
        return EnvironmentStub(account, environment)

    def stop_session(self, account, environment):
        self.calls.append(('stop', account, environment))

    def delete_account(self, account, environment):
        self.calls.append(('delete', account, environment))

    def exec(self, account, environment, command):
        self.calls.append(('exec', account, environment, command))
        if 'new-session' in command:
            self.sessions.add(command[command.index('-s') + 1])

    def exec_status(self, account, environment, command):
        self.calls.append(('exec_status', account, environment, command))
        return subprocess.CompletedProcess(command, 0 if command[-1] in self.sessions else 1, '', '')


class TerminalApiStub:
    def __init__(self):
        self.peer = None
        self.resizes = []

    def exec_create(self, *_args, **_kwargs):
        return {'Id': 'fixture-exec'}

    def exec_start(self, *_args, **_kwargs):
        upstream, self.peer = socket.socketpair()
        return upstream

    def exec_resize(self, exec_id, *, height, width):
        self.resizes.append((exec_id, height, width))


class MetricsStub:
    def __init__(self):
        self.calls = 0

    def environment(self, container):
        self.calls += 1
        return {'state': 'running', 'cpu_percent': 1.5, 'container': container}


def _serve_one_process(socket_path, secret, ready):
    with BrokerServer(socket_path, secret, RuntimeStub()) as server:
        server.daemon_threads = False
        ready.set()
        server.handle_request()


class BrokerTests(unittest.TestCase):
    def test_authenticated_ping_reports_protocol_without_account_or_docker(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        runtime = MagicMock()
        dispatch = BrokerDispatch(secret, runtime,
            account_resolver=lambda _account: self.fail('Account lookup during ping'))
        zero = str(uuid.UUID(int=0))
        result = dispatch.dispatch(BrokerClient('/unused', secret)._message('ping', zero, zero, None))
        self.assertEqual(result, {'protocol': 1, 'ready': True})
        runtime.ensure.assert_not_called()

    def test_workspace_commit_is_idempotent_and_checks_capability(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment, session = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeStub()
            runtime.exec_status = MagicMock(return_value=subprocess.CompletedProcess([], 0, '', ''))
            identity = MagicMock()
            identity.require = MagicMock()
            identity.account.return_value = {'username': 'owner'}
            runner = MagicMock(return_value={'hash': 'a' * 40})
            dispatch = BrokerDispatch(secret, runtime, file_runner=runner,
                account_resolver=lambda _account: {'environment_id': environment, 'state': 'active'},
                nonce_db_path=Path(directory) / 'nonce.sqlite3', identity=identity)
            client = BrokerClient('/unused', secret)
            operation_id = str(uuid.uuid4())
            payload = {'operation': 'git_commit', 'session_id': session,
                       'message': 'fixture', 'operation_id': operation_id}
            self.assertEqual(dispatch.dispatch(client._message('workspace', account, environment, payload)),
                             {'hash': 'a' * 40})
            self.assertEqual(dispatch.dispatch(client._message('workspace', account, environment, payload)),
                             {'hash': 'a' * 40})
            runner.assert_called_once()
            identity.require.assert_called()
            self.assertEqual(identity.require.call_args.args[1], 'git.write')
            changed = {**payload, 'message': 'outro commit'}
            with self.assertRaisesRegex(BrokerError, 'OPERATION_CONFLICT'):
                dispatch.dispatch(client._message('workspace', account, environment, changed))
            invalid = {**payload, 'docker_flags': ['--privileged']}
            with self.assertRaisesRegex(BrokerError, 'INVALID_WORKSPACE_REQUEST'):
                dispatch.dispatch(client._message('workspace', account, environment, invalid))

    def test_workload_rpc_revalidates_session_and_schema(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment, session = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        identity = MagicMock()
        identity.assert_active = MagicMock()
        service = MagicMock()
        service.list_mine.return_value = [{'id': 'owned'}]
        dispatch = BrokerDispatch(secret, RuntimeStub(),
            account_resolver=lambda _account: {'environment_id': environment, 'state': 'active'},
            workload_service=service, identity=identity)
        client = BrokerClient('/unused', secret)
        payload = {'operation': 'list_mine', 'session_id': session}
        request = client._message('workload', account, environment, payload)
        self.assertEqual(dispatch.dispatch(request), {'items': [{'id': 'owned'}]})
        identity.assert_active.assert_called_once()
        self.assertEqual(identity.assert_active.call_args.args[0].account_id, account)
        with self.assertRaisesRegex(BrokerError, 'REPLAY_DENIED'):
            dispatch.dispatch(request)
        invalid = client._message('workload', account, environment,
                                  {**payload, 'docker_flags': ['--privileged']})
        with self.assertRaisesRegex(BrokerError, 'INVALID_WORKLOAD_REQUEST'):
            dispatch.dispatch(invalid)
        service.list_mine.assert_called_once()

    def test_workload_proxy_rpc_is_typed_and_binds_actor(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment, session = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        proxy = MagicMock()
        proxy.request.return_value = (200, {'content-type': 'text/plain'}, b'hello')
        identity = MagicMock()
        identity.assert_active = MagicMock()
        dispatch = BrokerDispatch(secret, RuntimeStub(),
            account_resolver=lambda _account: {'environment_id': environment, 'state': 'active'},
            workload_service=MagicMock(), identity=identity, proxy_service=proxy)
        client = BrokerClient('/unused', secret)
        payload = {'operation': 'proxy', 'session_id': session,
                   'host': '0123456789ab.apps.local', 'method': 'GET', 'path': '/',
                   'headers': {'X-Test': 'safe'}, 'body': base64.b64encode(b'x').decode()}
        result = dispatch.dispatch(client._message('workload', account, environment, payload))
        self.assertEqual(base64.b64decode(result['body']), b'hello')
        self.assertEqual(proxy.request.call_args.args[0].account_id, account)
        self.assertEqual(proxy.request.call_args.args[0].session_id, session)
        self.assertEqual(proxy.request.call_args.args[1:],
                         (payload['host'], 'GET', '/', payload['headers'], b'x'))
        with self.assertRaisesRegex(BrokerError, 'PROXY_INVALID_REQUEST'):
            dispatch.dispatch(client._message('workload', account, environment,
                {**payload, 'body': '%%%'}))
        self.assertEqual(proxy.request.call_count, 1)

    def test_file_write_disconnect_has_unknown_outcome_only_after_send(self):
        client = BrokerClient('/unused', b'test-secret-with-at-least-32-bytes!!')
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value.__enter__.return_value.readline.return_value = b''
        with patch('apps.AetherDesk.runtime.broker_ipc.socket.AF_UNIX', 1, create=True), \
             patch('apps.AetherDesk.runtime.broker_ipc.socket.socket', return_value=connection):
            with self.assertRaisesRegex(BrokerError, '^UNKNOWN_WRITE_OUTCOME$'):
                client.call('file_agent', account, environment,
                            {'operation': 'write', 'path': '/persist/note', 'content': 'eA=='})
            with self.assertRaisesRegex(BrokerError, '^BROKER_UNAVAILABLE$'):
                client.call('file_agent', account, environment,
                            {'operation': 'read', 'path': '/persist/note'})
            connection.connect.side_effect = OSError('socket unavailable')
            with self.assertRaisesRegex(BrokerError, '^BROKER_UNAVAILABLE$'):
                client.call('file_agent', account, environment,
                            {'operation': 'write', 'path': '/persist/note', 'content': 'eA=='})

    def test_client_rejects_untyped_broker_responses(self):
        for response in (
            {'version': 1, 'error': 'private path /tmp/key'},
            {'version': 1, 'error': 503},
            {'version': 1, 'error': ''},
            {'version': 1},
            {'version': 1, 'data': {}, 'error': 'BROKER_BUSY'},
            {'version': True, 'data': {}},
        ):
            with self.subTest(response=response), self.assertRaisesRegex(BrokerError, '^BROKER_PROTOCOL$'):
                BrokerClient._result(_canonical(response))
        with self.assertRaisesRegex(BrokerError, '^BROKER_BUSY$'):
            BrokerClient._result(_canonical({'version': 1, 'error': 'BROKER_BUSY'}))

    def test_file_limit_rejects_before_stalled_runtime_call(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        release = threading.Event()
        lock = threading.Lock()

        class StalledRuntime(RuntimeStub):
            def __init__(self):
                super().__init__()
                self.started = 0

            def ensure(self, account_id, environment_id):
                with lock:
                    self.started += 1
                if not release.wait(5):
                    raise TimeoutError('runtime fixture stalled')
                return EnvironmentStub(account_id, environment_id)

        runtime = StalledRuntime()
        broker = BrokerDispatch(secret, runtime, file_runner=lambda *_: {'data': []})
        client = BrokerClient('/unused', secret)
        request = lambda: client._message('file_agent', account, environment,
                                          {'operation': 'list', 'path': '/'})
        with ThreadPoolExecutor(max_workers=_MAX_FILE_OPERATIONS) as pool:
            futures = [pool.submit(broker.dispatch, request())
                       for _ in range(_MAX_FILE_OPERATIONS)]
            try:
                deadline = time.monotonic() + 3
                while runtime.started < _MAX_FILE_OPERATIONS and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(runtime.started, _MAX_FILE_OPERATIONS)
                with self.assertRaisesRegex(BrokerError, 'BROKER_BUSY'):
                    broker.dispatch(request())
                self.assertEqual(runtime.started, _MAX_FILE_OPERATIONS)
            finally:
                release.set()
            for future in futures:
                self.assertEqual(future.result(timeout=3), {'data': []})
        self.assertEqual(broker.dispatch(request()), {'data': []})

    def test_mutation_nonce_survives_broker_restart(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        request = BrokerClient('/unused', secret)._message('ensure', account, environment, None)
        with tempfile.TemporaryDirectory() as temp:
            journal = Path(temp) / 'nonces.sqlite3'
            first = BrokerDispatch(secret, RuntimeStub(), nonce_db_path=journal)
            self.assertEqual(first.dispatch(request)['state'], 'running')
            restarted = BrokerDispatch(secret, RuntimeStub(), nonce_db_path=journal)
            with self.assertRaisesRegex(BrokerError, 'REPLAY_DENIED'):
                restarted.dispatch(request)
            self.assertEqual(restarted.dispatch(BrokerClient('/unused', secret)._message(
                'state', account, environment, None))['state'], 'running')

    def test_signed_malformed_types_are_rejected_without_runtime_effect(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        runtime = RuntimeStub()
        broker = BrokerDispatch(secret, runtime, file_runner=lambda *_: [])
        client = BrokerClient('/unused', secret)

        def signed(changes):
            message = client._message('file_agent', account, environment,
                                      {'operation': 'list', 'path': '/persist'})
            message.update(changes)
            message.pop('signature')
            message['signature'] = hmac.new(secret, _canonical(message), hashlib.sha256).hexdigest()
            return message

        malformed = (
            ({'operation': []}, 'INVALID_REQUEST'),
            ({'version': True}, 'BROKER_PROTOCOL'),
            ({'payload': {'operation': [], 'path': '/persist'}}, 'INVALID_FILE_REQUEST'),
        )
        for changes, code in malformed:
            with self.subTest(changes=changes), self.assertRaisesRegex(BrokerError, f'^{code}$'):
                broker.dispatch(signed(changes))
        self.assertEqual(runtime.calls, [])
        self.assertEqual(broker.dispatch(client._message('state', account, environment, None))['state'],
                         'running')

    def test_nonce_journal_failure_rejects_mutation_before_docker(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp:
            runtime = RuntimeStub()
            broker = BrokerDispatch(secret, runtime, nonce_db_path=Path(temp) / 'nonces.sqlite3')
            request = BrokerClient('/unused', secret)._message('ensure', account, environment, None)
            with patch('apps.AetherDesk.runtime.broker_ipc.sqlite3.connect',
                       side_effect=sqlite3.OperationalError('disk full')):
                with self.assertRaisesRegex(BrokerError, 'BROKER_UNAVAILABLE'):
                    broker.dispatch(request)
            self.assertEqual(runtime.calls, [])

    def test_file_agent_preserves_typed_errors_without_trusting_arbitrary_output(self):
        payload = {'operation': 'read', 'path': '/persist/../etc/passwd'}
        with patch('apps.AetherDesk.runtime.broker_ipc.subprocess.run') as runner:
            runner.return_value = subprocess.CompletedProcess([], 2, b'{"error":"INVALID_PATH"}', b'')
            with self.assertRaisesRegex(BrokerError, 'INVALID_PATH'):
                BrokerDispatch._run_file_agent('fixture', payload)
            runner.return_value = subprocess.CompletedProcess([], 2, b'{"error":"secret\\ncontent"}', b'')
            with self.assertRaisesRegex(BrokerError, 'FILE_UNAVAILABLE'):
                BrokerDispatch._run_file_agent('fixture', payload)
            for response, code in ((b'{"error":[]}', 2),
                                   (b'{"data":[],"error":"NOT_FOUND"}', 0),
                                   (b'{"data":[]}', 2)):
                runner.return_value = subprocess.CompletedProcess([], code, response, b'')
                with self.assertRaisesRegex(BrokerError, '^FILE_UNAVAILABLE$'):
                    BrokerDispatch._run_file_agent('fixture', payload)
        for response in ({'error': []}, {'data': [], 'error': 'NOT_FOUND'}):
            with self.assertRaisesRegex(BrokerError, '^FILE_UNAVAILABLE$'):
                _file_result(response)

    def test_persistent_file_agent_reuses_process_and_restarts_after_failure(self):
        created = []

        class AgentStub:
            def __init__(self, container):
                self.container = container
                self.lock = threading.Lock()
                self.last_used = time.monotonic()
                self.closed = False
                self.error = None
                created.append(self)

            def exchange(self, request):
                if self.error:
                    raise BrokerError(self.error)
                return json.loads(request)['path']

            def close(self):
                self.closed = True

        with patch('apps.AetherDesk.runtime.broker_ipc._FileAgentProcess', AgentStub), \
             patch('apps.AetherDesk.runtime.broker_ipc.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, b'', b'')):
            pool = _FileAgentPool()
            payload = {'operation': 'list', 'path': '/persist'}
            self.assertEqual(pool.call('container-a', payload), '/persist')
            self.assertEqual(pool.call('container-a', payload), '/persist')
            self.assertEqual(len(created), 1)
            created[0].error = 'NOT_FOUND'
            with self.assertRaisesRegex(BrokerError, '^NOT_FOUND$'):
                pool.call('container-a', payload)
            self.assertFalse(created[0].closed)
            created[0].error = 'FILE_UNAVAILABLE'
            with self.assertRaisesRegex(BrokerError, '^FILE_UNAVAILABLE$'):
                pool.call('container-a', payload)
            self.assertTrue(created[0].closed)
            self.assertEqual(pool.call('container-a', payload), '/persist')
            self.assertEqual(len(created), 2)
            created[1].error = 'FILE_UNAVAILABLE'
            with self.assertRaisesRegex(BrokerError, '^UNKNOWN_WRITE_OUTCOME$'):
                pool.call('container-a', {'operation': 'write', 'path': '/persist',
                                          'content': 'eA=='})
            pool.close()
            self.assertTrue(created[1].closed)

    def test_legacy_file_agent_uses_one_shot_protocol(self):
        payload = {'operation': 'list', 'path': '/persist'}
        with patch('apps.AetherDesk.runtime.broker_ipc.subprocess.run') as runner:
            runner.side_effect = [
                subprocess.CompletedProcess([], 1, b'', b''),
                subprocess.CompletedProcess([], 0, b'{"data":[]}', b''),
                subprocess.CompletedProcess([], 0, b'{"data":[]}', b''),
            ]
            pool = _FileAgentPool()
            self.assertEqual(pool.call('legacy-container', payload), [])
            self.assertEqual(pool.call('legacy-container', payload), [])
            self.assertEqual(runner.call_count, 3)
            self.assertEqual(runner.call_args_list[0].args[0][-3:],
                             ['test', '-f', '/opt/aetherdesk/.aetherdesk-file-stream-v1'])
            self.assertNotIn('--serve', runner.call_args_list[1].args[0])

    def test_legacy_file_write_timeout_has_unknown_outcome_after_probe(self):
        with patch('apps.AetherDesk.runtime.broker_ipc.subprocess.run') as runner:
            runner.side_effect = subprocess.TimeoutExpired(['docker', 'exec'], 5)
            pool = _FileAgentPool()
            write = {'operation': 'write', 'path': '/persist/note', 'content': 'eA=='}
            with self.assertRaisesRegex(BrokerError, '^FILE_UNAVAILABLE$'):
                pool.call('legacy-container', write)
            runner.side_effect = [
                subprocess.CompletedProcess([], 1, b'', b''),
                subprocess.TimeoutExpired(['docker', 'exec'], 30),
            ]
            with self.assertRaisesRegex(BrokerError, '^UNKNOWN_WRITE_OUTCOME$'):
                pool.call('legacy-container', write)

    def test_signed_http_correlation_is_validated_and_not_leaked(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        broker = BrokerDispatch(secret, RuntimeStub())
        client = BrokerClient('/unused', secret)
        request_id = 'a' * 24
        token = request_id_context.set(request_id)
        try:
            message = client._message('state', account, environment, None)
        finally:
            request_id_context.reset(token)
        self.assertEqual(message['request_id'], request_id)
        self.assertEqual(broker.dispatch(message)['state'], 'running')
        self.assertNotIn('request_id', client._message('state', account, environment, None))
        hostile = {**message, 'nonce': str(uuid.uuid4()), 'request_id': 'secret\ncontent'}
        hostile.pop('signature')
        hostile['signature'] = hmac.new(secret, _canonical(hostile), hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(BrokerError, 'INVALID_REQUEST'):
            broker.dispatch(hostile)

    def test_metrics_cache_is_scoped_and_invalidated_on_stop(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        metrics = MetricsStub()
        broker = BrokerDispatch(secret, RuntimeStub(), metrics_source=metrics)
        client = BrokerClient('/unused', secret)
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        other_account = str(uuid.uuid4())
        for _ in range(2):
            self.assertEqual(broker.dispatch(client._message('environment_metrics',
                account, environment, None))['cpu_percent'], 1.5)
        self.assertEqual(metrics.calls, 1)
        broker.dispatch(client._message('environment_metrics', other_account, environment, None))
        self.assertEqual(metrics.calls, 2)
        broker.dispatch(client._message('stop_session', account, environment, None))
        broker.dispatch(client._message('environment_metrics', account, environment, None))
        self.assertEqual(metrics.calls, 3)

    @unittest.skipUnless(hasattr(socketserver, 'ThreadingUnixStreamServer'), 'requer Unix socket')
    def test_slow_terminal_reader_exerts_backpressure_and_releases_slot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'broker.sock'
            secret = b'test-secret-with-at-least-32-bytes!!'
            terminal_api = TerminalApiStub()
            server = BrokerServer(path, secret, RuntimeStub(), terminal_api=terminal_api,
                                  relay_timeout=0.2)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            channel = None
            try:
                account, environment = str(uuid.uuid4()), str(uuid.uuid4())
                client = BrokerClient(path, secret)
                terminal_id = str(uuid.uuid4())
                client.call('terminal_create', account, environment,
                            {'terminal_id': terminal_id, 'columns': 80, 'rows': 24})
                _, channel = client.open_terminal(account, environment, terminal_id)
                channel.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                terminal_api.peer.settimeout(2)
                sent = 0
                try:
                    while sent < 8 * 1024 * 1024:
                        sent += terminal_api.peer.send(b'x' * 65536)
                except OSError:
                    pass
                deadline = time.monotonic() + 3
                while server.dispatcher._terminal_execs and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertLess(sent, 8 * 1024 * 1024)
                self.assertFalse(server.dispatcher._terminal_execs)
                release_deadline = time.monotonic() + 3
                while server.connection_slots._value != _MAX_CONNECTIONS and time.monotonic() < release_deadline:
                    time.sleep(0.01)
                self.assertEqual(server.connection_slots._value, _MAX_CONNECTIONS)
            finally:
                if channel is not None:
                    channel.close()
                if terminal_api.peer is not None:
                    terminal_api.peer.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    @unittest.skipUnless(hasattr(socketserver, 'ThreadingUnixStreamServer'), 'requer Unix socket')
    def test_idle_client_times_out_and_saturated_server_rejects_fast(self):
        with tempfile.TemporaryDirectory() as temp:
            secret = b'test-secret-with-at-least-32-bytes!!'
            path = Path(temp) / 'broker.sock'
            server = BrokerServer(path, secret, RuntimeStub(), request_timeout=0.2)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as idle:
                    idle.settimeout(2)
                    idle.connect(str(path))
                    self.assertEqual(idle.recv(1), b'')
                account, environment = str(uuid.uuid4()), str(uuid.uuid4())
                self.assertEqual(BrokerClient(path, secret).call('state', account, environment)['state'],
                                 'running')
                reserved = 0
                deadline = time.monotonic() + 2
                while reserved < _MAX_CONNECTIONS and time.monotonic() < deadline:
                    if server.connection_slots.acquire(blocking=False):
                        reserved += 1
                    else:
                        time.sleep(0.01)
                try:
                    self.assertEqual(reserved, _MAX_CONNECTIONS)
                    with self.assertRaisesRegex(BrokerError, 'BROKER_BUSY'):
                        BrokerClient(path, secret).call('state', account, environment)
                finally:
                    for _ in range(reserved):
                        server.connection_slots.release()
                self.assertEqual(BrokerClient(path, secret).call('state', account, environment)['state'],
                                 'running')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    @unittest.skipUnless(hasattr(socketserver, 'ThreadingUnixStreamServer'), 'requer Unix socket')
    def test_client_uses_a_separate_broker_process(self):
        with tempfile.TemporaryDirectory() as temp:
            secret = b'test-secret-with-at-least-32-bytes!!'
            path = Path(temp) / 'broker.sock'
            context = multiprocessing.get_context('fork')
            ready = context.Event()
            process = context.Process(target=_serve_one_process, args=(path, secret, ready))
            process.start()
            try:
                self.assertTrue(ready.wait(5))
                result = BrokerClient(path, secret).call('state', str(uuid.uuid4()), str(uuid.uuid4()))
                self.assertEqual(result['state'], 'running')
            finally:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            self.assertEqual(process.exitcode, 0)
            self.assertFalse(path.exists())

    def test_policy_rejects_replay_and_docker_passthrough(self):
        runtime = RuntimeStub()
        secret = b'test-secret-with-at-least-32-bytes!!'
        broker = BrokerDispatch(secret, runtime)
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        message = {'version': 1, 'operation': 'ensure', 'account_id': account,
                   'environment_id': environment, 'expires_at': time.time() + 15,
                   'nonce': str(uuid.uuid4())}
        message['signature'] = hmac.new(secret, _canonical(message), hashlib.sha256).hexdigest()
        self.assertEqual(broker.dispatch(message)['account_id'], account)
        with self.assertRaisesRegex(BrokerError, 'REPLAY_DENIED'):
            broker.dispatch(message)
        unsafe = {**message, 'operation': 'docker_exec', 'nonce': str(uuid.uuid4())}
        unsafe.pop('signature')
        unsafe['signature'] = hmac.new(secret, _canonical(unsafe), hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(BrokerError, 'OPERATION_DENIED'):
            broker.dispatch(unsafe)

    def test_account_mapping_and_lifecycle_are_verified_by_broker(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        account, environment, another = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        record = {'environment_id': environment, 'state': 'active'}
        broker = BrokerDispatch(secret, RuntimeStub(), account_resolver=lambda _account: record)
        client = BrokerClient('/unused', secret)
        with self.assertRaisesRegex(BrokerError, 'ENVIRONMENT_NOT_FOUND'):
            broker.dispatch(client._message('ensure', account, another, None))
        with self.assertRaisesRegex(BrokerError, 'OPERATION_DENIED'):
            broker.dispatch(client._message('delete_account', account, environment, None))
        record['state'] = 'disabled'
        with self.assertRaisesRegex(BrokerError, 'ACCOUNT_INACTIVE'):
            broker.dispatch(client._message('ensure', account, environment, None))
        self.assertEqual(broker.dispatch(client._message('state', account, environment, None))['state'],
                         'running')

    def test_file_and_terminal_attachment_quotas(self):
        secret = b'test-secret-with-at-least-32-bytes!!'
        broker = BrokerDispatch(secret, RuntimeStub(),
                                file_runner=lambda _container, _payload: {'ok': True},
                                terminal_api=TerminalApiStub())
        account, environment = str(uuid.uuid4()), str(uuid.uuid4())
        client = BrokerClient('/unused', secret)
        for _ in range(_MAX_FILE_OPERATIONS):
            self.assertTrue(broker._file_slots.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(BrokerError, 'BROKER_BUSY'):
                broker.dispatch(client._message('file_agent', account, environment,
                    {'operation': 'list', 'path': '/persist'}))
        finally:
            for _ in range(_MAX_FILE_OPERATIONS):
                broker._file_slots.release()
        broker._terminal_execs.update({f'exec-{index}': (account, environment)
                                       for index in range(4)})
        with self.assertRaisesRegex(BrokerError, 'TERMINAL_QUOTA'):
            broker._terminal('terminal_attach', account, environment,
                             {'terminal_id': str(uuid.uuid4())})

    @unittest.skipUnless(hasattr(socketserver, 'ThreadingUnixStreamServer'), 'requer Unix socket')
    def test_typed_ipc_authentication_and_denied_operation(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = RuntimeStub()
            terminal_api = TerminalApiStub()
            socket_path = Path(temp) / 'broker.sock'
            server = BrokerServer(socket_path, b'test-secret-with-at-least-32-bytes!!', runtime,
                file_runner=lambda container, payload: {'container': container, 'path': payload['path']},
                metrics_source=MetricsStub(), terminal_api=terminal_api)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = BrokerClient(socket_path, b'test-secret-with-at-least-32-bytes!!')
                account, environment = str(uuid.uuid4()), str(uuid.uuid4())
                self.assertEqual(client.call('ensure', account, environment)['account_id'], account)
                self.assertEqual(runtime.calls, [('ensure', account, environment)])
                adapter = BrokerEnvironmentAdapter(client)
                self.assertEqual(adapter.state(account, environment).environment_id, environment)
                self.assertEqual(client.call('file_agent', account, environment,
                    {'operation': 'list', 'path': '/persist'})['path'], '/persist')
                self.assertEqual(client.call('environment_metrics', account, environment)['cpu_percent'], 1.5)
                with self.assertRaisesRegex(BrokerError, 'INVALID_FILE_REQUEST'):
                    client.call('file_agent', account, environment, {'operation': 'shell', 'path': '/'})
                terminal_id = str(uuid.uuid4())
                client.call('terminal_create', account, environment,
                    {'terminal_id': terminal_id, 'columns': 80, 'rows': 24})
                client.call('terminal_create', account, environment,
                    {'terminal_id': terminal_id, 'columns': 80, 'rows': 24})
                self.assertEqual(sum('new-session' in call[3] for call in runtime.calls
                                     if call[0] == 'exec'), 1)
                exec_id, channel = client.open_terminal(account, environment, terminal_id)
                try:
                    channel.settimeout(5)
                    terminal_api.peer.settimeout(5)
                    channel.sendall(b'hello')
                    self.assertEqual(terminal_api.peer.recv(5), b'hello')
                    terminal_api.peer.sendall(b'world')
                    self.assertEqual(channel.recv(5), b'world')
                    client.call('terminal_resize', account, environment,
                        {'exec_id': exec_id, 'columns': 100, 'rows': 30})
                    self.assertEqual(terminal_api.resizes, [('fixture-exec', 30, 100)])
                finally:
                    channel.close()
                    terminal_api.peer.close()
                with self.assertRaisesRegex(BrokerError, 'OPERATION_DENIED'):
                    client.call('docker_exec', account, environment)
                hostile = client._message('state', account, environment, None)
                hostile['operation'] = 'docker\nexec'
                hostile.pop('signature')
                hostile['signature'] = hmac.new(client.secret,
                    _canonical(hostile), hashlib.sha256).hexdigest()
                with self.assertLogs('aetherdesk.broker', level='WARNING') as audit:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                        channel.connect(str(socket_path))
                        channel.sendall(_canonical(hostile) + b'\n')
                        response = json.loads(channel.makefile('rb').readline())
                self.assertEqual(response['error'], 'OPERATION_DENIED')
                self.assertIn('operation=denied', audit.output[0])
                self.assertIn(f'account={account}', audit.output[0])
                self.assertNotIn('docker\nexec', audit.output[0])
                impostor = BrokerClient(socket_path, b'different-secret-with-at-least-32-b')
                with self.assertRaisesRegex(BrokerError, 'UNAUTHENTICATED'):
                    impostor.call('state', account, environment)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            self.assertFalse(socket_path.exists())


if __name__ == '__main__':
    unittest.main()

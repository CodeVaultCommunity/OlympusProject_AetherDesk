"""Fronteira IPC tipada para o broker Docker local.

O protocolo não aceita comandos Docker nem argumentos de shell enviados pelo cliente.
Este módulo ainda não substitui os adapters de arquivo, PTY e métricas no ASGI.
"""

from __future__ import annotations

import hashlib
import base64
import binascii
import hmac
import json
import logging
import os
import re
import select
import secrets
import socket
import socketserver
import sqlite3
import stat
import subprocess
import threading
import time
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from apps.AetherDesk.support.correlation import request_id_context
from apps.AetherDesk.support.migrations import apply_migration
from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.workloads.service import WorkloadError

from .docker import DockerEnvironmentBroker, Environment, RuntimeError as DockerRuntimeError


class BrokerError(Exception):
    pass


_OPERATIONS = frozenset({'ping', 'ensure', 'state', 'stop_session', 'delete_account',
                         'file_agent', 'environment_metrics', 'terminal_create',
                         'terminal_attach', 'terminal_resize', 'terminal_kill', 'workload', 'workspace'})
_PAYLOAD_OPERATIONS = frozenset({'file_agent', 'terminal_create', 'terminal_attach',
                                 'terminal_resize', 'terminal_kill', 'workload', 'workspace'})
_FILE_OPERATIONS = frozenset({'list', 'metadata', 'read', 'write', 'mkdir', 'move', 'copy', 'delete'})
_FILE_ERRORS = frozenset({'INVALID_PATH', 'INVALID_REQUEST', 'INVALID_OPERATION',
                          'NOT_FOUND', 'CONFLICT', 'FORBIDDEN', 'QUOTA',
                          'TOO_LARGE', 'STALE_REVISION', 'LINUX_REQUIRED',
                          'INVALID_WORKSPACE', 'SESSION_REVOKED', 'NOT_DIRECTORY',
                          'TOO_MANY_ENTRIES', 'INVALID_PAGE', 'NOT_FILE',
                          'INVALID_ENCODING', 'BINARY', 'INVALID_CONTENT',
                          'INVALID_SEARCH', 'SEARCH_CANCELLED', 'UNTRUSTED_REPOSITORY',
                          'GIT_UNAVAILABLE', 'GIT_PROTOCOL', 'GIT_FAILED',
                          'GIT_TIMEOUT', 'GIT_OUTPUT_LIMIT', 'GIT_CANCELLED',
                          'GIT_CONFLICT', 'INVALID_PATHS', 'INVALID_COMMIT'})


def _file_result(result, *, returncode: int | None = None):
    if not isinstance(result, dict) or set(result) not in ({'data'}, {'error'}):
        raise BrokerError('FILE_UNAVAILABLE')
    if 'error' in result:
        error = result['error']
        if type(error) is str and error in _FILE_ERRORS and returncode in (None, 2):
            raise BrokerError(error)
        raise BrokerError('FILE_UNAVAILABLE')
    if returncode not in (None, 0):
        raise BrokerError('FILE_UNAVAILABLE')
    return result['data']
_MAX_MESSAGE = 16 * 1024 * 1024
_MAX_FILE_OPERATIONS = 16
_MAX_TERMINAL_ATTACHMENTS = 64
_MAX_TERMINAL_ATTACHMENTS_PER_ACCOUNT = 4
_MAX_CONNECTIONS = 96


def _canonical(message: dict) -> bytes:
    return json.dumps(message, sort_keys=True, separators=(',', ':')).encode()


def _audit_fields(request: object) -> tuple[str, str, str, str]:
    if not isinstance(request, dict):
        return '-', '-', '-', '-'
    operation = request.get('operation')
    operation = operation if isinstance(operation, str) and operation in _OPERATIONS else 'denied'
    values = []
    for field in ('account_id', 'nonce'):
        try:
            values.append(str(uuid.UUID(request[field])))
        except (KeyError, TypeError, ValueError, AttributeError):
            values.append('-')
    request_id = request.get('request_id')
    correlation = request_id if isinstance(request_id, str) and re.fullmatch(r'[0-9a-f]{24}', request_id) else '-'
    return operation, *values, correlation


class BrokerClient:
    def __init__(self, socket_path: str | Path, secret: bytes):
        if len(secret) < 32:
            raise BrokerError('WEAK_BROKER_SECRET')
        self.socket_path, self.secret = str(socket_path), secret

    def call(self, operation: str, account_id: str, environment_id: str,
             payload: dict | None = None) -> dict:
        message = self._message(operation, account_id, environment_id, payload)
        file_write = (operation == 'file_agent' and isinstance(payload, dict) and
                      payload.get('operation') in {'write', 'mkdir', 'move', 'copy', 'delete'})
        file_write = file_write or (operation == 'workload' and isinstance(payload, dict) and
                      payload.get('operation') in {'project', 'create', 'request', 'admin_request',
                                                  'cancel', 'configure_secrets'})
        file_write = file_write or (operation == 'workload' and isinstance(payload, dict) and
                      payload.get('operation') == 'proxy' and payload.get('method') not in ('GET', 'HEAD'))
        file_write = file_write or (operation == 'workspace' and isinstance(payload, dict) and
                      payload.get('operation') in {'write', 'git_stage', 'git_commit'})
        send_attempted = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(80 if operation == 'workspace' and isinstance(payload, dict) and
                                      payload.get('operation') == 'git_commit' else 20)
                connection.connect(self.socket_path)
                try:
                    send_attempted = True
                    connection.sendall(_canonical(message) + b'\n')
                except (BrokenPipeError, ConnectionResetError):
                    # Sob saturação o broker responde antes de ler a solicitação.
                    # A resposta de BUSY pode já estar no buffer do cliente.
                    pass
                with connection.makefile('rb') as stream:
                    raw = stream.readline(_MAX_MESSAGE + 1)
        except (AttributeError, OSError) as exc:
            code = 'UNKNOWN_WRITE_OUTCOME' if file_write and send_attempted else 'BROKER_UNAVAILABLE'
            raise BrokerError(code) from exc
        if not raw and file_write and send_attempted:
            raise BrokerError('UNKNOWN_WRITE_OUTCOME')
        return self._result(raw)

    def open_terminal(self, account_id: str, environment_id: str,
                      terminal_id: str) -> tuple[str, socket.socket]:
        message = self._message('terminal_attach', account_id, environment_id,
                                {'terminal_id': terminal_id})
        try:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except (AttributeError, OSError) as exc:
            raise BrokerError('BROKER_UNAVAILABLE') from exc
        try:
            connection.settimeout(20)
            connection.connect(self.socket_path)
            connection.sendall(_canonical(message) + b'\n')
            with connection.makefile('rb', buffering=0) as stream:
                raw = stream.readline(_MAX_MESSAGE + 1)
            result = self._result(raw)
            connection.settimeout(None)
            return result['exec_id'], connection
        except OSError as exc:
            connection.close()
            raise BrokerError('BROKER_UNAVAILABLE') from exc
        except BaseException:
            connection.close()
            raise

    def _message(self, operation: str, account_id: str, environment_id: str,
                 payload: dict | None) -> dict:
        if operation not in _OPERATIONS:
            raise BrokerError('OPERATION_DENIED')
        message = {'version': 1, 'operation': operation, 'account_id': account_id,
                   'environment_id': environment_id, 'expires_at': time.time() + 15,
                   'nonce': str(uuid.uuid4())}
        request_id = request_id_context.get()
        if request_id is not None:
            message['request_id'] = request_id
        if payload is not None:
            message['payload'] = payload
        signature = hmac.new(self.secret, _canonical(message), hashlib.sha256).hexdigest()
        message['signature'] = signature
        return message

    @staticmethod
    def _result(raw: bytes) -> dict:
        if not raw or len(raw) > _MAX_MESSAGE:
            raise BrokerError('BROKER_UNAVAILABLE')
        try:
            result = json.loads(raw)
        except ValueError as exc:
            raise BrokerError('BROKER_UNAVAILABLE') from exc
        if not isinstance(result, dict) or type(result.get('version')) is not int or result['version'] != 1:
            raise BrokerError('BROKER_PROTOCOL')
        if set(result) == {'version', 'error'}:
            error = result['error']
            if not isinstance(error, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', error):
                raise BrokerError('BROKER_PROTOCOL')
            raise BrokerError(error)
        if set(result) != {'version', 'data'}:
            raise BrokerError('BROKER_PROTOCOL')
        return result['data']


class BrokerEnvironmentAdapter:
    """Porta de ambiente compatível com a composição, sem daemon no cliente."""

    def __init__(self, client: BrokerClient):
        self.client = client

    def ensure(self, account_id: str, environment_id: str) -> Environment:
        return Environment(**self.client.call('ensure', account_id, environment_id))

    def state(self, account_id: str, environment_id: str) -> Environment:
        return Environment(**self.client.call('state', account_id, environment_id))

    def stop_session(self, account_id: str, environment_id: str) -> None:
        self.client.call('stop_session', account_id, environment_id)

    def delete_account(self, account_id: str, environment_id: str) -> None:
        self.client.call('delete_account', account_id, environment_id)


@dataclass
class _TerminalStream:
    exec_id: str
    stream: object


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            self.connection.settimeout(self.server.request_timeout)
            try:
                raw = self.rfile.readline(_MAX_MESSAGE + 1)
            except OSError:
                logging.getLogger('aetherdesk.broker').warning('result=REQUEST_TIMEOUT')
                return
            try:
                request = None
                if not raw or len(raw) > _MAX_MESSAGE:
                    raise BrokerError('INVALID_REQUEST')
                request = json.loads(raw)
                data = self.server.dispatcher.dispatch(request)
                operation, account, nonce, request_id = _audit_fields(request)
                logging.getLogger('aetherdesk.broker').info(
                    'operation=%s account=%s nonce=%s request_id=%s result=ok',
                    operation, account, nonce, request_id)
                if isinstance(data, _TerminalStream):
                    self.wfile.write(_canonical({'version': 1, 'data': {'exec_id': data.exec_id}}) + b'\n')
                    self.wfile.flush()
                    upstream = getattr(data.stream, '_sock', data.stream)
                    self.connection.settimeout(self.server.relay_timeout)
                    upstream.settimeout(self.server.relay_timeout)
                    try:
                        while True:
                            readable, _, _ = select.select((self.connection, upstream), (), (), 30)
                            if not readable:
                                continue
                            for source in readable:
                                chunk = source.recv(4096)
                                if not chunk:
                                    return
                                (upstream if source is self.connection else self.connection).sendall(chunk)
                    finally:
                        data.stream.close()
                        self.server.dispatcher.terminal_finished(data.exec_id)
                response = {'version': 1, 'data': data}
            except (BrokerError, DockerRuntimeError, WorkloadError, IdentityError) as exc:
                response = {'version': 1, 'error': exc.code if isinstance(exc, (DockerRuntimeError, IdentityError)) else str(exc)}
                operation, account, nonce, request_id = _audit_fields(request)
                if response['error'] == 'UNAUTHENTICATED':
                    operation, account, nonce, request_id = '-', '-', '-', '-'
                logging.getLogger('aetherdesk.broker').warning(
                    'operation=%s account=%s nonce=%s request_id=%s result=%s',
                    operation, account, nonce, request_id, response['error'])
            except (TypeError, ValueError, KeyError):
                response = {'version': 1, 'error': 'INVALID_REQUEST'}
                operation, account, nonce, request_id = _audit_fields(request)
                logging.getLogger('aetherdesk.broker').warning(
                    'operation=%s account=%s nonce=%s request_id=%s result=INVALID_REQUEST',
                    operation, account, nonce, request_id)
            self.wfile.write(_canonical(response) + b'\n')
        except OSError:
            # Cliente desconectado ou relay PTY encerrado.
            pass


class _FileAgentProcess:
    def __init__(self, container: str):
        self.lock = threading.Lock()
        self.last_used = time.monotonic()
        self.process = subprocess.Popen(
            ['docker', 'exec', '-i', '--user', '10001:10001', container,
             'python3', '/opt/aetherdesk/file_agent.py', '--serve'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0)

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()

    def exchange(self, payload: bytes) -> dict:
        if self.process.poll() is not None:
            raise BrokerError('FILE_UNAVAILABLE')
        deadline = time.monotonic() + (70 if b'"operation":"ws_git_commit"' in payload else 30)
        request = memoryview(payload + b'\n')
        while request:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrokerError('FILE_UNAVAILABLE')
            try:
                if not select.select([], [self.process.stdin], [], remaining)[1]:
                    raise BrokerError('FILE_UNAVAILABLE')
                written = os.write(self.process.stdin.fileno(), request)
                if not written:
                    raise BrokerError('FILE_UNAVAILABLE')
                request = request[written:]
            except (OSError, ValueError) as exc:
                raise BrokerError('FILE_UNAVAILABLE') from exc
        response = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrokerError('FILE_UNAVAILABLE')
            try:
                if not select.select([self.process.stdout], [], [], remaining)[0]:
                    raise BrokerError('FILE_UNAVAILABLE')
                chunk = os.read(self.process.stdout.fileno(), 64 * 1024)
            except (OSError, ValueError) as exc:
                raise BrokerError('FILE_UNAVAILABLE') from exc
            if not chunk or len(response) + len(chunk) > _MAX_MESSAGE + 1:
                raise BrokerError('FILE_UNAVAILABLE')
            response.extend(chunk)
            if b'\n' in chunk:
                if not response.endswith(b'\n') or response.count(b'\n') != 1:
                    raise BrokerError('FILE_UNAVAILABLE')
                break
        try:
            result = json.loads(response)
        except ValueError as exc:
            raise BrokerError('FILE_UNAVAILABLE') from exc
        self.last_used = time.monotonic()
        return _file_result(result)


class _FileAgentPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.agents: dict[str, _FileAgentProcess] = {}
        self.legacy: set[str] = set()

    def call(self, container: str, payload: dict) -> dict:
        request = _canonical(payload)
        if len(request) > 12 * 1024 * 1024:
            raise BrokerError('TOO_LARGE')
        file_write = payload.get('operation') in {'write', 'mkdir', 'move', 'copy', 'delete',
                                                   'ws_write', 'ws_git_stage', 'ws_git_commit'}
        with self.lock:
            if container not in self.agents and container not in self.legacy:
                try:
                    probe = subprocess.run(
                        ['docker', 'exec', '--user', '10001:10001', container,
                         'test', '-f', '/opt/aetherdesk/.aetherdesk-file-stream-v1'],
                        capture_output=True, timeout=5)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise BrokerError('FILE_UNAVAILABLE') from exc
                if probe.returncode == 1:
                    self.legacy.add(container)
                elif probe.returncode != 0:
                    raise BrokerError('FILE_UNAVAILABLE')
            legacy = container in self.legacy
            agent = self.agents.get(container) if not legacy else None
            if not legacy and agent is None:
                if len(self.agents) >= 32:
                    for name, candidate in sorted(self.agents.items(),
                                                  key=lambda item: item[1].last_used):
                        if candidate.lock.acquire(blocking=False):
                            try:
                                candidate.close()
                                del self.agents[name]
                            finally:
                                candidate.lock.release()
                            break
                    else:
                        raise BrokerError('BROKER_BUSY')
                try:
                    agent = _FileAgentProcess(container)
                except OSError as exc:
                    raise BrokerError('FILE_UNAVAILABLE') from exc
                self.agents[container] = agent
        if legacy:
            try:
                return BrokerDispatch._run_file_agent(container, payload)
            except BrokerError as exc:
                if file_write and str(exc) == 'FILE_UNAVAILABLE':
                    raise BrokerError('UNKNOWN_WRITE_OUTCOME') from exc
                raise
        with agent.lock:
            try:
                return agent.exchange(request)
            except BrokerError as exc:
                if str(exc) in _FILE_ERRORS:
                    raise
                with self.lock:
                    if self.agents.get(container) is agent:
                        del self.agents[container]
                agent.close()
                if file_write and str(exc) == 'FILE_UNAVAILABLE':
                    raise BrokerError('UNKNOWN_WRITE_OUTCOME') from exc
                raise

    def discard(self, container: str):
        with self.lock:
            self.legacy.discard(container)
            agent = self.agents.pop(container, None)
        if agent is not None:
            with agent.lock:
                agent.close()

    def close(self):
        with self.lock:
            names = list(self.agents)
            self.legacy.clear()
        for name in names:
            self.discard(name)


class BrokerDispatch:
    def __init__(self, secret: bytes, runtime: DockerEnvironmentBroker,
                 file_runner=None, metrics_source=None, terminal_api=None,
                 account_resolver=None, nonce_db_path: str | Path | None = None,
                 workload_service=None, identity=None, proxy_service=None):
        if len(secret) < 32:
            raise BrokerError('WEAK_BROKER_SECRET')
        self.secret, self.runtime = secret, runtime
        self._file_pool = _FileAgentPool() if file_runner is None else None
        self.file_runner = file_runner or self._file_pool.call
        self.metrics_source = metrics_source
        self._owns_metrics_source = metrics_source is None
        self._metrics_cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._metrics_lock = threading.Lock()
        self.terminal_api = terminal_api
        self._terminal_docker_client = None
        self._api_lock = threading.Lock()
        self.account_resolver = account_resolver
        self.workload_service = workload_service
        self.proxy_service = proxy_service
        self.identity = identity
        self._file_slots = threading.BoundedSemaphore(_MAX_FILE_OPERATIONS)
        self._terminal_execs: dict[str, tuple[str, str]] = {}
        self._terminal_lock = threading.Lock()
        self._nonces: dict[str, float] = {}
        self._nonce_lock = threading.Lock()
        self.nonce_db_path = str(nonce_db_path) if nonce_db_path is not None else None
        if self.nonce_db_path is not None:
            apply_migration(self.nonce_db_path, 'broker.nonces.v1', lambda db: db.execute(
                'CREATE TABLE broker_nonces '
                '(nonce TEXT PRIMARY KEY, expires_at REAL NOT NULL)'))
            apply_migration(self.nonce_db_path, 'broker.git_ops.v1', lambda db: db.execute('''
                CREATE TABLE IF NOT EXISTS broker_git_ops (
                    account_id TEXT NOT NULL, operation_id TEXT NOT NULL, args_hash TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT,
                    PRIMARY KEY(account_id,operation_id))'''))

    def _reserve_nonce(self, nonce: str, expires_at: float, now: float,
                       persistent: bool) -> None:
        if persistent and self.nonce_db_path is not None:
            try:
                with closing(sqlite3.connect(self.nonce_db_path, timeout=5)) as db:
                    with db:
                        db.execute('DELETE FROM broker_nonces WHERE expires_at<=?', (now,))
                        count = db.execute('SELECT COUNT(*) FROM broker_nonces').fetchone()[0]
                        if count >= 50_000:
                            raise BrokerError('BROKER_BUSY')
                        db.execute('INSERT INTO broker_nonces(nonce,expires_at) VALUES(?,?)',
                                   (nonce, expires_at))
            except sqlite3.IntegrityError as exc:
                raise BrokerError('REPLAY_DENIED') from exc
            except sqlite3.Error as exc:
                raise BrokerError('BROKER_UNAVAILABLE') from exc
            return
        with self._nonce_lock:
            self._nonces = {key: expiry for key, expiry in self._nonces.items() if expiry > now}
            if nonce in self._nonces:
                raise BrokerError('REPLAY_DENIED')
            if len(self._nonces) >= 50000:
                raise BrokerError('BROKER_BUSY')
            self._nonces[nonce] = expires_at

    def dispatch(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise BrokerError('INVALID_REQUEST')
        signature = request.get('signature')
        message = {key: value for key, value in request.items() if key != 'signature'}
        if not isinstance(signature, str) or not secrets.compare_digest(
            signature, hmac.new(self.secret, _canonical(message), hashlib.sha256).hexdigest()
        ):
            raise BrokerError('UNAUTHENTICATED')
        base_fields = {'version', 'operation', 'account_id', 'environment_id', 'expires_at', 'nonce'}
        operation = message.get('operation')
        if not isinstance(operation, str):
            raise BrokerError('INVALID_REQUEST')
        expected_fields = base_fields | ({'payload'} if operation in _PAYLOAD_OPERATIONS else set())
        if 'request_id' in message:
            expected_fields.add('request_id')
        if set(message) != expected_fields:
            raise BrokerError('INVALID_REQUEST')
        if 'request_id' in message and (not isinstance(message['request_id'], str) or
                                        not re.fullmatch(r'[0-9a-f]{24}', message['request_id'])):
            raise BrokerError('INVALID_REQUEST')
        if type(message['version']) is not int or message['version'] != 1:
            raise BrokerError('BROKER_PROTOCOL')
        if operation not in _OPERATIONS:
            raise BrokerError('OPERATION_DENIED')
        now = time.time()
        if not isinstance(message['expires_at'], (int, float)) or not now < message['expires_at'] <= now + 30:
            raise BrokerError('EXPIRED_REQUEST')
        try:
            account = str(uuid.UUID(message['account_id']))
            environment = str(uuid.UUID(message['environment_id']))
            nonce = str(uuid.UUID(message['nonce']))
        except (TypeError, ValueError) as exc:
            raise BrokerError('INVALID_REQUEST') from exc
        if operation != 'ping' and self.account_resolver is not None:
            record = self.account_resolver(account)
            if not record or record['environment_id'] != environment:
                raise BrokerError('ENVIRONMENT_NOT_FOUND')
            if message['operation'] == 'delete_account':
                if record['state'] != 'deleted':
                    raise BrokerError('OPERATION_DENIED')
            elif record['state'] != 'active' and message['operation'] not in ('state', 'stop_session'):
                raise BrokerError('ACCOUNT_INACTIVE')
        payload = message.get('payload')
        persistent = operation not in ('ping', 'state', 'environment_metrics') and (
            operation != 'file_agent' or not isinstance(payload, dict) or
            payload.get('operation') not in ('list', 'metadata', 'read'))
        self._reserve_nonce(nonce, message['expires_at'], now, persistent)
        if operation == 'ping':
            return {'protocol': 1, 'ready': True}
        if operation == 'ensure':
            return asdict(self.runtime.ensure(account, environment))
        if operation == 'state':
            return asdict(self.runtime.state(account, environment))
        if operation == 'file_agent':
            payload = message['payload']
            if (not isinstance(payload, dict) or set(payload) - {'operation', 'path', 'content',
                    'revision', 'replace', 'destination'} or
                    not isinstance(payload.get('operation'), str) or
                    payload['operation'] not in _FILE_OPERATIONS or
                    not isinstance(payload.get('path'), str) or len(payload['path']) > 4096):
                raise BrokerError('INVALID_FILE_REQUEST')
            if not self._file_slots.acquire(blocking=False):
                raise BrokerError('BROKER_BUSY')
            try:
                container = self.runtime.ensure(account, environment).container_name
                return self.file_runner(container, payload)
            finally:
                self._file_slots.release()
        if operation == 'workload':
            return self._workload(account, payload)
        if operation == 'workspace':
            return self._workspace(account, environment, payload)
        if operation == 'environment_metrics':
            state = self.runtime.state(account, environment)
            key = (account, environment)
            if state.state != 'running':
                with self._metrics_lock:
                    self._metrics_cache.pop(key, None)
                return {'state': state.state, 'cpu_percent': None, 'memory_bytes': None}
            with self._metrics_lock:
                cached = self._metrics_cache.get(key)
                if cached and time.monotonic() - cached[0] < 4:
                    return dict(cached[1])
                if self.metrics_source is None:
                    from apps.AetherDesk.monitor.service import MetricsSource
                    self.metrics_source = MetricsSource()
                source = self.metrics_source
            result = source.environment(state.container_name)
            with self._metrics_lock:
                if len(self._metrics_cache) >= 1024:
                    self._metrics_cache = {owner: item for owner, item in self._metrics_cache.items()
                                           if time.monotonic() - item[0] < 4}
                    if len(self._metrics_cache) >= 1024:
                        self._metrics_cache.pop(min(self._metrics_cache,
                            key=lambda owner: self._metrics_cache[owner][0]))
                self._metrics_cache[key] = (time.monotonic(), result)
            return result
        if operation in ('terminal_create', 'terminal_attach', 'terminal_resize', 'terminal_kill'):
            return self._terminal(operation, account, environment, message['payload'])
        if operation == 'stop_session':
            self.runtime.stop_session(account, environment)
        else:
            self.runtime.delete_account(account, environment)
        if self._file_pool is not None:
            self._file_pool.discard(DockerEnvironmentBroker._names(environment)[0])
        with self._metrics_lock:
            self._metrics_cache.pop((account, environment), None)
        return {'ok': True}

    def _workload(self, account: str, payload: object) -> dict:
        if self.workload_service is None or self.identity is None:
            raise BrokerError('FEATURE_DISABLED')
        if not isinstance(payload, dict) or not isinstance(payload.get('operation'), str):
            raise BrokerError('INVALID_WORKLOAD_REQUEST')
        operation = payload['operation']
        fields = {
            'list_mine': set(), 'list_controllable': set(), 'templates': set(),
            'project': {'name'}, 'create': {'project_id', 'name'},
            'state': {'workload_id'}, 'admin_state': {'workload_id'},
            'job': {'job_id'}, 'cancel': {'job_id'},
            'request': {'workload_id', 'action', 'operation_id', 'template'},
            'admin_request': {'workload_id', 'action', 'operation_id'},
            'logs': {'workload_id'}, 'metrics': {'workload_id'},
            'configure_secrets': {'workload_id', 'references', 'operation_id'},
            'proxy': {'host', 'method', 'path', 'headers', 'body'},
        }
        if operation not in fields or set(payload) != fields[operation] | {'operation', 'session_id'}:
            raise BrokerError('INVALID_WORKLOAD_REQUEST')
        try:
            session_id = str(uuid.UUID(payload['session_id']))
        except (TypeError, ValueError, KeyError) as exc:
            raise BrokerError('INVALID_WORKLOAD_REQUEST') from exc
        actor = ActorContext(account, session_id, 'member', 0)
        self.identity.assert_active(actor)
        service = self.workload_service
        if operation == 'list_mine':
            return {'items': service.list_mine(actor)}
        if operation == 'list_controllable':
            return {'items': service.list_controllable(actor)}
        if operation == 'templates':
            return {'items': service.approved_templates(actor)}
        if operation == 'project':
            return {'id': service.project(actor, payload['name'])}
        if operation == 'create':
            return {'id': service.create(actor, payload['project_id'], payload['name'])}
        if operation == 'state':
            return service.state(actor, payload['workload_id'])
        if operation == 'admin_state':
            return service.admin_state(actor, payload['workload_id'])
        if operation == 'job':
            return service.job(actor, payload['job_id'])
        if operation == 'cancel':
            return service.cancel(actor, payload['job_id'])
        if operation == 'request':
            return service.request(actor, payload['workload_id'], payload['action'],
                                   payload['operation_id'], payload['template'])
        if operation == 'admin_request':
            return service.admin_request(actor, payload['workload_id'], payload['action'],
                                         payload['operation_id'])
        if operation == 'logs':
            return {'text': service.logs(actor, payload['workload_id'])}
        if operation == 'metrics':
            return service.metrics(actor, payload['workload_id'])
        if operation == 'configure_secrets':
            service.configure_secrets(actor, payload['workload_id'], payload['references'],
                                      payload['operation_id'])
            return {'ok': True}
        if operation == 'proxy':
            if self.proxy_service is None:
                raise BrokerError('ROUTE_DISABLED')
            if (not isinstance(payload['body'], str) or len(payload['body']) > 1400000 or
                    not isinstance(payload['headers'], dict) or len(payload['headers']) > 100 or
                    any(type(key) is not str or type(value) is not str
                        for key, value in payload['headers'].items())):
                raise BrokerError('PROXY_INVALID_REQUEST')
            try:
                body = base64.b64decode(payload['body'], validate=True)
            except (binascii.Error, ValueError) as exc:
                raise BrokerError('PROXY_INVALID_REQUEST') from exc
            status, headers, response_body = self.proxy_service.request(
                actor, payload['host'], payload['method'], payload['path'],
                payload['headers'], body)
            return {'status': status, 'headers': headers,
                    'body': base64.b64encode(response_body).decode('ascii')}
        raise BrokerError('INVALID_WORKLOAD_REQUEST')

    def _workspace(self, account: str, environment: str, payload: object):
        if self.identity is None:
            raise BrokerError('FEATURE_DISABLED')
        if not isinstance(payload, dict) or not isinstance(payload.get('operation'), str):
            raise BrokerError('INVALID_WORKSPACE_REQUEST')
        operation = payload['operation']
        fields = {
            'tree': set(), 'read': {'path'}, 'write': {'path', 'content', 'revision'},
            'search': {'query'}, 'git_status': set(), 'git_diff': {'path'},
            'git_stage': {'paths'}, 'git_commit': {'message', 'operation_id'},
        }
        if operation not in fields or set(payload) != fields[operation] | {'operation', 'session_id'}:
            raise BrokerError('INVALID_WORKSPACE_REQUEST')
        try:
            session_id = str(uuid.UUID(payload['session_id']))
        except (TypeError, ValueError, KeyError) as exc:
            raise BrokerError('INVALID_WORKSPACE_REQUEST') from exc
        actor = ActorContext(account, session_id, 'member', 0)
        cap = ('files.write' if operation == 'write' else
               'git.write' if operation in ('git_stage', 'git_commit') else
               'git.read' if operation.startswith('git_') else 'files.read')
        self.identity.require(actor, 'ide.open')
        self.identity.require(actor, cap)
        state = self.runtime.ensure(account, environment)
        checked = self.runtime.exec_status(account, environment,
                                           ['test', '-f', '/opt/aetherdesk/.aetherdesk-workspace-v2'])
        if checked.returncode != 0:
            raise BrokerError('WORKSPACE_AGENT_UPGRADE_REQUIRED')
        request = {'operation': 'ws_' + operation, 'account_id': account,
                   **{key: value for key, value in payload.items() if key not in ('operation', 'session_id')}}
        if operation == 'git_commit':
            if self.nonce_db_path is None:
                raise BrokerError('GIT_COMMIT_DISABLED')
            if (not isinstance(payload['message'], str) or not 1 <= len(payload['message']) <= 2000 or
                    '\0' in payload['message']):
                raise BrokerError('INVALID_COMMIT')
            try:
                operation_id = str(uuid.UUID(payload['operation_id']))
            except (TypeError, ValueError) as exc:
                raise BrokerError('INVALID_OPERATION_ID') from exc
            username = self.identity.account(actor, account)['username']
            request['author_name'] = username
            request['author_email'] = f'{uuid.UUID(account).hex}@aetherdesk.local'
            del request['operation_id']
            digest = hashlib.sha256(_canonical({'message': payload['message']})).hexdigest()
            with closing(sqlite3.connect(self.nonce_db_path, timeout=5)) as db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('''SELECT args_hash,status,result FROM broker_git_ops
                    WHERE account_id=? AND operation_id=?''', (account, operation_id)).fetchone()
                if previous:
                    db.commit()
                    if not hmac.compare_digest(previous[0], digest):
                        raise BrokerError('OPERATION_CONFLICT')
                    if previous[1] == 'completed':
                        return {'hash': previous[2]}
                    raise BrokerError('UNKNOWN_WRITE_OUTCOME')
                db.execute('INSERT INTO broker_git_ops VALUES(?,?,?,?,NULL)',
                           (account, operation_id, digest, 'pending'))
                db.commit()
        if not self._file_slots.acquire(blocking=False):
            if operation == 'git_commit':
                with closing(sqlite3.connect(self.nonce_db_path, timeout=5)) as db, db:
                    db.execute("DELETE FROM broker_git_ops WHERE account_id=? AND operation_id=? AND status='pending'",
                               (account, operation_id))
            raise BrokerError('BROKER_BUSY')
        try:
            result = self.file_runner(state.container_name, request)
            if operation == 'git_commit':
                with closing(sqlite3.connect(self.nonce_db_path, timeout=5)) as db, db:
                    db.execute("UPDATE broker_git_ops SET status='completed',result=? "
                               'WHERE account_id=? AND operation_id=? AND status=\'pending\'',
                               (result['hash'], account, operation_id))
            return result
        except BaseException:
            if operation == 'git_commit':
                with closing(sqlite3.connect(self.nonce_db_path, timeout=5)) as db, db:
                    db.execute("UPDATE broker_git_ops SET status='unknown' "
                               "WHERE account_id=? AND operation_id=? AND status='pending'",
                               (account, operation_id))
            raise
        finally:
            self._file_slots.release()

    def _terminal(self, operation: str, account: str, environment: str, payload: dict):
        expected = {'terminal_id', 'columns', 'rows'} if operation == 'terminal_create' else (
            {'terminal_id'} if operation in ('terminal_attach', 'terminal_kill') else
            {'exec_id', 'columns', 'rows'})
        if not isinstance(payload, dict) or set(payload) != expected:
            raise BrokerError('INVALID_TERMINAL_REQUEST')
        if operation == 'terminal_resize':
            exec_id = payload['exec_id']
            if not isinstance(exec_id, str) or not self._size(payload):
                raise BrokerError('INVALID_TERMINAL_REQUEST')
            with self._terminal_lock:
                owner = self._terminal_execs.get(exec_id)
            if owner != (account, environment):
                raise BrokerError('TERMINAL_NOT_FOUND')
            self._api().exec_resize(exec_id, height=payload['rows'], width=payload['columns'])
            return {'ok': True}
        try:
            terminal_id = str(uuid.UUID(payload['terminal_id']))
        except (TypeError, ValueError) as exc:
            raise BrokerError('INVALID_TERMINAL_REQUEST') from exc
        if operation == 'terminal_create':
            if not self._size(payload):
                raise BrokerError('INVALID_TERMINAL_REQUEST')
            self.runtime.ensure(account, environment)
            existing = self.runtime.exec_status(account, environment, [
                'tmux', '-L', 'aether', '-f', '/dev/null', 'has-session', '-t', terminal_id])
            if existing.returncode == 0:
                return {'ok': True}
            if existing.returncode != 1:
                raise BrokerError('RUNTIME_UNAVAILABLE')
            self.runtime.exec(account, environment, [
                'tmux', '-L', 'aether', '-f', '/dev/null', 'new-session', '-d',
                '-s', terminal_id, '-c', '/persist', '-x', str(payload['columns']),
                '-y', str(payload['rows']), '/bin/bash'])
            return {'ok': True}
        state = self.runtime.state(account, environment)
        if state.state != 'running':
            raise BrokerError('ENVIRONMENT_STOPPED')
        if operation == 'terminal_kill':
            self.runtime.exec(account, environment, [
                'tmux', '-L', 'aether', 'kill-session', '-t', terminal_id])
            return {'ok': True}
        api = self._api()
        command = ['tmux', '-L', 'aether', '-f', '/dev/null', 'attach-session', '-t', terminal_id]
        with self._terminal_lock:
            if (len(self._terminal_execs) >= _MAX_TERMINAL_ATTACHMENTS or
                sum(1 for owner, _ in self._terminal_execs.values() if owner == account)
                    >= _MAX_TERMINAL_ATTACHMENTS_PER_ACCOUNT):
                raise BrokerError('TERMINAL_QUOTA')
            execution = api.exec_create(state.container_name, command, stdin=True, tty=True,
                                        stdout=True, stderr=True, user='10001:10001')
            stream = api.exec_start(execution['Id'], tty=True, socket=True)
            self._terminal_execs[execution['Id']] = (account, environment)
        return _TerminalStream(execution['Id'], stream)

    @staticmethod
    def _size(payload: dict) -> bool:
        columns, rows = payload.get('columns'), payload.get('rows')
        return (type(columns) is int and type(rows) is int and
                20 <= columns <= 400 and 5 <= rows <= 200)

    def _api(self):
        if self.terminal_api is None:
            with self._api_lock:
                if self.terminal_api is None:
                    import docker
                    self._terminal_docker_client = docker.from_env()
                    self.terminal_api = self._terminal_docker_client.api
        return self.terminal_api

    def close(self):
        if self._file_pool is not None:
            self._file_pool.close()
        if self._owns_metrics_source and self.metrics_source is not None:
            self.metrics_source.close()
        if self._terminal_docker_client is not None:
            self._terminal_docker_client.close()

    def terminal_finished(self, exec_id: str) -> None:
        with self._terminal_lock:
            self._terminal_execs.pop(exec_id, None)

    @staticmethod
    def _run_file_agent(container: str, payload: dict) -> dict:
        request = _canonical(payload)
        if len(request) > 12 * 1024 * 1024:
            raise BrokerError('TOO_LARGE')
        try:
            process = subprocess.run(['docker', 'exec', '-i', '--user', '10001:10001',
                container, 'python3', '/opt/aetherdesk/file_agent.py'],
                input=request, capture_output=True, timeout=30)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise BrokerError('FILE_UNAVAILABLE') from exc
        if len(process.stdout) > _MAX_MESSAGE:
            raise BrokerError('FILE_UNAVAILABLE')
        try:
            result = json.loads(process.stdout)
        except ValueError as exc:
            raise BrokerError('FILE_UNAVAILABLE') from exc
        return _file_result(result, returncode=process.returncode)


_UnixServer = getattr(socketserver, 'ThreadingUnixStreamServer', socketserver.BaseServer)


class BrokerServer(_UnixServer):
    daemon_threads = True

    def __init__(self, socket_path: str | Path, secret: bytes,
                 runtime: DockerEnvironmentBroker, file_runner=None, metrics_source=None,
                 terminal_api=None, account_resolver=None, request_timeout: float = 10,
                 relay_timeout: float = 10, nonce_db_path: str | Path | None = None,
                 workload_service=None, identity=None, proxy_service=None):
        if not hasattr(socketserver, 'ThreadingUnixStreamServer'):
            raise BrokerError('BROKER_REQUIRES_UNIX')
        path = Path(socket_path)
        if not path.is_absolute() or not path.parent.is_dir() or path.exists():
            raise BrokerError('INVALID_SOCKET_PATH')
        if request_timeout <= 0 or request_timeout > 30:
            raise BrokerError('INVALID_REQUEST_TIMEOUT')
        if relay_timeout <= 0 or relay_timeout > 30:
            raise BrokerError('INVALID_RELAY_TIMEOUT')
        self.dispatcher = BrokerDispatch(secret, runtime, file_runner, metrics_source,
                                         terminal_api, account_resolver, nonce_db_path,
                                         workload_service, identity, proxy_service)
        self.connection_slots = threading.BoundedSemaphore(_MAX_CONNECTIONS)
        self.request_timeout = request_timeout
        self.relay_timeout = relay_timeout
        super().__init__(str(path), _Handler)
        self.socket_path = path
        path.chmod(0o660)

    def process_request(self, request, client_address):
        # Reservar antes de criar a thread: um cliente ocioso não pode gerar
        # uma quantidade ilimitada de threads enquanto o handler aguarda IO.
        if not self.connection_slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(_canonical({'version': 1, 'error': 'BROKER_BUSY'}) + b'\n')
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()

    def server_close(self):
        self.dispatcher.close()
        super().server_close()
        if self.socket_path.exists() and stat.S_ISSOCK(self.socket_path.stat().st_mode):
            self.socket_path.unlink()

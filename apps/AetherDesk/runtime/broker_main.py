"""Processo separado que detém o acesso ao daemon Docker em Linux."""

from __future__ import annotations

import base64
import os
import sqlite3
import threading
import logging
from logging.handlers import RotatingFileHandler
import signal
import time
from pathlib import Path

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.backup.service import BackupService
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService
from .broker_ipc import BrokerError, BrokerServer
from .docker import DockerEnvironmentBroker
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.workloads import WorkloadService, DockerWorkloadRuntime, TemplateRegistry
from apps.AetherDesk.workloads.proxy import WorkloadProxy
from apps.AetherDesk.support.secrets import Keyring, SecretVault


def main() -> None:
    features = frozenset(part.strip() for part in os.environ.get('AETHERDESK_FEATURES', '').split(',') if part.strip())
    if not features.issubset({'ide', 'workloads', 'ai'}):
        raise BrokerError('INVALID_FEATURE_FLAG')
    safe_mode = os.environ.get('AETHERDESK_SAFE_MODE') == '1'
    if safe_mode or os.environ.get('AETHERDESK_KILL_AI') == '1':
        features = features - {'ai'}
    # Também protege arquivos criados pelo handler após cada rotação.
    os.umask(0o077)
    socket_path = Path(os.environ.get('AETHERDESK_BROKER_SOCKET', ''))
    encoded = os.environ.get('AETHERDESK_BROKER_SECRET_B64', '')
    try:
        secret = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise BrokerError('INVALID_BROKER_SECRET') from exc
    if not socket_path.is_absolute() or not socket_path.parent.is_dir():
        raise BrokerError('INVALID_SOCKET_PATH')
    if socket_path.parent.stat().st_mode & 0o007:
        raise BrokerError('INSECURE_SOCKET_DIRECTORY')
    data_dir = Path(os.environ.get('AETHERDESK_DATA_DIR', '/var/lib/aetherdesk'))
    audit_path = Path(os.environ.get('AETHERDESK_BROKER_AUDIT_LOG',
                                     '/var/log/aetherdesk-broker/audit.log'))
    if not audit_path.is_absolute() or not audit_path.parent.is_dir():
        raise BrokerError('INVALID_AUDIT_PATH')
    try:
        audit_max_bytes = int(os.environ.get('AETHERDESK_BROKER_AUDIT_MAX_BYTES', '10485760'))
        audit_backups = int(os.environ.get('AETHERDESK_BROKER_AUDIT_BACKUPS', '5'))
    except ValueError as exc:
        raise BrokerError('INVALID_AUDIT_POLICY') from exc
    if not 1048576 <= audit_max_bytes <= 104857600 or not 1 <= audit_backups <= 100:
        raise BrokerError('INVALID_AUDIT_POLICY')
    audit_logger = logging.getLogger('aetherdesk.broker')
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    audit_handler = RotatingFileHandler(audit_path, maxBytes=audit_max_bytes,
                                        backupCount=audit_backups, encoding='utf-8')
    audit_path.chmod(0o600)
    audit_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    audit_logger.addHandler(audit_handler)
    bootstrap_token = os.environ.get('AETHERDESK_BOOTSTRAP_TOKEN', '')
    if len(bootstrap_token) < 16:
        raise BrokerError('INVALID_BOOTSTRAP_TOKEN')
    identity = IdentityService(data_dir / 'identity.sqlite3', bootstrap_token,
                               enabled_features=features,
                               kill_deploys=os.environ.get('AETHERDESK_KILL_DEPLOYS') == '1',
                               safe_mode=safe_mode)
    runtime = DockerEnvironmentBroker(os.environ.get('AETHERDESK_RUNTIME_IMAGE', 'aetherdesk-files:w003'))
    administration = AdministrationService(data_dir / 'identity.sqlite3', identity,
                                           AppComposition(identity, runtime))
    backup_encoded = os.environ.get('AETHERDESK_BACKUP_KEY_B64', '')
    try:
        backup_key = base64.b64decode(backup_encoded, validate=True) if backup_encoded else None
    except ValueError as exc:
        raise BrokerError('INVALID_BACKUP_KEY') from exc
    backup = BackupService(data_dir, administration, runtime,
                           encryption_key=backup_key, require_encryption=bool(features))
    workloads = None
    proxy = None
    workload_runtime = None
    if 'workloads' in features:
        try:
            signing_key = base64.b64decode(os.environ.get('AETHERDESK_WORKLOAD_SIGNING_KEY_B64', ''), validate=True)
            master_key = base64.b64decode(os.environ.get('AETHERDESK_MASTER_KEY_B64', ''), validate=True)
        except ValueError as exc:
            raise BrokerError('INVALID_WORKLOAD_KEYS') from exc
        if len(signing_key) < 32 or len(master_key) != 32:
            raise BrokerError('INVALID_WORKLOAD_KEYS')
        template_dir = Path(os.environ.get('AETHERDESK_WORKLOAD_TEMPLATE_DIR', ''))
        if not template_dir.is_absolute() or not template_dir.is_dir() or template_dir.is_symlink():
            raise BrokerError('INVALID_TEMPLATE_DIRECTORY')
        registry = TemplateRegistry(signing_key)
        templates = {}
        for manifest_path in sorted(template_dir.glob('*.manifest.json')):
            stem = manifest_path.name[:-len('.manifest.json')]
            if not stem or manifest_path.is_symlink():
                raise BrokerError('INVALID_TEMPLATE_DIRECTORY')
            blobs = []
            for suffix in ('manifest', 'sbom', 'provenance', 'scan'):
                path = template_dir / f'{stem}.{suffix}.json'
                if path.is_symlink() or not path.is_file():
                    raise BrokerError('INVALID_TEMPLATE_DIRECTORY')
                blobs.append(path.read_bytes())
            template = registry.load(*blobs)
            if template.name in templates:
                raise BrokerError('DUPLICATE_TEMPLATE')
            templates[template.name] = template
        if not templates:
            raise BrokerError('NO_APPROVED_TEMPLATES')
        vault = SecretVault(data_dir / 'workload-secrets.sqlite3', Keyring({1: master_key}, 1))
        def session_active(actor):
            try:
                identity.assert_active(actor)
                return True
            except IdentityError:
                return False
        workload_runtime = DockerWorkloadRuntime()
        workloads = WorkloadService(data_dir / 'workloads.sqlite3', workload_runtime,
                                    templates, identity.require, session_active, vault)
        proxy = WorkloadProxy(data_dir / 'workloads.sqlite3', identity.require,
                              session_active, workload_runtime.container_ip)
        if safe_mode:
            workloads.suspend_pending_mutations()
    for suffix in ('', '-wal', '-shm'):
        shared_db_file = data_dir / ('identity.sqlite3' + suffix)
        if shared_db_file.exists():
            shared_db_file.chmod(0o660)

    def account_record(account_id: str):
        with sqlite3.connect(identity.db_path) as db:
            row = db.execute('SELECT environment_id,state FROM accounts WHERE id=?',
                             (account_id,)).fetchone()
        return {'environment_id': row[0], 'state': row[1]} if row else None

    stopped = threading.Event()

    def backup_worker():
        while not stopped.is_set():
            try:
                backup.run_due()
            except Exception:
                logging.getLogger('aetherdesk.backup').exception('Backup falhou')
            stopped.wait(60)

    worker = threading.Thread(target=backup_worker, name='aetherdesk-backup', daemon=True)
    def workload_worker():
        if workloads is None:
            return
        last_route_sync = 0.0
        def sync_route(workload_id):
            with sqlite3.connect(workloads.db_path) as db:
                row = db.execute('''SELECT owner_id,template,desired,observed FROM workloads
                    WHERE id=?''', (workload_id,)).fetchone()
            if row is None:
                return
            owner, template_name, desired, observed = row
            template = workloads.templates.get(template_name)
            if (template and template.port and desired == 'running' and
                    observed in ('running', 'rolled_back')):
                try:
                    route = workload_runtime.proxy_route(owner, workload_id, template.port)
                except Exception:
                    proxy.unregister(owner, workload_id)
                    logging.getLogger('aetherdesk.workloads').warning(
                        'Rota retirada após container indisponível: %s', workload_id)
                    return
                proxy.register(route)
            else:
                proxy.unregister(owner, workload_id)
        while not stopped.is_set():
            try:
                if identity.kill_deploys:
                    workloads.suspend_pending_deploys()
                with sqlite3.connect(workloads.db_path) as db:
                    ids = [row[0] for row in db.execute('''SELECT DISTINCT w.id FROM workloads w
                        LEFT JOIN workload_jobs j ON j.workload_id=w.id AND j.status='pending'
                        WHERE j.id IS NOT NULL OR w.desired!=w.observed LIMIT 100''')]
                for workload_id in ids:
                    if stopped.is_set():
                        break
                    workloads.reconcile(workload_id)
                    sync_route(workload_id)
                if time.monotonic() - last_route_sync >= 30:
                    with sqlite3.connect(workloads.db_path) as db:
                        route_ids = [row[0] for row in db.execute('SELECT id FROM workloads')]
                    for workload_id in route_ids:
                        if stopped.is_set():
                            break
                        sync_route(workload_id)
                    last_route_sync = time.monotonic()
                workloads.gc()
            except Exception:
                logging.getLogger('aetherdesk.workloads').exception('Reconciliação falhou')
            stopped.wait(3)
    workload_thread = threading.Thread(target=workload_worker, name='aetherdesk-workloads', daemon=True)
    with BrokerServer(socket_path, secret, runtime, account_resolver=account_record,
                      nonce_db_path=data_dir / 'broker-nonces.sqlite3',
                      workload_service=workloads, identity=identity,
                      proxy_service=proxy) as server:
        worker.start()
        if workloads is not None and not safe_mode:
            workload_thread.start()
        server_thread = threading.Thread(target=server.serve_forever,
                                         name='aetherdesk-broker-ipc')
        server_thread.start()
        previous_term = signal.signal(signal.SIGTERM, lambda *_args: stopped.set())
        try:
            stopped.wait()
        except KeyboardInterrupt:
            pass
        finally:
            stopped.set()
            if workloads is not None and not safe_mode:
                workload_thread.join(timeout=5)
            server.shutdown()
            server_thread.join(timeout=5)
            worker.join(timeout=5)
            signal.signal(signal.SIGTERM, previous_term)
            audit_logger.removeHandler(audit_handler)
            audit_handler.close()


if __name__ == '__main__':
    main()

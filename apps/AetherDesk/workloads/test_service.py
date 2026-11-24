import tempfile
import sqlite3
from contextlib import closing
import threading
import unittest
import uuid
from pathlib import Path

from apps.AetherDesk.identity import ActorContext
from apps.AetherDesk.support.secrets import Keyring, SecretVault
from .service import ApprovedTemplate, WorkloadError, WorkloadService


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.current = {}
        self.fail_health = set()

    def ensure(self, owner, workload, template, revision=None):
        self.calls.append(('ensure', owner, workload, template.name, revision))
        self.current[workload] = template.name
        return 'running'

    def ensure_secrets(self, owner, workload, template, secrets, revision):
        self.calls.append(('ensure_secrets', owner, workload, tuple(sorted(secrets)), revision))
        self.current[workload] = template.name
        return 'running'

    def state(self, _owner, workload):
        return 'running' if workload in self.current else 'absent'

    def healthy(self, _owner, workload):
        return self.current[workload] not in self.fail_health

    def stop(self, _owner, workload):
        self.calls.append(('stop', workload))

    def remove(self, _owner, workload):
        self.calls.append(('remove', workload))
        self.current.pop(workload, None)

    def remove_volume(self, _owner, workload):
        self.calls.append(('remove_volume', workload))

    def logs(self, _owner, _workload, _limit):
        return 'private logs'


class WorkloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.actor = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.other = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'member', 1)
        self.admin = ActorContext(str(uuid.uuid4()), str(uuid.uuid4()), 'admin', 1)
        self.runtime = FakeRuntime()
        def authorize(actor, capability):
            if capability == 'workloads.control.other' and actor.role != 'admin':
                raise WorkloadError('FORBIDDEN')
        self.service = WorkloadService(Path(self.temp.name) / 'workloads.sqlite3', self.runtime,
            {'stable': ApprovedTemplate('stable', 'example/app@sha256:' + 'a' * 64,
                                        'b' * 64, 'c' * 64, True),
             'candidate': ApprovedTemplate('candidate', 'example/app@sha256:' + 'd' * 64,
                                           'e' * 64, 'f' * 64, True)},
            authorize, lambda _actor: True)
        self.project = self.service.project(self.actor, 'Meu projeto')
        self.workload = self.service.create(self.actor, self.project, 'api')

    def test_idempotency_ownership_and_health_rollback(self):
        operation = str(uuid.uuid4())
        first = self.service.request(self.actor, self.workload, 'deploy', operation, 'stable')
        self.assertEqual(self.service.request(self.actor, self.workload, 'deploy', operation, 'stable'), first)
        with self.assertRaisesRegex(WorkloadError, 'OPERATION_CONFLICT'):
            self.service.request(self.actor, self.workload, 'deploy', operation, 'candidate')
        self.assertTrue(self.service.reconcile(self.workload))
        self.assertEqual(self.service.state(self.actor, self.workload)['observed'], 'running')
        self.runtime.fail_health.add('candidate')
        self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'candidate')
        self.assertTrue(self.service.reconcile(self.workload))
        state = self.service.state(self.actor, self.workload)
        self.assertEqual((state['observed'], state['template']), ('rolled_back', 'stable'))
        self.assertEqual(self.runtime.current[self.workload], 'stable')
        self.assertEqual(self.service.job(self.actor, first['id'])['status'], 'completed')
        with self.assertRaisesRegex(WorkloadError, 'WORKLOAD_NOT_FOUND'):
            self.service.state(self.other, self.workload)
        self.assertEqual(self.service.logs(self.actor, self.workload), 'private logs')
        with self.assertRaisesRegex(WorkloadError, 'WORKLOAD_NOT_FOUND'):
            self.service.logs(self.other, self.workload)
        self.assertEqual(set(self.service.admin_state(self.admin, self.workload)),
                         {'id', 'name', 'desired', 'observed', 'template'})
        with self.assertRaisesRegex(WorkloadError, 'FORBIDDEN'):
            self.service.admin_state(self.other, self.workload)
        with self.assertRaisesRegex(WorkloadError, 'WORKLOAD_NOT_FOUND'):
            self.service.logs(self.admin, self.workload)
        self.service.admin_request(self.admin, self.workload, 'stop', str(uuid.uuid4()))
        self.service.reconcile(self.workload)
        self.assertEqual(self.service.state(self.actor, self.workload)['observed'], 'stopped')

    def test_deploy_kill_switch_reverts_pending_without_runtime_action(self):
        first = self.service.request(self.actor, self.workload, 'deploy',
                                     str(uuid.uuid4()), 'stable')
        self.assertEqual(self.service.suspend_pending_deploys(), 1)
        self.assertEqual(self.service.suspend_pending_deploys(), 0)
        self.assertEqual(self.service.job(self.actor, first['id'])['error_code'], 'DEPLOY_DISABLED')
        state = self.service.state(self.actor, self.workload)
        self.assertEqual((state['desired'], state['template']), ('stopped', None))
        self.assertEqual(self.runtime.calls, [])
        self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'stable')
        self.service.reconcile(self.workload)
        candidate = self.service.request(self.actor, self.workload, 'deploy',
                                         str(uuid.uuid4()), 'candidate')
        self.assertEqual(self.service.suspend_pending_deploys(), 1)
        state = self.service.state(self.actor, self.workload)
        self.assertEqual((state['desired'], state['template']), ('running', 'stable'))
        self.assertEqual(self.service.job(self.actor, candidate['id'])['status'], 'failed')

    def test_safe_mode_suspends_pending_workload_mutations(self):
        deploy = self.service.request(self.actor, self.workload, 'deploy',
                                      str(uuid.uuid4()), 'stable')
        self.assertEqual(self.service.suspend_pending_mutations(), 1)
        self.assertEqual(self.service.job(self.actor, deploy['id'])['error_code'], 'SAFE_MODE')
        self.service.request(self.actor, self.workload, 'deploy',
                             str(uuid.uuid4()), 'stable')
        self.service.reconcile(self.workload)
        stopped = self.service.request(self.actor, self.workload, 'stop', str(uuid.uuid4()))
        self.assertEqual(self.service.suspend_pending_mutations(), 1)
        self.assertEqual(self.service.job(self.actor, stopped['id'])['error_code'], 'SAFE_MODE')
        self.assertEqual(self.service.state(self.actor, self.workload)['desired'], 'running')

    def test_hostile_template_and_invalid_action_fail_before_runtime(self):
        self.assertEqual(self.service.project(self.actor, 'Meu projeto'), self.project)
        self.assertEqual(self.service.create(self.actor, self.project, 'api'), self.workload)
        with self.assertRaisesRegex(WorkloadError, 'UNAPPROVED_TEMPLATE'):
            ApprovedTemplate('unsafe', 'example/app:latest', 'b' * 64, 'c' * 64, True).validate()
        with self.assertRaisesRegex(WorkloadError, 'UNAPPROVED_TEMPLATE'):
            self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'dockerfile')
        with self.assertRaisesRegex(WorkloadError, 'INVALID_ACTION'):
            self.service.request(self.actor, self.workload, '--privileged', str(uuid.uuid4()))
        self.assertEqual(self.runtime.calls, [])

    def test_list_privacy_cancel_restores_desired_and_admin_job(self):
        self.assertEqual([item['id'] for item in self.service.list_mine(self.actor)], [self.workload])
        self.assertEqual(self.service.list_mine(self.other), [])
        admin_rows = self.service.list_controllable(self.admin)
        self.assertEqual([item['owner'] for item in admin_rows], ['other'])
        self.assertNotIn('secret_refs', admin_rows[0])
        with self.assertRaisesRegex(WorkloadError, 'FORBIDDEN'):
            self.service.list_controllable(self.other)
        job = self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'stable')
        self.assertEqual(self.service.job(self.admin, job['id'])['status'], 'pending')
        self.assertEqual(self.service.cancel(self.actor, job['id'])['status'], 'cancelled')
        state = self.service.state(self.actor, self.workload)
        self.assertEqual((state['desired'], state['template']), ('stopped', None))
        self.assertEqual(self.service.cancel(self.actor, job['id'])['status'], 'cancelled')
        self.assertEqual(self.runtime.calls, [])
        with self.assertRaisesRegex(WorkloadError, 'FORBIDDEN'):
            self.service.job(self.other, job['id'])

    def test_reconcile_stop_remove_and_no_duplicate_on_repeat(self):
        self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'stable')
        self.service.reconcile(self.workload)
        self.service.request(self.actor, self.workload, 'stop', str(uuid.uuid4()))
        self.service.reconcile(self.workload)
        self.assertEqual(self.service.state(self.actor, self.workload)['observed'], 'stopped')
        self.service.request(self.actor, self.workload, 'remove', str(uuid.uuid4()))
        self.service.reconcile(self.workload)
        self.assertEqual(self.service.state(self.actor, self.workload)['observed'], 'removed')
        with self.assertRaisesRegex(WorkloadError, 'WORKLOAD_REMOVED'):
            self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'stable')
        self.assertEqual(self.service.gc(), 0)
        self.service.removed_retention_seconds = 0
        self.assertEqual(self.service.gc(), 1)
        self.assertIn(('remove_volume', self.workload), self.runtime.calls)
        with self.assertRaisesRegex(WorkloadError, 'WORKLOAD_NOT_FOUND'):
            self.service.state(self.actor, self.workload)

    def test_secret_refs_are_private_and_revocation_stops_reconciliation(self):
        vault = SecretVault(Path(self.temp.name) / 'secrets.sqlite3',
                            Keyring({1: b'k' * 32}, 1))
        metadata = vault.store(self.actor.account_id, 'workload', 'api', b'private-token')
        git_secret = vault.store(self.actor.account_id, 'git', 'origin', b'wrong-scope')
        service = WorkloadService(Path(self.temp.name) / 'with-secrets.sqlite3', self.runtime,
            self.service.templates, lambda _actor, _cap: None, lambda _actor: True, vault=vault)
        project = service.project(self.actor, 'Secret project')
        workload = service.create(self.actor, project, 'api')
        with self.assertRaisesRegex(WorkloadError, 'SECRET_REF_UNAVAILABLE'):
            service.configure_secrets(self.other, workload, {'token': metadata['id']}, str(uuid.uuid4()))
        with self.assertRaisesRegex(WorkloadError, 'SECRET_REF_UNAVAILABLE'):
            service.configure_secrets(self.actor, workload, {'token': git_secret['id']}, str(uuid.uuid4()))
        operation = str(uuid.uuid4())
        service.configure_secrets(self.actor, workload, {'token': metadata['id']}, operation)
        revision = service.state(self.actor, workload)['revision']
        service.configure_secrets(self.actor, workload, {'token': metadata['id']}, operation)
        self.assertEqual(service.state(self.actor, workload)['revision'], revision)
        with self.assertRaisesRegex(WorkloadError, 'OPERATION_CONFLICT'):
            service.configure_secrets(self.actor, workload, {}, operation)
        service.request(self.actor, workload, 'deploy', str(uuid.uuid4()), 'stable')
        self.assertTrue(service.reconcile(workload))
        self.assertEqual(service.state(self.actor, workload)['observed'], 'running')
        self.assertNotIn('secret_refs', service.state(self.actor, workload))
        self.assertIn('ensure_secrets', [call[0] for call in self.runtime.calls])
        vault.revoke(self.actor.account_id, metadata['id'])
        self.assertTrue(service.reconcile(workload))
        self.assertEqual(service.state(self.actor, workload)['observed'], 'failed')
        self.assertIn(('stop', workload), self.runtime.calls)

    def test_new_request_supersedes_pending_job_without_false_completion(self):
        first = self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'stable')
        second = self.service.request(self.actor, self.workload, 'stop', str(uuid.uuid4()))
        self.assertEqual(self.service.job(self.actor, first['id'])['status'], 'superseded')
        self.assertEqual(self.service.job(self.actor, second['id'])['status'], 'pending')
        self.service.reconcile(self.workload)
        self.assertEqual(self.service.job(self.actor, first['id'])['status'], 'superseded')
        self.assertEqual(self.service.job(self.actor, second['id'])['status'], 'completed')
        self.assertEqual(self.service.state(self.actor, self.workload)['observed'], 'stopped')

    def test_start_requires_prior_deploy_and_restart_advances_runtime_revision(self):
        with self.assertRaisesRegex(WorkloadError, 'NO_DEPLOYMENT'):
            self.service.request(self.actor, self.workload, 'start', str(uuid.uuid4()))
        self.service.request(self.actor, self.workload, 'deploy', str(uuid.uuid4()), 'stable')
        self.service.reconcile(self.workload)
        original = self.service.state(self.actor, self.workload)['revision']
        self.service.request(self.actor, self.workload, 'restart', str(uuid.uuid4()))
        self.service.reconcile(self.workload)
        self.assertIn(('ensure', self.actor.account_id, self.workload, 'stable', original + 1),
                      self.runtime.calls)
        self.service.request(self.actor, self.workload, 'stop', str(uuid.uuid4()))
        self.service.reconcile(self.workload)
        self.service.request(self.actor, self.workload, 'start', str(uuid.uuid4()))
        self.service.reconcile(self.workload)
        self.assertEqual(self.service.state(self.actor, self.workload)['observed'], 'running')

    def test_private_migration_adds_secret_refs_to_v1_database(self):
        path = Path(self.temp.name) / 'upgrade.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT)')
            db.execute("INSERT INTO schema_migrations VALUES('workloads.core.v1','fixture')")
            db.execute('''CREATE TABLE workloads (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                name TEXT NOT NULL, desired TEXT NOT NULL, observed TEXT NOT NULL,
                template TEXT, previous_template TEXT, revision INTEGER NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(project_id,name))''')
        WorkloadService(path, self.runtime, self.service.templates,
                        lambda *_: None, lambda _: True)
        with closing(sqlite3.connect(path)) as db:
            columns = [row[1] for row in db.execute('PRAGMA table_info(workloads)')]
            self.assertIn('secret_refs', columns)
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='workload_secret_ops'").fetchone())


if __name__ == '__main__':
    unittest.main()

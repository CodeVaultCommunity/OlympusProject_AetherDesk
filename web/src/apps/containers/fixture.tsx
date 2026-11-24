import { createRoot } from 'react-dom/client';
import { ContainersApp } from './ContainersApp';
import type { ContainersClient, WorkloadAction, WorkloadJob, WorkloadSummary } from './contracts';

const ownId = '00000000-0000-4000-8000-000000000001';
const otherId = '00000000-0000-4000-8000-000000000002';
let own: WorkloadSummary = { id: ownId, owner: 'self', project: 'Portal', name: 'api',
  desired: 'stopped', observed: 'stopped', template: 'web', health: 'parado',
  port: 8080, route: null, volume: '2 GiB · retenção 7 dias', updatedAt: '2026-11-24' };
const other: WorkloadSummary = { ...own, id: otherId, owner: 'other', name: 'api de outra conta' };
const jobs = new Map<string, WorkloadJob>();
const sleep = () => new Promise(resolve => setTimeout(resolve, 40));
const client: ContainersClient = {
  async listMine() { await sleep(); return [own]; },
  async listControllable() { await sleep(); return [other]; },
  async templates() { return ['web']; },
  async create() { await sleep(); },
  async build(_project, operationId) { await sleep();
    const job: WorkloadJob = { id: operationId, workloadId: ownId, action: 'build', status: 'pending' };
    jobs.set(job.id, job); return job; },
  async request(workloadId: string, action: WorkloadAction, operationId: string) {
    await sleep();
    if (jobs.has(operationId)) return jobs.get(operationId)!;
    const job: WorkloadJob = { id: operationId, workloadId, action, status: 'pending' };
    jobs.set(job.id, job); return job;
  },
  async job(id) {
    await sleep();
    const job = jobs.get(id)!;
    if (job.status !== 'pending') return job;
    const next: WorkloadJob = job.action === 'deploy'
      ? { ...job, status: 'failed', errorCode: 'HEALTH_FAILED' }
      : { ...job, status: 'completed' };
    jobs.set(id, next);
    if (job.workloadId === ownId) own = { ...own,
      observed: job.action === 'deploy' ? 'rolled_back' : job.action === 'stop' ? 'stopped'
        : job.action === 'remove' ? 'removed' : 'running',
      health: job.action === 'deploy' ? 'versão anterior saudável' : 'saudável' };
    return next;
  },
  async cancel(id) { const next: WorkloadJob = { ...jobs.get(id)!, status: 'cancelled' };
    jobs.set(id, next); return next; },
  async logs() { return 'Log privado da aplicação'; },
  async metrics() { return { cpu: '1%', memory: '5 MiB', network: '0 B', pids: '1' }; },
  async routeTicket() { throw new Error('Rota desativada na fixture'); },
  async configureSecrets() { await sleep(); },
};
const role = new URLSearchParams(location.search).get('role');
const admin = role === 'admin';
const permissions = admin ? ['workloads.control.other'] : [
  'workloads.read', 'workloads.create', 'workloads.build', 'workloads.deploy',
  'workloads.control', 'workloads.secrets'];
createRoot(document.getElementById('root')!).render(
  <ContainersApp client={client} permissions={role === 'forbidden' ? [] : permissions} />);

import { requestV2 } from '../../clients';
import type { ContainersClient } from './contracts';
const q = encodeURIComponent;
const body = (value: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(value) });
export const containersClient: ContainersClient = {
  listMine: () => requestV2('/workloads/mine'),
  listControllable: () => requestV2('/workloads/controllable'),
  templates: () => requestV2('/workloads/templates'),
  create: async (project, name) => { await requestV2('/workloads', body({ project, name })); },
  build: (project, operationId) => requestV2('/workloads/build', body({ project, operationId })),
  request: (workloadId, action, operationId, template) => requestV2(`/workloads/${q(workloadId)}/actions`,
    body({ action, operationId, template: template ?? null })),
  job: id => requestV2(`/jobs/${q(id)}`),
  cancel: id => requestV2(`/jobs/${q(id)}/cancel`, body({})),
  logs: id => requestV2(`/workloads/${q(id)}/logs`),
  metrics: id => requestV2(`/workloads/${q(id)}/metrics`),
  routeTicket: id => requestV2(`/workloads/${q(id)}/route-ticket`, body({})),
  configureSecrets: async (id, references, operationId) => {
    await requestV2(`/workloads/${q(id)}/secrets`, body({ references, operationId }));
  },
};

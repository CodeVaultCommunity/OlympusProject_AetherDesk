import { requestV2, terminalClient } from '../../clients';
import type { DeployTarget, IdeClient, IdeJob } from './contracts';
const q = encodeURIComponent;
const body = (value: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(value) });
type Workload = { id: string; name: string; project: string };
type BrokerJob = IdeJob & { errorCode?: string };
const job = (value: BrokerJob): IdeJob => ({ id: value.id, status: value.status,
  message: value.errorCode || value.message });
export const ideClient: IdeClient = {
  tree: () => requestV2('/workspace/tree'),
  read: path => requestV2(`/workspace/file?path=${q(path)}`),
  save: (path, content, revision) => requestV2('/workspace/file', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': revision },
    body: JSON.stringify({ path, content }),
  }),
  search: query => requestV2(`/workspace/search?q=${q(query)}`),
  gitStatus: () => requestV2('/workspace/git/status'),
  gitDiff: path => requestV2(`/workspace/git/diff?path=${q(path)}`),
  gitStage: async paths => { await requestV2('/workspace/git/stage', body({ paths })); },
  gitCommit: async (message, operationId) => {
    const result = await requestV2<{ hash: string }>('/workspace/git/commit', body({ message, operationId }));
    return { id: operationId, status: 'completed', message: result.hash };
  },
  gitPush: operationId => requestV2('/workspace/git/push', body({ operationId })),
  deployTargets: async () => {
    const [workloads, templates] = await Promise.all([
      requestV2<Workload[]>('/workloads/mine'), requestV2<string[]>('/workloads/templates'),
    ]);
    return workloads.flatMap(workload => templates.map(template => ({
      workloadId: workload.id, name: workload.name, project: workload.project, template,
    } as DeployTarget)));
  },
  deploy: async (target, operationId) => job(await requestV2<BrokerJob>(
    `/workloads/${q(target.workloadId)}/actions`, body({ action: 'deploy', operationId, template: target.template }))),
  job: async id => job(await requestV2<BrokerJob>(`/jobs/${q(id)}`)),
  cancelJob: async id => job(await requestV2<BrokerJob>(`/jobs/${q(id)}/cancel`, body({}))),
  terminal: terminalClient,
};

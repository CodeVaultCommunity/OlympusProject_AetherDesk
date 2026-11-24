export type WorkloadStatus = 'absent' | 'running' | 'stopped' | 'failed' | 'rolled_back' | 'removed' | 'error';
export type WorkloadSummary = {
  id: string; owner: 'self' | 'other'; project: string; name: string;
  desired: 'running' | 'stopped' | 'removed'; observed: WorkloadStatus;
  template: string | null; health: string; port: number | null;
  route: string | null; volume: string; updatedAt: string;
};
export type WorkloadJob = {
  id: string; workloadId: string; action: string;
  status: 'pending' | 'completed' | 'failed' | 'superseded' | 'cancelled';
  errorCode?: string;
};
export type WorkloadMetrics = { cpu: string; memory: string; network: string; pids: string };
export type WorkloadAction = 'deploy' | 'start' | 'stop' | 'restart' | 'remove';

export interface ContainersClient {
  listMine(): Promise<WorkloadSummary[]>;
  listControllable(): Promise<WorkloadSummary[]>;
  templates(): Promise<string[]>;
  create(project: string, name: string): Promise<void>;
  build(project: string, operationId: string): Promise<WorkloadJob>;
  request(workloadId: string, action: WorkloadAction, operationId: string,
    template?: string): Promise<WorkloadJob>;
  job(jobId: string): Promise<WorkloadJob>;
  cancel(jobId: string): Promise<WorkloadJob>;
  logs(workloadId: string): Promise<string>;
  metrics(workloadId: string): Promise<WorkloadMetrics>;
  routeTicket(workloadId: string): Promise<{ host: string; ticket: string }>;
  configureSecrets(workloadId: string, references: Record<string, string>,
    operationId: string): Promise<void>;
}

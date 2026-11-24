export type FileNode = { path: string; name: string; kind: 'file' | 'directory'; children?: FileNode[] };
export type FileSnapshot = { path: string; content: string; revision: string; language: string; readonly?: boolean };
export type GitEntry = { path: string; status: string; staged: boolean };
export type GitSnapshot = { branch: string; entries: GitEntry[]; ahead: number; behind: number };
export type IdeJob = { id: string; status: 'pending' | 'completed' | 'failed' | 'cancelled' | 'superseded'; message?: string };
export type DeployTarget = { workloadId: string; name: string; project: string; template: string };
export type TerminalSession = { id: string; state: string };
export interface IdeClient {
  tree(): Promise<FileNode[]>;
  read(path: string): Promise<FileSnapshot>;
  save(path: string, content: string, revision: string): Promise<FileSnapshot>;
  search(query: string): Promise<{ path: string; line: number; snippet: string }[]>;
  gitStatus(): Promise<GitSnapshot>;
  gitDiff(path: string): Promise<string>;
  gitStage(paths: string[]): Promise<void>;
  gitCommit(message: string, operationId: string): Promise<IdeJob>;
  gitPush(operationId: string): Promise<IdeJob>;
  deployTargets(): Promise<DeployTarget[]>;
  deploy(target: DeployTarget, operationId: string): Promise<IdeJob>;
  job(id: string): Promise<IdeJob>;
  cancelJob(id: string): Promise<IdeJob>;
  terminal: {
    list(): Promise<TerminalSession[]>;
    create(columns: number, rows: number): Promise<string>;
    close(id: string): Promise<void>;
    connect(id: string): WebSocket;
  };
}

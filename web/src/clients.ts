import type { FileClient } from './apps/files';
import type { TerminalClient } from './apps/terminal';
import type { MonitorClient } from './apps/monitor';
import type { Account, AdministrationClient, BackupPolicy } from './apps/administration';
import type { DesktopState } from './window-state';

function csrf() { return document.cookie.split('; ').find(part => part.startsWith('aether_csrf='))?.split('=')[1] || ''; }
export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}
export async function requestEnvelope<T>(path: string, init: RequestInit = {}): Promise<{ data: T; revision?: number }> {
  const response = await fetch(`/api/v1${path}`, { credentials: 'include', ...init,
    headers: { 'X-CSRF-Token': csrf(), ...init.headers } });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(response.status, error?.error?.code || error?.detail || `HTTP_${response.status}`);
  }
  return await response.json() as { data: T; revision?: number };
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await requestEnvelope<T>(path, init)).data;
}
export async function requestV2<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v2${path}`, { credentials: 'include', ...init,
    headers: { 'X-CSRF-Token': csrf(), 'X-AetherDesk-API-Version': '2', ...init.headers } });
  const version = response.headers.get('X-AetherDesk-API-Version');
  if (version && version !== '2') throw new ApiError(426, 'API_VERSION_UNSUPPORTED');
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(response.status, error?.error?.code || error?.detail || `HTTP_${response.status}`);
  }
  return (await response.json() as { data: T }).data;
}
function json(method: string, body?: unknown): RequestInit { return { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }; }
const query = (value: string) => encodeURIComponent(value);

export const desktopClient = {
  load: () => requestEnvelope<DesktopState>('/desktop/state'),
  save: (state: DesktopState, revision: number) => requestEnvelope<DesktopState>('/desktop/state', {
    ...json('PUT', state), headers: { 'Content-Type': 'application/json', 'If-Match': `"${revision}"` },
  }),
};

export const filesClient: FileClient = {
  list: path => request(`/files/list?path=${query(path)}`),
  read: path => request(`/files/content?path=${query(path)}`),
  write: async (path, content, revision) => (await request<{ revision: string }>(`/files/content`, {
    ...json('PUT', { path, content }), headers: { 'Content-Type': 'application/json', ...(revision ? { 'If-Match': revision } : {}) },
  })).revision,
  mkdir: async path => { await request('/files/mkdir', json('POST', { path })); },
  move: async (path, destination) => { await request('/files/move', json('POST', { path, destination })); },
  copy: async (path, destination) => { await request('/files/copy', json('POST', { path, destination })); },
  delete: async path => { await request('/files/entry', json('DELETE', { path })); },
  download: async path => {
    const response = await fetch(`/api/v1/files/download?path=${query(path)}`, { credentials: 'include' });
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    return response.blob();
  },
  upload: async (path, file, replace = false) => {
    const response = await fetch(`/api/v1/files/upload?path=${query(path)}&replace=${replace ? 'true' : 'false'}`, {
      method: 'PUT', credentials: 'include', headers: { 'X-CSRF-Token': csrf() }, body: file,
    });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `HTTP_${response.status}`);
  },
};

export const terminalClient: TerminalClient = {
  list: () => request('/terminals'),
  create: async (columns, rows) => (await request<{ id: string }>('/terminals', json('POST', { columns, rows }))).id,
  close: async id => { await request(`/terminals/${query(id)}`, { method: 'DELETE' }); },
  connect: id => new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/ws/terminals/${query(id)}`),
};

export const monitorClient: MonitorClient = {
  self: () => request('/metrics/self'),
  server: () => request('/metrics/server'),
  accounts: () => request('/metrics/accounts'),
};

export const administrationClient: AdministrationClient = {
  accounts: () => request('/admin/accounts'),
  create: async (username, password, role) => { await request('/admin/accounts', json('POST', { username, password, role })); },
  update: async (account: Account, change) => { await request(`/admin/accounts/${query(account.id)}`, json('PATCH', { revision: account.revision, ...change })); },
  permissions: id => request(`/admin/accounts/${query(id)}/permissions`),
  setPermission: async (id, capability, allowed) => { await request(`/admin/accounts/${query(id)}/permissions`, json('PUT', { capability, allowed })); },
  sessions: id => request(`/admin/accounts/${query(id)}/sessions`),
  revoke: async id => { await request(`/admin/sessions/${query(id)}/revoke`, json('POST')); },
  stop: async id => { await request(`/admin/accounts/${query(id)}/sessions/stop`, json('POST')); },
  environment: id => request(`/admin/accounts/${query(id)}/environment`),
  retry: async id => { await request(`/admin/accounts/${query(id)}/environment/retry`, json('POST')); },
  audit: () => request('/admin/audit'),
  backup: () => request('/admin/backup'),
  configureBackup: async (policy: BackupPolicy) => { await request('/admin/backup', json('PUT', policy)); },
};

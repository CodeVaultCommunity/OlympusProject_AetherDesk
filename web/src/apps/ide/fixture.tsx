import { createRoot } from 'react-dom/client';
import { IdeApp } from './IdeApp';
import type { IdeClient } from './contracts';

let content = 'export const ready = true;';
let revision = 'r1';
let conflict = false;
const jobs = new Map<string, { id: string; status: 'pending' | 'failed' | 'completed'; message?: string }>();
const client: IdeClient = {
  async tree() { return [{ path: 'src', name: 'src', kind: 'directory', children: [
    { path: 'src/main.ts', name: 'main.ts', kind: 'file' }] }]; },
  async read(path) { return { path, content, revision, language: 'typescript' }; },
  async save(path, next, expected) {
    if (conflict || expected !== revision) throw new Error('revision conflict');
    content = next; revision = 'r2'; return { path, content, revision, language: 'typescript' };
  },
  async search(query) { return [{ path: 'src/main.ts', line: 1, snippet: query }]; },
  async gitStatus() { return { branch: 'main', entries: [
    { path: 'src/main.ts', status: 'M', staged: false }], ahead: 1, behind: 0 }; },
  async gitDiff() { return '-export const ready = false;\n+export const ready = true;'; },
  async gitStage() {},
  async gitCommit(_message, id) { return { id, status: 'completed' }; },
  async gitPush(id) { return { id, status: 'completed' }; },
  async deployTargets() { return [{ workloadId: 'w1', name: 'portal', project: 'portal', template: 'web' }]; },
  async deploy(_target, id) { const job = { id, status: 'pending' as const }; jobs.set(id, job); return job; },
  async job(id) { const job = { ...jobs.get(id)!, status: 'failed' as const, message: 'Saúde falhou; release anterior restaurada' };
    jobs.set(id, job); return job; },
  async cancelJob(id) { return { id, status: 'failed', message: 'Cancelado' }; },
  terminal: { async list() { return []; }, async create() { return 't1'; }, async close() {},
    connect() { throw new Error('fixture does not open a real socket'); } },
};
function FakeEditor({ content: value, onChange }: { content: string; onChange: (value: string) => void }) {
  return <textarea aria-label="Editor" value={value} onChange={event => onChange(event.target.value)}
    style={{ width: '100%', height: '100%', boxSizing: 'border-box', background: '#0b1423', color: '#fff' }} />;
}
function FakeTerminal() { return <div style={{ padding: 8 }}>Terminal conectado · fixture isolada</div>; }
if (new URLSearchParams(location.search).has('conflict')) conflict = true;
createRoot(document.getElementById('root')!).render(<IdeApp client={client} workspace="demo" accountScope="fixture-owner"
  project="portal" permissions={['git.read', 'git.write', 'git.remote', 'workloads.deploy']}
  EditorComponent={FakeEditor} TerminalComponent={FakeTerminal} />);

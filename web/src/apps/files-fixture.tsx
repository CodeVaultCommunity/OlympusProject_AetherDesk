import React from 'react';
import { createRoot } from 'react-dom/client';
import { FilesApp, type FileClient, type FileEntry } from './files';
import './files.css';

const files = new Map<string, { content: string; revision: number; directory: boolean }>([
  ['/persist', { content: '', revision: 1, directory: true }],
  ['/persist/README.md', { content: '# Meu espaço\n\nArquivos pessoais ficam aqui.\n', revision: 1, directory: false }],
  ['/persist/exemplo.py', { content: 'print("Olá, AetherDesk!")\n', revision: 1, directory: false }],
]);
const client: FileClient = {
  async list(path) {
    return [...files.entries()].filter(([name]) => name !== path && name.startsWith(path === '/' ? '/' : `${path}/`) && !name.slice(path === '/' ? 1 : path.length + 1).includes('/'))
      .map(([name, file]): FileEntry => ({ name: name.split('/').pop()!, kind: file.directory ? 'directory' : 'file', size: file.content.length, mtime_ns: file.revision }));
  },
  async read(path) { const file = files.get(path); if (!file || file.directory) throw Error('NOT_FOUND'); return { content: file.content, revision: String(file.revision) }; },
  async write(path, content, revision) { const file = files.get(path); if (file && revision !== String(file.revision)) throw Error('STALE_REVISION'); const next = (file?.revision || 0) + 1; files.set(path, { content, revision: next, directory: false }); return String(next); },
  async mkdir(path) { if (files.has(path)) throw Error('CONFLICT'); files.set(path, { content: '', revision: 1, directory: true }); },
  async move(source, destination) { const file = files.get(source); if (!file || files.has(destination)) throw Error('CONFLICT'); files.set(destination, file); files.delete(source); },
  async copy(source, destination) { const file = files.get(source); if (!file || files.has(destination)) throw Error('CONFLICT'); files.set(destination, { ...file }); },
  async delete(path) { files.delete(path); for (const name of [...files.keys()]) if (name.startsWith(`${path}/`)) files.delete(name); },
  async download(path) { return new Blob([files.get(path)?.content || '']); },
  async upload(path, file) { files.set(path, { content: await file.text(), revision: 1, directory: false }); },
};

function Fixture() {
  const mode = new URLSearchParams(location.search).get('mode') === 'editor' ? 'editor' : 'explorer';
  return <div className="file-fixture"><FilesApp mode={mode} client={client} /></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Fixture /></React.StrictMode>);

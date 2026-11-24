import assert from 'node:assert/strict';
import { after, afterEach, before, test } from 'node:test';
import React from 'react';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/', pretendToBeVisual: true,
});
for (const name of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'localStorage'])
  globalThis[name] = dom.window[name];
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
let vite, IdeApp;
const file = { path: 'src/main.ts', content: 'const answer = 1;', revision: 'r1', language: 'typescript' };
function fixture() {
  const calls = [];
  let conflict = false;
  const client = {
    tree: async () => [{ path: 'src', name: 'src', kind: 'directory', children: [
      { path: file.path, name: 'main.ts', kind: 'file' }] }],
    read: async path => ({ ...file, path }),
    save: async (path, content, revision) => { calls.push({ type: 'save', path, content, revision });
      if (conflict) throw new Error('revision conflict');
      return { ...file, path, content, revision: 'r2' }; },
    search: async query => [{ path: file.path, line: 1, snippet: query }],
    gitStatus: async () => ({ branch: 'main', entries: [{ path: file.path, status: 'M', staged: false }], ahead: 1, behind: 0 }),
    gitDiff: async () => '-old\n+new', gitStage: async paths => { calls.push({ type: 'stage', paths }); },
    gitCommit: async (message, key) => { calls.push({ type: 'commit', message, key });
      return { id: key, status: 'completed' }; },
    gitPush: async key => { calls.push({ type: 'push', key }); return { id: key, status: 'completed' }; },
    deployTargets: async () => [{ workloadId: 'w1', name: 'portal', project: 'portal', template: 'web' }],
    deploy: async (target, key) => { calls.push({ type: 'deploy', target, key });
      return { id: key, status: 'pending' }; },
    job: async id => ({ id, status: 'completed' }), cancelJob: async id => ({ id, status: 'cancelled' }),
    terminal: { list: async () => [], create: async () => 't1', close: async () => {}, connect: () => { throw new Error('unused'); } },
  };
  return { client, calls, setConflict(value) { conflict = value; } };
}
function FakeEditor({ content, onChange }) {
  return React.createElement('textarea', { 'aria-label': 'Editor', value: content,
    onChange: event => onChange(event.target.value) });
}
function FakeTerminal() { return React.createElement('div', null, 'Terminal conectado'); }
function mount(client, accountScope = 'fixture-owner') { return render(React.createElement(IdeApp, { client, workspace: 'demo', project: 'portal', accountScope,
  permissions: ['git.read', 'git.write', 'git.remote', 'workloads.deploy'],
  EditorComponent: FakeEditor, TerminalComponent: FakeTerminal })); }
before(async () => { vite = await createServer({ server: { middlewareMode: true, hmr: false },
  appType: 'custom', logLevel: 'error', optimizeDeps: { noDiscovery: true } });
  ({ IdeApp } = await vite.ssrLoadModule('/src/apps/ide/IdeApp.tsx')); });
afterEach(() => { cleanup(); localStorage.clear(); });
after(async () => { await vite?.close(); dom.window.close(); });

test('árvore abre arquivo, salva com revisão e deploy exige salvar antes', async () => {
  const { client, calls } = fixture();
  const view = mount(client);
  fireEvent.click(await screen.findByRole('button', { name: 'main.ts' }));
  fireEvent.change(await screen.findByRole('textbox', { name: 'Editor' }),
    { target: { value: 'const answer = 2;' } });
  assert.equal(screen.getByRole('button', { name: 'Deploy' }).disabled, true);
  assert.equal(localStorage.getItem('aetherdesk.ide.recovery.v1:fixture-owner:demo:src/main.ts'), 'const answer = 2;');
  fireEvent.click(screen.getByRole('button', { name: 'Salvar' }));
  await waitFor(() => assert.equal(calls.filter(call => call.type === 'save').length, 1));
  assert.equal(calls.find(call => call.type === 'save').revision, 'r1');
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Deploy' }).disabled, false));
  fireEvent.click(screen.getByRole('button', { name: 'Deploy' }));
  assert.match(screen.getByRole('alertdialog').textContent, /reinicia o workload/);
  fireEvent.click(screen.getByRole('alertdialog').querySelector('button:last-child'));
  await waitFor(() => assert.equal(calls.filter(call => call.type === 'deploy').length, 1));
  view.unmount();
});

test('conflito mantém rascunho e permite comparar versão do servidor', async () => {
  const { client, setConflict } = fixture(); setConflict(true);
  const view = mount(client);
  fireEvent.click(await screen.findByRole('button', { name: 'main.ts' }));
  fireEvent.change(await screen.findByRole('textbox', { name: 'Editor' }),
    { target: { value: 'edição local' } });
  fireEvent.click(screen.getByRole('button', { name: 'Salvar' }));
  await screen.findByRole('alert');
  assert.equal(screen.getByRole('textbox', { name: 'Editor' }).value, 'edição local');
  fireEvent.click(screen.getByRole('button', { name: 'Comparar com servidor' }));
  await waitFor(() => assert.ok(screen.getByRole('dialog', { name: 'Diff src/main.ts' }).textContent.includes('edição local')));
  view.unmount();
});

test('fechar aba dirty pede confirmação e layout persiste', async () => {
  const { client } = fixture();
  const view = mount(client);
  fireEvent.click(await screen.findByRole('button', { name: 'main.ts' }));
  fireEvent.change(await screen.findByRole('textbox', { name: 'Editor' }),
    { target: { value: 'rascunho' } });
  fireEvent.click(screen.getByRole('button', { name: 'Terminal à direita' }));
  assert.equal(JSON.parse(localStorage.getItem('aetherdesk.ide.layout.v1:fixture-owner')).dock, 'right');
  fireEvent.click(screen.getByRole('button', { name: 'Fechar src/main.ts' }));
  assert.match(screen.getByRole('alertdialog').textContent, /Alterações não salvas/);
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
  assert.ok(screen.getByRole('textbox', { name: 'Editor' }));
  view.unmount();
});

test('rascunho e layout de outra conta não atravessam a sessão local', async () => {
  localStorage.setItem('aetherdesk.ide.recovery.v1:owner-a:demo:src/main.ts', 'conteúdo privado');
  localStorage.setItem('aetherdesk.ide.layout.v1:owner-a', JSON.stringify({ dock: 'right', splits: 2 }));
  const { client } = fixture();
  const view = mount(client, 'owner-b');
  fireEvent.click(await screen.findByRole('button', { name: 'main.ts' }));
  assert.equal((await screen.findByRole('textbox', { name: 'Editor' })).value, file.content);
  assert.ok(screen.getByRole('button', { name: 'Terminal à direita' }));
  view.unmount();
});

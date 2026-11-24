import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { after, afterEach, before, test } from 'node:test';
import React from 'react';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/', pretendToBeVisual: true,
});
for (const name of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'MutationObserver'])
  globalThis[name] = dom.window[name];
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
let vite, AiApp;
const proposal = { id: 'p1', name: 'external.delete', version: '2', source: 'external',
  serverVersion: '4', risk: 'destructive', target: 'workspace/demo',
  consequence: 'Remove o arquivo selecionado', arguments: { path: 'src/main.ts' },
  schemaDigest: 'abc' };
const hash = createHash('sha256').update('{"path":"src/main.ts"}').digest('hex');
const perms = ['ai.chat', 'ai.tools'];
function fixture() {
  const calls = [];
  let badTicket = false;
  let revoked = false;
  const client = {
    providers: async () => [{ name: 'fake', models: ['fast'], external: true, enabled: true,
      dataSent: 'mensagem e histórico', retentionDays: 30 }],
    saveProvider: async (name, model, secret) => { calls.push({ type: 'provider', name, model, secret }); },
    conversations: async () => [{ id: 'c1', provider: 'fake', title: 'Teste', updatedAt: '2026-11-24' }],
    create: async () => ({ id: 'c2', provider: 'fake', title: 'Nova', updatedAt: '2026-11-24' }),
    messages: async () => [],
    stream: async (_id, prompt, accepted, signal, onChunk) => { calls.push({ type: 'stream', prompt, accepted });
      onChunk('parcial'); await new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true });
        setTimeout(resolve, 300);
      }); },
    export: async () => ({ messages: [] }), delete: async () => {},
    usage: async () => ({ usedChars: 10, limitChars: 1000, cost: '0', limitCost: '1' }),
    proposals: async () => [proposal],
    requestApproval: async item => { calls.push({ type: 'request', item }); return {
      id: 'ticket', tool: item.name, version: item.version,
      argumentsHash: badTicket ? 'wrong' : hash, expiresAt: Date.now() / 1000 + 60,
      nonce: 'n1' }; },
    approve: async ticket => { calls.push({ type: 'approve', ticket });
      if (revoked) throw new Error('SESSION_REVOKED'); },
    invoke: async (item, ticket) => { calls.push({ type: 'invoke', item, ticket }); },
  };
  return { client, calls, setBadTicket(value) { badTicket = value; },
    setRevoked(value) { revoked = value; } };
}
before(async () => { vite = await createServer({ server: { middlewareMode: true, hmr: false },
  appType: 'custom', logLevel: 'error', optimizeDeps: { noDiscovery: true } });
  ({ AiApp } = await vite.ssrLoadModule('/src/apps/ai/AiApp.tsx')); });
afterEach(() => cleanup());
after(async () => { await vite?.close(); dom.window.close(); });

test('chat externo exige divulgação, transmite e cancela', async () => {
  const { client, calls } = fixture();
  const view = render(React.createElement(AiApp, { client, permissions: perms }));
  fireEvent.click(await screen.findByRole('button', { name: 'Teste' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Mensagem' }), { target: { value: 'olá' } });
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Enviar' }).disabled, false));
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));
  assert.equal(calls.some(call => call.type === 'stream'), false);
  await waitFor(() => assert.match(screen.getByRole('status').textContent, /aceite o envio/));
  fireEvent.click(screen.getByRole('checkbox', { name: /Aceito enviar/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));
  await waitFor(() => assert.equal(calls.filter(call => call.type === 'stream').length, 1));
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar resposta' }));
  await waitFor(() => assert.match(screen.getByRole('status').textContent, /cancelada/));
  view.unmount();
});

test('ticket divergente bloqueia aprovação e exibe origem/argumentos', async () => {
  const { client, calls, setBadTicket } = fixture(); setBadTicket(true);
  const view = render(React.createElement(AiApp, { client, permissions: perms }));
  fireEvent.click(screen.getByRole('button', { name: 'Ferramentas' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Revisar ação' }));
  const dialog = screen.getByRole('alertdialog');
  assert.match(dialog.textContent, /Servidor externo external · versão 4/);
  assert.match(dialog.textContent, /Destruição/);
  assert.match(dialog.textContent, /src\/main.ts/);
  fireEvent.click(screen.getByRole('button', { name: 'Solicitar ticket' }));
  await waitFor(() => assert.match(screen.getByRole('status').textContent, /mudaram/));
  assert.equal(screen.queryByRole('button', { name: 'Aprovar esta ação' }), null);
  assert.equal(calls.some(call => call.type === 'approve' || call.type === 'invoke'), false);
  view.unmount();
});

test('sessão revogada não invoca tool e secret não reaparece', async () => {
  const { client, calls, setRevoked } = fixture(); setRevoked(true);
  const view = render(React.createElement(AiApp, { client, permissions: perms }));
  fireEvent.click(screen.getByRole('button', { name: 'Configuração' }));
  await screen.findByRole('option', { name: 'fast' });
  fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'fast' } });
  fireEvent.change(screen.getByLabelText(/Secret do provedor/), { target: { value: 'top-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }));
  await waitFor(() => assert.equal(calls.some(call => call.type === 'provider'), true));
  assert.equal(screen.getByLabelText(/Secret do provedor/).value, '');
  assert.ok(!document.body.textContent.includes('top-secret'));
  fireEvent.click(screen.getByRole('button', { name: 'Ferramentas' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Revisar ação' }));
  fireEvent.click(screen.getByRole('button', { name: 'Solicitar ticket' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Aprovar esta ação' }));
  await waitFor(() => assert.match(screen.getByRole('status').textContent, /sessão foi revogada/));
  assert.equal(calls.some(call => call.type === 'invoke'), false);
  view.unmount();
});

test('sem capacidade não consulta provedor ou propostas', () => {
  const { client, calls } = fixture();
  client.providers = async () => { calls.push({ type: 'providers' }); return []; };
  const view = render(React.createElement(AiApp, { client, permissions: [] }));
  assert.ok(screen.getByRole('alert').textContent.includes('Sem permissão'));
  assert.deepEqual(calls, []);
  view.unmount();
});

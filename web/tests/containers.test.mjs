import assert from 'node:assert/strict';
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
const axe = (await import('axe-core')).default;
let vite, ContainersApp;

const mine = { id: '00000000-0000-4000-8000-000000000001', owner: 'self', project: 'Portal',
  name: 'api', desired: 'stopped', observed: 'stopped', template: 'web', health: 'parado',
  port: 8080, route: null, volume: '2 GiB', updatedAt: '2026-11-24' };
const other = { ...mine, id: '00000000-0000-4000-8000-000000000002', owner: 'other',
  name: 'serviço de outra conta' };
const permissions = ['workloads.read', 'workloads.create', 'workloads.build',
  'workloads.deploy', 'workloads.control', 'workloads.secrets'];

function fixture() {
  const calls = [];
  return { calls, client: {
    listMine: async () => [mine], listControllable: async () => [other],
    templates: async () => ['web'],
    create: async () => {},
    build: async (_project, operationId) => ({ id: operationId, workloadId: mine.id,
      action: 'build', status: 'pending' }),
    request: async (id, action, operationId) => { calls.push({ id, action, operationId });
      return { id: operationId, workloadId: id, action, status: 'pending' }; },
    job: async id => ({ id, workloadId: mine.id, action: 'start', status: 'completed' }),
    cancel: async id => ({ id, workloadId: mine.id, action: 'start', status: 'cancelled' }),
    logs: async id => { calls.push({ logs: id }); return 'private log'; },
    metrics: async id => { calls.push({ metrics: id }); return { cpu: '1%', memory: '5 MiB',
      network: '0 B', pids: '1' }; },
    configureSecrets: async (id, refs) => { calls.push({ secrets: id, refs }); },
    routeTicket: async () => { throw new Error('disabled'); },
  } };
}

before(async () => {
  vite = await createServer({ server: { middlewareMode: true, hmr: false },
    appType: 'custom', logLevel: 'error', optimizeDeps: { noDiscovery: true } });
  ({ ContainersApp } = await vite.ssrLoadModule('/src/apps/containers/ContainersApp.tsx'));
});
afterEach(() => cleanup());
after(async () => { await vite?.close(); dom.window.close(); });

test('owner confirma start com alvo e consequência, idempotency key e sem expor secret', async () => {
  const { client, calls } = fixture();
  const view = render(React.createElement(ContainersApp, { client, permissions }));
  await screen.findByRole('heading', { name: 'api' });
  assert.equal((await screen.findByText('private log')).textContent, 'private log');
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar' }));
  const dialog = screen.getByRole('alertdialog');
  assert.match(dialog.textContent, /Iniciar api/);
  assert.match(dialog.textContent, /último template aprovado/);
  fireEvent.click(dialog.querySelector('button:last-child'));
  await waitFor(() => assert.equal(calls.filter(call => call.action === 'start').length, 1));
  assert.match(calls.find(call => call.action === 'start').operationId,
    /^[0-9a-f]{8}-[0-9a-f-]{27}$/i);
  assert.equal(screen.queryByText('serviço de outra conta'), null);
  assert.equal(screen.queryByText('private-token'), null);
  const report = await axe.run(view.container, { runOnly: { type: 'tag',
    values: ['wcag2a', 'wcag2aa'] } });
  assert.deepEqual(report.violations.map(item => item.id), []);
  view.unmount();
});

test('admin control-only não carrega logs, métricas ou secret de outra conta', async () => {
  const { client, calls } = fixture();
  const view = render(React.createElement(ContainersApp,
    { client, permissions: ['workloads.control.other'] }));
  await screen.findByRole('heading', { name: 'serviço de outra conta' });
  assert.ok(screen.getByText(/não inclui acesso a logs/));
  assert.equal(screen.queryByText('private log'), null);
  assert.equal(screen.queryByRole('button', { name: 'Criar build aprovado' }), null);
  assert.equal(calls.some(call => call.logs || call.metrics), false);
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }));
  assert.match(screen.getByRole('alertdialog').textContent, /volume será eliminado/);
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
  view.unmount();
});

test('falha de listagem apresenta offline e impede mutação', async () => {
  const { client } = fixture();
  client.listMine = async () => { throw new Error('network'); };
  const view = render(React.createElement(ContainersApp, { client, permissions }));
  await waitFor(() => assert.ok(screen.getByRole('alert').textContent.includes('Offline')));
  assert.equal(screen.getByRole('button', { name: 'Criar build aprovado' }).disabled, true);
  view.unmount();
});

test('pedido incerto é consultado com a mesma chave de idempotência', async () => {
  const { client } = fixture();
  const seen = [];
  let first = true;
  client.request = async (id, action, operationId) => {
    seen.push(operationId);
    if (first) { first = false; throw new Error('response lost'); }
    return { id: operationId, workloadId: id, action, status: 'completed' };
  };
  const view = render(React.createElement(ContainersApp, { client, permissions }));
  await screen.findByRole('heading', { name: 'api' });
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar', exact: true }));
  fireEvent.click(screen.getByRole('alertdialog').querySelector('button:last-child'));
  fireEvent.click(await screen.findByRole('button', { name: 'Consultar pedido' }));
  await waitFor(() => assert.equal(seen.length, 2));
  assert.equal(seen[0], seen[1]);
  view.unmount();
});

test('sem capacidade não consulta dados privados nem mostra ações', async () => {
  const { client, calls } = fixture();
  client.listMine = async () => { throw new Error('should not be called'); };
  const view = render(React.createElement(ContainersApp, { client, permissions: [] }));
  assert.ok(screen.getByRole('alert').textContent.includes('Sem permissão'));
  assert.equal(screen.queryByRole('button'), null);
  assert.deepEqual(calls, []);
  view.unmount();
});

test('rota própria usa POST com ticket curto e não aparece ao admin', async () => {
  const { client } = fixture();
  const host = '000000000000.apps.local';
  client.listMine = async () => [{ ...mine, observed: 'running', route: host }];
  client.routeTicket = async id => {
    assert.equal(id, mine.id);
    return { host, ticket: 'fixture-one-use-ticket' };
  };
  let submitted;
  const original = dom.window.HTMLFormElement.prototype.submit;
  dom.window.HTMLFormElement.prototype.submit = function () {
    submitted = { method: this.method, action: this.action,
      ticket: this.querySelector('input[name=ticket]').value };
  };
  try {
    const view = render(React.createElement(ContainersApp,
      { client, permissions: [...permissions, 'workloads.route'] }));
    await screen.findByRole('button', { name: 'Abrir aplicação' });
    fireEvent.click(screen.getByRole('button', { name: 'Abrir aplicação' }));
    await waitFor(() => assert.ok(submitted));
    assert.deepEqual(submitted, { method: 'post',
      action: `http://${host}/__aetherdesk/open`, ticket: 'fixture-one-use-ticket' });
    view.unmount();
    client.listControllable = async () => [{ ...other, observed: 'running', route: host }];
    const admin = render(React.createElement(ContainersApp,
      { client, permissions: ['workloads.control.other', 'workloads.route'] }));
    await screen.findByRole('heading', { name: 'serviço de outra conta' });
    assert.equal(screen.queryByRole('button', { name: 'Abrir aplicação' }), null);
    admin.unmount();
  } finally {
    dom.window.HTMLFormElement.prototype.submit = original;
  }
});

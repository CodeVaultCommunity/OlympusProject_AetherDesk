import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import React from 'react';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/?fixture=1', pretendToBeVisual: true,
});
for (const name of ['window', 'document', 'HTMLElement', 'Element',
  'Node', 'MutationObserver', 'location', 'localStorage', 'sessionStorage']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
const axe = (await import('axe-core')).default;
let vite;
let components;
let shell;

before(async () => {
  vite = await createServer({
    server: { middlewareMode: true, hmr: false }, appType: 'custom', logLevel: 'error',
    optimizeDeps: { noDiscovery: true },
  });
  components = await vite.ssrLoadModule('/src/apps/administration.tsx');
  shell = await vite.ssrLoadModule('/src/shell.tsx');
});

test('desktop abre configurações e persiste a preferência do usuário', async () => {
  localStorage.removeItem('aetherdesk-fixture');
  const view = render(React.createElement(shell.App));
  fireEvent.click(await screen.findByRole('button', { name: /Configurações/ }));
  assert.ok(screen.getByRole('button', { name: 'Fechar' }));
  fireEvent.change(screen.getByLabelText('Tema'), { target: { value: 'light' } });
  await waitFor(() => assert.equal(JSON.parse(localStorage.getItem('aetherdesk-fixture')).theme, 'light'));
  fireEvent.click(screen.getByRole('button', { name: 'Fechar' }));
  assert.equal(screen.queryByLabelText('Tema'), null);
  view.unmount();
  localStorage.removeItem('aetherdesk-fixture');
});
after(async () => { cleanup(); await vite?.close(); dom.window.close(); });

test('configurações permitem mudar tema e mantêm rótulo acessível', async () => {
  const changes = [];
  const view = render(React.createElement(components.SettingsApp,
    { theme: 'dark', onTheme: value => changes.push(value) }));
  fireEvent.change(screen.getByLabelText('Tema'), { target: { value: 'light' } });
  assert.deepEqual(changes, ['light']);
  const report = await axe.run(view.container, { runOnly: { type: 'rule', values: ['label', 'button-name'] } });
  assert.deepEqual(report.violations.map(item => item.id), []);
  view.unmount();
});

test('painel de backup não cria metas ou retenção implícitas', async () => {
  let saved;
  const policy = { enabled: false, frequency_hours: 24, destination: '',
    retention_mode: 'replace', retention_days: null, rpo_hours: null, rto_hours: null };
  const client = {
    accounts: async () => [], backup: async () => policy, audit: async () => [],
    configureBackup: async value => { saved = value; },
  };
  const view = render(React.createElement(components.AdministrationApp, { client }));
  const rpo = await screen.findByLabelText('RPO desejado (horas, opcional)');
  assert.equal(rpo.value, '');
  assert.equal(screen.getByLabelText('RTO desejado (horas, opcional)').value, '');
  fireEvent.change(screen.getByLabelText('Retenção'), { target: { value: 'days' } });
  assert.equal(screen.getByLabelText('Dias').value, '');
  fireEvent.change(rpo, { target: { value: '24' } });
  fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }));
  await waitFor(() => assert.ok(saved));
  assert.equal(saved.rpo_hours, 24);
  assert.equal(saved.rto_hours, null);
  assert.equal(saved.retention_days, null);
  const report = await axe.run(view.container, { runOnly: { type: 'rule', values: ['label', 'button-name'] } });
  assert.deepEqual(report.violations.map(item => item.id), []);
  view.unmount();
});

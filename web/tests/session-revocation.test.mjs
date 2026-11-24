import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import React from 'react';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/', pretendToBeVisual: true,
});
for (const name of ['window', 'document', 'HTMLElement', 'Element',
  'Node', 'MutationObserver', 'location', 'localStorage', 'sessionStorage']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
let vite;
let shell;

before(async () => {
  vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom',
    logLevel: 'error', optimizeDeps: { noDiscovery: true } });
  shell = await vite.ssrLoadModule('/src/shell.tsx');
});
after(async () => { cleanup(); await vite?.close(); dom.window.close(); });

test('revogação de capacidade remove app e janela de administração', async () => {
  let session = { username: 'admin', role: 'admin', account_id: 'owner',
    permissions: ['accounts.view', 'metrics.server'], permissions_version: 1 };
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    if (url.endsWith('/me')) return Response.json({ data: session });
    if (url.endsWith('/desktop/state')) {
      return Response.json({ data: { schemaVersion: 2, windows: [], activeId: null, theme: 'dark' }, revision: init.method === 'PUT' ? 1 : 0 });
    }
    if (url.endsWith('/admin/accounts') || url.endsWith('/admin/audit')) return Response.json({ data: [] });
    if (url.endsWith('/admin/backup')) return Response.json({ data: {
      enabled: false, frequency_hours: 24, destination: '', retention_mode: 'replace',
      retention_days: null, rpo_hours: null, rto_hours: null,
    } });
    return Response.json({ detail: 'NOT_FOUND' }, { status: 404 });
  };
  let view;
  try {
    view = render(React.createElement(shell.App));
    fireEvent.click(await screen.findByRole('button', { name: /Administração/ }));
    assert.ok(screen.getByRole('button', { name: 'Fechar' }));
    session = { ...session, permissions: [], permissions_version: 2 };
    fireEvent(document, new dom.window.Event('visibilitychange'));
    await waitFor(() => assert.equal(screen.queryByRole('button', { name: /Administração/ }), null));
    assert.equal(screen.queryByRole('button', { name: 'Fechar' }), null);
  } finally {
    view?.unmount();
    globalThis.fetch = oldFetch;
  }
});

test('sessão expirada retorna ao login ao atualizar permissões', async () => {
  let expired = false;
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async url => {
    if (url.endsWith('/me')) return expired
      ? Response.json({ detail: 'UNAUTHENTICATED' }, { status: 401 })
      : Response.json({ data: { username: 'member', role: 'member', account_id: 'owner2',
        permissions: ['preferences.read'], permissions_version: 1 } });
    if (url.endsWith('/desktop/state')) return Response.json({ data: {
      schemaVersion: 2, windows: [], activeId: null, theme: 'dark',
    }, revision: 0 });
    return Response.json({ detail: 'NOT_FOUND' }, { status: 404 });
  };
  let view;
  try {
    view = render(React.createElement(shell.App));
    await screen.findByRole('button', { name: /Configurações/ });
    expired = true;
    fireEvent(document, new dom.window.Event('visibilitychange'));
    await screen.findByRole('button', { name: /Entrar/ }, { timeout: 5000 });
    assert.equal(screen.queryByRole('button', { name: /Configurações/ }), null);
  } finally {
    view?.unmount();
    globalThis.fetch = oldFetch;
  }
});

test('rascunho de revisão antiga exige descarte antes de recuperar servidor', async () => {
  const accountId = 'owner3';
  const id = '00000000-0000-4000-8000-000000000003';
  sessionStorage.setItem('aetherdesk-desktop-tab-id', id);
  const draftKey = `aetherdesk-desktop-draft:${accountId}:${id}`;
  localStorage.setItem(draftKey, JSON.stringify({ revision: 0, state: {
    schemaVersion: 2, windows: [], activeId: null, theme: 'light',
  } }));
  const oldFetch = globalThis.fetch;
  const oldConfirm = window.confirm;
  let desktopLoads = 0;
  globalThis.fetch = async url => {
    if (url.endsWith('/me')) return Response.json({ data: { username: 'member', role: 'member',
      account_id: accountId, permissions: ['preferences.read'], permissions_version: 1 } });
    if (url.endsWith('/desktop/state')) {
      desktopLoads++;
      return Response.json({ data: { schemaVersion: 2, windows: [], activeId: null,
        theme: 'dark' }, revision: 1 });
    }
    return Response.json({ detail: 'NOT_FOUND' }, { status: 404 });
  };
  window.confirm = () => true;
  let view;
  try {
    view = render(React.createElement(shell.App));
    await screen.findByRole('button', { name: 'Recarregar estado' });
    assert.match(screen.getByRole('status').textContent, /Conflito/);
    assert.ok(view.container.querySelector('.desktop.light'));
    fireEvent.click(screen.getByRole('button', { name: 'Recarregar estado' }));
    await waitFor(() => assert.match(screen.getByRole('status').textContent, /Salvo/));
    assert.ok(view.container.querySelector('.desktop.dark'));
    assert.equal(localStorage.getItem(draftKey), null);
    assert.equal(desktopLoads, 2);
  } finally {
    view?.unmount();
    globalThis.fetch = oldFetch;
    window.confirm = oldConfirm;
    localStorage.removeItem(draftKey);
    sessionStorage.removeItem('aetherdesk-desktop-tab-id');
  }
});

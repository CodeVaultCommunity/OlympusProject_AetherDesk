import assert from 'node:assert/strict';
import test from 'node:test';
import { emptyDesktop, fitWindow, focusWindow, normalizeDesktop, patchWindow, recoverDesktopDraft } from '../src/window-state.ts';

const viewport = { width: 900, height: 600 };
const terminal = { id: 'one', kind: 'terminal', x: 50, y: 50, width: 700, height: 400,
  z: 1, minimized: false, maximized: false };

test('foco altera z uma vez e dez mil movimentos não elevam a janela', () => {
  let state = { ...emptyDesktop, windows: [terminal], activeId: null };
  state = focusWindow(state, terminal.id);
  const z = state.windows[0].z;
  for (let index = 0; index < 10_000; index++) {
    state = patchWindow(state, terminal.id,
      { x: index, y: index, width: 200 + index, height: 160 + index }, viewport);
  }
  assert.equal(state.windows[0].z, z);
  assert.ok(state.windows[0].x <= viewport.width - 120);
  assert.ok(state.windows[0].y <= viewport.height - 42);
  assert.ok(state.windows[0].x + state.windows[0].width <= viewport.width);
  assert.ok(state.windows[0].y + state.windows[0].height <= viewport.height);
});

test('estado legado é normalizado e a barra de título permanece alcançável', () => {
  const state = normalizeDesktop({ windows: [{ ...terminal, id: undefined, x: 9_999, y: 9_999 }],
    activeId: 'missing', theme: 'light' }, { width: 320, height: 400 });
  assert.equal(state.schemaVersion, 2);
  assert.equal(state.activeId, null);
  assert.equal(state.windows.length, 1);
  assert.ok(state.windows[0].x <= 200);
  assert.ok(state.windows[0].y <= 358);
  assert.equal(state.theme, 'light');
  assert.deepEqual(fitWindow(terminal, viewport).z, terminal.z);
});

test('janela cabe no viewport estreito produzido por zoom alto', () => {
  const narrow = { width: 195, height: 306 };
  const fitted = fitWindow(terminal, narrow);
  assert.equal(fitted.width, narrow.width);
  assert.equal(fitted.height, narrow.height);
  assert.equal(fitted.x, 0);
  assert.equal(fitted.y, 0);
});

test('rascunho local recupera estado sem sobrescrever uma revisão concorrente', () => {
  const server = normalizeDesktop({ ...emptyDesktop, windows: [terminal] }, viewport);
  const changed = { ...server, theme: 'light' };
  const draft = JSON.stringify({ revision: 4, state: changed });
  assert.deepEqual(recoverDesktopDraft(draft, server, 4, viewport),
    { state: changed, conflict: false, recovered: true });
  assert.deepEqual(recoverDesktopDraft(draft, server, 5, viewport),
    { state: changed, conflict: true, recovered: true });
  assert.deepEqual(recoverDesktopDraft('{invalid', server, 4, viewport),
    { state: server, conflict: false, recovered: false });
});

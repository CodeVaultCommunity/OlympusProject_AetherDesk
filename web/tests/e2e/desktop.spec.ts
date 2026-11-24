import { expect, test } from '@playwright/test';
import axe from 'axe-core';

const sizes = [
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 1024, height: 768 },
];
const zooms = [0.67, 1, 1.25, 1.5, 2];
const baseURL = process.env.AETHERDESK_E2E_BASE_URL || 'http://127.0.0.1:5173';

for (const size of sizes) for (const zoom of zooms) {
  test(`atalhos e janela alcançáveis em ${size.width}×${size.height} com viewport efetivo ${zoom}`, async ({ page }) => {
    await page.setViewportSize({
      width: Math.round(size.width / zoom), height: Math.round(size.height / zoom),
    });
    await page.goto('/?fixture=1');
    const launchers = page.locator('.launchers');
    await expect(launchers.getByRole('button')).toHaveCount(6);
    const visible = await launchers.evaluate(element => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    });
    for (const name of ['Explorador', 'Editor', 'Terminal', 'Monitor', 'Administração', 'Configurações']) {
      const launcher = launchers.getByRole('button', { name: new RegExp(name) });
      await launcher.focus();
      const bounds = await launcher.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(visible.left - 1);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(visible.right + 1);
      expect(bounds!.y).toBeGreaterThanOrEqual(visible.top - 1);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(visible.bottom + 1);
    }
    await launchers.getByRole('button', { name: /Configurações/ }).click();
    const close = page.getByRole('button', { name: 'Fechar' });
    await expect(close).toBeVisible();
    const closeBounds = await close.boundingBox();
    expect(closeBounds).not.toBeNull();
    expect(closeBounds!.x).toBeGreaterThanOrEqual(0);
    expect(closeBounds!.x + closeBounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
    await close.click();
    await expect(page.locator('.desk-window')).toHaveCount(0);
  });
}

for (const size of [{ width: 390, height: 844 }, { width: 768, height: 1024 }]) {
  test(`touch mantém atalhos e controles alcançáveis em ${size.width}×${size.height}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: size, hasTouch: true, isMobile: true });
    try {
      const page = await context.newPage();
      await page.goto(`${baseURL}/?fixture=1`);
      await page.locator('.launchers').getByRole('button', { name: /Configurações/ }).tap();
      const close = page.getByRole('button', { name: 'Fechar' });
      await expect(close).toBeVisible();
      await close.tap();
      await expect(page.locator('.desk-window')).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
}

test('tema persiste após recarregar o desktop', async ({ page }) => {
  await page.goto('/?fixture=1');
  await page.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
  await page.getByLabel('Tema').selectOption('light');
  await expect(page.locator('.desktop.light')).toBeVisible();
  const tabId = await page.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'));
  await page.reload();
  await expect(page.locator('.desktop.light')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'))).toBe(tabId);
});

test('relógio atualiza sem interação', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-23T15:00:00Z') });
  await page.goto('/?fixture=1');
  const clock = page.locator('.task-clock');
  const before = await clock.innerText();
  await page.clock.fastForward(60_000);
  await expect(clock).not.toHaveText(before);
});

test('arraste salva bounds válidos em uma revisão nova', async ({ page }) => {
  let revision = 0;
  let saved: { windows: Array<{ x: number; y: number; width: number; height: number }> } | null = null;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'drag-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: saved || { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'PUT') {
      expect(route.request().headers()['if-match']).toBe(`"${revision}"`);
      saved = route.request().postDataJSON();
      revision++;
      await route.fulfill({ json: { data: saved, revision } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  await page.goto('/');
  await page.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
  await expect.poll(() => revision).toBe(1);
  await expect(page.getByRole('status')).toContainText('Salvo');
  const titlebar = page.locator('.window-titlebar');
  const rect = await titlebar.boundingBox();
  expect(rect).not.toBeNull();
  await page.mouse.move(rect!.x + 60, rect!.y + 20);
  await page.mouse.down();
  await page.mouse.move(rect!.x + 110, rect!.y + 55, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => revision).toBe(2);
  await expect(page.getByRole('status')).toContainText('Salvo');
  expect(saved?.windows).toHaveLength(1);
  const bounds = saved!.windows[0];
  expect(bounds.x).toBeGreaterThan(0);
  expect(bounds.y).toBeGreaterThan(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(1280);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(720);
  await page.waitForTimeout(500);
  expect(revision).toBe(2);
});

test('rascunho local sobrevive ao fechamento abrupto da aba', async ({ context }) => {
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'crash-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.abort('failed');
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  const first = await context.newPage();
  await first.goto(`${baseURL}/`);
  await first.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
  await first.getByLabel('Tema').selectOption('light');
  await expect(first.locator('.desktop.light')).toBeVisible();
  await expect.poll(() => first.evaluate(() =>
    Object.keys(localStorage).some(key => key.startsWith('aetherdesk-desktop-draft:crash-fixture:')))).toBe(true);
  const original = await first.evaluate(() => {
    const key = Object.keys(localStorage).find(item => item.startsWith('aetherdesk-desktop-draft:crash-fixture:'))!;
    return { key, raw: localStorage.getItem(key) };
  });
  await first.close({ runBeforeUnload: false });
  const recovered = await context.newPage();
  await recovered.setViewportSize({ width: 240, height: 320 });
  await recovered.goto(`${baseURL}/`);
  await expect(recovered.getByRole('button', { name: 'Recuperar rascunho' })).toBeVisible();
  await recovered.getByRole('button', { name: 'Recuperar rascunho' }).click();
  await expect(recovered.locator('.desktop.light')).toBeVisible();
  await expect(recovered.getByRole('status')).toContainText(/Falha ao salvar|Salvando/);
  expect(await recovered.evaluate(key => localStorage.getItem(key), original.key)).toBe(original.raw);
  expect(await recovered.evaluate(() => Object.keys(localStorage).filter(
    key => key.startsWith('aetherdesk-desktop-draft:crash-fixture:') && !key.endsWith(':consumed')).length)).toBe(2);
});

test('duas abas mantêm rascunhos locais distintos', async ({ context }) => {
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'tabs-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.abort('failed');
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  const first = await context.newPage();
  await first.goto(`${baseURL}/`);
  await first.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
  await first.getByLabel('Tema').selectOption('light');
  await expect.poll(() => first.evaluate(() => Object.keys(localStorage)
    .some(key => key.startsWith('aetherdesk-desktop-draft:tabs-fixture:')))).toBe(true);
  const original = await first.evaluate(() => {
    const key = Object.keys(localStorage).find(item => item.startsWith('aetherdesk-desktop-draft:tabs-fixture:'))!;
    return { key, raw: localStorage.getItem(key) };
  });
  const second = await context.newPage();
  await second.goto(`${baseURL}/`);
  await second.getByRole('button', { name: 'Ignorar rascunho' }).click();
  await second.locator('.launchers').getByRole('button', { name: /Explorador/ }).click();
  await expect.poll(() => second.evaluate(() => Object.keys(localStorage)
    .filter(key => key.startsWith('aetherdesk-desktop-draft:tabs-fixture:') &&
      !key.endsWith(':consumed')).length)).toBe(2);
  expect(await second.evaluate(key => localStorage.getItem(key), original.key)).toBe(original.raw);
});

test('aba com sessionStorage clonado recebe identidade própria', async ({ context }) => {
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'clone-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.abort('failed');
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  const first = await context.newPage();
  await first.goto(`${baseURL}/`);
  await first.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
  const originalId = await first.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'));
  expect(originalId).toBeTruthy();
  await expect.poll(() => first.evaluate(() => Object.keys(localStorage)
    .some(key => key.startsWith('aetherdesk-desktop-draft:clone-fixture:')))).toBe(true);

  const clone = await context.newPage();
  await clone.addInitScript(id => sessionStorage.setItem('aetherdesk-desktop-tab-id', id), originalId!);
  await clone.goto(`${baseURL}/`);
  await expect(clone.locator('.launchers').getByRole('button', { name: /Configurações/ })).toBeVisible();
  await expect.poll(() => clone.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'))).not.toBe(originalId);
  const cloneId = await clone.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'));
  expect(cloneId).toBeTruthy();
  expect(cloneId).not.toBe(originalId);
  await expect(clone.getByRole('button', { name: 'Recuperar rascunho' })).toBeVisible();
  await clone.getByRole('button', { name: 'Ignorar rascunho' }).click();
  await clone.locator('.launchers').getByRole('button', { name: /Explorador/ }).click();
  await expect.poll(() => clone.evaluate(() => Object.keys(localStorage)
    .filter(key => key.startsWith('aetherdesk-desktop-draft:clone-fixture:') &&
      !key.endsWith(':consumed')).length)).toBe(2);
});

test('menu Início, paleta e personalização funcionam com teclado', async ({ page }) => {
  await page.goto('/?fixture=1');
  await page.getByRole('button', { name: 'Início' }).click();
  const menu = page.getByRole('dialog', { name: 'Menu Início' });
  await expect(menu).toBeVisible();
  await menu.getByRole('button', { name: 'Gradiente' }).click();
  await expect(page.locator('.desktop.background-gradient')).toBeVisible();
  await menu.getByRole('button', { name: 'Remover Terminal na área de trabalho' }).click();
  await expect(page.locator('.launchers').getByRole('button', { name: 'Terminal' })).toHaveCount(0);
  await menu.getByRole('button', { name: 'Restaurar atalhos e aparência' }).click();
  const confirm = page.getByRole('alertdialog', { name: 'Restaurar personalização' });
  await expect(confirm).toBeVisible();
  await confirm.getByRole('button', { name: 'Restaurar' }).click();
  await expect(page.locator('.launchers').getByRole('button', { name: 'Terminal' })).toBeVisible();
  await expect(page.locator('.desktop.background-default')).toBeVisible();
  await menu.getByRole('button', { name: 'Fechar menu' }).click();
  await page.keyboard.press('Control+k');
  const palette = page.getByRole('dialog', { name: 'Paleta de comandos' });
  await expect(palette).toBeVisible();
  await palette.getByRole('textbox', { name: 'Buscar aplicativos' }).fill('config');
  await palette.getByRole('textbox', { name: 'Buscar aplicativos' }).press('Enter');
  await expect(page.locator('.desk-window')).toHaveCount(1);
  await page.locator('.launchers').getByRole('button', { name: 'Explorador' }).focus();
  await page.keyboard.press('Shift+F10');
  await expect(page.getByRole('menuitem', { name: 'Mover depois' })).toBeVisible();
});

test('wallpaper local rejeita arquivo falso, persiste imagem recodificada e limpa órfão', async ({ page }) => {
  await page.goto('/?fixture=1');
  await page.getByRole('button', { name: 'Início' }).click();
  const menu = page.getByRole('dialog', { name: 'Menu Início' });
  const upload = menu.getByLabel(/Enviar imagem PNG/);
  await upload.setInputFiles({ name: 'falso.png', mimeType: 'image/png', buffer: Buffer.from('<svg>unsafe</svg>') });
  await expect(menu.getByRole('alert')).toContainText('PNG, JPEG ou WebP válida');
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 4;
    canvas.getContext('2d')!.fillRect(0, 0, 4, 4);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await upload.setInputFiles({ name: 'seguro.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await expect(page.locator('.desktop.background-upload')).toBeVisible();
  await expect.poll(() => page.locator('.desktop-background').evaluate(element =>
    getComputedStyle(element).backgroundImage.startsWith('url("blob:'))).toBe(true);
  const stored = await page.evaluate(async () => new Promise<{ imageType: string; thumbnailSize: number; count: number }>((resolve, reject) => {
    const request = indexedDB.open('aetherdesk-wallpapers-v1');
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const all = db.transaction('wallpapers').objectStore('wallpapers').getAll();
      all.onsuccess = () => { const rows = all.result; resolve({ imageType: rows[0].mime,
        thumbnailSize: rows[0].thumbnailBytes.byteLength, count: rows.length }); db.close(); };
      all.onerror = () => reject(all.error);
    };
  }));
  expect(stored.count).toBe(1);
  expect(['image/webp', 'image/png']).toContain(stored.imageType);
  expect(stored.thumbnailSize).toBeGreaterThan(0);
  await page.reload();
  await expect.poll(() => page.locator('.desktop-background').evaluate(element =>
    getComputedStyle(element).backgroundImage.startsWith('url("blob:'))).toBe(true);
  await page.getByRole('button', { name: 'Início' }).click();
  await page.getByRole('dialog', { name: 'Menu Início' }).getByRole('button', { name: 'Sólido' }).click();
  await expect.poll(() => page.evaluate(async () => new Promise<number>((resolve, reject) => {
    const request = indexedDB.open('aetherdesk-wallpapers-v1');
    request.onerror = () => reject(request.error);
    request.onsuccess = () => { const db = request.result; const count = db.transaction('wallpapers').objectStore('wallpapers').count();
      count.onsuccess = () => { resolve(count.result); db.close(); }; count.onerror = () => reject(count.error); };
  }))).toBe(0);
});

test('primeira abertura do Monaco é mensurada com arquivo de fixture', async ({ page }, testInfo) => {
  test.setTimeout(45_000);
  let saved = '';
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'monaco-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.fulfill({ json: { data: {}, revision: 1 } });
    } else if (path === '/api/v1/files/list') {
      await route.fulfill({ json: { data: [{ name: 'fixture.py', kind: 'file',
        size: 11, mtime_ns: 0 }] } });
    } else if (path === '/api/v1/files/content' && route.request().method() === 'PUT') {
      saved = route.request().postDataJSON().content;
      await route.fulfill({ json: { data: { revision: 'fixture-v2' } } });
    } else if (path === '/api/v1/files/content') {
      await route.fulfill({ json: { data: { content: 'print(42)\n', revision: 'fixture-v1' } } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  await page.goto('/');
  const started = Date.now();
  await page.locator('.launchers').getByRole('button', { name: /Editor/ }).click();
  await page.locator('.open-path input').fill('/persist/fixture.py');
  await page.locator('.open-path').getByRole('button', { name: 'Abrir' }).click();
  await expect(page.locator('.monaco-editor')).toBeVisible({ timeout: 20_000 });
  console.log(`MONACO_FIRST_OPEN_MS ${testInfo.project.name} ${Date.now() - started}`);
  await page.locator('.monaco-editor').click();
  await page.keyboard.insertText('print(99)\n');
  await page.getByRole('button', { name: /Salvar · Ctrl\+S/ }).click();
  await expect.poll(() => saved).toContain('print(99)');
  await page.getByRole('button', { name: 'Buscar' }).click();
  await expect(page.locator('.find-widget')).toBeVisible();
});

test('revogação de capacidade oculta app e janela no navegador', async ({ page }) => {
  let revoked = false;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'admin', role: 'admin',
        account_id: 'revocation-fixture', permissions: revoked ? [] : ['accounts.view'],
        permissions_version: revoked ? 2 : 1 } } });
    } else if (path === '/api/v1/desktop/state') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/admin/accounts' || path === '/api/v1/admin/audit') {
      await route.fulfill({ json: { data: [] } });
    } else if (path === '/api/v1/admin/backup') {
      await route.fulfill({ json: { data: { enabled: false, frequency_hours: 24,
        destination: '', retention_mode: 'replace', retention_days: null,
        rpo_hours: null, rto_hours: null } } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  await page.goto('/');
  await page.locator('.launchers').getByRole('button', { name: /Administração/ }).click();
  await expect(page.locator('.desk-window')).toHaveCount(1);
  revoked = true;
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(page.locator('.launchers').getByRole('button', { name: /Administração/ })).toHaveCount(0);
  await expect(page.locator('.desk-window')).toHaveCount(0);
});

test('shell e configurações passam nas regras WCAG A e AA automatizadas', async ({ page }) => {
  await page.goto('/?fixture=1');
  await page.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
  await page.addScriptTag({ content: axe.source });
  const scan = () => page.evaluate(async () => {
    const result = await (window as typeof window & { axe: typeof axe }).axe.run(document,
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
    return result.violations.map(item => ({ id: item.id,
      nodes: item.nodes.map(node => node.target.join(' ')) }));
  });
  expect(await scan()).toEqual([]);
  await page.getByLabel('Tema').selectOption('light');
  expect(await scan()).toEqual([]);
});

test('menu Início e confirmação passam axe e mantêm foco contido', async ({ page }) => {
  await page.goto('/?fixture=1');
  await page.addScriptTag({ content: axe.source });
  await page.getByRole('button', { name: 'Início' }).click();
  const menu = page.getByRole('dialog', { name: 'Menu Início' });
  await expect(menu).toBeVisible();
  const violations = async () => page.evaluate(async () => {
    const report = await (window as typeof window & { axe: typeof axe }).axe.run(document,
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
    return report.violations.map(item => item.id);
  });
  expect(await violations()).toEqual([]);
  await menu.getByRole('button', { name: 'Restaurar atalhos e aparência' }).click();
  const confirm = page.getByRole('alertdialog', { name: 'Restaurar personalização' });
  await expect(confirm).toBeVisible();
  expect(await violations()).toEqual([]);
  for (let step = 0; step < 5; step++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => document.activeElement?.closest('[role="alertdialog"]') !== null)).toBe(true);
  }
  await confirm.getByRole('button', { name: 'Cancelar' }).click();
  await menu.getByRole('button', { name: 'Fechar menu' }).click();
});

test('apps base passam nas regras WCAG A e AA automatizadas', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/?fixture=1');
  await page.addScriptTag({ content: axe.source });
  for (const name of ['Explorador', 'Editor', 'Terminal', 'Monitor', 'Administração']) {
    await page.locator('.launchers').getByRole('button', { name: new RegExp(name) }).click();
    await expect(page.locator('.desk-window')).toBeVisible();
    const violations = await page.evaluate(async () => {
      const result = await (window as typeof window & { axe: typeof axe }).axe.run(document,
        { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
      return result.violations.map(item => ({ id: item.id,
        nodes: item.nodes.map(node => node.target.join(' ')) }));
    });
    expect(violations, name).toEqual([]);
    await page.getByRole('button', { name: 'Fechar' }).click();
  }
});

test('teclado alcança último atalho com contraste forçado e movimento reduzido', async ({ page }) => {
  await page.setViewportSize({ width: 240, height: 320 });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.goto('/?fixture=1');
  const launcher = page.locator('.launchers').getByRole('button', { name: /Configurações/ });
  for (let index = 0; index < 20 && !(await launcher.evaluate(element => document.activeElement === element)); index++) {
    await page.keyboard.press('Tab');
  }
  await expect(launcher).toBeFocused();
  await expect(launcher).toBeInViewport();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Fechar' })).toBeVisible();
  const close = page.getByRole('button', { name: 'Fechar' });
  for (let index = 0; index < 10 && !(await close.evaluate(element => document.activeElement === element)); index++) {
    await page.keyboard.press('Tab');
  }
  await expect(close).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('.desk-window')).toHaveCount(0);
});

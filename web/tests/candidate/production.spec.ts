import { expect, test, type Page } from '@playwright/test';
import axe from 'axe-core';

async function mockApi(page: Page) {
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'fixture', role: 'admin',
        account_id: 'production-fixture', permissions: ['files.read', 'files.write',
          'terminal.open', 'metrics.self', 'preferences.read', 'preferences.write',
          'accounts.view'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.fulfill({ json: { data: {}, revision: 1 } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
}

const sizes = [
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 1024, height: 768 },
];
const scales = [0.67, 1, 1.25, 1.5, 2];

for (const size of sizes) for (const scale of scales) {
  test(`bundle: atalhos e janela em ${size.width}×${size.height} escala CSS ${scale}`, async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width: Math.round(size.width / scale),
      height: Math.round(size.height / scale) });
    await page.goto('/');
    const launchers = page.locator('.launchers');
    await expect(launchers.getByRole('button')).toHaveCount(6);
    for (const name of ['Explorador', 'Editor', 'Terminal', 'Monitor', 'Administração', 'Configurações']) {
      const button = launchers.getByRole('button', { name: new RegExp(name) });
      await button.focus();
      await expect(button).toBeInViewport();
    }
    await launchers.getByRole('button', { name: /Configurações/ }).click();
    const close = page.getByRole('button', { name: 'Fechar' });
    await expect(close).toBeVisible();
    await expect(close).toBeInViewport();
    await close.click();
    await expect(page.locator('.desk-window')).toHaveCount(0);
  });
}

for (const size of [{ width: 390, height: 844 }, { width: 768, height: 1024 }]) {
  test(`bundle: toque em ${size.width}×${size.height}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: size, hasTouch: true, isMobile: true });
    try {
      const page = await context.newPage();
      await mockApi(page);
      await page.goto('/');
      const launcher = page.locator('.launchers').getByRole('button', { name: /Configurações/ });
      await launcher.tap();
      const close = page.getByRole('button', { name: 'Fechar' });
      await expect(close).toBeInViewport();
      await close.tap();
      await expect(page.locator('.desk-window')).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
}

test('bundle: teclado, contraste e movimento reduzido', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.goto('/');
  const launcher = page.locator('.launchers').getByRole('button', { name: /Configurações/ });
  await expect(launcher).toBeVisible();
  for (let index = 0; index < 20 && !(await launcher.evaluate(el => document.activeElement === el)); index++) {
    await page.keyboard.press('Tab');
  }
  await expect(launcher).toBeFocused();
  await page.keyboard.press('Enter');
  const close = page.getByRole('button', { name: 'Fechar' });
  await expect(close).toBeVisible();
  await close.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.desk-window')).toHaveCount(0);
});

test('bundle: axe WCAG A/AA no desktop', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await expect(page.locator('.launchers').getByRole('button')).toHaveCount(6);
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const result = await (window as typeof window & { axe: typeof axe }).axe.run(document,
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
    return result.violations.map(item => ({ id: item.id,
      nodes: item.nodes.map(node => node.target.join(' ')) }));
  });
  expect(violations).toEqual([]);
});

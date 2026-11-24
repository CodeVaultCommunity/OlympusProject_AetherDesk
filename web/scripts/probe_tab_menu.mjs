import { chromium, firefox, webkit } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const name = process.argv[2] ?? 'chromium';
const engine = { chromium, firefox, webkit }[name];
if (!engine) throw new Error(`Unknown browser: ${name}`);
const browser = await engine.launch({ headless: false });
try {
  const context = await browser.newContext({ viewport: null });
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'fixture', role: 'admin',
        account_id: `duplicate-${name}`, permissions: ['files.read', 'terminal.open',
          'metrics.self', 'preferences.read', 'accounts.view'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.fulfill({ json: { data: {}, revision: 1 } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:4173/');
  await page.locator('.launchers button').first().waitFor();
  const id = await page.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'));
  const ids = execFileSync('xdotool', ['search', '--onlyvisible', '--name', '.*'],
    { encoding: 'utf8' }).trim().split(/\s+/).filter(Boolean);
  const windows = ids.map(windowId => ({ id: windowId, title: execFileSync('xdotool',
    ['getwindowname', windowId], { encoding: 'utf8' }).trim() }));
  const target = windows.find(item => item.title.includes('AetherDesk'));
  if (!target) throw new Error(`No AetherDesk window: ${JSON.stringify(windows)}`);
  execFileSync('xdotool', ['windowsize', '--sync', target.id, '1280', '800']);
  execFileSync('xdotool', ['windowfocus', '--sync', target.id]);
  execFileSync('xdotool', ['mousemove', '--sync', '150', '20']);
  execFileSync('xdotool', ['click', '3']);
  await page.waitForTimeout(500);
  const screenshot = process.env.AETHERDESK_MENU_SCREENSHOT;
  if (screenshot) execFileSync('scrot', [screenshot]);
  let duplicate = null;
  if (process.env.AETHERDESK_DUPLICATE_TAB === '1') {
    const position = { chromium: [225, 192], firefox: [205, 228] }[name];
    if (!position) throw new Error(`Native tab duplication unconfigured for ${name}`);
    const opened = context.waitForEvent('page', { timeout: 10_000 });
    execFileSync('xdotool', ['mousemove', '--sync', ...position.map(String)]);
    execFileSync('xdotool', ['click', '1']);
    duplicate = await opened;
    await duplicate.waitForLoadState('domcontentloaded');
    await duplicate.locator('.launchers button').first().waitFor();
    let duplicateId = null;
    for (let attempt = 0; attempt < 50; attempt++) {
      duplicateId = await duplicate.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'));
      if (duplicateId && duplicateId !== id) break;
      await duplicate.waitForTimeout(100);
    }
    const originalId = await page.evaluate(() => sessionStorage.getItem('aetherdesk-desktop-tab-id'));
    duplicate = { id: duplicateId, originalId, different: duplicateId !== id,
      originalStable: originalId === id, url: duplicate.url() };
  }
  console.log(JSON.stringify({ name, tabId: id, pages: context.pages().length,
    browserWindow: target, screenshot, duplicate }));
  if (duplicate && (!duplicate.different || !duplicate.originalStable ||
    context.pages().length !== 2)) process.exitCode = 2;
} finally {
  await browser.close();
}

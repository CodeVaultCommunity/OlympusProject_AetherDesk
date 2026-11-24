import { firefox } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const browser = await firefox.launch({ headless: false });
try {
  const context = await browser.newContext({ viewport: null });
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'fixture', role: 'admin',
        account_id: 'reader-fixture', permissions: ['files.read', 'terminal.open',
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
  const launchers = page.locator('.launchers').getByRole('button');
  await launchers.first().waitFor();
  const ids = execFileSync('xdotool', ['search', '--onlyvisible', '--name', '.*'],
    { encoding: 'utf8' }).trim().split(/\s+/).filter(Boolean);
  const target = ids.find(id => execFileSync('xdotool', ['getwindowname', id],
    { encoding: 'utf8' }).includes('AetherDesk'));
  if (!target) throw new Error('Firefox window missing');
  execFileSync('xdotool', ['windowfocus', '--sync', target]);
  await page.waitForTimeout(2500);
  await launchers.first().focus();
  await page.waitForTimeout(800);
  execFileSync('xdotool', ['key', '--window', target, 'shift+Tab']);
  await page.waitForTimeout(500);
  execFileSync('xdotool', ['key', '--window', target, 'Tab']);
  await page.waitForTimeout(700);
  const focused = async () => page.evaluate(() => {
    const element = document.activeElement;
    return { text: element?.textContent?.trim(),
      label: element?.getAttribute('aria-label'),
      title: element?.getAttribute('title') };
  });
  const sequence = [await focused()];
  for (let index = 1; index < 6; index++) {
    execFileSync('xdotool', ['key', '--window', target, 'Tab']);
    await page.waitForTimeout(700);
    sequence.push(await focused());
  }
  const settingsFocused = await page.locator('.launchers')
    .getByRole('button', { name: /Configurações/ })
    .evaluate(element => document.activeElement === element);
  execFileSync('xdotool', ['key', '--window', target, 'Return']);
  const close = page.locator('.desk-window').filter({ hasText: 'Configurações pessoais' })
    .getByRole('button', { name: 'Fechar' });
  await close.waitFor({ state: 'visible' });
  const minimize = page.locator('.desk-window').filter({ hasText: 'Configurações pessoais' })
    .getByRole('button', { name: 'Minimizar' });
  await minimize.focus();
  execFileSync('xdotool', ['key', '--window', target, 'Tab']);
  await page.waitForTimeout(700);
  execFileSync('xdotool', ['key', '--window', target, 'Tab']);
  await page.waitForTimeout(700);
  const closeFocused = await close.evaluate(element => document.activeElement === element);
  execFileSync('xdotool', ['key', '--window', target, 'Return']);
  await close.waitFor({ state: 'detached' });
  await page.waitForTimeout(500);
  console.log(JSON.stringify({ reader: 'Orca 46.1', engine: 'firefox',
    sequence, settingsFocused, closeFocused,
    settingsOpened: true, settingsClosed: true }));
  if (!settingsFocused || !closeFocused) process.exitCode = 2;
} finally {
  await browser.close();
}

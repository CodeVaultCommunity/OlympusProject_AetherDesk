import { expect, test, firefox, webkit, type BrowserContext, type BrowserType } from '@playwright/test';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import { basename, resolve, sep } from 'node:path';

const baseURL = 'http://127.0.0.1:4173';
const profilesRoot = resolve(import.meta.dirname, '../../.tmp/candidate-crash');

test('bundle: rascunho sobrevive a crash real de Firefox ou WebKit', async ({ browserName }) => {
  test.skip(browserName === 'chromium', 'Chromium tem ensaio de crash próprio na suíte de desenvolvimento');
  test.setTimeout(120_000);
  const browserType: BrowserType = browserName === 'firefox' ? firefox : webkit;
  await mkdir(profilesRoot, { recursive: true });
  const profile = await mkdtemp(resolve(profilesRoot, 'profile-'));
  const account = `candidate-crash-${browserName}`;
  let context: BrowserContext | null = null;

  async function launch(): Promise<BrowserContext> {
    const opened = await browserType.launchPersistentContext(profile, { headless: true });
    await opened.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/v1/me') {
        await route.fulfill({ json: { data: { username: 'fixture', role: 'member',
          account_id: account, permissions: ['files.read', 'terminal.open', 'metrics.self',
            'preferences.read'], permissions_version: 1 } } });
      } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
        await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
          activeId: null, theme: 'dark' }, revision: 0 } });
      } else if (path === '/api/v1/desktop/state') {
        await route.abort('failed');
      } else {
        await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
      }
    });
    return opened;
  }

  async function browserPid(): Promise<number> {
    const children = (await readFile(`/proc/${process.pid}/task/${process.pid}/children`, 'utf8'))
      .trim().split(/\s+/).filter(Boolean).map(Number);
    const details = await Promise.all(children.map(async pid => {
      const command = await readFile(`/proc/${pid}/cmdline`, 'utf8').catch(() => '');
      return { pid, command };
    }));
    const matches = details.filter(item => item.command.includes(browserType.executablePath()) ||
      item.command.includes(profile));
    if (matches.length !== 1) {
      throw new Error(`Processo único não encontrado: ${JSON.stringify(details)}`);
    }
    return matches[0].pid;
  }

  try {
    context = await launch();
    const first = await context.newPage();
    await first.goto(baseURL);
    await first.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
    await first.getByLabel('Tema').selectOption('light');
    await expect(first.locator('.desktop.light')).toBeVisible();
    await expect.poll(() => first.evaluate(key => Object.keys(localStorage)
      .some(name => name.startsWith(key)), `aetherdesk-desktop-draft:${account}:`)).toBe(true);
    await first.waitForTimeout(5_000);
    const pid = await browserPid();
    process.kill(pid, 'SIGKILL');
    await context.close().catch(() => undefined);
    context = null;

    context = await launch();
    const second = await context.newPage();
    await second.goto(baseURL);
    await expect(second.getByRole('button', { name: 'Recuperar rascunho' })).toBeVisible();
    await second.getByRole('button', { name: 'Recuperar rascunho' }).click();
    await expect(second.locator('.desktop.light')).toBeVisible();
  } finally {
    if (context) await context.close().catch(() => undefined);
    const target = resolve(profile);
    if (target.startsWith(profilesRoot + sep) && basename(target).startsWith('profile-')) {
      await rm(target, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    }
  }
});

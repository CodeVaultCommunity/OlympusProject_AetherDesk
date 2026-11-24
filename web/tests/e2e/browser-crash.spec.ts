import { expect, test, chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { resolve, sep, basename } from 'node:path';

const baseURL = process.env.AETHERDESK_E2E_BASE_URL || 'http://127.0.0.1:5173';
const profilesRoot = resolve(import.meta.dirname, '../../.tmp/browser-crash');

test('rascunho sobrevive ao encerramento do processo Chromium', async ({ browserName }) => {
  test.skip(browserName !== 'chromium', 'Ensaio de processo usa o Chromium da fixture');
  test.setTimeout(90_000);
  await mkdir(profilesRoot, { recursive: true });
  const profile = await mkdtemp(resolve(profilesRoot, 'profile-'));
  let child: ReturnType<typeof spawn> | null = null;
  let connected: Awaited<ReturnType<typeof chromium.connectOverCDP>> | null = null;

  async function launch() {
    const process = spawn(chromium.executablePath(), [
      '--headless=new', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
      '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    ], { stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true,
      detached: processPlatform() !== 'win32' });
    child = process;
    const endpoint = await new Promise<string>((accept, reject) => {
      let output = '';
      const timer = setTimeout(() => reject(new Error(`Chromium não anunciou CDP: ${output}`)), 20_000);
      process.stderr!.on('data', chunk => {
        output += chunk.toString();
        const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/);
        if (match) { clearTimeout(timer); accept(match[1]); }
      });
      process.once('error', error => { clearTimeout(timer); reject(error); });
      process.once('exit', code => { clearTimeout(timer); reject(new Error(`Chromium saiu (${code}): ${output}`)); });
    });
    connected = await chromium.connectOverCDP(endpoint);
    const context = connected.contexts()[0];
    if (!context) throw new Error('Perfil Chromium sem contexto persistente');
    await context.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/v1/me') {
        await route.fulfill({ json: { data: { username: 'member', role: 'member',
          account_id: 'process-crash-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
      } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
        await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
          activeId: null, theme: 'dark' }, revision: 0 } });
      } else if (path === '/api/v1/desktop/state') {
        await route.abort('failed');
      } else {
        await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
      }
    });
    return context;
  }

  async function kill() {
    const process = child;
    child = null;
    connected = null;
    if (!process || !process.pid || process.exitCode !== null) return;
    const exited = new Promise<void>((done, reject) => {
      const timer = setTimeout(() => reject(new Error('Chromium não encerrou em 10 s')), 10_000);
      process.once('exit', () => { clearTimeout(timer); done(); });
    });
    if (processPlatform() === 'win32') {
      process.kill('SIGKILL');
    } else {
      globalThis.process.kill(-process.pid, 'SIGKILL');
    }
    await exited;
  }

  try {
    const firstContext = await launch();
    const first = await firstContext.newPage();
    await first.goto(baseURL);
    await first.locator('.launchers').getByRole('button', { name: /Configurações/ }).click();
    await first.getByLabel('Tema').selectOption('light');
    await expect(first.locator('.desktop.light')).toBeVisible();
    await expect.poll(() => first.evaluate(() => Object.keys(localStorage)
      .some(key => key.startsWith('aetherdesk-desktop-draft:process-crash-fixture:')))).toBe(true);
    await kill();

    const secondContext = await launch();
    const second = await secondContext.newPage();
    await second.goto(baseURL);
    await expect(second.locator('.launchers').getByRole('button', { name: /Configurações/ })).toBeVisible();
    await expect(second.getByRole('button', { name: 'Recuperar rascunho' })).toBeVisible();
    await second.getByRole('button', { name: 'Recuperar rascunho' }).click();
    await expect(second.locator('.desktop.light')).toBeVisible();
  } finally {
    if (connected) await connected.close().catch(() => undefined);
    await kill().catch(() => undefined);
    const target = resolve(profile);
    if (target.startsWith(profilesRoot + sep) && basename(target).startsWith('profile-')) {
      await rm(target, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    }
  }
});

function processPlatform() { return process.platform; }

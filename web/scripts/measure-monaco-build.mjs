import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
process.env.PLAYWRIGHT_BROWSERS_PATH ||= resolve(root, '.playwright-browsers');
const { chromium } = await import('@playwright/test');
const language = process.argv[2] === 'typescript' ? 'typescript' : 'python';
const filename = language === 'typescript' ? 'fixture.ts' : 'fixture.py';
const content = language === 'typescript' ? 'const answer: number = 42;\n' : 'print(42)\n';
const reservation = createServer();
reservation.listen(0, '127.0.0.1');
await once(reservation, 'listening');
const address = reservation.address();
if (!address || typeof address === 'string') throw new Error('Porta de medição indisponível');
const port = address.port;
const closed = once(reservation, 'close');
reservation.close();
await closed;
const baseURL = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, [resolve(root, 'node_modules/vite/bin/vite.js'),
  'preview', '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
{ cwd: root, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
let output = '';
for (const stream of [server.stdout, server.stderr]) {
  stream.on('data', chunk => { output = (output + chunk.toString()).slice(-4000); });
}

async function waitForPreview() {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) throw new Error(`Preview encerrou: ${output}`);
    try {
      const response = await fetch(baseURL);
      if (response.ok && (await response.text()).includes('<title>AetherDesk</title>')) return;
    } catch { /* aguardando o servidor */ }
    await new Promise(done => setTimeout(done, 100));
  }
  throw new Error(`Preview não iniciou: ${output}`);
}

let browser;
try {
  await waitForPreview();
  browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  let savedContent = '';
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    window.__workerUrls = [];
    window.Worker = class extends NativeWorker {
      constructor(url, options) {
        window.__workerUrls.push(String(url));
        super(url, options);
      }
    };
  });
  const browserErrors = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  const resources = [];
  let phase = 'initial';
  context.on('response', response => {
    const url = new URL(response.url());
    if (url.origin !== baseURL || !url.pathname.startsWith('/assets/')) return;
    resources.push({ response, phase });
  });
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'monaco-build-fixture', permissions: [], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.fulfill({ json: { data: {}, revision: 1 } });
    } else if (path === '/api/v1/files/list') {
      await route.fulfill({ json: { data: [{ name: filename, kind: 'file',
        size: content.length, mtime_ns: 0 }] } });
    } else if (path === '/api/v1/files/content' && route.request().method() === 'PUT') {
      savedContent = route.request().postDataJSON().content;
      await route.fulfill({ json: { data: { revision: 'fixture-v2' } } });
    } else if (path === '/api/v1/files/content') {
      await route.fulfill({ json: { data: { content, revision: 'fixture-v1' } } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  await page.goto(baseURL);
  await page.locator('.launchers').getByRole('button', { name: /Editor/ }).waitFor();
  await page.waitForLoadState('networkidle');
  phase = 'editor';
  const started = performance.now();
  await page.locator('.launchers').getByRole('button', { name: /Editor/ }).click();
  await page.locator('.open-path input').fill(`/persist/${filename}`);
  await page.locator('.open-path').getByRole('button', { name: 'Abrir' }).click();
  await page.locator('.monaco-editor').waitFor({ state: 'visible', timeout: 30_000 });
  const openMs = Math.round(performance.now() - started);
  if (language === 'typescript') {
    await page.locator('.monaco-editor').click();
    await page.keyboard.insertText('const invalid: string = 42;\n');
    await page.getByRole('button', { name: /Salvar · Ctrl\+S/ }).click();
    const saveDeadline = Date.now() + 5000;
    while (!savedContent && Date.now() < saveDeadline) {
      await new Promise(done => setTimeout(done, 50));
    }
    if (!savedContent.includes('const invalid: string = 42;')) {
      throw new Error('Edição TypeScript não chegou ao endpoint de salvamento');
    }
  }
  await page.waitForTimeout(language === 'typescript' ? 4000 : 1500);
  const visibleDiagnostics = language === 'typescript' ? await page.locator('.monaco-editor .squiggly-error').count() : null;
  const timings = await page.evaluate(() => Object.fromEntries(
    performance.getEntriesByType('resource')
      .filter(entry => new URL(entry.name).pathname.startsWith('/assets/'))
      .map(entry => {
        const resource = entry;
        return [new URL(resource.name).pathname, {
          encodedBytes: resource.encodedBodySize,
          transferBytes: resource.transferSize,
          decodedBytes: resource.decodedBodySize,
        }];
      })));
  const assets = await Promise.all(resources.map(async ({ response, phase: assetPhase }) => ({
    path: new URL(response.url()).pathname,
    phase: assetPhase,
    status: response.status(),
    decodedBytes: (await response.body()).length,
    contentEncoding: response.headers()['content-encoding'] || 'identity',
    contentLength: Number(response.headers()['content-length']) || null,
    ...timings[new URL(response.url()).pathname],
  })));
  if (assets.some(asset => asset.status !== 200)) throw new Error('Asset Monaco não carregou');
  const workers = page.workers().map(worker => new URL(worker.url()).pathname);
  const workerAttempts = await page.evaluate(() => window.__workerUrls);
  if (language === 'typescript' && (!workers.some(path => path.includes('ts.worker')) ||
      !visibleDiagnostics || browserErrors.length)) {
    throw new Error('Worker ou diagnóstico TypeScript indisponível no build');
  }
  process.stdout.write('AETHERDESK_MONACO_BUILD_LOAD=' + JSON.stringify({
    browser: 'chromium', preview: 'vite preview', language, openMs,
    assetCount: assets.length, workers, workerAttempts, browserErrors,
    editedAndSaved: language === 'typescript' ? !!savedContent : null,
    visibleDiagnostics,
    decodedBytes: assets.reduce((sum, asset) => sum + asset.decodedBytes, 0),
    encodedBytes: assets.reduce((sum, asset) => sum + (asset.encodedBytes || asset.contentLength || 0), 0),
    transferBytes: assets.reduce((sum, asset) => sum + (asset.transferBytes || 0), 0),
    editorEncodedBytes: assets.filter(asset => asset.phase === 'editor')
      .reduce((sum, asset) => sum + (asset.encodedBytes || asset.contentLength || 0), 0),
    assets,
  }) + '\n');
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) {
    const exited = once(server, 'exit');
    server.kill();
    await Promise.race([exited, new Promise(done => setTimeout(done, 3000))]);
    if (server.exitCode === null) server.kill('SIGKILL');
  }
}

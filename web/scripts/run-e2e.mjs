import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
// A primeira importação lazy do Monaco pode iniciar optimizeDeps e provocar
// reload em páginas de outros workers. Aquecer o cache antes do navegador.
const optimizer = spawnSync(process.execPath,
  [resolve(root, 'node_modules/vite/bin/vite.js'), 'optimize'],
  { cwd: root, encoding: 'utf8', timeout: 60_000, windowsHide: true });
if (optimizer.error || optimizer.status !== 0) {
  throw new Error(`Pré-otimização Vite falhou: ${optimizer.error || optimizer.stderr}`);
}
const reservation = createServer();
reservation.listen(0, '127.0.0.1');
await once(reservation, 'listening');
const address = reservation.address();
if (!address || typeof address === 'string') throw new Error('Porta E2E indisponível');
const port = address.port;
const released = once(reservation, 'close');
reservation.close();
await released;
const baseURL = `http://127.0.0.1:${port}`;
const browserEnv = { ...process.env,
  PLAYWRIGHT_BROWSERS_PATH: process.env.PLAYWRIGHT_BROWSERS_PATH || resolve(root, '.playwright-browsers'),
  AETHERDESK_E2E_BASE_URL: baseURL };
const server = spawn(process.execPath,
  [resolve(root, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1',
    '--port', String(port), '--strictPort'],
  { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
let serverOutput = '';
let stopping = false;
server.on('exit', (code, signal) => {
  if (!stopping) process.stderr.write(`Vite encerrou durante E2E (code=${code}, signal=${signal}): ${serverOutput}\n`);
});
for (const stream of [server.stdout, server.stderr]) {
  stream.on('data', chunk => { serverOutput = (serverOutput + chunk.toString()).slice(-4000); });
}

async function ready() {
  const deadline = Date.now() + 20_000;
  let lastProbe = 'nenhuma resposta';
  while (Date.now() < deadline) {
    if (server.exitCode !== null) throw new Error(`Vite encerrou: ${serverOutput}`);
    try {
      const response = await fetch(`${baseURL}/?fixture=1`);
      const html = await response.text();
      lastProbe = `HTTP ${response.status}, título=${html.includes('<title>AetherDesk</title>')}`;
      if (response.ok && html.includes('<title>AetherDesk</title>') &&
          server.exitCode === null) return;
    } catch (error) { lastProbe = String(error); }
    await new Promise(done => setTimeout(done, 100));
  }
  throw new Error(`Vite não iniciou em 20 s (${lastProbe}): ${serverOutput}`);
}

try {
  await ready();
  const runner = spawn(process.execPath,
    [resolve(root, 'node_modules/@playwright/test/cli.js'), 'test', ...process.argv.slice(2)],
    { cwd: root, stdio: 'inherit', windowsHide: true, env: browserEnv });
  const [code, signal] = await once(runner, 'exit');
  if (signal || code !== 0) process.exitCode = code || 1;
} catch (error) {
  process.stderr.write(`${error}\n`);
  process.exitCode = 1;
} finally {
  if (server.exitCode === null) {
    stopping = true;
    const stopped = once(server, 'exit');
    server.kill();
    await Promise.race([stopped, new Promise(done => setTimeout(done, 3000))]);
    if (server.exitCode === null) server.kill('SIGKILL');
  }
}

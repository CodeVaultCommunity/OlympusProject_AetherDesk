import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const installer = spawn(process.execPath,
  [resolve(root, 'node_modules/@playwright/test/cli.js'), 'install',
    'chromium', 'firefox', 'webkit'],
  { cwd: root, stdio: 'inherit', windowsHide: true, env: {
    ...process.env, PLAYWRIGHT_BROWSERS_PATH: resolve(root, '.playwright-browsers'),
  } });
const [code, signal] = await once(installer, 'exit');
if (signal || code !== 0) process.exitCode = code || 1;

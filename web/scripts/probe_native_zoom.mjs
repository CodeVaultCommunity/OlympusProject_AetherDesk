import { chromium, firefox, webkit } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const engines = { chromium, firefox, webkit };
const selected = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(engines);
const outcomes = [];
const sizes = process.env.AETHERDESK_NATIVE_SHORT === '1'
  ? [[1920, 1080]] : [[1920, 1080], [1366, 768], [1024, 768]];

for (const name of selected) {
  const engine = engines[name];
  if (!engine) throw new Error(`Unknown engine: ${name}`);
  const browser = await engine.launch({ headless: false });
  try {
    const context = await browser.newContext({ viewport: null });
    await context.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/v1/me') {
        await route.fulfill({ json: { data: { username: 'fixture', role: 'admin',
          account_id: `zoom-${name}`, permissions: ['files.read', 'terminal.open',
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
    const metrics = () => page.evaluate(() => ({ dpr: devicePixelRatio,
      width: innerWidth, height: innerHeight }));
    const ids = execFileSync('xdotool', ['search', '--onlyvisible', '--name', '.*'],
      { encoding: 'utf8' }).trim().split(/\s+/).filter(Boolean);
    const windows = ids.map(id => ({ id, title: execFileSync('xdotool',
      ['getwindowname', id], { encoding: 'utf8' }).trim() }));
    const target = windows.find(item => item.title.includes('AetherDesk'));
    if (!target) throw new Error(`No AetherDesk window: ${JSON.stringify(windows)}`);
    const key = value => execFileSync('xdotool', ['key', '--window', target.id, value]);
    const physicalClick = async box => {
      const geometry = Object.fromEntries(execFileSync('xdotool',
        ['getwindowgeometry', '--shell', target.id], { encoding: 'utf8' })
        .trim().split(/\r?\n/).map(line => line.split('=')));
      const pageMetrics = await page.evaluate(() => ({ outerHeight, innerHeight,
        dpr: devicePixelRatio, screenX, screenY }));
      const chromeHeight = Number(geometry.HEIGHT) - pageMetrics.innerHeight * pageMetrics.dpr;
      const x = Math.round(Number(geometry.X) + (box.x + box.width / 2) * pageMetrics.dpr);
      const y = Math.round(Number(geometry.Y) + chromeHeight +
        (box.y + box.height / 2) * pageMetrics.dpr);
      execFileSync('xdotool', ['mousemove', '--sync', String(x), String(y)]);
      execFileSync('xdotool', ['click', '1']);
      await page.waitForTimeout(100);
      return { geometry, pageMetrics, chromeHeight, x, y };
    };
    let currentSize = '';
    const inside = (box, view) => !!box && box.x >= -1 && box.y >= -1 &&
      box.x + box.width <= view.width + 1 && box.y + box.height <= view.height + 1;
    async function inspect(baseDpr) {
      await page.waitForTimeout(name === 'firefox' ? 500 : 100);
      const view = await metrics();
      const launchers = page.locator('.launchers').getByRole('button');
      const count = await launchers.count();
      let iconsReachable = count === 6;
      for (let index = 0; index < count; index++) {
        const button = launchers.nth(index);
        await button.focus();
        iconsReachable &&= inside(await button.boundingBox(), view);
      }
      console.log(`NATIVE_ZOOM_CHECK engine=${name} outer=${currentSize} percent=${Math.round(100 * view.dpr / baseDpr)}`);
      const settings = page.locator('.launchers').getByRole('button', { name: /Configurações/ });
      let launcherPointerReachable = true;
      let launcherOverlap = null;
      try {
        if (name === 'firefox') {
          await settings.scrollIntoViewIfNeeded();
          await physicalClick(await settings.boundingBox());
          if (!(await page.locator('.desk-window')
            .filter({ hasText: 'Configurações pessoais' }).count())) {
            throw new Error('Physical pointer did not open Settings');
          }
        } else {
          await settings.click({ timeout: 5000 });
        }
      } catch (error) {
        launcherPointerReachable = false;
        const settingsBox = await settings.boundingBox();
        const hit = settingsBox && await page.evaluate(({ x, y }) =>
          document.elementFromPoint(x, y)?.outerHTML.slice(0, 400),
        { x: settingsBox.x + settingsBox.width / 2,
          y: settingsBox.y + settingsBox.height / 2 });
        launcherOverlap = { settings: settingsBox, hit,
          administration: await page.locator('.launchers').getByRole('button',
            { name: /Administração/ }).boundingBox() };
        console.log(`NATIVE_ZOOM_LAUNCHER_INTERCEPT ${JSON.stringify({ name, currentSize,
          view, launcherOverlap, error: String(error).slice(0, 900) })}`);
        if (process.env.AETHERDESK_NATIVE_DIAG === '1' && settingsBox) {
          await page.mouse.click(settingsBox.x + settingsBox.width / 2,
            settingsBox.y + settingsBox.height / 2);
          console.log(`NATIVE_ZOOM_RAW_MOUSE ${JSON.stringify({ name, currentSize,
            openedSettings: !!(await page.locator('.desk-window')
              .filter({ hasText: 'Configurações pessoais' }).count()) })}`);
          if (!(await page.locator('.desk-window')
            .filter({ hasText: 'Configurações pessoais' }).count())) {
            const physical = await physicalClick(settingsBox);
            console.log(`NATIVE_ZOOM_PHYSICAL_MOUSE ${JSON.stringify({ name, currentSize,
              physical, openedSettings: !!(await page.locator('.desk-window')
                .filter({ hasText: 'Configurações pessoais' }).count()) })}`);
          }
        }
        if (!(await page.locator('.desk-window')
          .filter({ hasText: 'Configurações pessoais' }).count())) {
          await settings.focus();
          await settings.press('Enter');
        }
      }
      const close = page.locator('.desk-window').filter({ hasText: 'Configurações pessoais' })
        .getByRole('button', { name: 'Fechar' });
      if (!(await close.count())) {
        console.log(`NATIVE_ZOOM_MISSING_SETTINGS ${JSON.stringify({ name, currentSize,
          view, windows: await page.locator('.desk-window').allTextContents(),
          focused: await page.evaluate(() => document.activeElement?.outerHTML) })}`);
        throw new Error('Settings did not open after pointer and keyboard activation');
      }
      await page.waitForTimeout(name === 'firefox' ? 400 : 100);
      const closeBox = await close.boundingBox();
      const closeReachable = inside(closeBox, view);
      let closePointerReachable = true;
      let overlap = null;
      try {
        if (name === 'firefox') {
          await close.scrollIntoViewIfNeeded();
          await physicalClick(await close.boundingBox());
          if (await page.locator('.desk-window')
            .filter({ hasText: 'Configurações pessoais' }).count()) {
            throw new Error('Physical pointer did not close Settings');
          }
        } else {
          await close.click({ timeout: 5000 });
        }
      } catch (error) {
        closePointerReachable = false;
        overlap = { close: closeBox,
          minimize: await page.locator('.desk-window')
            .filter({ hasText: 'Configurações pessoais' })
            .getByRole('button', { name: 'Minimizar' }).boundingBox() };
        console.log(`NATIVE_ZOOM_CLOSE_INTERCEPT ${JSON.stringify({ name, currentSize,
          view, overlap, error: String(error).slice(0, 900) })}`);
        if (process.env.AETHERDESK_NATIVE_DIAG === '1' && closeBox) {
          await page.mouse.click(closeBox.x + closeBox.width / 2,
            closeBox.y + closeBox.height / 2);
          console.log(`NATIVE_ZOOM_RAW_MOUSE_CLOSE ${JSON.stringify({ name, currentSize,
            closedSettings: !(await page.locator('.desk-window')
              .filter({ hasText: 'Configurações pessoais' }).count()) })}`);
        }
        if (!(await page.locator('.desk-window')
          .filter({ hasText: 'Configurações pessoais' }).count())) {
          closePointerReachable = true;
        } else {
        await close.focus();
        await close.press('Enter');
        }
      }
      const unexpectedWindows = await page.locator('.desk-window').count();
      for (let index = 0; index < unexpectedWindows; index++) {
        await page.locator('.desk-window').first().getByRole('button', { name: 'Fechar' })
          .press('Enter');
      }
      return { percent: Math.round(100 * view.dpr / baseDpr), width: view.width,
        iconsReachable, launcherPointerReachable, launcherOverlap,
        closeReachable, closePointerReachable, overlap, unexpectedWindows };
    }
    for (const [width, height] of sizes) {
      currentSize = `${width}x${height}`;
      execFileSync('xdotool', ['windowsize', '--sync', target.id, String(width), String(height)]);
      execFileSync('xdotool', ['windowfocus', '--sync', target.id]);
      key('ctrl+0');
      await page.waitForTimeout(200);
      const baseDpr = (await metrics()).dpr;
      const at100 = await inspect(baseDpr);
      const plus = [];
      for (let step = 0; step < 12; step++) {
        key('ctrl+plus');
        await page.waitForTimeout(150);
        const sample = await inspect(baseDpr);
        plus.push(sample);
        if (sample.percent >= 200 || (process.env.AETHERDESK_NATIVE_DIAG === '1'
          && plus.length >= 2)) break;
      }
      key('ctrl+0');
      await page.waitForTimeout(150);
      const minus = [];
      for (let step = 0; step < (process.env.AETHERDESK_NATIVE_DIAG === '1' ? 0 : 12); step++) {
        key('ctrl+minus');
        await page.waitForTimeout(150);
        const sample = await inspect(baseDpr);
        minus.push(sample);
        if (sample.percent <= 67) break;
      }
      const samples = [at100, ...plus, ...minus];
      outcomes.push({ engine: name, outer: { width, height }, baseline: at100,
        plus, minus, rangeReached: plus.some(item => item.percent >= 200) &&
          minus.some(item => item.percent <= 67),
        controlsReachable: samples.every(item => item.iconsReachable &&
          item.launcherPointerReachable && item.closePointerReachable &&
          item.unexpectedWindows === 0) });
      console.log(`NATIVE_ZOOM_PROGRESS engine=${name} outer=${width}x${height} ` +
        `max=${Math.max(...plus.map(item => item.percent))}% ` +
        `min=${Math.min(...minus.map(item => item.percent))}% ` +
        `unreachable=${samples.filter(item => !item.iconsReachable ||
          !item.launcherPointerReachable || !item.closePointerReachable ||
          item.unexpectedWindows).length} ` +
        `scrollNeeded=${samples.filter(item => !item.closeReachable).length}`);
      key('ctrl+0');
    }
  } finally {
    await browser.close();
  }
}
const report = { nativeZoomProbe: outcomes };
if (process.env.AETHERDESK_NATIVE_REPORT) {
  writeFileSync(process.env.AETHERDESK_NATIVE_REPORT, JSON.stringify(report, null, 2));
}
console.log(JSON.stringify({ nativeZoomSummary: outcomes.map(item => ({
  engine: item.engine, outer: item.outer,
  min: Math.min(...item.minus.map(sample => sample.percent)),
  max: Math.max(...item.plus.map(sample => sample.percent)),
  rangeReached: item.rangeReached, controlsReachable: item.controlsReachable,
  anomalyCount: [item.baseline, ...item.plus, ...item.minus]
    .filter(sample => !sample.iconsReachable || !sample.launcherPointerReachable ||
      !sample.closePointerReachable || sample.unexpectedWindows).length,
})) }, null, 2));
if (process.env.AETHERDESK_NATIVE_DIAG !== '1' &&
  outcomes.some(item => !item.rangeReached || !item.controlsReachable)) {
  process.exitCode = 2;
}

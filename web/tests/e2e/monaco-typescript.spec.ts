import { expect, test } from '@playwright/test';

test('Monaco oferece diagnóstico TypeScript no modelo aberto', async ({ page }) => {
  test.setTimeout(60_000);
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      await route.fulfill({ json: { data: { username: 'member', role: 'member',
        account_id: 'typescript-fixture', permissions: ['files.read', 'terminal.open', 'metrics.self', 'preferences.read'], permissions_version: 1 } } });
    } else if (path === '/api/v1/desktop/state' && route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { schemaVersion: 2, windows: [],
        activeId: null, theme: 'dark' }, revision: 0 } });
    } else if (path === '/api/v1/desktop/state') {
      await route.fulfill({ json: { data: {}, revision: 1 } });
    } else if (path === '/api/v1/files/list') {
      await route.fulfill({ json: { data: [{ name: 'fixture.ts', kind: 'file',
        size: 28, mtime_ns: 0 }] } });
    } else if (path === '/api/v1/files/content') {
      await route.fulfill({ json: { data: { content: 'const answer: string = 42;\n',
        revision: 'fixture-v1' } } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'NOT_FOUND' } });
    }
  });
  await page.goto('/');
  await page.locator('.launchers').getByRole('button', { name: /Editor/ }).click();
  await page.locator('.open-path input').fill('/persist/fixture.ts');
  await page.locator('.open-path').getByRole('button', { name: 'Abrir' }).click();
  await expect(page.locator('.monaco-editor')).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => page.locator('.monaco-editor .squiggly-error').count(),
    { timeout: 20_000 }).toBeGreaterThan(0);
  const result = await page.evaluate(async () => {
    const { monaco, getTypeScriptWorker } = await import('/src/apps/monaco.ts');
    const model = monaco.editor.getModels().find(item => item.uri.path.endsWith('/fixture.ts'));
    if (!model) return { language: 'missing', diagnostics: 0 };
    try {
      const workerFactory = await getTypeScriptWorker();
      const worker = await workerFactory(model.uri);
      const diagnostics = await worker.getSemanticDiagnostics(model.uri.toString());
      return { language: model.getLanguageId(), diagnostics: diagnostics.length,
        registered: monaco.languages.getLanguages().map(item => item.id) };
    } catch (error) {
      return { language: model.getLanguageId(), diagnostics: 0,
        error: String(error), registered: monaco.languages.getLanguages().map(item => item.id) };
    }
  });
  expect(result.language).toBe('typescript');
  expect(result.registered).toEqual(expect.arrayContaining(
    ['typescript', 'javascript', 'css', 'html', 'python']));
  expect(result.diagnostics, JSON.stringify(result)).toBeGreaterThan(0);
});

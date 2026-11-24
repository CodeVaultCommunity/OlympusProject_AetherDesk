import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/candidate',
  workers: 2,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:4173', screenshot: 'only-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});

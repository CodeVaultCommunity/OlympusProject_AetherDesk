import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  workers: 2,
  timeout: 20_000,
  expect: { timeout: 5_000 },
  outputDir: './.tmp/playwright-results',
  reporter: 'list',
  use: { baseURL: process.env.AETHERDESK_E2E_BASE_URL || 'http://127.0.0.1:5173',
    screenshot: 'only-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});

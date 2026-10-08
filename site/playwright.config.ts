import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.ts',
  timeout: 45000,
  expect: { timeout: 10000 },
  workers: 1,
  reporter: 'list',
  outputDir: './test-results',
  use: { baseURL: process.env.SITE_URL ?? 'http://127.0.0.1:5190', channel: 'msedge', headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
});
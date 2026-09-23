import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
export default defineConfig({
  testDir: '.', testMatch: 'real-roster.spec.ts', workers: 1, timeout: 180000,
  reporter: [['list'], ['json', { outputFile: path.resolve('.local/yjyz-roster/playwright-results.json') }]],
  outputDir: path.resolve('.local/yjyz-roster/browser-results'),
  use: { baseURL: 'http://127.0.0.1:61564', ...devices['Desktop Chrome'], trace: 'off', video: 'off', screenshot: 'off' },
});

import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: '.', testMatch: '*.spec.ts', workers: 1, timeout: 30000,
  reporter: [['list']], outputDir: process.env.QA_OUTPUT_DIR || '/tmp/qa-alignment-browser',
  use: { baseURL: 'http://127.0.0.1:5198', ...devices['Desktop Chrome'], trace: 'off', video: 'off', screenshot: 'only-on-failure' },
})

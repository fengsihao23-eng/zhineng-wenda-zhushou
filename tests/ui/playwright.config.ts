import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: '../../test-results/ui',
  workers: 2,
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:5187', ...devices['Desktop Chrome'], screenshot: 'only-on-failure' },
  webServer: {
    command: 'node ../../apps/web/node_modules/vite/bin/vite.js --config vite.config.mts',
    cwd: path.resolve(__dirname),
    url: 'http://127.0.0.1:5187',
    reuseExistingServer: false,
  },
})

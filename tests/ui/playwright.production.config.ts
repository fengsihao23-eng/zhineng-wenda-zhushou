import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  testMatch: 'workflow-gaps.spec.ts',
  outputDir: '../../test-results/workflow-production',
  workers: 1,
  use: { ...base.use, baseURL: 'http://127.0.0.1:5196' },
  webServer: {
    ...base.webServer,
    command: 'node ../../apps/web/node_modules/vite/bin/vite.js preview --config vite.config.mts --host 127.0.0.1 --port 5196 --strictPort',
    url: 'http://127.0.0.1:5196',
    reuseExistingServer: false,
  },
})

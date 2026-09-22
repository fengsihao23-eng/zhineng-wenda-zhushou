import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E测试配置
 * 覆盖核心用户流程：认证、对话、成绩查询、诊断报告访问控制
 */
export default defineConfig({
  testDir: './tests/e2e',

  // 测试执行配置
  fullyParallel: true,
  timeout: 45000,
  expect: { timeout: 10000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 2,

  // 报告配置
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ['list'],
  ],

  // 全局配置
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    // 等待配置
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  // 测试项目配置
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],

  // CI 和 scripts/run-e2e-tests.sh 负责构建并启动生产服务。
  // 不在此重复启动 Compose，否则 CI 会把已经就绪的服务判为端口冲突。
});

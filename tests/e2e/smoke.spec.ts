import { test, expect } from './fixtures/auth-fixture';

/**
 * 冒烟测试 (Smoke Tests)
 * 快速验证系统基本功能是否正常
 */

test.describe('冒烟测试', () => {
  test('健康检查端点应该正常响应', async ({ request }) => {
    const response = await request.get('/health');
    expect(response.ok()).toBeTruthy();
    expect(response.status()).toBe(200);
  });

  test('登录页应该正常加载', async ({ page }) => {
    await page.goto('/login');

    await expect(page.locator('h1')).toContainText('智能问答助手');
    await expect(page.locator('input#username')).toBeVisible();
    await expect(page.locator('input#password')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('认证用户应该能访问首页', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/');

    // 验证不会重定向到登录页
    await expect(authenticatedPage).not.toHaveURL(/\/login/);

    // 验证页面内容加载
    await expect(authenticatedPage.locator('body')).not.toBeEmpty();
  });

  test('聊天页面应该正常加载', async ({ authenticatedPage }) => {
    await authenticatedPage.goto('/chat');

    await expect(authenticatedPage).toHaveURL(/\/chat/);

    // 验证输入框存在
    const input = authenticatedPage.locator('textarea, input[type="text"]').first();
    await expect(input).toBeVisible({ timeout: 10000 });
  });

  test('API 文档应该可访问', async ({ request }) => {
    const response = await request.get('/docs');
    expect(response.status()).toBeLessThan(400);
  });

  test('静态资源应该正常加载', async ({ page }) => {
    // 检查是否有关键的 CSS/JS 加载失败
    const failedResources: string[] = [];

    page.on('requestfailed', request => {
      if (request.resourceType() === 'stylesheet' ||
          request.resourceType() === 'script') {
        failedResources.push(request.url());
      }
    });

    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    expect(failedResources).toHaveLength(0);
  });

  test('应该没有控制台错误', async ({ page }) => {
    const consoleErrors: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // 过滤掉一些已知的无关错误
    const criticalErrors = consoleErrors.filter(error =>
      !error.includes('favicon') &&
      !error.includes('analytics')
    );

    expect(criticalErrors).toHaveLength(0);
  });
});

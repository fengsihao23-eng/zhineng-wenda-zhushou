import { test, expect } from '@playwright/test';

test('简单验证 - 访问登录页', async ({ page }) => {
  await page.goto('/login');

  await expect(page.locator('h1')).toContainText('智能问答助手', { timeout: 10000 });
  await expect(page.locator('input#username')).toBeVisible();
  await expect(page.locator('input#password')).toBeVisible();
});

test('简单验证 - 健康检查', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.ok()).toBeTruthy();
  expect(response.status()).toBe(200);
});

test('简单验证 - 登录流程', async ({ page }) => {
  await page.goto('/login');

  await page.fill('input#username', 'student_basic');
  await page.fill('input#password', 'password123');
  await page.click('button[type="submit"]');

  // 等待离开登录页
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 10000 });

  // 验证登录成功
  await expect(page.locator('body')).not.toContainText('登录失败');
});

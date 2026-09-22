import { test, expect } from './fixtures/auth-fixture';
import { LoginPage } from './pages/LoginPage';
import { TEST_USERS } from './fixtures/test-users';

/**
 * 认证流程测试
 * 覆盖：登录、登出、token刷新、无效凭据
 */

test.describe('认证流程', () => {
  test('应该成功登录 BASIC 学生账号', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.login(TEST_USERS.STUDENT_BASIC.username, TEST_USERS.STUDENT_BASIC.password);

    // 验证已离开登录页（学生首页路径为 /）
    await expect(page).not.toHaveURL(/\/login/);

    // 验证用户信息显示
    await expect(page.locator('body')).toContainText(TEST_USERS.STUDENT_BASIC.displayName, { timeout: 10000 });
  });

  test('应该成功登录 DIAGNOSIS 学生账号', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.login(TEST_USERS.STUDENT_DIAGNOSIS.username, TEST_USERS.STUDENT_DIAGNOSIS.password);

    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.locator('body')).toContainText(TEST_USERS.STUDENT_DIAGNOSIS.displayName, { timeout: 10000 });
  });

  test('应该成功登录教师账号', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.login(TEST_USERS.TEACHER.username, TEST_USERS.TEACHER.password);

    // 教师登录后由 HomeRedirect 渲染工作台，URL 仍为 /
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.locator('body')).toContainText('教师工作台', { timeout: 10000 });
  });

  test('应该拒绝无效凭据', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.login('invalid_user', 'wrong_password');

    // 验证错误消息显示
    await expect(loginPage.errorMessage).toBeVisible({ timeout: 5000 });

    const errorText = await loginPage.getErrorMessage();
    expect(errorText).toMatch(/登录失败|用户名或密码错误|认证失败/i);

    // 验证仍在登录页
    await expect(page).toHaveURL(/\/login/);
  });

  test('应该在未登录时重定向到登录页', async ({ page }) => {
    await page.goto('/chat');

    // 验证重定向到登录页
    await expect(page).toHaveURL(/\/login/);
  });

  test('应该成功登出', async ({ authenticatedPage }) => {
    await authenticatedPage.getByTitle('退出登录').click();
    await expect(authenticatedPage).toHaveURL(/\/login$/);
    expect(await authenticatedPage.evaluate(() => sessionStorage.getItem('refresh_token'))).toBeNull();

  });

  test('应该在 token 过期后自动刷新', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(TEST_USERS.STUDENT_BASIC.username, TEST_USERS.STUDENT_BASIC.password);

    // 等待登录成功
    await expect(page).not.toHaveURL(/\/login/);

    // 导航到不同页面，触发 API 调用
    const refreshed = page.waitForResponse(response => response.url().endsWith('/auth/refresh') && response.ok());
    await page.goto('/trends');
    expect((await refreshed).status()).toBe(200);
    await page.waitForLoadState('networkidle');

    // 验证页面正常加载（token 刷新成功）
    await expect(page.locator('body')).not.toContainText('登录失败');
    await expect(page).toHaveURL(/\/trends/);
  });
});

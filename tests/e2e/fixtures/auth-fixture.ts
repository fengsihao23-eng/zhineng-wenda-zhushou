import { test as base, Page } from '@playwright/test';
import { TEST_USERS, TestUser } from './test-users';
import { LoginPage } from '../pages/LoginPage';

/**
 * 认证状态管理 Fixture
 * 提供已登录的 Page 对象，避免每个测试重复登录
 */

type AuthFixtures = {
  authenticatedPage: Page;
  studentBasicPage: Page;
  studentDiagnosisPage: Page;
  teacherPage: Page;
};

/**
 * 登录辅助函数
 */
export async function loginAs(page: Page, user: TestUser): Promise<void> {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login(user.username, user.password);

  // 等待登录成功并跳转。原正则过于宽松，会立即匹配 /login 本身，
  // 导致后续断言在登录完成前就执行。这里等待离开登录页。
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 10000 });
}

/**
 * 扩展 Playwright test，添加认证 fixtures
 */
export const test = base.extend<AuthFixtures>({
  /**
   * 通用认证页面 - 使用 BASIC 学生登录
   */
  authenticatedPage: async ({ browser, baseURL }, use) => {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();

    await loginAs(page, TEST_USERS.STUDENT_BASIC);

    await use(page);

    await context.close();
  },

  /**
   * BASIC 权益学生页面
   */
  studentBasicPage: async ({ browser, baseURL }, use) => {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();

    await loginAs(page, TEST_USERS.STUDENT_BASIC);

    await use(page);

    await context.close();
  },

  /**
   * DIAGNOSIS 权益学生页面
   */
  studentDiagnosisPage: async ({ browser, baseURL }, use) => {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();

    await loginAs(page, TEST_USERS.STUDENT_DIAGNOSIS);

    await use(page);

    await context.close();
  },

  /**
   * 教师页面
   */
  teacherPage: async ({ browser, baseURL }, use) => {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();

    await loginAs(page, TEST_USERS.TEACHER);

    await use(page);

    await context.close();
  },
});

export { expect } from '@playwright/test';

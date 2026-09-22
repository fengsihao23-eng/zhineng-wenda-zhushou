import { test, expect } from './fixtures/auth-fixture';
import { TrendsPage } from './pages/TrendsPage';

/**
 * 数据可视化测试
 * 覆盖：图表渲染、交互、响应式布局
 */

test.describe('数据可视化', () => {
  test('应该渲染成绩趋势图表', async ({ studentBasicPage }) => {
    const trendsPage = new TrendsPage(studentBasicPage);
    await trendsPage.goto();

    // 验证图表容器存在
    const hasChart = await trendsPage.hasChart();
    expect(hasChart).toBeTruthy();
  });

  test('应该展示考试历史列表', async ({ studentBasicPage }) => {
    const trendsPage = new TrendsPage(studentBasicPage);
    await trendsPage.goto();

    const examCount = await trendsPage.getExamCount();

    // 种子数据固定为两次考试
    expect(examCount).toBe(2);
  });

  test('应该展示科目趋势', async ({ studentBasicPage }) => {
    const trendsPage = new TrendsPage(studentBasicPage);
    await trendsPage.goto();

    const subjectCount = await trendsPage.getSubjectCount();

    expect(subjectCount).toBe(5);
  });

  test('图表应该在移动端正确渲染', async ({ browser, baseURL }) => {
    const context = await browser.newContext({
      baseURL,
      viewport: { width: 375, height: 667 }, // iPhone 尺寸
    });
    const page = await context.newPage();

    // 登录
    await page.goto('/login');
    await page.fill('input#username', 'student_basic');
    await page.fill('input#password', 'password123');
    await page.click('button[type="submit"]');
    await page.waitForURL(url => !url.pathname.startsWith('/login'));

    // 访问趋势页
    await page.goto('/trends');
    await page.waitForLoadState('networkidle');

    // 验证图表存在且可见
    const chart = page.locator('.line-chart, [data-testid="chart"]');
    await expect(chart).toBeVisible({ timeout: 10000 });

    await context.close();
  });
});

import { test, expect } from './fixtures/auth-fixture';
import { DashboardPage } from './pages/DashboardPage';

/**
 * 成绩查询测试
 * 覆盖：成绩展示、权限隔离、数据访问边界
 */

test.describe('成绩查询功能', () => {
  test('BASIC 学生应该能看到仪表盘数据', async ({ studentBasicPage }) => {
    const dashboard = new DashboardPage(studentBasicPage);
    await dashboard.goto();

    // 验证页面加载成功
    await expect(studentBasicPage).toHaveURL('/');

    // 验证核心统计卡片存在
    await expect(dashboard.latestExamScore).toBeVisible({ timeout: 10000 });
    await expect(dashboard.classRank).toBeVisible();
  });

  test('应该展示最近考试成绩', async ({ studentBasicPage }) => {
    const dashboard = new DashboardPage(studentBasicPage);
    await dashboard.goto();

    // 获取最新成绩
    const score = await dashboard.getLatestScore();

    // 验证成绩格式（可能是 "XX 分" 或 "—"）
    expect(score).toBe('603 分');
  });

  test('应该展示班级排名', async ({ studentBasicPage }) => {
    const dashboard = new DashboardPage(studentBasicPage);
    await dashboard.goto();

    const rank = await dashboard.getClassRank();

    // 验证排名格式
    expect(rank).toBe('第 15 名');
  });

  test('应该展示科目成绩列表', async ({ studentBasicPage }) => {
    const dashboard = new DashboardPage(studentBasicPage);
    await dashboard.goto();

    const subjectCount = await dashboard.getSubjectCount();

    // 测试账号有五科成绩，缺失任一科都会失败
    expect(subjectCount).toBe(5);
  });

  test('应该能导航到成绩趋势页', async ({ studentBasicPage }) => {
    await studentBasicPage.goto('/trends');

    // 验证页面加载
    await expect(studentBasicPage).toHaveURL('/trends');

    // 验证关键元素
    await expect(studentBasicPage.locator('body')).toContainText('成绩趋势', { timeout: 10000 });
  });

  test('应该能查看错题分析', async ({ studentBasicPage }) => {
    await studentBasicPage.goto('/mistakes');

    await expect(studentBasicPage).toHaveURL('/mistakes');
    await expect(studentBasicPage.locator('body')).toContainText('错题分析', { timeout: 10000 });
  });

  test('BASIC 学生不应该看到其他学生数据', async ({ studentBasicPage }) => {
    const dashboard = new DashboardPage(studentBasicPage);
    await dashboard.goto();

    // 验证欢迎消息包含当前学生信息
    const welcome = await dashboard.getWelcomeMessage();

    // 不应该包含其他测试学生的名字
    expect(welcome).toContain('张三');
    expect(welcome).not.toContain('李四');
    expect(welcome).not.toContain('教师工作台');
  });

  test('无考试响应显示等待接入和空状态', async ({ studentBasicPage: page }) => {
    await page.route('**/platform/student/dashboard', async route => {
      const response = await route.fetch();
        if (!response.ok()) { await route.fulfill({ response }); return; }
      const json = await response.json();
      await route.fulfill({ response, json: { ...json, latest_exam: null, exam_count: 0, subjects: [] } });
    });
    await page.goto('/');
    await expect(page.locator('.score-hero')).toHaveCount(0);
    await expect(page.locator('.subject-card')).toHaveCount(0);
    await expect(page.locator('.workspace-main')).toContainText('等待成绩数据接入');
    await expect(page.locator('.workspace-main')).toContainText('暂无科目成绩');
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  test('完整刷新后成绩数据保持正确', async ({ studentBasicPage }) => {
    const dashboard = new DashboardPage(studentBasicPage);
    await dashboard.goto();

    // 获取初始数据
    const initialScore = await dashboard.getLatestScore();

    // 刷新页面
    await studentBasicPage.reload();
    await studentBasicPage.waitForLoadState('networkidle');

    // 验证数据一致性
    const refreshedScore = await dashboard.getLatestScore();
    expect(refreshedScore).toBe(initialScore);
  });
});

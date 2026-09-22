import { test, expect, loginAs } from './fixtures/auth-fixture';
import { TEST_USERS } from './fixtures/test-users';

// 故障注入不改真实业务记录；列表恢复使用真实 API。
test.describe('统一错误处理', () => {
  test('管理学生列表断网后显示统一错误并可重试', async ({ teacherPage: page }) => {
    await page.route('**/platform/management/students', route => route.abort('failed'));
    await page.goto('/teacher/students');
    await expect(page.getByRole('alert')).toContainText('网络连接失败');
    await page.unroute('**/platform/management/students');
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect(page.locator('.data-table tbody tr')).toHaveCount(2);
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  test('管理操作失败就地显示提示，保留表单且没有 alert 弹窗', async ({ page }) => {
    const dialogs: string[] = [];
    page.on('dialog', dialog => { dialogs.push(dialog.type()); void dialog.dismiss(); });
    await loginAs(page, TEST_USERS.SCHOOL_ADMIN);
    await page.goto('/admin/knowledge');
    await page.getByRole('button', { name: '+ 新建文档', exact: true }).click();
    await page.getByLabel('文档标题').fill('故障注入测试');
    await page.getByLabel('来源名称').fill('测试教研组');
    await page.getByLabel('来源引用').fill('测试文件第1页');
    await page.getByLabel('正文内容').fill('测试内容，不写入数据库');
    await page.route('**/platform/management/knowledge', route => route.request().method() === 'POST'
      ? route.fulfill({ status: 403, json: { error: { code: 'FORBIDDEN', message: '当前账号不能新建文档' } } })
      : route.continue());
    await page.getByRole('button', { name: '保存草稿', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('当前账号不能新建文档');
    await expect(page.getByLabel('文档标题')).toHaveValue('故障注入测试');
    expect(dialogs).toEqual([]);
  });

  test('支持页提交失败显示错误，320px 下提示与重试按钮不溢出', async ({ studentBasicPage: page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto('/support');
    await page.route('**/platform/student/feedback', route => route.abort('failed'));
    await page.getByRole('button', { name: '提交反馈', exact: true }).click();
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('网络连接失败');
    const dimensions = await alert.evaluate(el => ({ width: el.clientWidth, scroll: el.scrollWidth, right: el.getBoundingClientRect().right }));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1);
    expect(dimensions.right).toBeLessThanOrEqual(321);
  });

  test('渲染异常由 ErrorBoundary 显示可恢复提示', async ({ studentBasicPage: page }) => {
    await page.route('**/platform/student/dashboard', route => route.fulfill({ json: { student: null, subjects: [] } }));
    await page.goto('/profile');
    await expect(page.getByRole('alert')).toContainText('页面暂时无法显示，请重试');
    await page.unroute('**/platform/student/dashboard');
    // 清除故障注入响应的缓存，完整重载后应正常显示。
    await page.reload();
    await expect(page.locator('.score-number')).toHaveText('603/ 750');
  });
});

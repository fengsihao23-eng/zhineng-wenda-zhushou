import { test, expect } from './fixtures/auth-fixture';
import { ChatPage } from './pages/ChatPage';
import { mockChatReply } from './utils/chat-stream';

test.describe('诊断报告真实数据与浏览器呈现', () => {
  test('DIAGNOSIS 学生显示服务端返回的报告及来源', async ({ studentDiagnosisPage: page }) => {
    const response = page.waitForResponse(res => res.url().endsWith('/platform/student/diagnosis') && res.ok());
    await page.goto('/diagnosis');
    const reports = await (await response).json();
    expect(reports.length).toBeGreaterThan(0);
    await expect(page.locator('.report-card')).toHaveCount(reports.length);
    await expect(page.locator('.report-summary').first()).toHaveText(reports[0].content.summary);
    await expect(page.locator('.report-card__meta').first()).toContainText(reports[0].source);
    const help = page.locator('details.help-tip').filter({ has: page.locator('summary', { hasText: '报告说明' }) });
    await help.locator('summary').click();
    await expect(page.getByRole('note', { name: '报告说明', exact: true })).toBeVisible();
    await expect(page.getByRole('note', { name: '报告说明', exact: true })).toContainText('诊断结论来自正式报告');
  });

  test('BASIC 账号缺少诊断授权时，接口拒绝访问且页面显示授权提示', async ({ studentBasicPage: page }) => {
    const response = page.waitForResponse(res => res.url().endsWith('/platform/student/diagnosis'));
    await page.goto('/diagnosis');
    const denied = await response;
    expect(denied.status()).toBe(403);
    expect((await denied.json()).error.code).toBe('ENTITLEMENT_REQUIRED');
    await expect(page.getByRole('alert')).toContainText('当前没有有效的诊断报告授权，请联系学校确认。');
    await expect(page.locator('.report-card')).toHaveCount(0);
    await expect(page.locator('.empty-state')).toHaveCount(0);
  });

  test('已授权账号没有报告时显示空状态（受控空列表）', async ({ studentDiagnosisPage: page }) => {
    await page.route('**/platform/student/diagnosis', route => route.fulfill({ json: [] }));
    await page.goto('/diagnosis');
    await expect(page.locator('.empty-state')).toBeVisible();
    await expect(page.locator('.report-card')).toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  for (const role of ['basic', 'diagnosis'] as const) {
    test(`${role} 账号首页报告数量与列表一致`, async ({ studentBasicPage, studentDiagnosisPage }) => {
      const page = role === 'basic' ? studentBasicPage : studentDiagnosisPage;
      const value = page.locator('.stat-card:has-text("诊断报告") .stat-card__value');
      await expect(value).toHaveText(role === 'basic' ? '0' : '1');
      const count = Number(await value.textContent());
      await page.locator('.side-nav a[href="/diagnosis"]').click();
      if (role === 'basic') {
        await expect(page.getByRole('alert')).toContainText('当前没有有效的诊断报告授权');
      } else {
        await expect(page.locator('.report-card')).toBeVisible();
      }
      await expect(page.locator('.report-card')).toHaveCount(count);
    });
  }

  test('报告关联服务端返回的考试与版本', async ({ studentDiagnosisPage: page }) => {
    const response = page.waitForResponse(res => res.url().endsWith('/platform/student/diagnosis') && res.ok());
    await page.goto('/diagnosis');
    const [report] = await (await response).json();
    expect(report.exam_name).toBeTruthy();
    await expect(page.locator('.report-card h2').first()).toHaveText(report.exam_name);
    await expect(page.locator('.citation-row').first()).toContainText(report.id.slice(0, 8));
  });

  test('诊断加载失败时有中文提示和重试入口', async ({ studentDiagnosisPage: page }) => {
    await page.route('**/platform/student/diagnosis', route => route.abort('failed'));
    await page.goto('/diagnosis');
    await expect(page.getByRole('alert')).toContainText('网络连接失败');
    await page.unroute('**/platform/student/diagnosis');
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect(page.locator('.report-card')).toHaveCount(1);
  });

  // 受控 SSE 仅验证回复展示；真实权益隔离由后端权限测试负责。
  test('浏览器显示诊断解释回复（受控 SSE）', async ({ studentDiagnosisPage: page }) => {
    await mockChatReply(page, '诊断报告显示数学较稳定，建议复盘物理。');
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('我的诊断报告显示了什么？');
    await chat.waitForResponse();
    expect(await chat.getLastMessage()).toBe('诊断报告显示数学较稳定，建议复盘物理。');
  });

  test('浏览器显示权益提示回复（受控 SSE）', async ({ studentBasicPage: page }) => {
    await mockChatReply(page, '查看诊断报告需要 DIAGNOSIS 权益。');
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('我的诊断报告在哪里？');
    await chat.waitForResponse();
    expect(await chat.getLastMessage()).toBe('查看诊断报告需要 DIAGNOSIS 权益。');
  });
});

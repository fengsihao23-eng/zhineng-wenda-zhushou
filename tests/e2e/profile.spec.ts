import { test, expect, loginAs } from './fixtures/auth-fixture';
import { TEST_USERS } from './fixtures/test-users';

test.describe('成绩概览页 /profile', () => {
  for (const { user, score, percentage } of [
    { user: TEST_USERS.STUDENT_BASIC, score: 603, percentage: '80.4%' },
    { user: TEST_USERS.STUDENT_DIAGNOSIS, score: 664, percentage: '88.5%' },
  ]) {
    test(`真实登录 ${user.displayName} 显示本人总分与全部科目`, async ({ page }) => {
      await loginAs(page, user);
      const response = await page.goto('/profile');
      expect(response?.status()).toBe(200);
      await expect(page.locator('.profile-header h1')).toHaveText(user.displayName);
      await expect(page.locator('.score-number')).toHaveText(`${score}/ 750`);
      await expect(page.locator('.score-percentage')).toHaveText(percentage);
      await expect(page.locator('.subject-item')).toHaveCount(5);
      await expect(page.locator('.profile-subtitle')).toContainText('2 次考试');
      await expect(page.locator('.trend-chart .recharts-line-curve')).toHaveCount(2);
      await expect(page.locator('.subject-radar .recharts-radar-polygon')).toBeVisible();
      await expect(page.locator('.profile-container')).not.toContainText(/Infinity|NaN|Failed to fetch/);
    });
  }

  test('同标签页退出并切换账号后，侧栏导航不复用上一个账号的成绩', async ({ page }) => {
    await loginAs(page, TEST_USERS.STUDENT_DIAGNOSIS);
    await page.locator('.side-nav a[href="/profile"]').click();
    await expect(page.locator('.profile-header h1')).toHaveText('李四');
    await expect(page.locator('.score-number')).toHaveText('664/ 750');
    // 标记确保切换流程没有完整导航，避免重载清缓存而假通过。
    await page.evaluate(() => { document.documentElement.dataset.accountSwitch = 'same-document'; });
    await page.getByTitle('退出登录').click();
    await expect(page).toHaveURL(/\/login$/);
    const nextDashboard = page.waitForResponse(response =>
      response.url().endsWith('/platform/student/dashboard') && response.ok());
    await page.locator('#username').fill(TEST_USERS.STUDENT_BASIC.username);
    await page.locator('#password').fill(TEST_USERS.STUDENT_BASIC.password);
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await expect(page).toHaveURL('/');
    expect((await (await nextDashboard).json()).student.name).toBe('张三');
    await page.locator('.side-nav a[href="/profile"]').click();
    await expect(page.locator('.profile-header h1')).toHaveText('张三');
    await expect(page.locator('.score-number')).toHaveText('603/ 750');
    await expect(page.locator('.profile-container')).not.toContainText('李四');
    await expect(page.locator('html')).toHaveAttribute('data-account-switch', 'same-document');
  });

  test('雷达轴线透明，趋势图分别使用分数轴和百分比轴', async ({ studentBasicPage: page }) => {
    await page.goto('/profile');
    const radar = page.locator('.recharts-polar-angle-axis-line');
    await expect(radar).toBeVisible();
    expect(await radar.evaluate(el => getComputedStyle(el).fill)).toBe('none');
    await expect(page.locator('.subject-radar .recharts-radar-polygon')).toBeVisible();
    const axes = page.locator('.trend-chart .recharts-yAxis');
    await expect(axes).toHaveCount(2);
    // Recharts 3 将刻度标签放在独立图层，不能从轴线的父组查文本。
    const labels = page.locator('.trend-chart .recharts-yAxis-tick-labels');
    await expect(labels.filter({ hasText: '%' })).toHaveCount(1);
    await expect(labels.filter({ hasText: '%' })).toContainText('100%');
    await expect(page.locator('.trend-chart .recharts-line-curve')).toHaveCount(2);
    const rightAxis = axes.locator('.recharts-cartesian-axis-line[orientation="right"]');
    const top = Number(await rightAxis.getAttribute('y1'));
    const bottom = Number(await rightAxis.getAttribute('y2'));
    const lastPercentage = page.locator('.trend-chart circle[fill="#10b981"]').last();
    expect(Number(await lastPercentage.getAttribute('cy'))).toBeCloseTo(bottom - (bottom - top) * 0.804, 1);
  });

  for (const fullScore of [null, 0, -1]) {
    test(`满分为 ${fullScore} 时总分、科目、趋势不计算无效百分比`, async ({ studentBasicPage: page }) => {
      await page.route('**/platform/student/dashboard', async route => {
        const response = await route.fetch();
        if (!response.ok()) { await route.fulfill({ response }); return; }
        const json = await response.json();
        json.latest_exam.full_score = fullScore;
        json.subjects = json.subjects.map((subject: Record<string, unknown>) => ({ ...subject, full_score: fullScore, percentage: null }));
        await route.fulfill({ response, json });
      });
      await page.route('**/platform/student/trends', async route => {
        const response = await route.fetch();
        if (!response.ok()) { await route.fulfill({ response }); return; }
        const json = await response.json();
        json.exams = json.exams.map((exam: Record<string, unknown>) => ({ ...exam, full_score: fullScore }));
        await route.fulfill({ response, json });
      });
      await page.goto('/profile');
      await expect(page.locator('.score-percentage')).toHaveText('—');
      await expect(page.locator('.score-total')).toHaveText('/ —');
      await expect(page.locator('.subject-item')).toHaveCount(5);
      await expect(page.locator('.subject-item__meta').first()).toContainText('—');
      await expect(page.locator('.profile-container')).not.toContainText(/Infinity|NaN|\/\s*-?0\b|\/\s*-1\b/);
      await expect(page.locator('.trend-chart .recharts-line-curve')).toHaveCount(1);
      await expect(page.locator('.subject-radar')).toContainText('科目满分待补充');
      await expect(page.locator('.recharts-radar-polygon')).toHaveCount(0);
    });
  }

  test('断网显示中文错误，恢复后可通过重试加载成绩', async ({ studentBasicPage: page }) => {
    await page.route('**/platform/student/dashboard', route => route.abort('failed'));
    await page.goto('/profile');
    await expect(page.getByRole('alert')).toContainText(/网络.*(失败|检查|连接)/);
    await expect(page.getByRole('alert')).not.toContainText('Failed to fetch');
    await expect(page.locator('.score-number')).toHaveCount(0);
    await page.unroute('**/platform/student/dashboard');
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect(page.locator('.score-number')).toHaveText('603/ 750');
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  test('概览样式加载后返回首页，五个进度条仍为 5px', async ({ studentBasicPage: page }) => {
    await page.locator('.side-nav a[href="/profile"]').click();
    await expect(page.locator('.score-number')).toBeVisible();
    await page.locator('.side-nav a[href="/"]').click();
    const bars = page.locator('.subject-card .progress-bar');
    await expect(bars).toHaveCount(5);
    const heights = await bars.evaluateAll(elements => elements.map(el => parseFloat(getComputedStyle(el).height)));
    expect(heights).toEqual([5, 5, 5, 5, 5]);
  });

  for (const width of [320, 375, 390, 768]) {
    test(`${width}px 初始视口下内容与图表不横向溢出`, async ({ browser, baseURL }) => {
      const context = await browser.newContext({ baseURL, viewport: { width, height: 900 } });
      try {
        const page = await context.newPage();
        await loginAs(page, TEST_USERS.STUDENT_BASIC);
        await page.goto('/profile');
        await expect(page.locator('.score-number')).toHaveText('603/ 750');
        await expect(page.locator('.subject-radar .recharts-radar-polygon')).toBeVisible();
        await expect(page.locator('.trend-chart .recharts-line-curve')).toHaveCount(2);
        const lengths = await page.locator('.trend-chart .recharts-line-curve').evaluateAll(elements => elements.map(el => (el as SVGPathElement).getTotalLength()));
        lengths.forEach(length => expect(length).toBeGreaterThan(20));
        // 等待 CSS 动画稳定；根元素 overflow-x 会掩盖内容溢出，需逐容器检查。
        await page.evaluate(async () => {
          await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined)));
          await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        });
        const boxes = await page.locator('html, .app-main, .workspace-main, .profile-container, .profile-grid, .score-card, .trend-chart, .subject-radar').evaluateAll(elements => elements.map(el => ({
          name: el.className || el.tagName, width: el.clientWidth,
          overflow: el.scrollWidth - el.clientWidth, right: el.getBoundingClientRect().right,
        })));
        for (const box of boxes) {
          expect(box.width, `${box.name} 有实际内容宽度`).toBeGreaterThan(0);
          expect(box.overflow, `${width}px: ${box.name} 内部溢出`).toBeLessThanOrEqual(1);
          expect(box.right, `${width}px: ${box.name} 超出视口`).toBeLessThanOrEqual(width + 1);
        }
      } finally { await context.close(); }
    });
  }
});

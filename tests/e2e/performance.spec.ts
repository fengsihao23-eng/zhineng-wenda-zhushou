import { test, expect } from './fixtures/auth-fixture';
import { ChatPage } from './pages/ChatPage';
import { STREAM_ROUTE, streamBody } from './utils/chat-stream';

test.describe('性能与稳定性', () => {
  test('生产首页实际成绩在 2000ms 内首次可见', async ({ studentBasicPage: page }) => {
    const client = await page.context().newCDPSession(page);
    await client.send('Network.enable');
    await client.send('Network.setCacheDisabled', { cacheDisabled: true });
    await page.addInitScript(() => {
      const observe = () => {
        const content = document.querySelector('.score-hero__number');
        if (content?.textContent?.includes('603') && content.getBoundingClientRect().width > 0) {
          document.documentElement.dataset.firstScoreMs = String(performance.now());
        } else { requestAnimationFrame(observe); }
      };
      requestAnimationFrame(observe);
    });
    const response = await page.goto('/');
    const html = await response!.text();
    expect(html).toContain('/assets/');
    expect(html).not.toContain('/@vite/client');
    await page.waitForFunction(() => !!document.documentElement.dataset.firstScoreMs);
    const elapsed = await page.evaluate(() => Number(document.documentElement.dataset.firstScoreMs));
    expect(elapsed).toBeLessThan(2000);
  });

  test('生产 /profile 禁用缓存完整导航 5 次，成绩与图表首次可见均小于 2000ms', async ({ studentBasicPage: page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const client = await page.context().newCDPSession(page);
    await client.send('Network.enable');
    await client.send('Network.setCacheDisabled', { cacheDisabled: true });
    await page.addInitScript(() => {
      const observe = () => {
        const score = document.querySelector('.score-number');
        const line = document.querySelector<SVGPathElement>('.trend-chart .recharts-line-curve');
        const radar = document.querySelector('.subject-radar .recharts-radar-polygon');
        const visible = (element: Element | null) => {
          const bounds = element?.getBoundingClientRect();
          return bounds && bounds.width > 0 && bounds.top < innerHeight && bounds.bottom > 0 && bounds.left < innerWidth;
        };
        if (score?.textContent?.includes('603') && visible(score) && line?.getTotalLength() && visible(line) && visible(radar)) {
          document.documentElement.dataset.firstProfileMs = String(performance.now());
        } else { requestAnimationFrame(observe); }
      };
      requestAnimationFrame(observe);
    });
    const measurements: number[] = [];
    for (let sample = 0; sample < 5; sample++) {
      const response = await page.goto('/profile');
      expect(response?.status()).toBe(200);
      const html = await response!.text();
      expect(html).toContain('/assets/');
      expect(html).not.toContain('/@vite/client');
      await page.waitForFunction(() => !!document.documentElement.dataset.firstProfileMs, null, { timeout: 5000 });
      measurements.push(await page.evaluate(() => Number(document.documentElement.dataset.firstProfileMs)));
    }
    await testInfo.attach('profile-first-content-ms', {
      contentType: 'application/json',
      body: JSON.stringify({ url: page.url(), httpCache: 'disabled', viewport: page.viewportSize(), thresholdMs: 2000, measurements }, null, 2),
    });
    measurements.forEach((elapsed, sample) => expect(elapsed, `第 ${sample + 1} 次首屏成绩和图表`).toBeLessThan(2000));
  });

  test('聊天页在 5 秒内显示可用输入框', async ({ authenticatedPage: page }) => {
    const start = Date.now();
    await page.goto('/chat');
    await expect(page.locator('.input-box textarea')).toBeEnabled();
    expect(Date.now() - start).toBeLessThan(5000);
  });

  test('登录请求断网时显示中文提示并保留登录表单', async ({ page }) => {
    await page.goto('/login');
    await page.route('**/auth/login', route => route.abort('failed'));
    await page.locator('#username').fill('student_basic');
    await page.locator('#password').fill('password123');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText(/网络.*(连接|检查|失败)/);
    await expect(page.getByRole('alert')).not.toContainText('Failed to fetch');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator('#username')).toBeEnabled();
  });

  test('流请求等待时阻止重复发送，并能主动停止', async ({ authenticatedPage: page }) => {
    let requests = 0;
    await page.route(STREAM_ROUTE, async route => {
      requests += 1;
      // 保持请求未返回，由浏览器停止按钮中止；用例结束解除路由。
      await new Promise<void>(resolve => page.once('close', () => resolve()));
      await route.abort().catch(() => undefined);
    });
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('慢请求');
    await expect(chat.messageInput).toBeDisabled();
    await expect(chat.sendButton).toBeDisabled();
    await page.getByRole('button', { name: '停止', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('已停止生成');
    await expect(chat.messageInput).toBeEnabled();
    expect(requests).toBe(1);
  });

  test('侧栏快速切换后支持页完整可用且没有未捕获错误', async ({ studentBasicPage: page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const path of ['/profile', '/trends', '/diagnosis', '/mistakes', '/support']) {
      await page.locator(`.side-nav a[href="${path}"]`).click();
    }
    await expect(page).toHaveURL('/support');
    await expect(page.getByRole('heading', { name: '家长与支持', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '生成授权申请' })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('连续三轮请求各获得对应回复', async ({ authenticatedPage: page }) => {
    let requests = 0;
    await page.route(STREAM_ROUTE, route => route.fulfill({ contentType: 'text/event-stream', body: streamBody(`回复 ${++requests}`) }));
    const chat = new ChatPage(page);
    await chat.goto();
    for (let index = 1; index <= 3; index++) {
      await chat.sendMessage(`测试消息 ${index}`);
      await chat.waitForResponse();
    }
    await expect(page.locator('.message--user')).toHaveCount(3);
    await expect(page.locator('.message--assistant .message__text')).toHaveText(['回复 1', '回复 2', '回复 3']);
    expect(requests).toBe(3);
  });
});

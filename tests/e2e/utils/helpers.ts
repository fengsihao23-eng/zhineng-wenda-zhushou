/**
 * E2E 测试工具函数
 */

import { Page } from '@playwright/test';

/**
 * 等待 API 请求完成
 */
export async function waitForApiRequest(
  page: Page,
  urlPattern: string | RegExp,
  timeout: number = 10000
): Promise<void> {
  await page.waitForResponse(
    response => {
      const url = response.url();
      const matches = typeof urlPattern === 'string'
        ? url.includes(urlPattern)
        : urlPattern.test(url);
      return matches && response.status() === 200;
    },
    { timeout }
  );
}

/**
 * 截取页面截图（用于调试）
 */
export async function takeDebugScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({
    path: `test-results/debug-${name}-${Date.now()}.png`,
    fullPage: true,
  });
}

/**
 * 检查控制台错误
 */
export function setupConsoleErrorHandler(page: Page): string[] {
  const errors: string[] = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('pageerror', error => {
    errors.push(error.message);
  });

  return errors;
}

/**
 * 等待 SSE 事件流
 */
export async function waitForSSEConnection(
  page: Page,
  timeout: number = 10000
): Promise<void> {
  await page.waitForResponse(
    response => {
      const contentType = response.headers()['content-type'] || '';
      return contentType.includes('text/event-stream');
    },
    { timeout }
  );
}

/**
 * 清除浏览器存储
 */
export async function clearBrowserStorage(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
}

/**
 * 获取 LocalStorage 的值
 */
export async function getLocalStorageItem(page: Page, key: string): Promise<string | null> {
  return await page.evaluate((k) => localStorage.getItem(k), key);
}

/**
 * 设置 LocalStorage 的值
 */
export async function setLocalStorageItem(page: Page, key: string, value: string): Promise<void> {
  await page.evaluate(
    ({ k, v }) => localStorage.setItem(k, v),
    { k: key, v: value }
  );
}

/**
 * 模拟网络条件
 */
export async function simulateSlowNetwork(page: Page): Promise<void> {
  const client = await page.context().newCDPSession(page);
  await client.send('Network.emulateNetworkConditions', {
    offline: false,
    downloadThroughput: 50 * 1024, // 50KB/s
    uploadThroughput: 20 * 1024,   // 20KB/s
    latency: 500,                   // 500ms
  });
}

/**
 * 等待元素文本包含特定内容
 */
export async function waitForTextContent(
  page: Page,
  selector: string,
  text: string | RegExp,
  timeout: number = 10000
): Promise<void> {
  await page.waitForFunction(
    ({ sel, txt }) => {
      const element = document.querySelector(sel);
      if (!element) return false;

      const content = element.textContent || '';
      return typeof txt === 'string'
        ? content.includes(txt)
        : txt.test(content);
    },
    { sel: selector, txt: text },
    { timeout }
  );
}

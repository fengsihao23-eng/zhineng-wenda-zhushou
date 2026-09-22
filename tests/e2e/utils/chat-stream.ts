import { Page } from '@playwright/test';

export const STREAM_ROUTE = '**/chat/sessions/*/stream';

export function streamBody(content: string, complete = true, source?: Record<string, unknown>): string {
  const events: Array<[string, Record<string, unknown>]> = [
    ['message_start', {}], ['content_delta', { content }],
  ];
  if (source) events.push(['source', source]);
  if (complete) events.push(['message_end', { message_id: `e2e-assistant-${content}` }], ['done', {}]);
  return events.map(([event, data], index) => `event: ${event}\ndata: ${JSON.stringify({ request_id: 'e2e-stream', seq: index + 1, data })}\n\n`).join('');
}

// 仅替换消息流，登录、会话创建/查询/结束及成绩权限仍访问真实服务。
// 这些用例验证浏览器流协议/UI，不声称验证真实模型或工具选择。
export async function mockChatReply(page: Page, content: string, source?: Record<string, unknown>) {
  await page.route(STREAM_ROUTE, route => route.fulfill({
    status: 200, contentType: 'text/event-stream', body: streamBody(content, true, source),
  }));
}

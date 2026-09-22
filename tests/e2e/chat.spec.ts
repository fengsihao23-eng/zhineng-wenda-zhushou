import { test, expect } from './fixtures/auth-fixture';
import { ChatPage } from './pages/ChatPage';
import { mockChatReply, STREAM_ROUTE, streamBody } from './utils/chat-stream';

test.describe('智能问答浏览器流程（受控 SSE；真实会话 API）', () => {
  test('发送消息并显示流式助手回复', async ({ authenticatedPage: page }) => {
    await mockChatReply(page, '你好，可以帮你了解学习情况。');
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('你好');
    await chat.waitForResponse();
    await expect(page.locator('.message--user .message__text')).toHaveText('你好');
    expect(await chat.getLastMessage()).toBe('你好，可以帮你了解学习情况。');
  });

  test('显示成绩回复及对应数据来源', async ({ studentBasicPage: page }) => {
    await mockChatReply(page, '最近一次考试总分为 603 分。', { label: '最近一次考试成绩', id: 'score-source', as_of: '2026-09-16' });
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('我最近一次考试成绩怎么样？');
    await chat.waitForResponse();
    await expect(page.locator('.message--assistant .message__text')).toHaveText('最近一次考试总分为 603 分。');
    await expect(page.locator('.message__source')).toContainText('最近一次考试成绩');
    await expect(page.locator('.message__source')).toContainText('2026-09-16');
  });

  test('科目回复不把用户问题误判为助手答案', async ({ studentBasicPage: page }) => {
    await mockChatReply(page, '数学成绩为 135 分，得分率 90%。');
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('我的数学成绩表现如何？');
    await chat.waitForResponse();
    expect(await chat.getLastMessage()).toBe('数学成绩为 135 分，得分率 90%。');
  });

  test('同一会话两轮问答各显示用户消息和助手回复', async ({ authenticatedPage: page }) => {
    let turn = 0;
    const sessionIds: string[] = [];
    await page.route(STREAM_ROUTE, route => {
      sessionIds.push(route.request().url().split('/').at(-2)!);
      return route.fulfill({ contentType: 'text/event-stream', body: streamBody(`第 ${++turn} 轮回复`) });
    });
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('我的最新成绩是多少？');
    await chat.waitForResponse();
    await chat.sendMessage('和上次比有进步吗？');
    await chat.waitForResponse();
    await expect(page.locator('.message--user')).toHaveCount(2);
    await expect(page.locator('.message--assistant .message__text')).toHaveText(['第 1 轮回复', '第 2 轮回复']);
    expect(new Set(sessionIds).size).toBe(1);
  });

  test('新建真实会话后清空上一会话的消息', async ({ authenticatedPage: page }) => {
    await mockChatReply(page, '测试回复');
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('测试消息');
    await chat.waitForResponse();
    await chat.startNewSession();
    await expect(page.locator('.message')).toHaveCount(0);
  });

  test('结束真实会话后从下拉列表移除该会话', async ({ authenticatedPage: page }) => {
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.archiveSession();
  });

  test('服务端超时显示错误并允许重试', async ({ authenticatedPage: page }) => {
    await page.route(STREAM_ROUTE, route => route.fulfill({ status: 504, json: { error: { message: '请求超时，请重试' } } }));
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('分析我的成绩');
    await expect(page.getByRole('alert')).toContainText('请求超时，请重试');
    await expect(page.getByRole('button', { name: '重试', exact: true })).toBeEnabled();
    await expect(chat.messageInput).toBeEnabled();
  });

  test('SSE 未收到 done 时提示中断，重试保留客户端请求 ID', async ({ authenticatedPage: page }) => {
    const requestIds: string[] = [];
    let attempt = 0;
    await page.route(STREAM_ROUTE, route => {
      requestIds.push(route.request().postDataJSON().client_message_id);
      return route.fulfill({ contentType: 'text/event-stream', body: streamBody(++attempt === 1 ? '部分内容' : '已恢复完整回复', attempt > 1) });
    });
    const chat = new ChatPage(page);
    await chat.goto();
    await chat.sendMessage('测试连接恢复');
    await expect(page.getByRole('alert')).toContainText('连接中断');
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect(page.locator('.message--assistant .message__text').last()).toHaveText('已恢复完整回复');
    await expect(page.getByRole('alert')).toHaveCount(0);
    expect(requestIds).toHaveLength(2);
    expect(requestIds[1]).toBe(requestIds[0]);
  });
});

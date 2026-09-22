import { Page, Locator, expect } from '@playwright/test';

export class ChatPage {
  readonly messageInput: Locator;
  readonly sendButton: Locator;
  readonly messageList: Locator;
  readonly newSessionButton: Locator;
  readonly archiveSessionButton: Locator;
  private expectedAssistantCount = 0;

  constructor(readonly page: Page) {
    this.messageInput = page.locator('.input-box textarea');
    this.sendButton = page.locator('.input-box button[type="submit"]');
    this.messageList = page.locator('.message-list');
    this.newSessionButton = page.getByRole('button', { name: '新会话', exact: true });
    this.archiveSessionButton = page.getByRole('button', { name: '结束会话', exact: true });
  }

  async goto() {
    await this.page.goto('/chat');
    await expect(this.messageInput).toBeEnabled();
    // 每个用例使用真实 API 新建独立会话，避免读取其他用例留下的历史。
    await this.startNewSession();
  }

  async sendMessage(message: string) {
    this.expectedAssistantCount = await this.page.locator('.message--assistant').count() + 1;
    await this.messageInput.fill(message);
    await this.sendButton.click();
  }

  async waitForResponse(timeout = 15000) {
    await expect(this.page.locator('.message--assistant')).toHaveCount(this.expectedAssistantCount, { timeout });
    await expect(this.page.locator('.message--assistant .message__text').last()).not.toBeEmpty({ timeout });
    await expect(this.messageInput).toBeEnabled({ timeout });
    await expect(this.page.locator('.chat-container [role="alert"], .error-banner')).toHaveCount(0);
  }

  async getLastMessage(): Promise<string> {
    return await this.page.locator('.message--assistant .message__text').last().innerText();
  }

  async getAllMessages(): Promise<string[]> {
    return this.page.locator('.message .message__text').allTextContents();
  }

  async startNewSession() {
    const selector = this.page.getByRole('combobox', { name: '选择会话' });
    const previous = await selector.inputValue();
    const created = this.page.waitForResponse(response => response.url().endsWith('/chat/sessions') && response.request().method() === 'POST' && response.ok());
    await this.newSessionButton.click();
    const id = (await (await created).json()).id;
    expect(id).not.toBe(previous);
    await expect(selector).toHaveValue(id);
    await expect(this.page.locator('.message')).toHaveCount(0);
    await expect(this.messageInput).toBeEnabled();
  }

  async archiveSession() {
    const selector = this.page.getByRole('combobox', { name: '选择会话' });
    const previous = await selector.inputValue();
    await this.archiveSessionButton.click();
    await expect(selector).not.toHaveValue(previous);
    await expect(selector.locator(`option[value="${previous}"]`)).toHaveCount(0);
    await expect(this.messageInput).toBeEnabled();
  }
}

import { Page, Locator } from '@playwright/test';

/**
 * 学生仪表盘页面 Page Object
 */
export class DashboardPage {
  readonly page: Page;
  readonly welcomeMessage: Locator;
  readonly latestExamScore: Locator;
  readonly classRank: Locator;
  readonly diagnosisCount: Locator;
  readonly subjectCards: Locator;
  readonly chatButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.welcomeMessage = page.locator('h1, .welcome-title');
    this.latestExamScore = page.locator('.stat-card:has-text("最近一次总分")');
    this.classRank = page.locator('.stat-card:has-text("班级排名")');
    this.diagnosisCount = page.locator('.stat-card:has-text("诊断报告")');
    this.subjectCards = page.locator('.subject-card, [data-testid="subject-card"]');
    this.chatButton = page.locator('a[href="/chat"], button:has-text("问问学习助手")');
  }

  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('networkidle');
  }

  async getWelcomeMessage(): Promise<string> {
    return await this.welcomeMessage.textContent() || '';
  }

  async getLatestScore(): Promise<string> {
    return await this.latestExamScore.locator('.stat-card__value').textContent() || '';
  }

  async getClassRank(): Promise<string> {
    return await this.classRank.locator('.stat-card__value').textContent() || '';
  }

  async getDiagnosisCount(): Promise<number> {
    const text = await this.diagnosisCount.locator('.stat-card__value').textContent() || '0';
    return parseInt(text);
  }

  async getSubjectCount(): Promise<number> {
    return await this.subjectCards.count();
  }

  async navigateToChat() {
    await this.chatButton.click();
    await this.page.waitForURL('**/chat');
  }
}

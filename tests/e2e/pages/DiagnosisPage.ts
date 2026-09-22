import { Page, Locator } from '@playwright/test';

/**
 * 诊断报告页面 Page Object
 */
export class DiagnosisPage {
  readonly page: Page;
  readonly reportCards: Locator;
  readonly emptyState: Locator;
  readonly noticeBanner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.reportCards = page.locator('.report-card, [data-testid="report-card"]');
    this.emptyState = page.locator('.empty-state');
    this.noticeBanner = page.locator('.notice-banner');
  }

  async goto() {
    await this.page.goto('/diagnosis');
    await this.page.waitForLoadState('networkidle');
  }

  async getReportCount(): Promise<number> {
    return await this.reportCards.count();
  }

  async hasEmptyState(): Promise<boolean> {
    return await this.emptyState.isVisible();
  }

  async getFirstReportTitle(): Promise<string> {
    const firstReport = this.reportCards.first();
    return await firstReport.locator('h2').textContent() || '';
  }

  async hasNoticeBanner(): Promise<boolean> {
    return await this.noticeBanner.isVisible();
  }
}

import { Page, Locator } from '@playwright/test';

/**
 * 成绩趋势页面 Page Object
 */
export class TrendsPage {
  readonly page: Page;
  readonly chartContainer: Locator;
  readonly examList: Locator;
  readonly subjectTrendList: Locator;

  constructor(page: Page) {
    this.page = page;
    this.chartContainer = page.locator('.line-chart, [data-testid="chart"]');
    this.examList = page.locator('.trend-row, [data-testid="exam-row"]');
    this.subjectTrendList = page.locator('.subject-trend, [data-testid="subject-trend"]');
  }

  async goto() {
    await this.page.goto('/trends');
    await this.page.waitForLoadState('networkidle');
  }

  async getExamCount(): Promise<number> {
    return await this.examList.count();
  }

  async getSubjectCount(): Promise<number> {
    return await this.subjectTrendList.count();
  }

  async hasChart(): Promise<boolean> {
    return await this.chartContainer.isVisible();
  }
}

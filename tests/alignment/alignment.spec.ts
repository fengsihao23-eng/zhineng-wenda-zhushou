import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, 'utf8'))

async function login(page: Page, role: string) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(fixture.users[role])
  await page.getByLabel('密码').fill(process.env.QA_PASSWORD!)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
}

test('production login has no demo accounts; role deep links reject before data fetch', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('.test-accounts')).toHaveCount(0)
  await login(page, 'student')
  let managementCalls = 0
  page.on('request', request => { if (request.url().includes('/platform/management/')) managementCalls++ })
  await page.goto('/admin/risks')
  await expect(page.getByRole('heading', { name: '无权访问此页面' })).toBeVisible()
  expect(managementCalls).toBe(0)
})

test('refresh restores identity; report source and question evidence entry remain reachable', async ({ page }) => {
  await login(page, 'student')
  await page.goto('/diagnosis')
  await expect(page.getByText('QA 正式报告合成摘要')).toBeVisible()
  await page.reload()
  await expect(page.getByText('QA 正式报告合成摘要')).toBeVisible()
  await page.getByRole('button', { name: '查看原始依据' }).click()
  await expect(page.getByText('QA 原始依据，仅为合成验收数据。')).toBeVisible()
  await page.goto('/mistakes')
  await page.getByRole('button', { name: '查看原题 / 加入复盘', exact: true }).click()
  await expect(page.getByRole('heading', { name: '原题与复盘' })).toBeVisible()
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/diagnosis')
  await expect(page).toHaveURL(/\/login$/)
})

test('BASIC no-permission and empty states', async ({ page }) => {
  await login(page, 'basic')
  await page.goto('/diagnosis')
  await expect(page.getByText('当前没有有效的诊断报告授权，请联系学校确认。')).toBeVisible()
  await page.goto('/mistakes')
  await expect(page.getByText('还没有可展示的数据')).toBeVisible()
})

test('teacher navigation, scoped student detail and acknowledged risk can resolve', async ({ page }) => {
  await login(page, 'teacher')
  await expect(page.locator('.queue-item').filter({ hasText: '运营反馈' })).toHaveAttribute('href', '/teacher/feedback')
  await page.goto('/teacher/students')
  await expect(page.getByText('QA 合成学生')).toBeVisible()
  await expect(page.getByText('QA 空数据学生')).toHaveCount(0)
  await page.getByRole('link', { name: '查看学情' }).click()
  await expect(page.getByText('数学', { exact: true })).toBeVisible()
  await page.goto('/teacher/risks')
  const card = page.locator('.risk-card').filter({ hasText: 'QA 待确认事件' })
  await card.getByRole('button', { name: '确认事件' }).click()
  await expect(card.getByText('已确认', { exact: true })).toBeVisible()
  await card.getByRole('button', { name: '标记解决' }).click()
  await card.getByRole('textbox').fill('QA 已核验并完成跟进')
  await card.getByRole('button', { name: '确认标记解决' }).dblclick()
  await expect(card.getByText('已解决', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('QA 已核验并完成跟进')).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('risk-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 320, height: 800 })
  await expect(page.locator('.app-sidebar')).toBeHidden()
  expect((await page.locator('.workspace-main').boundingBox())!.width).toBeGreaterThan(200)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('risk-mobile.png'), fullPage: true, animations: 'disabled' })
})

test('knowledge reject edit resubmit publish persists', async ({ page }) => {
  await login(page, 'admin')
  await page.goto('/admin/knowledge')
  await page.getByRole('button', { name: '+ 新建文档' }).click()
  await page.getByLabel('文档标题').fill('QA 返工资料')
  await page.getByLabel('来源名称').fill('QA 合成教研组')
  await page.getByLabel('来源引用').fill('QA 第 1 页')
  await page.getByLabel('正文内容').fill('QA 初稿')
  await page.getByRole('button', { name: '保存草稿' }).click()
  const row = page.getByRole('row').filter({ hasText: 'QA 返工资料' })
  await row.getByRole('button', { name: '提交审核' }).click()
  await row.getByRole('button', { name: '驳回', exact: true }).click()
  await row.getByRole('textbox').fill('QA 需要补充来源')
  await row.getByRole('button', { name: '确认驳回' }).click()
  await row.getByRole('button', { name: '编辑返工' }).click()
  await page.getByLabel('正文内容').fill('QA 已修订正文')
  await page.getByRole('button', { name: '保存草稿' }).click()
  await row.getByRole('button', { name: '提交审核' }).click()
  await row.getByRole('button', { name: '通过', exact: true }).click()
  await page.reload()
  await expect(row.getByText('已发布', { exact: true })).toBeVisible()
  await expect(row.getByText('v2')).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('knowledge-published.png'), fullPage: true })
})

test('city school detail uses real scoped totals', async ({ page }) => {
  await login(page, 'city')
  await page.goto('/ops/schools')
  const card = page.locator('.school-card').filter({ hasText: 'QA 合成学校' }).last()
  await card.getByRole('link', { name: '查看运营详情' }).click()
  await expect(page.getByRole('heading', { name: '学校运营详情' })).toBeVisible()
  await expect(page.getByText('尚未建设学校活跃度统计，不能以学生总数代替。')).toBeVisible()
})

test('IME composing Enter does not send; normal Enter sends once', async ({ page }) => {
  await login(page, 'student')
  await page.goto('/chat')
  const input = page.getByRole('textbox', { name: '提问内容' })
  await input.fill('QA 输入法测试')
  let requests = 0
  await page.route('**/chat/sessions/*/stream', async route => { requests++; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'QA 合成错误' } }) }) })
  await input.dispatchEvent('compositionstart')
  await input.press('Enter')
  await expect(input).toHaveValue(/QA 输入法测试\s*/)
  expect(requests).toBe(0)
  await input.dispatchEvent('compositionend')
  await input.press('Enter')
  await expect.poll(() => requests).toBe(1)
  await expect(input).toHaveValue('')
})

test('error retry recovers; 320px source and workflow content are reachable', async ({ page }) => {
  await login(page, 'teacher')
  let fail = true
  await page.route('**/platform/management/feedback', route => fail ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'QA 暂时不可用' } }) }) : route.continue())
  await page.goto('/teacher/feedback')
  await expect(page.getByText('QA 暂时不可用')).toBeVisible()
  fail = false
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('当前没有符合条件的反馈。')).toBeVisible()
  await page.setViewportSize({ width: 320, height: 800 })
  await page.goto('/teacher/students/' + fixture.student_id)
  await expect(page.getByRole('heading', { name: '学生学情详情' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('student submissions prevent duplicate clicks and read back durable results', async ({ page }) => {
  await login(page, 'student')
  await page.goto('/support')
  await page.getByPlaceholder('写下你遇到的问题…').fill('QA 反馈提交回读')
  await page.getByRole('button', { name: '提交反馈', exact: true }).dblclick()
  await expect(page.locator('.feedback-card').filter({ hasText: '产品反馈' })).toHaveCount(1)
  await page.getByRole('button', { name: '联系老师' }).dblclick()
  await expect(page.locator('.feedback-card').filter({ hasText: '学生主动请求人工协助' })).toHaveCount(1)
  await page.reload()
  await expect(page.locator('.feedback-card').filter({ hasText: '产品反馈' })).toHaveCount(1)
  await expect(page.locator('.feedback-card').filter({ hasText: '学生主动请求人工协助' })).toHaveCount(1)
})

test('existing responsive score charts remain valid at target widths', async ({ page }) => {
  await login(page, 'student')
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/profile')
    await expect(page.locator('.score-number')).toHaveText('70/ 100')
    await expect(page.locator('.profile-container')).not.toContainText(/Infinity|NaN/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.goto('/trends')
    await expect(page.getByRole('img', { name: '总分趋势图' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
})

test('source read errors are visible and retry restores source', async ({ page }) => {
  await login(page, 'student')
  await page.goto('/diagnosis')
  let fail = true
  await page.route('**/platform/student/diagnosis/*/source', route => fail ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'QA 原文暂时不可用' } }) }) : route.continue())
  await page.getByRole('button', { name: '查看原始依据' }).click()
  await expect(page.getByText('QA 原文暂时不可用')).toBeVisible()
  fail = false
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('QA 原始依据，仅为合成验收数据。')).toBeVisible()
})

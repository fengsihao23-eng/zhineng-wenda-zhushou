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

test('controlled legacy snapshot has visible mapping hash and repeatable receipt', async ({ page }) => {
  await login(page, 'admin')
  await page.goto('/admin/sources')
  await page.getByRole('link', { name: '接入旧资料', exact: true }).click()
  const body = { source_system: 'browser_legacy', source_version: 'v1', captured_at: '2026-09-18T00:00:00Z', records: [
    { entity_type: 'exam', external_id: 'legacy-exam-ui', name: 'QA 旧考试快照', start_date: '2026-08-01' },
    { entity_type: 'question', external_id: 'legacy-question-ui', subject_id: fixture.subject_id, kind: 'standalone', title: 'QA 旧题快照', stem: '合成来源题干' },
  ] }
  await page.getByLabel('快照 JSON 文件').setInputFiles({ name: 'synthetic-snapshot.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(body)) })
  await page.getByRole('button', { name: '核验并接入快照' }).click()
  await expect(page.getByText(/已核验 2 个来源实体 · 版本 v1/)).toBeVisible()
  await page.getByRole('button', { name: '核验并接入快照' }).click()
  await expect(page.getByText(/已核验 2 个来源实体 · 版本 v1/)).toBeVisible()
  await page.getByRole('link', { name: '查看来源列表', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: 'legacy-exam-ui' })
  await expect(row).toHaveCount(1)
  await row.getByRole('link', { name: '查看映射与依据' }).click()
  await expect(page.getByText('旧标识 → 新记录')).toBeVisible()
  await page.reload()
  await expect(page.getByText('旧标识 → 新记录')).toBeVisible()
  await page.getByRole('link', { name: '返回来源列表' }).click()
  await expect(row).toHaveCount(1)
})

test('formal report original upload version preview and reload are real', async ({ page }) => {
  await login(page, 'admin')
  await page.goto('/admin/reports')
  await page.getByRole('link', { name: '保存新报告版本', exact: true }).click()
  await page.getByLabel('上传正式报告原件').setInputFiles(fixture.pdf_path)
  await page.getByRole('button', { name: '校验并上传', exact: true }).click()
  await expect(page.getByText(/原件已保存：/)).toBeVisible()
  await page.getByLabel('学生', { exact: true }).selectOption(fixture.student_id)
  await page.getByLabel('考试', { exact: true }).selectOption(fixture.exam_id)
  await page.getByLabel('学科（综合报告可留空）').selectOption(fixture.subject_id)
  await page.getByLabel('版本号').fill('browser-v2')
  await page.getByLabel('报告生成时间').fill('2026-09-18T10:00')
  await page.getByLabel('正式摘要').fill('QA 人工审核后的正式摘要。')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: 'browser-v2' })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '查看原件', exact: true }).click()
  await expect(page.getByTitle('原件预览')).toBeVisible()
  await expect(page.getByRole('link', { name: '下载当前版本' })).toHaveAttribute('href', /^blob:/)
  await page.getByRole('button', { name: '关闭预览' }).click()
  await page.reload()
  await expect(row).toBeVisible()
})

test('authorized teacher class aggregation drills down to the same student facts', async ({ page }) => {
  await login(page, 'teacher')
  await page.goto('/teacher/analysis')
  await page.getByLabel('班级', { exact: true }).selectOption({ label: 'QA 合成班级' })
  await page.getByLabel('学科', { exact: true }).selectOption(fixture.subject_id)
  await page.getByLabel('考试', { exact: true }).selectOption(fixture.exam_id)
  await expect(page.getByText(/样本量：1 · 平均分：70/)).toBeVisible()
  await page.getByRole('link', { name: '查看学情', exact: true }).click()
  await expect(page.getByText('数学', { exact: true })).toBeVisible()
  await expect(page.getByText('70 / 100')).toBeVisible()
})

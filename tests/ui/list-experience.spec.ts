import { test, expect, type Page } from '@playwright/test'

const batchId = '10000000-0000-4000-8000-000000000001'
const roster = Array.from({ length: 55 }, (_, index) => ({
  id: String(index + 1), name: `测试学生${index + 1}`, username: `student${index + 1}`,
  student_no: `S${index + 1}`, user_id: `user${index + 1}`, class_name: '高一1班', status: 'active', fields: {}, duties: [],
}))

async function mockApi(page: Page, role = 'SCHOOL_ADMIN', recordCount = 55) {
  let records = roster.slice(0, recordCount)
  const user = { user_id: 'ui-user', school_id: 'ui-school', username: 'ui-user', display_name: '测试用户', roles: [role] }
  await page.addInitScript(identity => {
    sessionStorage.setItem('refresh_token', 'synthetic-ui-token')
    sessionStorage.setItem('user_info', JSON.stringify(identity))
  }, user)
  const requests: string[] = []
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1', '')
    requests.push(path + url.search)
    let body: unknown = []
    if (path === '/auth/me') body = user
    else if (path === '/health') body = { model: { real_model_ready: true } }
    else if (path.endsWith('/actions')) {
      const id = path.split('/').at(-2)
      records = records.filter(row => row.id !== id)
      body = { message: '已删除原档案' }
    } else if (/\/roster\/(students|teachers)\/records$/.test(path)) {
      const rows = records.filter(row => (row.name + row.username).includes(url.searchParams.get('search') || ''))
      const size = Number(url.searchParams.get('page_size') || 30), current = Number(url.searchParams.get('page') || 1)
      body = { items: rows.slice((current - 1) * size, current * size), total: rows.length }
    } else if (/\/roster\/(students|teachers)\/imports$/.test(path)) {
      body = route.request().method() === 'POST' ? { id: batchId } : Array.from({ length: 25 }, (_, index) => ({ id: index ? String(index) : batchId, filename: `资料-${index + 1}.xlsx`, status: 'succeeded', operator_name: '管理员', created_at: '2026-09-24' }))
    } else if (path.endsWith(`/roster/imports/${batchId}`)) {
      body = { id: batchId, filename: '资料-1.xlsx', kind: 'students', status: 'succeeded', columns: [], rows: [], report: { total_rows: 2, issues: [], success_count: 2, skipped_count: 0, skipped_rows: [], unresolved_teaching: [] } }
    } else if (path.includes('/school/') || /\/(papers|questions|sources|deletions)$/.test(path)) {
      const size = Number(url.searchParams.get('page_size') || 30), current = Number(url.searchParams.get('page') || 1)
      body = { items: roster.slice((current - 1) * size, current * size).map(row => ({ ...row, title: row.name, source_system: 'native', kind: 'standalone', external_id: row.id })), total: roster.length }
    } else if (path === '/platform/management/feedback') {
      body = roster.map((row, index) => ({ id: row.id, category: `反馈${index + 1}`, status: index < 22 ? 'open' : 'resolved', allowed_transitions: [], state_version: 1 }))
    } else if (path === '/platform/education/imports') {
      body = [{ id: batchId, batch_key: '成绩批次', status: 'succeeded', source_system: 'school_csv' }]
    } else if (path === '/platform/student/mistakes') body = []
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  return requests
}

test('roster focuses on records, help opens on click, and history has its own refreshable page', async ({ page }) => {
  const requests = await mockApi(page)
  await page.goto('/admin/school?tab=students')
  await expect(page.getByRole('heading', { name: '学生信息列表' })).toBeVisible()
  await expect(page.getByLabel('上传学生 Excel')).toHaveCount(0)
  await expect(page.locator('tbody tr')).toHaveCount(20)
  expect(requests.some(path => path.includes('/roster/students/imports'))).toBe(false)
  const help = page.getByRole('note', { name: '档案维护说明', includeHidden: true })
  await expect(help).toBeHidden()
  await page.locator('summary').filter({ hasText: '档案维护说明' }).click()
  await expect(help).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(help).toBeHidden()
  await page.locator('summary').filter({ hasText: '档案维护说明' }).click()
  await page.getByRole('heading', { name: '学生信息列表' }).click()
  await expect(help).toBeHidden()
  await page.screenshot({ path: test.info().outputPath('student-list-desktop.png'), fullPage: true })
  await page.getByRole('link', { name: '导入记录及操作回执', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/school\/students\/imports$/)
  await expect(page.getByRole('heading', { name: '学生信息列表' })).toHaveCount(0)
  await page.getByLabel('每页显示条数').selectOption('10')
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await page.getByRole('link', { name: '查看批次' }).first().click()
  await expect(page.getByRole('heading', { name: '导入完成' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '导入完成' })).toBeVisible()
  await page.getByRole('link', { name: '返回信息列表' }).click()
  await expect(page.getByRole('heading', { name: '学生信息列表' })).toBeVisible()
  await page.getByRole('link', { name: '导入学生', exact: true }).click()
  await expect(page.getByLabel('上传学生 Excel')).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(0)
  await page.getByLabel('上传学生 Excel').setInputFiles({ name: 'test.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('synthetic fixture') })
  await page.getByRole('button', { name: '上传并预校验' }).click()
  await expect(page).toHaveURL(new RegExp(`/imports/${batchId}$`))
})

test('server pagination changes request size, resets filters and handles the last or empty page', async ({ page }) => {
  await mockApi(page)
  await page.goto('/admin/school?tab=students')
  const size = page.getByLabel('每页显示条数')
  await size.selectOption('10')
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.locator('tbody tr').first()).toContainText('测试学生11')
  await size.selectOption('50')
  await expect(page.locator('tbody tr')).toHaveCount(50)
  await expect(page.getByRole('button', { name: '上一页' })).toBeDisabled()
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.locator('tbody tr')).toHaveCount(5)
  await expect(page.getByRole('button', { name: '下一页' })).toBeDisabled()
  await page.getByLabel('学生姓名或账号').fill('student1')
  await expect(page.locator('tbody tr')).toHaveCount(11)
  await expect(page.getByText('第 1 / 1 页')).toBeVisible()
  await page.getByLabel('学生姓名或账号').fill('没有这位学生')
  await expect(page.locator('tbody tr')).toHaveCount(0)
  await expect(page.getByText('共 0 条', { exact: true })).toBeVisible()
  await expect(size).toHaveValue('50')
})

test('client pagination resets on status filters and keeps totals for the whole result', async ({ page }) => {
  await mockApi(page)
  await page.goto('/admin/feedback')
  await page.getByLabel('每页显示条数').selectOption('10')
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.locator('.feedback-card').first()).toContainText('反馈11')
  await page.getByLabel('处理状态').selectOption('resolved')
  await expect(page.locator('.feedback-card')).toHaveCount(10)
  await expect(page.locator('.feedback-card').first()).toContainText('反馈23')
  await expect(page.getByText('共 33 条', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '上一页' })).toBeDisabled()
  await page.getByLabel('处理状态').selectOption('all')
  await expect(page.locator('.feedback-card').first()).toContainText('反馈1')
  await expect(page.getByRole('button', { name: '上一页' })).toBeDisabled()
  await page.getByLabel('处理状态').selectOption('resolved')
  await page.getByLabel('每页显示条数').selectOption('100')
  await expect(page.locator('.feedback-card')).toHaveCount(33)
})

for (const [path, entry, field] of [
  ['/admin/imports', '上传新批次', '批次编号'],
  ['/admin/papers', '上传新试卷', '上传原件'],
  ['/admin/reports', '保存新报告版本', '上传正式报告原件'],
  ['/admin/sources', '接入旧资料', '快照 JSON 文件'],
]) {
  test(`${path} keeps upload forms off the list page`, async ({ page }) => {
    await mockApi(page)
    await page.goto(path)
    await expect(page.getByLabel(field, { exact: true })).toHaveCount(0)
    await page.getByRole('link', { name: entry, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${path}/new$`))
    await expect(page.getByLabel(field, { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByLabel(field, { exact: true })).toBeVisible()
  })
}

for (const path of ['/admin/papers', '/admin/questions', '/admin/sources']) {
  test(`${path} requests the selected page size`, async ({ page }) => {
    const requests = await mockApi(page)
    await page.goto(path)
    await page.getByLabel('每页显示条数').selectOption('10')
    await expect(page.locator('tbody tr')).toHaveCount(10)
    await page.getByRole('button', { name: '下一页' }).click()
    await expect(page.locator('tbody tr').first()).toContainText('11')
    expect(requests.some(url => url.includes('page=2') && url.includes('page_size=10'))).toBe(true)
  })
}

test('edit forms open in focused dialogs and keyboard dismissal returns to the list', async ({ page }) => {
  await mockApi(page)
  await page.goto('/admin/school?tab=classes')
  await expect(page.getByLabel('班级名称', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '新建班级', exact: true }).click()
  const form = page.getByRole('dialog', { name: '新建班级', exact: true })
  await expect(form).toBeVisible()
  await form.getByLabel('班级名称', { exact: true }).fill('新班级')
  await page.keyboard.press('Escape')
  await expect(form).toHaveCount(0)
  await page.goto('/admin/questions')
  await page.getByRole('button', { name: '知识点树与标签', exact: true }).click()
  await expect(page.getByLabel('节点名称')).toHaveCount(0)
  await page.getByRole('button', { name: '新建知识点 / 标签', exact: true }).click()
  const taxonomy = page.getByRole('dialog', { name: '新建知识点 / 标签', exact: true })
  await expect(taxonomy.getByLabel('节点名称')).toBeVisible()
  await taxonomy.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(taxonomy).toHaveCount(0)
})

test('deleting the last row on the last page returns to a populated page', async ({ page }) => {
  await mockApi(page, 'SCHOOL_ADMIN', 21)
  await page.goto('/admin/school?tab=students')
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.getByRole('button', { name: '删除原档案', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '确认档案操作' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '确认删除原档案' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.locator('tbody tr')).toHaveCount(20)
  await expect(page.getByText('第 1 / 1 页')).toBeVisible()
})

test('read-only roles retain history access without import or archive actions', async ({ page }) => {
  await mockApi(page, 'QA')
  await page.goto('/admin/school?tab=students')
  await expect(page.getByRole('link', { name: '导入学生', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '删除原档案', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: '导入记录及操作回执', exact: true }).click()
  await expect(page.getByRole('link', { name: '查看批次' }).first()).toBeVisible()
  await page.goto('/admin/school/students/import')
  await expect(page.getByLabel('上传学生 Excel')).toHaveCount(0)
})

test('student records are accessible from separate entries', async ({ page }) => {
  await mockApi(page, 'STUDENT')
  await page.goto('/mistakes')
  await expect(page.getByRole('heading', { name: '我的订正与复习' })).toHaveCount(0)
  await page.getByRole('link', { name: '我的订正与复习' }).click()
  await expect(page).toHaveURL(/\/mistakes\/reviews$/)
  await page.goto('/support')
  await expect(page.getByRole('button', { name: '人工工单' })).toHaveCount(0)
  await page.getByRole('link', { name: '反馈与求助记录' }).click()
  await expect(page).toHaveURL(/\/support\/records$/)
  await expect(page.getByRole('button', { name: '人工工单' })).toBeVisible()
})

test('mobile actions, pagination and explanation popovers stay within the viewport', async ({ page }) => {
  await mockApi(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/school?tab=students')
  await expect(page.getByRole('link', { name: '导入学生', exact: true })).toBeInViewport()
  await page.locator('summary').filter({ hasText: '档案维护说明' }).click()
  const note = page.getByRole('note', { name: '档案维护说明' })
  await expect(note).toBeInViewport()
  const bounds = (await note.boundingBox())!
  expect(bounds.x).toBeGreaterThanOrEqual(0)
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: '关闭档案维护说明' }).click()
  await page.getByLabel('每页显示条数').selectOption('10')
  await expect(page.locator('tbody tr')).toHaveCount(10)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('student-list-mobile.png'), fullPage: true })
})

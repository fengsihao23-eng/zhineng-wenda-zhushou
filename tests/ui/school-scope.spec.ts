import { test, expect, type Page } from '@playwright/test'

const schools = [
  { id: '10000000-0000-4000-8000-000000000001', name: '第一测试学校', code: 'SCHOOL-A', status: 'active' },
  { id: '10000000-0000-4000-8000-000000000002', name: '第二测试学校', code: 'SCHOOL-B', status: 'active' },
]

async function setup(page: Page, role = 'SUPER_ADMIN') {
  const identity = { user_id: 'owner-1', username: 'owner', display_name: '测试管理员', school_id: schools[0].id, roles: [role] }
  const requests: Array<{ path: string; school: string | undefined }> = []
  await page.addInitScript(user => {
    sessionStorage.setItem('refresh_token', 'synthetic-only')
    sessionStorage.setItem('user_info', JSON.stringify(user))
  }, identity)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    const selected = route.request().headers()['x-school-id']
    requests.push({ path, school: selected })
    const school = schools.find(s => s.id === selected) || schools[0]
    const person = { id: `person-${school.code}`, platform_id: school.code === 'SCHOOL-A' ? '88888881' : '88888882', name: `${school.code}教师`, username: `${school.code}-user`, display_name: `${school.code}教师`, school_id: school.id, school_name: school.name, school_code: school.code, status: 'active', phone: '', class_name: '', fields: {}, duties: ['TEACHER'] }
    let data: unknown = []
    if (path === '/auth/me') data = identity
    else if (path === '/auth/refresh') data = { access_token: 'synthetic-only', refresh_token: 'synthetic-only', expires_in: 3600 }
    else if (path === '/health') data = { model: { real_model_ready: true } }
    else if (path === '/platform/administrators/schools') data = schools
    else if (path.endsWith('/roster/teachers/records')) data = { items: [person], total: 1 }
    else if (path.endsWith('/roster/students/records')) data = { items: [{ ...person, name: `${school.code}学生`, grade: '高一', class_number: '1班' }], total: 1, current_year: '2026-2027' }
    else if (path.endsWith('/roster/students/context')) data = { current_year: '2026-2027', next_year: '2027-2028', status_counts: { active: 1 }, columns: [], change_columns: [], promotion_columns: [], locked_fields: [] }
    else if (path.endsWith('/exam-management/options')) data = { current_year: '2026-2027', academic_year: '2026-2027', years: ['2026-2027'], students: [], school: school.name }
    else if (path.endsWith('/exam-management')) data = { items: [{ id: 'exam-1', exam_id: 'E1', name: '测试考试', academic_year: '2026-2027', exam_date: '2026-11-05', participant_count: 0, subjects: [], snapshots: {}, score_files: {}, teacher_permissions: {}, student_permissions: {}, open_state_label: '未开放', open_state: 'none' }], total: 1, grades: [], subjects: [] }
    else if (path.endsWith('/report-management/options')) data = { school: school.name, exams: [] }
    else if (path.endsWith('/report-management')) data = { items: [], total: 0, counts: { all: 0, diagnostic: 0, essay: 0 }, facets: { subjects: [], grades: [], classes: [] } }
    else if (path === '/platform/management/overview') data = { scope: 'school', schools: 1, students: 1, open_risks: 0, open_feedback: 0, open_handoffs: 0 }
    else if (path === '/platform/management/schools') data = [{ ...school, students: 1, open_risks: 0 }]
    else if (path === '/platform/administrators' || path === '/platform/administrators/history') data = { items: [], total: 0 }
    else if (path === '/answer-workbench/admin/state') {
      await route.fulfill({ status: 503, json: { error: { message: '合成服务响应' } } }); return
    }
    await route.fulfill({ json: data })
  })
  return requests
}

test('super admin selects by school name or code and switching clears previous rows and selections', async ({ page }) => {
  const requests = await setup(page)
  await page.goto('/admin/school?tab=teachers')
  await expect(page.getByRole('heading', { name: '尚未选择学校' })).toBeVisible()
  expect(requests.some(r => r.path.includes('/roster/'))).toBe(false)
  await page.getByRole('combobox', { name: '学校名称', exact: true }).selectOption(schools[0].id)
  await expect(page.getByRole('columnheader', { name: '学校名称', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '第一测试学校 SCHOOL-A' })).toBeVisible()
  await page.getByRole('checkbox', { name: '选择教师SCHOOL-A教师' }).check()
  await page.getByRole('combobox', { name: '学校编码', exact: true }).selectOption(schools[1].id)
  await expect(page.getByRole('combobox', { name: '学校名称', exact: true })).toHaveValue(schools[1].id)
  await expect(page.getByRole('cell', { name: '第二测试学校 SCHOOL-B' })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: '选择教师SCHOOL-B教师' })).not.toBeChecked()
  await expect(page.getByRole('cell', { name: '第一测试学校 SCHOOL-A' })).toHaveCount(0)
  expect(requests.filter(r => r.path.endsWith('/teachers/records')).at(-1)?.school).toBe(schools[1].id)
  await page.screenshot({ path: test.info().outputPath('teacher-school-filter.png'), fullPage: true })
  await page.getByRole('link', { name: '学生档案', exact: true }).click()
  await expect(page.getByRole('heading', { name: '学生信息列表' })).toBeVisible()
  await expect(page.getByRole('cell', { name: '第二测试学校 SCHOOL-B' })).toBeVisible()
  expect(requests.filter(r => r.path.endsWith('/students/records')).at(-1)?.school).toBe(schools[1].id)
  await page.getByRole('link', { name: '考务管理', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: '学校名称', exact: true })).toBeVisible()
  expect(requests.filter(r => r.path.endsWith('/exam-management')).at(-1)?.school).toBe(schools[1].id)
  await page.getByRole('link', { name: '报告管理', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: '学校名称', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重置学校', exact: true }).click()
  await expect(page.getByRole('heading', { name: '尚未选择学校' })).toBeVisible()
})

test('name and code search combine; ordinary school admins have no cross-school selector', async ({ page }) => {
  await setup(page)
  await page.goto('/admin/school?tab=teachers')
  await page.getByRole('textbox', { name: '搜索学校名称', exact: true }).fill('第二')
  await page.getByRole('textbox', { name: '搜索学校编码', exact: true }).fill('SCHOOL-B')
  await expect(page.getByRole('combobox', { name: '学校名称', exact: true }).locator('option')).toHaveCount(2)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.app-sidebar')).toBeHidden()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('school-selection-mobile.png'), fullPage: true })
  const local = await page.context().newPage()
  const requests = await setup(local, 'SCHOOL_ADMIN')
  await local.goto('/admin/school?tab=teachers')
  await expect(local.getByRole('heading', { name: '教师信息列表' })).toBeVisible()
  await expect(local.getByRole('combobox', { name: '学校名称', exact: true })).toHaveCount(0)
  expect(requests.every(r => r.school === undefined)).toBe(true)
})

test('school selection also scopes prompt iframe and management lists', async ({ page }) => {
  const requests = await setup(page)
  await page.goto('/admin/prompts')
  await page.getByRole('combobox', { name: '学校编码', exact: true }).selectOption(schools[1].id)
  await expect.poll(() => requests.some(r => r.path === '/answer-workbench/admin/state')).toBe(true)
  expect(requests.find(r => r.path === '/answer-workbench/admin/state')?.school).toBe(schools[1].id)
  await page.goto('/ops/knowledge')
  await expect.poll(() => requests.some(r => r.path === '/platform/management/knowledge')).toBe(true)
  expect(requests.find(r => r.path === '/platform/management/knowledge')?.school).toBe(schools[1].id)
  await page.goto('/ops/administrators')
  await expect(page.getByRole('combobox', { name: '学校编码', exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: '学校编码', exact: true }).selectOption(schools[1].id)
  await expect(page.getByRole('combobox', { name: '学校名称', exact: true })).toHaveValue(schools[1].id)
})

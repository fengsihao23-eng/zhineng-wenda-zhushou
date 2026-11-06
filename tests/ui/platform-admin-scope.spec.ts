import { test, expect, type Page } from '@playwright/test'

const school = { id: '10000000-0000-4000-8000-000000000001', name: '阳江高级中学', code: '441702004001', status: 'active' }

async function setup(page: Page, roles: string[]) {
  const identity = { user_id: 'test-admin', username: 'test-admin', display_name: '测试管理员', school_id: school.id, roles }
  const requests: Array<{ path: string; school: string | undefined }> = []
  await page.addInitScript(user => {
    sessionStorage.setItem('refresh_token', 'synthetic-only')
    sessionStorage.setItem('user_info', JSON.stringify(user))
  }, identity)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    requests.push({ path, school: route.request().headers()['x-school-id'] })
    let data: unknown = []
    if (path === '/auth/me') data = identity
    else if (path === '/auth/refresh') data = { access_token: 'synthetic-only', refresh_token: 'synthetic-only', expires_in: 3600 }
    else if (path === '/health') data = { model: { real_model_ready: true } }
    else if (path === '/platform/administrators/schools') data = [school]
    else if (path === '/platform/administrators' || path === '/platform/administrators/history') data = { items: [], total: 0 }
    else if (path.endsWith('/roster/teachers/records')) data = { items: [{ id: 'teacher-1', platform_id: '88888881', name: '测试教师', username: 'teacher', status: 'active', phone: '', class_name: '', fields: {}, duties: [] }], total: 1 }
    else if (path.endsWith('/exam-management/options')) data = { current_year: '2026-2027', academic_year: '2026-2027', years: ['2026-2027'], students: [], school: school.name }
    else if (path.endsWith('/exam-management')) data = { items: [], total: 0, grades: [], subjects: [] }
    await route.fulfill({ json: data })
  })
  return requests
}

test('super admin has only the administrator module even when legacy business roles coexist', async ({ page }) => {
  const requests = await setup(page, ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'CITY_OPERATOR', 'TEACHER'])
  await page.goto('/')
  await expect(page).toHaveURL(/\/ops\/administrators$/)
  await expect(page.getByRole('heading', { name: '管理员与操作历史' })).toBeVisible()
  await expect(page.locator('.side-nav a')).toHaveText(['管理员与操作历史'])
  await expect(page.getByRole('combobox', { name: '学校编码', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '全部账号', exact: true })).toHaveCount(0)
  for (const path of ['/admin/school?tab=teachers', '/admin/reports', '/admin/prompts', '/ops/schools', '/teacher/students']) {
    await page.goto(path)
    await expect(page).toHaveURL(/\/ops\/administrators$/)
  }
  expect(requests.filter(r => r.path.startsWith('/platform/')).every(r => r.path.startsWith('/platform/administrators'))).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '切换导航' }).click()
  await expect(page.getByRole('dialog', { name: '主导航' }).getByRole('link')).toHaveText(['管理员与操作历史'])
})

test('school admin opens the original school modules without choosing a school', async ({ page }) => {
  const requests = await setup(page, ['SCHOOL_ADMIN'])
  await page.goto('/')
  await expect(page).toHaveURL(/\/admin\/school\?tab=exam-management$/)
  await expect(page.locator('.side-nav a')).toHaveText(['教师档案', '学生档案', '考务管理', '报告管理', '提示词及人工'])
  await page.getByRole('link', { name: '教师档案', exact: true }).click()
  await expect(page.getByRole('heading', { name: '教师信息列表' })).toBeVisible()
  await expect(page.getByRole('cell', { name: '测试教师 teacher' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: '学校编码', exact: true })).toHaveCount(0)
  await page.goto('/ops/administrators')
  await expect(page.getByRole('heading', { name: '无权访问此页面' })).toBeVisible()
  expect(requests.every(r => r.school === undefined && !r.path.startsWith('/platform/administrators'))).toBe(true)
})

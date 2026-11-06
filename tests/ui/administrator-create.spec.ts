import { test, expect, type Page } from '@playwright/test'

const school = { id: '10000000-0000-4000-8000-000000000001', name: '测试学校', code: 'SCHOOL-A', status: 'active' }

async function setup(page: Page, rejectFirst = false, roles = ['SUPER_ADMIN']) {
  const identity = { user_id: 'owner-1', username: 'owner', display_name: '测试管理员', school_id: school.id, roles }
  const creates: Record<string, unknown>[] = []
  const accounts: Record<string, unknown>[] = []
  await page.addInitScript(user => {
    sessionStorage.setItem('refresh_token', 'synthetic-only')
    sessionStorage.setItem('user_info', JSON.stringify(user))
  }, identity)
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    let data: unknown = []
    if (path === '/auth/me') data = identity
    else if (path === '/auth/refresh') data = { access_token: 'synthetic-only', refresh_token: 'synthetic-only', expires_in: 3600 }
    else if (path === '/health') data = { model: { real_model_ready: true } }
    else if (path === '/platform/administrators/schools') data = [school, { ...school, id: 'disabled-school', status: 'disabled' }]
    else if (path === '/platform/administrators' && request.method() === 'POST') {
      const body = request.postDataJSON(); creates.push(body)
      if (rejectFirst && creates.length === 1) {
        await route.fulfill({ status: 409, json: { error: { message: '该八位账号已被使用，请换一个或留空自动生成。' } } }); return
      }
      data = { id: 'new-admin', ...body, username: body.username || '87654321', school_name: school.name, school_code: school.code, status: 'active', is_administrator: true, revision: 0, account_type: 'general', platform_id: null, created_at: '2026-11-05T09:00:00Z', updated_at: '2026-11-05T09:00:00Z', last_login_at: null }
      accounts.push(data as Record<string, unknown>)
      await route.fulfill({ status: 201, json: data }); return
    } else if (path === '/platform/administrators') data = { items: accounts, total: accounts.length }
    else if (path.endsWith('/exam-management/options')) data = { current_year: '2026-2027', academic_year: '2026-2027', years: ['2026-2027'], students: [{ id: 'student-1', platform_id: '88888888', name: '测试学生', account: 'student', grade: '10', class_number: '1' }], school: school.name }
    else if (path.endsWith('/exam-management')) data = { items: [], total: 0, grades: [], subjects: [] }
    await route.fulfill({ json: data })
  })
  return creates
}

test('super admin creates a school account, retries duplicate names, and sees the new account', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const creates = await setup(page, true)
  await page.goto('/ops/administrators')
  await expect(page.getByRole('tab', { name: '注册密钥' })).toHaveCount(0)
  await page.getByRole('combobox', { name: '学校编码', exact: true }).selectOption(school.id)
  await page.getByRole('button', { name: '+ 新增学校管理员', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新增学校管理员' })
  await expect(dialog.getByLabel('管理学校')).toHaveValue(school.id)
  await expect(dialog.getByLabel('管理学校').locator('option')).toHaveCount(2)
  await dialog.getByLabel('管理员姓名').fill('测试教务员')
  await dialog.getByLabel('登录账号（可选）').fill('01234567')
  await dialog.getByLabel('权限方案').selectOption('EXAM_ADMIN')
  await dialog.getByLabel('初始密码', { exact: true }).fill('synthetic-password')
  await dialog.getByLabel('确认初始密码', { exact: true }).fill('different-password')
  await expect(dialog.getByRole('alert')).toContainText('两次输入的初始密码不一致')
  await expect(dialog.getByRole('button', { name: '创建管理员', exact: true })).toBeDisabled()
  expect(creates).toHaveLength(0)
  await dialog.getByLabel('确认初始密码', { exact: true }).fill('synthetic-password')
  await dialog.getByRole('button', { name: '创建管理员', exact: true }).click()
  await expect(dialog).toContainText('该八位账号已被使用')
  await expect(dialog.getByLabel('管理员姓名')).toHaveValue('测试教务员')
  await dialog.getByLabel('登录账号（可选）').fill('')
  await dialog.getByRole('button', { name: '创建管理员', exact: true }).click()
  await expect(dialog.getByRole('heading', { name: '学校管理员已创建' })).toBeVisible()
  await expect(dialog.getByLabel('登录账号')).toHaveValue('87654321')
  expect(creates[1]).toMatchObject({ username: '', school_id: school.id, roles: ['EXAM_ADMIN'], must_change_password: true })
  await dialog.getByRole('button', { name: '完成', exact: true }).click()
  await expect(page.getByRole('cell', { name: /测试教务员/ })).toBeVisible()
  await expect(page.getByRole('cell', { name: /考务管理/ })).toBeVisible()
  expect(errors).toEqual([])
})

test('creation dialog fits mobile and public registration returns to login', async ({ page }) => {
  await setup(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/ops/administrators')
  await page.getByRole('button', { name: '+ 新增学校管理员', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('首次登录必须修改密码')).toBeChecked()
  expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('create-admin-mobile.png'), fullPage: true })
  await page.goto('/register-administrator')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('学校管理员账号由超级管理员创建。', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /注册/ })).toHaveCount(0)
})

test('exam participant step displays the red absence reminder', async ({ page }) => {
  await setup(page, false, ['SCHOOL_ADMIN'])
  await page.goto('/admin/school?tab=exam-management')
  await page.getByRole('button', { name: '＋ 创建考试', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('考试名称', { exact: true }).fill('测试考试')
  await dialog.getByLabel('考试学年', { exact: true }).selectOption('2026-2027')
  await dialog.getByLabel('考试日期', { exact: true }).fill('2026-11-05')
  await dialog.getByRole('button', { name: '校验并下一步', exact: true }).click()
  await dialog.getByRole('checkbox', { name: '高中一年级', exact: true }).check()
  await dialog.getByRole('button', { name: '下一步：选择参试学生', exact: true }).click()
  const reminder = dialog.getByText('不包含【缺考】学生', { exact: true })
  await expect(reminder).toBeVisible()
  await expect(reminder).toHaveCSS('color', 'rgb(198, 40, 40)')
  await page.screenshot({ path: test.info().outputPath('exam-absence-reminder.png'), fullPage: true })
})

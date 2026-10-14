import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, 'utf8'))
const root = path.resolve(__dirname, '../..')
const base = '/api/v1/platform/education/roster'
const source = process.env.QA_STUDENT_IMPORT_SOURCE || path.join(root, 'apps/api/tests/fixtures/student_roster_legacy_headers.xls')
const expectedRows = Number(process.env.QA_STUDENT_IMPORT_ROWS || 2)

async function admin(page: Page, request: APIRequestContext) {
  const login = await request.post('/api/v1/auth/login', { data: { username: fixture.users.admin, password: process.env.QA_PASSWORD } })
  expect(login.ok()).toBeTruthy()
  await page.goto('/login')
  await page.getByLabel('用户名').fill(fixture.users.admin)
  await page.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).not.toHaveURL(/\/login$/)
  await page.goto('/admin/school?tab=students')
  await expect(page.getByRole('heading', { name: '学生信息列表' })).toBeVisible()
  return { Authorization: `Bearer ${(await login.json()).access_token}` }
}

test('current template and historical .xls headers pass; confirmation preserves data and repeated imports are blocked', async ({ page, request }) => {
  const headers = await admin(page, request)
  await page.setViewportSize({ width: 1920, height: 1000 })
  const before = await (await request.get(base + '/students/records', { headers })).json()
  await page.getByRole('button', { name: '导入学生', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const downloadPromise = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '下载《学生资料模板.xlsx》' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('学生资料模板.xlsx')
  await dialog.getByLabel('上传学生资料模板').setInputFiles({ name: download.suggestedFilename(), mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: readFileSync((await download.path())!) })
  await dialog.getByRole('button', { name: '开始预校验', exact: true }).click()
  await expect(dialog.getByText(/预校验通过，共 1 行/)).toBeVisible()
  await dialog.getByRole('button', { name: '重新上传', exact: true }).click()
  await dialog.getByLabel('上传学生资料模板').setInputFiles(source)
  const uploadResponse = page.waitForResponse(response => response.url().includes(base + '/students/imports') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: '开始预校验', exact: true }).click()
  const batch = await (await uploadResponse).json()
  expect(batch.report.ok).toBe(true)
  expect(batch.report.total_rows).toBe(expectedRows)
  await expect(dialog.getByText(`预校验通过，共 ${expectedRows} 行。`, { exact: false })).toBeVisible()
  expect((await (await request.get(base + '/students/records', { headers })).json()).total).toBe(before.total)
  await page.screenshot({ path: test.info().outputPath('legacy-xls-preflight.png'), fullPage: true })
  await dialog.getByRole('button', { name: '下一步：同班同名确认' }).click()
  for (const checkbox of await dialog.getByRole('checkbox', { name: '已核实本行选择' }).all()) await checkbox.check()
  await dialog.getByRole('button', { name: '确认入库', exact: true }).click()
  await expect(dialog.getByText('导入完成', { exact: true })).toBeVisible()
  await expect(dialog.getByText(`成功 ${expectedRows} 条 · 放弃 0 条`, { exact: true })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('legacy-xls-receipt.png'), fullPage: true })
  const saved = await (await request.get(base + `/imports/${batch.id}`, { headers })).json()
  expect(saved.report.success_count).toBe(expectedRows)
  const original = await request.get(base + `/imports/${batch.id}/original`, { headers })
  expect(await original.body()).toEqual(readFileSync(source))
  for (const imported of saved.report.imported) {
    const record = await (await request.get(base + `/students/records/${imported.id}`, { headers })).json()
    const values = batch.rows.find((row: { row_number: number }) => row.row_number === imported.row_number).values
    expect(Object.keys(values)).toHaveLength(30)
    expect(record.fields).toMatchObject(values)
    expect(record.platform_id).toMatch(/^[1-9][0-9]{7,9}$/)
  }
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByLabel('学生关键词').fill(batch.rows[0].values.账号)
  await expect(page.locator('.student-table tbody tr')).toHaveCount(1)
  await page.screenshot({ path: test.info().outputPath('legacy-xls-student-list.png'), fullPage: true })
  await page.getByRole('button', { name: '导入学生', exact: true }).click()
  await dialog.getByLabel('上传学生资料模板').setInputFiles(source)
  await dialog.getByRole('button', { name: '开始预校验', exact: true }).click()
  await expect(dialog.getByText('校验失败，整份退回', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: '下一步：同班同名确认' })).toBeDisabled()
  await expect(dialog.getByText(/与系统已有学生账号重复/).first()).toBeVisible()
  expect((await (await request.get(base + '/students/records', { headers })).json()).total).toBe(before.total + expectedRows)
  await page.screenshot({ path: test.info().outputPath('legacy-xls-repeat-blocked.png'), fullPage: true })
})

test('wrong column order reports its position and keeps the student count unchanged', async ({ page, request }) => {
  const headers = await admin(page, request)
  const before = await (await request.get(base + '/students/records', { headers })).json()
  const buffer = execFileSync(path.join(root, '.venv/bin/python'), ['-c', 'import sys;from app.services.roster_excel import STUDENT_COLUMNS,workbook_bytes;c=STUDENT_COLUMNS.copy();c[4],c[5]=c[5],c[4];sys.stdout.buffer.write(workbook_bytes(c,[[""]*30]))'], { env: { ...process.env, PYTHONPATH: path.join(root, 'apps/api') } })
  await page.getByRole('button', { name: '导入学生', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('上传学生资料模板').setInputFiles({ name: '学生错序模板.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer })
  await dialog.getByRole('button', { name: '开始预校验', exact: true }).click()
  await expect(dialog.getByText(/第 5 列应为「姓名」，实际为「账号」/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: '下一步：同班同名确认' })).toBeDisabled()
  const downloadPromise = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '下载错误清单', exact: true }).click()
  expect((await downloadPromise).suggestedFilename()).toBe('学生导入错误清单.xlsx')
  expect((await (await request.get(base + '/students/records', { headers })).json()).total).toBe(before.total)
  await page.screenshot({ path: test.info().outputPath('student-header-order-error.png'), fullPage: true })
})

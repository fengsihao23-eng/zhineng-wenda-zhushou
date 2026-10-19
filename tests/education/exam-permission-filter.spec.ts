import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { readFileSync, mkdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, 'utf8'))
const root = path.resolve(__dirname, '../..')
const base = '/api/v1/platform/education/exam-management'
const evidence = process.env.QA_EXAM_EVIDENCE || '/tmp/exam-permission-filter-evidence'
mkdirSync(evidence, { recursive: true })

async function prepare(request: APIRequestContext, name: string) {
  const login = await request.post('/api/v1/auth/login', { data: { username: fixture.users.admin, password: process.env.QA_PASSWORD } })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: 'Bearer ' + (await login.json()).access_token }
  const body = { name, academic_year: '2026-2027', exam_date: '2026-10-19', subjects: ['语文', '数学'].map((name, i) => ({ key: String(i), name, full_score: 150, student_ids: fixture.students.slice(0, 3).map((p: any) => p.id) })) }
  const preview = await request.post(base + '/preview', { headers, data: body }); expect(preview.ok()).toBeTruthy()
  const created = await request.post(base, { headers, data: { ...body, preview_hash: (await preview.json()).preview_hash } }); expect(created.ok()).toBeTruthy()
  const exam = await created.json(), subject = exam.subjects[0].subject_id
  const template = await request.get(`${base}/${exam.id}/score-template/${subject}`, { headers })
  const content = execFileSync(path.join(root, '.venv/bin/python'), ['-c', `import io,sys
from openpyxl import load_workbook
b=load_workbook(io.BytesIO(sys.stdin.buffer.read()));s=b.active
for r in range(2,s.max_row+1):s.cell(r,7,90)
out=io.BytesIO();b.save(out);sys.stdout.buffer.write(out.getvalue())`], { input: await template.body() })
  const checked = await request.post(`${base}/${exam.id}/score-files`, { headers, data: { subject_id: subject, expected_revision: exam.revision, filename: '筛选关联验收.xlsx', content_base64: content.toString('base64') } }); expect(checked.ok()).toBeTruthy()
  const imported = await request.post(`${base}/${exam.id}/score-files/${(await checked.json()).id}/confirm`, { headers }); expect(imported.ok()).toBeTruthy()
  return { headers, exam: await imported.json() }
}

async function open(page: Page, name: string) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(fixture.users.admin)
  await page.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).not.toHaveURL(/\/login$/)
  await page.goto('/admin/school?tab=exam-management')
  await page.getByRole('row').filter({ has: page.getByText(name, { exact: true }) }).getByRole('button', { name: '成绩开放设置', exact: true }).click()
  return page.getByRole('dialog')
}

test('teacher filter options include grades, classes and subjects outside the exam without creating false defaults', async ({ page, request }) => {
  await page.setViewportSize({ width: 1600, height: 1100 })
  const name = '跨年级教师筛选验收 ' + Date.now(), { exam, headers } = await prepare(request, name)
  const dialog = await open(page, name)
  const grade = dialog.getByLabel('授权教师年级筛选', { exact: true })
  const classroom = dialog.getByLabel('授权教师班级筛选', { exact: true })
  const subject = dialog.getByLabel('授权教师学科筛选', { exact: true })
  await expect(grade.locator('option')).toHaveText(['全部年级', '高中一年级', '高中二年级', '高中三年级'])
  await expect(subject.locator('option')).toContainText(['全部学科', '化学', '数学', '物理', '英语', '语文'])
  await expect(classroom.locator('option')).toContainText(['高中一年级 22班', '高中二年级 1班', '高中三年级 2班'])
  await grade.selectOption('高中二年级')
  await expect(classroom.locator('option')).toHaveText(['全部班级', '高中二年级 1班'])
  await classroom.selectOption('高中二年级 / 1'); await subject.selectOption('物理')
  await expect(dialog.locator('.exam-teacher-row')).toHaveCount(1)
  const person = dialog.locator('.exam-teacher-row').filter({ hasText: fixture.users.teacheroutside })
  await person.getByRole('checkbox').check()
  const options = await (await request.get(`${base}/teachers?exam_id=${exam.id}`, { headers })).json()
  const teacher = options.items.find((p: any) => p.account === fixture.users.teacheroutside)
  await expect(dialog.getByRole('heading', { name: `当前编辑：${teacher.name}（${teacher.platform_id}）`, exact: true })).toBeVisible()
  await expect(dialog.getByRole('region', { name: '当前教师信息' })).toContainText(fixture.users.teacheroutside)
  await expect(dialog.getByRole('checkbox', { name: '成绩科目：语文', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '报告科目：数学', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '授权班级：高中一年级 1班', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('region', { name: '当前教师授权预览' })).toContainText('当前范围覆盖 0 名参试学生')
  await expect(dialog.getByRole('checkbox', { name: '语种 · 个人报告：英语（本次考试未配置）', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: '确认保存生效', exact: true }).click()
  await expect(dialog.getByText(/配置尚未完整/).first()).toBeVisible()
  await page.screenshot({ path: path.join(evidence, '18-outside-exam-teacher-filter.png'), fullPage: true })
  await dialog.getByRole('button', { name: '重置筛选', exact: true }).click()
  await expect(grade).toHaveValue(''); await expect(classroom).toHaveValue(''); await expect(subject).toHaveValue('')
  expect((await (await request.get(`${base}/${exam.id}`, { headers })).json()).teacher_permissions).toEqual({})
})

test('teacher identity, selected subjects and student scope stay bound through filtering, batch selection, save and reload', async ({ page, request }) => {
  await page.setViewportSize({ width: 1600, height: 1100 })
  const name = '教师草稿关联验收 ' + Date.now(), { exam, headers } = await prepare(request, name)
  const dialog = await open(page, name)
  const first = dialog.locator('.exam-teacher-row').filter({ hasText: fixture.users.teacher })
  const second = dialog.locator('.exam-teacher-row').filter({ hasText: fixture.users.teacher2 })
  await first.getByRole('checkbox').check()
  await expect(dialog.getByRole('checkbox', { name: '报告科目：数学', exact: true })).toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '报告科目：语文', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '授权班级：高中一年级 1班', exact: true })).toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '授权班级：高中一年级 2班', exact: true })).not.toBeChecked()
  await dialog.getByRole('checkbox', { name: '成绩科目：语文', exact: true }).check()
  await expect(dialog.getByRole('checkbox', { name: '成绩类型：个人单科成绩', exact: true })).toBeChecked()
  await dialog.getByRole('checkbox', { name: '报告类型：班级综合诊断', exact: true }).check()
  await second.getByRole('checkbox').check()
  await expect(dialog.getByRole('checkbox', { name: '成绩类型：班级综合成绩', exact: true })).toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '授权班级：高中一年级 2班', exact: true })).toBeChecked()
  await dialog.getByRole('checkbox', { name: '报告类型：班级综合诊断', exact: true }).uncheck()
  await dialog.getByLabel('授权教师班级筛选', { exact: true }).selectOption('高中一年级 / 1')
  await dialog.getByLabel('授权教师职务筛选', { exact: true }).selectOption('TEACHER')
  await expect(dialog.getByText(/其中 1 位不在当前筛选内/)).toBeVisible()
  await expect(dialog.getByRole('heading', { name: /当前编辑：语文教师乙/ })).toBeVisible()
  await dialog.locator('.exam-permission-heading').getByRole('button', { name: '数学教师甲', exact: true }).click()
  await expect(dialog.getByRole('checkbox', { name: '报告类型：班级综合诊断', exact: true })).toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '授权班级：高中一年级 2班', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('region', { name: '当前教师授权预览' })).toContainText('当前范围覆盖 2 名参试学生')
  await dialog.getByRole('button', { name: '确认保存生效', exact: true }).click()
  await expect(dialog.getByText('保存成功，已更新 2 位教师的查询权限。')).toBeVisible()
  const saved = await (await request.get(`${base}/${exam.id}`, { headers })).json()
  const one = saved.teacher_permissions[fixture.user_ids.teacher], two = saved.teacher_permissions[fixture.user_ids.teacher2]
  expect(one.teacher_id).toBe(fixture.user_ids.teacher); expect(two.teacher_id).toBe(fixture.user_ids.teacher2)
  expect(one.classes).toEqual(['高中一年级 / 1']); expect(two.classes).toEqual(['高中一年级 / 1', '高中一年级 / 2'])
  expect(one.diagnosis_types).toContain('classAll'); expect(two.diagnosis_types).not.toContain('classAll')
  expect(one.frozen_student_ids).toHaveLength(2); expect(two.frozen_student_ids).toHaveLength(3)
  await page.screenshot({ path: path.join(evidence, '19-teacher-drafts-bound-after-save.png'), fullPage: true })
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await page.reload()
  await page.getByRole('row').filter({ has: page.getByText(name, { exact: true }) }).getByRole('button', { name: '成绩开放设置', exact: true }).click()
  await first.getByRole('checkbox').check()
  await expect(dialog.getByRole('region', { name: '当前教师信息' })).toContainText('配置来源：已保存的授权')
  await expect(dialog.getByRole('checkbox', { name: '报告类型：班级综合诊断', exact: true })).toBeChecked()
  await dialog.getByRole('button', { name: '重新按档案预选', exact: true }).click()
  await expect(dialog.getByRole('checkbox', { name: '报告类型：班级综合诊断', exact: true })).not.toBeChecked()
  await expect(dialog.getByRole('checkbox', { name: '成绩科目：语文', exact: true })).not.toBeChecked()
  await dialog.getByRole('button', { name: '清空已选教师', exact: true }).click()
  await expect(dialog.getByRole('button', { name: '确认保存生效', exact: true })).toBeDisabled()
})

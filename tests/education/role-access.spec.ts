import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { readFileSync, mkdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, 'utf8'))
const root = path.resolve(__dirname, '../..'), evidence = process.env.QA_EXAM_EVIDENCE!
const base = '/api/v1/platform', exams = base + '/education/exam-management'
mkdirSync(evidence, { recursive: true })

async function auth(request: APIRequestContext, name: string) {
  const response = await request.post('/api/v1/auth/login', { data: { username: fixture.users[name], password: process.env.QA_PASSWORD } })
  expect(response.status()).toBe(200)
  return { Authorization: 'Bearer ' + (await response.json()).access_token }
}

async function login(page: Page, name: string) {
  await page.goto('/login'); await page.getByLabel('用户名').fill(fixture.users[name]); await page.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!)
  const response = page.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const result = await (await response).json()
  await expect(page).not.toHaveURL(/\/login$/)
  return result
}

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const response = await request.post(url, { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data })
  expect(response.ok(), await response.text()).toBeTruthy()
  return response.json()
}

async function scoredExam(request: APIRequestContext) {
  const headers = await auth(request, 'admin')
  const body = { name: '角色范围回归 ' + Date.now(), academic_year: '2026-2027', exam_date: '2026-10-20', subjects: [{ key: 'math', name: '数学', full_score: 150, student_ids: fixture.students.slice(0, 3).map((student: any) => student.id) }] }
  const preview = await post(request, exams + '/preview', headers, body)
  let exam = await post(request, exams, headers, { ...body, preview_hash: preview.preview_hash })
  const template = await request.get(`${exams}/${exam.id}/score-template/${exam.subjects[0].subject_id}`, { headers })
  const bytes = execFileSync(path.join(root, '.venv/bin/python'), ['-c', `import io,sys
from openpyxl import load_workbook
b=load_workbook(io.BytesIO(sys.stdin.buffer.read()));s=b.active
for n in range(2,s.max_row+1):s.cell(n,7,85+n)
o=io.BytesIO();b.save(o);sys.stdout.buffer.write(o.getvalue())`], { input: await template.body() })
  const checked = await post(request, `${exams}/${exam.id}/score-files`, headers, { subject_id: exam.subjects[0].subject_id, expected_revision: exam.revision, filename: 'role-access.xlsx', content_base64: bytes.toString('base64') })
  exam = await post(request, `${exams}/${exam.id}/score-files/${checked.id}/confirm`, headers, undefined)
  const teachers = ['access_teacher', 'access_exam'].map(name => ({ teacher_id: fixture.user_ids[name], score_types: ['student', 'classSubject'], score_subjects: [exam.subjects[0].subject_id], diagnosis_types: [], diagnosis_subjects: [], essay_types: [], range_type: 'class', grades: [], classes: ['高中一年级 / 1'] }))
  exam = await post(request, `${exams}/${exam.id}/permissions/teacher`, headers, { expected_revision: exam.revision, teachers })
  return { exam, headers }
}

test('school reader opens all management queues and sees read-only controls', async ({ page, request }) => {
  await page.setViewportSize({ width: 1500, height: 1000 })
  const student = await auth(request, 'access_runtime'), admin = await auth(request, 'admin')
  await post(request, base + '/student/feedback', student, { rating: 'not_helpful', category: '角色只读回归', note: '合成反馈' })
  await post(request, base + '/student/handoffs', student, { reason: '角色只读回归求助', summary: '合成求助' })
  await post(request, base + '/management/risks', admin, { student_id: fixture.role_access.students.runtime, event_type: 'role-audit', title: '角色只读回归风险', detail: '合成事件', severity: 'low' })
  await login(page, 'access_viewer')
  for (const [route, endpoint] of [['/admin', 'overview'], ['/admin/students', 'students'], ['/admin/feedback', 'feedback'], ['/admin/risks', 'risks'], ['/admin/handoffs', 'handoffs']]) {
    const response = page.waitForResponse(r => r.url().includes('/platform/management/' + endpoint) && r.request().method() === 'GET' && r.status() !== 401)
    await page.goto(route)
    expect((await response).status()).toBe(200)
    await expect(page.getByRole('heading', { name: '无权访问此页面', exact: true })).toHaveCount(0)
    await expect(page.locator('.workflow-controls .card-actions button')).toHaveCount(0)
  }
  await page.screenshot({ path: path.join(evidence, '01-school-reader-management.png'), fullPage: true })
})

test('teacher with school read access handles own class help and cannot handle outside requests', async ({ page, request }) => {
  await page.setViewportSize({ width: 1500, height: 1000 })
  const student = await auth(request, 'access_runtime'), outside = await auth(request, 'access_outside'), teacher = await auth(request, 'access_principal')
  const reason = '兼任教师本班求助 ' + Date.now()
  const own = await post(request, base + '/student/handoffs', student, { reason, summary: '需要老师帮助安排复习' })
  const other = await post(request, base + '/student/handoffs', outside, { reason: '班外求助 ' + Date.now(), summary: '仅供只读查询' })
  await login(page, 'access_principal'); await page.goto('/admin/handoffs')
  const card = page.locator('.handoff-card').filter({ has: page.getByRole('heading', { name: reason, exact: true }) })
  await card.getByRole('button', { name: '接单', exact: true }).click()
  await expect(card.getByRole('button', { name: '完成跟进', exact: true })).toBeVisible()
  const detail = await request.get(base + '/education/handoffs/' + own.id, { headers: teacher })
  expect(detail.status()).toBe(200); expect((await detail.json()).can_reply).toBe(true)
  const reply = await post(request, base + '/education/handoffs/' + own.id + '/messages', teacher, { content: '已收到，我会在本班跟进学习安排。' })
  expect(reply.messages.at(-1).content).toContain('本班跟进')
  const outsideDetail = await request.get(base + '/education/handoffs/' + other.id, { headers: teacher })
  expect(outsideDetail.status()).toBe(200); expect((await outsideDetail.json()).can_reply).toBe(false)
  expect((await request.patch(base + '/management/handoffs/' + other.id, { headers: teacher, data: { status: 'accepted', expected_version: 1 } })).status()).toBe(404)
  await card.getByRole('button', { name: '完成跟进', exact: true }).click()
  await card.getByRole('textbox').fill('已经与学生核对并完成跟进。')
  const completed = page.waitForResponse(response => response.url().endsWith('/management/handoffs/' + own.id) && response.request().method() === 'PATCH')
  await card.getByRole('button', { name: '确认完成跟进', exact: true }).click()
  expect((await completed).status()).toBe(200)
  const final = await request.get(base + '/education/handoffs/' + own.id, { headers: teacher })
  expect((await final.json()).status).toBe('resolved')
  await page.screenshot({ path: path.join(evidence, '02-concurrent-duty-student-help.png'), fullPage: true })
})

test('super administrator drills into learning details and exam duty preserves teaching scope', async ({ page, request }) => {
  const { exam } = await scoredExam(request)
  const plain = await auth(request, 'access_teacher'), combined = await auth(request, 'access_exam')
  const summaries = []
  for (const headers of [plain, combined]) {
    const students = await request.get(base + '/management/students', { headers })
    const own = await request.get(base + '/management/students/' + fixture.students[0].id, { headers })
    const outside = await request.get(base + '/management/students/' + fixture.students[2].id, { headers })
    const analysis = await request.get(base + '/education/class-analysis', { headers, params: { class_id: fixture.role_access.class_id, subject_id: fixture.role_access.subject_id, exam_id: exam.id } })
    expect(students.status()).toBe(200); expect(own.status()).toBe(200); expect(outside.status()).toBe(404); expect(analysis.status()).toBe(200)
    summaries.push({ students: (await students.json()).map((student: any) => student.id).sort(), subjects: (await own.json()).subject_scores, analysis: (await analysis.json()).sample_size })
  }
  expect(summaries[0]).toEqual(summaries[1])
  expect((await request.get(exams + '/' + exam.id, { headers: plain })).status()).toBe(403)
  expect((await request.get(exams + '/' + exam.id, { headers: combined })).status()).toBe(200)
  await login(page, 'access_super'); await page.goto('/admin/analysis')
  await page.getByRole('combobox', { name: '班级', exact: true }).selectOption(fixture.role_access.class_id)
  await page.getByRole('combobox', { name: '学科', exact: true }).selectOption(fixture.role_access.subject_id)
  await page.getByRole('combobox', { name: '考试', exact: true }).selectOption(exam.id)
  const drill = page.getByRole('link', { name: '查看学情', exact: true }).first()
  await expect(drill).toBeVisible(); await drill.click()
  await expect(page.getByRole('heading', { name: '学科成绩', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '无权访问此页面', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: '← 返回学生列表', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/students$/)
  await page.screenshot({ path: path.join(evidence, '03-super-admin-learning-drilldown.png'), fullPage: true })
})

test('preview requires an eligible signed-in identity and errors preserve the backend session', async ({ browser, request }) => {
  const anonymous = await browser.newContext(), anonymousPage = await anonymous.newPage()
  await anonymousPage.goto('/mini-preview'); await expect(anonymousPage).toHaveURL(/\/login$/); await anonymous.close()
  const admin = await browser.newContext(), adminPage = await admin.newPage()
  const session = await login(adminPage, 'admin'); await adminPage.goto('/mini-preview')
  await expect(adminPage.getByRole('heading', { name: '无权访问此页面', exact: true })).toBeVisible()
  await expect(adminPage.locator('iframe')).toHaveCount(0)
  await adminPage.getByRole('link', { name: '返回我的工作台', exact: true }).click()
  await expect(adminPage).not.toHaveURL(/\/login$/)
  expect((await request.get('/api/v1/auth/me', { headers: { Authorization: 'Bearer ' + session.access_token } })).status()).toBe(200)
  await admin.close()
  const student = await browser.newContext(), studentPage = await student.newPage()
  const studentSession = await login(studentPage, 'access_runtime')
  await studentPage.route('**/answer-workbench/mini/state', route => route.fulfill({ status: 503, json: { detail: '临时读取失败，请重试' } }))
  await studentPage.goto('/mini-preview')
  const frame = studentPage.frameLocator('iframe[title="学科智能问答小程序"]')
  await expect(frame.getByRole('button', { name: '返回工作台', exact: true })).toBeVisible()
  await expect(frame.getByRole('button', { name: '返回登录', exact: true })).toHaveCount(0)
  await frame.getByRole('button', { name: '返回工作台', exact: true }).click()
  await expect(studentPage).not.toHaveURL(/\/login$/)
  expect((await request.get('/api/v1/auth/me', { headers: { Authorization: 'Bearer ' + studentSession.access_token } })).status()).toBe(200)
  await student.close()
})

test('password enforcement redirects from an active chat and password change restores access', async ({ page }) => {
  await login(page, 'access_initial'); await expect(page).toHaveURL(/\/change-password$/)
  await page.goto('/login'); await login(page, 'access_runtime'); await page.goto('/chat')
  const frame = page.frameLocator('iframe[title="智能问答助手"]')
  await frame.getByLabel('输入问题').fill('你好')
  execFileSync(path.join(root, '.venv/bin/python'), [path.join(root, 'tests/education/seed-role-access.py'), process.env.QA_FIXTURE_PATH!, 'force-password'], { env: process.env })
  const denied = page.waitForResponse(response => response.url().endsWith('/answer-workbench/mini/ask') && response.request().method() === 'POST')
  await frame.getByLabel('发送问题').click(); expect((await denied).status()).toBe(403)
  await expect(page).toHaveURL(/\/change-password$/)
  await page.getByLabel('当前密码', { exact: true }).fill(process.env.QA_PASSWORD!)
  await page.getByLabel('新密码（至少 8 位）', { exact: true }).fill(process.env.QA_PASSWORD! + '-changed')
  await page.getByLabel('再次输入新密码', { exact: true }).fill(process.env.QA_PASSWORD! + '-changed')
  await page.getByRole('button', { name: '修改密码并进入系统', exact: true }).click()
  await expect(page).not.toHaveURL(/\/change-password$/)
  await page.goto('/chat'); await expect(frame.getByLabel('输入问题')).toBeVisible()
  await page.screenshot({ path: path.join(evidence, '04-password-change-recovered-chat.png'), fullPage: true })
})

import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { readFileSync, mkdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, 'utf8'))
const root = path.resolve(__dirname, '../..'), base = '/api/v1/platform/education/report-management', examsBase = '/api/v1/platform/education/exam-management'
const evidence = process.env.QA_EXAM_EVIDENCE || '/tmp/report-r86-evidence'
mkdirSync(evidence, { recursive: true })
const types: Record<string, string> = { student: '个人学情诊断', classAll: '班级综合诊断', classSubject: '班级单科诊断', gradeAll: '年级综合诊断', gradeSubject: '年级单科诊断', school: '全校学情诊断', essay: '个人作文批改报告' }
const pdf = (text = 'SYNTHETIC REPORT v1') => execFileSync(path.join(root, '.venv/bin/python'), ['-c', `import io,sys
from PIL import Image,ImageDraw,ImageFont
images=[]
for n in range(2):
 image=Image.new('RGB',(595,842),'white');draw=ImageDraw.Draw(image)
 draw.rectangle((0,0,595,130),fill='#efedfd');draw.text((35,45),sys.argv[1],fill='#5348d8',font=ImageFont.load_default(size=23))
 draw.text((35,170),'BANG report acceptance / page '+str(n+1),fill='#202736',font=ImageFont.load_default(size=15))
 for i,v in enumerate([0.7,0.9,0.6,0.8]):
  draw.rectangle((35,240+i*65,550,270+i*65),fill='#f0f2f7');draw.rectangle((35,240+i*65,35+500*v,270+i*65),fill='#aaa3e4')
 images.append(image)
output=io.BytesIO();images[0].save(output,format='PDF',save_all=True,append_images=images[1:]);sys.stdout.buffer.write(output.getvalue())`, text])
const originalPdf = pdf(), replacementPdf = pdf('SYNTHETIC REPORT v2')

async function login(page: Page, kind = 'admin') {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(fixture.users[kind])
  await page.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
}

async function headers(request: APIRequestContext, kind = 'admin') {
  const response = await request.post('/api/v1/auth/login', { data: { username: fixture.users[kind], password: process.env.QA_PASSWORD } })
  expect(response.ok()).toBeTruthy()
  return { Authorization: 'Bearer ' + (await response.json()).access_token }
}

async function post(request: APIRequestContext, url: string, auth: Record<string, string>, data: unknown) {
  const response = await request.post(url, { headers: auth, data })
  expect(response.ok(), await response.text()).toBeTruthy()
  return response.json()
}

async function createExam(request: APIRequestContext, name: string, scored = false) {
  const auth = await headers(request), body = { name, academic_year: '2026-2027', exam_date: '2026-10-19', subjects: ['语文', '数学', '英语'].map((name, i) => ({ key: String(i), name, full_score: 150, student_ids: fixture.students.slice(0, 3).map((student: any) => student.id) })) }
  const preview = await post(request, examsBase + '/preview', auth, body)
  let exam = await post(request, examsBase, auth, { ...body, preview_hash: preview.preview_hash })
  if (scored) {
    const response = await request.get(`${examsBase}/${exam.id}/score-template/${exam.subjects[0].subject_id}`, { headers: auth })
    const content = execFileSync(path.join(root, '.venv/bin/python'), ['-c', `import io,sys
from openpyxl import load_workbook
book=load_workbook(io.BytesIO(sys.stdin.buffer.read()));sheet=book.active
for n in range(2,sheet.max_row+1):sheet.cell(n,7,90)
out=io.BytesIO();book.save(out);sys.stdout.buffer.write(out.getvalue())`], { input: await response.body() })
    const checked = await post(request, `${examsBase}/${exam.id}/score-files`, auth, { expected_revision: exam.revision, subject_id: exam.subjects[0].subject_id, filename: '合成报告授权成绩.xlsx', content_base64: content.toString('base64') })
    exam = await post(request, `${examsBase}/${exam.id}/score-files/${checked.id}/confirm`, auth, undefined)
  }
  const scope = await (await request.get(base + '/exams/' + exam.id, { headers: auth })).json()
  return { auth, exam, scope }
}

function reportRow(scope: any, type = 'student', index = 0, subjectIndex = 0) {
  const subject = scope.subjects[subjectIndex], sid = subject.student_ids[index], student = scope.snapshots[sid]
  const kind = ['student', 'essay'].includes(type) ? 'student' : type.startsWith('class') ? 'class' : type.startsWith('grade') ? 'grade' : 'school'
  const target = kind === 'student' ? sid : kind === 'class' ? student.grade + '|' + student.class_number : kind === 'grade' ? student.grade : 'school'
  const identity = kind === 'student' ? [student.platform_id, student.name] : kind === 'class' ? target.split('|') : [kind === 'school' ? '本校' : target]
  const filename = [scope.exam_code, ...identity, subject.name, types[type]].join('_') + '.pdf'
  const config = { category: type === 'essay' ? 'essay' : 'diagnostic', report_type: type, subject_ids: [subject.subject_id] }
  return { ...config, target_key: target, file: { filename, content_base64: originalPdf.toString('base64') }, naming: config, previewed: true }
}

async function saveRows(request: APIRequestContext, setup: any, rows: any[]) {
  const body = { exam_id: setup.exam.id, expected_exam_revision: setup.exam.revision, reports: rows }
  const preview = await post(request, base + '/batches/preview', setup.auth, body)
  return post(request, base + '/batches', setup.auth, { ...body, preview_hash: preview.preview_hash })
}

async function chooseExam(page: Page, name: string) {
  await page.getByRole('combobox', { name: '上传所属考试', exact: true }).fill(name)
  await page.getByRole('listbox', { name: '上传所属考试匹配结果', exact: true }).getByRole('option', { name: new RegExp(name) }).click()
  await expect(page.getByRole('radio', { name: '语文', exact: true })).toBeVisible()
}

async function renderPreview(page: Page, button = '预览 PDF') {
  await page.getByRole('button', { name: button, exact: true }).click()
  const preview = page.getByRole('dialog', { name: 'PDF预览', exact: true })
  await expect(preview.getByRole('img', { name: 'PDF第1页' })).toBeVisible()
  return preview
}

test('prototype upload wizard validates names, previews every file and persists a real batch', async ({ page, request }) => {
  const setup = await createExam(request, '报告r86三步上传验收'), rows = [reportRow(setup.scope), reportRow(setup.scope, 'student', 1)]
  await page.setViewportSize({ width: 1600, height: 1100 }); await login(page)
  await page.goto('/admin/reports'); await page.getByRole('button', { name: '＋ 上传报告', exact: true }).click()
  await chooseExam(page, setup.exam.name)
  const drawer = page.getByRole('dialog', { name: '上传报告', exact: true })
  await expect(drawer.getByRole('button', { name: '下一步：预览归属' })).toBeDisabled()
  await drawer.getByRole('radio', { name: '语文', exact: true }).check()
  const downloading = page.waitForEvent('download'); await drawer.getByRole('button', { name: '下载本次范围命名清单' }).click()
  const naming = await downloading; expect(readFileSync((await naming.path())!, 'utf8')).toContain(rows[0].file.filename)
  await drawer.getByLabel('上传 PDF 文件').setInputFiles({ name: '不规范文件.pdf', mimeType: 'application/pdf', buffer: originalPdf })
  await expect(drawer.getByText(/命名格式不规范/)).toBeVisible()
  await expect(drawer.getByRole('button', { name: '下一步：预览归属' })).toBeDisabled()
  await drawer.getByRole('button', { name: '移除', exact: true }).click()
  await drawer.getByLabel('上传 PDF 文件').setInputFiles(rows.map(row => ({ name: row.file.filename, mimeType: 'application/pdf', buffer: originalPdf })))
  await expect(drawer.getByText('校验通过 2 / 2 份')).toBeVisible()
  await drawer.getByRole('button', { name: '下一步：预览归属' }).hover()
  await expect(drawer.getByRole('button', { name: '下一步：预览归属' })).toHaveCSS('color', 'rgb(255, 255, 255)')
  await page.screenshot({ path: path.join(evidence, '01-upload-scope-and-naming.png'), fullPage: true })
  await drawer.getByRole('button', { name: '下一步：预览归属' }).click()
  await drawer.getByRole('button', { name: '下一步：核对清单' }).click()
  await expect(drawer.getByRole('alert')).toContainText('请先预览 PDF')
  let preview = await renderPreview(page)
  await preview.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(preview.getByRole('img', { name: 'PDF第2页' })).toBeVisible()
  await page.screenshot({ path: path.join(evidence, '02-real-pdf-preview.png'), fullPage: true })
  await preview.getByRole('button', { name: '关闭PDF预览' }).click()
  await expect(drawer).toBeVisible()
  await drawer.locator('.file-entry').nth(1).click()
  await drawer.getByRole('combobox', { name: '关联学生', exact: true }).fill(setup.scope.snapshots[rows[1].target_key].platform_id)
  await expect(drawer.getByRole('listbox', { name: '关联学生匹配结果', exact: true }).getByRole('option')).toHaveCount(1)
  await drawer.getByRole('listbox', { name: '关联学生匹配结果', exact: true }).getByRole('option').click()
  await expect(drawer.getByText('已手动调整归属，保存时以当前选项为准。')).toBeVisible()
  preview = await renderPreview(page); await preview.getByRole('button', { name: '关闭PDF预览' }).click()
  await page.screenshot({ path: path.join(evidence, '03-upload-attribution.png'), fullPage: true })
  await drawer.getByRole('button', { name: '下一步：核对清单' }).click()
  await expect(drawer.getByText('待保存 2 份报告')).toBeVisible()
  await page.screenshot({ path: path.join(evidence, '04-upload-confirmation.png'), fullPage: true })
  await drawer.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(drawer).toHaveCount(0)
  await page.getByLabel('考试筛选').selectOption(setup.exam.id)
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(2)
  await page.reload(); await page.getByLabel('考试筛选').selectOption(setup.exam.id)
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(2)
  await page.screenshot({ path: path.join(evidence, '05-report-list.png'), fullPage: true })
})

test('replace keeps attribution and history, delete cancellation and confirmed batch are real', async ({ page, request }) => {
  const setup = await createExam(request, '报告r86替换删除验收'), saved = await saveRows(request, setup, [reportRow(setup.scope), reportRow(setup.scope, 'essay')])
  await login(page); await page.goto('/admin/reports'); await page.getByLabel('考试筛选').selectOption(setup.exam.id)
  const row = page.getByRole('row').filter({ hasText: saved.reports[0].report_code })
  await row.getByRole('button', { name: '替换', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '替换更新', exact: true })
  await drawer.getByLabel('选择新 PDF', { exact: true }).setInputFiles({ name: '损坏.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7 invalid') })
  await expect(drawer.getByRole('alert')).toBeVisible()
  expect((await request.get(`${base}/${saved.reports[0].id}/file`, { headers: setup.auth })).ok()).toBeTruthy()
  await drawer.getByLabel('选择新 PDF', { exact: true }).setInputFiles({ name: '新版报告.pdf', mimeType: 'application/pdf', buffer: replacementPdf })
  await expect(drawer.getByRole('button', { name: '预览新 PDF', exact: true })).toBeVisible()
  await expect(drawer.getByRole('checkbox')).toBeDisabled()
  const preview = await renderPreview(page, '预览新 PDF'); await preview.getByRole('button', { name: '关闭PDF预览' }).click()
  await drawer.getByLabel('替换原因', { exact: true }).fill('合成验收：更新诊断内容')
  await drawer.getByRole('checkbox', { name: '已核对新 PDF，报告归属保持不变' }).check()
  await drawer.getByRole('button', { name: '确认替换为 v2', exact: true }).click()
  await expect(drawer).toHaveCount(0); await expect(row).toContainText('v2')
  const current = await (await request.get(`${base}/${saved.reports[0].id}`, { headers: setup.auth })).json()
  for (const key of ['report_code', 'exam_id', 'category', 'report_type', 'subject_ids', 'target_key', 'coverage']) expect(current[key]).toEqual(saved.reports[0][key])
  await row.getByRole('button', { name: '查看', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '报告详情', exact: true })
  await expect(detail.getByText('v1 · 历史版本', { exact: true })).toBeVisible()
  const oldPreview = await renderPreview(page, '预览历史 PDF'); await oldPreview.getByRole('button', { name: '关闭PDF预览' }).click()
  await page.screenshot({ path: path.join(evidence, '06-current-and-history.png'), fullPage: true })
  await detail.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('checkbox', { name: '选择当前页全部报告', exact: true }).check()
  await page.getByRole('button', { name: '删除所选', exact: true }).click()
  const deletion = page.getByRole('dialog', { name: '删除报告 · 2 份', exact: true })
  await deletion.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(2)
  await page.getByRole('button', { name: '删除所选', exact: true }).click()
  await deletion.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(deletion.getByRole('alert')).toHaveText('请填写删除原因并确认清单')
  await deletion.getByLabel('删除原因', { exact: true }).fill('合成验收：误传清理')
  await deletion.getByRole('checkbox', { name: '已核对所选报告，确认删除' }).check()
  await page.screenshot({ path: path.join(evidence, '07-batch-delete-confirmation.png'), fullPage: true })
  await deletion.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(deletion).toHaveCount(0); await expect(page.getByText('没有匹配的报告')).toBeVisible()
  await page.getByRole('button', { name: '操作记录', exact: true }).click()
  await expect(page.locator('.log').filter({ hasText: '合成验收：更新诊断内容' })).toBeVisible()
  const log = page.locator('.log').filter({ hasText: '合成验收：误传清理' }); await log.locator('summary').click()
  await expect(log).toContainText(saved.reports[0].report_code)
  await page.screenshot({ path: path.join(evidence, '08-operation-records.png'), fullPage: true })
})

test('query checks match live teacher and student permissions and only expose the current PDF', async ({ page, request, browser }) => {
  const setup = await createExam(request, '报告r86权限闭环验收', true)
  const saved = await saveRows(request, setup, [reportRow(setup.scope), reportRow(setup.scope, 'student', 2), reportRow(setup.scope, 'classAll'), reportRow(setup.scope, 'school'), reportRow(setup.scope, 'essay')])
  const english = await saveRows(request, setup, [reportRow(setup.scope, 'essay', 0, 2)])
  const grant = async (kind: string, body: any) => {
    const exam = await (await request.get(examsBase + '/' + setup.exam.id, { headers: setup.auth })).json()
    const data = { ...body, expected_revision: exam.revision }, url = `${examsBase}/${exam.id}/permissions/${kind}`
    const preview = await request.post(url + '/preview', { headers: setup.auth, data })
    expect(preview.ok(), await preview.text()).toBeTruthy()
    return post(request, url, setup.auth, { ...data, preview_hash: preview.headers()['x-exam-preview-hash'] })
  }
  await grant('teacher', { teachers: [{ teacher_id: fixture.user_ids.teacher, score_types: [], score_subjects: [], diagnosis_types: ['student', 'classAll', 'school'], diagnosis_subjects: [setup.scope.subjects[0].subject_id], essay_types: ['chinese'], range_type: 'class', classes: ['高中一年级 / 1'] }] })
  await grant('student', { student_ids: [fixture.students[0].id], subject_ids: [setup.scope.subjects[0].subject_id], mode: 'open' })
  await login(page); await page.goto('/admin/reports'); await page.getByLabel('考试筛选').selectOption(setup.exam.id)
  await page.getByRole('button', { name: '核对查询权限' }).click()
  const check = page.getByRole('dialog', { name: '核对报告查询权限', exact: true })
  await check.getByRole('combobox', { name: '查询账号', exact: true }).fill(fixture.users.teacher)
  await check.getByRole('listbox', { name: '查询账号匹配结果', exact: true }).getByRole('option').click()
  await expect(check.getByRole('row').filter({ hasText: '全校学情诊断' })).toContainText('不可查询')
  await expect(check.getByRole('row').filter({ hasText: '班级综合诊断' })).toContainText('可查询')
  await page.screenshot({ path: path.join(evidence, '09-teacher-access-check.png'), fullPage: true })
  await check.getByLabel('查询身份').selectOption('student')
  await check.getByRole('combobox', { name: '查询账号', exact: true }).fill(fixture.students[0].platform_id)
  await check.getByRole('listbox', { name: '查询账号匹配结果', exact: true }).getByRole('option').click()
  await expect(check.locator('tbody tr')).toHaveCount(3)
  await expect(check.getByRole('row').filter({ hasText: '英语' })).toContainText('不可查询')
  await expect(check.getByText('班级综合诊断', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: path.join(evidence, '10-student-access-check.png'), fullPage: true })
  await check.getByRole('button', { name: '关闭', exact: true }).click()
  const teacherContext = await browser.newContext(), teacherPage = await teacherContext.newPage()
  await login(teacherPage, 'teacher'); await teacherPage.goto('/teacher/exams'); await teacherPage.getByLabel('选择已授权考试').selectOption(setup.exam.id)
  await expect(teacherPage.getByRole('cell').filter({ hasText: '个人学情诊断' })).toHaveCount(1)
  await expect(teacherPage.getByRole('cell').filter({ hasText: '个人作文批改报告' })).toHaveCount(1)
  await teacherPage.getByLabel('查询内容类型').selectOption('school')
  await expect(teacherPage.getByRole('cell').filter({ hasText: '全校学情诊断' })).toHaveCount(0)
  await teacherPage.getByLabel('查询内容类型').selectOption('classAll')
  await expect(teacherPage.getByRole('cell').filter({ hasText: '班级综合诊断' })).toHaveCount(1)
  await teacherPage.screenshot({ path: path.join(evidence, '11-authorized-teacher-report.png'), fullPage: true })
  const studentContext = await browser.newContext(), studentPage = await studentContext.newPage()
  await login(studentPage, 'student'); await studentPage.goto('/exam-results'); await studentPage.getByLabel('选择已授权考试').selectOption(setup.exam.id)
  await expect(studentPage.getByRole('button', { name: '查看 PDF', exact: true })).toHaveCount(2)
  await studentPage.getByRole('button', { name: '查看 PDF', exact: true }).first().click()
  await expect(studentPage.getByRole('img', { name: 'PDF第1页' })).toBeVisible()
  await studentPage.getByRole('button', { name: '关闭PDF预览' }).click()
  await studentPage.locator('.workspace-main').evaluate(element => { element.scrollTop = 0 })
  await studentPage.screenshot({ path: path.join(evidence, '12-authorized-student-reports.png'), fullPage: true })
  const first = saved.reports[0]
  await post(request, base + '/' + first.id + '/replace', setup.auth, { expected_version: 1, file: { filename: '查询新版.pdf', content_base64: replacementPdf.toString('base64') }, reason: '合成验收权限不变', previewed: true, confirmed: true })
  const studentAuth = await headers(request, 'student'), source = `${examsBase}/my-exams/${setup.exam.id}/reports/${first.id}/original`
  const updated = await request.get(source + '?version=1', { headers: studentAuth }); expect(await updated.body()).toEqual(replacementPdf)
  expect((await request.get(`${base}/${first.id}/file?version=1`, { headers: studentAuth })).status()).toBe(403)
  expect((await request.get(`${examsBase}/my-exams/${setup.exam.id}/reports/${english.reports[0].id}/original`, { headers: studentAuth })).status()).toBe(404)
  const teacherAuth = await headers(request, 'teacher')
  expect((await request.get(`${examsBase}/my-exams/${setup.exam.id}/reports/${saved.reports[3].id}/original?view_type=school`, { headers: teacherAuth })).status()).toBe(404)
  await post(request, base + '/delete', setup.auth, { reports: [{ id: first.id, expected_version: 2 }], reason: '合成验收移除入口', confirmed: true })
  expect((await request.get(source, { headers: studentAuth })).status()).toBe(404)
  await studentPage.reload(); await studentPage.getByLabel('选择已授权考试').selectOption(setup.exam.id)
  await expect(studentPage.getByRole('button', { name: '查看 PDF', exact: true })).toHaveCount(1)
  await teacherContext.close(); await studentContext.close()
})

test('filters, twelve item pagination and cross page selection match the prototype', async ({ page, request }) => {
  const setup = await createExam(request, '报告r86筛选分页验收')
  const rows = [0, 1, 2].map(index => reportRow(setup.scope, 'student', index))
  for (const type of ['classAll', 'classSubject']) for (const index of [0, 2]) rows.push(reportRow(setup.scope, type, index))
  for (const type of ['gradeAll', 'gradeSubject', 'school']) rows.push(reportRow(setup.scope, type))
  for (const index of [0, 1, 2]) rows.push(reportRow(setup.scope, 'essay', index))
  await saveRows(request, setup, rows)
  await login(page); await page.goto('/admin/reports'); await page.getByLabel('考试筛选').selectOption(setup.exam.id)
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(12)
  await page.getByRole('checkbox', { name: '选择当前页全部报告', exact: true }).check()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(1)
  await page.getByRole('checkbox', { name: '选择当前页全部报告', exact: true }).check()
  await expect(page.getByText('已选 13 份', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '删除所选', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '删除报告 · 13 份', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('tab', { name: /作文批改报告/ }).click()
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(3)
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled()
  await page.getByRole('tab', { name: /全部报告/ }).click()
  await page.getByLabel('报告类型筛选').selectOption('classSubject')
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(2)
  await page.getByLabel('报告类型筛选').selectOption('')
  await page.getByLabel('全部班级').selectOption('高中一年级|1')
  await expect(page.locator('.report-workbench tbody tr')).toHaveCount(9)
  await page.getByLabel('搜索报告').fill('没有这个报告')
  await expect(page.getByText('没有匹配的报告')).toBeVisible()
  await page.getByLabel('搜索报告').fill('')
  await page.screenshot({ path: path.join(evidence, '13-filters-and-pagination.png'), fullPage: true })
})

test('mobile drawers fit the viewport and read only identities cannot maintain reports', async ({ page, request }) => {
  const setup = await createExam(request, '报告r86移动端验收')
  await page.setViewportSize({ width: 390, height: 844 }); await login(page); await page.goto('/admin/reports/new')
  await chooseExam(page, setup.exam.name)
  await page.getByRole('radio', { name: '语文', exact: true }).check()
  const drawer = page.getByRole('dialog', { name: '上传报告', exact: true }), bounds = await drawer.boundingBox()
  expect(bounds!.width).toBeLessThanOrEqual(390); expect(bounds!.x).toBeGreaterThanOrEqual(0)
  await page.screenshot({ path: path.join(evidence, '14-mobile-upload.png'), fullPage: true })
  await page.keyboard.press('Escape'); await expect(drawer).toHaveCount(0)
  const viewer = await headers(request, 'viewer')
  expect((await request.get(base, { headers: viewer })).status()).toBe(403)
  const examAdmin = await headers(request, 'examadmin')
  expect((await request.get(base + '/operations', { headers: examAdmin })).status()).toBe(403)
})

test('a lost upload response can be retried without duplicating reports or receipts', async ({ page, request }) => {
  const setup = await createExam(request, '报告r86网络重试验收'), row = reportRow(setup.scope)
  await login(page); await page.goto('/admin/reports/new'); await chooseExam(page, setup.exam.name)
  const drawer = page.getByRole('dialog', { name: '上传报告', exact: true })
  await drawer.getByRole('radio', { name: '语文', exact: true }).check()
  await drawer.getByLabel('上传 PDF 文件').setInputFiles({ name: row.file.filename, mimeType: 'application/pdf', buffer: originalPdf })
  await expect(drawer.getByText('校验通过 1 / 1 份')).toBeVisible()
  await drawer.getByRole('button', { name: '下一步：预览归属' }).click()
  const preview = await renderPreview(page); await preview.getByRole('button', { name: '关闭PDF预览' }).click()
  await drawer.getByRole('button', { name: '下一步：核对清单' }).click()
  await page.route('**/api/v1/platform/education/report-management/batches', async route => {
    const response = await route.fetch(); expect(response.ok()).toBeTruthy(); await route.abort('failed')
  }, { times: 1 })
  await drawer.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(drawer.getByRole('alert')).toContainText('提交结果尚未确认')
  const committed = await (await request.get(base + '?exam_id=' + setup.exam.id, { headers: setup.auth })).json()
  expect(committed.total).toBe(1)
  await drawer.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(drawer).toHaveCount(0)
  const after = await (await request.get(base + '?exam_id=' + setup.exam.id, { headers: setup.auth })).json()
  expect(after.items.map((item: any) => item.id)).toEqual(committed.items.map((item: any) => item.id))
})

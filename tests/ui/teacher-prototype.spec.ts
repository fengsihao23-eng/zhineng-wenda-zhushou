import { test, expect, type Page } from '@playwright/test'

const taskId = '50000000-0000-4000-8000-000000000001'
const batchId = '60000000-0000-4000-8000-000000000001'
const columns = ['学校编号', '学校名称', '部门名称', '教师姓名', '性别', '教师账号', '学工号', 'mac地址', 'SN码', '状态', '说明', '身份证', '手机号码', '短号', '座机号', '电子邮箱', '备注', '任课年级班级', '班主任年级班级', '教研组长负责年级科目', '年级长负责年级', '是否教务主任', '是否校长', '是否总务主任']
const initial = Array.from({ length: 25 }, (_, index) => {
  const name = `示例教师${index + 1}`, account = `1390000${String(index + 1).padStart(4, '0')}`
  return { id: `70000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`, name, username: account, phone: account, class_name: '数学:10.1;', duties: ['TEACHER'], status: 'active', fields: { ...Object.fromEntries(columns.map(c => [c, ''])), 教师姓名: name, 教师账号: account, 手机号码: account, 状态: '正常', 任课年级班级: '数学:10.1;' } }
})

async function mock(page: Page, role = 'SCHOOL_ADMIN', duplicate = false) {
  let records = structuredClone(initial), snapshots: any[] = [], batches: any[] = []
  let taskStatus = 'pending'
  const sent: { path: string; body: any }[] = []
  const user = { user_id: 'ui-user', school_id: 'ui-school', username: 'ui-user', display_name: '示例管理员', roles: [role] }
  await page.addInitScript(identity => {
    sessionStorage.setItem('refresh_token', 'synthetic-ui-token')
    sessionStorage.setItem('user_info', JSON.stringify(identity))
  }, user)
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/v1', '')
    let body: any = [], status = 200
    const payload = request.method() === 'POST' ? request.postDataJSON() : null
    if (payload) sent.push({ path, body: payload })
    const paged = (rows: any[]) => {
      const size = Number(url.searchParams.get('page_size') || 20), current = Number(url.searchParams.get('page') || 1)
      return { items: rows.slice((current - 1) * size, current * size), total: rows.length }
    }
    if (path === '/auth/me') body = user
    else if (path === '/health') body = { model: { real_model_ready: true } }
    else if (path.endsWith('/roster/teachers/records')) {
      body = paged(records.filter(row => `${row.name} ${row.username} ${row.phone}`.includes(url.searchParams.get('search') || '') && row.class_name.includes(url.searchParams.get('class_name') || '')))
    } else if (path.endsWith('/roster/teachers/delete')) {
      const chosen = records.filter(row => payload.teacher_ids.includes(row.id))
      snapshots.push(...chosen.map(row => ({ id: `snapshot-${row.id}`, user_id: row.id, teacher_name: row.name, account: row.username, fields: row.fields, reason: payload.reason, reason_note: payload.reason_note, operator_name: user.display_name, deleted_at: '2026-10-12T01:00:00Z', task_id: payload.reason === 'change' ? taskId : null, task_status: 'pending' })))
      records = records.filter(row => !payload.teacher_ids.includes(row.id))
      body = { id: 'deletion-operation', task_id: payload.reason === 'change' ? taskId : null, count: chosen.length, snapshots, message: '原档案已删除、账号已释放，24 列快照已保存。' }
    } else if (path.endsWith('/roster/teachers/deletions')) {
      body = paged(snapshots.filter(row => `${row.teacher_name} ${row.account} ${row.task_id || ''}`.includes(url.searchParams.get('search') || '') && (!url.searchParams.get('reason') || row.reason === url.searchParams.get('reason'))))
    } else if (path.endsWith(`/roster/teachers/change-tasks/${taskId}`)) {
      body = { id: taskId, status: taskStatus, snapshots, batches }
    } else if (path.endsWith('/roster/teachers/imports') || path.endsWith(`/change-tasks/${taskId}/imports`)) {
      if (payload) {
        const isTask = path.includes('/change-tasks/')
        const source = isTask ? snapshots : [{ ...initial[0], user_id: initial[0].id }]
        const rows = source.map((row: any, index: number) => ({ row_number: index + 2, values: { ...row.fields, 教师姓名: `${row.fields.教师姓名}更新`, ...(isTask ? { 教师ID: row.user_id } : {}) } }))
        body = { id: batchId, filename: payload.filename, kind: 'teachers', status: 'ready', revision: 1, change_task_id: isTask ? taskId : null, columns: isTask ? [...columns, '教师ID'] : columns, rows, report: { ok: true, issues: [], total_rows: rows.length, suspicious: duplicate ? [{ row_number: 2, name: '示例教师1', account: '13900009999', teaching: '数学:10.1;', matches: [{ id: initial[0].id, name: '示例教师1', account: initial[0].username, teaching: '数学:10.1;' }] }] : [] } }
        batches = [body]
      } else body = url.searchParams.get('paginated') ? paged(batches) : batches
    } else if (path.endsWith(`/roster/imports/${batchId}/confirm`)) {
      const batch = batches[0]
      body = { ...batch, status: 'succeeded', report: { ...batch.report, success_count: batch.rows.length, skipped_count: 0, skipped_rows: [], confirmed_by_name: user.display_name, confirmed_at: '2026-10-12T01:15:00Z', versions: batch.change_task_id ? snapshots.map((row, i) => ({ teacher_id: row.user_id, row_number: i + 2, changes: [{ field: '教师姓名', before: row.teacher_name, after: `${row.teacher_name}更新` }] })) : undefined } }
      batches = [body]
      if (batch.change_task_id) { taskStatus = 'succeeded'; snapshots = snapshots.map(row => ({ ...row, task_status: 'succeeded', reimported_at: '2026-10-12T01:15:00Z' })) }
    } else if (path.endsWith(`/roster/imports/${batchId}`)) body = batches[0]
    else if (path.endsWith('/template')) body = 'synthetic workbook download'
    else if (path.includes('/school/')) body = { items: [], total: 0 }
    else if (path === '/platform/education/accounts') body = []
    else if (path === '/auth/refresh') { body = { access_token: 'synthetic-token' }; }
    else if (path.includes('change-tasks')) { status = 404; body = { error: { code: 'NOT_FOUND', message: '任务不存在' } }; }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  })
  return sent
}

test('teacher list matches prototype, selects visible rows, resets filters, and shows 24 fields in a drawer', async ({ page }) => {
  await mock(page)
  await page.goto('/admin/school?tab=teachers')
  await expect(page.getByRole('heading', { name: '教师信息列表' })).toBeVisible()
  await expect(page.getByRole('button', { name: '批量删除', exact: true })).toBeDisabled()
  await expect(page.locator('.teacher-table tbody tr')).toHaveCount(20)
  await expect(page.getByRole('button', { name: '教师任教', exact: true })).toHaveCount(0)
  await page.getByLabel('选择本页全部教师').check()
  await expect(page.getByRole('button', { name: '批量删除（20）' })).toBeEnabled()
  await page.getByLabel('教师关键词').fill('示例教师25')
  await expect(page.locator('.teacher-table tbody tr')).toHaveCount(1)
  await expect(page.getByRole('button', { name: '批量删除', exact: true })).toBeDisabled()
  await page.getByLabel('教师关键词').clear()
  await expect(page.getByRole('button', { name: '批量删除', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '查看档案', exact: true }).first().click()
  const drawer = page.getByRole('dialog', { name: '教师档案详情' })
  await expect(drawer).toBeVisible()
  await expect(drawer.locator('dt')).toHaveCount(24)
  await expect(drawer).toContainText(initial[0].id)
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('teacher-prototype-list.png'), fullPage: true })
})

test('deletion needs a reason, mandatory other note, and explicit review', async ({ page }) => {
  const sent = await mock(page)
  await page.goto('/admin/school?tab=teachers')
  await page.getByRole('button', { name: '删除', exact: true }).first().click()
  const drawer = page.getByRole('dialog', { name: '删除教师档案' })
  await expect(drawer.getByRole('button', { name: '确认删除' })).toBeDisabled()
  await drawer.getByRole('radio', { name: /其他/ }).check()
  await drawer.getByRole('checkbox').check()
  await expect(drawer.getByRole('button', { name: '确认删除' })).toBeDisabled()
  await drawer.getByLabel('其他删除说明').fill('重复建档')
  await drawer.getByRole('button', { name: '确认删除' }).click()
  await expect(drawer.getByText('删除完成', { exact: true })).toBeVisible()
  expect(sent.find(row => row.path.endsWith('/teachers/delete'))?.body).toEqual({ teacher_ids: [initial[0].id], reason: 'other', reason_note: '重复建档', confirmed: true })
  await drawer.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '操作记录', exact: true }).click()
  await page.getByRole('tab', { name: '删除快照（含变更任务）' }).click()
  await expect(page.getByRole('dialog').getByText('重复建档', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '继续变更任务' })).toHaveCount(0)
})

test('import wizard requires duplicate review, clears review when decision changes, and shows receipt', async ({ page }) => {
  const sent = await mock(page, 'SCHOOL_ADMIN', true)
  await page.goto('/admin/school?tab=teachers')
  await page.getByRole('button', { name: '导入教师', exact: true }).click()
  const modal = page.getByRole('dialog', { name: '导入教师（Excel 批量新增）' })
  await modal.getByLabel('上传教师 Excel').setInputFiles({ name: 'new-teachers.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('synthetic') })
  await modal.getByRole('button', { name: '开始预校验' }).click()
  await expect(modal.getByText(/预校验通过，共 1 行/)).toBeVisible()
  await modal.getByRole('button', { name: '下一步：疑似重复确认' }).click()
  await expect(modal.getByRole('button', { name: '确认入库' })).toBeDisabled()
  await modal.getByRole('checkbox', { name: '已核对第 2 行' }).check()
  await modal.getByLabel('第2行保留或放弃').selectOption('false')
  await expect(modal.getByRole('button', { name: '确认入库' })).toBeDisabled()
  await modal.getByRole('checkbox', { name: '已核对第 2 行' }).check()
  await modal.getByRole('button', { name: '确认入库' }).click()
  await expect(modal.getByRole('heading', { name: '导入完成' })).toBeVisible()
  expect(sent.find(row => row.path.endsWith('/confirm'))?.body.duplicate_decisions).toEqual({ 2: false })
})

test('batch change retains task on cancel, requires matching locked IDs and verifies field changes', async ({ page }) => {
  const sent = await mock(page)
  await page.goto('/admin/school?tab=teachers')
  await page.getByLabel('选择教师示例教师1', { exact: true }).check()
  await page.getByLabel('选择教师示例教师2', { exact: true }).check()
  await page.getByRole('button', { name: '批量删除（2）' }).click()
  const deletion = page.getByRole('dialog', { name: '删除教师档案' })
  await deletion.locator('summary').first().click()
  await expect(deletion.locator('.teacher-batch-snapshot[open] dt')).toHaveCount(24)
  await deletion.getByRole('radio', { name: /变更前删除/ }).check()
  await deletion.getByRole('checkbox').check()
  await deletion.getByRole('button', { name: '确认删除' }).click()
  await deletion.getByRole('button', { name: '立即上传更新文件' }).click()
  let task = page.getByRole('dialog', { name: '教师专属变更任务' })
  await expect(task.getByText('任务内原教师 2 名', { exact: true })).toBeVisible()
  await task.getByRole('button', { name: '取消（保留任务）' }).click()
  await page.getByRole('button', { name: '操作记录', exact: true }).click()
  await page.getByRole('tab', { name: '删除快照（含变更任务）' }).click()
  await page.getByRole('button', { name: '继续变更任务' }).first().click()
  await page.reload()
  task = page.getByRole('dialog', { name: '教师专属变更任务' })
  await expect(task.getByText('任务内原教师 2 名', { exact: true })).toBeVisible()
  await task.getByLabel('上传教师 Excel').setInputFiles({ name: 'updated-teachers.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('synthetic') })
  await task.getByRole('button', { name: '开始预校验' }).click()
  await task.getByRole('button', { name: '下一步：指定对应关系' }).click()
  await task.getByRole('button', { name: '下一步：预览变更' }).click()
  await expect(task.getByText(/第 2 行：未指定原教师/)).toBeVisible()
  await task.getByLabel('第2行原教师').selectOption(initial[0].id)
  await task.getByLabel('第3行原教师').selectOption(initial[0].id)
  await task.getByRole('checkbox', { name: '我已逐行核实对应关系身份真实、准确。' }).check()
  await task.getByRole('button', { name: '下一步：预览变更' }).click()
  await expect(task.getByText(/第 3 行：原教师重复关联/)).toBeVisible()
  await task.getByLabel('第3行原教师').selectOption(initial[1].id)
  await task.getByRole('checkbox', { name: '我已逐行核实对应关系身份真实、准确。' }).check()
  await task.getByRole('button', { name: '下一步：预览变更' }).click()
  await expect(task.getByRole('button', { name: '确认整批提交' })).toBeDisabled()
  await expect(task).toContainText('示例教师1更新')
  await task.getByRole('checkbox', { name: '我已核对对应关系及全部变更内容，确认整批提交。' }).check()
  await page.screenshot({ path: test.info().outputPath('teacher-change-preview.png'), fullPage: true })
  await task.getByRole('button', { name: '确认整批提交' }).click()
  await expect(task.getByRole('heading', { name: '变更任务已完成' })).toBeVisible()
  const submitted = sent.find(row => row.path.endsWith('/confirm'))?.body
  expect(submitted.teacher_replacements).toEqual({ 2: initial[0].id, 3: initial[1].id })
  expect(submitted.identity_confirmed && submitted.changes_confirmed).toBe(true)
})

test('read-only teacher archives permit records and inspection while hiding mutation actions', async ({ page }) => {
  await mock(page, 'QA')
  await page.goto('/admin/school?tab=teachers')
  await expect(page.getByRole('button', { name: '导入教师', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '批量删除', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '删除', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '查看档案', exact: true }).first().click()
  await expect(page.getByRole('dialog')).toContainText('教师档案详情')
})

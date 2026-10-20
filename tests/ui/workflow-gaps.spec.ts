import { test, expect, type Page } from '@playwright/test'

async function identity(page: Page, role: 'STUDENT' | 'TEACHER') {
  const user = { user_id: 'workflow-user', school_id: 'workflow-school', username: 'synthetic', display_name: '合成账号', roles: [role] }
  await page.addInitScript(user => {
    sessionStorage.setItem('refresh_token', 'synthetic-workflow-token')
    sessionStorage.setItem('user_info', JSON.stringify(user))
  }, user)
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: user }))
  await page.route('**/api/v1/health', route => route.fulfill({ json: { model: { real_model_ready: true } } }))
  return user
}

test('the 101st conversation remains visible after state refresh and page reload', async ({ page }) => {
  await identity(page, 'STUDENT')
  const person = { id: 'workflow-student', role: 'student', userId: 'workflow-user', name: '合成学生', school: '合成学校', roles: ['学生'], stages: ['高中'], status: '正常' }
  const sessions = Array.from({ length: 100 }, (_, i) => ({ id: `session-${100-i}`, owner: 'student:workflow-student', title: `历史问题${100-i}`, createdAt: '2026-10-19', updatedAt: '2026-10-19', messages: [], context: null }))
  await page.route('**/api/v1/answer-workbench/mini/state', route => route.fulfill({ json: { identity: person, exams: [], reports: [], sessions: sessions.slice(0, 100), tickets: [], audit: [] } }))
  await page.route('**/api/v1/answer-workbench/mini/ask', async route => {
    const question = route.request().postDataJSON().question
    const session = { ...sessions[0], id: 'session-101', title: question, messages: [
      { id: 'q101', role: 'user', text: question, at: '2026-10-20', sources: [] },
      { id: 'a101', role: 'assistant', text: '第101个会话的回复已保留。', at: '2026-10-20', sources: [] },
    ] }
    sessions.unshift(session)
    await route.fulfill({ json: session })
  })
  await page.goto('/chat')
  const frame = page.frameLocator('iframe[title="智能问答助手"]')
  await expect(frame.getByLabel('选择会话').locator('option')).toHaveCount(101)
  await frame.getByLabel('输入问题').fill('第101个问题：如何复习数学？')
  await frame.getByLabel('发送问题').click()
  await expect(frame.getByText('第101个会话的回复已保留。')).toBeVisible()
  await expect(frame.getByLabel('选择会话').locator('option').nth(1)).toContainText('第101个问题')
  await page.reload()
  await frame.getByLabel('选择会话').selectOption('session-101')
  await expect(frame.getByText('第101个会话的回复已保留。')).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('conversation-101.png'), fullPage: true })
})

test('pending question scores show earned points and an explanation instead of an empty mistake page', async ({ page }) => {
  await identity(page, 'STUDENT')
  await page.route('**/api/v1/platform/student/mistakes', route => route.fulfill({ json: [
    { id: 'score-pending', exam: '合成考试', subject: '数学', question_no: '1', score: 3, full_score: null, lost_score: null, answer_status: null, date: '2026-10-20' },
    { id: 'score-known', exam: '合成考试', subject: '数学', question_no: '2', score: 2, full_score: 5, lost_score: 3, answer_status: 'partial', date: '2026-10-20' },
  ] }))
  await page.route('**/api/v1/platform/education/student/mistakes/score-pending', route => route.fulfill({ json: { score: { exam: '合成考试', subject: '数学', question_no: '1', score: 3, full_score: null, lost_score: null }, question: null, missing_reason: '尚未关联正式题目版本，得分事实仍可查看。' } }))
  await page.goto('/mistakes')
  await expect(page.getByRole('status')).toContainText('尚未提供满分')
  await expect(page.locator('tbody tr')).toHaveCount(2)
  await expect(page.locator('tbody tr').first()).toContainText('3 / 待补满分')
  await expect(page.getByText('待计算', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看原题 / 加入复盘' }).first().click()
  await expect(page.getByRole('dialog')).toContainText('得分事实仍可查看')
  await page.screenshot({ path: test.info().outputPath('pending-question-score.png'), fullPage: true })
})

test('teachers can claim and reply to answer tickets from the shared handoff page', async ({ page }) => {
  await identity(page, 'TEACHER')
  let ticket = { id: 'answer-ticket', revision: 1, status: '待处理', question: '需要老师核查学习安排', currentAllowed: true, canReply: false,
    assignee: null as { id: string; name: string } | null, sources: [], context: [], events: [{ role: 'user', text: '需要老师核查学习安排', at: '2026-10-20' }] }
  await page.route('**/api/v1/platform/management/handoffs', route => route.fulfill({ json: [{ id: ticket.id, source: 'answer', reason: '问答人工留言 · 合成学生', summary: ticket.question, status: ticket.status === '待处理' ? 'open' : ticket.status === '处理中' ? 'accepted' : 'resolved', created_at: '2026-10-20' }] }))
  await page.route('**/api/v1/answer-workbench/tickets/**', async route => {
    if (route.request().url().endsWith('/claim')) ticket = { ...ticket, revision: 2, status: '处理中', canReply: true, assignee: { id: 'workflow-user', name: '合成老师' } }
    if (route.request().url().endsWith('/reply')) {
      expect(route.request().postDataJSON().expected).toBe(2)
      ticket = { ...ticket, revision: 3, status: '已回复', canReply: false, events: [...ticket.events, { role: 'operator', text: route.request().postDataJSON().text, at: '2026-10-20' }] }
    }
    await route.fulfill({ json: ticket })
  })
  await page.goto('/teacher/handoffs')
  await expect(page.getByRole('link', { name: '学生人工求助' })).toBeVisible()
  await page.getByRole('button', { name: '处理问答人工留言' }).click()
  await page.getByRole('button', { name: '领取留言' }).click()
  await page.getByLabel('回复问答人工留言').fill('明天课间到办公室核对学习安排。')
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: '发送回复', exact: true }).click()
  await expect(page.getByRole('log')).toContainText('明天课间到办公室核对学习安排。')
  await expect(page.getByRole('log')).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('teacher-answer-ticket.png'), fullPage: true })
})

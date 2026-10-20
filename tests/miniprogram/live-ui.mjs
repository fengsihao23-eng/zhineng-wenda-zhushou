/** One live question through the native input/button using an account the owner logged in.
 * No credentials are read or exported. Evidence containing school data stays private.
 */
import automator from 'miniprogram-automator'
import assert from 'node:assert/strict'
import { mkdir, writeFile, chmod } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

assert.equal(process.env.QA_WECHAT_LIVE_UI, '1', 'Set QA_WECHAT_LIVE_UI=1 after the owner logs into the native project; this saves one live question')
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const config = createRequire(import.meta.url)(path.join(root, 'apps/miniprogram/config.js'))
const output = process.env.QA_WECHAT_LIVE_OUTPUT || path.join(root, '.local/wechat-live')
await mkdir(output, { recursive: true, mode: 0o700 })
await chmod(output, 0o700)
const healthResponse = await fetch(config.apiBaseUrl + '/health', { signal: AbortSignal.timeout(15000) })
assert.equal(healthResponse.status, 200)
const health = await healthResponse.json()
assert.equal(health.environment, 'production')
assert.equal(health.model.test_model_enabled, false)
assert.equal(health.model.real_model_ready, true)

const mini = await automator.launch({
  projectPath: path.join(root, 'apps/miniprogram'),
  cliPath: process.env.WECHAT_CLI || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',
  trustProject: true, timeout: 60000
})
const errors = []
mini.on('exception', error => errors.push(String(error)))
let page, originalDraft, submitted = false
const privateRecord = { health }
async function waitFor(condition, description, timeout = 50000) {
  const deadline = Date.now() + timeout
  while (!await condition()) {
    assert.ok(Date.now() < deadline, 'Native UI timed out: ' + description)
    await new Promise(resolve => setTimeout(resolve, 200))
  }
}
async function capture(name) {
  await mini.evaluate(() => { wx.hideToast(); return true })
  await mini.screenshot({ path: path.join(output, name) })
  await chmod(path.join(output, name), 0o600)
}
async function tapRendered(selector) {
  await waitFor(async () => {
    const element = await page.$(selector)
    if (!element) return false
    const size = await element.size()
    return Number(size.width) > 0 && Number(size.height) > 0
  }, 'render ' + selector)
  // Page data becomes observable before the native rendering thread has applied it.
  await new Promise(resolve => setTimeout(resolve, 350))
  await (await page.$(selector)).tap()
}
try {
  page = await mini.currentPage()
  assert.ok(page, 'Open the native project and log in first')
  await waitFor(async () => !await page.data('busy') && !await page.data('loading'), 'existing login')
  const before = await page.callMethod('syncState')
  assert.equal(before.identity.role, 'student', 'This single-account live check requires an already logged-in student')
  const exam = before.exams.find(row => row.subjects.length && row.types.includes('student'))
  assert.ok(exam, 'The logged-in account has no authorized student exam')
  assert.ok(before.questionStatus.quota.remaining > 0, 'The logged-in account has no daily questions remaining')
  originalDraft = await page.data('chatDraft')
  const question = '界面联调核验：请说明我在' + exam.name + '的' + exam.subjects[0].n + '成绩和满分，并根据已有资料给出一条学习建议。'
  privateRecord.before = before
  privateRecord.question = question
  console.log('LIVE_UI_PHASE=native_input_and_send')
  await page.callMethod('newChat')
  await waitFor(async () => !!await page.$('#question'), 'question input')
  await (await page.$('#question')).input(question)
  assert.equal(await page.data('chatDraft'), question)
  const start = Date.now()
  await tapRendered('#sendQuestion')
  submitted = true
  await waitFor(async () => !await page.data('busy') && !!await page.data('activeSession'), 'model answer')
  const messages = await page.data('messages')
  const answer = messages[messages.length - 1]
  privateRecord.messages = messages
  privateRecord.notice = await page.data('notice')
  await writeFile(path.join(output, 'live-ui-private.json'), JSON.stringify(privateRecord, null, 2), { mode: 0o600 })
  assert.equal(messages[0].text, question)
  assert.equal(answer.role, 'assistant')
  assert.ok(!answer.fallback && !answer.serviceFailure && !answer.configurationFailure, 'The native answer used a fallback; inspect private evidence')
  assert.ok(!/reportAvailability|matchedReports|readPages|not_available/.test(answer.text), 'The answer must describe report availability in ordinary language')
  assert.ok(answer.sources.some(ref => ref.kind === 'score'))
  assert.ok(answer.table.length > 0)
  assert.ok((await (await page.$('.messages')).text()).includes(answer.text), 'The model answer must actually render')
  const elapsedMs = Date.now() - start
  const sessionId = await page.data('activeSession')
  assert.equal(await page.data('questionStatus.quota.used'), before.questionStatus.quota.used + 1)
  await capture('real-user-ui-answer.png')

  console.log('LIVE_UI_PHASE=actual_score_source')
  await tapRendered('.source')
  await waitFor(async () => !!await page.data('source'), 'source sheet')
  const source = await page.data('source')
  privateRecord.source = source
  assert.equal(source.allowed, true)
  assert.equal(source.rows.length, 1, 'A student source may contain only the student themselves')
  assert.equal(source.rows[0].id, before.identity.id)
  assert.ok(answer.table.some(row => Number(row.score) === Number(source.rows[0].score) && Number(row.max) === Number(source.rows[0].max)), 'Displayed score differs from the existing backend source')
  await capture('real-user-ui-source.png')
  await tapRendered('.sheet .btn')
  await waitFor(async () => !await page.data('source'), 'close source')

  console.log('LIVE_UI_PHASE=shared_backend_and_history')
  const savedState = await page.callMethod('rpc', '/mini/state')
  const saved = savedState.sessions.find(row => row.id === sessionId)
  assert.ok(saved, 'The native conversation is missing from the shared web API')
  assert.equal(saved.messages[saved.messages.length - 1].id, answer.id)
  assert.equal(saved.messages[saved.messages.length - 1].text, answer.text)
  assert.equal(savedState.questionStatus.quota.used, before.questionStatus.quota.used + 1)
  await tapRendered('.tab-item[data-view="tools"]')
  await waitFor(async () => await page.data('view') === 'tools', 'tools')
  await tapRendered('.tool-card[data-view="history"]')
  await waitFor(async () => await page.data('view') === 'history', 'history')
  const historyRow = await page.$('.session[data-id="' + sessionId + '"]')
  assert.ok(historyRow, 'The saved question is missing from native history')
  await tapRendered('.session[data-id="' + sessionId + '"]')
  await waitFor(async () => await page.data('view') === 'chat' && await page.data('activeSession') === sessionId, 'reopen conversation')
  assert.equal((await page.data('messages')).at(-1).id, answer.id)
  assert.equal((await page.data('identity')).userId, before.identity.userId)
  assert.equal(errors.length, 0, 'Native runtime raised an exception')
  privateRecord.savedSession = saved
  privateRecord.errors = errors
  await writeFile(path.join(output, 'live-ui-private.json'), JSON.stringify(privateRecord, null, 2), { mode: 0o600 })
  const summary = {
    environment: health.environment, provider: health.model.configured_provider,
    model: health.model.default_model, testModel: false, role: before.identity.role,
    authorizedExams: before.exams.length, authorizedReports: before.reports.length,
    checks: { nativeInputAndSend: true, renderedRealModelAnswer: true, ordinaryLanguage: true, scoreMatchesBackendSource: true,
      sharedWebApiReadback: true, historyReopen: true, oneQuestionCharged: true, loginPreserved: true },
    elapsedMs, nativeExceptions: errors.length
  }
  await writeFile(path.join(output, 'live-ui-result.json'), JSON.stringify(summary, null, 2), { mode: 0o600 })
  console.log(JSON.stringify(summary))
} catch (error) {
  privateRecord.errors = errors
  privateRecord.failure = String(error)
  if (page) {
    privateRecord.view = await page.data('view').catch(() => undefined)
    privateRecord.notice = await page.data('notice').catch(() => undefined)
    privateRecord.messages = await page.data('messages').catch(() => undefined)
  }
  await writeFile(path.join(output, 'live-ui-private.json'), JSON.stringify(privateRecord, null, 2), { mode: 0o600 })
  throw error
} finally {
  // Leave the owner's genuine login and the new answer available in the developer tool.
  // Restore any unsent text only after the verification question actually completed.
  if (page && originalDraft && submitted && !await page.data('busy').catch(() => true)) {
    await page.setData({ chatDraft: originalDraft }).catch(() => {})
  }
  await mini.disconnect()
}

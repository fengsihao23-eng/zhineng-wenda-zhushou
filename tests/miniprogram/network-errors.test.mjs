import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../../apps/miniprogram/utils/api.js', import.meta.url), 'utf8')
function client({ base = 'http://43.161.195.51/api/v1', envVersion = 'develop', failure, response, loggedIn = false } = {}) {
  let requests = 0, writes = 0
  const stored = loggedIn ? { access_token: 'synthetic-access', refresh_token: 'synthetic-refresh', user: { id: 'synthetic-user' } } : null
  const wx = {
    getAccountInfoSync: () => ({ miniProgram: { envVersion } }),
    getStorageSync: () => stored,
    setStorageSync: () => { writes++ }, removeStorageSync: () => { writes++ },
    request: options => { requests++; response ? options.success(response) : options.fail(failure) },
    downloadFile: options => { requests++; options.fail(failure) }
  }
  const module = { exports: {} }
  vm.runInNewContext('(function(require,module,exports){' + source + '\n})', { wx, Promise, ArrayBuffer })
    (name => { assert.equal(name, '../config'); return { apiBaseUrl: base } }, module, module.exports)
  return { api: module.exports, requestCount: () => requests, storageWrites: () => writes }
}
const credentials = { username: 'private-test-account', password: 'private-test-password' }

test('HTTP development domain denial gives the owner an actionable retry step without credentials', async () => {
  const c = client({ failure: { errMsg: 'request:fail url not in domain list' } })
  await assert.rejects(c.api.login(credentials), error => {
    assert.equal(error.code, 'NETWORK_DOMAIN_BLOCKED')
    assert.match(error.message, /开发调试/)
    assert.match(error.message, /重新进入/)
    assert.ok(!error.message.includes(credentials.username) && !error.message.includes(credentials.password))
    return true
  })
  assert.equal(c.storageWrites(), 0)
})

test('HTTPS domain denial directs the user to the administrator', async () => {
  const c = client({ base: 'https://qa.example.com/api/v1', envVersion: 'trial', failure: { errMsg: 'request:fail url not in domain list' } })
  await assert.rejects(c.api.login(credentials), error => {
    assert.equal(error.code, 'NETWORK_DOMAIN_BLOCKED')
    assert.match(error.message, /管理员/)
    assert.ok(!error.message.includes('开发调试'))
    return true
  })
})

test('HTTP remains blocked before transmission in trial and release builds', async () => {
  for (const envVersion of ['trial', 'release']) {
    const c = client({ envVersion, failure: { errMsg: 'should not be transmitted' } })
    await assert.rejects(c.api.login(credentials), /HTTPS/)
    assert.equal(c.requestCount(), 0)
    assert.equal(c.storageWrites(), 0)
  }
})

test('network timeout and TLS failure have different recovery messages', async () => {
  for (const [reason, code, message] of [
    ['request:fail timeout', 'NETWORK_TIMEOUT', /超时/],
    ['request:fail ssl hand shake error', 'NETWORK_TLS_ERROR', /证书/]
  ]) {
    const c = client({ failure: { errMsg: reason } })
    await assert.rejects(c.api.login(credentials), error => error.code === code && message.test(error.message))
  }
})

test('unknown transport errors keep safe details while omitting request URLs', async () => {
  const c = client({ failure: { errMsg: 'request:fail connection refused http://43.161.195.51/api/v1/auth/login' } })
  await assert.rejects(c.api.login(credentials), error => {
    assert.equal(error.code, 'NETWORK_ERROR')
    assert.match(error.message, /connection refused/)
    assert.ok(!error.message.includes('43.161.195.51'))
    assert.ok(!error.details.networkReason.includes('/auth/login'))
    return true
  })
})

test('a server password rejection retains its auth status and message', async () => {
  const c = client({ response: { statusCode: 401, data: { error: { code: 'INVALID_CREDENTIALS', user_message: '账号或密码不正确' } } } })
  await assert.rejects(c.api.login(credentials), error => error.status === 401 && error.code === 'INVALID_CREDENTIALS' && error.message === '账号或密码不正确')
  assert.equal(c.storageWrites(), 0)
})

test('download failures use the same network diagnosis without discarding the login', async () => {
  const c = client({ loggedIn: true, failure: { errMsg: 'downloadFile:fail url not in domain list' } })
  await assert.rejects(c.api.file('/answer-workbench/reports/synthetic/file'), error => error.code === 'NETWORK_DOMAIN_BLOCKED')
  assert.equal(c.storageWrites(), 0)
  assert.equal(c.api.auth().user.id, 'synthetic-user')
})

'use strict';
const config = require('../config');
const AUTH_KEY = 'subject-assistant.auth.v1';
const BASE = config.apiBaseUrl.replace(/\/$/, '');
let credentials = null, hydrated = false, generation = 0, ownerGeneration = 0, refreshing = null;

function uuid() {
  // Idempotency identifiers are not credentials. Auth tokens are server generated.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const n = Math.floor(Math.random() * 16);
    return (c === 'x' ? n : (n & 3) | 8).toString(16);
  });
}
function auth() {
  if (!hydrated) {
    hydrated = true;
    let stored;
    try { stored = wx.getStorageSync(AUTH_KEY); } catch (_) { return null; }
    if (stored && typeof stored === 'object' && stored.access_token && stored.refresh_token && stored.user && typeof stored.user.id==='string') credentials = stored;
  }
  return credentials;
}
function setAuth(value) {
  // Persist before switching in-memory identity so storage failures cannot silently log in.
  wx.setStorageSync(AUTH_KEY, value);
  if (!credentials || credentials.user.id !== value.user.id) ownerGeneration++;
  credentials = value;
  hydrated = true;
  generation++;
}
function clearAuth() {
  credentials = null;
  hydrated = true;
  generation++;
  ownerGeneration++;
  try { wx.removeStorageSync(AUTH_KEY); } catch (_) { /* In-memory credentials are already discarded. */ }
}
function errorFrom(response) {
  let body = response.data;
  if (body instanceof ArrayBuffer) {
    // File endpoints are downloaded with wx.downloadFile, not request(arraybuffer).
    body = {};
  }
  const detail = body && (body.error || body.detail) || {};
  const err = new Error(typeof detail === 'string' ? detail : detail.user_message || detail.message || '请求失败，请稍后重试');
  err.status = response.statusCode;
  err.code = detail.code || response.header && (response.header['X-Error-Code'] || response.header['x-error-code']);
  err.details = detail.details || {};
  return err;
}
function assertOwner(scope) {
  if (!auth() || ownerGeneration !== scope) {
    const error = new Error('登录身份已变化，请重新操作');
    error.code = 'STALE_SESSION';
    throw error;
  }
}
function validateBase() {
  let version = 'develop';
  try { version = wx.getAccountInfoSync().miniProgram.envVersion; } catch (_) { /* Older local runtimes. */ }
  if (version !== 'develop' && (!/^https:\/\//.test(BASE) || /https:\/\/(?:localhost|127\.|0\.0\.0\.0)/.test(BASE))) {
    throw new Error('小程序尚未配置正式 HTTPS 服务地址，请联系管理员。');
  }
}
function networkError(cause, fallback) {
  const rawReason = typeof cause === 'string' ? cause : cause && (cause.errMsg || cause.message) || '';
  // Keep device diagnostics without exposing request URLs, headers or login inputs.
  const reason = String(rawReason).replace(/https?:\/\/[^\s"'<>]+/gi, '服务地址').slice(0, 180);
  const error = new Error(fallback);
  error.code = 'NETWORK_ERROR';
  error.details = {networkReason:reason};
  if (/domain\s*list|legal\s*domain|合法域名|域名.*(?:校验|未配置|不允许)|https.*required|only.*https|http.*not\s*(?:allowed|supported)/i.test(reason)) {
    error.code = 'NETWORK_DOMAIN_BLOCKED';
    error.message = /^http:\/\//.test(BASE)
      ? '微信尚未允许连接当前内测服务。请在右上角“…”打开开发调试，重新进入小程序后再试。'
      : '微信尚未允许连接服务域名，请联系管理员核对小程序网络配置。';
  } else if (/timeout|timed\s*out|超时/i.test(reason)) {
    error.code = 'NETWORK_TIMEOUT';
    error.message = '连接服务超时，请检查网络后重试；输入内容已保留。';
  } else if (/\bssl\b|\btls\b|certificate|handshake|证书/i.test(reason)) {
    error.code = 'NETWORK_TLS_ERROR';
    error.message = '服务安全连接失败，请联系管理员检查 HTTPS 证书及网络配置。';
  } else if (reason) {
    error.message += '\n连接详情：' + reason;
  }
  return error;
}
function raw(path, body, method, token, key) {
  validateBase();
  return new Promise((resolve, reject) => wx.request({
    url: BASE + path, method: method || (body === undefined ? 'GET' : 'POST'), data: body,
    timeout: 55000,
    header: Object.assign({'Content-Type': 'application/json'}, token ? {Authorization:'Bearer '+token} : {}, key ? {'Idempotency-Key':key} : {}),
    success: response => response.statusCode >= 200 && response.statusCode < 300 ? resolve(response.data) : reject(errorFrom(response)),
    fail: cause => reject(networkError(cause, '暂时无法连接服务，请检查网络后重试；输入内容已保留。'))
  }));
}
async function refresh() {
  if (!refreshing) {
    const original = auth(), scope = generation;
    if (!original) throw new Error('请先登录');
    refreshing = raw('/auth/refresh', {refresh_token:original.refresh_token}, 'POST').then(value => {
      if (scope !== generation) throw new Error('登录身份已变化，请重新操作');
      setAuth(Object.assign({}, original, value));
      return auth();
    }).catch(error => {
      if ((error.status === 401 || error.status === 403) && scope === generation) clearAuth();
      throw error;
    }).finally(() => { refreshing = null; });
  }
  return refreshing;
}
async function request(path, body, options) {
  const opts = options || {}, current = auth(), scope = generation, owner = ownerGeneration;
  if (!current) { const error = new Error('请先登录'); error.status = 401; throw error; }
  try {
    const value = await raw(path, body, opts.method, current.access_token, opts.key);
    assertOwner(owner);
    return value;
  } catch (error) {
    assertOwner(owner);
    if (error.status !== 401 || opts.noRefresh) throw error;
    if (scope !== generation && !auth()) throw error;
    const next = scope === generation ? await refresh() : auth();
    if (!next || next.user && current.user && next.user.id !== current.user.id) throw error;
    const value = await raw(path, body, opts.method, next.access_token, opts.key);
    assertOwner(owner);
    return value;
  }
}
async function login(body) {
  const value = await raw('/auth/login', body, 'POST');
  setAuth(value);
  return value.user;
}
async function logout() {
  const current = auth();
  try {
    if (current) await raw('/auth/logout', {refresh_token:current.refresh_token}, 'POST', current.access_token);
  } finally { clearAuth(); }
}
async function changePassword(current, next) {
  const value = await request('/auth/change-password', {current_password:current, new_password:next});
  const previous = auth();
  setAuth(Object.assign({}, previous, value, {user:Object.assign({}, previous.user, {must_change_password:false})}));
}
async function file(path, retry) {
  validateBase();
  const current = auth(), scope = generation, owner = ownerGeneration;
  if (!current) throw new Error('请先登录');
  const response = await new Promise((resolve, reject) => wx.downloadFile({url:BASE+path,
    header:{Authorization:'Bearer '+current.access_token}, timeout:55000,
    success:resolve, fail:cause=>reject(networkError(cause, '报告未下载成功，请检查网络后重试'))}));
  try { assertOwner(owner); } catch (error) {
    try { wx.getFileSystemManager().unlinkSync(response.tempFilePath); } catch (_) { /* Best effort. */ }
    throw error;
  }
  if (response.statusCode === 401 && !retry) {
    if (scope === generation) await refresh();
    return file(path, true);
  }
  if (response.statusCode !== 200) {
    try { wx.getFileSystemManager().unlinkSync(response.tempFilePath); } catch (_) { /* Best effort. */ }
    const error = new Error(response.statusCode===404 || response.statusCode===403 ? '报告不存在、版本已变化或当前无权查看。' : '报告读取失败，请稍后重试');
    error.status = response.statusCode;
    throw error;
  }
  return response.tempFilePath;
}
module.exports = {request, login, logout, changePassword, file, auth, uuid, clearAuth};

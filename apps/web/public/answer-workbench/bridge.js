/* Same-origin RPC uses the application's existing in-memory authentication and refresh flow. */
'use strict';
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const copy = v => structuredClone(v), clone = copy, uniq = a => [...new Set(a)];
const now = () => new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai', hour12: false }), stamp = now;
const uid = () => typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c => (Number(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> Number(c) / 4).toString(16)), uuid = uid;
const pending = new Map();
window.addEventListener('message', event => { if (event.origin !== location.origin || event.source !== parent || event.data?.type !== 'answer-result')
    return; const item = pending.get(event.data.id); if (!item)
    return; clearTimeout(item.timer); pending.delete(event.data.id); if (event.data.error) {
    const error = new Error(event.data.error.message);
    error.status = event.data.error.status;
    item.reject(error);
}
else
    item.resolve(event.data.value); });
function rpc(path, body, method = body === undefined ? 'GET' : 'POST', options = {}) { return new Promise((resolve, reject) => { const id = uid(), timer = setTimeout(() => { pending.delete(id); reject(new Error('请求超时，当前编辑内容保留，请重试。')); }, 60000); pending.set(id, { resolve, reject, timer }); parent.postMessage({ type: 'answer-request', id, path, body, method, ...options }, location.origin); }); }
function toast(msg) { const el = $('toast'); el.className = 'toast'; el.textContent = msg; clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.textContent = ''; el.className = ''; }, 4200); }
function blobResult(result, type) { return new Blob([result], { type }); }
function downloadBlob(blob, name) { const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 5000); }
window.addEventListener('error', e => { toast('页面操作失败，请刷新重试。'); console.error(e.error); });
window.addEventListener('unhandledrejection', e => { toast(e.reason?.message || '操作失败，当前编辑内容保留。'); console.error(e.reason); });

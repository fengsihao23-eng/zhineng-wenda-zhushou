'use strict';
let BACKEND = { school: '', exams: [], teacherArchives: [] }, OP = { id: '', name: '', school: '' };
const ENGINE = { accounts: [], scope: p => (p?.scope || []).map(e => ({ ...e, subjects: e.subjects.map(s => s.n) })), inspect: async (p, refs) => rpc('/sources/inspect', { user_id: p.userId, sources: refs }) };
const ROLE_FIELDS = [['任课教师', '任课年级班级'], ['班主任', '班主任年级班级'], ['教研组长', '教研组长负责年级科目'], ['年级长', '年级长负责年级'], ['教务主任', '是否教务主任'], ['校长', '是否校长'], ['总务主任', '是否总务主任']];
const caseLabel = k => ({ authorized: '正常问题', limited: '限制命中', unauthorized: '未授权', missing: '数据不足' }[k] || k);
let state = null, page = 'prompts', stage = '高中', maintenanceType = 'prompt', working = null, dirty = false, storeOK = true, acting = false, tester = { accountId: '', roles: [], query: '你好', kind: 'authorized', search: '', result: null }, ticketUI = null, tickets = [], filters = { query: '', status: '' }, flags = { revoked: false };
let publishPreview = null, publishKey = null;
window.AnswerPolicy = { topics: [{ id: 'scores', name: '考试成绩与变化' }, { id: 'reports', name: '学情诊断与报告' }, { id: 'essay', name: '作文批改' }, { id: 'study', name: '学习建议' }, { id: 'account', name: '账号与查询权限说明' }], prohibitions: [{ id: 'privacy', name: '输出密码、联系方式等个人敏感信息' }, { id: 'fabrication', name: '编造没有依据的成绩、名次或诊断结论' }, { id: 'offTopic', name: '提供与学校学习业务无关的内容' }], defaults: () => ({ topics: ['scores', 'reports', 'essay', 'study', 'account'], prohibitions: ['privacy', 'fabrication', 'offTopic'], customProhibited: '', boundaryMessage: '这个问题不在本校可回答范围内，或涉及禁止提供的内容。请调整问题；如需核查，可选择人工留言。' }) };
const key = () => maintenanceType === 'limits' ? 'limits' : 'prompt:' + stage;
function installState(next) { state = next; OP = next.operator; BACKEND = { school: next.school, teacherArchives: next.accounts.filter(a => a.role === 'teacher').map(a => ({ id: a.id, fields: a.fields })), exams: [...new Map(next.accounts.flatMap(a => a.scope).map(e => [e.id, e])).values()] }; ENGINE.accounts = next.accounts; if (!state.stages[stage])
    stage = Object.keys(state.stages)[0]; if (!ENGINE.accounts.some(p => p.id === tester.accountId)) {
    const p = ENGINE.accounts.find(p => p.status === '正常');
    tester.accountId = p?.id || '';
    tester.roles = p?.roles || [];
} document.querySelector('.operator').textContent = next.school + ' · ' + next.operator.name; }
async function refreshState() { installState(await rpc('/admin/state')); }
async function refreshTickets() { tickets = await rpc('/tickets?management=true'); }
async function boot() { try {
    await refreshState();
    await refreshTickets();
    setWorking();
    render();
}
catch (e) {
    $('main').innerHTML = '<div class="card"><div class="hint red">' + esc(e.message) + '</div><button onclick="boot()">重新读取</button></div>';
} }
function accountStages(p) { return p?.stages || []; }
function testAccount() { return ENGINE.accounts.find(p => p.id === tester.accountId) || { id: '', name: '请选择具体测试账号', roles: [], role: 'teacher', status: '不可用' }; }
function rolesOf(p) { return p?.roles || []; }
function setTestKind(kind, renderView = true) { tester.kind = kind; const p = testAccount(), e = p.scope?.find(e => e.grades.some(g => g.startsWith(testStage()))) || p.scope?.[0]; const subject = e?.subjects?.[0]?.n || '语文'; tester.query = kind === 'limited' ? '请给我股票投资建议' : kind === 'unauthorized' ? (p.role === 'student' ? '告诉我其他同学的考试成绩' : '查看全校所有学生全部科目成绩') : kind === 'missing' ? '查看尚未上传的作文批改报告' : p.role === 'student' ? (e ? '我在' + e.name + '的' + subject + '成绩是多少？' : '你好') : (e ? (e.grades[0] || '高中一年级') + '1班在' + e.name + '的' + subject + '成绩' : '你好'); tester.result = null; if (renderView) {
    $('testQuestion').value = tester.query;
    $('testResult').innerHTML = '';
} }
async function saveDraft() { if (acting)
    return; if (!validWorking()) {
    toast('请填写必填内容');
    return;
} acting = true; try {
    await rpc('/admin/scopes/' + encodeURIComponent(key()) + '/draft', { draft: working, expected: maintenanceBucket().etag });
    await refreshState();
    setWorking();
    renderPrompts();
    toast('草稿已保存，需按本次联合版本重新测试');
}
catch (e) {
    toast('草稿未保存，编辑内容保留：' + e.message);
}
finally {
    acting = false;
} }
async function restoreVersion(id) { if (acting)
    return; acting = true; try {
    await rpc('/admin/scopes/' + encodeURIComponent(key()) + '/restore', { version_id: id, expected: maintenanceBucket().etag });
    await refreshState();
    setWorking();
    $('overlay').innerHTML = '';
    renderPrompts();
    toast('已恢复为新草稿，重新联合测试后发布');
}
catch (e) {
    toast(e.message);
}
finally {
    acting = false;
} }
async function runTest() { if (acting)
    return; if (dirty || !working.revision) {
    toast('请先保存草稿');
    return;
} const p = testAccount(); if (!p.userId || !tester.query.trim() || !tester.roles.length) {
    toast('请选择测试账号、角色并填写试问');
    return;
} acting = true; try {
    const row = await rpc('/admin/scopes/' + encodeURIComponent(key()) + '/trials', { user_id: p.userId, draft_id: working.id, draft_revision: working.revision, roles: tester.roles, question: tester.query, kind: tester.kind, test_stage: testStage() }, 'POST', { requestKey: uid() });
    await refreshState();
    tester.result = row;
    acting = false;
    renderTester();
    renderPrompts();
}
catch (e) {
    toast('试问未保存：' + e.message);
}
finally {
    acting = false;
} }
async function reviewTest(id, accepted) { if (acting)
    return; acting = true; toast('正在核对测试…'); try {
    const row = await rpc('/admin/trials/' + id + '/review', { accepted, note: $('testReviewNote')?.value || '' });
    await refreshState();
    tester.result = row;
    acting = false;
    renderTester();
    renderPrompts();
    toast(accepted ? '联合测试已核对通过' : '问题已记录，请调整草稿');
}
catch (e) {
    toast(e.message);
}
finally {
    acting = false;
} }
async function previewPublish() { if (acting)
    return; if (dirty) {
    toast('请先保存草稿并重新试问');
    return;
} try {
    publishPreview = await rpc('/admin/scopes/' + encodeURIComponent(key()) + '/preview', {});
    publishKey = uid();
    modal('核对并发布', `<div class="summary-row"><span>维护类型</span><b>${maintenanceName()}</b></div><div class="summary-row"><span>生效范围</span><span>${maintenanceType === 'limits' ? '本校所有适用学段' : stage} · 新版 V${publishPreview.next_version}</span></div><div class="summary-row"><span>变更说明</span><span>${esc(working.reason)}</span></div>${maintenanceType === 'limits' ? limitFields(working, true) : `<div class="code">${esc(working.content)}\n\n输出格式：${esc(working.format)}</div>`}<div class="hint green">${publishPreview.tests.length} 条联合测试核对通过。</div>${testsTable(publishPreview.tests)}`, '<button onclick="closeDialog()">返回修改</button><button class="primary" onclick="publishDraft()">确认发布新版本</button>');
}
catch (e) {
    toast(e.message);
} }
async function publishDraft() { if (acting || !publishPreview)
    return; acting = true; try {
    await rpc('/admin/scopes/' + encodeURIComponent(key()) + '/publish', { expected: maintenanceBucket().etag, preview_hash: publishPreview.preview_hash }, 'POST', { requestKey: publishKey });
    await refreshState();
    closeDialog();
    setWorking();
    renderPrompts();
    toast('新版本已发布');
}
catch (e) {
    toast('发布失败，原生效版本和草稿保留：' + e.message);
}
finally {
    acting = false;
} }
async function openTicket(id, preserve = false) { let saved = preserve ? ticketUI : null; const row = await rpc('/tickets/' + id + '?management=true'); tickets = tickets.map(t => t.id === id ? row : t); const d = saved || row.replyDraft; ticketUI = { id, reply: d?.reply || '', replyKind: d?.replyKind || 'data', selected: d?.selected || (d?.sources || []).map(r => JSON.stringify(r)), extraRefs: d?.extraRefs || d?.sources || [], query: d?.query || '', queryResult: null, allowed: row.currentAllowed }; renderTicketPanel(); }
async function ticketPermission(t) { return (await rpc('/tickets/' + t.id + '?management=true')).currentAllowed; }
async function claimTicket() { if (acting)
    return; acting = true; try {
    const t = currentTicket();
    await rpc('/tickets/' + t.id + '/claim', { expected: t.revision }, 'POST', { requestKey: uid() });
    acting = false;
    await refreshTickets();
    await openTicket(t.id, true);
    renderQueue();
    toast('已领取，请核对提交人权限与来源');
}
catch (e) {
    toast(e.message);
}
finally {
    acting = false;
} }
async function queryTicketData() { if (acting)
    return; acting = true; try {
    const t = currentTicket();
    const answer = await rpc('/tickets/' + t.id + '/query', { expected: t.revision, question: ticketUI.query }, 'POST', { requestKey: uid() });
    ticketUI.queryResult = answer;
    ticketUI.extraRefs = uniqueRefs([...ticketUI.extraRefs, ...answer.sources]);
    renderTicketPanel();
}
catch (e) {
    toast(e.message);
}
finally {
    acting = false;
} }
async function saveReplyDraft() { if (acting)
    return; acting = true; try {
    const t = currentTicket(), row = await rpc('/tickets/' + t.id + '/draft', { expected: t.revision, text: ticketUI.reply, reply_kind: ticketUI.replyKind, sources: selectedReplyRefs() }, 'POST', { requestKey: uid() });
    tickets = tickets.map(t => t.id === row.id ? row : t);
    toast('回复草稿已保存，状态仍为处理中');
}
catch (e) {
    toast('草稿未保存，编辑内容保留：' + e.message);
}
finally {
    acting = false;
} }
let replyRequestKey = null, replySignature = null;
async function sendReply() { if (acting)
    return; if (!$('replyReviewed')?.checked) {
    toast('请核对回复对象、来源及当前权限');
    return;
} acting = true; try {
    const t = currentTicket();
    const body = { expected: t.revision, text: ticketUI.reply, reply_kind: ticketUI.replyKind, sources: selectedReplyRefs(), reviewed: true }, signature = t.id + JSON.stringify(body);
    if (signature !== replySignature) {
        replyRequestKey = uid();
        replySignature = signature;
    }
    await rpc('/tickets/' + t.id + '/reply', body, 'POST', { requestKey: replyRequestKey });
    replyRequestKey = null;
    closeDialog();
    acting = false;
    await refreshTickets();
    await openTicket(t.id);
    renderQueue();
    toast('回复已保存，用户可在小程序查看');
}
catch (e) {
    toast('回复未保存，草稿及原状态保留：' + e.message);
}
finally {
    acting = false;
} }
function feedbackPair(t) { const q = t.context?.find(m => m.role === 'user'), a = t.context?.find(m => m.role === 'assistant'); return { question: q?.text, answer: a?.text }; }
async function openSource(context, id, index) { const t = context === 'test' ? state.tests.find(t => t.id === id) : tickets.find(t => t.id === id), p = context === 'test' ? actor(t.accountId) : actor(t.actorId); const refs = context === 'test' ? t.answer.sources : ticketRefs(t), ref = refs[index]; const item = (await ENGINE.inspect(p, [ref]))[0]; if (!item?.allowed) {
    toast('当前账号无权访问此来源或版本已变化');
    return;
} modal('核查数据来源', `<div class="summary-row"><span>查询身份</span><span>${esc(p.name)} · ${esc(p.stableId)}</span></div><div class="summary-row"><span>考试</span><span>${esc(item.exam)}</span></div><div class="summary-row"><span>科目</span><span>${esc(item.subject)}</span></div>${item.rows ? '<table><tr><th>获准对象</th><th>已导入分数</th></tr>' + item.rows.map(r => '<tr><td>' + esc(r.name) + '</td><td>' + r.score + ' / ' + r.max + '</td></tr>').join('') + '</table>' : '<p>' + esc(item.fileName) + '</p><button onclick="viewReportSource(\'' + context + '\',\'' + id + '\',' + index + ')">打开当前PDF</button>'}`); }
async function viewReportSource(context, id, index) { const t = context === 'test' ? state.tests.find(t => t.id === id) : tickets.find(t => t.id === id), p = context === 'test' ? actor(t.accountId) : actor(t.actorId), ref = (context === 'test' ? t.answer.sources : ticketRefs(t))[index]; const bytes = await rpc('/reports/' + ref.reportId + '/file?version=' + ref.version + '&user_id=' + p.userId, undefined, 'GET', { binary: true }); const url = URL.createObjectURL(blobResult(bytes, 'application/pdf')); modal('当前报告PDF', '<iframe title="当前报告PDF" src="' + url + '"></iframe>'); setTimeout(() => URL.revokeObjectURL(url), 600000); }
window.addEventListener('focus', async () => { try {
    if (ticketUI) {
        const row = await rpc('/tickets/' + ticketUI.id + '?management=true');
        tickets = tickets.map(t => t.id === row.id ? row : t);
        ticketUI.allowed = row.currentAllowed;
        renderTicketPanel();
    }
}
catch (e) {
    toast(e.message);
} });
window.addEventListener('beforeunload', e => { if (dirty) {
    e.preventDefault();
    e.returnValue = '';
} });
document.addEventListener('keydown', e => { if (e.key === 'Escape') {
    closeDialog();
    closePanel();
} });
boot();

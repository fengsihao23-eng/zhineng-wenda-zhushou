'use strict';
let BACKEND = { school: '学校', exams: [] }, model = { sessions: [], tickets: [], audit: [] }, storageOK = true, reports = [], identity = null, view = 'chat', activeSession = null, activeTicket = null, chatDraft = '', ticketDraft = null, busy = false, reader = null, returnView = 'reports', reportFilters = { category: '', exam: '', subject: '', query: '' }, scenario = { disabled: false };
const TYPES = { student: ['个人学情诊断', 'student'], classAll: ['班级综合诊断', 'class'], classSubject: ['班级单科诊断', 'class'], gradeAll: ['年级综合诊断', 'grade'], gradeSubject: ['年级单科诊断', 'grade'], school: ['全校学情诊断', 'school'], essay: ['个人作文批改报告', 'student'] };
const exById = id => BACKEND.exams.find(e => e.id === id) || { id, name: '相关考试', subjects: [] }, subjectName = (ex, k) => ex?.subjects?.find(s => s.k === k)?.n || BACKEND.exams.flatMap(e => e.subjects).find(s => s.k === k)?.n || k, typeInfo = r => TYPES[r.category === 'essay' ? 'essay' : r.type] || ['报告', 'student'], ownerKey = p => p.role + ':' + p.id;
const subjectLabel = r => r.subjects.map(s => subjectName(exById(r.examId), s)).join('、'), objectLabel = r => r.target || '', sourceAllowed = ref => true, sourcesAllowed = refs => true, reportAllowed = r => !!r && reports.some(v => v.id === r.id), accountUsable = p => !!p && p.status === '正常';
const currentSession = () => model.sessions.find(s => s.id === activeSession && s.owner === ownerKey(identity)), currentTicket = () => model.tickets.find(t => t.id === activeTicket && t.owner === ownerKey(identity));
function ticketAccessible(t) { return t.currentAllowed !== false; }
function ensureLogin() { if (!identity) {
    view = 'login';
    render();
    return false;
} return true; }
function closeModal() { $('modal').innerHTML = ''; }
async function refreshBackend() { const next = await rpc('/mini/state'); identity = next.identity; BACKEND = { school: identity.school, exams: next.exams }; reports = next.reports; model = { sessions: next.sessions, tickets: next.tickets, audit: next.audit }; return next; }
const syncSharedModel = refreshBackend;
async function boot() { try {
    const session = await rpc('@session');
    if (session.authenticated) {
        if (session.user?.must_change_password) {
            parent.location.href = '/change-password';
            return;
        }
        await refreshBackend();
        view = 'chat';
    }
    else
        view = 'login';
    render();
}
catch (e) {
    $('screen').innerHTML = '<div class="content"><div class="note error">' + esc(e.message) + '</div><button class="btn" onclick="logout()">返回登录</button></div>';
} }
async function login() { if (busy)
    return; busy = true; try {
    const account = $('account').value.trim(), password = $('password').value;
    const user = await rpc('@login', { username: account, password });
    if (user.must_change_password) {
        parent.location.href = '/change-password';
        return;
    }
    activeSession = null;
    activeTicket = null;
    await refreshBackend();
    view = 'chat';
    render();
}
catch (e) {
    toast(e.message);
}
finally {
    busy = false;
} }
async function logout() { try {
    await rpc('@logout', {});
}
catch (e) {
    toast(e.message);
    return;
} closeReader(); identity = null; model = { sessions: [], tickets: [], audit: [] }; reports = []; activeSession = null; activeTicket = null; ticketDraft = null; chatDraft = ''; view = 'login'; render(); }
let askDraft = null;
async function ask(text) { if (!ensureLogin() || busy)
    return; const q = (text ?? $('question')?.value ?? chatDraft).trim(); if (!q)
    return; busy = true; chatDraft = q; const existing = currentSession(); if (!askDraft || askDraft.question !== q || askDraft.session_id !== (existing?.id || null))
    askDraft = { question: q, session_id: existing?.id || null, key: uid() }; const button = $('sendQuestion'); if (button)
    button.disabled = true; try {
    const s = await rpc('/mini/ask', { question: q, session_id: askDraft.session_id }, 'POST', { requestKey: askDraft.key });
    askDraft = null;
    activeSession = s.id;
    chatDraft = '';
    await refreshBackend();
    view = 'chat';
    render();
    $('screen').scrollTop = $('screen').scrollHeight;
}
catch (e) {
    toast('本次提问未完成，问题已保留：' + e.message);
}
finally {
    busy = false;
    if ($('sendQuestion'))
        $('sendQuestion').disabled = false;
} }
async function navigate(next) { if (next !== 'login' && !ensureLogin())
    return; closeReader(); closeModal(); try {
    if (identity)
        await refreshBackend();
    view = next;
    render();
}
catch (e) {
    toast('读取最新数据失败：' + e.message);
} }
async function openSession(id) { if (!ensureLogin())
    return; await refreshBackend(); if (!model.sessions.some(s => s.id === id))
    return; activeSession = id; view = 'chat'; render(); }
function renderHome() { const prompts = identity.role === 'student' ? ['我这次考试各科成绩怎么样？', '帮我对比期中和月考成绩'] : ['我可以查询哪些考试数据？', '查看已授权的学情诊断报告']; return '<div class="home-welcome"><div class="topline"><span class="school-label">' + esc(BACKEND.school) + '</span><span class="home-avatar">' + esc(identity.name.slice(-1)) + '</span></div><h1>' + esc(identity.name) + '，你好。</h1><p>今天想了解什么？</p></div><section class="home-section home-prompts"><div class="section-heading"><h3>试着问我</h3><span>也可以直接输入问题</span></div>' + prompts.map(p => '<button class="suggestion" data-prompt="' + esc(p) + '"><span class="question-mark">✦</span><b>' + esc(p) + '</b><span class="prompt-arrow">↗</span></button>').join('') + '<p class="home-scope">' + (identity.role === 'student' ? '只使用你本人已开放的考试与报告数据。' : '按学校为你配置的科目、类型和对象范围查询。') + '</p></section>'; }
async function showScope() { await refreshBackend(); $('modal').innerHTML = '<div class="sheet-cover"><div class="sheet"><button class="sheet-close" aria-label="关闭" onclick="closeModal()">×</button><h3>当前查询范围</h3>' + BACKEND.exams.map(e => '<div class="row">' + esc(e.name) + '<div class="small">' + esc(e.subjects.map(s => s.n).join('、')) + '</div><span class="small">' + esc(e.types.join('、')) + '</span></div>').join('') + (!BACKEND.exams.length ? '<div class="empty">当前暂无已开放的数据范围。</div>' : '') + '<div class="note">职务、任教科目和提问中的身份描述不会自动增加权限。</div></div></div>'; }
function renderAudit() { $('screen').innerHTML = '<div class="content">' + model.audit.map(a => '<div class="card"><div class="topline"><b>' + esc(a.action) + '</b><span class="pill">' + esc(a.result) + '</span></div><p class="small">' + esc(a.reportId) + ' · v' + a.version + '<br>' + esc(a.examId) + '<br>' + esc(a.at) + '</p></div>').join('') + (!model.audit.length ? '<div class="empty">暂无报告操作记录</div>' : '') + '</div>'; }
async function previewReport(id) { if (!ensureLogin())
    return; await refreshBackend(); const r = reports.find(r => r.id === id); if (!r) {
    toast('报告已删除或当前无权查看');
    view = 'reports';
    render();
    return;
} returnView = view === 'chat' ? 'chat' : 'reports'; closeReader(); view = 'pdf'; $('pageTitle').textContent = '报告预览'; $('back').hidden = false; $('bottom').style.display = 'none'; $('composer').innerHTML = ''; $('screen').innerHTML = '<div class="pdf-controls"><button class="btn" onclick="pdfPage(-1)">上一页</button><span class="small" id="pdfCount">正在载入…</span><button class="btn" onclick="pdfPage(1)">下一页</button></div><div class="pdf-view" id="pdfCanvasWrap"></div><div class="download-bar"><div class="small">' + esc(typeInfo(r)[0]) + ' · v' + r.version + '</div><button class="btn primary block" onclick="downloadReport(\'' + r.id + '\')">下载当前 PDF</button></div>'; reader = { reportId: id, version: r.version, page: 1, pages: r.pages }; await drawPdf(reader); }
async function drawPdf(current) { const page = current.page, sequence = (current.sequence || 0) + 1; current.sequence = sequence; try {
    const bytes = await rpc('/reports/' + current.reportId + '/file?version=' + current.version + '&page=' + page, undefined, 'GET', { binary: true });
    if (reader !== current || current.sequence !== sequence)
        return;
    const url = URL.createObjectURL(blobResult(bytes, 'image/png'));
    $('pdfCanvasWrap').innerHTML = '<img alt="报告PDF第' + page + '页" style="width:100%;display:block" src="' + url + '">';
    $('pdfCount').textContent = page + ' / ' + current.pages + ' 页';
    current.url && URL.revokeObjectURL(current.url);
    current.url = url;
}
catch (e) {
    if (reader === current) {
        $('pdfCanvasWrap').innerHTML = '<div class="note error">' + esc(e.message) + '</div>';
        toast(e.message);
    }
} }
async function pdfPage(delta) { if (!reader)
    return; reader.page = Math.max(1, Math.min(reader.pages, reader.page + delta)); await drawPdf(reader); }
function closeReader() { if (reader?.url)
    URL.revokeObjectURL(reader.url); reader = null; }
async function downloadReport(id) { try {
    await refreshBackend();
    const r = reports.find(r => r.id === id);
    if (!r)
        throw new Error('当前报告已不可访问');
    const bytes = await rpc('/reports/' + id + '/file?version=' + r.version + '&download=true', undefined, 'GET', { binary: true });
    downloadBlob(blobResult(bytes, 'application/pdf'), r.fileName);
    toast('已发起当前版本PDF下载');
}
catch (e) {
    toast(e.message);
} }
async function openSource(encoded) { const ref = JSON.parse(decodeURIComponent(encoded)); const item = (await rpc('/sources/inspect', { sources: [ref] }))[0]; if (!item?.allowed) {
    toast('来源权限已失效或文件版本已变化');
    await refreshBackend();
    render();
    return;
} if (ref.kind === 'report') {
    await previewReport(ref.reportId);
    return;
} $('modal').innerHTML = '<div class="sheet-cover"><div class="sheet"><button class="sheet-close" aria-label="关闭来源" onclick="closeModal()">×</button><h3>成绩来源</h3><div class="row">' + esc(item.exam) + '<br><span class="small">' + esc(item.subject) + ' · 考务管理已导入成绩</span></div><div class="row">范围：' + esc(item.target) + '<br>获准人数：' + item.rows.length + '</div><div class="small">没有已导入的正式排名时不推算名次。</div></div></div>'; }
function openTicketCompose(messageId, kind) { if (!ensureLogin())
    return; const s = currentSession(), m = s?.messages.find(m => m.id === messageId && m.role === 'assistant'), prior = m ? s.messages[s.messages.indexOf(m) - 1] : null; activeTicket = null; ticketDraft = { requestId: uid(), question: kind === 'answerFeedback' ? '' : prior?.text || '', sessionId: s?.id || null, selected: [], messageId: messageId || null, kind: kind === 'answerFeedback' ? 'answerFeedback' : null, returnView: messageId ? 'chat' : 'tickets' }; view = 'ticketCompose'; render(); }
async function submitTicket() { if (!ensureLogin() || busy || !ticketDraft)
    return; const question = ticketDraft.question.trim(); if (!question) {
    toast('请先填写问题');
    return;
} busy = true; try {
    let t;
    if (activeTicket) {
        const old = currentTicket();
        t = await rpc('/tickets/' + activeTicket + '/append', { expected: old.revision, question, session_id: ticketDraft.sessionId, message_ids: ticketDraft.selected }, 'POST', { requestKey: ticketDraft.requestId });
    }
    else
        t = await rpc('/tickets', { question, session_id: ticketDraft.sessionId, message_ids: ticketDraft.selected, feedback_message_id: ticketDraft.kind === 'answerFeedback' ? ticketDraft.messageId : null }, 'POST', { requestKey: ticketDraft.requestId });
    activeTicket = t.id;
    ticketDraft = null;
    await refreshBackend();
    view = 'ticket';
    render();
    toast('留言已提交，后续可回来查看回复');
}
catch (e) {
    toast('留言未提交，编辑内容保留：' + e.message);
}
finally {
    busy = false;
} }
async function openTicket(id) { await refreshBackend(); let t = model.tickets.find(t => t.id === id); if (!t)
    return; if (t.unread) {
    try {
        t = await rpc('/tickets/' + id + '/read', { expected: t.revision }, 'POST', { requestKey: uid() });
        model.tickets = model.tickets.map(row => row.id === id ? t : row);
    }
    catch (e) {
        toast('已读状态未保存：' + e.message);
    }
} activeTicket = id; view = 'ticket'; render(); }
async function closeTicket() { const t = currentTicket(); if (!t || busy)
    return; busy = true; try {
    await rpc('/tickets/' + t.id + '/close', { expected: t.revision }, 'POST', { requestKey: uid() });
    await refreshBackend();
    render();
}
catch (e) {
    toast(e.message);
}
finally {
    busy = false;
} }
window.addEventListener('focus', async () => { if (!identity)
    return; try {
    await refreshBackend();
    if (!['ticketCompose', 'pdf'].includes(view))
        render();
}
catch (e) {
    if (e.status === 401 || e.status === 403) {
        reports = [];
        model = { sessions: [], tickets: [], audit: [] };
        $('screen').innerHTML = '<div class="content"><div class="note error">' + esc(e.message) + '</div></div>';
    }
    else
        toast(e.message);
} });
document.addEventListener('keydown', e => { if (e.key === 'Escape')
    closeModal(); });
boot();

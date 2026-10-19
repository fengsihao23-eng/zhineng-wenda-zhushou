// Display templates adapted from the supplied mini program prototype.
const TOOL_ENTRIES = [{ id: "reports", title: "报告中心", subtitle: "查看与下载诊断、作文报告", icon: "report", tone: "mint" }, { id: "history", title: "历史会话", subtitle: "找回并继续之前的提问", icon: "clock", tone: "sand" }];
function newChat() { activeSession = null; chatDraft = ''; view = 'chat'; render(); }
function goBack() { if (view === 'pdf') {
    closeReader();
    view = returnView;
    render();
}
else if (view === 'ticketCompose') {
    view = activeTicket ? 'ticket' : ticketDraft?.returnView || 'tickets';
    render();
}
else if (['reports', 'history'].includes(view)) {
    navigate('tools');
}
else if (['ticket', 'audit'].includes(view)) {
    if (view === 'ticket')
        navigate('tickets');
    else {
        view = 'me';
        render();
    }
}
else
    navigate('chat'); }
function render() { const logged = !!identity; if (logged && !accountUsable(identity) && view !== 'login') {
    $('warning').innerHTML = '<div class="storage-warning">当前账号已停用，数据内容已隐藏。</div>';
}
else
    $('warning').innerHTML = storageOK ? '' : '<div class="storage-warning">本地存储不可用，当前操作无法保存。</div>'; const titles = { login: '学科智能问答', activate: '首次登录', chat: '学科智能问答', tools: '学习工具', reports: '我的报告', tickets: '人工留言', me: '我的', history: '历史会话', ticketCompose: '提交人工留言', ticket: '留言详情', pdf: '报告预览', audit: '查看与下载记录' }; $('pageTitle').textContent = titles[view] || '学科智能问答'; $('back').hidden = !['reports', 'history', 'ticketCompose', 'ticket', 'pdf', 'audit'].includes(view); $('composer').innerHTML = ''; $('bottom').style.display = logged && !['activate', 'pdf', 'ticketCompose', 'ticket', 'audit'].includes(view) ? 'flex' : 'none'; $('bottom').innerHTML = [['chat', '问答', 'chat'], ['tools', '学习工具', 'tools'], ['tickets', '留言', 'mail'], ['me', '我的', 'user']].map(([v, t, i]) => '<button class="' + (view === v || v === 'tools' && ['reports', 'history'].includes(view) ? 'on' : '') + '" onclick="navigate(\'' + v + '\')" aria-label="' + t + '">' + icon(i) + t + '</button>').join(''); if (!logged && view !== 'login')
    view = 'login'; if (logged && !accountUsable(identity)) {
    $('screen').innerHTML = '<div class="content"><div class="empty">账号当前不可用，请联系学校管理员。</div><button class="btn block" onclick="logout()">返回登录</button></div>';
    return;
} if (view === 'login')
    renderLogin();
else if (view === 'activate')
    renderActivate();
else if (view === 'chat')
    renderChat();
else if (view === 'tools')
    renderTools();
else if (view === 'reports')
    renderReports();
else if (view === 'tickets')
    renderTickets();
else if (view === 'me')
    renderMe();
else if (view === 'history')
    renderHistory();
else if (view === 'ticketCompose')
    renderTicketCompose();
else if (view === 'ticket')
    renderTicket();
else if (view === 'audit')
    renderAudit(); }
function renderLogin() { $('screen').innerHTML = '<div class="content login"><div class="brandmark">' + icon('spark') + '</div><h1>让每一次提问<br>都有真实的依据。</h1><p class="small">' + esc(BACKEND.school) + ' · 学科智能问答助手<br>使用学校提供的原有账号登录</p><label class="field">登录账号<input id="account" autocomplete="username" placeholder="请输入教师或学生账号"></label><label class="field">密码<input id="password" type="password" autocomplete="current-password" placeholder="请输入密码" onkeydown="if(event.key===\'Enter\')login()"></label><button class="btn primary block" onclick="login()">登录</button><div class="note">身份由账号自动识别，无需选择角色。<br>家长请使用子女的学生账号登录。</div><p class="small">首次登录初始密码与账号相同，登录后需修改。账号问题请联系学校管理员。</p></div>'; }
function renderActivate() { $('screen').innerHTML = '<div class="content"><div class="brandmark">' + icon('user') + '</div><h2>你好，' + esc(identity.name) + '</h2><p class="small">首次登录，请先修改初始密码。</p><label class="field">新密码<input id="newPassword" type="password" autocomplete="new-password" placeholder="至少8位，且不同于账号"></label><label class="field">确认新密码<input id="repeatPassword" type="password" autocomplete="new-password" placeholder="再次输入新密码"></label><button class="btn primary block" onclick="activate()">保存并进入</button><button class="quiet" onclick="logout()">返回登录</button></div>'; }
function sourceTitle(ref) { if (ref.kind === 'report') {
    const r = reports.find(r => r.id === ref.reportId);
    return r ? typeInfo(r)[0] + ' · ' + subjectLabel(r) : '报告已不可用';
} return subjectName(exById(ref.examId), ref.subject) + '成绩 · 考务管理'; }
function sourceButton(ref) { if (!sourceAllowed(ref))
    return ''; const ex = exById(ref.examId); return '<button class="source" onclick="openSource(\'' + encodeURIComponent(JSON.stringify(ref)) + '\')"><b>↗ ' + esc(sourceTitle(ref)) + '</b>' + esc(ex?.name || '') + (ref.kind === 'report' ? ' · ' + esc(ref.reportId) + (ref.page ? ' · 第' + ref.page + '页' : '') : ' · ' + esc(ex.id)) + '</button>'; }
function messageHTML(m) { if (m.role === 'user')
    return '<article class="message user"><div class="bubble">' + esc(m.text) + '</div></article>'; if (!sourcesAllowed(m.sources))
    return '<article class="message">' + assistantLabel(m) + '<div class="bubble">当前权限或来源版本已变化，相关历史答复及来源已隐藏。</div></article>'; return '<article class="message">' + assistantLabel(m) + '<div class="bubble">' + esc(m.text) + (m.table ? '<table class="metric-table"><tr><th>科目</th><th>分数 / 满分</th><th>范围</th></tr>' + m.table.map(r => '<tr><td>' + esc(r.subject) + '</td><td>' + r.score + ' / ' + r.max + '</td><td>' + (r.count > 1 ? r.count + '人平均' : '本人') + '</td></tr>').join('') + '</table>' + m.table.map(r => '<div class="chart"><span>' + esc(r.subject) + '</span><i><i style="width:' + Math.min(100, r.score / r.max * 100) + '%"></i></i><strong>' + r.score + '</strong></div>').join('') : '') + (m.sources || []).map(sourceButton).join('') + '</div>' + (m.choices || []).map(c => '<button class="choice-chip" onclick="ask(\'' + encodeURIComponent(c) + '\'.replace(/%[0-9A-F]{2}/g, x=>x))" data-choice="' + esc(c) + '">' + esc(c) + '</button>').join('') + '' + (!m.fallback ? '<div class="answer-feedback"><span>觉得回答有误？</span><button onclick="openTicketCompose(\'' + m.id + '\',\'answerFeedback\')">留言请人工核查 ↗</button></div>' : '') + '<div class="message-tools">' + (m.fallback ? '<button onclick="openTicketCompose(\'' + m.id + '\')">提交人工留言</button>' : '') + '<span>' + esc(m.at.slice(11, 16)) + '</span></div></article>'; }
function renderHistory() { const rows = model.sessions.filter(s => s.owner === ownerKey(identity)).slice().reverse(); $('screen').innerHTML = '<div class="content"><p class="small">历史数据型答复会按你当前的权限重新核对。</p>' + rows.map(s => '<button class="session" onclick="openSession(\'' + s.id + '\')">' + esc(s.title) + '<small>' + esc(s.updatedAt) + ' · ' + s.messages.filter(m => m.role === 'user').length + '次提问</small></button>').join('') + (!rows.length ? '<div class="empty">还没有会话记录，开始你的第一个问题。</div>' : '') + '</div>'; }
function listReports() { return reports.filter(r => reportAllowed(r)).filter(r => (!reportFilters.category || r.category === reportFilters.category) && (!reportFilters.exam || r.examId === reportFilters.exam) && (!reportFilters.subject || r.subjects.includes(reportFilters.subject)) && (!reportFilters.query || [typeInfo(r)[0], exById(r.examId).name, objectLabel(r), subjectLabel(r), r.id].join(' ').includes(reportFilters.query.trim()))); }
function reportFilter(key, value) { reportFilters[key] = value; renderReports(); if (key === 'query') {
    $('reportSearch').focus();
    $('reportSearch').setSelectionRange(value.length, value.length);
} }
function renderReports() { const allowed = reports.filter(r => reportAllowed(r)), examIds = uniq(allowed.map(r => r.examId)), rows = listReports(); $('screen').innerHTML = '<div class="content"><h2 style="font-size:20px;margin:0 0 9px">属于你的学情档案</h2><p class="small">' + (identity.role === 'student' ? '仅显示本人已开放的诊断与作文报告。' : '仅显示类型、科目和完整对象范围均已获准的报告。') + '</p><input class="search" id="reportSearch" aria-label="搜索报告" placeholder="搜索考试、科目、对象或报告" value="' + esc(reportFilters.query) + '" oninput="reportFilter(\'query\',this.value)"><div class="tabs">' + [['', '全部'], ['diagnostic', '诊断报告'], ['essay', '作文批改']].map(([k, t]) => '<button class="' + (reportFilters.category === k ? 'on' : '') + '" onclick="reportFilter(\'category\',\'' + k + '\')">' + t + '</button>').join('') + '</div><div class="filter-row"><select aria-label="报告考试筛选" onchange="reportFilter(\'exam\',this.value)"><option value="">全部已授权考试</option>' + examIds.map(id => '<option value="' + id + '" ' + (reportFilters.exam === id ? 'selected' : '') + '>' + esc(exById(id).name) + '</option>').join('') + '</select><select aria-label="报告科目筛选" onchange="reportFilter(\'subject\',this.value)"><option value="">全部科目</option>' + uniq(allowed.flatMap(r => r.subjects)).map(k => '<option value="' + k + '" ' + (reportFilters.subject === k ? 'selected' : '') + '>' + esc(subjectName(BACKEND.exams[0], k)) + '</option>').join('') + '</select></div>' + rows.map(r => '<article class="card"><div class="report-head"><div class="report-icon">PDF</div><div><h3>' + esc(typeInfo(r)[0]) + '</h3><p>' + esc(exById(r.examId).name) + '</p><p>' + esc(subjectLabel(r)) + ' · ' + esc(objectLabel(r)) + '</p><p>' + esc(r.id) + ' · v' + r.version + (r.demo ? ' · 演示PDF' : '') + '</p></div></div><div class="actions"><button class="btn" onclick="previewReport(\'' + r.id + '\')">查看报告</button><button class="btn primary" onclick="downloadReport(\'' + r.id + '\')">下载 PDF</button></div></article>').join('') + (!rows.length ? '<div class="empty">' + icon('report') + '暂无可查看报告<br><span class="small">未上传或尚未授权的报告不会列出。</span></div>' : '') + '</div>'; }
function closeReader() { if (reader) {
    reader.task?.cancel();
    reader.doc?.destroy();
    reader = null;
} }
function renderMe() { $('screen').innerHTML = '<div class="content"><div class="profile"><div class="avatar">' + esc(identity.name.slice(-1)) + '</div><div><h2>' + esc(identity.name) + '</h2><span class="pill">' + esc(identity.title) + '</span><div class="small">' + esc(identity.grade + ' ' + identity.cls) + '</div></div></div><div class="card"><div class="small">学校</div>' + esc(BACKEND.school) + '<div class="small" style="margin-top:12px">账号 / 稳定身份ID</div>' + esc(identity.account) + '<div class="small">' + esc(identity.stableId || identity.id) + '</div></div><div class="card"><button class="menu-row" onclick="navigate(\'audit\')">报告查看与下载记录<span>›</span></button><button class="menu-row" onclick="showScope()">我可以查询哪些数据<span>›</span></button></div><div class="note">数据和查询权限由学校后台维护。如需更正档案、补充成绩或开通权限，请联系学校管理员。</div><button class="btn block" onclick="logout()">退出登录</button></div>'; }
function ticketPill(status) { return '<span class="pill ' + (status === '已关闭' ? 'closed' : status === '已回复' ? '' : 'pending') + '">' + status + '</span>'; }
function renderTickets() { const rows = model.tickets.filter(t => t.owner === ownerKey(identity)).slice().reverse(); $('screen').innerHTML = '<div class="content"><div class="topline"><h2 style="font-size:20px;margin:0">未解决的问题，留在这里。</h2></div><p class="small">提交后可离开，之后回来查看回复。<br>人工留言不承诺实时回复或固定时限。</p><button class="btn primary block" onclick="openTicketCompose()">＋ 新建留言</button>' + rows.map(t => '<button class="card" style="width:100%;text-align:left" onclick="openTicket(\'' + t.id + '\')"><div class="topline">' + ticketPill(t.status) + '<span class="small">' + esc(t.updatedAt.slice(5, 16)) + '</span></div><div class="ticket-title">' + esc(ticketAccessible(t) ? t.question.slice(0, 60) : '当前数据权限已变化，仅可查看办理状态') + '</div><div class="small">' + esc(t.id) + (t.unread ? ' · 有新回复' : '') + '</div></button>').join('') + (!rows.length ? '<div class="empty">' + icon('mail') + '还没有留言记录<br><span class="small">你的问题和回复只对本人展示。</span></div>' : '') + '</div>'; }
function contextChoices() { const messages = model.sessions.find(s => s.id === ticketDraft?.sessionId && s.owner === ownerKey(identity))?.messages || []; const index = messages.findIndex(m => m.id === ticketDraft?.messageId), scope = ticketDraft?.kind === 'answerFeedback' ? (index >= 0 ? messages.slice(Math.max(0, index - 1), index + 1) : []) : messages.slice(-6); return scope.filter(m => m.role === 'user' || sourcesAllowed(m.sources)); }
function toggleContext(id, on) { ticketDraft.selected = on ? uniq([...ticketDraft.selected, id]) : ticketDraft.selected.filter(i => i !== id); }
function renderTicketCompose() { if (!ticketDraft) {
    view = 'tickets';
    render();
    return;
} const options = contextChoices(), feedback = ticketDraft.kind === 'answerFeedback', target = feedback ? options.find(m => m.id === ticketDraft.messageId) : null, question = feedback ? options.find(m => m.role === 'user') : null; $('screen').innerHTML = '<div class="content"><h2 style="font-size:19px">' + (activeTicket ? '补充原留言' : ticketDraft.kind === 'answerFeedback' ? '请说明回答中的问题' : '描述你还想了解的问题') + '</h2><p class="small">' + (feedback ? '提交时将关联下方原问题与对应回答，方便人工核查。' : '不会自动提交整段会话或PDF全文。') + '</p>' + (feedback ? '<div class="feedback-target"><b>反馈对象 · 本次回答</b><p>原问题：' + esc(question?.text || '原问题已不可用') + '</p><p>回答摘要：' + esc(target?.text.slice(0, 140) || '当前回答内容已不可用') + '</p></div>' : '') + '<label class="field">问题内容（必填）<textarea id="ticketQuestion" aria-label="留言问题" placeholder="请说明哪一处回答有误，或补充需要核查的情况…" oninput="ticketDraft.question=this.value">' + esc(ticketDraft.question) + '</textarea></label>' + (!feedback && options.length ? '<div class="subtle-title">选择附带上下文（可选，默认不选）</div>' + options.map(m => '<label class="check-context"><input type="checkbox" ' + (ticketDraft.selected.includes(m.id) ? 'checked' : '') + ' onchange="toggleContext(\'' + m.id + '\',this.checked)"><span>' + esc((m.role === 'user' ? '我的问题：' : '助手回答：') + m.text.slice(0, 140)) + '</span></label>').join('') : '') + '<div class="note">核对后点击提交。人工回复沿用你的当前查询权限，不会通过留言扩大数据范围。</div><button class="btn primary block" onclick="submitTicket()" ' + (busy ? 'disabled' : '') + '>确认提交留言</button></div>'; }
function ticketFeedback(t) { if (!t.feedbackMessageId || !ticketAccessible(t))
    return null; let pair = t.context || [], answer = pair.find(m => m.role === 'assistant'), question = pair.find(m => m.role === 'user'); if (!answer || !question) {
    const session = model.sessions.find(s => s.id === t.sessionId && s.owner === ownerKey(identity)), index = session?.messages.findIndex(m => m.id === t.feedbackMessageId && m.role === 'assistant') ?? -1;
    if (index < 1)
        return null;
    answer = session.messages[index];
    question = session.messages[index - 1];
    if (question.role !== 'user')
        return null;
} if (!sourcesAllowed(answer.sources))
    return null; return { question: question.text, answerSummary: answer.text.slice(0, 140) + (answer.text.length > 140 ? '…' : '') }; }
function ticketFeedbackHTML(t) { if (!t.feedbackMessageId)
    return ''; const feedback = ticketFeedback(t); return feedback ? '<div class="feedback-target"><b>反馈对象 · 本次回答</b><p>原问题：' + esc(feedback.question) + '</p><p>回答摘要：' + esc(feedback.answerSummary) + '</p></div>' : '<div class="note">原问题或回答当前不可查看，请重新核对来源与权限。</div>'; }
function renderTicket() { const t = currentTicket(); if (!t) {
    view = 'tickets';
    render();
    return;
} const allowed = ticketAccessible(t); $('screen').innerHTML = '<div class="content"><div class="topline">' + ticketPill(t.status) + '<span class="small">' + esc(t.id) + '</span></div>' + (allowed ? ticketFeedbackHTML(t) : '') + (allowed && t.feedbackMessageId ? '<div class="subtle-title">核查说明</div>' : '') + '<h3 class="ticket-title">' + esc(allowed ? t.question : '权限已变化，当前仅显示办理状态') + '</h3><div class="small">提交于 ' + esc(t.createdAt) + '</div>' + (allowed ? '<div class="timeline">' + t.events.map(e => '<div class="event"><b>' + esc(e.role === 'operator' ? '运营管理员' : e.role === 'system' ? '办理状态' : '我') + '</b><time>' + esc(e.at) + '</time>' + esc(e.text) + '</div>').join('') + '</div>' : '<div class="note">关联数据授权已失效，问题上下文与数据型回复已隐藏，办理记录状态保留。</div>') + (t.status === '已回复' ? '<div class="actions"><button class="btn" onclick="appendTicket()">继续补充</button><button class="btn primary" onclick="closeTicket()">已解决，结束办理</button></div>' : t.status === '已关闭' ? '<button class="btn block" onclick="openTicketCompose()">新问题，另建留言</button>' : '<div class="note">' + (t.status === '处理中' ? '运营管理员已领取，正在核对。' : '留言已保存，等待受理。') + '你可以离开此页面，稍后回来查看。</div>') + '</div>'; }
function appendTicket() { const t = currentTicket(); if (!t || t.status !== '已回复')
    return; ticketDraft = { requestId: uuid(), question: '', sessionId: t.sessionId, selected: [] }; view = 'ticketCompose'; render(); }
function toolEntries() { return TOOL_ENTRIES.filter(entry => entry.enabled !== false); }
function assistantLabel() { return '<div class="assistant-label"><i>✦</i>学科助手</div>'; }
function renderTools() { $('screen').innerHTML = '<div class="content tools-page"><div class="tools-intro"><span class="school-label">' + esc(BACKEND.school) + '</span><h1>学习工具</h1><p>查阅资料，继续探索。</p></div><div class="tool-grid">' + toolEntries().map(entry => '<button class="tool-card ' + entry.tone + '" onclick="navigate(\'' + entry.id + '\')"><span class="tool-icon">' + icon(entry.icon) + '</span><span class="tool-arrow">↗</span><b>' + esc(entry.title) + '</b><small>' + esc(entry.subtitle) + '</small></button>').join('') + '</div></div>'; }
function renderHome() { const prompts = identity.role === 'student' ? ['我这次考试各科成绩怎么样？', '帮我对比期中和月考成绩'] : ['高中一年级1班语文成绩', '对比期中和月考语文成绩']; return '<div class="home-welcome"><div class="topline"><span class="school-label">' + esc(BACKEND.school) + '</span><span class="home-avatar">' + esc(identity.name.slice(-1)) + '</span></div><h1>' + esc(identity.name) + '，你好。</h1><p>今天想了解什么？</p></div><section class="home-section home-prompts"><div class="section-heading"><h3>试着问我</h3><span>也可以直接输入问题</span></div>' + prompts.map(p => '<button class="suggestion" data-prompt="' + esc(p) + '"><span class="question-mark">✦</span><b>' + esc(p) + '</b><span class="prompt-arrow">↗</span></button>').join('') + '<p class="home-scope">' + (identity.role === 'student' ? '只使用你本人已开放的考试与报告数据。' : '按学校为你配置的科目、类型和对象范围查询。') + '</p></section>'; }
function renderComposer() { $('composer').innerHTML = '<div class="composer"><textarea id="question" rows="1" aria-label="输入问题" placeholder="输入问题，直接提问或继续追问…" oninput="chatDraft=this.value" onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();ask()}">' + esc(chatDraft) + '</textarea><button id="sendQuestion" aria-label="发送问题" onclick="ask()" ' + (busy ? 'disabled' : '') + '>↑</button></div>'; }
function renderChat() { const s = currentSession(); if (!s || !s.messages.length)
    $('screen').innerHTML = renderHome();
else
    $('screen').innerHTML = '<div class="conversation-heading"><span>' + esc(s.title) + '</span><button class="quiet" onclick="newChat()">新对话</button></div><div class="messages">' + s.messages.map(messageHTML).join('') + '</div>'; renderComposer(); document.querySelectorAll('[data-prompt],[data-choice]').forEach(b => { b.onclick = () => ask(b.getAttribute('data-prompt') || b.getAttribute('data-choice')); }); }

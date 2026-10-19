/* Desktop presentation. Authentication, questions, permissions, tickets and PDF access
 * reuse the existing mini-api.js request/state functions; the phone presentation remains at /mini-preview. */
'use strict';
let webComposing = false;
function webToolbar() {
  const rows = model.sessions.filter(s => s.owner === ownerKey(identity)).slice().reverse();
  $('webToolbar').innerHTML = `<select class="chat-header__sessions" aria-label="选择会话" onchange="this.value?openSession(this.value):newChat()" ${busy?'disabled':''}><option value="">新会话</option>${rows.map(s=>`<option value="${esc(s.id)}" ${s.id===activeSession?'selected':''}>${esc(s.title||'历史会话')}</option>`).join('')}</select><button class="chat-header__action" onclick="newChat()" ${busy?'disabled':''}>新会话</button><button class="chat-header__action" onclick="navigate('tools')">学习工具</button><button class="chat-header__action" aria-label="留言" onclick="navigate('tickets')">人工留言</button><button class="chat-header__action" onclick="navigate('me')">我的</button>`;
}
function render() {
  if (!identity) view = 'login';
  const titles = {chat:'智能问答助手',tools:'学习工具',reports:'报告中心',tickets:'人工留言',history:'历史会话',ticketCompose:'提交人工留言',ticket:'留言详情',me:'我的',audit:'查看与下载记录',login:'智能问答助手',activate:'首次登录'};
  $('pageTitle').textContent = titles[view] || '智能问答助手';
  $('warning').innerHTML = '';
  $('back').hidden = ['chat','login','activate'].includes(view);
  $('composer').innerHTML = '';
  $('bottom').innerHTML = '';
  $('webChat').classList.toggle('is-empty',view==='chat' && !(currentSession()?.messages.length));
  $('screen').className = view==='chat' ? 'screen message-list' : 'screen web-content';
  if (identity) webToolbar(); else $('webToolbar').innerHTML='';
  if (identity && !accountUsable(identity)) {
    $('screen').innerHTML='<div class="empty">账号当前不可用，请联系学校管理员。</div>';return;
  }
  const views = {login:renderLogin,activate:renderActivate,chat:renderChat,tools:renderTools,reports:renderReports,tickets:renderTickets,me:renderMe,history:renderHistory,ticketCompose:renderTicketCompose,ticket:renderTicket,audit:renderAudit};
  views[view]?.();
  parent.postMessage({type:'answer-web-render'},location.origin);
}
function renderHome() {
  const prompts=identity.role==='student'?['我这次考试各科成绩怎么样？','帮我对比期中和月考成绩']:['我可以查询哪些考试数据？','查看已授权的学情诊断报告'];
  return `<div class="message-list__empty"><div class="empty-state"><h3 class="empty-state__title">${esc(identity.name)}，想了解什么，尽管问吧！</h3><p class="empty-state__text">问我任何关于你成绩的问题</p><div class="web-suggestions">${prompts.map(q=>`<button class="choice-chip" data-prompt="${esc(q)}">${esc(q)}</button>`).join('')}</div></div></div>`;
}
function messageHTML(m) {
  if(m.role==='user')return `<article class="message message--user"><div class="message__content"><div class="message__text">${esc(m.text)}</div><div class="message__meta">${esc(m.at?.slice(11,16)||'')}</div></div></article>`;
  const table=m.table?`<table class="metric-table"><thead><tr><th>科目</th><th>分数 / 满分</th><th>范围</th></tr></thead><tbody>${m.table.map(r=>`<tr><td>${esc(r.subject)}</td><td>${r.score} / ${r.max}</td><td>${r.count>1?r.count+'人平均':'本人'}</td></tr>`).join('')}</tbody></table>${m.table.map(r=>`<div class="chart"><span>${esc(r.subject)}</span><i><i style="width:${Math.max(0,Math.min(100,r.score/r.max*100))}%"></i></i><strong>${r.score}</strong></div>`).join('')}`:'';
  return `<article class="message message--assistant"><div class="message__content"><div class="message__text" data-web-message="${esc(m.id)}" data-web-text="${esc(m.text)}">${esc(m.text)}</div>${table}${m.sources?.length?`<div class="message__sources"><span>回答依据</span>${m.sources.map(sourceButton).join('')}</div>`:''}${(m.choices||[]).map(q=>`<button class="choice-chip" data-choice="${esc(q)}">${esc(q)}</button>`).join('')}<div class="message-tools">${!m.fallback?`<button onclick="openTicketCompose('${m.id}','answerFeedback')">留言请人工核查</button>`:`<button onclick="openTicketCompose('${m.id}')">提交人工留言</button>`}<span>${esc(m.at?.slice(11,16)||'')}</span></div></div></article>`;
}
function renderComposer() {
  $('composer').innerHTML=`<form class="input-box" onsubmit="event.preventDefault();sendWebQuestion()"><div class="input-box__container"><textarea class="input-box__textarea" id="question" aria-label="输入问题" rows="1" placeholder="问我任何关于成绩的问题... (Enter发送，Shift+Enter换行)" oninput="chatDraft=this.value" oncompositionstart="webComposing=true" oncompositionend="webComposing=false" onblur="webComposing=false" onkeydown="if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229&&!webComposing){event.preventDefault();sendWebQuestion()}">${esc(chatDraft)}</textarea><button class="input-box__send" id="sendQuestion" aria-label="发送问题" type="submit" ${busy?'disabled':''}><span class="send-icon">➤</span>发送</button></div></form>`;
}
async function sendWebQuestion(text) {
  if(busy||webComposing)return;
  const button=$('sendQuestion');if(button)button.textContent='生成中…';
  const pending = ask(text); webToolbar();
  try{await pending}finally{webToolbar();if($('sendQuestion'))$('sendQuestion').innerHTML='<span class="send-icon">➤</span>发送'}
}
function renderChat() {
  const s=currentSession();
  $('screen').innerHTML=s?.messages.length?s.messages.map(messageHTML).join(''):renderHome();
  renderComposer();
  document.querySelectorAll('[data-prompt],[data-choice]').forEach(b=>{b.onclick=()=>sendWebQuestion(b.getAttribute('data-prompt')||b.getAttribute('data-choice'))});
  parent.postMessage({type:'answer-web-render'},location.origin);
}
boot();

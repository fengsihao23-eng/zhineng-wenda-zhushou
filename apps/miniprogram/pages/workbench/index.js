'use strict';
const api = require('../../utils/api');
const present = require('../../utils/presentation');
const ROOT = '/answer-workbench';
const TITLES = {login:'学科智能问答',activate:'首次登录',chat:'学科智能问答',tools:'学习工具',
  reports:'我的报告',history:'历史会话',tickets:'人工留言',ticket:'留言详情',
  ticketCompose:'提交人工留言',pdf:'报告预览',me:'我的',scope:'当前查询范围',audit:'查看与下载记录'};
const EMPTY = {identity:null,exams:[],reports:[],sessions:[],tickets:[],audit:[],questionStatus:null};
const detailValue = event => event.detail.value;

Page({
  data: {
    view:'login', ready:false, loading:false, busy:false, notice:'', offline:false,
    account:'', password:'', oldPassword:'', newPassword:'', repeatPassword:'', identities:[],
    identity:null, exams:[], reports:[], sessions:[], tickets:[], audit:[], questionStatus:null,
    prompts:[], activeSession:null, activeTicket:null, messages:[], sessionTitle:'',
    chatDraft:'', canRetry:false, ticketQuestion:'', ticketContext:[], selectedContext:[], feedback:null,
    ticket:null, ticketReturn:'tickets', reportFilters:{category:'',exam:'',subject:'',query:''},
    filteredReports:[], examOptions:[{id:'',name:'全部已授权考试'}], subjectOptions:[{id:'',name:'全部科目'}],
    examIndex:0, subjectIndex:0, pdf:null, pdfImage:'', pdfError:'', pdfLoading:false, source:null,
    canBack:false, showTabs:false, scrollTo:'', unreadCount:0,
    tabs:[{id:'chat',title:'问答',icon:'chat'},{id:'tools',title:'学习工具',icon:'tools'},
      {id:'tickets',title:'留言',icon:'mail'},{id:'me',title:'我的',icon:'user'}]
  },
  onLoad() {
    this._client = api.uuid(); this._files = []; this._askDraft = null;
    this._ticketDraft = null; this._syncing = null; this._active = false;
  },
  onShow() {
    this._active = true;
    this.resume();
    clearInterval(this._timer);
    this._timer = setInterval(() => this.poll(), 30000);
  },
  onHide() { this.suspend(); },
  onUnload() { this.suspend(); this.clearFiles(); },
  suspend() {
    this._active = false; clearInterval(this._timer);
    if (api.auth() && this.data.identity) this.rpc('/mini/presence',{client_id:this._client,present:false}).catch(()=>{});
  },
  async onPullDownRefresh() {
    try { await this.resume(); } finally { wx.stopPullDownRefresh(); }
  },
  rpc(path, body, options) { return api.request(ROOT+path, body, options); },
  toast(message) { wx.showToast({title:message,icon:'none',duration:2500}); },
  handleError(error, prefix) {
    if(error.code==='STALE_SESSION')return;
    const message = (prefix || '')+error.message;
    if (error.status===401 || error.status===403 && error.code!=='PASSWORD_CHANGE_REQUIRED') {
      api.clearAuth(); this.clearFiles();
      this._askDraft=null; this._ticketDraft=null; this._sessions=[];
      this.setData(Object.assign({}, EMPTY, {activeSession:null,activeTicket:null,messages:[],ticket:null,
        source:null,pdf:null,pdfImage:'',chatDraft:'',ticketQuestion:'',ticketContext:[],selectedContext:[],
        feedback:null,filteredReports:[],password:'',canRetry:false,notice:message}));
      this.setView('login');
    } else if (error.code==='PASSWORD_CHANGE_REQUIRED') this.setView('activate');
    else this.setData({notice:message,offline:!error.status});
    this.toast(message);
  },
  async resume() {
    if (this.data.busy || this._starting) return;
    if (!api.auth()) { this.setData({ready:true}); this.setView('login'); return; }
    this._starting = true; this.setData({loading:true});
    try {
      const me = await api.request('/auth/me');
      if (me.must_change_password) { this.setView('activate'); return; }
      await this.syncState();
      if (['login','activate'].includes(this.data.view)) this.setView('chat');
      await this.heartbeat();
      if (this.data.view==='pdf' && this.data.pdf) await this.loadPdfPage(this.data.pdf.page);
    } catch (error) { this.handleError(error); }
    finally { this._starting=false; this.setData({ready:true,loading:false}); }
  },
  async heartbeat() {
    if (!this.data.identity || !this._active) return;
    const status = await this.rpc('/mini/presence',{client_id:this._client});
    this.setData({questionStatus:status});
  },
  async poll() {
    if (!this._active || this.data.busy || this._starting || !this.data.identity) return;
    try {
      await this.heartbeat();
      await this.syncState();
    } catch (error) { this.handleError(error); }
  },
  async syncState() {
    if (this._syncing) return this._syncing;
    this._syncing = this.rpc('/mini/state').then(state => {
      const reports = present.reports(state.reports,state.exams);
      this._sessions=state.sessions;
      const sessions = state.sessions.map(row=>({id:row.id,title:row.title,updatedAt:row.updatedAt,
        questionCount:row.messages.filter(m=>m.role==='user').length}));
      const session = state.sessions.find(s=>s.id===this.data.activeSession);
      const ticket = state.tickets.find(t=>t.id===this.data.activeTicket);
      const exams = [{id:'',name:'全部已授权考试'}].concat(state.exams.filter(e=>reports.some(r=>r.examId===e.id)).map(e=>({id:e.id,name:e.name})));
      const subjectOptions = [{id:'',name:'全部科目'}];
      state.exams.forEach(e=>e.subjects.forEach(s=>{
        if (reports.some(r=>r.subjects.includes(s.k)) && !subjectOptions.some(o=>o.id===s.k)) subjectOptions.push({id:s.k,name:s.n});
      }));
      const tickets=state.tickets.map(t=>({id:t.id,question:t.question.slice(0,60),status:t.status,
        updatedAt:t.updatedAt,currentAllowed:t.currentAllowed,unread:t.unread}));
      this.setData({identity:state.identity,exams:state.exams,reports,sessions,tickets,
        audit:state.audit,questionStatus:state.questionStatus,notice:'',offline:false,
        messages:this.presentMessages(session ? session.messages:[],state.exams,reports),sessionTitle:session ? session.title:'',
        ticket:this.data.view==='ticketCompose' ? this.data.ticket : ticket ? this.ticketView(ticket):null, examOptions:exams, subjectOptions,
        unreadCount:state.tickets.filter(t=>t.unread).length,
        prompts:state.identity.role==='student'?['我这次考试各科成绩怎么样？','帮我对比期中和月考成绩']:['我可以查询哪些考试数据？','查看已授权的学情诊断报告']});
      this.filterReports();
      if(this.data.pdf && !reports.some(r=>r.id===this.data.pdf.id && r.version===this.data.pdf.version)){
        this._pdfSequence=(this._pdfSequence||0)+1;
        this.removeFile(this.data.pdfImage);
        this.setData({pdfImage:'',pdfLoading:false,pdfError:'报告不存在、版本已变化或当前无权查看。'});
      }
      return state;
    }).finally(()=>{this._syncing=null;});
    return this._syncing;
  },
  ticketView(ticket) {
    const pair=ticket.feedbackMessageId && ticket.currentAllowed ? ticket.context || []:[];
    return Object.assign({},ticket,{
      feedbackQuestion:(pair.find(m=>m.role==='user')||{}).text || '',
      feedbackAnswer:((pair.find(m=>m.role==='assistant')||{}).text || '').slice(0,140),
      events:ticket.events.map(e=>Object.assign({},e,{label:e.role==='operator'?'运营管理员':e.role==='system'?'办理状态':'我'}))
    });
  },
  presentMessages(rows, exams, reports) {
    const expanded = new Set(this.data.messages.filter(row=>row.sourcesExpanded).map(row=>row.id));
    return present.messages(rows,exams,reports).map(row=>Object.assign({},row,{sourcesExpanded:expanded.has(row.id)}));
  },
  toggleSources(event) {
    const id=event.currentTarget.dataset.message;
    const index=this.data.messages.findIndex(row=>row.id===id);
    if(index<0 || !this.data.messages[index].sources.length)return;
    this.setData({['messages['+index+'].sourcesExpanded']:!this.data.messages[index].sourcesExpanded});
  },
  setView(view) {
    if (!TITLES[view]) return;
    const tabViews=['chat','tools','reports','history','tickets','me','scope'];
    this.setData({view,source:null,canBack:['reports','history','ticket','ticketCompose','pdf','scope','audit'].includes(view),
      showTabs:!!this.data.identity && tabViews.includes(view),scrollTo:''});
    wx.setNavigationBarTitle({title:TITLES[view]});
  },
  input(event) {
    const field=event.currentTarget.dataset.field;
    if (['account','password','oldPassword','newPassword','repeatPassword','chatDraft','ticketQuestion'].includes(field)) {
      this.setData({[field]:detailValue(event)});
    }
  },
  async login(event) {
    if (this.data.busy) return;
    const selected=event && event.currentTarget.dataset.identity;
    if (!this.data.account.trim() || !this.data.password) { this.toast('请填写账号和密码'); return; }
    this.setData({busy:true,notice:''});
    try {
      const body={username:this.data.account.trim(),password:this.data.password};
      if (selected) body.identity_id=selected;
      const user=await api.login(body);
      this.setData(Object.assign({},EMPTY,{identities:[],activeSession:null,activeTicket:null,messages:[],ticket:null,
        password:'',chatDraft:'',canRetry:false,ticketQuestion:'',filteredReports:[],notice:''}));
      this._askDraft=null;this._ticketDraft=null;
      if (user.must_change_password) { this.setView('activate'); return; }
      await this.syncState();this.setView('chat');await this.heartbeat();
    } catch (error) {
      if (error.code==='LOGIN_IDENTITY_REQUIRED') this.setData({identities:error.details.identities || []});
      else this.handleError(error);
    } finally { this.setData({busy:false,ready:true}); }
  },
  async activate() {
    if (this.data.busy) return;
    if (this.data.newPassword!==this.data.repeatPassword) {this.toast('两次新密码不一致');return;}
    if (this.data.newPassword.length<8 || this.data.newPassword===this.data.account) {this.toast('新密码至少8位，且不同于账号');return;}
    this.setData({busy:true,notice:''});
    try {
      await api.changePassword(this.data.oldPassword,this.data.newPassword);
      this.setData({oldPassword:'',newPassword:'',repeatPassword:''});
      await this.syncState();this.setView('chat');await this.heartbeat();
    } catch (error) {this.handleError(error);}
    finally {this.setData({busy:false});}
  },
  async logout() {
    if (this.data.busy) return;
    this.setData({busy:true});
    let failure;
    try {
      if (this.data.identity) await this.rpc('/mini/presence',{client_id:this._client,present:false});
    } catch (_) { /* The server lease also expires automatically. */ }
    try {await api.logout();} catch (error) {failure=error;}
    finally {
      this.clearFiles();this._askDraft=null;this._ticketDraft=null;this._sessions=[];
      this.setData(Object.assign({},EMPTY,{account:'',password:'',oldPassword:'',newPassword:'',repeatPassword:'',
        identities:[],busy:false,activeSession:null,activeTicket:null,messages:[],ticket:null,pdf:null,pdfImage:'',
        chatDraft:'',canRetry:false,ticketQuestion:'',ticketContext:[],selectedContext:[],feedback:null,source:null,filteredReports:[],
        unreadCount:0,notice:failure?'已退出本机；网络异常，服务端登录撤销未确认。':''}));
      this.setView('login');
    }
  },
  async go(event) {
    const target=event.currentTarget.dataset.view;
    if (this.data.busy || target===this.data.view) return;
    try {await this.syncState();this.setView(target);}
    catch (error) {this.handleError(error,'读取最新数据失败：');}
  },
  back() {
    if (this.data.busy) return;
    const view=this.data.view;
    if (view==='pdf') {this.setData({pdfImage:'',pdf:null,pdfError:''});this.setView(this._pdfReturn||'reports');}
    else if (view==='ticketCompose') this.setView(this.data.ticketReturn);
    else if (view==='ticket') this.setView('tickets');
    else if (view==='audit'||view==='scope') this.setView('me');
    else this.setView('tools');
  },
  newChat() {
    if (this.data.busy) return;
    this._askDraft=null;this.setData({activeSession:null,messages:[],chatDraft:'',canRetry:false,sessionTitle:''});this.setView('chat');
  },
  async openSession(event) {
    if (this.data.busy) return;
    const id=event.currentTarget.dataset.id;
    try {
      this.setData({activeSession:id,messages:[]});await this.syncState();this.setView('chat');this.scrollBottom();
    } catch (error) {this.handleError(error);}
  },
  scrollBottom() {this.setData({scrollTo:''});this.setData({scrollTo:'conversation-end'});},
  async ask(event) {
    if (this.data.busy) return;
    const suggested=event && event.currentTarget && event.currentTarget.dataset.question;
    const question=(suggested || this.data.chatDraft).trim();
    if (!question) return;
    if (question.length>1500) {this.toast('请将问题控制在1500字以内');return;}
    const session=this.data.activeSession;
    if (!this._askDraft || this._askDraft.question!==question || this._askDraft.session_id!==session) {
      this._askDraft={question,session_id:session,key:api.uuid()};
    }
    // A response may have been lost after the 100th charge. Keep the same key to read it back.
    this.setData({busy:true,chatDraft:question,notice:''});
    let completed=false;
    try {
      const draft=this._askDraft;
      const response=await this.rpc('/mini/ask',{question:draft.question,session_id:draft.session_id},{key:draft.key});
      this._askDraft=null;completed=true;
      this.setData({activeSession:response.id,chatDraft:'',canRetry:false,questionStatus:response.questionStatus,
        messages:this.presentMessages(response.messages,this.data.exams,this.data.reports),sessionTitle:response.title});
      this.setView('chat');this.scrollBottom();
      try {await this.syncState();} catch (error) {this.setData({notice:'回答已保存，其他数据暂未刷新。可下拉重试。'});}
    } catch (error) {
      this.setData({canRetry:!!this._askDraft && error.code!=='DAILY_QUESTION_LIMIT'});
      if (error.details && error.details.quota) this.setData({'questionStatus.quota':error.details.quota});
      this.handleError(error,'本次提问未完成，问题已保留：');
    } finally {
      this.setData({busy:false});
      if (completed) this.scrollBottom();
    }
  },
  filterReports() {
    const f=this.data.reportFilters;
    const filtered=this.data.reports.filter(r=>(!f.category||r.category===f.category)&&(!f.exam||r.examId===f.exam)&&
      (!f.subject||r.subjects.includes(f.subject))&&(!f.query||[r.label,r.examName,r.target,r.subjectLabel,r.reportCode].join(' ').includes(f.query.trim())));
    this.setData({filteredReports:filtered,
      examIndex:Math.max(0,this.data.examOptions.findIndex(e=>e.id===f.exam)),
      subjectIndex:Math.max(0,this.data.subjectOptions.findIndex(e=>e.id===f.subject))});
  },
  reportSearch(event) {this.setData({'reportFilters.query':detailValue(event)});this.filterReports();},
  reportCategory(event) {this.setData({'reportFilters.category':event.currentTarget.dataset.category});this.filterReports();},
  reportExam(event) {this.setData({'reportFilters.exam':this.data.examOptions[Number(detailValue(event))].id});this.filterReports();},
  reportSubject(event) {this.setData({'reportFilters.subject':this.data.subjectOptions[Number(detailValue(event))].id});this.filterReports();},
  rememberFile(path) {this._files.push(path);return path;},
  removeFile(path) {if(!path)return;wx.getFileSystemManager().unlink({filePath:path,fail:()=>{}});this._files=this._files.filter(p=>p!==path);},
  clearFiles() {(this._files||[]).forEach(path=>{try{wx.getFileSystemManager().unlinkSync(path);}catch(_){}});this._files=[];},
  async openReport(event) {
    const id=event.currentTarget.dataset.id;
    try {
      await this.syncState();
      const report=this.data.reports.find(r=>r.id===id);
      if(!report)throw new Error('报告已删除或当前无权查看');
      this._pdfReturn=this.data.view==='chat'?'chat':'reports';
      this.setData({pdf:Object.assign({},report,{page:1}),pdfImage:'',pdfError:''});
      this.setView('pdf');await this.loadPdfPage(1);
    } catch(error){this.handleError(error);}
  },
  async loadPdfPage(page) {
    const pdf=this.data.pdf;
    if(!pdf || page<1 || page>pdf.pages)return;
    const sequence=(this._pdfSequence||0)+1;this._pdfSequence=sequence;
    this.removeFile(this.data.pdfImage);this.setData({pdfLoading:true,pdfImage:'',pdfError:'','pdf.page':page});
    try {
      const path=await api.file(ROOT+'/reports/'+pdf.id+'/file?version='+pdf.version+'&page='+page);
      if(this.data.view!=='pdf' || this._pdfSequence!==sequence){this.rememberFile(path);this.removeFile(path);return;}
      this.setData({pdfImage:this.rememberFile(path)});
    } catch(error){if(this._pdfSequence===sequence){this.setData({pdfError:error.message,pdfImage:''});this.handleError(error);}}
    finally{if(this._pdfSequence===sequence)this.setData({pdfLoading:false});}
  },
  pdfStep(event){if(!this.data.pdfLoading && this.data.pdf)this.loadPdfPage(this.data.pdf.page+Number(event.currentTarget.dataset.step));},
  retryPdf(){if(this.data.pdf)this.loadPdfPage(this.data.pdf.page);},
  async downloadReport(event) {
    if(this.data.busy)return;
    const id=event.currentTarget.dataset.id;
    this.setData({busy:true,notice:''});
    try {
      await this.syncState();const report=this.data.reports.find(r=>r.id===id);
      if(!report)throw new Error('当前报告已不可访问');
      const path=this.rememberFile(await api.file(ROOT+'/reports/'+id+'/file?version='+report.version+'&download=true'));
      await new Promise((resolve,reject)=>wx.openDocument({filePath:path,fileType:'pdf',showMenu:true,success:resolve,
        fail:()=>reject(new Error('PDF已下载，但系统阅读器未能打开，请重试。'))}));
      this.toast('已打开当前 PDF，可在右上角保存');
    }catch(error){this.handleError(error);}
    finally{this.setData({busy:false});}
  },
  async openSource(event) {
    try {
      const ref=event.currentTarget.dataset.ref;
      const rows=await this.rpc('/sources/inspect',{sources:[ref]});
      const item=rows[0];if(!item || !item.allowed)throw new Error('来源权限已失效或文件版本已变化');
      if(ref.kind==='report'){await this.openReport({currentTarget:{dataset:{id:ref.reportId}}});return;}
      this.setData({source:item});
    }catch(error){this.handleError(error);await this.syncState().catch(()=>{});}
  },
  closeSource(){this.setData({source:null});},
  noop(){},
  composeTicket(event) {
    if(this.data.busy)return;
    const messageId=event && event.currentTarget.dataset.message;
    const feedback=event && event.currentTarget.dataset.feedback;
    const rows=this.data.messages;
    const index=messageId?rows.findIndex(m=>m.id===messageId && m.role==='assistant'):-1;
    const answer=index>=1?rows[index]:null, question=index>=1?rows[index-1]:null;
    if(messageId && (!answer || answer.restricted)){this.toast('当前回答已不可用于反馈，请重新核对权限');return;}
    const context=(feedback?rows.slice(index-1,index+1):rows.slice(-6)).filter(m=>!m.restricted);
    this._ticketDraft={key:api.uuid(),session_id:this.data.activeSession,feedback_message_id:feedback?messageId:null};
    this.setData({activeTicket:null,ticket:null,ticketReturn:messageId?'chat':'tickets',ticketQuestion:feedback?'':question?question.text:'',
      ticketContext:context,selectedContext:[],feedback:feedback?{question:question.text,answer:answer.text.slice(0,140)}:null});
    this.setView('ticketCompose');
  },
  selectContext(event){this.setData({selectedContext:detailValue(event)});},
  async submitTicket() {
    if(this.data.busy || !this._ticketDraft)return;
    const question=this.data.ticketQuestion.trim();if(!question){this.toast('请先填写问题');return;}
    const draft=this._ticketDraft;
    const body={question,session_id:draft.session_id,message_ids:this.data.selectedContext};
    let path='/tickets';
    if(this.data.activeTicket){path+='/'+this.data.activeTicket+'/append';body.expected=this.data.ticket.revision;}
    else body.feedback_message_id=draft.feedback_message_id || null;
    const signature=JSON.stringify(body);
    if(draft.signature && draft.signature!==signature)draft.key=api.uuid();
    draft.signature=signature;
    this.setData({busy:true,notice:''});
    let saved=false;
    try {
      const ticket=await this.rpc(path,body,{key:draft.key});saved=true;
      this._ticketDraft=null;
      this.setData({activeTicket:ticket.id,ticket:this.ticketView(ticket),ticketQuestion:'',selectedContext:[],feedback:null});
      this.setView('ticket');this.toast('留言已提交，后续可回来查看回复');
      await this.syncState();
    }catch(error){this.handleError(error,saved?'留言已保存，列表刷新失败：':'留言未提交，编辑内容保留：');}
    finally{this.setData({busy:false});}
  },
  async openTicket(event) {
    if(this.data.busy)return;
    const id=event.currentTarget.dataset.id;
    this.setData({busy:true});
    try {
      let ticket=await this.rpc('/tickets/'+id);
      if(ticket.unread)ticket=await this.rpc('/tickets/'+id+'/read',{expected:ticket.revision},{key:api.uuid()});
      this.setData({activeTicket:id,ticket:this.ticketView(ticket)});this.setView('ticket');await this.syncState();
    }catch(error){this.handleError(error);}
    finally{this.setData({busy:false});}
  },
  appendTicket() {
    const ticket=this.data.ticket;if(!ticket || ticket.status!=='已回复' || this.data.busy)return;
    const session=(this._sessions||[]).find(s=>s.id===ticket.sessionId);
    this._ticketDraft={key:api.uuid(),session_id:ticket.sessionId};
    this.setData({ticketReturn:'ticket',ticketQuestion:'',selectedContext:[],feedback:null,
      ticketContext:session?session.messages.slice(-6).filter(m=>!m.restricted):[]});
    this.setView('ticketCompose');
  },
  async closeTicket() {
    const ticket=this.data.ticket;if(!ticket || ticket.status!=='已回复' || this.data.busy)return;
    const result=await new Promise(resolve=>wx.showModal({title:'确认结束办理',content:'确认问题已解决后，这条留言将结束办理。',confirmText:'确认结束',success:resolve,fail:()=>resolve({confirm:false})}));
    if(!result.confirm)return;
    this.setData({busy:true});
    try {
      const value=await this.rpc('/tickets/'+ticket.id+'/close',{expected:ticket.revision},{key:api.uuid()});
      this.setData({ticket:this.ticketView(value)});await this.syncState();
    }catch(error){this.handleError(error);}
    finally{this.setData({busy:false});}
  }
});

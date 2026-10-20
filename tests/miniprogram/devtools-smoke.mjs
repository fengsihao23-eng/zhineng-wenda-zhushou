/** Actual WeChat devtools rendering/binding gate. Needs an unlocked Mac and enabled service port. */
import automator from 'miniprogram-automator'
import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const session=process.env.QA_WECHAT_OUTPUT || path.join(root,'.local/wechat-mini/session')
const fixture=JSON.parse(await readFile(path.join(session,'fixtures.json'),'utf8'))
const output=path.join(session,'devtools');await mkdir(output,{recursive:true})
const apiBase='http://127.0.0.1:8048/api/v1'
async function api(endpoint,body,token){
  const response=await fetch(apiBase+endpoint,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),'Idempotency-Key':randomUUID()},body:body===undefined?undefined:JSON.stringify(body)})
  const bytes=Buffer.from(await response.arrayBuffer())
  assert.ok(response.ok,endpoint+': '+response.status)
  return {value:response.headers.get('content-type')?.includes('json')?JSON.parse(bytes.toString()):bytes,headers:response.headers}
}
assert.equal((await api('/health')).value.environment,'test','Native acceptance must use the isolated test service')
const admin=(await api('/auth/login',{username:fixture.users.admin,password:fixture.password})).value.access_token
const A='/answer-workbench',E='/platform/education/exam-management',R='/platform/education/report-management'
const available=(await api(R+'?page_size=100',undefined,admin)).value.items
const report=available.find(r=>r.report_type==='student' && r.target_key===fixture.students[0].id)
assert.ok(report,'Prepare the isolated Page/API report fixture before the native GUI gate')
let exam=(await api(E+'/'+report.exam_id,undefined,admin)).value
async function permission(mode){
  const body={expected_revision:exam.revision,student_ids:[fixture.students[0].id],subject_ids:report.subject_ids,mode}
  const preview=await api(E+'/'+exam.id+'/permissions/student/preview',body,admin)
  exam=(await api(E+'/'+exam.id+'/permissions/student',{...body,preview_hash:preview.headers.get('x-exam-preview-hash')},admin)).value
}
await permission('open')
const mini=process.env.QA_WECHAT_WS ? await automator.connect({wsEndpoint:process.env.QA_WECHAT_WS}) : await automator.launch({
  projectPath:path.join(root,'apps/miniprogram'),cliPath:process.env.WECHAT_CLI || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',trustProject:true,timeout:30000
})
const errors=[];mini.on('exception',error=>errors.push(error))
async function capture(name){
  await mini.evaluate(()=>{wx.hideToast();return true})
  await mini.screenshot({path:path.join(output,name)})
  console.log('Captured '+name)
}
async function ready(page,condition){
  const deadline=Date.now()+25000
  while(!(typeof condition==='string' ? await page.$(condition) : await condition())){
    if(Date.now()>deadline)throw new Error('等待原生界面超时：'+(typeof condition==='string'?condition:'页面状态'))
    await new Promise(resolve=>setTimeout(resolve,200))
  }
}
try{
  const existing=await mini.currentPage()
  if(existing){
    await ready(existing,async()=>!await existing.data('busy'))
    await existing.callMethod('logout')
  }
  await mini.callWxMethod('removeStorageSync','subject-assistant.auth.v1')
  const page=await mini.reLaunch('/pages/workbench/index')
  await ready(page,'#account')
  await capture('01-login.png')
  await (await page.$('#account')).input(fixture.users.teacher2)
  await (await page.$('#password')).input(fixture.password)
  await (await page.$('#login')).tap()
  await ready(page,async()=>await page.data('view')==='chat' && !await page.data('busy'))
  await ready(page,'.home-welcome')
  assert.equal(await page.data('identity.role'),'teacher')
  assert.ok(Number((await (await page.$('#sendQuestion')).size()).width)<80,'Native send button must not inherit the v2 wide-button default')
  const promptWidth=Number((await (await page.$('.suggestion')).size()).width)
  const contentWidth=Number((await (await page.$('.home-prompts')).size()).width)
  assert.ok(promptWidth>contentWidth*.8,'Suggestion cards should span the phone content')
  await capture('02-chat-home.png')
  const before=await page.data('questionStatus.quota.used')
  await (await page.$('#question')).input('你好')
  await (await page.$('#sendQuestion')).tap()
  await ready(page,async()=>await page.data('messages.length')===2 && !await page.data('busy'))
  await ready(page,'.messages')
  assert.equal(await page.data('questionStatus.quota.used'),before+1)
  assert.ok((await (await page.$('.messages')).text()).includes('你好，可以直接描述'))
  await capture('03-answer.png')
  await (await page.$('.tab-item[data-view="tools"]')).tap();await ready(page,async()=>await page.data('view')==='tools')
  await capture('04-tools.png')
  await (await page.$('.tool-card[data-view="history"]')).tap();await ready(page,async()=>await page.data('view')==='history')
  assert.ok((await (await page.$('.screen')).text()).includes('你好'))
  await (await page.$('.tab-item[data-view="tickets"]')).tap();await ready(page,'#newTicket')
  await (await page.$('#newTicket')).tap();await ready(page,'#ticketQuestion')
  await (await page.$('#ticketQuestion')).input('开发者工具原生界面实际提交验收')
  await (await page.$('#submitTicket')).tap();await ready(page,async()=>await page.data('view')==='ticket' && !await page.data('busy'))
  assert.equal(await page.data('ticket.status'),'待处理')
  await capture('05-ticket.png')
  const ticketId=await page.data('ticket.id')
  async function reply(text){
    const current=(await api(A+'/tickets/'+ticketId+'?management=true',undefined,admin)).value
    const claimed=(await api(A+'/tickets/'+ticketId+'/claim',{expected:current.revision},admin)).value
    await api(A+'/tickets/'+ticketId+'/reply',{expected:claimed.revision,text,reply_kind:'routing',reviewed:true},admin)
  }
  await reply('已收到开发者工具验收留言，请在报告中心核对当前考试资料。')
  await page.callMethod('syncState');await ready(page,'#appendTicket')
  assert.equal(await page.data('ticket.status'),'已回复')
  await capture('06-admin-reply.png')
  await (await page.$('#appendTicket')).tap();await ready(page,'#ticketQuestion')
  await (await page.$('#ticketQuestion')).input('补充确认处理状态可同步返回')
  await (await page.$('#submitTicket')).tap();await ready(page,async()=>await page.data('view')==='ticket' && !await page.data('busy'))
  assert.equal(await page.data('ticket.status'),'待处理')
  await reply('补充内容已处理，可在小程序确认结束办理。');await page.callMethod('syncState');await ready(page,'#closeTicket')
  await mini.mockWxMethod('showModal',{confirm:true,cancel:false})
  await (await page.$('#closeTicket')).tap();await ready(page,async()=>await page.data('ticket.status')==='已关闭' && !await page.data('busy'))
  await mini.restoreWxMethod('showModal')
  await page.callMethod('logout');await ready(page,'#account')
  await (await page.$('#account')).input(fixture.users.student);await (await page.$('#password')).input(fixture.password);await (await page.$('#login')).tap()
  await ready(page,async()=>await page.data('view')==='chat' && !await page.data('busy'))
  assert.equal(await page.data('identity.role'),'student')
  assert.ok(!(await page.data('tickets')).some(t=>t.id===ticketId),'Teacher tickets must not appear under the student identity')
  await (await page.$('.tab-item[data-view="tools"]')).tap();await ready(page,async()=>await page.data('view')==='tools')
  await (await page.$('.tool-card[data-view="reports"]')).tap();await ready(page,async()=>await page.data('view')==='reports')
  await (await page.$('#reportSearch')).input(report.report_code)
  await ready(page,async()=>await page.data('filteredReports.length')===1)
  await (await page.$('.actions button')).tap()
  await ready(page,async()=>!!await page.data('pdfImage') && !await page.data('pdfLoading'))
  await ready(page,'.pdf-image');assert.equal(await page.data('pdf.pages'),2)
  await capture('07-report-page1.png')
  await (await page.$('.pdf-controls button[data-step="1"]')).tap()
  await ready(page,async()=>await page.data('pdf.page')===2 && !!await page.data('pdfImage') && !await page.data('pdfLoading'))
  await capture('08-report-page2.png')
  await (await page.$('.download-bar button')).tap()
  await ready(page,async()=>!await page.data('busy'))
  assert.equal(await page.data('busy'),false)
  const downloaded=await mini.evaluate(()=>{
    const pages=getCurrentPages(),page=pages[pages.length-1]
    return wx.getFileSystemManager().readFileSync(page._files[page._files.length-1],'base64')
  })
  const original=(await api(R+'/'+report.id+'/file',undefined,admin)).value
  assert.ok(Buffer.from(downloaded,'base64').equals(original),'The native file must match the actual current PDF')
  await permission('close');await page.callMethod('syncState')
  assert.equal(await page.data('pdfImage'),'');assert.ok(await page.data('pdfError'))
  await capture('09-report-revoked.png')
  await page.callMethod('back');await ready(page,'.tab-item[data-view="me"]');await (await page.$('.tab-item[data-view="me"]')).tap();await ready(page,async()=>await page.data('view')==='me')
  await capture('10-profile.png')
  assert.equal(errors.length,0)
  await writeFile(path.join(output,'result.json'),JSON.stringify({kind:'real-wechat-devtools',cases:['login','ask','quota','tools','history','ticket','admin-reply','append','close','account-isolation','report-filter','pdf-pages','pdf-download','revocation','profile'],errors},null,2))
  console.log('微信开发者工具原生渲染与交互验收通过。截图：'+output)
}finally{await mini.disconnect()}

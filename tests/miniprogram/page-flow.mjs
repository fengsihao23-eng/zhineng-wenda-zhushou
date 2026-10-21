/** Business acceptance using the actual shipped native Page + real API/PostgreSQL. */
import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { nativeRuntime } from './native-runtime.mjs'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const session=process.env.QA_WECHAT_OUTPUT || path.join(root,'.local/wechat-mini/session')
const fixture=JSON.parse(await readFile(path.join(session,'fixtures.json'),'utf8'))
const base='http://127.0.0.1:8048/api/v1'
const output=path.join(session,'native-runtime');await mkdir(output,{recursive:true})
const event=dataset=>({currentTarget:{dataset}})
const results=[]
async function record(name,run){await run();results.push(name);console.log('PASS '+name)}
async function request(endpoint,body,token,method){
  const response=await fetch(base+endpoint,{method:method || (body===undefined?'GET':'POST'),headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),'Idempotency-Key':randomUUID()},body:body===undefined?undefined:JSON.stringify(body)})
  const bytes=Buffer.from(await response.arrayBuffer())
  const value=response.headers.get('content-type')?.includes('json') ? JSON.parse(bytes.toString()) : bytes
  assert.ok(response.ok,endpoint+': '+response.status+' '+(Buffer.isBuffer(value)?'binary response':JSON.stringify(value)))
  return {value,headers:response.headers}
}
const admin=(await request('/auth/login',{username:fixture.users.admin,password:fixture.password})).value.access_token
const student=(await request('/auth/login',{username:fixture.users.student,password:fixture.password})).value.access_token
const A='/answer-workbench',E='/platform/education/exam-management',R='/platform/education/report-management'
await request(A+'/admin/state',undefined,admin)
// Build one exam and import an actual XLSX through the same admin endpoints as web.
const draft={name:'原生微信联调-'+randomUUID().slice(0,6),academic_year:'2026-2027',exam_date:'2026-10-20',subjects:[{key:'math',name:'数学',full_score:150,student_ids:fixture.students.slice(0,2).map(s=>s.id)}]}
const checked=(await request(E+'/preview',draft,admin)).value
let exam=(await request(E,{...draft,preview_hash:checked.preview_hash},admin)).value
const subject=exam.subjects[0].subject_id
const template=await fetch(base+E+'/'+exam.id+'/score-template/'+subject,{headers:{Authorization:'Bearer '+admin}})
const xlsx=execFileSync(path.join(root,'.venv/bin/python'),['-c',`import io,sys
from openpyxl import load_workbook
b=load_workbook(io.BytesIO(sys.stdin.buffer.read()));s=b.active
for i in range(2,s.max_row+1):s.cell(i,7,91)
o=io.BytesIO();b.save(o);sys.stdout.buffer.write(o.getvalue())`],{input:Buffer.from(await template.arrayBuffer())})
const score=(await request(E+'/'+exam.id+'/score-files',{expected_revision:exam.revision,subject_id:subject,filename:'合成数学成绩.xlsx',content_base64:xlsx.toString('base64')},admin)).value
exam=(await request(E+'/'+exam.id+'/score-files/'+score.id+'/confirm',{},admin)).value
const permission={expected_revision:exam.revision,student_ids:[fixture.students[0].id],subject_ids:[subject],mode:'open'}
let preview=await request(E+'/'+exam.id+'/permissions/student/preview',permission,admin)
exam=(await request(E+'/'+exam.id+'/permissions/student',{...permission,preview_hash:preview.headers.get('x-exam-preview-hash')},admin)).value
const scope=(await request(R+'/exams/'+exam.id,undefined,admin)).value
const sid=fixture.students[0].id,person=scope.snapshots[sid],sub=scope.subjects.find(s=>s.subject_id===subject)
function pdfFixture(){
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>']
  for(const [number,text]of [[4,'VERIFIED MATH REPORT: score 91. Review algebra.'],[6,'VERIFIED REPORT PAGE TWO: practice equations.']]){
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 7 0 R >> >> /Contents ${number} 0 R >>`)
    const stream=`BT /F1 14 Tf 50 780 Td (${text}) Tj ET`;objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`)
  }
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
  let body='%PDF-1.4\n';const offsets=[]
  objects.forEach((object,index)=>{offsets.push(Buffer.byteLength(body));body+=`${index+1} 0 obj\n${object}\nendobj\n`})
  const offset=Buffer.byteLength(body)
  body+='xref\n0 8\n0000000000 65535 f \n'+offsets.map(n=>n.toString().padStart(10,'0')+' 00000 n \n').join('')+`trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n${offset}\n%%EOF`
  return Buffer.from(body)
}
const pdf=pdfFixture()
const row={category:'diagnostic',report_type:'student',subject_ids:[subject],target_key:sid,previewed:true,naming:{category:'diagnostic',report_type:'student',subject_ids:[subject]},file:{filename:[scope.exam_code,person.platform_id,person.name,sub.name,'个人学情诊断'].join('_')+'.pdf',content_base64:pdf.toString('base64')}}
const batch={exam_id:exam.id,expected_exam_revision:exam.revision,reports:[row]}
preview=await request(R+'/batches/preview',batch,admin)
const report=(await request(R+'/batches',{...batch,preview_hash:preview.value.preview_hash},admin)).value.reports[0]

const runtime=await nativeRuntime(output),page=runtime.page
const login=async kind=>{page.setData({account:fixture.users[kind],password:fixture.password});await page.login(event({}));assert.equal(page.data.view,'chat')}
try{
  await record('原账号登录、身份和当前范围来自服务端',async()=>{await login('student');assert.equal(page.data.identity.role,'student');assert.ok(page.data.exams.some(e=>e.id===exam.id))})
  let chat
  await record('自然语言问答、分数表、报告引用与网页同库回读',async()=>{
    page.setData({chatDraft:'我在'+exam.name+'的数学成绩怎么样？'});await page.ask()
    assert.equal(page.data.messages.at(-1).table[0].score,91)
    assert.ok(page.data.messages.at(-1).sources.some(s=>s.kind==='report'))
    assert.equal(page.data.messages.at(-1).sourcesExpanded,false)
    chat=page.data.activeSession
    const web=(await request(A+'/mini/state',undefined,student)).value
    assert.equal(web.sessions.find(s=>s.id===chat).messages[0].text,'我在'+exam.name+'的数学成绩怎么样？')
    assert.equal(page.data.questionStatus.quota.remaining,web.questionStatus.quota.remaining)
  })
  await record('数据来源默认收起、点击展开及收起，刷新保留选择，重开会话恢复收起',async()=>{
    const answer=page.data.messages.at(-1)
    page.toggleSources(event({message:answer.id}));assert.equal(page.data.messages.at(-1).sourcesExpanded,true)
    await page.syncState();assert.equal(page.data.messages.at(-1).sourcesExpanded,true)
    page.toggleSources(event({message:answer.id}));assert.equal(page.data.messages.at(-1).sourcesExpanded,false)
    page.toggleSources(event({message:answer.id}))
    await page.openSession(event({id:chat}));assert.equal(page.data.messages.at(-1).sourcesExpanded,false)
    assert.ok(page.data.messages.at(-1).sources.length>1)
  })
  await record('网页提问后小程序刷新可继续同一会话',async()=>{
    await request(A+'/mini/ask',{question:'我可以查询哪些考试数据？',session_id:chat},student)
    await page.syncState();assert.equal(page.data.messages.at(-2).text,'我可以查询哪些考试数据？')
  })
  await record('访问令牌失效时自动刷新，并发请求只刷新一次',async()=>{
    const before=runtime.requests.filter(r=>r.path==='/api/v1/auth/refresh').length
    runtime.api.auth().access_token='synthetic-invalid-access'
    const values=await Promise.all([runtime.api.request(A+'/mini/status'),runtime.api.request(A+'/mini/status')])
    assert.ok(values.every(v=>v.quota.remaining>=0))
    assert.equal(runtime.requests.filter(r=>r.path==='/api/v1/auth/refresh').length,before+1)
  })
  await record('切换账号后丢弃旧账号延迟到达的响应',async()=>{
    const gate=runtime.holdNext('/answer-workbench/mini/status')
    const pending=runtime.api.request(A+'/mini/status')
    const checked=assert.rejects(pending,error=>error.code==='STALE_SESSION')
    await gate.entered;runtime.api.clearAuth()
    await runtime.api.login({username:fixture.users.teacher,password:fixture.password})
    gate.release();await checked
    await runtime.api.logout();await runtime.api.login({username:fixture.users.student,password:fixture.password})
    await page.syncState();assert.equal(page.data.identity.role,'student')
  })
  await record('成绩来源重新鉴权、报告筛选、双页预览与实际 PDF 下载',async()=>{
    const sources=(await request(A+'/mini/state',undefined,student)).value.sessions.find(s=>s.id===chat).messages[1].sources
    await page.openSource(event({ref:sources.find(s=>s.kind==='score')}));assert.equal(page.data.source.rows[0].score,91);page.closeSource()
    await page.go(event({view:'reports'}));page.reportSearch({detail:{value:exam.name}});assert.equal(page.data.filteredReports.length,1)
    await page.openReport(event({id:report.id}));assert.ok(page.data.pdfImage);assert.equal(page.data.pdf.pages,2)
    await page.loadPdfPage(2);assert.equal(page.data.pdf.page,2);assert.ok(page.data.pdfImage)
    await page.downloadReport(event({id:report.id}));assert.ok(runtime.opened[0].equals(pdf))
    page.back();await page.go(event({view:'chat'}))
  })
  let ticket
  await record('反馈绑定原问答，响应丢失后保留输入并只创建一条留言',async()=>{
    const answer=page.data.messages.find(m=>m.role==='assistant' && m.sources.length)
    page.composeTicket(event({message:answer.id,feedback:true}));assert.ok(page.data.feedback)
    page.setData({ticketQuestion:'请核对原生微信联调的分数来源 '+exam.name})
    runtime.dropNext('/answer-workbench/tickets');await page.submitTicket();assert.equal(page.data.view,'ticketCompose');assert.ok(page.data.ticketQuestion)
    await page.submitTicket();assert.equal(page.data.view,'ticket');ticket=page.data.ticket
    assert.equal(ticket.status,'待处理');assert.equal(ticket.context.length,2)
    const queue=(await request(A+'/tickets?management=true',undefined,admin)).value
    assert.equal(queue.filter(t=>t.question===ticket.question).length,1)
  })
  const reply=async(text)=>{
    const current=(await request(A+'/tickets/'+ticket.id+'?management=true',undefined,admin)).value
    const claim=(await request(A+'/tickets/'+ticket.id+'/claim',{expected:current.revision},admin)).value
    return (await request(A+'/tickets/'+ticket.id+'/reply',{expected:claim.revision,text,reply_kind:'routing',reviewed:true},admin)).value
  }
  await record('后台领取回复 → 小程序未读 → 查看 → 追加回到待处理',async()=>{
    await reply('请在学校考务管理核对授权与成绩来源。');await page.syncState();assert.ok(page.data.tickets.find(t=>t.id===ticket.id).unread)
    await page.openTicket(event({id:ticket.id}));assert.equal(page.data.ticket.status,'已回复');assert.equal(page.data.ticket.unread,false)
    page.appendTicket();page.setData({ticketQuestion:'还需要确认报告对应的考试'});await page.submitTicket();assert.equal(page.data.ticket.status,'待处理')
  })
  await record('再次回复 → 本人确认关闭 → 教师账号无法看到学生会话和留言',async()=>{
    await reply('可在报告中心按考试筛选并核对报告来源。');await page.syncState();await page.closeTicket();assert.equal(page.data.ticket.status,'已关闭')
    await page.logout();await login('teacher');assert.ok(!page.data.tickets.some(t=>t.id===ticket.id));assert.ok(!page.data.sessions.some(s=>s.id===chat));assert.equal(page.data.messages.length,0)
    await page.logout();await login('student');await page.openSession(event({id:chat}));assert.ok(page.data.messages.length)
  })
  await record('提问响应丢失后以同一标识重试，会话和额度只记一次',async()=>{
    const before=page.data.questionStatus.quota.used
    page.setData({chatDraft:'你好'});runtime.dropNext('/answer-workbench/mini/ask');await page.ask();assert.equal(page.data.chatDraft,'你好');assert.equal(page.data.canRetry,true)
    await page.ask();assert.equal(page.data.chatDraft,'');assert.equal(page.data.questionStatus.quota.used,before+1)
    const tries=runtime.requests.filter(r=>r.path.endsWith('/mini/ask')).slice(-2);assert.equal(tries[0].key,tries[1].key)
  })
  await record('每天100次由服务端拦截，额度用尽后仍可看报告和留言',async()=>{
    let state=(await request(A+'/mini/status',undefined,student)).value
    for(let i=0;i<state.quota.remaining;i++)await request(A+'/mini/ask',{question:'你好'},student)
    await page.syncState();assert.equal(page.data.questionStatus.quota.remaining,0)
    page.setData({chatDraft:'这次不应调用模型'});await page.ask();assert.equal(page.data.questionStatus.quota.remaining,0);assert.equal(page.data.chatDraft,'这次不应调用模型')
    await page.go(event({view:'reports'}));await page.openReport(event({id:report.id}));assert.ok(page.data.pdfImage);page.back()
    page.composeTicket(event({}));page.setData({ticketQuestion:'额度用尽后仍能提交的独立留言'});await page.submitTicket();assert.equal(page.data.ticket.status,'待处理')
  })
  await record('后台撤权后小程序报告、已打开页面、历史回答和反馈内容同步隐藏',async()=>{
    await page.openSession(event({id:chat}));await page.openReport(event({id:report.id}))
    const revoke={expected_revision:exam.revision,student_ids:[sid],subject_ids:[subject],mode:'close'}
    const checked=await request(E+'/'+exam.id+'/permissions/student/preview',revoke,admin)
    await request(E+'/'+exam.id+'/permissions/student',{...revoke,preview_hash:checked.headers.get('x-exam-preview-hash')},admin)
    await page.syncState();assert.equal(page.data.pdfImage,'');assert.ok(page.data.pdfError);assert.ok(page.data.messages.some(m=>m.restricted))
    await page.loadPdfPage(1);assert.equal(page.data.pdfImage,'');assert.ok(page.data.pdfError)
  })
  await record('退出登录清空身份、草稿、会话、留言和临时报告文件',async()=>{
    await page.logout();assert.equal(page.data.view,'login');assert.equal(page.data.identity,null);assert.equal(page.data.messages.length,0)
    assert.equal(page.data.ticketQuestion,'');assert.equal(page.data.pdfImage,'');assert.equal(page._files.length,0);assert.equal(runtime.storage.size,0)
  })
  await record('刷新凭据失效后清空历史内容并返回登录',async()=>{
    await login('teacher')
    runtime.api.auth().access_token='synthetic-invalid-access';runtime.api.auth().refresh_token='synthetic-invalid-refresh'
    await page.poll();assert.equal(page.data.view,'login');assert.equal(page.data.identity,null);assert.equal(page.data.messages.length,0)
  })
  await writeFile(path.join(output,'result.json'),JSON.stringify({kind:'native-page-real-api',notGui:true,cases:results},null,2))
  console.log(`${results.length} native Page/API acceptance cases passed.`)
}finally{runtime.close()}

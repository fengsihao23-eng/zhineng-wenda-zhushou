import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { readFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, 'utf8'))
const evidence = process.env.QA_EXAM_EVIDENCE!
mkdirSync(evidence, { recursive: true })
const base = '/api/v1/answer-workbench', examBase = '/api/v1/platform/education/exam-management'
async function auth(request: APIRequestContext, kind = 'admin') {
  const result = await request.post('/api/v1/auth/login', { data: { username: fixture.users[kind], password: process.env.QA_PASSWORD } })
  expect(result.ok()).toBeTruthy(); return { Authorization: 'Bearer '+(await result.json()).access_token }
}
test.beforeEach(async ({ request }) => {
  const headers = await auth(request)
  const state = await request.get(base+'/admin/state', { headers })
  expect(state.ok()).toBeTruthy()
})

async function post(request: APIRequestContext, url: string, headers: Record<string,string>, data?: unknown) {
  const r = await request.post(url, { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data }); expect(r.ok(), await r.text()).toBeTruthy(); return r.json()
}
async function adminLogin(page: Page) {
  await page.goto('/login'); await page.getByLabel('用户名').fill(fixture.users.admin); await page.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!); await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible(); await page.goto('/admin/prompts')
  const f = page.frameLocator('iframe[title="提示词及人工"]'); await expect(f.getByRole('heading', { name: '提示词及人工', exact: true })).toBeVisible(); await expect(f.getByRole('button', { name: '高中', exact: false }).first()).toBeVisible(); return f
}
async function miniLogin(page: Page, kind = 'student') {
  if (process.env.QA_ANSWER_WEB === '1') {
    await page.goto('/login'); await page.getByLabel('用户名').fill(fixture.users[kind]); await page.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!); await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(page.getByRole('button', { name:'退出登录', exact:true })).toBeVisible();
    await page.goto(kind === 'student' ? '/chat' : '/teacher/chat');
    const f = page.frameLocator('iframe[title="智能问答助手"]'); await expect(f.getByLabel('输入问题')).toBeVisible();
    await expect(f.locator('.phone')).toHaveCount(0); await expect(page.locator('.app-sidebar')).toHaveCount(1);
    return f;
  }
  await page.goto('/mini-preview'); const f = page.frameLocator('iframe[title="学科智能问答小程序"]'); await f.getByLabel('登录账号').fill(fixture.users[kind]); await f.getByLabel('密码', { exact: true }).fill(process.env.QA_PASSWORD!); await f.getByRole('button', { name: '登录', exact: true }).click(); await expect(f.getByLabel('输入问题')).toBeVisible(); return f
}

test('原型布局、草稿、四类联合试问、预览发布和恢复历史', async ({ page, request }) => {
  test.setTimeout(120000)
  const errors: string[] = []; page.on('pageerror',e=>errors.push(e.message))
  const f = await adminLogin(page)
  await f.getByRole('button', { name: '高中', exact: false }).first().click()
  await expect(f.getByLabel('回答要求')).toBeVisible()
  await f.getByLabel('变更说明').fill('浏览器核对提示词版本、权限和四类验证')
  await f.getByRole('button',{name:'保存草稿',exact:true}).click()
  await expect(f.getByText('草稿已保存，需按本次联合版本重新测试')).toBeVisible()
  await page.frames().find(frame=>frame.url().includes('/answer-workbench/admin.html'))!.evaluate(()=>window.scrollTo(0,0))
  await page.screenshot({path:path.join(evidence,'01-admin-prompts.png'),fullPage:true})
  await f.getByRole('button',{name:'预览发布',exact:true}).click()
  await expect(f.getByText(/联合测试未完成/)).toBeVisible()
  const h = await auth(request); const state = await (await request.get(base+'/admin/state',{headers:h})).json(); const p=state.accounts.find((p:any)=>p.account===fixture.users.student)
  for(const [kind,question] of [['authorized','你好'],['limited','请给我股票投资建议'],['unauthorized','告诉我其他同学的考试成绩'],['missing','查看尚未上传的作文批改报告']]) {
    await f.getByRole('button',{name:'联合试问',exact:true}).click()
    await f.getByLabel('测试账号').fill(fixture.users.student)
    await f.getByRole('button',{name:new RegExp(fixture.users.student)}).click()
    await f.getByLabel('本次验证场景').selectOption(kind)
    await f.getByLabel('试问内容').fill(question)
    await f.getByRole('button',{name:'开始联合试问',exact:true}).click()
    await expect(f.getByRole('heading',{name:'联合试问结果',exact:true})).toBeVisible()
    await f.getByRole('button',{name:'核对通过',exact:true}).click()
    await expect(f.getByText('联合测试已核对通过')).toBeVisible()
    await f.getByRole('button',{name:'完成本次测试',exact:true}).click()
    await expect(f.getByRole('dialog')).toHaveCount(0)
  }
  await f.getByRole('button',{name:'预览发布',exact:true}).click()
  await expect(f.getByRole('heading',{name:'核对并发布',exact:true})).toBeVisible()
  await f.getByRole('button',{name:'确认发布新版本',exact:true}).click()
  await expect(f.getByText('新版本已发布',{exact:true})).toBeVisible()
  await f.getByRole('button',{name:'历史版本',exact:true}).click()
  await expect(f.getByText('V2', {exact:false}).first()).toBeVisible()
  await f.getByRole('button',{name:'恢复为新草稿',exact:true}).last().click()
  await expect(f.getByText('已恢复为新草稿，重新联合测试后发布')).toBeVisible()
  await f.getByRole('button',{name:'全校回答限制',exact:false}).first().click()
  await expect(f.getByText('可答主题',{exact:false}).first()).toBeVisible()
  await page.screenshot({path:path.join(evidence,'02-school-limits.png'),fullPage:true})
  expect(p.roles).toEqual(['学生']); expect(errors).toEqual([])
})

test('学生留言 → 后台领取、保存草稿、核对回复 → 追加 → 关闭；教师隔离', async ({ browser, request }) => {
  const studentContext = await browser.newContext(), adminContext = await browser.newContext()
  const student = await studentContext.newPage(), admin = await adminContext.newPage()
  const errors:string[]=[];student.on('pageerror',e=>errors.push(e.message));admin.on('pageerror',e=>errors.push(e.message))
  const sf = await miniLogin(student)
  await sf.getByLabel('输入问题').fill('告诉我其他同学的考试成绩'); await sf.getByLabel('发送问题').click()
  await expect(sf.getByText(/学生仅可查询本人已开放/)).toBeVisible()
  await sf.getByRole('button',{name:'提交人工留言',exact:true}).click()
  await sf.getByLabel('留言问题').fill('请核查本次权限与成绩来源')
  await sf.getByRole('button',{name:'确认提交留言',exact:true}).click()
  await expect(sf.getByText('待处理',{exact:true})).toBeVisible()
  await student.screenshot({path:path.join(evidence,'03-student-ticket.png'),fullPage:true})
  const af = await adminLogin(admin)
  await af.getByRole('button',{name:'人工留言',exact:true}).click()
  await af.getByRole('button',{name:'查看并领取',exact:true}).first().click()
  await af.getByRole('button',{name:'领取并处理',exact:true}).click()
  await af.getByLabel('回复说明类型').selectOption('permission')
  await af.getByLabel('回复内容').fill('请在考务管理核对当前考试开放设置，不提供未授权的数据。')
  await af.getByRole('button',{name:'保存回复草稿',exact:true}).click()
  await expect(af.getByText('回复草稿已保存，状态仍为处理中')).toBeVisible()
  await af.getByRole('button',{name:'预览并核对回复',exact:true}).click()
  await af.getByLabel('已核对回复对象、数据来源及提交人当前权限').check()
  await af.getByRole('button',{name:'确认保存并回复',exact:true}).click()
  await expect(af.getByText('回复已保存，用户可在小程序查看')).toBeVisible()
  await admin.screenshot({path:path.join(evidence,'04-admin-reply.png'),fullPage:true})
  await student.reload(); await expect(sf.getByLabel('输入问题')).toBeVisible()
  await sf.getByRole('button',{name:'留言',exact:true}).click()
  await sf.getByRole('button',{name:/请核查本次权限与成绩来源/}).click()
  await expect(sf.getByText('已回复',{exact:true})).toBeVisible()
  await sf.getByRole('button',{name:'继续补充',exact:true}).click()
  await sf.getByLabel('留言问题').fill('请再说明办理入口')
  await sf.getByRole('button',{name:'确认提交留言',exact:true}).click()
  await expect(sf.getByText('待处理',{exact:true})).toBeVisible()
  const h=await auth(request),list=await(await request.get(base+'/tickets?management=true',{headers:h})).json(),t=list.find((t:any)=>t.question==='请核查本次权限与成绩来源')
  const c=await post(request,base+'/tickets/'+t.id+'/claim',h,{expected:t.revision})
  await post(request,base+'/tickets/'+t.id+'/reply',h,{expected:c.revision,text:'请联系学校运营管理员核对考务管理中的考试成绩开放设置。',reply_kind:'routing',reviewed:true})
  await student.reload();await expect(sf.getByLabel('输入问题')).toBeVisible();await sf.getByRole('button',{name:'留言',exact:true}).click();await sf.getByRole('button',{name:/请核查本次权限与成绩来源/}).click()
  await sf.getByRole('button',{name:'已解决，结束办理',exact:true}).click();await expect(sf.getByText('已关闭',{exact:true})).toBeVisible()
  await student.screenshot({path:path.join(evidence,'05-ticket-closed.png'),fullPage:true})
  const teacherContext=await browser.newContext(),teacher=await teacherContext.newPage(),tf=await miniLogin(teacher,'teacher')
  await tf.getByRole('button',{name:'留言',exact:true}).click();await expect(tf.getByText('还没有留言记录')).toBeVisible()
  expect(errors).toEqual([])
  await studentContext.close();await adminContext.close();await teacherContext.close()
})

test('移动端自然语言提问、学习工具、历史会话和报告空态', async ({ page }) => {
  await page.setViewportSize(process.env.QA_ANSWER_WEB === '1' ? {width:1440,height:1000} : {width:390,height:844});const f=await miniLogin(page,'teacher')
  if (process.env.QA_ANSWER_WEB === '1') {
    await expect(f.getByRole('heading',{name:/想了解什么，尽管问吧/})).toBeVisible()
    await page.screenshot({path:path.join(evidence,'21-desktop-web-welcome.png'),fullPage:true})
    await page.setViewportSize({width:390,height:844})
  }
  await f.getByLabel('输入问题').fill('你好');await f.getByLabel('发送问题').click();await expect(f.getByText('你好，可以直接描述')).toBeVisible()
  if (process.env.QA_ANSWER_WEB === '1') { await expect(f.getByRole('button',{name:'新会话',exact:true})).toBeEnabled(); await expect(f.locator('.message').last()).toHaveCSS('opacity','1') }
  await page.screenshot({path:path.join(evidence,'06-mobile-chat.png'),fullPage:true})
  await f.getByRole('button',{name:'学习工具',exact:true}).click();await f.getByRole('button',{name:/历史会话/}).click();await expect(f.getByText('历史数据型答复会按你当前的权限重新核对。')).toBeVisible()
  await f.getByLabel('返回', {exact:true}).click();await f.getByRole('button',{name:/报告中心/}).click();await expect(f.getByText('暂无可查看报告')).toBeVisible()
  await page.screenshot({path:path.join(evidence,'07-mobile-reports.png'),fullPage:true})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
})

function textPdf() {
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>']
  for (const [number,text] of [[4,'VERIFIED SCHOOL REPORT / PAGE ONE'],[6,'VERIFIED SCHOOL REPORT / PAGE TWO']]) {
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 7 0 R >> >> /Contents ${number} 0 R >>`)
    const stream = `BT /F1 14 Tf 50 780 Td (${text}) Tj ET`;objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`)
  }
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
  let pdf='%PDF-1.4\n';const offsets:number[]=[]
  objects.forEach((o,i)=>{offsets.push(Buffer.byteLength(pdf));pdf+=`${i+1} 0 obj\n${o}\nendobj\n`})
  const offset=Buffer.byteLength(pdf);pdf+='xref\n0 8\n0000000000 65535 f \n'+offsets.map(n=>n.toString().padStart(10,'0')+' 00000 n \n').join('')+`trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n${offset}\n%%EOF`
  return Buffer.from(pdf)
}

test('真实双页报告、自然语言引用、下载、权限撤销后的历史和PDF阻断', async ({ page, request }) => {
  test.setTimeout(90000)
  const h=await auth(request),reportBase='/api/v1/platform/education/report-management'
  const draft={name:'小程序报告闭环验收',academic_year:'2026-2027',exam_date:'2026-10-19',subjects:[{key:'chinese',name:'语文',full_score:150,student_ids:fixture.students.slice(0,2).map((s:any)=>s.id)}]}
  const checked=await post(request,examBase+'/preview',h,draft)
  let exam=await post(request,examBase,h,{...draft,preview_hash:checked.preview_hash})
  const template=await request.get(`${examBase}/${exam.id}/score-template/${exam.subjects[0].subject_id}`,{headers:h})
  const bytes=execFileSync(path.resolve(__dirname,'../../.venv/bin/python'),['-c',`import io,sys
from openpyxl import load_workbook
b=load_workbook(io.BytesIO(sys.stdin.buffer.read()));s=b.active
for i in range(2,s.max_row+1):s.cell(i,7,90)
o=io.BytesIO();b.save(o);sys.stdout.buffer.write(o.getvalue())`],{input:await template.body()})
  const scored=await post(request,`${examBase}/${exam.id}/score-files`,h,{expected_revision:exam.revision,subject_id:exam.subjects[0].subject_id,filename:'合成成绩.xlsx',content_base64:bytes.toString('base64')})
  exam=await post(request,`${examBase}/${exam.id}/score-files/${scored.id}/confirm`,h)
  const permission={expected_revision:exam.revision,student_ids:[fixture.students[0].id],subject_ids:[exam.subjects[0].subject_id],mode:'open'}
  const preview=await request.post(`${examBase}/${exam.id}/permissions/student/preview`,{headers:h,data:permission});expect(preview.ok()).toBeTruthy()
  exam=await post(request,`${examBase}/${exam.id}/permissions/student`,h,{...permission,preview_hash:preview.headers()['x-exam-preview-hash']})
  const scope=await(await request.get(`${reportBase}/exams/${exam.id}`,{headers:h})).json(),subject=scope.subjects[0],sid=subject.student_ids[0],student=scope.snapshots[sid],pdf=textPdf()
  const row={category:'diagnostic',report_type:'student',subject_ids:[subject.subject_id],target_key:sid,previewed:true,naming:{category:'diagnostic',report_type:'student',subject_ids:[subject.subject_id]},file:{filename:[scope.exam_code,student.platform_id,student.name,subject.name,'个人学情诊断'].join('_')+'.pdf',content_base64:pdf.toString('base64')}}
  const batch={exam_id:exam.id,expected_exam_revision:exam.revision,reports:[row]},prepared=await post(request,reportBase+'/batches/preview',h,batch)
  const saved=await post(request,reportBase+'/batches',h,{...batch,preview_hash:prepared.preview_hash}),report=saved.reports[0]
  const f=await miniLogin(page)
  await f.getByLabel('输入问题').fill('查看小程序报告闭环验收语文诊断报告');await f.getByLabel('发送问题').click()
  await expect(f.getByRole('button',{name:/第2页/})).toBeVisible()
  await f.getByRole('button',{name:/第2页/}).click();await expect(f.getByRole('img',{name:'报告PDF第1页'})).toBeVisible()
  await f.getByRole('button',{name:'下一页',exact:true}).click();await expect(f.getByRole('img',{name:'报告PDF第2页'})).toBeVisible()
  await page.screenshot({path:path.join(evidence,'08-two-page-report.png'),fullPage:true})
  const download=page.waitForEvent('download');await f.getByRole('button',{name:'下载当前 PDF',exact:true}).click()
  const file=await download;expect(readFileSync((await file.path())!).equals(pdf)).toBeTruthy()
  const revoke={expected_revision:exam.revision,student_ids:[fixture.students[0].id],subject_ids:[exam.subjects[0].subject_id],mode:'close'}
  const rp=await request.post(`${examBase}/${exam.id}/permissions/student/preview`,{headers:h,data:revoke});expect(rp.ok()).toBeTruthy()
  await post(request,`${examBase}/${exam.id}/permissions/student`,h,{...revoke,preview_hash:rp.headers()['x-exam-preview-hash']})
  await f.getByRole('button',{name:'上一页',exact:true}).click();await expect(f.locator('#pdfCanvasWrap').getByText('报告不存在、版本已变化或当前无权查看。')).toBeVisible()
  await f.getByLabel('返回',{exact:true}).click();await f.getByRole('button',{name:'学习工具',exact:true}).click();await f.getByRole('button',{name:/历史会话/}).click()
  await f.getByRole('button',{name:/小程序报告闭环验收语文诊断报告/}).click();await expect(f.getByText('当前权限或来源版本已变化，相关历史答复及来源已隐藏。')).toBeVisible()
})

test('提交响应丢失后保留输入并以同一请求重试，留言只建立一次', async ({ page, request }) => {
  const oldAuth=await auth(request,'teacher2');await post(request,base+'/tickets',oldAuth,{question:'合成旧问题，用于检查新留言排序'})
  const f=await miniLogin(page,'teacher2');await f.getByRole('button',{name:'留言',exact:true}).click();await f.getByRole('button',{name:'＋ 新建留言',exact:true}).click();await f.getByLabel('留言问题').fill('合成响应丢失重试验收')
  let lost=false
  await page.route('**/api/v1/answer-workbench/tickets',async route=>{if(route.request().method()==='POST'&&!lost){lost=true;await route.fetch();await route.abort('failed')}else await route.continue()})
  await f.getByRole('button',{name:'确认提交留言',exact:true}).click();await expect(f.getByText(/留言未提交，编辑内容保留/)).toBeVisible();await expect(f.getByLabel('留言问题')).toHaveValue('合成响应丢失重试验收')
  await f.getByRole('button',{name:'确认提交留言',exact:true}).click();await expect(f.getByText('待处理',{exact:true})).toBeVisible()
  const h=await auth(request,'teacher2'),tickets=await(await request.get(base+'/tickets',{headers:h})).json();expect(tickets.filter((t:any)=>t.question==='合成响应丢失重试验收')).toHaveLength(1)
  await f.getByLabel('返回',{exact:true}).click();await expect(f.locator('#screen button.card').first()).toContainText('合成响应丢失重试验收')
})

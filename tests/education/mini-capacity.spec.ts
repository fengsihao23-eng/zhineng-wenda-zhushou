import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const fixture=JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!,'utf8'))
const base='/api/v1/answer-workbench'
async function auth(request:APIRequestContext,kind:string){
  const response=await request.post('/api/v1/auth/login',{data:{username:fixture.users[kind],password:process.env.QA_PASSWORD}})
  expect(response.ok()).toBeTruthy();return {Authorization:'Bearer '+(await response.json()).access_token}
}
async function login(page:Page,kind:string,desktop:boolean){
  if(desktop){
    await page.goto('/login');await page.getByLabel('用户名').fill(fixture.users[kind]);await page.getByLabel('密码',{exact:true}).fill(process.env.QA_PASSWORD!);await page.getByRole('button',{name:'登录',exact:true}).click()
    await expect(page.getByRole('button',{name:'退出登录',exact:true})).toBeVisible();await page.goto('/teacher/chat')
  }else await page.goto('/mini-preview')
  const frame=page.frameLocator(desktop?'iframe[title="智能问答助手"]':'iframe[title="学科智能问答小程序"]')
  if(!desktop){await frame.getByLabel('登录账号').fill(fixture.users[kind]);await frame.getByLabel('密码',{exact:true}).fill(process.env.QA_PASSWORD!);await frame.getByRole('button',{name:'登录',exact:true}).click()}
  await expect(frame.getByLabel('输入问题')).toBeVisible();return frame
}
test.beforeAll(async({request})=>{const headers=await auth(request,'admin');expect((await request.get(base+'/admin/state',{headers})).ok()).toBeTruthy()})

for(const desktop of [false,true])test(`${desktop?'网页':'手机网页'}第100次响应丢失后可重试，次数不重复扣除，刷新后仍为零`,async({page,request})=>{
  test.setTimeout(120000)
  const kind=desktop?'teacheroutside':'teacherleader',headers=await auth(request,kind)
  const status=await(await request.get(base+'/mini/status',{headers})).json()
  for(let i=0;i<status.quota.remaining-1;i++){
    const response=await request.post(base+'/mini/ask',{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data:{question:'你好'}})
    expect(response.ok()).toBeTruthy()
  }
  const frame=await login(page,kind,desktop);await expect(frame.locator('.quota-number, .quota-line strong')).toHaveText('1')
  let lost=false
  await page.route('**/api/v1/answer-workbench/mini/ask',async route=>{
    if(!lost){lost=true;await route.fetch();await route.abort('failed')}else await route.continue()
  })
  await frame.getByLabel('输入问题').fill('你好');await frame.getByLabel('发送问题').click()
  await expect(frame.getByText(/本次提问未完成，问题已保留/)).toBeVisible()
  await expect(frame.getByLabel('输入问题')).toHaveValue('你好');await expect(frame.getByLabel('发送问题')).toBeEnabled()
  await frame.getByLabel('发送问题').click();await expect(frame.locator('.quota-line strong')).toHaveText('0')
  await expect(frame.getByLabel('发送问题')).toBeDisabled();await expect(frame.getByText('你好，可以直接描述', {exact:false}).last()).toBeVisible()
  await page.reload();await expect(frame.locator('.quota-line strong')).toHaveText('0');await expect(frame.getByLabel('发送问题')).toBeDisabled()
  expect((await(await request.get(base+'/mini/status',{headers})).json()).quota.used).toBe(100)
  await frame.getByRole('button',{name:'学习工具',exact:true}).click();await expect(frame.getByRole('button',{name:/报告中心/})).toBeEnabled()
})

test('在线人数展示覆盖499、500、999、1000、1001边界，低于500不提醒',async({page})=>{
  let count=499
  await page.route('**/api/v1/answer-workbench/mini/*',async route=>{
    if(!['GET','POST'].includes(route.request().method())){await route.continue();return}
    const response=await route.fetch(),value=await response.json()
    const traffic={count,level:count>=1000?'extreme':count>=500?'busy':null,label:count>=1000?'极度拥堵':count>=500?'较为拥堵':'',message:'功能展示测试'}
    if(value.questionStatus)value.questionStatus.traffic=traffic;else if(value.traffic)value.traffic=traffic
    await route.fulfill({response,json:value})
  })
  const frame=await login(page,'teacher2',false)
  for(const [number,label]of [[499,''],[500,'较为拥堵'],[999,'较为拥堵'],[1000,'极度拥堵'],[1001,'极度拥堵']] as const){
    count=number;await page.reload();await expect(frame.getByLabel('输入问题')).toBeVisible()
    if(label)await expect(frame.locator('.traffic-notice b')).toHaveText(label)
    else await expect(frame.locator('.traffic-notice')).toHaveCount(0)
  }
})

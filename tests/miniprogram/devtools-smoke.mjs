/** Actual WeChat devtools rendering/binding gate. Needs an unlocked Mac and enabled service port. */
import automator from 'miniprogram-automator'
import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const session=process.env.QA_WECHAT_OUTPUT || path.join(root,'.local/wechat-mini/session')
const fixture=JSON.parse(await readFile(path.join(session,'fixtures.json'),'utf8'))
const output=path.join(session,'devtools');await mkdir(output,{recursive:true})
const mini=process.env.QA_WECHAT_WS ? await automator.connect({wsEndpoint:process.env.QA_WECHAT_WS}) : await automator.launch({
  projectPath:path.join(root,'apps/miniprogram'),cliPath:process.env.WECHAT_CLI || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',trustProject:true,timeout:30000
})
const errors=[];mini.on('exception',error=>errors.push(error))
try{
  await mini.callWxMethod('removeStorageSync','subject-assistant.auth.v1')
  const page=await mini.reLaunch('/pages/workbench/index')
  await page.waitFor('#account')
  await mini.screenshot({path:path.join(output,'01-login.png')})
  await (await page.$('#account')).input(fixture.users.teacher2)
  await (await page.$('#password')).input(fixture.password)
  await (await page.$('#login')).tap()
  await page.waitFor(async()=>await page.data('view')==='chat' && !await page.data('busy'))
  assert.equal(await page.data('identity.role'),'teacher')
  await mini.screenshot({path:path.join(output,'02-chat-home.png')})
  const before=await page.data('questionStatus.quota.used')
  await (await page.$('#question')).input('你好')
  await (await page.$('#sendQuestion')).tap()
  await page.waitFor(async()=>await page.data('messages.length')===2 && !await page.data('busy'))
  assert.equal(await page.data('questionStatus.quota.used'),before+1)
  assert.ok((await (await page.$('.messages')).text()).includes('你好，可以直接描述'))
  await mini.screenshot({path:path.join(output,'03-answer.png')})
  await (await page.$('.tab-item[data-view="tools"]')).tap();await page.waitFor(async()=>await page.data('view')==='tools')
  await mini.screenshot({path:path.join(output,'04-tools.png')})
  await (await page.$('.tool-card[data-view="history"]')).tap();await page.waitFor(async()=>await page.data('view')==='history')
  assert.ok((await (await page.$('.screen')).text()).includes('你好'))
  await (await page.$('.tab-item[data-view="tickets"]')).tap();await page.waitFor('#newTicket')
  await (await page.$('#newTicket')).tap();await page.waitFor('#ticketQuestion')
  await (await page.$('#ticketQuestion')).input('开发者工具原生界面实际提交验收')
  await (await page.$('#submitTicket')).tap();await page.waitFor(async()=>await page.data('view')==='ticket' && !await page.data('busy'))
  assert.equal(await page.data('ticket.status'),'待处理')
  await mini.screenshot({path:path.join(output,'05-ticket.png')})
  assert.equal(errors.length,0)
  await writeFile(path.join(output,'result.json'),JSON.stringify({kind:'real-wechat-devtools',cases:['login','ask','quota','tools','history','ticket'],errors},null,2))
  console.log('微信开发者工具原生渲染与交互验收通过。截图：'+output)
}finally{await mini.disconnect()}

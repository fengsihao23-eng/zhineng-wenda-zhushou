/** Actual WeChat network -> existing deployed school data -> real model -> web API read-back.
 * Requires an owner-authorized short-lived session in an ignored, private file.
 * It intentionally saves one clearly labelled verification question in that account's history.
 */
import automator from 'miniprogram-automator'
import assert from 'node:assert/strict'
import { readFile,mkdir,writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const sessionFile=process.env.QA_LIVE_SESSION_FILE
assert.ok(sessionFile,'Set QA_LIVE_SESSION_FILE to the private, short-lived owner-authorized session')
const fixture=JSON.parse(await readFile(sessionFile,'utf8'))
const output=path.dirname(sessionFile),base=fixture.baseUrl.replace(/\/$/,'')
await mkdir(output,{recursive:true,mode:0o700})
const headers={Authorization:'Bearer '+fixture.access_token,'Content-Type':'application/json'}
const endpoint=base+'/answer-workbench'
async function web(path){
  const response=await fetch(path.startsWith('http')?path:endpoint+path,{headers,signal:AbortSignal.timeout(30000)})
  assert.equal(response.status,200,'Web API read-back must use the actual account scope')
  return response.json()
}
const health=await web(base+'/health')
assert.equal(health.environment,'production')
assert.equal(health.model.test_model_enabled,false)
assert.equal(health.model.real_model_ready,true)
assert.ok(health.model.available_providers.includes('deepseek'))
const before=await web('/mini/state')
assert.equal(before.identity.userId,fixture.user.id)
const mini=await automator.launch({projectPath:path.join(root,'apps/miniprogram'),
  cliPath:process.env.WECHAT_CLI||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',trustProject:true,timeout:30000})
const client=randomUUID(),errors=[]
mini.on('exception',error=>errors.push(error))
const record={health,before:{examIds:before.exams.map(e=>e.id),reportIds:before.reports.map(r=>r.id)},checks:{}}
async function native(path,body,key){
  const value=await mini.evaluate(options=>new Promise(resolve=>wx.request({...options,
    success:r=>resolve({statusCode:r.statusCode,data:r.data}),fail:e=>resolve({statusCode:0,error:e.errMsg})})),{url:endpoint+path,method:body===undefined?'GET':'POST',
    data:body,header:{...headers,...(key?{'Idempotency-Key':key}:{})},timeout:55000})
  assert.equal(value.statusCode,200,'Native request failed: '+path+' ('+value.statusCode+')')
  return value.data
}
try{
  console.log('LIVE_PHASE=read_authorized_data')
  const state=await native('/mini/state')
  assert.equal(state.identity.userId,fixture.user.id)
  assert.ok(JSON.stringify(state.exams.map(e=>e.id).sort())===JSON.stringify(before.exams.map(e=>e.id).sort()),'WeChat/web authorized exam lists differ')
  assert.ok(JSON.stringify(state.reports.map(e=>e.id).sort())===JSON.stringify(before.reports.map(e=>e.id).sort()),'WeChat/web authorized report lists differ')
  record.checks.sharedAccountAndData=true
  console.log('LIVE_PHASE=quota_and_report')
  const status=await native('/mini/presence',{client_id:client})
  assert.ok(status.quota.remaining>0,'This account has exhausted its daily quota')
  record.quotaBefore=status.quota
  if(state.reports.length){
    const report=state.reports[0]
    const file=await mini.evaluate(options=>new Promise(resolve=>wx.downloadFile({...options,
      success:r=>resolve({statusCode:r.statusCode,tempFilePath:r.tempFilePath}),fail:e=>resolve({statusCode:0,error:e.errMsg})})),{url:endpoint+'/reports/'+report.id+'/file?version='+report.version+'&page=1',header:headers,timeout:55000})
    assert.equal(file.statusCode,200,'Actual authorized report must open from WeChat')
    record.checks.actualReportAccess=true
    await mini.evaluate(filePath=>{try{wx.getFileSystemManager().unlinkSync(filePath)}catch(_){};return true},file.tempFilePath)
  }else record.checks.actualReportAccess='no_authorized_report'
  const key=randomUUID(),body={question:fixture.question}
  console.log('LIVE_PHASE=real_model_question')
  const result=await native('/mini/ask',body,key),answer=result.messages[result.messages.length-1]
  record.sessionId=result.id;record.answer=answer;record.question=fixture.question
  await writeFile(path.join(output,'live-answer-private.json'),JSON.stringify(record,null,2),{mode:0o600})
  assert.ok(!answer.serviceFailure&&!answer.configurationFailure&&!answer.fallback,'Real model did not produce an authorized answer; inspect private verification evidence')
  assert.ok(answer.sources.some(s=>s.kind==='score'),'Answer must include the actual authorized score source')
  assert.ok(answer.table.some(row=>Number(row.score)===Number(fixture.expected_score)),'Answer score table differs from the existing database')
  assert.ok(answer.text && !answer.text.includes('确定性回答模型'),'Test-model output is not accepted')
  record.checks.realModelAnswer=true
  console.log('LIVE_PHASE=web_readback_and_retry')
  const after=await web('/mini/state'),saved=after.sessions.find(s=>s.id===result.id)
  assert.ok(saved,'The native conversation is missing from the web backend')
  assert.equal(saved.messages[saved.messages.length-1].id,answer.id)
  assert.equal(saved.messages[saved.messages.length-1].text,answer.text)
  record.checks.webConversationReadback=true
  const replay=await native('/mini/ask',body,key)
  assert.equal(replay.id,result.id)
  assert.equal(replay.messages.length,result.messages.length)
  assert.equal(replay.questionStatus.quota.used,result.questionStatus.quota.used)
  assert.equal(result.questionStatus.quota.used,status.quota.used+1)
  record.checks.idempotencyAndQuota=true
  assert.equal(errors.length,0)
  const summary={environment:'production',provider:health.model.configured_provider,model:health.model.default_model,testModel:false,
    authorizedExams:state.exams.length,authorizedReports:state.reports.length,checks:record.checks,oneQuestionCharged:true,nativeExceptions:errors.length}
  await writeFile(path.join(output,'live-answer-private.json'),JSON.stringify(record,null,2),{mode:0o600})
  await writeFile(path.join(output,'live-result.json'),JSON.stringify(summary,null,2))
  console.log(JSON.stringify(summary))
}finally{
  await native('/mini/presence',{client_id:client,present:false}).catch(()=>{})
  await mini.disconnect()
}

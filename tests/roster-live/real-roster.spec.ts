import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
const root = process.cwd();
const privateDir = path.join(root, '.local/yjyz-roster');
const f = JSON.parse(readFileSync(path.join(privateDir, 'acceptance-fixture.json'), 'utf8'));
const P = '/api/v1/platform/education';
const report: Record<string, any> = { source_sha256: f.source_sha256, source_rows: f.original.length, class_count: f.class_count, subject_count: f.subject_count, model: 'deepseek-flash' };
const save = () => writeFileSync(path.join(privateDir, 'acceptance-report.json'), JSON.stringify(report, null, 2), { mode: 0o600 });
let mainToken = '', sandboxToken = '', sandboxTeachers: any[] = [], studentRows: any[] = [];
const userTokens: Record<string, string> = {};
async function login(page: Page, actor = f.identity) {
  await page.goto('/login');
  await page.getByLabel('用户名').fill(actor.username);
  await page.getByLabel('密码', { exact: true }).fill(actor.password);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible({ timeout: 15000 });
  await page.goto('/admin/school?tab=teachers');
  await expect(page.getByRole('heading', { name: '教师信息列表', exact: true })).toBeVisible();
}
async function auth(request: APIRequestContext, actor: any, type?: string) {
  const response = await request.post('/api/v1/auth/login', { data: { username: actor.username, password: actor.password, school_id: actor.school_id, account_type: type } });
  expect(response.status(), 'login HTTP status').toBe(200);
  return response.json();
}
async function api(request: APIRequestContext, token: string, method: string, route: string, body?: any, status = 200) {
  const response = await request.fetch(route.startsWith('/api') ? route : P + route, { method, headers: { Authorization: `Bearer ${token}` }, data: body, timeout: 180000 });
  expect(response.status(), `${method} ${route} status`).toBe(status);
  return response.json();
}
async function list(request: APIRequestContext, token: string, kind: string) {
  const first = await api(request, token, 'GET', `/roster/${kind}/records?page_size=100`);
  let rows = first.items;
  for (let page=2; rows.length<first.total; page++) rows = rows.concat((await api(request, token, 'GET', `/roster/${kind}/records?page_size=100&page=${page}`)).items);
  return rows;
}
async function upload(page: Page, kind: 'teachers'|'students', filename: string) {
  await page.goto(`/admin/school/${kind}/import`);
  const noun = kind === 'teachers' ? '教师' : '学生';
  const done = page.waitForResponse(response => response.url().endsWith(`/roster/${kind}/imports`) && response.request().method() === 'POST');
  await page.getByLabel(`上传${noun} Excel`).setInputFiles(filename);
  await page.getByRole('button', { name: '上传并预校验', exact: true }).click();
  const response = await done; expect(response.status()).toBe(200);
  const batch = await response.json();
  await expect(page.getByRole('heading', { name: '导入预览与结果' })).toBeVisible();
  return batch;
}
async function confirm(page: Page, id: string) {
  const done = page.waitForResponse(response => response.url().endsWith(`/imports/${id}/confirm`) && response.request().method() === 'POST', { timeout: 180000 });
  await page.getByRole('button', { name: '确认导入并创建账号', exact: true }).click();
  const response = await done; expect(response.status()).toBe(200);
  const result = await response.json();
  await expect(page.getByRole('heading', { name: '导入完成', exact: true })).toBeVisible();
  return result;
}

test.describe.serial('real workbook + real Flash acceptance', () => {
  test('import all 160 actual staff using UI, preserve every field and verify every initial login', async ({ page, request }) => {
    mainToken = (await auth(request, f.identity)).access_token;
    sandboxToken = (await auth(request, f.sandbox)).access_token;
    await login(page);
    let existing = await list(request, mainToken, 'teachers');
    if (existing.length === 0) {
      const batch = await upload(page, 'teachers', f.source);
      expect(batch.report.ok).toBe(true); expect(batch.report.total_rows).toBe(160);
      expect(batch.report.issues).toHaveLength(0); expect(batch.report.suspicious).toHaveLength(0);
      const result = await confirm(page, batch.id);
      expect(result.report.success_count).toBe(160); expect(result.report.skipped_count).toBe(0);
      expect(result.report.unresolved_teaching).toHaveLength(0);
      report.import_batch_id = result.id;
      report.imported_at = result.report.confirmed_at;
      report.success_count = result.report.success_count;
      existing = await list(request, mainToken, 'teachers');
    } else {
      expect(existing).toHaveLength(160);
      const batches = await api(request, mainToken, 'GET', '/roster/teachers/imports');
      const result = await api(request, mainToken, 'GET', `/roster/imports/${batches.find((b: any) => b.status === 'succeeded').id}`);
      report.import_batch_id = result.id; report.imported_at = result.report.confirmed_at; report.success_count = 160;
    }
    expect(existing).toHaveLength(160);
    for (const original of f.original) {
      const stored = existing.find((r: any) => r.username === original['教师账号'].trim());
      expect(Boolean(stored), 'every original account present').toBe(true);
      expect(Object.keys(original).every(key => stored.fields[key] === original[key]), 'all 24 original cell values retained').toBe(true);
      expect(stored.status).toBe('active');
      const response = await auth(request, { username: stored.username, password: stored.username, school_id: f.identity.school_id }, 'teacher');
      expect(response.user.must_change_password).toBe(true);
      expect(response.user.roles).toContain('TEACHER');
    }
    const model = (await (await request.get('/api/v1/health')).json()).model;
    expect(model.default_model).toBe('deepseek-flash'); expect(model.real_model_ready).toBe(true);
    report.initial_login_verified = 160; report.original_fields_verified = 160 * 24; report.all_original_accounts_unchanged = true;
    const duplicate = await upload(page, 'teachers', f.source);
    expect(duplicate.status).toBe('invalid'); expect(duplicate.report.issues).toHaveLength(160);
    await api(request, mainToken, 'POST', `/roster/imports/${duplicate.id}/confirm`, { expected_revision: duplicate.revision }, 409);
    expect((await list(request, mainToken, 'teachers')).length).toBe(160);
    report.reimport_duplicates_blocked = 160;
    save();
  });

  test('real-format cloned profiles generate scoped roles and first-login password gates', async ({ page, request }) => {
    await login(page, f.sandbox);
    const batch = await upload(page, 'teachers', f.files.teachers);
    expect(batch.report.ok).toBe(true);
    const result = await confirm(page, batch.id); expect(result.report.success_count).toBe(6);
    sandboxTeachers = await list(request, sandboxToken, 'teachers');
    for (const key of Object.keys(f.accounts)) {
      const username = f.accounts[key];
      const response = await auth(request, { username, password: username, school_id: f.sandbox.school_id }, 'teacher');
      const token = response.access_token;
      const blocked = await api(request, token, 'GET', '/school/classes', undefined, 403);
      expect(blocked.error.code).toBe('PASSWORD_CHANGE_REQUIRED');
      const changed = await api(request, token, 'POST', '/api/v1/auth/change-password', { current_password: username, new_password: f.sandbox.password });
      userTokens[key] = changed.access_token;
      await api(request, token, 'GET', '/api/v1/auth/me', undefined, 401);
    }
    const role = async (key: string) => (await api(request,userTokens[key],'GET','/api/v1/auth/me')).roles;
    expect(await role('admin')).toContain('SCHOOL_ADMIN');
    expect(await role('exam')).toContain('EXAM_ADMIN');
    expect(await role('multi')).toContain('SUBJECT_LEADER');
    expect(await role('grade')).toContain('GRADE_LEADER');
    const multiSubjects = await api(request,userTokens.multi,'GET','/school/subjects');
    expect(multiSubjects.items.map((r:any)=>r.name).sort()).toEqual(['英语','语文']);
    expect((await api(request,userTokens.multi,'GET','/school/classes?page_size=100')).total).toBe(32);
    expect((await api(request,userTokens.grade,'GET','/school/classes?page_size=100')).total).toBe(31);
    await api(request,userTokens.teacher,'GET','/roster/teachers/records',undefined,403);
    await api(request,userTokens.exam,'GET','/roster/teachers/records',undefined,403);
    const exam = await api(request,userTokens.exam,'POST','/school/exams',{external_exam_id:'scope-'+f.suffix,name:'考试管理员权限验收',exam_type:'QA',start_date:'2026-09-22'});
    expect(Boolean(exam.id)).toBe(true);
    await api(request,userTokens.exam,'POST','/school/classes',{external_class_id:'denied',name:'不应创建'},403);
    await api(request,sandboxToken,'GET',`/roster/imports/${report.import_batch_id}`,undefined,404);
    report.role_scope_and_password_gate = 'passed'; report.multi_subject_leader_classes = 32; report.multi_subject_leader_subjects = 2;
    save();
  });

  test('row errors, suspected duplicates and teacher delete/reimport use the complete workflow', async ({ page, request }) => {
    await login(page, f.sandbox);
    const invalid = await upload(page,'teachers',f.files.invalid);
    expect(invalid.report.issues).toHaveLength(1); expect(invalid.report.issues[0].fields).toBe('教师姓名、教师账号、状态');
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button',{name:'下载本批次错误清单',exact:true}).click();
    const download=await downloadEvent; await download.saveAs(path.join(privateDir,'error-list.xlsx'));
    const batch = await upload(page,'teachers',f.files.suspects);
    expect(batch.report.suspicious).toHaveLength(2);
    await expect(page.getByLabel('第2行保留或放弃')).toHaveValue('true');
    await expect(page.getByRole('button',{name:'确认导入并创建账号',exact:true})).toBeDisabled();
    await api(request,sandboxToken,'POST',`/roster/imports/${batch.id}/confirm`,{expected_revision:batch.revision},422);
    await page.getByLabel('第3行保留或放弃').selectOption('false');
    await page.getByLabel('已核对第 2 行').check(); await page.getByLabel('已核对第 3 行').check();
    const result=await confirm(page,batch.id); expect(result.report.success_count).toBe(1);expect(result.report.skipped_count).toBe(1);
    const detached=sandboxTeachers.find(r=>r.username===f.accounts.detached);
    await api(request,sandboxToken,'POST',`/roster/teachers/records/${detached.id}/actions`,{action:'disable',confirmed:true});
    await api(request,userTokens.detached,'GET','/api/v1/auth/me',undefined,403);
    await api(request,sandboxToken,'POST',`/roster/teachers/records/${detached.id}/actions`,{action:'delete',confirmed:true});
    const again=await upload(page,'teachers',f.files.reimport);expect(again.report.ok).toBe(true);await confirm(page,again.id);
    const exam=sandboxTeachers.find(r=>r.username===f.accounts.exam);
    await api(request,sandboxToken,'POST',`/roster/teachers/records/${exam.id}/actions`,{action:'depart',confirmed:true});
    await api(request,userTokens.exam,'GET','/api/v1/auth/me',undefined,403);
    report.duplicate_keep_skip = {kept:1,skipped:1};report.teacher_lifecycle='passed';report.error_download='passed';save();
  });

  test('student import, real Flash questions and graduation retain all history', async ({ page, request }) => {
    await login(page,f.sandbox);
    const batch=await upload(page,'students',f.files.students);expect(batch.report.ok).toBe(true);
    const result=await confirm(page,batch.id);expect(result.report.success_count).toBe(2);expect(result.report.parent_binding_count).toBeUndefined();
    studentRows=await list(request,sandboxToken,'students');
    report.student_ids=studentRows.map(r=>r.id);save();
    // Only synthetic student scores are seeded; real teacher data never enters an LLM prompt.
    const seeded=spawnSync(path.join(root,'.venv/bin/python'),[path.join(root,'tests/roster-live/seed_scores.py')],{cwd:privateDir,env:{...process.env,PYTHONPATH:path.join(root,'apps/api'),APP_ENV:'test',MODEL_PROVIDER:'fake',DATABASE_URL:'postgresql+asyncpg://qa_education@127.0.0.1:55449/yjyz_roster_20260922'},encoding:'utf8'});
    expect(seeded.status,'synthetic score setup').toBe(0);
    const scoreState=JSON.parse(readFileSync(path.join(privateDir,'score-state.json'),'utf8'));
    const account=f.students[0]['账号'];
    await page.getByRole('button',{name:'退出登录'}).click();
    await page.getByLabel('用户名').fill(account); await page.getByLabel('密码',{exact:true}).fill(account);
    await page.getByRole('button',{name:'登录',exact:true}).click();
    await expect(page).toHaveURL(/change-password$/);
    await page.getByLabel('当前密码',{exact:true}).fill(account);
    await page.getByLabel('新密码（至少 8 位）',{exact:true}).fill(f.sandbox.password);
    await page.getByLabel('再次输入新密码',{exact:true}).fill(f.sandbox.password);
    await page.getByRole('button',{name:'修改密码并进入系统'}).click();
    await expect(page.getByRole('button',{name:'退出登录'})).toBeVisible();
    const studentAuth=await auth(request,{username:account,password:f.sandbox.password,school_id:f.sandbox.school_id},'student');
    const token=studentAuth.access_token;
    const session=await api(request,token,'POST','/api/v1/chat/sessions',{} ,201);
    const started=Date.now();
    const answer=await api(request,token,'POST',`/api/v1/chat/sessions/${session.id}/messages`,{content:'我这次数学考试多少分？请只根据查到的数据回答。',client_message_id:crypto.randomUUID()});
    expect(answer.message.content).toContain('83');expect(answer.sources.length).toBeGreaterThan(0);
    report.real_model_answer={model:'deepseek-flash',latency_ms:Date.now()-started,content:answer.message.content,agent_run_id:answer.agent_run_id,sources:answer.sources.length};
    const stream=await request.post(`/api/v1/chat/sessions/${session.id}/stream`,{headers:{Authorization:`Bearer ${token}`},data:{content:'数学第1题丢了多少分？',client_message_id:crypto.randomUUID()},timeout:60000});
    expect(stream.status()).toBe(200);const events=await stream.text();expect(events).toContain('event: done');expect(events).toContain('content_delta');expect(events).not.toContain('event: error');
    await page.goto('/chat');await expect(page.getByText('83',{exact:false}).first()).toBeVisible({timeout:15000});
    await page.reload();await expect(page.getByText('83',{exact:false}).first()).toBeVisible({timeout:15000});
    report.real_model_stream_and_readback='passed';
    const child=studentRows.find(r=>r.username===account);
    await api(request,sandboxToken,'POST',`/roster/students/records/${child.id}/actions`,{action:'delete',confirmed:true},409);
    const parents=await api(request,sandboxToken,'GET',`/roster/students/${child.id}/parents`,undefined,404);
    expect(parents.error.code ?? parents.error.message).toMatch(/NOT_FOUND|404|不存在/);
    await api(request,sandboxToken,'POST',`/roster/students/records/${child.id}/actions`,{action:'graduate',confirmed:true});
    await api(request,token,'GET','/api/v1/auth/me',undefined,403);
    expect((await list(request,sandboxToken,'students')).find(r=>r.id===child.id).status).toBe('graduated');
    report.student_lifecycle='passed';report.synthetic_score_state=scoreState;report.graduated_student_id=child.id;save();
  });
});

test('preserve teacher history and complete student class-change through deletion and reimport', async ({ page, request }) => {
  Object.assign(report, JSON.parse(readFileSync(path.join(privateDir,'acceptance-report.json'),'utf8')));
  sandboxToken=(await auth(request,f.sandbox)).access_token;
  const staff=await list(request,sandboxToken,'teachers');
  const original=staff.find((row:any)=>row.username===f.accounts.teacher);
  const first=await api(request,sandboxToken,'GET','/school/teaching?page_size=100');
  let grants=first.items;
  for (let page=2;grants.length<first.total;page++) grants=grants.concat((await api(request,sandboxToken,'GET',`/school/teaching?page_size=100&page=${page}`)).items);
  const selected=grants.filter((grant:any)=>grant.teacher_user_id===original.id);
  expect(selected.length).toBeGreaterThan(0);
  const deletion=await api(request,sandboxToken,'POST',`/roster/teachers/records/${original.id}/actions`,{action:'delete',confirmed:true});
  const snapshot=await api(request,sandboxToken,'GET',`/roster/teachers/deletions/${deletion.deletion_id}`);
  expect(snapshot.teaching_history.map((row:any)=>row.id).sort()).toEqual(selected.map((row:any)=>row.id).sort());
  expect(Object.keys(snapshot.fields)).toHaveLength(24);
  await login(page,f.sandbox);
  const teacherBatch=await upload(page,'teachers',f.files['teacher-change']);expect(teacherBatch.report.ok).toBe(true);
  expect((await confirm(page,teacherBatch.id)).report.success_count).toBe(1);
  const changed=(await list(request,sandboxToken,'teachers')).find((row:any)=>row.username===f.accounts.teacher);
  expect(changed.id).not.toBe(original.id);expect(changed.name).toBe('联调移交后重导教师');
  const children=await list(request,sandboxToken,'students');const movable=children.find((row:any)=>row.username===f.students[1]['账号']);
  await api(request,sandboxToken,'POST',`/roster/students/records/${movable.id}/actions`,{action:'delete',confirmed:true});
  const studentBatch=await upload(page,'students',f.files['student-change']);expect(studentBatch.report.ok).toBe(true);
  expect((await confirm(page,studentBatch.id)).report.success_count).toBe(1);
  const moved=(await list(request,sandboxToken,'students')).find((row:any)=>row.username===f.students[1]['账号']);
  expect(moved.id).not.toBe(movable.id);expect(moved.class_name).toBe('高中一年级2班');
  report.teacher_history_reimport={status:'passed',preserved_grants:selected.length};report.student_class_change='passed';save();
});

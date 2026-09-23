// Local roster preview: persistent school database, production frontend, real configured model.
// Bind only loopback; .local contains private identity/runtime state and is ignored by Git.
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { createWriteStream } from 'node:fs';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(root, '.local/yjyz-roster');
await mkdir(scratch, { recursive: true, mode: 0o700 });
const python = path.join(root, '.venv/bin/python');
const env = { ...process.env, APP_ENV: 'test', DEBUG: 'false', DATABASE_URL: 'postgresql+asyncpg://qa_education@127.0.0.1:55449/yjyz_roster_20260922', PYTHONPATH: path.join(root, 'apps/api'), LOG_FILE: path.join(scratch, 'api.log'), SECRET_KEY: randomBytes(48).toString('hex'), JWT_SECRET_KEY: randomBytes(48).toString('hex'), RATE_LIMIT_PER_MINUTE: '3000', RATE_LIMIT_PER_HOUR: '30000' };
function run(command, args, cwd = scratch) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    child.stdout.on('data', data => { output += data; });
    child.stderr.on('data', () => {});
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve(output) : reject(new Error(`Preview setup failed (${code}); step ${path.basename(args[0])}`)));
  });
}
const config = JSON.parse(await run(python, ['-c', `import json; from dotenv import dotenv_values; c=dotenv_values(${JSON.stringify(path.join(root, 'apps/api/.env'))}); print(json.dumps({k:c.get(k,'') for k in ['MODEL_PROVIDER','DEEPSEEK_API_KEY','DEEPSEEK_API_BASE','DEEPSEEK_MODEL','DEEPSEEK_THINKING','DEFAULT_MODEL']}))`]));
Object.assign(env, config, { OPENAI_API_KEY: '' });
await run(python, ['-m', 'alembic', 'upgrade', 'head'], path.join(root, 'apps/api'));
await run(python, [path.join(root, 'apps/api/scripts/setup_roster_preview.py')]);
const identity = JSON.parse(await readFile(path.join(scratch, 'identity.json'), 'utf8'));
env.JWT_SECRET_KEY = identity.jwt_secret; env.SECRET_KEY = identity.app_secret;
const dist = path.join(scratch, 'web');
const buildConfig = path.join(scratch, 'vite.config.mjs');
await writeFile(buildConfig, `import react from ${JSON.stringify(path.join(root, 'apps/web/node_modules/@vitejs/plugin-react/dist/index.js'))};export default {root:${JSON.stringify(path.join(root, 'apps/web'))},envDir:${JSON.stringify(scratch)},plugins:[react()],build:{outDir:${JSON.stringify(dist)},emptyOutDir:true}};`);
await run(process.execPath, [path.join(root, 'apps/web/node_modules/vite/bin/vite.js'), 'build', '--config', buildConfig]);
const reserve = createServer();
await new Promise(resolve => reserve.listen(0, '127.0.0.1', resolve));
const apiPort = reserve.address().port;
await new Promise(resolve => reserve.close(resolve));
const apiBase = `http://127.0.0.1:${apiPort}`;
const apiLog = createWriteStream(path.join(scratch, 'api-startup.log'), { flags: 'a', mode: 0o600 });
const api = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(apiPort), '--no-access-log'], { cwd: scratch, env, stdio: ['ignore', 'pipe', 'pipe'] });
api.stdout.pipe(apiLog); api.stderr.pipe(apiLog);
let ready = false;
for (let attempt = 0; attempt < 40; attempt++) {
  if (api.exitCode !== null) break;
  try { if ((await fetch(apiBase + '/api/v1/health', { signal: AbortSignal.timeout(1000) })).ok) { ready = true; break; } } catch {}
  await new Promise(resolve => setTimeout(resolve, 200));
}
if (!ready) { api.kill(); throw new Error('Preview API not ready'); }
const server = createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === identity.bootstrap_path) {
      const response = await fetch(apiBase + '/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: identity.username, password: identity.password, school_id: identity.school_id, account_type: 'general' }) });
      if (!response.ok) throw new Error('Preview login failed');
      const tokens = await response.json();
      const me = await fetch(apiBase + '/api/v1/auth/me', { headers: { Authorization: `Bearer ${tokens.access_token}` } });
      if (!me.ok) throw new Error('Preview identity failed');
      const user = await me.json();
      const safeJson = value => JSON.stringify(value).replace(/</g, '\\u003c');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' });
      res.end(`<!doctype html><meta charset="utf-8"><title>阳江一中师生档案</title><p>正在打开档案…</p><script>sessionStorage.setItem('refresh_token',${safeJson(tokens.refresh_token)});sessionStorage.setItem('user_info',${safeJson(JSON.stringify(user))});location.replace('/admin/school?tab=teachers');</script>`);
      return;
    }
    if (req.url.startsWith('/api/')) {
      const chunks = []; let size = 0;
      for await (const chunk of req) { size += chunk.length; if (size > 25_000_000) { res.writeHead(413); res.end(); return; } chunks.push(chunk); }
      const result = await fetch(apiBase + req.url, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks), signal: AbortSignal.timeout(300000) });
      const headers = { 'Content-Type': result.headers.get('Content-Type') || 'application/json', 'Cache-Control': 'no-store' };
      for (const key of ['Content-Disposition', 'X-Error-Code']) if (result.headers.has(key)) headers[key] = result.headers.get(key);
      res.writeHead(result.status, headers); res.end(Buffer.from(await result.arrayBuffer())); return;
    }
    const file = path.resolve(dist, '.' + decodeURIComponent(req.url.split('?')[0]));
    if (file !== dist && !file.startsWith(dist + path.sep)) { res.writeHead(403); res.end(); return; }
    let content, ext;
    try { content = await readFile(file); ext = path.extname(file); }
    catch { content = await readFile(path.join(dist, 'index.html')); ext = '.html'; }
    res.writeHead(200, { 'Content-Type': ({ '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' })[ext] || 'application/octet-stream' }); res.end(content);
  } catch { res.writeHead(502); res.end('预览请求暂时失败，请重试。'); }
});
try {
  await new Promise((resolve, reject) => { server.on('error', reject); server.listen(Number(process.env.ROSTER_PREVIEW_PORT || 61564), '127.0.0.1', resolve); });
} catch (error) { api.kill('SIGTERM'); throw error; }
const baseUrl = `http://127.0.0.1:${server.address().port}`;
await writeFile(path.join(scratch, 'status.json'), JSON.stringify({ pid: process.pid, apiPid: api.pid, apiBase, baseUrl, schoolId: identity.school_id, ready: true, model: env.DEEPSEEK_MODEL }), { mode: 0o600 });
console.log('阳江一中 preview ready at ' + baseUrl + '/admin/school?tab=teachers; model=' + env.DEEPSEEK_MODEL);
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => { server.closeAllConnections(); server.close(); api.kill('SIGTERM'); setTimeout(() => process.exit(0), 1000); });

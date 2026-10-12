/** Isolated real API/browser acceptance. Use a disposable database via QA_R79_DATABASE_URL. */
import { spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createServer } from 'node:http'
import { mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const database = process.env.QA_R79_DATABASE_URL
if (!database || !database.includes('teacher_r79_browser')) throw new Error('Explicit disposable teacher_r79_browser database required')
const scratch = await mkdtemp(path.join(tmpdir(), 'teacher-r79-browser-'))
const credential = randomBytes(32).toString('base64url')
const env = { ...process.env, APP_ENV: 'test', MODEL_PROVIDER: 'fake', DATABASE_URL: database, PYTHONPATH: path.join(root, 'apps/api'), LOG_FILE: path.join(scratch, 'api.log'), SECRET_KEY: randomBytes(48).toString('hex'), JWT_SECRET_KEY: randomBytes(48).toString('hex'), RATE_LIMIT_PER_MINUTE: '3000' }
const python = path.join(root, '.venv/bin/python')
const run = (command, args, options = {}) => new Promise((resolve, reject) => {
  const child = spawn(command, args, { cwd: scratch, env, stdio: ['pipe', 'pipe', 'pipe'], ...options })
  let output = ''
  child.stdout.on('data', chunk => { output += chunk })
  child.stderr.on('data', chunk => { output += chunk })
  child.on('error', reject)
  child.on('exit', code => code === 0 ? resolve(output) : reject(new Error(output.replaceAll(credential, '[redacted]'))))
  child.stdin.end(options.input || '')
})
const fixture = await run(python, [path.join(root, 'tests/alignment/seed.py')], { input: credential })
const fixturePath = path.join(scratch, 'fixtures.json')
await writeFile(fixturePath, fixture)
const dist = path.join(scratch, 'web')
const config = path.join(scratch, 'vite.config.mjs')
await writeFile(config, `import react from ${JSON.stringify(path.join(root, 'apps/web/node_modules/@vitejs/plugin-react/dist/index.js'))}; export default {root:${JSON.stringify(path.join(root, 'apps/web'))},envDir:${JSON.stringify(scratch)},plugins:[react()],define:{'import.meta.env.VITE_API_URL':JSON.stringify('/api/v1')},build:{outDir:${JSON.stringify(dist)},emptyOutDir:true}}`)
await run(process.execPath, [path.join(root, 'apps/web/node_modules/vite/bin/vite.js'), 'build', '--config', config])
const api = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8039', '--no-access-log'], { cwd: scratch, env, stdio: ['ignore', 'ignore', 'pipe'] })
let apiOutput = ''
api.stderr.on('data', data => { apiOutput += data })
const server = createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      const chunks = []
      for await (const chunk of req) chunks.push(chunk)
      const result = await fetch('http://127.0.0.1:8039' + req.url, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks) })
      const headers = { 'content-type': result.headers.get('content-type') || 'application/json' }
      const cookies = result.headers.getSetCookie()
      if (cookies.length) headers['set-cookie'] = cookies
      res.writeHead(result.status, headers); res.end(Buffer.from(await result.arrayBuffer())); return
    }
    const file = path.resolve(dist, '.' + decodeURIComponent(req.url.split('?')[0]))
    if (!file.startsWith(dist + path.sep) && file !== dist) { res.writeHead(403); res.end(); return }
    let content, extension
    try { content = await readFile(file); extension = path.extname(file) } catch { content = await readFile(path.join(dist, 'index.html')); extension = '.html' }
    res.writeHead(200, { 'content-type': { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }[extension] || 'application/octet-stream' }); res.end(content)
  } catch { res.writeHead(502); res.end('Isolated test proxy unavailable') }
})
try {
  let ready = false
  for (let i = 0; i < 30; i++) {
    try { if ((await fetch('http://127.0.0.1:8039/api/v1/health', { signal: AbortSignal.timeout(1000) })).ok) { ready = true; break } } catch { /* Startup pending. */ }
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  if (!ready) throw new Error(apiOutput)
  await new Promise((resolve, reject) => { server.on('error', reject); server.listen(5219, '127.0.0.1', resolve) })
  process.stdout.write(`Artifacts: ${scratch}\n`)
  process.stdout.write(await run(process.execPath, [path.join(root, 'node_modules/@playwright/test/cli.js'), 'test', '--config', path.join(root, 'tests/education/playwright.config.ts'), 'teacher-r79.spec.ts'], { env: { ...env, QA_PASSWORD: credential, QA_FIXTURE_PATH: fixturePath, QA_BASE_URL: 'http://127.0.0.1:5219', QA_OUTPUT_DIR: path.join(scratch, 'results') } }))
} catch (error) { process.stdout.write(error.message.replaceAll(credential, '[redacted]') + '\n'); process.exitCode = 1 }
finally { server.closeAllConnections(); server.close(); api.kill('SIGTERM') }

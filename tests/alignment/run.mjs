/** Run only against the isolated QA database named qa_alignment. No .env loading. */
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { randomBytes } from 'node:crypto'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const scratch = await mkdtemp(path.join(tmpdir(), 'alignment-browser-'))
const python = path.join(root, '.venv/bin/python')
const credential = randomBytes(32).toString('base64url')
const env = { ...process.env, APP_ENV: 'test', MODEL_PROVIDER: 'fake', DATABASE_URL: 'postgresql+asyncpg://qa_alignment@127.0.0.1:55439/qa_alignment', LOG_FILE: path.join(scratch, 'api.log'), PYTHONPATH: path.join(root, 'apps/api'), JWT_SECRET_KEY: randomBytes(48).toString('hex'), SECRET_KEY: randomBytes(48).toString('hex'), RATE_LIMIT_PER_MINUTE: '2000', RATE_LIMIT_PER_HOUR: '20000' }

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: scratch, env, stdio: ['pipe', 'pipe', 'pipe'], ...options })
    let out = ''
    child.stdout.on('data', data => { out += data })
    child.stderr.on('data', () => {}) // Never echo request/credential-bearing logs.
    child.on('error', reject)
    child.on('exit', code => code === 0 ? resolve(out) : reject(Object.assign(new Error(`QA subprocess failed (${code})`), { output: out.replaceAll(credential, '[redacted]') })))
    child.stdin.end(options.input || '')
  })
}
const fixture = await run(python, [path.join(root, 'tests/alignment/seed.py')], { input: credential })
const fixturePath = path.join(scratch, 'fixtures.json')
await writeFile(fixturePath, fixture)
const api = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8018', '--workers', '2', '--no-access-log'], { cwd: scratch, env, stdio: 'ignore' })
let ready = false
for (let i = 0; i < 60; i++) {
  try { if ((await fetch('http://127.0.0.1:8018/api/v1/health')).ok) { ready = true; break } } catch {}
  await new Promise(resolve => setTimeout(resolve, 250))
}
if (!ready) { api.kill(); throw new Error('Isolated API did not become ready') }
const dist = path.join(root, 'apps/web/dist')
const server = createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      const chunks = []
      for await (const chunk of req) chunks.push(chunk)
      const result = await fetch('http://127.0.0.1:8018' + req.url, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks) })
      res.writeHead(result.status, { 'content-type': result.headers.get('content-type') || 'application/json' })
      res.end(Buffer.from(await result.arrayBuffer()))
      return
    }
    const urlPath = decodeURIComponent(req.url.split('?')[0])
    const file = path.resolve(dist, '.' + urlPath)
    if (!file.startsWith(dist + path.sep) && file !== dist) { res.writeHead(403); res.end(); return }
    let content, ext
    try { content = await readFile(file); ext = path.extname(file) } catch { content = await readFile(path.join(dist, 'index.html')); ext = '.html' }
    res.writeHead(200, { 'content-type': ({ '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' })[ext] || 'application/octet-stream' })
    res.end(content)
  } catch { res.writeHead(502); res.end('Isolated QA proxy failed') }
})
await new Promise(resolve => server.listen(5198, '127.0.0.1', resolve))
try {
  const output = await run(process.execPath, [path.join(root, 'node_modules/@playwright/test/cli.js'), 'test', '--config', path.join(root, 'tests/alignment/playwright.config.ts')], { env: { ...env, QA_PASSWORD: credential, QA_FIXTURE_PATH: fixturePath, QA_OUTPUT_DIR: path.join(scratch, 'results') } })
  process.stdout.write(output)
} catch (error) {
  process.stdout.write(error.output || error.message)
  process.exitCode = 1
} finally {
  server.closeAllConnections(); server.close(); api.kill('SIGTERM')
  process.stdout.write(`QA artifact directory: ${scratch}\n`)
}

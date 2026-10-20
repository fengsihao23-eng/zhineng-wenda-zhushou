/** Disposable PostgreSQL + actual FastAPI + production web build for WeChat acceptance. */
import { spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createServer } from 'node:http'
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const database=process.env.QA_WECHAT_DATABASE_URL
if(!database || !database.includes('exam_v17_browser'))throw new Error('Explicit disposable exam_v17_browser PostgreSQL database required')
const output=process.env.QA_WECHAT_OUTPUT || await mkdtemp(path.join(root,'.local/wechat-mini-'))
await mkdir(output,{recursive:true,mode:0o700})
const password=randomBytes(24).toString('base64url')
const env={...process.env,APP_ENV:'test',MODEL_PROVIDER:'fake',DATABASE_URL:database,PYTHONPATH:path.join(root,'apps/api'),
  LOG_FILE:path.join(output,'api.log'),SECRET_KEY:randomBytes(48).toString('hex'),JWT_SECRET_KEY:randomBytes(48).toString('hex'),
  RATE_LIMIT_PER_MINUTE:'3000',RATE_LIMIT_PER_HOUR:'30000'}
const python=path.join(root,'.venv/bin/python')
function run(command,args,options={}){return new Promise((resolve,reject)=>{
  const process=spawn(command,args,{cwd:output,env,stdio:['pipe','pipe','pipe'],...options})
  let text='';process.stdout.on('data',d=>text+=d);process.stderr.on('data',d=>text+=d)
  process.on('error',reject);process.on('exit',code=>code===0?resolve(text):reject(new Error(text.replaceAll(password,'[redacted]'))))
  process.stdin.end(options.input||'')
})}
await run(python,['-m','alembic','upgrade','head'],{cwd:path.join(root,'apps/api')})
const fixture=JSON.parse(await run(python,[path.join(root,'tests/education/seed-exam.py')],{input:password}))
const file=path.join(output,'fixtures.json')
await writeFile(file,JSON.stringify({...fixture,password}),{mode:0o600})
const config=path.join(output,'vite.config.mjs'),dist=path.join(output,'web')
await writeFile(config,`import react from ${JSON.stringify(path.join(root,'apps/web/node_modules/@vitejs/plugin-react/dist/index.js'))};export default {root:${JSON.stringify(path.join(root,'apps/web'))},envDir:${JSON.stringify(output)},plugins:[react()],define:{'import.meta.env.VITE_API_URL':JSON.stringify('/api/v1')},build:{outDir:${JSON.stringify(dist)},emptyOutDir:true}}`)
await run(process.execPath,[path.join(root,'apps/web/node_modules/vite/bin/vite.js'),'build','--config',config])
const api=spawn(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8048','--no-access-log'],{cwd:output,env,stdio:['ignore','ignore','pipe']})
let stderr='';api.stderr.on('data',d=>stderr+=d)
let ready=false
for(let i=0;i<60;i++){
  try{if((await fetch('http://127.0.0.1:8048/api/v1/health',{signal:AbortSignal.timeout(1000)})).ok){ready=true;break}}catch{}
  await new Promise(resolve=>setTimeout(resolve,200))
}
if(!ready){api.kill();throw new Error(stderr)}
const server=createServer(async(req,res)=>{
  try{
    if(req.url.startsWith('/api/')){
      const chunks=[];for await(const chunk of req)chunks.push(chunk)
      const response=await fetch('http://127.0.0.1:8048'+req.url,{method:req.method,headers:req.headers,body:['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks)})
      const headers={'content-type':response.headers.get('content-type')||'application/json'}
      for(const name of ['content-disposition','x-exam-preview-hash','x-error-code'])if(response.headers.get(name))headers[name]=response.headers.get(name)
      res.writeHead(response.status,headers);res.end(Buffer.from(await response.arrayBuffer()));return
    }
    const target=path.resolve(dist,'.'+decodeURIComponent(req.url.split('?')[0]))
    if(!target.startsWith(dist+path.sep) && target!==dist){res.writeHead(403);res.end();return}
    let bytes,extension
    try{bytes=await readFile(target);extension=path.extname(target)}catch{bytes=await readFile(path.join(dist,'index.html'));extension='.html'}
    res.writeHead(200,{'content-type':{'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'}[extension]||'application/octet-stream'});res.end(bytes)
  }catch{res.writeHead(502);res.end('Isolated test proxy unavailable')}
})
await new Promise((resolve,reject)=>{server.on('error',reject);server.listen(5230,'127.0.0.1',resolve)})
await writeFile(path.join(output,'ready.json'),JSON.stringify({fixturePath:file,web:'http://127.0.0.1:5230',api:'http://127.0.0.1:8048',model:'fake',database:'disposable'}),{mode:0o600})
console.log('WeChat acceptance backend ready. Artifacts: '+output)
const stop=()=>{server.closeAllConnections();server.close();api.kill('SIGTERM');process.exit(0)}
process.on('SIGTERM',stop);process.on('SIGINT',stop)

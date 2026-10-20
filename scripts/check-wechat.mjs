#!/usr/bin/env node
import { readFile, readdir, stat } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const folder=path.join(root,'apps/miniprogram')
const require=createRequire(import.meta.url)
const config=require(path.join(folder,'config.js'))
const project=JSON.parse(await readFile(path.join(folder,'project.config.json'),'utf8'))
const app=JSON.parse(await readFile(path.join(folder,'app.json'),'utf8'))
let files=0,bytes=0
async function walk(dir){
  for(const name of await readdir(dir)){
    if(name==='project.private.config.json')continue
    const file=path.join(dir,name),info=await stat(file)
    if(info.isDirectory()){await walk(file);continue}
    files++;bytes+=info.size
    if(name.endsWith('.json'))JSON.parse(await readFile(file,'utf8'))
    if(name.endsWith('.js')){
      const result=spawnSync(process.execPath,['--check',file],{encoding:'utf8'})
      if(result.status)throw new Error(result.stderr)
    }
    if(name.endsWith('.wxml') && /<web-view\b/.test(await readFile(file,'utf8')))throw new Error('小程序需使用原生页面，禁止网页套壳')
  }
}
await walk(folder)
for(const page of app.pages)for(const extension of ['js','json','wxml'])await stat(path.join(folder,page+'.'+extension))
if(process.argv.includes('--release')){
  if(!/^wx[0-9a-f]{16}$/.test(project.appid))throw new Error('尚未配置正式小程序 AppID')
  const url=new URL(config.apiBaseUrl)
  if(url.protocol!=='https:' || /^(localhost|127\.|0\.0\.0\.0)/.test(url.hostname))throw new Error('尚未配置正式 HTTPS 后端域名')
  let local
  try{local=JSON.parse(await readFile(path.join(folder,'project.private.config.json'),'utf8'))}catch(error){if(error.code!=='ENOENT')throw error}
  if(project.setting.urlCheck===false || local?.setting?.urlCheck===false)throw new Error('上线前需开启合法域名校验')
}
console.log(`小程序静态检查通过：${app.pages.length} 个原生页面，${files} 个文件，${Math.ceil(bytes/1024)} KB。`)

#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const project = path.join(root, 'apps/miniprogram')
const args = process.argv.slice(2)
const value = flag => args.includes(flag) ? args[args.indexOf(flag)+1] : undefined
const api = value('--api'), appid = value('--appid')
if (!api && !appid) throw new Error('用法：npm run mini:configure -- --api https://你的域名/api/v1 --appid wx…；本地联调可加 --local')
if (api) {
  const url = new URL(api)
  const local = args.includes('--local')
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname.replace(/\/$/,'') !== '/api/v1') throw new Error('接口地址需为 https://域名/api/v1，不含用户名、密码或查询参数')
  if (!local && (url.protocol !== 'https:' || /^(localhost|127\.|0\.0\.0\.0)/.test(url.hostname))) throw new Error('正式接口必须使用 HTTPS 域名；仅本地联调可使用 --local')
  await writeFile(path.join(project, 'config.js'), '// Public API origin; never place API keys or AppSecret here.\nmodule.exports = '+JSON.stringify({apiBaseUrl:url.href.replace(/\/$/,'')},null,2)+';\n')
}
if (appid) {
  if (!/^wx[0-9a-f]{16}$/.test(appid)) throw new Error('AppID 格式应为 wx 开头的18位小程序 AppID')
  const filename = path.join(project, 'project.config.json')
  const config = JSON.parse(await readFile(filename,'utf8')); config.appid=appid
  await writeFile(filename, JSON.stringify(config,null,2)+'\n')
}
if (args.includes('--local')) {
  await writeFile(path.join(project,'project.private.config.json'),JSON.stringify({setting:{urlCheck:false}},null,2)+'\n')
} else {
  // Disabling local domain checks must never silently carry into launch preparation.
  const filename=path.join(project,'project.private.config.json')
  let config
  try { config=JSON.parse(await readFile(filename,'utf8')) } catch (error) { if(error.code!=='ENOENT')throw error }
  if(config){ config.setting={...config.setting,urlCheck:true};await writeFile(filename,JSON.stringify(config,null,2)+'\n') }
}
console.log('微信小程序配置已更新：'+project)

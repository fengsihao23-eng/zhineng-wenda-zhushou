/** Run the shipped Page/API modules against a real server when GUI access is unavailable.
 * Only WeChat device APIs are adapted. No auth, business responses or database are mocked.
 * This is not a replacement for the developer-tool rendering gate.
 */
import vm from 'node:vm'
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../apps/miniprogram')
export async function nativeRuntime(output){
  await mkdir(output,{recursive:true,mode:0o700})
  const storage=new Map(),modules=new Map(),toasts=[],opened=[],requests=[]
  let definition,drop=null,hold=null
  const wx={
    getStorageSync:key=>storage.get(key),setStorageSync:(key,value)=>storage.set(key,structuredClone(value)),removeStorageSync:key=>storage.delete(key),
    getAccountInfoSync:()=>({miniProgram:{envVersion:'develop'}}),setNavigationBarTitle:()=>{},showToast:options=>toasts.push(options.title),stopPullDownRefresh:()=>{},
    showModal:options=>options.success({confirm:true}),
    getFileSystemManager:()=>({unlinkSync,unlink:({filePath,fail})=>{try{unlinkSync(filePath)}catch{fail?.()}}}),
    openDocument:options=>{const bytes=readFileSync(options.filePath);if(!bytes.subarray(0,5).equals(Buffer.from('%PDF-')))throw new Error('Expected actual PDF');opened.push(bytes);options.success({})},
    request:async options=>{
      const entry={path:new URL(options.url).pathname,method:options.method,key:options.header['Idempotency-Key']};requests.push(entry)
      try{
        const response=await fetch(options.url,{method:options.method,headers:options.header,body:['GET','HEAD'].includes(options.method)?undefined:JSON.stringify(options.data),signal:AbortSignal.timeout(options.timeout)})
        const text=await response.text(),data=text?JSON.parse(text):undefined
        if(hold && entry.path.endsWith(hold.suffix)){
          const gate=hold;hold=null;gate.enter();await gate.wait;
        }
        if(drop && entry.path.endsWith(drop) && response.ok){drop=null;options.fail({errMsg:'synthetic lost response after server commit'});return}
        options.success({statusCode:response.status,data,header:Object.fromEntries(response.headers.entries())})
      }catch(error){options.fail({errMsg:error.message})}
    },
    downloadFile:async options=>{
      try{
        const response=await fetch(options.url,{headers:options.header,signal:AbortSignal.timeout(options.timeout)})
        const file=path.join(output,randomUUID());await writeFile(file,Buffer.from(await response.arrayBuffer()))
        options.success({statusCode:response.status,tempFilePath:file})
      }catch(error){options.fail({errMsg:error.message})}
    }
  }
  const sandbox=vm.createContext({wx,console,Promise,ArrayBuffer,Uint8Array,setInterval,clearInterval,setTimeout,clearTimeout,Page:value=>{definition=value}})
  function load(filename){
    let absolute=path.resolve(filename);if(!absolute.endsWith('.js'))absolute+='.js'
    if(modules.has(absolute))return modules.get(absolute).exports
    const module={exports:{}};modules.set(absolute,module)
    const code=readFileSync(absolute,'utf8')
    const fn=vm.runInContext('(function(require,module,exports){\n'+code+'\n})',sandbox,{filename:absolute})
    fn(p=>load(path.resolve(path.dirname(absolute),p)),module,module.exports)
    return module.exports
  }
  load(path.join(root,'pages/workbench/index.js'))
  const page={...definition,data:structuredClone(definition.data),setData(patch){
    for(const [key,value]of Object.entries(patch)){
      const pieces=key.split('.');let node=this.data
      for(const piece of pieces.slice(0,-1)){if(!node[piece])node[piece]={};node=node[piece]}
      node[pieces.at(-1)]=value
    }
  }}
  const wxml=readFileSync(path.join(root,'pages/workbench/index.wxml'),'utf8')
  for(const match of wxml.matchAll(/(?:bind\w*|catch\w*)="(\w+)"/g))if(typeof page[match[1]]!=='function')throw new Error('Unbound WXML handler: '+match[1])
  page.onLoad();page._active=true;await page.resume()
  return {page,api:load(path.join(root,'utils/api.js')),storage,toasts,opened,requests,dropNext:suffix=>{drop=suffix},
    holdNext:suffix=>{
      let release,enter;const wait=new Promise(resolve=>{release=resolve}),entered=new Promise(resolve=>{enter=resolve});
      hold={suffix,wait,enter};return {release,entered};
    },close:()=>page.onUnload()}
}

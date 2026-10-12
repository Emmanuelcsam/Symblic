// Synthetic metadata/attachments and static source only; never runs a program or model.
import nodeTest,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import http from 'node:http';
import {once} from 'node:events';
import {HOST_ONLY_REASON} from './host-harness.mjs';
// The host's preview harness (_journey.mjs: a static preview server of the host checkout) is not part of this
// repository; without it every journey below is registered as skipped.
let journey=null;
try{journey=await import('./_journey.mjs');}catch(error){if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;}
const {startPreview,launch,installFixtures,axePath}=journey||{};
const test=journey?nodeTest:(name)=>nodeTest(name,{skip:HOST_ONLY_REASON},()=>{});
let browser,preview,staticPreview,attachmentServer,attachmentRequests=[];
before(async()=>{
 if(!journey)return;
 staticPreview=await startPreview();
 // Chromium downloads use the browser network service. Serve synthetic bytes
 // over real loopback HTTP, rather than fulfilling an intercepted navigation.
 // Everything else is either mocked below or proxied to the inert static preview.
 attachmentServer=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  if(url.pathname===API+'examples/artifact'){
   const name=url.searchParams.get('name');
   attachmentRequests.push({id:url.searchParams.get('id'),name,method:req.method});
   if(req.method!=='GET'||url.searchParams.get('id')!==id||!['bundle.zip',...listing.bundles[0].files.map(f=>f.name)].includes(name)){
    res.writeHead(404);res.end();return;
   }
   const bytes=name==='bundle.zip'?zipPayload:payload;
   res.writeHead(200,{'Content-Type':name==='bundle.zip'?'application/zip':'application/octet-stream','Content-Length':bytes.length,
    'Content-Disposition':'attachment; filename="'+(name==='bundle.zip'?id+'.zip':name)+'"','X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'});
   res.end(bytes);return;
  }
  if(!['GET','HEAD'].includes(req.method)||url.pathname.startsWith('/api/')){res.writeHead(404);res.end();return;}
  const upstream=http.request(new URL(req.url,staticPreview.base),{method:req.method},reply=>{
   res.writeHead(reply.statusCode,reply.headers);reply.pipe(res);
  });
  upstream.on('error',()=>{res.writeHead(502);res.end();});upstream.end();
 });
 attachmentServer.listen(0,'127.0.0.1');await once(attachmentServer,'listening');
 preview={base:'http://127.0.0.1:'+attachmentServer.address().port};browser=await launch();
});
after(async()=>{await browser?.close();if(attachmentServer){attachmentServer.closeAllConnections();await new Promise(resolve=>attachmentServer.close(resolve));}await staticPreview?.stop();});
const API='/api/automation/symblic/',id='fixture-checked-build';
const payload=Buffer.from('solid synthetic_fixture\nendsolid synthetic_fixture\n');
const hash=crypto.createHash('sha256').update(payload).digest('hex');
const zipPayload=Buffer.from('UEsDBBQAAAAAAAAAISh2l2lRMwAAADMAAAAOAAAAdGFyZ2V0LWN1cC5zdGxzb2xpZCBzeW50aGV0aWNfZml4dHVyZQplbmRzb2xpZCBzeW50aGV0aWNfZml4dHVyZQpQSwMEFAAAAAAAAAAhKHaXaVEzAAAAMwAAAAkAAABjaGFydC5zdmdzb2xpZCBzeW50aGV0aWNfZml4dHVyZQplbmRzb2xpZCBzeW50aGV0aWNfZml4dHVyZQpQSwMEFAAAAAAAAAAhKHaXaVEzAAAAMwAAAAkAAAB2ZXJpZnkucHlzb2xpZCBzeW50aGV0aWNfZml4dHVyZQplbmRzb2xpZCBzeW50aGV0aWNfZml4dHVyZQpQSwMEFAAAAAAAAAAhKHaXaVEzAAAAMwAAAA0AAABldmlkZW5jZS5qc29uc29saWQgc3ludGhldGljX2ZpeHR1cmUKZW5kc29saWQgc3ludGhldGljX2ZpeHR1cmUKUEsBAhQDFAAAAAAAAAAhKHaXaVEzAAAAMwAAAA4AAAAAAAAAAAAAAIABAAAAAHRhcmdldC1jdXAuc3RsUEsBAhQDFAAAAAAAAAAhKHaXaVEzAAAAMwAAAAkAAAAAAAAAAAAAAIABXwAAAGNoYXJ0LnN2Z1BLAQIUAxQAAAAAAAAAISh2l2lRMwAAADMAAAAJAAAAAAAAAAAAAACAAbkAAAB2ZXJpZnkucHlQSwECFAMUAAAAAAAAACEodpdpUTMAAAAzAAAADQAAAAAAAAAAAAAAgAETAQAAZXZpZGVuY2UuanNvblBLBQYAAAAABAAEAOUAAABxAQAAAAA=','base64');
const listing={bundles:[{id,title:'Checked <example> & artifacts',examples:['synthetic.sym'],download_url:'https://invalid.example/ignored',files:[
 {name:'target-cup.stl',bytes:payload.length,sha256:hash,url:'https://invalid.example/ignored'},
 {name:'chart.svg',bytes:payload.length,sha256:hash,url:'https://invalid.example/ignored'},
 {name:'verify.py',bytes:payload.length,sha256:hash,url:'https://invalid.example/ignored'},
 {name:'evidence.json',bytes:payload.length,sha256:hash,url:'https://invalid.example/ignored'},
]}]};
async function fixture({mobile=false,theme='light',status=200,body=listing}={}){
 const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1280,height:800},isMobile:mobile,hasTouch:mobile,serviceWorkers:'block',acceptDownloads:true});
 const f=await installFixtures(context,preview.base,{empty:true,theme});
 const control={status,body},reads=[],downloads=[],errors=[],failed=[];
 attachmentRequests=downloads;
 await context.route(preview.base+API+'editor/check',r=>{
  const p=r.request().postDataJSON();return r.fulfill({json:{version:1,language:p.language,source_length_utf16:p.source.length,available:true,diagnostics:[],check:{ok:true,name:'Synthetic fixture',errors:[],warnings:[],plan:[],inputs:[]}}});
 });
 await context.route(preview.base+API+'meta',r=>r.fulfill({json:{examples:[],features:{}}}));
 await context.route(preview.base+API+'programs',r=>r.fulfill({json:{programs:[]}}));
 await context.route(preview.base+API+'runs',r=>r.fulfill({json:{runs:[]}}));
 await context.route(preview.base+API+'examples/artifacts',r=>{reads.push(r.request().method());return r.fulfill({status:control.status,json:control.body});});
 await context.route(preview.base+API+'examples/artifact?*',r=>r.continue());
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 page.on('requestfailed',r=>failed.push({url:r.url(),error:r.failure()?.errorText}));
 await page.goto(preview.base+'/automation-studio/symblic.html#write');
 await page.locator('#sySrc').waitFor();await page.waitForTimeout(150);
 return {context,page,reads,downloads,errors,failed,control,...f};
}
async function expand(page){await page.getByText('Checked example downloads',{exact:true}).click();}
for(const mobile of [false,true])for(const theme of ['light','dark'])
test(`Symblic checked attachments stay local, preserve editor, and support keyboard ${mobile?'phone':'desktop'} ${theme}`,async()=>{
 const f=await fixture({mobile,theme});
 try{
  const source=await f.page.locator('#sySrc').inputValue();assert.deepEqual(f.reads,[],'collapsed listing does not fetch');
  const summary=f.page.locator('#syExampleDownloads > summary');await summary.focus();await f.page.keyboard.press('Enter');
  await f.page.getByRole('heading',{name:listing.bundles[0].title,exact:true}).waitFor();
  assert.deepEqual(f.reads,['GET']);assert.equal(await f.page.locator('#syExampleDownloadList img').count(),0);
  const links=f.page.locator('#syExampleDownloadList a');assert.equal(await links.count(),5);
  for(const link of await links.all())assert.equal(new URL(await link.getAttribute('href'),preview.base).origin,preview.base);
  for(const name of ['target-cup.stl','Download complete bundle (ZIP)']){
   const pending=f.page.waitForEvent('download');await f.page.getByRole('link',{name,exact:true}).click();const download=await pending;
   assert.equal(download.suggestedFilename(),name==='target-cup.stl'?name:id+'.zip');
   assert.equal(await download.failure(),null,JSON.stringify({url:download.url(),requests:f.downloads,failed:f.failed}));
   assert.equal(crypto.createHash('sha256').update(await fs.readFile(await download.path())).digest('hex'),crypto.createHash('sha256').update(name==='target-cup.stl'?payload:zipPayload).digest('hex'));
  }
  assert.deepEqual(f.downloads,[{id,name:'target-cup.stl',method:'GET'},{id,name:'bundle.zip',method:'GET'}]);
  assert.equal(await f.page.locator('#sySrc').inputValue(),source);
  await f.page.addScriptTag({path:axePath()});
  const bad=await f.page.evaluate(async()=> (await axe.run()).violations.filter(v=>['critical','serious'].includes(v.impact)).map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})));
  assert.deepEqual(bad,[]);assert.equal(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(f.requests.filter(r=>r.method!=='GET'&&!['/api/perf/beacon',API+'editor/check'].includes(r.path)),[]);
  assert.deepEqual(f.errors,[]);assert.deepEqual(f.failed,[]);assert.deepEqual(f.blocked,[]);
 }finally{await f.context.close();}
});
test('Symblic missing checked-download API stays usable and retries explicitly',async()=>{
 const f=await fixture({status:404,body:{error:'Synthetic endpoint unavailable'}});
 try{
  await expand(f.page);await f.page.getByRole('button',{name:'Retry downloads',exact:true}).waitFor();
  assert.equal(await f.page.locator('#sySrc').isEditable(),true);assert.deepEqual(f.reads,['GET']);
  f.control.status=200;f.control.body=listing;
  await f.page.getByRole('button',{name:'Retry downloads',exact:true}).click();
  await f.page.getByRole('link',{name:'target-cup.stl',exact:true}).waitFor();assert.deepEqual(f.reads,['GET','GET']);
  assert.deepEqual(f.errors,[]);assert.deepEqual(f.blocked,[]);
 }finally{await f.context.close();}
});
test('Symblic malformed artifact names never become download links',async()=>{
 const invalid=structuredClone(listing);invalid.bundles[0].files[0].name='../private.json';
 const f=await fixture({body:invalid});
 try{
  await expand(f.page);await f.page.getByRole('button',{name:'Retry downloads',exact:true}).waitFor();
  assert.equal(await f.page.locator('#syExampleDownloadList a').count(),0);assert.deepEqual(f.downloads,[]);
  assert.deepEqual(f.errors,[]);assert.deepEqual(f.blocked,[]);
 }finally{await f.context.close();}
});

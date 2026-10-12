// Real frozen artifacts and native run preparation; isolated stores, fake launch only.
import {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import readline from 'node:readline';
import path from 'node:path';
import {test, launch,open,noHorizontalScroll,axe,root} from './host-harness.mjs';
let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
function fixture({loseNativeReply=false}={}){
  const child=spawn(process.env.TEST_PYTHON||'python3',[path.join(root,'tests/browser/forge_fixture.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
  const queue=[],sent=[];let stderr='';child.stderr.on('data',chunk=>stderr+=chunk);
  readline.createInterface({input:child.stdout}).on('line',line=>queue.shift()?.resolve(JSON.parse(line)));
  child.on('exit',code=>queue.splice(0).forEach(p=>p.reject(new Error('Fixture exited '+code+': '+stderr))));
  const call=request=>new Promise((resolve,reject)=>{queue.push({resolve,reject});child.stdin.write(JSON.stringify(request)+'\n');});
  return {sent,close(){child.stdin.end();},async api(req,url){
    let route;
    if(url.pathname.startsWith('/api/symblic-forge/'))route=url.pathname.slice('/api/symblic-forge/'.length);
    else if(url.pathname.startsWith('/api/automation/symblic/forge/'))route='native/'+url.pathname.slice('/api/automation/symblic/forge/'.length);
    else return {json:{}};
    const request={method:req.method(),route,query:Object.fromEntries(url.searchParams)};
    if(request.method==='POST'){request.body=req.postDataJSON();sent.push(request);}
    const result=await call(request);
    if(loseNativeReply&&route==='native/run'){loseNativeReply=false;return {abort:true};}
    return result;
  }};
}

for(const mobile of [false,true])for(const dark of [false,true])test(`frozen Forge native import · ${mobile?'phone touch':'desktop'} · ${dark?'dark':'light'}`,async()=>{
  const f=fixture({loseNativeReply:mobile&&dark});const {page,context,errors}=await open(browser,'/symblic-forge.html',f.api,{mobile,
    storage:`window.WebSocket=class{close(){}};localStorage.setItem('night','${dark?'1':'0'}');localStorage.setItem('studioTheme','${dark?'dark':'light'}');`});
  try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);
    await page.getByRole('button',{name:'Project…',exact:true}).click();
    await page.getByRole('button',{name:'Load Snake demonstration',exact:true}).click();
    await page.getByRole('button',{name:'Confirm',exact:true}).click();
    await page.waitForFunction(()=>window.__forge.state.analysis?.counts.accepted>20);
    await page.evaluate(()=>window.__forge.command('/exports'));
    await page.getByRole('button',{name:'Freeze build handoff',exact:true}).click();
    await page.getByRole('button',{name:'Confirm',exact:true}).click();
    await page.getByRole('heading',{name:'Frozen build handoff',exact:true}).waitFor();
    await page.getByRole('button',{name:'Close',exact:true}).click();
    assert.equal(f.sent.filter(r=>r.route==='native/run').length,0);
    await page.getByRole('button',{name:'Run frozen plan in Symblic',exact:true}).click();
    await page.getByLabel('Local model',{exact:true}).waitFor();
    assert.equal(await page.getByLabel('Local model',{exact:true}).inputValue(),'');
    assert.equal(f.sent.filter(r=>r.route==='native/run').length,0);
    await page.getByLabel('Local model',{exact:true}).selectOption('ollama:qwen3:4b-instruct');
    await page.getByLabel('Maximum model calls',{exact:true}).fill('8');
    await page.getByText('Local model token and time limits',{exact:true}).click();
    await page.getByLabel('Reply token limit',{exact:true}).fill('1024');
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(await axe(page),[]);
    await page.getByRole('button',{name:'Start native run',exact:true}).click();
    await page.getByRole('heading',{name:'Native Symblic run receipt',exact:true}).waitFor();
    const link=page.getByRole('link',{name:'Open native Symblic run',exact:true});
    const href=await link.getAttribute('href');assert.match(href,/^\/symblic\?run=[a-f0-9]{12}$/);
    const launched=f.sent.filter(r=>r.route==='native/run');assert.equal(launched.length,1);
    assert.equal(launched[0].body.by,'ollama:qwen3:4b-instruct');assert.equal(launched[0].body.max_calls,8);
    assert.deepEqual(launched[0].body.ollama_limits,{num_predict:1024,num_ctx:8192,timeout_seconds:300,total_timeout_seconds:900});
    assert.match(launched[0].body.artifact_sha256,/^[a-f0-9]{64}$/);
    assert.equal(await page.evaluate(()=>window.__forge.state.pending),null);
    await page.reload();await page.waitForFunction(()=>window.__forge?.state.project);
    assert.equal(f.sent.filter(r=>r.route==='native/run').length,1,'Reload may only inspect receipts');
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

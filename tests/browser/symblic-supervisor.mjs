import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {test, launch, open, noHorizontalScroll, axe, available} from './host-harness.mjs';
let browser, screenshotDir;
before(async()=>{
  if (!available) return;            // every journey is skipped: create no screenshot folder
  screenshotDir = process.env.SUPERVISOR_SCREENSHOTS
    || await fs.mkdtemp(path.join(os.tmpdir(), 'symblic-supervisor-browser-'));
  await fs.mkdir(screenshotDir, {recursive:true});
  browser=await launch();
});
after(async()=>{await browser?.close();});
const HTML='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Supervisor fixture</title><link rel="stylesheet" href="/studio.css"><link rel="stylesheet" href="/automation-studio/symblic-supervisor.css"><body style="padding:16px"><main id="app"></main><script src="/automation-studio/symblic-supervisor.js"></script><script>SymblicSupervisor.render(document.getElementById("app"))</script></body></html>';
function fixture({loseStart=false}={}) {
  let row;
  const calls=[];
  const api=async(request,url)=>{
    const name=url.pathname.split('/').at(-1),body=request.method()==='POST'?request.postDataJSON():null;
    calls.push({name,body});
    if(name==='create') row={version:1,id:'w_0123456789abcdef01234567',revision:1,definition:body.definition,state:body.definition.state||{},frozen:{},events:[],jobs:[],paused:false,schedule:null,pulse:null};
    else if(name==='start') {
      if(!row.jobs.length) row.jobs.push({id:'f_fixture',status:'needs_attention',steps:{left:{status:'unknown',submission:{prompt:'identity'},error:'Native outcome unknown.'}}});
      row.revision++;
      if(loseStart) {loseStart=false;return{abort:true};}
    } else if(name==='view') {}
    else if(name==='simulate') return {json:{simulation:true,executed:false,steps:{left:{status:'unknown'}},notice:'Synthetic control-flow exercise only. No native execution.'}};
    else if(name==='pause') {row.paused=body.paused;row.revision++;}
    else if(name==='state') {assert.equal(body.revision,row.revision);Object.assign(row.state,body.changes);row.revision++;}
    else if(name==='schedule') {assert.equal(body.revision,row.revision);row.schedule={cron:body.cron,enabled:body.enabled,status:'installed'};row.revision++;}
    else if(name==='reconcile') {assert.equal(body.native_id,'0123456789ab');row.jobs[0].steps.left={status:'running',native_id:body.native_id};row.jobs[0].status='running';row.revision++;}
    else throw new Error('Unexpected API '+name);
    return {json:structuredClone(row)};
  };
  return {api,calls};
}
for(const mobile of [false,true]) test(`save, run, recover and persist (${mobile?'phone dark':'desktop light'})`,async()=>{
  const f=fixture();
  const {context,page,errors}=await open(browser,'/supervisor-fixture.html',f.api,{mobile,files:{'/supervisor-fixture.html':{body:HTML.replace('lang="en"','lang="en" data-theme="'+(mobile?'dark':'light')+'"'),contentType:'text/html'}}});
  try {
    await page.getByRole('button',{name:'Simulate control flow',exact:true}).click();
    await page.getByText('SIMULATION — no native execution',{exact:true}).waitFor();
    assert.equal(f.calls.some(c=>c.name==='start'),false);
    await page.getByRole('button',{name:'Save workflow',exact:true}).click();
    await page.getByRole('button',{name:'Run once',exact:true}).waitFor();
    assert.equal(f.calls.some(c=>c.name==='start'),false,'save never executes');
    await page.getByRole('button',{name:'Run once',exact:true}).click();
    await page.getByLabel('Native run ID for left').fill('0123456789ab');
    await page.getByRole('button',{name:'Reconcile left',exact:true}).click();
    await page.getByRole('link',{name:'Open native run'}).waitFor();
    assert.equal(await page.getByRole('link',{name:'Open native run'}).getAttribute('href'),'/runner/#run/0123456789ab');
    await page.getByText('Persistent owner state',{exact:true}).click();
    await page.getByLabel('State changes (JSON object)').fill('{"ready":true}');
    await page.getByRole('button',{name:'Save state changes',exact:true}).click();
    assert.equal(f.calls.at(-1).body.changes.ready,true);
    await page.getByText('Schedule with the host scheduler',{exact:true}).click();
    await page.getByLabel('Cron expression').fill('*/5 * * * *');
    await page.getByLabel('Enable scheduled firings').check();
    await page.getByRole('button',{name:'Save schedule',exact:true}).click();
    assert.equal(f.calls.at(-1).body.cron,'*/5 * * * *');
    await page.getByRole('button',{name:'Pause workflow',exact:true}).click();
    await page.getByRole('button',{name:'Resume workflow',exact:true}).waitFor();
    await page.reload();
    await page.getByRole('button',{name:'Resume workflow',exact:true}).waitFor();
    assert.equal(f.calls.filter(c=>c.name==='start').length,1,'reconnect never starts a firing');
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(errors,[]);
    assert.deepEqual(await axe(page),[]);
    if(mobile) await page.screenshot({path:path.join(screenshotDir,'phone-dark.png'),fullPage:true});
  } finally {await context.close();}
});
test('lost start reply retries the same identity and preserves unknown handle',async()=>{
  const f=fixture({loseStart:true});
  const {context,page,errors}=await open(browser,'/supervisor-fixture.html',f.api,{files:{'/supervisor-fixture.html':{body:HTML,contentType:'text/html'}}});
  try {
    await page.getByRole('button',{name:'Save workflow',exact:true}).click();
    await page.getByRole('button',{name:'Run once',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Connection lost'}).waitFor();
    await page.reload();
    await page.getByLabel('Native run ID for left').waitFor();
    await page.getByRole('button',{name:'Run once',exact:true}).click();
    await page.getByLabel('Native run ID for left').waitFor();
    const starts=f.calls.filter(c=>c.name==='start');
    assert.equal(starts.length,2);
    assert.equal(starts[0].body.request_id,starts[1].body.request_id);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});

// All API and static requests are intercepted. No live provider, worker, shell or dashboard.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
if (process.env.MICA_BROWSER_HARNESS) process.env.SYMBLIC_BROWSER_HARNESS = process.env.MICA_BROWSER_HARNESS;
const {test, launch, open, axe, noHorizontalScroll, root, available} = await import('./host-harness.mjs');
const here = process.env.MICA_UI_ROOT || path.join(root, 'web', 'hub');
const evidence = process.env.MICA_BROWSER_ARTIFACTS || path.join(os.tmpdir(), 'symblic-mica-browser-' + process.pid);
const API = '/api/automation/symblic/mica/';
const SAVED = 'symblic.construct.selection.v1';
const BUDGET = {max_calls:64,max_candidates:4,max_depth:4,max_units:64,max_workers:3,retries:2,context_chars:24000,wall_seconds:1800};
const WORKER = {engine:'ollama',model:'fixture:tiny',node:'node-a',digest:null,ready:true,available:true,context_chars:null};
const spec = {task:{kind:'objective',objective:'Return a safely escaped value.',budget:BUDGET,allowed_outputs:['result.js']},mode:'mica'};
const req = {requirements:[{id:'r1',text:'Handle <img src=x onerror="window.pwned=1"> as text.',acceptance:'TESTED'}],assumptions:['No filesystem access.'],tests:[{call:'escape("<")',expected:'&lt;'}]};
const planned = id => ({id,meta:{title:'Checked text'},status:'planned',active:false,can_execute:true,can_resume:false,spec,result:{status:'planned',request:req,calls:2,calls_reserved_or_spent:2,provenance:{objective:'caller',requirements:'model_proposed',acceptance_tests:'model_proposed_not_independent'},child:{plan:{contracts:[{contract_id:'escape',objective:'Escape HTML',dependency_contract_ids:[]}]}}}});
let browser, files;
before(async()=>{
  if (available) await fs.mkdir(evidence, {recursive:true});   // no empty folder when every journey is skipped
  browser=await launch();
  let html=await fs.readFile(path.join(root,'web/hub/index.html'),'utf8');
  files={'/symblic/':{body:html,contentType:'text/html'},'/symblic/mica.js':{body:await fs.readFile(path.join(here,'mica.js'),'utf8'),contentType:'text/javascript'},'/symblic/mica.css':{body:await fs.readFile(path.join(here,'mica.css'),'utf8'),contentType:'text/css'}};
});
after(async()=>await browser?.close());
function fixture(options={}) {
  let run=options.run || null;
  const api=async(request,url)=>{
    const route=url.pathname.slice(API.length);
    if (!url.pathname.startsWith(API)) {
      if (options.fleet) { const got=await options.fleet(request,url);if(got)return got; }
      if(url.pathname==='/api/cluster/status') return {json:{status:[{id:'node-a',role:'worker',tags:['worker'],online:true}]}};
      if(url.pathname==='/api/fleet/probe') return {json:{ok:true,online:true}};
      return {json:{}};
    }
    if (options.override) {const got=await options.override(route,request,url);if(got)return got;}
    if(route==='capabilities') return {json:{version:1,modes:['mica','whole_program'],task_sources:['objective','request','forge'],budget_defaults:BUDGET}};
    if(route==='inventory') return {json:{inventory:[WORKER],observed_at:'2026-10-10',diagnostics:[],scope:'Cached availability is not a reservation.'}};
    if(route==='runs') return {json:{runs:run?[{id:run.id,title:'Retained fixture',status:run.status}]:[]}};
    if(route==='check') return {json:{ok:true,sha256:'a'.repeat(64)}};
    if(route==='plan') {
      const b=request.postDataJSON();const id=createHash('sha256').update(b.idempotency_key).digest('hex').slice(0,12);
      run=planned(id);run.spec={...run.spec,task:b.forge ? {kind:'forge',request:{...req,budget:BUDGET},prepared:{origin:{project:b.forge.project,handoff:b.forge.handoff,accepted_authority:{requirements:req.requirements}},criterion_mapping:[],plan:{contracts:[]}}} : {...run.spec.task,artifact_format:b.artifact_format}};
      return options.lost ? {abort:true}:{json:{ok:true,id}};
    }
    if(route==='run') return run&&url.searchParams.get('id')===run.id ? {json:run} : {status:404,json:{error:'No such run'}};
    if(route==='execute'||route==='resume') {run={...run,status:'running',active:true,can_execute:false,can_resume:false};return {json:{ok:true,id:run.id}};}
    if(route==='stop') {run={...run,status:'stopped',active:false,can_execute:false,can_resume:true};return {json:{ok:true,id:run.id}};}
    if(route==='artifacts') return {json:{id:run.id,status:'done',artifacts:[{file:'result.js',bytes:40,sha256:'b'.repeat(64),assurance:'TESTED_MODEL_PROPOSED_CHECKS',text:'// <script>window.pwned=1</script>\nfunction escape(x){return x;}'}]}};
    return {status:404,json:{error:'Missing fixture route '+route}};
  };
  return {api,set:v=>{run=v},get:()=>run};
}
async function boot(f=fixture(),options={}) {
  const ctx=await open(browser,'/symblic/#construct',f.api,{files,...options});
  await ctx.page.waitForSelector('.mica');return {...ctx,fixture:f};
}
const ready=page=>page.waitForFunction(()=>Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Propose plan')?.disabled===false);
const post=ctx=>ctx.requests.filter(r=>r.path.startsWith(API)&&r.method==='POST');
async function launchPlan(ctx) {
  await ready(ctx.page);await ctx.page.getByLabel('Objective',{exact:true}).fill('Return a safely escaped value.');
  await ctx.page.getByRole('button',{name:'Propose plan',exact:true}).click();
  await ctx.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Execute plan').disabled);
}

test('initial load is observational and explicit worker probes preserve edited limits',async()=>{
  const c=await boot();try {
    await ready(c.page);assert.equal(post(c).length,0);
    await c.page.getByLabel('Total model calls',{exact:true}).fill('9');
    await c.page.getByRole('button',{name:'Refresh workers',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.mica-message').textContent.includes('Worker checks finished'));
    assert.equal(await c.page.getByLabel('Total model calls',{exact:true}).inputValue(),'9');
    assert.equal(post(c).length,0);assert.deepEqual(c.errors,[]);
    assert.equal(c.requests.filter(r=>r.path==='/api/fleet/probe').length,1);
    assert.deepEqual(c.requests.find(r=>r.path==='/api/fleet/probe').body,{node:'node-a'});
    await c.page.reload();await ready(c.page);
    assert.equal(c.requests.filter(r=>r.path==='/api/fleet/probe').length,1);
  } finally {await c.context.close();}
});

test('objective, proposal, original budget, explicit execute/stop/resume and source download',async()=>{
  const c=await boot();try {
    await launchPlan(c);assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan']);
    const body=post(c)[1].body;assert.equal(body.expected_sha256,'a'.repeat(64));assert.deepEqual(body.budget,BUDGET);
    assert.equal(body.inventory[0].model,'fixture:tiny');assert.equal(body.allowed_outputs[0],'result.js');
    assert.match(await c.page.locator('.mica').textContent(),/No filesystem access/);
    assert.match(await c.page.locator('.mica').textContent(),/model_proposed_not_independent/);
    assert.equal(await c.page.locator('.mica img').count(),0);
    const stored=await c.page.evaluate(key=>JSON.parse(localStorage.getItem(key)),SAVED);
    assert.deepEqual(Object.keys(stored).sort(),['id','pending']);assert.equal(stored.pending,false);
    await c.page.getByLabel('Total model calls',{exact:true}).fill('999');
    await c.page.getByRole('button',{name:'Execute plan',exact:true}).click();
    await c.page.getByRole('button',{name:'Stop run',exact:true}).waitFor({state:'visible'});
    await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Stop run').disabled);
    assert.deepEqual(post(c).at(-1).body,{id:stored.id});
    assert.match(await c.page.locator('.mica-status').textContent(),/Original limit: 64/);
    await c.page.getByRole('button',{name:'Stop run',exact:true}).click();
    await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Resume explicitly').disabled);
    assert.equal(post(c).filter(r=>r.path.endsWith('/resume')).length,0);
    await c.page.getByRole('button',{name:'Resume explicitly',exact:true}).click();
    await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Stop run').disabled);
    c.fixture.set({...c.fixture.get(),status:'done',active:false,can_execute:false,can_resume:false});
    await c.page.getByRole('button',{name:'Refresh status',exact:true}).click();
    await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Read artifacts').disabled);
    await c.page.getByRole('button',{name:'Read artifacts',exact:true}).click();
    await c.page.getByText('View source',{exact:true}).click();
    assert.match(await c.page.locator('.mica').textContent(),/<script>window.pwned=1/);
    assert.equal(await c.page.evaluate(()=>window.pwned),undefined);
    const download=c.page.waitForEvent('download');await c.page.getByRole('button',{name:'Download result.js',exact:true}).click();
    assert.equal((await download).suggestedFilename(),'result.js');
    assert.ok(c.requests.some(r=>r.path===API+'artifacts' && !r.search.includes('archive=1')));
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan','execute','stop','resume']);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('reload/reconnect observes a retained unknown outcome without resuming or resetting budget',async()=>{
  const id='abcdefabcdef',f=fixture({run:{...planned(id),status:'unknown',can_execute:true,can_resume:true,result:{calls:null,calls_reserved_or_spent:3,error:'Delivery unknown'}}});
  const c=await boot(f,{storage:()=>localStorage.setItem('symblic.construct.selection.v1',JSON.stringify({id:'abcdefabcdef',pending:false}))});try {
    await c.page.getByText('Delivery unknown',{exact:true}).waitFor();
    assert.equal(await c.page.getByRole('button',{name:'Resume explicitly',exact:true}).isDisabled(),true);
    assert.equal(await c.page.getByRole('button',{name:'Execute plan',exact:true}).isDisabled(),true);
    assert.match(await c.page.locator('.mica-status').textContent(),/unknown/);
    await c.page.reload();await c.page.getByText('Delivery unknown',{exact:true}).waitFor();
    await c.page.evaluate(()=>window.dispatchEvent(new Event('online')));
    await c.page.getByRole('button',{name:'Refresh status',exact:true}).click();
    assert.equal(post(c).length,0);assert.match(await c.page.locator('.mica-status').textContent(),/Original limit: 64/);
  }finally{await c.context.close();}
});

test('lost plan response retains deterministic run ID and recovers with GET only',async()=>{
  const c=await boot(fixture({lost:true}));try {
    await launchPlan(c);
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan']);
    assert.ok(c.requests.some(r=>r.path===API+'run'));
    await c.page.reload();await c.page.waitForSelector('.mica-status strong');
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan']);
    assert.equal((await c.page.evaluate(key=>JSON.parse(localStorage.getItem(key)),SAVED)).pending,false);
  }finally{await c.context.close();}
});

test('module format stays explicit and archive download preserves a read-only action',async()=>{
  const zip = 'UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA==';
  const c = await boot(fixture({override: async(route,request,url)=> route==='artifacts' ?
    {json:{status:'done',artifacts:[],archive:{base64:zip,bytes:22,file:'symblic-modules.zip',mime_type:'application/zip'}}}:null}));
  try {
    await ready(c.page);
    await c.page.getByText('Advanced limits and reuse',{exact:true}).click();
    await c.page.getByLabel('Output format',{exact:true}).selectOption('javascript_modules');
    await launchPlan(c);
    assert.equal(post(c)[1].body.artifact_format,'javascript_modules');
    c.fixture.set({...c.fixture.get(),status:'done',active:false,can_execute:false,can_resume:false});
    await c.page.getByRole('button',{name:'Refresh status',exact:true}).click();
    await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Read artifacts').disabled);
    await c.page.getByRole('button',{name:'Read artifacts',exact:true}).click();
    const download=c.page.waitForEvent('download');
    await c.page.getByRole('button',{name:'Download module bundle',exact:true}).click();
    assert.equal((await download).suggestedFilename(),'symblic-modules.zip');
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan']);
    assert.ok(c.requests.some(r=>r.path===API+'artifacts' && r.search.includes('archive=1')));
    assert.deepEqual(c.errors,[]);
  } finally {await c.context.close();}
});

test('unresolved lost launch stays disabled after reload and never dispatches again',async()=>{
  const c=await boot(fixture({lost:true,override:async(route)=>route==='run'?{status:404,json:{error:'No committed record observed.'}}:null}));try{
    await ready(c.page);await c.page.getByLabel('Objective',{exact:true}).fill('Return a value.');
    await c.page.getByRole('button',{name:'Propose plan',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.mica-message').textContent.includes('Launch outcome is unknown'));
    assert.equal(await c.page.getByRole('button',{name:'Propose plan',exact:true}).isDisabled(),true);
    const retained=await c.page.evaluate(key=>JSON.parse(localStorage.getItem(key)),SAVED);assert.equal(retained.pending,true);
    await c.page.reload();await c.page.waitForFunction(()=>document.querySelector('.mica-message').textContent.includes('Launch outcome is unknown'));
    assert.equal(await c.page.getByRole('button',{name:'Propose plan',exact:true}).isDisabled(),true);
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan']);
  }finally{await c.context.close();}
});

test('definite admission rejection plus absent record permits revision, without auto-retry',async()=>{
  const c=await boot(fixture({override:async(route)=>route==='plan'?{status:409,json:{error:'No capacity at admission.'}}:null}));try{
    await ready(c.page);await c.page.getByLabel('Objective',{exact:true}).fill('Return a value.');
    await c.page.getByRole('button',{name:'Propose plan',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.mica-message').textContent.includes('no job record exists'));
    assert.equal(await c.page.getByRole('button',{name:'Propose plan',exact:true}).isDisabled(),false);
    assert.equal(await c.page.evaluate(key=>localStorage.getItem(key),SAVED),null);
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check','plan']);
  }finally{await c.context.close();}
});

test('missing API and owner refusal show actionable failure and launch nothing',async()=>{
  for(const status of [404,403,503]) {
    const c=await boot(fixture({override:async()=>({status,json:{error:status===403?'Owner access is required.':'Restart required for the construction API.'}})}));try{
      await c.page.waitForFunction(()=>document.querySelector('.mica-message').classList.contains('mica-error'));
      assert.equal(await c.page.getByRole('button',{name:'Propose plan',exact:true}).isDisabled(),true);
      assert.equal(post(c).length,0);assert.match(await c.page.locator('.mica-message').first().textContent(),status===403?/Owner/:/Restart/);
      await c.page.getByRole('button',{name:'Refresh workers',exact:true}).click();
      await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Refresh workers').disabled);
      assert.match(await c.page.locator('.mica-message').first().textContent(),status===403?/Owner/:/Restart/);
      assert.equal(post(c).length,0);
    }finally{await c.context.close();}
  }
});

test('navigation during check cannot dispatch a plan and returning stays observational',async()=>{
  let release,entered;const seen=new Promise(r=>entered=r),wait=new Promise(r=>release=r);
  const f=fixture({override:async(route)=>{if(route==='check'){entered();await wait;return {json:{ok:true,sha256:'a'.repeat(64)}}}}});
  const c=await boot(f);try{
    await ready(c.page);await c.page.getByLabel('Objective',{exact:true}).fill('Return a value.');
    await c.page.getByRole('button',{name:'Propose plan',exact:true}).click();await seen;
    await c.page.evaluate(()=>Studio.go('overview'));
    await c.page.locator('.mica').waitFor({state:'detached'});release();
    await c.page.evaluate(()=>Studio.go('construct'));await ready(c.page);
    assert.deepEqual(post(c).map(r=>r.path.slice(API.length)),['check']);
  }finally{release();await c.context.close();}
});

test('phone and desktop dark journey has no overflow, readable inputs and no serious a11y errors',async()=>{
  for(const mobile of [false,true]){
    const c=await boot(fixture(),{mobile,storage:()=>localStorage.setItem('studioTheme','dark')});try{
      await launchPlan(c);
      await c.page.getByText('Advanced limits and reuse',{exact:true}).click();
      await c.page.getByText('Eligible fleet workers',{exact:true}).click();
      assert.equal(await noHorizontalScroll(c.page),true);
      assert.equal(await c.page.locator('.mica .field').evaluateAll(nodes=>nodes.every(n=>parseFloat(getComputedStyle(n).fontSize)>=16)),true);
      assert.deepEqual(await axe(c.page),[]);assert.deepEqual(c.errors,[]);
      await c.page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
      await c.page.waitForFunction(()=>window.scrollY===0);
      await c.page.screenshot({path:path.join(evidence,mobile?'construct-phone-dark.png':'construct-desktop-dark.png'),fullPage:true});
    }finally{await c.context.close();}
  }
});


test('Forge source fixes accepted authority and keeps objective controls out of dispatch',async()=>{
  const c=await boot(fixture(),{mobile:true,storage:()=>localStorage.setItem('studioTheme','dark')});try{
    await ready(c.page);await c.page.getByLabel('Construction source',{exact:true}).selectOption('forge');
    assert.equal(await c.page.getByLabel('Objective',{exact:true}).isDisabled(),true);
    assert.equal(await c.page.getByLabel('Total model calls',{exact:true}).isDisabled(),true);
    await c.page.getByLabel('Forge project ID',{exact:true}).fill('project-fixture');
    await c.page.getByLabel('Frozen handoff ID',{exact:true}).fill('handoff-fixture');
    await c.page.getByLabel('Executable bindings JSON',{exact:true}).fill('{broken');
    await c.page.getByRole('button',{name:'Validate frozen plan',exact:true}).click();
    assert.match(await c.page.locator('.mica-message').first().textContent(),/valid JSON/);
    assert.equal(post(c).length,0);
    await c.page.getByLabel('Executable bindings JSON',{exact:true}).fill(JSON.stringify({version:1,budget:BUDGET}));
    await c.page.getByRole('button',{name:'Validate frozen plan',exact:true}).click();
    await c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.mica button')).find(b=>b.textContent==='Execute plan').disabled);
    const sent=post(c)[1].body;
    assert.deepEqual(Object.keys(sent).sort(),['expected_sha256','forge','idempotency_key','inventory','mode']);
    assert.equal(sent.forge.handoff,'handoff-fixture');assert.equal(sent.mode,'mica');
    assert.match(await c.page.locator('.mica').textContent(),/Accepted Forge requirements/);
    assert.match(await c.page.locator('.mica').textContent(),/completeness remains unassessed/);
    assert.equal(await noHorizontalScroll(c.page),true);assert.deepEqual(await axe(c.page),[]);
    assert.deepEqual(c.errors,[]);
    const prior=post(c).length;
    await c.page.reload();await ready(c.page);await c.page.getByText('Accepted Forge requirements',{exact:true}).waitFor();
    assert.equal(post(c).length,prior);
  }finally{await c.context.close();}
});


test('explicit worker refresh bounds parallel probes, skips offline/cloud nodes and exposes partial failure',async()=>{
  let active=0, peak=0;const seen=[];
  const f=fixture({fleet:async(request,url)=>{
    if(url.pathname==='/api/cluster/status')return {json:{status:[
      ...['node-a','node-b','node-d'].map(id=>({id,role:'worker',tags:['worker'],online:true})),
      {id:'asleep',role:'worker',tags:['worker'],online:false},{id:'cloud',role:'cloud',tags:['worker'],online:true},
      {id:'host',local:true,tags:['worker'],online:true}]}};
    if(url.pathname==='/api/fleet/probe'){
      const node=request.postDataJSON().node;seen.push(node);active++;peak=Math.max(peak,active);
      await new Promise(resolve=>setTimeout(resolve,80));active--;
      return node==='node-b'?{status:503,json:{error:'Probe unavailable'}}:{json:{ok:true,online:true}};
    }
  }});
  const c=await boot(f);try{
    await ready(c.page);assert.deepEqual(seen,[]);
    await c.page.getByRole('button',{name:'Refresh workers',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.mica-message').textContent.includes('Some worker checks failed'));
    assert.deepEqual(seen.sort(),['node-a','node-b','node-d']);assert.equal(peak,2);
    assert.match(await c.page.locator('.mica-message').first().textContent(),/node-b/);
    assert.equal(post(c).length,0);assert.deepEqual(c.errors,[]);
    assert.equal(await c.page.getByRole('button',{name:'Refresh workers',exact:true}).isDisabled(),false);
  }finally{await c.context.close();}
});

test('navigation during readiness observation prevents subsequent worker probes',async()=>{
  let release,entered;const wait=new Promise(r=>release=r),seen=new Promise(r=>entered=r);
  const c=await boot(fixture({fleet:async(request,url)=>{
    if(url.pathname==='/api/cluster/status'){entered();await wait;return {json:{status:[{id:'node-a',tags:['worker'],online:true}]}};}
  }}));try{
    await ready(c.page);await c.page.getByRole('button',{name:'Refresh workers',exact:true}).click();await seen;
    await c.page.evaluate(()=>Studio.go('overview'));await c.page.locator('.mica').waitFor({state:'detached'});release();
    await c.page.evaluate(()=>Studio.go('construct'));await ready(c.page);
    assert.equal(c.requests.filter(r=>r.path==='/api/fleet/probe').length,0);assert.equal(post(c).length,0);
  }finally{release();await c.context.close();}
});

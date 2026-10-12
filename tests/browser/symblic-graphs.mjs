// Browser-only workflow fixtures. Every API is intercepted; no provider or live store.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {test, launch, open, axe, noHorizontalScroll, root} from './host-harness.mjs';
let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
const GH='a'.repeat(64), PH='b'.repeat(64), ID='000000000099';
const DOCUMENT={graph:{id:'ExactSteps',iterations:1,max_calls:2,nodes:[
  {id:'Seed',source:'program Seed.\nlet answer = 8.\nshow answer.',contract:'Return the exact integer eight.',inputs:{}},
  {id:'Double',source:'program Double.\ngiven value: number.\nlet answer = value * 2.\nshow answer.',contract:'Double the supplied exact value.',inputs:{value:{node:'Seed'}}}]},policy:{order:['fixture'],routes:[{id:'fixture',provider:'fake',model:'none',node:'fixture',local:true}]}};
function fixture() {
  const state={unavailable:false,gate:null,run:null,checkError:false,stale:false,listError:false,reads:0,finishOnPoll:false,selectedGate:null};
  function record(status='running',active=true) {return {id:ID,meta:{title:'Two exact steps',graph_hash:GH,policy_hash:PH},
    state:{status,reserved_calls:2,ready:[],nodes:{Seed:{id:'Seed',status:'succeeded',iteration:0,result:{value:8,outcome:'supported',assumptions:[],evidence:['deterministic arithmetic']}},
      Double:{id:'Double',status:active?'running':'succeeded',iteration:0,result:{value:16,outcome:'supported',provenance:['<img src=x onerror=alert(1)>']}}}},events:[{id:'fixture-start',kind:'started'}],active,can_resume:!active && status==='recovering'};}
  async function api(request,url) {
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'mock-only',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(!route.startsWith('graph/'))return {json:{}};
    if(state.unavailable)return {status:503,json:{error:'Graph adapter is not installed; refresh after the server is upgraded.'}};
    if(route==='graph/example')return {json:{...DOCUMENT,description:'Synthetic deterministic fixture: eight, then sixteen. No models.'}};
    if(route==='graph/check') {
      if(state.gate)await state.gate;
      if(state.checkError)return {status:400,json:{error:'Graph iteration limit must be between 1 and 32.'}};
      return {json:{ok:true,graph_hash:GH,policy_hash:PH,nodes:2,iterations:1,max_calls:2,ready:['Seed'],scope:'Pure structural check. No dispatch or model calls.'}};
    }
    if(route==='graph/runs') {
      if(state.listError)return {status:503,json:{error:'Saved graph runs are temporarily unavailable.'}};
      return {json:{runs:state.run?[{id:ID,title:'Two exact steps',status:state.run.state.status,created:1,graph_hash:GH,policy_hash:PH,reserved_calls:2}]:[]}};
    }
    if(route==='graph/run' && request.method()==='POST') {
      if(state.stale)return {status:409,json:{error:'Reviewed graph hash changed.'}};
      state.run=record();return {json:{id:ID}};
    }
    if(route==='graph/run' && request.method()==='GET') {
      state.reads++;
      if(state.selectedGate)await state.selectedGate;
      if(state.finishOnPoll)state.run=record('done',false);
      return {json:state.run};
    }
    if(route==='graph/stop'){state.run=record('cancelled',false);return {json:{ok:true,id:ID}};}
    if(route==='graph/resume'){state.run=record();return {json:{ok:true,id:ID}};}
    throw new Error('Unexpected graph API '+route);
  }
  return {api,state,record};
}
async function visit(t,{mobile=false,theme='light',fake=fixture(),storage=null}={},body) {
  const {context,page,requests,errors}=await open(browser,'/automation-studio/symblic.html#graphs',fake.api,{mobile,storage});
  page.setDefaultTimeout(10000);
  try {
    await page.waitForFunction(()=>!!window.Studio);await page.evaluate(value=>Studio.setTheme(value),theme);
    await page.locator('.sy-graphs').waitFor();
    await body({page,requests,...fake});assert.deepEqual(errors,[]);
  } catch(error) {
    const file='/tmp/symblic-graphs-browser-'+t.name.replace(/[^a-z0-9]+/gi,'-');
    await page.screenshot({path:file+'.png',fullPage:true});await fs.writeFile(file+'.html',await page.content());
    t.diagnostic(JSON.stringify({file,requests:requests.filter(row=>row.path.includes('/graph/')).map(({path,method,search})=>({path,method,search})),errors}));throw error;
  } finally {await context.close();}
}
async function checked(page) {
  await page.getByRole('button',{name:'Check graph',exact:true}).click();
  await page.getByRole('heading',{name:'Reviewed graph contract'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isEnabled(),true);
}
async function advanced(page) {
  if(!await page.locator('#sy-graph-json').isVisible())await page.getByText('Edit graph and routing policy JSON',{exact:true}).click();
}
async function layout(page) {
  assert.equal(await noHorizontalScroll(page),true);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=page.viewportSize().width+1,'Mobile viewport expansion');
  assert.deepEqual(await axe(page),[]);
}
for(const mobile of [false,true])for(const theme of ['light','dark']) {
  test(`graph review, run, receipt, stop and recovery ${mobile?'phone':'desktop'} ${theme}`,async t=>{
    await visit(t,{mobile,theme},async({page,requests,state,record})=>{
      await page.getByRole('heading',{name:'ExactSteps',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
      assert.match(await page.locator('[data-graph-overview]').textContent(),/value ← Seed/);
      await checked(page);
      assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
      await page.getByText('Reviewed hashes and check receipt',{exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-check] pre')?.textContent.includes('graph_hash'));
      assert.match(await page.locator('[data-graph-check] pre').textContent(),new RegExp(GH));
      await advanced(page);
      const original=await page.locator('#sy-graph-json').inputValue();
      await page.locator('#sy-graph-json').fill(original+'\n');
      assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
      assert.equal(await page.locator('[data-graph-check]').count(),0);
      await page.reload();await page.locator('.sy-graphs').waitFor();await advanced(page);
      assert.equal(await page.locator('#sy-graph-json').inputValue(),original+'\n');
      assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
      await checked(page);
      await page.getByRole('button',{name:'Run checked graph'}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('Recorded status: running'));
      const dispatch=requests.find(r=>r.path.endsWith('/graph/run')&&r.method==='POST');
      assert.deepEqual(dispatch.body,{...DOCUMENT,expected_graph_hash:GH,expected_policy_hash:PH});
      assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,1);
      assert.match(await page.locator('[data-graph-status]').textContent(),/2 reserved calls/);
      assert.equal(await page.locator('[data-graph-run] pre').first().textContent(),'','Large receipts are lazy');
      await page.getByText('Recorded result for Double',{exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-run]')?.textContent.includes('"value": 16'));
      assert.match(await page.locator('[data-graph-run]').textContent(),/"value": 16/);
      assert.equal(await page.locator('.sy-graphs img').count(),0);
      await page.getByRole('button',{name:'Stop graph',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('cancelled'));
      assert.equal(await page.getByRole('button',{name:'Resume graph'}).isDisabled(),true,'Cancelled graphs are terminal');
      assert.deepEqual(requests.find(r=>r.path.endsWith('/graph/stop')).body,{id:ID});
      state.run=record('recovering',false);
      await page.getByRole('button',{name:'Refresh selected run'}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('recovering'));
      await page.getByRole('button',{name:'Resume graph'}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('running'));
      assert.deepEqual(requests.find(r=>r.path.endsWith('/graph/resume')).body,{id:ID});
      state.finishOnPoll=true;
      await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('done'));
      assert.equal(await page.getByRole('button',{name:'Resume graph'}).isDisabled(),true);
      await page.getByText('Full state and event receipts',{exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('[data-graph-run]')?.textContent.includes('fixture-start'));
      assert.match(await page.locator('[data-graph-run]').textContent(),/fixture-start/);
      assert.ok(await page.locator('#stage [data-step]').count()>0,'Component must preserve Studio pager');
      await layout(page);
      await page.reload();await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('done'));
      assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,1,'Reload only reads saved state');
      await page.getByRole('button',{name:'Two exact steps · done · 2 reserved calls'}).waitFor();
    });
  });
}
test('graph JSON, structural caps, stale pins and unavailable server recover visibly',async t=>{
  const fake=fixture();fake.state.unavailable=true;
  await visit(t,{mobile:true,theme:'dark',fake},async({page,requests,state})=>{
    await page.getByText(/Graph execution is unavailable on this server/).first().waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
    state.unavailable=false;await advanced(page);
    await page.getByRole('button',{name:'Load deterministic example'}).click();
    await page.getByRole('heading',{name:'ExactSteps',exact:true}).waitFor();
    await page.getByRole('button',{name:'Refresh saved runs'}).click();
    await page.locator('#sy-graph-json').fill('{broken');
    const before=requests.filter(r=>r.path.endsWith('/graph/check')).length;
    await page.getByRole('button',{name:'Check graph',exact:true}).click();
    await page.getByText('The graph document must be valid JSON containing graph and policy.',{exact:true}).waitFor();
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/check')).length,before);
    const invalid=structuredClone(DOCUMENT);invalid.graph.iterations=33;
    await page.locator('#sy-graph-json').fill(JSON.stringify(invalid));state.checkError=true;
    await page.getByRole('button',{name:'Check graph',exact:true}).click();
    await page.getByText('Graph iteration limit must be between 1 and 32.',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
    state.checkError=false;await page.locator('#sy-graph-json').fill(JSON.stringify(DOCUMENT));await checked(page);
    state.stale=true;await page.getByRole('button',{name:'Run checked graph'}).click();
    await page.getByText('Reviewed graph hash changed. Check the current document again.',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
    state.stale=false;await checked(page);await page.getByRole('button',{name:'Run checked graph'}).click();
    await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('running'));
    await layout(page);
  });
});
for(const mobile of [false,true])test(`graph late check preserves edits and navigation ${mobile?'phone':'desktop'}`,async t=>{
  const fake=fixture();let release;
  fake.state.gate=new Promise(resolve=>{release=resolve;});
  await visit(t,{mobile,fake},async({page,requests})=>{
    await page.getByRole('heading',{name:'ExactSteps',exact:true}).waitFor();await advanced(page);
    await page.evaluate(()=>{const original=Studio.api;window.graphSettled=0;Studio.api=async(...args)=>{try{return await original(...args);}finally{if(args[0].endsWith('/graph/check'))window.graphSettled++;}};});
    await page.getByRole('button',{name:'Check graph',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-graph-controls]').textContent.includes('Checking'));
    const edited=JSON.stringify({...DOCUMENT,graph:{...DOCUMENT.graph,id:'EditedWhileChecking'}});
    await page.locator('#sy-graph-json').fill(edited);
    await page.evaluate(()=>Studio.go('write'));
    await page.locator('#sySrc').waitFor();release();await page.waitForFunction(()=>window.graphSettled===1);
    assert.equal(await page.locator('.sy-graphs').count(),0,'Late response cannot replace another component');
    await page.evaluate(()=>Studio.go('graphs'));await page.locator('.sy-graphs').waitFor();
    await page.getByRole('heading',{name:'EditedWhileChecking',exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true,'Stale check cannot authorize edited draft');
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
    assert.equal(await page.locator('#sy-graph-json').inputValue(),edited);
  });
});

test('real deterministic graph API receipts render exact twelve with zero provider calls',async t=>{
  const script=`import json,os,tempfile
from unittest.mock import patch
from symblic.js import check as JS
from integration.host import symblic_graph_api as A
class NoApps:
 def call(self, request): raise AssertionError('provider call forbidden')
with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'AUTOMATION_DATA_DIR':folder}), patch.object(JS,'node_version',return_value='browser-fixture-no-node'), patch('subprocess.Popen',side_effect=AssertionError('external process forbidden')):
 example=A.example()
 body={k:v for k,v in example.items() if k in ('graph','policy')}
 checked=A.check(body)
 def launch(ident, saved, generation):
  A.run_job(saved, applicators=NoApps(), generation=generation)
  return {'ok':True}
 with patch.dict(A.launcher, {'launch':launch,'active':lambda _:False,'stop':lambda _:True}):
  ident=A.start({**body,'expected_graph_hash':checked['graph_hash'],'expected_policy_hash':checked['policy_hash']})['id']
  print(json.dumps({'example':example,'checked':checked,'run':A.view(ident),'runs':A.list_runs()}))
`;
  const result=spawnSync(process.env.TEST_PYTHON || 'python3',['-B','-c',script],{cwd:root,encoding:'utf8',timeout:30000});
  assert.equal(result.status,0,result.stderr||String(result.error));
  const data=JSON.parse(result.stdout), fallback=fixture();let dispatched=false;
  const fake={state:{},api:async(request,url)=>{
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='graph/example')return {json:data.example};
    if(route==='graph/check') {
      assert.deepEqual(request.postDataJSON(),{graph:data.example.graph,policy:data.example.policy});
      return {json:data.checked};
    }
    if(route==='graph/run'&&request.method()==='POST') {
      assert.deepEqual(request.postDataJSON(),{graph:data.example.graph,policy:data.example.policy,
        expected_graph_hash:data.checked.graph_hash,expected_policy_hash:data.checked.policy_hash});
      dispatched=true;return {json:{id:data.run.id}};
    }
    if(route==='graph/run')return {json:data.run};
    if(route==='graph/runs')return {json:{runs:dispatched?data.runs:[]}};
    return fallback.api(request,url);
  }};
  await visit(t,{mobile:true,theme:'dark',fake},async({page,requests})=>{
    await page.getByRole('heading',{name:'DoubleExample',exact:true}).waitFor();
    await checked(page);assert.equal(dispatched,false);
    await page.getByRole('button',{name:'Run checked graph'}).click();
    await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('succeeded'));
    await page.getByText('Recorded result for Double',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-graph-run]')?.textContent.includes('"value": 12'));
    assert.match(await page.locator('[data-graph-run]').textContent(),/"issued_calls": 0/);
    assert.match(await page.locator('[data-graph-run]').textContent(),/source_truth/);
    assert.equal(await page.getByRole('button',{name:'Resume graph'}).isDisabled(),true);
    assert.equal(await page.getByRole('button',{name:'Stop graph'}).isDisabled(),true);
    assert.equal(requests.filter(row=>row.path.endsWith('/graph/run')&&row.method==='POST').length,1);
    await layout(page);
  });
});

test('node outcomes are paged without dropping receipts and unknown recovery stays disabled',async t=>{
  const fake=fixture();fake.state.run=fake.record('unresolved',false);
  fake.state.run.state.nodes=Array.from({length:45},(_,i)=>({node:'Node'+i,iteration:0,status:'unknown',error:'Uncertain fixture '+i}));
  fake.state.run.can_resume=false;
  await visit(t,{mobile:true,fake},async({page})=>{
    await page.getByRole('button',{name:'Two exact steps · unresolved · 2 reserved calls'}).click();
    await page.getByText('Node outcomes 1–20 of 45',{exact:true}).waitFor();
    assert.equal(await page.locator('.sy-graph-results li').count(),20);
    await page.getByRole('button',{name:'Next node outcomes'}).click();
    await page.getByText('Node outcomes 21–40 of 45',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Next node outcomes'}).click();
    await page.getByText('Node outcomes 41–45 of 45',{exact:true}).waitFor();
    assert.equal(await page.locator('.sy-graph-results li').count(),5);
    assert.equal(await page.getByRole('button',{name:'Next node outcomes'}).isDisabled(),true);
    assert.equal(await page.getByRole('button',{name:'Resume graph'}).isDisabled(),true);
    await page.getByText('Full state and event receipts',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-graph-run]')?.textContent.includes('Uncertain fixture 0'));
    assert.match(await page.locator('[data-graph-run]').textContent(),/Uncertain fixture 44/);
    await layout(page);
  });
});

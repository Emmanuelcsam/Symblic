// Isolated policy UI contract tests. APIs and experiment measurements are synthetic.
import {before,after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {test, launch,open,axe,noHorizontalScroll} from './host-harness.mjs';
let browser;before(async()=>{browser=await launch();});after(async()=>{await browser?.close();});
const HASH='a'.repeat(64), POLICY_HASH='b'.repeat(64), ID='0000000000bb';
const BASE={version:1,routes:[{id:'Old',provider:'fake',model:'old',node:'test',local:true}],order:['Old']};
const CHOSEN={version:1,routes:[{id:'Chosen',provider:'fake',model:'small',node:'test',local:true}],order:['Chosen']};
const GRAPH={id:'PreservedGraph',nodes:[{id:'Step',contract:'Preserve this authored graph.',inputs:{},source:'let answer = 12.'}],iterations:1,max_calls:2};
const DOCUMENT={title:'Synthetic policy experiment',candidates:[BASE,CHOSEN],baseline_index:0,
  training:[{family:'train',input:{graph:GRAPH,output_node:'Step'},expected:12}],
  heldout:[{family:'test',input:{graph:{...GRAPH,id:'Heldout'},output_node:'Step'},expected:12}],
  budget:{max_calls:2,max_cost_units:2},objective:{max_score:1,score_weight:100,call_weight:1,cost_weight:0,unknown_cost:'reject',tie_break:'policy_sha256_ascending',min_heldout_gain:1}};
const SUMMARY={denominator:2,statuses:{correct:1,failed:1,missing:0},score_sum:1,observed_calls:2,charged_calls:4,unknown_cost_items:1,utility_sum:96};
function fixture(){
  const state={unavailable:false,invalid:false,stale:false,run:null,checkGate:null,selectedGate:null,finish:false};
  function record(status='running',active=true){return {id:ID,meta:{title:DOCUMENT.title},status,active,can_resume:status==='stopped',scope:'Synthetic finite routing comparison; future runs only.',
    state:{stage:status==='done'?'evaluated':'heldout',assignments:{training:{pending:{count:0},inflight:{count:0},terminal:{count:2}},heldout:{pending:{count:0},inflight:{count:active?1:0},terminal:{count:active?1:2}}},
      selected:{selected:{sha256:POLICY_HASH,policy_json:JSON.stringify(CHOSEN)},receipt:{summaries:{[POLICY_HASH]:SUMMARY}}},
      evaluation:status==='done'?{improvement:false,complete_accounting:false,comparison:'not_established',utility_gain:{numerator:1,denominator:2},summaries:{[POLICY_HASH]:SUMMARY}}:null}};}
  async function api(request,url){
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'fixture',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route==='graph/example')return {json:{graph:GRAPH,policy:BASE,description:'Preserve this graph'}};
    if(route==='graph/runs')return {json:{runs:[]}};
    if(route==='graph/check')return {json:{ok:true,graph_hash:'c'.repeat(64),policy_hash:'d'.repeat(64),nodes:1,iterations:1,max_calls:2,ready:['Step'],scope:'Synthetic structural check'}};
    if(!route.startsWith('policy/'))return {json:{}};
    if(state.unavailable)return {status:503,json:{error:'Policy graph bridge needs the server update.'}};
    if(route==='policy/example')return {json:DOCUMENT};
    if(route==='policy/check'){
      if(state.checkGate)await state.checkGate;
      if(state.invalid)return {status:400,json:{error:'Training and held-out families overlap.'}};
      return {json:{ok:true,plan_hash:HASH,candidates:2,training_cases:1,heldout_cases:1,max_assignments:4,max_provider_calls:8,scope:'Frozen finite fixture. No scientific gain established.'}};
    }
    if(route==='policy/runs')return {json:{runs:state.run?[{id:ID,title:DOCUMENT.title,status:state.run.status}]:[]}};
    if(route==='policy/run'&&request.method()==='POST'){
      if(state.stale)return {status:409,json:{error:'The experiment differs from the checked version.'}};
      state.run=record();return {json:{id:ID}};
    }
    if(route==='policy/run'){if(state.finish)state.run=record('done',false);return {json:state.run};}
    if(route==='policy/stop'){state.run=record('stopped',false);return {json:{ok:true,id:ID}};}
    if(route==='policy/resume'){state.run=record();return {json:{ok:true,id:ID}};}
    if(route==='policy/selected'){if(state.selectedGate)await state.selectedGate;return {json:{id:ID,policy:CHOSEN,policy_hash:POLICY_HASH,selection:state.run.state.selected,scope:'future runs only'}};}
    throw new Error('Unexpected policy API '+route);
  }return {api,state,record};
}
async function visit(t,{mobile=false,theme='light',fake=fixture(),storage=null,hash='policies'}={},body){
  const {context,page,requests,errors}=await open(browser,'/automation-studio/symblic.html#'+hash,fake.api,{mobile,storage});page.setDefaultTimeout(10000);
  try{await page.waitForFunction(()=>!!window.Studio);await page.evaluate(value=>Studio.setTheme(value),theme);await body({page,requests,...fake});assert.deepEqual(errors,[]);}
  catch(error){const path='/tmp/symblic-policies-browser-'+t.name.replace(/[^a-z0-9]+/gi,'-');await page.screenshot({path:path+'.png',fullPage:true});await fs.writeFile(path+'.html',await page.content());t.diagnostic(JSON.stringify({path,requests:requests.filter(row=>row.path.includes('/policy/')).map(({path,method,search})=>({path,method,search})),errors}));throw error;}
  finally{await context.close();}
}
async function advanced(page){if(!await page.locator('#sy-policy-json').isVisible())await page.getByText('Edit experiment JSON',{exact:true}).click();}
async function checked(page){await page.getByRole('button',{name:'Check experiment',exact:true}).click();await page.getByRole('heading',{name:'Reviewed experiment limits'}).waitFor();}
async function layout(page){assert.equal(await noHorizontalScroll(page),true);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=page.viewportSize().width+1);assert.deepEqual(await axe(page),[]);}
for(const mobile of [false,true])for(const theme of ['light','dark'])test(`frozen policy workflow and explicit draft copy ${mobile?'phone':'desktop'} ${theme}`,async t=>{
  await visit(t,{mobile,theme,hash:'graphs'},async({page,requests,state})=>{
    await page.getByRole('heading',{name:'PreservedGraph',exact:true}).waitFor();
    await page.getByRole('button',{name:'Check graph',exact:true}).click();await page.getByRole('heading',{name:'Reviewed graph contract'}).waitFor();
    await page.evaluate(()=>Studio.go('policies'));await page.getByRole('heading',{name:DOCUMENT.title,exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked experiment'}).isDisabled(),true);
    await checked(page);assert.equal(requests.filter(row=>row.path.endsWith('/policy/run')&&row.method==='POST').length,0);
    await advanced(page);const text=await page.locator('#sy-policy-json').inputValue();await page.locator('#sy-policy-json').fill(text+'\n');
    assert.equal(await page.getByRole('button',{name:'Run checked experiment'}).isDisabled(),true);
    await page.reload();await page.locator('.sy-policies').waitFor();await advanced(page);assert.equal(await page.locator('#sy-policy-json').inputValue(),text+'\n');
    await checked(page);await page.getByRole('button',{name:'Run checked experiment'}).click();
    await page.waitForFunction(()=>document.querySelector('[data-policy-status]')?.textContent.includes('running'));
    assert.deepEqual(requests.find(row=>row.path.endsWith('/policy/run')&&row.method==='POST').body,{...DOCUMENT,expected_plan_hash:HASH});
    assert.match(await page.locator('[data-policy-stage=training]').textContent(),/pending 0 · inflight 0 · terminal 2/);
    assert.match(await page.locator('[data-policy-stage=heldout]').textContent(),/inflight 1 · terminal 1/);
    assert.match(await page.locator('[data-policy-run]').textContent(),/Score sum: 1 \/ 2 assigned cases/);
    assert.match(await page.locator('[data-policy-evaluation]').textContent(),/not established/);
    await page.getByRole('button',{name:'Stop experiment',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[data-policy-status]')?.textContent.includes('stopped'));
    await page.getByRole('button',{name:'Resume experiment',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[data-policy-status]')?.textContent.includes('running'));
    state.finish=true;await page.waitForFunction(()=>document.querySelector('[data-policy-status]')?.textContent.includes('done'));
    assert.match(await page.locator('[data-policy-evaluation]').textContent(),/not established/);
    assert.equal(await page.getByRole('button',{name:'Resume experiment'}).isDisabled(),true);
    assert.equal(await page.locator('[data-policy-run] pre').textContent(),'');
    await page.getByText('Full experiment state and receipts',{exact:true}).click();await page.waitForFunction(()=>document.querySelector('[data-policy-run] pre')?.textContent.includes('"unknown_cost_items": 1'));
    await layout(page);
    await page.getByRole('button',{name:'Copy selected policy to Graphs draft'}).click();
    await page.locator('.sy-graphs').waitFor();await page.getByText(/Copied routing policy/).waitFor();
    const copied=JSON.parse(await page.locator('#sy-graph-json').inputValue());assert.deepEqual(copied.graph,GRAPH);assert.deepEqual(copied.policy,CHOSEN);
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
    assert.equal(requests.filter(row=>row.path.endsWith('/graph/run')&&row.method==='POST').length,0);
    assert.equal(requests.filter(row=>row.path.endsWith('/policy/run')&&row.method==='POST').length,1);
    await page.reload();await page.locator('.sy-graphs').waitFor();await page.getByText('Edit graph and routing policy JSON',{exact:true}).click();
    assert.deepEqual(JSON.parse(await page.locator('#sy-graph-json').inputValue()),copied);
  });
});
test('policy unavailable, malformed draft, leaked family and stale pin fail visibly',async t=>{
  const fake=fixture();fake.state.unavailable=true;
  await visit(t,{mobile:true,theme:'dark',fake},async({page,requests,state})=>{
    await page.getByText(/Policy experiments are unavailable/).first().waitFor();state.unavailable=false;await advanced(page);
    await page.getByRole('button',{name:'Load deterministic experiment'}).click();await page.getByRole('heading',{name:DOCUMENT.title,exact:true}).waitFor();
    await page.getByRole('button',{name:'Refresh saved experiments'}).click();
    await page.locator('#sy-policy-json').fill('{bad');const count=requests.filter(row=>row.path.endsWith('/policy/check')).length;
    await page.getByRole('button',{name:'Check experiment',exact:true}).click();await page.getByText('The experiment document must be valid JSON.',{exact:true}).waitFor();
    assert.equal(requests.filter(row=>row.path.endsWith('/policy/check')).length,count);
    await page.locator('#sy-policy-json').fill(JSON.stringify(DOCUMENT));state.invalid=true;
    await page.getByRole('button',{name:'Check experiment',exact:true}).click();await page.getByText('Training and held-out families overlap.',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked experiment'}).isDisabled(),true);
    state.invalid=false;await checked(page);state.stale=true;await page.getByRole('button',{name:'Run checked experiment'}).click();
    await page.getByText('The experiment differs from the checked version. Check the current document again.',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked experiment'}).isDisabled(),true);await layout(page);
  });
});
test('policy finite gain requires complete recorded comparison and invalid graph draft is preserved',async t=>{
  const fake=fixture();fake.state.run=fake.record('done',false);fake.state.run.state.evaluation.improvement=true;
  await visit(t,{fake,storage:()=>sessionStorage.setItem('symblic-graph-draft-v1',JSON.stringify({raw:'{my unfinished graph',selected:''}))},async({page,state})=>{
    await page.getByRole('button',{name:DOCUMENT.title+' · done'}).click();await page.locator('[data-policy-status]').waitFor();
    assert.match(await page.locator('[data-policy-evaluation]').textContent(),/not established/);
    state.run.state.evaluation.complete_accounting=true;state.run.state.evaluation.comparison='observed_improvement';
    await page.getByRole('button',{name:'Refresh selected experiment'}).click();await page.getByText('Recorded finite held-out utility gain: 1 / 2. This applies only to these frozen cases and objective.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Copy selected policy to Graphs draft'}).click();
    await page.getByText('The graph document must be valid JSON containing graph and policy.',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('symblic-graph-draft-v1')).raw),'{my unfinished graph');
    assert.equal(await page.evaluate(()=>Studio.page),'policies');
  });
});
for(const mobile of [false,true])test(`late policy selection does not redirect after navigation ${mobile?'phone':'desktop'}`,async t=>{
  const fake=fixture();fake.state.run=fake.record('done',false);let release;fake.state.selectedGate=new Promise(resolve=>{release=resolve;});
  await visit(t,{mobile,fake},async({page,requests})=>{
    await page.getByRole('button',{name:DOCUMENT.title+' · done'}).click();await page.locator('[data-policy-status]').waitFor();
    await page.evaluate(()=>{const original=Studio.api;window.policySettled=0;Studio.api=async(...args)=>{try{return await original(...args);}finally{if(args[0].includes('/policy/selected?'))window.policySettled++;}};});
    await page.getByRole('button',{name:'Copy selected policy to Graphs draft'}).click();await page.getByRole('button',{name:'Copying…'}).waitFor();
    await page.evaluate(()=>Studio.go('write'));await page.locator('#sySrc').waitFor();release();await page.waitForFunction(()=>window.policySettled===1);
    assert.equal(await page.evaluate(()=>Studio.page),'write');assert.equal(await page.locator('.sy-policies').count(),0);
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('symblic-graph-draft-v1')),null);
    assert.equal(requests.filter(row=>row.path.endsWith('/graph/run')&&row.method==='POST').length,0);
  });
});

test('late policy check cannot certify an edited document or replace another page',async t=>{
  const fake=fixture();let release;fake.state.checkGate=new Promise(resolve=>{release=resolve;});
  await visit(t,{mobile:true,fake},async({page})=>{
    await page.getByRole('heading',{name:DOCUMENT.title,exact:true}).waitFor();await advanced(page);
    await page.evaluate(()=>{const original=Studio.api;window.checkSettled=0;Studio.api=async(...args)=>{try{return await original(...args);}finally{if(args[0].endsWith('/policy/check'))window.checkSettled++;}};});
    await page.getByRole('button',{name:'Check experiment',exact:true}).click();await page.getByRole('button',{name:'Checking…'}).waitFor();
    const document=JSON.stringify({...DOCUMENT,title:'Edited while checking'});await page.locator('#sy-policy-json').fill(document);
    await page.evaluate(()=>Studio.go('write'));await page.locator('#sySrc').waitFor();release();await page.waitForFunction(()=>window.checkSettled===1);
    assert.equal(await page.locator('.sy-policies').count(),0);assert.equal(await page.evaluate(()=>Studio.page),'write');
    await page.evaluate(()=>Studio.go('policies'));await page.getByRole('heading',{name:'Edited while checking',exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Run checked experiment'}).isDisabled(),true);
    assert.equal(await page.locator('#sy-policy-json').inputValue(),document);
  });
});

// Real pure compiler/scorer; invented run/adoption records and intercepted APIs only.
// No live service, model, provider, or store is accessed.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {test, launch, open, noHorizontalScroll, axe, root} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });
const RUN = '000000000001', JOB = '0000000000aa';
const ORIGINAL = 'program Original fixture.\nlet answer = 8.\nshow answer.\n';
const CANDIDATE = 'program Candidate fixture.\nlet answer = 9.\nshow answer.\n';
const pythonCache = new Map();
function python(code, value) {
  const key = code + JSON.stringify(value);
  if (!pythonCache.has(key)) {
    const r = spawnSync(process.env.TEST_PYTHON || 'python3', ['-B', '-c', code], {cwd:root,input:JSON.stringify(value),encoding:'utf8',timeout:30000});
    assert.equal(r.status, 0, r.stderr || String(r.error));
    pythonCache.set(key, JSON.parse(r.stdout));
  }
  return structuredClone(pythonCache.get(key));
}
function compiler(body) {
  return python('import sys,json\nfrom symblic.adapters import logic as L\ntry: print(json.dumps({"ok":True,"value":L.compile_task(json.load(sys.stdin))}))\nexcept ValueError as e: print(json.dumps({"ok":False,"error":str(e)}))', body);
}
function matchedEvidence() {
  return python(`import json
from symblic.bench import eval_protocol as E, matched as M
controls=dict(model={'primary':['fake:small'],'fallback':[],'stronger_fallback':[],'settings':{}},information={'task':'synthetic'},budget={'provider_calls':1},feedback={'policy':'none'},validator={'id':'exact-fixture'})
cases=[{'id':str(i),'family':'fixture-'+str(i),'split':'heldout','input':{'question':'synthetic '+str(i)},'rubric':{'mode':'typed_json','expected':8}} for i in range(2)]
plan=E.make_plan(cases,[E.make_arm('direct','direct',**controls),E.make_arm('typed','typed',**controls)])
records=[]
for assignment,value in zip(plan['assignments'][:2],[9,8]):
 records.append(E.make_record(plan,assignment['id'],[{'model':'fake:small','role':'primary','status':'answered','answer':value,'encoding':'json_value','contract_accept':True,'feedback_exposed':False,'usage':{}}],selected=1))
summary=E.summarize(plan,records)
summary['runner']={'version':1,'endpoint':'one_exact_typed_decision','current_implementation_matches':False}
print(json.dumps({'summary':summary,'markdown':M.markdown(summary)}))`, null);
}
function fixtures() {
  const state = {lastRun:null, rejectAdoption:false, adopted:false, compileGate:null};
  const claims = Array.from({length:45},(_,i)=>({id:'claim-'+i,revision:1,sha256:'a'.repeat(64),
    content:{name:i===0?'<img src=x onerror=alert(1)>':'Claim '+i},origin:i%2?'model_proposal':'owner_input',
    status:'active',dependencies:[],checks:[{kind:'type','scope':'synthetic'}]}));
  const epistemic = {claims,assessments:claims.map(c=>({id:c.id,status:'active',support:'conditional',admissible:true,
    conditional_on:[{id:'root',origin:'owner_input'}],lineage_complete:true}))};
  epistemic.assessments[0].roots_omitted = {count:129,total:130,by_origin_status:[{origin:'owner_input',status:'active',count:129}]};
  epistemic.assessments[0].lineage_complete = false;
  epistemic.assessments[1].roots_omitted = {count:2,total:900}; // malformed summary never invents a total
  const job = () => ({id:JOB,title:'Synthetic tightening',status:'done',source:ORIGINAL,panel:['fake:a','fake:b'],clarifier:'fake:c',
    result:{version:2,changed:true,program:ORIGINAL,candidate_program:CANDIDATE,audit_sha256:'a'.repeat(64),
      original_sha256:'b'.repeat(64),candidate_sha256:'c'.repeat(64),history:[],rewrites:[],
      fidelity:{status:'unknown',requirements:[{id:'R1',text:'Keep the original unit convention',status:'unmapped'}]}},
    ...(state.adopted?{adoption:{adoption:{status:'accepted'}}}:{})});
  async function api(request,url) {
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta') return {json:{version:'fixture-only',examples:[],features:{strict_model_pins:state.strictCapability}}};
    if(route==='runs') return {json:{runs:state.lastRun?[{id:RUN,title:'Synthetic proof run',status:'done',calls:0}]:[]}};
    if(route==='programs') return {json:{programs:[]}};
    if(route==='compares') return {json:{compares:[]}};
    if(route==='editor/check') return {json:python('import sys,json; from symblic.authoring import editor_diagnostics as D; b=json.load(sys.stdin); print(json.dumps(D.check(b["source"],b.get("language","native"))))',request.postDataJSON())};
    if(route==='check') return {json:python('import sys,json,symblic; print(json.dumps(symblic.check(json.load(sys.stdin)["source"])))',request.postDataJSON())};
    if(route==='logic/compile') {
      if(state.compileGate) await state.compileGate;
      const result=compiler(request.postDataJSON());
      return result.ok?{json:result.value}:{status:400,json:{error:result.error}};
    }
    if(route==='run' && request.method()==='POST') {
      state.lastRun=request.postDataJSON(); return {json:{id:RUN,title:'Synthetic proof run'}};
    }
    if(route==='run' && request.method()==='GET') return {json:{id:RUN,title:'Synthetic proof run',status:'done',
      source:state.lastRun?.source||ORIGINAL,meta:{title:'Synthetic proof run',by:'fake:small',created:1,
        options:state.savedOptions||{}},
      state:{status:'done',progress:[1,1],asks:0,calls:0,cached:0,outputs:[],epistemic},trace:[],artifacts:[],log:''}};
    if(route==='paper/map') return {json:{map:[]}};
    if(route==='tightens') return {json:{tightens:[{id:JOB,title:'Synthetic tightening',status:'done',panel:['fake:a','fake:b']}]}};
    if(route==='tighten') return {json:job()};
    if(route==='tighten/adopt') {
      if(state.rejectAdoption) {state.rejectAdoption=false;return {status:409,json:{error:'Candidate hash is stale; review the current candidate.'}};}
      state.adopted=true;return {json:{ok:true,adoption:{status:'accepted'}}};
    }
    if(route==='evidence') return {json:{kernel:[],benches:[],matched:[
      {name:'Synthetic assigned comparison',ok:true,...matchedEvidence()},
      {name:'Legacy scope fixture',ok:true,summary:{},markdown:'Historical fixture without endpoint metadata.'},
      {name:'Torn synthetic record',ok:false,error:'Torn receipt <img src=x onerror=alert(1)>'}]}};
    if(route==='lang/evidence') return {json:{experiments:[]}};
    return undefined;
  }
  return {api,state};
}
async function diagnostics(t,page,requests,errors) {
  const stem='/tmp/symblic-reform-browser-'+t.name.replace(/[^a-z0-9]+/gi,'-').slice(0,100);
  try {
    await page.screenshot({path:stem+'.png',fullPage:true});
    await fs.writeFile(stem+'.html',await page.content());
    t.diagnostic(JSON.stringify({artifacts:stem,page:await page.evaluate(()=>({route:Studio.page,hash:location.hash,
      title:document.querySelector('#barNm')?.textContent,goal:document.querySelector('#sy-logic-goal')?.value,
      alerts:[...document.querySelectorAll('[role=alert]')].map(x=>x.textContent)})),
      requests:requests.map(({method,path,search,body})=>({method,path,search,body})),errors}));
  } catch(error) {t.diagnostic('Unable to collect browser diagnostics: '+error.message);}
}
async function journey(t,{mobile=false,theme='light',hash='logic',fixture=fixtures(),storage=null}={},body) {
  const {context,page,requests,errors}=await open(browser,'/automation-studio/symblic.html#'+hash,fixture.api,{mobile,storage});
  page.setDefaultTimeout(12000);
  try {
    await page.waitForFunction(()=>!!window.Studio);
    await page.evaluate(value=>Studio.setTheme(value),theme);
    if(hash==='write') await openWriteSettings(page);
    await body({page,requests,errors,state:fixture.state});
    assert.deepEqual(errors,[]);
  } catch(error) {await diagnostics(t,page,requests,errors);throw error;}
  finally {await context.close();}
}
async function openWriteSettings(page) {
  const summary=page.locator('.sy-native-settings > summary');
  await summary.waitFor();
  if(await summary.evaluate(node=>!node.parentElement.open)) await summary.click();
}
async function reload(page) {
  await page.reload();
  // A reload deliberately closes the advanced controls. Reopen them through
  // their disclosure before inspecting retained choices and prepared inputs.
  if(new URL(page.url()).hash==='#write') await openWriteSettings(page);
}
async function go(page,id,selector) {
  await page.evaluate(value=>Studio.go(value),id);
  await page.waitForFunction(value=>Studio.page===value && document.querySelector('#barNm')?.textContent===
    ({logic:'Logic',write:'Write',runs:'Runs',tighten:'Tighten',evidence:'Evidence'}[value]),id);
  if(id==='write') await openWriteSettings(page);
  if(selector) await page.locator(selector).waitFor();
}
async function prepare(page,{ok=true}={}) {
  const [response]=await Promise.all([
    page.waitForResponse(r=>new URL(r.url()).pathname==='/api/automation/symblic/logic/compile' && r.request().method()==='POST'),
    page.getByRole('button',{name:'Prepare proof task',exact:true}).click()]);
  assert.equal(response.ok(),ok,JSON.stringify(await response.json()));
  if(ok) await page.getByRole('button',{name:'Open in Write',exact:true}).waitFor();
  else await page.getByRole('alert').waitFor();
  return response.request().postDataJSON();
}
async function visualChecks(page) {
  assert.equal(await noHorizontalScroll(page),true);
  const viewport=page.viewportSize();
  const layout=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,inner:window.innerWidth}));
  assert.ok(layout.scroll<=viewport.width+1 && layout.inner<=viewport.width+1,
    'Content expanded the mobile viewport: '+JSON.stringify({layout,viewport}));
  const violations=await axe(page);
  const detail=violations.length ? await page.evaluate(async()=>({
    findings:(await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations,
    logic:[...document.querySelectorAll('.sy-logic .unit')].map(node=>({
      className:node.className,opacity:getComputedStyle(node).opacity,
      animation:getComputedStyle(node).animation,
      active:node.getAnimations().map(a=>({time:a.currentTime,state:a.playState}))
    }))
  })) : null;
  assert.deepEqual(violations,[],JSON.stringify(detail));
}

for (const mobile of [false,true]) test(`strict identity selection survives editing and reload ${mobile?'phone dark':'desktop light'}`,async t=>{
  const fixture=fixtures(); fixture.state.strictCapability=true;
  await journey(t,{hash:'write',mobile,theme:mobile?'dark':'light',fixture},async({page,state})=>{
    await page.getByText('Run model identity policy',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#syStrictPins')?.disabled===false);
    assert.equal(await page.locator('#syStrictPins').isChecked(),false);
    await page.locator('#syStrictPins').check();
    await page.locator('#sySrc').fill(ORIGINAL);
    await reload(page);
    await page.locator('#syStrictPins').waitFor();
    assert.equal(await page.locator('#syStrictPins').isChecked(),true);
    await visualChecks(page);
    await page.locator('#syRun').click();
    await page.locator('#syLoad').waitFor();
    assert.equal(state.lastRun.options.model_pins,'strict');
    state.savedOptions={profile:'verified',max_calls:3}; // loading an older run cannot silently clear the selection
    await reload(page); await page.locator(`[data-run="${RUN}"]`).click();
    await page.locator('#syLoad').waitFor();
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#syLoad').click();await openWriteSettings(page);
    await page.locator('#syStrictPins').waitFor();
    assert.equal(await page.locator('#syStrictPins').isChecked(),true);
    const loadedSource=await page.locator('#sySrc').inputValue();
    await page.locator('#sySrc').fill(loadedSource+'\nnote Temporary edit.\n');
    await page.locator('#syStrictPins').uncheck();
    await page.locator('#sySrc').fill(loadedSource);
    await reload(page);
    await page.getByText('Run model identity policy',{exact:true}).click();
    assert.equal(await page.locator('#syStrictPins').isChecked(),false);
    await page.locator('#syRun').click(); await page.locator('#syLoad').waitFor();
    assert.deepEqual(state.lastRun.options,{profile:'verified',max_calls:3,side_effects:false});
  });
});

test('unsupported strict identity stays selected and prevents dispatch until cleared',async t=>{
  const fixture=fixtures();
  const storage=()=>{
    localStorage.setItem('symblic-v2-draft','program Saved strict.\nlet n = 1.\nshow n.\n');
    sessionStorage.setItem('symblic-v3-task',JSON.stringify({
      source:'program Saved strict.\nlet n = 1.\nshow n.\n',inputs:{},options:{model_pins:'strict',profile:'verified'}}));
  };
  await journey(t,{hash:'write',fixture,storage},async({page,state,requests})=>{
    await page.locator('#syStrictPins').waitFor();
    assert.equal(await page.locator('#syStrictPins').isChecked(),true);
    assert.equal(await page.locator('#syStrictPins').isEnabled(),true);
    await page.locator('#syRun').click();
    await page.getByText('Strict model identities require a server update. Your selection has been retained.',{exact:true}).waitFor();
    assert.equal(state.lastRun,null);
    assert.equal(requests.filter(r=>r.path.endsWith('/run')&&r.method==='POST').length,0);
    await page.locator('#syStrictPins').uncheck();
    assert.equal(await page.locator('#syStrictPins').isDisabled(),true);
    await page.locator('#syRun').click(); await page.locator('#syLoad').waitFor();
    assert.deepEqual(state.lastRun.options,{profile:'verified',side_effects:false});
  });
});

test('loaded and restored task effects follow the visible checkbox',async t=>{
  const fixture=fixtures();
  fixture.state.savedOptions={side_effects:true,profile:'verified',max_calls:3};
  await journey(t,{hash:'write',fixture},async({page,state})=>{
    await page.locator('#syRun').waitFor();
    await page.locator('#syRun').click();
    await page.locator('#syLoad').waitFor();
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#syLoad').click();await openWriteSettings(page);
    await page.locator('#syFx').waitFor();
    assert.equal(await page.locator('#syFx').isChecked(),false);
    await reload(page);
    await page.locator('#syFx').waitFor();
    assert.equal(await page.locator('#syFx').isChecked(),false);
    await page.locator('#syRun').click();
    await page.locator('#syLoad').waitFor();
    assert.deepEqual(state.lastRun.options,{side_effects:false,profile:'verified',max_calls:3});
    await go(page,'write','#syFx');
    await page.locator('#syFx').check();
    await page.locator('#syRun').click();
    await page.locator('#syLoad').waitFor();
    assert.equal(state.lastRun.options.side_effects,true);
    await go(page,'write','#syFx');
    await page.locator('#syFx').uncheck();
    await page.locator('#syRun').click();
    await page.locator('#syLoad').waitFor();
    assert.equal(state.lastRun.options.side_effects,false);
  });
});

for(const mobile of [false,true]) for(const theme of ['light','dark']) {
  test(`logic compile, finite domains, recovery and caps ${mobile?'phone':'desktop'} ${theme}`,async t=>{
    await journey(t,{mobile,theme},async({page,requests})=>{
      await page.locator('#sy-logic-goal').waitFor();
      assert.equal(await page.locator('#sy-logic-calls').getAttribute('min'),'1');
      assert.equal(await page.locator('#sy-logic-calls').getAttribute('max'),'6');
      const initial=await prepare(page);
      assert.equal('domains' in initial,false);
      await page.getByRole('button',{name:'Open in Write',exact:true}).click();await openWriteSettings(page);
      await page.locator('#syInputs textarea[data-input="premises"]').waitFor();
      assert.equal(JSON.parse(await page.locator('#syInputs textarea[data-input="premises"]').inputValue()).human[1],'Socrates is human');
      await reload(page);
      await page.locator('#syInputs textarea[data-input="premises"]').waitFor();
      assert.match(await page.locator('#sySrc').inputValue(),/proof_steps_check/);
      assert.equal(JSON.parse(await page.locator('#syInputs textarea[data-input="goal"]').inputValue())[1],'Socrates is mortal');
      const runRead=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/automation/symblic/run' && r.request().method()==='GET');
      await page.locator('#syRun').click();
      await runRead;
      await page.locator('#syLock').waitFor(); // complete GET fixture rendered, not merely the early hash transition
      const payload=requests.find(r=>r.path==='/api/automation/symblic/run' && r.method==='POST').body;
      assert.equal(payload.options.profile,'verified');assert.equal(payload.options.max_calls,4);
      await go(page,'logic','#sy-logic-goal');
      await page.locator('#sy-logic-goal').fill('unquoted invalid formula');
      const invalid=await prepare(page,{ok:false});
      assert.equal(invalid.goal,'unquoted invalid formula');
      assert.equal(await page.getByRole('button',{name:'Open in Write',exact:true}).count(),0);
      await page.locator('#sy-logic-goal').fill('"<img src=x onerror=alert(1)>"');
      await prepare(page);
      assert.equal(await page.locator('.sy-logic img').count(),0);
      await page.getByText('Finite domains and quantified statements',{exact:true}).click();
      await page.locator('#sy-logic-domains').fill('{broken');
      const callsBefore=requests.filter(r=>r.path.endsWith('/logic/compile')).length;
      await page.getByRole('button',{name:'Prepare proof task',exact:true}).click();
      await page.getByRole('alert').waitFor();
      assert.match(await page.getByRole('alert').textContent(),/Finite domains must be a JSON object/);
      assert.equal(requests.filter(r=>r.path.endsWith('/logic/compile')).length,callsBefore);
      await page.locator('#sy-logic-domains').fill('{"People":["Ada","Ben"]}');
      await page.locator('#sy-logic-premises').fill('everyone: forall x in People: Kind(x:People)');
      await page.locator('#sy-logic-goal').fill('Kind(People["Ada"])');
      await page.locator('#sy-logic-calls').fill('7');
      await prepare(page,{ok:false});
      assert.match(await page.getByRole('alert').textContent(),/integer from 1 to 6/);
      await page.locator('#sy-logic-calls').fill('6');
      const finite=await prepare(page);
      assert.deepEqual(finite.domains,{People:['Ada','Ben']});assert.equal(finite.calls,6);
      await page.getByText('Declared finite universe · only these members are quantified over:',{exact:true}).waitFor();
      assert.equal(await page.locator('#sy-logic-domains').isVisible(),true);
      assert.ok(await page.locator('#stage [data-step]').count()>0,'Async component paint must preserve the Studio pager');
      await reload(page);await page.locator('#sy-logic-goal').waitFor();
      assert.equal(await page.locator('#sy-logic-domains').inputValue(),'{"People":["Ada","Ben"]}');
      assert.equal(await page.locator('#sy-logic-calls').inputValue(),'6');
      await prepare(page);await visualChecks(page);
      await page.getByRole('button',{name:'Open in Write',exact:true}).click();await openWriteSettings(page);
      await page.locator('#syInputs textarea[data-input="domains"]').waitFor();
      assert.match(await page.locator('#sySrc').inputValue(),/finite_steps_check/);
      assert.deepEqual(JSON.parse(await page.locator('#syInputs textarea[data-input="domains"]').inputValue()),{People:['Ada','Ben']});
    });
  });

  test(`provenance paging, candidate adoption and matched Evidence ${mobile?'phone':'desktop'} ${theme}`,async t=>{
    const fixture=fixtures();fixture.state.rejectAdoption=true;
    await journey(t,{mobile,theme,hash:'write',fixture,storage:()=>localStorage.setItem('symblic-v2-draft','program Original fixture.\nlet answer = 8.\nshow answer.\n')},async({page,requests,state})=>{
      await page.locator('#syRun').waitFor();await page.locator('#syRun').click();
      await page.getByText('Claim provenance · 45 recorded claims',{exact:true}).waitFor();
      assert.equal(await page.locator('[data-claim-page] .card').count(),0,'Claims load only when expanded');
      await page.getByText('Claim provenance · 45 recorded claims',{exact:true}).click();
      await page.locator('[data-claim-page] .card').last().waitFor();
      assert.equal(await page.locator('[data-claim-page] .card').count(),20);
      assert.match(await page.locator('[data-claim-page] .card').nth(0).textContent(),/130 root claim\(s\).*1 listed, 129 retained in summary/);
      assert.match(await page.locator('[data-claim-page] .card').nth(1).textContent(),/1 listed root claim\(s\); total unavailable/);
      assert.match(await page.locator('[data-claim-page] .card').nth(2).textContent(),/1 root claim\(s\)/);
      assert.equal(await page.locator('[data-claim="0"] pre').textContent(),'');
      await page.locator('[data-claim="0"] summary').click();
      await page.waitForFunction(()=>document.querySelector('[data-claim="0"] pre')?.textContent.includes('"revision": 1'));
      assert.equal(await page.locator('.sy-epistemic img').count(),0);
      await page.getByRole('button',{name:'Next claims',exact:true}).click();
      assert.equal(await page.locator('[data-claim-page] .card').count(),20);
      assert.match(await page.locator('[data-claim-page]').textContent(),/21–40 of 45/);
      await page.getByRole('button',{name:'Next claims',exact:true}).click();
      assert.equal(await page.locator('[data-claim-page] .card').count(),5);
      assert.equal(await page.getByRole('button',{name:'Next claims',exact:true}).isDisabled(),true);
      await page.getByRole('button',{name:'Previous claims',exact:true}).click();
      assert.equal(await page.locator('[data-claim-page] .card').count(),20);
      await visualChecks(page);
      await go(page,'tighten','[data-tj]');await page.locator('[data-tj]').click();
      await page.locator('#syTAdopt').waitFor();
      assert.match(await page.locator('#stage').textContent(),/Fidelity: unknown/);
      assert.match(await page.locator('#stage').textContent(),/R1.*unmapped/);
      assert.equal(await page.evaluate(()=>localStorage.getItem('symblic-v2-draft')),ORIGINAL);
      await page.locator('#syTAdopt').click();
      await page.getByText('Candidate hash is stale; review the current candidate.',{exact:true}).waitFor();
      assert.equal(state.adopted,false);
      await page.locator('#syTAdopt').click();
      await page.getByText('Saved owner choice: accepted',{exact:true}).waitFor();
      const adoption=requests.filter(r=>r.path.endsWith('/tighten/adopt')).map(r=>r.body);
      assert.equal(adoption.length,2);
      assert.deepEqual(adoption[1],{id:JOB,original_sha256:'b'.repeat(64),candidate_sha256:'c'.repeat(64),audit_sha256:'a'.repeat(64)});
      assert.equal(await page.evaluate(()=>localStorage.getItem('symblic-v2-draft')),ORIGINAL,'Adoption records do not silently replace the editor');
      page.once('dialog',dialog=>dialog.accept());
      await page.locator('#syTUse').click();await page.locator('#sySrc').waitFor();
      assert.equal(await page.locator('#sySrc').inputValue(),CANDIDATE);
      await go(page,'evidence','#syLangEv');
      await page.getByText('Matched evaluation Synthetic assigned comparison',{exact:true}).waitFor();
      await page.getByText('Papers, certifications and crystals',{exact:true}).waitFor();
      const matched=page.locator('.sy-md').filter({hasText:'Synthetic assigned comparison'});
      assert.match(await matched.textContent(),/0\/2/);assert.match(await matched.textContent(),/1\/2/);
      assert.match(await matched.textContent(),/False acceptance/);assert.match(await matched.textContent(),/unmeasured/);
      assert.match(await matched.textContent(),/Scope: one typed decision per task/);
      assert.match(await matched.textContent(),/Historical implementation/);
      assert.match(await matched.textContent(),/These results describe the recorded version/);
      await page.getByText('Endpoint and implementation-version metadata were not recorded for this evaluation.',{exact:true}).waitFor();
      await page.getByText('Torn receipt <img src=x onerror=alert(1)>',{exact:true}).waitFor();
      assert.equal(await page.locator('.sy-md img').count(),0);
      await visualChecks(page);
    });
  });
}

for(const mobile of [false,true]) test(`late compiler response owns only its Logic view ${mobile?'phone':'desktop'}`,async t=>{
  const fixture=fixtures();let release;
  await journey(t,{mobile,theme:mobile?'dark':'light',fixture},async({page})=>{
    await page.locator('#sy-logic-goal').waitFor();await prepare(page);
    await page.evaluate(()=>{
      const original=Studio.api; window.__logicRepliesSettled=0;
      Studio.api=async(...args)=>{
        if(!String(args[0]).endsWith('/logic/compile')) return original(...args);
        try {return await original(...args);} finally {window.__logicRepliesSettled++;}
      };
    });
    fixture.state.compileGate=new Promise(resolve=>{release=resolve;});
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/logic/compile'));
    const dispatch=page.waitForRequest(r=>new URL(r.url()).pathname.endsWith('/logic/compile'));
    await page.getByRole('button',{name:'Prepare proof task',exact:true}).click();await dispatch;
    assert.equal(await page.getByRole('button',{name:'Open in Write',exact:true}).count(),0,'Pending compilation must invalidate an old candidate action');
    await go(page,'evidence','#syLangEv');
    await page.getByText('Papers, certifications and crystals',{exact:true}).waitFor();
    release();await pending;
    // Observe Studio.api settlement; the next browser task runs after the
    // prepare continuation and its finally/paint microtasks have completed.
    await page.waitForFunction(()=>window.__logicRepliesSettled===1);
    assert.equal(await page.locator('.sy-logic').count(),0,'A late response must not overwrite Evidence');
    assert.equal(await page.locator('#barNm').textContent(),'Evidence');
    await go(page,'logic','#sy-logic-goal');
    await page.getByRole('button',{name:'Open in Write',exact:true}).waitFor();
    assert.ok(await page.locator('#stage [data-step]').count()>0);
    await visualChecks(page);
  });
});

for(const legacy of [false,true]) test(`proof format choice preserves ${legacy?'legacy term drafts':'new step drafts'} and handoff`,async t=>{
  const fixture=fixtures();
  const storage=legacy?()=>{if(!sessionStorage.getItem('symblic-logic-draft-v1'))sessionStorage.setItem('symblic-logic-draft-v1',JSON.stringify({
    premises:'human: "Socrates is human"\nrule: "Socrates is human" implies "Socrates is mortal"',
    goal:'"Socrates is mortal"',calls:4,domains:''}));}:null;
  await journey(t,{mobile:!legacy,theme:legacy?'light':'dark',fixture,storage},async({page,requests})=>{
    await page.locator('#sy-logic-goal').waitFor();
    await page.getByText('Proof format',{exact:true}).click();
    assert.equal(await page.locator('#sy-logic-format').inputValue(),legacy?'terms':'steps');
    const initial=await prepare(page);
    assert.equal(initial.certificate_format,legacy?'terms':'steps');
    await page.getByText('Prepared proof format: '+(legacy?'Nested proof terms':'Flat proof steps'),{exact:true}).waitFor();
    const changed=legacy?'steps':'terms';
    await page.locator('#sy-logic-format').selectOption(changed);
    assert.equal(await page.getByRole('button',{name:'Open in Write',exact:true}).count(),0,'Changing the certificate format invalidates the prepared task');
    assert.match(await page.locator('[data-logic-result]').textContent(),/Prepare it again/);
    assert.equal(JSON.parse(await page.evaluate(()=>sessionStorage.getItem('symblic-logic-draft-v1'))).certificate_format,changed);
    let release;fixture.state.compileGate=new Promise(resolve=>{release=resolve;});
    const dispatch=page.waitForRequest(request=>new URL(request.url()).pathname.endsWith('/logic/compile'));
    await page.getByRole('button',{name:'Prepare proof task',exact:true}).click();
    const pendingRequest=await dispatch;assert.equal(pendingRequest.postDataJSON().certificate_format,changed);
    assert.equal(await page.locator('#sy-logic-format').isDisabled(),true);
    assert.equal(await page.locator('#sy-logic-goal').isDisabled(),true);
    release();fixture.state.compileGate=null;
    await page.getByRole('button',{name:'Open in Write',exact:true}).waitFor();
    await page.getByText('Prepared proof format: '+(changed==='steps'?'Flat proof steps':'Nested proof terms'),{exact:true}).waitFor();
    assert.equal(await page.locator('#sy-logic-format').isDisabled(),false);
    await visualChecks(page);
    await page.getByRole('button',{name:'Open in Write',exact:true}).click();await openWriteSettings(page);await page.locator('#sySrc').waitFor();
    const handoff=await page.locator('#sySrc').inputValue();assert.match(handoff,/Construct a logical derivation/);
    const inputs=await page.locator('#syInputs textarea[data-input="proof_rules"]').inputValue();assert.ok(JSON.parse(inputs));
    await reload(page);await page.locator('#sySrc').waitFor();assert.equal(await page.locator('#sySrc').inputValue(),handoff);
    await go(page,'logic','#sy-logic-goal');await page.getByText('Proof format',{exact:true}).click();
    assert.equal(await page.locator('#sy-logic-format').inputValue(),changed);
    const restored=await prepare(page);assert.equal(restored.certificate_format,changed);
    assert.equal(requests.filter(row=>row.path==='/api/automation/symblic/run'&&row.method==='POST').length,0,'Preparing and transferring a format makes no model run');
  });
});

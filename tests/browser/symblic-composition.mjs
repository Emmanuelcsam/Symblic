// Private composition integration. All HTTP/provider/store interactions are fake.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {test, launch, open, axe, noHorizontalScroll, root} from './host-harness.mjs';
const data=JSON.parse(await fs.readFile(new URL('./fixtures/symblic-composition.json',import.meta.url),'utf8'));
const composition=data.composition, expanded=data.expanded, flat={graph:data.flat_example.graph,policy:data.flat_example.policy};
let browser;
before(async()=>{browser=await launch();});after(async()=>{await browser?.close();});
function fixture() {
  const state={gate:null,exampleGate:null,error:null,malformed:false,run:false};
  const api=async(request,url)=>{
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'mock',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route==='graph/runs')return {json:{runs:[]}};
    if(route==='graph/example')return state.flatExampleRaw?{body:state.flatExampleRaw}:{json:data.flat_example};
    if(route==='graph/composition-example') {if(state.exampleGate)await state.exampleGate;return state.compositionExampleRaw?{body:state.compositionExampleRaw}:{json:composition};}
    if(route==='graph/compose') {
      if(state.gate)await state.gate;
      if(state.error)return {status:state.error,json:{error:'<img src=x onerror=alert(1)> unavailable fixture'}};
      return state.expandedRaw?{body:state.expandedRaw}:{json:state.malformed?{ok:true,draft:expanded.draft}:expanded};
    }
    if(route==='graph/check')return {json:{...expanded.check,ok:true}};
    if(route==='graph/run'&&request.method()==='POST'){state.run=true;return {json:{id:'000000000009'}};}
    if(route==='graph/run')return {json:{id:'000000000009',state:{status:'succeeded',reserved_calls:0,nodes:[]},active:false,can_resume:false}};
    return {json:{}};
  };
  return {state,api};
}
async function visit(t,opts,body) {
  const fake=opts.fake||fixture();const {context,page,requests,errors}=await open(browser,'/automation-studio/symblic.html#graphs',fake.api,opts);
  page.setDefaultTimeout(8000);
  try {
    await page.locator('.sy-graphs').waitFor();await page.getByRole('heading',{name:opts.expectedTitle||flat.graph.id,exact:true}).waitFor();
    await page.evaluate(theme=>Studio.setTheme(theme),opts.theme||'light');
    await page.getByText('Advanced: compose reusable graph fragments',{exact:true}).click();
    await page.getByText('Edit graph and routing policy JSON',{exact:true}).click();
    await body({page,requests,...fake});assert.deepEqual(errors,[]);
  } catch(error) {
    const name=path.join(root,'../ui-evidence','failure-'+t.name.replace(/[^a-z0-9]+/gi,'-'));
    await fs.mkdir(path.dirname(name),{recursive:true});await page.screenshot({path:name+'.png',fullPage:true});await fs.writeFile(name+'.html',await page.content());throw error;
  } finally {await context.close();}
}
async function example(page) {await page.getByRole('button',{name:'Load reusable example',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#sy-graph-composition')?.value.includes('composition'));}
async function checked(page) {await page.getByRole('button',{name:'Check graph',exact:true}).click();await page.getByRole('heading',{name:'Reviewed graph contract',exact:true}).waitFor();}
async function expand(page) {await page.getByRole('button',{name:'Expand to flat draft',exact:true}).click();await page.getByText('Expanded into the flat draft. Check graph before running; expansion does not start a run.',{exact:true}).waitFor();}
async function layout(page) {assert.equal(await noHorizontalScroll(page),true);assert.deepEqual(await axe(page),[]);assert.equal(await page.locator('#sy-graph-composition').evaluate(e=>getComputedStyle(e).fontSize),'16px');}
for(const [mobile,theme] of [[false,'light'],[true,'dark']]) test(`composition explicit handoff and session restore ${mobile?'phone':'desktop'} ${theme}`,async t=>{
  await visit(t,{mobile,theme},async({page,requests})=>{
    assert.equal(requests.filter(r=>r.path.includes('composition')||r.path.endsWith('/compose')).length,0,'No auto composition load/expand');
    const prior=await page.locator('#sy-graph-json').inputValue();await checked(page);await example(page);
    assert.equal(await page.locator('#sy-graph-json').inputValue(),prior);
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isEnabled(),true,'Loading authoring source preserves flat check');
    await expand(page);
    assert.deepEqual(JSON.parse(await page.locator('#sy-graph-json').inputValue()),expanded.draft);
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
    assert.equal(await page.locator('[data-graph-check]').count(),0);
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
    assert.match(await page.locator('[data-composition-status]').textContent(),/matches these drafts/);
    await page.getByText('Composition source, mapping and expansion receipt',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-composition-receipt] pre')?.textContent.includes('definition_sha256'));
    assert.match(await page.locator('[data-composition-receipt] pre').textContent(),new RegExp(expanded.manifest.expander_sha256));
    await layout(page);
    await fs.mkdir(path.join(root,'../ui-evidence'),{recursive:true});await page.screenshot({path:path.join(root,'../ui-evidence',`composition-${mobile?'phone':'desktop'}-${theme}.png`),fullPage:true});
    const raw=await page.locator('#sy-graph-json').inputValue();await page.locator('#sy-graph-json').fill(raw+'\n');
    assert.match(await page.locator('[data-composition-status]').textContent(),/Detached/);
    await page.reload();await page.locator('.sy-graphs').waitFor();
    assert.equal(await page.locator('#sy-graph-json').inputValue(),raw+'\n');assert.deepEqual(JSON.parse(await page.locator('#sy-graph-composition').inputValue()),composition);
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true);
    await page.getByText('Advanced: compose reusable graph fragments',{exact:true}).click();
    assert.match(await page.locator('[data-composition-status]').textContent(),/Detached/);
    await expand(page);await checked(page);await page.getByRole('button',{name:'Run checked graph'}).click();
    await page.waitForFunction(()=>document.querySelector('[data-graph-status]')?.textContent.includes('succeeded'));
    const runs=requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST');assert.equal(runs.length,1);
    assert.deepEqual(runs[0].body,{...expanded.draft,expected_graph_hash:expanded.check.graph_hash,expected_policy_hash:expanded.check.policy_hash});
    assert.deepEqual(requests.find(r=>r.path.endsWith('/compose')).body,composition);
  });
});
for(const edit of ['flat','composition','policy'])test(`composition late expansion preserves ${edit} edits`,async t=>{
  const fake=fixture();let release;fake.state.gate=new Promise(r=>{release=r;});
  await visit(t,{fake},async({page,requests})=>{
    await example(page);const before=await page.locator('#sy-graph-json').inputValue();
    await page.getByRole('button',{name:'Expand to flat draft'}).click();await page.waitForFunction(()=>document.querySelector('[data-composition-controls]')?.textContent.includes('Expanding'));
    let expected=before;
    if(edit==='flat') {expected=before+'\n ';await page.locator('#sy-graph-json').fill(expected);}
    if(edit==='composition')await page.locator('#sy-graph-composition').fill(JSON.stringify(composition)+'\n ');
    if(edit==='policy') {const policy=structuredClone(flat.policy);policy.order=['copied'];policy.routes=[{...policy.routes[0],id:'copied'}];await page.evaluate(value=>SymblicGraphs.importPolicy(value,{policy_hash:'copied-policy'}),policy);expected=JSON.stringify({graph:flat.graph,policy},null,2);}
    release();await page.getByText('The draft changed while the request was pending. Its response was not applied.',{exact:true}).waitFor();
    assert.equal(await page.locator('#sy-graph-json').inputValue(),expected);assert.equal(await page.locator('[data-composition-status]').count(),0);
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
  });
});
test('composition mount epoch rejects old response even after return and newer request',async t=>{
  const fake=fixture();let release;fake.state.gate=new Promise(r=>{release=r;});
  await visit(t,{fake},async({page,requests,state})=>{
    await example(page);const original=await page.locator('#sy-graph-json').inputValue();
    await page.evaluate(()=>{const call=Studio.api;window.settledComposition=0;Studio.api=async(...args)=>{try{return await call(...args);}finally{if(args[0].endsWith('/compose'))window.settledComposition++;}};});
    await page.getByRole('button',{name:'Expand to flat draft'}).click();await page.waitForFunction(()=>document.querySelector('[data-composition-controls]')?.textContent.includes('Expanding'));
    await page.evaluate(()=>Studio.go('write'));await page.locator('#sySrc').waitFor();
    await page.evaluate(()=>Studio.go('graphs'));await page.locator('.sy-graphs').waitFor();
    state.gate=null;state.malformed=true;
    await page.getByRole('button',{name:'Expand to flat draft'}).click();await page.getByText('The server returned an incomplete composition expansion. Both drafts were preserved.',{exact:true}).waitFor();
    release();await page.waitForFunction(()=>window.settledComposition===2);
    assert.equal(await page.locator('#sy-graph-json').inputValue(),original);assert.equal(await page.locator('[data-composition-status]').count(),0);
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
  });
});
test('composition failures preserve raw drafts and existing flat check with inert errors',async t=>{
  await visit(t,{mobile:true,theme:'dark'},async({page,requests,state})=>{
    await checked(page);await example(page);const raw=await page.locator('#sy-graph-json').inputValue(), comp=await page.locator('#sy-graph-composition').inputValue();
    for(const code of [503,404,400]) {state.error=code;await page.getByRole('button',{name:'Expand to flat draft'}).click();await page.locator('[data-composition-controls] [role=alert]').waitFor();
      assert.equal(await page.locator('#sy-graph-json').inputValue(),raw);assert.equal(await page.locator('#sy-graph-composition').inputValue(),comp);assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isEnabled(),true);assert.equal(await page.locator('.sy-graphs img').count(),0);}
    state.error=null;await page.locator('#sy-graph-composition').fill('{invalid');const before=requests.filter(r=>r.path.endsWith('/compose')).length;
    await page.getByRole('button',{name:'Expand to flat draft'}).click();await page.getByText('The composition document must be valid JSON containing composition and policy.',{exact:true}).waitFor();assert.equal(requests.filter(r=>r.path.endsWith('/compose')).length,before);
    await page.locator('#sy-graph-composition').fill(JSON.stringify({composition:{id:'é'.repeat(524288)},policy:{}}));
    await page.getByRole('button',{name:'Expand to flat draft'}).click();await page.getByText('Composition documents are limited to 1 MiB.',{exact:true}).waitFor();assert.equal(requests.filter(r=>r.path.endsWith('/compose')).length,before);
    await layout(page);
  });
});
test('late reusable example cannot erase composition edits and old flat sessions still load',async t=>{
  const fake=fixture();let release;fake.state.exampleGate=new Promise(r=>{release=r;});
  await visit(t,{fake,expectedTitle:'Old',storage:()=>sessionStorage.setItem('symblic-graph-draft-v1',JSON.stringify({raw:JSON.stringify({graph:{id:'Old',nodes:[]},policy:{}}),selected:''}))},async({page,requests})=>{
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/example')).length,0);
    await page.getByRole('button',{name:'Load reusable example'}).click();
    await page.waitForFunction(()=>document.querySelector('[data-composition-controls]')?.textContent.includes('Loading reusable'));
    await page.locator('#sy-graph-composition').fill('{unfinished author text');release();
    await page.getByText('The draft changed while the request was pending. Its response was not applied.',{exact:true}).waitFor();
    assert.equal(await page.locator('#sy-graph-composition').inputValue(),'{unfinished author text');
    assert.equal(JSON.parse(await page.locator('#sy-graph-json').inputValue()).graph.id,'Old');
  });
});


test('graph numeric authoring refuses unsafe integers before dispatch or adoption',async t=>{
  await visit(t,{mobile:true,theme:'dark'},async({page,requests,state})=>{
    await checked(page);await example(page);
    const flatRaw=await page.locator('#sy-graph-json').inputValue();
    const checkRaw=await page.locator('[data-graph-check]').textContent();
    const posts=()=>requests.filter(r=>r.path.endsWith('/compose'));
    function exactSource(token) {
      const doc=structuredClone(composition), literal=doc.composition.instances[0].inputs.request.literal;
      literal.value='EXACT_NUMBER_PLACEHOLDER';
      literal.value_id=createHash('sha256').update(token==='-0'?'0':token).digest('hex');
      literal.assumptions=['Quoted "9007199254740993" and \\ 1e999 remain text.'];
      return JSON.stringify(doc).replace('"EXACT_NUMBER_PLACEHOLDER"',token);
    }
    async function unchanged(raw) {
      assert.equal(await page.locator('#sy-graph-composition').inputValue(),raw);
      assert.equal(await page.locator('#sy-graph-json').inputValue(),flatRaw);
      assert.equal(await page.locator('[data-graph-check]').textContent(),checkRaw);
      assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isEnabled(),true);
      assert.equal(await page.locator('[data-composition-status]').count(),0);
    }
    for(const token of ['9007199254740993','-9007199254740993','9007199254740992','-9007199254740992','999999999999999999999999999999','1.0','1e0','1e9999','-1e9999','0.00000000000000000000001']) {
      const raw=exactSource(token), count=posts().length;await page.locator('#sy-graph-composition').fill(raw);
      await page.getByRole('button',{name:'Expand to flat draft'}).click();
      await page.locator('[data-composition-controls] [role=alert]').filter({hasText:'bin/symblic graph compose FILE.json --flat'}).waitFor();
      assert.equal(posts().length,count,'Rejected original numeric lexeme must never be posted: '+token);await unchanged(raw);
    }
    // Both safe boundaries and signed zero retain exact values. A server refusal
    // keeps the prior flat check, while its captured request verifies transport.
    state.error=400;
    for(const token of ['9007199254740991','-9007199254740991','-0']) {
      const raw=exactSource(token);await page.locator('#sy-graph-composition').fill(raw);
      await page.getByRole('button',{name:'Expand to flat draft'}).click();
      await page.locator('[data-composition-controls] [role=alert]').filter({hasText:'unavailable fixture'}).waitFor();
      const literal=posts().at(-1).body.composition.instances[0].inputs.request.literal;
      assert.equal(literal.value,token==='-0'?0:Number(token));assert.match(literal.assumptions[0],/9007199254740993/);await unchanged(raw);
    }
    state.error=null;
    // Actual HTTP response text is decoded by Studio.api: unsafe integers must
    // still refuse before replacing either draft or installing a receipt.
    state.compositionExampleRaw=exactSource('9007199254740993');
    let raw=await page.locator('#sy-graph-composition').inputValue();
    await page.getByRole('button',{name:'Load reusable example'}).click();
    await page.locator('[data-composition-controls] [role=alert]').filter({hasText:'bin/symblic graph compose FILE.json --flat'}).waitFor();await unchanged(raw);
    state.compositionExampleRaw=null;
    raw=JSON.stringify(composition);await page.locator('#sy-graph-composition').fill(raw);
    state.expandedRaw=JSON.stringify(expanded).replace('"value":3','"value":9007199254740993');
    assert.notEqual(state.expandedRaw,JSON.stringify(expanded));
    await page.getByRole('button',{name:'Expand to flat draft'}).click();
    await page.locator('[data-composition-controls] [role=alert]').filter({hasText:'bin/symblic graph compose FILE.json --flat'}).waitFor();await unchanged(raw);
    state.flatExampleRaw=JSON.stringify(data.flat_example).replace('"iterations":1','"iterations":9007199254740993');
    assert.notEqual(state.flatExampleRaw,JSON.stringify(data.flat_example));
    await page.getByRole('button',{name:'Load deterministic example'}).click();
    await page.locator('[data-graph-controls] [role=alert]').filter({hasText:'bin/symblic graph compose FILE.json --flat'}).waitFor();await unchanged(raw);
    // Existing flat authoring cannot silently normalize unsupported numeric text.
    const count=requests.filter(r=>r.path.endsWith('/graph/check')).length;
    const badFlat=flatRaw.replace('"iterations": 1','"iterations": 9007199254740993');assert.notEqual(badFlat,flatRaw);
    await page.locator('#sy-graph-json').fill(badFlat);await page.getByRole('button',{name:'Check graph',exact:true}).click();
    await page.locator('[data-graph-controls] [role=alert]').filter({hasText:'bin/symblic graph compose FILE.json --flat'}).waitFor();
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/check')).length,count);assert.equal(await page.locator('#sy-graph-json').inputValue(),badFlat);
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
    state.expandedRaw=null;await expand(page);
    assert.deepEqual(JSON.parse(await page.locator('#sy-graph-json').inputValue()),expanded.draft);
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isDisabled(),true,'Valid expansion still requires a new flat check');
    await layout(page);
  });
});

test('graph malformed escaped strings refuse promptly and preserve the checked flat draft',async t=>{
  await visit(t,{mobile:true,theme:'dark'},async({page,requests})=>{
    await checked(page);await example(page);
    const flatRaw=await page.locator('#sy-graph-json').inputValue();
    const checkRaw=await page.locator('[data-graph-check]').textContent();
    const postCount=requests.filter(r=>r.path.endsWith('/compose')).length;
    const prefix='{"composition":"', limit=1048576;
    const raw=prefix+'\\"'.repeat(Math.floor((limit-prefix.length)/2))+'\\'.repeat((limit-prefix.length)%2);
    assert.equal(Buffer.byteLength(raw),limit);
    await page.locator('#sy-graph-composition').fill(raw);
    await page.getByRole('button',{name:'Expand to flat draft'}).click();
    await page.getByText('The composition document must be valid JSON containing composition and policy.',{exact:true}).waitFor();
    assert.equal(requests.filter(r=>r.path.endsWith('/compose')).length,postCount);
    assert.equal(await page.locator('#sy-graph-composition').inputValue(),raw);
    assert.equal(await page.locator('#sy-graph-json').inputValue(),flatRaw);
    assert.equal(await page.locator('[data-graph-check]').textContent(),checkRaw);
    assert.equal(await page.getByRole('button',{name:'Run checked graph'}).isEnabled(),true);
    assert.equal(await page.locator('[data-composition-status]').count(),0);
    assert.equal(requests.filter(r=>r.path.endsWith('/graph/run')&&r.method==='POST').length,0);
    await layout(page);
  });
});

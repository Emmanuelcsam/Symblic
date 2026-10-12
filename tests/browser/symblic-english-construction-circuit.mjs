// Source-only construction circuit. Fixture comes from the real compiler and source checker.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import test from 'node:test';
import {test as pageTest, launch as launchCircuitBrowser} from './host-harness.mjs';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const saved=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/symblic-english-construction.json'),'utf8'));
const context={window:{}};
vm.runInNewContext(await fs.readFile(path.join(root, 'web/studio/symblic-english-circuit.js'),'utf8'),context);
const fixture=()=>JSON.parse(JSON.stringify(saved));
const project=(compiled,source)=>JSON.parse(JSON.stringify(context.window.SymblicEnglishCircuit.project(compiled,source)));

test('construction keeps every authored statement and only declared model memory',()=>{
  const f=fixture(),p=project(f.compiled,f.source),units=f.compiled.construction.units;
  assert.equal(p.available,true);assert.equal(p.mode,'construction');assert.equal(p.nodes.length,f.compiled.statements.length);
  assert.deepEqual(p.nodes.map(n=>n.text),f.compiled.statements.map(n=>n.text));
  for(const unit of units){
    const worker=p.nodes.find(n=>n.kind==='ask'&&n.binds.includes(unit.binding));assert.ok(worker);
    assert.deepEqual(worker.incoming.map(e=>e.name),unit.selected_bindings);
    const selected=p.nodes.find(n=>n.kind==='using'&&n.parent===worker.id);
    assert.deepEqual(selected.selected.map(e=>e.name),unit.selected_bindings);
  }
  assert.equal(p.nodes.filter(n=>n.kind==='ask').length,7);
  assert.equal(p.nodes.filter(n=>n.kind==='accept').length,7);
  assert.equal(p.nodes.reduce((n,row)=>n+row.checks.length,0),14);
  assert.ok(p.nodes.flatMap(n=>n.checks).every(check=>check.status==='not_run'));
  assert.deepEqual(p.nodes.at(-1).incoming.map(e=>e.name),f.compiled.construction.output.selected_bindings);
  assert.ok(p.nodes.some(n=>n.kind==='presentation'));
  assert.ok(f.compiled.check.plan.some(row=>row.depth>0),'generated playback loop is expected and does not hide author source');
});
test('native scoped and assembly check reads stay separate from worker context',()=>{
  const f=fixture(),p=project(f.compiled,f.source),second=f.compiled.construction.units[1];
  const worker=p.nodes.find(n=>n.binds.includes(second.binding)),gate=p.nodes.find(n=>n.kind==='accept'&&n.parent===worker.id);
  assert.deepEqual(worker.incoming,[],'movement selects no earlier work');
  assert.deepEqual(gate.incoming.map(e=>e.name),['built_step_2','built_step_1'],'assembly still checks earlier source compatibility');
  assert.ok(gate.checks.every(check=>check.status==='not_run'));
});
test('construction refuses stale text, failed checks and unknown schemas',()=>{
  const f=fixture();assert.equal(project(f.compiled,f.source.replace('Matrix rain','Wrong title')).available,false);
  f.compiled.check.ok=false;assert.equal(project(f.compiled,f.source).available,false);
  f.compiled.check.ok=true;f.compiled.construction.version='unrecognized';assert.equal(project(f.compiled,f.source).available,false);
});
test('construction refuses missing, future, duplicate and mismatched dependency metadata',()=>{
  for(const mutate of [
    c=>{c.construction.units[0].selected_bindings=['built_step_7'];c.construction.units[0].selected_steps=['animation'];},
    c=>{c.construction.units[2].selected_bindings=['built_step_2','built_step_2'];c.construction.units[2].selected_steps=['movement','movement'];},
    c=>{c.construction.units[2].selected_steps=['invented'];},
    c=>{c.construction.units[1].statement_ids=c.construction.units[0].statement_ids;},
    c=>{delete c.construction.output;},
    c=>{c.construction.unmapped_statements=[3];}
  ]){const f=fixture();mutate(f.compiled);assert.equal(project(f.compiled,f.source).available,false);}
});
test('construction uses complete code-point spans and normalized line endings',()=>{
  const f=fixture();assert.equal(project(f.compiled,'\uFEFF'+f.source.replaceAll('\n','\r\n')).available,true);
  f.compiled.statements[4].end_col--;assert.equal(project(f.compiled,f.source).available,false);
});

const ORIGIN='http://127.0.0.1:18774';
const TYPES={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.woff2':'font/woff2','.svg':'image/svg+xml'};
export async function runConstructionCircuitJourney(browser,{assetRoot=root,checkoutRoot=root,mobile=false,screenshotDir=null,fixtureData=saved}={}){
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1400,height:1000},isMobile:mobile,hasTouch:mobile,colorScheme:mobile?'dark':'light'});
  const calls=[],errors=[];const f=JSON.parse(JSON.stringify(fixtureData));
  const workerCount=f.compiled.construction.units.length;
  await context.addInitScript(source=>{window.WebSocket=class {close(){}};sessionStorage.setItem('symblic-english-v1',JSON.stringify({source,id:'',by:'ollama:qwen3:4b-instruct',calls:'32',retries:'2',budget:'12000'}));},f.source);
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());if(url.origin!==ORIGIN)return route.abort();
    if(url.pathname.startsWith('/api/')){
      let body=null;try{body=request.postDataJSON();}catch(_){/* GET */}calls.push({method:request.method(),path:url.pathname,body});
      if(url.pathname.endsWith('/editor/check')){
        const exact=body.language==='english'&&body.source===f.source;
        return route.fulfill({json:{version:1,language:body.language,source_length_utf16:body.source.length,available:true,ok:exact,diagnostics:[],
          check:exact?{ok:true,compiled:f.compiled,native:f.compiled.check}:null}});
      }
      if(url.pathname.endsWith('/english/examples'))return route.fulfill({json:{version:1,examples:{}}});
      if(url.pathname.endsWith('/meta'))return route.fulfill({json:{version:'fixture',examples:[],features:{}}});
      if(url.pathname.endsWith('/runs'))return route.fulfill({json:{runs:[]}});
      if(url.pathname.endsWith('/programs'))return route.fulfill({json:{programs:[]}});
      return route.fulfill({json:{}});
    }
    const relative=url.pathname.replace(/^\//,'');
    for(const base of [assetRoot,checkoutRoot]){
      const filename=path.resolve(base,relative);if(!filename.startsWith(path.resolve(base)+path.sep))return route.fulfill({status:403});
      try{return await route.fulfill({body:await fs.readFile(filename),contentType:TYPES[path.extname(filename)]||'application/octet-stream'});}catch(_){/* staged fallback */}
    }
    return route.fulfill({status:404,body:''});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.goto(ORIGIN+'/automation-studio/symblic.html#english');await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    await page.locator('[data-en-circuit-panel] > summary').click();
    await page.locator('.sy-ec-component').first().waitFor();
    assert.equal(await page.locator('.sy-ec-component').count(),f.compiled.statements.length);
    assert.equal(await page.locator('.sy-ec-component[data-kind=ask]').count(),workerCount);
    assert.equal(await page.locator('.sy-ec-component[data-kind=accept]').count(),workerCount);
    assert.equal(await page.locator('.sy-ec-component[data-kind=presentation]').count(),1);
    assert.equal(await page.locator('.sy-ec-component[data-kind=finish]').count(),workerCount);
    assert.match(await page.locator('.sy-en-circuit').innerText(),/Parsed connections; checks not run/);
    const frames=f.compiled.construction.units.find(unit=>['frames','frames_from_columns'].includes(unit.contract));
    const ask=f.compiled.statements.find(statement=>frames.statement_ids.includes(statement.index)&&statement.kind==='ask');
    const worker=page.locator('.sy-ec-component[data-statement="'+ask.index+'"]');
    const labels=await worker.locator('.sy-ec-connections button').allTextContents();
    assert.deepEqual(labels.map(label=>label.split(' ← ')[0]),frames.selected_steps);
    const movement=f.compiled.construction.units.find(unit=>unit.contract==='movement');
    const head=f.compiled.construction.units.find(unit=>unit.contract==='heads');
    const headAsk=f.compiled.statements.find(statement=>head.statement_ids.includes(statement.index)&&statement.kind==='ask');
    const link=page.locator('.sy-ec-component[data-statement="'+headAsk.index+'"] .sy-ec-connections button').first();
    if(mobile)await link.tap();else await link.click();
    const expected=f.source.split('\n')[movement.line-1];
    assert.equal(await page.locator('#sy-en-source').evaluate(el=>el.value.slice(el.selectionStart,el.selectionEnd)),expected);
    const gate=f.compiled.statements.find(statement=>frames.statement_ids.includes(statement.index)&&statement.kind==='accept');
    const gateLink=page.locator('.sy-ec-component[data-statement="'+gate.index+'"] .sy-ec-head button');
    await gateLink.focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#sy-en-source').evaluate(el=>el.value.slice(el.selectionStart,el.selectionEnd)),gate.text);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    if(screenshotDir){await fs.mkdir(screenshotDir,{recursive:true});await worker.screenshot({path:path.join(screenshotDir,'construction-circuit-'+(mobile?'phone-dark':'desktop-light')+'.png')});}
    const remaining=await page.locator('#sy-en-source').evaluate(el=>{el.value+='\nChanged instructions.';el.dispatchEvent(new Event('input',{bubbles:true}));return document.querySelectorAll('.sy-ec-component').length;});
    assert.equal(remaining,0,'source edits immediately invalidate the circuit');
    assert.deepEqual(calls.filter(call=>call.method==='POST'&&call.path!=='/api/perf/beacon'&&!call.path.endsWith('/editor/check')),[]);
    assert.deepEqual(errors,[]);
    return {mobile,statements:f.compiled.statements.length,workers:workerCount,gates:workerCount,checked_passes_not_run:workerCount*2,selected_dependencies:true,source_links:true,edit_invalidation:true,execution_calls:0};
  }finally{await context.close();}
}

for (const mobile of [false,true]) pageTest(`collapsed circuit preserves full source links (${mobile?'phone dark':'desktop'})`, async()=>{
  const browser=await launchCircuitBrowser();
  try { await runConstructionCircuitJourney(browser,{mobile}); } finally { await browser.close(); }
});

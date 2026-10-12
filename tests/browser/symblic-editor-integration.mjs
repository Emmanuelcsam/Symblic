// Actual page integration; every request is fulfilled locally using source-only checker fixtures.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORIGIN = 'http://127.0.0.1:18771';
const TYPES = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.woff2':'font/woff2','.svg':'image/svg+xml'};
export async function runEditorIntegrationJourney(browser, {assetRoot=root, checkoutRoot=root, fixtureRoot=root, mobile=false, screenshotDir=null}={}) {
  const fixture = JSON.parse(await fs.readFile(path.join(fixtureRoot,'tests/fixtures/symblic-editor-checks.json'),'utf8'));
  const F = fixture.fixtures;
  const context = await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1400,height:1000},isMobile:mobile,hasTouch:mobile,colorScheme:mobile?'dark':'light'});
  const calls=[],errors=[],gates=[];
  let diagnosticStatus=200;
  const gateNext = source => {
    let release, arrived;
    const pending=new Promise(resolve=>release=resolve), received=new Promise(resolve=>arrived=resolve);
    const gate={source,pending,received,release,arrived,used:false};gates.push(gate);return gate;
  };
  const find = body => Object.values(F).find(row=>row.source===body?.source&&row.language===(body.language||'native'));
  await context.addInitScript(({native,english})=>{
    localStorage.setItem('symblic-v2-draft',native);
    sessionStorage.setItem('symblic-english-v1',JSON.stringify({source:english,by:'ollama:qwen3:4b-instruct',calls:'32',retries:'2',budget:'12000',id:''}));
  },{native:F.native_error.source,english:F.english_error.source});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==ORIGIN)return route.abort();
    if(url.pathname.startsWith('/api/')) {
      let body=null;try{body=request.postDataJSON();}catch(_){/* GET */}
      calls.push({path:url.pathname,method:request.method(),body});
      if(url.pathname.endsWith('/editor/check')) {
        const gate=gates.find(item=>!item.used&&item.source===body?.source);
        if(gate){gate.used=true;gate.arrived();await gate.pending;}
        if(diagnosticStatus!==200)return route.fulfill({status:diagnosticStatus,json:{error:'Fixture inline checker unavailable'}});
        const row=find(body);assert.ok(row,'Unexpected checker source: '+JSON.stringify(body));
        return route.fulfill({json:row.report});
      }
      if(url.pathname.endsWith('/english/check')) {
        assert.equal(body.source,F.english_valid.source);return route.fulfill({json:F.english_valid.manual_check});
      }
      if(url.pathname.endsWith('/check')) {
        const row=find(body);assert.ok(row,'Unexpected legacy checker source');return route.fulfill({json:row.report.check});
      }
      if(url.pathname.endsWith('/english/examples'))return route.fulfill({json:{version:1,examples:{}}});
      if(url.pathname.endsWith('/meta'))return route.fulfill({json:{version:'fixture',examples:[],features:{}}});
      if(url.pathname.endsWith('/programs'))return route.fulfill({json:{programs:[]}});
      if(url.pathname.endsWith('/runs'))return route.fulfill({json:{runs:[]}});
      if(url.pathname==='/api/runner/engines')return route.fulfill({json:{engines:[{spec:'ollama:llama3.2:1b@node-a',id:'ollama:llama3.2:1b@node-a',title:'Llama 1B',engine:'ollama',model:'llama3.2:1b',kind:'local',typed_ask:true,selectable:true,ready:true}],errors:[],councils:[]}});
      return route.fulfill({json:{}});
    }
    const relative=url.pathname.replace(/^\//,'');
    for(const base of [assetRoot,checkoutRoot]) {
      const filename=path.resolve(base,relative);
      if(!filename.startsWith(path.resolve(base)+path.sep))return route.fulfill({status:403});
      try{return await route.fulfill({body:await fs.readFile(filename),contentType:TYPES[path.extname(filename)]||'application/octet-stream'});}catch(_){/* staged fallback */}
    }
    return route.fulfill({status:404,body:''});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const native=()=>page.locator('#sySrc'), english=()=>page.locator('#sy-en-source');
  const marks=()=>page.locator('.sy-editor-mark');
  const awaitReport=async (source,message)=>{
    await page.waitForFunction(({source,message})=>{
      const editor=document.querySelector('#sySrc')||document.querySelector('#sy-en-source');
      return editor?.value===source&&[...document.querySelectorAll('.sy-editor-problem')].some(node=>node.textContent.includes(message));
    },{source,message});
  };
  const awaitClear=async ()=>page.waitForFunction(()=>[...document.querySelectorAll('.sy-editor-status')].some(node=>node.textContent==='No diagnostics reported by this check.'));
  const fillAtomically=async (selector,source)=>page.locator(selector).evaluate((editor,text)=>{
    editor.value=text;editor.dispatchEvent(new Event('input',{bubbles:true}));
    return {marks:document.querySelectorAll('.sy-editor-mark,.sy-editor-point').length,problems:document.querySelectorAll('.sy-editor-problem').length};
  },source);
  const jump=async hash=>{await page.evaluate(hash=>{Studio.go(hash.slice(1));},hash);await page.locator(hash==='#english'?'#sy-en-source':'#sySrc').waitFor();};
  if(screenshotDir)await fs.mkdir(screenshotDir,{recursive:true});
  const postResponse=source=>page.waitForResponse(response=>response.url().endsWith('/editor/check')&&response.request().postDataJSON()?.source===source);
  try {
    await page.goto(ORIGIN+'/automation-studio/symblic.html#write');
    await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    await awaitReport(F.native_error.source,F.native_error.report.diagnostics[0].message);
    assert.equal(await marks().filter({hasText:')'}).count(),1);
    assert.equal(await marks().filter({hasText:')'}).getAttribute('data-severity'),'error');
    await native().press('F8');
    assert.deepEqual(await native().evaluate(el=>[el.selectionStart,el.selectionEnd]),[F.native_error.report.diagnostics[0].start,F.native_error.report.diagnostics[0].end]);
    assert.equal(await native().evaluate(el=>el.value.slice(el.selectionStart,el.selectionEnd)),')');
    if(screenshotDir)await page.locator('.sy-ed').screenshot({path:path.join(screenshotDir,`editor-page-error-${mobile?'phone-dark':'desktop-light'}.png`)});
    assert.equal(await native().evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=16),true);
    assert.equal(await page.locator('#syHl').innerText().then(text=>text.trimEnd()),F.native_error.source,'native highlighting stays intact');
    assert.deepEqual(await fillAtomically('#sySrc',F.native_warning.source),{marks:0,problems:0});
    await awaitReport(F.native_warning.source,F.native_warning.report.diagnostics[1].message);
    assert.equal(await page.locator('.sy-editor-mark[data-severity=warning]').count(),2);
    if(screenshotDir)await page.locator('.sy-ed').screenshot({path:path.join(screenshotDir,`editor-page-warning-${mobile?'phone-dark':'desktop-light'}.png`)});
    assert.equal(await page.locator('#syInlineDiagnostics').innerText().then(t=>t.includes('whole line; exact portion unavailable')),true);
    assert.deepEqual(await fillAtomically('#sySrc',F.native_valid.source),{marks:0,problems:0});await awaitClear();
    // A response arrives after an edit but before its 450 ms timer fires.
    const first=gateNext(F.native_error.source);await native().fill(F.native_error.source);await first.received;
    const oldResponse=postResponse(F.native_error.source);
    assert.deepEqual(await fillAtomically('#sySrc',F.native_valid2.source),{marks:0,problems:0});
    first.release();await oldResponse;await page.waitForTimeout(80);
    assert.equal(await marks().count(),0,'stale response must not repaint during the new debounce');await awaitClear();
    // Reverse completion order: the newer error remains when the older warning returns.
    const second=gateNext(F.native_warning.source);await native().fill(F.native_warning.source);await second.received;
    await native().fill(F.native_error.source);await awaitReport(F.native_error.source,F.native_error.report.diagnostics[0].message);
    const lateResponse=postResponse(F.native_warning.source);second.release();await lateResponse;await page.waitForTimeout(80);
    assert.equal(await page.locator('.sy-editor-mark[data-severity=warning]').count(),0);
    assert.equal(await page.locator('.sy-editor-mark[data-severity=error]').count(),1);
    const leaving=gateNext(F.native_warning.source);await native().fill(F.native_warning.source);await leaving.received;
    const leavingResponse=postResponse(F.native_warning.source);await jump('#english');leaving.release();await leavingResponse;
    await awaitReport(F.english_error.source,F.english_error.report.diagnostics[0].message);
    assert.equal(await page.locator('.sy-editor-overlay').count(),1,'tab switch destroys detached native decorator');
    assert.equal(await page.locator('.sy-editor-tooltip').count(),1);
    await english().press('F8');assert.equal(await english().evaluate(el=>el.value.slice(el.selectionStart,el.selectionEnd)),'plus');
    assert.deepEqual(await fillAtomically('#sy-en-source',F.english_point.source),{marks:0,problems:0});
    await awaitReport(F.english_point.source,F.english_point.report.diagnostics[0].message);
    assert.equal(await page.locator('.sy-editor-point').count(),1);
    await english().press('F8');assert.deepEqual(await english().evaluate(el=>[el.selectionStart,el.selectionEnd]),[F.english_point.report.diagnostics[0].start,F.english_point.report.diagnostics[0].end]);
    assert.deepEqual(await fillAtomically('#sy-en-source',F.english_valid.source),{marks:0,problems:0});
    await awaitClear();
    // The current editor keeps engineering views in explicit disclosures.
    // Open the circuit the same way a reader does before checking its contents.
    await page.locator('[data-en-panel="circuit"] > summary').click();
    await page.locator('.sy-en-circuit').waitFor();
    assert.equal(await page.locator('.sy-ec-component').count(),5);
    assert.equal(await page.locator('.sy-ec-component[data-kind=ask]').count(),1);
    assert.equal(await page.locator('.sy-ec-component[data-kind=accept]').count(),1);
    assert.match(await page.locator('.sy-en-circuit').innerText(),/checks not run/i);
    assert.match(await page.locator('.sy-ec-connections').first().innerText(),/base/);
    const sourceButton=page.locator('.sy-ec-component[data-kind=ask] .sy-ec-link').first();
    if(mobile)await sourceButton.tap();else await sourceButton.click();
    assert.equal(await english().evaluate(el=>el.value.slice(el.selectionStart,el.selectionEnd)),F.english_valid.source.split('\n')[1]);
    await page.getByRole('button',{name:'Check statements',exact:true}).click();
    await page.getByRole('heading',{name:'How these statements will run',exact:true}).waitFor();
    assert.equal(calls.filter(row=>row.path.endsWith('/english/check')).length,1,'manual Check remains available');
    assert.equal(await page.locator('.sy-editor-overlay').count(),1,'manual-check rerender disposes old decorator');
    // The English request has its own sequence; editing also clears the circuit immediately.
    const englishGate=gateNext(F.english_error.source);await english().fill(F.english_error.source);await englishGate.received;
    const englishResponse=postResponse(F.english_error.source);
    assert.deepEqual(await fillAtomically('#sy-en-source',F.english_valid.source),{marks:0,problems:0});
    assert.equal(await page.locator('.sy-en-circuit').count(),0,'changed source clears old circuit');
    englishGate.release();await englishResponse;await page.waitForTimeout(80);
    assert.equal(await marks().count(),0);await awaitClear();await page.locator('.sy-en-circuit').waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+2),true,'phone/desktop has no horizontal page overflow');
    if(screenshotDir){await fs.mkdir(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,`editor-page-${mobile?'phone-dark':'desktop-light'}.png`),fullPage:true});}
    // Older servers retain native check text; English makes unavailable inline analysis visible.
    for(const status of [404,503]) {
      diagnosticStatus=status;await jump('#write');
      await native().fill(F.native_warning.source);
      await page.locator('#syDiag .d.warn').first().waitFor();
      assert.equal(await page.locator('.sy-editor-mark').count(),0);
      assert.match(await page.locator('#syInlineDiagnostics').innerText(),/Inline ranges are unavailable/);
      await jump('#english');await english().fill(F.english_error.source);
      await page.waitForFunction(()=>document.querySelector('[data-en-diagnostics]')?.textContent.includes('Inline checking is unavailable'));
      assert.equal(await page.locator('.sy-en-circuit').count(),0);
      assert.equal(await page.locator('.sy-editor-mark').count(),0);
    }
    diagnosticStatus=200;await page.evaluate(()=>{location.hash='#write';});await native().waitFor();await native().fill(F.native_valid.source);await awaitClear();
    assert.equal(await page.locator('.sy-editor-overlay').count(),1);
    assert.equal(await page.locator('.sy-editor-tooltip').count(),1,'tab transitions do not accumulate tooltips/listeners');
    const effects=calls.filter(row=>row.method==='POST'&&/^\/api\/automation\/symblic\/(run|preview|english\/(run|preview)|compare|stop|spec\/run)(?:\?|$)/.test(row.path));
    assert.deepEqual(effects,[],'source diagnostics and circuit must never dispatch an execution endpoint');
    assert.deepEqual(errors,[]);
    return {mobile,helper_sha256:fixture.helper_sha256,checkerRequests:calls.filter(row=>row.path.endsWith('/editor/check')).length,
      legacyRequests:calls.filter(row=>row.path==='/api/automation/symblic/check').length,manualChecks:1,executionRequests:0,
      checks:'real checker ranges, native/English edits, F8, reverse response order, debounce invalidation, circuit source jump, manual Check, tab cleanup, 404/503 fallback'};
  } finally {for(const gate of gates)gate.release();await context.close();}
}
if(process.env.PLAYWRIGHT_MODULE){
  const test=await import('node:test');const{chromium}=await import(process.env.PLAYWRIGHT_MODULE);
  for(const mobile of[false,true])test.test(`editor page integration ${mobile?'phone':'desktop'}`,async()=>{
    const browser=await chromium.launch({executablePath: process.env.CHROME_BIN || undefined, headless:true});try{await runEditorIntegrationJourney(browser,{mobile});}finally{await browser.close();}
  });
}

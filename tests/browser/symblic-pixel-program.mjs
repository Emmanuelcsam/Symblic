// Real Symblic page; every request intercepted, fabricated model artifact explicitly test-only.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const fixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/symblic-pixel-program.json'),'utf8'));
const ORIGIN='http://127.0.0.1:18776',RID='bbccdd445566';
const TYPES={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.woff2':'font/woff2','.svg':'image/svg+xml'};
export async function runPixelProgramJourney(browser,{assetRoot=root,checkoutRoot=root,mobile=false,screenshotDir=null}={}){
  const context=await browser.newContext({viewport:mobile?{width:320,height:844}:{width:1400,height:1050},deviceScaleFactor:mobile?3:1,
    isMobile:mobile,hasTouch:mobile,colorScheme:mobile?'dark':'light',reducedMotion:'reduce'});
  const calls=[],errors=[];let mode='done';
  await context.addInitScript(source=>sessionStorage.setItem('symblic-english-v1',JSON.stringify({source,id:'',by:'ollama:qwen3:4b-instruct',calls:'32',retries:'2',budget:'24000'})),fixture.source);
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());if(url.origin!==ORIGIN)return route.abort();
    if(url.pathname.startsWith('/api/')){
      let body=null;try{body=request.postDataJSON();}catch(_){/* GET */}
      calls.push({method:request.method(),path:url.pathname,body});
      if(url.pathname.endsWith('/english/examples'))return route.fulfill({json:{version:1,examples:{}}});
      if(url.pathname.endsWith('/editor/check'))return route.fulfill({json:{version:1,language:'english',source_length_utf16:body.source.length,available:true,ok:true,diagnostics:[],check:{ok:true,errors:[],warnings:[],plan:[]}}});
      if(url.pathname.endsWith('/meta'))return route.fulfill({json:{version:'fixture',examples:[],features:{}}});
      if(url.pathname.endsWith('/english/run'))return route.fulfill({json:{id:'ccddeeff0011',kept:7,reuse:{decisions:[]}}});
      if(url.pathname.endsWith('/run'))return route.fulfill({json:{id:url.searchParams.get('id')||RID,status:url.searchParams.get('id')==='ccddeeff0011'?'running':mode==='failed'?'failed':'done',meta:{by:'ollama:qwen3:4b-instruct@node-f',authoring:{document:fixture.source,reuse:url.searchParams.get('id')==='ccddeeff0011'?{from_run:RID,kept:7,scope:mode==='bad-reuse'?'unverified':'locally_rechecked_model_work'}:undefined,presentation:mode==='wrong-assets'?{...fixture.presentation,assets:{...fixture.presentation.assets,vm:fixture.presentation.assets.parser}}:fixture.presentation}},trace:[],
        state:{asks:9,calls:9,cached:0,outputs:[{label:'implementation.js',value:mode==='hostile'?fixture.implementation.replace('return pixel - center;','return window;'):mode==='runtime-failure'?fixture.implementation.replace('buffer.fill(0); return buffer;','buffer.fill(0); return null;'):fixture.implementation}]}}});
      if(url.pathname.endsWith('/english/check'))return route.fulfill({json:{ok:true,statements:[],source:'test-only'}});
      if(url.pathname.endsWith('/runs'))return route.fulfill({json:{runs:[]}});
      if(url.pathname.endsWith('/programs'))return route.fulfill({json:{programs:[]}});
      if(url.pathname.endsWith('/check'))return route.fulfill({json:{ok:true,errors:[],warnings:[],inputs:[],plan:[]}});
      return route.fulfill({json:{}});
    }
    const relative=url.pathname.replace(/^\//,'');
    for(const base of [assetRoot,checkoutRoot]){
      const filename=path.resolve(base,relative);if(!filename.startsWith(path.resolve(base)+path.sep))return route.fulfill({status:403});
      try{return await route.fulfill({body:await fs.readFile(filename),contentType:TYPES[path.extname(filename)]||'application/octet-stream'});}catch(_){/* fallback */}
    }
    return route.fulfill({status:404,body:''});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const url=ORIGIN+'/automation-studio/symblic.html?english_run='+RID+'#english';
  try{
    await page.goto(url);await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    const launch=page.getByRole('button',{name:'Open display',exact:true});await launch.waitFor();
    assert.equal(await page.locator('[data-en-pixel-program] canvas').getAttribute('width'),'800');
    assert.equal(await page.getByRole('link',{name:'Link to saved program'}).getAttribute('href'),'?english_run='+RID+'#english');
    await launch.click();
    const player=page.locator('.sy-pixels'),dialog=page.locator('.sy-pixels-dialog');
    assert.equal(await dialog.evaluate(e=>getComputedStyle(e).backgroundColor),mobile?'rgb(10, 10, 10)':'rgb(244, 241, 235)','modal keeps the current theme and readable controls');
    await page.waitForTimeout(100);assert.equal(Number(await player.getAttribute('data-frame')),0,'existing reduced-motion preference prevents autoplay on open');
    if(mobile)await player.getByRole('button',{name:'Run preview',exact:true}).click();
    else await player.getByRole('button',{name:'Start exact display',exact:true}).click();
    await page.waitForFunction(()=>Number(document.querySelector('.sy-pixels')?.dataset.frame)>=3);
    await player.getByRole('button',{name:'Pause',exact:true}).click();
    const paused=Number(await player.getAttribute('data-frame'));await page.waitForTimeout(80);
    assert.equal(Number(await player.getAttribute('data-frame')),paused);
    await player.getByText('Display evidence',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.sy-pixels pre')?.textContent.startsWith('{'));
    const receipt=JSON.parse(await player.locator('pre').textContent());
    if(mobile)assert.equal(receipt.presentation.mode,'preview');
    else{assert.deepEqual(receipt.presentation.device_pixel_box,[800,600]);assert.equal(receipt.presentation.mapping,'browser_device_pixel_box_matches');assert.equal(receipt.presentation.mode,'exact');}
    assert.deepEqual(receipt.assets,fixture.presentation.assets,'receipt records matching loaded asset identities');
    assert.equal(await player.getByRole('button',{name:'Use exact display',exact:true,includeHidden:true}).isVisible(),mobile,'exact-mode switch is only shown in preview');
    assert.equal(receipt.presentation.viewport_scope,'canvas_within_browser_window');
    assert.equal(receipt.presentation.physical_light,'unverified');assert.equal(receipt.presentation.physical_refresh_completion,'unverified');
    assert.equal(receipt.presentation.geometry.transformed,false);assert.equal(receipt.presentation.geometry.integral_origin_estimate,true);
    for(const event of receipt.execution.trace.filter(row=>row.kind==='delay-complete'))assert.ok(event.elapsed>=1000/60);
    const validation=await player.locator('canvas').evaluate(canvas=>{
      const source=canvas.getContext('2d').getImageData(0,0,800,600).data,x=Number(document.querySelector('.sy-pixels').dataset.x);let white=0,wrong=0;
      for(let y=0;y<600;y++)for(let col=0;col<800;col++){
        const off=(y*800+col)*4,wanted=(col-x)*(col-x)+(y-300)*(y-300)<=25?255:0;
        if(wanted)white++;if(source[off]!==wanted||source[off+1]!==wanted||source[off+2]!==wanted||source[off+3]!==255)wrong++;
      }
      return{wrong,white,width:canvas.width,height:canvas.height};
    });
    assert.equal(validation.wrong,0,'every backing pixel matches the model-built binary circle, without trails or antialiasing');
    assert.ok(validation.white>0);assert.deepEqual([validation.width,validation.height],[800,600]);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'phone/desktop page has no horizontal overflow');
    assert.equal(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1),true,'display has no horizontal overflow');
    await player.getByText('Display evidence',{exact:true}).click();
    if(screenshotDir){await fs.mkdir(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,'pixel-'+(mobile?'phone-dark':'desktop-light')+'.png')});}
    await player.getByRole('button',{name:mobile?'Resume preview':'Resume display',exact:true}).click();
    await page.waitForFunction(n=>Number(document.querySelector('.sy-pixels')?.dataset.frame)>n,paused);
    await player.getByRole('button',{name:'Close display',exact:true}).click();
    const closed=Number(await player.getAttribute('data-frame'));await page.waitForTimeout(90);assert.equal(Number(await player.getAttribute('data-frame')),closed);
    assert.equal(await dialog.evaluate(e=>e.open),false);
    await page.getByRole('button',{name:'Check statements',exact:true}).click();
    await page.getByRole('heading',{name:'How these statements will run',exact:true}).waitFor();
    assert.equal(Number(await player.getAttribute('data-frame')),closed,'source-only check preserves paused display state');
    await page.getByRole('button',{name:'Open display',exact:true}).click();
    await page.waitForTimeout(80);assert.equal(Number(await player.getAttribute('data-frame')),closed,'reopen honors reduced motion');
    await player.getByRole('button',{name:mobile?'Resume preview':'Resume display',exact:true}).click();
    await page.waitForFunction(n=>Number(document.querySelector('.sy-pixels')?.dataset.frame)>n,closed);
    await page.setViewportSize(mobile?{width:321,height:844}:{width:1398,height:1050});
    await page.waitForFunction(()=>document.querySelector('.sy-pixels')?.dataset.phase==='paused');
    const resized=Number(await player.getAttribute('data-frame'));await page.waitForTimeout(80);assert.equal(Number(await player.getAttribute('data-frame')),resized);
    if(!mobile){
      await player.getByRole('button',{name:'Resume display',exact:true}).click();
      await page.waitForFunction(n=>Number(document.querySelector('.sy-pixels')?.dataset.frame)>n,resized);
      await page.evaluate(()=>dispatchEvent(new Event('resize')));
      await page.waitForFunction(()=>document.querySelector('.sy-pixels')?.dataset.phase==='paused');
      await player.getByRole('button',{name:'Resume display',exact:true}).click();
      await player.getByRole('button',{name:'Pause',exact:true}).click();
      await player.getByRole('button',{name:'Run preview',exact:true}).click();
      await player.getByRole('button',{name:'Pause',exact:true}).click();
      await player.getByRole('button',{name:'Use exact display',exact:true}).click();
      await player.getByRole('button',{name:'Pause',exact:true}).waitFor();
      await dialog.evaluate(element=>{const holder=document.createElement('div');holder.style.filter='invert(1)';document.body.append(holder);holder.append(element);});
      await page.waitForFunction(()=>document.querySelector('.sy-pixels')?.dataset.phase==='paused');
      assert.equal(await dialog.evaluate(e=>e.matches(':modal')),false);
      const lost=Number(await player.getAttribute('data-frame'));await page.waitForTimeout(100);assert.equal(Number(await player.getAttribute('data-frame')),lost,'loss of modality stops playback');
      await player.getByText('Display evidence',{exact:true}).click();
      const broken=JSON.parse(await player.locator('pre').textContent());
      assert.equal(broken.presentation.geometry.modal,false);assert.equal(broken.presentation.geometry.transformed,true);
      await player.getByText('Display evidence',{exact:true}).click();
      await page.getByRole('button',{name:'Open display',exact:true}).click();
      assert.equal(await dialog.evaluate(e=>e.matches(':modal')),true);
      await player.getByRole('button',{name:'Resume display',exact:true}).click();
      await page.waitForFunction(n=>Number(document.querySelector('.sy-pixels')?.dataset.frame)>n,lost);
    }

    await player.getByRole('button',{name:'Close display',exact:true}).click();
    await page.evaluate(()=>Studio.go('write'));await page.locator('#sySrc').waitFor();assert.equal(await page.locator('.sy-pixels-dialog').count(),0,'navigation removes the owned display');
    mode='failed';await page.goto(url);await page.waitForFunction(()=>document.querySelector('[data-en-status]')?.textContent.startsWith('failed'));assert.equal(await page.getByRole('button',{name:'Open display',exact:true}).count(),0,'failed runs cannot become displays');
    await page.getByRole('button',{name:'Retry remaining tasks',exact:true}).waitFor();
    assert.equal(calls.filter(call=>call.path.endsWith('/english/run')).length,0,'failed-run loading never dispatches a retry');
    const draft='A separate unfinished editor draft.';
    await page.locator('#sy-en-source').fill(draft);
    await page.locator('#sy-en-calls').fill('10001');
    await page.getByRole('button',{name:'Retry remaining tasks',exact:true}).click();
    assert.equal(calls.filter(call=>call.path.endsWith('/english/run')).length,0,'retry preserves bounded limits');
    await page.locator('#sy-en-calls').fill('21');await page.getByText('Task limits',{exact:true}).click();await page.locator('#sy-en-retries').fill('3');await page.locator('#sy-en-budget').fill('16000');
    await page.locator('#sy-en-by').selectOption('ollama:llama3.2:1b');
    await page.getByRole('button',{name:'Retry remaining tasks',exact:true}).click();
    await page.getByRole('link',{name:'Original failed run',exact:true}).waitFor();
    const dispatched=calls.filter(call=>call.path.endsWith('/english/run'));
    assert.equal(dispatched.length,1);assert.deepEqual(dispatched[0].body,{source:fixture.source,by:'ollama:llama3.2:1b',max_calls:21,retries:3,budget:16000,keep:RID});
    assert.equal(await page.locator('#sy-en-source').inputValue(),draft,'recovery must not replace the editor draft');
    assert.equal(await page.getByRole('link',{name:'Original failed run',exact:true}).getAttribute('href'),'?english_run='+RID+'#english');
    assert.equal(await page.locator('[data-en-run]').textContent().then(text=>text.includes('7 accepted tasks were locally rechecked')),true);
    assert.equal(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('symblic-english-v1')).id),'ccddeeff0011','retry creates a distinct run');
    assert.equal(calls.filter(call=>call.path.endsWith('/editor/check')||call.path.endsWith('/english/check')).every(call=>!call.body?.keep),true);
    await page.goto(ORIGIN+'/automation-studio/symblic.html?english_run=ccddeeff0011#english');await page.reload();
    await page.getByRole('link',{name:'Original failed run',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>Boolean(JSON.parse(sessionStorage.getItem('symblic-english-v1')).recovery)),false,'fresh linked-run journey has no session recovery record');
    assert.equal(await page.locator('[data-en-run]').textContent().then(text=>text.includes('7 accepted tasks were locally rechecked')),true,'saved authoring provenance survives a fresh-device session');
    assert.equal(await page.getByRole('link',{name:'Original failed run',exact:true}).getAttribute('href'),'?english_run='+RID+'#english');
    assert.equal(calls.filter(call=>call.path.endsWith('/english/run')).length,1,'opening retained provenance does not dispatch');
    mode='bad-reuse';await page.reload();await page.locator('[data-en-status]').waitFor();
    assert.equal(await page.getByRole('link',{name:'Original failed run',exact:true}).count(),0,'unverified reuse metadata cannot claim retained work');
    mode='hostile';await page.goto(url);await page.reload();await page.locator('[data-en-pixel-program] [role=alert]').waitFor();assert.equal(await page.getByRole('button',{name:'Open display',exact:true}).count(),0,'forbidden model globals fail before display');
    mode='wrong-assets';await page.reload();await page.locator('[data-en-pixel-program] [role=alert]').waitFor();
    assert.equal(await page.getByRole('button',{name:'Open display',exact:true}).count(),0,'a different required interpreter cannot be displayed');
    assert.equal((await page.locator('[data-en-pixel-program] [role=alert]').textContent()).includes('different pixel runtime assets'),true);
    mode='runtime-failure';await page.reload();await page.getByRole('button',{name:'Open display',exact:true}).click();
    await page.locator('.sy-pixels').getByRole('button',{name:mobile?'Run preview':'Start exact display',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.sy-pixels')?.dataset.phase==='error');
    await page.locator('.sy-pixels').getByRole('button',{name:'Close display',exact:true}).click();
    await page.getByRole('button',{name:'Open display',exact:true}).click();
    await page.evaluate(()=>dispatchEvent(new Event('resize')));await page.waitForTimeout(120);
    assert.equal(await page.locator('.sy-pixels').getAttribute('data-phase'),'error');
    assert.equal(await page.locator('.sy-pixels').getByRole('button',{name:'Start exact display',exact:true}).isDisabled(),true);
    await page.locator('.sy-pixels').getByText('Display evidence',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.sy-pixels pre')?.textContent.startsWith('{'));
    const refused=JSON.parse(await page.locator('.sy-pixels pre').textContent());
    assert.equal(refused.execution.trace.filter(row=>row.kind==='play').length,1);
    assert.equal(refused.execution.trace.filter(row=>row.kind==='error').length,1);

    assert.deepEqual(calls.filter(call=>call.method==='POST'&&!['/api/perf/beacon','/api/automation/symblic/editor/check','/api/automation/symblic/english/check','/api/automation/symblic/english/run'].includes(call.path)),[],'opening saved output never dispatches model execution');
    assert.deepEqual(errors,[]);
    return{mobile,device_pixel_box:receipt.presentation.device_pixel_box,pixels:validation,frame:paused,minimum_wait_ms:Math.min(...receipt.execution.trace.filter(row=>row.kind==='delay-complete').map(row=>row.elapsed)),execution_requests:1,explicit_recovery:true,cleanup:true};
  }finally{await context.close();}
}

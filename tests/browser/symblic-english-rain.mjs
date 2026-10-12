// Recorded character-grid playback on the real English page. All HTTP is intercepted.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const ORIGIN='http://127.0.0.1:18773', RID='aabbcc112233';
const SOURCE='Ask the worker to move each rain head downward.\nKeep the earlier checked work.';
const TYPES={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.woff2':'font/woff2','.svg':'image/svg+xml'};
const frames=Array.from({length:3},(_,tick)=>({value:{kind:'character-grid',width:12,height:8,tick,cells:[
  {x:0,y:tick,char:'A',shade:0},{x:3,y:tick+1,char:'B',shade:0},{x:3,y:tick,char:'C',shade:3},
  {x:6,y:tick+2,char:'<',shade:0},{x:6,y:tick+1,char:'D',shade:2},{x:6,y:tick,char:'E',shade:7}
]}}));
export async function runEnglishRainJourney(browser,{assetRoot=root,checkoutRoot=root,mobile=false,screenshotDir=null}={}) {
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1400,height:1000},isMobile:mobile,hasTouch:mobile,reducedMotion:'reduce',colorScheme:mobile?'dark':'light'});
  const calls=[],errors=[];let mode='saved',reads=0;
  await context.addInitScript(source=>{
    sessionStorage.setItem('symblic-english-v1',JSON.stringify({source,id:'',by:'ollama:qwen3:4b-instruct',calls:'32',retries:'2',budget:'12000'}));
    window.__rainDraws=[];
    const draw=CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText=function(text,x,y,...rest){window.__rainDraws.push({text,x,y,shade:this.fillStyle});return draw.call(this,text,x,y,...rest);};
  },SOURCE);
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());if(url.origin!==ORIGIN)return route.abort();
    if(url.pathname.startsWith('/api/')) {
      let body=null;try{body=request.postDataJSON();}catch(_){/* GET */}
      calls.push({method:request.method(),path:url.pathname,search:url.search,body});
      if(url.pathname.endsWith('/english/examples'))return route.fulfill({json:{version:1,examples:{}}});
      if(url.pathname.endsWith('/editor/check'))return route.fulfill({json:{version:1,language:body.language,source_length_utf16:body.source.length,available:true,ok:true,diagnostics:[],check:{ok:true,errors:[],warnings:[],plan:[]}}});
      if(url.pathname.endsWith('/meta'))return route.fulfill({json:{version:'fixture',examples:[],features:{}}});
      if(url.pathname.endsWith('/run')) {
        assert.equal(url.search,'?id='+RID);reads++;
        const count=mode==='progress'?Math.min(reads,3):3;
        return route.fulfill({json:{id:RID,status:mode==='progress'&&count<3?'running':'done',
          meta:{authoring:{document:SOURCE}},trace:[],state:{asks:count,calls:count,cached:0,
            outputs:mode==='legacy'?[{value:{kind:'grid',width:5,height:3,x:1,y:0,value:'A'}}]:frames.slice(0,count),
            ...(mode==='progress'&&count<3?{outputs_progress:{partial:true,omitted:0}}:{})}}});
      }
      if(url.pathname.endsWith('/check'))return route.fulfill({json:{ok:true,errors:[],warnings:[],inputs:[],plan:[]}});
      if(url.pathname.endsWith('/runs'))return route.fulfill({json:{runs:[]}});
      if(url.pathname.endsWith('/programs'))return route.fulfill({json:{programs:[]}});
      return route.fulfill({json:{}});
    }
    const relative=url.pathname.replace(/^\//,'');
    for(const base of [assetRoot,checkoutRoot]) {
      const filename=path.resolve(base,relative);if(!filename.startsWith(path.resolve(base)+path.sep))return route.fulfill({status:403});
      try{return await route.fulfill({body:await fs.readFile(filename),contentType:TYPES[path.extname(filename)]||'application/octet-stream'});}catch(_){/* staged fallback */}
    }
    return route.fulfill({status:404,body:''});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const url=ORIGIN+'/automation-studio/symblic.html?english_run='+RID+'#english';
  try {
    await page.goto(url);await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    const player=page.locator('[data-en-character-frames] .sy-frames');await player.waitFor();
    await page.waitForFunction(()=>document.querySelector('[data-en-character-frames] .sy-frames')?.dataset.playing==='false');
    assert.equal(await player.getAttribute('data-frame'),'0');
    assert.match(await player.locator('canvas').getAttribute('aria-label'),/12 columns by 8 rows.*Frame 1 of 3.*6 occupied cells.*top left/);
    assert.deepEqual(await page.evaluate(()=>window.__rainDraws.slice(0,6)),[
      {text:'A',x:9,y:12,shade:'#e6ffe9'},{text:'B',x:63,y:36,shade:'#e6ffe9'},
      {text:'C',x:63,y:12,shade:'#28c954'},{text:'<',x:117,y:60,shade:'#e6ffe9'},
      {text:'D',x:117,y:36,shade:'#4aef72'},{text:'E',x:117,y:12,shade:'#083818'}
    ],'player draws the saved coordinates and trail shades exactly, with top-origin rows');
    assert.equal(await player.locator('canvas').evaluate(canvas=>{const data=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;let bright=0;for(let i=0;i<data.length;i+=4)if(data[i+1]>64)bright++;return bright>20;}),true,'glyphs appear on the actual canvas');
    assert.equal(await page.getByRole('link',{name:'Link to saved frames'}).getAttribute('href'),'?english_run='+RID+'#english');
    await page.getByText('Original instructions for this saved run',{exact:true}).click();
    assert.ok((await page.locator('[data-en-run]').textContent()).includes(SOURCE));
    assert.equal(await player.locator('img,script').count(),0,'saved glyphs are drawn, never interpreted as markup');
    const next=player.getByRole('button',{name:'Next frame',exact:true});if(mobile)await next.tap();else await next.click();
    assert.equal(await player.getAttribute('data-frame'),'1');
    await next.click();await next.click();assert.equal(await player.getAttribute('data-frame'),'0','saved playback wraps');
    const play=player.getByRole('button',{name:'Play',exact:true});if(mobile)await play.tap();else await play.click();
    await page.waitForFunction(()=>document.querySelector('[data-en-character-frames] .sy-frames')?.dataset.frame!=='0');
    await player.getByRole('button',{name:'Pause',exact:true}).click();const paused=await player.getAttribute('data-frame');
    await page.waitForTimeout(230);assert.equal(await player.getAttribute('data-frame'),paused);
    await page.evaluate(()=>{window.__savedRainCanvas=document.querySelector('[data-en-character-frames] canvas');});
    await page.getByRole('button',{name:'Check statements',exact:true}).click();
    await page.getByRole('heading',{name:'How these statements will run',exact:true}).waitFor();
    assert.equal(await player.getAttribute('data-frame'),paused,'editor rerender preserves the paused frame');
    assert.equal(await page.evaluate(()=>window.__savedRainCanvas===document.querySelector('[data-en-character-frames] canvas')),true,'editor rerender retains the mounted player');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'player fits the viewport');
    if(screenshotDir){await fs.mkdir(screenshotDir,{recursive:true});await player.screenshot({path:path.join(screenshotDir,'english-rain-'+(mobile?'phone-dark':'desktop-light')+'.png')});}
    await player.getByRole('button',{name:'Play',exact:true}).click();
    await page.evaluate(()=>Studio.go('write'));await page.locator('#sySrc').waitFor();
    const draws=await page.evaluate(()=>window.__rainDraws.length);await page.waitForTimeout(260);
    assert.equal(await page.evaluate(()=>window.__rainDraws.length),draws,'navigation disposes active playback');
    mode='progress';reads=0;await page.goto(url);await page.locator('[data-en-character-frames] .sy-frames').waitFor();
    await page.getByText('Current outputs while this run is in progress.',{exact:true}).waitFor();
    await page.waitForFunction(()=>document.querySelector('[data-en-status]')?.textContent.startsWith('done'));
    assert.match(await page.locator('[data-en-character-frames] canvas').getAttribute('aria-label'),/of 3/);
    assert.equal(reads,3,'partial saved frames advance as the existing read-only polling finishes');
    mode='legacy';reads=0;await page.reload();await page.locator('[data-en-frames] [role=img]').waitFor();
    assert.equal(await page.locator('[data-en-frames] [role=img]').getAttribute('aria-label'),'Frame 1: A at column 1, row 0');
    assert.equal(await page.locator('[data-en-character-frames]').count(),0,'the original single-cell display stays intact');
    assert.deepEqual(calls.filter(call=>call.method==='POST'&&call.path!=='/api/perf/beacon'&&!call.path.endsWith('/editor/check')&&!call.path.endsWith('/check')),[],'opening and playing saved results never dispatches execution');
    assert.deepEqual(errors,[]);
    return {mobile,calls:calls.length,execution_calls:0,saved_frames:3,top_origin:true,trail_shades:true,legacy_grid:true,progress:true,cleanup:true};
  } finally {await context.close();}
}

if(process.env.PLAYWRIGHT_MODULE){
  const test=await import('node:test');const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
  for(const mobile of [false,true])test.test(`English saved rain ${mobile?'phone':'desktop'}`,async()=>{
    const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_BIN||undefined});
    try{await runEnglishRainJourney(browser,{mobile});}finally{await browser.close();}
  });
}

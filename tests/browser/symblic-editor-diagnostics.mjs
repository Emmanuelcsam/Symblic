// No API, model, daemon or live website. Also callable through the pinned Playwright CLI.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export async function runEditorDiagnosticsJourney(browser, {assetRoot = root, checkoutRoot = root, mobile = false, screenshotDir = null} = {}) {
  const context = await browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1280, height: 900},
    isMobile: mobile, hasTouch: mobile, colorScheme: mobile ? 'dark' : 'light'});
  await context.route('**/*', route => route.abort());
  const page = await context.newPage(), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const css = await fs.readFile(path.join(assetRoot, 'web/studio/symblic-editor-diagnostics.css'), 'utf8');
  const native = await fs.readFile(path.join(checkoutRoot, 'web/studio/symblic.css'), 'utf8');
  const english = await fs.readFile(path.join(checkoutRoot, 'web/studio/symblic-english.css'), 'utf8');
  try {
    await page.setContent(`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
      :root{--mono:monospace;--bg1:${mobile ? '#182023' : '#fff'};--bg2:${mobile ? '#202b31' : '#eee'};--tx1:${mobile ? '#eee' : '#222'};--tx2:${mobile ? '#ddd' : '#444'};--err:${mobile ? '#ff8780' : '#bc302c'};--warn:${mobile ? '#ffc363' : '#a56a00'};--ctl:#888;--acc:#478ac2}
      body{background:var(--bg1);color:var(--tx1);font:16px system-ui;margin:12px}*{box-sizing:border-box}.host{position:relative;max-width:700px}textarea{font:16px/24px monospace;padding:10px 12px;background:var(--bg1);color:var(--tx1);tab-size:2}textarea:focus{outline:2px solid var(--acc)}
      ${native}\n${english}\n${css}
      .sy-ed{height:190px;min-height:190px}.sy-english textarea{height:180px;min-height:180px;resize:both}.test-title{font-size:18px}
      </style></head><body><h1 class="test-title">Editor diagnostic fixture</h1>
      <div class="host"><div class="sy-ed"><div class="sy-gut">1</div><div class="sy-body"><pre id="highlight" class="sy-hl" aria-hidden="true"></pre><textarea id="native" class="sy-src" wrap="off" spellcheck="false" aria-label="Native" aria-describedby="original-help"></textarea></div></div><div id="native-problems"></div></div>
      <p id="original-help">Existing help stays available.</p><div class="sy-english host"><label for="english">English</label><textarea id="english" wrap="soft" spellcheck="false"></textarea><div id="english-problems"></div></div></body></html>`);
    await page.addScriptTag({path: path.join(assetRoot, 'web/studio/symblic-editor-diagnostics.js')});
    await page.evaluate(() => {
      const native = document.getElementById('native'), english = document.getElementById('english');
      native.value = 'first line\r\n\t😀 ' + 'long '.repeat(60) + 'BROKEN\r\n' + 'more lines\n'.repeat(24) + 'EOF';
      document.getElementById('highlight').textContent = native.value;
      native.addEventListener('scroll',()=>{const hl=document.getElementById('highlight');hl.scrollTop=native.scrollTop;hl.scrollLeft=native.scrollLeft;});
      english.value = 'Remember the accepted foundation. ' + 'Keep the pieces together while this sentence wraps. '.repeat(3) + '\t😀 BROKEN text.\n';
      window.nativeDiag = SymblicEditorDiagnostics.attach(native, {problems: document.getElementById('native-problems')});
      window.englishDiag = SymblicEditorDiagnostics.attach(english, {problems: document.getElementById('english-problems')});
      window.mark = (editor, diag) => diag.setDiagnostics(editor.value, [
        {severity:'error', message:'Incorrect <img src=x onerror=window.bad=1> portion', line:2, col:5, start:editor.value.indexOf('BROKEN'), end:editor.value.indexOf('BROKEN') + 6, position_kind:'token'},
        {severity:'warning', message:'Point at the end', start:editor.value.length, end:editor.value.length, position_kind:'point'},
        {severity:'warning', message:'Whole line; no precise token reported', line:1, start:0, end:editor.value.indexOf('\n') < 0 ? 20 : editor.value.indexOf('\n'), position_kind:'line'},
        {severity:'info', message:'General note', start:null, end:null, position_kind:'none'}]);
      native.setSelectionRange(3, 7); window.beforeSource = native.value; mark(native, nativeDiag); mark(english, englishDiag);
    });
    assert.deepEqual(await page.locator('#native').evaluate(el => [el.selectionStart, el.selectionEnd, el.value.includes('\r')]), [3, 7, false]);
    assert.equal(await page.locator('.sy-editor-mark').count() > 0, true);
    assert.equal(await page.locator('img').count(), 0);
    assert.equal(await page.evaluate(() => window.bad), undefined);
    assert.equal(await page.locator('#native').getAttribute('aria-describedby').then(value => value.startsWith('original-help ')), true);
    assert.equal(await page.locator('.sy-editor-mark').first().evaluate(el => getComputedStyle(el).textDecorationStyle), 'wavy');
    const clickMarkedText = async (id, api) => {
      await page.evaluate(({api}) => window[api].focus(0), {api});
      const info = await page.evaluate(id => {
        const ta = document.getElementById(id), overlay = ta.parentElement.querySelector('.sy-editor-overlay');
        const mark = [...overlay.querySelectorAll('.sy-editor-mark')].find(el => el.dataset.diagnostic.split(',').includes('0'));
        const rects = [...mark.getClientRects()].filter(r => r.width > 0);
        const r = rects[0], view = overlay.getBoundingClientRect();
        return {x:(Math.max(r.left, view.left) + Math.min(r.right, view.right)) / 2, y:(r.top+r.bottom)/2,
          start:ta.value.indexOf('BROKEN'), end:ta.value.indexOf('BROKEN')+6,
          visible:r.top >= view.top - 1 && r.bottom <= view.bottom + 1, scrollLeft:ta.scrollLeft, scrollTop:ta.scrollTop};
      }, id);
      assert.equal(info.visible, true, `${id} focus makes the actual mark visible`);
      await page.locator('#' + id).evaluate(el => el.setSelectionRange(0, 0));
      if (mobile) await page.touchscreen.tap(info.x, info.y); else await page.mouse.click(info.x, info.y);
      const at = await page.locator('#' + id).evaluate(el => ({start:el.selectionStart,end:el.selectionEnd,focused:document.activeElement===el}));
      assert.equal(at.focused, true); assert.ok(at.start >= info.start && at.start <= info.end, `${id}: native caret ${at.start} must land in diagnostic token ${info.start}–${info.end}`);
      assert.equal(at.start, at.end, 'overlay must not intercept or select text itself: ' + id + ' ' + JSON.stringify(info));
      return info;
    };
    const nativePosition = await clickMarkedText('native', 'nativeDiag');
    if(!mobile){await page.mouse.move(nativePosition.x,nativePosition.y);assert.equal(await page.locator('.sy-editor-tooltip:visible').count(),1);}
    assert.ok(nativePosition.scrollLeft > 100, 'long unwrapped lines scroll horizontally');
    await page.locator('#native').press('F8');
    assert.equal(await page.locator('#native').evaluate(el => el.selectionStart), await page.locator('#native').evaluate(el => el.value.length));
    assert.ok(await page.locator('#native').evaluate(el => el.scrollTop) > 100, 'EOF point scrolls vertically');
    await page.locator('#native').press('Shift+F8');
    assert.equal(await page.locator('#native').evaluate(el => el.selectionStart), await page.locator('#native').evaluate(el => el.value.indexOf('BROKEN')));
    await clickMarkedText('english', 'englishDiag');
    if(mobile) await page.locator('#english-problems .sy-editor-problem').nth(0).tap(); else await page.locator('#english-problems .sy-editor-problem').nth(0).click();
    assert.equal(await page.locator('#english').evaluate(el => el.value.slice(el.selectionStart,el.selectionEnd)), 'BROKEN');
    assert.equal(await page.locator('#english-problems .sy-editor-problem').nth(2).innerText().then(t => t.includes('whole line; exact portion unavailable')), true);
    // Resize and CSS zoom must follow the browser's own textarea geometry.
    await page.locator('#english').evaluate(el => {el.style.width='253px'; el.parentElement.style.zoom='1.25'; window.englishDiag.refresh();});
    await clickMarkedText('english', 'englishDiag');
    await page.locator('#english').evaluate(el => {el.parentElement.style.zoom=''; el.style.width='100%'; window.englishDiag.refresh();});
    if (screenshotDir) {await fs.mkdir(screenshotDir,{recursive:true}); await page.screenshot({path:path.join(screenshotDir,`editor-${mobile?'phone-dark':'desktop-light'}.png`),fullPage:true});}
    await page.locator('#native').press('End'); await page.locator('#native').press('x');
    assert.equal(await page.locator('#native-problems button').count(), 0, 'typing immediately clears obsolete diagnostics');
    assert.equal(await page.locator('#native').evaluate(el => el.parentElement.querySelectorAll('.sy-editor-mark').length), 0);
    assert.equal(await page.evaluate(() => nativeDiag.setDiagnostics(window.beforeSource,[{severity:'error',message:'stale',start:0,end:1,position_kind:'token'}])), false);
    assert.equal(await page.locator('#native-problems button').count(),0);
    assert.equal(await page.evaluate(()=>{const ta=document.getElementById('native');ta.value='';nativeDiag.setDiagnostics('',[{severity:'error',message:'Empty program',start:0,end:0,position_kind:'point'}]);nativeDiag.focus(0);const p=ta.parentElement.querySelector('.sy-editor-point').getBoundingClientRect();return p.height>0&&ta.selectionStart===0;}),true,'empty source keeps a visible EOF insertion point');
    const teardown = await page.evaluate(() => {
      const ta=document.getElementById('native'), value=ta.value;
      nativeDiag.destroy(); nativeDiag.destroy(); englishDiag.destroy();
      ta.dispatchEvent(new Event('input')); ta.dispatchEvent(new KeyboardEvent('keydown',{key:'F8'}));
      return {overlays:document.querySelectorAll('.sy-editor-overlay').length,tips:document.querySelectorAll('.sy-editor-tooltip').length,
        described:ta.getAttribute('aria-describedby'),shortcuts:ta.getAttribute('aria-keyshortcuts'),same:ta.value===value};
    });
    assert.deepEqual(teardown,{overlays:0,tips:0,described:'original-help',shortcuts:null,same:true});
    assert.deepEqual(errors,[]);
    return {mobile, nativePosition, checks:'underlines, native caret, tabs/emoji/CRLF, scroll, wrapping, zoom/resize, F8, touch buttons, stale source, escaped messages, cleanup', networkCalls:0};
  } finally {await context.close();}
}
if (process.env.PLAYWRIGHT_MODULE) {
  const test = await import('node:test');
  const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
  for (const mobile of [false,true]) test.test(`editor diagnostics ${mobile?'phone':'desktop'}`,async () => {
    const browser=await chromium.launch({executablePath: process.env.CHROME_BIN || undefined, headless:true}); try {await runEditorDiagnosticsJourney(browser,{mobile});} finally {await browser.close();}
  });
}

// Real bounded JS checks, intercepted HTTP, no providers or live stores.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test, launch, open, root, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
const sheet='# demo.js\n## Unit `f(x)`\nReturn x+1.\nExamples:\n    f(1) ==> 2\n## Assemble `demo.js`\n    /*UNITS*/\n';
const candidates=[{label:'A',source:'function f(x){return x+1;}'},
  {label:'B <img src=x onerror=alert(1)>',source:'function f(x){return x===-7 ? 900 : x+1;}'}];

for(const mobile of [false,true])test('differential questions retain owner choice '+(mobile?'phone dark':'desktop light'),async()=>{
  let body, report, count=0;
  async function api(request,url) {
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'fixture',examples:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='spec/compare') {
      count++; body=request.postDataJSON();
      const r=spawnSync(process.env.TEST_PYTHON || 'python3',['-B','-c','import sys,json; from integration.host import symblic_engine as E; print(json.dumps(E.spec_compare(json.load(sys.stdin))))'],
        {cwd:root,input:JSON.stringify(body),encoding:'utf8',timeout:30000});
      assert.equal(r.status,0,r.stderr||String(r.error));
      report=JSON.parse(r.stdout);
      return {json:report};
    }
  }
  const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#build',api,{mobile});
  try {
    await page.locator('#sySheet').fill(sheet);
    await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    await page.getByText('Compare candidate behavior',{exact:true}).click();
    await page.locator('#syCandidates').fill(JSON.stringify(candidates));
    await page.locator('#syProbes').fill('["f(-7)"]');
    await page.locator('#syCompareCode').click();
    await page.waitForFunction(()=>!document.querySelector('#syCompareCode').disabled);
    assert.match(await page.locator('#syComparisonResult').textContent(), /requires_owner_resolution/,
      JSON.stringify({report,status:await page.locator('#syComparisonStatus').textContent(),errors}));
    const result=JSON.parse(await page.locator('#syComparisonResult').textContent());
    assert.equal(result.proposed_examples[0].expected_json,null);
    assert.equal(result.probes[0].status,'divergent');
    assert.deepEqual(body.externals,[]);
    assert.equal(await page.locator('#sySheet').inputValue(),sheet);
    assert.equal(await page.locator('#syComparisonResult img').count(),0);
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(await axe(page),[]);
    await page.locator('#syProbes').fill('invalid JSON');
    assert.equal(await page.locator('#syComparisonResult').textContent(),'');
    await page.locator('#syCompareCode').click();
    await page.waitForFunction(()=>!document.querySelector('#syCompareCode').disabled);
    assert.equal(count,1);
    assert.notEqual(await page.locator('#syComparisonStatus').textContent(),'');
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});

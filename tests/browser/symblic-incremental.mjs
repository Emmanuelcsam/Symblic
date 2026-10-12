// Source assets and the pure logic compiler; all run/provider APIs intercepted.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test, launch, open, root, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
function compile(body) {
  const run=spawnSync(process.env.TEST_PYTHON || 'python3',['-B','-c',
    'import json,sys;from symblic.adapters import logic as L;print(json.dumps(L.compile_task(json.load(sys.stdin))))'],
    {cwd:root,input:JSON.stringify(body),encoding:'utf8',timeout:30000});
  assert.equal(run.status,0,run.stderr||String(run.error));
  return JSON.parse(run.stdout);
}
for(const mode of ['json','command'])for(const mobile of [false,true])test('incremental '+mode+' prepare and Write handoff '+(mobile?'phone dark':'desktop light'),async()=>{
  let submitted;
  const api=async(request,url)=>{
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'fixture',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route==='logic/compile') {
      submitted=request.postDataJSON(); return {json:compile(submitted)};
    }
    return undefined;
  };
  const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#logic',api,{mobile});
  try {
    await page.locator('#sy-logic-goal').waitFor();
    await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    await page.getByText('Proof format',{exact:true}).click();
    await page.locator('#sy-logic-format').selectOption('incremental');
    assert.equal(await page.locator('#sy-logic-inference').inputValue(),'json');
    await page.locator('#sy-logic-inference').selectOption(mode);
    assert.ok(await page.locator('#sy-logic-inference').evaluate(node=>parseFloat(getComputedStyle(node).fontSize)>=16));
    assert.equal(await page.locator('#sy-logic-calls').getAttribute('max'),'64');
    assert.equal(await page.locator('#sy-logic-calls').inputValue(),'32');
    await page.locator('#sy-logic-steps').fill('4');
    await page.locator('#sy-logic-calls').fill('8');
    await page.getByRole('button',{name:'Prepare proof task',exact:true}).click();
    await page.getByRole('button',{name:'Open in Write',exact:true}).waitFor();
    assert.equal(submitted.certificate_format,'incremental');
    assert.equal(submitted.inference_format,mode==='command'?'command':undefined);
    assert.match(await page.locator('[data-logic-inference]').textContent(),mode==='command'?/One inference command/:/JSON inference record/);
    assert.equal(submitted.step_limit,4);
    assert.equal(submitted.calls,8);
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(await axe(page),[]);
    await page.reload();
    await page.getByText('Proof format',{exact:true}).click();
    assert.equal(await page.locator('#sy-logic-format').inputValue(),'incremental');
    assert.equal(await page.locator('#sy-logic-inference').inputValue(),mode);
    assert.equal(await page.locator('#sy-logic-steps').inputValue(),'4');
    assert.equal(await page.locator('#sy-logic-calls').inputValue(),'8');
    await page.getByRole('button',{name:'Prepare proof task',exact:true}).click();
    await page.getByRole('button',{name:'Open in Write',exact:true}).click();
    await page.locator('#sySrc').waitFor();
    const source=await page.locator('#sySrc').inputValue();
    assert.match(source,mode==='command'?/proof_session_command/:/proof_session_append/);
    assert.match(source,/proof_steps_check/);
    assert.match(source,/context=none/);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});

test('command selection refuses a server response that silently compiles another format',async()=>{
  const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#logic',async(request,url)=>{
    if(url.pathname.endsWith('/logic/compile')) {
      const body=request.postDataJSON(); delete body.inference_format;
      return {json:compile(body)};
    }
    return {json:{examples:[],runs:[],programs:[]}};
  });
  try {
    await page.getByText('Proof format',{exact:true}).click();
    await page.locator('#sy-logic-format').selectOption('incremental');
    await page.locator('#sy-logic-inference').selectOption('command');
    await page.getByRole('button',{name:'Prepare proof task',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'did not compile the selected command format'}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Open in Write',exact:true}).count(),0);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});

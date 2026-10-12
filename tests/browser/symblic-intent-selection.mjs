// Mocked HTTP only; exact selection/persistence, desktop-light and phone-dark.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch, open, noHorizontalScroll, axe} from './host-harness.mjs';
let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });
const LOCAL = 'ollama:deepseek-r1:1.5b@host+high';
const OTHER = 'ollama:qwen3:4b@node-d';
const HTML = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Interpreter selection fixture</title><link rel="stylesheet" href="/studio.css"><link rel="stylesheet" href="/automation-studio/symblic-intent.css"><link rel="stylesheet" href="/automation-studio/symblic-picker.css"><body style="padding:16px"><main id="app"></main><script src="/automation-studio/symblic-picker.js"></script><script src="/automation-studio/symblic-intent.js"></script><script>SymblicIntent.render(document.getElementById("app"))</script></body></html>';
function fixture() {
  let state;
  const calls = [];
  const view = () => ({state, validation:{ok:true, readiness:{phase:state.phase}}, readback:{prompt:state.request.text},
    budget:{limit:6,used:1,remaining:5},artifact:null,handoff:null,job:null});
  const api = async (request, url) => {
    if (url.pathname === '/api/runner/engines') return {json:{engines:[LOCAL,OTHER].map(spec => ({spec,id:spec,engine:'ollama',model:spec.includes('deepseek')?'deepseek-r1:1.5b':'qwen3:4b',node:spec.includes('host')?'host':'node-d',kind:'local',typed_ask:true,ready:true,status:'available'}))}};
    const name = url.pathname.split('/').at(-1);
    const body = request.method() === 'POST' ? request.postDataJSON() : null;
    calls.push({name,body});
    if (name === 'create') {
      state={id:'intent-fixture',revision:0,content_revision:0,phase:'draft',request:{text:body.request},goal:'',turns:[],questions:[],requirements:[],assumptions:[],examples:[],policy:{by:body.by,confidential:body.confidential,allow_cloud:!body.confidential}};
    } else if (name === 'analyse') { state.phase='specified';state.goal='Compute five';state.revised_prompt=state.goal;state.revision++;state.content_revision++; }
    else if (name === 'revise') { assert.equal(body.event.kind,'applicator');assert.equal(body.revision,state.revision);state.policy.by=body.event.payload.by;state.revision++;state.content_revision++; }
    else if (name !== 'view') throw new Error('Unexpected API call '+name);
    return {json:view()};
  };
  return {api,calls};
}
for (const mobile of [false,true]) test(`Interpreter selection persists (${mobile?'phone dark':'desktop light'})`, async () => {
  const f=fixture();
  const {context,page,errors}=await open(browser,'/intent-selection-fixture.html',f.api,{mobile,files:{'/intent-selection-fixture.html':{body:HTML.replace('lang="en"', 'lang="en" data-theme="' + (mobile?'dark':'light') + '"'),contentType:'text/html'}}});
  try {
    await page.evaluate(dark=>document.documentElement.setAttribute('data-theme',dark?'dark':'light'),mobile);
    await page.getByLabel('What do you want to achieve?').fill('Compute the exact result of two plus three.');
    await page.getByLabel('Interpreter model',{exact:true}).selectOption(LOCAL);
    await page.getByRole('button',{name:'Analyse request',exact:true}).click();
    await page.getByRole('button',{name:'Analyse again',exact:true}).waitFor();
    assert.equal(f.calls.find(c=>c.name==='create').body.by,LOCAL);
    assert.equal(await page.getByLabel('Interpreter model',{exact:true}).inputValue(),LOCAL);
    await page.reload();
    await page.getByRole('button',{name:'Analyse again',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Interpreter model',{exact:true}).inputValue(),LOCAL);
    assert.equal(f.calls.filter(c=>c.name==='analyse').length,1,'reload never reruns analysis');
    await page.getByLabel('Interpreter model',{exact:true}).selectOption(OTHER);
    await page.getByRole('status').filter({hasText:'Saved.'}).waitFor();
    assert.equal(f.calls.at(-1).body.event.payload.by,OTHER);
    await page.reload();
    await page.getByRole('button',{name:'Analyse again',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Interpreter model',{exact:true}).inputValue(),OTHER);
    await page.getByLabel('Interpreter model',{exact:true}).selectOption('');
    await page.getByRole('status').filter({hasText:'Saved.'}).waitFor();
    assert.equal(f.calls.at(-1).body.event.payload.by,'');
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(errors,[]);
    assert.deepEqual(await axe(page),[]);
  } finally { await context.close(); }
});
test('older API cannot silently discard the selected model and start analysis', async () => {
  const f=fixture();
  const api=async (request,url) => {
    const result=await f.api(request,url);
    if(url.pathname.endsWith('/create')) result.json.state.policy={allow_cloud:true};
    return result;
  };
  const {context,page,errors}=await open(browser,'/intent-selection-fixture.html',api,{files:{'/intent-selection-fixture.html':{body:HTML,contentType:'text/html'}}});
  try {
    await page.getByLabel('What do you want to achieve?').fill('Compute five.');
    await page.getByLabel('Interpreter model',{exact:true}).selectOption(LOCAL);
    await page.getByRole('button',{name:'Analyse request',exact:true}).click();
    await page.getByText('The host API did not save your model choice.',{exact:false}).waitFor();
    assert.equal(f.calls.filter(c=>c.name==='analyse').length,0);
    assert.equal(await page.getByLabel('Interpreter model',{exact:true}).inputValue(),LOCAL);
    assert.equal(await page.getByLabel('What do you want to achieve?').inputValue(),'Compute five.');
    assert.deepEqual(errors,[]);
  } finally { await context.close(); }
});

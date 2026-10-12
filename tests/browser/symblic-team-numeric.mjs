// Shared editor only. Isolated Chromium; static local files; no API/provider calls.
import {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch,open,noHorizontalScroll} from './host-harness.mjs';
let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
const document='<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/symblic-team-editor.css"><main id="editor"></main><script src="/symblic-team-editor.js"></script>';
async function fixture(purpose='checked',weight=1){
  const result=await open(browser,'/team-numeric-fixture.html',()=>{throw new Error('This editor must not make API calls.');},{mobile:true,files:{'/team-numeric-fixture.html':{body:document,contentType:'text/html'}}});
  await result.page.evaluate(({purpose,weight})=>{
    const catalog={specs:{local:{title:'Ollama'}},models:{local:[{id:'qwen3:4b-instruct'}]},nodes:[{id:'node-f',online:true,ready:{ollama:true,local:true},models:['qwen3:4b-instruct']}],
      team_capabilities:{version:1,max_members:24,engines:{ollama:{checked:true,forge:true,project:true,project_team:true,efforts:[],project_efforts:[],settings:['temperature','seed'],project_settings:[]}}}};
    window.fixtureCatalog=catalog;
    window.editor=window.SymblicTeamEditor.mount(document.getElementById('editor'),{catalog,purpose,
      team:{version:1,members:[{id:'ownerSeat',engine:'ollama',model:'qwen3:4b-instruct',node:'node-f',effort:'',role:'Builder',characteristics:'Exact',instruction:'Keep the goal.',settings:{},weight}]}});
    window.readEditor=()=>{try{return {value:window.editor.getValue()};}catch(error){return {error:error.message};}};
  },{purpose,weight});
  await result.page.locator('.symblic-team-member > summary').click();
  await result.page.locator('.symblic-team-advanced > summary').click();
  return result;
}

test('invalid intermediate numeric input refuses instead of silently removing a requested override',async()=>{
  const {page,context,errors,requests}=await fixture();
  try{
    for(const setting of ['temperature','seed','vote weight']){
      const input=page.getByLabel('Agent 1 '+setting,{exact:true});
      await input.fill('');await input.pressSequentially('1e');
      assert.equal(await input.evaluate(node=>node.validity.badInput),true,'fixture must contain a real browser-invalid number');
      assert.equal(await input.inputValue(),'');
      const rejected=await page.evaluate(()=>window.readEditor());
      assert.ok(rejected.error,'invalid '+setting+' must refuse; it cannot become a default or zero');
      await input.fill(setting==='vote weight'?'1':'');
      assert.ok((await page.evaluate(()=>window.readEditor())).value);
    }
    await page.getByLabel('Agent 1 temperature',{exact:true}).fill('0.25');
    await page.getByLabel('Agent 1 seed',{exact:true}).fill('0');
    const accepted=await page.evaluate(()=>window.readEditor().value);
    assert.deepEqual(accepted.members[0].settings,{temperature:.25,seed:0});
    assert.equal(accepted.members[0].id,'ownerSeat');
    assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);assert.equal(await noHorizontalScroll(page),true);
  }finally{await context.close();}
});

test('project lane preserves and rejects a retained vote weight until explicitly reset',async()=>{
  const {page,context,errors,requests}=await fixture('project',2);
  try{
    assert.match((await page.evaluate(()=>window.readEditor())).error,/do not use voting|sequential project teams/i);
    assert.equal(await page.getByLabel('Agent 1 vote weight',{exact:true}).inputValue(),'2');
    await page.getByLabel('Agent 1 vote weight',{exact:true}).fill('1');
    const accepted=await page.evaluate(()=>window.readEditor().value);
    assert.equal(accepted.members[0].weight,1);assert.deepEqual(accepted.members[0].settings,{});
    assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);
  }finally{await context.close();}
});


test('invalid numeric draft stays fenced across model edits and catalogue redraw until explicit clear',async()=>{
  const {page,context,errors,requests}=await fixture();
  try{
    const input=page.getByLabel('Agent 1 temperature',{exact:true});
    await input.fill('0.25');await input.press('End');await input.pressSequentially('e');
    assert.equal(await input.evaluate(node=>node.validity.badInput),true);
    assert.equal(await page.evaluate(()=>window.editor.getDraft().members[0].settings.temperature),.25);
    await page.getByLabel('Agent 1 model',{exact:true}).fill('qwen3:8b');
    assert.ok((await page.evaluate(()=>window.readEditor())).error);
    await page.evaluate(()=>window.editor.setCatalog(window.fixtureCatalog));
    assert.ok((await page.evaluate(()=>window.readEditor())).error,'metadata refresh must not erase the bad-number fence');
    await page.locator('.symblic-team-advanced > summary').click();
    assert.equal(await page.getByLabel('Agent 1 temperature',{exact:true}).inputValue(),'0.25');
    await page.getByRole('button',{name:'Clear sampling overrides',exact:true}).click();
    const accepted=await page.evaluate(()=>window.readEditor().value);
    assert.deepEqual(accepted.members[0].settings,{});assert.equal(accepted.members[0].model,'qwen3:8b');
    assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);
  }finally{await context.close();}
});

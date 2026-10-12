// Recorded history remains inspectable when current-runtime assurance is refused.
// Every API response is synthetic; this test never starts an experiment.
import {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch,open,axe,noHorizontalScroll} from './host-harness.mjs';
let browser;before(async()=>{browser=await launch();});after(async()=>{await browser?.close();});
const ID='0000000000cc', HASH='c'.repeat(64);
const DOCUMENT={title:'Historical fixture',candidates:[{version:1,routes:[],order:[]}],training:[],heldout:[]};
const RECORDED={id:ID,meta:{title:DOCUMENT.title},status:'done',active:false,can_resume:false,
  error:'Recorded native diagnostic remains visible.',
  assurance:'recorded; current assurance unavailable (implementation changed)',
  state:{stage:'evaluated',cost_unit:'provider_calls',implementation_intact:false,
    assignments:{training:{pending:{count:0},inflight:{count:0},terminal:{count:1}}},
    selected:{selected:{sha256:HASH},receipt:{summaries:{}}},evaluation:null}};
for(const mobile of [false,true])for(const theme of ['light','dark'])test(`historical policy receipts ${mobile?'phone':'desktop'} ${theme}`,async()=>{
  async function api(request,url){
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'fixture',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route==='policy/example')return {json:DOCUMENT};
    if(route==='policy/runs')return {json:{runs:[{id:ID,title:DOCUMENT.title,status:'done'}]}};
    if(route==='policy/run')return {json:url.searchParams.get('audit')==='0'?RECORDED:
      {id:ID,meta:{title:DOCUMENT.title},status:'unavailable',active:false,can_resume:false,state:{},error:'implementation_pin'}};
    if(route==='policy/selected')return {status:409,json:{error:'Current runtime cannot export this historical selection.'}};
    return {json:{}};
  }
  const {context,page,requests,errors}=await open(browser,'/automation-studio/symblic.html#policies',api,{mobile});
  page.setDefaultTimeout(10000);
  try{
    await page.waitForFunction(()=>!!window.Studio);await page.evaluate(value=>Studio.setTheme(value),theme);
    await page.getByRole('button',{name:DOCUMENT.title+' · done'}).click();
    await page.getByText('implementation_pin',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Read recorded receipts',exact:true}).click();
    await page.getByText('Assurance: '+RECORDED.assurance,{exact:true}).waitFor();
    await page.getByText(RECORDED.error,{exact:true}).waitFor();
    assert.match(await page.locator('[data-policy-status]').textContent(),/done.*evaluated/);
    assert.match(await page.locator('[data-policy-stage=training]').textContent(),/terminal 1/);
    assert.equal(await page.getByRole('button',{name:'Resume experiment',exact:true}).isDisabled(),true);
    const reads=requests.filter(row=>row.path.endsWith('/policy/run'));
    assert.equal(reads.length,2);assert.ok(reads.at(-1).search.includes('audit=0'));
    await page.getByRole('button',{name:'Copy selected policy to Graphs draft',exact:true}).click();
    await page.getByText('Current runtime cannot export this historical selection.',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>Studio.page),'policies');
    await page.getByRole('button',{name:'Refresh selected experiment',exact:true}).click();
    await page.getByText('implementation_pin',{exact:true}).waitFor();
    assert.equal(requests.filter(row=>row.method==='POST'&&row.path.startsWith('/api/automation/symblic/')).length,0);
    assert.equal(await noHorizontalScroll(page),true);assert.deepEqual(await axe(page),[]);assert.deepEqual(errors,[]);
  }finally{await context.close();}
});

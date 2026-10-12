// Real bounded notebook/API functions in temp storage; all HTTP/provider work mocked.
import {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {test, launch,open,root,axe,noHorizontalScroll} from './host-harness.mjs';
let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
function request(store,method,route,body,query={}) {
  const script=`import json,sys
from integration.host import symblic_memory_api as A
class Handler:
 def get_query_param(self,name): return data['query'].get(name)
 def send_json(self,body,status=200): print(json.dumps({'status':status,'json':body}))
data=json.load(sys.stdin)
A.handle(Handler(),data['method'],'memory/'+data['route'],data['body'])`;
  const result=spawnSync(process.env.TEST_PYTHON || 'python3',['-B','-c',script],{cwd:root,env:{...process.env,AUTOMATION_DATA_DIR:store},
    input:JSON.stringify({method,route,body,query}),encoding:'utf8',timeout:30000});
  assert.equal(result.status,0,result.stderr||String(result.error));
  return JSON.parse(result.stdout);
}
for(const mobile of [false,true])test('notebook uncertainty, stale edit and support export '+(mobile?'phone dark':'desktop light'),async()=>{
  const store=await fs.mkdtemp(path.join(os.tmpdir(),'symblic-memory-browser-'));
  let book,loseCreate=true;
  const api=async(req,url)=>{
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'fixture',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route.startsWith('memory/')) {
      const name=route.slice(7),body=req.method()==='POST'?req.postDataJSON():null;
      const result=request(store,req.method(),name,body,Object.fromEntries(url.searchParams));
      if(result.status===200&&result.json.head)book=result.json;
      if(name==='create'&&loseCreate) {loseCreate=false;return {abort:true};}
      return result;
    }
  };
  const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#memory',api,{mobile});
  try {
    await page.locator('#sy-memory-book').waitFor();
    await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    await page.getByText('Create a notebook',{exact:true}).click();
    await page.locator('#sy-memory-title').fill('Brick-by-brick evidence');
    await page.locator('#sy-memory-create').click();
    await page.getByRole('alert').waitFor();
    await page.getByText('Create a notebook',{exact:true}).click();
    await page.locator('#sy-memory-create').click();
    await page.locator('#sy-memory-id').waitFor();
    assert.equal(book.event_count,1,'lost response must not create a second event');
    await page.locator('#sy-memory-id').fill('foundation');
    await page.locator('#sy-memory-content').fill('The foundation is level.');
    await page.locator('#sy-memory-add').click();
    await page.getByLabel('Select foundation',{exact:true}).waitFor();
    const changed=request(store,'POST','change',{id:book.id,command:{operation_id:'outside-change',expected_head:book.head,
      action:'add',claim_id:'wall',content:'The wall is vertical.',depends_on:[]}});
    assert.equal(changed.status,200);
    await page.locator('#sy-memory-id').fill('roof');
    await page.locator('#sy-memory-content').fill('The roof covers the house.');
    await page.locator('#sy-memory-add').click();
    await page.getByRole('alert').waitFor();
    await page.getByRole('button',{name:'Reload current notebook',exact:true}).click();
    await page.getByLabel('Select wall',{exact:true}).waitFor();
    await page.locator('#sy-memory-add').click();
    await page.getByLabel('Select roof',{exact:true}).waitFor();
    await page.getByLabel('Select foundation',{exact:true}).check();
    await page.getByLabel('Select wall',{exact:true}).check();
    await page.getByRole('button',{name:'Record disagreement',exact:true}).click();
    await page.getByRole('heading',{name:'Active disagreements',exact:true}).waitFor();
    await page.locator('#sy-memory-context').click();
    await page.getByRole('alert').waitFor();
    await page.getByRole('button',{name:'Close this disagreement',exact:true}).click();
    await page.locator('#sy-memory-context').click();
    await page.locator('#sy-memory-download').waitFor();
    assert.deepEqual(book.closure_ids,['foundation','wall']);
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(await axe(page),[]);
    await page.getByText('Retained history and prior disagreements',{exact:true}).click();
    assert.equal(await page.locator('#sy-memory-content').evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=16),true);
    assert.deepEqual(errors,[]);
  } finally {await context.close();await fs.rm(store,{recursive:true,force:true});}
});

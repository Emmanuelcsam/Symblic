// Actual browser + Python API/state engine. All stores temp; all external calls fake.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import readline from 'node:readline';
import path from 'node:path';
import {test, launch,open,noHorizontalScroll,axe,root} from './host-harness.mjs';
let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
function fixture(){
  const child=spawn(process.env.TEST_PYTHON||'python3',[path.join(root,'tests/browser/forge_fixture.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
  const queue=[];let stderr='';child.stderr.on('data',chunk=>stderr+=chunk);
  readline.createInterface({input:child.stdout}).on('line',line=>{const next=queue.shift();if(next)next.resolve(JSON.parse(line));});
  child.on('exit',code=>{for(const p of queue)p.reject(new Error('Fixture ended '+code+' '+stderr));});
  const sent=[];
  function call(request){return new Promise((resolve,reject)=>{queue.push({resolve,reject});child.stdin.write(JSON.stringify(request)+'\n');});}
  return {sent,close(){child.stdin.end();},call,async api(req,url){if(!url.pathname.startsWith('/api/symblic-forge/'))return {json:{}};
    const request={method:req.method(),route:url.pathname.split('/api/symblic-forge/')[1],query:Object.fromEntries(url.searchParams)};
    if(request.method==='POST'){request.body=req.postDataJSON();sent.push(request);}
    return call(request);}};
}
async function fresh(options={}){const f=fixture();let p;
  try{p=await open(browser,'/symblic-forge.html',f.api,options);await p.page.waitForFunction(()=>window.__forge?.state.catalog);return {...p,f};}
  catch(error){if(p){error.message+='; page errors: '+JSON.stringify(p.errors)+'; API paths: '+JSON.stringify(p.requests.map(r=>r.path));await p.context.close();}f.close();throw error;}
}
async function idea(page,text='I want to create a simple snake game'){await page.getByLabel('Your idea',{exact:true}).fill(text);await page.getByRole('button',{name:'Commit idea',exact:true}).click();await page.waitForFunction(()=>window.__forge.state.project);}
async function cmd(page,text){await page.evaluate(text=>window.__forge.command(text),text);}
async function closeDialog(page){await page.getByRole('button',{name:'Close',exact:true}).click();}
async function ready(page){await page.waitForFunction(()=>!window.__forge.state.busy);}
async function demo(page){await page.getByRole('button',{name:'Project…',exact:true}).click();await page.getByRole('button',{name:'Load Snake demonstration',exact:true}).click();await page.getByRole('button',{name:'Confirm',exact:true}).click();await page.waitForFunction(()=>window.__forge.state.analysis?.counts.accepted>20);}
async function configureFirstAgent(page){await page.locator('.symblic-team-member').first().locator('summary').first().click();
  await page.getByLabel('Agent 1 engine',{exact:true}).selectOption('ollama');await page.getByLabel('Agent 1 device',{exact:true}).selectOption('node-f');
  await page.getByLabel('Agent 1 model',{exact:true}).fill('qwen3:4b-instruct');}

test('old or malformed catalogue team capabilities refuse every new team request',async()=>{
  for(const version of [undefined,'1']){
    const f=fixture();const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
      const result=await f.api(req,url);
      if(url.pathname.endsWith('/models')){if(version===undefined)delete result.json.team_capabilities;else result.json.team_capabilities.version=version;}
      return result;
    },{storage:'window.WebSocket=class{close(){}};'});try{
      await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);
      await page.getByRole('button',{name:'Ask agents',exact:true}).click();
      await page.locator('#error').filter({hasText:'This backend does not support configurable agent teams'}).waitFor();
      assert.equal(await page.locator('dialog[open]').count(),0);
      assert.equal(f.sent.filter(r=>r.route==='model/start').length,0);
      assert.equal(await page.evaluate(()=>window.__forge.state.pending),null);assert.deepEqual(errors,[]);
    }finally{await context.close();f.close();}
  }
});

test('a catalogue downgrade after team editing refuses submit without replacing the draft',async()=>{
  const f=fixture();const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(url.pathname.endsWith('/models')&&url.searchParams.get('refresh')==='1')delete result.json.team_capabilities;
    return result;
  },{storage:'window.WebSocket=class{close(){}};'});try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);
    await page.getByRole('button',{name:'Ask agents',exact:true}).click();await configureFirstAgent(page);
    const draft=await page.evaluate(()=>JSON.stringify(window.__forge.state.teamDraft));
    await page.getByRole('button',{name:'Refresh agent availability',exact:true}).click();
    await page.waitForFunction(()=>!window.__forge.state.models.team_capabilities);
    await page.getByRole('button',{name:'Request proposals',exact:true}).click();
    await page.locator('#dialog-error').filter({hasText:'This backend does not support configurable agent teams'}).waitFor();
    assert.equal(await page.evaluate(()=>JSON.stringify(window.__forge.state.teamDraft)),draft);
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,0);
    assert.equal(await page.evaluate(()=>window.__forge.state.pending),null);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('an exact pending team retry stays retained when the backend lacks team support',async()=>{
  const f=fixture();const created=await f.call({method:'POST',route:'project/create',body:{request_id:'old-team-recovery-project',idea:'Preserve exact team intent',title:'Recovery project',template:''}});
  assert.equal(created.status,200);const id=created.json.project.id;
  const pending={route:'model/start',body:{id,revision:0,request_id:'old-team-recovery-request',role:'QUESTIONER',instruction:'Review this project.',
    team:{version:1,members:[{id:'member-1',engine:'ollama',node:'node-f',model:'qwen3:4b-instruct',effort:'',role:'Reviewer',characteristics:'',instruction:'',settings:{},weight:1}]}}};
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);if(url.pathname.endsWith('/models'))delete result.json.team_capabilities;return result;
  },{storage:'window.WebSocket=class{close(){}};localStorage.setItem("forge.active",'+JSON.stringify(id)+');sessionStorage.setItem("forge.pending",'+JSON.stringify(JSON.stringify(pending))+');'});try{
    await page.getByRole('button',{name:'Retry exact saved action',exact:true}).waitFor();
    await page.getByRole('button',{name:'Retry exact saved action',exact:true}).click();
    await page.locator('#dialog-error').filter({hasText:'This backend does not support configurable agent teams'}).waitFor();
    assert.deepEqual(await page.evaluate(()=>window.__forge.state.pending),pending);
    assert.deepEqual(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('forge.pending'))),pending);
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,0);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('agent choices loaded for another project cannot open a stale request dialog',async()=>{
  const f=fixture();let release=null,held=false;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(url.pathname.endsWith('/models')&&!held){held=true;await new Promise(resolve=>{release=resolve;});}
    return result;
  },{storage:'window.WebSocket=class{close(){}};'});try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);
    const firstId=await page.evaluate(()=>window.__forge.state.project.id);
    const second=await f.call({method:'POST',route:'project/create',body:{request_id:'catalogue-project-b',
      idea:'A separate weather display project.',title:'Second project',template:''}});
    assert.equal(second.status,200);const secondId=second.json.project.id;
    await page.reload();await page.waitForFunction(()=>window.__forge?.state.project);
    assert.equal(await page.evaluate(()=>window.__forge.state.project.id),firstId);
    await page.getByLabel('Active project',{exact:true}).locator('option[value="'+secondId+'"]').waitFor({state:'attached'});
    await page.locator('#input').fill('Inspect the Snake movement contract from project A.');
    await page.getByRole('button',{name:'Ask agents',exact:true}).click();
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));
    await page.getByLabel('Active project',{exact:true}).selectOption(secondId);
    await page.waitForFunction(id=>window.__forge.state.project.id===id,secondId);
    release();await page.locator('#error').filter({hasText:'The project changed while agent choices loaded'}).waitFor();
    assert.equal(await page.locator('dialog[open]').count(),0);
    assert.equal(await page.evaluate(()=>window.__forge.state.project.id),secondId);
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,0);
    await page.locator('#input').fill('Inspect the weather display contract from project B.');
    await page.getByRole('button',{name:'Ask agents',exact:true}).click();
    await page.getByLabel('Your request to this team',{exact:true}).waitFor();
    assert.equal(await page.getByLabel('Your request to this team',{exact:true}).inputValue(),'Inspect the weather display contract from project B.');
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,0);assert.deepEqual(errors,[]);
  }finally{release?.();await context.close();f.close();}
});

test('out-of-order project loads keep the latest selection and clearing invalidates an older load',async()=>{
  const f=fixture();let delayedId='',release=null;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(url.pathname.endsWith('/project')&&url.searchParams.get('id')===delayedId){delayedId='';await new Promise(resolve=>{release=resolve;});}
    return result;
  },{storage:'window.WebSocket=class{close(){}};'});try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);
    const ids=[];
    for(const title of ['Second project','Third project']){
      const result=await f.call({method:'POST',route:'project/create',body:{request_id:'ordered-'+title.replaceAll(' ','-'),idea:title,title,template:''}});
      assert.equal(result.status,200);ids.push(result.json.project.id);
    }
    await page.reload();await page.waitForFunction(()=>window.__forge?.state.project);
    await page.getByLabel('Active project',{exact:true}).locator('option[value="'+ids[1]+'"]').waitFor({state:'attached'});
    delayedId=ids[0];await page.getByLabel('Active project',{exact:true}).selectOption(ids[0]);
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));
    await page.getByLabel('Active project',{exact:true}).selectOption(ids[1]);
    await page.waitForFunction(id=>window.__forge.state.project.id===id,ids[1]);
    const firstReply=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/project')&&new URL(r.url()).searchParams.get('id')===ids[0]);
    release();await firstReply;await page.waitForTimeout(50);
    assert.equal(await page.evaluate(()=>window.__forge.state.project.id),ids[1]);
    assert.equal(await page.getByLabel('Active project',{exact:true}).inputValue(),ids[1]);
    assert.equal(await page.evaluate(()=>localStorage.getItem('forge.active')),ids[1]);
    release=null;delayedId=ids[0];await page.getByLabel('Active project',{exact:true}).selectOption(ids[0]);
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));
    await page.getByLabel('Active project',{exact:true}).selectOption('');
    const secondReply=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/project')&&new URL(r.url()).searchParams.get('id')===ids[0]);
    release();await secondReply;await page.waitForTimeout(50);
    assert.equal(await page.evaluate(()=>window.__forge.state.project),null);
    assert.equal(await page.evaluate(()=>localStorage.getItem('forge.active')),null);
    assert.deepEqual(errors,[]);
  }finally{release?.();await context.close();f.close();}
});

test('a delayed job poll cannot put another project jobs into the selected project',async()=>{
  const f=fixture();let delayedId='',release=null;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(url.pathname.endsWith('/project')&&url.searchParams.get('id')===delayedId){delayedId='';await new Promise(resolve=>{release=resolve;});}
    return result;
  },{storage:()=>{window.WebSocket=class{close(){}};const nativeTimeout=window.setTimeout;let nextPoll;
    window.setTimeout=(fn,delay,...args)=>{if(fn.name==='poll'&&delay===5000){nextPoll=fn;return 1;}return nativeTimeout(fn,delay,...args);};
    window.fixtureRunPoll=()=>nextPoll();}});try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);
    const firstId=await page.evaluate(()=>window.__forge.state.project.id);
    const result=await f.call({method:'POST',route:'project/create',body:{request_id:'poll-project-b',idea:'Weather display',title:'Second project',template:''}});
    assert.equal(result.status,200);const secondId=result.json.project.id;
    await page.reload();await page.waitForFunction(()=>window.__forge?.state.project);
    await page.getByRole('button',{name:'Ask agents',exact:true}).click();await configureFirstAgent(page);
    await page.getByRole('button',{name:'Request proposals',exact:true}).click();await ready(page);
    const jobId=await page.evaluate(()=>window.__forge.state.jobs[0].id);
    assert.equal(await page.evaluate(()=>window.__forge.state.jobs[0].status),'queued');
    delayedId=firstId;await page.evaluate(()=>{window.fixturePendingPoll=window.fixtureRunPoll();});
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));
    await page.getByLabel('Active project',{exact:true}).selectOption(secondId);
    await page.waitForFunction(id=>window.__forge.state.project.id===id,secondId);
    release();await page.evaluate(()=>window.fixturePendingPoll);
    assert.equal(await page.evaluate(()=>window.__forge.state.project.id),secondId);
    assert.deepEqual(await page.evaluate(()=>window.__forge.state.jobs),[]);
    assert.equal(await page.locator('#workspace').getByText(jobId,{exact:false}).count(),0);
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,1);
    assert.equal(f.sent.filter(r=>['model/stop','model/recover'].includes(r.route)).length,0);assert.deepEqual(errors,[]);
  }finally{release?.();await context.close();f.close();}
});

test('project selection stays locked while a lost committed reply reloads its exact project',async()=>{
  const f=fixture();let release=null;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(url.pathname.endsWith('/action')&&req.postDataJSON()?.action==='project.rename'){
      await new Promise(resolve=>{release=resolve;});return {abort:true};
    }
    return result;
  },{storage:'window.WebSocket=class{close(){}};'});try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);
    const id=await page.evaluate(()=>window.__forge.state.project.id);
    await page.locator('#input').fill('/rename Reconciled committed title');await page.locator('#submit').click();
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));
    assert.equal(await page.getByLabel('Active project',{exact:true}).isDisabled(),true);
    release();await page.waitForFunction(()=>window.__forge.state.project.title==='Reconciled committed title'&&!window.__forge.state.busy);
    assert.equal(await page.evaluate(()=>window.__forge.state.project.id),id);
    assert.equal(await page.evaluate(()=>window.__forge.state.pending),null);
    assert.equal(await page.getByLabel('Active project',{exact:true}).isDisabled(),false);
    assert.equal(f.sent.filter(r=>r.route==='action').length,1);assert.deepEqual(errors,[]);
  }finally{release?.();await context.close();f.close();}
});

test('a delayed coach preview cannot restore stale wording after the contract changes',async()=>{
  const f=fixture();let release=null,hold=true;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(hold&&url.pathname.endsWith('/coach/preview'))await new Promise(resolve=>{release=resolve;});
    return result;
  });try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);await cmd(page,'/coach');
    for(const [label,value]of Object.entries({'One action':'Write A.','Inputs':'literal A','Expected output':'output record',
      'Observable check':'Output equals A.','Allowed context':'Only the literal A.'}))await page.getByLabel(label,{exact:true}).fill(value);
    await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();
    await page.waitForFunction(()=>window.__forge.state.busy);
    await page.getByLabel('One action',{exact:true}).fill('Write B.');
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));hold=false;release();await ready(page);
    assert.equal(await page.getByLabel('Review and edit the proposed instruction',{exact:true}).count(),0);
    assert.match(await page.getByRole('region',{name:'Atomic instruction preview'}).innerText(),/Preview the changed fields/);
    await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();
    assert.match(await page.getByLabel('Review and edit the proposed instruction',{exact:true}).inputValue(),/Write B/);
    assert.equal(f.sent.filter(r=>r.route==='coach/propose').length,0);assert.deepEqual(errors,[]);
  }finally{release?.();await context.close();f.close();}
});

test('coached instruction becomes an explicitly reviewed unit and compiler-valid handoff source',async()=>{
  const {page,context,errors,f}=await fresh({mobile:true});try{
    await idea(page,'Create a bounded Snake movement step');await cmd(page,'/coach');
    for(const [label,value]of Object.entries({'One action':'Compute one rightward Snake step.','Inputs':'body=[(2,2),(1,2)]',
      'Expected output':'next body cells in snake/src/state.js','Observable check':'Return [(3,2),(2,2)] without changing the input.',
      'Allowed context':'Only the supplied ordered cells. No hidden history.'}))await page.getByLabel(label,{exact:true}).fill(value);
    await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();
    const edited=await page.getByLabel('Review and edit the proposed instruction',{exact:true}).inputValue()+'\nPreserve exact integer cells.';
    await page.getByLabel('Review and edit the proposed instruction',{exact:true}).fill(edited);
    await page.getByRole('button',{name:'Prepare a construction unit',exact:true}).click();
    await page.getByLabel('Component name',{exact:true}).fill('Snake state');
    await page.getByRole('button',{name:'Propose component',exact:true}).click();await ready(page);
    await page.getByRole('button',{name:'Accept component',exact:true}).click();await ready(page);
    await cmd(page,'/coach');await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();
    assert.equal(await page.getByLabel('Review and edit the proposed instruction',{exact:true}).inputValue(),edited);
    await page.getByRole('button',{name:'Prepare a construction unit',exact:true}).click();
    await page.getByLabel('Target paths (optional)',{exact:true}).fill('snake/src/state.js');
    await page.getByRole('button',{name:'Propose instruction and unit',exact:true}).click();await ready(page);
    const proposed=await page.evaluate(()=>{const b=window.__forge.state.project.branches.main;return {statement:b.statements.at(-1),unit:b.entities.units.at(-1)};});
    assert.equal(proposed.statement.status,'proposed');assert.equal(proposed.unit.status,'proposed');
    assert.equal(proposed.statement.text,edited);assert.deepEqual(proposed.unit.requirement_ids,[proposed.statement.id]);
    await page.locator('#workspace').getByRole('button',{name:'Accept statement',exact:true}).click();await ready(page);
    await page.locator('#workspace').getByRole('button',{name:'Accept unit',exact:true}).click();await ready(page);
    await cmd(page,'/validate');assert.equal(await page.evaluate(()=>window.__forge.state.project.branches.main.validation.ok),true);
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,0);
    assert.equal(await noHorizontalScroll(page),true);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('Snake keyboard decisions, edited suggestion, provenance, snapshot, reload and branch preserve authority',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await idea(page);assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),0);
    await page.getByRole('button',{name:'Skip animation',exact:true}).click();
    assert.match(await page.locator('#question').innerText(),/render/i);
    await page.getByRole('button',{name:'Edit suggestion',exact:true}).first().click();
    await page.getByLabel('Your edited suggestion',{exact:true}).fill('Canvas 2D with exact solid-color rectangles.');
    await page.getByRole('button',{name:'Accept edited suggestion',exact:true}).click();await ready(page);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),0);
    await page.getByRole('button',{name:'Accept statement',exact:true}).click();await ready(page);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),1);
    await cmd(page,'/spec');await page.getByRole('button',{name:'Originating decisions',exact:true}).first().click();
    assert.match(await page.locator('#dialog-body').innerText(),/Canvas 2D with exact/);await closeDialog(page);
    await cmd(page,'/snapshot Before branch');const before=await page.evaluate(()=>window.__forge.state.fingerprint);
    await cmd(page,'/branch Browser alternative');await cmd(page,'/rename Alternative title');await cmd(page,'/undo');await cmd(page,'/redo');
    await page.reload();await page.waitForFunction(()=>window.__forge?.state.project?.title==='Alternative title');
    assert.equal(await page.evaluate(()=>window.__forge.state.fingerprint),before);
    await cmd(page,'/branches');assert.match(await page.locator('#workspace').innerText(),/Browser alternative/);
    const posts=f.sent.length;await cmd(page,'/clear');assert.equal(f.sent.length,posts);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),1);
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('demo compiler, seven reproducible exports, immutable handoff and all engineering views are usable',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await demo(page);await cmd(page,'/validate');assert.equal(await page.evaluate(()=>window.__forge.state.project.branches[window.__forge.state.project.active_branch].validation.ok),true);
    for(const view of ['status','spec','proposed','questions','conflicts','assumptions','completeness','objectives','architecture','components','units','agents','models','cluster','tests','invariants','forbidden','evidence','scope','parked','vocabulary','snapshots','branches','history','search','source','exports','jobs']){
      await cmd(page,'/'+view);assert.equal(await page.locator('#workspace h2').count(),1,view);
    }
    await page.getByRole('button',{name:'Ask your agents',exact:true}).click();await configureFirstAgent(page);
    assert.equal(await page.getByLabel('Agent 1 model',{exact:true}).inputValue(),'qwen3:4b-instruct');
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    await cmd(page,'/exports');
    for(const format of ['manifest','brief','prompt','construction','tasks','sheet','symblic']){
      const event=page.waitForEvent('download');await page.getByRole('button',{name:'Export '+format,exact:true}).click();
      const download=await event;await ready(page);const chunks=[];
      for await(const chunk of await download.createReadStream())chunks.push(chunk);
      const bytes=Buffer.concat(chunks);const receipt=await page.evaluate(()=>window.__forge.state.project.exports.at(-1));
      assert.equal(receipt.kind,format);assert.equal(createHash('sha256').update(bytes).digest('hex'),receipt.sha256);
      assert.ok(download.suggestedFilename().startsWith('forge-'+format+'.'));
    }
    await page.getByRole('button',{name:'Freeze build handoff',exact:true}).click();await page.getByRole('button',{name:'Confirm',exact:true}).click();
    await page.getByRole('heading',{name:'Frozen build handoff',exact:true}).waitFor();assert.match(await page.locator('#dialog-body').innerText(),/"execution_started": false/);await closeDialog(page);
    assert.equal(await page.evaluate(()=>window.__forge.state.jobs.length),0);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('ordinary pixel answers derive accepted area and export their width and height meaning',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await idea(page);
    for(const [key,answer] of [['rendering','HTML canvas 2D'],['viewport.width','eight hundred pixels'],['viewport.height','600 pixels']]){
      const id=await page.evaluate(key=>window.__forge.state.project.branches[window.__forge.state.project.active_branch].questions.find(q=>q.key===key).id,key);
      await cmd(page,'/question '+id);await page.locator('#input').fill(answer);await page.locator('#submit').click();await ready(page);
      if(key==='viewport.height')assert.equal(await page.evaluate(()=>window.__forge.state.analysis.derived.length),0);
      await page.locator('#proposals').getByRole('button',{name:'Accept statement',exact:true}).click();await ready(page);
    }
    const details=await page.evaluate(()=>({derived:window.__forge.state.analysis.derived,prompt:window.__forge.state.analysis.accepted_prompt,
      answers:window.__forge.state.project.branches[window.__forge.state.project.active_branch].answers.map(a=>a.text)}));
    assert.ok(details.derived.some(r=>r.value===480000));assert.ok(details.answers.includes('eight hundred pixels'));
    assert.match(details.prompt,/viewport\.width/);assert.match(details.prompt,/viewport\.height/);
    await cmd(page,'/validate');const valid=await page.evaluate(()=>window.__forge.state.project.branches[window.__forge.state.project.active_branch].validation);
    assert.equal(valid.ok,true);assert.match(valid.source,/viewport\.width/);assert.match(valid.source,/viewport\.height/);
    await page.reload();await page.waitForFunction(()=>window.__forge?.state.project);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.accepted_prompt),details.prompt);
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('phone, reduced motion, complete text, XSS data, focus and accessible controls',async()=>{
  const {page,context,errors,f}=await fresh({mobile:true});try{
    await page.emulateMedia({reducedMotion:'reduce',colorScheme:'dark'});
    await idea(page,'I want a simple snake game. <img src=x onerror="window.forgeXSS=1">');
    assert.equal(await page.evaluate(()=>window.forgeXSS),undefined);
    assert.equal(await noHorizontalScroll(page),true);
    await cmd(page,'/questions');await cmd(page,'/focus');assert.equal(await page.locator('#drawer').getAttribute('open'),null);
    await page.getByRole('button',{name:'Overview',exact:true}).click();await ready(page);assert.equal(await page.locator('#overview').isVisible(),true);
    const fonts=await page.locator('input,textarea,select').evaluateAll(nodes=>nodes.filter(n=>n.offsetParent).map(n=>parseFloat(getComputedStyle(n).fontSize)));
    assert.ok(fonts.every(v=>v>=16),String(fonts));assert.deepEqual(await axe(page),[]);
    await cmd(page,'/skip');const complete=await page.locator('#question [data-complete-text]').evaluateAll(nodes=>nodes.length&&nodes.every(n=>n.querySelector('[aria-hidden]').textContent===n.dataset.completeText&&n.querySelector('.forge-sr-only').textContent===n.dataset.completeText));assert.ok(complete);
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('model request survives reload without redispatch and explicit stop frees its pending state',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await idea(page);await cmd(page,'/model QUESTIONER');
    await configureFirstAgent(page);
    await page.getByRole('button',{name:'Request proposals',exact:true}).click();await ready(page);
    await page.getByRole('button',{name:'Stop owned request',exact:true}).waitFor();
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,1);await page.reload();await page.waitForFunction(()=>window.__forge?.state.jobs.length===1);
    assert.equal(f.sent.filter(r=>r.route==='model/start').length,1);await cmd(page,'/jobs');
    await page.getByRole('button',{name:'Stop owned request',exact:true}).click();await ready(page);
    await page.waitForFunction(()=>window.__forge.state.jobs[0].status==='cancelled');assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('five mixed agents retain exact devices, custom profiles and per-prompt controls across reload',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await idea(page);await page.getByRole('button',{name:'Ask agents',exact:true}).click();await configureFirstAgent(page);
    await page.getByLabel('Agent 1 role',{exact:true}).fill('Interaction designer');
    await page.getByLabel('Agent 1 characteristics',{exact:true}).fill('Precise. <img src=x onerror="window.teamXSS=1">');
    await page.getByLabel('Agent 1 instructions',{exact:true}).fill('Keep exact dimensions.\nIdentify one missing decision.');
    await page.getByLabel('Number of agents',{exact:true}).fill('5');await page.getByRole('button',{name:'Set size',exact:true}).click();
    assert.equal(await page.locator('.symblic-team-member').count(),5);
    await page.locator('.symblic-team-member').nth(1).locator('summary').first().click();
    await page.getByLabel('Agent 2 engine',{exact:true}).selectOption('codex');await page.getByLabel('Agent 2 device',{exact:true}).selectOption('node-i');
    await page.getByLabel('Agent 2 model',{exact:true}).fill('fixture');await page.getByLabel('Agent 2 effort',{exact:true}).selectOption('high');
    await page.getByLabel('Agent 2 role',{exact:true}).fill('Edge case reviewer');
    await page.locator('.symblic-team-member').nth(2).locator('summary').first().click();
    await page.getByLabel('Agent 3 engine',{exact:true}).selectOption('chatgpt');await page.getByLabel('Agent 3 device',{exact:true}).selectOption('host');
    await page.getByLabel('Agent 3 model',{exact:true}).fill('fixture');
    await page.getByLabel('How the agents contribute',{exact:true}).selectOption('critique');
    await page.getByText('Context & request settings',{exact:true}).click();await page.getByLabel('Allow selected cloud and web agents',{exact:true}).check();
    await page.getByRole('button',{name:'Request proposals',exact:true}).click();await ready(page);
    const request=f.sent.find(row=>row.route==='model/start').body;assert.equal(request.team.members.length,5);assert.equal(request.strategy,'critique');
    assert.equal(new Set(request.team.members.map(m=>m.id)).size,5);assert.equal(request.team.members[1].engine,'codex');assert.equal(request.team.members[1].node,'node-i');
    assert.equal(request.team.members[1].role,'Edge case reviewer');assert.equal(request.team.members[0].instruction,'Keep exact dimensions.\nIdentify one missing decision.');
    const retained=await page.evaluate(()=>window.__forge.state.jobs[0].request.team);assert.equal(retained.members.length,5);assert.equal(retained.members[1].effort,'high');
    const sent=f.sent.length;await page.reload();await page.waitForFunction(()=>window.__forge?.state.project);assert.equal(f.sent.length,sent);
    await page.getByRole('button',{name:'Ask agents',exact:true}).click();assert.equal(await page.getByLabel('Number of agents',{exact:true}).inputValue(),'5');
    assert.equal(await page.evaluate(()=>window.teamXSS),undefined);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('mobile spec coach teaches an atomic contract and preserves explicit proposal acceptance',async()=>{
  const {page,context,errors,f}=await fresh({mobile:true});try{
    await idea(page);await page.locator('#input').fill('compute one Snake step.');await page.getByRole('button',{name:'Shape this instruction',exact:true}).click();
    await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();await ready(page);
    assert.equal(await page.getByRole('button',{name:'Add as a proposal',exact:true}).isDisabled(),true);
    await page.getByLabel('Inputs',{exact:true}).fill('the ordered body cells and direction');
    await page.getByLabel('Expected output',{exact:true}).fill('the next ordered body cells');
    await page.getByLabel('Observable check',{exact:true}).fill('[(2,2),(1,2)] moving right returns [(3,2),(2,2)].');
    await page.getByLabel('Allowed context',{exact:true}).fill('one square cell per tick; no rendering');
    await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();await ready(page);
    const block=await page.getByLabel('Review and edit the proposed instruction',{exact:true}).inputValue();assert.match(block,/Finish this step\./);assert.match(block,/Use only this input:/);
    await page.getByLabel('Review and edit the proposed instruction',{exact:true}).fill(block+'\nPreserve the input unchanged.');
    await page.getByRole('button',{name:'Add as a proposal',exact:true}).click();await ready(page);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),0);
    assert.equal(await page.evaluate(()=>window.__forge.state.project.branches.main.statements.at(-1).text),block+'\nPreserve the input unchanged.');
    await page.locator('#workspace').getByRole('button',{name:'Accept statement',exact:true}).click();await ready(page);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),1);
    await cmd(page,'/explore');await page.getByLabel('Thinking lens',{exact:true}).waitFor();assert.ok(await page.getByLabel('Thinking lens',{exact:true}).locator('option').count()>5);
    assert.equal(f.sent.filter(row=>row.route==='model/start').length,0);assert.equal(await noHorizontalScroll(page),true);assert.deepEqual(await axe(page),[]);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('New template project, multiline entry and data-only evidence attachment',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await page.getByRole('button',{name:'New',exact:true}).click();await page.getByLabel('Exact original idea',{exact:true}).fill('A bounded research experiment');
    await page.getByLabel('Question template (optional)',{exact:true}).selectOption('research');await page.locator('#dialog-save').click();await ready(page);
    await page.waitForFunction(()=>window.__forge.state.project);const input=page.locator('#input');await input.fill('First line');await input.press('Shift+Enter');await input.type('Second line');assert.equal(await input.inputValue(),'First line\nSecond line');
    const count=f.sent.length;assert.equal(f.sent.length,count);await cmd(page,'/evidence');const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Attach evidence file',exact:true}).click();
    await(await chooser).setFiles({name:'observations.txt',mimeType:'text/plain',buffer:Buffer.from('Measured 20 mm.\n')});await page.getByRole('button',{name:'Download observations.txt',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>window.__forge.state.project.branches[window.__forge.state.project.active_branch].entities.evidence[0].status),'proposed');
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('400 accepted requirements remain inspectable, searchable and responsive at declared fixture scale',async()=>{
  const {page,context,errors,f}=await fresh();try{
    const start=performance.now(),result=await f.call({method:'POST',route:'fixture/scaling'});
    assert.equal(result.status,200,JSON.stringify(result));
    await page.evaluate(id=>window.__forge.load(id),result.json.project.id);
    const loaded=performance.now();await cmd(page,'/spec');
    assert.equal(await page.locator('#workspace .forge-record.accepted').count(),400);
    const rendered=performance.now();await cmd(page,'/search');await page.getByLabel('Search statements, decisions, questions, components, tests and revisions',{exact:true}).fill('requirement 399');
    await page.locator('#workspace').getByRole('button',{name:'Search',exact:true}).click();await page.getByText('Accepted fixture requirement 399',{exact:false}).waitFor();
    const searched=performance.now();console.log('Forge400 timing ms '+JSON.stringify({create_load:Math.round(loaded-start),render:Math.round(rendered-loaded),search:Math.round(searched-rendered)}));
    assert.ok(rendered-loaded<10000,'400-record view exceeded the browser responsiveness guard');
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('offline before commit recovers only by explicit exact-identity retry after reload',async()=>{
  const f=fixture(),attempts=[];let first=true;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    if(url.pathname.endsWith('/project/create')&&req.method()==='POST'){attempts.push(req.postDataJSON());if(first){first=false;return {abort:true};}}
    return f.api(req,url);
  });try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await page.locator('#input').fill('Unsent fixture idea');await page.locator('#submit').click();
    await page.waitForFunction(()=>window.__forge.state.pending&&!window.__forge.state.busy);assert.equal(attempts.length,1);
    await page.reload();await page.getByRole('button',{name:'Retry exact saved action',exact:true}).waitFor();assert.equal(attempts.length,1);
    await page.getByRole('button',{name:'Retry exact saved action',exact:true}).click();await page.waitForFunction(()=>window.__forge.state.project&&!window.__forge.state.pending);
    assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1]);assert.equal(f.sent.filter(r=>r.route==='project/create').length,1);
    assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('session storage failure refuses sending without locking the composer',async()=>{
  const {page,context,errors,f}=await fresh({storage:()=>{window.fixtureSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key==='forge.pending')throw new DOMException('Fixture storage quota exceeded','QuotaExceededError');return window.fixtureSetItem.call(this,key,value);};}});try{
    await page.locator('#input').fill('Storage test idea');await page.locator('#submit').click();await page.locator('#error').waitFor();
    assert.equal(await page.evaluate(()=>window.__forge.state.busy),false);assert.equal(await page.locator('#submit').isDisabled(),false);assert.equal(f.sent.length,0);
    await page.evaluate(()=>{Storage.prototype.setItem=window.fixtureSetItem;});await page.locator('#submit').click();await page.waitForFunction(()=>window.__forge.state.project);
    assert.equal(f.sent.length,1);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('cluster byte quantities are numbers and inventory objects survive actual form editing',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await idea(page,'A bounded local cluster workload');await cmd(page,'/cluster');
    await page.getByRole('button',{name:'Propose cluster',exact:true}).click();
    await page.getByLabel('Description',{exact:true}).fill('Two independent workers with explicit byte budgets.');
    await page.getByLabel('capabilities (required)',{exact:true}).fill('cpu');
    await page.getByLabel('memory bytes',{exact:true}).fill('1024');
    await page.getByLabel('storage bytes',{exact:true}).fill('2048');
    await page.getByLabel('concurrency',{exact:true}).fill('2');
    await page.getByLabel('node id',{exact:true}).fill('node-i');
    await page.getByRole('button',{name:'Create proposal',exact:true}).click();await ready(page);
    const plan=await page.evaluate(()=>window.__forge.state.project.branches[window.__forge.state.project.active_branch].entities.cluster[0]);
    assert.equal(plan.status,'proposed');assert.equal(plan.memory_bytes,1024);assert.equal(plan.storage_bytes,2048);assert.equal(plan.concurrency,2);
    const sentPlan=f.sent.filter(r=>r.route==='action'&&r.body.payload?.kind==='cluster').at(-1).body.payload.entity;
    assert.equal(typeof sentPlan.memory_bytes,'number');assert.equal(typeof sentPlan.storage_bytes,'number');
    await cmd(page,'/evidence');await page.getByRole('button',{name:'Propose evidence',exact:true}).click();
    const inventory={models:[],nodes:[{id:'node-i',models:[],memory_bytes:8192,storage_bytes:16384}],complete:true,source:'Explicit test fixture inventory'};
    await page.getByLabel('Description',{exact:true}).fill('Retained structured inventory fixture.');
    await page.getByLabel('evidence type (required)',{exact:true}).fill('inventory');
    await page.getByLabel('inventory',{exact:true}).fill(JSON.stringify(inventory));
    await page.getByLabel('captured at',{exact:true}).fill('0');
    await page.getByRole('button',{name:'Create proposal',exact:true}).click();await ready(page);
    await page.locator('#workspace').getByRole('button',{name:'Edit',exact:true}).click();
    assert.deepEqual(JSON.parse(await page.getByLabel('inventory',{exact:true}).inputValue()),inventory);
    await page.getByLabel('Description',{exact:true}).fill('Same inventory, edited explanation.');
    await page.getByRole('button',{name:'Commit entity revision',exact:true}).click();await ready(page);
    const evidence=await page.evaluate(()=>window.__forge.state.project.branches[window.__forge.state.project.active_branch].entities.evidence[0]);
    assert.deepEqual(evidence.inventory,inventory);assert.equal(evidence.captured_at,0);assert.equal(evidence.status,'proposed');
    assert.equal(evidence.text,'Same inventory, edited explanation.');assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('unit form preserves commas and JSON-shaped prose in exact line lists through exports',async()=>{
  const {page,context,errors,f}=await fresh();try{
    await demo(page);await cmd(page,'/units');
    await page.locator('#workspace').getByRole('button',{name:'Edit',exact:true}).first().click();
    const paths=['snake/src/state,shared.js','snake/src/draw.js'];
    const checks=['[body=(2,2),(1,2)] moving right returns [(3,2),(2,2)].','Preserve x,y coordinates.'];
    await page.getByLabel('paths',{exact:true}).fill(paths.join('\n'));
    await page.getByLabel('checks (required)',{exact:true}).fill(checks.join('\n'));
    await page.getByRole('button',{name:'Commit entity revision',exact:true}).click();await ready(page);
    const changed=await page.evaluate(()=>window.__forge.state.project.branches.main.entities.units[0]);
    assert.deepEqual(changed.paths,paths);assert.deepEqual(changed.checks,checks);assert.equal(changed.status,'proposed');
    await page.locator('#workspace').getByRole('button',{name:'Accept unit',exact:true}).click();await ready(page);
    await page.locator('#workspace').getByRole('button',{name:'Edit',exact:true}).first().click();
    assert.equal(await page.getByLabel('paths',{exact:true}).inputValue(),paths.join('\n'));
    assert.equal(await page.getByLabel('checks (required)',{exact:true}).inputValue(),checks.join('\n'));
    await page.getByRole('button',{name:'Cancel',exact:true}).click();await cmd(page,'/exports');
    const exported=page.waitForEvent('download');await page.getByRole('button',{name:'Export tasks',exact:true}).click();
    const chunks=[];for await(const chunk of await(await exported).createReadStream())chunks.push(chunk);
    const cards=JSON.parse(Buffer.concat(chunks).toString());const card=cards.find(row=>row.id===changed.id);
    assert.deepEqual(card.paths,paths);assert.deepEqual(card.verification,checks);
    assert.equal(f.sent.filter(row=>row.route==='model/start').length,0);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

test('delayed history cannot append old project records to a newer workspace view',{timeout:30000},async()=>{
  const f=fixture();let release=null,held=false;
  const {page,context,errors}=await open(browser,'/symblic-forge.html',async(req,url)=>{
    const result=await f.api(req,url);
    if(url.pathname.endsWith('/history')&&!held){held=true;await new Promise(resolve=>{release=resolve;});}
    return result;
  });try{
    await page.waitForFunction(()=>window.__forge?.state.catalog);await idea(page);await cmd(page,'/spec');
    await page.evaluate(()=>{window.fixtureHistory=window.__forge.command('/history');});
    await page.waitForFunction(()=>window.__forge.state.view==='history');
    while(!release)await new Promise(resolve=>setTimeout(resolve,10));
    await cmd(page,'/spec');release();await page.evaluate(()=>window.fixtureHistory);
    assert.equal(await page.locator('#workspace h2').innerText(),'Accepted');
    assert.doesNotMatch(await page.locator('#workspace').innerText(),/Append-only operator trail|project\.create/);
    assert.deepEqual(errors,[]);
  }finally{release?.();await context.close();f.close();}
});

test('cup teaching example loads a bounded editable draft without accepting or dispatching work',async()=>{
  const {page,context,errors,f}=await fresh({mobile:true});try{
    await idea(page,'A synthetic cup design exercise');await cmd(page,'/coach');
    await page.getByText('Learn from examples',{exact:true}).click();
    assert.equal(await page.getByRole('button',{name:/^Use example:/}).count(),11);
    const before=f.sent.length;
    await page.getByRole('button',{name:'Use example: A dimensioned cup and STL',exact:true}).click();
    await page.getByLabel('One action',{exact:true}).waitFor();
    assert.match(await page.getByLabel('Inputs',{exact:true}).inputValue(),/wall 3 mm, base 4 mm/);
    assert.match(await page.getByLabel('Observable check',{exact:true}).inputValue(),/floor is z=4 mm/);
    assert.equal(f.sent.length,before);
    assert.equal(await page.evaluate(()=>window.__forge.state.analysis.counts.accepted),0);
    await page.getByRole('button',{name:'Preview atomic instruction',exact:true}).click();await ready(page);
    assert.equal(await page.getByRole('button',{name:'Add as a proposal',exact:true}).isEnabled(),true);
    assert.equal(f.sent.filter(row=>row.route==='model/start').length,0);
    assert.equal(await noHorizontalScroll(page),true);assert.deepEqual(errors,[]);
  }finally{await context.close();f.close();}
});

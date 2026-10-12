// All API and static requests are intercepted. No live provider, coordinator, agent, shell or dashboard.
// Run: node --test tests/browser/symblic-autogen.mjs (skipped without the host's page harness; see host-harness.mjs)
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
if (process.env.AUTOGEN_BROWSER_HARNESS) process.env.SYMBLIC_BROWSER_HARNESS = process.env.AUTOGEN_BROWSER_HARNESS;
const {test, launch, open, axe, noHorizontalScroll, root, available} = await import('./host-harness.mjs');
const here = process.env.AUTOGEN_UI_ROOT || path.join(root, 'web', 'hub');
const evidence = process.env.AUTOGEN_BROWSER_ARTIFACTS || path.join(os.tmpdir(), 'symblic-autogen-browser-' + process.pid);
const API = '/api/symblicos/';
const SAVED = 'symblic.autogen.selection.v1';
const LIMITS_V1 = {candidates:[1,4],regenerate:[0,8],depth:[0,3],children:[2,8],generations:[1,16],agents_max:[1,96],
  attempt_seconds:[120,14400],wall_seconds:[300,172800],interval_seconds:[60,86400],feedback_chars:[200,6000]};
const LIMITS = {...LIMITS_V1,novelty_limit:[1,8],saturation:[0,16]};
const DEFAULTS_V1 = {candidates:1,regenerate:2,depth:0,children:4,generations:3,agents_max:24,attempt_seconds:3600,wall_seconds:21600,
  interval_seconds:900,feedback_chars:2000,strategies:['fresh','feedback','other_node','other_engine'],perpetual:false,checks:{},final:[],hidden:[],syntax:true,require_change:true};
const DEFAULTS = {...DEFAULTS_V1,until_done:false,novelty_limit:2,self_split:true,designer:false,saturation:0};
const CATALOG = {version:1,limits:LIMITS,defaults:DEFAULTS,strategies:['fresh','feedback','other_node','other_engine'],
  all_strategies:['fresh','feedback','other_node','other_engine','stronger_model'],
  failure_classes:['INFRASTRUCTURE','REFUSAL','NO_OUTPUT','SYNTAX','CHECK_FAILURE','CLAIM_MISMATCH','CONTEXT_EXHAUSTED','TIMEOUT','CANCELLED','UNKNOWN'],
  handoff_file:'HANDOFF.md',checkpoint_file:'AUTOGEN-CHECKPOINT.json'};
const CATALOG_V1 = {...CATALOG,limits:LIMITS_V1,defaults:DEFAULTS_V1};   // a server not yet restarted onto autogen v2
const UNTIL = 'Until done (no clock or count caps; agents keep regenerating, subdividing and re-planning until the checks pass or the statement is stuck)';
const DESIGNER = 'Test designer (an independent agent writes AUTOGEN-TESTS.sh first; it must fail on an empty folder)';
const SELF_SPLIT = 'Self-split (a worker may answer too big with a split file)';
const NOVELTY = 'Attempts without progress before a split', SATURATION = 'Perpetual generations with nothing new before the lane stops';
const STUCK_HINT = 'Resume after changing the statement, the checks or the catalogue.';
const AGENTS = {specs:{agy:{title:'Antigravity',efforts:[]},claude:{title:'Claude Code',efforts:['high','max']}},
  models:{agy:[],claude:[{id:'opus',title:'Opus'}]},effortTitles:{high:'High',max:'Max'},
  nodes:[{id:'host',name:'host',online:true,local:true},{id:'node-a',name:'node-a',online:true},{id:'node-c',name:'node-c',online:false}]};
const CWD = '/srv/symblic/projects/fixture';
const LINES = ['Create the file add.js in the folder ' + CWD + ' exporting add(a, b) that returns a + b.',
  'Verify the file add.js in the folder ' + CWD + ' by running node --test and writing verify.txt with PASS or FAIL.'];
const runIdFor = requestId => 'autogen-' + createHash('sha256').update(requestId).digest('hex').slice(0, 24);
const TASK = 'task-' + 'c'.repeat(32), TASK2 = 'task-' + 'd'.repeat(32);
function treeRun(id, requestId='fixture-request') {
  const now = Date.now() / 1000;
  return {id, client_request_id:requestId, status:'active', error:'', created:now - 600, updated:now, cancel_requested:false,
    base:{engine:'agy',model:'',effort:'',node:'node-a',cwd:CWD,context_note:'',headless:true},
    policy:{...DEFAULTS,depth:1,final:['node --test']}, lines:LINES,
    budget:{agents_started:5,agents_max:24,deadline:now + 7200}, order:['n0','n1'], final:null, resume_required:false,
    nodes:[
      {id:'n0',index:0,parent:null,depth:0,statement:LINES[0],status:'split',children:['n0.0','n0.1'],generation:0,perpetual:false,winner:'n0-a1',
        decisions:[{at:now-500,action:'launch',reason:'first wave of 1 candidate(s)'},{at:now-400,action:'decompose',reason:'regeneration exhausted on a semantic failure; split the statement'}],
        attempts:[
          {id:'n0-a0',kind:'candidate',strategy:'fresh',engine:'agy',node:'node-a',model:'',generation:0,request_id:requestId+':n0-a0',task_id:TASK,status:'failed',
            started:now-500,finished:now-450,failure:'CHECK_FAILURE',agent_id:'agent-n0a0',workspace:'/tmp/x',error:'command node --test: AssertionError',
            verdict:{passed:false,files_changed:1,report:'',checks:[
              {kind:'exists',file:'add.js',passed:true,output:'',public:true},
              {kind:'command',command:'node --test',passed:false,output:'AssertionError: expected 3 but got <b>"12"</b>',public:true},
              {kind:'hidden',passed:false,output:'SECRET-HIDDEN-OUTPUT',public:false}]}},
          {id:'n0-a1',kind:'planner',strategy:'split',engine:'agy',node:'node-a',model:'',generation:0,request_id:requestId+':n0-a1',task_id:TASK2,status:'accepted',
            started:now-440,finished:now-420,failure:null,agent_id:'agent-n0a1',split:['Create the file add.js in the folder '+CWD+' with add(a, b).','Write the file add.test.js in the folder '+CWD+' testing add.'],
            verdict:{passed:true,files_changed:null,report:'',checks:[{kind:'split',passed:true,public:true,output:'2 lines'}]}}]},
      {id:'n0.0',index:0,parent:'n0',depth:1,statement:'Create the file add.js in the folder '+CWD+' with add(a, b).',status:'accepted',children:[],generation:0,perpetual:false,winner:'n0.0-a0',decisions:[],
        attempts:[{id:'n0.0-a0',kind:'candidate',strategy:'fresh',engine:'agy',node:'node-a',model:'',generation:0,task_id:'',status:'accepted',started:now-400,finished:now-300,failure:null,agent_id:'agent-n00a0',
          verdict:{passed:true,files_changed:1,report:'',checks:[{kind:'syntax',file:'add.js',passed:true,output:'',public:true}]}}]},
      {id:'n0.1',index:1,parent:'n0',depth:1,statement:'Write the file add.test.js in the folder '+CWD+' testing add.',status:'pending',children:[],generation:1,perpetual:false,winner:'',decisions:[],
        attempts:[
          {id:'n0.1-a0',kind:'candidate',strategy:'fresh',engine:'agy',node:'node-a',model:'',generation:0,task_id:'',status:'handoff',started:now-290,finished:now-200,failure:null,agent_id:'agent-n01a0',
            checkpoint:{valid:true,done:['wrote half the tests'],left:['edge cases'],files:['add.test.js']},verdict:{passed:false,files_changed:1,report:'',checks:[]}},
          {id:'n0.1-a1',kind:'handoff',strategy:'handoff',engine:'agy',node:'node-a',model:'',generation:1,from:'n0.1-a0',task_id:'',status:'running',started:now-190,finished:null,failure:null}]},
      {id:'n1',index:1,parent:null,depth:0,statement:LINES[1],status:'pending',children:[],generation:0,perpetual:false,winner:'',decisions:[],attempts:[]}],
    tasks:{[TASK]:{id:TASK,status:'failed',steps:[{index:0,agent_id:'agent-n0a0',url:'/terminal.html?session=agent-n0a0&node=node-a'}]},
      [TASK2]:{id:TASK2,status:'completed',steps:[{index:0,agent_id:'agent-n0a1',url:'javascript:alert(1)'}]}}};
}
function stuckRun(id, requestId='stuck-request') {
  const now = Date.now() / 1000, base = treeRun(id, requestId);
  const why = 'no eligible strategy remains: CHECK_FAILURE, CHECK_FAILURE; every novel action at this subdivision was tried (resume after changing the statement, the checks or the catalogue)';
  const first = 'Create the file add.js in the folder '+CWD+' with add(a, b).', second = 'Write the file add.test.js in the folder '+CWD+' testing add.';
  const attempt = (id, extra) => ({id,engine:'agy',node:'node-a',model:'',generation:0,task_id:'',failure:null,agent_id:'agent-'+id.replace(/[^a-z0-9]/g,''),...extra});
  return {...base, status:'stuck', error:'Statement n0.1 is stuck: '+why, tasks:{},
    policy:{...DEFAULTS,until_done:true,designer:true,agents_max:0,wall_seconds:0,final:['node --test']},
    budget:{agents_started:5,agents_max:0,deadline:null},
    nodes:[
      {id:'n0',index:0,parent:null,depth:0,statement:LINES[0],status:'split',children:['n0.0','n0.1'],generation:0,perpetual:false,winner:'n0-a1',
        stale:0,progress:{},items_total:0,decisions:[],attempts:[
          attempt('n0-a0',{kind:'designer',strategy:'design',status:'design_done',started:now-500,finished:now-480,
            verdict:{passed:true,files_changed:null,report:'',checks:[{kind:'design',file:'AUTOGEN-TESTS.sh',passed:true,public:true,sandbox:'landlock',output:'discriminating: exit 1 on an empty folder'}]}}),
          attempt('n0-a1',{kind:'planner',strategy:'self_split',self_split:true,status:'accepted',started:now-470,finished:now-420,split:[first,second],
            verdict:{passed:true,files_changed:null,report:'',checks:[{kind:'split',passed:true,public:true,output:'2 lines'}]}})]},
      {id:'n0.0',index:0,parent:'n0',depth:1,statement:first,status:'accepted',children:[],generation:0,perpetual:false,winner:'n0.0-a0',
        stale:0,progress:{files:['add.js'],checks:2,done:0},items_total:0,decisions:[],attempts:[
          attempt('n0.0-a0',{kind:'candidate',strategy:'fresh',status:'accepted',started:now-400,finished:now-300,
            verdict:{passed:true,files_changed:1,report:'',checks:[{kind:'syntax',file:'add.js',passed:true,public:true,output:''}]}})]},
      {id:'n0.1',index:1,parent:'n0',depth:1,statement:second,status:'stuck',children:[],generation:0,perpetual:false,winner:'',error:why,
        stale:2,progress:{files:['add.test.js'],checks:1,done:1},items_total:0,decisions:[{at:now-60,action:'stuck',reason:why}],attempts:[
          attempt('n0.1-a0',{kind:'candidate',strategy:'fresh',status:'failed',failure:'CHECK_FAILURE',started:now-290,finished:now-200,
            verdict:{passed:false,files_changed:1,report:'',checks:[{kind:'command',command:'node --test',passed:false,public:true,output:'1 failing'},
              {kind:'designed',file:'AUTOGEN-TESTS.sh',passed:false,public:true,sandbox:'landlock',output:'add: expected 3'}]}}),
          attempt('n0.1-a1',{kind:'regen',strategy:'feedback',status:'failed',failure:'CHECK_FAILURE',started:now-190,finished:now-100,
            verdict:{passed:false,files_changed:1,report:'',checks:[{kind:'command',command:'node --test',passed:false,public:true,output:'1 failing'}]}})]},
      {id:'n1',index:1,parent:null,depth:0,statement:LINES[1],status:'pending',children:[],generation:0,perpetual:false,winner:'',
        stale:0,progress:{},items_total:0,decisions:[],attempts:[]}]};
}
function perpetualRun(id, requestId='perpetual-request') {
  const now = Date.now() / 1000, line = 'Index new sources on lighthouse history in the folder '+CWD+' and append them to the file sources.md.';
  return {...treeRun(id, requestId), lines:[line], order:['n0'], tasks:{}, policy:{...DEFAULTS,perpetual:true,saturation:3},
    budget:{agents_started:4,agents_max:24,deadline:now+3600},
    nodes:[{id:'n0',index:0,parent:null,depth:0,statement:line,status:'pending',children:[],generation:4,perpetual:true,winner:'',
      stale:0,progress:{},items_total:7,stale_generations:1,decisions:[],attempts:[
        {id:'n0-a3',kind:'perpetual',strategy:'perpetual',engine:'agy',node:'node-a',model:'',generation:4,task_id:'',status:'generation_done',
          started:now-900,finished:now-600,failure:null,items_new:0,items_listed:3}]}]};
}
let browser, files;
before(async()=>{
  if (available) await fs.mkdir(evidence, {recursive:true});   // no empty folder when every journey is skipped
  browser=await launch();
  files={'/symblic/':{body:await fs.readFile(path.join(root,'web/hub/index.html'),'utf8'),contentType:'text/html'},
    '/symblic/autogen.js':{body:await fs.readFile(path.join(here,'autogen.js'),'utf8'),contentType:'text/javascript'},
    '/symblic/autogen.css':{body:await fs.readFile(path.join(here,'autogen.css'),'utf8'),contentType:'text/css'}};
});
after(async()=>await browser?.close());
function fixture(options={}) {
  let run=options.run || null;
  const api=async(request,url)=>{
    if (!url.pathname.startsWith(API)) return {json:{}};
    const route=url.pathname.slice(API.length);
    if (options.override) {const got=await options.override(route,request,url);if(got)return got;}
    if(route==='catalog') return {json:AGENTS};
    if(route==='autogen/catalog') return {json:CATALOG};
    if(route==='autogen') return {json:{runs:run?[{...run,tasks:undefined}]:[]}};
    if(route==='autogen/get') return run&&url.searchParams.get('id')===run.id ? {json:{run}} : {status:404,json:{error:'Unknown autogen run id.'}};
    if(route==='workspace/create') return {json:{cwd:CWD,path:CWD,name:request.postDataJSON().name,created:true,baseline:'e'.repeat(40)}};
    if(route==='autogen/start') {
      const body=request.postDataJSON();const id=runIdFor(body.client_request_id);
      const duplicate=!!run&&run.id===id;run=run&&duplicate?run:treeRun(id,body.client_request_id);
      if (options.gate) await options.gate();
      return options.lost ? {abort:true} : {json:{run:{...run,tasks:undefined,summary:undefined},duplicate}};
    }
    if(route==='autogen/control') {
      const body=request.postDataJSON();
      if(body.action==='cancel') run={...run,cancel_requested:true};
      if(body.action==='resume') run={...run,status:'queued',resume_required:false,error:''};
      return {json:{run}};
    }
    if(route==='tasks/get') return {json:{task:{}}};
    return {status:404,json:{error:'Missing fixture route '+route}};
  };
  return {api,set:v=>{run=v},get:()=>run};
}
async function boot(f=fixture(),options={}) {
  const ctx=await open(browser,'/symblic/#autogen',f.api,{files,...options});
  await ctx.page.waitForSelector('.autogen');return {...ctx,fixture:f};
}
const posts=ctx=>ctx.requests.filter(r=>r.path.startsWith(API)&&r.method==='POST');
const ready=page=>page.waitForFunction(()=>Array.from(document.querySelectorAll('.autogen button')).find(b=>b.textContent==='Start autogen run')?.disabled===false);
async function fillDraft(page) {
  await ready(page);
  await page.getByLabel('Statements',{exact:true}).fill(LINES.join('\n'));
  await page.getByLabel('Machine',{exact:true}).selectOption('node-a');
  await page.getByLabel('Workspace folder',{exact:true}).fill(CWD);
}
async function openTree(page) {
  await page.getByText('Statement tree',{exact:true}).waitFor();
  await page.locator('.ag-node').nth(3).waitFor();
}

test('section renders, limits populate the form, and loading posts nothing',async()=>{
  const c=await boot();try{
    await ready(c.page);
    assert.equal(await c.page.locator('.autogen h2').first().textContent(),'Autogen');
    const cand=c.page.getByLabel('Candidates per statement',{exact:true});
    assert.deepEqual([await cand.getAttribute('min'),await cand.getAttribute('max'),await cand.inputValue()],['1','4','1']);
    const agents=c.page.getByLabel('Agents for the whole run',{exact:true});
    assert.deepEqual([await agents.getAttribute('max'),await agents.inputValue()],['96','24']);
    const minutes=c.page.getByLabel('Minutes per attempt',{exact:true});
    assert.deepEqual([await minutes.getAttribute('min'),await minutes.getAttribute('max'),await minutes.inputValue()],['2','240','60']);
    assert.equal(await c.page.getByLabel('Hours for the whole run',{exact:true}).inputValue(),'6');
    assert.equal(await c.page.getByLabel('Fresh agent',{exact:true}).isChecked(),true);
    assert.equal(await c.page.getByLabel('Another agent type',{exact:true}).isChecked(),true);
    assert.equal(await c.page.getByLabel('A stronger model').count(),0);   // refused by the server; not offered
    const nodes=await c.page.getByLabel('Machine',{exact:true}).locator('option').evaluateAll(o=>o.map(x=>[x.value,x.disabled]));
    assert.deepEqual(nodes,[['',false],['host',false],['node-a',false],['node-c',true]]);
    assert.equal(await c.page.getByLabel('Agent type',{exact:true}).inputValue(),'agy');
    assert.match(await c.page.locator('.autogen').textContent(),/keeping every existing part/);
    assert.equal(posts(c).length,0);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('Start posts once with the policy and a stable id; a second click while pending does not post',async()=>{
  let release,entered;const seen=new Promise(r=>entered=r),wait=new Promise(r=>release=r);
  const f=fixture({gate:async()=>{entered();await wait;}});
  const c=await boot(f);try{
    await fillDraft(c.page);
    await c.page.getByLabel('New workspace name',{exact:true}).fill('fixture');
    await c.page.getByRole('button',{name:'Create workspace',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Workspace created'));
    assert.equal(await c.page.getByLabel('Workspace folder',{exact:true}).inputValue(),CWD);
    await c.page.getByText('Policy: candidates, regeneration, splits and budget',{exact:true}).click();
    await c.page.getByLabel('Candidates per statement',{exact:true}).fill('2');
    await c.page.getByLabel('Split depth',{exact:true}).fill('1');
    await c.page.getByLabel('Minutes per attempt',{exact:true}).fill('30');
    await c.page.getByLabel('Another machine',{exact:true}).uncheck();
    await c.page.getByText('Checks',{exact:true}).click();
    await c.page.getByLabel('Public checks per statement',{exact:true}).fill('1: node --check add.js\n2: test -f verify.txt');
    await c.page.getByLabel('Final commands',{exact:true}).fill('node --test');
    await c.page.getByLabel('Hidden commands',{exact:true}).fill('node hidden.js');
    const start=c.page.getByRole('button',{name:'Start autogen run',exact:true});
    await start.click();await seen;
    assert.equal(await start.isDisabled(),true);
    await c.page.evaluate(()=>{const b=Array.from(document.querySelectorAll('.autogen button')).find(x=>x.textContent==='Start autogen run');b.disabled=false;b.click();b.click();});
    const starts=()=>posts(c).filter(r=>r.path===API+'autogen/start');
    assert.equal(starts().length,1);
    release();
    await openTree(c.page);
    assert.equal(starts().length,1);
    const body=starts()[0].body;
    assert.match(body.client_request_id,/^autogen-ui-[A-Za-z0-9-]+$/);
    assert.equal(body.instruction,LINES.join('\n'));assert.equal(body.engine,'agy');assert.equal(body.node,'node-a');assert.equal(body.cwd,CWD);
    assert.equal(body.headless,true);assert.equal('model' in body,false);
    assert.deepEqual(body.autogen,{candidates:2,regenerate:2,depth:1,children:4,generations:3,agents_max:24,attempt_seconds:1800,wall_seconds:21600,
      interval_seconds:900,feedback_chars:2000,strategies:['fresh','feedback','other_engine'],perpetual:false,syntax:true,require_change:true,
      checks:{'0':['node --check add.js'],'1':['test -f verify.txt']},final:['node --test'],hidden:['node hidden.js'],
      until_done:false,designer:false,self_split:true,novelty_limit:2,saturation:0});
    const id=runIdFor(body.client_request_id);
    assert.deepEqual(await c.page.evaluate(k=>JSON.parse(localStorage.getItem(k)),SAVED),{id,pending:false});
    assert.deepEqual(Object.keys(await c.page.evaluate(()=>({...localStorage}))).filter(k=>k.startsWith('symblic.autogen')),[SAVED]);
    // a recorded start retires the draft id: the next start is a new request
    assert.doesNotMatch(await c.page.locator('.autogen form .ag-mono').last().textContent(),new RegExp(body.client_request_id));
    assert.deepEqual(posts(c).map(r=>r.path.slice(API.length)),['workspace/create','autogen/start']);
    assert.deepEqual(c.errors,[]);
  }finally{release();await c.context.close();}
});

test('a lost start response keeps the request id, observes the derived run and resends the same id',async()=>{
  const f=fixture({lost:true});
  const c=await boot(f);try{
    await fillDraft(c.page);
    await c.page.getByRole('button',{name:'Start autogen run',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Start outcome is unknown'));
    const first=posts(c).filter(r=>r.path===API+'autogen/start')[0].body.client_request_id;
    await openTree(c.page);  // the derived run id is observed with GET only
    assert.equal(posts(c).length,1);
    await ready(c.page);
    await c.page.getByRole('button',{name:'Start autogen run',exact:true}).click();
    for (let i=0;i<100&&posts(c).length<2;i++) await c.page.waitForTimeout(50);
    await ready(c.page);
    const sent=posts(c).filter(r=>r.path===API+'autogen/start').map(r=>r.body.client_request_id);
    assert.deepEqual(sent,[first,first]);
  }finally{await c.context.close();}
});

test('the tree renders depth, attempts, verdict output, handoff and decisions; hidden output is withheld',async()=>{
  const id=runIdFor('fixture-request');
  const c=await boot(fixture({run:treeRun(id)}));
  try{
    await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();
    await openTree(c.page);
    const depths=await c.page.locator('.ag-node').evaluateAll(n=>n.map(x=>[x.dataset.depth,parseFloat(getComputedStyle(x).marginLeft)]));
    assert.deepEqual(depths.map(d=>d[0]),['0','1','1','0']);assert.ok(depths[1][1]>depths[0][1]);
    const text=await c.page.locator('.ag-tree').textContent();
    for (const want of ['n0-a0','CHECK_FAILURE','planner','split','agy@node-a','handoff','continues n0.1-a0','generation 1','winner','No attempts yet.']) assert.ok(text.includes(want),want);
    await c.page.getByText('Verdict · failed · 3 checks',{exact:true}).click();
    assert.match(await c.page.locator('.ag-tree').textContent(),/AssertionError: expected 3 but got <b>"12"<\/b>/);
    assert.equal(await c.page.locator('.ag-tree b').filter({hasText:'"12"'}).count(),0);
    assert.doesNotMatch(await c.page.locator('.autogen').textContent(),/SECRET-HIDDEN-OUTPUT/);
    await c.page.getByText('Validated split · 2 statements',{exact:true}).click();
    await c.page.getByText('Checkpoint',{exact:true}).click();
    assert.match(await c.page.locator('.ag-tree').textContent(),/left: edge cases/);
    await c.page.getByText('Decisions · 2',{exact:true}).click();
    assert.match(await c.page.locator('.ag-tree').textContent(),/decompose · regeneration exhausted/);
    assert.equal(await c.page.getByRole('link',{name:'Agent terminal for n0-a0'}).getAttribute('href'),'/terminal.html?session=agent-n0a0&node=node-a');
    assert.equal(await c.page.getByRole('link',{name:'Agent terminal for n0-a1'}).getAttribute('href'),'/terminal.html?session=agent-n0a1');
    assert.equal(await c.page.getByRole('link',{name:'Task record for n0-a0'}).getAttribute('href'),API+'tasks/get?id='+TASK);
    assert.equal(await c.page.locator('a[href^="javascript"]').count(),0);
    assert.match(await c.page.locator('.ag-budget').textContent(),/Agents started 5 of 24/);
    assert.match(await c.page.locator('.ag-budget').textContent(),/Deadline in 1 h 59 min/);
    assert.equal(await c.page.locator('.ag-bar').getAttribute('aria-valuenow'),'5');
    assert.match(await c.page.locator('.autogen').textContent(),/Final checks run after every statement is accepted: node --test/);
    assert.ok(c.requests.some(r=>r.path===API+'autogen/get'&&r.search.includes('tasks=1')));
    // reload observes the same run with GET only
    await c.page.reload();await openTree(c.page);
    assert.equal(posts(c).length,0);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('Cancel posts control once; Resume posts only when the record requires it',async()=>{
  const id=runIdFor('fixture-request');
  // a retained selection is restored on load and only read
  const c=await boot(fixture({run:{...treeRun(id),resume_required:true}}),{storage:`localStorage.setItem(${JSON.stringify(SAVED)},${JSON.stringify(JSON.stringify({id,pending:false}))})`});
  try{
    await openTree(c.page);
    assert.match(await c.page.locator('.autogen').textContent(),/No coordinator is driving this run/);
    await c.page.getByRole('button',{name:'Resume run',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Resume recorded'));
    await c.page.waitForFunction(()=>Array.from(document.querySelectorAll('.autogen button')).find(b=>b.textContent==='Resume run').disabled);
    await c.page.getByRole('button',{name:'Cancel run',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Cancel recorded'));
    await c.page.waitForFunction(()=>Array.from(document.querySelectorAll('.autogen button')).find(b=>b.textContent==='Cancel run').disabled);
    assert.deepEqual(posts(c).map(r=>[r.path.slice(API.length),r.body]),[['autogen/control',{id,action:'resume'}],['autogen/control',{id,action:'cancel'}]]);
    await c.page.evaluate(()=>window.dispatchEvent(new Event('online')));
    await c.page.getByRole('button',{name:'Refresh run',exact:true}).click();
    assert.equal(posts(c).length,2);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('navigation away stops observation and returning launches nothing',async()=>{
  const id=runIdFor('fixture-request');
  const c=await boot(fixture({run:treeRun(id)}));
  try{
    await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();await openTree(c.page);
    await c.page.evaluate(()=>Studio.go('overview'));await c.page.locator('.autogen').waitFor({state:'detached'});
    const before=c.requests.length;await c.page.waitForTimeout(300);
    assert.equal(c.requests.length,before);
    await c.page.evaluate(()=>Studio.go('autogen'));await openTree(c.page);
    assert.equal(posts(c).length,0);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('phone and desktop dark layout: no overflow, readable inputs, no serious a11y errors',async()=>{
  const id=runIdFor('fixture-request');
  for(const mobile of [false,true]){
    const c=await boot(fixture({run:treeRun(id)}),{mobile,storage:()=>localStorage.setItem('studioTheme','dark')});try{
      await ready(c.page);
      await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();await openTree(c.page);
      await c.page.getByText('Policy: candidates, regeneration, splits and budget',{exact:true}).click();
      await c.page.getByLabel(UNTIL,{exact:true}).check();   // the until-done hints join the policy grid
      await c.page.getByText('Checks',{exact:true}).click();
      await c.page.getByText('Verdict · failed · 3 checks',{exact:true}).click();
      await c.page.getByText('Checkpoint',{exact:true}).click();
      assert.equal(await noHorizontalScroll(c.page),true);
      assert.equal(await c.page.locator('.autogen .field').evaluateAll(n=>n.every(x=>parseFloat(getComputedStyle(x).fontSize)>=16)),true);
      assert.equal(await c.page.locator('.autogen button:visible').evaluateAll(n=>n.every(x=>x.getBoundingClientRect().height>=44)),true);
      assert.deepEqual(await axe(c.page),[]);assert.deepEqual(c.errors,[]);
      await c.page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
      await c.page.screenshot({path:path.join(evidence,mobile?'autogen-phone-dark.png':'autogen-desktop-dark.png'),fullPage:true});
      assert.equal(posts(c).length,0);
    }finally{await c.context.close();}
  }
});

test('until done: v2 policy keys are sent as named; blank or 0 caps mean unlimited only with until done; a typed cap is sent',async()=>{
  const c=await boot();try{
    await fillDraft(c.page);
    await c.page.getByText('Policy: candidates, regeneration, splits and budget',{exact:true}).click();
    const until=c.page.getByLabel(UNTIL,{exact:true}),designer=c.page.getByLabel(DESIGNER,{exact:true}),split=c.page.getByLabel(SELF_SPLIT,{exact:true});
    assert.deepEqual([await until.isChecked(),await designer.isChecked(),await split.isChecked()],[false,false,true]);   // catalogue defaults
    const novelty=c.page.getByLabel(NOVELTY,{exact:true}),saturation=c.page.getByLabel(SATURATION,{exact:true});
    assert.deepEqual([await novelty.getAttribute('min'),await novelty.getAttribute('max'),await novelty.inputValue()],['1','8','2']);
    assert.deepEqual([await saturation.getAttribute('min'),await saturation.getAttribute('max'),await saturation.inputValue()],['0','16','0']);
    assert.equal(await c.page.locator('#ag-hint-saturation').textContent(),'0 = never; perpetual lanes only');
    assert.equal(await c.page.getByLabel('Candidates per statement',{exact:true}).inputValue(),'1');   // one agent per line stays the default
    const agents=c.page.getByLabel('Agents for the whole run',{exact:true}),hours=c.page.getByLabel('Hours for the whole run',{exact:true});
    const start=c.page.getByRole('button',{name:'Start autogen run',exact:true});
    // bounded: 0 is below the catalogue limit, so the browser refuses the form and nothing is sent
    await agents.fill('0');
    assert.equal(await agents.evaluate(i=>i.validity.rangeUnderflow),true);
    await start.click();await c.page.waitForTimeout(200);
    assert.equal(posts(c).length,0);
    await agents.fill('24');
    assert.equal(await c.page.locator('#ag-hint-agents_max').isVisible(),false);
    // until done lifts the count and clock caps: both are blanked, optional, and read "blank or 0 = unlimited"
    await until.check();
    assert.deepEqual([await agents.inputValue(),await agents.getAttribute('min'),await hours.inputValue(),await hours.getAttribute('min')],['','0','','0']);
    assert.deepEqual([await agents.evaluate(i=>i.required),await hours.evaluate(i=>i.required)],[false,false]);
    assert.deepEqual([await c.page.locator('#ag-hint-agents_max').textContent(),await c.page.locator('#ag-hint-wall_seconds').textContent()],
      ['blank or 0 = unlimited','blank or 0 = unlimited']);
    assert.equal(await c.page.locator('#ag-hint-agents_max').isVisible(),true);
    assert.equal(await c.page.locator('#ag-hint-depth').textContent(),'Not a cap until done');
    await agents.fill('0');
    assert.deepEqual([await agents.evaluate(i=>i.validity.valid),await hours.evaluate(i=>i.validity.valid)],[true,true]);
    // switching it off restores the caps, the catalogue minimum and the required flag
    await until.uncheck();
    assert.deepEqual([await agents.inputValue(),await agents.getAttribute('min'),await hours.inputValue(),String(await agents.evaluate(i=>i.required))],['24','1','6','true']);
    assert.equal(await c.page.locator('#ag-hint-agents_max').isVisible(),false);
    await until.check();await designer.check();await split.uncheck();
    await novelty.fill('3');await saturation.fill('4');
    // a typed cap below the catalogue minimum is refused before anything is sent
    await hours.fill('0.05');await start.click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Hours for the whole run must be blank or 0 (unlimited), or a cap of at least 300 seconds.'));
    assert.equal(posts(c).length,0);
    // first run: no agent cap (blank, left out), a 12-hour safety cap on the clock
    await hours.fill('12');
    await start.click();
    await openTree(c.page);
    const starts=()=>posts(c).filter(r=>r.path===API+'autogen/start');
    assert.equal(starts().length,1);
    const {agents_max:_a,wall_seconds:_w,...rest}=DEFAULTS;
    assert.deepEqual(starts()[0].body.autogen,{...rest,wall_seconds:43200,until_done:true,designer:true,self_split:false,novelty_limit:3,saturation:4});
    assert.equal('agents_max' in starts()[0].body.autogen,false);
    // second run (a recorded start renewed the request id): an explicit 0 is sent as 0, a blank clock is left out
    await ready(c.page);
    await agents.fill('0');await hours.fill('');
    await start.click();
    for (let i=0;i<100&&starts().length<2;i++) await c.page.waitForTimeout(50);
    assert.equal(starts().length,2);
    assert.notEqual(starts()[1].body.client_request_id,starts()[0].body.client_request_id);
    assert.deepEqual(starts()[1].body.autogen,{...rest,agents_max:0,until_done:true,designer:true,self_split:false,novelty_limit:3,saturation:4});
    await ready(c.page);
    assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('a stuck until-done run: own chip, resume hint, unlimited budget, no deadline, progress, v2 attempts; not polled until resumed',async()=>{
  const id=runIdFor('stuck-request');
  const c=await boot(fixture({run:stuckRun(id)}),{mobile:true,storage:()=>localStorage.setItem('studioTheme','dark')});
  try{
    await ready(c.page);
    const row=c.page.locator('.ag-run-row');await row.first().waitFor();
    assert.deepEqual([await row.locator('.ag-chip').textContent(),await row.locator('.ag-s-stuck').count()],['stuck',1]);
    assert.match(await row.textContent(),/2 statements · agents 5\/unlimited · until done · /);
    await c.page.clock.install();   // the poll timer is created after this, so fake time decides whether it fires
    await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();
    await openTree(c.page);
    // its own chip: a hollow warning marker (every other status has a filled dot), in the list, the run head and the stuck node
    assert.equal(await c.page.locator('.autogen .ag-s-stuck').count(),3);
    assert.equal(await c.page.locator('.ag-tree .ag-s-stuck').count(),1);
    const marker=n=>{const s=getComputedStyle(n,'::before');return [s.backgroundColor,s.borderTopWidth,s.borderTopStyle];};
    assert.deepEqual(await c.page.locator('.ag-tree .ag-s-stuck').evaluate(marker),['rgba(0, 0, 0, 0)','2px','solid']);
    assert.notEqual((await c.page.locator('.ag-tree .ag-s-failed').first().evaluate(marker))[0],'rgba(0, 0, 0, 0)');
    // the hint sits right under the actions row that holds Resume, and describes the Resume button
    const hint=c.page.locator('#ag-stuck-hint'),resume=c.page.getByRole('button',{name:'Resume run',exact:true});
    assert.deepEqual([await hint.isVisible(),await hint.textContent()],[true,STUCK_HINT]);
    assert.equal(await hint.evaluate(n=>[...n.previousElementSibling.querySelectorAll('button')].some(b=>b.textContent==='Resume run')),true);
    assert.deepEqual([await resume.isEnabled(),await resume.getAttribute('aria-describedby')],[true,'ag-stuck-hint']);
    assert.equal(await c.page.getByRole('button',{name:'Cancel run',exact:true}).isEnabled(),true);   // the server still cancels a stuck run
    const budget=await c.page.locator('.ag-budget').textContent();
    assert.match(budget,/Agents started 5 of unlimited/);assert.match(budget,/No deadline: no clock ends this run/);
    assert.equal(await c.page.locator('.ag-bar').count(),0);
    const text=await c.page.locator('.ag-tree').textContent();
    for (const want of ['test designer · writes AUTOGEN-TESTS.sh · agy@node-a','design done','planner · self-split · agy@node-a',
      'Progress: 1 file (add.js), 2 checks passed','Progress: 1 file (add.test.js), 1 check passed, 1 checkpoint item done · 2 of 2 attempts without progress'])
      assert.ok(text.includes(want),want);
    assert.equal(text.includes('items indexed'),false);
    assert.match(await c.page.locator('.autogen').textContent(),/Statement n0\.1 is stuck: no eligible strategy remains/);
    await c.page.getByText('Validated split · 2 statements',{exact:true}).click();
    // designed tests show the sandbox they ran in as a small tag; other checks have none
    await c.page.locator('details[data-key="n0/n0-a0/verdict"] > summary').click();
    await c.page.locator('details[data-key="n0.1/n0.1-a0/verdict"] > summary').click();
    assert.deepEqual(await c.page.locator('.ag-tree .ag-tag').evaluateAll(n=>n.map(x=>[x.textContent,x.closest('.ag-check-row').textContent.split(' ')[1]])),
      [['landlock','design'],['landlock','designed']]);
    assert.equal(await c.page.locator('.ag-tree .ag-check-row').filter({hasText:'node --test'}).locator('.ag-tag').count(),0);
    assert.equal(await noHorizontalScroll(c.page),true);
    assert.deepEqual(await axe(c.page),[]);
    await c.page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
    await c.page.screenshot({path:path.join(evidence,'autogen-stuck-phone-dark.png'),fullPage:true});
    // nothing changes a stuck run until the owner acts, so it is not polled
    const gets=()=>c.requests.filter(r=>r.path===API+'autogen/get').length,seen=gets();
    await c.page.clock.runFor(25000);await c.page.waitForTimeout(300);
    assert.equal(gets(),seen);
    await resume.click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Stuck statements reopen with their stall count cleared'));
    assert.deepEqual(posts(c).map(r=>[r.path.slice(API.length),r.body]),[['autogen/control',{id,action:'resume'}]]);
    await c.page.waitForFunction(()=>document.getElementById('ag-stuck-hint').hidden);
    await c.page.waitForFunction(()=>Array.from(document.querySelectorAll('.autogen button')).find(b=>b.textContent==='Resume run').disabled);
    assert.equal(await resume.getAttribute('aria-describedby'),null);
    // the resumed run is queued again and observed on the poll interval
    for (let i=0;i<50&&gets()<=seen;i++) await c.page.waitForTimeout(50);
    const after=gets();
    for (let i=0;i<20&&gets()<=after;i++) {await c.page.clock.runFor(11000);await c.page.waitForTimeout(100);}
    assert.ok(gets()>after,'a resumed run is polled');
    assert.equal(posts(c).length,1);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('cancelling a stuck run hides the hint, disables Resume and observes the run until it ends',async()=>{
  const id=runIdFor('stuck-request'),f=fixture({run:stuckRun(id)});
  const c=await boot(f,{storage:`localStorage.setItem(${JSON.stringify(SAVED)},${JSON.stringify(JSON.stringify({id,pending:false}))})`});
  try{
    await openTree(c.page);
    await c.page.clock.install();
    assert.equal(await c.page.locator('#ag-stuck-hint').isVisible(),true);
    await c.page.getByRole('button',{name:'Cancel run',exact:true}).click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.includes('Cancel recorded'));
    await c.page.waitForFunction(()=>document.getElementById('ag-stuck-hint').hidden);
    await c.page.waitForFunction(()=>Array.from(document.querySelectorAll('.autogen button')).find(b=>b.textContent==='Cancel run').disabled);
    assert.equal(await c.page.getByRole('button',{name:'Resume run',exact:true}).isDisabled(),true);
    assert.match(await c.page.locator('.autogen').textContent(),/cancel requested/);
    assert.deepEqual(posts(c).map(r=>[r.path.slice(API.length),r.body]),[['autogen/control',{id,action:'cancel'}]]);
    // the pending cancel is observed on the poll interval until the record ends
    const gets=()=>c.requests.filter(r=>r.path===API+'autogen/get').length;
    for (let i=0;i<50&&gets()<2;i++) await c.page.waitForTimeout(50);   // the read that follows the control request
    const after=gets();
    for (let i=0;i<20&&gets()<=after;i++) {await c.page.clock.runFor(11000);await c.page.waitForTimeout(100);}
    assert.ok(gets()>after,'a stuck run with a pending cancel is polled');
    f.set({...f.get(),status:'cancelled'});
    for (let i=0;i<20&&!(await c.page.locator('.ag-budget').textContent()).includes('Run ended');i++) {await c.page.clock.runFor(11000);await c.page.waitForTimeout(100);}
    assert.match(await c.page.locator('.ag-budget').textContent(),/Run ended · it had no deadline/);
    const ended=gets();
    await c.page.clock.runFor(25000);await c.page.waitForTimeout(300);
    assert.equal(gets(),ended);
    assert.equal(posts(c).length,1);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('a perpetual lane shows its indexed items; a capped budget keeps its bar',async()=>{
  const id=runIdFor('perpetual-request');
  const c=await boot(fixture({run:perpetualRun(id)}));
  try{
    await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();
    await c.page.locator('.ag-node').first().waitFor();
    const text=await c.page.locator('.ag-tree').textContent();
    for (const want of ['perpetual','7 items indexed','generation done']) assert.ok(text.includes(want),want);
    assert.equal(text.includes('without progress'),false);
    assert.match(await c.page.locator('.ag-budget').textContent(),/Agents started 4 of 24/);
    assert.equal(await c.page.locator('.ag-bar').getAttribute('aria-valuemax'),'24');
    assert.match(await c.page.locator('.ag-budget').textContent(),/Deadline in /);
    assert.equal(posts(c).length,0);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

test('an older catalogue without the v2 fields hides them, explains why, and sends only the bounded policy',async()=>{
  const c=await boot(fixture({override:route=>route==='autogen/catalog'?{json:CATALOG_V1}:null}));
  try{
    await fillDraft(c.page);
    await c.page.getByText('Policy: candidates, regeneration, splits and budget',{exact:true}).click();
    const parts=await c.page.evaluate(labels=>labels.map(label=>{
      const input=Array.from(document.querySelectorAll('.autogen input')).find(i=>i.getAttribute('aria-label')===label||i.closest('label')?.textContent===label);
      return input?[input.closest('label').hidden,input.disabled]:null;
    }),[UNTIL,DESIGNER,SELF_SPLIT,NOVELTY,SATURATION]);
    assert.deepEqual(parts,[[true,true],[true,true],[true,true],[true,true],[true,true]]);
    assert.match(await c.page.locator('.autogen').textContent(),/no Until done, test designer or self-split fields yet \(the host update needs a restart\)/);
    assert.equal(await c.page.getByLabel('Agents for the whole run',{exact:true}).getAttribute('min'),'1');
    await c.page.getByRole('button',{name:'Start autogen run',exact:true}).click();
    await openTree(c.page);
    const starts=posts(c).filter(r=>r.path===API+'autogen/start');
    assert.equal(starts.length,1);
    assert.deepEqual(starts[0].body.autogen,DEFAULTS_V1);   // an older server refuses unknown fields
    assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

const SPENT = 'The agents_max cap you gave this run is spent; resume with extend {"agents_max": N} (0 lifts it under until_done) or start a new run with a higher cap.';
test('resuming a stuck run whose cap is spent: the 409 is shown verbatim, extend raises the caps, 0 needs until done',async()=>{
  const id=runIdFor('stuck-request'),base=stuckRun(id);
  const spent={...base,policy:{...base.policy,agents_max:24},budget:{agents_started:24,agents_max:24,deadline:null}};
  const f=fixture({run:spent,override:async(route,request)=>{
    // the server refuses a plain resume while the explicit cap is spent; any extend is accepted by the default handler
    if(route==='autogen/control'&&request.postDataJSON().action==='resume'&&!request.postDataJSON().extend)return {status:409,json:{error:SPENT}};
    return null;
  }});
  const c=await boot(f);try{
    await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();await openTree(c.page);
    const agents=c.page.getByLabel('agents',{exact:true}),hours=c.page.getByLabel('hours',{exact:true});
    const resume=c.page.getByRole('button',{name:'Resume run',exact:true}),controls=()=>posts(c).filter(r=>r.path===API+'autogen/control').map(r=>r.body);
    const idle=()=>c.page.waitForFunction(()=>!Array.from(document.querySelectorAll('.autogen button')).find(b=>b.textContent==='Resume run').disabled);
    assert.deepEqual([await agents.isVisible(),await hours.isVisible(),await agents.inputValue(),await hours.inputValue()],[true,true,'','']);
    assert.deepEqual([await agents.getAttribute('min'),await agents.getAttribute('max'),await hours.getAttribute('min'),await hours.getAttribute('max')],['0','96','0','48']);
    assert.match(await c.page.locator('.ag-extend').textContent(),/Raise a spent cap with Resume \(optional\).*0 lifts it \(unlimited\)/);
    // blank inputs send no extend; the refusal is the server's message, verbatim, as an error
    await resume.click();
    await c.page.waitForFunction(m=>document.querySelector('.ag-message').textContent===m,SPENT);
    assert.equal(await c.page.locator('.ag-message').evaluate(n=>n.classList.contains('ag-error')),true);
    assert.deepEqual(controls(),[{id,action:'resume'}]);
    await idle();
    // a typed clock cap under the catalogue minimum is refused here; nothing is sent
    await hours.fill('0.05');await resume.click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent==='hours must be blank, 0 (unlimited) or a cap of at least 300 seconds.');
    assert.equal(controls().length,1);
    // 0 lifts the agent cap on an until-done run; hours become whole seconds from the resume
    await agents.fill('0');await hours.fill('2.5');await resume.click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.startsWith('Resume recorded.'));
    assert.deepEqual(controls(),[{id,action:'resume'},{id,action:'resume',extend:{agents_max:0,wall_seconds:9000}}]);
    await c.page.waitForFunction(()=>document.querySelector('.ag-extend').hidden);
    assert.deepEqual([await agents.inputValue(),await hours.inputValue()],['','']);
    // a run without until done offers no 0: the browser refuses it before anything is sent
    f.set({...spent,policy:{...spent.policy,until_done:false}});
    await c.page.getByRole('button',{name:'Refresh run',exact:true}).click();
    await c.page.waitForFunction(()=>!document.querySelector('.ag-extend').hidden);
    assert.equal(await agents.getAttribute('min'),'1');
    assert.doesNotMatch(await c.page.locator('.ag-extend').textContent(),/unlimited/);
    await agents.fill('0');await resume.click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.startsWith('Fix agents before resuming: '));
    assert.equal(controls().length,2);
    // a wider cap is sent as typed
    await agents.fill('48');await hours.fill('');await resume.click();
    await c.page.waitForFunction(()=>document.querySelector('.ag-message').textContent.startsWith('Resume recorded.'));
    assert.deepEqual(controls()[2],{id,action:'resume',extend:{agents_max:48}});
    assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

function integrationRun(id, requestId='integration-request') {
  const now=Date.now()/1000, base=treeRun(id,requestId);
  const first='Create the file add.js in the folder '+CWD+' with add(a, b).', second='Write the file add.test.js in the folder '+CWD+' testing add.';
  const accepted=(nid,index,statement)=>({id:nid,index,parent:'n0',depth:1,statement,status:'accepted',children:[],generation:0,perpetual:false,winner:nid+'-a0',
    stale:0,handoff_stale:0,integrations:0,progress:{},items_total:0,decisions:[],attempts:[]});
  return {...base,status:'active',tasks:{},policy:{...DEFAULTS,until_done:true,final:['node --test']},budget:{agents_started:7,agents_max:0,deadline:null},
    nodes:[
      {id:'n0',index:0,parent:null,depth:0,statement:LINES[0],status:'pending',children:['n0.0','n0.1'],generation:0,perpetual:false,winner:'',
        stale:0,handoff_stale:0,integrations:1,progress:{},items_total:0,decisions:[],attempts:[
          {id:'n0-a0',kind:'planner',strategy:'split',engine:'agy',node:'node-a',model:'',generation:0,task_id:'',status:'split_done',failure:null,
            started:now-500,finished:now-450,split:[first,second],verdict:{passed:true,files_changed:null,report:'',checks:[{kind:'split',passed:true,public:true,output:'2 lines'}]}},
          {id:'n0-i1',kind:'integration',strategy:'integration',engine:null,node:null,model:'',generation:0,request_id:'',task_id:'',status:'failed',
            failure:'CHECK_FAILURE',started:now-60,finished:now-60,error:'children accepted, parent checks failed: command node --test failed',
            verdict:{passed:false,files_changed:null,report:'command node --test failed',scope:'parent_after_children',
              checks:[{kind:'command',command:'node --test',passed:false,public:true,output:'1 failing'}]}}]},
      accepted('n0.0',0,first),accepted('n0.1',1,second),
      {id:'n1',index:1,parent:null,depth:0,statement:LINES[1],status:'pending',children:[],generation:2,perpetual:false,winner:'',
        stale:2,handoff_stale:2,integrations:0,progress:{},items_total:0,decisions:[],attempts:[
          {id:'n1-a0',kind:'candidate',strategy:'fresh',engine:'agy',node:'node-a',model:'',generation:0,task_id:'',status:'handoff',failure:null,started:now-300,finished:now-200,
            checkpoint:{valid:true,done:[],left:['verify'],files:[]},progress:{files:[],checks:0,done:0,new:false}},
          {id:'n1-a1',kind:'handoff',strategy:'handoff',engine:'agy',node:'node-a',model:'',generation:1,from:'n1-a0',task_id:'',status:'handoff',failure:null,started:now-190,finished:now-100,
            checkpoint:{valid:true,done:[],left:['verify'],files:[]},progress:{files:[],checks:0,done:0,new:false}}]}]};
}
test('a reopened split parent and stalled handoffs: node tags, the integration check and the split history',async()=>{
  const id=runIdFor('integration-request');
  const c=await boot(fixture({run:integrationRun(id)}),{mobile:true,storage:()=>localStorage.setItem('studioTheme','dark')});
  try{
    await c.page.getByRole('button',{name:'Open run '+id,exact:true}).click();await openTree(c.page);
    const tags=await c.page.locator('.ag-node > .ag-row-head').evaluateAll(n=>n.map(h=>Array.from(h.querySelectorAll('.ag-tag'),t=>t.textContent)));
    assert.deepEqual(tags,[['reopened 1× after integration'],[],[],['2 handoffs without progress']]);   // shown only when nonzero
    const integration=c.page.locator('.ag-attempt').filter({hasText:'n0-i1'});
    assert.equal(await integration.locator('.ag-chip').textContent(),'failed');
    assert.equal(await integration.locator('.ag-s-failed').count(),1);
    const meta=await integration.locator('p.ag-meta').first().textContent();
    assert.ok(meta.startsWith('integration check · started '),meta);    // no "integration" strategy echo, no ?@? placement
    assert.match(await integration.textContent(),/children accepted, parent checks failed/);
    const planner=c.page.locator('.ag-attempt').filter({hasText:'n0-a0'});
    assert.equal(await planner.locator('.ag-chip').textContent(),'split (history)');
    assert.equal(await planner.locator('.ag-s-split_done').count(),1);
    assert.equal(await noHorizontalScroll(c.page),true);
    assert.deepEqual(await axe(c.page),[]);
    assert.equal(posts(c).length,0);assert.deepEqual(c.errors,[]);
  }finally{await c.context.close();}
});

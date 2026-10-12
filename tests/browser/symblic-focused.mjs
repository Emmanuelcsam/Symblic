// All APIs and WebSockets are inert; these journeys exercise the actual shared controls.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';
let browser;
before(async()=>{browser=await launch();});after(async()=>{await browser?.close();});
const source='Remember value is 7.\nAsk for answer as a whole number: "Read value.".\nUsing only value.\nShow answer.';
const engines=['ollama','codex','claude','chatgpt','gemini','council','triad','squad'];
const catalogue={home:'/projects/demo',specs:{local:{title:'Ollama'},codex:{title:'Codex'},claude:{title:'Claude'},gpt:{title:'ChatGPT'},gemini:{title:'Gemini'},council:{},triad:{},squad:{}},
 models:{local:[{id:'qwen:4b'}],codex:[{id:'codex-model'}]},nodes:[{id:'host',local:true,online:true},{id:'node-i',online:true,probed:true,models:['qwen:4b']}],
 machines:{local:'host',engines:['local','codex','claude','gpt','gemini']},seats:{},
 team_capabilities:{version:1,project_team:true,max_members:24,engines:Object.fromEntries(engines.map(engine=>[engine,{checked:!['triad','squad','council'].includes(engine),project:true,project_team:!['triad','squad','council'].includes(engine),project_efforts:['','high'],project_settings:[],efforts:['','high'],settings:engine==='ollama'?['temperature','seed']:[],typedNodes:engine==='ollama'?['host','node-i']:['host']}]))}};
const team={version:1,members:['ollama','codex','claude','chatgpt','gemini'].map((engine,index)=>({id:'seat-'+index,engine,model:index?'':'qwen:4b',node:index?'host':'node-i',role:['planner','builder','critic','researcher','tester'][index],characteristics:'Exact perspective '+index,instruction:'Verify step '+index,effort:'',settings:index?{}:{temperature:0.2,seed:7},weight:1}))};
function fixture(overrides={}) {return async(request,url)=>{
 if(overrides[url.pathname])return overrides[url.pathname](request,url);
 if(url.pathname==='/api/symblicos/catalog')return{json:catalogue};
 if(url.pathname==='/api/symblicos/tasks')return{json:{tasks:[]}};
 if(url.pathname.endsWith('/english/examples'))return{json:{examples:{},capabilities:{team:{version:1,max_members:24}}}};
 if(url.pathname.endsWith('/meta'))return{json:{features:{english_team:{version:1,max_members:24}},examples:[]}};
 if(url.pathname.endsWith('/editor/check')) {const body=request.postDataJSON();return{json:{version:1,language:body.language,source_length_utf16:body.source.length,available:true,ok:true,diagnostics:[],check:{ok:true}}};}
 if(url.pathname.endsWith('/english/check'))return{json:{ok:true,statements:[],source:'checked-native'}};
 if(url.pathname.endsWith('/english/preview'))return{json:{ok:true,compiled:{ok:true,statements:[]},preview:{next:{prompt:'exact-profiled-task'}}}};
 if(url.pathname.endsWith('/runs'))return{json:{runs:[]}};
 if(url.pathname.endsWith('/programs'))return{json:{programs:[]}};
 if(url.pathname.endsWith('/paper/map'))return{json:null};
 return{json:{}};
};}
async function boot({mobile=false,saved={source,team,teamEnabled:true},url='/automation-studio/symblic.html',overrides={},direct}={}) {
 const s=await open(browser,url,fixture(overrides),{mobile,storage:`window.WebSocket=class {close(){}};if(!sessionStorage.getItem('symblic-english-v1'))sessionStorage.setItem('symblic-english-v1',${JSON.stringify(JSON.stringify(saved))});${direct?`if(!sessionStorage.getItem('symblic-task-composer-v1'))sessionStorage.setItem('symblic-task-composer-v1',${JSON.stringify(JSON.stringify(direct))});`:''}`});
 await s.page.locator('#sy-en-source').waitFor();await s.page.waitForFunction(()=>document.querySelector('[data-en-catalog-status]')?.textContent.includes('Choose every'));
 await s.page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');return s;
}
const teamPanel=p=>p.locator('[data-en-panel=team]');
const posts=s=>s.requests.filter(r=>r.method==='POST'&&(r.path.includes('/english/')||r.path.endsWith('/tasks/start')));
for(const mobile of [false,true])test(`focused default is one editor with primary action before advanced (${mobile?'phone dark':'desktop'})`,async()=>{
 const s=await boot({mobile});try{
  assert.equal(new URL(s.page.url()).hash,'#english');assert.equal(await s.page.locator('#sy-en-source').count(),1);assert.equal(await s.page.locator('.st-command').count(),0);
  assert.equal(await teamPanel(s.page).evaluate(e=>e.open),false);
  assert.match(await teamPanel(s.page).locator('summary').first().textContent(),/5 members/);
  assert.equal(await s.page.locator('[data-en-panel=limits]').evaluate(e=>e.open),false);
  const action=await s.page.locator('#sy-en-run').boundingBox(),advanced=await s.page.locator('[data-en-panel=examples]').boundingBox();assert.ok(action.y<advanced.y);
  if(!mobile)assert.ok(action.y+action.height<900);
  assert.equal(await noHorizontalScroll(s.page),true);assert.deepEqual(await axe(s.page),[]);assert.deepEqual(posts(s),[]);assert.deepEqual(s.errors,[]);
  if(process.env.SYMBLIC_UI_SHOTS){await mkdir(process.env.SYMBLIC_UI_SHOTS,{recursive:true});await s.page.screenshot({path:process.env.SYMBLIC_UI_SHOTS+'/'+(mobile?'english-phone-dark':'english-desktop')+'.png'});}
 }finally{await s.context.close();}
});
test('five mixed configured members apply to the same checked source and survive reorder/reload',async()=>{
 const s=await boot();try{
  await teamPanel(s.page).locator('summary').first().click();
  await s.page.locator('.symblic-team-member').nth(4).locator('summary').first().click();
  await s.page.getByRole('button',{name:'Move agent 5 up',exact:true}).click();
  await s.page.getByLabel('Agent 4 instructions',{exact:true}).fill('Inspect exactly <script>literal</script>');
  await s.page.locator('#sy-en-check').click();await s.page.getByText('How these statements will run',{exact:true}).waitFor();
  const expected=structuredClone(team);[expected.members[3],expected.members[4]]=[expected.members[4],expected.members[3]];expected.members[3].instruction='Inspect exactly <script>literal</script>';
  assert.deepEqual(posts(s)[0].body.team,expected);assert.equal(posts(s)[0].body.source,source);
  await s.page.reload();await s.page.locator('#sy-en-source').waitFor();assert.equal(await s.page.locator('#sy-en-source').inputValue(),source);
  await s.page.locator('#sy-en-preview').click();await s.page.getByText('Exact next model request',{exact:true}).waitFor();
  assert.deepEqual(posts(s)[1].body.team,expected);assert.equal(await s.page.locator('script').filter({hasText:'literal'}).count(),0);assert.deepEqual(s.errors,[]);
 }finally{await s.context.close();}
});
test('team count, duplicate, remove and sampling changes are explicit and never dispatch',async()=>{
 const s=await boot();try{
  await teamPanel(s.page).locator('summary').first().click();await s.page.getByLabel('Number of agents',{exact:true}).fill('6');await s.page.getByRole('button',{name:'Set size',exact:true}).click();
  assert.equal(await s.page.locator('.symblic-team-member').count(),6);
  await s.page.locator('.symblic-team-member').first().locator('summary').first().click();
  await s.page.getByRole('button',{name:'Duplicate agent 1',exact:true}).click();assert.equal(await s.page.locator('.symblic-team-member').count(),7);
  await s.page.getByRole('button',{name:'Remove agent 2',exact:true}).click();assert.equal(await s.page.locator('.symblic-team-member').count(),6);
  await s.page.locator('.symblic-team-member').first().locator('.symblic-team-advanced > summary').click();await s.page.getByLabel('Agent 1 temperature',{exact:true}).fill('0.8');
  const saved=await s.page.evaluate(()=>JSON.parse(sessionStorage.getItem('symblic-english-v1')));assert.equal(saved.team.members[0].settings.temperature,0.8);assert.equal(new Set(saved.team.members.map(m=>m.id)).size,6);assert.deepEqual(posts(s),[]);
 }finally{await s.context.close();}
});
test('unavailable API team capability refuses without falling back to the single worker',async()=>{
 const s=await boot({overrides:{'/api/automation/symblic/english/examples':()=>({json:{examples:{}}})}});try{
  await s.page.locator('#sy-en-run').click();await s.page.getByRole('alert').filter({hasText:'does not yet support configured teams'}).waitFor();assert.deepEqual(posts(s),[]);
  assert.equal(await s.page.locator('#sy-en-source').inputValue(),source);
 }finally{await s.context.close();}
});
test('agent workflow sends the shared editor exactly and retries the original uncertain submission',async()=>{
 let calls=0;const s=await boot({saved:{source,execution:'agent',teamEnabled:false},direct:{draft:{node:'host',engine:'codex',cwd:'/projects/demo',instruction:'STALE HIDDEN DRAFT'}},overrides:{'/api/symblicos/tasks/start':()=>++calls===1?{abort:true}:{json:{duplicate:true,task:{id:'task-existing',instruction:source,status:'completed',steps:[]}}}}});try{
  assert.equal(await s.page.locator('.st-command').count(),0);await s.page.getByRole('button',{name:'Run instruction',exact:true}).click();
  await s.page.getByRole('button',{name:'Reconnect this submission',exact:true}).waitFor();assert.equal(posts(s)[0].body.instruction,source);
  assert.equal(await s.page.locator('#sy-en-source').isDisabled(),true);await s.page.reload();await s.page.getByRole('button',{name:'Reconnect this submission',exact:true}).click();
  await s.page.getByText('Reconnected to the existing task.',{exact:true}).waitFor();assert.deepEqual(posts(s)[0].body,posts(s)[1].body);
  assert.equal(await s.page.locator('#sy-en-source').inputValue(),source);assert.deepEqual(s.errors,[]);
 }finally{await s.context.close();}
});
test('all tools remain searchable and native deep link keeps advanced controls accessible',async()=>{
 const s=await boot();try{
  await s.page.getByRole('button',{name:'All Symblic tools',exact:true}).click();const count=await s.page.locator('#menuBody .mi').count();assert.equal(count,19);
  await s.page.locator('#syToolSearch').fill('workcard');assert.equal(await s.page.locator('#menuBody .mi:visible').count(),1);await s.page.locator('#syToolSearch').fill('');assert.equal(await s.page.locator('#menuBody .mi:visible').count(),count);
  await s.page.keyboard.press('Escape');await s.page.locator('.sy-quick-nav a[href="#write"]').click();await s.page.locator('#sySrc').waitFor();
  assert.equal(await s.page.locator('.sy-native-settings').evaluate(e=>e.open),false);assert.equal(await s.page.locator('#syRun').isVisible(),true);
  await s.page.locator('.sy-native-settings > summary').click();assert.equal(await s.page.locator('#syPick').isVisible(),true);assert.deepEqual(s.errors,[]);
 }finally{await s.context.close();}
});

test('project team uses the same instruction and exact five seats without legacy overrides',async()=>{
 const projectTeam=structuredClone(team);projectTeam.members.forEach(member=>{member.settings={};});
 const exact='Create a retro game.\nThen inspect its tests.';
 const s=await boot({saved:{source:exact,execution:'agent',team:projectTeam,teamEnabled:true},direct:{draft:{node:'OTHER',engine:'triad',cwd:'/projects/game',mode:'qwen',model:'OLD'}},
  overrides:{'/api/symblicos/tasks/start':()=>({json:{task:{id:'configured-team',status:'running',steps:[]}}})}});try{
  assert.equal(await s.page.getByLabel('Mode',{exact:true}).isVisible(),false);
  await s.page.getByLabel('New team for each line',{exact:true}).check();await s.page.locator('#sy-en-source').focus();await s.page.keyboard.press('Control+Enter');
  await s.page.getByText('Task saved. Follow its progress below.',{exact:true}).waitFor();
  const payload=posts(s)[0].body;assert.equal(payload.mode,'team');assert.equal(payload.instruction,exact);assert.deepEqual(payload.team,projectTeam);assert.equal(payload.fresh_lines,true);
  assert.equal(payload.cwd,'/projects/game');for(const old of ['engine','node','model','roles'])assert.equal(old in payload,false);
  assert.match(await s.page.locator('.st-composer').innerText(),/different machines keep separate checkouts/);assert.deepEqual(s.errors,[]);
 }finally{await s.context.close();}
});
test('project settings that the native CLI cannot honor refuse and preserve the configured draft',async()=>{
 const s=await boot({saved:{source,execution:'agent',team,teamEnabled:true}});try{
  await s.page.getByRole('button',{name:'Run team',exact:true}).click();await s.page.getByRole('alert').filter({hasText:/sampling|temperature|seed/i}).waitFor();assert.deepEqual(posts(s),[]);
  assert.deepEqual(await s.page.evaluate(()=>JSON.parse(sessionStorage.getItem('symblic-english-v1')).team),team);
 }finally{await s.context.close();}
});
test('switching workflows retains one exact editor and checks only the checked workflow',async()=>{
 const s=await boot({saved:{source,teamEnabled:false}});try{
  await s.page.locator('#sy-en-execution').selectOption('agent');await s.page.locator('#sy-en-source').fill('Create files freely. Keep this exact string.');
  const before=s.requests.filter(row=>row.path.endsWith('/editor/check')).length;await s.page.waitForTimeout(650);
  assert.equal(s.requests.filter(row=>row.path.endsWith('/editor/check')).length,before);
  await s.page.locator('#sy-en-execution').selectOption('checked');assert.equal(await s.page.locator('#sy-en-source').inputValue(),'Create files freely. Keep this exact string.');
  assert.equal(await s.page.locator('#sy-en-source').count(),1);assert.equal(await s.page.locator('.st-command').count(),0);assert.deepEqual(posts(s),[]);
 }finally{await s.context.close();}
});
for(const mobile of [false,true])test(`expanded team controls remain usable and accessible (${mobile?'phone dark':'desktop'})`,async()=>{
 const s=await boot({mobile});try{
  await teamPanel(s.page).locator('summary').first().click();await s.page.locator('.symblic-team-member').first().locator('summary').first().click();
  await s.page.locator('.symblic-team-member').first().locator('.symblic-team-advanced > summary').click();
  await s.page.getByLabel('Agent 1 role',{exact:true}).fill('Design and inspect');await s.page.getByLabel('Agent 1 characteristics',{exact:true}).fill('Preserve the original objective and verify real outputs.');
  assert.equal(await noHorizontalScroll(s.page),true);assert.deepEqual(await axe(s.page),[]);
  for(const control of ['Agent 1 engine','Agent 1 device','Agent 1 model','Agent 1 characteristics','Agent 1 temperature'])assert.ok(await s.page.getByLabel(control,{exact:true}).evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=16));
  assert.deepEqual(posts(s),[]);assert.deepEqual(s.errors,[]);
  if(process.env.SYMBLIC_UI_SHOTS){await s.page.locator('.symblic-team-member').first().screenshot({path:process.env.SYMBLIC_UI_SHOTS+'/'+(mobile?'team-phone-dark':'team-desktop')+'.png'});}
 }finally{await s.context.close();}
});

test('an uncertain shared-editor submission stays exact when recovered in Terminal',async()=>{
 let calls=0;const s=await boot({saved:{source,execution:'agent',teamEnabled:false},direct:{draft:{node:'host',engine:'codex',cwd:'/projects/demo',instruction:'OLDER TERMINAL DRAFT'}},
  overrides:{'/api/symblicos/tasks/start':()=>++calls===1?{abort:true}:{json:{duplicate:true,task:{id:'same-task',instruction:source,status:'completed',steps:[]}}}}});try{
  await s.page.getByRole('button',{name:'Run instruction',exact:true}).click();await s.page.getByRole('button',{name:'Reconnect this submission',exact:true}).waitFor();
  assert.equal(await s.page.evaluate(()=>JSON.parse(sessionStorage.getItem('symblic-task-composer-v1')).draft.instruction),source);
  await s.page.goto('https://dashboard.test/symblic-terminal.html');await s.page.getByRole('button',{name:'Reconnect this submission',exact:true}).waitFor();
  assert.equal(await s.page.getByLabel('Your instruction',{exact:true}).inputValue(),source);assert.equal(posts(s).length,1);
  await s.page.getByRole('button',{name:'Reconnect this submission',exact:true}).click();await s.page.getByText('Reconnected to the existing task.',{exact:true}).waitFor();
  assert.deepEqual(posts(s)[1].body,posts(s)[0].body);assert.deepEqual(s.errors,[]);
 }finally{await s.context.close();}
});

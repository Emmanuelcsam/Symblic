// Versioned evidence rendering with intercepted APIs; no live workers or models.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });
const ID = '0000000000dd';
const unsafe = '<img src=x onerror=alert(1)>';
function evidence() {
  return {
    determinism_summary:{version:1,determined:1,underdetermined:1,contradictory:1,unassessed:2},
    determinacy:{version:1,summary:{determined:1,underdetermined:1,contradictory:1,unassessed:2},asks:[
      {line:2,name:unsafe,status:'determined',domain:{size:3},method:'enumeration',passing:['2'],passing_count:1,answered_by:'kernel',solve_mode:'auto'},
      {line:4,index:2,name:'several',status:'underdetermined',domain:{size:50},method:'enumeration',passing:['3','4'],passing_count:null,passing_truncated:true,answered_by:'model',solve_mode:'off'},
      {line:6,name:'impossible',status:'contradictory',domain:{size:2},method:'enumeration',passing:[],passing_count:0,answered_by:null,solve_mode:'off'},
      {line:8,name:'open',status:'unassessed',reason:'no_finite_domain',answered_by:null,solve_mode:'off'},
      {line:9,name:'constructed',status:'unassessed',reason:'author_disabled',answered_by:'model',solve_mode:'off'},
    ]},
    code_behavior:{version:1,asks:[{line:10,name:'code',scope:'declared_tests_only',tests:{count:3},
      candidates:2,passing:2,status:'agreed_on_declared',covered_by:'root_D7'}]},
    model_identity:{version:1,basis:'recorded_at_report',computed_at:1791140000,strict:false,applicators:{[unsafe]:{pinned:'sha256:'+'a'.repeat(64),
      statuses:{observed:2,drift:1,unavailable:1,invalid:0}}},drift:[{line:12,applicator:unsafe,action:'recorded'}]},
    escalation:{version:1,asks:2,local_only_success:1,cloud_accepted:1,failed:0,
      by_rung:[{rung:0,applicator:'ollama:small',locality:'local',accepted:1},
        {rung:1,applicator:'explicit-cloud',locality:'cloud',accepted:1}]},
  };
}
function fixture(report, trace = [], paperMap = []) {
  return async (request,url) => {
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta') return {json:{version:'fixture',examples:[]}};
    if(route==='runs') return {json:{runs:[{id:ID,title:'Synthetic evidence',status:'done'}]}};
    if(route==='run') return {json:{id:ID,title:'Synthetic evidence',status:'done',source:'let x=1.\nshow x.',
      meta:{by:'fake:local',created:1,options:{}},state:{status:'done',asks:4,calls:2,cached:0,outputs:[],...report},
      trace,artifacts:[],log:''}};
    if(route==='paper/map') return {json:{map:paperMap}};
    return undefined;
  };
}
for (const mobile of [false, true]) {
  test(`imported premise scope and immutable acceptance ${mobile ? 'phone dark' : 'desktop light'}`, async () => {
    const checked = {id:'receipt-1',passed:true,predicate:'gate'};
    const relation = {check_id:'receipt-1',scope:'same_scope_values_selected_by_a_passed_check',bindings:{[unsafe]:{}}};
    const trace = [
      {kind:'module-knowledge',line:4,note:unsafe,status:'ok'},
      {kind:'ensure',line:4,check:checked,acceptance_lineage:relation},
      {kind:'ensure',line:4,check:checked,acceptance_lineage:{...relation,check_id:'unrelated'}},
      {kind:'ensure',line:4,check:checked,acceptance_lineage:{...relation,bindings:[]}},
      {kind:'ensure',line:4,check:{passed:true},acceptance_lineage:{...relation,check_id:undefined}},
    ];
    const {context,page,errors} = await open(browser,'/automation-studio/symblic.html#runs',
      fixture({},trace,[{}, {}, {}, {paper_line:99}]),{mobile});
    try {
      await page.locator(`[data-run="${ID}"]`).click();
      await page.locator('.sy-trace .st').first().waitFor();
      await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
      const rows=page.locator('.sy-trace .st');
      assert.equal(await rows.nth(0).locator('.ln').textContent(),'L4');
      assert.equal(await rows.nth(0).locator('.ln').getAttribute('title'),'Module line 4 · '+unsafe);
      assert.equal(await rows.nth(1).locator('.ln').textContent(),'L99');
      assert.match(await rows.nth(1).textContent(),/Additional imported premises retained for:/);
      assert.ok((await rows.nth(1).textContent()).includes(unsafe));
      for (const index of [2,3,4]) assert.doesNotMatch(await rows.nth(index).textContent(),/Additional imported premises/);
      assert.equal(await page.locator('.sy-trace img').count(),0);
      assert.equal(await noHorizontalScroll(page),true);
      assert.deepEqual(await axe(page),[]);
      assert.deepEqual(errors,[]);
    } finally {await context.close();}
  });
}
for(const mobile of [false,true]) {
  test(`determination and provider receipts ${mobile?'phone dark':'desktop light'}`,async()=>{
    const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#runs',fixture(evidence()),{mobile});
    try {
      await page.locator(`[data-run="${ID}"]`).click();
      const panel=page.locator('#syDeterminism');
      await panel.locator('summary').first().waitFor();
      await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
      await panel.locator('summary').first().click();
      const content=await panel.textContent();
      assert.match(content,/One answer satisfies the encoded constraints/);
      assert.match(content,/Several answers satisfy the encoded constraints/);
      assert.match(content,/Line 4 · item 2 · several/);
      assert.match(content,/No answer satisfies the encoded constraints/);
      assert.match(content,/No finite answer domain/);
      assert.match(content,/Speculative analysis was disabled by the author/);
      assert.match(content,/Passing values: not reported/);
      assert.match(content,/Answered by: No accepted answer/);
      assert.match(content,/Passing-value list is truncated/);
      assert.match(content,/does not establish equivalence on other inputs/);
      assert.match(content,/Manifest observations do not attest/);
      assert.match(content,/Recorded when the runner wrote this report/);
      assert.match(content,/computed at: 2026-/);
      assert.match(content,/accepted from cloud: 1/);
      assert.match(content,/Cloud selection does not establish/);
      assert.ok(content.includes(unsafe));
      assert.equal(await panel.locator('img').count(),0);
      assert.equal(await noHorizontalScroll(page),true);
      assert.deepEqual(await axe(page),[]);
      assert.deepEqual(errors,[]);
    } finally {await context.close();}
  });
}
test('old, partial and unknown-version reports never imply zero observations',async()=>{
  const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#runs',fixture({}));
  try {
    await page.locator(`[data-run="${ID}"]`).click();
    const panel=page.locator('#syDeterminism');
    await panel.locator('summary').first().waitFor();
    assert.equal((await panel.textContent()).match(/Not reported by this run/g).length,4);
    await page.evaluate(()=>SymblicDeterminism.render(document.querySelector('#syDeterminism'),{
      determinacy:{version:99},escalation:{version:1,by_rung:[]},model_identity:{version:1,checker:{available:false}}}));
    const content=await panel.textContent();
    assert.match(content,/Unsupported report version/);
    assert.match(content,/accepted from cloud: not reported/);
    assert.match(content,/Applicator observations were not reported/);
    assert.match(content,/identity checker is unavailable/);
    assert.doesNotMatch(content,/accepted from cloud: 0/);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});
test('model observations are rechecked only on request, with visible failures and bounds',async()=>{
  let rechecks=0;
  const recorded=evidence();
  const base=fixture(recorded);
  const {context,page,errors,requests}=await open(browser,'/automation-studio/symblic.html#runs',async(request,url)=>{
    if(url.pathname.endsWith('/run/recheck-models')) {
      assert.equal(request.method(),'POST');
      assert.deepEqual(request.postDataJSON(),{id:ID});
      rechecks++;
      if(rechecks===1) return {status:503,json:{error:'Observation checker update needed'}};
      return {json:{id:ID,model_identity:{...recorded.model_identity,basis:'fresh_recheck',computed_at:1791140100,
        rows_truncated:true,audit_complete:false,calls_file:'present',invalid_rows:2,rows_scanned:13,missing_identity_rows:3}}};
    }
    return base(request,url);
  });
  try {
    await page.locator(`[data-run="${ID}"]`).click();
    const panel=page.locator('#syDeterminism');
    await panel.locator('summary').first().click();
    assert.equal(rechecks,0);
    const button=panel.getByRole('button',{name:'Recheck retained model observations'});
    await button.click();
    await panel.getByRole('status').filter({hasText:'Observation checker update needed'}).waitFor();
    assert.equal(await button.isEnabled(),true);
    await button.click();
    await panel.getByText('Explicit recheck of retained call records',{exact:false}).waitFor();
    assert.match(await panel.textContent(),/later rows were not assessed/);
    assert.match(await panel.textContent(),/Stored-record audit: incomplete/);
    assert.match(await panel.textContent(),/Call ledger: readable · malformed records: 2/);
    assert.match(await panel.textContent(),/Records scanned: 13 · missing identity records: 3/);
    assert.doesNotMatch(await panel.textContent(),/Stored-record audit: complete/);
    assert.equal(await panel.locator('details').first().evaluate(node=>node.open),true);
    assert.equal(rechecks,2);
    assert.equal(requests.filter(row=>row.path.endsWith('/run/recheck-models')).length,2);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});

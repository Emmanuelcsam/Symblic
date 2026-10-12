// Browser wiring only: source assets, pure compilers and intercepted APIs. No providers.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test, launch, open, root, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async()=>{browser=await launch();});
after(async()=>{await browser?.close();});
function python(code,value) {
  const r=spawnSync(process.env.TEST_PYTHON || 'python3',['-B','-c',code],{cwd:root,input:JSON.stringify(value),encoding:'utf8',timeout:30000});
  assert.equal(r.status,0,r.stderr||String(r.error)); return JSON.parse(r.stdout);
}
const sheet='# demo.js\n## Unit `answer()`\nReturn 7.\nExamples:\n    answer() ==> 7\n## Assemble `demo.js`\n    /*UNITS*/\n';
const code='function answer() { return 7; }';
function fixture() {
  const state={body:null,compiled:null};
  const manifest=python(`import json,sys;from symblic.spec import sheets as S,contracts as C,build as B
d=json.load(sys.stdin);p=C.plan(S.parse(d['sheet']));i=p['order'][0];r=B.runtime_identity()
a=C.record_artifact(p,i,d['code'],{},runtime_identity=r,checks=[{'scope':'invented_browser_fixture','passed':True,'subject_sha256':C.code_hash(d['code'])}])
print(json.dumps(C.artifact_manifest(p,{i:a},runtime_identity=r)))`,{sheet,code});
  async function api(request,url) {
    const route=url.pathname.replace('/api/automation/symblic/','');
    if(route==='meta')return {json:{version:'fixture',examples:[]}};
    if(route==='programs')return {json:{programs:[]}};
    if(route==='runs')return {json:{runs:[]}};
    if(route==='spec/check') return {json:python('import json,sys;from integration.host import symblic_engine as E;print(json.dumps(E.spec_check(json.load(sys.stdin))))',request.postDataJSON())};
    if(route==='spec/verify')return {json:python('import json,sys;from symblic.spec import contracts as C;print(json.dumps(C.verify_manifest(json.load(sys.stdin)["manifest"])))',request.postDataJSON())};
    if(route==='spec/run') {
      state.body=request.postDataJSON();
      state.compiled=python('import json,sys;from symblic.spec import build as B;d=json.load(sys.stdin);print(json.dumps(B.compile_cards(d["sheet"],d["by"],budget=d["budget"],artifacts=d.get("manifest",{}).get("artifacts"),presentation=d.get("presentation","compact"),declaration_contracts=d.get("declaration_contracts"))))',state.body);
      return {json:{id:'000000000001',kept:state.compiled.kept}};
    }
    if(route==='run')return {json:{id:'000000000001',source:state.compiled.source,status:'done',meta:{},state:{outputs:[],status:'done'},trace:[],artifacts:[]}};
    if(route==='paper/map')return {json:{map:[]}};
    if(route==='spec/manifest')return {json:{manifest}};
    return undefined;
  }
  return {api,state,manifest};
}

for(const mobile of [false,true])test('task-card import check build export '+(mobile?'phone dark':'desktop light'),async()=>{
  const f=fixture();const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#build',f.api,{mobile});
  try {
    await page.locator('#syBuildMode').waitFor();
    await page.evaluate(theme=>Studio.setTheme(theme),mobile?'dark':'light');
    await page.locator('#syBuildMode').selectOption('task-cards');
    await page.locator('#sySheet').fill(sheet);
    await page.locator('#syBuildBudget').fill('20000');
    await page.locator('#syCheckSheet').click();
    await page.getByText('1 dependency layers.',{exact:false}).waitFor();
    await page.locator('#syBuildManifest').setInputFiles({name:'fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(f.manifest))});
    await page.locator('#syClearManifest').waitFor();
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(await axe(page),[]);
    await page.locator('#syBuild').click();
    await page.locator('#syExportManifest').waitFor();
    assert.equal(f.state.body.mode,'task-cards');
    assert.equal(f.state.body.budget,20000);
    assert.equal(f.state.body.manifest.sha256,f.manifest.sha256);
    assert.equal(f.state.compiled.kept,1);
    const download=page.waitForEvent('download');
    await page.locator('#syExportManifest').click();
    assert.equal((await download).suggestedFilename(),'symblic-build-000000000001.json');
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});


test('task-card declaration template is editable and passed to the compiler',async()=>{
  const f=fixture();const {context,page,errors}=await open(browser,'/automation-studio/symblic.html#build',f.api);
  try {
    await page.locator('#syBuildMode').selectOption('task-cards');
    await page.locator('#sySheet').fill(sheet);
    await page.locator('#syBuildPresentation').selectOption('full');
    await page.getByText('Declaration requirements (optional)',{exact:true}).click();
    await page.locator('#syDeclarationTemplate').click();
    await page.waitForFunction(()=>document.querySelector('#syBuildDeclarations').value.includes('"exports"'));
    const contracts=JSON.parse(await page.locator('#syBuildDeclarations').inputValue());
    assert.deepEqual(Object.values(contracts),[{version:1,exports:{answer:'function'}}]);
    assert.equal(await noHorizontalScroll(page),true);
    assert.deepEqual(await axe(page),[]);
    await page.locator('#syBuild').click();
    await page.locator('#syExportManifest').waitFor();
    assert.equal(f.state.body.presentation,'full');
    assert.deepEqual(f.state.body.declaration_contracts,contracts);
    assert.match(f.state.compiled.source,/js_declarations_check/);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});

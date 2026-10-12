// Uses real compiler/checker fixture. No model, provider, store, or program execution.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const sourceJS=fs.readFileSync(path.join(root, 'web/studio/symblic-english-circuit.js'),'utf8');
const saved=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/symblic-english-pixels.json'),'utf8'));
const context={window:{}};vm.runInNewContext(sourceJS,context);
const fixture=()=>JSON.parse(JSON.stringify(saved));
const project=f=>JSON.parse(JSON.stringify(context.window.SymblicEnglishCircuit.project(f.compiled,f.source)));

test('pixel circuit retains every English clause and only genuine generated workers and gates',()=>{
  const f=fixture(),p=project(f);assert.equal(p.available,true);assert.equal(p.mode,'pixels');
  assert.equal(p.sourceStatementCount,34);assert.equal(p.nodes.length,52);
  assert.deepEqual(p.nodes.filter(n=>n.kind==='pixel_obligation').map(n=>n.text),f.compiled.statements.map(s=>s.text));
  assert.equal(p.nodes.filter(n=>n.kind==='ask').length,9);assert.equal(p.nodes.filter(n=>n.kind==='accept').length,9);
  assert.equal(p.nodes.reduce((sum,n)=>sum+n.checks.length,0),36);
  assert.ok(p.nodes.flatMap(n=>n.checks).every(c=>c.status==='not_run'));
  assert.ok(!p.nodes.some(n=>['display','presentation'].includes(n.kind)),'no invented execution or physical display node');
});

test('model wires match exact transitive task-card inputs and direct helpers remain distinct',()=>{
  const f=fixture(),p=project(f),b=f.compiled.pixel_build,byId=new Map(b.plan.units.map(u=>[u.id,u]));
  for(const u of b.plan.units){
    const n=p.nodes.find(n=>n.binds.includes(u.binding));assert.ok(n);
    assert.deepEqual(n.incoming.map(e=>e.name),u.closure.map(id=>byId.get(id).binding));
    assert.ok(n.incoming.every(e=>e.role==='model_context'));
  }
  const draw=p.nodes.find(n=>n.binds.includes('unit_drawPixels'));
  assert.match(draw.checkDetail,/direct helpers: whitePixels/);
  assert.match(draw.checkDetail,/does not prove helper use/);
  assert.ok(draw.incoming.some(e=>e.name==='unit_square'),'transitive implementation code really is supplied');
  assert.deepEqual(p.nodes.find(n=>n.binds.includes('unit_clearPixels')).incoming,[]);
});

test('gate mapping follows builder DAG order rather than compiler unit listing order',()=>{
  const f=fixture(),p=project(f),b=f.compiled.pixel_build,byId=new Map(b.plan.units.map(u=>[u.id,u]));
  assert.notDeepEqual(b.units.map(u=>u.binding),b.plan.order.map(id=>byId.get(id).binding));
  for(const [index,id] of b.plan.order.entries()){
    const u=byId.get(id),g=p.nodes.find(n=>n.id==='pixel-gate:'+u.binding);
    const check=f.compiled.check.plan.find(row=>row.binds==='assembly_check_'+index);
    assert.ok(g.nativeLines.includes(check.line));
    assert.deepEqual(g.incoming.map(e=>e.name),b.units.map(u=>u.binding).sort());
    assert.deepEqual(g.checks.map(c=>c.kind),['declaration_shape','selected_scope','assembled_scope','output_scope']);
  }
});

test('all worker/gate links use their original English clause lines including shared clause fourteen',()=>{
  const f=fixture(),p=project(f);
  for(const u of f.compiled.pixel_build.units){
    const expected=u.clauses.map(id=>({statement:id,line:f.compiled.statements[id-1].line}));
    for(const id of ['pixel-worker:','pixel-gate:']) assert.deepEqual(p.nodes.find(n=>n.id===id+u.binding).sourceRefs,expected);
  }
  assert.equal(p.nodes.find(n=>n.binds.includes('unit_square')).line,p.nodes.find(n=>n.binds.includes('unit_separation')).line);
});

test('physical light, host display, mapping and timing clauses remain explicitly unverified',()=>{
  const p=project(fixture()),physical=p.nodes.filter(n=>n.label==='Physical display obligation');
  assert.deepEqual(physical.map(n=>n.id),[24,25,26,27,28,29,32,33,34]);
  for(const n of physical){assert.equal(n.obligationStatus,'physical_unverified');assert.match(n.checkDetail,/unverified/);assert.deepEqual(n.checks,[]);}
});

test('stale source and unknown or incomplete coverage never produce imagined circuit wires',()=>{
  const changed=fixture();changed.source=changed.source.replace('eight hundred columns','nine hundred columns');assert.equal(project(changed).available,false);
  for(const mutate of [
    c=>{c.check.ok=false;},c=>{c.pixel_build.version='unknown';},c=>{c.pixel_build.unmapped_statements=[7];},
    c=>{c.presentation.clause_obligations.pop();},c=>{c.presentation.clause_obligations[23].status='verified';},
    c=>{c.presentation.clause_obligations[23].category='software_host';},
    c=>{c.presentation.clause_obligations[13].model_units=['square'];},
    c=>{c.pixel_build.units[0].clauses=[1];},c=>{c.presentation.future_frame_precomputation=true;}
  ]){const f=fixture();mutate(f.compiled);const p=project(f);assert.equal(p.available,false);assert.deepEqual(p.edges,[]);}
});

test('mismatched, future or missing dependency metadata cannot fabricate model context',()=>{
  for(const mutate of [
    c=>{c.pixel_build.units[0].uses=['drawPixels'];},
    c=>{c.presentation.dependencies.drawPixels=[];},
    c=>{c.pixel_build.plan.order.reverse();},
    c=>{c.pixel_build.plan.units[0].closure=[c.pixel_build.plan.units.at(-1).id];},
    c=>{c.pixel_build.plan.units[0].dependencies=null;},
    c=>{c.check.plan.find(r=>r.binds==='unit_delta').reads=[];},
    c=>{c.check.plan.find(r=>r.binds==='test_inside').reads.push('unit_nextX');}
  ]){const f=fixture();mutate(f.compiled);assert.equal(project(f).available,false);}
});

test('absent native gates and unrelated assembly/output dependencies are refused',()=>{
  for(const mutate of [
    c=>{c.check.plan=c.check.plan.filter(r=>r.binds!=='declarations_unit_square');},
    c=>{c.check.plan.find(r=>r.binds==='assembly_check_3').reads=['unit_delta'];},
    c=>{c.check.plan.find(r=>r.binds==='output_check_3').reads=['unit_delta'];},
    c=>{c.check.plan.find(r=>r.binds==='spec_output').reads=[];},
    c=>{c.check.plan.find(r=>r.binds==='spec_code').reads.pop();},
    c=>{c.pixel_build.units[2].native_lines=c.pixel_build.units[3].native_lines;}
  ]){const f=fixture();mutate(f.compiled);assert.equal(project(f).available,false);}
});

test('normalized line endings retain source links',()=>{
  const f=fixture();f.source='\uFEFF'+f.source.replaceAll('\n','\r\n');assert.equal(project(f).available,true);
  f.compiled.statements[0].end_col--;assert.equal(project(f).available,false);
});

class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};this.attributes={};this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(key,value){this.attributes[key]=value;}
  addEventListener(key,callback){this.listeners[key]=callback;}
}
const walk=e=>[e,...e.children.flatMap(walk)];
test('renderer keeps source links actionable and labels generated components without claiming success',()=>{
  const document={createElement:tag=>new Element(tag)},c={window:{},document};vm.runInNewContext(sourceJS,c);
  const target=new Element('main'),f=fixture();let selected=0;
  const p=c.window.SymblicEnglishCircuit.render(target,{...f,onSelectLine:line=>{selected=line;}});
  assert.equal(p.available,true);const all=walk(target),text=all.map(e=>e.textContent).join('\n');
  assert.match(text,/34 statements · 9 workers · 36 checks/);assert.match(text,/Physical display obligations remain unverified/);
  const link=all.find(e=>e.tagName==='button'&&e.textContent==='Statement 14 · line 27');assert.ok(link);
  link.listeners.click();assert.equal(selected,27);assert.match(link.attributes['aria-label'],/select English line 27/);
  assert.equal(all.filter(e=>e.dataset.kind==='pixel_obligation').length,34);
  assert.ok(all.filter(e=>e.tagName==='button').every(e=>e.type==='button'));
});

const savedRecovery=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/symblic-english-pixel-recovery.json'),'utf8'));
const recovered=()=>JSON.parse(JSON.stringify(savedRecovery));
test('recovery projects seven retained model implementations and only two fresh workers',()=>{
  const f=recovered(),p=project(f);assert.equal(p.available,true);assert.equal(p.retainedWorkerCount,7);
  assert.equal(p.nodes.filter(n=>n.kind==='retained').length,7);assert.equal(p.nodes.filter(n=>n.kind==='ask').length,2);
  assert.deepEqual(p.nodes.filter(n=>n.kind==='ask').flatMap(n=>n.outputs.map(o=>o.label)),['whitePixels','drawPixels']);
  assert.equal(p.nodes.reduce((n,node)=>n+node.checks.length,0),46);
  assert.deepEqual(p.nodes.filter(n=>n.kind==='pixel_obligation').map(n=>n.text),saved.compiled.statements.map(s=>s.text));
});

test('retained helper relationships never masquerade as fresh model context',()=>{
  const f=recovered(),p=project(f),byId=new Map(f.compiled.pixel_build.plan.units.map(u=>[u.id,u]));
  for(const n of p.nodes.filter(n=>n.kind==='retained')){
    const row=f.compiled.pixel_build.plan.units.find(u=>u.binding===n.binds[0]);
    assert.deepEqual(n.incoming.map(e=>e.name),row.dependencies.map(id=>byId.get(id).binding));
    assert.ok(n.incoming.every(e=>e.role==='retained_dependency'));assert.match(n.checkDetail,/no new model request/);
  }
  const white=p.nodes.find(n=>n.binds.includes('unit_whitePixels'));
  assert.equal(white.kind,'ask');assert.ok(white.incoming.every(e=>e.role==='model_context'));
});

test('retained literal bindings and mandatory assert gates preserve source associations',()=>{
  const f=recovered(),p=project(f),rows=new Map(f.compiled.check.plan.map(r=>[r.line,r]));
  for(const u of f.compiled.pixel_build.units.filter(u=>u.acquisition==='reused_artifact')){
    const worker=p.nodes.find(n=>n.binds.includes(u.binding)),gate=p.nodes.find(n=>n.parent===worker.id);
    assert.equal(rows.get(worker.nativeLines[0]).kind,'let');
    assert.ok(gate.checks.every(c=>rows.get(c.nativeLine).kind==='assert'));
    assert.deepEqual(gate.sourceRefs,worker.sourceRefs);
  }
});

test('incomplete retained provenance or changed gate kind refuses recovery projection',()=>{
  for(const mutate of [
    c=>{c.pixel_build.kept=6;},c=>{c.pixel_build.units[0].artifact_sha256=null;},
    c=>{c.pixel_build.units[0].binding_kind='ask';},
    c=>{const id=c.pixel_build.plan.order[0];c.pixel_build.reuse[id].reusable=false;},
    c=>{const id=c.pixel_build.plan.order[0];c.pixel_build.reuse[id].artifact_sha256='0'.repeat(64);},
    c=>{const row=c.check.plan.find(r=>r.binds==='test_delta');c.check.plan.find(r=>r.line===row.line+1).kind='ensure';}
  ]){const f=recovered();mutate(f.compiled);assert.equal(project(f).available,false);}
});

test('recovery render summary separates fresh work from retained model functions',()=>{
  const document={createElement:tag=>new Element(tag)},c={window:{},document};vm.runInNewContext(sourceJS,c);
  const target=new Element('main');c.window.SymblicEnglishCircuit.render(target,recovered());
  const text=walk(target).map(e=>e.textContent).join('\n');
  assert.match(text,/34 statements · 2 workers · 7 reused model functions · 46 checks/);
  assert.match(text,/Native gates recheck the retained code/);
});

const savedVM=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/symblic-english-pixel-vm.json'),'utf8'));
const vmFixture=()=>JSON.parse(JSON.stringify(savedVM));
test('fresh exact-client-VM circuit exposes nine local and one whole-program VM gate',()=>{
  const f=vmFixture(),p=project(f);assert.equal(p.available,true);assert.equal(p.nodes.length,53);
  assert.equal(p.nodes.filter(n=>n.kind==='ask').length,9);
  assert.equal(p.nodes.reduce((sum,n)=>sum+n.checks.length,0),46);
  assert.equal(p.nodes.flatMap(n=>n.checks).filter(c=>c.kind==='client_vm').length,9);
  assert.equal(p.nodes.flatMap(n=>n.checks).filter(c=>c.kind==='client_vm_assembly').length,1);
  const gate=p.nodes.find(n=>n.id==='pixel-client-assembly');assert.ok(gate);
  assert.equal(gate.incoming.length,9);assert.ok(gate.incoming.every(e=>e.role==='client_vm_check'));
  assert.match(gate.checkDetail,/does not verify physical light/);
});

test('every VM gate matches actual native source, retained status and selected input dependencies',()=>{
  for(const f of [vmFixture(),recovered()]){
    const p=project(f);assert.equal(p.available,true);
    const rows=new Map(f.compiled.check.plan.map(r=>[r.line,r]));
    for(const [name,mapped] of Object.entries(f.compiled.pixel_build.client_vm.gates)){
      const check=p.nodes.flatMap(n=>n.checks).find(c=>c.nativeLine===mapped.guard_line);
      assert.ok(check,name);assert.equal(check.status,'not_run');
      assert.equal(rows.get(mapped.check_line).binds,mapped.binding);
      assert.equal(rows.get(mapped.guard_line).kind,mapped.retained?'assert':'ensure');
      assert.ok(rows.get(mapped.check_line).reads.includes('pixel_vm_boot'));
    }
  }
});

test('missing VM gate, wrong retained flag, changed assets or untracked output dependency refuses projection',()=>{
  for(const mutate of [
    c=>{delete c.pixel_build.client_vm.gates.assembly;},
    c=>{c.pixel_build.client_vm.gates.inside.retained=true;},
    c=>{c.presentation.assets.vm.sha256='0'.repeat(64);},
    c=>{c.check.plan.find(r=>r.binds==='pixel_vm_assembly').reads.pop();},
    c=>{c.check.plan.find(r=>r.binds==='pixel_vm_inside').reads.push('unit_nextX');},
    c=>{c.pixel_build.client_vm.version='unknown';},
    c=>{c.pixel_build.plan.sheet.template.text+='runAnything();';}
  ]){const f=vmFixture();mutate(f.compiled);assert.equal(project(f).available,false);}
});

const savedVMv1=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/symblic-english-pixel-vm-v1.json'),'utf8'));
test('previous host-bootstrap-only VM metadata remains readable',()=>{
  const f=JSON.parse(JSON.stringify(savedVMv1));assert.equal(f.compiled.pixel_build.client_vm.version,'symblic-english-pixel-checks/1');
  assert.equal(project(f).available,true);
});

test('split pinned parser is a checked host dependency and never a model context wire',()=>{
  const f=vmFixture(),p=project(f);assert.equal(p.available,true);
  assert.equal(f.compiled.pixel_build.client_vm.version,'symblic-english-pixel-checks/2');
  assert.equal(f.compiled.pixel_build.client_vm.assets.parser_binding,'pixel_vm_parser');
  assert.ok(f.compiled.check.plan.some(row=>row.kind==='let'&&row.binds==='pixel_vm_parser'));
  assert.ok(f.compiled.check.plan.filter(row=>row.kind==='let'&&row.binds?.startsWith('pixel_vm_')&&row.binds!=='pixel_vm_parser').every(row=>row.reads.includes('pixel_vm_parser')));
  assert.ok(!p.edges.some(edge=>['pixel_vm_parser','pixel_vm_boot'].includes(edge.name)));
  assert.equal(p.nodes.length,53);assert.equal(p.nodes.reduce((sum,node)=>sum+node.checks.length,0),46);
});

test('missing or mislabeled split-parser provenance refuses projected gates',()=>{
  for(const mutate of [
    c=>{c.pixel_build.client_vm.assets.parser_binding='unknown';},
    c=>{c.pixel_build.client_vm.assets.host_input='unknown';},
    c=>{c.check.plan=c.check.plan.filter(row=>row.binds!=='pixel_vm_parser');},
    c=>{c.check.plan.find(row=>row.binds==='pixel_vm_delta').reads=['pixel_vm_boot','unit_delta'];}
  ]){const f=vmFixture();mutate(f.compiled);assert.equal(project(f).available,false);}
});

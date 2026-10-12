// Smaller construction tasks retain exact selected dependencies and every source sentence.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const saved=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/symblic-english-atomic-construction.json'),'utf8'));
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root, 'web/studio/symblic-english-circuit.js'),'utf8'),context);
const fixture=()=>JSON.parse(JSON.stringify(saved));
const project=f=>JSON.parse(JSON.stringify(context.window.SymblicEnglishCircuit.project(f.compiled,f.source)));

test('atomic construction projects all sixty statements and nine source workers',()=>{
  const f=fixture(),p=project(f);assert.equal(p.available,true);assert.equal(p.mode,'construction');
  assert.equal(p.nodes.length,60);assert.equal(p.nodes.filter(node=>node.kind==='ask').length,9);
  assert.equal(p.nodes.filter(node=>node.kind==='accept').length,9);
  assert.equal(p.nodes.reduce((sum,node)=>sum+node.checks.length,0),18);
  assert.deepEqual(p.nodes.map(node=>node.text),f.compiled.statements.map(row=>row.text));
  assert.ok(p.nodes.flatMap(node=>node.checks).every(check=>check.status==='not_run'));
});

test('cell, column and frame workers only receive their declared earlier implementations',()=>{
  const f=fixture(),p=project(f),units=f.compiled.construction.units;
  for(const [contract,expected] of [['cell',['built_step_1','built_step_3','built_step_4','built_step_5']],['column',['built_step_6']],['frames_from_columns',['built_step_7']],['film',['built_step_8']]]){
    const unit=units.find(unit=>unit.contract===contract);assert.ok(unit);
    const worker=p.nodes.find(node=>node.kind==='ask'&&node.binds.includes(unit.binding));
    assert.deepEqual(worker.incoming.map(edge=>edge.name),expected);
    assert.deepEqual(p.nodes.find(node=>node.kind==='using'&&node.parent===worker.id).selected.map(edge=>edge.name),expected);
  }
  assert.deepEqual(p.nodes.at(-1).incoming.map(edge=>edge.name),units.map(unit=>unit.binding),'assembly preserves the whole accepted program');
});

test('both supported construction versions require the exact known schema',()=>{
  for(const version of ['symblic-english-build/1','symblic-english-build/2']){
    const f=fixture();f.compiled.construction.version=version;assert.equal(project(f).available,true);
    f.compiled.construction.schema_version=2;assert.equal(project(f).available,false);
    delete f.compiled.construction.schema_version;assert.equal(project(f).available,false);
  }
  const f=fixture();f.compiled.construction.version='symblic-english-build/3';assert.equal(project(f).available,false);
});

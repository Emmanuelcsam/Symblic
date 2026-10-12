// Pure interpreter/controller regression checks. Synthetic fixtures, no model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import test from 'node:test';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const checkout=process.env.SYMBLIC_CHECKOUT_ROOT||root;
const require=createRequire(import.meta.url),acorn=require(path.join(checkout,'symblic/js/acorn.js'));
const context=vm.createContext({performance,Uint8Array,console});
vm.runInContext(fs.readFileSync(path.join(root, 'web/studio/symblic-pixel-vm.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root, 'web/studio/symblic-pixel-program.js'),'utf8'),context);
const VM=context.SymblicPixelVM,Player=context.SymblicPixelProgram;
const compile=(source,options={})=>VM.compile(source,{parser:acorn,...options});
const plain=value=>JSON.parse(JSON.stringify(value));
const fixture=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/symblic-pixel-program.json'),'utf8'));

test('data interpreter matches native arithmetic, declared calls and local mutation',()=>{
  const source=`function unit(a,b){const pair={left:a,right:b}; let value=0; for(let i=0;i<3;i++){value+=pair.left;} const values=[]; values.push(value,pair.right); let sum=0; for(const item of values){sum+=item;} return sum>0?Math.floor(sum):Math.abs(sum);}`;
  const machine=compile(source),native=vm.runInNewContext(source+';unit');
  for(const input of [[2,9],[-4,3],[0,0],[1.5,2.25]])assert.equal(machine.call('unit',input),native(...input));
});
test('no global, executable value, prototype, accessor or dynamic call can enter the VM',()=>{
  const refused=[
    'function unit(){return window;}', 'function unit(){return globalThis;}', 'function unit(){return fetch(1);}',
    'function unit(){return [].constructor;}', 'function unit(){return [].__proto__;}',
    'function unit(){return new Uint8Array(2);}', 'function unit(){return (()=>1)();}',
    'function unit(){return {get x(){return 1;}};}', 'function unit(){return {__proto__:1};}',
    'function unit(){const x={a:1};return x["a"];}','function unit(){return Math.random();}',
    'function unit(){return eval(1);}', 'function unit(){return Function(1);}',
    'function unit(){let x;return x;}', 'function unit(){return;}',
    'const unit=()=>1;', 'async function unit(){return 1;}', 'function* unit(){return 1;}',
    'function unit(){while(true){}return 0;}', 'function unit(){return import(1);}',
    'function unit(){const x=[];return x.map(unit);}', 'function unit(){return this;}',
    'function unit(){return Math;}', 'function unit(){return /x/;}', 'function unit(){return 1n;}'
  ];
  for(const source of refused)assert.throws(()=>compile(source),/Pixel program:/,source);
});
test('only owned buffers cross the boundary and binary writes are strict',()=>{
  const machine=compile('function unit(a){a.fill(0);a[1]=1;return a;}');
  const buffer=machine.buffer(4);buffer.fill(1);assert.equal(machine.call('unit',[buffer]),buffer);assert.deepEqual([...buffer],[0,1,0,0]);
  for(const arg of [[],{},new Uint8Array(4),()=>1,NaN,Infinity])assert.throws(()=>machine.call('unit',[arg]),/invalid invocation/);
  assert.throws(()=>compile('function unit(a){a[0]=255;return a;}').call('unit',[buffer]),/invalid invocation/);
  const invalid=compile('function unit(a){a[0]=255;return a;}'),own=invalid.buffer(2);assert.throws(()=>invalid.call('unit',[own]),/binary buffer/);
});
test('memory, iteration, recursion and numeric resource limits refuse visibly',()=>{
  assert.throws(()=>compile('function unit(){for(let i=0;i<99999999;i++){}return 1;}').call('unit',[]),/budget/);
  assert.throws(()=>compile('function unit(){return unit();}').call('unit',[]),/depth/);
  assert.throws(()=>compile('function unit(){return 1/0;}').call('unit',[]),/nonfinite/);
  assert.throws(()=>compile('function unit(){const a=[];a[99999999]=1;return a;}').call('unit',[]),/bounds/);
  assert.throws(()=>compile('function unit(){const a=[];for(let i=0;i<99999999;i++){a.push(i);}return a;}').call('unit',[]),/budget|limit/);
  assert.throws(()=>compile('function unit(){if(false)return 1;}').call('unit',[]),/explicit value/);
});
test('exact exports and declared dependency edges are validated before use',()=>{
  const source='function a(x){return x+1;}function b(x){return a(x);}';
  assert.equal(compile(source,{exports:['a','b'],dependencies:{a:[],b:['a']}}).call('b',[2]),3);
  assert.throws(()=>compile(source,{exports:['a']}),/declarations/);
  assert.throws(()=>compile(source,{dependencies:{a:[],b:[]}}),/declared dependency/);
  assert.throws(()=>compile(source,{dependencies:{a:[],b:['missing']}}),/invalid declared/);
  assert.throws(()=>compile('function a(){return 1;}function b(){return a; }'),/forbidden local/);
});
test('complete test-only pixel artifact agrees with native JS including clipped boundaries and clearing',()=>{
  const machine=compile(fixture.implementation,{exports:Player.ABI,dependencies:Player.DEPENDENCIES});
  const native=vm.runInNewContext(fixture.implementation+';({nextX,bounds,whitePixels,clearPixels,drawPixels})');
  const a=machine.buffer(480000),b=new Uint8Array(480000);
  for(const x of [0,1,5,47,399,794,799]){
    assert.equal(machine.call('nextX',[x]),native.nextX(x));
    assert.deepEqual(plain(machine.call('bounds',[x,300])),plain(native.bounds(x,300)));
    assert.deepEqual(plain(machine.call('whitePixels',[x,300])),plain(native.whitePixels(x,300)));
    machine.call('clearPixels',[a]);native.clearPixels(b);machine.call('drawPixels',[a,x,300]);native.drawPixels(b,x,300);
    assert.deepEqual(a,b);
  }
  assert.equal(machine.call('nextX',[null]),0);assert.equal(machine.call('nextX',[799]),0);
});
test('presentation is bound to dimensions, binary colors, source and declared functions',()=>{
  const outputs=[{label:'implementation.js',value:fixture.implementation}];
  assert.equal(Player.validate(fixture.presentation,outputs),fixture.implementation);
  for(const change of [{width:0},{width:2049},{height:1000},{radius:17},{initial_x:800},{center_y:600},{future_frame_precomputation:true},
    {functions:['nextX']},{dependencies:{}},{assets:null},{assets:{...fixture.presentation.assets,vm:{sha256:'0'.repeat(64),sri:fixture.presentation.assets.vm.sri}}}])assert.throws(()=>Player.validate({...fixture.presentation,...change},outputs));
  assert.throws(()=>Player.validate(fixture.presentation,outputs.concat(outputs)));
  assert.throws(()=>Player.validate(fixture.presentation,[{label:'wrong.js',value:fixture.implementation}]));
});
function controllerHarness(){
  let now=0,id=0,paint=null,paintReject=null,visible=true;const tasks=new Map(),calls=[];
  const machine={buffer:n=>new Uint8Array(n),call(name,args){calls.push({name,time:now});
    if(name==='nextX')return args[0]===null?0:args[0]+1;
    if(name==='clearPixels')args[0].fill(0);else args[0][args[1]]=1;return args[0];}};
  const controller=Player.createController({machine,present:b=>calls.push({name:'copy',time:now,white:b.reduce((a,n)=>a+n,0)}),
    waitForPaint:(done,reject)=>{paint=done;paintReject=reject;return()=>{paint=null;paintReject=null;};},clock:()=>now,
    schedule:(fn,ms)=>{const key=++id;tasks.set(key,{fn,at:now+ms});return key;},cancelSchedule:key=>tasks.delete(key),visible:()=>visible});
  return{controller,calls,tasks,setVisible:v=>{visible=v;},paint:()=>{const fn=paint;paint=null;fn();},reject:()=>paintReject(new Error('no rendering opportunity')),
    advance(ms){now+=ms;for(const[key,row]of [...tasks])if(row.at<=now){tasks.delete(key);row.fn();}},early(){const[key,row]=tasks.entries().next().value;tasks.delete(key);row.fn();}};
}
test('controller never calculates the next frame before presentation and a complete delay',()=>{
  const h=controllerHarness();h.controller.play();
  assert.deepEqual(h.calls.map(x=>x.name),['nextX','clearPixels','drawPixels','copy']);assert.equal(h.tasks.size,0);
  h.advance(200);assert.equal(h.calls.length,4,'elapsed time alone cannot replace the rendering barrier');
  h.paint();h.advance(10);h.early();assert.equal(h.calls.length,4,'early timer callback cannot shorten the delay');
  h.advance(7);assert.equal(h.calls.length,8);assert.equal(h.calls[4].time,217);
  const events=plain(h.controller.state().trace);assert.ok(events.find(row=>row.kind==='delay-complete').elapsed>=1000/60);
  h.controller.destroy();assert.equal(h.tasks.size,0);
});
test('pause, resume, hidden state, failed presentation and destroy cannot skip a gate',()=>{
  const h=controllerHarness();h.controller.play();h.controller.pause();assert.equal(h.calls.length,4);
  h.controller.play();assert.equal(h.calls.length,4);h.paint();h.advance(8);h.controller.pause();h.advance(500);assert.equal(h.calls.length,4);
  h.controller.play();h.paint();h.setVisible(false);h.advance(17);assert.equal(h.calls.length,4);assert.equal(h.controller.state().playing,false);
  h.setVisible(true);h.controller.play();h.reject();assert.equal(h.controller.state().phase,'error');assert.equal(h.calls.length,4);
  h.controller.play();assert.equal(h.calls.length,4);h.controller.destroy();
});
test('a bad model clear is refused before drawing or presentation',()=>{
  let copied=false;const machine={buffer:n=>new Uint8Array(n).fill(1),call:name=>name==='nextX'?0:null};
  const c=Player.createController({machine,present:()=>{copied=true;},waitForPaint:()=>{},clock:()=>0,schedule:()=>1,cancelSchedule:()=>{}});
  c.play();assert.equal(c.state().phase,'error');assert.equal(copied,false);
});
test('block and loop lexical bindings preserve native temporal dead zones',()=>{
  const sources=[
    'function unit(a){let x=a;{const y=x;let x=2;return y;}}',
    'function unit(a){let x=a;for(let x=x;x<3;x++){}return x;}',
    'function unit(a){const x=[a];for(const x of x){return x;}return a;}',
    'function unit(a){let x=x;return x;}',
    'function unit(a){const x=(x=2);return x;}'
  ];
  for(const source of sources){
    const native=vm.runInNewContext(source+';unit');assert.throws(()=>native(7),{name:'ReferenceError'});
    assert.throws(()=>compile(source).call('unit',[7]),/not initialized/);
  }
  assert.equal(compile('function unit(a){let x=a;{let x=2;return x;}}').call('unit',[7]),2);
  assert.equal(compile('function unit(a){let x=a;for(let x=0;x<2;x++){const y=x;}return x;}').call('unit',[7]),7);
});
test('a presentation refusal remains terminal through pause, resize and reopen equivalents',()=>{
  const h=controllerHarness();h.controller.play();h.reject();const original=h.controller.state().error;
  for(const reason of ['user','display closed','display geometry changed','page is hidden']){
    h.controller.pause(reason);h.controller.play();assert.equal(h.controller.state().phase,'error');
    assert.equal(h.controller.state().error,original);assert.equal(h.controller.state().playing,false);assert.equal(h.calls.length,4);
  }
  h.controller.destroy();assert.equal(h.tasks.size,0);
});

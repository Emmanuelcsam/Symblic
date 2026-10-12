'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const scope = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/studio/symblic-frames.js'), 'utf8'), scope);
const validate = scope.window.SymblicFrames.validate;
const frame = () => ({ kind: 'character-grid', width: 32, height: 24, tick: 0, cells: [{ x: 1, y: 2, char: 'ｱ', shade: 0 }] });
const run = values => validate(values.map(value => ({ value })));
let tests = 0;
function test(label, fn) { fn(); tests++; console.log('PASS ' + label); }
function bad(f) { const result = run([f]); assert(result.error); assert.equal(result.frames.length, 0); }
test('inert import, ordinary outputs omitted, valid Unicode scalar copied', () => {
  const f = frame(), result = run([1, 'text', { kind: 'grid', value: 7 }, f]);
  assert.equal(result.error, null); assert.equal(result.frames.length, 1);
  f.cells[0].char = 'B'; assert.equal(result.frames[0].cells[0].char, 'ｱ');
  const emoji = frame(); emoji.cells[0].char = '🟢'; assert.equal(run([emoji]).error, null);
});
test('integer geometry, tick and shade enforce all bounds', () => {
  for (const [key, values] of Object.entries({ width: [0, 101, 1.5, '32'], height: [0, 101, false], tick: [-1, 64, 0.5, '0'] }))
    for (const value of values) bad({ ...frame(), [key]: value });
  bad({ ...frame(), width: 100, height: 100 });
  for (const [key, values] of Object.entries({ x: [-1, 32, 1.5, '1'], y: [-1, 24, null], shade: [-1, 8, 0.5, '0'] }))
    for (const value of values) { const f = frame(); f.cells[0][key] = value; bad(f); }
});
test('malformed cells, duplicate coordinates and non-single characters refuse entire sequence', () => {
  for (const value of [null, {}, 'x']) bad({ ...frame(), cells: value });
  bad({ ...frame(), cells: [null] });
  const duplicate = frame(); duplicate.cells.push({ ...duplicate.cells[0] }); bad(duplicate);
  for (const char of ['', 'ab', 'a\u0301', '<script>', '\ud800', '\udc00', 7, {}]) {
    const f = frame(); f.cells[0].char = char; bad(f);
  }
  const result = run([frame(), { ...frame(), tick: 99 }, frame()]);
  assert(result.error); assert.equal(result.frames.length, 0);
});
test('frame and occupied-cell ceilings are exact and bounded', () => {
  assert.equal(run(Array.from({ length: 128 }, frame)).error, null);
  assert(run(Array.from({ length: 129 }, frame)).error);
  const dense = count => ({ ...frame(), width: 50, height: 50, cells: Array.from({ length: count }, (_, i) => ({ x: i % 50, y: Math.floor(i / 50), char: '0', shade: i % 8 })) });
  assert.equal(run(Array.from({ length: 128 }, () => dense(1250))).error, null);
  assert(run(Array.from({ length: 128 }, () => dense(1251))).error);
  assert(validate(Array(10001).fill({ value: 1 })).error);
});
test('plain punctuation is accepted, errors never echo payloads', () => {
  const f = frame(); f.cells[0].char = '<'; assert.equal(run([f]).error, null);
  f.cells[0].char = '<script>PRIVATE_SENTINEL</script>';
  const r = run([f]); assert(r.error); assert(!r.error.includes('PRIVATE_SENTINEL'));
});
console.log(`${tests} focused validation groups passed`);

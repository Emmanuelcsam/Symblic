'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { normalize } = require('../../web/studio/symblic-editor-diagnostics.js');
const row = (start, end, extras = {}) => ({ start, end, position_kind: 'token', severity: 'error', message: 'Bad', ...extras });
test('ranges are bounded UTF16, including astral characters and CRLF', () => {
  const source = 'a\r\n\t😀BROKEN';
  assert.deepEqual(normalize(source, [row(6, 12)])[0], { ...row(6, 12), code: '', line: null, col: null });
  assert.deepEqual(normalize(source, [row(5, 6)])[0].start, 4);
  assert.deepEqual(normalize(source, [row(4, 5)])[0].end, 6);
  for (const invalid of [row(-1, 1), row(0, 100), row(4, 3), row('1', 2), row(0, 1, {position_kind: 'none'})]) {
    const found = normalize(source, [invalid])[0]; assert.equal(found.start, null); assert.equal(found.position_kind, 'none');
  }
});
test('EOF points and whole lines keep their honest position kind', () => {
  assert.equal(normalize('abc', [row(3, 3)])[0].position_kind, 'point');
  assert.equal(normalize('abc', [row(0, 3, {position_kind: 'line'})])[0].position_kind, 'line');
});
test('producer payload is bounded without parsing or interpreting prose', () => {
  const input = Array.from({length: 200}, () => row(0, 1, {message: '<img src=x>' + 'x'.repeat(5000), severity: 'madeup'}));
  const found = normalize('x', input);
  assert.equal(found.length, 128); assert.equal(found[0].message.length, 4000); assert.equal(found[0].severity, 'info');
  assert.equal(found[0].message.startsWith('<img src=x>'), true);
});

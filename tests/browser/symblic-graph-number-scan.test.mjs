// Exercise the actual browser scanner without publishing a test-only global.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source = await fs.readFile(new URL('../../web/studio/symblic-graphs.js', import.meta.url), 'utf8');
const start = source.indexOf('  function checkNumberText(raw) {');
const end = source.indexOf('  function checkResponseNumbers', start);
assert.ok(start >= 0 && end > start);
const check = vm.runInNewContext('const NUMBER_GUIDANCE = "numeric refusal";\n' + source.slice(start, end) + '\ncheckNumberText');
const LIMIT = 1048576;
function observed(raw) {
  const reads = {characters:0, lengths:0, slices:[]};
  const value = new Proxy({}, {get(_target, key) {
    if (key === 'length') {reads.lengths++; return raw.length;}
    if (key === 'slice') return (from,to) => {reads.slices.push(to-from); return raw.slice(from,to);};
    if (typeof key === 'string' && key[0] >= '0' && key[0] <= '9') reads.characters++;
    return raw[key];
  }});
  return {value, reads};
}
test('actual number scanner visits escaped unterminated strings with linear access bounds', () => {
  for (const pairs of [1000, 10000, 25000]) {
    const raw = '"' + '\\"'.repeat(pairs), {value, reads} = observed(raw);
    assert.doesNotThrow(() => check(value));
    assert.ok(reads.characters <= raw.length + 4, JSON.stringify(reads));
    assert.ok(reads.lengths <= 2*raw.length + 4, JSON.stringify(reads));
    assert.deepEqual(reads.slices, []);
    assert.throws(() => JSON.parse(raw), SyntaxError);
  }
  // Full caller byte limit; the final backslash is also unterminated. This
  // remains JSON.parse's syntax error, with no regex retries or numeric copies.
  const raw = '"' + '\\"'.repeat((LIMIT-2)/2) + '\\';
  assert.equal(Buffer.byteLength(raw), LIMIT);
  assert.doesNotThrow(() => check(raw));
  assert.throws(() => JSON.parse(raw), SyntaxError);
});
test('actual number scanner preserves quoted data and leaves syntax authority to JSON.parse', () => {
  for (const text of ['9007199254740993', '1e9999', '\\" 9007199254740993', 'é 😀 \n "', '\\']) {
    const raw = JSON.stringify({text, value:42});
    assert.doesNotThrow(() => check(raw));
    assert.equal(JSON.parse(raw).text, text);
  }
  for (const raw of ['{"x":"\\q"}', '"\\', '{"x":-', '[01]', '{"x":1,}']) {
    assert.doesNotThrow(() => check(raw));
    assert.throws(() => JSON.parse(raw), SyntaxError);
  }
  for (const raw of ['["escaped \\\" text",9007199254740993]', '["\\\\",1e0]']) {
    assert.throws(() => check(raw), /numeric refusal/);
  }
});
test('actual number scanner bounds numeric work and preserves safe integer policy', () => {
  for (const token of ['0', '-0', '9007199254740991', '-9007199254740991']) {
    assert.doesNotThrow(() => check('{"value":' + token + '}'));
  }
  for (const token of ['9007199254740992', '-9007199254740992', '9007199254740993', '1.0', '1e0', '-1e9999']) {
    assert.throws(() => check('{"value":' + token + '}'), /numeric refusal/);
  }
  const {value, reads} = observed('9'.repeat(LIMIT));
  assert.throws(() => check(value), /numeric refusal/);
  assert.ok(reads.characters <= 18 && reads.lengths <= 18, JSON.stringify(reads));
  assert.deepEqual(reads.slices, [], 'Huge integers never reach Number or a token allocation');
  const safe = observed('[9007199254740991,-9007199254740991]');
  check(safe.value);
  assert.deepEqual(safe.reads.slices, [16,17]);
});

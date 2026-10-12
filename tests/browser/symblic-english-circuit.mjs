// Source-only circuit projection: no models, network, live stores, or execution.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync(path.join(root, 'web/studio/symblic-english-circuit.js'), 'utf8'), context);
const project = (compiled, source) => JSON.parse(JSON.stringify(context.window.SymblicEnglishCircuit.project(compiled, source)));

export function fixture() {
  const texts = ['Remember base is 7.', 'Remember unused is 50.',
    'Ask for result as a whole number: "Add one to base; the word unused is instruction text.".',
    'Using only base.', 'Accept only if result equals base plus 1.', 'Show result.'];
  const kinds = ['remember', 'remember', 'ask', 'using', 'accept', 'show'];
  const nativeLines = [[2], [3], [4], [4], [5], [6]];
  const statements = texts.map((text, i) => ({index: i + 1, line: i + 1, col: 1, end_line: i + 1,
    end_col: [...text].length, kind: kinds[i], text, native_lines: nativeLines[i],
    ...(['using', 'accept'].includes(kinds[i]) ? {ask: 'result'} : {})}));
  const plan = [{line: 1, kind: 'use', depth: 0}, {line: 2, kind: 'let', depth: 0, binds: 'base'},
    {line: 3, kind: 'let', depth: 0, binds: 'unused'},
    {line: 4, kind: 'ask', depth: 0, binds: 'result', reads: ['base'], type: 'Int'},
    {line: 5, kind: 'ensure', depth: 0, reads: ['base', 'result']},
    {line: 6, kind: 'show', depth: 0, reads: ['result']}];
  return {source: texts.join('\n'), compiled: {statements, check: {ok: true, plan},
    names: {base: 'base', unused: 'unused', result: 'result'},
    source_map: statements.flatMap(row => row.native_lines.map(native_line => ({native_line, statement: row.index, line: row.line, col: 1})))}};
}

test('circuit connects actual parsed reads, preserving every source statement', () => {
  const f = fixture(), p = project(f.compiled, f.source);
  assert.equal(p.available, true); assert.equal(p.nodes.length, 6); assert.deepEqual(p.notes, []);
  assert.deepEqual(p.edges.map(e => [e.from, e.to, e.name]), [[1, 3, 'base'], [1, 5, 'base'], [3, 5, 'result'], [3, 6, 'result']]);
  assert.equal(p.nodes[3].parent, 3); assert.equal(p.nodes[4].parent, 3);
  assert.deepEqual(p.nodes[3].selected.map(e => e.name), ['base']);
  assert.equal(p.nodes[4].checks[0].status, 'not_run');
  assert.equal(p.nodes[2].type, 'Int');
  assert(!p.edges.some(e => e.from === 2), 'mere prompt mention must not become a wire');
});

test('several native rows for a grid output retain one source component and deduplicate reads', () => {
  const f = fixture(), row = f.compiled.statements.at(-1); row.kind = 'display'; row.native_lines.push(7);
  f.compiled.check.plan.at(-1).kind = 'assert';
  f.compiled.check.plan.push({line: 7, kind: 'show', depth: 0, reads: ['result']});
  const p = project(f.compiled, f.source);
  assert.equal(p.nodes.length, 6); assert.equal(p.nodes.at(-1).checks.length, 1);
  assert.equal(p.edges.filter(e => e.to === 6).length, 1);
});

test('source verification accepts CRLF, BOM and astral Unicode without changing code-point columns', () => {
  const f = fixture(), first = f.compiled.statements[0];
  first.text = 'Remember base is "🧱".'; first.end_col = [...first.text].length;
  f.source = '\uFEFF' + [first.text, ...f.source.split('\n').slice(1)].join('\r\n');
  assert.equal(project(f.compiled, f.source).available, true);
});

test('stale source refuses projected wires', () => {
  const f = fixture(), p = project(f.compiled, f.source.replace('base is 7', 'base is 8'));
  assert.equal(p.available, false); assert.deepEqual(p.edges, []); assert.match(p.notes[0], /source changed/);
});

test('failed checks and branching plans cannot masquerade as an English straight-line circuit', () => {
  const f = fixture(); f.compiled.check.ok = false;
  assert.equal(project(f.compiled, f.source).available, false);
  f.compiled.check.ok = true; f.compiled.check.plan[2].depth = 1;
  assert.equal(project(f.compiled, f.source).available, false);
});

test('unresolved inputs stay visible without fabricated producer edges', () => {
  const f = fixture(); f.compiled.check.plan[3].reads.push('missing');
  const p = project(f.compiled, f.source);
  assert.match(p.notes.join(' '), /missing.*no earlier mapped source/);
  assert(!p.edges.some(e => e.name === 'missing'));
});

test('missing and oversized data stays bounded', () => {
  assert.equal(project(null, '').available, false);
  const f = fixture(); f.compiled.statements = Array(401).fill(f.compiled.statements[0]);
  assert.equal(project(f.compiled, f.source).available, false);
});

test('source-map associations recover native lines and do not duplicate shared Ask/Using wires', () => {
  const f = fixture(); for (const row of f.compiled.statements) row.native_lines = [];
  const p = project(f.compiled, f.source);
  assert.equal(p.edges.length, 4); assert.deepEqual(p.nodes[3].selected.map(e => e.name), ['base']);
});

export async function runCircuitJourney(browser, {assetRoot = root, mobile = false, screenshot = null} = {}) {
  const c = await browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1300, height: 900},
    isMobile: mobile, hasTouch: mobile, colorScheme: mobile ? 'dark' : 'light'});
  try {
    const page = await c.newPage(); const errors = [], external = [];
    page.on('pageerror', error => errors.push(String(error)));
    await c.route('**/*', route => { external.push(route.request().url()); return route.abort(); });
    await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><main id="circuit"></main></body></html>');
    await page.addStyleTag({path: path.join(assetRoot, 'web/studio/symblic-english-circuit.css')});
    await page.addStyleTag({content: `:root{--bg1:${mobile ? '#111' : '#faf7f1'};--bg2:${mobile ? '#222' : '#eee'};--tx1:${mobile ? '#eee' : '#222'};--tx2:${mobile ? '#bbb' : '#444'};--tx3:#888;--acc:#e85b2a;--brd:#888;--ctl:#888}body{margin:16px;background:var(--bg1);color:var(--tx1);font:16px/1.5 sans-serif}main{max-width:900px;margin:auto}`});
    await page.addScriptTag({path: path.join(assetRoot, 'web/studio/symblic-english-circuit.js')});
    const f = fixture(), old = f.compiled.statements[2].text;
    const attack = '<img src=x onerror="window.__circuitXss=1">';
    f.compiled.statements[2].text = old.replace('Add one', attack + ' Add one');
    f.compiled.statements[2].end_col = [...f.compiled.statements[2].text].length;
    f.source = f.source.replace(old, f.compiled.statements[2].text);
    await page.evaluate(f => window.SymblicEnglishCircuit.render(document.getElementById('circuit'), {...f,
      onSelectLine: line => { window.__selectedLine = line; }}), f);
    assert.equal(await page.locator('.sy-ec-component').count(), 6);
    assert.equal(await page.locator('img').count(), 0);
    assert.equal(await page.evaluate(() => window.__circuitXss), undefined);
    await page.getByRole('button', {name: 'base ← line 1; select English line 1', exact: true}).first().click();
    assert.equal(await page.evaluate(() => window.__selectedLine), 1);
    const target = page.getByRole('button', {name: 'Line 5; select English line 5', exact: true});
    await target.focus(); await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => window.__selectedLine), 5);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.match(await page.locator('.sy-en-circuit').innerText(), /Parsed connections; checks not run/);
    if (screenshot) await page.screenshot({path: screenshot, fullPage: true});
    await page.evaluate(f => window.SymblicEnglishCircuit.render(document.getElementById('circuit'), {...f,
      source: f.source.replace('base is 7', 'base is 8')}), f);
    assert.equal(await page.locator('.sy-ec-component').count(), 0);
    assert.match(await page.locator('.sy-en-circuit').innerText(), /source changed/);
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    return {mobile, sourceStatements: 6, parsedConnections: 4, xss: false, keyboard: true, overflow: false, networkRequests: 0};
  } finally { await c.close(); }
}

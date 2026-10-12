// Computes the examples of a Kirby sheet (../sheets/*.sheet.md) with the reference (ref-units.mjs), so no expected
// value is typed by hand.
//
//   node kits/kirby/reference/fill-sheet.mjs fill  SHEET.md [OUT.md]   replace every `call ==> ?` with the
//                                                 reference's value (in place when OUT is omitted)
//   node kits/kirby/reference/fill-sheet.mjs check SHEET.md            recompute every example and compare (exit 1
//                                                 on any difference)
//
// Each example runs the way the kernel's js_test runs it (symblic/js/check.py, docs/reference/JS.md): a fresh vm context made from a
// null-prototype object, Math.random throwing, Date fixed at 1700000000000, console a no-op, then the unit's test
// setup and the reference code of every unit up to and including this one, each as its own script, in sheet order,
// and only then the call. A call that reaches a later unit therefore fails here as it would in the build. The tool
// also refuses a sheet whose units do not cover every top-level declaration of the reference in the same order, and
// values the kernel could not compare (NaN, Infinity, functions, undefined inside arrays).
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REF = path.join(HERE, 'ref-units.mjs');
const LIMITS = { cases: 200, call: 4000, expected: 200000, source: 400000 };

// ------------------------------------------------------- the sheet, parsed like symblic.spec.sheets.parse()
export function parseSheet(text) {
  const out = { title: '', intro: [], shared: [], units: [], template: null, directives: {} };
  let section = 'intro', current = null;
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    let m = /^# (.+?)\s*$/.exec(line);
    if (m && !out.title) { out.title = m[1].trim(); continue; }
    m = /^(Answers normalized|Used units shown as):\s*(\S+)\s*$/.exec(line);
    if (m && (section === 'intro' || section === 'shared')) { out.directives[m[1]] = m[2]; continue; }
    m = /^## (Shared|Unit `([^`]+)`|Assemble `([^`]+)`)\s*$/.exec(line);
    if (m) {
      if (m[1] === 'Shared') { section = 'shared'; current = null; }
      else if (m[2]) {
        const names = m[2].split(/,\s*(?![^()]*\))/).map((p) => /^\s*([A-Za-z_$][\w$]*)/.exec(p)[1]);
        current = { heading: m[2], names, lines: [] };
        out.units.push(current); section = 'unit';
      } else {
        current = { file: m[3], lines: [] }; out.template = current; section = 'assemble';
      }
      continue;
    }
    if (line.startsWith('## ')) throw new Error('unknown section: ' + line);
    if (section === 'intro' || section === 'shared') out[section].push(line); else current.lines.push(line);
  }
  for (const u of out.units) Object.assign(u, splitUnit(u.lines));
  return out;
}

function splitUnit(lines) {
  const body = [], setup = [], examples = [], uses = [];
  let mode = 'body';
  for (const line of lines) {
    const s = line.trim();
    if (s.startsWith('Uses:')) { uses.push(...[...s.matchAll(/`([^`]+)`/g)].map((x) => x[1])); continue; }
    if (s === 'Test setup:') { mode = 'setup'; continue; }
    if (s === 'Examples:') { mode = 'examples'; continue; }
    if (mode === 'setup') {
      if (line.startsWith('    ') || !s) { setup.push(line.startsWith('    ') ? line.slice(4) : ''); continue; }
      mode = 'body';
    }
    if (mode === 'examples') {
      if (line.startsWith('    ') && line.includes('==>')) {
        const at = line.lastIndexOf('==>');
        examples.push([line.slice(4, at).trim(), line.slice(at + 3).trim()]);
        continue;
      }
      if (!s) continue;
      mode = 'body';
    }
    body.push(line);
  }
  return { body: body.join('\n').trim(), setup: setup.join('\n').trim(), examples, uses };
}

// ------------------------------------------------------------------ the reference, cut into top-level declarations
export function referenceDeclarations(file = REF) {
  const src = fs.readFileSync(file, 'utf8');
  const decls = new Map();
  let name = null, cur = [];
  const flush = () => { if (name) decls.set(name, cur.join('\n').replace(/\s+$/, '')); };
  for (const line of src.split('\n')) {
    const m = /^export (?:function\s+([A-Za-z_$][\w$]*)|const\s+([A-Za-z_$][\w$]*))/.exec(line);
    if (m) { flush(); name = m[1] || m[2]; cur = [line.slice('export '.length)]; continue; }
    if (name) {
      if (/^\/\//.test(line)) { flush(); name = null; cur = []; continue; }   // a comment between declarations
      cur.push(line);
    }
  }
  flush();
  return decls;
}

export function unitSources(sheet, decls) {
  const order = [...decls.keys()];
  const named = sheet.units.flatMap((u) => u.names);
  if (JSON.stringify(named) !== JSON.stringify(order)) {
    throw new Error(`the sheet's unit names differ from the reference's declarations:\n sheet ${named.join(',')}\n ref   ${order.join(',')}`);
  }
  return sheet.units.map((u) => u.names.map((n) => decls.get(n)).join('\n\n'));
}

// ------------------------------------------------------------------ running one example as the kernel would
const PRELUDE = `
  (function () {
    const fixed = 1700000000000;
    Math.random = function () { throw new Error('Math.random is not available in a deterministic check'); };
    const RealDate = Date;
    globalThis.Date = class extends RealDate {
      constructor(...a) { if (a.length) super(...a); else super(fixed); }
      static now() { return fixed; }
    };
    globalThis.console = { log() {}, warn() {}, error() {}, info() {}, debug() {} };
  })();`;

function plainJson(value, where) {
  const bad = [];
  const walk = (v, p) => {
    if (typeof v === 'number' && !Number.isFinite(v)) bad.push(`${p} is ${v}`);
    else if (typeof v === 'function' || typeof v === 'symbol' || typeof v === 'bigint') bad.push(`${p} is a ${typeof v}`);
    else if (Array.isArray(v)) v.forEach((x, i) => (x === undefined ? bad.push(`${p}[${i}] is undefined`) : walk(x, `${p}[${i}]`)));
    else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) if (x !== undefined) walk(x, `${p}.${k}`);
  };
  walk(value, 'value');
  if (bad.length) throw new Error(`${where}: the kernel cannot compare this value (${bad.slice(0, 3).join('; ')})`);
}

export function evaluate(pieces, call, timeout = 3000) {
  const ctx = vm.createContext(Object.create(null), { codeGeneration: { strings: false, wasm: false } });
  vm.runInContext(PRELUDE, ctx, { timeout });
  pieces.forEach((p, i) => vm.runInContext(p, ctx, { timeout, filename: `piece${i}.js` }));
  // the value is serialized inside the context, so its own JSON (not the host's) decides what comes back
  const holder = vm.runInContext(`(function () { const v = (${call}\n); return { v, s: JSON.stringify(v === undefined ? null : v) }; })()`,
    ctx, { timeout, filename: 'case.js' });
  plainJson(holder.v, call.slice(0, 80));
  if (typeof holder.s !== 'string') throw new Error('the result is not JSON: ' + call.slice(0, 80));
  return holder.s;
}

// the kernel compares parsed JSON: objects by key regardless of order, arrays in order, numbers by value
export function sameJson(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => sameJson(x, b[i]));
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    return sameJson(ka, kb) && ka.every((k) => sameJson(a[k], b[k]));
  }
  return a === b;
}

export function runSheet(text, { fill = false } = {}) {
  const sheet = parseSheet(text);
  const sources = unitSources(sheet, referenceDeclarations());
  const values = new Map();
  let total = 0, bad = 0;
  const report = [];
  sheet.units.forEach((u, i) => {
    if (!u.examples.length) throw new Error(`unit ${u.heading} has no examples`);
    if (u.examples.length > LIMITS.cases) throw new Error(`unit ${u.heading} has too many examples`);
    const pieces = (u.setup ? [u.setup] : []).concat(sources.slice(0, i + 1));
    if (pieces.join('\n').length > LIMITS.source) throw new Error(`unit ${u.heading}: source too long`);
    for (const [call, expect] of u.examples) {
      if (call.length > LIMITS.call) throw new Error(`unit ${u.heading}: call longer than ${LIMITS.call}: ${call.slice(0, 60)}`);
      let got;
      try { got = evaluate(pieces, call); } catch (e) { throw new Error(`unit ${u.heading}: the reference fails on ${call}\n  ${e.message}`); }
      if (got.length > LIMITS.expected) throw new Error(`unit ${u.heading}: expected value too long for ${call.slice(0, 60)}`);
      total++;
      values.set(`${i}\u0000${call}`, got);
      if (expect !== '?') {
        let ok = false;
        try { ok = sameJson(JSON.parse(expect), JSON.parse(got)); } catch (_) { ok = false; }
        if (!ok) { bad++; report.push(`FAIL ${u.heading}\n  ${call}\n  sheet ${expect.slice(0, 300)}\n  ref   ${got.slice(0, 300)}`); }
      }
    }
  });
  let filled = null;
  if (fill) {
    const lines = text.split('\n');
    let unit = -1;
    filled = lines.map((line) => {
      if (/^## Unit `/.test(line)) unit++;
      if (unit >= 0 && line.startsWith('    ') && /==>\s*\?\s*$/.test(line)) {
        const at = line.lastIndexOf('==>');
        const call = line.slice(4, at).trim();
        const v = values.get(`${unit}\u0000${call}`);
        if (v === undefined) throw new Error('no value computed for ' + call);
        return line.slice(0, at) + '==> ' + v;
      }
      return line;
    }).join('\n');
  }
  return { sheet, total, bad, report, filled };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [cmd, sheetPath, outPath] = process.argv.slice(2);
  if (!['fill', 'check'].includes(cmd) || !sheetPath) {
    console.error('usage: node fill-sheet.mjs fill|check SHEET.md [OUT.md]');
    process.exit(2);
  }
  const text = fs.readFileSync(sheetPath, 'utf8');
  const r = runSheet(text, { fill: cmd === 'fill' });
  for (const line of r.report) console.log(line);
  const pending = r.sheet.units.reduce((n, u) => n + u.examples.filter(([, e]) => e === '?').length, 0);
  if (cmd === 'fill') {
    fs.writeFileSync(outPath || sheetPath, r.filled);
    console.log(`filled ${pending} examples; ${r.sheet.units.length} units, ${r.total} examples, ${r.bad} differing from the reference -> ${outPath || sheetPath}`);
  } else {
    console.log(`${r.sheet.units.length} units, ${r.total} examples, ${r.bad} differing from the reference, ${pending} unfilled`);
  }
  process.exit(r.bad || (cmd === 'check' && pending) ? 1 : 0);
}

// Strict conformance harness for a built kirby.html (../sheets/kirby.sheet.md), in node alone: no browser, no DOM
// library.
//
//   node kits/kirby/harness/harness.mjs path/to/kirby.html [out.json]
//
// The page's inline script runs in a fresh vm context with a minimal fake document, a recording 2D canvas context
// and a manual requestAnimationFrame. The harness drives the page only through what the sheet specifies: the
// window.kirby test API (reset, input, tick, state), keyboard events on document, animation frames, and, for the
// white-box checks, the units' own top-level names. Every scripted or random input sequence is replayed on the
// page and on the reference (../reference/ref-units.mjs) and the states are compared after every action; the rules
// of the feature contract (../README.md) are also checked on the page's own states with their numbers, so a check does not
// pass merely because the reference agrees with itself. Prints one line per check and "required N/N"; exits 0 only
// when every required check passes.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import * as R from '../reference/ref-units.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
if (!argv[0]) { console.error('usage: node harness.mjs path/to/kirby.html [out.json]'); process.exit(2); }
const file = path.resolve(argv[0]);
const outPath = argv[1] || '';
const results = [];
const record = (name, pass, detail = '') => {
  results.push({ name, pass: !!pass, detail: String(detail).slice(0, 1500) });
};
const check = (name, fn) => {
  try {
    const r = fn();
    if (r === true || r === false) record(name, r);
    else record(name, r && r.pass, r && r.detail);
  } catch (e) {
    record(name, false, (e && e.message) || String(e));
  }
};

// ------------------------------------------------------------------------------------------- independent constants
// The level and the numbers below are the feature contract's (README.md), written here again on purpose: the
// property checks use them, not the reference.
const LEVEL = [
  '................................................................',
  '................................................................',
  '.............................................*..................',
  '..........................................B.....................',
  '.........................***....................................',
  '........................=====...................................',
  '................................................................',
  '...............**..................W............................',
  '..............====...............######.....B...................',
  '....***..#..W.....W........^^....######.............W...**...D..',
  '####################....#######################..###############',
  '####################....#######################..###############',
];
const C = {
  start: { x: 40, y: 296 }, accel: 0.125, friction: 0.25, maxWalk: 2, gravity: 0.25, maxFall: 6, jump: 6,
  jumpRise: 69, wingRise: 140.25, flap: 2, floatGravity: 0.0625, floatMaxFall: 1, floatLimit: 360, hurtSteps: 90,
  knockVx: 2, knockVy: 3, hp: 6, star: 100, enemy: 200, shotSpeed: 6, waddleSpeed: 0.5, inhaleRange: 64, pull: 2,
  camMax: 2048 - 640,
};
const SNAP_KEYS = ['cam', 'enemies', 'frame', 'kirby', 'over', 'score', 'shot', 'stars', 'won'];
const KIRBY_KEYS = ['ability', 'face', 'floatT', 'floating', 'full', 'ground', 'hp', 'hurtT', 'inhaling', 'vx', 'vy', 'x', 'y'];
const ENEMY_KEYS = ['alive', 'dir', 'kind', 't', 'x', 'y'];

// ------------------------------------------------------------------------------------------------ static checks
const html = fs.readFileSync(file, 'utf8');
record('file size is plausible', html.length > 5000 && html.length < 400000, `${html.length} characters`);
{
  const urls = (html.match(/https?:\/\/[^\s"'<>)]+/g) || []).filter((u) => !u.startsWith('http://www.w3.org/'));
  const remote = /<(script|link|img|iframe)[^>]+(src|href)\s*=/i.test(html);
  record('no external URL or remote resource', urls.length === 0 && !remote, urls.slice(0, 5).join(' '));
}
record('a 640 x 384 canvas with id "game"', /<canvas[^>]*id="game"[^>]*width="640"[^>]*height="384"/.test(html) ||
  /<canvas[^>]*width="640"[^>]*height="384"[^>]*id="game"/.test(html), (html.match(/<canvas[^>]*>/) || ['no canvas'])[0]);
const scripts = [...html.matchAll(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi)].filter((m) => !/\bsrc\s*=/.test(m[1] || ''));
const script = scripts.map((m) => m[2]).join('\n;\n');
record('one inline script that calls startGame()', scripts.length === 1 && /\bstartGame\s*\(\s*\)\s*;?\s*$/.test(script.trim()),
  `${scripts.length} inline script(s)`);

// ------------------------------------------------------------------------------------------- the fake page
const PRELUDE = String.raw`
var window = globalThis;
var self = globalThis;
var __stringify = JSON.stringify.bind(JSON);
var __h = { frames: [], listeners: { document: {}, window: {} }, calls: [], errors: [], els: {}, now: 0 };
function __ctx2d() {
  const ctx = { fillStyle: '#000000', strokeStyle: '#000000', lineWidth: 1, font: '10px sans-serif', textAlign: 'start',
    textBaseline: 'alphabetic', globalAlpha: 1, lineCap: 'butt', lineJoin: 'miter', imageSmoothingEnabled: true };
  for (const m of ['fillRect', 'strokeRect', 'clearRect', 'fillText', 'strokeText', 'beginPath', 'closePath', 'moveTo',
    'lineTo', 'arc', 'arcTo', 'ellipse', 'rect', 'quadraticCurveTo', 'bezierCurveTo', 'fill', 'stroke', 'save', 'restore',
    'translate', 'scale', 'rotate', 'setTransform', 'resetTransform', 'transform', 'clip', 'drawImage', 'setLineDash']) {
    ctx[m] = function (...a) { __h.calls.push([m, ctx.fillStyle, ctx.font, ctx.textAlign, ...a]); };
  }
  ctx.measureText = (s) => ({ width: String(s).length * 8 });
  ctx.createLinearGradient = ctx.createRadialGradient = () => ({ addColorStop() {} });
  return ctx;
}
function __el(id, tag) {
  return { id, tagName: tag, width: tag === 'CANVAS' ? 640 : 0, height: tag === 'CANVAS' ? 384 : 0, style: {},
    getContext(kind) { if (kind !== '2d') return null; return (this.__c = this.__c || __ctx2d()); },
    addEventListener() {}, removeEventListener() {}, focus() {}, blur() {}, setAttribute() {}, getAttribute() { return null; },
    appendChild(c) { return c; }, classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    getBoundingClientRect() { return { left: 0, top: 0, width: 640, height: 384 }; }, textContent: '', innerText: '' };
}
var document = {
  readyState: 'complete', hidden: false,
  body: __el('body', 'BODY'), documentElement: __el('html', 'HTML'),
  getElementById(id) { if (!__h.els[id]) __h.els[id] = __el(id, id === 'game' ? 'CANVAS' : 'DIV'); return __h.els[id]; },
  querySelector(s) { s = String(s); return s === 'canvas' || s === '#game' || s === 'canvas#game' ? this.getElementById('game') : null; },
  querySelectorAll(s) { const e = this.querySelector(s); return e ? [e] : []; },
  createElement(tag) { return __el('', String(tag).toUpperCase()); },
  addEventListener(type, fn) { (__h.listeners.document[type] = __h.listeners.document[type] || []).push(fn); },
  removeEventListener(type, fn) { const l = __h.listeners.document[type] || []; const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); },
};
window.addEventListener = function (type, fn) { (__h.listeners.window[type] = __h.listeners.window[type] || []).push(fn); };
window.removeEventListener = function (type, fn) { const l = __h.listeners.window[type] || []; const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); };
window.innerWidth = 1280; window.innerHeight = 800; window.devicePixelRatio = 1;
function requestAnimationFrame(fn) { __h.frames.push(fn); return __h.frames.length; }
function cancelAnimationFrame() {}
var performance = { now() { return __h.now; } };
function setTimeout() { return 0; } function clearTimeout() {} function setInterval() { return 0; } function clearInterval() {}
var console = { log() {}, info() {}, warn() {}, debug() {}, error(...a) { __h.errors.push('console.error: ' + a.join(' ')); } };
function __key(type, key, o) {
  const e = Object.assign({ type, key, code: '', repeat: false, ctrlKey: false, altKey: false, metaKey: false, shiftKey: false,
    defaultPrevented: false, target: document.body }, o || {});
  e.preventDefault = function () { e.defaultPrevented = true; };
  e.stopPropagation = function () {}; e.stopImmediatePropagation = function () {};
  for (const scope of ['document', 'window']) {
    for (const f of (__h.listeners[scope][type] || []).slice()) {
      try { f.call(scope === 'document' ? document : window, e); } catch (err) { __h.errors.push(type + ' listener: ' + ((err && err.stack) || err)); }
    }
  }
  return e.defaultPrevented;
}
function __frame(t) {
  __h.now = t;
  const fs = __h.frames; __h.frames = [];
  for (const f of fs) { try { f(t); } catch (err) { __h.errors.push('animation frame: ' + ((err && err.stack) || err)); } }
}
function __apply(a) {
  if (a[0] === 'in') window.kirby.input(a[1], a[2]);
  else if (a[0] === 't') window.kirby.tick(a[1]);
  else if (a[0] === 'key') __key(a[1], a[2], a[3]);
  else if (a[0] === 'frame') __frame(a[1]);
}
function __run(seed, acts) {
  const out = [];
  try {
    window.kirby.reset(seed);
    out.push(__stringify(window.kirby.state()));
    for (let i = 0; i < acts.length; i++) { __apply(acts[i]); out.push(__stringify(window.kirby.state())); }
    return '{"states":[' + out.join(',') + ']}';
  } catch (err) {
    return __stringify({ states: out.map((s) => JSON.parse(s)), error: String((err && err.stack) || err), at: out.length - 1 });
  }
}
`;

class Page {
  constructor(source) {
    this.ctx = vm.createContext(Object.create(null), { codeGeneration: { strings: false, wasm: false } });
    vm.runInContext(PRELUDE, this.ctx, { filename: 'harness-prelude.js' });
    this.loadError = null;
    try {
      vm.runInContext(source, this.ctx, { timeout: 20000, filename: 'kirby.html#script' });
    } catch (e) {
      this.loadError = String((e && e.stack) || e);
    }
  }
  eval(expr, timeout = 30000) { return vm.runInContext(expr, this.ctx, { timeout }); }
  json(expr, timeout = 30000) {
    const s = this.eval(`__stringify((${expr}))`, timeout);
    return s === undefined ? undefined : JSON.parse(s);
  }
  errors() { return this.json('__h.errors'); }
  run(seed, acts) {
    const out = JSON.parse(this.eval(`__run(${JSON.stringify(seed)}, ${JSON.stringify(acts)})`, 120000));
    if (out.error) throw new Error(`the page threw after action ${out.at}: ${out.error.split('\n').slice(0, 2).join(' ')}`);
    return out.states;
  }
  calls() { return this.json('__h.calls'); }
  clearCalls() { this.eval('__h.calls = []'); }
}

// --------------------------------------------------------------------------------------------- the reference side
function refKey(g, type, key, o) {
  const e = Object.assign({ key, repeat: false, ctrlKey: false, altKey: false, metaKey: false }, o || {});
  e.preventDefault = () => {};
  if (type !== 'keydown' && type !== 'keyup') return g;
  return R.handleKey(g, e, type === 'keydown') ? null : g;    // a restart has a clock seed: never compared
}
function refRun(seed, acts) {
  const g = R.newGame(seed);
  const out = [R.snapshot(g)];
  let testMode = true, last = null;
  for (const a of acts) {
    if (a[0] === 'in') R.input(g, a[1], a[2]);
    else if (a[0] === 't') R.tick(g, a[1]);
    else if (a[0] === 'key') { if (refKey(g, a[1], a[2], a[3]) === null) throw new Error('restart in a compared run'); }
    else if (a[0] === 'frame') { if (last === null) last = a[1]; const ms = Math.min(100, Math.max(0, a[1] - last)); last = a[1]; if (!testMode && ms > 0) R.tick(g, ms); }
    out.push(R.snapshot(g));
  }
  return out;
}
// the reference's units as plain scripts in their own context: the same expression runs on the page and here
const REF_CTX = (() => {
  const src = fs.readFileSync(path.join(HERE, '..', 'reference', 'ref-units.mjs'), 'utf8').replace(/^export /gm, '');
  const ctx = vm.createContext(Object.create(null));
  vm.runInContext('var __stringify = JSON.stringify.bind(JSON);\n' + src, ctx, { filename: 'ref-units.js' });
  return ctx;
})();
function both(expr) {
  const got = page.json(expr);
  const want = JSON.parse(vm.runInContext(`__stringify((${expr}))`, REF_CTX, { timeout: 30000 }));
  return { got, want, same: same(got, want) };
}
function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])]));
  return v;
}
const same = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
function diffState(a, b) {
  const out = [];
  const walk = (x, y, p) => {
    if (out.length > 4) return;
    if (x && y && typeof x === 'object' && typeof y === 'object') {
      for (const k of new Set([...Object.keys(x), ...Object.keys(y)])) walk(x[k], y[k], p ? `${p}.${k}` : k);
    } else if (JSON.stringify(x) !== JSON.stringify(y)) out.push(`${p}: got ${JSON.stringify(x)} want ${JSON.stringify(y)}`);
  };
  walk(a, b, '');
  return out.join('; ');
}
const seen = [];          // every page state the harness saw, for the invariant checks at the end
const runFaults = [];     // within one run: frames never go back, stars never come back, score and HP never undo
function compare(page, seed, acts) {
  const got = page.run(seed, acts);
  const want = refRun(seed, acts);
  seen.push(...got);
  for (let i = 1; i < got.length && runFaults.length < 5; i++) {
    const a = got[i - 1], b = got[i];
    if (b.frame < a.frame || b.stars > a.stars || b.score < a.score || b.kirby.hp > a.kirby.hp) {
      runFaults.push(`seed ${seed} action ${i}: frame ${a.frame}->${b.frame} stars ${a.stars}->${b.stars} score ${a.score}->${b.score} hp ${a.kirby.hp}->${b.kirby.hp}`);
    }
  }
  for (let i = 0; i < want.length; i++) {
    if (!same(got[i], want[i])) {
      return { got, want, pass: false, detail: `differs from the reference at action ${i} (${i ? JSON.stringify(acts[i - 1]) : 'reset'}): ${diffState(got[i], want[i])}` };
    }
  }
  return { got, want, pass: true, detail: `${acts.length} actions, ${want[want.length - 1].frame} steps` };
}

// scenario recorder: drives the reference and records the actions, so the page can replay them
class Rec {
  constructor(seed) { this.seed = seed; this.g = R.newGame(seed); this.acts = []; }
  in(a, p = true) { this.acts.push(['in', a, p]); R.input(this.g, a, p); return this; }
  t(ms) { this.acts.push(['t', ms]); R.tick(this.g, ms); return this; }
  step(n = 1) { for (let i = 0; i < n; i++) this.t(Math.ceil((1000 - this.g.acc) / 60)); return this; }    // exactly one step
  until(pred, max, what) {
    for (let n = 0; n < max; n++) { if (pred(this.g)) return this; this.step(); }
    if (pred(this.g)) return this;
    const k = this.g.kirby;
    throw new Error(`harness scenario (seed ${this.seed}) did not reach "${what}" on the reference (x ${k.x}, y ${k.y}, hp ${k.hp}, over ${this.g.over})`);
  }
  get k() { return this.g.kirby; }
}
// a simple player on the reference: holds right, jumps at walls, spikes, pits and enemies, flaps over gaps
function travel(r, stop, max = 4000) {
  r.in('right', true);
  let lastFlap = -100;
  for (let i = 0; i < max; i++) {
    const g = r.g, k = g.kirby;
    if (stop(g) || g.over || g.won) return r;
    const ahead = (dx, row) => R.tileAt(g, row, Math.floor((k.x + 12 + dx) / 32));
    const enemyNear = g.enemies.some((e) => e.alive && e.x - k.x > 0 && e.x - k.x < 70 && Math.abs(e.y - k.y) < 40);
    if (k.ground) {
      const wall = ahead(28, 9) === '#' || ahead(28, Math.floor(k.y / 32)) === '#';
      const spike = ahead(40, 9) === '^' || ahead(24, 9) === '^';
      const pit = !R.standAt(g, 10, Math.floor((k.x + 42) / 32)) && k.y >= 296;
      if (k.x < 1880 && (wall || spike || pit || enemyNear)) r.in('jump', true);
    } else {
      const below = [10, 11].some((row) => R.standAt(g, row, Math.floor((k.x + 12) / 32)) || R.standAt(g, row, Math.floor((k.x + 30) / 32)));
      if (k.vy > 0.5 && (!below || ahead(20, 9) === '^' || enemyNear) && g.frame - lastFlap > 12) { r.in('jump', true); lastFlap = g.frame; }
    }
    r.step();
  }
  throw new Error('harness travel did not reach its condition on the reference');
}
const minOf = (xs) => xs.reduce((a, b) => Math.min(a, b), Infinity);
const maxOf = (xs) => xs.reduce((a, b) => Math.max(a, b), -Infinity);

// ------------------------------------------------------------------------------------------------ load the page
const page = new Page(script);
record('the script runs and calls startGame() without an error', !page.loadError && page.errors().length === 0,
  page.loadError || page.errors().join(' | '));
const hasApi = !page.loadError && page.eval(`typeof window.kirby === 'object' && window.kirby !== null &&
  ['reset', 'input', 'tick', 'state'].every((k) => typeof window.kirby[k] === 'function')`);
record('window.kirby has reset, input, tick and state', hasApi);
if (!hasApi) finish();

// ------------------------------------------------------------------------------------------------ real time
check('the first paint fills the 640 x 384 sky and a frame is requested', () => {
  const calls = page.calls();
  const sky = calls.find((c) => c[0] === 'fillRect');
  const frames = page.json('__h.frames.length');
  return { pass: !!sky && sky[1] === '#87ceeb' && sky.slice(4, 8).join() === '0,0,640,384' && frames >= 1, detail: JSON.stringify({ sky, frames }) };
});
check('real time: animation frames advance the game before any reset (60 steps per second, 100 ms cap)', () => {
  const f0 = page.json('window.kirby.state().frame');
  const times = [1000];
  for (let i = 1; i <= 120; i++) times.push(1000 + i * (1000 / 60));
  times.push(times[times.length - 1] + 1000);                 // a 1 s stall counts as 100 ms
  for (const t of times) page.eval(`__frame(${t})`);
  const f1 = page.json('window.kirby.state().frame');
  // the same arithmetic on the reference's tick
  const g = R.newGame(1); let last = null;
  for (const t of times) { if (last === null) last = t; const ms = Math.min(100, Math.max(0, t - last)); last = t; if (ms > 0) R.tick(g, ms); }
  return { pass: f1 - f0 === g.frame && g.frame >= 125 && g.frame <= 126, detail: `page stepped ${f1 - f0}, reference ${g.frame}` };
});
check('after reset(seed) animation frames no longer move the game (test mode)', () => {
  page.eval('window.kirby.reset(3)');
  for (let i = 0; i < 30; i++) page.eval(`__frame(${5000 + i * 17})`);
  const s = page.json('window.kirby.state()');
  return { pass: s.frame === 0 && s.kirby.x === C.start.x, detail: `frame ${s.frame}` };
});

// ------------------------------------------------------------------------------------------------ state shape
check('state() has exactly the specified fields', () => {
  page.eval('window.kirby.reset(1)');
  const s = page.json('window.kirby.state()');
  const ok = same(Object.keys(s).sort(), SNAP_KEYS) && same(Object.keys(s.kirby).sort(), KIRBY_KEYS) &&
    s.enemies.every((e) => same(Object.keys(e).sort(), ENEMY_KEYS)) && s.shot === null;
  return { pass: ok, detail: JSON.stringify(s).slice(0, 600) };
});
check('state() returns a new copy each call', () => {
  const r = page.json(`(() => {
    window.kirby.reset(1); const a = window.kirby.state(); const snap = __stringify(a);
    a.kirby.x = 999; a.enemies[0].x = 999; a.enemies.push({}); a.score = 77;
    const leaked = __stringify(window.kirby.state()) !== snap;
    const held = window.kirby.state(); const heldSnap = __stringify(held);
    window.kirby.input('right', true); window.kirby.tick(500);
    return { leaked, aliased: __stringify(held) !== heldSnap };
  })()`);
  return { pass: !r.leaked && !r.aliased, detail: JSON.stringify(r) };
});

// ------------------------------------------------------------------------------------------------ the level
check('LEVEL is the specified 12 x 64 level, character for character', () => {
  const got = page.json('LEVEL');
  return { pass: same(got, LEVEL), detail: Array.isArray(got) ? got.map((r, i) => (r === LEVEL[i] ? '' : `row ${i}`)).filter(Boolean).join(' ') : typeof got };
});
check('newGame parses the level: W/B become enemies (row by row), their tiles become air', () => {
  const g = page.json('(() => { const g = newGame(1); return { tiles: g.tiles.map((r) => r.join("")), enemies: g.enemies }; })()');
  const wantTiles = LEVEL.map((r) => r.replace(/[WB]/g, '.'));
  const wantEnemies = [];
  LEVEL.forEach((row, r) => [...row].forEach((ch, c) => { if (ch === 'W' || ch === 'B') wantEnemies.push({ kind: ch, x: c * 32 + 4, y: r * 32 + 8, baseY: r * 32 + 8 }); }));
  const shape = g.enemies.map((e) => ({ kind: e.kind, x: e.x, y: e.y, baseY: e.baseY }));
  const dirs = g.enemies.every((e) => (e.dir === 1 || e.dir === -1) && Number.isInteger(e.t) && e.t >= 0 && e.t < 64 && e.alive === true);
  return { pass: same(g.tiles, wantTiles) && same(shape, wantEnemies) && dirs, detail: JSON.stringify(shape).slice(0, 400) };
});
check('the seed decides each enemy\'s direction and phase exactly as the reference (seeds 1-40)', () => {
  const bad = [];
  for (let seed = 1; seed <= 40; seed++) {
    const got = page.json(`window.kirby.reset(${seed}), window.kirby.state()`);
    if (!same(got, R.snapshot(R.newGame(seed)))) bad.push(seed);
  }
  const differ = !same(R.snapshot(R.newGame(1)).enemies, R.snapshot(R.newGame(2)).enemies);
  return { pass: bad.length === 0 && differ, detail: bad.length ? `differs for seeds ${bad.join(',')}` : '40 seeds' };
});
check('the start: Kirby at (40, 296) on the ground with 6 HP, 11 stars, score 0, camera 0', () => {
  const s = page.json('window.kirby.reset(9), window.kirby.state()');
  const k = s.kirby;
  return { pass: k.x === 40 && k.y === 296 && k.ground === true && k.hp === 6 && k.face === 1 && k.ability === 'none' &&
    k.full === null && s.stars === 11 && s.score === 0 && s.cam === 0 && s.frame === 0 && !s.over && !s.won, detail: JSON.stringify(s.kirby) };
});

// ------------------------------------------------------------------------------------------------ walking
let scen;
check('walking right: +0.125 per step up to 2, three stars collected, stopped by the wall at x 264', () => {
  const r = new Rec(1).in('right', true);
  r.until((g) => g.kirby.x === 264 && g.kirby.vx === 0, 400, 'the wall');
  r.step(20);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const vx = c.got.slice(2, 22).map((s) => s.kirby.vx);
  const ramp = vx.every((v, i) => v === Math.min(C.maxWalk, C.accel * (i + 1)));
  const end = c.got[c.got.length - 1];
  return { pass: ramp && end.kirby.x === 264 && end.kirby.vx === 0 && end.score === 300 && end.stars === 8 && end.kirby.face === 1,
    detail: JSON.stringify({ ramp, x: end.kirby.x, score: end.score, stars: end.stars }) };
});
check('friction: released, the speed falls by 0.25 per step to 0', () => {
  const r = new Rec(2).in('right', true).step(30).in('right', false).step(12);
  const c = compare(page, 2, r.acts);
  if (!c.pass) return c;
  const after = c.got.slice(c.got.length - 12).map((s) => s.kirby.vx);
  const ok = after.every((v, i) => v === Math.max(0, C.maxWalk - C.friction * (i + 1)));
  return { pass: ok, detail: after.join(',') };
});
check('walking left turns Kirby (face -1) and the level\'s left edge is a wall (x stops at 0)', () => {
  const r = new Rec(3).in('left', true).step(80);
  const c = compare(page, 3, r.acts);
  if (!c.pass) return c;
  const end = c.got[c.got.length - 1].kirby;
  return { pass: end.face === -1 && end.x === 0 && end.vx === 0 && minOf(c.got.map((s) => s.kirby.x)) === 0, detail: JSON.stringify(end) };
});
check('stars count once: walking back and forth over them keeps 300 and 8 left', () => {
  const r = new Rec(4).in('right', true).step(70).in('right', false).in('left', true).step(70).in('left', false).in('right', true).step(70);
  const c = compare(page, 4, r.acts);
  if (!c.pass) return c;
  const scores = c.got.map((s) => s.score);
  return { pass: c.got[c.got.length - 1].score === 300 && c.got[c.got.length - 1].stars === 8 && maxOf(scores) === 300,
    detail: `score ${c.got[c.got.length - 1].score}, stars ${c.got[c.got.length - 1].stars}` };
});

// ------------------------------------------------------------------------------------------------ jumping
check('jump: rises exactly 69 px, lands back on the ground after 48 steps', () => {
  const r = new Rec(5).in('jump', true).step(60);
  const c = compare(page, 5, r.acts);
  if (!c.pass) return c;
  const ys = c.got.map((s) => s.kirby.y);
  const landedAt = c.got.findIndex((s, i) => i > 2 && s.kirby.ground);
  return { pass: C.start.y - minOf(ys) === C.jumpRise && c.got[1].kirby.vy === -C.jump && landedAt === 49 && ys[ys.length - 1] === 296,
    detail: `rise ${C.start.y - minOf(ys)}, landed at state ${landedAt}` };
});
check('one-way platform: Kirby jumps up through "=" and lands on it (y 232)', () => {
  const r = new Rec(1).in('right', true);
  r.until((g) => g.kirby.x >= 200, 400, 'x 200').in('jump', true);
  r.until((g) => g.kirby.ground && g.kirby.x > 320, 400, 'past the wall');
  r.until((g) => g.kirby.x >= 440, 400, 'under the platform').in('jump', true);
  r.until((g) => g.kirby.ground, 100, 'landing');
  r.in('right', false).step(30);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const end = c.got[c.got.length - 1];
  const passedUp = c.got.some((s) => s.kirby.vy < 0 && s.kirby.y < 256 && s.kirby.y > 200);
  return { pass: end.kirby.y === 232 && end.kirby.ground && passedUp, detail: JSON.stringify({ y: end.kirby.y, ground: end.kirby.ground, score: end.score }) };
});
check('the top of the level is a ceiling: floating up stops at y 0', () => {
  const r = new Rec(6).in('jump', true);
  for (let i = 0; i < 40; i++) r.step(7).in('jump', true);
  r.step(5);
  const c = compare(page, 6, r.acts);
  if (!c.pass) return c;
  const ys = c.got.map((s) => s.kirby.y);
  return { pass: minOf(ys) === 0 && ys.every((y) => y >= 0), detail: `min y ${minOf(ys)}` };
});

// ------------------------------------------------------------------------------------------------ floating
check('float: a jump press in the air inflates and flaps (vy -2); floating falls at most 1 px per step', () => {
  const r = new Rec(7).in('jump', true).step(30).in('jump', true).step(60);
  const c = compare(page, 7, r.acts);
  if (!c.pass) return c;
  const flap = c.got[32];
  const floating = c.got.slice(33).filter((s) => s.kirby.floating);
  const slow = floating.every((s) => s.kirby.vy <= C.floatMaxFall);
  const steps = floating.slice(1).every((s, i) => s.kirby.vy === Math.min(C.floatMaxFall, floating[i].kirby.vy + C.floatGravity) || s.kirby.ground);
  return { pass: flap.kirby.floating && flap.kirby.vy === -C.flap && floating.length > 50 && slow && steps,
    detail: JSON.stringify({ flapVy: flap.kirby.vy, floatingStates: floating.length, maxVy: maxOf(floating.map((s) => s.kirby.vy)) }) };
});
check('float: repeated flaps give lift (Kirby climbs while flapping)', () => {
  const r = new Rec(8).in('jump', true).step(20);
  for (let i = 0; i < 6; i++) r.in('jump', true).step(10);
  const c = compare(page, 8, r.acts);
  if (!c.pass) return c;
  const y20 = c.got[21].kirby.y, yEnd = c.got[c.got.length - 1].kirby.y;
  return { pass: yEnd < y20 - 40, detail: `y ${y20} -> ${yEnd}` };
});
check('float timer: floating ends after 360 floating steps and cannot restart before landing; landing resets it', () => {
  const r = new Rec(9).in('jump', true).step(20).in('jump', true);
  for (let n = 0; r.g.kirby.floating; n++) {
    if (n > 400) throw new Error('harness scenario: the float did not end on the reference');
    if (r.g.kirby.vy > 0.5) r.in('jump', true);
    r.step();
  }
  const atEnd = r.acts.length;
  r.in('jump', true).step(3).in('jump', true);
  r.until((g) => g.kirby.ground, 600, 'landing').step(2);
  const c = compare(page, 9, r.acts);
  if (!c.pass) return c;
  const end = c.got[atEnd];
  const after = c.got.slice(atEnd + 1).filter((s) => !s.kirby.ground);
  const land = c.got[c.got.length - 1];
  return { pass: end.kirby.floatT === C.floatLimit && !end.kirby.floating && after.every((s) => !s.kirby.floating) && land.kirby.floatT === 0,
    detail: JSON.stringify({ floatT: end.kirby.floatT, refloated: after.some((s) => s.kirby.floating), landedFloatT: land.kirby.floatT }) };
});
check('exhale: pressing inhale while floating drops Kirby with normal gravity', () => {
  const r = new Rec(10).in('jump', true).step(20).in('jump', true).step(40).in('inhale', true).step(6);
  const c = compare(page, 10, r.acts);
  if (!c.pass) return c;
  const i = c.got.length - 7;
  const s = c.got[i], next = c.got.slice(i + 1);
  const normal = next.every((x, j) => x.kirby.vy === Math.min(C.maxFall, (j ? next[j - 1] : s).kirby.vy + C.gravity));
  return { pass: !s.kirby.floating && !next.some((x) => x.kirby.floating || x.kirby.inhaling) && normal, detail: JSON.stringify(next.map((x) => x.kirby.vy)) };
});
let pitRec = null;
check('float carries Kirby over pit A (4 tiles) to the far side', () => {
  const r = new Rec(1).in('right', true);
  r.until((g) => g.kirby.x >= 200, 400, 'x 200').in('jump', true);
  r.until((g) => g.kirby.ground && g.kirby.x > 320, 400, 'past the wall');
  r.until((g) => g.kirby.x >= 600 || g.kirby.hurtT > 0, 600, 'the pit edge');
  r.in('jump', true).step(12);
  let held = true;
  for (let n = 0; n < 400 && !(r.g.kirby.ground && r.g.kirby.x > 744); n++) {
    if (held && r.g.kirby.x > 772) { r.in('right', false); held = false; }     // past the pit: let him settle
    if (!r.g.kirby.ground && r.g.kirby.vy > 0.5 && r.g.kirby.y > 240 && r.g.kirby.x < 740) r.in('jump', true);
    r.step();
  }
  pitRec = r;
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const end = c.got[c.got.length - 1];
  return { pass: end.kirby.ground && end.kirby.x > 744 && end.kirby.x < 840 && end.kirby.y === 296 && !end.over && !end.kirby.floating && end.kirby.floatT === 0,
    detail: JSON.stringify({ x: end.kirby.x, y: end.kirby.y, over: end.over }) };
});

// ------------------------------------------------------------------------------------------------ inhale, swallow, spit
let afterCapture = null;
check('inhale: an enemy in front is pulled in and swallowed into the mouth (+200, full "W")', () => {
  const r = new Rec(1).in('right', true);
  r.until((g) => g.kirby.x >= 200, 400, 'x 200').in('jump', true);
  r.until((g) => g.kirby.ground && g.kirby.x > 320, 400, 'past the wall').in('right', false);
  r.until((g) => g.kirby.vx === 0, 60, 'standing');
  const mark = r.acts.length;
  r.in('inhale', true);
  r.until((g) => g.kirby.full !== null, 1500, 'a capture');
  afterCapture = r;
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const run = c.got.slice(mark + 1);
  const end = run[run.length - 1];
  const caught = end.enemies.findIndex((e, i) => !e.alive && run[0].enemies[i].alive);
  const xs = run.map((s) => s.enemies[caught].x);
  const pulled = xs.slice(1).filter((x, i) => x < xs[i]).length;
  return { pass: end.kirby.full === 'W' && end.score - run[0].score === C.enemy && caught >= 0 && pulled > 5 && end.kirby.hp === 6 && !end.kirby.inhaling,
    detail: JSON.stringify({ full: end.kirby.full, dscore: end.score - run[0].score, caught, pulledSteps: pulled }) };
});
check('while inhaling Kirby cannot walk: held right only meets friction', () => {
  const r = new Rec(11).in('right', true).step(30).in('inhale', true).step(10);
  const c = compare(page, 11, r.acts);
  if (!c.pass) return c;
  const tail = c.got.slice(c.got.length - 10);
  return { pass: tail.every((s, i) => s.kirby.inhaling && s.kirby.vx === Math.max(0, C.maxWalk - C.friction * (i + 1))), detail: tail.map((s) => s.kirby.vx).join(',') };
});
check('spit: the star leaves the mouth at x + 24, flies 6 px per step and defeats the first enemy it hits (+200)', () => {
  if (!afterCapture) throw new Error('needs the inhale scenario');
  const r = afterCapture;
  r.in('inhale', false);
  const mark = r.acts.length;
  r.in('spit', true);
  r.until((g) => g.shot === null, 300, 'the shot ending');
  r.step(2);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const s0 = c.got[mark + 1], k = c.got[mark].kirby;
  const shots = c.got.slice(mark + 1).filter((s) => s.shot).map((s) => s.shot.x);
  const speed = shots.slice(1).every((x, i) => x - shots[i] === C.shotSpeed);
  const end = c.got[c.got.length - 1];
  const killed = end.enemies.filter((e) => !e.alive).length - c.got[mark].enemies.filter((e) => !e.alive).length;
  return { pass: s0.shot && s0.shot.x === k.x + 24 && s0.shot.y === k.y + 4 && s0.kirby.full === null && speed && killed === 1 && end.score - s0.score === C.enemy,
    detail: JSON.stringify({ shot: s0.shot, steps: shots.length, killed, dscore: end.score - s0.score }) };
});
check('swallow a waddle-dee: no ability; swallow a bronto-burt: "wing", and the wing jump rises 140.25 px', () => {
  const r = new Rec(1);
  travel(r, (g) => g.kirby.ground && g.kirby.y === 296 && g.kirby.x > 1340);
  r.in('right', false).until((g) => g.kirby.vx === 0, 60, 'standing');
  r.in('inhale', true);
  r.until((g) => g.kirby.full !== null, 1500, 'the bronto-burt');
  r.in('inhale', false).in('swallow', true).step(2);
  const mark = r.acts.length;
  r.in('jump', true);
  r.until((g) => g.kirby.ground, 200, 'landing').step(2);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const before = c.got[mark];
  const ys = c.got.slice(mark).map((s) => s.kirby.y);
  // a waddle-dee swallowed earlier in the same game (white-box, page functions): ability 'none'
  const w = page.json('(() => { const g = newGame(1); g.kirby.full = "W"; g.kirby.ability = "wing"; input(g, "swallow", true); return [g.kirby.ability, g.kirby.full]; })()');
  return { pass: before.kirby.ability === 'wing' && before.kirby.full === null && before.kirby.y - minOf(ys) === C.wingRise && same(w, ['none', null]),
    detail: JSON.stringify({ ability: before.kirby.ability, rise: before.kirby.y - minOf(ys), waddle: w }) };
});
check('a full Kirby cannot float or inhale; swallow and spit do nothing when empty', () => {
  const v = page.json(`(() => {
    const g = newGame(1); g.kirby.full = 'W'; jump(g); const vy1 = g.kirby.vy; const r2 = jump(g);
    g.keys.inhale = true; step(g);
    const e = newGame(1); const sw = swallow(e), sp = spit(e);
    return [vy1, r2, g.kirby.floating, g.kirby.inhaling, sw, sp, e.shot, e.kirby.ability];
  })()`);
  return { pass: same(v, [-6, 'none', false, false, false, false, null, 'none']), detail: JSON.stringify(v) };
});
check('inhale reaches only 64 px ahead, less than 32 px up or down, and never behind', () => {
  const expr = `(() => {
    const g = newGame(1); g.enemies = []; g.kirby.x = 400; g.kirby.face = 1; g.kirby.inhaling = true;
    const mk = (x, y) => ({ kind: 'B', x, y, dir: 1, t: 0, baseY: y, alive: true });
    g.enemies = [mk(465, 296), mk(464, 296), mk(380, 296), mk(440, 264), mk(440, 265), mk(440, 327), mk(440, 328)];
    pull(g); const a = g.enemies.map((e) => e.x);
    g.kirby.face = -1; g.enemies = [mk(336, 296), mk(335.5, 296), mk(420, 296)]; pull(g);
    return [a, g.enemies.map((e) => e.x)];
  })()`;
  const got = page.json(expr);
  const want = [[465, 462, 380, 440, 438, 438, 440], [338, 335.5, 420]];
  return { pass: same(got, want), detail: JSON.stringify(got) };
});

check('spit at a wall: the star flies 6 px per step and vanishes when its middle reaches a "#" tile', () => {
  const r = new Rec(1).in('right', true);
  r.until((g) => g.kirby.x >= 200, 400, 'x 200').in('jump', true);
  r.until((g) => g.kirby.ground && g.kirby.x > 320, 400, 'past the wall').in('right', false);
  r.until((g) => g.kirby.vx === 0, 60, 'standing').in('inhale', true);
  r.until((g) => g.kirby.full !== null, 1500, 'a capture').in('inhale', false);
  r.in('left', true).step().in('left', false);
  const mark = r.acts.length;
  r.in('spit', true).until((g) => g.shot === null, 60, 'the wall').step(2);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const run = c.got.slice(mark + 1);
  const xs = run.filter((s) => s.shot).map((s) => s.shot.x);
  const k = c.got[mark].kirby;
  const last = xs[xs.length - 1];
  return { pass: k.face === -1 && xs[0] === k.x - 16 && xs.slice(1).every((x, i) => x - xs[i] === -C.shotSpeed) &&
    Math.floor((last + 8) / 32) === 10 && Math.floor((last - 6 + 8) / 32) === 9 && run[run.length - 1].shot === null &&
    run[run.length - 1].score === c.got[mark].score, detail: JSON.stringify({ first: xs[0], last, steps: xs.length }) };
});
check('the level\'s left and right edges stop the star too (white-box, same expression on the reference)', () => {
  const b = both(`(() => { const out = []; for (const [x, dir] of [[2020, 1], [10, -1]]) { const g = newGame(1); g.enemies = [];
    g.shot = { x, y: 200, dir }; const xs = []; while (g.shot !== null && xs.length < 50) { xs.push(g.shot.x); shotStep(g); } out.push(xs); } return out; })()`);
  return { pass: b.same && same(b.got, [[2020, 2026, 2032, 2038], [10, 4, -2, -8]]), detail: JSON.stringify(b.got) };
});
check('one step in order: the star hits first, then an enemy bump, then the tiles (white-box)', () => {
  const b = both(`(() => {
    const mk = (o) => { const g = newGame(1); g.enemies = [{ kind: 'W', x: 50, y: 296, dir: 1, t: 0, baseY: 296, alive: true }]; g.tiles[9][1] = '^'; return Object.assign(g, o); };
    const a = mk({ shot: { x: 30, y: 300, dir: 1 } }); step(a);
    const b = mk({}); step(b);
    return [a.kirby.hp, a.score, a.shot, a.enemies[0].alive, b.kirby.hp, b.kirby.hurtT, b.enemies[0].alive];
  })()`);
  return { pass: b.same && same(b.got, [5, 200, null, false, 5, 90, false]), detail: JSON.stringify(b.got) };
});
check('HP never goes below 0: a hit at 0 HP keeps 0 and the game is over (white-box)', () => {
  const b = both(`(() => { const g = newGame(1); g.kirby.hp = 0; const r = hurt(g); const h = newGame(1); h.kirby.hp = 1; hurt(h);
    return [r, g.kirby.hp, g.over, h.kirby.hp, h.over]; })()`);
  return { pass: b.same && same(b.got, [true, 0, true, 0, true]), detail: JSON.stringify(b.got) };
});
check('snapshot shares nothing with the game: Kirby, the enemies and the star are copies (white-box)', () => {
  const b = both(`(() => { const g = newGame(1); g.shot = { x: 1, y: 2, dir: 1 }; const s = snapshot(g);
    s.shot.x = 50; s.kirby.hp = 1; s.enemies[0].x = -5; s.enemies.length = 0;
    return [g.shot.x, g.kirby.hp, g.enemies[0].x, g.enemies.length, Object.keys(s).length]; })()`);
  return { pass: b.same && same(b.got, [1, 6, 1348, 6, 9]), detail: JSON.stringify(b.got) };
});

// ------------------------------------------------------------------------------------------------ damage
let spikeRec = null;
check('spikes: 1 HP, knockback (vx -2 x face, vy -3) and 90 steps without damage', () => {
  if (!pitRec) throw new Error('needs the pit scenario');
  const r = pitRec;
  r.until((g) => g.kirby.hurtT === 0, 200, 'no invulnerability left');
  r.in('right', true);
  r.until((g) => g.kirby.hurtT === 90, 300, 'the spikes');
  const hitAt = r.acts.length;
  r.in('right', false).step(95);
  spikeRec = r;
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const before = c.got[hitAt - 1].kirby, hit = c.got[hitAt].kirby;
  const window = c.got.slice(hitAt, hitAt + 90).map((s) => s.kirby.hp);
  const hurtTs = c.got.slice(hitAt, hitAt + 91).map((s) => s.kirby.hurtT);
  const countdown = hurtTs.slice(2).every((h, i) => h === Math.max(0, hurtTs[i + 1] - 1));
  return { pass: hit.hp === before.hp - 1 && hit.vx === -C.knockVx * before.face && hit.vy === -C.knockVy && hit.hurtT === C.hurtSteps &&
    window.every((h) => h === hit.hp) && countdown, detail: JSON.stringify({ before: before.hp, hit, countdown }) };
});
check('spikes again and again: HP 5, 4, 3, 2, 1, 0, never below 0, then game over and frozen', () => {
  if (!spikeRec) throw new Error('needs the spike scenario');
  const r = spikeRec;
  for (let i = 0; i < 12 && !r.g.over; i++) {
    r.until((g) => g.kirby.hurtT === 0 || g.over, 200, 'the end of invulnerability');
    r.in('right', true).until((g) => g.kirby.hurtT === 90 || g.over, 400, 'the next hit').in('right', false);
  }
  const overAt = r.acts.length;
  r.step(30).in('right', true).in('jump', true).t(1000);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const hps = c.got.map((s) => s.kirby.hp);
  const drops = hps.filter((h, i) => i && h !== hps[i - 1]);
  const over = c.got[overAt], end = c.got[c.got.length - 1];
  return { pass: same(drops, [5, 4, 3, 2, 1, 0]) && hps.every((h) => h >= 0) && over.over && over.kirby.hp === 0 &&
    same(end, over), detail: JSON.stringify({ drops, over: over.over, frozen: same(end, over) }) };
});
check('touching an enemy: 1 HP, the enemy is defeated, no score; no damage while invulnerable', () => {
  const v = page.json(`(() => {
    const g = newGame(1); g.enemies = [{ kind: 'W', x: 64, y: 296, dir: -1, t: 0, baseY: 296, alive: true },
      { kind: 'W', x: 70, y: 296, dir: -1, t: 0, baseY: 296, alive: true }];
    step(g); const a = [g.kirby.hp, g.kirby.hurtT, g.score, g.enemies.map((e) => e.alive)];
    for (let i = 0; i < 20; i++) step(g);
    return [a, g.kirby.hp, g.enemies.map((e) => e.alive)];
  })()`);
  return { pass: same(v, [[5, 90, 0, [false, true]], 5, [false, true]]), detail: JSON.stringify(v) };
});
check('a pit: falling below the level sets HP to 0 and ends the game', () => {
  const r = new Rec(1).in('right', true);
  r.until((g) => g.kirby.x >= 200, 400, 'x 200').in('jump', true);
  r.until((g) => g.kirby.ground && g.kirby.x > 320, 400, 'past the wall');
  r.until((g) => g.over, 900, 'the pit');
  r.step(10);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const i = c.got.findIndex((s) => s.over);
  const s = c.got[i];
  return { pass: i > 0 && s.kirby.hp === 0 && s.kirby.y > 384 && c.got[i - 1].kirby.y <= 384 && same(c.got[c.got.length - 1], s),
    detail: JSON.stringify({ y: s.kirby.y, hp: s.kirby.hp }) };
});

// ------------------------------------------------------------------------------------------------ enemies
check('waddle-dees patrol at 0.5 px per step and turn at walls and ledges (1500 single steps)', () => {
  const r = new Rec(1).step(1500);
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const ranges = { 1: [1056, 1224], 3: [320, 616], 4: [320, 616], 5: [1568, 2024] };
  const bad = [];
  for (const [i, [lo, hi]] of Object.entries(ranges)) {
    const xs = c.got.map((s) => s.enemies[i].x);
    const dirs = c.got.map((s) => s.enemies[i].dir);
    const turns = dirs.filter((d, j) => j && d !== dirs[j - 1]).length;
    if (minOf(xs) < lo || maxOf(xs) > hi || turns < 2) bad.push(`#${i} x ${minOf(xs)}..${maxOf(xs)} turns ${turns}`);
    const touches = (minOf(xs) === lo) + (maxOf(xs) === hi);
    if (touches < 2) bad.push(`#${i} never reached both ends (${minOf(xs)}..${maxOf(xs)})`);
  }
  return { pass: bad.length === 0, detail: bad.join('; ') || 'all four stay on their ground and turn at both ends' };
});
check('bronto-burts fly a sine wave: y = baseY + round(24 sin(t / 16)), 1 px per step, turning every 128 steps', () => {
  const acts = Array.from({ length: 1200 }, () => ['t', 17]);
  const c = compare(page, 2, acts);
  if (!c.pass) return c;
  const bad = [];
  for (const i of [0, 2]) {
    const baseY = i === 0 ? 3 * 32 + 8 : 8 * 32 + 8;
    c.got.forEach((s, j) => {
      const e = s.enemies[i];
      if (s.frame > 0 && e.y !== baseY + Math.round(24 * Math.sin(e.t / 16))) bad.push(`#${i} state ${j}`);
      if (j) {
        const p = c.got[j - 1].enemies[i];
        const dt = e.t - p.t;
        if (dt < 0 || Math.abs(e.x - p.x) > dt) bad.push(`#${i} moved too far at state ${j}`);
      }
    });
    const flips = c.got.filter((s, j) => j && s.enemies[i].dir !== c.got[j - 1].enemies[i].dir).map((s) => s.enemies[i].t);
    if (!flips.length) bad.push(`#${i} never turned`);
  }
  return { pass: bad.length === 0, detail: bad.slice(0, 4).join('; ') || '1200 actions, both on the sine and turning' };
});
check('bronto-burts pass through tiles; waddle-dees keep to their ground (white-box)', () => {
  const v = page.json(`(() => {
    const g = newGame(1); const b = { kind: 'B', x: 100, y: 300, dir: 1, t: 10, baseY: 300, alive: true }; g.enemies = [b];
    for (let i = 0; i < 40; i++) moveEnemies(g);
    const w = { kind: 'W', x: 290, y: 264, dir: 1, t: 0, baseY: 264, alive: true };
    const h = { tiles: g.tiles };
    for (let i = 0; i < 200; i++) waddleStep(h, w);
    return [b.x, b.y, b.t, w.x, w.dir];
  })()`);
  return { pass: v[0] === 140 && v[1] === 300 + Math.round(24 * Math.sin(50 / 16)) && v[2] === 50 && v[3] >= 288 && v[3] <= 296,
    detail: JSON.stringify(v) };
});

// ------------------------------------------------------------------------------------------------ door, camera, time
let playthrough = null;
check('a full playthrough reaches the door: the level is complete and the game freezes', () => {
  const r = new Rec(1);
  travel(r, () => false, 6000);
  if (!r.g.won) throw new Error('harness player did not finish on the reference');
  const wonAt = r.acts.length;
  r.step(40).in('left', true).in('jump', true).t(2000);
  playthrough = r;
  const c = compare(page, 1, r.acts);
  if (!c.pass) return c;
  const s = c.got[wonAt], end = c.got[c.got.length - 1];
  return { pass: s.won && !s.over && same(end, s) && s.kirby.x + 24 > 61 * 32, detail: `won after ${s.frame} steps, score ${s.score}, hp ${s.kirby.hp}` };
});
check('the camera follows Kirby: cam = clamp(floor(x + 12 - 320), 0, 1408), 0 at the start and 1408 at the end', () => {
  if (!playthrough) throw new Error('needs the playthrough');
  const got = page.run(1, playthrough.acts);
  const bad = got.filter((s) => s.cam !== Math.min(C.camMax, Math.max(0, Math.floor(s.kirby.x + 12 - 320))) && s.frame > 0 && !s.over);
  const cams = got.map((s) => s.cam);
  return { pass: bad.length === 0 && cams[0] === 0 && cams[cams.length - 1] === C.camMax && maxOf(cams) === C.camMax,
    detail: bad.length ? `first bad: cam ${bad[0].cam} at x ${bad[0].kirby.x}` : `cam 0..${maxOf(cams)}` };
});
check('time: 16 ms is no step yet, 1 ms more completes it, 1000 ms is exactly 60 steps', () => {
  const v = page.json(`(() => { window.kirby.reset(3); const f = () => window.kirby.state().frame;
    window.kirby.tick(16); const a = f(); window.kirby.tick(1); const b = f(); window.kirby.tick(1000); const c = f();
    window.kirby.tick(50); return [a, b, c, f()]; })()`);
  return { pass: same(v, [0, 1, 61, 64]), detail: JSON.stringify(v) };
});
check('one long tick equals many short ticks (5000 ms vs 5000 x 1 ms)', () => {
  const a = page.run(12, [['in', 'right', true], ['t', 5000]]);
  const b = page.run(12, [['in', 'right', true], ...Array.from({ length: 5000 }, () => ['t', 1])]);
  return { pass: same(a[a.length - 1], b[b.length - 1]) && a[a.length - 1].frame === 300, detail: `frames ${a[a.length - 1].frame} / ${b[b.length - 1].frame}` };
});
check('determinism: two separate page instances, same seed and inputs, identical states', () => {
  if (!playthrough) throw new Error('needs the playthrough');
  const other = new Page(script);
  const a = page.run(1, playthrough.acts), b = other.run(1, playthrough.acts);
  const c = page.run(2, playthrough.acts);
  return { pass: a.length === b.length && a.every((s, i) => same(s, b[i])) && !same(a[a.length - 1], c[c.length - 1]),
    detail: `${a.length} states; seed 2 differs: ${!same(a[a.length - 1], c[c.length - 1])}` };
});

// ------------------------------------------------------------------------------------------------ random inputs
for (const seed of [21, 22, 23, 24, 25, 26]) {
  check(`random inputs, seed ${seed}: every state equals the reference`, () => {
    const rng = R.mulberry32(seed * 7919 + 13);
    const acts = [];
    for (let i = 0; i < 1500; i++) {
      const p = rng();
      if (p < 0.35) acts.push(['t', 1 + Math.floor(rng() * 120)]);
      else if (p < 0.52) acts.push(['in', 'right', rng() < 0.8]);
      else if (p < 0.6) acts.push(['in', 'left', rng() < 0.4]);
      else if (p < 0.76) acts.push(['in', 'jump', rng() < 0.75]);
      else if (p < 0.88) acts.push(['in', 'inhale', rng() < 0.6]);
      else if (p < 0.94) acts.push(['in', 'swallow', rng() < 0.9]);
      else acts.push(['in', 'spit', rng() < 0.9]);
    }
    const c = compare(page, seed, acts);
    if (!c.pass) return c;
    const end = c.got[c.got.length - 1];
    return { pass: true, detail: `${acts.length} actions, ${end.frame} steps, score ${end.score}, hp ${end.kirby.hp}, over ${end.over}` };
  });
}
check('random play with the travelling player and random extra presses reaches far into the level identically', () => {
  const r = new Rec(31);
  const rng = R.mulberry32(99);
  r.in('right', true);
  for (let i = 0; i < 1600 && !r.g.over && !r.g.won; i++) {
    const p = rng();
    if (p < 0.04) r.in('jump', true); else if (p < 0.06) r.in('inhale', rng() < 0.5); else if (p < 0.07) r.in('spit', true);
    else if (p < 0.08) r.in('swallow', true);
    const k = r.g.kirby;
    if (k.ground && (R.tileAt(r.g, 9, Math.floor((k.x + 40) / 32)) !== '.' || !R.standAt(r.g, 10, Math.floor((k.x + 42) / 32)))) r.in('jump', true);
    if (!k.ground && k.vy > 0.5 && rng() < 0.15) r.in('jump', true);
    r.step();
  }
  const c = compare(page, 31, r.acts);
  if (!c.pass) return c;
  const end = c.got[c.got.length - 1];
  return { pass: maxOf(c.got.map((s) => s.kirby.x)) > 700, detail: `${r.acts.length} actions, max x ${maxOf(c.got.map((s) => s.kirby.x))}, score ${end.score}` };
});

// ------------------------------------------------------------------------------------------------ keyboard
check('keyboard: ArrowRight held walks right, keyup releases it; keys are preventDefault-ed', () => {
  const acts = [['key', 'keydown', 'ArrowRight'], ['t', 500], ['key', 'keyup', 'ArrowRight'], ['t', 500]];
  const c = compare(page, 13, acts);
  if (!c.pass) return c;
  const prevented = page.json('(() => { window.kirby.reset(13); return [__key("keydown", "ArrowRight"), __key("keyup", "ArrowRight"), __key("keydown", " "), __key("keydown", "q")]; })()');
  return { pass: c.got[2].kirby.x > 40 && c.got[4].kirby.vx === 0 && same(prevented, [true, true, true, false]), detail: JSON.stringify({ x: c.got[2].kirby.x, prevented }) };
});
check('keyboard: every listed key maps to its action, other keys and Ctrl/Alt/Meta map to null', () => {
  const keys = { ArrowLeft: 'left', a: 'left', A: 'left', ArrowRight: 'right', d: 'right', D: 'right', ArrowUp: 'jump', ' ': 'jump',
    w: 'jump', W: 'jump', z: 'jump', Z: 'jump', x: 'inhale', X: 'inhale', ArrowDown: 'swallow', s: 'swallow', S: 'swallow',
    c: 'spit', C: 'spit', r: 'restart', R: 'restart', q: null, Enter: null, Shift: null, p: null, Escape: null };
  const got = page.json(`(() => { const ks = ${JSON.stringify(Object.keys(keys))}; return ks.map((key) => keyAction({ key, ctrlKey: false, altKey: false, metaKey: false }))
    .concat([keyAction({ key: 'c', ctrlKey: true, altKey: false, metaKey: false }), keyAction({ key: 'a', ctrlKey: false, altKey: true, metaKey: false }), keyAction({ key: 'd', ctrlKey: false, altKey: false, metaKey: true })]); })()`);
  return { pass: same(got, Object.values(keys).concat([null, null, null])), detail: JSON.stringify(got) };
});
check('keyboard: Space jumps; a repeating keydown does nothing; Ctrl+key is left to the browser', () => {
  const acts = [['key', 'keydown', ' '], ['key', 'keydown', ' ', { repeat: true }], ['t', 100], ['key', 'keydown', 'd', { ctrlKey: true }], ['t', 300]];
  const c = compare(page, 14, acts);
  if (!c.pass) return c;
  const p = page.json('(() => { window.kirby.reset(14); return [__key("keydown", "d", { ctrlKey: true }), __key("keydown", "x", { metaKey: true })]; })()');
  return { pass: c.got[1].kirby.vy === -6 && c.got[2].kirby.vy === -6 && !c.got[2].kirby.floating && c.got[5].kirby.vx === 0 && same(p, [false, false]),
    detail: JSON.stringify({ vy: c.got[2].kirby.vy, floating: c.got[2].kirby.floating, prevented: p }) };
});
check('keyboard: X inhales while held, S swallows, C spits, R starts a new game', () => {
  const v = page.json(`(() => {
    window.kirby.reset(15); __key('keydown', 'x'); const held = window.kirby.state().kirby; __key('keyup', 'x');
    window.kirby.tick(100); const after = window.kirby.state().kirby.inhaling;
    window.kirby.input('right', true); window.kirby.tick(2000); __key('keydown', 'r');
    const s = window.kirby.state();
    return [after, s.frame, s.score, s.kirby.x, s.stars];
  })()`);
  const sw = page.json(`(() => { const g = newGame(1); g.kirby.full = 'B'; handleKey(g, { key: 's', repeat: false, ctrlKey: false, altKey: false, metaKey: false, preventDefault() {} }, true);
    const h = newGame(1); h.kirby.full = 'W'; handleKey(h, { key: 'c', repeat: false, ctrlKey: false, altKey: false, metaKey: false, preventDefault() {} }, true);
    const i = newGame(1); handleKey(i, { key: 'x', repeat: false, ctrlKey: false, altKey: false, metaKey: false, preventDefault() {} }, true);
    return [g.kirby.ability, h.shot !== null, i.keys.inhale]; })()`);
  return { pass: v[0] === false && v[1] === 0 && v[2] === 0 && v[3] === 40 && v[4] === 11 && same(sw, ['wing', true, true]), detail: JSON.stringify({ v, sw }) };
});

// ------------------------------------------------------------------------------------------------ drawing
function paintCalls(expr) {
  page.eval(expr);
  page.clearCalls();
  page.eval('window.kirby.tick(0)');                 // tick paints once, even when no step is due
  return page.calls();
}
check('drawing: each paint starts with the sky (640 x 384) and draws the visible ground relative to the camera', () => {
  if (!playthrough) throw new Error('needs the playthrough');
  const ref = refRun(1, playthrough.acts);
  const at = ref.findIndex((s) => s.kirby.x > 1000);
  page.run(1, playthrough.acts.slice(0, at));
  page.clearCalls(); page.eval('window.kirby.tick(0)');
  const calls = page.calls();
  const s = page.json('window.kirby.state()');
  const first = calls[0];
  const xs = calls.filter((c) => c[0] === 'fillRect' && c[1] === '#8b5a2b' && c[5] === 320).map((c) => c[4]);
  const want = [];
  const c0 = Math.floor(s.cam / 32);
  for (let col = c0; col <= c0 + 20 && col < 64; col++) if (LEVEL[10][col] === '#') want.push(col * 32 - s.cam);
  return { pass: first[0] === 'fillRect' && first[1] === '#87ceeb' && same(first.slice(4, 8), [0, 0, 640, 384]) && same(xs, want) && s.cam > 600,
    detail: JSON.stringify({ cam: s.cam, ground: xs.length, want: want.length }) };
});
check('drawing: Kirby is a pink circle at his place on screen (radius 12, 15 floating, 14 full) with red feet', () => {
  const a = paintCalls('window.kirby.reset(1); window.kirby.input("right", true); window.kirby.tick(9000)');
  const s = page.json('window.kirby.state()');
  const pink = a.filter((c) => c[0] === 'arc' && c[1] === '#ff9ebd').map((c) => c.slice(4, 7));
  const feet = a.filter((c) => c[0] === 'arc' && c[1] === '#d81e3a').length;
  const b = paintCalls('window.kirby.reset(1); window.kirby.input("jump", true); window.kirby.tick(300); window.kirby.input("jump", true); window.kirby.tick(100)');
  const floatR = b.filter((c) => c[0] === 'arc' && c[1] === '#ff9ebd').map((c) => c[6]);
  return { pass: same(pink, [[s.kirby.x + 12 - s.cam, s.kirby.y + 12, 12]]) && feet === 2 && same(floatR, [15]), detail: JSON.stringify({ pink, feet, floatR }) };
});
check('drawing: Kirby blinks while invulnerable (hidden when floor(hurtT / 4) is odd)', () => {
  const v = page.json(`(() => [90, 87, 84, 83, 80, 2].map((h) => {
    const g = newGame(1); g.kirby.hurtT = h; __h.calls = []; drawKirby(window.document.getElementById('game').getContext('2d'), g);
    return __h.calls.filter((c) => c[0] === 'arc' && c[1] === '#ff9ebd').length; }))()`);
  return { pass: same(v, [1, 0, 0, 1, 1, 1]), detail: JSON.stringify(v) };
});
check('drawing: live enemies are drawn at their places, defeated ones are not', () => {
  const calls = paintCalls('window.kirby.reset(1)');
  const s = page.json('window.kirby.state()');
  const bodies = calls.filter((c) => c[0] === 'arc' && (c[1] === '#f4a460' || c[1] === '#e75480')).map((c) => [c[1], c[4], c[5]]);
  const want = s.enemies.filter((e) => e.alive).map((e) => [e.kind === 'W' ? '#f4a460' : '#e75480', e.x + 12 - s.cam, e.y + 12]);
  const dead = page.json(`(() => { const g = newGame(1); g.enemies.forEach((e) => { e.alive = false; }); __h.calls = [];
    draw(window.document.getElementById('game').getContext('2d'), g);
    return __h.calls.filter((c) => c[0] === 'arc' && (c[1] === '#f4a460' || c[1] === '#e75480')).length; })()`);
  return { pass: same(bodies.sort(), want.sort()) && dead === 0, detail: JSON.stringify({ drawn: bodies.length, dead }) };
});
check('drawing: the HUD shows HP squares, the score, the ability, and GAME OVER / LEVEL COMPLETE', () => {
  const texts = (calls) => calls.filter((c) => c[0] === 'fillText').map((c) => String(c[4]));
  const a = paintCalls('window.kirby.reset(1); window.kirby.input("right", true); window.kirby.tick(1200)');
  const s = page.json('window.kirby.state()');
  const hp = a.filter((c) => c[0] === 'fillRect' && c[1] === '#ff69b4').length;
  if (!playthrough) throw new Error('needs the playthrough');
  page.run(1, playthrough.acts);
  page.clearCalls(); page.eval('window.kirby.tick(0)');
  const won = texts(page.calls());
  page.run(1, spikeRec ? spikeRec.acts : []);
  page.clearCalls(); page.eval('window.kirby.tick(0)');
  const over = texts(page.calls());
  return { pass: hp === s.kirby.hp && texts(a).includes('SCORE ' + s.score) && texts(a).includes('ABILITY none') &&
    won.includes('LEVEL COMPLETE') && over.includes('GAME OVER'), detail: JSON.stringify({ hp, texts: texts(a), won, over }) };
});

// ------------------------------------------------------------------------------------------------ invariants
check('invariants over every state seen: HP 0-6, finite numbers, speeds in range, score steps; in a run stars and HP never come back', () => {
  const bad = [];
  for (const s of seen) {
    const k = s.kirby;
    if (!(Number.isInteger(k.hp) && k.hp >= 0 && k.hp <= 6)) bad.push(`hp ${k.hp}`);
    for (const v of [k.x, k.y, k.vx, k.vy, s.score, s.cam, s.frame]) if (typeof v !== 'number' || !Number.isFinite(v)) bad.push(`number ${v}`);
    if (k.vx < -C.maxWalk || k.vx > C.maxWalk || k.vy > C.maxFall) bad.push(`speed ${k.vx},${k.vy}`);
    if (s.stars < 0 || s.stars > 11 || s.score < 0 || s.score % 100 !== 0) bad.push(`stars ${s.stars} score ${s.score}`);
    if (s.over && k.hp !== 0) bad.push('game over with HP left');
    if (bad.length > 5) break;
  }
  bad.push(...runFaults);
  return { pass: bad.length === 0, detail: bad.slice(0, 5).join('; ') || `${seen.length} states` };
});
check('no page errors (thrown exceptions or console.error) during the whole run', () => {
  const errs = page.errors();
  return { pass: errs.length === 0, detail: errs.slice(0, 3).join(' | ') };
});

finish();

function finish() {
  const passed = results.filter((r) => r.pass).length;
  const summary = { file, passed, total: results.length, results };
  if (outPath) fs.writeFileSync(outPath, JSON.stringify(summary, null, 2) + '\n');
  for (const r of results) console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name}${r.pass ? '' : '  ::  ' + r.detail}`);
  console.log(`required ${passed}/${results.length}`);
  process.exit(passed === results.length ? 0 : 1);
}

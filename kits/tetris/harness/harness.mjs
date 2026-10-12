// Conformance harness: a built tetris.html in headless Chromium against ../reference/reference.mjs (the strict
// specification, executable). Prints one line per check and "N/M required checks passed"; exits 0 only when every
// required check passes.
//
//   node kits/tetris/harness/harness.mjs path/to/tetris.html [out.json] [--v1]     (no network; file:// only)
//
// --v1 grades a file made from the first version of the specification: the checks for later clarifications become
// advisory. Needs Playwright with its Chromium: `npm install playwright` (in any folder on node's module path) and
// `npx playwright install chromium`, or set PLAYWRIGHT_MODULE to the path of an installed playwright/index.mjs.
import { Game, boxCells, mulberry32 } from '../reference/reference.mjs';
import fs from 'node:fs';
import path from 'node:path';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const V1 = process.argv.includes('--v1');
const argv = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const file = path.resolve(argv[0] || 'tetris.html');
const outPath = argv[1] || '';
const results = [];
const record = (name, pass, detail = '', advisory = false) => { results.push({ name, pass: !!pass, advisory, detail: String(detail).slice(0, 1500) }); };

function norm(s) {
  if (!s || typeof s !== 'object') return { bad: true, raw: s };
  const a = s.active && !(V1 && s.over) ? {
    type: s.active.type, rotation: s.active.rotation, row: s.active.row, col: s.active.col,
    cells: (s.active.cells || []).map((c) => `${c[0]},${c[1]}`).sort(),
  } : null;
  return {
    board: s.board, active: a, hold: s.hold === undefined ? 'undefined' : s.hold, next: s.next,
    score: s.score, lines: s.lines, level: s.level, over: !!s.over, paused: !!s.paused,
  };
}

function diff(a, b) {
  const out = [];
  for (const k of Object.keys(b)) {
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) {
      if (k === 'board') {
        const rows = [];
        for (let r = 0; r < 22; r++) if (JSON.stringify((a.board || [])[r]) !== JSON.stringify(b.board[r])) rows.push(r);
        out.push(`board rows ${rows.join(',')}: got ${JSON.stringify((a.board || [])[rows[0]])} want ${JSON.stringify(b.board[rows[0]])}`);
      } else out.push(`${k}: got ${JSON.stringify(a[k])} want ${JSON.stringify(b[k])}`);
    }
  }
  return out.join('; ');
}

// a placement player on the reference: picks rotation and column that clear the most rows, then the flattest board
function placements(game) {
  const a = game.active; const acts = [];
  let best = null;
  for (let rot = 0; rot < 4; rot++) {
    for (let target = -2; target < 10; target++) {
      const g = { board: game.board, fits: game.fits };
      let st = { type: a.type, rot: 0, row: a.row, col: a.col };
      const seq = [];
      let ok = true;
      for (let k = 0; k < rot && a.type !== 'O'; k++) {
        const probe = Object.create(Game.prototype); probe.board = game.board; probe.active = { ...st };
        probe.holdUsed = true; probe.paused = false; probe.over = false; probe.resets = 0; probe.lockT = 0;
        const before = JSON.stringify(probe.active); probe.input('cw');
        if (JSON.stringify(probe.active) === before) { ok = false; break; }
        st = { ...probe.active }; seq.push('cw');
      }
      if (!ok) continue;
      while (st.col !== target) {
        const dc = target < st.col ? -1 : 1;
        if (!g.fits.call(game, st.type, st.rot, st.row, st.col + dc)) break;
        st.col += dc; seq.push(dc < 0 ? 'left' : 'right');
      }
      if (st.col !== target) continue;
      let row = st.row; while (g.fits.call(game, st.type, st.rot, row + 1, st.col)) row++;
      const board = game.board.map((r) => r.slice());
      for (const [r, c] of boxCells(st.type, st.rot)) if (row + r >= 0) board[row + r][st.col + c] = 'x';
      const full = board.filter((r) => r.every((x) => x)).length;
      const heights = []; let holes = 0;
      for (let c = 0; c < 10; c++) {
        let h = 0, seen = false;
        for (let r = 0; r < 22; r++) { if (board[r][c]) { if (!seen) { h = 22 - r; seen = true; } } else if (seen) holes++; }
        heights.push(h);
      }
      const bump = heights.slice(1).reduce((s, h, i) => s + Math.abs(h - heights[i]), 0);
      const score = full * 1000 - holes * 40 - heights.reduce((s, h) => s + h, 0) * 2 - bump * 3;
      if (!best || score > best.score) best = { score, seq: [...seq, 'drop'] };
    }
  }
  return best ? best.seq : ['drop'];
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 900, height: 800 } });
  const errors = [], external = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('request', (r) => { const u = r.url(); if (!u.startsWith('file:') && !u.startsWith('data:') && !u.startsWith('blob:')) external.push(u); });
  await page.route('**/*', (route) => { const u = route.request().url(); return u.startsWith('file:') || u.startsWith('data:') || u.startsWith('blob:') ? route.continue() : route.abort(); });
  const html = fs.readFileSync(file, 'utf8');
  record('size', html.length > 2000 && html.length < 400000, `${html.length} characters`);
  const urls = (html.match(/https?:\/\/[^\s"'<>)]+/g) || []).filter((u) => !u.startsWith('http://www.w3.org/'));
  record('no external URLs in source', urls.length === 0, urls.slice(0, 5).join(' '));
  await page.goto('file://' + file);
  const hasApi = await page.waitForFunction(() => window.tetris && ['reset', 'input', 'tick', 'state'].every((k) => typeof window.tetris[k] === 'function'), null, { timeout: 5000 }).then(() => true, () => false);
  record('window.tetris API', hasApi);
  if (!hasApi) throw new Error('no test API');
  {
    const a = await page.evaluate(() => JSON.parse(JSON.stringify(window.tetris.state())));
    await page.waitForTimeout(3000);
    const b = await page.evaluate(() => JSON.parse(JSON.stringify(window.tetris.state())));
    record('real-time gravity before any reset()', b.active && a.active && (b.active.row > a.active.row || b.board.some((r) => r.some((x) => x))),
      `row ${a.active && a.active.row} -> ${b.active && b.active.row} after 3 s`);
  }
  const T = {
    reset: (s) => page.evaluate((s) => { window.tetris.reset(s); }, s),
    input: (a) => page.evaluate((a) => { window.tetris.input(a); }, a),
    tick: (m) => page.evaluate((m) => { window.tetris.tick(m); }, m),
    state: () => page.evaluate(() => JSON.parse(JSON.stringify(window.tetris.state()))),
    run: (seed, actions) => page.evaluate(([seed, actions]) => {
      window.tetris.reset(seed); const out = [JSON.parse(JSON.stringify(window.tetris.state()))];
      for (const a of actions) { if (typeof a === 'number') window.tetris.tick(a); else window.tetris.input(a); out.push(JSON.parse(JSON.stringify(window.tetris.state()))); }
      return out;
    }, [seed, actions]),
  };
  const compare = async (name, seed, actions, advisory = false) => {
    const got = await T.run(seed, actions);
    const ref = new Game(seed); const want = [norm(ref.state())];
    for (const a of actions) { if (typeof a === 'number') ref.tick(a); else ref.input(a); want.push(norm(ref.state())); }
    for (let i = 0; i < want.length; i++) {
      const d = diff(norm(got[i]), want[i]);
      if (d) { record(name, false, `step ${i} (${i ? JSON.stringify(actions[i - 1]) : 'reset'}): ${d}`, advisory); return false; }
    }
    record(name, true, `${actions.length} actions`, advisory);
    return true;
  };

  // shape of state()
  await T.reset(1);
  const s0 = await T.state();
  const shapeOk = Array.isArray(s0.board) && s0.board.length === 22 && s0.board.every((r) => Array.isArray(r) && r.length === 10)
    && s0.active && Array.isArray(s0.active.cells) && s0.active.cells.length === 4 && Array.isArray(s0.next) && s0.next.length === 3;
  record('state() shape', shapeOk, JSON.stringify(s0).slice(0, 300));
  {
    const letters = new Set(['I', 'O', 'T', 'S', 'Z', 'J', 'L']);
    await T.reset(4); await T.input('hold'); await T.input('drop');
    const s = await T.state();
    const cellsOk = s.board.every((r) => r.every((x) => x === '' || letters.has(x)));
    const holdOk = s0.hold === null && letters.has(s.hold);
    const nextOk = s.next.length === 3 && s.next.every((x) => letters.has(x));
    const activeOk = letters.has(s.active.type) && [0, 1, 2, 3].includes(s.active.rotation) && s.active.cells.every((c) => Array.isArray(c) && c.length === 2);
    record('state() types are exact', cellsOk && holdOk && nextOk && activeOk,
      JSON.stringify({ cellsOk, holdOk, nextOk, activeOk, hold0: s0.hold, hold: s.hold, next: s.next }));
  }

  // three bags: pieces spread over the width so the stack never tops out before piece 21
  const spread = [];
  for (let k = 0; k < 21; k++) { const n = [4, 2, 0, -2, -4][k % 5]; spread.push(...Array(Math.abs(n)).fill(n > 0 ? 'left' : 'right'), 'drop'); }
  for (const seed of [1, 2, 42, 2026]) await compare(`bag sequence and spawns, seed ${seed}`, seed, spread);
  // moves, rotations and kicks at the walls, holds, soft drops
  await compare('moves to the walls', 5, ['left', 'left', 'left', 'left', 'left', 'drop', 'right', 'right', 'right', 'right', 'right', 'right', 'drop']);
  await compare('rotations and wall kicks', 6, ['cw', 'left', 'left', 'left', 'left', 'cw', 'cw', 'ccw', 'drop', 'ccw', 'right', 'right', 'right', 'right', 'right', 'cw', 'ccw', 'ccw', 'drop', 'cw', 'cw', 'cw', 'cw', 'drop']);
  await compare('hold rules', 7, ['hold', 'hold', 'drop', 'hold', 'left', 'drop', 'hold', 'cw', 'hold', 'drop']);
  await compare('soft drop scoring', 8, ['down', 'down', 'down', 'down', 'drop', 'down', 'drop']);
  // a placement player that clears rows
  for (const seed of [3, 11]) {
    const g = new Game(seed); const acts = [];
    for (let p = 0; p < 70 && !g.over; p++) { const seq = placements(g); for (const a of seq) { g.input(a); acts.push(a); } }
    await compare(`line clears and scoring (player), seed ${seed}: ${g.lines} lines, score ${g.score}`, seed, acts);
  }
  {
    const g = new Game(3); const acts = [];
    for (let p = 0; p < 40 && !g.over; p++) {
      const seq = placements(g); seq.pop();
      for (const a of seq) { g.input(a); acts.push(a); }
      const piece = g.active; let ms = 0;
      while (g.active === piece && !g.over && ms < 60000) { g.tick(1); ms++; }
      acts.push(ms);
    }
    await compare(`line clears inside ticks (gravity locks), seed 3: ${g.lines} lines, level ${g.level}`, 3, acts, V1);
  }
  // random inputs
  for (const seed of [21, 22, 23]) {
    const rng = mulberry32(seed * 7 + 1); const pool = ['left', 'right', 'down', 'cw', 'ccw', 'left', 'right', 'drop', 'hold'];
    const acts = Array.from({ length: 300 }, () => pool[Math.floor(rng() * pool.length)]);
    await compare(`random inputs, seed ${seed}`, seed, acts);
  }
  // pause
  await compare('pause freezes input and time', 9, ['pause', 'left', 'cw', 'drop', 5000, 'pause', 'left']);
  // gravity: one row per second at level 1
  {
    await T.reset(31); const r0 = (await T.state()).active.row;
    await T.tick(950); const r1 = (await T.state()).active.row;
    await T.tick(100); const r2 = (await T.state()).active.row;
    record('gravity: one row after 1 s at level 1', r1 === r0 && r2 === r0 + 1, `rows ${r0} -> ${r1} (950 ms) -> ${r2} (1050 ms)`);
  }
  // lock delay: 500 ms after resting
  {
    await T.reset(32);
    let prev = -1, s = await T.state();
    for (let i = 0; i < 25 && s.active.row !== prev; i++) { prev = s.active.row; await T.input('down'); s = await T.state(); }
    const resting = JSON.stringify(s.active);
    await T.tick(450); const a1 = await T.state();
    await T.tick(100); const a2 = await T.state();
    const stillThere = JSON.stringify(a1.active) === resting;
    const locked = JSON.stringify(a2.active) !== resting && a2.board.some((r) => r.some((x) => x));
    record('lock delay: locks between 450 and 550 ms of rest', stillThere && locked, `after 450 ms same piece: ${stillThere}; after 550 ms locked: ${locked}`);
  }
  // lock delay restarts on a move while resting, at most 15 times
  {
    const acts = Array(22).fill('down');
    acts.push(400, 'left', 400, 'right', 400, 'left', 450);              // three restarts: still the same piece
    await compare('lock delay restarts on a move while resting', 37, acts);
    const capped = Array(22).fill('down');
    for (let i = 0; i < 17; i++) capped.push(400, i % 2 ? 'right' : 'left');
    capped.push(450, 100);
    await compare('lock delay restarts at most 15 times', 38, capped);
  }
  // gravity at a higher level: the placement player clears 10+ rows, then a fresh piece falls on that level's clock
  {
    const g = new Game(3); const acts = [];
    while (g.lines < 10 && !g.over) for (const a of placements(g)) { g.input(a); acts.push(a); }
    const lvl = g.level; const ms = Math.round(Math.pow(0.8 - (lvl - 1) * 0.007, lvl - 1) * 1000);
    const got = await T.run(3, [...acts, ms - 25, 50]);
    const n = got.length; const r0 = got[n - 3].active.row, r1 = got[n - 2].active.row, r2 = got[n - 1].active.row;
    record(`gravity at level ${lvl}: one row per ${ms} ms`, got[n - 3].level === lvl && r1 === r0 && r2 === r0 + 1,
      `level ${got[n - 3].level}, rows ${r0} -> ${r1} (${ms - 25} ms) -> ${r2} (${ms + 25} ms)`);
  }
  // spec v2: one long tick is the same as that many 1 ms steps (falls, rests, locks, spawns inside one call)
  await compare('one long tick equals 1 ms steps', 41, [25000, 1, 999, 7777, 30000], V1);
  // spec v2: at game over active is null, the overlapping piece is not placed, next has advanced
  await compare('game over: active null, piece not placed', 33, Array(60).fill('drop'), V1);
  // spec v2: state() returns a new copy each call
  {
    const r = await page.evaluate(() => {
      window.tetris.reset(40);
      const a = window.tetris.state(); const snap = JSON.stringify(a);
      a.board[21][0] = 'Z'; a.next.push('Q'); a.score = 12345; if (a.active) { a.active.row = 99; a.active.cells[0][0] = 99; }
      const leaked = JSON.stringify(window.tetris.state()) !== snap;
      const held = window.tetris.state(); const heldSnap = JSON.stringify(held);
      window.tetris.input('left'); window.tetris.input('drop');
      const aliased = JSON.stringify(held) !== heldSnap;
      return { leaked, aliased };
    });
    record('state() returns a new copy each call', !r.leaked && !r.aliased, JSON.stringify(r), V1);
  }
  // game over
  {
    await T.reset(33); let s = await T.state(), n = 0;
    while (!s.over && n < 80) { await T.input('drop'); s = await T.state(); n++; }
    const frozen = JSON.stringify(norm(s));
    await T.input('left'); await T.tick(3000);
    record('game over and frozen after it', s.over && JSON.stringify(norm(await T.state())) === frozen, `over after ${n} drops`);
    await T.input('pause'); const sp = await T.state();
    record('game over: active is null and pause does nothing', s.over && s.active === null && sp.paused === false,
      JSON.stringify({ active: s.active, pausedAfterPause: sp.paused }), V1);
    const text = await page.evaluate(() => document.body.innerText || '');
    record('GAME OVER shown as page text (canvas text cannot be read here)', /game\s*over/i.test(text), text.slice(0, 120), true);
  }
  // keyboard
  {
    await page.evaluate(() => { const d = document.createElement('div'); d.style.height = '4000px'; d.id = 'harness-spacer';
      document.body.appendChild(d); window.scrollTo(0, 0); const c = document.querySelector('canvas[tabindex]'); (c || document.body).focus(); });
    await T.reset(34);
    const st = async () => (await T.state());
    const a0 = await st();
    await page.keyboard.press('ArrowLeft'); const a1 = await st();
    await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); const a2 = await st();
    await page.keyboard.press('ArrowUp'); const a3 = await st();
    await page.keyboard.press('KeyZ'); const a4 = await st();
    await page.keyboard.press('KeyC'); const a5 = await st();
    await page.keyboard.press('Space'); const a6 = await st();
    await page.keyboard.press('KeyP'); const a7 = await st();
    await page.keyboard.press('KeyP');
    await T.reset(39); const k0 = await st();
    await page.keyboard.press('ArrowDown'); const k1 = await st();
    await page.keyboard.press('KeyX'); const k2 = await st();
    await page.keyboard.press('Shift'); const k3 = await st();
    record('keyboard: ArrowDown, X and Shift', k1.active.row === k0.active.row + 1 && (k0.active.type === 'O' || k2.active.rotation !== k1.active.rotation) && !!k3.hold,
      JSON.stringify({ row0: k0.active.row, row1: k1.active.row, rot1: k1.active.rotation, rot2: k2.active.rotation, hold: k3.hold }));
    const rotOk = a0.active.type === 'O' || a3.active.rotation !== a2.active.rotation;
    const pass = a1.active.col === a0.active.col - 1 && a2.active.col === a1.active.col + 2 && rotOk
      && (a0.active.type === 'O' || a4.active.rotation === a2.active.rotation) && a5.hold && a6.board.some((r) => r.some((x) => x)) && a7.paused;
    record('keyboard controls', pass, JSON.stringify({ c0: a0.active.col, c1: a1.active.col, c2: a2.active.col, r2: a2.active.rotation, r3: a3.active.rotation, r4: a4.active.rotation, hold: a5.hold, locked: a6.board.some((r) => r.some((x) => x)), paused: a7.paused }));
    const scrolled = await page.evaluate(() => window.scrollY);
    record('keys do not scroll the page', scrolled === 0, `scrollY ${scrolled}`);
    {
      await T.reset(42); const m0 = await st();
      await page.evaluate(() => { window.__prevented = []; addEventListener('keydown', (e) => window.__prevented.push(e.defaultPrevented)); });
      await page.keyboard.press('Control+KeyC'); await page.keyboard.press('Control+KeyX'); await page.keyboard.press('Meta+ArrowLeft');
      await page.keyboard.press('Alt+KeyZ');
      const m1 = await st(); const prevented = await page.evaluate(() => window.__prevented);
      record('keys with Ctrl, Alt or Meta are left to the browser',
        JSON.stringify(norm(m1)) === JSON.stringify(norm(m0)) && prevented.every((p) => p === false),
        JSON.stringify({ hold: m1.hold, rotation: m1.active && m1.active.rotation, col: m1.active && m1.active.col, prevented }), V1);
    }
  }
  // canvas
  {
    await T.reset(35); for (let i = 0; i < 6; i++) await T.input('drop');
    await page.waitForTimeout(150);
    const info = await page.evaluate(() => {
      const cs = [...document.querySelectorAll('canvas')];
      const c = cs.find((x) => x.width === 300 && x.height === 600) || cs[0];
      if (!c) return { canvases: 0 };
      const ctx = c.getContext('2d'); const d = ctx.getImageData(0, 0, c.width, c.height).data; const colours = new Set();
      for (let i = 0; i < d.length; i += 4 * 97) colours.add(`${d[i]},${d[i + 1]},${d[i + 2]}`);
      return { canvases: cs.length, w: c.width, h: c.height, colours: colours.size };
    });
    record('a 300x600 canvas with drawing', info.w === 300 && info.h === 600 && info.colours >= 4, JSON.stringify(info));
    const s = await T.state(); const text = await page.evaluate(() => document.body.innerText || '');
    record('side panel shows score, lines and level as page text', text.includes(String(s.score)) && text.includes(String(s.lines)) && text.includes(String(s.level)),
      `score ${s.score}, level ${s.level}: ${text.replace(/\s+/g, ' ').slice(0, 160)}`, true);
  }
  // R restarts
  {
    await T.reset(36); for (let i = 0; i < 3; i++) await T.input('drop');
    await page.keyboard.press('KeyR'); await page.waitForTimeout(50);
    let s = await T.state(); let how = 'r';
    if (s.score !== 0) { await page.keyboard.press('Shift+KeyR'); await page.waitForTimeout(50); s = await T.state(); how = 'Shift+R'; }
    record('R restarts', s.score === 0 && s.lines === 0 && !s.over && !s.board.some((r) => r.some((x) => x)), `score ${s.score} after ${how}`);
  }
  record('no page errors', errors.length === 0, errors.slice(0, 5).join(' | '));
  record('no network requests', external.length === 0, external.slice(0, 5).join(' '));
} catch (e) {
  record('harness', false, String(e && e.stack || e));
} finally {
  await browser.close();
}
const required = results.filter((r) => !r.advisory);
const passed = required.filter((r) => r.pass).length;
const summary = { file, passed, total: required.length, advisory: results.filter((r) => r.advisory), results };
if (outPath) fs.writeFileSync(outPath, JSON.stringify(summary, null, 2) + '\n');
for (const r of results) console.log(`${r.pass ? 'PASS' : r.advisory ? 'WARN' : 'FAIL'}  ${r.name}${r.pass ? '' : '  ::  ' + r.detail}`);
console.log(`${passed}/${required.length} required checks passed; ${results.filter((r) => r.advisory && r.pass).length}/${results.filter((r) => r.advisory).length} advisory`);
process.exit(passed === required.length ? 0 : 1);

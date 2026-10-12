// Checks the reference (ref-units.mjs) against the written specification before any example is derived from it.
//
//   node kits/kirby/reference/check-ref.mjs
//
// Three independent lines of evidence, all printed:
//   1. an oracle: the feature contract (../README.md) written again as one class, in a different style from the units
//      (tiles a box overlaps found by a loop, not by span(); one switch for input; no shared helper with the
//      reference except the PRNG, which the contract gives as code). Reference and oracle must report the same
//      state after every action of 300 random games and of the travelling player's games on 20 seeds;
//   2. the contract's numbers, measured on the reference (jump 69 px, wing 140.25 px, float 360 steps, ...);
//   3. the level's own rules (12 x 64, every waddle-dee stands on ground, the door is reachable) and the sheet:
//      every example of ../sheets/kirby.sheet.md recomputed with the reference (fill-sheet.mjs check).
// Exit 0 only when everything passes.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as R from './ref-units.mjs';
import { runSheet } from './fill-sheet.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const results = [];
function check(name, fn) {
  let pass = false, detail = '';
  try {
    const r = fn();
    pass = r === true || (r && r.pass === true);
    detail = r && r.detail !== undefined ? r.detail : '';
  } catch (e) { detail = (e && e.stack) || String(e); }
  results.push({ name, pass, detail: String(detail).slice(0, 600) });
}

// ------------------------------------------------------------------------------------------------ 1. the oracle
const ROWS = [
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
const TILE = 32, VIEW = 640, WIDTH = 64 * TILE;

class Oracle {
  constructor(seed) {
    const rnd = R.mulberry32(seed);                          // the contract gives the PRNG as code
    this.grid = ROWS.map((row) => row.split(''));
    this.foes = [];
    for (let r = 0; r < 12; r++) {
      for (let c = 0; c < 64; c++) {
        const ch = this.grid[r][c];
        if (ch !== 'W' && ch !== 'B') continue;
        const dir = rnd() < 0.5 ? -1 : 1;
        const t = Math.floor(rnd() * 64);
        this.foes.push({ kind: ch, x: c * TILE + 4, y: r * TILE + 8, dir, t, baseY: r * TILE + 8, alive: true });
        this.grid[r][c] = '.';
      }
    }
    this.k = { x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0, inhaling: false,
      full: null, ability: 'none', hp: 6, hurtT: 0 };
    this.held = { left: false, right: false, inhale: false };
    this.shot = null; this.score = 0; this.cam = 0; this.acc = 0; this.frame = 0; this.over = false; this.won = false;
  }
  tile(r, c) {
    if (c < 0 || c >= 64 || r < 0) return '#';
    if (r >= 12) return '.';
    return this.grid[r][c];
  }
  // tile indexes that the interval [a, a + len) overlaps
  cover(a, len) {
    const out = [];
    for (let i = Math.floor(a / TILE); i * TILE < a + len; i++) out.push(i);
    return out;
  }
  static overlap(ax, ay, as, bx, by, bs) { return ax < bx + bs && bx < ax + as && ay < by + bs && by < ay + as; }
  hurt() {
    const k = this.k;
    if (k.hurtT > 0) return;
    k.hp = Math.max(0, k.hp - 1);
    k.hurtT = 90;
    k.vx = -2 * k.face;
    k.vy = -3;
    k.floating = false;
    if (k.hp === 0) this.over = true;
  }
  step() {
    if (this.over || this.won) return;
    const k = this.k;
    this.frame++;
    if (k.hurtT > 0) k.hurtT--;
    k.inhaling = this.held.inhale && !k.floating && k.full === null;
    const L = this.held.left && !k.inhaling, Rt = this.held.right && !k.inhaling;
    if (L && !this.held.right) { k.vx = Math.max(-2, k.vx - 1 / 8); k.face = -1; }
    else if (Rt && !this.held.left) { k.vx = Math.min(2, k.vx + 1 / 8); k.face = 1; }
    else k.vx = k.vx > 0 ? Math.max(0, k.vx - 1 / 4) : Math.min(0, k.vx + 1 / 4);
    if (k.floating && ++k.floatT >= 360) k.floating = false;
    k.vy = k.floating ? Math.min(1, k.vy + 1 / 16) : Math.min(6, k.vy + 1 / 4);
    // sideways, against '#' only
    k.x += k.vx;
    const rows = this.cover(k.y, 24);
    if (k.vx !== 0) {
      const cols = this.cover(k.x, 24);
      const c = k.vx > 0 ? cols[cols.length - 1] : cols[0];
      if (rows.some((r) => this.tile(r, c) === '#')) { k.x = k.vx > 0 ? c * TILE - 24 : (c + 1) * TILE; k.vx = 0; }
    }
    // up and down: '#' always, '=' only from above
    const bottomBefore = k.y + 24;
    k.y += k.vy;
    k.ground = false;
    const cols = this.cover(k.x, 24);
    if (k.vy > 0) {
      const r = this.cover(k.y, 24).pop();
      const solid = cols.some((c) => this.tile(r, c) === '#');
      const platform = bottomBefore <= r * TILE && cols.some((c) => this.tile(r, c) === '=');
      if (solid || platform) { k.y = r * TILE - 24; k.vy = 0; k.ground = true; k.floating = false; k.floatT = 0; }
    } else if (k.vy < 0) {
      const r = this.cover(k.y, 24)[0];
      if (cols.some((c) => this.tile(r, c) === '#')) { k.y = (r + 1) * TILE; k.vy = 0; }
    }
    if (k.y > 12 * TILE) { k.hp = 0; this.over = true; return; }
    for (const e of this.foes) {
      if (!e.alive) continue;
      if (e.kind === 'W') {
        const nx = e.x + e.dir / 2;
        const span = this.cover(nx, 24);
        const front = e.dir > 0 ? span[span.length - 1] : span[0];
        const row = Math.floor(e.y / TILE);
        const under = this.tile(row + 1, front);
        if (this.tile(row, front) === '#' || (under !== '#' && under !== '=')) e.dir = -e.dir;
        else e.x = nx;
      } else {
        e.t++;
        e.x += e.dir;
        if (e.t % 128 === 0) e.dir = -e.dir;
        e.y = e.baseY + Math.round(24 * Math.sin(e.t / 16));
      }
    }
    if (k.inhaling) {
      for (const e of this.foes) {
        if (!e.alive) continue;
        const ahead = (e.x - k.x) * k.face;
        if (ahead <= 0 || ahead > 64 || Math.abs(e.y - k.y) >= 32) continue;
        e.x -= 2 * k.face;
        if ((e.x - k.x) * k.face <= 24) { e.alive = false; k.full = e.kind; k.inhaling = false; this.score += 200; break; }
      }
    }
    if (this.shot) {
      const s = this.shot;
      s.x += 6 * s.dir;
      const hit = this.foes.find((e) => e.alive && Oracle.overlap(s.x, s.y, 16, e.x, e.y, 24));
      if (hit) { hit.alive = false; this.score += 200; this.shot = null; }
      else if (this.tile(Math.floor((s.y + 8) / TILE), Math.floor((s.x + 8) / TILE)) === '#') this.shot = null;
    }
    for (const e of this.foes) if (e.alive && k.hurtT === 0 && Oracle.overlap(k.x, k.y, 24, e.x, e.y, 24)) { e.alive = false; this.hurt(); }
    for (const r of this.cover(k.y, 24)) {
      for (const c of this.cover(k.x, 24)) {
        const t = this.tile(r, c);
        if (t === '*') { this.grid[r][c] = '.'; this.score += 100; }
        else if (t === '^') this.hurt();
        else if (t === 'D') this.won = true;
      }
    }
    this.cam = Math.max(0, Math.min(WIDTH - VIEW, Math.floor(k.x + 12 - VIEW / 2)));
  }
  tick(ms) { this.acc += ms * 60; while (this.acc >= 1000) { this.acc -= 1000; this.step(); } }
  input(action, pressed) {
    if (this.over || this.won) return;
    const k = this.k;
    switch (action) {
      case 'left': case 'right': this.held[action] = pressed; break;
      case 'inhale': if (pressed && k.floating) k.floating = false; else this.held.inhale = pressed; break;
      case 'jump':
        if (!pressed) break;
        if (k.ground) { k.vy = k.ability === 'wing' ? -8.5 : -6; k.ground = false; }
        else if (k.full === null && k.floatT < 360) { k.floating = true; k.vy = -2; }
        break;
      case 'swallow': if (pressed && k.full !== null) { k.ability = k.full === 'B' ? 'wing' : 'none'; k.full = null; } break;
      case 'spit':
        if (pressed && k.full !== null) { this.shot = { x: k.face > 0 ? k.x + 24 : k.x - 16, y: k.y + 4, dir: k.face }; k.full = null; }
        break;
      default: break;
    }
  }
  state() {
    const k = this.k;
    return {
      frame: this.frame, score: this.score, cam: this.cam, stars: this.grid.flat().filter((t) => t === '*').length,
      over: this.over, won: this.won, kirby: { ...k },
      enemies: this.foes.map(({ kind, x, y, dir, t, alive }) => ({ kind, x, y, dir, t, alive })),
      shot: this.shot && { ...this.shot },
    };
  }
}

function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])]));
  return v;
}
const same = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
let compared = 0;
function agree(seed, acts) {
  const o = new Oracle(seed), g = R.newGame(seed);
  if (!same(o.state(), R.snapshot(g))) return `seed ${seed}: differ at the start`;
  for (let i = 0; i < acts.length; i++) {
    const a = acts[i];
    if (a[0] === 'in') { o.input(a[1], a[2]); R.input(g, a[1], a[2]); } else { o.tick(a[1]); R.tick(g, a[1]); }
    compared++;
    if (!same(o.state(), R.snapshot(g))) {
      return `seed ${seed}: differ after action ${i} ${JSON.stringify(a)}\n oracle ${JSON.stringify(o.state()).slice(0, 300)}\n ref    ${JSON.stringify(R.snapshot(g)).slice(0, 300)}`;
    }
  }
  return null;
}
function randomActs(seed, n) {
  const rng = R.mulberry32(seed * 104729 + 7);
  const acts = [];
  for (let i = 0; i < n; i++) {
    const p = rng();
    if (p < 0.35) acts.push(['t', 1 + Math.floor(rng() * 150)]);
    else if (p < 0.52) acts.push(['in', 'right', rng() < 0.8]);
    else if (p < 0.6) acts.push(['in', 'left', rng() < 0.4]);
    else if (p < 0.76) acts.push(['in', 'jump', rng() < 0.75]);
    else if (p < 0.88) acts.push(['in', 'inhale', rng() < 0.6]);
    else if (p < 0.94) acts.push(['in', 'swallow', rng() < 0.9]);
    else acts.push(['in', 'spit', rng() < 0.9]);
  }
  return acts;
}
// the travelling player of the harness, on the reference: its inputs, and whether it reached the door
function player(seed, max = 6000) {
  const g = R.newGame(seed), acts = [['in', 'right', true]];
  R.input(g, 'right', true);
  let lastFlap = -100;
  const act = (a) => { acts.push(a); if (a[0] === 'in') R.input(g, a[1], a[2]); else R.tick(g, a[1]); };
  for (let i = 0; i < max && !g.over && !g.won; i++) {
    const k = g.kirby;
    const ahead = (dx, row) => R.tileAt(g, row, Math.floor((k.x + 12 + dx) / 32));
    const enemyNear = g.enemies.some((e) => e.alive && e.x - k.x > 0 && e.x - k.x < 70 && Math.abs(e.y - k.y) < 40);
    if (k.ground) {
      const wall = ahead(28, 9) === '#' || ahead(28, Math.floor(k.y / 32)) === '#';
      const spike = ahead(40, 9) === '^' || ahead(24, 9) === '^';
      const pit = !R.standAt(g, 10, Math.floor((k.x + 42) / 32)) && k.y >= 296;
      if (k.x < 1880 && (wall || spike || pit || enemyNear)) act(['in', 'jump', true]);
    } else {
      const below = [10, 11].some((row) => R.standAt(g, row, Math.floor((k.x + 12) / 32)) || R.standAt(g, row, Math.floor((k.x + 30) / 32)));
      if (k.vy > 0.5 && (!below || ahead(20, 9) === '^' || enemyNear) && g.frame - lastFlap > 12) { act(['in', 'jump', true]); lastFlap = g.frame; }
    }
    act(['t', Math.ceil((1000 - g.acc) / 60)]);
  }
  return { acts, won: g.won, g };
}

check('oracle and reference agree on 300 random games (seeds 1-300, 600 actions each)', () => {
  for (let seed = 1; seed <= 300; seed++) { const d = agree(seed, randomActs(seed, 600)); if (d) return { pass: false, detail: d }; }
  return { pass: true, detail: `${compared} actions compared` };
});
let wins = 0;
check('oracle and reference agree on the travelling player\'s games (seeds 1-20)', () => {
  const before = compared;
  for (let seed = 1; seed <= 20; seed++) {
    const p = player(seed);
    if (p.won) wins++;
    const d = agree(seed, p.acts);
    if (d) return { pass: false, detail: d };
  }
  return { pass: true, detail: `${compared - before} actions compared, ${wins} of 20 games reached the door` };
});

// ------------------------------------------------------------------------------------------------ 2. the numbers
function stepN(g, n) { for (let i = 0; i < n; i++) R.step(g); }

check('walking: +0.125 per step to 2 px/step, friction 0.25 per step to 0', () => {
  const g = R.newGame(1); R.input(g, 'right', true);
  const v = []; for (let i = 0; i < 20; i++) { R.step(g); v.push(g.kirby.vx); }
  R.input(g, 'right', false);
  const f = []; for (let i = 0; i < 10; i++) { R.step(g); f.push(g.kirby.vx); }
  return { pass: v.every((x, i) => x === Math.min(2, 0.125 * (i + 1))) && f.every((x, i) => x === Math.max(0, 2 - 0.25 * (i + 1))), detail: `${v.join(',')} | ${f.join(',')}` };
});
check('jump: vy -6, gravity 0.25, rises 69 px and lands after 48 steps', () => {
  const g = R.newGame(1); R.input(g, 'jump', true);
  let minY = g.kirby.y, n = 0;
  do { R.step(g); minY = Math.min(minY, g.kirby.y); n++; } while (!g.kirby.ground && n < 200);
  return { pass: 296 - minY === 69 && n === 48 && g.kirby.y === 296, detail: `rise ${296 - minY}, ${n} steps` };
});
check('wing: vy -8.5, rises 140.25 px (about twice the 69 px jump)', () => {
  const g = R.newGame(1); g.kirby.ability = 'wing'; R.input(g, 'jump', true);
  let minY = g.kirby.y, n = 0;
  do { R.step(g); minY = Math.min(minY, g.kirby.y); n++; } while (!g.kirby.ground && n < 300);
  const rise = 296 - minY;
  return { pass: rise === 140.25 && rise / 69 > 2 && rise / 69 < 2.1, detail: `rise ${rise} in ${n} steps` };
});
check('float: flap vy -2, slow fall at most 1 px/step (+0.0625), 360 floating steps at most until landing', () => {
  const g = R.newGame(1); R.input(g, 'jump', true); stepN(g, 20); R.input(g, 'jump', true);
  const flap = g.kirby.vy;
  let floating = 0, maxVy = -9;
  while (g.kirby.floating) { if (g.kirby.vy > 0.5) R.input(g, 'jump', true); R.step(g); floating++; if (g.kirby.floating) maxVy = Math.max(maxVy, g.kirby.vy); }
  const t = g.kirby.floatT;
  const again = R.jump(g);
  while (!g.kirby.ground) R.step(g);
  // without flaps the floating fall speeds up by 0.0625 per step and stays at 1
  const h = R.newGame(1); R.input(h, 'jump', true); stepN(h, 10); R.input(h, 'jump', true);
  const vys = []; for (let i = 0; i < 60; i++) { R.step(h); vys.push(h.kirby.vy); }
  const slow = vys.every((v, i) => v === Math.min(1, -2 + 0.0625 * (i + 1))) && h.kirby.floating;
  return { pass: flap === -2 && floating === 360 && t === 360 && again === 'none' && maxVy <= 1 && g.kirby.floatT === 0 && slow,
    detail: JSON.stringify({ flap, floating, t, again, maxVy, last: vys.slice(-3), slow }) };
});
check('inhale: 64 px ahead, |dy| < 32, pulled 2 px/step, inside at 24 px; +200; one at a time', () => {
  const mk = (x, y) => ({ kind: 'W', x, y, dir: 1, t: 0, baseY: y, alive: true });
  const g = R.newGame(1); g.enemies = [mk(104, 296), mk(105, 296), mk(100, 264), mk(100, 265), mk(20, 296)]; g.kirby.inhaling = true;
  R.pull(g);
  const a = g.enemies.map((e) => e.x);
  const h = R.newGame(1); h.enemies = [mk(66, 296), mk(64, 296)];
  R.pull(h);
  return { pass: same(a, [102, 105, 100, 98, 20]) && h.kirby.full === 'W' && h.score === 200 && h.enemies[1].alive && h.enemies[1].x === 64,
    detail: JSON.stringify({ a, full: h.kirby.full, score: h.score }) };
});
check('swallow: waddle-dee gives "none", bronto-burt gives "wing"; spit: a 16 px star at 6 px/step from the mouth', () => {
  const g = R.newGame(1); g.kirby.full = 'B'; R.swallow(g);
  const h = R.newGame(1); h.kirby.full = 'W'; h.kirby.ability = 'wing'; R.swallow(h);
  const s = R.newGame(1); s.kirby.full = 'W'; R.spit(s); const x0 = s.shot.x; R.shotStep(s);
  return { pass: g.kirby.ability === 'wing' && h.kirby.ability === 'none' && x0 === 64 && s.shot.x === 70 && s.shot.y === 300,
    detail: JSON.stringify([g.kirby.ability, h.kirby.ability, x0, s.shot]) };
});
check('damage: 6 HP, -1 per hit, knockback (-2 x face, -3), 90 invulnerable steps, 0 HP is game over and never below 0', () => {
  const g = R.newGame(1);
  const hps = [];
  for (let i = 0; i < 8; i++) { R.hurt(g); hps.push(g.kirby.hp); g.kirby.hurtT = 0; }
  const h = R.newGame(1); h.kirby.face = -1; R.hurt(h); const k = h.kirby;
  const again = R.hurt(h);
  return { pass: same(hps, [5, 4, 3, 2, 1, 0, 0, 0]) && g.over && k.vx === 2 && k.vy === -3 && k.hurtT === 90 && again === false,
    detail: JSON.stringify({ hps, over: g.over, k: [k.vx, k.vy, k.hurtT] }) };
});
check('spikes hurt once per invulnerability; stars count once (+100); the door completes the level', () => {
  const g = R.newGame(1); g.tiles[9][1] = '^'; R.touchTiles(g); R.touchTiles(g); const hp = g.kirby.hp;
  const s = R.newGame(1); s.tiles[9][1] = '*'; R.touchTiles(s); R.touchTiles(s);
  const d = R.newGame(1); d.tiles[9][1] = 'D'; R.touchTiles(d); stepN(d, 5);
  return { pass: hp === 5 && s.score === 100 && d.won && d.frame === 0, detail: JSON.stringify([hp, s.score, d.won, d.frame]) };
});
check('waddle-dees walk 0.5 px/step and turn at walls and ledges; bronto-burts follow the sine through tiles', () => {
  const g = R.newGame(1);
  const xs = g.enemies.map(() => []);
  for (let i = 0; i < 3000; i++) { R.moveEnemies(g); g.enemies.forEach((e, j) => xs[j].push(e.x)); }
  const ranges = xs.map((v) => [Math.min(...v), Math.max(...v)]);
  const sine = g.enemies.filter((e) => e.kind === 'B').every((e) => e.y === e.baseY + Math.round(24 * Math.sin(e.t / 16)));
  return { pass: same(ranges[1], [1056, 1224]) && same(ranges[3], [320, 616]) && same(ranges[4], [320, 616]) && same(ranges[5], [1568, 2024]) && sine,
    detail: JSON.stringify(ranges) };
});
check('camera: floor(x + 12 - 320) clamped to 0..1408; time: 1000 ms = 60 steps, remainder kept', () => {
  const cams = [40, 308, 309.5, 1000, 1716, 2024].map(R.cameraX);
  const g = R.newGame(1); R.tick(g, 16); const a = g.frame; R.tick(g, 1); const b = g.frame; R.tick(g, 1000);
  return { pass: same(cams, [0, 0, 1, 692, 1408, 1408]) && a === 0 && b === 1 && g.frame === 61 && g.acc === 20, detail: JSON.stringify({ cams, a, b, frame: g.frame, acc: g.acc }) };
});

// ------------------------------------------------------------------------------------------------ 3. level and sheet
check('the level: 12 x 64, only the specified letters, 11 stars, 6 enemies, one door, every waddle-dee on ground', () => {
  const L = R.LEVEL;
  const letters = new Set(L.join(''));
  const ws = [];
  L.forEach((row, r) => [...row].forEach((ch, c) => { if (ch === 'W') ws.push([r, c]); }));
  const grounded = ws.every(([r, c]) => L[r + 1] && (L[r + 1][c] === '#' || L[r + 1][c] === '='));
  const count = (ch) => L.join('').split(ch).length - 1;
  return { pass: L.length === 12 && L.every((row) => row.length === 64) && [...letters].every((ch) => '.#=^*DWB'.includes(ch)) &&
    count('*') === 11 && count('W') + count('B') === 6 && count('D') === 1 && grounded && same(L, ROWS), detail: JSON.stringify({ letters: [...letters].join(''), ws }) };
});
check('the level can be completed: the travelling player reaches the door on most seeds', () => ({ pass: wins >= 15, detail: `${wins} of 20` }));
check('every example in kirby.sheet.md equals the reference\'s value (fill-sheet.mjs check)', () => {
  const r = runSheet(fs.readFileSync(path.join(HERE, '..', 'sheets', 'kirby.sheet.md'), 'utf8'));
  const pending = r.sheet.units.reduce((n, u) => n + u.examples.filter(([, e]) => e === '?').length, 0);
  return { pass: r.bad === 0 && pending === 0, detail: `${r.sheet.units.length} units, ${r.total} examples, ${r.bad} differing, ${pending} unfilled${r.report.length ? '\n' + r.report[0] : ''}` };
});

for (const r of results) console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? '  ::  ' + r.detail : ''}`);
const passed = results.filter((r) => r.pass).length;
console.log(`check-ref ${passed}/${results.length}`);
process.exit(passed === results.length ? 0 : 1);

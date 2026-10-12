// Do the sheet's examples reject wrong answers? Each mutant is one unit's reference code with one plausible slip of a
// small model (a wrong constant, a swapped order, an off-by-one, a missing step); it is run against that unit's
// examples exactly as the build's js_test runs them (the unit's test setup, the earlier units, then the unit, each as
// its own script). A mutant no example rejects is a hole the kernel would let through to the page, where only the
// harness would find it (2026-10-10: llama3.2:1b passed 37 of 37 units and scored 243 of 500 on the harness).
//
//   node kits/kirby/harness/sheet-mutants.mjs    prints every mutant as caught or MISSED; exit 0 only when all are
//                                                caught (reads ../sheets/kirby.sheet.md)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseSheet, referenceDeclarations, unitSources, evaluate, sameJson } from '../reference/fill-sheet.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
// [first name of the unit, what the slip is, text in that unit's reference code, replacement]
const MUTANTS = [
  ['LEVEL', 'one dot dropped from a row', "'.........................***....................................',", "'.........................***...................................',"],
  ['mulberry32', 'a different increment', 'a = a + 0x6D2B79F5 | 0;', 'a = a + 0x6D2B79F4 | 0;'],
  ['tileAt', 'the bottom closed', "if (r > 11) return '.';", "if (r > 11) return '#';"],
  ['tileAt', 'the top open', "if (r < 0) return '#';", "if (r < 0) return '.';"],
  ['tileAt', 'standAt without platforms', "return t === '#' || t === '=';", "return t === '#';"],
  ['span', 'floor instead of ceil - 1', 'Math.ceil((a + size) / 32) - 1', 'Math.floor((a + size) / 32)'],
  ['solidRow', 'one column short', 'for (let c = c0; c <= c1; c++) if (solidAt(g, r, c)) return true;', 'for (let c = c0; c < c1; c++) if (solidAt(g, r, c)) return true;'],
  ['solidRow', 'solidCol tests the platform too', 'for (let r = r0; r <= r1; r++) if (solidAt(g, r, c)) return true;', 'for (let r = r0; r <= r1; r++) if (standAt(g, r, c)) return true;'],
  ['makeEnemy', 'the PRNG calls swapped', "  const dir = rng() < 0.5 ? -1 : 1;\n  const t = Math.floor(rng() * 64);", "  const t = Math.floor(rng() * 64);\n  const dir = rng() < 0.5 ? -1 : 1;"],
  ['makeEnemy', 'standing on the tile top', 'y: r * 32 + 8, dir', 'y: r * 32, dir'],
  ['parseLevel', 'the spawn letter kept as a tile', "        enemies.push(makeEnemy(ch, r, c, rng));\n        row.push('.');", "        enemies.push(makeEnemy(ch, r, c, rng));\n        row.push(ch);"],
  ['newGame', 'not standing at the start', 'ground: true, floating', 'ground: false, floating'],
  ['cameraX', 'rounded instead of floored', 'Math.floor(x + 12 - 320)', 'Math.round(x + 12 - 320)'],
  ['cameraX', 'no right clamp', 'return Math.min(1408, Math.max(0, Math.floor(x + 12 - 320)));', 'return Math.max(0, Math.floor(x + 12 - 320));'],
  ['walk', 'walking while inhaling', 'const right = g.keys.right && !g.keys.left && !k.inhaling;', 'const right = g.keys.right && !g.keys.left;'],
  ['walk', 'face not turned', '    k.vx = Math.max(-2, k.vx - 0.125);\n    k.face = -1;', '    k.vx = Math.max(-2, k.vx - 0.125);'],
  ['walk', 'both keys walk right', 'const right = g.keys.right && !g.keys.left && !k.inhaling;', 'const right = g.keys.right && !k.inhaling;'],
  ['fall', 'gravity before the float timer', "  if (k.floating) {\n    k.floatT += 1;\n    if (k.floatT >= 360) k.floating = false;\n  }\n  if (k.floating) k.vy = Math.min(1, k.vy + 0.0625);\n  else k.vy = Math.min(6, k.vy + 0.25);", "  if (k.floating) k.vy = Math.min(1, k.vy + 0.0625);\n  else k.vy = Math.min(6, k.vy + 0.25);\n  if (k.floating) {\n    k.floatT += 1;\n    if (k.floatT >= 360) k.floating = false;\n  }"],
  ['fall', 'float limit off by one', 'if (k.floatT >= 360) k.floating = false;', 'if (k.floatT > 360) k.floating = false;'],
  ['moveX', 'right edge column by floor', 'const c = Math.ceil((k.x + 24) / 32) - 1;', 'const c = Math.floor((k.x + 24) / 32);'],
  ['moveX', 'speed kept at a wall', 'if (solidCol(g, c, k.y, 24)) { k.x = c * 32 - 24; k.vx = 0; }', 'if (solidCol(g, c, k.y, 24)) { k.x = c * 32 - 24; }'],
  ['moveY', 'platforms hold from below too', 'if (solidRow(g, r, k.x, 24) || (before <= r * 32 && standRow(g, r, k.x, 24))) {', 'if (standRow(g, r, k.x, 24)) {'],
  ['moveY', 'landing keeps floating', '      k.ground = true;\n      k.floating = false;\n      k.floatT = 0;', '      k.ground = true;'],
  ['moveY', 'ground flag not cleared', '  k.y += k.vy;\n  k.ground = false;', '  k.y += k.vy;'],
  ['moveY', 'no ceiling', "    if (solidRow(g, r, k.x, 24)) { k.y = r * 32 + 32; k.vy = 0; }", ''],
  ['jump', 'wing ignored', "k.vy = k.ability === 'wing' ? -8.5 : -6;", 'k.vy = -6;'],
  ['jump', 'a full Kirby floats', 'if (k.full === null && k.floatT < 360) {', 'if (k.floatT < 360) {'],
  ['jump', 'ground kept after a jump', "    k.vy = k.ability === 'wing' ? -8.5 : -6;\n    k.ground = false;", "    k.vy = k.ability === 'wing' ? -8.5 : -6;"],
  ['hurt', 'invulnerability ignored', '  if (k.hurtT > 0) return false;\n', ''],
  ['hurt', 'knockback toward the face', 'k.vx = -2 * k.face;', 'k.vx = 2 * k.face;'],
  ['hurt', 'HP below 0', '    k.hp = 0;\n    g.over = true;', '    g.over = true;'],
  ['boxesTouch', 'shared edges touch', 'return ax < bx + bw && bx < ax + aw && ay < by + bw && by < ay + aw;', 'return ax <= bx + bw && bx <= ax + aw && ay <= by + bw && by <= ay + aw;'],
  ['inFront', 'behind counts', 'return dx > 0 && dx <= 64 && Math.abs(e.y - k.y) < 32;', 'return Math.abs(dx) <= 64 && Math.abs(e.y - k.y) < 32;'],
  ['inFront', 'one tile up or down counts', 'Math.abs(e.y - k.y) < 32', 'Math.abs(e.y - k.y) <= 32'],
  ['pull', 'pulled away from Kirby', 'e.x -= 2 * k.face;', 'e.x += 2 * k.face;'],
  ['pull', 'several at once', '      g.score += 200;\n      return;', '      g.score += 200;'],
  ['pull', 'no score', '      k.inhaling = false;\n      g.score += 200;', '      k.inhaling = false;'],
  ['waddleStep', 'ledge tested in its own row', 'if (solidAt(g, r, c) || !standAt(g, r + 1, c)) {', 'if (solidAt(g, r, c) || !standAt(g, r, c)) {'],
  ['waddleStep', 'turns and moves', '    e.dir = -e.dir;\n    return;\n  }\n  e.x = nx;', '    e.dir = -e.dir;\n  }\n  e.x = nx;'],
  ['brontoStep', 'turn before the phase step', '  e.t += 1;\n  e.x += e.dir;\n  if (e.t % 128 === 0) e.dir = -e.dir;', '  if (e.t % 128 === 0) e.dir = -e.dir;\n  e.t += 1;\n  e.x += e.dir;'],
  ['brontoStep', 'sine of degrees', 'Math.sin(e.t / 16)', 'Math.sin(e.t * 16)'],
  ['moveEnemies', 'moves dead enemies', '    if (!e.alive) continue;\n', ''],
  ['swallow', 'every enemy gives wing', "k.ability = k.full === 'B' ? 'wing' : 'none';", "k.ability = 'wing';"],
  ['swallow', 'spit keeps the mouth full', "  g.shot = { x: k.face > 0 ? k.x + 24 : k.x - 16, y: k.y + 4, dir: k.face };\n  k.full = null;", "  g.shot = { x: k.face > 0 ? k.x + 24 : k.x - 16, y: k.y + 4, dir: k.face };"],
  ['swallow', 'spit left from the wrong side', 'k.face > 0 ? k.x + 24 : k.x - 16', 'k.face > 0 ? k.x + 24 : k.x - 24'],
  ['shotStep', 'a star through walls', "  if (solidAt(g, Math.floor((s.y + 8) / 32), Math.floor((s.x + 8) / 32))) g.shot = null;", ''],
  ['shotStep', 'a star through enemies', '      g.score += 200;\n      g.shot = null;\n      return;', '      g.score += 200;'],
  ['touchEnemies', 'a bump scores', '      e.alive = false;\n      hurt(g);', '      e.alive = false;\n      g.score += 200;\n      hurt(g);'],
  ['touchEnemies', 'bumps while invulnerable', 'if (e.alive && k.hurtT === 0 && boxesTouch(k.x, k.y, 24, e.x, e.y, 24)) {', 'if (e.alive && boxesTouch(k.x, k.y, 24, e.x, e.y, 24)) {'],
  ['touchTiles', 'stars stay', "        g.tiles[r][c] = '.';\n        g.score += 100;", '        g.score += 100;'],
  ['touchTiles', 'no door', "      } else if (t === 'D') {\n        g.won = true;\n      }", '      }'],
  ['step', 'enemies after the pull', '  moveEnemies(g);\n  if (k.inhaling) pull(g);', '  if (k.inhaling) pull(g);\n  moveEnemies(g);'],
  ['step', 'bumps before the star', '  shotStep(g);\n  touchEnemies(g);', '  touchEnemies(g);\n  shotStep(g);'],
  ['step', 'tiles before bumps', '  touchEnemies(g);\n  touchTiles(g);', '  touchTiles(g);\n  touchEnemies(g);'],
  ['step', 'pit check after the enemies', '  if (k.y > 384) {\n    k.hp = 0;\n    g.over = true;\n    return;\n  }\n  moveEnemies(g);', '  moveEnemies(g);\n  if (k.y > 384) {\n    k.hp = 0;\n    g.over = true;\n    return;\n  }'],
  ['step', 'camera before the moves', '  walk(g);\n  fall(g);\n  moveX(g);\n  moveY(g);\n  if (k.y > 384) {\n    k.hp = 0;\n    g.over = true;\n    return;\n  }\n  moveEnemies(g);\n  if (k.inhaling) pull(g);\n  shotStep(g);\n  touchEnemies(g);\n  touchTiles(g);\n  g.cam = cameraX(k.x);', '  g.cam = cameraX(k.x);\n  walk(g);\n  fall(g);\n  moveX(g);\n  moveY(g);\n  if (k.y > 384) {\n    k.hp = 0;\n    g.over = true;\n    return;\n  }\n  moveEnemies(g);\n  if (k.inhaling) pull(g);\n  shotStep(g);\n  touchEnemies(g);\n  touchTiles(g);'],
  ['step', 'invulnerability counted at the end', '  if (k.hurtT > 0) k.hurtT -= 1;\n', ''],
  ['step', 'moveY before moveX', '  moveX(g);\n  moveY(g);', '  moveY(g);\n  moveX(g);'],
  ['step', 'fall after the moves', '  walk(g);\n  fall(g);\n  moveX(g);\n  moveY(g);', '  walk(g);\n  moveX(g);\n  moveY(g);\n  fall(g);'],
  ['step', 'inhaling while floating', 'k.inhaling = g.keys.inhale && !k.floating && k.full === null;', 'k.inhaling = g.keys.inhale && k.full === null;'],
  ['step', 'frozen game still counts frames', '  if (g.over || g.won) return;\n  const k = g.kirby;\n  g.frame += 1;', '  const k = g.kirby;\n  g.frame += 1;\n  if (g.over || g.won) return;'],
  ['tick', 'one step per ms', 'g.acc += ms * 60;', 'g.acc += ms;'],
  ['tick', 'strictly over 1000', 'while (g.acc >= 1000) {', 'while (g.acc > 1000) {'],
  ['input', 'a release jumps', "  } else if (pressed && action === 'jump') {", "  } else if (action === 'jump') {"],
  ['input', 'exhale also holds inhale', '    if (pressed && k.floating) k.floating = false;\n    else g.keys.inhale = pressed;', '    if (pressed && k.floating) k.floating = false;\n    g.keys.inhale = pressed;'],
  ['input', 'input after the end', '  if (g.over || g.won) return;\n', ''],
  ['snapshot', 'baseY leaks', 'enemies: g.enemies.map((e) => ({ kind: e.kind, x: e.x, y: e.y, dir: e.dir, t: e.t, alive: e.alive })),', 'enemies: g.enemies.map((e) => ({ ...e })),'],
  ['snapshot', 'the shot shared', 'shot: g.shot === null ? null : { x: g.shot.x, y: g.shot.y, dir: g.shot.dir },', 'shot: g.shot,'],
  ['keyAction', "'Z' forgotten", " || k === 'z' || k === 'Z') return 'jump';", " || k === 'z') return 'jump';"],
  ['keyAction', 'modifiers ignored', '  if (e.ctrlKey || e.altKey || e.metaKey) return null;\n', ''],
  ['handleKey', 'repeat before preventDefault', '  e.preventDefault();\n  if (e.repeat) return false;', '  if (e.repeat) return false;\n  e.preventDefault();'],
  ['handleKey', 'restart on key up', "  if (act === 'restart') return pressed;", "  if (act === 'restart') return true;"],
  ['circle', 'half a circle', 'ctx.arc(x, y, r, 0, Math.PI * 2);', 'ctx.arc(x, y, r, 0, Math.PI);'],
  ['circle', 'diamond not closed', '  ctx.closePath();\n  ctx.fill();', '  ctx.fill();'],
  ['drawTile', 'a full-height platform', "ctx.fillStyle = '#c68642'; ctx.fillRect(x, y, 32, 8);", "ctx.fillStyle = '#c68642'; ctx.fillRect(x, y, 32, 32);"],
  ['drawTile', 'no grass', "ctx.fillRect(x, y, 32, 32); ctx.fillStyle = '#5c9e32'; ctx.fillRect(x, y, 32, 8);", 'ctx.fillRect(x, y, 32, 32);'],
  ['drawTiles', 'one column short', 'for (let c = c0; c <= c0 + 20; c++) {', 'for (let c = c0; c < c0 + 20; c++) {'],
  ['drawTiles', 'camera ignored', 'if (c < 64) drawTile(ctx, g.tiles[r][c], c * 32 - g.cam, r * 32);', 'if (c < 64) drawTile(ctx, g.tiles[r][c], c * 32, r * 32);'],
  ['drawKirby', 'blink inverted', 'Math.floor(k.hurtT / 4) % 2 === 1', 'Math.floor(k.hurtT / 4) % 2 === 0'],
  ['drawKirby', 'full radius 15', 'const r = k.floating ? 15 : k.full !== null ? 14 : 12;', 'const r = k.floating || k.full !== null ? 15 : 12;'],
  ['drawKirby', 'eyes not mirrored', 'ctx.fillRect(x + 6 * k.face - 1, y - 7, 2, 6);', 'ctx.fillRect(x + 6 - 1, y - 7, 2, 6);'],
  ['drawEnemy', 'dead enemies drawn', '  if (!e.alive) return;\n', ''],
  ['drawEnemy', 'bronto-burt without wings', "    circle(ctx, x - 9, y - 9, 6, '#ffffff');\n    circle(ctx, x + 9, y - 9, 6, '#ffffff');\n", ''],
  ['drawHud', 'one HP square too many', "ctx.fillStyle = i < k.hp ? '#ff69b4' : '#555';", "ctx.fillStyle = i <= k.hp ? '#ff69b4' : '#555';"],
  ['drawHud', 'alignment left centred', "    ctx.fillText(g.over ? 'GAME OVER' : 'LEVEL COMPLETE', 320, 192);\n    ctx.textAlign = 'left';", "    ctx.fillText(g.over ? 'GAME OVER' : 'LEVEL COMPLETE', 320, 192);"],
  ['draw', 'no sky', "  ctx.fillStyle = '#87ceeb';\n  ctx.fillRect(0, 0, 640, 384);\n", ''],
  ['draw', 'the star at the wrong height', 'diamond(ctx, g.shot.x + 8 - g.cam, g.shot.y + 8, 9', 'diamond(ctx, g.shot.x + 8 - g.cam, g.shot.y, 9'],
  ['startGame', 'reset keeps real time', 'reset(seed) { game = newGame(seed); testMode = true; paint(); },', 'reset(seed) { game = newGame(seed); paint(); },'],
  ['startGame', 'no 100 ms cap', 'const ms = Math.min(100, Math.max(0, t - last));', 'const ms = Math.max(0, t - last);'],
  ['startGame', 'no key up listener', "  document.addEventListener('keyup', (e) => { if (handleKey(game, e, false)) game = newGame(Date.now()); paint(); });\n", ''],
];

const sheet = parseSheet(fs.readFileSync(path.join(HERE, '..', 'sheets', 'kirby.sheet.md'), 'utf8'));
const sources = unitSources(sheet, referenceDeclarations());
let caught = 0, problems = 0;
for (const [first, what, find, repl] of MUTANTS) {
  const i = sheet.units.findIndex((u) => u.names[0] === first);
  if (i < 0) { console.log(`ERROR    ${first}: no such unit`); problems++; continue; }
  const n = sources[i].split(find).length - 1;
  if (n !== 1) { console.log(`ERROR    ${first} / ${what}: the text is found ${n} times`); problems++; continue; }
  const unit = sheet.units[i];
  const pieces = (unit.setup ? [unit.setup] : []).concat(sources.slice(0, i), [sources[i].replace(find, () => repl)]);
  let failing = 0;
  for (const [call, expect] of unit.examples) {
    let ok = false;
    try { ok = sameJson(JSON.parse(evaluate(pieces, call)), JSON.parse(expect)); } catch (_) { ok = false; }
    if (!ok) failing++;
  }
  if (failing) caught++;
  console.log(`${failing ? 'caught ' : 'MISSED '}  ${unit.heading.slice(0, 34).padEnd(34)} ${what.padEnd(36)} ${failing}/${unit.examples.length} examples fail`);
}
console.log(`sheet mutants caught by their unit's examples: ${caught}/${MUTANTS.length - problems}${problems ? `, ${problems} not applied` : ''}`);
process.exit(caught === MUTANTS.length ? 0 : 1);

// Mutation test of harness.mjs: each mutant is the reference page (../reference/assemble-ref.mjs) with one rule
// broken, and the harness must reject every one of them (exit 1). Run after changing the harness or the reference.
//
//   node kits/kirby/harness/mutants.mjs REF_PAGE.html SCRATCH_DIR [NAME_REGEX]
//
// Mutant pages are written to SCRATCH_DIR (outside the repository). Two harness processes run at a time.
import fs from 'node:fs';
import { execFile } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const [refPage, outDir, only] = process.argv.slice(2);
if (!refPage || !outDir) { console.error('usage: node mutants.mjs REF_PAGE.html SCRATCH_DIR [NAME_REGEX]'); process.exit(2); }
const harness = path.join(path.dirname(fileURLToPath(import.meta.url)), 'harness.mjs');
fs.mkdirSync(outDir, { recursive: true });
const page = fs.readFileSync(refPage, 'utf8');
const ALL = [
  ['walk accel 0.125 -> 0.25', 'k.vx = Math.min(2, k.vx + 0.125);', 'k.vx = Math.min(2, k.vx + 0.25);'],
  ['friction 0.25 -> 0.125', 'k.vx = Math.max(0, k.vx - 0.25);', 'k.vx = Math.max(0, k.vx - 0.125);'],
  ['max walk 2 -> 2.5', 'k.vx = Math.min(2, k.vx + 0.125);', 'k.vx = Math.min(2.5, k.vx + 0.125);'],
  ['gravity 0.25 -> 0.3125', 'else k.vy = Math.min(6, k.vy + 0.25);', 'else k.vy = Math.min(6, k.vy + 0.3125);'],
  ['max fall 6 -> 5', 'else k.vy = Math.min(6, k.vy + 0.25);', 'else k.vy = Math.min(5, k.vy + 0.25);'],
  ['jump -6 -> -5.5', "k.vy = k.ability === 'wing' ? -8.5 : -6;", "k.vy = k.ability === 'wing' ? -8.5 : -5.5;"],
  ['wing -8.5 -> -8', "k.vy = k.ability === 'wing' ? -8.5 : -6;", "k.vy = k.ability === 'wing' ? -8 : -6;"],
  ['float gravity 1/16 -> 1/8', 'if (k.floating) k.vy = Math.min(1, k.vy + 0.0625);', 'if (k.floating) k.vy = Math.min(1, k.vy + 0.125);'],
  ['float max fall 1 -> 1.5', 'if (k.floating) k.vy = Math.min(1, k.vy + 0.0625);', 'if (k.floating) k.vy = Math.min(1.5, k.vy + 0.0625);'],
  ['float limit 360 -> 300', 'if (k.floatT >= 360) k.floating = false;', 'if (k.floatT >= 300) k.floating = false;'],
  ['flap -2 -> -2.5', "    k.floating = true;\n    k.vy = -2;", "    k.floating = true;\n    k.vy = -2.5;"],
  ['no float limit on re-inflate', 'if (k.full === null && k.floatT < 360) {', 'if (k.full === null) {'],
  ['full Kirby can float', 'if (k.full === null && k.floatT < 360) {', 'if (k.floatT < 360) {'],
  ['invulnerable 90 -> 60', 'k.hurtT = 90;', 'k.hurtT = 60;'],
  ['knockback toward the face', 'k.vx = -2 * k.face;', 'k.vx = 2 * k.face;'],
  ['hurt keeps floating', "  k.vy = -3;\n  k.floating = false;", "  k.vy = -3;"],
  ['HP may go below 0', "    k.hp = 0;\n    g.over = true;\n  }\n  return true;", "    g.over = true;\n  }\n  return true;"],
  ['inhale range 64 -> 80', 'return dx > 0 && dx <= 64 && Math.abs(e.y - k.y) < 32;', 'return dx > 0 && dx <= 80 && Math.abs(e.y - k.y) < 32;'],
  ['inhale reaches behind', 'return dx > 0 && dx <= 64 && Math.abs(e.y - k.y) < 32;', 'return Math.abs(dx) <= 64 && Math.abs(e.y - k.y) < 32;'],
  ['pull 2 -> 3', 'e.x -= 2 * k.face;', 'e.x -= 3 * k.face;'],
  ['capture at 24 -> 16', 'if ((e.x - k.x) * k.face <= 24) {', 'if ((e.x - k.x) * k.face <= 16) {'],
  ['capture score 200 -> 100', "      k.inhaling = false;\n      g.score += 200;", "      k.inhaling = false;\n      g.score += 100;"],
  ['waddle speed 0.5 -> 1', 'const nx = e.x + 0.5 * e.dir;', 'const nx = e.x + 1 * e.dir;'],
  ['waddle ignores ledges', 'if (solidAt(g, r, c) || !standAt(g, r + 1, c)) {', 'if (solidAt(g, r, c)) {'],
  ['waddle ignores walls', 'if (solidAt(g, r, c) || !standAt(g, r + 1, c)) {', 'if (!standAt(g, r + 1, c)) {'],
  ['bronto turns every 100', 'if (e.t % 128 === 0) e.dir = -e.dir;', 'if (e.t % 100 === 0) e.dir = -e.dir;'],
  ['bronto amplitude 20', 'e.y = e.baseY + Math.round(24 * Math.sin(e.t / 16));', 'e.y = e.baseY + Math.round(20 * Math.sin(e.t / 16));'],
  ['shot speed 5', 's.x += 6 * s.dir;', 's.x += 5 * s.dir;'],
  ['shot y offset 0', 'g.shot = { x: k.face > 0 ? k.x + 24 : k.x - 16, y: k.y + 4, dir: k.face };', 'g.shot = { x: k.face > 0 ? k.x + 24 : k.x - 16, y: k.y, dir: k.face };'],
  ['shot passes walls', "  if (solidAt(g, Math.floor((s.y + 8) / 32), Math.floor((s.x + 8) / 32))) g.shot = null;", ''],
  ['swallow W gives wing', "k.ability = k.full === 'B' ? 'wing' : 'none';", "k.ability = 'wing';"],
  ['star 100 -> 50', "        g.tiles[r][c] = '.';\n        g.score += 100;", "        g.tiles[r][c] = '.';\n        g.score += 50;"],
  ['stars count again', "        g.tiles[r][c] = '.';\n        g.score += 100;", "        g.score += 100;"],
  ['door does nothing', "      } else if (t === 'D') {\n        g.won = true;", "      } else if (t === 'D') {\n        g.won = false;"],
  ['camera max 1500', 'return Math.min(1408, Math.max(0, Math.floor(x + 12 - 320)));', 'return Math.min(1500, Math.max(0, Math.floor(x + 12 - 320)));'],
  ['camera centre 300', 'return Math.min(1408, Math.max(0, Math.floor(x + 12 - 320)));', 'return Math.min(1408, Math.max(0, Math.floor(x + 12 - 300)));'],
  ['tick 61 per second', 'g.acc += ms * 60;', 'g.acc += ms * 61;'],
  ['top is open', "  if (r < 0) return '#';", "  if (r < 0) return '.';"],
  ['platforms always solid', 'if (solidRow(g, r, k.x, 24) || (before <= r * 32 && standRow(g, r, k.x, 24))) {', 'if (standRow(g, r, k.x, 24)) {'],
  ['pit at 400', 'if (k.y > 384) {', 'if (k.y > 400) {'],
  ['contact before tiles swapped', "  touchEnemies(g);\n  touchTiles(g);", "  touchTiles(g);\n  touchEnemies(g);"],
  ['enemies move after the shot', "  moveEnemies(g);\n  if (k.inhaling) pull(g);\n  shotStep(g);", "  if (k.inhaling) pull(g);\n  shotStep(g);\n  moveEnemies(g);"],
  ['exhale also inhales', '    if (pressed && k.floating) k.floating = false;\n    else g.keys.inhale = pressed;', '    if (pressed && k.floating) k.floating = false;\n    g.keys.inhale = pressed;'],
  ['jump on release too', "  } else if (pressed && action === 'jump') {", "  } else if (action === 'jump') {"],
  ['input after game over', '  if (g.over || g.won) return;\n  const k = g.kirby;\n  if (action ===', '  const k = g.kirby;\n  if (action ==='],
  ['makeEnemy phase *32', 'const t = Math.floor(rng() * 64);', 'const t = Math.floor(rng() * 32);'],
  ['snapshot without stars', 'frame: g.frame, score: g.score, cam: g.cam, stars, over: g.over, won: g.won,', 'frame: g.frame, score: g.score, cam: g.cam, over: g.over, won: g.won,'],
  ['snapshot shares the shot', 'shot: g.shot === null ? null : { x: g.shot.x, y: g.shot.y, dir: g.shot.dir },', 'shot: g.shot,'],
  ["'z' not a jump key", "if (k === 'ArrowUp' || k === ' ' || k === 'w' || k === 'W' || k === 'z' || k === 'Z') return 'jump';", "if (k === 'ArrowUp' || k === ' ' || k === 'w' || k === 'W' || k === 'Z') return 'jump';"],
  ['key repeat acts', '  if (e.repeat) return false;\n', ''],
  ['no preventDefault', '  e.preventDefault();\n  if (e.repeat) return false;', '  if (e.repeat) return false;'],
  ['reset keeps real time', 'reset(seed) { game = newGame(seed); testMode = true; paint(); },', 'reset(seed) { game = newGame(seed); paint(); },'],
  ['no 100 ms cap', 'const ms = Math.min(100, Math.max(0, t - last));', 'const ms = Math.max(0, t - last);'],
  ['blink inverted', 'if (k.hurtT > 0 && Math.floor(k.hurtT / 4) % 2 === 1) return;', 'if (k.hurtT > 0 && Math.floor(k.hurtT / 4) % 2 === 0) return;'],
  ['no GAME OVER text', "ctx.fillText(g.over ? 'GAME OVER' : 'LEVEL COMPLETE', 320, 192);", "ctx.fillText(g.over ? 'OVER' : 'LEVEL COMPLETE', 320, 192);"],
  ['tiles drawn without camera', 'if (c < 64) drawTile(ctx, g.tiles[r][c], c * 32 - g.cam, r * 32);', 'if (c < 64) drawTile(ctx, g.tiles[r][c], c * 32, r * 32);'],
  ['Kirby radius 13', "const r = k.floating ? 15 : k.full !== null ? 14 : 12;", "const r = k.floating ? 15 : k.full !== null ? 14 : 13;"],
  ['moveY before moveX', '  moveX(g);\n  moveY(g);', '  moveY(g);\n  moveX(g);'],
  ['camera before the moves', '  walk(g);\n  fall(g);\n  moveX(g);\n  moveY(g);\n  if (k.y > 384) {\n    k.hp = 0;\n    g.over = true;\n    return;\n  }\n  moveEnemies(g);\n  if (k.inhaling) pull(g);\n  shotStep(g);\n  touchEnemies(g);\n  touchTiles(g);\n  g.cam = cameraX(k.x);', '  g.cam = cameraX(k.x);\n  walk(g);\n  fall(g);\n  moveX(g);\n  moveY(g);\n  if (k.y > 384) {\n    k.hp = 0;\n    g.over = true;\n    return;\n  }\n  moveEnemies(g);\n  if (k.inhaling) pull(g);\n  shotStep(g);\n  touchEnemies(g);\n  touchTiles(g);'],
  ['level star moved', "'.........................***....................................',", "'........................***.....................................',"],
];
const M = only ? ALL.filter(([n]) => new RegExp(only).test(n)) : ALL;
const run = (file) => new Promise((resolve) => {
  execFile(process.execPath, [harness, file], { maxBuffer: 1 << 24, timeout: 300000 }, (err, stdout) => {
    const fails = (stdout.match(/^FAIL .*$/mg) || []);
    resolve({ code: err ? (err.code ?? 1) : 0, fails, summary: (stdout.match(/required \d+\/\d+/) || ['?'])[0] });
  });
});
const rows = [];
let next = 0;
async function worker() {
  while (next < M.length) {
    const i = next++;
    const [name, find, repl] = M[i];
    const n = page.split(find).length - 1;
    if (n !== 1) { rows[i] = { name, error: `pattern found ${n} times` }; continue; }
    const file = `${outDir}/m${String(i).padStart(2, '0')}.html`;
    fs.writeFileSync(file, page.replace(find, () => repl));
    const r = await run(file);
    rows[i] = { name, detected: r.code !== 0, summary: r.summary, first: r.fails[0] ? r.fails[0].slice(6, 90) : '' };
  }
}
await Promise.all([worker(), worker()]);
let detected = 0;
for (const r of rows) {
  if (r.error) { console.log(`ERROR     ${r.name}: ${r.error}`); continue; }
  if (r.detected) detected++;
  console.log(`${r.detected ? 'rejected' : 'MISSED  '}  ${r.name.padEnd(32)} ${r.summary.padEnd(14)} ${r.first}`);
}
const total = rows.filter((r) => !r.error).length;
console.log(`mutants rejected ${detected}/${total}`);
process.exit(detected === total && rows.every((r) => !r.error) ? 0 : 1);

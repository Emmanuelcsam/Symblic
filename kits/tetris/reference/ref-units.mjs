// The Tetris spec sheet's reference, written as the same small units the spec sheet asks models to write.
// It is the spec author's tool: it computes each unit's examples and is checked against reference.mjs (the oracle)
// by check-ref-units.mjs. Models never see this file.
//
// Game state g (the shared contract every unit reads and writes):
//   board: 22 arrays of 10 strings ('' or a piece letter): the locked cells only
//   queue: array of upcoming piece letters, front first        rng: function returning a number in [0, 1)
//   active: {type, rot, row, col} or null                       hold: a letter or null      holdUsed: boolean
//   score, lines: integers      over, paused: booleans
//   fall: ms counted toward the next gravity row                lock: ms counted toward locking
//   resets: lock-timer restarts this piece has used

export function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

export const SHAPES = {
  I: { n: 4, cells: [[1, 0], [1, 1], [1, 2], [1, 3]] },
  O: { n: 2, cells: [[0, 0], [0, 1], [1, 0], [1, 1]] },
  T: { n: 3, cells: [[0, 1], [1, 0], [1, 1], [1, 2]] },
  S: { n: 3, cells: [[0, 1], [0, 2], [1, 0], [1, 1]] },
  Z: { n: 3, cells: [[0, 0], [0, 1], [1, 1], [1, 2]] },
  J: { n: 3, cells: [[0, 0], [1, 0], [1, 1], [1, 2]] },
  L: { n: 3, cells: [[0, 2], [1, 0], [1, 1], [1, 2]] },
};
export const COLORS = { I: 'cyan', O: 'yellow', T: 'purple', S: 'green', Z: 'red', J: 'blue', L: 'orange' };

// (dx, dy), dy = +up: the box moves by row - dy, col + dx. Keys 'from>to' with states 0, 1 (R), 2, 3 (L).
export const KICKS_JLSTZ = {
  '0>1': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]], '1>0': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  '1>2': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]], '2>1': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  '2>3': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]], '3>2': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  '3>0': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]], '0>3': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
};
export const KICKS_I = {
  '0>1': [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]], '1>0': [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  '1>2': [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]], '2>1': [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  '2>3': [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]], '3>2': [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  '3>0': [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]], '0>3': [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
};

export function cellsOf(type, rot) {
  const { n, cells } = SHAPES[type];
  let out = cells.map(([r, c]) => [r, c]);
  if (type === 'O') return out;
  for (let k = 0; k < rot; k++) out = out.map(([r, c]) => [c, n - 1 - r]);
  return out;
}

export function emptyBoard() { return Array.from({ length: 22 }, () => Array(10).fill('')); }

export function fits(board, type, rot, row, col) {
  for (const [r, c] of cellsOf(type, rot)) {
    const R = row + r, C = col + c;
    if (R < 0 || R > 21 || C < 0 || C > 9 || board[R][C] !== '') return false;
  }
  return true;
}

export function levelOf(lines) { return 1 + Math.floor(lines / 10); }

export function gravityMs(level) {
  return Math.max(1, Math.round(Math.pow(0.8 - (level - 1) * 0.007, level - 1) * 1000));
}

export function refill(g) {
  while (g.queue.length < 3) {
    const bag = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];
    for (let i = 6; i >= 1; i--) {
      const j = Math.floor(g.rng() * (i + 1));
      const t = bag[i]; bag[i] = bag[j]; bag[j] = t;
    }
    for (const p of bag) g.queue.push(p);
  }
}

export function spawn(g, type) {
  g.active = { type, rot: 0, row: 0, col: type === 'O' ? 4 : 3 };
  g.fall = 0; g.lock = 0; g.resets = 0;
  if (!fits(g.board, type, 0, 0, g.active.col)) { g.over = true; g.active = null; }
}

export function newGame(seed) {
  const g = { board: emptyBoard(), queue: [], rng: mulberry32(seed), active: null, hold: null, holdUsed: false,
    score: 0, lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 };
  refill(g);
  spawn(g, g.queue.shift());
  refill(g);
  return g;
}

export function resting(g) {
  const a = g.active;
  return !fits(g.board, a.type, a.rot, a.row + 1, a.col);
}

// After a successful move or rotation. wasResting: the piece could not move down before it.
export function afterMove(g, wasResting) {
  if (!resting(g)) { g.lock = 0; return; }
  if (wasResting && g.resets < 15) { g.lock = 0; g.resets += 1; }
}

export function moveSide(g, dc) {
  const a = g.active, was = resting(g);
  if (!fits(g.board, a.type, a.rot, a.row, a.col + dc)) return false;
  a.col += dc; afterMove(g, was); return true;
}

export function softDrop(g) {
  const a = g.active, was = resting(g);
  if (!fits(g.board, a.type, a.rot, a.row + 1, a.col)) return false;
  a.row += 1; g.score += 1; afterMove(g, was); return true;
}

export function rotate(g, dir) {
  const a = g.active;
  if (a.type === 'O') return false;
  const was = resting(g);
  const to = (a.rot + (dir > 0 ? 1 : 3)) % 4;
  const table = a.type === 'I' ? KICKS_I : KICKS_JLSTZ;
  for (const [dx, dy] of table[a.rot + '>' + to]) {
    if (fits(g.board, a.type, to, a.row - dy, a.col + dx)) {
      a.rot = to; a.row -= dy; a.col += dx; afterMove(g, was); return true;
    }
  }
  return false;
}

export function lockPiece(g) {
  const a = g.active;
  for (const [r, c] of cellsOf(a.type, a.rot)) g.board[a.row + r][a.col + c] = a.type;
  const level = levelOf(g.lines);
  const kept = g.board.filter((row) => row.some((x) => x === ''));
  const n = 22 - kept.length;
  while (kept.length < 22) kept.unshift(Array(10).fill(''));
  g.board = kept;
  g.score += [0, 100, 300, 500, 800][n] * level;
  g.lines += n;
  g.holdUsed = false;
  spawn(g, g.queue.shift());
  refill(g);
}

export function hardDrop(g) {
  const a = g.active;
  let d = 0;
  while (fits(g.board, a.type, a.rot, a.row + 1, a.col)) { a.row += 1; d += 1; }
  g.score += 2 * d;
  lockPiece(g);
}

export function holdPiece(g) {
  if (g.holdUsed) return false;
  g.holdUsed = true;
  const cur = g.active.type;
  if (g.hold === null) { g.hold = cur; spawn(g, g.queue.shift()); refill(g); }
  else { const t = g.hold; g.hold = cur; spawn(g, t); }
  return true;
}

export function step(g) {
  if (g.paused || g.over || !g.active) return;
  if (resting(g)) {
    g.lock += 1;
    if (g.lock >= 500) lockPiece(g);
  } else {
    g.lock = 0;
    g.fall += 1;
    if (g.fall >= gravityMs(levelOf(g.lines))) { g.fall = 0; g.active.row += 1; }
  }
}

export function tick(g, ms) { for (let i = 0; i < ms; i++) step(g); }

export function input(g, action) {
  if (action === 'pause') { if (!g.over) g.paused = !g.paused; return; }
  if (g.paused || g.over || !g.active) return;
  if (action === 'left') moveSide(g, -1);
  else if (action === 'right') moveSide(g, 1);
  else if (action === 'down') softDrop(g);
  else if (action === 'drop') hardDrop(g);
  else if (action === 'cw') rotate(g, 1);
  else if (action === 'ccw') rotate(g, -1);
  else if (action === 'hold') holdPiece(g);
}

export function snapshot(g) {
  const a = g.active;
  return {
    board: g.board.map((r) => r.slice()),
    active: a ? { type: a.type, rotation: a.rot, row: a.row, col: a.col,
      cells: cellsOf(a.type, a.rot).map(([r, c]) => [a.row + r, a.col + c]) } : null,
    hold: g.hold, next: g.queue.slice(0, 3), score: g.score, lines: g.lines, level: levelOf(g.lines),
    over: g.over, paused: g.paused,
  };
}

// keyboard: a KeyboardEvent-like {key, ctrlKey, altKey, metaKey} -> 'left'|'right'|'down'|'drop'|'cw'|'ccw'|'hold'|
// 'pause'|'restart'|null (null: not a game key, or Ctrl/Alt/Meta held)
export function keyAction(e) {
  if (e.ctrlKey || e.altKey || e.metaKey) return null;
  const k = e.key;
  if (k === 'ArrowLeft') return 'left';
  if (k === 'ArrowRight') return 'right';
  if (k === 'ArrowDown') return 'down';
  if (k === ' ' || k === 'Spacebar') return 'drop';
  if (k === 'ArrowUp' || k === 'x' || k === 'X') return 'cw';
  if (k === 'z' || k === 'Z') return 'ccw';
  if (k === 'c' || k === 'C' || k === 'Shift') return 'hold';
  if (k === 'p' || k === 'P') return 'pause';
  if (k === 'r' || k === 'R') return 'restart';
  return null;
}

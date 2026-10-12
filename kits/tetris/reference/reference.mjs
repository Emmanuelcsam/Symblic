// The strict Tetris specification, executable: the oracle the harness (../harness/harness.mjs) compares a built
// tetris.html against, and that check-ref-units.mjs compares the unit-by-unit reference (ref-units.mjs) against.
// It was written from a prose specification before the spec sheet (../sheets/tetris.sheet.md) existed.
// Pure logic, no DOM. Time is advanced only by tick(ms), in 1 ms steps (gravity, then lock timer).

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

// (dx, dy) with dy = +up; the box moves by row -dy, col +dx. States 0, 1 (R), 2, 3 (L).
const K_JLSTZ = {
  '0>1': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]], '1>0': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  '1>2': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]], '2>1': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  '2>3': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]], '3>2': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  '3>0': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]], '0>3': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
};
const K_I = {
  '0>1': [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]], '1>0': [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  '1>2': [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]], '2>1': [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  '2>3': [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]], '3>2': [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  '3>0': [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]], '0>3': [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
};

export function boxCells(type, rot) {
  const { n, cells } = SHAPES[type];
  let out = cells.map(([r, c]) => [r, c]);
  if (type === 'O') return out;
  for (let k = 0; k < rot; k++) out = out.map(([r, c]) => [c, n - 1 - r]);
  return out;
}

export const interval = (level) => Math.max(1, Math.round(Math.pow(0.8 - (level - 1) * 0.007, level - 1) * 1000));

export class Game {
  constructor(seed = 1) { this.reset(seed); }

  reset(seed) {
    this.rng = mulberry32(seed);
    this.board = Array.from({ length: 22 }, () => Array(10).fill(''));
    this.queue = [];
    this.holdType = null; this.holdUsed = false;
    this.score = 0; this.lines = 0; this.over = false; this.paused = false;
    this.grav = 0; this.lockT = 0; this.resets = 0;
    this.active = null;
    this.refill();
    this.spawn(this.queue.shift());
    this.refill();
  }

  get level() { return 1 + Math.floor(this.lines / 10); }

  refill() {
    while (this.queue.length < 3) {
      const bag = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];
      for (let i = 6; i >= 1; i--) {
        const j = Math.floor(this.rng() * (i + 1));
        [bag[i], bag[j]] = [bag[j], bag[i]];
      }
      this.queue.push(...bag);
    }
  }

  fits(type, rot, row, col) {
    for (const [r, c] of boxCells(type, rot)) {
      const R = row + r, C = col + c;
      if (R < 0 || R > 21 || C < 0 || C > 9 || this.board[R][C]) return false;
    }
    return true;
  }

  spawn(type) {
    this.active = { type, rot: 0, row: 0, col: type === 'O' ? 4 : 3 };
    this.grav = 0; this.lockT = 0; this.resets = 0;
    if (!this.fits(type, 0, 0, this.active.col)) { this.over = true; this.active = null; }
  }

  resting() { const a = this.active; return !this.fits(a.type, a.rot, a.row + 1, a.col); }

  moved(wasResting) {            // after a successful move or rotation; wasResting: it could not move down BEFORE it
    if (!this.resting()) { this.lockT = 0; return; }       // free to fall again: no lock timer runs
    if (wasResting && this.resets < 15) { this.lockT = 0; this.resets += 1; }
  }

  input(action) {
    if (action === 'pause') { if (!this.over) this.paused = !this.paused; return; }
    if (this.paused || this.over || !this.active) return;
    const a = this.active;
    const was = this.resting();
    if (action === 'left' || action === 'right') {
      const dc = action === 'left' ? -1 : 1;
      if (this.fits(a.type, a.rot, a.row, a.col + dc)) { a.col += dc; this.moved(was); }
    } else if (action === 'down') {
      if (this.fits(a.type, a.rot, a.row + 1, a.col)) { a.row += 1; this.score += 1; this.moved(was); }
    } else if (action === 'drop') {
      let d = 0;
      while (this.fits(a.type, a.rot, a.row + 1, a.col)) { a.row += 1; d += 1; }
      this.score += 2 * d;
      this.lock();
    } else if (action === 'cw' || action === 'ccw') {
      if (a.type === 'O') return;
      const to = (a.rot + (action === 'cw' ? 1 : 3)) % 4;
      const table = a.type === 'I' ? K_I : K_JLSTZ;
      for (const [dx, dy] of table[`${a.rot}>${to}`]) {
        if (this.fits(a.type, to, a.row - dy, a.col + dx)) {
          a.rot = to; a.row -= dy; a.col += dx; this.moved(was); return;
        }
      }
    } else if (action === 'hold') {
      if (this.holdUsed) return;
      this.holdUsed = true;
      const cur = a.type;
      if (this.holdType === null) { this.holdType = cur; this.spawn(this.queue.shift()); this.refill(); }
      else { const t = this.holdType; this.holdType = cur; this.spawn(t); }
    }
  }

  lock() {
    const a = this.active;
    for (const [r, c] of boxCells(a.type, a.rot)) {
      const R = a.row + r, C = a.col + c;
      if (R >= 0 && R <= 21) this.board[R][C] = a.type;
    }
    const level = this.level;
    const kept = this.board.filter((row) => row.some((x) => !x));
    const n = 22 - kept.length;
    while (kept.length < 22) kept.unshift(Array(10).fill(''));
    this.board = kept;
    this.score += [0, 100, 300, 500, 800][n] * level;
    this.lines += n;
    this.holdUsed = false;
    this.spawn(this.queue.shift());
    this.refill();
  }

  tick(ms) {
    for (let i = 0; i < ms; i++) {
      if (this.paused || this.over || !this.active) return;
      const a = this.active;
      if (this.resting()) {
        this.lockT += 1;
        if (this.lockT >= 500) this.lock();
      } else {
        this.lockT = 0;
        this.grav += 1;
        if (this.grav >= interval(this.level)) { this.grav = 0; a.row += 1; }
      }
    }
  }

  state() {
    const a = this.active;
    return {
      board: this.board.map((r) => r.slice()),
      active: a ? { type: a.type, rotation: a.rot, row: a.row, col: a.col,
        cells: boxCells(a.type, a.rot).map(([r, c]) => [a.row + r, a.col + c]) } : null,
      hold: this.holdType, next: this.queue.slice(0, 3),
      score: this.score, lines: this.lines, level: this.level, over: this.over, paused: this.paused,
    };
  }
}

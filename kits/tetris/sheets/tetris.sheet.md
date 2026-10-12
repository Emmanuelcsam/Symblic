# tetris.html

One self-contained HTML5 file (inline style and script, no external URL, library or network use) that implements
exactly this Tetris. Its JavaScript is written as the units below. Each unit is written and tested on its own,
and the file is assembled from the units that pass their tests.

## Shared

Write plain browser JavaScript (ES2020) as top-level `function` and `const` declarations: no `import`, `export`,
`require`, classes, `console` or `Math.random`. Use only the names your unit defines and the names it lists under
"Uses". Do not define anything another unit defines.

The board has 22 rows and 10 columns, row 0 at the top. Rows 0-1 are hidden. Pieces are I, O, T, S, Z, J and L.
A piece sits in an n x n box. Its position (row, col) is the box's top-left cell, and `rot` 0-3 counts clockwise
turns (0 = spawn, 1 = R, 2, 3 = L).

The game state `g` is one plain object with exactly these fields:

- `board`: 22 arrays of 10 strings, each `''` (empty) or a piece letter. These are the locked cells only.
- `queue`: an array of upcoming piece letters, next first.
- `rng`: a function returning a number in [0, 1).
- `active`: `{type, rot, row, col}` or `null`.
- `hold`: a piece letter or `null`.
- `holdUsed`: `true` once hold was used for the current piece.
- `score`, `lines`: integers.
- `over`, `paused`: booleans.
- `fall`: milliseconds counted toward the next gravity row.
- `lock`: milliseconds counted toward locking.
- `resets`: how many times this piece restarted its lock timer.

## Unit `SHAPES, COLORS`

Define two constants. `SHAPES` maps each letter to `{n, cells}`: n is the box size and cells are its `[row, col]`
cells at rotation 0, in exactly this order:

- I: n=4, `[[1,0],[1,1],[1,2],[1,3]]`
- O: n=2, `[[0,0],[0,1],[1,0],[1,1]]`
- T: n=3, `[[0,1],[1,0],[1,1],[1,2]]`
- S: n=3, `[[0,1],[0,2],[1,0],[1,1]]`
- Z: n=3, `[[0,0],[0,1],[1,1],[1,2]]`
- J: n=3, `[[0,0],[1,0],[1,1],[1,2]]`
- L: n=3, `[[0,2],[1,0],[1,1],[1,2]]`

`COLORS` maps I cyan, O yellow, T purple, S green, Z red, J blue, L orange, as CSS color names.

Examples:

    SHAPES.I ==> {"n":4,"cells":[[1,0],[1,1],[1,2],[1,3]]}
    SHAPES.L ==> {"n":3,"cells":[[0,2],[1,0],[1,1],[1,2]]}
    SHAPES.O.n ==> 2
    Object.keys(SHAPES).sort() ==> ["I","J","L","O","S","T","Z"]
    COLORS ==> {"I":"cyan","O":"yellow","T":"purple","S":"green","Z":"red","J":"blue","L":"orange"}

## Unit `KICKS_JLSTZ, KICKS_I`

Define two constants of SRS wall-kick offsets. Each maps a key `'from>to'`, where from and to are rotation numbers
0-3, to a list of 5 `[dx, dy]` offsets tried in order. dx is +right and dy is +UP.

For J, L, S, T and Z (`KICKS_JLSTZ`):
- 0>1 (0,0)(-1,0)(-1,1)(0,-2)(-1,-2)
- 1>0 (0,0)(1,0)(1,-1)(0,2)(1,2)
- 1>2 (0,0)(1,0)(1,-1)(0,2)(1,2)
- 2>1 (0,0)(-1,0)(-1,1)(0,-2)(-1,-2)
- 2>3 (0,0)(1,0)(1,1)(0,-2)(1,-2)
- 3>2 (0,0)(-1,0)(-1,-1)(0,2)(-1,2)
- 3>0 (0,0)(-1,0)(-1,-1)(0,2)(-1,2)
- 0>3 (0,0)(1,0)(1,1)(0,-2)(1,-2)

For I (`KICKS_I`):
- 0>1 (0,0)(-2,0)(1,0)(-2,-1)(1,2)
- 1>0 (0,0)(2,0)(-1,0)(2,1)(-1,-2)
- 1>2 (0,0)(-1,0)(2,0)(-1,2)(2,-1)
- 2>1 (0,0)(1,0)(-2,0)(1,-2)(-2,1)
- 2>3 (0,0)(2,0)(-1,0)(2,1)(-1,-2)
- 3>2 (0,0)(-2,0)(1,0)(-2,-1)(1,2)
- 3>0 (0,0)(1,0)(-2,0)(1,-2)(-2,1)
- 0>3 (0,0)(-1,0)(2,0)(-1,2)(2,-1)

Write each offset as a two-number array: `'0>1': [[0,0],[-1,0],[-1,1],[0,-2],[-1,-2]]`.

Examples:

    KICKS_JLSTZ ==> {"0>1":[[0,0],[-1,0],[-1,1],[0,-2],[-1,-2]],"1>0":[[0,0],[1,0],[1,-1],[0,2],[1,2]],"1>2":[[0,0],[1,0],[1,-1],[0,2],[1,2]],"2>1":[[0,0],[-1,0],[-1,1],[0,-2],[-1,-2]],"2>3":[[0,0],[1,0],[1,1],[0,-2],[1,-2]],"3>2":[[0,0],[-1,0],[-1,-1],[0,2],[-1,2]],"3>0":[[0,0],[-1,0],[-1,-1],[0,2],[-1,2]],"0>3":[[0,0],[1,0],[1,1],[0,-2],[1,-2]]}
    KICKS_I ==> {"0>1":[[0,0],[-2,0],[1,0],[-2,-1],[1,2]],"1>0":[[0,0],[2,0],[-1,0],[2,1],[-1,-2]],"1>2":[[0,0],[-1,0],[2,0],[-1,2],[2,-1]],"2>1":[[0,0],[1,0],[-2,0],[1,-2],[-2,1]],"2>3":[[0,0],[2,0],[-1,0],[2,1],[-1,-2]],"3>2":[[0,0],[-2,0],[1,0],[-2,-1],[1,2]],"3>0":[[0,0],[1,0],[-2,0],[1,-2],[-2,1]],"0>3":[[0,0],[-1,0],[2,0],[-1,2],[2,-1]]}

## Unit `mulberry32(seed)`

Define exactly this random number generator. It returns a function, and each call of that function returns the next
number in [0, 1):

    function mulberry32(a) {
      return function () {
        a |= 0; a = a + 0x6D2B79F5 | 0;
        var t = Math.imul(a ^ a >>> 15, 1 | a);
        t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
        return ((t ^ t >>> 14) >>> 0) / 4294967296;
      };
    }

Examples:

    (() => { const r = mulberry32(1); return [r(), r(), r()]; })() ==> [0.6270739405881613,0.002735721180215478,0.5274470399599522]
    (() => { const r = mulberry32(2026); r(); return r(); })() ==> 0.30849614599719644

## Unit `cellsOf(type, rot)`

Uses: `SHAPES`

Return a new array of the piece's `[row, col]` box cells after `rot` clockwise turns. Start from
`SHAPES[type].cells`, then turn `rot` times. One clockwise turn maps each cell `[r, c]` to `[c, n-1-r]`, where
n = `SHAPES[type].n`. Keep the cells in the same order. O never turns: for O, return its rotation-0 cells for every
rot.

Examples:

    cellsOf('T', 0) ==> [[0,1],[1,0],[1,1],[1,2]]
    cellsOf('T', 1) ==> [[1,2],[0,1],[1,1],[2,1]]
    cellsOf('T', 2) ==> [[2,1],[1,2],[1,1],[1,0]]
    cellsOf('I', 1) ==> [[0,2],[1,2],[2,2],[3,2]]
    cellsOf('I', 3) ==> [[3,1],[2,1],[1,1],[0,1]]
    cellsOf('S', 3) ==> [[1,0],[0,0],[2,1],[1,1]]
    cellsOf('L', 2) ==> [[2,0],[1,2],[1,1],[1,0]]
    cellsOf('O', 3) ==> [[0,0],[0,1],[1,0],[1,1]]

## Unit `emptyBoard()`

Return a new board of 22 rows, each a new array of 10 empty strings `''`.

Examples:

    emptyBoard().length ==> 22
    emptyBoard()[21] ==> ["","","","","","","","","",""]
    (() => { const b = emptyBoard(); b[0][0] = 'X'; return b[1][0]; })() ==> ""

## Unit `fits(board, type, rot, row, col)`

Uses: `cellsOf`

Return `true` when every cell of the piece (from `cellsOf(type, rot)`, each moved by `row`, `col`) is on the board
(0 <= row <= 21 and 0 <= col <= 9) and that board cell is `''`. Otherwise return `false`.

Test setup:

    function blank() { return Array.from({ length: 22 }, () => Array(10).fill('')); }

Examples:

    fits(blank(), 'T', 0, 0, 3) ==> true
    fits(blank(), 'T', 0, 0, 8) ==> false
    fits(blank(), 'T', 0, 0, 7) ==> true
    fits(blank(), 'I', 0, -1, 0) ==> true
    fits(blank(), 'I', 0, -2, 0) ==> false
    fits(blank(), 'I', 1, 18, 0) ==> true
    fits(blank(), 'I', 1, 19, 0) ==> false
    fits(blank(), 'O', 0, 0, -1) ==> false
    (() => { const b = blank(); b[1][4] = 'Z'; return [fits(b, 'T', 0, 0, 3), fits(b, 'T', 0, 0, 4)]; })() ==> [false,false]

## Unit `levelOf(lines), gravityMs(level)`

`levelOf(lines)` returns `1 + Math.floor(lines / 10)`.

`gravityMs(level)` returns the gravity interval in milliseconds:
`Math.max(1, Math.round(Math.pow(0.8 - (level - 1) * 0.007, level - 1) * 1000))`.

Examples:

    [levelOf(0), levelOf(9), levelOf(10), levelOf(25)] ==> [1,1,2,3]
    [gravityMs(1), gravityMs(2), gravityMs(3), gravityMs(10), gravityMs(20), gravityMs(200)] ==> [1000,793,618,64,1,1]

## Unit `refill(g)`

While `g.queue` has fewer than 3 letters, append one new bag to it. To make a bag, start from the array
`['I','O','T','S','Z','J','L']`. Then for i = 6 down to 1: let `j = Math.floor(g.rng() * (i + 1))` and swap items i
and j. Then append ALL 7 letters of the bag to the end of `g.queue`, from index 0 up. Never remove or drop letters
from the queue: after refill it usually holds more than 3 letters (an empty queue ends with 7, a queue of 2 with 9),
and a queue that already holds 3 or more is left unchanged. Call `g.rng` only to make bags.

In code, the whole unit is one loop:

    while (g.queue.length < 3) { make one shuffled bag of 7 as above; push its 7 letters onto g.queue }

Test setup:

    function seq(values) { let k = 0; return () => values[k++ % values.length]; }

Examples:

    (() => { const g = { queue: [], rng: seq([0]) }; refill(g); return g.queue; })() ==> ["O","T","S","Z","J","L","I"]
    (() => { const g = { queue: [], rng: seq([0.999]) }; refill(g); return g.queue; })() ==> ["I","O","T","S","Z","J","L"]
    (() => { const g = { queue: [], rng: seq([0.5, 0.25, 0.75]) }; refill(g); return g.queue; })() ==> ["Z","J","I","T","L","O","S"]
    (() => { const g = { queue: ['T', 'S'], rng: seq([0]) }; refill(g); return g.queue; })() ==> ["T","S","O","T","S","Z","J","L","I"]
    (() => { const g = { queue: ['T', 'S', 'Z'], rng: seq([0]) }; refill(g); return g.queue; })() ==> ["T","S","Z"]
    (() => { let n = 0; const g = { queue: [], rng: () => { n++; return 0.3; } }; refill(g); return n; })() ==> 6

## Unit `spawn(g, type)`

Uses: `fits`

Put a new piece of `type` into play: set `g.active` to `{type, rot: 0, row: 0, col: 3}`, with col 4 for O. Set
`g.fall`, `g.lock` and `g.resets` to 0. If that piece does not fit (`fits(g.board, type, 0, 0, col)` is false), the
game is over: set `g.over = true` and `g.active = null`.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: null, hold: null, holdUsed: false, score: 0, lines: 0, over: false, paused: false,
        fall: 0, lock: 0, resets: 0 }, o || {});
    }

Examples:

    (() => { const g = mk({ fall: 7, lock: 9, resets: 3 }); spawn(g, 'T'); return [g.active, g.fall, g.lock, g.resets, g.over]; })() ==> [{"type":"T","rot":0,"row":0,"col":3},0,0,0,false]
    (() => { const g = mk(); spawn(g, 'O'); return g.active; })() ==> {"type":"O","rot":0,"row":0,"col":4}
    (() => { const g = mk(); g.board[1][4] = 'J'; spawn(g, 'T'); return [g.active, g.over]; })() ==> [null,true]
    (() => { const g = mk(); g.board[0][4] = 'J'; spawn(g, 'O'); return [g.active, g.over]; })() ==> [null,true]

## Unit `newGame(seed)`

Uses: `emptyBoard`, `mulberry32`, `refill`, `spawn`

Return a new game state with every field of the shared state and no other field. Start from exactly this object:

    const g = { board: emptyBoard(), queue: [], rng: mulberry32(seed), active: null, hold: null, holdUsed: false,
      score: 0, lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 };

Then call `refill(g)`, then `spawn(g, g.queue.shift())`, then `refill(g)` again, and return g.

Examples:

    (() => { const g = newGame(1); return [g.active, g.queue, g.hold, g.score, g.over]; })() ==> [{"type":"O","rot":0,"row":0,"col":4},["J","L","S","T","I","Z"],null,0,false]
    (() => { const g = newGame(42); return [g.active.type, g.queue.slice(0, 3)]; })() ==> ["S",["O","I","J"]]
    Object.keys(newGame(5)).sort() ==> ["active","board","fall","hold","holdUsed","lines","lock","over","paused","queue","resets","rng","score"]

## Unit `resting(g), afterMove(g, wasResting)`

Uses: `fits`

`resting(g)` returns true when the active piece cannot move down one row:
`!fits(g.board, a.type, a.rot, a.row + 1, a.col)` for `a = g.active`.

`afterMove(g, wasResting)` is called after every successful move or rotation. `wasResting` is the piece's state
BEFORE the move; `resting(g)`, called inside afterMove, is its state NOW, after the move. Follow these steps exactly:

1. If `resting(g)` is false (the piece can fall now): set `g.lock = 0` and return.
2. If `wasResting` is true and `g.resets < 15`: set `g.lock = 0` and add 1 to `g.resets`.
3. Otherwise change nothing.

Step 1 must call `resting(g)`; do not use `wasResting` in step 1. In code, afterMove has exactly two `if`
statements: `if (!resting(g)) { ...; return; }` then `if (wasResting && g.resets < 15) { ... }`.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 0, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }

Examples:

    [resting(mk()), resting(mk({ active: { type: 'T', rot: 0, row: 20, col: 3 } }))] ==> [false,true]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 5, col: 3 } }); g.board[7][4] = 'I'; return resting(g); })() ==> true
    (() => { const g = mk({ lock: 300, resets: 2 }); afterMove(g, true); return [g.lock, g.resets]; })() ==> [0,2]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 }, lock: 300, resets: 2 }); afterMove(g, true); return [g.lock, g.resets]; })() ==> [0,3]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 }, lock: 300, resets: 2 }); afterMove(g, false); return [g.lock, g.resets]; })() ==> [300,2]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 }, lock: 300, resets: 15 }); afterMove(g, true); return [g.lock, g.resets]; })() ==> [300,15]

## Unit `moveSide(g, dc), softDrop(g)`

Uses: `fits`, `resting`, `afterMove`

`moveSide(g, dc)` moves the active piece one column (dc is -1 or +1). Follow these steps exactly:

1. Let `a = g.active` and `was = resting(g)`. `was` is only passed on to `afterMove`; never test it here.
2. If `fits(g.board, a.type, a.rot, a.row, a.col + dc)`: set `a.col = a.col + dc`, call `afterMove(g, was)` and
   return true.
3. Otherwise return false without changing anything.

`softDrop(g)` moves the active piece down one row. Follow these steps exactly:

1. Let `a = g.active` and `was = resting(g)`. `was` is only passed on to `afterMove`; never test it here.
2. If `fits(g.board, a.type, a.rot, a.row + 1, a.col)`: set `a.row = a.row + 1`, add 1 to `g.score`, call
   `afterMove(g, was)` and return true.
3. Otherwise return false without changing anything.

Each function has exactly one `if`, and its condition is the `fits(...)` call alone.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 0, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }

Examples:

    (() => { const g = mk(); return [moveSide(g, -1), g.active.col, moveSide(g, 1), moveSide(g, 1), g.active.col]; })() ==> [true,2,true,true,4]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 0, col: 0 } }); return [moveSide(g, -1), g.active.col]; })() ==> [false,0]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 0, col: 7 } }); return [moveSide(g, 1), g.active.col]; })() ==> [false,7]
    (() => { const g = mk(); return [softDrop(g), g.active.row, g.score]; })() ==> [true,1,1]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 }, score: 5 }); return [softDrop(g), g.active.row, g.score]; })() ==> [false,20,5]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 }, lock: 200 }); moveSide(g, 1); return [g.active.col, g.lock, g.resets]; })() ==> [4,0,1]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 19, col: 3 }, lock: 0 }); softDrop(g); return [g.active.row, g.lock, g.resets]; })() ==> [20,0,0]
    (() => { const g = mk({ active: { type: 'I', rot: 0, row: 5, col: 0 } }); g.board[7][4] = 'Z'; g.lock = 120; const r = moveSide(g, 1); return [r, g.active.col, g.lock, g.resets]; })() ==> [true,1,120,0]

## Unit `rotate(g, dir)`

Uses: `fits`, `resting`, `afterMove`, `KICKS_JLSTZ`, `KICKS_I`

Turn the active piece: dir +1 is clockwise and -1 is counter-clockwise. Follow these steps exactly:

1. Let `a = g.active`. If `a.type` is `'O'`, return false (O never turns).
2. Let `was = resting(g)` (before the turn). `was` is only passed on to `afterMove`; never test it here.
3. Let `to = (a.rot + 1) % 4` when dir is +1, else `(a.rot + 3) % 4`.
4. Let `kicks = (a.type === 'I' ? KICKS_I : KICKS_JLSTZ)[a.rot + '>' + to]`.
5. For each `[dx, dy]` of `kicks`, in order: if `fits(g.board, a.type, to, a.row - dy, a.col + dx)`, then set
   `a.rot = to`, `a.row = a.row - dy`, `a.col = a.col + dx`, call `afterMove(g, was)` and return true.
6. If no offset fits, return false without changing anything.

Note the minus in `a.row - dy`: dy counts up, rows count down.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 0, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }

Examples:

    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 5, col: 3 } }); return [rotate(g, 1), g.active]; })() ==> [true,{"type":"T","rot":1,"row":5,"col":3}]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 5, col: 3 } }); return [rotate(g, -1), g.active]; })() ==> [true,{"type":"T","rot":3,"row":5,"col":3}]
    (() => { const g = mk({ active: { type: 'O', rot: 0, row: 5, col: 4 } }); return [rotate(g, 1), g.active]; })() ==> [false,{"type":"O","rot":0,"row":5,"col":4}]
    (() => { const g = mk({ active: { type: 'T', rot: 1, row: 5, col: -1 } }); return [rotate(g, 1), g.active]; })() ==> [true,{"type":"T","rot":2,"row":5,"col":0}]
    (() => { const g = mk({ active: { type: 'I', rot: 0, row: 5, col: 0 } }); rotate(g, 1); return [rotate(g, 1), g.active]; })() ==> [true,{"type":"I","rot":2,"row":5,"col":0}]
    (() => { const g = mk({ active: { type: 'I', rot: 1, row: 5, col: -2 } }); return [rotate(g, -1), g.active]; })() ==> [true,{"type":"I","rot":0,"row":5,"col":0}]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 0, col: 3 } }); return [rotate(g, 1), g.active]; })() ==> [true,{"type":"T","rot":1,"row":0,"col":3}]
    (() => { const g = mk({ active: { type: 'J', rot: 0, row: 19, col: 0 } }); return [rotate(g, -1), g.active]; })() ==> [true,{"type":"J","rot":3,"row":19,"col":0}]
    (() => { const g = mk({ active: { type: 'S', rot: 0, row: 20, col: 3 }, lock: 250 }); return [rotate(g, 1), g.active, g.lock, g.resets]; })() ==> [true,{"type":"S","rot":1,"row":19,"col":2},0,1]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 5, col: 3 } }); for (let r = 0; r < 22; r++) { if (r !== 5 && r !== 6) g.board[r].fill('Z'); } g.board[5].fill(''); g.board[6].fill(''); return [rotate(g, 1), g.active]; })() ==> [false,{"type":"T","rot":0,"row":5,"col":3}]

## Unit `lockPiece(g)`

Uses: `cellsOf`, `levelOf`, `spawn`, `refill`

Lock the active piece, remove full rows, score them and bring in the next piece. Follow these steps exactly:

1. Let `a = g.active`. For each `[r, c]` of `cellsOf(a.type, a.rot)`, set `g.board[a.row + r][a.col + c] = a.type`.
2. `const level = levelOf(g.lines);` (the level BEFORE this lock's lines are counted).
3. `const kept = g.board.filter((row) => row.includes(''));` These are the rows that are not full: a row is full
   when it has no `''` left.
4. `const n = 22 - kept.length;` This is the number of full rows, which are removed.
5. `g.board = Array.from({ length: n }, () => Array(10).fill('')).concat(kept);` This puts n new empty rows of 10
   `''` on top of the kept rows, so the board has 22 rows again.
6. Add `[0, 100, 300, 500, 800][n] * level` to `g.score`, and add `n` to `g.lines`.
7. Set `g.holdUsed = false`.
8. Call `spawn(g, g.queue.shift())`, then `refill(g)`.

Do not check for game over here: `spawn` already sets `g.over` when the new piece does not fit.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 0, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function rowsOf(g) { return g.board.map((r) => r.map((x) => x || '.').join('')).filter((s) => s !== '..........'); }

Examples:

    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 }, holdUsed: true }); lockPiece(g); return [rowsOf(g), g.score, g.lines, g.holdUsed, g.active, g.queue]; })() ==> [["....T.....","...TTT...."],0,0,false,{"type":"I","rot":0,"row":0,"col":3},["O","T","I","J","O","Z","T","L","S"]]
    (() => { const g = mk({ active: { type: 'I', rot: 0, row: 20, col: 0 } }); for (let c = 4; c < 10; c++) g.board[21][c] = 'L'; lockPiece(g); return [rowsOf(g), g.score, g.lines]; })() ==> [[],100,1]
    (() => { const g = mk({ active: { type: 'I', rot: 1, row: 18, col: 7 }, lines: 12 }); for (let r = 18; r < 22; r++) for (let c = 0; c < 10; c++) if (c !== 9) g.board[r][c] = 'O'; g.board[17][0] = 'S'; lockPiece(g); return [rowsOf(g), g.score, g.lines]; })() ==> [["S........."],1600,16]
    (() => { const g = mk({ active: { type: 'O', rot: 0, row: 20, col: 0 }, lines: 9, score: 40 }); for (let c = 2; c < 10; c++) { g.board[20][c] = 'J'; g.board[21][c] = 'J'; } g.board[19][5] = 'T'; lockPiece(g); return [rowsOf(g), g.score, g.lines]; })() ==> [[".....T...."],340,11]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 } }); for (let r = 0; r < 22; r++) g.board[r][4] = r < 3 ? 'Z' : ''; lockPiece(g); return [g.over, g.active]; })() ==> [true,null]

## Unit `hardDrop(g)`

Uses: `fits`, `lockPiece`

Follow these steps exactly:

1. Let `a = g.active` and `d = 0`.
2. While `fits(g.board, a.type, a.rot, a.row + 1, a.col)`: add 1 to `a.row` and add 1 to `d`.
3. Add `2 * d` to `g.score`.
4. Call `lockPiece(g)`.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 0, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function rowsOf(g) { return g.board.map((r) => r.map((x) => x || '.').join('')).filter((s) => s !== '..........'); }

Examples:

    (() => { const g = mk(); hardDrop(g); return [rowsOf(g), g.score, g.active]; })() ==> [["....T.....","...TTT...."],40,{"type":"I","rot":0,"row":0,"col":3}]
    (() => { const g = mk({ active: { type: 'I', rot: 1, row: 0, col: 0 } }); g.board[15][2] = 'Z'; hardDrop(g); return [rowsOf(g), g.score]; })() ==> [["..I.......","..I.......","..I.......","..I.......","..Z......."],22]
    (() => { const g = mk({ active: { type: 'O', rot: 0, row: 20, col: 4 }, score: 3 }); hardDrop(g); return [rowsOf(g), g.score]; })() ==> [["....OO....","....OO...."],3]

## Unit `holdPiece(g)`

Uses: `spawn`, `refill`

Follow these steps exactly:

1. If `g.holdUsed` is true, return false without changing anything.
2. Set `g.holdUsed = true` and let `cur = g.active.type`.
3. If `g.hold` is null: set `g.hold = cur`, then call `spawn(g, g.queue.shift())`, then `refill(g)`.
4. Otherwise: let `old = g.hold`, set `g.hold = cur`, then call `spawn(g, old)` (no refill).
5. Return true.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'S', rot: 2, row: 7, col: 5 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 30, lock: 40, resets: 2 }, o || {});
    }

Examples:

    (() => { const g = mk(); return [holdPiece(g), g.hold, g.active, g.queue, g.holdUsed, g.fall, g.lock, g.resets]; })() ==> [true,"S",{"type":"I","rot":0,"row":0,"col":3},["O","T","I","J","O","Z","T","L","S"],true,0,0,0]
    (() => { const g = mk({ hold: 'L' }); return [holdPiece(g), g.hold, g.active, g.queue]; })() ==> [true,"S",{"type":"L","rot":0,"row":0,"col":3},["I","O","T"]]
    (() => { const g = mk({ holdUsed: true }); return [holdPiece(g), g.hold, g.active]; })() ==> [false,null,{"type":"S","rot":2,"row":7,"col":5}]
    (() => { const g = mk({ hold: 'O' }); g.board[0][4] = 'Z'; return [holdPiece(g), g.over, g.active, g.hold]; })() ==> [true,true,null,"S"]

## Unit `step(g), tick(g, ms)`

Uses: `resting`, `lockPiece`, `gravityMs`, `levelOf`

`step(g)` advances the game by 1 millisecond. Follow these steps exactly:

1. If `g.paused` or `g.over` is true or `g.active` is null, return.
2. If `resting(g)`: add 1 to `g.lock`; then if `g.lock >= 500`, call `lockPiece(g)`. Return.
3. Otherwise (the piece can fall): set `g.lock = 0`, add 1 to `g.fall`; then if
   `g.fall >= gravityMs(levelOf(g.lines))`, set `g.fall = 0` and `g.active.row += 1`.

Each call does exactly one of step 2 or step 3. `g.fall` is not reset while the piece rests.

`tick(g, ms)` calls `step(g)` exactly `ms` times.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 0, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function rowsOf(g) { return g.board.map((r) => r.map((x) => x || '.').join('')).filter((s) => s !== '..........'); }

Examples:

    (() => { const g = mk(); tick(g, 999); const a = g.active.row; tick(g, 1); return [a, g.active.row, g.fall]; })() ==> [0,1,0]
    (() => { const g = mk({ lines: 10 }); tick(g, 793); return [g.active.row, g.fall]; })() ==> [1,0]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 } }); tick(g, 499); return [g.lock, g.active, rowsOf(g)]; })() ==> [499,{"type":"T","rot":0,"row":20,"col":3},[]]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 20, col: 3 } }); tick(g, 500); return [g.active, rowsOf(g), g.lock]; })() ==> [{"type":"I","rot":0,"row":0,"col":3},["....T.....","...TTT...."],0]
    (() => { const g = mk({ paused: true }); tick(g, 5000); return [g.active.row, g.fall]; })() ==> [0,0]
    (() => { const g = mk(); tick(g, 25000); return [rowsOf(g), g.active, g.queue, g.fall, g.lock]; })() ==> [["....T.....","...TTT...."],{"type":"I","rot":0,"row":4,"col":3},["O","T","I","J","O","Z","T","L","S"],500,0]
    (() => { const g = mk({ active: { type: 'T', rot: 0, row: 19, col: 3 }, fall: 990 }); tick(g, 30); return [g.active.row, g.fall, g.lock]; })() ==> [20,0,20]

## Unit `input(g, action)`

Uses: `moveSide`, `softDrop`, `hardDrop`, `rotate`, `holdPiece`

Apply one action. Follow these steps exactly:

1. If `action` is `'pause'`: when `g.over` is false, set `g.paused = !g.paused`. Then return (also when over).
2. If `g.paused` or `g.over` is true or `g.active` is null, return.
3. Call the function for the action: `'left'` calls `moveSide(g, -1)`, `'right'` calls `moveSide(g, 1)`, `'down'`
   calls `softDrop(g)`, `'drop'` calls `hardDrop(g)`, `'cw'` calls `rotate(g, 1)`, `'ccw'` calls `rotate(g, -1)`
   and `'hold'` calls `holdPiece(g)`. Any other action does nothing.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 5, col: 3 }, hold: null, holdUsed: false, score: 0,
        lines: 0, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }

Examples:

    (() => { const g = mk(); ['left', 'left', 'cw', 'down'].forEach((a) => input(g, a)); return [g.active, g.score]; })() ==> [{"type":"T","rot":1,"row":6,"col":1},1]
    (() => { const g = mk(); input(g, 'pause'); input(g, 'left'); input(g, 'drop'); return [g.paused, g.active]; })() ==> [true,{"type":"T","rot":0,"row":5,"col":3}]
    (() => { const g = mk(); input(g, 'pause'); input(g, 'pause'); input(g, 'right'); return [g.paused, g.active.col]; })() ==> [false,4]
    (() => { const g = mk({ over: true, active: null }); input(g, 'pause'); input(g, 'left'); return [g.paused, g.over]; })() ==> [false,true]
    (() => { const g = mk(); input(g, 'hold'); input(g, 'hold'); return [g.hold, g.active, g.holdUsed]; })() ==> ["T",{"type":"I","rot":0,"row":0,"col":3},true]
    (() => { const g = mk(); input(g, 'ccw'); input(g, 'jump'); return g.active; })() ==> {"type":"T","rot":3,"row":5,"col":3}
    (() => { const g = mk(); input(g, 'drop'); return [g.score, g.active, g.board[21].join(',')]; })() ==> [30,{"type":"I","rot":0,"row":0,"col":3},",,,T,T,T,,,,"]

## Unit `snapshot(g)`

Uses: `cellsOf`, `levelOf`

Return a NEW object that shares no arrays or objects with g, with exactly these nine fields:

- `board`: a copy of every row, `g.board.map((row) => row.slice())`.
- `active`: `null` when `g.active` is null. Otherwise, for `a = g.active`, a new object
  `{ type: a.type, rotation: a.rot, row: a.row, col: a.col, cells }` where `cells` is the piece's four board cells:
  each `[r, c]` of `cellsOf(a.type, a.rot)` becomes `[a.row + r, a.col + c]`. Note the field is named `rotation`.
- `hold`: `g.hold`.
- `next`: a new array of the first 3 letters of `g.queue` (`g.queue.slice(0, 3)`).
- `score`, `lines`, `over`, `paused`: copied from g.
- `level`: `levelOf(g.lines)`.

Test setup:

    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T', 'S'],
        rng: () => 0.5, active: { type: 'L', rot: 1, row: 5, col: 2 }, hold: 'Z', holdUsed: false, score: 120,
        lines: 13, over: false, paused: true, fall: 0, lock: 0, resets: 0 }, o || {});
    }

Examples:

    (() => { const s = snapshot(mk()); delete s.board; return s; })() ==> {"active":{"type":"L","rotation":1,"row":5,"col":2,"cells":[[7,4],[5,3],[6,3],[7,3]]},"hold":"Z","next":["I","O","T"],"score":120,"lines":13,"level":2,"over":false,"paused":true}
    (() => { const g = mk({ active: null, over: true }); g.board[21][0] = 'T'; const s = snapshot(g); return [s.active, s.over, s.board[21][0], s.board.length]; })() ==> [null,true,"T",22]
    (() => { const g = mk(); const s = snapshot(g); s.board[0][0] = 'X'; s.next.push('Q'); s.active.cells[0][0] = 99; return [g.board[0][0], g.queue.length, snapshot(g).active.cells[0]]; })() ==> ["",4,[7,4]]
    Object.keys(snapshot(mk())).sort() ==> ["active","board","hold","level","lines","next","over","paused","score"]

## Unit `keyAction(e)`

Return the game action for a keyboard event `e` (an object with `key`, `ctrlKey`, `altKey`, `metaKey`). Follow these
steps exactly:

1. If `e.ctrlKey`, `e.altKey` or `e.metaKey` is true, return null: those keys are left to the browser.
2. Otherwise return the action this table gives for `e.key`. Every key listed is a separate case; the return value is
   always one of the action words, never the key itself.

   | `e.key` | returns |
   |---|---|
   | `'ArrowLeft'` | `'left'` |
   | `'ArrowRight'` | `'right'` |
   | `'ArrowDown'` | `'down'` |
   | `' '` (the Space key) | `'drop'` |
   | `'ArrowUp'`, `'x'`, `'X'` | `'cw'` |
   | `'z'`, `'Z'` | `'ccw'` |
   | `'c'`, `'C'`, `'Shift'` | `'hold'` |
   | `'p'`, `'P'` | `'pause'` |
   | `'r'`, `'R'` | `'restart'` |

3. Any other key returns null.

Examples:

    ['ArrowLeft', 'ArrowRight', 'ArrowDown', ' ', 'ArrowUp', 'x', 'X', 'z', 'Z', 'c', 'C', 'Shift', 'p', 'P', 'r', 'R', 'q', 'Enter'].map((key) => keyAction({ key, ctrlKey: false, altKey: false, metaKey: false })) ==> ["left","right","down","drop","cw","cw","cw","ccw","ccw","hold","hold","hold","pause","pause","restart","restart",null,null]
    [keyAction({ key: 'c', ctrlKey: true, altKey: false, metaKey: false }), keyAction({ key: 'r', ctrlKey: false, altKey: false, metaKey: true }), keyAction({ key: 'ArrowLeft', ctrlKey: false, altKey: true, metaKey: false })] ==> [null,null,null]

## Unit `drawCell(ctx, r, c, color)`

Fill one board cell on the canvas 2D context `ctx` (call its members directly). A board cell at row r and column c
has its top-left corner at x = c * 30 and y = (r - 2) * 30, because rows 0 and 1 are hidden. Follow these steps
exactly:

1. Set `ctx.fillStyle = color`.
2. Call `ctx.fillRect(c * 30 + 1, (r - 2) * 30 + 1, 28, 28)`.

drawCell checks nothing else: its callers never pass a hidden row.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls };
      for (const m of ['fillRect', 'strokeRect', 'clearRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'stroke'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ctx.strokeStyle, ...a]);
      ctx.fillStyle = ''; ctx.strokeStyle = ''; ctx.lineWidth = 1; ctx.font = ''; ctx.textAlign = 'left';
      return ctx;
    }
    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 5, col: 3 }, hold: 'L', holdUsed: false, score: 1200,
        lines: 14, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function texts(ctx) { return ctx.calls.filter((c) => c[0] === 'fillText').map((c) => String(c[3])); }
    function filledAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'fillRect' && c[1] === color && c[3] <= x + 1 && x + 1 < c[3] + c[5] && c[4] <= y + 1 && y + 1 < c[4] + c[6]); }
    function strokedAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'strokeRect' && c[2] === color && Math.abs(c[3] - x) <= 3 && Math.abs(c[4] - y) <= 3); }

Examples:

    (() => { const b = fake(); drawCell(b, 21, 0, 'red'); return b.calls; })() ==> [["fillRect","red","",1,571,28,28]]
    (() => { const b = fake(); drawCell(b, 2, 9, 'cyan'); drawCell(b, 7, 4, 'blue'); return b.calls; })() ==> [["fillRect","cyan","",271,1,28,28],["fillRect","blue","",121,151,28,28]]

## Unit `drawBoard(g, board)`

Uses: `drawCell`, `cellsOf`, `fits`, `COLORS`

Draw the board on `board`, a canvas 2D context of a 300 x 600 canvas: call its members directly, as in
`board.fillRect(...)`. Use only these context members: `fillStyle`, `strokeStyle`, `lineWidth`, `font`, `textAlign`, `fillRect`, `strokeRect`,
`clearRect`, `fillText`, `beginPath`, `moveTo`, `lineTo`, `stroke`. Never call any other method (no `save`, `fill`,
`arc`, `measureText`, `getContext`).

Follow these steps exactly:

1. Set `board.fillStyle = '#111'` and call `board.fillRect(0, 0, 300, 600)`.
2. Grid: set `board.strokeStyle = '#333'` and `board.lineWidth = 1`. For c from 0 to 10, call `board.beginPath()`,
   `board.moveTo(c * 30, 0)`, `board.lineTo(c * 30, 600)` and `board.stroke()`. For r from 0 to 20, call
   `board.beginPath()`, `board.moveTo(0, r * 30)`, `board.lineTo(300, r * 30)` and `board.stroke()`.
3. Locked cells: for each row r from 2 to 21 and column c from 0 to 9, if `g.board[r][c]` is not `''`, call
   `drawCell(board, r, c, COLORS[g.board[r][c]])`.
4. If `g.active` is not null, let `a = g.active`, then:
   - Ghost: `let gr = a.row;` and while `fits(g.board, a.type, a.rot, gr + 1, a.col)` add 1 to `gr`. Set
     `board.strokeStyle = COLORS[a.type]` and `board.lineWidth = 2`. For each `[r, c]` of `cellsOf(a.type, a.rot)`,
     if `gr + r >= 2`, call `board.strokeRect((a.col + c) * 30 + 2, (gr + r - 2) * 30 + 2, 26, 26)`.
   - Piece: for each `[r, c]` of `cellsOf(a.type, a.rot)`, if `a.row + r >= 2`, call
     `drawCell(board, a.row + r, a.col + c, COLORS[a.type])`.
5. If `g.over` is true: set `board.fillStyle = '#fff'`, `board.font = 'bold 36px sans-serif'` and
   `board.textAlign = 'center'`, call `board.fillText('GAME OVER', 150, 300)`, then set `board.textAlign = 'left'`.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls };
      for (const m of ['fillRect', 'strokeRect', 'clearRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'stroke'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ctx.strokeStyle, ...a]);
      ctx.fillStyle = ''; ctx.strokeStyle = ''; ctx.lineWidth = 1; ctx.font = ''; ctx.textAlign = 'left';
      return ctx;
    }
    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 5, col: 3 }, hold: 'L', holdUsed: false, score: 1200,
        lines: 14, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function texts(ctx) { return ctx.calls.filter((c) => c[0] === 'fillText').map((c) => String(c[3])); }
    function filledAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'fillRect' && c[1] === color && c[3] <= x + 1 && x + 1 < c[3] + c[5] && c[4] <= y + 1 && y + 1 < c[4] + c[6]); }
    function strokedAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'strokeRect' && c[2] === color && Math.abs(c[3] - x) <= 3 && Math.abs(c[4] - y) <= 3); }

Examples:

    (() => { const b = fake(); const g = mk(); g.board[21][0] = 'Z'; drawBoard(g, b); return [filledAt(b, 0, 570, 'red'), filledAt(b, 120, 120, 'purple'), filledAt(b, 90, 150, 'purple')]; })() ==> [true,true,false]
    (() => { const b = fake(); drawBoard(mk(), b); return [strokedAt(b, 120, 570, 'purple'), strokedAt(b, 90, 600 - 30, 'purple')]; })() ==> [true,true]
    (() => { const b = fake(); drawBoard(mk({ active: { type: 'I', rot: 0, row: 0, col: 3 } }), b); return filledAt(b, 90, 0, 'cyan'); })() ==> false
    (() => { const b = fake(); drawBoard(mk({ over: true, active: null }), b); return texts(b).some((t) => t.toUpperCase().includes('GAME OVER')); })() ==> true
    (() => { const b = fake(); drawBoard(mk(), b); return [texts(b).length, b.calls.filter((c) => c[0] === 'stroke').length, b.calls[0]]; })() ==> [0,32,["fillRect","#111","",0,0,300,600]]

## Unit `drawSide(g, side)`

Uses: `cellsOf`, `levelOf`, `COLORS`

Draw the side panel on `side`, a canvas 2D context of a 180 x 600 canvas: call its members directly, as in
`side.fillText(...)`. Use only these context members: `fillStyle`, `strokeStyle`, `lineWidth`, `font`, `textAlign`, `fillRect`, `strokeRect`,
`clearRect`, `fillText`, `beginPath`, `moveTo`, `lineTo`, `stroke`. Never call any other method (no `save`, `fill`,
`arc`, `measureText`, `getContext`).

Follow these steps exactly:

1. Set `side.fillStyle = '#222'` and call `side.fillRect(0, 0, 180, 600)`.
2. Set `side.fillStyle = '#eee'`, `side.font = '18px sans-serif'` and `side.textAlign = 'left'`. Call
   `side.fillText('Score ' + g.score, 10, 30)`, `side.fillText('Lines ' + g.lines, 10, 60)` and
   `side.fillText('Level ' + levelOf(g.lines), 10, 90)`.
3. Call `side.fillText('Next', 10, 130)`. For each of the first 3 letters `t` of `g.queue`, at index i: set
   `side.fillStyle = COLORS[t]`, and for each `[r, c]` of `cellsOf(t, 0)` call
   `side.fillRect(20 + c * 15, 145 + i * 70 + r * 15, 14, 14)`.
4. Set `side.fillStyle = '#eee'` and call `side.fillText('Hold', 10, 380)`. If `g.hold` is not null: set
   `side.fillStyle = COLORS[g.hold]`, and for each `[r, c]` of `cellsOf(g.hold, 0)` call
   `side.fillRect(20 + c * 15, 395 + r * 15, 14, 14)`.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls };
      for (const m of ['fillRect', 'strokeRect', 'clearRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'stroke'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ctx.strokeStyle, ...a]);
      ctx.fillStyle = ''; ctx.strokeStyle = ''; ctx.lineWidth = 1; ctx.font = ''; ctx.textAlign = 'left';
      return ctx;
    }
    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 5, col: 3 }, hold: 'L', holdUsed: false, score: 1200,
        lines: 14, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function texts(ctx) { return ctx.calls.filter((c) => c[0] === 'fillText').map((c) => String(c[3])); }
    function filledAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'fillRect' && c[1] === color && c[3] <= x + 1 && x + 1 < c[3] + c[5] && c[4] <= y + 1 && y + 1 < c[4] + c[6]); }
    function strokedAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'strokeRect' && c[2] === color && Math.abs(c[3] - x) <= 3 && Math.abs(c[4] - y) <= 3); }

Examples:

    (() => { const s = fake(); drawSide(mk(), s); return texts(s); })() ==> ["Score 1200","Lines 14","Level 2","Next","Hold"]
    (() => { const s = fake(); drawSide(mk({ hold: null, queue: ['O', 'T', 'S', 'Z'] }), s); return [texts(s).join('|'), s.calls.filter((c) => c[0] === 'fillRect').length]; })() ==> ["Score 1200|Lines 14|Level 2|Next|Hold",13]
    (() => { const s = fake(); drawSide(mk(), s); return s.calls.filter((c) => c[0] === 'fillRect' && c[1] === 'orange').map((c) => c.slice(3)); })() ==> [[50,395,14,14],[20,410,14,14],[35,410,14,14],[50,410,14,14]]

## Unit `draw(g, board, side)`

Uses: `drawBoard`, `drawSide`

Draw the whole game: call `drawBoard(g, board)`, then `drawSide(g, side)`. Nothing else.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls };
      for (const m of ['fillRect', 'strokeRect', 'clearRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'stroke'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ctx.strokeStyle, ...a]);
      ctx.fillStyle = ''; ctx.strokeStyle = ''; ctx.lineWidth = 1; ctx.font = ''; ctx.textAlign = 'left';
      return ctx;
    }
    function mk(o) {
      return Object.assign({ board: Array.from({ length: 22 }, () => Array(10).fill('')), queue: ['I', 'O', 'T'],
        rng: () => 0.5, active: { type: 'T', rot: 0, row: 5, col: 3 }, hold: 'L', holdUsed: false, score: 1200,
        lines: 14, over: false, paused: false, fall: 0, lock: 0, resets: 0 }, o || {});
    }
    function texts(ctx) { return ctx.calls.filter((c) => c[0] === 'fillText').map((c) => String(c[3])); }
    function filledAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'fillRect' && c[1] === color && c[3] <= x + 1 && x + 1 < c[3] + c[5] && c[4] <= y + 1 && y + 1 < c[4] + c[6]); }
    function strokedAt(ctx, x, y, color) { return ctx.calls.some((c) => c[0] === 'strokeRect' && c[2] === color && Math.abs(c[3] - x) <= 3 && Math.abs(c[4] - y) <= 3); }

Examples:

    (() => { const b = fake(), s = fake(); const g = mk(); g.board[21][0] = 'Z'; draw(g, b, s); return [filledAt(b, 0, 570, 'red'), filledAt(b, 120, 120, 'purple'), filledAt(b, 90, 150, 'purple')]; })() ==> [true,true,false]
    (() => { const b = fake(), s = fake(); draw(mk(), b, s); const t = texts(s).join('|'); return [t.includes('1200'), t.includes('14'), t.includes('2'), t.includes('Next'), t.includes('Hold'), texts(b).length]; })() ==> [true,true,true,true,true,0]
    (() => { const b = fake(), s = fake(); draw(mk({ over: true, active: null }), b, s); return texts(b).some((t) => t.toUpperCase().includes('GAME OVER')); })() ==> true

## Unit `startGame()`

Uses: `newGame`, `input`, `tick`, `snapshot`, `keyAction`, `draw`

Start the page. The document has `<canvas id="board" width="300" height="600">` and
`<canvas id="side" width="180" height="600">`. Write only `function startGame() { ... }`: the page calls it once,
after all the units, and the tests call it before each example. Inside startGame, follow these steps exactly:

1. `const bctx = document.getElementById('board').getContext('2d')` and
   `const sctx = document.getElementById('side').getContext('2d')`.
2. `let game = newGame(Date.now())` and `let testMode = false`.
3. `const paint = () => draw(game, bctx, sctx)`.
4. Set `window.tetris` to an object with these four methods. Write each one either as `reset(seed) { ... }` or as
   `reset: (seed) => { ... }`, never `reset: (seed) { ... }`; inside them the names `input` and `tick` still mean
   the top-level functions:
   - `reset(seed) { game = newGame(seed); testMode = true; paint(); }`
   - `input(action) { input(game, action); paint(); }`
   - `tick(ms) { tick(game, ms); paint(); }`
   - `state() { return snapshot(game); }`
5. `document.addEventListener('keydown', (e) => { ... })`. In the listener: let `act = keyAction(e)`. If `act` is
   null, return at once (no `preventDefault`). Otherwise call `e.preventDefault()`; then if `act` is `'restart'`
   set `game = newGame(Date.now())`, else call `input(game, act)`. Then `paint()`.
6. Real time: `let last = null` and a function `frame(t)` that does, in order: if `last` is null set `last = t`;
   let `ms = Math.min(100, Math.max(0, Math.round(t - last)))`; set `last = t`; if `testMode` is false and `ms > 0`,
   call `tick(game, ms)`; call `paint()`; call `requestAnimationFrame(frame)`.
7. Call `paint()` once, then `requestAnimationFrame(frame)`.

Test setup:

    var __frames = [], __listeners = {};
    function fakeCtx() { const c = {}; for (const m of ['fillRect', 'strokeRect', 'clearRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'stroke']) c[m] = () => {}; return c; }
    var window = globalThis;
    var document = {
      getElementById(id) { return { id, width: id === 'board' ? 300 : 180, height: 600, getContext() { return fakeCtx(); } }; },
      querySelector(s) { return this.getElementById(s.replace('#', '')); },
      addEventListener(type, fn) { (__listeners[type] = __listeners[type] || []).push(fn); },
    };
    function requestAnimationFrame(fn) { __frames.push(fn); return __frames.length; }
    var performance = { now() { return 0; } };
    function press(key, mods) { let prevented = false; const e = Object.assign({ key, ctrlKey: false, altKey: false, metaKey: false, preventDefault() { prevented = true; } }, mods || {}); (__listeners.keydown || []).forEach((f) => f(e)); return prevented; }

Examples:

    (startGame(), ['reset', 'input', 'tick', 'state'].map((k) => typeof window.tetris[k])) ==> ["function","function","function","function"]
    (() => { startGame(); window.tetris.reset(1); const s = window.tetris.state(); return [s.active, s.next, s.score]; })() ==> [{"type":"O","rotation":0,"row":0,"col":4,"cells":[[0,4],[0,5],[1,4],[1,5]]},["J","L","S"],0]
    (() => { startGame(); window.tetris.reset(7); window.tetris.input('left'); window.tetris.tick(1000); const s = window.tetris.state(); return [s.active.col, s.active.row]; })() ==> [2,1]
    (() => { startGame(); window.tetris.reset(3); const p = press('ArrowLeft'); return [p, window.tetris.state().active.col]; })() ==> [true,3]
    (() => { startGame(); window.tetris.reset(3); const p = press('c', { ctrlKey: true }); return [p, window.tetris.state().hold]; })() ==> [false,null]
    (() => { startGame(); window.tetris.reset(3); window.tetris.input('drop'); press('r'); const s = window.tetris.state(); return [s.score, s.board[21].join('')]; })() ==> [0,""]
    (startGame(), __frames.length > 0) ==> true

## Assemble `tetris.html`

The file is this page with every unit's code, in the order above, in place of `/*UNITS*/`. The page then calls
`startGame()` once:

    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>Tetris</title>
    <style>
    html, body { margin: 0; background: #111; color: #eee; font-family: sans-serif; }
    #wrap { display: flex; gap: 16px; justify-content: center; padding: 16px; }
    canvas { display: block; background: #000; }
    </style>
    </head>
    <body>
    <div id="wrap"><canvas id="board" width="300" height="600"></canvas><canvas id="side" width="180" height="600"></canvas></div>
    <script>
    /*UNITS*/
    startGame();
    </script>
    </body>
    </html>

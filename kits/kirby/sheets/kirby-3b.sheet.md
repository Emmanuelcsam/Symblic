# kirby.html

One self-contained HTML5 file (inline style and script, no external URL, library or network use) that implements
exactly this side-scrolling Kirby level on a canvas. Its JavaScript is written as the units below. Each unit is
written and tested on its own, and the file is assembled from the units that pass their tests.

Used units shown as: signatures

Answers normalized: yes

## Shared

Write plain browser JavaScript (ES2020) as top-level `function` and `const` declarations: no `import`, `export`,
`require`, classes, `console` or `Math.random`. Use only the names your unit declares and the names it lists under
"Uses". Never declare a name that another unit declares. The units under "Uses" already exist in the page: call them
and never write a placeholder for them (no `const LEVEL = /* provided */;` lines). Your answer is the declaration of
your unit only, starting with `function` or `const`.

The level is 12 rows x 64 columns of 32 x 32 px tiles, row 0 at the top: `'.'` air, `'#'` ground, `'='` one-way
platform, `'^'` spike, `'*'` star, `'D'` door. Positions are pixels, x to the right and y down. One step is one
frame (60 per second); speeds are pixels per step.

The game state `g` is one plain object with exactly these fields:

- `tiles`: 12 arrays of 64 one-letter strings, `g.tiles[row][col]`.
- `kirby`: `{x, y, vx, vy, face, ground, floating, floatT, inhaling, full, ability, hp, hurtT}`, a 24 x 24 box with
  top-left (x, y). `face` is 1 (right) or -1 (left). `full` is null or the kind of the enemy in his mouth. `ability`
  is `'none'` or `'wing'`. `hurtT` counts the steps left without damage.
- `enemies`: an array of `{kind, x, y, dir, t, baseY, alive}`, each a 24 x 24 box; kind `'W'` (waddle-dee) or `'B'`
  (bronto-burt).
- `shot`: null or the spit star `{x, y, dir}`, a 16 x 16 box.
- `keys`: `{left, right, inhale}`, true while that key is held.
- `score`, `cam` (the camera's left x), `acc` (time not yet stepped), `frame` (steps so far): numbers.
- `over`, `won`: booleans.

## Unit `LEVEL`

Given: yes

The level map, supplied by the sheet (no model writes it):

```js
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
```
Examples:

    LEVEL.length ==> 12
    LEVEL.every((row) => row.length === 64) ==> true
    LEVEL ==> ["................................................................","................................................................",".............................................*..................","..........................................B.....................",".........................***....................................","........................=====...................................","................................................................","...............**..................W............................","..............====...............######.....B...................","....***..#..W.....W........^^....######.............W...**...D..","####################....#######################..###############","####################....#######################..###############"]
    [LEVEL[9].indexOf('D'), LEVEL[10].indexOf('.'), LEVEL[10].lastIndexOf('.')] ==> [61,20,48]
    ['W', 'B', '*', '^', '=', 'D'].map((ch) => LEVEL.join('').split(ch).length - 1) ==> [4,2,11,2,9,1]

## Unit `mulberry32(seed)`

A random number generator, given as code: copy it. Follow exactly these steps:

1. Copy the code below exactly: the same lines, the same operators (`>>>`, `^`, `|`, `|=`) and the same constants, in the same order.
2. `mulberry32(a)` returns the inner `function () { ... }` itself, without calling it.
3. Each call of that inner function changes `a` and returns the next number in [0, 1).

    function mulberry32(a) {
      return function () {
        a |= 0; a = a + 0x6D2B79F5 | 0;
        var t = Math.imul(a ^ a >>> 15, 1 | a);
        t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
        return ((t ^ t >>> 14) >>> 0) / 4294967296;
      };
    }

Never write `>>` for `>>>`, never drop a `| 0` and never use `Math.random`: the examples check the exact numbers.

Examples:

    (() => { const r = mulberry32(1); return [r(), r(), r()]; })() ==> [0.6270739405881613,0.002735721180215478,0.5274470399599522]
    (() => { const r = mulberry32(2026); r(); return r(); })() ==> 0.30849614599719644
    (() => { const a = mulberry32(42), b = mulberry32(42); return [a() === b(), a() === b(), a()]; })() ==> [true,true,0.8524657934904099]
    (() => { const r = mulberry32(5); let s = 0; for (let i = 0; i < 1000; i++) s += r(); return [Math.round(s * 1000), r()]; })() ==> [480836,0.5903743733651936]

## Unit `tileAt(g, r, c), solidAt(g, r, c), standAt(g, r, c)`

Three functions that read the tile at row r, column c. Follow exactly these steps:

1. `tileAt(g, r, c)`: first `if (c < 0 || c > 63) return '#';` (the left and right edges are walls).
2. Then `if (r < 0) return '#';` (the top is a ceiling).
3. Then `if (r > 11) return '.';` (below the bottom is open: a pit).
4. Last `return g.tiles[r][c];`
5. `solidAt(g, r, c)`: `return tileAt(g, r, c) === '#';`
6. `standAt(g, r, c)`: `const t = tileAt(g, r, c);` then `return t === '#' || t === '=';`

solidAt and standAt call tileAt and return true or false, never a letter, and never read `g.tiles` themselves: row 12 or column 64 does not exist.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function lvl() { const t = grid(); t[9][5] = '='; t[9][6] = '^'; t[2][63] = '*'; return { tiles: t }; }

Examples:

    (() => { const g = lvl(); return [tileAt(g, 10, 0), tileAt(g, 9, 0), tileAt(g, 9, 5), tileAt(g, 9, 6), tileAt(g, 2, 63)]; })() ==> ["#",".","=","^","*"]
    (() => { const g = lvl(); return [tileAt(g, 5, -1), tileAt(g, 5, 64), tileAt(g, -1, 5), tileAt(g, 12, 5), tileAt(g, 12, 64), tileAt(g, -3, -3)]; })() ==> ["#","#","#",".","#","#"]
    (() => { const g = lvl(); return [solidAt(g, 10, 3), solidAt(g, 9, 3), solidAt(g, 9, 5), solidAt(g, 9, 6), solidAt(g, -1, 3), solidAt(g, 12, 3), solidAt(g, 4, 64)]; })() ==> [true,false,false,false,true,false,true]
    (() => { const g = lvl(); return [standAt(g, 10, 3), standAt(g, 9, 5), standAt(g, 9, 6), standAt(g, 9, 3), standAt(g, 3, 70), standAt(g, 15, 3), standAt(g, 2, 63)]; })() ==> [true,true,false,false,true,false,false]

## Unit `span(a, size)`

The first and the last tile index that a box from a to a + size covers (tiles are 32 px). Follow exactly these steps:

1. `const first = Math.floor(a / 32);`
2. `const last = Math.ceil((a + size) / 32) - 1;`
3. `return [first, last];` (an array of two numbers).

Never write `Math.floor((a + size) / 32)` for the last index: a box that ends exactly on a tile edge does not cover the next tile, so `span(8, 24)` is `[0, 0]`.

Examples:

    [span(0, 24), span(8, 24), span(10, 24)] ==> [[0,0],[0,0],[0,1]]
    [span(296, 24), span(296.25, 24), span(295.75, 24)] ==> [[9,9],[9,10],[9,9]]
    [span(-4, 24), span(-30, 24), span(40, 16)] ==> [[-1,0],[-1,-1],[1,1]]
    [span(1000, 32), span(1000.5, 32), span(2024, 24)] ==> [[31,32],[31,32],[63,63]]

## Unit `solidRow(g, r, x, w), standRow(g, r, x, w), solidCol(g, c, y, h)`

Uses: `span`, `solidAt`, `standAt`

Three tests of a box against one line of tiles. Follow exactly these steps:

1. `solidRow(g, r, x, w)`: `const [c0, c1] = span(x, w);`
2. Then `for (let c = c0; c <= c1; c++) if (solidAt(g, r, c)) return true;` and after the loop `return false;`
3. `standRow(g, r, x, w)`: the same two steps, calling `standAt(g, r, c)` instead of `solidAt(g, r, c)`.
4. `solidCol(g, c, y, h)`: `const [r0, r1] = span(y, h);`
5. Then `for (let r = r0; r <= r1; r++) if (solidAt(g, r, c)) return true;` and after the loop `return false;`

`span(a, size)` returns `[first, last]` tile indexes; `solidAt` is true for `'#'`, `standAt` for `'#'` or `'='`. Call these three and loop with `<=`; never compute `Math.floor(x / 32)` or read `g.tiles` yourself.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }

Examples:

    (() => { const g = { tiles: grid() }; return [solidRow(g, 10, 40, 24), solidRow(g, 9, 40, 24), standRow(g, 10, 40, 24), standRow(g, 9, 40, 24)]; })() ==> [true,false,true,false]
    (() => { const g = { tiles: grid() }; g.tiles[8][3] = '='; return [solidRow(g, 8, 80, 24), standRow(g, 8, 80, 24), standRow(g, 8, 72, 24), standRow(g, 8, 72, 23.5)]; })() ==> [false,true,false,false]
    (() => { const g = { tiles: grid() }; g.tiles[10][2] = '.'; g.tiles[10][3] = '.'; return [solidRow(g, 10, 64, 32), solidRow(g, 10, 60, 40), solidRow(g, 10, 70, 24), solidRow(g, 10, 120, 24)]; })() ==> [false,true,false,true]
    (() => { const g = { tiles: grid() }; g.tiles[9][5] = '#'; return [solidCol(g, 5, 296, 24), solidCol(g, 5, 270, 24), solidCol(g, 5, 250, 24), solidCol(g, 4, 296, 24)]; })() ==> [true,true,false,false]
    (() => { const g = { tiles: grid() }; return [solidCol(g, -1, 100, 24), solidCol(g, 64, 100, 24), solidCol(g, 3, -30, 24), solidCol(g, 3, 400, 24)]; })() ==> [true,true,true,false]
    (() => { const g = { tiles: grid() }; g.tiles[7][6] = '='; return [solidCol(g, 6, 220, 24), standRow(g, 7, 190, 24), standRow(g, 7, 168, 24)]; })() ==> [false,true,false]

## Unit `makeEnemy(kind, r, c, rng)`

Return a new enemy for the letter `kind` (`'W'` or `'B'`) found at row r, column c of the level. Follow exactly these steps:

1. `const dir = rng() < 0.5 ? -1 : 1;` (the first call of rng).
2. `const t = Math.floor(rng() * 64);` (the second call of rng).
3. `return { kind, x: c * 32 + 4, y: r * 32 + 8, dir, t, baseY: r * 32 + 8, alive: true };`

Call `rng()` exactly twice, `dir` first, and never swap r and c: x comes from the column c, y from the row r.

Test setup:

    function seq(values) { let k = 0; return () => values[k++ % values.length]; }

Examples:

    makeEnemy('W', 9, 12, seq([0.7, 0.5])) ==> {"kind":"W","x":388,"y":296,"dir":1,"t":32,"baseY":296,"alive":true}
    makeEnemy('B', 3, 42, seq([0.2, 0.99])) ==> {"kind":"B","x":1348,"y":104,"dir":-1,"t":63,"baseY":104,"alive":true}
    makeEnemy('W', 0, 0, seq([0.5, 0])) ==> {"kind":"W","x":4,"y":8,"dir":1,"t":0,"baseY":8,"alive":true}
    (() => { let n = 0; makeEnemy('B', 1, 1, () => { n++; return 0.3; }); return n; })() ==> 2
    (() => { const r = mulberry32(7); return [makeEnemy('W', 9, 12, r), makeEnemy('B', 8, 44, r)]; })() ==> [{"kind":"W","x":388,"y":296,"dir":-1,"t":3,"baseY":296,"alive":true},{"kind":"B","x":1412,"y":264,"dir":1,"t":44,"baseY":264,"alive":true}]

## Unit `parseLevel(rows, rng)`

Uses: `makeEnemy`

Turn level rows (strings) into `{ tiles, enemies }`. Follow exactly these steps:

1. `const tiles = [];` and `const enemies = [];`
2. `for (let r = 0; r < rows.length; r++)`: inside it, first `const row = [];` (a new array for every row).
3. Inside that, `for (let c = 0; c < rows[r].length; c++)` with `const ch = rows[r][c];`
4. If `ch === 'W' || ch === 'B'`: `enemies.push(makeEnemy(ch, r, c, rng));` and `row.push('.');`
5. Else `row.push(ch);`
6. After the inner loop, `tiles.push(row);` and after both loops, `return { tiles, enemies };`

`makeEnemy(kind, r, c, rng)` returns the new enemy and calls rng itself. Never declare `row` outside the row loop, never call `rng()` here, and never change `rows` (it is LEVEL itself).

Test setup:

    function seq(values) { let k = 0; return () => values[k++ % values.length]; }

Examples:

    parseLevel(['.W*', '#B=', '##D'], seq([0.7, 0.5, 0.1, 0.25])) ==> {"tiles":[[".",".","*"],["#",".","="],["#","#","D"]],"enemies":[{"kind":"W","x":36,"y":8,"dir":1,"t":32,"baseY":8,"alive":true},{"kind":"B","x":36,"y":40,"dir":-1,"t":16,"baseY":40,"alive":true}]}
    parseLevel(LEVEL, mulberry32(1)).enemies.map((e) => e.kind + ' ' + e.x + ' ' + e.y + ' ' + e.dir + ' ' + e.t) ==> ["B 1348 104 1 0","W 1124 232 1 62","B 1412 264 1 17","W 388 296 1 46","W 580 296 -1 63","W 1668 296 -1 31"]
    (() => { const L = parseLevel(LEVEL, mulberry32(3)); return [L.tiles.length, L.tiles[9].length, L.tiles[9].join(''), L.tiles[7].join(''), L.enemies.length]; })() ==> [12,64,"....***..#.................^^....######.................**...D..","...............**...............................................",6]
    (() => { const L = parseLevel(['ab', 'cd'], seq([0])); L.tiles[0][0] = 'z'; return [L.tiles, Array.isArray(L.tiles[1])]; })() ==> [[["z","b"],["c","d"]],true]

## Unit `newGame(seed)`

Uses: `LEVEL`, `mulberry32`, `parseLevel`

Return a new game state with every field of the shared state and no other field. Follow exactly these steps:

1. Write the whole function below, from its first line `function newGame(seed) {` to its last line `}`.
2. Inside it, first `const level = parseLevel(LEVEL, mulberry32(seed));` (`parseLevel(rows, rng)` returns `{ tiles, enemies }`).
3. Then `return` the object literal exactly as shown, field for field, so every call makes new objects (Kirby starts standing in column 1).

    function newGame(seed) {
      const level = parseLevel(LEVEL, mulberry32(seed));
      return {
        tiles: level.tiles,
        kirby: { x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0, inhaling: false,
          full: null, ability: 'none', hp: 6, hurtT: 0 },
        enemies: level.enemies,
        shot: null,
        keys: { left: false, right: false, inhale: false },
        score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false,
      };
    }

`LEVEL`, `mulberry32` and `parseLevel` already exist: call them, never redeclare them and never write a placeholder line such as `const LEVEL = /* provided */;`.

Examples:

    Object.keys(newGame(1)).sort() ==> ["acc","cam","enemies","frame","keys","kirby","over","score","shot","tiles","won"]
    newGame(1).kirby ==> {"x":40,"y":296,"vx":0,"vy":0,"face":1,"ground":true,"floating":false,"floatT":0,"inhaling":false,"full":null,"ability":"none","hp":6,"hurtT":0}
    newGame(1).enemies ==> [{"kind":"B","x":1348,"y":104,"dir":1,"t":0,"baseY":104,"alive":true},{"kind":"W","x":1124,"y":232,"dir":1,"t":62,"baseY":232,"alive":true},{"kind":"B","x":1412,"y":264,"dir":1,"t":17,"baseY":264,"alive":true},{"kind":"W","x":388,"y":296,"dir":1,"t":46,"baseY":296,"alive":true},{"kind":"W","x":580,"y":296,"dir":-1,"t":63,"baseY":296,"alive":true},{"kind":"W","x":1668,"y":296,"dir":-1,"t":31,"baseY":296,"alive":true}]
    (() => { const g = newGame(5); return [g.tiles[9].join(''), g.enemies.map((e) => e.dir), g.shot, g.keys, g.score, g.over, g.won]; })() ==> ["....***..#.................^^....######.................**...D..",[1,-1,-1,1,1,1],null,{"left":false,"right":false,"inhale":false},0,false,false]
    (() => { const a = newGame(2), b = newGame(2); a.tiles[9][4] = '.'; a.kirby.x = 99; return [b.tiles[9][4], b.kirby.x, a.enemies === b.enemies]; })() ==> ["*",40,false]

## Unit `cameraX(x)`

Return the camera's left edge for Kirby at x. The view is 640 px wide and the level 2048 px. Follow exactly these steps:

1. Kirby's middle is `x + 12`, and it goes 320 px from the view's left edge.
2. `const left = Math.floor(x + 12 - 320);`
3. `return Math.min(1408, Math.max(0, left));` (never left of 0, never past 2048 - 640 = 1408).

Floor first and never use `Math.round`: `cameraX(309.5)` is 1, not 2.

Examples:

    [cameraX(40), cameraX(0), cameraX(-50)] ==> [0,0,0]
    [cameraX(308), cameraX(309.5), cameraX(400.875)] ==> [0,1,92]
    [cameraX(1000), cameraX(1715.5), cameraX(1716)] ==> [692,1407,1408]
    [cameraX(1717), cameraX(2024), cameraX(5000)] ==> [1408,1408,1408]

## Unit `walk(g)`

Change Kirby's horizontal speed for one step from the held keys. Follow exactly these steps:

1. `const k = g.kirby;`
2. `const left = g.keys.left && !g.keys.right && !k.inhaling;` and `const right = g.keys.right && !g.keys.left && !k.inhaling;`
3. If `left`: `k.vx = Math.max(-2, k.vx - 0.125);` and `k.face = -1;`
4. Else if `right`: `k.vx = Math.min(2, k.vx + 0.125);` and `k.face = 1;`
5. Else if `k.vx > 0`: `k.vx = Math.max(0, k.vx - 0.25);` (friction).
6. Else if `k.vx < 0`: `k.vx = Math.min(0, k.vx + 0.25);`

walk changes only `k.vx` and `k.face`: never change `k.x`, and never set `k.vx` straight to 2, -2 or 0.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); g.keys.right = true; walk(g); return [g.kirby.vx, g.kirby.face, g.kirby.x]; })() ==> [0.125,1,40]
    (() => { const g = mk(); g.keys.left = true; const v = []; for (let i = 0; i < 18; i++) { walk(g); v.push(g.kirby.vx); } return [v[0], v[7], v[15], v[17], g.kirby.face]; })() ==> [-0.125,-1,-2,-2,-1]
    (() => { const g = mk({ kirby: kb({ vx: 1.5 }) }); const v = []; for (let i = 0; i < 8; i++) { walk(g); v.push(g.kirby.vx); } return v; })() ==> [1.25,1,0.75,0.5,0.25,0,0,0]
    (() => { const g = mk({ kirby: kb({ vx: -0.375, face: -1 }) }); walk(g); const a = g.kirby.vx; walk(g); return [a, g.kirby.vx, g.kirby.face]; })() ==> [-0.125,0,-1]
    (() => { const g = mk({ kirby: kb({ vx: 1 }) }); g.keys.left = true; g.keys.right = true; walk(g); return [g.kirby.vx, g.kirby.face]; })() ==> [0.75,1]
    (() => { const g = mk({ kirby: kb({ vx: 2, inhaling: true }) }); g.keys.right = true; walk(g); return [g.kirby.vx, g.kirby.face]; })() ==> [1.75,1]
    (() => { const g = mk({ kirby: kb({ vx: 1, face: 1 }) }); g.keys.left = true; walk(g); return [g.kirby.vx, g.kirby.face]; })() ==> [0.875,-1]

## Unit `fall(g)`

Update the float timer and Kirby's vertical speed for one step (vy > 0 is down). Follow exactly these steps:

1. `const k = g.kirby;`
2. If `k.floating`: `k.floatT = k.floatT + 1;` then, if `k.floatT >= 360`, `k.floating = false;`
3. Then a second, separate `if`: if `k.floating` is still true, `k.vy = Math.min(1, k.vy + 0.0625);`
4. Else `k.vy = Math.min(6, k.vy + 0.25);`

Never join steps 2 and 3 into one `if ... else`: when floating ends at 360, normal gravity applies in that same step; fall never changes `k.y`.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); fall(g); return [g.kirby.vy, g.kirby.floatT, g.kirby.y]; })() ==> [0.25,0,296]
    (() => { const g = mk({ kirby: kb({ vy: 5.9 }) }); fall(g); return g.kirby.vy; })() ==> 6
    (() => { const g = mk({ kirby: kb({ floating: true, vy: -2, floatT: 10 }) }); fall(g); return [g.kirby.vy, g.kirby.floatT, g.kirby.floating]; })() ==> [-1.9375,11,true]
    (() => { const g = mk({ kirby: kb({ floating: true, vy: 0.97 }) }); fall(g); return g.kirby.vy; })() ==> 1
    (() => { const g = mk({ kirby: kb({ floating: true, vy: 0.5, floatT: 359 }) }); fall(g); return [g.kirby.floating, g.kirby.floatT, g.kirby.vy]; })() ==> [false,360,0.75]
    (() => { const g = mk({ kirby: kb({ vy: 1, floatT: 360 }) }); fall(g); return [g.kirby.floatT, g.kirby.vy]; })() ==> [360,1.25]

## Unit `moveX(g)`

Uses: `solidCol`

Move Kirby sideways by `vx` and stop him at walls. Follow exactly these steps:

1. `const k = g.kirby;` then move first: `k.x = k.x + k.vx;`
2. If `k.vx > 0`: `const c = Math.ceil((k.x + 24) / 32) - 1;` (the column of his right edge).
3. Then, if `solidCol(g, c, k.y, 24)`: `k.x = c * 32 - 24;` and `k.vx = 0;`
4. Else if `k.vx < 0`: `const c = Math.floor(k.x / 32);` (the column of his left edge).
5. Then, if `solidCol(g, c, k.y, 24)`: `k.x = c * 32 + 32;` and `k.vx = 0;`

`solidCol(g, c, y, h)` is true when column c has a `'#'` in the rows from y to y + h (the level's edges count). Never test `g.tiles` yourself: `'='` and `'^'` never stop him sideways.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk({ kirby: kb({ vx: 1.5 }) }); moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [41.5,1.5]
    (() => { const g = mk({ kirby: kb({ x: 263, vx: 2 }) }); g.tiles[9][9] = '#'; moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [264,0]
    (() => { const g = mk({ kirby: kb({ x: 262, vx: 2 }) }); g.tiles[9][9] = '#'; moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [264,2]
    (() => { const g = mk({ kirby: kb({ x: 1, vx: -2 }) }); moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [0,0]
    (() => { const g = mk({ kirby: kb({ x: 2023, vx: 2 }) }); moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [2024,0]
    (() => { const g = mk({ kirby: kb({ x: 110, y: 200, vx: 2 }) }); g.tiles[6][4] = '^'; g.tiles[7][4] = '='; moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [112,2]
    (() => { const g = mk({ kirby: kb({ x: 321, y: 270, vx: -2 }) }); g.tiles[8][9] = '#'; moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [320,0]
    (() => { const g = mk({ kirby: kb({ x: 50, vx: 0 }) }); moveX(g); return [g.kirby.x, g.kirby.vx]; })() ==> [50,0]

## Unit `moveY(g)`

Uses: `solidRow`, `standRow`

Move Kirby by `vy`: land him, or stop his head at a ceiling. Follow exactly these steps:

1. `const k = g.kirby;` and `const before = k.y + 24;` (his bottom edge before the move).
2. `k.y = k.y + k.vy;` and `k.ground = false;`
3. If `k.vy > 0`: `const r = Math.ceil((k.y + 24) / 32) - 1;` (the row of his bottom edge).
4. He lands if `solidRow(g, r, k.x, 24) || (before <= r * 32 && standRow(g, r, k.x, 24))`.
5. To land: `k.y = r * 32 - 24; k.vy = 0; k.ground = true; k.floating = false; k.floatT = 0;`
6. Else if `k.vy < 0`: `const r = Math.floor(k.y / 32);` (his top edge's row).
7. Then, if `solidRow(g, r, k.x, 24)`: `k.y = r * 32 + 32;` and `k.vy = 0;`

`solidRow` finds a `'#'` in row r under the box, `standRow` a `'#'` or `'='`. Never drop `before <= r * 32`: a `'='` holds him only from above.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk({ kirby: kb({ vy: 0.25, ground: false }) }); moveY(g); return [g.kirby.y, g.kirby.vy, g.kirby.ground]; })() ==> [296,0,true]
    (() => { const g = mk({ kirby: kb({ y: 200, vy: 3 }) }); moveY(g); return [g.kirby.y, g.kirby.vy, g.kirby.ground]; })() ==> [203,3,false]
    (() => { const g = mk({ kirby: kb({ y: 290, vy: 6, ground: false, floating: true, floatT: 99 }) }); moveY(g); return g.kirby; })() ==> {"x":40,"y":296,"vx":0,"vy":6,"face":1,"ground":false,"floating":true,"floatT":99,"inhaling":false,"full":null,"ability":"none","hp":6,"hurtT":0}
    (() => { const g = mk({ kirby: kb({ y: 292, vy: 6, ground: false, floating: true, floatT: 99 }) }); moveY(g); return g.kirby; })() ==> {"x":40,"y":296,"vx":0,"vy":0,"face":1,"ground":true,"floating":false,"floatT":0,"inhaling":false,"full":null,"ability":"none","hp":6,"hurtT":0}
    (() => { const g = mk({ kirby: kb({ y: 228, vy: 5, ground: false }) }); g.tiles[8][1] = '='; moveY(g); return [g.kirby.y, g.kirby.vy, g.kirby.ground]; })() ==> [232,0,true]
    (() => { const g = mk({ kirby: kb({ y: 240, vy: 2, ground: false }) }); g.tiles[8][1] = '='; moveY(g); return [g.kirby.y, g.kirby.vy, g.kirby.ground]; })() ==> [242,2,false]
    (() => { const g = mk({ kirby: kb({ y: 260, vy: -6, ground: false }) }); g.tiles[7][1] = '='; moveY(g); return [g.kirby.y, g.kirby.vy]; })() ==> [254,-6]
    (() => { const g = mk({ kirby: kb({ y: 4, vy: -6, ground: false }) }); moveY(g); return [g.kirby.y, g.kirby.vy]; })() ==> [0,0]
    (() => { const g = mk({ kirby: kb({ y: 290, vy: -3 }) }); g.tiles[8][1] = '#'; moveY(g); return [g.kirby.y, g.kirby.vy, g.kirby.ground]; })() ==> [288,0,false]
    (() => { const g = mk({ kirby: kb({ x: 650, y: 380, vy: 6, ground: false }) }); for (const r of [10, 11]) { g.tiles[r][20] = '.'; g.tiles[r][21] = '.'; } moveY(g); return [g.kirby.y, g.kirby.ground]; })() ==> [386,false]

## Unit `jump(g)`

The jump key was pressed. Return the string `'jump'`, `'flap'` or `'none'`. Follow exactly these steps:

1. `const k = g.kirby;`
2. If `k.ground`: `k.vy = k.ability === 'wing' ? -8.5 : -6;`, `k.ground = false;` and `return 'jump';`
3. Else, if `k.full === null && k.floatT < 360`: `k.floating = true;`, `k.vy = -2;` and `return 'flap';` (every press while floating flaps again).
4. Otherwise change nothing and `return 'none';`

Always return one of those three strings, never true, false or nothing.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); return [jump(g), g.kirby.vy, g.kirby.ground, g.kirby.floating]; })() ==> ["jump",-6,false,false]
    (() => { const g = mk({ kirby: kb({ ability: 'wing' }) }); return [jump(g), g.kirby.vy, g.kirby.ground]; })() ==> ["jump",-8.5,false]
    (() => { const g = mk({ kirby: kb({ ground: false, vy: 3 }) }); return [jump(g), g.kirby.vy, g.kirby.floating]; })() ==> ["flap",-2,true]
    (() => { const g = mk(); jump(g); return [jump(g), g.kirby.vy, g.kirby.floating]; })() ==> ["flap",-2,true]
    (() => { const g = mk({ kirby: kb({ ground: false, vy: 1, full: 'W' }) }); return [jump(g), g.kirby.vy, g.kirby.floating]; })() ==> ["none",1,false]
    (() => { const g = mk({ kirby: kb({ ground: false, vy: 1, floatT: 360 }) }); return [jump(g), g.kirby.vy, g.kirby.floating]; })() ==> ["none",1,false]
    (() => { const g = mk({ kirby: kb({ full: 'B' }) }); return [jump(g), g.kirby.vy, g.kirby.floating]; })() ==> ["jump",-6,false]

## Unit `hurt(g)`

Kirby takes one hit. Follow exactly these steps:

1. `const k = g.kirby;` If `k.hurtT > 0` (still invulnerable), `return false;` and change nothing.
2. `k.hp = k.hp - 1;` and `k.hurtT = 90;`
3. Knockback: `k.vx = -2 * k.face;`, `k.vy = -3;` and `k.floating = false;`
4. If `k.hp <= 0`: `k.hp = 0;` and `g.over = true;`
5. `return true;`

Test `k.hp <= 0`, never `k.hp === 0`, so HP never goes below 0; set `g.over`, never `k.over`.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); return [hurt(g), g.kirby.hp, g.kirby.hurtT, g.kirby.vx, g.kirby.vy, g.over]; })() ==> [true,5,90,-2,-3,false]
    (() => { const g = mk({ kirby: kb({ face: -1, floating: true, ground: false }) }); hurt(g); return [g.kirby.vx, g.kirby.vy, g.kirby.floating]; })() ==> [2,-3,false]
    (() => { const g = mk({ kirby: kb({ hurtT: 5, vx: 1 }) }); return [hurt(g), g.kirby.hp, g.kirby.hurtT, g.kirby.vx]; })() ==> [false,6,5,1]
    (() => { const g = mk({ kirby: kb({ hp: 1 }) }); return [hurt(g), g.kirby.hp, g.over]; })() ==> [true,0,true]
    (() => { const g = mk(); hurt(g); hurt(g); return [g.kirby.hp, g.kirby.hurtT]; })() ==> [5,90]
    (() => { const g = mk({ kirby: kb({ hp: 0 }) }); hurt(g); return [g.kirby.hp, g.over]; })() ==> [0,true]

## Unit `boxesTouch(ax, ay, aw, bx, by, bw)`

Do two squares overlap? Square a has its top-left corner at (ax, ay) and side aw; square b at (bx, by) and side bw. Follow exactly these steps:

1. Test `ax < bx + bw` (a starts left of b's right edge).
2. Test `bx < ax + aw` (b starts left of a's right edge).
3. Test `ay < by + bw` and `by < ay + aw` (the same two tests downward: a square's side is also its height).
4. `return ax < bx + bw && bx < ax + aw && ay < by + bw && by < ay + aw;`

Use `<`, never `<=`: squares that only share an edge do not touch.

Examples:

    [boxesTouch(0, 0, 24, 10, 10, 24), boxesTouch(0, 0, 24, 24, 0, 24), boxesTouch(0, 0, 24, 23.5, 0, 24)] ==> [true,false,true]
    [boxesTouch(30, 30, 16, 0, 0, 24), boxesTouch(30, 30, 16, 10, 20, 24), boxesTouch(100, 0, 24, 90, 23, 24)] ==> [false,true,true]
    [boxesTouch(0, 0, 24, 0, -24, 24), boxesTouch(0, 0, 24, 0, -23, 24), boxesTouch(50, 50, 16, 60, 60, 24)] ==> [false,true,true]
    [boxesTouch(60, 60, 24, 50, 50, 16), boxesTouch(0, 0, 24, 30, 30, 24), boxesTouch(-10, 5, 24, 0, 0, 24)] ==> [true,false,true]

## Unit `inFront(k, e)`

Is enemy e close enough in front of Kirby k to be inhaled? Follow exactly these steps:

1. `const dx = (e.x - k.x) * k.face;` (how far e is ahead of him, in the direction he faces).
2. The three tests are `dx > 0` (ahead), `dx <= 64` (at most 2 tiles away) and `Math.abs(e.y - k.y) < 32` (less than a tile above or below).
3. `return dx > 0 && dx <= 64 && Math.abs(e.y - k.y) < 32;`

Never use `Math.abs(e.x - k.x)`: an enemy behind him must give false.

Test setup:

    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }

Examples:

    [inFront(kb(), en('W', 100, 296)), inFront(kb(), en('W', 104, 296)), inFront(kb(), en('W', 105, 296))] ==> [true,true,false]
    [inFront(kb({ face: -1 }), en('W', 100, 296)), inFront(kb({ x: 200, face: -1 }), en('B', 150, 270)), inFront(kb(), en('W', 40, 296))] ==> [false,true,false]
    [inFront(kb(), en('B', 80, 264)), inFront(kb(), en('B', 80, 265)), inFront(kb(), en('B', 80, 327)), inFront(kb(), en('B', 80, 328))] ==> [false,true,true,false]
    [inFront(kb({ x: 300, face: -1 }), en('W', 236, 296)), inFront(kb({ x: 300, face: -1 }), en('W', 235.5, 296)), inFront(kb({ x: 300, face: -1 }), en('W', 330, 296))] ==> [true,false,false]

## Unit `pull(g)`

Uses: `inFront`

Kirby is inhaling: pull the enemies in front of him and take into his mouth the first one that reaches it. Follow exactly these steps:

1. `const k = g.kirby;` then `for (const e of g.enemies)`, in order.
2. If `!e.alive || !inFront(k, e)`, skip it (`continue`).
3. Pull it 2 px toward him: `e.x = e.x - 2 * k.face;`
4. If now `(e.x - k.x) * k.face <= 24`: `e.alive = false;`, `k.full = e.kind;`, `k.inhaling = false;`, `g.score = g.score + 200;` and `return;`

`inFront(k, e)` is true when e is ahead of him, at most 64 px away and less than 32 px above or below. Return right after the first enemy reaches his mouth (one at a time), and never move Kirby.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk({ enemies: [en('W', 100, 296)] }); pull(g); return [g.enemies[0].x, g.enemies[0].alive, g.kirby.full, g.score]; })() ==> [98,true,null,0]
    (() => { const g = mk({ kirby: kb({ inhaling: true }), enemies: [en('W', 66, 296)] }); pull(g); return [g.enemies[0].x, g.enemies[0].alive, g.kirby.full, g.kirby.inhaling, g.score]; })() ==> [64,false,"W",false,200]
    (() => { const g = mk({ kirby: kb({ x: 300, face: -1 }), enemies: [en('B', 250, 290), en('W', 380, 296)] }); pull(g); return g.enemies.map((e) => e.x); })() ==> [252,380]
    (() => { const g = mk({ enemies: [en('W', 66, 296), en('B', 64, 300)] }); pull(g); return [g.enemies.map((e) => [e.x, e.alive]), g.kirby.full, g.score]; })() ==> [[[64,false],[64,true]],"W",200]
    (() => { const g = mk({ enemies: [en('W', 66, 296, { alive: false }), en('B', 90, 300)] }); pull(g); return [g.enemies.map((e) => e.x), g.kirby.full]; })() ==> [[66,88],null]
    (() => { const g = mk({ enemies: [en('W', 100, 296)] }); let n = 0; while (g.kirby.full === null && n < 99) { pull(g); n++; } return [n, g.enemies[0].x, g.score]; })() ==> [18,64,200]

## Unit `waddleStep(g, e)`

Uses: `solidAt`, `standAt`

Move a waddle-dee e one step: 0.5 px per step, turning around at walls and ledges. Follow exactly these steps:

1. `const nx = e.x + 0.5 * e.dir;` (where it would go).
2. `const c = e.dir > 0 ? Math.ceil((nx + 24) / 32) - 1 : Math.floor(nx / 32);` (its front edge's column).
3. `const r = Math.floor(e.y / 32);` (its row).
4. If `solidAt(g, r, c) || !standAt(g, r + 1, c)`: `e.dir = -e.dir;` and `return;`
5. Otherwise `e.x = nx;`

`solidAt(g, r, c)` is true for `'#'` and outside the left, right and top edges; `standAt(g, r, c)` for `'#'` or `'='`. A waddle-dee that turns does not move that step: never set `e.x = nx` after turning.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }

Examples:

    (() => { const g = { tiles: grid() }; const e = en('W', 388, 296); waddleStep(g, e); return [e.x, e.dir]; })() ==> [388.5,1]
    (() => { const g = { tiles: grid() }; const e = en('W', 388, 296, { dir: -1 }); waddleStep(g, e); waddleStep(g, e); return [e.x, e.dir]; })() ==> [387,-1]
    (() => { const g = { tiles: grid() }; g.tiles[9][9] = '#'; const e = en('W', 320, 296, { dir: -1 }); waddleStep(g, e); return [e.x, e.dir]; })() ==> [320,1]
    (() => { const g = { tiles: grid() }; g.tiles[10][20] = '.'; const e = en('W', 616, 296); waddleStep(g, e); return [e.x, e.dir]; })() ==> [616,-1]
    (() => { const g = { tiles: grid() }; g.tiles[10][20] = '.'; const e = en('W', 615.5, 296); waddleStep(g, e); return [e.x, e.dir]; })() ==> [616,1]
    (() => { const g = { tiles: grid() }; const e = en('W', 2024, 296); waddleStep(g, e); return [e.x, e.dir]; })() ==> [2024,-1]
    (() => { const g = { tiles: grid() }; for (let c = 33; c <= 38; c++) g.tiles[8][c] = '#'; const e = en('W', 1124, 232); const xs = []; for (let i = 0; i < 800; i++) { waddleStep(g, e); xs.push(e.x); } return [Math.min(...xs), Math.max(...xs), e.x, e.dir]; })() ==> [1056,1224,1187,1]
    (() => { const g = { tiles: grid() }; g.tiles[8][3] = '='; const e = en('W', 100, 232, { dir: -1 }); const xs = []; for (let i = 0; i < 40; i++) { waddleStep(g, e); xs.push(e.x); } return [Math.min(...xs), Math.max(...xs), e.dir]; })() ==> [96,104,-1]

## Unit `brontoStep(e)`

Move a bronto-burt e one step; it flies through tiles, so there is no tile test. Follow exactly these steps:

1. `e.t = e.t + 1;`
2. `e.x = e.x + e.dir;` (1 px per step).
3. If `e.t % 128 === 0`: `e.dir = -e.dir;` (it turns every 128 steps).
4. `e.y = e.baseY + Math.round(24 * Math.sin(e.t / 16));`

Keep this order (t, then x, then the turn), and compute `e.y` from `e.baseY` every step, never by adding to `e.y`.

Test setup:

    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }

Examples:

    (() => { const e = en('B', 100, 104); brontoStep(e); return e; })() ==> {"kind":"B","x":101,"y":105,"dir":1,"t":1,"baseY":104,"alive":true}
    (() => { const e = en('B', 100, 104, { t: 127 }); brontoStep(e); return [e.t, e.x, e.dir, e.y]; })() ==> [128,101,-1,128]
    (() => { const e = en('B', 100, 104, { dir: -1, t: 20 }); brontoStep(e); brontoStep(e); return [e.t, e.x, e.dir, e.y]; })() ==> [22,98,-1,128]
    (() => { const e = en('B', 500, 200); const ys = []; for (let i = 0; i < 300; i++) { brontoStep(e); ys.push(e.y); } return [Math.min(...ys), Math.max(...ys), e.t, e.x, e.dir, e.baseY]; })() ==> [176,224,300,544,1,200]
    (() => { const e = en('B', 0, 50, { t: 300, baseY: 60 }); brontoStep(e); return [e.t, e.x, e.y]; })() ==> [301,1,59]

## Unit `moveEnemies(g)`

Uses: `waddleStep`, `brontoStep`

Move every live enemy by one step. Follow exactly these steps:

1. Loop `for (const e of g.enemies)`.
2. If `!e.alive`, skip it (`continue`).
3. If `e.kind === 'W'`, call `waddleStep(g, e);`
4. Else call `brontoStep(e);`

`waddleStep(g, e)` and `brontoStep(e)` move the enemy themselves: call them, never write their movement again here, and never remove an enemy from `g.enemies`.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }

Examples:

    (() => { const g = { tiles: grid(), enemies: [en('W', 388, 296), en('B', 100, 104), en('W', 500, 296, { alive: false })] }; moveEnemies(g); return g.enemies.map((e) => [e.x, e.y, e.t, e.dir]); })() ==> [[388.5,296,0,1],[101,105,1,1],[500,296,0,1]]
    (() => { const g = newGame(1); for (let i = 0; i < 3; i++) moveEnemies(g); return g.enemies.map((e) => [e.kind, e.x, e.y, e.dir, e.t]); })() ==> [["B",1351,108,1,3],["W",1125.5,232,1,62],["B",1415,287,1,20],["W",389.5,296,1,46],["W",578.5,296,-1,63],["W",1666.5,296,-1,31]]
    (() => { const g = { tiles: grid(), enemies: [en('B', 10, 50, { alive: false }), en('W', 40, 296, { dir: -1 })] }; for (let i = 0; i < 30; i++) moveEnemies(g); return g.enemies.map((e) => [e.x, e.y, e.t, e.dir]); })() ==> [[10,50,0,1],[25,296,0,-1]]
    (() => { const g = { tiles: grid(), enemies: [en('B', 700, 100, { t: 126, dir: -1 }), en('W', 616, 296)] }; g.tiles[10][20] = '.'; moveEnemies(g); moveEnemies(g); return g.enemies.map((e) => [e.x, e.y, e.t, e.dir]); })() ==> [[698,124,128,1],[615.5,296,0,-1]]

## Unit `swallow(g), spit(g)`

Two actions of a full Kirby (`k.full` is the kind of the enemy in his mouth, or null). Follow exactly these steps:

1. `swallow(g)`: `const k = g.kirby;` If `k.full === null`, `return false;`
2. Then `k.ability = k.full === 'B' ? 'wing' : 'none';`, `k.full = null;` and `return true;`
3. `spit(g)`: `const k = g.kirby;` If `k.full === null`, `return false;`
4. Then `g.shot = { x: k.face > 0 ? k.x + 24 : k.x - 16, y: k.y + 4, dir: k.face };`, `k.full = null;` and `return true;`

Read `k.full` before setting it to null, and never change `k.ability` in spit.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk({ kirby: kb({ full: 'B' }) }); return [swallow(g), g.kirby.ability, g.kirby.full, g.shot]; })() ==> [true,"wing",null,null]
    (() => { const g = mk({ kirby: kb({ full: 'W', ability: 'wing' }) }); return [swallow(g), g.kirby.ability, g.kirby.full]; })() ==> [true,"none",null]
    (() => { const g = mk(); return [swallow(g), spit(g), g.kirby.ability, g.kirby.full, g.shot]; })() ==> [false,false,"none",null,null]
    (() => { const g = mk({ kirby: kb({ full: 'W' }) }); return [spit(g), g.shot, g.kirby.full, g.kirby.ability]; })() ==> [true,{"x":64,"y":300,"dir":1},null,"none"]
    (() => { const g = mk({ kirby: kb({ x: 200, y: 100, face: -1, full: 'B', ability: 'wing' }) }); spit(g); return [g.shot, g.kirby.ability, g.kirby.full]; })() ==> [{"x":184,"y":104,"dir":-1},"wing",null]
    (() => { const g = mk({ kirby: kb({ full: 'B' }) }); spit(g); return [spit(g), swallow(g), g.kirby.ability]; })() ==> [false,false,"none"]

## Unit `shotStep(g)`

Uses: `boxesTouch`, `solidAt`

Move the spit star one step. Follow exactly these steps:

1. `const s = g.shot;` If `s === null`, `return;`
2. `s.x = s.x + 6 * s.dir;`
3. `for (const e of g.enemies)`: if `e.alive && boxesTouch(s.x, s.y, 16, e.x, e.y, 24)`, then `e.alive = false;`, `g.score = g.score + 200;`, `g.shot = null;` and `return;`
4. After the loop: if `solidAt(g, Math.floor((s.y + 8) / 32), Math.floor((s.x + 8) / 32))`, `g.shot = null;` (a wall at the star's middle).

`boxesTouch(ax, ay, aw, bx, by, bw)` is true when the two squares overlap; `solidAt(g, r, c)` takes the row first. Return right after the first hit: the star never defeats two enemies.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk({ shot: { x: 64, y: 300, dir: 1 } }); shotStep(g); return [g.shot, g.score]; })() ==> [{"x":70,"y":300,"dir":1},0]
    (() => { const g = mk(); shotStep(g); return [g.shot, g.score]; })() ==> [null,0]
    (() => { const g = mk({ shot: { x: 64, y: 300, dir: 1 }, enemies: [en('W', 100, 296), en('W', 90, 296)] }); shotStep(g); const a = g.shot && g.shot.x; shotStep(g); return [a, g.shot, g.enemies.map((e) => e.alive), g.score]; })() ==> [70,null,[true,false],200]
    (() => { const g = mk({ shot: { x: 236, y: 300, dir: 1 } }); g.tiles[9][8] = '#'; shotStep(g); const a = g.shot && g.shot.x; shotStep(g); return [a, g.shot]; })() ==> [242,null]
    (() => { const g = mk({ shot: { x: 10, y: 100, dir: -1 } }); const xs = []; while (g.shot !== null && xs.length < 50) { xs.push(g.shot.x); shotStep(g); } return xs; })() ==> [10,4,-2,-8]
    (() => { const g = mk({ shot: { x: 1000, y: 100, dir: -1 }, enemies: [en('W', 980, 200)] }); shotStep(g); return [g.shot, g.enemies[0].alive]; })() ==> [{"x":994,"y":100,"dir":-1},true]
    (() => { const g = mk({ shot: { x: 100, y: 290, dir: 1 }, enemies: [en('W', 112, 296, { alive: false })] }); shotStep(g); return [g.shot, g.score]; })() ==> [{"x":106,"y":290,"dir":1},0]
    (() => { const g = mk({ shot: { x: 2020, y: 200, dir: 1 } }); const xs = []; while (g.shot !== null && xs.length < 50) { xs.push(g.shot.x); shotStep(g); } return xs; })() ==> [2020,2026,2032,2038]

## Unit `touchEnemies(g)`

Uses: `boxesTouch`, `hurt`

Kirby bumps into enemies. Follow exactly these steps:

1. `const k = g.kirby;` then `for (const e of g.enemies)`, in order.
2. Test `e.alive && k.hurtT === 0 && boxesTouch(k.x, k.y, 24, e.x, e.y, 24)`.
3. When it is true: `e.alive = false;` (the enemy is defeated), then call `hurt(g);`
4. Go on with the next enemy (no `return`).

`hurt(g)` takes 1 HP, knocks him back and sets `k.hurtT = 90`, so later enemies pass through him; `boxesTouch` is true when the two squares overlap. A bump gives no score: never change `g.score`, and never write hurt's steps here.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk({ enemies: [en('W', 60, 296)] }); touchEnemies(g); return [g.enemies[0].alive, g.kirby.hp, g.kirby.hurtT, g.kirby.vx, g.kirby.vy, g.score]; })() ==> [false,5,90,-2,-3,0]
    (() => { const g = mk({ enemies: [en('W', 64, 296), en('B', 40, 272)] }); touchEnemies(g); return [g.enemies.map((e) => e.alive), g.kirby.hp]; })() ==> [[true,true],6]
    (() => { const g = mk({ kirby: kb({ hurtT: 10 }), enemies: [en('W', 50, 296)] }); touchEnemies(g); return [g.enemies[0].alive, g.kirby.hp, g.kirby.hurtT]; })() ==> [true,6,10]
    (() => { const g = mk({ enemies: [en('W', 50, 296), en('B', 30, 290)] }); touchEnemies(g); return [g.enemies.map((e) => e.alive), g.kirby.hp, g.kirby.hurtT]; })() ==> [[false,true],5,90]
    (() => { const g = mk({ kirby: kb({ hp: 1 }), enemies: [en('B', 40, 280)] }); touchEnemies(g); return [g.kirby.hp, g.over, g.enemies[0].alive]; })() ==> [0,true,false]
    (() => { const g = mk({ enemies: [en('W', 50, 296, { alive: false })] }); touchEnemies(g); return [g.kirby.hp, g.kirby.hurtT]; })() ==> [6,0]

## Unit `touchTiles(g)`

Uses: `span`, `tileAt`, `hurt`

Kirby touches the tiles his box covers. Follow exactly these steps:

1. `const k = g.kirby;` then `const [r0, r1] = span(k.y, 24);` and `const [c0, c1] = span(k.x, 24);`
2. `for (let r = r0; r <= r1; r++)` and inside it `for (let c = c0; c <= c1; c++)`.
3. Inside: `const t = tileAt(g, r, c);`
4. If `t === '*'`: `g.tiles[r][c] = '.';` and `g.score = g.score + 100;`
5. Else if `t === '^'`: call `hurt(g);`
6. Else if `t === 'D'`: `g.won = true;`

`span(a, size)` returns `[first, last]` tile indexes, and `hurt(g)` does nothing while he is invulnerable. Get `t` only from `tileAt(g, r, c)`, never by reading `g.tiles[r][c]`: r and c can be outside the grid, where only tileAt answers.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); g.tiles[9][1] = '*'; touchTiles(g); return [g.score, g.tiles[9][1]]; })() ==> [100,"."]
    (() => { const g = mk({ kirby: kb({ x: 50 }) }); g.tiles[9][1] = '*'; g.tiles[9][2] = '*'; touchTiles(g); touchTiles(g); return [g.score, g.tiles[9].slice(0, 4)]; })() ==> [200,[".",".",".","."]]
    (() => { const g = mk(); g.tiles[9][1] = '^'; touchTiles(g); return [g.kirby.hp, g.kirby.hurtT, g.kirby.vx, g.kirby.vy]; })() ==> [5,90,-2,-3]
    (() => { const g = mk({ kirby: kb({ x: 50 }) }); g.tiles[9][1] = '^'; g.tiles[9][2] = '^'; touchTiles(g); touchTiles(g); return [g.kirby.hp, g.kirby.hurtT, g.tiles[9][1]]; })() ==> [5,90,"^"]
    (() => { const g = mk({ kirby: kb({ x: 1940 }) }); g.tiles[9][61] = 'D'; touchTiles(g); return [g.won, g.tiles[9][61]]; })() ==> [true,"D"]
    (() => { const g = mk({ kirby: kb({ x: 1920 }) }); g.tiles[9][61] = 'D'; touchTiles(g); return g.won; })() ==> false
    (() => { const g = mk({ kirby: kb({ y: 280 }) }); g.tiles[8][1] = '*'; g.tiles[10][1] = '*'; touchTiles(g); return [g.score, g.tiles[8][1], g.tiles[10][1]]; })() ==> [100,".","*"]
    (() => { const g = mk({ kirby: kb({ x: -8, y: -8 }) }); touchTiles(g); return [g.score, g.kirby.hp, g.won]; })() ==> [0,6,false]

## Unit `step(g)`

Uses: `walk`, `fall`, `moveX`, `moveY`, `moveEnemies`, `pull`, `shotStep`, `touchEnemies`, `touchTiles`, `cameraX`

Advance the game by one step (one frame). Follow exactly these steps, in this order:

1. If `g.over || g.won`, `return;`
2. `const k = g.kirby;` then `g.frame = g.frame + 1;` and, if `k.hurtT > 0`, `k.hurtT = k.hurtT - 1;`
3. `k.inhaling = g.keys.inhale && !k.floating && k.full === null;`
4. Call `walk(g);`, `fall(g);`, `moveX(g);`, `moveY(g);`
5. If `k.y > 384` (he fell into a pit): `k.hp = 0;`, `g.over = true;` and `return;`
6. Call `moveEnemies(g);` then, if `k.inhaling`, call `pull(g);`
7. Call `shotStep(g);`, `touchEnemies(g);`, `touchTiles(g);`
8. `g.cam = cameraX(k.x);`

Each called function changes `g` itself: call them in exactly this order and never copy their bodies here.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = newGame(1); step(g); return [g.frame, g.kirby, g.cam]; })() ==> [1,{"x":40,"y":296,"vx":0,"vy":0,"face":1,"ground":true,"floating":false,"floatT":0,"inhaling":false,"full":null,"ability":"none","hp":6,"hurtT":0},0]
    (() => { const g = newGame(1); g.keys.right = true; for (let i = 0; i < 60; i++) step(g); return [g.kirby.x, g.kirby.vx, g.score, g.tiles[9].slice(3, 8).join(''), g.frame]; })() ==> [145,2,200,"...*.",60]
    (() => { const g = mk({ over: true }); step(g); const w = mk({ won: true }); step(w); const c = mk({ kirby: kb({ x: 71, y: 262, vx: 2, vy: 4, ground: false }) }); c.tiles[9][3] = '#'; c.keys.right = true; step(c); return [g.frame, w.frame, c.kirby.x, c.kirby.y, c.kirby.vx, c.kirby.ground]; })() ==> [0,0,73,264,2,true]
    (() => { const g = mk({ kirby: kb({ x: 650, ground: false }), enemies: [en('B', 100, 100)] }); for (const r of [10, 11]) for (let c = 20; c <= 23; c++) g.tiles[r][c] = '.'; let n = 0; while (!g.over && n < 100) { step(g); n++; } return [n, g.over, g.kirby.hp, g.kirby.y, g.enemies[0].t]; })() ==> [27,true,0,389,26]
    (() => { const a = mk({ kirby: kb({ hurtT: 3 }) }); step(a); const b = mk({ kirby: kb({ hurtT: 1 }) }); b.tiles[9][1] = '^'; step(b); return [a.kirby.hurtT, a.frame, b.kirby.hurtT, b.kirby.hp]; })() ==> [2,1,90,5]
    (() => { const g = mk({ enemies: [en('W', 100, 296)] }); g.keys.inhale = true; const seen = []; for (let i = 0; i < 30; i++) { step(g); seen.push(g.kirby.inhaling); } return [g.kirby.full, g.score, seen.indexOf(false), g.enemies[0].alive, g.enemies[0].x]; })() ==> ["W",200,23,false,64]
    (() => { const g = mk({ kirby: kb({ floating: true, ground: false, y: 100, vy: 0 }) }); g.keys.inhale = true; step(g); return [g.kirby.inhaling, g.kirby.vy, g.kirby.floatT]; })() ==> [false,0.0625,1]
    (() => { const g = mk({ kirby: kb({ x: 1000, vx: 2 }), shot: { x: 1100, y: 300, dir: 1 }, enemies: [en('W', 1112, 296, { dir: -1 })] }); g.keys.right = true; step(g); return [g.kirby.x, g.cam, g.shot, g.score, g.enemies[0].alive]; })() ==> [1002,694,null,200,false]
    (() => { const g = mk({ enemies: [en('W', 64, 296, { dir: -1 })] }); step(g); return [g.kirby.hp, g.kirby.hurtT, g.kirby.vx, g.kirby.vy, g.enemies[0].alive, g.enemies[0].x]; })() ==> [5,90,-2,-3,false,63.5]
    (() => { const a = mk({ enemies: [en('W', 50, 296)], shot: { x: 30, y: 300, dir: 1 } }); a.tiles[9][1] = '^'; step(a); const b = mk({ enemies: [en('W', 50, 296)] }); b.tiles[9][1] = '^'; step(b); return [a.kirby.hp, a.score, a.shot, a.enemies[0].alive, b.kirby.hp, b.kirby.hurtT, b.enemies[0].alive]; })() ==> [5,200,null,false,5,90,false]

## Unit `tick(g, ms)`

Uses: `step`

Run the game for `ms` milliseconds at exactly 60 steps per second. Follow exactly these steps:

1. `g.acc = g.acc + ms * 60;`
2. `while (g.acc >= 1000)`: first `g.acc = g.acc - 1000;`, then call `step(g);`
3. After the loop, leave the rest in `g.acc` for the next call.

`step(g)` advances one step and does nothing once the game is over. Never touch `g.frame` (`step` counts the frames itself), never keep the accumulator in a local variable (it must stay in `g.acc` for the next call), never count steps with a division such as `Math.floor(ms / 16)` and never reset `g.acc` to 0: after 16 ms `g.acc` is 960 and no step ran.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); tick(g, 16); const a = [g.frame, g.acc]; tick(g, 1); return [a, g.frame, g.acc]; })() ==> [[0,960],1,20]
    (() => { const g = mk(); tick(g, 1000); return [g.frame, g.acc]; })() ==> [60,0]
    (() => { const g = mk(); for (let i = 0; i < 60; i++) tick(g, 50); return [g.frame, g.acc]; })() ==> [180,0]
    (() => { const g = mk(); tick(g, 0); tick(g, 33); return [g.frame, g.acc]; })() ==> [1,980]
    (() => { const a = newGame(4), b = newGame(4); a.keys.right = true; b.keys.right = true; tick(a, 2000); for (let i = 0; i < 2000; i++) tick(b, 1); return [a.frame, b.frame, JSON.stringify(a.kirby) === JSON.stringify(b.kirby), a.kirby.x]; })() ==> [120,120,true,264]
    (() => { const g = mk({ won: true }); tick(g, 100); return [g.frame, g.acc]; })() ==> [0,0]

## Unit `input(g, action, pressed)`

Uses: `jump`, `swallow`, `spit`

Apply one key change: `action` is `'left'`, `'right'`, `'jump'`, `'inhale'`, `'swallow'` or `'spit'`; `pressed` is true on key down. Follow exactly these steps:

1. If `g.over || g.won`, `return;`
2. If `action === 'left' || action === 'right'`: `g.keys[action] = pressed;`
3. Else if `action === 'inhale'`: if `pressed && g.kirby.floating`, `g.kirby.floating = false;` (he exhales); otherwise `g.keys.inhale = pressed;`
4. Else if `pressed && action === 'jump'`: call `jump(g);`
5. Else if `pressed && action === 'swallow'`: call `swallow(g);`
6. Else if `pressed && action === 'spit'`: call `spit(g);`

`jump`, `swallow` and `spit` change the state themselves. Never store `'jump'`, `'swallow'` or `'spit'` in `g.keys`, and never act on their release.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    (() => { const g = mk(); input(g, 'right', true); input(g, 'left', true); input(g, 'right', false); return g.keys; })() ==> {"left":true,"right":false,"inhale":false}
    (() => { const g = mk(); input(g, 'jump', true); return [g.kirby.vy, g.kirby.ground, g.kirby.floating]; })() ==> [-6,false,false]
    (() => { const g = mk(); input(g, 'jump', false); return [g.kirby.vy, g.kirby.ground]; })() ==> [0,true]
    (() => { const g = mk({ kirby: kb({ floating: true, ground: false }) }); input(g, 'inhale', true); return [g.kirby.floating, g.keys.inhale]; })() ==> [false,false]
    (() => { const g = mk(); input(g, 'inhale', true); const a = g.keys.inhale; input(g, 'inhale', false); return [a, g.keys.inhale]; })() ==> [true,false]
    (() => { const g = mk({ kirby: kb({ full: 'B' }) }); input(g, 'swallow', false); const a = g.kirby.full; input(g, 'swallow', true); return [a, g.kirby.ability, g.kirby.full]; })() ==> ["B","wing",null]
    (() => { const g = mk({ kirby: kb({ full: 'W' }) }); input(g, 'spit', false); const a = g.shot; input(g, 'spit', true); return [a, g.shot]; })() ==> [null,{"x":64,"y":300,"dir":1}]
    (() => { const g = mk({ over: true }); input(g, 'right', true); input(g, 'jump', true); return [g.keys.right, g.kirby.vy]; })() ==> [false,0]
    (() => { const g = mk(); input(g, 'fly', true); input(g, 'pause', true); return [g.keys, g.kirby.vy, g.shot]; })() ==> [{"left":false,"right":false,"inhale":false},0,null]

## Unit `snapshot(g)`

Return a NEW plain object that shares no object or array with g. Follow exactly these steps:

1. `const k = g.kirby;` and `let stars = 0;` then `for (const row of g.tiles) for (const t of row) if (t === '*') stars += 1;`
2. `const kirby = { x: k.x, y: k.y, vx: k.vx, vy: k.vy, face: k.face, ground: k.ground, floating: k.floating, floatT: k.floatT, inhaling: k.inhaling, full: k.full, ability: k.ability, hp: k.hp, hurtT: k.hurtT };`
3. `const enemies = g.enemies.map((e) => ({ kind: e.kind, x: e.x, y: e.y, dir: e.dir, t: e.t, alive: e.alive }));` (no `baseY`).
4. `const shot = g.shot === null ? null : { x: g.shot.x, y: g.shot.y, dir: g.shot.dir };`
5. `return { frame: g.frame, score: g.score, cam: g.cam, stars, over: g.over, won: g.won, kirby, enemies, shot };`

Never put `g.kirby`, `g.enemies` or `g.shot` itself in the result, and add no other field.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }
    function mk(o) {
      return Object.assign({ tiles: grid(), kirby: kb(), enemies: [], shot: null,
        keys: { left: false, right: false, inhale: false }, score: 0, cam: 0, acc: 0, frame: 0, over: false, won: false }, o || {});
    }

Examples:

    Object.keys(snapshot(newGame(1))).sort() ==> ["cam","enemies","frame","kirby","over","score","shot","stars","won"]
    snapshot(newGame(1)) ==> {"frame":0,"score":0,"cam":0,"stars":11,"over":false,"won":false,"kirby":{"x":40,"y":296,"vx":0,"vy":0,"face":1,"ground":true,"floating":false,"floatT":0,"inhaling":false,"full":null,"ability":"none","hp":6,"hurtT":0},"enemies":[{"kind":"B","x":1348,"y":104,"dir":1,"t":0,"alive":true},{"kind":"W","x":1124,"y":232,"dir":1,"t":62,"alive":true},{"kind":"B","x":1412,"y":264,"dir":1,"t":17,"alive":true},{"kind":"W","x":388,"y":296,"dir":1,"t":46,"alive":true},{"kind":"W","x":580,"y":296,"dir":-1,"t":63,"alive":true},{"kind":"W","x":1668,"y":296,"dir":-1,"t":31,"alive":true}],"shot":null}
    (() => { const g = mk({ shot: { x: 1, y: 2, dir: -1 }, enemies: [en('B', 5, 6, { t: 9, baseY: 0 })], score: 300, frame: 7, cam: 12, won: true }); g.tiles[3][3] = '*'; return snapshot(g); })() ==> {"frame":7,"score":300,"cam":12,"stars":1,"over":false,"won":true,"kirby":{"x":40,"y":296,"vx":0,"vy":0,"face":1,"ground":true,"floating":false,"floatT":0,"inhaling":false,"full":null,"ability":"none","hp":6,"hurtT":0},"enemies":[{"kind":"B","x":5,"y":6,"dir":1,"t":9,"alive":true}],"shot":{"x":1,"y":2,"dir":-1}}
    (() => { const g = newGame(1); const s = snapshot(g); s.kirby.x = 999; s.enemies[0].x = 999; s.enemies.push(1); return [g.kirby.x, g.enemies[0].x, g.enemies.length]; })() ==> [40,1348,6]
    (() => { const g = mk({ shot: { x: 1, y: 2, dir: 1 } }); const s = snapshot(g); s.shot.x = 50; return [g.shot.x, snapshot(g).shot.x]; })() ==> [1,1]
    (() => { const g = mk({ kirby: kb({ full: 'W', floatT: 33, hurtT: 4, inhaling: true }) }); const k = snapshot(g).kirby; return [Object.keys(k).length, k.full, k.floatT, k.hurtT, k.inhaling]; })() ==> [13,"W",33,4,true]

## Unit `keyAction(e)`

Return the game action for a keyboard event `e` (an object with `key`, `ctrlKey`, `altKey`, `metaKey`). Follow exactly these steps:

1. If `e.ctrlKey || e.altKey || e.metaKey`, `return null;` (those keys are left to the browser).
2. `const k = e.key;`
3. If `k === 'ArrowLeft' || k === 'a' || k === 'A'`, `return 'left';`
4. If `k === 'ArrowRight' || k === 'd' || k === 'D'`, `return 'right';`
5. If `k === 'ArrowUp' || k === ' ' || k === 'w' || k === 'W' || k === 'z' || k === 'Z'`, `return 'jump';`
6. If `k === 'x' || k === 'X'`, `return 'inhale';` and if `k === 'ArrowDown' || k === 's' || k === 'S'`, `return 'swallow';`
7. If `k === 'c' || k === 'C'`, `return 'spit';` and if `k === 'r' || k === 'R'`, `return 'restart';`
8. Otherwise `return null;`

Return the action word, never `e.key` itself, and `null`, never undefined, for every other key.

Examples:

    ['ArrowLeft', 'a', 'A', 'ArrowRight', 'd', 'D'].map((key) => keyAction({ key, ctrlKey: false, altKey: false, metaKey: false })) ==> ["left","left","left","right","right","right"]
    ['ArrowUp', ' ', 'w', 'W', 'z', 'Z'].map((key) => keyAction({ key, ctrlKey: false, altKey: false, metaKey: false })) ==> ["jump","jump","jump","jump","jump","jump"]
    ['x', 'X', 'ArrowDown', 's', 'S', 'c', 'C', 'r', 'R'].map((key) => keyAction({ key, ctrlKey: false, altKey: false, metaKey: false })) ==> ["inhale","inhale","swallow","swallow","swallow","spit","spit","restart","restart"]
    ['q', 'Enter', 'Shift', 'p', 'Escape', 'b', 'ArrowLeftX'].map((key) => keyAction({ key, ctrlKey: false, altKey: false, metaKey: false })) ==> [null,null,null,null,null,null,null]
    [keyAction({ key: 'c', ctrlKey: true, altKey: false, metaKey: false }), keyAction({ key: 'r', ctrlKey: false, altKey: false, metaKey: true }), keyAction({ key: 'ArrowLeft', ctrlKey: false, altKey: true, metaKey: false })] ==> [null,null,null]

## Unit `handleKey(game, e, pressed)`

Uses: `keyAction`, `input`

Handle one keyboard event `e` for the state `game` (`pressed` is true on keydown, false on keyup); return true only when the player asked for a new game. Follow exactly these steps:

1. `const act = keyAction(e);` If `act === null`, `return false;` (not a game key).
2. `e.preventDefault();` (the page must not scroll).
3. If `e.repeat`, `return false;`
4. If `act === 'restart'`, `return pressed;`
5. `input(game, act, pressed);` then `return false;`

`keyAction(e)` returns an action word or null; `input(g, action, pressed)` applies it. Never pass `'restart'` to input and never make the new game here: the caller does that when you return true.

Test setup:

    function ev(key, o) { const e = Object.assign({ key, repeat: false, ctrlKey: false, altKey: false, metaKey: false, prevented: false }, o || {}); e.preventDefault = () => { e.prevented = true; }; return e; }

Examples:

    (() => { const g = newGame(1); const e = ev('ArrowRight'); return [handleKey(g, e, true), e.prevented, g.keys.right]; })() ==> [false,true,true]
    (() => { const g = newGame(1); handleKey(g, ev('d'), true); const e = ev('d'); return [handleKey(g, e, false), e.prevented, g.keys.right]; })() ==> [false,true,false]
    (() => { const g = newGame(1); const e = ev('q'); return [handleKey(g, e, true), e.prevented]; })() ==> [false,false]
    (() => { const g = newGame(1); const e = ev('d', { ctrlKey: true }); return [handleKey(g, e, true), e.prevented, g.keys.right]; })() ==> [false,false,false]
    (() => { const g = newGame(1); handleKey(g, ev(' '), true); const a = g.kirby.vy; const e = ev(' ', { repeat: true }); return [a, handleKey(g, e, true), e.prevented, g.kirby.vy, g.kirby.floating]; })() ==> [-6,false,true,-6,false]
    (() => { const g = newGame(1); const d = ev('r'), u = ev('R'); return [handleKey(g, d, true), handleKey(g, u, false), d.prevented, u.prevented]; })() ==> [true,false,true,true]
    (() => { const g = newGame(1); g.kirby.full = 'B'; handleKey(g, ev('ArrowDown'), true); return g.kirby.ability; })() ==> "wing"

## Unit `circle(ctx, x, y, r, color), diamond(ctx, x, y, r, color)`

Two filled shapes on a canvas 2D context `ctx`. Follow exactly these steps:

1. `circle(ctx, x, y, r, color)`: `ctx.fillStyle = color;` then `ctx.beginPath();`
2. Then `ctx.arc(x, y, r, 0, Math.PI * 2);` then `ctx.fill();`
3. `diamond(ctx, x, y, r, color)`: `ctx.fillStyle = color;` then `ctx.beginPath();`
4. Then `ctx.moveTo(x, y - r);`, `ctx.lineTo(x + r, y);`, `ctx.lineTo(x, y + r);`, `ctx.lineTo(x - r, y);`
5. Then `ctx.closePath();` then `ctx.fill();`

Use exactly these calls in this order: never `stroke`, `save`, `restore` or `ellipse`, and never a rounded number such as 6.28 for `Math.PI * 2`.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }

Examples:

    (() => { const c = fake(); circle(c, 10, 20, 5, '#ff9ebd'); return c.calls; })() ==> [["beginPath","#ff9ebd"],["arc","#ff9ebd",10,20,5,0,6.283185307179586],["fill","#ff9ebd"]]
    (() => { const c = fake(); circle(c, -3.5, 0, 12, '#000'); circle(c, 1, 2, 3, 'red'); return [c.calls.length, c.calls[4], c.fillStyle]; })() ==> [6,["arc","red",1,2,3,0,6.283185307179586],"red"]
    (() => { const c = fake(); diamond(c, 100, 50, 10, '#ffd700'); return c.calls; })() ==> [["beginPath","#ffd700"],["moveTo","#ffd700",100,40],["lineTo","#ffd700",110,50],["lineTo","#ffd700",100,60],["lineTo","#ffd700",90,50],["closePath","#ffd700"],["fill","#ffd700"]]
    (() => { const c = fake(); diamond(c, 0, 0, 9, 'blue'); return [c.calls.map((x) => x[0]).join(' '), c.fillStyle]; })() ==> ["beginPath moveTo lineTo lineTo lineTo closePath fill","blue"]

## Unit `drawTile(ctx, ch, x, y)`

Uses: `diamond`

Draw one tile, top-left corner at (x, y), on `ctx`. Follow exactly these steps:

1. If `ch === '#'`: `ctx.fillStyle = '#8b5a2b'; ctx.fillRect(x, y, 32, 32); ctx.fillStyle = '#5c9e32'; ctx.fillRect(x, y, 32, 8);`
2. Else if `ch === '='`: `ctx.fillStyle = '#c68642'; ctx.fillRect(x, y, 32, 8);`
3. Else if `ch === '^'`: `ctx.fillStyle = '#9aa0a6'; ctx.beginPath(); ctx.moveTo(x, y + 32); ctx.lineTo(x + 16, y + 8); ctx.lineTo(x + 32, y + 32); ctx.closePath(); ctx.fill();`
4. Else if `ch === '*'`: `diamond(ctx, x + 16, y + 16, 10, '#ffd700');`
5. Else if `ch === 'D'`: `ctx.fillStyle = '#6b3e1f'; ctx.fillRect(x + 6, y, 20, 32); ctx.fillStyle = '#ffd700'; ctx.fillRect(x + 20, y + 16, 3, 3);`
6. Any other `ch`, such as `'.'`: draw nothing.

`diamond(ctx, x, y, r, color)` fills a diamond centred at (x, y): call it for the star. Never call `save`, `restore`, `stroke`, `ellipse`, `clearRect` or `getContext`.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }

Examples:

    (() => { const c = fake(); drawTile(c, '#', 64, 320); return c.calls; })() ==> [["fillRect","#8b5a2b",64,320,32,32],["fillRect","#5c9e32",64,320,32,8]]
    (() => { const c = fake(); drawTile(c, '=', -16, 256); return c.calls; })() ==> [["fillRect","#c68642",-16,256,32,8]]
    (() => { const c = fake(); drawTile(c, '^', 32, 288); return c.calls; })() ==> [["beginPath","#9aa0a6"],["moveTo","#9aa0a6",32,320],["lineTo","#9aa0a6",48,296],["lineTo","#9aa0a6",64,320],["closePath","#9aa0a6"],["fill","#9aa0a6"]]
    (() => { const c = fake(); drawTile(c, '*', 0, 0); return c.calls; })() ==> [["beginPath","#ffd700"],["moveTo","#ffd700",16,6],["lineTo","#ffd700",26,16],["lineTo","#ffd700",16,26],["lineTo","#ffd700",6,16],["closePath","#ffd700"],["fill","#ffd700"]]
    (() => { const c = fake(); drawTile(c, 'D', 160, 288); return c.calls; })() ==> [["fillRect","#6b3e1f",166,288,20,32],["fillRect","#ffd700",180,304,3,3]]
    (() => { const c = fake(); drawTile(c, '.', 0, 0); drawTile(c, 'W', 0, 0); return c.calls; })() ==> []

## Unit `drawTiles(ctx, g)`

Uses: `drawTile`

Draw the 21 tile columns the camera can see; drawTiles only calls `drawTile`. Follow exactly these steps:

1. `const c0 = Math.floor(g.cam / 32);` (the first visible column).
2. `for (let r = 0; r < 12; r++)`
3. Inside it, `for (let c = c0; c <= c0 + 20; c++)` (21 columns).
4. Inside: if `c < 64`, call `drawTile(ctx, g.tiles[r][c], c * 32 - g.cam, r * 32);`

`drawTile(ctx, ch, x, y)` draws one tile with its top-left corner at (x, y). Use `<= c0 + 20`, never `< c0 + 20`, and never set `ctx.fillStyle` or call `ctx.fillRect` here.

Test setup:

    function grid() { return Array.from({ length: 12 }, (_, r) => Array(64).fill(r >= 10 ? '#' : '.')); }
    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }
    function rects(c, color) { return c.calls.filter((x) => x[0] === 'fillRect' && x[1] === color).map((x) => x.slice(2)); }

Examples:

    (() => { const c = fake(); drawTiles(c, { tiles: grid(), cam: 0 }); return [c.calls.length, rects(c, '#5c9e32').length, rects(c, '#8b5a2b')[0], rects(c, '#8b5a2b').pop()]; })() ==> [84,42,[0,320,32,32],[640,352,32,32]]
    (() => { const c = fake(); drawTiles(c, { tiles: grid(), cam: 1408 }); const r = rects(c, '#8b5a2b'); return [r.length, r[0], r[r.length - 1]]; })() ==> [40,[0,320,32,32],[608,352,32,32]]
    (() => { const c = fake(); drawTiles(c, { tiles: grid(), cam: 16 }); const r = rects(c, '#8b5a2b'); return [r.length, r[0], r[20]]; })() ==> [42,[-16,320,32,32],[624,320,32,32]]
    (() => { const c = fake(); const t = grid(); t[9][3] = 'D'; t[0][25] = '='; drawTiles(c, { tiles: t, cam: 100 }); return [rects(c, '#6b3e1f'), rects(c, '#c68642')]; })() ==> [[[2,288,20,32]],[]]
    (() => { const c = fake(); const t = grid(); t[5][30] = '='; drawTiles(c, { tiles: t, cam: 300 }); return rects(c, '#c68642'); })() ==> []

## Unit `drawKirby(ctx, g)`

Uses: `circle`

Draw Kirby on `ctx`: a pink ball with red feet, two eyes and a mouth. Follow exactly these steps:

1. `const k = g.kirby;` If `k.hurtT > 0 && Math.floor(k.hurtT / 4) % 2 === 1`, `return;` (he blinks).
2. `const x = k.x + 12 - g.cam;`, `const y = k.y + 12;` and `const r = k.floating ? 15 : k.full !== null ? 14 : 12;`
3. Feet: `circle(ctx, x - 6, y + r - 2, 5, '#d81e3a');` then `circle(ctx, x + 6, y + r - 2, 5, '#d81e3a');`
4. Body: `circle(ctx, x, y, r, '#ff9ebd');`
5. Eyes: `ctx.fillStyle = '#000';` then `ctx.fillRect(x + 2 * k.face - 1, y - 7, 2, 6);` and `ctx.fillRect(x + 6 * k.face - 1, y - 7, 2, 6);`
6. Mouth: if `k.inhaling`, `circle(ctx, x + 7 * k.face, y + 3, 5, '#000');` else `ctx.fillRect(x + 4 * k.face - 2, y + 3, 4, 2);`

`circle(ctx, x, y, r, color)` fills a circle: call it. Never call `save`, `restore`, `stroke`, `ellipse`, `clearRect` or `getContext`.

Test setup:

    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }
    function shapes(c) { return c.calls.filter((x) => x[0] === 'arc' || x[0] === 'fillRect').map((x) => [x[0], x[1], x[2], x[3], x[4]]); }

Examples:

    (() => { const c = fake(); drawKirby(c, { kirby: kb(), cam: 0 }); return shapes(c); })() ==> [["arc","#d81e3a",46,318,5],["arc","#d81e3a",58,318,5],["arc","#ff9ebd",52,308,12],["fillRect","#000",53,301,2],["fillRect","#000",57,301,2],["fillRect","#000",54,311,4]]
    (() => { const c = fake(); drawKirby(c, { kirby: kb({ x: 700, y: 100, face: -1, floating: true }), cam: 400 }); return shapes(c); })() ==> [["arc","#d81e3a",306,125,5],["arc","#d81e3a",318,125,5],["arc","#ff9ebd",312,112,15],["fillRect","#000",309,105,2],["fillRect","#000",305,105,2],["fillRect","#000",306,115,4]]
    (() => { const c = fake(); drawKirby(c, { kirby: kb({ full: 'W', inhaling: false }), cam: 0 }); return shapes(c).map((s) => s[4]); })() ==> [5,5,14,2,2,4]
    (() => { const c = fake(); drawKirby(c, { kirby: kb({ inhaling: true }), cam: 0 }); return shapes(c).pop(); })() ==> ["arc","#000",59,311,5]
    (() => [90, 86, 85, 84, 81, 80, 3, 1, 0].map((h) => { const c = fake(); drawKirby(c, { kirby: kb({ hurtT: h }), cam: 0 }); return c.calls.length; }))() ==> [12,0,0,0,12,12,12,12,12]

## Unit `drawEnemy(ctx, e, cam)`

Uses: `circle`

Draw one enemy e on `ctx`. Follow exactly these steps:

1. If `!e.alive`, `return;`
2. `const x = e.x + 12 - cam;` and `const y = e.y + 12;`
3. If `e.kind === 'W'`: `circle(ctx, x - 6, y + 10, 4, '#8b4513');`, `circle(ctx, x + 6, y + 10, 4, '#8b4513');`, `circle(ctx, x, y, 12, '#f4a460');`, `circle(ctx, x + 3 * e.dir, y + 1, 7, '#ffe4c4');`
4. Else: `circle(ctx, x - 9, y - 9, 6, '#ffffff');`, `circle(ctx, x + 9, y - 9, 6, '#ffffff');`, `circle(ctx, x, y, 11, '#e75480');`
5. Then, for both kinds, the eye: `ctx.fillStyle = '#000';` and `ctx.fillRect(x + 4 * e.dir - 1, y - 4, 2, 5);`

`circle(ctx, x, y, r, color)` fills a circle: call it. Draw the eye once, after the if/else; never call `save`, `restore`, `stroke`, `ellipse`, `clearRect` or `getContext`.

Test setup:

    function en(kind, x, y, o) { return Object.assign({ kind, x, y, dir: 1, t: 0, baseY: y, alive: true }, o || {}); }
    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }
    function shapes(c) { return c.calls.filter((x) => x[0] === 'arc' || x[0] === 'fillRect').map((x) => [x[0], x[1], x[2], x[3], x[4]]); }

Examples:

    (() => { const c = fake(); drawEnemy(c, en('W', 388, 296), 0); return shapes(c); })() ==> [["arc","#8b4513",394,318,4],["arc","#8b4513",406,318,4],["arc","#f4a460",400,308,12],["arc","#ffe4c4",403,309,7],["fillRect","#000",403,304,2]]
    (() => { const c = fake(); drawEnemy(c, en('W', 388, 296, { dir: -1 }), 100); return shapes(c); })() ==> [["arc","#8b4513",294,318,4],["arc","#8b4513",306,318,4],["arc","#f4a460",300,308,12],["arc","#ffe4c4",297,309,7],["fillRect","#000",295,304,2]]
    (() => { const c = fake(); drawEnemy(c, en('B', 1348, 110), 1000); return shapes(c); })() ==> [["arc","#ffffff",351,113,6],["arc","#ffffff",369,113,6],["arc","#e75480",360,122,11],["fillRect","#000",363,118,2]]
    (() => { const c = fake(); drawEnemy(c, en('B', 10, 10, { alive: false }), 0); return c.calls; })() ==> []

## Unit `drawHud(ctx, g)`

Draw the HP bar, the score, the ability and the end message on `ctx`. Follow exactly these steps:

1. `for (let i = 0; i < 6; i++)`: `ctx.fillStyle = i < g.kirby.hp ? '#ff69b4' : '#555';` then `ctx.fillRect(10 + i * 18, 10, 14, 14);`
2. `ctx.fillStyle = '#000';`, `ctx.font = '16px monospace';` and `ctx.textAlign = 'left';`
3. `ctx.fillText('SCORE ' + g.score, 130, 23);` then `ctx.fillText('ABILITY ' + g.kirby.ability, 300, 23);`
4. If `g.over || g.won`: `ctx.font = 'bold 32px monospace';` and `ctx.textAlign = 'center';`
5. Still inside that `if`: `ctx.fillText(g.over ? 'GAME OVER' : 'LEVEL COMPLETE', 320, 192);` (leave `ctx.font` as it is).
6. After the `if` block, as the last statement of the function, always: `ctx.textAlign = 'left';` (the examples read `ctx.textAlign` after the call and expect `'left'`).

Always draw all 6 squares (grey `'#555'` for lost HP), and never call `save`, `restore`, `strokeText` or `measureText`.

Test setup:

    function kb(o) {
      return Object.assign({ x: 40, y: 296, vx: 0, vy: 0, face: 1, ground: true, floating: false, floatT: 0,
        inhaling: false, full: null, ability: 'none', hp: 6, hurtT: 0 }, o || {});
    }
    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }

Examples:

    (() => { const c = fake(); drawHud(c, { kirby: kb({ hp: 4 }), score: 1200, over: false, won: false }); return c.calls; })() ==> [["fillRect","#ff69b4",10,10,14,14],["fillRect","#ff69b4",28,10,14,14],["fillRect","#ff69b4",46,10,14,14],["fillRect","#ff69b4",64,10,14,14],["fillRect","#555",82,10,14,14],["fillRect","#555",100,10,14,14],["fillText","#000","16px monospace","left","SCORE 1200",130,23],["fillText","#000","16px monospace","left","ABILITY none",300,23]]
    (() => { const c = fake(); drawHud(c, { kirby: kb({ hp: 0, ability: 'wing' }), score: 0, over: true, won: false }); return [c.calls.slice(6), c.textAlign]; })() ==> [[["fillText","#000","16px monospace","left","SCORE 0",130,23],["fillText","#000","16px monospace","left","ABILITY wing",300,23],["fillText","#000","bold 32px monospace","center","GAME OVER",320,192]],"left"]
    (() => { const c = fake(); drawHud(c, { kirby: kb(), score: 700, over: false, won: true }); return [c.calls.filter((x) => x[0] === 'fillText').map((x) => x[4]), c.textAlign, c.font]; })() ==> [["SCORE 700","ABILITY none","LEVEL COMPLETE"],"left","bold 32px monospace"]
    (() => { const c = fake(); drawHud(c, { kirby: kb({ hp: 6 }), score: 5, over: false, won: false }); return [c.calls.filter((x) => x[1] === '#ff69b4').length, c.calls.filter((x) => x[1] === '#555').length, c.calls.length, c.font]; })() ==> [6,0,8,"16px monospace"]

## Unit `draw(ctx, g)`

Uses: `drawTiles`, `drawEnemy`, `diamond`, `drawKirby`, `drawHud`

Draw the whole frame on `ctx`, the context of the 640 x 384 canvas. Follow exactly these steps:

1. The sky: `ctx.fillStyle = '#87ceeb';` then `ctx.fillRect(0, 0, 640, 384);`
2. `drawTiles(ctx, g);`
3. `for (const e of g.enemies) drawEnemy(ctx, e, g.cam);`
4. If `g.shot !== null`: `diamond(ctx, g.shot.x + 8 - g.cam, g.shot.y + 8, 9, '#ffd700');`
5. `drawKirby(ctx, g);` then `drawHud(ctx, g);`

Each draw function draws its own part (drawEnemy skips dead enemies itself). Call them in this order and never copy their code; never call `getContext`, `clearRect`, `save` or `restore`.

Test setup:

    function fake() {
      const calls = [];
      const ctx = { calls, fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill'])
        ctx[m] = (...a) => calls.push([m, ctx.fillStyle, ...a]);
      ctx.fillText = (...a) => calls.push(['fillText', ctx.fillStyle, ctx.font, ctx.textAlign, ...a]);
      return ctx;
    }
    function arcs(c, color) { return c.calls.filter((x) => x[0] === 'arc' && x[1] === color).map((x) => x.slice(2, 5)); }

Examples:

    (() => { const c = fake(); draw(c, newGame(1)); return [c.calls[0], c.calls.length, arcs(c, '#ff9ebd'), arcs(c, '#f4a460')]; })() ==> [["fillRect","#87ceeb",0,0,640,384],214,[[52,308,12]],[[1136,244,12],[400,308,12],[592,308,12],[1680,308,12]]]
    (() => { const c = fake(); const g = newGame(1); g.cam = 1000; g.kirby.x = 1300; g.shot = { x: 1330, y: 300, dir: 1 }; draw(c, g); return [arcs(c, '#ff9ebd'), arcs(c, '#e75480'), c.calls.filter((x) => x[0] === 'moveTo' && x[1] === '#ffd700').map((x) => x.slice(2))]; })() ==> [[[312,308,12]],[[360,116,11],[424,276,11]],[[456,70],[338,299]]]
    (() => { const c = fake(); const g = newGame(1); g.over = true; draw(c, g); return c.calls.filter((x) => x[0] === 'fillText').map((x) => x[4]); })() ==> ["SCORE 0","ABILITY none","GAME OVER"]
    (() => { const c = fake(); const g = newGame(1); g.enemies.forEach((e) => { e.alive = false; }); g.kirby.hurtT = 5; draw(c, g); return [c.calls.length, arcs(c, '#ff9ebd').length, arcs(c, '#f4a460').length, c.calls[c.calls.length - 1][4]]; })() ==> [130,0,0,"ABILITY none"]

## Unit `startGame()`

Uses: `newGame`, `input`, `tick`, `snapshot`, `handleKey`, `draw`

Start the page. Write only `function startGame() { ... }`: the page calls it once and the tests call it before each example. Inside it, follow exactly these steps:

1. `const ctx = document.getElementById('game').getContext('2d');`
2. `let game = newGame(Date.now());`, `let testMode = false;` and `const paint = () => draw(ctx, game);`
3. `window.kirby = { reset(seed) { game = newGame(seed); testMode = true; paint(); }, input(action, pressed) { input(game, action, pressed); paint(); }, tick(ms) { tick(game, ms); paint(); }, state() { return snapshot(game); } };` (inside the methods, `input` and `tick` are the top-level functions).
4. `document.addEventListener('keydown', (e) => { if (handleKey(game, e, true)) game = newGame(Date.now()); paint(); });`
5. The same for `'keyup'`, with `handleKey(game, e, false)`.
6. `let last = null;` and `function frame(t)` that does, in order: if `last === null`, `last = t`; `const ms = Math.min(100, Math.max(0, t - last));`; `last = t;`; if `!testMode && ms > 0`, `tick(game, ms)`; `paint();`; `requestAnimationFrame(frame);`
7. Last: `paint();` then `requestAnimationFrame(frame);`

Write each method as `reset(seed) { ... }`, never `reset: (seed) { ... }`, and never call startGame yourself.

Test setup:

    var __frames = [], __listeners = {};
    function fakeCtx() {
      const c = { fillStyle: '', font: '', textAlign: 'left' };
      for (const m of ['fillRect', 'fillText', 'beginPath', 'moveTo', 'lineTo', 'closePath', 'arc', 'fill']) c[m] = () => {};
      return c;
    }
    var window = globalThis;
    var document = {
      getElementById(id) { return { id, width: 640, height: 384, getContext() { return fakeCtx(); } }; },
      querySelector(s) { return this.getElementById(s.replace('#', '')); },
      addEventListener(type, fn) { (__listeners[type] = __listeners[type] || []).push(fn); },
    };
    function requestAnimationFrame(fn) { __frames.push(fn); return __frames.length; }
    var performance = { now() { return 0; } };
    function key(type, k, o) {
      const e = Object.assign({ key: k, repeat: false, ctrlKey: false, altKey: false, metaKey: false, prevented: false }, o || {});
      e.preventDefault = () => { e.prevented = true; };
      (__listeners[type] || []).forEach((f) => f(e));
      return e.prevented;
    }

Examples:

    (startGame(), ['reset', 'input', 'tick', 'state'].map((k) => typeof window.kirby[k])) ==> ["function","function","function","function"]
    (() => { startGame(); window.kirby.reset(1); const s = window.kirby.state(); return [s.frame, s.kirby.x, s.enemies.length, s.stars, s.score]; })() ==> [0,40,6,11,0]
    (() => { startGame(); window.kirby.reset(1); window.kirby.input('right', true); window.kirby.tick(1000); const s = window.kirby.state(); return [s.frame, s.kirby.x, s.kirby.vx, s.score]; })() ==> [60,145,2,200]
    (() => { startGame(); window.kirby.reset(1); const p = key('keydown', 'ArrowRight'); window.kirby.tick(500); return [p, window.kirby.state().kirby.x]; })() ==> [true,85]
    (() => { startGame(); window.kirby.reset(1); key('keydown', 'ArrowRight'); key('keyup', 'ArrowRight'); window.kirby.tick(500); return window.kirby.state().kirby.x; })() ==> 40
    (() => { startGame(); window.kirby.reset(1); const p = key('keydown', 'd', { ctrlKey: true }); window.kirby.tick(500); return [p, window.kirby.state().kirby.x]; })() ==> [false,40]
    (() => { startGame(); window.kirby.reset(1); key('keydown', ' '); const a = window.kirby.state().kirby.vy; key('keydown', ' ', { repeat: true }); return [a, window.kirby.state().kirby.vy]; })() ==> [-6,-6]
    (() => { startGame(); window.kirby.reset(1); window.kirby.input('right', true); window.kirby.tick(1000); key('keydown', 'r'); const s = window.kirby.state(); return [s.frame, s.kirby.x, s.score]; })() ==> [0,40,0]
    (() => { startGame(); __frames[0](1000); __frames[1](1500); return [__frames.length, window.kirby.state().frame]; })() ==> [3,6]
    (() => { startGame(); window.kirby.reset(2); __frames[0](1000); __frames[1](1100); return [__frames.length, window.kirby.state().frame]; })() ==> [3,0]

## Assemble `kirby.html`

The file is this page with every unit's code, in the order above, in place of `/*UNITS*/`. The page then calls
`startGame()` once:

    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Kirby</title>
    <style>
    html, body { margin: 0; background: #222; color: #eee; font-family: sans-serif; }
    #wrap { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 16px; }
    canvas { display: block; max-width: 100%; background: #87ceeb; }
    p { margin: 0; font-size: 14px; text-align: center; }
    </style>
    </head>
    <body>
    <div id="wrap">
    <canvas id="game" width="640" height="384"></canvas>
    <p>Arrows or A/D walk. Space, W, Z or Up jumps; in the air it floats and flaps. X inhales (hold it; while floating it exhales). S or Down swallows, C spits a star. R starts again.</p>
    </div>
    <script>
    /*UNITS*/
    startGame();
    </script>
    </body>
    </html>

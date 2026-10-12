// Reference drawing and page units (drawCell, drawBoard, ..., startGame) of the spec sheet, in plain script form
// (not a module): build/dryrun.py appends them to ref-units.mjs to answer every unit. Not shown to models.
function drawCell(ctx, r, c, color) {
  ctx.fillStyle = color;
  ctx.fillRect(c * 30 + 1, (r - 2) * 30 + 1, 28, 28);
}

function drawBoard(g, board) {
  board.fillStyle = '#111'; board.fillRect(0, 0, 300, 600);
  board.strokeStyle = '#333'; board.lineWidth = 1;
  for (let c = 0; c <= 10; c++) { board.beginPath(); board.moveTo(c * 30, 0); board.lineTo(c * 30, 600); board.stroke(); }
  for (let r = 0; r <= 20; r++) { board.beginPath(); board.moveTo(0, r * 30); board.lineTo(300, r * 30); board.stroke(); }
  for (let r = 2; r < 22; r++) for (let c = 0; c < 10; c++) {
    const v = g.board[r][c];
    if (v !== '') drawCell(board, r, c, COLORS[v]);
  }
  if (g.active) {
    const a = g.active;
    let gr = a.row;
    while (fits(g.board, a.type, a.rot, gr + 1, a.col)) gr += 1;
    board.strokeStyle = COLORS[a.type]; board.lineWidth = 2;
    for (const [r, c] of cellsOf(a.type, a.rot)) if (gr + r >= 2) board.strokeRect((a.col + c) * 30 + 2, (gr + r - 2) * 30 + 2, 26, 26);
    for (const [r, c] of cellsOf(a.type, a.rot)) if (a.row + r >= 2) drawCell(board, a.row + r, a.col + c, COLORS[a.type]);
  }
  if (g.over) { board.fillStyle = '#fff'; board.font = 'bold 36px sans-serif'; board.textAlign = 'center'; board.fillText('GAME OVER', 150, 300); board.textAlign = 'left'; }
}

function drawSide(g, side) {
  side.fillStyle = '#222'; side.fillRect(0, 0, 180, 600);
  side.fillStyle = '#eee'; side.font = '18px sans-serif'; side.textAlign = 'left';
  side.fillText('Score ' + g.score, 10, 30); side.fillText('Lines ' + g.lines, 10, 60); side.fillText('Level ' + levelOf(g.lines), 10, 90);
  side.fillText('Next', 10, 130);
  g.queue.slice(0, 3).forEach((t, i) => { side.fillStyle = COLORS[t]; for (const [r, c] of cellsOf(t, 0)) side.fillRect(20 + c * 15, 145 + i * 70 + r * 15, 14, 14); });
  side.fillStyle = '#eee'; side.fillText('Hold', 10, 380);
  if (g.hold !== null) { side.fillStyle = COLORS[g.hold]; for (const [r, c] of cellsOf(g.hold, 0)) side.fillRect(20 + c * 15, 395 + r * 15, 14, 14); }
}

function draw(g, board, side) {
  drawBoard(g, board);
  drawSide(g, side);
}

function startGame() {
  const bctx = document.getElementById('board').getContext('2d');
  const sctx = document.getElementById('side').getContext('2d');
  let game = newGame(Date.now());
  let testMode = false;
  const paint = () => draw(game, bctx, sctx);
  window.tetris = {
    reset(seed) { game = newGame(seed); testMode = true; paint(); },
    input(action) { input(game, action); paint(); },
    tick(ms) { tick(game, ms); paint(); },
    state() { return snapshot(game); },
  };
  document.addEventListener('keydown', (e) => {
    const a = keyAction(e);
    if (!a) return;
    e.preventDefault();
    if (a === 'restart') game = newGame(Date.now()); else input(game, a);
    paint();
  });
  let last = null;
  function frame(t) {
    if (last === null) last = t;
    const ms = Math.min(100, Math.max(0, Math.round(t - last)));
    last = t;
    if (!testMode && ms > 0) tick(game, ms);
    paint();
    requestAnimationFrame(frame);
  }
  paint();
  requestAnimationFrame(frame);
}

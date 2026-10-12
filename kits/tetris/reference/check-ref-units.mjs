// ref-units.mjs (the reference written as the sheet's units) must agree with the oracle (reference.mjs, the
// specification written as one class) on every state after every action of 300 seeded random games.
//
//   node kits/tetris/reference/check-ref-units.mjs        prints the number of steps compared; exit 1 on a difference
import * as U from './ref-units.mjs';
import { Game, mulberry32 } from './reference.mjs';

let checked = 0;
function run(seed, actions) {
  const ref = new Game(seed), g = U.newGame(seed);
  const same = () => JSON.stringify(ref.state()) === JSON.stringify(U.snapshot(g));
  if (!same()) throw new Error(`seed ${seed}: differ at reset`);
  actions.forEach((a, i) => {
    if (typeof a === 'number') { ref.tick(a); U.tick(g, a); } else { ref.input(a); U.input(g, a); }
    checked++;
    if (!same()) throw new Error(`seed ${seed}: differ after step ${i} (${JSON.stringify(a)})\nref ${JSON.stringify(ref.state())}\nunits ${JSON.stringify(U.snapshot(g))}`);
  });
}
const pool = ['left', 'right', 'down', 'cw', 'ccw', 'left', 'right', 'drop', 'hold', 'pause', 'pause', 37, 120, 500, 1000, 2500];
for (let seed = 1; seed <= 300; seed++) {
  const rng = mulberry32(seed * 13 + 5);
  run(seed, Array.from({ length: 400 }, () => pool[Math.floor(rng() * pool.length)]));
}
console.log(`ref-units agrees with the oracle: 300 seeds, ${checked} steps`);

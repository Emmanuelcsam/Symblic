# Tetris results: two pages written by small local models

Each page is a complete, self-contained `tetris.html`: open it in a browser (arrows move, Up/X and Z rotate, Space
drops, C or Shift holds, P pauses, R restarts). Both were built from `../sheets/tetris.sheet.md` by Symblic programs
in which local models wrote every unit, in Ollama on CPU-only machines; the kernel tested each unit against the
sheet's examples and assembled the page from passing units only. Nobody edited a page afterwards.

Both were graded again on 2026-10-11 with this repository's harness (`node kits/tetris/harness/harness.mjs PAGE`):
**`39/39 required checks passed; 0/2 advisory`** for each. The advisory checks want the score and "GAME OVER" as page
text; these pages draw them on the canvas.

| page | built | models | how | cost |
|---|---|---|---|---|
| `tetris-90ffd27f92ab.html` | 2026-10-04, finished 05:01 | qwen3:4b-instruct, phi4-mini, gemma3:4b | 14 incremental builds while the sheet was being reworded; each kept what the last one accepted (`--keep`) | 421 model calls, 21 model-hours |
| `tetris-3566050e304f.html` | 2026-10-04, 08:30-10:24 | the same three models | one build of the final sheet from scratch: nothing kept, no cached answers, samples 5 | 141 model calls, 8.7 model-hours; all 25 units accepted on their first attempt |

In the first build, qwen3:4b-instruct (asked first in each round) wrote every accepted unit; the other two models
passed 14 of the 25 units too and lost the tie. In the second, a second model also passed in 12 of the 25 units. The
two pages differ (models sample), and both pass. About 30% of each page's non-trivial script lines appear word for
word in the sheet (`kits/tetris/build/verbatim.py`: 30.1% and 30.7%), mostly in the drawing steps, `startGame` and
the PRNG, which the sheet gives as code.

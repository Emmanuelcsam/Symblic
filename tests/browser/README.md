# tests/browser: page tests for web/

Two kinds of test live here, all written for Node.js's built-in runner (`node --test`).

**Node-only tests run anywhere.** They load the pure page modules from `web/studio/` with `node:vm` or as ES
modules and need nothing but Node.js 22:

| File | What it checks |
|---|---|
| `symblic-studio-text-mode.mjs` | The early text-mode parser, compiler and plan (`web/studio/js/symblic/`). |
| `symblic-english-circuit.mjs` | The instruction-circuit projection of compiled English programs (`symblic-english-circuit.js`). |
| `symblic-english-atomic-construction-circuit.mjs`, `symblic-english-construction-circuit.mjs`, `symblic-english-pixel-circuit.mjs` | The same projection for construction and pixel programs, against fixtures in `tests/fixtures/` produced by the real compiler. The browser part of the construction file is a page journey (below). |
| `symblic-pixel-vm.mjs` | The pixel-program interpreter and player (`symblic-pixel-vm.js`, `symblic-pixel-program.js`), parsing with `symblic/js/acorn.js`. |
| `symblic-graph-number-scan.test.mjs` | The numeric-literal scanner of the graph tab (`symblic-graphs.js`). |
| `symblic-academy.mjs` | The catalog facts its Academy journeys rely on (`web/academy/symblic-academy-content.js`). The journeys themselves are page journeys; see below. |

**Page journeys need the original host's harness.** The other files drive the real pages in headless Chromium
through the host's Playwright harness (`_mock.mjs` and `_journey.mjs` in the host checkout): it served the host's
files at the host's URL paths, its shared page library (`/studio.js`, `/studio.css`) and answered every `/api/`
call from the test's fixture. None of that is part of this repository, so `host-harness.mjs` registers every
journey as **skipped** with the reason, unless `SYMBLIC_BROWSER_HARNESS` names a compatible harness module.
They are kept as precise, executable descriptions of how each page behaved.

**The Academy's journeys are the exception.** The Academy (`web/academy/`) is static: `symblic-academy.mjs` loads
`/web/academy/index.html` and the documents it shows from the harness's root, and the page calls no `/api/` route. It
needs a harness with the same interface whose root is this repository (the host's harness served the host's checkout,
where the page was `/symblic-learn.html`); without one its journeys are skipped with a reason that says so. They
cover a lesson answered wrong and then right, the research map and its reader (plain text, the catalog's `sha256`, a
deep link that recovers from a failed fetch), the link rules, the missing-catalog message, the cloze checker, and the
Check and Preview buttons that need a host. The first journey runs on a phone and a desktop, light and dark, with
axe, and checks that the course, the research map, the readings, the syntax drills and the Parsons puzzles fit the
screen (against the viewport's width, since a phone browser zooms out to show a wider page); the others run on a
desktop. While this repository was prepared they were run with such a harness (Playwright 1.63.0, axe-core 4.11.1,
headless Chromium): 10 of 10 tests passed in each of five runs, and in each of four runs after the drills and
puzzles checks were added. That harness is not part of this repository either.

Run everything with

    node --test tests/browser/symblic-*.mjs

`fixtures/symblic-composition.json` is the fixture of the graph-composition journey.

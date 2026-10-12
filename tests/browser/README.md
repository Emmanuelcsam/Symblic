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

**Page journeys need the original host's harness.** The other files drive the real pages in headless Chromium
through the host's Playwright harness (`_mock.mjs` and `_journey.mjs` in the host checkout): it served the host's
files at the host's URL paths, its shared page library (`/studio.js`, `/studio.css`) and answered every `/api/`
call from the test's fixture. None of that is part of this repository, so `host-harness.mjs` registers every
journey as **skipped** with the reason, unless `SYMBLIC_BROWSER_HARNESS` names a compatible harness module.
They are kept as precise, executable descriptions of how each page behaved.

Run everything with

    node --test tests/browser/symblic-*.mjs

`fixtures/symblic-composition.json` is the fixture of the graph-composition journey.

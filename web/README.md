# web: the Symblic pages of the original host

Symblic was built inside a private home-server system ("the host", see `integration/host/README.md`). The host
served these browser pages for it, kept here:

- `hub/` was served at `/symblic/`: an overview of the tools, the 2026-10-08 beta record, demos written by fresh
  agent sessions, the trial records and the measured "atomic" results.
- `studio/` was served at `/automation-studio/`: the Symblic studio page (`symblic.html`: write, check, preview,
  run and compare programs, plus English, graphs, policies, memory, workcards, supervisor and help tabs), its
  static guides, and the host's general automation canvas that the Symblic text mode plugged into.
- `academy/` was served at `/symblic-learn`: the Symblic Academy, a self-paced course (lessons with checkpoints,
  flashcards, drills, quizzes) with a reader for the documents of this repository.

**Most of these pages need a host to do anything beyond display.** The host provided a shared page library
(`/studio.js`, `/studio.css`), and every button that checks, runs or saves calls its HTTP API, whose server side
is in `integration/host/`. Without a host, the static parts below still work, and the pure JavaScript modules run
under Node.js and are tested.

## What works without the host

Serve the folder with any static file server, because browsers refuse `fetch()` from `file://` pages:

    python3 -m http.server --directory web 8000
    # then open http://localhost:8000/hub/ and http://localhost:8000/studio/symblic-guides/index.html

The Academy's reader also loads documents from outside `web/`, so for it serve the repository root instead
(`python3 -m http.server 8000` there) and open http://localhost:8000/web/academy/.

| Part | Works as static files? | Notes |
|---|---|---|
| `hub/index.html` | Yes: overview, lanes, demos, records, For agents, Atomic results | `hub/standalone-shell.js` stands in for the host's page library when `/studio.js` is absent. The Construct and Autogen sections and the Atomic "Run it yourself" form call the host API and report an error without it. |
| `hub/beta.html` | Yes | The beta gallery: every prompt, command, output and failure of the 2026-10-08 trial, with frame players. The data is embedded in the page. |
| `hub/records/` | Yes | Plain files: reviews, run logs, statements, task records, verification scripts. Paths inside them were rewritten to neutral ones (`/srv/symblic/projects/...`, `node-a`, `host-checkout/`). |
| `hub/demos/graphview/`, `hub/demos/pcb/` | Yes | Pages written entirely by fresh agent sessions from English statements, with every generated script (the graph view's note data is fictional); kept as built, so they keep their own look. One change for publication: in `graphview/graph-input.js` the four variables that hold where a drag or touch began were renamed (`originX`, `originY`, `touchOriginX`, `touchOriginY`). The Kirby demo page is not included, only its statements. |
| `hub/atomic/results.json` | Yes | The measured results the Atomic section shows. The study's sheets and built pages are not included. |
| `academy/` | Yes, except Check and Preview | The course, the practice sections and the research reader (with the repository root served). `hub/standalone-shell.js` stands in for the host's page library here too. Check and Preview in Projects and Playground call the host API and, without it, say so and send nothing. See `academy/README.md`. |
| `studio/symblic-guides/` | Yes | Static guides generated from `docs/reference/` by `tools/scripts/build_symblic_guides.cjs` (needs marked 15.0.12). Links back to the studio page need a host. |
| `studio/symblic.html` | No | The studio page. It needs the host's page library, two host scripts that are not part of this repository (a team editor and a task composer) and the host API for every action. Its own scripts and styles are the `symblic-*.js` / `symblic-*.css` files next to it. |
| `studio/symblic-help-content.json` | Data | The help text of the studio page, written for the host: topics about the host's other pages were removed and host names replaced by neutral words; file:line references are approximate. |
| `studio/index.html`, `styles.css`, `js/ui.js`, `js/graph.js`, `js/constants.js` | No | The host's general automation canvas, kept because the Symblic text mode belonged to it. Several of its modules (`state.js`, `inspector.js`, `api.js`, `app.js` and others) and its backend are not part of this repository. |

## Pure JavaScript you can run with Node.js

| Module | What it is | Test |
|---|---|---|
| `studio/js/symblic/` (`parser.js`, `compiler.js`, `plan.js`, `settings.js`, `constants.js`, `utils.js`) | The early Symblic text mode of the automation canvas: a line-oriented workflow language (`Program:`, `Module:`, `Branch:`, `Loop:`) parsed into statements and compiled to a canvas workflow graph. It predates the formal language in `symblic/kernel/` and is not the same language. ES modules; `js/utils.js` is its one other dependency. | `tests/browser/symblic-studio-text-mode.mjs` |
| `studio/symblic-english-circuit.js` | Projects a compiled English program into the "instruction circuit" view: statements, model memory and check reads. | `tests/browser/symblic-english-circuit.mjs`, `symblic-english-atomic-construction-circuit.mjs`, `symblic-english-construction-circuit.mjs`, `symblic-english-pixel-circuit.mjs` |
| `studio/symblic-pixel-vm.js`, `studio/symblic-pixel-program.js` | A small interpreter for model-written pixel programs (parsed with acorn, `symblic/js/acorn.js`) and their frame player. Pinned by subresource-integrity hashes in `symblic.html`: change them only together. The page loads the parser from `/symblic_js_contract_acorn.js` (the original host's URL, which the presenter's pinned code looks up), so a host must serve `symblic/js/acorn.js` at that path. | `tests/browser/symblic-pixel-vm.mjs` |
| `studio/symblic-graphs.js` (number scanning) | The graph tab's parser for numeric literals. | `tests/browser/symblic-graph-number-scan.test.mjs` |
| `studio/symblic-intent.js` | The intent interpreter tab, exercised against a fake DOM and API. | `tests/integration/test_symblic_intent_page.py` (runs `tests/symblic_intent_page_check.js`) |

Run them with

    node --test tests/browser/symblic-*.mjs

The other files in `tests/browser/` are page journeys written for the host's Playwright harness; without it they
are reported as skipped (see `tests/browser/host-harness.mjs`).

## What calls the host API

| Script | API prefix (server side) |
|---|---|
| `studio/symblic-page.js`, `symblic-english.js`, `hub/atomic/atomic.js`, `academy/symblic-learn.js` (check and preview, only when the host's page library is loaded) | `/api/automation/symblic/` (`integration/host/symblic_engine.py` and its sub-route modules) |
| `studio/symblic-experiments.js`, `-graphs.js`, `-inquiry.js`, `-intent.js`, `-logic.js`, `-memory.js`, `-policies.js`, `-supervisor.js`, `-workcards.js`, `hub/mica.js` | `/api/automation/symblic/<tab>/` (`integration/host/symblic_*_api.py`) |
| `hub/autogen.js`, `studio/symblic-english.js` (catalog) | `/api/symblicos/` (`integration/host/symblicos_engine.py`) |
| `studio/symblic-picker.js` | `/api/runner/engines` (the host runner's engine catalogue; not in this repository) |
| `hub/mica.js` (worker probes) | `/api/cluster/status`, `/api/fleet/probe` (the host's fleet; not in this repository) |
| `studio/js/ui.js`, `studio/js/symblic.js` | `/api/automation/list`, `save`, `health`, `compile` (the host's automation engine; not in this repository) |
| `hub/subnav.js` | none; a navigation strip of the host's routes, included by no page here |

## Experimental and unmeasured

Everything here is a user interface for the experiments described in `docs/reference/`. The pages were tested
against fixtures (the journeys in `tests/browser/`), not with users; the Academy was checked in headless Chromium
when it was added, and its course, written by AI agents, has not been reviewed. Results shown in the beta gallery,
the demos and the atomic table are single recorded runs on the original host; they are evidence of what happened
then, not measurements of reliability.

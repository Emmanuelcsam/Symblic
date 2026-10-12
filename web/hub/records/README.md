# Symblic Beta Trial Records (2026-10-08)

This directory preserves the complete historical record, prompts, and run logs of the heavy beta trial of **Symblic** (`symblic#english`), which created both the **Kirby animation** (`/symblic-beta-kirby/`) and **Obsidian 3D Graph View** (`/symblic-beta-graphview/`) sub-sites.

---

In this repository the folder is `web/hub/records/` (the demos are in `web/hub/demos/`). Two files listed below
were not kept: `beta-kirby-draft-v1.english.txt` and `graphview-statements-v2-changelog.txt`; the Kirby page itself is
not included either, only its statements.

## 1. Directory Contents

| File | Description |
| :--- | :--- |
| [`SYMBLIC-CRITICAL-ANALYSIS.md`](SYMBLIC-CRITICAL-ANALYSIS.md) | **Comprehensive Critical Analysis**: Honest benefits, failures, successes, roadmap, and use cases |
| `beta-kirby-draft-v1.english.txt` (not kept) | Initial draft prompt (4 statements) using relative workspace paths |
| [`beta-kirby-executed-v2.english.txt`](beta-kirby-executed-v2.english.txt) | **Canonical executed prompt** (4 statements) with absolute paths and strict contracts |
| [`beta-graphview-draft-v1.english.txt`](beta-graphview-draft-v1.english.txt) | Initial draft prompt (8 statements) before compiler/agent critique |
| [`beta-graphview-executed-v2.english.txt`](beta-graphview-executed-v2.english.txt) | **Canonical executed prompt** (8 statements) with 15 fixes applied post-review |
| `graphview-statements-v2-changelog.txt` (not kept) | Detailed changelog of the 15 fixes between Graph View v1 and v2 |
| [`beta-trial-2026-10-08.md`](beta-trial-2026-10-08.md) | Original trial design document, architecture facts, and test plan |
| [`beta-trial-run-log.md`](beta-trial-run-log.md) | Authoritative execution log, verification findings, and product bug fixes |
| [`task-kirby-run2.json`](task-kirby-run2.json) | SymblicOS task execution state record for Kirby (Run 2: `task-5a01358e3c72da875f5ca269dbc8fe0e`) |
| [`task-graphview-run2.json`](task-graphview-run2.json) | SymblicOS task execution state record for Graph View (Run 2: `task-e84d63615eeffa5fb2800fd8c11ca529`) |

Copies of the prompts are also saved directly in their respective subsite folders:
- Kirby: [`symblic-beta-kirby/prompt-executed.english.txt`](../demos/kirby/prompt-executed.english.txt)
- Graph View: [`symblic-beta-graphview/prompt-executed.english.txt`](../demos/graphview/prompt-executed.english.txt)

---

## 2. Key Differences Between v1 (Draft) and v2 (Executed)

### Kirby (`beta-kirby.english.txt`)
- **Folder resolution**: In v1, statements used relative paths like `Create the file kirby.html`. Because Symblic spins up a fresh AGY session per statement line in `mode: lines`, fresh agents were prone to wandering outside the workspace. In v2, every statement explicitly targets `/srv/symblic/projects/beta-kirby`.
- **Incremental state preservation**: Statement 3 explicitly mandates `keeping every existing part`.
- **Validation formatting**: Exact verify file syntax specified (`kirby.js: pass` or error message).

### Graph View (`beta-graphview.english.txt`)
- **Absolute Paths**: Every statement specifies `/srv/symblic/projects/beta-graphview`.
- **15 Technical Fixes in v2**:
  1. Engine exposes `getParameter` and `reheat`.
  2. Engine exposes `pin(id, x, y, z)` with 3D coordinate targets.
  3. `positions` schema returns `ghost` and `tag` boolean flags.
  4. Tag nodes added as hollow diamonds linked from notes for the Tags filter switch.
  5. Renderer `setOption` extended with filter switches (`attachments`, `unresolved`, `orphans`, `tags`).
  6. `highlight` option supports one, many, or no IDs.
  7. Added `focusDepth` option (subgraph link hop bounding).
  8. Added `unproject` method on renderer to project screen pointer into 3D world space.
  9. Dual-canvas architecture: WebGL2 base canvas + 2D transparent overlay canvas for crisp label rendering.
  10. Added `getOption` on renderer.
  11. Drag behavior in `graph-input.js` connects `unproject` + `pin` + `reheat`.
  12. Hover reporting flows through `onHover` callback.
  13. UI controls read initial values with `getOption` / `getParameter`.
  14. Force sliders trigger engine `reheat` on change.
  15. `index.html` binds explicit canvas IDs (`graph-canvas`, `label-canvas`, `settings-panel`) and initializes rAF loop with `renderer.frame()`.
  16. Dataset constraints enforce exactly 12 distinct unresolved node IDs and ensure orphans are not attachments.

---

## 3. Execution Infrastructure

- **Agent Engine**: `agy` (`accept-edits` mode, `gemini-3.8-flash-high`).
- **Endpoint**: `POST /api/symblicos/tasks/start` with `mode: 'lines'`.
- **Verification**: Zero code was written by the overseeing CLI agent. All files were generated purely by the Symblic line-by-line compiler dispatching to fresh AGY sessions, followed by independent DOM, headless Chrome, pixel color, and syntax checks.

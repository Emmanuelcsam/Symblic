# tests

The unit tests of every package, one folder per package (`tests/kernel` tests `symblic/kernel`, and so on). They
use fake models, fake hosts and temporary folders. **No test calls a real model, starts a real agent or touches a
network service.** All of them were written by the same AI agents that wrote the code, so a passing suite says the
code does what its tests expect, not that a human checked it.

## Running them

One package (Python 3.12, from the repository root):

    DASH_TEST=1 python3 -m unittest discover -s tests/kernel -t .

Everything:

    DASH_TEST=1 python3 -m unittest discover -s tests -t .
    node --test tests/browser/symblic-*.mjs          # the page tests; Node.js 22

`DASH_TEST=1` tells the code it is under test. The name comes from the system Symblic was built in. Code that
would otherwise start real work checks it: `symblic/autogen/kernel_lane.py` then starts no systemd scope, refuses
to start a real kernel build (that would call a model) and reads no live model inventory. Most packages never
read it, but setting it always is the safe habit. The test modules set up their own temporary folders and
environment variables.

**Run time.** There are about 4,560 tests. While this repository was being prepared, one full run on a loaded
6-core desktop took about two hours of wall time (about 72 CPU-minutes; the kernel suite alone about 16 minutes).
A later run on the same machine, lightly loaded, with `TMPDIR` in `/dev/shm` and the packages split over two
parallel lanes, took about 45 minutes; the longest suites were `integration` (15 min), `mica` (14 min), `graph`
(10 min), `kernel` (9 min) and `english` (6 min). The suites that write and `fsync` many small files gain most from
memory-backed temporary files: `mica` took 819 s with `TMPDIR=/dev/shm/...` against more than 1,800 s on disk.

    mkdir -p /dev/shm/symblic-tests && TMPDIR=/dev/shm/symblic-tests DASH_TEST=1 python3 -m unittest discover -s tests/mica -t .

A few tests wait for a background thread or process. Their waits were lengthened after three of them failed on a
machine with a load average of 15 to 18; if a test fails only under load, please report it.

## What is skipped, and what is expected to fail

- **Host-only tests skip with a reason.** About 20 test modules and cases cover code that only ran inside the
  original host (its HTTP routes, store and agent runner, kept in [`../integration/host/`](../integration/host/README.md)).
  They live in [`integration/`](integration/README.md), which lists each module and whether it runs here or why
  it skips. Each skip message says what is missing.
- **Tests of the JavaScript checks need Node.js** (`tests/js`, parts of `tests/kernel`) and skip without it. The
  optional Z3 solver is not needed: `tests/linear` and `tests/constructor` use fake workers.
- **`tests/tools` needs markdown-it-py 3.0.0** (the CommonMark parser of `tools/scripts/symblic_docs_audit.py`):
  `pip install markdown-it-py==3.0.0` in a virtual environment. Without it the docs-audit tests error.
- **Two expected failures, on purpose:** `tests/mica/test_symblic_mica_strategies.py` marks two escalation tests
  with `@unittest.expectedFailure`. They also failed on the original code; the comments above them say what
  disagrees. Decide which behaviour is right before removing the markers.
- **Page journeys in `tests/browser/` are skipped** unless `SYMBLIC_BROWSER_HARNESS` names the host's Playwright
  harness, which is not part of this repository; the Academy's journeys need a harness that serves this repository
  instead ([`browser/README.md`](browser/README.md)). The Node-only page tests there run anywhere.

## Layout

| Folder | What it tests |
|---|---|
| `kernel/`, `providers/`, `adapters/`, `js/`, `lang/`, `spec/`, `english/`, `steps/`, `authoring/`, `delegate/`, `graph/`, `mica/`, `autogen/`, `linear/`, `constructor/`, `intent/`, `forge/`, `inquiry/`, `memory/`, `policy/`, `bench/`, `experiments/`, `distill/`, `portable/`, `os/` | The package of the same name under `symblic/` |
| `integration/` | Host-only code (`integration/host/`); runs against fakes or skips with a reason |
| `browser/` | The web pages (`web/`), with Node's test runner |
| `web/` | The Academy's catalog (`web/academy/symblic-academy-content.js`): lesson shape, document hashes, and its teaching examples run on the kernel |
| `kits/`, `examples/`, `tools/` | `kits/`, `examples/` and `tools/` |
| `misc/` | The host's automation canvas node (skipped) and the frame validator of the studio page |
| `fixtures/` | Recorded inputs shared by several test folders |

`symblic_frames_check.js` and `symblic_intent_page_check.js` are Node.js scripts that
`misc/test_symblic_frames_page.py` and `integration/test_symblic_intent_page.py` run.

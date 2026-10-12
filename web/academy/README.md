# academy: the Symblic Academy learning page

The Academy is the self-paced course on Symblic that the original host served at `/symblic-learn`. It is kept here
as static files: everything except two buttons (below) works in a browser without the host.

The page has 18 sections, grouped in its menu:

| Group | Sections |
|---|---|
| Course | Zero to Mastery: levels of short lessons ("bites"), each with a worked example, a checkpoint question, an exercise that applies it to a new case, and links to the documents it draws on |
| Theory | Architecture Map, Foundations, Deep Readings (chapters made from the later course levels, with comprehension questions), Research Map (every document in the catalog, the lessons that use it, and a reader for its text) |
| Syntax | Reference: statements and types |
| Practice | Flashcards (an SM-2-style scheduler with intervals in minutes), Cloze Blanks, Syntax Drills, Parsons Puzzles, Bug Hunt, Concept Quizzes |
| Tools | State Stepper, Speed Drill, Feynman Coach (a keyword rubric) |
| Build | Projects and Playground: Symblic programs to edit, check and preview |
| Analytics | Metacognition: review groups and an illustrative recall curve (not fitted to anyone's data) |

## Open it

Serve the repository root with any static file server and open `/web/academy/`:

    python3 -m http.server 8000        # from the repository root
    # then open http://localhost:8000/web/academy/

The research reader fetches the catalog's documents from `docs/`, `examples/`, `benchmarks/` and `kits/` (and six
from `symblic/` and `tests/`), so the server has to serve the whole repository. Serving only `web/` (as
[../README.md](../README.md) does for the hub) shows the page, but every document then reads "Source unavailable
(404)". Browsers refuse `fetch()` from pages opened as files, so opening `index.html` from disk shows the course but
not the documents.

## What works without the host, and what does not

| Part | Static files? | Notes |
|---|---|---|
| Course, theory, readings, flashcards, cloze, drills, puzzles, bug hunt, quizzes, stepper, speed drill, Feynman coach, metacognition | Yes | Progress (checkpoints, XP, the flashcard schedule, reading answers, your written explanations) stays in this browser's `localStorage`, under keys that start with `symblic_`. Nothing is sent anywhere. |
| Research Map and its reader | Yes, with the repository root served | The reader loads a document as a file (`../..` followed by its repository path) and shows it as plain text. Where the browser offers `crypto.subtle` (https or localhost), it hashes the bytes and says so when the document has changed since the catalog's `sha256` was recorded. |
| Check and Preview in Projects and Playground | **No: they need the host API** | They call `/api/automation/symblic/check` and `/preview` ([`integration/host/symblic_engine.py`](../../integration/host/symblic_engine.py)). Without a host the buttons say so and send nothing. From a checkout, `tools/symblic check FILE.sym` and `tools/symblic preview FILE.sym` do the same work locally, without a model. |
| Links to the studio page | Need a host | `../studio/symblic.html`; see [../README.md](../README.md). |

[`../hub/standalone-shell.js`](../hub/standalone-shell.js) stands in for the host's page library (`/studio.js`,
`/studio.css`): the menu (folded behind a "Pages" button on narrow screens), the short status messages and the
colours for light and dark. When the host's library is present the stand-in does nothing, and the two buttons call
the host API as they did on the host. `index.html` still asks for `/studio.css` and `/studio.js` first, as the hub
does, so a plain static server logs two harmless 404 responses.

## Files

| File | What it is |
|---|---|
| `index.html` | The page: the optional host library, the stand-in, the catalog and the script, in that order. |
| `symblic-learn.js` | Every section, the flashcard scheduler and the research reader. |
| `symblic-learn.css` | The page's styles. The shared colour names (`--bg1`, `--acc`, `--ok`, ...) come from the host's library or the stand-in. |
| `symblic-academy-content.js` | The catalog, `window.SymblicAcademyContent = {version, updated, levels, sources}`: the authored lessons, and one entry per document (title, repository path, headings, status, linked lessons, `sha256`, provenance). |

The catalog's `url` values are repository paths such as `/docs/reference/SPEC.md`; links to other sites stay
`https://` links. A link to a document under `docs/`, `examples/`, `benchmarks/` or `kits/` opens the reader
(`index.html?reading=PATH#research`); a link to another repository file opens the file itself.
[`tools/scripts/symblic_refresh_catalog.py`](../../tools/scripts/symblic_refresh_catalog.py) keeps the document
entries (titles, headings, hashes) in step with the files without rewriting the authored lessons:

    python3 tools/scripts/symblic_refresh_catalog.py --check   # read only; exits 1 when a refresh is needed
    python3 tools/scripts/symblic_refresh_catalog.py           # rewrite the document entries

Six rows also point at files under `symblic/bench/data/`, `symblic/authoring/grammar/` and `tests/kernel/fixtures/`;
after editing one of those, run the refresh too. After a document is moved or deleted, the script drops its row if
the script wrote the row and nobody has changed it; otherwise it stops and names the row, which then has to be
renamed or removed by hand, with the lesson links to it.

## Tests

| File | What it checks |
|---|---|
| [`tests/web/test_symblic_academy.py`](../../tests/web/test_symblic_academy.py) | The catalog: the shape of the levels and lessons, distinct questions and feedback, links that are `https://` or files of this repository, every document listed with the `sha256` of its bytes, lesson links that name real lessons, and the lessons' example programs run on the kernel without a model. |
| [`tests/tools/test_symblic_refresh_catalog.py`](../../tests/tools/test_symblic_refresh_catalog.py) | The refresh script, on temporary catalogs and read-only on this one. |
| [`tests/browser/symblic-academy.mjs`](../../tests/browser/symblic-academy.mjs) | The page in a browser. Its journeys need a browser harness that serves this repository and are skipped without one ([`tests/browser/README.md`](../../tests/browser/README.md)). |
| [`tests/integration/test_symblic_academy_sources.py`](../../tests/integration/test_symblic_academy_sources.py) | The host-only source route the page used on the original host. |

    DASH_TEST=1 python3 -m unittest discover -s tests/web -t .
    node --test tests/browser/symblic-academy.mjs

## Who wrote it, and how far to trust it

The course text, the questions and their explanations, and the catalog were written by AI agents in October 2026, on
the original host and in the publication pass, and no person has reviewed them. A lesson's links mark a teaching
connection, not a check of every claim in the linked document. Where a lesson disagrees with the language reference
or the code, the code wins. Checkpoints, XP, ranks, review groups and the Feynman keyword rubric record practice;
they do not measure learning.

Changed for publication on 2026-10-12: the catalog's links were rewritten to repository paths, and entries for
documents that are not in this repository were removed; links to the host's other pages (its terminal, its Forge page
and its reading feed) were removed, and the studio and hub links point into this repository; the reader loads files
instead of calling the host; Check and Preview say when there is no host; one flashcard was removed; the cloze
checker, which looked up the wrong element ids and so reported every answer as correct, now checks the blanks; wrong
answers got dark-theme colours, the program editors got labels, and a few small texts got more contrast; the syntax
drills and the Parsons puzzles no longer overflow a phone screen; an unsourced claim on the Bug Hunt page was removed,
and the answers on flashcards and in the Bug Hunt are labelled "Answer" and "Fix" instead of "Verified", since
no person has checked them; one exercise prompt was made more general.

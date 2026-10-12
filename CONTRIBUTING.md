# Contributing

**Symblic is looking for maintainers.** It was built in about ten days by AI agents for one person, who is
publishing it so that the community can take it further. If you want to adopt it, fork it, split it up or keep only
one idea from it, please do; no permission is needed beyond the [license](LICENSE). If you would like to become a
maintainer of this repository, open an issue saying so.

## Before you start

- Read [docs/MADE-WITH-AI.md](docs/MADE-WITH-AI.md) and [docs/HONEST-ASSESSMENT.md](docs/HONEST-ASSESSMENT.md).
  Nothing here has had a human code review. The most useful early contributions are reviews, reproductions and bug
  reports, especially ones that show a test passing when it should not.
- Where a document and the code disagree, the code is right and the document is a bug.
- [docs/MAP.md](docs/MAP.md) translates the old file names that older documents and records still use.

## Working on the code

- Python 3.12, standard library only for the interpreter. Node.js (tested with 22.17) and Linux 6.7 or newer are
  needed for the JavaScript checks.
- Run the tests of the package you change, from the repository root:
  `DASH_TEST=1 python3 -m unittest discover -s tests/<package> -t .`
  (`DASH_TEST=1` tells the code it is under test: no systemd scopes, no real kernel builds, no live model
  inventory; [tests/README.md](tests/README.md) covers the whole suite, its run time and its skips.)
  Tests must not call a real model, use the network or touch files outside a temporary folder; use the fakes in
  `symblic/providers`.
- Keep the rule the project is built on: a model's answer counts only when code has checked it. A change that lets an
  unchecked answer through is a bug, even if the result looks right.
- Every module has a docstring saying what it is for, what it depends on and what runs it, and every package has a
  README. Please keep them true when you change the code.
- The Academy's catalog (`web/academy/symblic-academy-content.js`) records a hash of every document under `docs/`,
  `examples/`, `benchmarks/` and `kits/`. After adding, moving, deleting or editing one, run
  `python3 tools/scripts/symblic_refresh_catalog.py`; `tests/web` fails until the catalog matches the files. Six
  rows also point at files under `symblic/bench/data/`, `symblic/authoring/grammar/` and `tests/kernel/fixtures/`;
  after editing one of those, run the refresh too. The script drops the row of a moved or deleted document only
  when it wrote the row and nobody has changed it; otherwise it stops and names the row, which you then rename or
  remove by hand, together with the lesson links to it.
- Code in `integration/host/` belonged to the private system Symblic was built in and does not run here. Porting a
  piece of it to something that runs anywhere is a welcome contribution.

## Reporting results

If you measure anything (a model, a sheet, a kit), add the record with its failures, settings and versions, and say
what it does not show. The existing records in [docs/reference/](docs/reference/README.md) and
[kits/](kits/README.md) show the format.

AI-assisted contributions are welcome, provided you have read and run what you submit.

#!/usr/bin/env python3
"""The build loop for a kit: compile a spec sheet, run it against Ollama, keep what passed, and go again.

    python3 kits/build_loop.py SHEET.md --dir NEW_RUN_FOLDER --by ollama:MODEL [--by ollama:MODEL ...]
        [--samples 2] [--retries 3] [--rounds 2] [--keep EARLIER_RUN_FOLDER [--redo NAME ...]]
        [--num-predict 2048] [--call-timeout 600] [--max-calls 2000]
    python3 kits/build_loop.py --resume RUN_FOLDER          continue a stopped run (recorded calls are reused)

One round:

1. compile the sheet with symblic.spec.sheets (deterministic; no model is called), keeping the leading units an
   earlier run accepted when --keep names it (they are tested again, never asked again);
2. write the program and its options into the new run folder (program.sym, meta.json);
3. run it with the kernel's runner (symblic.kernel.run.run_folder) and this repository's applicators
   (symblic.providers.applicators: `ollama:MODEL` or `ollama:MODEL@HOST`, servers listed in SYMBLIC_OLLAMA_HOSTS,
   default 127.0.0.1:11434). Every model call, the trace and the final state stay in the folder.

After a round: grade the page with the kit's build/grade.sh. If a unit stalled, ask the sheet why
(`python3 -m symblic.spec.sheets diagnose SHEET.md --run RUN_FOLDER`), reword it, refill its examples with the
kit's reference, and start the next round with --keep pointing at the best run so far.

--num-predict and --call-timeout cap every local call (Ollama's num_predict, and seconds per call), so a model that
loops cannot hold a machine for long. Each round asks the models named by --by; nothing else is contacted.

Depends on: symblic.spec.sheets, symblic.kernel.run (and through it symblic.providers.applicators).
Tested with a fake model in tests/kits/test_build_loop.py; the kits' dry runs (build/dryrun.py) use the reference
as the model instead.
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # the repository root
sys.path.insert(0, str(REPO))
from symblic.spec import sheets as SP  # noqa: E402
from symblic.kernel import run as R  # noqa: E402


def prepare_run(sheet_text, by, folder, *, samples=2, retries=3, rounds=2, keep=None, redo=(),
                num_predict=2048, call_timeout=600, max_calls=2000):
    """Compile the sheet and write program.sym and meta.json into a new, empty run folder. No model is called."""
    folder = Path(folder)
    if folder.exists() and any(folder.iterdir()):
        raise SystemExit(f'{folder} is not empty: give a new run folder (or --resume it)')
    kept = SP.accepted_units(str(keep)) if keep else None
    source = SP.compile_sheet(sheet_text, list(by), samples=samples, retries=retries, rounds=rounds, keep=kept,
                              keep_from=('run ' + Path(keep).name) if keep else '', redo=redo)
    options = {'max_calls': int(max_calls),
               'ollama_limits': {'num_predict': int(num_predict), 'timeout_seconds': int(call_timeout)}}
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    (folder / 'program.sym').write_text(source, encoding='utf-8')
    (folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': options, 'by_label': 'kit build loop'}),
                                      encoding='utf-8')
    return source


def run_build(sheet_text, by, folder, *, applicators=None, **settings):
    """prepare_run, then run the folder; returns the kernel's report (status, calls, outputs, error)."""
    prepare_run(sheet_text, by, folder, **settings)
    return R.run_folder(str(folder), applicators=applicators)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Compile a spec sheet and run the build against Ollama.')
    ap.add_argument('sheet', nargs='?', help='the spec sheet (SHEET.md)')
    ap.add_argument('--dir', help='a new, empty run folder')
    ap.add_argument('--by', action='append', default=[], help='an applicator, e.g. ollama:qwen3:4b-instruct (repeat)')
    ap.add_argument('--samples', type=int, default=2, help='candidates asked at once per round (default 2)')
    ap.add_argument('--retries', type=int, default=3, help='repairs per candidate (default 3)')
    ap.add_argument('--rounds', type=int, default=2, help='fresh rounds when no candidate passes (default 2)')
    ap.add_argument('--keep', help='an earlier run folder whose accepted leading units are kept')
    ap.add_argument('--redo', action='append', default=[], help='stop keeping at the unit that defines NAME')
    ap.add_argument('--num-predict', type=int, default=2048, help='output tokens per local call (default 2048)')
    ap.add_argument('--call-timeout', type=int, default=600, help='seconds per local call (default 600)')
    ap.add_argument('--max-calls', type=int, default=2000, help='model calls for the whole build (default 2000)')
    ap.add_argument('--resume', metavar='RUN_FOLDER', help='continue a stopped run instead of starting one')
    a = ap.parse_args(argv)
    if a.resume:
        report = R.run_folder(a.resume, resume=True)
    else:
        if not (a.sheet and a.dir and a.by):
            ap.error('give SHEET.md, --dir and at least one --by (or --resume RUN_FOLDER)')
        with open(a.sheet, encoding='utf-8') as fh:
            text = fh.read()
        report = run_build(text, a.by, a.dir, samples=a.samples, retries=a.retries, rounds=a.rounds, keep=a.keep,
                           redo=a.redo, num_predict=a.num_predict, call_timeout=a.call_timeout,
                           max_calls=a.max_calls)
    folder = a.resume or a.dir
    print(f"status {report.get('status')}, {report.get('calls')} model calls"
          + (f": {(report.get('error') or {}).get('message', '')[:300]}" if report.get('error') else ''))
    print(f'records: {os.path.abspath(folder)}  (grade with the kit\'s build/grade.sh; diagnose with '
          f'python3 -m symblic.spec.sheets diagnose SHEET.md --run {folder})')
    return 0 if report.get('status') == 'done' else 1


if __name__ == '__main__':
    sys.exit(main())

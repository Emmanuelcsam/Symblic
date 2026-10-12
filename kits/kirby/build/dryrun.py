#!/usr/bin/env python3
"""Dry run of a compiled Kirby build in the real kernel, with no model.

A stand-in applicator answers every unit with the reference code for the names it declares (fenced, the way a
model would answer), so the sheet compiler (symblic.spec.sheets), the answer normalizer (symblic.js.normalize),
js_test (the sandboxed JavaScript checker, symblic.js.check), the `ensure ... else retry` statements and the
assembly all run exactly as in a real build. Nothing is sent to any model or network.

    python3 kits/kirby/build/dryrun.py [--sheet SHEET.md] [--dir NEW_RUN_FOLDER] OUT.html

--sheet    the sheet to dry-run (default kits/kirby/sheets/kirby.sheet.md; the 3B and 1B variants are its siblings)
--dir      keep the run folder (program.sym, meta.json, calls.jsonl, trace.jsonl, state.json, ...) so
           build/grade.sh can grade it as it would grade a real build, and `tools/symblic replay` and the sheet
           `diagnose` command can read it; without it the run is in memory only
OUT.html   the assembled page this script WRITES. It must be outside the repository; the script refuses a path
           inside it (an earlier version took the sheet path by mistake and overwrote the sheet).

Prints the run status and writes the assembled kirby.html, which must be byte-identical to what
kits/kirby/reference/assemble-ref.mjs writes. Needs Python 3.12 and Node.js 22 (for the JavaScript sandbox).
"""
import argparse
import json
import os
import re
import sys
import time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # kits/kirby
REPO = os.path.abspath(os.path.join(KIT, '..', '..'))                        # the repository root
sys.path.insert(0, REPO)
from symblic.spec import sheets as SP  # noqa: E402
from symblic.kernel.run import Run  # noqa: E402

DEFAULT_SHEET = os.path.join(KIT, 'sheets', 'kirby.sheet.md')


def declarations(src):
    """Top-level `export function NAME` / `export const NAME` blocks of ref-units.mjs, by name."""
    out, name, cur = {}, None, []
    for line in src.split('\n'):
        m = re.match(r'^export (?:function\s+([A-Za-z_$][\w$]*)|const\s+([A-Za-z_$][\w$]*))', line)
        if m:
            if name:
                out[name] = '\n'.join(cur).rstrip()
            name, cur = m.group(1) or m.group(2), [line[len('export '):]]
        elif name:
            if line.startswith('//'):
                out[name] = '\n'.join(cur).rstrip()
                name, cur = None, []
            else:
                cur.append(line)
    if name:
        out[name] = '\n'.join(cur).rstrip()
    return out


def main(out_path, sheet_path=DEFAULT_SHEET, folder=None):
    with open(os.path.join(KIT, 'reference', 'ref-units.mjs'), encoding='utf-8') as fh:
        decls = declarations(fh.read())
    with open(sheet_path, encoding='utf-8') as fh:
        text = fh.read()
    sheet = SP.parse(text)
    answers = {u['heading']: '\n\n'.join(decls[n] for n in u['names']) for u in sheet['units']}
    asked = []

    class Stand:
        def call(self, req):
            heading = re.search(r'YOUR UNIT: `([^`]+)`', req['prompt']).group(1)
            asked.append(heading)
            return {'ok': True, 'text': 'Here is the unit.\n```js\n' + answers[heading] + '\n```', 'json': None,
                    'model': 'reference', 'node': 'none', 'ms': 1}

    source = SP.compile_sheet(text, ['fake:reference'], samples=1, retries=0, rounds=1)
    given = sum(1 for u in sheet['units'] if u.get('given'))
    if folder:
        # program.sym and meta.json make the folder a complete run record, like one from kits/build_loop.py:
        # `tools/symblic replay FOLDER` and `python3 -m symblic.spec.sheets diagnose SHEET --run FOLDER` read them.
        os.makedirs(folder, mode=0o700, exist_ok=True)
        with open(os.path.join(folder, 'program.sym'), 'w', encoding='utf-8') as fh:
            fh.write(source)
        with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fh:
            json.dump({'inputs': {}, 'options': {'parallel': 1}, 'by_label': 'dry run (reference answers)'}, fh)
    t0 = time.time()
    report = Run(source, applicators=Stand(), options={'parallel': 1}, folder=folder).execute()
    print('status', report['status'], (report.get('error') or {}).get('message', '')[:800])
    print(f'{len(asked)} of {len(sheet["units"])} units asked and accepted ({given} given by the sheet) '
          f'in {time.time() - t0:.1f} s')
    out = next((o for o in report.get('outputs') or [] if o.get('label') == 'kirby.html'), None)
    if out is None:
        return 1
    html = out['value'] if isinstance(out.get('value'), str) else out.get('text')
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(html)
    print('wrote', out_path, len(html), 'characters')
    return 0 if report['status'] == 'done' and len(asked) + given == len(sheet['units']) else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Dry-run a Kirby sheet build with the reference as the answers.')
    ap.add_argument('out', help='the page to WRITE (OUT.html), outside the repository')
    ap.add_argument('--sheet', default=DEFAULT_SHEET, help='the sheet to dry-run (default: sheets/kirby.sheet.md)')
    ap.add_argument('--dir', help='a new, empty run folder to keep (for build/grade.sh)')
    args = ap.parse_args()
    if not args.out.endswith('.html'):
        sys.exit('usage: dryrun.py [--sheet SHEET.md] [--dir FOLDER] OUT.html  (OUT.html is the page to WRITE)')
    for path in [args.out] + ([args.dir] if args.dir else []):
        if os.path.realpath(path).startswith(os.path.realpath(REPO) + os.sep):
            sys.exit(f'refusing to write inside the repository ({path}): give a path outside it')
    if args.dir and os.path.exists(args.dir) and os.listdir(args.dir):
        sys.exit(f'--dir must be a new or empty folder: {args.dir}')
    sys.exit(main(args.out, args.sheet, args.dir))

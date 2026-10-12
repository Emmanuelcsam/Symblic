"""The `english` command: check, compile, preview, run or resume a document of English statements.

Usage (from the repository root; `tools/symblic english ...` dispatches here too):

    python3 -m symblic.english.cli check FILE.english.txt          compile and check; no model is called
    python3 -m symblic.english.cli compile FILE.english.txt        print the generated Symblic program
    python3 -m symblic.english.cli preview FILE.english.txt        the program up to its first model request, and
                                                                    exactly what that request would send
    python3 -m symblic.english.cli run FILE.english.txt --dir NEW_EMPTY_FOLDER [--by ollama:qwen3:4b-instruct]
    python3 -m symblic.english.cli resume FOLDER                   continue a saved run (its records are reused)
    python3 -m symblic.english.cli examples                        the built-in example documents, as JSON

`run` asks a model (the --by applicator; see symblic.providers.applicators for `ollama:MODEL[@HOST]` and
`command:NAME`), one fresh request per English `Ask for` statement, and the kernel checks every answer against the
document's `Accept only if` lines. The folder keeps the document (instructions.english), the generated program,
every call and the results, so the run can be inspected and replayed.

`preview` runs in the kernel's bounded child process (symblic.kernel.process_limits); where that child is not
available it reports "unavailable" instead of a preview.
Depends on: symblic.english.authoring (compile + authoring record), symblic.kernel (language, run,
execution_pins, process_limits) and symblic.authoring.helpers (bounded file reads).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path

from symblic.kernel import language as S
from symblic.english import authoring as A


def run_compiled(compiled, folder, by, *, applicators=None):
    from symblic.kernel import execution_pins as X
    from symblic.kernel import run as R
    folder = Path(folder)
    if folder.exists() and (folder.is_symlink() or not folder.is_dir() or any(folder.iterdir())):
        raise ValueError('Choose a new empty run directory. Use english resume for a saved run.')
    by = S.parse_applicator(by)['spec']
    options = {**compiled['options'], 'by': by}
    hashes = {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest() for name in X.REQUIRED_FILES}
    options['execution_pins'] = X.build(compiled['source'], compiled['inputs'], hashes)
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    meta = {'title': 'English statements', 'inputs': compiled['inputs'], 'options': options,
            'by': by, 'by_label': 'operator (Symblic English CLI)', 'authoring': compiled['authoring']}
    # Exclusive writes preserve any concurrent creator's records. Nothing launches before every input exists.
    for name, text in [('program.sym', compiled['source']),
                       ('instructions.english', compiled['authoring']['document']),
                       ('meta.json', json.dumps(meta, ensure_ascii=False))]:
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return R.run_folder(str(folder), applicators=applicators)


def resume(folder, *, applicators=None):
    from symblic.kernel import run as R
    folder = Path(folder)
    from symblic.authoring.helpers import _pairs, _read
    # Run metadata includes finite provider temperatures and voting weights.
    # The authoring-editor loader intentionally forbids floats and is not this format.
    def reject_constant(_value):
        raise ValueError('Run metadata contains a nonfinite JSON number.')
    meta = json.loads(_read(folder / 'meta.json').decode('utf-8'),
                      object_pairs_hook=_pairs, parse_constant=reject_constant)
    if type(meta) is not dict:
        raise ValueError('Run metadata must be an object.')
    source = _read(folder / 'program.sym').decode('utf-8')
    if meta.get('authoring') is None:
        raise ValueError('This is not a saved English run.')
    A.validate_saved(folder, source, meta)
    return R.run_folder(str(folder), resume=True, applicators=applicators)


def preview(compiled, by):
    """The kernel's bounded preview (a separate, resource-limited process): bindings up to the first ask, and
    exactly what would be sent for it. No model is called."""
    from symblic.kernel import process_limits as P
    body = {'source': compiled['source'], 'inputs': compiled['inputs'], 'by': S.parse_applicator(by)['spec']}
    if type(compiled.get('options', {}).get('determine')) is bool:
        # the run will not let the kernel answer an ask itself, so neither may the preview
        body['options'] = {'determine': compiled['options']['determine']}
    return P.call_bounded('preview', body)


def main(argv=None):
    p = argparse.ArgumentParser(prog='symblic english', description='English instructions, one fresh checked model task at a time.')
    p.add_argument('command', choices=('check', 'compile', 'preview', 'run', 'resume', 'examples'))
    p.add_argument('path', nargs='?')
    p.add_argument('--by', default='ollama:qwen3:4b-instruct')
    p.add_argument('--dir', help='New empty directory retaining instructions, results and replay records')
    p.add_argument('--max-calls', type=int, default=64)
    p.add_argument('--retries', type=int, default=2)
    p.add_argument('--budget', type=int, default=12000)
    p.add_argument('--agent-json', '--json', action='store_true', dest='json')
    args = p.parse_args(argv)
    try:
        if args.command == 'examples':
            result = {'examples': A.examples()}
        elif args.command == 'resume':
            if not args.path:
                raise ValueError('Provide the saved run directory.')
            with contextlib.redirect_stdout(sys.stderr):
                result = resume(args.path)
        else:
            if not args.path:
                raise ValueError('Provide the English instruction file.')
            from symblic.authoring.helpers import _read
            compiled = A.prepare({'source': _read(args.path).decode('utf-8'), 'retries': args.retries,
                                  'max_calls': args.max_calls, 'budget': args.budget})
            if args.command == 'run':
                if not args.dir:
                    raise ValueError('Use --dir to retain the run for inspection and replay.')
                with contextlib.redirect_stdout(sys.stderr):
                    result = run_compiled(compiled, args.dir, args.by)
            elif args.command == 'preview':
                result = preview(compiled, args.by)
            elif args.command == 'compile' and not args.json:
                print(compiled['source'], end='')
                return 0
            else:
                result = {'ok': True, **compiled}
        if args.json or args.command == 'examples':
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f'{result.get("status", "checked")} · {result.get("calls", 0)} model calls')
            for row in result.get('outputs', []):
                print(row.get('text', ''))
        return 1 if result.get('status') == 'failed' else 0
    except (OSError, ValueError, S.SymblicError) as error:
        detail = error.as_dict() if isinstance(error, S.SymblicError) else {
            'message': str(error), 'line': getattr(error, 'line', 0), 'kind': getattr(error, 'code', 'english')}
        print(json.dumps({'ok': False, 'error': detail}) if args.json else detail['message'],
              file=sys.stdout if args.json else sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

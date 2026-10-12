"""Spec sheets: compile a strict Markdown specification into a Symblic build program, deterministically.

What it is for: building one file (a game page, a library) with small local models, one small unit of code at a
time. A spec sheet describes the file as units, each with a contract in prose and examples; this module turns the
sheet into a Symblic program in which a model writes each unit in a fresh context and the kernel accepts a unit only
when it gives every example's value. No model writes the program itself. The kits in kits/kirby and kits/tetris
are complete worked examples.

A spec sheet is Markdown that describes one output file as small units of code, each with a contract and examples:

    # tetris.html                         the output file (the first heading)
    (intro: what the file is)
    ## Shared                             what every unit sees: conventions, the shared data model
    Used units shown as: signatures      (optional, before the units) prompts name the units a unit may call
                                          instead of pasting their code; for 0.5B-1B workers, which copy code
    Answers normalized: yes               (optional, before the units) every unit is asked as `Code js unit NAMES
                                          reusing EARLIER`: the kernel takes the fenced block that declares the unit,
                                          restores a dropped `function` and cuts the worker's copies of earlier units
                                          before testing and assembling (symblic.js.normalize); for 0.5B-1B workers
    ## Unit `cellsOf(type, rot)`          one unit: the names it defines, then its contract in prose
    Uses: `SHAPES`                        names other units define that this one may call
    Given: yes                            (optional) the unit's fenced ```js block IS its code: tested, never asked
    Test setup:                           (optional, indented) helpers the examples use; never part of the answer
        function blank() { ... }
    Examples:                             (indented) `call ==> expected JSON`, all of which must hold
        cellsOf('T', 1) ==> [[1,2],[0,1],[1,1],[2,1]]
    ## Assemble `tetris.html`             (indented) the file around the code, with /*UNITS*/ where it goes

The compiled program asks for every unit in its own fresh context (`context=none`): the unit's contract, the
contracts of the units it uses, its examples and the shared section, nothing else. It tests each answer with the
kernel's sandboxed JavaScript (`js_test`) against the examples, after the code of every earlier unit (so a name
declared twice fails at once and the last unit's test covers the whole file), and retries with the failing examples
as feedback (`ensure ... else retry because`). `route=search` lets several local models try at once; the passing
candidate with the fewest attempts (then the lowest index) is accepted. The file is assembled by the kernel from
passing units only, in sheet order. What a passing build establishes: every unit gives every example's value. It
does not establish anything the examples do not test; a kit's harness tests the whole file.

`diagnose` reads one build's run folder and tests every model reply again, grouping the failures by the first example
each reply fails: many replies, from different models, failing one example the same way usually point at the
sheet's wording rather than at the models. `compile --keep RUN` makes an incremental rebuild that keeps the units an
earlier build accepted (still tested, never asked again).

Command line (no model is called by any of these):

    python3 -m symblic.spec.sheets check SHEET.md
    python3 -m symblic.spec.sheets compile SHEET.md --by ollama:MODEL [--by ...] [--samples N] [--retries N]
                                         [--rounds N] [--keep RUN_FOLDER [--redo NAME]] > BUILD.sym
    python3 -m symblic.spec.sheets diagnose SHEET.md --run RUN_FOLDER [--unit NAME] [--all] [--json]

Run the compiled program with the kernel's runner (`tools/symblic run BUILD.sym --dir RUN_FOLDER`).
Depends on: symblic.kernel.language (parsing a run's program), symblic.js.check and symblic.js.normalize (diagnose).
Used by: symblic.spec.build, symblic.spec.compare, symblic.spec.contracts (the parsed shape), symblic.english.pixels.
This is the "legacy" build compiler the kits use; symblic.spec.build is the newer task-card compiler for the same
sheets (see symblic/spec/README.md for the difference).
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import re
import sys

VERSION = 1
PLACEHOLDER = '/*UNITS*/'
_NAME = re.compile(r'[A-Za-z_$][\w$]*')


class SheetError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------------- parsing

def parse(text: str) -> dict:
    """{'title', 'intro', 'shared', 'units': [{'names', 'heading', 'body', 'uses', 'setup', 'examples'}],
    'template': {'file', 'text', 'note'} | None}"""
    # the two directive keys appear only when a sheet states them: a plain sheet parses to the historical shape
    out = {'title': '', 'intro': [], 'shared': [], 'units': [], 'template': None}
    section, current = 'intro', None
    for n, line in enumerate(str(text).replace('\r\n', '\n').split('\n'), 1):
        m = re.match(r'^# (.+?)\s*$', line)
        if m and not out['title']:
            out['title'] = m.group(1).strip()
            continue
        m = re.match(r'^Answers normalized:\s*(yes|no)\s*$', line)
        if m and section in ('intro', 'shared'):
            # yes: every unit is asked as `Code js unit NAMES reusing EARLIER`, so the kernel takes the fenced block
            # that declares the unit, restores a dropped `function` and cuts the model's copies of earlier units'
            # names before testing and assembling (2026-10-10: that is where 0.5B-1B workers failed, not on logic)
            out['normalize'] = m.group(1) == 'yes'
            continue
        m = re.match(r'^Used units shown as:\s*(code|signatures)\s*$', line)
        if m and section in ('intro', 'shared'):
            # signatures: a unit's prompt names the units it may call instead of pasting their tested code. A 1B
            # model shown that code copies it instead of writing its own unit (2026-10-10, gemma3:1b: `strongEm`
            # answered with a second `strong`); it needs to know only that the names exist.
            out['uses_shown'] = m.group(1)
            continue
        m = re.match(r'^## (Shared|Unit `([^`]+)`|Assemble `([^`]+)`)\s*$', line)
        if m:
            if m.group(1) == 'Shared':
                section, current = 'shared', None
            elif m.group(2):
                heading = m.group(2).strip()
                names = []
                for part in re.split(r',\s*(?![^()]*\))', heading):
                    found = _NAME.match(part.strip())
                    if not found:
                        raise SheetError(f'line {n}: a unit heading names what it defines: {heading!r}')
                    names.append(found.group(0))
                current = {'names': names, 'heading': heading, 'line': n, 'lines': []}
                out['units'].append(current)
                section = 'unit'
            else:
                current = {'file': m.group(3).strip(), 'line': n, 'lines': []}
                out['template'] = current
                section = 'assemble'
            continue
        if line.startswith('## '):
            raise SheetError(f'line {n}: unknown section {line[3:].strip()!r} (Shared, Unit `...`, Assemble `...`)')
        if section in ('intro', 'shared'):
            out[section].append(line)
        else:
            current['lines'].append(line)
    for unit in out['units']:
        unit.update(_split_unit(unit.pop('lines')))
    if out['template'] is not None:
        t = out['template']
        lines = t.pop('lines')
        t['text'] = _indented(lines)
        t['note'] = '\n'.join(l for l in lines if l.strip() and not l.startswith('    ')).strip()
    out['intro'] = '\n'.join(out['intro']).strip()
    out['shared'] = '\n'.join(out['shared']).strip()
    return out


def _indented(lines) -> str:
    block = [l[4:] if l.startswith('    ') else '' for l in lines if l.startswith('    ') or not l.strip()]
    while block and not block[0].strip():
        block.pop(0)
    while block and not block[-1].strip():
        block.pop()
    return '\n'.join(block)


def _split_unit(lines) -> dict:
    body, setup, examples, uses, mode = [], [], [], [], 'body'
    for line in lines:
        s = line.strip()
        if s.startswith('Uses:'):
            uses += re.findall(r'`([^`]+)`', s)
            continue
        if s == 'Test setup:':
            mode = 'setup'
            continue
        if s == 'Examples:':
            mode = 'examples'
            continue
        if mode == 'setup':
            if line.startswith('    ') or not s:
                setup.append(line[4:] if line.startswith('    ') else '')
                continue
            mode = 'body'
        if mode == 'examples':
            if line.startswith('    ') and '==>' in line:
                call, _, expect = line[4:].rpartition('==>')
                examples.append([call.strip(), expect.strip()])
                continue
            if not s:
                continue
            mode = 'body'
        body.append(line)
    text = '\n'.join(body).strip()
    given = any(re.fullmatch(r'Given:\s*yes', ln.strip(), re.I) for ln in body)
    fence = re.search(r'(?ms)^```(?:js|javascript)?[ \t]*\n(.*?)^```[ \t]*$', text)
    return {'body': text, 'setup': '\n'.join(setup).strip(), 'examples': examples, 'uses': uses,
            'given': given, 'code': fence.group(1).strip() if fence else ''}


def problems(sheet: dict) -> list[str]:
    """What makes a sheet uncompilable (empty when it compiles)."""
    out = []
    if not sheet['title']:
        out.append('the sheet has no title (# file name)')
    if not sheet['units']:
        out.append('the sheet has no units (## Unit `name(...)`)')
    defined: dict = {}
    for unit in sheet['units']:
        for name in unit['names']:
            if name in defined:
                out.append(f'{name} is defined by two units ({defined[name]} and {unit["heading"]})')
            defined[name] = unit['heading']
        if not unit['examples']:
            out.append(f'unit {unit["heading"]} has no examples: nothing could check it')
        if unit.get('given') and not unit.get('code'):
            out.append(f'unit {unit["heading"]} says Given: yes but has no fenced ```js block to take as its code')
        for call, expect in unit['examples']:
            try:
                json.loads(expect)
            except ValueError:
                out.append(f'unit {unit["heading"]}: the expected value of `{call}` is not JSON: {expect[:80]}')
    order = {name: i for i, unit in enumerate(sheet['units']) for name in unit['names']}
    for i, unit in enumerate(sheet['units']):
        for used in unit['uses']:
            base = _NAME.match(used)
            if base and base.group(0) in order and order[base.group(0)] >= i:
                out.append(f'unit {unit["heading"]} uses {used}, which a later unit defines (put it first)')
    t = sheet['template']
    if t is None:
        out.append('the sheet has no Assemble section')
    elif PLACEHOLDER not in t['text']:
        out.append(f'the Assemble section has no {PLACEHOLDER} where the code goes')
    if sheet.get('normalize'):
        # the kernel's `Code js unit NAME reusing ...` syntax takes plain identifiers; `$` and non-ASCII names do
        # not parse there and would make every answer empty
        for unit in sheet['units']:
            bad = [n for n in unit['names'] if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', n)]
            if bad:
                out.append(f'Answers normalized: yes needs plain identifier names (letters, digits, _): {", ".join(bad)}')
    return out


# ------------------------------------------------------------------------------------------------------ compiling

def literal(text: str) -> str:
    """A Symblic string literal that reads back as exactly `text` (escapes processed, braces not interpolated)."""
    s = str(text).replace('\\', '\\\\').replace('{', '{{').replace('}', '}}')
    if '"""' in s or s.endswith('"') or s.startswith('"'):
        s = s.replace('"', '\\"')
    return '"""' + s + '"""'


def _var(name: str) -> str:
    return 'unit_' + re.sub(r'\W', '_', name)


def _contract(unit: dict) -> str:
    first = ' '.join(unit['body'].split('\n\n')[0].split())
    return first if len(first) <= 600 else first[:560].rsplit(' ', 1)[0] + ' …'


def _direct(sheet: dict, i: int) -> list[int]:
    """The units this unit names under Uses, in sheet order."""
    owner = {name: j for j, unit in enumerate(sheet['units']) for name in unit['names']}
    found = {owner[m.group(0)] for used in sheet['units'][i]['uses'] for m in [_NAME.match(used)]
             if m and m.group(0) in owner and owner[m.group(0)] != i}
    return sorted(found)


def unit_prompt(sheet: dict, i: int) -> list:
    """The unit's instruction as parts: ('text', s) is shown as written, ('name', v) interpolates a binding (the shared
    section, and the tested code of the units this one uses, so a model never guesses what they hold)."""
    unit = sheet['units'][i]
    parts = [('name', 'sheet_shared'), ('text', f'\n\n---\nYOUR UNIT: `{unit["heading"]}`\n\n{unit["body"]}\n\n')]
    used = _direct(sheet, i)
    if used and sheet.get('uses_shown') == 'signatures':
        heads = ', '.join('`' + sheet['units'][j]['heading'] + '`' for j in used)
        # no prohibition here: told "your answer must not contain them", gemma3:1b answered `return s` sixteen
        # times (2026-10-10); the kernel still rejects a copy, because a name declared twice fails to run
        parts.append(('text', f'The functions {heads} already exist and work; call them.\n\n'))
    elif used:
        taken = ', '.join(n for j in used for n in sheet['units'][j]['names'])
        # name what must not be copied: 4B models pasted SHAPES/cellsOf/fits into their answers (2026-10-04)
        parts.append(('text', 'Already in the file before your code, written and tested. Call these as they are; '
                              f'your answer must not contain {taken} again (no copies of this code).\n'))
        for j in used:
            dep = sheet['units'][j]
            parts.append(('text', f'\n// {dep["heading"]}: {_contract(dep)}\n```js\n'))
            parts.append(('name', _var(dep['names'][0])))
            parts.append(('text', '\n```\n'))
        parts.append(('text', '\n'))
    text = ('The kernel tests your code with these examples. Each call runs after your code (and after the code '
            'above) and must give exactly the value after ==>:\n')
    text += ''.join(f'    {call} ==> {expect}\n' for call, expect in unit['examples'])
    if unit['setup']:
        text += '\nThe tests define these helpers before your code; they are not part of your answer:\n'
        text += ''.join(f'    {line}\n' for line in unit['setup'].split('\n'))
    # never the word "define": phi4-mini answered `define("drawBoard", function ...)` after reading "define()"
    text += (f'\nWrite only this unit\'s code: plain top-level `function` or `const` declarations named '
             f'{", ".join(unit["names"])}, and nothing else (no wrapper, module, export or copy of the code above).')
    parts.append(('text', text))
    return parts


def prompt_text(sheet: dict, i: int, values: dict) -> str:
    """unit_prompt with its interpolations filled from `values` (for previews and tests)."""
    return ''.join(v if k == 'text' else str(values.get(v, '')) for k, v in unit_prompt(sheet, i))


def literal_parts(parts: list) -> str:
    """A Symblic string literal: text parts read back exactly, name parts are interpolations {name}."""
    body = ''.join(literal(v)[3:-3] if k == 'text' else '{' + v + '}' for k, v in parts)
    if body.endswith('"') and not body.endswith('\\"'):
        body = body[:-1] + '\\"'
    return '"""' + body + '"""'


def compile_sheet(text: str, applicators: list[str], *, samples: int | None = None, retries: int = 3,
                  rounds: int = 3, keep: dict | None = None, keep_from: str = '', redo=()) -> str:
    """The Symblic program that builds the sheet's file from its units with the given applicators.

    `keep` ({unit_X: code}, as `accepted_units` reads it from an earlier build) makes an incremental rebuild: the
    longest run of leading units found there, up to the first named in `redo`, becomes fixed text in the program.
    Those units are still tested against the sheet's examples (`assert`, so a kept unit that no longer passes stops
    the build), but no model is asked again, so editing a later unit never re-asks or changes them. Later units see
    their code exactly as before. `keep_from` says where the code came from, in the program's notes.

    A unit whose contract holds the line `Given: yes` (2026-10-11) is data the sheet supplies, not work for a model:
    its fenced ```js block becomes the unit's text, tested against its examples like a kept unit, and no model is
    asked for it. The Kirby level map is such a unit: 12 rows of 64 characters that 1B models cannot copy."""
    sheet = parse(text)
    found = problems(sheet)
    if found:
        raise SheetError('; '.join(found))
    if not applicators:
        raise SheetError('name at least one applicator (for example "ollama:qwen3:4b-instruct")')
    units = sheet['units']
    shared = (sheet['intro'] + '\n\n' + sheet['shared']).strip()
    title = sheet['title']
    keep, redo = dict(keep or {}), set(redo or ())
    given = {_var(u['names'][0]): u['code'] for u in units if u.get('given')}
    # an exact-code unit ("Write exactly this code:" plus a fenced block) gets, as its retry reason, the lines where
    # the answer departs from the given code (diff_lines), after the failing examples: a 0.5B model restructured a
    # guard it was told to copy four times when it only saw failing examples (2026-10-11)
    exact = {_var(u['names'][0]): u['code'] for u in units
             if u.get('code') and not u.get('given') and re.search(r'write exactly', u['body'], re.I)}
    kept = 0
    for unit in units:
        var = _var(unit['names'][0])
        if (var not in keep and var not in given) or redo & set(unit['names']):
            break
        kept += 1
    out = [f'program Build {title}.',
           f'note Compiled from the spec sheet "{title}" ({len(units)} units) by symblic.spec.sheets {VERSION}: deterministic, '
           f'no model wrote this program. Each unit is written in a fresh context, tested against the sheet\'s '
           f'examples by the kernel\'s sandboxed JavaScript, and the file is assembled only from units that pass.',
           'use by=' + json.dumps(list(applicators)) + ', route=search'
           + (f', samples={int(samples)}' if samples else '') + f', retries={int(retries)}, rounds={int(rounds)}'
           + ', context=none.',
           f'let sheet_shared = {literal(shared)}.', '']
    # the leading run counts given units too (they are literal text as well), but only units taken from an earlier
    # build are "kept": a sheet whose first unit is given, compiled without --keep, has no kept unit to announce
    from_earlier = [i for i in range(kept) if _var(units[i]['names'][0]) not in given]
    if from_earlier:
        source = f' ({" ".join(keep_from.split())[:200]})' if keep_from.strip() else ''
        given_too = ' (the units the sheet gives excepted)' if len(from_earlier) < kept else ''
        out[2:2] = [f'note Units 1-{kept}{given_too} are kept from an earlier build{source}: their code is the text '
                    f'that build accepted, tested again here, and no model is asked for them.']
    for i, unit in enumerate(units):
        var = _var(unit['names'][0])
        test = 'test_' + var[5:]
        # every earlier unit, not only this one's dependencies: the file holds them all, so a top-level name this unit
        # declares again fails HERE, and the last unit's test is a whole-file check. The pieces run as separate scripts:
        # a const declared again fails "already declared", a function declared again fails "defines f again" (a
        # classic script would let the copy silently replace the earlier unit's function)
        pieces = ([literal(unit['setup'])] if unit['setup'] else []) + \
            [_var(units[j]['names'][0]) for j in range(i)] + [var]
        cases = ', '.join(f'[{literal(call)}, {literal(expect)}]' for call, expect in unit['examples'])
        if var in given:
            out.append(f'# unit {i + 1} of {len(units)}: {unit["heading"]} (given by the sheet)')
            out.append(f'let {var} = {literal(given[var])}.')
            out.append(f'let {test} = js_test([{", ".join(pieces)}], [{cases}]).')
            out.append(f'assert {test}.passed because {test}.report.')
        elif i < kept:
            out.append(f'# unit {i + 1} of {len(units)}: {unit["heading"]} (kept)')
            out.append(f'let {var} = {literal(keep[var])}.')
            out.append(f'let {test} = js_test([{", ".join(pieces)}], [{cases}]).')
            out.append(f'assert {test}.passed because {test}.report.')
        else:
            out.append(f'# unit {i + 1} of {len(units)}: {unit["heading"]}')
            ty = 'Code js'
            if sheet.get('normalize'):
                earlier = [n for j in range(i) for n in units[j]['names'] if n not in unit['names']]
                ty += f' unit {", ".join(unit["names"])}' + (f' reusing {", ".join(earlier)}' if earlier else '')
            out.append(f'ask {var}: {ty} {literal_parts(unit_prompt(sheet, i))}.')
            out.append(f'let {test} = js_test([{", ".join(pieces)}], [{cases}]).')
            if var in exact:
                out.append(f'let exact_{var[5:]} = {literal(exact[var])}.')
                out.append(f'ensure {test}.passed else retry because join([{test}.report, '
                           f'"Your answer must be exactly the code given in the task.", '
                           f'diff_lines({var}, exact_{var[5:]})], "\\n").')
            else:
                out.append(f'ensure {test}.passed else retry because {test}.report.')
        out.append('')
    template = sheet['template']
    out.append(f'let page = {literal(template["text"])}.')
    out.append('let code = join([' + ', '.join(_var(u['names'][0]) for u in units) + '], "\\n\\n").')
    file_var = 'built_' + re.sub(r'\W', '_', template['file'])
    out.append(f'let {file_var} = replace(page, {literal(PLACEHOLDER)}, code).')
    out.append(f'show {file_var} as {json.dumps(template["file"])}.')
    return '\n'.join(out) + '\n'


# ----------------------------------------------------------------------------------------------------- diagnosis

def _rows(path: str) -> list:
    try:
        with open(path, encoding='utf-8') as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        return []


def _calls(folder: str) -> list:
    """The folder's model calls, once each (a cache merged from several runs repeats rows)."""
    import os
    out, seen = [], set()
    for c in _rows(os.path.join(folder, 'calls.jsonl')):
        k = (c.get('key'), c.get('at'), c.get('sample'), c.get('repair'))
        if c.get('key') is None or c.get('at') is None:          # not a recorded call row: nothing to match it by
            out.append(c)
        elif k not in seen:
            seen.add(k)
            out.append(c)
    return out


def ask_types(folder: str) -> dict:
    """{unit_X: type} for every `ask unit_X: Code js ...` of a run's program (empty when it cannot be read)."""
    import os

    from symblic.kernel import language as S
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as fh:
            statements = S.parse(fh.read())['statements']
    except (OSError, S.SymblicError):
        return {}
    return {str(st.name): st.type for st in statements if getattr(st, 'k', '') == 'ask' and isinstance(getattr(st, 'type', None), dict)}


def reply_code(text: str, ty: dict | None) -> str:
    """The code a reply bound: the normalized text for a `Code js unit ...` ask, the plain extraction otherwise."""
    from symblic.kernel import language as S
    if ty and ty.get('names'):
        from symblic.js import normalize as symblic_js_normalize
        return symblic_js_normalize.normalize(text, ty)
    return S.extract_code(text, 'js')


def accepted_units(folder: str) -> dict[str, str]:
    """The code a build accepted, by unit variable (`unit_X`), from its run folder.

    An asked unit: the trace shows only the first 400 characters of a value but names its fingerprint, so the
    accepted code is the reply (the run's own, or a cached one it replayed) whose code has that fingerprint. A unit
    the program kept from an earlier build: the literal in program.sym, once the trace shows its check passed."""
    import os

    from symblic.kernel import language as S
    trace = _rows(os.path.join(folder, 'trace.jsonl'))
    wanted = {t.get('name'): t.get('hash') for t in trace
              if t.get('kind') == 'ask' and t.get('status') == 'ok' and t.get('hash')}
    types = ask_types(folder)
    out = {}
    for c in _calls(folder):
        reply = c.get('reply') or {}
        name = c.get('stmt')
        if name in wanted and name not in out and reply.get('ok'):
            code = reply_code(reply.get('text') or '', types.get(name))
            if S.fingerprint(code) == wanted[name]:
                out[name] = code
    passed = {t.get('line') for t in trace if t.get('kind') == 'assert' and t.get('status') == 'ok'}
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as fh:
            program = S.parse(fh.read())['statements']
    except (OSError, S.SymblicError):
        return out
    kept = {s.name: ''.join(s.value.parts) for s in program
            if s.k == 'let' and str(s.name).startswith('unit_') and getattr(s.value, 'k', '') == 'str'
            and all(isinstance(p, str) for p in s.value.parts)}
    for s in program:                                   # assert test_X.passed ... (the kept unit's check)
        if s.k == 'assert' and s.line in passed and getattr(s.cond, 'k', '') == 'attr':
            name = 'unit_' + str(getattr(s.cond.obj, 'name', ''))[5:]
            if name in kept:
                out.setdefault(name, kept[name])
    return out


def diagnose(text: str, folder: str, only: str | None = None, everything: bool = False) -> list[dict]:
    """Where models misread the sheet, from one build's run folder (program.sym, calls.jsonl, trace.jsonl).

    Every model reply to a unit's ask is tested again by the kernel's sandboxed JavaScript against this sheet's
    examples, after the code that run accepted for the earlier units, as the build tested it. Failing replies are
    grouped by the first example they fail. Only the run's own calls count, unless `everything` (then also the calls
    of earlier programs merged into the folder as a cache, which may have answered other wordings). Per unit:
    {'unit', 'line', 'accepted', 'replies', 'distinct', 'passed', 'failures': [{'example', 'expected', 'replies',
    'got': [[what happened, count], ...], 'models': {app: count}}], 'note'}. No model is called, nothing is
    written."""
    import hashlib
    import os

    from symblic.js import check as J
    sheet = parse(text)
    units = sheet['units']
    asks = {}
    with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as fh:
        program = fh.read()
    for n, line in enumerate(program.split('\n'), 1):
        m = re.match(r'ask (unit_\w+): Code', line)
        if m:
            asks[m.group(1)] = n
    own = hashlib.sha256(program.encode('utf-8')).hexdigest()
    calls = [c for c in _calls(folder) if everything or c.get('source_sha256') == own]
    accepted = accepted_units(folder)
    types = ask_types(folder)
    kept = set(re.findall(r'^let (unit_\w+) = ', program, re.M))
    out = []
    for i, unit in enumerate(units):
        var = _var(unit['names'][0])
        if only and only != var and only not in unit['names']:
            continue
        row = {'unit': unit['heading'], 'line': asks.get(var), 'accepted': var in accepted, 'replies': 0,
               'distinct': 0, 'passed': 0, 'failures': [], 'note': ''}
        out.append(row)
        earlier = [accepted.get(_var(units[j]['names'][0])) for j in range(i)]
        if row['line'] is None:
            row['note'] = (('given by the sheet: no model was asked' if re.search(r'^# unit \d+ of \d+: .*\(given by the sheet\)\n' + re.escape('let ' + var + ' = '), program, re.M) else 'kept from an earlier build: no model was asked') if var in kept else
                           'the program has no ask for this unit (compiled from another sheet?)')
            continue
        if any(code is None for code in earlier):
            row['note'] = 'an earlier unit was not accepted in this run, so the replies cannot be tested as built'
            continue
        tested, groups = {}, {}
        for c in calls:
            reply = c.get('reply') or {}
            if c.get('stmt') != var or not reply.get('ok'):
                continue
            row['replies'] += 1
            code = reply_code(reply.get('text') or '', types.get(var))
            if code not in tested:
                pieces = ([unit['setup']] if unit['setup'] else []) + earlier + [code]
                tested[code] = J.failures(pieces, unit['examples'])[0]
            failed = tested[code]
            if not failed:
                row['passed'] += 1
                continue
            call, expected, got = failed[0]
            g = groups.setdefault(call, {'example': call, 'expected': expected, 'replies': 0, 'got': {}, 'models': {}})
            g['replies'] += 1
            g['got'][got] = g['got'].get(got, 0) + 1
            app = c.get('app') or '?'
            g['models'][app] = g['models'].get(app, 0) + 1
        row['distinct'] = len(tested)
        for g in sorted(groups.values(), key=lambda g: -g['replies']):
            g['got'] = sorted(([k, v] for k, v in g['got'].items()), key=lambda kv: -kv[1])
            row['failures'].append(g)
    return out


def _print_diagnosis(rows: list[dict]) -> None:
    for r in rows:
        state = 'accepted' if r['accepted'] else 'not accepted'
        print(f"{r['unit']} (line {r['line']}): {r['replies']} replies, {r['distinct']} distinct, "
              f"{r['passed']} pass, {state}" + (f" - {r['note']}" if r['note'] else ''))
        for g in r['failures'][:4]:
            models = ', '.join(f'{k} {v}' for k, v in sorted(g['models'].items()))
            print(f"  {g['replies']} fail first at: {g['example'][:200]}")
            print(f"     expected {g['expected'][:200]}")
            for what, n in g['got'][:3]:
                print(f"     {n} x {what.strip()[:200]}")
            print(f"     ({models})")


def main(argv: list[str]) -> int:
    import argparse
    import os
    ap = argparse.ArgumentParser(description='compile a strict spec sheet into a Symblic program, or diagnose a build')
    ap.add_argument('command', choices=['compile', 'check', 'diagnose'])
    ap.add_argument('sheet')
    ap.add_argument('--by', action='append', default=[], help='an applicator (repeat for a collection of models)')
    ap.add_argument('--samples', type=int, default=None)
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--keep', help='compile: keep the leading units this earlier build (its run folder) accepted')
    ap.add_argument('--redo', action='append', default=[], help='compile: stop keeping at this unit (a name it defines)')
    ap.add_argument('--run', help='diagnose: the run folder of a build compiled from this sheet')
    ap.add_argument('--unit', help='diagnose: only this unit (a name it defines)')
    ap.add_argument('--all', action='store_true', help='diagnose: also the calls merged in from earlier programs')
    ap.add_argument('--json', action='store_true', help='diagnose: print JSON')
    a = ap.parse_args(argv)
    text = open(a.sheet, encoding='utf-8').read()
    if a.command == 'check':
        found = problems(parse(text))
        print('\n'.join(found) if found else 'ok')
        return 1 if found else 0
    if a.command == 'diagnose':
        if not a.run:
            ap.error('diagnose needs --run FOLDER')
        if not os.path.isfile(os.path.join(a.run, 'program.sym')):
            print(f'diagnose: {a.run} has no program.sym; give the run folder of a build compiled from this sheet',
                  file=sys.stderr)
            return 2
        rows = diagnose(text, a.run, a.unit, everything=a.all)
        if a.json:
            print(json.dumps(rows, indent=1))
        else:
            _print_diagnosis(rows)
        return 0
    keep = accepted_units(a.keep) if a.keep else None
    sys.stdout.write(compile_sheet(text, a.by, samples=a.samples, retries=a.retries, rounds=a.rounds, keep=keep,
                                   keep_from=('run ' + os.path.basename(a.keep.rstrip('/'))) if a.keep else '',
                                   redo=a.redo))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

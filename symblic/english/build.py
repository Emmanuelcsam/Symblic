"""English construction documents: "Build a character animation called ..." compiled to checked model-written steps.

What it is for: the construction grammar of symblic.english. The author writes, in English, the steps of a
character animation (for example the example Matrix rain: letters, movement, positions, shades, columns, frames);
each step becomes one model request for one small JavaScript function (a `Code js` ask), checked by the kernel's
sandboxed JavaScript against finite cases this module derives from the step's English obligations, and the accepted
functions are run once (`js_run`) to produce the frames a character player shows. The author supplies English; the
model writes every executable unit. This module supplies interfaces and finite checks, never a candidate
implementation. Unrecognized obligations refuse compilation. No provider or JavaScript runs while compiling. The
output is data for a character player, not browser code.

`checkpoint(folder)` rechecks a finished or failed run's accepted steps locally, so a retry keeps them
(`compile_source(text, artifacts=...)`) and asks only for the remaining steps.

Depends on: symblic.kernel.language, symblic.english.compiler, symblic.js.check and symblic.spec.sheets (checkpoint).
Used by: symblic.english.compiler (dispatch on the first words) and symblic.english.authoring.
Status: one worked example (EXAMPLE, also examples/english/matrix-rain.english.txt); tested with fake models only.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import re

from symblic.kernel import language as S
from symblic.english import compiler as E

VERSION = 'symblic-english-build/2'
MAX_STEPS = 24
# One js_test report is bounded by the checker (six failures, each with a shortened call, expected and
# got). The retry capsule holds exactly one report plus an explicit marker when the second check also
# failed: a 4B model stalled repeatedly under the two full reports joined together (beta review E3,
# 2026-10-08). The scoped report carries the expected/got head the diagnostics rely on.
OMITTED_ASSEMBLY = '[the assembled-program check also failed; its report is omitted to bound this feedback]'
CANVAS = {'width': 32, 'height': 24, 'trail': 8, 'frames': 24,
          'origin': 'top', 'background': 'black', 'foreground': 'green',
          'shade_min': 0, 'shade_max': 7, 'repeat': True}
_NAME = re.compile(r'[A-Za-z]+(?: [A-Za-z]+)*')
_HEADER = re.compile(r'Build a character animation called ([A-Za-z]+(?: [A-Za-z]+)*)\.', re.IGNORECASE)
_START = re.compile(r'Ask the model to make ([A-Za-z]+(?: [A-Za-z]+)*)\.', re.IGNORECASE)
_CANVAS = 'Use the standard character canvas and a complete repeating sequence.'
_STYLE = ('Show green characters on a black background with the brightest leading characters '
          'and progressively darker trails.')
_DISPLAY = 'Display the accepted animation and repeat it in the character player.'

# Each contract is reusable under arbitrary step names. Dependency roles, not
# user-chosen names, determine its interface. None of these entries is a body.
CONTRACTS = {
    'letters': {
        'rules': [('Choose the uppercase English letter at the requested position and repeat the alphabet '
                   'after its end.')],
        'check': 'Check the beginning, the end and repeated journeys through the alphabet.',
        'args': 'offset', 'deps': [],
        'interface': 'offset is a nonnegative integer. Return a single uppercase English letter as text. '
                     'The alphabet starts with A at offset zero and ends with Z before repeating.'},
    'movement': {
        'rules': [('Move a row by the requested distance and wrap between the bottom and the top in '
                   'either direction.')],
        'check': 'Check every canvas row with forward, backward and stationary movement.',
        'args': 'row, distance, height', 'deps': [],
        'interface': 'row and distance are integers; height is a positive integer. Rows count from zero at '
                     'the top through height minus one at the bottom. Return the wrapped integer row, '
                     'including when distance is negative or spans several complete cycles.'},
    'heads': {
        'rules': ['Start the leftmost column at the top.',
                  ('Start each following column below the previous column by the trail length and wrap '
                   'below the bottom to the top.'),
                  'Move the leftmost column downward at normal speed.',
                  'Alternate each following column between double speed and normal speed.'],
        'check': 'Check the initial positions, both speeds and repeated journeys through the canvas.',
        'args': 'column, tick, height, trail', 'deps': ['movement'],
        'interface': 'All arguments are integers. column and tick start at zero; height and trail are '
                     'positive. The initial unwrapped row is column multiplied by trail. Even columns '
                     'advance one row per tick; odd columns advance two. Return the wrapped head row '
                     'using the selected movement function.'},
    'trails': {
        'rules': [('Place each later trail character immediately above the previous character and wrap '
                   'above the top to the bottom.')],
        'check': 'Check every trail position at the top, middle and bottom of the canvas.',
        'args': 'head, age, height', 'deps': ['movement'],
        'interface': 'head is an integer row; age is a nonnegative integer; height is a positive integer. '
                     'Age zero is the leader. Each later age is one row above the previous age. Return '
                     'its wrapped row using the selected movement function.'},
    'shades': {
        'rules': [('Give the leading character the brightest shade and make each later trail character '
                   'progressively darker until the darkest shade.')],
        'check': 'Check the leading shade, every trail shade and saturation at the darkest shade.',
        'args': 'age', 'deps': [],
        'interface': 'age is a nonnegative integer. The player uses integer shades zero through seven. '
                     'Zero is brightest, seven is darkest. Advance one shade for every age step; '
                     'remain at seven after reaching the darkest shade.'},
    'frames': {
        'rules': ['Fill each separate vertical column with its leading character and trailing characters.',
                  ('Choose each character from its column position plus the elapsed frame position plus '
                   'its distance behind the leader.'),
                  'Restart the frame position at the beginning whenever the complete canvas cycle finishes.',
                  ('Use the restarted frame position for both character selection and movement so that '
                   'every repetition begins identically.')],
        'check': 'Check every character position, letter and shade against the earlier accepted steps.',
        'args': 'width, height, trail, tick', 'deps': ['letters', 'heads', 'trails', 'shades'],
        'interface': 'width, height and trail are positive integers; tick is nonnegative. trail is at most '
                     'height and eight. Normalize tick by the height before any other work. Return an '
                     'object with exactly kind, width, height, tick, cells. kind is character-grid; tick '
                     'is the normalized tick. cells is an array in column order, then increasing age. '
                     'Every column has trail cells, including its leader. A cell has exactly x, y, char, '
                     'shade. x is its column; y comes from the selected head and trail functions; char '
                     'comes from the selected letter function using column plus normalized tick plus '
                     'age; shade comes from the selected shade function. Call these checked functions '
                     'instead of replacing their work.'},
    'cell': {
        'rules': ['Make the requested trail character in the requested column.',
                  'Place it the requested distance above its column leader and wrap above the top to the bottom.',
                  ('Choose its letter from its column position plus the elapsed frame position plus '
                   'its distance behind the leader.'),
                  'Use the shade for that distance behind the leader.'],
        'check': 'Check the character position, letter and shade against the earlier accepted steps.',
        'args': 'column, tick, age, height, trail',
        'deps': ['letters', 'heads', 'trails', 'shades'],
        'interface': 'column, tick and age are nonnegative integers; height and trail are positive. '
                     'tick is already less than height; age is less than trail. Return one object '
                     'with exactly x, y, char, shade. x is column. First obtain the column leader '
                     'from the selected leading positions function with column, tick, height, trail. '
                     'Pass that returned leader, age and height to the selected trailing positions '
                     'function; its returned row is y. Pass column plus tick plus age to the '
                     'selected letters function; its returned character is char. Pass age to '
                     'the selected shades function; its returned shade is shade. Return this '
                     'single cell, with no loop and no array.'},
    'column': {
        'rules': ['Create the complete vertical stream for the requested column.',
                  'Keep its characters in order from the leader to the end of the trail.'],
        'check': 'Check every character and its order against the earlier accepted character step.',
        'args': 'column, tick, height, trail', 'deps': ['cell'],
        'interface': 'column and tick are nonnegative integers; height and trail are positive; '
                     'tick is already less than height. Return an array of exactly trail cells '
                     'in increasing age order, starting with age zero. For every age, call the '
                     'selected character function with column, tick, age, height, trail. '
                     'Append that returned cell. Return the array, not a frame object.'},
    'frames_from_columns': {
        'role': 'frames',
        'rules': ['Create a frame by collecting the complete vertical stream for every column.',
                  'Keep the columns in order from the left edge to the right edge.',
                  'Keep every character in the order supplied by its column.',
                  'Restart the frame position at the beginning whenever the complete canvas cycle finishes.',
                  ('Use the restarted frame position for both character selection and movement so that '
                   'every repetition begins identically.')],
        'check': 'Check every complete column and its order against the earlier accepted column step.',
        'args': 'width, height, trail, tick', 'deps': ['column'],
        'interface': 'width, height and trail are positive integers; tick is nonnegative. '
                     'trail is at most height and eight. Normalize tick by height first. '
                     'Return an object with exactly kind, width, height, tick, cells. kind is '
                     'character-grid; tick is normalized. For each column from zero through '
                     'width minus one, call the selected column function with column, normalized '
                     'tick, height, trail. Append all cells from that returned array to cells '
                     'without changing their order. cells is one flat array, not arrays of columns.'},
    'film': {
        'rules': [('Create successive frames from the initial canvas until every stream returns to its '
                   'starting position.')],
        'check': 'Check the complete sequence, its ordering and its return to the initial frame.',
        'args': 'width, height, trail', 'deps': ['frames'],
        'interface': 'width, height and trail are positive integers. Return an array containing exactly '
                     'height frames in increasing tick order, starting at tick zero and ending at height '
                     'minus one. Obtain each frame by calling the selected frame function with width, '
                     'height, trail and that tick. Do not add a repeated final frame.'},
}


def recognizes(text):
    """Recognize the construction lane without accepting malformed documents."""
    return isinstance(text, str) and text.lstrip('\ufeff \t\r\n').lower().startswith(
        'build a character animation')


def _key(text):
    return ' '.join(text.lower().split())


def _error(message, stmt=None, code='ENG_BUILD'):
    return E.EnglishError(code, message, (stmt or {}).get('line', 1), (stmt or {}).get('col', 1))


def _sentences(text):
    normalized = E._normalize(text)
    statements = []
    for line, raw in enumerate(normalized.split('\n'), 1):
        if not raw.strip():
            continue
        value = raw.strip()
        col = len(raw) - len(raw.lstrip()) + 1
        stmt = {'index': len(statements) + 1, 'line': line, 'col': col, 'end_line': line,
                'end_col': col + len(value) - 1, 'kind': 'construction', 'text': value,
                'native_lines': []}
        if not re.fullmatch(r'[A-Za-z ,]+\.', value):
            raise _error('Write one complete English sentence per line, using letters, spaces, commas and '
                         'a final period. Construction source does not accept code or digits.', stmt)
        statements.append(stmt)
    if not statements:
        raise _error('Start with Build a character animation called followed by its name.')
    if len(statements) > E.MAX_STATEMENTS:
        raise _error('This construction has too many English statements.', statements[E.MAX_STATEMENTS],
                     'ENG_LIMIT')
    return statements


def _parse(text):
    statements = _sentences(text)
    title = _HEADER.fullmatch(statements[0]['text'])
    if title is None:
        raise _error('Start with Build a character animation called followed by its name.', statements[0])
    if len(title.group(1)) > 80:
        raise _error('The animation name is too long.', statements[0], 'ENG_LIMIT')
    statements[0]['kind'] = 'build'
    if len(statements) < 4:
        raise _error('The canvas, presentation, model steps and final display are required.', statements[-1])
    for idx, sentence, kind in ((1, _CANVAS, 'canvas'), (2, _STYLE, 'presentation')):
        if _key(statements[idx]['text']) != _key(sentence):
            raise _error('Expected: ' + sentence, statements[idx])
        statements[idx]['kind'] = kind
    units, names, current = [], {}, None
    for stmt in statements[3:]:
        sentence = stmt['text']
        start = _START.fullmatch(sentence)
        if start:
            if current is not None:
                raise _error('Finish the preceding step before starting another model task.', stmt)
            name = start.group(1)
            key = _key(name)
            if len(name) > E.MAX_NAME or ' and ' in key:
                raise _error('A step name uses at most forty eight letters and spaces; do not put and '
                             'inside its name.', stmt, 'ENG_NAME')
            if key in names:
                raise _error('This step name has already been used.', stmt, 'ENG_NAME')
            if len(units) >= MAX_STEPS:
                raise _error('This construction has too many model steps.', stmt, 'ENG_LIMIT')
            current = {'name': name, 'key': key, 'start': stmt, 'rules': [], 'using': None,
                       'check': None, 'finish': None, 'statements': [stmt]}
            stmt['kind'] = 'ask'
            continue
        if current is None:
            if _key(sentence) == _key(_DISPLAY) and stmt is statements[-1] and units:
                if units[-1]['contract'] != 'film':
                    raise _error('The final accepted step must construct a complete sequence.', stmt)
                stmt['kind'] = 'display'
                continue
            raise _error('Expected a model step or the final display sentence; this sentence has no '
                         'supported construction meaning.', stmt)
        current['statements'].append(stmt)
        if _key(sentence) == 'finish this step.':
            if not current['rules'] or current['using'] is None or current['check'] is None:
                raise _error('Each step needs its complete rule, selected earlier steps and explicit check '
                             'before Finish this step.', stmt)
            matches = [name for name, contract in CONTRACTS.items()
                       if [_key(s['text']) for s in current['rules']] == [_key(s) for s in contract['rules']]]
            if not matches:
                raise _error('These instructions do not match a supported complete construction rule; '
                             'no part of the rule was silently ignored.', current['rules'][0])
            contract = CONTRACTS[matches[0]]
            if _key(current['check']['text']) != _key(contract['check']):
                raise _error('This rule requires: ' + contract['check'], current['check'])
            dep_units = []
            for name in current['dependency_names']:
                dep = names.get(_key(name))
                if dep is None:
                    raise _error('Selected step ' + name + ' is not an earlier accepted step.',
                                 current['using'], 'ENG_NAME')
                if dep in dep_units:
                    raise _error('An earlier step was selected more than once.', current['using'], 'ENG_NAME')
                dep_units.append(dep)
            if [CONTRACTS[dep['contract']].get('role', dep['contract']) for dep in dep_units] != contract['deps']:
                wanted = ', '.join(contract['deps']) or 'no earlier steps'
                raise _error('The selected steps must provide these roles in this order: ' + wanted + '.',
                             current['using'])
            current.update({'contract': matches[0], 'deps': dep_units, 'finish': stmt,
                            'function': 'build_step_' + str(len(units) + 1),
                            'binding': 'built_step_' + str(len(units) + 1)})
            stmt['kind'] = 'finish'
            names[current['key']] = current
            units.append(current)
            current = None
        elif _key(sentence) == 'use no earlier steps.' or _key(sentence).startswith('use only '):
            if current['using'] is not None or current['check'] is not None:
                raise _error('Select earlier steps once, after the rule and before its check.', stmt)
            current['using'] = stmt
            stmt['kind'] = 'using'
            if _key(sentence) == 'use no earlier steps.':
                current['dependency_names'] = []
            else:
                selected = re.split(r'\s+and\s+', sentence[9:-1], flags=re.IGNORECASE)
                if not all(_NAME.fullmatch(name) for name in selected):
                    raise _error('Separate earlier step names with and.', stmt)
                if len(selected) > E.MAX_SELECTED:
                    raise _error('Too many earlier steps were selected.', stmt, 'ENG_LIMIT')
                current['dependency_names'] = selected
        elif _key(sentence).startswith('check '):
            if current['using'] is None or current['check'] is not None:
                raise _error('Put the explicit check once, immediately after the selected earlier steps.', stmt)
            current['check'] = stmt
            stmt['kind'] = 'accept'
        else:
            if current['using'] is not None:
                raise _error('Rules must come before the selected earlier steps and the check.', stmt)
            if not any(_key(sentence) in [_key(rule) for rule in c['rules']] for c in CONTRACTS.values()):
                raise _error('Unsupported construction instruction. Rewrite it as a supported rule; '
                             'the compiler will not discard it.', stmt)
            current['rules'].append(stmt)
            stmt['kind'] = 'rule'
    if current is not None:
        raise _error('This model step is unfinished.', current['start'])
    if statements[-1]['kind'] != 'display':
        raise _error('End with: ' + _DISPLAY, statements[-1])
    return title.group(1), statements, units


def _row(row, distance, height):
    return (row + distance) % height


def _frame(width, height, trail, tick):
    """Independent test oracle only. Never supplies executable model answers."""
    tick %= height
    cells = []
    for column in range(width):
        head = (column * trail + tick * (1 if column % 2 == 0 else 2)) % height
        for age in range(trail):
            cells.append({'x': column, 'y': (head - age) % height,
                          'char': chr(ord('A') + (column + tick + age) % 26), 'shade': min(age, 7)})
    return {'kind': 'character-grid', 'width': width, 'height': height, 'tick': tick, 'cells': cells}


def _examples(unit):
    kind, fn = unit['contract'], unit['function']
    cases = []
    if kind == 'letters':
        cases = [([n], chr(ord('A') + n % 26)) for n in (0, 25, 26, 77)]
    elif kind == 'movement':
        cases = [(list(args), _row(*args)) for args in ((0, 0, 24), (23, 1, 24), (0, -1, 24), (5, 50, 24))]
    elif kind == 'heads':
        cases = [(list(args), (args[0] * args[3] + args[1] * (1 + args[0] % 2)) % args[2])
                 for args in ((0, 0, 24, 8), (1, 0, 24, 8), (1, 1, 24, 8), (3, 13, 24, 8))]
    elif kind == 'trails':
        cases = [(list(args), (args[0] - args[1]) % args[2])
                 for args in ((0, 0, 24), (0, 1, 24), (12, 7, 24), (23, 2, 24))]
    elif kind == 'shades':
        cases = [([n], min(n, 7)) for n in (0, 1, 7, 40)]
    elif kind == 'cell':
        for column, tick, age, height, trail in ((0, 0, 1, 24, 8), (1, 1, 2, 24, 8), (2, 3, 1, 5, 3)):
            cell = _frame(column + 1, height, trail, tick)['cells'][column * trail + age]
            cases.append(([column, tick, age, height, trail], cell))
    elif kind == 'column':
        for column, tick, height, trail in ((0, 0, 3, 2), (1, 1, 4, 2), (2, 3, 5, 3)):
            cells = _frame(column + 1, height, trail, tick)['cells'][column * trail:]
            cases.append(([column, tick, height, trail], cells))
    elif kind in ('frames', 'frames_from_columns'):
        cases = [(list(args), _frame(*args)) for args in ((1, 3, 2, 0), (2, 4, 2, 1), (2, 4, 2, 4))]
    elif kind == 'film':
        cases = [([w, h, t], [_frame(w, h, t, tick) for tick in range(h)])
                 for w, h, t in ((1, 1, 1), (1, 3, 2), (2, 3, 2))]
    return [(fn + '(' + ','.join(map(str, args)) + ')', _json(expect)) for args, expect in cases]


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


def _selected_closure(unit, earlier):
    """Runtime dependencies of selected units; not extra model context."""
    wanted = set()

    def visit(dep):
        if dep['binding'] in wanted:
            return
        wanted.add(dep['binding'])
        for parent in dep['deps']:
            visit(parent)

    for dep in unit['deps']:
        visit(dep)
    return [dep for dep in earlier if dep['binding'] in wanted]


def _coverage_cases(unit):
    """Bounded acceptance coverage named by each English Check sentence.

    The model sees the small examples. These additional checks remain explicit in
    compiler metadata and the generated native source; failures can become repair
    feedback. They are construction checks, not held-out evaluation.
    """
    kind, fn = unit['contract'], unit['function']
    cases = []
    if kind == 'letters':
        call = f'Array.from({{length:104}},(_,n)=>{fn}(n)).join("")'
        cases.append((call, _json('ABCDEFGHIJKLMNOPQRSTUVWXYZ' * 4)))
    elif kind == 'movement':
        for distance in (-49, -24, -1, 0, 1, 24, 49):
            call = f'Array.from({{length:24}},(_,r)=>{fn}(r,{distance},24))'
            cases.append((call, _json([_row(r, distance, 24) for r in range(24)])))
    elif kind == 'heads':
        for tick in (0, 1, 23, 24, 49):
            call = f'Array.from({{length:32}},(_,c)=>{fn}(c,{tick},24,8))'
            cases.append((call, _json([(c * 8 + tick * (1 + c % 2)) % 24 for c in range(32)])))
    elif kind == 'trails':
        for head in (0, 12, 23):
            call = f'Array.from({{length:8}},(_,a)=>{fn}({head},a,24))'
            cases.append((call, _json([(head - a) % 24 for a in range(8)])))
    elif kind == 'shades':
        call = f'Array.from({{length:32}},(_,a)=>{fn}(a))'
        cases.append((call, _json([min(a, 7) for a in range(32)])))
    elif kind == 'cell':
        letter, head, trail, shade = [d['function'] for d in unit['deps']]
        call = (f'(()=>{{for(let c=0;c<32;c++)for(let a=0;a<8;a++){{const v={fn}(c,17,a,24,8);'
                'if(Object.keys(v).sort().join(",")!=="char,shade,x,y"||v.x!==c'
                f'||v.y!=={trail}({head}(c,17,24,8),a,24)||v.char!=={letter}(c+17+a)'
                f'||v.shade!=={shade}(a))return false;}}return true;}})()')
        cases.append((call, 'true'))
    elif kind == 'column':
        cell = unit['deps'][0]['function']
        call = (f'(()=>{{for(let c=0;c<32;c++){{const cells={fn}(c,17,24,8);'
                'if(!Array.isArray(cells)||cells.length!==8)return false;'
                f'for(let a=0;a<8;a++)if(JSON.stringify(cells[a])!==JSON.stringify({cell}(c,17,a,24,8)))'
                'return false;}return true;})()')
        cases.append((call, 'true'))
    elif kind == 'frames_from_columns':
        column = unit['deps'][0]['function']
        call = (f'(()=>{{const f={fn}(32,24,8,17);return Object.keys(f).sort().join(",")==="cells,height,kind,tick,width"'
                '&&f.kind==="character-grid"&&f.width===32&&f.height===24&&f.tick===17&&f.cells.length===256'
                f'&&Array.from({{length:32}},(_,c)=>JSON.stringify(f.cells.slice(c*8,(c+1)*8))==='
                f'JSON.stringify({column}(c,17,24,8))).every(Boolean);}})()')
        cases.append((call, 'true'))
        cases.append((f'JSON.stringify({fn}(32,24,8,24))===JSON.stringify({fn}(32,24,8,0))', 'true'))
    elif kind == 'frames':
        # Compare every cell using the earlier accepted steps, never a candidate
        # reference implementation supplied in a literal.
        letter, head, trail, shade = [d['function'] for d in unit['deps']]
        call = (f'(()=>{{const f={fn}(32,24,8,17);return Object.keys(f).sort().join(",")==="cells,height,kind,tick,width"'
                '&&f.kind==="character-grid"&&f.width===32&&f.height===24&&f.tick===17&&f.cells.length===256'
                f'&&f.cells.every((v,i)=>{{const c=Math.floor(i/8),a=i%8;return Object.keys(v).sort().join(",")'
                f'==="char,shade,x,y"&&v.x===c&&v.y==={trail}({head}(c,17,24,8),a,24)'
                f'&&v.char==={letter}(c+17+a)&&v.shade==={shade}(a);}});}})()')
        cases.append((call, 'true'))
        cases.append((f'JSON.stringify({fn}(32,24,8,24))===JSON.stringify({fn}(32,24,8,0))', 'true'))
    elif kind == 'film':
        frame = unit['deps'][0]['function']
        call = (f'(()=>{{const film={fn}(32,24,8);return Array.isArray(film)&&film.length===24'
                f'&&film.every((f,t)=>JSON.stringify(f)===JSON.stringify({frame}(32,24,8,t)))'
                f'&&JSON.stringify({frame}(32,24,8,24))===JSON.stringify(film[0]);}})()')
        cases.append((call, 'true'))
    return cases


def _reusable(artifacts, unit, scoped, kept, document_sha256):
    """A checkpoint step becomes a kept literal only with its exact recorded bytes, for this exact
    document, and with its dependencies kept."""
    if artifacts is None:
        return None
    entry = artifacts.get(unit['binding'])
    code = entry.get('code') if type(entry) is dict else None
    if (type(code) is not str
            or hashlib.sha256(code.encode('utf-8')).hexdigest() != entry.get('code_sha256')
            or entry.get('document_sha256') != document_sha256
            or any(dep['binding'] not in kept for dep in scoped[:-1])):
        return None
    return entry


def checkpoint(folder, *, recheck_seconds=30):
    """Recheck a finished construction run's accepted steps locally; portable step memory for a retry.

    Reads only the run's own folder. Each accepted step's code is recovered from the run's recorded
    replies, then re-run against its own examples and construction checks (after its accepted
    dependencies) in the sandboxed JavaScript checker before it becomes a reusable artifact. A step
    whose reply never passed its checks is skipped and asked again on the retry. No model is called.
    """
    import time
    from pathlib import Path

    from symblic.js import check as JS
    from symblic.spec import sheets as SP
    if type(recheck_seconds) is not int or not 1 <= recheck_seconds <= 1800:
        raise _error('Recheck time must be an integer from 1 to 1800 seconds.')
    deadline = time.monotonic() + recheck_seconds
    folder = Path(folder)
    document = (folder / 'instructions.english').read_text(encoding='utf-8')
    if len(document) > S.MAX_SOURCE:
        raise _error('The saved English document exceeds its source limit.')
    if not recognizes(document):
        raise _error('This run holds no English construction document.')
    _, _, units = _parse(document)
    accepted = {name: code for name, code in SP.accepted_units(str(folder)).items()
                if isinstance(name, str) and re.fullmatch(r'built_step_\d+', name)}
    artifacts, skipped = {}, {}
    for index, unit in enumerate(units):
        binding = unit['binding']
        code = accepted.get(binding)
        scoped = _selected_closure(unit, units[:index])
        if code is None:
            skipped[binding] = 'not_accepted'
            continue
        if any(dep['binding'] not in artifacts for dep in scoped):
            skipped[binding] = 'missing_code_or_dependency'
            continue
        cases = _examples(unit) + _coverage_cases(unit)
        pieces = [artifacts[dep['binding']]['code'] for dep in scoped] + [code]
        result = JS._js_test(None, None, pieces, cases, deadline=deadline)
        if not result['passed']:
            skipped[binding] = 'examples_failed'
            continue
        sha = hashlib.sha256(code.encode('utf-8')).hexdigest()
        artifacts[binding] = {'code': code, 'code_sha256': sha, 'contract': unit['contract'],
                              'document_sha256': hashlib.sha256(document.encode('utf-8')).hexdigest(),
                              'checks': [{'scope': 'scoped_dependency_examples_and_construction_checks',
                                          'passed': True, 'subject_sha256': sha,
                                          'examples_sha256': hashlib.sha256(_json(cases).encode()).hexdigest(),
                                          'checker': JS.VERSION}]}
    return {'version': VERSION, 'kind': 'construction_checkpoint',
            'document_sha256': hashlib.sha256(document.encode('utf-8')).hexdigest(),
            'artifacts': artifacts, 'skipped': skipped,
            'scope': 'locally_rechecked_scoped_dependency_checks'}


def compile_source(text, *, retries=2, max_calls=64, budget=12000, artifacts=None):
    """Compile author English to checked native construction, without execution.

    `artifacts` (a construction checkpoint's rechecked steps) re-bind accepted steps as exact code
    literals: kept steps assert their checks instead of retrying, and only the remaining steps are
    asked of a model again.
    """
    retries = E._int_option('retries', retries, E.RETRIES)
    max_calls = E._int_option('max_calls', max_calls, E.MAX_CALLS)
    budget = E._int_option('budget', budget, E.BUDGET)
    if artifacts is not None and (type(artifacts) is not dict
                                  or any(type(v) is not dict or type(v.get('code')) is not str
                                         or type(v.get('code_sha256')) is not str
                                         for v in artifacts.values())):
        raise _error('Retained construction steps must be checkpoint artifact records.', code='ENG_RECOVERY')
    title, statements, units = _parse(text)
    source_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    lines, source_map = [], []

    def emit(line, owners):
        lines.append(line)
        number = len(lines)
        for stmt in owners:
            stmt['native_lines'].append(number)
            source_map.append({'native_line': number, 'line': stmt['line'], 'col': stmt['col'],
                               'statement': stmt['index']})
        return number

    emit('use profile=verified.', [statements[0]])
    emit('note Model-written construction from retained English; finite checks are not a proof of arbitrary '
         'English meaning. The character player owns playback, controls and the clock.', statements[:3])
    metadata = []
    kept: dict = {}
    for unit in units:
        contract = CONTRACTS[unit['contract']]
        cases = _examples(unit)
        coverage = _coverage_cases(unit)
        prior = units[:units.index(unit) + 1]
        scoped = _selected_closure(unit, prior[:-1]) + [unit]
        token = _reusable(artifacts, unit, scoped, kept, source_hash)
        instruction = '\n'.join(stmt['text'] for stmt in unit['statements'])
        instruction += ('\n\nGENERATED INTERFACE FOR THIS ENGLISH STEP\nWrite one JavaScript function named '
                        + unit['function'] + '(' + contract['args'] + ').\n' + contract['interface'])
        if unit['deps']:
            instruction += '\nCall the selected earlier functions using these interfaces:\n'
            instruction += '\n'.join(d['name'] + ': ' + d['function'] + '(' +
                                     CONTRACTS[d['contract']]['args'] + '). The accepted source is in '
                                     'CONTEXT under ' + d['binding'] + '.' for d in unit['deps'])
        instruction += '\nExamples checked before adoption:\n'
        instruction += '\n'.join(call + ' gives ' + expect for call, expect in cases)
        instruction += ('\nOther finite construction checks cover the English check sentence; their failures '
                        'can be returned for correction. Write only this function declaration in a JavaScript '
                        'code fence. Do not copy earlier functions, run the function, add other declarations, '
                        'perform I/O, use randomness or access a clock. Use only the selected functions and '
                        'standard JavaScript arithmetic, strings, arrays and objects.')
        sources = (' from ' + ', '.join(d['binding'] for d in unit['deps'])) if unit['deps'] else ''
        if token is not None:
            kept[unit['binding']] = token
            ask_line = emit(f'let {unit["binding"]} = {E.native_string(token["code"])}.', unit['statements'])
        else:
            ask = (f'ask {unit["binding"]}: Code js {E.native_string(instruction)}{sources} with context=none, '
                   f'determine=false, solve=false, retries={retries}, budget={budget}.')
            ask_line = emit(ask, unit['statements'])
        pieces = '[' + ', '.join(u['binding'] for u in prior) + ']'
        scoped_pieces = '[' + ', '.join(u['binding'] for u in scoped) + ']'
        encoded_cases = '[' + ', '.join('[' + E.native_string(call) + ', ' + E.native_string(expect) + ']'
                                       for call, expect in cases + coverage) + ']'
        checked = 'checked_' + unit['binding']
        check_line = emit(f'let {checked} = js_test({scoped_pieces}, {encoded_cases}).',
                          unit['rules'] + [unit['check']])
        assembled = 'assembly_' + unit['binding']
        assembly_line = emit(f'let {assembled} = js_test({pieces}, {encoded_cases}).',
                             unit['rules'] + [unit['check']])
        feedback = (f'if {checked}.passed then {assembled}.report else '
                    f'join([{checked}.report, {E.native_string(OMITTED_ASSEMBLY)}], "\\n")')
        gate_line = emit((f'assert {checked}.passed and {assembled}.passed because {feedback}.' if token
                          else f'ensure {checked}.passed and {assembled}.passed else retry because {feedback}.'),
                         [unit['check'], unit['finish']])
        for stmt in unit['statements']:
            stmt['ask'] = unit['binding']
        metadata.append({'name': unit['name'], 'contract': unit['contract'], 'function': unit['function'],
                         'binding': unit['binding'], 'id': unit['binding'], 'line': unit['start']['line'],
                         'uses': [d['name'] for d in unit['deps']],
                         'check_lines': [unit['check']['line']],
                         'selected_steps': [d['name'] for d in unit['deps']],
                         'selected_bindings': [d['binding'] for d in unit['deps']],
                         'runtime_dependency_bindings': [d['binding'] for d in scoped[:-1]],
                         'statement_ids': [s['index'] for s in unit['statements']],
                         'ask_line': ask_line, 'check_line': check_line, 'assembly_line': assembly_line,
                         'gate_line': gate_line,
                         'binding_kind': 'let' if token else 'ask',
                         'acquisition': 'reused_artifact' if token else 'model_request',
                         'artifact_code_sha256': token['code_sha256'] if token else None,
                         'visible_examples': len(cases), 'additional_construction_checks': len(coverage),
                         'instruction': instruction})
    pieces = '[' + ', '.join(u['binding'] for u in units) + ']'
    film_call = units[-1]['function'] + '(32,24,8)'
    display = statements[-1]
    emit('let constructed_code = join(' + pieces + ', "\\n\\n").', [display])
    emit('show constructed_code as "implementation.js".', [display])
    emit(f'let constructed_frames = js_run({pieces}, {E.native_string(film_call)}).',
         [statements[1], display])
    emit('for constructed_frame in constructed_frames do', [display])
    emit('  show constructed_frame.', [statements[2], display])
    emit('end.', [display])
    source = '\n'.join(lines) + '\n'
    if len(source) > E.MAX_NATIVE:
        raise _error('The compiled construction exceeds the native source limit.', code='ENG_LIMIT')
    parsed = S.parse(source, execution_profile='verified')
    asks = [s for s in parsed['statements'] if s.k == 'ask']
    asked = [meta for meta in metadata if meta['binding'] not in kept]
    if len(asks) != len(asked) or any(list(ask.parts) != [meta['instruction']]
                                     for ask, meta in zip(asks, asked)):
        raise RuntimeError('English construction instruction did not survive native parsing verbatim')
    return {'version': VERSION, 'source_sha256': source_hash, 'source': source,
            'options': {'profile': 'verified', 'context': 'none', 'determine': False, 'solve': False,
                        'constructor': 'off', 'max_calls': max_calls},
            'inputs': {}, 'names': {u['name']: u['binding'] for u in units},
            'statements': statements, 'source_map': source_map,
            'construction': {'version': VERSION, 'schema_version': 1, 'title': title, 'canvas': dict(CANVAS),
                             'defaults': dict(CANVAS),
                             'units': metadata, 'unmapped_statements': [],
                             'kept': len(kept),
                             'reuse': {u['binding']: {'reusable': u['binding'] in kept} for u in units},
                             'output': {'statement': display['index'],
                                        'selected_bindings': [u['binding'] for u in units],
                                        'sequence_binding': 'constructed_frames',
                                        'implementation_binding': 'constructed_code'},
                             'answer_origin': 'model_code_required',
                             'candidate_bodies': 'retained_artifact_bodies_only' if kept else 'not_supplied',
                             'check_scope': 'finite_examples_and_bounded_construction_checks',
                             'held_out_evaluation': 'not_performed_by_compiler',
                             'player_role': 'renders_saved_data_and_supplies_playback_clock'}}


# The preceding public example remains accepted without changing its native lowering.
LEGACY_EXAMPLE = 'Build a character animation called Matrix rain.\nUse the standard character canvas and a complete repeating sequence.\nShow green characters on a black background with the brightest leading characters and progressively darker trails.\n\nAsk the model to make letters.\nChoose the uppercase English letter at the requested position and repeat the alphabet after its end.\nUse no earlier steps.\nCheck the beginning, the end and repeated journeys through the alphabet.\nFinish this step.\n\nAsk the model to make movement.\nMove a row by the requested distance and wrap between the bottom and the top in either direction.\nUse no earlier steps.\nCheck every canvas row with forward, backward and stationary movement.\nFinish this step.\n\nAsk the model to make leading positions.\nStart the leftmost column at the top.\nStart each following column below the previous column by the trail length and wrap below the bottom to the top.\nMove the leftmost column downward at normal speed.\nAlternate each following column between double speed and normal speed.\nUse only movement.\nCheck the initial positions, both speeds and repeated journeys through the canvas.\nFinish this step.\n\nAsk the model to make trailing positions.\nPlace each later trail character immediately above the previous character and wrap above the top to the bottom.\nUse only movement.\nCheck every trail position at the top, middle and bottom of the canvas.\nFinish this step.\n\nAsk the model to make shades.\nGive the leading character the brightest shade and make each later trail character progressively darker until the darkest shade.\nUse no earlier steps.\nCheck the leading shade, every trail shade and saturation at the darkest shade.\nFinish this step.\n\nAsk the model to make frames.\nFill each separate vertical column with its leading character and trailing characters.\nChoose each character from its column position plus the elapsed frame position plus its distance behind the leader.\nRestart the frame position at the beginning whenever the complete canvas cycle finishes.\nUse the restarted frame position for both character selection and movement so that every repetition begins identically.\nUse only letters and leading positions and trailing positions and shades.\nCheck every character position, letter and shade against the earlier accepted steps.\nFinish this step.\n\nAsk the model to make animation.\nCreate successive frames from the initial canvas until every stream returns to its starting position.\nUse only frames.\nCheck the complete sequence, its ordering and its return to the initial frame.\nFinish this step.\n\nDisplay the accepted animation and repeat it in the character player.\n'

# The default separates a cell, a column and a frame into individual model tasks.
EXAMPLE = 'Build a character animation called Matrix rain.\nUse the standard character canvas and a complete repeating sequence.\nShow green characters on a black background with the brightest leading characters and progressively darker trails.\n\nAsk the model to make letters.\nChoose the uppercase English letter at the requested position and repeat the alphabet after its end.\nUse no earlier steps.\nCheck the beginning, the end and repeated journeys through the alphabet.\nFinish this step.\n\nAsk the model to make movement.\nMove a row by the requested distance and wrap between the bottom and the top in either direction.\nUse no earlier steps.\nCheck every canvas row with forward, backward and stationary movement.\nFinish this step.\n\nAsk the model to make leading positions.\nStart the leftmost column at the top.\nStart each following column below the previous column by the trail length and wrap below the bottom to the top.\nMove the leftmost column downward at normal speed.\nAlternate each following column between double speed and normal speed.\nUse only movement.\nCheck the initial positions, both speeds and repeated journeys through the canvas.\nFinish this step.\n\nAsk the model to make trailing positions.\nPlace each later trail character immediately above the previous character and wrap above the top to the bottom.\nUse only movement.\nCheck every trail position at the top, middle and bottom of the canvas.\nFinish this step.\n\nAsk the model to make shades.\nGive the leading character the brightest shade and make each later trail character progressively darker until the darkest shade.\nUse no earlier steps.\nCheck the leading shade, every trail shade and saturation at the darkest shade.\nFinish this step.\n\nAsk the model to make characters.\nMake the requested trail character in the requested column.\nPlace it the requested distance above its column leader and wrap above the top to the bottom.\nChoose its letter from its column position plus the elapsed frame position plus its distance behind the leader.\nUse the shade for that distance behind the leader.\nUse only letters and leading positions and trailing positions and shades.\nCheck the character position, letter and shade against the earlier accepted steps.\nFinish this step.\n\nAsk the model to make columns.\nCreate the complete vertical stream for the requested column.\nKeep its characters in order from the leader to the end of the trail.\nUse only characters.\nCheck every character and its order against the earlier accepted character step.\nFinish this step.\n\nAsk the model to make frames.\nCreate a frame by collecting the complete vertical stream for every column.\nKeep the columns in order from the left edge to the right edge.\nKeep every character in the order supplied by its column.\nRestart the frame position at the beginning whenever the complete canvas cycle finishes.\nUse the restarted frame position for both character selection and movement so that every repetition begins identically.\nUse only columns.\nCheck every complete column and its order against the earlier accepted column step.\nFinish this step.\n\nAsk the model to make animation.\nCreate successive frames from the initial canvas until every stream returns to its starting position.\nUse only frames.\nCheck the complete sequence, its ordering and its return to the initial frame.\nFinish this step.\n\nDisplay the accepted animation and repeat it in the character player.\n'

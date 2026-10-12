"""Labelled English pixel documents ("STATEMENT ZERO ONE: ...") compiled into a checked, model-written pixel program.

What it is for: the pixel grammar of symblic.english. The author writes a numbered list of English statements
describing a raster animation (the example: a white dot crossing an 800 x 600 black canvas at 60 frames per second,
34 statements). This module recognizes the supported statement forms, keeps the exact document and every
obligation, and builds a spec sheet of small JavaScript units (delta, square, separation, inside, nextX, bounds,
whitePixels, clearPixels, drawPixels) with finite examples derived from the statements; symblic.spec.build compiles
that sheet into task cards, and symblic.english.pixel_checks adds checks that run each candidate inside the exact
browser pixel interpreter. Models supply executable unit bodies; this adapter supplies interfaces and finite
examples, never replacements. The client executes accepted functions sequentially. A saved initial image is only a
preview, not evidence that a physical monitor or a timer fulfilled the contract (statements about monitors and
timers are recorded as obligations the checks cannot establish).

Depends on: symblic.kernel.language, symblic.lang.abstraction, symblic.english (compiler, pixel_checks),
symblic.spec (sheets, build, contracts). Used by: symblic.english.compiler and symblic.english.authoring.
Status: one worked example (EXAMPLE, also examples/english/moving-dot.english.txt); tested with fake models only.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import re

from symblic.kernel import language as S
from symblic.english import compiler as E
from symblic.english import pixel_checks as CHECKS
from symblic.lang import abstraction as L
from symblic.spec import sheets as SP
from symblic.spec import build as BUILD
from symblic.spec import contracts as CONTRACTS

VERSION = 'symblic-english-pixels/1'
MAX_PIXELS = 480_000
_SMALL = dict(zip(['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'], range(20)))
_TENS = dict(zip(['twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'], range(20, 100, 10)))
_LABELS = ['ZERO ' + s.upper() for s in ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']]
_LABELS += [s.upper() for s in ['ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty']]
_LABELS += ['TWENTY-' + s.upper() for s in ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']]
_LABELS += ['THIRTY'] + ['THIRTY-' + s.upper() for s in ['one', 'two', 'three', 'four']]
_SLOTS = {
    1: [('eight hundred', 'width'), ('six hundred', 'height')],
    2: [('zero', 'left'), ('seven hundred ninety-nine', 'right')],
    3: [('zero', 'top'), ('five hundred ninety-nine', 'bottom')],
    5: [('four hundred eighty thousand', 'count'), ('eight hundred', 'product_width'),
        ('six hundred', 'product_height')],
    7: [('zero', 'channel_min'), ('two hundred fifty-five', 'channel_max')],
    8: [('zero', 'black_r'), ('zero', 'black_g'), ('zero', 'black_b')],
    9: [('two hundred fifty-five', 'white_r'), ('two hundred fifty-five', 'white_g'),
        ('two hundred fifty-five', 'white_b')],
    11: [('five', 'radius')], 15: [('twenty-five', 'radius_squared')],
    16: [('four hundred eighty thousand', 'clear_count')],
    19: [('zero', 'initial_x')], 20: [('three hundred', 'initial_y')],
    21: [('three hundred', 'fixed_y'), ('zero', 'vertical_displacement')],
    22: [('seven hundred ninety-nine', 'wrap_right'), ('zero', 'reset_x')],
    23: [('seven hundred ninety-nine', 'step_right'), ('one', 'step_size')],
    25: [('eight hundred', 'physical_width'), ('six hundred', 'physical_height')],
    33: [('one', 'delay_numerator'), ('sixtieth', 'delay_denominator')],
}

SUBSET = ('Use only ordinary named function declarations, let or const, return, if, traditional for or '
          'for of loops, numeric or Boolean or null literals, arrays and plain objects, arithmetic, '
          'comparisons, Boolean operators, assignments, indexed writes, and the selected functions. '
          'Allowed methods are array push and fill and Math.min, Math.max, Math.abs, Math.floor. '
          'Do not use arrows, callbacks, while, constructors, new, globals, prototypes, recursion, '
          'dynamic calls, browser APIs or I/O. Use multiplication for squares. The buffer is supplied '
          'by the host; never allocate it inside your function.')


def recognizes(text):
    return isinstance(text, str) and text.lstrip('\ufeff \t\r\n').upper().startswith('STATEMENT ZERO ONE:')


is_source = recognizes


def _error(message, statement=None, code='ENG_PIXELS'):
    return E.EnglishError(code, message, (statement or {}).get('line', 1), (statement or {}).get('col', 1))


def _number(text):
    words = text.lower().replace('-', ' ').split()
    if words == ['sixtieth']:
        return 60
    total = group = 0
    for word in words:
        if word in _SMALL:
            group += _SMALL[word]
        elif word in _TENS:
            group += _TENS[word]
        elif word == 'hundred' and 1 <= group <= 9:
            group *= 100
        elif word == 'thousand' and 1 <= group <= 999:
            total += group * 1000
            group = 0
        else:
            raise ValueError('Unsupported English whole number: ' + text)
    return total + group


def _words(value):
    small = list(_SMALL)
    if value < 20:
        return small[value]
    if value < 100:
        return list(_TENS)[value // 10 - 2] + ('-' + small[value % 10] if value % 10 else '')
    if value < 1000:
        return small[value // 100] + ' hundred' + (' ' + _words(value % 100) if value % 100 else '')
    return _words(value // 1000) + ' thousand' + (' ' + _words(value % 1000) if value % 1000 else '')


def _document(text):
    normalized = E._normalize(text)
    pattern = re.compile(r'^STATEMENT ([A-Z -]+): (.+?)(?=\n\s*\n|\Z)', re.MULTILINE | re.DOTALL)
    matches = list(pattern.finditer(normalized))
    if len(matches) != 34 or [m.group(1) for m in matches] != _LABELS:
        raise _error('Supply every labelled statement exactly once, from STATEMENT ZERO ONE through '
                     'STATEMENT THIRTY-FOUR, in order.')
    cursor, statements = 0, []
    for index, match in enumerate(matches, 1):
        if normalized[cursor:match.start()].strip():
            raise _error('Text outside the labelled statements has no defined meaning.')
        start, end = match.start(), match.end()
        while end > start and normalized[end - 1] in '\r\n \t':
            end -= 1
        before = normalized[:start]
        line, col = before.count('\n') + 1, start - before.rfind('\n')
        ending = normalized[:end]
        statements.append({'index': index, 'label': match.group(1), 'line': line, 'col': col,
                           'end_line': ending.count('\n') + 1, 'end_col': end - ending.rfind('\n') - 1,
                           'text': normalized[start:end], 'body': match.group(2).rstrip(),
                           'kind': 'pixel_obligation', 'native_lines': []})
        cursor = end
    if normalized[cursor:].strip():
        raise _error('Text after the last statement has no defined meaning.', statements[-1])
    return statements


def parse_source(text):
    statements = _document(text)
    canonical = _document(EXAMPLE)
    values = {}
    for stmt, standard in zip(statements, canonical):
        expected = ' '.join(standard['body'].split())
        cursor, parts = 0, []
        for number_text, key in _SLOTS.get(stmt['index'], []):
            position = expected.index(number_text, cursor)
            parts += [re.escape(expected[cursor:position]), '(?P<' + key + '>[a-z -]+?)']
            cursor = position + len(number_text)
        parts.append(re.escape(expected[cursor:]))
        matched = re.fullmatch(''.join(parts), ' '.join(stmt['body'].split()))
        if matched is None:
            raise _error('Unsupported or changed meaning in this statement. No clause was dropped or '
                         'silently rewritten.', stmt)
        for key, words in matched.groupdict().items():
            try:
                value = _number(words)
                if (key == 'delay_denominator' and words != 'sixtieth') or (key != 'delay_denominator' and _words(value) != words):
                    raise ValueError('Use canonical English whole numbers.')
            except (ValueError, IndexError):
                raise _error('Write the quantity as an unambiguous English whole number.', stmt) from None
            values[key] = value
    v = values
    conditions = [
        (1, 1 <= v['width'] <= 2048 and 1 <= v['height'] <= 2048 and v['width'] * v['height'] <= MAX_PIXELS,
         'The declared canvas exceeds the bounded pixel renderer.'),
        (2, v['left'] == 0 and v['right'] == v['width'] - 1, 'Column bounds must match the canvas.'),
        (3, v['top'] == 0 and v['bottom'] == v['height'] - 1, 'Row bounds must match the canvas.'),
        (5, v['count'] == v['width'] * v['height'] and v['product_width'] == v['width']
         and v['product_height'] == v['height'], 'The stated pixel count and product must match the dimensions.'),
        (7, v['channel_min'] == 0 and v['channel_max'] == 255, 'This renderer implements exactly eight-bit RGB channels.'),
        (8, all(v[k] == 0 for k in ('black_r', 'black_g', 'black_b')), 'Black requires every channel to be zero.'),
        (9, all(v[k] == 255 for k in ('white_r', 'white_g', 'white_b')), 'White requires every channel to be at maximum.'),
        (11, 1 <= v['radius'] <= 16, 'The radius must fit the bounded raster task.'),
        (15, v['radius_squared'] == v['radius'] ** 2, 'The interior threshold must be the squared radius.'),
        (16, v['clear_count'] == v['count'], 'Clearing must cover the complete declared canvas.'),
        (19, 0 <= v['initial_x'] < v['width'], 'The initial column must lie within the canvas.'),
        (20, 0 <= v['initial_y'] < v['height'], 'The initial row must lie within the canvas.'),
        (21, v['fixed_y'] == v['initial_y'] and v['vertical_displacement'] == 0,
         'The declared vertical center must stay fixed.'),
        (22, v['wrap_right'] == v['right'] and v['reset_x'] == 0, 'Wrap must use the rightmost and leftmost columns.'),
        (23, v['step_right'] == v['right'] and v['step_size'] == 1, 'The next frame must advance exactly one column.'),
        (25, v['physical_width'] == v['width'] and v['physical_height'] == v['height'],
         'The requested physical viewport must match the logical canvas.'),
        (33, v['delay_numerator'] == 1 and v['delay_denominator'] == 60,
         'This presentation contract currently supports the stated one-sixtieth-second delay.'),
    ]
    for label, okay, message in conditions:
        if not okay:
            raise _error(message, statements[label - 1], 'ENG_PIXEL_CONTRADICTION')
    return statements, values


def _json(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False)


def _white(cx, cy, cfg):
    """Independent finite-check oracle; never supplied as a candidate body."""
    w, h, r = cfg['width'], cfg['height'], cfg['radius']
    return [y * w + x for y in range(max(0, cy - r), min(h - 1, cy + r) + 1)
            for x in range(max(0, cx - r), min(w - 1, cx + r) + 1)
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r]


def _unit(name, args, clauses, uses, instruction, examples):
    return {'name': name, 'args': args, 'clauses': clauses, 'uses': uses, 'instruction': instruction,
            'examples': [(call, _json(value)) for call, value in examples]}


def _units(c):
    w, h, r, cy = c['width'], c['height'], c['radius'], c['fixed_y']
    units = [
        _unit('delta', 'pixel, center', [12, 13], [],
              'Return the integer pixel minus center. This same operation serves either coordinate.',
              [('delta(7,3)', 4), ('delta(3,7)', -4), ('delta(3,3)', 0)]),
        _unit('square', 'value', [14], [],
              'Return value multiplied by itself. This is the single multiplication component of the statement.',
              [('square(-5)', 25), ('square(0)', 0), ('square(4)', 16)]),
        _unit('separation', 'dx, dy', [14], ['square'],
              'Return the sum of the selected square function applied to dx and to dy.',
              [('separation(3,4)', 25), ('separation(-3,-4)', 25), ('separation(0,0)', 0)]),
        _unit('inside', 'pixelX, pixelY, cx, cy', [15], ['delta', 'separation'],
              f'Compute horizontal and vertical differences with delta, then use separation. Return Boolean true '
              f'if and only if the squared separation is at most {r*r}. The boundary is included.',
              [(f'inside({r},0,0,0)', True), (f'inside({r+1},0,0,0)', False),
               ('inside(0,0,0,0)', True), (f'inside({-r},0,0,0)', True)]),
        _unit('nextX', 'previousX', [19, 22, 23], [],
              f'previousX is null before the initial frame or an integer from zero through {w-1}. '
              f'For null return {c["initial_x"]}. For {w-1} return zero. Otherwise return previousX plus one. '
              'Do not calculate any later frame or read a clock.',
              [('nextX(null)', c['initial_x']), ('nextX(0)', 1 if w > 1 else 0),
               (f'nextX({w-1})', 0), (f'nextX({max(0,w-2)})', w-1 if w > 1 else 0)]),
        _unit('bounds', 'cx, cy', [1, 2, 3, 11], [],
              f'Return exactly an object with left, right, top, bottom integer fields. These are the inclusive '
              f'radius {r} square around the center, clipped to columns zero through {w-1} and rows zero '
              f'through {h-1}. Use Math.max and Math.min. This is a candidate search box, not the circle predicate.',
              [(f'bounds({x},{y})', {'left': max(0,x-r), 'right': min(w-1,x+r),
                                    'top': max(0,y-r), 'bottom': min(h-1,y+r)})
               for x,y in ((0,0),(w-1,h-1),(w//2,h//2))]),
        _unit('whitePixels', 'cx, cy', [4, 17], ['bounds', 'inside'],
              f'Store the result of bounds(cx,cy) in a local variable named searchBox. All supplied function names, '
              f'including bounds and inside, are reserved: never reuse them for a variable, parameter or declaration. '
              f'Visit only that inclusive search box with rows outermost and columns '
              f'innermost, both increasing. For each position where inside(x,y,cx,cy) is true, append '
              f'y multiplied by {w} plus x to an array. Return that array. Every index appears once. '
              'Do not scan the complete canvas; do not mutate the canvas or predict future frames.',
              [(f'whitePixels({x},{cy})', _white(x,cy,c)) for x in (0,w-1)] +
              [(f'whitePixels({w//2},{cy}).length', len(_white(w//2,cy,c)))]),
        _unit('clearPixels', 'buffer', [16], [],
              f'buffer is a supplied mutable array-like binary pixel buffer with {w*h} elements. '
              'Call buffer.fill(0) exactly once and return the same buffer object. Use the bulk fill '
              'primitive, not an element-by-element loop. Do not allocate a replacement.',
              [(( '(()=>{let calls=[];let b={fill:function(v){calls.push(v);return this;}};'
                'return [clearPixels(b)===b,calls];})()'), [True,[0]]),
               (f'(()=>{{let b=new Uint8Array({w*h});b.fill(1);return clearPixels(b)===b&&b.every(v=>v===0);}})()', True)]),
        _unit('drawPixels', 'buffer, cx, cy', [17, 30], ['whitePixels'],
              'Call whitePixels(cx,cy), then use a traditional for loop or for of loop to set each returned '
              'buffer index to one. Return the same buffer. Do not clear, replace, resize or allocate the '
              'buffer; do not alter pixels not listed by whitePixels. The caller clears first.',
              [((f'(()=>{{let b=new Uint8Array({w*h});let same=drawPixels(b,{x},{cy})===b;'
                'let lit=[];for(let i=0;i<b.length;i++)if(b[i]===1)lit.push(i);'
                'return {same,lit,binary:b.every(v=>v===0||v===1)};})()'),
                {'same':True,'lit':_white(x,cy,c),'binary':True}) for x in (0,)]),
    ]
    # Full deterministic prior canvas: drawing must preserve every unrelated pixel.
    preservation = (f'(()=>{{let b=new Uint8Array({w*h});for(let i=0;i<b.length;i++)b[i]=i%2;'
                    f'let same=drawPixels(b,{w-1},{cy})===b;for(let i=0;i<b.length;i++){{'
                    f'let x=i%{w}-{w-1},y=Math.floor(i/{w})-{cy};'
                    f'if(b[i]!==((x*x+y*y<={r*r})?1:i%2))return false;}}'
                    f'return same&&b.length==={w*h};}})()')
    units[-1]['examples'].append((preservation, 'true'))
    return units


def _obligations(statements, units):
    result = []
    for stmt in statements:
        index = stmt['index']
        involved = [u['name'] for u in units if index in u['clauses']]
        physical = index in (24,25,26,27,28,29,32,33,34)
        host = physical or index in (1,2,3,4,5,6,7,8,9,10,18,19,20,21,30,31)
        result.append({'statement':index,'label':stmt['label'],'text':stmt['text'],
                       'line':stmt['line'],'col':stmt['col'],'end_line':stmt['end_line'],'end_col':stmt['end_col'],
                       'model_units':involved,'host_required':host,
                       'category':'physical_host' if physical else 'software_host' if host else
                                  'model_behavior' if involved else 'definition',
                       'status':'physical_unverified' if physical else 'not_run',
                       'software_checks_are_not_physical_proof':True})
    return result


def compile_source(text, *, retries=2, max_calls=64, budget=12000, artifacts=None):
    retries = E._int_option('retries', retries, E.RETRIES)
    max_calls = E._int_option('max_calls', max_calls, E.MAX_CALLS)
    budget = E._int_option('budget', budget, E.BUDGET)
    statements, config = parse_source(text)
    units = _units(config)
    shared = (f'The declared canvas is {config["width"]} columns by {config["height"]} rows; '
              f'indices are zero based, the vertical center is {config["fixed_y"]}, and the radius is '
              f'{config["radius"]}. A supplied binary buffer has {config["count"]} entries in row-major '
              'order: zero means black, one means white. RGB conversion, visible presentation and timing '
              'belong to a separate host obligation and are not part of these pure computational units. '
              + SUBSET)
    sheet = ['# implementation.js', 'Model construction from the exact labelled English document.',
             '## Shared', shared]
    for unit in units:
        sheet += ['## Unit `' + unit['name'] + '(' + unit['args'] + ')`']
        if unit['uses']:
            sheet += ['Uses: ' + ', '.join('`' + name + '`' for name in unit['uses'])]
        sheet += [statements[i-1]['text'] for i in unit['clauses']]
        sheet += ['\nGenerated interface: ' + unit['instruction'], 'Examples:']
        sheet += ['    ' + call + ' ==> ' + expected for call, expected in unit['examples']]
    sheet += ['## Assemble `implementation.js`', '    /*UNITS*/']
    sheet_text = '\n'.join(sheet) + '\n'
    plan = CONTRACTS.plan(SP.parse(sheet_text))
    declaration_contracts = {row['id']: {'version':1,'exports':{name:'function' for name in row['exports']}}
                             for row in plan['units']}
    compiled = BUILD.compile_cards(sheet_text, None, inherit_applicators=True, samples=1, rounds=1,
                                   retries=retries, budget=budget, declaration_contracts=declaration_contracts, artifacts=artifacts)
    vm = CHECKS.lower(compiled['source'], compiled['plan'], config=config,
                      reused_ids=[ident for ident, decision in compiled['reuse'].items() if decision['reusable']])
    obligations = _obligations(statements, units)
    presentation = {'kind':'binary-pixel-program','version':1,'width':config['width'],'height':config['height'],
                    'radius':config['radius'],'center_y':config['fixed_y'],'initial_x':config['initial_x'],
                    'delay_seconds':{'numerator':config['delay_numerator'],'denominator':config['delay_denominator']},
                    'min_delay_ms':1000*config['delay_numerator']/config['delay_denominator'],
                    'implementation_label':'implementation.js',
                    'assets':{role:{key:vm['assets'][role][key] for key in ('sha256','sri')}
                              for role in ('parser','vm','presenter')},
                    'functions':[u['name'] for u in units],
                    'dependencies':{u['name']:u['uses'] for u in units},
                    'buffer':{'format':'binary-row-major','off':0,'on':1,'count':config['count']},
                    'color':{'black':[0,0,0],'white':[255,255,255],'alpha':255},
                    'sequence':['compute_column','clear','draw','present','presentation_opportunity','delay'],
                    'future_frame_precomputation':False,'clause_obligations':obligations,
                    'physical_status':'unverified','software_checks_are_not_physical_proof':True}
    lines = vm['source'].splitlines()
    literal = L.literal(S.from_json(presentation))
    preview = f'whitePixels({config["initial_x"]},{config["fixed_y"]})'
    lines += ['let pixel_initial_preview = js_run(spec_output, ' + L.literal(S.from_json(preview)) + ').',
              'show pixel_initial_preview as \"Initial frame indices only; not playback evidence\".',
              'let pixel_presentation = ' + literal + '.', 'show pixel_presentation.']
    presentation_line = len(lines) - 1
    source_map = []
    metadata = []
    plan_units = {row['id']: row for row in compiled['plan']['units']}
    gate_indices = {plan_units[ident]['binding']: index
                    for index, ident in enumerate(compiled['plan']['order'])}
    plan_bindings = {row['binding']: row for row in compiled['plan']['units']}
    for unit in units:
        binding = 'unit_' + unit['name']
        ident = plan_bindings[binding]['id']
        reused = compiled['reuse'][ident]['reusable']
        token = (artifacts or {}).get(ident) if reused else None
        unit_index = gate_indices[binding]
        found = []
        for number, line in enumerate(lines,1):
            if line.startswith(('ask ' + binding + ':',
                                'let ' + binding + ' =',
                                'let test_' + unit['name'] + ' =',
                                'let declarations_' + binding + ' =',
                                'ensure test_' + unit['name'] + '.',
                                'assert test_' + unit['name'] + '.',
                                'ensure declarations_' + binding + '.',
                                'assert declarations_' + binding + '.',
                                'let assembly_check_' + str(unit_index) + ' =',
                                'assert assembly_check_' + str(unit_index) + '.',
                                'let output_check_' + str(unit_index) + ' =',
                                'assert output_check_' + str(unit_index) + '.')):
                found.append(number)
        unit_gate = vm['gates'][unit['name']]
        found.extend([unit_gate['check_line'],unit_gate['guard_line']])
        found = sorted(set(found))
        for index in unit['clauses']:
            statements[index-1]['native_lines'].extend(found)
        metadata.append({'name':unit['name'],'binding':binding,'clauses':unit['clauses'],
                         'uses':unit['uses'],'native_lines':found,'examples':len(unit['examples']),
                         'binding_kind':'let' if reused else 'ask',
                         'acquisition':'reused_artifact' if reused else 'model_request',
                         'artifact_sha256':token['sha256'] if token else None,
                         'code_sha256':token['code_sha256'] if token else None})
    assembly_gate = vm['gates']['assembly']
    for index in {index for unit in units for index in unit['clauses']}:
        statements[index-1]['native_lines'].extend([assembly_gate['check_line'],assembly_gate['guard_line']])
    for stmt in statements:
        stmt['native_lines'] = sorted({*stmt['native_lines'],presentation_line,presentation_line+1})
        for number in stmt['native_lines']:
            source_map.append({'native_line':number,'line':stmt['line'],'col':stmt['col'],
                               'statement':stmt['index']})
    source = '\n'.join(lines) + '\n'
    if len(source) > S.MAX_SOURCE:
        raise _error('The generated task-card program exceeds the native source bound.', code='ENG_LIMIT')
    checked = S.check(source, execution_profile='verified')
    if not checked['ok']:
        raise _error('Generated task-card program refused: ' + checked['errors'][0]['message'])
    options = {**compiled['options'],'context':'none','determine':False,'solve':False,
               'constructor':'off','side_effects':False,'max_calls':max_calls}
    return {'version':VERSION,'source_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source':source,'options':options,'inputs':vm['inputs'],'statements':statements,'source_map':source_map,
            'names':{u['name']:'unit_'+u['name'] for u in units},'presentation':presentation,
            'pixel_build':{'version':VERSION,'units':metadata,'config':config,'sheet':sheet_text,
                           'kept':compiled['kept'],'reuse':compiled['reuse'],
                           'client_vm':{'version':CHECKS.VERSION,'gates':vm['gates'],'assets':vm['assets']},
                           'plan':compiled['plan'],'runtime':compiled['runtime'],
                           'candidate_bodies':'retained_artifact_bodies_only' if compiled['kept'] else 'not_supplied','unmapped_statements':[],
                           'check_scope':'finite_software_checks_not_physical_guarantees'}}


# Exact owner-provided source; the parser retains its original text and labels.
EXAMPLE = 'STATEMENT ZERO ONE: A display canvas is defined as a two-dimensional grid composed of eight hundred columns and six hundred rows of individual picture elements.\n\nSTATEMENT ZERO TWO: The columns are ordered horizontally from left to right, indexed consecutively starting at zero for the leftmost column and ending at seven hundred ninety-nine for the rightmost column.\n\nSTATEMENT ZERO THREE: The rows are ordered vertically from top to bottom, indexed consecutively starting at zero for the topmost row and ending at five hundred ninety-nine for the bottommost row.\n\nSTATEMENT ZERO FOUR: Every individual picture element on the canvas is uniquely identified by an ordered pair consisting of its horizontal column index and its vertical row index.\n\nSTATEMENT ZERO FIVE: The total number of picture elements constituting the canvas is four hundred eighty thousand, calculated as eight hundred multiplied by six hundred.\n\nSTATEMENT ZERO SIX: Every picture element possesses three independent primary color channels: a red channel, a green channel, and a blue channel.\n\nSTATEMENT ZERO SEVEN: Each primary color channel is capable of holding an integer intensity level ranging from a minimum of zero up to a maximum of two hundred fifty-five.\n\nSTATEMENT ZERO EIGHT: The color black is defined as the state wherein the red channel is zero, the green channel is zero, and the blue channel is zero.\n\nSTATEMENT ZERO NINE: The color white is defined as the state wherein the red channel is two hundred fifty-five, the green channel is two hundred fifty-five, and the blue channel is two hundred fifty-five.\n\nSTATEMENT TEN: Under the law of non-contradiction, an individual picture element at any single moment must be rendered exclusively in the black state or exclusively in the white state, and cannot exist in both states simultaneously, nor in any intermediate state.\n\nSTATEMENT ELEVEN: A solid circular dot is defined by a horizontal center column index, a vertical center row index, and an invariant boundary radius of five units.\n\nSTATEMENT TWELVE: For any given picture element, the horizontal difference is defined as the element column index minus the center column index.\n\nSTATEMENT THIRTEEN: For any given picture element, the vertical difference is defined as the element row index minus the center row index.\n\nSTATEMENT FOURTEEN: For any given picture element, the squared separation is defined as the horizontal difference multiplied by itself added to the vertical difference multiplied by itself.\n\nSTATEMENT FIFTEEN: A picture element belongs to the interior of the circular dot if and only if its squared separation from the center is less than or equal to twenty-five.\n\nSTATEMENT SIXTEEN: Setting the canvas to an empty background requires assigning every one of the four hundred eighty thousand picture elements to the black state.\n\nSTATEMENT SEVENTEEN: Drawing the circular dot requires assigning every picture element belonging to the interior of the dot to the white state.\n\nSTATEMENT EIGHTEEN: The progression of execution is partitioned into an infinite succession of discrete temporal frames, beginning at an initial frame and advancing frame by frame without omission.\n\nSTATEMENT NINETEEN: For the initial frame, the horizontal center column index of the circular dot is set to zero.\n\nSTATEMENT TWENTY: For the initial frame, the vertical center row index of the circular dot is set to three hundred.\n\nSTATEMENT TWENTY-ONE: Across every frame of execution without exception, the vertical center row index remains fixed at three hundred, guaranteeing that vertical displacement is zero.\n\nSTATEMENT TWENTY-TWO: If the horizontal center column index of the current frame is seven hundred ninety-nine, the horizontal center column index for the immediately subsequent frame is assigned zero.\n\nSTATEMENT TWENTY-THREE: If the horizontal center column index of the current frame is strictly less than seven hundred ninety-nine, the horizontal center column index for the immediately subsequent frame is assigned the current horizontal center column index plus one.\n\nSTATEMENT TWENTY-FOUR: Execution of the program requires initializing an active, visible graphical presentation window on the operating host system.\n\nSTATEMENT TWENTY-FIVE: The viewport of the visible graphical presentation window must measure exactly eight hundred physical display pixels in horizontal width and six hundred physical display pixels in vertical height.\n\nSTATEMENT TWENTY-SIX: The graphical presentation window must be registered with the host operating system display server so that its pixel buffer is presented visibly on an attached physical monitor.\n\nSTATEMENT TWENTY-SEVEN: Each picture element of the canvas grid corresponds in a direct, one-to-one relationship with the physical screen pixel sharing the identical column and row coordinates within the visible window.\n\nSTATEMENT TWENTY-EIGHT: Assigning a picture element to the white state requires emitting physical light from the corresponding screen pixel by driving its hardware red, green, and blue components to maximum intensity.\n\nSTATEMENT TWENTY-NINE: Assigning a picture element to the black state requires emitting no physical light from the corresponding screen pixel by driving its hardware red, green, and blue components to minimum zero intensity.\n\nSTATEMENT THIRTY: In each frame, updating the state consists of performing the following distinct actions in strict sequential order: first, computing the horizontal center column index for the frame; second, clearing the entire canvas to the black state; third, setting all elements satisfying the interior dot condition to the white state.\n\nSTATEMENT THIRTY-ONE: Immediately following the third step of statement thirty, the memory buffer containing the canvas picture elements must be copied directly to the active visible graphical presentation window.\n\nSTATEMENT THIRTY-TWO: The window presentation operation must execute a complete buffer swap or refresh call, forcing the rendered frame into visible emission on the physical display before any subsequent frame calculation commences.\n\nSTATEMENT THIRTY-THREE: A hardware timer delay of one sixtieth of a second must elapse between the presentation of the current frame and the processing of the subsequent frame to constrain playback to a steady, observable speed.\n\nSTATEMENT THIRTY-FOUR: Continuous cycling through statements thirty, thirty-one, thirty-two, and thirty-three forces the visible emission of an isolated white circular spot translating continuously from left to right across a black field on a physical display monitor.\n'

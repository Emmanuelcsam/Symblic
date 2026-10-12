"""MICA demo fixtures: seeded arithmetic/collections and strict-JSON-parser tasks with stdlib oracles.

These are development fixtures for bench.py, not a held-out measure of ability. Depends on contracts.py.

Details
    Deterministic public requests and evaluator-only, stdlib-oracle demo cases.

    These fixtures are demonstrations, not a held-out measure of broad ability. Seeded
    case generation is reproducible; it does not make repeated trials independent.
    No implementation/reference answer is sent to the construction runner.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import math
import random
from collections import Counter
from pathlib import Path

from symblic.mica import contracts as C

VERSION = 1
SAFE = 9007199254740991


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def _test(requirements, call, expected):
    return {'requirement_ids': requirements, 'call': call, 'expected': _json(expected)}


def _request(objective, requirements, exports, tests, budget):
    return C.normalize_request({'version': 1, 'language': 'javascript', 'objective': objective,
        'requirements': [{'id': key, 'text': text, 'acceptance': 'TESTED'} for key, text in requirements],
        'exports': [{'name': name, 'signature': signature} for name, signature in exports],
        'tests': tests, 'allowed_outputs': ['result.js'], 'budget': budget, 'assumptions': []})


def arithmetic_collections(*, seed=7183, generated=12, budget=None):
    """Five reusable arithmetic/collection units plus their integrating summary."""
    if type(generated) is not int or not 0 <= generated <= 20:
        raise ValueError('generated must be 0..20')
    budget = C._budget(budget or {})
    requirements = [
        ('clamp', 'clamp(x,lo,hi) returns min(hi,max(lo,x)); finite numeric inputs with lo<=hi.'),
        ('sum', 'sum(values) sums finite numeric values in input order; empty array returns 0; never mutate input.'),
        ('mean', 'mean(values) returns sum(values)/values.length or null for empty; never mutate input.'),
        ('histogram', 'histogram(values) counts String(value) keys into an own-key object for string or integer values, including __proto__ and constructor; never mutate input.'),
        ('moving', 'movingAverage(values,width) returns means of each consecutive full-width window, width a positive integer; width>length returns []; never mutate input.'),
        ('summary', 'summarize(values) for integer arrays returns exactly {count,total,mean,min,max,histogram}; min/max/mean null when empty, total zero, histogram from histogram(values); never mutate input.')]
    exports = [(n, s) for n, s in [('clamp', 'clamp(x,lo,hi)'), ('sum', 'sum(values)'),
        ('mean', 'mean(values)'), ('histogram', 'histogram(values)'),
        ('movingAverage', 'movingAverage(values,width)'), ('summarize', 'summarize(values)')]]
    public = [_test(['clamp'], 'clamp(12,0,10)', 10), _test(['sum'], 'sum([1,2,3])', 6),
        _test(['mean'], 'mean([])', None), _test(['histogram'], 'histogram(["a","b","a"])', {'a': 2, 'b': 1}),
        _test(['moving'], 'movingAverage([1,2,3,4],2)', [1.5, 2.5, 3.5]),
        _test(['summary'], 'summarize([1,2,2])', {'count': 3, 'total': 5, 'mean': 5/3,
             'min': 1, 'max': 2, 'histogram': {'1': 1, '2': 2}})]
    request = _request('Build a small JavaScript arithmetic and collections library with reusable units and an integrating summary.',
                       requirements, exports, public, budget)
    hidden = [['clamp(-12,-3,4)', '-3'], ['clamp(2,2,2)', '2'], ['sum([])', '0'],
              ['mean([0,-4,8])', _json(4/3)], ['histogram(["__proto__","constructor","__proto__",""])',
                _json({'__proto__': 2, 'constructor': 1, '': 1})], ['movingAverage([1,2],3)', '[]']]
    rng = random.Random(seed)
    arrays = [[], [0], [-2, -2, 4]] + [[rng.randint(-30, 30) for _ in range(rng.randint(0, 16))]
                                        for _ in range(generated)]
    for values in arrays:
        histogram = dict(Counter(str(v) for v in values))
        total = sum(values)
        mean = total / len(values) if values else None
        summary = {'count': len(values), 'total': total, 'mean': mean,
                   'min': min(values) if values else None, 'max': max(values) if values else None,
                   'histogram': histogram}
        literal = _json(values)
        width = rng.randint(1, 5)
        rolling = [sum(values[i:i+width])/width for i in range(len(values)-width+1)]
        hidden += [[f'summarize({literal})', _json(summary)],
                   [f'movingAverage({literal},{width})', _json(rolling)],
                   [f'(()=>{{const x={literal};sum(x);mean(x);histogram(x);movingAverage(x,2);summarize(x);return x}})()', literal]]
    return {'id': 'arithmetic_collections', 'family': 'mica_demo_arithmetic_v1', 'split': 'heldout',
            'request': request, 'hidden_tests': hidden}


def strict_json_oracle(text):
    """Independent stdlib JSON parser plus the explicitly declared bounded policy."""
    if type(text) is not str or len(text.encode('utf-16-le', errors='surrogatepass')) // 2 > 65536:
        raise ValueError('input')
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('duplicate')
            out[key] = value
        return out
    def number(raw):
        value = float(raw) if any(c in raw for c in '.eE') else int(raw)
        if not math.isfinite(value) or abs(value) > SAFE:
            raise ValueError('range')
        return value
    def constant(_):
        raise ValueError('constant')
    value = json.loads(text, object_pairs_hook=pairs, parse_int=number,
                       parse_float=number, parse_constant=constant)
    def depth(item, containers=0):
        if isinstance(item, (list, dict)):
            containers += 1
            if containers > 32:
                raise ValueError('depth')
            for child in item.values() if isinstance(item, dict) else item:
                depth(child, containers)
    depth(value)
    return value


def _parse_call(text):
    return f'parseJSON({_json(text)})'


def _reject_call(text):
    return f'(()=>{{try{{parseJSON({_json(text)});return false}}catch(e){{return e instanceof Error}}}})()'


def strict_json(*, seed=991, generated=16, invalid_generated=12, budget=None):
    """Behaviorally strict parser. Does not claim proof of a JSON.parse/API ban."""
    if (type(generated) is not int or not 0 <= generated <= 32
            or type(invalid_generated) is not int or not 0 <= invalid_generated <= 32):
        raise ValueError('generated and invalid_generated must be 0..32')
    requirements = [
        ('grammar', 'parseJSON(text) accepts exactly one JSON value with optional JSON whitespace (space, tab, LF, CR); rejects malformed syntax, trailing input, comments, unquoted keys, trailing commas, leading zeroes, NaN/Infinity and non-string inputs by throwing an Error.'),
        ('strings', 'Decode all JSON string escapes and four-hex-digit Unicode escapes using JavaScript UTF-16 semantics (including surrogate pairs and individual escaped surrogate code units); reject raw control characters and malformed escapes.'),
        ('collections', 'Parse arrays and objects recursively; reject duplicate object keys after escape decoding; preserve keys including __proto__ and constructor as own enumerable data properties.'),
        ('numbers', 'Parse JSON number grammar using IEEE-754 semantics; reject non-finite parsed results or absolute value greater than 9007199254740991. Negative zero is permitted.'),
        ('bounds', 'Accept input strings of at most 65536 UTF-16 code units and container nesting depth at most 32; count each array/object as one container level; reject larger input or depth by throwing an Error.')]
    public = [_test(['grammar'], _parse_call(' true \n'), True),
              _test(['grammar'], _reject_call('[1,]'), True),
              _test(['strings'], _parse_call('"a\\n\\u0041"'), 'a\nA'),
              _test(['collections'], _parse_call('{"a":[1,null,false]}'), {'a': [1, None, False]}),
              _test(['collections'], _reject_call('{"x":1,"x":2}'), True),
              _test(['numbers'], _parse_call('-1.25e2'), -125),
              _test(['numbers'], _reject_call('1e309'), True),
              _test(['bounds'], _reject_call('['*33 + '0' + ']'*33), True)]
    request = _request('Implement parseJSON(text), a strict bounded JSON parser with explicit duplicate-key and numeric-range policy. Return plain JavaScript source defining parseJSON.',
                       requirements, [('parseJSON', 'parseJSON(text)')], public, C._budget(budget or {}))
    valid = ['null', 'false', '-0', '0.125', '1e-8', '-9E+3', str(SAFE), str(-SAFE),
             '"\\\"\\\\\\/\\b\\f\\n\\r\\t"', '"\\uD83D\\uDE03"', '"\\uD800"',
             '{"__proto__":{"safe":true},"constructor":2}', '[{},[],[false,null,{"x":"y"}]]',
             '['*32 + '0' + ']'*32, ' \t\r\n {"a":1} \t\r\n']
    invalid = ['', ' ', '+1', '.5', '1.', '01', '-01', '1e', '1e+', '--1', '[1,,2]', '{"a":}',
               '{a:1}', '{"a":1,}', '/*x*/null', 'true false', 'undefined', 'NaN', 'Infinity',
               '"\\x20"', '"\\u12G4"', '"\\u123"', '"unterminated', '"raw\nline"',
               '{"a":1,"\\u0061":2}', '{"x":{"y":1,"y":2}}', str(SAFE+1), '1e100',
               '['*33 + '0' + ']'*33, '\u00a0null', 'null\u000b']
    rng = random.Random(seed)
    def value(level):
        kind = rng.randrange(6 if level < 3 else 4)
        if kind == 0:
            return None
        if kind == 1:
            return bool(rng.randrange(2))
        if kind == 2:
            return rng.randint(-50000, 50000) / (10 ** rng.randrange(3))
        if kind == 3:
            return ''.join(rng.choice('aZ09é\\\"\n\t') for _ in range(rng.randrange(10)))
        if kind == 4:
            return [value(level+1) for _ in range(rng.randrange(4))]
        return {f'k{i}': value(level+1) for i in range(rng.randrange(4))}
    valid += [_json(value(0)) for _ in range(generated)]
    # Invalid mutations are independently checked by the oracle before freezing;
    # append an unconditionally illegal suffix, never assume a mutation is invalid.
    invalid += [_json(value(0)) + rng.choice(['#', ',', ';', ' true']) for _ in range(invalid_generated)]
    hidden = [[_parse_call(text), _json(strict_json_oracle(text))] for text in valid]
    for text in invalid:
        try:
            strict_json_oracle(text)
        except (ValueError, OverflowError, RecursionError):
            hidden.append([_reject_call(text), 'true'])
        else:
            raise AssertionError('invalid fixture accepted by oracle')
    hidden += [['(()=>{try{parseJSON(1);return false}catch(e){return e instanceof Error}})()', 'true'],
               ['(()=>{try{parseJSON(" ".repeat(65533)+"null");return false}catch(e){return e instanceof Error}})()', 'true'],
               ['parseJSON(" ".repeat(65532)+"null")', 'null']]
    return {'id': 'strict_json', 'family': 'mica_demo_json_parser_v1', 'split': 'heldout',
            'request': request, 'hidden_tests': hidden}


def write_demo_files(directory, *, budget=None):
    """Host-only fixture files; only *.request.json belongs in provider context."""
    path = Path(directory)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for fixture in (arithmetic_collections(budget=budget), strict_json(budget=budget)):
        for suffix, payload in (('request', fixture['request']), ('fixture', fixture)):
            target = path / f'{fixture["id"]}.{suffix}.json'
            target.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + '\n')
            target.chmod(0o600)

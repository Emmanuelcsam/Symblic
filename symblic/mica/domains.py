"""Finite JSON domains for check packs: exact, size-checked expansion of declared value sets.

Depends on: checkpack.py. Used by checkpack.py. Pure.

Details
    Pure exact finite JSON domain expansion for caller-bound check packs.

    This is data enumeration, not an expression interpreter, oracle or executor.
    Every product is fully sized before any product values are materialized. Literal
    admission/lowering remains the existing check-pack implementation.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from decimal import Decimal
import copy
import itertools

from symblic.mica import checkpack as K

VERSION = 1
MAX_RECIPE_DEPTH = 8
MAX_RECIPE_NODES = 128
MAX_ARRAY_LENGTH = 16
SCOPE = 'all_values_in_declared_finite_domain_only'


def schema():
    """Recursive JSON-schema guide; the bounded native normalizer is authoritative."""
    def obj(properties):
        return {'type': 'object', 'properties': properties,
                'required': list(properties), 'additionalProperties': False}
    integer = {'type': 'integer', 'minimum': -K.MAX_SAFE_INTEGER, 'maximum': K.MAX_SAFE_INTEGER}
    return {'oneOf': [
        obj({'kind': {'const': 'enum'}, 'values_json': {'type': 'array', 'minItems': 1,
            'maxItems': K.MAX_CASES, 'items': {'type': 'string', 'minLength': 1, 'maxLength': K.MAX_LITERAL}}}),
        obj({'kind': {'const': 'integer_range'}, 'min': integer, 'max': integer,
             'step': {'type': 'integer', 'minimum': 1, 'maximum': K.MAX_SAFE_INTEGER}}),
        obj({'kind': {'const': 'array'}, 'elements': {'$ref': '#/$defs/finite_domain'},
             'lengths': {'type': 'array', 'minItems': 1, 'maxItems': MAX_ARRAY_LENGTH + 1,
                         'uniqueItems': True, 'items': {'type': 'integer', 'minimum': 0,
                                                      'maximum': MAX_ARRAY_LENGTH}}})]}


def _semantic(value):
    """Exact JSON equality key, independent of Decimal precision and rounding."""
    if value is None:
        return ('null',)
    if type(value) is bool:
        return ('boolean', value)
    if type(value) is str:
        return ('string', value)
    if type(value) is Decimal:
        sign, digits, exponent = value.as_tuple()
        digits = list(digits)
        if not any(digits):
            return ('number', 0, (0,), 0)
        while digits[-1] == 0:
            digits.pop(); exponent += 1
        return ('number', sign, tuple(digits), exponent)
    if type(value) is list:
        return ('array', tuple(_semantic(item) for item in value))
    if type(value) is dict:
        return ('object', tuple((key, _semantic(value[key])) for key in sorted(value)))
    K._fail('domain', 'Unsupported finite JSON value.')


def _shape(value):
    if type(value) is list:
        child = [_shape(item) for item in value]
        return 1 + max((d for d, _ in child), default=0), 1 + sum(n for _, n in child)
    if type(value) is dict:
        child = [_shape(item) for item in value.values()]
        return 1 + max((d for d, _ in child), default=0), 1 + len(value) + sum(n for _, n in child)
    return 0, 1


def _metrics(values):
    sizes = [len(raw.encode('utf-8')) for raw in values]
    shapes = [_shape(K._literal(raw)[0]) for raw in values]
    return {'count': len(values), 'bytes': sum(sizes), 'max_chars': max(map(len, values)),
            'max_depth': max(d for d, _ in shapes), 'max_nodes': max(n for _, n in shapes)}


def _plan(domain, limits, depth=0):
    limits['recipe_nodes'] += 1
    if depth > MAX_RECIPE_DEPTH or limits['recipe_nodes'] > MAX_RECIPE_NODES:
        K._fail('domain_limit', 'Finite domain recipe depth/node limit exceeded.')
    if type(domain) is not dict:
        K._fail('domain', 'Finite domain must be a strict object.')
    kind = domain.get('kind')
    if kind == 'enum':
        K._keys(domain, ('kind', 'values_json'))
        values = domain['values_json']
        if type(values) is not list or not 1 <= len(values) <= limits['values']:
            K._fail('domain_limit', 'Finite literal domain is empty or exceeds the remaining case allowance.')
        seen = set()
        for raw in values:
            semantic = _semantic(K._literal(raw)[0])
            if semantic in seen:
                K._fail('domain_duplicate', 'Semantically duplicate JSON domain values would inflate coverage.')
            seen.add(semantic)
        planned = {'kind': kind, 'values': list(values), **_metrics(values)}
    elif kind == 'integer_range':
        K._keys(domain, ('kind', 'min', 'max', 'step'))
        low, high, step = (domain[key] for key in ('min', 'max', 'step'))
        if (any(type(value) is not int for value in (low, high, step)) or
                not -K.MAX_SAFE_INTEGER <= low <= high <= K.MAX_SAFE_INTEGER or
                not 1 <= step <= K.MAX_SAFE_INTEGER):
            K._fail('domain', 'Integer domain needs safe inclusive endpoints and a positive exact step.')
        count = (high - low) // step + 1
        if count > limits['values']:
            K._fail('domain_limit', 'Integer domain exceeds the remaining case allowance.')
        # Only bounded leaf literals are allocated in planning; product arrays are not.
        values = [str(low + index * step) for index in range(count)]
        planned = {'kind': kind, 'values': values, **_metrics(values)}
    elif kind == 'array':
        K._keys(domain, ('kind', 'elements', 'lengths'))
        lengths = domain['lengths']
        if (type(lengths) is not list or not 1 <= len(lengths) <= MAX_ARRAY_LENGTH + 1 or
                any(type(n) is not int or not 0 <= n <= MAX_ARRAY_LENGTH for n in lengths) or
                len(set(lengths)) != len(lengths)):
            K._fail('domain', 'Array lengths must be distinct exact integers from 0 to 16.')
        child = _plan(domain['elements'], limits, depth + 1)
        count = size = 0
        max_chars, max_depth, max_nodes = 0, 0, 0
        for n in lengths:
            combinations = child['count'] ** n
            count += combinations
            if count > limits['values']:
                K._fail('domain_limit', 'Cartesian domain exceeds the remaining case allowance before expansion.')
            size += (2 if n == 0 else
                     n * child['count'] ** (n - 1) * child['bytes'] + combinations * (n + 1))
            max_chars = max(max_chars, 2 if n == 0 else n * child['max_chars'] + n + 1)
            max_depth = max(max_depth, 1 if n == 0 else child['max_depth'] + 1)
            max_nodes = max(max_nodes, 1 + n * child['max_nodes'])
        planned = {'kind': kind, 'child': child, 'lengths': list(lengths), 'count': count,
                   'bytes': size, 'max_chars': max_chars, 'max_depth': max_depth, 'max_nodes': max_nodes}
    else:
        K._fail('domain', 'Unsupported finite domain kind.')
    if (planned['bytes'] > limits['bytes'] or planned['max_chars'] > K.MAX_LITERAL or
            planned['max_depth'] > 16 or planned['max_nodes'] > 4096):
        K._fail('domain_limit', 'Finite domain byte, literal, depth or node allowance exceeded before expansion.')
    return planned


def _materialize(plan):
    if plan['kind'] != 'array':
        return list(plan['values'])
    values = _materialize(plan['child'])
    return ['[' + ','.join(items) + ']' for n in plan['lengths']
            for items in itertools.product(values, repeat=n)]


def expand_domain(domain, *, max_values=K.MAX_CASES, max_bytes=K.MAX_BYTES):
    """Return all literal values after preflight; zero sampling or truncation."""
    if (type(max_values) is not int or not 1 <= max_values <= K.MAX_CASES or
            type(max_bytes) is not int or not 1 <= max_bytes <= K.MAX_BYTES):
        K._fail('domain_limit', 'A positive bounded remaining domain allowance is required.')
    K._bounded(domain)
    plan = _plan(domain, {'values': max_values, 'bytes': max_bytes, 'recipe_nodes': 0})
    values = _materialize(plan)
    if len(values) != plan['count'] or sum(len(raw.encode('utf-8')) for raw in values) != plan['bytes']:
        K._fail('domain_internal', 'Finite expansion disagrees with its preflight accounting.')
    # Final values are re-admitted by K during emission; these are still JSON data.
    return {'version': VERSION, 'scope': SCOPE, 'recipe': copy.deepcopy(domain),
            'cardinality': plan['count'], 'total_utf8_bytes': plan['bytes'],
            'max_value_chars': plan['max_chars'], 'max_value_depth': plan['max_depth'],
            'enumeration': 'declared_enum_order_ascending_integer_range_declared_lengths_lexicographic_product',
            'values_json': values, 'values_sha256': K._hash(values)}

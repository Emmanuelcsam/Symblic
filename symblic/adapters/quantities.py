"""Measured quantities: exact interval arithmetic with SI dimensions and declared units.

    let q = quantity_convert(quantity_measure(1.2, 0.05, "m"), "cm").     # 120 cm plus or minus 5
    show [q.lower, q.upper].                                              # [115, 125]

A quantity is a plain record: a lower and an upper bound (exact rationals), a unit with its seven SI
dimension exponents, and the measurements it depends on. quantity_add, _sub, _mul, _div, _convert and
_compare keep the bounds exact; quantity_status checks a quantity's declared validity and, optionally, the
age of its observation against a time the caller supplies.
Temperatures distinguish points from differences. Bounds are deterministic enclosures, never probabilities;
shared measurement dependencies are retained, and interval arithmetic may overestimate their range. Units and
precision are never inferred: the program declares them. See docs/reference/QUANTITIES.md.

Import is inert. A host explicitly registers the plain-record API with register(kernel); the language exposes
the quantity_* builtins through symblic.kernel.language.ADAPTERS.

Depends on: symblic.kernel.language, symblic.adapters.variational (exact helpers). Used by: the quantity_*
builtins.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import re
from datetime import datetime
from fractions import Fraction
from functools import wraps

from symblic.kernel import language as S
from symblic.adapters import variational as V

VERSION = 1
ARITHMETIC_VERSION = V.VERSION
SCHEMA = 'symblic.quantity.v1'
DIMENSIONS = ('length', 'mass', 'time', 'current', 'temperature', 'amount', 'luminosity')
MAX_EXPONENT = 32
MAX_SOURCES = 32
MAX_TOLERANCES = 32
MAX_TEXT = 256
MAX_BITS = V.MAX_BITS
MAX_WORK = V.MAX_WORK
ZERO = (0,) * 7
TEMPERATURE = (0, 0, 0, 0, 1, 0, 0)
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z', re.ASCII)
_UNIT_FIELDS = {'symbol', 'dimensions', 'scale', 'offset', 'kind', 'definition'}
_FIELDS = {'schema', 'lower', 'upper', 'unit', 'kind', 'sources', 'validity',
           'declared_tolerances', 'provenance'}
_KINDS = {'exact_definition', 'measured_interval', 'derived_exact', 'derived_interval'}
_EXACT = {'exact_definition', 'derived_exact'}


class QuantityError(S.SymblicError):
    """An invalid quantity, incompatible dimension or exhausted local limit."""


def _fail(message, kind='type'):
    raise QuantityError(message, kind=kind)


def _fields(value, fields, label, *, optional=()):
    if (type(value) is not dict or len(value) > len(fields) + len(optional)
            or any(type(k) is not str for k in value)
            or not fields <= value.keys() or not value.keys() <= fields | set(optional)):
        _fail(label + ' fields do not match the quantity schema')


def _text(value, label):
    if type(value) is not str or not 1 <= len(value) <= MAX_TEXT or any(ord(c) < 32 for c in value):
        _fail(label + ' must be nonempty bounded text without controls')
    try:
        value.encode('utf-8')
    except UnicodeError:
        _fail(label + ' must be valid UTF-8')
    return value


def _sequence(value, maximum, label):
    if type(value) not in (tuple, list) or len(value) > maximum:
        _fail(label + ' exceeds its finite sequence limit')
    return value


def _stamp(value, label):
    if value is None:
        return None
    if type(value) is not str or len(value) != 20 or not _DATE.fullmatch(value):
        _fail(label + ' must be UTC YYYY-MM-DDTHH:MM:SSZ')
    try:
        datetime.strptime(value, '%Y-%m-%dT%H:%M:%S%z')
    except ValueError:
        _fail(label + ' is not a valid calendar timestamp')
    return value


def _cmp(a, b, work):
    value = work.sub(a, b).numerator
    return (value > 0) - (value < 0)


def _digest(value):
    return hashlib.sha256(S.canon_json(value).encode('utf-8')).hexdigest()


def _native(value):
    if type(value) is Fraction:
        return S.norm_num(value)
    if type(value) in (list, tuple):
        return tuple(_native(v) for v in value)
    if type(value) is dict:
        return {key: _native(v) for key, v in value.items()}
    return value


def _bounded(function):
    @wraps(function)
    def invoke(*args, max_bits=MAX_BITS, max_work=MAX_WORK, budget=None, node=None, **kwargs):
        try:
            work = V._Work(1, max_bits, max_work, budget, node)
            return _native(function(*args, work=work, **kwargs))
        except V.VariationalError as exc:
            raise QuantityError(exc.message.replace('quadratic', 'quantity'),
                                exc.line, exc.col, exc.kind) from None
    return invoke


def _definition(symbol, dimensions, scale=1, offset=0, kind='linear', definition='declared exact SI relation'):
    return {'symbol': symbol, 'dimensions': dimensions, 'scale': scale,
            'offset': offset, 'kind': kind, 'definition': definition}


# Exact definitions, not rounded empirical conversions. Case-sensitive symbols.
_CATALOGUE = {'1': _definition('1', ZERO)}
for _i, _symbol in enumerate(('m', 'kg', 's', 'A', 'delta_K', 'mol', 'cd')):
    _dimension = tuple(int(_i == j) for j in range(7))
    _CATALOGUE[_symbol] = _definition(_symbol, _dimension)
for _symbol, _base, _factor in (
        ('cm', 'm', Fraction(1, 100)), ('mm', 'm', Fraction(1, 1000)),
        ('km', 'm', 1000), ('inch', 'm', Fraction(127, 5000)), ('ft', 'm', Fraction(381, 1250)),
        ('g', 'kg', Fraction(1, 1000)), ('mg', 'kg', Fraction(1, 1_000_000)),
        ('lb', 'kg', Fraction(45359237, 100_000_000)), ('min', 's', 60), ('h', 's', 3600)):
    _CATALOGUE[_symbol] = _definition(_symbol, _CATALOGUE[_base]['dimensions'], _factor)
_CATALOGUE.update({
    'K': _definition('K', TEMPERATURE, kind='point'),
    'degC': _definition('degC', TEMPERATURE, offset=Fraction(27315, 100), kind='point'),
    'degF': _definition('degF', TEMPERATURE, Fraction(5, 9), Fraction(45967, 180), kind='point'),
    'delta_degC': _definition('delta_degC', TEMPERATURE),
    'delta_degF': _definition('delta_degF', TEMPERATURE, Fraction(5, 9)),
})
del _i, _symbol, _dimension, _base, _factor


def _unit(value, work):
    work.tick()
    if type(value) is str:
        if value not in _CATALOGUE:
            _fail('unknown unit; supply an explicit exact unit record', 'unit')
        value = _CATALOGUE[value]
    _fields(value, _UNIT_FIELDS, 'unit')
    symbol = _text(value['symbol'], 'unit symbol')
    definition = _text(value['definition'], 'unit definition')
    dimension = _sequence(value['dimensions'], 7, 'dimensions')
    if len(dimension) != 7:
        _fail('dimensions must have seven integer exponents')
    dimension = tuple(S.norm_num(v) if type(v) is Fraction else v for v in dimension)
    for exponent in dimension:
        work.tick()
        if type(exponent) is not int or abs(exponent) > MAX_EXPONENT:
            _fail('dimension exponents must be bounded native integers')
    dimension = tuple(dimension)
    scale, offset = work.scalar(value['scale']), work.scalar(value['offset'])
    if scale.numerator <= 0:
        _fail('unit scale must be positive', 'unit')
    kind = value['kind']
    if type(kind) is not str or kind not in ('linear', 'point'):
        _fail('unit kind must be linear or point', 'unit')
    if kind == 'point' and dimension != TEMPERATURE:
        _fail('affine points currently support temperature only', 'unit')
    if kind == 'linear' and offset:
        _fail('linear and delta units cannot have an offset', 'unit')
    result = _definition(symbol, dimension, scale, offset, kind, definition)
    if symbol in _CATALOGUE:
        standard = _CATALOGUE[symbol]
        if any(result[k] != standard[k] for k in ('dimensions', 'scale', 'offset', 'kind')):
            _fail('a catalogue unit symbol cannot be redefined', 'unit')
    return result


@_bounded
def quantity_unit(symbol, dimensions, scale=1, offset=0, kind='linear',
                  definition='declared exact SI relation', *, work):
    """Declare a positive exact conversion: SI value = scale * value + offset."""
    return _unit(_definition(symbol, dimensions, scale, offset, kind, definition), work)


def _sources(value, work):
    rows = []
    for row in _sequence(value, MAX_SOURCES, 'sources'):
        work.tick()
        _fields(row, {'id', 'version'}, 'source', optional={'observed_at'})
        rows.append({'id': _text(row['id'], 'source id'), 'version': _text(row['version'], 'source version'),
                     'observed_at': _stamp(row.get('observed_at'), 'observed_at')})
    return _unique(rows, MAX_SOURCES, 'sources')


def _unique(rows, maximum, label):
    # All inputs are already bounded, native records before canonical hashing.
    values = {S.canon_json(row): row for row in rows}
    if len(values) > maximum:
        _fail(label + ' union exceeds its finite limit', 'budget')
    return tuple(values[key] for key in sorted(values))


def _validity(value):
    _fields(value, {'from', 'until'}, 'validity')
    start, end = _stamp(value['from'], 'valid from'), _stamp(value['until'], 'valid until')
    if start is not None and end is not None and start > end:
        _fail('declared validity interval is empty', 'domain')
    return {'from': start, 'until': end}


def _metadata(value, work):
    if value is None:
        value = {}
    _fields(value, set(), 'metadata', optional={'sources', 'valid_from', 'valid_until'})
    return _sources(value.get('sources', ()), work), _validity({
        'from': value.get('valid_from'), 'until': value.get('valid_until')})


def _tolerances(value, work):
    result = []
    for item in _sequence(value, MAX_TOLERANCES, 'declared tolerances'):
        work.tick()
        _fields(item, {'nominal', 'absolute', 'unit', 'sources'}, 'declared tolerance')
        absolute = work.scalar(item['absolute'])
        if absolute.numerator < 0:
            _fail('absolute tolerance cannot be negative', 'domain')
        result.append({'nominal': work.scalar(item['nominal']), 'absolute': absolute,
                       'unit': _unit(item['unit'], work), 'sources': _sources(item['sources'], work)})
    return _unique(result, MAX_TOLERANCES, 'declared tolerances')


def _quantity(value, work):
    work.tick()
    _fields(value, _FIELDS, 'quantity')
    if type(value['schema']) is not str or value['schema'] != SCHEMA:
        _fail('quantity schema version does not match', 'version')
    low, high = work.scalar(value['lower']), work.scalar(value['upper'])
    if _cmp(low, high, work) > 0:
        _fail('lower bound exceeds upper bound', 'domain')
    kind = value['kind']
    if type(kind) is not str or kind not in _KINDS:
        _fail('quantity kind is unsupported')
    if kind in _EXACT and low != high:
        _fail('exact definitions must have equal bounds', 'domain')
    provenance = value['provenance']
    _fields(provenance, {'version', 'operation', 'parents', 'independence', 'bounds'}, 'provenance')
    if type(provenance['version']) is not int or provenance['version'] != VERSION:
        _fail('quantity arithmetic version does not match', 'version')
    if provenance['independence'] != 'not_assumed' or provenance['bounds'] != 'conservative':
        _fail('quantity provenance must not claim statistical independence or precision')
    operation = _text(provenance['operation'], 'operation')
    parents = _sequence(provenance['parents'], 2, 'parents')
    if any(type(v) is not str or len(v) != 64 or not _HASH.fullmatch(v) for v in parents):
        _fail('parent identities must be SHA-256 fingerprints')
    tolerances = _tolerances(value['declared_tolerances'], work)
    if kind in _EXACT and tolerances:
        _fail('exact definitions cannot carry measurement tolerance declarations', 'domain')
    return {'schema': SCHEMA, 'lower': low, 'upper': high, 'kind': kind,
            'unit': _unit(value['unit'], work), 'sources': _sources(value['sources'], work),
            'validity': _validity(value['validity']), 'declared_tolerances': tolerances,
            'provenance': {'version': VERSION, 'operation': operation, 'parents': tuple(parents),
                           'independence': 'not_assumed', 'bounds': 'conservative'}}


def _make(low, high, unit, kind, sources, validity, tolerances=(), operation='declare', parents=()):
    return {'schema': SCHEMA, 'lower': low, 'upper': high, 'unit': unit, 'kind': kind,
            'sources': sources, 'validity': validity, 'declared_tolerances': tolerances,
            'provenance': {'version': VERSION, 'operation': operation, 'parents': parents,
                           'independence': 'not_assumed', 'bounds': 'conservative'}}


@_bounded
def quantity_exact(value, unit, metadata=None, *, work):
    """Declare an exact definition, not a claim that an empirical measurement is exact."""
    value, unit = work.scalar(value), _unit(unit, work)
    sources, validity = _metadata(metadata, work)
    return _make(value, value, unit, 'exact_definition', sources, validity)


@_bounded
def quantity_interval(lower, upper, unit, metadata=None, *, work):
    """Declare a closed measured interval, with no distribution or confidence level."""
    low, high, unit = work.scalar(lower), work.scalar(upper), _unit(unit, work)
    if _cmp(low, high, work) > 0:
        _fail('lower bound exceeds upper bound', 'domain')
    sources, validity = _metadata(metadata, work)
    return _make(low, high, unit, 'measured_interval', sources, validity)


@_bounded
def quantity_measure(value, tolerance, unit, metadata=None, *, work):
    """Declare value +/- absolute tolerance in the named unit; retain that declaration."""
    value, tolerance, unit = work.scalar(value), work.scalar(tolerance), _unit(unit, work)
    if tolerance.numerator < 0:
        _fail('absolute tolerance cannot be negative', 'domain')
    sources, validity = _metadata(metadata, work)
    declaration = {'nominal': value, 'absolute': tolerance, 'unit': unit, 'sources': sources}
    return _make(work.sub(value, tolerance), work.add(value, tolerance), unit,
                 'measured_interval', sources, validity, (declaration,))


def _canonical(quantity, work):
    unit = quantity['unit']
    return tuple(work.add(work.mul(quantity[key], unit['scale']), unit['offset']) for key in ('lower', 'upper'))


def _compatible(left, right, *, kind=False):
    if left['dimensions'] != right['dimensions']:
        _fail('incompatible quantity dimensions', 'dimension')
    if kind and left['kind'] != right['kind']:
        _fail('temperature points and differences are distinct quantities', 'unit')


def _in_unit(low, high, unit, work):
    return tuple(work.div(work.sub(v, unit['offset']), unit['scale']) for v in (low, high))


def _combine(left, right, low, high, unit, operation, work):
    sources = _unique(left['sources'] + right['sources'], MAX_SOURCES, 'sources')
    tolerances = _unique(left['declared_tolerances'] + right['declared_tolerances'],
                         MAX_TOLERANCES, 'declared tolerances')
    starts = [q['validity']['from'] for q in (left, right) if q['validity']['from'] is not None]
    ends = [q['validity']['until'] for q in (left, right) if q['validity']['until'] is not None]
    validity = _validity({'from': max(starts) if starts else None, 'until': min(ends) if ends else None})
    low, high = _in_unit(low, high, unit, work)
    kind = 'derived_exact' if left['kind'] in _EXACT and right['kind'] in _EXACT else 'derived_interval'
    return _make(low, high, unit, kind, sources, validity, tolerances,
                 operation, (_digest(left), _digest(right)))


@_bounded
def quantity_convert(quantity, unit, *, work):
    """Convert enclosures exactly; original tolerance declarations retain original units."""
    quantity, unit = _quantity(quantity, work), _unit(unit, work)
    _compatible(quantity['unit'], unit, kind=True)
    low, high = _in_unit(*_canonical(quantity, work), unit, work)
    return _make(low, high, unit, quantity['kind'], quantity['sources'], quantity['validity'],
                 quantity['declared_tolerances'], 'convert', (_digest(quantity),))


def _delta(unit, work):
    if unit['symbol'] in ('K', 'degC', 'degF'):
        return _unit('delta_' + unit['symbol'], work)
    # Generated labels remain bounded even for a maximal caller-supplied symbol.
    return _unit(_definition('delta:' + _digest(unit)[:16], TEMPERATURE, unit['scale']), work)


def _add_sub(left, right, subtract, work):
    left, right = _quantity(left, work), _quantity(right, work)
    a, b = left['unit'], right['unit']
    _compatible(a, b)
    ap, bp = a['kind'] == 'point', b['kind'] == 'point'
    if not subtract and ap and bp:
        _fail('cannot add two absolute temperature points; add a temperature difference', 'unit')
    if subtract and not ap and bp:
        _fail('cannot subtract an absolute temperature point from a difference', 'unit')
    unit = _delta(a, work) if subtract and ap and bp else b if bp and not subtract else a
    al, ah = _canonical(left, work)
    bl, bh = _canonical(right, work)
    low, high = (work.sub(al, bh), work.sub(ah, bl)) if subtract else (work.add(al, bl), work.add(ah, bh))
    return _combine(left, right, low, high, unit, 'subtract' if subtract else 'add', work)


@_bounded
def quantity_add(left, right, *, work):
    return _add_sub(left, right, False, work)


@_bounded
def quantity_sub(left, right, *, work):
    return _add_sub(left, right, True, work)


def _product_unit(a, b, divide, work):
    dimensions = tuple(x - y if divide else x + y for x, y in zip(a['dimensions'], b['dimensions']))
    for symbol, unit in _CATALOGUE.items():
        if unit['dimensions'] == dimensions and unit['kind'] == 'linear' and unit['scale'] == 1:
            return _unit(symbol, work)
    label = 'SI[' + ','.join(str(n) for n in dimensions) + ']'
    return _unit(_definition(label, dimensions), work)


def _mul_div(left, right, divide, work):
    left, right = _quantity(left, work), _quantity(right, work)
    if left['unit']['kind'] == 'point' or right['unit']['kind'] == 'point':
        _fail('products of absolute temperature points are unsupported; use an explicit domain model', 'unit')
    unit = _product_unit(left['unit'], right['unit'], divide, work)
    al, ah = _canonical(left, work)
    bl, bh = _canonical(right, work)
    if divide and bl.numerator <= 0 <= bh.numerator:
        _fail('denominator interval contains zero; no finite quotient enclosure', 'domain')
    operation = work.div if divide else work.mul
    values = [operation(a, b) for a in (al, ah) for b in (bl, bh)]
    low = high = values[0]
    for value in values[1:]:
        if _cmp(value, low, work) < 0:
            low = value
        if _cmp(value, high, work) > 0:
            high = value
    return _combine(left, right, low, high, unit, 'divide' if divide else 'multiply', work)


@_bounded
def quantity_mul(left, right, *, work):
    return _mul_div(left, right, False, work)


@_bounded
def quantity_div(left, right, *, work):
    return _mul_div(left, right, True, work)


@_bounded
def quantity_compare(left, right, relation='lt', *, work):
    """Three-valued comparison over all values in each enclosure; no rounding."""
    left, right = _quantity(left, work), _quantity(right, work)
    _compatible(left['unit'], right['unit'], kind=True)
    if type(relation) is not str or relation not in ('lt', 'le', 'gt', 'ge', 'eq', 'ne'):
        _fail('comparison relation must be lt, le, gt, ge, eq or ne')
    al, ah = _canonical(left, work)
    bl, bh = _canonical(right, work)
    if relation in ('gt', 'ge'):
        al, ah, bl, bh = bl, bh, al, ah
    upper_lower, lower_upper = _cmp(ah, bl, work), _cmp(al, bh, work)
    if relation in ('lt', 'gt'):
        yes, no = upper_lower < 0, lower_upper >= 0
    elif relation in ('le', 'ge'):
        yes, no = upper_lower <= 0, lower_upper > 0
    else:
        yes, no = al == ah == bl == bh, upper_lower < 0 or lower_upper > 0
        if relation == 'ne':
            yes, no = no, yes
    shared = sorted({row['id'] for row in left['sources']} & {row['id'] for row in right['sources']})
    return {'relation': relation, 'outcome': 'true' if yes else 'false' if no else 'indeterminate',
            'scope': 'declared_bounds', 'shared_sources': tuple(shared), 'independence': 'not_assumed',
            'parents': (_digest(left), _digest(right)), 'version': VERSION}


@_bounded
def quantity_status(quantity, evaluated_at, max_age_seconds=None, *, work):
    """Check declared validity and optional observation age using only caller time."""
    quantity = _quantity(quantity, work)
    evaluated_at = _stamp(evaluated_at, 'evaluated_at')
    if evaluated_at is None:
        _fail('evaluated_at is required')
    if type(max_age_seconds) is Fraction:
        max_age_seconds = S.norm_num(max_age_seconds)
    if max_age_seconds is not None and (type(max_age_seconds) is not int or not 0 <= max_age_seconds <= 315_576_000_000):
        _fail('max_age_seconds must be a bounded nonnegative native integer')
    validity = quantity['validity']
    status = 'not_declared'
    if validity['from'] is not None or validity['until'] is not None:
        status = 'within_declared_window'
    if validity['from'] is not None and evaluated_at < validity['from']:
        status = 'not_yet_valid'
    if validity['until'] is not None and evaluated_at > validity['until']:
        status = 'expired'
    moment = datetime.strptime(evaluated_at, '%Y-%m-%dT%H:%M:%S%z')
    ages = []
    for source in quantity['sources']:
        work.tick()
        observed = source['observed_at']
        age = None
        if observed is not None:
            delta = moment - datetime.strptime(observed, '%Y-%m-%dT%H:%M:%S%z')
            age = delta.days * 86400 + delta.seconds
        ages.append({'id': source['id'], 'version': source['version'], 'age_seconds': age})
    freshness = 'not_assessed' if max_age_seconds is None else 'within_max_age'
    if max_age_seconds is not None and (not ages or any(row['age_seconds'] is None for row in ages)):
        freshness = 'unknown'
    if max_age_seconds is not None and any(row['age_seconds'] is not None and row['age_seconds'] > max_age_seconds for row in ages):
        freshness = 'stale'
    if any(row['age_seconds'] is not None and row['age_seconds'] < 0 for row in ages):
        freshness = 'not_yet_observed'
    return {'evaluated_at': evaluated_at, 'validity': status, 'freshness': freshness,
            'max_age_seconds': max_age_seconds, 'observations': tuple(ages),
            'quantity': _digest(quantity), 'scope': 'caller_declared_times', 'version': VERSION}


def _adapter(function):
    def call(kernel, node, *args, **limits):
        return function(*args, budget=kernel.budget, node=node, **limits)
    call.__name__ = '_' + function.__name__
    return call


FUNCTIONS = {function.__name__: _adapter(function) for function in (
    quantity_unit, quantity_exact, quantity_interval, quantity_measure, quantity_convert,
    quantity_add, quantity_sub, quantity_mul, quantity_div, quantity_compare, quantity_status)}


def register(kernel):
    """Attach to one Kernel, idempotently; import never changes a global registry."""
    if not isinstance(kernel, S.Kernel):
        _fail('register requires a Symblic Kernel')
    for name, function in FUNCTIONS.items():
        if ((name in S.BUILTINS and S.BUILTINS[name] is not function
             and getattr(S.BUILTINS[name], '_symblic_quantities', None) != name
             and getattr(S.BUILTINS[name], '_symblic_adapter', None) != ('symblic.adapters.quantities', name))
                or (name in kernel.functions and kernel.functions[name] is not function)):
            _fail('kernel function ' + name + ' already exists', 'name')
    kernel.functions.update(FUNCTIONS)
    return kernel

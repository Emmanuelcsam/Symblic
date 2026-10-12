"""MICA check packs: frozen, finite, requirement-linked test data (public and evaluator-only rows).

What it is for
    A caller declares extra function cases or encode/decode round-trip laws, each bound to the exact requirement
    text it checks. Freezing produces a sealed pack: a public part that may enter construction and hidden rows that
    stay with the evaluator.

Depends on: symblic.kernel.grounding (source spans), contracts.py, domains.py. Run by checkpack_cli.py; used by
checkpack_link.py, bench.py and promote.py.

Details
    Frozen finite caller-bound check data; no candidate, provider or executor.

    JSON literals remain text in the declaration. Their bounded parsed values are
    lowered to JavaScript expressions, with computed object keys preserving __proto__
    as data. Model-proposed rows stay proposals and never become acceptance checks.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re

from symblic.kernel import grounding as W
from symblic.mica import contracts as C

VERSION = 1
MAX_CASES = 256
MAX_BYTES = 1_000_000
MAX_LITERAL = 12000
MAX_SAFE_INTEGER = 2**53 - 1
SCOPE = 'finite_caller_bound_checks_semantic_completeness_unassessed'
_NAME = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*\Z')
_KEYWORDS = frozenset('await break case catch class const continue debugger default delete do else enum export extends false finally for function if import in instanceof let new null return super switch this throw true try typeof var void while with yield implements interface package private protected public static'.split())


def declaration_schema():
    """Structural guidance only; exact root bindings and JSON lowering still validate."""
    def obj(properties):
        return {'type': 'object', 'additionalProperties': False, 'required': list(properties), 'properties': properties}
    def array(items, maximum):
        return {'type': 'array', 'minItems': 1, 'maxItems': maximum, 'items': items}
    text = lambda maximum: {'type': 'string', 'minLength': 1, 'maxLength': maximum}
    ident = {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_-]{0,63}$'}
    span = obj({'source_id': text(160), 'revision': {'type': 'integer', 'minimum': 1},
                'source_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
                'start': {'type': 'integer', 'minimum': 0}, 'end': {'type': 'integer', 'minimum': 0},
                'quote': text(12000)})
    requirement = obj({'id': ident, 'text': text(12000), 'span': span})
    export = obj({'name': text(128), 'signature': text(1000)})
    common = {'id': ident, 'origin': {'enum': ['caller_supplied', 'model_proposed']},
              'visibility': {'enum': ['public', 'hidden']}, 'requirements': array(requirement, 128)}
    case = obj({**common, 'kind': {'const': 'case'}, 'function': export,
                'arguments_json': text(MAX_LITERAL), 'expected_json': text(MAX_LITERAL)})
    round_trip = obj({**common, 'kind': {'const': 'round_trip'}, 'encoder': export, 'decoder': export,
                      'inputs_json': array(text(MAX_LITERAL), MAX_CASES)})
    domain_trip = obj({**common, 'kind': {'const': 'round_trip_domain'}, 'encoder': export, 'decoder': export,
                       'domain': {'$ref': '#/$defs/finite_domain'}})
    from symblic.mica import domains as D
    result = obj({'version': {'const': VERSION}, 'seed': {'type': 'integer', 'minimum': 0, 'maximum': 2**32 - 1},
                'evaluation': obj({'id': ident, 'family': text(200), 'split': {'enum': ['train', 'dev', 'heldout']}}),
                'checks': array({'oneOf': [case, round_trip, domain_trip]}, MAX_CASES)})
    result['$defs'] = {'finite_domain': D.schema()}
    return result


class CheckPackError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise CheckPackError(code, message)


def _keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        _fail('fields', 'Missing or unknown check-pack fields.')


def _bounded(value):
    raw = C._bounded(value)
    if len(raw) > MAX_BYTES:
        _fail('limit', 'Check pack exceeds 1000000 bytes; use separate declared packs.')
    return raw


def _hash(value):
    return hashlib.sha256(_bounded(value)).hexdigest()


def _uses_domains(declaration):
    return (type(declaration) is dict and type(declaration.get('checks')) is list and
            any(type(row) is dict and row.get('kind') == 'round_trip_domain' for row in declaration['checks']))


def _identity(declaration=None):
    """{version, sources: {repository path: sha256}} of the code that generated and checks a pack."""
    from symblic.mica import source_identity as I
    sources = {}
    modules = [__import__('sys').modules[__name__], C, W]
    if _uses_domains(declaration):
        modules.append(__import__('importlib').import_module('symblic.mica.domains'))
    for module in modules:
        path = Path(module.__file__)
        marker = getattr(module, '_symblic_import_identity', {})
        with path.open('rb') as stream:
            raw = stream.read(262145)
        if len(raw) > 262144:
            _fail('identity', 'Check-pack source exceeds its bounded source limit.')
        digest = hashlib.sha256(raw).hexdigest()
        name = I.relative_path(path)
        if marker.get('matched') is not True or marker.get('sha256') != digest or I.audit({name: digest}):
            _fail('identity', 'Check-pack dependency changed; use a fresh process: ' + name)
        sources[name] = digest
    return {'version': VERSION, 'sources': sources}


def _source(requirement):
    return W.source_record('requirement/' + requirement['id'], requirement['text'])


def requirement_binding(request, requirement_id, *, start=0, end=None):
    """Exact source witness helper, not an assertion that the span implies a law."""
    request = C.normalize_request(request)
    row = next((r for r in request['requirements'] if r['id'] == requirement_id), None)
    if row is None:
        _fail('requirement', 'Unknown original requirement ID.')
    source = _source(row)
    return {'id': row['id'], 'text': row['text'],
            'span': W.source_span(source, start, len(row['text']) if end is None else end)}


def _bindings(request, bindings):
    if type(bindings) is not list or not 1 <= len(bindings) <= 128:
        _fail('requirement', 'Each declaration needs 1..128 original requirement bindings.')
    original = {r['id']: r for r in request['requirements']}
    ids = []
    for binding in bindings:
        _keys(binding, ('id', 'text', 'span'))
        C._identifier(binding['id'])
        row = original.get(binding['id'])
        if row is None or row['text'] != binding['text'] or binding['id'] in ids:
            _fail('requirement', 'Original requirement ID/text must match exactly once.')
        W.check_span(_source(row), binding['span'])
        ids.append(row['id'])
    return ids


def _export(request, value, *, unary=False):
    _keys(value, ('name', 'signature'))
    if value not in request['exports']:
        _fail('signature', 'Export and signature must exactly match the original request.')
    name = value['name']
    if len(name) > 128 or not _NAME.fullmatch(name) or name in _KEYWORDS:
        _fail('signature', 'The supported fragment needs a callable JavaScript identifier.')
    match = re.fullmatch(re.escape(name) + r'\s*\(\s*([^()]*)\s*\)', value['signature'])
    if match is None:
        _fail('signature', 'The supported fragment requires a simple exact name(arg,...) signature.')
    arguments = [item.strip() for item in match.group(1).split(',')] if match.group(1).strip() else []
    if (len(arguments) > 16 or len(arguments) != len(set(arguments)) or
            any(not _NAME.fullmatch(item) or item in _KEYWORDS for item in arguments) or
            (unary and len(arguments) != 1)):
        _fail('signature', 'Unsupported function parameters or non-unary round trip.')
    return name, len(arguments)


def _literal(text):
    if type(text) is not str or not text or len(text) > MAX_LITERAL:
        _fail('literal', 'Supply bounded JSON literal text, not Python values or source expressions.')
    def number(raw):
        if len(raw) > 128:
            _fail('number', 'Numeric literal exceeds its limit.')
        value = Decimal(raw)
        numeric = float(value)
        if (not math.isfinite(numeric) or value.copy_abs() > MAX_SAFE_INTEGER or
                (value.is_zero() and value.is_signed()) or Decimal(str(numeric)) != value):
            _fail('number', 'Number is outside the finite round-trippable safe-magnitude JSON fragment.')
        return value
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('literal', 'Duplicate JSON object keys are refused.')
            result[key] = value
        return result
    try:
        value = json.loads(text, parse_int=number, parse_float=number, object_pairs_hook=pairs,
                           parse_constant=lambda _: _fail('number', 'Nonfinite JSON is refused.'))
    except (ValueError, RecursionError, InvalidOperation, OverflowError) as error:
        if isinstance(error, CheckPackError):
            raise
        _fail('literal', 'Invalid or excessively nested JSON literal.')
    left = 4096
    def lower(item, depth=0):
        nonlocal left
        left -= 1
        if left < 0 or depth > 16:
            _fail('limit', 'JSON literal node/depth limit exceeded.')
        if item is None:
            return 'null'
        if type(item) is bool:
            return 'true' if item else 'false'
        if type(item) is Decimal:
            return str(item)
        if type(item) is str:
            try:
                item.encode('utf-8')
            except UnicodeError:
                _fail('literal', 'Unpaired Unicode surrogate in JSON literal.')
            return json.dumps(item, ensure_ascii=True)
        if type(item) is list:
            return '[' + ','.join(lower(child, depth + 1) for child in item) + ']'
        if type(item) is dict:
            return '({' + ','.join('[' + lower(key, depth + 1) + ']:' + lower(child, depth + 1)
                                   for key, child in item.items()) + '})'
        _fail('literal', 'Unsupported JSON literal.')
    expression = lower(value)
    return value, expression


def _declarations(request, declaration):
    _bounded(declaration)
    _keys(declaration, ('version', 'seed', 'evaluation', 'checks'))
    if type(declaration['version']) is not int or declaration['version'] != VERSION:
        _fail('version', 'Unsupported check declaration version.')
    if type(declaration['seed']) is not int or not 0 <= declaration['seed'] < 2**32:
        _fail('seed', 'Seed is an exact integer controlling case order only.')
    evaluation = declaration['evaluation']
    _keys(evaluation, ('id', 'family', 'split'))
    C._identifier(evaluation['id']); C._text(evaluation['family'], 'family', 200)
    if evaluation['split'] not in ('train', 'dev', 'heldout'):
        _fail('split', 'Choose an explicit existing evaluation split before freezing.')
    checks = declaration['checks']
    if type(checks) is not list or not 1 <= len(checks) <= MAX_CASES:
        _fail('limit', 'Supply 1..256 explicit check declarations.')
    generated, ids, duplicates, domains = [], set(), set(), []
    semantic_roundtrips = set()
    semantic_visibility = {}
    using_domains = _uses_domains(declaration)
    for row in checks:
        if type(row) is not dict:
            _fail('fields', 'A check declaration must be an object.')
        kind = row.get('kind')
        extra = ('function', 'arguments_json', 'expected_json') if kind == 'case' else (
            ('encoder', 'decoder', 'inputs_json') if kind == 'round_trip' else (
            ('encoder', 'decoder', 'domain') if kind == 'round_trip_domain' else ()))
        if not extra:
            _fail('kind', 'Choose case, caller-declared round_trip or round_trip_domain.')
        _keys(row, ('id', 'kind', 'origin', 'visibility', 'requirements', *extra))
        ident = C._identifier(row['id'])
        if ident in ids:
            _fail('duplicate', 'Declaration IDs must be unique.')
        ids.add(ident)
        if row['origin'] not in ('caller_supplied', 'model_proposed') or row['visibility'] not in ('public', 'hidden'):
            _fail('provenance', 'Declare origin and visibility explicitly.')
        requirements = _bindings(request, row['requirements'])
        cases = []
        if kind == 'case':
            name, arity = _export(request, row['function'])
            arguments, _ = _literal(row['arguments_json'])
            if type(arguments) is not list or len(arguments) != arity:
                _fail('arguments', 'Arguments JSON must be an array matching the declared arity.')
            # Parse each argument through the same trusted lowering without re-encoding Decimal.
            _, array_expression = _literal(row['arguments_json'])
            _literal(row['expected_json'])
            cases = [(name + '(...' + array_expression + ')', row['expected_json'])]
        else:
            encoder, _ = _export(request, row['encoder'], unary=True)
            decoder, _ = _export(request, row['decoder'], unary=True)
            if kind == 'round_trip_domain':
                from symblic.mica import domains as D
                remaining = MAX_CASES - len(generated)
                if row['origin'] == 'caller_supplied':
                    previous = sum(r['origin'] == 'caller_supplied' and r['visibility'] == row['visibility']
                                   for r in generated)
                    capacity = (200 if row['visibility'] == 'hidden' else 256 - len(request['tests']))
                    remaining = min(remaining, capacity - previous)
                expanded = D.expand_domain(row['domain'], max_values=remaining)
                inputs = expanded['values_json']
                domains.append({'declaration_id': ident, **{k: v for k, v in expanded.items() if k != 'values_json'}})
            else:
                inputs = row['inputs_json']
            if type(inputs) is not list or not 1 <= len(inputs) <= MAX_CASES:
                _fail('limit', 'Round-trip inputs require 1..256 finite JSON literals.')
            for literal in inputs:
                value, expression = _literal(literal)
                if using_domains:
                    from symblic.mica import domains as D
                    semantic = (row['origin'], row['visibility'], encoder, decoder, D._semantic(value))
                    if semantic in semantic_roundtrips:
                        _fail('domain_duplicate', 'Equivalent round-trip inputs would inflate finite domain coverage.')
                    semantic_roundtrips.add(semantic)
                    if row['origin'] == 'caller_supplied':
                        identity = (encoder, decoder, D._semantic(value))
                        prior = semantic_visibility.get(identity)
                        if prior is not None and prior != row['visibility']:
                            _fail('exposure', 'Equivalent authoritative round-trip input is both public and hidden.')
                        semantic_visibility[identity] = row['visibility']
                cases.append((decoder + '(' + encoder + '(' + expression + '))', literal))
        for index, (call, expected) in enumerate(cases):
            C._text(call, 'call', 4000); C._expected(expected)
            duplicate = (row['origin'], row['visibility'], call, expected)
            if duplicate in duplicates:
                _fail('duplicate', 'Repeated generated check would inflate finite coverage.')
            duplicates.add(duplicate)
            generated.append({'id': ident + '/' + str(index), 'declaration_id': ident,
                              'origin': row['origin'], 'visibility': row['visibility'],
                              'requirements': requirements, 'call': call, 'expected': expected,
                              'assurance': 'proposed_interpretation' if row['origin'] == 'model_proposed' else 'caller_bound_finite_example'})
            if len(generated) > MAX_CASES:
                _fail('limit', 'Generated case count exceeds 256; no cases were truncated.')
    return sorted(generated, key=lambda row: _hash({'seed': declaration['seed'], 'id': row['id']})), domains


def _build(request, declaration, checker_identity, implementation):
    request = C.normalize_request(request)
    if type(checker_identity) is not dict or not checker_identity:
        _fail('checker', 'Supply an explicit nonempty checker identity from the trusted caller.')
    _bounded(checker_identity)
    rows, domains = _declarations(request, declaration)
    public = [r for r in rows if r['origin'] == 'caller_supplied' and r['visibility'] == 'public']
    hidden = [r for r in rows if r['origin'] == 'caller_supplied' and r['visibility'] == 'hidden']
    public_calls = {r['call'] for r in request['tests']} | {r['call'] for r in public}
    if any(row['call'] in public_calls for row in hidden):
        _fail('exposure', 'An authoritative hidden call is already public.')
    if len(request['tests']) + len(public) > 256 or len(hidden) > 200:
        _fail('limit', 'Existing MICA public/hidden case limits would be exceeded; no truncation.')
    expanded = copy.deepcopy(request)
    expanded['tests'] += [{'requirement_ids': r['requirements'], 'call': r['call'], 'expected': r['expected']} for r in public]
    expanded = C.normalize_request(expanded)
    body = {'version': VERSION, 'scope': SCOPE, 'semantic_completeness': 'unassessed',
            'original_request': request, 'original_request_sha256': C.digest(request),
            'declaration': copy.deepcopy(declaration), 'checker_identity': copy.deepcopy(checker_identity),
            'checker_identity_scope': 'caller_supplied_content_pin_not_execution_attestation',
            'implementation': copy.deepcopy(implementation), 'checks': rows,
            'public_request': expanded, 'public_request_sha256': C.digest(expanded),
            'counts': {'original_public': len(request['tests']), 'generated_public': len(public),
                       'hidden': len(hidden), 'proposals': sum(r['origin'] == 'model_proposed' for r in rows)},
            'order_scope': 'seeded_order_only_all_declared_cases_retained',
            'independence': 'not_established', 'oracle_exposure_scope': 'explicit_public_hidden_partition_only',
            'freeze_scope': 'immutable_data_only_caller_must_pin_before_any_candidate_dispatch'}
    if domains:
        body['finite_domains'] = domains
    return {**body, 'sha256': _hash(body)}


def freeze(request, declaration, checker_identity):
    """Generate all bounded rows before candidates; this function executes none."""
    return _build(request, declaration, checker_identity, _identity(declaration))


def validate(pack, *, current_checker=None, expected_sha256=None, require_current=True):
    """Check a sealed pack against its retained SHA-256; require_current=False reads a historical pack."""
    _bounded(pack)
    if type(pack) is not dict:
        _fail('pack', 'Expected a sealed check pack.')
    required = ('original_request', 'declaration', 'checker_identity', 'implementation')
    if not all(name in pack for name in required):
        _fail('pack', 'Incomplete check pack.')
    if expected_sha256 is not None and pack.get('sha256') != expected_sha256:
        _fail('pin', 'Check pack differs from the original caller-retained content pin.')
    expected = _build(*(pack[name] for name in required))
    if expected != pack:
        _fail('pin', 'Check pack changed; complete deterministic regeneration differs.')
    if require_current and pack['implementation'] != _identity(pack['declaration']):
        _fail('identity', 'Generator or requirement checker differs from the frozen implementation.')
    if current_checker is not None and pack['checker_identity'] != current_checker:
        _fail('checker', 'Current checker differs from the original explicit pin.')
    return copy.deepcopy(pack)


def public_request(pack, *, expected_sha256=None):
    """Only original/public caller authority; never proposals or hidden cases."""
    return validate(pack, expected_sha256=expected_sha256)['public_request']


def fixture(pack, *, expected_sha256=None):
    """Evaluator-side only: this result contains hidden checks. Never prompt it."""
    pack = validate(pack, expected_sha256=expected_sha256)
    evaluation = pack['declaration']['evaluation']
    hidden = [[r['call'], r['expected']] for r in pack['checks']
              if r['origin'] == 'caller_supplied' and r['visibility'] == 'hidden']
    if not hidden:
        _fail('hidden', 'Existing MICA fixtures require at least one authoritative hidden check.')
    return {**copy.deepcopy(evaluation),
            'request': copy.deepcopy(pack['public_request']), 'hidden_tests': hidden}

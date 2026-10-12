"""MICA root proposals: strict, versioned decoding of a model's proposed requirements and tests.

Depends on: source_identity.py (lazily). Used by project.py. Pure.

Details
    Versioned JSON transport lowering for MICA root proposals; no execution.

    Version 3 admits a JSON value in tests.expected_value and lowers it to the
    existing expected JSON-text contract. Legacy expected strings are unchanged.
    This checks representation only, never the semantic correctness of an answer.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import math
from pathlib import Path
import re

VERSION = 1
PROPOSAL_VERSION = 3
MAX_BYTES = 2_000_000
MAX_ITEMS = 50_000
MAX_DEPTH = 32
MAX_EXPECTED = 12_000
_INTEGER = re.compile(r'-?(?:0|[1-9][0-9]*)\Z')
_LOADED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class ProposalEncodingError(ValueError):
    pass


class _Number:
    __slots__ = ('text',)

    def __init__(self, text):
        # The standard JSON parser has already checked the number grammar.
        if len(text) > 1236:
            raise ProposalEncodingError('Proposal number token exceeds its bound.')
        self.text = text


def identity():
    """The version and source digest of this lowering code; refuses when the loaded code changed."""
    path = Path(__file__)
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    from symblic.mica import source_identity as I
    problems = I.audit({I.relative_path(path): _LOADED_SHA256})
    if problems or current != _LOADED_SHA256:
        raise ProposalEncodingError('Proposal lowering source differs from its loaded implementation.')
    return {'version': VERSION, 'proposal_version': PROPOSAL_VERSION, 'sha256': current}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProposalEncodingError('Duplicate proposal JSON key.')
        result[key] = value
    return result


def _constant(_text):
    raise ProposalEncodingError('Nonfinite proposal JSON numbers are refused.')


def _bounded_tree(value):
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_ITEMS or depth > MAX_DEPTH:
            raise ProposalEncodingError('Proposal JSON exceeds its structure bound.')
        if type(item) is dict:
            if len(item) * 2 > MAX_ITEMS - count - len(stack):
                raise ProposalEncodingError('Proposal JSON exceeds its item bound.')
            stack.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif type(item) is list:
            if len(item) > MAX_ITEMS - count - len(stack):
                raise ProposalEncodingError('Proposal JSON exceeds its item bound.')
            stack.extend((part, depth + 1) for part in item)
        elif type(item) is str:
            if len(item) > 262144:
                raise ProposalEncodingError('Proposal JSON text exceeds its bound.')
        elif item is not None and type(item) not in (bool, _Number):
            raise ProposalEncodingError('Proposal contains an unsupported JSON value.')


def _plain(value):
    """Outside value expectations, retain the existing exact-integer policy."""
    if type(value) is _Number:
        if not _INTEGER.fullmatch(value.text):
            raise ProposalEncodingError('Only integer numbers are admitted outside expected_value.')
        number = int(value.text)
        if number.bit_length() > 4096:
            raise ProposalEncodingError('Proposal integer exceeds its bound.')
        return number
    if type(value) is dict:
        return {key: _plain(item) for key, item in value.items()}
    if type(value) is list:
        return [_plain(item) for item in value]
    return value


def _value_json(value):
    """Bounded deterministic JSON; numeric lexemes never round-trip through float."""
    pieces, used = [], 0

    def emit(text):
        nonlocal used
        used += len(text)
        if used > MAX_EXPECTED:
            raise ProposalEncodingError('Encoded expected value exceeds its text bound.')
        pieces.append(text)

    def visit(item):
        kind = type(item)
        if kind is _Number:
            try:
                finite = math.isfinite(float(item.text))
            except (ValueError, OverflowError):
                finite = False
            if not finite:
                raise ProposalEncodingError('Expected value numbers must have finite IEEE-754 values.')
            emit(item.text)
        elif kind is dict:
            emit('{')
            for index, key in enumerate(sorted(item)):
                if index:
                    emit(',')
                emit(json.dumps(key, ensure_ascii=True)); emit(':'); visit(item[key])
            emit('}')
        elif kind is list:
            emit('[')
            for index, child in enumerate(item):
                if index:
                    emit(',')
                visit(child)
            emit(']')
        elif item is None or kind in (str, bool):
            emit(json.dumps(item, ensure_ascii=True, allow_nan=False))
        else:
            raise ProposalEncodingError('Unsupported expected JSON value.')
    visit(value)
    return ''.join(pieces)


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def decode(text):
    """Return (legacy-shaped detached envelope, auditable transport receipt).

    Envelope authority and request semantics are checked by MicaProject after
    lowering. No malformed strings, exceptions or expected answers are repaired.
    """
    if type(text) is not str:
        raise ProposalEncodingError('Root proposal must be JSON text.')
    try:
        raw = text.encode('utf-8')
    except UnicodeError as exc:
        raise ProposalEncodingError('Proposal source is not valid UTF-8 text.') from exc
    if len(raw) > MAX_BYTES:
        raise ProposalEncodingError('Proposal source exceeds its byte bound.')
    try:
        row = json.loads(text, object_pairs_hook=_pairs, parse_int=_Number,
                         parse_float=_Number, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise ProposalEncodingError('Root proposal must be bounded JSON without duplicate or nonfinite values.') from exc
    _bounded_tree(row)
    if type(row) is not dict:
        raise ProposalEncodingError('Root proposal must be an object.')
    versioned = 'proposal_version' in row
    keys = {'request', 'objective_coverage', 'missing_decisions'}
    if versioned:
        marker = row['proposal_version']
        if type(marker) is not _Number or marker.text != str(PROPOSAL_VERSION):
            raise ProposalEncodingError('Unknown or noninteger root proposal version.')
        if set(row) != keys | {'proposal_version'}:
            raise ProposalEncodingError('Versioned proposal has missing or unknown fields.')
        row = {key: row[key] for key in row if key != 'proposal_version'}
    elif set(row) != keys:
        raise ProposalEncodingError('Legacy proposal has missing or unknown fields.')
    encoded = []
    request = row.get('request')
    if type(request) is dict and type(request.get('tests')) is list:
        tests = []
        for index, test in enumerate(request['tests']):
            if type(test) is not dict:
                raise ProposalEncodingError('Every proposed test must be an object.')
            key = 'expected_value' if versioned else 'expected'
            if set(test) != {'requirement_ids', 'call', key}:
                raise ProposalEncodingError('Test fields do not match the declared proposal encoding.')
            expected = _value_json(test[key]) if versioned else test[key]
            if type(expected) is not str:
                raise ProposalEncodingError('Legacy expected values must remain JSON text.')
            lowered = {name: _plain(value) for name, value in test.items() if name != key}
            lowered['expected'] = expected
            tests.append(lowered)
            encoded.append({'test_index': index,
                            'input_value_json_sha256': _sha(expected) if versioned else None,
                            'lowered_expected_sha256': _sha(expected)})
        row['request'] = {**request, 'tests': tests}
    row = _plain(row)
    receipt = {'version': VERSION, 'proposal_version': PROPOSAL_VERSION if versioned else 2,
               'encoding': 'expected_value' if versioned else 'legacy_expected_json_text',
               'transformation': 'json_value_to_json_text' if versioned else 'none',
               'raw_proposal_sha256': hashlib.sha256(raw).hexdigest(), 'tests': encoded,
               'semantic_validation': 'not_performed', 'independent_evidence': False}
    return row, receipt

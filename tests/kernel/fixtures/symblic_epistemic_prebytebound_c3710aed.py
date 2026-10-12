"""Pure claim provenance and context packing, with no truth or confidence oracle.

Only a trusted host/checker may construct origins or receipts. Hashes provide
integrity and exact references, not signatures or authority. Do not accept a
model-supplied envelope as a host attestation. Content is bounded exact JSON;
Symblic values must first pass through the kernel's canonical encoder.

A receipt concerns its encoded predicate/schema/derivation only. An admitted
premise remains a premise, including an owner statement or unanimous model
answer. A checked conclusion remains conditional on all retained root premises.
This module neither evaluates logic nor infers anything from a contradiction.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import hashlib
import heapq
import itertools
import json
import re

VERSION = 1
MAX_CLAIMS = 1024
MAX_REFS = 64
MAX_CHECKS = 64
MAX_DEPTH = 24
MAX_NODES = 16384
MAX_BYTES = 262144
MAX_CONTEXT = 16 * 1024 * 1024
ORIGINS = frozenset({'owner_premise', 'assumption', 'source_report', 'observation',
                     'model_proposal', 'derived'})
STATUSES = frozenset({'unknown', 'contested', 'refuted', 'conditional'})
SCOPES = frozenset({'encoded_schema', 'encoded_predicate', 'encoded_derivation'})
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class EpistemicError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _fail(code, message, details=None):
    raise EpistemicError(code, message, details)


_END = object()


def _json(value):
    # A lazy pre-order walk over iterator frames (D16 v2): the same nodes in the same order, with the same checks,
    # so the same first error, as the recursive walk it replaces, and like it at most one pending frame per open
    # container (never more than MAX_DEPTH + 2): a wide list or dict is read one child at a time, never queued
    # whole before the node limit can stop it. MAX_DEPTH (24) is far below Python's recursion limit, so recursion
    # was never the binding bound; only the per-node call overhead goes.
    count = 0
    frames = [(iter((value,)), 0)]
    while frames:
        children, depth = frames[-1]
        try:
            item = next(children)
        except StopIteration:
            frames.pop()
            continue
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _fail('limit', 'JSON structure exceeds the node/depth limit')
        kind = type(item)
        if item is None or kind is bool:
            continue
        if kind is int:
            if item.bit_length() > 4096:
                _fail('limit', 'Integer exceeds 4096 bits; use canonical exact text')
            continue
        if kind is str:
            if len(item) > MAX_BYTES:
                _fail('limit', 'Text exceeds the claim limit')
            if not item.isascii():          # ASCII text holds no surrogates (D16: skip the encode)
                try:
                    item.encode('utf-8')
                except UnicodeEncodeError:
                    _fail('json', 'Unpaired Unicode surrogates are not supported')
            continue
        if kind is list:
            frames.append((iter(item), depth + 1))
            continue
        if kind is dict and all(type(key) is str for key in item):
            # key, value, key, value in insertion order: the recursive walk's order
            frames.append((itertools.chain.from_iterable(item.items()), depth + 1))
            continue
        _fail('json', 'Content must be exact JSON (no floats, tuples or custom objects)')
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    # ASCII text is one byte per character (D16: no second encode just to measure it)
    if (len(encoded) if encoded.isascii() else len(encoded.encode('utf-8'))) > MAX_BYTES:
        _fail('limit', 'Encoded claim exceeds the byte limit')
    return encoded


def digest(value):
    """SHA-256 of exact bounded canonical JSON; never Python object repr."""
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _keys(row, expected, kind):
    if type(row) is not dict or set(row) != set(expected):
        _fail('schema', f'{kind} has missing or unknown fields')


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail('id', 'ID must be 1..160 ASCII identifier characters')
    return value


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail('hash', 'Expected a lowercase SHA-256 digest')
    return value


def _reference(row):
    _keys(row, ('id', 'revision', 'sha256'), 'Reference')
    _id(row['id'])
    if type(row['revision']) is not int or not 1 <= row['revision'] <= 2**53 - 1:
        _fail('revision', 'Revision must be a positive exact JSON integer')
    _sha(row['sha256'])
    return copy.deepcopy(row)


def _references(rows):
    if type(rows) is not list or len(rows) > MAX_REFS:
        _fail('limit', f'At most {MAX_REFS} references are allowed')
    out = [_reference(row) for row in rows]
    if len({row['id'] for row in out}) != len(out):
        _fail('duplicate', 'Duplicate dependency IDs, including identical references, are invalid')
    return sorted(out, key=lambda row: row['id'])


def reference(claim):
    """Pin content, origin, lifecycle, checks and dependencies, not just content."""
    row = validate_claim(claim)
    return {key: row[key] for key in ('id', 'revision', 'sha256')}


def receipt(*, subject, predicate, scope, passed, inputs, predicate_sha256=None):
    """Host attestation for one exact subject and predicate; no implicit truth.

    encoded_derivation must be emitted only after the host checks that this
    content follows from exactly these inputs. Schema/acceptance checks must
    use their weaker scopes. A rejected predicate does not refute the subject.
    """
    if type(scope) is not str or scope not in SCOPES or type(passed) is not bool:
        _fail('receipt', 'Invalid receipt scope or passed flag')
    body = {'version': VERSION, 'subject_sha256': digest(subject),
            'predicate': copy.deepcopy(predicate),
            # D16: a caller that already holds digest(predicate) (the runner, once per run per distinct predicate)
            # passes it; a claim built from this receipt still re-checks it (_receipt), so a wrong one cannot pass.
            'predicate_sha256': digest(predicate) if predicate_sha256 is None else predicate_sha256,
            'scope': scope, 'passed': passed, 'inputs': _references(inputs)}
    return {**body, 'id': digest(body)}


def _receipt(row):
    _keys(row, ('version', 'subject_sha256', 'predicate', 'predicate_sha256',
                'scope', 'passed', 'inputs', 'id'), 'Receipt')
    if type(row['version']) is not int or row['version'] != VERSION:
        _fail('version', 'Unknown receipt version')
    _sha(row['subject_sha256'])
    _sha(row['id'])
    if type(row['scope']) is not str or row['scope'] not in SCOPES or type(row['passed']) is not bool:
        _fail('receipt', 'Invalid receipt scope or passed flag')
    if digest(row['predicate']) != row['predicate_sha256']:
        _fail('hash', 'Receipt predicate digest differs')
    if _references(row['inputs']) != row['inputs']:
        _fail('canonical', 'Receipt inputs must be in canonical ID order')
    if digest({key: value for key, value in row.items() if key != 'id'}) != row['id']:
        _fail('hash', 'Receipt digest differs')
    return copy.deepcopy(row)


def make_claim(ident, content, *, origin, revision=1, dependencies=None, checks=None,
               status='unknown', withdrawn=False):
    """Build an immutable JSON value; caller retains revisions in its existing ledger."""
    try:
        return _make_claim_once(ident, content, origin, revision, dependencies, checks, status, withdrawn)
    except _Decline:
        # Any doubt: the reference checks below decide, raising exactly as before.
        return _make_claim_reference(ident, content, origin=origin, revision=revision,
                                     dependencies=dependencies, checks=checks, status=status,
                                     withdrawn=withdrawn)


def validate_claim(claim):
    try:
        return _validate_claim_once(claim)
    except _Decline:
        return _validate_claim_reference(claim)


def _make_claim_reference(ident, content, *, origin, revision=1, dependencies=None, checks=None,
                          status='unknown', withdrawn=False):
    """The original construction: every check, in its original order."""
    dependencies = [] if dependencies is None else dependencies
    checks = [] if checks is None else checks
    if type(checks) is not list or len(checks) > MAX_CHECKS:
        _fail('limit', f'At most {MAX_CHECKS} checks are allowed')
    validated_checks = [_receipt(row) for row in checks]
    body = {'version': VERSION, 'id': ident, 'revision': revision, 'origin': origin,
            'content': copy.deepcopy(content), 'content_sha256': digest(content),
            'dependencies': _references(dependencies),
            'checks': sorted(validated_checks, key=lambda row: row['id']),
            'status': status, 'withdrawn': withdrawn}
    return _validate_claim_reference({**body, 'sha256': digest(body)})


def _validate_claim_reference(claim):
    """The original validation: every check, in its original order."""
    _keys(claim, ('version', 'id', 'revision', 'origin', 'content', 'content_sha256',
                  'dependencies', 'checks', 'status', 'withdrawn', 'sha256'), 'Claim')
    _json(claim)
    if type(claim['version']) is not int or claim['version'] != VERSION:
        _fail('version', 'Unknown claim format version')
    _reference({key: claim[key] for key in ('id', 'revision', 'sha256')})
    if type(claim['origin']) is not str or claim['origin'] not in ORIGINS \
            or type(claim['status']) is not str or claim['status'] not in STATUSES:
        _fail('schema', 'Unknown claim origin or status')
    if claim['status'] == 'conditional' and claim['origin'] != 'derived':
        _fail('status', 'Only a derivation can request conditional status')
    if type(claim['withdrawn']) is not bool:
        _fail('schema', 'withdrawn must be a boolean')
    if digest(claim['content']) != claim['content_sha256']:
        _fail('hash', 'Content digest differs')
    refs = _references(claim['dependencies'])
    if refs != claim['dependencies']:
        _fail('canonical', 'Dependencies must be in canonical ID order')
    if type(claim['checks']) is not list or len(claim['checks']) > MAX_CHECKS:
        _fail('limit', f'At most {MAX_CHECKS} checks are allowed')
    checks = [_receipt(row) for row in claim['checks']]
    if len({row['id'] for row in checks}) != len(checks):
        _fail('duplicate', 'Duplicate receipt IDs are invalid')
    if checks != sorted(checks, key=lambda row: row['id']):
        _fail('canonical', 'Receipts must be in canonical ID order')
    ref_by_id = {row['id']: row for row in refs}
    for check in checks:
        if check['subject_sha256'] != claim['content_sha256']:
            _fail('receipt', 'Receipt is for different subject content')
        if any(ref_by_id.get(row['id']) != row for row in check['inputs']):
            _fail('receipt', 'Receipt reads an undeclared or differently pinned dependency')
        if check['scope'] == 'encoded_derivation' and check['inputs'] != refs:
            _fail('receipt', 'A derivation must attest to exactly the declared dependencies')
    if digest({key: value for key, value in claim.items() if key != 'sha256'}) != claim['sha256']:
        _fail('hash', 'Claim digest differs')
    return copy.deepcopy(claim)


# Single-pass path. make_claim and validate_claim try it first: one traversal
# per field validates exactly what the reference checks validate and builds the
# detached copy, and one reusable encoder produces each canonical text. It only
# ever returns a value the reference path would return (equal values, the same
# key order, no sharing with the caller). Anything it cannot vouch for, such as
# an invalid input, a bound, or internal sharing that deepcopy would preserve,
# raises _Decline, and the unchanged reference path decides and raises exactly
# as before. Nothing is trusted: every field is checked on every call.

class _Decline(Exception):
    """The single-pass path does not vouch for this input; the reference path decides."""


_CANON = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode
_CLAIM_KEYS = frozenset(('version', 'id', 'revision', 'origin', 'content', 'content_sha256',
                         'dependencies', 'checks', 'status', 'withdrawn', 'sha256'))
_RECEIPT_KEYS = frozenset(('version', 'subject_sha256', 'predicate', 'predicate_sha256',
                           'scope', 'passed', 'inputs', 'id'))
_REFERENCE_KEYS = frozenset(('id', 'revision', 'sha256'))
# Adding "sha256" to a claim body adds two JSON nodes (key, value) and exactly
# len(',"sha256":"' + 64 hex + '"') bytes to its canonical text.
_SHA256_FIELD_BYTES = 76


def _envelope(row, keys):
    """An exact dict whose keys are exact str and exactly `keys`.

    Key types come first: a str subclass key compares and hashes like its text,
    so a schema comparison alone would accept what _json refuses, and a custom
    key could run arbitrary comparison code during that comparison or a lookup.
    """
    return type(row) is dict and all(type(key) is str for key in row) and row.keys() == keys


def _digest_text(value):
    """An exact lowercase SHA-256 str; anything else must reach the reference checks
    before it is compared (a subclass would compare equal; a custom object could run code)."""
    return type(value) is str and _SHA.fullmatch(value) is not None


def _sha256(text):
    try:
        raw = text.encode('utf-8')
    except UnicodeEncodeError:  # an unpaired surrogate: _json refuses it
        raise _Decline from None
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _tree(value, depth, state, seen):
    """Validate one subtree as _json's walk does and return its detached copy.

    state is [nodes, deepest]. Over-long text is refused here; an unpaired
    surrogate fails the UTF-8 encoding of the canonical text that every copied
    subtree goes through. A container met twice declines: deepcopy would keep
    that sharing, so the reference path must produce it.
    """
    state[0] += 1
    if state[0] > MAX_NODES or depth > MAX_DEPTH:
        raise _Decline
    if depth > state[1]:
        state[1] = depth
    kind = type(value)
    if kind is str:
        if len(value) > MAX_BYTES:
            raise _Decline
        return value
    if value is None or kind is bool:
        return value
    if kind is int:
        if value.bit_length() > 4096:
            raise _Decline
        return value
    if kind is dict:
        if id(value) in seen:
            raise _Decline
        seen.add(id(value))
        out = {}
        for key, item in value.items():
            if type(key) is not str or len(key) > MAX_BYTES:
                raise _Decline
            state[0] += 1
            out[key] = _tree(item, depth + 1, state, seen)
        return out
    if kind is list:
        if id(value) in seen:
            raise _Decline
        seen.add(id(value))
        return [_tree(item, depth + 1, state, seen) for item in value]
    raise _Decline


def _reference_once(row, depth, state, seen):
    """One reference checked as _reference does; its copy keeps the caller's key order."""
    if not _envelope(row, _REFERENCE_KEYS) or id(row) in seen:
        raise _Decline
    seen.add(id(row))
    ident, revision, sha = row['id'], row['revision'], row['sha256']
    if (type(ident) is not str or not _ID.fullmatch(ident) or type(revision) is not int
            or not 1 <= revision <= 2**53 - 1 or type(sha) is not str or not _SHA.fullmatch(sha)):
        raise _Decline
    state[0] += 7  # the object, three keys and three scalar values
    if depth + 1 > state[1]:
        state[1] = depth + 1
    return {key: row[key] for key in row}


def _ascending(rows):
    """Canonical order: IDs strictly ascending, so also free of duplicates."""
    return all(rows[index - 1]['id'] < rows[index]['id'] for index in range(1, len(rows)))


def _receipt_once(row, depth, state, seen):
    """One receipt checked as _receipt does; returns its detached copy."""
    if not _envelope(row, _RECEIPT_KEYS) or id(row) in seen:
        raise _Decline
    seen.add(id(row))
    if (type(row['version']) is not int or row['version'] != VERSION or not _digest_text(row['subject_sha256'])
            or not _digest_text(row['id']) or not _digest_text(row['predicate_sha256'])
            or type(row['scope']) is not str or row['scope'] not in SCOPES or type(row['passed']) is not bool):
        raise _Decline
    state[0] += 1
    if depth + 1 > state[1]:
        state[1] = depth + 1
    out = {}
    for key, item in row.items():
        state[0] += 1
        if key == 'predicate':
            out[key] = _tree(item, depth + 1, state, seen)
        elif key == 'inputs':
            if type(item) is not list or len(item) > MAX_REFS or id(item) in seen:
                raise _Decline
            seen.add(id(item))
            state[0] += 1
            out[key] = [_reference_once(ref, depth + 2, state, seen) for ref in item]
            if not _ascending(out[key]):
                raise _Decline
        else:
            state[0] += 1
            out[key] = item
    if _sha256(_CANON(out['predicate']))[0] != row['predicate_sha256']:
        raise _Decline
    if _sha256(_CANON({key: value for key, value in out.items() if key != 'id'}))[0] != row['id']:
        raise _Decline
    return out


def _scalars_once(ident, revision, origin, status, withdrawn):
    if (type(ident) is not str or not _ID.fullmatch(ident) or type(revision) is not int
            or not 1 <= revision <= 2**53 - 1 or type(origin) is not str or origin not in ORIGINS
            or type(status) is not str or status not in STATUSES or type(withdrawn) is not bool
            or (status == 'conditional' and origin != 'derived')):
        raise _Decline


def _receipts_fit(checks, refs, content_sha256):
    by_id = {row['id']: row for row in refs}
    for check in checks:
        if (check['subject_sha256'] != content_sha256
                or any(by_id.get(row['id']) != row for row in check['inputs'])
                or (check['scope'] == 'encoded_derivation' and check['inputs'] != refs)):
            raise _Decline


def _sealed(body, state):
    """The claim digest, after the claim-wide node, depth and byte bounds of _json."""
    sha, size = _sha256(_CANON(body))
    if state[0] + 2 > MAX_NODES or state[1] > MAX_DEPTH or size + _SHA256_FIELD_BYTES > MAX_BYTES:
        raise _Decline
    return sha


def _make_claim_once(ident, content, origin, revision, dependencies, checks, status, withdrawn):
    dependencies = [] if dependencies is None else dependencies
    checks = [] if checks is None else checks
    if (type(checks) is not list or len(checks) > MAX_CHECKS or type(dependencies) is not list
            or len(dependencies) > MAX_REFS):
        raise _Decline
    _scalars_once(ident, revision, origin, status, withdrawn)
    # Nodes of the unsealed body: the object, its ten keys, seven scalar values
    # and the two lists; content, references and receipts add their own.
    state = [20, 1]
    # Fields are copied independently, like the reference path's separate deep
    # copies: sharing between fields never reaches the result.
    refs = sorted((_reference_once(row, 2, state, set()) for row in dependencies), key=lambda row: row['id'])
    receipts = sorted((_receipt_once(row, 2, state, set()) for row in checks), key=lambda row: row['id'])
    if not _ascending(refs) or not _ascending(receipts):
        raise _Decline
    detached = _tree(content, 1, state, set())
    content_sha256 = _sha256(_CANON(detached))[0]
    _receipts_fit(receipts, refs, content_sha256)
    body = {'version': VERSION, 'id': ident, 'revision': revision, 'origin': origin, 'content': detached,
            'content_sha256': content_sha256, 'dependencies': refs, 'checks': receipts,
            'status': status, 'withdrawn': withdrawn}
    return {**body, 'sha256': _sealed(body, state)}


def _validate_claim_once(claim):
    if not _envelope(claim, _CLAIM_KEYS):
        raise _Decline
    if type(claim['version']) is not int or claim['version'] != VERSION:
        raise _Decline
    _scalars_once(claim['id'], claim['revision'], claim['origin'], claim['status'], claim['withdrawn'])
    if not _digest_text(claim['sha256']) or not _digest_text(claim['content_sha256']):
        raise _Decline
    # One deep copy in the reference path: sharing anywhere in the claim declines.
    seen = {id(claim)}
    state = [1, 1]
    out = {}
    for key, value in claim.items():
        state[0] += 1
        if key == 'content':
            out[key] = _tree(value, 1, state, seen)
        elif key in ('dependencies', 'checks'):
            limit = MAX_REFS if key == 'dependencies' else MAX_CHECKS
            if type(value) is not list or len(value) > limit or id(value) in seen:
                raise _Decline
            seen.add(id(value))
            state[0] += 1
            each = _reference_once if key == 'dependencies' else _receipt_once
            out[key] = [each(row, 2, state, seen) for row in value]
            if not _ascending(out[key]):
                raise _Decline
        else:
            state[0] += 1
            out[key] = value
    if _sha256(_CANON(out['content']))[0] != claim['content_sha256']:
        raise _Decline
    _receipts_fit(out['checks'], out['dependencies'], claim['content_sha256'])
    state[0] -= 2  # _sealed counts the sha256 key and value again
    if _sealed({key: value for key, value in out.items() if key != 'sha256'}, state) != claim['sha256']:
        raise _Decline
    return out


def _index(claims):
    if type(claims) is not list or len(claims) > MAX_CLAIMS:
        _fail('limit', f'At most {MAX_CLAIMS} claims are allowed')
    rows = {}
    for claim in claims:
        row = validate_claim(claim)
        if row['id'] in rows:
            _fail('duplicate', 'Duplicate claim IDs are invalid; select one current revision')
        rows[row['id']] = row
    # Iterative topological sort avoids recursion and makes cycles explicit even
    # when their references are stale. Missing references are evaluated below.
    indegree = {ident: 0 for ident in rows}
    children = {ident: [] for ident in rows}
    for ident, row in rows.items():
        for parent in row['dependencies']:
            if parent['id'] in rows:
                indegree[ident] += 1
                children[parent['id']].append(ident)
    ready = [ident for ident, count in indegree.items() if not count]
    heapq.heapify(ready)
    order = []
    while ready:
        ident = heapq.heappop(ready)
        order.append(ident)
        for child in sorted(children[ident]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(rows):
        _fail('cycle', 'Cyclic claim dependencies are invalid',
              {'ids': sorted(ident for ident, count in indegree.items() if count)})
    return rows, order


def _disagreements(disagreements, rows):
    if type(disagreements) is not list or len(disagreements) > MAX_CLAIMS:
        _fail('limit', 'Disagreement list exceeds its limit')
    selected = {ident: [] for ident in rows}
    seen = set()
    for row in disagreements:
        _keys(row, ('id', 'claims'), 'Disagreement')
        ident = _id(row['id'])
        if ident in seen:
            _fail('duplicate', 'Duplicate disagreement IDs are invalid')
        seen.add(ident)
        refs = _references(row['claims'])
        if len(refs) < 2:
            _fail('disagreement', 'A disagreement requires at least two distinct claims')
        for ref in refs:
            target = rows.get(ref['id'])
            if target is None or {key: target[key] for key in ref} != ref:
                _fail('stale', 'Disagreement names a missing or stale claim')
        for ref in refs:
            selected[ref['id']].append({'id': ident, 'claims': refs})
    return {ident: sorted(items, key=lambda item: item['id']) for ident, items in selected.items()}


def evaluate(claims, *, disagreements=None):
    """Evaluate support applicability at one immutable snapshot.

    ``admissible`` means usable as an explicitly conditional premise or checked
    derivation, never empirically true. A conflict disables affected support;
    it never produces arbitrary conclusions or marks downstream claims false.
    Duplicate content from several models remains several unknown proposals.
    """
    rows, order = _index(claims)
    conflicts = _disagreements([] if disagreements is None else disagreements, rows)
    result = {}
    for ident in order:
        row = rows[ident]
        issues = []
        roots = {}
        declared = row['status']
        status = 'contested' if conflicts[ident] else declared
        if row['withdrawn']:
            issues.append({'code': 'withdrawn', 'id': ident})
            status = 'unknown'
        if status in ('contested', 'refuted'):
            issues.append({'code': status, 'id': ident})
        for ref in row['dependencies']:
            parent = rows.get(ref['id'])
            if parent is None:
                issues.append({'code': 'missing_dependency', 'ref': ref})
                continue
            if {key: parent[key] for key in ref} != ref:
                issues.append({'code': 'stale_dependency', 'ref': ref,
                               'current': {key: parent[key] for key in ref}})
                continue
            prior = result[ref['id']]
            if not prior['admissible']:
                issues.append({'code': 'unavailable_dependency', 'ref': ref})
            for root in prior['conditional_on']:
                roots[root['ref']['id']] = root
        passed = [check['id'] for check in row['checks'] if check['passed']]
        derivations = [check['id'] for check in row['checks']
                       if check['passed'] and check['scope'] == 'encoded_derivation']
        if row['origin'] == 'derived':
            if not derivations:
                issues.append({'code': 'no_checked_derivation', 'id': ident})
            if any(not check['passed'] for check in row['checks']):
                issues.append({'code': 'rejected_check', 'id': ident})
            admissible = not issues
            support = 'checked_derivation' if admissible else 'unavailable'
            if status not in ('contested', 'refuted'):
                status = 'conditional' if admissible else 'unknown'
        else:
            # Even a unanimous answer or schema pass remains an explicit premise.
            admissible = not issues
            support = 'premise' if admissible else 'unavailable'
            roots[ident] = {'ref': {key: row[key] for key in ('id', 'revision', 'sha256')},
                            'origin': row['origin'], 'status': status}
        result[ident] = {'id': ident, 'revision': row['revision'], 'sha256': row['sha256'],
                         'status': status, 'admissible': admissible, 'support': support,
                         'empirical_truth': 'not_established',
                         'conditional_on': [roots[key] for key in sorted(roots)],
                         'passed_receipt_ids': passed, 'derivation_receipt_ids': derivations,
                         'issues': issues, 'disagreements': conflicts[ident]}
    return {ident: result[ident] for ident in sorted(result)}


def context_manifest(claims, *, required, optional, budget, prefix, suffix, fixed_parts,
                     priorities=None, disagreements=None, unit='utf8_bytes'):
    """Pack complete provenance rows; required dependency closures never truncate.

    ``prefix`` and ``suffix`` are exact prompt text surrounding the context.
    ``fixed_parts`` must contain every other budgeted string, e.g. system prompt,
    serialized answer schema, definitions/feedback not already in prefix/suffix,
    and any host wrapper. The caller must not append uncounted text afterwards.
    Units are exactly bytes or Unicode code points, never estimated model tokens.
    Provider token limits require their own exact tokenizer/check.

    Optional rows are atomic with their dependency closure, selected by descending
    priority and then ID. Returned manifest metadata is external to the prompt;
    included prompt rows themselves contain claim/version/content hashes.
    """
    rows, _ = _index(claims)
    assessed = evaluate(claims, disagreements=disagreements)
    if type(budget) is not int or not 0 <= budget <= MAX_CONTEXT:
        _fail('budget', 'Invalid context budget')
    if type(unit) is not str or unit not in ('utf8_bytes', 'characters'):
        _fail('budget', 'Budget unit must be utf8_bytes or characters')
    if type(prefix) is not str or type(suffix) is not str or type(fixed_parts) is not list \
            or any(type(part) is not str for part in fixed_parts):
        _fail('budget', 'Exact prefix, suffix and all fixed strings are required')
    if len(fixed_parts) > MAX_REFS:
        _fail('limit', 'Too many fixed prompt parts')

    def measure(value):
        try:
            encoded = value.encode('utf-8')
            return len(encoded) if unit == 'utf8_bytes' else len(value)
        except UnicodeEncodeError:
            _fail('json', 'Prompt has an unpaired Unicode surrogate')

    for text in [prefix, suffix, *fixed_parts]:
        if measure(text) > MAX_CONTEXT:
            _fail('limit', 'Fixed prompt text exceeds the context limit')
    for names in (required, optional):
        if type(names) is not list or len(names) > MAX_CLAIMS:
            _fail('limit', 'Invalid context ID list')
        if any(type(ident) is not str or ident not in rows for ident in names):
            _fail('missing', 'Context requests an unknown claim ID')
        if len(set(names)) != len(names):
            _fail('duplicate', 'Duplicate context IDs are invalid')
    if set(required) & set(optional):
        _fail('duplicate', 'A context ID cannot be both required and optional')
    priorities = {} if priorities is None else priorities
    if type(priorities) is not dict or any(key not in rows or type(value) is not int
            or abs(value) > 1000000 for key, value in priorities.items()):
        _fail('priority', 'Priorities must be bounded integer weights for known IDs')
    rendered = {}
    for ident, row in rows.items():
        view = assessed[ident]
        rendered[ident] = _json({'id': ident, 'revision': row['revision'], 'sha256': row['sha256'],
                                'content_sha256': row['content_sha256'], 'origin': row['origin'],
                                'content': row['content'], 'status': view['status'],
                                'support': view['support'], 'conditional_on': view['conditional_on'],
                                'empirical_truth': view['empirical_truth'], 'issues': view['issues'],
                                'disagreements': view['disagreements']})

    def closure(names):
        found = set()
        pending = list(names)
        while pending:
            ident = pending.pop()
            if ident in found:
                continue
            if ident not in rows:
                _fail('missing', 'A selected context dependency is missing', {'id': ident})
            found.add(ident)
            pending.extend(ref['id'] for ref in rows[ident]['dependencies'])
            for conflict in assessed[ident]['disagreements']:
                pending.extend(ref['id'] for ref in conflict['claims'])
        return found

    header, footer = '\nCONTEXT CLAIMS (conditional evidence, not established truth):\n', '\nEND CONTEXT CLAIMS\n'

    def prompt(ids):
        return prefix + header + '\n'.join(rendered[ident] for ident in sorted(ids)) + footer + suffix

    fixed_cost = sum(measure(part) for part in fixed_parts)

    def cost(ids):
        return fixed_cost + measure(prompt(ids))

    mandatory = closure(required)
    minimum = cost(mandatory)
    if minimum > budget:
        _fail('required_context_overflow', 'Required context and fixed prompt text exceed the budget',
              {'budget': budget, 'required_size': minimum, 'fixed_size': cost(set()), 'unit': unit,
               'required': [reference(rows[ident]) for ident in sorted(mandatory)]})
    included = set(mandatory)
    candidates = closure(optional)
    excluded = {}
    for ident in sorted(optional, key=lambda key: (-priorities.get(key, 0), key)):
        needed = closure([ident])
        if cost(included | needed) <= budget:
            included.update(needed)
        else:
            excluded[ident] = 'optional_context_overflow'
    out = prompt(included)

    def manifest_row(ident):
        return {**reference(rows[ident]), 'content_sha256': rows[ident]['content_sha256']}

    return {'version': VERSION, 'unit': unit, 'budget': budget, 'used': cost(included),
            'fixed_size': cost(set()), 'prompt': out,
            'prompt_sha256': hashlib.sha256(out.encode('utf-8')).hexdigest(),
            'fixed_parts_sha256': [hashlib.sha256(part.encode('utf-8')).hexdigest() for part in fixed_parts],
            'included': [{**manifest_row(ident), 'required': ident in mandatory,
                          'reason': 'required_dependency_closure' if ident in mandatory else 'optional_dependency_closure'}
                         for ident in sorted(included)],
            'omitted': [{**manifest_row(ident), 'reason': excluded.get(ident, 'optional_dependency_not_selected')}
                        for ident in sorted((mandatory | candidates) - included)]}

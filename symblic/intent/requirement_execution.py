"""Requirement execution: what did a run's own checks observe about each recorded requirement?

What it is for
    An intent (symblic.intent.records) is compiled into a program, the program is handed off and run. This
    module joins the two afterwards, read-only: derive(state, artifact, handoff, coverage, native) checks that
    the handoff, the checked artifact, the coverage manifest (symblic.intent.coverage) and the run's own records
    (program.sym, meta.json, state.json, trace.jsonl, read by read_snapshot with bounded, no-follow reads) all
    belong to the same content revision, source, inputs and kernel; then, for every requirement, it counts the
    check receipts the run retained at the predicate's exact locations ('observed', 'partially_observed',
    'failed', 'unobserved', ...). view(row, coverage, run_folder) does the same for a stored intent row and a
    function that maps a run id to its folder. Anything malformed, stale or ambiguous stays 'unknown' with a
    fixed reason code; nothing is guessed.

What it is not
    It changes no record, starts nothing and never marks a run ready. Passing checks establish the encoded
    predicates on that exact source and those exact inputs, not the requirement's meaning or external truth;
    'intent_fidelity' stays 'unassessed' and 'owner_acceptance' 'not_established'. Saved records are checked
    for consistency, not authenticity.

Depends on: symblic.kernel (language, evidence, execution_pins, run) and symblic.intent.records. Used by: the
original host's interpreter API (integration/host/symblic_intent_api.py). Status: prototype with unit tests
over temporary run folders (tests/intent).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from collections import Counter

from symblic.kernel import language as S
from symblic.kernel import evidence as E
from symblic.kernel import execution_pins as X
from symblic.intent import records as I
from symblic.kernel import run as SR

VERSION = 1
MAX_FILE_BYTES = 8_000_000
MAX_TRACE_BYTES = 16_000_000
MAX_TRACE_ROWS = 50000
MAX_CHECKS = 20000
_ID = re.compile(r'[0-9a-f]{12}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_HASH = re.compile(r'(?:[0-9a-f]{16}|[0-9a-f]{64})\Z')


class Unavailable(ValueError):
    """Fixed diagnostic code, without caller contents."""


def _require(ok, code):
    if not ok:
        raise Unavailable(code)


def _canonical(value):
    # Reuse the native exact finite JSON bounds; bytes preserve bool/int identity.
    return X._json(value)


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _sha(value):
    return type(value) is str and bool(_SHA.fullmatch(value))


def _sealed(value, field='sha256', digest=E.digest):
    return (type(value) is dict and _sha(value.get(field)) and
            value[field] == digest({k: v for k, v in value.items() if k != field}))


def _read(directory_fd, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'native_file_bound')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        _require(len(raw) <= limit, 'native_file_bound')
        _require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'native_snapshot_changed')
        return raw


def _json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            _require(key not in out, 'duplicate_json_key')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Unavailable('nonfinite_json')))


def read_snapshot(folder):
    """Bounded regular-file reads only; no directory/store creation or unit probe."""
    fd = os.open(Path(folder), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = _read(fd, 'state.json', MAX_FILE_BYTES)
        meta = _json(_read(fd, 'meta.json', MAX_FILE_BYTES))
        source = _read(fd, 'program.sym', 400000).decode('utf-8')
        trace_raw = _read(fd, 'trace.jsonl', MAX_TRACE_BYTES)
        _require(not trace_raw or trace_raw.endswith(b'\n'), 'partial_trace')
        lines = trace_raw.splitlines()
        _require(len(lines) <= MAX_TRACE_ROWS, 'trace_row_bound')
        trace = [_json(line) for line in lines if line.strip()]
        _require(before == _read(fd, 'state.json', MAX_FILE_BYTES), 'native_snapshot_changed')
        return {'source': source, 'meta': meta, 'state': _json(before), 'trace': trace}
    finally:
        os.close(fd)


def _base(coverage):
    requirements = []
    if (type(coverage) is dict and type(coverage.get('requirements')) is list and
            len(coverage['requirements']) <= 64):
        for row in coverage['requirements']:
            if type(row) is not dict or type(row.get('id')) is not str or type(row.get('status')) is not str:
                continue
            requirements.append({'id': row['id'], 'mapping_status': row['status'],
                'predicate_origin': row.get('predicate_origin', 'unrecorded'),
                'status': 'retired' if row['status'] == 'retired' else 'unobserved',
                'passed_checks': 0, 'failed_checks': 0, 'receipt_ids': [],
                'locations': [], 'intent_fidelity': 'unassessed', 'owner_acceptance': 'not_established'})
    return {'version': VERSION, 'scope': 'linked_run_retained_encoded_checks',
            'status': 'unknown', 'reason': 'not_available', 'requirements': requirements,
            'intent_fidelity': 'unassessed', 'owner_acceptance': 'not_established',
            'limits': ['Observed checks apply only to the saved source and exact inputs.',
                       'Retained receipts establish encoded predicates, not requirement meaning or external truth.',
                       'Caller-owned saved records are checked for consistency, not cryptographic authenticity.',
                       'Check receipts lack module/column/call identity; ambiguous locations remain unassessed.']}


def unavailable(reason='metadata_unavailable'):
    out = _base(None)
    out['reason'] = reason
    return out


def _check(receipt, source_hash, kernel):
    _require(type(receipt) is dict and _sealed(receipt, 'id'), 'check_receipt_integrity')
    _require(type(receipt.get('version')) is int and receipt['version'] == E.VERSION,
             'check_receipt_version')
    _require(type(receipt.get('passed')) is bool and type(receipt.get('line')) is int and receipt['line'] > 0,
             'check_receipt_types')
    _require(receipt.get('source_sha256') == source_hash and _same(receipt.get('kernel'), kernel),
             'check_receipt_scope')
    _require(receipt.get('kind') in ('assert', 'ensure', 'expect') and
             receipt.get('scope') == 'encoded_predicate' and _sha(receipt.get('predicate_sha256')) and
             type(receipt.get('predicate')) is str, 'check_receipt_schema')
    bindings = receipt.get('bindings')
    _require(type(bindings) is list and len(bindings) <= 10000, 'check_bindings')
    names = set()
    for binding in bindings:
        _require(type(binding) is dict and set(binding) == {'name', 'hash'} and
                 type(binding['name']) is str and type(binding['hash']) is str and
                 bool(_HASH.fullmatch(binding['hash'])) and binding['name'] not in names, 'check_bindings')
        names.add(binding['name'])
    return (receipt['kind'], receipt['line'], receipt['predicate_sha256'])


def derive(state, artifact, handoff, coverage, native):
    """Pure consistency join. Malformed, stale, incomplete or ambiguous data stays explicit."""
    out = _base(coverage)
    try:
        _canonical([state, artifact, handoff, coverage])
        _require(type(artifact) is dict and type(coverage) is dict and _sealed(coverage, digest=I.digest) and
                 type(coverage.get('requirements')) is list and len(coverage['requirements']) <= 64 and
                 len(out['requirements']) == len(coverage['requirements']), 'mapping_unavailable')
        _require(type(handoff) is dict and handoff.get('status') == 'started' and
                 type(handoff.get('run_id')) is str and bool(_ID.fullmatch(handoff['run_id'])), 'linked_run_unavailable')
        env = handoff.get('envelope')
        _require(type(env) is dict and _sealed(env, 'key', I.digest) and env['key'] == handoff.get('key'), 'handoff_integrity')
        _require(type(state.get('content_revision')) is int and
                 type(handoff.get('content_revision')) is int and type(env.get('content_revision')) is int and
                 type(artifact.get('content_revision')) is int and
                 state['content_revision'] == handoff['content_revision'] == env['content_revision'] == artifact.get('content_revision') and
                 I.content_digest(state) == env.get('intent_content_sha256') == artifact.get('intent_content_sha256') == coverage.get('intent_content_sha256'),
                 'stale_intent_revision')
        source, inputs = artifact.get('source'), artifact.get('inputs')
        _require(type(source) is str and type(inputs) is dict and len(source.encode('utf-8')) <= 400000, 'artifact_schema')
        source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
        input_hash = I.digest(inputs)
        _require(source_hash == artifact.get('source_sha256') == env.get('source_sha256') == coverage.get('source_sha256') and
                 input_hash == artifact.get('input_sha256') == env.get('input_sha256') == coverage.get('input_sha256') and
                 env.get('source') == source and _same(env.get('inputs'), inputs), 'source_or_input_scope')
        _require(_same(artifact.get('coverage'), coverage) and _same(env.get('coverage'), coverage), 'mapping_changed')
        # The existing manifest validator enforces exact location types, bounds,
        # distinct locations, requirement IDs, origin and raw predicate hashes.
        mappings = {r['id']: r['locations'] for r in coverage['requirements']}
        rebuilt = I.coverage_manifest(state, source, inputs, mappings, version=coverage.get('version'))
        _require(_same(coverage, rebuilt), 'mapping_schema')
        pins = handoff.get('execution_pins')
        _require(type(pins) is dict and _sealed(pins), 'execution_pins_integrity')
        # A parser/runtime mismatch is unknown, never a weakening of archived pins.
        X.validate(pins, source, inputs)
        out['binding'] = {'run_id': handoff['run_id'], 'handoff_key': env['key'],
            'content_revision': state['content_revision'], 'intent_content_sha256': I.content_digest(state),
            'source_sha256': source_hash, 'input_sha256': input_hash, 'execution_pins_sha256': pins['sha256']}
        if native is None:
            raise Unavailable('native_snapshot_unavailable')
        _require(type(native) is dict and native.get('source') == source, 'native_source_mismatch')
        meta, report, trace = native.get('meta'), native.get('state'), native.get('trace')
        _require(type(meta) is dict and type(report) is dict and type(trace) is list and
                 len(trace) <= MAX_TRACE_ROWS, 'native_schema')
        _canonical(meta); _canonical(report)
        _require(_same(meta.get('inputs'), inputs) and
                 meta.get('inputs_source_sha256') == source_hash, 'native_input_mismatch')
        _require(type(meta.get('prompt')) is str and meta['prompt'].startswith('[Symblic intent '+env['key']+']\n'),
                 'native_handoff_mismatch')
        options = meta.get('options')
        _require(type(options) is dict and _same(options.get('execution_pins'), pins), 'native_pins_mismatch')
        out['run_status'] = report.get('status') if type(report.get('status')) is str else 'unknown'
        if report.get('status') not in ('done', 'failed'):
            out.update(status='partial', reason='final_retained_evidence_pending')
            return out
        evidence = report.get('evidence')
        _require(type(evidence) is dict and type(evidence.get('version')) is int and evidence['version'] == E.VERSION and
                 evidence.get('source_sha256') == source_hash and type(evidence.get('checks')) is list and
                 len(evidence['checks']) <= MAX_CHECKS, 'retained_evidence_unavailable')
        kernel = report.get('kernel')
        _require(_same(kernel, S.kernel_id()), 'native_kernel_mismatch')
        _require(type(report.get('execution_id')) is str and bool(re.fullmatch(r'[0-9a-f]{32}', report['execution_id'])),
                 'execution_identity_missing')
        out['binding']['execution_id'] = report['execution_id']
        nodes = list(S.walk(S.parse(source)['statements']))
        # Imported routines can carry module-local line numbers. Native v1 check
        # receipts cannot disambiguate them, so do not infer root occurrence identity.
        imported = any(n.k == 'import' for n in nodes)
        locations, positions = {}, {}
        for node in nodes:
            if node.k in ('assert', 'ensure', 'expect'):
                key = (node.k, node.line, E.digest(E.syntax(node.cond)))
                locations.setdefault(key, []).append(node)
                positions.setdefault((node.k, node.line, node.col), []).append((key, node))
        traced, last_sequence, trace_bytes = Counter(), 0, 2
        for row in trace:
            trace_bytes += len(_canonical(row)) + 1
            _require(trace_bytes <= MAX_TRACE_BYTES, 'trace_byte_bound')
            _require(type(row) is dict and type(row.get('sequence')) is int and
                     row['sequence'] > last_sequence, 'trace_sequence')
            last_sequence = row['sequence']
            receipt = row.get('check')
            if receipt is None:
                continue
            _check(receipt, source_hash, kernel)
            _require(type(row.get('line')) is int and row['line'] == receipt['line'] and
                     row.get('kind') == receipt['kind'] and _same(row.get('kernel'), kernel) and
                     row.get('status') in (('ok',) if receipt['passed'] else ('warn', 'failed')),
                     'trace_check_mismatch')
            traced[_canonical(receipt)] += 1
        retained, by_location = Counter(), {}
        for receipt in evidence['checks']:
            key = _check(receipt, source_hash, kernel)
            if not imported and len(locations.get(key, [])) == 1:
                _require(receipt['predicate'] == SR._src(locations[key][0]), 'check_predicate_text_mismatch')
            encoded = _canonical(receipt); retained[encoded] += 1
            _require(retained[encoded] <= traced[encoded], 'retained_check_missing_trace')
            by_location.setdefault(key, []).append(receipt)
        for row, mapping in zip(out['requirements'], coverage['requirements']):
            if row['status'] == 'retired':
                continue
            requirement = next(r for r in state['requirements'] if r['id'] == row['id'])
            predicate = requirement.get('predicate')
            expected_ast = None
            if mapping['locations']:
                declared = S.parse('assert '+predicate)['statements']
                _require(len(declared) == 1 and declared[0].k == 'assert' and
                         declared[0].because is None and declared[0].on_fail == 'fail', 'mapping_predicate_schema')
                expected_ast = E.digest(E.syntax(declared[0].cond))
            for location in mapping['locations']:
                matches = positions.get((location['kind'], location['line'], location['col']), [])
                result = {**location, 'status': 'unobserved', 'passed_checks': 0, 'failed_checks': 0, 'receipt_ids': []}
                _require(all(key[2] == expected_ast for key, _node in matches), 'mapping_predicate_mismatch')
                if len(matches) != 1 or imported or len(locations.get(matches[0][0], [])) != 1:
                    result['status'] = 'ambiguous'
                else:
                    receipts = by_location.get(matches[0][0], [])
                    result['passed_checks'] = sum(r['passed'] for r in receipts)
                    result['failed_checks'] = sum(not r['passed'] for r in receipts)
                    result['receipt_ids'] = sorted({r['id'] for r in receipts})
                    if receipts:
                        result['status'] = 'observed_fail' if result['failed_checks'] else 'observed_pass'
                row['locations'].append(result)
            row['passed_checks'] = sum(r['passed_checks'] for r in row['locations'])
            row['failed_checks'] = sum(r['failed_checks'] for r in row['locations'])
            row['receipt_ids'] = sorted({i for r in row['locations'] for i in r['receipt_ids']})
            statuses = [r['status'] for r in row['locations']]
            row['status'] = ('observed_fail' if row['failed_checks'] else 'ambiguous' if 'ambiguous' in statuses
                             else 'partially_observed' if row['passed_checks'] and 'unobserved' in statuses
                             else 'observed_pass' if row['passed_checks'] else 'unobserved')
        out.update(status='joined', reason='retained_checks_matched',
                   retained_checks=len(evidence['checks']),
                   trace_only_checks=sum(traced.values())-sum(retained.values()),
                   trace_rows=len(trace))
        _canonical(out)
        return out
    except Unavailable as exc:
        out['reason'] = str(exc)
        out['status'] = 'stale' if str(exc) == 'stale_intent_revision' else 'unknown'
    except (S.SymblicError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        out['reason'] = 'metadata_invalid_or_runtime_unavailable'
        out['status'] = 'unknown'
    # Never expose partially computed successful rows after a later join refusal.
    out['requirements'] = _base(coverage)['requirements']
    return out


def view(row, coverage, run_folder):
    """Validate linkage first, then read only that native run; never scan alternatives."""
    state, artifact = row['state'], row.get('artifact')
    handoff = row['handoffs'][-1] if row.get('handoffs') else None
    preliminary = derive(state, artifact, handoff, coverage, None)
    if preliminary['reason'] != 'native_snapshot_unavailable':
        return preliminary
    try:
        native = read_snapshot(run_folder(handoff['run_id']))
    except Unavailable as exc:
        preliminary['reason'] = str(exc)
        return preliminary
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        preliminary['reason'] = 'native_snapshot_unavailable'
        return preliminary
    return derive(state, artifact, handoff, coverage, native)

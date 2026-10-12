"""Differential questions for spec sheets: run several candidate implementations on new probe calls and report where
they disagree, without choosing an answer. No model or provider is called.

What it is for: finding what a spec sheet leaves open. Two implementations that both pass every example of a sheet
may still disagree on inputs the examples do not cover; each such disagreement is a question the sheet's author has
to answer (a missing example), not something a majority vote should settle.

    compare(sheet, candidates=[{'label': ..., 'source': text_or_pieces}],
            probes=[expression_or_{id, expression, unit_id?}], deadline_seconds=30, externals=())

Every candidate receives all exposed unit checks, using that unit's setup. Only candidates passing every exposed check
enter differential grouping. Probes run in fresh JavaScript sandbox contexts (symblic.js.check), with the selected
unit setup or no setup. Errors are unresolved observations, never alternative answer votes. Returned questions have
no chosen expected value. Attribution labels are caller supplied, not evidence of independent models or
authenticated origins. Results are compared as canonical JSON values (object order and number spelling ignored), not
as complete JavaScript observational equivalence.

Command line: python3 -m symblic.spec.compare REQUEST.json [--json] (review only; the request file is not changed).
Depends on: symblic.kernel.language, symblic.js.check, symblic.spec (sheets, contracts).
Requirements: the JavaScript sandbox (Node.js 22 and Linux Landlock); without it every probe is "unavailable".
"""
from __future__ import annotations

import decimal
import hashlib
import json
import math
import time
from pathlib import Path

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.spec import sheets as SP
from symblic.spec import contracts as C

VERSION = 1
MAX_CANDIDATES = 8
MAX_PROBES = 64
MAX_EVALUATIONS = 2048
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_VALUE_BYTES = 32768
MAX_RETAINED_VALUE_BYTES = 1024 * 1024
MAX_BATCH_OUTPUT_BYTES = 512 * 1024
MAX_VALUE_NODES = 16384
MAX_VALUE_DEPTH = 32
PROBE_BATCH = 8
# the sources whose bytes identify a comparison's runtime, as paths from the repository root
SOURCE_FILES = ('symblic/spec/compare.py', 'symblic/spec/sheets.py', 'symblic/spec/contracts.py',
                'symblic/js/check.py')
_ROOT = Path(__file__).resolve().parents[2]


class CompareError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}

    def as_dict(self):
        return {'code': self.code, 'message': str(self), 'details': self.details}


def _fail(code, message, details=None):
    raise CompareError(code, message, details)


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _text(value, limit, label, *, nonempty=True):
    if type(value) is not str or len(value) > limit or (nonempty and not value.strip()):
        _fail('input', f'{label} must be bounded text.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        _fail('input', f'{label} must be valid Unicode.')
    return value


def _keys(row, required, optional=()):
    if type(row) is not dict or not set(required) <= set(row) or set(row) - set(required) - set(optional):
        _fail('input', 'Missing or unknown fields.', {'required': list(required), 'optional': list(optional)})


def _source_hashes():
    return {name: hashlib.sha256((_ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def runtime_identity():
    return {'version': VERSION, 'javascript': JS.VERSION, 'assets': JS.asset_hashes(),
            'node_version': JS.node_version(), 'sources': _source_hashes(),
            'source_identity_scope': 'disk_snapshot_only_not_loaded_python_code_attestation',
            'case_milliseconds': JS.CASE_MS, 'heap_megabytes': JS.HEAP_MB,
            'value_semantics': 'symblic.js.check JSON equality, not complete JavaScript observational equivalence'}


def _parse_value(raw):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError('Duplicate JSON object key')
            output[key] = value
        return output
    value = json.loads(raw, parse_float=decimal.Decimal, object_pairs_hook=pairs,
                       parse_constant=lambda _x: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))
    count = 0
    def canonical(item, depth=0):
        nonlocal count
        count += 1
        if count > MAX_VALUE_NODES or depth > MAX_VALUE_DEPTH:
            raise ValueError('JSON result structure exceeds the limit')
        if item is None:
            return ['null']
        if type(item) is bool:
            return ['boolean', item]
        if type(item) in (int, decimal.Decimal):
            number = decimal.Decimal(item)
            if not number.is_finite():
                raise ValueError('Nonfinite JSON number')
            sign, digits, exponent = number.as_tuple()
            digits = list(digits)
            if not any(digits):
                sign, digits, exponent = 0, [0], 0
            else:
                while len(digits) > 1 and digits[-1] == 0:
                    digits.pop(); exponent += 1
            return ['number', sign, ''.join(map(str, digits)), exponent]
        if type(item) is str:
            return ['string', item]
        if type(item) is list:
            return ['array', [canonical(child, depth + 1) for child in item]]
        if type(item) is dict:
            return ['object', [[key, canonical(item[key], depth + 1)] for key in sorted(item)]]
        raise ValueError('Unsupported JSON output')
    return value, _digest(canonical(value))


def _prepare(sheet, candidates, probes, externals):
    _text(sheet, S.MAX_SOURCE, 'Spec sheet')
    try:
        plan = C.plan(SP.parse(sheet), externals=externals)
    except (SP.SheetError, C.ContractError) as error:
        _fail('spec', str(error))
    if not plan['sheet']['template']['file'].lower().endswith('.js'):
        _fail('spec', 'Differential comparison requires one assembled .js output spec.')
    if type(candidates) is not list or not 1 <= len(candidates) <= MAX_CANDIDATES:
        _fail('input', 'Supply 1..8 explicitly labeled candidate sources.')
    normalized = []; labels = set()
    for candidate in candidates:
        _keys(candidate, ('label', 'source'))
        label = _text(candidate['label'], 128, 'Candidate label')
        if label in labels:
            _fail('input', 'Candidate labels must be unique.')
        labels.add(label)
        source = candidate['source']
        if type(source) not in (str, list) or (type(source) is list and any(type(piece) is not str for piece in source)):
            _fail('input', 'Candidate source must be text or a list of exact text pieces.')
        try:
            pieces = JS._pieces(source, 'candidate source', None)
        except S.SymblicError as error:
            _fail('input', error.message)
        for piece in pieces:
            _text(piece, JS.MAX_SOURCE, 'Candidate piece', nonempty=False)
        normalized.append({'label': label, 'pieces': pieces,
                           'source_sha256': _digest(pieces),
                           'piece_sha256': [hashlib.sha256(piece.encode()).hexdigest() for piece in pieces]})
    if type(probes) is not list or not 1 <= len(probes) <= MAX_PROBES:
        _fail('input', 'Supply 1..64 explicit probe expressions.')
    units = {row['id']: row for row in plan['units']}; probe_ids = set(); probes_out = []
    for index, supplied in enumerate(probes, 1):
        probe = {'id': 'probe-' + str(index), 'expression': supplied} if type(supplied) is str else supplied
        _keys(probe, ('id', 'expression'), ('unit_id',))
        ident = _text(probe['id'], 128, 'Probe ID')
        if ident in probe_ids:
            _fail('input', 'Probe IDs must be unique.')
        probe_ids.add(ident)
        expression = _text(probe['expression'], JS.MAX_CALL, 'Probe expression')
        unit_id = probe.get('unit_id')
        if unit_id is not None and (type(unit_id) is not str or unit_id not in units):
            _fail('input', 'A probe setup must name an exact plan unit ID.')
        setup = units[unit_id]['contract']['unit']['setup'] if unit_id else ''
        probes_out.append({'id': ident, 'expression': expression, 'unit_id': unit_id, 'setup': setup,
                           'probe_sha256': _digest({'expression': expression, 'unit_id': unit_id, 'setup': setup})})
    checks = []
    for unit_id in plan['order']:
        unit = units[unit_id]['contract']['unit']
        try:
            cases = JS._cases(unit['examples'], None)
        except S.SymblicError as error:
            _fail('spec', error.message)
        for index, (expression, expected) in enumerate(cases, 1):
            # Use the stricter output reader for expected data too: never eval it.
            try:
                _parse_value(expected)
            except (ValueError, RecursionError, decimal.InvalidOperation):
                _fail('spec', 'An exposed expected value exceeds the bounded exact JSON domain.')
            checks.append({'id': unit_id + ':' + str(index), 'unit_id': unit_id, 'expression': expression,
                           'expected_json': expected, 'setup': unit['setup'],
                           'check_sha256': _digest({'expression': expression, 'expected_json': expected, 'setup': unit['setup']})})
    evaluations = len(normalized) * (len(checks) + len(probes_out))
    if evaluations > MAX_EVALUATIONS:
        _fail('work_limit', 'Comparison exceeds 2048 declared candidate-case evaluations.')
    for candidate in normalized:
        for setup in {row['setup'] for row in checks + probes_out}:
            try:
                JS._pieces(([setup] if setup else []) + candidate['pieces'], 'candidate with setup', None)
            except S.SymblicError as error:
                _fail('input', error.message)
    if len(_json({'sheet': sheet, 'candidates': candidates, 'probes': probes, 'externals': list(externals)})) > MAX_REQUEST_BYTES:
        _fail('input', 'Comparison request exceeds 4 MiB encoded JSON.')
    return plan, normalized, checks, probes_out, evaluations


def _unknown(code, message, *, status='unresolved'):
    return {'status': status, 'kind': code, 'message': message[:500]}


def compare(sheet, candidates, probes, *, deadline_seconds=30, externals=()):
    """Return recorded finite comparisons and proposed owner questions, never a new spec."""
    if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or not 0.1 <= deadline_seconds <= 120:
        _fail('budget', 'deadline_seconds must be a finite number from 0.1 to 120.')
    started = time.monotonic(); deadline = started + deadline_seconds
    plan, candidates, checks, probes, evaluations = _prepare(sheet, candidates, probes, externals)
    try:
        runtime = runtime_identity(); runtime_error = None
    except (S.SymblicError, OSError) as error:
        runtime = {'version': VERSION, 'unavailable': True}
        runtime_error = _unknown(getattr(error, 'kind', 'unavailable'), str(error))
    by_label = {row['label']: {'label': row['label'], 'source_sha256': row['source_sha256'],
                 'piece_sha256': row['piece_sha256'], 'checks': [], 'probes': []} for row in candidates}
    requested = retained = 0; fatal = runtime_error

    def execute(candidate, rows):
        nonlocal requested, retained, fatal
        if fatal:
            return [dict(fatal) for _ in rows]
        if time.monotonic() >= deadline:
            return [_unknown('aggregate_deadline', 'No time remained for this observation.', status='budget') for _ in rows]
        setup = rows[0]['setup']
        pieces = ([setup] if setup else []) + candidate['pieces']
        requested += len(rows)
        try:
            raw_results = JS.evaluate(pieces, [row['expression'] for row in rows], deadline=deadline,
                                      max_output_bytes=MAX_BATCH_OUTPUT_BYTES)
        except S.SymblicError as error:
            status = 'budget' if error.kind in ('budget', 'limit') else 'unresolved'
            failure = _unknown(error.kind, error.message, status=status)
            if error.kind in ('unavailable', 'version'):
                fatal = failure
            return [dict(failure) for _ in rows]
        except OSError:
            fatal = _unknown('unavailable', 'The sandbox process could not be started or read.')
            return [dict(fatal) for _ in rows]
        if type(raw_results) is not list or len(raw_results) != len(rows):
            return [_unknown('protocol', 'The sandbox returned the wrong number of observations.') for _ in rows]
        out = []
        for raw in raw_results:
            if type(raw) is not dict or type(raw.get('ok')) is not bool:
                out.append(_unknown('protocol', 'Malformed sandbox observation.')); continue
            if raw['ok'] is not True:
                kind = raw.get('kind') if type(raw.get('kind')) is str else 'error'
                error = raw.get('error') if type(raw.get('error')) is str else 'No valid JSON result.'
                out.append(_unknown(kind, error, status='budget' if kind == 'timeout' else 'unresolved')); continue
            text = raw.get('value')
            if type(text) is not str:
                out.append(_unknown('invalid_json', 'The sandbox result was not JSON text.')); continue
            size = len(text.encode('utf-8', errors='surrogatepass'))
            if size > MAX_VALUE_BYTES or retained + size > MAX_RETAINED_VALUE_BYTES:
                out.append(_unknown('output_limit', 'The JSON result exceeded its per-value or aggregate output bound.', status='budget'))
                continue
            try:
                _value, semantic_hash = _parse_value(text)
            except (ValueError, RecursionError, decimal.InvalidOperation):
                out.append(_unknown('invalid_json', 'The result is not bounded unambiguous JSON.')); continue
            retained += size
            out.append({'status': 'value', 'value_json': text, 'value_sha256': semantic_hash,
                        'json_text_sha256': hashlib.sha256(text.encode('utf-8', errors='surrogatepass')).hexdigest()})
        return out

    # Unit-order rounds avoid finishing every unit of the first candidate before
    # considering another candidate. Every exposed case is retained in the report.
    for unit_id in plan['order']:
        rows = [row for row in checks if row['unit_id'] == unit_id]
        for candidate in candidates:
            outcomes = execute(candidate, rows)
            for check, outcome in zip(rows, outcomes):
                passed = None
                if outcome['status'] == 'value':
                    passed = JS.same(_parse_value(outcome['value_json'])[0], _parse_value(check['expected_json'])[0])
                by_label[candidate['label']]['checks'].append({'id': check['id'], 'check_sha256': check['check_sha256'],
                                                              'passed': passed, **outcome})
    for row in by_label.values():
        answers = [check['passed'] for check in row['checks']]
        row['exposed_checks'] = 'passed' if all(value is True for value in answers) else (
            'failed' if any(value is False for value in answers) else 'unresolved')
        row['eligible_for_comparison'] = row['exposed_checks'] == 'passed'
    # Consecutive equal-setup probes share a bounded process request; cases still
    # run in separate fresh V8 contexts. Candidate order remains caller-visible.
    chunks = []
    for probe in probes:
        if not chunks or len(chunks[-1]) >= PROBE_BATCH or chunks[-1][0]['setup'] != probe['setup']:
            chunks.append([])
        chunks[-1].append(probe)
    for rows in chunks:
        for candidate in candidates:
            target = by_label[candidate['label']]
            outcomes = execute(candidate, rows) if target['eligible_for_comparison'] else [
                _unknown('exposed_checks_not_passed', 'Candidate did not pass every exposed check.', status='not_evaluated') for _ in rows]
            target['probes'].extend({'id': probe['id'], **outcome} for probe, outcome in zip(rows, outcomes))
    compared = []; questions = []
    for index, probe in enumerate(probes):
        groups = []; unresolved = []
        for candidate in candidates:
            row = by_label[candidate['label']]; outcome = row['probes'][index]
            if not row['eligible_for_comparison']:
                continue
            if outcome['status'] != 'value':
                unresolved.append({'label': row['label'], **outcome}); continue
            value = _parse_value(outcome['value_json'])[0]
            group = next((g for g in groups if JS.same(value, _parse_value(g['value_json'])[0])), None)
            if group is None:
                group = {'value_json': outcome['value_json'], 'value_sha256': outcome['value_sha256'], 'labels': []}
                groups.append(group)
            group['labels'].append(row['label'])
        observed = sum(len(group['labels']) for group in groups)
        status = 'divergent' if len(groups) >= 2 else 'agreement' if observed >= 2 and not unresolved else 'unresolved'
        record = {'id': probe['id'], 'expression': probe['expression'], 'unit_id': probe['unit_id'],
                  'probe_sha256': probe['probe_sha256'], 'status': status, 'alternatives': groups,
                  'unresolved': unresolved, 'eligible_candidates': sum(r['eligible_for_comparison'] for r in by_label.values()),
                  'observed_candidates': observed}
        compared.append(record)
        if status == 'divergent':
            questions.append({'probe_id': probe['id'], 'expression': probe['expression'], 'unit_id': probe['unit_id'],
                              'question': 'What should this expression return under the intended specification?',
                              'alternatives': groups, 'expected_json': None, 'requires_owner_resolution': True})
    drift = False
    if not runtime_error:
        try:
            drift = _source_hashes() != runtime['sources'] or JS.asset_hashes() != runtime['assets']
        except (OSError, S.SymblicError):
            drift = True
    if drift:
        questions = []
        for row in compared:
            row.update(status='unresolved', runtime_drift=True)
    exact_groups = {}
    for candidate in candidates:
        exact_groups.setdefault(candidate['source_sha256'], []).append(candidate['label'])
    unresolved_count = sum(outcome['status'] in ('budget', 'unresolved') for row in by_label.values()
                           for outcome in row['checks'] + row['probes'])
    result = {'version': VERSION, 'kind': 'spec_differential_review', 'status': 'partial' if unresolved_count or drift else 'complete',
              'sheet_sha256': hashlib.sha256(sheet.encode()).hexdigest(), 'plan_sha256': plan['sha256'],
              'checks_sha256': _digest(checks), 'probes_sha256': _digest(probes), 'runtime': runtime,
              'runtime_sha256': _digest(runtime), 'runtime_drift': drift,
              'candidate_order': [row['label'] for row in candidates], 'candidates': list(by_label.values()),
              'exact_source_agreement': {'all_equal': len(exact_groups) == 1,
                  'groups': [{'source_sha256': digest, 'labels': labels} for digest, labels in exact_groups.items()],
                  'scope': 'exact_ordered_script_pieces_including_boundaries'},
              'probes': compared, 'proposed_examples': questions,
              'work': {'declared_evaluations': evaluations, 'requested_evaluations': requested,
                       'retained_value_bytes': retained, 'deadline_seconds': deadline_seconds,
                       'elapsed_seconds': round(time.monotonic() - started, 6), 'max_evaluations': MAX_EVALUATIONS},
              'assurance': {'scope': 'finite_declared_examples_and_supplied_probes', 'universal_equivalence': 'not_established',
                            'attribution': 'caller_supplied_labels_not_authenticated_independence',
                            'expected_answers': 'not_chosen', 'spec_modified': False,
                            'probe_order': 'caller_order_in_bounded_chunks; deadline may censor later observations',
                            'output_semantics': 'existing JS adapter maps undefined to null and nonfinite numbers to tagged JSON'}}
    return {**result, 'sha256': _digest(result)}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Compare assembled JavaScript candidates without model calls.')
    parser.add_argument('request', help='JSON object containing sheet, candidates, probes and optional deadline_seconds/externals')
    parser.add_argument('--agent-json', '--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        with Path(args.request).open('rb') as stream:
            raw = stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            _fail('input', 'Request file exceeds 4 MiB.')
        request = json.loads(raw)
        _keys(request, ('sheet', 'candidates', 'probes'), ('deadline_seconds', 'externals'))
        print(json.dumps(compare(**request), ensure_ascii=True))
        return 0
    except (CompareError, ValueError, OSError, S.SymblicError, RecursionError) as error:
        print(json.dumps({'ok': False, 'error': error.as_dict() if hasattr(error, 'as_dict') else {'message': str(error)}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

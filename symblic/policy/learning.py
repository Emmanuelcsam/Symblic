"""Policy selection: pick one of a few predeclared policies from recorded outcomes, then check it on held-out cases.

What it is for
    "Learning" here is deliberately small and auditable. A training plan lists a finite set of candidate
    policies (opaque JSON values pinned by SHA-256, one of them the baseline), the training cases (case, family,
    input and exposure hashes), a budget and an integer objective (score, call and cost weights, how to treat
    unknown cost, a minimum held-out gain). Records give, for every (candidate, case) pair, a status, an
    integer score and the calls and cost units of every attempt.

    select(plan, records, expected_plan_hash=, expected_records_hash=)
        picks the candidate with the highest training utility (ties: lowest SHA-256), charging a missing or
        unknown measurement at the full budget, and returns the policy as canonical JSON plus a receipt.
    validate_split(training_cases, heldout_cases)
        refuses held-out cases that share any case, family, input or exposure hash with training.
    evaluate_heldout(..., pins=)
        replays the frozen training choice, audits the split and compares the chosen policy with the baseline on
        held-out records only. 'observed_improvement' requires complete accounting and the declared gain.

What it is not
    No gradient descent or fitted model: the result is always one of the listed candidates. Held-out data never
    changes the choice. Scores and costs are whatever the caller recorded ('measurement_status':
    'host_declared_not_verified'); confidence and causality are always 'not_established'. Hashes detect
    changes against the caller's pins; they do not prove when a plan was written.

Command line (bounded JSON files in, one JSON line out):
    python3 -m symblic.policy.learning hash FILE
    python3 -m symblic.policy.learning select --plan P --records R --pins PINS
    python3 -m symblic.policy.learning evaluate --training-plan --training-records --selection --heldout-plan
                                                --heldout-records --pins

Depends on: the standard library (symblic.kernel.identity records the import identity). Used by:
symblic.policy.store and symblic.policy.graph. Status: prototype with unit and exhaustive small-case tests
(tests/policy); no real-model routing improvement is claimed.
"""

# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
import hashlib
import json
import re
from pathlib import Path

_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

VERSION = 1
METHOD = 'predeclared-finite-candidate-selection'
MAX_BYTES = 2_000_000
MAX_NODES = 50000
MAX_DEPTH = 40
MAX_TEXT = 16384
MAX_INT = 10**12
MAX_JSON_INT = 10**30  # room for exact aggregated receipts
MAX_ASSIGNMENTS = 1024
MAX_CANDIDATES = 32
MAX_CASES = 256
MAX_ATTEMPTS = 64
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class PolicyError(ValueError):
    """Stable finite error code, without caller-controlled excerpts."""


def _fail(code):
    raise PolicyError(code)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _scan(value):
    active = set()
    stack = [(value, 0, False)]
    nodes = size = 0
    scheduled = 1
    while stack:
        item, depth, end = stack.pop()
        if end:
            active.remove(id(item))
            continue
        nodes += 1
        size += 2
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            _fail('structure_limit')
        typ = type(item)
        if typ in (dict, list):
            if id(item) in active:
                _fail('cycle')
            scheduled += len(item) * (2 if typ is dict else 1)
            if scheduled > MAX_NODES:
                _fail('structure_limit')
            active.add(id(item))
            stack.append((item, depth, True))
            if typ is dict:
                for key, val in item.items():
                    if type(key) is not str:
                        _fail('json_type')
                    stack.extend(((key, depth + 1, False), (val, depth + 1, False)))
            else:
                stack.extend((val, depth + 1, False) for val in item)
        elif typ is str:
            if len(item) > MAX_TEXT:
                _fail('text_limit')
            try:
                size += len(_json(item).encode('utf-8'))
            except UnicodeError:
                _fail('unicode')
        elif typ is int:
            if abs(item) > MAX_JSON_INT:
                _fail('integer_limit')
            size += 34
        elif item is None or typ is bool:
            size += 5
        else:
            _fail('json_type')
        if size > MAX_BYTES:
            _fail('byte_limit')


def digest(value):
    """SHA256 of bounded canonical exact JSON, for trusted predeclaration pins."""
    try:
        _scan(value)
        return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()
    except RecursionError:
        raise PolicyError('structure_limit') from None


def _fields(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        _fail('schema')


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail('hash')


def _pin(value, expected):
    _sha(expected)
    if digest(value) != expected:
        _fail('pin_mismatch')


def _integer(value, minimum=0, maximum=MAX_INT):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail('integer')


def _version(value):
    if type(value) is not int or value != VERSION:
        _fail('version')


def _cases(cases):
    if type(cases) is not list or not 1 <= len(cases) <= MAX_CASES:
        _fail('cases')
    indexed = {}
    for case in cases:
        _fields(case, 'case_hash family_hash input_hash exposure_hashes')
        for key in ('case_hash', 'family_hash', 'input_hash'):
            _sha(case[key])
        exposure = case['exposure_hashes']
        if type(exposure) is not list or len(exposure) > MAX_CASES:
            _fail('exposures')
        for value in exposure:
            _sha(value)
        if len(set(exposure)) != len(exposure):
            _fail('exposures')
        if case['case_hash'] in indexed:
            _fail('duplicate_case')
        indexed[case['case_hash']] = case
    return indexed


def validate_split(training_cases, heldout_cases):
    """Separate audit API; its heldout metadata is never an input to select()."""
    _scan([training_cases, heldout_cases])
    train, held = _cases(training_cases), _cases(heldout_cases)
    for field in ('case_hash', 'family_hash', 'input_hash'):
        if {c[field] for c in train.values()} & {c[field] for c in held.values()}:
            _fail('split_overlap_' + field)
    # Every declared identity can also name an exposed artifact. A complete
    # heldout case/family may include answers even when its input hash differs;
    # changing the metadata role must not conceal that resource overlap.
    def resources(cases):
        return {v for c in cases.values()
                for v in [c['case_hash'], c['family_hash'], c['input_hash'], *c['exposure_hashes']]}
    if resources(train) & resources(held):
        _fail('split_overlap_exposure')
    return {'training_cases_hash': digest(training_cases), 'heldout_cases_hash': digest(heldout_cases),
            'separation': 'declared_hashes_disjoint'}


def _plan(plan):
    _fields(plan, 'version candidates baseline cases budget objective')
    _version(plan['version'])
    candidates = plan['candidates']
    if type(candidates) is not list or not 1 <= len(candidates) <= MAX_CANDIDATES:
        _fail('candidates')
    indexed = {}
    for candidate in candidates:
        _fields(candidate, 'sha256 policy')
        _pin(candidate['policy'], candidate['sha256'])
        # Keep the frozen wire representation bounded as an output string too.
        wire = _json(candidate['policy'])
        if len(wire) > MAX_TEXT:
            _fail('policy_limit')
        if candidate['sha256'] in indexed:
            _fail('duplicate_candidate')
        indexed[candidate['sha256']] = wire
    _sha(plan['baseline'])
    if plan['baseline'] not in indexed:
        _fail('baseline')
    cases = _cases(plan['cases'])
    if len(cases) * len(indexed) > MAX_ASSIGNMENTS:
        _fail('assignment_limit')
    _fields(plan['budget'], 'max_calls max_cost_units')
    _integer(plan['budget']['max_calls'])
    _integer(plan['budget']['max_cost_units'])
    objective = plan['objective']
    _fields(objective, 'max_score score_weight call_weight cost_weight unknown_cost tie_break min_heldout_gain')
    _integer(objective['max_score'], 1)
    _integer(objective['score_weight'], 1)
    for key in ('call_weight', 'cost_weight', 'min_heldout_gain'):
        _integer(objective[key])
    if type(objective['unknown_cost']) is not str or objective['unknown_cost'] not in ('reject', 'budget'):
        _fail('unknown_cost_policy')
    if objective['tie_break'] != 'policy_sha256_ascending':
        _fail('tie_break')
    return indexed, cases


def _records(records, candidates, cases, budget, objective):
    if type(records) is not list or len(records) > len(candidates) * len(cases):
        _fail('records')
    indexed = {}
    for row in records:
        _fields(row, 'candidate case status score attempts')
        _sha(row['candidate'])
        _sha(row['case'])
        if row['candidate'] not in candidates or row['case'] not in cases:
            _fail('unassigned_record')
        key = (row['candidate'], row['case'])
        if key in indexed:
            _fail('duplicate_record')
        if type(row['status']) is not str or row['status'] not in ('success', 'failed', 'refused'):
            _fail('status')
        _integer(row['score'], 0, objective['max_score'])
        if row['status'] != 'success' and row['score'] != 0:
            _fail('failure_score')
        attempts = row['attempts']
        if type(attempts) is not list or len(attempts) > MAX_ATTEMPTS:
            _fail('attempts')
        calls = known = unknown = 0
        for attempt in attempts:
            _fields(attempt, 'calls cost_units')
            _integer(attempt['calls'])
            calls += attempt['calls']
            if attempt['cost_units'] is None:
                unknown += 1
            else:
                _integer(attempt['cost_units'])
                known += attempt['cost_units']
        if calls > budget['max_calls'] or known > budget['max_cost_units']:
            _fail('budget_exceeded')
        indexed[key] = (row, calls, known, unknown)
    return indexed


def _summaries(candidates, cases, records, budget, objective):
    indexed = _records(records, candidates, cases, budget, objective)
    summaries = {}
    for candidate in sorted(candidates):
        counts = {'success': 0, 'failed': 0, 'refused': 0, 'missing': 0}
        score = calls = known = unknown = charged_calls = charged_cost = 0
        rows = []
        for case in sorted(cases):
            record = indexed.get((candidate, case))
            if record is None:
                status, value, call, cost, uncertain = 'missing', 0, 0, 0, 1
                call_charge = budget['max_calls']
                record_hash = None
            else:
                row, call, cost, uncertain = record
                status, value = row['status'], row['score']
                call_charge = call
                record_hash = digest(row)
            cost_charge = budget['max_cost_units'] if uncertain else cost
            counts[status] += 1
            score += value
            calls += call
            known += cost
            unknown += uncertain
            charged_calls += call_charge
            charged_cost += cost_charge
            rows.append({'case': case, 'status': status, 'record_hash': record_hash,
                         'score': value, 'observed_calls': call, 'charged_calls': call_charge,
                         'known_cost_units': cost, 'unknown_cost_items': uncertain,
                         'charged_cost_units': cost_charge})
        utility = (objective['score_weight'] * score - objective['call_weight'] * charged_calls
                   - objective['cost_weight'] * charged_cost)
        summaries[candidate] = {'denominator': len(cases), 'statuses': counts, 'score_sum': score,
                               'observed_calls': calls, 'unknown_call_assignments': counts['missing'],
                               'charged_calls': charged_calls, 'known_cost_units': known,
                               'unknown_cost_items': unknown, 'charged_cost_units': charged_cost,
                               'eligible': not unknown or objective['unknown_cost'] == 'budget',
                               'utility_sum': utility, 'assignments': rows}
    return summaries


def select(training_plan, training_records, *, expected_plan_hash, expected_records_hash):
    """Select from training only; heldout metadata/records have no parameter path.

    The selected policy is immutable canonical JSON text, identified by SHA256.
    Raises PolicyError rather than silently falling back to a rejected candidate.
    """
    _scan([training_plan, training_records])
    _pin(training_plan, expected_plan_hash)
    _pin(training_records, expected_records_hash)
    candidates, cases = _plan(training_plan)
    summaries = _summaries(candidates, cases, training_records,
                           training_plan['budget'], training_plan['objective'])
    eligible = [key for key, value in summaries.items() if value['eligible']]
    if not eligible:
        _fail('no_eligible_candidate')
    chosen = min(eligible, key=lambda key: (-summaries[key]['utility_sum'], key))
    receipt = {'training_plan_hash': expected_plan_hash, 'training_records_hash': expected_records_hash,
               'baseline': training_plan['baseline'], 'assignment_count': len(cases) * len(candidates),
               'summaries': summaries, 'objective': json.loads(_json(training_plan['objective'])),
               'measurement_status': 'host_declared_not_verified', 'confidence': 'not_established',
               'causality': 'not_established', 'deployment': 'future_runs_only', 'history': 'unchanged'}
    result = {'version': VERSION, 'method': METHOD,
              'selected': {'sha256': chosen, 'policy_json': candidates[chosen]}, 'receipt': receipt}
    _scan(result)
    return result


def evaluate_heldout(training_plan, training_records, selection, heldout_plan, heldout_records, *, pins):
    """Replay a frozen training choice, audit separation, then compare on heldout.

    Heldout never chooses/reorders candidates or updates the selected policy.
    Pins must come from trusted predeclaration/freeze storage, not the candidate.
    """
    _scan(pins)
    _fields(pins, 'training_plan training_records selection heldout_plan heldout_records')
    # Do not pass even heldout ordering/metadata into the selector or its pins.
    replay = select(training_plan, training_records, expected_plan_hash=pins['training_plan'],
                    expected_records_hash=pins['training_records'])
    _pin(selection, pins['selection'])
    if _json(replay) != _json(selection):
        _fail('selection_mismatch')
    _scan([heldout_plan, heldout_records])
    _pin(heldout_plan, pins['heldout_plan'])
    _pin(heldout_records, pins['heldout_records'])
    _fields(heldout_plan, 'version training_plan_hash cases')
    _version(heldout_plan['version'])
    if heldout_plan['training_plan_hash'] != pins['training_plan']:
        _fail('training_plan_mismatch')
    separation = validate_split(training_plan['cases'], heldout_plan['cases'])
    chosen = replay['selected']['sha256']
    baseline = training_plan['baseline']
    candidates = {chosen, baseline}
    cases = _cases(heldout_plan['cases'])
    summaries = _summaries(candidates, cases, heldout_records,
                           training_plan['budget'], training_plan['objective'])
    a, b = summaries[chosen], summaries[baseline]
    delta = a['utility_sum'] - b['utility_sum']
    # An observed improvement requires complete comparable accounting. Conservative
    # training penalties cannot turn missing/unknown heldout measurements into evidence.
    complete = all(s['statuses']['missing'] == 0 and s['unknown_cost_items'] == 0
                   for s in summaries.values())
    threshold = training_plan['objective']['min_heldout_gain'] * len(cases)
    improved = complete and chosen != baseline and delta > 0 and delta >= threshold
    result = {'version': VERSION, 'method': METHOD, 'selected_hash': chosen, 'baseline_hash': baseline,
              'pins': dict(pins), 'separation': separation, 'summaries': summaries,
              'improvement': improved, 'comparison': 'observed_improvement' if improved else 'not_established',
              'complete_accounting': complete,
              'utility_gain': {'numerator': delta, 'denominator': len(cases)},
              'measurement_status': 'host_declared_not_verified', 'confidence': 'not_established',
              'causality': 'not_established', 'deployment': 'future_runs_only', 'history': 'unchanged'}
    _scan(result)
    return result


def load_json(path):
    """CLI input: bounded regular UTF-8 JSON file, never a device/FIFO or provider."""
    import os
    import stat

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('duplicate_key')
            result[key] = value
        return result

    def integer(text):
        if len(text) > 32:
            _fail('integer_limit')
        return int(text)

    def noninteger(_):
        _fail('json_number')

    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                _fail('input_file')
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            _fail('byte_limit')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_int=integer, parse_float=noninteger, parse_constant=noninteger)
        _scan(value)
        return value
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise PolicyError('input_file') from None
    except RecursionError:
        raise PolicyError('structure_limit') from None


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog='python3 -m symblic.policy.learning',
                                     description='Select one predeclared policy from training records; compare it on held-out cases.')
    commands = parser.add_subparsers(dest='command', required=True)
    hashing = commands.add_parser('hash', help='canonical SHA256 for a JSON file')
    hashing.add_argument('file')
    selection = commands.add_parser('select', help='training files only')
    selection.add_argument('--plan', required=True)
    selection.add_argument('--records', required=True)
    selection.add_argument('--pins', required=True)
    evaluation = commands.add_parser('evaluate', help='frozen heldout comparison; no reselection')
    for name in ('training-plan', 'training-records', 'selection', 'heldout-plan', 'heldout-records', 'pins'):
        evaluation.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'hash':
            result = {'sha256': digest(load_json(args.file))}
        elif args.command == 'select':
            pins = load_json(args.pins)
            _fields(pins, 'training_plan training_records')
            result = select(load_json(args.plan), load_json(args.records),
                            expected_plan_hash=pins['training_plan'], expected_records_hash=pins['training_records'])
        else:
            result = evaluate_heldout(load_json(args.training_plan), load_json(args.training_records),
                                      load_json(args.selection), load_json(args.heldout_plan),
                                      load_json(args.heldout_records), pins=load_json(args.pins))
        print(_json(result))
        return 0
    except PolicyError as exc:
        print(_json({'ok': False, 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

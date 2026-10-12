"""Inquiry: choose the next check that would add measured evidence for a claim.

What it is for
    Repeating the same check, or asking a second model the same question, does not by itself add evidence.
    plan(assessment) takes one claim, a declared scope (the finite fault fixtures a good check should catch
    and the alternative explanations it should tell apart), candidate methods with their dependencies, cost
    and admission, and the receipts of checks already performed. It returns, for every method, whether it is
    eligible and why not, which faults and alternative pairs it would newly cover, and one recommended next
    method: the stable-ID first member of the Pareto frontier over (new coverage by set inclusion, cost).
    Methods that share an acquisition, interpretation or assumption are reported as shared dependencies;
    independence between methods is never assumed ('independence': 'not_established').

    example() builds a complete synthetic assessment (three integer predicates over three fault fixtures);
    plan(example()) shows the whole output. loads(raw) reads JSON while refusing duplicate keys and floats.

What it is not
    Pure and deterministic: no store, model, solver, file write or process. It never executes the recommended
    method and never changes a claim; every result says 'authorizes_execution': False. Hashes bind the
    caller's records to each other; they do not authenticate observations. Coverage means coverage of the
    declared finite fixtures only.

Command line: python3 -m symblic.inquiry.selection example | plan FILE  (JSON output; tools/symblic exposes
the same as `symblic inquiry`). Depends on: the Python standard library only. Used by: the host's HTTP route
in integration/host/symblic_inquiry_api.py. Status: prototype with unit tests on synthetic fixtures
(tests/inquiry); no evaluation on real research questions is included. Design notes: docs/reference/INQUIRY.md.
"""
import hashlib
import json
import re

VERSION = 1
ASSESSMENT = 'symblic.inquiry.assessment.v1'
PLAN = 'symblic.inquiry.plan.v1'
RECOMMENDATION = 'symblic.inquiry.recommendation.v1'
MAX_BYTES = 1_048_576
MAX_NODES = 65_536
MAX_DEPTH = 16
MAX_TEXT = 4096
MAX_INT = 2**53 - 1
MAX_METHODS = 64
MAX_RECEIPTS = 256
MAX_FAULTS = 128
MAX_ALTERNATIVES = 16
MAX_DEPENDENCIES = 256
MAX_REFS = 32
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_SUPPORT = {'unassessed', 'conditional', 'supported', 'contested', 'unavailable', 'withdrawn'}
_INQUIRY = {'planned', 'running', 'completed', 'stopped', 'awaiting_evidence'}
_OUTCOMES = {'completed', 'failed', 'timed_out', 'unavailable', 'unperformed'}
_FAULT_OUTCOMES = {'caught', 'missed', 'unassessed', 'unavailable'}


class InquiryError(ValueError):
    """Stable code and field location, without echoing private input values."""

    def __init__(self, code, path='assessment'):
        self.code, self.path = code, path
        super().__init__(code + ': ' + path)


def _fail(code, path='assessment'):
    raise InquiryError(code, path)


def _wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _bounded(value):
    # Only one iterator frame per nesting level; aliases still spend work for
    # every occurrence. Never enqueue a caller's entire wide container.
    active = set()
    nodes = size = 0

    def walk(item, depth):
        nonlocal nodes, size
        nodes += 1
        size += 2
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            _fail('structure_limit')
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active:
                _fail('cycle')
            if len(item) > MAX_NODES:
                _fail('structure_limit')
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        _fail('json_type')
                    walk(key, depth + 1)
                    walk(child, depth + 1)
            else:
                for child in item:
                    walk(child, depth + 1)
            active.remove(id(item))
        elif kind is str:
            if len(item) > MAX_TEXT:
                _fail('text_limit')
            try:
                size += len(_wire(item))
            except UnicodeError:
                _fail('unicode')
        elif kind is int:
            if abs(item) > MAX_INT:
                _fail('integer_limit')
            size += 18
        elif kind is bool or item is None:
            size += 5
        else:
            _fail('json_type')
        if size > MAX_BYTES:
            _fail('byte_limit')

    walk(value, 0)
    raw = _wire(value)
    if len(raw) > MAX_BYTES:
        _fail('byte_limit')
    return raw


def digest(value):
    """Digest bounded exact JSON; no floats, custom objects or implicit casts."""
    return hashlib.sha256(_bounded(value)).hexdigest()


def loads(raw):
    """Decode bounded JSON without duplicate keys or approximate numbers."""
    if type(raw) not in (str, bytes):
        _fail('json_type')
    try:
        if len(raw) > MAX_BYTES or (type(raw) is str and len(raw.encode('utf-8')) > MAX_BYTES):
            _fail('byte_limit')
    except UnicodeError:
        _fail('unicode')

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                _fail('duplicate_key')
            result[key] = value
        return result

    def approximate(_):
        _fail('json_type')

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=approximate,
                           parse_constant=approximate)
    except InquiryError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        _fail('invalid_json')
    _bounded(value)
    return value


def _fields(value, names, path):
    if type(value) is not dict or set(value) != set(names.split()):
        _fail('schema', path)


def _id(value, path):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail('id', path)
    return value


def _hash(value, path):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail('hash', path)


def _integer(value, path, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_INT:
        _fail('integer', path)


def _text(value, path):
    if type(value) is not str or not value.strip():
        _fail('text', path)


def _enum(value, choices, path):
    if type(value) is not str or value not in choices:
        _fail('enum', path)


def _rows(value, maximum, path):
    if type(value) is not list or len(value) > maximum:
        _fail('list_limit', path)
    return value


def _reference(value, path):
    _fields(value, 'id revision sha256', path)
    _id(value['id'], path + '.id')
    _integer(value['revision'], path + '.revision', 1)
    _hash(value['sha256'], path + '.sha256')


def _references(rows, maximum, path):
    indexed = {}
    for row in _rows(rows, maximum, path):
        _reference(row, path)
        if row['id'] in indexed:
            _fail('duplicate_id', path)
        indexed[row['id']] = row
    return indexed


def _scope(scope):
    _fields(scope, 'id revision claim domain units outcome_schema_sha256 faults alternatives', 'scope')
    _id(scope['id'], 'scope.id')
    _integer(scope['revision'], 'scope.revision', 1)
    _reference(scope['claim'], 'scope.claim')
    for name in ('domain', 'units'):
        _text(scope[name], 'scope.' + name)
    _hash(scope['outcome_schema_sha256'], 'scope.outcome_schema_sha256')
    indices = []
    for name, maximum, hash_key in (('faults', MAX_FAULTS, 'fixture_sha256'),
                                    ('alternatives', MAX_ALTERNATIVES, 'definition_sha256')):
        indexed = {}
        for row in _rows(scope[name], maximum, 'scope.' + name):
            _fields(row, 'id ' + hash_key, 'scope.' + name)
            _id(row['id'], 'scope.' + name)
            _hash(row[hash_key], 'scope.' + name)
            if row['id'] in indexed:
                _fail('duplicate_id', 'scope.' + name)
            indexed[row['id']] = row[hash_key]
        indices.append(indexed)
    return indices


def scope_digest(scope):
    """Pin the exact caller scope, including claim revision and fixture identities."""
    _bounded(scope)
    _scope(scope)
    return digest(scope)


def _method(method):
    _fields(method, 'id revision implementation_sha256 acquisition interpretation assumptions '
                    'authorized available cost', 'method')
    _id(method['id'], 'method.id')
    _integer(method['revision'], 'method.revision', 1)
    _hash(method['implementation_sha256'], 'method.implementation_sha256')
    for name in ('acquisition', 'interpretation', 'assumptions'):
        _references(method[name], MAX_REFS, 'method.' + name)
    # The same reference may play several roles, but not disagree within one method.
    all_refs = {}
    for name in ('acquisition', 'interpretation', 'assumptions'):
        for ref in method[name]:
            if ref['id'] in all_refs and all_refs[ref['id']] != ref:
                _fail('conflicting_reference', 'method')
            all_refs[ref['id']] = ref
    if type(method['authorized']) is not bool:
        _fail('boolean', 'method.authorized')
    if method['available'] is not None and type(method['available']) is not bool:
        _fail('boolean', 'method.available')
    cost = method['cost']
    if cost is not None:
        _fields(cost, 'amount receipt_sha256', 'method.cost')
        _integer(cost['amount'], 'method.cost.amount')
        _hash(cost['receipt_sha256'], 'method.cost.receipt_sha256')


def method_digest(method):
    """Pin method semantics/dependencies; current admission and cost are separate."""
    _bounded(method)
    _method(method)
    return digest({k: method[k] for k in ('id', 'revision', 'implementation_sha256',
                                        'acquisition', 'interpretation', 'assumptions')})


def _receipt(row, methods, scope_hash, faults, alternatives):
    _fields(row, 'id scope_sha256 method_id method_sha256 status faults predictions', 'receipt')
    _id(row['id'], 'receipt.id')
    _hash(row['scope_sha256'], 'receipt.scope_sha256')
    if row['scope_sha256'] != scope_hash:
        _fail('stale_scope_receipt', 'receipt.scope_sha256')
    _id(row['method_id'], 'receipt.method_id')
    if row['method_id'] not in methods:
        _fail('unknown_method', 'receipt.method_id')
    _hash(row['method_sha256'], 'receipt.method_sha256')
    if row['method_sha256'] != method_digest(methods[row['method_id']]):
        _fail('stale_method_receipt', 'receipt.method_sha256')
    _enum(row['status'], _OUTCOMES, 'receipt.status')
    seen = set()
    for fault in _rows(row['faults'], MAX_FAULTS, 'receipt.faults'):
        _fields(fault, 'id fixture_sha256 outcome witness_sha256', 'receipt.fault')
        ident = _id(fault['id'], 'receipt.fault.id')
        if ident in seen:
            _fail('duplicate_id', 'receipt.faults')
        seen.add(ident)
        if ident not in faults or fault['fixture_sha256'] != faults[ident]:
            _fail('fault_contract_mismatch', 'receipt.fault')
        _enum(fault['outcome'], _FAULT_OUTCOMES, 'receipt.fault.outcome')
        if fault['outcome'] in ('caught', 'missed'):
            _hash(fault['witness_sha256'], 'receipt.fault.witness_sha256')
        elif fault['witness_sha256'] is not None:
            _fail('unexpected_witness', 'receipt.fault')
    seen = set()
    for prediction in _rows(row['predictions'], MAX_ALTERNATIVES, 'receipt.predictions'):
        _fields(prediction, 'id definition_sha256 outcome_sha256', 'receipt.prediction')
        ident = _id(prediction['id'], 'receipt.prediction.id')
        if ident in seen:
            _fail('duplicate_id', 'receipt.predictions')
        seen.add(ident)
        if ident not in alternatives or prediction['definition_sha256'] != alternatives[ident]:
            _fail('alternative_contract_mismatch', 'receipt.prediction')
        if prediction['outcome_sha256'] is not None:
            _hash(prediction['outcome_sha256'], 'receipt.prediction.outcome_sha256')


def _evidence(receipts, faults, alternatives):
    fault_states = {ident: set() for ident in faults}
    predictions = {ident: set() for ident in alternatives}
    for receipt in receipts:
        if receipt['status'] != 'completed':
            continue
        for fault in receipt['faults']:
            fault_states[fault['id']].add(fault['outcome'])
        for prediction in receipt['predictions']:
            if prediction['outcome_sha256'] is not None:
                predictions[prediction['id']].add(prediction['outcome_sha256'])
    caught = {k for k, v in fault_states.items() if 'caught' in v and 'missed' not in v}
    conflicts = {k for k, v in fault_states.items() if {'caught', 'missed'} <= v}
    unknown = {k for k, v in fault_states.items() if not (v & {'caught', 'missed'})}
    known = {k: next(iter(v)) for k, v in predictions.items() if len(v) == 1}
    pairs = {(left, right) for left in sorted(known) for right in sorted(known)
             if left < right and known[left] != known[right]}
    return {'caught': caught, 'conflicts': conflicts, 'unknown': unknown,
            'pairs': pairs, 'unknown_predictions': set(alternatives) - set(known),
            'prediction_conflicts': {k for k, v in predictions.items() if len(v) > 1},
            'fault_states': {k: sorted(v) for k, v in sorted(fault_states.items())}}


def plan(assessment):
    """Return a deterministic recommendation; never execute or change input state."""
    raw = _bounded(assessment)
    # Detach output and prevent retaining mutable caller containers.
    data = json.loads(raw)
    _fields(data, 'schema claim scope scope_sha256 dependencies methods receipts '
                  'used_receipt_ids budget support inquiry', 'assessment')
    if data['schema'] != ASSESSMENT:
        _fail('version')
    _reference(data['claim'], 'claim')
    faults, alternatives = _scope(data['scope'])
    if data['claim'] != data['scope']['claim']:
        _fail('stale_claim', 'scope.claim')
    scope_hash = scope_digest(data['scope'])
    _hash(data['scope_sha256'], 'scope_sha256')
    if data['scope_sha256'] != scope_hash:
        _fail('scope_pin_mismatch', 'scope_sha256')
    dependencies = _references(data['dependencies'], MAX_DEPENDENCIES, 'dependencies')
    methods = {}
    for method in _rows(data['methods'], MAX_METHODS, 'methods'):
        _method(method)
        if method['id'] in methods:
            _fail('duplicate_id', 'methods')
        methods[method['id']] = method
    receipts = {}
    by_method = {ident: [] for ident in methods}
    for row in _rows(data['receipts'], MAX_RECEIPTS, 'receipts'):
        _receipt(row, methods, scope_hash, faults, alternatives)
        if row['id'] in receipts:
            _fail('duplicate_id', 'receipts')
        receipts[row['id']] = row
        by_method[row['method_id']].append(row)
    used = set()
    for ident in _rows(data['used_receipt_ids'], MAX_RECEIPTS, 'used_receipt_ids'):
        _id(ident, 'used_receipt_ids')
        if ident in used:
            _fail('duplicate_id', 'used_receipt_ids')
        if ident not in receipts:
            _fail('unknown_receipt', 'used_receipt_ids')
        used.add(ident)
    _fields(data['budget'], 'unit remaining', 'budget')
    _id(data['budget']['unit'], 'budget.unit')
    _integer(data['budget']['remaining'], 'budget.remaining')
    _fields(data['support'], 'status reason', 'support')
    _enum(data['support']['status'], _SUPPORT, 'support.status')
    _text(data['support']['reason'], 'support.reason')
    _fields(data['inquiry'], 'status reason history', 'inquiry')
    _enum(data['inquiry']['status'], _INQUIRY, 'inquiry.status')
    _text(data['inquiry']['reason'], 'inquiry.reason')
    for event in _rows(data['inquiry']['history'], 64, 'inquiry.history'):
        _fields(event, 'status reason scope_sha256', 'inquiry.history')
        _enum(event['status'], _INQUIRY, 'inquiry.history.status')
        _text(event['reason'], 'inquiry.history.reason')
        _hash(event['scope_sha256'], 'inquiry.history.scope_sha256')

    stale = {}
    for ident, method in methods.items():
        stale[ident] = sorted({ref['id'] for role in ('acquisition', 'interpretation', 'assumptions')
                               for ref in method[role] if dependencies.get(ref['id']) != ref})
    invalid_used = sorted(ident for ident in used if stale[receipts[ident]['method_id']])
    # Coverage is a union across methods. A second method missing a fault does
    # not erase the first method's catch; predictions from different methods
    # cannot be stitched together into a fabricated within-method distinction.
    baseline = {'caught': set(), 'pairs': set()}
    for method_id in methods:
        observed = _evidence([receipts[ident] for ident in sorted(used)
                              if ident not in invalid_used and receipts[ident]['method_id'] == method_id],
                             faults, alternatives)
        baseline['caught'].update(observed['caught'])
        baseline['pairs'].update(observed['pairs'])
    rows = []
    sets = {}
    for ident, method in sorted(methods.items()):
        observed = _evidence(by_method[ident], faults, alternatives)
        reasons = []
        if stale[ident]:
            reasons.append('stale_dependencies')
        if not method['authorized']:
            reasons.append('not_authorized')
        if method['available'] is not True:
            reasons.append('availability_unknown' if method['available'] is None else 'unavailable')
        cost = method['cost']
        if cost is None:
            reasons.append('cost_unknown')
        elif cost['amount'] > data['budget']['remaining']:
            reasons.append('over_budget')
        new_faults = observed['caught'] - baseline['caught']
        new_pairs = observed['pairs'] - baseline['pairs']
        if not new_faults and not new_pairs:
            reasons.append('no_measured_gain')
        eligible = not reasons
        rows.append({'id': ident, 'method_sha256': method_digest(method), 'eligible': eligible,
                     'reasons': reasons, 'cost': cost, 'stale_dependency_ids': stale[ident],
                     'receipt_ids': sorted(row['id'] for row in by_method[ident]),
                     'new_fault_ids': sorted(new_faults),
                     'new_alternative_pairs': [list(pair) for pair in sorted(new_pairs)],
                     'unknown_fault_ids': sorted(observed['unknown']),
                     'conflicting_fault_ids': sorted(observed['conflicts']),
                     'fault_outcomes': observed['fault_states'],
                     'unknown_alternative_ids': sorted(observed['unknown_predictions']),
                     'conflicting_alternative_ids': sorted(observed['prediction_conflicts']),
                     'acquisition': method['acquisition'], 'interpretation': method['interpretation'],
                     'assumptions': method['assumptions']})
        if eligible:
            sets[ident] = (new_faults, new_pairs, cost['amount'])

    def dominates(left, right):
        a, b = sets[left], sets[right]
        return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a != b

    frontier = sorted(ident for ident in sets if not any(
        other != ident and dominates(other, ident) for other in sets))
    # No implicit scalar trade-off: retain all incomparable candidates, then use
    # the documented stable ID policy to choose one bounded next step.
    chosen = frontier[0] if frontier else None
    if data['support']['status'] == 'withdrawn':
        status, chosen = 'claim_withdrawn', None
    elif data['inquiry']['status'] == 'running':
        status, chosen = 'await_current_inquiry', None
    elif chosen is not None:
        status = ('reopen_recommended' if data['inquiry']['status'] in ('stopped', 'completed')
                  else 'recommendation')
    else:
        status = 'no_admissible_measured_gain'
    assessment_hash = hashlib.sha256(raw).hexdigest()
    recommendation = None
    if chosen is not None:
        selected = next(row for row in rows if row['id'] == chosen)
        item = {'schema': RECOMMENDATION, 'scope_sha256': scope_hash,
                'assessment_sha256': assessment_hash, 'claim': data['claim'],
                'method_id': chosen, 'method_sha256': selected['method_sha256'],
                'receipt_ids': selected['receipt_ids'], 'cost': selected['cost'],
                'budget_unit': data['budget']['unit'], 'new_fault_ids': selected['new_fault_ids'],
                'new_alternative_pairs': selected['new_alternative_pairs'],
                'reason': 'stable_id_first_on_set_inclusion_cost_pareto_frontier',
                'authorizes_execution': False}
        recommendation = dict(item, id=digest(item))
    shared = []
    for role in ('acquisition', 'interpretation', 'assumptions'):
        refs = {}
        for ident, method in sorted(methods.items()):
            for ref in method[role]:
                key = (ref['id'], ref['revision'], ref['sha256'])
                refs.setdefault(key, []).append(ident)
        for key, names in sorted(refs.items()):
            if len(names) > 1:
                shared.append({'role': role, 'reference': dict(zip(('id', 'revision', 'sha256'), key)),
                               'method_ids': names})
    result = {'schema': PLAN, 'version': VERSION, 'assessment_sha256': assessment_hash,
              'scope_sha256': scope_hash, 'claim': data['claim'], 'status': status,
              'support': data['support'], 'inquiry': data['inquiry'],
              'support_binding': {'status': 'stale' if invalid_used else 'current_declared_scope',
                                  'stale_used_receipt_ids': invalid_used},
              'baseline': {'used_receipt_ids': sorted(used), 'covered_fault_ids': sorted(baseline['caught']),
                           'uncovered_fault_ids': sorted(set(faults) - baseline['caught']),
                           'distinguished_alternative_pairs': [list(p) for p in sorted(baseline['pairs'])]},
              'planned_receipts': [{'id': r['id'], 'method_id': r['method_id'], 'status': r['status']}
                                   for r in sorted(receipts.values(), key=lambda r: r['id'])],
              'methods': rows, 'pareto_frontier': frontier, 'recommendation': recommendation,
              'shared_dependencies': shared, 'independence': 'not_established',
              'coverage_scope': 'declared_finite_fixtures_only', 'authorizes_execution': False}
    # Output size is bounded separately; callers never receive partial evidence.
    _bounded(result)
    return result


def example():
    """Run three tiny pure predicates on finite synthetic integer fixtures.

    Operation counts use the declared primitive-count convention. They are not
    wall-clock measurements, external observations or production admissions.
    """
    def ref(ident):
        return {'id': ident, 'revision': 1, 'sha256': digest(['synthetic-v1', ident])}

    claim = ref('synthetic.reading')
    fixtures = {'drift': [3, 4], 'reversal': [-2, -3], 'omission': [2]}
    alternatives = {'expected': [2, 3], 'shifted': [3, 4], 'short': [2]}
    scope = {'id': 'synthetic.integer-readings', 'revision': 1, 'claim': claim,
             'domain': 'Synthetic integer fixtures; expected readings are [2, 3].',
             'units': 'dimensionless', 'outcome_schema_sha256': digest('Boolean predicate result'),
             'faults': [{'id': key, 'fixture_sha256': digest(value)} for key, value in fixtures.items()],
             'alternatives': [{'id': key, 'definition_sha256': digest(value)}
                              for key, value in alternatives.items()]}
    source, calibration = ref('synthetic.fixture-source'), ref('synthetic.expected-readings')
    def nonnegative(values):
        observations = [value >= 0 for value in values]
        return all(observations)

    specs = [
        ('a-nonnegative', 'Every reading is nonnegative; one comparison per reading.',
         nonnegative, lambda values: len(values)),
        ('b-total', 'The sum equals 5; one addition per reading and one comparison.',
         lambda values: sum(values) == 5, lambda values: len(values) + 1),
        ('c-length', 'There are two readings; one length operation and one comparison.',
         lambda values: len(values) == 2, lambda values: 2),
    ]
    data = {'schema': ASSESSMENT, 'claim': claim, 'scope': scope,
            'scope_sha256': scope_digest(scope), 'dependencies': [source, calibration],
            'methods': [], 'receipts': [], 'used_receipt_ids': ['fixture-a-nonnegative'],
            'budget': {'unit': 'synthetic_primitive_operations', 'remaining': 10},
            'support': {'status': 'conditional',
                        'reason': 'The nonnegative check leaves other synthetic faults uncovered.'},
            'inquiry': {'status': 'stopped', 'reason': 'Only the first check was previously selected.',
                        'history': []}}
    for ident, description, check, count in specs:
        reader = ref(ident + '.interpretation')
        data['dependencies'].append(reader)
        operations = sum(count(values) for values in fixtures.values())
        method = {'id': ident, 'revision': 1, 'implementation_sha256': digest(description),
                  'acquisition': [source], 'interpretation': [reader], 'assumptions': [calibration],
                  'authorized': True, 'available': True,
                  'cost': {'amount': operations, 'receipt_sha256': digest({
                      'convention': description, 'fixture_operations': operations})}}
        data['methods'].append(method)
        data['receipts'].append({'id': 'fixture-' + ident, 'scope_sha256': data['scope_sha256'],
            'method_id': ident, 'method_sha256': method_digest(method), 'status': 'completed',
            'faults': [{'id': key, 'fixture_sha256': digest(values),
                        'outcome': 'missed' if check(values) else 'caught',
                        'witness_sha256': digest({'values': values, 'accepted': check(values)})}
                       for key, values in fixtures.items()],
            'predictions': [{'id': key, 'definition_sha256': digest(values),
                             'outcome_sha256': digest(check(values))}
                            for key, values in alternatives.items()]})
    return data


def main(argv=None):
    """Local JSON interface. Planning reads one bounded regular file."""
    import argparse
    import os
    import stat

    parser = argparse.ArgumentParser(prog='symblic inquiry', description=(
        'Select the next evidence method for one claim from a bounded assessment JSON file.'))
    commands = parser.add_subparsers(dest='command', required=True)
    sample = commands.add_parser('example', help='Print a synthetic assessment.')
    sample.add_argument('--agent-json', action='store_true', help='Output is always exact JSON.')
    selected = commands.add_parser('plan', help='Select the next check from an assessment JSON file.')
    selected.add_argument('file', help='Path to a bounded regular assessment JSON file.')
    selected.add_argument('--agent-json', action='store_true', help='Output is always exact JSON.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'example':
            result = example()
        else:
            if args.file == '-':
                print(json.dumps({'ok': False, 'error': 'Save the assessment JSON to a regular file and provide its path; stdin is not supported.',
                                  'detail': {'code': 'file_path_required', 'path': 'file'}}))
                return 1
            fd = os.open(args.file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    _fail('regular_file_required', 'file')
                if info.st_size > MAX_BYTES:
                    _fail('byte_limit', 'file')
                raw = stream.read(MAX_BYTES + 1)
            result = plan(loads(raw))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (InquiryError, OSError) as error:
        detail = {'code': error.code, 'path': error.path} if isinstance(error, InquiryError) else {
            'code': 'file_unavailable', 'path': 'file'}
        print(json.dumps({'ok': False, 'error': 'Inquiry request refused.', 'detail': detail}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

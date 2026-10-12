"""MICA requests and contracts: the bounded JSON shapes every other MICA module agrees on.

What it is for
    Normalizes and validates a construction request (objective, requirements, exports, tests, allowed outputs,
    budget) and a proposed plan (a DAG of unit contracts with requirement coverage, dependencies, scopes and
    budgets), computes content hashes, and checks finite refinements. Everything else in MICA starts from these
    records.

Depends on: symblic.kernel.language (lazily), symblic.js.check and symblic.spec.contracts for example checks.
Used by every other MICA module. Pure: no files, providers or processes.

Details
    Pure bounded MICA request/contract admission over existing Symblic contracts.

    No files, provider, solver, worker or host effect. Plans are admitted declarations,
    not construction success. A finite refinement proves only its supplied exact
    predicate implication on the declared finite domains, never prose or emitted JS.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import hashlib
import itertools
import json
import math
import re
import time

VERSION = 1
MAX_BYTES = 2_000_000
MAX_ITEMS = 50_000
_NAME = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*\Z')
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
DEFAULT_BUDGET = {'max_calls': 64, 'max_candidates': 4, 'max_depth': 4,
                  'max_units': 64, 'max_workers': 3, 'retries': 2,
                  'context_chars': 32768, 'wall_seconds': 1800}
BUDGET_LIMITS = {'max_calls': (0, 10000), 'max_candidates': (1, 32),
                 'max_depth': (1, 16), 'max_units': (1, 128),
                 'max_workers': (1, 8), 'retries': (0, 8),
                 'context_chars': (256, 262144), 'wall_seconds': (1, 86400)}
CONTRACT_FIELDS = {'contract_id', 'parent_contract_id', 'root_requirement_ids', 'objective',
    'preconditions', 'postconditions', 'invariants', 'input_artifacts', 'output_artifacts',
    'dependency_contract_ids', 'permitted_read_scope', 'permitted_write_scope',
    'permitted_effects', 'verification_obligations', 'resource_budget', 'model_eligibility',
    'failure_policy', 'version', 'content_hash', 'unit', 'construction'}


class ContractError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise ContractError(code, message)


def _bounded(value):
    seen = set()
    left = MAX_ITEMS
    def visit(v, depth):
        nonlocal left
        left -= 1
        if left < 0 or depth > 32:
            _fail('structure_limit', 'JSON exceeds the bounded structure.')
        typ = type(v)
        if typ in (dict, list):
            if id(v) in seen:
                _fail('cycle', 'Cyclic JSON is refused.')
            seen.add(id(v))
            if typ is dict:
                for k, child in v.items():
                    if type(k) is not str:
                        _fail('json_type', 'JSON keys must be strings.')
                    visit(k, depth + 1); visit(child, depth + 1)
            else:
                for child in v:
                    visit(child, depth + 1)
            seen.remove(id(v))
        elif typ is str:
            if len(v) > 262144:
                _fail('text_limit', 'JSON string exceeds its limit.')
        elif typ is int:
            if v.bit_length() > 4096:
                _fail('integer_limit', 'Integer exceeds its limit.')
        elif v is None or typ is bool:
            pass
        else:
            _fail('json_type', 'Only exact JSON values, without floats or custom types, are admitted.')
    visit(value, 0)
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (UnicodeError, ValueError, OverflowError):
        _fail('json_encoding', 'JSON must have valid UTF-8 encoding.')
    if len(raw) > MAX_BYTES:
        _fail('byte_limit', 'JSON exceeds the byte limit.')
    return raw


def digest(value):
    """SHA-256 of the canonical bounded JSON of `value`."""
    return hashlib.sha256(_bounded(value)).hexdigest()


def _keys(row, required, optional=()):
    if type(row) is not dict or not set(required) <= set(row) or set(row) - set(required) - set(optional):
        _fail('fields', 'Missing or unknown contract fields.')


def _text(value, field, maximum=12000):
    if type(value) is not str or not value.strip() or len(value) > maximum or '\x00' in value:
        _fail(field, field + ' must be bounded nonempty text.')
    return value


def _identifier(value, field='id'):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail(field, 'Expected a bounded identifier.')
    return value


def _strings(value, field, *, nonempty=False, maximum=128):
    if type(value) is not list or len(value) > maximum or (nonempty and not value):
        _fail(field, field + ' must be a bounded string list.')
    for item in value:
        _text(item, field)
    if len(value) != len(set(value)):
        _fail(field, field + ' contains duplicate entries.')
    return list(value)


def _path(value):
    _text(value, 'path', 240)
    parts = value.split('/')
    if (value.startswith('/') or '\\' in value or ':' in value
            or any(p in ('', '.', '..') or p.startswith('.') for p in parts)
            or any(ord(c) < 32 for c in value)):
        _fail('path', 'Only normalized relative output paths are admitted.')
    return value


def _budget(value, *, defaults=None):
    if type(value) is not dict or set(value) - set(BUDGET_LIMITS):
        _fail('budget', 'Unknown budget fields.')
    result = dict(DEFAULT_BUDGET if defaults is None else defaults)
    for name, item in value.items():
        low, high = BUDGET_LIMITS[name]
        if type(item) is not int or not low <= item <= high:
            _fail('budget', 'Budget values must be bounded exact integers.')
        result[name] = item
    return result


def _expected(value):
    _text(value, 'expected', 12000)
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                _fail('expected', 'Duplicate expected JSON keys are refused.')
            result[key] = item
        return result
    def finite(raw):
        x = float(raw)
        if not math.isfinite(x):
            _fail('expected', 'Expected JSON numbers must be finite.')
        return x
    try:
        json.loads(value, object_pairs_hook=pairs, parse_float=finite,
                   parse_constant=lambda _: _fail('expected', 'Expected JSON must be finite.'))
    except (ValueError, RecursionError):
        _fail('expected', 'Expected must be JSON text.')
    return value


def normalize_request(request):
    """Detach and normalize explicit-safe defaults; never invent a check or goal."""
    _bounded(request)
    _keys(request, ('objective', 'requirements', 'exports', 'tests', 'allowed_outputs'),
          ('version', 'budget', 'assumptions', 'language', 'artifact_format'))
    if type(request.get('version', VERSION)) is not int or request.get('version', VERSION) != VERSION:
        _fail('version', 'Unsupported request version.')
    if request.get('language', 'javascript') != 'javascript':
        _fail('language', 'This construction lane supports JavaScript only.')
    requirements = request['requirements']
    if type(requirements) is not list or not 1 <= len(requirements) <= 128:
        _fail('requirements', 'Supply 1..128 explicit requirements.')
    ids = set()
    for row in requirements:
        _keys(row, ('id', 'text', 'acceptance'))
        ident = _identifier(row['id'])
        if ident in ids:
            _fail('requirements', 'Duplicate requirement ID.')
        ids.add(ident); _text(row['text'], 'requirement')
        if row['acceptance'] not in ('TESTED', 'PROVEN'):
            _fail('acceptance', 'Requirement acceptance must be TESTED or PROVEN.')
    exports = request['exports']
    if type(exports) is not list or not 1 <= len(exports) <= 128:
        _fail('exports', 'Supply 1..128 declared exports.')
    names = set()
    for row in exports:
        _keys(row, ('name', 'signature'))
        if type(row['name']) is not str or not _NAME.fullmatch(row['name']) or row['name'] in names:
            _fail('exports', 'Exports need unique JavaScript names.')
        names.add(row['name']); _text(row['signature'], 'signature', 1000)
        if not re.match(re.escape(row['name']) + r'\s*(?:\(|$)', row['signature']):
            _fail('signature', 'The export signature must start with its exact name.')
    tests = request['tests']
    if type(tests) is not list or not 1 <= len(tests) <= 256:
        _fail('tests', 'Supply 1..256 caller-authored acceptance tests.')
    coverage = set()
    for row in tests:
        _keys(row, ('requirement_ids', 'call', 'expected'))
        selected = _strings(row['requirement_ids'], 'requirement_ids', nonempty=True)
        if not set(selected) <= ids:
            _fail('requirements', 'A test references an unknown requirement.')
        coverage.update(selected); _text(row['call'], 'call', 4000); _expected(row['expected'])
    if coverage != ids:
        _fail('coverage', 'Every root requirement needs an explicit acceptance test.')
    outputs = _strings(request['allowed_outputs'], 'allowed_outputs', nonempty=True)
    artifact_format = request.get('artifact_format', 'javascript_script')
    if artifact_format not in ('javascript_script', 'javascript_modules'):
        _fail('artifact_format', 'Choose javascript_script or javascript_modules.')
    if artifact_format == 'javascript_script' and len(outputs) != 1:
        _fail('allowed_outputs', 'A script has exactly one output; use javascript_modules for multiple files.')
    for path in outputs:
        _path(path)
        if artifact_format == 'javascript_modules' and (not path.endswith(('.js', '.mjs')) or path == '__symblic_test__.mjs'):
            _fail('allowed_outputs', 'Module outputs need .js/.mjs paths distinct from the reserved verifier module.')
    if any(a != b and b.startswith(a + '/') for a in outputs for b in outputs):
        _fail('write_conflict', 'Allowed output files cannot be ancestors of one another.')
    result = {'version': VERSION, 'language': 'javascript', 'artifact_format': artifact_format,
              'objective': _text(request['objective'], 'objective'),
              'requirements': copy.deepcopy(requirements), 'exports': copy.deepcopy(exports),
              'tests': copy.deepcopy(tests), 'allowed_outputs': outputs,
              'budget': _budget(request.get('budget', {})),
              'assumptions': _strings(request.get('assumptions', []), 'assumptions')}
    _bounded(result)
    return result


def validate_refinement(obligation):
    """Exhaustively check an explicit bounded implication using native Symblic.

Unsupported syntax returns UNKNOWN. Empty premise support is UNPROVEN. Time and
kernel bounds return TIMEOUT. Nothing here evaluates JavaScript or opens a file.
"""
    _bounded(obligation)
    base = {'scope': 'declared_finite_refinement', 'obligation_sha256': digest(obligation),
            'prose_or_program_correctness': 'not_established'}
    if type(obligation) is not dict or obligation.get('kind') != 'finite_refinement':
        return {**base, 'status': 'UNKNOWN', 'reason': 'unsupported_refinement'}
    _keys(obligation, ('kind', 'variables', 'premises', 'conclusions'),
          ('requirement_ids', 'max_cases', 'timeout_ms', 'max_steps'))
    variables = obligation['variables']
    if type(variables) is not dict or not 1 <= len(variables) <= 12:
        _fail('variables', 'Refinement needs 1..12 finite variable domains.')
    count = 1
    for name, values in variables.items():
        if type(name) is not str or not _NAME.fullmatch(name) or type(values) is not list or not 1 <= len(values) <= 256:
            _fail('variables', 'Invalid finite variable domain.')
        if any(type(v) not in (str, int, bool) for v in values):
            _fail('variables', 'Domains contain exact scalar values only.')
        if any(type(v) is int and v.bit_length() > 128 for v in values):
            _fail('variables', 'Domain integer exceeds the finite checker bound.')
        if len({digest(v) for v in values}) != len(values):
            _fail('variables', 'Duplicate finite domain values.')
        count *= len(values)
    premises = _strings(obligation['premises'], 'premises', maximum=32)
    conclusions = _strings(obligation['conclusions'], 'conclusions', nonempty=True, maximum=32)
    limits = {'max_cases': (10000, 1, 10000), 'timeout_ms': (1000, 1, 5000), 'max_steps': (100000, 1, 500000)}
    values = {}
    for key, (default, low, high) in limits.items():
        item = obligation.get(key, default)
        if type(item) is not int or not low <= item <= high:
            _fail('refinement_budget', 'Invalid refinement budget.')
        values[key] = item
    if count > values['max_cases']:
        return {**base, 'status': 'UNKNOWN', 'reason': 'domain_budget', 'domain_cases': count}
    # Lazy inert native import: no process adapter may be called by this fragment.
    from symblic.kernel import language as S
    allowed = {'num', 'lit', 'str', 'name', 'un', 'bin', 'cmp', 'cond'}
    def inspect(node):
        if isinstance(node, (list, tuple)):
            for child in node:
                inspect(child)
            return
        if isinstance(node, dict):
            for child in node.values():
                inspect(child)
            return
        if not isinstance(node, S.Node):
            return
        if node.k not in allowed:
            raise ValueError('unsupported expression')
        if node.k == 'bin' and node.op not in ('+', '-', '*', '/', '%', 'and', 'or', 'implies'):
            raise ValueError('unsupported operator')
        if node.k == 'name' and node.name not in variables:
            raise ValueError('unknown variable')
        if node.k == 'num' and (node.value.numerator.bit_length() > 128 or node.value.denominator.bit_length() > 128):
            raise ValueError('number bound')
        for item in node.__dict__.values():
            inspect(item)
    try:
        parsed = []
        for text in premises + conclusions:
            if len(text) > 2000:
                raise ValueError('predicate bound')
            parser = S.Parser(S.tokenize(text), 1)
            node = parser.expr()
            if parser.peek() is not None:
                raise ValueError('trailing syntax')
            inspect(node); parsed.append(node)
    except (S.SymblicError, ValueError, TypeError, RecursionError, AttributeError):
        return {**base, 'status': 'UNKNOWN', 'reason': 'unsupported_predicate'}
    deadline = time.monotonic() + values['timeout_ms'] / 1000
    budget = S.Budget(values['max_steps'])
    tested = satisfying = 0
    try:
        for row in itertools.product(*variables.values()):
            if time.monotonic() >= deadline:
                return {**base, 'status': 'TIMEOUT', 'reason': 'wall_budget', 'tested_cases': tested}
            env = S.Env()
            for name, value in zip(variables, row):
                env.vars[name] = S.Binding(name, S.from_json(value))
            kernel = S.Kernel(env, budget=budget)
            answers = [kernel.eval(node) for node in parsed[:len(premises)]]
            if any(type(answer) is not bool for answer in answers):
                return {**base, 'status': 'UNKNOWN', 'reason': 'nonboolean_predicate', 'tested_cases': tested}
            tested += 1
            if not all(answers):
                continue
            satisfying += 1
            conclusions_result = [kernel.eval(node) for node in parsed[len(premises):]]
            if any(type(answer) is not bool for answer in conclusions_result):
                return {**base, 'status': 'UNKNOWN', 'reason': 'nonboolean_predicate', 'tested_cases': tested}
            if not all(conclusions_result):
                return {**base, 'status': 'REFUTED', 'counterexample': dict(zip(variables, row)),
                        'tested_cases': tested, 'domain_cases': count}
    except S.KernelLimitError:
        return {**base, 'status': 'TIMEOUT', 'reason': 'kernel_budget', 'tested_cases': tested}
    except (S.SymblicError, ArithmeticError, ValueError, RecursionError):
        return {**base, 'status': 'UNKNOWN', 'reason': 'predicate_undefined', 'tested_cases': tested}
    return {**base, 'status': 'PROVEN' if satisfying else 'UNPROVEN',
            'reason': 'finite_exhaustion' if satisfying else 'vacuous_premises',
            'tested_cases': tested, 'domain_cases': count, 'premise_cases': satisfying,
            'kernel': {'language': S.VERSION, 'canonical': S.CANON_VERSION, 'parser': S.PARSER_VERSION,
                       'core_source_sha256': getattr(S, '_symblic_import_identity', {}).get('sha256'),
                       'loaded_source_matched': getattr(S, '_symblic_import_identity', {}).get('matched', False),
                       'scope': 'native_core_expression_fragment_no_optional_adapter_probe'},
            'evidence': copy.deepcopy(obligation)}


def _eligibility(value):
    if type(value) is not dict or set(value) - {'local_only', 'models', 'nodes', 'digests', 'task_class', 'min_observations'}:
        _fail('model_eligibility', 'Unknown model eligibility fields.')
    if value.get('local_only', True) is not True:
        _fail('effects', 'MICA construction is local-model-only.')
    result = {'local_only': True, 'models': [], 'nodes': [], 'digests': [],
              'task_class': 'javascript_unit', 'min_observations': 0}
    result.update(copy.deepcopy(value))
    for field in ('models', 'nodes', 'digests'):
        result[field] = _strings(result[field], field)
    for sha in result['digests']:
        if not _SHA.fullmatch(sha):
            _fail('model_eligibility', 'Model digests must be exact SHA-256 identities.')
    _text(result['task_class'], 'task_class', 120)
    if type(result['min_observations']) is not int or not 0 <= result['min_observations'] <= 100000:
        _fail('model_eligibility', 'Invalid observation minimum.')
    return result


def _direct_literal_call(call):
    """A conservative comparison key, never a JavaScript parser or evaluator.

    Only a direct name(JSON-literals...) expression is recognized. Number tokens
    retain their exact spelling: -0, unsafe integers and exponent forms cannot
    silently merge. Object member order stays observable; duplicate keys and the
    object-literal __proto__ special form remain outside this fragment.
    """
    match = re.fullmatch(r'[ \t\r\n]*([A-Za-z_$][A-Za-z0-9_$]*)[ \t\r\n]*\((.*)\)[ \t\r\n]*', call, re.S)
    if match is None or len(call) > 4000:
        return None
    def number(raw):
        return ('number', raw)
    def pairs(items):
        keys = [key for key, _ in items]
        if '__proto__' in keys or len(keys) != len(set(keys)):
            raise ValueError('unsupported object literal')
        return ('object', tuple(items))
    try:
        args = json.loads('[' + match.group(2) + ']', parse_int=number, parse_float=number,
                          object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        remaining = 4096
        def key(value, depth=0):
            nonlocal remaining
            remaining -= 1
            if depth > 16 or remaining < 0:
                raise ValueError('literal bound')
            if value is None:
                return ('null',)
            if type(value) is bool:
                return ('boolean', value)
            if type(value) is str:
                return ('string', value)
            if type(value) is list:
                return ('array', tuple(key(item, depth + 1) for item in value))
            if type(value) is tuple and value[0] == 'number':
                return value
            if type(value) is tuple and value[0] == 'object':
                return ('object', tuple((name, key(item, depth + 1)) for name, item in value[1]))
            raise ValueError('unsupported literal')
        return match.group(1), key(args)
    except (ValueError, RecursionError, TypeError):
        return None


def _check_root_example_consistency(request, contracts):
    """Refuse only a conflicting expectation for the same admitted direct call.

    Source/signature/context applicability is deliberately narrow. This does not
    prove a unit contract complete or equivalent to arbitrary root expressions.
    Both root and unit declarations remain byte-for-byte unchanged on success.
    """
    root = {}
    for index, test in enumerate(request['tests']):
        key = _direct_literal_call(test['call'])
        if key is not None:
            root.setdefault(key, []).append((index, test))
    signatures = {export['name']: export['signature'] for export in request['exports']}
    for contract in contracts:
        unit = contract['unit']
        # Setup/dependency contexts can change expression meaning. No static
        # equality claim is made for them, even when the call text is identical.
        if unit['setup'] or unit['uses'] or contract['dependency_contract_ids']:
            continue
        applicable = {name for name in unit['names'] if name in signatures and
                      re.search(r'(?:^|,\s*)' + re.escape(signatures[name]) + r'(?:\s*,|$)', unit['heading'])}
        for example_index, (call, expected) in enumerate(unit['examples']):
            key = _direct_literal_call(call)
            if key is None or key[0] not in applicable or key not in root:
                continue
            # Reuse the existing trusted JSON equality, without starting Node,
            # probing runtime assets, or evaluating either call expression.
            from symblic.js import check as JS
            actual_expected = JS._parse(expected)
            for root_index, original in root[key]:
                if not JS.same(actual_expected, JS._parse(original['expected'])):
                    def excerpt(text):
                        return text if len(text) <= 400 else text[:397] + '...'
                    _fail('unit_example_conflict',
                          'Unit ' + contract['contract_id'] + ' example ' + str(example_index) +
                          ' conflicts with original root test ' + str(root_index) +
                          ' for ' + excerpt(original['call']) + '. Original expected JSON: ' +
                          excerpt(original['expected']) + '; proposed expected JSON: ' + excerpt(expected) +
                          '. Correct the proposed plan; original acceptance remains unchanged.')


def validate_plan(request, plan):
    """Validate one flat AND alternative; return a detached content-sealed plan.

Root tests are retained separately from model-authored unit examples. Dependency
edges must exactly match declared Uses. Paths are lexical authority constraints;
the trusted materializer must still reject filesystem symlinks at execution.
"""
    request = normalize_request(request)
    _bounded(plan)
    sealed_fields = {'version', 'id', 'request_sha256', 'assumptions', 'contracts', 'order',
                     'layers', 'spec_plan', 'refinements', 'root_tests', 'assurance',
                     'path_scope', 'content_hash'}
    if type(plan) is dict and set(plan) == sealed_fields:
        source = {key: copy.deepcopy(plan[key]) for key in ('version', 'id', 'assumptions', 'contracts')}
        rebuilt = validate_plan(request, source)
        if rebuilt != plan:
            _fail('sealed_plan', 'Sealed plan differs from complete current revalidation.')
        return rebuilt
    _keys(plan, ('id', 'contracts'), ('version', 'assumptions', 'content_hash'))
    if type(plan.get('version', VERSION)) is not int or plan.get('version', VERSION) != VERSION:
        _fail('version', 'Unsupported plan version.')
    _identifier(plan['id'])
    rows = plan['contracts']
    if type(rows) is not list or not 1 <= len(rows) <= request['budget']['max_units']:
        _fail('units', 'Plan exceeds its declared unit bound.')
    root_ids = {r['id'] for r in request['requirements']}
    contracts = []; ids = set(); export_owner = {}; covered = set(); artifacts = {}; refinements = []
    for original in rows:
        _keys(original, ('contract_id', 'root_requirement_ids', 'objective', 'unit', 'verification_obligations'),
              CONTRACT_FIELDS - {'contract_id', 'root_requirement_ids', 'objective', 'unit', 'verification_obligations'})
        ident = _identifier(original['contract_id'], 'contract_id')
        if ident == 'root' or ident in ids:
            _fail('contract_id', 'Contract IDs must be unique and differ from root.')
        ids.add(ident)
        if type(original.get('version', VERSION)) is not int or original.get('version', VERSION) != VERSION:
            _fail('version', 'Unsupported contract version.')
        selected = _strings(original['root_requirement_ids'], 'root_requirement_ids', nonempty=True)
        if not set(selected) <= root_ids:
            _fail('coverage', 'Contract references an unknown root requirement.')
        covered.update(selected)
        unit = copy.deepcopy(original['unit'])
        _keys(unit, ('names', 'heading', 'body', 'uses', 'setup', 'examples'))
        names = _strings(unit['names'], 'names', nonempty=True)
        for name in names:
            if not _NAME.fullmatch(name) or name in export_owner:
                _fail('exports', 'Unit exports must be valid and have a single owner.')
            export_owner[name] = ident
        _text(unit['heading'], 'heading', 1000); _text(unit['body'], 'body')
        _strings(unit['uses'], 'uses')
        if type(unit['setup']) is not str or len(unit['setup']) > 12000 or '\x00' in unit['setup']:
            _fail('setup', 'Setup must be bounded text.')
        if type(unit['examples']) is not list or not 1 <= len(unit['examples']) <= 256:
            _fail('checks', 'Every unit needs explicit nonempty examples.')
        for example in unit['examples']:
            if type(example) is not list or len(example) != 2:
                _fail('checks', 'Examples must be call/expected-JSON pairs.')
            _text(example[0], 'call', 4000); _expected(example[1])
        row = {'version': VERSION, 'contract_id': ident, 'parent_contract_id': 'root',
               'root_requirement_ids': selected, 'objective': _text(original['objective'], 'objective'),
               'preconditions': [], 'postconditions': [], 'invariants': [], 'input_artifacts': [],
               'output_artifacts': ['units/' + ident + '.js'], 'dependency_contract_ids': [],
               'permitted_read_scope': [], 'permitted_write_scope': [], 'permitted_effects': [],
               'verification_obligations': copy.deepcopy(original['verification_obligations']),
               'resource_budget': {}, 'model_eligibility': {},
               'failure_policy': {'action': 'refine_or_escalate', 'retries': request['budget']['retries']},
               'unit': unit}
        for key in CONTRACT_FIELDS - {'content_hash', 'unit'}:
            if key in original:
                row[key] = copy.deepcopy(original[key])
        if 'construction' in row:
            # This optional compiler declaration grants no execution/effect
            # authority. Omission preserves the historical normalized shape.
            from symblic.mica import deterministic as D
            try:
                row['construction'] = D.normalize(row['construction'], unit)
            except D.DeterministicError as error:
                _fail('construction_' + error.code, str(error))
        _identifier(row['parent_contract_id'], 'parent_contract_id')
        for key in ('preconditions', 'postconditions', 'invariants', 'input_artifacts', 'output_artifacts',
                    'dependency_contract_ids', 'permitted_read_scope', 'permitted_write_scope', 'permitted_effects'):
            _strings(row[key], key, nonempty=key == 'output_artifacts')
        if row['permitted_effects']:
            _fail('effects', 'No effects are allowed in a pure construction contract.')
        for path in row['input_artifacts'] + row['output_artifacts'] + row['permitted_read_scope'] + row['permitted_write_scope']:
            _path(path)
        for path in row['output_artifacts']:
            if path not in request['allowed_outputs'] and path != 'units/' + ident + '.js':
                _fail('write_scope', 'Output is outside the caller-authorized paths.')
            if request['artifact_format'] == 'javascript_modules' and (
                    len(row['output_artifacts']) != 1 or not path.endswith(('.js', '.mjs')) or
                    path == '__symblic_test__.mjs' or path == request['allowed_outputs'][0]):
                _fail('module_layout', 'Each unit needs one .js/.mjs module distinct from the public entry.')
            if any(path == other or path.startswith(other + '/') or other.startswith(path + '/') for other in artifacts):
                _fail('write_conflict', 'Contract output files conflict or overlap.')
            artifacts[path] = ident
        if not set(row['permitted_write_scope']) <= set(row['output_artifacts']):
            _fail('write_scope', 'Write scope exceeds the contract output paths.')
        if not set(row['permitted_read_scope']) <= set(row['input_artifacts']):
            _fail('read_scope', 'Read scope exceeds explicitly selected input artifacts.')
        row['resource_budget'] = _budget(row['resource_budget'], defaults=request['budget'])
        if any(row['resource_budget'][k] > request['budget'][k] for k in BUDGET_LIMITS):
            _fail('budget', 'A contract cannot increase a root resource bound.')
        row['model_eligibility'] = _eligibility(row['model_eligibility'])
        policy = row['failure_policy']
        _keys(policy, ('action', 'retries'))
        if policy['action'] not in ('stop', 'refine', 'escalate', 'refine_or_escalate') or type(policy['retries']) is not int or not 0 <= policy['retries'] <= request['budget']['retries']:
            _fail('failure_policy', 'Invalid bounded failure policy.')
        obligations = row['verification_obligations']
        if type(obligations) is not list or not 1 <= len(obligations) <= 32:
            _fail('checks', 'Every contract needs explicit verification obligations.')
        checked_ids = set()
        for obligation in obligations:
            if type(obligation) is not dict:
                _fail('checks', 'Verification obligations must be objects.')
            if obligation.get('kind') == 'unit_examples':
                _keys(obligation, ('kind', 'requirement_ids'))
            elif obligation.get('kind') == 'finite_refinement':
                if len(refinements) >= 32:
                    _fail('refinement_budget', 'A plan may contain at most 32 formal refinement obligations.')
                proof = validate_refinement(obligation)
                if proof['status'] == 'REFUTED':
                    _fail('refinement_refuted', 'A declared formal refinement has a counterexample.')
                refinements.append({'contract_id': ident, 'requirement_ids': obligation.get('requirement_ids', []), **proof})
            else:
                _fail('checks', 'Unsupported verification obligation kind.')
            reqs = _strings(obligation.get('requirement_ids'), 'requirement_ids', nonempty=True)
            if not set(reqs) <= set(selected):
                _fail('checks', 'Obligation requirements exceed the contract mapping.')
            checked_ids.update(reqs)
        if checked_ids != set(selected):
            _fail('checks', 'Every mapped requirement needs an explicit obligation.')
        row['content_hash'] = digest(row)
        if original.get('content_hash') is not None and original['content_hash'] != row['content_hash']:
            _fail('content_hash', 'Contract differs from its claimed content hash.')
        contracts.append(row)
    if covered != root_ids:
        _fail('coverage', 'Plan does not cover every root requirement.')
    if not {r['name'] for r in request['exports']} <= set(export_owner):
        _fail('exports', 'Plan omits a caller-declared output export.')
    if request['artifact_format'] == 'javascript_modules' and not set(request['allowed_outputs'][1:]) <= set(artifacts):
        _fail('module_layout', 'Every additional declared output must be assigned to exactly one unit.')
    by_id = {r['contract_id']: r for r in contracts}
    for row in contracts:
        ident = row['contract_id']; parent = row['parent_contract_id']
        if parent != 'root' and parent not in by_id:
            _fail('parent', 'Unknown parent contract.')
        trail = {ident}; depth = 1
        while parent != 'root':
            if parent in trail:
                _fail('parent_cycle', 'Parent relation contains a cycle.')
            trail.add(parent); depth += 1; parent = by_id[parent]['parent_contract_id']
            if parent != 'root' and parent not in by_id:
                _fail('parent', 'Unknown parent contract.')
        if depth > request['budget']['max_depth']:
            _fail('depth', 'Contract hierarchy exceeds the root depth bound.')
        dependencies = set(row['dependency_contract_ids'])
        if not dependencies <= ids or ident in dependencies:
            _fail('dependency', 'Dependency IDs must name other contracts.')
        actual = set()
        for used in row['unit']['uses']:
            match = re.match(r'[A-Za-z_$][A-Za-z0-9_$]*', used)
            if not match or match.group(0) not in export_owner:
                _fail('uses', 'Uses must resolve to declared unit exports.')
            actual.add(export_owner[match.group(0)])
        if actual != dependencies:
            _fail('dependency', 'Uses and dependency contract IDs must agree exactly.')
        available = {path for dep in dependencies for path in by_id[dep]['output_artifacts']}
        if not set(row['input_artifacts']) <= available:
            _fail('read_scope', 'Inputs must come from declared dependency artifacts.')
    _check_root_example_consistency(request, contracts)
    # Existing exact contract planner decides topology, layers and stable export IDs.
    from symblic.spec import contracts as C
    sheet = {'title': request['allowed_outputs'][0], 'intro': request['objective'], 'shared': '',
             'units': [r['unit'] for r in contracts],
             'template': {'file': request['allowed_outputs'][0], 'text': '/*UNITS*/', 'note': ''}}
    try:
        native = C.plan(sheet)
    except C.ContractError as error:
        _fail(error.code, str(error))
    native_to_contract = {r['id']: export_owner[r['exports'][0]] for r in native['units']}
    proven = {req for r in refinements if r['status'] == 'PROVEN' for req in r['requirement_ids']}
    required = {r['id'] for r in request['requirements'] if r['acceptance'] == 'PROVEN'}
    if not required <= proven:
        _fail('refinement_unproven', 'PROVEN requirements need supported explicit finite refinement obligations.')
    result = {'version': VERSION, 'id': plan['id'], 'request_sha256': digest(request),
              'assumptions': _strings(plan.get('assumptions', []), 'assumptions'), 'contracts': contracts,
              'order': [native_to_contract[x] for x in native['order']],
              'layers': [[native_to_contract[x] for x in layer] for layer in native['layers']],
              'spec_plan': native, 'refinements': refinements,
              'root_tests': copy.deepcopy(request['tests']),
              'assurance': 'validated_declarations_pending_execution_and_refinement_linkage',
              'path_scope': 'lexical_only_host_must_reject_symlinks'}
    result['content_hash'] = digest(result)
    if plan.get('content_hash') is not None and plan['content_hash'] != result['content_hash']:
        _fail('content_hash', 'Plan differs from its claimed content hash.')
    return result

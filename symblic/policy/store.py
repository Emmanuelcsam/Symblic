"""Policy experiments: a durable, private store that runs the train / select / held-out protocol end to end.

What it is for
    PolicyExperiment turns symblic.policy.learning into a lifecycle that survives crashes:
    1. freeze(root, ident, training_plan, heldout_plan, training_fixtures, heldout_fixtures, cost_unit=...)
       writes the plans and the evaluator-owned fixtures (case_fixture: input + expected output, scored by exact
       equality) as immutable files, records the hashes of this package's implementation files and returns a
       handle pinned by the freeze hash. Reopen it with PolicyExperiment(root, ident, expected_freeze_hash=...).
    2. assignments('training') lists every (candidate, case) pair; run_assignment(...) writes a durable intent,
       calls a runner you inject (for example symblic.policy.graph.GraphPolicyRunner) with the policy and the
       case input only, and records the exact output, the attempts and the score computed here.
    3. seal_training() runs the selector once every training assignment is settled; seal_heldout() runs the
       held-out comparison for the chosen policy and the baseline. status() summarizes the experiment.
    An interrupted assignment is settled with reconcile_assignment(..., resolver=...), a recovery callback you
    supply; an intent whose outcome is unknown is never silently re-run.

What it is not
    It starts no worker, calls no provider and never adopts the selected policy anywhere. Directories are 0700
    and files 0600 for the current user; hashes are integrity pins against the freeze record, not signatures.
    The caller chooses the root directory and decides who may call it.

Depends on: the standard library (fcntl), symblic.policy.learning and symblic.kernel.execution_pins (cached
bytecode check). Used by: symblic.policy.graph and the original host's policy routes
(integration/host/symblic_policy_api.py). Status: prototype; tested with temporary stores and fake runners
(tests/policy). Design notes: docs/reference/POLICY-EXPERIMENTS.md.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

from symblic.policy import learning as P

VERSION = 1
SCORER = 'exact-output-v1'
MAX_FILE = P.MAX_BYTES
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')
_SCOPES = frozenset({'schema', 'encoded_predicate', 'formal_proof', 'source_witness'})
# The source files an experiment's freeze record binds, as POSIX paths relative to _BASE (the folder that holds
# the symblic package, the same base as symblic.kernel.execution_pins). In the original host the host's policy
# routes were bound here too; a host now passes its own identity through freeze(host_identity=...).
IMPLEMENTATION_FILES = ('symblic/policy/learning.py', 'symblic/policy/store.py', 'symblic/policy/graph.py',
                        'symblic/graph/planner.py', 'symblic/graph/run.py')
_BASE = Path(__file__).resolve().parents[2]


def _source_bytes(name):
    path = _BASE / name
    if path.is_symlink():
        raise PolicyStoreError('implementation_source')
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE + 1)
    except OSError:
        raise PolicyStoreError('implementation_source') from None
    if len(raw) > MAX_FILE:
        raise PolicyStoreError('implementation_source')
    return raw


class PolicyStoreError(P.PolicyError):
    """Finite diagnostic code; messages never echo private inputs or callbacks."""


_IMPORTED_HASHES = {name: hashlib.sha256(_source_bytes(name)).hexdigest() for name in IMPLEMENTATION_FILES}


def _implementation():
    # Lazy reuse of the bounded bytecode compatibility check; this starts no
    # worker/provider and never executes graph source or a candidate policy.
    from symblic.kernel import execution_pins as X
    current = {}
    for name in IMPLEMENTATION_FILES:
        raw = _source_bytes(name)
        identity = hashlib.sha256(raw).hexdigest()
        loaded = sys.modules.get(name[:-3].replace('/', '.'))
        loaded_hash = getattr(loaded, '_SOURCE_SHA256', None)
        if loaded_hash is None:
            loaded_hash = getattr(loaded, '_GRAPH_HASHES', {}).get(name)
        if loaded_hash is not None and loaded_hash != identity:
            _fail('implementation_loaded_source')
        if identity != _IMPORTED_HASHES[name]:
            _fail('implementation_changed_use_fresh_worker')
        if not X._bytecode_matches(name, raw):
            _fail('implementation_bytecode')
        current[name] = identity
    return current


def _fail(code):
    raise PolicyStoreError(code)


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value) or value in ('.', '..'):
        _fail('identifier')


def _hash(value):
    try:
        return P.digest(value)
    except P.PolicyError as exc:
        raise PolicyStoreError(str(exc)) from None


def _sha(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value):
        _fail('hash')


def _fields(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        _fail('schema')


def _integer(value, maximum=P.MAX_INT):
    if type(value) is not int or not 0 <= value <= maximum:
        _fail('integer')


def _directory(path, create=False):
    try:
        if create:
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        info = path.lstat()
    except OSError:
        raise PolicyStoreError('private_directory') from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        _fail('private_directory')


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _fail('duplicate_key')
            out[key] = value
        return out
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_FILE):
                _fail('private_file')
            raw = handle.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            _fail('file_limit')
        value = json.loads(raw, object_pairs_hook=pairs)
        _hash(value)
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        if canonical != raw:
            _fail('noncanonical_file')
        return value
    except (OSError, ValueError, RecursionError) as exc:
        if isinstance(exc, PolicyStoreError):
            raise
        raise PolicyStoreError('unreadable_file') from None


def _write_immutable(path, value):
    """Publish a complete fsynced file without replacing existing history."""
    identity = _hash(value)
    if path.exists():
        if _hash(_read(path)) != identity:
            _fail('immutable_conflict')
        return identity
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if len(raw) > MAX_FILE:
        _fail('file_limit')
    descriptor, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if _hash(_read(path)) != identity:
                _fail('immutable_conflict')
        finally:
            os.unlink(temporary)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return identity


def case_fixture(input_value, expected, *, family_hash, exposure_hashes=()):
    """Host-owned fixture; only input_value will be sent to a runner."""
    _sha(family_hash)
    body = {'input': copy.deepcopy(input_value), 'expected': copy.deepcopy(expected), 'scorer': SCORER}
    metadata = {'case_hash': _hash(body), 'input_hash': _hash(input_value),
                'family_hash': family_hash, 'exposure_hashes': list(exposure_hashes)}
    P._cases([metadata])
    return {'case': metadata, 'input': body['input'], 'expected': body['expected']}


def _fixtures(plan_cases, fixtures):
    _hash(fixtures)
    if type(fixtures) is not list or len(fixtures) != len(plan_cases):
        _fail('fixtures')
    expected = {case['case_hash']: case for case in plan_cases}
    indexed = {}
    for fixture in fixtures:
        _fields(fixture, 'case input expected')
        metadata = fixture['case']
        P._cases([metadata])
        rebuilt = case_fixture(fixture['input'], fixture['expected'],
                               family_hash=metadata['family_hash'], exposure_hashes=metadata['exposure_hashes'])
        if rebuilt != fixture or expected.get(metadata['case_hash']) != metadata:
            _fail('fixture_pin')
        if metadata['case_hash'] in indexed:
            _fail('duplicate_fixture')
        indexed[metadata['case_hash']] = fixture
    return indexed


class PolicyExperiment:
    """Explicit private-store handle, pinned by its host-held freeze identity."""

    def __init__(self, root, ident, *, expected_freeze_hash):
        _id(ident)
        _sha(expected_freeze_hash)
        self.path = Path(root) / ident
        _directory(self.path)
        self.ident, self.freeze_hash = ident, expected_freeze_hash
        self._cache = {}

    @classmethod
    def freeze(cls, root, ident, training_plan, heldout_plan, training_fixtures, heldout_fixtures, *, cost_unit,
               host_identity=None):
        _id(ident)
        if type(cost_unit) is not str or not 1 <= len(cost_unit) <= 160 or any(ord(x) < 32 for x in cost_unit):
            _fail('cost_unit')
        P._scan([training_plan, heldout_plan, training_fixtures, heldout_fixtures])
        _hash(host_identity)
        P._plan(training_plan)
        _fields(heldout_plan, 'version training_plan_hash cases')
        if type(heldout_plan['version']) is not int or heldout_plan['version'] != P.VERSION:
            _fail('version')
        if heldout_plan['training_plan_hash'] != _hash(training_plan):
            _fail('training_plan_pin')
        P.validate_split(training_plan['cases'], heldout_plan['cases'])
        _fixtures(training_plan['cases'], training_fixtures)
        _fixtures(heldout_plan['cases'], heldout_fixtures)
        files = {'training-plan.json': training_plan, 'heldout-plan.json': heldout_plan,
                 'training-cases.json': training_fixtures, 'heldout-cases.json': heldout_fixtures}
        manifest = {'version': VERSION, 'selector_version': P.VERSION, 'experiment': ident,
                    'scorer': SCORER, 'cost_unit': cost_unit,
                    'implementation': _implementation(),
                    'host_identity': copy.deepcopy(host_identity),
                    'files': {name: _hash(value) for name, value in files.items()}}
        parent = Path(root)
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = parent / ident
        _directory(path, create=True)
        experiment = cls(root, ident, expected_freeze_hash=_hash(manifest))
        with experiment._lock():
            if (path / 'frozen.json').exists():
                if _hash(_read(path / 'frozen.json')) != experiment.freeze_hash:
                    _fail('immutable_conflict')
                return experiment
            for name, value in files.items():
                _write_immutable(path / name, value)
            _write_immutable(path / 'frozen.json', manifest)
            _sync_directory(parent)
        return experiment

    @contextmanager
    def _lock(self):
        _directory(self.path)
        fd = os.open(self.path / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                _fail('private_lock')
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._cache = {}
            yield
        finally:
            self._cache = {}
            os.close(fd)

    def _manifest(self, *, require_current_implementation=True):
        if 'manifest' in self._cache:
            m = self._cache['manifest']
            if require_current_implementation and not m.get('_implementation_match', True):
                _fail('implementation_pin')
            return m
        value = _read(self.path / 'frozen.json')
        if _hash(value) != self.freeze_hash:
            _fail('freeze_pin')
        _fields(value, 'version selector_version experiment scorer cost_unit implementation host_identity files')
        try:
            implementation_match = (value['implementation'] == _implementation())
        except PolicyStoreError:
            if require_current_implementation:
                raise
            implementation_match = False
        if require_current_implementation and not implementation_match:
            _fail('implementation_pin')
        if (type(value['version']) is not int or type(value['selector_version']) is not int
                or value['version'] != VERSION or value['selector_version'] != P.VERSION
                or value['scorer'] != SCORER or value['experiment'] != self.ident):
            _fail('version')
        if (type(value['files']) is not dict or set(value['files']) != {
                'training-plan.json', 'heldout-plan.json', 'training-cases.json', 'heldout-cases.json'}):
            _fail('manifest_files')
        for identity in value['files'].values():
            _sha(identity)
        value['_implementation_match'] = implementation_match
        self._cache['manifest'] = value
        return value

    def _pinned(self, name, *, require_current_implementation=True):
        manifest = self._manifest(require_current_implementation=require_current_implementation)
        if name in self._cache:
            return self._cache[name]
        value = _read(self.path / name)
        if _hash(value) != manifest['files'][name]:
            _fail('file_pin')
        self._cache[name] = value
        return value

    def _selection(self, *, require_current_implementation=True):
        if 'selection' in self._cache:
            sel = self._cache['selection']
            if not require_current_implementation or not sel.get('_unverified'):
                return sel
        value = _read(self.path / 'selection.json')
        _fields(value, 'freeze_sha256 selection selection_sha256 training_records_sha256')
        if value['freeze_sha256'] != self.freeze_hash or value['selection_sha256'] != _hash(value['selection']):
            _fail('selection_pin')
        if require_current_implementation:
            plan, records = self._pinned('training-plan.json'), self._records('training')
            if _hash(records) != value['training_records_sha256']:
                _fail('training_records_pin')
            replay = P.select(plan, records, expected_plan_hash=_hash(plan), expected_records_hash=_hash(records))
            if value['selection'] != replay:
                _fail('selection_pin')
        else:
            value['_unverified'] = True
        self._cache['selection'] = value
        return value

    def selection(self):
        """Training-only receipt: this method never opens heldout data files."""
        with self._lock():
            self._manifest()
            return self._selection()['selection']

    def assert_host_identity(self, identity):
        """Host checks its current runtime/measurement contract against the frozen one."""
        supplied = _hash(identity)
        with self._lock():
            if supplied != _hash(self._manifest()['host_identity']):
                _fail('host_identity_pin')
        return supplied

    def _assignment(self, stage, candidate, case_hash, *, require_current_implementation=True):
        if stage not in ('training', 'heldout'):
            _fail('stage')
        _sha(candidate)
        _sha(case_hash)
        plan = self._pinned('training-plan.json', require_current_implementation=require_current_implementation)
        policies = {row['sha256']: row['policy'] for row in plan['candidates']}
        if stage == 'heldout':
            if not (self.path / 'selection.json').exists():
                _fail('heldout_not_open')
            chosen = self._selection(require_current_implementation=require_current_implementation)['selection']['selected']['sha256']
            if candidate not in (chosen, plan['baseline']):
                _fail('unassigned_candidate')
        if candidate not in policies:
            _fail('unassigned_candidate')
        phase_plan = plan if stage == 'training' else self._pinned('heldout-plan.json', require_current_implementation=require_current_implementation)
        fixture_key = 'fixtures:' + stage
        if fixture_key not in self._cache:
            self._cache[fixture_key] = _fixtures(phase_plan['cases'], self._pinned(stage + '-cases.json', require_current_implementation=require_current_implementation))
        fixtures = self._cache[fixture_key]
        if case_hash not in fixtures:
            _fail('unassigned_case')
        identity = _hash([self.freeze_hash, stage, candidate, case_hash])
        directory = self.path / ('assignment-' + identity)
        if directory.exists() or directory.is_symlink():
            _directory(directory)
        fixture = fixtures[case_hash]
        request = {'version': VERSION, 'assignment_id': identity, 'experiment_sha256': self.freeze_hash,
                   'stage': stage, 'candidate_sha256': candidate, 'case_hash': case_hash,
                   'policy': copy.deepcopy(policies[candidate]), 'input': copy.deepcopy(fixture['input']),
                   'budget': copy.deepcopy(plan['budget']), 'cost_unit': self._manifest(require_current_implementation=require_current_implementation)['cost_unit']}
        return directory, request, fixture, plan

    def _phase_open(self, stage):
        if (self.path / 'evaluation.json').exists():
            _fail('experiment_sealed')
        if stage == 'training' and (self.path / 'selection.json').exists():
            _fail('training_sealed')

    def _outcome(self, request, fixture, plan, outcome):
        _hash(outcome)
        _fields(outcome, 'status output attempts checks complete effects')
        if type(outcome['status']) is not str or outcome['status'] not in ('done', 'failed', 'refused', 'uncertain'):
            _fail('outcome_status')
        if (outcome['complete'] is not True or type(outcome['effects']) is not str
                or outcome['effects'] not in ('none', 'settled')):
            _fail('incomplete_outcome')
        if outcome['status'] == 'uncertain':
            _fail('incomplete_outcome')
        attempts = outcome['attempts']
        if type(attempts) is not list or len(attempts) > P.MAX_ATTEMPTS:
            _fail('attempts')
        identities, calls, cost = set(), 0, 0
        for attempt in attempts:
            _fields(attempt, 'id request_sha256 calls cost_units status')
            _id(attempt['id'])
            _sha(attempt['request_sha256'])
            _integer(attempt['calls'])
            _integer(attempt['cost_units'])
            if type(attempt['status']) is not str or attempt['status'] not in ('done', 'failed', 'refused'):
                _fail('attempt_unresolved')
            if attempt['id'] in identities:
                _fail('duplicate_attempt')
            identities.add(attempt['id'])
            calls += attempt['calls']
            cost += attempt['cost_units']
        if calls > plan['budget']['max_calls'] or cost > plan['budget']['max_cost_units']:
            _fail('budget_exceeded')
        checks = outcome['checks']
        if type(checks) is not list or len(checks) > 64:
            _fail('checks')
        subject = _hash(outcome['output'])
        for check in checks:
            _fields(check, 'scope passed subject_sha256 checker_sha256')
            if type(check['scope']) is not str or check['scope'] not in _SCOPES or type(check['passed']) is not bool:
                _fail('check_scope')
            _sha(check['checker_sha256'])
            if check['subject_sha256'] != subject:
                _fail('check_subject')
        matched = _hash(fixture['expected']) == subject
        accepted = outcome['status'] == 'done' and matched and all(check['passed'] for check in checks)
        status = 'success' if accepted else 'refused' if outcome['status'] == 'refused' else 'failed'
        record = {'candidate': request['candidate_sha256'], 'case': request['case_hash'],
                  'status': status, 'score': plan['objective']['max_score'] if accepted else 0,
                  'attempts': [{'calls': item['calls'], 'cost_units': item['cost_units']} for item in attempts]}
        return {'version': VERSION, 'assignment_id': request['assignment_id'],
                'request_sha256': _hash(request), 'outcome_sha256': _hash(outcome),
                'record': record, 'attempt_ids': sorted(identities),
                'score_receipt': {'scorer': SCORER, 'scope': 'exact_match_to_declared_expected_output',
                                  'passed': accepted, 'output_sha256': subject,
                                  'expected_sha256': _hash(fixture['expected']),
                                  'empirical_truth': 'not_established', 'causality': 'not_established'}}

    def _commit(self, directory, request, fixture, plan, outcome, *, recovered=False):
        result = self._outcome(request, fixture, plan, outcome)
        for path in self.path.glob('assignment-*/result.json'):
            if path.parent != directory:
                _directory(path.parent)
                prior = _read(path)
                if set(result['attempt_ids']) & set(prior['attempt_ids']):
                    _fail('attempt_reused')
        outcome_name = ('reconciled-' + result['outcome_sha256'] + '.json') if recovered else 'outcome.json'
        _write_immutable(directory / outcome_name, outcome)
        result['outcome_file'] = outcome_name
        _write_immutable(directory / 'result.json', result)
        return result

    def run_assignment(self, stage, candidate, case_hash, *, runner):
        """At most one dispatch per assignment; interruption never triggers a new one."""
        if not callable(runner):
            _fail('runner')
        with self._lock():
            directory, request, fixture, plan = self._assignment(stage, candidate, case_hash)
            if (directory / 'result.json').exists():
                return self._checked_result(directory, request, fixture, plan)
            self._phase_open(stage)
            _directory(directory, create=True)
            if (directory / 'intent.json').exists():
                if _hash(_read(directory / 'intent.json')) != _hash(request):
                    _fail('intent_pin')
                if (directory / 'outcome.json').exists():
                    return self._commit(directory, request, fixture, plan, _read(directory / 'outcome.json'))
                _fail('assignment_in_doubt')
            _write_immutable(directory / 'intent.json', request)
            _sync_directory(self.path)
        try:
            outcome = runner(copy.deepcopy(request))
        except Exception:  # noqa: BLE001 - injected callbacks must not leak private exception text.
            raise PolicyStoreError('runner_unresolved') from None
        with self._lock():
            checked_directory, checked_request, fixture, plan = self._assignment(stage, candidate, case_hash)
            if directory != checked_directory or request != checked_request:
                _fail('intent_pin')
            # Preserve every bounded returned outcome, even one that cannot be
            # accepted. The unresolved intent blocks sealing and redispatch.
            _write_immutable(directory / 'outcome.json', outcome)
            return self._commit(directory, request, fixture, plan, outcome)

    def reconcile_assignment(self, stage, candidate, case_hash, *, resolver):
        """Resolve or continue through a trusted host using the original pinned request.

        A resolver may continue work proven never started. It must retain issued
        intents and must never redispatch an uncertain external call or effect.
        """
        if not callable(resolver):
            _fail('resolver')
        with self._lock():
            directory, request, fixture, plan = self._assignment(stage, candidate, case_hash)
            if (directory / 'result.json').exists():
                return self._checked_result(directory, request, fixture, plan)
            self._phase_open(stage)
            if not (directory / 'intent.json').exists() or _hash(_read(directory / 'intent.json')) != _hash(request):
                _fail('missing_intent')
        try:
            outcome = resolver(copy.deepcopy(request))
        except Exception:  # noqa: BLE001 - preserve unresolved intent; no hidden retry.
            raise PolicyStoreError('resolver_unresolved') from None
        with self._lock():
            checked_directory, checked_request, fixture, plan = self._assignment(stage, candidate, case_hash)
            if directory != checked_directory or request != checked_request:
                _fail('intent_pin')
            return self._commit(directory, request, fixture, plan, outcome, recovered=True)

    def _checked_result(self, directory, request, fixture, plan):
        stored = _read(directory / 'result.json')
        name = stored.get('outcome_file')
        if name != 'outcome.json' and name != 'reconciled-' + str(stored.get('outcome_sha256')) + '.json':
            _fail('outcome_file')
        outcome = _read(directory / name)
        expected = self._outcome(request, fixture, plan, outcome)
        expected['outcome_file'] = name
        if stored != expected or _hash(_read(directory / 'intent.json')) != _hash(request):
            _fail('result_pin')
        return stored

    def _records(self, stage):
        plan = self._pinned('training-plan.json')
        candidates = [item['sha256'] for item in plan['candidates']]
        cases = plan['cases']
        if stage == 'heldout':
            candidates = sorted({self._selection()['selection']['selected']['sha256'], plan['baseline']})
            cases = self._pinned('heldout-plan.json')['cases']
        records, identities = [], set()
        for candidate in sorted(candidates):
            for case in sorted(cases, key=lambda value: value['case_hash']):
                directory, request, fixture, current = self._assignment(stage, candidate, case['case_hash'])
                if not (directory / 'result.json').exists():
                    _fail('incomplete_assignments')
                result = self._checked_result(directory, request, fixture, current)
                if identities & set(result['attempt_ids']):
                    _fail('attempt_reused')
                identities.update(result['attempt_ids'])
                records.append(result['record'])
        return records

    def _assignments(self, stage, *, require_current_implementation=True):
        if stage not in ('training', 'heldout'):
            _fail('stage')
        plan = self._pinned('training-plan.json', require_current_implementation=require_current_implementation)
        candidates = [row['sha256'] for row in plan['candidates']]
        cases = plan['cases']
        if stage == 'heldout':
            if not (self.path / 'selection.json').exists():
                _fail('heldout_not_open')
            sel = self._selection(require_current_implementation=require_current_implementation)
            chosen = sel['selection']['selected']['sha256']
            candidates = sorted({chosen, plan['baseline']})
            cases = self._pinned('heldout-plan.json', require_current_implementation=require_current_implementation)['cases']
        descriptors = []
        for candidate in sorted(candidates):
            for case in sorted(cases, key=lambda row: row['case_hash']):
                directory, request, fixture, current = self._assignment(stage, candidate, case['case_hash'],
                                                                        require_current_implementation=require_current_implementation)
                state = 'pending'
                if (directory / 'result.json').exists():
                    if require_current_implementation:
                        self._checked_result(directory, request, fixture, current)
                    else:
                        if (directory / 'intent.json').exists() and _hash(_read(directory / 'intent.json')) != _hash(request):
                            _fail('intent_pin')
                    state = 'terminal'
                elif (directory / 'intent.json').exists():
                    if _hash(_read(directory / 'intent.json')) != _hash(request):
                        _fail('intent_pin')
                    state = 'inflight'
                descriptors.append({key: copy.deepcopy(request[key]) for key in (
                    'assignment_id', 'stage', 'candidate_sha256', 'case_hash', 'policy')} | {'state': state})
        return descriptors

    def assignments(self, stage, *, require_current_implementation=True):
        """Scheduling/recovery descriptors; no fixture inputs, gold or raw outcomes."""
        with self._lock():
            return self._assignments(stage, require_current_implementation=require_current_implementation)

    def status(self, *, audit_implementation=True):
        """Safe UI projection. An inflight assignment may need host reconciliation."""
        with self._lock():
            manifest = self._manifest(require_current_implementation=audit_implementation)
            plan = self._pinned('training-plan.json', require_current_implementation=audit_implementation)
            implementation_match = manifest.get('_implementation_match', True)
            assurance = 'verified' if (audit_implementation and implementation_match) else (
                'recorded; current assurance unavailable (implementation changed)' if not implementation_match else 'recorded'
            )
            result = {'version': VERSION, 'experiment': self.ident, 'freeze_sha256': self.freeze_hash,
                      'frozen_hashes': copy.deepcopy(manifest['files']), 'stage': 'training',
                      'implementation_hashes': copy.deepcopy(manifest['implementation']),
                      'host_identity_sha256': _hash(manifest['host_identity']),
                      'cost_unit': manifest['cost_unit'], 'candidates': copy.deepcopy(plan['candidates']),
                      'assignments': {}, 'selected': None, 'evaluation': None,
                      'implementation_intact': implementation_match, 'assurance': assurance}
            stages = ['training']
            if (self.path / 'selection.json').exists():
                sel = self._selection(require_current_implementation=audit_implementation)
                result['selected'] = sel['selection']
                result['stage'] = 'heldout'
                stages.append('heldout')
            for stage in stages:
                rows = self._assignments(stage, require_current_implementation=audit_implementation)
                result['assignments'][stage] = {
                    state: {'count': sum(row['state'] == state for row in rows),
                            'assignment_ids': [row['assignment_id'] for row in rows if row['state'] == state]}
                    for state in ('pending', 'inflight', 'terminal')}
            if (self.path / 'evaluation.json').exists():
                if audit_implementation:
                    evaluation = self._evaluation()
                    if _read(self.path / 'evaluation.json') != evaluation:
                        _fail('evaluation_pin')
                else:
                    evaluation = _read(self.path / 'evaluation.json')
                result['evaluation'], result['stage'] = evaluation, 'evaluated'
            return result

    def seal_training(self):
        with self._lock():
            self._manifest()
            if (self.path / 'selection.json').exists():
                return self._selection()['selection']
            plan, records = self._pinned('training-plan.json'), self._records('training')
            selection = P.select(plan, records, expected_plan_hash=_hash(plan), expected_records_hash=_hash(records))
            value = {'freeze_sha256': self.freeze_hash, 'selection': selection,
                     'selection_sha256': _hash(selection), 'training_records_sha256': _hash(records)}
            _write_immutable(self.path / 'selection.json', value)
            return selection

    def _evaluation(self):
        selected = self._selection()
        plan, records = self._pinned('training-plan.json'), self._records('training')
        if _hash(records) != selected['training_records_sha256']:
            _fail('training_records_pin')
        hp, hr = self._pinned('heldout-plan.json'), self._records('heldout')
        pins = {'training_plan': _hash(plan), 'training_records': _hash(records),
                'selection': selected['selection_sha256'], 'heldout_plan': _hash(hp), 'heldout_records': _hash(hr)}
        return P.evaluate_heldout(plan, records, selected['selection'], hp, hr, pins=pins)

    def seal_heldout(self):
        with self._lock():
            self._manifest()
            evaluation = self._evaluation()
            _write_immutable(self.path / 'evaluation.json', evaluation)
            return evaluation

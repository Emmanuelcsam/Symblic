"""Constructor bridge: let the native Run answer an `ask` with the linear constructor, durably and checkably.

What it is for
    With the run option `constructor` set to 'linear' (or 'linear_diagnose'), symblic.kernel.run.Run creates
    one Bridge per run folder. For each ask whose anchored checks fall in the linear fragment, Bridge.attempt
    asks symblic.linear.constructor for candidate answers; every candidate is decoded exactly (decode), checked
    again by the Run's own contract, selected by a fixed policy (canonical minimum) and only then adopted, with
    origin 'solver_proposal' in the claim records. 'linear_diagnose' records what the solver would have proposed
    but still asks the model.

    Every attempt is journaled before anything is dispatched (symblic.constructor.journal) and the run's
    configuration is pinned on first use (symblic.constructor.records): the mode, the limits, the solver runtime
    record and the SHA-256 of the six implementation files (IMPLEMENTATION). A resumed or replayed run reuses
    recorded outcomes exactly; an attempt with an intent but no outcome is 'uncertain' and blocks the run until
    someone reconciles it (symblic.constructor.inspect explains what to do). Errors are SymblicError with kind
    'constructor', 'budget', 'version' or 'uncertain'.

    The runtime record is read only from ~/.local/share/symblic/linear/runtime.json (HOST_RUNTIME), never from a
    program or client option; tools/scripts/symblic_linear_provision.py writes it.

Depends on: symblic.kernel (language, evidence, execution_pins), symblic.constructor (journal, records) and
symblic.linear.constructor. Used by: symblic.kernel.run when a run enables the constructor; tools/symblic run
--constructor linear|linear_diagnose. Status: prototype; tested with a fake solver worker (tests/constructor).
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction
from functools import wraps
import hashlib
import os
from pathlib import Path
import re
import stat
import time

from symblic.kernel import language as S
from symblic.kernel import evidence as E
from symblic.constructor import journal as J
from symblic.constructor import records as R
from symblic.linear import constructor as L

VERSION = 1
KIND = 'smt_linear'
SELECTION = 'canonical_min_v1'
HOST_RUNTIME = Path.home() / '.local/share/symblic/linear/runtime.json'
# The six source files a constructor configuration pins (registry paths, see symblic.kernel.execution_pins).
IMPLEMENTATION = tuple(sorted(R.IMPLEMENTATION_FILES))
_Q = re.compile(r'-?(?:0|[1-9][0-9]*)/[1-9][0-9]*\Z')


def _refuse(code, message):
    raise S.SymblicError('Constructor: ' + message, kind=code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return _sha(J.canonical(value).encode('ascii'))


def _typed_errors(operation):
    @wraps(operation)
    def call(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except (J.JournalError, R.RecordsError) as exc:
            kind = ('budget' if exc.code in ('budget', 'journal_full') else
                    'version' if exc.code in ('drift', 'pins', 'configuration', 'configuration_drift')
                    else 'uncertain')
            # Reports serialize the message, not Python's exception notes. Retain
            # cleanup warnings there as well as on the originating typed error.
            message = '\n'.join((str(exc), *getattr(exc, '__notes__', ())))
            raise S.SymblicError('Constructor: ' + message, kind=kind) from exc
    return call


def _implementation():
    """Bind disk, imported Python and the worker to the initial kernel snapshot."""
    from symblic.kernel import execution_pins as X
    X._check_loaded_runtime()
    hashes = {}
    for name in IMPLEMENTATION:
        raw = X._read(name)
        digest = _sha(raw)
        if X._RUNTIME.get(name) != digest:
            _refuse('version', 'constructor implementation changed since kernel import: ' + name)
        if name in X.PYTHON_FILES and (name in X._RUNTIME_PROBLEMS or not X._bytecode_matches(name, raw)):
            _refuse('version', 'constructor bytecode differs from its imported source: ' + name)
        hashes[name] = digest
    return hashes


def _runtime():
    """Fixed host provisioning only; replay never calls this reader."""
    try:
        fd = os.open(HOST_RUNTIME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            _refuse('version', 'host runtime file must be an owner-controlled regular file')
        raw = stream.read(65537)
    if len(raw) > 65536:
        _refuse('version', 'host runtime file exceeds its bound')
    # Helper's strict decoder refuses duplicate fields/non-finite values.
    return L._strict_json(raw)


def decode(value, ty):
    """Decode only this constructor's scalar/flat-record canonical values."""
    kind = ty.get('k')
    if kind == 'record':
        fields = dict(ty['fields'])
        encoded = {name: ('#' + name if name.startswith('#') else name) for name in fields}
        if type(value) is not dict or set(value) != set(encoded.values()):
            _refuse('constructor', 'record candidate does not match its native type')
        result = {name: decode(value[encoded[name]], field) for name, field in fields.items()}
    elif type(value) in (bool, int):
        result = value
    elif type(value) is dict and set(value) == {'#q'} and type(value['#q']) is str \
            and len(value['#q']) <= 1024 and _Q.fullmatch(value['#q']):
        result = Fraction(value['#q'])
    else:
        _refuse('constructor', 'candidate is outside the exact scalar fragment')
    result = S.check_value(result, ty)
    if J.canonical(S.canon(result)) != J.canonical(value):
        _refuse('constructor', 'candidate encoding is not canonical for its native type')
    return result


class Bridge:
    @_typed_errors
    def __init__(self, run, policy):
        self.run, self.policy = run, policy
        self.replay = bool(run.opts.get('replay'))
        if not run.store.dir:
            _refuse('constructor', 'enabled construction requires a durable run folder')
        self.folder = run.store.dir
        implementation = _implementation()
        old = R.read_config(self.folder)
        if self.replay:
            if old is None:
                _refuse('uncertain', 'replay is missing its constructor configuration')
            config = old
        else:
            config = {'version': VERSION, 'mode': policy['mode'], 'selection_policy': SELECTION,
                      'limits': dict(policy['limits']), 'runtime': _runtime(),
                      'implementation': implementation}
        self.config = R.validate_config(config)
        if config['mode'] != policy['mode'] or config['limits'] != policy['limits'] \
                or config['implementation'] != implementation:
            _refuse('version', 'constructor configuration or implementation changed')
        if old is not None and R.config_hash(old) != R.config_hash(config):
            _refuse('version', 'run was opened with another constructor configuration')
        limits = config['limits']
        self.pins = {'source_sha256': run.source_sha256, 'input_sha256': E.digest(run.inputs),
                     'kernel_id': run._kernel_identity()['id'], 'kind': KIND, 'mode': policy['mode'],
                     'selection_policy': SELECTION, 'implementation_sha256': _hash(config['implementation']),
                     'worker_sha256': config['implementation'][R.WORKER_FILE],
                     'configuration_sha256': R.config_hash(config),
                     'allowance': {'attempts': limits['attempts'], 'milliseconds': limits['milliseconds']}}
        self.journal = J.Journal(self.folder, self.pins, replay=self.replay)
        self.guard()

    def guard(self):
        """Run-wide uncertainty blocks fallback and effects, even before an ask."""
        if _implementation() != self.config['implementation']:
            _refuse('version', 'constructor implementation no longer matches this run')
        summary = J.summary(self.folder)
        if summary['problem'] or summary['uncertain'] or summary['blocked']:
            _refuse('uncertain', 'constructor journal requires explicit recovery before any work')
        if summary['present']:
            # Read the strict stream to check open pins even when no future ask
            # would revisit the old slot. A changed source cannot skip the gate.
            state = R.validate_journal(R.read_journal(self.folder))
            R.bind_journal(state, self.config, source_sha256=self.pins['source_sha256'],
                           input_sha256=self.pins['input_sha256'], kernel_id=self.pins['kernel_id'])

    def _request(self, ask, ty, plan, env, occurrence):
        names = set(S.free_names([ask.parts, plan])) - {ask.name}
        if plan:
            names -= {row.name for row in plan['between'] if row.k == 'let'}
        constants, dependencies = {}, []
        for name in sorted(names):
            binding = env.lookup(name)
            if binding is None:
                continue
            value = binding.value
            if type(value) in (bool, int, Fraction):
                constants[name] = value
            claim = self.run._claim_for_binding(binding)['claim']
            dependencies.append(self.run._epistemic_ref(claim))
        limits = self.policy['limits']
        request = {'occurrence': 'ask:' + E.digest([ask.line, ask.col, ask.name, occurrence])[:48],
                   'item': None,
                   'contract_sha256': E.digest([E.syntax(ask), E.syntax(ty), E.syntax(plan),
                                               E.syntax(self.run.defaults)]),
                   'constants_sha256': E.digest(S.canon(constants)),
                   'dependencies_sha256': E.digest(dependencies),
                   'limits': {'milliseconds': limits['attempt_ms'],
                              'resource_limit': limits['resource_limit'],
                              'address_space_bytes': L.DEFAULT_ADDRESS_SPACE_BYTES}}
        return request, constants

    def _validate(self, ask, ty, plan, env, candidates, request, check_stop):
        if not plan or not self.run._speculable(plan):
            _refuse('constructor', 'recorded candidate lacks an admitted original contract')
        values = []
        for canonical in candidates:
            check_stop()
            value = decode(canonical, ty)
            ok, _message = self.run._candidate(ask, env, value, plan)
            if not ok:
                _refuse('constructor', 'candidate failed the original native predicates')
            check_stop()
            values.append(value)
        if not 1 <= len(values) <= 2 or len({J.canonical(S.canon(v)) for v in values}) != len(values):
            _refuse('constructor', 'candidate set is empty, repeated or exceeds its bound')
        validation = {'version': VERSION, 'kernel_id': self.pins['kernel_id'],
                      'contract_sha256': request['contract_sha256'],
                      'dependencies_sha256': request['dependencies_sha256'],
                      'schema_sha256': E.digest(E.syntax(ty)),
                      'predicate_sha256s': [E.digest(E.syntax(e.cond)) for e in plan['ensures']],
                      'candidate_sha256s': [E.digest(S.canon(value)) for value in values], 'passed': True}
        return values, validation

    def _selected(self, row, request, validation, *, replayed):
        outcome = row['outcome']
        if row['key'] != J.attempt_key(self.pins, request) or outcome['disposition'] != 'accepted' \
                or J.canonical(outcome['evidence']['native_validation']) != J.canonical(validation):
            _refuse('version', 'recorded construction/native-validation relationship changed')
        index = row['selected']
        value = outcome['candidates'][index]
        content = {'version': VERSION, 'kind': KIND, 'mode': self.policy['mode'],
                   'selection_policy': SELECTION, 'journal_version': J.VERSION,
                   'attempt': row['attempt'], 'attempt_key': row['key'], 'outcome_sha256': row['sha256'],
                   'implementation_sha256': self.pins['implementation_sha256'],
                   'worker_sha256': self.pins['worker_sha256'],
                   'configuration_sha256': self.pins['configuration_sha256'],
                   'request_sha256': outcome['evidence']['lifecycle']['request_sha256'],
                   'contract_sha256': request['contract_sha256'],
                   'selected_index': index, 'selected_sha256': row['selected_sha256'],
                   'native_validation_sha256': E.digest(validation), 'kernel_id': self.pins['kernel_id']}
        return {'canonical': value, 'content': content, 'validation': validation,
                'receipt': {'version': VERSION, 'kind': KIND, 'disposition': 'accepted',
                            'attempt': row['attempt'], 'outcome_sha256': row['sha256'],
                            'witnesses': len(outcome['candidates']), 'exhaustive': False,
                            'determination': outcome['determination'], 'replayed': replayed}}

    @_typed_errors
    def attempt(self, ask, ty, env, occurrence, rec):
        """One admitted sequential ask; no mutation of its parent environment."""
        started = time.monotonic()
        self.run.check_stop()
        self.guard()
        plan = self.run._contract(ask)
        request, constants = self._request(ask, ty, plan, env, occurrence)
        decision = self.journal.lookup(request)
        if decision['unresolved']:
            _refuse('uncertain', 'another constructor attempt is unresolved')
        if decision['kind'] in ('missing', 'stopped', 'abandoned'):
            _refuse('uncertain', 'constructor continuation requires explicit recovery')
        if decision['kind'] == 'accepted':
            row = decision['record']
            R.validate_worker_evidence(row['outcome'], request, self.config)
            _values, validation = self._validate(ask, ty, plan, env, row['outcome']['candidates'],
                                                 request, self.run.check_stop)
            return self._selected(row, request, validation, replayed=True)
        if decision['kind'] == 'recorded':
            rec['_constructor'] = {'version': VERSION, 'kind': KIND,
                                   'disposition': decision['disposition'], 'replayed': True,
                                   'attempt': decision['attempt'],
                                   'outcome_sha256': decision['record']['sha256']}
            return None
        # Validate the original native seam without erasing defaults/options.
        unsupported = None
        try:
            L._prepare_seam(ask, ty, plan, constants, set(env.all()), self.run.defaults)
        except L.Unsupported as exc:
            unsupported = exc.code
        R.save_config(self.folder, self.config)
        self.run._constructor_checkpoint()
        attempt = self.journal.begin(request, started=started, check_stop=self.run.check_stop)
        lifecycle, validation = {}, None
        before = self.run.kernel.budget.left

        def check():
            self.run.check_stop()
            if attempt.remaining() <= 0:
                raise TimeoutError('constructor attempt deadline')

        try:
            if unsupported:
                report = {'status': 'unsupported', 'reason': unsupported, 'witnesses': []}
                lifecycle = {'dispatched': False, 'reaped': None}
            else:
                check()
                # The helper validates hypothetical bindings in its own Env.
                # Those copies must not become premise roots in the outer ask.
                # Real dependencies are captured by _request and the final native
                # _candidate checks outside this isolated speculative read frame.
                with S.capture_binding_reads(None, scope=True):
                    report = L.assess_ask(ask, ty, plan, constants, bound=set(env.all()), defaults=self.run.defaults,
                        enabled=True, runtime=self.config['runtime'], deadline_seconds=attempt.remaining(),
                        resource_limit=request['limits']['resource_limit'],
                        address_space_bytes=request['limits']['address_space_bytes'], combined_memory=True,
                        check_stop=check, lifecycle=lifecycle)
            if lifecycle.get('dispatched') is None or (lifecycle.get('dispatched') and not lifecycle.get('reaped')):
                _refuse('uncertain', 'worker launch or reaping is unconfirmed')
            candidates = [w['canonical'] for w in report.get('witnesses', [])]
            if candidates:
                _values, validation = self._validate(ask, ty, plan, env, candidates, request, check)
            self.run.check_stop()
            disposition = ('accepted' if self.policy['mode'] == 'linear' else 'diagnosed') if candidates \
                else 'no_candidate' if report['status'] == 'unsat' else report['status']
            outcome = self._outcome(disposition, report, candidates, lifecycle, validation, started,
                                    before - self.run.kernel.budget.left)
            R.validate_worker_evidence(outcome, request, self.config)
            completed = self.journal.complete(attempt, outcome)
        except BaseException as exc:
            # Preserve the original control-flow cause even if terminal logging
            # also fails. Unknown launch stays an unresolved intent. A confirmed
            # un-reaped child records a block; only terminal ownership can log
            # stop/timeout/refusal without inventing reaping evidence.
            dispatched = lifecycle.get('dispatched', False)
            reaped = lifecycle.get('reaped')
            disposition = ('cleanup_failed' if dispatched is True and reaped is False else
                           'stopped' if self.run.stop.is_set() or not isinstance(exc, Exception) else
                           'timeout' if isinstance(exc, TimeoutError) else 'unknown')
            if dispatched is not None:
                terminal = {'status': disposition, 'reason': 'host_interrupted'}
                lifecycle.setdefault('dispatched', False)
                lifecycle.setdefault('reaped', None)
                outcome = self._outcome(disposition, terminal, [], lifecycle, None, started,
                                        before - self.run.kernel.budget.left)
                if disposition in ('stopped', 'cleanup_failed'):
                    outcome.update(status=None, determination=None)
                try:
                    self.journal.complete(attempt, outcome)
                except BaseException as logging_error:
                    exc.add_note('Constructor intent remains unresolved if terminal recording failed: '
                                 + type(logging_error).__name__)
            raise
        row = completed['record']
        rec['_constructor'] = {'version': VERSION, 'kind': KIND, 'disposition': disposition,
                               'attempt': row['attempt'], 'outcome_sha256': row['sha256'], 'replayed': False}
        if not completed['adoptable']:
            return None
        return self._selected(row, request, validation, replayed=False)

    @staticmethod
    def _outcome(disposition, report, candidates, lifecycle, validation, started, steps):
        solver = report.get('solver') or {}
        status = report['status']
        return {'disposition': disposition, 'dispatched': lifecycle['dispatched'],
                'reaped': lifecycle['reaped'], 'status': status, 'reason': report.get('reason'),
                'determination': 'underdetermined' if len(candidates) == 2 else 'unassessed',
                'candidates': candidates, 'raw_sha256': lifecycle.get('raw_sha256'),
                'effective_limits': solver.get('limits'),
                'costs': {'elapsed_ms': max(0, int((time.monotonic() - started) * 1000)),
                          'solver_rlimit': solver.get('resource_used'), 'validation_steps': max(0, steps)},
                'evidence': {'lifecycle': lifecycle, 'native_validation': validation,
                             'solver_claims_independently_proved': False}}

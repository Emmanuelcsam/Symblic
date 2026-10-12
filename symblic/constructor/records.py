"""Constructor records: the pinned configuration of a constructor run and the checks that bind a journal to it.

What it is for
    constructor-config.json pins, once per run folder: the mode, the selection policy, the limits
    (DEFAULT_LIMITS), the solver runtime record (or None) and the SHA-256 of the six implementation files
    (IMPLEMENTATION_FILES; the worker file must match the runtime record's worker_sha256). This module validates
    and saves that file (validate_config, save_config, read_config), reads and validates the journal stream
    (read_journal, validate_journal), binds a journal to a run's source, inputs, kernel and configuration
    (bind_journal), checks a worker's recorded evidence against the request it answered
    (validate_worker_evidence) and checks that a 'solver_proposal' claim really is backed by an accepted
    journal outcome (validate_solver_claim).

What it is not
    Validation never resolves an executable or reads a solver package. The file helpers touch only the named
    run-folder records. Hashes bind exact bytes; they do not authenticate a solver or authorize running it.

Depends on: the standard library, symblic.constructor.journal and (lazily) symblic.kernel.epistemic. Used by:
symblic.constructor.core and .inspect, symblic.kernel.lockfile and the original host's notebook import
(integration/host/symblic_memory_api.py). Status: prototype with unit tests (tests/constructor).
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import fcntl
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import tempfile
import time

from symblic.constructor import journal as J

VERSION = 1
CONFIG_FILE = 'constructor-config.json'
MAX_CONFIG_BYTES = 65536
# Fixed protocol-3 capture/request caps; recorded settings, never worker execution authority.
WORKER_REQUEST_BYTES = 65536
WORKER_OUTPUT_BYTES = 65536  # aggregate stdout + stderr
WORKER_LIFECYCLE_FIELDS = frozenset({'version', 'dispatched', 'reaped', 'request_sha256', 'request_bytes',
    'requested_milliseconds', 'requested_resource_limit', 'requested_address_space_bytes',
    'raw_sha256', 'raw_bytes', 'capture_complete', 'stdout_observed_bytes', 'stderr_observed_bytes', 'returncode'})
# The source files a constructor configuration pins, as registry paths relative to the folder that holds the
# symblic package (the names symblic.kernel.execution_pins uses). WORKER_FILE is the solver worker the runtime
# record names.
WORKER_FILE = 'symblic/linear/worker.py'
IMPLEMENTATION_FILES = frozenset({'symblic/constructor/core.py', 'symblic/constructor/journal.py',
    'symblic/constructor/records.py', 'symblic/linear/constructor.py', WORKER_FILE,
    'symblic/linear/resources.py'})
RUNTIME_KEYS = frozenset({'python', 'python_sha256', 'worker_sha256', 'z3_version', 'package', 'purelib'})
DEFAULT_LIMITS = {'attempts': 16, 'milliseconds': 80000, 'attempt_ms': 5000, 'resource_limit': 100000}
LIMIT_CEILINGS = {'attempts': 64, 'milliseconds': 320000, 'attempt_ms': 5000, 'resource_limit': 1000000}
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_VERSION = re.compile(r'[0-9]+(?:\.[0-9]+){1,3}\Z')


class RecordsError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def _fail(code, message):
    raise RecordsError(code, message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _cleanup(action, primary, label):
    """Cleanup cannot replace an original stop, interrupt or other failure."""
    try:
        action()
    except BaseException as cleanup:
        if primary is None:
            if isinstance(cleanup, OSError):
                raise RecordsError('cleanup', label + ' failed') from cleanup
            raise
        try:
            primary.add_note(label + ' also failed: ' + type(cleanup).__name__)
        except BaseException:
            pass  # Annotation is best-effort; the original exception always wins.


def _hex(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _canonical(value):
    try:
        return J.canonical(value)
    except J.JournalError as exc:
        raise RecordsError('configuration', str(exc)) from None


def _absolute(value):
    return type(value) is str and 1 <= len(value) <= 4096 and '\0' not in value \
        and PurePosixPath(value).is_absolute()


def _runtime(runtime, implementation):
    if runtime is None:
        return
    if type(runtime) is not dict or set(runtime) != RUNTIME_KEYS:
        _fail('configuration', 'Runtime has exactly the pinned linear helper runtime fields')
    if not _absolute(runtime['python']) or not _absolute(runtime['purelib']):
        _fail('configuration', 'Runtime paths must be bounded absolute texts')
    if not _hex(runtime['python_sha256']) or not _hex(runtime['worker_sha256']) \
            or runtime['worker_sha256'] != implementation[WORKER_FILE]:
        _fail('configuration', 'Runtime worker and implementation pins differ or are invalid')
    if type(runtime['z3_version']) is not str or len(runtime['z3_version']) > 64 \
            or not _VERSION.fullmatch(runtime['z3_version']):
        _fail('configuration', 'Runtime Z3 version must be a bounded dotted numeric version')
    package = runtime['package']
    if type(package) is not dict or not 1 <= len(package) <= 256:
        _fail('configuration', 'Runtime package requires 1..256 exact file pins')
    for name, digest in package.items():
        if type(name) is not str or not 1 <= len(name) <= 4096 or '\0' in name:
            _fail('configuration', 'Invalid runtime package path')
        path = PurePosixPath(name)
        if path.is_absolute() or not path.parts or '..' in path.parts or str(path) != name \
                or path.parts[0] not in ('z3', 'z3_solver-4.15.4.0.dist-info') or not _hex(digest):
            _fail('configuration', 'Invalid relative runtime package path or hash')


def validate_config(config):
    """Return a detached validated config; no solver/runtime filesystem reads."""
    text = _canonical(config)  # Charge exact bytes/nodes/depth before copying or inspecting wide inputs.
    if len(text) > MAX_CONFIG_BYTES:
        _fail('configuration', 'Constructor configuration exceeds 64 KiB')
    if type(config) is not dict or set(config) != {'version', 'mode', 'selection_policy', 'limits', 'runtime', 'implementation'}:
        _fail('configuration', 'Constructor configuration has invalid fields')
    if type(config['version']) is not int or config['version'] != VERSION:
        _fail('configuration', 'Unsupported constructor configuration version')
    if type(config['mode']) is not str or config['mode'] not in ('linear', 'linear_diagnose') \
            or config['selection_policy'] != 'canonical_min_v1':
        _fail('configuration', 'Unsupported constructor mode or selection policy')
    limits = config['limits']
    if type(limits) is not dict or set(limits) != set(LIMIT_CEILINGS) \
            or any(type(limits[key]) is not int or not 1 <= limits[key] <= cap
                   for key, cap in LIMIT_CEILINGS.items()) \
            or limits['milliseconds'] < limits['attempt_ms']:
        _fail('configuration', 'Constructor limits must be exact bounded positive integers with room for one attempt')
    implementation = config['implementation']
    if type(implementation) is not dict or set(implementation) != IMPLEMENTATION_FILES \
            or any(not _hex(value) for value in implementation.values()):
        _fail('configuration', 'Constructor implementation requires the six exact module filename/hash pins')
    _runtime(config['runtime'], implementation)
    return copy.deepcopy(config)


def config_hash(config):
    return _sha(J.canonical(validate_config(config)).encode('ascii'))


def implementation_hash(config):
    return _sha(J.canonical(validate_config(config)['implementation']).encode('ascii'))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('configuration', 'Duplicate configuration JSON key')
        result[key] = value
    return result


def _number(_value):
    _fail('configuration', 'Configuration JSON must contain exact finite integers, not floats')


def parse_config(raw):
    """Validate exact canonical ASCII file text without opening any path."""
    if type(raw) is not str or len(raw) > MAX_CONFIG_BYTES:
        _fail('configuration', 'Configuration text exceeds 64 KiB or is not text')
    try:
        raw.encode('ascii')
        config = json.loads(raw, object_pairs_hook=_pairs, parse_float=_number, parse_constant=_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, RecordsError):
            raise
        raise RecordsError('configuration', 'Configuration is not bounded exact ASCII JSON') from None
    result = validate_config(config)
    if J.canonical(result) != raw:
        _fail('configuration', 'Configuration file is not canonical ASCII JSON')
    return result


def _regular_bytes(path, limit):
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(before.st_mode):
        _fail('unsafe_file', 'Constructor record must be a regular file, not a symlink or special file')
    fd, primary = None, None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            _fail('unsafe_file', 'Constructor record changed while opening')
        if info.st_size > limit:
            _fail('size', 'Constructor record exceeds its byte bound')
        chunks, count = [], 0
        while count <= limit:
            part = os.read(fd, min(65536, limit + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
        raw = b''.join(chunks)
    except OSError as exc:
        primary = RecordsError('unreadable', 'Constructor record could not be read')
        raise primary from exc
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if fd is not None:
            _cleanup(lambda: os.close(fd), primary, 'Closing constructor record')
    if len(raw) > limit:
        _fail('size', 'Constructor record exceeds its byte bound')
    return raw


def read_config(folder):
    raw = _regular_bytes(os.path.join(folder, CONFIG_FILE), MAX_CONFIG_BYTES)
    if raw is None:
        return None
    try:
        return parse_config(raw.decode('ascii'))
    except UnicodeError:
        _fail('configuration', 'Configuration file must be ASCII JSON')


def _sync_folder(folder):
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    primary = None
    try:
        os.fsync(fd)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _cleanup(lambda: os.close(fd), primary, 'Closing constructor directory')


def _sync_existing(folder, target):
    try:
        fd = J._open_regular(target, os.O_RDONLY)
        primary = None
        try:
            os.fsync(fd)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            _cleanup(lambda: os.close(fd), primary, 'Closing existing constructor configuration')
        _sync_folder(folder)
    except (OSError, J.JournalError) as exc:
        raise RecordsError('durability', 'Existing constructor configuration durability was not confirmed') from exc


def save_config(folder, config):
    """Create once via a synced private temporary file; exact existing config is idempotent."""
    checked = validate_config(config)
    raw = J.canonical(checked).encode('ascii')
    target = os.path.join(folder, CONFIG_FILE)
    previous = read_config(folder)
    if previous is not None:
        if J.canonical(previous).encode('ascii') != raw:
            _fail('configuration_drift', 'Constructor configuration already exists with different exact bytes')
        _sync_existing(folder, target)
        return checked
    temporary, primary = None, None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.constructor-config-', dir=folder)
        write_error = None
        try:
            remaining = memoryview(raw)
            while remaining:
                count = os.write(fd, remaining)
                if count <= 0:
                    raise OSError('constructor configuration write made no progress')
                remaining = remaining[count:]
            os.fsync(fd)
        except BaseException as exc:
            write_error = exc
            raise
        finally:
            _cleanup(lambda: os.close(fd), write_error, 'Closing temporary constructor configuration')
        try:
            os.link(temporary, target, follow_symlinks=False)  # create-only atomic publication
        except FileExistsError:
            previous = read_config(folder)
            if previous is None or J.canonical(previous).encode('ascii') != raw:
                _fail('configuration_drift', 'Constructor configuration changed during creation')
            _sync_existing(folder, target)
        _sync_folder(folder)
        return checked
    except OSError as exc:
        primary = RecordsError('durability', 'Constructor configuration publication was not confirmed durable')
        raise primary from exc
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if temporary is not None:
            def remove():
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            _cleanup(remove, primary, 'Removing temporary constructor configuration')


def validate_journal(raw_text):
    """Strict reader for an existing stream; return J._State, never skip a row."""
    if type(raw_text) is not str or not raw_text or len(raw_text) > J.MAX_JOURNAL_BYTES:
        _fail('journal', 'Journal must be nonempty bounded exact ASCII text')
    try:
        raw = raw_text.encode('ascii')
        state = J._validate(raw)
    except (UnicodeError, J.JournalError, ValueError, RecursionError) as exc:
        raise RecordsError('journal', 'Constructor journal is invalid: ' + str(exc)[:256]) from None
    if state.pins is None:
        _fail('journal', 'Constructor journal has no pinned opening record')
    if J._unresolved(state):
        _fail('unresolved', 'Constructor journal has unknown or unreaped attempts')
    return state


def read_journal(folder):
    """Read a consistent exact journal snapshot; return None only when absent."""
    fd, primary = None, None
    try:
        fd = J._open_lock(folder, False)
        if fd is not None and not J._flock(fd, fcntl.LOCK_SH, time.monotonic() + J.LOCK_WAIT_SECONDS):
            _fail('busy', 'Constructor journal is being written')
        raw = _regular_bytes(os.path.join(folder, J.FILE), J.MAX_JOURNAL_BYTES)
        if raw is None:
            return None
        try:
            text = raw.decode('ascii')
        except UnicodeError:
            _fail('journal', 'Constructor journal must be ASCII JSONL')
        validate_journal(text)
        return text
    except J.JournalError as exc:
        primary = RecordsError('journal', str(exc))
        raise primary from None
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if fd is not None:
            _cleanup(lambda: os.close(fd), primary, 'Closing constructor journal lock')


def validate_worker_evidence(outcome, request, config=None):
    """Validate recorded full-reply relationships without executing or importing a worker.

    True means the accepted/diagnosed/no_candidate receipt binds its request,
    complete capture and protocol-3 resource settings. Other structurally valid
    dispositions return False: an interruption may retain only partial evidence.
    This does not validate the candidate, prove UNSAT, attest host truth, or make
    configured Z3 work allocations a measured global hard cap.
    """
    _canonical(request)
    _canonical(outcome)
    checked = validate_config(config) if config is not None else None
    mode = checked['mode'] if checked is not None else \
        'linear_diagnose' if type(outcome) is dict and outcome.get('disposition') == 'diagnosed' else 'linear'
    problem = J._request_problem(request) or J._outcome_problem(mode, outcome)
    if problem:
        _fail('worker_evidence', 'Invalid constructor request/outcome: ' + problem)
    if outcome['disposition'] not in ('accepted', 'diagnosed', 'no_candidate'):
        return False
    evidence = outcome['evidence']
    lifecycle = evidence.get('lifecycle') if type(evidence) is dict else None
    if type(lifecycle) is not dict or set(lifecycle) != WORKER_LIFECYCLE_FIELDS:
        _fail('worker_evidence', 'Worker reply requires the exact protocol-3 lifecycle fields')
    fixed = request['limits']
    requested_ms = lifecycle.get('requested_milliseconds')
    if type(lifecycle.get('version')) is not int or lifecycle['version'] != 1 \
            or lifecycle.get('dispatched') is not True or lifecycle.get('reaped') is not True \
            or lifecycle.get('capture_complete') is not True or type(lifecycle.get('returncode')) is not int \
            or lifecycle['returncode'] != 0 or not _hex(lifecycle.get('request_sha256')) \
            or not _hex(lifecycle.get('raw_sha256')) or lifecycle['raw_sha256'] != outcome['raw_sha256'] \
            or type(requested_ms) is not int or not 1 <= requested_ms <= fixed['milliseconds'] \
            or fixed['address_space_bytes'] != 256 * 1024 * 1024 \
            or type(lifecycle.get('requested_resource_limit')) is not int \
            or lifecycle['requested_resource_limit'] != fixed['resource_limit'] \
            or type(lifecycle.get('requested_address_space_bytes')) is not int \
            or lifecycle['requested_address_space_bytes'] != fixed['address_space_bytes']:
        _fail('worker_evidence', 'Worker lifecycle does not confirm exact request limits, capture and terminal outcome')
    counts = {'request_bytes': (1, WORKER_REQUEST_BYTES), 'raw_bytes': (1, WORKER_OUTPUT_BYTES),
              'stdout_observed_bytes': (1, WORKER_OUTPUT_BYTES), 'stderr_observed_bytes': (0, WORKER_OUTPUT_BYTES)}
    if any(type(lifecycle[key]) is not int or not low <= lifecycle[key] <= high
           for key, (low, high) in counts.items()) \
            or lifecycle['raw_bytes'] != lifecycle['stdout_observed_bytes'] \
            or lifecycle['stdout_observed_bytes'] + lifecycle['stderr_observed_bytes'] > WORKER_OUTPUT_BYTES:
        _fail('worker_evidence', 'Full worker capture byte counts are invalid, incomplete or exceed the aggregate bound')
    limits = outcome['effective_limits']
    if type(limits) is not dict or set(limits) != {'requested', 'effective_os', 'z3_applied',
                                                'private_import_root', 'loaded_library'}:
        _fail('worker_evidence', 'Worker reply lacks complete protocol-3 resource settings')
    root = limits['private_import_root']
    if not _absolute(root):
        _fail('worker_evidence', 'Worker private import root is not a bounded absolute path')
    if checked is not None:
        if checked['runtime'] is None or root != checked['runtime']['purelib'] \
                or fixed['milliseconds'] > checked['limits']['attempt_ms'] \
                or fixed['resource_limit'] > checked['limits']['resource_limit']:
            _fail('worker_evidence', 'Worker reply differs from its pinned runtime or configuration limits')
    first_work = fixed['resource_limit'] // 2 or 1
    cpu = (requested_ms + 999) // 1000 + 1
    expected = {
        'requested': {'milliseconds': requested_ms, 'rlimit_total': fixed['resource_limit'],
                      'address_space_bytes': fixed['address_space_bytes']},
        'effective_os': {'address_space_bytes': [fixed['address_space_bytes']] * 2,
                         'cpu_seconds': [cpu, cpu], 'file_bytes': [0, 0],
                         'core_bytes': [0, 0], 'open_files': [64, 64]},
        'z3_applied': {'threads': 1, 'random_seed': 0,
                      'allocated_check_rlimits': [first_work, fixed['resource_limit'] - first_work]},
        'private_import_root': root, 'loaded_library': str(PurePosixPath(root) / 'z3/lib/libz3.so')}
    # Canonical exact JSON distinguishes bool/int aliases throughout these bounded records.
    if J.canonical(limits) != J.canonical(expected):
        _fail('worker_evidence', 'Recorded OS limits, Z3 allocations or library path differ from the exact request')
    return True


def bind_journal(state, config, *, source_sha256, input_sha256, kernel_id):
    """Verify source/input/kernel/configuration/implementation pins and declared attempt limits."""
    config = validate_config(config)
    expected = {'source_sha256': source_sha256, 'input_sha256': input_sha256, 'kernel_id': kernel_id,
                'kind': 'smt_linear', 'mode': config['mode'], 'selection_policy': config['selection_policy'],
                'implementation_sha256': implementation_hash(config),
                'worker_sha256': config['implementation'][WORKER_FILE],
                'configuration_sha256': config_hash(config),
                'allowance': {key: config['limits'][key] for key in ('attempts', 'milliseconds')}}
    if J.canonical(state.pins) != J.canonical(expected):
        _fail('pins', 'Constructor journal source, inputs, kernel or configuration pins differ')
    for entry in state.attempts.values():
        limits = entry['intent']['request']['limits']
        if limits['milliseconds'] > config['limits']['attempt_ms'] \
                or limits['resource_limit'] > config['limits']['resource_limit'] \
                or type(limits['address_space_bytes']) is not int or limits['address_space_bytes'] != 256 * 1024 * 1024:
            _fail('pins', 'Recorded constructor attempt exceeds its configuration limits')
        if entry['outcome'] is not None:
            validate_worker_evidence(entry['outcome']['outcome'], entry['intent']['request'], config)
    return state


def validate_solver_claim(claim, state):
    """Bind one host solver claim to an accepted immutable outcome and its recorded native checks.

    Call with a state returned by validate_journal and bound through bind_journal.
    This checks records, not solver execution or arbitrary semantic entailment.
    """
    from symblic.kernel import epistemic as EP
    try:
        claim = EP.validate_claim(claim)
    except EP.EpistemicError as exc:
        raise RecordsError('epistemic', str(exc)) from None
    content = claim['content']
    if claim['origin'] != 'solver_proposal' or type(content) is not dict \
            or type(content.get('constructor')) is not dict:
        _fail('epistemic', 'Expected a solver proposal with its host constructor identity')
    meta = content['constructor']
    attempt = meta.get('attempt')
    entry = state.attempts.get(attempt) if type(attempt) is int else None
    if entry is None or entry['outcome'] is None:
        _fail('epistemic', 'Solver claim names no recorded outcome')
    row, request = entry['outcome'], entry['intent']['request']
    out = row['outcome']
    if out['disposition'] != 'accepted' or type(row['selected']) is not int:
        _fail('epistemic', 'Only an accepted selected outcome can source a solver proposal')
    evidence = out['evidence']
    if type(evidence) is not dict or type(evidence.get('native_validation')) is not dict \
            or type(evidence.get('lifecycle')) is not dict:
        _fail('epistemic', 'Solver outcome lacks the recorded native validation/lifecycle relationship')
    native = evidence['native_validation']
    validate_worker_evidence(out, request)
    fields = {'version', 'kernel_id', 'contract_sha256', 'dependencies_sha256', 'schema_sha256',
              'predicate_sha256s', 'candidate_sha256s', 'passed'}
    hashes = native.get('predicate_sha256s')
    if set(native) != fields or type(native['version']) is not int or native['version'] != 1 \
            or native['passed'] is not True or not _hex(native['schema_sha256']) \
            or type(hashes) is not list or len(hashes) > 64 or any(not _hex(v) for v in hashes) \
            or native['kernel_id'] != state.pins['kernel_id'] \
            or native['contract_sha256'] != request['contract_sha256'] \
            or native['dependencies_sha256'] != request['dependencies_sha256'] \
            or native['candidate_sha256s'] != [EP.digest(value) for value in out['candidates']]:
        _fail('epistemic', 'Recorded native validation does not bind the exact request/candidates')
    request_sha = evidence['lifecycle'].get('request_sha256')
    if not _hex(request_sha):
        _fail('epistemic', 'Recorded lifecycle has no exact worker request identity')
    expected = {'version': 1, 'kind': state.pins['kind'], 'mode': state.pins['mode'],
                'selection_policy': state.pins['selection_policy'], 'journal_version': row['v'],
                'attempt': row['attempt'], 'attempt_key': row['key'], 'outcome_sha256': row['sha256'],
                'implementation_sha256': state.pins['implementation_sha256'],
                'worker_sha256': state.pins['worker_sha256'],
                'configuration_sha256': state.pins['configuration_sha256'],
                'request_sha256': request_sha, 'contract_sha256': request['contract_sha256'],
                'selected_index': row['selected'], 'selected_sha256': row['selected_sha256'],
                'native_validation_sha256': EP.digest(native), 'kernel_id': state.pins['kernel_id']}
    if J.canonical(meta) != J.canonical(expected):
        _fail('epistemic', 'Solver constructor identity differs from the selected journal outcome')
    value_sha = EP.digest(out['candidates'][row['selected']])
    if content.get('value_sha256') != value_sha or content.get('source_sha256') != state.pins['source_sha256']:
        _fail('epistemic', 'Solver value/source identity differs from the journal')
    expected_predicates = [{'kernel': native['kernel_id'], 'source_sha256': state.pins['source_sha256'],
                           'contract_sha256': native['contract_sha256'], 'predicate_sha256': h} for h in hashes]
    actual_predicates = []
    schema = []
    for check in claim['checks']:
        if check['passed'] is not True or check['inputs'] != claim['dependencies']:
            _fail('epistemic', 'Solver check does not attest exactly its declared dependencies')
        if check['scope'] == 'encoded_predicate':
            actual_predicates.append(check['predicate'])
        elif check['scope'] == 'encoded_schema':
            schema.append(check['predicate'])
    if sorted(J.canonical(v) for v in actual_predicates) != sorted(J.canonical(v) for v in expected_predicates) \
            or not _hex(content.get('type_sha256')) or schema != [{'type_sha256': content['type_sha256']}]:
        _fail('epistemic', 'Solver claim checks differ from the recorded native validation')
    return claim

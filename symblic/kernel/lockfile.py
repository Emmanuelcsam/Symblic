"""Lockfiles: a finished run frozen into one portable file that replays with no model at all.

    python3 -m symblic.kernel.lockfile lock RUN_FOLDER [--out FILE]   # write FILE (default RUN_FOLDER/run.lock.json)
    python3 -m symblic.kernel.lockfile replay LOCK.json               # rerun it from the recorded answers
    python3 -m symblic.kernel.lockfile show LOCK.json

A run folder already replays exactly (calls.jsonl answers every call it made). A lock packages that record so
it can travel with a program or a paper, like a package lockfile:

    lock = make_lock(run_folder)          # {program sha, inputs, options, modules, statements, calls}
    save_lock(lock, 'paper.symd.lock.json')
    rep = replay(lock)                    # the same run with no model at all; fingerprint must match
    d = drift(lock, fresh_report)         # what a new group of agents answered differently

The lock records, per statement that binds or shows something, its line, name, class and fingerprint.
replay() rebuilds a temporary run folder from the lock (calls.jsonl and modules.json) and runs the program with
an applicator that refuses every call, so any call the lock does not hold fails the replay instead of
reaching a model. A lock is valid only for the exact program text (SHA-256), inputs and options it was made
with. Runs written from English instructions carry their authoring record; replaying one of those needs the
English front end's checks (symblic/english/authoring.py).

Depends on: symblic.kernel.language, symblic.kernel.run, symblic.kernel.evidence, symblic.kernel.epistemic,
symblic.constructor.records. Pure except the file helpers; nothing runs on import.
"""

from __future__ import annotations

import hashlib
import copy
import json
import os
import shutil
import sys
import tempfile
import time

from symblic.kernel import language as S

LOCK_VERSION = 2
CONSTRUCTOR_LOCK_VERSION = 3
MAX_PROVENANCE_ROWS = 8192
MAX_PROVENANCE_BYTES = 16 * 1024 * 1024
MAX_LOCK_BYTES = 50_000_000
EFFECT_LEDGERS = frozenset(('delegate-effects.jsonl', 'effects.jsonl'))
EFFECT_CATALOGUE_FILE = 'effects-catalogue.json'


class LockError(Exception):
    pass


def _read_jsonl(path: str) -> list:
    out = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue            # a torn last line
    except OSError:
        pass
    return out


def _load(path: str, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def statements_of(bindings: list, outputs: list) -> list:
    """The run's final top-level results, in order: one row per binding and per output (exactly what the
    run fingerprint hashes; a routine's or a loop's inner bindings are summarised by what they bind)."""
    rows = []
    for b in bindings or []:
        if b.get('hash'):
            meta = b.get('meta') or {}
            rows.append({'key': f'{b.get("line", 0)}:{b["name"]}', 'line': b.get('line', 0), 'name': b['name'],
                         'hash': b['hash'], 'class': b.get('class'), 'value': _short(b.get('value')),
                         'agreement': meta.get('agreement'), 'evidence': meta.get('evidence')})
    for o in outputs or []:
        rows.append({'key': f'{o["line"]}:{o["kind"]}', 'line': o['line'], 'name': o['kind'], 'hash': o['hash'],
                     'class': o.get('class', 'output'), 'value': (o.get('text') or '')[:400],
                     'evidence': o.get('evidence')})
    return rows


def _short(v) -> str:
    text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return text if len(text) <= 400 else text[:399] + '…'


def make_lock(folder: str) -> dict:
    """Freeze a finished run folder. Refuses a run that did not finish."""
    state = _load(os.path.join(folder, 'state.json'), {})
    if state.get('status') != 'done':
        raise LockError(f'only a finished run can be locked (this one is {state.get("status") or "unknown"})')
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as f:
            source = f.read()
    except OSError:
        raise LockError('the run folder has no program.sym') from None
    meta = _load(os.path.join(folder, 'meta.json'), {})
    authoring = None
    if meta.get('authoring') is not None or os.path.lexists(os.path.join(folder, 'instructions.english')):
        try:
            from symblic.english.authoring import validate_saved
            validate_saved(folder, source, meta)
            authoring = copy.deepcopy(meta['authoring'])
        except (ImportError, S.SymblicError, ValueError, KeyError) as exc:
            raise LockError('Cannot preserve saved English instructions: ' + str(exc)
                            + '. Retain the original run folder; repair its records before export.') from None
    kernel = state.get('kernel')
    _kernel_identity(kernel)  # Never relabel an old run with today's kernel.
    if state.get('version') != kernel.get('lang'):
        raise LockError('the run version does not match its recorded kernel')
    modules = _load(os.path.join(folder, 'modules.json'), {})
    _validate_modules(modules)
    effect_ledgers = {}
    for name in sorted(EFFECT_LEDGERS):
        try:
            with open(os.path.join(folder, name), encoding='utf-8', newline='') as f:
                effect_ledgers[name] = f.read()
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError) as exc:
            raise LockError(f'cannot read the effect ledger {name}') from exc
    try:
        with open(os.path.join(folder, EFFECT_CATALOGUE_FILE), encoding='utf-8', newline='') as f:
            effect_catalogue = f.read()
    except FileNotFoundError:
        effect_catalogue = None
    except (OSError, UnicodeError) as exc:
        raise LockError('cannot read the frozen effect catalogue') from exc
    # The final invocation's complete per-key reply sequence preserves rejected
    # transport attempts too. A transient failure can change which reader is
    # tried; replaying only successful answers would take a different route.
    execution = state.get('execution_id')
    calls = [r for r in _read_jsonl(os.path.join(folder, 'call-events.jsonl'))
             if execution and r.get('execution_id') == execution and r.get('key')]
    grouped = {}
    if calls:
        for r in calls:
            row = grouped.setdefault(r['key'], {k: r[k] for k in
                                     ('key', 'app', 'line', 'stmt', 'sample') if k in r})
            row.setdefault('replies', []).append(r['reply'])
            row['reply'] = r['reply']
    else:
        for r in _read_jsonl(os.path.join(folder, 'calls.jsonl')):
            if r.get('key') and isinstance(r.get('reply'), dict):
                grouped[r['key']] = {k: r[k] for k in ('key', 'app', 'line', 'stmt', 'sample', 'reply') if k in r}
    kept = list(grouped.values())
    lock = {'symblic_lock': LOCK_VERSION, 'version': kernel['lang'], 'canon': kernel['canon'], 'kernel': kernel,
            'created': round(time.time(), 3), 'program': state.get('program'),
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'source': source,
            'inputs': meta.get('inputs') or {}, 'options': _portable_options(meta.get('options') or {}),
            'fingerprint': state.get('fingerprint'),
            'modules': modules, 'effect_ledgers': effect_ledgers, 'effect_catalogue': effect_catalogue,
            'evidence': state.get('evidence'),
            'provenance_recorded': 'evidence' in state,
            'checks': [r for r in _read_jsonl(os.path.join(folder, 'trace.jsonl')) if r.get('check') is not None],
            'statements': statements_of(state.get('bindings') or [], state.get('outputs') or []), 'calls': kept}
    if authoring is not None:
        lock['authoring'] = authoring
    constructor = _constructor_export(folder, state, lock)
    if constructor is not None:
        lock['symblic_lock'] = CONSTRUCTOR_LOCK_VERSION
        lock['constructor'] = constructor
    lock['sha256'] = lock_hash(lock)
    return _validate(lock)


def _portable_options(opts: dict) -> dict:
    out = {}
    for key, value in opts.items():
        if key in ('stop', 'on_event', 'event_sink', 'replay', 'effects', 'effects_ledger'):
            continue
        try:
            out[key] = json.loads(json.dumps(value, allow_nan=False))
        except (TypeError, ValueError):
            continue
    return out


def lock_hash(lock: dict) -> str:
    body = {k: v for k, v in lock.items() if k != 'sha256'}
    try:
        data = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LockError('the lock contains non-JSON or nonfinite values') from exc
    return hashlib.sha256(data.encode()).hexdigest()


def _kernel_identity(kernel):
    if (not isinstance(kernel, dict) or not isinstance(kernel.get('id'), str) or not kernel['id']
            or 'lang' not in kernel or 'canon' not in kernel):
        raise LockError('the lock needs the original run kernel identity; this run is not pinned')
    return {k: v for k, v in kernel.items() if k != 'python'}


def _validate_modules(modules):
    if not isinstance(modules, dict):
        raise LockError('the lock module record is invalid')
    for name, row in modules.items():
        if (not isinstance(name, str) or not isinstance(row, dict)
                or not isinstance(row.get('source'), str)
                or hashlib.sha256(row['source'].encode()).hexdigest() != row.get('sha256')):
            raise LockError('the lock module source hash does not match')


def _evidence_identity(value):
    """Compare validation meaning while preserving original execution provenance.

    Receipts hash their original full kernel (including informational Python).
    Replaying under the same semantic kernel may therefore produce a new receipt
    ID. Its predicate, inputs, result and semantic kernel must still match.
    """
    if isinstance(value, list):
        return [_evidence_identity(v) for v in value]
    if not isinstance(value, dict):
        return value
    receipt = 'predicate_sha256' in value and 'id' in value
    acquired = value.get('mechanism') in ('effect', 'observation') and 'effect_id' in value
    if receipt:
        body = {k: v for k, v in value.items() if k != 'id'}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                           separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if value['id'] != digest:
            raise LockError('validation receipt content hash mismatch')
    return {k: (_kernel_identity(v) if k == 'kernel' else _evidence_identity(v))
            for k, v in value.items() if not ((receipt and k == 'id') or (acquired and k == 'replayed'))}


def _binding_provenance(bindings):
    if type(bindings) is not list or len(bindings) > MAX_PROVENANCE_ROWS:
        raise LockError('constructor binding registry exceeds its row bound')
    out = []
    for row in bindings:
        if type(row) is not dict:
            raise LockError('invalid constructor binding record')
        if row.get('hash'):
            meta = row.get('meta') or {}
            if type(meta) is not dict:
                raise LockError('invalid constructor binding metadata')
            out.append({'key': f'{row.get("line", 0)}:{row.get("name")}', 'line': row.get('line', 0),
                        'name': row.get('name'), 'hash': row['hash'], 'epistemic': meta.get('epistemic')})
    return out


def _provenance_validate(epistemic, bindings, journal):
    """Exact bounded registry and selected binding records, including all immutable receipt IDs."""
    from symblic.kernel import epistemic as EP
    from symblic.constructor import records as R
    if type(epistemic) is not dict or set(epistemic) != {'version', 'empirical_truth', 'claims', 'assessments'} \
            or type(epistemic['version']) is not int or epistemic['version'] != EP.VERSION \
            or epistemic['empirical_truth'] != 'not_established':
        raise LockError('constructor lock requires its exact epistemic registry')
    claims, views = epistemic['claims'], epistemic['assessments']
    if type(claims) is not list or type(views) is not list or len(claims) != len(views) \
            or len(claims) > MAX_PROVENANCE_ROWS or type(bindings) is not list or len(bindings) > MAX_PROVENANCE_ROWS:
        raise LockError('constructor provenance exceeds its row bound or has inconsistent assessments')
    remaining = MAX_PROVENANCE_BYTES
    digest = hashlib.sha256()

    def charge(value):
        nonlocal remaining
        raw = EP._json(value).encode('utf-8')
        remaining -= len(raw) + 32  # includes framing/wrapper allowance
        if remaining < 0:
            raise LockError('constructor provenance exceeds its encoded byte bound')
        digest.update(str(len(raw)).encode('ascii') + b':' + raw)
        return raw

    by_id, by_view = {}, {}
    try:
        digest.update(b'claims\0')
        for claim in claims:
            charge(claim)
            row = EP.validate_claim(claim)
            if row['id'] in by_id:
                raise LockError('duplicate constructor provenance claim')
            by_id[row['id']] = row
            if row['origin'] == 'solver_proposal':
                R.validate_solver_claim(row, journal)
        # Complete exact reference closure, with an iterative cycle check independent of registry order.
        incoming = {key: 0 for key in by_id}
        children = {key: [] for key in by_id}
        for row in by_id.values():
            for ref in row['dependencies']:
                parent = by_id.get(ref['id'])
                if parent is None or EP.reference(parent) != ref:
                    raise LockError('constructor provenance has missing or stale dependency closure')
                incoming[row['id']] += 1
                children[ref['id']].append(row['id'])
        ready = [key for key, count in incoming.items() if count == 0]
        visited = 0
        while ready:
            key = ready.pop(); visited += 1
            for child in children[key]:
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
        if visited != len(by_id):
            raise LockError('cyclic constructor provenance')
        digest.update(b'assessments\0')
        for view in views:
            charge(view)
            if type(view) is not dict or type(view.get('id')) is not str or view['id'] in by_view:
                raise LockError('invalid or duplicate constructor assessment')
            claim = by_id.get(view['id'])
            if claim is None or any(type(view.get(k)) is not type(claim[k]) or view.get(k) != claim[k]
                                    for k in ('id', 'revision', 'sha256')):
                raise LockError('constructor assessment does not identify its exact claim')
            by_view[view['id']] = view
        digest.update(b'bindings\0')
        seen = set()
        for row in bindings:
            charge(row)
            if type(row) is not dict or set(row) != {'key', 'line', 'name', 'hash', 'epistemic'} \
                    or type(row['line']) is not int or row['line'] < 0 or type(row['name']) is not str \
                    or not row['name'] or type(row['hash']) is not str or not row['hash'] \
                    or row['key'] != f'{row["line"]}:{row["name"]}' or row['key'] in seen:
                raise LockError('invalid or duplicate selected constructor binding identity')
            seen.add(row['key'])
            info = row['epistemic']
            if info is None:
                continue  # Retain explicitly missing non-constructor metadata, never fabricate it.
            if type(info) is not dict or set(info) != {'claim', 'assessment', 'dependency_scope'} \
                    or info['dependency_scope'] != 'conservative_runtime_reads':
                raise LockError('invalid selected binding epistemic record')
            claim = info['claim']
            if type(claim) is not dict or type(claim.get('id')) is not str \
                    or claim['id'] not in by_id or EP._json(claim) != EP._json(by_id[claim['id']]) \
                    or EP._json(info['assessment']) != EP._json(by_view[claim['id']]):
                raise LockError('selected binding does not match the exact epistemic registry')
            content = claim['content']
            if type(content) is dict and 'value_sha256' in content and row['hash'] != content['value_sha256'][:16]:
                raise LockError('selected binding value hash differs from its epistemic claim')
    except (EP.EpistemicError, R.RecordsError, TypeError, KeyError) as exc:
        raise LockError('invalid constructor provenance: ' + str(exc)[:256]) from None
    return digest.hexdigest()


def _constructor_validate(bundle, lock):
    from symblic.constructor import records as R
    from symblic.kernel import evidence as E
    from symblic.kernel import run as SR
    if type(bundle) is not dict or set(bundle) != {'version', 'configuration', 'configuration_sha256',
            'journal', 'journal_sha256', 'epistemic', 'bindings'} or type(bundle['version']) is not int \
            or bundle['version'] != 1:
        raise LockError('invalid constructor lock bundle')
    try:
        config = R.parse_config(bundle['configuration'])
        journal = R.validate_journal(bundle['journal'])
        if journal.repairs:
            raise LockError('repaired constructor journals require quarantine packaging; export is not supported yet')
        if bundle['configuration_sha256'] != R.config_hash(config) \
                or bundle['journal_sha256'] != hashlib.sha256(bundle['journal'].encode('ascii')).hexdigest():
            raise LockError('constructor journal or configuration bytes changed')
        if type(lock.get('inputs')) is not dict:
            raise LockError('constructor lock inputs must be an object')
        if type(lock.get('options')) is not dict:
            raise LockError('constructor lock options must be an object')
        policy = SR.validate_constructor_options(lock['options'])
        if policy['mode'] != config['mode'] or R.J.canonical(policy['limits']) != R.J.canonical(config['limits']):
            raise LockError('constructor lock options differ from its recorded configuration')
        R.bind_journal(journal, config, source_sha256=lock.get('source_sha256'),
                       input_sha256=E.digest(lock['inputs']), kernel_id=(lock.get('kernel') or {}).get('id'))
        _provenance_validate(bundle['epistemic'], bundle['bindings'], journal)
    except (R.RecordsError, S.SymblicError, ValueError, TypeError, AttributeError) as exc:
        raise LockError('invalid constructor bundle: ' + str(exc)[:256]) from None
    return config, journal


def _constructor_export(folder, state, lock):
    # No quarantine bytes may disappear from a portable package. This includes
    # an interrupted repair whose truncate succeeded before the audit row.
    # Journal v3 has eight fixed paths; lexists refuses links without reading them.
    if any(os.path.lexists(os.path.join(folder, f'constructor-events.torn-{slot}.bin')) for slot in range(8)):
        raise LockError('constructor quarantine remains; repaired journals require quarantine packaging; export is not supported yet')
    present = os.path.lexists(os.path.join(folder, 'constructor-events.jsonl'))
    if not present:
        if os.path.lexists(os.path.join(folder, '.constructor-events.lock')):
            raise LockError('constructor journal is missing but its lock remains; explicit recovery is required')
        from symblic.kernel import run as SR
        try:
            # A configuration alone does not promote a never-used ordinary lock.
            # Host activity, even without a solver-origin accepted value, must survive.
            mode = SR.validate_constructor_options(lock.get('options') or {})['mode']
            SR.constructor_history_gate(folder, mode=mode)
        except S.SymblicError as exc:
            raise LockError('constructor records cannot be exported: ' + str(exc)[:256]) from None
        return None
    from symblic.constructor import records as R
    try:
        text = R.read_journal(folder)
        config = R.read_config(folder)
        if config is None or text is None:
            raise LockError('constructor journal requires its exact configuration')
        bundle = {'version': 1, 'configuration': R.J.canonical(config), 'configuration_sha256': R.config_hash(config),
                  'journal': text, 'journal_sha256': hashlib.sha256(text.encode('ascii')).hexdigest(),
                  'epistemic': state.get('epistemic'), 'bindings': _binding_provenance(state.get('bindings'))}
        _constructor_validate(bundle, lock)
        return copy.deepcopy(bundle)
    except R.RecordsError as exc:
        raise LockError('constructor records cannot be exported: ' + str(exc)[:256]) from None


def _constructor_restore(bundle, folder):
    from symblic.constructor import records as R
    # _validate already checked both exact payloads; this folder is fresh and private.
    for name, contents in ((R.CONFIG_FILE, bundle['configuration']), (R.J.FILE, bundle['journal'])):
        path = os.path.join(folder, name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        primary = None
        try:
            raw = memoryview(contents.encode('ascii'))
            while raw:
                written = os.write(fd, raw)
                if written <= 0:
                    raise OSError('constructor replay restore made no write progress')
                raw = raw[written:]
            os.fsync(fd)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            R._cleanup(lambda: os.close(fd), primary, 'Closing restored constructor record')
    R._sync_folder(folder)


def _constructor_matches(bundle, report, *, folder=None):
    from symblic.constructor import records as R
    try:
        journal = R.validate_journal(bundle['journal'])
        old = _provenance_validate(bundle['epistemic'], bundle['bindings'], journal)
        fresh = _provenance_validate(report.get('epistemic'), _binding_provenance(report.get('bindings')), journal)
        if old != fresh:
            return False
        if folder is not None:
            if R.read_journal(folder) != bundle['journal']:
                return False
            config = R.read_config(folder)
            if config is None or R.J.canonical(config) != bundle['configuration']:
                return False
        return True
    except (LockError, R.RecordsError, TypeError, ValueError):
        return False


def _validate(lock, *, current_kernel=None):
    if not isinstance(lock, dict) or lock.get('symblic_lock') not in (LOCK_VERSION, CONSTRUCTOR_LOCK_VERSION):
        raise LockError('unsupported Symblic lock version; legacy unpinned locks cannot be replayed')
    if lock['symblic_lock'] == CONSTRUCTOR_LOCK_VERSION:
        if type(lock['symblic_lock']) is not int:
            raise LockError('constructor lock version must be an exact integer')
        _constructor_validate(lock.get('constructor'), lock)
    elif 'constructor' in lock:
        raise LockError('constructor records require lock version 3')
    if lock.get('sha256') != lock_hash(lock):
        raise LockError('the lock was edited after it was made (its hash does not match)')
    if (not isinstance(lock.get('source'), str)
            or hashlib.sha256(lock['source'].encode()).hexdigest() != lock.get('source_sha256')):
        raise LockError('the lock program source hash does not match')
    if 'authoring' in lock:
        try:
            from symblic.english.authoring import checked_authoring
            if not checked_authoring(lock['authoring'], lock['source']):
                raise ValueError('English instructions differ from their saved hashes')
        except (ImportError, ValueError, TypeError) as exc:
            raise LockError('the lock English authoring record is invalid: ' + str(exc)) from None
    original = _kernel_identity(lock.get('kernel'))
    if lock.get('version') != original['lang'] or lock.get('canon') != original['canon']:
        raise LockError('the lock version disagrees with its kernel identity')
    if current_kernel is not None and original != _kernel_identity(current_kernel):
        raise LockError('kernel identity mismatch: replay/comparison across semantic versions is refused')
    _validate_modules(lock.get('modules'))
    ledgers = lock.get('effect_ledgers', {})
    if (not isinstance(ledgers, dict) or any(name not in EFFECT_LEDGERS for name in ledgers)
            or any(not isinstance(contents, str) for contents in ledgers.values())):
        raise LockError('invalid effect ledger file names or contents')
    catalogue = lock.get('effect_catalogue')
    if catalogue is not None:
        try:
            data = json.loads(catalogue) if isinstance(catalogue, str) else None
        except ValueError as exc:
            raise LockError('invalid frozen effect catalogue') from exc
        if (not isinstance(data, dict) or not isinstance(data.get('capabilities'), dict)
                or type(data.get('version')) is not int or not isinstance(data.get('digest'), str)):
            raise LockError('invalid frozen effect catalogue')
    if (type(lock.get('provenance_recorded')) is not bool
            or lock['provenance_recorded'] != isinstance(lock.get('evidence'), dict)):
        raise LockError('the lock evidence availability flag is inconsistent')
    if (lock.get('evidence') is not None
            and lock['evidence'].get('source_sha256') != lock['source_sha256']):
        raise LockError('the lock evidence belongs to a different program')
    _evidence_identity(lock.get('evidence'))
    if not isinstance(lock.get('checks'), list):
        raise LockError('the lock validation events must be a list')
    for row in lock.get('checks', []):
        if not isinstance(row, dict) or 'check' not in row:
            raise LockError('invalid recorded validation event')
        _evidence_identity(row['check'])
    if not isinstance(lock.get('options'), dict) or not isinstance(lock.get('inputs'), dict):
        raise LockError('the lock options and inputs must be objects')
    if not isinstance(lock.get('calls'), list) or not isinstance(lock.get('statements'), list):
        raise LockError('the lock calls and statements must be lists')
    for row in lock['statements']:
        if not isinstance(row, dict) or not all(key in row for key in ('key', 'line', 'name', 'hash')):
            raise LockError('invalid locked statement')
        _evidence_identity(row.get('evidence'))
    seen = set()
    for row in lock['calls']:
        if (not isinstance(row, dict) or not isinstance(row.get('key'), str) or not row['key']
                or not isinstance(row.get('reply'), dict) or row['key'] in seen):
            raise LockError('invalid or duplicate recorded call')
        if 'replies' in row and (not isinstance(row['replies'], list) or not row['replies']
                or any(not isinstance(r, dict) or type(r.get('ok')) is not bool for r in row['replies'])
                or row['reply'] != row['replies'][-1]):
            raise LockError('invalid recorded reply sequence')
        seen.add(row['key'])
    return lock


def save_lock(lock: dict, path: str) -> None:
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(lock, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_lock(path: str) -> dict:
    if os.path.getsize(path) > MAX_LOCK_BYTES:
        raise LockError('the lock file is too large')
    with open(path, encoding='utf-8') as f:
        lock = json.load(f)
    return _validate(lock)


class _NoModels:
    """Every call the lock does not answer fails, so a replay can never reach a model."""

    def __init__(self):
        self.refused = []

    def call(self, req):
        self.refused.append({'app': S.app_label(req['app']), 'key': req.get('key')})
        return {'ok': False, 'fatal': True, 'error': 'replay: this call is not in the lock'}

    def delegate(self, *args, **kwargs):
        self.refused.append({'effect': 'delegate'})
        return {'ok': False, 'error': 'replay: external effects are refused'}


def replay(lock: dict, source: str | None = None, log=None) -> dict:
    """Run the locked program again from the lock alone. {'ok', 'fingerprint', 'expected', 'refused',
    'report'}. With `source`, the given text must be the locked program."""
    from symblic.kernel import run as SR
    _validate(lock, current_kernel=S.kernel_id())
    if source is not None and hashlib.sha256(source.encode('utf-8')).hexdigest() != lock['source_sha256']:
        raise LockError('this program is not the one the lock was made for (its SHA-256 differs)')
    folder = tempfile.mkdtemp(prefix='symblic-replay-')
    try:
        os.chmod(folder, 0o700)
        with open(os.path.join(folder, 'calls.jsonl'), 'w', encoding='utf-8') as f:
            f.writelines(json.dumps({**r, 'ok': bool(r['reply'].get('ok')),
                                     'replies': r.get('replies', [r['reply']])}, ensure_ascii=False) + '\n'
                         for r in lock['calls'])
        if lock.get('modules'):
            with open(os.path.join(folder, 'modules.json'), 'w', encoding='utf-8') as f:
                json.dump(lock['modules'], f, ensure_ascii=False)
        for name, contents in lock.get('effect_ledgers', {}).items():
            with open(os.path.join(folder, name), 'w', encoding='utf-8', newline='') as f:
                f.write(contents)
            os.chmod(os.path.join(folder, name), 0o600)
        if lock.get('effect_catalogue') is not None:
            path = os.path.join(folder, EFFECT_CATALOGUE_FILE)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(lock['effect_catalogue'])
            os.chmod(path, 0o600)
        if lock['symblic_lock'] == CONSTRUCTOR_LOCK_VERSION:
            _constructor_restore(lock['constructor'], folder)
        # The validated lock supplies the identity of this temporary replay folder.
        kernel = lock['kernel']
        path = os.path.join(folder, SR.KERNEL_RECORD)
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump({'version': SR.KERNEL_RECORD_VERSION, 'id': kernel['id'], 'lang': kernel['lang'],
                       'kernel': kernel, 'basis': 'lock'}, stream, ensure_ascii=False)
        os.chmod(path, 0o600)
        apps = _NoModels()
        options = _portable_options(lock.get('options') or {})
        options.update(replay=True, side_effects=False)
        run = SR.Run(lock['source'], lock.get('inputs') or {}, apps, options, folder=folder,
                     log=log)
        rep = run.execute()
        constructor_match = None
        if lock['symblic_lock'] == CONSTRUCTOR_LOCK_VERSION:
            constructor_match = _constructor_matches(lock['constructor'], rep, folder=folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    evidence_match = (not lock.get('provenance_recorded')
                      or _evidence_identity(rep.get('evidence')) == _evidence_identity(lock.get('evidence')))
    binding_evidence = {r['key']: r.get('evidence') for r in lock['statements'] if r.get('evidence') is not None}
    replay_evidence = {r['key']: r.get('evidence') for r in statements_of(rep.get('bindings'), rep.get('outputs'))}
    evidence_match = evidence_match and all(_evidence_identity(replay_evidence.get(k)) == _evidence_identity(v)
                                            for k, v in binding_evidence.items())
    ok = (rep['status'] == 'done' and rep['fingerprint'] == lock['fingerprint'] and not apps.refused
          and evidence_match and constructor_match is not False)
    return {'ok': ok, 'fingerprint': rep['fingerprint'], 'expected': lock['fingerprint'], 'status': rep['status'],
            'error': rep.get('error'), 'refused': apps.refused, 'calls': rep['calls'], 'cached': rep['cached'],
            'evidence_match': evidence_match, 'recorded_evidence': lock.get('evidence'),
            'recorded_checks': lock.get('checks', []), 'report': rep,
            **({'recorded_authoring': copy.deepcopy(lock['authoring'])} if 'authoring' in lock else {}),
            **({'constructor_match': constructor_match} if constructor_match is not None else {})}


def drift(lock: dict, report: dict) -> dict:
    """Compare a fresh run of the locked program (new agents, no shared record) with the lock: which
    statements now have a different fingerprint. Agreement with the lock is not correctness either."""
    _validate(lock, current_kernel=report.get('kernel') or {})
    fresh = {r['key']: r for r in statements_of(report.get('bindings') or [], report.get('outputs') or [])}
    rows, same, model, model_same = [], 0, 0, 0
    for r in lock['statements']:
        f = fresh.get(r['key'])
        match = f is not None and f['hash'] == r['hash']
        same += match
        if r.get('class') not in ('exact', 'output', None):
            model += 1
            model_same += match
        if not match:
            rows.append({'key': r['key'], 'line': r['line'], 'name': r['name'], 'class': r.get('class'),
                         'locked': r.get('value'), 'now': f.get('value') if f else None,
                         'missing': f is None})
    result = {'same_run': report.get('fingerprint') == lock['fingerprint'], 'statements': len(lock['statements']),
            'identical': same, 'model_statements': model, 'model_identical': model_same, 'changed': rows,
            'status': report.get('status')}
    if lock['symblic_lock'] == CONSTRUCTOR_LOCK_VERSION:
        result['constructor_match'] = _constructor_matches(lock['constructor'], report)
        result['same_run'] = result['same_run'] and result['constructor_match']
    return result


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog='python3 -m symblic.kernel.lockfile', description='Symblic lockfiles.')
    p.add_argument('cmd', choices=['lock', 'replay', 'show'])
    p.add_argument('path', help='lock: a finished run folder; replay/show: a lock file')
    p.add_argument('--out', default='', help='lock: where to write it (default: FOLDER/run.lock.json)')
    a = p.parse_args(argv)
    if a.cmd == 'lock':
        lock = make_lock(a.path)
        out = a.out or os.path.join(a.path, 'run.lock.json')
        save_lock(lock, out)
        print(f'{out}: {len(lock["statements"])} statements, {len(lock["calls"])} calls, fingerprint '
              f'{lock["fingerprint"]}')
        return 0
    lock = load_lock(a.path)
    if a.cmd == 'show':
        print(f'{lock["program"]}: fingerprint {lock["fingerprint"]}, {len(lock["calls"])} calls, '
              f'source {lock["source_sha256"][:16]}')
        for r in lock['statements']:
            print(f'{r["line"]:>5} {r["name"]:<20} {r.get("class") or "":<11} {r["hash"]}  {str(r.get("value"))[:60]}')
        return 0
    res = replay(lock)
    print(f'replay {"OK" if res["ok"] else "FAILED"}: fingerprint {res["fingerprint"]} (locked {res["expected"]}), '
          f'{res["cached"]} answers from the lock, {len(res["refused"])} refused' +
          (f' · {res["error"]["message"]}' if res.get('error') else ''))
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    from symblic.kernel import lockfile as _canonical      # one copy of the module's classes
    sys.exit(_canonical.main())

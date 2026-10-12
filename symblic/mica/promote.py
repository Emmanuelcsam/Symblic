"""MICA promotion: a finished construction whose frozen check pack passes becomes a reusable library component.

Run as `python3 -m symblic.mica.cli promote ...`. Depends on library.py, checkpack.py, search.py, cli.py,
symblic.js.check, symblic.graph.run, symblic.spec.contracts.

Details
    Stage IV promotion: a done MICA construction becomes a reusable zero-call component.

    `promote` reads one retained MicaRun folder through the same verified readers as
    `python3 -m symblic.mica.cli status/artifacts`, requires status `done`, validates a frozen
    finite verification pack against its caller-retained SHA-256, and reruns every
    caller-supplied pack row (original public tests, generated public rows and
    evaluator-only hidden rows) against the retained program text with the existing
    sandboxed JavaScript checker, in root acceptance's argument shape and under one
    bounded deadline. Only when every row passes are the run's accepted units, as
    already retained in its TESTED component tokens, published into the private
    ComponentLibrary under their exact contract/dependency/runtime identity, and a
    sealed receipt is written to <library_root>/promotions/. A later construction
    given that library finds the component by identity and still rechecks it before
    reuse: a promoted unit costs zero provider calls but never skips current checks.

    A receipt records finite checks only. It is not a proof of general correctness,
    an independent oracle for the caller's intent, or authenticated provenance.
    Model-proposed pack rows remain proposals and never count. Failing hidden rows
    are reported by ID only. No provider, model, worker or network is used;
    importing this module starts nothing and touches no store.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from symblic.graph import run as G
from symblic.js import check as JS
from symblic.mica import library as L
from symblic.spec import contracts as SC

VERSION = 1
ASSURANCE = 'TESTED_ON_FROZEN_FINITE_PACK'
SCOPE = 'finite checks only: not a proof of general correctness'
BINDINGS = ('original_request', 'public_request')
FOLDER = 'promotions'
DEFAULT_WALL_SECONDS = 300
MAX_WALL_SECONDS = 3600
MAX_RECEIPT_BYTES = 1_000_000
MAX_LISTING = 4096
MAX_COMPONENTS = 128
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_RUN_ID = re.compile(r'[0-9a-f]{32}\Z')
_RECEIPT_NAME = re.compile(r'[0-9a-f]{32}-[0-9a-f]{16}\.json\Z')
_FIELDS = frozenset({'version', 'run_id', 'result_sha256', 'pack_sha256', 'request_binding', 'cases',
                     'finite_domains', 'components', 'runtime', 'assurance', 'scope', 'at', 'sha256'})


class PromotionError(ValueError):
    def __init__(self, code, message, *, cause=None):
        self.code, self.cause = code, cause
        super().__init__(message)


@contextmanager
def _stage(code):
    """Name the refused stage; an underlying module's own code is kept as the cause."""
    try:
        yield
    except PromotionError:
        raise
    except (ValueError, KeyError, TypeError, OSError, RecursionError, JS.JsError) as exc:
        cause = getattr(exc, 'code', None)
        raise PromotionError(code, str(exc)[:1000] or type(exc).__name__,
                             cause=cause if type(cause) is str else type(exc).__name__) from None


def promote(run_dir, *, pack, pack_sha256, library_root, runtime=None, wall_seconds=DEFAULT_WALL_SECONDS):
    """Promote the accepted units of one done run after every frozen pack row passes.

    Returns {'status': 'promoted', 'receipt', ...}; {'status': 'refused', 'code',
    'cause', 'error', 'failed': [...]} with nothing written; or {'status':
    'inconclusive', ...} when the checker could not finish, which is neither a
    pass nor a failure. `runtime` defaults to the current MICA implementation
    identity and must equal the run's. An identical repeat returns the existing
    receipt without rerunning checks; a receipt for another result or pack under
    the same name is refused and left unchanged.
    """
    try:
        wall_seconds = _wall_seconds(wall_seconds)
        if type(pack_sha256) is not str or not _SHA.fullmatch(pack_sha256):
            raise PromotionError('arguments', 'Supply the exact lowercase SHA-256 retained when the pack was frozen.')
        if runtime is not None and type(runtime) is not dict:
            raise PromotionError('arguments', 'An explicit runtime must be a MICA implementation identity object.')
        evidence = _evidence(run_dir, runtime)
        checked, binding = _bound_pack(pack, pack_sha256, evidence['request'])
        with _stage('pack'):
            rows, proposals = _rows(checked)
        public = sum(row['visibility'] == 'public' for row in rows)
        body = {'version': VERSION, 'run_id': evidence['run_id'], 'result_sha256': evidence['result_sha256'],
                'pack_sha256': pack_sha256, 'request_binding': binding,
                'cases': {'public': public, 'hidden': len(rows) - public, 'total': len(rows)},
                'finite_domains': copy.deepcopy(checked.get('finite_domains')),
                'components': [{key: row[key] for key in ('key', 'code_sha256', 'contract_sha256')}
                               for row in evidence['components']],
                'runtime': evidence['runtime'], 'assurance': ASSURANCE, 'scope': SCOPE}
        name = '%s-%s.json' % (evidence['run_id'], pack_sha256[:16])
        prior = _probe(library_root, name)
        if prior is not None:
            _same_or_conflict(prior, body)
        else:
            failed, unknown = _verify_rows(evidence['text'], rows, wall_seconds)
            extra = {'cases': body['cases'], 'proposals_excluded': proposals}
            if unknown is not None:
                return {'version': VERSION, 'status': 'inconclusive', 'code': 'verification_unknown',
                        'cause': unknown[0], 'error': unknown[1], 'failed': [], **extra}
            if failed:
                return {'version': VERSION, 'status': 'refused', 'code': 'checks_failed', 'cause': None,
                        'error': '%d of %d frozen pack cases failed; nothing was published.' % (len(failed), len(rows)),
                        'failed': failed, **extra}
        receipt, existing, published, path = _commit(library_root, name, body, evidence['components'],
                                                     evidence['runtime'], checked=prior is None)
    except PromotionError as exc:
        return {'version': VERSION, 'status': 'refused', 'code': exc.code, 'cause': exc.cause,
                'error': str(exc)[:1000], 'failed': []}
    return {'version': VERSION, 'status': 'promoted', 'existing': existing, 'checked': prior is None,
            'receipt': receipt, 'receipt_file': str(path), 'published': published,
            'proposals_excluded': proposals, 'scope': SCOPE}


def promotions(library_root):
    """Verified receipts directly inside <library_root>/promotions, in run/pack order.

    Symlinked, misnamed, oversized, unsealed or malformed entries are ignored;
    a symlinked library/promotion folder is refused. Nothing outside is read.
    """
    return _scan(library_root)[0]


def _wall_seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= MAX_WALL_SECONDS:
        raise PromotionError('arguments', 'wall_seconds must be a finite number from 1 to %d.' % MAX_WALL_SECONDS)
    return value


def _evidence(run_dir, runtime):
    """Verified retained facts of one done MicaRun; reads only, never writes."""
    from symblic.mica import search as M
    from symblic.mica import cli as CLI
    folder = Path(run_dir).absolute()
    with _stage('run_evidence'):
        project = folder / 'project-manifest.json'
        if project.exists() or project.is_symlink():
            raise PromotionError('unsupported', 'Objective project folders are not promoted directly; pass the '
                                 'MicaRun construction folder holding mica-manifest.json and mica-result.json.')
        # Same sealed readers as `status`/`artifacts`: manifest pin, verify_result_artifacts, host costs.
        folder, manifest, result = CLI._run_records(folder)
    if result is None:
        raise PromotionError('not_done', 'The run has no retained terminal result; incomplete construction is never promoted.')
    if result.get('status') != 'done':
        raise PromotionError('not_done', 'Only a done construction is promoted; the retained status is %s.'
                             % json.dumps(result.get('status'))[:80])
    with _stage('runtime'):
        current = M.implementation_identity() if runtime is None else copy.deepcopy(runtime)
        if manifest['identity'] != current:
            raise PromotionError('runtime', 'The retained run was built under another implementation identity; '
                                 'its components would be keyed and rechecked under a different runtime.')
        if current.get('javascript') != JS.VERSION:
            raise PromotionError('runtime', 'The current JavaScript checker differs from the runtime identity, '
                                 'so pack rows would not run under the recorded checker.')
    with _stage('run_evidence'):
        output, run_id = result['output'], manifest.get('run_id')
        if (type(output) is not dict or type(output.get('text')) is not str
                or output.get('sha256') != hashlib.sha256(output['text'].encode()).hexdigest()):
            raise PromotionError('run_evidence', 'Output source digest is missing or changed.')
        if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
            raise PromotionError('run_evidence', 'The construction manifest has no exact run ID.')
        plan = _accepted_plan(M, folder, manifest['request'], result)
        components = _components(M, folder, manifest, plan, result['manifest'], current)
    return {'request': manifest['request'], 'run_id': run_id, 'result_sha256': G._hash(result),
            'text': output['text'], 'components': components, 'runtime': current}


def _accepted_plan(M, folder, request, result):
    """The exact admitted plan of the branch whose build produced the terminal result."""
    from symblic.mica import contracts as C
    attempts = result.get('attempts')
    last = attempts[-1] if type(attempts) is list and attempts else None
    index = last.get('branch') if type(last) is dict else None
    if type(index) is not int or not 0 <= index < 1000 or last.get('status') != 'done':
        raise PromotionError('run_evidence', 'The done result does not name its accepted branch.')
    branch = M._read(folder, 'branch-%03d.json' % index)
    if branch.get('root_request_sha256') != C.digest(request):
        raise PromotionError('run_evidence', 'The accepted branch belongs to another root request.')
    plan = C.validate_plan(request, branch['plan'])
    accepted = branch['result']
    if (plan['content_hash'] != last.get('plan_sha256') or type(accepted) is not dict
            or accepted.get('status') != 'done'
            or any(accepted.get(key) != result.get(key) for key in ('output', 'manifest', 'checks', 'decisions'))):
        raise PromotionError('run_evidence', 'The accepted branch plan or result differs from the terminal result.')
    return plan


def _components(M, folder, manifest, plan, assembly, runtime):
    """Accepted units with the library identity derived exactly as MicaRun._prepare_unit derives it.

    Contract and dependency hashes are recomputed by MicaRun's own methods (the
    key is a one-way hash); the code, key and runtime come from the retained
    component token, which must agree with the verified accepted assembly.
    """
    view = M.MicaRun(manifest['request'], folder, None, manifest['inventory'])  # stores only; no I/O
    spec = view._sheet_plan(plan)
    if spec != assembly['plan']:
        raise PromotionError('run_evidence', 'The accepted assembly was not built from the retained branch plan.')
    owners = {name: contract for contract in plan['contracts'] for name in contract['unit']['names']}
    artifacts, store = assembly['artifacts'], folder / 'components'
    if store.is_symlink() or not store.is_dir():
        raise PromotionError('run_evidence', 'The retained component folder is missing or redirected.')
    rows = []
    for unit in spec['units']:
        contract = owners[unit['exports'][0]]
        contract_hash = view._component_contract_hash(contract, unit['contract_sha256'])
        dependency_hashes = [artifacts[dep]['sha256'] for dep in unit['closure']]
        key = L.identity(contract_hash, dependency_hashes, runtime)
        code = artifacts[unit['id']]['code']
        code_sha256 = SC.code_hash(code)
        name = key + '-' + code_sha256 + '.json'
        if not M._exists(store, name):
            raise PromotionError('run_evidence', 'Accepted unit %s has no retained component token.' % contract['contract_id'])
        token = M._read(store, name)
        artifact = token.get('artifact')
        if (token.get('key') != key or token.get('code') != code or token.get('runtime') != runtime
                or token.get('assurance') != 'TESTED' or type(artifact) is not dict
                or artifact.get('code_sha256') != code_sha256):
            raise PromotionError('run_evidence', 'The retained component token of %s no longer matches its accepted unit.'
                                 % contract['contract_id'])
        rows.append({'unit_id': unit['id'], 'contract_id': contract['contract_id'], 'key': key,
                     'code_sha256': code_sha256, 'contract_sha256': contract_hash,
                     'dependency_hashes': dependency_hashes, 'code': token['code']})
    return rows


def _bound_pack(pack, pack_sha256, request):
    """Validate the pin, then require the run to be built from the pack's own original or public request."""
    from symblic.mica import checkpack as K
    from symblic.mica import contracts as C
    with _stage('pack'):
        checked = K.validate(pack, expected_sha256=pack_sha256)
        original, public = checked['original_request'], checked['public_request']
        digest = C.digest(request)
    if original['exports'] != request['exports']:
        raise PromotionError('signature', 'Pack rows call the exports %s, but the retained result declares %s; '
                             'promotion refuses to guess a mapping between signatures.'
                             % (json.dumps([e['signature'] for e in original['exports']]),
                                json.dumps([e['signature'] for e in request['exports']])))
    if digest == checked['original_request_sha256']:
        return checked, 'original_request'
    if digest == checked['public_request_sha256']:
        return checked, 'public_request'
    fields = sorted(key for key in set(request) | set(original)
                    if request.get(key) != original.get(key) and request.get(key) != public.get(key))
    raise PromotionError('request_binding', 'The pack was frozen for another request (differs in: %s); promote a '
                         'run built from the pack original or public request.' % (', '.join(fields) or 'canonical form'))


def _rows(pack):
    """Authoritative rows: public request tests (original prefix, then caller public rows) and caller hidden rows."""
    supplied = [row for row in pack['checks'] if row['origin'] == 'caller_supplied']
    public = [row for row in supplied if row['visibility'] == 'public']
    hidden = [row for row in supplied if row['visibility'] == 'hidden']
    original, tests = pack['original_request']['tests'], pack['public_request']['tests']
    if ([[t['call'], t['expected']] for t in tests]
            != [[t['call'], t['expected']] for t in original] + [[r['call'], r['expected']] for r in public]):
        raise PromotionError('pack', 'The public request is not the original tests followed by caller public rows.')
    ids = ['original:%d' % index for index in range(len(original))] + [row['id'] for row in public]
    rows = [{'id': ident, 'visibility': 'public', 'call': test['call'], 'expected': test['expected']}
            for ident, test in zip(ids, tests)]
    rows += [{'id': row['id'], 'visibility': 'hidden', 'call': row['call'], 'expected': row['expected']}
             for row in hidden]
    return rows, len(pack['checks']) - len(supplied)


def _verify_rows(text, rows, wall_seconds):
    """Run every row as root acceptance does, JS.test's comparison via JS.failures; (failed, unknown)."""
    deadline = time.monotonic() + wall_seconds
    failed = []
    try:
        for offset in range(0, len(rows), JS.MAX_CASES):
            chunk = rows[offset:offset + JS.MAX_CASES]
            misses, _ = JS.failures(text, [[row['call'], row['expected']] for row in chunk], deadline=deadline)
            position = 0
            for row in chunk:  # failures() reports in case order
                if position < len(misses) and tuple(misses[position][:2]) == (row['call'], row['expected']):
                    failed.append(_failure(row, misses[position][2]))
                    position += 1
            if position != len(misses):
                raise PromotionError('checker', 'Checker failures could not be attributed to pack rows.')
    except JS.JsError as exc:
        return [], (getattr(exc, 'kind', 'unknown'), 'The checker could not complete every pack case (%s); '
                    'no verdict and nothing was published.' % str(exc)[:600])
    return failed, None


def _failure(row, observed):
    if row['visibility'] == 'hidden':
        return {'id': row['id'], 'visibility': 'hidden',
                'detail': 'withheld: evaluator-only case; look up this ID in the retained pack'}
    return {'id': row['id'], 'visibility': 'public', 'call': row['call'], 'expected': row['expected'],
            'observed': str(observed)[:600]}


def _probe(library_root, name):
    """Read-only lookup of an earlier receipt; creates nothing."""
    with _stage('library'):
        folder = Path(library_root).absolute() / FOLDER
        if any(path.is_symlink() for path in (folder, *folder.parents)):
            raise PromotionError('library', 'Symlinked component library or promotion folder refused.')
        return _existing(folder, name)


def _existing(folder, name):
    """The verified receipt at name, None when absent; an unreadable one is a conflict."""
    try:
        descriptor = _open_folder(folder)
    except FileNotFoundError:
        return None
    try:
        return _read_receipt(descriptor, name)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise PromotionError('receipt_conflict', 'An existing receipt for this run and pack is unreadable or altered; '
                             'it was left unchanged for inspection.', cause=type(exc).__name__) from None
    finally:
        os.close(descriptor)


def _same_or_conflict(existing, body):
    if {key: value for key, value in existing.items() if key not in ('at', 'sha256')} == body:
        return
    if existing['result_sha256'] != body['result_sha256']:
        reason = 'records a different retained result/program for this run'
    elif existing['pack_sha256'] != body['pack_sha256']:
        reason = 'records a different frozen pack under the same name prefix'
    else:
        reason = 'records different components, cases, binding or runtime'
    raise PromotionError('receipt_conflict', 'An existing promotion receipt %s; it was left unchanged.' % reason)


def _commit(library_root, name, body, components, runtime, *, checked):
    """Publish the components, then write the receipt last; serialized per promotion folder."""
    with _stage('library'):
        library = L.ComponentLibrary(library_root)
        folder = library.root / FOLDER
        if folder.is_symlink():
            raise PromotionError('library', 'Symlinked promotion folder refused.')
        G._mkdir_private(folder)
        with _locked(folder):
            existing = _existing(folder, name)
            if existing is not None:
                _same_or_conflict(existing, body)
            elif not checked:
                raise PromotionError('receipt_conflict', 'The earlier identical receipt disappeared during promotion; '
                                     'retry so the pack is checked again.')
            published = _publish(library, components, runtime)
            if existing is not None:
                return existing, True, published, folder / name
            receipt = G._seal({**body, 'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
            G._write_json(folder, name, receipt)  # crash-atomic private 0600 replace
            return receipt, False, published, folder / name


def _publish(library, components, runtime):
    """Idempotent: identical records are kept as they are. Capacity is checked before any write."""
    for row in components:
        present = library.candidates(row['key'], runtime=runtime)
        if (len(present) >= L.MAX_CANDIDATES
                and not any(token['code_sha256'] == row['code_sha256'] for token in present)):
            raise PromotionError('library', 'Component identity %s already holds %d variants; nothing was published.'
                                 % (row['key'], L.MAX_CANDIDATES))
    published = []
    for row in components:
        result = library.publish(contract_sha256=row['contract_sha256'], dependency_hashes=row['dependency_hashes'],
                                 runtime=runtime, code=row['code'])
        if result.get('key') != row['key'] or result.get('retained') is not True:
            raise PromotionError('library', 'The component library did not retain %s; no receipt was written.' % row['key'])
        published.append({'key': row['key'], 'code_sha256': row['code_sha256'], 'record_sha256': result['sha256']})
    return published


@contextmanager
def _locked(folder):
    # A separate lock file: ComponentLibrary.publish takes its own non-reentrant lock inside.
    descriptor = os.open(folder / '.promotions.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)  # closing releases the flock


def _open_folder(folder):
    return os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _read_receipt(directory, name):
    """Bounded no-follow read relative to an open folder, seal and shape verified."""
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECEIPT_BYTES:
            raise PromotionError('receipt', 'A promotion receipt must be a bounded regular file.')
        raw = stream.read(MAX_RECEIPT_BYTES + 1)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise PromotionError('receipt', 'A promotion receipt exceeds its byte bound.')
    receipt = G._unseal(G._decode(raw))
    _check_receipt(receipt, name)
    return receipt


def _check_receipt(receipt, name):
    if type(receipt) is not dict or set(receipt) != _FIELDS:
        raise PromotionError('receipt', 'Promotion receipt fields differ from version 1.')
    cases, components = receipt['cases'], receipt['components']
    valid = (type(receipt['version']) is int and receipt['version'] == VERSION
             and type(receipt['run_id']) is str and _RUN_ID.fullmatch(receipt['run_id']) is not None
             and all(type(receipt[key]) is str and _SHA.fullmatch(receipt[key]) is not None
                     for key in ('result_sha256', 'pack_sha256'))
             and name == '%s-%s.json' % (receipt['run_id'], receipt['pack_sha256'][:16])
             and receipt['request_binding'] in BINDINGS
             and type(cases) is dict and set(cases) == {'public', 'hidden', 'total'}
             and all(type(value) is int and value >= 0 for value in cases.values())
             and cases['public'] >= 1 and cases['total'] == cases['public'] + cases['hidden']
             and type(components) is list and 1 <= len(components) <= MAX_COMPONENTS
             and all(type(row) is dict and set(row) == {'key', 'code_sha256', 'contract_sha256'}
                     and all(type(value) is str and _SHA.fullmatch(value) is not None for value in row.values())
                     for row in components)
             and type(receipt['runtime']) is dict and receipt['assurance'] == ASSURANCE
             and receipt['scope'] == SCOPE and type(receipt['at']) is str and 0 < len(receipt['at']) <= 64)
    if not valid:
        raise PromotionError('receipt', 'Promotion receipt does not match its name or version 1 shape.')


def _scan(library_root):
    folder = Path(library_root).absolute() / FOLDER
    if any(path.is_symlink() for path in (folder, *folder.parents)):
        raise PromotionError('library', 'Symlinked component library or promotion folder refused.')
    try:
        descriptor = _open_folder(folder)
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        raise PromotionError('library', 'The promotion folder is not a directory.', cause=type(exc).__name__) from None
    receipts, ignored = [], []
    try:
        with os.scandir(descriptor) as entries:
            for count, entry in enumerate(entries, 1):
                if count > MAX_LISTING:
                    raise PromotionError('limit', 'The promotion folder exceeds %d entries; nothing was listed.' % MAX_LISTING)
                name = entry.name
                if name.startswith('.'):
                    continue  # the promotion lock and crash-atomic write temporaries
                if not _RECEIPT_NAME.fullmatch(name):
                    reason = 'unrecognized_name'
                elif entry.is_symlink():
                    reason = 'symlink'
                else:
                    try:
                        receipts.append(_read_receipt(descriptor, name))
                        continue
                    except (OSError, ValueError, KeyError, TypeError, RecursionError):
                        reason = 'unverified'
                ignored.append({'name': name[:255], 'reason': reason})
    finally:
        os.close(descriptor)
    receipts.sort(key=lambda row: (row['run_id'], row['pack_sha256']))
    ignored.sort(key=lambda row: row['name'])
    return receipts, ignored


def parser():
    from symblic.mica import cli as CLI
    p = CLI._Parser(prog='python3 -m symblic.mica.cli promote', description=__doc__, add_help=False)
    p.add_argument('--help', action='store_true')
    commands = p.add_subparsers(dest='command')
    run = commands.add_parser('promote', add_help=False)
    run.add_argument('--dir', required=True, help='Retained MicaRun construction folder with a done result.')
    run.add_argument('--pack', required=True, help='Sealed frozen check pack (evaluator-side: holds hidden rows).')
    run.add_argument('--freeze', required=True, help='Pack SHA-256 retained when the pack was frozen.')
    run.add_argument('--library', required=True, help='Private component library root.')
    run.add_argument('--wall-seconds', type=int, default=DEFAULT_WALL_SECONDS)
    listing = commands.add_parser('list', add_help=False)
    listing.add_argument('--library', required=True)
    return p


def dispatch(args):
    """Return (JSON result, exit code): 0 promoted/listed, 1 refused or inconclusive."""
    if args.help or args.command is None:
        return {'version': VERSION, 'commands': ['promote', 'list'], 'assurance': ASSURANCE, 'scope': SCOPE,
                'checked_rows': 'every caller-supplied public and hidden pack row; model-proposed rows never count',
                'hidden_failures': 'reported by row ID only', 'provider_calls': 0,
                'receipts': '<library>/promotions/<run_id>-<pack_sha256[:16]>.json',
                'usage': parser().format_help()}, 0
    if args.command == 'list':
        receipts, ignored = _scan(args.library)
        return {'version': VERSION, 'status': 'listed', 'receipts': receipts, 'ignored': ignored, 'scope': SCOPE}, 0
    from symblic.mica import checkpack as K
    from symblic.mica import cli as CLI
    pack = CLI._json_file(args.pack, max_bytes=K.MAX_BYTES)
    report = promote(args.dir, pack=pack, pack_sha256=args.freeze, library_root=args.library,
                     wall_seconds=args.wall_seconds)
    return report, 0 if report['status'] == 'promoted' else 1


def main(argv=None, *, out=None):
    stream = out or sys.stdout
    try:
        raw = list(sys.argv[1:] if argv is None else argv)
        if raw and raw[0].startswith('--') and raw[0] != '--help':
            raw = ['promote'] + raw  # `python3 -m symblic.mica.cli promote --dir ...` names the default command
        result, code = dispatch(parser().parse_args(raw))
    except KeyboardInterrupt:
        result, code = {'ok': False, 'error': {'code': 'interrupted', 'message': 'Interrupted; promotion is '
                        'idempotent and writes its receipt only after every check passes.'}}, 130
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        result, code = {'ok': False, 'error': {'code': getattr(exc, 'code', type(exc).__name__),
                                               'message': str(exc)[:1000]}}, 2
    try:
        payload = json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        payload = '{"ok":false,"error":{"code":"invalid_result","message":"Result is not finite JSON."}}'
        code = 2
    print(payload, file=stream)
    return code


if __name__ == '__main__':
    raise SystemExit(main())

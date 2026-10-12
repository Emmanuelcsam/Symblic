"""Expense hand-off example: pin caller inputs, run a Symblic program, then replay and check its exact output.

What it shows: how a program that embeds Symblic hands one bounded job to a small local model and keeps the result
checkable. The caller supplies trip notes and a catalog of expense items (examples/expense-handoff.json); the
program (examples/expense-handoff.sym) asks the model, for each item separately and with only that item's text,
to return the item's exact source span, and the kernel accepts an answer only when the span, the amount and the
category check out against the caller's catalog. The totals are computed by the kernel, not by the model.

    python3 examples/expense_handoff.py prepare examples/expense-handoff.json --by ollama:qwen3:4b-instruct \
        --dir NEW_JOB_FOLDER                   (no model; prints handoff_sha256, the fingerprint to keep)
    python3 examples/expense_handoff.py run NEW_JOB_FOLDER --expect HANDOFF_SHA256     (asks the model; needs Ollama)
    python3 examples/expense_handoff.py check NEW_JOB_FOLDER --expect HANDOFF_SHA256   (replays the record; no model)

This is demonstration plumbing, not an expense oracle or a new runtime. The .sym program performs all candidate
acceptance and arithmetic. No expected totals or model answers are generated here. SHA fingerprints bind bytes,
not authenticity. Only an `ollama:` applicator is accepted: the example never routes to a cloud model.
Depends on: symblic.kernel (language, execution_pins, grounding, run), symblic.providers.applicators and the
standard-library module `text` (symblic/lang/library/text.sym). Walkthrough: docs/reference/EXPENSE-HANDOFF.md.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import fcntl
import hashlib
import json
import os
import re
import signal
import sys
import tempfile
import threading
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # the repository root
sys.path.insert(0, str(ROOT))
from symblic.kernel import language as S
from symblic.kernel import execution_pins as X
from symblic.kernel import grounding as G
from symblic.kernel.run import Run

VERSION = 1
MAX_BYTES = 2_000_000
PROGRAM = Path(__file__).with_name('expense-handoff.sym')
CATEGORIES = {'meal', 'hotel', 'travel', 'client_meal'}


def raw_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, limit=MAX_BYTES):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Example file exceeds its finite byte limit')
    return raw


def keys(value, wanted):
    if type(value) is not dict or set(value) != set(wanted):
        raise ValueError('Missing or unknown caller/handoff fields')


def caller_inputs(body):
    """Check caller contract structure without deriving any candidate amount."""
    keys(body, ('version', 'source', 'entries', 'policy', 'caller_scope'))
    if type(body['version']) is not int or body['version'] != VERSION:
        raise ValueError('Unknown example version')
    if type(body['caller_scope']) is not str or not 1 <= len(body['caller_scope']) <= 4000:
        raise ValueError('An explicit caller scope is required')
    G.source_ref(body['source'])
    if len(body['source']['text']) > 16000:
        raise ValueError('Example source exceeds 16000 code points')
    entries = body['entries']
    if type(entries) is not list or not 1 <= len(entries) <= 32:
        raise ValueError('Supply 1..32 caller items')
    catalog, regions = [], []
    policy = body['policy']
    keys(policy, ('rates', 'hotel_daily_cap', 'meal_item_cap', 'negative_amounts'))
    if type(policy['negative_amounts']) is not str or policy['negative_amounts'] != 'refuse':
        raise ValueError('This example only implements the explicit negative-amount refusal policy')
    keys(policy['rates'], ('USD', 'JPY'))
    for rate in policy['rates'].values():
        keys(rate, ('numerator', 'denominator'))
        if any(type(v) is not int or not 1 <= v <= 1_000_000 for v in rate.values()):
            raise ValueError('Rates require bounded positive integer numerator/denominator')
    for key in ('hotel_daily_cap', 'meal_item_cap'):
        if type(policy[key]) is not int or not 0 <= policy[key] <= 1_000_000:
            raise ValueError('Caps require bounded nonnegative integer USD amounts')
    for row in entries:
        keys(row, ('id', 'start', 'end', 'label', 'day', 'category', 'currency'))
        if type(row['category']) is not str or type(row['currency']) is not str or row['category'] not in CATEGORIES or row['currency'] not in policy['rates']:
            raise ValueError('Unsupported caller category/currency')
        if type(row['day']) is not str or datetime.date.fromisoformat(row['day']).isoformat() != row['day']:
            raise ValueError('Caller day must be an ISO calendar date')
        span = G.source_span(body['source'], row['start'], row['end'])
        local = G.source_record(row['id'], span['quote'], body['source']['revision'])
        if not 1 <= len(local['text']) <= 512:
            raise ValueError('One caller item must contain 1..512 code points')
        local_span = G.source_span(local, 0, len(local['text']))
        G.field_contract(row['id'], local, labels=[row['label']], region=local_span,
                         separator='\n', prefix=' ', suffix=' ' + row['currency'], currency=row['currency'])
        catalog.append({'id': row['id'], 'span': span})
        regions.append((span['start'], span['end']))
    contract = G.list_contract('trip-items', body['source'], catalog=catalog, require_nonempty=True)
    if not G.verify_items(body['source'], contract, {'contract_sha256': contract['sha256'], 'items': catalog})['accepted']:
        raise ValueError('Caller catalog must contain unique, supported item occurrences')
    ordered = sorted(regions)
    if any(a[1] > b[0] for a, b in pairwise(ordered)):
        raise ValueError('Caller item regions must be disjoint')
    return copy.deepcopy({key: body[key] for key in ('source', 'entries', 'policy')})


def prepare(body, *, by, retries=0):
    if type(by) is not str or not re.fullmatch(r'ollama:[A-Za-z0-9._:/-]+(@[A-Za-z0-9][A-Za-z0-9.-]{0,252}(:[0-9]{1,5})?)?', by):
        raise ValueError('Use one explicit ollama:MODEL[@HOST] route; this example grants no cloud authority')
    if type(retries) is not int or retries not in (0, 1):
        raise ValueError('Example retries must be 0 or 1')
    inputs = caller_inputs(body)
    source = PROGRAM.read_text(encoding='utf-8')
    checked = S.check(source)
    if not checked['ok']:
        raise ValueError('Example program does not parse: ' + str(checked['errors']))
    names = X.REQUIRED_FILES | {'symblic/providers/applicators.py'} | {'symblic/lang/library/text.sym'}
    if 'symblic/providers/ollama_call.py' in X.PYTHON_FILES and (ROOT / 'symblic/providers/ollama_call.py').is_file():
        names |= {'symblic/providers/ollama_call.py'}
    pins = X.build(source, inputs, {name: sha((ROOT / name).read_bytes()) for name in sorted(names)})
    ceiling = len(inputs['entries']) * 2 * (retries + 1)
    options = {'by': 'auto', 'auto_route': {'candidates': [by], 'max_calls': ceiling,
               'repairs': len(inputs['entries']) * 2 * retries, 'allow_cloud': False}, 'retries': retries, 'effort': 'low', 'context': 'none', 'profile': 'verified',
               'coercion': 'strict', 'budget': 24000, 'max_calls': ceiling,
               'max_steps': 200000, 'parallel': 1, 'side_effects': False, 'execution_pins': pins}
    envelope = {'version': VERSION, 'source': source, 'caller': copy.deepcopy(body), 'inputs': inputs,
                'options': options, 'helper_sha256': sha(Path(__file__).read_bytes()),
                'output_binding': 'result', 'encoding': f'symblic-canon-v{S.CANON_VERSION}'}
    return {**envelope, 'sha256': sha(raw_json(envelope))}


def atomic(path, raw):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_job(envelope, folder):
    folder = Path(folder)
    folder.mkdir(mode=0o700, parents=False, exist_ok=False)
    atomic(folder / 'handoff.json', raw_json(envelope))
    return {'ok': True, 'handoff_sha256': envelope['sha256'], 'folder': str(folder),
            'charged_dispatch_ceiling_across_resumes': envelope['options']['max_calls'], 'model_calls': 0}


@contextmanager
def job_lock(folder):
    fd = os.open(Path(folder) / '.handoff.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


class NoModels:
    def call(self, _request):
        return {'ok': False, 'fatal': True, 'refused': True, 'error': 'Offline check: no recorded answer'}


def execute_job(folder, expected_sha, *, applicators=None, replay=False, stop=None):
    """Replay accepted native calls; all source, catalog and field checks run again."""
    folder = Path(folder)
    with job_lock(folder):
        envelope = json.loads(read(folder / 'handoff.json'))
        keys(envelope, ('version', 'source', 'caller', 'inputs', 'options', 'helper_sha256', 'output_binding', 'encoding', 'sha256'))
        body = {key: value for key, value in envelope.items() if key != 'sha256'}
        if envelope['sha256'] != expected_sha or sha(raw_json(body)) != expected_sha:
            raise ValueError('Handoff differs from the caller-retained fingerprint')
        if envelope['helper_sha256'] != sha(Path(__file__).read_bytes()) or envelope['source'] != PROGRAM.read_text(encoding='utf-8'):
            raise ValueError('Example helper/program changed since preparation')
        if envelope['inputs'] != caller_inputs(envelope['caller']):
            raise ValueError('Prepared inputs differ from retained caller contract')
        if envelope['encoding'] != f'symblic-canon-v{S.CANON_VERSION}' or envelope['output_binding'] != 'result':
            raise ValueError('Output contract changed')
        X.validate(envelope['options']['execution_pins'], envelope['source'], envelope['inputs'])
        native = folder / 'native'
        options = copy.deepcopy(envelope['options'])
        options.update(replay=replay, stop=stop or threading.Event())
        if not replay and applicators is None:
            raise ValueError('The host must provide its existing admitted Applicators')
        runner = Run(envelope['source'], inputs=envelope['inputs'], options=options,
                     applicators=NoModels() if replay else applicators, folder=str(native))
        report = runner.execute()
        answer = {'ok': report['status'] == 'done', 'accepted': report['status'] == 'done',
                  'replay': replay, 'handoff_sha256': expected_sha, 'report': report,
                  'charged_dispatch_ceiling_across_resumes': envelope['options']['max_calls']}
        if report.get('determinism_summary') is not None:
            answer['determinism_summary'] = report['determinism_summary']
        if answer['accepted']:
            value = runner.kernel.env.lookup('result').value
            raw = S.canon_json(value).encode('utf-8')
            target = folder / 'artifact.canon'
            receipt = {'handoff_sha256': expected_sha, 'artifact_sha256': sha(raw),
                       'encoding': envelope['encoding'], 'bytes': len(raw)}
            if replay:
                if read(target) != raw or json.loads(read(folder / 'receipt.json', 4096)) != receipt:
                    raise ValueError('Replay output differs from the exact retained artifact/receipt')
            else:
                atomic(target, raw)
                atomic(folder / 'receipt.json', raw_json(receipt))
            answer['artifact'] = {'path': str(target), 'sha256': sha(raw), 'encoding': envelope['encoding'],
                                  'bytes': len(raw), 'checked_by_replay': replay}
        return answer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'check'))
    parser.add_argument('path', help='Caller JSON for prepare; prepared directory for run/check')
    parser.add_argument('--dir', help='New private directory for prepare')
    parser.add_argument('--by', help='Explicit local route for prepare')
    parser.add_argument('--retries', type=int, default=0)
    parser.add_argument('--expect', help='Caller-retained handoff SHA-256, required for run/check')
    parser.add_argument('--agent-json', action='store_true', help='JSON is always emitted on stdout')
    args = parser.parse_args(argv)
    apps, previous = None, {}
    stop = threading.Event()
    try:
        if args.command == 'prepare':
            if not args.dir or not args.by:
                raise ValueError('prepare requires --dir and --by')
            result = write_job(prepare(json.loads(read(args.path)), by=args.by, retries=args.retries), args.dir)
        else:
            if not args.expect or args.by or args.dir or args.retries:
                raise ValueError('run/check require --expect and preserve prepared options')
            if args.command == 'run':
                from symblic.providers import applicators as symblic_apply
                apps = symblic_apply.Applicators(owner_label='operator (expense handoff example)',
                                                run_id=Path(args.path).name)
                for sig in (signal.SIGTERM, signal.SIGINT):
                    previous[sig] = signal.signal(sig, lambda *_: stop.set())
            result = execute_job(args.path, args.expect, applicators=apps, replay=args.command == 'check', stop=stop)
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0 if result['ok'] else 1
    except (OSError, ValueError, S.SymblicError) as exc:
        print(json.dumps({'ok': False, 'accepted': False, 'error': {'kind': getattr(exc, 'kind', 'contract'), 'message': str(exc)}}))
        return 1
    finally:
        stop.set()
        if apps is not None:
            apps.cancel_all()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Small, preregistered diagnostic of semantic contracts and bounded escalation.

Preparation never connects an applicator. Execution requires an existing immutable
plan and a separate --execute invocation. All outcomes, including failures and
unstarted assignments, remain in the denominator. This is not a general benchmark
or evidence that model agreement implies truth.

    python3 tools/scripts/symblic_contract_pilot.py --out DIR            prepare a plan (no model is called)
    python3 tools/scripts/symblic_contract_pilot.py --out DIR --execute  run the prepared plan

The pilot ran once in the original host, with local Ollama models on its worker nodes and a cloud command
line as the fallback; its recorded results are in docs/reference/evidence/2026-10-03-contract-pilot-*.json.
To execute it elsewhere, configure the applicators (symblic/providers/applicators.py) for your own models.
DIR must be outside this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # the repository root (this file is tools/scripts/...)
sys.path.insert(0, str(ROOT))
SOURCE_FILES = ('tools/scripts/symblic_contract_pilot.py', 'symblic/kernel/language.py', 'symblic/kernel/run.py',
                'symblic/kernel/evidence.py', 'symblic/providers/applicators.py', 'symblic/lang/abstraction.py',
                'symblic/adapters/geometry.py', 'symblic/adapters/render.py', 'symblic/kernel/effects.py')


def file_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


IMPORTED_SOURCE = {name: (ROOT / name).read_bytes() for name in SOURCE_FILES}
IMPORTED_FILES = {name: hashlib.sha256(value).hexdigest() for name, value in IMPORTED_SOURCE.items()}

from symblic.kernel import language as S
from symblic.providers import applicators as SA
from symblic.adapters import geometry as symblic_geometry  # noqa: F401
from symblic.lang import abstraction as symblic_lang  # noqa: F401
from symblic.adapters import render as symblic_render  # noqa: F401
from symblic.kernel import run as SR

if file_hashes() != IMPORTED_FILES:
    raise RuntimeError('source changed while importing pilot; restart with a fresh frozen snapshot')

VERSION = 1
ARMS = ('natural', 'typed', 'checked_escalation')
MAX_CALLS = 2
MAX_PROMPT_CHARS = 8000
MAX_REPLY_CHARS = 8192
MAX_SECONDS = 1800
ANSWER_TYPE = 'Record {choice: one of {initial, remaining, seconds, all, any}, value: Number}'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def exact(value):
    """Common independent numeric decoder; booleans and nonfinite numbers fail."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Fraction)):
        raise ValueError('not an exact numeric answer')  # noqa: TRY004 - invalid serialized answer value
    if isinstance(value, str) and not re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:/\d+)?', value.strip()):
        raise ValueError('not an unambiguous numeric literal')
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError('not a finite numeric answer') from exc


def normalize(value):
    """Same scorer for every arm; no substring matching or Symblic coercion."""
    if isinstance(value, str):
        value = json.loads(value, parse_float=str)
    if isinstance(value, dict) and set(value) == {'answer'}:
        value = value['answer']
    if not isinstance(value, dict) or set(value) != {'choice', 'value'}:
        raise ValueError('expected exactly choice and value')
    if not isinstance(value['choice'], str):
        raise ValueError('choice must be text')  # noqa: TRY004 - invalid serialized answer value
    return {'choice': value['choice'], 'value': str(exact(value['value']))}


def reference(item):
    """Independent reference using only Python/Fraction, never the Symblic kernel."""
    p = item['parameters']
    if item['family'] == 'basis':
        value = p['initial'] if p['choice'] == 'initial' else p['initial'] - p['removed']
        return {'choice': p['choice'], 'value': str(Fraction(value))}
    if item['family'] == 'unit':
        return {'choice': 'seconds', 'value': str(Fraction(p['duration']) * p['count'] / p['divisor'])}
    if item['family'] == 'scope':
        predicate = all if p['choice'] == 'all' else any
        count = sum(predicate(x > p['threshold'] for x in row) for row in p['rows'])
        return {'choice': p['choice'], 'value': str(Fraction(count))}
    raise ValueError('unknown task family')


def items(seed, count=6):
    if count not in (6, 9, 12):
        raise ValueError('choose 6, 9 or 12 synthetic diagnostic items')
    rng = random.Random(seed)
    out = []
    for i in range(count // 3):
        initial = rng.randrange(8, 21) * 10
        removed = rng.randrange(1, 5) * 10
        choice = 'initial' if i % 2 == 0 else 'remaining'
        p = {'initial': initial, 'removed': removed, 'choice': choice}
        out.append({'id': f'basis-{i}', 'family': 'basis', 'parameters': p,
                    'question': f'A tank initially contains {initial} litres. {removed} litres are removed. '
                    f'The next instruction removes 25% of the {choice} amount. Identify the percentage '
                    'basis: choice is initial or remaining; value is the litres in that basis BEFORE '
                    'applying 25%, not the amount removed.',
                    'predicate': f'answer.choice = "{choice}" and answer.value = '
                    + (str(initial) if choice == 'initial' else f'({initial} - {removed})')})
        duration = rng.randrange(3, 25) * 25
        pulses = rng.randrange(2, 9)
        p = {'duration': duration, 'count': pulses, 'divisor': 1000}
        out.append({'id': f'unit-{i}', 'family': 'unit', 'parameters': p,
                    'question': f'A device emits {pulses} pulses, each lasting {duration} milliseconds. '
                    'Report the total ON time, excluding gaps, in seconds. choice is seconds and value '
                    'is the exact total. One second is 1000 milliseconds.',
                    'predicate': f'answer.choice = "seconds" and '
                    f'answer.value * 1000 = {duration} * {pulses}'})
        threshold = rng.randrange(2, 8)
        # Deliberately separate all/any; random-only fixtures can accidentally agree.
        rows = [[threshold + 1, threshold + 2], [threshold + 1, threshold - 1],
                [threshold - 1, threshold], [threshold + 3, threshold + 1]]
        rng.shuffle(rows)
        choice = 'all' if i % 2 == 0 else 'any'
        quantifier = 'every reading is' if choice == 'all' else 'at least one reading is'
        p = {'rows': rows, 'threshold': threshold, 'choice': choice}
        qualifies = (f'len([x for x in r if x > {threshold}]) = len(r)' if choice == 'all'
                     else f'len([x for x in r if x > {threshold}]) > 0')
        out.append({'id': f'scope-{i}', 'family': 'scope', 'parameters': p,
                    'question': f'Teams have these reading lists: {json.dumps(rows)}. Count teams for which '
                    f'{quantifier} strictly greater than {threshold}. choice is {choice}; value is the '
                    'number of qualifying teams. Equality does not qualify.',
                    'predicate': f'answer.choice = "{choice}" and answer.value = '
                    f'len([r for r in {json.dumps(rows)} if {qualifies}])'})
    for item in out:
        item['expected'] = reference(item)
    rng.shuffle(out)
    return out


def question(item):
    return item['question'] + (' Return only JSON with exactly choice and value, optionally inside '
                               'an answer object. No explanation. Write exact numbers or fractions '
                               'as numeric literals or strings. Keep the reply under 180 characters.')


def _quoted(text):
    # Symblic strings interpolate braces; protect literal text in the task.
    return json.dumps(text.replace('{', '{{').replace('}', '}}'), ensure_ascii=False)


def program(item, arm, model, fallback, seed):
    if arm == 'natural':
        return ''
    apps = [model, fallback] if arm == 'checked_escalation' else [model]
    by = '[' + ', '.join(_quoted(a) for a in apps) + ']'
    options = f'effort=low, context=none, tools=none, temperature=0, seed={seed}, retries='
    options += '0, route=escalate' if arm == 'checked_escalation' else '1'
    src = f'ask answer: {ANSWER_TYPE} {_quoted(question(item))} by {by} with {options}.\n'
    if arm == 'checked_escalation':
        src += f'ensure {item["predicate"]} else retry.\n'
    return src


def validate_app(spec, *, fallback=False):
    app = S.parse_applicator(spec)
    if fallback:
        if app['engine'] not in ('claude', 'codex', 'agy'):
            raise ValueError('fallback must use an explicitly selected admitted cloud CLI')
    elif app['engine'] != 'ollama' or not app.get('model'):
        raise ValueError('pilot primary must be an explicit local Ollama model')
    if app.get('node') in ('host', 'node-h', 'workstation'):
        raise ValueError('pilot model work stays on eligible worker nodes, excluding node-h')
    return app


def build_plan(seed=20261003, count=6, models=('ollama:llama3.2:1b',), fallback='claude:haiku'):
    if file_hashes() != IMPORTED_FILES:
        raise ValueError('source changed since process import; restart before preregistration')
    if not models or len(models) > 2 or len(set(models)) != len(models):
        raise ValueError('choose one or two distinct small-model specifications')
    for model in models:
        validate_app(model)
    validate_app(fallback, fallback=True)
    tasks = items(seed, count)
    cells = []
    for model in models:
        for task in tasks:
            for arm in ARMS:
                source = program(task, arm, model, fallback, seed)
                checked = S.check(source) if source else {'ok': True}
                if not checked['ok']:
                    raise ValueError(f'invalid generated program: {checked["errors"]}')
                cells.append({'id': digest([model, task['id'], arm])[:16], 'model': model,
                              'item': task['id'], 'family': task['family'], 'arm': arm,
                              'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                              'question_sha256': hashlib.sha256(question(task).encode()).hexdigest()})
    random.Random(seed ^ 0x534D).shuffle(cells)
    plan = {'version': VERSION, 'purpose': 'diagnostic_only_no_general_gain_claim', 'seed': seed,
            'count': count, 'models': list(models), 'fallback': fallback, 'items': tasks, 'cells': cells,
            'max_calls_per_cell': MAX_CALLS, 'max_total_calls': MAX_CALLS * len(cells),
            'max_seconds': MAX_SECONDS, 'max_prompt_chars': MAX_PROMPT_CHARS,
            'max_reply_chars': MAX_REPLY_CHARS, 'kernel': S.kernel_id(), 'files': file_hashes(),
            'source_archive': 'source_snapshot',
            'analysis': {'denominator': 'all_assigned_cells', 'paired_by': ['model', 'item'],
                         'primary': 'first_call_correct', 'secondary': 'final_accepted_correct',
                         'repairs_and_fallback': 'reported_separately', 'independence': 'not_established'},
            'limits': ['Synthetic held-out instances of exposed templates, not a novel-domain holdout.',
                       'Checked arm includes a reference contract and conditional stronger fallback.',
                       'Equal call ceilings do not imply equal consumed calls or identical prompts.',
                       'No confidence or superiority claim from this small diagnostic.',
                       'Reply cap rejects received output; backend generation uses existing admitted limits.']}
    plan['plan_sha256'] = digest(plan)
    return plan


class Ledger:
    def __init__(self, directory):
        self.path = Path(directory) / 'ledger.jsonl'
        self.lock = threading.Lock()

    def append(self, row):
        payload = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + '\n'
        with self.lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

    def rows(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]


def prepare(directory, **kwargs):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    plan = build_plan(**kwargs)
    snapshot = IMPORTED_SOURCE
    path = directory / 'plan.json'
    with path.open('x', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        json.dump(plan, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    for name, value in snapshot.items():
        target = directory / plan['source_archive'] / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open('xb') as stream:
            os.chmod(target, 0o600)
            stream.write(value)
    ledger = Ledger(directory)
    for cell in plan['cells']:
        ledger.append({'event': 'assigned', 'cell': cell['id'], 'plan_sha256': plan['plan_sha256']})
    return plan


def load_plan(directory):
    plan = json.loads((Path(directory) / 'plan.json').read_text())
    if digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan.get('plan_sha256'):
        raise ValueError('frozen plan hash mismatch')
    if (plan.get('version') != VERSION or plan.get('kernel') != S.kernel_id()
            or plan['files'] != file_hashes() or plan['files'] != IMPORTED_FILES):
        raise ValueError('source or runtime changed after preregistration; prepare a new directory')
    archive = Path(directory) / plan['source_archive']
    if {name: hashlib.sha256((archive / name).read_bytes()).hexdigest() for name in plan['files']} != plan['files']:
        raise ValueError('preregistered source archive hash mismatch')
    return plan


class RecordedApps:
    def __init__(self, backend, ledger, cell, stop):
        self.backend, self.ledger, self.cell, self.stop = backend, ledger, cell, stop
        self.replies = []
        self.calls = 0

    def call(self, req):
        if self.stop.is_set():
            return {'ok': False, 'fatal': True, 'error': 'pilot deadline or cancellation'}
        if self.calls >= MAX_CALLS:
            return {'ok': False, 'fatal': True, 'error': 'pilot per-cell call cap'}
        if len(req.get('system', '')) + len(req.get('prompt', '')) > MAX_PROMPT_CHARS:
            return {'ok': False, 'fatal': True, 'error': 'pilot prompt length cap'}
        self.calls += 1
        request = {k: v for k, v in req.items() if k != 'stop'}
        self.ledger.append({'event': 'call_started', 'cell': self.cell['id'], 'number': self.calls,
                            'at_utc': timestamp(),
                            'request_sha256': digest(request), 'request': request})
        start = time.monotonic()
        try:
            result = dict(self.backend.call({**req, 'stop': self.stop}) or {})
        except Exception as exc:  # noqa: BLE001 - every backend failure must remain in the ledger
            result = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
        public = {k: v for k, v in result.items() if k in ('ok', 'json', 'text', 'error', 'fatal',
                                                        'node', 'model', 'ms', 'meta')}
        if len(json.dumps(public, default=str)) > MAX_REPLY_CHARS:
            public = {'ok': False, 'fatal': True, 'error': 'pilot received reply length cap',
                      'original_sha256': digest(public)}
        self.replies.append(public)
        self.ledger.append({'event': 'call_finished', 'cell': self.cell['id'], 'number': self.calls,
                            'at_utc': timestamp(),
                            'elapsed_seconds': round(time.monotonic() - start, 3), 'reply': public})
        return public


def score_reply(reply, expected):
    if not reply or not reply.get('ok'):
        return {'valid': False, 'correct': False, 'answer': None}
    try:
        value = normalize(reply.get('json') if reply.get('json') is not None else reply.get('text', ''))
    except (ValueError, TypeError, json.JSONDecodeError):
        return {'valid': False, 'correct': False, 'answer': None}
    return {'valid': True, 'correct': value == expected, 'answer': value}


def run_cell(cell, item, plan, apps, stop):
    expected = reference(item)
    report = None
    if cell['arm'] == 'natural':
        prompt = question(item)
        for attempt in range(MAX_CALLS):
            reply = apps.call({'app': S.parse_applicator(cell['model']),
                              'system': 'Read the supplied task literally. Return the requested JSON only.',
                              'prompt': prompt, 'schema': None, 'sample': attempt, 'temperature': 0,
                              'seed': plan['seed'], 'effort': 'low', 'tools': 'none', 'stop': stop})
            if score_reply(reply, expected)['valid'] or reply.get('fatal'):
                break
            prompt = question(item) + '\nThe previous reply was not valid JSON in the requested shape. Try once more.'
        final = score_reply(reply, expected)
        status = 'done' if final['valid'] else 'failed'
        error = reply.get('error') if not final['valid'] else None
    else:
        report = SR.Run(cell['source'], applicators=apps,
                        options={'parallel': 1, 'max_calls': MAX_CALLS, 'max_asks': 1,
                                 'stop': stop, 'side_effects': False, 'budget': 2000}).execute()
        value = next((row['value'] for row in report.get('bindings', []) if row['name'] == 'answer'), None)
        final = score_reply({'ok': report['status'] == 'done', 'json': value}, expected)
        status, error = report['status'], report.get('error')
    first = score_reply(apps.replies[0] if apps.replies else None, expected)
    return {'event': 'cell_finished', 'cell': cell['id'], 'item': cell['item'], 'model': cell['model'],
            'family': cell['family'], 'arm': cell['arm'], 'status': status, 'error': error,
            'expected': expected, 'first_pass': first, 'final': final, 'calls': apps.calls,
            'repaired_or_escalated': bool(not first['correct'] and final['correct']),
            'selected': next((row.get('meta', {}).get('selected') for row in (report or {}).get('bindings', [])
                              if row['name'] == 'answer'), None)}


def summarize(plan, rows):
    finished = {r['cell']: r for r in rows if r.get('event') == 'cell_finished'}
    started = {r['cell'] for r in rows if r.get('event') == 'cell_started'}
    result = {'purpose': plan['purpose'], 'plan_sha256': plan['plan_sha256'], 'assigned': len(plan['cells']),
              'finished': len(finished), 'calls': sum(r.get('event') == 'call_started' for r in rows),
              'unknown_after_interruption': sorted((started - set(finished)) |
                                                  {i for i, r in finished.items() if r['status'] == 'uncertain'}),
              'arms': {}, 'limits': plan['limits']}
    for arm in ARMS:
        ids = [c['id'] for c in plan['cells'] if c['arm'] == arm]
        observed = [finished[i] for i in ids if i in finished]
        calls_started = [r for r in rows if r.get('event') == 'call_started' and r['cell'] in ids]
        calls_finished = [r for r in rows if r.get('event') == 'call_finished' and r['cell'] in ids]
        placements = Counter((r['reply'].get('node', 'unreported'), r['reply'].get('model', 'unreported'))
                             for r in calls_finished)
        result['arms'][arm] = {'assigned': len(ids), 'finished': len(observed),
                              'first_pass_correct': sum(r.get('first_pass', {}).get('correct', False) for r in observed),
                              'final_correct': sum(r.get('final', {}).get('correct', False) for r in observed),
                              'false_acceptance': {'count': sum(bool(r.get('final', {}).get('valid'))
                                                             and not r['final']['correct'] for r in observed),
                                                   'assigned': len(ids)},
                              'actual_placements': [{'node': node, 'model': model, 'calls': n}
                                                    for (node, model), n in sorted(placements.items())],
                              'call_started_at_utc': min((r['at_utc'] for r in calls_started), default=None),
                              'call_finished_at_utc': max((r['at_utc'] for r in calls_finished), default=None),
                              'call_elapsed_seconds': round(sum(r['elapsed_seconds'] for r in calls_finished), 3),
                              'calls': sum(r.get('calls', 0) for r in observed),
                              'status': dict(Counter(r['status'] for r in observed))}
    return result


def execute(directory, backend, *, seconds=MAX_SECONDS):
    if not 1 <= seconds <= MAX_SECONDS:
        raise ValueError('deadline must be 1..1800 seconds')
    plan = load_plan(directory)
    ledger = Ledger(directory)
    # Uncertain calls must never be automatically reissued after a disconnect.
    initial = ledger.rows()
    if any(r['event'] != 'assigned' for r in initial):
        raise ValueError('pilot already began; inspect its ledger, do not redispatch uncertain cells')
    expected_ids = {cell['id'] for cell in plan['cells']}
    if (len(initial) != len(expected_ids) or {row['cell'] for row in initial} != expected_ids
            or any(row.get('plan_sha256') != plan['plan_sha256'] for row in initial)):
        raise ValueError('assignment ledger incomplete or inconsistent with preregistration')
    stop = threading.Event()
    timer = threading.Timer(seconds, stop.set)
    timer.daemon = True
    timer.start()
    task_map = {item['id']: item for item in plan['items']}
    finished = set()
    try:
        for cell in plan['cells']:
            if stop.is_set():
                break
            ledger.append({'event': 'cell_started', 'cell': cell['id']})
            apps = RecordedApps(backend, ledger, cell, stop)
            try:
                result = run_cell(cell, task_map[cell['item']], plan, apps, stop)
            except Exception as exc:  # noqa: BLE001 - every assigned cell keeps its failure receipt
                result = {'event': 'cell_finished', 'cell': cell['id'], 'item': cell['item'],
                          'model': cell['model'], 'family': cell['family'], 'arm': cell['arm'],
                          'status': 'failed', 'error': f'{type(exc).__name__}: {exc}', 'calls': apps.calls}
            ledger.append(result)
            finished.add(cell['id'])
    finally:
        stop.set()
        timer.cancel()
        if hasattr(backend, 'cancel_all'):
            try:
                backend.cancel_all()  # only this applicator instance's own live runs
            except Exception as exc:  # noqa: BLE001 - preserve primary outcomes if cleanup fails
                ledger.append({'event': 'cleanup_failed', 'error': type(exc).__name__})
        rows = ledger.rows()
        started = {r['cell'] for r in rows if r['event'] == 'cell_started'}
        call_counts = Counter(r['cell'] for r in rows if r['event'] == 'call_started')
        for cell in plan['cells']:
            if cell['id'] not in finished:
                ledger.append({'event': 'cell_finished', 'cell': cell['id'], 'item': cell['item'],
                               'model': cell['model'], 'family': cell['family'], 'arm': cell['arm'],
                               'status': 'uncertain' if cell['id'] in started else 'not_run',
                               'error': 'deadline or interrupted pilot', 'calls': call_counts[cell['id']]})
    summary = summarize(plan, ledger.rows())
    path = Path(directory) / 'summary.json'
    path.write_text(json.dumps(summary, sort_keys=True, indent=2))
    os.chmod(path, 0o600)
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--execute', action='store_true', help='execute an already prepared immutable plan')
    p.add_argument('--seed', type=int, default=20261003)
    p.add_argument('--items', type=int, default=6, choices=(6, 9, 12))
    p.add_argument('--model', action='append')
    p.add_argument('--fallback', default='claude:haiku')
    args = p.parse_args(argv)
    # CLI output is private. Tests use injected temporary stores directly.
    destination = args.out.expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents:
        p.error('put pilot artifacts outside the served repository')
    if args.execute:
        plan = load_plan(destination)
        SA.install_sigterm()
        backend = SA.Applicators(owner_label='operator (preregistered Symblic contract diagnostic)',
                                run_id=plan['plan_sha256'][:16], allow_web=False,
                                avoid=['node-h', 'host', 'workstation'], thermal=True)
        print(json.dumps(execute(destination, backend), indent=2))
    else:
        plan = prepare(destination, seed=args.seed, count=args.items,
                       models=tuple(args.model or ['ollama:llama3.2:1b']), fallback=args.fallback)
        print(json.dumps({'prepared': str(destination / 'plan.json'), 'plan_sha256': plan['plan_sha256'],
                          'assigned': len(plan['cells']), 'max_calls': plan['max_total_calls'],
                          'models_called': 0}, indent=2))


if __name__ == '__main__':
    main()

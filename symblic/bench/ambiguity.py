"""Ambiguity benchmark: does a model ask for the one missing preference instead of guessing it?

What it is for
    Runs the synthetic intent dataset in data/ambiguity-v1.json (42 cases in 14 families; see
    data/ambiguity-v1.md). Each family has two "ambiguous twins" with byte-identical public text but different
    hidden owner preferences, and one clear control. A model must answer every field, ask for the unresolved
    field(s), or abstain, in a fixed JSON protocol. Four conditions:

        direct         one plain prompt
        typed          the same prompt through a one-statement Symblic `ask` with a declared record type
        clarify        typed; if the model asks, the scripted owner answers the requested fields, then one more call
        oracle_direct  direct, with every owner answer supplied up front (an information control)

    Grading is exact and finite (``grade``): field IDs and typed values, never prose quality.

How a run works
    ``make_plan`` freezes the assignment (cases x applicators x conditions), the call limits and the digests of
    the code and dataset; ``run`` executes each cell's first attempt exactly once and journals every call intent
    before dispatch, so a crash leaves an "uncertain" cell that is never redispatched; ``summarize`` keeps every
    assigned cell in its denominator (done, failed, pending, uncertain, damaged).

Status: measured machinery. The dataset's labels are author-stipulated synthetic intentions, an oracle for these
fixtures and not an external truth measurement. No result for any model is claimed here.

Depends on: ``symblic.kernel.language``/``run`` (typed arm), ``symblic.bench.code_pins``. Run through
``python3 -m symblic.bench.bench --suite ambiguity --ambiguity-apps APP[,APP] --out DIR [--dry-run]``.
No providers, stores or work start on import.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

VERSION = 1
# The published dataset (synthetic; documented in data/ambiguity-v1.md).
DATA = Path(__file__).resolve().parent / 'data' / 'ambiguity-v1.json'
CONDITIONS = ('direct', 'typed', 'clarify', 'oracle_direct')
CALL_LIMITS = {'direct': 1, 'typed': 1, 'clarify': 2, 'oracle_direct': 1}
RESPONSE_TYPE = ('Record {action: one of {answer, clarify, abstain}, '
                 'values: List of Record {field: Text, value: Any} length 0..16, '
                 'questions: List of Text length 0..3}')
INSTRUCTIONS = '''Interpret this synthetic request; do not perform any actions.
Use only the request, context, field definitions and any supplied owner answers.
Return exactly one JSON object with keys action, values, questions.
action is "answer", "clarify", or "abstain".
If every required field is determined, answer with one {"field": NAME, "value": VALUE}
entry per field in values, and questions: []. Preserve the specified JSON types.
If an essential meaning or owner preference is missing, use action: "clarify",
values: [], and questions containing at most three field names needing clarification.
Do not guess the owner's preference. If the task cannot be resolved, use
action: "abstain", values: [], questions: []. No extra keys or commentary.'''
ID = re.compile(r'[a-z][a-z0-9_-]{0,79}\Z')
MAX_REPLY = 65536
# This benchmark's own code (the kernel's registered files are pinned too; see make_plan).
CODE_FILES = ('symblic/bench/bench.py', 'symblic/bench/ambiguity.py', 'symblic/providers/applicators.py')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    """SHA-256 of canonical JSON."""
    return hashlib.sha256(_json(value).encode()).hexdigest()


def equal(a, b):
    """JSON equality with bool/int and every nested type kept apart."""
    return type(a) is type(b) and (all(k in b and equal(v, b[k]) for k, v in a.items()) and len(a) == len(b)
                                  if isinstance(a, dict) else
                                  len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
                                  if isinstance(a, list) else a == b)


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('Duplicate JSON key: ' + key)
        out[key] = value
    return out


def parse_json(text):
    """Strict JSON from a bounded reply: no duplicate keys, no NaN or Infinity."""
    if not isinstance(text, str) or len(text.encode()) > MAX_REPLY:
        raise ValueError('Response is not bounded JSON text')
    return json.loads(text, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))


def _fits(value, field):
    kind = field['type']
    good = ((kind == 'text' and type(value) is str and len(value) <= 4096)
            or (kind == 'integer' and type(value) is int and abs(value) <= 10**15)
            or (kind == 'boolean' and type(value) is bool)
            or (kind == 'text_list' and type(value) is list and len(value) <= 32
                and all(type(x) is str and len(x) <= 4096 for x in value)))
    return good and ('choices' not in field or any(equal(value, x) for x in field['choices']))


def public_case(case):
    """The provider-visible part of a case (request, context, fields); never gold."""
    return {k: case[k] for k in ('request', 'context', 'fields')}


def load_dataset(path=DATA):
    """Read and validate a dataset file; returns (data, sha256 of its bytes)."""
    raw = Path(path).read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError('Dataset exceeds 1 MiB')
    data = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(data, dict) or data.get('version') != VERSION or type(data.get('version')) is not int:
        raise ValueError('Unknown dataset version')
    cases = data.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 512:
        raise ValueError('Dataset needs 1..512 cases')
    ids, families, groups, visible_splits = set(), {}, {}, {}
    for case in cases:
        if set(case) != {'id', 'family', 'domain', 'split', 'public_group', 'request', 'context', 'fields', 'gold'}:
            raise ValueError('Unknown or missing case fields')
        for key in ('id', 'family', 'domain', 'public_group'):
            if not isinstance(case.get(key), str) or not ID.fullmatch(case[key]):
                raise ValueError('Invalid case identity')
        if case['id'] in ids or case.get('split') not in ('dev', 'heldout'):
            raise ValueError('Duplicate case or invalid split')
        ids.add(case['id'])
        if families.setdefault(case['family'], case['split']) != case['split']:
            raise ValueError('Scenario family crosses splits')
        if any(not isinstance(case.get(k), str) or len(case[k]) > 12000 for k in ('request', 'context')):
            raise ValueError('Invalid public text')
        fields = case.get('fields')
        if not isinstance(fields, list) or not 1 <= len(fields) <= 16:
            raise ValueError('A case needs 1..16 fields')
        names = set()
        for field in fields:
            if not isinstance(field, dict) or not ID.fullmatch(str(field.get('name', ''))):
                raise ValueError('Invalid field')
            if not {'name', 'description', 'type'} <= field.keys() or not set(field) <= {'name', 'description', 'type', 'choices'}:
                raise ValueError('Unknown field metadata')
            if field['name'] in names or field.get('type') not in ('text', 'integer', 'boolean', 'text_list'):
                raise ValueError('Duplicate field or unknown type')
            names.add(field['name'])
            if not isinstance(field.get('description'), str) or len(field['description']) > 2000:
                raise ValueError('Invalid field description')
            if 'choices' in field:
                choices = field['choices']
                if not isinstance(choices, list) or not 1 <= len(choices) <= 32:
                    raise ValueError('Invalid choices')
                base = {k: v for k, v in field.items() if k != 'choices'}
                if any(not _fits(x, base) for x in choices) or len({digest(x) for x in choices}) != len(choices):
                    raise ValueError('Ill-typed or duplicate choices')
        gold = case.get('gold', {})
        if not isinstance(gold, dict) or set(gold) != {'values', 'clarify_fields', 'owner_answers'}:
            raise ValueError('Unknown gold fields')
        vals, queries, answers = gold.get('values'), gold.get('clarify_fields'), gold.get('owner_answers')
        if not isinstance(vals, dict) or set(vals) != names or any(not _fits(vals[f['name']], f) for f in fields):
            raise ValueError('Gold must specify every field with exact types')
        if (not isinstance(queries, list) or not all(isinstance(x, str) for x in queries)
                or not 0 <= len(queries) <= 3 or len(set(queries)) != len(queries) or not set(queries) <= names
                or not isinstance(answers, dict) or set(answers) != set(queries)
                or any(not equal(v, vals[k]) for k, v in answers.items())):
            raise ValueError('Invalid owner answer script')
        key = (case['split'], case['family'], digest(public_case(case)))
        if groups.setdefault(case['public_group'], key) != key:
            raise ValueError('A public group must have identical inputs in one family/split')
        if visible_splits.setdefault(key[2], case['split']) != case['split']:
            raise ValueError('Identical public input crosses splits')
    return data, hashlib.sha256(raw).hexdigest()


def prompt(case, answers=None):
    """The exact prompt for a case, optionally with the scripted owner answers."""
    payload = public_case(case)
    if answers is not None:
        payload = {**payload, 'owner_answers': answers}
    return INSTRUCTIONS + '\n\n' + _json(payload)


def grade(case, reply, disclosed=()):
    """Finite exact rubric. Gold is read here, never used to repair a model answer."""
    result = {'protocol_valid': False, 'initial_success': False, 'owner_exact': False,
              'supported_exact': False, 'unsupported_commitment': False, 'abstained': False,
              'requested_fields': [], 'useful_questions': 0, 'unnecessary_questions': 0}
    fields = {f['name']: f for f in case['fields']}
    missing = set(case['gold']['clarify_fields']) - set(disclosed)
    try:
        if type(reply) is not dict or set(reply) != {'action', 'values', 'questions'}:
            raise ValueError('Response needs exactly action, values, questions')
        action, values, questions = reply['action'], reply['values'], reply['questions']
        if type(action) is not str or action not in ('answer', 'clarify', 'abstain'):
            raise ValueError('Invalid action')
        if type(values) is not list or len(values) > 16 or type(questions) is not list or len(questions) > 3:
            raise ValueError('Invalid response lists')
        if any(type(q) is not str or q not in fields for q in questions) or len(set(questions)) != len(questions):
            raise ValueError('Unknown or repeated question field')
        chosen = {}
        for item in values:
            if (type(item) is not dict or set(item) != {'field', 'value'} or type(item['field']) is not str
                    or item['field'] not in fields or item['field'] in chosen
                    or not _fits(item['value'], fields[item['field']])):
                raise ValueError('Unknown, repeated or ill-typed field value')
            chosen[item['field']] = item['value']
        if action == 'answer' and (set(chosen) != set(fields) or questions):
            raise ValueError('An answer needs all fields and no questions')
        if action != 'answer' and values:
            raise ValueError('A non-answer must not commit values')
        if (action == 'clarify' and not questions) or (action == 'abstain' and questions):
            raise ValueError('Invalid question/action combination')
        result.update(protocol_valid=True, action=action, requested_fields=questions,
                      useful_questions=len(set(questions) & missing),
                      unnecessary_questions=len(set(questions) - missing), abstained=action == 'abstain')
        if action == 'answer':
            exact = equal(chosen, case['gold']['values'])
            result.update(owner_exact=exact, supported_exact=exact and not missing,
                          unsupported_commitment=bool(missing), initial_success=exact and not missing)
        elif action == 'clarify':
            result['initial_success'] = bool(missing) and set(questions) == missing
    except (ValueError, TypeError, KeyError) as exc:
        result['error'] = str(exc)
    return result


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as handle:
        os.chmod(tmp, 0o600)
        handle.write(_json(value) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save(path, row):
    row = {k: v for k, v in row.items() if k != 'integrity'}
    _atomic(path, {**row, 'integrity': digest(row)})


def _read_record(path, cell):
    if not path.exists():
        return {'status': 'pending', 'cell': cell['id']}
    try:
        row = json.loads(path.read_text(), object_pairs_hook=_object)
        if not isinstance(row, dict):
            raise ValueError('Record is not an object')  # noqa: TRY004 - corrupt persisted JSON
        integrity = row.pop('integrity')
        if digest(row) != integrity or row['cell'] != cell['id'] or row['condition'] != cell['condition']:
            raise ValueError('Record identity/integrity differs')
        return {**row, 'status': 'uncertain' if row['status'] == 'started' else row['status']}
    except (ValueError, TypeError, KeyError, OSError):
        return {'status': 'damaged', 'cell': cell['id']}


def make_plan(data, dataset_sha256, apps, split='dev', conditions=CONDITIONS, quick=False, avoid=''):
    """Freeze every assignment before any provider exists. `avoid` lists nodes an applicator may not name."""
    from symblic.kernel import language as S
    from symblic.bench import code_pins
    if split not in ('dev', 'heldout') or not apps or len(apps) != len(set(apps)) or len(apps) > 16:
        raise ValueError('Choose a split and 1..16 distinct explicit applicators')
    if not conditions or len(set(conditions)) != len(conditions) or any(c not in CONDITIONS for c in conditions):
        raise ValueError('Unknown or repeated ambiguity condition')
    for app in apps:
        if not isinstance(app, str) or not app or '|' in app:
            raise ValueError('Invalid applicator')
        try:
            parsed = S.parse_applicator(app)
        except S.SymblicError as exc:
            raise ValueError(f'Invalid applicator {app!r}: {exc.message}') from None
        if parsed['engine'] not in ('ollama', 'command', 'fake', 'claude', 'codex', 'agy', 'mistral', 'copilot',
                                    'gemini', 'chatgpt'):
            raise ValueError('This protocol needs individual model applicators, not orchestration or kernel engines')
        if parsed['effort'] not in ('', 'low') or parsed['weight_exact'] != '1':
            raise ValueError('This protocol fixes effort=low and weight=1 across conditions')
        if parsed.get('node') and parsed['node'] in {n.strip() for n in avoid.split(',') if n.strip()}:
            raise ValueError('An applicator explicitly targets an avoided node')
    cases = [c for c in data['cases'] if c['split'] == split]
    if quick:
        first_family = sorted({c['family'] for c in cases})[:1]
        cases = [c for c in cases if c['family'] in first_family]
    if not cases:
        raise ValueError('No cases in this split')
    files = code_pins.kernel_files() | set(CODE_FILES)
    config = {'version': VERSION, 'dataset_sha256': dataset_sha256, 'split': split,
              'apps': list(apps), 'conditions': list(conditions), 'avoid': avoid,
              'case_ids': [c['id'] for c in cases], 'call_limits': CALL_LIMITS,
              'temperature': 0, 'seed': 7, 'effort': 'low', 'tools': 'none',
              'kernel': S.kernel_id(),
              'modules': code_pins.code_pins(files)}
    plan_id = digest(config)
    cells = []
    for case in cases:
        for by in apps:
            for condition in conditions:
                cells.append({'id': digest([plan_id, case['id'], by, condition]), 'case': case['id'],
                              'family': case['family'], 'domain': case['domain'],
                              'public_group': case['public_group'], 'by': by, 'condition': condition,
                              'ambiguous': bool(case['gold']['clarify_fields'])})
    plan = {'config': config, 'id': plan_id, 'cells': cells,
            'maximum_calls': sum(CALL_LIMITS[c['condition']] for c in cells)}
    return {**plan, 'integrity': digest(plan)}


class _Calls:
    def __init__(self, apps, row, path, limit):
        self.apps, self.row, self.path, self.limit = apps, row, path, limit

    def call(self, request):
        if len(self.row['calls']) >= self.limit:
            raise ValueError('Cell call budget exhausted; no extra dispatch')
        req = {**request, 'tools': 'none'}
        material = {k: req.get(k) for k in ('app', 'system', 'prompt', 'schema', 'sample', 'temperature',
                                            'seed', 'effort', 'tools')}
        req['key'] = digest([self.row['cell'], len(self.row['calls']), material])
        attempt = {'request_sha256': digest(material), 'phase': self.row['phase'], 'started': time.time(),
                   'status': 'intent', 'requested_app': req.get('app')}
        self.row['calls'].append(attempt)
        _save(self.path, self.row)  # A crash after here is uncertain, never auto-resent.
        try:
            result = self.apps.call(req)
            if not isinstance(result, dict):
                raise TypeError('Provider returned a non-object')
            attempt.update(status='returned', ok=result.get('ok') is True,
                           node=result.get('node'), model=result.get('model'), engine=result.get('engine'),
                           independence='not_established')
            if len(_json(result).encode()) > MAX_REPLY:
                raise ValueError('Provider response exceeds 64 KiB')
            attempt['response'] = result
            return result
        except Exception as exc:
            attempt.update(status='error', error=f'{type(exc).__name__}: {exc}'[:1000])
            raise
        finally:
            attempt['finished'] = time.time()
            _save(self.path, self.row)


def _decode(result):
    """Same strict raw inner record for every arm, before canonical field dropping.

    A provider may omit original text; duplicate keys lost upstream cannot then be
    detected. That availability is recorded, not a claimed raw-text validation.
    """
    if isinstance(result.get('text'), str) and result['text'].strip():
        raw = parse_json(result['text'])
    elif result.get('json') is not None:
        raw = parse_json(_json(result['json']))
    else:
        raise ValueError('Provider returned no JSON response')
    envelope_keys = {'answer', 'reasoning', 'confidence', 'readings', 'ambiguous'}
    if isinstance(raw, dict) and 'answer' in raw and set(raw) <= envelope_keys:
        raw = raw['answer']
    return raw


def _ask(calls, by, text, typed):
    from symblic.kernel import language as S
    if typed:
        from symblic.kernel import run as SR
        # Payload is data, never interpolated Symblic source (JSON itself contains braces).
        source = (f'given task: Text.\nask response: {RESPONSE_TYPE} "Follow the task response instructions." from task '
                  'with effort=low, retries=0, votes=1, context=none.\n')
        rep = SR.Run(source, {'task': text}, calls, {'by': by, 'max_calls': 1, 'max_asks': 1, 'parallel': 1}).execute()
        if rep['status'] != 'done':
            raise ValueError((rep.get('error') or {}).get('message', 'Typed request failed'))
        binding = next((b for b in rep['bindings'] if b['name'] == 'response'), None)
        if binding is None:
            raise ValueError('Typed request did not bind a response')
        calls.row.setdefault('typed_normalizations', {})[calls.row['phase']] = binding['value']
        result = calls.row['calls'][-1].get('response', {})
        calls.row.setdefault('raw_text_available', {})[calls.row['phase']] = bool(result.get('text'))
        return _decode(result)
    result = calls.call({'app': S.parse_applicator(by), 'system': 'Follow the provided response protocol.',
                         'prompt': text, 'schema': None, 'sample': 0, 'temperature': 0,
                         'seed': 7, 'effort': 'low', 'tools': 'none', 'key': ''})
    if result.get('ok') is not True:
        raise ValueError(str(result.get('error') or 'Provider did not return an answer'))
    calls.row.setdefault('raw_text_available', {})[calls.row['phase']] = bool(result.get('text'))
    return _decode(result)


def execute_cell(cell, case, apps, path):
    """Run one assigned cell exactly once, journaling every call; returns its record."""
    row = {'cell': cell['id'], 'condition': cell['condition'], 'case': cell['case'], 'by': cell['by'],
           'status': 'started', 'phase': 'initial', 'calls': [], 'started': time.time(),
           'initial': None, 'final': None, 'correct': False, 'disclosed_fields': []}
    _save(path, row)
    calls = _Calls(apps, row, path, CALL_LIMITS[cell['condition']])
    condition = cell['condition']
    try:
        supplied = case['gold']['owner_answers'] if condition == 'oracle_direct' else None
        disclosed = set(supplied or {})
        oracle_message = {'provided': supplied, 'already_specified': []} if supplied is not None else None
        response = _ask(calls, cell['by'], prompt(case, oracle_message), condition in ('typed', 'clarify'))
        first = grade(case, response, disclosed)
        row.update(initial=first, initial_response=response, final=first, final_response=response,
                   disclosed_fields=sorted(disclosed))
        if condition == 'clarify' and first['protocol_valid'] and first.get('action') == 'clarify':
            questions = first['requested_fields']
            supplied = {q: case['gold']['owner_answers'][q] for q in questions if q in case['gold']['owner_answers']}
            disclosed = set(supplied)
            # No gold feedback, expected values or grading verdict enters the follow-up.
            followup = {'provided': supplied,
                        'already_specified': [q for q in questions if q not in supplied]}
            row.update(phase='after_questions', disclosed_fields=sorted(disclosed), owner_reply=followup)
            response = _ask(calls, cell['by'], prompt(case, followup), True)
            row.update(final=grade(case, response, disclosed), final_response=response)
        row['correct'] = (row['final']['supported_exact'] if condition in ('clarify', 'oracle_direct')
                          else row['initial']['initial_success'])
        row['status'] = 'done'
    except Exception as exc:  # noqa: BLE001 - failed provider/protocol cells stay in the assigned denominator
        row.update(status='failed', error=f'{type(exc).__name__}: {exc}'[:1000])
    row['finished'] = time.time()
    row['call_attempts'] = len(row['calls'])
    _save(path, row)
    return row


def _load_plan(out):
    plan = json.loads((Path(out) / 'ambiguity-manifest.json').read_text(), object_pairs_hook=_object)
    if not isinstance(plan, dict):
        raise ValueError('Benchmark manifest is not an object')  # noqa: TRY004 - corrupt persisted JSON
    if (plan.get('id') != digest(plan['config'])
            or plan.get('integrity') != digest({k: v for k, v in plan.items() if k != 'integrity'})):
        raise ValueError('Benchmark manifest identity differs')
    expected = {(case, by, cond) for case in plan['config']['case_ids']
                for by in plan['config']['apps'] for cond in plan['config']['conditions']}
    actual = {(c['case'], c['by'], c['condition']) for c in plan['cells']}
    if expected != actual or len(actual) != len(plan['cells']):
        raise ValueError('Benchmark assignments differ')
    for cell in plan['cells']:
        if cell['id'] != digest([plan['id'], cell['case'], cell['by'], cell['condition']]):
            raise ValueError('Benchmark cell identity differs')
    return plan


def run(out, data, plan, apps=None, *, resume=False, dry_run=False, log=print):
    """One first attempt per assigned cell. A resumed intent is never redispatched."""
    import fcntl
    out = Path(out)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(out / 'ambiguity.lock', 'a', encoding='utf-8') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = out / 'ambiguity-manifest.json'
        if path.exists():
            if not equal(_load_plan(out), plan):
                raise ValueError('Existing benchmark has different data, code, models or conditions; use a new folder')
            if not resume and not dry_run:
                raise ValueError('Existing assignment: use --resume; completed/uncertain cells will not be retried')
        else:
            if resume:
                raise ValueError('Cannot resume an unknown assignment: manifest is missing')
            _atomic(path, plan)
        if dry_run:
            log(f'Assigned {len(plan["cells"])} cells; at most {plan["maximum_calls"]} calls; no dispatch.')
        else:
            if apps is None:
                from symblic.providers import applicators as providers
                providers.install_sigterm()
                apps = providers.Applicators(owner_label='symblic ambiguity benchmark', run_id=plan['id'][:16])
            cases = {c['id']: c for c in data['cases']}
            for cell in plan['cells']:
                destination = out / 'ambiguity-cells' / (cell['id'] + '.json')
                if destination.exists():
                    continue
                row = execute_cell(cell, cases[cell['case']], apps, destination)
                log(f'{cell["case"]} {cell["condition"]} {cell["by"]}: {row["status"]}, '
                    f'{row["call_attempts"]} call attempt(s)')
        result = summarize(out)
        _atomic(out / 'ambiguity-summary.json', result)
        (out / 'report.md').write_text(markdown(result), encoding='utf-8')
        return result


def summarize(out):
    """Denominators come from assignments, including failures and unfinished work."""
    from itertools import combinations
    out = Path(out)
    plan = _load_plan(out)
    groups, records = {}, {}
    for cell in plan['cells']:
        row = _read_record(out / 'ambiguity-cells' / (cell['id'] + '.json'), cell)
        key = (cell['by'], cell['condition'])
        g = groups.setdefault(key, {'by': key[0], 'condition': key[1], 'assigned': 0,
                                   'done': 0, 'failed': 0, 'pending': 0, 'uncertain': 0, 'damaged': 0,
                                   'success': 0, 'initial_success': 0, 'supported_exact': 0,
                                   'unsupported_commitments': 0, 'protocol_invalid': 0, 'abstentions': 0,
                                   'call_attempts': 0, 'ambiguous_assigned': 0, 'clear_assigned': 0,
                                   'ambiguous_success': 0, 'clear_success': 0, 'family_counts': {}})
        g['assigned'] += 1
        status = row.get('status')
        if status not in ('done', 'failed', 'pending', 'uncertain', 'damaged'):
            status = 'damaged'
        g[status] += 1
        ok = status == 'done' and row.get('correct') is True
        initial, final = row.get('initial') or {}, row.get('final') or {}
        g['success'] += ok
        g['initial_success'] += initial.get('initial_success') is True
        g['supported_exact'] += final.get('supported_exact') is True
        g['unsupported_commitments'] += initial.get('unsupported_commitment') is True
        g['protocol_invalid'] += status == 'done' and final.get('protocol_valid') is not True
        g['abstentions'] += final.get('abstained') is True
        g['call_attempts'] += len(row.get('calls') or [])
        category = 'ambiguous' if cell['ambiguous'] else 'clear'
        g[category + '_assigned'] += 1
        g[category + '_success'] += ok
        family = g['family_counts'].setdefault(cell['family'], {'assigned': 0, 'success': 0})
        family['assigned'] += 1
        family['success'] += ok
        records[(key, cell['case'])] = {'attempted': status in ('done', 'failed', 'uncertain'), 'ok': ok,
                                       'family': cell['family'], 'public_group': cell['public_group']}
    paired = []
    for left, right in combinations(sorted(groups), 2):
        # Same endpoint only: initial interpretation or resolved owner intent.
        endpoint = lambda k: 'initial' if k[1] in ('direct', 'typed') else 'resolved'
        if endpoint(left) != endpoint(right):
            continue
        pairs = [(a, records[(right, case)]) for (key, case), a in records.items()
                 if key == left and (right, case) in records]
        observed = [(a, b) for a, b in pairs if a['attempted'] and b['attempted']]
        paired.append({'left': list(left), 'right': list(right), 'endpoint': endpoint(left),
                       'assigned_pairs': len(pairs), 'both_attempted': len(observed),
                       'joint_non_success': sum(not a['ok'] and not b['ok'] for a, b in observed),
                       'left_only_success': sum(a['ok'] and not b['ok'] for a, b in observed),
                       'right_only_success': sum(b['ok'] and not a['ok'] for a, b in observed),
                       'families': len({a['family'] for a, b in observed}),
                       'public_groups': len({a['public_group'] for a, b in observed}),
                       'independence': 'not_established'})
    return {'version': VERSION, 'plan_id': plan['id'], 'dataset_sha256': plan['config']['dataset_sha256'],
            'split': plan['config']['split'], 'planned_cells': len(plan['cells']),
            'maximum_calls': plan['maximum_calls'], 'call_limits': plan['config']['call_limits'],
            'groups': list(groups.values()), 'paired': paired,
            'limits': ['Synthetic author-stipulated labels, not external factual ground truth.',
                       'Published heldout is separate from prompt development, not proven absent from model training.',
                       'Field selection is scored; natural-language question quality is not.',
                       'Clarify receives requested owner information; oracle_direct receives all owner answers upfront.',
                       'Conditions have different information and call budgets; this is not an isolated syntax treatment.',
                       'Identical-public owner twins and scenario families are dependent observations.',
                       'An interrupted intent consumes a call attempt and is not automatically redispatched.']}


def markdown(summary):
    """The Markdown report of a summary."""
    lines = ['# Symblic ambiguity benchmark', '',
             (f'Split: {summary["split"]}. Assigned cells: {summary["planned_cells"]}. '
              f'Maximum provider calls: {summary["maximum_calls"]}.'), '',
             f'Plan: `{summary["plan_id"]}`. Dataset: `{summary["dataset_sha256"]}`.', '',
             ('Direct/typed success means a correct explicit answer OR exactly the necessary clarification fields. '
             'Clarify/oracle_direct success means a fully supported exact final specification. '
             'Never compare these two endpoints as one accuracy score.'), '',
             ('All assigned cases remain in each denominator. Failed, pending, damaged and uncertain cells are '
              'reported separately. No model result is inferred from an offline fixture.'), '',
             '| Applicator | Condition | Success / assigned | Done | Failed | Pending | Uncertain | Damaged | Calls |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for g in summary['groups']:
        app = g['by'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f'| {app} | {g["condition"]} | {g["success"]}/{g["assigned"]} | {g["done"]} | '
                     f'{g["failed"]} | {g["pending"]} | {g["uncertain"]} | {g["damaged"]} | {g["call_attempts"]} |')
    lines += ['', ('The JSON summary also records clear controls, ambiguous cases, initial decisions, unsupported '
                   'commitments, exact final results, family counts and paired shared non-successes.'), '']
    lines += ['- ' + limit for limit in summary['limits']]
    return '\n'.join(lines) + '\n'


def main(args):
    """Entry point called only by the ambiguity-only branch of the bench.py command line."""
    out = Path(args.out).expanduser().resolve()
    if args.report_only:
        result = summarize(out)
        _atomic(out / 'ambiguity-summary.json', result)
        (out / 'report.md').write_text(markdown(result), encoding='utf-8')
        print(markdown(result))
        return 0
    if args.retry:
        raise ValueError('Ambiguity keeps first attempts; use a new preregistered run instead of --retry')
    data, sha = load_dataset(args.ambiguity_data)
    apps = [x.strip() for x in args.ambiguity_apps.split(',') if x.strip()]
    conditions = [x.strip() for x in args.ambiguity_conditions.split(',') if x.strip()]
    plan = make_plan(data, sha, apps, args.ambiguity_split, conditions, args.quick, args.avoid)
    result = run(out, data, plan, resume=args.resume, dry_run=args.dry_run)
    print(markdown(result))
    return 0

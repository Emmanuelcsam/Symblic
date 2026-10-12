"""Matched evaluation: the same tasks asked directly and through a typed Symblic capsule, under frozen controls.

What it is for
    To compare "ask the model in plain text" with "ask through a verified one-statement Symblic program" without
    giving either arm an advantage. A manifest (see data/matched-example-v1.json) declares the cases, the arms
    (direct, typed), the model schedule (primary/fallback calls), feedback policy, split and repetitions.
    ``freeze`` validates it and fixes every assignment and its counterbalanced order before any provider exists;
    ``MatchedBench.run`` executes the never-started assignments through injected applicators and writes durable
    dispatch receipts; ``summary``/``markdown`` report exact, denominator-preserving results
    (scoring rules live in eval_protocol.py).

Rules it enforces
    * One typed decision per case, not arbitrary multistep programs. Gold stays evaluator-side; contract repair
      never asks whether an answer is correct (feedback is "none" or "contract_only").
    * Both arms carry the byte-identical task text: the direct prompt starts with it and the typed capsule
      receives it as a runtime input, never as program source text.
    * Every dispatch is journaled (intent, then result) before the next; an interrupted intent is "uncertain",
      never retried automatically; a damaged receipt damages only its own cell.
    * Version 1 experiments remain readable; they are reported as version 1, never rerun.

Status: measured machinery (the protocol and its receipts are tested with fake applicators). No result about
any particular model is claimed here.

Depends on: ``symblic.kernel.language``/``run``/``profiles`` (the typed arm), ``symblic.bench.eval_protocol``
(plans and scoring), ``symblic.bench.code_pins`` (implementation digests). Run through
``python3 -m symblic.bench.bench --suite matched --matched-manifest FILE --out DIR``; only that CLI constructs
real applicators (symblic.providers.applicators). Importing, freezing and reporting are inert.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time

from symblic.kernel import language as S
from symblic.bench import eval_protocol as E
from symblic.kernel import profiles as P
from symblic.kernel import run as SR
from symblic.bench import code_pins

VERSION = 2                    # frozen experiment protocol written by this runner
READABLE_VERSIONS = (1, 2)     # frozen experiments that still verify and report
MANIFEST_VERSION = 1           # manifest format; order_seed is an optional addition
KINDS = ('direct', 'typed')
DIRECT_SYSTEM = 'Answer the question directly and correctly.'
TASK_INPUT = 'task'
SNIPPET = 4000                 # characters of an envelope-violating reply kept as evidence
FEEDBACK = 'The previous response violated the declared output format or type. Return the exact requested shape.'
FORMAT = ('Return one JSON object with an "answer" field and optional string "reasoning". '
          'No other fields, markdown, or surrounding prose. To abstain, return {"abstain":true}.')
_INTENT_KEYS = ('model', 'role', 'feedback_exposed', 'request_sha256', 'information_sha256', 'dispatched_at_ms')


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle, object_pairs_hook=E._pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def _write(path, value, *, exclusive=False):
    """Private, fsynced files. Exclusive intent records prevent duplicate execution."""
    path = Path(path)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n'
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        temp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
        with open(temp, 'w', encoding='utf-8') as handle:
            os.chmod(temp, 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)


def _event(path, value):
    with open(path, 'a', encoding='utf-8') as handle:
        os.chmod(path, 0o600)
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def _text(value, limit):
    """Bounded, UTF-8-encodable text from provider data (lone surrogates become escapes)."""
    text = value if type(value) is str else str(value)
    return text.encode('utf-8', 'backslashreplace').decode('utf-8')[:limit]


def _typed_source(type_text):
    """The exact program the typed arm runs; the task arrives only as the input TASK_INPUT."""
    return 'given ' + TASK_INPUT + ': Any.\nask answer: ' + type_text + ' "{' + TASK_INPUT + '}".\n'


def _type(type_text):
    """Validate a declared type in its real position: the typed arm's own source.

    The type must not end, comment out or extend the ask (statements, from/by/with
    options, instruction text), so the instruction stays exactly the task input.
    """
    if type(type_text) is not str or not type_text or len(type_text) > 4000:
        raise E.ProtocolError('Every public case needs a bounded Symblic type')
    try:
        program = S.parse(_typed_source(type_text), execution_profile='verified')
    except S.SymblicError as exc:
        raise E.ProtocolError('Invalid output type in the typed source: ' + exc.message) from exc
    except RecursionError as exc:
        raise E.ProtocolError('Output type nests too deeply') from exc
    statements = program['statements']
    given, ask = statements if len(statements) == 2 else (None, None)
    if (given is None or given.k != 'given' or given.name != TASK_INPUT or given.type != {'k': 'any'}
            or given.default is not None or ask.k != 'ask' or ask.name != 'answer' or ask.each is not None
            or ask.sources or ask.options or len(ask.parts) != 1 or not isinstance(ask.parts[0], S.Node)
            or ask.parts[0].k != 'name' or ask.parts[0].get('name') != TASK_INPUT):
        raise E.ProtocolError('The output type changes the typed source beyond one typed ask of the task input')
    try:
        ty = S.resolve_type(ask.type, {})
    except S.SymblicError as exc:
        raise E.ProtocolError('Invalid output type in the typed source: ' + exc.message) from exc

    def supported(node):
        if node['k'] not in ('int', 'number', 'bool', 'text', 'enum', 'list', 'record'):
            raise E.ProtocolError('Matched v1 supports exact JSON scalar/list/record types; unsupported ' + node['k'])
        if node['k'] == 'list':
            supported(node['of'])
        elif node['k'] == 'record':
            for _, child in node['fields']:
                supported(child)
    supported(ty)
    return ty


def _task_text(public, feedback):
    """The task information both arms carry, byte for byte (question, format, feedback, context)."""
    text = public['question'] + '\n' + FORMAT
    if feedback:
        text += '\nCONTRACT FEEDBACK: ' + FEEDBACK
    if 'context' in public:
        text += '\nTASK CONTEXT JSON:\n' + json.dumps(public['context'], ensure_ascii=False, sort_keys=True)
    return text


def _bind_task(task):
    """Refuse any runtime normalization: the typed instruction must equal the direct text."""
    value = S.coerce(task, {'k': 'any'}, TASK_INPUT)
    if type(value) is not str or value != task or S.show(value) != task:
        raise E.ProtocolError('The verified runtime would not carry the task text unchanged')
    return value


def _validate_value(value, ty):
    """Gold-free shape validation: no numeric strings, rounding, omission or retyping."""
    def shape(raw, node):
        kind = node['k']
        allowed = {'int': (int,), 'number': (int, float), 'bool': (bool,), 'text': (str,),
                   'enum': (str,), 'list': (list,), 'record': (dict,)}[kind]
        if type(raw) not in allowed:
            raise E.ProtocolError('Answer does not have the declared exact JSON type')
        if kind == 'record':
            fields = dict(node['fields'])
            if set(raw) != set(fields):
                raise E.ProtocolError('Record fields do not match the declared exact shape')
            for name, child in fields.items():
                shape(raw[name], child)
        elif kind == 'list':
            for child in raw:
                shape(child, node['of'])
    E.digest(value)
    shape(value, ty)
    receipt = {}
    canonical = P.coerce(value, ty, policy='strict', receipt=receipt)
    if S.canon_json(canonical) != S.canon_json(S.from_json(value)):
        raise E.ProtocolError('Answer requires a value-changing canonicalization')
    return canonical


# The files whose exact bytes a frozen experiment records (a change refuses to resume an old experiment).
IMPLEMENTATION_FILES = ('symblic/bench/matched.py', 'symblic/bench/eval_protocol.py', 'symblic/kernel/language.py',
                        'symblic/kernel/run.py', 'symblic/kernel/profiles.py', 'symblic/lang/abstraction.py')


def _implementation():
    """{'kernel': kernel id, 'files': {path: sha256}} of the code this runner's results depend on."""
    return {'kernel': S.kernel_id(), 'files': code_pins.code_pins(IMPLEMENTATION_FILES)}


def freeze(manifest):
    """Validate and hash a complete experiment before any provider can be constructed.

    Optional order_seed (default 0) reproducibly fixes the counterbalanced arm order.
    """
    E._keys(manifest, ('version', 'cases', 'arms', 'model', 'schedule', 'feedback', 'split', 'repetitions'),
            ('exposures', 'spec_labor', 'max_prompt_characters', 'order_seed'))
    if type(manifest['version']) is not int or manifest['version'] != MANIFEST_VERSION:
        raise E.ProtocolError('Unsupported matched experiment version')
    if manifest['feedback'] not in ('none', 'contract_only'):
        raise E.ProtocolError('Feedback is none or contract_only; gold feedback is forbidden')
    schedule = manifest['schedule']
    if type(schedule) is not list or not 1 <= len(schedule) <= 100:
        raise E.ProtocolError('Declare 1..100 dispatches per assignment')
    for step in schedule:
        E._keys(step, ('model', 'role'))
        if step['role'] not in ('primary', 'fallback'):
            raise E.ProtocolError('Schedule role must be primary or fallback')
    if schedule[0]['role'] != 'primary':
        raise E.ProtocolError('Schedule must start with a primary model')
    E._keys(manifest['model'], ('primary', 'fallback', 'stronger_fallback', 'settings'))
    settings = manifest['model']['settings']
    E._keys(settings, ('temperature', 'seed', 'effort'))
    if type(settings['temperature']) not in (int, float) or not 0 <= settings['temperature'] <= 2:
        raise E.ProtocolError('Temperature must be 0..2')
    if type(settings['seed']) is not int or not 0 <= settings['seed'] < 2**31:
        raise E.ProtocolError('Seed must be an integer in 0..2^31-1')
    if settings['effort'] not in ('low', 'medium'):
        raise E.ProtocolError('Matched one-call capsule supports low/medium effort')
    ceiling = manifest.get('max_prompt_characters', 32000)
    if type(ceiling) is not int or not 1000 <= ceiling <= 1_000_000:
        raise E.ProtocolError('Prompt ceiling must be 1000..1000000 characters')
    order_seed = manifest.get('order_seed', 0)
    if type(order_seed) is not int or not 0 <= order_seed < 2**31:
        raise E.ProtocolError('order_seed must be an integer in 0..2^31-1')
    E._cases(manifest['cases'])
    for case in manifest['cases']:
        public = case['input']
        E._keys(public, ('question', 'type'), ('context',))
        if type(public['question']) is not str or not public['question'].strip():
            raise E.ProtocolError('Case question must be nonempty text')
        ty = _type(public['type'])
        for feedback in (False, True):
            _bind_task(_task_text(public, feedback))
        _validate_value(case['rubric']['expected'], ty)
        if case['rubric']['mode'] == 'exact_text' and ty['k'] != 'text':
            raise E.ProtocolError('Exact-text rubric requires Text output type')
    if type(manifest['arms']) is not list or not 1 <= len(manifest['arms']) <= 20:
        raise E.ProtocolError('Declare 1..20 direct/typed arms')
    controls = {
        'model': manifest['model'],
        'information': {'public_cases': {c['id']: E.digest(c['input']) for c in manifest['cases']},
                        'output_format': FORMAT, 'gold': 'evaluator_only', 'examples': [],
                        'task_delivery': 'identical task text: direct prompt prefix; verified runtime input ' + TASK_INPUT,
                        'output_type': 'canonical Symblic type label'},
        'budget': {'provider_calls': len(schedule), 'max_prompt_characters': ceiling,
                   'schedule_sha256': E.digest(schedule), 'stop_policy': 'first_contract_valid_or_abstain'},
        'feedback': {'policy': manifest['feedback'], 'content': FEEDBACK if manifest['feedback'] != 'none' else '',
                     'gold_visible': False},
        'validator': {'id': 'matched-exact-json-shape-v1', 'source_sha256': _implementation()['files']['symblic/bench/matched.py'],
                      'oracle': 'evaluator_only', 'coercion': 'identity_preserving', 'output_format': FORMAT},
    }
    arms = []
    for arm in manifest['arms']:
        E._keys(arm, ('id', 'treatment'))
        if arm['treatment'] not in KINDS:
            raise E.ProtocolError('Treatment must be direct or typed')
        arms.append(E.make_arm(arm['id'], arm['treatment'], **controls))
    for step in schedule:
        if step['model'] not in manifest['model'][step['role']]:
            raise E.ProtocolError('Scheduled model is not declared in its role')
        app = S.parse_applicator(step['model'])
        if app['engine'] in ('council', 'auto', 'kernel'):
            raise E.ProtocolError('Use explicit single-applicator models; composite or automatic dispatch is not measured by this runner')
        if S.app_label(app) != step['model'] or app.get('effort') or app.get('weight', 1) != 1:
            raise E.ProtocolError('Use canonical model IDs; settings/weights belong in the explicit controls')
    exposures = list(manifest.get('exposures', []))
    exposures += [{'purpose': 'prompt', 'content': 'input', 'case_id': c['id'], 'target_case_id': c['id']}
                  for c in manifest['cases'] if c['split'] == manifest['split']]
    plan = E.make_plan(manifest['cases'], arms, split=manifest['split'],
                       repetitions=manifest['repetitions'], exposures=exposures, order_seed=order_seed)
    E.summarize(plan, [], spec_labor=manifest.get('spec_labor', []))
    body = {'version': VERSION, 'manifest': copy.deepcopy(manifest), 'plan': plan,
            'implementation': _implementation()}
    return {'id': E.digest(body), **body}


def _check_frozen(frozen):
    E._keys(frozen, ('id', 'version', 'manifest', 'plan', 'implementation'))
    if (type(frozen['version']) is not int or frozen['version'] not in READABLE_VERSIONS or
            E.digest({k: v for k, v in frozen.items() if k != 'id'}) != frozen['id']):
        raise E.ProtocolError('Frozen experiment changed')
    E._check_plan(frozen['plan'])
    if (frozen['version'] == 1) != (frozen['plan']['version'] == 1):
        raise E.ProtocolError('Frozen experiment and plan versions disagree')
    return frozen


def _schema(ty):
    return {'oneOf': [
        {'type': 'object', 'properties': {'answer': S.json_schema(ty), 'reasoning': {'type': 'string'}},
         'required': ['answer'], 'additionalProperties': False},
        {'type': 'object', 'properties': {'abstain': {'const': True}}, 'required': ['abstain'],
         'additionalProperties': False}]}


def _envelope_violation(raw, error):
    """A reply outside the answer envelope: kept as bounded text, malformed in every rubric mode."""
    if len(raw) > SNIPPET:
        digest = hashlib.sha256(raw.encode('utf-8', 'backslashreplace')).hexdigest()
        error += f' (reply of {len(raw)} characters, sha256 {digest}; first {SNIPPET} kept)'
    return {'status': 'answered', 'answer': _text(raw, SNIPPET), 'encoding': 'invalid_envelope',
            'contract_accept': False, 'error': error}, None


def _reply(reply, ty, encoding):
    """Translate an Applicator reply without fuzzy extraction or gold access.

    Anything that is not exactly one envelope (unparseable or oversized text, extra or
    missing fields, non-text reasoning) is an envelope violation, whatever the rubric.
    A well-formed envelope whose value breaks the declared type keeps its value.
    """
    if type(reply) is not dict:
        return {'status': 'error', 'contract_accept': None, 'error': 'Provider returned no reply object'}, None
    if reply.get('abstained') is True:
        return {'status': 'abstained', 'contract_accept': None}, None
    if not reply.get('ok'):
        return {'status': 'refused' if reply.get('refused') is True else 'error', 'contract_accept': None,
                'error': _text(reply.get('error') or 'Provider did not answer', 2000)}, None
    # Prefer exact raw text when present; parsed JSON cannot reveal duplicate keys.
    raw = reply.get('text')
    if type(raw) is str and raw.strip():
        if len(raw.encode('utf-8', errors='replace')) > E.MAX_JSON_BYTES:
            return _envelope_violation(raw, 'Reply exceeds the evaluation size limit')
        try:
            obj = json.loads(raw, object_pairs_hook=E._pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        except (ValueError, RecursionError):
            return _envelope_violation(raw, 'Expected one strict JSON envelope')
    else:
        raw, obj = None, reply.get('json')
    try:
        E.digest(obj)
    except (ValueError, TypeError, RecursionError):
        return _envelope_violation(raw if raw is not None else repr(obj), 'Invalid answer envelope')
    if E.exact_equal(obj, {'abstain': True}):
        return {'status': 'abstained', 'contract_accept': None}, None
    if (type(obj) is not dict or 'answer' not in obj or set(obj) - {'answer', 'reasoning'}
            or ('reasoning' in obj and type(obj['reasoning']) is not str)):
        shown = raw if raw is not None else json.dumps(obj, ensure_ascii=False, sort_keys=True)
        return _envelope_violation(shown, 'Expected the declared answer envelope')
    value = obj['answer']
    attempt = {'status': 'answered', 'answer': value, 'encoding': encoding, 'contract_accept': False}
    try:
        canonical = _validate_value(value, ty)
    except (ValueError, S.SymblicError) as exc:
        return {**attempt, 'error': _text(exc, 2000)}, None
    return {**attempt, 'contract_accept': True}, canonical


def _usage(reply, elapsed):
    result = {'latency_ms': max(0, round(elapsed * 1000))}
    observed = reply.get('usage', {}) if isinstance(reply, dict) else {}
    if isinstance(reply, dict) and reply.get('cached') is True:
        return result  # cached historical token/currency usage is not charged again
    if isinstance(observed, dict):
        for key in ('input_tokens', 'output_tokens', 'usd'):
            if key in observed:
                try:
                    result[key] = E._number(observed[key], integer=key.endswith('tokens'))
                except E.ProtocolError:
                    pass               # unknown is not zero; invalid provider accounting is not invented
    return result


class MatchedBench:
    """Injected Applicators + frozen plan. Resume runs only never-started assignments."""
    def __init__(self, out, manifest=None, *, apps=None, resume=False):
        self.out, self.apps = Path(out), apps
        self.out.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.out / 'matched-plan.json'
        if path.exists():
            if not resume:
                raise E.ProtocolError('Experiment already exists; use resume/report without rewriting it')
            self.frozen = _check_frozen(_read(path))
            if manifest is not None and not E.exact_equal(manifest, self.frozen['manifest']):
                raise E.ProtocolError('Manifest changed after assignment')
        else:
            if manifest is None:
                raise E.ProtocolError('A manifest is required to freeze a new experiment')
            self.frozen = freeze(manifest)
            _write(path, self.frozen, exclusive=True)
        self.plan = self.frozen['plan']
        self.manifest = self.frozen['manifest']
        self.cells = self.out / 'matched-cells'
        self.cells.mkdir(exist_ok=True, mode=0o700)
        self.cases = {c['id']: c for c in self.plan['cases']}
        self.arms = {a['id']: a for a in self.plan['arms']}

    def _one(self, assignment, step, public, encoding, feedback, event_path, attempts):
        ty = _type(public['type'])
        settings = self.manifest['model']['settings']
        ordinal = len(attempts) + 1
        seed = (settings['seed'] + assignment['repeat']) % (2**31)
        canonical, seen, faults = [None], [False], []
        task = _task_text(public, feedback)
        typed = self.arms[assignment['arm_id']]['treatment'] == 'typed'
        # The exact text each treatment must carry: the whole direct prompt, or the
        # verified capsule's statement quoting the task input as its instruction.
        carried = S.statement_source('answer', ty, task) if typed else task + '\nOUTPUT TYPE: ' + S.type_label(ty)
        owner = self

        class Capture:
            def call(self, req):
                try:
                    return self.dispatch(req)
                except Exception as exc:
                    faults.append(exc)   # a harness fault, never a model outcome
                    raise

            def dispatch(self, req):
                if seen[0]:
                    raise E.ProtocolError('One scheduled dispatch cannot create additional provider calls')
                seen[0] = True
                actual = dict(req)
                actual.update(schema=_schema(ty), sample=0, temperature=settings['temperature'], seed=seed,
                              effort=settings['effort'], tools='none')
                if S.app_label(actual['app']) != step['model']:
                    raise E.ProtocolError('Runtime requested an undeclared model')
                if carried not in actual['prompt']:
                    raise E.ProtocolError('The request does not carry the exact task text')
                key_fields = {k: actual[k] for k in ('system', 'prompt', 'schema', 'sample', 'temperature', 'seed', 'effort', 'tools')}
                key_fields['model'] = step['model']
                size = len(actual['system']) + len(actual['prompt']) + len(json.dumps(actual['schema']))
                if size > owner.manifest.get('max_prompt_characters', 32000):
                    raise E.ProtocolError('Matched prompt character ceiling exceeded before dispatch')
                request_hash = E.digest(key_fields)
                actual['key'] = request_hash
                intent = {'ordinal': ordinal, 'model': step['model'], 'role': step['role'],
                          'feedback_exposed': feedback, 'request_sha256': request_hash,
                          'information_sha256': hashlib.sha256(task.encode('utf-8')).hexdigest(),
                          'dispatched_at_ms': time.time_ns() // 1_000_000}
                _event(event_path, {'kind': 'dispatch_intent', **intent})
                started = time.monotonic()
                try:
                    reply = owner.apps.call(actual)
                except Exception as exc:  # a failed dispatch remains a counted attempt
                    reply = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}
                response, canonical[0] = _reply(reply, ty, encoding)
                attempt = {k: v for k, v in intent.items() if k != 'ordinal'}
                attempt.update(response, usage=_usage(reply, time.monotonic() - started))
                if isinstance(reply, dict) and reply.get('cached') is True:
                    attempt['cached'] = True
                if isinstance(reply, dict) and type(reply.get('model')) is str and _text(reply['model'], 200).strip():
                    attempt['observed_model'] = _text(reply['model'], 200)
                _event(event_path, {'kind': 'dispatch_result', 'ordinal': ordinal, 'attempt': attempt})
                attempts.append(attempt)
                if attempt['contract_accept'] is True:
                    return {'ok': True, 'json': {'answer': attempt['answer']}}
                return {'ok': False, 'fatal': True, 'refused': attempt['status'] == 'refused',
                        'error': attempt.get('error', attempt['status'])}

        cap = Capture()
        if not typed:
            cap.call({'app': S.parse_applicator(step['model']), 'system': DIRECT_SYSTEM, 'prompt': carried})
            return attempts[-1]['contract_accept'] is True
        run = SR.Run(_typed_source(public['type']), inputs={TASK_INPUT: task}, applicators=cap, options={
            'profile': 'verified', 'by': step['model'], 'parallel': 1, 'max_calls': 1, 'max_asks': 1,
            'votes': 1, 'retries': 0, 'effort': settings['effort'], 'temperature': settings['temperature'],
            'seed': seed, 'budget': self.manifest.get('max_prompt_characters', 32000), 'side_effects': False})
        report = run.execute()
        if faults:
            raise faults[0]
        if not seen[0]:
            raise E.ProtocolError('Verified runtime failed before dispatch: ' + _text(report.get('error'), 400))
        accepted = attempts[-1]['contract_accept'] is True
        binding = next((b for b in report['bindings'] if b['name'] == 'answer'), None) \
            if report['status'] == 'done' else None
        bound = bool(binding and canonical[0] is not None and binding['hash'] == S.fingerprint(canonical[0]))
        if accepted != bound:
            raise E.ProtocolError('Verified runtime and the shared validator disagree about this answer')
        return bound

    def run(self):
        """Execute every never-started assignment in its frozen order; returns the report summary."""
        if self.apps is None:
            raise E.ProtocolError('Execution requires explicitly injected Applicators')
        if self.frozen['version'] != VERSION or self.frozen['implementation'] != _implementation():
            raise E.ProtocolError('Implementation changed after assignment; report existing results or freeze a new experiment')
        for assignment in self.plan['assignments']:      # the frozen, counterbalanced dispatch order
            folder = self.cells / assignment['id']
            folder.mkdir(exist_ok=True, mode=0o700)
            try:
                _write(folder / 'started.json', {'assignment': assignment, 'experiment_id': self.frozen['id']}, exclusive=True)
            except FileExistsError:
                continue               # complete AND uncertain attempts are never silently retried
            attempts, selected, status = [], None, 'failed'
            case = self.cases[assignment['case_id']]
            public = E.public_case(case)
            encoding = 'text' if case['rubric']['mode'] == 'exact_text' else 'json_value'
            try:
                for step in self.manifest['schedule']:
                    feedback = bool(attempts and attempts[-1]['contract_accept'] is False and
                                    self.manifest['feedback'] == 'contract_only')
                    accepted = self._one(assignment, step, public, encoding, feedback, folder / 'events.jsonl', attempts)
                    if accepted or (attempts and attempts[-1]['status'] == 'abstained'):
                        selected, status = len(attempts), 'complete'
                        break
            except Exception as exc:
                # The harness, not the model, ended this cell; its dispatches still count.
                status = 'harness_failed'
                _write(folder / 'failure.json', {'type': type(exc).__name__, 'message': _text(exc, 2000)})
            try:
                record = E.make_record(self.plan, assignment['id'], attempts, status=status, selected=selected,
                                       agreement_attempts=list(range(1, len(attempts) + 1)))
            except E.ProtocolError as exc:   # e.g. an oversized receipt: this cell only stays unresolved
                _write(folder / 'failure.json', {'type': 'ReceiptError', 'message': _text(exc, 2000)})
                continue
            _write(folder / 'receipt.json', record, exclusive=True)
        return self.report()

    def _journal(self, folder, assignment):
        start = _read(folder / 'started.json')
        if not E.exact_equal(start, {'assignment': assignment, 'experiment_id': self.frozen['id']}):
            raise E.ProtocolError('Started assignment identity changed')
        intents, results = {}, {}
        path = folder / 'events.jsonl'
        for line in path.read_text(encoding='utf-8').splitlines() if path.exists() else []:
            event = json.loads(line, object_pairs_hook=E._pairs)
            if type(event) is not dict:
                raise E.ProtocolError('Invalid dispatch journal event')
            index = event.get('ordinal')
            if type(index) is not int or not 1 <= index <= len(self.manifest['schedule']):
                raise E.ProtocolError('Invalid dispatch ordinal')
            if event.get('kind') == 'dispatch_intent':
                E._keys(event, ('kind', 'ordinal', 'model', 'role', 'feedback_exposed', 'request_sha256'),
                        ('information_sha256', 'dispatched_at_ms'))
                if index != len(intents) + 1 or (index > 1 and index - 1 not in results):
                    raise E.ProtocolError('Broken dispatch intent order')
                step = self.manifest['schedule'][index - 1]
                if event['model'] != step['model'] or event['role'] != step['role']:
                    raise E.ProtocolError('Dispatch differs from frozen schedule')
                intents[index] = event
            elif event.get('kind') == 'dispatch_result':
                E._keys(event, ('kind', 'ordinal', 'attempt'))
                if index not in intents or index in results or type(event['attempt']) is not dict:
                    raise E.ProtocolError('Missing or repeated dispatch intent/result')
                for key in _INTENT_KEYS:
                    if not E.exact_equal(event['attempt'].get(key), intents[index].get(key)):
                        raise E.ProtocolError('Dispatch result differs from intent')
                results[index] = event['attempt']
            else:
                raise E.ProtocolError('Unknown dispatch journal event')
        return [results[index] if index in results else {
            **{k: intent[k] for k in _INTENT_KEYS if k in intent},
            'status': 'unknown', 'contract_accept': None, 'usage': {}}
            for index, intent in intents.items()]

    def records(self):
        """One record per started cell, bound to its own folder; damage stays in that cell."""
        records = []
        self.record_issues, self.harness_failures = [], []
        for assignment in self.plan['assignments']:
            folder = self.cells / assignment['id']
            receipt = folder / 'receipt.json'
            if not receipt.exists() and not (folder / 'started.json').exists():
                continue
            if (folder / 'failure.json').exists():
                self.harness_failures.append(assignment['id'])
            try:
                attempts = self._journal(folder, assignment)
                if receipt.exists():
                    record = _read(receipt)
                    if type(record) is not dict or record.get('assignment_id') != assignment['id']:
                        raise E.ProtocolError('Receipt is not bound to its assignment folder')
                    if not E.exact_equal(record.get('attempts'), attempts):
                        raise E.ProtocolError('Receipt omitted or changed a journaled dispatch')
                else:
                    record = E.make_record(self.plan, assignment['id'], attempts, status='uncertain')
                records.append(record)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
                self.record_issues.append({'assignment_id': assignment['id'], 'kind': 'invalid_journal_or_receipt',
                                           'error': str(exc)[:400]})
                records.append({'assignment_id': assignment['id']})  # damaged, still assigned
        return records

    def summary(self):
        """Read-only aggregation; used by the Evidence bridge without creating a run."""
        records = self.records()
        summary = E.summarize(self.plan, records, spec_labor=self.manifest.get('spec_labor', []),
                              harness_failures=self.harness_failures)
        summary['experiment_id'] = self.frozen['id']
        summary['runner'] = {'version': self.frozen['version'], 'reader_version': VERSION,
                             'endpoint': 'one_exact_typed_decision',
                             'frozen_implementation': self.frozen['implementation'],
                             'current_implementation_matches': self.frozen['implementation'] == _implementation()}
        summary['limits'] += ['A dispatch intent interrupted without a receipt is an unknown attempt, not a known billable call.',
                              'Only provider_calls and prompt characters are enforced; no token/dollar/time ceiling is claimed.',
                              'Provider token/USD usage is included only when explicitly returned under usage.',
                              'The observation boundary is Applicators.call; provider-internal work and retries are not observable.',
                              'This experiment measures one decision; it does not establish multistep project competence.']
        if self.frozen['version'] == 1:
            summary['limits'].append('Frozen under matched protocol 1: the typed arm received the task as escaped program '
                                     'source, so non-ASCII text, control characters, braces or an annotated type could '
                                     'differ from, or fail before, the direct arm.')
        summary['receipt_integrity'] = {'issues': self.record_issues, 'harness_failures': self.harness_failures,
            'policy': 'Never started: pending; intent without final receipt: uncertain; torn, malformed, mismatched '
                      'or misfiled journal/receipt: damaged in its own cell; failure.json: harness failure.'}
        return summary

    def report(self):
        """Write matched-summary.json and matched-report.md from the retained receipts; returns the summary."""
        summary = self.summary()
        _write(self.out / 'matched-summary.json', summary)
        text = markdown(summary)
        (self.out / 'matched-report.md').write_text(text, encoding='utf-8')
        os.chmod(self.out / 'matched-report.md', 0o600)
        return summary



def load_summary(folder):
    """Pure read-only Evidence bridge. No mkdir, writes, providers or worker launch.

    Return {ok, summary, markdown}; malformed/missing plans return an error.
    Invalid cells retain their assigned denominator as damaged, not a plan error.
    Implementation drift is labeled on read, never repaired from current code.
    """
    try:
        out = Path(folder)
        frozen = _check_frozen(_read(out / 'matched-plan.json'))
        bench = MatchedBench.__new__(MatchedBench)
        bench.out, bench.apps, bench.frozen = out, None, frozen
        bench.plan, bench.manifest = frozen['plan'], frozen['manifest']
        bench.cells = out / 'matched-cells'
        bench.cases = {case['id']: case for case in bench.plan['cases']}
        bench.arms = {arm['id']: arm for arm in bench.plan['arms']}
        summary = bench.summary()
        return {'ok': True, 'summary': summary, 'markdown': markdown(summary)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        return {'ok': False, 'summary': None, 'markdown': '', 'error': str(exc)[:500]}


def _cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def markdown(summary):
    """The Markdown report of a matched-evaluation summary."""
    lines = ['# Symblic matched evaluation', '', 'Plan: `' + summary['plan_id'] + '`.', '',
             'Exact predeclared answers; every assigned task remains in the denominator. '
             'A passing format/type contract is separate from correctness.', '',
             '| Arm | Correct / assigned | False acceptance | Abstain | Contract accepted | Pending | Failed | Harness failed | Uncertain | Damaged | Dispatch attempts | Stronger fallback calls |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for g in summary['groups']:
        lines.append(f'| {_cell(g["arm_id"])} | {g["correct"]}/{g["assigned"]} | {g["false_accept"]} | {g["abstain"]} | '
                     f'{g["contract_accept"]} | {g["pending"]} | {g["failed"]} | {g["harness_failed"]} | '
                     f'{g["uncertain"]} | {g["damaged"]} | {g["attempts"]} | {g["stronger_fallback_calls"]} |')
    cells = summary['cells']
    lines += ['', f'Cells: {cells["assigned"]} assigned = {cells["pending"]} pending + {cells["attempted"]} attempted '
                  f'({cells["attempted_with_dispatch"]} with a recorded dispatch, {cells["attempted_without_dispatch"]} '
                  f'without one, {cells["damaged"]} damaged with unknown dispatches); {cells["resolved"]} reached a '
                  f'model-attributable outcome.']
    if summary['paired']:
        lines += ['', 'Paired outcomes count only pairs in which both arms reached a model-attributable outcome; '
                      'pending, unfinished, damaged, harness and infrastructure cells are unresolved, never wrong.', '',
                  '| Left | Right | Assigned pairs | Resolved | Both correct | Left only | Right only | Neither | Unresolved |',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for p in summary['paired']:
            lines.append(f'| {_cell(p["left"])} | {_cell(p["right"])} | {p["assigned_pairs"]} | {p["resolved_pairs"]} | '
                         f'{p["both_correct"]} | {p["left_only_correct"]} | {p["right_only_correct"]} | '
                         f'{p["neither_correct"]} | {p["unresolved_pairs"]} |')
    order = summary['order']
    lines += ['', 'Arm order: counterbalanced within each case and repeat (balanced Latin square, seed '
              f'{order["seed"]}).' if order['counterbalanced'] else
              'Arm order: fixed (plan version 1); latency and cost comparisons are confounded with arm order.']
    measured = summary['spec_labor']['known_minutes_total']
    lines += ['', 'Specification labor: ' + ('unmeasured.' if measured is None else str(measured) + ' recorded minutes.'), '',
              'The JSON summary retains paired family outcomes, initial correctness, fallback dependence, '
              'agreement, all attempt grades and known/unknown cost coverage.', '']
    lines += ['- ' + limit for limit in summary['limits']]
    return '\n'.join(lines) + '\n'


def main(args):
    """Entry point for ``bench.py --suite matched``: freeze (or resume) the experiment, run it, print the report."""
    manifest = _read(args.matched_manifest) if args.matched_manifest else None
    bench = MatchedBench(args.out, manifest, resume=args.resume or args.report_only)
    if args.report_only or args.dry_run:
        summary = bench.report()
    else:
        from symblic.providers import applicators as providers
        providers.install_sigterm()
        bench.apps = providers.Applicators(owner_label='symblic matched evaluation', run_id=bench.frozen['id'][:20])
        summary = bench.run()
    print(markdown(summary))
    return 0

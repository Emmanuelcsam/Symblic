"""Read back a finished step construction from its run folder, and prepare one for a run.

What this is for: symblic.steps.construction compiles a *step construction*, a short program in which a model
chooses, for each function of a small program, one expression from a list the author wrote; the kernel's checks
decide whether a choice is adopted. When such a run has finished, its folder (program.sym, meta.json, state.json)
holds the choices. `from_folder(folder)` reads that folder, recompiles the construction from the request saved in
it, and accepts the result only if everything agrees: the program text, the inputs, the execution pins, the
kernel, the one output record, every check receipt and every attribution (a choice made by a model, or by the
host's finite fallback, which tries the author's choices in order). Then it assembles the finished program with
symblic.steps.construction.assemble. It never runs the program again and never calls a model.

`prepare(request, by, ...)` compiles a construction and adds execution pins, ready for symblic.kernel.run.Run.

Depends on: symblic.kernel (language, evidence, execution_pins, run) and symblic.steps.construction.
Used by: symblic.authoring.workcards (`run_card(kind='steps')` and the `result` command).

These are local coherence checks over files on disk, not signatures: someone who can write the run folder could
write a consistent forgery. This module came from the original host's HTTP glue (its `/steps` API); the HTTP
route itself stays in integration/host/symblic_steps_api.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from symblic.kernel import language as S

MAX_INPUT_CHARACTERS = 200_000


class StepsResultError(ValueError):
    pass


def _read(path, maximum):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise StepsResultError('The construction record is missing or is not a regular file.')
    try:
        with path.open('rb') as stream:
            raw = stream.read(maximum + 1)
    except OSError as error:
        raise StepsResultError('The construction record could not be read; retry the read.') from error
    if len(raw) > maximum:
        raise StepsResultError('The construction record exceeds its size limit.')
    return raw


def prepare(request, by, *, retries=2, context_budget=12000, finite_fallback=False):
    """Compile a step construction and pin it for execution; nothing runs and no model is called.

    Returns symblic.steps.construction.compile_sequence's task with `options['execution_pins']` added: the hashes
    of the kernel sources the run must execute with (symblic.kernel.execution_pins). Hand the task's `source`,
    `inputs` and `options` to symblic.kernel.run.Run, or use symblic.authoring.workcards.run_card, which does this
    and keeps the record folder.
    """
    from symblic.steps import construction as C
    from symblic.kernel import execution_pins as X
    task = C.compile_sequence(request, by, retries=retries, context_budget=context_budget, finite_fallback=finite_fallback)
    _check_inputs(task['inputs'])
    hashes = {name: X._sha(X._read(name)) for name in sorted(X.REQUIRED_FILES)}
    task['options'] = {**task['options'], 'execution_pins': X.build(task['source'], task['inputs'], hashes)}
    return task


def _check_inputs(inputs):
    """The run inputs must be one JSON object of at most MAX_INPUT_CHARACTERS (the original host's admission rule,
    kept as a portable bound)."""
    if not isinstance(inputs, dict):
        raise StepsResultError('Construction inputs must be a JSON object.')
    if len(json.dumps(inputs)) > MAX_INPUT_CHARACTERS:
        raise StepsResultError('Construction inputs are too large.')
    return inputs


def _check_evidence(state, task, statements, choices, bindings, source_sha256):
    """Match recorded native observations; do not evaluate any predicate.

    A completed compiler run has one surviving receipt per compiled check
    (a local conjunction or a final assertion). Native retry rollback removes
    receipts of rejected candidates. Each selected
    index must agree with its actual ask binding and every receipt that reads it.
    These are local coherence checks, not signatures or a new proof execution.
    """
    from symblic.kernel import evidence as E
    from symblic.kernel.run import _src

    steps = task['task']['steps']
    if set(choices) != {step['name'] for step in steps}:
        raise StepsResultError('The choices do not name exactly the constructed functions.')
    asks = [statement for statement in statements if statement.k == 'ask']
    if len(asks) != len(steps):
        raise StepsResultError('The compiled construction has an unexpected ask shape.')
    env = S.Env()
    for index, (step, ask) in enumerate(zip(steps, asks)):
        selected = choices[step['name']]
        if not 1 <= selected <= len(step['choices']) or ask.name != 'brick_choice_' + str(index):
            raise StepsResultError('The selected expression is outside its declared choices.')
        expression = step['choices'][selected - 1]
        matches = [binding for binding in bindings if binding.get('name') == ask.name]
        if (len(matches) != 1 or matches[0].get('hash') != S.fingerprint(expression)
                or type(matches[0].get('value')) is not str or matches[0]['value'] != expression
                or type(matches[0].get('line')) is not int or matches[0]['line'] != ask.line
                or matches[0].get('type') != S.type_label(ask.type)):
            raise StepsResultError('A selected expression differs from its accepted ask binding.')
        env.vars[ask.name] = S.Binding(ask.name, expression)
    evidence = state.get('evidence')
    if (type(evidence) is not dict or type(evidence.get('version')) is not int
            or evidence['version'] != E.VERSION or evidence.get('source_sha256') != source_sha256
            or type(evidence.get('checks')) is not list):
        raise StepsResultError('The completed construction has missing or mismatched check evidence.')
    checks = [statement for statement in statements if statement.k in ('ensure', 'assert')]
    recorded = evidence['checks']
    if len(recorded) != len(checks):
        raise StepsResultError('The completed construction does not retain every authored check.')
    for statement, receipt in zip(checks, recorded):
        expected = E.check_receipt(statement, env, source=source_sha256, passed=True, text=_src(statement))
        # Canonical JSON comparison distinguishes true from 1 and an integer
        # from a float, while checking predicate/source/kernel/receipt IDs and
        # exact choice-binding hashes against the native receipt implementation.
        try:
            exact = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise StepsResultError('A recorded check receipt is malformed.') from error
        if exact != json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False):
            raise StepsResultError('A recorded check does not match the accepted source, kernel and choices.')


def _selection_origins(state, task, statements, bindings, choices, source_sha256):
    """Cross-check surviving native attribution; do not credit host trials to models."""
    from symblic.kernel import evidence as E
    from symblic.kernel import run as R

    def exact(left, right):
        return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(
            right, sort_keys=True, separators=(',', ':'), allow_nan=False)

    rows = state.get('finite_fallbacks', [])
    determinacy = state.get('determinacy')
    if (type(rows) is not list or any(type(row) is not dict for row in rows)
            or type(determinacy) is not dict or determinacy.get('asks_truncated') is not False
            or type(determinacy.get('asks')) is not list
            or any(type(row) is not dict for row in determinacy['asks'])):
        raise StepsResultError('Missing or malformed construction attribution.')
    asks = [n for n in statements if n.k == 'ask']
    ensures = [n for n in statements if n.k == 'ensure']
    if len(ensures) != len(asks) or len(determinacy['asks']) != len(asks):
        raise StepsResultError('The construction does not retain one decision for every step.')
    origins, trials, consumed = {}, 0, []
    for index, (step, ask, ensure) in enumerate(zip(task['task']['steps'], asks, ensures)):
        binding = next(b for b in bindings if b.get('name') == ask.name)
        meta = binding.get('meta')
        receipts = [r for r in determinacy['asks'] if r.get('name') == ask.name and r.get('line') == ask.line]
        found = [row for row in rows if row.get('name') == ask.name and row.get('line') == ask.line]
        if type(meta) is not dict or len(receipts) != 1:
            raise StepsResultError('Missing or ambiguous step attribution.')
        receipt = receipts[0]
        if receipt.get('answered_by') == 'finite_fallback':
            if (not task['inputs']['_steps_settings'].get('finite_fallback')
                    or meta.get('answered_by_finite_fallback') is not True or len(found) != 1):
                raise StepsResultError('The host-selected step has no matching finite completion record.')
            expected = R.finite_fallback_receipt(ask, ensure, choices[step['name']],
                source_sha256=source_sha256, kernel_id=state['kernel']['id'])
            check = state['evidence']['checks'][index]
            row = {'line': ask.line, 'name': ask.name, 'version': expected['version'],
                   'choices_sha256': expected['choices_sha256'], 'predicate_sha256': expected['predicate_sha256'],
                   'selection': expected['selection'], 'evaluated_count': expected['evaluated_count'],
                   'model_calls': 0, 'status': 'accepted', 'selected_index': expected['selected_index'],
                   'check_id': check['id'], 'selected_value_hash': expected['selected_value_hash'],
                   'receipt_sha256': E.digest(expected)}
            if (not exact(meta.get('finite_fallback'), expected)
                    or not exact(receipt.get('finite_fallback'), expected) or not exact(found[0], row)
                    or meta.get('agreement') is not None or meta.get('apps') != []
                    or type(meta.get('votes')) is not int or meta['votes'] != 0):
                raise StepsResultError('Finite completion attribution differs from its source and passing check.')
            consumed.append(found[0])
            trials += expected['evaluated_count']
            origins[step['name']] = 'finite_fallback'
        else:
            if (receipt.get('answered_by') != 'model' or found or 'finite_fallback' in meta
                    or meta.get('answered_by_finite_fallback') or 'finite_fallback' in receipt):
                raise StepsResultError('A step has inconsistent model or host attribution.')
            origins[step['name']] = 'model'
    if len(consumed) != len(rows):
        raise StepsResultError('The construction contains an unmatched finite completion record.')
    return {'selection_origins': origins, 'model_selected_steps': sum(v == 'model' for v in origins.values()),
            'finite_selected_steps': sum(v == 'finite_fallback' for v in origins.values()),
            'finite_trials': trials}


def from_folder(folder):
    """Inspect exact saved inputs/source/state; never execute or dispatch."""
    from symblic.steps import construction as C
    from symblic.kernel import execution_pins as X

    folder = Path(folder)
    limits = {'program.sym': S.MAX_SOURCE * 4, 'meta.json': 4_000_000, 'state.json': 16_000_000}
    raw = {name: _read(folder / name, limit) for name, limit in limits.items()}
    meta, state = json.loads(raw['meta.json']), json.loads(raw['state.json'])
    source = raw['program.sym'].decode('utf-8')
    if type(meta) is not dict or type(state) is not dict:
        raise StepsResultError('Malformed construction records.')
    inputs, options = meta.get('inputs'), meta.get('options')
    if type(inputs) is not dict or type(options) is not dict:
        raise StepsResultError('The construction has no saved input and policy record.')
    request, settings = inputs.get('_steps_request'), inputs.get('_steps_settings')
    if (type(settings) is not dict or not {'by', 'retries', 'context_budget'} <= set(settings)
            or set(settings) - {'by', 'retries', 'context_budget', 'finite_fallback'}):
        raise StepsResultError('This run has no step construction contract.')
    task = C.compile_sequence(request, **settings)
    if source != task['source'] or inputs != task['inputs']:
        raise StepsResultError('The saved program does not match its step construction contract.')
    # These options survive the normal engine's host-policy normalization. The
    # compiled source also carries per-ask context, solver and routing limits.
    for name in ('profile', 'max_calls', 'max_asks', 'parallel', 'determine'):
        if name in task['options'] and (type(options.get(name)) is not type(task['options'][name])
                                       or options.get(name) != task['options'][name]):
            raise StepsResultError('The saved construction policy differs: ' + name)
    if options.get('side_effects', False) is not False or options.get('constructor', 'off') != 'off':
        raise StepsResultError('Construction must retain its pure execution policy.')
    try:
        pins = X.validate(options.get('execution_pins'), source, inputs)
    except S.SymblicError as error:
        raise StepsResultError(error.message) from error
    status = state.get('status')
    if status != 'done':
        return {'status': status or 'unknown', 'accepted': False,
                'calls': state.get('calls'), 'error': state.get('error')}
    if (state.get('error') or type(state.get('kernel')) is not dict
            or state['kernel'].get('id') != pins['kernel_id']):
        raise StepsResultError('The completed record has an error or a different kernel.')
    outputs = state.get('outputs')
    if type(outputs) is not list or len(outputs) != 1 or type(outputs[0]) is not dict:
        raise StepsResultError('The completed construction must have one exact choice record.')
    row = outputs[0]
    statements = S.parse(source, execution_profile='verified')['statements']
    final = statements[-1]
    if (final.k != 'show' or final.value.k != 'name'
            or final.value.name != task['output_binding']
            or row.get('kind') != 'show' or row.get('line') != final.line
            or row.get('binding') != task['output_binding']
            or row.get('canonical_version') != S.CANON_VERSION):
        raise StepsResultError('The final choice record does not match the compiled output.')
    choices = row.get('canonical')
    if type(choices) is not dict or any(type(v) is not int for v in choices.values()):
        raise StepsResultError('Construction choices must be exact integers.')
    fingerprint = S.fingerprint(choices)
    bindings = state.get('bindings')
    if type(bindings) is not list or any(type(b) is not dict for b in bindings):
        raise StepsResultError('Malformed completed bindings.')
    matches = [b for b in bindings if b.get('name') == task['output_binding']]
    if row.get('hash') != fingerprint or len(matches) != 1 or matches[0].get('hash') != fingerprint:
        raise StepsResultError('The output fingerprint differs from its accepted binding.')
    source_sha256 = hashlib.sha256(raw['program.sym']).hexdigest()
    _check_evidence(state, task, statements, choices, bindings, source_sha256)
    origins = _selection_origins(state, task, statements, bindings, choices, source_sha256)
    # Refuse a concurrent mutation rather than mixing records from two versions.
    if any(_read(folder / name, limit) != raw[name] for name, limit in limits.items()):
        raise StepsResultError('The construction changed while it was being inspected; retry the read.')
    artifact = C.assemble(request, choices)
    return {'status': 'done', 'accepted': True, 'contract_id': task['contract_id'],
            'calls': state.get('calls'), 'choices': choices, 'artifact': artifact,
            **origins,
            'construction_source_sha256': source_sha256,
            'assurance': 'The completed construction passed its authored checks. Run the assembled program on independent inputs to test its wider behavior.'}

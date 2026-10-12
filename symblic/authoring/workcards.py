"""Workcards: small, typed authoring forms that compile to ordinary checked Symblic programs.

What it is for: giving a person or a small model a form to fill instead of a program to write. Three kinds:

- `slots`: a program template with holes (`[[name]]`), each hole typed (an expression, an integer, a name, ...)
  with the author's options; compile_slots makes a program in which a model picks one option per hole (by its
  number), and fill_slots substitutes the picks into the template. The filled program is an ordinary program whose
  own checks decide when it runs.
- `team`: a builder applicator proposes an answer and named reviewer applicators (critic and others) check it against
  explicit constraints, for a bounded number of rounds (compile_team).
- `steps`: a step construction (symblic.steps.construction): a model picks each function's expression from the
  author's list; the kernel's checks decide; the finished program is read back by symblic.steps.recovery.

run_card(request, kind=..., folder=NEW_PRIVATE_FOLDER, by=...) compiles, pins the kernel sources (execution pins),
runs the card with symblic.kernel.run.Run and keeps every record in the folder; an existing record refuses, so an
unknown call is never dispatched twice. No new model transport, grammar, effect executor or acceptance oracle:
generated programs remain ordinary verified Symblic with explicit checks and call budgets.

Command line: python3 -m symblic.authoring.workcards catalog | prepare | fill | compile | run | result
(--kind slots|team|steps, --request FILE.json, --by APP, --dir FOLDER). Examples: examples/workcard-*.json and
examples/steps-parcel.json. handle() is the HTTP adapter the original host dashboard used; its `steps/result` route
needs that host's run store.
Depends on: symblic.kernel (language, run, execution_pins), symblic.authoring.helpers, symblic.steps (construction,
recovery) and, when no applicators object is passed, symblic.providers.applicators.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from symblic.kernel import language as S
from symblic.authoring import helpers as A

VERSION = 1
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
HOLE = re.compile(r'\[\[([A-Za-z][A-Za-z0-9_]{0,47})\]\]')
PURE_NODES = frozenset({'num', 'lit', 'str', 'name', 'list', 'set', 'record', 'range',
                        'un', 'bin', 'cmp', 'cond', 'quant', 'comp', 'attr', 'index', 'call'})
# one engine per role: every engine the kernel knows except `kernel` (it never answers an ask) and `council` (a
# nested group of agents is not bounded here)
SINGLE_PROVIDERS = frozenset(S.ENGINES) - {'kernel', 'council'}


class CardError(ValueError):
    pass


def copy(value):
    return A._json_copy(value)


def digest(value):
    return hashlib.sha256(A._raw(value)).hexdigest()


def keys(value, required, optional=()):
    if type(value) is not dict or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise CardError('Wrong fields: expected ' + ', '.join(required))


def text(value, maximum=8192):
    if type(value) is not str or not value.strip() or len(value.encode('utf-8')) > maximum:
        raise CardError('Expected nonempty bounded text')
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise CardError('Integer outside declared bounds')
    return value


def name(value):
    if type(value) is not str or not NAME.fullmatch(value) or value in S.BUILTINS or value.lower() in S.KEYWORDS or value.lower() in S.WORD_OPS:
        raise CardError('Expected a nonreserved binding name')
    return value


def app(value):
    text(value, 200)
    if not re.fullmatch(r'[A-Za-z0-9_.:/@+*\-]+', value):
        raise CardError('Expected one explicit applicator')
    parsed = S.parse_applicator(value)
    if parsed['engine'] not in SINGLE_PROVIDERS or '*' in value or S.app_label(parsed) != value:
        raise CardError('Roles require one explicit provider per role; nested councils and weights are not bounded here')
    return value


def expr(value):
    """One native expression, never statements or evaluation."""
    text(value, 4096)
    parsed = S.parse('let slot_value = (' + value + ').', execution_profile='verified')
    nodes = parsed['statements']
    if len(nodes) != 1 or nodes[0].k != 'let':
        raise CardError('The slot must contain exactly one expression')
    return nodes[0].value


def native_check(source):
    checked = S.check(source, execution_profile='verified')
    if not checked['ok']:
        raise CardError('Native checker refused: ' + str(checked['errors'][0].get('message')))
    return checked


def compile_team(request):
    """Bounded sequential roles; only authored executable predicates accept."""
    r = copy(request)
    keys(r, ('instruction', 'answer_type', 'checks', 'builder', 'reviewers'),
         ('rounds', 'inputs', 'context_budget'))
    rounds = integer(r.get('rounds', 2), 1, 4)
    budget = integer(r.get('context_budget', 24000), 1024, 131072)
    typ = text(r['answer_type'], 1000)
    parsed = S.parse('given answer: ' + typ + '.', execution_profile='verified')['statements']
    if len(parsed) != 1 or parsed[0].k != 'given' or parsed[0].name != 'answer' or getattr(parsed[0], 'default', None) is not None:
        raise CardError('Expected one native answer type')
    builder = app(r['builder'])
    reviewers = r['reviewers']
    if type(reviewers) is not list or not 1 <= len(reviewers) <= 3:
        raise CardError('Provide one to three explicit reviewers')
    roles = []
    for review in reviewers:
        keys(review, ('role', 'by', 'instruction'))
        roles.append({'role': name(review['role']), 'by': app(review['by']), 'instruction': text(review['instruction'])})
    if len({v['role'] for v in roles}) != len(roles):
        raise CardError('Reviewer role names must be distinct')
    checks = r['checks']
    supplied = r.get('inputs', {})
    if type(supplied) is not dict or len(supplied) > 32:
        raise CardError('Expected a bounded input record')
    if type(checks) is not list or not 1 <= len(checks) <= 32:
        raise CardError('At least one authored executable acceptance predicate is required')
    for check in checks:
        node = expr(check)
        if any(n.k not in PURE_NODES for n in S.walk(node)):
            raise CardError('Acceptance predicates require pure expression nodes')
        if any(n.k == 'call' and (n.fn not in S.BUILTINS or n.fn in S.EVAL_DENIED) for n in S.walk(node)):
            raise CardError('Acceptance predicates use pure native builtins only')
        if 'answer' not in S.free_names(node):
            raise CardError('Each acceptance predicate must read answer')
        if S.free_names(node) - {'answer'} - set(supplied) - set(S.CONSTANTS):
            raise CardError('Acceptance predicates may read only answer and explicit inputs')
    reserved = {'instruction', 'answer', 'review_instructions', 'accepted', 'previous', 'card_accept', 'acceptance_checks'}
    for k in supplied:
        name(k)
        if k in reserved or k.startswith(('candidate_', 'review_', 'check_', 'passed_', 'accepted_')):
            raise CardError('Input collides with generated role bindings')
    inputs = {**supplied, 'instruction': text(r['instruction']),
              'review_instructions': [v['instruction'] for v in roles], 'acceptance_checks': checks}
    head = [f'use profile=verified, context=none, coercion=strict, retries=0, determine=false, budget={budget}.',
            'given instruction: Text.', 'given review_instructions: List of Text.', 'given acceptance_checks: List of Text.']
    head += ['given ' + k + ': Any.' for k in sorted(supplied)]
    # A pure function binds the exact authored answer name. Its body never asks.
    head += ['function card_accept(answer: ' + typ + ') -> Bool = ' + ' and '.join('(' + c + ')' for c in checks) + '.']
    for n in range(1, rounds + 1):
        # Each subsequent round executes only when every earlier round was vetoed.
        if n > 1:
            head.append('else')
        deps = ['instruction', 'acceptance_checks'] + sorted(supplied)
        if n > 1:
            deps += ['candidate_' + str(n - 1), 'passed_' + str(n - 1)] + ['review_' + str(n - 1) + '_' + str(i) for i in range(len(roles))]
        head.append('ask candidate_' + str(n) + ': ' + typ + ' "Build the answer requested by {instruction}. Satisfy acceptance_checks using the explicit inputs; earlier review records, when present, explain a rejected proposal." from ' + ', '.join(deps) + ' by ' + json.dumps(builder) + ' with retries=0.')
        head.append('let passed_' + str(n) + ' = card_accept(candidate_' + str(n) + ').')
        # Reviewers see the same candidate plus earlier critiques: a bounded debate.
        for i, role in enumerate(roles):
            deps = ['instruction', 'acceptance_checks', 'review_instructions', 'candidate_' + str(n), 'passed_' + str(n)] + sorted(supplied)
            deps += ['review_' + str(n) + '_' + str(j) for j in range(i)]
            prompt = 'Role ' + role['role'] + '. Apply instruction {review_instructions[' + str(i + 1) + ']}. Review candidate_' + str(n) + '; return accept and a concrete reason. Agreement cannot override a failed executable check.'
            head.append('ask review_' + str(n) + '_' + str(i) + ': Record {accept: Bool, reason: Text up to 160 words} ' + json.dumps(prompt) + ' from ' + ', '.join(deps) + ' by ' + json.dumps(role['by']) + ' with retries=0.')
        cond = ' and '.join(['passed_' + str(n)] + ['review_' + str(n) + '_' + str(i) + '.accept' for i in range(len(roles))])
        head += ['if ' + cond + ' then', 'let answer = candidate_' + str(n) + '.', 'assert card_accept(answer).',
                 'show answer as "Accepted answer".']
        if n == rounds:
            head += ['else', 'ensure false else fail because "No proposal passed the executable checks and reviewer vetoes.".']
    head += ['end.' for _ in range(rounds)]
    # Because the last refusal branch has no answer binding, no post-branch name
    # is assumed. Output inside each accepted branch instead.
    source = '\n'.join(head) + '\n'
    checked = native_check(source)
    result = {'version': VERSION, 'kind': 'team', 'source': source, 'inputs': inputs,
              'options': {'profile': 'verified', 'parallel': 1, 'side_effects': False,
                          'max_calls': rounds * (1 + len(roles)), 'max_asks': rounds * (1 + len(roles)),
                          'context_budget': budget, 'constructor': 'off'},
              'check': checked, 'roles': [{'role': 'builder', 'by': builder}] + roles,
              'assurance': 'Accepted only under authored executable predicates and reviewer vetoes; no independence or factual-truth guarantee.'}
    result['contract_id'] = digest(result)
    return result


def slot_catalog():
    shapes = {'let': 'let value = ([[expression]]).', 'assert': 'assert ([[expression]]).',
              'if': 'if ([[condition]]) then\nshow true.\nelse\nshow false.\nend.',
              'for': 'for item in ([[collection]]) do\nshow item.\nend.'}
    authorities = {}
    for key, source in shapes.items():
        sample = HOLE.sub('true' if key in ('assert', 'if') else '[1]' if key == 'for' else '0', source)
        authorities[key] = {'template': source, 'native_shape': [n.k for n in S.parse(sample, execution_profile='verified')['statements']]}
    return {'version': VERSION, 'shapes': authorities, 'slot_kinds': ['expression', 'identifier', 'type'],
            'authority': 'symblic.parse and symblic.check', 'authoring_contract': A.catalog()['contract_id'],
            'assurance': 'Menus retain caller choices; parsing never ranks them by correctness.'}


def validate_slot(kind, value):
    text(value, 4096)
    if HOLE.search(value):
        raise CardError('Choice contains reserved hole delimiters; write nested lists with spaces')
    if kind == 'expression':
        expr(value)
    elif kind == 'identifier':
        name(value)
    elif kind == 'type':
        rows = S.parse('given slot_value: ' + value + '.', execution_profile='verified')['statements']
        if len(rows) != 1 or rows[0].k != 'given' or rows[0].name != 'slot_value' or getattr(rows[0], 'default', None) is not None:
            raise CardError('Expected exactly one type')
    else:
        raise CardError('Unknown slot kind')
    return value


def substitute(template, slots, answers):
    kinds = {slot['name']: slot['kind'] for slot in slots}
    def chosen(match):
        key = match.group(1)
        value = answers[key]
        return '(' + value + ')' if kinds[key] == 'expression' else value
    return HOLE.sub(chosen, template)


def prepare_slots(request):
    r = copy(request)
    keys(r, ('template', 'slots'), ('instruction',))
    template = text(r['template'], 32768)
    holes = HOLE.findall(template)
    slots = r['slots']
    if type(slots) is not list or not 1 <= len(slots) <= 32:
        raise CardError('Provide one to 32 named holes')
    if len(set(holes)) != len(holes) or len(holes) != len(slots):
        raise CardError('Each hole must occur exactly once')
    bound = []
    for slot in slots:
        keys(slot, ('name', 'kind', 'instruction', 'choices'))
        ident = name(slot['name'])
        choices = slot['choices']
        if type(choices) is not list or not 1 <= len(choices) <= 32 or any(type(v) is not str for v in choices) or len(set(choices)) != len(choices):
            raise CardError('Provide one to 32 distinct exact caller-authored choices')
        bound.append({'name': ident, 'kind': slot['kind'], 'instruction': text(slot['instruction']),
                      'choices': [validate_slot(slot['kind'], v) for v in choices]})
    if {b['name'] for b in bound} != set(holes):
        raise CardError('Slot names do not exactly match visible template holes')
    # Check the skeleton with one syntactically valid caller choice per slot.
    sample = substitute(template, bound, {b['name']: b['choices'][0] for b in bound})
    shape = S.parse(sample, execution_profile='verified')
    result = {'version': VERSION, 'kind': 'slots', 'instruction': text(r.get('instruction', 'Fill the visible holes according to their instructions.')),
              'template': template, 'slots': bound, 'native_shape': [n.k for n in shape['statements']],
              'authoring_contract': A.catalog()['contract_id'], 'model_calls': 0,
              'assurance': 'Syntax guidance only. Every choice remains visible, including semantically wrong choices. Final native checks are separate.'}
    budget = 4096 + 3 * (len(template) + len(result['instruction']) + max(len(json.dumps(b, ensure_ascii=False)) for b in bound))
    if budget > 131072:
        raise CardError('Template and slot choices exceed the bounded context budget; split the task')
    result['context_budget'] = max(24000, budget)
    result['contract_id'] = digest(result)
    return result


def fill_slots(request, answers):
    task = prepare_slots(request)
    if type(answers) is not dict or set(answers) != {v['name'] for v in task['slots']}:
        raise CardError('Supply exactly one selected choice per hole')
    for slot in task['slots']:
        value = answers[slot['name']]
        if type(value) is not str or value not in slot['choices']:
            raise CardError('Answer is not an exact declared choice for ' + slot['name'])
        validate_slot(slot['kind'], value)
    source = substitute(task['template'], task['slots'], answers)
    parsed = S.parse(source, execution_profile='verified')
    if [n.k for n in parsed['statements']] != task['native_shape']:
        raise CardError('Filled program changed the statement skeleton')
    check = native_check(source)
    return {'source': source, 'check': check, 'contract_id': task['contract_id'], 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'status': 'prepared', 'execution': 'not_run', 'answers': copy(answers)}


def compile_slots(request, by):
    task = prepare_slots(request)
    app(by)
    budget = task['context_budget']
    lines = [f'use profile=verified, context=none, coercion=strict, retries=0, determine=false, budget={budget}.',
             'given instruction: Text.', 'given template: Text.']
    inputs = {'instruction': task['instruction'], 'template': task['template']}
    for i, slot in enumerate(task['slots']):
        inputs['card_' + str(i)] = slot
        lines += ['given card_' + str(i) + ': Any.',
                  'ask choice_' + str(i) + ': Int in 1..' + str(len(slot['choices'])) +
                  ' "Choose the one-based choice index for this one hole, following {instruction}. The exact template is {template}. This slot card is {card_' + str(i) + '}." from instruction, template, card_' + str(i) + ' by ' + json.dumps(by) + ' with retries=0.',
                  'show choice_' + str(i) + ' as "' + slot['name'] + '".']
    source = '\n'.join(lines) + '\n'
    return {'version': VERSION, 'kind': 'slots', 'source': source, 'inputs': inputs, 'task': task,
            'options': {'profile': 'verified', 'parallel': 1, 'side_effects': False, 'constructor': 'off',
                        'max_calls': len(task['slots']), 'max_asks': len(task['slots']), 'context_budget': budget},
            'contract_id': digest({'task': task, 'by': by}), 'check': native_check(source)}


def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_folder(path):
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for item in reversed(missing):
        item.mkdir(mode=0o700, exist_ok=True)
        fsync_dir(item.parent)
    state = path.stat()
    if not path.is_dir() or state.st_uid != os.getuid() or state.st_mode & 0o077:
        raise CardError('Record folder must be private and owned by this user (mode 0700)')


def run_card(request, *, kind, folder, by=None, applicators=None,
             retries=None, context_budget=None, finite_fallback=None):
    """Fresh explicit invocation; existing records refuse, so unknown calls never redispatch."""
    from symblic.kernel.run import Run
    from symblic.kernel import execution_pins as X
    step_options = {key: value for key, value in
                    (('retries', retries), ('context_budget', context_budget),
                     ('finite_fallback', finite_fallback)) if value is not None}
    if step_options and kind != 'steps':
        raise CardError('Retry and context options apply only to step construction.')
    if kind == 'team':
        card = compile_team(request)
    elif kind == 'slots':
        card = compile_slots(request, by)
    elif kind == 'steps':
        from symblic.steps import construction as symblic_steps
        card = symblic_steps.compile_sequence(request, by, **step_options)
    else:
        raise CardError('Unknown workcard kind')
    path = Path(folder).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CardError('Record folder must not be a symlink')
    private_folder(path)
    if any(path.iterdir()):
        raise CardError('Record already exists. Inspect it; no automatic redispatch is allowed.')
    options = dict(card['options'])
    hashes = {n: X._sha(X._read(n)) for n in sorted(X.REQUIRED_FILES)}
    options['execution_pins'] = X.build(card['source'], card['inputs'], hashes)
    record = {'request': request, 'kind': kind, 'card': card, 'options': options,
              'compiler_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if kind == 'steps':
        record.update(steps_compiler_sha256=hashlib.sha256(Path(symblic_steps.__file__).read_bytes()).hexdigest(),
                      steps_compiler_version=symblic_steps.VERSION)
    with (path/'card.json').open('x') as f:
        json.dump(record, f)
        f.flush(); __import__('os').fsync(f.fileno())
    for filename, data in [('program.sym', card['source']), ('meta.json', json.dumps({'inputs': card['inputs'], 'options': options}))]:
        with (path/filename).open('x') as f:
            f.write(data); f.flush(); __import__('os').fsync(f.fileno())
    fsync_dir(path)
    if applicators is None:
        from symblic.providers.applicators import Applicators
        applicators = Applicators(owner_label='operator (Symblic workcard)', run_id=path.name)
    run = Run(card['source'], card['inputs'], applicators, options, folder=str(path))
    report = run.execute()
    result = {'kind': kind, 'contract_id': card['contract_id'], 'status': report['status'], 'report': report}
    if kind == 'slots' and report['status'] == 'done':
        answers = {slot['name']: slot['choices'][int(run.kernel.env.lookup('choice_' + str(i)).value) - 1]
                   for i, slot in enumerate(card['task']['slots'])}
        try:
            result['prepared'] = fill_slots(request, answers)
            result['status'] = 'prepared'
        except (CardError, S.SymblicError) as error:
            result.update(status='refused', error=str(error))
    if kind == 'steps' and report['status'] == 'done':
        from symblic.steps import recovery
        try:
            recovered = recovery.from_folder(path)
        except (ValueError, S.SymblicError, OSError) as error:
            result.update(status='refused', error=str(error))
        else:
            result['artifact'] = recovered['artifact']
            result['choices'] = recovered['choices']
            for key in ('selection_origins', 'model_selected_steps', 'finite_selected_steps', 'finite_trials'):
                result[key] = recovered[key]
            with (path/'assembled.sym').open('x') as f:
                f.write(recovered['artifact']['source']); f.flush(); os.fsync(f.fileno())
    with (path/'workcard-result.json').open('x') as f:
        json.dump(result, f);f.flush();__import__('os').fsync(f.fileno())
    fsync_dir(path)
    return result


def handle(handler, method, route, data):
    """HTTP adapter for a host (the original host dashboard used it); the host checks access before calling it."""
    if not route.startswith('workcards/'):
        return False
    try:
        if method == 'GET' and route == 'workcards/catalog':
            handler.send_json(slot_catalog())
        elif method == 'POST' and route == 'workcards/compile':
            keys(data, ('kind', 'request'), ('by',))
            if data['kind'] == 'team': result = compile_team(data['request'])
            elif data['kind'] == 'slots': result = compile_slots(data['request'], data.get('by'))
            else: raise CardError('Unknown workcard kind')
            handler.send_json(result)
        elif method == 'POST' and route == 'workcards/steps/compile':
            from symblic.steps import recovery
            keys(data, ('request', 'by'), ('retries', 'context_budget', 'finite_fallback'))
            handler.send_json(recovery.prepare(data['request'], data['by'],
                retries=data.get('retries', 2), context_budget=data.get('context_budget', 12000),
                finite_fallback=data.get('finite_fallback', False)))
        elif method == 'POST' and route == 'workcards/steps/result':
            # host-only: a run id is looked up in the original host's run store
            from integration.host import symblic_steps_api as symblic_steps_api
            keys(data, ('id',))
            handler.send_json(symblic_steps_api.result(data['id']))
        elif method == 'POST' and route == 'workcards/prepare':
            keys(data, ('request',))
            handler.send_json(prepare_slots(data['request']))
        elif method == 'POST' and route == 'workcards/fill':
            keys(data, ('request', 'answers'))
            handler.send_json(fill_slots(data['request'], data['answers']))
        else:
            handler.send_json({'error': 'Unknown workcard route'}, 404)
    except (ValueError, TypeError, A.AuthoringError, S.SymblicError) as error:
        handler.send_json({'error': str(error)}, 400)
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description='Symblic typed workcards and bounded reviewer roles')
    p.add_argument('command', choices=['catalog', 'prepare', 'fill', 'compile', 'run', 'result'])
    p.add_argument('--kind', choices=['slots', 'team', 'steps'], default='slots')
    p.add_argument('--request'); p.add_argument('--answers'); p.add_argument('--by'); p.add_argument('--dir')
    p.add_argument('--retries', type=int, help='Corrections per step, from 0 to 5 (default: 2).')
    p.add_argument('--context-budget', type=int, help='Step request character budget, from 1000 to 100000 (default: 12000).')
    p.add_argument('--finite-fallback', action='store_true', default=None,
                   help='After model check failures exhaust retries, try authored choices with native checks; record host selections.')
    args = p.parse_args(argv)
    try:
        if args.kind == 'steps' and args.command == 'fill':
            raise CardError('Steps select expressions during run; fill supports slots only.')
        step_options = {key: value for key, value in
                        (('retries', args.retries), ('context_budget', args.context_budget),
                         ('finite_fallback', args.finite_fallback)) if value is not None}
        if step_options and (args.kind != 'steps' or args.command not in ('prepare', 'compile', 'run')):
            raise CardError('--retries, --context-budget and --finite-fallback apply only to steps prepare, compile or run.')
        if args.command == 'catalog':
            result = slot_catalog()
        elif args.command == 'result':
            if not args.dir: p.error('--dir is required')
            from symblic.steps import recovery
            result = recovery.from_folder(args.dir)
        else:
            if not args.request: p.error('--request is required')
            request = A._load_json(args.request)
            if args.kind == 'steps' and args.command in ('prepare', 'compile'):
                from symblic.steps import recovery
                result = recovery.prepare(request, args.by, **step_options)
            elif args.command == 'prepare': result = prepare_slots(request) if args.kind == 'slots' else compile_team(request)
            elif args.command == 'fill':
                if not args.answers: p.error('--answers is required')
                result = fill_slots(request, A._load_json(args.answers))
            elif args.command == 'compile': result = compile_team(request) if args.kind == 'team' else compile_slots(request, args.by)
            else:
                if not args.dir: p.error('--dir is required for durable records')
                result = run_card(request, kind=args.kind, folder=args.dir, by=args.by, **step_options)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get('status') in ('failed', 'refused', 'stopped') else 0
    except (ValueError, A.AuthoringError, S.SymblicError, OSError) as error:
        print(json.dumps({'status': 'refused', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

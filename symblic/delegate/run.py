"""Run a delegation task (symblic.delegate.contracts) on the kernel's runner and return the exact accepted value.

What it is for: the executing half of delegation. `run_task(request, by=..., applicators=..., folder=...)` compiles
the request, pins the kernel sources it must run with (execution pins), runs the program with symblic.kernel.run.Run,
and returns a compact result: `accepted`, the canonical `result` (only after a successful run), the contract and
routing identities, the call count and the run's error, if any. Templates own all syntax and checks; candidates,
retries and evidence stay in the run (and in its folder when one is given). A saved folder can be verified again
(`verify_declaration`) before it is resumed or replayed.

Routing: with `by` the caller names one applicator, or an ordered list of up to 12 for the kernel's automatic route.
Without `by`, model asks use the automatic route over a local-only ladder of small Ollama models (LOCAL_LADDER:
llama3.2:1b, granite3.3:2b, qwen3:4b-instruct) inside the template's own call ceiling; nothing falls back to a
cloud model (docs/reference/LOCAL-ROUTING.md). The ladder is a routing heuristic chosen in October 2026 from the
models then installed, not a quality ranking.

Command line (python3 -m symblic.delegate.run ..., or `tools/symblic delegate ...`):

    catalog [--template NAME]                       the templates and their request schemas
    check TASK.json | compile TASK.json             validate and compile; no model
    run TASK.json [--by APPLICATOR ...] [--dir NEW_FOLDER] [--json]

Depends on: symblic.kernel (language, run, execution_pins), symblic.delegate.contracts and, when no applicators
object is passed, symblic.providers.applicators. Examples: examples/*.task.json and examples/proof_step*_handoff.py.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
from pathlib import Path

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.kernel import execution_pins as X
from symblic.kernel.run import Run

# Ascending parameter count among the locally observed installed tags (2026-10-04).
# This is a routing heuristic, not a quality ranking or an availability reservation.
LOCAL_LADDER = ('ollama:llama3.2:1b', 'ollama:granite3.3:2b', 'ollama:qwen3:4b-instruct')
MAX_ROUTE = 12            # the native automatic route takes one to twelve candidates
ROUTING_VERSION = 2


def _applicator(by):
    if type(by) is not str or not by.strip() or len(by) > 300:
        raise D.ContractError('applicator', 'Supply one named applicator.', 'by')
    return S.parse_applicator(by)


def routing_plan(by, ceiling):
    """The requested route: none, one named applicator, or an ordered list for the native automatic route.

    by None means the local ladder whenever the template may call a model. A list is the caller's exact
    order; a cloud engine is allowed only when the caller names one. Charged native
    dispatches never exceed ceiling; refunded pre-dispatch refusals are separate.
    """
    plan = {'version': ROUTING_VERSION, 'mode': 'none', 'candidates': [], 'allow_cloud': False,
            'call_ceiling': ceiling, 'repairs': 0, 'declared_repairs': 'shared',
            'availability': 'decided_at_dispatch', 'call_accounting_scope': 'native_applicator_dispatches'}
    if by is None and ceiling <= 0:
        return plan
    if by is None:
        names, mode = list(LOCAL_LADDER), 'default_local_ladder'
    elif type(by) in (list, tuple):
        if not 1 <= len(by) <= MAX_ROUTE:
            raise D.ContractError('applicator', f'Supply one to {MAX_ROUTE} named applicators.', 'by')
        names, mode = list(by), 'explicit_list'
    else:
        names, mode = [by], 'explicit_single'
    apps = [_applicator(name) for name in names]
    names = [app['spec'] for app in apps]
    if mode != 'explicit_single':
        if len(set(names)) != len(names):
            raise D.ContractError('applicator', 'Name each applicator once.', 'by')
        if any(app['engine'] in ('kernel', 'council') for app in apps):
            raise D.ContractError('applicator', 'A route lists single models; the kernel and councils cannot be '
                                                'rungs.', 'by')
    plan.update(mode=mode, candidates=names,
                allow_cloud=any(app['engine'] not in (*S.LOCAL_APPLICATOR_ENGINES, 'kernel') for app in apps))
    if any(app['engine'] == 'council' for app in apps):
        plan['nested_provider_call_ceiling'] = 'not_established'
    return plan


_VOTING = ('votes', 'ahead', 'key', 'vote', 'agree', 'strict', 'families', 'permute', 'within')


def _literal(node):
    """A bare word or literal number, else None (the native run evaluates other expressions)."""
    if isinstance(node, S.Node):
        if node.k == 'name':
            return node.name
        return getattr(node, 'value', None) if node.k in ('num', 'lit') else None
    return node


def ask_routes(source, plan):
    """Disclose finite per-ask routing possibilities, not a forecast.

    The delegated auto policy shares zero repairs, so checked failures advance
    after one sample. Full-attempt budget reach assumes no refunded refusals;
    reach includes free pre-dispatch refusals. Every ask shares the run ceiling.
    """
    if plan['mode'] in ('none', 'explicit_single'):
        return []
    rows, defaults, count, ceiling = [], {}, len(plan['candidates']), plan['call_ceiling']
    for node in S.walk(S.parse(source, execution_profile='verified')['statements']):
        kind = getattr(node, 'k', '')
        if kind == 'use':
            defaults.update({key: _literal(value) for key, value in node.options.items()})
        if kind != 'ask':
            continue
        option = {**defaults, **{key: _literal(value) for key, value in node.options.items()}}
        row = {'line': node.line, 'name': node.name}
        if 'by' in node.options:
            row.update(route='template_applicator', calls_per_rung=None, reach=0)
        elif option.get('route') == 'escalate':
            retries = option.get('retries', 2)
            per_rung = 1 if plan.get('declared_repairs') == 'shared' and plan['repairs'] == 0 else (
                max(0, min(5, int(retries))) + 1 if type(retries) is int else None)
            row.update(route='declared_escalate_shared' if plan.get('declared_repairs') == 'shared'
                       else 'declared_escalate', calls_per_rung=per_rung,
                       full_attempt_budget_reach=min(count, -(-ceiling // per_rung)) if per_rung else None,
                       reach=count, reach_scope='possible_with_free_predispatch_refusals')
        elif option.get('route') is None and option.get('effort') != 'ultra' and not any(
                key in option for key in _VOTING):
            row.update(route='automatic', calls_per_rung=1, full_attempt_budget_reach=min(count, ceiling),
                       reach=count, reach_scope='possible_with_free_predispatch_refusals')
        else:
            row.update(route='first_candidate_only', calls_per_rung=None, reach=min(count, 1))
        rows.append(row)
    return rows


def prepare(body, *, by=None):
    task = D.compile_task(body)
    options = dict(task['options'])
    plan = routing_plan(by, options['max_calls'])
    if plan['mode'] == 'explicit_single':
        options['by'] = plan['candidates'][0]
    elif plan['mode'] != 'none':
        # One native run; charged dispatches share max_calls, confirmed refusals are refunded.
        options.update(by='auto', auto_route={'candidates': list(plan['candidates']),
                                              'max_calls': options['max_calls'], 'repairs': plan['repairs'],
                                              'allow_cloud': plan['allow_cloud'],
                                              'declared_repairs': plan['declared_repairs']})
    plan['asks'] = ask_routes(task['source'], plan)
    pin_names = set(X.REQUIRED_FILES)
    if options['max_calls'] > 0:
        pin_names.update(name for name in ('symblic/providers/applicators.py', 'symblic/providers/ollama_call.py')
                         if name in X.PYTHON_FILES and (X.BASE / name).is_file())
    hashes = {name: X._sha(X._read(name)) for name in sorted(pin_names)}
    options['execution_pins'] = X.build(task['source'], task['inputs'], hashes)
    routing_id = X._sha(X._json({'version': ROUTING_VERSION, 'contract_id': task['contract_id'],
                                  'routing': plan, 'options': options}))
    return {**task, 'options': options, 'routing': plan, 'routing_id': routing_id}


def requested_by(plan):
    """Recover the canonical caller choice; prepare() validates the whole result."""
    if type(plan) is not dict or type(plan.get('candidates')) is not list:
        raise D.ContractError('routing', 'Routing declaration is missing or malformed.')
    mode, candidates = plan.get('mode'), plan['candidates']
    if mode in ('none', 'default_local_ladder'):
        return None
    if mode == 'explicit_single' and len(candidates) == 1:
        return candidates[0]
    if mode == 'explicit_list':
        return list(candidates)
    raise D.ContractError('routing', 'Unknown routing declaration mode.')


def verify_declaration(declaration, source, inputs, options):
    """Pure reconstruction used at API creation/read and worker dispatch/resume.

    This binds an exact policy and its execution pins to the template contract.
    It detects changed or misfiled records, not a writer replacing the whole record.
    """
    keys = {'contract_id', 'template_id', 'output_binding', 'assurance', 'request'}
    routed_keys = keys | {'routing', 'routing_id'}
    if type(declaration) is not dict or set(declaration) not in (keys, routed_keys):
        raise D.ContractError('routing', 'Invalid delegation result declaration.')
    if type(options) is not dict:
        raise D.ContractError('routing', 'Delegation execution options must be a record.')
    if set(declaration) == routed_keys:
        task = prepare(declaration['request'], by=requested_by(declaration['routing']))
        if X._json(options) != X._json(task['options']):
            raise D.ContractError('routing', 'Delegation routing/execution options changed.')
    else:
        task = D.compile_task(declaration['request'])
        if set(options) - (set(task['options']) | {'by', 'execution_pins'}):
            raise D.ContractError('routing', 'Unbound legacy delegation execution option.')
        if 'by' in options:
            _applicator(options['by'])
    if any(X._json(declaration[key]) != X._json(task[key]) for key in set(declaration) - {'request'}):
        raise D.ContractError('routing', 'Delegation contract or routing identity changed.')
    if source != task['source'] or X._json(inputs) != X._json(task['inputs']):
        raise D.ContractError('routing', 'Delegation source or inputs changed.')
    for key, value in task['options'].items():
        actual = options.get(key, False if key == 'side_effects' else None)
        if X._json(actual) != X._json(value):
            raise D.ContractError('routing', 'Delegation execution option changed: ' + key)
    X.validate(options.get('execution_pins'), source, inputs)
    return task


def routing_record(task, native, report, *, trace_scope='current_invocation', trace_complete=True):
    """Requested route, completed rung summaries, filters and native budget accounting.

    An exception can interrupt a rung before its summary; sample attempts include
    cached replies and are not a provider-call counter. Preserve these limits.

    A native validation scope names the checks a candidate passed. For a schema-only or enum template those
    checks are only the declared type, so acceptance never establishes that the answer is correct.
    """
    attempts, filters = [], []
    for row in native.trace:
        if row.get('kind') == 'route-attempt':
            attempt = (row.get('ask') or {}).get('attempt') or {}
            attempts.append({'line': row.get('line'), 'app': attempt.get('app'), 'ok': attempt.get('ok') is True,
                             'sample_attempts': attempt.get('attempts'), 'cached_final_answer': attempt.get('cached'),
                             'error': attempt.get('error')})
        elif row.get('kind') == 'route-filter':
            filters.append({'line': row.get('line'), 'note': row.get('note')})
    accepted = [{'name': row['name'], 'selected': row['meta'].get('selected'),
                 'native_validation_scope': row['meta'].get('validation_scope')}
                for row in report.get('bindings') or []
                if (row.get('meta') or {}).get('route') in ('automatic', 'escalate')]
    error = report.get('error')
    return {**task['routing'], 'routing_id': task['routing_id'], 'calls': report.get('calls'),
            'model_budget': report.get('model_budget'), 'cached_requests': report.get('cached'),
            'attempts': attempts, 'attempt_scope': 'completed_rung_summaries_including_cached_samples',
            'trace_scope': trace_scope, 'trace_complete': trace_complete,
            'interrupted_rung_may_be_omitted': bool(report.get('error')) or report.get('status') != 'done', 'filters': filters,
            'accepted': accepted, 'budget_exhausted': isinstance(error, dict) and error.get('kind') == 'budget',
            'assurance_scope': task['assurance'].get('scope'), 'semantic_correctness': 'not_established'}


def run_task(body, *, applicators=None, by=None, folder=None, stop=None, log=None):
    """Run one template. A nonempty record directory refuses before dispatch."""
    request = D._copy(body)
    task = prepare(request, by=by)
    if folder is not None:
        directory = Path(folder)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise D.ContractError('record_exists', 'Use a new empty run directory; replay existing records explicitly.')
        for name, text in (
                ('program.sym', task['source']),
                ('meta.json', json.dumps({'inputs': task['inputs'], 'options': task['options'],
                                          'delegation': {'contract_id': task['contract_id'],
                                                         'template_id': task['template_id'],
                                                         'output_binding': task['output_binding'],
                                                         'assurance': task['assurance'],
                                                         'routing': task['routing'], 'routing_id': task['routing_id'],
                                                         'request': request}}))):
            path = directory / name
            with path.open('x', encoding='utf-8') as stream:
                stream.write(text)
            path.chmod(0o600)
    options = {**task['options'], 'side_effects': False}
    if stop is not None:
        options['stop'] = stop
    native = Run(task['source'], task['inputs'], applicators, options, folder=folder, log=log)
    report = native.execute()
    result = None
    if report['status'] == 'done':
        binding = native.kernel.env.lookup(task['output_binding'])
        if binding is None:
            raise D.ContractError('result_missing', 'Completed template did not bind its declared output.')
        result = S.canon(binding.value)
    return {'contract_id': task['contract_id'], 'routing_id': task['routing_id'],
            'template_id': task['template_id'],
            'status': report['status'], 'accepted': report['status'] == 'done',
            'output_encoding': task['output_encoding'], 'result': result,
            'assurance': task['assurance'], 'calls': report['calls'], 'error': report.get('error'),
            'routing': routing_record(task, native, report),
            **({'determinism_summary': report['determinism_summary']}
               if type(report.get('determinism_summary')) is dict else {}),
            'evidence': report.get('evidence'), 'report': report}


def main(argv=None):
    import argparse
    import signal
    import sys
    import threading
    parser = argparse.ArgumentParser(description='Compile and run agent delegation templates through Symblic.')
    parser.add_argument('command', choices=('catalog', 'check', 'compile', 'run'))
    parser.add_argument('path', nargs='?')
    parser.add_argument('--by', action='append', metavar='APPLICATOR',
                        help='a named applicator; repeat for an ordered route (default: the local ladder)')
    parser.add_argument('--dir')
    parser.add_argument('--template', action='append', metavar='NAME',
                        help='catalog only: return one exact registered template, without unrelated schemas')
    parser.add_argument('--json', '--agent-json', action='store_true', dest='json')
    args = parser.parse_args(argv)
    try:
        if args.template is not None and (args.command != 'catalog' or len(args.template) != 1):
            raise D.ContractError('catalog_selector', 'Use exactly one --template with catalog only.', 'template')
        if args.command == 'catalog':
            result = D.catalog() if args.template is None else D.catalog(args.template[0])
        else:
            if not args.path:
                parser.error('a task JSON file is required')
            with Path(args.path).open('rb') as stream:
                raw = stream.read(D.MAX_BYTES + 1)
            if len(raw) > D.MAX_BYTES:
                raise D.ContractError('bounds', 'Task file exceeds 512 KiB.')
            body = json.loads(raw)
            if args.command in ('check', 'compile'):
                result = D.inspect_task(body)
                if args.command == 'compile' and not args.json and result['ok']:
                    print(result['source'], end='')
                    return 0
            else:
                # Applicators dispatch only when native ask statements call them.
                from symblic.providers import applicators as symblic_apply
                apps = symblic_apply.Applicators(owner_label='operator (symblic delegate)',
                                                 run_id=Path(args.dir).name if args.dir else 'delegate-cli')
                stop = threading.Event()
                previous = {}

                def on_signal(*_args):
                    stop.set()

                try:
                    for signum in (signal.SIGTERM, signal.SIGINT):
                        try:
                            handler = signal.getsignal(signum)
                            signal.signal(signum, on_signal)
                            previous[signum] = handler
                        except (ValueError, OSError):
                            # main() can also be embedded in a non-main thread.
                            pass
                    by = args.by[0] if args.by and len(args.by) == 1 else args.by
                    result = run_task(body, applicators=apps, by=by, folder=args.dir, stop=stop,
                                      log=lambda text: print(text, file=sys.stderr, flush=True))
                finally:
                    stop.set()
                    try:
                        apps.cancel_all()
                    finally:
                        for signum, handler in previous.items():
                            signal.signal(signum, handler)
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 1 if result.get('ok') is False or result.get('accepted') is False else 0
    except (D.ContractError, S.SymblicError, OSError, ValueError) as error:
        detail = error.as_dict() if hasattr(error, 'as_dict') else {'message': str(error)}
        print(json.dumps({'ok': False, 'errors': [detail]}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

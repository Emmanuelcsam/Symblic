"""Step constructions: build a small program function by function, a model choosing each expression from a fixed list.

What it is for: the most constrained way to let a small model build a program. The author writes the steps: for each
function its name, parameters, return type, the earlier functions it may use, a list of candidate expressions
(`choices`) and checks; plus final checks over the whole program. compile_sequence(request, by) compiles one Symblic
program in which each step is one model request with a short, fresh context (the step's card, the cards of the
functions it uses) asking only for the NUMBER of the right choice; the kernel defines the function from that exact
expression and runs the step's checks, retrying with the failure. A model never writes code here, and this module never
interprets or ranks the choices. With finite_fallback=True the kernel may, after the model's retries fail, try the
author's choices in order and record that the host (not a model) selected that step.

prepare(request) validates a request before any model work; assemble(request, choices) builds the finished program
from the accepted choices (pure). Execution is symblic.kernel.run.Run's; symblic.steps.recovery reads a finished run
back and checks it, and symblic.authoring.workcards.run_card does compile, run and read-back in one call.

Example: examples/steps-parcel.json (13 parcel-pricing functions) with examples/steps-parcel-inputs.json; the assembled
result is examples/steps-parcel-built.sym.
Depends on: symblic.kernel.language, symblic.authoring.helpers, symblic.english.compiler (string-literal quoting).
"""
from __future__ import annotations

import hashlib
import json
import re

from symblic.kernel import language as S
from symblic.authoring import helpers as A
from symblic.english import compiler as E

VERSION = 4
OUTPUT_BINDING = 'steps_choices'
MAX_STEPS = 64
MAX_CHOICES = 16
MAX_CHECKS = 32
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
EXPRESSIONS = frozenset({'num', 'lit', 'str', 'name', 'list', 'set', 'record', 'range',
                         'un', 'bin', 'cmp', 'cond', 'quant', 'comp', 'attr', 'index', 'call'})
# Deliberately bounded first edition: no dynamic eval, adapters, effects, proofs,
# provider calls or user-defined callable other than the declared earlier steps.
BUILTINS = frozenset({'abs', 'ceil', 'floor', 'round', 'min', 'max', 'sum', 'product',
    'len', 'length', 'count', 'first', 'last', 'list', 'set', 'keys', 'zip', 'sort',
    'reverse', 'unique', 'contains', 'starts_with', 'ends_with', 'lower', 'upper',
    'trim', 'split', 'join', 'replace', 'text', 'number', 'words'})
# every engine the kernel knows, except `kernel` (it never answers an ask) and `council` (a group of agents)
PROVIDERS = frozenset(S.ENGINES) - {'kernel', 'council'}


class StepError(ValueError):
    pass


def _keys(value, required, optional=()):
    if type(value) is not dict or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise StepError('Expected fields: ' + ', '.join(required))


def _text(value, maximum=4096, *, empty=False):
    if type(value) is not str or (not empty and not value.strip()) or len(value.encode('utf-8')) > maximum:
        raise StepError('Expected bounded text')
    return value


def _name(value, *, parameter=False):
    if (type(value) is not str or not NAME.fullmatch(value) or value.startswith('brick_')
            or value == OUTPUT_BINDING or (not parameter and value in S.BUILTINS) or value in S.CONSTANTS
            or value.lower() in S.KEYWORDS or value.lower() in S.WORD_OPS):
        raise StepError('Expected a nonreserved native name')
    return value


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise StepError(f'Expected integer from {low} to {high}')
    return value


def _digest(value):
    return hashlib.sha256(A._raw(value)).hexdigest()


def _literal(value):
    # Native interpolation must not evaluate braces in caller strings.
    if type(value) is str:
        return E.native_string(value)
    if type(value) is list:
        return '[' + ', '.join(_literal(v) for v in value) + ']'
    if type(value) is dict:
        return '{' + ', '.join(k + ': ' + _literal(v) for k, v in value.items()) + '}' if value else '{:}'
    if type(value) is bool:
        return 'true' if value else 'false'
    if type(value) is int:
        return str(value)
    raise StepError('Unsupported compiler literal')


def _type(value):
    _text(value, 512)
    rows = S.parse('given brick_type: ' + value + '.', execution_profile='verified')['statements']
    if len(rows) != 1 or rows[0].k != 'given' or rows[0].name != 'brick_type' or rows[0].default is not None:
        raise StepError('Expected exactly one native type without a default')
    _closed_type(rows[0].type)
    return value


def _closed_type(value):
    if value is not None and any(n.k not in {'num', 'lit', 'str', 'list', 'set', 'record'}
                                 for n in S.walk(value)):
        raise StepError('Types must be closed native literal types')
    def visit(item):
        if type(item) is dict:
            if item.get('k') == 'named':
                raise StepError('Named external types are not supported by this closed compiler')
            for child in item.values():
                visit(child)
        elif type(item) in (list, tuple):
            for child in item:
                visit(child)
    visit(value)


def _expr(value, *, names=(), functions=()):
    _text(value)
    rows = S.parse('let brick_value = (' + value + ').', execution_profile='verified')['statements']
    if len(rows) != 1 or rows[0].k != 'let' or rows[0].name != 'brick_value':
        raise StepError('Expected one native expression')
    node = rows[0].value
    _expression(node, names=names, functions=functions)
    return node


def _expression(node, *, names, functions):
    if any(n.k not in EXPRESSIONS for n in S.walk(node)):
        raise StepError('Only pure native expressions are supported')
    if any(n.k == 'call' and n.fn not in BUILTINS and n.fn not in functions for n in S.walk(node)):
        raise StepError('Expression calls an undeclared or unsupported function')
    if S.free_names(node) - set(names) - set(S.CONSTANTS):
        raise StepError('Expression reads an undeclared name')


def _signature(step):
    return step['name'] + '(' + ', '.join(p['name'] + ': ' + p['type'] for p in step['parameters']) + ') -> ' + step['returns']


def _program(text, functions):
    """Validate the caller's pure artifact body, with native lexical flow."""
    _text(text, 65536, empty=True)
    parsed = S.parse(text, execution_profile='verified')['statements']

    def bind(ident, visible):
        _name(ident)
        if ident in functions or ident in visible:
            raise StepError('Program may not redefine a function or existing binding')
        visible.add(ident)

    def block(rows, available, nested=False):
        visible = set(available)
        for row in rows:
            if row.k in ('given', 'let'):
                _closed_type(row.type)
                if row.k == 'given':
                    if nested:
                        raise StepError('Program inputs must be top-level')
                    if row.default is not None:
                        _expression(row.default, names=visible, functions=functions)
                else:
                    _expression(row.value, names=visible, functions=functions)
                    if row.weight is not None:
                        raise StepError('Program binding weights are not supported')
                bind(row.name, visible)
            elif row.k == 'if':
                alternatives = []
                for condition, body in row.branches:
                    _expression(condition, names=visible, functions=functions)
                    alternatives.append(block(body, visible, True))
                alternatives.append(block(row.else_body, visible, True))
                visible |= set.intersection(*alternatives)
            elif row.k == 'for':
                _expression(row.src, names=visible, functions=functions)
                inside = set(visible)
                bind(row.var, inside)
                visible |= block(row.body, inside, True) - {row.var}
            elif row.k == 'assert':
                _expression(row.cond, names=visible, functions=functions)
                detail = getattr(row, 'because', None)
                if detail is not None:
                    _expression(detail, names=visible, functions=functions)
            elif row.k == 'show':
                _expression(row.value, names=visible, functions=functions)
                if row.label is not None:
                    _expression(row.label, names=visible, functions=functions)
            else:
                raise StepError('Program supports only pure given, let, if, for, assert and show statements')
        return visible

    block(parsed, set())


def prepare(request):
    """Preserve every authored option; reject invalid scope before any model work."""
    r = A._json_copy(request)
    _keys(r, ('title', 'steps', 'final_checks'), ('program',))
    _text(r['title'], 200)
    if type(r['steps']) is not list or not 1 <= len(r['steps']) <= MAX_STEPS:
        raise StepError('Provide one to 64 steps')
    known = set()
    for step in r['steps']:
        _keys(step, ('name', 'instruction', 'parameters', 'returns', 'uses', 'choices', 'checks'))
        ident = _name(step['name'])
        if ident in known:
            raise StepError('Step names must be unique')
        _text(step['instruction'], 2000)
        _type(step['returns'])
        if type(step['parameters']) is not list or len(step['parameters']) > 12:
            raise StepError('Provide at most 12 parameters')
        params = set()
        for param in step['parameters']:
            _keys(param, ('name', 'type'))
            pname = _name(param['name'], parameter=True)
            if pname in params or pname in known or pname == ident:
                raise StepError('Parameter names must be distinct from function names')
            params.add(pname)
            _type(param['type'])
        uses = step['uses']
        if (type(uses) is not list or len(uses) > 12 or any(type(n) is not str for n in uses)
                or len(set(uses)) != len(uses) or set(uses) - known):
            raise StepError('Uses must name distinct earlier accepted functions')
        choices = step['choices']
        if (type(choices) is not list or not 1 <= len(choices) <= MAX_CHOICES
                or any(type(v) is not str for v in choices) or len(set(choices)) != len(choices)):
            raise StepError('Provide one to 16 distinct exact expressions')
        for choice in choices:
            _expr(choice, names=params, functions=uses)
        checks = step['checks']
        if type(checks) is not list or not 1 <= len(checks) <= MAX_CHECKS:
            raise StepError('Every step needs one to 32 executable checks')
        for check in checks:
            node = _expr(check, functions=set(uses) | {ident})
            if not any(n.k == 'call' and n.fn == ident for n in S.walk(node)):
                raise StepError('Each step check must call its function')
        known.add(ident)
    checks = r['final_checks']
    if type(checks) is not list or not 1 <= len(checks) <= MAX_CHECKS:
        raise StepError('Provide one to 32 final checks')
    for check in checks:
        node = _expr(check, functions=known)
        if not any(n.k == 'call' and n.fn in known for n in S.walk(node)):
            raise StepError('Each final check must call a constructed function')
    r.setdefault('program', '')
    _program(r['program'], known)
    return r


def _checked(source):
    if len(source) > S.MAX_SOURCE:
        raise StepError('Compiled program exceeds the native source limit')
    result = S.check(source, execution_profile='verified')
    if not result['ok']:
        raise StepError('Native checker refused: ' + result['errors'][0]['message'])
    return result


def compile_sequence(request, by, *, retries=2, context_budget=12000, finite_fallback=False):
    task = prepare(request)
    if type(finite_fallback) is not bool:
        raise StepError('finite_fallback must be true or false')
    _int(retries, 0, 5)
    _int(context_budget, 1000, 100000)
    _text(by, 200)
    if not re.fullmatch(r'[A-Za-z0-9_.:/@+\-]+', by):
        raise StepError('Choose one exact provider')
    route = S.parse_applicator(by)
    if route['engine'] not in PROVIDERS or S.app_label(route) != by or '*' in by:
        raise StepError('Choose one exact provider')
    lines = ['use profile=verified, context=none, coercion=strict, effort=low, capsule=compact, '
             f'determine=false, solve=false, retries={retries}, budget={context_budget}.']
    inputs = {'_steps_request': A._json_copy(task),
              '_steps_settings': {'by': by, 'retries': retries, 'context_budget': context_budget}}
    if finite_fallback:
        inputs['_steps_settings']['finite_fallback'] = True
    indexes = {}
    for index, step in enumerate(task['steps']):
        indexes[step['name']] = index
        card = 'brick_card_' + str(index)
        choice = 'brick_choice_' + str(index)
        accepted = 'brick_accepted_' + str(index)
        # Put the exact task and alternatives in the actual instruction.
        # The named card identifies this contract without duplicating its menu.
        inputs[card] = {'signature': _signature(step)}
        instruction = (step['instruction'] + '\nFunction: ' + _signature(step)
                       + '\nChoose the expression that does exactly this task:\n'
                       + '\n'.join(step['choices'])
                       + '\nRequired examples: ' + '; '.join(step['checks'])
                       + '\nReturn the exact expression you choose. '
                         'Use any supplied accepted functions as written.')
        dependencies = [card] + ['brick_accepted_' + str(indexes[n]) for n in step['uses']]
        # Native enums require two options distinct under their presentation
        # normalization. Preserve singleton and exact-but-similar expressions
        # with a text answer and an exact membership predicate instead.
        native_enum = (len(step['choices']) >= 2
                       and len({S._norm_option(v) for v in step['choices']}) == len(step['choices']))
        # Type options are raw lexer string tokens, not interpolated expressions.
        choice_type = ('one of {' + ', '.join(json.dumps(v, ensure_ascii=False) for v in step['choices']) + '}'
                       if native_enum else 'Text up to 4096 words')
        lines += ['given ' + card + ': Any.',
                  'ask ' + choice + ': ' + choice_type
                  + ' ' + _literal(instruction) + ' from '
                  + ', '.join(dependencies) + ' by ' + _literal(by)
                  + ' with context=none, determine=false, solve=false, effort=low, capsule=compact'
                  + (', fallback_choices=' + _literal(step['choices']) if finite_fallback else '') + '.']
        body = '(' + step['choices'][-1] + ')'
        for i in range(len(step['choices']) - 1, 0, -1):
            body = f'if {choice} = {_literal(step["choices"][i - 1])} then ({step["choices"][i - 1]}) else ({body})'
        lines.append('function ' + _signature(step) + ' = ' + body + '.')
        # Native retry counters belong to ensures. One ordered conjunction gives
        # this candidate one shared correction budget across all authored checks.
        # The true equality guard anchors rollback to this exact choice binding.
        checks = ' and '.join('(' + check + ')' for check in step['checks'])
        guard = choice + ' = ' + choice if native_enum else choice + ' in ' + _literal(step['choices'])
        lines.append('ensure ' + guard + ' and ' + checks + ' else retry because '
                     + _literal('The selected expression must satisfy every check: '
                                + '; '.join(step['checks'])) + '.')
        lines.append('let ' + accepted + ' = {signature: ' + _literal(_signature(step))
                     + ', instruction: ' + _literal(step['instruction']) + ', expression: '
                     + choice + '}.')
    lines += ['assert (' + check + ').' for check in task['final_checks']]
    selected_indexes = []
    for index, step in enumerate(task['steps']):
        choice = 'brick_choice_' + str(index)
        selected = str(len(step['choices']))
        for i in range(len(step['choices']) - 1, 0, -1):
            selected = f'if {choice} = {_literal(step["choices"][i - 1])} then {i} else ({selected})'
        selected_indexes.append(step['name'] + ': (' + selected + ')')
    lines.append('let ' + OUTPUT_BINDING + ' = {' + ', '.join(selected_indexes) + '}.')
    lines.append('show ' + OUTPUT_BINDING + '.')
    source = '\n'.join(lines) + '\n'
    result = {'version': VERSION, 'kind': 'steps', 'task': task, 'request': task,
              'source': source, 'inputs': inputs, 'output_binding': OUTPUT_BINDING,
              'options': {'profile': 'verified', 'context': 'none', 'coercion': 'strict',
                          'effort': 'low', 'capsule': 'compact', 'determine': False, 'solve': False,
                          'constructor': 'off', 'side_effects': False, 'parallel': 1,
                          'max_calls': len(task['steps']) * (retries + 1),
                          'max_asks': len(task['steps']) * (retries + 1), 'context_budget': context_budget},
              'check': _checked(source),
              'assurance': 'Only authored predicates decide acceptance. They do not prove objective completeness.'}
    result['source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
    result['contract_id'] = _digest({'version': VERSION, 'task': task, 'by': by,
                                    'retries': retries, 'context_budget': context_budget,
                                    'source': source, 'inputs': inputs, 'options': result['options']})
    return result


def assemble(request, choices):
    """Build a pure artifact; parsing is not evidence that its assertions passed."""
    task = prepare(request)
    choices = A._json_copy(choices)
    if type(choices) is not dict or set(choices) != {s['name'] for s in task['steps']}:
        raise StepError('Supply exactly one choice index for every step')
    lines = ['use profile=verified, context=none, coercion=strict, determine=false, solve=false.']
    for step in task['steps']:
        selected = _int(choices[step['name']], 1, len(step['choices']))
        lines.append('function ' + _signature(step) + ' = (' + step['choices'][selected - 1] + ').')
        lines += ['assert (' + check + ').' for check in step['checks']]
    lines += ['assert (' + check + ').' for check in task['final_checks']]
    if task['program']:
        lines.append(task['program'])
    source = '\n'.join(lines) + '\n'
    return {'version': VERSION, 'kind': 'steps_artifact', 'status': 'prepared', 'execution': 'not_run',
            'source': source, 'inputs': {}, 'choices': choices, 'check': _checked(source),
            'options': {'profile': 'verified', 'max_calls': 0, 'max_asks': 0, 'side_effects': False,
                        'constructor': 'off', 'determine': False, 'solve': False},
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'contract_id': _digest({'version': VERSION, 'task': task, 'choices': choices})}

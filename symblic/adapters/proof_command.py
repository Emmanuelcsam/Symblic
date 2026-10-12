"""Proof commands: a short text format for proposing one inference of a proof session.

A small model writes one line instead of a JSON object, for example `premise human`, `implies_elim s1 s2` or
`or_left s3 :: "B"`. parse(state, command) translates the command into the session's candidate,
append(premises, goal, state, command) checks and appends it, frontier(state) lists what can be referenced, and
rules() describes the command language for the prompt.

Commands select every rule and argument explicitly. Formula rules require `::` followed by the existing
controlled formula syntax. Translation neither searches nor fills in missing arguments or formulas; the
session's append and the step checker (symblic.adapters.proof_session.append,
symblic.adapters.proof_steps.verify) remain authoritative. Every entry point except rules() accepts an optional
host tick (a callback that charges the kernel's step budget). See docs/reference/PROOF-COMMANDS.md.

Depends on: symblic.adapters.proof, proof_session, proof_steps. Used by: symblic.adapters.proof_adapter and the
delegation templates.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import re

from symblic.adapters import proof as P
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W

VERSION = 1
MAX_COMMAND_BYTES = P.MAX_BYTES
MAX_FRONTIER_BYTES = 2 * P.MAX_BYTES
_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
_LINE = re.compile(r's[1-9][0-9]{0,2}\Z')
HINTS = {
    'command_type': 'Return one command as a text string.',
    'command_line': 'Return one physical line, without a second command, comment or code fence.',
    'command_id': 'Use exact current premise names or host line IDs; do not declare an ID.',
    'command_formula': 'This rule needs :: followed by one complete controlled formula.',
    'syntax': 'Quote propositions as JSON strings; use false, not, and, or, implies and parentheses.',
    'unexpected_formula': 'This rule takes no formula or :: delimiter.',
}


def _parse(command, tick):
    charge = W._charger(tick)
    charge(1)
    if type(command) is not str:
        P._fail('command_type')
    if len(command) > MAX_COMMAND_BYTES:
        P._fail('byte_limit')
    try:
        if len(command.encode('utf-8')) > MAX_COMMAND_BYTES:
            P._fail('byte_limit')
    except UnicodeError:
        P._fail('unicode')
    charge(len(command))
    if any(char in command for char in ('\n', '\r', '\x85', '\u2028', '\u2029')):
        P._fail('command_line')
    text = command.strip(' \t')
    first = re.match(r'([a-z_]+)(?:[ \t]+|(?=::)|$)', text)
    if first is None or first[1] not in W.ARITIES:
        P._fail('rule')
    rule = first[1]
    rest = text[first.end():].strip(' \t')
    formula = None
    if rule in W.FORMULA_RULES:
        head, delimiter, formula_text = rest.partition('::')
        if not delimiter or not formula_text.strip(' \t'):
            P._fail('command_formula')
        rest = head.strip(' \t')
        formula = P.parse_formula(formula_text)
    elif rule != 'premise' and '::' in rest:
        P._fail('unexpected_formula')
    if rule == 'premise' and rest.startswith('"'):
        # A quoted exact premise name preserves the pure session API's Unicode
        # and whitespace names; compiler-generated names use the shorter form.
        try:
            name, end = json.JSONDecoder().raw_decode(rest)
        except ValueError:
            P._fail('command_id')
        if type(name) is not str or not name or rest[end:].strip(' \t'):
            P._fail('command_id')
        args = [name]
    else:
        args = re.split(r'[ \t]+', rest) if rest else []
        if len(args) != W.ARITIES[rule]:
            P._fail('rule_arity')
        pattern = _NAME if rule == 'premise' else _LINE
        if any(not pattern.fullmatch(arg) for arg in args):
            P._fail('command_id')
    candidate = {'rule': rule, 'args': args, 'formula': formula}
    W._scan(candidate, charge)
    return candidate


def parse(state, command, *, tick=None):
    """Translate one command against a rechecked current session, without inference.

    Unknown references raise the same finite reference codes as append. A
    translated candidate is not an acceptance receipt; append still checks it.
    """
    view = R.frontier(state, tick=tick)
    if view['complete']:
        P._fail('session_complete')
    if view['next_id'] is None:
        P._fail('step_limit')
    candidate = _parse(command, tick)
    if candidate['rule'] == 'premise':
        if candidate['args'][0] not in view['premises']:
            P._fail('unknown_premise')
    elif any(arg not in {line['id'] for line in view['lines']} for arg in candidate['args']):
        P._fail('unknown_or_forward_reference')
    return candidate


def append(premises, goal, state, command, *, tick=None):
    """Translate then call unchanged R.append; syntax refusal preserves checked state.

    A syntax error cannot hide a foreign/invalid state or already completed
    session. R.append establishes refusal precedence and rechecks retained state.
    Host budget exceptions always propagate.
    """
    problem = None
    try:
        candidate = _parse(command, tick)
    except P.ProofError as error:
        problem, candidate = str(error), None
    result = R.append(premises, goal, state, candidate, tick=tick)
    if problem is not None and result['rejected'] == 'candidate':
        result.update(error=problem, hint=HINTS.get(problem, R.HINTS.get(problem)))
    return result


def frontier(state, *, tick=None):
    """The same checked proof information, with exact controlled-text formulas.

    Every rendered formula reparses to its existing AST. IDs, rule names, free
    assumptions, order, completion and remaining steps are preserved. No next
    inference, target certificate or simplification is added.
    """
    view = R.frontier(state, tick=tick)
    charge = W._charger(tick)

    def render(formula):
        W._scan(formula, charge)
        text = P.render_formula(formula)
        for separator in ('\x85', '\u2028', '\u2029'):
            text = text.replace(separator, json.dumps(separator, ensure_ascii=True)[1:-1])
        if len(text.encode('utf-8')) > MAX_COMMAND_BYTES:
            P._fail('byte_limit')
        charge(len(text))
        return text

    view['goal'] = render(view['goal'])
    view['premises'] = {name: render(formula) for name, formula in view['premises'].items()}
    view['lines'] = [{**line, 'formula': render(line['formula'])} for line in view['lines']]
    encoded = json.dumps(view, ensure_ascii=False).encode('utf-8')
    if len(encoded) > MAX_FRONTIER_BYTES:
        P._fail('output_limit')
    return view


def rules():
    """Generic syntax/rule descriptions, independent of the caller's task."""
    return {
        'version': VERSION,
        'wire': 'The answer value is one text command on one physical line. Preserve the enclosing native '
                'response object and its schema. Do not put a proof-step object, code fence, comment or '
                'assigned ID inside the answer value.',
        'commands': [
            'premise NAME', 'assume :: FORMULA', 'implies_intro ASSUME_LINE BODY_LINE',
            'implies_elim IMPLICATION_LINE ANTECEDENT_LINE', 'and_intro LEFT_LINE RIGHT_LINE',
            'and_left CONJUNCTION_LINE', 'and_right CONJUNCTION_LINE',
            'or_left LEFT_LINE :: RIGHT_FORMULA', 'or_right RIGHT_LINE :: LEFT_FORMULA',
            'or_elim OR_LINE LEFT_ASSUME LEFT_BODY RIGHT_ASSUME RIGHT_BODY',
            'false_elim FALSE_LINE :: TARGET_FORMULA'],
        'references': 'NAME is an exact key in frontier.premises; quote it as a JSON string if needed. '
                      'Use JSON escapes for line breaks in quoted names. '
                      'Every LINE is an exact existing frontier.lines id. The host assigns next_id.',
        'formulas': 'Use the controlled text displayed in the frontier: JSON-double-quoted opaque propositions, '
                    'false, not, and, or, implies, and parentheses. Precedence high to low: not, and, or, implies. '
                    'Implication associates right. A quoted "false" is an atom; bare false is falsity. '
                    'Use JSON escapes inside an atom for line breaks; never a literal newline in the command.',
        'rules': [{'rule': rule['rule'], 'gives': rule['gives']} for rule in R.rules()['rules']],
        'semantics': R.rules()['semantics'],
        'unrelated_example': {'frontier': {'goal': '"An unrelated sample flag"',
            'premises': {'sample': '"An unrelated sample flag"'}, 'lines': [], 'next_id': 's1',
            'complete': False, 'steps_left': W.MAX_STEPS}, 'command': 'premise sample'},
    }

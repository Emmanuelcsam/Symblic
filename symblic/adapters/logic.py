"""Human logic to proof tasks: compile named premises and a goal into a checked, model-constructed proof task.

    compile_task({'premises': [{'name': 'human', 'formula': '"Socrates is human"'},
                               {'name': 'rule', 'formula': '"Socrates is human" implies "Socrates is mortal"'}],
                  'goal': '"Socrates is mortal"', 'calls': 2})

compile_task() parses the premises and goal (quoted atomic statements combined with and, or, not, implies;
finite quantifiers over declared domains) and returns a Symblic program in which a model constructs a proof
certificate that the kernel then checks (symblic.adapters.proof, proof_steps, proof_session). formal_reading()
renders the parsed task back as text, so a person can confirm what was understood.

Compilation parses the supplied propositions; it neither discovers the author's intended meaning nor
searches for a proof. No models, stores or effects.

Depends on: symblic.kernel.language and the proof adapters (symblic.adapters.proof, proof_command,
proof_session, proof_steps, finite_logic). Used by: the delegation templates (symblic.delegate) and front ends.
"""

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import re
import unicodedata

from symblic.kernel import language as S
from symblic.adapters import finite_logic as F
from symblic.adapters import proof as P
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W

VERSION = 5
_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
RULES = {
    'certificate': {'version': 1, 'proof': 'a proof term from the rules below'},
    'terms': [
        ['premise', 'caller-supplied premise name'],
        ['hypothesis', 'name of a currently scoped assumption'],
        ['implies_intro', 'fresh name', 'assumed formula', 'body proof term'],
        ['implies_elim', 'proof of A implies B', 'proof of A'],
        ['and_intro', 'proof of A', 'proof of B'],
        ['and_left', 'proof of A and B'], ['and_right', 'proof of A and B'],
        ['or_left', 'proof of A', 'formula B'], ['or_right', 'proof of B', 'formula A'],
        ['or_elim', 'proof of A or B', 'fresh left name', 'proof of C assuming A',
         'fresh right name', 'proof of C assuming B'],
        ['false_elim', 'proof of false', 'target formula'],
    ],
    'formulas': [['atom', 'exact proposition text'], ['false'],
                 ['implies', 'A', 'B'], ['and', 'A', 'B'], ['or', 'A', 'B']],
    'semantics': 'Intuitionistic propositional natural deduction. Names cannot shadow premises or assumptions. '
                 'Premise and hypothesis names are different rules. Do not invent premises. '
                 'Negation is implication to false. Premise truth and consistency are not checked.',
}
STEPS_RULES = {
    'certificate': {'version': 1, 'steps': 'list of uniform inference records', 'result': 'final step id'},
    'step': {'id': 'unique ASCII letter then letters/digits/underscores; maximum 64 characters',
             'rule': 'one of the rules below', 'args': 'list of argument names',
             'formula': 'null except for assume, or_left, or_right and false_elim'},
    'rules': [
        {'rule': 'premise', 'args': ['external premise name'], 'formula': None},
        {'rule': 'assume', 'args': [], 'formula': 'assumed formula'},
        {'rule': 'implies_intro', 'args': ['assume step', 'body step'], 'formula': None},
        {'rule': 'implies_elim', 'args': ['implication step', 'antecedent step'], 'formula': None},
        {'rule': 'and_intro', 'args': ['left step', 'right step'], 'formula': None},
        {'rule': 'and_left', 'args': ['conjunction step'], 'formula': None},
        {'rule': 'and_right', 'args': ['conjunction step'], 'formula': None},
        {'rule': 'or_left', 'args': ['left step'], 'formula': 'other/right formula'},
        {'rule': 'or_right', 'args': ['right step'], 'formula': 'other/left formula'},
        {'rule': 'or_elim', 'args': ['disjunction step', 'left assume step', 'left body step',
                                   'right assume step', 'right body step'], 'formula': None},
        {'rule': 'false_elim', 'args': ['false step'], 'formula': 'target formula'},
    ],
    'formulas': RULES['formulas'],
    'semantics': 'Only backward step references are allowed, except premise names read the external premises. '
                 'Discharge references must name assume steps. Disjunction branches have distinct assumptions '
                 'matching the corresponding disjunct; branches cannot read each other\'s free assumptions. '
                 'The final result must have no free assumptions and exactly match goal. Vacuous discharge is valid. '
                 'Never replace the caller premises or goal. Formula is literal JSON null for rules not requiring it. '
                 'Atoms are opaque; premise truth and consistency are not checked.',
    'unrelated_example': {
        'premises': {'sample': ['atom', 'An unrelated sample flag']},
        'goal': ['atom', 'An unrelated sample flag'],
        'certificate': {'version': 1, 'steps': [{'id': 's', 'rule': 'premise', 'args': ['sample'], 'formula': None}],
                        'result': 's'}},
}
TERM_TYPE = 'Record {version: Int in 1..1, proof: List of Any length 2..6}'
STEPS_TYPE = ('Record {version: Int in 1..1, steps: List of Record {id: Text, rule: one of {'
              + ', '.join(W.ARITIES) + '}, args: List of Text length 0..5, formula: Any} length 1..512, result: Text}')


def _quoted(text):
    """Keep ordinary Unicode readable, but make directional/control text visible."""
    encoded = json.dumps(text, ensure_ascii=False)
    return ''.join(json.dumps(char, ensure_ascii=True)[1:-1]
                   if unicodedata.category(char) in ('Cf', 'Cs', 'Zl', 'Zp') else char
                   for char in encoded)


def formal_reading(formula):
    """Render a parsed formula with every connective and quantifier scope explicit.

    Called only after the bounded propositional/finite parsers validate the tree.
    The displayed reading is derived from that tree, never copied from source.
    """
    op = formula[0]
    if op == 'atom':
        return _quoted(formula[1])
    if op == 'false':
        return 'false'
    if op in ('forall', 'exists'):
        return f'({op} {formula[1]} in {formula[2]}: {formal_reading(formula[3])})'
    if op == 'pred':
        args = [f'{term[1]}:{term[2]}' if term[0] == 'var'
                else f'{term[1]}[{_quoted(term[2])}]' for term in formula[2]]
        return formula[1] + '(' + ', '.join(args) + ')'
    return '(' + formal_reading(formula[1]) + ' ' + op + ' ' + formal_reading(formula[2]) + ')'


def _incremental_source(finite, step_limit, calls, inference_format="json"):
    """Unroll bounded immutable sessions; every accepted line gets a fresh task card.

    The model supplies one inference, never a replacement state or its own id.
    Branches bind the same final certificate only when their proof completes.
    A partial proof or exhausted budget cannot reach the final acceptance check.
    """
    command = inference_format == 'command'
    candidate_type = 'Text' if command else R.CANDIDATE_TYPE
    frontier_function = 'proof_command_frontier' if command else 'proof_session_frontier'
    append_function = 'proof_session_command' if command else 'proof_session_append'
    wire_instruction = ('Return one command string as the answer value, preserving the native outer response schema. '
                        'Use the syntax in proof_rules. ' if command else '')
    lines = ['program Construct a logical derivation one inference at a time.',
             'use profile=verified.',
             'given premises: Any.', 'given goal: Any.', 'given proof_rules: Any.']
    premises, goal = 'premises', 'goal'
    if finite:
        lines.extend(['given domains: Any.', 'let expanded = finite_expand(domains, premises, goal).'])
        premises, goal = 'expanded.premises', 'expanded.goal'
    lines.append(f'let session0 = proof_session_start({premises}, {goal}).')
    for index in range(1, step_limit + 1):
        indent = '  ' * (index - 1)
        prior = 'session0' if index == 1 else f'inference{index - 1}.state'
        raw = f'raw_frontier{index}'
        frontier = f'frontier{index}'
        candidate = f'candidate{index}'
        result = f'inference{index}'
        statements = [
            f'let {raw} = {frontier_function}({prior}).',
            (f'let {frontier} = {{goal: {raw}.goal, premises: {raw}.premises, lines: {raw}.lines, '
             f'next_id: {raw}.next_id, complete: {raw}.complete, steps_left: {step_limit - index + 1}}}.'),
            (f'ask {candidate}: {candidate_type} "{wire_instruction}Propose exactly one next inference toward the goal in '
             f'{frontier}. Follow proof_rules. Use only named premises or prior lines in the frontier. '
             'The host assigns next_id and checks every inference. Do not return a proof, state, id or new premises. '
             'Proposition text is opaque; no unstated facts are available." '
             f'from {frontier}, proof_rules with context=none, effort=low, route=escalate, '
             f'retries={min(2, calls - 1)}, budget=24000'),
            f'let {result} = {append_function}({premises}, {goal}, {prior}, {candidate}).',
            f'ensure {result}.valid else retry because [{result}.error, {result}.hint].',
        ]
        if index < step_limit:
            statements.extend([f'if {result}.complete then',
                               f'  let certificate = {result}.certificate.', 'else'])
        else:
            statements.extend([(f'assert {result}.complete because "Proof step limit reached without a complete '
                                'derivation; the goal remains unresolved.".'),
                               f'let certificate = {result}.certificate.'])
        lines.extend(indent + line for line in statements)
    for depth in range(step_limit - 2, -1, -1):
        lines.append('  ' * depth + 'end.')
    check = ('finite_steps_check(domains, premises, goal, certificate)' if finite
             else 'proof_steps_check(premises, goal, certificate)')
    lines.extend([f'let verification = {check}.', 'assert verification.valid.', 'show verification.'])
    return '\n'.join(lines) + '\n'


def compile_task(body):
    if type(body) is not dict or set(body) - {'premises', 'goal', 'calls', 'domains', 'certificate_format', 'step_limit', 'inference_format'}:
        raise ValueError('A logic task takes premises, goal, optional finite domains, certificate format, '
                         'call budget, incremental step limit and optional inference format.')
    certificate_format = body.get('certificate_format', 'terms')
    if type(certificate_format) is not str or certificate_format not in ('terms', 'steps', 'incremental'):
        raise ValueError('Certificate format must be terms, steps or incremental.')
    incremental = certificate_format == 'incremental'
    inference_format = body.get('inference_format', 'json')
    if type(inference_format) is not str or inference_format not in ('json', 'command'):
        raise ValueError('Inference format must be json or command.')
    if not incremental and 'inference_format' in body:
        raise ValueError('An inference format applies only to incremental proof construction.')
    if not incremental and 'step_limit' in body:
        raise ValueError('A step limit applies only to incremental proof construction.')
    step_limit = body.get('step_limit', 16) if incremental else None
    if incremental and (type(step_limit) is not int or not 1 <= step_limit <= 32):
        raise ValueError('Proof step limit must be an integer from 1 to 32.')
    finite = 'domains' in body
    domains = body.get('domains')
    parser = F.parse_formula if finite else P.parse_formula
    raw = body.get('premises')
    if type(raw) is str:
        if len(raw) > 32768:
            raise ValueError('Premises are limited to 32768 characters.')
        rows = []
        for line, text in enumerate(raw.splitlines(), 1):
            if not text.strip():
                continue
            name, sep, formula = text.partition(':')
            if not sep:
                raise ValueError(f'Premise line {line} needs a name followed by a colon and a formula.')
            rows.append({'name': name.strip(), 'formula': formula.strip()})
    elif type(raw) is list:
        rows = raw
    else:
        raise ValueError('Premises must be named formula lines or a list of named formulas.')
    if len(rows) > 64:
        raise ValueError('At most 64 named premises are supported in one task.')
    premises = {}
    shown = []
    try:
        for index, row in enumerate(rows, 1):
            if type(row) is not dict or set(row) != {'name', 'formula'}:
                raise ValueError(f'Premise {index} needs exactly name and formula.')
            name = row['name']
            if type(name) is not str or not _NAME.fullmatch(name) or name in premises:
                raise ValueError(f'Premise {index} has an invalid or repeated name.')
            premises[name] = parser(row['formula'])
            shown.append({'name': name, 'formula': formal_reading(premises[name])})
        goal = parser(body.get('goal'))
        goal_text = formal_reading(goal)
        if finite:
            F.expand(domains, premises, goal)
    except (P.ProofError, F.FiniteLogicError) as error:
        raise ValueError(f'Formal formula error: {error}. Quote proposition text and use and/or/implies/not.') from None
    calls = body.get('calls', 32 if incremental else 4)
    call_limit = 64 if incremental else 6
    if type(calls) is not int or not 1 <= calls <= call_limit:
        raise ValueError(f'Call budget must be an integer from 1 to {call_limit}.')
    rules = ((C.rules() if inference_format == 'command' else R.rules()) if incremental
             else STEPS_RULES if certificate_format == 'steps' else RULES)
    inputs = {'premises': premises, 'goal': goal, 'proof_rules': json.loads(json.dumps(rules))}
    if finite:
        inputs['domains'] = domains
    if len(json.dumps(inputs, ensure_ascii=False).encode()) > P.MAX_BYTES:
        raise ValueError('Combined logic task exceeds the proof input limit.')
    # The instruction contains no target proof, expected certificate or search
    # result. The model must construct the witness; generic rules are task data.
    source = (
        'program Construct a logical derivation.\n'
        'use profile=verified.\n'
        'given premises: Any.\ngiven goal: Any.\ngiven proof_rules: Any.\n'
        'ask certificate: Any "Construct a proof term deriving goal from the named premises. '
        'Follow proof_rules exactly. Return the certificate as the answer. Every inference will be checked. '
        'A proposition that looks like ordinary English is an opaque atom; no extra premises are available." '
        f'from premises, goal, proof_rules with effort=low, route=escalate, retries={calls-1}, budget=24000\n'
        'let verification = proof_check(premises, goal, certificate).\n'
        'ensure verification.valid else retry because "Supply a valid derivation under the exact premises and goal.".\n'
        'show verification.\n'
    )
    source = source.replace('ask certificate: Any', 'ask certificate: ' + TERM_TYPE)
    if certificate_format == 'steps':
        source = source.replace('ask certificate: ' + TERM_TYPE, 'ask certificate: ' + STEPS_TYPE)
        source = source.replace('Construct a proof term deriving', 'Construct a flat line-by-line proof deriving')
        source = source.replace('proof_check(premises, goal, certificate)', 'proof_steps_check(premises, goal, certificate)')
    if finite:
        source = source.replace('given proof_rules: Any.\n',
            'given proof_rules: Any.\ngiven domains: Any.\nlet expanded = finite_expand(domains, premises, goal).\n')
        source = source.replace('deriving goal from the named premises.',
                                'deriving expanded.goal from expanded.premises.')
        source = source.replace('from premises, goal, proof_rules', 'from expanded, proof_rules')
        function = 'proof_steps_check' if certificate_format == 'steps' else 'proof_check'
        finite_function = 'finite_steps_check' if certificate_format == 'steps' else 'finite_check'
        source = source.replace(function + '(premises, goal, certificate)',
                                finite_function + '(domains, premises, goal, certificate)')
    if incremental:
        source = _incremental_source(finite, step_limit, calls, inference_format)
    checked = S.check(source, execution_profile='verified')
    if not checked['ok']:
        raise ValueError('The logic runtime is not compatible with this compiler: ' + checked['errors'][0]['message'])
    identity = json.dumps([VERSION, F.LOGIC if finite else P.LOGIC, certificate_format, domains, premises, goal, rules], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    if incremental:
        identity = json.dumps([identity, R.VERSION, step_limit, calls, inference_format,
                               C.VERSION if inference_format == 'command' else None], ensure_ascii=False, separators=(',', ':'))
    return {'version': VERSION, 'source': source, 'inputs': inputs,
            'options': {'profile': 'verified', 'max_calls': calls, 'parallel': 1},
            'formalization': {'premises': shown, 'goal': goal_text, 'logic': F.LOGIC if finite else P.LOGIC,
                              'certificate_format': certificate_format,
                              **({'step_limit': step_limit, 'inference_format': inference_format} if incremental else {}),
                              'domains': domains if finite else None,
                              'sha256': hashlib.sha256(identity.encode()).hexdigest()},
            'assurance': 'A checked derivation is conditional on the supplied premises and any declared finite domains. '
                         'Failure to construct one does not prove the goal false.',
            'check': checked}

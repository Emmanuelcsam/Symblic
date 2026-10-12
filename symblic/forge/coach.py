"""Forge coach: help a person write one atomic construction instruction that a fresh agent can carry out.

What it is for
    A good instruction names one observable change, its exact input and output, a check with an expected
    observation, and only the context it needs. preview(project, fields) turns the person's draft (text,
    input, output, check, context, optional construction links) into a proposed atomic statement and unit and
    explains what is missing (EXPLANATIONS); lens() offers ideation prompts; overview(project) summarizes the
    coaching state; EXAMPLES are teaching drafts (a Snake movement step, a latency chart, ...) that also serve
    as a reproducible test corpus. The resulting 'coach.propose' transition is applied by the store, and like
    every Forge proposal it stays proposed until the operator accepts it.

Depends on: symblic.forge.core and symblic.forge.catalog. Used by: symblic.forge.core (coach.propose),
symblic.forge.models (refinement prompts) and the original host's Forge routes. Status: prototype; tested by
tests/forge/test_symblic_forge_coach_construction.py. No model call, store or file access here.
"""
from __future__ import annotations

from copy import deepcopy
import re

from symblic.forge import catalog as Catalog
from symblic.forge import core as C

EXPLANATIONS = [
    'Name one observable change rather than a promise to investigate or a list of unrelated tasks.',
    'Name the exact input and output so a fresh agent does not need the previous conversation.',
    'State a check with an expected observation; running a command alone is not proof of success.',
    'List only the context needed for this instruction. Files may persist; hidden chat history is not an input.',
    'Finish closes this instruction after its check. A complete form is a proposal, not a passed check or compiler proof.',
]

# Teaching inputs, never accepted requirements or model-quality receipts. These
# exact drafts also form a reproducible authoring/export corpus in isolated tests.
EXAMPLES = [
    ('game', 'A pure Snake movement step', 'Make the snake move.',
     'compute one Snake movement step without rendering or writing files.',
     'the current ordered body cells and requested direction', 'the next ordered body cells',
     'for body [(2,2),(1,2)] moving right without growth, return [(3,2),(2,2)]',
     ['Illustrative example only: one square cell per step; collision and food belong to separate instructions']),
    ('data', 'A file transformation', 'Make my data cleaner.',
     'validate one supplied CSV row against the declared schema.',
     'one CSV row and its explicit column/type schema', 'either a typed record or a field-specific validation error',
     'an invalid numeric field produces the named field error and no partial accepted record',
     ['Illustrative example only: no external lookup, file writes or inferred missing values']),
    ('recovery', 'An interruption check', 'Make saving robust.',
     'test recovery after the supplied save operation is interrupted.',
     'the save contract, temporary test store and interruption fixture', 'a reproducible recovery test and its observed result',
     'after interruption, observe exactly the old complete record or the new complete record, never a partial record',
     ['Illustrative example only: isolated temporary data; the project must explicitly choose this invariant']),
    ('debugging', 'A reproducible code repair', 'Debug the application.',
     'repair the supplied sum_prices function while preserving its declared interface.',
     'src/prices.py with def sum_prices(items): return sum(items[:-1]); tests use numeric lists only',
     'a patch to src/prices.py and an isolated regression test',
     'sum_prices([]) returns 0; sum_prices([5]) returns 5; sum_prices([2,3,4]) returns 9; input lists are unchanged',
     ['Only the supplied function and these acceptance cases; no live files or external services']),
    ('website', 'A responsive website component', 'Make a new website.',
     'build a local pricing-card component in web/pricing.html and web/pricing.css.',
     'three plans: Basic $0, Studio $12, Team $30; each has a label and a Select button',
     'a semantic pricing section with three cards, keyboard focus and responsive layout',
     'at 390 px and 1280 px viewport widths all three plans are visible with no horizontal overflow; Tab reaches each Select button with visible focus',
     ['Use local HTML/CSS only; no purchase, network request, invented benefits or external fonts']),
    ('math', 'An exact quadratic solution', 'Solve the math problem.',
     'derive all real roots of x^2 - 5*x + 6 = 0 using exact arithmetic.',
     'the polynomial coefficients 1, -5, 6', 'a sorted set of roots and an algebraic completeness argument',
     'substitution gives zero for each root; the two linear factors multiply to the original polynomial; report roots {2,3}',
     ['Only this polynomial and exact arithmetic; numerical agreement alone is not a completeness proof']),
    ('visualization', 'A data-faithful visualization', 'Make a useful chart.',
     'render a labelled local bar chart for the supplied measurements.',
     'categories A, B, C with values 2, 5, 3 milliseconds',
     'web/latency.html with one labelled bar per category and an accessible data table',
     'labels and table retain 2, 5, 3 ms in A/B/C order; the zero baseline is visible; no value or unit is inferred',
     ['Only the supplied synthetic measurements; no claim that they are live benchmarks']),
    ('program', 'A bounded command-line program', 'Make a new program.',
     'implement a pure word-count command reading UTF-8 text from standard input.',
     'whitespace-separated text; empty input is valid', 'count_words.py that prints one integer and a newline',
     'empty input prints 0; input alpha beta followed by a newline prints 2; the program neither opens files nor uses the network',
     ['Use the Python standard library; count whitespace-separated fields without claiming linguistic tokenization']),
    ('planning', 'A checked dependency schedule', 'Solve a complex planning problem.',
     'construct a minimum-makespan schedule for the supplied finite task graph on two identical workers.',
     'A takes 2 ticks; B takes 3 ticks; C takes 1 tick after both A and B; tasks are indivisible and start at tick 0 or later',
     'start/end ticks and worker assignment for A, B and C, with a lower-bound argument',
     'A and B may overlap on different workers; C starts no earlier than tick 3; completion at tick 4 matches the dependency-path lower bound',
     ['Only three deterministic tasks and two workers; no setup cost, communication delay or stochastic duration']),
    ('cad', 'A dimensioned cup and STL', 'Describe and build a cup.',
     'construct a handleless open-top cylindrical cup in a temporary CAD project.',
     'outer radius 40 mm, outer height 100 mm, uniform wall 3 mm, base 4 mm; z=0 is the outer bottom',
     'cup.step and cup.stl plus a dimensional and mesh-check report',
     'the cavity radius is 37 mm and its floor is z=4 mm; it extends through the top at z=100 mm; the material mesh is watertight with no non-manifold edges and positive volume',
     ['Only the supplied geometry; record actual CAD/mesh tool and tessellation tolerance; no food-safety, strength or manufacturing claim']),
    ('machine', 'A bounded machine motion component', 'Design a machine.',
     'simulate one bounded linear stage controller as a pure state transition.',
     'position in integer millimeters from 0 through 100; command delta is -1, 0 or 1; emergency stop is a Boolean',
     'stage.py with a pure next_position function and exhaustive finite-state checks',
     'for every allowed position and delta the result stays in [0,100]; emergency stop preserves the current position; no hardware is actuated',
     ['An illustrative kinematic state model only; excludes dynamics, electrical design and physical safety validation']),
]


def lens(identifier=''):
    if type(identifier) is not str:
        raise C.ForgeError('Choose a named ideation lens.')
    if not identifier:
        return None
    found = next((row for row in Catalog.IDEATION_LENSES if row['id'] == identifier), None)
    if found is None:
        raise C.ForgeError('Choose a named ideation lens.')
    return deepcopy(found)


def atomic_block(text, input_, output, check, context):
    return '\n'.join([
        'Ask the model to ' + (text or '[Specify one bounded action]'),
        'Use only this input: ' + (input_ or '[Specify the input]') + '. Context: ' +
        ('; '.join(context) if context else '[Specify the bounded context, or explicitly state no additional context]'),
        'Produce: ' + (output or '[Specify the observable output]'),
        'Check: ' + (check or '[Specify the check and expected observation]'),
        'Finish this step.',
    ])


def granularity(text):
    hints = []
    if len(re.findall(r'(?i)\b(?:then|also|after that|and then)\b', text)) or len(text.splitlines()) > 1:
        hints.append('This may contain several actions. Split independent outputs into separate instructions; keep necessary dependencies explicit.')
    if re.search(r'(?i)\b(?:nice|good|better|simple|fast|robust|user.friendly)\b', text):
        hints.append('Replace subjective adjectives with the behavior, bound or observable condition you intend.')
    if re.search(r'(?i)\b(?:all (?:prior|previous) context|(?:the )?whole conversation)\b', text):
        hints.append('Replace broad conversation references with the exact facts, paths or source identifiers needed here.')
    return hints


def preview(project, fields):
    project = C.validate_project(project)
    C._keys(fields, (), ('text', 'input', 'output', 'check', 'context', 'source_ids', 'lens', 'edited_text', 'construction'))
    values = {name: C._text(fields.get(name, ''), empty=True, limit=8000) for name in ('text', 'input', 'output', 'check')}
    contexts = C._list(fields.get('context', []), maximum=30)
    for item in contexts:
        C._text(item, limit=2000)
    source_ids = C._strings(fields.get('source_ids', []), identifiers=True)
    branch = C.active_branch(project)
    accepted = {row['id'] for row in branch['statements'] if row['status'] == 'accepted'}
    accepted.update(row['id'] for rows in branch['entities'].values() for row in rows if row['status'] == 'accepted')
    C._require(set(source_ids) <= accepted, 'Coaching source identifiers must name explicitly accepted current records.')
    selected_lens = lens(fields.get('lens', ''))
    missing = [name for name, value in values.items() if not value.strip()]
    if not contexts:
        missing.append('context')
    broad_context = any(re.search(r'(?i)\b(?:all (?:prior|previous) context|(?:the )?whole conversation)\b', item)
                        for item in [values['input'], *contexts])
    if broad_context:
        missing.append('bounded_context')
    after = atomic_block(values['text'], values['input'], values['output'], values['check'], contexts)
    if 'edited_text' in fields:
        after = C._text(fields['edited_text'], limit=C.MAX_TEXT)
    C._require(len(after) <= C.MAX_TEXT, 'The atomic instruction exceeds the retained statement limit.')
    construction = None
    if 'construction' in fields:
        selected = fields['construction']
        C._keys(selected, ('component_id',), ('dependencies', 'paths'))
        component = C._find(branch['entities']['components'], selected['component_id'])
        C._require(component['status'] == 'accepted', 'Choose an accepted component for the construction unit.')
        dependencies = C._strings(selected.get('dependencies', []), identifiers=True)
        allowed = {row['id'] for row in branch['entities']['units'] if row['status'] == 'accepted'}
        C._require(len(dependencies) == len(set(dependencies)) and set(dependencies) <= allowed,
                   'Construction dependencies must name distinct accepted units.')
        paths = C._strings(selected.get('paths', []))
        C._require(len(paths) <= 100, 'A coached unit supports at most 100 explicit paths.')
        # The reviewed wording is authoritative proposal text, including edits.
        # Never pair a revised requirement with the original, different action.
        construction = {'text': next(line for line in after.splitlines() if line.strip()),
                        'component_id': component['id'], 'objective': after,
                        'inputs': [values['input'], *contexts], 'outputs': [values['output']],
                        'checks': [values['check']], 'dependencies': deepcopy(dependencies), 'paths': deepcopy(paths)}
        if not missing:
            C._entity_contract('units', construction)
    return {'before': values['text'], 'after': after,
            'contract': {'instruction': values['text'], 'input': values['input'], 'output': values['output'],
                         'check': values['check'], 'context': deepcopy(contexts)},
            'missing': missing, 'complete': not missing, 'explanations': list(EXPLANATIONS),
            'granularity': granularity(values['text']) + granularity(values['check']) +
                          (['Name exact context inputs instead of importing prior conversation.'] if broad_context else []),
            'source_ids': deepcopy(source_ids), 'lens': selected_lens['id'] if selected_lens else '',
            'construction': construction, 'revision': project['revision'], 'fingerprint': C.fingerprint(project)}


def overview(project):
    project = C.validate_project(project)
    examples = []
    for identifier, title, before, instruction, input_, output, check, context in EXAMPLES:
        examples.append({'id': identifier, 'title': title, 'before': before,
                         'draft': {'text': instruction, 'input': input_, 'output': output, 'check': check,
                                   'context': deepcopy(context), 'source_ids': []},
                         'after': atomic_block(instruction, input_, output, check, context),
                         'explanations': list(EXPLANATIONS), 'illustrative': True})
    analysis = C.analyze(project)
    return {'revision': project['revision'], 'fingerprint': C.fingerprint(project),
            'lenses': deepcopy(Catalog.IDEATION_LENSES), 'examples': examples,
            'unit_diagnostics': analysis['unit_checks'], 'readiness': analysis['readiness'],
            'meaning': 'Examples are teaching material. Preview completeness never grants acceptance, compiler proof or execution authority.'}

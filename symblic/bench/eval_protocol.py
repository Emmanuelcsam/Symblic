"""Pure, predeclared evaluation contracts: arms, plans, receipts and denominator-preserving summaries.

What it is for
    The scoring core shared by the matched evaluation (matched.py) and MICA's construction benchmark
    (symblic/mica/bench.py). Everything an evaluation will compare is declared before any model is asked: the
    arms and their controls (model, information, budget, feedback, validator), the cases and their split, and
    the assignment order. Receipts record every provider dispatch; summaries keep every assigned case in the
    denominator and report paired outcomes, costs with their coverage, and the limits of the claim.

Status: measured machinery, stdlib only.

No providers, files, stores or workers. A plan fixes all assignments before calls
and, from version 2, a seeded counterbalanced arm order within each case/repeat;
missing, refused and malformed outcomes remain in its denominator. Rubrics accept
only exact JSON values or explicitly exact text: this is not a prose entailment
judge. Control hashes are reproducible declarations, not execution attestations.

Integration: make_arm -> make_plan -> make_record -> summarize. Feed *every*
provider dispatch (including repair/fallback/refusal) to a record's attempts.
Keep gold inside the evaluator; public_case returns only the declared input.
Version 1 plans and receipts still verify and report under their own rules; they
are never relabelled as version 2 measurements.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from itertools import combinations

VERSION = 2                    # plans, receipts and summaries written by this module
READABLE_VERSIONS = (1, 2)     # frozen plans and receipts that still verify and report
ARM_VERSION = 1                # arm declarations have not changed since version 1
AXES = ('model', 'information', 'budget', 'feedback', 'validator')
SPLITS = ('train', 'dev', 'heldout')
ATTEMPT_STATES = ('answered', 'abstained', 'refused', 'error', 'unknown', 'cancelled')
# Dispatches that returned no model reply: admission refusal before any model saw the
# prompt, transport/provider error, an interrupted (unknown) or cancelled call.
UNREPLIED_STATES = ('refused', 'error', 'unknown', 'cancelled')
RUN_STATES = ('complete', 'failed', 'harness_failed', 'pending', 'uncertain', 'cancelled')
# Why an assignment has no model-attributable terminal outcome (paired analysis).
UNRESOLVED = ('pending', 'uncertain', 'damaged', 'cancelled', 'harness', 'infrastructure')
COST_FIELDS = ('latency_ms', 'input_tokens', 'output_tokens', 'usd')
MAX_JSON_BYTES = 2_000_000
ORDER_DESIGN = 'balanced_latin_square'
_ATTEMPT_FIELDS = ('answer', 'encoding', 'cached', 'request_sha256', 'observed_model', 'error')
_RECEIPTS = {
    1: {'states': ('complete', 'failed', 'pending', 'uncertain', 'cancelled'),
        'encodings': ('json_value', 'json_text', 'text'), 'optional': _ATTEMPT_FIELDS},
    2: {'states': RUN_STATES, 'encodings': ('json_value', 'json_text', 'text', 'invalid_envelope'),
        'optional': _ATTEMPT_FIELDS + ('information_sha256', 'dispatched_at_ms')},
}
ENCODINGS = _RECEIPTS[VERSION]['encodings']


class ProtocolError(ValueError):
    """An invalid protocol declaration or receipt, never a wrong model answer."""


def _json(value, depth=0):
    if depth > 40:
        raise ProtocolError('JSON nesting exceeds 40')
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is str:
        try:
            value.encode('utf-8')
        except UnicodeError as exc:
            raise ProtocolError('Invalid Unicode') from exc
        return
    if type(value) is list:
        for child in value:
            _json(child, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for key, child in value.items():
            _json(key, depth + 1)
            _json(child, depth + 1)
        return
    raise ProtocolError('Expected finite, plain JSON values')


def digest(value):
    _json(value)
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
    except (ValueError, OverflowError) as exc:
        raise ProtocolError('JSON encoding limit') from exc
    if len(raw) > MAX_JSON_BYTES:
        raise ProtocolError('JSON exceeds evaluation size limit')
    return hashlib.sha256(raw).hexdigest()


def exact_equal(left, right):
    """JSON equality that never equates true, 1, 1.0 or '1'."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(exact_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right))
    return left == right


def _keys(row, required, optional=()):
    if type(row) is not dict or not set(required) <= row.keys() or set(row) - set(required) - set(optional):
        raise ProtocolError('Missing or unknown fields: ' + ', '.join(required))


def _label(value):
    if type(value) is not str or not value.strip() or len(value) > 200:
        raise ProtocolError('Expected nonempty label, at most 200 characters')
    return value


def _number(value, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or value < 0:
        raise ProtocolError('Expected nonnegative number' + (' (integer)' if integer else ''))
    if type(value) is float and not math.isfinite(value):
        raise ProtocolError('Nonfinite number')
    if value > 10**15:
        raise ProtocolError('Measurement/resource value exceeds 10^15')
    return value


def _rubric(rubric):
    _keys(rubric, ('mode', 'expected'), ('normalization',))
    if rubric['mode'] not in ('typed_json', 'exact_text'):
        raise ProtocolError('Rubric must be typed_json or exact_text')
    if rubric['mode'] == 'exact_text':
        if type(rubric['expected']) is not str:
            raise ProtocolError('Exact text requires textual gold')
        if rubric.get('normalization', 'none') not in ('none', 'outer_whitespace'):
            raise ProtocolError('Undeclared text normalization')
    elif 'normalization' in rubric:
        raise ProtocolError('JSON rubrics do not coerce or normalize values')
    digest(rubric)
    return rubric


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def grade(rubric, answer, encoding='json_value'):
    """Score only a predeclared exact answer protocol; unsupported prose is unknown.

    encoding=json_text parses one whole JSON document with duplicate-key rejection.
    encoding=text is scored only by an exact_text rubric. encoding=invalid_envelope
    holds the text of a reply that violated the declared answer envelope (unparseable,
    extra/missing fields, oversized): it is malformed under every rubric mode. No token
    extraction, substring matching, last-number heuristic, entity guessing or coercion.
    """
    _rubric(rubric)
    result = {'gradable': False, 'correct': None, 'status': 'ungradable',
              'answer_sha256': None, 'rubric_sha256': digest(rubric)}
    if encoding not in ENCODINGS:
        return {**result, 'reason': 'Unsupported answer encoding'}
    if encoding == 'invalid_envelope':
        return {**result, 'status': 'malformed', 'reason': 'Reply violates the declared answer envelope'}
    if rubric['mode'] == 'typed_json' and encoding == 'text':
        return {**result, 'reason': 'Prose requires its own declared exact-text rubric'}
    if rubric['mode'] == 'exact_text' and encoding != 'text':
        return {**result, 'reason': 'Exact-text rubric requires text encoding'}
    try:
        if encoding == 'json_text':
            if type(answer) is not str or len(answer.encode('utf-8')) > MAX_JSON_BYTES:
                raise ValueError('Expected bounded JSON text')
            answer = json.loads(answer, object_pairs_hook=_pairs,
                                parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        if rubric['mode'] == 'exact_text':
            if type(answer) is not str:
                raise ValueError('Expected text')
            expected = rubric['expected']
            if rubric.get('normalization', 'none') == 'outer_whitespace':
                answer, expected = answer.strip(), expected.strip()
        else:
            expected = rubric['expected']
        answer_hash = digest(answer)
        correct = exact_equal(answer, expected)
    except (ValueError, TypeError, RecursionError, UnicodeError, OverflowError):
        return {**result, 'status': 'malformed', 'reason': 'Answer violates the declared encoding'}
    return {**result, 'gradable': True, 'correct': correct,
            'status': 'correct' if correct else 'incorrect', 'answer_sha256': answer_hash}


def make_arm(arm_id, treatment, *, model, information, budget, feedback, validator):
    """Declare common controls; treatment names the intentional changed mechanism.

    model: primary/fallback model-ID lists, stronger_fallback subset, settings map.
    "Stronger" is the experiment author's declared cohort, not a measured ranking.
    information: IDs/hashes of all available task information, examples and sources.
    budget: provider_calls (required), plus any token/time/resource ceilings.
    feedback/validator: complete policy/version/content declarations, including none.
    Equal fingerprints establish declared matching, not identical actual prompts.
    """
    _label(arm_id)
    _label(treatment)
    controls = dict(model=model, information=information, budget=budget,
                    feedback=feedback, validator=validator)
    for name, value in controls.items():
        if type(value) is not dict or not value:
            raise ProtocolError(name + ' controls must be a nonempty object')
        digest(value)
    _keys(model, ('primary', 'fallback', 'stronger_fallback', 'settings'))
    for key in ('primary', 'fallback', 'stronger_fallback'):
        values = model[key]
        if type(values) is not list or any(type(x) is not str or not x for x in values) or len(set(values)) != len(values):
            raise ProtocolError('Model lists must contain unique IDs')
    if not model['primary'] or set(model['primary']) & set(model['fallback']):
        raise ProtocolError('Need primary models disjoint from fallback models')
    if not set(model['stronger_fallback']) <= set(model['fallback']) or type(model['settings']) is not dict:
        raise ProtocolError('Invalid stronger fallback or settings declaration')
    if _number(budget.get('provider_calls'), integer=True) < 1:
        raise ProtocolError('provider_calls must be positive')
    fingerprints = {axis: digest(controls[axis]) for axis in AXES}
    return {'version': ARM_VERSION, 'id': arm_id, 'treatment': treatment,
            'controls': copy.deepcopy(controls), 'fingerprints': fingerprints,
            'matched_controls_sha256': digest(fingerprints)}


def compare_arms(arms):
    """Return exact mismatched control axes; never pronounce a confounded trial fair."""
    if len(arms) < 2:
        raise ProtocolError('Comparison requires at least two arms')
    checked = [_check_arm(arm) for arm in arms]
    if len({a['id'] for a in checked}) != len(checked):
        raise ProtocolError('Repeated arm ID')
    mismatches = [axis for axis in AXES if len({a['fingerprints'][axis] for a in checked}) != 1]
    return {'matched': not mismatches, 'mismatched_axes': mismatches,
            'fingerprints': {a['id']: a['fingerprints'] for a in checked},
            'scope': 'declared_controls_only'}


def _check_arm(arm):
    _keys(arm, ('version', 'id', 'treatment', 'controls', 'fingerprints', 'matched_controls_sha256'))
    _keys(arm['controls'], AXES)
    expected = make_arm(arm['id'], arm['treatment'], **arm['controls'])
    if not exact_equal(arm, expected):
        raise ProtocolError('Arm fingerprint or version changed')
    return arm


def _cases(cases):
    if type(cases) is not list or not cases or len(cases) > 10_000:
        raise ProtocolError('Need 1..10000 cases')
    identities = set()
    for case in cases:
        _keys(case, ('id', 'family', 'split', 'input', 'rubric'))
        _label(case['id'])
        _label(case['family'])
        if case['id'] in identities or case['split'] not in SPLITS:
            raise ProtocolError('Repeated case ID or unsupported split')
        identities.add(case['id'])
        _rubric(case['rubric'])
        digest(case['input'])
    return cases


def public_case(case):
    """Only input is supplied to a model; identity/family/gold stay evaluator-side."""
    _cases([case])
    return copy.deepcopy(case['input'])


def leakage_report(cases, exposures=()):
    """Check declared family/input splits and logged oracle/heldout exposure.

    Each exposure names case_id, family and/or input_sha256; purpose is train,
    tune, prompt, repair, or score; content is input, answer, or feedback. A heldout
    input may be the prompt of its own assigned case; heldout answer/feedback may
    only be scored. Exact hashes cannot detect paraphrases or model pretraining.
    """
    _cases(cases)
    issues, families, inputs = [], {}, {}
    for case in cases:
        families.setdefault(case['family'], set()).add(case['split'])
        inputs.setdefault(digest(case['input']), set()).add(case['split'])
    for kind, groups in (('family_cross_split', families), ('input_cross_split', inputs)):
        issues += [{'kind': kind, 'id': key, 'splits': sorted(splits)} for key, splits in sorted(groups.items())
                   if len(splits) > 1]
    for index, exposure in enumerate(exposures):
        _keys(exposure, ('purpose', 'content'), ('case_id', 'family', 'input_sha256', 'target_case_id'))
        if exposure['purpose'] not in ('train', 'tune', 'prompt', 'repair', 'score') or exposure['content'] not in ('input', 'answer', 'feedback'):
            raise ProtocolError('Unknown exposure purpose/content')
        selectors = [k for k in ('case_id', 'family', 'input_sha256') if k in exposure]
        if not selectors:
            raise ProtocolError('Exposure needs an exact case/family/input reference')
        for selector in selectors:
            _label(exposure[selector])
        found = [c for c in cases if (exposure.get('case_id') == c['id'] or
                 exposure.get('family') == c['family'] or exposure.get('input_sha256') == digest(c['input']))]
        if not found:
            issues.append({'kind': 'unresolved_exposure', 'exposure': index})
        for case in found:
            if exposure['purpose'] == 'score':
                continue
            self_prompt = (exposure['purpose'] == 'prompt' and exposure['content'] == 'input' and
                           exposure.get('target_case_id') == case['id'])
            if case['split'] == 'heldout' and not self_prompt:
                issues.append({'kind': 'heldout_exposure', 'case_id': case['id'], 'exposure': index})
            elif exposure['content'] == 'answer' and exposure['purpose'] in ('prompt', 'repair'):
                issues.append({'kind': 'oracle_exposure', 'case_id': case['id'], 'exposure': index})
    return {'clean': not issues, 'issues': issues,
            'scope': 'declared_references_and_exact_input_hashes; pretraining/paraphrases not assessed'}


def make_plan(cases, arms, split='heldout', repetitions=1, exposures=(), *, order_seed=0):
    """Fix every assignment and its dispatch order before any call (plan version 2).

    Within each case/repeat block the arms follow one row of a balanced Latin square
    (Williams design): over each cycle of rows every arm takes every position equally
    often and, for an even arm count, follows every other arm once. order_seed fixes,
    reproducibly, which arm takes which slot and the first row. Run assignments in list
    order. Counterbalancing spreads warm-up, cache and drift effects over the arms; it
    does not remove them.
    """
    return _plan(cases, arms, split, repetitions, exposures, VERSION, order_seed)


def _williams(count):
    first = [0] + [step // 2 + 1 if step % 2 else count - step // 2 for step in range(1, count)]
    rows = [[(slot + shift) % count for slot in first] for shift in range(count)]
    return rows + [row[::-1] for row in rows] if count % 2 else rows


def _plan(cases, arms, split, repetitions, exposures, version, order_seed=None):
    _cases(cases)
    if split not in SPLITS or _number(repetitions, integer=True) < 1 or repetitions > 100:
        raise ProtocolError('Invalid split or repetitions')
    if type(arms) is not list or not arms or len(arms) > 128:
        raise ProtocolError('Need 1..128 arms')
    for arm in arms:
        _check_arm(arm)
    if len({a['id'] for a in arms}) != len(arms):
        raise ProtocolError('Need unique arms')
    exposures = list(exposures)
    leakage = leakage_report(cases, exposures)
    if not leakage['clean']:
        raise ProtocolError('Evaluation leakage: ' + ', '.join(sorted({i['kind'] for i in leakage['issues']})))
    selected = [c for c in cases if c['split'] == split]
    if not selected:
        raise ProtocolError('Requested split has no cases')
    if len(selected) * len(arms) * repetitions > 10000:
        raise ProtocolError('Plan exceeds 10000 assignments; use separately pinned shards')
    hashes = {case['id']: digest(case) for case in selected}
    assignments = []
    if version == 1:
        # Historical layout: all repeats of one arm before the next arm of the same case.
        for case in selected:
            for arm in arms:
                for repeat in range(repetitions):
                    row = {'case_id': case['id'], 'arm_id': arm['id'], 'repeat': repeat,
                           'case_sha256': hashes[case['id']], 'controls_sha256': arm['matched_controls_sha256']}
                    assignments.append({'id': digest(row), **row})
    else:
        if type(order_seed) is not int or not 0 <= order_seed < 2**63:
            raise ProtocolError('order_seed must be an integer in 0..2^63-1')
        rows = _williams(len(arms))
        slots = sorted(arms, key=lambda arm: digest({'order_seed': order_seed, 'arm_id': arm['id']}))
        start = int(digest({'order_seed': order_seed, 'first_row': True}), 16) % len(rows)
        blocks = [(case, repeat) for case in selected for repeat in range(repetitions)]
        for index, (case, repeat) in enumerate(blocks):
            for position, slot in enumerate(rows[(start + index) % len(rows)]):
                arm = slots[slot]
                row = {'case_id': case['id'], 'arm_id': arm['id'], 'repeat': repeat, 'position': position,
                       'case_sha256': hashes[case['id']], 'controls_sha256': arm['matched_controls_sha256']}
                assignments.append({'id': digest(row), **row})
    body = {'version': version, 'split': split, 'cases': copy.deepcopy(cases),
            'arms': copy.deepcopy(arms), 'repetitions': repetitions,
            'exposures': copy.deepcopy(list(exposures)), 'assignments': assignments}
    if version != 1:
        body['order'] = {'design': ORDER_DESIGN, 'seed': order_seed, 'unit': 'case_repeat'}
    return {'id': digest(body), **body}


def _check_plan(plan):
    """Re-derive a frozen plan under the rules of its own version."""
    if type(plan) is not dict or type(plan.get('version')) is not int or plan['version'] not in READABLE_VERSIONS:
        raise ProtocolError('Unsupported or missing plan version')
    fields = ('id', 'version', 'split', 'cases', 'arms', 'repetitions', 'exposures', 'assignments')
    seed = None
    if plan['version'] == 1:
        _keys(plan, fields)
    else:
        _keys(plan, fields + ('order',))
        _keys(plan['order'], ('design', 'seed', 'unit'))
        seed = plan['order']['seed']
    expected = _plan(plan['cases'], plan['arms'], plan['split'], plan['repetitions'], plan['exposures'],
                     plan['version'], seed)
    if not exact_equal(plan, expected):
        raise ProtocolError('Plan changed after assignment')
    return plan


def make_record(plan, assignment_id, attempts, *, status='complete', selected=None, agreement_attempts=()):
    """Construct a receipt; selected is a 1-based attempt ordinal, never inferred.

    Every attempt requires model, role(primary/fallback), status, contract_accept
    (bool/null), feedback_exposed(bool/null), and usage (possibly empty). Answered
    attempts also need answer and encoding. Optional cached defaults to false.
    Refused/error attempts still count as dispatch attempts and retain known cost.
    """
    _check_plan(plan)
    assignments = {a['id']: a for a in plan['assignments']}
    if assignment_id not in assignments:
        raise ProtocolError('Unassigned record')
    row = {'version': VERSION, 'plan_id': plan['id'], 'assignment_id': assignment_id,
           'assignment_sha256': digest(assignments[assignment_id]), 'status': status,
           'selected': selected, 'attempts': copy.deepcopy(attempts),
           'agreement_attempts': list(agreement_attempts)}
    _record(row, plan, assignments[assignment_id])
    return row


def _record(row, plan, assignment):
    _keys(row, ('version', 'plan_id', 'assignment_id', 'assignment_sha256', 'status',
                'selected', 'attempts', 'agreement_attempts'))
    if type(row['version']) is not int or row['version'] not in _RECEIPTS:
        raise ProtocolError('Unsupported receipt version')
    rules = _RECEIPTS[row['version']]
    if (row['plan_id'] != plan['id'] or row['assignment_id'] != assignment['id'] or
            row['assignment_sha256'] != digest(assignment)):
        raise ProtocolError('Receipt belongs to another plan or assignment')
    if row['status'] not in rules['states'] or type(row['attempts']) is not list or len(row['attempts']) > 10000:
        raise ProtocolError('Invalid receipt status or attempt list')
    for attempt in row['attempts']:
        _keys(attempt, ('model', 'role', 'status', 'contract_accept', 'feedback_exposed', 'usage'),
              rules['optional'])
        _label(attempt['model'])
        if 'observed_model' in attempt:
            _label(attempt['observed_model'])
        for key in ('request_sha256', 'information_sha256'):
            if key in attempt and (type(attempt[key]) is not str or not re.fullmatch('[0-9a-f]{64}', attempt[key])):
                raise ProtocolError('Invalid ' + key)
        if 'dispatched_at_ms' in attempt:
            _number(attempt['dispatched_at_ms'], integer=True)
        if 'error' in attempt and (type(attempt['error']) is not str or len(attempt['error']) > 2000):
            raise ProtocolError('Error details require bounded text')
        if attempt['role'] not in ('primary', 'fallback') or attempt['status'] not in ATTEMPT_STATES:
            raise ProtocolError('Invalid attempt role/status')
        for flag in ('contract_accept', 'feedback_exposed'):
            if attempt[flag] is not None and type(attempt[flag]) is not bool:
                raise ProtocolError('Receipt flags require bool or null')
        if type(attempt.get('cached', False)) is not bool:
            raise ProtocolError('Invalid cached flag')
        if attempt['status'] == 'answered':
            if 'answer' not in attempt or attempt.get('encoding') not in rules['encodings']:
                raise ProtocolError('Answered attempt needs answer and declared encoding')
            if attempt['encoding'] == 'invalid_envelope' and (type(attempt['answer']) is not str or
                                                              attempt['contract_accept'] is True):
                raise ProtocolError('An envelope violation is recorded as text and never contract-accepted')
        elif 'answer' in attempt or 'encoding' in attempt or attempt['contract_accept'] is True:
            raise ProtocolError('Non-answer cannot contain or accept an answer')
        if type(attempt['usage']) is not dict or set(attempt['usage']) - set(COST_FIELDS):
            raise ProtocolError('Unknown usage fields')
        for key, value in attempt['usage'].items():
            _number(value, integer=key.endswith('tokens'))
            if attempt.get('cached', False) and key != 'latency_ms' and value != 0:
                raise ProtocolError('Cached answers cannot charge historical provider usage again')
    selected = row['selected']
    if selected is not None and (type(selected) is not int or not 1 <= selected <= len(row['attempts'])):
        raise ProtocolError('Selected attempt is not an assigned ordinal')
    if row['status'] == 'complete' and (selected is None or row['attempts'][selected - 1]['status'] not in ('answered', 'abstained')):
        raise ProtocolError('Complete receipt must select an answer or explicit abstention')
    if row['status'] != 'complete' and selected is not None:
        raise ProtocolError('An unfinished/failed receipt cannot select a final answer')
    indices = row['agreement_attempts']
    if (type(indices) is not list or any(type(i) is not int or not 1 <= i <= len(row['attempts']) for i in indices)
            or len(set(indices)) != len(indices)):
        raise ProtocolError('Invalid agreement sample indices')
    digest(row)
    return row


def _agreement(attempts, scores, indices):
    hashes = [scores[i - 1]['answer_sha256'] for i in indices
              if scores[i - 1]['gradable'] and not attempts[i - 1].get('cached', False)]
    count = len(hashes)
    support = max(Counter(hashes).values(), default=0)
    return {'assigned': len(indices), 'fresh_valid': count, 'support': support,
            'measured': count >= 2, 'agreement_valid': support / count if count >= 2 else None,
            'agreement_all': support / len(indices) if count >= 2 else None,
            'cached_excluded': sum(attempts[i - 1].get('cached', False) for i in indices),
            'feedback_exposed': sum(attempts[i - 1]['feedback_exposed'] is True for i in indices),
            'feedback_unknown': sum(attempts[i - 1]['feedback_exposed'] is None for i in indices),
            'independence': 'not_established'}


def score_assignment(plan, assignment, record=None):
    """Missing/damaged records are outcomes, never removed denominator entries."""
    _check_plan(plan)
    if assignment not in plan['assignments']:
        raise ProtocolError('Unassigned outcome')
    return _score_assignment(plan, assignment, record)


def _score_assignment(plan, assignment, record=None):
    base = {'assignment_id': assignment['id'], 'case_id': assignment['case_id'],
            'arm_id': assignment['arm_id'], 'status': 'pending', 'resolution': 'pending', 'attempts': [],
            'final': None, 'agreement': None, 'violations': []}
    if record is None:
        return base
    try:
        _record(record, plan, assignment)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        # One unreadable receipt is one damaged cell; it never hides the other cells.
        return {**base, 'status': 'damaged', 'resolution': 'damaged', 'error': str(exc)[:400]}
    case = next(c for c in plan['cases'] if c['id'] == assignment['case_id'])
    arm = next(a for a in plan['arms'] if a['id'] == assignment['arm_id'])
    controls = arm['controls']
    scored, violations = [], []
    for index, attempt in enumerate(record['attempts'], 1):
        if attempt['model'] not in controls['model'][attempt['role']]:
            violations.append({'kind': 'undeclared_model', 'attempt': index})
        result = grade(case['rubric'], attempt['answer'], attempt['encoding']) if attempt['status'] == 'answered' else {
            'gradable': False, 'correct': None, 'status': attempt['status'], 'answer_sha256': None}
        scored.append({**result, 'ordinal': index, 'model': attempt['model'], 'role': attempt['role'],
                       'stronger_fallback': attempt['role'] == 'fallback' and attempt['model'] in controls['model']['stronger_fallback'],
                       'contract_accept': attempt['contract_accept'], 'feedback_exposed': attempt['feedback_exposed'],
                       'cached': attempt.get('cached', False), 'usage': attempt['usage'],
                       **{k: attempt[k] for k in ('error', 'request_sha256', 'observed_model', 'information_sha256',
                                                  'dispatched_at_ms') if k in attempt},
                       'dispatch_status': attempt['status']})
    if sum(not a['cached'] for a in scored) > controls['budget']['provider_calls']:
        violations.append({'kind': 'provider_budget_exceeded'})
    if record['selected'] and scored[record['selected'] - 1]['contract_accept'] is False:
        violations.append({'kind': 'selected_rejected_contract'})
    return {**base, 'status': record['status'], 'resolution': _resolution(record['status'], scored),
            'attempts': scored, 'final': scored[record['selected'] - 1] if record['selected'] else None,
            'agreement': _agreement(record['attempts'], scored, record['agreement_attempts']),
            'violations': violations}


def _resolution(status, attempts):
    """'resolved' for a model-attributable terminal outcome, otherwise why not.

    A failed cell is the model's failure only when something was dispatched and every
    dispatch returned a model reply. A failure with no dispatch is the harness's; one
    with a refused, errored, unknown or cancelled dispatch is the infrastructure's.
    """
    if status == 'complete':
        return 'resolved'
    if status == 'failed':
        if not attempts:
            return 'harness'
        if any(a['dispatch_status'] in UNREPLIED_STATES for a in attempts):
            return 'infrastructure'
        return 'resolved'
    return 'harness' if status == 'harness_failed' else status


def _group(arm_id):
    fields = ('assigned complete failed harness_failed pending uncertain cancelled damaged correct incorrect '
              'ungradable malformed contract_accept accepted_correct false_accept false_contract_accept '
              'ungradable_accept ungradable_contract_accept unchecked_answer abstain initial_correct '
              'correct_without_fallback fallback_cases stronger_fallback_cases fallback_correct stronger_fallback_correct '
              'attempts fresh_calls cached_attempts fallback_calls stronger_fallback_calls protocol_violations')
    return {'arm_id': arm_id, **dict.fromkeys(fields.split(), 0), 'attempt_states': dict.fromkeys(ATTEMPT_STATES, 0),
            'attempt_grades': dict.fromkeys(('correct', 'incorrect', 'ungradable', 'malformed'), 0),
            'cost': {k: {'known_total': 0, 'observed_attempts': 0, 'unobserved_attempts': 0} for k in COST_FIELDS},
            'agreement': {'measured_assignments': 0, 'sum_valid_agreement': 0}, 'families': {},
            'cells': _cells()}


def _cells():
    return {'assigned': 0, 'pending': 0, 'attempted': 0, 'damaged': 0, 'attempted_with_dispatch': 0,
            'attempted_without_dispatch': 0, 'by_status': dict.fromkeys(RUN_STATES + ('damaged',), 0),
            'resolved': 0, 'unresolved': dict.fromkeys(UNRESOLVED, 0)}


def _count_cell(cells, outcome):
    """Each assigned cell lands in exactly one status, one dispatch class and one resolution."""
    cells['assigned'] += 1
    cells['by_status'][outcome['status']] += 1
    if outcome['status'] == 'pending':
        cells['pending'] += 1
    else:
        cells['attempted'] += 1      # execution began: a start record or receipt exists
        if outcome['status'] == 'damaged':
            cells['damaged'] += 1    # its dispatch count is unknown, not zero
        elif outcome['attempts']:
            cells['attempted_with_dispatch'] += 1
        else:
            cells['attempted_without_dispatch'] += 1
    if outcome['resolution'] == 'resolved':
        cells['resolved'] += 1
    else:
        cells['unresolved'][outcome['resolution']] += 1


def _check_cells(cells):
    if not (cells['assigned'] == cells['pending'] + cells['attempted'] == sum(cells['by_status'].values())
            == cells['resolved'] + sum(cells['unresolved'].values()) and cells['attempted'] ==
            cells['damaged'] + cells['attempted_with_dispatch'] + cells['attempted_without_dispatch']):
        raise ProtocolError('Cell accounting does not balance')
    return cells


def _order(plan):
    if plan['version'] == 1:
        return {'design': 'fixed_case_arm_repeat', 'seed': None, 'counterbalanced': False,
                'confounded_with_arm': ['latency_ms', 'cost', 'time_dependent_provider_state']}
    positions = {arm['id']: [0] * len(plan['arms']) for arm in plan['arms']}
    for assignment in plan['assignments']:
        positions[assignment['arm_id']][assignment['position']] += 1
    return {**plan['order'], 'counterbalanced': True, 'positions': positions}


def summarize(plan, records, *, spec_labor=(), harness_failures=()):
    """Aggregate all planned assignments; retain unknown grading and unknown costs.

    spec_labor is optional measured evidence: unique id, arm_id, minutes, method
    ('timed'/'self_reported'), scope text. One measurement is counted once, not
    multiplied by tasks/repetitions. Absent labor remains unknown, never zero.
    harness_failures names assignments whose runner durably recorded a harness failure
    (needed for version 1 receipts, which have no harness_failed status). A failed
    outcome among them is unresolved, never a model failure; its attempts and known
    costs still count. Paired outcomes use only pairs whose members both resolved.
    """
    _check_plan(plan)
    assignments = {a['id']: a for a in plan['assignments']}
    harness = set()
    for ident in harness_failures:
        if type(ident) is not str or ident not in assignments:
            raise ProtocolError('Harness failure names an unassigned outcome')
        harness.add(ident)
    by_id, ignored = {}, []
    for index, record in enumerate(records):
        ident = record.get('assignment_id') if type(record) is dict else None
        if type(ident) is not str or ident not in assignments:
            ignored.append({'record_index': index, 'reason': 'unassigned_record'})
        else:
            by_id.setdefault(ident, []).append(record)
    groups = {a['id']: _group(a['id']) for a in plan['arms']}
    outcomes = []
    cases = {c['id']: c for c in plan['cases']}
    for ident, assignment in assignments.items():
        rows = by_id.get(ident, [])
        outcome = _score_assignment(plan, assignment, rows[0] if rows else None)
        if len(rows) > 1:
            outcome = {**outcome, 'status': 'damaged', 'resolution': 'damaged', 'final': None, 'attempts': [],
                       'agreement': None, 'error': 'Duplicate receipts; reconcile by assignment before scoring'}
        if ident in harness and outcome['status'] == 'failed':
            outcome = {**outcome, 'resolution': 'harness'}
        outcomes.append(outcome)
        group = groups[assignment['arm_id']]
        group['assigned'] += 1
        group[outcome['status']] += 1
        _count_cell(group['cells'], outcome)
        group['protocol_violations'] += bool(outcome['violations'])
        final = outcome['final']
        good = final is not None and final['correct'] is True
        group['correct'] += good
        family = group['families'].setdefault(cases[assignment['case_id']]['family'], {'assigned': 0, 'correct': 0})
        family['assigned'] += 1
        family['correct'] += good
        if final:
            for key in ('incorrect', 'malformed', 'ungradable'):
                group[key] += final['status'] == key
            group['abstain'] += final['status'] == 'abstained'
            group['contract_accept'] += final['contract_accept'] is True
            group['accepted_correct'] += final['contract_accept'] is True and good
            # A selected final answer is a delivered acceptance even in a direct
            # baseline with no runtime contract. Keep verifier acceptance separate.
            answered = final['dispatch_status'] == 'answered'
            group['false_accept'] += answered and final['correct'] is False
            group['false_contract_accept'] += final['contract_accept'] is True and final['correct'] is False
            group['ungradable_accept'] += answered and final['correct'] is None
            group['ungradable_contract_accept'] += final['contract_accept'] is True and final['correct'] is None
            group['unchecked_answer'] += answered and final['contract_accept'] is None
            group['fallback_correct'] += good and final['role'] == 'fallback'
            group['stronger_fallback_correct'] += good and final['stronger_fallback']
        attempts = outcome['attempts']
        group['attempts'] += len(attempts)
        group['initial_correct'] += bool(attempts and attempts[0]['correct'] is True)
        fallback = any(a['role'] == 'fallback' for a in attempts)
        group['fallback_cases'] += fallback
        group['stronger_fallback_cases'] += any(a['stronger_fallback'] for a in attempts)
        group['correct_without_fallback'] += good and not fallback
        for attempt in attempts:
            fresh = not attempt['cached']
            group['fresh_calls'] += fresh
            group['cached_attempts'] += not fresh
            group['fallback_calls'] += fresh and attempt['role'] == 'fallback'
            group['stronger_fallback_calls'] += fresh and attempt['stronger_fallback']
            group['attempt_states'][attempt['dispatch_status']] += 1
            if attempt['status'] in group['attempt_grades']:
                group['attempt_grades'][attempt['status']] += 1
            for key, cost in group['cost'].items():
                if key in attempt['usage']:
                    cost['known_total'] += attempt['usage'][key]
                    cost['observed_attempts'] += 1
                else:
                    cost['unobserved_attempts'] += 1
        agreement = outcome['agreement']
        if agreement and agreement['measured']:
            group['agreement']['measured_assignments'] += 1
            group['agreement']['sum_valid_agreement'] += agreement['agreement_valid']
    totals = _cells()
    for group in groups.values():
        group['rates_per_assigned'] = {key: group[key] / group['assigned'] for key in (
            'correct', 'false_accept', 'ungradable_accept', 'abstain', 'contract_accept', 'accepted_correct')}
        agreement = group['agreement']
        n = agreement['measured_assignments']
        agreement['mean_valid_agreement'] = agreement.pop('sum_valid_agreement') / n if n else None
        group['cost_unresolved_assignments'] = sum(group[k] for k in ('pending', 'uncertain', 'damaged'))
        cells = _check_cells(group['cells'])
        for key, value in cells.items():
            if type(value) is dict:
                for name, count in value.items():
                    totals[key][name] += count
            else:
                totals[key] += value
    labor, ids = [], set()
    for row in spec_labor:
        _keys(row, ('id', 'arm_id', 'minutes', 'method', 'scope'))
        _label(row['id'])
        _label(row['scope'])
        _number(row['minutes'])
        if row['id'] in ids or row['arm_id'] not in groups or row['method'] not in ('timed', 'self_reported'):
            raise ProtocolError('Duplicate/invalid labor measurement')
        ids.add(row['id'])
        labor.append(copy.deepcopy(row))
    pairs = []
    indexed = {(o['arm_id'], a['case_id'], a['repeat']): o
               for a, o in zip(plan['assignments'], outcomes)}
    for left, right in combinations(groups, 2):
        pair = {'left': left, 'right': right, 'assigned_pairs': 0, 'resolved_pairs': 0,
                'both_correct': 0, 'left_only_correct': 0, 'right_only_correct': 0, 'neither_correct': 0,
                'unresolved_pairs': 0, 'unresolved': {'left_only': 0, 'right_only': 0, 'both': 0},
                'unresolved_reasons': {'left': dict.fromkeys(UNRESOLVED, 0), 'right': dict.fromkeys(UNRESOLVED, 0)},
                'information': {'matched': 0, 'mismatched': 0, 'unrecorded': 0,
                                'scope': 'SHA-256 of the task text carried by each arm\'s first dispatch'},
                'families': {}}
        for assignment in plan['assignments']:
            if assignment['arm_id'] != left:
                continue
            key = (assignment['case_id'], assignment['repeat'])
            a, b = indexed[(left, *key)], indexed[(right, *key)]
            family = pair['families'].setdefault(cases[assignment['case_id']]['family'], {
                'assigned_pairs': 0, 'resolved_pairs': 0, 'both_correct': 0, 'left_only_correct': 0,
                'right_only_correct': 0, 'neither_correct': 0, 'unresolved_pairs': 0})
            pair['assigned_pairs'] += 1
            family['assigned_pairs'] += 1
            seen = [o['attempts'][0].get('information_sha256') if o['attempts'] else None for o in (a, b)]
            pair['information']['unrecorded' if None in seen else
                                'matched' if seen[0] == seen[1] else 'mismatched'] += 1
            a_open, b_open = a['resolution'] != 'resolved', b['resolution'] != 'resolved'
            if a_open or b_open:
                # Pending, unfinished, damaged or non-model failures are not wrong answers.
                pair['unresolved_pairs'] += 1
                family['unresolved_pairs'] += 1
                pair['unresolved']['both' if a_open and b_open else 'left_only' if a_open else 'right_only'] += 1
                if a_open:
                    pair['unresolved_reasons']['left'][a['resolution']] += 1
                if b_open:
                    pair['unresolved_reasons']['right'][b['resolution']] += 1
                continue
            a_good = bool(a['final'] and a['final']['correct'] is True)
            b_good = bool(b['final'] and b['final']['correct'] is True)
            category = ('both_correct' if a_good and b_good else 'left_only_correct' if a_good else
                        'right_only_correct' if b_good else 'neither_correct')
            pair['resolved_pairs'] += 1
            pair[category] += 1
            family['resolved_pairs'] += 1
            family[category] += 1
        pairs.append(pair)
    order = _order(plan)
    return {'version': VERSION, 'plan_version': plan['version'], 'plan_id': plan['id'], 'assigned': len(assignments),
            'cells': _check_cells(totals),
            'groups': list(groups.values()), 'outcomes': outcomes, 'ignored_records': ignored,
            'paired': pairs, 'order': order,
            'comparability': compare_arms(plan['arms']) if len(plan['arms']) > 1 else None,
            'observed_protocol': {'violating_assignments': sum(g['protocol_violations'] for g in groups.values()),
                                  'damaged_assignments': sum(g['damaged'] for g in groups.values()),
                                  'information_mismatched_pairs': sum(p['information']['mismatched'] for p in pairs),
                                  'scope': 'declared_model_membership_dispatch_call_limit_and_first_dispatch_task_hash'},
            'spec_labor': {'measurements': labor, 'known_minutes_total': sum(r['minutes'] for r in labor) if labor else None},
            'limits': ['Exact finite labels; no general semantic entailment or external-truth proof.',
                       'Control hashes are declarations, not model/settings execution attestations.',
                       'Heldout means family/input isolation in this manifest, not unseen model pretraining.',
                       'Unknown grading and unknown costs remain separate; labor is optional measured evidence.',
                       'Fresh calls count dispatch attempts including refusal, not billable provider calls.',
                       'Paired outcomes count only pairs whose members both reached a model-attributable terminal '
                       'state; pending, uncertain, damaged, cancelled, harness and infrastructure outcomes are '
                       'unresolved pairs, and their attempts and known costs still count.',
                       'Paired counts retain families; no independent-sample confidence interval is implied.',
                       'Agreement is fresh-sample identity, never correctness or independent evidence.',
                       'Arm order is counterbalanced within each case and repeat; this balances, but does not remove, '
                       'warm-up, cache and drift effects.' if order['counterbalanced'] else
                       'Plan version 1 ran every case\'s arms in a fixed order; latency, cost and time-dependent '
                       'provider state are confounded with arm.']}

"""The convergence compiler: find where agents read a program differently, and propose a tighter wording.

The idea is measurement, not hope. A statement that different agents answer differently is underspecified for those
agents (or beyond some of them). Run every ask on a PANEL of applicators with fresh contexts at temperature 0, and the
spread of their canonical answers locates the problem statement by statement:

    converged     every panel member gave the same canonical answer and nobody listed a second reading
    format        many answers did not even fit the type (the contract is the problem)
    ambiguous     a reader listed two readings that change the answer (probes are asked for them), or the
                  strong applicators disagree among themselves
    capability    the strong applicators agree, only weaker ones deviate (which can still be a reading the
                  strong ones share by convention: 26.2 miles vs 42.195 km for "a marathon")
    divergent     the panel has no strong applicators to tell the last two apart

"Strong" is a heuristic over engine names (STRONG_ENGINES: the cloud coding agents the language knows); a local
`ollama:` or `command:` applicator is not assumed strong.

A pilot on 2026-10-02: capable probes (Claude Haiku, Codex and a Gemini model through the agy CLI) answered 365 days
and 100 degrees C unanimously while held-out small models split (a marathon: 42.195 vs 26.2), so a capable-only "do
they disagree?" test misses ambiguity that shared conventions hide. Probes therefore list readings, and every
non-unanimous ask is clarified by default. That pilot was small and is evidence for this design choice only.

Disagreement is evidence of ambiguity only when capable readers disagree; disagreement can also be plain error.
Agreement is never evidence of correctness. Reported per ask: coverage (valid answers / answers), agreement over ALL
answers (an invalid answer counts as disagreement), agreement among valid answers only, distinct answers, and which
applicator said what.

Tightening: deterministic suggestions from the answers themselves (a Text answer with a few short values ->
`one of {...}`; numbers that agree after rounding -> `to N places`; record fields that differ), plus, for ambiguous
statements, a CLARIFIER applicator rewrites the instruction with explicit assumptions (units, conventions, frames,
definitions). It is told not to choose the answer, and a rewrite that names the modal answer when the original did not
is flagged `leaks_answer`. tighten() repeats probe -> clarify -> probe for a few rounds. A fair test of a rewrite uses a
DIFFERENT panel from the one that produced it (paper_experiment, and the tighten suite of symblic.bench). These
diagnoses are heuristics, not findings that the author intended one convention or that a provider is inherently
capable.

Return contract v2 keeps experimental candidates separate from adopted source. Convergence is neither semantic
fidelity nor permission to change a requirement. Finite held-out obligations are checked only after exploration.
Explicit host decisions or a predeclared exact-AST policy control adoption, without additional model calls. Their hashes
protect local integrity; they are not signatures.

Command line: python3 -m symblic.authoring.tighten paper PAPER.symd --probe APPS --heldout APPS --clarifier APP
--out FOLDER (asks the models). The library default clarifier (`claude:opus`) names the `claude` engine, which this
repository's applicators reach only through a configured command (`command:NAME`, symblic.providers.applicators).
Depends on: symblic.kernel (language, run), symblic.authoring.paper, symblic.providers.applicators (CLI and jobs).
Status: experimental; measured only in the small pilot above.
"""

from __future__ import annotations

import json
import re
import copy
import hashlib

from symblic.kernel import language as S
from symblic.kernel import run as SR

STRONG_ENGINES = ('claude', 'codex', 'agy', 'mistral', 'copilot', 'gemini', 'chatgpt', 'council')
TIGHTEN_VERSION = 2

CLARIFY_SOURCE = (
    'given statement: Text.\n'
    'given interpretations: Text.\n'
    'given program: Text = "".\n'
    'ask fix: Record {instruction: Text up to 90 words, assumptions: List of Text length 1..4} '
    '"Independent careful readers answered the STATEMENT differently; INTERPRETATIONS lists each distinct answer and '
    'who gave it. Rewrite the statement so that every careful reader must give the same answer. Keep its intent and '
    'its question. Remove the ambiguity that produced the different answers by stating explicit assumptions: units, '
    'conventions, reference frames, definitions, rounding, what exactly to count. Resolve it by naming the convention '
    'in the statement itself (for example “a common, non-leap year” or “in kilometres”), never by replacing a general '
    'question with a specific instance that needs extra knowledge (a particular year, place, date or edition) unless '
    'the original named it: a careful reader must be able to answer the rewrite with no more knowledge than the '
    'original needed. Prefer the convention of the field the statement belongs to (how its practitioners read it: '
    'a lab, a kitchen, a ledger), and name the convention you chose in the assumptions, so the author can see the '
    'choice and change it. Say what to use, never what to avoid: do not name the readings you exclude (a reader '
    'told \u201cnot in Fahrenheit\u201d may convert to Fahrenheit). Do not state, hint at or choose the answer itself, '
    'and do not add new facts the question did not imply. Return the rewritten instruction and the assumptions you '
    'added as proposed choices, not established author intentions. Agreement does not establish that the proposal '
    'preserves meaning. PROGRAM, when given, is the program the statement belongs to: readers saw its definitions and section '
    'texts as context; if readers ignored a rule stated there, restate that rule in the statement itself." '
    'from statement, interpretations, program with effort=high, votes=1, vote=whole\n')


def engine_of(label: str) -> str:
    return str(label).split(':', 1)[0].split('@', 1)[0]


OUTAGE = re.compile(r'quota|paused|unavailable|outage|rate.?limit|still busy|stopped|cancel|timed? ?out|no capacity|'
                    r'hot after|transient|curl|empty reply|failed to connect|connection (refused|reset)', re.I)


def _norm_reading(text) -> str:
    return re.sub(r'\s+', ' ', str(text or '').strip().strip('"').lower())


def analyse(row: dict, panel: list) -> dict:
    """One ask's probe result (a trace row) -> diagnosis and measures. A reader that could not be reached
    (quota, outage, capacity, heat) gave no reading: it is reported under `missing`, not counted as an answer;
    an answer that did not fit the type IS counted (as disagreement)."""
    meta = row.get('ask') or {}
    every = [x for x in meta.get('samples') or [] if x.get('round', 1) == 1]
    missing = [x['app'] for x in every if not x.get('ok') and OUTAGE.search(str(x.get('error') or ''))]
    samples = [x for x in every if x.get('ok') or not OUTAGE.search(str(x.get('error') or ''))]
    readings = []
    for x in samples:
        for r in x.get('readings') or []:
            if r not in readings:
                readings.append(r)
    flagged = [x['app'] for x in samples if x.get('readings')]
    # one reader listing a reading of an agreed answer is weak evidence (capable readers always find some nuance:
    # "count only days, not years"); an agreed ask counts as ambiguous when two readers see another reading
    quorum = 2 if len(samples) >= 3 else 1
    n = len(samples)
    valid = [x for x in samples if x.get('ok')]
    counts = {}
    for x in valid:
        counts[x['hash']] = counts.get(x['hash'], 0) + 1
    modal = max(counts.values()) if counts else 0
    # a deviating answer that some reader listed as another reading's answer ("in miles: 26.2") is ambiguity,
    # not weakness, even when only one reader saw it
    modal_hash = max(counts, key=counts.get) if counts else None
    blob = ' '.join(_norm_reading(r) for r in readings)
    explained = any(x['hash'] != modal_hash and _norm_reading(S.show(x.get('value'))) and
                    re.search(r'(?<![\w.])' + re.escape(_norm_reading(S.show(x.get('value')))) + r'(?![\w.])', blob)
                    for x in valid) if readings else False
    strong = [x for x in valid if engine_of(x['app']) in STRONG_ENGINES]
    weak = [x for x in valid if engine_of(x['app']) not in STRONG_ENGINES]
    strong_hashes = {x['hash'] for x in strong}
    coverage = len(valid) / n if n else 0.0
    if not samples:
        diagnosis = 'unreached'                  # every reader was unavailable: nothing was measured
    elif valid and len(counts) == 1 and len(valid) == n and len(flagged) < quorum:
        diagnosis = 'converged'
    elif coverage < 0.6:
        diagnosis = 'format'
    elif len(flagged) >= quorum or len(strong_hashes) >= 2 or explained:
        diagnosis = 'ambiguous'
    elif len(strong_hashes) == 1 and any(x['hash'] not in strong_hashes for x in weak):
        diagnosis = 'capability'
    elif len(strong_hashes) == 1:
        diagnosis = 'converged-valid'          # every valid answer agrees; some answers were invalid
    else:
        diagnosis = 'divergent'
    return {'line': row.get('line'), 'name': row.get('name'), 'diagnosis': diagnosis,
            'coverage': round(coverage, 4), 'agreement_all': round(modal / n, 4) if n else 0.0,
            'agreement_valid': round(modal / len(valid), 4) if valid else 0.0, 'distinct': len(counts),
            'answers': [{'app': x['app'], 'ok': bool(x.get('ok')), 'value': x.get('value'), 'hash': x.get('hash'),
                         'error': x.get('error', ''), 'readings': x.get('readings') or []} for x in samples],
            'readings': readings, 'flagged': flagged, 'missing': missing,
            'modal_value': next((x.get('value') for x in valid if counts.get(x['hash']) == modal), None)}


def probe(source: str, inputs: dict | None, panel: list, applicators, folder: str | None = None, log=None,
          readings: bool = False) -> dict:
    """Run the program once with every ask answered by every panel member (fresh context, temperature 0).
    With `readings`, each reader also lists the statement's alternative readings (for diagnosis; a held-out
    evaluation leaves it off so it measures the statement alone)."""
    run = SR.Run(source, inputs, applicators,
                 {'override_by': list(panel), 'override_temperature': 0, 'parallel': max(1, min(8, len(panel))),
                  'max_asks': 400, 'override_ambiguous': readings}, folder=folder, log=log)
    report = run.execute()
    asks = [analyse(t, panel) for t in run.trace if t.get('kind') == 'ask' and t.get('ask')]
    err = report.get('error') or {}
    if report['status'] == 'failed' and err.get('line') and not any(a['line'] == err['line'] for a in asks):
        # the run stopped at an ask no reader answered: record it rather than dropping it
        miss = OUTAGE.search(str(err.get('message') or ''))
        asks.append({'line': err['line'], 'name': '', 'diagnosis': 'unreached' if miss else 'failed',
                     'coverage': 0.0, 'agreement_all': 0.0, 'agreement_valid': 0.0, 'distinct': 0, 'answers': [],
                     'readings': [], 'flagged': [], 'missing': list(panel) if miss else [], 'modal_value': None,
                     'error': str(err.get('message') or '')[:300]})
    checked = S.check(source)
    static = {d['line']: d for d in checked.get('asks_detail') or []}
    for a in asks:
        a['static'] = static.get(a['line'], {}).get('reasons', [])
        a['suggestions'] = suggest(a, _ask_type(source, a['line']))
    scores = [a['agreement_all'] for a in asks]
    return {'status': report['status'], 'error': report.get('error'), 'asks': asks,
            'agreement_all': round(sum(scores) / len(scores), 4) if scores else 1.0,
            'coverage': round(sum(a['coverage'] for a in asks) / len(asks), 4) if asks else 1.0,
            'calls': report['calls'], 'fingerprint': report['fingerprint']}


def _ask_type(source: str, line: int):
    try:
        prog = S.parse(source)
    except S.SymblicError:
        return None
    types = {}
    for st in SR._flat(prog['statements']):
        if st.k == 'define':
            types[st.name] = st.type
        if st.k == 'ask' and st.line == line:
            try:
                return S.resolve_type(st.type, types, st.line)
            except S.SymblicError:
                return None
    return None


def suggest(a: dict, ty) -> list:
    """Deterministic tightenings read off the answers (no model)."""
    out = []
    if a['diagnosis'] in ('converged',) or ty is None:
        return out
    vals = [x['value'] for x in a['answers'] if x['ok'] and x.get('value') is not None]
    if ty['k'] == 'text' and vals:
        short = sorted({S._norm_option(str(v)) for v in vals})
        if len(short) <= 6 and all(len(v.split()) <= 4 for v in short):
            out.append('consider one of {' + ', '.join(short) + '} only if it covers all task-relevant answers; '
                       'observed answers alone cannot establish that coverage')
    if ty['k'] in ('number', 'int') and len({x['hash'] for x in a['answers'] if x['ok']}) > 1:
        nums = []
        for v in vals:
            try:
                nums.append(S._coerce_num(v, 'v'))
            except S.SymblicError:
                pass
        for places in (0, 1, 2):
            if nums and len({S.round_half_up(S.Fraction(x), places) for x in nums}) == 1:
                out.append(f'the answers agree after rounding to {places} places; change precision only if the '
                           'original requirements permit it, not to manufacture agreement')
                break
        else:
            if nums and min(nums) > 0 and max(nums) / min(nums) >= 1.5:
                out.append('the answers differ by a large factor: state the unit and the convention explicitly')
    if ty['k'] == 'record':
        fields = {}
        for x in a['answers']:
            if x['ok'] and isinstance(x.get('value'), dict):
                for k, v in x['value'].items():
                    fields.setdefault(k, set()).add(json.dumps(v, sort_keys=True, default=str))
        diff = sorted(k for k, v in fields.items() if len(v) > 1)
        if diff:
            out.append('the record fields that differ: ' + ', '.join(diff) + ' (pin each down, or vote=fields)')
    if a['diagnosis'] == 'capability':
        out.append('strong applicators agree: the statement may be fine; prefer stronger applicators or more votes')
    if a['diagnosis'] == 'format':
        out.append('many answers did not fit the type: give a worked example (examples=[[q, a]])')
    return out


def interpretations_text(a: dict) -> str:
    groups = {}
    for x in a['answers']:
        key = x['hash'] if x['ok'] else 'invalid: ' + str(x.get('error'))[:80]
        g = groups.setdefault(key, {'value': x.get('value') if x['ok'] else key, 'apps': []})
        g['apps'].append(x['app'])
    out = '\n'.join(f'- answer {json.dumps(g["value"], ensure_ascii=False, default=str)[:300]} '
                    f'(from {len(g["apps"])} reader(s))' for g in groups.values())
    if a.get('readings'):
        out += '\nReaders also listed these readings of the statement:\n' + '\n'.join(
            f'- {r}' for r in a['readings'][:10])
    return out


def clarify(statement_text: str, a: dict, clarifier: str, applicators, log=None, program: str = '',
            hints: str = '', options=None) -> dict:
    """A rewritten instruction with explicit assumptions, from one clarifier applicator. `program` (the whole
    source) lets it restate a rule readers saw only as context."""
    interp = interpretations_text(a) + (f'\nA static check (no model) flagged these phrases in the source:\n{hints}'
                                        if hints else '')
    run = SR.Run(CLARIFY_SOURCE, {'statement': statement_text, 'interpretations': interp,
                                  'program': program[:12000]},
                 applicators, {'by': clarifier, 'parallel': 1, 'max_asks': 5}, log=log)
    rep = run.execute()
    fix = next((b['value'] for b in rep['bindings'] if b['name'] == 'fix'), None)
    if not isinstance(fix, dict):
        return {'ok': False, 'error': (rep.get('error') or {}).get('message', 'no rewrite')}
    new = str(fix.get('instruction') or '').strip()
    modal = a.get('modal_value')
    leak = False
    if modal is not None and not isinstance(modal, (dict, list)):
        m = S._norm_option(str(modal))
        leak = bool(m) and re.search(rf'\b{re.escape(m)}\b', S._norm_option(new)) is not None and \
            re.search(rf'\b{re.escape(m)}\b', S._norm_option(statement_text)) is None
        if leak and options:
            # a closed answer: naming the modal option beside another allowed option lists the choices
            # ("one of monday, tuesday, …"; "true if …, false if …"), it does not give the answer
            others = [o for o in options if S._norm_option(o) != m]
            if any(re.search(rf'\b{re.escape(S._norm_option(o))}\b', S._norm_option(new)) for o in others):
                leak = False
    return {'ok': bool(new), 'instruction': new, 'assumptions': list(fix.get('assumptions') or []),
            'leaks_answer': leak}


def ask_instruction(source: str, line: int):
    """(node, plain instruction text) of the ask on `line`, or (node, None) if it interpolates expressions."""
    prog = S.parse(source)
    for st in SR._flat(prog['statements']):
        if st.k == 'ask' and st.line == line:
            if all(isinstance(p, str) for p in st.parts):
                return st, ''.join(st.parts)
            return st, None
    return None, None


def rewrite(source: str, line: int, old: str, new: str) -> str | None:
    """Replace exactly the named ask's instruction, with an AST change guard.

    A nearby string with the same spelling is never a substitute for locating
    the intended instruction. Escaped literals we cannot locate remain intact.
    """
    parsed = S.parse(source)
    target = next((st for st in SR._flat(parsed['statements']) if st.k == 'ask' and st.line == line), None)
    if target is None or any(not isinstance(p, str) for p in target.parts) or ''.join(target.parts) != old:
        return None
    target.parts = [new]
    expected = _parsed_identity(parsed)
    lines = source.splitlines(keepends=True)
    start = sum(len(s) for s in lines[:line - 1])
    end = min((sum(len(s) for s in lines[:ln - 1]) for _, ln, _ in S.split_statements(source) if ln > line),
              default=len(source))
    for quote in ('"""', "'''", '"', "'"):
        literal = quote + old + quote
        offset = source.find(literal, start, end)
        while offset != -1:
            replacement = json.dumps(new, ensure_ascii=False).replace('{', '{{').replace('}', '}}')
            candidate = source[:offset] + replacement + source[offset + len(literal):]
            try:
                if _ast_identity(candidate) == expected:
                    return candidate
            except (S.SymblicError, RecursionError):
                pass
            offset = source.find(literal, offset + 1, end)
    return None


TIGHTEN = ('ambiguous', 'divergent', 'capability')


class FidelityError(ValueError):
    """Invalid host-side fidelity declaration; never a model refusal."""


def source_hash(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _digest(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return source_hash(raw)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FidelityError('Fidelity declarations must be finite JSON') from exc


def _keys(row, required, optional=()):
    if type(row) is not dict or not set(required) <= row.keys() or set(row) - set(required) - set(optional):
        raise FidelityError('Missing or unknown fidelity fields: ' + ', '.join(required))


def _text(value, label, limit=12000):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise FidelityError(label + ' must be bounded nonempty text')
    return value


def _declarations(requirements, obligations, requirement_map, checker, checker_id):
    requirements = copy.deepcopy(list(requirements or []))
    obligations = copy.deepcopy(list(obligations or []))
    mapping = copy.deepcopy(requirement_map or {})
    if len(requirements) > 256 or len(obligations) > 512:
        raise FidelityError('Too many fidelity requirements/obligations')
    ids, tests = set(), set()
    for row in requirements:
        _keys(row, ('id', 'text'), ('kind',))
        _text(row['id'], 'Requirement ID', 200)
        _text(row['text'], 'Requirement')
        if row['id'] in ids or row.get('kind', 'hard') not in ('hard', 'soft'):
            raise FidelityError('Repeated requirement ID or invalid requirement kind')
        ids.add(row['id'])
    for row in obligations:
        _keys(row, ('id', 'kind', 'split', 'requirement_ids', 'fixture', 'expected'))
        _text(row['id'], 'Obligation ID', 200)
        if row['id'] in tests or row['kind'] not in ('positive', 'negative') or row['split'] != 'heldout':
            raise FidelityError('Obligations need unique IDs and heldout positive/negative fixtures')
        tests.add(row['id'])
        refs = row['requirement_ids']
        if type(refs) is not list or any(type(x) is not str for x in refs) or len(set(refs)) != len(refs) or not set(refs) <= ids:
            raise FidelityError('Obligation maps unknown/repeated requirement IDs')
    if type(mapping) is not dict:
        raise FidelityError('Requirement map must map ask names to ID lists')
    for name, refs in mapping.items():
        _text(name, 'Ask name', 200)
        if type(refs) is not list or any(type(x) is not str for x in refs) or len(set(refs)) != len(refs) or not set(refs) <= ids:
            raise FidelityError('Rewrite maps unknown/repeated requirement IDs')
    if checker is not None:
        if not callable(checker):
            raise FidelityError('Fidelity checker must be an injected pure callable')
        _text(checker_id, 'Checker identity', 200)
    elif checker_id:
        raise FidelityError('Checker identity given without a checker')
    _digest([requirements, obligations, mapping])
    return requirements, obligations, mapping


def _ast_identity(source):
    return _parsed_identity(S.parse(source))


def _parsed_identity(parsed):
    def syntax(value):
        if isinstance(value, S.Node):
            return {key: syntax(child) for key, child in vars(value).items() if key not in ('line', 'col')}
        if isinstance(value, dict):
            return {key: syntax(child) for key, child in value.items()}
        if isinstance(value, (list, tuple)):
            return [syntax(child) for child in value]
        return S.canon(value)
    return _digest({'name': parsed['name'], 'statements': syntax(parsed['statements'])})


def _risks(before, after, options=()):
    """Visible syntactic hints only, never an arbitrary prose equivalence checker."""
    risks = []
    if before != after:
        risks.append('meaning_change_unassessed')
    for name, pattern in (
        ('rounding_or_precision', r'\b(round\w*|precision|decimal|digits?|places)\b'),
        ('unit_or_convention', r'\b(kilo\w*|miles?|metres?|meters?|celsius|fahrenheit|inches|pounds?|ISO|convention|percent|percentage|units?)\b'),
    ):
        if re.findall(pattern, before, re.I) != re.findall(pattern, after, re.I):
            risks.append(name)
    present = lambda word, text: re.search(r'(?<!\w)' + re.escape(str(word)) + r'(?!\w)', text, re.I)
    if any(present(option, before) and not present(option, after) for option in options or []):
        risks.append('removed_option_mention')
    return risks


def _fidelity(original, candidate, requirements, obligations, checker, checker_id):
    """Run heldout checks once, after exploration; never feed results to a model."""
    results = []
    for obligation in obligations:
        result = {'status': 'unknown', 'reason': 'No injected fidelity checker'}
        if checker is not None:
            try:
                answer = checker(original, candidate, copy.deepcopy(obligation))
                _keys(answer, ('status', 'reason'), ('evidence',))
                if answer['status'] not in ('pass', 'fail', 'unknown'):
                    raise FidelityError('Checker did not return pass/fail/unknown')
                _text(answer['reason'], 'Checker reason', 4000)
                _digest(answer)
                result = copy.deepcopy(answer)
            except Exception as exc:  # trusted pure adapter failures must remain visible, never pass
                result = {'status': 'unknown', 'reason': 'Checker unavailable/invalid: ' + type(exc).__name__}
        results.append({'id': obligation['id'], 'kind': obligation['kind'],
                        'requirement_ids': obligation['requirement_ids'], 'obligation_sha256': _digest(obligation),
                        **result})
    coverage = []
    for requirement in requirements:
        mapped = [row for row in results if requirement['id'] in row['requirement_ids']]
        status = ('unmapped' if not mapped else 'fail' if any(r['status'] == 'fail' for r in mapped)
                  else 'unknown' if any(r['status'] == 'unknown' for r in mapped) else 'pass')
        coverage.append({'id': requirement['id'], 'text': requirement['text'],
                         'kind': requirement.get('kind', 'hard'), 'mapping': 'mapped' if mapped else 'unmapped',
                         'status': status, 'obligation_ids': [r['id'] for r in mapped]})
    status = ('fail' if any(r['status'] == 'fail' for r in results) else
              'unknown' if not results or any(r['status'] == 'unknown' for r in results) or
              any(r['mapping'] == 'unmapped' for r in coverage) else 'pass')
    body = {'version': TIGHTEN_VERSION, 'status': status, 'checker_id': checker_id or None,
            'original_sha256': source_hash(original), 'candidate_sha256': source_hash(candidate),
            'requirements_sha256': _digest(requirements), 'obligations_sha256': _digest(obligations),
            'checks': results, 'requirements': coverage, 'meaning_preserved': 'not_established',
            'scope': 'declared_finite_fidelity_obligations; mappings are caller declarations',
            'heldout_feedback_to_clarifier': False}
    return {**body, 'sha256': _digest(body)}


def _policy(policy, original):
    if policy is None:
        return None
    _keys(policy, ('id', 'kind', 'original_sha256'))
    _text(policy['id'], 'Policy ID', 200)
    if policy['kind'] != 'ast_equivalent' or policy['original_sha256'] != source_hash(original):
        raise FidelityError('Equivalent rewrite policy must pin the original and require AST identity')
    return copy.deepcopy(policy)


def adoption_token(result, actor):
    """Trusted host helper after an explicit decision; a checksum, not a signature.

    Never call this from a model proposal or merely because tests/convergence pass.
    The actor is supplied by the authenticated host, not inferred from model text.
    """
    _text(actor, 'Decision actor', 200)
    return {'decision': 'adopt', 'actor': actor, 'original_sha256': result['original_sha256'],
            'candidate_sha256': result['candidate_sha256'], 'audit_sha256': result['audit_sha256']}


def adopt(result, decision=None):
    """Return a new result with an adoption decision; never modify the proposal.

    A deliberate host decision may adopt an unassessed meaning, recorded as such.
    It cannot erase failed obligations, an original requirement, or a prohibition
    on meaning changes. Changing requirements requires a newly audited proposal.
    """
    out = copy.deepcopy(result)
    integrity = {key: out[key] for key in ('version', 'original_program', 'candidate_program', 'original_sha256',
                 'candidate_sha256', 'rewrites', 'fidelity', 'requirement_map', 'equivalent_policy', 'allow_meaning_changes')}
    if (_digest(integrity) != out.get('audit_sha256') or
            source_hash(out['original_program']) != out['original_sha256'] or
            source_hash(out['candidate_program']) != out['candidate_sha256']):
        raise FidelityError('Tightening candidate/audit changed after review')
    out['program'] = out['original_program']
    out['changed'] = out['candidate_program'] != out['original_program']
    out['accepted_changed'] = False
    out['adoption'] = {'status': 'unchanged' if not out['changed'] else 'not_requested', 'basis': None,
                       'scope': 'host_decision_or_declared_syntax_equivalence; not a semantic truth certificate'}
    if not out['changed']:
        return out
    reason = None
    try:
        equivalent = _ast_identity(out['original_program']) == _ast_identity(out['candidate_program'])
    except S.SymblicError:
        equivalent = False
    if decision is not None:
        _keys(decision, ('decision', 'actor', 'original_sha256', 'candidate_sha256', 'audit_sha256'))
        _text(decision['actor'], 'Decision actor', 200)
        if decision['decision'] != 'adopt' or any(decision[k] != out[k] for k in (
                'original_sha256', 'candidate_sha256', 'audit_sha256')):
            reason = 'stale_or_mismatched_decision'
        elif out['fidelity']['status'] == 'fail':
            reason = 'failed_fidelity_obligation'
        elif not out['allow_meaning_changes'] and not equivalent:
            reason = 'meaning_changes_disabled'
        else:
            out['adoption'].update(status='adopted', basis='explicit_host_decision', decision=copy.deepcopy(decision))
    elif out['equivalent_policy'] is not None:
        if out['fidelity']['status'] == 'fail':
            reason = 'failed_fidelity_obligation'
        elif equivalent:
            out['adoption'].update(status='adopted', basis='predeclared_ast_equivalence',
                                   policy=out['equivalent_policy'])
        else:
            reason = 'equivalence_not_established'
    if reason:
        out['adoption'].update(status='rejected', reason=reason)
    if out['adoption']['status'] == 'adopted':
        out['program'] = out['candidate_program']
        out['accepted_changed'] = True
    return out


def audit_candidate(original, candidate, *, rewrites=(), requirements=(), obligations=(),
                    requirement_map=None, fidelity_checker=None, checker_id='', decision=None,
                    equivalent_policy=None, allow_meaning_changes=True):
    """Pure candidate audit/adoption boundary, reusable for existing saved jobs."""
    reqs, fixtures, mapping = _declarations(requirements, obligations, requirement_map, fidelity_checker, checker_id)
    if type(allow_meaning_changes) is not bool:
        raise FidelityError('allow_meaning_changes must be Boolean')
    policy = _policy(equivalent_policy, original)
    if not S.check(candidate)['ok']:
        raise FidelityError('Candidate must pass the static language check')
    result = {'version': TIGHTEN_VERSION, 'original_program': original, 'candidate_program': candidate,
              'original_sha256': source_hash(original), 'candidate_sha256': source_hash(candidate),
              'changed': candidate != original, 'candidate_status': 'proposed' if candidate != original else 'unchanged',
              'rewrites': copy.deepcopy(list(rewrites)), 'equivalent_policy': policy,
              'requirement_map': mapping,
              'allow_meaning_changes': allow_meaning_changes,
              'fidelity': _fidelity(original, candidate, reqs, fixtures, fidelity_checker, checker_id)}
    integrity = {key: result[key] for key in ('version', 'original_program', 'candidate_program', 'original_sha256',
                 'candidate_sha256', 'rewrites', 'fidelity', 'requirement_map', 'equivalent_policy', 'allow_meaning_changes')}
    result['audit_sha256'] = _digest(integrity)
    return adopt(result, decision)


def tighten(source: str, inputs: dict | None, panel: list, applicators, clarifier: str = 'claude:opus',
            rounds: int = 2, target: float = 1.0, log=None, diagnoses=TIGHTEN, hints: str = '', *,
            requirements=(), obligations=(), requirement_map=None, fidelity_checker=None, checker_id='',
            decision=None, equivalent_policy=None, allow_meaning_changes=True) -> dict:
    """probe (with readings) -> clarify every ask that is not converged -> probe again, up to `rounds`
    rewrites. v2 returns candidate_program for experimentation; program is the
    adopted source (the original by default). Agreement, parsing and the leak
    heuristic never establish fidelity. Heldout obligations run only after the
    final candidate is frozen and are never sent to the panel or clarifier.

    allow_meaning_changes=False forbids adopting a non-AST-identical candidate;
    it still permits proposing and inspecting that candidate in the experiment.
    """
    reqs, fixtures, mapping = _declarations(requirements, obligations, requirement_map, fidelity_checker, checker_id)
    policy = _policy(equivalent_policy, source)  # validate before any model call
    if type(allow_meaning_changes) is not bool:
        raise FidelityError('allow_meaning_changes must be Boolean')
    say = log or (lambda t: None)
    history, rewrites = [], []
    cur = source
    for r in range(rounds + 1):
        pr = probe(cur, inputs, panel, applicators, log=log, readings=True)
        history.append({'round': r, 'source_sha256': source_hash(cur),
                        'source_role': 'original' if cur == source else 'experimental_candidate',
                        'agreement_all': pr['agreement_all'], 'coverage': pr['coverage'],
                        'asks': [{k: a[k] for k in ('line', 'name', 'diagnosis', 'agreement_all',
                                                     'agreement_valid', 'coverage', 'distinct', 'suggestions',
                                                     'readings', 'flagged')}
                                 for a in pr['asks']]})
        say(f'round {r}: agreement {pr["agreement_all"]:.2f}, coverage {pr["coverage"]:.2f}')
        todo = [a for a in pr['asks'] if a['diagnosis'] in diagnoses]
        if not todo or r == rounds:
            break
        changed = False
        for a in todo:
            node, text = ask_instruction(cur, a['line'])
            if text is None:
                continue
            ty = _ask_type(cur, a['line'])
            opts = (ty.get('options') if ty and ty['k'] == 'enum' else ['true', 'false'] if ty and ty['k'] == 'bool'
                    else None)
            fix = clarify(text, a, clarifier, applicators, log=log, program=cur, hints=hints, options=opts)
            record = {'round': r, 'line': a['line'], 'name': a['name'], 'before': text, **fix,
                      'original_sha256': source_hash(source), 'before_sha256': source_hash(cur),
                      'candidate_sha256': None, 'candidate_included': False, 'status': 'proposed',
                      'requirement_ids': list(mapping.get(a['name'], [])),
                      'risks': _risks(text, fix.get('instruction', ''), opts)}
            record['assumption_records'] = [
                {'id': _digest([record['before_sha256'], a['name'], index, assumption]), 'text': assumption,
                 'origin': 'clarifier_proposed', 'status': 'proposed'}
                for index, assumption in enumerate(fix.get('assumptions') or [])]
            proposal = rewrite(cur, a['line'], text, fix['instruction']) if fix.get('ok') else None
            if proposal is not None:
                record['candidate_sha256'] = source_hash(proposal)
            if fix.get('leaks_answer'):
                record['status'] = 'rejected_answer_leak'
                record['risks'].append('answer_leak')
            if fix.get('ok') and not fix.get('leaks_answer'):
                new_src = proposal
                if new_src is not None and S.check(new_src)['ok']:
                    cur, changed = new_src, True
                    record.update(candidate_included=True, status='candidate_only')
                else:
                    record['status'] = 'rejected_static_or_literal'
            record['id'] = _digest(record)
            rewrites.append(record)
        if not changed:
            break
    result = audit_candidate(source, cur, rewrites=rewrites, requirements=reqs, obligations=fixtures,
                             requirement_map=mapping, fidelity_checker=fidelity_checker, checker_id=checker_id,
                             decision=decision, equivalent_policy=policy, allow_meaning_changes=allow_meaning_changes)
    return {**result, 'history': history}


def tighten_paper(paper: str, panel: list, applicators, clarifier: str = 'claude:opus', rounds: int = 2,
                  log=None, *, decision=None, **fidelity_options) -> dict:
    """tighten() on a .symd paper: compile it, tighten the compiled program, and write every accepted rewrite
    into a candidate copy of the paper's code block. `paper` remains the original
    until adoption; `candidate_paper` is available for heldout experiments. The
    paper's exact bytes are pinned separately from its compiled program.
    """
    from symblic.authoring import paper as P
    compiled = P.compile_paper(paper)
    # the paper linter (vague quantities, percentages without a basis; no model) tells the clarifier where to look
    found = P.lint(paper) if hasattr(P, 'lint') else []
    hints = '\n'.join(f'- paper line {w.get("line")}: {w.get("message")}' for w in found[:12])
    res = tighten(compiled['source'], None, panel, applicators, clarifier=clarifier, rounds=rounds, log=log,
                  hints=hints, **fidelity_options)
    new_paper = paper
    applied = []

    def instructions(source):
        out = {}
        try:
            for st in SR._flat(S.parse(source)['statements']):
                if st.k == 'ask' and all(isinstance(x, str) for x in st.parts):
                    out[st.line] = ''.join(st.parts)
        except S.SymblicError:
            pass
        return out
    # map each ask's ORIGINAL instruction to its FINAL one (rewrites can chain over rounds: the second rewrite's
    # "before" is the first rewrite, which the paper never contained)
    first, last = instructions(compiled['source']), instructions(res['candidate_program'])
    for line, old in sorted(first.items()):
        new = last.get(line)
        if not new or new == old:
            continue
        old_lit = json.dumps(old, ensure_ascii=False)
        if old_lit in new_paper:
            new_paper = new_paper.replace(old_lit, json.dumps(new, ensure_ascii=False), 1)
            paper_line = next((m['paper_line'] for m in compiled['map'] if m['line'] == line), None)
            steps = [r for r in res['rewrites'] if r.get('line') == line and r.get('candidate_included')]
            applied.append({'line': line, 'paper_line': paper_line, 'before': old, 'instruction': new,
                            'assumptions': (steps[-1].get('assumptions') if steps else []), 'rewrites': len(steps)})
    if P.compile_paper(new_paper)['source'] != res['candidate_program']:
        raise FidelityError('Candidate paper does not compile to the audited candidate program')
    body = {'original_paper': paper, 'candidate_paper': new_paper, 'original_paper_sha256': source_hash(paper),
            'candidate_paper_sha256': source_hash(new_paper), 'compiled_audit_sha256': res['audit_sha256']}
    result = {**res, **body, 'paper_audit_sha256': _digest(body), 'compiled_result': res,
              'paper': new_paper if res['accepted_changed'] else paper, 'applied': applied,
              'applied_to': 'candidate_paper', 'lint': found}
    return adopt_paper(result, decision) if decision is not None else result


def paper_adoption_token(result, actor):
    _text(actor, 'Decision actor', 200)
    return {'decision': 'adopt', 'actor': actor, 'original_paper_sha256': result['original_paper_sha256'],
            'candidate_paper_sha256': result['candidate_paper_sha256'], 'audit_sha256': result['paper_audit_sha256']}


def adopt_paper(result, decision):
    """Explicitly adopt the exact candidate paper; no second model call/check run."""
    out = copy.deepcopy(result)
    _keys(decision, ('decision', 'actor', 'original_paper_sha256', 'candidate_paper_sha256', 'audit_sha256'))
    body = {key: out[key] for key in ('original_paper', 'candidate_paper', 'original_paper_sha256',
                                     'candidate_paper_sha256', 'compiled_audit_sha256')}
    if (_digest(body) != out['paper_audit_sha256'] or source_hash(out['original_paper']) != out['original_paper_sha256'] or
            source_hash(out['candidate_paper']) != out['candidate_paper_sha256'] or
            out['compiled_result']['audit_sha256'] != out['compiled_audit_sha256']):
        raise FidelityError('Paper/audit changed after review')
    matching = (decision['decision'] == 'adopt' and decision['original_paper_sha256'] == out['original_paper_sha256'] and
                decision['candidate_paper_sha256'] == out['candidate_paper_sha256'] and decision['audit_sha256'] == out['paper_audit_sha256'])
    if not matching:
        out.update(paper=out['original_paper'], program=out['original_program'], accepted_changed=False,
                   adoption={'status': 'rejected', 'reason': 'stale_or_mismatched_decision'})
        return out
    adopted = adopt(out['compiled_result'], adoption_token(out['compiled_result'], decision['actor']))
    out.update(compiled_result=adopted, program=adopted['program'], accepted_changed=adopted['accepted_changed'],
               adoption={**adopted['adoption'], 'paper_decision': copy.deepcopy(decision)},
               paper=out['candidate_paper'] if adopted['accepted_changed'] else out['original_paper'])
    return out


def paper_experiment(paper: str, probe_panel: list, heldout: list, clarifier: str, runner, applicators,
                     log=None) -> dict:
    """The fresh-readers test of a tightened paper: reproduce the paper on held-out cohorts, tighten it with a
    probe panel that shares no model with them, reproduce the tightened paper on the same held-out cohorts."""
    from symblic.authoring import paper as P
    say = log or (lambda t: None)
    say('baseline: the paper as written, held-out cohorts')
    before = P.reproduce(paper, heldout, runner)
    say('tightening with the probe panel')
    t = tighten_paper(paper, probe_panel, applicators, clarifier=clarifier, log=log)
    after = None
    if t['changed']:
        say('the tightened paper, the same held-out cohorts')
        after = P.reproduce(t['candidate_paper'], heldout, runner)

    def brief(rep):
        if rep is None:
            return None
        return {'reproduces': rep['reproduces'], 'results_reproduce': rep.get('results_reproduce'),
                'model_reproduced': rep['model_reproduced'], 'model_statements': rep['model_statements'],
                'coverage': rep.get('coverage'),
                'cohorts': [{k: c.get(k) for k in ('by', 'status', 'fingerprint', 'error')} for c in rep['cohorts']],
                'underspecified': rep['underspecified'], 'text': P.report_text(rep)}
    return {'probe': probe_panel, 'heldout': heldout, 'clarifier': clarifier, 'before': brief(before),
            'tightened': {'changed': t['changed'], 'applied': t['applied'], 'history': t['history'],
                          'rewrites': t['rewrites'], 'candidate_status': t['candidate_status'],
                          'fidelity': t['fidelity'], 'adoption': t['adoption']},
            'after': brief(after), 'paper_after': t['candidate_paper'] if t['changed'] else None,
            'paper_after_role': 'experimental_candidate'}


def run_job(folder: str, applicators=None, *, fidelity_checker=None, checker_id='') -> dict:
    """A tightening job (started by a host, for example the original host dashboard's tighten route):
    program.sym + meta.json in, result.json (0600) out; a line per step in log.txt. The job only orchestrates; the
    applicators decide where models run.
    Fidelity declarations may be retained in metadata. A checker is injected by
    trusted host code, never imported/executed from a JSON-supplied module name.
    A job proposes candidates; an adoption decision belongs to a later host action.
    """
    import os
    import time

    def save(data):
        path = os.path.join(folder, 'result.json')
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, default=str)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    logf = open(os.path.join(folder, 'log.txt'), 'a', encoding='utf-8')
    os.chmod(os.path.join(folder, 'log.txt'), 0o600)

    def log(text):
        logf.write(time.strftime('%H:%M:%S ') + str(text) + '\n')
        logf.flush()
    with open(os.path.join(folder, 'meta.json'), encoding='utf-8') as f:
        meta = json.load(f)
    with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as f:
        source = f.read()
    if applicators is None:
        from symblic.providers import applicators as SA
        applicators = SA.Applicators(owner_label=f'operator (Symblic tighten {meta.get("id")})',
                                     run_id=f'tighten-{meta.get("id")}')
    save({'status': 'running', 'started': time.time()})
    try:
        res = tighten(source, meta.get('inputs') or None, list(meta['panel']), applicators,
                      clarifier=meta.get('clarifier') or 'claude:sonnet', rounds=int(meta.get('rounds') or 2), log=log,
                      requirements=meta.get('requirements') or [], obligations=meta.get('fidelity_obligations') or [],
                      requirement_map=meta.get('requirement_map') or {}, fidelity_checker=fidelity_checker,
                      checker_id=checker_id, equivalent_policy=meta.get('equivalent_policy'),
                      allow_meaning_changes=meta.get('allow_meaning_changes', True))
        out = {'status': 'done', 'finished': time.time(), **res}
        log('done: ' + ('a candidate rewrite was proposed; original retained' if res['changed'] else 'no candidate rewrite'))
    except Exception as e:  # noqa: BLE001  (a failed job is a visible result, not a lost one)
        out = {'status': 'failed', 'finished': time.time(), 'error': f'{type(e).__name__}: {e}'[:600]}
        log(out['error'])
    save(out)
    logf.close()
    return out


def main(argv=None) -> int:
    import argparse
    import os
    import tempfile
    ap = argparse.ArgumentParser(prog='python3 -m symblic.authoring.tighten', description='The convergence compiler.')
    ap.add_argument('cmd', choices=['paper', 'job'])
    ap.add_argument('path', nargs='?', default='')
    ap.add_argument('--dir', default='', help='job: the job folder (program.sym, meta.json)')
    ap.add_argument('--probe', default='', help='comma-separated applicators that drive tightening')
    ap.add_argument('--heldout', default='', help='comma-separated cohorts that judge the paper (one per cohort)')
    ap.add_argument('--clarifier', default='', help='the applicator that rewrites ambiguous statements: a capable '
                    'model, for example command:claude (see symblic/providers/applicators.py) or an ollama: model')
    ap.add_argument('--out', default='', help='folder for experiment.json and the tightened paper')
    a = ap.parse_args(argv)
    from symblic.providers import applicators as symblic_apply
    symblic_apply.install_sigterm()            # a stopped job cancels its live runs
    if a.cmd == 'job':
        if not a.dir:
            ap.error('job needs --dir')
        return 0 if run_job(a.dir)['status'] == 'done' else 1
    if not (a.path and a.probe and a.heldout and a.clarifier and a.out):
        ap.error('paper needs PATH, --probe, --heldout, --clarifier and --out')
    from symblic.providers import applicators as SA
    apps = SA.Applicators(owner_label='operator (tighten)')

    def runner(source, by):
        folder = tempfile.mkdtemp(prefix='symblic-tighten-')
        run = SR.Run(source, {}, SA.Applicators(owner_label='operator (tighten heldout)'),
                     {'by': by}, folder=folder, log=lambda t: print(f'[{by}] {t}', flush=True))
        return {'report': run.execute(), 'trace': run.trace}
    split = lambda v: [x.strip() for x in v.split(',') if x.strip()]
    paper = open(a.path, encoding='utf-8').read()
    res = paper_experiment(paper, split(a.probe), split(a.heldout), a.clarifier, runner, apps,
                           log=lambda t: print(t, flush=True))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'experiment.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=1, default=str)
    if res['paper_after']:
        with open(os.path.join(a.out, 'tightened.symd'), 'w', encoding='utf-8') as f:
            f.write(res['paper_after'])
    for k in ('before', 'after'):
        if res[k]:
            print(f'--- {k}\n{res[k]["text"]}')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())

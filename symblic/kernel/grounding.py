"""Source witnesses: check that a model's answer is quoted from the source it claims, by exact offsets.

Models propose spans ("this value comes from characters 120 to 141 of document D"). A trusted caller supplies
the source and an immutable field, summary or finite-catalogue contract. Exact source correspondence is then
checked by code: source_record/source_span build the references, verify_field, verify_summary and
verify_items check a proposal against its contract. Source truth, the contract's semantic adequacy and
omitted qualifications are never inferred from textual overlap. There is no model, store or I/O here; this is
not a general semantic-entailment oracle.

Offsets are Python/Unicode code points, not UTF-8 bytes or JavaScript UTF-16 code units. No Unicode
normalization, case-folding, alias inference, unit conversion or natural-language negation parser runs.
Unsupported field structure refuses. The field language deliberately requires a literal, whole-field template.
Span boundaries use the kernel's quotes() numeral classes; the kernel module is imported on first use, so
importing this module loads nothing else.

Depends on: symblic.kernel.language (on first use). Used by: the language builtins source_record, source_span,
verify_source_field, verify_source_summary and verify_source_items, and the delegation contracts.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
from fractions import Fraction
import hashlib
import json
import re
import unicodedata

VERSION = 1                     # record format of sources, contracts and receipts
RULES = 4                       # verdict rules: 4 = shared quotes() numeral boundaries, exponent/power continuations
                                # uncatalogued items (2026-10-04 core repair); kernel_id() carries it
MAX_SOURCE = 200000
MAX_BYTES = 2000000
MAX_ROWS = 256
MAX_DEPTH = 24
MAX_NODES = 32768
MAX_NUMBER = 256
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_DECIMAL = re.compile(r'[+-]?[0-9]+(?:\.[0-9]+)?\Z')
_SPACE = ' \t\r\n'
# Marks that join digit groups inside one written number: decimal points and commas, and grouping
# apostrophes, underscores and no-break/thin spaces. ASCII whitespace always ends a numeric token.
# Between two digits the kernel's numeral operators (symblic._OPERATORS) join one numeral too: 3/4, 2×10, 3·5.
_NUMERAL_OPERATORS = frozenset('/\u2044\u2215\u00b7\u00d7\u00f7*')
_NUMBER_JOINERS = frozenset(".,'\u2019_\u00a0\u2009\u202f\u066b\u066c") | _NUMERAL_OPERATORS
# Runs of white space: quotes() reads each run as one space when it looks for whole numerals.
_WHITE_RUN = re.compile(r'\s+')
_LONG_WHITE_RUN = re.compile(r'\s{2,}')
# Marks inside one word when written between two word characters: can't, non-toxic.
_WORD_JOINERS = frozenset("'\u2019-\u2010\u2011")
# A sign directly before a numeral belongs to it (-5); after a word character it joins (10-20).
_SIGNS = frozenset('+-\u2212\u2013\u00b1')
_UNKNOWN = ['source_truth', 'contract_semantic_adequacy', 'undeclared_qualifications']


class GroundingError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise GroundingError(code, message)


def _encoded(value):
    count = 0

    def visit(item, depth):
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _fail('limit', 'JSON node/depth limit exceeded (cycles are not allowed)')
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            if item.bit_length() > 4096:
                _fail('limit', 'JSON integer is too large')
            return
        if type(item) is str:
            if len(item) > MAX_BYTES:
                _fail('limit', 'JSON string is too long')
            try:
                item.encode('utf-8')
            except UnicodeEncodeError:
                _fail('unicode', 'Unpaired Unicode surrogate')
            return
        if type(item) is list:
            if len(item) > MAX_NODES:
                _fail('limit', 'JSON list is too large')
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
            return
        _fail('json', 'Only exact plain JSON values are accepted')

    visit(value, 0)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    if len(raw) > MAX_BYTES:
        _fail('limit', 'Encoded JSON byte limit exceeded')
    return raw


def digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _keys(value, keys, kind):
    if type(value) is not dict or set(value) != set(keys):
        _fail('schema', f'{kind} has missing or unknown fields')


def _text(value, limit, *, empty=False):
    if type(value) is not str or len(value) > limit or (not value and not empty):
        _fail('text', 'Expected bounded text')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        _fail('unicode', 'Unpaired Unicode surrogate')
    return value


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail('id', 'Expected a bounded ASCII identifier')
    return value


def _whole(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail('integer', 'Integer is outside its allowed range')
    return value


def source_record(ident, text, revision=1):
    _id(ident)
    _text(text, MAX_SOURCE, empty=True)
    _whole(revision, 1, 2**53 - 1)
    return {'version': VERSION, 'id': ident, 'revision': revision, 'text': text,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def _source(source):
    _keys(source, ('version', 'id', 'revision', 'text', 'sha256'), 'Source')
    if type(source['version']) is not int or source['version'] != VERSION:
        _fail('version', 'Unknown source version')
    expected = source_record(source['id'], source['text'], source['revision'])
    if expected != source:
        _fail('source_hash', 'Source digest differs from exact retained text')
    return source


def source_ref(source):
    _source(source)
    return {'source_id': source['id'], 'revision': source['revision'], 'source_sha256': source['sha256']}


def source_span(source, start, end):
    _source(source)
    _whole(start, 0, len(source['text']))
    _whole(end, start, len(source['text']))
    return {**source_ref(source), 'start': start, 'end': end, 'quote': source['text'][start:end]}


def check_span(source, span, *, allow_empty=False):
    """Return a detached exact witness or raise; checks source revision as well as text."""
    _source(source)
    _keys(span, ('source_id', 'revision', 'source_sha256', 'start', 'end', 'quote'), 'Span')
    _encoded(span)
    if {key: span[key] for key in ('source_id', 'revision', 'source_sha256')} != source_ref(source):
        _fail('stale_source', 'Span names another source or revision')
    expected = source_span(source, span['start'], span['end'])
    if span != expected:
        _fail('quote_mismatch', 'Quote differs from the exact code-point source interval')
    if not allow_empty and span['start'] == span['end']:
        _fail('empty_span', 'An empty span supplies no source witness')
    return copy.deepcopy(span)


def _seal(body):
    return {**body, 'sha256': digest(body)}


def _bounded_rows(rows):
    if type(rows) is not list or len(rows) > MAX_ROWS:
        _fail('limit', f'Expected at most {MAX_ROWS} rows')
    return rows


def _named_spans(source, rows):
    checked = []
    for row in _bounded_rows(rows):
        _keys(row, ('id', 'span'), 'Named span')
        checked.append({'id': _id(row['id']), 'span': check_span(source, row['span'])})
    if len({row['id'] for row in checked}) != len(checked):
        _fail('duplicate', 'Duplicate requirement/catalog IDs')
    return sorted(checked, key=lambda row: row['id'])


def field_contract(ident, source, *, labels, region, separator, prefix, suffix,
                   max_gap=64, unit='', currency='', entity=None):
    """Declare literal label + prefix + decimal + suffix, within one source field.

    Labels/aliases are author-supplied exact strings. Whitespace around the whole
    separated field is allowed; text inside the template is exact. `unit` and
    `currency` are exact literals that must appear in prefix/suffix, not inferred
    physical dimensions, conversions, or currency names. Entity scope is an
    optional exact source witness inside the explicitly selected region.
    """
    _source(source)
    _id(ident)
    if type(labels) is not list or not 1 <= len(labels) <= 32:
        _fail('labels', 'Supply 1..32 exact labels/aliases')
    for label in labels:
        _text(label, 256)
        if label.strip(_SPACE) != label or '\n' in label or '\r' in label:
            _fail('labels', 'Labels cannot have outside whitespace or line breaks')
    if len(set(labels)) != len(labels):
        _fail('duplicate', 'Duplicate labels/aliases')
    region = check_span(source, region)
    _text(separator, 16)
    _text(prefix, 256, empty=True)
    _text(suffix, 256, empty=True)
    _whole(max_gap, 0, 256)
    if len(prefix) > max_gap:
        _fail('gap', 'The declared prefix exceeds max_gap')
    if any(separator in part for part in [*labels, prefix, suffix]):
        _fail('separator', 'A field separator cannot occur inside the declared template')
    for literal in (unit, currency):
        _text(literal, 64, empty=True)
        if literal and literal not in prefix and literal not in suffix:
            _fail('unit_currency', 'Declared unit/currency literal must occur in the exact prefix or suffix')
    if entity is not None:
        entity = check_span(source, entity)
        if not region['start'] <= entity['start'] < entity['end'] <= region['end']:
            _fail('entity_scope', 'Entity witness must be inside the selected region')
    return _seal({'version': VERSION, 'kind': 'literal_field', 'id': ident, 'source': source_ref(source),
                  'labels': sorted(labels), 'region': region, 'separator': separator,
                  'prefix': prefix, 'suffix': suffix, 'max_gap': max_gap,
                  'unit': unit, 'currency': currency, 'entity': entity})


def summary_contract(ident, source, *, required, joiner='\n…\n', max_spans=64):
    _source(source)
    _id(ident)
    _text(joiner, 256, empty=True)
    _whole(max_spans, 0, MAX_ROWS)
    required = _named_spans(source, required)
    return _seal({'version': VERSION, 'kind': 'extractive_summary', 'id': ident,
                  'source': source_ref(source), 'required': required,
                  'joiner': joiner, 'max_spans': max_spans})


def list_contract(ident, source, *, catalog=None, require_nonempty=False):
    """None means unknown universe; [] is an explicitly declared empty universe."""
    _source(source)
    _id(ident)
    if type(require_nonempty) is not bool:
        _fail('schema', 'require_nonempty must be boolean')
    if catalog is not None:
        catalog = _named_spans(source, catalog)
        if require_nonempty and not catalog:
            _fail('contract', 'An explicitly empty catalog contradicts require_nonempty')
    return _seal({'version': VERSION, 'kind': 'source_items', 'id': ident,
                  'source': source_ref(source), 'catalog': catalog, 'require_nonempty': require_nonempty})


def _contract(source, contract, kind):
    _source(source)
    _encoded(contract)
    common = {'version', 'kind', 'id', 'source', 'sha256'}
    extras = {'literal_field': {'labels', 'region', 'separator', 'prefix', 'suffix', 'max_gap', 'unit', 'currency', 'entity'},
              'extractive_summary': {'required', 'joiner', 'max_spans'},
              'source_items': {'catalog', 'require_nonempty'}}
    _keys(contract, common | extras[kind], 'Contract')
    if type(contract['version']) is not int or contract['version'] != VERSION or contract['kind'] != kind:
        _fail('version', 'Contract kind/version differs')
    if contract['source'] != source_ref(source):
        _fail('stale_source', 'Contract names another source or revision')
    args = {key: contract[key] for key in extras[kind]}
    builder = {'literal_field': field_contract, 'extractive_summary': summary_contract,
               'source_items': list_contract}[kind]
    if builder(contract['id'], source, **args) != contract:
        _fail('contract_hash', 'Contract is modified or not in canonical form')
    return contract


def _candidate(candidate, contract, fields):
    _keys(candidate, {'contract_sha256', *fields}, 'Candidate')
    _encoded(candidate)
    if candidate['contract_sha256'] != contract['sha256']:
        _fail('contract_changed', 'Candidate does not answer the caller-pinned contract')


def _report(source, contract, candidate, *, accepted, issues, scope, coverage=None, **values):
    body = {'version': VERSION, 'source': source_ref(source), 'contract_sha256': contract['sha256'],
            'candidate_sha256': digest(candidate), 'accepted': accepted, 'issues': issues,
            'assurance': {'scope': scope, 'source_truth': 'not_established',
                          'semantic_entailment': 'not_established'},
            'coverage': coverage or {'scope': 'declared_contract'}, 'unknown': list(_UNKNOWN), **values}
    return {**body, 'receipt_sha256': digest(body)}


def _refusal(source, contract, candidate, error, scope):
    # Malformed/cyclic candidates cannot be safely hashed; the accepted contract
    # still pins the failed check. A hash is never fabricated for rejected JSON.
    try:
        candidate_hash = digest(candidate)
    except GroundingError:
        candidate_hash = ''
    body = {'version': VERSION, 'source': source_ref(source), 'contract_sha256': contract['sha256'],
            'candidate_sha256': candidate_hash, 'accepted': False,
            'issues': [{'code': error.code, 'message': str(error)}],
            'assurance': {'scope': scope, 'source_truth': 'not_established',
                          'semantic_entailment': 'not_established'},
            'coverage': {'scope': 'declared_contract', 'complete': False}, 'unknown': list(_UNKNOWN)}
    return {**body, 'receipt_sha256': digest(body)}


def _occurrences(text, label, begin, end):
    found = []
    at = begin
    while True:
        at = text.find(label, at, end)
        if at < 0:
            return found
        after = at + len(label)
        # Prevent Total from anchoring Totality; punctuation labels remain exact.
        left_ok = at == begin or not (text[at - 1].isalnum() or text[at - 1] == '_') or not label[0].isalnum()
        right_ok = after == end or not (text[after].isalnum() or text[after] == '_') or not label[-1].isalnum()
        if left_ok and right_ok:
            found.append((at, after, label))
            if len(found) > MAX_ROWS:
                _fail('ambiguous_label', 'Too many label occurrences in the selected region')
        at += 1


# This is only a boundary recognizer, not a parser or evaluator. The field
# value still must match _DECIMAL exactly. Exponents/grouping are recognized to
# refuse truncation of an unsupported written number into a supported fragment.
_WRITTEN_NUMBER = re.compile(
    '[' + re.escape(''.join(sorted(_SIGNS))) + ']?'
    r'(?:\d+(?:[' + re.escape(''.join(sorted(_NUMBER_JOINERS))) + r']\d+)*|[.,\u066b]\d+)'
    r'(?:[eE][+\-\u2212]?\d+)?')


def _number_boundaries(text):
    """Finite scan over MAX_SOURCE characters, with no candidate execution."""
    return [(match.start(), match.end()) for match in _WRITTEN_NUMBER.finditer(text)]


def _splits_number(boundaries, at):
    return any(start < at < end for start, end in boundaries)


def _word_char(ch):
    """The kernel quotes() word classes: letters/digits of any script, '_', combining marks, format chars."""
    if not ch:
        return False
    if ch.isalnum() or ch == '_':
        return True
    category = unicodedata.category(ch)
    return category[0] == 'M' or category == 'Cf'


def _inside_token(text, at):
    """True when a span boundary at `at` would cut a word, a numeral or a numeral's sign.

    Same classes as the kernel's whole-token quotes(), plus apostrophes/hyphens between two word
    characters (a cut there turns "can't" into "can" and "non-toxic" into "toxic").
    """
    if at <= 0 or at >= len(text):
        return False
    left, right = text[at - 1], text[at]
    before = text[at - 2] if at >= 2 else ''
    after = text[at + 1] if at + 1 < len(text) else ''
    if _word_char(left) and _word_char(right):
        return True                     # inside a word or numeral, or a letter cut from its mark
    if unicodedata.category(right)[0] == 'M':
        return True                     # a combining mark cut from its base character
    if right in _WORD_JOINERS and _word_char(left) and _word_char(after):
        return True                     # can|'t, non|-toxic
    if left in _WORD_JOINERS and _word_char(before) and _word_char(right):
        return True                     # can'|t, non-|toxic
    if left.isdecimal() and right in _NUMBER_JOINERS and after.isdecimal():
        return True                     # 3|.14, 1|,250
    if left in _NUMBER_JOINERS and before.isdecimal() and right.isdecimal():
        return True                     # 3.|14, 1,|250
    return left in _SIGNS and right.isdecimal() and not _word_char(before)   # -|5


def _numeral_checker(text):
    """The kernel quotes() whole-numeral rule for spans of `text`: check(start, end) -> (start_cuts, end_cuts).

    It calls the kernel's own predicates (symblic.kernel.language._whole_left, _whole_right, and the _SCIENTIFIC and _GROUPED
    spans), so a numeral is cut here exactly where quotes() would refuse the same quote: fractions and dates
    (3/4), products and powers (2×10, 10^3, 10**3, 10⁻³), scientific notation (1.5×10^3, 6.02 × 10²³), digit
    groups (1 250 000) and dash signs (－5). Like quotes(), it reads the text with each run of white space as one
    space and trims a span's outer white space; offsets map back exactly. O(len(text)) once, O(log) per span.
    """
    import bisect
    from symblic.kernel import language as kernel           # the single definition of quotes()'s numeral classes
    view = _WHITE_RUN.sub(' ', text)
    ends, removed, total = [], [], 0
    for match in _LONG_WHITE_RUN.finditer(text):        # each such run shrinks to one space in the view
        total += match.end() - match.start() - 1
        ends.append(match.end())
        removed.append(total)

    def position(offset):               # the view index of a source offset that is not white space
        k = bisect.bisect_right(ends, offset) - 1
        return offset - (removed[k] if k >= 0 else 0)
    found = (kernel._spans(kernel._SCIENTIFIC, view), kernel._spans(kernel._GROUPED, view))

    def check(start, end):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start == end:
            return False, False
        i, j = position(start), position(end - 1) + 1
        # The kernel predicates read the quote's first two and last two characters only.
        left = (not kernel._whole_left(view, i, view[i:min(j, i + 2)])
                or any(kernel._cuts_span(spans, i, i) for spans in found))
        right = (not kernel._whole_right(view, j, view[max(i, j - 2):j])
                 or any(kernel._cuts_span(spans, j, j) for spans in found))
        return left, right
    return check


def _whole_token_spans(text, spans, exempt=frozenset()):
    """Refuse spans whose start or end cuts a token; caller-declared boundary positions are exempt.

    Words and intra-word joiners: _inside_token. Numerals: the kernel quotes() rule (_numeral_checker), so a span
    is refused wherever quotes() refuses the same quote, and more strictly at intra-word apostrophes and hyphens.
    """
    numeral_cuts = _numeral_checker(text) if spans else None
    for row in spans:
        cuts = numeral_cuts(row['start'], row['end'])
        for at, numeral_cut in zip((row['start'], row['end']), cuts):
            if at not in exempt and (numeral_cut or _inside_token(text, at)):
                _fail('partial_token', 'Spans must start and end at whole-word and whole-numeral boundaries '
                                       f'(offset {at} cuts a token)')


def _numeral_goes_on(text, at):
    """True when the written number ending just before `at` continues as a number character (², ½, Ⅻ), an
    exponent (e5, E-3, e+2) or a power (^3, **3, ⁻³), beyond the digits and joiners checked before. quotes()
    refuses the same cut; a field value read there would truncate 10² to 10 or 1e5 to 1."""
    if at >= len(text):
        return False
    ch = text[at]
    if unicodedata.category(ch)[0] == 'N' or ch in '^⁺⁻':
        return True
    power = text.startswith('**', at)
    if ch not in 'eE' and not power:
        return False
    at += 2 if power else 1
    if at < len(text) and text[at] in _SIGNS:
        at += 1
    return at < len(text) and text[at].isdecimal()


def verify_field(source, contract, candidate):
    """Check source association for one decimal field; candidate provides two spans.

    Candidate: {contract_sha256, label: span, value: span}. Values are obtained
    from the witnessed source, so there is no separate unchecked numeric answer.
    """
    scope = 'declared_literal_field_template'
    try:
        _contract(source, contract, 'literal_field')
    except GroundingError:
        raise  # A bad caller contract/source is not a bad model candidate.
    try:
        _candidate(candidate, contract, ('label', 'value'))
        label = check_span(source, candidate['label'])
        value = check_span(source, candidate['value'])
        text, region = source['text'], contract['region']
        begin, end = region['start'], region['end']
        found = []
        for alias in contract['labels']:
            found.extend(_occurrences(text, alias, begin, end))
        if len(found) != 1:
            _fail('ambiguous_label' if found else 'missing_label',
                  'Exactly one declared label occurrence is required in the caller-selected region')
        start, stop, _ = found[0]
        if label['start'] != start or label['end'] != stop:
            _fail('wrong_referent', 'Candidate label is not the declared unique field anchor')
        separator = contract['separator']
        previous = text.rfind(separator, begin, start)
        field_start = begin if previous < 0 else previous + len(separator)
        following = text.find(separator, stop, end)
        field_end = end if following < 0 else following
        boundary = field_end
        numeric_boundaries = _number_boundaries(text)
        segment = text[field_start:field_end]
        leading = len(segment) - len(segment.lstrip(_SPACE))
        trailing = len(segment) - len(segment.rstrip(_SPACE))
        field_start += leading
        field_end -= trailing
        if start != field_start:
            _fail('unsupported_layout_or_negation', 'Text before the label is outside the declared whole-field template')
        # The field ends at the first separator (or the region end). When that boundary falls inside one
        # written number ('1,200' with separator ',', '3.75' with '.'), the field is ambiguous: refuse
        # rather than accept a truncated prefix of the number.
        if _splits_number(numeric_boundaries, boundary):
            _fail('ambiguous_number_boundary',
                  'The field boundary (separator or region end) falls inside a written number; refusing instead of truncating it')
        expected_start = stop + len(contract['prefix'])
        expected_end = field_end - len(contract['suffix'])
        if (value['start'] != expected_start or value['end'] != expected_end
                or text[stop:expected_start] != contract['prefix']
                or text[expected_end:field_end] != contract['suffix']):
            _fail('unsupported_relation_unit_or_negation',
                  'Value position, surrounding text, unit or currency differs from the declared template')
        if len(value['quote']) > MAX_NUMBER or not _DECIMAL.fullmatch(value['quote']):
            _fail('unsupported_number', 'Only an exact signed decimal literal is supported by this contract')
        if any(_splits_number(numeric_boundaries, at) for at in (value['start'], value['end'])):
            _fail('ambiguous_number_boundary',
                  'The value span cuts a written number, sign or exponent; both boundaries must preserve the whole numeral')
        number = Fraction(value['quote'])
        if _numeral_goes_on(text, value['end']):
            _fail('ambiguous_number_boundary', 'The written number continues after the value span (a number '
                                               'character, exponent or power); refusing instead of truncating it')
        return _report(source, contract, candidate, accepted=True, issues=[], scope=scope,
                       coverage={'scope': 'one_declared_field', 'required': [contract['id']],
                                 'checked': [contract['id']], 'missing': [], 'complete': True},
                       value={'source_text': value['quote'], 'numerator': str(number.numerator),
                              'denominator': str(number.denominator)},
                       label=label, value_span=value, unit=contract['unit'], currency=contract['currency'],
                       entity=contract['entity'])
    except GroundingError as error:
        return _refusal(source, contract, candidate, error, scope)


def verify_summary(source, contract, candidate):
    """Render exact selected spans and check required span IDs, including exceptions.

    Candidate: {contract_sha256, spans: [...], text: <claimed exact rendering>}.
    The required spans are caller-owned; no overlap score claims paraphrase truth.
    """
    scope = 'exact_extraction_and_declared_span_coverage'
    _contract(source, contract, 'extractive_summary')
    try:
        _candidate(candidate, contract, ('spans', 'text'))
        _text(candidate['text'], MAX_SOURCE, empty=True)
        selected = [check_span(source, row) for row in _bounded_rows(candidate['spans'])]
        if len(selected) > contract['max_spans']:
            _fail('limit', 'Selected summary exceeds its declared span limit')
        if len({(row['start'], row['end']) for row in selected}) != len(selected):
            _fail('duplicate', 'Duplicate selected summary spans')
        # Preserve source order and disallow overlaps: duplicated/crossed quotes
        # can manufacture misleading repetition even though each quote exists.
        if any(left['end'] > right['start'] for left, right in zip(selected, selected[1:])):
            _fail('order', 'Summary spans must be disjoint and in source order')
        # A cut inside a word manufactures text the source never says ('unsafe' -> 'safe'), even though
        # every character is quoted. Caller-declared required boundaries remain authoritative.
        declared = {at for row in contract['required'] for at in (row['span']['start'], row['span']['end'])}
        _whole_token_spans(source['text'], selected, frozenset(declared))
        rendered = contract['joiner'].join(row['quote'] for row in selected)
        if candidate['text'] != rendered:
            _fail('unwitnessed_summary_text', 'Summary text differs from exact concatenation of selected source spans')
        checked, missing = [], []
        for requirement in contract['required']:
            span = requirement['span']
            covered = any(row['start'] <= span['start'] and span['end'] <= row['end'] for row in selected)
            (checked if covered else missing).append(requirement['id'])
        issues = ([{'code': 'missing_required_spans', 'ids': missing}] if missing else [])
        return _report(source, contract, candidate, accepted=not issues, issues=issues, scope=scope,
                       coverage={'scope': 'caller_declared_required_spans',
                                 'required': [row['id'] for row in contract['required']],
                                 'checked': checked, 'missing': missing, 'complete': not missing},
                       rendered=rendered, selected=selected)
    except GroundingError as error:
        return _refusal(source, contract, candidate, error, scope)


def proposed_summary(source, text, links):
    """Free-form output remains a proposal even when all cited spans are exact."""
    _source(source)
    _text(text, MAX_SOURCE, empty=True)
    checked = [check_span(source, row) for row in _bounded_rows(links)]
    body = {'version': VERSION, 'origin': 'model_proposal', 'status': 'unknown', 'text': text,
            'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'source': source_ref(source), 'links': checked, 'source_links_checked': True,
            'assurance': {'scope': 'exact_source_links_only', 'source_truth': 'not_established',
                          'semantic_entailment': 'not_established'}, 'unknown': list(_UNKNOWN)}
    return {**body, 'sha256': digest(body)}


def verify_items(source, contract, candidate):
    """Separate per-item source support from exhaustive finite-catalog coverage.

    Candidate: {contract_sha256, items: [{id, span}, ...]}. With no caller
    catalog, enumeration_complete is 'unknown', including for the empty list.
    With a catalog, item IDs must map to the exact declared source witnesses.
    """
    scope = 'exact_items_and_optional_declared_finite_catalog'
    _contract(source, contract, 'source_items')
    try:
        _candidate(candidate, contract, ('items',))
        items = _named_spans(source, candidate['items'])
        if len({(row['span']['start'], row['span']['end']) for row in items}) != len(items):
            _fail('duplicate', 'One source occurrence cannot be counted twice under different IDs')
        catalog = contract['catalog']
        if catalog is None:
            # Without a caller catalog, overlapping spans ('copper' and 'coppe') are one occurrence and
            # proposed items must be whole tokens. A declared catalog's own witnesses stay authoritative.
            ordered = sorted((row['span'] for row in items), key=lambda row: (row['start'], row['end']))
            if any(left['end'] > right['start'] for left, right in zip(ordered, ordered[1:])):
                _fail('overlap', 'Overlapping spans of one source occurrence cannot count as separate items')
            _whole_token_spans(source['text'], ordered)
        issues = []
        if contract['require_nonempty'] and not items:
            issues.append({'code': 'required_nonempty'})
        required, missing, checked, extra = [], [], [], []
        complete = 'unknown'
        if catalog is not None:
            expected = {row['id']: row['span'] for row in catalog}
            returned = {row['id']: row['span'] for row in items}
            required = sorted(expected)
            checked = sorted(ident for ident, span in returned.items() if expected.get(ident) == span)
            missing = sorted(set(expected) - set(checked))
            extra = sorted(ident for ident, span in returned.items() if expected.get(ident) != span)
            if missing:
                issues.append({'code': 'missing_catalog_items', 'ids': missing})
            if extra:
                issues.append({'code': 'undeclared_or_mismatched_items', 'ids': extra})
            complete = not missing and not extra
        report = _report(source, contract, candidate, accepted=not issues, issues=issues, scope=scope,
                         returned_items_supported=True, enumeration_complete=complete,
                         coverage={'scope': 'declared_finite_catalog' if catalog is not None else 'returned_items_only',
                                   'required': required, 'checked': checked, 'missing': missing,
                                   'extra': extra, 'complete': complete}, items=items)
        if catalog is None:
            report['unknown'].append('enumeration_completeness')
            report['receipt_sha256'] = digest({key: value for key, value in report.items() if key != 'receipt_sha256'})
        return report
    except GroundingError as error:
        report = _refusal(source, contract, candidate, error, scope)
        report.update({'returned_items_supported': False, 'enumeration_complete': False})
        report['receipt_sha256'] = digest({key: value for key, value in report.items() if key != 'receipt_sha256'})
        return report


# Lazy first-party adapter convention used by symblic.kernel.language._adapter. No kernel import
# at module import, and no effects. Charge bounded input work before validation.
def _native(value, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if counter[0] > MAX_NODES:
        _fail('limit', 'Kernel value has too many nodes')
    if depth > MAX_DEPTH:
        _fail('limit', 'Kernel value nesting is too deep')
    if type(value) is Fraction:
        if value.denominator != 1:
            _fail('json', 'Witness coordinates must be integers; source numbers remain text')
        return value.numerator
    if type(value) in (tuple, list):
        if len(value) > MAX_NODES:
            _fail('limit', 'Kernel list is too large')
        return [_native(item, depth + 1, counter) for item in value]
    if type(value) is dict:
        return {key: _native(item, depth + 1, counter) for key, item in value.items()}
    return value


def _out(value):
    if type(value) is list:
        return tuple(_out(item) for item in value)
    if type(value) is dict:
        return {key: _out(item) for key, item in value.items()}
    return value


def _invoke(kernel, node, function, *args, **kwargs):
    from symblic.kernel import language as S
    try:
        kernel.budget.tick(1, node)
        native = [_native(arg) for arg in args]
        native_kwargs = {key: _native(value) for key, value in kwargs.items()}
        work = sum(len(_encoded(arg)) for arg in native) + len(_encoded(native_kwargs))
        kernel.budget.tick(1 + work // 64, node)
        return _out(function(*native, **native_kwargs))
    except GroundingError as error:
        raise S.SymblicError(str(error), kind='budget' if error.code == 'limit' else 'check') from None


def _source_record(kernel, node, ident, text, revision=1):
    return _invoke(kernel, node, source_record, ident, text, revision)


def _source_span(kernel, node, source, start, end):
    return _invoke(kernel, node, source_span, source, start, end)


def _field_contract(kernel, node, ident, source, labels, region, separator, prefix, suffix,
                    max_gap=64, unit='', currency='', entity=None):
    return _invoke(kernel, node, field_contract, ident, source, labels=labels, region=region,
                   separator=separator, prefix=prefix, suffix=suffix, max_gap=max_gap,
                   unit=unit, currency=currency, entity=entity)


def _summary_contract(kernel, node, ident, source, required, joiner='\n…\n', max_spans=64):
    return _invoke(kernel, node, summary_contract, ident, source, required=required,
                   joiner=joiner, max_spans=max_spans)


def _list_contract(kernel, node, ident, source, catalog=None, require_nonempty=False):
    return _invoke(kernel, node, list_contract, ident, source, catalog=catalog, require_nonempty=require_nonempty)


def _proposed_summary(kernel, node, source, text, links):
    return _invoke(kernel, node, proposed_summary, source, text, links)


def _verify_field(kernel, node, source, contract, candidate):
    return _invoke(kernel, node, verify_field, source, contract, candidate)


def _verify_summary(kernel, node, source, contract, candidate):
    return _invoke(kernel, node, verify_summary, source, contract, candidate)


def _verify_items(kernel, node, source, contract, candidate):
    return _invoke(kernel, node, verify_items, source, contract, candidate)


FUNCTIONS = {'source_record': _source_record, 'source_span': _source_span,
             'source_field_contract': _field_contract, 'source_summary_contract': _summary_contract,
             'source_list_contract': _list_contract, 'source_proposed_summary': _proposed_summary,
             'verify_source_field': _verify_field, 'verify_source_summary': _verify_summary,
             'verify_source_items': _verify_items}

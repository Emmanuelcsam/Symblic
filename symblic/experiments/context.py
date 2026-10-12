"""Experiments: source-linked context compression and pinned short hash references.

Research experiment, no result claimed.

Experiments:
    extractive-compression  keep every caller-declared mandatory source span under a byte budget, with a
                            hierarchy and a retrieval comparison; offsets are Unicode code points, costs exact
                            UTF-8 bytes (tokenizer costs are not measured)
    pinned-hash-sidecar     replace repeated SHA-256 values with scoped short ids (@h1, @h2, ...) and verify that
                            the exact text round-trips

Pure functions over caller-supplied text: no files, providers, network, registries or executors. Caller pins
establish scope, not authorship.

Depends on: the standard library only. Run through ``symblic.experiments.registry``.
"""

# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
import hashlib
import json
import re

VERSION = 1
MAX_BYTES = 65536
MAX_ENVELOPE_BYTES = 131072
MAX_RESULT_BYTES = 524288
MAX_SPANS = 64
MAX_NODES = 4096
MAX_DEPTH = 16
JOINER = '\n…\n'
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,47}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_HASH_VALUE = re.compile(r'(?:sha256:)?[0-9a-f]{64}\Z')
_REF = re.compile(r'@h[1-9][0-9]{0,2}\Z')
SOURCES = (
    ('Existing source-witness contracts', 'docs/reference/SOURCE-WITNESSES.md'),
    ('Research transfer and context discipline', 'docs/reference/RESEARCH-TRANSFER.md'),
)
LIMITS = (
    'Only caller-declared mandatory spans are guaranteed; semantic completeness is not inferred.',
    'Greedy selection is bounded and deterministic, not claimed globally optimal.',
    'UTF-8 byte counts are exact. Tokenizer costs are unmeasured; no tokenizer is invoked.',
    'Source/card hashes detect changes relative to caller pins; they do not authenticate a source.',
    'No model, file, network, store or execution operation occurs.',
)


def _fail(code):
    raise ValueError(code)


def _obj(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        _fail('fields')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail('integer_bound')
    return value


def _text(value, maximum=MAX_BYTES, *, empty=True):
    if type(value) is not str:
        _fail('text_type')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        _fail('unicode')
    if size > maximum or (not empty and not value):
        _fail('text_bound')
    return value


def _identifier(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail('identifier')
    return value


def _hash(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail('hash')
    return value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, maximum=MAX_ENVELOPE_BYTES):
    count = 0
    size = 0
    active = set()

    def charge(amount):
        nonlocal size
        size += amount
        if size > maximum:
            _fail('byte_bound')

    def visit(item, depth):
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _fail('structure_bound')
        typ = type(item)
        if typ in (list, dict):
            if len(item) > 128 or id(item) in active:
                _fail('structure_bound')
            charge(2 + max(0, len(item) - 1))
            active.add(id(item))
            if typ is dict:
                for key, child in item.items():
                    _text(key, 1024)
                    charge(len(json.dumps(key, ensure_ascii=False).encode('utf-8')) + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        elif typ is str:
            _text(item)
            charge(len(json.dumps(item, ensure_ascii=False).encode('utf-8')))
        elif typ is int:
            if abs(item) > 10**100:
                _fail('integer_bound')
            charge(len(str(item)))
        elif item is None or typ is bool:
            charge(4 if item is None or item is True else 5)
        elif item is not None and typ is not bool:
            _fail('json_type')

    visit(value, 0)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > maximum:
        _fail('byte_bound')
    return raw


def _digest(value):
    return _sha(_canonical(value))


def _pin(value, *, with_content=False):
    fields = 'id revision sha256 content' if with_content else 'id revision sha256'
    _obj(value, fields)
    _identifier(value['id'])
    _integer(value['revision'], 1, 10**9)
    _hash(value['sha256'])
    if with_content and _sha(_canonical(value['content'], MAX_BYTES)) != value['sha256']:
        _fail('content_pin')
    return {key: value[key] for key in ('id', 'revision', 'sha256')}


def _ranges(spans):
    merged = []
    for start, end in sorted((row['start'], row['end']) for row in spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _render(text, ranges):
    return JOINER.join(text[start:end] for start, end in ranges)


def _covered(row, ranges):
    return any(start <= row['start'] and end >= row['end'] for start, end in ranges)


def _summary(text, selected, all_spans, budget):
    ranges = _ranges(selected)
    result = _render(text, ranges)
    raw = result.encode('utf-8')
    covered = [row['id'] for row in all_spans if _covered(row, ranges)]
    missing = [row['id'] for row in all_spans if row['required'] and row['id'] not in covered]
    return {'text': result, 'ranges': ranges, 'bytes': len(raw), 'sha256': _sha(raw),
            'selected_span_ids': [row['id'] for row in selected],
            'covered_span_ids': covered, 'missing_required_ids': missing,
            'required_preserved': not missing, 'fits_budget': len(raw) <= budget}


def _hierarchy(text, ranges, spans, fanout, budget):
    level = [[[start, end]] for start, end in ranges]
    levels = []
    while level:
        rows = []
        for ranges_at_node in level:
            rendered = _render(text, ranges_at_node).encode('utf-8')
            if len(rendered) > budget:
                _fail('merge_budget')
            rows.append({'ranges': ranges_at_node, 'bytes': len(rendered),
                         'sha256': _sha(rendered),
                         'covered_span_ids': [s['id'] for s in spans if _covered(s, ranges_at_node)]})
        levels.append(rows)
        if len(level) == 1:
            break
        level = [[interval for child in level[i:i + fanout] for interval in child]
                 for i in range(0, len(level), fanout)]
    return levels


def _compression(data):
    _obj(data, 'source spans budget_bytes query_terms merge_fanout')
    source = data['source']
    _obj(source, 'id revision sha256 text')
    _identifier(source['id'])
    _integer(source['revision'], 1, 10**9)
    _hash(source['sha256'])
    text = _text(source['text'], empty=False)
    if _sha(text.encode('utf-8')) != source['sha256']:
        _fail('source_pin')
    budget = _integer(data['budget_bytes'], 0, MAX_BYTES)
    fanout = _integer(data['merge_fanout'], 2, 8)
    spans = data['spans']
    if type(spans) is not list or not 1 <= len(spans) <= MAX_SPANS:
        _fail('span_bound')
    ids = set()
    for row in spans:
        _obj(row, 'id start end required priority')
        ident = _identifier(row['id'])
        if ident in ids:
            _fail('duplicate_span')
        ids.add(ident)
        _integer(row['start'], 0, len(text) - 1)
        _integer(row['end'], row['start'] + 1, len(text))
        _integer(row['priority'], 0, 1000)
        if type(row['required']) is not bool:
            _fail('required_type')
    terms = data['query_terms']
    if type(terms) is not list or len(terms) > 16:
        _fail('query_bound')
    terms = [_text(term, 64, empty=False).casefold() for term in terms]
    if len(set(terms)) != len(terms):
        _fail('duplicate_query')
    order = sorted(spans, key=lambda row: (row['start'], row['end'], row['id']))
    required = [row for row in order if row['required']]
    minimum = _summary(text, required, order, budget)
    full = _summary(text, [{'start': 0, 'end': len(text), 'id': 'full'}], order, budget)
    retrieval = []
    ranked = sorted(order, key=lambda row: (
        -sum(term in text[row['start']:row['end']].casefold() for term in terms),
        row['start'], row['id']))
    for row in ranked:
        if not any(term in text[row['start']:row['end']].casefold() for term in terms):
            continue
        if _summary(text, retrieval + [row], order, budget)['fits_budget']:
            retrieval.append(row)
    baseline = _summary(text, retrieval, order, budget)
    results = {'source': {key: source[key] for key in ('id', 'revision', 'sha256')},
               'budget_bytes': budget, 'minimum_required_bytes': minimum['bytes'],
               'comparisons': {'full_source': full, 'simple_keyword_retrieval': baseline},
               'token_cost': {'status': 'unmeasured', 'tokenizer': None},
               'selection': 'mandatory spans, then descending declared priority; stable greedy admission'}
    if not minimum['fits_budget']:
        results.update(status='refused', reason='required_budget', compressed=None, hierarchy=[])
        return results, {'source_pin': True, 'required_fit': False, 'no_partial_output': True}
    selected = list(required)
    for row in sorted((row for row in order if not row['required']),
                      key=lambda row: (-row['priority'], row['start'], row['id'])):
        if _summary(text, selected + [row], order, budget)['fits_budget']:
            selected.append(row)
    compressed = _summary(text, selected, order, budget)
    hierarchy = _hierarchy(text, compressed['ranges'], order, fanout, budget)
    results.update(status='ok', compressed=compressed, hierarchy=hierarchy)
    return results, {'source_pin': True, 'required_fit': True,
                     'required_preserved': compressed['required_preserved'],
                     'within_budget': compressed['fits_budget'],
                     'hierarchy_reconstructs': not hierarchy or hierarchy[-1][0]['sha256'] == compressed['sha256']}


def _walk(value, transform):
    if type(value) is str:
        return transform(value)
    if type(value) is list:
        return [_walk(item, transform) for item in value]
    if type(value) is dict:
        return {key: _walk(child, transform) for key, child in value.items()}
    return value


def _decode(expected, envelope):
    _pin(expected)
    _obj(envelope, 'version card payload sidecar sha256')
    _integer(envelope['version'], VERSION, VERSION)
    actual = _pin(envelope['card'])
    if actual != expected:
        _fail('card_scope')
    _hash(envelope['sha256'])
    body = {key: value for key, value in envelope.items() if key != 'sha256'}
    if _digest(body) != envelope['sha256']:
        _fail('envelope_pin')
    rows = envelope['sidecar']
    if type(rows) is not list or len(rows) > 64:
        _fail('reference_bound')
    lookup = {}
    for row in rows:
        _obj(row, 'id value')
        token = row['id']
        if type(token) is not str or not _REF.fullmatch(token):
            _fail('reference_id')
        if token in lookup:
            _fail('duplicate_reference')
        if type(row['value']) is not str or not _HASH_VALUE.fullmatch(row['value']):
            _fail('reference_value')
        lookup[token] = row['value']
    used = set()

    def expand(value):
        if value.startswith('@@'):
            return value[1:]
        if value.startswith('@'):
            if value not in lookup:
                _fail('reference_missing')
            used.add(value)
            return lookup[value]
        return value

    content = _walk(envelope['payload'], expand)
    if used != set(lookup):
        _fail('unused_reference')
    if _sha(_canonical(content, MAX_BYTES)) != expected['sha256']:
        _fail('content_pin')
    return content


def _sidecar(data):
    if type(data) is not dict or data.get('operation') not in ('encode', 'decode'):
        _fail('operation')
    if data['operation'] == 'decode':
        _obj(data, 'operation expected envelope')
        content = _decode(data['expected'], data['envelope'])
        return {'status': 'ok', 'content': content,
                'content_sha256': _digest(content)}, {'caller_scope': True, 'content_pin': True}
    _obj(data, 'operation card')
    pin = _pin(data['card'], with_content=True)
    content = data['card']['content']
    counts = {}

    def count(value):
        if _HASH_VALUE.fullmatch(value):
            counts[value] = counts.get(value, 0) + 1
        return value

    _walk(content, count)
    hashes = sorted(value for value, count in counts.items() if count > 1)
    if len(hashes) > 64:
        _fail('reference_bound')
    lookup = {value: '@h' + str(i + 1) for i, value in enumerate(hashes)}

    def shrink(value):
        return lookup.get(value, '@' + value if value.startswith('@') else value)

    payload = _walk(content, shrink)
    sidecar = [{'id': lookup[value], 'value': value} for value in hashes]
    body = {'version': VERSION, 'card': pin, 'payload': payload, 'sidecar': sidecar}
    envelope = {**body, 'sha256': _digest(body)}
    decoded = _decode(pin, envelope)
    raw = _canonical(content, MAX_BYTES)
    payload_bytes = len(_canonical(payload))
    results = {'status': 'ok', 'envelope': envelope,
               'bytes': {'original_content': len(raw), 'model_payload': payload_bytes,
                         'sidecar': len(_canonical(sidecar)),
                         'total_envelope': len(_canonical(envelope)),
                         'payload_saved': len(raw) - payload_bytes},
               'token_cost': {'status': 'unmeasured', 'tokenizer': None},
               'reference_count': len(sidecar),
               'scope': 'Only repeated full hash string values are replaced; dictionary keys remain literal.'}
    return results, {'caller_scope': True, 'content_pin': True,
                     'round_trip_exact': _canonical(decoded) == raw,
                     'total_transport_measured': True}


def run(experiment_id, data):
    _canonical(data)
    if experiment_id == 'extractive-compression':
        results, checks = _compression(data)
    elif experiment_id == 'pinned-hash-sidecar':
        results, checks = _sidecar(data)
    else:
        _fail('experiment_id')
    answer = {'arithmetic': 'exact integer intervals, UTF-8 bytes and canonical JSON hashes',
              'results': results, 'checks': checks, 'limits': list(LIMITS),
              'sources': [{'title': title, 'path': path} for title, path in SOURCES]}
    _canonical(answer, MAX_RESULT_BYTES)
    return answer


def catalog():
    text = 'Invoice total is 40 USD.\nDo not pay until inspection passes.\nThe office wall is blue.'
    lines = text.splitlines()
    spans = []
    offset = 0
    for i, line in enumerate(lines):
        spans.append({'id': 'span' + str(i + 1), 'start': offset, 'end': offset + len(line),
                      'required': i < 2, 'priority': 10 - i})
        offset += len(line) + 1
    source = {'id': 'invoice', 'revision': 1, 'sha256': _sha(text.encode('utf-8')), 'text': text}
    repeated = _sha(b'public synthetic dependency')
    content = {'claim': repeated, 'dependencies': [repeated, repeated], 'literal': '@h1',
               'value': 'Inspection is still required.'}
    examples = [
        ('extractive-compression', 'Source-linked context compression',
         'Preserve declared required source spans under a byte budget, with hierarchy and retrieval comparison.',
         {'source': source, 'spans': spans, 'budget_bytes': 64,
          'query_terms': ['invoice'], 'merge_fanout': 2}),
        ('pinned-hash-sidecar', 'Pinned short hash references',
         'Replace repeated hash values with scoped short IDs and verify exact round-trip reconstruction.',
         {'operation': 'encode', 'card': {'id': 'work-card', 'revision': 1,
                                        'sha256': _digest(content), 'content': content}}),
    ]
    return [{'id': ident, 'title': title, 'summary': summary, 'example': example,
             'sources': [{'title': title, 'path': path} for title, path in SOURCES],
             'limits': list(LIMITS)} for ident, title, summary, example in examples]

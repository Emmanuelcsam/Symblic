"""Provenance-pinned distillation datasets, frozen splits, training/evaluation plans and honest comparison.

What it is for
    The pure core of the distillation pipeline (README.md in this package). It turns accepted-answer records
    (from export.py) into a dataset, freezes leakage-aware train/validation/test splits, freezes training and
    evaluation plans, checks model outputs against the declared answer type, and compares baseline and trained
    outcomes with exact paired statistics (McNemar's exact test, Wilson intervals).

This module is stdlib-only and inert on import. Every dataset, split and plan function is pure: it reads
only what the caller passes and returns detached JSON values. It never scans a store, reads credentials,
calls a model, imports torch/transformers/peft or starts a process. File helpers at the end read and write
exactly the paths a caller names, through bounded strict JSON and atomic, fsynced writes.

What an accepted record proves: a model produced this typed answer to this exact prompt, and the named
native checks (encoded predicates) passed under the recorded kernel and checker. It does NOT prove that the
answer is true, that the predicates capture the author's intent, that the item is novel to any model, or
that training on it improves anything. See docs/reference/DISTILLATION.md.

Used by: symblic/distill/cli.py (command line) and symblic/distill/worker.py (job runner).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import unicodedata
from decimal import Decimal, localcontext
from fractions import Fraction

VERSION = 1
METHOD = 'symblic-accepted-ask-distillation'
MAX_BYTES = 8_000_000            # one JSON input file
MAX_NODES = 400_000
MAX_DEPTH = 32
MAX_TEXT = 16_384                # one prompt/answer/label string
MAX_INT = 10 ** 12
MAX_RECORDS = 5_000
MAX_CHECKS = 32
MAX_EXPOSURES = 64
MAX_LABELS = 64
MAX_STEPS = 1_000_000
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_KERNEL = re.compile(r'[0-9a-f]{16}\Z')
_FP = re.compile(r'[0-9a-f]{16}\Z')
_REVISION = re.compile(r'[0-9a-f]{40}\Z')
_LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,199}\Z')
_DECIMAL = re.compile(r'(0|[1-9][0-9]{0,8})(\.[0-9]{1,12})?([eE]-?[0-9]{1,2})?\Z')
_MODULE = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,63}\Z')
_PACKAGE_PINS = {'torch': '2.14.1', 'transformers': '5.18.0', 'peft': '0.21.2', 'safetensors': '0.8.0',
                 'tokenizers': '0.23.2'}
ANSWER_TYPES = ('integer', 'boolean', 'string', 'label')
SPLITS = ('train', 'validation', 'test')

SCOPE = {
    'acceptance': 'encoded_predicates_passed_under_recorded_kernel_and_checker',
    'proves': ['the recorded model produced this typed answer to this exact prompt',
               'every listed native check passed, as recorded by the caller-supplied receipts'],
    'does_not_prove': ['empirical or semantic truth of the answer',
                       'that the predicates express the author intent',
                       'novelty of any item to any model (hash disjointness is not unseen data)',
                       'independence of observations or models',
                       'that training on these items improves a model'],
    'measurement_status': 'host_declared_not_verified',
}

_SECRET_KEYS = re.compile(r'(\A|[_-])(password|passwd|passphrase|secret|token|apikey|api[_-]key|cookie|'
                          r'authori[sz]ation|credentials?|private[_-]key|session[_-]id|bearer|ssh[_-]key)([_-]|\Z)',
                          re.I)
_SECRET_VALUES = re.compile(
    r'(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{16,}|\bsk-ant-[A-Za-z0-9_-]{16,}|\bghp_[A-Za-z0-9]{20,}|'
    r'\bgithub_pat_[A-Za-z0-9_]{20,}|\bxox[abpors]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}|'
    r'\bya29\.[0-9A-Za-z_-]{20,}|\bBearer\s+[A-Za-z0-9._~+/-]{20,}|\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,})')


class DistillError(ValueError):
    """A finite diagnostic code (never caller-controlled text), optionally with a record/item index."""

    def __init__(self, code, index=None):
        super().__init__(code if index is None else f'{code} (index {index})')
        self.code, self.index = code, index


def _fail(code, index=None):
    raise DistillError(code, index)


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------

def canonical(value) -> str:
    """Canonical JSON text: sorted keys, compact, UTF-8, no NaN."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value) -> str:
    """SHA-256 of bounded canonical JSON (sorted keys, compact, UTF-8, no floats)."""
    _scan(value)
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def fingerprint(value) -> str:
    """Symblic canonical-form-3 fingerprint for the supported answer kinds (int, bool, text)."""
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()[:16]


def _scan(value, *, max_nodes=MAX_NODES):
    stack, nodes, active = [(value, 0, False)], 0, set()
    while stack:
        item, depth, end = stack.pop()
        if end:
            active.discard(id(item))
            continue
        nodes += 1
        if nodes > max_nodes or depth > MAX_DEPTH:
            _fail('structure_limit')
        typ = type(item)
        if typ is dict:
            if id(item) in active:
                _fail('cycle')
            active.add(id(item))
            stack.append((item, depth, True))
            for k, v in item.items():
                if type(k) is not str or len(k) > 200:
                    _fail('invalid_key')
                stack.append((v, depth + 1, False))
        elif typ is list:
            if id(item) in active:
                _fail('cycle')
            active.add(id(item))
            stack.append((item, depth, True))
            stack.extend((v, depth + 1, False) for v in item)
        elif typ is str:
            if len(item) > MAX_TEXT * 4:
                _fail('text_limit')
            try:
                item.encode('utf-8')
            except UnicodeEncodeError:
                _fail('invalid_unicode')
        elif typ is int:
            if abs(item) > 10 ** 30:
                _fail('integer_limit')
        elif item is None or typ is bool:
            pass
        else:
            _fail('unsupported_json_value')      # floats, tuples, custom types
    return nodes


def _copy(value):
    return json.loads(canonical(value))


def _fields(value, required, optional=(), code='schema'):
    if type(value) is not dict:
        _fail(code)
    keys = set(value)
    if not set(required) <= keys or keys - set(required) - set(optional):
        _fail(code)
    return value


def _sha(value, code):
    if type(value) is not str or not _SHA.match(value):
        _fail(code)
    return value


def _int(value, lo, hi, code):
    if type(value) is not int or not lo <= value <= hi:
        _fail(code)
    return value


def _text(value, code, limit=MAX_TEXT, empty=False):
    if type(value) is not str or len(value) > limit or (not empty and not value.strip()):
        _fail(code)
    return value


def _decimal(value, code, lo='0', hi='1'):
    """A decimal string (never a float) within [lo, hi]."""
    if type(value) is not str or not _DECIMAL.match(value):
        _fail(code)
    d = Decimal(value)
    if not Decimal(lo) <= d <= Decimal(hi):
        _fail(code)
    return value


# ---------------------------------------------------------------------------
# 1. Dataset from explicit accepted records
# ---------------------------------------------------------------------------

_RECORD_KEYS = ('version', 'run_id', 'source_sha256', 'statement_sha256', 'kernel_id', 'checker', 'model',
                'prompt', 'answer', 'acceptance')
_RECORD_OPTIONAL = ('group_key', 'exposure_hashes', 'request_sha256', 'capsule_sha256', 'sensitivity')


def _secret_scan(value, index):
    stack = [value]
    while stack:
        item = stack.pop()
        if type(item) is dict:
            for k, v in item.items():
                if _SECRET_KEYS.search(k):
                    _fail('secret_like_field', index)
                stack.append(v)
        elif type(item) is list:
            stack.extend(item)
        elif type(item) is str and _SECRET_VALUES.search(item):
            _fail('secret_like_content', index)


def _answer_kind(answer, index):
    _fields(answer, ('type', 'value', 'fingerprint', 'sha256'), ('labels',), 'answer_schema')
    kind, value = answer['type'], answer['value']
    if kind not in ANSWER_TYPES:
        _fail('unsupported_answer_type', index)
    if kind == 'integer' and (type(value) is not int or abs(value) > MAX_INT):
        _fail('answer_type_mismatch', index)
    if kind == 'boolean' and type(value) is not bool:
        _fail('answer_type_mismatch', index)
    if kind in ('string', 'label'):
        _text(value, 'answer_type_mismatch', empty=(kind == 'string'))
    if kind == 'label':
        labels = answer.get('labels')
        if (type(labels) is not list or not 2 <= len(labels) <= MAX_LABELS
                or any(type(x) is not str or not x or len(x) > 200 for x in labels) or len(set(labels)) != len(labels)):
            _fail('answer_labels', index)
        if value not in labels:
            _fail('answer_not_in_labels', index)
    elif 'labels' in answer:
        _fail('answer_schema', index)
    if answer['sha256'] != hashlib.sha256(canonical(value).encode('utf-8')).hexdigest():
        _fail('answer_hash_mismatch', index)
    if type(answer['fingerprint']) is not str or not _FP.match(answer['fingerprint']) \
            or answer['fingerprint'] != fingerprint(value):
        _fail('answer_fingerprint_mismatch', index)
    return kind


def _record(record, index, options):
    _fields(record, _RECORD_KEYS, _RECORD_OPTIONAL, 'record_schema')
    if record['version'] != 1 or type(record['version']) is not int:
        _fail('record_version', index)
    _secret_scan(record, index)
    if record.get('sensitivity', 'shareable') not in ('shareable', 'internal'):
        _fail('private_record', index)
    for key in ('source_sha256', 'statement_sha256'):
        if type(record[key]) is not str or not _SHA.match(record[key]):
            _fail('missing_identity', index)
    for key in ('request_sha256', 'capsule_sha256'):
        if key in record and (type(record[key]) is not str or not _SHA.match(record[key])):
            _fail('missing_identity', index)
    if type(record['kernel_id']) is not str or not _KERNEL.match(record['kernel_id']):
        _fail('missing_identity', index)
    if type(record['run_id']) is not str or not _LABEL.match(record['run_id']):
        _fail('missing_identity', index)
    checker = record['checker']
    if type(checker) is not dict or set(checker) != {'id', 'version', 'sha256'} or type(checker['id']) is not str \
            or not _LABEL.match(checker['id']) or type(checker['version']) is not int or checker['version'] < 1 \
            or type(checker['sha256']) is not str or not _SHA.match(checker['sha256']):
        _fail('missing_identity', index)
    model = record['model']
    if type(model) is not dict or set(model) != {'requested', 'observed', 'identity', 'digest'}:
        _fail('model_identity_schema', index)
    if type(model['requested']) is not str or not _LABEL.match(model['requested']):
        _fail('missing_identity', index)
    if model['identity'] == 'drift':
        _fail('model_identity_drift', index)
    if model['identity'] == 'observed':
        if type(model['observed']) is not str or not _LABEL.match(model['observed']) \
                or type(model['digest']) is not str or not _SHA.match(model['digest']):
            _fail('model_identity_incomplete', index)
    elif model['identity'] == 'unavailable':
        if not options['allow_unavailable_model_identity']:
            _fail('model_identity_unavailable', index)
        if model['digest'] is not None:
            _fail('model_identity_schema', index)
    else:
        _fail('model_identity_schema', index)
    prompt = record['prompt']
    _fields(prompt, ('system', 'user', 'sha256'), (), 'prompt_schema')
    _text(prompt['system'], 'prompt_schema', empty=True)
    _text(prompt['user'], 'prompt_schema')
    if prompt['sha256'] != hashlib.sha256(canonical([prompt['system'], prompt['user']]).encode('utf-8')).hexdigest():
        _fail('prompt_hash_mismatch', index)
    kind = _answer_kind(record['answer'], index)
    acceptance = record['acceptance']
    _fields(acceptance, ('status', 'checks', 'vote', 'determination'), (), 'acceptance_schema')
    if acceptance['status'] != 'accepted':
        _fail('unsupported_outcome', index)
    if acceptance['vote'] not in ('single', 'uncontested'):
        _fail('ambiguous_outcome', index)
    if acceptance['determination'] not in ('typed_answer', 'unique_in_declared_domain', 'author_disabled'):
        _fail('unsupported_outcome', index)
    checks = acceptance['checks']
    if type(checks) is not list or not 1 <= len(checks) <= MAX_CHECKS:
        _fail('acceptance_checks_missing', index)
    seen = set()
    for check in checks:
        _fields(check, ('id', 'predicate_sha256', 'passed', 'scope', 'kernel_id'), ('predicate',), 'check_schema')
        if check['passed'] is not True:
            _fail('check_not_passed', index)
        if check['scope'] != 'encoded_predicate':
            _fail('check_scope', index)
        if check['kernel_id'] != record['kernel_id']:
            _fail('kernel_mismatch', index)
        for key in ('id', 'predicate_sha256'):
            if type(check[key]) is not str or not _SHA.match(check[key]):
                _fail('check_schema', index)
        if 'predicate' in check:
            _text(check['predicate'], 'check_schema', limit=2000)
        if check['id'] in seen:
            _fail('duplicate_check', index)
        seen.add(check['id'])
    exposures = record.get('exposure_hashes', [])
    if type(exposures) is not list or len(exposures) > MAX_EXPOSURES or len(set(map(str, exposures))) != len(exposures) \
            or any(type(x) is not str or not _SHA.match(x) for x in exposures):
        _fail('exposure_schema', index)
    group_key = record.get('group_key')
    if group_key is not None and (type(group_key) is not str or not _LABEL.match(group_key)):
        _fail('group_key', index)
    return kind


def _norm(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    return ' '.join(text.split())


def _skeleton(text):
    return re.sub(r'\d+', '0', _norm(text))


def target_text(kind, value):
    """The training target: the bare answer, exactly as a Symblic applicator replies (JSON object)."""
    return canonical({'answer': value})


def build_dataset(records, *, allow_unavailable_model_identity=False, strict=True):
    """Explicit caller-selected accepted records -> provenance-pinned dataset (never reads a store)."""
    if type(records) is not list or not 1 <= len(records) <= MAX_RECORDS:
        _fail('record_count')
    _scan(records)
    options = {'allow_unavailable_model_identity': bool(allow_unavailable_model_identity)}
    if type(allow_unavailable_model_identity) is not bool or type(strict) is not bool:
        _fail('options')
    items, rejected, by_prompt, by_identity = [], [], {}, {}
    for index, record in enumerate(records):
        try:
            kind = _record(record, index, options)
        except DistillError as exc:
            if exc.index is None:
                exc = DistillError(exc.code, index)
            if strict:
                raise exc from None
            rejected.append({'index': index, 'code': exc.code})
            continue
        prompt, answer = record['prompt'], record['answer']
        item_id = digest({'prompt': prompt['sha256'], 'answer': answer['sha256'], 'source': record['source_sha256'],
                          'statement': record['statement_sha256']})
        if item_id in by_identity:
            code = 'duplicate_identity'
        elif prompt['sha256'] in by_prompt and by_prompt[prompt['sha256']] != answer['sha256']:
            code = 'conflicting_answers'
        else:
            code = None
        if code:
            if strict:
                _fail(code, index)
            rejected.append({'index': index, 'code': code})
            continue
        by_identity[item_id] = index
        by_prompt[prompt['sha256']] = answer['sha256']
        provenance = {'run_id': record['run_id'], 'source_sha256': record['source_sha256'],
                      'statement_sha256': record['statement_sha256'], 'kernel_id': record['kernel_id'],
                      'checker': dict(record['checker']), 'model': dict(record['model']),
                      'record_sha256': digest(record)}
        for key in ('request_sha256', 'capsule_sha256'):
            if key in record:
                provenance[key] = record[key]
        item = {'item_id': item_id, 'prompt': {'system': prompt['system'], 'user': prompt['user'],
                                               'sha256': prompt['sha256']},
                'answer': {'type': kind, 'value': answer['value'], 'sha256': answer['sha256'],
                           'fingerprint': answer['fingerprint']},
                'target': target_text(kind, answer['value']),
                'provenance': provenance,
                'acceptance': _copy(record['acceptance']),
                'grouping': {'source': record['source_sha256'], 'normalized_prompt': digest(_norm(prompt['user'])),
                             'skeleton': digest(_skeleton(prompt['system'] + '\n' + prompt['user'])),
                             'group_key': record.get('group_key')},
                'exposure_hashes': sorted(record.get('exposure_hashes', []))}
        if kind == 'label':
            item['answer']['labels'] = list(answer['labels'])
        items.append(item)
    if not items:
        _fail('empty_dataset')
    items.sort(key=lambda it: it['item_id'])
    body = {'version': VERSION, 'method': METHOD, 'records_sha256': digest(records), 'record_count': len(records),
            'options': options, 'items': items, 'rejected': rejected, 'scope': SCOPE}
    return {**body, 'dataset_sha256': digest(body)}


def verify_dataset(dataset):
    """Recompute every record digest and the dataset digest; returns the dataset."""
    _fields(dataset, ('version', 'method', 'records_sha256', 'record_count', 'options', 'items', 'rejected', 'scope',
                      'dataset_sha256'), (), 'dataset_schema')
    body = {k: v for k, v in dataset.items() if k != 'dataset_sha256'}
    if dataset['version'] != VERSION or dataset['method'] != METHOD or digest(body) != dataset['dataset_sha256']:
        _fail('dataset_changed')
    ids = [it['item_id'] for it in dataset['items']]
    if len(set(ids)) != len(ids) or ids != sorted(ids):
        _fail('dataset_changed')
    return dataset['dataset_sha256']


# ---------------------------------------------------------------------------
# 2. Frozen leakage-aware splits
# ---------------------------------------------------------------------------

def _exposure_list(exposures, items_by_id):
    """Explicitly recorded held-out exposure: items whose content some model/process has already seen."""
    if exposures is None:
        return []
    if type(exposures) is not list or len(exposures) > MAX_RECORDS:
        _fail('exposure_schema')
    out = []
    for row in exposures:
        _fields(row, ('item_id', 'kind', 'evidence_sha256'), (), 'exposure_schema')
        if row['item_id'] not in items_by_id:
            _fail('exposure_unknown_item')
        if row['kind'] not in ('prompt_or_feedback', 'prior_training', 'prior_evaluation', 'published'):
            _fail('exposure_schema')
        _sha(row['evidence_sha256'], 'exposure_schema')
        out.append(dict(row))
    out.sort(key=lambda r: (r['item_id'], r['kind'], r['evidence_sha256']))
    if len({canonical(r) for r in out}) != len(out):
        _fail('exposure_duplicate')
    return out


GROUP_BY_OPTIONAL = ('source', 'digit_skeleton')


def _groups(items, group_by):
    parent = {it['item_id']: it['item_id'] for it in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner = {}
    for it in items:
        keys = [('norm', it['grouping']['normalized_prompt']), ('prompt', it['prompt']['sha256'])]
        if 'source' in group_by:
            keys.append(('source', it['grouping']['source']))
        if 'digit_skeleton' in group_by:
            keys.append(('skel', it['grouping']['skeleton']))
        if it['grouping'].get('group_key'):
            keys.append(('group', it['grouping']['group_key']))
        keys += [('exposure', h) for h in it['exposure_hashes']]
        keys += [('exposure', it['prompt']['sha256'])]
        for key in keys:
            if key in owner:
                a, b = find(owner[key]), find(it['item_id'])
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                owner[key] = it['item_id']
    groups = {}
    for it in items:
        groups.setdefault(find(it['item_id']), []).append(it['item_id'])
    return [sorted(members) for members in groups.values()]


def freeze_splits(dataset, *, seed, ratios=(80, 10, 10), exposures=None, group_by=GROUP_BY_OPTIONAL):
    """Deterministic group-level assignment. Groups join items that share a source program, normalized prompt,
    digit-skeleton, caller group key or declared exposure hash, so related items never straddle splits."""
    verify_dataset(dataset)
    _text(seed, 'seed', limit=200)
    if type(ratios) not in (list, tuple) or len(ratios) != 3 or any(type(r) is not int or not 0 <= r <= 100
                                                                    for r in ratios) \
            or sum(ratios) != 100 or ratios[0] == 0 or ratios[2] == 0:
        _fail('ratios')
    if type(group_by) not in (list, tuple) or len(set(group_by)) != len(group_by) \
            or any(g not in GROUP_BY_OPTIONAL for g in group_by):
        _fail('group_by')
    group_by = sorted(group_by)
    items = dataset['items']
    by_id = {it['item_id']: it for it in items}
    exposed_rows = _exposure_list(exposures, by_id)
    exposed = {r['item_id'] for r in exposed_rows}
    groups = _groups(items, group_by)
    named = [{'group_id': digest(members), 'members': members} for members in groups]
    named.sort(key=lambda g: hashlib.sha256((seed + '\0' + g['group_id']).encode('utf-8')).hexdigest())
    total = len(items)
    want_test = (total * ratios[2]) // 100
    want_val = (total * ratios[1]) // 100
    counts = {'train': 0, 'validation': 0, 'test': 0}
    assignments = {}
    for group in named:
        size = len(group['members'])
        # A group containing an exposed item is never held out: exposure makes it test-ineligible.
        ineligible = any(m in exposed for m in group['members'])
        if not ineligible and counts['test'] + size <= want_test:
            split = 'test'
        elif counts['validation'] + size <= want_val:
            split = 'validation'
        else:
            split = 'train'
        group['split'] = split
        group['test_ineligible'] = ineligible
        counts[split] += size
        for m in group['members']:
            assignments[m] = split
    if counts['test'] == 0:
        _fail('empty_test_split')
    if counts['train'] == 0:
        _fail('empty_train_split')
    named.sort(key=lambda g: g['group_id'])
    split_ids = {s: sorted(i for i, v in assignments.items() if v == s) for s in SPLITS}
    body = {'version': VERSION, 'dataset_sha256': dataset['dataset_sha256'], 'seed': seed, 'ratios': list(ratios),
            'groups': named, 'assignments': dict(sorted(assignments.items())), 'counts': counts,
            'split_sha256': {s: digest(ids) for s, ids in split_ids.items()},
            'exposures': exposed_rows,
            'novelty': 'not_established',
            'group_by': group_by,
            'grouping_always': ['prompt_sha256', 'normalized_prompt', 'caller_group_key', 'declared_exposure_hash']}
    return {**body, 'splits_sha256': digest(body)}


def verify_splits(dataset, splits, *, expected_sha256=None):
    """Recompute from the dataset and the frozen seed/ratios/exposures; refuse any change or overlap."""
    verify_dataset(dataset)
    if type(splits) is not dict or 'splits_sha256' not in splits:
        _fail('splits_schema')
    if expected_sha256 is not None and splits['splits_sha256'] != expected_sha256:
        _fail('splits_pin_mismatch')
    if splits.get('dataset_sha256') != dataset['dataset_sha256']:
        _fail('splits_dataset_mismatch')
    again = freeze_splits(dataset, seed=splits.get('seed'), ratios=splits.get('ratios'),
                          exposures=splits.get('exposures'), group_by=splits.get('group_by'))
    if again != splits:
        _fail('splits_changed')
    return split_ids(splits)


def split_ids(splits):
    """{split name: [item ids]} of frozen splits."""
    out = {s: [] for s in SPLITS}
    for item_id, split in splits['assignments'].items():
        out[split].append(item_id)
    for s in SPLITS:
        out[s].sort()
    if set(out['test']) & (set(out['train']) | set(out['validation'])):
        _fail('split_overlap')
    return out


# ---------------------------------------------------------------------------
# 3. Training plan (SFT/LoRA) and the GRPO status
# ---------------------------------------------------------------------------

_TRAIN_OPTIONS = {'epochs': (1, 100), 'max_steps': (1, MAX_STEPS), 'batch_size': (1, 64), 'grad_accum': (1, 256),
                  'max_seq_len': (32, 8192), 'seed': (0, 2 ** 31 - 1), 'checkpoint_every': (1, MAX_STEPS),
                  'lora_r': (1, 256), 'lora_alpha': (1, 1024)}
_TRAIN_DECIMALS = {'learning_rate': ('0', '1'), 'lora_dropout': ('0', '0.9'), 'weight_decay': ('0', '1')}
DEFAULT_TRAIN_OPTIONS = {'epochs': 1, 'max_steps': 1000, 'batch_size': 1, 'grad_accum': 8, 'max_seq_len': 1024,
                         'seed': 1234, 'checkpoint_every': 50, 'lora_r': 8, 'lora_alpha': 16,
                         'learning_rate': '0.0002', 'lora_dropout': '0.05', 'weight_decay': '0',
                         'target_modules': ['q_proj', 'k_proj', 'v_proj', 'o_proj'],
                         'dtype': 'float32', 'device': 'cpu'}


def _train_options(options):
    merged = dict(DEFAULT_TRAIN_OPTIONS)
    if options is not None:
        if type(options) is not dict or set(options) - set(DEFAULT_TRAIN_OPTIONS):
            _fail('train_options')
        merged.update(options)
    for key, (lo, hi) in _TRAIN_OPTIONS.items():
        _int(merged[key], lo, hi, 'train_options')
    for key, (lo, hi) in _TRAIN_DECIMALS.items():
        _decimal(merged[key], 'train_options', lo, hi)
    if Decimal(merged['learning_rate']) == 0:
        _fail('train_options')
    mods = merged['target_modules']
    if type(mods) is not list or not 1 <= len(mods) <= 32 or len(set(mods)) != len(mods) \
            or any(type(m) is not str or not _MODULE.match(m) for m in mods):
        _fail('train_options')
    if merged['dtype'] not in ('float32', 'bfloat16', 'float16') or merged['device'] != 'cpu':
        _fail('train_options')
    if merged['device'] == 'cpu' and merged['dtype'] == 'float16':
        _fail('train_options')
    return merged


def _model_spec(model):
    """The operator's pinned local snapshot: a directory name under the worker's --models-root, never a URL or hub fetch."""
    _fields(model, ('dir', 'repo_id', 'revision', 'files_sha256'), (), 'model_spec')
    if type(model['dir']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', model['dir']) \
            or model['dir'] in ('.', '..'):
        _fail('model_spec')
    if type(model['repo_id']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}',
                                                             model['repo_id']):
        _fail('model_spec')
    if type(model['revision']) is not str or not _REVISION.match(model['revision']):
        _fail('model_revision')
    _sha(model['files_sha256'], 'model_spec')
    return dict(model)


def grpo_status():
    """Verifiable-reward/GRPO is NOT implemented in this candidate. This is a status, never a trainer."""
    return {'method': 'grpo_verifiable_reward', 'status': 'unsupported',
            'gap': ['a reward function that runs the native Symblic checker (type coercion + encoded predicates) '
                    'in-process on each sampled completion, pinned to the kernel/checker identity, using only the '
                    'training prompt and its own predicates (never held-out answers or reference answers)',
                    'per-prompt group sampling (G completions) with recorded seeds, and recording every sample, '
                    'reward and failure in the checkpointed ledger so resume cannot double-count',
                    'a verified policy-gradient update with a frozen reference model and KL term (TRL GRPOTrainer '
                    'was not verified against the pinned versions here), plus its resume semantics',
                    'measured generation throughput: G samples per prompt per step on CPU-only machines is likely '
                    'impractical beyond tiny models; needs a GPU'],
            'reports_success': False}


def plan_training(dataset, splits, *, model, options=None, method='sft_lora', packages=None):
    """Freeze everything a training run depends on. Test items are excluded by construction and recorded."""
    if method != 'sft_lora':
        _fail('grpo_unsupported' if method == 'grpo' else 'method_unsupported')
    ids = verify_splits(dataset, splits)
    pins = dict(_PACKAGE_PINS)
    if packages is not None:
        if type(packages) is not dict or set(packages) != set(_PACKAGE_PINS) \
                or any(type(v) is not str or not re.fullmatch(r'[0-9][0-9A-Za-z.+-]{0,40}', v) for v in packages.values()):
            _fail('package_pins')
        pins = dict(packages)
    opts = _train_options(options)
    if not ids['train']:
        _fail('empty_train_split')
    body = {'version': VERSION, 'method': 'sft_lora', 'dataset_sha256': dataset['dataset_sha256'],
            'splits_sha256': splits['splits_sha256'], 'train_ids_sha256': digest(ids['train']),
            'validation_ids_sha256': digest(ids['validation']), 'test_ids_sha256': digest(ids['test']),
            'train_count': len(ids['train']), 'validation_count': len(ids['validation']),
            'excluded_test_count': len(ids['test']), 'model': _model_spec(model), 'options': opts,
            'packages': pins, 'promotion': 'never_automatic', 'downloads': 'forbidden_local_files_only',
            'grpo': grpo_status()}
    return {**body, 'plan_sha256': digest(body)}


def verify_plan(plan, *, expected_sha256=None):
    """Check a training plan against its own digest (and an expected one when given)."""
    if type(plan) is not dict or 'plan_sha256' not in plan:
        _fail('plan_schema')
    body = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    if digest(body) != plan['plan_sha256']:
        _fail('plan_changed')
    if expected_sha256 is not None and expected_sha256 != plan['plan_sha256']:
        _fail('plan_pin_mismatch')
    if plan.get('method') != 'sft_lora' or plan.get('version') != VERSION:
        _fail('plan_schema')
    _train_options(plan['options'])
    _model_spec(plan['model'])
    return plan['plan_sha256']


def training_job(dataset, splits, plan):
    """The worker's input: ONLY train/validation items. Test prompts and answers never enter a training job."""
    verify_plan(plan)
    ids = verify_splits(dataset, splits, expected_sha256=plan['splits_sha256'])
    if plan['dataset_sha256'] != dataset['dataset_sha256'] or digest(ids['train']) != plan['train_ids_sha256'] \
            or digest(ids['validation']) != plan['validation_ids_sha256']:
        _fail('plan_dataset_mismatch')
    by_id = {it['item_id']: it for it in dataset['items']}
    test = set(ids['test'])

    def row(item_id):
        if item_id in test:
            _fail('test_reuse_as_training')
        it = by_id[item_id]
        return {'item_id': item_id, 'system': it['prompt']['system'], 'user': it['prompt']['user'],
                'target': it['target']}
    body = {'version': VERSION, 'kind': 'train', 'plan': plan, 'train': [row(i) for i in ids['train']],
            'validation': [row(i) for i in ids['validation']], 'test_ids_sha256': plan['test_ids_sha256']}
    return {**body, 'job_sha256': digest(body)}


# ---------------------------------------------------------------------------
# 5. Frozen baseline-vs-trained evaluation and pure comparison
# ---------------------------------------------------------------------------

ARMS = ('baseline', 'trained')
OUTCOMES = ('passed', 'failed', 'error', 'unavailable', 'interrupted')


CHECKERS = ('schema', 'schema_and_reference', 'schema_and_native')
CHECKER_SCOPES = {
    'schema': 'structural_answer_schema',
    'schema_and_reference': 'structural_answer_schema_and_reference_hash_agreement',
    'schema_and_native': 'structural_answer_schema_and_native_encoded_predicates',
}


def native_checker_pin(pin):
    """The frozen identity of a trusted, operator-registered native checker (see the worker's checker interface).
    `module_sha256` pins the exact checker module source; `identity` is what the checker reports for itself."""
    _fields(pin, ('name', 'module_sha256', 'identity'), (), 'native_checker_pin')
    if type(pin['name']) is not str or not _LABEL.match(pin['name']):
        _fail('native_checker_pin')
    _sha(pin['module_sha256'], 'native_checker_pin')
    ident = pin['identity']
    _fields(ident, ('id', 'version', 'kernel_id', 'contract_version', 'source_sha256'), (), 'native_checker_pin')
    if type(ident['id']) is not str or not _LABEL.match(ident['id']) or type(ident['version']) is not int \
            or type(ident['contract_version']) is not int or type(ident['kernel_id']) is not str \
            or not _KERNEL.match(ident['kernel_id']):
        _fail('native_checker_pin')
    _sha(ident['source_sha256'], 'native_checker_pin')
    return _copy(pin)


def native_contract(item):
    """What a native checker needs to re-check a generated answer for one item: the original program/statement and
    its accepted predicate identities. It never contains the accepted answer."""
    out = {'source_sha256': item['provenance']['source_sha256'],
           'statement_sha256': item['provenance']['statement_sha256'],
           'kernel_id': item['provenance']['kernel_id'], 'checker': dict(item['provenance']['checker']),
           'predicate_sha256s': [c['predicate_sha256'] for c in item['acceptance']['checks']],
           'answer_type': item['answer']['type']}
    if item['answer']['type'] == 'label':
        out['labels'] = list(item['answer']['labels'])
    return out


def plan_evaluation(dataset, splits, plan, *, max_new_tokens=256, prior_test_uses=0, checker='schema',
                    native_checker=None):
    """Both arms get exactly the same held-out items, prompts, decoding and budgets. Greedy decoding only.
    `schema_and_reference` = equality with the stored accepted answer (agreement, not verification);
    `schema_and_native` = a pinned trusted native checker re-runs the item's predicates on the generated answer."""
    verify_plan(plan)
    ids = verify_splits(dataset, splits, expected_sha256=plan['splits_sha256'])
    _int(max_new_tokens, 1, 4096, 'eval_budget')
    _int(prior_test_uses, 0, 10_000, 'eval_prior_uses')
    if checker not in CHECKERS:
        _fail('eval_checker')
    if (checker == 'schema_and_native') != (native_checker is not None):
        _fail('eval_checker')
    pin = native_checker_pin(native_checker) if native_checker is not None else None
    by_id = {it['item_id']: it for it in dataset['items']}
    items = []
    for item_id in ids['test']:
        it = by_id[item_id]
        row = {'item_id': item_id, 'system': it['prompt']['system'], 'user': it['prompt']['user'],
               'answer_type': it['answer']['type']}
        if it['answer']['type'] == 'label':
            row['labels'] = list(it['answer']['labels'])
        if checker == 'schema_and_reference':
            row['reference_sha256'] = it['answer']['sha256']
        if checker == 'schema_and_native':
            row['contract'] = native_contract(it)
        items.append(row)
    checker_row = {'id': checker, 'version': VERSION, 'scope': CHECKER_SCOPES[checker]}
    if pin is not None:
        checker_row['native'] = pin
    body = {'version': VERSION, 'plan_sha256': plan['plan_sha256'], 'splits_sha256': splits['splits_sha256'],
            'test_ids_sha256': plan['test_ids_sha256'], 'arms': list(ARMS), 'items': items,
            'budget': {'max_new_tokens': max_new_tokens, 'decoding': 'greedy', 'attempts_per_item': 1},
            'checker': checker_row,
            'heldout_status': 'fresh' if prior_test_uses == 0 else 'reused',
            'prior_test_uses': prior_test_uses, 'novelty': 'not_established'}
    return {**body, 'eval_sha256': digest(body)}


def verify_eval_plan(eval_plan, *, expected_sha256=None):
    """Check an evaluation plan against its own digest (and an expected one when given)."""
    if type(eval_plan) is not dict or 'eval_sha256' not in eval_plan:
        _fail('eval_schema')
    body = {k: v for k, v in eval_plan.items() if k != 'eval_sha256'}
    if digest(body) != eval_plan['eval_sha256']:
        _fail('eval_changed')
    if expected_sha256 is not None and expected_sha256 != eval_plan['eval_sha256']:
        _fail('eval_pin_mismatch')
    return eval_plan['eval_sha256']


_JSON_OBJECT = re.compile(r'\{.*\}', re.S)


def check_output(item, text):
    """Structural check of one generated reply: a single JSON object {"answer": v} whose v has the declared type.
    Returns scoped evidence. Passing means 'well-formed and typed', never 'true'."""
    if type(text) is not str or len(text) > 64_000:
        return {'schema_valid': False, 'reason': 'not_text', 'answer_sha256': None}
    stripped = text.strip()
    try:
        value = json.loads(stripped, parse_float=lambda s: _fail('float_answer'),
                           parse_constant=lambda s: _fail('float_answer'))
    except (ValueError, DistillError):
        return {'schema_valid': False, 'reason': 'not_json_object', 'answer_sha256': None}
    if type(value) is not dict or set(value) != {'answer'}:
        return {'schema_valid': False, 'reason': 'not_answer_object', 'answer_sha256': None}
    answer = value['answer']
    kind = item['answer_type']
    ok = ((kind == 'integer' and type(answer) is int and abs(answer) <= MAX_INT)
          or (kind == 'boolean' and type(answer) is bool)
          or (kind == 'string' and type(answer) is str and len(answer) <= MAX_TEXT)
          or (kind == 'label' and type(answer) is str and answer in item.get('labels', ())))
    if not ok:
        return {'schema_valid': False, 'reason': 'wrong_answer_type', 'answer_sha256': None}
    return {'schema_valid': True, 'reason': None,
            'answer_sha256': hashlib.sha256(canonical(answer).encode('utf-8')).hexdigest(), '_value': answer}


def score_outcome(item, check):
    """passed/failed under the schema or reference checker. Reference agreement is hash equality with the recorded
    accepted answer: an agreement metric (that answer was itself only predicate-checked), never native verification.
    Native verification is scored by the worker from a pinned checker's receipt, never here."""
    if 'contract' in item:
        _fail('native_checker_required')
    if not check['schema_valid']:
        return 'failed'
    if 'reference_sha256' in item:
        check['reference_match'] = check['answer_sha256'] == item['reference_sha256']
        if not check['reference_match']:
            return 'failed'
    return 'passed'


def _wilson(k, n):
    """95% Wilson score interval as 6-decimal strings (z = 1.96). n = planned items, never successes-only."""
    if n == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        z = Decimal('1.96')
        p = Decimal(k) / Decimal(n)
        n_ = Decimal(n)
        denom = 1 + z * z / n_
        centre = (p + z * z / (2 * n_)) / denom
        half = z * ((p * (1 - p) / n_ + z * z / (4 * n_ * n_)).sqrt()) / denom
        q = Decimal('0.000001')
        lo, hi = max(Decimal(0), centre - half), min(Decimal(1), centre + half)
        return [str(lo.quantize(q)), str(hi.quantize(q))]


def _mcnemar_exact(b, c):
    """Exact two-sided binomial p-value on discordant pairs (b, c), as a Fraction rendered p/q."""
    n = b + c
    if n == 0:
        return {'#q': '1/1'}
    k = min(b, c)
    tail = sum(Fraction(_choose(n, i), 2 ** n) for i in range(k + 1))
    p = min(Fraction(1), 2 * tail)
    return {'#q': f'{p.numerator}/{p.denominator}'}


def _choose(n, k):
    out = 1
    for i in range(1, k + 1):
        out = out * (n - k + i) // i
    return out


def compare(eval_plan, outcomes):
    """Pure comparison. `outcomes` = list of {arm, item_id, status, attempts, output_sha256, check}. Every planned
    (arm, item) is in the denominator; missing rows count as missing (not passed). No row may be repeated."""
    verify_eval_plan(eval_plan)
    if type(outcomes) is not list or len(outcomes) > 2 * MAX_RECORDS:
        _fail('outcomes_schema')
    _scan(outcomes)
    planned = [it['item_id'] for it in eval_plan['items']]
    planned_set = set(planned)
    rows = {}
    for row in outcomes:
        _fields(row, ('arm', 'item_id', 'status', 'attempts', 'output_sha256', 'check'), (), 'outcomes_schema')
        if row['arm'] not in ARMS or row['status'] not in OUTCOMES:
            _fail('outcomes_schema')
        if row['item_id'] not in planned_set:
            _fail('outcome_unplanned_item')
        _int(row['attempts'], 0, 64, 'outcomes_schema')
        key = (row['arm'], row['item_id'])
        if key in rows:
            _fail('outcome_duplicate')
        rows[key] = row
    n = len(planned)
    summary = {}
    for arm in ARMS:
        counts = {s: 0 for s in OUTCOMES}
        counts['missing'] = 0
        for item_id in planned:
            row = rows.get((arm, item_id))
            counts['missing' if row is None else row['status']] += 1
        summary[arm] = {'planned': n, 'counts': counts, 'passed': counts['passed'],
                        'pass_rate': {'#q': f'{Fraction(counts["passed"], n).numerator}/'
                                            f'{Fraction(counts["passed"], n).denominator}'},
                        'wilson95': _wilson(counts['passed'], n)}
    b = c = 0
    for item_id in planned:
        base = rows.get(('baseline', item_id))
        trained = rows.get(('trained', item_id))
        bp = base is not None and base['status'] == 'passed'
        tp = trained is not None and trained['status'] == 'passed'
        b += bp and not tp
        c += tp and not bp
    complete = all(summary[a]['counts']['missing'] == 0 and summary[a]['counts']['unavailable'] == 0
                   and summary[a]['counts']['interrupted'] == 0 for a in ARMS)
    body = {'version': VERSION, 'eval_sha256': eval_plan['eval_sha256'], 'plan_sha256': eval_plan['plan_sha256'],
            'outcomes_sha256': digest(outcomes), 'arms': summary,
            'paired': {'baseline_only_passed': b, 'trained_only_passed': c, 'mcnemar_exact_p': _mcnemar_exact(b, c)},
            'complete': complete,
            'comparison': ('difference_observed_under_declared_checker' if complete and b != c
                           else 'no_difference_observed' if complete else 'not_established'),
            'checker_scope': eval_plan['checker']['scope'], 'heldout_status': eval_plan['heldout_status'],
            'prior_test_uses': eval_plan['prior_test_uses'],
            'limits': ['structural acceptance is not semantic truth',
                       'one greedy sample per item; not a distribution over decoding',
                       'the p-value is descriptive for this frozen item set only; no generalization or causal claim',
                       'novelty of test items to the base model is not established']}
    return {**body, 'comparison_sha256': digest(body)}


# ---------------------------------------------------------------------------
# Bounded files: strict JSON reads, atomic fsynced writes, safe paths
# ---------------------------------------------------------------------------

def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            _fail('duplicate_json_key')
        out[k] = v
    return out


def _no_float(text):
    _fail('float_in_json')


def loads(raw: bytes):
    """Strict bounded JSON from bytes: no duplicate keys, no floats."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        _fail('input_too_large')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        _fail('invalid_utf8')
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_float=_no_float, parse_constant=_no_float)
    except DistillError:
        raise
    except (ValueError, RecursionError):
        _fail('invalid_json')
    _scan(value)
    return value


def read_json(path):
    """Read one regular, non-symlink file of bounded size."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        _fail('symlink_refused' if exc.errno == errno.ELOOP else 'unreadable_input')
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            _fail('not_regular_file')
        if st.st_size > MAX_BYTES:
            _fail('input_too_large')
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                _fail('input_too_large')
            chunks.append(chunk)
    finally:
        os.close(fd)
    return loads(b''.join(chunks))


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_atomic(path, data: bytes, *, exclusive=False):
    """Write a new file atomically: temp file in the same directory, fsync, rename (or link for exclusive), fsync dir.
    `exclusive` refuses to replace an existing file (history is never overwritten)."""
    folder = os.path.dirname(os.path.abspath(path))
    st = os.lstat(folder)
    if not stat.S_ISDIR(st.st_mode):
        _fail('unsafe_directory')
    if os.path.lexists(path):
        if exclusive:
            _fail('output_exists')
        if not stat.S_ISREG(os.lstat(path).st_mode):
            _fail('unsafe_output')
    tmp = os.path.join(folder, f'.{os.path.basename(path)}.{os.getpid()}.{os.urandom(6).hex()}.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        if exclusive:
            os.link(tmp, path)          # fails if `path` appeared meanwhile
            os.unlink(tmp)
        else:
            os.replace(tmp, path)
    except FileExistsError:
        os.unlink(tmp)
        _fail('output_exists')
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise
    _fsync_dir(folder)


def write_json(path, value, *, exclusive=False):
    """Atomic, fsynced JSON write; exclusive=True refuses an existing file."""
    _scan(value)
    write_atomic(path, (canonical(value) + '\n').encode('utf-8'), exclusive=exclusive)


def safe_child(root, name):
    """root/name where name is one plain component and nothing on the path is a symlink."""
    if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name) or name in ('.', '..'):
        _fail('unsafe_path')
    root = os.path.abspath(root)
    real = os.path.realpath(root)
    if real != root:
        _fail('symlink_refused')
    path = os.path.join(root, name)
    if os.path.lexists(path) and os.path.islink(path):
        _fail('symlink_refused')
    return path

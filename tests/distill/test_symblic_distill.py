"""symblic.distill.datasets / symblic.distill.worker / python3 -m symblic.distill.cli.

Stdlib unittest only: temporary stores, fake training/generation backends, no model, package download,
network, account or system worker. The real TorchLoraBackend is exercised only on its refusal paths.
Run: DASH_TEST=1 python3 -B -m unittest tests.distill.test_symblic_distill -v
"""
import builtins
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]      # the repository root
sys.path.insert(0, str(ROOT))

from symblic.distill import datasets as D  # noqa: E402
from symblic.distill import worker as W  # noqa: E402

KERNEL = '59c87dc8a638abce'
REVISION = '7ae557604adf67be50417f59c2c2f167def9a775'


def H(value):
    return hashlib.sha256(D.canonical(value).encode('utf-8')).hexdigest()


def _word(i):
    letters = 'abcdefghijklmnopqrstuvwxyz'
    return 'item ' + letters[i % 26] + letters[(i // 26) % 26] + letters[(i // 676) % 26]


def record(i, *, source=None, user=None, value=None, kind='integer', labels=None, **changes):
    system = 'You carry out exactly one statement.'
    user = user if user is not None else f'Name the frozen colour assigned to {_word(i)}.'
    value = (i * 3 + 1) if value is None else value
    rec = {'version': 1, 'run_id': f'run-{i}', 'source_sha256': H(['source', source if source is not None else i]),
           'statement_sha256': H(['statement', i]), 'kernel_id': KERNEL,
           'checker': {'id': 'symblic-native', 'version': 1, 'sha256': H('checker')},
           'model': {'requested': 'ollama:qwen3:4b@node-a', 'observed': 'qwen3:4b', 'identity': 'observed',
                     'digest': H('model')},
           'prompt': {'system': system, 'user': user, 'sha256': H([system, user])},
           'answer': {'type': kind, 'value': value, 'sha256': H(value), 'fingerprint': H(value)[:16]},
           'acceptance': {'status': 'accepted', 'vote': 'single', 'determination': 'typed_answer',
                          'checks': [{'id': H(['check', i]), 'predicate_sha256': H(['pred', i]), 'passed': True,
                                      'scope': 'encoded_predicate', 'kernel_id': KERNEL,
                                      'predicate': 'answer >= 0'}]}}
    if labels is not None:
        rec['answer']['labels'] = labels
    for key, val in changes.items():
        rec[key] = val
    return rec


def records(n=30):
    return [record(i) for i in range(n)]


def dataset(n=30, **kw):
    return D.build_dataset(records(n), **kw)


class Fake:
    """Deterministic fake training/generation backend. Records every call; never imports torch."""

    def __init__(self, name='fake', crash_at=None, answers=None, unavailable_arms=(), fail_items=()):
        self.name, self.crash_at, self.answers = name, crash_at, answers or {}
        self.unavailable_arms, self.fail_items = unavailable_arms, fail_items
        self.calls, self.batches, self.generated, self.closed = [], [], [], 0
        self.step = 0
        self.adapter = None

    def identity(self):
        return {'name': self.name, 'version': 1, 'packages': {'fake': '1'}}

    def preflight(self, plan):
        self.calls.append(('preflight', plan['plan_sha256']))

    def begin(self, model_dir, plan, *, resume_dir, adapter_dir, trainable):
        arm = 'trained' if adapter_dir else 'baseline'
        if not trainable and arm in self.unavailable_arms:
            raise W.BackendUnavailable('model_load_failed')
        self.calls.append(('begin', os.path.basename(model_dir), resume_dir and os.path.basename(resume_dir),
                           adapter_dir and os.path.basename(adapter_dir), trainable))
        self.adapter = adapter_dir
        self.step = 0
        if resume_dir:
            self.step = json.loads(Path(resume_dir, 'adapter_model.safetensors').read_text())['step']

    def train_step(self, batches):
        if self.crash_at is not None and self.step + 1 == self.crash_at:
            raise KeyboardInterrupt('simulated power loss')
        self.step += 1
        self.batches.append([[r['item_id'] for r in mb] for mb in batches])
        return f'{2 - self.step / 1000:.6f}'

    def eval_loss(self, rows):
        return '1.250000'

    def save(self, folder):
        Path(folder, 'adapter_model.safetensors').write_text(json.dumps({'step': self.step}))
        Path(folder, 'adapter_config.json').write_text('{"r": 8}')

    def generate(self, row, max_new_tokens):
        arm = 'trained' if self.adapter else 'baseline'
        self.generated.append((arm, row, max_new_tokens))
        if (arm, row['user']) in self.fail_items:
            raise RuntimeError('fake generation failure')
        return self.answers.get((arm, row['user']), '{"answer": 1}')

    def close(self):
        self.closed += 1


class Env:
    """A temporary models root with a fake safetensors snapshot, and a jobs root."""

    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.models = self.root / 'models'
        self.jobs = self.root / 'jobs'
        (self.models / 'qwen').mkdir(parents=True)
        self.jobs.mkdir()
        for name, data in (('config.json', '{"model_type": "qwen2"}'), ('model.safetensors', 'weights'),
                           ('tokenizer.json', '{}'), ('tokenizer_config.json', '{}')):
            (self.models / 'qwen' / name).write_text(data)
        self.manifest = W.model_manifest(str(self.models / 'qwen'))

    def spec(self):
        return {'dir': 'qwen', 'repo_id': 'Qwen/Qwen2.5-0.5B-Instruct', 'revision': REVISION,
                'files_sha256': self.manifest['files_sha256']}


def frozen(env, n=30, options=None, group_by=('source', 'digit_skeleton'), exposures=None):
    ds = dataset(n)
    sp = D.freeze_splits(ds, seed='seed-1', ratios=(60, 20, 20), group_by=group_by, exposures=exposures)
    opts = {'max_steps': 4, 'grad_accum': 2, 'checkpoint_every': 2}
    opts.update(options or {})
    plan = D.plan_training(ds, sp, model=env.spec(), options=opts)
    return ds, sp, plan


# ---------------------------------------------------------------------------
# 1. Dataset
# ---------------------------------------------------------------------------

class Dataset(unittest.TestCase):
    def test_build_pins_provenance_and_is_deterministic(self):
        recs = records(5)
        a, b = D.build_dataset(recs), D.build_dataset(copy.deepcopy(recs))
        self.assertEqual(a, b)
        self.assertEqual(a['dataset_sha256'], D.verify_dataset(a))
        self.assertEqual(5, len(a['items']))
        self.assertEqual([it['item_id'] for it in a['items']], sorted(it['item_id'] for it in a['items']))
        item = a['items'][0]
        for key in ('source_sha256', 'statement_sha256', 'kernel_id', 'checker', 'model', 'record_sha256', 'run_id'):
            self.assertIn(key, item['provenance'])
        self.assertEqual(1, len(item['acceptance']['checks']))
        self.assertEqual(D.canonical({'answer': item['answer']['value']}), item['target'])
        self.assertIn('empirical or semantic truth of the answer', a['scope']['does_not_prove'])
        recs[0]['answer']['value'] += 0                      # inputs are not retained by reference
        a['items'][0]['target'] = 'tampered'
        with self.assertRaises(D.DistillError) as ctx:
            D.verify_dataset(a)
        self.assertEqual('dataset_changed', ctx.exception.code)

    def test_fingerprint_matches_symblic_canonical_form(self):
        # symblic.fingerprint = sha256(json.dumps(canon(v), sort_keys, (',', ':'), ensure_ascii=False))[:16]
        for value in (6, -3, True, 'naïve "x"', 'label-a'):
            expect = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                               ensure_ascii=False).encode()).hexdigest()[:16]
            self.assertEqual(expect, D.fingerprint(value))

    def refused(self, rec, code, **kw):
        with self.assertRaises(D.DistillError) as ctx:
            D.build_dataset([rec], **kw)
        self.assertEqual(code, ctx.exception.code, rec)
        self.assertEqual(0, ctx.exception.index)

    def test_identity_and_hash_rejections(self):
        self.refused(record(1, kernel_id='nothex'), 'missing_identity')
        self.refused(record(1, source_sha256='0' * 63), 'missing_identity')
        r = record(1); r['checker'] = {'id': 'x', 'version': 1}
        self.refused(r, 'missing_identity')
        r = record(1); r['prompt']['user'] += ' changed'
        self.refused(r, 'prompt_hash_mismatch')
        r = record(1); r['answer']['value'] = 99
        self.refused(r, 'answer_hash_mismatch')
        r = record(1); r['answer']['fingerprint'] = '0' * 16
        self.refused(r, 'answer_fingerprint_mismatch')
        r = record(1); r['model']['identity'] = 'drift'
        self.refused(r, 'model_identity_drift')
        r = record(1); r['model'].update(identity='observed', digest=None)
        self.refused(r, 'model_identity_incomplete')

    def test_unavailable_model_identity_only_by_recorded_choice(self):
        r = record(1); r['model'].update(identity='unavailable', observed='', digest=None)
        self.refused(r, 'model_identity_unavailable')
        ds = D.build_dataset([r], allow_unavailable_model_identity=True)
        self.assertTrue(ds['options']['allow_unavailable_model_identity'])

    def test_outcome_rejections(self):
        r = record(1); r['acceptance']['status'] = 'rejected'
        self.refused(r, 'unsupported_outcome')
        r = record(1); r['acceptance']['vote'] = 'contested'
        self.refused(r, 'ambiguous_outcome')
        r = record(1); r['acceptance']['determination'] = 'underdetermined'
        self.refused(r, 'unsupported_outcome')
        r = record(1); r['acceptance']['checks'] = []
        self.refused(r, 'acceptance_checks_missing')
        r = record(1); r['acceptance']['checks'][0]['passed'] = False
        self.refused(r, 'check_not_passed')
        r = record(1); r['acceptance']['checks'][0]['passed'] = 1
        self.refused(r, 'check_not_passed')
        r = record(1); r['acceptance']['checks'][0]['kernel_id'] = 'f' * 16
        self.refused(r, 'kernel_mismatch')
        r = record(1); r['acceptance']['checks'][0]['scope'] = 'model_said_so'
        self.refused(r, 'check_scope')

    def test_answer_type_rejections(self):
        self.refused(record(1, kind='number', value=3), 'unsupported_answer_type')
        self.refused(record(1, kind='integer', value=True), 'answer_type_mismatch')
        self.refused(record(1, kind='boolean', value=1), 'answer_type_mismatch')
        self.refused(record(1, kind='label', value='c', labels=['a', 'b']), 'answer_not_in_labels')
        self.refused(record(1, kind='label', value='a', labels=['a']), 'answer_labels')
        ok = D.build_dataset([record(1, kind='label', value='a', labels=['a', 'b']),
                              record(2, kind='boolean', value=False)])
        self.assertEqual({'label', 'boolean'}, {it['answer']['type'] for it in ok['items']})
        with self.assertRaises(D.DistillError) as ctx:
            D.build_dataset([record(1, kind='integer', value=1.5)])
        self.assertEqual('unsupported_json_value', ctx.exception.code)

    def test_secret_private_and_unknown_fields(self):
        self.refused(record(1, user='use key sk-ant-' + 'a' * 30 + ' please'), 'secret_like_content')
        self.refused(record(1, user='-----BEGIN RSA PRIVATE KEY----- x'), 'secret_like_content')
        self.refused(record(1, user='header Bearer ' + 'x' * 30), 'secret_like_content')
        self.refused(record(1, sensitivity='private'), 'private_record')
        self.refused(record(1, api_token='x'), 'record_schema')
        r = record(1); r['acceptance']['checks'][0]['session_id'] = 'x'
        self.refused(r, 'secret_like_field')
        D.build_dataset([record(1, user='The password field must be validated; passed checks are kept.')])

    def test_duplicates_and_conflicts_and_lenient_listing(self):
        with self.assertRaises(D.DistillError) as ctx:
            D.build_dataset([record(1), record(1)])
        self.assertEqual(('duplicate_identity', 1), (ctx.exception.code, ctx.exception.index))
        conflict = record(1, value=999)
        conflict['statement_sha256'] = H('other statement')
        with self.assertRaises(D.DistillError) as ctx:
            D.build_dataset([record(1), conflict])
        self.assertEqual('conflicting_answers', ctx.exception.code)
        bad = record(2); bad['acceptance']['vote'] = 'contested'
        ds = D.build_dataset([record(1), bad, record(1)], strict=False)
        self.assertEqual([{'index': 1, 'code': 'ambiguous_outcome'}, {'index': 2, 'code': 'duplicate_identity'}],
                         ds['rejected'])
        self.assertEqual(1, len(ds['items']))
        with self.assertRaises(D.DistillError):
            D.build_dataset([])
        with self.assertRaises(D.DistillError) as ctx:
            D.build_dataset([record(1)] * (D.MAX_RECORDS + 1))
        self.assertEqual('record_count', ctx.exception.code)


# ---------------------------------------------------------------------------
# 2. Splits
# ---------------------------------------------------------------------------

class Splits(unittest.TestCase):
    def test_frozen_deterministic_disjoint(self):
        ds = dataset(40)
        a = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20))
        self.assertEqual(a, D.freeze_splits(copy.deepcopy(ds), seed='s', ratios=(60, 20, 20)))
        ids = D.verify_splits(ds, a, expected_sha256=a['splits_sha256'])
        self.assertEqual(40, sum(len(v) for v in ids.values()))
        self.assertFalse(set(ids['test']) & set(ids['train']))
        self.assertEqual('not_established', a['novelty'])
        self.assertNotEqual(a['assignments'], D.freeze_splits(ds, seed='other', ratios=(60, 20, 20))['assignments'])

    def test_related_items_never_straddle(self):
        recs = [record(i, source='shared' if i < 6 else None) for i in range(30)]
        recs += [record(100, user='  TASK 100: name the colour   NUMBER 5 in the frozen table.'),
                 record(101, user='task 100: name the colour number 5 in the frozen table.')]
        ds = D.build_dataset(recs)
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20), group_by=['source'])
        by_source = {}
        for it in ds['items']:
            by_source.setdefault(it['provenance']['source_sha256'], set()).add(sp['assignments'][it['item_id']])
        self.assertTrue(all(len(v) == 1 for v in by_source.values()))
        dup = [it['item_id'] for it in ds['items'] if it['provenance']['run_id'] in ('run-100', 'run-101')]
        self.assertEqual(1, len({sp['assignments'][i] for i in dup}))       # normalized-prompt grouping is mandatory
        sp_none = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20), group_by=[])
        self.assertEqual(1, len({sp_none['assignments'][i] for i in dup}))
        self.assertEqual([], sp_none['group_by'])

    def test_digit_skeleton_grouping_is_conservative_and_recorded(self):
        recs = [record(i, user=f'What is {i} plus {i}?') for i in range(20)]
        ds = D.build_dataset(recs)
        with self.assertRaises(D.DistillError) as ctx:
            D.freeze_splits(ds, seed='s', ratios=(60, 20, 20))
        self.assertEqual('empty_test_split', ctx.exception.code)
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20), group_by=['source'])
        self.assertEqual(['source'], sp['group_by'])
        with self.assertRaises(D.DistillError) as ctx:
            D.freeze_splits(ds, seed='s', group_by=['semantic'])
        self.assertEqual('group_by', ctx.exception.code)

    def test_declared_exposure_keeps_items_out_of_test(self):
        ds = dataset(30)
        ids = [it['item_id'] for it in ds['items']]
        exposures = [{'item_id': i, 'kind': 'prior_training', 'evidence_sha256': H(['ev', i])} for i in ids[:20]]
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20), exposures=exposures)
        for row in exposures:
            self.assertNotEqual('test', sp['assignments'][row['item_id']])
        self.assertEqual(sorted(exposures, key=lambda r: (r['item_id'], r['kind'], r['evidence_sha256'])),
                         sp['exposures'])
        with self.assertRaises(D.DistillError) as ctx:
            D.freeze_splits(ds, seed='s', exposures=[{'item_id': H('nope'), 'kind': 'published',
                                                     'evidence_sha256': H(1)}])
        self.assertEqual('exposure_unknown_item', ctx.exception.code)
        with self.assertRaises(D.DistillError) as ctx:
            D.freeze_splits(ds, seed='s', exposures=exposures[:1] * 2)
        self.assertEqual('exposure_duplicate', ctx.exception.code)

    def test_exposure_hash_links_groups(self):
        recs = records(30)
        recs[5]['exposure_hashes'] = [recs[6]['prompt']['sha256']]
        ds = D.build_dataset(recs)
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20), group_by=[])
        by_run = {it['provenance']['run_id']: it['item_id'] for it in ds['items']}
        self.assertEqual(sp['assignments'][by_run['run-5']], sp['assignments'][by_run['run-6']])

    def test_changed_or_mismatched_manifests_refuse(self):
        ds = dataset(30)
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20))
        moved = copy.deepcopy(sp)
        test_id = next(i for i, s in moved['assignments'].items() if s == 'test')
        moved['assignments'][test_id] = 'train'
        for bad, code in ((moved, 'splits_changed'), ({**sp, 'seed': 'other'}, 'splits_changed'),
                          ({**sp, 'dataset_sha256': H('x')}, 'splits_dataset_mismatch')):
            with self.assertRaises(D.DistillError) as ctx:
                D.verify_splits(ds, bad)
            self.assertEqual(code, ctx.exception.code)
        with self.assertRaises(D.DistillError) as ctx:
            D.verify_splits(ds, sp, expected_sha256=H('old'))
        self.assertEqual('splits_pin_mismatch', ctx.exception.code)
        for ratios in ((50, 50, 0), (0, 50, 50), (60, 20, 21), (60.0, 20, 20)):
            with self.assertRaises(D.DistillError):
                D.freeze_splits(ds, seed='s', ratios=ratios)


# ---------------------------------------------------------------------------
# 3. Plans, jobs and GRPO status
# ---------------------------------------------------------------------------

class Plans(unittest.TestCase):
    def test_plan_pins_everything_and_excludes_test(self):
        env = Env(self)
        ds, sp, plan = frozen(env)
        self.assertEqual(plan['plan_sha256'], D.verify_plan(plan))
        for key in ('dataset_sha256', 'splits_sha256', 'train_ids_sha256', 'test_ids_sha256', 'model', 'options',
                    'packages'):
            self.assertIn(key, plan)
        self.assertEqual({'torch': '2.14.1', 'transformers': '5.18.0', 'peft': '0.21.2', 'safetensors': '0.8.0',
                          'tokenizers': '0.23.2'}, plan['packages'])
        self.assertEqual('never_automatic', plan['promotion'])
        job = D.training_job(ds, sp, plan)
        ids = D.split_ids(sp)
        self.assertEqual(ids['train'], [r['item_id'] for r in job['train']])
        test_items = [it for it in ds['items'] if it['item_id'] in set(ids['test'])]
        blob = D.canonical(job)
        for it in test_items:
            self.assertNotIn(it['prompt']['user'], blob)
            self.assertNotIn(it['item_id'], blob)

    def test_test_reuse_and_tampering_refuse(self):
        env = Env(self)
        ds, sp, plan = frozen(env)
        forged = copy.deepcopy(sp)
        tid = next(i for i, s in forged['assignments'].items() if s == 'test')
        forged['assignments'][tid] = 'train'
        with self.assertRaises(D.DistillError):
            D.training_job(ds, forged, plan)
        job = D.training_job(ds, sp, plan)
        test_item = next(it for it in ds['items'] if sp['assignments'][it['item_id']] == 'test')
        job['train'].append({'item_id': test_item['item_id'], 'system': '', 'user': test_item['prompt']['user'],
                             'target': test_item['target']})
        job['job_sha256'] = D.digest({k: v for k, v in job.items() if k != 'job_sha256'})
        with self.assertRaises(W.WorkerError) as ctx:
            W._verify_job(job)
        self.assertEqual('job_changed', ctx.exception.code)
        changed = copy.deepcopy(plan)
        changed['options']['max_steps'] = 5
        with self.assertRaises(D.DistillError) as ctx:
            D.verify_plan(changed)
        self.assertEqual('plan_changed', ctx.exception.code)

    def test_options_and_model_spec_validation(self):
        env = Env(self)
        ds = dataset(30)
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20))
        for bad in ({'learning_rate': 0.0002}, {'learning_rate': '0'}, {'dtype': 'float16'}, {'device': 'tpu'}, {'device': 'cuda'},
                    {'unknown': 1}, {'max_steps': True}, {'target_modules': ['q_proj; rm -rf /']},
                    {'lora_dropout': '1.5'}):
            with self.assertRaises(D.DistillError, msg=bad) as ctx:
                D.plan_training(ds, sp, model=env.spec(), options=bad)
            self.assertEqual('train_options', ctx.exception.code)
        for change in ({'revision': 'main'}, {'dir': '../etc'}, {'dir': '/abs'}, {'repo_id': 'https://x/y'}):
            with self.assertRaises(D.DistillError):
                D.plan_training(ds, sp, model={**env.spec(), **change})
        with self.assertRaises(D.DistillError) as ctx:
            D.plan_training(ds, sp, model=env.spec(), packages={'torch': '2.14.1'})
        self.assertEqual('package_pins', ctx.exception.code)

    def test_grpo_is_an_explicit_unsupported_status(self):
        env = Env(self)
        ds = dataset(30)
        sp = D.freeze_splits(ds, seed='s', ratios=(60, 20, 20))
        with self.assertRaises(D.DistillError) as ctx:
            D.plan_training(ds, sp, model=env.spec(), method='grpo')
        self.assertEqual('grpo_unsupported', ctx.exception.code)
        status = D.grpo_status()
        self.assertEqual('unsupported', status['status'])
        self.assertFalse(status['reports_success'])
        self.assertTrue(any('never held-out answers' in g for g in status['gap']))


# ---------------------------------------------------------------------------
# 5. Evaluation planning and the pure comparison
# ---------------------------------------------------------------------------

class Comparison(unittest.TestCase):
    def setUp(self):
        env = Env(self)
        self.ds, self.sp, self.plan = frozen(env)
        self.ep = D.plan_evaluation(self.ds, self.sp, self.plan, max_new_tokens=32)

    def rows(self, statuses):
        out = []
        for arm, seq in statuses.items():
            for item, status in zip(self.ep['items'], seq):
                out.append({'arm': arm, 'item_id': item['item_id'], 'status': status, 'attempts': 1,
                            'output_sha256': None, 'check': {}})
        return out

    def test_eval_plan_freezes_identical_items_and_budgets(self):
        ids = D.split_ids(self.sp)['test']
        self.assertEqual(ids, [it['item_id'] for it in self.ep['items']])
        self.assertEqual(['baseline', 'trained'], self.ep['arms'])
        self.assertEqual({'max_new_tokens': 32, 'decoding': 'greedy', 'attempts_per_item': 1}, self.ep['budget'])
        blob = D.canonical(self.ep)
        for it in self.ds['items']:
            if it['item_id'] in ids:
                self.assertNotIn(it['target'], blob)                # no answers in the eval plan
        ref = D.plan_evaluation(self.ds, self.sp, self.plan, checker='schema_and_reference', prior_test_uses=2)
        self.assertEqual('reused', ref['heldout_status'])
        self.assertTrue(all('reference_sha256' in it and 'value' not in it for it in ref['items']))

    def test_denominators_missing_and_uncertainty(self):
        n = len(self.ep['items'])
        self.assertEqual(6, n)
        rows = self.rows({'baseline': ['passed', 'failed', 'failed', 'failed', 'error', 'unavailable'],
                          'trained': ['passed', 'passed', 'passed', 'passed', 'passed']})   # one trained row missing
        out = D.compare(self.ep, rows)
        self.assertEqual({'#q': '1/6'}, out['arms']['baseline']['pass_rate'])
        self.assertEqual({'#q': '5/6'}, out['arms']['trained']['pass_rate'])
        self.assertEqual(1, out['arms']['trained']['counts']['missing'])
        self.assertEqual('not_established', out['comparison'])
        self.assertFalse(out['complete'])
        lo, hi = out['arms']['baseline']['wilson95']
        self.assertTrue(0 <= float(lo) < 1 / 6 < float(hi) <= 1)

    def test_exact_mcnemar_and_complete_verdict(self):
        rows = self.rows({'baseline': ['failed'] * 4 + ['passed', 'passed'],
                          'trained': ['passed'] * 4 + ['passed', 'failed']})
        out = D.compare(self.ep, rows)
        self.assertEqual((1, 4), (out['paired']['baseline_only_passed'], out['paired']['trained_only_passed']))
        # two-sided exact binomial on 5 discordant pairs, k=1: 2 * (1 + 5) / 32 = 3/8
        self.assertEqual({'#q': '3/8'}, out['paired']['mcnemar_exact_p'])
        self.assertEqual(Fraction(3, 8), 2 * Fraction(1 + 5, 32))
        self.assertEqual('difference_observed_under_declared_checker', out['comparison'])
        same = D.compare(self.ep, self.rows({'baseline': ['passed'] * 6, 'trained': ['passed'] * 6}))
        self.assertEqual('no_difference_observed', same['comparison'])
        self.assertIn('structural acceptance is not semantic truth', out['limits'])

    def test_duplicate_unplanned_and_changed_plan_refuse(self):
        rows = self.rows({'baseline': ['passed'] * 6})
        with self.assertRaises(D.DistillError) as ctx:
            D.compare(self.ep, rows + rows[:1])
        self.assertEqual('outcome_duplicate', ctx.exception.code)
        extra = dict(rows[0], item_id=H('unplanned'))
        with self.assertRaises(D.DistillError) as ctx:
            D.compare(self.ep, [extra])
        self.assertEqual('outcome_unplanned_item', ctx.exception.code)
        changed = copy.deepcopy(self.ep)
        changed['budget']['max_new_tokens'] = 64
        with self.assertRaises(D.DistillError) as ctx:
            D.compare(changed, rows)
        self.assertEqual('eval_changed', ctx.exception.code)

    def test_structural_checker(self):
        item = {'answer_type': 'integer'}
        self.assertTrue(D.check_output(item, ' {"answer": 7} ')['schema_valid'])
        for text in ('{"answer": 7.0}', '{"answer": true}', '{"answer": 7, "why": 1}', 'seven', '[7]',
                     '{"answer": NaN}', 'x' * 70000):
            self.assertFalse(D.check_output(item, text)['schema_valid'], text)
        label = {'answer_type': 'label', 'labels': ['red', 'blue']}
        self.assertTrue(D.check_output(label, '{"answer": "red"}')['schema_valid'])
        self.assertFalse(D.check_output(label, '{"answer": "green"}')['schema_valid'])
        ref = {'answer_type': 'integer', 'reference_sha256': H(7)}
        self.assertEqual('passed', D.score_outcome(ref, D.check_output(ref, '{"answer": 7}')))
        self.assertEqual('failed', D.score_outcome(ref, D.check_output(ref, '{"answer": 8}')))


# ---------------------------------------------------------------------------
# 6. Worker: training, recovery, safety
# ---------------------------------------------------------------------------

class WorkerTraining(unittest.TestCase):
    def setUp(self):
        self.env = Env(self)
        self.ds, self.sp, self.plan = frozen(self.env)
        self.job = D.training_job(self.ds, self.sp, self.plan)
        self.dir = W.prepare_job(str(self.env.jobs), 'train', self.job)

    def run_job(self, backend, **kw):
        return W.run(self.dir, models_root=str(self.env.models), backend=backend, **kw)

    def state(self):
        return json.loads(Path(self.dir, 'state.json').read_text())

    def test_import_is_inert(self):
        code = ('import sys, threading; sys.path.insert(0, %r); import symblic.distill.worker, symblic.distill.datasets; '
                'heavy = [m for m in sys.modules if m.split(".")[0] in ("torch", "transformers", "peft", '
                '"safetensors", "tokenizers")]; print(heavy, threading.active_count())' % str(ROOT))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True, timeout=60)
        self.assertEqual('[] 1', out.stdout.strip())

    def test_complete_training_flow(self):
        fake = Fake()
        result = self.run_job(fake)
        self.assertEqual('completed', result['status'])
        self.assertEqual(4, result['steps'])
        self.assertEqual('step-00000004', result['checkpoint'])
        self.assertEqual('not_established', result['claims']['quality'])
        self.assertEqual(0, result['claims']['test_items_used'])
        self.assertEqual('never_automatic', result['promotion'])
        self.assertEqual('1.250000', result['validation_loss'])
        digest, manifest = W.verify_checkpoint(str(Path(self.dir, 'checkpoints', 'step-00000004')))
        self.assertEqual(result['checkpoint_manifest_sha256'], digest)
        self.assertEqual(self.plan['plan_sha256'], manifest['identity']['plan_sha256'])
        self.assertTrue(Path(self.dir, 'checkpoints', 'step-00000002', 'MANIFEST.json').exists())
        test_ids = set(D.split_ids(self.sp)['test'])
        self.assertFalse(test_ids & {i for step in fake.batches for mb in step for i in mb})
        self.assertEqual(json.loads(Path(self.dir, 'result.json').read_text()), result)
        again = Fake()
        self.assertEqual(result, self.run_job(again))           # completed: never re-trained
        self.assertEqual([], again.batches)

    def test_crash_resume_continues_the_same_schedule(self):
        reference = Fake()
        other = W.prepare_job(str(self.env.jobs), 'reference', self.job)
        W.run(other, models_root=str(self.env.models), backend=reference)
        crashing = Fake(crash_at=4)
        with self.assertRaises(KeyboardInterrupt):
            self.run_job(crashing)
        self.assertEqual('running', self.state()['status'])
        resumed = Fake()
        result = self.run_job(resumed)
        self.assertEqual('completed', result['status'])
        self.assertEqual(('begin', 'qwen', 'step-00000002', None, True), resumed.calls[1])
        self.assertEqual(3, len(crashing.batches))                 # steps 1-3 ran; only step 2 was checkpointed
        self.assertEqual(reference.batches[:3], crashing.batches)
        self.assertEqual(reference.batches[2:], resumed.batches)
        events = [h['event'] for h in self.state()['history']]
        self.assertIn('previous_attempt_interrupted', events)
        self.assertEqual(2, events.count('attempt_started'))
        self.assertEqual(result['checkpoint_manifest_sha256'],
                         json.loads(Path(other, 'result.json').read_text())['checkpoint_manifest_sha256'])

    def test_torn_and_corrupt_checkpoints_are_quarantined_not_deleted(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_job(Fake(crash_at=4))
        ck = Path(self.dir, 'checkpoints')
        (ck / '.tmp-step-00000004-dead').mkdir()
        (ck / '.tmp-step-00000004-dead' / 'adapter_model.safetensors').write_text('half')
        # also corrupt the only real checkpoint: resume must restart from zero, keeping the evidence
        Path(ck, 'step-00000002', 'adapter_model.safetensors').write_text('{"step": 999}')
        fake = Fake()
        result = self.run_job(fake)
        self.assertEqual('completed', result['status'])
        self.assertEqual(4, len(fake.batches))
        quarantined = sorted(p.name for p in (ck / 'quarantine').iterdir())
        self.assertEqual(2, len(quarantined))
        self.assertTrue(quarantined[0].startswith('.tmp-step-00000004-dead.'))
        self.assertTrue(quarantined[1].startswith('step-00000002.'))
        self.assertEqual('half', (ck / 'quarantine' / quarantined[0] / 'adapter_model.safetensors').read_text())
        reasons = {h.get('reason') for h in self.state()['history'] if h['event'] == 'quarantined'}
        self.assertEqual({'torn_temporary', 'checkpoint_hash_mismatch'}, reasons)
        self.assertIn('no_verified_checkpoint_restart', [h['event'] for h in self.state()['history']])

    def test_checkpoint_of_another_backend_or_model_refuses(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_job(Fake(crash_at=4))
        before = sorted(os.listdir(Path(self.dir, 'checkpoints')))
        result = self.run_job(Fake(name='different-backend'))
        self.assertEqual(('failed', 'checkpoint_identity_mismatch', False),
                         (result['status'], result['code'], result['completed']))
        self.assertEqual(before, sorted(os.listdir(Path(self.dir, 'checkpoints'))))
        self.assertFalse(Path(self.dir, 'result.json').exists())

    def test_torn_unknown_state_and_busy_lock(self):
        state_path = Path(self.dir, 'state.json')
        good = state_path.read_bytes()
        state_path.write_bytes(good[:20])
        with self.assertRaises(W.WorkerError) as ctx:
            self.run_job(Fake())
        self.assertEqual('torn_state', ctx.exception.code)
        self.assertEqual(good[:20], state_path.read_bytes())          # never overwritten
        state_path.write_bytes(good.replace(b'"version":1', b'"version":9'))
        with self.assertRaises(W.WorkerError) as ctx:
            self.run_job(Fake())
        self.assertEqual('unknown_state', ctx.exception.code)
        state_path.write_bytes(good)
        with W._JobLock(self.dir):
            with self.assertRaises(W.WorkerError) as ctx:
                self.run_job(Fake())
            self.assertEqual('job_busy', ctx.exception.code)
        self.assertEqual('completed', self.run_job(Fake())['status'])

    def test_concurrent_workers_one_wins(self):
        gate = threading.Event()

        class Slow(Fake):
            def train_step(self, batches):
                gate.wait(5)
                return super().train_step(batches)
        results = []
        t = threading.Thread(target=lambda: results.append(self.run_job(Slow())))
        t.start()
        for _ in range(200):
            if self.state()['status'] == 'running':
                break
            threading.Event().wait(0.01)
        with self.assertRaises(W.WorkerError) as ctx:
            self.run_job(Fake())
        gate.set()
        t.join(10)
        self.assertEqual('job_busy', ctx.exception.code)
        self.assertEqual('completed', results[0]['status'])

    def test_unexpected_backend_exception_is_recorded_failed(self):
        class Oom(Fake):
            def train_step(self, batches):
                raise MemoryError('fake out of memory')
        result = self.run_job(Oom())
        self.assertEqual(('failed', 'exception:MemoryError', False),
                         (result['status'], result['code'], result['completed']))
        self.assertEqual('failed', self.state()['status'])
        self.assertEqual('completed', self.run_job(Fake())['status'])        # rerunnable after the cause is fixed

    def test_stop_then_resume(self):
        stop = threading.Event()

        class Stopper(Fake):
            def train_step(self, batches):
                out = super().train_step(batches)
                if self.step == 2:
                    stop.set()
                return out
        result = self.run_job(Stopper(), stop=stop)
        self.assertEqual(('stopped', 2), (result['status'], result['step']))
        self.assertEqual('completed', self.run_job(Fake())['status'])

    def test_result_written_but_state_running_recovers(self):
        result = self.run_job(Fake())
        state = self.state()
        state['status'] = 'running'
        Path(self.dir, 'state.json').write_text(json.dumps(state))
        fake = Fake()
        self.assertEqual(result, self.run_job(fake))
        self.assertEqual([], fake.calls)
        self.assertEqual('completed_recovered_from_result', self.state()['history'][-1]['event'])

    def test_model_snapshot_checks(self):
        Path(self.env.models, 'qwen', 'model.safetensors').write_text('different weights')
        result = self.run_job(Fake())
        self.assertEqual(('failed', 'model_manifest_mismatch'), (result['status'], result['code']))
        Path(self.env.models, 'qwen', 'model.safetensors').write_text('weights')
        Path(self.env.models, 'qwen', 'pytorch_model.bin').write_text('pickle')
        self.assertEqual('model_format_unsupported', self.run_job(Fake())['code'])
        os.unlink(Path(self.env.models, 'qwen', 'pytorch_model.bin'))
        Path(self.env.models, 'qwen', 'modeling_custom.py').write_text('code')
        self.assertEqual('model_format_unsupported', self.run_job(Fake())['code'])
        os.unlink(Path(self.env.models, 'qwen', 'modeling_custom.py'))
        os.symlink('/etc/hostname', Path(self.env.models, 'qwen', 'extra.json'))
        self.assertEqual('symlink_refused', self.run_job(Fake())['code'])
        os.unlink(Path(self.env.models, 'qwen', 'extra.json'))
        os.rename(Path(self.env.models, 'qwen'), Path(self.env.models, 'moved'))
        self.assertEqual('model_unavailable', self.run_job(Fake())['code'])
        os.symlink(Path(self.env.models, 'moved'), Path(self.env.models, 'qwen'))
        self.assertEqual('symlink_refused', self.run_job(Fake())['code'])
        failures = [h['code'] for h in self.state()['history'] if h['event'] == 'failed']
        self.assertEqual(6, len(failures))
        self.assertFalse(Path(self.dir, 'result.json').exists())

    def test_path_safety(self):
        link = Path(self.env.root, 'jobs-link')
        os.symlink(self.dir, link)
        with self.assertRaises(W.WorkerError) as ctx:
            W.run(str(link), models_root=str(self.env.models), backend=Fake())
        self.assertEqual('symlink_refused', ctx.exception.code)
        with self.assertRaises(D.DistillError):
            W.prepare_job(str(self.env.jobs), '../escape', self.job)
        with self.assertRaises(W.WorkerError) as ctx:
            W.prepare_job(str(self.env.jobs), 'train', self.job)
        self.assertEqual('job_exists', ctx.exception.code)
        hostile = copy.deepcopy(self.job)
        hostile['plan']['model']['dir'] = '../../etc'
        with self.assertRaises((W.WorkerError, D.DistillError)):
            W.prepare_job(str(self.env.jobs), 'hostile', hostile)

    def test_real_backend_missing_packages_fails_visibly(self):
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'transformers', 'peft', 'safetensors', 'tokenizers'):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)
        with mock.patch.object(builtins, '__import__', blocked):
            result = self.run_job(W.TorchLoraBackend())
        self.assertEqual(('failed', 'missing_package', False), (result['status'], result['code'], result['completed']))
        self.assertFalse(Path(self.dir, 'result.json').exists())
        self.assertEqual([], os.listdir(Path(self.dir, 'checkpoints')))
        self.assertEqual('1', os.environ.get('HF_HUB_OFFLINE'))

    def test_real_backend_version_and_hardware_gates(self):
        backend = W.TorchLoraBackend()
        backend.mods = {'torch': mock.Mock(cuda=mock.Mock(is_available=lambda: False))}
        with mock.patch.object(W.TorchLoraBackend, 'versions', return_value={**self.plan['packages'], 'torch': '2.13.0'}):
            with self.assertRaises(W.BackendUnavailable) as ctx:
                backend.preflight(self.plan)
        self.assertEqual('package_version_mismatch', ctx.exception.code)
        cuda_plan = copy.deepcopy(self.plan)
        cuda_plan['options']['device'] = 'cuda'
        with mock.patch.object(W.TorchLoraBackend, 'versions', return_value=dict(self.plan['packages'])):
            with self.assertRaises(W.BackendUnavailable) as ctx:
                backend.preflight(cuda_plan)
        self.assertEqual('device_unsupported', ctx.exception.code)
        backend.mods['torch'].cuda.is_available = lambda: True
        with mock.patch.object(backend, 'versions', return_value=self.plan['packages']):
            with self.assertRaises(W.BackendUnavailable) as ctx:
                backend.preflight(cuda_plan)
        self.assertEqual('device_unsupported', ctx.exception.code)

    def test_launch_manifest_is_data_only(self):
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('no process may start')):
            out = W.launch_manifest(self.dir, models_root=str(self.env.models), python='/opt/venv/bin/python')
        self.assertFalse(out['shell'])
        self.assertEqual(['/opt/venv/bin/python', str(ROOT / 'symblic' / 'distill' / 'worker.py'), 'run', '--job-dir',
                          self.dir, '--models-root', str(self.env.models), '--backend', 'torch-lora'], out['argv'])
        self.assertEqual('1', out['env']['HF_HUB_OFFLINE'])
        self.assertEqual(self.plan['packages'], out['requires']['packages'])
        for bad in ({'python': 'python3'}, {'python': '/x;rm -rf /\n'}):
            with self.assertRaises(W.WorkerError):
                W.launch_manifest(self.dir, models_root=str(self.env.models), **bad)


# ---------------------------------------------------------------------------
# 5/6. Integration: dataset -> plan -> worker boundary -> checkpoint -> evaluation
# ---------------------------------------------------------------------------

class Integration(unittest.TestCase):
    def setUp(self):
        self.env = Env(self)
        self.ds, self.sp, self.plan = frozen(self.env)
        train_dir = W.prepare_job(str(self.env.jobs), 'train', D.training_job(self.ds, self.sp, self.plan))
        self.trained = W.run(train_dir, models_root=str(self.env.models), backend=Fake())
        self.adapter = os.path.join(train_dir, 'checkpoints', self.trained['checkpoint'])
        self.ep = D.plan_evaluation(self.ds, self.sp, self.plan, max_new_tokens=48,
                                    checker='schema_and_reference')
        self.answers = {it['item_id']: it for it in self.ds['items']}

    def prepare(self, name='eval', adapter_sha=None):
        job = W.eval_job(self.ep, self.plan, adapter_manifest_sha256=adapter_sha or
                         self.trained['checkpoint_manifest_sha256'])
        return W.prepare_job(str(self.env.jobs), name, job)

    def test_end_to_end_same_prompts_budgets_no_answers(self):
        replies = {}
        for item in self.ep['items']:
            value = self.answers[item['item_id']]['answer']['value']
            replies[('trained', item['user'])] = json.dumps({'answer': value})
            replies[('baseline', item['user'])] = 'I think it is ' + str(value)
        fake = Fake(answers=replies)
        result = W.run(self.prepare(), models_root=str(self.env.models), backend=fake, adapter_dir=self.adapter)
        self.assertEqual('completed', result['status'])
        n = len(self.ep['items'])
        by_arm = {a: [(row['system'], row['user'], budget) for arm, row, budget in fake.generated if arm == a]
                  for a in D.ARMS}
        self.assertEqual(by_arm['baseline'], by_arm['trained'])
        self.assertEqual(n, len(by_arm['trained']))
        self.assertEqual({48}, {b for _, _, b in by_arm['trained']})
        for _, row, _ in fake.generated:
            self.assertEqual({'system', 'user'}, set(row))           # the backend never sees an answer
        begins = [c for c in fake.calls if c[0] == 'begin']
        self.assertEqual([('begin', 'qwen', None, None, False),
                          ('begin', 'qwen', None, os.path.basename(self.adapter), False)], begins)
        cmp = result['comparison']
        self.assertEqual(n, cmp['arms']['trained']['passed'])
        self.assertEqual(0, cmp['arms']['baseline']['passed'])
        self.assertEqual('difference_observed_under_declared_checker', cmp['comparison'])
        self.assertEqual(cmp, D.compare(self.ep, result['outcomes']))
        self.assertEqual(2 * n, len(result['outcomes']))

    def test_adapter_pin_tamper_and_identity(self):
        result = W.run(self.prepare('wrongpin', adapter_sha=H('other')), models_root=str(self.env.models),
                       backend=Fake(), adapter_dir=self.adapter)
        self.assertEqual(('failed', 'adapter_pin_mismatch'), (result['status'], result['code']))
        Path(self.adapter, 'adapter_config.json').write_text('{"r": 64}')
        result = W.run(self.prepare(), models_root=str(self.env.models), backend=Fake(), adapter_dir=self.adapter)
        self.assertEqual(('failed', 'checkpoint_hash_mismatch'), (result['status'], result['code']))
        result = W.run(self.prepare('noadapter'), models_root=str(self.env.models), backend=Fake())
        self.assertEqual('adapter_required', result['code'])

    def test_failed_and_unavailable_outcomes_stay_in_the_denominator(self):
        first_user = self.ep['items'][0]['user']
        fake = Fake(unavailable_arms=('trained',), fail_items={('baseline', first_user)})
        result = W.run(self.prepare(), models_root=str(self.env.models), backend=fake, adapter_dir=self.adapter)
        self.assertEqual('completed', result['status'])
        cmp = result['comparison']
        n = len(self.ep['items'])
        self.assertEqual(n, cmp['arms']['trained']['counts']['unavailable'])
        self.assertEqual(1, cmp['arms']['baseline']['counts']['error'])
        self.assertEqual('not_established', cmp['comparison'])
        error = next(o for o in result['outcomes'] if o['status'] == 'error')
        self.assertEqual('generation_error:RuntimeError', error['check']['reason'])

    def test_interrupted_evaluation_resumes_and_counts_attempts(self):
        class Crash(Fake):
            def generate(self, row, max_new_tokens):
                if len(self.generated) == 2:
                    raise KeyboardInterrupt('power loss mid-item')
                return super().generate(row, max_new_tokens)
        job = self.prepare()
        with self.assertRaises(KeyboardInterrupt):
            W.run(job, models_root=str(self.env.models), backend=Crash(), adapter_dir=self.adapter)
        state = json.loads(Path(job, 'state.json').read_text())
        self.assertEqual(2, len(state['outcomes']))
        self.assertIsNotNone(state['in_flight'])
        fake = Fake()
        result = W.run(job, models_root=str(self.env.models), backend=fake, adapter_dir=self.adapter)
        self.assertEqual('completed', result['status'])
        attempts = {(o['arm'], o['item_id']): o['attempts'] for o in result['outcomes']}
        self.assertEqual(2, attempts[(state['in_flight']['arm'], state['in_flight']['item_id'])])
        self.assertEqual(2 * len(self.ep['items']), len(result['outcomes']))
        self.assertEqual(2 * len(self.ep['items']) - 2, len(fake.generated))


# ---------------------------------------------------------------------------
# Explicit inference with the pinned trained adapter
# ---------------------------------------------------------------------------

class Inference(unittest.TestCase):
    def setUp(self):
        self.env = Env(self)
        self.ds, self.sp, self.plan = frozen(self.env)
        self.train_dir = W.prepare_job(str(self.env.jobs), 'train', D.training_job(self.ds, self.sp, self.plan))
        self.trained = W.run(self.train_dir, models_root=str(self.env.models), backend=Fake())
        self.adapter = os.path.join(self.train_dir, 'checkpoints', self.trained['checkpoint'])
        self.pin = self.trained['checkpoint_manifest_sha256']
        self.prompt = {'version': 1, 'system': 'You carry out exactly one statement.',
                       'user': 'A brand-new prompt nobody recorded.', 'answer_type': 'integer'}

    def infer(self, name='receipt.json', backend=None, **kw):
        args = dict(plan=self.plan, models_root=str(self.env.models), backend=backend or Fake(answers={
            ('trained', self.prompt['user']): '{"answer": 42}'}), prompt=self.prompt,
            out_path=str(self.env.root / name), adapter_dir=self.adapter, adapter_manifest_sha256=self.pin)
        args.update(kw)
        return W.infer(**args)

    def test_trained_adapter_answers_a_new_prompt_with_full_identity(self):
        fake = Fake(answers={('trained', self.prompt['user']): '{"answer": 42}'})
        receipt = self.infer(backend=fake)
        self.assertEqual(('trained', '{"answer": 42}'), (receipt['arm'], receipt['output']['text']))
        self.assertEqual(hashlib.sha256(b'{"answer": 42}').hexdigest(), receipt['output']['sha256'])
        self.assertEqual(self.pin, receipt['adapter']['manifest_sha256'])
        self.assertEqual(4, receipt['adapter']['step'])
        self.assertEqual(self.plan['plan_sha256'], receipt['plan_sha256'])
        self.assertEqual({'repo_id': 'Qwen/Qwen2.5-0.5B-Instruct', 'revision': REVISION,
                          'files_sha256': self.env.manifest['files_sha256']}, receipt['model'])
        self.assertEqual({'max_new_tokens': 256, 'decoding': 'greedy', 'dtype': 'float32', 'device': 'cpu',
                          'seed': 1234}, receipt['options'])
        self.assertEqual('fake', receipt['backend']['name'])
        self.assertTrue(receipt['structural_check']['schema_valid'])
        self.assertEqual({'quality': 'not_established', 'native_verification': 'not_performed',
                          'promotion': 'never_automatic'}, receipt['claims'])
        self.assertEqual({'checked': False, 'novelty': 'not_established'}, receipt['dataset_overlap'])
        self.assertEqual(('begin', 'qwen', None, os.path.basename(self.adapter), False),
                         [c for c in fake.calls if c[0] == 'begin'][0])
        self.assertEqual([('trained', {'system': self.prompt['system'], 'user': self.prompt['user']}, 256)],
                         fake.generated)
        self.assertEqual(receipt, json.loads(Path(self.env.root, 'receipt.json').read_text()))
        self.assertEqual(receipt['receipt_sha256'], D.digest({k: v for k, v in receipt.items()
                                                              if k != 'receipt_sha256'}))
        with self.assertRaises(W.WorkerError) as ctx:
            self.infer()
        self.assertEqual('output_exists', ctx.exception.code)

    def test_baseline_arm_and_dataset_overlap(self):
        test_item = next(it for it in self.ds['items'] if self.sp['assignments'][it['item_id']] == 'test')
        self.prompt = {'version': 1, 'system': test_item['prompt']['system'], 'user': test_item['prompt']['user']}
        receipt = self.infer(arm='baseline', adapter_dir=None, adapter_manifest_sha256=None,
                             dataset=self.ds, splits=self.sp)
        self.assertIsNone(receipt['adapter'])
        self.assertEqual('not_requested', receipt['structural_check'])
        self.assertEqual([{'item_id': test_item['item_id'], 'split': 'test', 'match': 'exact'}],
                         receipt['dataset_overlap']['matches'])
        self.assertEqual('not_established', receipt['dataset_overlap']['novelty'])
        with self.assertRaises(W.WorkerError) as ctx:
            self.infer('b2.json', arm='baseline')
        self.assertEqual('baseline_takes_no_adapter', ctx.exception.code)

    def test_adapter_must_be_the_pinned_verified_checkpoint(self):
        for kw, code in (({'adapter_manifest_sha256': None}, 'adapter_pin_required'),
                         ({'adapter_manifest_sha256': H('x')}, 'adapter_pin_mismatch'),
                         ({'adapter_dir': None}, 'adapter_required'),
                         ({'arm': 'other'}, 'infer_arm'), ({'max_new_tokens': 0}, 'infer_budget'),
                         ({'prompt': {'version': 1, 'system': '', 'user': ' '}}, 'prompt_schema'),
                         ({'prompt': {'version': 1, 'system': '', 'user': 'x', 'extra': 1}}, 'prompt_schema')):
            with self.assertRaises(W.WorkerError, msg=kw) as ctx:
                self.infer('r-%s.json' % code, **kw)
            self.assertEqual(code, ctx.exception.code)
        other = D.plan_training(self.ds, self.sp, model=self.env.spec(), options={'max_steps': 3, 'grad_accum': 2})
        with self.assertRaises(W.WorkerError) as ctx:
            self.infer('other-plan.json', plan=other)
        self.assertEqual('adapter_identity_mismatch', ctx.exception.code)
        Path(self.adapter, 'adapter_model.safetensors').write_text('{"step": 1}')
        with self.assertRaises(W.WorkerError) as ctx:
            self.infer('tampered.json')
        self.assertEqual('checkpoint_hash_mismatch', ctx.exception.code)
        self.assertFalse(any(p.name.startswith(('r-', 'other-', 'tampered')) for p in self.env.root.iterdir()))

    def test_real_backend_without_packages_writes_no_receipt(self):
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'transformers', 'peft', 'safetensors', 'tokenizers'):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)
        with mock.patch.object(builtins, '__import__', blocked):
            with self.assertRaises(W.BackendUnavailable) as ctx:
                self.infer(backend=W.TorchLoraBackend())
        self.assertEqual('missing_package', ctx.exception.code)
        self.assertFalse(Path(self.env.root, 'receipt.json').exists())

    def test_inference_manifest_is_data_only(self):
        plan_path = self.env.root / 'plan.json'
        D.write_json(str(plan_path), self.plan)
        m = W.infer_manifest(plan_path=str(plan_path), prompt_path='/in/prompt.json', out_path='/out/r.json',
                             models_root=str(self.env.models), python='/opt/venv/bin/python',
                             adapter_dir=self.adapter, adapter_manifest_sha256=self.pin)
        self.assertFalse(m['shell'])
        self.assertEqual(['infer', '--plan', str(plan_path)], m['argv'][2:5])
        self.assertEqual(['--adapter-dir', self.adapter, '--adapter-manifest-sha256', self.pin], m['argv'][-4:])
        with self.assertRaises(W.WorkerError):
            W.infer_manifest(plan_path=str(plan_path), prompt_path='prompt.json', out_path='/o', models_root='/m',
                             python='/p', adapter_dir=self.adapter, adapter_manifest_sha256=self.pin)
        with self.assertRaises(W.WorkerError):
            W.infer_manifest(plan_path=str(plan_path), prompt_path='/p.json', out_path='/o', models_root='/m',
                             python='/p')                       # trained arm without an adapter pin


# ---------------------------------------------------------------------------
# Native checker interface: trusted pinned module; reference equality is never native verification
# ---------------------------------------------------------------------------

CHECKER_SOURCE = '''
import hashlib, json
EXPECTED = %s          # stands in for root's trusted program store + native predicates
MODE = %r


class Checker:
    def identity(self):
        return {'id': 'fake-native', 'version': 1, 'kernel_id': %r, 'contract_version': 1,
                'source_sha256': hashlib.sha256(b'fake-native-checker').hexdigest()}

    def check(self, contract, answer):
        if MODE == 'raise':
            raise RuntimeError('checker crashed')
        if MODE == 'bad':
            return {'passed': 'yes'}
        ok = EXPECTED.get(contract['statement_sha256']) == answer
        return {'passed': ok, 'scope': 'encoded_predicate', 'kernel_id': contract['kernel_id'],
                'receipts': [hashlib.sha256(json.dumps([contract['statement_sha256'], answer]).encode()).hexdigest()]}


CHECKERS = {'fake-native': Checker}
'''


class NativeChecker(unittest.TestCase):
    def setUp(self):
        self.env = Env(self)
        self.ds, self.sp, self.plan = frozen(self.env)
        train_dir = W.prepare_job(str(self.env.jobs), 'train', D.training_job(self.ds, self.sp, self.plan))
        self.trained = W.run(train_dir, models_root=str(self.env.models), backend=Fake())
        self.adapter = os.path.join(train_dir, 'checkpoints', self.trained['checkpoint'])
        self.module = self.env.root / 'checkers.py'
        patcher = mock.patch.object(W, 'CHECKER_MODULE_PATH', str(self.module))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.expected = {it['provenance']['statement_sha256']: it['answer']['value'] for it in self.ds['items']}

    def write_module(self, mode='ok', kernel=KERNEL):
        self.module.write_text(CHECKER_SOURCE % (repr(self.expected), mode, kernel))

    def eval_job(self, name, pin):
        ep = D.plan_evaluation(self.ds, self.sp, self.plan, checker='schema_and_native', native_checker=pin)
        job = W.eval_job(ep, self.plan, adapter_manifest_sha256=self.trained['checkpoint_manifest_sha256'])
        return ep, W.prepare_job(str(self.env.jobs), name, job)

    def replies(self, trained_correct=True):
        out = {}
        for it in self.ds['items']:
            if self.sp['assignments'][it['item_id']] != 'test':
                continue
            value = it['answer']['value']
            out[('trained', it['prompt']['user'])] = json.dumps({'answer': value if trained_correct else value + 1})
            out[('baseline', it['prompt']['user'])] = json.dumps({'answer': value + 1})
        return out

    def run_eval(self, job, backend):
        return W.run(job, models_root=str(self.env.models), backend=backend, adapter_dir=self.adapter)

    def test_native_verification_pins_and_scores(self):
        self.write_module()
        pin = W.checker_identity('fake-native')
        self.assertEqual(hashlib.sha256(self.module.read_bytes()).hexdigest(), pin['module_sha256'])
        ep, job = self.eval_job('native', pin)
        self.assertEqual('structural_answer_schema_and_native_encoded_predicates', ep['checker']['scope'])
        blob = D.canonical(ep['items'])
        for it in self.ds['items']:
            if self.sp['assignments'][it['item_id']] == 'test':
                self.assertNotIn(it['target'], blob)                    # contracts carry no accepted answer
                self.assertNotIn('reference_sha256', D.canonical(ep['items']))
        result = self.run_eval(job, Fake(answers=self.replies()))
        self.assertEqual('completed', result['status'])
        cmp = result['comparison']
        n = len(ep['items'])
        self.assertEqual((n, 0), (cmp['arms']['trained']['passed'], cmp['arms']['baseline']['passed']))
        row = next(o for o in result['outcomes'] if o['arm'] == 'trained')
        self.assertEqual({'ran', 'passed', 'scope', 'kernel_id', 'receipts', 'checker_module_sha256', 'checker_id'},
                         set(row['check']['native']))
        self.assertTrue(row['check']['native']['passed'])
        self.assertNotIn('_value', row['check'])
        self.assertNotIn('reference_match', row['check'])
        self.assertEqual(cmp['checker_scope'], 'structural_answer_schema_and_native_encoded_predicates')

    def test_missing_changed_or_mismatched_checker_refuses_never_passes(self):
        self.write_module()
        pin = W.checker_identity('fake-native')
        _, job = self.eval_job('missing', pin)
        os.unlink(self.module)
        result = self.run_eval(job, Fake(answers=self.replies()))
        self.assertEqual(('failed', 'checker_unavailable', False),
                         (result['status'], result['code'], result['completed']))
        state = json.loads(Path(job, 'state.json').read_text())
        self.assertEqual([], state['outcomes'])
        self.module.write_text(CHECKER_SOURCE % (repr(self.expected), 'ok', KERNEL) + '\n# edited\n')
        self.assertEqual('checker_source_mismatch', self.run_eval(job, Fake())['code'])
        changed = copy.deepcopy(pin)
        changed['identity']['version'] = 2
        self.write_module()
        _, job2 = self.eval_job('identity', changed)
        self.assertEqual('checker_identity_mismatch', self.run_eval(job2, Fake())['code'])
        os.unlink(self.module)
        os.symlink('/etc/hostname', self.module)
        with self.assertRaises(W.WorkerError) as ctx:
            W.checker_identity('fake-native')
        self.assertEqual('symlink_refused', ctx.exception.code)
        os.unlink(self.module)
        with self.assertRaises(D.DistillError) as ctx:
            D.plan_evaluation(self.ds, self.sp, self.plan, checker='schema_and_native')
        self.assertEqual('eval_checker', ctx.exception.code)

    def test_failed_error_and_kernel_mismatch_outcomes(self):
        self.write_module()
        pin = W.checker_identity('fake-native')
        _, job = self.eval_job('wrong', pin)
        result = self.run_eval(job, Fake(answers=self.replies(trained_correct=False)))
        self.assertEqual(0, result['comparison']['arms']['trained']['passed'])
        self.assertTrue(all(o['check']['native']['passed'] is False for o in result['outcomes']))
        schema_bad = Fake(answers={k: 'not json' for k in self.replies()})
        _, job = self.eval_job('schema', pin)
        result = self.run_eval(job, schema_bad)
        self.assertTrue(all(o['check']['native'] == {'ran': False, 'reason': 'schema_invalid'}
                            and o['status'] == 'failed' for o in result['outcomes']))
        for mode, status, reason in (('raise', 'error', 'checker_error:RuntimeError'),
                                     ('bad', 'error', 'checker_bad_receipt')):
            self.write_module(mode)
            pin = W.checker_identity('fake-native')
            _, job = self.eval_job('mode-' + mode, pin)
            result = self.run_eval(job, Fake(answers=self.replies()))
            self.assertTrue(all(o['status'] == status and o['check']['native']['reason'] == reason
                                for o in result['outcomes']), mode)
            self.assertEqual(0, result['comparison']['arms']['trained']['passed'])
        self.write_module(kernel='f' * 16)
        pin = W.checker_identity('fake-native')
        _, job = self.eval_job('kernel', pin)
        result = self.run_eval(job, Fake(answers=self.replies()))
        self.assertTrue(all(o['status'] == 'unavailable' and o['check']['native']['reason'] == 'checker_kernel_mismatch'
                            for o in result['outcomes']))
        self.assertEqual('not_established', result['comparison']['comparison'])

    def test_reference_equality_is_labelled_as_agreement_not_verification(self):
        ep = D.plan_evaluation(self.ds, self.sp, self.plan, checker='schema_and_reference')
        self.assertEqual('structural_answer_schema_and_reference_hash_agreement', ep['checker']['scope'])
        self.assertNotIn('native', ep['checker'])
        item = ep['items'][0]
        value = next(it for it in self.ds['items'] if it['item_id'] == item['item_id'])['answer']['value']
        check = D.check_output(item, json.dumps({'answer': value}))
        check.pop('_value')
        self.assertEqual('passed', D.score_outcome(item, check))
        self.assertTrue(check['reference_match'])
        self.assertNotIn('native', check)
        native_item = {'answer_type': 'integer', 'contract': {}}
        with self.assertRaises(D.DistillError) as ctx:
            D.score_outcome(native_item, {'schema_valid': True, 'answer_sha256': H(1)})
        self.assertEqual('native_checker_required', ctx.exception.code)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class Cli(unittest.TestCase):
    def cli(self, *args, code=0):
        out = subprocess.run([sys.executable, '-m', 'symblic.distill.cli', *args], capture_output=True,
                             text=True, timeout=120, cwd=str(ROOT))
        self.assertEqual(code, out.returncode, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def test_cli_flow_and_refusals(self):
        env = Env(self)
        t = env.root
        (t / 'records.json').write_text(json.dumps(records(30)))
        built = self.cli('build', '--records', str(t / 'records.json'), '--out', str(t / 'dataset.json'))
        self.assertEqual('written', built['status'])
        self.assertEqual('output_exists', self.cli('build', '--records', str(t / 'records.json'), '--out',
                                                   str(t / 'dataset.json'), code=2)['code'])
        self.cli('split', '--dataset', str(t / 'dataset.json'), '--seed', 's', '--ratios', '60,20,20',
                 '--out', str(t / 'splits.json'))
        manifest = self.cli('model-manifest', '--model-dir', str(env.models / 'qwen'))
        self.assertEqual(env.manifest, manifest)
        (t / 'model.json').write_text(json.dumps(env.spec()))
        (t / 'options.json').write_text(json.dumps({'max_steps': 2, 'grad_accum': 2, 'checkpoint_every': 1}))
        plan = self.cli('plan-train', '--dataset', str(t / 'dataset.json'), '--splits', str(t / 'splits.json'),
                        '--model-spec', str(t / 'model.json'), '--options', str(t / 'options.json'),
                        '--out', str(t / 'plan.json'))
        prepared = self.cli('prepare-train', '--dataset', str(t / 'dataset.json'), '--splits', str(t / 'splits.json'),
                            '--plan', str(t / 'plan.json'), '--jobs-root', str(env.jobs), '--name', 'cli-train',
                            '--expect-plan-sha256', plan['sha256'])
        launch = self.cli('launch', '--job-dir', prepared['job_dir'], '--models-root', str(env.models),
                          '--python', '/opt/venv/bin/python')
        self.assertEqual('torch-lora', launch['argv'][-1])
        self.assertEqual('prepared', json.loads(Path(prepared['job_dir'], 'state.json').read_text())['status'])
        self.assertEqual('plan_pin_mismatch', self.cli(
            'prepare-train', '--dataset', str(t / 'dataset.json'), '--splits', str(t / 'splits.json'), '--plan',
            str(t / 'plan.json'), '--jobs-root', str(env.jobs), '--name', 'x', '--expect-plan-sha256', H('x'),
            code=2)['code'])
        self.cli('plan-eval', '--dataset', str(t / 'dataset.json'), '--splits', str(t / 'splits.json'), '--plan',
                 str(t / 'plan.json'), '--out', str(t / 'eval.json'))
        self.assertEqual('grpo_unsupported', self.cli(
            'plan-train', '--dataset', str(t / 'dataset.json'), '--splits', str(t / 'splits.json'), '--model-spec',
            str(t / 'model.json'), '--method', 'grpo', '--out', str(t / 'g.json'), code=2)['code'])
        self.assertEqual('unsupported', self.cli('grpo-status')['status'])
        (t / 'prompt.json').write_text(json.dumps({'version': 1, 'system': '', 'user': 'new prompt'}))
        infer = self.cli('launch-infer', '--plan', str(t / 'plan.json'), '--prompt', str(t / 'prompt.json'),
                         '--out', str(t / 'receipt.json'), '--models-root', str(env.models), '--python',
                         '/opt/venv/bin/python', '--arm', 'baseline')
        self.assertEqual(['infer', '--plan'], infer['argv'][2:4])
        self.assertFalse((t / 'receipt.json').exists())               # printed, never executed
        self.assertEqual('infer_arm', self.cli('launch-infer', '--plan', str(t / 'plan.json'), '--prompt',
                                               str(t / 'prompt.json'), '--out', str(t / 'r.json'), '--models-root',
                                               str(env.models), '--python', '/p', code=2)['code'])
        self.assertEqual('checker_unavailable', self.cli('checker-identity', '--name', 'x', code=2)['code'])
        self.assertEqual('eval_checker', self.cli(
            'plan-eval', '--dataset', str(t / 'dataset.json'), '--splits', str(t / 'splits.json'), '--plan',
            str(t / 'plan.json'), '--checker', 'schema_and_native', '--out', str(t / 'e2.json'), code=2)['code'])

    def test_strict_json_reader(self):
        with tempfile.TemporaryDirectory() as d:
            for body, code in (('{"a": 1, "a": 2}', 'duplicate_json_key'), ('{"a": 1.5}', 'float_in_json'),
                               ('{"a": NaN}', 'float_in_json'), ('{"a": ', 'invalid_json'),
                               (b'\xff\xfe', 'invalid_utf8')):
                p = Path(d, 'x.json')
                p.write_bytes(body if isinstance(body, bytes) else body.encode())
                self.assertEqual(code, self.cli('hash', str(p), code=2)['code'])
            os.symlink(p, Path(d, 'link.json'))
            self.assertEqual('symlink_refused', self.cli('hash', str(Path(d, 'link.json')), code=2)['code'])
            os.mkfifo(Path(d, 'fifo'))
            self.assertEqual('not_regular_file', self.cli('hash', str(Path(d, 'fifo')), code=2)['code'])


if __name__ == '__main__':
    unittest.main()

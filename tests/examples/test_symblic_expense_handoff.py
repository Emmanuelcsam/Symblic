"""Executable handoff example: fake construction, real native checks and durable replay."""
import copy
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from fractions import Fraction
from pathlib import Path

from symblic.kernel import grounding as G
from symblic.kernel.run import Run

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'examples'
DATA = EXAMPLES / 'expense-handoff.json'          # the example's input, shipped next to expense_handoff.py
spec = importlib.util.spec_from_file_location('expense_handoff_example', EXAMPLES / 'expense_handoff.py')
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)
BY = 'ollama:llama3.2:1b@node-f'


def fixture():
    return json.loads(DATA.read_text())


def witnesses(body=None, values=None):
    """Test-only constructor knows fixture spans. The production helper contains no answers."""
    body = body or fixture()
    values = values or ['4500', '850', '280', '140', '45', '280', '35', '8']
    answers = []
    for row, numeral in zip(body['entries'], values):
        parent = G.source_span(body['source'], row['start'], row['end'])
        source = G.source_record(row['id'], parent['quote'], body['source']['revision'])
        full = G.source_span(source, 0, len(source['text']))
        item = {'id': row['id'], 'span': full}
        catalog = G.list_contract(row['id'], source, catalog=[item], require_nonempty=True)
        field = G.field_contract(row['id'], source, labels=[row['label']], region=full,
                                 separator='\n', prefix=' ', suffix=' ' + row['currency'], currency=row['currency'])
        start = source['text'].index(numeral, len(row['label']))
        answers.extend([{'contract_sha256': catalog['sha256'], 'items': [item], 'category': row['category']},
                        {'contract_sha256': field['sha256'],
                         'label': G.source_span(source, 0, len(row['label'])),
                         'value': G.source_span(source, start, start + len(numeral))}])
    return answers


class Apps:
    def __init__(self, answers):
        self.answers, self.requests = answers, []

    def call(self, request):
        at = len(self.requests)
        self.requests.append(dict(request))
        if at >= len(self.answers):
            raise AssertionError('Unexpected additional model call')
        return {'ok': True, 'json': {'answer': copy.deepcopy(self.answers[at])}, 'model': 'fake', 'node': 'isolated'}


def execute(body=None, answers=None, retries=0, source=None):
    body = body or fixture()
    apps = Apps(witnesses(body) if answers is None else answers)
    runner = Run(source or H.PROGRAM.read_text(), inputs=H.caller_inputs(body), applicators=apps,
                 options={'by': BY, 'retries': retries, 'budget': 24000, 'max_calls': 64,
                          'effort': 'low', 'context': 'none', 'profile': 'verified', 'coercion': 'strict'})
    return runner, runner.execute(), apps


class ExpenseHandoff(unittest.TestCase):
    def test_valid_fake_completion_and_exact_rational_accounting(self):
        run, report, apps = execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        value = run.kernel.env.lookup('result').value
        self.assertEqual(value['totals'], {'claimed': Fraction(33363, 20), 'approved': Fraction(32163, 20), 'disallowed': 60})
        self.assertTrue(value['catalog_receipt']['enumeration_complete'])
        self.assertEqual([row['id'] for row in value['rows']], [f'e{i:02}' for i in range(1, 9)])
        self.assertEqual(len(apps.requests), 16)
        self.assertEqual(value['assurance']['source_truth'], 'not_established')
        for row in value['rows']:
            self.assertEqual(row['amount_receipt']['assurance']['semantic_entailment'], 'not_established')

    def test_fresh_request_contains_only_current_raw_item_not_full_trip_or_previous_rows(self):
        body = fixture()
        _, report, apps = execute(body)
        self.assertEqual(report['status'], 'done', report.get('error'))
        quotes = [body['source']['text'][r['start']:r['end']] for r in body['entries']]
        for index, request in enumerate(apps.requests):
            with self.subTest(call=index):
                prompt = request['system'] + '\n' + request['prompt']
                self.assertIn(quotes[index // 2], prompt)
                self.assertNotIn('Trip to Tokyo and San Francisco', prompt)
                self.assertNotIn('March 12:', prompt)
                for other in set(quotes) - {quotes[index // 2]}:
                    self.assertNotIn(other, prompt)

    def test_duplicate_omitted_foreign_id_category_and_replacement_contract_refuse(self):
        good = witnesses()
        variants = []
        for category in ('travel', 'entertainment'):
            bad = copy.deepcopy(good[0]); bad['category'] = category; variants.append(bad)
        bad = copy.deepcopy(good[0]); bad['items'] = []; variants.append(bad)
        bad = copy.deepcopy(good[0]); bad['items'] *= 2; variants.append(bad)
        bad = copy.deepcopy(good[0]); bad['items'][0]['id'] = 'e02'; variants.append(bad)
        bad = copy.deepcopy(good[0]); bad['contract_sha256'] = '0' * 64; variants.append(bad)
        bad = copy.deepcopy(good[0]); bad['items'][0]['span']['source_id'] = 'e02'; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad):
                _, report, apps = execute(answers=[bad])
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(apps.requests), 1)

    def test_wrong_amount_dropped_digits_sign_currency_and_extra_contract_refuse(self):
        good = witnesses()
        variants = []
        bad = copy.deepcopy(good[1]); bad['value']['quote'] = '9999'; variants.append(bad)
        bad = copy.deepcopy(good[1]); bad['value']['start'] += 1; bad['value']['quote'] = '500'; variants.append(bad)
        bad = copy.deepcopy(good[1]); bad['value']['quote'] = '-4500'; variants.append(bad)
        bad = copy.deepcopy(good[1]); bad['currency'] = 'USD'; variants.append(bad)
        bad = copy.deepcopy(good[1]); bad['contract'] = {'currency': 'USD'}; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad):
                _, report, apps = execute(answers=[good[0], bad])
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(apps.requests), 2)

    def test_complete_catalog_check_rejects_duplicate_and_omission_independently(self):
        body = fixture()
        catalog = [{'id': r['id'], 'span': G.source_span(body['source'], r['start'], r['end'])} for r in body['entries']]
        contract = G.list_contract('trip-items', body['source'], catalog=catalog, require_nonempty=True)
        for rows in (catalog[:-1], [*catalog[:-1], catalog[0]], [], [{**catalog[0], 'id': 'foreign'}, *catalog[1:]]):
            receipt = G.verify_items(body['source'], contract, {'contract_sha256': contract['sha256'], 'items': rows})
            self.assertFalse(receipt['accepted'])
            self.assertIsNot(receipt.get('enumeration_complete'), True)

    def test_repeated_hotel_quote_cannot_swap_occurrence_identity(self):
        good = witnesses()
        bad = copy.deepcopy(good[4]); bad['items'][0]['span'] = good[10]['items'][0]['span']
        _, report, apps = execute(answers=[*good[:4], bad])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 5)

    def test_caller_input_drift_duplicate_regions_and_unsupported_policies_fail_before_call(self):
        variants = []
        bad = fixture(); bad['source']['text'] += 'Changed'; variants.append(bad)
        bad = fixture(); bad['entries'][1]['id'] = bad['entries'][0]['id']; variants.append(bad)
        bad = fixture(); bad['entries'][1].update(start=bad['entries'][0]['start'], end=bad['entries'][0]['end']); variants.append(bad)
        bad = fixture(); bad['entries'][0]['currency'] = 'EUR'; variants.append(bad)
        bad = fixture(); bad['entries'][0]['category'] = 'misc'; variants.append(bad)
        bad = fixture(); bad['policy']['rates']['JPY']['denominator'] = 0; variants.append(bad)
        bad = fixture(); bad['policy']['negative_amounts'] = 'absolute'; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                H.prepare(bad, by=BY)

    def test_source_unit_negation_and_negative_policy_are_explicit_refusals(self):
        for text, label, numeral in [('Lunch 35 EUR', 'Lunch', '35'), ('Not Lunch 35 USD', 'Lunch', '35'),
                                      ('Lunch -35 USD', 'Lunch', '-35'), ('Lunch -35 USD', 'Lunch', '35')]:
            body = fixture()
            body['source'] = G.source_record('one', text)
            body['entries'] = [{'id': 'one', 'start': 0, 'end': len(text), 'label': label,
                                'day': '2026-03-12', 'category': 'meal', 'currency': 'USD'}]
            answers = witnesses(body, [numeral])
            # For negation, quote the actual exact label occurrence: overlap still cannot prove the field.
            start = text.index(label)
            answers[1]['label'] = G.source_span(G.source_record('one', text), start, start + len(label))
            _, report, apps = execute(body, answers)
            self.assertEqual(report['status'], 'failed', text)
            self.assertEqual(len(apps.requests), 2)

    def test_unicode_offsets_and_same_day_hotel_cap(self):
        body = fixture()
        text = '🚕 Taxi 45 USD\nHotel A 200 USD\nHotel B 200 USD'
        body['source'] = G.source_record('unicode', text)
        body['entries'] = []
        for i, (quote, label, cat) in enumerate([('🚕 Taxi 45 USD', '🚕 Taxi', 'travel'), ('Hotel A 200 USD', 'Hotel A', 'hotel'), ('Hotel B 200 USD', 'Hotel B', 'hotel')]):
            at = text.index(quote)
            body['entries'].append({'id': f'u{i}', 'start': at, 'end': at + len(quote), 'label': label, 'day': '2026-03-12', 'category': cat, 'currency': 'USD'})
        run, report, _ = execute(body, witnesses(body, ['45', '200', '200']))
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(run.kernel.env.lookup('result').value['totals'], {'claimed': 445, 'approved': 295, 'disallowed': 150})

    def test_weak_original_predicates_accept_wrong_duplicate_rows(self):
        fabricated = [{'id': 'duplicate', 'cat': 'travel', 'amount': 9000} for _ in range(6)] + [
            {'id': 'same-hotel', 'cat': 'hotel', 'amount': 280}, {'id': 'same-hotel', 'cat': 'hotel', 'amount': 280}]
        claimed = sum(r['amount'] for r in fabricated)
        approved = sum(min(r['amount'], 250) if r['cat'] == 'hotel' else r['amount'] for r in fabricated)
        self.assertEqual(len(fabricated), 8)
        self.assertLessEqual(approved, claimed)
        self.assertEqual(claimed - approved, 60)
        # The new acceptance path requires exact named witnesses before arithmetic.
        bad = witnesses()[0]; bad['items'][0]['id'] = 'duplicate'
        _, report, _ = execute(answers=[bad])
        self.assertEqual(report['status'], 'failed')

    def test_handoff_run_replay_and_exact_artifact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'job'
            envelope = H.prepare(fixture(), by=BY)
            H.write_job(envelope, folder)
            apps = Apps(witnesses())
            result = H.execute_job(folder, envelope['sha256'], applicators=apps)
            self.assertTrue(result['accepted'], result['report'].get('error'))
            self.assertEqual(len(apps.requests), 16)
            checked = H.execute_job(folder, envelope['sha256'], replay=True)
            self.assertTrue(checked['accepted'], checked['report'].get('error'))
            self.assertEqual(checked['report']['calls'], 0)
            self.assertEqual(checked['artifact']['sha256'], result['artifact']['sha256'])
            (folder / 'artifact.canon').write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError, 'Replay output'):
                H.execute_job(folder, envelope['sha256'], replay=True)

    def test_interrupted_native_progress_resumes_under_one_shared_native_budget(self):
        body = fixture()
        body['entries'] = body['entries'][:2]
        answers = witnesses(body)
        stop = threading.Event()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'job'
            envelope = H.prepare(body, by=BY)
            H.write_job(envelope, folder)

            class InterruptedApps(Apps):
                def call(self, request):
                    response = super().call(request)
                    ledger = json.loads((folder / 'native/model-budget.json').read_text())
                    used = ledger['sources'][H.sha(envelope['source'].encode())]['calls']
                    if used != len(self.requests):
                        raise AssertionError('Native budget must reserve before host dispatch')
                    if len(self.requests) == 2:
                        stop.set()
                    return response

            first = InterruptedApps(answers[:2])
            interrupted = H.execute_job(folder, envelope['sha256'], applicators=first, stop=stop)
            self.assertFalse(interrupted['accepted'])
            self.assertEqual(interrupted['report']['status'], 'stopped')
            self.assertFalse((folder / 'artifact.canon').exists())
            remaining = Apps(answers[2:])
            done = H.execute_job(folder, envelope['sha256'], applicators=remaining)
            self.assertTrue(done['accepted'], done['report'].get('error'))
            self.assertEqual(len(first.requests) + len(remaining.requests), 4)
            self.assertEqual(done['report']['model_budget']['used'], 4)
            self.assertEqual(done['report']['model_budget']['scope'], 'run_source')
            self.assertGreaterEqual(done['report']['cached'], 2)

    def test_opted_in_repair_stays_in_native_shared_call_and_repair_budgets(self):
        body = fixture()
        body['entries'] = body['entries'][:1]
        good = witnesses(body)
        wrong = copy.deepcopy(good[0])
        wrong['category'] = 'travel'
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'job'
            envelope = H.prepare(body, by=BY, retries=1)
            H.write_job(envelope, folder)
            apps = Apps([wrong, *good])
            done = H.execute_job(folder, envelope['sha256'], applicators=apps)
            self.assertTrue(done['accepted'], done['report'].get('error'))
            self.assertEqual(len(apps.requests), 3)
            self.assertEqual(done['report']['model_budget']['used'], 3)
            self.assertEqual(done['report']['model_budget']['repairs_used'], 1)
            self.assertEqual(done['charged_dispatch_ceiling_across_resumes'], 4)

    def test_native_exhausted_budget_refuses_before_host_dispatch_and_cloud_not_authorized(self):
        with self.assertRaises(ValueError):
            H.prepare(fixture(), by='claude:haiku')
        body = fixture()
        body['entries'] = body['entries'][:1]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'job'
            envelope = H.prepare(body, by=BY)
            H.write_job(envelope, folder)
            native = folder / 'native'
            native.mkdir()
            (native / 'model-budget.json').write_text(json.dumps({'version': 1, 'sources': {
                H.sha(envelope['source'].encode()): {'calls': 2, 'repairs': 0}}}))
            apps = Apps([])
            result = H.execute_job(folder, envelope['sha256'], applicators=apps)
            self.assertFalse(result['accepted'])
            self.assertEqual(apps.requests, [])
            self.assertEqual(result['report']['model_budget']['used'], 2)
            self.assertFalse(envelope['options']['auto_route']['allow_cloud'])
            self.assertEqual(envelope['options']['auto_route']['candidates'], [BY])

    def test_cli_prepare_and_offline_check_return_one_json_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'job'
            out = io.StringIO()
            with redirect_stdout(out):
                code = H.main(['prepare', str(DATA), '--dir', str(folder),
                               '--by', BY, '--agent-json'])
            result = json.loads(out.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result['model_calls'], 0)
            self.assertEqual((folder / 'handoff.json').stat().st_mode & 0o777, 0o600)
            out = io.StringIO()
            with redirect_stdout(out):
                code = H.main(['check', str(folder), '--expect', result['handoff_sha256'], '--agent-json'])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(out.getvalue())['accepted'])

    def test_handoff_mutation_and_missing_replay_refuse_without_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'job'
            envelope = H.prepare(fixture(), by=BY)
            H.write_job(envelope, folder)
            result = H.execute_job(folder, envelope['sha256'], replay=True)
            self.assertFalse(result['accepted'])
            self.assertEqual(result['report']['calls'], 0)
            bad = copy.deepcopy(envelope); bad['options']['by'] = 'claude:haiku'
            (folder / 'handoff.json').write_bytes(H.raw_json(bad))
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                H.execute_job(folder, envelope['sha256'], applicators=Apps([]))


if __name__ == '__main__':
    unittest.main()

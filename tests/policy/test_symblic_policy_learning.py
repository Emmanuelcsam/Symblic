"""Exact independent scoring and adversarial isolation/accounting checks."""
import contextlib
import copy
import io
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.policy import learning as P


def h(value):
    return P.digest(value)


def case(label):
    return {'case_hash': h(['case', label]), 'family_hash': h(['family', label]),
            'input_hash': h(['input', label]), 'exposure_hashes': [h(['exposure', label])]}


def fixture():
    policies = [{'route': 'one', 'nodes': [1]}, {'route': 'two', 'nodes': [2]}]
    candidates = [{'sha256': h(v), 'policy': v} for v in policies]
    plan = {'version': 1, 'candidates': candidates, 'baseline': candidates[0]['sha256'],
            'cases': [case('train0'), case('train1')],
            'budget': {'max_calls': 4, 'max_cost_units': 20},
            'objective': {'max_score': 10, 'score_weight': 10, 'call_weight': 1, 'cost_weight': 1,
                          'unknown_cost': 'budget', 'tie_break': 'policy_sha256_ascending',
                          'min_heldout_gain': 1}}
    records = [row(c['sha256'], a['case_hash'], 4 + i, calls=2, cost=3)
               for i, c in enumerate(candidates) for a in plan['cases']]
    return plan, records


def row(candidate, case_hash, score, status='success', calls=1, cost=1):
    return {'candidate': candidate, 'case': case_hash, 'status': status, 'score': score,
            'attempts': [{'calls': calls, 'cost_units': cost}]}


def select(plan, records):
    return P.select(plan, records, expected_plan_hash=h(plan), expected_records_hash=h(records))


def heldout(plan, records):
    chosen = select(plan, records)
    hp = {'version': 1, 'training_plan_hash': h(plan), 'cases': [case('held0'), case('held1')]}
    hr = [row(candidate, c['case_hash'], 9 if candidate == chosen['selected']['sha256'] else 2)
          for candidate in {chosen['selected']['sha256'], plan['baseline']} for c in hp['cases']]
    pins = {'training_plan': h(plan), 'training_records': h(records), 'selection': h(chosen),
            'heldout_plan': h(hp), 'heldout_records': h(hr)}
    return chosen, hp, hr, pins


class SelectionTests(unittest.TestCase):
    def test_independent_exhaustive_ranking(self):
        plan, _ = fixture()
        a, b = [c['sha256'] for c in plan['candidates']]
        # An independent direct objective, over all two-case score allocations.
        for scores in itertools.product(range(3), repeat=4):
            records = [row(candidate, c['case_hash'], scores[i * 2 + j], calls=1 + i, cost=j + 1)
                       for i, candidate in enumerate((a, b)) for j, c in enumerate(plan['cases'])]
            totals = {a: 10 * (scores[0] + scores[1]) - 2 - 3,
                      b: 10 * (scores[2] + scores[3]) - 4 - 3}
            expected = min(totals, key=lambda key: (-totals[key], key))
            result = select(plan, records)
            self.assertEqual(result['selected']['sha256'], expected)
            self.assertEqual(result['receipt']['summaries'][a]['utility_sum'], totals[a])
            self.assertEqual(result['receipt']['summaries'][b]['utility_sum'], totals[b])

    def test_missing_failed_refused_denominators_and_all_attempts(self):
        plan, _ = fixture()
        a, b = [c['sha256'] for c in plan['candidates']]
        x, y = [c['case_hash'] for c in plan['cases']]
        records = [row(a, x, 10), row(b, x, 0, 'failed'), row(b, y, 0, 'refused', calls=0, cost=0)]
        records[0]['attempts'] = [{'calls': 1, 'cost_units': 3}, {'calls': 2, 'cost_units': 4}]
        result = select(plan, records)
        stats = result['receipt']['summaries']
        self.assertEqual(stats[a]['denominator'], 2)
        self.assertEqual(stats[a]['statuses']['missing'], 1)
        self.assertEqual(stats[a]['observed_calls'], 3)
        self.assertEqual(stats[a]['charged_calls'], 7)
        self.assertEqual(stats[a]['known_cost_units'], 7)
        self.assertEqual(stats[a]['charged_cost_units'], 27)
        self.assertEqual(stats[a]['unknown_cost_items'], 1)
        self.assertEqual(stats[b]['statuses']['failed'], 1)
        self.assertEqual(stats[b]['statuses']['refused'], 1)
        self.assertEqual(stats[b]['denominator'], 2)
        # No success-only mean: the candidate with one high score loses to two good scores.
        records = [row(a, x, 10), row(b, x, 7), row(b, y, 7)]
        self.assertEqual(select(plan, records)['selected']['sha256'], b)

    def test_unknown_cost_is_not_free_and_rejection_is_explicit(self):
        plan, records = fixture()
        a, b = [c['sha256'] for c in plan['candidates']]
        for r in records:
            r['score'] = 5
            if r['candidate'] == a:
                r['attempts'] = [{'calls': 1, 'cost_units': 2}, {'calls': 1, 'cost_units': None}]
        result = select(plan, records)
        s = result['receipt']['summaries'][a]
        self.assertEqual(s['known_cost_units'], 4)
        self.assertEqual(s['unknown_cost_items'], 2)
        self.assertEqual(s['charged_cost_units'], 40)
        self.assertEqual(result['selected']['sha256'], b)
        plan['objective']['unknown_cost'] = 'reject'
        result = select(plan, records)
        self.assertFalse(result['receipt']['summaries'][a]['eligible'])
        self.assertEqual(result['selected']['sha256'], b)
        with self.assertRaisesRegex(P.PolicyError, 'no_eligible_candidate'):
            select(plan, [])

    def test_tie_break_ignores_record_case_candidate_order(self):
        plan, records = fixture()
        for r in records:
            r['score'] = 5
        expected = min(c['sha256'] for c in plan['candidates'])
        result = select(plan, records)
        self.assertEqual(result['selected']['sha256'], expected)
        plan['candidates'].reverse()
        plan['cases'].reverse()
        records.reverse()
        self.assertEqual(select(plan, records)['selected'], result['selected'])
        # Hashes preserve the supplied history/order even when the ranking is unchanged.
        self.assertNotEqual(select(plan, records)['receipt']['training_records_hash'],
                            result['receipt']['training_records_hash'])

    def test_unequal_or_exceeded_budgets_are_rejected(self):
        plan, records = fixture()
        for field, value in [('calls', 5), ('cost_units', 21)]:
            bad = copy.deepcopy(records)
            bad[0]['attempts'][0][field] = value
            with self.assertRaisesRegex(P.PolicyError, 'budget_exceeded'):
                select(plan, bad)
        bad = copy.deepcopy(records)
        bad[0]['budget'] = {'max_calls': 50}
        with self.assertRaisesRegex(P.PolicyError, 'schema'):
            select(plan, bad)
        plan['candidates'][0]['budget'] = {'max_calls': 50}
        with self.assertRaisesRegex(P.PolicyError, 'schema'):
            select(plan, records)

    def test_pins_changed_records_and_immutable_selected_payload(self):
        plan, records = fixture()
        ph, rh = h(plan), h(records)
        result = select(plan, records)
        frozen = result['selected']['policy_json']
        self.assertEqual(h(json.loads(frozen)), result['selected']['sha256'])
        records[0]['score'] += 1
        with self.assertRaisesRegex(P.PolicyError, 'pin_mismatch'):
            P.select(plan, records, expected_plan_hash=ph, expected_records_hash=rh)
        plan['candidates'][1]['policy']['nodes'].append(3)
        self.assertEqual(result['selected']['policy_json'], frozen)
        with self.assertRaisesRegex(P.PolicyError, 'pin_mismatch'):
            select(plan, records)

    def test_no_metadata_or_heldout_records_in_selector(self):
        plan, records = fixture()
        bad = copy.deepcopy(plan)
        bad['heldout_cases'] = [case('held')]
        with self.assertRaisesRegex(P.PolicyError, 'schema'):
            select(bad, records)
        bad_records = copy.deepcopy(records)
        bad_records[0]['case'] = case('held')['case_hash']
        with self.assertRaisesRegex(P.PolicyError, 'unassigned_record'):
            select(plan, bad_records)
        bad_records = copy.deepcopy(records)
        bad_records[0]['heldout_score'] = 100
        with self.assertRaisesRegex(P.PolicyError, 'schema'):
            select(plan, bad_records)

    def test_large_exact_aggregates_are_hashable(self):
        plan, records = fixture()
        plan['objective']['max_score'] = P.MAX_INT
        plan['objective']['score_weight'] = P.MAX_INT
        for r in records:
            r['score'] = P.MAX_INT
        result = select(plan, records)
        self.assertEqual(len(h(result)), 64)


class HeldoutTests(unittest.TestCase):
    def test_frozen_improvement_and_failure_not_reselection(self):
        plan, records = fixture()
        selected, hp, hr, pins = heldout(plan, records)
        result = P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        self.assertTrue(result['improvement'])
        self.assertEqual(result['confidence'], 'not_established')
        self.assertEqual(result['measurement_status'], 'host_declared_not_verified')
        for row_ in hr:
            row_['score'] = 0 if row_['candidate'] == selected['selected']['sha256'] else 10
        pins['heldout_records'] = h(hr)
        failed = P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        self.assertFalse(failed['improvement'])
        self.assertEqual(failed['selected_hash'], result['selected_hash'])
        self.assertEqual(select(plan, records), selected)

    def test_missing_unknown_and_same_baseline_cannot_claim_improvement(self):
        plan, records = fixture()
        selected, hp, hr, pins = heldout(plan, records)
        for changed in (hr[:-1], [dict(r, attempts=[{'calls': 1, 'cost_units': None}]) for r in hr]):
            pins['heldout_records'] = h(changed)
            result = P.evaluate_heldout(plan, records, selected, hp, changed, pins=pins)
            self.assertFalse(result['improvement'])
            self.assertFalse(result['complete_accounting'])
        plan['baseline'] = selected['selected']['sha256']
        selected, hp, hr, pins = heldout(plan, records)
        result = P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        self.assertFalse(result['improvement'])
        self.assertEqual(result['utility_gain']['numerator'], 0)

    def test_predeclared_gain_threshold_and_rejected_heldout_choices(self):
        plan, records = fixture()
        plan['objective']['min_heldout_gain'] = 1000
        selected, hp, hr, pins = heldout(plan, records)
        result = P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        self.assertGreater(result['utility_gain']['numerator'], 0)
        self.assertFalse(result['improvement'])
        hr[0]['candidate'] = h('undeclared heldout choice')
        pins['heldout_records'] = h(hr)
        with self.assertRaisesRegex(P.PolicyError, 'unassigned_record'):
            P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        selected, hp, hr, pins = heldout(plan, records)
        hp['cases'][0]['family_hash'] = plan['cases'][0]['family_hash']
        pins['heldout_plan'] = h(hp)
        with self.assertRaisesRegex(P.PolicyError, 'split_overlap_family_hash'):
            P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)

    def test_each_split_overlap_and_cross_exposure(self):
        train, held = [case('train')], [case('held')]
        for field in ('case_hash', 'family_hash', 'input_hash', 'exposure_hashes'):
            bad = copy.deepcopy(held)
            bad[0][field] = train[0][field]
            with self.assertRaisesRegex(P.PolicyError, 'split_overlap'):
                P.validate_split(train, bad)
        bad = copy.deepcopy(held)
        bad[0]['input_hash'] = train[0]['exposure_hashes'][0]
        with self.assertRaisesRegex(P.PolicyError, 'split_overlap_exposure'):
            P.validate_split(train, bad)
        bad = copy.deepcopy(held)
        bad[0]['exposure_hashes'] = [train[0]['input_hash']]
        with self.assertRaisesRegex(P.PolicyError, 'split_overlap_exposure'):
            P.validate_split(train, bad)

    def test_replayed_choice_cannot_be_replaced_even_with_new_pin(self):
        plan, records = fixture()
        selected, hp, hr, pins = heldout(plan, records)
        fake = copy.deepcopy(selected)
        fake['selected']['sha256'] = plan['baseline']
        pins['selection'] = h(fake)
        with self.assertRaisesRegex(P.PolicyError, 'selection_mismatch'):
            P.evaluate_heldout(plan, records, fake, hp, hr, pins=pins)
        selected, hp, hr, pins = heldout(plan, records)
        hr[0]['score'] += 1
        with self.assertRaisesRegex(P.PolicyError, 'pin_mismatch'):
            P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)

    def test_heldout_changes_never_enter_selector_arguments(self):
        plan, records = fixture()
        selected, hp, hr, pins = heldout(plan, records)
        original = P.select
        calls = []
        def spy(*args, **kwargs):
            calls.append(copy.deepcopy((args, kwargs)))
            return original(*args, **kwargs)
        with patch.object(P, 'select', side_effect=spy):
            P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
            hp['cases'].reverse()
            hr.reverse()
            pins['heldout_plan'], pins['heldout_records'] = h(hp), h(hr)
            P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        self.assertEqual(calls[0], calls[1])


class AdversarialTests(unittest.TestCase):
    def test_schema_cycles_floats_duplicate_unassigned_bad_scores(self):
        plan, records = fixture()
        for value in (1.0, float('nan'), float('inf')):
            with self.assertRaisesRegex(P.PolicyError, 'json_type'):
                h({'v': value})
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(P.PolicyError, 'cycle'):
            h(cyclic)
        deep = []
        for _ in range(100):
            deep = [deep]
        with self.assertRaisesRegex(P.PolicyError, 'structure_limit'):
            h(deep)
        for mutation in ('duplicate', 'unassigned', 'failure_score', 'bool_calls', 'extra_attempt'):
            bad = copy.deepcopy(records)
            if mutation == 'duplicate':
                bad[-1] = copy.deepcopy(bad[0])
            elif mutation == 'unassigned':
                bad[0]['candidate'] = h('not a candidate')
            elif mutation == 'failure_score':
                bad[0]['status'] = 'failed'
            elif mutation == 'bool_calls':
                bad[0]['attempts'][0]['calls'] = True
            else:
                bad[0]['attempts'][0]['ignored_cost'] = 9
            with self.subTest(mutation=mutation), self.assertRaises(P.PolicyError):
                select(plan, bad)
        bad_plan = copy.deepcopy(plan)
        bad_plan['version'] = True
        with self.assertRaisesRegex(P.PolicyError, 'version'):
            select(bad_plan, records)
        bad_plan = copy.deepcopy(plan)
        bad_plan['cases'] *= 2
        with self.assertRaisesRegex(P.PolicyError, 'duplicate_case'):
            select(bad_plan, records)

    def test_assignment_and_attempt_limits(self):
        plan, records = fixture()
        with patch.object(P, 'MAX_ASSIGNMENTS', 3), self.assertRaisesRegex(P.PolicyError, 'assignment_limit'):
            select(plan, records)
        records[0]['attempts'] = [{'calls': 0, 'cost_units': 0}] * (P.MAX_ATTEMPTS + 1)
        with self.assertRaisesRegex(P.PolicyError, 'attempts'):
            select(plan, records)

    def test_frozen_heldout_cli_journey(self):
        plan, records = fixture()
        selected, hp, hr, pins = heldout(plan, records)
        objects = {'training-plan': plan, 'training-records': records, 'selection': selected,
                   'heldout-plan': hp, 'heldout-records': hr, 'pins': pins}
        with tempfile.TemporaryDirectory() as directory:
            argv = ['evaluate']
            for name, value in objects.items():
                path = Path(directory) / (name + '.json')
                path.write_text(json.dumps(value), encoding='utf-8')
                argv.extend(['--' + name, str(path)])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(P.main(argv), 0)
            result = json.loads(out.getvalue())
            self.assertTrue(result['improvement'])
            self.assertEqual(result['pins'], pins)
            for name, value in objects.items():
                self.assertEqual(json.loads((Path(directory) / (name + '.json')).read_text()), value)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(P.main(['hash', str(Path(directory) / 'selection.json')]), 0)
            self.assertEqual(json.loads(out.getvalue())['sha256'], pins['selection'])

    def test_cli_files_exact_output_and_invalid_json(self):
        plan, records = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {'plan': plan, 'records': records,
                    'pins': {'training_plan': h(plan), 'training_records': h(records)}}
            for name, value in data.items():
                (root / name).write_text(json.dumps(value), encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = P.main(['select', '--plan', str(root / 'plan'), '--records', str(root / 'records'),
                               '--pins', str(root / 'pins')])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue()), select(plan, records))
            self.assertEqual(json.loads((root / 'records').read_text()), records)
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1.0}', '[1e999]', '"\\ud800"'):
                (root / 'bad').write_text(text)
                with self.assertRaises(P.PolicyError):
                    P.load_json(root / 'bad')
            with self.assertRaisesRegex(P.PolicyError, 'input_file'):
                P.load_json(root)


if __name__ == '__main__':
    unittest.main()

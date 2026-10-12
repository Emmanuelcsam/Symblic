"""Independent policy-accounting and cross-role leakage counterexamples."""
import copy
import itertools
import unittest
from fractions import Fraction

from symblic.policy import learning as P
from tests.policy.test_symblic_policy_learning import case, fixture, h, heldout, row, select


class SplitAudit(unittest.TestCase):
    def test_every_declared_resource_role_is_disjoint_across_splits(self):
        roles = ('case_hash', 'family_hash', 'input_hash', 'exposure_hashes')
        for train_role, held_role in itertools.product(roles, repeat=2):
            with self.subTest(train_role=train_role, held_role=held_role):
                train, held = [case('train')], [case('held')]
                resource = held[0][held_role]
                resource = resource[0] if held_role == 'exposure_hashes' else resource
                train[0][train_role] = [resource] if train_role == 'exposure_hashes' else resource
                with self.assertRaisesRegex(P.PolicyError, 'split_overlap'):
                    P.validate_split(train, held)

    def test_training_exposure_of_complete_heldout_case_blocks_comparison(self):
        plan, records = fixture()
        selected, hp, hr, pins = heldout(plan, records)
        plan['cases'][0]['exposure_hashes'].append(hp['cases'][0]['case_hash'])
        selected = select(plan, records)
        hp['training_plan_hash'] = h(plan)
        pins.update(training_plan=h(plan), selection=h(selected), heldout_plan=h(hp))
        with self.assertRaisesRegex(P.PolicyError, 'split_overlap'):
            P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)


class AccountingAudit(unittest.TestCase):
    def test_pure_deterministic_experiment_can_forbid_all_model_calls(self):
        plan, records = fixture()
        plan['budget']['max_calls'] = 0
        for record in records:
            record['attempts'] = [{'calls': 0, 'cost_units': 3}]
        result = select(plan, records)
        self.assertTrue(all(summary['observed_calls'] == 0 for summary in result['receipt']['summaries'].values()))
        records[0]['attempts'][0]['calls'] = 1
        with self.assertRaisesRegex(P.PolicyError, 'budget_exceeded'):
            select(plan, records)

    def test_exact_mean_gain_boundary_never_rounds_up(self):
        plan, records = fixture()
        plan['objective'].update(score_weight=1, call_weight=0, cost_weight=0, min_heldout_gain=1)
        chosen = select(plan, records)
        cases = [case('held-' + str(i)) for i in range(3)]
        hp = {'version': 1, 'training_plan_hash': h(plan), 'cases': cases}
        selected_hash = chosen['selected']['sha256']
        for score_vector, expected in (((1, 1, 0), False), ((1, 1, 1), True)):
            with self.subTest(scores=score_vector):
                hr = [row(candidate, item['case_hash'], score_vector[i] if candidate == selected_hash else 0)
                      for candidate in (selected_hash, plan['baseline']) for i, item in enumerate(cases)]
                pins = {'training_plan': h(plan), 'training_records': h(records), 'selection': h(chosen),
                        'heldout_plan': h(hp), 'heldout_records': h(hr)}
                result = P.evaluate_heldout(plan, records, chosen, hp, hr, pins=pins)
                self.assertEqual(result['utility_gain'], {'numerator': sum(score_vector), 'denominator': 3})
                self.assertEqual(result['improvement'], expected)

    def test_multiple_unknown_attempts_charge_one_total_cap_and_block_heldout_claim(self):
        plan, records = fixture()
        for record in records:
            record['attempts'] = [{'calls': 1, 'cost_units': 3}, {'calls': 1, 'cost_units': None},
                                  {'calls': 1, 'cost_units': None}]
        selected, hp, hr, pins = heldout(plan, records)
        for summary in selected['receipt']['summaries'].values():
            self.assertEqual(summary['known_cost_units'], 6)
            self.assertEqual(summary['unknown_cost_items'], 4)
            self.assertEqual(summary['charged_cost_units'], 2 * plan['budget']['max_cost_units'])
        for record in hr:
            record['attempts'] = [{'calls': 0, 'cost_units': None}]
        plan['budget']['max_cost_units'] = 0
        # Re-freeze a distinct experiment before constructing its heldout comparison.
        for record in records:
            record['attempts'] = [{'calls': 0, 'cost_units': 0}]
        selected = select(plan, records)
        hp['training_plan_hash'] = h(plan)
        pins.update(training_plan=h(plan), training_records=h(records), selection=h(selected),
                    heldout_plan=h(hp), heldout_records=h(hr))
        result = P.evaluate_heldout(plan, records, selected, hp, hr, pins=pins)
        self.assertFalse(result['complete_accounting'])
        self.assertFalse(result['improvement'])

    def test_per_assignment_cap_and_aggregate_receipt_are_distinct(self):
        plan, records = fixture()
        for record in records:
            record['attempts'] = [{'calls': plan['budget']['max_calls'],
                                   'cost_units': plan['budget']['max_cost_units']}]
        selected = select(plan, records)
        for summary in selected['receipt']['summaries'].values():
            self.assertEqual(summary['charged_calls'], 2 * plan['budget']['max_calls'])
            self.assertEqual(summary['charged_cost_units'], 2 * plan['budget']['max_cost_units'])
        over = copy.deepcopy(records)
        over[0]['attempts'].append({'calls': 1, 'cost_units': 0})
        with self.assertRaisesRegex(P.PolicyError, 'budget_exceeded'):
            select(plan, over)

    def test_exact_extreme_signed_utility_matches_independent_integer_formula(self):
        plan, records = fixture()
        bound = P.MAX_INT
        plan['budget'] = {'max_calls': bound, 'max_cost_units': bound}
        plan['objective'].update(max_score=bound, score_weight=bound, call_weight=bound, cost_weight=bound)
        for index, record in enumerate(records):
            record['score'] = bound - index
            record['attempts'] = [{'calls': bound - index, 'cost_units': bound // 2},
                                  {'calls': 0, 'cost_units': bound - bound // 2}]
        selected = select(plan, records)
        for candidate in plan['candidates']:
            assigned = [record for record in records if record['candidate'] == candidate['sha256']]
            expected = sum(bound * record['score'] - bound * sum(a['calls'] for a in record['attempts'])
                           - bound * sum(a['cost_units'] for a in record['attempts']) for record in assigned)
            actual = selected['receipt']['summaries'][candidate['sha256']]
            self.assertEqual(actual['utility_sum'], expected)
            self.assertEqual(Fraction(actual['utility_sum'], actual['denominator']), Fraction(expected, 2))
        self.assertEqual(len(P.digest(selected)), 64)

    def test_refused_and_missing_cases_do_not_disappear_even_with_zero_cost_weights(self):
        plan, _ = fixture()
        plan['objective'].update(score_weight=1, call_weight=0, cost_weight=0)
        a, b = [candidate['sha256'] for candidate in plan['candidates']]
        x, y = [item['case_hash'] for item in plan['cases']]
        records = [row(a, x, 10), row(b, x, 6), row(b, y, 6)]
        chosen = select(plan, records)
        self.assertEqual(chosen['selected']['sha256'], b)
        self.assertEqual(chosen['receipt']['summaries'][a]['statuses']['missing'], 1)
        records.append(row(a, y, 0, status='refused', calls=0, cost=0))
        updated = select(plan, records)
        self.assertEqual(updated['selected']['sha256'], b)
        self.assertEqual(updated['receipt']['summaries'][a]['denominator'], 2)
        self.assertEqual(updated['receipt']['summaries'][a]['statuses']['refused'], 1)


if __name__ == '__main__':
    unittest.main()

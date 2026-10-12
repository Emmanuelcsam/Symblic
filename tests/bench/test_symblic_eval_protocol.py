"""Adversarial evaluation protocol checks: synthetic data, no provider or store."""

import copy
import unittest

from symblic.bench import eval_protocol as E


def arm(name='direct', **changes):
    controls = {
        'model': {'primary': ['small'], 'fallback': ['large'], 'stronger_fallback': ['large'],
                  'settings': {'temperature': 0, 'seed': 7}},
        'information': {'task_spec': 'fixture-v1', 'examples': []},
        'budget': {'provider_calls': 4, 'output_tokens': 1024},
        'feedback': {'policy': 'same-failure-predicate-only', 'gold_visible': False},
        'validator': {'id': 'fixture-exact-v1', 'oracle': 'heldout-evaluator-only'},
    }
    controls.update(changes)
    return E.make_arm(name, name + '-treatment', **controls)


def case(index=0, **changes):
    row = {'id': f'case-{index}', 'family': f'family-{index}', 'split': 'heldout',
           'input': {'question': f'Fixture {index}: answer eight.'},
           'rubric': {'mode': 'typed_json', 'expected': 8}}
    row.update(changes)
    return row


def attempt(answer=8, **changes):
    row = {'model': 'small', 'role': 'primary', 'status': 'answered', 'answer': answer,
           'encoding': 'json_value', 'contract_accept': True, 'feedback_exposed': False, 'usage': {}}
    row.update(changes)
    if row['status'] != 'answered':
        row.pop('answer', None)
        row.pop('encoding', None)
        row['contract_accept'] = None
    return row


class ExactScoring(unittest.TestCase):
    def test_numbers_are_exact_values_not_tokens(self):
        rubric = {'mode': 'typed_json', 'expected': 8}
        self.assertTrue(E.grade(rubric, '8', 'json_text')['correct'])
        for raw in ('The answer is not 8; it is 9.', '8 or 9', 'ANSWER: 8', '18', '"8"', '8.0', 'true'):
            with self.subTest(raw=raw):
                self.assertIsNot(E.grade(rubric, raw, 'json_text')['correct'], True)
        prose = E.grade(rubric, 'The answer is not 8; it is 9.', 'text')
        self.assertEqual(prose['status'], 'ungradable')
        self.assertIsNone(prose['correct'])

    def test_entity_associations_and_extra_conflicts_matter(self):
        rubric = {'mode': 'typed_json', 'expected': {'element': 'oxygen', 'protons': 8}}
        for value in ({'element': 'oxygen', 'protons': 7},
                      {'element': 'nitrogen', 'protons': 8},
                      {'element': 'oxygen', 'protons': 8, 'but': 'actually nitrogen'},
                      {'element': 'oxygen', 'protons': '8'}):
            self.assertFalse(E.grade(rubric, value)['correct'])
        value = E.grade(rubric, 'oxygen has 7 protons; nitrogen has 8.', 'text')
        self.assertEqual(value['status'], 'ungradable')
        self.assertTrue(E.grade(rubric, {'protons': 8, 'element': 'oxygen'})['correct'])

    def test_nested_json_never_coerces_bool_integer_float_or_order(self):
        rubric = {'mode': 'typed_json', 'expected': {'items': [1, False, None]}}
        for value in ({'items': [True, False, None]}, {'items': [1.0, False, None]},
                      {'items': [1, 0, None]}, {'items': [None, False, 1]}):
            self.assertFalse(E.grade(rubric, value)['correct'])
        self.assertTrue(E.grade(rubric, {'items': [1, False, None]})['correct'])

    def test_duplicate_fields_nonfinite_and_fenced_json_are_malformed(self):
        rubric = {'mode': 'typed_json', 'expected': {'total': 8}}
        for raw in ('{"total":9,"total":8}', '{"total":NaN}', '{"total":Infinity}',
                    '```json\n{"total":8}\n```', '{"total":8} trailing', '[] []'):
            with self.subTest(raw=raw):
                result = E.grade(rubric, raw, 'json_text')
                self.assertEqual(result['status'], 'malformed')
                self.assertIsNone(result['correct'])

    def test_explicit_exact_text_never_matches_substrings(self):
        rubric = {'mode': 'exact_text', 'expected': '8'}
        self.assertTrue(E.grade(rubric, '8', 'text')['correct'])
        for raw in ('18', 'not 8', '8 or 9', '8.', ' 8 ', 'The answer is 8.'):
            self.assertFalse(E.grade(rubric, raw, 'text')['correct'])
        self.assertEqual(E.grade(rubric, 8)['status'], 'ungradable')

    def test_text_normalization_is_declared_and_limited(self):
        rubric = {'mode': 'exact_text', 'expected': 'Oxygen', 'normalization': 'outer_whitespace'}
        self.assertTrue(E.grade(rubric, ' Oxygen\n', 'text')['correct'])
        self.assertFalse(E.grade(rubric, 'oxygen', 'text')['correct'])
        with self.assertRaises(E.ProtocolError):
            E.grade({**rubric, 'normalization': 'fuzzy'}, 'Oxygen', 'text')
        with self.assertRaises(E.ProtocolError):
            E.grade({'mode': 'typed_json', 'expected': 8, 'normalization': 'none'}, 8)

    def test_invalid_gold_fails_protocol_not_model(self):
        for rubric in ({'mode': 'semantic', 'expected': 8}, {'mode': 'exact_text', 'expected': 8},
                       {'mode': 'typed_json', 'expected': float('nan')}):
            with self.assertRaises(E.ProtocolError):
                E.grade(rubric, 8)


class MatchingAndLeakage(unittest.TestCase):
    def test_intentional_treatment_difference_with_identical_controls(self):
        left, right = arm('direct'), arm('decomposed')
        self.assertEqual(left['matched_controls_sha256'], right['matched_controls_sha256'])
        self.assertTrue(E.compare_arms([left, right])['matched'])

    def test_every_control_axis_is_detected_independently(self):
        first = arm('one')
        for axis in E.AXES:
            replacement = copy.deepcopy(first['controls'][axis])
            if axis == 'model':
                replacement['settings']['seed'] = 9
            else:
                replacement['changed'] = 'yes'
            second = arm('two', **{axis: replacement})
            result = E.compare_arms([first, second])
            self.assertFalse(result['matched'])
            self.assertEqual(result['mismatched_axes'], [axis])

    def test_fingerprint_tampering_and_unbounded_call_budget_fail(self):
        changed = arm()
        changed['controls']['feedback']['gold_visible'] = True
        with self.assertRaises(E.ProtocolError):
            E.compare_arms([changed, arm('other')])
        for bad in (0, -1, True, None, 1.5):
            with self.assertRaises(E.ProtocolError):
                arm(budget={'provider_calls': bad})

    def test_family_and_identical_inputs_cannot_cross_splits(self):
        datasets = [
            [case(0, split='dev', family='shared'), case(1, family='shared')],
            [case(0, split='dev'), case(1, input=case(0)['input'])],
        ]
        for data, expected in zip(datasets, ('family_cross_split', 'input_cross_split')):
            self.assertIn(expected, [i['kind'] for i in E.leakage_report(data)['issues']])
            with self.assertRaises(E.ProtocolError):
                E.make_plan(data, [arm()])

    def test_same_family_within_one_split_is_retained_as_dependent(self):
        plan = E.make_plan([case(0, family='shared'), case(1, family='shared')], [arm()])
        report = E.summarize(plan, [])
        self.assertEqual(report['groups'][0]['families'], {'shared': {'assigned': 2, 'correct': 0}})

    def test_exact_heldout_exposures_and_gold_repair_are_detected(self):
        cases = [case(0), case(1, split='dev')]
        for exposure in (
            {'purpose': 'train', 'content': 'input', 'case_id': 'case-0'},
            {'purpose': 'tune', 'content': 'input', 'family': 'family-0'},
            {'purpose': 'repair', 'content': 'answer', 'input_sha256': E.digest(cases[0]['input'])},
            {'purpose': 'prompt', 'content': 'input', 'case_id': 'case-0', 'target_case_id': 'case-1'},
        ):
            report = E.leakage_report(cases, [exposure])
            self.assertFalse(report['clean'])
            self.assertIn('heldout_exposure', [i['kind'] for i in report['issues']])
        report = E.leakage_report(cases, [{'purpose': 'repair', 'content': 'answer', 'case_id': 'case-1'}])
        self.assertEqual(report['issues'][0]['kind'], 'oracle_exposure')

    def test_self_input_and_grading_gold_allowed_but_not_sent_by_public_case(self):
        cases = [case()]
        exposures = [{'purpose': 'prompt', 'content': 'input', 'case_id': 'case-0', 'target_case_id': 'case-0'},
                     {'purpose': 'score', 'content': 'answer', 'case_id': 'case-0'}]
        self.assertTrue(E.leakage_report(cases, exposures)['clean'])
        self.assertEqual(E.public_case(cases[0]), cases[0]['input'])
        public = E.public_case(cases[0])
        public['question'] = 'mutated'
        self.assertNotEqual(public, cases[0]['input'])
        plan = E.make_plan(cases, [arm()], exposures=(x for x in exposures))
        self.assertEqual(plan['exposures'], exposures)
        self.assertEqual(E.summarize(plan, [])['assigned'], 1)

    def test_unknown_exposure_reference_is_not_clean(self):
        result = E.leakage_report([case()], [{'purpose': 'train', 'content': 'input', 'case_id': 'missing'}])
        self.assertFalse(result['clean'])
        self.assertEqual(result['issues'][0]['kind'], 'unresolved_exposure')


class AssignedDenominators(unittest.TestCase):
    def setUp(self):
        self.plan = E.make_plan([case(i) for i in range(7)], [arm()])

    def record(self, index, attempts, **options):
        return E.make_record(self.plan, self.plan['assignments'][index]['id'], attempts, **options)

    def test_all_assigned_outcomes_and_every_fallback_attempt_count(self):
        records = [
            self.record(0, [attempt(usage={'latency_ms': 3, 'input_tokens': 2, 'usd': 0})], selected=1),
            self.record(1, [attempt(9)], selected=1),
            self.record(2, [attempt('{"x":9,"x":8}', encoding='json_text')], selected=1),
            self.record(3, [attempt(status='abstained')], selected=1),
            self.record(4, [attempt(status='refused')], status='failed'),
            self.record(5, [attempt(9, contract_accept=False),
                            attempt(model='large', role='fallback', feedback_exposed=True)], selected=2),
        ]
        group = E.summarize(self.plan, records)['groups'][0]
        for key, value in {'assigned': 7, 'complete': 5, 'failed': 1, 'pending': 1,
                           'correct': 2, 'false_accept': 1, 'ungradable_accept': 1, 'abstain': 1,
                           'contract_accept': 4, 'accepted_correct': 2, 'attempts': 7,
                           'fresh_calls': 7, 'fallback_calls': 1, 'stronger_fallback_calls': 1,
                           'fallback_cases': 1, 'stronger_fallback_cases': 1,
                           'fallback_correct': 1, 'stronger_fallback_correct': 1,
                           'initial_correct': 1, 'correct_without_fallback': 1}.items():
            with self.subTest(key=key):
                self.assertEqual(group[key], value)
        self.assertEqual(group['rates_per_assigned']['correct'], 2 / 7)
        self.assertEqual(group['attempt_states']['refused'], 1)
        self.assertEqual(group['attempt_grades']['incorrect'], 2)
        self.assertEqual(group['cost']['input_tokens'], {'known_total': 2, 'observed_attempts': 1, 'unobserved_attempts': 6})
        self.assertEqual(group['cost']['output_tokens']['observed_attempts'], 0)
        self.assertEqual(group['cost_unresolved_assignments'], 1)

    def test_wrong_unanimity_is_not_correctness(self):
        record = self.record(0, [attempt(9), attempt(9), attempt(9)], selected=1, agreement_attempts=[1, 2, 3])
        report = E.summarize(self.plan, [record])
        group = report['groups'][0]
        self.assertEqual(group['false_accept'], 1)
        self.assertEqual(group['correct'], 0)
        self.assertEqual(group['agreement']['mean_valid_agreement'], 1)
        self.assertEqual(report['outcomes'][0]['agreement']['independence'], 'not_established')

    def test_feedback_exposure_is_visible_on_agreement(self):
        record = self.record(0, [attempt(), attempt(feedback_exposed=True), attempt(feedback_exposed=None)],
                             selected=1, agreement_attempts=[1, 2, 3])
        evidence = E.summarize(self.plan, [record])['outcomes'][0]['agreement']
        self.assertEqual(evidence['feedback_exposed'], 1)
        self.assertEqual(evidence['feedback_unknown'], 1)
        self.assertEqual(evidence['agreement_valid'], 1)

    def test_replays_never_inflate_agreement_or_charge_old_usage(self):
        record = self.record(0, [attempt(), attempt(cached=True)], selected=1, agreement_attempts=[1, 2])
        report = E.summarize(self.plan, [record])
        self.assertFalse(report['outcomes'][0]['agreement']['measured'])
        group = report['groups'][0]
        self.assertEqual(group['fresh_calls'], 1)
        self.assertEqual(group['cached_attempts'], 1)
        with self.assertRaises(E.ProtocolError):
            self.record(0, [attempt(cached=True, usage={'input_tokens': 20})], selected=1)

    def test_missing_and_invalid_samples_stay_in_agreement_denominator(self):
        record = self.record(0, [attempt(), attempt(), attempt(status='refused'),
                                 attempt('not json', encoding='json_text')], selected=1,
                             agreement_attempts=[1, 2, 3, 4])
        agreement = E.summarize(self.plan, [record])['outcomes'][0]['agreement']
        self.assertEqual(agreement['assigned'], 4)
        self.assertEqual(agreement['fresh_valid'], 2)
        self.assertEqual(agreement['agreement_valid'], 1)
        self.assertEqual(agreement['agreement_all'], .5)

    def test_damaged_duplicate_and_unknown_records_do_not_move_denominator(self):
        valid = self.record(0, [attempt()], selected=1)
        damaged = self.record(1, [attempt()], selected=1)
        damaged['plan_id'] = 'tampered'
        report = E.summarize(self.plan, [valid, valid, damaged, {'assignment_id': 'not-assigned'}])
        group = report['groups'][0]
        self.assertEqual(group['assigned'], 7)
        self.assertEqual(group['damaged'], 2)
        self.assertEqual(group['pending'], 5)
        self.assertEqual(group['correct'], 0)
        self.assertEqual(len(report['ignored_records']), 1)

    def test_selected_result_cannot_hide_earlier_wrong_or_refused_calls(self):
        record = self.record(0, [attempt(status='refused'), attempt(9, contract_accept=False), attempt()], selected=3)
        group = E.summarize(self.plan, [record])['groups'][0]
        self.assertEqual(group['attempts'], 3)
        self.assertEqual(group['initial_correct'], 0)
        self.assertEqual(group['correct'], 1)
        self.assertEqual(group['attempt_grades']['incorrect'], 1)

    def test_wrong_unchecked_baseline_is_still_false_acceptance(self):
        record = self.record(0, [attempt(9, contract_accept=None)], selected=1)
        group = E.summarize(self.plan, [record])['groups'][0]
        self.assertEqual(group['false_accept'], 1)
        self.assertEqual(group['false_contract_accept'], 0)
        self.assertEqual(group['unchecked_answer'], 1)
        self.assertEqual(group['contract_accept'], 0)

    def test_accepting_rejected_candidate_is_a_visible_protocol_violation(self):
        record = self.record(0, [attempt(9, contract_accept=False)], selected=1)
        report = E.summarize(self.plan, [record])
        self.assertEqual(report['groups'][0]['false_accept'], 1)
        self.assertEqual(report['outcomes'][0]['violations'], [{'kind': 'selected_rejected_contract'}])

    def test_undeclared_model_and_over_budget_retained_as_protocol_violations(self):
        record = self.record(0, [attempt(model='undeclared')] * 5, selected=5)
        report = E.summarize(self.plan, [record])
        group = report['groups'][0]
        self.assertEqual(group['attempts'], 5)
        self.assertEqual(group['correct'], 1)
        self.assertEqual(group['protocol_violations'], 1)
        self.assertEqual(report['observed_protocol']['violating_assignments'], 1)
        kinds = {i['kind'] for i in report['outcomes'][0]['violations']}
        self.assertEqual(kinds, {'undeclared_model', 'provider_budget_exceeded'})

    def test_uncertain_execution_does_not_promote_partial_correct_answer(self):
        record = self.record(0, [attempt(), attempt(status='unknown')], status='uncertain')
        group = E.summarize(self.plan, [record])['groups'][0]
        self.assertEqual(group['correct'], 0)
        self.assertEqual(group['initial_correct'], 1)
        self.assertEqual(group['uncertain'], 1)
        self.assertEqual(group['attempts'], 2)
        with self.assertRaises(E.ProtocolError):
            self.record(0, [attempt()], status='uncertain', selected=1)

    def test_bad_boolean_flags_ordinals_and_negative_costs_are_rejected(self):
        for bad in (attempt(contract_accept=1), attempt(feedback_exposed='yes'),
                    attempt(usage={'usd': -1}), attempt(usage={'input_tokens': True})):
            with self.assertRaises(E.ProtocolError):
                self.record(0, [bad], selected=1)
        for selected in (0, 2, True):
            with self.assertRaises(E.ProtocolError):
                self.record(0, [attempt()], selected=selected)
        with self.assertRaises(E.ProtocolError):
            self.record(0, [attempt()], selected=1, agreement_attempts=[1, 1])

    def test_missing_labor_is_unknown_and_measured_labor_counted_once(self):
        report = E.summarize(self.plan, [])
        self.assertIsNone(report['spec_labor']['known_minutes_total'])
        measure = {'id': 'authoring-one', 'arm_id': 'direct', 'minutes': 12.5,
                   'method': 'timed', 'scope': 'All seven fixture task specifications'}
        report = E.summarize(self.plan, [], spec_labor=[measure])
        self.assertEqual(report['spec_labor']['known_minutes_total'], 12.5)
        with self.assertRaises(E.ProtocolError):
            E.summarize(self.plan, [], spec_labor=[measure, measure])


def assignment_id(plan, arm_id, repeat=0, case_id='case-0'):
    return next(a['id'] for a in plan['assignments']
                if (a['arm_id'], a['repeat'], a['case_id']) == (arm_id, repeat, case_id))


class MatchedPlans(unittest.TestCase):
    def test_repetition_pairing_keeps_pending_unresolved_and_retains_family(self):
        plan = E.make_plan([case()], [arm('direct'), arm('decomposed')], repetitions=2)
        records = [E.make_record(plan, assignment_id(plan, 'direct', 0), [attempt()], selected=1),
                   E.make_record(plan, assignment_id(plan, 'decomposed', 0), [attempt()], selected=1),
                   E.make_record(plan, assignment_id(plan, 'decomposed', 1), [attempt()], selected=1)]
        report = E.summarize(plan, records)
        self.assertTrue(report['comparability']['matched'])
        pair = report['paired'][0]
        self.assertEqual(pair['assigned_pairs'], 2)
        self.assertEqual((pair['resolved_pairs'], pair['both_correct'], pair['right_only_correct']), (1, 1, 0))
        self.assertEqual((pair['unresolved_pairs'], pair['unresolved']), (1, {'left_only': 1, 'right_only': 0, 'both': 0}))
        self.assertEqual(pair['unresolved_reasons']['left']['pending'], 1)
        self.assertEqual(pair['families'], {'family-0': {
            'assigned_pairs': 2, 'resolved_pairs': 1, 'both_correct': 1, 'left_only_correct': 0,
            'right_only_correct': 0, 'neither_correct': 0, 'unresolved_pairs': 1}})

    def test_plan_gold_assignment_and_arm_changes_are_detected(self):
        plan = E.make_plan([case()], [arm()])
        for change in ('gold', 'assignment', 'arm'):
            corrupted = copy.deepcopy(plan)
            if change == 'gold':
                corrupted['cases'][0]['rubric']['expected'] = 9
            elif change == 'assignment':
                corrupted['assignments'].clear()
            else:
                corrupted['arms'][0]['treatment'] = 'other'
            with self.assertRaises(E.ProtocolError):
                E.summarize(corrupted, [])

    def test_public_scoring_refuses_unassigned_cell(self):
        plan = E.make_plan([case()], [arm()])
        other = dict(plan['assignments'][0], id='unassigned')
        with self.assertRaises(E.ProtocolError):
            E.score_assignment(plan, other)



class ReformRepairs(unittest.TestCase):
    """Review findings evalclaims-2/6/7/8 and frozen version identity."""
    def setUp(self):
        self.plan = E.make_plan([case(i) for i in range(8)], [arm('left'), arm('right')])

    def record(self, arm_id, index, attempts, **options):
        return E.make_record(self.plan, assignment_id(self.plan, arm_id, case_id=f'case-{index}'), attempts, **options)

    def test_version_1_plan_identity_and_receipts_still_verify(self):
        cases = [case(0), case(1, family='family-1')]
        legacy = E._plan(cases, [arm('direct'), arm('decomposed')], 'heldout', 2, (), 1)
        # Digest produced by the version 1 implementation before this reform.
        self.assertEqual(legacy['id'], '35c4cf0ff7c91311c408871851cde56a6a76c8e588417d797c2dcf21bfb45e49')
        self.assertEqual([(a['arm_id'], a['repeat']) for a in legacy['assignments'][:4]],
                         [('direct', 0), ('direct', 1), ('decomposed', 0), ('decomposed', 1)])
        report = E.summarize(legacy, [])
        self.assertEqual((report['plan_version'], report['order']['counterbalanced']), (1, False))
        self.assertTrue(any('fixed order' in limit for limit in report['limits']))
        receipt = E.make_record(legacy, legacy['assignments'][0]['id'], [attempt()], selected=1)
        receipt['version'] = 1
        self.assertEqual(E.summarize(legacy, [receipt])['outcomes'][0]['status'], 'complete')
        for change in ({'status': 'harness_failed', 'selected': None},
                       {'attempts': [attempt('x', encoding='invalid_envelope', contract_accept=False)]},
                       {'attempts': [attempt(dispatched_at_ms=1)]}):
            with self.subTest(change=change):
                outcome = E.summarize(legacy, [{**receipt, **change}])['outcomes'][0]
                self.assertEqual(outcome['status'], 'damaged')
        changed = copy.deepcopy(legacy)
        changed['assignments'].reverse()
        with self.assertRaises(E.ProtocolError):
            E.summarize(changed, [])

    def test_counterbalanced_plan_is_seeded_reproducible_balanced_and_tamper_evident(self):
        for count in (2, 3, 4, 5):
            arms = [arm(f'arm-{i}') for i in range(count)]
            cases = [case(i) for i in range(2 * count)]
            plan = E.make_plan(cases, arms, order_seed=11)
            self.assertEqual(plan, E.make_plan(copy.deepcopy(cases), copy.deepcopy(arms), order_seed=11))
            positions = E.summarize(plan, [])['order']['positions']
            self.assertEqual(positions, {a['id']: [2] * count for a in arms})
            for start in range(0, len(plan['assignments']), count):
                block = plan['assignments'][start:start + count]
                self.assertEqual(len({(a['case_id'], a['repeat']) for a in block}), 1)
                self.assertEqual(sorted(a['arm_id'] for a in block), sorted(a['id'] for a in arms))
        base = E.make_plan([case(i) for i in range(4)], [arm('left'), arm('right')], order_seed=3)
        for change in ('seed', 'position', 'order'):
            tampered = copy.deepcopy(base)
            if change == 'seed':
                tampered['order']['seed'] = 4
            elif change == 'position':
                tampered['assignments'][0]['position'] = 1
            else:
                tampered['assignments'][0], tampered['assignments'][1] = tampered['assignments'][1], tampered['assignments'][0]
            with self.subTest(change=change), self.assertRaises(E.ProtocolError):
                E.summarize(tampered, [])
        for bad in (-1, True, 1.0, None):
            with self.assertRaises(E.ProtocolError):
                E.make_plan([case()], [arm()], order_seed=bad)

    def test_only_model_attributable_outcomes_enter_paired_counts(self):
        refused, error = attempt(status='refused'), attempt(status='error')
        bad = attempt('{"x"', encoding='invalid_envelope', contract_accept=False)
        records = [
            self.record('left', 0, [attempt()], selected=1),                       # both correct
            self.record('right', 0, [attempt()], selected=1),
            self.record('left', 1, [attempt()], selected=1),                       # right pending
            self.record('left', 2, [attempt()], selected=1),                       # right uncertain
            self.record('right', 2, [attempt(), attempt(status='unknown')], status='uncertain'),
            self.record('left', 3, [attempt()], selected=1),                       # right: no dispatch
            self.record('right', 3, [], status='failed'),
            self.record('left', 4, [attempt(9)], selected=1),                      # right: infrastructure
            self.record('right', 4, [refused, error], status='failed'),
            self.record('left', 5, [attempt()], selected=1),                       # right: harness failure
            self.record('right', 5, [bad], status='harness_failed'),
            self.record('left', 6, [attempt(9)], selected=1),                      # both wrong: resolved
            self.record('right', 6, [bad, attempt(9, contract_accept=False)], status='failed'),
            self.record('left', 7, [attempt()], selected=1),                       # right damaged
            {**self.record('right', 7, [attempt()], selected=1), 'plan_id': 'other'},
        ]
        report = E.summarize(self.plan, records)
        pair = report['paired'][0]
        self.assertEqual((pair['assigned_pairs'], pair['resolved_pairs'], pair['unresolved_pairs']), (8, 2, 6))
        self.assertEqual((pair['both_correct'], pair['left_only_correct'], pair['right_only_correct'],
                          pair['neither_correct']), (1, 0, 0, 1))
        self.assertEqual(pair['unresolved'], {'left_only': 0, 'right_only': 6, 'both': 0})
        self.assertEqual({k: v for k, v in pair['unresolved_reasons']['right'].items() if v},
                         {'pending': 1, 'uncertain': 1, 'harness': 2, 'infrastructure': 1, 'damaged': 1})
        right = report['groups'][1]
        self.assertEqual((right['attempts'], right['fresh_calls']), (8, 8))   # unresolved cells keep their costs
        self.assertEqual(right['attempt_states']['refused'] + right['attempt_states']['error'], 2)
        self.assertEqual(right['cost_unresolved_assignments'], 3)
        self.assertEqual(right['cells']['unresolved']['harness'], 2)

    def test_runner_harness_failures_mark_only_failed_outcomes(self):
        failed = self.record('right', 0, [attempt(9, contract_accept=False)], status='failed')
        ident = failed['assignment_id']
        self.assertEqual(E.summarize(self.plan, [failed])['outcomes'][1]['resolution'], 'resolved')
        marked = E.summarize(self.plan, [failed], harness_failures=[ident])
        outcome = next(o for o in marked['outcomes'] if o['assignment_id'] == ident)
        self.assertEqual((outcome['status'], outcome['resolution']), ('failed', 'harness'))
        self.assertEqual(marked['groups'][1]['attempts'], 1)
        for bad in (['not-assigned'], [['list']]):
            with self.assertRaises(E.ProtocolError):
                E.summarize(self.plan, [], harness_failures=bad)

    def test_malformed_record_identity_never_breaks_the_summary(self):
        valid = self.record('left', 0, [attempt()], selected=1)
        deep = self.record('left', 1, [attempt()], selected=1)
        deep['attempts'][0]['answer'] = [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
        rows = [valid, deep, {'assignment_id': [valid['assignment_id']]}, {'assignment_id': {'x': 1}},
                ['not', 'a', 'record'], {'assignment_id': None}]
        report = E.summarize(self.plan, rows)
        self.assertEqual(report['groups'][0]['correct'], 1)
        self.assertEqual(report['groups'][0]['damaged'], 1)
        self.assertEqual(len(report['ignored_records']), 4)
        self.assertEqual(report['cells']['assigned'], 16)

    def test_envelope_violations_grade_malformed_under_every_rubric(self):
        for rubric in ({'mode': 'typed_json', 'expected': 8}, {'mode': 'exact_text', 'expected': '8'}):
            for raw in ('8', '{"answer":8,"confidence":1}', 'prose'):
                with self.subTest(rubric=rubric['mode'], raw=raw):
                    result = E.grade(rubric, raw, 'invalid_envelope')
                    self.assertEqual((result['status'], result['correct']), ('malformed', None))
        for row in (attempt(8, encoding='invalid_envelope', contract_accept=False),
                    attempt('{"answer":8}', encoding='invalid_envelope', contract_accept=True)):
            with self.assertRaises(E.ProtocolError):
                self.record('left', 0, [row], status='failed')
        record = self.record('left', 0, [attempt('{"answer":8,"x":1}', encoding='invalid_envelope', contract_accept=False)],
                             status='failed')
        group = E.summarize(self.plan, [record])['groups'][0]
        self.assertEqual(group['attempt_grades']['malformed'], 1)
        self.assertEqual(group['cells']['resolved'], 1)

    def test_first_dispatch_information_hashes_are_compared_per_pair(self):
        same, other = 'a' * 64, 'b' * 64
        records = [self.record('left', 0, [attempt(information_sha256=same)], selected=1),
                   self.record('right', 0, [attempt(information_sha256=same)], selected=1),
                   self.record('left', 1, [attempt(information_sha256=same)], selected=1),
                   self.record('right', 1, [attempt(information_sha256=other)], selected=1)]
        report = E.summarize(self.plan, records)
        self.assertEqual({k: v for k, v in report['paired'][0]['information'].items() if k != 'scope'},
                         {'matched': 1, 'mismatched': 1, 'unrecorded': 6})
        self.assertEqual(report['observed_protocol']['information_mismatched_pairs'], 1)
        with self.assertRaises(E.ProtocolError):
            self.record('left', 0, [attempt(information_sha256='nothex')], selected=1)


if __name__ == '__main__':
    unittest.main()

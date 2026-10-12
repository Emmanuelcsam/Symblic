"""Compiled incremental proof journeys; injected constructors, no providers or stores."""

import copy
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.adapters import logic as L
from symblic.adapters import proof_session as R
from symblic.kernel.run import Run

TASK = {'premises': 'a: "A"\nrule: "A" implies "B"', 'goal': '"B"',
        'certificate_format': 'incremental', 'step_limit': 3, 'calls': 6}


def candidate(rule, *args, formula=None):
    return {'rule': rule, 'args': list(args), 'formula': formula}


MP = [candidate('premise', 'rule'), candidate('premise', 'a'),
      candidate('implies_elim', 's1', 's2')]


class Apps:
    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def call(self, request):
        self.requests.append(dict(request))
        index = len(self.requests) - 1
        if index >= len(self.answers):
            raise AssertionError('unexpected extra constructor call')
        return {'ok': True, 'json': {'answer': copy.deepcopy(self.answers[index])}}


def value(report, name):
    return next(row['value'] for row in report['bindings'] if row['name'] == name)


class IncrementalLogic(unittest.TestCase):
    def setUp(self):
        for manager in (
            patch.object(JS, 'node_version', return_value='test-no-node'),
            patch('subprocess.Popen', side_effect=AssertionError('no processes in compiler tests')),
        ):
            manager.start()
            self.addCleanup(manager.stop)

    def execute(self, answers, task=None):
        compiled = L.compile_task(TASK if task is None else task)
        apps = Apps(answers)
        with patch.object(S.KB, 'derive', side_effect=AssertionError('no proof search')):
            report = Run(compiled['source'], compiled['inputs'], apps,
                         {**compiled['options'], 'by': 'fake:constructor'}, folder=None).execute()
        return compiled, apps, report

    def test_one_typed_inference_per_fresh_context_and_full_certificate(self):
        compiled, apps, report = self.execute(MP)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['calls'], len(apps.requests)), (3, 3))
        self.assertTrue(value(report, 'verification')['valid'])
        self.assertEqual(len(value(report, 'certificate')['steps']), 3)
        self.assertEqual(value(report, 'certificate')['result'], 's3')
        for index, request in enumerate(apps.requests, 1):
            schema = request['schema']['properties']['answer']
            self.assertEqual(set(schema['properties']), {'rule', 'args', 'formula'})
            self.assertFalse(schema['additionalProperties'])
            self.assertIn(f'"next_id": "s{index}"', request['prompt'])
            self.assertIn(f'"steps_left": {4 - index}', request['prompt'])
            self.assertNotIn('"steps":', request['prompt'])
        self.assertEqual(compiled['formalization']['step_limit'], 3)
        self.assertNotIn('max_steps', compiled['options'])

    def test_repair_reports_specific_inference_error_and_does_not_carry_failed_step(self):
        wrong = candidate('implies_elim', 's2', 's1')
        _compiled, apps, report = self.execute(MP[:2] + [wrong, MP[-1]])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 4)
        self.assertIn('implies_elim_mismatch', apps.requests[3]['prompt'])
        self.assertIn('exactly its left side', apps.requests[3]['prompt'])
        self.assertEqual(len(value(report, 'certificate')['steps']), 3)
        self.assertEqual(value(report, 'certificate')['steps'][-1]['args'], ['s1', 's2'])

    def test_rejected_formula_is_visible_only_to_that_steps_repair(self):
        marker = 'rejected candidate marker'
        wrong = candidate('premise', 'a', formula=['atom', marker])
        _compiled, apps, report = self.execute([wrong] + MP)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertIn(marker, apps.requests[1]['prompt'])
        for request in apps.requests[2:]:
            self.assertNotIn(marker, request['prompt'])

    def test_completion_stops_without_spending_remaining_steps_or_calls(self):
        task = {**TASK, 'goal': '"A"', 'step_limit': 32, 'calls': 64}
        _compiled, apps, report = self.execute([candidate('premise', 'a')], task)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(value(report, 'certificate')['result'], 's1')

    def test_all_32_allowed_steps_can_execute_with_immutable_host_ids(self):
        task = {**TASK, 'premises': 'a: "A"\nb: "B"', 'step_limit': 32, 'calls': 32}
        answers = [candidate('premise', 'a')] * 31 + [candidate('premise', 'b')]
        _compiled, apps, report = self.execute(answers, task)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 32)
        self.assertEqual(value(report, 'certificate')['result'], 's32')

    def test_step_limit_leaves_goal_unresolved_not_false_or_accepted(self):
        _compiled, apps, report = self.execute(MP[:2], {**TASK, 'step_limit': 2})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 2)
        self.assertIn('Proof step limit reached', report['error']['message'])
        self.assertNotIn('verification', [row['name'] for row in report['bindings']])

    def test_shared_call_budget_counts_repairs_and_stops_before_next_dispatch(self):
        answers = [candidate('premise', 'missing')] + MP[:2]
        _compiled, apps, report = self.execute(answers, {**TASK, 'calls': 3})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual((len(apps.requests), report['calls']), (3, 3))
        self.assertIn('budget', report['error']['message'])
        self.assertNotIn('verification', [row['name'] for row in report['bindings']])

    def test_bad_candidate_exhaustion_never_promotes_an_unchecked_step(self):
        wrong = candidate('premise', 'invented')
        _compiled, apps, report = self.execute([wrong] * 3)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 3)
        self.assertIn('unknown_premise', report['error']['message'])
        self.assertNotIn('certificate', [row['name'] for row in report['bindings']])

    def test_oversize_required_frontier_refuses_before_any_constructor_call(self):
        rows = [{'name': f'p{index}', 'formula': '"' + str(index) + 'x' * 3000 + '"'}
                for index in range(8)]
        _compiled, apps, report = self.execute([], {**TASK, 'premises': rows, 'goal': rows[0]['formula']})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual((len(apps.requests), report['calls']), (0, 0))
        self.assertEqual(report['error']['kind'], 'context')

    def test_final_checker_independently_refuses_a_forged_completion_certificate(self):
        real_append = R.append

        def corrupted(*args, **kwargs):
            result = real_append(*args, **kwargs)
            if result['complete']:
                result['certificate']['steps'][-1]['args'] = ['invented']
            return result

        with patch.object(R, 'append', side_effect=corrupted):
            _compiled, apps, report = self.execute([candidate('premise', 'a')], {**TASK, 'goal': '"A"'})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 1)
        self.assertFalse(value(report, 'verification')['valid'])

    def test_assumption_requires_discharge_before_completion(self):
        task = {**TASK, 'premises': '', 'goal': '"A" implies "A"', 'step_limit': 2}
        answers = [candidate('assume', formula=['atom', 'A']), candidate('implies_intro', 's1', 's1')]
        _compiled, apps, report = self.execute(answers, task)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertIn('"free": ["s1"]', apps.requests[1]['prompt'])
        self.assertTrue(value(report, 'verification')['valid'])

    def test_finite_task_uses_expanded_frontier_and_checks_original_domains(self):
        task = {**TASK, 'premises': 'all: forall x in People: Kind(x:People)',
                'goal': 'Kind(People["Ada"])', 'domains': {'People': ['Ada', 'Ben']}}
        compiled, apps, report = self.execute([candidate('premise', 'all'), candidate('and_left', 's1')], task)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        self.assertIn('finite_steps_check(domains, premises, goal, certificate)', compiled['source'])
        self.assertTrue(value(report, 'verification')['conditional_on_domains'])
        self.assertEqual(value(report, 'verification')['domain_sizes'], {'People': 2})

    def test_bounds_bad_types_unknown_fields_and_cross_lane_limit_are_refused(self):
        for update in ({'step_limit': 0}, {'step_limit': 33}, {'step_limit': True}, {'step_limit': 2.5},
                       {'calls': 0}, {'calls': 65}, {'calls': True}, {'max_steps': 10},
                       {'certificate_format': 'terms'}, {'certificate_format': 'steps'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                L.compile_task({**TASK, **update})

    def test_incremental_defaults_and_identity_pin_limits(self):
        task = {'premises': 'a: "A"', 'goal': '"A"', 'certificate_format': 'incremental'}
        compiled = L.compile_task(task)
        self.assertEqual(compiled['options']['max_calls'], 32)
        self.assertEqual(compiled['formalization']['step_limit'], 16)
        self.assertNotEqual(compiled['formalization']['sha256'],
                            L.compile_task({**task, 'step_limit': 17})['formalization']['sha256'])
        self.assertNotEqual(compiled['formalization']['sha256'],
                            L.compile_task({**task, 'calls': 33})['formalization']['sha256'])
        compiled['inputs']['proof_rules']['rules'].clear()
        self.assertTrue(L.compile_task(task)['inputs']['proof_rules']['rules'])

    def test_previous_formats_keep_their_defaults_and_call_bounds(self):
        task = {'premises': 'a: "A"', 'goal': '"A"'}
        compiled = L.compile_task(task)
        self.assertEqual(compiled['formalization']['certificate_format'], 'terms')
        self.assertEqual(compiled['options']['max_calls'], 4)
        self.assertNotIn('step_limit', compiled['formalization'])
        self.assertIn('proof_check(premises, goal, certificate)', compiled['source'])
        for lane in ('terms', 'steps'):
            with self.assertRaises(ValueError):
                L.compile_task({**task, 'certificate_format': lane, 'calls': 7})


if __name__ == '__main__':
    unittest.main()

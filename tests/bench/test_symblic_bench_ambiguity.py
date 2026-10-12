"""Offline benchmark invariants; invented fixtures, fake providers, temporary stores."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from symblic.bench import ambiguity as A


def fixture(ambiguous=True):
    return {'id': 'fixture-one', 'family': 'fixture', 'domain': 'labels', 'split': 'dev',
            'public_group': 'fixture-public', 'request': 'Create 3 labels using my preferred title.',
            'context': 'The owner has not stated a preferred title.' if ambiguous else 'The title is Sample.',
            'fields': [{'name': 'count', 'type': 'integer', 'description': 'Number of labels'},
                       {'name': 'title', 'type': 'text', 'description': 'Exact title'}],
            'gold': {'values': {'count': 3, 'title': 'PRIVATE_ORACLE_{only}' if ambiguous else 'Sample'},
                     'clarify_fields': ['title'] if ambiguous else [],
                     'owner_answers': {'title': 'PRIVATE_ORACLE_{only}'} if ambiguous else {}}}


def answer(case):
    return {'action': 'answer', 'values': [{'field': k, 'value': v} for k, v in case['gold']['values'].items()],
            'questions': []}


QUERY = {'action': 'clarify', 'values': [], 'questions': ['title']}


class Fake:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def call(self, req):
        self.requests.append(req)
        value = self.replies.pop(0)
        if isinstance(value, BaseException):
            raise value
        return {'ok': True, 'json': value, 'node': 'fake-node', 'model': 'synthetic-fixture'}


class Raw(Fake):
    def call(self, req):
        self.requests.append(req)
        return self.replies.pop(0)


class AmbiguityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.case = fixture()

    def plan(self, conditions=('direct',), cases=None):
        data = {'version': 1, 'cases': cases or [self.case]}
        return data, A.make_plan(data, A.digest(data), ['claude:haiku'], conditions=conditions)

    def test_oracle_guess_is_not_supported_under_ambiguity(self):
        result = A.grade(self.case, answer(self.case))
        self.assertTrue(result['owner_exact'])
        self.assertTrue(result['unsupported_commitment'])
        self.assertFalse(result['initial_success'])
        self.assertFalse(result['supported_exact'])
        self.assertTrue(A.grade(self.case, answer(self.case), ['title'])['supported_exact'])

    def test_clear_controls_reject_always_ask_and_always_abstain(self):
        clear = fixture(False)
        self.assertFalse(A.grade(clear, QUERY)['initial_success'])
        self.assertFalse(A.grade(clear, {'action': 'abstain', 'values': [], 'questions': []})['initial_success'])
        self.assertTrue(A.grade(clear, answer(clear))['initial_success'])

    def test_exact_question_set_and_types(self):
        self.assertTrue(A.grade(self.case, QUERY)['initial_success'])
        for questions in (['count'], ['title', 'count'], ['title', 'title'], ['unknown'], []):
            self.assertFalse(A.grade(self.case, {**QUERY, 'questions': questions})['initial_success'])
        for value in (True, '3', 3.0):
            bad = answer(self.case)
            bad['values'][0]['value'] = value
            self.assertFalse(A.grade(self.case, bad, ['title'])['protocol_valid'])
        self.assertFalse(A.equal({'x': [True]}, {'x': [1]}))

    def test_protocol_extra_duplicate_missing_and_injection_values(self):
        for bad in ({**QUERY, 'extra': 1}, [], None, {'action': 'clarify', 'values': []}):
            self.assertFalse(A.grade(self.case, bad)['protocol_valid'])
        bad = answer(self.case)
        bad['values'].append(bad['values'][0])
        self.assertFalse(A.grade(self.case, bad)['protocol_valid'])
        with self.assertRaises(ValueError):
            A.parse_json('{"action":"answer","action":"abstain"}')
        with self.assertRaises(ValueError):
            A.parse_json('{"x":NaN}')

    def test_prompt_has_no_private_gold_or_identity(self):
        text = A.prompt(self.case)
        for private in ('PRIVATE_ORACLE', self.case['id'], self.case['family'], 'clarify_fields', 'gold'):
            self.assertNotIn(private, text)
        self.assertIn(self.case['request'], text)

    def test_real_typed_kernel_path_and_cancellation_handle_serialization(self):
        data, plan = self.plan(('typed',))
        fake = Fake([QUERY])
        result = A.run(self.out, data, plan, fake, log=lambda _: None)
        self.assertEqual(result['groups'][0]['success'], 1)
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(fake.requests[0]['tools'], 'none')
        self.assertIsNotNone(fake.requests[0]['schema'])
        self.assertNotIn('PRIVATE_ORACLE', fake.requests[0]['prompt'])

    def test_clarification_discloses_requested_value_only_and_uses_two_calls(self):
        data, plan = self.plan(('clarify',))
        fake = Fake([QUERY, answer(self.case)])
        result = A.run(self.out, data, plan, fake, log=lambda _: None)
        self.assertEqual(result['groups'][0]['success'], 1)
        self.assertEqual(result['groups'][0]['call_attempts'], 2)
        self.assertNotIn('PRIVATE_ORACLE', fake.requests[0]['prompt'])
        self.assertIn('PRIVATE_ORACLE', fake.requests[1]['prompt'])
        self.assertNotIn('clarify_fields', fake.requests[1]['prompt'])
        self.assertNotIn('initial_success', fake.requests[1]['prompt'])

    def test_oracle_control_and_clear_clarification_use_one_call(self):
        for condition, case in (('oracle_direct', self.case), ('clarify', fixture(False))):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as folder:
                data, plan = self.plan((condition,), [case])
                fake = Fake([answer(case)])
                result = A.run(folder, data, plan, fake, log=lambda _: None)
                self.assertEqual(result['groups'][0]['success'], 1)
                self.assertEqual(result['groups'][0]['call_attempts'], 1)

    def test_provider_failure_remains_and_resume_never_retries_it(self):
        data, plan = self.plan()
        fake = Fake([RuntimeError('no capacity')])
        result = A.run(self.out, data, plan, fake, log=lambda _: None)
        self.assertEqual((result['groups'][0]['assigned'], result['groups'][0]['failed']), (1, 1))
        result = A.run(self.out, data, plan, Fake([]), resume=True, log=lambda _: None)
        self.assertEqual(result['groups'][0]['failed'], 1)
        self.assertEqual(result['groups'][0]['success'], 0)

    def test_crash_is_uncertain_and_never_redispatched(self):
        data, plan = self.plan()
        with self.assertRaises(KeyboardInterrupt):
            A.run(self.out, data, plan, Fake([KeyboardInterrupt()]), log=lambda _: None)
        result = A.run(self.out, data, plan, Fake([]), resume=True, log=lambda _: None)
        self.assertEqual(result['groups'][0]['uncertain'], 1)
        self.assertEqual(result['groups'][0]['call_attempts'], 1)

    def test_pending_and_tampered_records_stay_in_denominator(self):
        data, plan = self.plan()
        result = A.run(self.out, data, plan, Fake([]), dry_run=True, log=lambda _: None)
        self.assertEqual(result['groups'][0]['pending'], 1)
        A.run(self.out, data, plan, Fake([QUERY]), resume=True, log=lambda _: None)
        path = self.out / 'ambiguity-cells' / (plan['cells'][0]['id'] + '.json')
        record = json.loads(path.read_text())
        record['correct'] = False
        path.write_text(json.dumps(record))
        result = A.summarize(self.out)
        self.assertEqual(result['groups'][0]['damaged'], 1)
        self.assertEqual(result['groups'][0]['assigned'], 1)

    def test_manifest_removal_is_detected(self):
        data, plan = self.plan()
        A.run(self.out, data, plan, Fake([]), dry_run=True, log=lambda _: None)
        path = self.out / 'ambiguity-manifest.json'
        row = json.loads(path.read_text())
        row['cells'] = []
        path.write_text(json.dumps(row))
        with self.assertRaises(ValueError):
            A.summarize(self.out)

    def test_budget_guard_and_pairwise_report(self):
        data, plan = self.plan(('direct', 'typed'))
        result = A.run(self.out, data, plan, Fake([QUERY, QUERY]), log=lambda _: None)
        self.assertEqual(result['paired'][0]['both_attempted'], 1)
        self.assertEqual(result['paired'][0]['joint_non_success'], 0)
        row = {'cell': 'fixture', 'phase': 'initial', 'calls': []}
        fake = Fake([QUERY, QUERY])
        calls = A._Calls(fake, row, self.out / 'budget.json', 1)
        calls.call({'app': {}, 'prompt': 'test', 'tools': 'none'})
        with self.assertRaises(ValueError):
            calls.call({'app': {}, 'prompt': 'test', 'tools': 'none'})
        self.assertEqual(len(fake.requests), 1)

    def test_dataset_validation_and_no_cross_split_public_clone(self):
        data = {'version': 1, 'cases': [self.case]}
        path = self.out / 'dataset.json'
        path.write_text(json.dumps(data))
        A.load_dataset(path)
        other = copy.deepcopy(self.case)
        other.update(id='other', family='another', split='heldout', public_group='another-public')
        data['cases'].append(other)
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            A.load_dataset(path)

    def test_same_raw_protocol_rejected_before_typed_projection(self):
        bad = {**QUERY, 'surprise': True}
        duplicate = '{"action":"answer","action":"clarify","values":[],"questions":["title"]}'
        for condition in ('direct', 'typed'):
            for response in ({'ok': True, 'json': bad}, {'ok': True, 'text': duplicate},
                             {'ok': True, 'json': QUERY, 'text': json.dumps(bad)}):
                with self.subTest(condition=condition, response=response), tempfile.TemporaryDirectory() as folder:
                    data, plan = self.plan((condition,))
                    fake = Raw([response])
                    result = A.run(folder, data, plan, fake, log=lambda _: None)
                    self.assertEqual(result['groups'][0]['success'], 0)
                    self.assertEqual(len(fake.requests), 1)

    def test_valid_inner_envelope_accepted_in_both_arms(self):
        for condition in ('direct', 'typed'):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as folder:
                data, plan = self.plan((condition,))
                result = A.run(folder, data, plan, Fake([{'answer': QUERY}]), log=lambda _: None)
                self.assertEqual(result['groups'][0]['success'], 1)

    def test_effort_weight_and_orchestration_are_refused(self):
        for app in ('claude:haiku+high', 'claude:haiku*2', 'council:panel', 'no-such-engine', 'kernel'):
            with self.subTest(app=app), self.assertRaises(ValueError):
                A.make_plan({'cases': [self.case]}, 'fixture', [app])
        data, _ = self.plan(('direct', 'typed'))
        plan = A.make_plan(data, A.digest(data), ['claude:haiku+low'], conditions=('direct', 'typed'))
        fake = Fake([QUERY, QUERY])
        A.run(self.out, data, plan, fake, log=lambda _: None)
        self.assertEqual([r['effort'] for r in fake.requests], ['low', 'low'])

    def test_scalar_records_are_damaged_not_a_report_crash(self):
        data, plan = self.plan()
        A.run(self.out, data, plan, Fake([]), dry_run=True, log=lambda _: None)
        path = self.out / 'ambiguity-cells' / (plan['cells'][0]['id'] + '.json')
        path.parent.mkdir()
        for value in (None, 7, 'oops', [], True):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                result = A.summarize(self.out)
                self.assertEqual(result['groups'][0]['damaged'], 1)
                self.assertEqual(result['groups'][0]['assigned'], 1)

    def test_unknown_resume_does_not_create_assignment_or_dispatch(self):
        data, plan = self.plan()
        fake = Fake([QUERY])
        with self.assertRaises(ValueError):
            A.run(self.out, data, plan, fake, resume=True, log=lambda _: None)
        self.assertEqual(fake.requests, [])
        self.assertFalse((self.out / 'ambiguity-manifest.json').exists())


if __name__ == '__main__':
    unittest.main()

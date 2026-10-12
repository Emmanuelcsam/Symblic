"""Atomic construction: real native parser/runner, fake providers and temp stores."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import lockfile as K
from symblic.steps import construction as T
from symblic.kernel.run import Run
from tests.delegate.test_symblic_delegate import Fake


def step(name, instruction, choices, checks, uses=()):
    return {'name': name, 'instruction': instruction, 'parameters': [{'name': 'x', 'type': 'Int'}],
            'returns': 'Int', 'uses': list(uses), 'choices': choices, 'checks': checks}


REQUEST = {'title': 'GLOBAL_PRIVATE_TITLE', 'steps': [
    step('twice', 'Double x. FIRST_CARD_ONLY', ['x + 1', 'x * 2'], ['twice(3) = 6', 'twice(0) = 0']),
    step('unrelated', 'INDEPENDENT_CARD_ONLY. Add seven.', ['x + 7', 'x - 7'], ['unrelated(2) = 9']),
    step('after', 'Add one to twice(x). THIRD_CARD_ONLY', ['twice(x) - 1', 'twice(x) + 1'],
         ['after(3) = 7'], ['twice'])],
    'final_checks': ['after(9) = 19'],
    'program': 'let private_note = "PROGRAM_PRIVATE_ONLY".\nshow after(10).'}


class AtomicSteps(unittest.TestCase):
    def execute(self, request=REQUEST, replies=('x * 2', 'x + 7', 'twice(x) + 1'), **kwargs):
        c = T.compile_sequence(request, 'fake:worker', **kwargs)
        a = Fake(replies)
        r = Run(c['source'], c['inputs'], a, c['options']).execute()
        return c, a, r

    def test_wrong_choice_repairs_before_next_step_then_pure_artifact(self):
        c, a, r = self.execute(replies=['x + 1', 'x * 2', 'x + 7', 'twice(x) + 1'], retries=1)
        self.assertEqual(r['status'], 'done', r.get('error'))
        self.assertEqual(len(a.requests), 4)
        self.assertIn('brick_choice_0', a.requests[0]['prompt'])
        self.assertIn('brick_choice_0', a.requests[1]['prompt'])
        self.assertIn('brick_choice_1', a.requests[2]['prompt'])
        self.assertEqual(r['outputs'][0]['value'], {'twice': 2, 'unrelated': 1, 'after': 2})
        self.assertEqual(r['outputs'][0]['binding'], T.OUTPUT_BINDING)
        built = T.assemble(REQUEST, r['outputs'][0]['value'])
        self.assertEqual(built['execution'], 'not_run')
        pure = Fake()
        done = Run(built['source'], built['inputs'], pure, built['options']).execute()
        self.assertEqual(done['status'], 'done', done.get('error'))
        self.assertEqual(done['outputs'][0]['value'], 21)
        self.assertEqual(pure.requests, [])
        self.assertNotIn('ask', [n.k for n in S.walk(S.parse(built['source'])['statements'])])

    def test_context_is_exact_and_retained_metadata_never_enters_prompts(self):
        c, a, r = self.execute()
        self.assertEqual(r['status'], 'done', r.get('error'))
        self.assertEqual(c['inputs']['_steps_request'], REQUEST)
        self.assertEqual(c['inputs']['_steps_settings']['by'], 'fake:worker')
        for index, request in enumerate(a.requests):
            for marker in ['GLOBAL_PRIVATE_TITLE', 'PROGRAM_PRIVATE_ONLY', '_steps_request', '_steps_settings']:
                self.assertNotIn(marker, request['prompt'])
                self.assertNotIn(marker, json.dumps(request['context_manifest']))
            expected = ['brick_card_' + str(index)]
            if index == 2:
                expected = ['brick_card_2', 'brick_accepted_0']
                self.assertIn('FIRST_CARD_ONLY', request['prompt'])
                self.assertNotIn('INDEPENDENT_CARD_ONLY', request['prompt'])
                self.assertNotIn('x + 1', request['prompt'].split('STATEMENT:')[0])
            else:
                self.assertNotIn('THIRD_CARD_ONLY', request['prompt'])
            self.assertEqual([v['name'] for v in request['context_manifest']['included']], expected)

    def test_exhaustion_and_global_failure_produce_no_artifact_choice_output(self):
        _, a, r = self.execute(replies=['x + 1', 'x + 1'], retries=1)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(len(a.requests), 2)
        self.assertEqual(r['outputs'], [])
        bad = copy.deepcopy(REQUEST)
        bad['final_checks'] = ['after(9) = 200']
        _, a, r = self.execute(bad)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(len(a.requests), 3)
        self.assertEqual(r['outputs'], [])

    def test_types_and_unlisted_indexes_refuse_before_later_steps(self):
        for reply in [True, 3, 0, {'index': 2}]:
            with self.subTest(reply=reply):
                _, a, r = self.execute(replies=[reply], retries=0)
                self.assertEqual(r['status'], 'failed')
                self.assertEqual(len(a.requests), 1)
                self.assertEqual(r['outputs'], [])

    def test_context_overflow_refuses_before_call(self):
        _, a, r = self.execute(context_budget=1000)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['error']['kind'], 'context')
        self.assertEqual(a.requests, [])

    def test_prompt_size_does_not_grow_with_independent_program_length(self):
        q = {'title': 'Long task', 'steps': [step('unit' + str(i), 'Double x.', ['x + 1', 'x * 2'],
                 ['unit' + str(i) + '(3) = 6']) for i in range(24)],
             'final_checks': ['unit23(5) = 10']}
        _, a, r = self.execute(q, replies=['x * 2'] * 24)
        self.assertEqual(r['status'], 'done', r.get('error'))
        sizes = [v['context_manifest']['request_characters'] for v in a.requests]
        self.assertLess(max(sizes) - min(sizes), 100)
        self.assertLess(max(sizes), 5000)
        for v in a.requests:
            self.assertEqual(len(v['context_manifest']['included']), 1)

    def test_choices_retained_and_bad_assembly_does_not_claim_execution(self):
        c = T.compile_sequence(REQUEST, 'fake:worker')
        self.assertEqual(c['task']['steps'][0]['choices'], ['x + 1', 'x * 2'])
        built = T.assemble(REQUEST, {'twice': 1, 'unrelated': 1, 'after': 2})
        self.assertEqual(built['status'], 'prepared')
        self.assertEqual(built['execution'], 'not_run')
        result = Run(built['source'], applicators=Fake(), options=built['options']).execute()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['outputs'], [])

    def test_future_hidden_calls_and_impure_bodies_refuse(self):
        for edit in [lambda q: q['steps'][0].update(uses=['after']),
                     lambda q: q['steps'][0].update(choices=['after(x)']),
                     lambda q: q['steps'][0].update(choices=['js_run("", "")']),
                     lambda q: q['steps'][0].update(choices=['eval("1+1")']),
                     lambda q: q['steps'][0].update(choices=['unseen + x']),
                     lambda q: q['steps'][0].update(checks=['true']),
                     lambda q: q.update(final_checks=['true']),
                     lambda q: q.update(program='ask result: Int "secret".'),
                     lambda q: q.update(program='assert true because js_run("", "").'),
                     lambda q: q.update(program='show js_test("", []).'),
                     lambda q: q.update(program='let twice = 1.'),
                     lambda q: q.update(program='given payload: HiddenType.'),
                     lambda q: q.update(program='given payload: Record {nested: List of HiddenType}.'),
                     lambda q: q.update(program='let payload: HiddenType = 2.'),
                     lambda q: q['steps'][0].update(choices=['"{js_run(x, x)}"']),
                     lambda q: q['steps'][0].update(choices=['"{hidden}"']),
                     lambda q: q.update(program='show missing.')]:
            q = copy.deepcopy(REQUEST)
            edit(q)
            with self.subTest(request=q), self.assertRaises((T.StepError, S.SymblicError)):
                T.prepare(q)

    def test_inputs_and_program_loops_are_preserved_but_not_constructed_or_executed(self):
        q = copy.deepcopy(REQUEST)
        q['program'] = ('given parcels: List of Any length 1..100.\nfor row in parcels do\n'
                        'let result = {label: row.label, price: after(row.price)}.\nend.\nshow result.')
        _, a, r = self.execute(q)
        self.assertEqual(r['status'], 'done', r.get('error'))
        self.assertNotIn('parcels', ''.join(v['prompt'] for v in a.requests))
        b = T.assemble(q, {'twice': 2, 'unrelated': 1, 'after': 2})
        r = Run(b['source'], {'parcels': [{'label': 'box', 'price': 6}]}, Fake(), b['options']).execute()
        self.assertEqual(r['status'], 'done', r.get('error'))
        self.assertEqual(r['outputs'][0]['value'], [{'label': 'box', 'price': 13}])

    def test_duplicate_names_defaults_and_statement_injection_refuse(self):
        for edit in [lambda q: q['steps'][0].update(name='brick_choice_9'),
                     lambda q: q['steps'][0].update(returns='Int. show 1'),
                     lambda q: q['steps'][0].update(returns='Int = 2'),
                     lambda q: q['steps'][0].update(choices=['x). show 42. let hidden=(1']),
                     lambda q: q['steps'][0].update(parameters=[{'name': 'x', 'type': 'Int'}, {'name': 'x', 'type': 'Int'}]),
                     lambda q: q['steps'][1].update(name='twice')]:
            q = copy.deepcopy(REQUEST)
            edit(q)
            with self.subTest(request=q), self.assertRaises((T.StepError, S.SymblicError)):
                T.prepare(q)

    def test_text_is_data_and_compile_is_pure(self):
        q = copy.deepcopy(REQUEST)
        q['steps'][0]['instruction'] = 'Literal {private_note}. ".\nact evil = shell().'
        with patch('symblic.kernel.run.Run.execute', side_effect=AssertionError('no execution')):
            c = T.compile_sequence(q, 'fake:worker')
            T.assemble(q, {'twice': 2, 'unrelated': 1, 'after': 2})
        a = Fake(['x * 2', 'x + 7', 'twice(x) + 1'])
        r = Run(c['source'], c['inputs'], a, c['options']).execute()
        self.assertEqual(r['status'], 'done', r.get('error'))
        self.assertIn('{private_note}', a.requests[0]['prompt'])

    def test_native_lock_replay_without_any_new_model_calls(self):
        c = T.compile_sequence(REQUEST, 'fake:worker', retries=1)
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'program.sym').write_text(c['source'])
            Path(folder, 'meta.json').write_text(json.dumps({'inputs': c['inputs'], 'options': c['options']}))
            r = Run(c['source'], c['inputs'], Fake(['x + 1', 'x * 2', 'x + 7', 'twice(x) + 1']), c['options'], folder=folder).execute()
            self.assertEqual(r['status'], 'done', r.get('error'))
            lock = K.make_lock(folder)
            replay = K.replay(lock)
            self.assertTrue(replay['ok'], replay)
            self.assertEqual(replay['calls'], 0)
            self.assertEqual(replay['fingerprint'], r['fingerprint'])

    def test_app_and_assembly_bounds(self):
        for by in ['council:debate', 'fake:x*2', '', 'fake:x\nshow 1.']:
            with self.subTest(by=by), self.assertRaises((T.StepError, S.SymblicError)):
                T.compile_sequence(REQUEST, by)
        for answers in [{'twice': 2}, {'twice': True, 'unrelated': 1, 'after': 2},
                        {'twice': 3, 'unrelated': 1, 'after': 2}]:
            with self.subTest(answers=answers), self.assertRaises(T.StepError):
                T.assemble(REQUEST, answers)


if __name__ == '__main__':
    unittest.main()

"""symblic.steps.recovery: exact read-back of a finished step construction from its run folder.

Isolated temporary folders and fake applicators only; no model, network or host. Every tampering case
(source, request, output, policy, evidence, receipts, attribution, a concurrent change) must refuse.
Ported from the original host's steps-API tests; the HTTP-route cases stay in
tests/integration/test_symblic_steps_api.py.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.steps import recovery as A
from symblic.authoring import workcards as W
from symblic.kernel import evidence as EV
from symblic.kernel.run import Run
from tests.delegate.test_symblic_delegate import Fake


REQUEST = {'title': 'Small assembled function', 'steps': [
    {'name': 'twice', 'instruction': 'Multiply the input x by two.',
     'parameters': [{'name': 'x', 'type': 'Int'}], 'returns': 'Int',
     'uses': [], 'choices': ['x + 2', 'x * 2'], 'checks': ['twice(3) = 6']}],
    'final_checks': ['twice(7) = 14'], 'program': 'show twice(10).'}


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'run'
        self.fake = Fake(['x * 2'])
        self.result = W.run_card(REQUEST, kind='steps', folder=self.folder,
                                 by='fake:worker', applicators=self.fake)

    def change(self, name, mutate):
        path = self.folder / name
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value))

    def test_durable_cli_recovery_and_zero_call_artifact(self):
        self.assertEqual(self.result['status'], 'done')
        self.assertEqual(len(self.fake.requests), 1)
        recovered = A.from_folder(self.folder)
        self.assertTrue(recovered['accepted'])
        self.assertEqual(recovered['choices'], {'twice': 2})
        self.assertEqual((self.folder / 'assembled.sym').read_text(), recovered['artifact']['source'])
        no_models = Fake()
        final = Run(recovered['artifact']['source'], applicators=no_models,
                    options=recovered['artifact']['options']).execute()
        self.assertEqual(final['status'], 'done', final.get('error'))
        self.assertEqual(final['outputs'][0]['value'], 20)
        self.assertEqual(no_models.requests, [])

    def test_modified_source_refuses(self):
        with (self.folder / 'program.sym').open('a') as stream:
            stream.write('\nshow true.\n')
        with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)

    def test_modified_request_refuses(self):
        self.change('meta.json', lambda m: m['inputs']['_steps_request'].update(title='changed'))
        with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)

    def test_canonical_output_fingerprint_and_type_refuse(self):
        self.change('state.json', lambda s: s['outputs'][0]['canonical'].update(twice=1))
        with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)

    def test_weakened_host_policy_refuses(self):
        self.change('meta.json', lambda m: m['options'].update(side_effects=True))
        with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)

    def test_pending_and_failed_runs_have_no_artifact(self):
        for status in ('running', 'failed'):
            self.change('state.json', lambda s: s.update(status=status))
            recovered = A.from_folder(self.folder)
            self.assertFalse(recovered['accepted'])
            self.assertNotIn('artifact', recovered)

    def test_final_check_failure_is_not_an_artifact(self):
        request = copy.deepcopy(REQUEST)
        request['final_checks'] = ['twice(7) = 100']
        folder = Path(self.tmp.name) / 'failure'
        result = W.run_card(request, kind='steps', folder=folder,
                            by='fake:worker', applicators=Fake(['x * 2']))
        self.assertEqual(result['status'], 'failed')
        self.assertFalse((folder / 'assembled.sym').exists())
        self.assertFalse(A.from_folder(folder)['accepted'])

    def test_missing_and_mismatched_check_evidence_refuses(self):
        original = (self.folder / 'state.json').read_text()
        for mutate in [lambda s: s.pop('evidence'),
                       lambda s: s['evidence'].update(source_sha256='0' * 64),
                       lambda s: s['evidence'].update(checks=[]),
                       lambda s: s['evidence']['checks'].pop(),
                       lambda s: s['evidence']['checks'].reverse(),
                       lambda s: s['evidence']['checks'].append(s['evidence']['checks'][0]),
                       lambda s: s['evidence'].update(version=True)]:
            with self.subTest(mutation=mutate):
                (self.folder / 'state.json').write_text(original)
                self.change('state.json', mutate)
                with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)

    def test_receipt_predicate_result_kernel_and_binding_are_exact(self):
        original = (self.folder / 'state.json').read_text()
        changes = [lambda r: r.update(predicate_sha256='0' * 64),
                   lambda r: r.update(source_sha256='0' * 64),
                   lambda r: r.update(passed=False), lambda r: r.update(passed=1),
                   lambda r: r.update(kind='assert'), lambda r: r.update(line=999),
                   lambda r: r['kernel'].update(id='wrong'),
                   lambda r: r['bindings'][0].update(hash=S.fingerprint(1))]
        for mutate in changes:
            with self.subTest(mutation=mutate):
                (self.folder / 'state.json').write_text(original)
                def update(state):
                    receipt = state['evidence']['checks'][0]
                    mutate(receipt)
                    receipt['id'] = EV.digest({k: v for k, v in receipt.items() if k != 'id'})
                self.change('state.json', update)
                with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)

    def test_copied_output_cannot_replace_individual_accepted_choices(self):
        def change_output(state):
            choices = {'twice': 1}
            aggregate = S.fingerprint(choices)
            state['outputs'][0].update(canonical=choices, hash=aggregate)
            for binding in state['bindings']:
                if binding['name'] == 'steps_choices':
                    binding.update(hash=aggregate, value=choices)
        self.change('state.json', change_output)
        with self.assertRaisesRegex(A.StepsResultError, 'accepted ask binding'):
            A.from_folder(self.folder)
        def change_binding(state):
            for binding in state['bindings']:
                if binding['name'] == 'brick_choice_0':
                    binding.update(hash=S.fingerprint('x + 2'), value='x + 2')
        self.change('state.json', change_binding)
        with self.assertRaisesRegex(A.StepsResultError, 'recorded check'):
            A.from_folder(self.folder)

    def test_retried_construction_has_only_surviving_passing_receipts(self):
        folder = Path(self.tmp.name) / 'retry'
        result = W.run_card(REQUEST, kind='steps', folder=folder,
                           by='fake:worker', applicators=Fake(['x + 2', 'x * 2']))
        self.assertEqual(result['status'], 'done')
        recovered = A.from_folder(folder)
        self.assertTrue(recovered['accepted'])
        self.assertEqual(recovered['calls'], 2)
        state = json.loads((folder / 'state.json').read_text())
        self.assertEqual(len(state['evidence']['checks']), 2)
        self.assertTrue(all(row['passed'] is True for row in state['evidence']['checks']))

    def test_corrupt_kernel_and_concurrent_read_refuse(self):
        original = (self.folder / 'state.json').read_text()
        self.change('state.json', lambda s: s.update(kernel=None))
        with self.assertRaises(A.StepsResultError): A.from_folder(self.folder)
        (self.folder / 'state.json').write_text(original)
        read = A._read
        calls = []
        def mutating(path, maximum):
            calls.append(str(path))
            raw = read(path, maximum)
            return raw + b' ' if len(calls) == 4 else raw
        with patch.object(A, '_read', side_effect=mutating), self.assertRaisesRegex(A.StepsResultError, 'changed'):
            A.from_folder(self.folder)

    def test_finite_completion_is_counted_as_host_work_and_runs_without_models(self):
        folder = Path(self.tmp.name) / 'finite'
        fake = Fake(['x + 2'])
        result = W.run_card(REQUEST, kind='steps', folder=folder, by='fake:worker',
                            applicators=fake, retries=0, finite_fallback=True)
        self.assertEqual(result['status'], 'done', result.get('error'))
        recovered = A.from_folder(folder)
        self.assertEqual(recovered['selection_origins'], {'twice': 'finite_fallback'})
        self.assertEqual(recovered['model_selected_steps'], 0)
        self.assertEqual(recovered['finite_selected_steps'], 1)
        self.assertEqual(recovered['finite_trials'], 2)
        self.assertEqual(len(fake.requests), 1)
        pure = Fake()
        final = Run(recovered['artifact']['source'], applicators=pure,
                    options=recovered['artifact']['options']).execute()
        self.assertEqual(final['outputs'][0]['value'], 20)
        self.assertEqual(pure.requests, [])

    def test_valid_model_proposal_does_not_claim_finite_work(self):
        folder = Path(self.tmp.name) / 'model'
        result = W.run_card(REQUEST, kind='steps', folder=folder, by='fake:worker',
                            applicators=Fake(['x * 2']), retries=0, finite_fallback=True)
        self.assertEqual(result['status'], 'done')
        recovered = A.from_folder(folder)
        self.assertEqual(recovered['selection_origins'], {'twice': 'model'})
        self.assertEqual(recovered['model_selected_steps'], 1)
        self.assertEqual(recovered['finite_selected_steps'], 0)
        self.assertEqual(recovered['finite_trials'], 0)

    def test_finite_origin_and_selection_receipts_cannot_be_relabelled(self):
        folder = Path(self.tmp.name) / 'tamper-finite'
        W.run_card(REQUEST, kind='steps', folder=folder, by='fake:worker',
                   applicators=Fake(['x + 2']), retries=0, finite_fallback=True)
        path = folder / 'state.json'
        original = path.read_text()
        def choice(state):
            return next(b for b in state['bindings'] if b['name'] == 'brick_choice_0')['meta']
        mutations = [lambda s: s.pop('finite_fallbacks'),
                     lambda s: s['finite_fallbacks'][0].update(selected_index=1),
                     lambda s: s['finite_fallbacks'][0].update(model_calls=1),
                     lambda s: s['finite_fallbacks'][0].update(check_id='wrong'),
                     lambda s: choice(s)['finite_fallback'].update(selected_index=1),
                     lambda s: choice(s).update(answered_by_finite_fallback=False),
                     lambda s: choice(s).update(agreement=1, votes=1),
                     lambda s: s['determinacy']['asks'][0].update(answered_by='model')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                state = json.loads(original)
                mutate(state)
                path.write_text(json.dumps(state))
                with self.assertRaises(A.StepsResultError): A.from_folder(folder)

    def test_finite_compile_option_requires_an_exact_boolean(self):
        for invalid in [1, 'true', None]:
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                A.prepare(REQUEST, 'fake:worker', finite_fallback=invalid)


if __name__ == '__main__':
    unittest.main()

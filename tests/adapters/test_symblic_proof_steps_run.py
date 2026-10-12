"""Flat certificates through the existing compiler, native Run and pinned adapters."""
import copy
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import embed as embed
from symblic.kernel import execution_pins as X
from symblic.js import check as JS
from symblic.adapters import logic as L
from symblic.adapters import proof_adapter as A
from symblic.adapters import proof_steps as W
from symblic.kernel.run import Run
from tests.adapters.test_symblic_proof_steps import certificate, step

TASK = {'premises': 'human: "Socrates is human"\nrule: "Socrates is human" implies "Socrates is mortal"',
        'goal': '"Socrates is mortal"', 'calls': 2, 'certificate_format': 'steps'}
GOOD = certificate(step('p', 'premise', 'rule'), step('q', 'premise', 'human'), step('r', 'implies_elim', 'p', 'q'))


class Apps:
    def __init__(self, *answers):
        self.answers, self.requests = answers, []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': copy.deepcopy(self.answers[min(len(self.requests)-1, len(self.answers)-1)])}}


class FlatProofRuntime(unittest.TestCase):
    def setUp(self):
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)
        process = patch('subprocess.Popen', side_effect=AssertionError('no external process in flat proof tests'))
        process.start()
        self.addCleanup(process.stop)

    def execute(self, task, *answers):
        compiled = L.compile_task(task)
        apps = Apps(*answers)
        report = Run(compiled['source'], compiled['inputs'], apps,
                     {**compiled['options'], 'by': 'fake:constructor'}).execute()
        return compiled, apps, report

    def value(self, report):
        return next(row['value'] for row in report['bindings'] if row['name'] == 'verification')

    def test_injected_model_constructs_flat_certificate_under_uniform_schema_without_search(self):
        with patch.object(S.KB, 'derive', side_effect=AssertionError('checker must not search')):
            compiled, apps, report = self.execute(TASK, GOOD)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 1)
        value = self.value(report)
        self.assertTrue(value['valid'])
        self.assertEqual(value['format'], W.FORMAT)
        self.assertEqual(value['used_premises'], ['human', 'rule'])
        schema = apps.requests[0]['schema']['properties']['answer']
        fields = schema['properties']['steps']['items']['properties']
        self.assertEqual(set(fields), {'id', 'rule', 'args', 'formula'})
        self.assertEqual(set(fields['rule']['enum']), set(W.ARITIES))
        self.assertFalse(schema['additionalProperties'])
        self.assertIn('"formula": null', apps.requests[0]['prompt'])
        self.assertNotIn('Socrates', compiled['source'])
        self.assertEqual(compiled['inputs']['goal'], ['atom', 'Socrates is mortal'])
        candidate = next(row for row in report['bindings'] if row['name'] == 'certificate')
        self.assertEqual(candidate['meta']['epistemic']['claim']['origin'], 'model_proposal')

    def test_invalid_inference_is_repaired_with_shared_call_cap(self):
        wrong = certificate(step('p', 'premise', 'invented'))
        _, apps, report = self.execute(TASK, wrong, GOOD)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 2)
        self.assertEqual(len(apps.requests), 2)
        self.assertTrue(self.value(report)['valid'])
        _, apps, report = self.execute(dict(TASK, calls=1), wrong, GOOD)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 1)

    def test_candidate_cannot_replace_caller_contract_or_supply_a_conclusion(self):
        for key, forged in (('premises', {'human': ['atom', 'Socrates is mortal']}),
                            ('goal', ['atom', 'Socrates is human']), ('conclusion', ['atom', 'Socrates is mortal'])):
            _, apps, report = self.execute(dict(TASK, calls=1), dict(GOOD, **{key: forged}))
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(len(apps.requests), 1)
            self.assertNotIn('verification', [row['name'] for row in report['bindings']])

    def test_free_assumption_and_forward_reference_fail_then_valid_closed_proof_repairs(self):
        task = {'premises': '', 'goal': '"A" implies "A"', 'calls': 2, 'certificate_format': 'steps'}
        goal = ['implies', ['atom', 'A'], ['atom', 'A']]
        forged = certificate(step('h', 'assume', formula=goal))
        closed = certificate(step('h', 'assume', formula=['atom', 'A']), step('out', 'implies_intro', 'h', 'h'))
        _, apps, report = self.execute(task, forged, closed)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        forward = certificate(step('out', 'and_left', 'later'), step('later', 'assume', formula=goal), result='out')
        _, _, report = self.execute(dict(task, calls=1), forward)
        self.assertEqual(report['status'], 'failed')

    def test_finite_authoritative_expansion_and_format_identity(self):
        body = {'domains': {'People': ['Ada', 'Ben']},
                'premises': 'everyone: forall x in People: Kind(x:People)',
                'goal': 'Kind(People["Ada"])', 'certificate_format': 'steps'}
        proof = certificate(step('p', 'premise', 'everyone'), step('out', 'and_left', 'p'))
        compiled, apps, report = self.execute(body, proof)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 1)
        value = self.value(report)
        self.assertTrue(value['valid'])
        self.assertTrue(value['conditional_on_domains'])
        self.assertEqual(value['domain_sizes'], {'People': 2})
        self.assertEqual(value['proof_receipt']['format'], W.FORMAT)
        self.assertEqual(value['certificate_format'], 'steps')
        self.assertIn('finite_steps_check(domains, premises, goal, certificate)', compiled['source'])
        altered = copy.deepcopy(body)
        altered['domains']['People'].reverse()
        _, _, rejected = self.execute(dict(altered, calls=1), proof)
        self.assertEqual(rejected['status'], 'failed')
        self.assertNotEqual(compiled['formalization']['sha256'], L.compile_task(altered)['formalization']['sha256'])

    def test_finite_schema_failure_is_a_scoped_receipt_and_cannot_invent_domains(self):
        inputs = {'domains': {'People': ['Ada']}, 'premises': {},
                  'goal': ['pred', 'Kind', [['const', 'People', 'Missing']]], 'cert': GOOD}
        source = ('given domains: Any.\ngiven premises: Any.\ngiven goal: Any.\ngiven cert: Any.\n'
                  'let verification = finite_steps_check(domains, premises, goal, cert).')
        report = embed.run(source, inputs=inputs)
        self.assertEqual(report['status'], 'done', report.get('error'))
        value = self.value(report)
        self.assertFalse(value['valid'])
        self.assertEqual(value['error'], 'out_of_domain')
        self.assertTrue(value['conditional_on_domains'])

    def test_default_terms_backward_compatible_and_format_is_pinned(self):
        default = dict(TASK)
        default.pop('certificate_format')
        terms = L.compile_task(default)
        explicit = L.compile_task(dict(default, certificate_format='terms'))
        flat = L.compile_task(TASK)
        self.assertEqual(terms, explicit)
        self.assertEqual(terms['formalization']['certificate_format'], 'terms')
        self.assertIn('proof_check(premises, goal, certificate)', terms['source'])
        self.assertNotEqual(terms['formalization']['sha256'], flat['formalization']['sha256'])
        old = {'version': 1, 'proof': ['implies_elim', ['premise', 'rule'], ['premise', 'human']]}
        _, apps, report = self.execute(default, old)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 1)
        for value in ('auto', '', None, True, 1):
            with self.assertRaises(ValueError):
                L.compile_task(dict(default, certificate_format=value))

    def test_detached_generic_rules_do_not_contain_target_proofs(self):
        first = L.compile_task(TASK)
        self.assertNotIn('Socrates', str(first['inputs']['proof_rules']))
        first['inputs']['proof_rules']['rules'].clear()
        self.assertTrue(L.compile_task(TASK)['inputs']['proof_rules']['rules'])
        _, _, report = self.execute(dict(TASK, calls=1), first['inputs']['proof_rules']['unrelated_example']['certificate'])
        self.assertEqual(report['status'], 'failed')

    def test_language_builtins_accept_null_only_in_steps_wire_lane(self):
        inputs = {'premises': {'a': ['atom', 'A']}, 'goal': ['atom', 'A'],
                  'cert': certificate(step('p', 'premise', 'a'))}
        source = ('given premises: Any.\ngiven goal: Any.\ngiven cert: Any.\n'
                  'assert proof_steps_valid(premises, goal, cert).\n'
                  'let verification = proof_steps_check(premises, goal, cert).')
        report = embed.run(source, inputs=inputs)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)
        # Existing terms intentionally retain their old wire contract.
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        with self.assertRaises(S.SymblicError):
            A._wire(None, kernel, node)
        self.assertIsNone(A._wire(None, kernel, node, allow_none=True))
        for bad in (True, 1.0, object()):
            with self.assertRaises(S.SymblicError):
                A._wire(bad, kernel, node, allow_none=True)

    def test_host_budget_alias_bounds_and_execution_pins(self):
        inputs = {'premises': {'a': ['atom', 'A']}, 'goal': ['atom', 'A'], 'cert': certificate(step('p', 'premise', 'a'))}
        source = ('given premises: Any.\ngiven goal: Any.\ngiven cert: Any.\n'
                  'let verification = proof_steps_check(premises, goal, cert).')
        report = embed.run(source, inputs=inputs, options={'max_steps': 10})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['calls'], 0)
        shared = ['atom', 'A']
        for _ in range(15):
            shared = ['and', shared, shared]
        kernel = S.Kernel(budget=S.Budget(100))
        with self.assertRaises(S.SymblicError):
            A.proof_steps_check(kernel, S.Node('call', 1, 1), {'a': shared}, ['atom', 'A'], inputs['cert'])
        self.assertIn('symblic/adapters/proof_steps.py', X.REQUIRED_FILES)
        self.assertIn('symblic/adapters/proof_steps.py', X.PYTHON_FILES)
        self.assertEqual(S.kernel_id()['proof_steps'], W.VERSION)
        self.assertIn('proof_steps_check', S.BUILTINS)
        self.assertIn('finite_steps_check', S.BUILTINS)


if __name__ == '__main__':
    unittest.main()

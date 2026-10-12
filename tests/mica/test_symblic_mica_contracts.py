import copy
import unittest
from unittest import mock

from symblic.mica import contracts as C


def request():
    return {'objective': 'Build a pure integer increment function.',
            'requirements': [{'id': 'increment', 'text': 'Return the input plus one.', 'acceptance': 'TESTED'}],
            'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
            'tests': [{'requirement_ids': ['increment'], 'call': 'inc(2)', 'expected': '3'}],
            'allowed_outputs': ['result.js']}


def unit(ident='increment', name='inc', uses=None, deps=None):
    return {'contract_id': ident, 'root_requirement_ids': ['increment'], 'objective': 'Return input plus one.',
            'dependency_contract_ids': deps or [],
            'unit': {'names': [name], 'heading': name + '(x)', 'body': 'Return the input plus one.',
                     'uses': uses or [], 'setup': '', 'examples': [[name + '(2)', '3']]},
            'verification_obligations': [{'kind': 'unit_examples', 'requirement_ids': ['increment']}]}


def plan():
    return {'id': 'first', 'contracts': [unit()]}


def obligation():
    return {'kind': 'finite_refinement', 'requirement_ids': ['increment'],
            'variables': {'x': [-1, 0, 1, 2]}, 'premises': ['x > 0'], 'conclusions': ['x >= 1']}


class ContractsTest(unittest.TestCase):
    def error(self, code, fn, *args):
        with self.assertRaises(C.ContractError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_defaults_are_structural_detached_and_deterministic(self):
        value = request(); first = C.normalize_request(value)
        self.assertEqual(first['language'], 'javascript')
        self.assertEqual(first['budget']['max_workers'], 3)
        value['tests'][0]['expected'] = '999'
        self.assertEqual(first['tests'][0]['expected'], '3')
        self.assertEqual(C.normalize_request(first), first)
        self.assertEqual(C.digest({'a': 1, 'b': 2}), C.digest({'b': 2, 'a': 1}))

    def test_rejects_authority_and_unknown_fields(self):
        value = request(); value['shell'] = 'true'
        self.error('fields', C.normalize_request, value)
        value = request(); value['budget'] = {'max_calls': True}
        self.error('budget', C.normalize_request, value)
        for path in ('/tmp/out.js', '../out.js', 'a/../out.js', 'a\\out.js', 'C:out.js', './out.js', 'a//out.js', '.hidden/x.js'):
            value = request(); value['allowed_outputs'] = [path]
            self.error('path', C.normalize_request, value)

    def test_missing_or_false_acceptance_shape(self):
        value = request(); value['tests'] = []
        self.error('tests', C.normalize_request, value)
        value = request(); value['requirements'].append({'id': 'extra', 'text': 'More.', 'acceptance': 'TESTED'})
        self.error('coverage', C.normalize_request, value)
        value = request(); value['requirements'][0]['acceptance'] = 'PROBABLY'
        self.error('acceptance', C.normalize_request, value)
        for expected in ('NaN', '1e10000', '{"a":1,"a":2}', 'undefined'):
            value = request(); value['tests'][0]['expected'] = expected
            self.error('expected', C.normalize_request, value)

    def test_valid_plan_uses_existing_dag_and_has_no_success_claim(self):
        value = C.validate_plan(request(), plan())
        self.assertEqual(value['order'], ['increment'])
        self.assertEqual(value['layers'], [['increment']])
        self.assertEqual(value['root_tests'], request()['tests'])
        self.assertIn('pending_execution', value['assurance'])
        self.assertEqual(value['spec_plan']['scope'], 'declared_dependencies_and_exposed_examples')
        self.assertEqual(value['content_hash'], C.digest({k: v for k, v in value.items() if k != 'content_hash'}))

    def test_sealed_plan_revalidates_every_derived_field(self):
        sealed = C.validate_plan(request(), plan())
        self.assertEqual(C.validate_plan(request(), sealed), sealed)
        for field, value in [('order', []), ('layers', []), ('root_tests', []), ('request_sha256', '0' * 64)]:
            changed = copy.deepcopy(sealed); changed[field] = value
            changed['content_hash'] = C.digest({k: v for k, v in changed.items() if k != 'content_hash'})
            self.error('sealed_plan', C.validate_plan, request(), changed)

    def test_optional_affine_construction_is_preserved_sealed_and_bounded(self):
        original = C.validate_plan(request(), plan())
        self.assertNotIn('construction', original['contracts'][0])
        row = unit()
        row['construction'] = {'kind': 'affine_integer_v1', 'parameters': [{'name': 'x', 'lo': -10, 'hi': 10}],
                               'coefficient_bounds': [{'lo': -3, 'hi': 3}], 'intercept_bounds': {'lo': -3, 'hi': 3}}
        sealed = C.validate_plan(request(), {'id': 'affine', 'contracts': [row]})
        self.assertEqual(sealed['contracts'][0]['construction']['version'], 1)
        self.assertEqual(C.validate_plan(request(), sealed), sealed)
        changed = copy.deepcopy(sealed)
        changed['contracts'][0]['construction']['intercept_bounds']['hi'] = 4
        self.error('content_hash', C.validate_plan, request(), changed)
        row['construction']['source'] = 'unrequested_native_code'
        self.error('construction_shape', C.validate_plan, request(), {'id': 'bad', 'contracts': [row]})

    def test_false_refinement_refuses_even_tested_requirement(self):
        row = unit(); proof = obligation(); proof['conclusions'] = ['x > 1']
        row['verification_obligations'].append(proof)
        self.error('refinement_refuted', C.validate_plan, request(), {'id': 'false', 'contracts': [row]})

    def test_dag_can_reorder_and_maps_exact_dependencies(self):
        first = unit('helper', 'addOne'); last = unit('final', 'inc', ['addOne(x)'], ['helper'])
        last['input_artifacts'] = ['units/helper.js']; last['permitted_read_scope'] = ['units/helper.js']
        result = C.validate_plan(request(), {'id': 'reordered', 'contracts': [last, first]})
        self.assertEqual(result['order'], ['helper', 'final'])
        self.assertEqual(result['layers'], [['helper'], ['final']])
        last['dependency_contract_ids'] = []
        self.error('dependency', C.validate_plan, request(), {'id': 'invalid', 'contracts': [last, first]})

    def test_rejects_dependency_and_parent_cycles(self):
        first = unit('a', 'inc', ['helper'], ['b']); last = unit('b', 'helper', ['inc'], ['a'])
        self.error('dependency_cycle', C.validate_plan, request(), {'id': 'cycle', 'contracts': [first, last]})
        first = unit(); first['parent_contract_id'] = 'increment'
        self.error('parent_cycle', C.validate_plan, request(), {'id': 'cycle', 'contracts': [first]})

    def test_rejects_effects_scopes_conflicts_and_expanded_budget(self):
        for key, value, code in [('permitted_effects', ['network'], 'effects'),
                                 ('permitted_write_scope', ['other.js'], 'write_scope'),
                                 ('input_artifacts', ['secret.txt'], 'read_scope'),
                                 ('resource_budget', {'max_calls': 100}, 'budget'),
                                 ('model_eligibility', {'local_only': False}, 'effects')]:
            row = unit(); row[key] = value
            self.error(code, C.validate_plan, request(), {'id': 'bad', 'contracts': [row]})
        a = unit(); b = unit('other', 'helper')
        a['output_artifacts'] = b['output_artifacts'] = ['result.js']
        self.error('write_conflict', C.validate_plan, request(), {'id': 'bad', 'contracts': [a, b]})

    def test_proven_never_comes_from_coverage_or_failed_refinement(self):
        req = request(); req['requirements'][0]['acceptance'] = 'PROVEN'
        self.error('refinement_unproven', C.validate_plan, req, plan())
        row = unit(); row['verification_obligations'] = [obligation()]
        result = C.validate_plan(req, {'id': 'finite', 'contracts': [row]})
        self.assertEqual(result['refinements'][0]['status'], 'PROVEN')
        self.assertEqual(result['refinements'][0]['prose_or_program_correctness'], 'not_established')
        self.assertIn('pending_execution_and_refinement_linkage', result['assurance'])

    def test_check_and_content_hash_cannot_be_forged(self):
        value = plan(); value['contracts'][0]['verification_obligations'] = []
        self.error('checks', C.validate_plan, request(), value)
        value = plan(); value['contracts'][0]['content_hash'] = '0' * 64
        self.error('content_hash', C.validate_plan, request(), value)
        value = plan(); value['contracts'][0]['unit']['examples'] = []
        self.error('checks', C.validate_plan, request(), value)

    def test_refinement_exact_exhaustion_and_counterexample(self):
        from symblic.kernel import language as S
        with mock.patch.object(S, 'kernel_id', side_effect=AssertionError('must not probe optional runtimes')):
            good = C.validate_refinement(obligation())
        self.assertEqual((good['status'], good['tested_cases'], good['premise_cases']), ('PROVEN', 4, 2))
        value = obligation(); value['conclusions'] = ['x > 1']
        bad = C.validate_refinement(value)
        self.assertEqual(bad['status'], 'REFUTED')
        self.assertEqual(bad['counterexample'], {'x': 1})

    def test_vacuity_undefined_and_budget_are_visible(self):
        value = obligation(); value['premises'] = ['x > 10']
        self.assertEqual(C.validate_refinement(value)['status'], 'UNPROVEN')
        value = obligation(); value['max_steps'] = 1
        self.assertEqual(C.validate_refinement(value)['status'], 'TIMEOUT')
        value = obligation(); value['max_cases'] = 1
        self.assertEqual(C.validate_refinement(value)['reason'], 'domain_budget')
        value = obligation(); value['premises'] = []; value['conclusions'] = ['1 / x > 0']
        self.assertEqual(C.validate_refinement(value)['status'], 'REFUTED')

    def test_no_native_effect_or_js_adapter_can_hide_in_predicate_ast(self):
        from symblic.kernel import language as S
        for expression in ('js_test("x", []) = true', 'x = js_test("x", [])', '1 < js_test("x", []) < 9', 'eval("1") = 1'):
            value = obligation(); value['conclusions'] = [expression]
            with mock.patch.object(S.Kernel, 'eval', side_effect=AssertionError('must never execute')):
                self.assertEqual(C.validate_refinement(value)['status'], 'UNKNOWN')

    def test_request_cycles_and_custom_types_are_refused(self):
        value = []; value.append(value)
        self.error('cycle', C.digest, value)
        self.error('json_type', C.digest, {'float': 0.5})


if __name__ == '__main__':
    unittest.main()

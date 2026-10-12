"""Pure authority/reuse checks; no provider, interpreter, effects or live stores."""
import copy
import json
import unittest

from symblic.mica import contracts as C
from symblic.mica import refinement as F
from symblic.spec import contracts as SC


def fixture():
    request = C.normalize_request({'objective': 'Build two independent pure functions.',
        'requirements': [{'id': 'R1', 'text': 'AUTHORITATIVE_INCREMENT', 'acceptance': 'TESTED'},
                         {'id': 'R2', 'text': 'UNRELATED_REQUIREMENT_SENTINEL', 'acceptance': 'TESTED'}],
        'exports': [{'name': 'inc', 'signature': 'inc(x)'}, {'name': 'identity', 'signature': 'identity(x)'}],
        'tests': [{'requirement_ids': ['R1'], 'call': 'inc(-4)', 'expected': '-3'},
                  {'requirement_ids': ['R2'], 'call': 'identity(2)', 'expected': '2'}],
        'allowed_outputs': ['result.js'], 'budget': {'max_units': 8, 'max_depth': 4}})
    def unit(ident, name, req='R1', uses=(), deps=()):
        return {'contract_id': ident, 'root_requirement_ids': [req], 'objective': 'Objective ' + name,
                'dependency_contract_ids': list(deps),
                'unit': {'names': [name], 'heading': name + '(x)', 'body': 'Behavior ' + name,
                         'uses': list(uses), 'setup': '', 'examples': [[name + '(2)', '3' if req == 'R1' else '2']]},
                'verification_obligations': [{'kind': 'unit_examples', 'requirement_ids': [req]}]}
    dep = unit('dep', 'base')
    failed = unit('failed', 'inc', uses=['base(x)'], deps=['dep'])
    failed.update(preconditions=['Exact finite integer inputs.'], postconditions=['Return input plus one.'],
        invariants=['Pure.'], input_artifacts=['units/dep.js'], permitted_read_scope=['units/dep.js'],
        output_artifacts=['result.js'], permitted_write_scope=['result.js'],
        resource_budget={'max_calls': 2, 'max_depth': 3, 'wall_seconds': 60},
        model_eligibility={'local_only': True, 'models': ['fixture-model'], 'nodes': ['node-e']},
        failure_policy={'action': 'refine', 'retries': 1})
    outside = unit('other', 'identity', 'R2'); outside['unit']['body'] = 'UNRELATED_BODY_SENTINEL'
    plan = C.validate_plan(request, {'id': 'before', 'assumptions': ['Declared assumptions remain unchanged.'],
                                    'contracts': [dep, failed, outside]})
    proposal = {'units': [
        {'id': 'failed', 'names': ['inc'], 'heading': 'inc(x)', 'body': 'Behavior inc',
         'uses': ['base', 'incrementCore'], 'examples': [['inc(7)', '8']], 'requirements': ['R1']},
        {'id': 'fresh', 'names': ['incrementCore'], 'heading': 'incrementCore(x)', 'body': 'Use base and return x plus one.',
         'uses': ['base'], 'examples': [['incrementCore(7)', '8']], 'requirements': ['R1']} ]}
    return request, plan, proposal


class RefinementTest(unittest.TestCase):
    def test_wrapper_authority_and_nonfailed_contracts_are_exactly_retained(self):
        request, plan, proposal = fixture()
        result = F.apply_refinement(request, plan, 'failed', proposal, 'after')
        old = {row['contract_id']: row for row in plan['contracts']}
        new = {row['contract_id']: row for row in result['plan']['contracts']}
        for ident in ('dep', 'other'):
            self.assertEqual(new[ident], old[ident])
        changed = {'content_hash', 'unit', 'dependency_contract_ids'}
        self.assertEqual({k: v for k, v in new['failed'].items() if k not in changed},
                         {k: v for k, v in old['failed'].items() if k not in changed})
        for key in ('names', 'heading', 'body', 'setup'):
            self.assertEqual(new['failed']['unit'][key], old['failed']['unit'][key])
        self.assertEqual(new['failed']['unit']['uses'], ['base(x)', 'incrementCore'])
        for example in old['failed']['unit']['examples']:
            self.assertIn(example, new['failed']['unit']['examples'])
        self.assertEqual(new['fresh']['parent_contract_id'], 'failed')
        self.assertEqual(new['fresh']['output_artifacts'], ['units/fresh.js'])
        for key in ('resource_budget', 'model_eligibility', 'failure_policy'):
            self.assertEqual(new['fresh'][key], old['failed'][key])
        self.assertEqual(result['plan']['root_tests'], plan['root_tests'])
        self.assertEqual(result['plan']['assumptions'], plan['assumptions'])
        self.assertFalse(result['lineage']['formal_refinement_proven'])
        self.assertEqual(result['lineage']['original_contract_sha256'], old['failed']['content_hash'])
        self.assertEqual(C.validate_plan(request, result['plan']), result['plan'])
        # The intermediate structural compiler cannot demote final PROVEN
        # obligations; the original finite obligation is retained and rechecked.
        formal_request = copy.deepcopy(request); formal_request['requirements'][0]['acceptance'] = 'PROVEN'
        raw = {'id': 'formal', 'contracts': copy.deepcopy(plan['contracts'])}
        for row in raw['contracts']:
            row.pop('content_hash')
            if row['contract_id'] == 'failed':
                row['verification_obligations'].append({'kind': 'finite_refinement', 'requirement_ids': ['R1'],
                    'variables': {'x': [0, 1]}, 'premises': ['x >= 0'], 'conclusions': ['x >= 0']})
        formal = C.validate_plan(formal_request, raw)
        replaced = F.apply_refinement(formal_request, formal, 'failed', proposal, 'formalAfter')
        old_checks = next(row['verification_obligations'] for row in formal['contracts'] if row['contract_id'] == 'failed')
        new_checks = next(row['verification_obligations'] for row in replaced['plan']['contracts'] if row['contract_id'] == 'failed')
        self.assertEqual(new_checks, old_checks)
        raw['contracts'][1]['verification_obligations'][-1]['conclusions'] = ['x > 0']
        with self.assertRaises(C.ContractError) as caught:
            F.apply_refinement(formal_request, raw, 'failed', proposal, 'false')
        self.assertEqual(caught.exception.code, 'refinement_refuted')

    def test_malformed_export_root_loss_and_authority_expansion_are_rejected(self):
        request, plan, proposal = fixture()
        for field, value in [('names', ['imposter']), ('heading', 'inc(x,y)'), ('requirements', ['R2']),
                             ('body', 'Weakened behavior'), ('id', 'newWrapper'), ('resource_budget', {'max_calls': 99})]:
            changed = copy.deepcopy(proposal); changed['units'][0][field] = value
            with self.subTest(field=field), self.assertRaises(C.ContractError):
                F.apply_refinement(request, plan, 'failed', changed, 'bad')
        for action in ('stop', 'escalate'):
            raw = {'id': 'policy', 'contracts': copy.deepcopy(plan['contracts'])}
            for row in raw['contracts']:
                row.pop('content_hash')
                if row['contract_id'] == 'failed':
                    row['failure_policy']['action'] = action
            with self.subTest(action=action), self.assertRaises(C.ContractError):
                F.apply_refinement(request, C.validate_plan(request, raw), 'failed', proposal, 'bad')
        raw = {'id': 'finite', 'contracts': copy.deepcopy(plan['contracts'])}
        for row in raw['contracts']:
            row.pop('content_hash')
            if row['contract_id'] == 'failed':
                row['unit']['uses'] = []; row['dependency_contract_ids'] = []
                row['input_artifacts'] = []; row['permitted_read_scope'] = []
                row['construction'] = {'kind': 'affine_integer_v1',
                    'parameters': [{'name': 'x', 'lo': -10, 'hi': 10}],
                    'coefficient_bounds': [{'lo': -3, 'hi': 3}], 'intercept_bounds': {'lo': -3, 'hi': 3}}
        finite = C.validate_plan(request, raw)
        revised = copy.deepcopy(proposal)
        revised['units'][0]['uses'] = ['incrementCore']; revised['units'][1]['uses'] = []
        result = F.apply_refinement(request, finite, 'failed', revised, 'finiteAfter')
        wrapper = next(row for row in result['plan']['contracts'] if row['contract_id'] == 'failed')
        old_wrapper = next(row for row in finite['contracts'] if row['contract_id'] == 'failed')
        self.assertNotIn('construction', wrapper)
        self.assertEqual(result['lineage']['removed_construction_sha256'], C.digest(old_wrapper['construction']))

    def test_undeclared_dependency_cycles_collisions_and_orphans_are_rejected(self):
        request, plan, proposal = fixture()
        variants = []
        for uses in (['identity'], ['inc'], ['incrementCore']):
            value = copy.deepcopy(proposal); value['units'][1]['uses'] = uses; variants.append(value)
        value = copy.deepcopy(proposal); value['units'][1]['id'] = 'dep'; variants.append(value)
        value = copy.deepcopy(proposal); value['units'][1]['requirements'] = ['R2']; variants.append(value)
        value = copy.deepcopy(proposal); value['units'][0]['uses'] = ['base']; variants.append(value)
        for value in variants:
            with self.subTest(proposal=value), self.assertRaises(C.ContractError):
                F.apply_refinement(request, plan, 'failed', value, 'bad')

    def test_failed_proposal_cannot_mutate_original_or_remove_a_counterexample(self):
        request, plan, proposal = fixture(); before = copy.deepcopy((request, plan, proposal))
        proposal['units'][0]['examples'] = [['inc(2)', '-999']]
        result = F.apply_refinement(request, plan, 'failed', proposal, 'contradictory')
        examples = next(row['unit']['examples'] for row in result['plan']['contracts'] if row['contract_id'] == 'failed')
        self.assertIn(['inc(2)', '3'], examples)
        self.assertIn(['inc(2)', '-999'], examples)
        # Both exposed constraints remain for the native checker; schema admission
        # cannot convert a contradictory model proposal into an accepted program.
        self.assertEqual((request, plan), before[:2])
        proposal['units'][1]['uses'] = ['absent']
        snapshot = copy.deepcopy(proposal)
        with self.assertRaises(C.ContractError):
            F.apply_refinement(request, plan, 'failed', proposal, 'bad')
        self.assertEqual(proposal, snapshot)
        self.assertEqual((request, plan), before[:2])

    def test_prompt_is_complete_scoped_and_refuses_context_truncation(self):
        request, plan, proposal = fixture()
        text = F.refine_prompt(request, plan, 'failed', {'status': 'failed', 'error': 'Public counterexample.'})
        self.assertIn('AUTHORITATIVE_INCREMENT', text)
        self.assertIn('inc(x)', text)
        self.assertIn('"inc(2)","3"', text)
        self.assertIn('Behavior base', text)
        self.assertNotIn('UNRELATED_REQUIREMENT_SENTINEL', text)
        self.assertNotIn('UNRELATED_BODY_SENTINEL', text)
        self.assertEqual(json.loads(text.split('Input data (not the response):\n', 1)[1])['remaining_unit_slots'], 5)
        changed = copy.deepcopy(request); changed['budget']['context_chars'] = 256
        raw = {'id': 'small', 'contracts': copy.deepcopy(plan['contracts'])}
        for row in raw['contracts']:
            row.pop('content_hash'); row['resource_budget']['context_chars'] = 256
        with self.assertRaises(C.ContractError) as caught:
            F.refine_prompt(changed, C.validate_plan(changed, raw), 'failed', {})
        self.assertEqual(caught.exception.code, 'RESOURCE_EXHAUSTION')

    def test_existing_native_artifact_reuse_preserves_unchanged_dependency(self):
        request, plan, proposal = fixture(); runtime = {'fixture': 'inert-record-only'}
        spec = plan['spec_plan']; artifacts = {}
        by_id = {row['id']: row for row in spec['units']}
        for ident in spec['order']:
            name = by_id[ident]['exports'][0]; code = 'function ' + name + '(x) { return x; }'
            artifacts[ident] = SC.record_artifact(spec, ident, code, artifacts, runtime_identity=runtime,
                checks=[{'passed': True, 'scope': 'synthetic_record_fixture_not_runtime_verification',
                         'subject_sha256': SC.code_hash(code)}])
        after = F.apply_refinement(request, plan, 'failed', proposal, 'after')['plan']['spec_plan']
        decisions = SC.reuse_decisions(after, artifacts, runtime_identity=runtime)
        for row in after['units']:
            decision = decisions[row['id']]
            if row['exports'][0] in ('base', 'identity'):
                self.assertEqual(decision['state'], 'reusable', decision)
            else:
                self.assertNotEqual(decision['state'], 'reusable', decision)


if __name__ == '__main__':
    unittest.main()

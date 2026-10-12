"""Imported declaration premises remain conditional; fake modules/answers only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.lang import abstraction as L
from symblic.kernel import evidence as E
from symblic.kernel import run as SR
from tests.kernel.test_symblic_core_repair_run import lineage_run, assessment, root_ids, Answers


MODULE = 'fact allowed(10).\nfunction seen(v:Int)->Bool = holds allowed(v).\n'


class ModuleProvenance(unittest.TestCase):
    def execute(self, source, modules, *answers, profile='verified'):
        with patch.object(L, 'saved_source', side_effect=lambda name: modules.get(name)):
            run, report, apps = lineage_run(source, *answers, profile=profile)
        return run, report, apps

    def done(self, *args, **kwargs):
        run, report, apps = self.execute(*args, **kwargs)
        self.assertEqual(report['status'], 'done', report.get('error'))
        return run, report, apps

    def facts(self, run):
        return [b for b in run._epistemic_knowledge if b.meta.get('_epistemic_module')]

    def exact_roots(self, run, name):
        return run._root_ids(run.kernel.env.lookup(name).meta['epistemic']['claim']['id'])

    def module_roots(self, run, name):
        return {run._epistemic_claims[ident]['content']['module']['key']
                for ident in self.exact_roots(run, name)
                if run._epistemic_claims[ident]['content'].get('module')}

    def assert_premises(self, run, name):
        facts = self.facts(run)
        self.assertTrue(facts, 'module facts/rules must have recorded premises')
        self.assertLessEqual({b.meta['epistemic']['claim']['id'] for b in facts}, self.exact_roots(run, name))
        for binding in facts:
            claim = binding.meta['epistemic']['claim']
            self.assertEqual(claim['origin'], 'owner_premise')
            self.assertEqual(claim['content']['module'], binding.meta['_epistemic_module'])
            self.assertEqual(binding.meta['epistemic']['assessment']['empirical_truth'], 'not_established')
        self.assertEqual(assessment(run, name)['empirical_truth'], 'not_established')

    def test_import_before_ask_keeps_exact_module_fact_premise_in_both_profiles(self):
        for profile in ('legacy', 'verified'):
            with self.subTest(profile=profile):
                run, _, apps = self.done('import "Facts" as c.\nask x:Int "x" with effort=low.\n'
                    'ensure c.seen(x) else retry.\nlet doubled=x*2.', {'Facts': MODULE}, 10, profile=profile)
                self.assertEqual(len(apps.requests), 1)
                self.assert_premises(run, 'x'); self.assert_premises(run, 'doubled')
                module = self.facts(run)[0].meta['_epistemic_module']
                self.assertEqual(module['source_sha256'], hashlib.sha256(MODULE.encode()).hexdigest())
                self.assertEqual(module['key'], 'saved:Facts')
                self.assertEqual(module['logic']['mode'], 'isolated' if profile == 'verified' else 'shared')

    def test_late_import_refines_acceptance_and_prior_derivations_without_erasing_proposal(self):
        for profile, votes, answers in [('verified', '', (10,)), ('legacy', ',votes=2', (10, 20))]:
            with self.subTest(profile=profile):
                run, _, apps = self.done(f'ask x:Int "x" with effort=low{votes}.\nlet doubled=x*2.\n'
                    'import "Facts" as c.\nensure c.seen(x) else retry.\nlet later=doubled+1.',
                    {'Facts': MODULE}, *answers, profile=profile)
                self.assertEqual(len(apps.requests), len(answers))
                proposal = next(r['epistemic']['claim'] for r in run.trace if r['kind'] == 'ask')
                self.assertEqual(proposal['origin'], 'model_proposal')
                self.assertEqual(proposal['content']['value_sha256'], run.kernel.env.lookup('x').meta['epistemic']['claim']['content']['value_sha256'])
                for name, expected in [('x', 10), ('doubled', 20), ('later', 21)]:
                    self.assertEqual(run.kernel.env.lookup(name).value, expected)
                    self.assert_premises(run, name)
                    self.assertIn(proposal['id'], root_ids(run, name))
                    self.assertEqual(assessment(run, name)['admissible'], profile == 'verified')
                for receipt in run.checks:
                    self.assertEqual(receipt['id'], E.digest({k: v for k, v in receipt.items() if k != 'id'}))
                accepted = next(r['acceptance_lineage'] for r in run.trace if r.get('acceptance_lineage'))
                self.assertEqual(accepted['check_id'], run.checks[0]['id'])
                self.assertEqual(set(accepted['bindings']), {'x', 'doubled'})

    def test_nested_predicate_imports_and_rules_keep_both_source_premises(self):
        modules = {'Leaf': 'fact edge(a,b).', 'Top': 'import "Leaf" as leaf.\n'
                   'rule reachable(X,Y) if leaf.edge(X,Y).\nfunction seen()=holds reachable(a,b).'}
        run, _, apps = self.done('import "Top" as top.\nlet answer=top.seen().', modules)
        self.assertEqual(apps.requests, [])
        self.assertTrue(run.kernel.env.lookup('answer').value)
        self.assert_premises(run, 'answer')
        self.assertEqual({b.meta['_epistemic_module']['key'] for b in self.facts(run)}, {'saved:Leaf', 'saved:Top'})

    def test_aliases_reuse_one_module_premise_and_do_not_change_namespace_values(self):
        modules = {'Red': 'fact item(red).\nfunction rows()=query item(X).',
                   'Blue': 'fact item(blue).\nfunction rows()=query item(X).'}
        run, _, _ = self.done('import "Red" as a.\nimport "Red" as b.\nimport "Blue" as c.\n'
                              'let red=a.rows().\nlet again=b.rows().\nlet blue=c.rows().', modules)
        self.assertEqual(S.to_plain(run.kernel.env.lookup('red').value), ['red'])
        self.assertEqual(S.to_plain(run.kernel.env.lookup('again').value), ['red'])
        self.assertEqual(S.to_plain(run.kernel.env.lookup('blue').value), ['blue'])
        self.assertEqual(len(self.facts(run)), 2)
        self.assertEqual(self.module_roots(run, 'red'), {'saved:Red'})
        self.assertEqual(self.module_roots(run, 'again'), {'saved:Red'})
        self.assertEqual(self.module_roots(run, 'blue'), {'saved:Blue'})
        self.assertNotEqual(L.state(run).modules['saved:Red'].logic_namespace,
                            L.state(run).modules['saved:Blue'].logic_namespace)

    def test_actual_check_excludes_other_namespaces_and_skipped_query_branches(self):
        for early in (True, False):
            for skipped in (True, False):
                with self.subTest(early=early, skipped=skipped):
                    imports = 'import "Red" as red.\nimport "Blue" as blue.\n'
                    ask = 'ask x:Int "x" with effort=low,context=none.\n'
                    check = 'true or red.seen(x)' if skipped else 'red.seen(x)'
                    run, _, _ = self.done((imports + ask if early else ask + imports) +
                        f'ensure {check} else retry.\nlet later=x.', {'Red': MODULE, 'Blue': MODULE}, 10)
                    expected = set() if skipped else {'saved:Red'}
                    for name in ('x', 'later'):
                        self.assertEqual(self.module_roots(run, name), expected)
                    self.assertEqual(bool([r for r in run.trace if r.get('acceptance_lineage')]), not skipped)

    def test_negative_rule_inputs_retain_transitive_module_premises_only(self):
        modules = {'Leaf': 'fact edge(a,b).\nfact blocked(c).',
                   'Top': 'import "Leaf" as leaf.\n'
                   'rule clear(X,Y) if leaf.edge(X,Y), not leaf.blocked(Y).\n'
                   'function seen()=holds clear(a,b).', 'Unused': MODULE}
        run, _, _ = self.done('import "Top" as top.\nimport "Unused" as unused.\n'
                              'let answer=top.seen().', modules)
        self.assertTrue(run.kernel.env.lookup('answer').value)
        self.assertEqual(self.module_roots(run, 'answer'), {'saved:Leaf', 'saved:Top'})
        used = {b.meta['epistemic']['claim']['id'] for b in self.facts(run)
                if b.meta['_epistemic_module']['key'] != 'saved:Unused'}
        self.assertLessEqual(used, root_ids(run, 'answer'))

    def test_derived_boolean_check_retains_original_module_ancestry(self):
        for early in (False, True):
            with self.subTest(early=early):
                imports = 'import "Red" as red.\nimport "Blue" as blue.\n'
                ask = 'ask x:Int "x" with effort=low,context=none.\n'
                run, _, apps = self.done((imports + ask if early else ask + imports) +
                    'let gate=red.seen(x).\nensure gate else retry.\nlet later=x.',
                    {'Red': MODULE, 'Blue': MODULE}, 10)
                self.assertEqual(len(apps.requests), 1)
                for name in ('x', 'gate', 'later'):
                    self.assertEqual(self.module_roots(run, name), {'saved:Red'})
                for receipt in run.checks:
                    self.assertEqual(receipt['id'], E.digest({k: v for k, v in receipt.items() if k != 'id'}))

    def test_more_than_64_module_premises_keep_exact_root_set(self):
        module = '\n'.join(f'fact allowed({i}).' for i in range(65)) + '\nfunction seen(v)=holds allowed(v).'
        run, _, _ = self.done('ask x:Int "x" with effort=low,context=none.\n'
                             'import "Many" as c.\nensure c.seen(x) else retry.', {'Many': module}, 10)
        self.assert_premises(run, 'x')
        self.assertEqual(len(self.exact_roots(run, 'x')), 66)
        self.assertIn('roots_omitted', assessment(run, 'x'))
        self.assertTrue(assessment(run, 'x')['admissible'])

    def test_shared_legacy_predicates_retain_both_modules_and_main_static_scope(self):
        modules = {'Red': 'fact allowed(10).\nfunction seen(v)=holds allowed(v).',
                   'Blue': 'fact allowed(20).'}
        run, _, _ = self.done('fact unrelated(owner).\nimport "Red" as red.\nimport "Blue" as blue.\n'
                              'let answer=red.seen(10).', modules, profile='legacy')
        self.assertEqual(self.module_roots(run, 'answer'), {'saved:Red', 'saved:Blue'})
        main = {b.meta['epistemic']['claim']['id'] for b in run._epistemic_knowledge
                if not b.meta.get('_epistemic_module')}
        self.assertLessEqual(main, root_ids(run, 'answer'))

    def test_full_fact_context_keeps_all_transmitted_premises(self):
        run, _, _ = self.done('import "Red" as red.\nimport "Blue" as blue.\n'
                              'ask x:Int "x" with effort=low,context=facts.',
                              {'Red': MODULE, 'Blue': MODULE}, 10)
        self.assertEqual(self.module_roots(run, 'x'), {'saved:Red', 'saved:Blue'})

    def test_optional_kernel_query_observer_preserves_no_argument_callback(self):
        kernel = S.Kernel()
        kernel.kb.add_fact('entry', ('a',))
        query = S.parse('let result=holds entry(a).')['statements'][0].value
        old_calls, selected = [], []
        kernel.knowledge_read = lambda: old_calls.append(True)
        self.assertTrue(kernel.eval(query))
        kernel.knowledge_predicate_read = selected.append
        self.assertTrue(kernel.eval(query))
        self.assertEqual(old_calls, [True])
        self.assertEqual(selected, ['entry'])

    def test_model_dependent_module_constant_default_and_fact_keep_contested_origin(self):
        module = ('routine construct_amount()->Int do\nask v:Int "module value" with effort=low,votes=2.\nreturn v.\nend.\n'
                  'let cap=construct_amount().\nfunction defaulted_amount(v:Int=cap)->Int=v.\nfact allowed(defaulted_amount()).\n'
                  'function seen(v:Int)->Bool=holds allowed(v).')
        run, _, apps = self.done('import "Dynamic" as c.\nlet answer=c.seen(10).', {'Dynamic': module},
                                 10, 20, profile='legacy')
        self.assertEqual(len(apps.requests), 2)
        self.assert_premises(run, 'answer')
        self.assertIn(('model_proposal', 'contested'),
                      {(r['origin'], r['status']) for r in assessment(run, 'answer')['conditional_on']})
        self.assertFalse(assessment(run, 'answer')['admissible'])
        _, report, apps = self.execute('import "Dynamic" as c.', {'Dynamic': module}, 10, profile='verified')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(apps.requests, [])

    def test_retry_after_successful_late_check_restores_refinement_and_module_premises(self):
        module = 'fact allowed(9),allowed(10).\nfunction seen(v:Int)->Bool=holds allowed(v).'
        run, _, apps = self.done('ask x:Int "x" with effort=low,retries=1.\nlet doubled=x*2.\n'
            'import "Facts" as c.\nensure c.seen(x) else retry.\nensure x=10 else retry.\nlet final=doubled.',
            {'Facts': module}, 9, 10)
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(run.kernel.env.lookup('final').value, 20)
        self.assertEqual(len(self.facts(run)), 1)
        self.assert_premises(run, 'final')
        self.assertFalse(set(run._epistemic_rootsets) - run._epistemic_claims.keys())
        self.assertTrue(all(d['id'] in run._epistemic_claims for c in run._epistemic_claims.values() for d in c['dependencies']))

    def test_unrelated_late_import_does_not_refine_nonquery_check(self):
        run, _, _ = self.done('ask x:Int "x" with effort=low.\nimport "Facts" as c.\n'
                              'ensure x>0 else retry.', {'Facts': MODULE}, 10)
        original = next(r['epistemic']['claim']['id'] for r in run.trace if r['kind'] == 'ask')
        self.assertEqual(run.kernel.env.lookup('x').meta['epistemic']['claim']['id'], original)
        self.assertTrue(self.facts(run))

    def test_replay_uses_retained_module_source_and_keeps_acceptance_receipt_binding(self):
        source = 'ask x:Int "x" with effort=low.\nimport "Facts" as c.\nensure c.seen(x) else retry.\n'
        with tempfile.TemporaryDirectory() as folder:
            options = {'by': 'fake:a', 'profile': 'verified', 'max_calls': 1}
            with patch.object(L, 'saved_source', return_value=MODULE):
                apps = Answers(10)
                first = SR.Run(source, applicators=apps, options=options, folder=folder)
                report = first.execute()
            self.assertEqual(report['status'], 'done', report.get('error'))
            self.assertEqual(len(apps.requests), 1)
            no_models = Answers()
            with patch.object(L, 'saved_source', side_effect=AssertionError('Replay must use retained source')):
                replay = SR.Run(source, applicators=no_models, options={**options, 'replay': True}, folder=folder)
                checked = replay.execute()
            self.assertEqual(checked['status'], 'done', checked.get('error'))
            self.assertEqual(no_models.requests, [])
            self.assertEqual(checked['calls'], 0)
            self.assertEqual(assessment(first, 'x'), assessment(replay, 'x'))
            self.assert_premises(replay, 'x')
            traces = [json.loads(line) for line in (Path(folder) / 'trace.jsonl').read_text().splitlines()]
            acceptance = [r['acceptance_lineage'] for r in traces if r.get('acceptance_lineage')]
            self.assertEqual(len(acceptance), 2)
            self.assertEqual(acceptance[0], acceptance[1])


if __name__ == '__main__':
    unittest.main()

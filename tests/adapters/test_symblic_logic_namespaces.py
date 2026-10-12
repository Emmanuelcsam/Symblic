"""Module Datalog isolation/explicit sharing; fake modules and temporary stores only."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.lang import abstraction as L
from symblic.kernel import lockfile as K
from symblic.kernel import run as SR


class NoModels:
    def __init__(self):
        self.calls = 0

    def call(self, request):
        self.calls += 1
        raise AssertionError('A module declaration must not reach a provider')


def relation(value):
    return f'fact item({value}).\nfunction items() = query item(X).\n'


def binding(report, name):
    return next(row['value'] for row in report['bindings'] if row['name'] == name)


class LogicNamespaces(unittest.TestCase):
    def setUp(self):
        L.register()

    def execute(self, source, modules, *, profile='verified', folder=None, **options):
        apps = NoModels()
        with patch.object(L, 'saved_source', side_effect=lambda name: modules.get(name)):
            run = SR.Run(source, applicators=apps, folder=folder,
                         options={'profile': profile, 'by': 'fake:a', **options})
            report = run.execute()
        self.assertEqual(apps.calls, 0)
        return run, report

    def done(self, source, modules, **kwargs):
        run, report = self.execute(source, modules, **kwargs)
        self.assertEqual(report['status'], 'done', report.get('error'))
        return run, report

    def test_same_predicate_in_two_modules_and_caller_has_no_crosstalk(self):
        source = ('fact item(caller).\nimport "Red" as red.\nimport "Blue" as blue.\n'
                  'let r = red.items().\nlet b = blue.items().\nlet c = query item(X).\n')
        run, report = self.done(source, {'Red': relation('red'), 'Blue': relation('blue')})
        self.assertEqual(binding(report, 'r'), ['red'])
        self.assertEqual(binding(report, 'b'), ['blue'])
        self.assertEqual(binding(report, 'c'), ['caller'])
        modules = L.state(run).modules
        self.assertNotEqual(modules['saved:Red'].logic_namespace, modules['saved:Blue'].logic_namespace)

    def test_aliases_of_same_module_keep_one_identity(self):
        run, report = self.done('import "Rows" as a.\nimport "Rows" as b.\n'
                                'let x = a.items().\nlet y = b.items().\n', {'Rows': relation('one')})
        self.assertEqual(binding(report, 'x'), binding(report, 'y'))
        self.assertEqual(len(L.state(run).modules), 1)
        self.assertEqual(run.kernel.kb.fact_count(), 1)

    def test_saved_titles_with_same_normalized_modid_do_not_share_helpers(self):
        _, report = self.done('import "A B" as a.\nimport "A-B" as b.\n'
                              'let x = a.items().\nlet y = b.items().\n',
                              {'A B': relation('first'), 'A-B': relation('second')})
        self.assertEqual(binding(report, 'x'), ['first'])
        self.assertEqual(binding(report, 'y'), ['second'])

    def test_transitive_rules_negative_literals_and_nested_expressions_rewrite(self):
        graph = ('fact edge(a, b), edge(b, c), blocked(c).\n'
                 'rule reach(X, Y) if edge(X, Y).\n'
                 'rule reach(X, Z) if edge(X, Y) and reach(Y, Z).\n'
                 'rule allowed(X, Y) if reach(X, Y) and not blocked(Y).\n'
                 'function count_allowed() = len(query allowed(X, Y)).\n'
                 'function has_path() = if holds reach(a, c) then count_allowed() else 0.\n')
        _, report = self.done('fact blocked(b).\nimport "Graph" as g.\nlet n = g.has_path().\n', {'Graph': graph})
        self.assertEqual(binding(report, 'n'), 1)

    def test_predicate_references_in_routine_bodies_and_defaults_are_local(self):
        module = ('fact item(initial).\n'
                  'routine add(value: Text) do\n fact item(value).\n return len(query item(X)).\nend.\n'
                  'function row_count(rows = query item(X)) = len(rows).\n')
        _, report = self.done('fact item(outside).\nimport "Bag" as bag.\n'
                              'let added = bag.add("later").\nlet n = bag.row_count().\n', {'Bag': module})
        self.assertEqual(binding(report, 'added'), 2)
        self.assertEqual(binding(report, 'n'), 2)

    def test_qualified_child_predicate_import_is_an_explicit_read_dependency(self):
        modules = {'Child': 'fact edge(a, b), edge(b, c).\n',
                   'Parent': ('import "Child" as child.\nrule reach(X, Y) if child.edge(X, Y).\n'
                              'rule reach(X, Z) if child.edge(X, Y) and reach(Y, Z).\n'
                              'function nodes() = query reach(a, X).\n')}
        run, report = self.done('fact edge(a, outside).\nimport "Parent" as p.\nlet xs = p.nodes().\n', modules)
        self.assertEqual(binding(report, 'xs'), ['b', 'c'])
        parent = L.state(run).modules['saved:Parent']
        child = L.state(run).modules['saved:Child']
        self.assertEqual(parent.logic_imports['child.edge']['predicate'], child.predicates['edge'])

    def test_selective_relation_import_reexports_through_nested_modules(self):
        modules = {'Leaf': relation('leaf'), 'Middle': 'import item from "Leaf".\n',
                   'Top': 'import item from "Middle".\nfunction rows() = query item(X).\n'}
        _, report = self.done('import "Top" as top.\nlet xs = top.rows().\n', modules)
        self.assertEqual(binding(report, 'xs'), ['leaf'])

    def test_transitive_imported_helper_keeps_child_lexical_namespace(self):
        modules = {'Child': relation('child'),
                   'Parent': 'import "Child" as c.\nfact item(parent).\nfunction child_rows() = c.items().\n'}
        _, report = self.done('import "Parent" as p.\nlet xs = p.child_rows().\n', modules)
        self.assertEqual(binding(report, 'xs'), ['child'])

    def test_undeclared_extensional_dependency_is_a_diagnostic_not_empty_relation(self):
        module = 'rule child(X, Y) if parent(Y, X).\nfunction children() = query child(X, Y).\n'
        _, report = self.execute('fact parent(a, b).\nimport "Needs Parent" as m.\n', {'Needs Parent': module})
        self.assertEqual(report['status'], 'failed')
        self.assertIn('undeclared external predicates parent', report['error']['message'])
        self.assertIn('module_logic', report['error']['message'])

    def test_test_only_facts_do_not_silently_declare_runtime_external_inputs(self):
        module = ('rule derived(X) if outside(X).\n'
                  'test "fixture" do\n fact outside(a).\n assert holds derived(a).\nend.\n')
        _, report = self.execute('import "Hidden Input".\n', {'Hidden Input': module})
        self.assertEqual(report['status'], 'failed')
        self.assertIn('undeclared external predicates outside', report['error']['message'])

    def test_imported_predicate_cannot_be_written_by_another_module(self):
        modules = {'Child': relation('child'),
                   'Parent': 'import item from "Child".\nfact item(parent).\n'}
        _, report = self.execute('import "Parent".\n', modules)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('multiple owners', report['error']['message'])

    def test_unqualified_import_conflict_requires_explicit_alias(self):
        modules = {'A': relation('a'), 'B': relation('b'),
                   'Parent': 'import item from "A".\nimport item from "B".\n'}
        _, report = self.execute('import "Parent".\n', modules)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('multiple owners', report['error']['message'])

    def test_top_level_relation_import_points_to_helper_contract(self):
        _, report = self.execute('import item from "Rows".\n', {'Rows': relation('row')})
        self.assertEqual(report['status'], 'failed')
        self.assertIn('module query helper', report['error']['message'])

    def test_legacy_shared_logic_composition_still_works(self):
        _, report = self.done('fact item(caller).\nimport "A" as a.\nimport "B" as b.\n'
                              'let xs = a.items().\n', {'A': relation('a'), 'B': relation('b')}, profile='legacy')
        self.assertEqual(binding(report, 'xs'), ['a', 'b', 'caller'])

    def test_verified_explicit_shared_policy_preserves_kinship_library(self):
        _, report = self.done('fact parent(ada, ben), parent(ben, cy).\nimport kinship.\n'
                              'let yes = holds ancestor(ada, cy).\n', {}, module_logic={'lib:kinship': 'shared'})
        self.assertTrue(binding(report, 'yes'))

    def test_terms_still_conflict_even_when_logic_is_isolated(self):
        modules = {'A': 'term unit means "metres".\n', 'B': 'term unit means "inches".\n'}
        _, report = self.execute('import "A" as a.\nimport "B" as b.\n', modules)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('means different things', report['error']['message'])

    def test_verified_module_initialization_cannot_call_routine_or_external_adapter(self):
        modules = [
            'routine r() do\n ask x: Int "Number."\n return x.\nend.\nlet x = r().\n',
            'routine r() do\n ask x: Int "Number."\n return x.\nend.\nfunction f() = r().\nlet x = f().\n',
            'let x = js_run("throw 1", []).\n',
        ]
        for module in modules:
            with self.subTest(module=module):
                with patch.dict(S.BUILTINS, {'js_run': lambda *a, **k: self.fail('External adapter was executed')}):
                    _, report = self.execute('import "Unsafe" as m.\n', {'Unsafe': module})
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['error']['kind'], 'effect')

    def test_module_load_guard_restores_for_later_explicit_routine_execution(self):
        module = 'routine local() do\n return 7.\nend.\n'
        run, report = self.done('import "Pure Load" as m.\nlet x = m.local().\n', {'Pure Load': module})
        self.assertEqual(binding(report, 'x'), 7)
        self.assertEqual(L.state(run).local.pure_depth, 0)
        self.assertFalse(run.kernel.module_loading)

    def test_recorded_mode_namespace_imports_and_source_are_checked_on_resume(self):
        modules = {'Rows': relation('old')}
        source = 'import "Rows" as rows.\nlet xs = rows.items().\n'
        with tempfile.TemporaryDirectory(prefix='symblic-logic-module-') as folder:
            self.done(source, modules, folder=folder)
            path = Path(folder) / 'modules.json'
            record = json.loads(path.read_text())
            identity = record['saved:Rows']['logic']
            self.assertEqual(identity['mode'], 'isolated')
            self.assertEqual(identity['version'], L.MODULE_LOGIC_VERSION)
            self.assertTrue(identity['namespace'].startswith('__symmod_'))
            _, report = self.done(source, {'Rows': relation('new')}, folder=folder)
            self.assertEqual(binding(report, 'xs'), ['old'])
            for field, value in (('mode', 'shared'), ('namespace', 'other'), ('version', 999),
                                 ('imports', {'item': {'module': 'wrong', 'predicate': 'wrong'}})):
                tampered = copy.deepcopy(record)
                tampered['saved:Rows']['logic'][field] = value
                path.write_text(json.dumps(tampered))
                _, bad = self.execute(source, modules, folder=folder)
                self.assertEqual(bad['status'], 'failed')
                self.assertEqual(bad['error']['kind'], 'version')
            path.write_text(json.dumps(record))
            _, legacy = self.execute(source, modules, folder=folder, profile='legacy')
            self.assertEqual(legacy['status'], 'failed')
            self.assertEqual(legacy['error']['kind'], 'version')

    def test_historical_shared_record_replays_only_shared_semantics(self):
        module, source = relation('old'), 'import "Rows" as r.\nlet xs = r.items().\n'
        with tempfile.TemporaryDirectory(prefix='symblic-logic-historical-') as folder:
            row = {'source': module, 'sha256': hashlib.sha256(module.encode()).hexdigest(), 'origin': 'synthetic'}
            path = Path(folder) / 'modules.json'
            path.write_text(json.dumps({'saved:Rows': row}))
            _, bad = self.execute(source, {}, folder=folder)
            self.assertEqual(bad['status'], 'failed')
            self.assertIn('historical shared', bad['error']['message'])
            _, good = self.done(source, {}, folder=folder, profile='legacy')
            self.assertEqual(binding(good, 'xs'), ['old'])

    def test_plain_json_lock_replays_nested_imports_and_collision_identities(self):
        source = ('import "A B" as a.\nimport "A-B" as b.\nimport "Parent" as p.\n'
                  'let first_rows = a.items().\nlet second_rows = b.items().\nlet nested = p.rows().\n')
        modules = {'A B': relation('red'), 'A-B': relation('blue'),
                   'Parent': 'import "A B" as a.\nfunction rows() = query a.item(X).\n'}
        with tempfile.TemporaryDirectory(prefix='symblic-logic-lock-') as folder:
            Path(folder, 'program.sym').write_text(source)
            Path(folder, 'meta.json').write_text(json.dumps({'inputs': {}, 'options': {
                'profile': 'verified', 'by': 'fake:a', 'module_logic': {'saved:Parent': 'isolated'}}}))
            self.done(source, modules, folder=folder, module_logic={'saved:Parent': 'isolated'})
            lock = json.loads(json.dumps(K.make_lock(folder)))
            self.assertEqual(lock['options']['module_logic'], {'saved:Parent': 'isolated'})
            with patch.object(L, 'saved_source', side_effect=AssertionError('Replay must use pinned source')):
                result = K.replay(lock)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['refused'], [])
            self.assertEqual(binding(result['report'], 'first_rows'), ['red'])
            self.assertEqual(binding(result['report'], 'second_rows'), ['blue'])
            self.assertEqual(binding(result['report'], 'nested'), ['red'])

    def test_kernel_identity_names_module_logic_semantics(self):
        self.assertEqual(S.kernel_id()['module_logic'], L.MODULE_LOGIC_VERSION)


if __name__ == '__main__':
    unittest.main()

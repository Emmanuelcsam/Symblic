"""Real native parser/checker evidence; no ask execution or model calls."""
import hashlib
import json
import unittest
from unittest.mock import patch

from symblic.forge import core as C
from symblic.forge import exports as E
from symblic.forge.store import StoreError


class ForgeExportTests(unittest.TestCase):
    def setUp(self):
        self.p = C.snake_demo(project_id='forge_export_fixture')

    def test_generated_demo_uses_actual_native_checker_and_explicit_context(self):
        result = E.validate(self.p)
        self.assertTrue(result['ok'], result['diagnostics'])
        self.assertTrue(result['generated'])
        self.assertFalse(result['verification']['executed'])
        self.assertIn('context=none, determine=false, solve=false', result['source'])
        self.assertTrue(result['mapping'])
        self.assertEqual(result['fingerprint'], C.fingerprint(self.p))
        self.assertEqual(result['source_sha256'], hashlib.sha256(result['source'].encode()).hexdigest())

    def test_loaded_identity_is_immutable_and_reports_disk_drift_without_relabeling(self):
        baseline = E.source_identity()
        self.assertFalse(baseline['restart_required'])
        altered = dict(baseline['source_hashes'])
        altered['symblic/forge/core.py'] = '0' * 64
        baseline['source_hashes']['symblic/forge/core.py'] = 'caller-forgery'
        with patch.object(E, '_read_source_hashes', return_value=altered):
            identity = E.compiler_identity()
        self.assertTrue(identity['restart_required'])
        self.assertEqual(identity['changed_sources'], ['symblic/forge/core.py'])
        self.assertNotEqual(identity['source_hashes']['symblic/forge/core.py'], 'caller-forgery')
        self.assertNotEqual(identity['source_hashes']['symblic/forge/core.py'], altered['symblic/forge/core.py'])
        self.assertEqual(identity['disk_source_hashes']['symblic/forge/core.py'], '0' * 64)
        self.assertIsNone(identity['kernel'])

    def test_stale_loaded_source_refuses_before_generation_or_compiler_call(self):
        hashes = E.source_identity()['source_hashes']
        hashes['symblic/forge/exports.py'] = 'f' * 64
        with patch.object(E, '_read_source_hashes', return_value=hashes), \
                patch.object(E, 'native_source', side_effect=AssertionError('No generation while stale')), \
                patch('symblic.authoring.editor_diagnostics.check', side_effect=AssertionError('No compiler while stale')):
            with self.assertRaisesRegex(StoreError, 'restart required') as raised:
                E.validate(self.p)
        self.assertEqual(raised.exception.status, 503)

    def test_source_change_during_check_discards_receipt(self):
        pinned = E.source_identity()['source_hashes']
        changed = {**pinned, 'symblic/spec/sheets.py': 'e' * 64}
        with patch.object(E, '_read_source_hashes', side_effect=[pinned, changed]), \
                patch('symblic.authoring.editor_diagnostics.check', return_value={'ok': True, 'diagnostics': []}) as check:
            with self.assertRaisesRegex(StoreError, 'changed during validation') as raised:
                E.validate(self.p, 'program Fixture.\nlet x = 1.\nshow x.')
        self.assertEqual(check.call_count, 1)
        self.assertEqual(raised.exception.status, 503)

    def test_missing_pinned_source_is_visible_and_never_proven_current(self):
        hashes = E.source_identity()['source_hashes']
        hashes['symblic/kernel/embed.py'] = None
        with patch.object(E, '_read_source_hashes', return_value=hashes):
            identity = E.compiler_identity()
        self.assertTrue(identity['restart_required'])
        self.assertIn('symblic/kernel/embed.py', identity['changed_sources'])

    def test_custom_source_checks_even_without_accepted_project_and_no_false_lineage(self):
        p = C.new_project('An incomplete intention')
        with patch.object(E, 'native_source', side_effect=AssertionError('must not generate project')):
            result = E.validate(p, 'program Custom.\nlet fixture_value = 2.\nshow fixture_value.\n')
        self.assertTrue(result['ok'], result['diagnostics'])
        self.assertFalse(result['generated'])
        self.assertEqual(result['mapping'], [])
        self.assertFalse(result['verification']['executed'])

    def test_invalid_custom_source_reports_real_failure(self):
        result = E.validate(C.new_project('Idea'), 'not valid Symblic grammar')
        self.assertFalse(result['ok'])
        self.assertTrue(result['diagnostics'].get('diagnostics') or result['diagnostics'].get('errors'))

    def test_custom_source_utf8_limit_refuses_before_compiler_work(self):
        with patch('symblic.authoring.editor_diagnostics.check', side_effect=AssertionError('No checker call for oversized input')):
            with self.assertRaisesRegex(StoreError, '400,000 UTF-8 bytes'):
                E.validate(C.new_project('Idea'), '😀' * 100001)

    def test_rejected_generated_source_cannot_be_published_as_valid_native_artifact(self):
        with patch.object(E, 'validate', return_value={'ok': False, 'source': 'invalid'}):
            with self.assertRaisesRegex(StoreError, 'rejected'):
                E.artifact(self.p, 'symblic')

    def test_stale_revision_is_an_explicit_conflict_never_a_stale_artifact(self):
        stale = self.p['revision'] - 1
        with patch.object(E, 'native_source', side_effect=AssertionError('No generation for a stale revision')):
            for call in (lambda: E.validate(self.p, revision=stale),
                         lambda: E.artifact(self.p, 'manifest', revision=stale),
                         lambda: E.artifact(self.p, 'symblic', revision=stale)):
                with self.subTest(call=call):
                    with self.assertRaisesRegex(StoreError, 'changed in another operation') as raised:
                        call()
                    self.assertEqual(raised.exception.status, 409)
        artifact = E.artifact(self.p, 'prompt', revision=self.p['revision'])
        self.assertEqual(artifact['source_revision'], self.p['revision'])
        self.assertIn('fingerprint', artifact)

    def test_all_artifacts_hash_actual_bytes_and_do_not_mutate_revision(self):
        revision = self.p['revision']
        for kind in ('manifest', 'brief', 'prompt', 'construction', 'tasks', 'sheet'):
            artifact = E.artifact(self.p, kind)
            self.assertEqual(artifact['sha256'], hashlib.sha256(artifact['text'].encode()).hexdigest())
            self.assertEqual(artifact['source_revision'], revision)
        self.assertEqual(self.p['revision'], revision)

    def test_unaccepted_text_never_enters_accepted_prompt_or_native_source(self):
        p = C.transition(self.p, 'statement.propose', {'text': 'DO_NOT_PROMOTE_fixture'})
        self.assertNotIn('DO_NOT_PROMOTE_fixture', E.artifact(p, 'prompt')['text'])
        self.assertNotIn('DO_NOT_PROMOTE_fixture', E.native_source(p)[0])
        self.assertIn('DO_NOT_PROMOTE_fixture', E.artifact(p, 'manifest')['text'])

    def test_partial_answer_exports_retain_accepted_decision_meaning_without_rewriting_text(self):
        p = C.new_project('A browser canvas')
        for key, exact, value in [('viewport.width', '800 pixels', 800),
                                  ('viewport.height', 'six hundred pixels', 600)]:
            p = C.transition(p, 'statement.propose', {'text': exact,
                'fact': {'subject': 'project', 'predicate': key, 'value': value, 'unit': 'px'}})
            p = C.transition(p, 'statement.accept', {'id': C.active_branch(p)['statements'][-1]['id']})
        saved = json.dumps(p, sort_keys=True)
        prompt = E.artifact(p, 'prompt')['text']
        result = E.validate(p)
        self.assertTrue(result['ok'], result['diagnostics'])
        for key in ('viewport.width', 'viewport.height'):
            self.assertIn(key, prompt)
            self.assertIn(key, result['source'])
        self.assertIn('six hundred pixels', prompt)
        self.assertIn('"value":600', prompt.replace(' ', ''))
        self.assertEqual(json.dumps(p, sort_keys=True), saved)

    def test_task_capsules_and_construction_keep_fact_conditions_and_units(self):
        p = self.p
        b = C.active_branch(p)
        row = next(r for r in b['statements'] if r.get('fact', {}).get('predicate') == 'viewport.width')
        p = C.transition(p, 'statement.edit', {'id': row['id'],
            'text': '800 pixels', 'fact': {**row['fact'], 'condition': 'Main canvas'}})
        p = C.transition(p, 'statement.accept', {'id': row['id']})
        cards = E.task_cards(p)
        matches = [r for c in cards for r in c['requirements'] if r['id'] == row['id']]
        self.assertTrue(matches)
        for r in matches:
            self.assertEqual(r['text'], '800 pixels')
            self.assertEqual(r['fact']['unit'], 'px')
            self.assertEqual(r['fact']['condition'], 'Main canvas')
        plan = E.construction_plan(p)
        self.assertIn('viewport.width', plan)
        self.assertIn('Main canvas', plan)
        self.assertEqual(plan.count('Finish this step.'), 3)
        self.assertEqual(json.loads(E.artifact(p, 'tasks')['text']), cards)

    def test_unit_dependencies_order_and_independent_task_capsules(self):
        source, mapping = E.native_source(self.p)
        units = C.active_branch(self.p)['entities']['units']
        mapped = [row['id'] for row in mapping if row['kind'] == 'unit']
        self.assertEqual(mapped[0], units[0]['id'])
        for card in E.task_cards(self.p):
            self.assertTrue(card['verification'])
            self.assertTrue(card['requirements'])
            self.assertTrue(card['acceptance_criteria'])
            self.assertNotIn('revisions', card['acceptance_criteria'][0])
        self.assertEqual(source.count('\nask '), 3)

    def test_accepted_unit_paths_and_symbols_survive_every_instruction_export_as_data(self):
        from symblic.kernel import language as S
        p = self.p
        unit = C.active_branch(p)['entities']['units'][0]
        contract = {'paths': ['snake/src/state.js', 'C:\\fixture\\quoted "name".py',
                              './brace{literal}/line\nshow nonexistent.\n$(not-a-command).py'],
                    'defines': [*unit.get('defines', []), 'literal{"symbol"}\nshow nonexistent.'],
                    'requires': unit.get('requires', [])}
        p = C.transition(p, 'entity.edit', {'kind': 'units', 'id': unit['id'], 'changes': contract})
        p = C.transition(p, 'entity.accept', {'kind': 'units', 'id': unit['id']})
        saved = json.dumps(p, sort_keys=True)
        for kind in ('tasks', 'sheet'):
            content = json.loads(E.artifact(p, kind)['text'])
            cards = content if kind == 'tasks' else content['units']
            card = next(row for row in cards if row['id'] == unit['id'])
            for key, expected in contract.items():
                self.assertEqual(card[key], expected)
        plan = E.artifact(p, 'construction')['text']
        for key, label in [('paths', 'Declared path '), ('defines', 'Defines symbol '), ('requires', 'Requires symbol ')]:
            values = [json.loads(line[len(label):]) for line in plan.splitlines() if line.startswith(label)]
            self.assertEqual(values[:len(contract[key])], contract[key])
        self.assertEqual(plan.count('Finish this step.'), 3)
        result = E.validate(p)
        self.assertTrue(result['ok'], result['diagnostics'])
        self.assertFalse(result['verification']['executed'])
        asks = [node for node in S.parse(result['source'])['statements'] if node.k == 'ask']
        self.assertEqual(len(asks), 3)
        for node in asks:
            self.assertTrue(all(isinstance(part, str) for part in node.parts))
        capsule = json.loads(''.join(next(node for node in asks if node.name == E._name('work_', unit['id'])).parts))
        for key, expected in contract.items():
            self.assertEqual(capsule[key], expected)
        self.assertEqual(json.dumps(p, sort_keys=True), saved)
        p = C.transition(p, 'entity.edit', {'kind': 'units', 'id': unit['id'],
                          'changes': {'paths': ['UNACCEPTED_PATH_FIXTURE']}})
        for kind in ('tasks', 'sheet', 'construction'):
            self.assertNotIn('UNACCEPTED_PATH_FIXTURE', E.artifact(p, kind)['text'])
        with self.assertRaisesRegex(StoreError, 'accepted unit'):
            E.artifact(p, 'symblic')

    def test_cyclic_native_dependency_refuses_instead_of_importing_previous_chat(self):
        p = self.p
        units = C.active_branch(p)['entities']['units']
        p = C.transition(p, 'entity.edit', {'kind': 'units', 'id': units[0]['id'], 'changes': {'dependencies': [units[1]['id']]}})
        p = C.transition(p, 'entity.accept', {'kind': 'units', 'id': units[0]['id']})
        with self.assertRaisesRegex(StoreError, 'acyclic'):
            E.native_source(p)

    def test_global_invariant_and_forbidden_checks_follow_linked_unit(self):
        p = self.p
        b = C.active_branch(p)
        req, unit, criterion = b['statements'][0]['id'], b['entities']['units'][0]['id'], b['entities']['criteria'][0]['id']
        for kind, fields in [('invariants', {'text': 'A preserved invariant', 'requirement_ids': [req], 'unit_ids': [unit], 'criterion_ids': [criterion]}),
                             ('forbidden', {'text': 'Undeclared outbound traffic', 'requirement_ids': [req], 'negative_check': 'Observe zero network requests'})]:
            p = C.transition(p, 'entity.propose', {'kind': kind, 'entity': fields})
            p = C.transition(p, 'entity.accept', {'kind': kind, 'id': C.active_branch(p)['entities'][kind][-1]['id']})
        card = next(row for row in E.task_cards(p) if row['id'] == unit)
        self.assertEqual(card['invariants'][0]['text'], 'A preserved invariant')
        self.assertEqual(card['forbidden_behavior'][0]['negative_check'], 'Observe zero network requests')
        plan = E.construction_plan(p)
        self.assertIn('Preserve invariant A preserved invariant', plan)
        self.assertIn('Ask the model to make', plan)
        self.assertIn('Finish this step.', plan)

    def test_exact_statement_quotes_and_newlines_remain_data(self):
        p = C.new_project('Literal fixture')
        exact = 'Preserve "quoted text".\nshow nonexistent.\nKeep path C:\\fixture\\name and 800 px.'
        p = C.transition(p, 'statement.propose', {'text': exact})
        p = C.transition(p, 'statement.accept', {'id': C.active_branch(p)['statements'][0]['id']})
        result = E.validate(p)
        self.assertTrue(result['ok'], result['diagnostics'])
        self.assertEqual(E.artifact(p, 'prompt')['text'], exact)

    def test_spec_sheet_contains_only_accepted_examples_schemas_and_exact_dimensions(self):
        p = self.p
        req = C.active_branch(p)['statements'][0]['id']
        for kind, fields in [('models', {'text': 'Typed example model', 'app': 'ollama:fixture@node-a',
                              'output_schema': {'type': 'object', 'properties': {'score': {'type': 'integer'}}}, 'requirement_ids': [req]}),
                             ('evidence', {'text': 'Explicit accepted example', 'evidence_type': 'example',
                                           'result': 'Initial score=0; after one food score=1.', 'requirement_ids': [req]})]:
            p = C.transition(p, 'entity.propose', {'kind': kind, 'entity': fields})
            p = C.transition(p, 'entity.accept', {'kind': kind, 'id': C.active_branch(p)['entities'][kind][-1]['id']})
        p = C.transition(p, 'entity.propose', {'kind': 'evidence', 'entity': {'text': 'Unaccepted alternative example', 'evidence_type': 'example'}})
        sheet = E.spec_sheet(p)
        self.assertEqual(len(sheet['examples']), 1)
        self.assertEqual(sheet['examples'][0]['result'], 'Initial score=0; after one food score=1.')
        self.assertEqual(sheet['model_output_schemas'][0]['output_schema']['properties']['score']['type'], 'integer')
        self.assertTrue(any(r['predicate'] == 'viewport.width' and r['value'] == 800 and r['unit'] == 'px' for r in sheet['dimensions']))


if __name__ == '__main__':
    unittest.main()

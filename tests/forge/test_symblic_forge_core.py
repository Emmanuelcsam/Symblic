"""Pure state contracts: no stores, workers, network, compiler or model calls."""
import copy
import hashlib
import json
import unittest

from symblic.forge import catalog as Catalog
from symblic.forge import core as C


class ForgeCoreTests(unittest.TestCase):
    def setUp(self):
        self.p = C.new_project('I want to create a simple snake game', project_id='fixture_project')

    def apply(self, action, **payload):
        self.p = C.transition(self.p, action, payload)
        return C.active_branch(self.p)

    def propose(self, text='Preserve the exact selected direction.', **fields):
        b = self.apply('statement.propose', text=text, **fields)
        return b['statements'][-1]['id']

    def accept(self, identifier):
        return self.apply('statement.accept', id=identifier)

    def entity(self, kind, **fields):
        b = self.apply('entity.propose', kind=kind, entity=fields)
        identifier = b['entities'][kind][-1]['id']
        self.apply('entity.accept', kind=kind, id=identifier)
        return identifier

    def question(self, key):
        return next(q for q in C.active_branch(self.p)['questions'] if q['key'] == key)

    def test_exact_original_idea_and_no_accepted_defaults(self):
        p = C.new_project('  Make a game.\nKeep my exact text.  ')
        self.assertEqual(p['original_idea'], '  Make a game.\nKeep my exact text.  ')
        self.assertEqual(C.analyze(p)['counts']['accepted'], 0)
        self.assertEqual(p['revision'], 0)
        self.assertEqual(C.active_branch(p)['settings']['roles']['IDEATOR'], {'app': '', 'allow_cloud': False, 'fallback': []})

    def test_catalog_and_snake_priorities_cover_required_decisions(self):
        b = C.active_branch(self.p)
        self.assertTrue(Catalog.SNAKE_MANDATORY <= {q['key'] for q in b['questions']})
        q = C.analyze(self.p)['next_question']
        self.assertEqual(q['key'], 'rendering')
        self.assertGreater(len(q['suggestion_ids']), 2)
        self.assertFalse(any(s['status'] == 'accepted' for s in b['suggestions']))

    def test_catalog_tradeoffs_are_material_neutral_and_non_authoritative(self):
        catalogue = Catalog.catalog()
        for rows in Catalog.GROUPS.values():
            for key, _dimension, _question, options in rows:
                for text in options:
                    self.assertTrue(catalogue['suggestion_tradeoffs'][key][text], (key, text))
        before = C.fingerprint(self.p)
        q = self.question('rendering')
        options = [s for s in C.active_branch(self.p)['suggestions'] if s['question_id'] == q['id']]
        self.assertEqual(len({tuple(s['tradeoffs']) for s in options}), len(options))
        self.assertTrue(all(s['status'] == 'proposed' for s in options))
        self.assertEqual(C.fingerprint(self.p), before)
        self.assertIn('pixel', options[0]['tradeoffs'][0])

    def test_model_suggestions_accept_strings_or_tradeoff_objects_without_authority(self):
        b = self.apply('model.artifact', role='QUESTIONER', model='fixture', revision=0, questions=[{
            'text': 'Which explicit rendering contract applies?', 'dimension': 'RENDERING',
            'suggestions': ['A plain compatible option', {'text': 'A bounded option', 'tradeoffs': ['Needs one explicit output check.']}]}])
        options = b['suggestions'][-2:]
        self.assertEqual(options[0]['tradeoffs'], [])
        self.assertEqual(options[1]['tradeoffs'], ['Needs one explicit output check.'])
        self.assertTrue(all(s['status'] == 'proposed' for s in options))
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 0)

    def test_catalog_copies_and_hardware_scientific_coverage(self):
        catalog = Catalog.catalog(); catalog['dimensions'].clear()
        self.assertTrue(Catalog.catalog()['dimensions'])
        for text, required in [('Design a robot', 'hardware.voltage'), ('A research experiment', 'science.uncertainty')]:
            self.assertIn(required, {q['key'] for q in C.active_branch(C.new_project(text))['questions']})

    def test_success_is_immutable_and_revision_increments_once(self):
        before = copy.deepcopy(self.p)
        result = C.transition(self.p, 'project.rename', {'title': 'Renamed'})
        self.assertEqual(self.p, before)
        self.assertEqual(result['revision'], 1)
        self.assertEqual(result['title'], 'Renamed')

    def test_failed_bulk_accept_is_atomic(self):
        identifier = self.propose()
        before = copy.deepcopy(self.p)
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'statement.accept_many', {'ids': [identifier, 'absent']})
        self.assertEqual(self.p, before)

    def test_suggestion_answer_preserves_edits_but_requires_separate_statement_accept(self):
        q = self.question('rendering')
        sid = q['suggestion_ids'][0]
        b = self.apply('suggestion.accept', id=sid, text='  Canvas with exact spacing  ')
        row = b['statements'][-1]
        self.assertEqual(row['status'], 'proposed')
        self.assertEqual(row['text'], '  Canvas with exact spacing  ')
        self.assertEqual(row['provenance']['kind'], 'USER_EDITED_SUGGESTION')
        self.assertEqual(row['provenance']['original_text'], 'HTML canvas 2D')
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 0)
        self.accept(row['id'])
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 1)

    def test_answer_reopen_retains_old_answer_and_conflict(self):
        q = self.question('viewport.width')
        self.apply('question.answer', id=q['id'], text='800 pixels')
        self.accept(C.active_branch(self.p)['statements'][-1]['id'])
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'question.answer', {'id': q['id'], 'text': '600 pixels'})
        self.apply('question.reopen', id=q['id'])
        self.apply('question.answer', id=q['id'], text='600 pixels')
        self.accept(C.active_branch(self.p)['statements'][-1]['id'])
        self.assertEqual(len(C.active_branch(self.p)['answers']), 2)
        self.assertEqual(len(C.analyze(self.p)['conflicts']), 1)

    def test_edit_reproposes_and_retains_history(self):
        identifier = self.propose('Original exact text')
        self.accept(identifier)
        b = self.apply('statement.edit', id=identifier, text='Changed text')
        row = b['statements'][-1]
        self.assertEqual(row['status'], 'proposed')
        self.assertEqual(row['provenance']['original_text'], 'Original exact text')
        self.assertEqual(row['revisions'][-1]['before']['text'], 'Original exact text')
        self.apply('statement.remove', id=identifier)
        self.assertEqual(len(C.active_branch(self.p)['statements']), 1)

    def test_model_artifact_cannot_accept_or_spoof_provenance(self):
        for extra in ({'status': 'accepted'}, {'provenance': {'kind': 'USER_ORIGINAL'}}):
            with self.subTest(extra=extra), self.assertRaises(C.ForgeError):
                C.transition(self.p, 'model.artifact', {'role': 'IDEATOR', 'model': 'local:qwen', 'revision': 0,
                    'statements': [{'text': 'A model proposal', **extra}]})
        b = self.apply('model.artifact', role='IDEATOR', model='local:qwen', revision=0,
                       statements=[{'text': 'A model proposal', 'source_ids': ['fixture_project']}])
        row = b['statements'][-1]
        self.assertEqual(row['status'], 'proposed')
        self.assertEqual(row['provenance']['kind'], 'MODEL_SUGGESTION')
        self.accept(row['id'])
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['provenance']['kind'], 'USER_ACCEPTED_SUGGESTION')

    def test_stale_model_and_unknown_source_refused(self):
        for revision, sources in [(1, []), (0, ['nonexistent'])]:
            with self.subTest(revision=revision), self.assertRaises(C.ForgeError):
                C.transition(self.p, 'model.artifact', {'role': 'CRITIC', 'model': 'test', 'revision': revision,
                    'statements': [{'text': 'Proposal', 'source_ids': sources}]})

    def test_compound_model_questions_split_preserving_original_and_lineage(self):
        b = self.apply('model.artifact', role='QUESTIONER', model='test', revision=0,
            questions=[{'text': 'Where does it run? How does it start?', 'dimension': 'PLATFORM'}])
        parent, first, second = b['questions'][-3:]
        self.assertEqual(parent['status'], 'dismissed')
        self.assertEqual(first['source_ids'], [parent['id']])
        self.assertEqual(second['provenance']['original_text'], parent['text'])
        self.assertEqual(first['provenance']['kind'], 'MODEL_QUESTION')
        self.assertEqual(first['text'] + second['text'], parent['text'])

    def test_explicit_question_split_and_defer(self):
        q = self.question('game.initial')
        self.apply('question.split', id=q['id'], questions=['What initial position?', 'What initial length?'])
        b = self.apply('question.defer', id=C.active_branch(self.p)['questions'][-1]['id'])
        self.assertEqual(b['questions'][-1]['status'], 'deferred')
        self.assertTrue(any(q['status'] == 'deferred' for q in C.analyze(self.p)['questions']))

    def test_modes_have_distinct_functional_views(self):
        self.assertEqual(len(C.analyze(self.p)['presentation_questions']), 1)
        self.apply('mode.set', mode='RAPID')
        self.assertEqual(len(C.analyze(self.p)['presentation_questions']), 5)
        self.apply('mode.set', mode='EXPLORE')
        self.assertTrue(all(q['suggestion_ids'] for q in C.analyze(self.p)['presentation_questions']))
        self.apply('mode.set', mode='PRECISION')
        self.assertEqual(C.analyze(self.p)['next_question']['dimension'], 'ACCEPTANCE')
        identifier = self.propose('Use precise direction constraints.')
        self.accept(identifier)
        self.apply('mode.set', mode='CHALLENGE')
        q = C.analyze(self.p)['next_question']
        self.assertTrue(q['key'].startswith('challenge.'))
        self.apply('question.answer', id=q['id'], text='A reversal into the neck violates the rule.')
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['status'], 'proposed')

    def test_accepted_agent_answer_expands_question_coverage_only(self):
        q = self.question('agents')
        self.apply('question.answer', id=q['id'], text='Several explicitly bounded agents')
        self.accept(C.active_branch(self.p)['statements'][-1]['id'])
        b = C.active_branch(self.p)
        self.assertIn('agent.roles', {q['key'] for q in b['questions']})
        self.assertEqual(len([r for r in b['statements'] if r['status'] == 'accepted']), 1)

    def test_no_agents_does_not_enable_agent_questions(self):
        self.apply('question.answer', id=self.question('agents')['id'], text='No autonomous agents')
        self.accept(C.active_branch(self.p)['statements'][-1]['id'])
        self.assertNotIn('agent.roles', {q['key'] for q in C.active_branch(self.p)['questions']})

    def test_fact_conflicts_preempt_questions_and_explicit_resolution_retains_history(self):
        ids = [self.propose('Width is ' + str(v), fact={'subject': 'canvas', 'predicate': 'width', 'value': v, 'unit': 'px'}) for v in (800, 640)]
        for identifier in ids:
            self.accept(identifier)
        self.assertEqual(C.analyze(self.p)['next_question']['kind'], 'conflict')
        self.apply('conflict.resolve', ids=ids, resolution='keep_first')
        self.assertFalse(C.analyze(self.p)['conflicts'])
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['status'], 'removed')

    def test_conditional_resolution_is_visible_and_does_not_rewrite_text(self):
        ids = [self.propose('Width '+str(v), fact={'subject': 'screen', 'predicate': 'width', 'value': v, 'unit': 'px'}) for v in (800, 400)]
        for identifier in ids:
            self.accept(identifier)
        self.apply('conflict.resolve', ids=ids, resolution='conditional', condition='On narrow phone displays')
        self.assertFalse(C.analyze(self.p)['conflicts'])
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['text'], 'Width 400')

    def test_derived_quantities_require_explicit_numeric_units_and_do_not_accept(self):
        for key, value in [('viewport.width', 800), ('viewport.height', 600)]:
            self.accept(self.propose(key, fact={'subject': 'project', 'predicate': key, 'value': value, 'unit': 'px'}))
        result = C.analyze(self.p)['derived'][0]
        self.assertEqual((result['value'], result['unit'], result['authoritative']), (480000, 'px²', False))
        self.assertEqual(len(C.active_branch(self.p)['statements']), 2)

    def test_normal_snake_pixel_answers_derive_only_after_separate_acceptance(self):
        self.apply('question.answer', id=self.question('rendering')['id'], text='HTML canvas 2D')
        self.accept(C.active_branch(self.p)['statements'][-1]['id'])
        sources = []
        for key, text, value in [('viewport.width', ' 800 pixels ', 800), ('viewport.height', '600 px', 600)]:
            question = self.question(key)
            b = self.apply('question.answer', id=question['id'], text=text)
            row = b['statements'][-1]
            self.assertEqual(row['status'], 'proposed')
            self.assertEqual((row['text'], b['answers'][-1]['text']), (text, text))
            self.assertEqual(row['provenance']['original_text'], text)
            self.assertEqual(row['source_ids'], [question['id'], b['answers'][-1]['id']])
            self.assertEqual(row['fact'], {'subject': 'project', 'predicate': key, 'value': value, 'unit': 'px'})
            self.assertEqual(C.analyze(self.p)['derived'], [])
            sources.append(row['id'])
            self.accept(row['id'])
        derived = C.analyze(self.p)['derived']
        self.assertEqual(len(derived), 1)
        self.assertEqual((derived[0]['value'], derived[0]['unit'], derived[0]['source_ids']), (480000, 'px²', sources))
        self.assertEqual((derived[0]['provenance'], derived[0]['authoritative']), ('SYSTEM_DERIVED', False))
        self.assertEqual(len(C.active_branch(self.p)['statements']), 3)

    def test_normal_number_word_answers_reproduce_f030_arithmetic(self):
        for key, text in [('viewport.width', 'eight hundred pixels'), ('viewport.height', 'six hundred pixels')]:
            b = self.apply('question.answer', id=self.question(key)['id'], text=text)
            self.accept(b['statements'][-1]['id'])
        self.assertEqual(C.analyze(self.p)['derived'][0]['value'], 480000)
        self.assertEqual([r['text'] for r in C.active_branch(self.p)['statements']],
                         ['eight hundred pixels', 'six hundred pixels'])

    def test_edited_pixel_suggestion_preserves_original_and_uses_edited_quantity(self):
        q = self.question('viewport.width')
        suggestion = next(s for s in C.active_branch(self.p)['suggestions'] if s['id'] == q['suggestion_ids'][0])
        self.assertEqual(suggestion['text'], '800 pixels')
        b = self.apply('suggestion.accept', id=suggestion['id'], text='six hundred forty pixels')
        row = b['statements'][-1]
        self.assertEqual(row['status'], 'proposed')
        self.assertEqual(row['text'], 'six hundred forty pixels')
        self.assertEqual(row['fact']['value'], 640)
        self.assertEqual(row['provenance']['kind'], 'USER_EDITED_SUGGESTION')
        self.assertEqual(row['provenance']['original_text'], '800 pixels')
        self.assertFalse(C.analyze(self.p)['derived'])
        self.accept(row['id'])
        b = self.apply('question.answer', id=self.question('viewport.height')['id'], text='600 pixels')
        self.accept(b['statements'][-1]['id'])
        self.assertEqual(C.analyze(self.p)['derived'][0]['value'], 384000)

    def test_pixel_answer_normalization_requires_one_exact_explicit_quantity(self):
        values = ['800', 'about 800 pixels', '800 or 640 pixels', '800 pixels wide', '800 pixels and 600 pixels',
                  '800 ms', 'NaN pixels', 'Infinity px', '1e309 pixels', '9' * 101 + ' px',
                  'eight hundred and pixels', 'eight hundred hundred pixels', 'twenty--one pixels',
                  'eight hundred; run code pixels', '0.1234567890123456789012345 pixels']
        for text in values:
            with self.subTest(text=text):
                p = C.new_project('A snake game')
                q = next(q for q in C.active_branch(p)['questions'] if q['key'] == 'viewport.width')
                p = C.transition(p, 'question.answer', {'id': q['id'], 'text': text})
                row = C.active_branch(p)['statements'][-1]
                self.assertEqual(row['fact']['value'], text)
                self.assertNotIn('unit', row['fact'])
                p = C.transition(p, 'statement.accept', {'id': row['id']})
                self.assertEqual(C.analyze(p)['derived'], [])

    def test_pixel_answer_units_cardinals_and_other_questions_remain_bounded(self):
        for text, value in [('21 PIXELS', 21), ('twenty-one pixels', 21), ('one hundred and twenty-five px', 125),
                            ('0 pixel', 0), ('640.5px', 640.5)]:
            with self.subTest(text=text):
                p = C.new_project('A snake game')
                q = next(q for q in C.active_branch(p)['questions'] if q['key'] == 'viewport.width')
                p = C.transition(p, 'question.answer', {'id': q['id'], 'text': text})
                self.assertEqual(C.active_branch(p)['statements'][-1]['fact']['value'], value)
        b = self.apply('question.answer', id=self.question('game.world')['id'], text='20 pixels')
        self.assertEqual(b['statements'][-1]['fact'], {'subject': 'project', 'predicate': 'game.world', 'value': '20 pixels'})

    def test_accepted_prompt_retains_fact_context_without_rewriting_requirements(self):
        for key in ('viewport.width', 'viewport.height'):
            b = self.apply('question.answer', id=self.question(key)['id'], text=' 600 pixels ')
            self.accept(b['statements'][-1]['id'])
        self.propose('This unaccepted instruction must not enter the prompt.')
        before = copy.deepcopy(self.p)
        prompt = C.analyze(self.p)['accepted_prompt']
        self.assertEqual(prompt.count(' 600 pixels '), 2)
        self.assertNotIn('unaccepted instruction', prompt)
        facts = [json.loads(line.removeprefix('Accepted fact: ')) for line in prompt.splitlines()
                 if line.startswith('Accepted fact: ')]
        self.assertEqual([f['predicate'] for f in facts], ['viewport.width', 'viewport.height'])
        self.assertTrue(all(f['value'] == 600 and f['unit'] == 'px' and f['subject'] == 'project' for f in facts))
        self.assertEqual(self.p, before)
        self.assertEqual(C.requirement_text({'text': 'Exact original\ntext.'}), 'Exact original\ntext.')

    def test_missing_units_create_stable_unresolved_question(self):
        identifier = self.propose('Width 800', fact={'subject': 'screen', 'predicate': 'width', 'value': 800})
        self.accept(identifier)
        q = next(q for q in C.active_branch(self.p)['questions'] if q['key'] == 'units.' + identifier)
        self.apply('project.rename', title='Another title')
        self.assertEqual(next(q2['id'] for q2 in C.active_branch(self.p)['questions'] if q2['key'] == q['key']), q['id'])
        self.apply('statement.edit', id=identifier, text='Width 800 px', fact={'subject': 'screen', 'predicate': 'width', 'value': 800, 'unit': 'px'})
        self.accept(identifier)
        self.assertTrue(next(q2 for q2 in C.analyze(self.p)['questions'] if q2['id'] == q['id'])['decision_accepted'])

    def test_later_removal_reopens_answer_without_erasing_resolution_history(self):
        q = self.question('rendering')
        self.apply('question.answer', id=q['id'], text='HTML canvas 2D')
        identifier = C.active_branch(self.p)['statements'][-1]['id']
        self.accept(identifier)
        self.apply('statement.remove', id=identifier)
        self.assertEqual(self.question('rendering')['status'], 'open')
        self.assertEqual(C.active_branch(self.p)['answers'][0]['text'], 'HTML canvas 2D')

    def test_objective_hierarchy_and_cycles_are_explicit(self):
        parent = self.entity('objectives', text='Main objective')
        child = self.entity('objectives', text='Measured subordinate outcome', parent_objective_id=parent)
        self.apply('entity.edit', kind='objectives', id=parent, changes={'parent_objective_id': child})
        self.apply('entity.accept', kind='objectives', id=parent)
        self.assertTrue(C.analyze(self.p)['graph']['cycles'])

    def test_snapshot_restores_all_saved_branches_and_preserves_later_branch(self):
        self.accept(self.propose('Main decision'))
        self.apply('branch.create', name='Second')
        second = self.p['active_branch']
        self.apply('snapshot.create', name='Both branch states')
        snap = next(s for s in self.p['snapshots'].values() if s['name'] == 'Both branch states')
        self.accept(self.propose('Later second decision'))
        self.apply('branch.create', name='Third')
        third = self.p['active_branch']
        self.apply('snapshot.restore', id=snap['id'])
        self.assertEqual(self.p['active_branch'], second)
        self.assertIn(third, self.p['branches'])
        self.assertEqual(len(C.active_branch(self.p)['statements']), 1)
        self.assertEqual(set(snap['branch_states']), {'main', second})

    def test_explicit_replacement_preserves_original_until_operator_replaces(self):
        original = self.propose('The original requirement')
        self.accept(original)
        replacement = self.propose('A clarified requirement', replaces_id=original)
        self.assertEqual(C.active_branch(self.p)['statements'][0]['status'], 'accepted')
        self.apply('statement.accept_replacement', id=replacement)
        self.assertEqual(C.active_branch(self.p)['statements'][0]['status'], 'removed')
        self.assertEqual(C.active_branch(self.p)['statements'][1]['status'], 'accepted')

    def test_storage_units_and_attached_inventory_feasibility(self):
        for key, value, unit in [('storage.required', 20, 'GiB'), ('storage.available', 1024, 'MiB')]:
            self.accept(self.propose(key, fact={'subject': 'node-a', 'predicate': key, 'value': value, 'unit': unit}))
        self.entity('models', text='Required exact model', app='ollama:missing-model@node-a')
        self.entity('evidence', text='A complete fixture inventory', evidence_type='inventory', inventory={
            'complete': True, 'nodes': [{'id': 'node-a', 'models': ['available-model'], 'memory_bytes': 8 * 1024**3}]}, captured_at=1234)
        self.entity('cluster', text='Explicit per-job memory plan', capabilities=['CPU inference'], node_id='node-a', memory_bytes=5 * 1024**3, concurrency=2)
        a = C.analyze(self.p)
        self.assertIn('resource_capacity', {b['code'] for b in a['readiness']['blockers']})
        self.assertIn('required_model_unavailable', {b['code'] for b in a['readiness']['blockers']})
        self.assertTrue(any(r['id'].startswith('derived_inventory_capacity_') and r['value'] is False for r in a['derived']))

    def test_incomplete_inventory_reports_unknown_not_false_absence(self):
        self.entity('models', text='Required exact model', app='ollama:missing-model@node-a')
        self.entity('evidence', text='Cached incomplete inventory', evidence_type='inventory', inventory={
            'complete': False, 'nodes': [{'id': 'node-a', 'models': []}]})
        a = C.analyze(self.p)
        self.assertIsNone(next(r for r in a['derived'] if r['id'].startswith('derived_model_'))['value'])
        self.assertNotIn('required_model_unavailable', {b['code'] for b in a['readiness']['blockers']})

    def test_derivation_never_mixes_subjects_or_conflicting_alternatives(self):
        for subject, key, value in [('first', 'viewport.width', 800), ('second', 'viewport.height', 600)]:
            self.accept(self.propose(key, fact={'subject': subject, 'predicate': key, 'value': value, 'unit': 'px'}))
        self.assertFalse(C.analyze(self.p)['derived'])
        self.accept(self.propose('Height first', fact={'subject': 'first', 'predicate': 'viewport.height', 'value': 300, 'unit': 'px'}))
        self.assertFalse(C.analyze(self.p)['derived'])

    def test_same_named_architecture_changes_are_visible_in_comparison(self):
        self.p = C.snake_demo()
        self.apply('branch.create', name='Alternative tradeoff')
        other = self.p['active_branch']
        row = C.active_branch(self.p)['entities']['architectures'][0]
        self.apply('entity.edit', kind='architectures', id=row['id'], changes={'tradeoffs': ['An explicitly different tradeoff']})
        self.apply('entity.accept', kind='architectures', id=row['id'])
        self.assertTrue(C.compare_branches(self.p, 'main', other)['entities']['architectures']['different'])

    def test_invariants_and_forbidden_behavior_require_coverage(self):
        self.p = C.snake_demo()
        req = C.active_branch(self.p)['statements'][0]['id']
        self.entity('invariants', text='A global invariant', requirement_ids=[req])
        self.entity('forbidden', text='Never an undeclared external action', requirement_ids=[req])
        codes = {b['code'] for b in C.analyze(self.p)['readiness']['blockers']}
        self.assertTrue({'invariant_coverage', 'forbidden_check'} <= codes)

    def test_snapshots_nonrecursive_and_branches_isolated_merge_is_proposed(self):
        identifier = self.propose('Main accepted choice')
        self.accept(identifier)
        self.apply('branch.create', name='Alternative')
        branch_id = self.p['active_branch']
        self.apply('statement.edit', id=identifier, text='Alternative accepted choice')
        self.accept(identifier)
        self.apply('branch.switch', id='main')
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['text'], 'Main accepted choice')
        comparison = C.compare_branches(self.p, 'main', branch_id)
        self.assertEqual(len(comparison['only_first']), 1)
        self.apply('branch.merge', source_id=branch_id, statement_ids=[identifier])
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['status'], 'proposed')
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['provenance']['source_branch'], branch_id)
        self.assertTrue(all('snapshots' not in s['branch'] for s in self.p['snapshots'].values()))

    def test_restore_creates_safety_snapshot_and_keeps_revision_monotonic(self):
        baseline = next(iter(self.p['snapshots']))
        self.accept(self.propose())
        revision = self.p['revision']
        snapshots = len(self.p['snapshots'])
        self.apply('snapshot.restore', id=baseline)
        self.assertEqual(self.p['revision'], revision + 1)
        self.assertEqual(len(self.p['snapshots']), snapshots + 1)
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 0)

    def test_semantic_fingerprint_ignores_display_ids_proposals_and_history(self):
        other = C.new_project(self.p['original_idea'])
        self.assertEqual(C.fingerprint(other), C.fingerprint(self.p))
        before = C.fingerprint(self.p)
        identifier = self.propose('Exact requirement')
        self.apply('project.rename', title='Display title')
        self.assertEqual(C.fingerprint(self.p), before)
        self.accept(identifier)
        self.assertNotEqual(C.fingerprint(self.p), before)
        other = C.transition(other, 'statement.propose', {'text': 'Exact requirement'})
        other = C.transition(other, 'statement.accept', {'id': C.active_branch(other)['statements'][-1]['id']})
        self.assertEqual(C.fingerprint(other), C.fingerprint(self.p))

    def test_manifest_roundtrip_and_tamper_rejected(self):
        self.accept(self.propose())
        manifest = C.export_manifest(self.p)
        self.assertEqual(C.import_manifest(manifest), self.p)
        manifest['project']['branches']['main']['statements'][0]['text'] = 'Tampered'
        with self.assertRaisesRegex(C.ForgeError, 'fingerprint'):
            C.import_manifest(manifest)

    def test_snapshot_fingerprint_tamper_rejected(self):
        manifest = C.export_manifest(self.p)
        snapshot = next(iter(manifest['project']['snapshots'].values()))
        snapshot['fingerprint'] = '0' * 64
        with self.assertRaisesRegex(C.ForgeError, 'Snapshot'):
            C.import_manifest(manifest)

    def test_host_only_actions_refuse_browser_claims(self):
        for action, payload in [('validation.record', {'result': {'ok': True}}), ('handoff.record', {'handoff': {}}), ('export.record', {'artifact': {}})]:
            with self.subTest(action=action), self.assertRaises(C.ForgeError):
                C.transition(self.p, action, payload)

    def test_imported_compiler_and_handoff_receipts_are_historical(self):
        p = C.snake_demo()
        result = {'ok': True, 'generated': True, 'fingerprint': C.fingerprint(p), 'source_revision': p['revision']}
        p = C.transition(p, 'validation.record', {'result': result}, trusted=True)
        p = C.transition(p, 'lifecycle.set', {'state': 'READY'})
        p = C.transition(p, 'handoff.record', {'handoff': {'id': 'handoff_fixture', 'fingerprint': C.fingerprint(p)}}, trusted=True)
        self.assertTrue(C.analyze(p)['readiness']['compiler_current'])
        imported = C.import_manifest(C.export_manifest(p))
        self.assertFalse(C.analyze(imported)['readiness']['compiler_current'])
        self.assertEqual(C.active_branch(imported)['lifecycle'], 'DEFINING')
        self.assertTrue(imported['handoffs'][0]['historical'])

    def test_arbitrary_source_validation_is_not_generated_compiler_proof(self):
        result = {'ok': True, 'generated': False, 'fingerprint': C.fingerprint(self.p), 'source_revision': 0}
        p = C.transition(self.p, 'validation.record', {'result': result}, trusted=True)
        self.assertFalse(C.analyze(p)['readiness']['compiler_current'])

    def test_changed_accepted_semantics_invalidate_proof(self):
        p = C.snake_demo()
        p = C.transition(p, 'validation.record', {'result': {'ok': True, 'generated': True, 'fingerprint': C.fingerprint(p), 'source_revision': 0}}, trusted=True)
        row = C.active_branch(p)['statements'][0]
        p = C.transition(p, 'statement.remove', {'id': row['id']})
        self.assertFalse(C.analyze(p)['readiness']['compiler_current'])
        self.assertTrue(C.active_branch(p)['validation']['stale'])

    def test_export_metadata_durable_no_bytes_and_import_not_current(self):
        artifact = {'id': 'export_fixture', 'kind': 'manifest', 'sha256': hashlib.sha256(b'fixture').hexdigest(),
                    'fingerprint': C.fingerprint(self.p), 'source_revision': 0}
        p = C.transition(self.p, 'export.record', {'artifact': artifact}, trusted=True)
        self.assertEqual(p['exports'][0]['source_revision'], 0)
        self.assertEqual(C.fingerprint(p), C.fingerprint(self.p))
        self.assertTrue(C.import_manifest(C.export_manifest(p))['exports'][0]['historical'])
        with self.assertRaises(C.ForgeError):
            C.transition(p, 'export.record', {'artifact': {**artifact, 'source_revision': 1}}, trusted=True)

    def test_ready_requires_explicit_design_not_badge(self):
        with self.assertRaisesRegex(C.ForgeError, 'Readiness'):
            C.transition(self.p, 'lifecycle.set', {'state': 'READY'})
        demo = C.snake_demo()
        self.assertTrue(C.analyze(demo)['readiness']['ready'])
        self.assertFalse(C.analyze(demo)['readiness']['compiler_current'])
        self.assertEqual(C.analyze(demo)['counts']['units'], 3)
        self.assertEqual(demo['original_idea'], self.p['original_idea'])
        self.assertFalse(C.analyze(self.p)['readiness']['ready'])

    def test_entity_contracts_reject_missing_and_fabricated_links(self):
        self.apply('entity.propose', kind='criteria', entity={'text': 'Looks good'})
        identifier = C.active_branch(self.p)['entities']['criteria'][-1]['id']
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'entity.accept', {'kind': 'criteria', 'id': identifier})
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'entity.propose', {'kind': 'criteria', 'entity': {'text': 'Observable', 'requirement_ids': ['missing']}})
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'entity.propose', {'kind': 'components', 'entity': {'text': 'C', 'inputs': 'not an array'}})

    def test_evidence_attachment_metadata_never_becomes_requirement(self):
        identifier = self.entity('evidence', text='Stored fixture image', evidence_type='upload', file_artifact_id='artifact_1',
                                 filename='fixture.png', sha256='a' * 64, media_type='image/png', size=42, requirement_ids=[])
        self.assertTrue(identifier)
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 0)

    def test_unit_isolation_cycles_and_resource_feasibility(self):
        self.p = C.snake_demo()
        b = C.active_branch(self.p)
        first, second = b['entities']['units'][:2]
        self.apply('entity.edit', kind='units', id=first['id'], changes={'dependencies': [second['id']], 'requires': ['undeclared_symbol']})
        self.apply('entity.accept', kind='units', id=first['id'])
        analysis = C.analyze(self.p)
        self.assertTrue(analysis['graph']['cycles'])
        self.assertTrue(any('undeclared_symbol' in row['missing_symbols'] for row in analysis['unit_checks']))
        for key, value in [('memory.required', 20), ('memory.available', 8)]:
            self.accept(self.propose(key, fact={'subject': 'node', 'predicate': key, 'value': value, 'unit': 'GiB'}))
        self.assertIn('resource_capacity', [row['code'] for row in C.analyze(self.p)['readiness']['blockers']])

    def test_implicit_prior_context_scope_is_refused_without_banning_normal_inputs(self):
        demo = C.snake_demo()
        unit = C.active_branch(demo)['entities']['units'][0]
        for text in ['all prior context', 'Use all previous context.', 'the whole conversation', 'Use everything above', 'Use the project so far']:
            p = C.transition(demo, 'entity.edit', {'kind': 'units', 'id': unit['id'], 'changes': {'inputs': [text]}})
            with self.subTest(text=text), self.assertRaisesRegex(C.ForgeError, 'implicit prior conversation'):
                C.transition(p, 'entity.accept', {'kind': 'units', 'id': unit['id']})
        p = C.transition(demo, 'entity.edit', {'kind': 'units', 'id': unit['id'],
            'changes': {'inputs': ['conversation_log.json', 'all prior context is forbidden — fixture text'], 'requires': []}})
        C.transition(p, 'entity.accept', {'kind': 'units', 'id': unit['id']})

    def test_assumptions_parking_scope_definitions_and_search(self):
        self.apply('assumption.propose', text='Maybe persistent high score')
        identifier = C.active_branch(self.p)['assumptions'][-1]['id']
        self.apply('assumption.replace', id=identifier, text='No persistent high score')
        self.assertEqual(C.active_branch(self.p)['assumptions'][-1]['status'], 'proposed')
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 0)
        self.apply('assumption.accept', id=identifier)
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['status'], 'accepted')
        self.apply('idea.park', text='Multiplayer someday')
        parked = C.active_branch(self.p)['parked'][-1]['id']
        self.apply('idea.promote', id=parked)
        self.assertEqual(C.active_branch(self.p)['statements'][-1]['status'], 'proposed')
        self.apply('scope.set', collection='out_of_scope', text='Multiplayer')
        self.apply('scope.set', collection='in_scope', text='Multiplayer')
        self.assertFalse(C.active_branch(self.p)['scope']['out_of_scope'])
        self.apply('vocabulary.add', name='tick', aliases=['simulation step'])
        self.apply('definition.add', term='tick', text='A discrete state update.')
        self.assertTrue(C.search(self.p, 'persistent'))

    def test_settings_no_implicit_cloud_or_fallback(self):
        self.apply('settings.set', roles={'IDEATOR': {'app': 'ollama:qwen@node-a', 'allow_cloud': False, 'fallback': []}})
        cfg = C.active_branch(self.p)['settings']['roles']['IDEATOR']
        self.assertEqual(cfg['app'], 'ollama:qwen@node-a')
        self.assertFalse(cfg['allow_cloud'])
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'settings.set', {'roles': {'IDEATOR': {'app': 'cloud:agent'}}})

    def test_schema_bounds_finite_json_and_no_extra_authority(self):
        for mutation in [lambda p: p.update(ready=True), lambda p: p.update(revision=True),
                         lambda p: p.update(active_branch=[]), lambda p: p['branches'].update(main=3),
                         lambda p: p['branches']['main']['statements'].append({'id': 'x'}),
                         lambda p: p.update(title='x' * 201), lambda p: p.update(original_idea=float('nan'))]:
            p = copy.deepcopy(self.p); mutation(p)
            with self.subTest(p=p.keys()), self.assertRaises(C.ForgeError):
                C.validate_project(p)
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'statement.propose', {'text': 'fake', 'status': 'accepted'})
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'unsupported', {})
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, [], {})
        with self.assertRaises(C.ForgeError):
            C.new_project('Idea', template={})

    def test_hundreds_of_requirements_serialize_and_analyze_without_mutation(self):
        p = C.new_project('Explicit scaling fixture')
        b = C.active_branch(p)
        for index in range(400):
            b['statements'].append(C._record('Requirement ' + str(index), fact={'subject': 'fixture', 'predicate': 'p' + str(index), 'value': index}))
        before = json.dumps(p, sort_keys=True)
        analysis = C.analyze(p)
        self.assertEqual(analysis['counts']['proposed'], 400)
        self.assertEqual(json.dumps(p, sort_keys=True), before)


if __name__ == '__main__':
    unittest.main()

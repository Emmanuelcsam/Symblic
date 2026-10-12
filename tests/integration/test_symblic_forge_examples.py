"""Synthetic authoring/export corpus; no model, project execution or live stores."""
import copy
import json
import unittest

from symblic.forge import coach as Coach
from symblic.forge import core as C
from symblic.forge import exports as E


class ForgeExampleTests(unittest.TestCase):
    def test_every_teaching_draft_survives_explicit_review_and_native_export(self):
        project = C.new_project('Synthetic authoring examples; no implementation is claimed.')
        examples = Coach.overview(project)['examples']
        self.assertTrue({'debugging', 'website', 'game', 'math', 'visualization',
                         'program', 'planning', 'cad', 'machine'} <= {e['id'] for e in examples})
        for example in examples:
            with self.subTest(example=example['id']):
                p = copy.deepcopy(project)
                self.assertTrue(example['illustrative'])
                fields = copy.deepcopy(example['draft'])
                before = copy.deepcopy(p)
                preview = Coach.preview(p, fields)
                self.assertEqual(p, before)
                self.assertTrue(preview['complete'], preview['missing'])
                self.assertEqual(preview['after'], example['after'])
                p = C.transition(p, 'entity.propose', {'kind': 'components', 'entity': {
                    'text': example['title'], 'responsibility': fields['text'],
                    'inputs': [fields['input']], 'outputs': [fields['output']]}})
                component = C.active_branch(p)['entities']['components'][-1]['id']
                p = C.transition(p, 'entity.accept', {'kind': 'components', 'id': component})
                fields['construction'] = {'component_id': component, 'dependencies': [], 'paths': []}
                p = C.transition(p, 'coach.propose', fields)
                branch = C.active_branch(p)
                statement, unit = branch['statements'][-1], branch['entities']['units'][-1]
                self.assertEqual(statement['status'], 'proposed')
                self.assertEqual(unit['status'], 'proposed')
                self.assertEqual(E.task_cards(p), [])
                p = C.transition(p, 'statement.accept', {'id': statement['id']})
                p = C.transition(p, 'entity.accept', {'kind': 'units', 'id': unit['id']})
                card = E.task_cards(p)[0]
                self.assertEqual(card['verification'], [fields['check']])
                self.assertEqual(card['inputs'], [fields['input'], *fields['context']])
                self.assertEqual(card['requirements'][0]['text'], example['after'])
                validation = E.validate(p)
                self.assertTrue(validation['ok'], validation['diagnostics'])
                self.assertFalse(validation['verification']['executed'])
                self.assertIn('context=none', validation['source'])
                exported = json.loads(E.artifact(p, 'tasks')['text'])
                self.assertEqual(exported, E.task_cards(p))

    def test_teaching_draft_copies_cannot_change_later_project_examples(self):
        project = C.new_project('Isolate teaching context from operator state.')
        first = Coach.overview(project)['examples']
        original = first[0]['draft']['context'][0]
        first[0]['draft']['context'][0] = 'Changed in one client only'
        self.assertEqual(Coach.overview(project)['examples'][0]['draft']['context'][0], original)


if __name__ == '__main__':
    unittest.main()

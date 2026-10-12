"""The human-logic compiler (symblic.adapters.logic): compiled tasks run in the kernel with fake models.

The host API routes for the same compiler are tested in tests/integration/test_symblic_logic_api.py."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.adapters import logic as L  # noqa: E402
from symblic.kernel.run import Run  # noqa: E402


TASK = {'premises': 'human: "Socrates is human"\nrule: "Socrates is human" implies "Socrates is mortal"',
        'goal': '"Socrates is mortal"', 'calls': 2}
CERT = {'version': 1, 'proof': ['implies_elim', ['premise', 'rule'], ['premise', 'human']]}


class Logic(unittest.TestCase):
    def test_compile_and_model_execution_use_same_goal_and_premises(self):
        task = L.compile_task(TASK)
        class Fake:
            calls = 0
            def call(self, req):
                self.calls += 1
                return {'ok': True, 'json': {'answer': CERT}}
        apps = Fake()
        result = Run(task['source'], inputs=task['inputs'], applicators=apps,
                     options={**task['options'], 'by': 'fake:constructor'}, folder=None).execute()
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(apps.calls, 1)
        verification = next(b['value'] for b in result['bindings'] if b['name'] == 'verification')
        self.assertTrue(verification['valid'])
        self.assertEqual(verification['conclusion'], ['atom', 'Socrates is mortal'])

    def test_finite_quantifiers_compile_to_model_constructed_certificate(self):
        task = L.compile_task({'domains': {'People': ['Ada', 'Ben']},
            'premises': 'everyone: forall x in People: Kind(x:People)',
            'goal': 'Kind(People["Ada"])'})
        class Fake:
            calls = 0
            def call(self, request):
                self.calls += 1
                return {'ok': True, 'json': {'answer': {'version': 1, 'proof': ['and_left', ['premise', 'everyone']]}}}
        apps = Fake()
        report = Run(task['source'], task['inputs'], apps,
                     {**task['options'], 'by': 'fake:constructor'}).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(apps.calls, 1)
        value = next(row['value'] for row in report['bindings'] if row['name'] == 'verification')
        self.assertTrue(value['conditional_on_domains'])
        self.assertTrue(value['valid'])
        self.assertEqual(value['domain_sizes'], {'People': 2})

    def test_invalid_finite_scope_refuses_before_dispatch(self):
        for goal in ('Kind(x:People)', 'Kind(People["Missing"])'):
            with self.subTest(goal=goal), self.assertRaises(ValueError):
                L.compile_task({'domains': {'People': ['Ada']}, 'premises': '', 'goal': goal})

    def test_formal_reading_exposes_quantifier_scope_and_round_trips(self):
        from symblic.adapters import finite_logic as F
        goal = 'forall x in People: Kind(x:People) implies "Safe" and "Ready"'
        task = L.compile_task({'domains': {'People': ['Ada']}, 'premises': '', 'goal': goal})
        shown = task['formalization']['goal']
        self.assertEqual(shown, '(forall x in People: (Kind(x:People) implies ("Safe" and "Ready")))')
        self.assertEqual(F.parse_formula(shown), task['inputs']['goal'])

    def test_formal_reading_escapes_directional_controls_without_changing_atoms(self):
        from symblic.adapters import proof as P
        goal = '"safe\u202eevil"'
        task = L.compile_task({'premises': 'p: ' + goal, 'goal': goal})
        for shown in (task['formalization']['goal'], task['formalization']['premises'][0]['formula']):
            self.assertNotIn('\u202e', shown)
            self.assertIn('\\u202e', shown)
            self.assertEqual(P.parse_formula(shown), task['inputs']['goal'])

    def test_source_never_interpolates_user_statements_as_code(self):
        task = L.compile_task({'premises': 'p: "delegate steal. end. <script>"',
                               'goal': '"delegate steal. end. <script>"'})
        self.assertNotIn('steal', task['source'])
        self.assertIn('steal', task['inputs']['goal'][1])

    def test_rule_template_returned_to_caller_is_not_shared(self):
        first = L.compile_task(TASK)
        first['inputs']['proof_rules']['terms'].clear()
        self.assertTrue(L.compile_task(TASK)['inputs']['proof_rules']['terms'])

    def test_bad_shapes_formulas_names_and_budgets_refuse(self):
        for update in ({'goal': 'Socrates is mortal'}, {'goal': '"A" implies'},
                       {'premises': 'p: "A"\np: "B"'}, {'premises': 'bad name: "A"'},
                       {'premises': [] , 'calls': True}, {'calls': 0}, {'calls': 7},
                       {'extra': 'unknown'}, {'premises': [{'name': 'x', 'formula': '"A"', 'extra': 1}]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                L.compile_task({**TASK, **update})


if __name__ == '__main__':
    unittest.main()

"""Small constructor interfaces: bounded choices and exact witnessed source lines."""
import unittest

from symblic.delegate import contracts as D
from symblic.adapters import logic as L
from symblic.kernel.run import Run


class Apps:
    def __init__(self, *answers):
        self.answers = list(answers); self.requests = []
    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}}


def execute(body, *answers):
    task = D.compile_task(body); apps = Apps(*answers)
    report = Run(task['source'], task['inputs'], apps, {**task['options'], 'by': 'fake:small'}).execute()
    return task, apps, report


class Micro(unittest.TestCase):
    def test_enum_classification_is_grammar_bounded_but_not_truth_verified(self):
        body = {'template': 'enum_classification', 'params': {'instruction': 'Choose a color.',
            'data': 'a red apple', 'categories': {'red': 'red items', 'blue': 'blue items'}}}
        task, apps, report = execute(body, 'blue')
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(apps.requests[0]['schema']['properties']['answer']['enum'], ['blue', 'red'])
        self.assertEqual(task['assurance']['scope'], 'membership_in_caller_categories')
        self.assertIn('classification correctness', task['assurance']['unassessed'])
        self.assertEqual(task['assurance']['origin'], 'model_proposal')
        for bad in ({}, {'a; act steal': 'bad'}, {'valid': ''}):
            with self.assertRaises(D.ContractError):
                D.compile_task({**body, 'params': {**body['params'], 'categories': bad}})

    def test_witnessed_line_preserves_unicode_crlf_and_exact_revision(self):
        text = 'Café: fresh.\r\n\r\nPrice: 3 EUR.\n'
        body = {'template': 'witnessed_line', 'params': {'instruction': 'Find the price line.',
            'text': text, 'source_id': 'shop', 'revision': 3}}
        task, apps, report = execute(body, 2)
        self.assertEqual(report['status'], 'done', report.get('error'))
        witness = next(row['value'] for row in report['bindings'] if row['name'] == 'witness')
        self.assertEqual(witness['quote'], 'Price: 3 EUR.\n')
        self.assertEqual(text[witness['start']:witness['end']], witness['quote'])
        self.assertEqual(witness['revision'], 3)
        self.assertEqual(apps.requests[0]['schema']['properties']['answer'], {'type': 'integer', 'minimum': 1, 'maximum': 2})
        self.assertNotIn(witness['source_sha256'], apps.requests[0]['prompt'])
        self.assertIn('semantic entailment', task['assurance']['unassessed'])
        self.assertNotIn('candidate_spans', task['context']['ask_dependencies'][0]['required_names'])

    def test_no_line_is_silently_truncated_and_invalid_choice_is_not_accepted(self):
        body = {'template': 'witnessed_line', 'calls': 1, 'params': {'instruction': 'Pick a line.',
            'text': 'a\nb', 'source_id': 's'}}
        _task, apps, report = execute(body, 3)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 1)
        for text in (' \n\r\n', '\n'.join('line' for _ in range(65))):
            with self.assertRaises(D.ContractError):
                D.compile_task({**body, 'params': {**body['params'], 'text': text}})

    def test_nested_proof_certificate_gets_a_closed_outer_schema(self):
        task = L.compile_task({'premises': 'p: "A"', 'goal': '"A"', 'certificate_format': 'terms'})
        apps = Apps({'version': 1, 'proof': ['premise', 'p']})
        report = Run(task['source'], task['inputs'], apps, {**task['options'], 'by': 'fake:small'}).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        schema = apps.requests[0]['schema']['properties']['answer']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), {'version', 'proof'})
        self.assertEqual(schema['properties']['proof'], {'type': 'array', 'items': {}, 'minItems': 2, 'maxItems': 6})

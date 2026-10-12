"""Any's JSON schema matches its existing runtime domain; no real providers."""
import copy
import unittest

from symblic.kernel import language as S
from symblic.kernel.run import Run


class Reply:
    def __init__(self, value):
        self.value = value
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': copy.deepcopy(self.value)},
                'model': 'schema-fixture', 'node': 'fixture'}


class AnySchema(unittest.TestCase):
    def run_answer(self, type_text, value, declarations=''):
        reader = Reply(value)
        run = Run(declarations + f'ask x: {type_text} "Fixture" by "fake:schema" '
                  'with votes=1, retries=0.\n', {}, reader)
        report = run.execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual(1, len(reader.requests))
        self.assertEqual(1, report['calls'])
        schema = reader.requests[0]['schema']
        self.assertIn('answer', schema['required'])
        self.assertFalse(schema['additionalProperties'])
        self.assertTrue(S.values_equal(run.kernel.env.lookup('x').value, S.from_json(value)))
        return schema['properties']['answer']

    def test_any_schema_is_unrestricted_json(self):
        self.assertEqual({}, S.json_schema({'k': 'any'}))

    def test_any_runtime_and_request_schema_cover_every_json_kind(self):
        values = [None, False, True, 0, -7, 1.25, '', 'exact text', [], [1, None, False],
                  {}, {'count': 2, 'nested': {'enabled': True}}]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual({}, self.run_answer('Any', value))

    def test_list_of_any_preserves_mixed_json_items(self):
        schema = self.run_answer('List of Any', [None, True, 3, 1.25, 'text', [], {'x': [False]}])
        self.assertEqual({'type': 'array', 'items': {}}, schema)

    def test_nested_record_and_list_any_schema_is_resolved_recursively(self):
        value = {'payload': {'nested': [None, 7]}, 'rows': [{'values': [True, 'text', {'x': 3}]}]}
        schema = self.run_answer('Record {payload: Any, rows: List of Record {values: List of Any}}', value)
        self.assertEqual({}, schema['properties']['payload'])
        rows = schema['properties']['rows']
        self.assertEqual('array', rows['type'])
        self.assertEqual('object', rows['items']['type'])
        self.assertEqual({}, rows['items']['properties']['values']['items'])
        self.assertFalse(schema['additionalProperties'])
        self.assertFalse(rows['items']['additionalProperties'])

    def test_named_record_type_keeps_any_schema_inside_lists(self):
        schema = self.run_answer('List of Box', [{'value': None}, {'value': {'a': [1, False]}}],
                                 'define Box as Record {value: Any}.\n')
        self.assertEqual({}, schema['items']['properties']['value'])
        self.assertEqual(['value'], schema['items']['required'])

    def test_specific_type_schemas_remain_constrained(self):
        self.assertEqual({'type': 'string'}, S.json_schema({'k': 'text'}))
        self.assertEqual({'type': 'boolean'}, S.json_schema({'k': 'bool'}))
        self.assertEqual({'type': 'number'}, S.json_schema({'k': 'number'}))
        self.assertEqual({'type': 'integer', 'minimum': 0, 'maximum': 2},
                         S.json_schema({'k': 'int', 'lo': 0, 'hi': 2}))
        self.assertEqual({'type': 'array', 'items': {'type': 'string'}},
                         S.json_schema({'k': 'list', 'of': {'k': 'text'}}))


if __name__ == '__main__':
    unittest.main()

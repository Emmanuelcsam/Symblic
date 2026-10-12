"""Pure bounded shape/lossless checks; no providers or stores."""
import copy
import json
import unittest
from unittest import mock

from symblic.kernel import language as S
from symblic.kernel import json_schema as J
from symblic.mica import search as M
from symblic.mica import native as N
from symblic.mica import project as P
from tests.mica.test_symblic_mica_execution import request, proposal, ROUTE


def obj(props):
    return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}


def declared(schema):
    return {'k': 'code', 'lang': 'json', 'json_schema': J.admit(schema), 'json_schema_version': J.VERSION}


class ShapeTests(unittest.TestCase):
    def test_literal_parser_is_data_not_interpolation(self):
        schema = obj({'literal': {'const': 'a "quote" \\ slash {missing} é\nnext'}})
        source = N.planner_source('Do the task.', ROUTE, schema=schema)
        tree = S.parse(source)
        ask = next(s for s in tree['statements'] if s.k == 'ask')
        self.assertEqual(ask.type, declared(schema))
        self.assertTrue(S.check(source)['ok'])
        self.assertEqual(J.validate(json.dumps({'literal': schema['properties']['literal']['const']}), schema),
                         json.dumps({'literal': schema['properties']['literal']['const']}))

    def test_nonliteral_and_wrong_language_refused(self):
        for source in ('ask a: Code json schema saved "task".', 'ask a: Code js schema "{}" "task".'):
            with self.subTest(source=source):
                self.assertFalse(S.check(source)['ok'])

    def test_numeric_lexemes_and_original_document_unchanged(self):
        ty = declared(obj({'x': {}, 's': {'type': 'string'}}))
        for number in ('0.100000000000000000000000000001', '-0', '1e-300', '9007199254740993'):
            raw = ' \r\n{"x":' + number + ',"s":"  e\\u0301\\r\\n {x} `  "}\r\n'
            receipt = {}
            out = S.read_answer(raw, ty, coercion='strict', receipt=receipt)[0]
            self.assertEqual(out, raw)
            self.assertEqual(out.encode(), raw.encode())
            self.assertEqual(receipt['changes'], [])

    def test_answer_property_is_not_unwrapped_and_fence_not_stripped(self):
        ty = declared(obj({'answer': {'type': 'string'}}))
        raw = '{"answer":"keep the object"}'
        self.assertEqual(S.read_answer(raw, ty)[0], raw)
        for invalid in ('```json\n' + raw + '\n```', {'answer': raw}, None):
            with self.subTest(invalid=invalid), self.assertRaises(S.SymblicError):
                S.read_answer(invalid, ty)

    def test_plain_code_semantics_preserved(self):
        self.assertEqual(S.read_answer('```json\n{"answer":"x"}\n```', {'k': 'code', 'lang': 'json'})[0], '{"answer":"x"}')
        self.assertEqual(S.read_answer('{"answer":"x"}', {'k': 'code', 'lang': 'json'})[0], 'x')
        self.assertIsNone(S.answer_schema({'k': 'code', 'lang': 'json'}, False))

    def test_coerce_and_nested_kernel_type_checks_cannot_bypass(self):
        ty = declared(obj({'x': {'type': 'integer'}}))
        for check in (lambda: S.coerce('{"x":true}', ty),
                      lambda: S.check_value('{"x":true}', ty),
                      lambda: S.check_value(('{"x":true}',), {'k': 'list', 'of': ty})):
            with self.assertRaises(S.SymblicError):
                check()

    def test_named_type_preserves_schema(self):
        label = S.type_label(declared(obj({'x': {'type': 'integer'}})))
        from symblic.kernel import run as SR
        from symblic.spec import sheets as SP
        for raw, wanted in (('{"x":1}', 'done'), ('{"x":true}', 'failed')):
            source = 'define Result as ' + label + '.\nlet result: Result = ' + SP.literal(raw) + '.\n'
            self.assertTrue(S.check(source)['ok'], S.check(source))
            with __import__('tempfile').TemporaryDirectory() as folder:
                report = SR.Run(source, folder=folder, options={'profile': 'verified'}).execute()
            self.assertEqual(report['status'], wanted, report)
            if wanted == 'failed':
                self.assertEqual(report['error']['kind'], 'type')

    def test_closed_keyword_subset_and_contradictions(self):
        invalid = [{'$ref': '#/x'}, {'type': 'string', 'pattern': '^x$'}, {'type': 'number', 'minimum': 0},
                   {'anyOf': [{}], 'type': 'string'}, {'anyOf': [{}] * 9},
                   {'type': 'integer', 'minimum': 3, 'maximum': 1}, {'type': 'integer', 'const': True},
                   {'const': 1, 'enum': [2]}, {'enum': [1.5]}, {'type': 'array'},
                   {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': True}]
        for schema in invalid:
            with self.subTest(schema=schema), self.assertRaises(J.SchemaError):
                J.admit(schema)

    def test_shape_rejections_and_generic_values(self):
        schema = obj({'x': {'type': 'integer', 'minimum': -2, 'maximum': 3}})
        for raw in ('{}', '{"x":1,"extra":1}', '{"x":true}', '{"x":1.5}', '{"x":4}', '{"x":null}'):
            with self.subTest(raw=raw), self.assertRaises(J.ValidationError):
                J.validate(raw, schema)
        for raw in ('{"a":[null,true,1e100,"x"]}', 'null', '[]', '"text"', '-0', '1.5'):
            self.assertEqual(J.validate(raw, {}), raw)

    def test_duplicate_nonfinite_unicode_and_malformed_refused(self):
        for raw in ('{"x":1,"x":2}', 'NaN', 'Infinity', '{', '"\\ud800"', '"\ud800"'):
            with self.subTest(raw=repr(raw)), self.assertRaises(J.ValidationError):
                J.validate(raw, {})

    def test_resource_limits_are_separate_from_invalid_shape(self):
        for raw in ('[' * 33 + '0' + ']' * 33, '1e999999', '1e99999999999999999999999999', '1' * 1237):
            with self.subTest(raw=raw[:40]), self.assertRaises(J.ResourceError):
                J.validate(raw, {})
        for name, value in (('MAX_TEXT_CHARS', 1), ('MAX_DATA_NODES', 1), ('MAX_STEPS', 0)):
            with self.subTest(name=name), mock.patch.object(J, name, value), self.assertRaises(J.ResourceError):
                J.validate('[1,2]', {'type': 'array', 'items': {}})
        with mock.patch.object(J, 'MAX_STEPS', 0), self.assertRaises(S.SymblicError) as caught:
            S.read_answer('{}', declared({}))
        self.assertEqual(caught.exception.kind, 'resource')

    def test_schema_detaches_and_version_is_checked(self):
        schema = obj({'x': {'type': 'string'}})
        ty = declared(schema); schema['properties']['x']['type'] = 'integer'
        self.assertEqual(S.read_answer('{"x":"a"}', ty)[0], '{"x":"a"}')
        ty['json_schema_version'] = 999
        with self.assertRaises(S.SymblicError) as caught:
            S.read_answer('{"x":"a"}', ty)
        self.assertEqual(caught.exception.kind, 'version')

    def test_factored_prompt_expands_to_exact_schema(self):
        def expand(node, defs):
            if type(node) is list:
                return [expand(x, defs) for x in node]
            if type(node) is not dict:
                return node
            if '$ref' in node:
                return expand(defs[node['$ref'].split('/')[-1]], defs)
            return {k: expand(v, defs) for k, v in node.items() if k != '$defs'}
        req = M.C.normalize_request({**request(), 'artifact_format': 'javascript_modules'})
        shape = M.proposal_schema(req)
        display = json.loads(J.describe(shape))
        self.assertEqual(expand(display, display.get('$defs', {})), shape)
        self.assertLess(len(J.describe(shape)), len(json.dumps(shape)))
        ty = declared(shape)
        cap = S.capsule('test', 1, 1, S.statement_source('p', ty, M.plan_prompt(req)), ty, 'low', [], [],
                        profile='verified', budget=24000)
        transport = json.dumps(cap['schema'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        self.assertEqual(cap['schema'], shape)
        self.assertLessEqual(len(cap['system']) + len(cap['prompt']) + len(transport), 24000)

    def test_all_optional_graph_fields_and_refinement_preserved(self):
        req = M.C.normalize_request({**request(), 'artifact_format': 'javascript_modules'})
        base = proposal(); unit = base['units'][0]
        construction = {'kind': 'affine_integer_v1', 'parameters': [{'name': 'x', 'lo': -5, 'hi': 5}],
                        'coefficient_bounds': [{'lo': 1, 'hi': 1}], 'intercept_bounds': {'lo': 1, 'hi': 1}}
        for assumptions in (False, True):
            for has_path in (False, True):
                for native in (None, construction, {**construction, 'version': 1}):
                    row = {'units': [{**unit, **({'output_path': 'units/step.js'} if has_path else {}),
                                      **({'construction': native})}]}
                    if assumptions:
                        row['assumptions'] = []
                    J.validate(json.dumps(row), M.proposal_schema(req))
        null_plan = copy.deepcopy(base); null_plan['units'][0]['construction'] = None
        self.assertIsInstance(M.proposal_to_plan(req, null_plan), dict)
        refined = copy.deepcopy(base); refined['units'][0]['examples'] = []
        refined['units'][0]['construction'] = None
        refined['units'].append({**unit, 'id': 'helper', 'names': ['helper']})
        for assumptions in (False, True):
            row = copy.deepcopy(refined)
            if not assumptions:
                row.pop('assumptions')
            J.validate(json.dumps(row), M.proposal_schema(req, refinement=True))
        with self.assertRaises(J.ValidationError):
            J.validate(json.dumps(refined), M.proposal_schema(req))

    def test_schema_pins_registered(self):
        from symblic.kernel import execution_pins as X
        self.assertIn('symblic/kernel/json_schema.py', X.REQUIRED_FILES)
        self.assertIn('symblic/kernel/json_schema.py', X.PYTHON_FILES)
        self.assertIn('symblic/js/normalize.py', X.REQUIRED_FILES)
        self.assertIn('symblic/js/normalize.js', X.ASSET_FILES)
        self.assertEqual(set(S.kernel_id()['js_normalize_assets']), {'normalize.py', 'normalize.js', 'acorn.js'})
        self.assertEqual(S.kernel_id()['json_schema'], J.VERSION)
        self.assertIn('symblic/kernel/json_schema.py', M.implementation_identity()['sources'])

    def test_normalizer_closure_change_refuses_fresh_process_before_execution(self):
        import shutil
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from symblic.kernel import execution_pins as X
        source = 'show 5.\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(X.BASE / 'symblic', root / 'symblic', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            create = """import hashlib,json
from symblic.kernel import execution_pins as X
from pathlib import Path
hashes={name:hashlib.sha256((X.BASE/name).read_bytes()).hexdigest() for name in X.REQUIRED_FILES}
Path('pins.json').write_text(json.dumps(X.build('show 5.\\n',{},hashes)))
"""
            check = """import json
from symblic.kernel import language as S, execution_pins as X
from pathlib import Path
pins=json.loads(Path('pins.json').read_text())
try:
 X.validate(pins,'show 5.\\n',{})
except S.SymblicError as exc:
 assert exc.kind=='version',exc
 print('refused')
else:
 raise AssertionError('Changed executable normalizer closure was accepted')
"""
            built = subprocess.run([sys.executable, '-B', '-c', create], cwd=root, capture_output=True, text=True, timeout=180)
            self.assertEqual(built.returncode, 0, built.stderr)
            for name in ('symblic/js/normalize.py', 'symblic/js/normalize.js', 'symblic/js/acorn.js'):
                with self.subTest(name=name):
                    path = root / name
                    raw = path.read_bytes()
                    path.write_bytes(raw + b'\n')
                    try:
                        result = subprocess.run([sys.executable, '-B', '-c', check], cwd=root,
                                                capture_output=True, text=True, timeout=180)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), 'refused')
                    finally:
                        path.write_bytes(raw)


if __name__ == '__main__':
    unittest.main()

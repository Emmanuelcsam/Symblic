"""Optional declaration contracts: real sandbox parsing, never candidate execution."""

import hashlib
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.js import contract as C


def contract(**exports):
    return {'version': 1, 'exports': exports}


class DeclarationContracts(unittest.TestCase):
    def check(self, source, **exports):
        return C.check(source, contract(**exports))

    def codes(self, result):
        return {row['code'] for row in result['diagnostics']}

    def test_exact_functions_and_deferred_bodies_without_execution(self):
        source = '"use strict"; async function f(){throw new Error("not executed")} function* g(){while(true) yield 1};'
        with patch.object(JS, 'evaluate', side_effect=AssertionError('candidate execution forbidden')):
            result = self.check(source, f='function', g='function')
        self.assertTrue(result['passed'], result)
        self.assertEqual([row['name'] for row in result['declarations']], ['f', 'g'])
        self.assertEqual(result['source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(result['parser']['version'], '8.8.1')
        self.assertEqual(result['runtime']['assets']['parser'], C.PARSER_SHA256)

    def test_exact_names_kinds_missing_extra_and_duplicate(self):
        fixtures = [('function wrong(){}', contract(wanted='function'), {'unexpected_name', 'missing_name'}),
                    ('const f=()=>1', contract(f='function'), {'wrong_kind'}),
                    ('function f(){} function f(){}', contract(f='function'), {'duplicate_name'}),
                    ('function f(){} var f;', contract(f='function'), {'duplicate_name', 'wrong_kind'}),
                    ('function f(){} function helper(){}', contract(f='function'), {'unexpected_name'})]
        for source, rule, expected in fixtures:
            with self.subTest(source=source):
                result = C.check(source, rule)
                self.assertFalse(result['passed'])
                self.assertEqual(result['status'], 'invalid')
                self.assertTrue(expected <= self.codes(result), result)

    def test_top_level_wrapper_and_statements_refuse_without_running(self):
        sources = ['(()=>{globalThis.f=function(){}})()', 'for(;;){}', 'throw new Error("ran")',
                   'globalThis.f = function(){}', 'if(true){function f(){}}',
                   'try{}catch(e){}', '"arbitrary directive"; function f(){}']
        for source in sources:
            with self.subTest(source=source):
                result = self.check(source, f='function')
                self.assertFalse(result['passed'])
                self.assertIn('top_level_statement', self.codes(result))

    def test_top_level_return_import_export_and_bad_syntax_are_syntax_errors(self):
        for source in ('return 1;', 'export function f(){}', 'import x from "fs";', 'function f( {',
                       '#!/usr/bin/node\nfunction f(){}', 'await Promise.resolve();'):
            with self.subTest(source=source):
                result = self.check(source, f='function')
                self.assertEqual(result['status'], 'invalid')
                self.assertIn('syntax_error', self.codes(result))

    def test_variable_policy_allows_only_declared_passive_initializers(self):
        source = ('const f=(x)=>x+1, data={n:-2, items:[1,null,,true], method(){return Date.now()}}; '
                  'let pending; var flag, literal=`abc`, expression=/a+/;')
        result = self.check(source, f='const', data='const', pending='let', flag='var',
                            literal='var', expression='var')
        self.assertTrue(result['passed'], result)
        for expression in ('(()=>{throw 1})()', 'Math.random()', 'obj.x', 'missing', 'new Date()',
                           '{...source}', '[...source]', '{get x(){return 1}}', '{["x"]:1}',
                           '{x}', '`abc${other}`', '({valueOf(){throw 1}})+1', 'await other'):
            with self.subTest(expression=expression):
                result = self.check('const f=' + expression, f='const')
                self.assertFalse(result['passed'])
                self.assertTrue(self.codes(result) & {'active_initializer', 'syntax_error'}, result)

    def test_destructuring_is_an_explicit_policy_refusal(self):
        result = self.check('const {f}={f:1}', f='const')
        self.assertIn('destructuring_declaration', self.codes(result))
        self.assertIn('missing_name', self.codes(result))

    def test_class_policy_separates_deferred_bodies_from_eager_definition_work(self):
        source = ('class A { field = dangerous(); static n={x:1}; constructor(){throw 1} '
                  'method(){return eval("x")} get value(){return sideEffect()} } '
                  'const B=class { static make(){return new Date()} };')
        self.assertTrue(self.check(source, A='class', B='const')['passed'])
        for source in ('class A extends B {}', 'class A {static {throw 1}}',
                       'class A {[dangerous()](){}}', 'class A {static n=dangerous()}'):
            with self.subTest(source=source):
                result = self.check(source, A='class')
                self.assertIn('active_class_definition', self.codes(result))
        self.assertIn('active_initializer', self.codes(self.check('const A=class extends B {}', A='const')))

    def test_comments_strings_and_unicode_escapes_are_parsed_not_searched(self):
        source = ('/* function extra(){} */ function \\u0066(){return "var hidden=1;"} '
                  'const text="function fake(){}";')
        result = self.check(source, f='function', text='const')
        self.assertTrue(result['passed'], result)
        result = self.check('function α(){}')
        self.assertIn('unsupported_identifier', self.codes(result))

    def test_proto_named_binding_does_not_pollute_expected_or_seen_maps(self):
        result = self.check('var __proto__=null; function constructor(){}',
                            __proto__='var', constructor='function')
        self.assertTrue(result['passed'], result)

    def test_exact_contract_identity_and_source_identity_are_separate(self):
        source = 'function f(){}'
        a = C.check(source, contract(f='function'))
        b = C.check(source + '\n', contract(f='function'))
        c = C.check(source, contract(f='const'))
        self.assertEqual(a['contract_sha256'], b['contract_sha256'])
        self.assertNotEqual(a['source_sha256'], b['source_sha256'])
        self.assertNotEqual(a['contract_sha256'], c['contract_sha256'])
        self.assertFalse(c['passed'])

    def test_finite_diagnostics_locations_and_truncation(self):
        result = self.check('\n' + '\n'.join(f'function extra{i}(){{}}' for i in range(40)))
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['diagnostics']), 32)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['diagnostics'][0]['line'], 2)
        self.assertEqual(result['diagnostics'][0]['column'], 1)

    def test_parser_resource_limits_are_distinct_from_invalid_declarations(self):
        for source in (';' * 50001, 'const f=' + '{x:' * 140 + '1' + '}' * 140):
            with self.subTest(size=len(source)):
                result = self.check(source, f='const')
                self.assertFalse(result['passed'])
                self.assertEqual(result['status'], 'budget')
        result = C.check('function f(){}', contract(f='function'), deadline=time.monotonic() - 1)
        self.assertEqual(result['status'], 'budget')
        self.assertIn('deadline', self.codes(result))

    def test_invalid_inputs_refuse_before_parser(self):
        with patch.object(C, '_parse', side_effect=AssertionError('invalid input reached parser')):
            for rule in ({}, {'version': True, 'exports': {}}, {'version': 1, 'exports': []},
                         contract(f='unknown'), contract(**{'bad-name': 'function'}),
                         {'version': 1, 'exports': {}, 'extra': True}):
                with self.subTest(rule=rule), self.assertRaises(JS.JsError):
                    C.check('function f(){}', rule)
            for source in ([], '\ud800', 'x' * (C.MAX_SOURCE_BYTES + 1)):
                with self.subTest(source_type=type(source)), self.assertRaises(JS.JsError):
                    C.check(source, contract())

    def test_assets_are_pinned_frozen_and_disk_changes_refuse(self):
        originals = {key: (C.HERE / name).read_bytes() for key, name in C.ASSETS.items()}
        for kind in ('parser', 'runner', 'license'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)
                for key, name in C.ASSETS.items():
                    (path / name).write_bytes(originals[key])
                with patch.object(C, 'HERE', path), patch.object(C, '_assets', {}):
                    first = C.asset_snapshot()
                    first['runner'] = b'caller mutation'
                    self.assertEqual(C.asset_snapshot()['runner'], originals['runner'])
                    (path / C.ASSETS[kind]).write_bytes(originals[kind] + b'\n')
                    with self.assertRaises(JS.JsError) as raised:
                        C.asset_snapshot()
                    self.assertEqual(raised.exception.kind, 'version')

    def test_native_adapter_preserves_exact_contract_and_charges_before_launch(self):
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        result = C.FUNCTIONS['js_declarations_check'](kernel, node, 'function f(){}', S.from_json(contract(f='function')))
        self.assertTrue(result['passed'])
        self.assertEqual(result['scope'], C.SCOPE)
        with patch.object(C, 'check', side_effect=AssertionError('exhausted budget started parser')), \
                self.assertRaises(S.SymblicError):
            C.FUNCTIONS['js_declarations_check'](S.Kernel(budget=S.Budget(1)), node, '', S.from_json(contract()))


class ParserHostBoundaries(unittest.TestCase):
    def setUp(self):
        pump = patch.object(JS, '_communicate_bounded', side_effect=lambda proc, *a, **kw: proc.communicate())
        self.addCleanup(pump.stop)
        pump.start()

    def fake_process(self, output=b'', error=b'', code=0):
        return type('Process', (), {'pid': 123456, 'returncode': code,
                                   'communicate': lambda self, *a, **kw: (output, error)})()

    def test_sandbox_refusal_does_not_fall_back_to_host_parsing(self):
        with patch.object(C.subprocess, 'Popen', return_value=self.fake_process(code=125)) as launch, \
                self.assertRaises(JS.JsError) as raised:
            C.check('function f(){}', contract(f='function'))
        self.assertEqual(raised.exception.kind, 'unavailable')
        args, kwargs = launch.call_args
        self.assertIn('--require', args[0])
        self.assertIn('--no-unix', args[0])
        self.assertIn('--disallow-code-generation-from-strings', args[0])
        self.assertTrue(kwargs['start_new_session'])
        self.assertNotIn(str(C.HERE), args[0])

    def test_memory_output_and_malformed_protocol_are_separate_failures(self):
        for process, code in ((self.fake_process(error=b'heap out of memory', code=-6), 'memory_limit'),
                              (self.fake_process(output=b'x' * (C.MAX_OUTPUT_BYTES + 1)), 'output_limit')):
            with self.subTest(code=code), patch.object(C.subprocess, 'Popen', return_value=process):
                result = C.check('', contract())
                self.assertEqual(result['status'], 'budget')
                self.assertEqual(result['diagnostics'][0]['code'], code)
        for output in (b'not JSON', json.dumps({'passed': True}).encode()):
            with patch.object(C.subprocess, 'Popen', return_value=self.fake_process(output=output)):
                with self.assertRaises(JS.JsError) as raised:
                    C.check('', contract())
                self.assertEqual(raised.exception.kind, 'js')

    def test_forged_acceptance_without_exact_declarations_is_a_protocol_error(self):
        output = json.dumps({'passed': True, 'status': 'accepted', 'declarations': [],
                             'diagnostics': [], 'truncated': False}).encode()
        with patch.object(C.subprocess, 'Popen', return_value=self.fake_process(output=output)), \
                self.assertRaises(JS.JsError) as raised:
            C.check('function f(){}', contract(f='function'))
        self.assertEqual(raised.exception.kind, 'js')

    def test_streaming_timeout_is_reported_as_budget(self):
        process = self.fake_process()
        calls = []

        def communicate(*_args, **_kwargs):
            calls.append(True)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired('trusted parser', 5)
            return b'', b''

        process.communicate = communicate
        with patch.object(C.subprocess, 'Popen', return_value=process):
            result = C.check('', contract())
        self.assertEqual(result['status'], 'budget')
        self.assertEqual(result['diagnostics'][0]['code'], 'timeout')


if __name__ == '__main__':
    unittest.main()

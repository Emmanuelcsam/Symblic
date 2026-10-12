"""Adversarial subprocess output stays bounded; only owned children are reaped."""
import subprocess
import sys
import time
import unittest

from symblic.js import check as JS


class BoundedPipes(unittest.TestCase):
    def launch(self, code):
        return subprocess.Popen([sys.executable, '-I', '-c', code], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)

    def test_simultaneous_large_input_stdout_stderr_do_not_deadlock(self):
        proc = self.launch('import sys; sys.stderr.buffer.write(b"e"*65536); '
                           'sys.stderr.flush(); data=sys.stdin.buffer.read(); '
                           'sys.stdout.buffer.write(data)')
        body = b'a' * 200000
        out, err = JS._communicate_bounded(proc, body, deadline=time.monotonic() + 5)
        self.assertEqual(out, body)
        self.assertEqual(err, b'e' * 65536)
        self.assertEqual(proc.returncode, 0)

    def test_infinite_stdout_or_stderr_is_killed_at_the_limit(self):
        for stream in ('stdout', 'stderr'):
            with self.subTest(stream=stream):
                proc = self.launch(f'import sys\nwhile True: sys.{stream}.buffer.write(b"x"*65536)')
                with self.assertRaises(JS.JsError) as error:
                    JS._communicate_bounded(proc, b'', deadline=time.monotonic() + 5,
                                            max_output_bytes=1024, max_error_bytes=1024)
                self.assertEqual(error.exception.kind, 'budget')
                self.assertIsNotNone(proc.returncode)
                self.assertTrue(all(getattr(proc, key).closed for key in ('stdin', 'stdout', 'stderr')))

    def test_closed_outputs_do_not_escape_wall_deadline(self):
        proc = self.launch('import os,time; os.close(1); os.close(2); time.sleep(20)')
        with self.assertRaises(subprocess.TimeoutExpired):
            JS._communicate_bounded(proc, b'', deadline=time.monotonic() + .15)
        self.assertIsNotNone(proc.returncode)

    def test_invalid_public_limits_refuse_without_launch(self):
        for limit in (True, 0, -1, JS.MAX_OUTPUT_BYTES + 1, 1.5):
            with self.subTest(limit=limit), self.assertRaises(JS.JsError):
                JS.evaluate('', [], max_output_bytes=limit)

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_real_candidate_large_result_is_budget_not_an_accepted_value(self):
        with self.assertRaises(JS.JsError) as error:
            JS.evaluate('', ['"x".repeat(2000000)'], max_output_bytes=4096)
        self.assertEqual(error.exception.kind, 'budget')
        self.assertEqual(JS.evaluate('', ['[1,2,3]'], max_output_bytes=4096)[0]['value'], '[1,2,3]')

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_candidate_cannot_replace_or_shadow_checker_intrinsics(self):
        for source in ('function f(){return 0;} JSON.stringify=()=>"2";',
                       'const JSON={stringify:()=>"2"}; function f(){return 0;}',
                       'function f(){JSON.stringify=()=>"2"; return 0;}',
                       'const Number={isFinite:()=>true}; const String=()=>"2"; function f(){return NaN;}',
                       'const __symblicEncodeResult=()=>"2"; function f(){return 0;}'):
            with self.subTest(source=source):
                self.assertFalse(JS.test(source, [('f()', '2')])['passed'])

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_candidate_cannot_erase_function_snapshot_to_replace_dependency(self):
        for evasion in ('delete globalThis[Symbol.for("symblic.defined")];',
                        'Object.getOwnPropertyNames=()=>[];', 'JSON.stringify=()=>"[]";',
                        'Symbol.for=()=>Symbol();'):
            with self.subTest(evasion=evasion):
                result = JS.test(['function f(){return 1;}', evasion + 'function f(){return 2;}'], [('f()', '2')])
                self.assertFalse(result['passed'])
                self.assertIn('defines f again', result['report'])
        result = JS.test(['function f(){return 1;}', 'delete globalThis.f;'], [('typeof f', '"undefined"')])
        self.assertFalse(result['passed'])

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_prior_callable_bindings_remain_fixed_during_later_calls(self):
        variants = [
            ['globalThis.f=function(){return 1;}', 'const f=()=>2;'],
            ['function f(){return 1;}', 'function g(){f=()=>2; return f();}'],
            ['function f(){return 1;}', 'function g(){const old=f; f=()=>2; const n=f(); f=old; return n;}'],
            ['Object.defineProperty(globalThis,"f",{get(){return ()=>1;}, configurable:true});', 'const f=()=>2;'],
        ]
        for pieces in variants:
            with self.subTest(pieces=pieces):
                self.assertFalse(JS.test(pieces, [('typeof g === "function" ? g() : f()', '2')])['passed'])
        self.assertTrue(JS.test(['var n=0; function bump(){return ++n;}',
                                 'function twice(){bump(); return bump();}'], [('twice()', '2')])['passed'])

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_duplicate_declarations_fail_even_when_frozen_function_would_be_kept(self):
        # Node 20 silently ignores some declarations of non-writable globals;
        # expecting the original result reproduces the old false acceptance.
        for declaration in ('function f(){return 2;}', r'function \u0066(){return 2;}',
                            'async function f(){return 2;}', 'function* f(){yield 2;}',
                            '{ function f(){return 2;} }', 'if (true) function f(){return 2;}',
                            'try{throw 0;}catch(f){{function f(){return 2;}}}',
                            'switch(1){case 1: function f(){return 2;}}'):
            with self.subTest(declaration=declaration):
                result = JS.test(['function f(){return 1;}', declaration], [('f()', '1')])
                self.assertFalse(result['passed'])
                self.assertIn('defines f again', result['report'])
        for name in ('café', '𝒇'):
            with self.subTest(name=name):
                result = JS.test([f'function {name}(){{return 1;}}', f'function {name}(){{return 2;}}'],
                                 [(f'{name}()', '1')])
                self.assertFalse(result['passed'])
                self.assertIn(f'defines {name} again', result['report'])

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_local_functions_and_same_piece_classic_declarations_remain_valid(self):
        for piece in ('function g(){function f(){return 2;} return f();}',
                      '"use strict"; {function f(){return 2;}} function g(){return 2;}',
                      '{let f=0; {function f(){return 2;}}} function g(){return 2;}',
                      'try{throw {f:0};}catch({f}){{function f(){return 2;}}} function g(){return 2;}',
                      'for(let f=0; f<1; f++){function f(){return 2;}} function g(){return 2;}',
                      '{async function f(){return 2;}} function g(){return 2;}',
                      '{function* f(){yield 2;}} function g(){return 2;}',
                      '// function f(){}\nconst text="function f(){}"; function g(){return 2;}'):
            with self.subTest(piece=piece):
                result = JS.test(['function f(){return 1;}', piece], [('f()', '1'), ('g()', '2')])
                self.assertTrue(result['passed'], result['report'])
        result = JS.test('function f(){return 1;} function f(){return 2;}', [('f()', '2')])
        self.assertTrue(result['passed'], result['report'])

    @unittest.skipUnless(JS.available(), 'sandboxed node unavailable')
    def test_parser_exhaustion_is_inconclusive_before_candidate_execution(self):
        with self.assertRaises(JS.JsError) as caught:
            JS.test(';' * 100001, [('1', '1')])
        self.assertEqual(caught.exception.kind, 'resource')

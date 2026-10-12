"""A callable overwritten outside the checker must never pass by a swallowed write."""
import unittest

from symblic.js import check as JS


@unittest.skipUnless(JS.available(), 'sandboxed Node unavailable')
class BindingWrites(unittest.TestCase):
    def rejects(self, pieces, call='f()', expected='1'):
        result = JS.test(pieces, [(call, expected)])
        self.assertFalse(result['passed'], result)
        self.assertIn('defines f again', result['report'])

    def test_historical_list_item_false_acceptance(self):
        result = JS.test([
            'function listItem(line){return "<li>"+line+"</li>";}',
            'function renderList(lines){return lines.map(listItem).join("");}\n'
            'listItem=function(line){return line;};',
        ], [('renderList(["x"])', '"<li>x</li>"')])
        self.assertFalse(result['passed'], result)
        self.assertIn('defines listItem again', result['report'])
        self.assertIn('listItem=function', result['report'])

    def test_direct_compound_update_destructuring_and_loop_writes(self):
        for write in ('f=()=>2;', 'f+=1;', 'f++;', '--f;', '[f]=[()=>2];',
                      '({f}={f:()=>2});', '({x:f}={x:()=>2});',
                      '[...f]=[()=>2];', 'for(f of [()=>2]){}', 'for(f in {x:1}){}',
                      r'\u0066=()=>2;', 'f &&= ()=>2;', 'f **= 2;', 'delete f;'):
            with self.subTest(write=write):
                self.rejects(['function f(){return 1;}', write])

    def test_closures_temporary_restore_and_caught_writes(self):
        for body in ('f=()=>2; return 1;',
                     'const old=f; f=()=>2; f=old; return 1;',
                     'try{f=()=>2;}catch(e){} return 1;',
                     'const fn=()=>{f=()=>2;};fn();return 1;',
                     'return (({x:f}={x:()=>2}),1);'):
            with self.subTest(body=body):
                self.rejects(['function f(){return 1;}', 'function g(){'+body+'}'], 'g()')

    def test_same_piece_closure_is_guarded_at_call_time(self):
        self.rejects('function f(){return 1;} function g(){f=()=>2;return 1;}', 'g()')
        self.rejects('function f(){return 1;} class C { x=(f=()=>2); }', '(new C(),1)')
        result = JS.test('function f(){return 1;} f=()=>2;', [('f()', '2')])
        self.assertTrue(result['passed'], result)

    def test_computed_aliases_and_reflection_are_rejected(self):
        for write in ('globalThis.f=()=>2;', 'const alias=globalThis; alias["f"]=()=>2;',
                      'Reflect.set(globalThis,"f",()=>2);',
                      'Reflect.defineProperty(globalThis,"f",{value:()=>2});',
                      'try{Object.defineProperty(globalThis,"f",{value:()=>2});}catch(e){}',
                      'delete globalThis.f;', 'Reflect.deleteProperty(globalThis,"f");',
                      'const {set}=Reflect;set(globalThis,"f",()=>2);',
                      'const {defineProperty:d}=Object;try{d(globalThis,"f",{value:()=>2});}catch(e){}',
                      'try{__defineGetter__.call(globalThis,"f",()=>()=>2);}catch(e){}'):
            with self.subTest(write=write):
                self.rejects(['function f(){return 1;}', write])

    def test_local_shadows_and_data_mutation_keep_classic_semantics(self):
        for body in ('function g(f){f++;return f;} g(1)',
                     'function g(){var f=1;f++;return f;}g()',
                     'function g(){let f;[f]=[2];return f;}g()',
                     'function g(){let f=1;const add=()=>++f;return add();}g()',
                     'function g(){try{throw 1;}catch(f){f++;return f;}}g()',
                     'function g(){let n=0;for(let f=0;f<2;f++){n++;}return n;}g()',
                     '(function f(){return 2;})()',
                     '(()=>{const obj={f:1};obj.f++;return obj.f;})()'):
            # The IIFE keeps each valid declaration in local scope, while the
            # test still invokes an ordinary sloppy classic script.
            declaration, call = body.rsplit('}', 1) if body.startswith('function g') else ('', body)
            if declaration:
                declaration += '}'
            result = JS.test(['function f(){return 1;}', declaration], [(call, '2'), ('f()', '1')])
            self.assertTrue(result['passed'], (body, result))
        result = JS.test(['var n=0;function bump(){return ++n;}',
                          'function twice(){bump();return bump();}'], [('twice()', '2')])
        self.assertTrue(result['passed'], result)

    def test_accessor_setters_preserve_their_ordinary_semantics(self):
        pieces = ['var n=1; Object.defineProperty(globalThis,"box",'
                  '{get(){return n;},set(v){n=v;},configurable:true});function f(){return 1;}',
                  'box=2; function g(){return box;}']
        self.assertTrue(JS.test(pieces, [('g()', '2'), ('f()', '1')])['passed'])

    def test_no_host_error_object_crosses_a_caught_write_boundary(self):
        # The host-only preflight rejects this caught identifier write.
        # A property-based strict error below must originate in the candidate
        # realm, so its constructor cannot defeat the vm codegen restriction.
        pieces = ['function f(){return 1;}',
                  'function g(){"use strict";try{f=()=>2;}catch(e){'
                  'try{const p=e.constructor.constructor("return process")();'
                  'p.stdout.write("HOST_ESCAPE");}catch(blocked){} }return 1;}']
        self.rejects(pieces, 'g()')
        result = JS.test(['function f(){return 1;}',
                          'function g(){"use strict";try{globalThis.f=()=>2;}catch(e){'
                          'try{return e.constructor.constructor("return process")();}'
                          'catch(blocked){return blocked.name;}}return "unguarded";}'],
                         [('g()', '"EvalError"')])
        self.assertFalse(result['passed'], result)
        self.assertNotIn('HOST_ESCAPE', result['report'])
        # Intrinsics still come exclusively from the candidate's own realm.
        result = JS.test('function f(){try{return Error.constructor("return process")();}'
                         'catch(e){return e.name;}}', [('f()', '"EvalError"')])
        self.assertTrue(result['passed'], result)

    def test_write_inside_case_or_microtask_is_rejected(self):
        self.rejects('function f(){return 1;}', '(f=()=>2, 1)')
        self.rejects(['function f(){return 1;}',
                      'Promise.resolve().then(()=>{f=()=>2;});'])

    def test_incomplete_execution_keeps_its_resource_classification(self):
        for pieces, call in [(['function f(){return 1;}', 'globalThis.f=()=>2;while(true){}'], '1'),
                             (['function f(){return 1;}', 'function g(){globalThis.f=()=>2;while(true){}}'], 'g()'),
                             (['function f(){return 1;}', 'function g(){globalThis.f=()=>{while(true){}};return f();}'], 'g()')]:
            with self.subTest(pieces=pieces):
                result = JS.evaluate(pieces, [call], case_ms=50)
                self.assertEqual(result[0]['kind'], 'timeout')

    def test_source_frozen_properties_and_mutable_lexicals_keep_their_semantics(self):
        # These are already frozen by the artifact's own code, so no silent
        # checker-only change creates the historical false acceptance.
        result = JS.test(['function f(){return 1;} Object.defineProperty(globalThis,"f",{value:f,writable:false});',
                          'function g(){return f();}'], [('g()', '1')])
        self.assertTrue(result['passed'], result)
        # Mutable lexical state is outside the protected-global-property
        # contract. Its mutation must run in both checking and the artifact.
        result = JS.test(['let f=()=>1;', 'f=()=>2;'], [('f()', '2')])
        self.assertTrue(result['passed'], result)

    def test_parameter_defaults_and_switch_scopes_resolve_the_correct_binding(self):
        for declaration, call in [('function g(x=(f=()=>2)){var f;return 1;}', 'g()'),
                                  ('function g(){switch(1){case 1:f=()=>2;}return 1;}', 'g()')]:
            with self.subTest(declaration=declaration):
                self.rejects(['function f(){return 1;}', declaration], call)
        valid = [('function g(f,x=(f=2)){return f;}', 'g(1)'),
                 ('function g(){switch(1){case 1:let f=1;f++;return f;}}', 'g()'),
                 ('function g(){if(true){function f(){return 1;}}f=()=>2;return f();}', 'g()'),
                 ('function g(){try{throw {f:1};}catch({f}){f++;return f;}}', 'g()'),
                 ('function g(){try{throw 1}catch(f){{function f(){return 1;}}}f=()=>2;return f();}', 'g()')]
        for declaration, call in valid:
            with self.subTest(declaration=declaration):
                result = JS.test(['function f(){return 1;}', declaration], [(call, '2'), ('f()', '1')])
                self.assertTrue(result['passed'], result)

    def test_with_and_restored_reflection_preserve_the_finite_observation_boundary(self):
        changed = ['function f(){return 1;}',
                   'function g(){with(globalThis){const old=f;f=()=>2;'
                   'const value=f();f=old;return value;}}']
        result = JS.test(changed, [('g()', '1')])
        self.assertFalse(result['passed'], result)
        self.assertIn('artifact semantics', result['report'])
        # Same output and restored identities do not constitute evidence of a
        # faulty example. This intentionally is not a universal mutation proof.
        restored = ['function f(){return 1;}',
                    'function g(){with(globalThis){const old=f;f=()=>2;f=old;return 1;}}']
        self.assertTrue(JS.test(restored, [('g()', '1')])['passed'])

    def test_reflection_errors_keep_candidate_realm_constructors(self):
        source = ['function f(){return 1;}',
                  'function g(){try{Object.defineProperty(globalThis,"f",{get:1});}'
                  'catch(e){try{return e.constructor.constructor("return process")();}'
                  'catch(blocked){return blocked.name;}}return "unexpected";}']
        result = JS.test(source, [('g()', '"EvalError"'), ('f()', '1')])
        self.assertTrue(result['passed'], result)

    def test_alias_parameter_and_temporary_reflective_mutation_cannot_forge_a_pass(self):
        self.rejects(['function f(){return 1;}',
                      'function g(target,key){target[key]=()=>2;return 1;}'], 'g(globalThis,"f")')
        result = JS.test(['function f(){return 1;}',
                          'function g(target,key){const old=target[key];target[key]=()=>2;'
                          'const value=target[key]();target[key]=old;return value;}'],
                         [('g(globalThis,"f")', '2')])
        self.assertFalse(result['passed'], result)


if __name__ == '__main__':
    unittest.main()

"""Adjudicated verifier review: finite behavior, exception evidence, wall accounting."""
import json
import subprocess
import time
import unittest
from unittest import mock

from symblic.js import check as JS


@unittest.skipUnless(JS.available(), 'sandboxed Node unavailable')
class ReviewedBindings(unittest.TestCase):
    def test_reflective_mutation_followed_by_error_is_redefinition(self):
        for mutate in ['Reflect.set(globalThis,"f",null);',
                       'const target=globalThis;target["f"]=null;',
                       'Reflect.deleteProperty(globalThis,"f");']:
            with self.subTest(mutate=mutate):
                pieces=['function f(){return 1;}', 'function g(){'+mutate+'return f();}']
                result=JS.evaluate(pieces,['g()'])[0]
                self.assertFalse(result['ok'],result)
                self.assertEqual(result['kind'],'redefine',result)
                self.assertIn('defines f again',result['error'])
        # Piece loading can also mutate, then throw only under artifact semantics.
        result=JS.evaluate(['function f(){return 1;}',
            'Reflect.set(globalThis,"f",null);f();'],['1'])[0]
        self.assertEqual(result['kind'],'redefine',result)
        self.assertEqual(result['piece'],2)

    def test_mutation_before_timeout_remains_inconclusive(self):
        result=JS.evaluate(['function f(){return 1;}',
            'function g(){Reflect.set(globalThis,"f",null);while(true){}}'],['g()'],case_ms=50)[0]
        self.assertEqual(result['kind'],'timeout',result)
        with self.assertRaises(JS.JsError):
            with JS.verification_deadline_scope(time.monotonic()+.01):
                JS.test(['function f(){return 1;}','function g(){Reflect.set(globalThis,"f",null);while(true){}}'],[('g()','1')])

    def test_descriptor_inspection_is_documented_conservative_refusal(self):
        pieces=['function f(){return 1;}',
            'function inspect(){return Object.getOwnPropertyDescriptor(globalThis,"f").writable;}']
        result=JS.evaluate(pieces,['inspect()'])[0]
        self.assertEqual(result['kind'],'redefine',result)
        self.assertIn('artifact semantics',result['error'])
        # Matching an actually frozen artifact is supported; no ambient freeze mismatch.
        pieces[0]+='Object.defineProperty(globalThis,"f",{value:f,writable:false});'
        self.assertTrue(JS.test(pieces,[('inspect()','false')])['passed'])

    def test_class_heritage_resolves_its_inner_name_in_tdz(self):
        bodies=['const C=class f extends(f=class {}){};', '{class f extends(f=class {}){}}']
        for body in bodies:
            with self.subTest(body=body):
                result=JS.test(['function f(){return 1;}',
                    'function g(){try{'+body+'return "unexpected";}catch(e){return [e.name,f()];}}'],
                    [('g()','["ReferenceError",1]'),('f()','1')])
                self.assertTrue(result['passed'],result)
        # A differently named class does not shadow f; its write is forbidden.
        result=JS.evaluate(['function f(){return 1;}',
            'function g(){return class C extends(f=class {}){};}'],['g()'])[0]
        self.assertEqual(result['kind'],'redefine',result)
        self.assertIn('defines f again',result['error'])


class ReviewedWallAccounting(unittest.TestCase):
    def test_two_valid_realm_evaluations_fit_the_parent_allowance(self):
        # Ten 2.8-second calls in each realm need 56 seconds. The former 55-second
        # process allowance aborted this valid simulated child before completion.
        observed={}
        child=mock.Mock(returncode=0)
        payload=json.dumps({'version':1,'results':[{'ok':True,'value':'1'} for _ in range(10)]}).encode()
        def communicate(proc, body, *, deadline, **kwargs):
            observed['allowance']=deadline-time.monotonic()
            if observed['allowance']<56:raise subprocess.TimeoutExpired('fixture-node',observed['allowance'])
            return payload,b''
        with mock.patch.object(JS.subprocess,'Popen',return_value=child), mock.patch.object(JS,'_communicate_bounded',side_effect=communicate):
            results=JS.evaluate('function f(){return Math.max(1,1);}', ['f()']*10,case_ms=3000)
        self.assertTrue(all(r['ok'] for r in results),results)
        self.assertGreater(observed['allowance'],56)
        self.assertLessEqual(observed['allowance'],85)

    def test_absolute_deadline_still_overrides_dual_realm_allowance(self):
        child=mock.Mock(returncode=0);end=time.monotonic()+20;observed=[]
        def communicate(proc, body, *, deadline, **kwargs):
            observed.append(deadline)
            raise subprocess.TimeoutExpired('fixture-node',20)
        with JS.verification_deadline_scope(end):
            with mock.patch.object(JS.subprocess,'Popen',return_value=child), mock.patch.object(JS,'_communicate_bounded',side_effect=communicate):
                with self.assertRaises(JS.JsError) as raised:
                    JS.evaluate('function f(){return Math.max(1,1);}', ['f()']*10,case_ms=3000,deadline=end+100)
        self.assertEqual(raised.exception.kind,'budget')
        self.assertEqual(observed,[end])


if __name__=='__main__':unittest.main()

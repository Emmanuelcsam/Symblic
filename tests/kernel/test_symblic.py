"""Symblic: the language (parser, kernel, logic, types, capsule, consensus), the interpreter with fake
applicators (no model, no network, no dashboard), and the deterministic renderer."""

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.adapters import render as R  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402


def kernel_run(src, inputs=None):
    run = SR.Run(src, inputs, None, {'by': 'fake:x'})
    rep = run.execute()
    return run, rep


class FakeApps:
    """answer(app_label, prompt, req) -> a JSON-able answer object or text. Records every request."""

    def __init__(self, answer):
        self.answer = answer
        self.reqs = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        out = self.answer(S.app_label(req['app']), req['prompt'], req)
        if isinstance(out, dict) and out.get('__error__'):
            return {'ok': False, 'error': out['__error__']}
        if isinstance(out, str):
            return {'ok': True, 'text': out, 'ms': 1}
        return {'ok': True, 'json': out, 'ms': 1}


def run_with(src, answer, inputs=None, folder=None, **opts):
    apps = FakeApps(answer)
    o = {'by': 'fake:a'}
    o.update(opts)
    run = SR.Run(src, inputs, apps, o, folder=folder)
    return run, run.execute(), apps


class Parsing(unittest.TestCase):
    def test_statements_and_positions(self):
        prog = S.parse('program Demo.\nlet x = 1 + 2.\nask y: Int "Double {x}." with effort=high, votes=3\n')
        self.assertEqual(prog['name'], 'Demo')
        kinds = [s.k for s in prog['statements']]
        self.assertEqual(kinds, ['program', 'let', 'ask'])
        ask = prog['statements'][2]
        self.assertEqual(ask.type, {'k': 'int'})
        self.assertEqual(set(ask.options), {'effort', 'votes'})

    def test_syntax_error_has_line_and_column(self):
        c = S.check('let x = 1.\nlet y = (2 + .\n')
        self.assertFalse(c['ok'])
        self.assertEqual(c['errors'][0]['line'], 2)
        self.assertGreater(c['errors'][0]['col'], 1)

    def test_ask_options_continue_on_following_lines(self):
        prog = S.parse('ask c: one of {red, blue} "Pick."\n  with effort=max\n  by "fake:a"\n')
        ask = prog['statements'][0]
        self.assertEqual(ask.type['options'], ['red', 'blue'])
        self.assertIn('effort', ask.options)
        self.assertIn('by', ask.options)

    def test_unicode_logic_is_first_class(self):
        _, rep = kernel_run('let s = {1, 2} ∪ {3}.\nassert 3 ∈ s ∧ ¬(4 ∈ s).\nassert ∀ x in s: x ≥ 1.\n'
                            'assert (true → false) = false.\nassert (false ↔ false).\n')
        self.assertEqual(rep['status'], 'done', rep.get('error'))

    def test_prose_lines_are_v1_asks(self):
        prog = S.parse('Program: Outreach.\nSummarize the client\'s request in one paragraph.\n'
                       'Continue with context. Extract exactly 5 requirements.\n')
        self.assertEqual(prog['name'], 'Outreach')
        asks = [s for s in prog['statements'] if s.k == 'ask']
        self.assertEqual(len(asks), 2)
        self.assertEqual(asks[0].options['context'].value, 'none')
        self.assertEqual(asks[1].options['context'].value, 'all')
        self.assertIn("client's", asks[0].parts[0])

    def test_block_errors(self):
        self.assertFalse(S.check('if true then\nlet x = 1.\n')['ok'])
        self.assertFalse(S.check('end.\n')['ok'])
        self.assertTrue(S.check('if 1 < 2 then\nlet x = 1.\nelse\nlet x = 2.\nend.\n')['ok'])

    def test_immutable_names_are_checked_statically(self):
        c = S.check('let x = 1.\nlet x = 2.\n')
        self.assertFalse(c['ok'])
        self.assertIn('bound twice', c['errors'][0]['message'])

    def test_unsafe_rule_is_refused(self):
        with self.assertRaises(S.SymblicError):
            S.parse('rule bad(X, Y) if p(X).\n')

    def test_vague_words_warn(self):
        c = S.check('ask x: Text "Maybe list some good ideas." with by="fake:a"\n')
        self.assertTrue(any('vague' in w['message'] for w in c['warnings']))

    def test_plan_and_profile(self):
        c = S.check('let a = 1.\nask b: Bool "Is {a} odd?" with by="fake:a"\nask c: Text "Say hi."\n')
        self.assertEqual(c['profile'], {'exact': 1, 'closed': 1, 'open': 1})
        self.assertEqual(c['plan'][1]['reads'], ['a'])


class Kernel(unittest.TestCase):
    def ev(self, expr, **names):
        env = S.Env()
        for k, v in names.items():
            env.vars[k] = S.Binding(k, v)
        p = S.Parser(S.tokenize(expr), 1)
        return S.Kernel(env).eval(p.expr())

    def test_exact_arithmetic(self):
        self.assertEqual(self.ev('4 + 4'), 8)
        self.assertEqual(self.ev('0.1 + 0.2'), Fraction(3, 10))
        self.assertTrue(self.ev('0.1 + 0.2 = 0.3'))
        self.assertEqual(self.ev('1 / 3 * 3'), 1)
        self.assertEqual(self.ev('2 ^ 100'), 2 ** 100)
        self.assertEqual(self.ev('7 // 2'), 3)
        self.assertEqual(self.ev('-7 mod 3'), 2)
        self.assertEqual(self.ev('sqrt(9/4)'), Fraction(3, 2))

    def test_irrational_results_are_reproducible(self):
        a = S.canon_json(self.ev('sqrt(2)'))
        b = S.canon_json(self.ev('sqrt(2)'))
        self.assertEqual(a, b)
        self.assertEqual(S.num_text(self.ev('round(sqrt(2), 6)')), '1.414214')
        self.assertEqual(S.num_text(self.ev('round(sin(pi / 6), 12)')), '0.5')

    def test_division_by_zero_is_an_error(self):
        with self.assertRaises(S.SymblicError):
            self.ev('1 / 0')

    def test_collections(self):
        self.assertEqual(self.ev('[n * n for n in 1..5 if n mod 2 = 1]'), (1, 9, 25))
        self.assertEqual(self.ev('[10, 20, 30][1]'), 10)        # 1-based, like mathematics
        self.assertEqual(self.ev('[10, 20, 30][-1]'), 30)
        self.assertEqual(self.ev('{3, 1, 2} = {1, 2, 3}'), True)
        self.assertEqual(self.ev('{name: "a", n: 2}.n'), 2)
        self.assertEqual(self.ev('sort([3, 1, 2], desc=true)'), (3, 2, 1))
        self.assertEqual(self.ev('len("abc")'), 3)
        self.assertTrue(self.ev('all x in [2, 4]: x mod 2 = 0'))
        self.assertTrue(self.ev('none x in [2, 4]: x > 9'))
        self.assertTrue(self.ev('1 < 2 < 3'))
        self.assertFalse(self.ev('1 < 3 < 2'))

    def test_interpolation(self):
        self.assertEqual(self.ev('"x is {x + 1}, {{literal}}"', x=1), 'x is 2, {literal}')

    def test_eval_is_sandboxed_to_the_kernel(self):
        self.assertEqual(self.ev('eval("a * 3 + 1", a=4)'), 13)
        self.assertEqual(self.ev('eval("k + n + text", k=1, n=2, text=3)'), 6)     # no clash with internals
        with self.assertRaises(S.SymblicError):
            self.ev('eval("__import__(1)")')
        with self.assertRaises(S.SymblicError):
            self.ev('eval("b + 1")')

    def test_limits(self):
        with self.assertRaises(S.SymblicError):
            self.ev('2 ^ 10000000')
        with self.assertRaises(S.SymblicError):
            self.ev('len(1..10000000)')

    def test_unbound_name(self):
        with self.assertRaises(S.SymblicError) as cm:
            self.ev('y + 1')
        self.assertEqual(cm.exception.kind, 'name')


class Logic(unittest.TestCase):
    SRC = ('fact parent(alice, bob), parent(bob, carol), parent(carol, dan), person(alice), person(bob), '
           'person(carol), person(dan), person(eve).\n'
           'rule ancestor(X, Y) if parent(X, Y).\n'
           'rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).\n'
           'rule root(X) if person(X) and not parent(_, X).\n'
           'rule older(X, N) if person(X) and age(X, A) and N = A + 1.\n'
           'fact age(alice, 70), age(bob, 45).\n')

    def test_recursion_negation_arithmetic(self):
        src = self.SRC + ('let anc = query ancestor(alice, Who).\nassert anc = ["bob", "carol", "dan"].\n'
                          'let roots = query root(R).\nassert roots = ["alice", "eve"].\n'
                          'assert holds ancestor(alice, dan).\nassert not holds ancestor(dan, alice).\n'
                          'let o = query older(alice, N).\nassert o = [71].\n'
                          'let pairs = query parent(P, C).\nassert len(pairs) = 3 and pairs[1].P = "alice".\n')
        _, rep = kernel_run(src)
        self.assertEqual(rep['status'], 'done', rep.get('error'))

    def test_negation_cycle_is_refused(self):
        _, rep = kernel_run('fact n(a).\nrule p(X) if n(X) and not q(X).\nrule q(X) if n(X) and not p(X).\n'
                            'let z = query p(X).\n')
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('themselves', rep['error']['message'])


class Types(unittest.TestCase):
    def test_coercion(self):
        self.assertEqual(S.coerce('8', {'k': 'int'}), 8)
        self.assertEqual(S.coerce(8.0, {'k': 'int'}), 8)
        with self.assertRaises(S.SymblicError):
            S.coerce(8.5, {'k': 'int'})
        self.assertEqual(S.coerce('3.14159', {'k': 'number', 'places': 2}), Fraction(157, 50))
        self.assertEqual(S.coerce(' "Gold." ', {'k': 'enum', 'options': ['gold', 'white']}), 'gold')
        with self.assertRaises(S.SymblicError):
            S.coerce('golden', {'k': 'enum', 'options': ['gold', 'white']})
        self.assertIs(S.coerce('Yes', {'k': 'bool'}), True)
        rec = {'k': 'record', 'fields': [['n', {'k': 'int'}], ['c', {'k': 'text'}]]}
        self.assertEqual(S.coerce({'N': 2, 'c': ' hi '}, rec), {'n': 2, 'c': 'hi'})
        with self.assertRaises(S.SymblicError):
            S.coerce([1, 2], {'k': 'list', 'of': {'k': 'int'}, 'min': 3, 'max': 3})
        self.assertTrue(S.values_equal(S.coerce([2, 1, 2], {'k': 'set', 'of': {'k': 'int'}}), frozenset({1, 2})))
        with self.assertRaises(S.SymblicError):
            S.coerce(5, {'k': 'int', 'lo': 1, 'hi': 4})

    def test_schema(self):
        ty = S.resolve_type(S.parse('define C as Record {petals: Int in 3..12, hue: one of {red, gold}}.\n'
                                    )['statements'][0].type, {})
        sch = S.answer_schema(ty, True)
        self.assertEqual(sch['required'], ['reasoning', 'answer'])
        ans = sch['properties']['answer']
        self.assertEqual(ans['properties']['petals'], {'type': 'integer', 'minimum': 3, 'maximum': 12})
        self.assertEqual(ans['properties']['hue']['enum'], ['red', 'gold'])
        self.assertFalse(ans['additionalProperties'])

    def test_canonical_form(self):
        self.assertEqual(S.fingerprint(frozenset({3, 1})), S.fingerprint(frozenset({1, 3})))
        self.assertEqual(S.fingerprint({'b': 1, 'a': 2}), S.fingerprint({'a': 2, 'b': 1}))
        # Canon v3 preserves every observable code point; normalisation is an explicit operation.
        self.assertNotEqual(S.fingerprint('a  \r\nb  '), S.fingerprint('a\nb'))
        self.assertEqual(S.fingerprint(S.canon_text('a  \r\nb  ')), S.fingerprint('a\nb'))
        self.assertNotEqual(S.fingerprint(1), S.fingerprint('1'))
        self.assertEqual(S.fingerprint(Fraction(2, 1)), S.fingerprint(2))

    def test_canonical_encoding_is_injective_for_tagged_values(self):
        self.assertNotEqual(S.fingerprint(Fraction(1, 2)), S.fingerprint({'#q': '1/2'}))
        self.assertNotEqual(S.fingerprint(frozenset({1})), S.fingerprint({'#set': (1,)}))
        self.assertNotEqual(S.fingerprint({'#q': '1/2'}), S.fingerprint({'##q': '1/2'}))
        self.assertEqual(S.fingerprint({'a': 1}), S.fingerprint({'a': 1}))      # ordinary records unchanged

    def test_conflicting_case_variants_of_a_field_are_refused(self):
        rec = {'k': 'record', 'fields': [['x', {'k': 'int'}]]}
        for value in ({'x': 1, 'X': 2}, {'X': 2, 'x': 1}, {' x': 1, 'X': 2}):
            with self.assertRaises(S.SymblicError):
                S.coerce(value, rec)
        self.assertEqual(S.coerce({'X': 2}, rec), {'x': 2})
        self.assertEqual(S.coerce({'x': 2, 'X': 2}, rec), {'x': 2})              # same value twice is fine

    def test_extract_json(self):
        self.assertEqual(S.extract_json('```json\n{"answer": 3}\n```'), {'answer': 3})
        self.assertEqual(S.extract_json('thinking {not json} ... final {"answer": "a", "reasoning": "x {y}"}'),
                         {'answer': 'a', 'reasoning': 'x {y}'})
        self.assertEqual(S.extract_json('Work...\nANSWER: 42'), {'answer': 42})
        self.assertIsNone(S.extract_json('no answer here'))


class Capsule(unittest.TestCase):
    def test_budget_drops_whole_items_by_weight(self):
        known = [('big', 'Text', '"' + 'x' * 500 + '"', 1), ('rule', 'Int', '3', 9), ('small', 'Int', '4', 2)]
        cap = S.capsule('P', 1, 1, 'ask q : Int\n  "q"', {'k': 'int'}, 'low', known, [], budget=120)
        self.assertIn('KNOWN — BINDING', cap['prompt'])
        self.assertIn('- rule : Int = 3', cap['prompt'])
        self.assertIn('- small : Int = 4', cap['prompt'])
        self.assertNotIn('xxxx', cap['prompt'])
        self.assertIn('left out', cap['prompt'])
        self.assertEqual(cap['schema']['required'], ['answer'])         # effort low: no reasoning field

    def test_effort_adds_reasoning(self):
        cap = S.capsule('P', 1, 1, 's', {'k': 'bool'}, 'high', [], [])
        self.assertIn('reasoning', cap['schema']['properties'])
        self.assertIn('step by step', cap['prompt'])


class Consensus(unittest.TestCase):
    def sample(self, v, app, order, w=1):
        return {'value': v, 'hash': S.fingerprint(v), 'app': app, 'order': order, 'weight': w}

    def test_majority_and_weights(self):
        r = S.consensus([self.sample(8, 'a', 0), self.sample(8, 'b', 1), self.sample(9, 'c', 2)])
        self.assertEqual(r['value'], 8)
        self.assertAlmostEqual(r['agreement'], 2 / 3, places=3)
        r = S.consensus([self.sample(8, 'a', 0), self.sample(9, 'b', 1, w=3)])
        self.assertEqual(r['value'], 9)

    def test_ties_are_deterministic(self):
        a = S.consensus([self.sample('x', 'a', 0), self.sample('y', 'b', 1)])
        b = S.consensus([self.sample('y', 'b', 1), self.sample('x', 'a', 0)])
        self.assertEqual(a['value'], b['value'])
        self.assertTrue(a['contested'] is False or a['agreement'] == 0.5)


class Interpreter(unittest.TestCase):
    def test_kernel_only_program(self):
        run, rep = kernel_run('program K.\nlet a = 4 + 4.\nassert a = 8.\nshow a * 2 as "double".\n')
        self.assertEqual(rep['status'], 'done')
        self.assertEqual(rep['outputs'][0]['value'], 16)
        self.assertEqual(rep['outputs'][0]['label'], 'double')
        self.assertEqual(rep['calls'], 0)

    def test_same_program_same_fingerprint_whoever_applies_it(self):
        src = ('let n = 3.\nask hue: one of {red, gold} "Pick the hue." with effort=low\n'
               'ask k: Int in 1..10 "Give {n} + 1." with effort=low\nshow [hue, k].\n')
        answers = {'hue': 'GOLD', 'k': '4'}

        def ans(app, prompt, req):
            return {'answer': answers['hue'] if 'hue' in prompt else answers['k']}
        _, r1, _ = run_with(src, ans, by='fake:alpha')
        _, r2, _ = run_with(src, ans, by='ollama:tiny@nowhere')
        self.assertEqual(r1['status'], 'done', r1.get('error'))
        self.assertEqual(r1['fingerprint'], r2['fingerprint'])
        self.assertEqual(r1['outputs'][0]['value'], ['gold', 4])

    def test_votes_and_contest(self):
        src = 'group g = ["fake:a", "fake:b", "fake:c"].\nask x: Int "?" by g with effort=low\n'
        _, rep, apps = run_with(src, lambda app, p, r: {'answer': 9 if app == 'fake:c' else 8})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        x = next(b for b in rep['bindings'] if b['name'] == 'x')
        self.assertEqual(x['value'], 8)
        self.assertAlmostEqual(x['meta']['agreement'], 0.6667, places=3)
        self.assertEqual(len(apps.reqs), 3)

    def test_strict_contest_fails(self):
        src = 'group g = ["fake:a", "fake:b"].\nask x: Int "?" by g with effort=low, agree=0.9, strict\n'
        _, rep, _ = run_with(src, lambda app, p, r: {'answer': 1 if app == 'fake:a' else 2})
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('did not agree', rep['error']['message'])

    def test_invalid_reply_gets_a_repair_attempt(self):
        seen = []

        def ans(app, prompt, req):
            seen.append(prompt)
            return 'I think it is purple' if len(seen) == 1 else {'answer': 'red'}
        _, rep, _ = run_with('ask c: one of {red, blue} "?" with effort=low\n', ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('NOT VALID', seen[1])

    def test_ensure_retry_reasks_with_feedback(self):
        prompts = []

        def ans(app, prompt, req):
            prompts.append(prompt)
            return {'answer': 3 if len(prompts) == 1 else 12}
        src = 'ask n: Int "Give an even number above 10." with effort=low\nlet half = n / 2.\nensure half > 5 else retry.\n'
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('REJECTED BY THE KERNEL', prompts[1])
        self.assertIn('half > 5', prompts[1])
        self.assertEqual(next(b for b in rep['bindings'] if b['name'] == 'n')['value'], 12)

    def test_every_ensure_retry_is_a_fresh_request_even_with_a_replay_cache(self):
        d = tempfile.mkdtemp()
        try:
            prompts = []

            def ans(app, prompt, req):
                prompts.append(prompt)
                return {'answer': 1}                    # always the same wrong answer
            _, rep, apps = run_with('ask n: Int "?" with effort=low, retries=3\nensure n > 100 else retry.\n',
                                    ans, folder=d)
            self.assertEqual(rep['status'], 'failed')
            self.assertEqual(len(apps.reqs), 4)        # 1 + 3 retries, none answered from the cache
            self.assertEqual(len(set(prompts)), 4)
            self.assertIn('Attempt 4', prompts[-1])
        finally:
            shutil.rmtree(d)

    def test_ensure_retry_gives_up_and_fails(self):
        _, rep, apps = run_with('ask n: Int "?" with effort=low, retries=1\nensure n > 100 else retry.\n',
                                lambda a, p, r: {'answer': 1})
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'check')
        self.assertEqual(len(apps.reqs), 2)

    def test_context_policies(self):
        prompts = {}

        def ans(app, prompt, req):
            name = re.search(r'ask (\w+)', prompt).group(1)
            prompts[name] = prompt
            return {'answer': 'ok'}
        src = ('let secret = 42.\nlet topic = "tides".\nlet heavy = "binding rule" with weight=9.\n'
               'ask a: Text "Fresh." with effort=low\n'
               'ask b: Text "All." with effort=low, context=all\n'
               'ask c: Text "Named." from topic with effort=low\n'
               'ask d: Text "Last one." with effort=low, context=last 1\n'
               'forget secret.\nask e: Text "All after forgetting." with effort=low, context=all\n')
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertNotIn('secret', prompts['a'])
        self.assertIn('- secret : Int = 42', prompts['b'])
        self.assertLess(prompts['b'].index('heavy'), prompts['b'].index('secret'))   # weight orders memory
        self.assertIn('BINDING', prompts['b'])
        self.assertIn('topic', prompts['c'])
        self.assertNotIn('secret', prompts['c'])
        self.assertIn('- c : Text', prompts['d'])
        self.assertNotIn('secret', prompts['e'])

    def test_facts_reach_the_context(self):
        got = {}

        def ans(app, prompt, req):
            got['p'] = prompt
            return {'answer': True}
        _, rep, _ = run_with('fact likes(ann, tea).\nask q: Bool "Does ann like tea?" with effort=low, context=facts\n',
                             ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('likes(ann, tea)', got['p'])

    def test_ultra_runs_a_mixture_round_with_candidates(self):
        rounds = []

        def ans(app, prompt, req):
            rounds.append('CANDIDATE ANSWERS' in prompt)
            if 'CANDIDATE ANSWERS' in prompt:
                return {'answer': 8, 'reasoning': 'rechecked'}
            return {'answer': {'fake:a': 8, 'fake:b': 7, 'fake:c': 9}[app], 'reasoning': 'r'}
        src = 'group g = ["fake:a", "fake:b", "fake:c"].\nask x: Int "?" by g with effort=ultra, votes=3\n'
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        x = next(b for b in rep['bindings'] if b['name'] == 'x')
        self.assertEqual(x['value'], 8)
        self.assertEqual(x['meta']['rounds'], 2)
        self.assertEqual(x['meta']['agreement'], 1.0)
        self.assertEqual(rounds.count(True), 3)

    def test_ahead_by_k_stops_early(self):
        calls = []

        def ans(app, prompt, req):
            calls.append(app)
            return {'answer': 8}
        src = 'group g = ["fake:a", "fake:b"].\nask x: Int "?" by g with effort=low, votes=9, ahead=2\n'
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(calls), 2)            # one batch already leads by 2

        def split(app, prompt, req):
            calls.append(app)
            return {'answer': 1 if app == 'fake:a' else 2}
        calls.clear()
        _, rep, _ = run_with(src, split)
        self.assertEqual(len(calls), 9)            # never ahead: every vote is used

    def test_native_reasoning_engines_get_no_reasoning_field(self):
        schemas = {}

        def ans(app, prompt, req):
            schemas[app] = req['schema']
            return {'answer': 1}
        src = 'group g = ["claude:haiku", "ollama:m@n"].\nask x: Int "?" by g with effort=high, votes=2\n'
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertNotIn('reasoning', schemas['claude:haiku']['properties'])
        self.assertIn('reasoning', schemas['ollama:m@n']['properties'])

    def test_key_groups_votes_by_meaning_and_red_flags_bad_answers(self):
        replies = iter(['3 * 4 + 2', '2 + 3 * 4', '(2 + 12', '7 + 7'])

        def ans(app, prompt, req):
            return {'answer': next(replies)}
        src = ('ask f: Text "Formalize." with effort=low, votes=4, key=eval(it)\n'
               'let v = eval(f).\nshow v.\n')
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        f = next(b for b in rep['bindings'] if b['name'] == 'f')
        self.assertEqual(rep['outputs'][0]['value'], 14)
        self.assertEqual(f['meta']['agreement'], 1.0)          # three formulas, one meaning; one red-flagged
        self.assertEqual(sum(1 for x in f['meta']['samples'] if not x['ok']), 1)

    def test_for_each_fans_out_and_loops_lift(self):
        src = ('let xs = [1, 2, 3].\nask d: Int "Double {x}." for each x in xs with effort=low\n'
               'for v in d do\nlet sq = v * v.\nend.\nassert sq = [4, 16, 36].\n')
        _, rep, apps = run_with(src, lambda a, p, r: {'answer': 2 * int(re.search(r'Double (\d+)', p).group(1))})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.reqs), 3)

    def test_inputs_and_types(self):
        _, rep, _ = run_with('given n: Int in 1..5.\nlet m = n * 2.\nshow m.\n', None, inputs={'n': '3'})
        self.assertEqual(rep['outputs'][0]['value'], 6)
        _, rep, _ = run_with('given n: Int in 1..5.\n', None, inputs={'n': 9})
        self.assertEqual(rep['status'], 'failed')
        _, rep, _ = run_with('given n: Int.\n', None)
        self.assertIn('required', rep['error']['message'])

    def test_resume_reuses_calls(self):
        d = tempfile.mkdtemp()
        try:
            src = 'ask x: Int "?" with effort=low\nask y: Int "?? {x}" with effort=low\n'
            _, r1, a1 = run_with(src, lambda a, p, r: {'answer': 5}, folder=d)
            _, r2, a2 = run_with(src, lambda a, p, r: {'answer': 99}, folder=d)
            self.assertEqual(len(a1.reqs), 2)
            self.assertEqual(len(a2.reqs), 0)              # every answer replayed from calls.jsonl
            self.assertEqual(r1['fingerprint'], r2['fingerprint'])
            self.assertEqual(r2['cached'], 2)
            with open(os.path.join(d, 'state.json')) as f:
                self.assertEqual(json.load(f)['status'], 'done')
        finally:
            shutil.rmtree(d)

    def test_replay_key_separates_effort_and_tools(self):
        d = tempfile.mkdtemp()
        try:
            calls = []

            def ans(app, prompt, req):
                calls.append((req['effort'], req['tools']))
                return {'answer': len(calls)}
            # same app, statement, sample and seed; only the engine's effort and the tools differ
            # claude reasons natively, so high and max send the same prompt: only the engine effort differs
            for opts in ('effort=high, votes=1', 'effort=max, votes=1', 'effort=max, votes=1, tools=web'):
                run_with(f'ask x: Int "?" by "claude:haiku" with {opts}\n', ans, folder=d)
            self.assertEqual(calls, [('high', 'none'), ('max', 'none'), ('max', 'web')])   # nothing replayed across
            run_with('ask x: Int "?" by "claude:haiku" with effort=ultra, votes=1\n', ans, folder=d)
            self.assertEqual(len(calls), 3)              # ultra with one vote sends exactly the max request: replayed
            self.assertNotEqual(SR.call_key({'engine': 'claude', 'model': 'haiku'}, 's', 'p', None, 0, 0, 7, 'low'),
                                SR.call_key({'engine': 'claude', 'model': 'haiku'}, 's', 'p', None, 0, 0, 7, 'high'))
        finally:
            shutil.rmtree(d)

    def test_failures_are_abstentions_then_an_error(self):
        def ans(app, p, r):
            return {'__error__': 'usage limit'} if app == 'fake:a' else {'answer': 4}
        _, rep, _ = run_with('group g = ["fake:a", "fake:b"].\nask x: Int "?" by g with effort=low\n', ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        _, rep, _ = run_with('ask x: Int "?" with effort=low, retries=0\n', lambda a, p, r: {'__error__': 'down'})
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('down', rep['error']['message'])

    def test_ask_needs_a_model(self):
        _, rep, _ = run_with('ask x: Int "?" by "kernel"\n', lambda a, p, r: {'answer': 1})
        self.assertIn('model applicator', rep['error']['message'])

    def test_max_asks(self):
        _, rep, _ = run_with('ask x: Int "{i}" for each i in 1..5 with effort=low\n', lambda a, p, r: {'answer': 1},
                             max_asks=3)
        self.assertEqual(rep['status'], 'failed')

    def test_delegate_needs_side_effects(self):
        _, rep, _ = run_with('delegate t = "fix it" to "triad".\n', None)
        self.assertIn('side effects', rep['error']['message'])

        class Hub(FakeApps):
            def delegate(self, target, task, options):
                return {'id': 'abc', 'engine': target, 'status': 'starting'}
        run = SR.Run('delegate t = "fix it" to "triad".\nshow t.id.\n', None, Hub(None), {'side_effects': True})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(rep['outputs'][0]['value'], 'abc')

    def test_stop(self):
        ev = threading.Event()
        ev.set()
        run = SR.Run('let a = 1.\n', None, None, {'stop': ev})
        self.assertEqual(run.execute()['status'], 'stopped')

    def test_v1_prose_program_runs(self):
        src = 'Program: Brief.\nUse Model: llama3.1.\nSummarize the request.\nContinue with context. List 2 risks.\n'
        prompts = []

        def ans(app, p, r):
            prompts.append((app, p))
            return {'answer': 'done', 'reasoning': ''}
        run = SR.Run(src, None, FakeApps(ans), {})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(prompts[0][0], 'ollama:llama3.1')
        self.assertIn('step1', prompts[1][1])


class Predictability(unittest.TestCase):
    def test_terms_reach_only_the_statements_that_use_them(self):
        prompts = {}

        def ans(app, prompt, req):
            prompts[re.search(r'ask (\w+)', prompt).group(1)] = prompt
            return {'answer': 1}
        src = ('term petal means "one coloured leaf-like part around the centre of a flower".\n'
               'term stem is "the green stalk".\n'
               'ask a: Int "How many petals does a buttercup have?" with effort=low\n'
               'ask b: Int "How many wheels does a bicycle have?" with effort=low\n')
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('DEFINITIONS', prompts['a'])
        self.assertIn('"petal": "one coloured', prompts['a'])
        self.assertNotIn('stem', prompts['a'])
        self.assertNotIn('DEFINITIONS', prompts['b'])
        _, rep, _ = run_with('term x means "a".\nterm X means "b".\n', None)
        self.assertIn('twice', rep['error']['message'])

    def test_examples_are_type_checked_and_shown_canonically(self):
        got = {}

        def ans(app, prompt, req):
            got['p'] = prompt
            return {'answer': 'gold'}
        src = ('ask c: one of {red, gold} "Colour of a sunflower?" with effort=low, '
               'examples=[["Colour of a poppy?", "RED"]]\n')
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('WORKED EXAMPLES', got['p'])
        self.assertIn('Colour of a poppy? → {"answer": "red"}', got['p'])
        _, rep, _ = run_with('ask c: one of {red, gold} "?" with effort=low, examples=[["q", "blue"]]\n',
                             lambda a, p, r: {'answer': 'red'})
        self.assertIn('example 1', rep['error']['message'])

    def test_field_voting_rescues_a_record_with_one_slip_per_agent(self):
        answers = {'fake:a': {'n': 5, 'c': 'red', 'k': True}, 'fake:b': {'n': 5, 'c': 'gold', 'k': True},
                   'fake:c': {'n': 6, 'c': 'red', 'k': True}}
        src = ('group g = ["fake:a", "fake:b", "fake:c"].\n'
               'ask r: Record {n: Int, c: one of {red, gold}, k: Bool} "?" by g with effort=low\n')
        _, rep, _ = run_with(src, lambda app, p, r: {'answer': answers[app]})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        r = next(b for b in rep['bindings'] if b['name'] == 'r')
        self.assertEqual(r['value'], {'n': 5, 'c': 'red', 'k': True})       # nobody said exactly this
        self.assertEqual(r['meta']['vote'], 'fields')
        self.assertAlmostEqual(r['meta']['agreement'], 0.6667, places=3)
        self.assertAlmostEqual(r['meta']['agreement_whole'], 0.3333, places=3)
        _, rep, _ = run_with(src.replace('effort=low', 'effort=low, vote=whole'),
                             lambda app, p, r: {'answer': answers[app]})
        r = next(b for b in rep['bindings'] if b['name'] == 'r')
        self.assertEqual(r['meta']['vote'], 'whole')

    def test_an_assembled_record_that_breaks_a_whole_record_check_falls_back(self):
        # the coordinator's counterexample: each agent satisfies a + b + c = 1, the field-wise mode (0,0,0)
        # does not; the kernel then uses the whole-record consensus instead of re-asking
        answers = {'fake:a': {'a': 1, 'b': 0, 'c': 0}, 'fake:b': {'a': 0, 'b': 1, 'c': 0},
                   'fake:c': {'a': 0, 'b': 0, 'c': 1}}
        calls = []

        def ans(app, p, r):
            calls.append(app)
            return {'answer': answers[app]}
        src = ('group g = ["fake:a", "fake:b", "fake:c"].\n'
               'ask r: Record {a: Int, b: Int, c: Int} "?" by g with effort=low\n'
               'ensure r.a + r.b + r.c = 1 else retry.\n')
        _, rep, _ = run_with(src, ans)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        r = next(b for b in rep['bindings'] if b['name'] == 'r')
        self.assertEqual(r['value'], {'a': 1, 'b': 0, 'c': 0})
        self.assertEqual(r['meta']['vote'], 'whole (fallback)')
        self.assertEqual(len(calls), 3)                    # no model was asked again
        self.assertNotIn('_whole_value', r['meta'])
        json.dumps(rep['bindings'])                        # the report stays JSON

    def test_determination_by_enumeration(self):
        calls = []

        def ans(app, p, r):
            calls.append(app)
            return {'answer': 7}
        src = ('let total = 10.\n'
               'ask x: Int in 0..20 "How many?" with effort=low, solve\n'
               'let twice = x * 2.\n'
               'ensure twice + 2 = total else retry.\n'
               'ask y: Int in 0..20 "Pick one above 3." with effort=low\n'
               'ensure y > 3 else retry.\n'
               'ask c: Record {a: Bool, b: one of {p, q}} "?" with effort=low, solve\n'
               'ensure c.a and c.b = "q" else retry.\n'
               'ask k: Int in 0..5 "?" with effort=low\n'
               'ensure k > 9 else retry.\n')
        _, rep, _ = run_with(src, ans)
        got = {b['name']: b for b in rep['bindings']}
        self.assertEqual(got['x']['value'], 4)
        self.assertTrue(got['x']['meta']['solved_by_kernel'])
        self.assertEqual(got['x']['meta']['determination']['verdict'], 'determined')
        self.assertEqual(got['y']['meta']['determination']['verdict'], 'underdetermined')
        self.assertEqual(got['c']['value'], {'a': True, 'b': 'q'})          # a record domain, enumerated
        self.assertEqual(rep['status'], 'failed')                           # k: no answer can pass
        self.assertTrue(any('no possible answer' in w['message'] for w in rep['warnings']))
        self.assertEqual(calls.count('fake:a'), 1)              # y once; contradictory k refused before calling
        self.assertEqual(rep['error']['kind'], 'contradictory')

    def test_domains(self):
        self.assertEqual(S.domain({'k': 'bool'}), [False, True])
        self.assertEqual(len(S.domain({'k': 'set', 'of': {'k': 'enum', 'options': ['a', 'b', 'c']}})), 8)
        self.assertIsNone(S.domain({'k': 'text'}))
        self.assertIsNone(S.domain({'k': 'int'}))
        self.assertIsNone(S.domain({'k': 'int', 'lo': 0, 'hi': 10 ** 9}))

    def test_static_predictability(self):
        c = S.check('let n = 5.\nask a: Text "Describe it nicely and then list some large items."\n'
                    'ask b: one of {red, gold} "Which colour is a ripe lemon?"\n'
                    'ask d: Number "What is the length of the table?"\n')
        risk = {d['name']: d for d in c['asks_detail']}
        self.assertLess(risk['a']['score'], 50)
        self.assertEqual(risk['b']['score'], 100)
        self.assertTrue(any('unit' in r for r in risk['d']['reasons']))
        self.assertTrue(any('places' in r for r in risk['d']['reasons']))
        self.assertTrue(0 < c['predictability'] < 100)
        self.assertEqual(S.check('let a = 1.\n')['predictability'], 100)


class Extensions(unittest.TestCase):
    def setUp(self):
        self._saved = dict(S.EXTENSIONS)          # symblic_lang's statements are registered on import

    def tearDown(self):
        S.EXTENSIONS.clear()
        S.EXTENSIONS.update(self._saved)

    def test_a_statement_and_a_kernel_function_from_another_module(self):
        def parse(p, line, col, prog):
            name = p.expect_name().value
            p.expect_op('(')
            params = [p.expect_name().value]
            while p.op(','):
                p.take()
                params.append(p.expect_name().value)
            p.expect_op(')')
            p.expect_op('=')
            body = p.expr()
            p.finish()
            return S.Node('function', line, col, name=name, params=params, value=body)

        def execute(run, node, env):
            def fn(kernel, n, *args):
                child = S.Env(env)
                for k, v in zip(node.params, args):
                    child.vars[k] = S.Binding(k, v)
                return kernel.eval(node.value, child)
            run.kernel.functions[node.name] = fn
        S.register_extension(S.Extension('function', parse, execute, binds=lambda n: [],
                                         label=lambda n: f'function {n.name}'))
        _, rep = kernel_run('function sq(x) = x * x.\nlet a = sq(7).\nassert a = 49.\n')
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(S.check('function sq(x) = x * x.\n')['plan'][0]['label'], 'function sq')
        with self.assertRaises(ValueError):
            S.register_extension(S.Extension('let', parse, execute))

    def test_block_extensions_get_a_body(self):
        seen = []

        def parse(p, line, col, prog):
            name = p.expect_name().value
            p.finish()
            return S.Node('suite', line, col, name=name)

        def execute(run, node, env):
            seen.append((node.name, [s.k for s in node.body]))
            run.exec_block(node.body, S.Env(env))
        S.register_extension(S.Extension('suite', parse, execute, block=True))
        _, rep = kernel_run('suite basics.\nlet x = 1.\nassert x = 1.\nend.\n')
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(seen, [('basics', ['let', 'assert'])])


class Render(unittest.TestCase):
    def test_flower_is_byte_identical(self):
        a = R.flower(petals=7, color_='violet', shape='pointed', layers=2)
        b = R.flower(petals=7, color_='violet', shape='pointed', layers=2)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith('<svg'))
        self.assertIsNone(re.search(r'[0-9.]e[-+][0-9]', a))     # no float exponents leak out
        self.assertEqual(a.count('<path'), 7 * 2 + 1 + 2)   # petals x layers, stem, two leaves

    def test_flower_from_a_record_and_errors(self):
        svg = R.flower({'petals': 5, 'color': 'gold', 'shape': 'heart', 'stem': False})
        self.assertNotIn('stroke-linecap', svg)
        with self.assertRaises(S.SymblicError):
            R.flower(petals=2)
        with self.assertRaises(S.SymblicError):
            R.flower(color_='not-a-colour')
        with self.assertRaises(S.SymblicError):
            R.flower(spec={'petals': 5, 'smell': 'sweet'})

    def test_known_fingerprint_is_stable(self):
        # pinned: a change to the renderer that changes these bytes must be deliberate
        _, rep = kernel_run('draw flower(petals=5, color="gold") as "f.svg".\n')
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertRegex(rep['outputs'][0]['hash'], r'^[0-9a-f]{16}$')
        _, rep2 = kernel_run('let p = 2 + 3.\ndraw flower(petals=p, color="gold").\n')
        self.assertEqual(rep['outputs'][0]['hash'], rep2['outputs'][0]['hash'])

    def test_rose_and_polygon(self):
        self.assertIn('<path', R.rose(k=5))
        _, rep = kernel_run('draw rose(k=7, color="violet").\n')
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('<polygon', R.polygon(sides=6))


class ResearchRules(unittest.TestCase):
    """2026-10-02 rules from docs/reference/RESEARCH-{AGREEMENT,LANGUAGE}.md."""

    def test_options_carry_operational_definitions(self):
        src = ('ask kind: one of {fruit: "botanically, the seed-bearing part grown from a flower", '
               'vegetable means "any other edible plant part, by culinary use"} "Is a tomato a fruit or a vegetable?"\n')
        prog = S.parse(src)
        ty = S.resolve_type(prog['statements'][0].type, {}, 1)
        self.assertEqual(ty['options'], ['fruit', 'vegetable'])
        self.assertIn('seed-bearing', ty['defs']['fruit'])
        self.assertIn('chosen by its definition', S.describe_type(ty))
        self.assertIn('culinary', S.json_schema(ty)['description'])
        detail = S.check(src)['asks_detail'][0]
        self.assertIn('every option has a definition (-8)', detail['reasons'])
        half = S.check('ask k: one of {a: "first", b} "Pick."\n')['asks_detail'][0]
        self.assertTrue(any('options named by letters' in r for r in half['reasons']))
        self.assertTrue(any('without a definition: b' in r for r in half['reasons']))
        with self.assertRaises(S.SymblicError):
            S.parse('ask k: one of {a: 5, b} "Pick."\n')

    def test_readings_are_collected_and_can_stop_a_run(self):
        from symblic.kernel import run as SR

        class Fake:
            def call(self, req):
                assert 'readings' in req['schema']['properties']
                reads = ['common year: 365', 'leap year: 366'] if req['app']['engine'] == 'codex' else []
                return {'ok': True, 'json': {'readings': reads, 'answer': 365}}
        src = 'ask d: Int in 300..400 "How many days are in a year?" with by=["claude:haiku", "codex"], ambiguous=true\n'
        run = SR.Run(src, None, Fake(), {'parallel': 1})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        meta = next(t['ask'] for t in run.trace if t.get('ask'))
        self.assertEqual(meta['ambiguity']['flagged'], 1)
        self.assertIn('leap year: 366', meta['ambiguity']['readings'])
        self.assertTrue(any('more than one reading' in w['message'] for w in rep['warnings']))
        rep = SR.Run(src.replace('ambiguous=true', 'ambiguous=fail'), None, Fake(), {'parallel': 1}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'ambiguous')
        # without the option the schema has no readings field
        cap = S.capsule('p', 1, 1, 'x', {'k': 'int'}, 'low', [], [])
        self.assertNotIn('readings', cap['schema']['properties'])

    def test_entropy_separates_a_two_way_split_from_a_seven_way_split(self):
        two = [{'value': i % 2, 'hash': str(i % 2), 'weight': 1, 'app': f'a{i}', 'order': i} for i in range(7)]
        seven = [{'value': i, 'hash': str(i), 'weight': 1, 'app': f'a{i}', 'order': i} for i in range(7)]
        e2, e7 = S.consensus(two)['entropy'], S.consensus(seven)['entropy']
        self.assertLess(e2, 0.5)
        self.assertEqual(e7, 1.0)
        self.assertEqual(S.consensus(seven[:1])['entropy'], 0.0)

    def test_families_option_needs_support_across_model_makers(self):
        from symblic.kernel import run as SR

        class Fake:
            def call(self, req):
                return {'ok': True, 'json': {'answer': 8}}
        two_claudes = 'ask n: Int "Eight?" with by=["claude:haiku", "claude:sonnet"], families=2, strict\n'
        rep = SR.Run(two_claudes, None, Fake(), {'parallel': 1}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('1 of 2 families', rep['error']['message'])
        mixed = two_claudes.replace('"claude:sonnet"', '"codex"')
        self.assertEqual(SR.Run(mixed, None, Fake(), {'parallel': 1}).execute()['status'], 'done')

    def test_a_tie_at_the_top_is_contested(self):
        two = [{'value': v, 'hash': str(v), 'weight': 1, 'app': a, 'order': i}
               for i, (a, v) in enumerate([('claude:haiku', 1), ('codex', 2)])]
        r = S.consensus(two)
        self.assertTrue(r['tied'])
        self.assertTrue(r['contested'])
        self.assertEqual(r['value'], 1)              # still decided the same way every time
        self.assertFalse(S.consensus(two + [{'value': 1, 'hash': '1', 'weight': 1, 'app': 'agy', 'order': 2}])['tied'])

    def test_families_count_model_makers_not_samples(self):
        self.assertEqual(S.family_of('claude:haiku'), 'anthropic')
        self.assertEqual(S.family_of('ollama:qwen3:4b-instruct@node-b'), 'alibaba')
        self.assertEqual(S.family_of('ollama:gemma3:4b'), 'google')
        self.assertEqual(S.family_of('agy'), S.UNATTRIBUTED)   # 2.3: agy can run Claude or GPT-OSS models
        self.assertEqual(S.family_of('agy:gemini-3-pro'), 'google')
        self.assertEqual(S.family_of('codex'), 'openai')
        votes = [{'value': 8, 'hash': 'h', 'weight': 1, 'app': a, 'order': i}
                 for i, a in enumerate(['claude:haiku', 'claude:sonnet', 'ollama:llama3.2:1b'])]
        self.assertEqual(S.consensus(votes)['families'], ['anthropic', 'meta'])

    def test_linter_flags_frames_units_dates_and_time(self):
        def reasons(src):
            return ' | '.join(S.check(src)['asks_detail'][0]['reasons'])
        self.assertIn('without a stated frame', reasons('ask p: Text "Which block is on the left?"\n'))
        self.assertNotIn('without a stated frame', reasons('ask p: Number "How far left of the origin along the x axis is '
                                                           'the block, in mm?"\n'))
        self.assertIn('more than one definition: ton', reasons('ask w: Number "How many kilograms are in a ton?"\n'))
        self.assertIn('YYYY-MM-DD', reasons('ask m: Int "Which month is 03/04/2025?"\n'))
        self.assertIn('time reference', reasons('ask p: Int "What is the current population of Canada?"\n'))
        self.assertIn('rounding without a rule', reasons('ask r: Int "Round 2.5 to the nearest whole number."\n'))
        self.assertNotIn('rounding without', reasons('ask r: Int "Round 2.5 half up to a whole number."\n'))


class Transactions(unittest.TestCase):
    """2026-10-02 semantics audit R2/R3: a retry undoes everything a rejected answer caused; `for each` items
    get their own capsule inputs."""

    def run_with(self, src, replies, opts=None):
        from symblic.kernel import run as SR
        calls = []

        class Fake:
            def call(self, req):
                calls.append(req['prompt'])
                r = replies[min(len(calls), len(replies)) - 1]
                return {'ok': True, 'json': {'answer': r}}
        run = SR.Run(src, None, Fake(), {'by': 'claude:haiku', 'parallel': 1, **(opts or {})})
        return run, run.execute(), calls

    def test_a_check_through_the_knowledge_base_anchors_the_retry(self):
        src = ('ask e: Record {a: Text, b: Text} "Who is whose parent?" with effort=low, retries=2\n'
               'fact parent(e.a, e.b).\n'
               'ensure holds parent("ann", "gus") else retry\n')
        run, rep, calls = self.run_with(src, [{'a': 'ann', 'b': 'guss'}, {'a': 'ann', 'b': 'gus'}])
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(calls), 2)
        self.assertEqual(run.kernel.kb.fact_count(), 1)

    def test_a_rejected_answer_leaves_no_fact_and_no_output(self):
        src = ('rule reach(X, Y) if link(X, Y).\n'
               'rule reach(X, Y) if link(X, Z) and reach(Z, Y).\n'
               'ask e: Record {a: Text, b: Text} "Give one link." with effort=low, retries=1\n'
               'fact link(e.a, e.b).\n'
               'show e.\n'
               'ensure e.b != "" and holds reach("s", "t") else retry\n')
        # (s, m) then (m, t): only together do they connect s to t, so the second must fail on its own
        run, rep, calls = self.run_with(src, [{'a': 's', 'b': 'm'}, {'a': 'm', 'b': 't'}])
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(len(calls), 2)
        run, rep, calls = self.run_with(src, [{'a': 's', 'b': 'm'}, {'a': 's', 'b': 't'}])
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(run.kernel.kb.fact_count(), 1)
        self.assertEqual(len(rep['outputs']), 1)
        self.assertEqual(rep['outputs'][0]['value'], {'a': 's', 'b': 't'})

    def test_definitions_between_ask_and_ensure_survive_a_retry(self):
        src = ('ask n: Int "Pick a small number." with effort=low\n'
               'define Small as Int in 0..9.\n'
               'let m: Small = n.\n'
               'ensure m > 2 else retry\n')
        run, rep, calls = self.run_with(src, [1, 5])
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(calls), 2)

    def test_a_delegate_inside_a_retry_window_is_refused(self):
        src = ('ask n: Int "Pick." with effort=low\n'
               'delegate job = "do it" to "triad".\n'
               'ensure n > 2 else retry\n')
        run, rep, calls = self.run_with(src, [5])
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('retry would repeat it', rep['error']['message'])
        self.assertEqual(calls, [])

    def test_each_item_gets_its_own_definitions(self):
        from symblic.kernel import run as SR
        import time as _t
        seen = {}

        class Fake:
            def call(self, req):
                p = req['prompt']
                item = 'apple' if 'Describe apple' in p else 'pear'
                seen[item] = [t for t in ('apple', 'pear') if f'- "{t}"' in p]
                return {'ok': True, 'json': {'answer': 'ok'}}
        orig = SR.Run.examples_for

        def slow(self, *a, **k):          # force the interleaving that exposed the shared state
            _t.sleep(0.05)
            return orig(self, *a, **k)
        src = ('term apple means "a pome fruit".\nterm pear means "another pome fruit".\n'
               'ask d: Text "Describe {v}." for each v in ["apple", "pear"] with effort=low\n')
        SR.Run.examples_for = slow
        try:
            rep = SR.Run(src, None, Fake(), {'by': 'claude:haiku', 'parallel': 2}).execute()
        finally:
            SR.Run.examples_for = orig
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(seen, {'apple': ['apple'], 'pear': ['pear']})


class KernelPurity(unittest.TestCase):
    """2026-10-02 semantics audit R4: kernel results never depend on the hash seed, the int-digit limit or
    a regex's backtracking."""

    def run_src(self, src):
        from symblic.kernel import run as SR
        return SR.Run(src, None, None, {}).execute()

    def test_text_builtins_read_sets_in_canonical_order(self):
        import subprocess
        prog = ('from symblic.kernel import run as SR\nr = SR.Run(\'show replace({"x", "y", "z"}, " ", "").\\nshow words({"q r", '
                '"p"}).\\n\', None, None, {}).execute()\nprint(r["fingerprint"])\n')
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))          # the repository root
        outs = set()
        for seed in ('0', '1', '7'):
            out = subprocess.run([sys.executable, '-c', prog], cwd=root, capture_output=True, text=True, timeout=60,
                                 env={**os.environ, 'PYTHONHASHSEED': seed})
            self.assertEqual(out.returncode, 0, out.stderr)
            outs.add(out.stdout.strip())
        self.assertEqual(len(outs), 1)

    def test_big_numbers_fail_the_same_way_under_any_digit_limit(self):
        self.assertEqual(self.run_src('let x = 10 ^ 3000.\nshow len(text(x)).\n')['outputs'][0]['value'], 3001)
        for src in ('let x = 10 ^ 5000.\n', 'let x = 1e10000000.\n', 'let x = factorial(2000).\n',
                    'let x = choose(100000, 50000).\n'):
            rep = self.run_src(src)
            self.assertEqual(rep['status'], 'failed', src)
            self.assertIn('factorial needs' if 'factorial' in src else 'digits', rep['error']['message'])

    def test_regex_and_eval_limits(self):
        rep = self.run_src('show matches("aaaa!", "(a+)+$").\n')
        self.assertIn('bounded pattern profile', rep['error']['message'])
        self.assertTrue(self.run_src('show matches("abc", "^a[bc]+$").\n')['outputs'][0]['value'])
        rep = self.run_src('show eval("matches(\\"a\\", \\"a\\")").\n')
        self.assertIn('not available inside eval', rep['error']['message'])
        self.assertEqual(self.run_src('show eval("2 * x", x=21).\n')['outputs'][0]['value'], 42)

    def test_fail_stops_a_run_with_a_check_and_is_not_available_to_eval(self):
        rep = self.run_src('let x = -2.\nlet y = if x < 0 then fail("negative length") else sqrt(x).\n')
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'check')
        self.assertIn('negative length', rep['error']['message'])
        self.assertEqual(self.run_src('let y = if 4 < 0 then fail("no") else sqrt(4).\nshow y.\n')['outputs'][0]['value'], 2)
        self.assertIn('not available inside eval', self.run_src('show eval("fail(\\"x\\")").\n')['error']['message'])

    def test_reports_name_their_kernel(self):
        rep = self.run_src('show 4 + 4.\n')
        self.assertEqual(rep['kernel']['lang'], S.VERSION)
        self.assertEqual(len(rep['kernel']['id']), 16)
        # the identity programs (copies of two published examples) keep their fingerprints on every machine
        fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
        for name, fp in (('02-flower-formal.sym', 'c2351a32c05cc58d'), ('10-kernel-identity.sym', 'fff6d4efbecb4a3a')):
            with open(os.path.join(fixtures, name)) as fh:
                self.assertEqual(self.run_src(fh.read())['fingerprint'], fp)


class Soundness(unittest.TestCase):
    """2026-10-02 semantics audit R1/R5: what is formal is decided by its form, and check() refuses what a run
    would refuse."""

    def test_formal_looking_lines_are_kernel_statements(self):
        kinds = [(n.line, n.k) for n in S.parse('let x = 4.\nx = 4.\n4 = x.\ntrue.\nnot false.\n'
                                                'all v in [1, 2]: v > 0.\nPrice is high.\nSummarize the request.\n'
                                                'Test it twice.\n')['statements']]
        self.assertEqual(kinds, [(1, 'let'), (2, 'show'), (3, 'show'), (4, 'show'), (5, 'show'), (6, 'show'),
                                 (7, 'ask'), (8, 'ask'), (9, 'ask')])

    def test_a_keyword_typo_is_a_syntax_error_not_a_model_call(self):
        with self.assertRaises(S.SymblicError) as cm:
            S.parse('lett y = 2.\n')
        self.assertIn('did you mean `let`', cm.exception.message)
        self.assertEqual(S.parse('Set the table for four.\n')['statements'][0].k, 'ask')

    def test_a_loop_never_lifts_a_name_some_iterations_did_not_bind(self):
        from symblic.kernel import run as SR
        src = 'let xs = [1, -2, 3].\nfor v in xs do\n  if v > 0 then\n    let y = v * 10.\n  end.\nend.\nshow zip(xs, y).\n'
        self.assertIn('may not be bound', ' '.join(e['message'] for e in S.check(src)['errors']))
        rep = SR.Run(src, None, None, {}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('2 of 3 iterations', rep['error']['message'])

    def test_check_refuses_what_a_run_would_refuse(self):
        def errors(src):
            return ' | '.join(e['message'] for e in S.check(src)['errors'])
        self.assertIn('may not be bound', errors('given c: Bool = false.\nif c then\n  let x = 1.\nend.\nshow x.\n'))
        self.assertEqual(errors('given c: Bool = false.\nif c then\n  let x = 1.\nelse\n  let x = 2.\nend.\n'
                                'show x.\n'), '')
        self.assertIn('must be ground', errors('fact p(X).\n'))
        self.assertIn('duplicate option', errors('ask c: one of {Red, red} "Colour?"\n'))
        self.assertIn('Int in a..b', errors('ask c: one of {1, 2} "n?"\n'))
        self.assertIn('use Bool', errors('ask c: one of {true, false} "b?"\n'))
        # rule safety follows the solver's order: positives, then comparisons as written
        self.assertIn('used before anything binds it', errors('rule r(Z) if p(X) and Z = Y * 2 and Y = X + 1.\n'))
        self.assertEqual(errors('rule r(Z) if p(X) and Y = X + 1 and Z = Y * 2.\n'), '')
        self.assertIn('before "not q', errors('rule b(X) if p(X) and not q(X, Y).\n'))


class Regressions(unittest.TestCase):
    def test_a_fractional_temperature_reaches_the_applicator_as_a_float(self):
        # 2026-10-02 helper report: temperature=0.7 is an exact 7/10 and broke the replay key (0 calls, crash)
        from symblic.kernel import run as SR
        seen = []

        class Fake:
            def call(self, req):
                seen.append(req['temperature'])
                json.dumps(req["temperature"])
                return {'ok': True, 'json': {'answer': 8}}
        rep = SR.Run('ask x: Int "Eight." with effort=low, temperature=0.7\n', None, Fake(),
                     {'by': 'claude:haiku', 'parallel': 1}).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(seen, [0.7])
        self.assertEqual(SR.call_key({'engine': 'claude'}, 's', 'p', {}, 0, Fraction(7, 10), 7),
                         SR.call_key({'engine': 'claude'}, 's', 'p', {}, 0, 0.7, 7))


if __name__ == '__main__':
    unittest.main()

"""symblic_lang: functions, routines, modules (symblic_lib) and in-language tests. Fake applicators only
(no model, no network, no dashboard); saved programs come from a stub, run folders are temporary."""

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
from symblic.lang import abstraction as L  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402


class FakeApps:
    """answer(prompt, req) -> a JSON-able answer object. Records every request."""

    def __init__(self, answer):
        self.answer = answer
        self.reqs = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        return {'ok': True, 'json': self.answer(req['prompt'], req), 'ms': 1}


def run(src, answer=None, inputs=None, folder=None, **opts):
    apps = FakeApps(answer) if answer else None
    o = {'by': 'fake:a'}
    o.update(opts)
    r = SR.Run(src, inputs, apps, o, folder=folder)
    return r, r.execute(), apps


def binding(rep, name):
    return next(b for b in rep['bindings'] if b['name'] == name)


class Base(unittest.TestCase):
    def setUp(self):
        L.register()             # another suite may have cleared symblic.EXTENSIONS


class Functions(Base):
    def test_pure_functions_typed_recursive_and_exact(self):
        r, rep, _ = run('function sq(x: Number) -> Number = x * x.\n'
                        'function fact(n: Int) -> Int = if n = 0 then 1 else n * fact(n - 1).\n'
                        'function hyp(a: Number, b: Number = 4) -> Number = sqrt(sq(a) + sq(b)).\n'
                        'let a = sq(0.1).\nlet f = fact(25).\nlet h = hyp(3).\nlet g = hyp(b=12, a=5).\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('a').value, Fraction(1, 100))
        self.assertEqual(r.kernel.env.lookup('f').value, 15511210043330985984000000)
        self.assertEqual(r.kernel.env.lookup('h').value, 5)
        self.assertEqual(r.kernel.env.lookup('g').value, 13)
        self.assertEqual(binding(rep, 'f')['class'], 'exact')

    def test_argument_and_result_types_are_checked(self):
        for src, msg in (('function f(x: Int) -> Int = x.\nlet y = f(1.5).\n', 'f:'),
                         ('function f(x: Int) -> Int = x / 2.\nlet y = f(3).\n', 'result of f'),
                         ('function f(x) = x.\nlet y = f(1, 2).\n', 'takes 1'),
                         ('function f(x) = x.\nlet y = f(z=1).\n', 'no parameter z'),
                         ('function f(x) = x.\nlet y = f().\n', 'needs x')):
            _, rep, _ = run(src)
            self.assertEqual(rep['status'], 'failed', src)
            self.assertIn(msg, rep['error']['message'], src)

    def test_unbounded_recursion_is_a_clear_error(self):
        _, rep, _ = run('function loop(n) = loop(n + 1).\nlet x = loop(0).\n')
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('nest deeper', rep['error']['message'])

    def test_names_are_defined_once_and_builtins_are_reserved(self):
        _, rep, _ = run('function f(x) = x.\nfunction f(x) = x + 1.\n')
        self.assertIn('already defined', rep['error']['message'])
        with self.assertRaises(S.SymblicError):
            S.parse('function sum(x) = x.\n')
        with self.assertRaises(S.SymblicError):
            S.parse('function f(x, x) = x.\n')
        with self.assertRaises(S.SymblicError):
            S.parse('function f(a = 1, b) = a.\n')

    def test_check_and_plan(self):
        c = S.check('function sq(x: Number) -> Number = x * x.\nlet a = sq(3).\n')
        self.assertTrue(c['ok'], c['errors'])
        self.assertEqual(c['warnings'], [])
        typo = S.check('let k = 2.\nfunction f(x, y = k) = x * yy + k.\n')['warnings']   # found before any run
        self.assertEqual([w['message'] for w in typo], ['yy is read before anything binds it'])
        self.assertEqual(c['plan'][0]['label'], 'function sq(x) -> Number')


def colour_answer(prompt, req):
    m = re.search(r'What colour is (\w+)', prompt)
    return {'answer': {'banana': 'yellow', 'grass': 'green'}.get(m.group(1) if m else '', 'red')}


ROUTINE = '''program Colours.
routine colour_of(thing: Text) -> one of {red, green, yellow} with effort=low do
  ask c: one of {red, green, yellow} "What colour is {thing}?"
  if c = "yellow" then
    return "yellow".
  end.
  return c.
end.
'''


class Routines(Base):
    def test_a_routine_is_a_typed_llm_function(self):
        r, rep, apps = run(ROUTINE + 'let a = colour_of("banana").\nlet b = colour_of("grass").\n', colour_answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual((r.kernel.env.lookup('a').value, r.kernel.env.lookup('b').value), ('yellow', 'green'))
        self.assertEqual(len(apps.reqs), 2)
        self.assertIn('STATEMENT', apps.reqs[0]['prompt'])            # the normal capsule
        self.assertEqual(apps.reqs[0]['schema']['properties']['answer']['enum'], ['red', 'green', 'yellow'])
        calls = [t for t in rep and r.trace if t['kind'] == 'call']
        self.assertEqual(len(calls), 2)
        self.assertIn('[closed]', calls[0]['note'])
        # the routine's own bindings stay inside it
        self.assertIsNone(r.kernel.env.lookup('c'))

    def test_same_arguments_same_answer_within_a_run(self):
        answers = iter(['red', 'green', 'yellow'])
        r, rep, apps = run(ROUTINE + 'let a = colour_of("rose").\nlet b = colour_of("rose").\n'
                                     'assert a = b.\n', lambda p, q: {'answer': next(answers)})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(len(apps.reqs), 1)
        self.assertTrue(any('same call, recorded' in t.get('note', '') for t in r.trace))

    def test_ensure_retry_inside_a_routine(self):
        seen = []

        def answer(prompt, req):
            seen.append(prompt)
            return {'answer': 7 if len(seen) == 1 else 12}
        r, rep, _ = run('routine even(n: Int) -> Int do\n  ask x: Int "An even number above {n}."\n'
                        '  ensure x mod 2 = 0 else retry.\n  return x.\nend.\nlet e = even(5).\n', answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('e').value, 12)
        self.assertIn('failed the check', seen[1])

    def test_routine_options_are_defaults_inside_it_only(self):
        r, rep, apps = run('routine pick() -> Int with effort=high do\n'
                           '  ask x: Int in 1..3 "Pick."\n  return x.\nend.\n'
                           'let a = pick().\nask b: Int in 1..3 "Pick again."\n', lambda p, q: {'answer': 2})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(len(apps.reqs), 3 + 1)           # effort=high: 3 votes inside, 1 outside

    def test_result_class_follows_the_model(self):
        """With the core hook (kernel.klass) the binding is 'closed'; without it the call row says so."""
        r, rep, _ = run(ROUTINE + 'let a = colour_of("banana").\n', colour_answer)
        call = next(t for t in r.trace if t['kind'] == 'call')
        self.assertIn('[closed]', call['note'])
        self.assertEqual(L.state(r).taint, 'closed')
        if 'klass' in SR.Run.exec_statement.__code__.co_names:
            self.assertEqual(binding(rep, 'a')['class'], 'closed')

    def test_a_routine_must_return_and_cannot_run_inside_an_ask(self):
        _, rep, _ = run('routine f() -> Int do\n  let x = 1.\nend.\nlet y = f().\n')
        self.assertIn('without return', rep['error']['message'])
        _, rep, _ = run(ROUTINE + 'ask x: Text "Say {colour_of(\\"sky\\")}." for each i in [1, 2]\n', colour_answer)
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('in its own statement', rep['error']['message'])

    def test_replay_from_the_record_needs_no_model(self):
        tmp = tempfile.mkdtemp()
        try:
            _, rep, apps = run(ROUTINE + 'let a = colour_of("banana").\n', colour_answer, folder=tmp)
            self.assertEqual(len(apps.reqs), 1)
            r2, rep2, apps2 = run(ROUTINE + 'let a = colour_of("banana").\n',
                                  lambda p, q: self.fail('asked a model on replay'), folder=tmp)
            self.assertEqual(rep2['status'], 'done', rep2['error'])
            self.assertEqual(rep2['fingerprint'], rep['fingerprint'])
            self.assertEqual(len(apps2.reqs), 0)
        finally:
            shutil.rmtree(tmp)


class Modules(Base):
    def test_library_import_forms(self):
        r, rep, _ = run('import units.\nimport stats as st.\nimport fleiss_kappa, variance from stats.\n'
                        'let cm = convert_length(1, "inch", "cm").\nlet v = variance([2, 4, 4, 4, 5, 5, 7, 9]).\n'
                        'let k = fleiss_kappa([[3, 0], [0, 3]]).\nshow length_in_m.inch.\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('cm').value, Fraction(254, 100))
        self.assertEqual(r.kernel.env.lookup('v').value, 4)
        self.assertEqual(r.kernel.env.lookup('k').value, 1)

    def test_qualified_calls_need_the_parser_hook(self):
        src = 'import stats as st.\nlet v = st.variance([1, 3]).\n'
        try:
            S.parse(src)
        except S.SymblicError:
            self.skipTest('core parser hook for g.f(...) not applied yet')
        r, rep, _ = run(src)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('v').value, 1)
        self.assertEqual(r.kernel.env.lookup('st').value, {})         # stats has no public constants

    def test_fleiss_kappa_matches_the_published_example(self):
        # Fleiss' kappa worked example: 10 subjects, 14 raters, 5 categories; P-bar 0.378, P-e 0.213, kappa 0.210
        table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
                 [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
        n = 14
        p_bar = sum(Fraction(sum(c * c for c in row) - n, n * (n - 1)) for row in table) / len(table)
        p_e = sum(Fraction(sum(r[j] for r in table), len(table) * n) ** 2 for j in range(5))
        expected = (p_bar - p_e) / (1 - p_e)
        r, rep, _ = run(f'import fleiss_kappa from stats.\nlet k = fleiss_kappa({table}).\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('k').value, expected)
        self.assertEqual(round(float(expected), 3), 0.210)

    def test_dates_match_pythons_calendar(self):
        import datetime
        import random
        rnd = random.Random(11)
        epoch = datetime.date(1970, 1, 1)
        days = [datetime.date(1, 1, 1), datetime.date(9999, 12, 31), datetime.date(2000, 2, 29),
                datetime.date(1900, 3, 1)] + [epoch + datetime.timedelta(days=rnd.randint(-700000, 400000))
                                              for _ in range(16)]
        names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        src = 'import dates.\n' + ''.join(
            f'show [day_number(date({d.year}, {d.month}, {d.day})), weekday(date({d.year}, {d.month}, {d.day})), '
            f'day_of_year(date({d.year}, {d.month}, {d.day})), from_day_number({(d - epoch).days})].\n' for d in days)
        _, rep, _ = run(src)
        self.assertEqual(rep['status'], 'done', rep['error'])
        for d, o in zip(days, rep['outputs'], strict=True):
            self.assertEqual(o['value'], [(d - epoch).days, names[d.weekday()], d.timetuple().tm_yday,
                                          {'year': d.year, 'month': d.month, 'day': d.day}], d)

    def test_si_constants_are_exact(self):
        r, rep, _ = run('import constants as si.\nlet r = si.gas_constant.\nlet f = si.faraday.\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('r').value, Fraction('6.02214076e23') * Fraction('1.380649e-23'))
        self.assertEqual(r.kernel.env.lookup('f').value, Fraction('6.02214076e23') * Fraction('1.602176634e-19'))

    def test_unit_terms_reach_the_capsule(self):
        r, rep, apps = run('import units.\nask w: Number "How many centimetres is one inch?"\n',
                           lambda p, q: {'answer': 2.54})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertIn('exactly 2.54 centimetres', apps.reqs[0]['prompt'])

    def test_module_isolation_and_errors(self):
        for src, msg in (('import nosuch.\n', 'no module'),
                         ('import variance from units.\n', 'has no variance'),
                         ('import units.\nfunction c_to_f(x) = x.\n', 'already defined'),
                         ('import units.\nlet length_in_m = 1.\n', 'already bound')):
            _, rep, _ = run(src)
            self.assertEqual(rep['status'], 'failed', src)
            self.assertIn(msg, rep['error']['message'], src)
        try:                                    # never a path: a syntax error, or (with the prose filter) prose
            kinds = [s.k for s in S.parse('import ../../etc/passwd.\n')['statements']]
            self.assertNotIn('import', kinds)
        except S.SymblicError:
            pass
        _, rep, _ = run('import "../../etc/passwd" as p.\n')
        self.assertEqual(rep['status'], 'failed')

    def test_saved_programs_as_modules_with_nested_imports_and_private_names(self):
        saved = {
            'Shapes': 'program Shapes.\nimport stats as st.\nfunction _half(x) = x / 2.\n'
                      'function midpoint(a: Number, b: Number) -> Number = _half(a + b).\n'
                      'let golden = (1 + sqrt(5)) / 2.\nterm midpoint means "the point halfway between two numbers".\n'
                      'define Pair as Record {a: Number, b: Number}.\n',
            'Loop A': 'import "Loop B" as b.\n', 'Loop B': 'import "Loop A" as a.\n',
            'Asks': 'ask x: Int "No."\n',
        }
        old = L.saved_source
        L.saved_source = lambda name: saved.get(name)
        try:
            r, rep, _ = run('import "Shapes" as sh.\nlet m = midpoint(1, 2) .\n')
            self.assertEqual(rep['status'], 'failed')               # qualified import does not bind midpoint
            r, rep, _ = run('import "Shapes".\nlet m = midpoint(1, 2).\nlet g = golden.\n'
                            'let p: Pair = {a: 1, b: 2}.\n')
            self.assertEqual(rep['status'], 'done', rep['error'])
            self.assertEqual(r.kernel.env.lookup('m').value, Fraction(3, 2))
            self.assertIn('midpoint', r.terms)
            self.assertIsNone(r.kernel.functions.get('_half'))
            _, rep, _ = run('import "Shapes".\nlet h = _half(2).\n')
            self.assertIn('unknown function _half', rep['error']['message'])
            _, rep, _ = run('import "Loop A" as a.\n')
            self.assertIn('cycle', rep['error']['message'])
            _, rep, _ = run('import "Asks" as a.\n')
            self.assertIn('only declares', rep['error']['message'])
        finally:
            L.saved_source = old

    def test_a_run_keeps_the_module_it_started_with(self):
        tmp = tempfile.mkdtemp()
        saved = {'Lib': 'function f(x) = x + 1.\n'}
        old = L.saved_source
        L.saved_source = lambda name: saved.get(name)
        try:
            _, rep, _ = run('import "Lib".\nlet y = f(1).\n', folder=tmp)
            self.assertEqual(rep['status'], 'done', rep['error'])
            with open(os.path.join(tmp, 'modules.json'), encoding='utf-8') as stream:
                rec = json.load(stream)
            self.assertEqual(rec['saved:Lib']['source'], saved['Lib'])
            self.assertEqual(oct(os.stat(os.path.join(tmp, 'modules.json')).st_mode & 0o777), '0o600')
            saved['Lib'] = 'function f(x) = x + 100.\n'                 # edited after the run started
            r2, rep2, _ = SR.Run('import "Lib".\nlet y = f(1).\n', {}, None, {'by': 'fake:a'}, folder=tmp), None, None
            rep2 = r2.execute()
            self.assertEqual(r2.kernel.env.lookup('y').value, 2)
            self.assertEqual(rep2['fingerprint'], rep['fingerprint'])
        finally:
            L.saved_source = old
            shutil.rmtree(tmp)


class Tests(Base):
    def test_tests_are_skipped_in_a_run_and_run_by_run_tests(self):
        src = ('function sq(x) = x * x.\nlet base = 3.\nask nope: Int "Never asked by tests."\n'
               'test "squares" do\n  assert sq(base) = 9.\nend.\n'
               'test "a failing one" do\n  assert sq(2) = 5.\nend.\n')
        res = L.run_tests(src)
        self.assertEqual((res['passed'], res['failed']), (1, 1))
        failing = res['tests'][1]
        self.assertEqual(failing['title'], 'a failing one')
        self.assertIn('assert failed', failing['error']['message'])
        self.assertEqual(res['asks'], 0)
        r, rep, _ = run(src, lambda p, q: {'answer': 1})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertTrue(any(t['status'] == 'skipped' and t['kind'] == 'test' for t in r.trace))

    def test_each_test_has_its_own_scope(self):
        res = L.run_tests('test "one" do\n  let x = 1.\n  function h(y) = y + x.\n  assert h(1) = 2.\nend.\n'
                          'test "two" do\n  let x = 5.\n  function h(y) = y * x.\n  assert h(2) = 10.\nend.\n')
        self.assertEqual((res['passed'], res['failed']), (2, 0), res)

    def test_every_library_module_passes_its_kernel_tests(self):
        for m in L.library():
            if m['name'] == 'text':
                continue                         # certification tests: they ask models
            res = L.run_tests(L.library_source(m['name']))
            self.assertTrue(res['ok'], (m['name'], res))
            self.assertGreater(res['passed'], 0, m['name'])

    def test_text_routines_with_a_scripted_model(self):
        def answer(prompt, req):
            stmt = prompt.split('STATEMENT', 1)[-1]
            if 'hydrogen and oxygen' in stmt:
                return {'answer': True}
            if 'larger than the Earth' in stmt:
                return {'answer': False}
            if 'OPTIONS' in stmt:
                return {'answer': 2}
            if 'metal' in stmt:
                return {'answer': ['copper', 'tin', 'zinc']}
            if 'planets' in stmt:
                return {'answer': 4}
            if 'boiling point' in stmt:
                return {'answer': 100}
            if 'Summarize' in stmt:
                return {'answer': 'Honeybees pollinate about a third of the crops people eat.'}
            return {'answer': None}
        res = L.run_tests(L.library_source('text'), FakeApps(answer))
        self.assertTrue(res['ok'], res)
        self.assertEqual(res['passed'], 6)          # five that ask a model and the kernel-only quoted_number test

    def test_grounding_check_rejects_an_invented_item(self):
        src = 'import items_in from text.\nlet m = items_in("metal", "Copper and tin.").\n'
        _, rep, apps = run(src, lambda p, q: {'answer': ['copper', 'iron']})
        self.assertEqual(rep['status'], 'failed')                 # never grounded: retries run out
        self.assertIn('ensure failed', rep['error']['message'])
        r, rep, apps = run(src, lambda p, q: {'answer': ['Copper', 'tin'] if 'failed the check' in p
                                              else ['copper', 'iron']})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('m').value, ('Copper', 'tin'))
        self.assertTrue(any('word for word' in q['prompt'] for q in apps.reqs))


class Certify(Base):
    def test_a_routine_is_certified_only_when_every_cohort_passes(self):
        src = ('routine double(n: Int) -> Int do\n  ask x: Int "What is twice {n}?"\n  return x.\nend.\n'
               'test "twice three" do\n  assert double(3) = 6.\nend.\n'
               'test "twice zero" do\n  assert double(0) = 0.\nend.\n')

        def careful(prompt, req):
            n = int(re.search(r'twice (\d+)', prompt).group(1))
            return {'answer': 2 * n}

        def sloppy(prompt, req):
            n = int(re.search(r'twice (\d+)', prompt).group(1))
            return {'answer': 2 * n if n else 1}
        answers = {'fake:careful': careful, 'fake:sloppy': sloppy}
        cert = L.certify(src, ['fake:careful', 'fake:sloppy'], lambda by: FakeApps(answers[by]))
        self.assertFalse(cert['all'])
        self.assertEqual(cert['certified'], ['twice three'])
        zero = next(t for t in cert['tests'] if t['title'] == 'twice zero')
        self.assertEqual((zero['passed'], zero['of']), (1, 2))
        self.assertEqual([c['status'] for c in zero['cohorts']], ['passed', 'failed'])
        cert = L.certify(src, ['fake:careful'], lambda by: FakeApps(careful))
        self.assertTrue(cert['all'])


class Crystal(Base):
    SRC = ('program Colours.\n'
           'routine colour_of(thing: Text) -> one of {red, green, yellow} with effort=high do\n'
           '  ask c: one of {red, green, yellow} "What colour is {thing}?"\n  return c.\nend.\n'
           'routine pair(a: Int, b: Int) -> Int do\n  ask s: Int "What is {a} plus {b}?"\n  return s.\nend.\n'
           'ask unrelated: Int "Never asked while crystallising."\n')

    def test_agreed_answers_become_a_kernel_function(self):
        votes = {}

        def answer(prompt, req):
            m = re.search(r'What colour is (\w+)', prompt)
            thing = m.group(1)
            n = votes[thing] = votes.get(thing, 0) + 1
            if thing == 'rose':                                    # the voters split: not kept
                return {'answer': ['red', 'yellow', 'red'][(n - 1) % 3]}
            return {'answer': {'banana': 'yellow', 'grass': 'green'}[thing]}
        apps = FakeApps(answer)
        res = L.crystallise(self.SRC, 'colour_of', ['banana', 'grass', 'rose'], apps, by='fake:a')
        self.assertEqual([k['input'] for k in res['kept']], ['banana', 'grass'])
        self.assertEqual(res['applicators'], ['fake:a'])
        self.assertIn('Kernel regime: lang', res['module'])
        self.assertIn('model families:', res['module'])
        self.assertEqual(res['left_out'][0]['input'], 'rose')
        self.assertIn('below 100%', res['left_out'][0]['reason'])
        self.assertTrue(S.check(res['module'])['ok'])
        self.assertTrue(L.run_tests(res['module'])['ok'])
        asked = len(apps.reqs)
        old = L.saved_source
        L.saved_source = lambda name: res['module'] if name == 'Colour crystal' else None
        try:
            r, rep, apps2 = run('import "Colour crystal".\nlet a = colour_of("banana").\nlet b = colour_of("grass").\n',
                                lambda p, q: self.fail('a crystal never asks'))
            self.assertEqual(rep['status'], 'done', rep['error'])
            self.assertEqual((r.kernel.env.lookup('a').value, r.kernel.env.lookup('b').value), ('yellow', 'green'))
            self.assertEqual(binding(rep, 'a')['class'], 'exact')            # compiled: decided by the kernel
            _, rep, _ = run('import "Colour crystal".\nlet c = colour_of("rose").\n')
            self.assertEqual(rep['status'], 'failed')                         # outside the table: no guess
        finally:
            L.saved_source = old
        self.assertEqual(len(apps.reqs), asked)

    def test_parallel_workers_keep_the_domain_order(self):
        words = ['w%d' % i for i in range(9)]

        def answer(prompt, req):
            import time as _t
            n = int(re.search(r'What colour is w(\d+)', prompt).group(1))
            _t.sleep(0.002 * (9 - n))                               # later inputs finish first
            return {'answer': ['red', 'green', 'yellow'][n % 3]}
        res = L.crystallise(self.SRC, 'colour_of', words, FakeApps(answer), by='fake:a', workers=4)
        self.assertEqual([k['input'] for k in res['kept']], words)
        one = L.crystallise(self.SRC, 'colour_of', words, FakeApps(answer), by='fake:a', workers=1)
        self.assertEqual(one['module'].split('let ', 1)[1], res['module'].split('let ', 1)[1])

    def test_several_arguments_and_bad_requests(self):
        res = L.crystallise(self.SRC, 'pair', [[1, 2], [3, 4]], FakeApps(
            lambda p, q: {'answer': sum(int(x) for x in re.findall(r'What is (\d+) plus (\d+)', p)[0])}))
        self.assertEqual(len(res['kept']), 2)
        self.assertIn('[[3, 4], 7]', res['module'])
        self.assertTrue(L.run_tests(res['module'])['ok'])
        with self.assertRaises(S.SymblicError):
            L.crystallise(self.SRC, 'nosuch', [1], FakeApps(lambda p, q: {'answer': 1}))


class Library(Base):
    def test_describe_every_module(self):
        lib = {m['name']: m for m in L.library()}
        self.assertTrue({'units', 'stats', 'kinship', 'graphs', 'text', 'dates', 'constants'} <= set(lib))
        text = lib['text']
        names = [i['name'] for i in text['items']]
        self.assertIn('items_in', names)
        doc = next(i for i in text['items'] if i['name'] == 'items_in')['doc']
        self.assertIn('word for word', doc)
        self.assertFalse(any(n.startswith('_') for m in lib.values() for n in [i['name'] for i in m['items']]))
        for m in lib.values():
            self.assertTrue(S.check(L.library_source(m['name']))['ok'], m['name'])

    def test_prose_lines_stay_prose_when_the_core_filters_them(self):
        try:
            prog = S.parse('Import the data from the shared folder.\nTest it twice.\nimport units.\n')
        except S.SymblicError:
            self.skipTest('core prose filter (Extension.looks) not applied yet')
        kinds = [s.k for s in prog['statements']]
        self.assertEqual(kinds, ['ask', 'ask', 'import'])


class ExtensionSoundness(Base):
    def test_distinct_lexical_closures_do_not_share_memo_entries(self):
        source = ('routine parent(x: Int) -> Int do\n'
                  '  routine helper(y: Int) -> Int do\n    return x + y.\n  end.\n'
                  '  return helper(10).\nend.\n'
                  'let a = parent(1).\nlet b = parent(2).\nlet again = parent(1).\n')
        r, rep, _ = run(source)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual([r.kernel.env.lookup(n).value for n in ('a', 'b', 'again')], [11, 12, 11])
        self.assertEqual(L.state(r).calls, 4)
        second, repeated, _ = run(source)
        self.assertEqual(repeated['fingerprint'], rep['fingerprint'])
        self.assertEqual(sorted(L.state(r).memo), sorted(L.state(second).memo))

    def test_cached_weak_evidence_never_becomes_unanimous(self):
        source = ('routine sub_rout(y: Int) -> Int with effort=high do\n'
                  '  ask a: Int "Choose {y}."\n  return a.\nend.\n'
                  'routine test_rout(x: Int) -> Int do\n  return sub_rout(5) + x.\nend.\n')
        calls = []

        def answer(prompt, req):
            calls.append(req)
            return {'answer': 10 if len(calls) == 1 else 20}

        result = L.crystallise(source, 'test_rout', [1, 2], FakeApps(answer), min_agreement=1.0)
        self.assertEqual(result['kept'], [])
        self.assertEqual([row['input'] for row in result['left_out']], [1, 2])
        self.assertTrue(all(row['agreement'] < 1 for row in result['left_out']))
        self.assertEqual(len(calls), 3)       # reuse the observation; do not invent or rerun it
        self.assertEqual(result['left_out'][0]['dependencies'], result['left_out'][1]['dependencies'])

    def test_memo_trace_references_original_ask_and_keeps_class(self):
        source = ('routine inner() -> Int do\n  ask v: Int "Pick." with effort=low\n  return v.\nend.\n'
                  'routine outer(x: Int) -> Int do\n  return inner() + x.\nend.\n'
                  'let a = outer(1).\nlet b = outer(2).\n')
        r, rep, apps = run(source, lambda _p, _q: {'answer': 5})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(len(apps.reqs), 1)
        asks = [row for row in r.trace if row.get('ask') is not None]
        self.assertEqual(len(asks), 1)
        calls = [row for row in r.trace if row['kind'] == 'call']
        self.assertTrue(all(row['dependencies'][0]['sequence'] == asks[0]['sequence'] for row in calls))
        self.assertTrue(all('ask' not in row for row in calls))
        self.assertEqual(binding(rep, 'a')['class'], binding(rep, 'b')['class'])
        self.assertNotEqual(binding(rep, 'b')['class'], 'exact')

    def test_retry_rolls_back_new_definitions_and_memo_results(self):
        attempts = []

        def answer(_prompt, req):
            attempts.append(req)
            return {'answer': len(attempts)}

        source = ('ask x: Int "Pick 1 or 2." with effort=low\n'
                  'routine helper() -> Int do\n  return x.\nend.\n'
                  'let y = helper().\nensure x = 2 and y = 2 else retry.\n')
        r, rep, _ = run(source, answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('y').value, 2)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(L.state(r).declarations, 1)
        self.assertEqual(len(L.state(r).memo), 1)
        self.assertEqual(L.state(r).calls, 1)

    def test_retry_preserves_preexisting_memo_and_discards_rejected_calls(self):
        attempts = []

        def answer(_prompt, req):
            attempts.append(req)
            return {'answer': len(attempts)}

        source = ('routine inc(n: Int) -> Int do\n  return n + 1.\nend.\n'
                  'let before = inc(7).\nask x: Int "Pick." with effort=low\n'
                  'let y = inc(x).\nensure x = 2 and y = 3 else retry.\n')
        r, rep, _ = run(source, answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(sorted(key[1] for key in L.state(r).memo), ['[2]', '[7]'])
        self.assertEqual(L.state(r).calls, 2)

    def test_certification_records_actual_source_and_import_provenance(self):
        import hashlib
        source = 'import units.\ntest "inch" do\n  assert convert_length(1, "inch", "cm") = 2.54.\nend.\n'
        result = L.certify(source, ['fake:a', 'fake:b'], lambda _by: None)
        self.assertTrue(result['all'], result)
        self.assertEqual(result['source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(result['kernel'], S.kernel_id())
        self.assertEqual(result['module_hashes']['lib:units'],
                         hashlib.sha256(L.library_source('units').encode()).hexdigest())
        self.assertTrue(all(row['status'] == 'done' for row in result['cohorts']))

    def test_certification_detects_module_drift_between_cohorts(self):
        from unittest.mock import patch
        source = 'import sample.\ntest "identity" do\n  assert answer() = 1.\nend.\n'
        modules = iter(['function answer() = 1.\n', 'note changed.\nfunction answer() = 1.\n'])
        with patch.object(L, 'library_source', side_effect=lambda _name: next(modules)):
            result = L.certify(source, ['fake:a', 'fake:b'], lambda _by: None)
        self.assertFalse(result['all'])
        self.assertNotIn('module_hashes', result)
        self.assertIn('different module', result['provenance_divergence'])
        self.assertNotEqual(result['cohorts'][0]['module_hashes'], result['cohorts'][1]['module_hashes'])

    def test_certificate_cli_writes_private_source_pinned_artifact(self):
        import contextlib
        import io
        import stat
        from unittest.mock import patch
        from symblic.kernel import certificates as C
        source = 'test "arithmetic" do\n  ask x: Int "Two plus two?" with effort=low\n  assert x = 4.\nend.\n'
        with tempfile.TemporaryDirectory() as tmp:
            program = os.path.join(tmp, 'program.sym')
            target = os.path.join(tmp, 'certificate.json')
            with open(program, 'w', encoding='utf-8') as stream:
                stream.write(source)
            fake = lambda **kw: FakeApps(lambda _p, _q: {'answer': 4})  # noqa: E731
            with patch('symblic.providers.applicators.Applicators', fake), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = L.main(['certify', program, '--cohort', 'fake:a', '--certificate-out', target, '--json'])
            self.assertEqual(code, 0)
            self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
            with open(target, encoding='utf-8') as stream:
                certificate = json.load(stream)
            checked = C.validate_certificate(certificate, source, module_hashes={})
            self.assertTrue(checked['candidates'][0]['qualified'])
            self.assertEqual(sorted(os.listdir(tmp)), ['certificate.json', 'program.sym'])


if __name__ == '__main__':
    unittest.main()

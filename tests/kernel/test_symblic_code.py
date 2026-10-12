"""Symblic code generation: the Code answer type, the sandboxed JavaScript adapter (js_test / js_run), checked
search over several applicators (route=search), escalation feedback from `because`, and the spec-sheet compiler.
Fake applicators only; no model, worker node or network. The JavaScript adapter runs a local node process
inside the Landlock sandbox, symblic/sandbox/landlock.py (skipped when node is not installed)."""

import threading
import time
import unittest
from unittest import mock

from symblic.kernel import language as S
from symblic.js import check as J
from symblic.spec import sheets as SP
from symblic.kernel.run import Run

NODE = J.available()


class Replies:
    """answers: {model: [reply text, ...]} (the last one repeats); records every request."""

    def __init__(self, answers, delays=None):
        self.answers, self.delays, self.requests, self.lock = answers, delays or {}, [], threading.Lock()

    def call(self, req):
        name = req['app']['model'] or req['app']['engine']
        with self.lock:
            self.requests.append(dict(req))
            n = sum(1 for r in self.requests if (r['app']['model'] or r['app']['engine']) == name)
        time.sleep(self.delays.get(name, 0))
        seq = self.answers[name]
        return {'ok': True, 'text': seq[min(n - 1, len(seq) - 1)], 'json': None, 'model': name, 'node': 'n', 'ms': 1}


def js(code):
    return 'Here it is:\n```js\n' + code + '\n```'


class CodeType(unittest.TestCase):
    def test_type_label_description_and_no_schema(self):
        prog = S.parse('ask f: Code js "write add".\n')
        ty = prog.statements[0].type if hasattr(prog, 'statements') else None
        ty = ty or {'k': 'code', 'lang': 'js'}
        self.assertEqual(S.type_label({'k': 'code', 'lang': 'js'}), 'Code js')
        self.assertEqual(S.describe_type({'k': 'code', 'lang': 'js'}), 'JavaScript code')
        self.assertIsNone(S.answer_schema({'k': 'code'}, True))
        self.assertEqual(S.determinism_class({'k': 'code'}), 'open')
        self.assertTrue(S.check('program C.\nask f: Code "x" by "fake:a".\nshow f.\n')['ok'])

    def test_the_last_fenced_block_is_the_answer(self):
        ty = {'k': 'code', 'lang': 'js'}
        cases = [
            ('Sure:\n```js\nfunction a(){}\n```\nDone.', 'function a(){}'),
            ('think\n```javascript\nconst x = 1;\n```\nthen\n```js\nfunction b(){}\n```', 'function b(){}'),
            ('```js\nfunction c(){}\n', 'function c(){}'),                     # an unclosed last fence runs to the end
            ('function d(){}', 'function d(){}'),                              # no fence: the whole reply
            ('{"answer": "function e(){}"}', 'function e(){}'),                # answered in JSON anyway
            ('```\r\nline1\r\n  line2\r\n```', 'line1\n  line2'),              # indentation kept, line ends unified
        ]
        for reply, want in cases:
            with self.subTest(reply=reply):
                self.assertEqual(S.read_answer(reply, ty)[0], want)
        with self.assertRaises(S.SymblicError):
            S.read_answer('```js\n\n```', ty)

    def test_capsule_asks_for_one_fenced_block_and_sends_no_schema(self):
        cap = S.capsule('P', 1, 1, 'ask f : Code js\n  "write add"', {'k': 'code', 'lang': 'js'}, 'medium', [], [])
        self.assertIsNone(cap['schema'])
        self.assertEqual(cap['system'], S.CODE_SYSTEM)
        self.assertIn('```js', cap['prompt'])
        self.assertNotIn('"reasoning"', cap['prompt'])

    def test_a_code_reply_is_read_from_its_text_not_a_json_object_inside_it(self):
        src = 'program P.\nask f: Code js "write cfg" by "fake:a".\nshow f.\n'
        code = 'const cfg = {"answer": 1};'
        rep = Run(src, applicators=Replies({'a': [js(code)]})).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(rep['outputs'][0]['text'], code)


@unittest.skipUnless(NODE, 'node is not installed')
class JavaScriptAdapter(unittest.TestCase):
    def test_passing_and_failing_examples_are_reported_exactly(self):
        r = J.test('function add(a, b) { return a - b; }', [('add(2, 3)', '5'), ('add(1, 1)', '0')])
        self.assertEqual((r['passed'], r['total'], r['failed']), (False, 2, 1))
        self.assertIn('add(2, 3)\n  expected 5\n  got      -1', r['report'])
        self.assertTrue(J.test('function add(a, b) { return a + b; }', [('add(2, 3)', '5')])['passed'])

    def test_values_compare_as_json(self):
        r = J.test('const o = {b: [true], a: 1};', [('o', '{"a": 1, "b": [true]}'), ('1', 'true'), ('0.5', '0.50')])
        self.assertEqual(r['failed'], 1)                       # 1 is not true; key order and 0.5 = 0.50 are fine
        self.assertIn('expected true', r['report'])
        nan = J.test('function f() { return NaN; }', [('f()', 'null')])
        self.assertFalse(nan['passed'])                        # NaN is never the JSON null an example expects

    def test_broken_code_and_escapes_fail_closed(self):
        self.assertIn('The code does not run: SyntaxError', J.test('function f( {', [('f()', '1')])['report'])
        # pieces run as separate scripts: their consts and functions carry over, but a function defined again fails
        # (a classic script would let the copy replace the earlier one silently, 2026-10-04)
        ok = J.test(['const N = 2;\nfunction dbl(x) { return x * N; }', 'function quad(x) { return dbl(dbl(x)); }'],
                    [('quad(3)', '12')])
        self.assertTrue(ok['passed'], ok['report'])
        again = J.test(['function dbl(x) { return x * 2; }\nfunction helper() { return 0; }',
                        'function quad(x) { return dbl(dbl(x)); }\nfunction dbl(x) { return x * 3; }'],
                       [('quad(1)', '4'), ('dbl(1)', '2')])
        self.assertFalse(again['passed'])
        self.assertIn('The code does not run: it defines dbl again, but the code it runs with already defines it',
                      again['report'])
        self.assertIn('Remove your own copies and call the existing ones', again['report'])
        self.assertIn('has already been declared', J.test(['const N = 1;', 'const N = 2;'], [('N', '1')])['report'])
        before = J.test(['function helper(g) {\n  return g.rows.map((r) => r.map((x) => x));\n}', 'function f() {}'],
                        [('helper({ rows: ["ab"] })', '[]')])['report']
        self.assertIn('(in this line of the code run before it: return g.rows.map((r) => r.map((x) => x));)', before)
        kernel = S.Kernel(S.Env(), S.KB(), S.Budget())
        self.assertEqual(J.FUNCTIONS['js_run'](kernel, None, ['const a = 2;', 'const b = a + 1;'], 'b'), 3)
        with self.assertRaises(S.SymblicError):
            J.FUNCTIONS['js_test'](kernel, None, ['ok', 3], [('1', '1')])
        # an error names the line's text, not a number in the joined source the model never saw whole
        rep = J.test('function helper(g) { return g.rows.map((r) => r.map((x) => x)); }\nfunction f() { return 1; }',
                     [('helper({ rows: ["ab"] })', '[]')])['report']
        self.assertIn('TypeError', rep)
        self.assertIn('(in this line: function helper(g) { return g.rows.map((r) => r.map((x) => x)); })', rep)
        self.assertNotIn('of the code', rep)
        for call in ("this.constructor.constructor('return process')()", "eval('1')", 'new Function("return 1")()',
                     'Math.random()', "(function(){ return typeof require + typeof process })() === 'functionobject'"):
            with self.subTest(call=call):
                r = J.test('', [(call, 'true')])
                self.assertFalse(r['passed'], r['report'])
        self.assertEqual(J.test('', [('Date.now()', '1700000000000')])['passed'], True)   # a fixed clock
        with self.assertRaisesRegex(J.JsError, 'inconclusive') as got:
            J.test('', [('(()=>{ while (true) {} })()', '1')])
        self.assertEqual(got.exception.kind, 'resource')

    def test_each_case_runs_in_a_fresh_context(self):
        r = J.test('var n = 0; function bump() { n += 1; return n; }', [('bump()', '1'), ('bump()', '1')])
        self.assertTrue(r['passed'], r['report'])

    def test_lone_surrogates_and_bad_inputs(self):
        r = J.test('', [("'a\\ud800b'", '"x"')])
        self.assertFalse(r['passed'])
        S.fingerprint(r)                                       # never raises on what came back
        kernel = S.Kernel(S.Env(), S.KB(), S.Budget())
        with self.assertRaises(S.SymblicError):
            J.FUNCTIONS['js_test'](kernel, None, 'x', [('1', 'not json')])
        with self.assertRaises(S.SymblicError):
            J.FUNCTIONS['js_test'](kernel, None, 'x', [])
        self.assertEqual(J.FUNCTIONS['js_run'](kernel, None, 'const a = [1, {b: 2}];', 'a'), (1, {'b': 2}))

    def test_the_kernel_identity_names_the_engine(self):
        self.assertTrue(str(S.kernel_id()['js']).startswith(f'{J.ADAPTER}+node'))

    def test_check_and_speculation_never_start_node(self):
        src = ('program P.\nask f: Code js "add" by "fake:a".\nlet t = js_test(f, [["1", "1"]]).\n'
               'ensure t.passed else retry because t.report.\nshow f.\n')
        with mock.patch.object(J, 'evaluate', side_effect=AssertionError('node started during check')):
            self.assertTrue(S.check(src)['ok'])
        calls = []
        real = J.evaluate
        with mock.patch.object(J, 'evaluate', side_effect=lambda s, c, *a: calls.append(s) or real(s, c, *a)):
            rep = Run(src, applicators=Replies({'a': [js('1')]})).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(calls, [['1']])                      # only the real candidate, no empty-answer probe
        self.assertIn('js_test', S.EVAL_DENIED)


@unittest.skipUnless(NODE, 'node is not installed')
class Repairs(unittest.TestCase):
    PROGRAM = ('program P.\nask add: Code js "Write add(a, b)." by {by} with {opts}.\n'
               'let t = js_test(add, [["add(2, 3)", "5"]]).\nensure t.passed else retry because t.report.\nshow add.\n')

    def test_ensure_retry_shows_the_test_report(self):
        apps = Replies({'a': [js('function add(a,b){return a-b}'), js('function add(a,b){return a+b}')]})
        rep = Run(self.PROGRAM.format(by='"fake:a"', opts='retries=2'), applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('expected 5\n  got      -1', apps.requests[1]['prompt'])

    def test_escalation_uses_because_and_shows_the_whole_previous_code(self):
        wrong = 'function add(a, b) {\n  // a long comment ' + 'x' * 300 + '\n  return a - b;\n}'
        apps = Replies({'a': [js(wrong), js('function add(a,b){return a+b}')]})
        rep = Run(self.PROGRAM.format(by='"fake:a"', opts='route=escalate, retries=2'), applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        repair = apps.requests[1]['prompt']
        self.assertIn('expected 5\n  got      -1', repair)       # the author's `because`, not only the predicate
        self.assertIn(wrong, repair)                            # the whole previous code, not 200 characters
        self.assertIn('Write the corrected, complete code in one fenced block.', repair)
        self.assertNotIn('JSON', repair.split('CHECK REJECTED')[1])


@unittest.skipUnless(NODE, 'node is not installed')
class Search(unittest.TestCase):
    PROGRAM = ('program P.\nuse by=["fake:a", "fake:b", "fake:c"].\n'
               'ask add: Code js "Write add(a, b)." with route=search{opts}.\n'
               'let t = js_test(add, [["add(2, 3)", "5"]]).\nensure t.passed else retry because t.report.\nshow add.\n')
    GOOD, BAD = js('function add(a,b){return a+b}'), js('function add(a,b){return a-b}')

    def run_(self, answers, opts=', retries=1', delays=None, parallel=3):
        apps = Replies(answers, delays)
        rep = Run(self.PROGRAM.format(opts=opts), applicators=apps, options={'parallel': parallel}).execute()
        return rep, apps

    def test_fewest_attempts_then_lowest_index_wins_never_arrival_order(self):
        # c passes at its first attempt; b only after a repair; a never: c wins (fewest attempts)
        rep, apps = self.run_({'a': [self.BAD], 'b': [self.BAD, self.GOOD], 'c': [self.GOOD]},
                              delays={'a': 0.2, 'b': 0.2, 'c': 0.01})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        meta = next(b for b in rep['bindings'] if b['name'] == 'add')['meta']
        self.assertEqual((meta['route'], meta['selected'], meta['rounds']), ('search', 'fake:c', 1))
        # a and b both pass at their first attempt; b arrives first, but a (the lower index) is selected
        rep, _ = self.run_({'a': [self.GOOD], 'b': [self.GOOD], 'c': [self.BAD]}, delays={'a': 0.3, 'b': 0.01, 'c': 0.01})
        meta = next(b for b in rep['bindings'] if b['name'] == 'add')['meta']
        self.assertEqual(meta['selected'], 'fake:a')
        # a needs a repair, b passes at once: b wins without waiting for a's repair
        rep, apps = self.run_({'a': [self.BAD, self.GOOD], 'b': [self.GOOD], 'c': [self.BAD]}, opts=', retries=3',
                              delays={'a': 0.3, 'b': 0.01, 'c': 0.01})
        meta = next(b for b in rep['bindings'] if b['name'] == 'add')['meta']
        self.assertEqual(meta['selected'], 'fake:b')
        temps = {(r['app']['model'], r['seed'], r['temperature']) for r in apps.requests if r['sample'] < 1000}
        self.assertEqual(temps, {('a', 7, 0), ('b', 8, 0.7), ('c', 9, 0.7)})

    def test_a_passing_first_candidate_stops_the_others(self):
        rep, apps = self.run_({'a': [self.GOOD], 'b': [self.BAD], 'c': [self.BAD]}, opts=', retries=4',
                              delays={'a': 0.01, 'b': 0.3, 'c': 0.3})
        self.assertEqual(rep['status'], 'done')
        self.assertLessEqual(sum(1 for r in apps.requests if r['app']['model'] in 'bc'), 2)   # no repairs started

    def test_acceptance_cancels_the_other_candidates_in_flight_calls(self):
        # a passes quickly; b and c are slow models still generating: their calls see the stop and end at once
        stopped = []

        class Slow(Replies):
            def call(self, req):
                name = req['app']['model']
                if name == 'a':
                    return super().call(req)
                with self.lock:
                    self.requests.append(dict(req))
                if req['stop'].wait(5):            # a real applicator polls stop and cancels its call
                    stopped.append(name)
                    return {'ok': False, 'error': 'stopped', 'fatal': True}
                return {'ok': True, 'text': Search.BAD, 'model': name, 'node': 'n', 'ms': 1}
        apps = Slow({'a': [self.GOOD]})
        t0 = time.time()
        rep = Run(self.PROGRAM.format(opts=', retries=2'), applicators=apps, options={'parallel': 3}).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertLess(time.time() - t0, 4)       # it did not wait 5 s for b and c
        self.assertEqual(sorted(stopped), ['b', 'c'])

    def test_fresh_rounds_then_a_failure(self):
        rep, apps = self.run_({'a': [self.BAD], 'b': [self.BAD], 'c': [self.BAD]}, opts=', retries=0, rounds=2')
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('no search candidate passed its checks in 2 round(s) of 3', rep['error']['message'])
        seeds = sorted(r['seed'] for r in apps.requests)
        self.assertEqual(seeds, [7, 8, 9, 1007, 1008, 1009])
        self.assertNotIn('CHECK REJECTED', apps.requests[-1]['prompt'])     # a new round carries no feedback
        rep, _ = self.run_({'a': [self.BAD], 'b': [self.BAD], 'c': [self.BAD, self.GOOD]}, opts=', retries=0, rounds=2')
        self.assertEqual(rep['status'], 'done')

    def test_options_are_checked(self):
        for opts in (', samples=0', ', rounds=99', ', votes=3'):
            with self.subTest(opts=opts):
                rep, _ = self.run_({'a': [self.GOOD], 'b': [self.GOOD], 'c': [self.GOOD]}, opts=opts)
                self.assertEqual(rep['status'], 'failed')
        rep, _ = self.run_({'a': [self.GOOD], 'b': [self.GOOD], 'c': [self.GOOD]}, opts=', samples=5')
        self.assertEqual(rep['status'], 'done')
        no_check = 'program P.\nask x: Code js "x" by "fake:a" with route=search.\nshow x.\n'
        self.assertEqual(Run(no_check, applicators=Replies({'a': [self.GOOD]})).execute()['status'], 'failed')


SHEET = """# tiny.js

Two units.

## Shared

Plain JavaScript functions.

## Unit `double(x)`

Return x times 2.

Examples:

    double(2) ==> 4
    double(-1) ==> -2

## Unit `quad(x)`

Uses: `double`

Return double(double(x)). Text with {braces}, a backslash \\n and \"\"\"quotes\"\"\".

Test setup:

    function four() { return 4; }

Examples:

    quad(1) ==> four()
    quad(3) ==> 12

## Assemble `tiny.html`

    <script>
    /*UNITS*/
    </script>
"""


class SpecSheet(unittest.TestCase):
    def test_parse_and_problems(self):
        sheet = SP.parse(SHEET.replace('quad(1) ==> four()', 'quad(1) ==> 4'))
        self.assertEqual([u['names'] for u in sheet['units']], [['double'], ['quad']])
        self.assertEqual(sheet['units'][1]['uses'], ['double'])
        self.assertEqual(sheet['units'][1]['setup'], 'function four() { return 4; }')
        self.assertEqual(SP.problems(sheet), [])
        bad = SP.parse(SHEET)                                   # four() is not JSON
        self.assertTrue(any('not JSON' in p for p in SP.problems(bad)))
        later = SP.parse(SHEET.replace('Uses: `double`', '').replace('Return x times 2.', 'Uses: `quad`\n\nReturn x.'))
        self.assertTrue(any('later unit' in p for p in SP.problems(later)))
        self.assertTrue(any('/*UNITS*/' in p for p in SP.problems(SP.parse(SHEET.replace('/*UNITS*/', 'x')))))

    def test_literals_read_back_exactly(self):
        for text in ('a {b} \\n "q" """three"""', 'ends with "', '{{already}}', 'tab\there'):
            with self.subTest(text=text):
                src = f'let x = {SP.literal(text)}.\nshow x.\n'
                rep = Run(src, {}, None, {}).execute()
                self.assertEqual(rep['outputs'][0]['text'], text)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_compiled_sheet_builds_from_passing_units_only(self):
        text = SHEET.replace('quad(1) ==> four()', 'quad(1) ==> 4')
        src = SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1)
        self.assertTrue(S.check(src)['ok'], S.check(src).get('errors'))
        answers = {'double': js('function double(x) { return x * 2; }'),
                   'quad': [js('function quad(x) { return x * 3; }'), js('function quad(x) { return double(double(x)); }')]}

        class Units:
            def __init__(self):
                self.requests = []

            def call(self, req):
                self.requests.append(req)
                name = 'quad' if 'YOUR UNIT: `quad(x)`' in req['prompt'] else 'double'
                seq = answers[name] if isinstance(answers[name], list) else [answers[name]]
                n = sum(1 for r in self.requests if ('`quad(x)`' in r['prompt']) == (name == 'quad'))
                return {'ok': True, 'text': seq[min(n - 1, len(seq) - 1)], 'model': 'a', 'node': 'n', 'ms': 1}
        apps = Units()
        rep = Run(src, applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        out = rep['outputs'][-1]
        self.assertEqual(out['label'], 'tiny.html')
        self.assertIn('return double(double(x));', out['text'])
        self.assertNotIn('x * 3', out['text'])                  # the failing first answer never reaches the file
        quad_prompt = next(r['prompt'] for r in apps.requests if '`quad(x)`' in r['prompt'])
        self.assertIn('Plain JavaScript functions.', quad_prompt)         # the shared section, interpolated
        self.assertNotIn('sheet_shared', quad_prompt)
        self.assertIn('// double(x): Return x times 2.\n```js\nfunction double(x) { return x * 2; }\n```', quad_prompt)
        self.assertIn('quad(3) ==> 12', quad_prompt)
        self.assertIn('function four()', quad_prompt)
        self.assertIn('Text with {braces}', quad_prompt)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_rebuild_keeps_the_leading_accepted_units_as_tested_text(self):
        text = SHEET.replace('quad(1) ==> four()', 'quad(1) ==> 4')
        double = 'function double(x) { return x * 2; }  // "{kept}" \\ text'
        plain = SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1)
        self.assertEqual(SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1, keep={}), plain)
        src = SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1, keep={'unit_double': double},
                               keep_from='run abc')
        self.assertTrue(S.check(src)['ok'], S.check(src).get('errors'))
        self.assertNotIn('ask unit_double', src)
        self.assertIn('ask unit_quad', src)
        self.assertIn('assert test_double.passed because test_double.report.', src)
        self.assertIn('Units 1-1 are kept from an earlier build (run abc)', src)
        # only a leading run is kept: quad alone (double asked again) or a redo of double keeps nothing
        self.assertEqual(SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1,
                                          keep={'unit_quad': 'x'}), plain)
        self.assertEqual(SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1,
                                          keep={'unit_double': double}, redo=['double']), plain)
        asked = []

        class Quad:
            def call(self, req):
                asked.append(req['prompt'])
                return {'ok': True, 'text': js('function quad(x) { return double(double(x)); }'), 'model': 'a',
                        'node': 'n', 'ms': 1}
        rep = Run(src, applicators=Quad()).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(asked), 1)                               # only quad was asked
        self.assertIn(double, asked[0])                               # and saw the kept code exactly
        self.assertIn(double, rep['outputs'][-1]['text'])
        broken = SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1,
                                  keep={'unit_double': 'function double(x) { return x * 3; }'})
        rep = Run(broken, applicators=Quad()).execute()
        self.assertEqual(rep['status'], 'failed')                     # a kept unit that no longer passes stops it
        self.assertIn('examples failed', str(rep.get('error')))

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_diagnose_groups_a_runs_replies_by_their_first_failing_example(self):
        import hashlib
        import json
        import os
        import tempfile
        text = SHEET.replace('quad(1) ==> four()', 'quad(1) ==> 4')
        program = SP.compile_sheet(text, ['fake:a'], samples=1, retries=1, rounds=1)
        own = hashlib.sha256(program.encode('utf-8')).hexdigest()
        double = 'function double(x) { return x * 2; }'
        right, triple, once = ('function quad(x) { return double(double(x)); }', 'function quad(x) { return x * 3; }',
                               'function quad(x) { return double(x); }')

        def call(stmt, code, app='fake:a', sha=own):
            return {'stmt': stmt, 'source_sha256': sha, 'app': app, 'ok': True,
                    'reply': {'ok': True, 'text': js(code)}}
        calls = [call('unit_double', double), call('unit_quad', triple), call('unit_quad', triple, 'fake:b'),
                 call('unit_quad', once), call('unit_quad', right),
                 call('unit_quad', triple, sha='an older program'),               # merged cache: not this run's
                 {'stmt': 'unit_quad', 'source_sha256': own, 'app': 'fake:a', 'reply': {'ok': False}}]
        trace = [{'kind': 'ask', 'status': 'ok', 'name': 'unit_double', 'value': double[:5] + '…',
                  'hash': S.fingerprint(double)},
                 {'kind': 'ask', 'status': 'ok', 'name': 'unit_quad', 'value': right, 'hash': S.fingerprint(right)}]
        with tempfile.TemporaryDirectory() as folder:
            for name, body in (('program.sym', program), ('calls.jsonl', '\n'.join(json.dumps(c) for c in calls)),
                               ('trace.jsonl', '\n'.join(json.dumps(t) for t in trace))):
                with open(os.path.join(folder, name), 'w', encoding='utf-8') as fh:
                    fh.write(body)
            rows = SP.diagnose(text, folder)
            wider = SP.diagnose(text, folder, 'quad', everything=True)
        self.assertEqual([r['unit'] for r in rows], ['double(x)', 'quad(x)'])
        self.assertEqual((rows[0]['replies'], rows[0]['passed'], rows[0]['failures']), (1, 1, []))
        quad = rows[1]
        self.assertEqual((quad['replies'], quad['distinct'], quad['passed'], quad['accepted']), (4, 3, 1, True))
        self.assertEqual(len(quad['failures']), 1)                  # both wrong codes fail quad(1) first
        first = quad['failures'][0]
        self.assertEqual((first['example'], first['expected'], first['replies']), ('quad(1)', '4', 3))
        self.assertEqual([[what.split()[-1], n] for what, n in first['got']], [['3', 2], ['2', 1]])
        self.assertEqual(first['models'], {'fake:a': 2, 'fake:b': 1})
        self.assertEqual(len(wider), 1)
        self.assertEqual((wider[0]['replies'], wider[0]['failures'][0]['replies']), (5, 4))


if __name__ == '__main__':
    unittest.main()

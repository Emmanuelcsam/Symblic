"""Determinism receipts on every run (items D1-D5 of the development plan that introduced them).

D1  every executed ask says whether the kernel determined it over a finite declared domain (determined,
    underdetermined, contradictory) or why it was not assessed;
D2  `solve=auto` (the existing `solve` behaviour, named) lets the kernel answer a determined ask with no model
    call; the default stays model construction;
D3  the passing Code candidates of a checked search are grouped by what their declared tests returned, labelled
    declared_tests_only (no claim about other inputs);
D4  calls.jsonl keeps each reply's raw model_identity and usage; identities are re-validated with
    symblic.providers.ollama_call.check, only an observed validated sha256 digest pins, and a call whose digest differs from
    the folder's pin is recorded (default) or refused (model_pins=strict), across resumes too;
D5  an escalated ask says which rung answered, whether it was local, and what cloud calls it charged.

Report keys: the determinism report schema, version 1 (ReportSchema validates a real report against them),
including its "D4 host policy" section (model_pins: observe or strict, validated before anything runs).
Fake applicators and temporary folders only: no model, provider or network.
The Code tests run the local sandboxed JavaScript adapter and are skipped without node."""

import io
import json
import os
import re
import signal
import stat
import sys
import tempfile
import threading
import types
import unittest
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.providers import ollama_call as boc  # noqa: E402
from symblic.kernel import language as S  # noqa: E402
from symblic.js import check as J  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

NODE = J.available()
SHA = 'c' * 64                     # the observer's sha256, as the caller fixed it before the call
NONCE = 'd' * 32
MODEL = 'qwen3:4b-instruct'
LOCAL = 'ollama:qwen3:4b-instruct@node-a'
DIGEST_A, DIGEST_B = 'sha256:' + 'a' * 64, 'sha256:' + 'b' * 64
HEX64 = re.compile(r'[0-9a-f]{64}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
USAGE = {'input_tokens': 10, 'output_tokens': 2}
MISSING = object()


def observed(digest, model=MODEL, node='node-a'):
    """A model_identity record the provider helper itself makes for one call: the same listing before and after."""
    side = {'at_ms': 1, 'name': model, 'digest': digest, 'error': None}
    observation = {'version': boc.VERSION, 'model': model, 'nonce': NONCE, 'before': side,
                   'after': {**side, 'at_ms': 2}, 'response_model': model}
    record = boc.identity(observation, model, node, observer_sha256=SHA, nonce=NONCE)
    assert record['status'] == 'observed', record
    return record


def listing_changed(model=MODEL, node='node-a'):
    """The helper's own 'drift' status: the listing changed during the call (no digest)."""
    before = {'at_ms': 1, 'name': model, 'digest': DIGEST_A, 'error': None}
    observation = {'version': boc.VERSION, 'model': model, 'nonce': NONCE, 'before': before,
                   'after': {**before, 'at_ms': 2, 'digest': DIGEST_B}, 'response_model': model}
    record = boc.identity(observation, model, node, observer_sha256=SHA, nonce=NONCE)
    assert record['status'] == 'drift' and record['digest'] is None, record
    return record


def unavailable(model=MODEL, node='node-a'):
    return boc.unavailable('ollama', model, 'not_observed', node)


def forged(digest=DIGEST_A):
    """An observed record whose digest was edited afterwards: the helper cannot rebuild it."""
    return {**observed(digest), 'digest': DIGEST_B if digest == DIGEST_A else DIGEST_A}


def reply(answer, identity=MISSING, usage=MISSING, **extra):
    out = {'ok': True, 'json': {'answer': answer}, 'model': MODEL, 'node': 'node-a', 'ms': 1, **extra}
    if identity is not MISSING:
        out['model_identity'] = identity
    if usage is not MISSING:
        out['usage'] = usage
    return out


class Models:
    """answer(label, request, n) -> the reply dict for the n-th call (1-based). Keeps every request."""

    def __init__(self, answer):
        self.answer, self.requests, self.lock = answer, [], threading.Lock()

    def call(self, req):
        with self.lock:
            self.requests.append(req)
            n = len(self.requests)
        return dict(self.answer(S.app_label(req['app']), req, n))


def execute(src, answer, folder=None, **options):
    apps = Models(answer)
    run = SR.Run(src, None, apps, options, folder=folder)
    return run, run.execute(), apps


def rows_of(run, kind):
    return [r for r in run.trace if r['kind'] == kind]


def calls_rows(folder):
    return SR._read_jsonl(os.path.join(folder, 'calls.jsonl'))


def folder_state(folder):
    out = {}
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            path = os.path.join(root, name)
            with open(path, 'rb') as stream:
                out[os.path.relpath(path, folder)] = (stream.read(), os.stat(path).st_mtime_ns)
    return out


def tree_state(folder):
    """Everything a write can change under `folder`, the folder itself included ('.'): every directory (an empty
    artifacts/ too) and file with its kind, mode, size and mtime_ns, a file's bytes, a link's target. None when the
    folder does not exist, so a refusal that must create nothing is told apart from one that changed nothing."""
    if not os.path.lexists(folder):
        return None

    def entry(path):
        st = os.lstat(path)
        if stat.S_ISREG(st.st_mode):
            with open(path, 'rb') as stream:
                content = stream.read()
        else:
            content = os.readlink(path) if stat.S_ISLNK(st.st_mode) else None
        return stat.S_IFMT(st.st_mode), stat.S_IMODE(st.st_mode), st.st_size, st.st_mtime_ns, content

    out = {'.': entry(folder)}
    for root, dirs, files in os.walk(folder):
        for name in sorted(dirs) + sorted(files):
            path = os.path.join(root, name)
            out[os.path.relpath(path, folder)] = entry(path)
    return out


BROKEN_AT_IMPORT = 'raise RuntimeError("half-deployed helper")\n'
BROKEN_ATTRIBUTES = 'def __getattr__(name):\n    raise RuntimeError("half-deployed helper: " + name)\n'


HELPER = 'symblic.providers.ollama_call'


class _BrokenHelperFinder:
    """Imports HELPER from `body` instead of the real file (a half-deployed helper)."""

    def __init__(self, body):
        self.body = body

    def find_spec(self, name, path=None, target=None):
        if name != HELPER:
            return None
        import importlib.util
        return importlib.util.spec_from_loader(name, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(compile(self.body, '<broken ollama_call>', 'exec'), module.__dict__)  # noqa: S102


@contextmanager
def broken_helper(body=BROKEN_AT_IMPORT):
    """The observer module present but failing (at import, or on reading its attributes); the real module is out
    of sys.modules until the block ends. Importing the broken copy also sets it as an attribute of the package
    (symblic.providers.ollama_call), so that attribute is restored too: nothing broken outlives the block."""
    import symblic.providers as package
    real = package.__dict__.get('ollama_call', MISSING)
    try:
        with mock.patch.dict(sys.modules), \
                mock.patch.object(sys, 'meta_path', [_BrokenHelperFinder(body)] + sys.meta_path):
            sys.modules.pop(HELPER, None)
            yield
    finally:
        if real is MISSING:
            package.__dict__.pop('ollama_call', None)
        else:
            package.ollama_call = real


# --------------------------------------------------------------------------------------------------------- D1, D2

DETERMINED = ('let total = 10.\n'
              'ask x: Int in 0..20 "How many?" by "fake:a" with effort=low{solve}\n'
              'let twice = x * 2.\n'
              'ensure twice + 2 = total else retry.\n')


class Determinacy(unittest.TestCase):
    def test_a_determined_ask_reports_its_unique_value_domain_checks_and_cost(self):
        run, rep, apps = execute(DETERMINED.format(solve=', solve=auto'), lambda *_: reply(7))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(apps.requests, [])                                   # the kernel answered
        entry, = rep['determinacy']['asks']
        self.assertEqual(entry['status'], 'determined')
        self.assertEqual((entry['line'], entry['name']), (2, 'x'))
        self.assertEqual(entry['domain'], {'kind': 'int_range', 'size': 21})
        self.assertIs(entry['exhaustive'], True)
        self.assertEqual(entry['method'], 'enumeration')
        self.assertEqual((entry['passing'], entry['passing_count'], entry['passing_truncated']), (['4'], 1, False))
        self.assertEqual((entry['checks'], entry['checks_truncated']), ([4], False))
        self.assertGreater(entry['cost']['steps'], 0)
        self.assertEqual((entry['answered_by'], entry['solve_mode']), ('kernel', 'auto'))
        self.assertNotIn('reason', entry)
        row, = rows_of(run, 'determinacy')
        self.assertEqual({k: row[k] for k in ('line', 'name', 'status', 'method', 'exhaustive', 'passing_count',
                                              'reason')},
                         {'line': 2, 'name': 'x', 'status': 'determined', 'method': 'enumeration',
                          'exhaustive': True, 'passing_count': 1, 'reason': None})
        self.assertEqual(rep['determinacy']['summary'],
                         {'determined': 1, 'underdetermined': 0, 'contradictory': 0, 'unassessed': 0})
        self.assertIs(rep['determinacy']['asks_truncated'], False)

    def test_several_passing_values_are_listed_bounded_and_the_model_still_answers(self):
        src = 'ask y: Int in 0..20 "Pick one above 17." by "fake:a" with effort=low, solve=auto\nensure y > 17 else retry.\n'
        run, rep, apps = execute(src, lambda *_: reply(19))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.requests), 1)
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['passing'], entry['passing_count']),
                         ('underdetermined', ['18', '19', '20'], 3))
        self.assertEqual((entry['answered_by'], entry['solve_mode']), ('model', 'auto'))

    def test_a_partial_enumeration_is_never_a_count(self):
        src = 'ask z: Int in 0..200 "Pick." by "fake:a" with effort=low\nensure z > 3 else retry.\n'
        _run, rep, _apps = execute(src, lambda *_: reply(10))
        entry, = rep['determinacy']['asks']
        self.assertEqual(entry['status'], 'underdetermined')        # two witnesses suffice for that
        self.assertIs(entry['exhaustive'], False)
        self.assertIsNone(entry['passing_count'])
        self.assertEqual(entry['passing'], [str(n) for n in range(4, 24)])
        self.assertIs(entry['passing_truncated'], True)
        self.assertEqual(entry['domain'], {'kind': 'int_range', 'size': 201})

    def test_a_contradictory_ask_fails_before_any_call_and_is_not_underdetermined(self):
        src = 'ask k: Int in 0..5 "?" by "fake:a" with effort=low, solve=auto\nensure k > 9 else retry.\n'
        _run, rep, apps = execute(src, lambda *_: reply(1))
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'contradictory'))
        self.assertEqual(apps.requests, [])
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['passing'], entry['passing_count'], entry['exhaustive']),
                         ('contradictory', [], 0, True))
        self.assertIsNone(entry['answered_by'])
        self.assertEqual(rep['determinacy']['summary']['contradictory'], 1)
        self.assertEqual(rep['determinism_summary']['unanswered'], 1)

    def test_every_unassessed_ask_says_why(self):
        cases = {
            'no_finite_domain': ('ask t: Text "Say hi." by "fake:a" with effort=low\n', 'hi'),
            'over_limit': ('ask n: Int in 0..30000 "n" by "fake:a" with effort=low\nensure n > 3 else retry.\n', 5),
            'no_anchored_checks': ('ask b: Bool "b?" by "fake:a" with effort=low\n', True),
            'unsupported_check': ('function big(v: Int) -> Bool = v > 2.\n'
                                  'ask u: Int in 1..5 "u" by "fake:a" with effort=low\nensure big(u) else retry.\n', 3),
        }
        for reason, (src, answer) in cases.items():
            with self.subTest(reason=reason):
                run, rep, _apps = execute(src, lambda *_a, answer=answer: reply(answer))
                self.assertEqual(rep['status'], 'done', rep.get('error'))
                entry, = rep['determinacy']['asks']
                self.assertEqual((entry['status'], entry['reason'], entry['answered_by']),
                                 ('unassessed', reason, 'model'))
                self.assertNotIn('passing', entry)
                row, = rows_of(run, 'determinacy')
                self.assertEqual((row['status'], row['reason'], row['method'], row['exhaustive'],
                                  row['passing_count']), ('unassessed', reason, None, None, None))

    def test_for_each_items_are_one_entry_each_in_item_order(self):
        src = ('ask e: Bool "is {it} big?" for each it in [1, 2] by "fake:a" with effort=low\n'
               'ensure len(e) = 2 else retry.\n')
        run, rep, _apps = execute(src, lambda *_: reply(True))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        entries = rep['determinacy']['asks']
        self.assertEqual([(e['index'], e['status'], e['reason'], e['answered_by']) for e in entries],
                         [(1, 'unassessed', 'not_attempted', 'model'), (2, 'unassessed', 'not_attempted', 'model')])
        self.assertEqual([r['index'] for r in rows_of(run, 'determinacy')], [1, 2])
        sequences = [r['sequence'] for r in run.trace]
        self.assertEqual(len(sequences), len(set(sequences)))

    def test_a_budget_stop_is_unassessed_never_uniqueness(self):
        src = 'ask x:Int in 1..100 "x" by "kernel" with solve=true\nensure x > 0 else retry.\n'
        run = SR.Run(src, options={'max_steps': 12})
        rep = run.execute()
        self.assertEqual(rep['status'], 'failed')
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['reason'], entry['answered_by']), ('unassessed', 'budget', None))

    def test_an_ensure_retry_rolls_back_the_rejected_executions_record_but_the_trace_keeps_it(self):
        src = ('function big(v: Int) -> Bool = v > 2.\n'
               'ask u: Int in 1..5 "u" by "fake:a" with effort=low, retries=2\nensure big(u) else retry.\n')
        run, rep, apps = execute(src, lambda _l, _r, n: reply(1 if n == 1 else 3))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(len(rep['determinacy']['asks']), 1)
        self.assertEqual(len(rows_of(run, 'determinacy')), 2)
        self.assertEqual(rep['determinism_summary']['answered_by_model'], 1)
        # each execution keeps its own occurrence number: the trace's rows of the rejected one stay distinguishable
        self.assertEqual([r['occurrence'] for r in rows_of(run, 'determinacy')], [1, 2])
        self.assertEqual(rep['determinacy']['asks'][0]['occurrence'], 2)

    def test_an_ask_that_fails_before_its_assessment_still_has_its_trace_row(self):
        # review m1: a single ask failing on its options (before determine) said so in the report but not the trace
        run, rep, apps = execute('ask x: Int in 0..5 "?" by "fake:a" with effort=bogus\nensure x > 1 else retry.\n',
                                 lambda *_: reply(3))
        self.assertEqual((rep['status'], apps.requests), ('failed', []))
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['reason'], entry['answered_by']), ('unassessed', 'not_attempted', None))
        row, = rows_of(run, 'determinacy')
        self.assertEqual((row['line'], row['name'], row['status'], row['reason'], row['occurrence']),
                         (1, 'x', 'unassessed', 'not_attempted', 1))

    def test_repeated_executions_of_one_ask_are_told_apart(self):
        # review m2: a statement-level loop (or a routine) executes one ask several times; same line and name
        run, rep, _apps = execute('for v in [1, 2] do\n  ask q: Bool "is {v} big?" by "fake:a" with effort=low\nend.\n',
                                  lambda *_: reply(True))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual([(e['line'], e['name'], e['occurrence']) for e in rep['determinacy']['asks']],
                         [(2, 'q', 1), (2, 'q', 2)])
        self.assertEqual([r['occurrence'] for r in rows_of(run, 'determinacy')], [1, 2])
        self.assertEqual([r['occurrence'] for r in rows_of(run, 'ask')], [1, 2])
        src = ('for v in [1, 2] do\n'
               '  ask e: Bool "is {it} below {v}?" for each it in [1, 2] by "fake:a" with effort=low\nend.\n')
        run, rep, _apps = execute(src, lambda *_: reply(True))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual([(e['occurrence'], e['index']) for e in rep['determinacy']['asks']],
                         [(1, 1), (1, 2), (2, 1), (2, 2)])
        self.assertEqual([(r['occurrence'], r['index']) for r in rows_of(run, 'determinacy')],
                         [(1, 1), (1, 2), (2, 1), (2, 2)])

    def test_receipt_rows_are_not_work_a_kernel_change_would_refuse(self):
        # an ask that failed before any call leaves only its determinacy row: as before that row existed, the folder
        # holds no work, so a deployment with another kernel may start it (language-1's gate is unchanged)
        src = 'ask x: Int in 0..5 "?" by "kernel"\n'
        with tempfile.TemporaryDirectory() as folder:
            other = {**S.kernel_id(), 'lang': '2.4', 'id': '0b2cca3828a1965a'}
            with mock.patch.object(S, 'kernel_id', return_value=other):
                rep = SR.Run(src, folder=folder).execute()
            self.assertEqual(rep['status'], 'failed')
            kinds = [r['kind'] for r in SR._read_jsonl(os.path.join(folder, 'trace.jsonl'))]
            self.assertEqual(kinds, ['determinacy'])
            gate = SR.kernel_gate(folder)
            self.assertEqual((gate['decision'], gate['statements']), ('fresh', 0))
            self.assertNotIn('kernel_check', SR.Run(src, folder=folder).execute())

    def test_existing_results_do_not_change(self):
        src = ('let total = 10.\n'
               'ask x: Int in 0..20 "How many?" with effort=low, solve\n'
               'let twice = x * 2.\n'
               'ensure twice + 2 = total else retry.\n'
               'ask y: Int in 0..20 "Pick one above 3." with effort=low\n'
               'ensure y > 3 else retry.\n')
        _run, rep, apps = execute(src, lambda *_: reply(7), by='fake:a')
        got = {b['name']: b for b in rep['bindings']}
        self.assertEqual((got['x']['value'], got['y']['value']), (4, 7))
        self.assertTrue(got['x']['meta']['solved_by_kernel'])
        self.assertEqual(got['x']['meta']['determination']['verdict'], 'determined')
        self.assertEqual(got['y']['meta']['determination']['verdict'], 'underdetermined')
        self.assertEqual((rep['calls'], len(apps.requests)), (1, 1))
        self.assertEqual([d['verdict'] for d in rep['evidence']['determinations']], ['determined', 'underdetermined'])
        self.assertEqual([e['solve_mode'] for e in rep['determinacy']['asks']], ['on', 'off'])


class SolveAuto(unittest.TestCase):
    def test_the_default_is_model_construction_even_when_determined(self):
        _run, rep, apps = execute(DETERMINED.format(solve=''), lambda *_: reply(4))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.requests), 1)
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['answered_by'], entry['solve_mode']), ('determined', 'model', 'off'))

    def test_use_solve_auto_is_a_program_default_and_true_reads_on(self):
        _run, rep, apps = execute('use solve=auto.\n' + DETERMINED.format(solve=''), lambda *_: reply(9))
        self.assertEqual((rep['status'], len(apps.requests)), ('done', 0))
        self.assertEqual(next(b['value'] for b in rep['bindings'] if b['name'] == 'x'), 4)
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['answered_by'], entry['solve_mode']), ('kernel', 'auto'))
        _run, rep, apps = execute(DETERMINED.format(solve=', solve=true'), lambda *_: reply(9))
        self.assertEqual(len(apps.requests), 0)
        self.assertEqual(rep['determinacy']['asks'][0]['solve_mode'], 'on')
        self.assertEqual(rep['determinism_summary']['answered_by_kernel'], 1)

    def test_auto_sends_what_the_kernel_cannot_decide_to_the_models(self):
        _run, rep, apps = execute('ask t: Text "Say hi." by "fake:a" with solve=auto\n', lambda *_: reply('hi'))
        self.assertEqual((rep['status'], len(apps.requests)), ('done', 1))
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['reason'], entry['answered_by'], entry['solve_mode']),
                         ('unassessed', 'no_finite_domain', 'model', 'auto'))

    def test_a_kernel_only_underdetermined_ask_still_fails_and_answered_nothing(self):
        src = 'ask x:Int in 1..3 "pick" by kernel with solve=true\nensure x>1 else retry.\n'
        rep = SR.Run(src).execute()
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'underdetermined'))
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['status'], entry['passing'], entry['answered_by']), ('underdetermined', ['2', '3'], None))

    def test_the_ask_trace_row_says_who_answered(self):
        run, _rep, _apps = execute(DETERMINED.format(solve=', solve=auto'), lambda *_: reply(4))
        row, = [r for r in run.trace if r['kind'] == 'ask']
        self.assertEqual((row['answered_by'], row['solve_mode']), ('kernel', 'auto'))

    def test_an_answer_its_anchored_check_finally_rejects_was_not_answered(self):
        # review m3: on the vote route the ensure runs after the binding; with no retry left the run fails, and the
        # rejected answer was never accepted (answered_by null), as on route=escalate
        src = 'ask x: Int in 0..9 "x" by "fake:a" with effort=low, retries=0\nensure x = 7 else retry.\n'
        _run, rep, apps = execute(src, lambda *_: reply(3))
        self.assertEqual((rep['status'], rep['error']['kind'], len(apps.requests)), ('failed', 'check', 1))
        entry, = rep['determinacy']['asks']
        self.assertEqual((entry['answered_by'], entry['rejected_by_check']), (None, True))
        summary = rep['determinism_summary']
        self.assertEqual((summary['answered_by_model'], summary['unanswered']), (0, 1))
        _run, rep, _apps = execute(src, lambda *_: reply(7))                   # accepted: no such mark
        self.assertNotIn('rejected_by_check', rep['determinacy']['asks'][0])
        self.assertEqual(rep['determinacy']['asks'][0]['answered_by'], 'model')


# ------------------------------------------------------------------------------------------------------------- D3

def js(code):
    return 'Here it is:\n```js\n' + code + '\n```'


class Replies:
    """Code replies by model name, with optional delays; keeps every request."""

    def __init__(self, answers, delays=None):
        self.answers, self.delays, self.requests, self.lock = answers, delays or {}, [], threading.Lock()

    def call(self, req):
        import time
        name = req['app']['model'] or req['app']['engine']
        with self.lock:
            self.requests.append(dict(req))
            n = sum(1 for r in self.requests if (r['app']['model'] or r['app']['engine']) == name)
        time.sleep(self.delays.get(name, 0))
        seq = self.answers[name]
        return {'ok': True, 'text': seq[min(n - 1, len(seq) - 1)], 'json': None, 'model': name, 'node': 'n', 'ms': 1}


@unittest.skipUnless(NODE, 'node is not installed')
class CodeBehavior(unittest.TestCase):
    TESTED = ('program P.\nuse by=["fake:a", "fake:b", "fake:c"].\n'
              'ask add: Code js "Write add(a, b)." with route=search, retries=0\n'
              'let t = js_test(add, [["add(2, 3)", "5"], ["add(1, 1)", "2"]]).\n'
              'ensure t.passed else retry because t.report.\nshow add.\n')
    LOOSE = ('program P.\nuse by=["fake:a", "fake:b"].\n'
             'ask add: Code js "Write add(a, b)." with route=search, retries=0\n'
             'let r = js_run(add, "add(2, 3)").\nensure r >= 5 else retry.\nshow add.\n')
    PLUS = js('function add(a,b){return a+b}')
    SWAPPED = js('function add(x, y) {\n  return y + x;\n}')
    LOOP = js('function add(a,b){let s=a; for(let i=0;i<b;i++){s++} return s}')
    BAD = js('function add(a,b){return a-b}')

    def run_(self, src, answers, delays):
        apps = Replies(answers, delays)
        rep = SR.Run(src, applicators=apps, options={'parallel': 3}).execute()
        return rep, apps

    def test_passing_sources_that_differ_agree_on_the_declared_tests_only(self):
        rep, _apps = self.run_(self.TESTED, {'a': [self.PLUS], 'b': [self.SWAPPED], 'c': [self.LOOP]},
                               {'a': 0.4, 'b': 0.01, 'c': 0.01})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['line'], entry['name'], entry['scope']), (3, 'add', 'declared_tests_only'))
        self.assertEqual(entry['tests']['count'], 2)
        self.assertRegex(entry['tests']['sha256'], HEX64)
        self.assertEqual((entry['candidates'], entry['passing'], entry['status']), (3, 3, 'agreed_on_declared'))
        group, = entry['groups']
        self.assertEqual((group['members'], group['members_truncated']), ([0, 1, 2], False))
        self.assertRegex(group['vector_sha256'], HEX64)
        self.assertIsNone(entry['covered_by'])
        self.assertEqual(rep['determinism_summary']['behavior_scope'], 'declared_tests_only')

    def test_outputs_a_loose_check_admits_are_told_apart(self):
        six = js('function add(a,b){return a+b+1}')
        rep, _apps = self.run_(self.LOOSE, {'a': [self.PLUS], 'b': [six]}, {'a': 0.4, 'b': 0.01})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['passing'], entry['status'], entry['tests']['count']), (2, 'differs_on_declared', 1))
        self.assertEqual(sorted(g['members'] for g in entry['groups']), [[0], [1]])
        selected = next(b for b in rep['bindings'] if b['name'] == 'add')
        self.assertEqual(selected['meta']['selected'], 'fake:a')           # selection unchanged: the lowest index

    def test_one_and_no_passing_candidate(self):
        rep, _apps = self.run_(self.TESTED, {'a': [self.PLUS], 'b': [self.BAD], 'c': [self.BAD]},
                               {'a': 0.01, 'b': 0.3, 'c': 0.3})
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['passing'], entry['status'], [g['members'] for g in entry['groups']]),
                         (1, 'single', [[0]]))
        rep, _apps = self.run_(self.TESTED, {'a': [self.BAD], 'b': [self.BAD], 'c': [self.BAD]}, {})
        self.assertEqual(rep['status'], 'failed')
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['candidates'], entry['passing'], entry['status'], entry['groups']), (3, 0, 'none', []))

    DECLARED = ('program P.\nuse by=["fake:a", "fake:b"].\n'
                'ask add: Code js "Write add(a, b)." with route=search, retries=0\n'
                'let d = js_declarations_check(add, {version: 1, exports: {add: "function"}}).\n'
                'ensure d.passed else retry because d.report.\n'
                'let t = js_test(add, [["add(2, 3)", "5"], ["add(1, 1)", "2"]]).\n'
                'ensure t.passed else retry because t.report.\nshow add.\n')

    def test_declaration_checks_compare_behaviour_never_the_source_text(self):
        # review M1: js_declarations_check returns the candidate's source hash and declaration positions; two
        # candidates that behave the same but are written differently must not be told apart by them
        rep, _apps = self.run_(self.DECLARED, {'a': [self.PLUS], 'b': [self.SWAPPED]}, {'a': 0.4, 'b': 0.01})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['passing'], entry['status'], entry['tests']['count']), (2, 'agreed_on_declared', 3))
        self.assertEqual([g['members'] for g in entry['groups']], [[0, 1]])
        # a different declared surface is behaviour: told apart, while both still pass their own (loose) check
        loose = self.DECLARED.replace('ensure d.passed else retry because d.report.\n', '')
        other = js('function add(a,b){return a+b}\nfunction helper(){return 0}')
        rep, _apps = self.run_(loose, {'a': [self.PLUS], 'b': [other]}, {'a': 0.4, 'b': 0.01})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['passing'], entry['status']), (2, 'differs_on_declared'))

    def test_results_that_do_not_say_what_each_candidate_did_are_not_grouped(self):
        # a passing candidate whose js_test failed some cases (a loose check): which cases, and what it returned, is
        # not in the result, so agreement is not measured (never claimed); the ask says so
        src = ('program P.\nuse by=["fake:a", "fake:b"].\n'
               'ask add: Code js "Write add(a, b)." with route=search, retries=0\n'
               'let t = js_test(add, [["add(2, 3)", "5"], ["add(1, 1)", "2"]]).\n'
               'ensure t.failed <= 1 else retry because t.report.\nshow add.\n')
        first = js('function add(a,b){return a===2 ? 5 : 0}')                # fails the second case
        second = js('function add(a,b){return a===1 ? 2 : 0}')               # fails the first case
        rep, _apps = self.run_(src, {'a': [first], 'b': [second]}, {'a': 0.4, 'b': 0.01})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        entry, = rep['code_behavior']['asks']
        self.assertEqual((entry['passing'], entry['status'], entry['groups'], entry['unmeasured_adapters']),
                         (2, 'unmeasured', [], ['js_test']))


class CodeBehaviorProjection(unittest.TestCase):
    """The per-adapter behaviour projection, without node: what is compared, and what is never."""

    def observe(self, name, out, args=('SOURCE', 'test')):
        return SR._adapter_observation(name, args, {}, out)

    def test_source_derived_provenance_never_reaches_the_vector(self):
        surface = {'passed': True, 'status': 'accepted', 'truncated': False, 'diagnostics': (),
                   'declarations': ({'name': 'add', 'kind': 'function', 'line': 1, 'column': 10},),
                   'source_sha256': 'a' * 64, 'report': 'accepted', 'runtime': {'node': 'v22'}}
        moved = {**surface, 'source_sha256': 'b' * 64, 'runtime': {'node': 'v24'},
                 'declarations': ({'name': 'add', 'kind': 'function', 'line': 3, 'column': 1},)}
        self.assertEqual(self.observe('js_declarations_check', surface)['behavior'],
                         self.observe('js_declarations_check', moved)['behavior'])
        renamed = {**surface, 'declarations': ({'name': 'sum', 'kind': 'function', 'line': 1, 'column': 10},)}
        self.assertNotEqual(self.observe('js_declarations_check', surface)['behavior'],
                            self.observe('js_declarations_check', renamed)['behavior'])
        passed = {'passed': True, 'total': 2, 'failed': 0, 'report': 'All 2 examples passed.'}
        self.assertEqual(self.observe('js_test', passed)['behavior'],
                         self.observe('js_test', {**passed, 'report': 'other text'})['behavior'])
        self.assertIsNone(self.observe('js_test', {'passed': False, 'total': 2, 'failed': 1, 'report': 'x'})['behavior'])
        self.assertNotEqual(self.observe('js_run', 5)['behavior'], self.observe('js_run', 6)['behavior'])
        self.assertIsNone(self.observe('js_future_adapter', {'passed': True})['behavior'])   # unknown: not projected

    def test_an_unknown_adapter_excludes_the_ask_from_grouping(self):
        seen = [self.observe('js_future_adapter', {'passed': True})]
        entry = SR._code_behavior(S.Node('ask', 3, 0, name='add'), {0: (True, seen), 1: (True, list(seen))})
        self.assertEqual((entry['status'], entry['groups'], entry['unmeasured_adapters']),
                         ('unmeasured', [], ['js_future_adapter']))
        entry = SR._code_behavior(S.Node('ask', 3, 0, name='add'), {0: (True, seen), 1: (False, [])})
        self.assertEqual(entry['status'], 'single')                       # one passing: agreement not measured


# ------------------------------------------------------------------------------------------------------------- D4

TWO = ('ask a: Int "First number?" by "ollama:qwen3:4b-instruct@node-a" with effort=low\n'
       'ask b: Int "Second number?" by "ollama:qwen3:4b-instruct@node-a" with effort=low\n'
       'show a + b.\n')


def identities(*records, usage=USAGE):
    """Call n answers n with records[n-1] (the last repeats); MISSING sends no identity."""
    def answer(_label, _req, n):
        return reply(n, records[min(n, len(records)) - 1], usage)
    return answer


def hidden_helper():
    return mock.patch.dict(sys.modules, {HELPER: None})


class ModelIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='symblic-lane-c-')
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_calls_rows_keep_the_raw_record_usage_and_a_check_label(self):
        _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        rows = calls_rows(self.folder)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row['model_identity_raw'], observed(DIGEST_A))
            self.assertNotIn('model_identity_raw_truncated', row)
            self.assertEqual(row['usage'], USAGE)
            self.assertEqual(row['identity_check_at_call'],
                             {'checker': 'symblic.providers.ollama_call.check', 'checker_version': boc.VERSION,
                              'validated': True, 'pinned': True, 'strict': False, 'refused': False})
        block = rep['model_identity']
        self.assertEqual((block['version'], block['basis'], block['strict']), (1, 'recorded_at_report', False))
        self.assertEqual(block['checker'], {'available': True, 'version': boc.VERSION})
        self.assertIsInstance(block['computed_at'], float)
        self.assertEqual(block['applicators'], {LOCAL: {
            'pinned': DIGEST_A, 'digests': {DIGEST_A: 2}, 'digests_truncated': False,
            'statuses': {'observed': 2, 'drift': 0, 'unavailable': 0, 'invalid': 0, 'unverifiable': 0}}})
        self.assertEqual((block['drift'], block['drift_truncated'], block['applicators_truncated']), ([], False, False))

    def test_only_an_observed_validated_digest_pins(self):
        src = ''.join(f'ask q{i}: Int "Number {i}?" by "{LOCAL}" with effort=low\n' for i in range(5))
        _run, rep, _apps = execute(src, identities(unavailable(), forged(), listing_changed(), observed(DIGEST_B),
                                                   MISSING), folder=self.folder)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        app = rep['model_identity']['applicators'][LOCAL]
        self.assertEqual(app['statuses'], {'observed': 1, 'drift': 1, 'unavailable': 1, 'invalid': 1, 'unverifiable': 0})
        self.assertEqual((app['pinned'], app['digests']), (DIGEST_B, {DIGEST_B: 1}))
        self.assertEqual(rep['model_identity']['drift'], [])                # none of the others counts as drift
        labels = [r.get('identity_check_at_call') for r in calls_rows(self.folder)]
        self.assertEqual([(x['validated'], x['pinned']) for x in labels[:4]],
                         [(True, False), (False, False), (True, False), (True, True)])
        self.assertIsNone(labels[4])                                       # no record, no label
        self.assertNotIn('model_identity_raw', calls_rows(self.folder)[4])

    def test_a_changed_digest_is_recorded_in_the_trace_and_the_report_by_default(self):
        run, rep, _apps = execute(TWO, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=self.folder)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(rep['model_identity']['drift'], [{'line': 2, 'applicator': LOCAL, 'pinned': DIGEST_A,
                                                           'observed': DIGEST_B, 'cached': False,
                                                           'action': 'recorded'}])
        row, = rows_of(run, 'model-drift')
        self.assertEqual((row['line'], row['status'], row['applicator'], row['pinned'], row['observed'], row['cached']),
                         (2, 'recorded', LOCAL, DIGEST_A, DIGEST_B, False))
        app = rep['model_identity']['applicators'][LOCAL]
        self.assertEqual((app['pinned'], app['digests']), (DIGEST_A, {DIGEST_A: 1, DIGEST_B: 1}))
        self.assertEqual(calls_rows(self.folder)[1]['identity_check_at_call']['pinned'], False)
        self.assertEqual(rep['determinism_summary']['drift_events'], 1)

    def test_strict_pins_refuse_a_changed_digest_before_it_is_accepted_or_cached(self):
        run, rep, apps = execute(TWO, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=self.folder,
                                 model_pins='strict')
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('model_pins=strict', rep['error']['message'])
        self.assertEqual(len(apps.requests), 2)                             # b was asked once, never again
        rows = calls_rows(self.folder)
        self.assertEqual([r['ok'] for r in rows], [True, False])
        self.assertTrue(rows[1]['identity_check_at_call']['refused'])
        self.assertNotIn('json', rows[1]['reply'])                          # the refused answer is not kept
        self.assertEqual(len(SR.Store(self.folder).calls), 1)               # nothing a resume could reuse
        self.assertEqual(rep['model_identity']['drift'][0]['action'], 'refused')
        self.assertTrue(rep['model_identity']['strict'])
        self.assertEqual(rows_of(run, 'model-drift')[0]['status'], 'refused')

    def test_without_the_helper_identities_are_unverifiable_never_pin_and_strict_refuses(self):
        with hidden_helper():
            _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=self.folder)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        block = rep['model_identity']
        self.assertEqual(block['checker'], {'available': False, 'version': None})
        app = block['applicators'][LOCAL]
        self.assertEqual((app['pinned'], app['statuses']['unverifiable'], app['digests']), (None, 2, {}))
        self.assertEqual(block['drift'], [])
        self.assertEqual(calls_rows(self.folder)[0]['identity_check_at_call'],
                         {'checker': 'symblic.providers.ollama_call.check', 'checker_version': None, 'validated': False,
                          'pinned': False, 'strict': False, 'refused': False})
        self.assertEqual(rep['determinism_summary']['identity_unverifiable'], 2)
        with hidden_helper(), tempfile.TemporaryDirectory() as other:
            _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=other, model_pins='strict')
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('unverifiable', rep['error']['message'])
        self.assertEqual(len(apps.requests), 1)

    def test_strict_pins_refuse_an_answer_that_carries_no_identity_record(self):
        run, rep, apps = execute(TWO, identities(MISSING), folder=self.folder, model_pins='strict')
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('carries no model identity record', rep['error']['message'])
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual([r['ok'] for r in calls_rows(self.folder)], [False])
        row, = rows_of(run, 'model-identity')
        self.assertEqual((row['status'], row['applicator'], row['identity']), ('refused', LOCAL, None))
        _run, rep, _apps = execute(TWO, identities(MISSING))                  # default: recorded as it was
        self.assertEqual((rep['status'], rep['model_identity']['applicators']), ('done', {}))

    def test_hostile_records_and_a_failing_checker_never_validate_or_crash(self):
        deep = cursor = {}
        for _ in range(5000):
            cursor['x'] = {}
            cursor = cursor['x']
        nan = {**observed(DIGEST_A), 'version': float('nan')}
        src = ''.join(f'ask q{i}: Int "Number {i}?" by "{LOCAL}" with effort=low\n' for i in range(4))
        _run, rep, _apps = execute(src, identities(deep, ['not', 'a', 'record'], 'observed', nan), folder=self.folder)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        app = rep['model_identity']['applicators'][LOCAL]
        self.assertEqual((app['statuses']['invalid'], app['pinned']), (4, None))
        rows = calls_rows(self.folder)
        self.assertIsInstance(rows[0]['model_identity_raw'], str)          # too deep for JSON: described, not kept
        self.assertEqual(rows[1]['model_identity_raw'], ['not', 'a', 'record'])
        self.assertIsInstance(rows[3]['model_identity_raw'], str)          # NaN is not JSON
        with mock.patch.object(boc, 'check', side_effect=RuntimeError('broken checker')):
            _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A)))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(rep['model_identity']['applicators'][LOCAL]['statuses']['invalid'], 2)

    def test_a_record_over_the_bound_is_kept_truncated_and_never_validates(self):
        big = {**observed(DIGEST_A), 'padding': 'x' * 20_000}
        _run, rep, _apps = execute(TWO, identities(big), folder=self.folder)
        row = calls_rows(self.folder)[0]
        self.assertIs(row['model_identity_raw_truncated'], True)
        self.assertIsInstance(row['model_identity_raw'], str)
        self.assertEqual(rep['model_identity']['applicators'][LOCAL]['statuses']['invalid'], 2)
        self.assertIsNone(rep['model_identity']['applicators'][LOCAL]['pinned'])

    def test_a_resume_across_a_digest_change_is_drift_against_the_folders_pin(self):
        def first(_label, _req, n):
            return reply(1, observed(DIGEST_A), USAGE) if n == 1 else {'ok': False, 'error': 'node busy', 'fatal': True}
        _run, rep, _apps = execute(TWO, first, folder=self.folder)
        self.assertEqual(rep['status'], 'failed')
        run, rep, apps = execute(TWO, identities(observed(DIGEST_B)), folder=self.folder)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.requests), 1)                             # a came from calls.jsonl
        self.assertEqual(rep['model_identity']['drift'],
                         [{'line': 2, 'applicator': LOCAL, 'pinned': DIGEST_A, 'observed': DIGEST_B, 'cached': False,
                           'action': 'recorded'}])
        self.assertEqual(rep['model_identity']['applicators'][LOCAL]['digests'], {DIGEST_A: 1, DIGEST_B: 1})
        # the same resume under strict pins refuses b's new answer
        with tempfile.TemporaryDirectory() as other:
            execute(TWO, first, folder=other)
            _run, rep, apps = execute(TWO, identities(observed(DIGEST_B)), folder=other, model_pins='strict')
            self.assertEqual(rep['status'], 'failed')
            self.assertEqual(rep['model_identity']['drift'][0]['action'], 'refused')

    def test_strict_resume_refuses_a_cached_answer_whose_digest_differs_without_asking_again(self):
        _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=self.folder)
        self.assertEqual(rep['status'], 'done')
        _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=self.folder, model_pins='strict')
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(apps.requests, [])                                 # never re-asked
        self.assertEqual(rep['model_identity']['drift'],
                         [{'line': 2, 'applicator': LOCAL, 'pinned': DIGEST_A, 'observed': DIGEST_B, 'cached': True,
                           'action': 'refused'}])
        _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        self.assertEqual((rep['status'], apps.requests), ('done', []))      # default: recorded and reused
        self.assertEqual(rep['model_identity']['drift'][0]['cached'], True)

    def test_drift_in_for_each_threads_is_traced_by_the_run_thread_with_unique_sequences(self):
        src = f'ask e: Int "number for {{it}}?" for each it in [1, 2, 3] by "{LOCAL}" with effort=low\n'
        run, rep, _apps = execute(src, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=self.folder,
                                  parallel=1)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(rep['model_identity']['drift']), 2)
        self.assertEqual(len(rows_of(run, 'model-drift')), 2)
        sequences = [r['sequence'] for r in run.trace]
        self.assertEqual(sequences, sorted(set(sequences)))

    def test_the_recheck_helper_reads_only_and_revalidates_every_raw_record(self):
        execute(TWO, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=self.folder)
        before = folder_state(self.folder)
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['version'], block['basis'], block['rows_truncated'], block['strict']),
                         (1, 'fresh_recheck', False, False))
        self.assertIsInstance(block['computed_at'], float)
        self.assertEqual(block['applicators'][LOCAL]['pinned'], DIGEST_A)
        self.assertEqual(block['drift'], [{'line': 2, 'applicator': LOCAL, 'pinned': DIGEST_A, 'observed': DIGEST_B,
                                           'cached': False, 'action': 'recorded'}])
        self.assertTrue(SR.recheck_model_identities(self.folder, max_rows=1)['rows_truncated'])
        self.assertEqual(SR.recheck_model_identities(self.folder, max_rows=1)['drift'], [])
        self.assertTrue(SR.recheck_model_identities(self.folder, max_bytes=100)['rows_truncated'])
        refused = SR.recheck_model_identities(self.folder, checker=lambda record: None)
        self.assertEqual(refused['applicators'][LOCAL]['statuses']['invalid'], 2)
        with hidden_helper():
            blind = SR.recheck_model_identities(self.folder)
        self.assertEqual((blind['checker']['available'], blind['applicators'][LOCAL]['statuses']['unverifiable']),
                         (False, 2))
        self.assertEqual(folder_state(self.folder), before)                # nothing was written

    def test_the_provider_helper_is_not_part_of_the_kernel_identity(self):
        self.assertNotIn('ollama', json.dumps(S.kernel_id()).lower())
        self.assertNotIn('observer', json.dumps(S.kernel_id()).lower())

    def test_the_runner_advertises_the_identity_contract_root_gates_strict_pins_on(self):
        self.assertIs(type(SR.MODEL_IDENTITY_VERSION), int)       # root's API/CLI accept model_pins only for 1
        self.assertEqual(SR.MODEL_IDENTITY_VERSION, 1)
        self.assertEqual(SR.MODEL_PIN_POLICIES, ('observe', 'strict'))
        self.assertIs(type(SR.MODEL_PIN_POLICIES), tuple)
        self.assertEqual(SR.MODEL_PINS_CAPABILITY, f'symblic.model_pins.strict.v{SR.MODEL_IDENTITY_VERSION}')
        self.assertEqual(SR.MODEL_PINS_CAPABILITY, 'symblic.model_pins.strict.v1')
        self.assertTrue(callable(SR.validate_model_pins))


class StrSub(str):
    pass


INVALID_POLICIES = ('Strict', 'STRICT', 'strct', 'observed', '', ' strict', 'strict ', 'observe\n', StrSub('strict'),
                    True, False, 0, 1, 1.0, b'strict', ['strict'], ('strict',), {'strict': True}, {'policy': 'strict'},
                    object())


class ModelPinsPolicy(unittest.TestCase):
    """D-REPORT-SCHEMA "D4 host policy": the exported surface, the pure validator, and the refusal of an invalid
    policy before any call, effect or write (review B1)."""

    def test_validate_model_pins_accepts_exactly_the_two_policies_and_defaults_to_observe(self):
        self.assertEqual(SR.validate_model_pins(None), 'observe')
        self.assertEqual(SR.validate_model_pins('observe'), 'observe')
        self.assertEqual(SR.validate_model_pins('strict'), 'strict')
        for value in INVALID_POLICIES:
            with self.subTest(value=value), self.assertRaises(S.SymblicError) as raised:
                SR.validate_model_pins(value)
            self.assertEqual(raised.exception.kind, 'invalid')
            self.assertIn('observe', raised.exception.message)
            self.assertIn('strict', raised.exception.message)

    def test_an_invalid_policy_refuses_before_any_call_effect_or_write(self):
        # The whole tree, the folder's own mode and mtime included, from before the Run is CONSTRUCTED: the Store is
        # made in __init__, and a Store for the folder would create artifacts/ (review C v1: a files-only snapshot
        # taken after construction missed it).
        for value in INVALID_POLICIES:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                apps = Models(identities(observed(DIGEST_A)))
                before = tree_state(folder)
                run = SR.Run(TWO, None, apps, {'model_pins': value}, folder=folder)
                rep = run.execute()
                self.assertEqual((rep['status'], rep['error']['kind'], rep['calls']), ('failed', 'invalid', 0))
                self.assertEqual(apps.requests, [])
                self.assertEqual(tree_state(folder), before)       # no artifacts/, state, trace, kernel, calls or log
                self.assertEqual(run.trace, [])
                block = rep['model_identity']
                self.assertEqual((block['policy'], block['strict'], block['applicators']), (None, None, {}))
                self.assertEqual(rep['determinacy']['asks'], [])

    def test_an_invalid_policy_does_not_create_a_folder_that_does_not_exist(self):
        for value in INVALID_POLICIES:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as parent:
                folder = os.path.join(parent, 'never-created')
                before = tree_state(parent)
                apps = Models(identities(observed(DIGEST_A)))
                rep = SR.Run(TWO, None, apps, {'model_pins': value}, folder=folder).execute()
                self.assertEqual((rep['status'], rep['error']['kind'], apps.requests), ('failed', 'invalid', []))
                self.assertIsNone(tree_state(folder))
                self.assertEqual(tree_state(parent), before)       # the parent's mtime too: nothing was made in it

    def test_an_invalid_policy_with_a_budget_ledger_option_reads_no_folder(self):
        with tempfile.TemporaryDirectory() as parent:
            folder = os.path.join(parent, 'never-created')
            run = SR.Run(TWO, None, Models(identities(observed(DIGEST_A))),
                         {'model_pins': 'bad', 'auto_route': {'max_calls': 4, 'repairs': 1}}, folder=folder)
            self.assertIsNone(run.store.dir)
            rep = run.execute()
            self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'invalid'))
            self.assertIsNone(tree_state(folder))

    def test_an_invalid_policy_leaves_a_folder_with_work_exactly_as_it_was(self):
        with tempfile.TemporaryDirectory() as folder:
            _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A)), folder=folder)
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            os.makedirs(os.path.join(folder, 'artifacts', 'nested'))
            with open(os.path.join(folder, 'artifacts', 'nested', 'kept.txt'), 'w', encoding='utf-8') as stream:
                stream.write('kept\n')
            before = tree_state(folder)
            self.assertIn('artifacts', before)
            _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=folder, model_pins='Strict')
            self.assertEqual((rep['status'], rep['error']['kind'], apps.requests), ('failed', 'invalid', []))
            self.assertEqual(tree_state(folder), before)

    def test_omitted_means_observe_and_strict_is_only_explicit(self):
        cases = ((MISSING, 'observe', 'recorded'), (None, 'observe', 'recorded'), ('observe', 'observe', 'recorded'),
                 ('strict', 'strict', 'refused'))
        for value, policy, action in cases:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                options = {} if value is MISSING else {'model_pins': value}
                _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A), observed(DIGEST_B)), folder=folder,
                                           **options)
                block = rep['model_identity']
                self.assertEqual((block['policy'], block['strict']), (policy, policy == 'strict'))
                self.assertEqual([d['action'] for d in block['drift']], [action])
                self.assertEqual(rep['status'], 'done' if policy == 'observe' else 'failed')

    @staticmethod
    def saved_folder(folder, options, trace=True, **meta):
        with open(os.path.join(folder, 'program.sym'), 'w', encoding='utf-8') as stream:
            stream.write(TWO)
        with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as stream:
            json.dump({'options': options, **meta}, stream)
        if trace:
            with open(os.path.join(folder, 'trace.jsonl'), 'w', encoding='utf-8') as stream:
                stream.write('{"line": 1, "kind": "note", "status": "ok", "sequence": 1}\n')
        with open(os.path.join(folder, 'log.txt'), 'w', encoding='utf-8') as stream:
            stream.write('00:00:00 an earlier invocation\n')

    def worker(self, folder, applicators=None):
        """run_folder as the unit runs it, with the provider module replaced by one that counts constructions,
        start_fresh counted (and run) and stdout captured; the signal handlers are compared, then restored."""
        provider = types.SimpleNamespace(Applicators=mock.Mock(side_effect=AssertionError('a provider was constructed')))
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        out = io.StringIO()
        try:
            with mock.patch('symblic.providers.applicators.Applicators', provider.Applicators), \
                    mock.patch.object(SR, 'start_fresh', wraps=SR.start_fresh) as fresh, \
                    mock.patch('sys.stdout', out):
                rep = SR.run_folder(folder, resume=False, applicators=applicators)
            after = {sig: signal.getsignal(sig) for sig in handlers}
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        return rep, provider.Applicators.call_count, fresh.call_count, after == handlers, out.getvalue()

    def test_run_folder_refuses_an_invalid_saved_policy_before_constructing_or_writing_anything(self):
        for value in ('strct', 'Strict', '', True, 1, ['strict'], {'policy': 'strict'}):
            for injected in (False, True):
                with self.subTest(value=value, injected=injected), tempfile.TemporaryDirectory() as folder:
                    self.saved_folder(folder, {'model_pins': value})
                    before = tree_state(folder)
                    self.assertNotIn('artifacts', before)
                    apps = Models(identities(observed(DIGEST_A))) if injected else None
                    rep, constructed, fresh, handlers_kept, out = self.worker(folder, apps)
                    self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'invalid'))
                    self.assertEqual(constructed, 0)               # no provider (symblic.providers.applicators.Applicators)
                    self.assertEqual(fresh, 0)                     # no fresh start
                    self.assertTrue(handlers_kept)                 # no signal handler installed
                    if injected:
                        self.assertEqual(apps.requests, [])
                    self.assertEqual(tree_state(folder), before)   # log.txt, '.' mtime, no artifacts/, trace kept
                    self.assertIn('model_pins', out)               # the refusal is visible in the unit's journal

    def test_run_folder_refuses_an_invalid_policy_before_a_delegation_record(self):
        with tempfile.TemporaryDirectory() as folder:
            self.saved_folder(folder, {'model_pins': 'bad'}, delegation={'not': 'a declaration'})
            before = tree_state(folder)
            rep, constructed, fresh, _kept, _out = self.worker(folder)
            self.assertEqual((rep['status'], rep['error']['kind'], constructed, fresh), ('failed', 'invalid', 0, 0))
            self.assertEqual(tree_state(folder), before)           # no delegation-refusal.json, no state.json

    def test_the_snapshot_sees_what_a_valid_worker_writes(self):
        # Control: the same saved folder with a valid policy is readied and written, so tree_state above would have
        # seen a created artifacts/, a changed folder mtime and an appended log.txt. (No earlier trace here: work
        # an unrecorded kernel left is refused by the resume guard, language-1, before any ask.)
        with tempfile.TemporaryDirectory() as folder:
            self.saved_folder(folder, {'model_pins': 'observe'}, trace=False)
            before = tree_state(folder)
            apps = Models(identities(observed(DIGEST_A)))
            rep, constructed, fresh, _kept, _out = self.worker(folder, apps)
            self.assertEqual((rep['status'], constructed, fresh, len(apps.requests)), ('done', 0, 1, 2))
            after = tree_state(folder)
            self.assertIn('artifacts', after)
            self.assertNotEqual(after['.'], before['.'])
            self.assertNotEqual(after['log.txt'], before['log.txt'])


class StrictIdentity(unittest.TestCase):
    """Strict pins accept ONLY an observed, freshly validated, non-null manifest digest (equal to the folder's pin
    when there is one); everything else is refused before it is accepted or cached, on the first call too. Observe
    records the same cases and refuses nothing (root's requirement 3; review m4, m5)."""

    def assert_refused(self, rep, apps, folder, row_identity):
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('model_pins=strict', rep['error']['message'])
        self.assertEqual(len(apps.requests), 1)                           # never asked again
        self.assertEqual([r['ok'] for r in calls_rows(folder)], [False])  # 0 accepted answers, nothing to reuse
        self.assertEqual(SR.Store(folder).calls, {})
        self.assertEqual(rep['bindings'], [])
        self.assertIsNone(rep['determinacy']['asks'][0]['answered_by'])
        refusals = [r for r in SR._read_jsonl(os.path.join(folder, 'trace.jsonl')) if r['kind'] == 'model-identity']
        self.assertEqual([(r['status'], r['applicator'], r['identity']) for r in refusals],
                         [('refused', LOCAL, row_identity)])

    def test_every_unproven_identity_is_refused_on_the_first_call(self):
        cases = {'unavailable': (unavailable(), 'unavailable'),
                 'listing changed': (listing_changed(), 'drift'),
                 'forged': (forged(), 'invalid'),
                 'another model': (observed(DIGEST_A, model='llama3.2:1b'), 'invalid'),
                 'another node': (observed(DIGEST_A, node='node-b'), 'invalid'),
                 'no record': (MISSING, None)}
        for name, (record, status) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as folder:
                _run, rep, apps = execute(TWO, identities(record), folder=folder, model_pins='strict')
                self.assert_refused(rep, apps, folder, status)
            with self.subTest(case=name, policy='observe'), tempfile.TemporaryDirectory() as folder:
                _run, rep, apps = execute(TWO, identities(record), folder=folder)
                self.assertEqual((rep['status'], len(apps.requests)), ('done', 2), rep.get('error'))
                self.assertEqual([r['ok'] for r in calls_rows(folder)], [True, True])
                app = rep['model_identity']['applicators'].get(LOCAL)
                if status is None:
                    self.assertIsNone(app)                                  # nothing to record without a record
                else:
                    self.assertEqual((app['statuses'][status], app['pinned']), (2, None))

    def test_an_absent_broken_or_unknowing_checker_is_refused_on_the_first_call(self):
        checkers = {'absent': (hidden_helper, 'unverifiable'),
                    'fails at import': (broken_helper, 'unverifiable'),
                    'fails on its attributes': (lambda: broken_helper(BROKEN_ATTRIBUTES), 'unverifiable'),
                    'knows no record': (lambda: mock.patch.object(boc, 'check', lambda record: None), 'invalid')}
        for name, (context, status) in checkers.items():
            with self.subTest(checker=name), tempfile.TemporaryDirectory() as folder, context():
                _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=folder, model_pins='strict')
                self.assert_refused(rep, apps, folder, status)
            with self.subTest(checker=name, policy='observe'), tempfile.TemporaryDirectory() as folder, context():
                _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=folder)
                self.assertEqual(rep['status'], 'done', rep.get('error'))
                app = rep['model_identity']['applicators'][LOCAL]
                self.assertEqual((app['statuses'][status], app['pinned']), (2, None))

    def test_an_observed_validated_digest_is_accepted_and_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            _run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), folder=folder, model_pins='strict')
            self.assertEqual((rep['status'], len(apps.requests)), ('done', 2), rep.get('error'))
            app = rep['model_identity']['applicators'][LOCAL]
            self.assertEqual((app['pinned'], app['statuses']['observed']), (DIGEST_A, 2))
            # an untagged name resolves to name:latest (Ollama's own rule): still this applicator's record
            src = 'ask a: Int "First?" by "ollama:llama3.2@node-a" with effort=low\n'
            _run, rep, _apps = execute(src, identities(observed(DIGEST_B, model='llama3.2:latest')), folder=folder,
                                       model_pins='strict')
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            self.assertEqual(rep['model_identity']['applicators']['ollama:llama3.2@node-a']['pinned'], DIGEST_B)

    def test_a_record_for_another_model_or_node_never_pins_its_applicator(self):
        src = ''.join(f'ask q{i}: Int "Number {i}?" by "{LOCAL}" with effort=low\n' for i in range(3))
        with tempfile.TemporaryDirectory() as folder:
            _run, rep, _apps = execute(src, identities(observed(DIGEST_B, model='llama3.2:1b'),
                                                       observed(DIGEST_B, node='node-b'), observed(DIGEST_A)),
                                       folder=folder)
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            app = rep['model_identity']['applicators'][LOCAL]
            self.assertEqual((app['pinned'], app['statuses']['invalid'], app['statuses']['observed']), (DIGEST_A, 2, 1))
            self.assertEqual(rep['model_identity']['drift'], [])
            self.assertEqual(SR.recheck_model_identities(folder)['applicators'][LOCAL]['pinned'], DIGEST_A)


class BrokenHelper(unittest.TestCase):
    """A provider helper that is present but fails is no checker at all: never a crash (review M2)."""

    def test_a_helper_that_fails_at_import_or_on_its_attributes_never_breaks_a_run_or_its_report(self):
        for body in (BROKEN_AT_IMPORT, BROKEN_ATTRIBUTES):
            with self.subTest(body=body.splitlines()[0]), broken_helper(body):
                rep = SR.Run('let x = 2 + 2.\nshow x.\n').execute()               # kernel only
                self.assertEqual(rep['status'], 'done', rep.get('error'))
                self.assertEqual(rep['model_identity']['checker'], {'available': False, 'version': None})
                with tempfile.TemporaryDirectory() as folder:
                    _run, rep, _apps = execute(TWO, identities(observed(DIGEST_A)), folder=folder)
                    self.assertEqual(rep['status'], 'done', rep.get('error'))
                    app = rep['model_identity']['applicators'][LOCAL]
                    self.assertEqual((app['statuses']['unverifiable'], app['pinned']), (2, None))
                    state = SR._load(os.path.join(folder, 'state.json'), {})
                    self.assertEqual(state.get('status'), 'done')                 # the final save happened
                    block = SR.recheck_model_identities(folder)
                    self.assertEqual((block['checker']['available'], block['audit_complete']), (False, False))


class RecheckAudit(unittest.TestCase):
    """recheck_model_identities never reports a clean audit it did not complete (root's requirement 2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='symblic-lane-c-audit-')
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def audit(self, block):
        return {k: block[k] for k in ('calls_file', 'audit_complete', 'invalid_rows', 'missing_identity_rows',
                                      'rows_truncated', 'incomplete_reasons')}

    def test_a_folder_without_calls_is_a_complete_audit_of_nothing(self):
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual(self.audit(block), {'calls_file': 'absent', 'audit_complete': True, 'invalid_rows': 0,
                                             'missing_identity_rows': 0, 'rows_truncated': False,
                                             'incomplete_reasons': []})
        self.assertEqual((block['applicators'], block['rows_scanned']), ({}, 0))

    def test_an_empty_ledger_is_a_complete_audit_of_nothing(self):
        open(os.path.join(self.folder, 'calls.jsonl'), 'w', encoding='utf-8').close()
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual(self.audit(block), {'calls_file': 'present', 'audit_complete': True, 'invalid_rows': 0,
                                             'missing_identity_rows': 0, 'rows_truncated': False,
                                             'incomplete_reasons': []})
        self.assertEqual((block['applicators'], block['rows_scanned']), ({}, 0))

    def test_a_clean_ledger_is_complete(self):
        execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual(self.audit(block), {'calls_file': 'present', 'audit_complete': True, 'invalid_rows': 0,
                                             'missing_identity_rows': 0, 'rows_truncated': False,
                                             'incomplete_reasons': []})
        self.assertEqual(block['rows_scanned'], 2)

    def write_rows(self, *rows):
        with open(os.path.join(self.folder, 'calls.jsonl'), 'a', encoding='utf-8') as stream:
            for row in rows:
                stream.write(json.dumps(row) + '\n')

    LEGACY = {'key': 'old', 'app': LOCAL, 'ok': True, 'reply': {'ok': True, 'json': {'answer': 3}}}

    def test_an_answer_recorded_without_identity_is_counted_and_never_a_complete_audit(self):
        # Review C v1 (probe-final-edges.json): this legacy answer audited complete with no statuses, which reads in
        # the UI exactly like a ledger with no calls. It is an attempt whose identity is unknown, not a status.
        self.write_rows(self.LEGACY)
        before = tree_state(self.folder)
        block = SR.recheck_model_identities(self.folder, checker=boc.check)
        self.assertEqual(self.audit(block), {'calls_file': 'present', 'audit_complete': False, 'invalid_rows': 0,
                                             'missing_identity_rows': 1, 'rows_truncated': False,
                                             'incomplete_reasons': ['missing_identity']})
        self.assertEqual((block['applicators'], block['drift'], block['rows_scanned']), ({}, [], 1))
        self.assertEqual(tree_state(self.folder), before)

    def test_every_attempt_without_identity_counts_but_a_refusal_before_dispatch_does_not(self):
        failed = {'key': 'f', 'app': LOCAL, 'ok': False, 'reply': {'ok': False, 'error': 'timeout'}}
        prefused = {'key': 'p', 'app': LOCAL, 'ok': False,
                    'reply': {'ok': False, 'refused': True, 'error': 'refused: the power fence is down'}}
        self.write_rows(prefused)
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['missing_identity_rows'], block['audit_complete'], block['rows_scanned']),
                         (0, True, 1))                                      # no model saw it: not an attempt
        self.write_rows(failed, self.LEGACY)
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['missing_identity_rows'], block['audit_complete'], block['incomplete_reasons']),
                         (2, False, ['missing_identity']))

    def test_a_strict_refusal_of_an_unlabelled_answer_is_a_charged_attempt_without_identity(self):
        _run, rep, apps = execute(TWO, identities(MISSING), folder=self.folder, model_pins='strict')
        self.assertEqual(rep['status'], 'failed')
        rows = calls_rows(self.folder)
        self.assertTrue(rows and len(rows) == len(apps.requests))
        self.assertTrue(all(not r['ok'] and 'model_identity_raw' not in r for r in rows))
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['missing_identity_rows'], block['audit_complete'], block['incomplete_reasons']),
                         (len(rows), False, ['missing_identity']))

    def test_identity_evidence_still_counts_beside_rows_that_have_none(self):
        execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        self.write_rows(self.LEGACY)
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual(block['applicators'][LOCAL]['statuses']['observed'], 2)
        self.assertEqual(block['applicators'][LOCAL]['pinned'], DIGEST_A)
        self.assertEqual((block['missing_identity_rows'], block['incomplete_reasons']), (1, ['missing_identity']))

    def test_an_unreadable_ledger_or_folder_is_never_clean(self):
        os.mkdir(os.path.join(self.folder, 'calls.jsonl'))                   # present, but not a readable file
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['calls_file'], block['audit_complete'], block['incomplete_reasons']),
                         ('unreadable', False, ['unreadable']))
        missing = os.path.join(self.folder, 'no-such-run')
        block = SR.recheck_model_identities(missing)
        self.assertEqual((block['calls_file'], block['audit_complete'], block['incomplete_reasons'],
                          block['missing_identity_rows']), ('unreadable', False, ['unreadable'], 0))
        self.assertIsNone(tree_state(missing))                               # the audit created nothing

    def test_torn_or_malformed_rows_are_counted_and_make_the_audit_incomplete(self):
        execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        with open(os.path.join(self.folder, 'calls.jsonl'), 'ab') as stream:
            stream.write(b'[1, 2]\n"text"\n\xff\xfe not utf-8\n'
                         b'{"app": 7, "model_identity_raw": {"status": "observed"}}\n{"key": "x", "ok": tr')
        block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['invalid_rows'], block['audit_complete'], block['incomplete_reasons']),
                         (5, False, ['invalid_rows']))
        self.assertEqual(block['applicators'][LOCAL]['pinned'], DIGEST_A)      # the readable rows still count

    def test_bounds_make_the_audit_incomplete(self):
        execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        rows = SR.recheck_model_identities(self.folder, max_rows=1)
        self.assertEqual((rows['rows_truncated'], rows['audit_complete'], rows['incomplete_reasons']),
                         (True, False, ['max_rows']))
        size = os.path.getsize(os.path.join(self.folder, 'calls.jsonl'))
        cut = SR.recheck_model_identities(self.folder, max_bytes=size - 10)
        self.assertEqual((cut['rows_truncated'], cut['audit_complete'], cut['incomplete_reasons'], cut['rows_scanned']),
                         (True, False, ['max_bytes'], 1))
        whole = SR.recheck_model_identities(self.folder, max_bytes=size)
        self.assertEqual((whole['rows_truncated'], whole['audit_complete']), (False, True))

    def test_records_no_checker_could_examine_are_not_a_complete_audit(self):
        execute(TWO, identities(observed(DIGEST_A)), folder=self.folder)
        with hidden_helper():
            block = SR.recheck_model_identities(self.folder)
        self.assertEqual((block['audit_complete'], block['incomplete_reasons']), (False, ['no_checker']))
        with tempfile.TemporaryDirectory() as other, hidden_helper():
            execute(TWO, identities(MISSING), folder=other)                  # rows without identity records
            block = SR.recheck_model_identities(other)
            # nothing a checker could examine, and no status invented for them: missing, not unverifiable
            self.assertEqual((block['audit_complete'], block['incomplete_reasons'], block['missing_identity_rows'],
                              block['applicators']), (False, ['missing_identity'], 2, {}))


# ------------------------------------------------------------------------------------------------------------- D5

LADDER = ('ask x: Int in 0..9 "x" by {by} with route=escalate, retries=0\n'
          'ensure x = 7 else retry.\n')


def ladder(answers):
    """answers: {label: value or 'refused'}."""
    def answer(label, _req, _n):
        value = answers[label]
        if value == 'refused':
            return {'ok': False, 'refused': True, 'error': 'refused: cloud release needs the owner opt-in'}
        return reply(value)
    return answer


class Escalation(unittest.TestCase):
    def escalate(self, by, answers, folder=None, **options):
        run, rep, apps = execute(LADDER.format(by=by), ladder(answers), folder=folder, **options)
        return run, rep, apps

    def receipt(self, run):
        row, = [r for r in run.trace if r['kind'] == 'ask']
        return row['escalation']

    def test_a_local_rung_answers_with_no_cloud_call(self):
        run, rep, _apps = self.escalate('["fake:small", "fake:big", "claude:haiku"]',
                                        {'fake:small': 3, 'fake:big': 7, 'claude:haiku': 7})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(self.receipt(run), {'rung': 1, 'rungs': 3, 'applicator': 'fake:big', 'locality': 'local',
                                             'cached': False, 'cloud_dispatches_charged': 0,
                                             'cloud_refused_pre_dispatch': 0})
        block = rep['escalation']
        self.assertEqual({k: block[k] for k in ('version', 'asks', 'local_only_success', 'cloud_accepted', 'failed',
                                                'cloud_dispatches_charged', 'cloud_refused_pre_dispatch')},
                         {'version': 1, 'asks': 1, 'local_only_success': 1, 'cloud_accepted': 0, 'failed': 0,
                          'cloud_dispatches_charged': 0, 'cloud_refused_pre_dispatch': 0})
        self.assertEqual(block['by_rung'], [{'rung': 1, 'applicator': 'fake:big', 'locality': 'local', 'accepted': 1}])
        meta = rep['bindings'][0]['meta']
        self.assertEqual((meta['route'], meta['selected']), ('escalate', 'fake:big'))      # behaviour unchanged

    def test_a_cloud_rung_is_cloud_accepted_and_its_dispatch_is_charged(self):
        run, rep, _apps = self.escalate('["fake:small", "fake:big", "claude:haiku"]',
                                        {'fake:small': 3, 'fake:big': 2, 'claude:haiku': 7})
        self.assertEqual(self.receipt(run)['locality'], 'cloud')
        self.assertEqual(self.receipt(run)['cloud_dispatches_charged'], 1)
        block = rep['escalation']
        self.assertEqual((block['local_only_success'], block['cloud_accepted'], block['cloud_dispatches_charged']),
                         (0, 1, 1))
        self.assertEqual(rep['determinism_summary']['cloud_accepted'], 1)

    def test_a_cloud_rung_refused_before_dispatch_is_not_charged(self):
        run, rep, _apps = self.escalate('["claude:haiku", "fake:big"]', {'claude:haiku': 'refused', 'fake:big': 7})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        receipt = self.receipt(run)
        self.assertEqual((receipt['rung'], receipt['locality'], receipt['cloud_dispatches_charged'],
                          receipt['cloud_refused_pre_dispatch']), (1, 'local', 0, 1))
        self.assertEqual((rep['escalation']['local_only_success'], rep['escalation']['cloud_refused_pre_dispatch']),
                         (1, 1))

    def test_a_charged_cloud_dispatch_disqualifies_a_later_local_success(self):
        _run, rep, _apps = self.escalate('["claude:haiku", "fake:big"]', {'claude:haiku': 3, 'fake:big': 7})
        block = rep['escalation']
        self.assertEqual((block['asks'], block['local_only_success'], block['cloud_accepted'], block['failed'],
                          block['cloud_dispatches_charged']), (1, 0, 0, 0, 1))

    def test_a_failed_escalation_counts_as_failed(self):
        _run, rep, _apps = self.escalate('["fake:small", "claude:haiku"]', {'fake:small': 3, 'claude:haiku': 4})
        self.assertEqual(rep['status'], 'failed')
        block = rep['escalation']
        self.assertEqual((block['asks'], block['failed'], block['cloud_dispatches_charged'], block['by_rung']),
                         (1, 1, 1, []))

    def test_a_cached_answer_keeps_its_original_locality_and_charges_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            answers = {'fake:small': 3, 'claude:haiku': 7}
            self.escalate('["fake:small", "claude:haiku"]', answers, folder=folder)
            run, rep, apps = self.escalate('["fake:small", "claude:haiku"]', answers, folder=folder)
        self.assertEqual((rep['status'], apps.requests), ('done', []))
        receipt = self.receipt(run)
        self.assertEqual((receipt['cached'], receipt['locality'], receipt['cloud_dispatches_charged']),
                         (True, 'cloud', 0))
        self.assertEqual((rep['escalation']['cloud_accepted'], rep['escalation']['cloud_dispatches_charged']), (1, 0))

    def test_for_each_items_escalating_in_threads_are_counted_per_item(self):
        policy = {'candidates': ['claude:haiku', 'fake:big'], 'max_calls': 20, 'repairs': 0}
        run, rep, _apps = execute('ask x: Int in 0..9 "x for {it}" for each it in [1, 2, 3] by "auto"\n',
                                  ladder({'claude:haiku': 'refused', 'fake:big': 7}), auto_route=policy, parallel=3)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        row, = [r for r in run.trace if r['kind'] == 'ask']
        self.assertEqual([(e['rung'], e['locality'], e['cloud_refused_pre_dispatch']) for e in row['escalation']],
                         [(1, 'local', 1)] * 3)
        block = rep['escalation']
        self.assertEqual((block['asks'], block['local_only_success'], block['cloud_refused_pre_dispatch'],
                          block['by_rung']),
                         (3, 3, 3, [{'rung': 1, 'applicator': 'fake:big', 'locality': 'local', 'accepted': 3}]))
        self.assertEqual([e['index'] for e in rep['determinacy']['asks']], [1, 2, 3])

    def test_automatic_routing_reports_its_rungs_and_policy_refusals(self):
        policy = {'candidates': ['fake:small', 'claude:haiku', 'fake:big'], 'max_calls': 10, 'repairs': 0,
                  'allow_cloud': False}
        run, rep, apps = execute('ask x: Int in 0..9 "x" by "auto"\nensure x = 7 else retry.\n',
                                 ladder({'fake:small': 3, 'fake:big': 7, 'claude:haiku': 7}), auto_route=policy)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertNotIn('claude:haiku', [S.app_label(r['app']) for r in apps.requests])
        receipt = self.receipt(run)
        self.assertEqual((receipt['rung'], receipt['rungs'], receipt['applicator'], receipt['cloud_refused_pre_dispatch']),
                         (1, 2, 'fake:big', 1))
        self.assertEqual(rep['escalation']['local_only_success'], 1)

    def test_cloud_dispatches_of_a_rolled_back_ask_stay_charged_when_it_is_not_asked_again(self):
        # review M3: an ensure-retry rolls back an escalated ask that charged a cloud dispatch, and control flow then
        # skips it (a succeeding run) or the re-asked anchor fails: the dispatch was made and charged all the same
        skipped = ('ask a: Int in 0..9 "a" by "fake:a" with effort=low, retries=1\n'
                   'if a < 5 then\n'
                   '  ask y: Int in 0..9 "y" by ["claude:haiku", "fake:big"] with route=escalate, retries=0\n'
                   '  ensure y = 5 else retry.\n'
                   'end.\n'
                   'ensure a = 7 else retry.\n')
        failing = ('ask a: Int in 0..9 "a" by "fake:a" with effort=low, retries=1\n'
                   'ask y: Int in 0..9 "y" by ["claude:haiku", "fake:big"] with route=escalate, retries=0\n'
                   'ensure y = 5 else retry.\n'
                   'ensure a = 7 else retry.\n')
        for src, second, status in ((skipped, reply(7), 'done'),
                                    (failing, {'ok': False, 'error': 'down', 'fatal': True}, 'failed')):
            seen = {'a': 0}

            def answer(label, _req, _n, second=second):
                if label == 'fake:a':
                    seen['a'] += 1
                    return reply(3) if seen['a'] == 1 else second
                return reply(1) if label == 'claude:haiku' else reply(5)
            with self.subTest(status=status):
                _run, rep, apps = execute(src, answer)
                self.assertEqual(rep['status'], status, rep.get('error'))
                self.assertEqual(sum(1 for r in apps.requests if S.app_label(r['app']) == 'claude:haiku'), 1)
                block = rep['escalation']
                self.assertEqual((block['asks'], block['rolled_back'], block['cloud_dispatches_charged'],
                                  block['local_only_success'], block['failed']), (0, 1, 1, 0, 0))
                self.assertEqual(rep['determinism_summary']['cloud_dispatches_charged'], 1)

    def test_a_re_asked_escalation_carries_the_charge_and_the_total_counts_it_once(self):
        src = ('ask a: Int in 0..9 "a" by "fake:a" with effort=low, retries=1\n'
               'ask y: Int in 0..9 "y for {a}" by ["claude:haiku", "fake:big"] with route=escalate, retries=0\n'
               'ensure y = 5 else retry.\n'
               'ensure a = 7 else retry.\n')
        seen = {'a': 0}

        def answer(label, _req, _n):
            if label == 'fake:a':
                seen['a'] += 1
                return reply(3 if seen['a'] == 1 else 7)
            return reply(1) if label == 'claude:haiku' else reply(5)
        run, rep, apps = execute(src, answer)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(sum(1 for r in apps.requests if S.app_label(r['app']) == 'claude:haiku'), 2)
        receipt = [r for r in run.trace if r['kind'] == 'ask' and r.get('escalation')][-1]['escalation']
        self.assertEqual((receipt['locality'], receipt['cloud_dispatches_charged']), ('local', 2))   # both attempts
        block = rep['escalation']
        self.assertEqual((block['asks'], block['rolled_back'], block['cloud_dispatches_charged'],
                          block['local_only_success']), (1, 1, 2, 0))

    def test_for_each_by_auto_at_scale_keeps_the_state_the_trace_and_the_receipts_consistent(self):
        # review M4: items run in 8 worker threads that write route rows and periodic state saves; base-root and the
        # first lane C failed this with "FileNotFoundError .../.state.json.<pid>.tmp" and duplicate sequences
        items = 40
        policy = {'candidates': ['claude:haiku', LOCAL], 'max_calls': 200, 'repairs': 0}
        src = f'ask x: Int in 0..9 "x for {{it}}" for each it in [{", ".join(str(i) for i in range(items))}] by "auto"\n'
        lock, count = threading.Lock(), {'n': 0}

        def answer(label, _req, _n):
            if label == 'claude:haiku':
                return {'ok': False, 'refused': True, 'error': 'refused: cloud release needs the owner opt-in'}
            with lock:
                count['n'] += 1
                n = count['n']
            return reply(7, observed(DIGEST_A if n % 3 else DIGEST_B), USAGE)
        with tempfile.TemporaryDirectory() as folder:
            run, rep, _apps = execute(src, answer, folder=folder, auto_route=policy, parallel=8)
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            self.assertEqual([e['index'] for e in rep['determinacy']['asks']], list(range(1, items + 1)))
            self.assertEqual([r['index'] for r in rows_of(run, 'determinacy')], list(range(1, items + 1)))
            sequences = [r['sequence'] for r in run.trace]
            self.assertEqual(sequences, list(range(1, len(run.trace) + 1)))     # unique, no gap, in list order
            on_disk = SR._read_jsonl(os.path.join(folder, 'trace.jsonl'))
            self.assertEqual([r['sequence'] for r in on_disk], sequences)       # the file holds the same order
            self.assertEqual(len(rep['model_identity']['drift']), len(rows_of(run, 'model-drift')))
            block = rep['escalation']
            self.assertEqual((block['asks'], block['local_only_success'], block['cloud_refused_pre_dispatch'],
                              block['cloud_dispatches_charged']), (items, items, items, 0))
            self.assertEqual([name for name in os.listdir(folder) if name.endswith('.tmp')], [])
            state = SR._load(os.path.join(folder, 'state.json'), {})
            self.assertEqual((state.get('status'), state.get('determinism_summary')),
                             ('done', rep['determinism_summary']))

    def test_concurrent_state_saves_and_trace_rows_never_collide(self):
        with tempfile.TemporaryDirectory() as folder:
            store, errors = SR.Store(folder), []

            def save(n):
                try:
                    for i in range(40):
                        store.save('state.json', {'writer': n, 'i': i, 'padding': 'x' * 4000})
                except Exception as exc:  # noqa: BLE001
                    errors.append(f'{type(exc).__name__}: {exc}')
            threads = [threading.Thread(target=save, args=(n,)) for n in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            self.assertEqual([name for name in os.listdir(folder) if name.endswith('.tmp')], [])
            self.assertEqual(SR._load(os.path.join(folder, 'state.json'), {}).get('i'), 39)
        with tempfile.TemporaryDirectory() as folder:
            run, errors = SR.Run('show 1.\n', folder=folder), []

            def trace(n):
                try:
                    for i in range(60):
                        run._trace(S.Node('note', n, 0), 'ok', note=f'{n}.{i}')
                except Exception as exc:  # noqa: BLE001
                    errors.append(f'{type(exc).__name__}: {exc}')
            threads = [threading.Thread(target=trace, args=(n,)) for n in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            sequences = [r['sequence'] for r in run.trace]
            self.assertEqual(sequences, list(range(1, 481)))
            self.assertEqual([r['sequence'] for r in SR._read_jsonl(os.path.join(folder, 'trace.jsonl'))], sequences)
            self.assertEqual([name for name in os.listdir(folder) if name.endswith('.tmp')], [])


# --------------------------------------------------------------------------------------------- the report contract

COMBINED = ('let total = 10.\n'
            'ask x: Int in 0..20 "How many?" by "fake:a" with effort=low, solve=auto\n'
            'let twice = x * 2.\n'
            'ensure twice + 2 = total else retry.\n'
            'ask y: Int in 0..9 "y" by ["fake:small", "claude:haiku"] with route=escalate, retries=0\n'
            'ensure y = 7 else retry.\n'
            f'ask w: Int in 0..20 "Pick one above 17." by "{LOCAL}" with effort=low\n'
            'ensure w > 17 else retry.\n'
            f'ask v: Int "Another number?" by "{LOCAL}" with effort=low\n'
            'show [x, y, w, v].\n')


def combined(label, req, _n):
    if label == 'fake:small':
        return reply(3, unavailable('small'), {'input_tokens': 1})
    if label == 'claude:haiku':
        return reply(7, unavailable('haiku'), {'input_tokens': 5})
    if 'above 17' in req['prompt']:
        return reply(19, observed(DIGEST_A), USAGE)
    return reply(5, observed(DIGEST_B), USAGE)


class ReportSchema(unittest.TestCase):
    """Every key and type of D-REPORT-SCHEMA.md v1 on real run reports, traces and calls.jsonl rows."""

    def is_count(self, value):
        self.assertIs(type(value), int)
        self.assertGreaterEqual(value, 0)

    def check_determinacy(self, block, trace):
        self.assertEqual(block['version'], 1)
        self.assertEqual(set(block['summary']), {'determined', 'underdetermined', 'contradictory', 'unassessed'})
        for value in block['summary'].values():
            self.is_count(value)
        self.assertIsInstance(block['asks'], list)
        self.assertIs(type(block['asks_truncated']), bool)
        self.assertEqual(sum(block['summary'].values()), len(block['asks']))
        for entry in block['asks']:
            self.is_count(entry['line'])
            self.assertIsInstance(entry['name'], str)
            self.assertIs(type(entry['occurrence']), int)
            self.assertGreaterEqual(entry['occurrence'], 1)
            if 'index' in entry:
                self.assertIs(type(entry['index']), int)
            self.assertIn(entry['status'], ('determined', 'underdetermined', 'contradictory', 'unassessed'))
            self.assertIn(entry['answered_by'], ('kernel', 'model', None))
            if 'rejected_by_check' in entry:
                self.assertEqual((entry['rejected_by_check'], entry['answered_by']), (True, None))
            self.assertIn(entry['solve_mode'], ('off', 'on', 'auto'))
            if entry['status'] == 'unassessed':
                self.assertIn(entry['reason'], ('no_finite_domain', 'over_limit', 'no_anchored_checks',
                                                'unsupported_check', 'budget', 'not_attempted'))
                continue
            self.assertEqual(set(entry['domain']), {'kind', 'size'})
            self.assertIn(entry['domain']['kind'], ('bool', 'enum', 'int_range', 'record', 'set', 'list'))
            self.is_count(entry['domain']['size'])
            self.assertIs(type(entry['exhaustive']), bool)
            self.assertEqual(entry['method'], 'enumeration')
            self.assertTrue(all(isinstance(v, str) for v in entry['passing']))
            self.assertLessEqual(len(entry['passing']), 20)
            if entry['passing_count'] is not None:
                self.is_count(entry['passing_count'])
            else:
                self.assertFalse(entry['exhaustive'])
            self.assertIs(type(entry['passing_truncated']), bool)
            self.assertTrue(all(type(n) is int for n in entry['checks']))
            self.assertIs(type(entry['checks_truncated']), bool)
            self.is_count(entry['cost']['steps'])
            if entry['status'] == 'contradictory':
                self.assertEqual((entry['passing_count'], entry['exhaustive']), (0, True))
            if entry['status'] == 'determined':
                self.assertEqual((entry['passing_count'], entry['exhaustive']), (1, True))
        rows = [r for r in trace if r['kind'] == 'determinacy']
        self.assertTrue(rows or not block['asks'])
        for row in rows:
            self.assertTrue({'line', 'name', 'status', 'method', 'exhaustive', 'passing_count', 'reason',
                             'occurrence'} <= set(row))
        for row in trace:
            if row['kind'] == 'ask':
                self.assertIn(row['answered_by'], ('kernel', 'model'))
                self.assertIn(row['solve_mode'], ('off', 'on', 'auto'))

    def check_code_behavior(self, block):
        self.assertEqual(block['version'], 1)
        self.assertIs(type(block['asks_truncated']), bool)
        for entry in block['asks']:
            self.is_count(entry['line'])
            self.assertIsInstance(entry['name'], str)
            self.assertIs(type(entry['occurrence']), int)
            self.assertEqual(entry['scope'], 'declared_tests_only')
            self.is_count(entry['tests']['count'])
            self.assertRegex(entry['tests']['sha256'], HEX64)
            self.is_count(entry['candidates'])
            self.is_count(entry['passing'])
            self.assertIs(type(entry['groups_truncated']), bool)
            for group in entry['groups']:
                self.assertRegex(group['vector_sha256'], HEX64)
                self.assertTrue(all(type(m) is int for m in group['members']))
                self.assertIs(type(group['members_truncated']), bool)
            self.assertIn(entry['status'], ('agreed_on_declared', 'differs_on_declared', 'single', 'none',
                                            'unmeasured'))
            if entry['status'] == 'unmeasured':
                self.assertEqual(entry['groups'], [])
                self.assertTrue(entry['unmeasured_adapters'])
            self.assertIn(entry['covered_by'], (None, 'root_D7'))

    def check_model_identity(self, block, basis='recorded_at_report', refused=False):
        self.assertEqual((block['version'], block['basis']), (1, basis))
        self.assertIsInstance(block['computed_at'], float)
        if basis == 'recorded_at_report' and refused:
            # an invalid policy refused the invocation before anything ran: no policy was in force
            self.assertEqual((block['policy'], block['strict']), (None, None))
        elif basis == 'recorded_at_report':
            self.assertIn(block['policy'], ('observe', 'strict'))          # the validated host policy
            self.assertIs(type(block['strict']), bool)
        else:
            self.assertNotIn('policy', block)           # a folder's rows can come from executions under several policies
            self.assertIs(type(block['strict']), bool)
            self.assertIn(block['calls_file'], ('present', 'absent', 'unreadable'))
            self.assertIs(type(block['audit_complete']), bool)
            self.is_count(block['invalid_rows'])
            self.is_count(block['rows_scanned'])
            self.is_count(block['missing_identity_rows'])
            self.assertEqual('missing_identity' in block['incomplete_reasons'], block['missing_identity_rows'] > 0)
            self.assertIs(type(block['rows_truncated']), bool)
            order = ('unreadable', 'invalid_rows', 'max_rows', 'max_bytes', 'no_checker', 'missing_identity')
            self.assertTrue(set(block['incomplete_reasons']) <= set(order))
            self.assertEqual(block['incomplete_reasons'], [r for r in order if r in block['incomplete_reasons']])
            self.assertEqual(block['audit_complete'], not block['incomplete_reasons'])
        self.assertIs(type(block['checker']['available']), bool)
        self.assertIn(type(block['checker']['version']), (int, type(None)))
        self.assertIs(type(block['applicators_truncated']), bool)
        for label, app in block['applicators'].items():
            self.assertIsInstance(label, str)
            self.assertTrue(app['pinned'] is None or DIGEST.fullmatch(app['pinned']))
            self.assertTrue(all(DIGEST.fullmatch(d) and type(n) is int for d, n in app['digests'].items()))
            self.assertIs(type(app['digests_truncated']), bool)
            self.assertEqual(set(app['statuses']), {'observed', 'drift', 'unavailable', 'invalid', 'unverifiable'})
            for value in app['statuses'].values():
                self.is_count(value)
        self.assertIs(type(block['drift_truncated']), bool)
        for drift in block['drift']:
            self.is_count(drift['line'])
            self.assertIsInstance(drift['applicator'], str)
            self.assertRegex(drift['pinned'], DIGEST)
            self.assertRegex(drift['observed'], DIGEST)
            self.assertIs(type(drift['cached']), bool)
            self.assertIn(drift['action'], ('recorded', 'refused'))

    def check_escalation(self, block, trace):
        self.assertEqual(block['version'], 1)
        for key in ('asks', 'local_only_success', 'cloud_accepted', 'failed', 'cloud_dispatches_charged',
                    'cloud_refused_pre_dispatch', 'rolled_back'):
            self.is_count(block[key])
        self.assertIs(type(block['by_rung_truncated']), bool)
        for row in block['by_rung']:
            self.is_count(row['rung'])
            self.assertIsInstance(row['applicator'], str)
            self.assertIn(row['locality'], ('local', 'cloud'))
            self.is_count(row['accepted'])
        receipts = [r['escalation'] for r in trace if r['kind'] == 'ask' and 'escalation' in r]
        self.assertTrue(receipts or not block['asks'])
        for receipt in receipts:
            self.assertEqual(set(receipt), {'rung', 'rungs', 'applicator', 'locality', 'cached',
                                            'cloud_dispatches_charged', 'cloud_refused_pre_dispatch'})
            self.assertIn(receipt['locality'], ('local', 'cloud'))
            self.assertIs(type(receipt['cached']), bool)

    def check_summary(self, summary):
        self.assertEqual(summary['version'], 1)
        self.assertEqual(set(summary) - {'version'},
                         {'determined', 'underdetermined', 'contradictory', 'unassessed', 'answered_by_kernel',
                          'answered_by_model', 'unanswered', 'local_only_success', 'cloud_accepted',
                          'cloud_dispatches_charged', 'drift_events', 'identity_unverifiable', 'behavior_scope'})
        self.assertEqual(summary['behavior_scope'], 'declared_tests_only')
        for key, value in summary.items():
            if key not in ('version', 'behavior_scope'):
                self.is_count(value)

    def test_a_real_run_report_carries_every_key_and_type(self):
        with tempfile.TemporaryDirectory() as folder:
            run, rep, _apps = execute(COMBINED, combined, folder=folder)
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            self.check_determinacy(rep['determinacy'], run.trace)
            self.assertEqual([e['status'] for e in rep['determinacy']['asks']],
                             ['determined', 'determined', 'underdetermined', 'unassessed'])
            self.assertEqual([e['answered_by'] for e in rep['determinacy']['asks']], ['kernel', 'model', 'model', 'model'])
            self.check_code_behavior(rep['code_behavior'])
            self.check_model_identity(rep['model_identity'])
            self.assertEqual(len(rep['model_identity']['drift']), 1)
            self.check_escalation(rep['escalation'], run.trace)
            self.check_summary(rep['determinism_summary'])
            self.assertEqual({k: rep['determinism_summary'][k] for k in
                              ('determined', 'underdetermined', 'unassessed', 'answered_by_kernel', 'answered_by_model',
                               'unanswered', 'cloud_accepted', 'drift_events')},
                             {'determined': 2, 'underdetermined': 1, 'unassessed': 1, 'answered_by_kernel': 1,
                              'answered_by_model': 3, 'unanswered': 0, 'cloud_accepted': 1, 'drift_events': 1})
            for row in calls_rows(folder):
                self.assertIn('model_identity_raw', row)
                self.assertIsInstance(row['usage'], dict)
                label = row['identity_check_at_call']
                self.assertEqual(label['checker'], 'symblic.providers.ollama_call.check')
                self.assertIn(type(label['checker_version']), (int, type(None)))
                self.assertIs(type(label['validated']), bool)
                self.assertIs(type(label['pinned']), bool)
            self.check_model_identity(SR.recheck_model_identities(folder), basis='fresh_recheck')
            state = SR._load(os.path.join(folder, 'state.json'), {})
            self.assertEqual(state['determinism_summary'], rep['determinism_summary'])
            json.dumps(rep, allow_nan=False)                                # the report stays strict JSON

    def check_all(self, rep, trace, refused=False):
        self.check_determinacy(rep['determinacy'], trace)
        self.check_code_behavior(rep['code_behavior'])
        self.check_model_identity(rep['model_identity'], refused=refused)
        self.check_escalation(rep['escalation'], trace)
        self.check_summary(rep['determinism_summary'])
        json.dumps(rep, allow_nan=False)

    def test_a_failed_runs_report_carries_the_blocks_too(self):
        run, rep, _apps = execute('ask k: Int in 0..5 "?" by "fake:a"\nensure k > 9 else retry.\n',
                                  lambda *_: reply(1))
        self.assertEqual(rep['status'], 'failed')
        self.check_all(rep, run.trace)
        self.assertEqual(rep['escalation']['asks'], 0)
        self.assertEqual(rep['code_behavior']['asks'], [])

    def test_a_kernel_refusal_carries_the_blocks_too(self):
        # review m7: a real refusal by language-1's kernel gate (work another kernel recorded), with 0 calls
        src = 'ask x: Int in 0..5 "?" by "fake:a" with effort=low\nensure x > 1 else retry.\n'
        with tempfile.TemporaryDirectory() as folder:
            other = {**S.kernel_id(), 'lang': '2.4', 'id': '0b2cca3828a1965a'}
            with mock.patch.object(S, 'kernel_id', return_value=other):
                _run, rep, _apps = execute(src, lambda *_: reply(3), folder=folder)
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            run, rep, apps = execute(src, lambda *_: reply(3), folder=folder)
            self.assertEqual((rep['status'], rep['error']['kind'], apps.requests), ('failed', 'version', []))
            self.assertEqual(rep['kernel_check']['decision'], 'refused')
            self.check_all(rep, run.trace)
            self.assertEqual((rep['determinacy']['asks'], rep['model_identity']['policy']), ([], 'observe'))

    def test_an_invalid_policy_refusal_carries_the_blocks_too(self):
        run, rep, apps = execute(TWO, identities(observed(DIGEST_A)), model_pins='STRICT')
        self.assertEqual((rep['status'], rep['error']['kind'], apps.requests), ('failed', 'invalid', []))
        self.check_all(rep, run.trace, refused=True)

    def test_a_recheck_of_every_audit_case_carries_the_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            self.check_model_identity(SR.recheck_model_identities(folder), basis='fresh_recheck')
            execute(TWO, identities(observed(DIGEST_A)), folder=folder)
            for bounds in ({}, {'max_rows': 1}, {'max_bytes': 50}):
                self.check_model_identity(SR.recheck_model_identities(folder, **bounds), basis='fresh_recheck')
            with hidden_helper():
                self.check_model_identity(SR.recheck_model_identities(folder), basis='fresh_recheck')
            with open(os.path.join(folder, 'calls.jsonl'), 'ab') as stream:
                stream.write(b'{"torn')
            self.check_model_identity(SR.recheck_model_identities(folder), basis='fresh_recheck')
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, 'calls.jsonl'), 'w', encoding='utf-8') as stream:
                stream.write(json.dumps(RecheckAudit.LEGACY) + '\n')
            self.check_model_identity(SR.recheck_model_identities(folder), basis='fresh_recheck')
        self.check_model_identity(SR.recheck_model_identities('/nonexistent/symblic-run'), basis='fresh_recheck')

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_a_code_search_report_carries_the_behavior_block(self):
        rep = SR.Run(CodeBehavior.TESTED, applicators=Replies({'a': [CodeBehavior.PLUS], 'b': [CodeBehavior.LOOP],
                                                                 'c': [CodeBehavior.BAD]}, {'a': 0.3}),
                     options={'parallel': 3}).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.check_code_behavior(rep['code_behavior'])
        self.assertEqual(len(rep['code_behavior']['asks']), 1)


if __name__ == '__main__':
    unittest.main()

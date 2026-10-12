"""Symblic 2.3 interpreter hooks with fake applicators (no model, no network): retry feedback from the kernel,
the no-leak rule, retry exhaustion, vacuous checks, the permutation probe, the median vote, the feedback
exposure record and the run-polling snapshot."""

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import diagnose as D  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

SECRET = 987654321
LABEL = 'zebra-label-4417'


class FakeApps:
    """answer(app_label, prompt, req) -> a JSON-able answer object. Records every request."""

    def __init__(self, answer):
        self.answer = answer
        self.reqs = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        return {'ok': True, 'json': self.answer(S.app_label(req['app']), req['prompt'], req), 'ms': 1}


def run_with(src, answer, folder=None, **opts):
    apps = FakeApps(answer)
    run = SR.Run(src, None, apps, {'by': 'fake:a', **opts}, folder=folder)
    return run, run.execute(), apps


def sequence(*values):
    """A fake that answers the given values in order (the last one again when they run out)."""
    it = iter(values)
    last = [values[-1]]

    def answer(app, prompt, req):
        last[0] = next(it, last[0])
        return {'answer': last[0]}
    return answer


def first_listed(app, prompt, req):
    """A reader with a position bias: it picks whichever option is listed first."""
    return {'answer': re.search(r'exactly one of: "([^"]+)"', prompt).group(1)}


class Feedback(unittest.TestCase):
    def test_the_last_answer_is_explained_without_a_because(self):
        src = ('ask n: Int "Give an even number above 10." with effort=low\nlet half = n / 2.\n'
               'ensure half > 5 else retry.\n')
        _, rep, apps = run_with(src, sequence(3, 12))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('Each failed the check `half > 5`. Give an answer that passes it. '
                      'In the last answer: half = 1.5.\n', apps.reqs[1]['prompt'])

    def test_a_because_message_is_preserved_and_answer_detail_is_appended(self):
        src = ('ask n: Int "Give a number above 10." with effort=low\nlet half = n / 2.\n'
               'ensure half > 5 else retry because "too small".\n')
        _, rep, apps = run_with(src, sequence(3, 12))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('Each failed the check `half > 5` (too small). Give an answer that passes it. '
                      'In the last answer: half = 1.5.\n', apps.reqs[1]['prompt'])

    def test_escalation_explains_a_failed_encoded_predicate(self):
        src = ('ask n: Int "Give a number above 10." with effort=low, route=escalate, retries=1\n'
               'let half = n / 2.\nensure half > 5 else retry.\n')
        _, rep, apps = run_with(src, sequence(3, 12))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('failed encoded predicate: half > 5 (half = 1.5)', apps.reqs[1]['prompt'])


class NoLeak(unittest.TestCase):
    """No value outside the answer reaches a prompt through the explanation: every prompt is scanned."""

    SOURCE = (f'given secret: Int = {SECRET}.\ngiven label: Text = "{LABEL}".\n'
              'ask n: Int "Pick a number." with effort=low, retries=5{opts}\n'
              'let m = n * 3.\nlet gap = n - secret.\nlet tagged = text(m) + label.\n'
              'ensure m > 30 and n != secret + 1 and gap < 0 else retry.\n'
              'ensure (all d in [n, m]: d != secret % 97) or len(tagged) > 1000 else retry.\n'
              'ensure contains(label, text(m)) else retry.\n')

    def scan(self, apps):
        self.assertTrue(apps.reqs)
        for req in apps.reqs:
            for secret in (str(SECRET), str(SECRET + 1), LABEL, str(SECRET * 2), str(SECRET * 3)):
                self.assertNotIn(secret, req['prompt'])
                self.assertNotIn(secret, req['system'])

    def test_vote_route_retries(self):
        # 5 fails the first check, 30 (the secret mod 97) the second, 40 the third
        _, rep, apps = run_with(self.SOURCE.format(opts=''), sequence(5, 30, 40))
        self.assertEqual(rep['status'], 'failed')
        prompts = [r['prompt'] for r in apps.reqs]
        self.assertIn('Each failed the check `m > 30 and n != secret + 1 and gap < 0`. Give an answer that passes it. '
                      'In the last answer: m = 15.\n', prompts[1])                 # an answer-only part is shown
        self.assertNotIn('In the last answer', prompts[2])                         # the failing body reads secret
        self.assertIn('In the last answer: text(m) = 120.\n', prompts[3])          # label is never shown
        self.scan(apps)

    def test_a_constant_name_bound_to_an_input(self):
        # `let c = n * pi` reads like a function of the answer; here pi is an input, so nothing is shown
        src = (f'given pi: Int = {SECRET}.\nask n: Int "Pick a number." with effort=low, retries=1\n'
               'let c = n * pi.\nensure c < 0 else retry.\n')
        _, rep, apps = run_with(src, sequence(2))
        self.assertEqual(len(apps.reqs), 2)
        self.assertNotIn('In the last answer', apps.reqs[1]['prompt'])
        self.scan(apps)

    def test_escalation_route(self):
        src = 'group g = ["fake:a", "fake:b"].\n' + self.SOURCE.format(opts=', route=escalate, by=g')
        _, rep, apps = run_with(src, sequence(5, 40, 7, 41, 2, 6, 8, 9, 3, 4, 1, 11))
        self.assertEqual(rep['status'], 'failed')
        self.assertTrue(any('failed encoded predicate' in r['prompt'] for r in apps.reqs))
        self.scan(apps)


class Exhaustion(unittest.TestCase):
    SOURCE = 'ask n: Int "Give a number above 100." with effort=low, retries=2\nensure n > 100 else retry.\n'

    def test_same_answer_every_time(self):
        run, rep, _ = run_with(self.SOURCE, sequence(1))
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['message'], 'ensure failed: n > 100; every attempt gave the same answer, so the '
                         'check, the answer type or the input may be what is wrong')
        self.assertEqual(rep['diagnoses'], [{'line': 2, 'name': 'n', 'check': 'n > 100', 'attempts': 3, 'distinct': 1,
                                             'pattern': 'same', 'answers': ['1', '1', '1']}])
        failed = [r for r in run.trace if r['kind'] == 'ensure' and r['status'] == 'failed']
        self.assertEqual(failed[-1]['note'], 'rejected answers: same')

    def test_a_different_answer_every_time(self):
        run, rep, _ = run_with(self.SOURCE, sequence(1, 2, 3))
        self.assertTrue(rep['error']['message'].endswith('; every attempt gave a different answer, so the statement '
                                                         'may be read in more than one way'))
        self.assertEqual(rep['diagnoses'][0]['pattern'], 'different')
        self.assertEqual(rep['diagnoses'][0]['answers'], ['1', '2', '3'])
        self.assertIn('different', [r for r in run.trace if r['status'] == 'failed'][-1]['note'])

    def test_mixed_and_single(self):
        _, rep, _ = run_with(self.SOURCE, sequence(1, 1, 2))
        self.assertEqual(rep['error']['message'], 'ensure failed: n > 100')
        self.assertEqual(rep['diagnoses'][0]['pattern'], 'mixed')
        _, rep, _ = run_with(self.SOURCE.replace('retries=2', 'retries=0'), sequence(1))
        self.assertEqual(rep['diagnoses'], [])
        _, rep, _ = run_with(self.SOURCE, sequence(1, 200))
        self.assertEqual((rep['status'], rep['diagnoses']), ('done', []))

    def test_escalation(self):
        src = ('group g = ["fake:a", "fake:b"].\n'
               'ask n: Int "Give a number above 100." by g with effort=low, route=escalate, retries=0\n'
               'ensure n > 100 else retry.\n')
        run, rep, _ = run_with(src, sequence(1))
        self.assertTrue(rep['error']['message'].endswith('; every attempt gave the same answer, so the check, the '
                                                         'answer type or the input may be what is wrong'))
        self.assertEqual(rep['diagnoses'], [{'line': 2, 'name': 'n', 'check': 'n > 100', 'attempts': 2,
                                             'distinct': 1, 'pattern': 'same', 'answers': ['1', '1']}])
        self.assertEqual(run.trace[-1]['note'], 'rejected answers: same')

    def test_a_retry_restores_diagnoses_like_warnings(self):
        run = SR.Run('let x = 1.\n', None, None, {'by': 'fake:a'})
        snap = run._snapshot(run.kernel.env)
        run.diagnoses.append({'line': 3})
        run.warnings.append({'line': 3, 'message': 'w'})
        run._restore(snap, run.kernel.env)
        self.assertEqual((run.diagnoses, run.warnings), ([], []))


class Vacuity(unittest.TestCase):
    def vacuous(self, rep):
        return [w for w in rep['warnings'] if w.get('code') == 'SYM_VACUOUS']

    def test_a_check_that_accepts_the_empty_answer(self):
        src = 'ask t: List of Text "Name the rivers." with effort=low\nensure len(t) < 50 else retry.\n'
        run, rep, _ = run_with(src, sequence(['Nile']))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(self.vacuous(rep), [{'line': 1, 'code': 'SYM_VACUOUS', 'message': 't: its checks accept the '
                                              'empty answer []; add a check that an empty answer fails'}])
        rows = [r for r in run.trace if r['kind'] == 'vacuity']
        self.assertEqual([(r['line'], r['status']) for r in rows], [(1, 'warn')])
        static = [w for w in S.check(src)['warnings'] if w.get('code') == 'SYM_VACUOUS']
        self.assertEqual(static[0]['message'], self.vacuous(rep)[0]['message'])     # the same text as the lint
        ask, ensure = S.parse(src)['statements']
        fresh = SR.Run(src, None, None, {'by': 'fake:a'})
        self.assertIsNone(fresh.vacuity(ask, fresh.kernel.env, {'k': 'list', 'of': {'k': 'text'}}))   # no plan yet
        fresh._checks[id(ask)] = {'between': [], 'ensures': [ensure]}
        self.assertEqual(fresh.vacuity(ask, fresh.kernel.env, {'k': 'list', 'of': {'k': 'text'}}),
                         {'value': '[]', 'checks': ['len(t) < 50']})
        self.assertIsNone(fresh.vacuity(ask, fresh.kernel.env, {'k': 'list', 'of': {'k': 'bool'}, 'min': 1,
                                                                'max': 3}))         # [false] is not an open answer

    def test_absent_with_a_length_check(self):
        src = 'ask t: Text "Name the river." with effort=low\nensure len(t) > 0 and len(t) < 50 else retry.\n'
        _, rep, _ = run_with(src, sequence('Nile'))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(self.vacuous(rep), [])

    def test_not_duplicated_in_a_loop(self):
        src = ('for i in [1, 2, 3] do\n  ask t: Text "Name river {i}." with effort=low\n'
               '  ensure len(t) < 50 else retry.\nend.\n')
        run, rep, apps = run_with(src, sequence('Nile'))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.reqs), 3)
        self.assertEqual(len(self.vacuous(rep)), 1)
        self.assertEqual(len([r for r in run.trace if r['kind'] == 'vacuity']), 1)


class Permute(unittest.TestCase):
    SOURCE = 'ask c: one of {{red, green, blue}} "Pick a colour." with effort=low, votes=2{opts}\n'

    def test_stable(self):
        _, rep, apps = run_with(self.SOURCE.format(opts=', permute=3'), lambda a, p, r: {'answer': 'blue'})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        meta = next(b for b in rep['bindings'] if b['name'] == 'c')['meta']
        self.assertEqual(meta['permutation'], {'rotations': 3, 'stable': True, 'complete': True, 'without_answer': [],
                                               'contested': [], 'winners': ['blue', 'blue', 'blue']})
        self.assertFalse(meta['contested'])
        self.assertEqual([x['rotation'] for x in meta['samples']], [0, 0, 1, 1, 2, 2])
        self.assertEqual(len(apps.reqs), 6)
        orders = [re.search(r'exactly one of: (.*)\.\n', r['prompt']).group(1) for r in apps.reqs]
        self.assertEqual(sorted(set(orders)), ['"blue", "red", "green"', '"green", "blue", "red"',
                                               '"red", "green", "blue"'])
        self.assertTrue(any('ask c : one of {green, blue, red}' in r['prompt'] for r in apps.reqs))
        # same seeds and temperatures for every rotation: only the order differs
        self.assertEqual(sorted({(r['seed'], r['temperature'], r['sample']) for r in apps.reqs}),
                         [(7, 0, 0), (8, 0.7, 1)])

    def test_unstable(self):
        _, rep, _ = run_with(self.SOURCE.format(opts=', permute=3'), first_listed)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        meta = next(b for b in rep['bindings'] if b['name'] == 'c')['meta']
        self.assertEqual(meta['permutation'], {'rotations': 3, 'stable': False, 'complete': True, 'without_answer': [],
                                               'contested': [], 'winners': ['red', 'green', 'blue']})
        self.assertTrue(meta['contested'])
        self.assertTrue(meta['unstable_order'])
        self.assertIn({'line': 1, 'message': 'c: the answer changed with the order of the options'}, rep['warnings'])

    def test_strict_fails(self):
        _, rep, _ = run_with(self.SOURCE.format(opts=', permute=2, strict=true'), first_listed)
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['message'], 'c: the answer changed with the order of the options')
        self.assertEqual(rep['error']['kind'], 'check')

    def test_refusals(self):
        cases = [(self.SOURCE.format(opts=', permute=1'), 'permute must be an integer from 2 to 6'),
                 (self.SOURCE.format(opts=', permute=7'), 'permute must be an integer from 2 to 6'),
                 (self.SOURCE.format(opts=', permute=2.5'), 'permute must be an integer from 2 to 6'),
                 ('ask n: Int "?" with effort=low, permute=2\n', 'permute needs an answer with a "one of"'),
                 (self.SOURCE.format(opts=', permute=2, ahead=1'), 'permute cannot be combined with ahead'),
                 (self.SOURCE.format(opts=', permute=2, route=escalate') + 'ensure c != "red" else retry.\n',
                  'route=escalate does not use voting options: votes, permute')]
        for src, message in cases:
            with self.subTest(src):
                _, rep, apps = run_with(src, first_listed)
                self.assertEqual(rep['status'], 'failed')
                self.assertEqual(rep['error']['message'], message)
                self.assertEqual(apps.reqs, [])

    def test_replay_from_the_folder_reuses_every_call(self):
        d = tempfile.mkdtemp()
        try:
            src = self.SOURCE.format(opts=', permute=3')
            _, first, apps = run_with(src, first_listed, folder=d)
            self.assertEqual(len(apps.reqs), 6)
            for opts in ({}, {'replay': True}):
                _, again, apps2 = run_with(src, lambda a, p, r: self.fail('asked a model on replay'), folder=d, **opts)
                self.assertEqual(again['status'], 'done', again.get('error'))
                self.assertEqual(len(apps2.reqs), 0)
                self.assertEqual(again['cached'], 6)
                self.assertEqual(again['fingerprint'], first['fingerprint'])
                meta = next(b for b in again['bindings'] if b['name'] == 'c')['meta']
                self.assertEqual(meta['permutation']['winners'], ['red', 'green', 'blue'])
        finally:
            shutil.rmtree(d)


class Median(unittest.TestCase):
    SOURCE = 'group g = ["fake:a", "fake:b", "fake:c"].\nask x: {ty} "How many?" by g with effort=low, votes=3{opts}\n'

    @staticmethod
    def spread(values):
        return lambda app, prompt, req: {'answer': values[app]}

    def test_median_within(self):
        answer = self.spread({'fake:a': 10, 'fake:b': 11, 'fake:c': 30})
        _, rep, _ = run_with(self.SOURCE.format(ty='Int', opts=', vote=median, within=1'), answer)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        x = next(b for b in rep['bindings'] if b['name'] == 'x')
        self.assertEqual(x['value'], 11)
        meta = x['meta']
        self.assertEqual((meta['vote'], meta['within'], meta['agreement']), ('median', '1', 0.6667))
        self.assertEqual(meta['spread'], {'min': '10', 'max': '30', 'mad': '1'})
        self.assertFalse(meta['contested'])
        _, rep, _ = run_with(self.SOURCE.format(ty='Number', opts=', vote=median, strict=true'), answer)
        self.assertEqual(rep['status'], 'failed')                  # within 0: 11 alone is a third of the weight
        self.assertIn('did not agree', rep['error']['message'])

    def test_refusals(self):
        answer = self.spread({'fake:a': 1, 'fake:b': 1, 'fake:c': 1})
        cases = [('Text', ', vote=median', 'vote=median needs a numeric answer'),
                 ('Int', ', vote=median, key=it', 'vote=median cannot be combined with key'),
                 ('Int', ', vote=median, permute=2', 'vote=median cannot be combined with permute'),
                 ('Int', ', within=1', 'within needs vote=median'),
                 ('Int', ', vote=whole, within=1', 'within needs vote=median'),
                 ('Int', ', vote=median, within=-1', 'within must be a number >= 0'),
                 ('Int', ', vote=mean', 'vote must be whole, fields, median or auto')]
        for ty, opts, message in cases:
            with self.subTest(opts):
                _, rep, apps = run_with(self.SOURCE.format(ty=ty, opts=opts), answer)
                self.assertEqual(rep['status'], 'failed')
                self.assertEqual(rep['error']['message'], message)
                self.assertEqual(apps.reqs, [])


class ReviewFixes(unittest.TestCase):
    """Corrections made when the lanes were merged."""

    def test_exhaustion_counts_one_pass_of_the_block(self):
        # a loop body is one block per item: the second item's pattern must not include the first item's answers
        src = ('for k in [1, 2] do\n'
               '  ask n: Int "Give a number above {k}00." with effort=low, retries=1\n'
               '  ensure n > 100 * k else retry.\n'
               'end.\n')
        # item 1: 5, then 150 (passes). item 2: 150, then 150 (fails twice with one answer)
        _, rep, _ = run_with(src, sequence(5, 150, 150, 150))
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual([(d['attempts'], d['pattern'], d['answers']) for d in rep['diagnoses']],
                         [(2, 'same', ['150', '150'])])

    def test_an_order_is_asked_once_when_there_are_fewer_orders_than_k(self):
        src = 'ask c: one of {red, blue} "Which colour is the sky?" with effort=low, votes=1, permute=5\n'
        _, rep, apps = run_with(src, lambda app, prompt, req: {'answer': 'blue'})
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(len(apps.reqs), 2)                     # two options have two rotations, not five
        ask = [r for r in rep['bindings'] if r['name'] == 'c'][0]
        self.assertEqual(ask['value'], 'blue')

    def test_permute_is_a_voting_option_for_automatic_routing(self):
        src = 'ask c: one of {red, blue} "Which colour is the sky?" with effort=low, permute=2\n'
        route = {'candidates': ['fake:a', 'fake:b'], 'max_calls': 6, 'repairs': 0, 'allow_cloud': False}
        _, rep, apps = run_with(src, lambda app, prompt, req: {'answer': 'blue'}, by='auto', auto_route=route)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual({S.app_label(r['app']) for r in apps.reqs}, {'fake:a'})    # the primary candidate votes

    def test_a_kernel_error_that_may_quote_an_outside_value_is_not_sent_to_the_model(self):
        # the check adds a text input to the answer: the kernel's error names the operand types and values
        src = (f'given label: Text = "{LABEL}".\n'
               'ask n: Int "Pick a number." with effort=low, retries=1\n'
               'ensure n + label else retry.\n')
        _, rep, apps = run_with(src, sequence(4, 5))
        self.assertEqual(rep['status'], 'failed')
        for req in apps.reqs:
            self.assertNotIn(LABEL, req['prompt'])
        self.assertIn('the check could not be evaluated for this answer', apps.reqs[1]['prompt'])

    def test_a_kernel_error_about_the_answer_alone_is_sent(self):
        src = ('ask r: Record {a: Int} "Give a record." with effort=low, retries=1\n'
               'ensure r.b > 0 else retry.\n')
        _, rep, apps = run_with(src, lambda app, prompt, req: {'answer': {'a': 1}})
        self.assertEqual(rep['status'], 'failed')
        self.assertNotIn('could not be evaluated', apps.reqs[1]['prompt'])
        self.assertIn('Each failed the check `r.b > 0` (', apps.reqs[1]['prompt'])

    def test_the_empty_text_answer_is_shown_quoted(self):
        src = 'ask name: Text "Name the river." with effort=low\nensure len(name) < 100 else retry.\n'
        _, rep, _ = run_with(src, lambda app, prompt, req: {'answer': 'Nile'})
        self.assertIn('name: its checks accept the empty answer ""; add a check that an empty answer fails',
                      [w['message'] for w in rep['warnings']])

    def test_families_follow_the_model_a_reply_reports(self):
        class Reporting(FakeApps):
            def call(self, req):
                reply = super().call(req)
                label = S.app_label(req['app'])
                reply['model'] = {'copilot': 'claude-sonnet-4.5', 'claude:haiku': 'haiku'}.get(label, '')
                return reply
        src = ('group g = ["copilot", "claude:haiku", "codex"].\n'
               'ask n: Int "How many legs has a spider?" by g with effort=low, votes=3\n')
        apps = Reporting(lambda app, prompt, req: {'answer': 8})
        run = SR.Run(src, None, apps, {})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        row = [r for r in run.trace if r.get('ask') and r['kind'] == 'ask'][0]
        # copilot answered with a Claude model: one family with claude:haiku (whose alias echo changes nothing)
        self.assertEqual(row['ask']['families'], ['anthropic', 'openai'])

    def test_adapters_do_not_break_either_import_order(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))          # the repository root
        for first in ('symblic.adapters.variational', 'symblic.adapters.transport', 'symblic.kernel.language',
                      'symblic.kernel.diagnose', 'symblic.kernel.run'):
            code = (f'import sys; sys.path.insert(0, {root!r}); import {first}; '
                    'from symblic.kernel import language as S; print(S.kernel_id()["id"])')
            out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            self.assertEqual(out.returncode, 0, first + ': ' + out.stderr[-400:])
            self.assertEqual(out.stdout.strip(), S.kernel_id()['id'], first)


class ReviewA(unittest.TestCase):
    """Root's review of snapshot A (2026-10-03): A1 order probe, A2 exact weights, A3 shadowed constants, A4 bound."""

    PROBE = 'ask c: one of {{red, blue}} "Pick." with effort=low, votes=1, permute=2, retries=0{opts}\n'

    @staticmethod
    def red_or_invalid(app, prompt, req):
        return {'answer': 'red' if 'exactly one of: "red", "blue"' in prompt else 'not-an-option'}

    def test_a1_a_rotation_without_an_answer_is_not_stable(self):
        run, rep, apps = run_with(self.PROBE.format(opts=''), self.red_or_invalid)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        meta = next(b for b in rep['bindings'] if b['name'] == 'c')['meta']
        self.assertEqual(meta['permutation'], {'rotations': 2, 'stable': False, 'complete': False,
                                               'without_answer': [1], 'contested': [], 'winners': ['red', None]})
        self.assertTrue(meta['contested'])
        self.assertIn({'line': 1, 'message': 'c: no valid answer with the options in order 2 of 2'}, rep['warnings'])
        _, rep, _ = run_with(self.PROBE.format(opts=', strict=true'), self.red_or_invalid)
        self.assertEqual((rep['status'], rep['error']['message']),
                         ('failed', 'c: no valid answer with the options in order 2 of 2'))

    def test_a1_a_contested_rotation_is_not_stable(self):
        # two votes per order, one for each colour: every rotation ties, so no order establishes anything
        def split(app, prompt, req):
            return {'answer': 'red' if req['sample'] % 2 == 0 else 'blue'}
        _, rep, _ = run_with(self.PROBE.format(opts='').replace('votes=1', 'votes=2'), split)
        meta = next(b for b in rep['bindings'] if b['name'] == 'c')['meta']
        self.assertEqual((meta['permutation']['stable'], meta['permutation']['contested']), (False, [0, 1]))
        self.assertIn({'line': 1, 'message': 'c: the vote was contested with the options in order 1, 2 of 2'},
                      rep['warnings'])

    def test_a1_resume_and_replay_keep_the_incomplete_probe(self):
        folder = tempfile.mkdtemp()
        try:
            src = self.PROBE.format(opts='')
            _, first, _ = run_with(src, self.red_or_invalid, folder=folder)
            for opts in ({}, {'replay': True}):
                _, again, apps = run_with(src, lambda a, p, r: self.fail('asked a model again'), folder=folder, **opts)
                meta = lambda r: next(b for b in r['bindings'] if b['name'] == 'c')['meta']['permutation']  # noqa: E731
                self.assertEqual((again['status'], len(apps.reqs), meta(again)), ('done', 0, meta(first)))
                self.assertEqual(again['fingerprint'], first['fingerprint'])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a2_exact_weights_decide_the_median(self):
        src = ('group g = ["fake:a*1", "fake:b*1.0000000000000001"].\n'
               'ask n: Int "Pick." by g with effort=low, votes=2, vote=median\n')
        _, rep, _ = run_with(src, lambda app, prompt, req: {'answer': 0 if app == 'fake:a' else 1})
        self.assertEqual((rep['status'], next(b for b in rep['bindings'] if b['name'] == 'n')['value']), ('done', 1))

    def test_a2_a_weight_must_be_above_zero(self):
        rows = [{'value': 1, 'hash': S.fingerprint(1), 'order': 0, 'app': 'fake:a', 'weight_exact': '0'}]
        with self.assertRaises(S.SymblicError):
            S.consensus_median(rows)

    def test_a3_a_constant_name_bound_to_an_input_never_reaches_a_prompt(self):
        src = (f'given pi: Text = "{LABEL}".\nask n: Int "Pick a number." with effort=low, retries=1\n'
               'let c = text(n) + pi.\nensure number(c) > 0 else retry.\n')
        _, rep, apps = run_with(src, sequence(2, 3))
        self.assertEqual(rep['status'], 'failed')
        for req in apps.reqs:
            self.assertNotIn(LABEL, req['prompt'])
        self.assertIn('the check could not be evaluated for this answer', apps.reqs[1]['prompt'])

    def test_a4_a_huge_fixed_length_builds_no_witness(self):
        self.assertIsNone(D.trivial({'k': 'list', 'of': {'k': 'text'}, 'min': 1_000_000_000, 'max': 1_000_000_000}))
        nested = {'k': 'list', 'of': {'k': 'list', 'of': {'k': 'text'}, 'min': 200, 'max': 200}, 'min': 200, 'max': 200}
        self.assertIsNone(D.trivial(nested))
        rep = S.check('ask xs: List of Text length 1000000000 "Many."\nensure len(xs) > 0 else retry.\n')
        self.assertTrue(rep['ok'])


class ReviewB(unittest.TestCase):
    """Fable's adversarial review of snapshot B (2026-10-03)."""

    def test_names_spelled_like_logic_variables_or_builtins_are_still_outside_values(self):
        cases = [
            f'given Limit: Int = {SECRET}.\nask n: Int "Pick." with effort=low, retries=1{{r}}\nlet gap = Limit - n.\n'
            'ensure gap < 0 else retry.\n',
            f'given _s: Int = {SECRET}.\nask n: Int "Pick." with effort=low, retries=1{{r}}\nensure n + _s < 0 else retry.\n',
            f'given secret: Int = {SECRET}.\nfor count in [secret] do\n  ask n: Int "Pick." with effort=low, retries=1{{r}}\n'
            '  ensure n + count < 0 else retry.\nend.\n',
            f'given secret: Int = {SECRET}.\nfor last in [secret] do\n  ask n: Int "Pick." with effort=low, retries=1{{r}}\n'
            '  ensure [1, 2][n * last] == 1 else retry.\nend.\n',
        ]
        for template in cases:
            for route in ('', ', route=escalate'):
                with self.subTest(source=template.format(r=route)):
                    _, rep, apps = run_with(template.format(r=route), sequence(1))
                    self.assertTrue(apps.reqs)
                    for req in apps.reqs:
                        self.assertNotIn(str(SECRET)[:6], req['prompt'])

    def test_the_name_collector_sees_every_read_name(self):
        expr = lambda text: S.Parser(S.tokenize(text), 1).expr()  # noqa: E731
        self.assertEqual(D.names(expr('Limit - n + _s + count')), {'Limit', 'n', '_s', 'count'})
        self.assertEqual(D.names(expr('all x in xs: x > Limit')), {'xs', 'Limit'})
        self.assertEqual(D.names(expr('[y * k for y in ys if y > 0]')), {'ys', 'k'})

    def test_permute_is_refused_with_effort_ultra(self):
        src = 'ask c: one of {red, blue} "Pick." with effort=ultra, permute=2\n'
        _, rep, apps = run_with(src, lambda a, p, r: {'answer': 'red'})
        self.assertEqual((rep['status'], rep['error']['message'], len(apps.reqs)),
                         ('failed', 'permute cannot be combined with effort=ultra', 0))
        self.assertIn('permute cannot be combined with effort=ultra', [e['message'] for e in S.check(src)['errors']])

    def test_an_outer_retry_starts_the_later_asks_over(self):
        seq = {'A': iter([1, 200]), 'B': iter([1, 200, 1, 1, 1, 1])}

        def answer(app, prompt, req):
            return {'answer': next(seq['A' if 'Question A' in prompt else 'B'])}
        src = ('ask a: Int "Question A" with effort=low, retries=2\n'
               'ask b: Int "Question B given {a}" with effort=low, retries=2\n'
               'ensure b > 100 else retry.\nensure a > 100 else retry.\n')
        _, rep, apps = run_with(src, answer)
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual([(d['name'], d['attempts'], d['pattern']) for d in rep['diagnoses']], [('b', 3, 'same')])
        second_pass = [r['prompt'] for r in apps.reqs if 'Question B given 200' in r['prompt']]
        self.assertEqual(len(second_pass), 3)                       # b had its full two retries again
        self.assertTrue(all('given 1' not in p for p in second_pass))
        self.assertIn('These answers were rejected: 1.', second_pass[1])   # only this pass's answer

    def test_a_whole_record_fallback_starts_the_later_asks_over_too(self):
        # root's B.1 closure (root-B1-fallback-retry-repro.py): the field vote assembles {1, 1, 1}, which no agent
        # gave; the check on a rejects it and the whole-record consensus {1, 1, 0} is substituted without a model
        # call; b then runs again with its full two retries and without the first pass's rejected 11
        records = {'fake:a': {'x': 1, 'y': 1, 'z': 0}, 'fake:b': {'x': 1, 'y': 0, 'z': 1},
                   'fake:c': {'x': 0, 'y': 1, 'z': 1}}
        later = iter([11, 200, 1, 1, 200])
        prompts = []

        def answer(app, prompt, req):
            if 'Question A' in prompt:
                return {'answer': records[app]}
            prompts.append(prompt)
            return {'answer': next(later, 200)}
        src = ('group g = ["fake:a", "fake:b", "fake:c"].\n'
               'ask a: Record {x: Int, y: Int, z: Int} "Question A" by g with effort=low, votes=3, vote=fields, retries=2\n'
               'ask b: Int "Question B given {a}" with effort=low, retries=2\n'
               'ensure b > 100 else retry.\nensure a.x + a.y + a.z <= 2 else retry.\n')
        _, rep, _ = run_with(src, answer)
        self.assertEqual((rep['status'], len(prompts)), ('done', 5), rep.get('error'))
        self.assertEqual(next(b for b in rep['bindings'] if b['name'] == 'a')['value'], {'x': 1, 'y': 1, 'z': 0})
        self.assertTrue(all('rejected: 11' not in p for p in prompts[2:]), prompts[2:])
        self.assertIn('Attempt 2. These answers were rejected: 1.', prompts[3])   # numbering restarts in the new pass

    def test_one_items_rejected_answers_are_not_shown_to_the_next(self):
        src = ('given ids: List of Int = [111111, 222222].\nfor k in ids do\n'
               '  ask n: Int "Give a number above {k}." with effort=low, retries=1\n'
               '  ensure n > k else retry.\nend.\n')
        _, rep, apps = run_with(src, sequence(5, 150000, 150000, 150000))
        retry_prompts = [r['prompt'] for r in apps.reqs if 'Attempt 2' in r['prompt']]
        self.assertEqual(len(retry_prompts), 2)
        self.assertIn('These answers were rejected: 150000.', retry_prompts[1])
        self.assertNotIn('5;', retry_prompts[1])


class Crystal(unittest.TestCase):
    """crystallise reports the families the votes computed and keeps no contested answer (review B)."""

    def test_families_follow_the_replies_and_a_contested_answer_is_left_out(self):
        from symblic.lang import abstraction as L
        L.register()
        src = ('program P.\ngroup g = ["copilot:gpt-5", "claude:haiku"].\n'
               'routine colour_of(thing: Text) -> one of {red, green, yellow} with effort=high do\n'
               '  ask c: one of {red, green, yellow} "What colour is {thing}?" by g with votes=2, families=2\n'
               '  return c.\nend.\n')

        class Replies:
            def call(self, req):
                label = S.app_label(req['app'])
                return {'ok': True, 'json': {'answer': 'yellow'}, 'ms': 1,
                        'model': 'claude-sonnet-4.5' if label.startswith('copilot') else 'haiku'}
        res = L.crystallise(src, 'colour_of', ['banana'], Replies(), by='fake:a')
        self.assertEqual(res['families'], ['anthropic'])                 # copilot answered with a Claude model
        self.assertEqual((len(res['kept']), len(res['left_out'])), (0, 1))
        self.assertIn('contested', res['left_out'][0]['reason'])         # families=2 was not met


class ValueNames(unittest.TestCase):
    """A name node reads Env whatever its spelling; only a query's immediate bare capitalised or _-prefixed argument
    is a logic variable. No spelling is refused (root's B.1 flow finding and the kernel advice that followed,
    2026-10-03)."""

    TABLE = [('Page', {'Page'}), ('_page', {'_page'}), ('len', {'len'}), ('len(Page)', {'Page'}),
             ('all Page in Rows: Page = Secret', {'Rows', 'Secret'}),
             ('[len for len in Rows if len = Target]', {'Rows', 'Target'}),
             ('query p(X, _x, bob, len)', {'bob', 'len'}),
             ('query p(Page + 1, [Hidden])', {'Page', 'Hidden'}),
             ('all bob in Rows: query p(X, bob)', {'Rows'})]      # kernel-B1-shared-name-advice.md, verbatim

    @staticmethod
    def expr(text):
        return S.Parser(S.tokenize(text), 1).expr()

    def test_the_expected_name_table(self):
        for text, names in self.TABLE:
            with self.subTest(text=text):
                self.assertEqual(S.free_names(self.expr(text)), names)

    def test_check_scope_leaves_out_only_bare_query_atoms(self):
        cases = [('query p(X, bob)', set(), set()), ('query p(X, bob)', {'bob'}, {'bob'}),
                 ('query p(X, bob) and bob = 1', set(), {'bob'}), ('query p(bob + 1)', set(), {'bob'})]
        for text, scope, names in cases:
            with self.subTest(text=text, scope=scope):
                self.assertEqual(S.free_names(self.expr(text), scope), names)
        quiet = S.check('fact p(ann, bob).\nshow query p(X, bob).\n')
        self.assertEqual((quiet['ok'], quiet['warnings']), (True, []))
        read = S.check('fact p(ann, bob).\nshow query p(X, bob) and bob = "bob".\n')
        self.assertIn('bob is read before anything binds it', [w['message'] for w in read['warnings']])

    def test_the_flow_check_sees_every_spelling(self):
        from symblic.kernel import effects as FX
        from tests.kernel.test_symblic_effects import CAT
        fetch = 'observe {}: Text = web.fetch(url="https://example.test").\n'
        refused = [fetch.format(name) + f'act mail.send(to={name}, body="x").\n' for name in ('page', 'Page', '_page')]
        refused += [fetch.format('page') + 'for count in [page] do\n  act mail.send(to=count, body="x").\nend.\n',
                    fetch.format('Page') + 'let Body = Page + "!".\nact mail.send(to="a@example.test", body=Body).\n',
                    fetch.format('_p') + 'act mail.send(to="a@example.test", body=[x for x in [_p]][0]).\n']
        for src in refused:
            with self.subTest(src=src):
                res = FX.check(src, CAT)
                self.assertFalse(res['ok'])
                self.assertIn('SYM_FLOW', [e.get('code') for e in res['errors']])
        steered = FX.check(fetch.format('Page') + 'let Go = Page = "go".\nif Go then\n'
                           '  act mail.send(to="a@example.test", body="x").\nend.\n', CAT)
        self.assertEqual([(e['influence'], e['needs_owner']) for e in steered['effects'] if e['kind'] == 'act'],
                         [('steered', True)])

    def test_builtin_spelled_names_hold_values(self):
        for src, shown in (('for count in [1, 2] do\n  show count.\nend.\n', ['1', '2']),
                           ('function f(len: Int) -> Int = len + 1.\nshow f(1).\n', ['2'])):
            with self.subTest(src=src):
                self.assertEqual((S.check(src)['ok'], S.check(src)['warnings']), (True, []))
                rep = SR.Run(src, None, None, {'by': 'kernel'}).execute()
                self.assertEqual((rep['status'], [o['text'] for o in rep['outputs']]), ('done', shown))

    def test_an_item_variable_is_bound_inside_its_prompt(self):
        for src in ('ask n: Int "x {sum}" for each sum in [1, 2]\n',
                    'let items = [1, 2].\nask n: Int "x {item}" for each item in items\n'):
            with self.subTest(src=src):
                rep = S.check(src)
                self.assertEqual((rep['ok'], rep['warnings']), (True, []))
        self.assertEqual(S.check('let items = [1, 2].\nask n: Int "x {item}" for each item in items\n')['plan'][1]['reads'],
                         ['items'])

    def test_a_capitalised_answer_is_retried_by_the_check_that_reads_it(self):
        src = 'ask Total: Int "Give a number above 10." with effort=low, retries=1\nensure Total > 10 else retry.\n'
        _, rep, apps = run_with(src, sequence(3, 12))
        self.assertEqual((rep['status'], len(apps.reqs)), ('done', 2))      # 2.2 never re-asked: the anchor was missed

    def test_an_answer_read_as_a_query_argument_is_retried(self):
        src = ('fact known(ann).\nask who: Text "Name someone we know." with effort=low, retries=1\n'
               'ensure query known(who) else retry.\n')
        _, rep, apps = run_with(src, sequence('bob', 'ann'))
        self.assertEqual((rep['status'], len(apps.reqs)), ('done', 2))      # B.1 left bare query arguments out

    def test_a_check_receipt_pins_every_spelling(self):
        for src, name in (('given Limit: Int = 7.\nassert Limit > 3.\n', 'Limit'),
                          ('for count in [5] do\n  assert count > 3.\nend.\n', 'count')):
            with self.subTest(src=src):
                run = SR.Run(src, None, None, {'by': 'kernel'})
                rep = run.execute()
                self.assertEqual(rep['status'], 'done')
                self.assertIn(name, [b['name'] for b in run.checks[0]['bindings']])


class ExposureRecord(unittest.TestCase):
    """The evidence of a retried attempt names an answer-only accept line as model-readable (beta E1)."""

    @staticmethod
    def observations(rep, name):
        row = next(b for b in rep['bindings'] if b['name'] == name)
        return row['meta']['evidence']['observations']

    def test_an_answer_only_check_line_is_recorded_as_model_readable(self):
        src = 'ask wrong: Int "Pick a number." with effort=low, retries=1\nensure wrong = 5 else retry.\n'
        _, rep, apps = run_with(src, sequence(4, 5))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertIn('Each failed the check `wrong = 5`', apps.reqs[1]['prompt'])
        exposed = [o for o in self.observations(rep, 'wrong') if o.get('feedback_exposed')]
        self.assertTrue(exposed)
        for obs in exposed:
            self.assertEqual({'line': 2, 'model_readable': True}, obs['feedback_check'])

    def test_a_check_that_reads_an_input_names_no_model_readable_line(self):
        src = (f'given secret: Int = {SECRET}.\nask n: Int "Pick a number." with effort=low, retries=1\n'
               'ensure n = secret else retry.\n')
        _, rep, apps = run_with(src, sequence(4, SECRET))
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        for req in apps.reqs:
            self.assertNotIn(str(SECRET), req['prompt'])
        for obs in self.observations(rep, 'n'):
            self.assertIsNone(obs.get('feedback_check'))


class PollingSnapshot(unittest.TestCase):
    """A launched run (run_folder) makes each output durably visible to the run?id= poller (beta E5)."""

    def folder_with(self, source, options):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump({'options': options, 'inputs': {}, 'title': 'poll'}, f)
        with open(os.path.join(folder, 'program.sym'), 'w', encoding='utf-8') as f:
            f.write(source)
        return folder

    def poller(self, folder, answer):
        seen = []

        class Apps(FakeApps):
            def call(self, req):
                with open(os.path.join(folder, 'state.json'), encoding='utf-8') as f:
                    seen.append(json.load(f))
                return super().call(req)

        return seen, Apps(answer)

    def test_every_output_reaches_state_json_before_the_next_dispatch(self):
        folder = self.folder_with('show 1.\nask n: Int "Give a number." with effort=low\nshow n.\n',
                                  {'by': 'fake:a'})
        seen, apps = self.poller(folder, lambda app, prompt, req: {'answer': 3})
        report = SR.run_folder(folder, applicators=apps)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual('running', seen[0]['status'])
        self.assertEqual([1], [row['value'] for row in seen[0]['outputs']])
        with open(os.path.join(folder, 'state.json'), encoding='utf-8') as f:
            final = json.load(f)
        self.assertEqual([1, 3], [row['value'] for row in final['outputs']])

    def test_a_saved_opt_out_keeps_the_completion_only_snapshot(self):
        folder = self.folder_with('show 1.\nask n: Int "Give a number." with effort=low\nshow n.\n',
                                  {'by': 'fake:a', 'progress_outputs': False})
        seen, apps = self.poller(folder, lambda app, prompt, req: {'answer': 3})
        report = SR.run_folder(folder, applicators=apps)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertNotIn('outputs', seen[0])
        with open(os.path.join(folder, 'state.json'), encoding='utf-8') as f:
            self.assertEqual([1, 3], [row['value'] for row in json.load(f)['outputs']])


if __name__ == '__main__':
    unittest.main()

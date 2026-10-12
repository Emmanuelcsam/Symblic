"""Symblic 2.3 library: text.quoted_number / quoted_number_in (on the kernel's quotes), the records module and the
two-accounts example. Fake applicators only (no model, no network, no dashboard)."""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.lang import abstraction as L  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '13-two-accounts.sym')
PASSAGE = 'The bath was held at 85 degrees for an hour.'
QUOTED_SRC = ('import quoted_number_in from text.\n'
              f'let t = quoted_number_in("bath temperature in degrees", "{PASSAGE}").\n')


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


def run(src, answer=None, inputs=None):
    apps = FakeApps(answer) if answer else None
    r = SR.Run(src, inputs, apps, {'by': 'fake:a'})
    return r, r.execute(), apps


class Base(unittest.TestCase):
    def setUp(self):
        L.register()             # another suite may have cleared symblic.EXTENSIONS


class TextFunctions(Base):
    def test_the_kernel_tests_of_text_pass(self):
        res = L.run_tests(L.library_source('text'), only=['quoted_number'])
        self.assertTrue(res['ok'], res)
        self.assertEqual((res['passed'], res['failed'], res['asks']), (1, 0, 0))

    def test_quotes_is_exact_where_contains_folds_case(self):
        r, rep, _ = run('let q = quotes("gives 1 mW", "1 MW").\n'
                        'let c = contains("gives 1 mW", "1 MW").\n'
                        'import quoted_number from text.\n'
                        'let cut = quoted_number("Total: 120 units", "20 units", 20).\n'
                        'let whole = quoted_number("Total: 120 units", "120 units", 120).\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertIs(r.kernel.env.lookup('q').value, False)
        self.assertIs(r.kernel.env.lookup('c').value, True)
        self.assertIs(r.kernel.env.lookup('cut').value, False)        # a quote may not cut a numeral
        self.assertIs(r.kernel.env.lookup('whole').value, True)

    def test_text_still_checks_and_documents_the_new_names(self):
        self.assertTrue(S.check(L.library_source('text'))['ok'])
        items = {i['name']: i for i in L.describe_module('text')['items']}
        for name in ('quoted_number', 'quoted_number_in', 'number_in'):
            self.assertIn(name, items)
        self.assertIn('does not establish', items['quoted_number']['doc'])


class QuotedNumberIn(Base):
    def test_a_fabricated_quote_is_retried(self):
        def answer(prompt, req):
            if 'failed the check' in prompt:
                return {'answer': {'value': 85, 'quote': 'held at 85 degrees'}}
            return {'answer': {'value': 85, 'quote': 'kept at 85 degrees'}}
        r, rep, apps = run(QUOTED_SRC, answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('t').value, 85)
        self.assertTrue(any('copied exactly from the passage' in q['prompt'] and 'kept at 85' in q['prompt']
                            for q in apps.reqs))

    def test_a_value_absent_from_the_quote_is_retried(self):
        def answer(prompt, req):
            if 'failed the check' in prompt:
                return {'answer': {'value': 85, 'quote': 'held at 85 degrees'}}
            return {'answer': {'value': 90, 'quote': 'held at 85 degrees'}}
        r, rep, apps = run(QUOTED_SRC, answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('t').value, 85)
        self.assertTrue(any('failed the check' in q['prompt'] for q in apps.reqs))

    def test_a_correct_answer_returns_on_the_first_attempt(self):
        r, rep, apps = run(QUOTED_SRC, lambda p, q: {'answer': {'value': 85, 'quote': 'held at 85 degrees'}})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('t').value, 85)
        self.assertFalse(any('failed the check' in q['prompt'] for q in apps.reqs))

    def test_never_grounded_fails(self):
        _, rep, _ = run(QUOTED_SRC, lambda p, q: {'answer': {'value': 85, 'quote': 'about 85 degrees'}})
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('ensure failed', rep['error']['message'])


class Records(Base):
    def test_the_module_checks_and_its_tests_pass(self):
        source = L.library_source('records')
        self.assertIsNotNone(source)
        self.assertTrue(S.check(source)['ok'])
        res = L.run_tests(source)
        self.assertTrue(res['ok'], res)
        self.assertEqual((res['passed'], res['asks']), (2, 0))
        self.assertIn('records', {m['name'] for m in L.library()})
        names = [i['name'] for i in L.describe_module('records')['items']]
        self.assertEqual(names, ['conflicts', 'agree'])

    def test_import_forms(self):
        r, rep, _ = run('import records as rec.\nlet c = rec.conflicts({a: 1, b: 2}, {b: 3, a: 1}).\n'
                        'import agree from records.\nlet g = agree({a: 1}, {a: 1, b: 2}).\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('c').value, ('b',))
        self.assertIs(r.kernel.env.lookup('g').value, True)


A_ITEMS = [{'kind': 'observation', 'quote': 'On Tuesday you came home at eleven and did not call.'},
           {'kind': 'feeling', 'quote': 'I felt worried.'},
           {'kind': 'need', 'quote': 'I need to know when you will be late.'},
           {'kind': 'request', 'quote': 'Would you text me when you leave work?'}]
B_ITEMS = [{'kind': 'observation', 'quote': 'On Tuesday I came home at eleven.'},
           {'kind': 'observation', 'quote': 'My phone battery was dead.'},
           {'kind': 'feeling', 'quote': 'I felt frustrated.'},
           {'kind': 'need', 'quote': 'I need some room after a long shift.'},
           {'kind': 'request', 'quote': 'Can we talk about it in the morning?'}]


class TwoAccounts(Base):
    def setUp(self):
        super().setUp()
        with open(EXAMPLE, encoding='utf-8') as f:
            self.src = f.read()

    def test_it_checks_and_is_short(self):
        res = S.check(self.src)
        self.assertTrue(res['ok'], res['errors'])
        self.assertLess(len(self.src.splitlines()), 60)

    def test_it_runs_to_done_and_retries_an_invented_quote(self):
        def answer(prompt, req):
            stmt = prompt.split('STATEMENT', 1)[-1]
            if 'say the same thing' in stmt:
                return {'answer': stmt.count('came home at eleven') >= 2}
            if 'did not call' in stmt:
                if 'failed the check' in stmt:
                    return {'answer': A_ITEMS}
                return {'answer': A_ITEMS[:1] + [{'kind': 'feeling', 'quote': 'I felt ignored.'}]}
            return {'answer': B_ITEMS}
        r, rep, apps = run(self.src, answer)
        self.assertEqual(rep['status'], 'done', rep['error'])
        outs = {o['label']: o['value'] for o in rep['outputs']}
        a = outs['account A by kind']
        self.assertEqual(a['feeling'], ['I felt worried.'])
        self.assertEqual(outs['account B by kind']['observation'],
                         ['On Tuesday I came home at eleven.', 'My phone battery was dead.'])
        shared = outs['observations both accounts make (model judgement)']
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]['b'], ['On Tuesday I came home at eleven.'])
        self.assertTrue(any('I felt ignored' in q['prompt'] and 'failed the check' in q['prompt']
                            for q in apps.reqs))

    def test_an_empty_list_is_retried(self):
        _, rep, _ = run(self.src, lambda p, q: {'answer': [] if 'ACCOUNT' in p else False})
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('at least one thing', rep['error']['message'])


if __name__ == '__main__':
    unittest.main()

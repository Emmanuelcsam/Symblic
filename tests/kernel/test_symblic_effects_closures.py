"""symblic_effects.flow follows what callables read: their free names at the call and what their defining scope
held when they were defined, transitively, routines, imports and the defaults asks take (root's HOLD of 2026-10-03,
kernel advice kernel-function-closure-flow-advice.md). Static checks with the fake catalogue, and fake-host runs:
no capability, model or store outside temp folders."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import effects as FX  # noqa: E402
from tests.kernel.test_symblic_effects import CATALOGUE, Base, Host, run  # noqa: E402

PAGE = 'observe page: Text = web.fetch(url="https://example.test").\n'
SEND = 'act mail.send(to="a@example.test", body={}).\n'


def verdict(src):
    res = FX.check(src, CATALOGUE)
    return res['ok'], [e['influence'] for e in res['effects'] if e['kind'] == 'act'], \
        sorted({e.get('code') for e in res['errors']})


class Closures(Base):
    REFUSED = {
        'function defined after the observation': PAGE + 'function leak(x: Int) -> Text = page.\n' + SEND.format('leak(1)'),
        'function defined before the observation': 'function leak(x: Int) -> Text = page.\n' + PAGE
                                                   + SEND.format('leak(1)'),
        'transitive call': 'function g(x: Int) -> Text = page.\nfunction f(x: Int) -> Text = g(x).\n' + PAGE
                           + SEND.format('f(1)'),
        'a caller parameter does not hide its callee\'s closure': PAGE + 'function g(x: Int) -> Text = page.\n'
                           'function f(page: Text) -> Text = g(1).\n' + SEND.format('f("safe")'),
        'a default runs in the defining scope': PAGE + 'function f(page: Text = page) -> Text = page.\n'
                                                + SEND.format('f()'),
        'recursion': PAGE + 'function f(n: Int) -> Text = if n = 0 then page else f(n - 1).\n' + SEND.format('f(2)'),
        'a loop pass keeps its value after the name is bound again': PAGE + 'for captured in [page] do\n'
                           '  function leak(x: Int) -> Text = captured.\nend.\ngiven captured: Text = "safe".\n'
                           + SEND.format('leak(1)'),
        'routine body': PAGE + 'routine r(x: Int) -> Text do\n  let y = page + "!".\n  return y.\nend.\n'
                        'let out = r(1).\n' + SEND.format('out'),
        'routine with context=all': PAGE + 'routine r(x: Int) -> Text with context=all do\n'
                                    '  ask s: Text "Summarize." by "fake:a"\n  return s.\nend.\nlet out = r(1).\n'
                                    + SEND.format('out'),
        'use context=all before an ask': PAGE + 'use context=all.\nask s: Text "Summarize what you were given." '
                                         'by "fake:a"\n' + SEND.format('s'),
        'examples are shown to the model': PAGE + 'ask s: Text "Summarize." by "fake:a" with examples=[[page, "ok"]]\n'
                                           + SEND.format('s'),
        'a loop variable spelled like the observation': PAGE + 'for page in ["x"] do\n  note inside.\nend.\n'
                                                        + SEND.format('page'),
        'a callee queries the knowledge base': PAGE + 'fact seen(page).\nfunction f(x: Int) -> Bool = holds seen(x).\n'
                                               + SEND.format('text(f(1))'),
        'facts a routine asserts reach later queries': PAGE + 'routine r(x: Int) -> Int do\n  fact seen(page).\n'
                           '  return 1.\nend.\nlet n = r(1).\nlet w = query seen(W).\n' + SEND.format('text(w)'),
        'a call nobody defined is not clean': PAGE + SEND.format('mystery(1)'),
        'nor is a name a module does not export': PAGE + 'import stats as st.\n' + SEND.format('text(st.mystery(1))'),
        'an imported routine asks under the program\'s use default': PAGE + 'import text as t.\nuse context=all.\n'
                           'let n = t.count_in("cats", "two cats").\n' + SEND.format('text(n)'),
        'a routine without its own context follows the use default': PAGE + 'use context=all.\n'
                           'routine b(x: Int) -> Text do\n  ask s: Text "Summarize." by "fake:a"\n  return s.\nend.\n'
                           'let out = b(1).\n' + SEND.format('out'),
        # the B.2 closure review (wf_91d20d90-b94), all present in B.1 too
        'a name bound in either branch carries both': PAGE + 'if 1 = 1 then\n  let x = page.\nelse\n'
                           '  let x = "safe".\nend.\n' + SEND.format('x'),
        '... the branches of an elif too': PAGE + 'if 1 = 2 then\n  let x = "a".\nelif 1 = 1 then\n  let x = page.\n'
                           'else\n  let x = "b".\nend.\n' + SEND.format('x'),
        'a rule reads its bindings when a query derives': 'fact seed(1).\nrule leak(X) if seed(1), X = page.\n' + PAGE
                           + 'let found = query leak(X).\n' + SEND.format('text(found)'),
        'a context item that is not a bare name': PAGE + 'ask s: Text "Summarize." by "fake:a" with context=["page"]\n'
                           + SEND.format('s'),
        'a default given without an input': PAGE + 'given x: Text = page.\n' + SEND.format('x'),
        # root's B.3 kernel review: a local callee's edge to an imported or unknown callee was dropped
        'a local function wrapping an imported routine': PAGE + 'import text as t.\nuse context=all.\n'
                           'function wrapper(x: Int) -> Int = t.count_in("cats", "two cats").\n'
                           + SEND.format('text(wrapper(1))'),
        'a local function calling a name nobody defined': PAGE + 'function wrapper(x: Int) -> Int = mystery(x).\n'
                           + SEND.format('text(wrapper(1))'),
    }
    CLEAN = {
        'a parameter shadows the outside name': PAGE + 'function f(page: Text) -> Text = page.\n'
                                                + SEND.format('f("safe")'),
        'a function of its arguments only': PAGE + 'function f(x: Int) -> Int = x + 1.\n' + SEND.format('text(f(1))'),
        'a loop over the program\'s own items': 'for item in ["a", "b"] do\n  ' + SEND.format('item') + 'end.\n',
        'a library function of clean arguments': PAGE + 'import stats as st.\n'
                                                 + SEND.format('text(st.stdev([1, 2, 3]))'),
        'a local function wrapping it': PAGE + 'import stats as st.\n'
                                        'function w(x: Int) -> Number = st.stdev([1, 2, 3]).\n' + SEND.format('text(w(1))'),
        'a local function wrapping an imported routine without a wide default': PAGE + 'import text as t.\n'
                           'function wrapper(x: Int) -> Int = t.count_in("cats", "two cats").\n'
                           + SEND.format('text(wrapper(1))'),
        'an imported routine without a wide default': PAGE + 'import text as t.\n'
                                                      'let n = t.count_in("cats", "two cats").\n' + SEND.format('text(n)'),
        'a builtin spelled like nothing the program binds': PAGE + SEND.format('text(len("abc"))'),
        'an ask with context=none under a wide use default': PAGE + 'use context=all.\n'
                           'ask s: Text "Say clean." by "fake:a" with context=none\n' + SEND.format('s'),
        'a routine that sets its own context shields its asks': PAGE + 'use context=all.\n'
                           'routine r(x: Int) -> Text with context=none do\n  ask s: Text "Say clean." by "fake:a"\n'
                           '  return s.\nend.\nlet out = r(1).\n' + SEND.format('out'),
        '... and the routines it calls': PAGE + 'use context=all.\nroutine b(x: Int) -> Text do\n'
                           '  ask s: Text "Say clean." by "fake:a"\n  return s.\nend.\n'
                           'routine a(x: Int) -> Text with context=none do\n  let t = b(x).\n  return t.\nend.\n'
                           'let out = a(1).\n' + SEND.format('out'),
        # B.2 counted bare query arguments, so a label left behind by an ended loop or a sibling branch made an
        # atom look like outside text (the review's two regressions)
        'an atom spelled like a loop variable that has ended': 'observe doc: Text = web.fetch(url="https://example.test").\n'
                           'fact seen(page).\nfor page in [doc] do\n  note inside.\nend.\n'
                           + SEND.format('text(holds seen(page))'),
        'an atom in one branch, a binding in its sibling': 'given online: Bool = false.\nfact allowed(page).\n'
                           'if online then\n  observe page: Text = web.fetch(url="https://example.test").\n'
                           '  show page.\nelse\n  ' + SEND.format('text(holds allowed(page))') + 'end.\n',
    }

    def test_every_hidden_dependency_is_followed(self):
        for name, src in self.REFUSED.items():
            with self.subTest(name):
                ok, acts, codes = verdict(src)
                self.assertEqual((ok, acts, codes), (False, ['untrusted'], ['SYM_FLOW']))

    def test_programs_that_read_no_outside_text_keep_their_verdict(self):
        for name, src in self.CLEAN.items():
            with self.subTest(name):
                self.assertEqual(verdict(src), (True, ['none'], []))

    def test_a_delegate_inside_a_routine_is_checked_where_the_routine_is_called(self):
        for src in (PAGE + 'routine r(x: Int) -> Int do\n  delegate job = page to "triad".\n  return 1.\nend.\n'
                           'let n = r(1).\n',
                    PAGE + 'routine r(t: Text) -> Int do\n  delegate job = t to "triad".\n  return 1.\nend.\n'
                           'let n = r(page).\n'):
            with self.subTest(src=src):
                res = FX.check(src, CATALOGUE)
                self.assertFalse(res['ok'])
                self.assertTrue(any('delegate' in e['message'] for e in res['errors']), res['errors'])
        clean = 'routine r(x: Int) -> Int do\n  delegate job = "tidy the notes" to "triad".\n  return 1.\nend.\n' \
                'let n = r(1).\n'
        self.assertTrue(FX.check(clean, CATALOGUE)['ok'])

    def test_personal_data_through_a_closure_stays_inside(self):
        src = ('observe busy: Text = calendar.free_busy(days=3).\nfunction q(x: Int) -> Text = busy.\n'
               'observe hits: Text = web.search(query=q(1)).\n')
        res = FX.check(src, CATALOGUE)
        self.assertFalse(res['ok'])
        self.assertTrue(any('personal data' in e['message'] for e in res['errors']), res['errors'])

    def test_a_definition_chosen_by_outside_text_is_steered_and_asks_the_owner(self):
        src = (PAGE + 'let go: Bool = page = "x".\nif go then\n  function f(x: Int) -> Text = "A".\nelse\n'
               '  function f(x: Int) -> Text = "B".\nend.\n' + SEND.format('f(1)'))
        self.assertEqual(verdict(src), (True, ['steered'], []))
        host = Host({'web.fetch': 'x', 'mail.send': {'sent': True}})
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        acts = [c for c in host.calls if c['kind'] == 'act']
        self.assertEqual([(c['args']['body'], c['influence'], c['needs_owner']) for c in acts], [('A', 'steered', True)])

    def test_a_builtin_spelled_result_is_refused_before_the_effect_runs(self):
        from symblic.kernel import language as S
        for src in ('act count = notes.write(text="a").\nshow count.\n',
                    'observe len: Text = web.fetch(url="https://example.test").\nshow len.\n'):
            with self.subTest(src=src):
                self.assertIn('is a builtin function name', ' '.join(e['message'] for e in S.check(src)['errors']))
        self.assertTrue(S.check('for count in [1, 2] do\n  show count.\nend.\n')['ok'])   # a loop variable may

    def test_a_saved_import_binds_the_names_it_lists(self):
        from symblic.kernel import language as S
        from symblic.lang import abstraction as L
        node = S.Node('import', 1, 1, module='rates', saved=True, alias=None, names=['Rate', 'other'])
        self.assertEqual(L.import_binds(node), ['Rate', 'other'])

    def test_the_run_labels_an_act_that_reads_outside_text_through_a_function(self):
        # A host refuses this program before it runs (the check above); a bare Run still labels the act from
        # the same flow, so a host that sees it anyway knows outside text wrote it
        src = 'function leak(x: Int) -> Text = page.\n' + PAGE + SEND.format('leak(1)')
        host = Host({'web.fetch': 'outside text', 'mail.send': {'sent': True}})
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        acts = [c for c in host.calls if c['kind'] == 'act']
        self.assertEqual([(c['args']['body'], c['influence'], c['needs_owner']) for c in acts],
                         [('outside text', 'untrusted', True)])


if __name__ == '__main__':
    unittest.main()

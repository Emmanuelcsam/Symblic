"""Finite assessment cannot infer a false predicate from a host inability."""
import unittest
from symblic.kernel import language as S
from symblic.kernel import run as R


class NoModels:
    def call(self, request):
        raise AssertionError('This zero-provider check must never dispatch a model.')


def run(source, cls=R.Run, **options):
    runner = cls(source, {}, NoModels(), {'side_effects': False, 'max_calls': 0, **options})
    return runner, runner.execute()


class FiniteResourceRegression(unittest.TestCase):
    def assert_inconclusive(self, source, cls=R.Run, reason='resource'):
        runner, result = run(source, cls)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['calls'], 0)
        self.assertNotEqual(result['error']['kind'], 'contradictory')
        self.assertIsNone(runner.kernel.env.lookup('candidate'))
        rec = result['determinacy']['asks'][0]
        self.assertEqual((rec['status'], rec['reason']), ('unassessed', reason))
        self.assertFalse(any('no possible answer' in w['message'] for w in result['warnings']))
        for d in result['evidence']['determinations']:
            self.assertNotIn(d['verdict'], ('determined', 'contradictory'))
        return result

    def test_representation_limit_is_not_contradiction(self):
        self.assert_inconclusive('ask candidate: Bool "Choose." by "kernel" with solve=true.\n'
            'ensure (candidate or not candidate) and len("a" * 100001) > 0.\n')

    def test_representation_limit_is_not_uniqueness(self):
        self.assert_inconclusive('ask candidate: Bool "Choose." by "kernel" with solve=true.\n'
            'ensure candidate or len("a" * 100001) > 0.\n')

    def test_optional_assessment_does_not_dispatch_after_representation_limit(self):
        self.assert_inconclusive('ask candidate: Bool "Choose." by "fake:a" with solve=false.\n'
            'ensure candidate or len("a" * 100001) > 0.\n')

    def test_positive_step_budget_does_not_hide_other_host_refusals(self):
        source = 'ask candidate: Bool "Choose." by "kernel" with solve=true.\nensure candidate.\n'
        for kind in ('budget', 'resource', 'unavailable'):
            with self.subTest(kind=kind):
                class RefusedRun(R.Run):
                    def _candidate(self, *args, **kwargs):
                        raise S.SymblicError('Independent checker cannot run.', kind=kind)
                self.assert_inconclusive(source, RefusedRun, reason=kind)

    def test_exhausted_global_steps_keep_budget_reason(self):
        class ExhaustedRun(R.Run):
            def _candidate(self, *args, **kwargs):
                self.kernel.budget.left = -1
                raise S.KernelLimitError('The kernel step budget ran out.')
        self.assert_inconclusive('ask candidate: Bool "Choose." by "kernel" with solve=true.\n'
            'ensure candidate.\n', ExhaustedRun, reason='budget')

    def test_ordinary_undefined_candidate_remains_a_semantic_rejection(self):
        runner, result = run('ask candidate: Int in 0..1 "Choose." by "kernel" with solve=true.\n'
            'ensure 1 / candidate = 1.\n')
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(runner.kernel.env.lookup('candidate').value, 1)
        self.assertEqual(result['determinacy']['asks'][0]['status'], 'determined')

    def test_genuine_contradiction_and_uniqueness_still_work(self):
        for predicate, expected in (('candidate and not candidate', 'contradictory'),
                                    ('candidate', 'determined')):
            with self.subTest(predicate=predicate):
                _runner, result = run('ask candidate: Bool "Choose." by "kernel" with solve=true.\n'
                    'ensure ' + predicate + '.\n')
                self.assertEqual(result['determinacy']['asks'][0]['status'], expected)

    def test_semantic_identity_changes(self):
        self.assertEqual(S.kernel_id()['ask_policy'], 4)


if __name__ == '__main__':
    unittest.main()

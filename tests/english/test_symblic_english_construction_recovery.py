"""Partial construction recovery keeps accepted steps and retries only the remaining ones.

Fake providers, temporary folders and the sandboxed JavaScript checker only: no model, node,
network or live store. The accepted prefix of a failed construction run is locally rechecked
and re-bound as exact literals; a later step is asked again (beta review E4, 2026-10-08)."""
import copy
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from symblic.kernel import language as S
from symblic.english import build as B
from symblic.js import check as J
from symblic.kernel.run import Run
from tests.english.test_symblic_english_build import CANDIDATES, FixtureWorker


class FailingWorker(FixtureWorker):
    """Answers every step from the fixture, except step four, which never passes its checks."""

    def __init__(self, fail_at=4):
        super().__init__()
        self.fail_at = fail_at

    def call(self, req):
        self.requests.append(copy.deepcopy({k: v for k, v in req.items() if k != 'stop'}))
        number = int(re.search(r'function named build_step_(\d+)\(', req['prompt']).group(1))
        code = CANDIDATES[number - 1]
        if number == self.fail_at:
            code = 'function build_step_4(head,age,height) {return head;}'
        return {'ok': True, 'text': '```js\n' + code + '\n```', 'json': None,
                'model': 'fixture', 'node': 'fixture', 'ms': 1}


@unittest.skipUnless(J.available(), 'Sandboxed JavaScript runtime is unavailable')
class Recovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = B.compile_source(B.EXAMPLE, retries=0, max_calls=12)
        cls.folder = tempfile.TemporaryDirectory(prefix='symblic-construction-first-')
        cls.addClassCleanup(cls.folder.cleanup)
        folder = cls.folder.name
        Path(folder, 'program.sym').write_text(cls.compiled['source'])
        Path(folder, 'instructions.english').write_text(B.EXAMPLE)
        worker = FailingWorker(4)
        options = {**cls.compiled['options'], 'by': 'fake:fixture', 'parallel': 1}
        report = Run(cls.compiled['source'], {}, worker, options, folder=folder).execute()
        if report['status'] != 'failed':
            raise AssertionError(report)
        cls.checkpoint = B.checkpoint(folder, recheck_seconds=60)
        cls.recovered = B.compile_source(B.EXAMPLE, retries=0, max_calls=12,
                                         artifacts=cls.checkpoint['artifacts'])

    def test_checkpoint_keeps_only_the_accepted_prefix(self):
        self.assertEqual(['built_step_1', 'built_step_2', 'built_step_3'], sorted(self.checkpoint['artifacts']))
        self.assertEqual({'examples_failed'}, {self.checkpoint['skipped']['built_step_4']})
        self.assertEqual({f'built_step_{n}' for n in range(5, 10)},
                         {name for name, why in self.checkpoint['skipped'].items()
                          if why == 'not_accepted'})
        self.assertEqual(hashlib.sha256(B.EXAMPLE.encode()).hexdigest(),
                         self.checkpoint['document_sha256'])
        for artifact in self.checkpoint['artifacts'].values():
            self.assertEqual(hashlib.sha256(artifact['code'].encode()).hexdigest(), artifact['code_sha256'])
            self.assertEqual(self.checkpoint['document_sha256'], artifact['document_sha256'])
            self.assertTrue(artifact['checks'][0]['passed'])

    def test_kept_steps_rebind_exact_bytes_and_only_remaining_steps_are_asked(self):
        c = self.recovered
        self.assertEqual(3, c['construction']['kept'])
        self.assertEqual(6, c['source'].count('\nask '))
        expected = {name: artifact['code'] for name, artifact in self.checkpoint['artifacts'].items()}
        actual = {s.name: ''.join(s.value.parts) for s in S.parse(c['source'])['statements']
                  if s.k == 'let' and s.name in expected}
        self.assertEqual(expected, actual)
        self.assertEqual('retained_artifact_bodies_only', c['construction']['candidate_bodies'])
        for unit in c['construction']['units']:
            reused = unit['binding'] in expected
            self.assertEqual('reused_artifact' if reused else 'model_request', unit['acquisition'])
            self.assertEqual('let' if reused else 'ask', unit['binding_kind'])
            self.assertEqual(reused, unit['artifact_code_sha256'] is not None)
            gate = c['source'].splitlines()[unit['gate_line'] - 1]
            self.assertTrue(gate.startswith('assert ' if reused else 'ensure '), gate)
            self.assertIn('omitted to bound this feedback', gate)
        self.assertTrue(S.check(c['source'], execution_profile='verified')['ok'])

    def test_only_remaining_steps_are_dispatched_and_the_run_completes(self):
        worker = FixtureWorker()
        with tempfile.TemporaryDirectory(prefix='symblic-construction-second-') as folder:
            options = {**self.recovered['options'], 'by': 'fake:fixture', 'parallel': 1}
            report = Run(self.recovered['source'], {}, worker, options, folder=folder).execute()
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual([f'ask built_step_{n}' for n in range(4, 10)],
                         [re.search(r'ask built_step_(\d+)', r['prompt']).group(0)
                          for r in worker.requests])
        self.assertEqual(25, len(report['outputs']))
        self.assertEqual([B._frame(32, 24, 8, tick) for tick in range(24)],
                         [o['canonical'] for o in report['outputs'][1:]])

    def test_changed_code_bytes_are_never_silently_kept(self):
        artifacts = copy.deepcopy(self.checkpoint['artifacts'])
        artifacts['built_step_1']['code'] += '\n'
        c = B.compile_source(B.EXAMPLE, retries=0, max_calls=12, artifacts=artifacts)
        # the tampered step is asked again; the steps that never depended on it stay kept
        self.assertEqual({'built_step_2', 'built_step_3'},
                         {u['binding'] for u in c['construction']['units']
                          if u['acquisition'] == 'reused_artifact'})
        self.assertEqual('model_request', c['construction']['units'][0]['acquisition'])
        self.assertEqual(7, c['source'].count('\nask '))

    def test_changed_document_invalidates_every_artifact(self):
        c = B.compile_source(B.EXAMPLE.replace('Matrix rain', 'Emerald curtains'), retries=0,
                             max_calls=12, artifacts=self.checkpoint['artifacts'])
        self.assertEqual(0, c['construction']['kept'])
        self.assertEqual(9, c['source'].count('\nask '))

    def test_retry_feedback_is_one_report_with_an_explicit_marker(self):
        compiled = B.compile_source(B.EXAMPLE, retries=1, max_calls=12)
        worker = FixtureWorker(wrong_first=True)
        with tempfile.TemporaryDirectory(prefix='symblic-construction-feedback-') as folder:
            options = {**compiled['options'], 'by': 'fake:fixture', 'parallel': 1}
            report = Run(compiled['source'], {}, worker, options, folder=folder).execute()
        self.assertEqual('done', report['status'], report.get('error'))
        prompt = worker.requests[1]['prompt']
        self.assertIn('expected', prompt)                    # the expected/got head survives
        self.assertIn(B.OMITTED_ASSEMBLY, prompt)            # the cut is explicit, never silent



if __name__ == '__main__':
    unittest.main()

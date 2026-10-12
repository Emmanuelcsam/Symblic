"""The preview (symblic/kernel/preview.py): the kernel runs up to the first ask and reports that ask's capsule.

No model, no host: the capture applicator refuses every call, and preview() runs in the bounded child process of
symblic/kernel/process_limits.py. These are the checks behind README step 2 (`tools/symblic preview`).
"""
import unittest

from symblic.kernel import preview as PV

ROOT_PROGRAM = ('ask root: Int in 1..9 "Find the positive integer whose square is nine."\n'
                'ensure root * root = 9 else retry.\nshow root.\n')


class PreviewInProcess(unittest.TestCase):
    """run_preview() is the child side; calling it directly needs no child process."""

    def test_the_first_ask_is_captured_and_nothing_is_answered(self):
        report = PV.run_preview({'source': 'let x = 2 + 3.\n' + ROOT_PROGRAM, 'by': 'ollama:qwen3:4b-instruct'})
        self.assertEqual(report['status'], 'paused', report.get('error'))
        self.assertEqual(report['next']['name'], 'root')
        self.assertEqual(report['next']['line'], 2)
        self.assertEqual(report['next']['app'], 'ollama:qwen3:4b-instruct')
        self.assertIn('Find the positive integer whose square is nine.', report['next']['prompt'])
        self.assertEqual(report['next']['schema']['properties']['answer'],
                         {'type': 'integer', 'minimum': 1, 'maximum': 9})
        self.assertEqual([b['name'] for b in report['bindings']], ['x'])       # formal steps before the ask ran

    def test_a_program_without_an_ask_runs_to_the_end(self):
        report = PV.run_preview({'source': 'let x = 2 + 3.\nshow x.\n'})
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertNotIn('next', report)
        self.assertEqual(report['outputs'][0]['value'], 5)

    def test_requests_are_refused_before_anything_runs(self):
        for body, words in (({'source': '   '}, 'Write a program first'),
                            ({'source': ROOT_PROGRAM, 'inputs': '[1, 2]'}, 'JSON object'),
                            ({'source': ROOT_PROGRAM, 'inputs': '{not json'}, 'JSON object'),
                            ({'source': ROOT_PROGRAM, 'by': 'Not An Applicator!'}, ''),
                            ({'source': ROOT_PROGRAM, 'options': {'determine': 'yes'}}, 'determine')):
            with self.subTest(body=body):
                with self.assertRaises(PV.RequestError) as caught:
                    PV.run_preview(body)
                self.assertIn(words, str(caught.exception))
                with self.assertRaises(PV.RequestError):
                    PV.preview(body)                     # refused in the caller, before a child starts


class PreviewInChild(unittest.TestCase):
    def test_preview_runs_in_the_bounded_child_and_returns_the_same_capsule(self):
        report = PV.preview({'source': ROOT_PROGRAM, 'by': 'ollama:qwen3:4b-instruct'})
        self.assertEqual(report['status'], 'paused', report.get('error'))
        self.assertEqual(report['next']['name'], 'root')
        self.assertEqual(report['next'], PV.run_preview({'source': ROOT_PROGRAM,
                                                         'by': 'ollama:qwen3:4b-instruct'})['next'])


if __name__ == '__main__':
    unittest.main()

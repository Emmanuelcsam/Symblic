"""kits/build_loop.py (compile a spec sheet, run it, keep what passed) and the Kirby kit's example tool.

A fake model answers the three units of examples/agent-handoff.sheet.md; nothing reaches a model or the network. The
JavaScript checks run in the kernel's sandbox (Node.js 22 and Linux Landlock); without it these tests are skipped.
"""
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from symblic.js import check as JS
from symblic.spec import sheets as SP

ROOT = Path(__file__).resolve().parents[2]          # the repository root
SPEC = importlib.util.spec_from_file_location('build_loop', ROOT / 'kits/build_loop.py')
LOOP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOOP)
SHEET = (ROOT / 'examples/agent-handoff.sheet.md').read_text()
CODE = {'double(x)': 'function double(x) { return x * 2; }',
        'ready()': 'function ready() { return "ready"; }',
        'next(x)': 'function next(x) { return double(x) + 1; }'}


class FakeModel:
    """Answers each unit with correct code, fenced the way a model would; counts the calls."""

    def __init__(self):
        self.asked = []

    def call(self, request):
        heading = request['prompt'].split('YOUR UNIT: `', 1)[1].split('`', 1)[0]
        self.asked.append(heading)
        return {'ok': True, 'text': 'Here it is.\n```js\n' + CODE[heading] + '\n```', 'json': None, 'ms': 1}

    def cancel_all(self):
        return 0


class NoModel:
    def call(self, request):
        raise AssertionError('a kept build must not ask a model')

    def cancel_all(self):
        return 0


@unittest.skipUnless(JS.available(), 'the JavaScript sandbox (Node.js 22, Linux Landlock) is unavailable')
class BuildLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='symblic-build-loop-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patcher = mock.patch('signal.signal')          # run_folder installs SIGTERM/SIGINT handlers
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_round_writes_its_records_and_a_kept_round_asks_no_model(self):
        first = self.tmp / 'run1'
        model = FakeModel()
        report = LOOP.run_build(SHEET, ['fake:model'], first, applicators=model, samples=1, retries=1, rounds=1)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(sorted(model.asked), sorted(CODE))
        for name in ('program.sym', 'meta.json', 'calls.jsonl', 'trace.jsonl', 'state.json'):
            self.assertTrue((first / name).is_file(), name)
        self.assertEqual(set(SP.accepted_units(str(first))), {'unit_double', 'unit_ready', 'unit_next'})
        rows = SP.diagnose(SHEET, str(first))
        self.assertEqual([r['accepted'] for r in rows], [True, True, True])

        second = self.tmp / 'run2'
        report = LOOP.run_build(SHEET, ['fake:model'], second, applicators=NoModel(), keep=first)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)
        self.assertIn('Units 1-3 are kept from an earlier build (run run1)', (second / 'program.sym').read_text())

    def test_a_used_folder_is_refused_before_anything_runs(self):
        used = self.tmp / 'used'
        used.mkdir()
        (used / 'keep.txt').write_text('earlier work')
        with self.assertRaises(SystemExit):
            LOOP.prepare_run(SHEET, ['fake:model'], used)
        self.assertEqual(sorted(p.name for p in used.iterdir()), ['keep.txt'])

    def test_call_ceilings_reach_the_run_options(self):
        folder = self.tmp / 'run'
        LOOP.prepare_run(SHEET, ['ollama:qwen3:4b-instruct'], folder, num_predict=512, call_timeout=60, max_calls=9)
        meta = __import__('json').loads((folder / 'meta.json').read_text())
        self.assertEqual(meta['options'], {'max_calls': 9, 'ollama_limits': {'num_predict': 512, 'timeout_seconds': 60}})
        self.assertIn('use by=["ollama:qwen3:4b-instruct"], route=search', (folder / 'program.sym').read_text())


@unittest.skipUnless(shutil.which('node') or JS.node_path(), 'Node.js is unavailable')
class KirbyExamples(unittest.TestCase):
    def test_every_example_of_the_4b_sheet_equals_the_reference(self):
        node = JS.node_path() or shutil.which('node')
        done = subprocess.run([node, str(ROOT / 'kits/kirby/reference/fill-sheet.mjs'), 'check',
                               str(ROOT / 'kits/kirby/sheets/kirby.sheet.md')],
                              capture_output=True, text=True, timeout=600, check=False)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn('39 units, 229 examples, 0 differing from the reference, 0 unfilled', done.stdout)


if __name__ == '__main__':
    unittest.main()

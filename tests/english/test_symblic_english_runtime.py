"""Real English compiler -> the kernel's runner through the `english` CLI, fake model requests, temporary folders.

These prove integration and durability, not model quality: the fake worker reads exactly the
selected capsule value and computes a response. No external provider or solver is available.
The host's HTTP `english/run` case moved to tests/integration/test_symblic_english_routes.py.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from symblic.providers import applicators as AP
from symblic.english import compiler as C
from symblic.english import authoring as A
from symblic.english import cli as CLI
from symblic.kernel import lockfile as K

FALLING = C.EXAMPLES['falling-number']['source']
CONTEXT = re.compile(r'^- (\w+) : [^=]+ = (.*)$', re.M)


def selected(prompt):
    return dict(CONTEXT.findall(prompt.split('CONTEXT', 1)[1].split('STATEMENT:', 1)[0]))


class FallingWorker:
    def __init__(self, wrong_once=False):
        self.requests = []
        self.wrong_once = wrong_once

    def call(self, request):
        self.requests.append(copy.deepcopy({key: request[key] for key in ('app', 'system', 'prompt', 'schema', 'messages')
                                            if key in request}))
        values = selected(request['prompt'])
        if len(values) != 1:
            raise AssertionError(f'One selected row expected: {values}')
        answer = 99 if self.wrong_once and len(self.requests) == 1 else int(next(iter(values.values()))) - 1
        return {'ok': True, 'json': {'answer': answer}, 'model': 'fake', 'node': 'isolated'}


class EnglishRuntime(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for patch in (mock.patch.object(AP, 'Applicators', side_effect=AssertionError('real model factory')),
                      mock.patch('signal.signal')):
            patch.start()
            self.addCleanup(patch.stop)

    def prepare(self, document=FALLING, **options):
        return A.prepare({'source': document, 'by': 'fake:falling', 'max_calls': 20, **options})

    def run_it(self, compiled, worker, name='falling'):
        folder = self.root / name
        with contextlib.redirect_stdout(io.StringIO()):
            report = CLI.run_compiled(compiled, folder, 'fake:falling', applicators=worker)
        return report, folder

    def frames(self, report):
        values = [row['value'] for row in report['outputs']]
        self.assertTrue(all(row['kind'] == 'grid' for row in values))
        return values

    def test_falling_six_fresh_asks_seven_frames_and_selected_context_only(self):
        document = 'Remember confidential is "UNSELECTED_SENTINEL_VALUE".\n' + FALLING
        compiled, worker = self.prepare(document), FallingWorker()
        report, folder = self.run_it(compiled, worker)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['asks'], report['calls'], len(worker.requests)), (6, 6, 6))
        frames = self.frames(report)
        self.assertEqual([frame['y'] for frame in frames], [6, 5, 4, 3, 2, 1, 0])
        self.assertTrue(all((frame['value'], frame['x'], frame['width'], frame['height']) == (7, 5, 20, 7)
                            for frame in frames))
        for index, request in enumerate(worker.requests):
            self.assertEqual(selected(request['prompt']), {compiled['names'][f'row {index}']: str(6 - index)})
            self.assertNotIn('UNSELECTED_SENTINEL_VALUE', request['prompt'])
            self.assertNotIn('UNSELECTED_SENTINEL_VALUE', request['system'])
            self.assertNotIn('messages', request)
        self.assertEqual((folder / 'instructions.english').read_text(), document)

    def test_preview_shows_exactly_the_first_request(self):
        compiled, worker = self.prepare(), FallingWorker()
        preview = CLI.preview(compiled, 'fake:falling')
        error = preview.get('error') or {}
        if preview.get('status') == 'failed' and error.get('kind') == 'unavailable':
            # the preview runs in the kernel's bounded child process (symblic.kernel.process_limits)
            self.skipTest('the kernel preview child is unavailable here: ' + str(error.get('message')))
        report, _ = self.run_it(compiled, worker)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(worker.requests[0]['prompt'], preview['next']['prompt'])

    def test_one_wrong_model_answer_retries_before_displaying_and_advancing(self):
        worker = FallingWorker(wrong_once=True)
        report, _ = self.run_it(self.prepare(), worker)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(worker.requests), 7)
        self.assertEqual(selected(worker.requests[0]['prompt']), selected(worker.requests[1]['prompt']))
        self.assertEqual([frame['y'] for frame in self.frames(report)], [6, 5, 4, 3, 2, 1, 0])
        self.assertEqual(report['calls'], 7)

    def test_zero_model_calls_refuses_and_retains_the_initial_display(self):
        worker = FallingWorker()
        report, _ = self.run_it(self.prepare(max_calls=0), worker)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'budget')
        self.assertEqual((report['calls'], worker.requests), (0, []))
        self.assertEqual([frame['y'] for frame in self.frames(report)], [6])

    def test_english_resume_and_portable_replay_keep_frames_and_original_source(self):
        compiled, worker = self.prepare(), FallingWorker()
        first, folder = self.run_it(compiled, worker)
        self.assertEqual(first['status'], 'done', first.get('error'))
        kept = {name: (folder / name).read_bytes() for name in ('program.sym', 'instructions.english', 'meta.json')}
        with mock.patch.object(C, 'compile_source', side_effect=AssertionError('saved run recompiled')), \
                contextlib.redirect_stdout(io.StringIO()):
            resumed = CLI.resume(folder, applicators=worker)
            lock = K.make_lock(str(folder))
            replay = K.replay(lock)
        self.assertEqual(len(worker.requests), 6)
        self.assertEqual(resumed['status'], 'done', resumed.get('error'))
        self.assertEqual(self.frames(resumed), self.frames(first))
        self.assertTrue(replay['ok'], replay.get('error'))
        self.assertEqual((replay['calls'], replay['refused']), (0, []))
        self.assertEqual(self.frames(replay['report']), self.frames(first))
        self.assertEqual(lock['authoring'], compiled['authoring'])
        self.assertEqual(replay['recorded_authoring']['document'], FALLING)
        self.assertEqual(kept, {name: (folder / name).read_bytes() for name in kept})



class EnglishBoundaryRepairs(unittest.TestCase):
    def test_loaded_compiler_drift_refuses_before_stamping_false_provenance(self):
        probe = r'''
import importlib.util, json, pathlib, sys, tempfile
sys.path.insert(0, sys.argv[1])
import symblic.english
from symblic.english import authoring as A
original = pathlib.Path(sys.argv[1], 'symblic', 'english', 'compiler.py').read_bytes()
document = 'Remember seven is 7.\nShow seven.\n'
with tempfile.TemporaryDirectory() as directory:
    # a private copy laid out like the repository, so the compiler's repository path resolves inside it
    path = pathlib.Path(directory, 'symblic', 'english', 'compiler.py')
    path.parent.mkdir(parents=True)
    results = {}
    for mode in ('before', 'during'):
        path.write_bytes(original)
        spec = importlib.util.spec_from_file_location('symblic.english.compiler', path)
        compiler = importlib.util.module_from_spec(spec)
        sys.modules['symblic.english.compiler'] = compiler
        symblic.english.compiler = compiler
        spec.loader.exec_module(compiler)
        baseline = A.prepare({'source': document})
        assert baseline['authoring']['compiler_sha256'] == compiler._symblic_import_identity['sha256']
        if mode == 'before':
            path.write_bytes(original + b'\n# changed after import\n')
        else:
            real_compile = compiler.compile_source
            def compile_then_change(*args, **kwargs):
                result = real_compile(*args, **kwargs)
                path.write_bytes(original + b'\n# changed during compilation\n')
                return result
            compiler.compile_source = compile_then_change
        try:
            A.prepare({'source': document})
        except ValueError as error:
            assert 'restart' in str(error).lower(), error
            results[mode] = str(error)
        else:
            raise AssertionError('stale loaded compiler accepted')
    print(json.dumps(results))
'''
        root = Path(__file__).resolve().parents[2]          # the repository root
        # about 7 s on an idle machine; the bound is generous because a loaded machine can take several times that
        completed = subprocess.run([sys.executable, '-B', '-c', probe, str(root)],
                                   capture_output=True, text=True, timeout=180)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(set(json.loads(completed.stdout)), {'before', 'during'})

    def test_unicode_digit_like_tokens_are_positioned_refusals_not_attribute_errors(self):
        for value in ('²', '-²', '⑦', '³'):
            with self.subTest(value=value):
                result = C.check_source(f'Remember quantity is {value}.\n')
                self.assertFalse(result['ok'])
                self.assertEqual(result['errors'][0]['code'], 'ENG_SYNTAX')
                self.assertEqual(result['errors'][0]['line'], 1)

    def test_decoded_escape_length_has_the_same_bound_as_plain_text(self):
        for token in ('a', r'\n', r'\t', r'\"', r'\\'):
            with self.subTest(token=token):
                at_limit = 'Remember message is "' + token * C.MAX_STRING + '".\nShow message.\n'
                self.assertTrue(C.check_source(at_limit)['ok'])
                beyond = 'Remember message is "' + token * (C.MAX_STRING + 1) + '".\nShow message.\n'
                result = C.check_source(beyond)
                self.assertFalse(result['ok'])
                self.assertEqual(result['errors'][0]['code'], 'ENG_LIMIT')

    def test_grid_static_limits_match_browser_capacity(self):
        for width, height, allowed in ((100, 1, True), (50, 50, True), (101, 1, False),
                                       (1, 101, False), (51, 50, False)):
            with self.subTest(width=width, height=height):
                source = f'Display 7 at column 0 and row 0 on a grid {width} columns by {height} rows.\n'
                result = C.check_source(source)
                self.assertEqual(result['ok'], allowed, result)
                if not allowed:
                    self.assertEqual(result['errors'][0]['code'], 'ENG_GEOMETRY')

    def test_model_generated_grid_dimensions_are_checked_before_renderable_output(self):
        from symblic.kernel.run import Run
        source = ('Ask for width as a whole number: "Choose a grid width.".\n'
                  'Display 7 at column 0 and row 0 on a grid width columns by 1 rows.\n')
        compiled = C.compile_source(source)
        for width, status in ((100, 'done'), (101, 'failed')):
            with self.subTest(width=width):
                app = mock.Mock()
                app.call.return_value = {'ok': True, 'json': {'answer': width}, 'model': 'fake', 'node': 'isolated'}
                report = Run(compiled['source'], {}, app, {**compiled['options'], 'by': 'fake:grid'}).execute()
                self.assertEqual(report['status'], status, report.get('error'))
                self.assertEqual(app.call.call_count, 1)
                self.assertEqual(len(report['outputs']), 1 if status == 'done' else 0)


if __name__ == '__main__':
    unittest.main()

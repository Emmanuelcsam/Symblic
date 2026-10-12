"""D17: resource exhaustion is neither a wrong answer nor permission to retry it."""
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.kernel.test_symblic_code import Replies, js

try:  # the host engine's preview and API: host-only (integration/host/symblic_engine.py imports the host dashboard)
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise
    E = None
from symblic.js import check as JS
from symblic.lang import abstraction as L
from symblic.kernel import process_limits as P
from symblic.kernel.run import Run

ROOT = Path(P.__file__).resolve().parents[2]          # the repository root


class InconclusiveChecks(unittest.TestCase):
    def test_timeout_memory_and_unavailable_are_never_failed_examples(self):
        for kind in ('timeout', 'memory', 'oom', 'resource', 'unavailable'):
            with self.subTest(kind=kind), mock.patch.object(JS, 'evaluate', return_value=[
                    {'ok': False, 'kind': kind, 'error': 'fixture resource exhausted'}]):
                with self.assertRaises(JS.JsError) as got:
                    JS.test('function f(){return 1}', [('f()', '1')])
                self.assertEqual(got.exception.kind, 'resource')
                self.assertIn('inconclusive', got.exception.message)
                with self.assertRaises(JS.JsError) as got:
                    JS._js_run(None, None, '', '1')
                self.assertEqual(got.exception.kind, 'resource')

    def test_ordinary_inline_escalate_and_search_never_repair_or_blame_resource(self):
        forms = [
            ('with retries=2', 'let check = js_test(f, [["f()", "1"]]).\nensure check.passed else retry because check.report.'),
            ('with retries=2', 'ensure js_test(f, [["f()", "1"]]).passed else retry.'),
            ('with route=escalate, retries=2', 'let check = js_test(f, [["f()", "1"]]).\nensure check.passed else retry because check.report.'),
            ('with route=search, samples=1, rounds=2, retries=2', 'let check = js_test(f, [["f()", "1"]]).\nensure check.passed else retry because check.report.'),
        ]
        for kind in ('resource', 'unavailable', 'budget'):
            for options, checks in forms:
                with self.subTest(kind=kind, options=options, checks=checks):
                    apps = Replies({'a': [js('function f(){return 1}')], 'b': [js('function f(){return 1}')]})
                    source = f'ask f: Code js "write f" by "fake:a" {options}.\n{checks}\nshow f.\n'
                    with mock.patch.object(JS, 'evaluate', side_effect=JS.JsError('check incomplete', kind=kind)):
                        result = Run(source, applicators=apps, options={'parallel': 1}).execute()
                    self.assertEqual(result['error']['kind'], kind, result)
                    self.assertEqual(len(apps.requests), 1, result)
                    self.assertEqual(result.get('diagnoses'), [])
                    self.assertFalse(any('REJECTED' in row['prompt'] for row in apps.requests))

    def test_resource_signal_or_memory_inside_provider_call_does_not_trigger_retry(self):
        for error in (MemoryError(), JS.JsError('CPU budget exhausted', kind='resource')):
            apps = mock.Mock()
            apps.call.side_effect = error
            result = Run('ask x: Int "choose one" by "fake:a" with retries=2.\nshow x.\n',
                         applicators=apps).execute()
            self.assertEqual(result['error']['kind'], 'resource', result)
            self.assertEqual(apps.call.call_count, 1)

    def test_test_blocks_stop_inconclusive_without_counting_failure_or_certifying(self):
        source = 'test "resource" do\n assert js_test("", [["1", "1"]]).passed.\nend.\ntest "later" do\n assert true.\nend.\n'
        with mock.patch.object(JS, 'evaluate', side_effect=JS.JsError('adapter missing', kind='unavailable')):
            result = L.run_tests(source)
            certificate = L.certify(source, ['fake:a'], lambda _: None)
        self.assertEqual((result['passed'], result['failed'], result['inconclusive']), (0, 0, 1), result)
        self.assertEqual([row['status'] for row in result['tests']], ['inconclusive'])
        self.assertFalse(result['ok'])
        self.assertFalse(certificate['all'])
        self.assertEqual(certificate['cohorts'][0]['inconclusive'], 1)

    def test_top_level_resource_is_not_skipped_as_missing_test_input(self):
        with mock.patch.object(JS, 'evaluate', side_effect=JS.JsError('out of memory', kind='resource')):
            result = L.run_tests('let x = js_run("", "1").\ntest "uses x" do\n assert x = 1.\nend.\n')
        self.assertEqual(result['error']['kind'], 'resource')
        self.assertEqual((result['passed'], result['failed']), (0, 0))

    def test_abrupt_js_child_and_oom_are_unresolved(self):
        for code, stderr in ((-9, b''), (-24, b''), (-6, b'FATAL ERROR: Reached heap limit')):
            proc = mock.Mock(returncode=code)
            with self.subTest(code=code), mock.patch.object(JS.subprocess, 'Popen', return_value=proc), \
                    mock.patch.object(JS, 'available', return_value=True), \
                    mock.patch.object(JS, '_communicate_bounded', return_value=(b'', stderr)):
                rows = JS.evaluate('', ['1'])
            self.assertEqual(rows[0]['kind'], 'resource')


class ChildBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = {**os.environ, 'AUTOMATION_DATA_DIR': str(self.home/'automation'),
                    'PYTHONDONTWRITEBYTECODE': '1'}

    def cli(self, source, *args):
        script = self.home/'entry.py'
        script.write_text(source)
        return subprocess.run([sys.executable, '-I', str(ROOT/'symblic/kernel/process_limits.py'), 'cli', '--file', str(script), *args],
                              capture_output=True, text=True, timeout=120, env=self.env, check=False)

    @unittest.skipIf(E is None, 'host-only: needs the original host engine (integration/host/symblic_engine.py)')
    def test_optional_api_hooks_fail_visibly_when_services_are_not_updated(self):
        import integration.host as host_package
        import symblic.authoring as authoring_package
        for prefix, package, name in (('supervisor/', host_package, 'symblic_supervisor_api'),
                                      ('workcards/', authoring_package, 'workcards')):
            handler = mock.Mock()
            hidden = package.__dict__.pop(name, None)      # an earlier import leaves the submodule on its package
            try:
                with mock.patch.dict(sys.modules, {f'{package.__name__}.{name}': None}):
                    self.assertTrue(E.handle(handler, 'GET', prefix + 'catalog', {}))
            finally:
                if hidden is not None:
                    setattr(package, name, hidden)
            self.assertEqual(handler.send_json.call_args.args[1], 503)

    @unittest.skipIf(E is None, 'host-only: needs the original host engine (integration/host/symblic_engine.py)')
    def test_import_and_api_caller_never_change_parent_limits(self):
        before = [resource.getrlimit(x) for x in (resource.RLIMIT_CPU, resource.RLIMIT_AS)]
        with self.assertRaises(P.BoundaryUnavailable):
            P._apply_limits('preview')
        with mock.patch.dict(os.environ, self.env):
            result = E.preview({'source': 'let x = 2 + 3.\nshow x.\n'})
        after = [resource.getrlimit(x) for x in (resource.RLIMIT_CPU, resource.RLIMIT_AS)]
        self.assertEqual(before, after)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['outputs'][0]['text'], '5')
        self.assertFalse((self.home/'automation').exists())

    def test_cli_and_module_entrypoints_use_real_limits_and_clean_up_admitted_instances(self):
        done = self.cli('import resource,json,sys,types\n'
                        'sys.modules["symblic.providers.applicators"] = types.SimpleNamespace(cancel_everything=lambda: print("CLEANUP"))\n'
                        'print(json.dumps({"cpu":resource.getrlimit(resource.RLIMIT_CPU), '
                        '"as":resource.getrlimit(resource.RLIMIT_AS), "pid":__import__("os").getpid()}))\n')
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        limits = json.loads(lines[0])
        self.assertEqual(limits['cpu'], [120, 122])
        self.assertEqual(limits['as'], [P.ADDRESS_SPACE_BYTES]*2)
        self.assertEqual(lines[-1], 'CLEANUP')
        self.assertNotEqual(limits['pid'], os.getpid())

    def test_cli_address_exhaustion_returns_inconclusive_without_allocating_it(self):
        done = self.cli('bytearray(3 * 1024 * 1024 * 1024)\n', '--json')
        self.assertEqual(done.returncode, 75, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result['error']['kind'], 'resource')
        self.assertIn('address-space', result['error']['message'])

    def test_cli_cpu_exhaustion_returns_inconclusive(self):
        # the limit counts from the CPU the child already used (importing the kernel, capturing its execution
        # snapshot), so the script exhausts it inside its own loop on a slow or busy machine too
        done = self.cli('import resource\nu = resource.getrusage(resource.RUSAGE_SELF)\n'
                        'used = int(u.ru_utime + u.ru_stime)\n'
                        'resource.setrlimit(resource.RLIMIT_CPU, (used + 1, used + 2))\nwhile True: pass\n', '--json')
        self.assertEqual(done.returncode, 75, done.stderr)
        self.assertEqual(json.loads(done.stdout)['error']['kind'], 'resource')

    def test_unavailable_boundary_and_output_timeout_never_become_failed_tests(self):
        with mock.patch.object(P.subprocess, 'Popen', side_effect=OSError('fixture')):
            result = P.call_bounded('tests', {'source': 'test "x" do assert true. end.'})
        self.assertEqual((result['failed'], result['error']['kind']), (0, 'unavailable'))
        self.assertTrue(result['incomplete'])
        # A real sleeping child is killed/reaped; this substitutes no host/live process.
        original = subprocess.Popen
        children = []
        def spawn(*_args, **_kwargs):
            child = original([sys.executable, '-I', '-c', 'import time; time.sleep(20)'], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            children.append(child)
            return child
        with mock.patch.object(P.subprocess, 'Popen', side_effect=spawn), mock.patch.dict(P.WALL_SECONDS, {'tests': .05}):
            result = P.call_bounded('tests', {'source': ''})
        self.assertEqual(result['error']['kind'], 'resource')
        self.assertEqual(result['failed'], 0)
        self.assertIsNotNone(children[0].poll())

    def test_js_child_dies_with_its_request_worker(self):
        marker = self.home/'child-ready'
        child_code = 'import pathlib,time; pathlib.Path(' + repr(str(marker)) + ').write_text("ready"); time.sleep(20)'
        owner_code = ('import os,subprocess,sys,time\n'
                      'p=subprocess.Popen([sys.executable,"-I",sys.argv[1],"js","10",str(os.getpid()),"--",'
                      'sys.executable,"-I","-c",sys.argv[2]])\n'
                      'print(p.pid,flush=True)\n'
                      'time.sleep(20)\n')
        owner = subprocess.Popen([sys.executable, '-I', '-c', owner_code, str(ROOT/'symblic/kernel/process_limits.py'), child_code],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        child = int(owner.stdout.readline())
        try:
            until = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < until:
                time.sleep(.02)
            self.assertTrue(marker.exists(), 'child never reached its bounded entrypoint')
            owner.kill()
            owner.wait(timeout=5)
            until = time.monotonic() + 5
            active = True
            while active and time.monotonic() < until:
                try:
                    status = Path(f'/proc/{child}/status').read_text()
                    active = not any(line.startswith('State:') and 'Z' in line for line in status.splitlines())
                except FileNotFoundError:
                    active = False
                if active:
                    time.sleep(.02)
            self.assertFalse(active, 'an owned JS child survived its request worker')
        finally:
            if owner.poll() is None:
                owner.kill()
            owner.wait(timeout=5)
            owner.stdout.close()
            owner.stderr.close()
            try:
                os.kill(child, 9)
            except ProcessLookupError:
                pass

    @unittest.skipUnless(JS.available(), 'sandboxed Node unavailable')
    def test_tests_child_retains_js_sandbox_and_semantic_results(self):
        with mock.patch.dict(os.environ, self.env):
            tests = P.call_bounded('tests', {'source': 'test "js" do\n assert js_test("", [["1", "2"]]).passed.\nend.\n'})
        self.assertEqual((tests['passed'], tests['failed'], tests['inconclusive']), (0, 1, 0), tests)

    @unittest.skipUnless(JS.available(), 'sandboxed Node unavailable')
    @unittest.skipIf(E is None, 'host-only: needs the original host engine (integration/host/symblic_engine.py)')
    def test_preview_child_retains_js_sandbox_and_semantic_results(self):
        with mock.patch.dict(os.environ, self.env):
            preview = E.preview({'source': 'let x = js_run("const four = 4;", "four").\nshow x.\n'})
        self.assertEqual(preview['status'], 'done', preview)
        self.assertEqual(preview['outputs'][0]['text'], '4')


if __name__ == '__main__':
    unittest.main()

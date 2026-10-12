"""symblic.providers.applicators: configuration, the fake, a local command and Ollama over HTTP.

Every Ollama test talks to a small fake Ollama server this file starts on 127.0.0.1 (a random port); every
command test runs a short Python script. No model, no network beyond loopback, no agent CLI.
"""

import http.server
import json
import os
import sys
import tempfile
import textwrap
import threading
import time
import unittest

from symblic.kernel import language as S
from symblic.kernel import run as SR
from symblic.providers import applicators as A
from symblic.providers import ollama_call as OC

DIGEST = 'sha256:' + 'ab' * 32


def req(spec, **kw):
    r = {'app': S.parse_applicator(spec), 'system': 'SYSTEM TEXT', 'prompt': 'PROMPT TEXT',
         'schema': {'type': 'object', 'properties': {'answer': {'type': 'integer'}}, 'required': ['answer']},
         'sample': 0, 'temperature': 0, 'seed': 7, 'effort': 'low', 'tools': 'none', 'stop': threading.Event()}
    r.update(kw)
    return r


class FakeOllama:
    """A loopback HTTP server that answers /api/tags and /api/generate like Ollama 0.9 does."""

    def __init__(self, models=('tiny:latest',), answer='{"answer": 8}', delay=0.0, status=200):
        self.models, self.answer, self.delay, self.status = list(models), answer, delay, status
        self.bodies, self.tags_reads = [], 0
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, value):
                raw = json.dumps(value).encode()
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass                    # a cancellation test closed the connection first: expected

            def do_GET(self):
                if self.path != '/api/tags':
                    return self.reply(404, {'error': 'not found'})
                fake.tags_reads += 1
                self.reply(200, {'models': [{'name': m, 'model': m, 'digest': DIGEST[7:], 'size': 1000}
                                            for m in fake.models]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fake.bodies.append(body)
                if fake.delay:
                    time.sleep(fake.delay)
                if fake.status != 200:
                    return self.reply(fake.status, {'error': 'model failed to load'})
                self.reply(200, {'model': body['model'], 'response': fake.answer, 'done': True,
                                 'done_reason': 'stop', 'prompt_eval_count': 31, 'eval_count': 5,
                                 'total_duration': 2_000_000, 'eval_duration': 1_000_000})

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()

    def apps(self, extra='', **env):
        hosts = f'local=127.0.0.1:{self.port}' + (',' + extra if extra else '')
        return A.Applicators(run_id='test', environ={'SYMBLIC_OLLAMA_HOSTS': hosts, **env})


class Configuration(unittest.TestCase):
    def test_default_host_and_entries(self):
        self.assertEqual(A.ollama_hosts(''), {'127.0.0.1:11434': {'base': 'http://127.0.0.1:11434',
                                                                  'hostport': '127.0.0.1:11434'}})
        hosts = A.ollama_hosts('127.0.0.1, gpu=192.0.2.10:8080 , https://Box.Example:443')
        self.assertEqual(list(hosts), ['127.0.0.1:11434', 'gpu', 'box.example:443'])
        self.assertEqual(hosts['gpu']['base'], 'http://192.0.2.10:8080')
        self.assertEqual(hosts['box.example:443']['base'], 'https://box.example:443')

    def test_malformed_or_repeated_entries_are_visible_errors(self):
        for text in ('local=', 'bad name=127.0.0.1', 'ftp://host', '127.0.0.1:99999', 'a=h1,a=h2', 'h1,h1:11434'):
            with self.subTest(text=text), self.assertRaises(A.ConfigError):
                A.ollama_hosts(text)

    def test_commands_come_only_from_their_own_variable(self):
        env = {'SYMBLIC_COMMAND_MY_AGENT': 'agent -p --flag "two words"', 'SYMBLIC_COMMAND_EMPTY': '  '}
        self.assertEqual(A.command_variable('my-agent'), 'SYMBLIC_COMMAND_MY_AGENT')
        self.assertEqual(A.command_argv('my-agent', env), ['agent', '-p', '--flag', 'two words'])
        self.assertIsNone(A.command_argv('empty', env))
        self.assertIsNone(A.command_argv('sh', env))                    # never a bare executable from PATH
        self.assertIsNone(A.command_argv('../x', env))
        self.assertEqual(A.configured_commands(env), ['my_agent'])

    def test_context_buckets_and_refusal(self):
        self.assertEqual(A.context_tokens(3000), 8192)                 # 1000 + 256 + 4096 reply room
        self.assertEqual(A.context_tokens(3000, num_predict=512), 4096)
        self.assertEqual(A.context_tokens(3000, num_predict=512, cap=3000), 3000)
        self.assertIsNone(A.context_tokens(3000, num_predict=512, cap=1500))
        self.assertEqual(A.context_tokens(300, num_predict=64, cap=1024), 1024)

    def test_ollama_format_narrows_and_refuses(self):
        schema = {'$defs': {'n': {'type': 'integer', 'description': 'dropped'}},
                  'type': 'object', 'title': 'dropped', 'properties': {'answer': {'$ref': '#/$defs/n'},
                                                                      'code': {'type': 'string', 'pattern': 'a+'}}}
        self.assertEqual(A.ollama_format(schema), {
            'type': 'object', 'properties': {'answer': {'type': 'integer'},
                                             'code': {'type': 'string', 'pattern': '^a+'}},
            'required': ['answer', 'code'], 'additionalProperties': False})
        self.assertEqual(A.ollama_format({'type': ['string', 'null']}),
                         {'anyOf': [{'type': 'string'}, {'type': 'null'}]})
        for bad in ([], {'not': {}}, {'$ref': '#/$defs/missing'}, {'type': 'date'}, False,
                    {'type': 'array', 'items': False}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                A.ollama_format(bad)


class FakeAndRouting(unittest.TestCase):
    def test_fake_answers_records_and_fails_without_an_answer(self):
        fake = A.FakeApplicators({'answer': 4}, by_label={'fake:b': 'plain text',
                                                          'fake:c': lambda label, prompt, request: {'__error__': 'no'}})
        apps = A.Applicators(fake=fake, environ={})
        out = apps.call(req('fake:a'))
        self.assertEqual((out['ok'], out['json'], out['model_identity']['reason']), (True, {'answer': 4},
                                                                                       'fake_applicator'))
        self.assertEqual(apps.call(req('fake:b'))['text'], 'plain text')
        self.assertEqual(apps.call(req('fake:c')), {**apps.call(req('fake:c')), 'ok': False, 'error': 'no'})
        self.assertNotIn('stop', fake.requests[0])
        self.assertFalse(A.FakeApplicators().call(req('fake:x'))['ok'])
        self.assertTrue(A.Applicators(environ={}).call(req('fake:a'))['fatal'])

    def test_unshipped_engines_are_refused_with_a_hint(self):
        apps = A.Applicators(environ={})
        for spec in ('claude:haiku', 'codex', 'gemini:pro', 'council:panel'):
            with self.subTest(spec=spec):
                out = apps.call(req(spec))
                self.assertFalse(out['ok'])
                self.assertTrue(out['fatal'] and out['refused'])
                self.assertIn('command:', out['error'])
                self.assertEqual(out['model_identity']['status'], 'unavailable')
        self.assertIn('kernel does not answer', apps.call(req('kernel'))['error'])

    def test_legacy_keywords_change_nothing(self):
        apps = A.Applicators(owner_label='x', run_id='r', thermal=True, allow_web=False, avoid='a', environ={})
        self.assertEqual((apps.owner, apps.run_id), ('x', 'r'))

    def test_status_without_probe_contacts_nothing(self):
        status = A.engines_status()
        self.assertFalse(status['ollama']['probed'])
        self.assertIn('ollama', status)
        self.assertFalse(status['claude']['installed'])


SCRIPT = textwrap.dedent('''
    import json, os, sys, time
    text = sys.stdin.read()
    mode = sys.argv[1]
    if mode == 'echo':
        schema = json.load(open(os.environ['SYMBLIC_SCHEMA_FILE']))
        print(json.dumps({'answer': 8, 'stdin': text, 'schema': schema, 'effort': os.environ['SYMBLIC_EFFORT'],
                          'cwd': os.getcwd(), 'name': os.environ['SYMBLIC_COMMAND_NAME']}))
    elif mode == 'fail':
        print('it went wrong', file=sys.stderr)
        sys.exit(3)
    elif mode == 'sleep':
        time.sleep(30)
''')


class Command(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.script = os.path.join(self.tmp.name, 'agent.py')
        with open(self.script, 'w', encoding='utf-8') as f:
            f.write(SCRIPT)

    def apps(self, mode, **env):
        return A.Applicators(environ={**os.environ, 'SYMBLIC_COMMAND_AGENT': f'{sys.executable} {self.script} {mode}',
                                      **env})

    def test_prompt_on_stdin_schema_file_and_fresh_directory(self):
        out = self.apps('echo').call(req('command:agent', effort='high'))
        self.assertTrue(out['ok'], out)
        seen = json.loads(out['text'])
        self.assertEqual(out['json'], seen)
        self.assertEqual(seen['stdin'], 'SYSTEM TEXT\n\nPROMPT TEXT')
        self.assertEqual(seen['schema'], req('command:agent')['schema'])
        self.assertEqual((seen['effort'], seen['name']), ('high', 'agent'))
        self.assertFalse(os.path.exists(seen['cwd']))                 # the temporary directory is gone
        self.assertEqual((out['node'], out['model'], out['model_identity']['reason']),
                         ('local', 'agent', 'command_reports_no_weight_digest'))

    def test_failure_exit_status_and_stderr_tail(self):
        out = self.apps('fail').call(req('command:agent'))
        self.assertFalse(out['ok'])
        self.assertIn('exited with status 3', out['error'])
        self.assertIn('it went wrong', out['error'])

    def test_unconfigured_or_misplaced_commands_are_refused(self):
        apps = A.Applicators(environ={})
        out = apps.call(req('command:agent'))
        self.assertTrue(out['refused'] and out['fatal'])
        self.assertIn('SYMBLIC_COMMAND_AGENT', out['error'])
        out = self.apps('echo').call(req('command:agent@node-a'))
        self.assertTrue(out['refused'])

    def test_wall_bound_stop_and_cancel_end_the_process_group(self):
        started = time.monotonic()
        out = self.apps('sleep', SYMBLIC_CALL_WALL_S='2').call(req('command:agent'))
        self.assertIn('timed out', out['error'])
        self.assertLess(time.monotonic() - started, 15)
        apps = self.apps('sleep')
        request = req('command:agent')
        threading.Timer(1.0, request['stop'].set).start()
        out = apps.call(request)
        self.assertEqual((out['ok'], out['fatal']), (False, True))
        self.assertIn('stopped', out['error'])
        result = {}
        worker = threading.Thread(target=lambda: result.update(apps.call(req('command:agent'))))
        worker.start()
        time.sleep(1.0)
        self.assertEqual(A.cancel_everything(), 1)
        worker.join(15)
        self.assertIn('cancelled', result['error'])

    def test_no_time_left_never_starts_the_command(self):
        out = self.apps('echo').call(req('command:agent', deadline=time.time() - 1))
        self.assertTrue(out['refused'] and out['fatal'])


class Ollama(unittest.TestCase):
    def test_generate_request_reply_usage_and_observed_identity(self):
        with FakeOllama() as server:
            out = server.apps().call(req('ollama:tiny@local', temperature=0.25, seed=3,
                                         ollama_limits={'num_predict': 100, 'num_ctx': 4096}))
        self.assertTrue(out['ok'], out)
        self.assertEqual(out['json'], {'answer': 8})
        body = server.bodies[0]
        self.assertEqual((body['model'], body['system'], body['prompt'], body['stream']),
                         ('tiny', 'SYSTEM TEXT', 'PROMPT TEXT', False))
        self.assertEqual(body['options'], {'temperature': 0.25, 'seed': 3, 'num_ctx': 4096, 'num_predict': 100})
        self.assertEqual(body['format']['additionalProperties'], False)
        self.assertNotIn('keep_alive', body)
        self.assertEqual(out['usage'], {'input_tokens': 31, 'output_tokens': 5, 'duration_ms': 2, 'eval_ms': 1})
        identity = out['model_identity']
        self.assertEqual((identity['status'], identity['digest'], identity['node'], identity['resolved']),
                         ('observed', DIGEST, 'local', 'tiny:latest'))
        self.assertEqual(identity['observer_sha256'], OC.observer_sha256())
        self.assertEqual(OC.check(identity), identity)
        self.assertEqual(server.tags_reads, 2)

    def test_hosts_by_name_by_address_or_only_when_configured(self):
        with FakeOllama() as server:
            apps = server.apps()
            self.assertTrue(apps.call(req(f'ollama:tiny@127.0.0.1:{server.port}'))['ok'])
            self.assertTrue(apps.call(req('ollama:tiny'))['ok'])           # the only configured host
            out = apps.call(req('ollama:tiny@other.example:11434'))
            self.assertTrue(out['refused'] and out['fatal'])
            self.assertIn('SYMBLIC_OLLAMA_HOSTS', out['error'])
        self.assertEqual(len(server.bodies), 2)

    def test_placement_prefers_a_host_that_lists_the_model(self):
        with FakeOllama(models=('other:latest',)) as first, FakeOllama() as second:
            apps = A.Applicators(environ={'SYMBLIC_OLLAMA_HOSTS':
                                          f'a=127.0.0.1:{first.port},b=127.0.0.1:{second.port}'})
            A._inventory.update(key=None, t=0.0, rows=[])
            self.assertEqual(apps.pick_node('ollama', 'tiny'), 'b')
            self.assertTrue(apps.call(req('ollama:tiny'))['ok'])
        self.assertEqual((len(first.bodies), len(second.bodies)), (0, 1))

    def test_refusals_before_any_generation(self):
        with FakeOllama(models=('else:latest',)) as server:
            out = server.apps().call(req('ollama:tiny@local'))
            self.assertTrue(out['refused'] and out['fatal'])
            self.assertIn('ollama pull tiny', out['error'])
            out = server.apps().call(req('ollama:tiny@local', schema={'not': {}}))
            self.assertTrue(out['refused'] and out['fatal'])
            out = server.apps().call(req('ollama:tiny@local', prompt='x' * 300_000))
            self.assertTrue(out['refused'] and out['fatal'])
            self.assertIn('would cut the prompt', out['error'])
            out = server.apps().call(req('ollama'))
            self.assertIn('needs a model', out['error'])
        self.assertEqual(server.bodies, [])
        port = server.port
        out = A.Applicators(environ={'SYMBLIC_OLLAMA_HOSTS': f'127.0.0.1:{port}'}).call(req('ollama:tiny'))
        self.assertEqual((out['ok'], out['refused']), (False, True))       # the server is gone: not reachable

    def test_server_errors_and_keep_alive(self):
        with FakeOllama(status=500) as server:
            out = server.apps(SYMBLIC_OLLAMA_KEEP_ALIVE='0').call(req('ollama:tiny@local'))
        self.assertFalse(out['ok'])
        self.assertFalse(out.get('fatal'))
        self.assertIn('HTTP 500', out['error'])
        self.assertEqual(server.bodies[0]['keep_alive'], 0)

    def test_stop_closes_the_connection(self):
        with FakeOllama(delay=5) as server:
            request = req('ollama:tiny@local')
            threading.Timer(0.5, request['stop'].set).start()
            started = time.monotonic()
            out = server.apps().call(request)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual((out['ok'], out['fatal']), (False, True))
        self.assertIn('stopped', out['error'])

    def test_a_program_runs_end_to_end_against_the_fake_server(self):
        with FakeOllama() as server:
            run = SR.Run('ask n: Int "How many legs has a spider?" by "ollama:tiny@local" with effort=low\nshow n.\n',
                         None, server.apps())
            report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['outputs'][0]['value'], 8)


if __name__ == '__main__':
    unittest.main()

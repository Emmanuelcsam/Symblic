"""integration/host/symblic_engine.py (the host's /api/automation/symblic/ routes): runs, preview, compare,
programs, evidence and the HTTP dispatch — with a temporary data dir, a fake launcher (the runner executes
in-process with fake applicators), the fake store in fake_host_apps.py and no systemd, model, host or network.
These run without the host."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from integration.host import symblic_engine as E
from symblic.kernel import run as SR
from tests.integration import fake_host_apps


class FakeApps:
    def __init__(self, answer=None):
        self.answer = answer or (lambda app, prompt: {'answer': 8})
        self.calls = []

    def call(self, req):
        self.calls.append(req)
        return {'ok': True, 'json': self.answer(req['app']['spec'], req['prompt']), 'ms': 1}


class Handler:
    """The bits of DashboardHandler symblic_engine uses."""

    def __init__(self, query=None):
        self.query = query or {}
        self.sent = None
        self.status = None
        self.ctype = None

    def get_query_param(self, name):
        return self.query.get(name)

    def send_json(self, data, status=200, extra_headers=None):
        self.sent, self.status = data, status

    def send_bytes(self, data, content_type='application/octet-stream', status=200):
        self.sent, self.status, self.ctype = data, status, content_type


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.tmp})
        self.env.start()
        fake_host_apps.install(self)                     # the host's store, faked when the host is absent
        self.apps = FakeApps()
        self.active = set()
        self.launches = []

        def launch(run_id, folder, resume):
            self.launches.append((run_id, resume))
            SR.run_folder(folder, resume, applicators=self.apps)
            return {'ok': True}
        self.launcher = mock.patch.dict(E.launcher, {'launch': launch, 'active': lambda rid: rid in self.active,
                                                     'stop': lambda rid: True})
        self.launcher.start()

    def tearDown(self):
        self.launcher.stop()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, route, data=None, query=None):
        h = Handler(query)
        handled = E.handle(h, method, route, data or {})
        self.assertTrue(handled, route)
        return h


SRC = ('program Test run.\nlet a = 4 + 4.\nask legs: Int in 0..20 "How many legs does a spider have?" with effort=low\n'
       'ensure legs = a else retry.\ndraw flower(petals=5) as "f.svg".\nshow [a, legs].\n')


class Runs(Base):
    def test_run_records_everything_and_lists(self):
        h = self.call('POST', 'run', {'source': SRC, 'by': 'claude:haiku'})
        self.assertEqual(h.status, 200, h.sent)
        rid = h.sent['id']
        view = self.call('GET', 'run', query={'id': rid}).sent
        self.assertEqual(view['status'], 'done')
        self.assertEqual(view['state']['outputs'][-1]['value'], [8, 8])
        self.assertNotIn('svg', view['state']['outputs'][0])          # drawings come from symblic/artifact
        self.assertEqual(view['artifacts'], ['f.svg'])
        self.assertEqual(view['meta']['by'], 'claude:haiku')
        self.assertIn('legs', [t.get('name') for t in view['trace']])
        art = self.call('GET', 'artifact', query={'id': rid, 'name': 'f.svg'})
        self.assertEqual(art.ctype, 'image/svg+xml')
        self.assertTrue(art.sent.startswith(b'<svg'))
        runs = self.call('GET', 'runs').sent['runs']
        self.assertEqual(runs[0]['id'], rid)
        self.assertEqual(runs[0]['status'], 'done')
        self.assertTrue(runs[0]['fingerprint'])
        folder = os.path.join(self.tmp, 'symblic', 'runs', rid)
        self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
        for name in ('meta.json', 'program.sym', 'state.json', 'calls.jsonl', 'trace.jsonl'):
            self.assertEqual(os.stat(os.path.join(folder, name)).st_mode & 0o777, 0o600, name)
        self.assertEqual(os.stat(os.path.join(folder, 'artifacts')).st_mode & 0o777, 0o700)

    def test_invalid_programs_and_applicators_are_refused_before_launch(self):
        h = self.call('POST', 'run', {'source': 'let x = (1 +.\n'})
        self.assertEqual(h.status, 400)
        self.assertIn('line 1', h.sent['error'])
        h = self.call('POST', 'run', {'source': SRC, 'by': 'skynet:9000'})
        self.assertEqual(h.status, 400)
        self.assertEqual(self.launches, [])

    def test_artifact_and_ids_cannot_escape(self):
        rid = self.call('POST', 'run', {'source': SRC, 'by': 'claude:haiku'}).sent['id']
        for name in ('../meta.json', '/etc/passwd', 'x.json', '..svg'):
            h = self.call('GET', 'artifact', query={'id': rid, 'name': name})
            self.assertEqual(h.status, 400, name)
        for bad in ('../../x', 'zz', '', None):
            self.assertEqual(self.call('GET', 'run', query={'id': bad}).status, 400)

    def test_lost_and_resume_and_delete(self):
        rid = self.call('POST', 'run', {'source': SRC, 'by': 'claude:haiku'}).sent['id']
        folder = os.path.join(self.tmp, 'symblic', 'runs', rid)
        with open(os.path.join(folder, 'state.json'), 'w') as f:
            json.dump({'status': 'running', 'updated': 1}, f)
        self.assertEqual(self.call('GET', 'runs').sent['runs'][0]['status'], 'lost')
        calls_before = len(self.apps.calls)
        self.assertEqual(self.call('POST', 'resume', {'id': rid}).status, 200)
        self.assertEqual(len(self.apps.calls), calls_before)          # every answer replayed from calls.jsonl
        self.assertEqual(self.launches[-1], (rid, True))
        self.active.add(rid)
        self.assertEqual(self.call('POST', 'delete', {'id': rid}).status, 400)   # still active
        self.active.discard(rid)
        self.assertEqual(self.call('POST', 'delete', {'id': rid}).status, 200)
        self.assertFalse(os.path.exists(folder))

    def test_failed_launch_is_visible(self):
        with mock.patch.dict(E.launcher, {'launch': lambda *a: {'ok': False, 'error': 'systemd-run refused'}}):
            h = self.call('POST', 'run', {'source': SRC})
        self.assertEqual(h.status, 400)
        rid = self.call('GET', 'runs').sent['runs'][0]['id']
        self.assertEqual(self.call('GET', 'run', query={'id': rid}).sent['state']['error']['message'],
                         'systemd-run refused')


class Preview(Base):
    def test_preview_stops_at_the_first_ask_and_shows_its_capsule(self):
        h = self.call('POST', 'preview', {'source': 'let a = 2.\nask b: one of {x, y} "Pick for {a}." with effort=low\n',
                                          'by': 'ollama:qwen3:4b-instruct'})
        p = h.sent
        self.assertEqual(p['status'], 'paused')
        self.assertEqual(p['bindings'][0]['name'], 'a')
        self.assertEqual(p['next']['name'], 'b')
        self.assertIn('Pick for 2.', p['next']['prompt'])
        self.assertEqual(p['next']['schema']['properties']['answer']['enum'], ['x', 'y'])
        self.assertEqual(self.apps.calls, [])                          # nothing reached a model

    def test_preview_of_a_kernel_program_runs_it_and_returns_the_drawing(self):
        p = self.call('POST', 'preview', {'source': 'draw flower(petals=6).\n'}).sent
        self.assertEqual(p['status'], 'done')
        self.assertTrue(p['drawing'].startswith('<svg'))


class Compare(Base):
    def test_compare_lines_statements_up_by_fingerprint(self):
        def answer(app, prompt):
            return {'answer': 9 if app == 'ollama:llama3.2:1b' else 8}
        self.apps.answer = answer
        src = 'ask legs: Int "Spider legs?" with effort=low\nshow legs.\n'
        h = self.call('POST', 'compare', {'source': src, 'applicators': ['claude:haiku', 'codex', 'ollama:llama3.2:1b']})
        self.assertEqual(h.status, 200, h.sent)
        view = self.call('GET', 'compare', query={'id': h.sent['id']}).sent
        self.assertEqual([c['by'] for c in view['columns']], ['claude:haiku', 'codex', 'ollama:llama3.2:1b'])
        s = view['summary']
        self.assertEqual(s['total'], 2)
        self.assertEqual(s['unanimous'], 0)
        self.assertAlmostEqual(s['pairwise'], 1 / 3, places=3)
        self.assertFalse(s['identical_runs'])
        self.assertEqual((s['same_runs'], s['runs'], s['finished']), (2, 3, 3))
        legs = next(x for x in s['statements'] if x['key'].endswith(':legs'))
        self.assertEqual((legs['modal'], legs['distinct']), (2, 2))
        self.assertEqual(len(self.call('GET', 'compares').sent['compares']), 1)

    def test_compare_needs_two_distinct_valid_applicators(self):
        self.assertEqual(self.call('POST', 'compare', {'source': SRC, 'applicators': ['codex']}).status, 400)
        self.assertEqual(self.call('POST', 'compare', {'source': SRC, 'applicators': ['codex', 'codex']}).status, 400)
        self.assertEqual(self.call('POST', 'compare', {'source': SRC, 'applicators': ['codex', 'nope:x']}).status, 400)


class Programs(Base):
    def test_save_list_overwrite_delete(self):
        self.assertEqual(self.call('POST', 'programs/save', {'name': 'Flower one', 'source': 'let a = 1.\n'}).status, 200)
        self.call('POST', 'programs/save', {'name': 'Flower one', 'source': 'let a = 2.\n'})
        progs = self.call('GET', 'programs').sent['programs']
        self.assertEqual(len(progs), 1)
        self.assertEqual(progs[0]['source'], 'let a = 2.\n')
        self.assertEqual(self.call('POST', 'programs/save', {'name': '../evil', 'source': 'x'}).status, 400)
        self.assertEqual(self.call('POST', 'programs/delete', {'name': 'Flower one'}).status, 200)
        self.assertEqual(self.call('POST', 'programs/delete', {'name': 'Flower one'}).status, 400)


class MetaAndEvidence(Base):
    def test_meta_lists_examples_that_all_check(self):
        from symblic.kernel import language as S
        with mock.patch('symblic.providers.applicators.engines_status', return_value={}):
            m = self.call('GET', 'meta').sent
        self.assertGreaterEqual(len(m['examples']), 9)
        for ex in m['examples']:
            self.assertTrue(S.check(ex['source'])['ok'], ex['id'])
        self.assertIn('high', m['efforts'])

    def test_evidence_reads_the_kernel_record_and_bench_reports(self):
        d = os.path.join(self.tmp, 'symblic', 'bench', 'b1')
        os.makedirs(d)
        with open(os.path.join(d, 'results.jsonl'), 'w') as f:
            for by, h in (('a', 'x1'), ('b', 'x1')):
                f.write(json.dumps({'cell': f'identity|q|symblic|{by}', 'suite': 'identity', 'item': 'q',
                                    'condition': 'symblic', 'by': by, 'ok': True, 'hash': h, 'correct': True}) + '\n')
        ev = self.call('GET', 'evidence').sent
        self.assertTrue(ev['kernel'])
        self.assertEqual(len({r['fingerprint'] for r in ev['kernel'] if r['program'] == '02-flower-formal.sym'}), 1)
        self.assertEqual(ev['benches'][0]['name'], 'b1')
        self.assertIn('unanimous on 1/1', ev['benches'][0]['report'])

    def test_check_route(self):
        c = self.call('POST', 'check', {'source': 'let x = 1.\nlet x = 2.\n'}).sent
        self.assertFalse(c['ok'])
        self.assertEqual(self.call('POST', 'check', {'source': ''}).status, 400)
        self.assertFalse(E.handle(Handler(), 'GET', 'nope', {}))


SHEET = """# twice.js

## Shared

Plain functions.

## Unit `twice(x)`

Return x times 2.

Examples:

    twice(2) ==> 4

## Assemble `twice.html`

    <script>
    /*UNITS*/
    </script>
"""


class SpecSheets(Base):
    """Build: a spec sheet compiles server-side (no model) and its units are written by the chosen applicators."""

    def test_check_reports_units_and_problems(self):
        h = self.call('POST', 'spec/check', {'sheet': SHEET})
        self.assertEqual((h.sent['ok'], h.sent['file'], h.sent['units']), (True, 'twice.html',
                         [{'heading': 'twice(x)', 'examples': 1, 'uses': []}]))
        bad = self.call('POST', 'spec/check', {'sheet': SHEET.replace('    twice(2) ==> 4', '')}).sent
        self.assertFalse(bad['ok'])
        self.assertIn('unit twice(x) has no examples: nothing could check it', bad['problems'])
        self.assertEqual(self.call('POST', 'spec/check', {'sheet': ''}).status, 400)
        self.assertEqual(self.call('POST', 'spec/check', {'sheet': 'x' * (E.SPEC_MAX + 1)}).status, 400)

    def test_the_tetris_example_ships_and_compiles(self):
        sheet = self.call('GET', 'spec/example', query={'name': 'tetris'}).sent['sheet']
        info = self.call('POST', 'spec/check', {'sheet': sheet}).sent
        self.assertTrue(info['ok'], info['problems'])
        self.assertEqual(len(info['units']), 25)
        for name in ('../etc', 'nope'):
            self.assertEqual(self.call('GET', 'spec/example', query={'name': name}).status, 400)

    def test_run_compiles_and_starts_a_build_with_the_chosen_models(self):
        with mock.patch.object(E, 'start_run', lambda body: {'id': 'r1', 'body': body}):
            h = self.call('POST', 'spec/run', {'sheet': SHEET, 'by': ['ollama:qwen3:4b-instruct'], 'samples': 2,
                                               'retries': 1, 'rounds': 1})
        self.assertEqual(h.status, 200, h.sent)
        body = h.sent['body']
        self.assertIn('ask unit_twice: Code js', body['source'])
        self.assertIn('use by=["ollama:qwen3:4b-instruct"], route=search, samples=2, retries=1, rounds=1', body['source'])
        # a local model gets output caps (a looping 1B model otherwise runs to the worker nodes' 16k-token default);
        # a cloud-only build gets none; an explicit ollama_limits passes through to start_run's validation
        self.assertEqual(body['options'], {'parallel': 2, 'max_asks': 11, 'max_calls': 4,
                                           'ollama_limits': {'num_predict': 4096, 'timeout_seconds': 900}})
        with mock.patch.object(E, 'start_run', lambda body: {'id': 'r2', 'body': body}):
            cloud = self.call('POST', 'spec/run', {'sheet': SHEET, 'by': ['claude:haiku'], 'samples': 1, 'retries': 1, 'rounds': 1}).sent['body']
            own = self.call('POST', 'spec/run', {'sheet': SHEET, 'by': ['ollama:qwen3:4b-instruct'], 'samples': 1, 'retries': 1,
                                                 'rounds': 1, 'ollama_limits': {'num_predict': 2048}}).sent['body']
        self.assertNotIn('ollama_limits', cloud['options'])
        self.assertEqual(own['options']['ollama_limits'], {'num_predict': 2048})
        for bad in ({'samples': 0}, {'rounds': 99}, {'by': []}):
            self.assertEqual(self.call('POST', 'spec/run', {'sheet': SHEET, **bad}).status, 400, bad)
        self.assertEqual(self.call('POST', 'spec/run', {'sheet': SHEET.replace('/*UNITS*/', '')}).status, 400)

    def test_a_rebuild_keeps_the_units_an_earlier_build_accepted(self):
        import json

        from symblic.kernel import language as S
        from symblic.spec import sheets as SP
        code = 'function twice(x) { return x * 2; }'
        folder = os.path.join(E.runs_dir(), 'abcdef012345')
        os.makedirs(folder)
        program = SP.compile_sheet(SHEET, ['ollama:qwen3:4b-instruct'], samples=1, retries=1, rounds=1)
        rows = {'program.sym': program,
                'calls.jsonl': json.dumps({'key': 'k', 'at': 1.0, 'stmt': 'unit_twice', 'app': 'ollama:qwen3:4b-instruct',
                                           'reply': {'ok': True, 'text': '```js\n' + code + '\n```'}}),
                'trace.jsonl': json.dumps({'kind': 'ask', 'status': 'ok', 'name': 'unit_twice',
                                           'hash': S.fingerprint(code), 'value': code})}
        for name, text in rows.items():
            with open(os.path.join(folder, name), 'w', encoding='utf-8') as f:
                f.write(text)
        self.assertTrue(next(r for r in E.list_runs() if r['id'] == 'abcdef012345')['spec'])
        with mock.patch.object(E, 'start_run', lambda body: {'id': 'r2', 'body': body}):
            h = self.call('POST', 'spec/run', {'sheet': SHEET, 'by': ['ollama:qwen3:4b-instruct'], 'samples': 1,
                                               'retries': 1, 'rounds': 1, 'keep': 'abcdef012345'})
            missing = self.call('POST', 'spec/run', {'sheet': SHEET, 'keep': '000000000000'})
            escape = self.call('POST', 'spec/run', {'sheet': SHEET, 'keep': '../runs'})
        self.assertEqual(h.status, 200, h.sent)
        self.assertEqual(h.sent['kept'], 1)
        source = h.sent['body']['source']
        self.assertNotIn('ask unit_twice', source)
        self.assertIn(f'let unit_twice = {SP.literal(code)}.', source)
        self.assertIn('kept from an earlier build (run abcdef012345)', source)
        self.assertIn('keeping 1 units', h.sent['body']['title'])
        self.assertEqual((missing.status, escape.status), (400, 400))


class Tighten(Base):
    """POST tighten starts a job (fake launcher runs it in-process with fake agents); GET tighten shows it."""

    def setUp(self):
        super().setUp()
        from symblic.authoring import tighten as T

        def answer(app, prompt):
            if 'Rewrite the statement' in prompt:
                return {'answer': {'instruction': 'How many legs does an adult spider have, counting only legs?',
                                   'assumptions': ['an adult spider', 'legs only']}}
            extra = {'readings': []}
            if app == 'claude:haiku' and 'counting only legs' not in prompt:
                extra = {'readings': ['legs only: 8', 'legs and pedipalps: 10']}
            return {'answer': 8, **extra}
        self.apps = FakeApps(answer)
        self.jobs = []

        def launch_tighten(job_id, folder):
            self.jobs.append(job_id)
            T.run_job(folder, applicators=self.apps)
            return {'ok': True}
        E.launcher['tighten'] = launch_tighten
        E.launcher['active'] = lambda rid, unit='': False

    def test_a_job_runs_and_its_result_is_shown(self):
        src = 'ask legs: Int in 0..20 "How many legs does a spider have?" with effort=low\nshow legs.\n'
        h = self.call('POST', 'tighten', {'source': src, 'panel': ['claude:haiku', 'codex'], 'clarifier': 'claude:sonnet'})
        self.assertEqual(h.status, 200, h.sent)
        job = h.sent['id']
        v = self.call('GET', 'tighten', query={'id': job}).sent
        self.assertEqual(v['status'], 'done')
        self.assertTrue(v['result']['changed'])
        self.assertIn('counting only legs', v['result']['candidate_program'])
        self.assertEqual(v['result']['program'], src)
        self.assertEqual(v['result']['adoption']['status'], 'not_requested')
        self.assertEqual([x['asks'][0]['diagnosis'] for x in v['result']['history']], ['ambiguous', 'converged'])
        self.assertEqual(oct(os.stat(os.path.join(E.tighten_dir(), job, 'result.json')).st_mode & 0o777), '0o600')
        self.assertEqual([t['id'] for t in self.call('GET', 'tightens').sent['tightens']], [job])

    def test_refusals(self):
        for body, word in (({'source': 'let a = 1.\n'}, 'no ask'),
                           ({'source': 'ask a: Int "n?"\n', 'panel': ['codex']}, 'at least two'),
                           ({'source': 'ask a: Int "n?"\n', 'panel': ['nonsense engine!']}, '')):
            h = self.call('POST', 'tighten', body)
            self.assertEqual(h.status, 400, body)
            self.assertIn(word, h.sent['error'])
        self.assertEqual(self.call('GET', 'tighten', query={'id': '../etc'}).status, 400)


if __name__ == '__main__':
    unittest.main()

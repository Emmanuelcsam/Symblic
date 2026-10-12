"""integration/host/symblic_lang_api.py (library, tests, papers, locks under the host's /api/automation/symblic/)
with a temporary data dir, a fake launcher (runs execute in-process with fake applicators), the fake store in
fake_host_apps.py and no systemd, model, host or network. These run without the host."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from integration.host import symblic_engine as E
from symblic.lang import abstraction as L
from integration.host import symblic_lang_api as A
from symblic.kernel import run as SR
from tests.integration import fake_host_apps

PAPER = '''---
effort: low
---
# Spider study

Spiders are arachnids.

## Definitions

- **arachnid**: an eight-legged arthropod

## Counting

```symblic
ask legs: Int in 0..20 "How many legs does an arachnid have?"
ensure legs = 8 else retry.
show legs.
```
'''


class FakeApps:
    def __init__(self, answer=None):
        self.answer = answer or (lambda prompt: {'answer': 8})
        self.calls = []

    def call(self, req):
        self.calls.append(req)
        return {'ok': True, 'json': self.answer(req['prompt']), 'ms': 1}


class Handler:
    def __init__(self, query=None):
        self.query = query or {}
        self.sent = self.status = None

    def get_query_param(self, name):
        return self.query.get(name)

    def send_json(self, data, status=200, extra_headers=None):
        self.sent, self.status = data, status


class Base(unittest.TestCase):
    def setUp(self):
        L.register()
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.tmp})
        fake_host_apps.install(self)                     # the host's store, faked when the host is absent
        self.env.start()
        self.apps = FakeApps()

        def launch(run_id, folder, resume):
            SR.run_folder(folder, resume, applicators=self.apps)
            return {'ok': True}
        self.launcher = mock.patch.dict(E.launcher, {'launch': launch, 'active': lambda rid: False,
                                                     'stop': lambda rid: True})
        self.launcher.start()

    def tearDown(self):
        self.launcher.stop()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, route, data=None, query=None):
        h = Handler(query)
        self.assertTrue(A.handle(h, method, route, data or {}), route)
        return h


class Library(Base):
    def test_library_module_and_tests(self):
        mods = {m['name'] for m in self.call('GET', 'library').sent['modules']}
        self.assertTrue({'units', 'stats', 'text'} <= mods)
        units = self.call('GET', 'module', query={'name': 'units'}).sent
        self.assertIn('convert_length', units['source'])
        for bad in ('../x', 'Units', '', None, 'nosuch'):
            self.assertEqual(self.call('GET', 'module', query={'name': bad}).status, 400, bad)
        res = self.call('POST', 'tests', {'source': units['source']}).sent
        self.assertTrue(res['ok'], res)
        res = self.call('POST', 'tests', {'source': 'test "no" do\n  assert 1 = 2.\nend.\n'}).sent
        self.assertEqual((res['passed'], res['failed']), (0, 1))
        text = self.call('POST', 'tests', {'source': L.library_source('text')}).sent
        self.assertEqual(text['passed'], 1)                     # the kernel-only quoted_number test (2.3);
        self.assertGreater(text['failed'], 0)                   # the certification tests need agents
        self.assertEqual(self.apps.calls, [])                   # and the page's request never reaches one


class Papers(Base):
    def test_check_compile_run_and_map(self):
        c = self.call('POST', 'paper/check', {'source': PAPER}).sent
        self.assertTrue(c['ok'], c['errors'])
        self.assertEqual(c['name'], 'Spider study')
        self.assertEqual(c['asks'], 1)
        ask_row = next(r for r in c['plan'] if r['kind'] == 'ask')
        self.assertEqual(ask_row['line'], PAPER.split('\n').index(next(
            ln for ln in PAPER.split('\n') if ln.startswith('ask legs'))) + 1)
        compiled = self.call('POST', 'paper/compile', {'source': PAPER}).sent
        self.assertIn('term "arachnid"', compiled['source'])
        rid = self.call('POST', 'paper/run', {'source': PAPER, 'by': 'claude:haiku'}).sent['id']
        view = E.run_view(rid)
        self.assertEqual(view['status'], 'done')
        self.assertIs(view['has_paper_map'], True)
        self.assertIn('an eight-legged arthropod', self.apps.calls[0]['prompt'])
        self.assertIn('Spiders are arachnids', self.apps.calls[0]['prompt'])
        pmap = self.call('GET', 'paper/map', query={'run': rid}).sent
        self.assertEqual(pmap['title'], 'Spider study')
        folder = E.run_dir(rid)
        self.assertEqual(os.stat(os.path.join(folder, 'paper.json')).st_mode & 0o777, 0o600)
        self.assertEqual(self.call('POST', 'paper/run', {'source': '# T\n```symblic\nlet x = .\n```\n'}).status, 400)
        plain = E.start_run({'source': 'let x = 1.\n'})['id']
        self.assertIs(E.run_view(plain)['has_paper_map'], False)
        self.assertEqual(self.call('GET', 'paper/map', query={'run': plain}).status, 400)

    def test_map_presence_tracks_later_receipt_and_keeps_invalid_map_refusal(self):
        rid = E.start_run({'source': 'let x = 1.\n'})['id']
        self.assertIs(E.run_view(rid)['has_paper_map'], False)
        path = os.path.join(E.run_dir(rid), 'paper.json')
        record = {'title': 'Later receipt', 'map': [{'line': 1, 'paper_line': 17, 'section': 0, 'kind': 'let'}]}
        A._save(path, record)
        self.assertIs(E.run_view(rid)['has_paper_map'], True)
        self.assertEqual(self.call('GET', 'paper/map', query={'run': rid}).sent, record)
        with open(path, 'w', encoding='utf-8') as stream:
            stream.write('{broken')
        self.assertIs(E.run_view(rid)['has_paper_map'], True)
        self.assertEqual(self.call('GET', 'paper/map', query={'run': rid}).status, 400)
        os.unlink(path)
        self.assertIs(E.run_view(rid)['has_paper_map'], False)

    def test_reproduce_and_the_paper_view(self):
        res = self.call('POST', 'paper/reproduce', {'source': PAPER, 'applicators': ['claude:haiku', 'codex']}).sent
        self.assertEqual(len(res['runs']), 2)
        pv = self.call('GET', 'paper/view', query={'id': res['id']}).sent
        self.assertTrue(pv['reproduces'], pv)
        self.assertEqual((pv['model_statements'], pv['model_reproduced']), (1, 1))
        self.assertIn('REPRODUCES', pv['text'])
        self.apps.answer = lambda prompt: {'answer': 8}
        plain = E.start_compare({'source': 'ask n: Int "One." with effort=low\n',
                                 'applicators': ['claude:haiku', 'codex']})
        self.assertEqual(self.call('GET', 'paper/view', query={'id': plain['id']}).status, 400)
        self.assertEqual(self.call('GET', 'paper/view', query={'id': '../../x'}).status, 400)


class Locks(Base):
    def test_lock_get_and_replay(self):
        rid = E.start_run({'source': 'ask n: Int in 0..20 "Legs of a spider?" with effort=low\nshow n.\n',
                           'by': 'claude:haiku'})['id']
        self.assertEqual(self.call('GET', 'lock', query={'id': rid}).status, 400)          # not locked yet
        r = self.call('POST', 'lock', {'id': rid}).sent
        self.assertTrue(r['ok'])
        path = os.path.join(E.run_dir(rid), 'run.lock.json')
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        lock = self.call('GET', 'lock', query={'id': rid}).sent
        self.assertEqual(lock['fingerprint'], r['fingerprint'])
        calls = len(self.apps.calls)
        rep = self.call('POST', 'lock/replay', {'id': rid}).sent
        self.assertTrue(rep['ok'], rep)
        self.assertEqual((rep['calls'], len(self.apps.calls)), (0, calls))
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
        data['source'] = 'show 2.\n'
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
        self.assertEqual(self.call('POST', 'lock/replay', {'id': rid}).status, 400)      # an edited lock
        self.assertEqual(self.call('POST', 'lock', {'id': 'zz'}).status, 400)

    def test_an_unfinished_run_cannot_be_locked(self):
        rid = E.start_run({'source': 'ask n: Int "N." with effort=low\nassert n = 3.\n', 'by': 'claude:haiku'})['id']
        h = self.call('POST', 'lock', {'id': rid})
        self.assertEqual(h.status, 400)
        self.assertIn('finished', h.sent['error'])


class Jobs(Base):
    ROUTINE = ('routine colour_of(thing: Text) -> one of {red, green, yellow} with effort=high do\n'
               '  ask c: one of {red, green, yellow} "What colour is {thing}?"\n  return c.\nend.\n'
               'test "banana" do\n  assert colour_of("banana") = "yellow".\nend.\n')

    def setUp(self):
        super().setUp()
        import re as _re

        def answer(prompt):
            m = _re.search(r'What colour is (\w+)', prompt)
            return {'answer': {'banana': 'yellow', 'grass': 'green'}.get(m.group(1) if m else '', 'red')}
        self.apps = FakeApps(answer)

        def launch(job_id, folder):
            L.run_job(folder, applicators_for=lambda by: self.apps)
            return {'ok': True}
        self.jobs = mock.patch.dict(A.jobs, {'launch': launch, 'active': lambda jid: False, 'stop': lambda jid: True})
        self.jobs.start()

    def tearDown(self):
        self.jobs.stop()
        super().tearDown()

    def test_certify_a_program_and_a_library_module(self):
        body = {'source': self.ROUTINE, 'cohorts': ['claude:haiku', 'codex']}
        jid = self.call('POST', 'lang/certify', body).sent['id']
        view = self.call('GET', 'lang/job', query={'id': jid}).sent
        self.assertEqual(view['status'], 'done', view)
        res = view['result']['result']
        self.assertEqual(res['certified'], ['banana'])
        self.assertEqual([c['by'] for c in res['cohorts']], ['claude:haiku', 'codex'])
        self.assertNotIn('source', view['job'])
        rows = self.call('GET', 'lang/jobs').sent['jobs']
        self.assertEqual(rows[0]['summary'], '1/1 tests pass for every agent')
        folder = os.path.join(A.jobs_dir(), jid)
        for name in ('job.json', 'result.json'):
            self.assertEqual(os.stat(os.path.join(folder, name)).st_mode & 0o777, 0o600, name)
        self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
        jid2 = self.call('POST', 'lang/certify', {'module': 'units', 'cohorts': ['codex']}).sent['id']
        self.assertEqual(self.call('GET', 'lang/job', query={'id': jid2}).sent['status'], 'done')

    def test_crystallise_and_save_the_crystal(self):
        jid = self.call('POST', 'lang/crystallise', {'source': self.ROUTINE, 'routine': 'colour_of',
                                                     'domain': ['banana', 'grass'], 'by': 'claude:haiku'}).sent['id']
        view = self.call('GET', 'lang/job', query={'id': jid}).sent
        self.assertEqual(view['status'], 'done', view)
        self.assertEqual(len(view['result']['result']['kept']), 2)
        self.assertEqual(self.call('POST', 'lang/save', {'id': jid, 'name': 'Colour crystal'}).status, 200)
        saved = {p['name']: p['source'] for p in E.load_programs()}
        self.assertIn('colour_of_table', saved['Colour crystal'])
        r, rep, _ = (lambda run: (run, run.execute(), None))(
            SR.Run('import "Colour crystal".\nlet c = colour_of("grass").\n', {}, None, {'by': 'fake:x'}))
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(r.kernel.env.lookup('c').value, 'green')

    def test_requests_are_validated_before_anything_starts(self):
        bad = [('lang/certify', {'source': 'let x = 1.\n', 'cohorts': ['codex']}),            # no tests
               ('lang/certify', {'module': '../x', 'cohorts': ['codex']}),
               ('lang/certify', {'source': self.ROUTINE, 'cohorts': ['skynet:9']}),
               ('lang/certify', {'source': self.ROUTINE, 'cohorts': []}),
               ('lang/crystallise', {'source': self.ROUTINE, 'routine': 'nope', 'domain': [1], 'by': 'codex'}),
               ('lang/crystallise', {'source': self.ROUTINE, 'routine': 'colour_of', 'domain': [], 'by': 'codex'}),
               ('lang/crystallise', {'source': self.ROUTINE, 'routine': 'colour_of', 'domain': ['x'],
                                     'min_agreement': 0.1})]
        for route, body in bad:
            self.assertEqual(self.call('POST', route, body).status, 400, (route, body))
        self.assertEqual(os.listdir(A.jobs_dir()), [])
        self.assertEqual(self.call('GET', 'lang/job', query={'id': '../../x'}).status, 400)
        self.assertEqual(self.call('POST', 'lang/save', {'id': 'zz', 'name': 'x'}).status, 400)


class Evidence(Base):
    def test_experiments_are_summarised_and_outages_are_not_wrong_answers(self):
        bench = os.path.join(E.bench_dir(), 'lang-test')
        os.makedirs(os.path.join(bench, 'paper-a'), exist_ok=True)
        paper_a = {'title': 'Paper A', 'reproduces': False, 'results_reproduce': True,
                   'coverage': {'finished': 2, 'of': 3}, 'model_statements': 1, 'model_reproduced': 1,
                   'cohorts': [{'by': 'claude:haiku', 'status': 'done', 'fingerprint': 'aa'},
                               {'by': 'codex', 'status': 'done', 'fingerprint': 'aa'},
                               {'by': 'agy', 'status': 'failed', 'error': 'quota: paused (outage)'}],
                   'correctness': {'claude:haiku': {'correct': {'ok': True}}, 'codex': {'correct': {'ok': False}},
                                   'agy': {'correct': {'ok': False}}},
                   'underspecified': [{'paper_line': 9, 'section_title': 'Steps', 'name': 'x', 'distinct': 2}]}
        with open(os.path.join(bench, 'paper-a', 'reproduce.json'), 'w', encoding='utf-8') as stream:
            json.dump(paper_a, stream)
        with open(os.path.join(bench, 'certify.json'), 'w', encoding='utf-8') as stream:
            json.dump({'tests': [{'title': 't1', 'passed': 2, 'of': 2, 'cohorts': {}}], 'certified_for_all': ['t1']},
                      stream)
        ev = self.call('GET', 'lang/evidence').sent['experiments']
        kinds = sorted(e['kind'] for e in ev)
        self.assertEqual(kinds, ['certify', 'reproduce'])
        paper = next(e for e in ev if e['kind'] == 'reproduce')
        self.assertEqual((paper['finished'], paper['of'], paper['results_reproduce']), (2, 3, True))
        self.assertEqual([c['correct'] for c in paper['cohorts']], [True, False, None])   # outage: no result
        self.assertEqual(paper['underspecified'][0]['paper_line'], 9)


class Routing(Base):
    def test_the_engine_hands_these_routes_over(self):
        h = Handler()
        if not E.handle(h, 'GET', 'library', {}):
            self.skipTest('the engine routing hook is not applied yet')
        self.assertIn('modules', h.sent)
        h = Handler()
        self.assertFalse(E.handle(h, 'GET', 'paper/nothing', {}))


if __name__ == '__main__':
    unittest.main()

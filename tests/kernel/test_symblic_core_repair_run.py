"""Core repair of the interpreter (symblic/kernel/run.py and symblic/kernel/language.py).

language-1: a run folder's work belongs to the semantic kernel that did it. Call keys hash the exact prompt and
effect ids hash the arguments, and both change with the kernel. Resuming or re-executing a folder whose answered
calls or effects were recorded under another kernel identity, or under one that cannot be told, is therefore refused
before any model call, effect or write.

Lineage (epistemic-1, -2, -3, -5, language-2): what a value was computed from stays its lineage through loops,
contracts that call user functions, more than 64 parents or roots, and `ask ... for each` workers; and keeping it
costs work linear in the program's own work.

Review of lane A: what decided a routine's loop that can return stays in the routine's result; callables introduced
between an ask and its check (a routine's options, an imported module) are read; kernel.json follows the effect
ledger's durability switch; and a tripwire (PromptIdentity) ties the call keys of typical programs to kernel_id().
Fake applicators, a fake effect host and temporary folders only: nothing reaches a model, a capability, the network
or a live store."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import signal
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import effects as FX  # noqa: E402
from symblic.kernel import epistemic as EP  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

ACT = 'ask t: Text "Write a one-word title." with effort=low, by="fake:a"\nact n = msg.post(text=t).\n'
ASKS = ('ask a: Text "First title?" with effort=low, by="fake:a"\n'
        'ask b: Text "Second title for {a}?" with effort=low, by="fake:a"\nshow [a, b].\n')
POST_ONLY = 'act n = msg.post(text="Hello").\n'
CAT = [{'name': 'msg.post', 'effect': 'write-external', 'policy': 'auto',
        'params': {'type': 'object', 'additionalProperties': False,
                   'properties': {'text': {'type': 'string'}}, 'required': ['text']}}]
OLD_ID = '0b2cca3828a1965a'           # the 2.4 kernel id the review's folders were recorded under
RECORD = 'kernel.json'


class Apps:
    """Answers every call with one value and keeps every request."""

    def __init__(self, answer):
        self.answer, self.requests, self.lock = answer, [], threading.Lock()

    def call(self, req):
        with self.lock:
            self.requests.append(req)
        return {'ok': True, 'json': {'answer': self.answer}, 'model': 'a', 'node': 'fake'}


class Host:
    """A write-external capability that is performed without asking (a host that approves everything itself)."""

    def __init__(self):
        self.performed, self.on_wait = [], None

    def catalogue(self):
        return CAT

    def perform(self, effect, stop):
        self.performed.append(dict(effect['args']))
        return {'status': 'done', 'result': True, 'receipt': {'n': len(self.performed)}}


def old_kernel():
    """Execute as another deployment did: another kernel identity and, as 2.4 -> 2.5 did, another system prompt,
    so that every call key differs from today's."""
    other = {**S.kernel_id(), 'lang': '2.4', 'id': OLD_ID}
    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.object(S, 'kernel_id', return_value=other))
    stack.enter_context(mock.patch.object(S, 'SYSTEM', S.SYSTEM + ' (2.4)'))
    return stack


def snapshot(folder, skip=()):
    """Every entry of the folder: bytes, mode and modification time of files (a rewrite is a change too)."""
    out = {}
    for root, dirs, files in os.walk(folder):
        for name in sorted(dirs + files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder)
            if rel in skip:
                continue
            st = os.lstat(path)
            if os.path.isfile(path):
                with open(path, 'rb') as stream:
                    out[rel] = (stream.read(), st.st_mode, st.st_mtime_ns)
            else:
                out[rel] = (None, st.st_mode, None)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='symblic-core-repair-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.folder = os.path.join(self.tmp, 'run')
        os.makedirs(self.folder, mode=0o700)
        sync = mock.patch.object(FX, 'SYNC', False)       # durability is not what these tests measure
        sync.start()
        self.addCleanup(sync.stop)
        FX.set_catalogue(None)
        self.addCleanup(FX.set_catalogue, None)
        for sig in (signal.SIGTERM, signal.SIGINT):        # the runners install their own handlers
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))

    def execute(self, source=ACT, answer='Alpha', **options):
        apps, host = Apps(answer), Host()
        opts = {'effects': host, 'side_effects': True, **options}
        report = SR.Run(source, applicators=apps, options=opts, folder=self.folder).execute()
        return report, apps, host

    def path(self, name):
        return os.path.join(self.folder, name)

    def read_json(self, name):
        with open(self.path(name), encoding='utf-8') as stream:
            return json.load(stream)

    def lose(self, drop_trace=False):
        """Make the folder look like one written before kernel.json existed, by a run that was killed: its last
        state.json is an intermediate one, without the final report's kernel."""
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.path(RECORD))
        with open(self.path('state.json'), 'w', encoding='utf-8') as stream:
            json.dump({'program': 'Untitled', 'status': 'running', 'asks': 1, 'calls': 1, 'progress': [1, 2],
                       'seconds': 0.2, 'updated': 1.0}, stream)
        if drop_trace:
            os.unlink(self.path('trace.jsonl'))

    def assert_refused(self, report, apps, host, before, reason):
        self.assertEqual([], apps.requests)                     # nothing asked again
        self.assertEqual([], host.performed)                   # nothing performed again
        self.assertEqual(before, snapshot(self.folder))        # status, trace, calls, ledgers: untouched
        self.assertEqual('failed', report['status'])           # this invocation was refused ...
        self.assertEqual('SYM_VERSION', report['error']['code'])
        check = report['kernel_check']                         # ... and says why, for a program to read
        self.assertEqual(('refused', reason), (check['decision'], check['reason']))
        self.assertEqual(S.kernel_id()['id'], check['current']['id'])
        message = report['error']['message']
        for part in (S.kernel_id()['id'], 'Nothing was asked or performed', 'start a new run', 'lock'):
            self.assertIn(part, message)
        return check, message


class CrossKernelResume(Base):
    def test_review_scenario_answered_ask_and_performed_act_of_another_kernel_are_refused(self):
        with old_kernel():
            first, apps, host = self.execute(answer='Alpha')
        self.assertEqual('done', first['status'], first['error'])
        self.assertEqual((1, [{'text': 'Alpha'}]), (len(apps.requests), host.performed))
        before = snapshot(self.folder)
        report, apps, host = self.execute(answer='Beta')       # unrefused, Beta was posted after Alpha
        check, message = self.assert_refused(report, apps, host, before, 'changed')
        self.assertEqual((1, 1), (check['answered_calls'], check['effects']))
        for part in ('Symblic 2.4', OLD_ID, 'up to 1 answered model call', '1 recorded effect',
                     # review of lane A: an agent in full mode may follow the safe option literally, and this run
                     # had posted, so the option says that a new run does it again
                     'start a new run of this program here (it asks everything again and performs its effects again'):
            self.assertIn(part, message)
        self.assertEqual('done', self.read_json('state.json')['status'])

    def test_same_kernel_resume_serves_every_answer_and_repeats_no_effect(self):
        first, apps, host = self.execute(answer='Alpha')
        self.assertEqual('done', first['status'], first['error'])
        self.assertEqual((1, [{'text': 'Alpha'}]), (len(apps.requests), host.performed))
        record = self.read_json(RECORD)
        self.assertEqual((S.kernel_id()['id'], S.VERSION, 'first_execution'),
                         (record['id'], record['lang'], record['basis']))
        with open(self.path(RECORD), 'rb') as stream:
            raw = stream.read()
        resumed, apps, host = self.execute(answer='Beta')
        self.assertEqual('done', resumed['status'], resumed['error'])
        self.assertEqual((0, 1, []), (len(apps.requests), resumed['cached'], host.performed))
        self.assertEqual(first['fingerprint'], resumed['fingerprint'])
        self.assertNotIn('kernel_check', resumed)
        with open(self.path(RECORD), 'rb') as stream:
            self.assertEqual(raw, stream.read())               # written once, at the first execution

    def test_legacy_folder_whose_only_identity_is_its_trace_rows(self):
        with old_kernel():
            self.execute(answer='Alpha')
        self.lose()
        before = snapshot(self.folder)
        report, apps, host = self.execute(answer='Beta')
        check, message = self.assert_refused(report, apps, host, before, 'changed')
        self.assertEqual([{'source': 'trace.jsonl', 'id': OLD_ID, 'lang': '2.4', 'rows': 2}], check['recorded'])
        self.assertIn('Symblic 2.4 (kernel 0b2cca3828a1965a)', message)

    def test_legacy_same_kernel_folder_resumes_and_adopts_the_identity_of_its_trace(self):
        self.execute(answer='Alpha')
        self.lose()
        resumed, apps, host = self.execute(answer='Beta')
        self.assertEqual('done', resumed['status'], resumed['error'])
        self.assertEqual((0, 1, []), (len(apps.requests), resumed['cached'], host.performed))
        record = self.read_json(RECORD)
        self.assertEqual((S.kernel_id()['id'], 'trace.jsonl'), (record['id'], record['basis']))

    def test_trace_rows_written_before_kernels_were_recorded_are_another_kernels(self):
        self.execute(answer='Alpha')
        self.lose()
        with open(self.path('trace.jsonl'), encoding='utf-8') as stream:
            rows = [json.loads(line) for line in stream]
        with open(self.path('trace.jsonl'), 'w', encoding='utf-8') as stream:
            stream.writelines(json.dumps({k: v for k, v in r.items() if k != 'kernel'}) + '\n' for r in rows)
        before = snapshot(self.folder)
        report, apps, host = self.execute(answer='Beta')
        check, message = self.assert_refused(report, apps, host, before, 'changed')
        self.assertEqual([None], [r['id'] for r in check['recorded']])
        self.assertIn('did not record its identity', message)

    def test_final_state_report_identifies_a_folder_without_trace(self):
        with old_kernel():
            self.execute(answer='Alpha')
        os.unlink(self.path(RECORD))
        os.unlink(self.path('trace.jsonl'))                    # e.g. a fresh restart dropped it; the report stays
        before = snapshot(self.folder)
        report, apps, host = self.execute(answer='Beta')
        check, _message = self.assert_refused(report, apps, host, before, 'changed')
        self.assertEqual(['state.json'], [r['source'] for r in check['recorded']])

    def test_unreadable_record_with_work_is_not_trusted(self):
        self.execute(answer='Alpha')
        for damaged in ('{torn', json.dumps({'version': 2, 'id': S.kernel_id()['id'], 'lang': S.VERSION})):
            with self.subTest(damaged=damaged):
                with open(self.path(RECORD), 'w', encoding='utf-8') as stream:
                    stream.write(damaged)
                before = snapshot(self.folder)
                report, apps, host = self.execute(answer='Beta')
                check, message = self.assert_refused(report, apps, host, before, 'changed')
                self.assertIn(RECORD, message)


class UnknownIdentity(Base):
    def test_answered_calls_without_any_identity_are_refused_as_unknown(self):
        self.execute(answer='Alpha')                           # really today's kernel, but nothing says so
        self.lose(drop_trace=True)
        before = snapshot(self.folder)
        report, apps, host = self.execute(answer='Beta')
        check, message = self.assert_refused(report, apps, host, before, 'unknown')
        self.assertEqual(([], 1, 1), (check['recorded'], check['answered_calls'], check['effects']))
        self.assertIn('no record of the kernel', message)

    def test_effects_without_any_identity_are_refused_as_unknown(self):
        first, apps, host = self.execute(POST_ONLY)
        self.assertEqual((0, [{'text': 'Hello'}]), (len(apps.requests), host.performed))
        self.lose(drop_trace=True)
        before = snapshot(self.folder)
        report, apps, host = self.execute(POST_ONLY)
        check, _message = self.assert_refused(report, apps, host, before, 'unknown')
        self.assertEqual((0, 1), (check['answered_calls'], check['effects']))

    def test_a_ledger_seeded_without_any_run_is_left_to_the_effects_receipts(self):
        # every run writes state.json before its first statement: a ledger alone is not this folder's work, and
        # the effects module refuses its unvouched action by itself (as test_symblic_effects expects)
        args = {'text': 'Hello'}
        FX.Ledger(self.path(FX.LEDGER)).append({'id': FX.effect_id('msg.post', args), 'kind': 'act',
                                                 'capability': 'msg.post', 'args': args, 'phase': 'intent',
                                                 'attempt': 1})
        report, apps, host = self.execute(POST_ONLY)
        self.assertEqual(('failed', 'uncertain', []), (report['status'], report['error']['kind'], host.performed))
        self.assertNotIn('kernel_check', report)
        self.assertEqual('first_execution', self.read_json(RECORD)['basis'])

    def test_a_page_folder_says_which_version_created_it(self):
        with open(self.path('meta.json'), 'w', encoding='utf-8') as stream:
            json.dump({'title': 'page', 'inputs': {}, 'options': {}, 'version': '2.4'}, stream)
        self.execute(answer='Alpha')
        self.lose(drop_trace=True)
        before = snapshot(self.folder)
        report, apps, host = self.execute(answer='Beta')
        _check, message = self.assert_refused(report, apps, host, before, 'unknown')
        self.assertIn('created under Symblic 2.4', message)


class FreshFolders(Base):
    def test_a_folder_where_nothing_ran_yet_runs_and_records_its_kernel(self):
        report, apps, host = self.execute(answer='Alpha')
        self.assertEqual('done', report['status'], report['error'])
        self.assertEqual((1, [{'text': 'Alpha'}]), (len(apps.requests), host.performed))
        record = self.read_json(RECORD)
        self.assertEqual((1, S.kernel_id()['id'], S.VERSION, 'first_execution'),
                         (record['version'], record['id'], record['lang'], record['basis']))
        self.assertEqual(S.kernel_id()['id'], record['kernel']['id'])
        self.assertEqual(0o600, os.stat(self.path(RECORD)).st_mode & 0o777)

    def test_a_stale_record_without_work_is_replaced(self):
        with open(self.path(RECORD), 'w', encoding='utf-8') as stream:
            json.dump({'version': 1, 'id': OLD_ID, 'lang': '2.4'}, stream)
        report, apps, _host = self.execute(answer='Alpha')
        self.assertEqual('done', report['status'], report['error'])
        self.assertEqual(1, len(apps.requests))
        self.assertEqual(S.kernel_id()['id'], self.read_json(RECORD)['id'])

    def test_a_folder_without_folder_runs_as_before(self):
        report = SR.Run(ASKS, applicators=Apps('Alpha'), options={}).execute()
        self.assertEqual('done', report['status'], report['error'])
        self.assertNotIn('kernel_check', report)


class PageRunner(Base):
    def page(self, version='2.4'):
        with open(self.path('program.sym'), 'w', encoding='utf-8') as stream:
            stream.write(ASKS)
        with open(self.path('meta.json'), 'w', encoding='utf-8') as stream:
            json.dump({'title': 'page', 'inputs': {}, 'options': {'by': 'fake:a'}, 'version': version}, stream)

    def run_folder(self, resume, answer):
        apps = Apps(answer)
        with contextlib.redirect_stdout(io.StringIO()):
            report = SR.run_folder(self.folder, resume=resume, applicators=apps)
        return report, apps

    def log_text(self):
        try:
            with open(self.path('log.txt'), encoding='utf-8') as stream:
                return stream.read()
        except FileNotFoundError:
            return ''

    def test_page_resume_of_another_kernels_run_is_refused_and_its_log_says_why(self):
        self.page()
        with old_kernel():
            first, apps = self.run_folder(False, 'Alpha')
        self.assertEqual(('done', 2), (first['status'], len(apps.requests)))
        state = self.read_json('state.json')
        state['status'] = 'stopped'                            # the owner stopped it before the deploy
        with open(self.path('state.json'), 'w', encoding='utf-8') as stream:
            json.dump(state, stream)
        for resume in (True, False):                           # Resume, and a fresh start of the same folder
            with self.subTest(resume=resume):
                before, log = snapshot(self.folder, skip=('log.txt',)), self.log_text()
                report, apps = self.run_folder(resume, 'Beta')
                self.assertEqual([], apps.requests)
                self.assertEqual(before, snapshot(self.folder, skip=('log.txt',)))     # the trace is kept too
                self.assertEqual(('failed', 'SYM_VERSION'), (report['status'], report['error']['code']))
                added = self.log_text()[len(log):]
                self.assertIn('Resume refused', added)
                self.assertIn(OLD_ID, added)
                self.assertNotIn('failed:', added)
                self.assertIn('(it asks everything again, as a new run)', added)     # no effect was recorded
                self.assertEqual('stopped', self.read_json('state.json')['status'])

    def test_page_fresh_start_of_a_lost_same_kernel_legacy_folder_keeps_its_answers(self):
        self.page(version=S.VERSION)
        first, apps = self.run_folder(False, 'Alpha')
        self.assertEqual(('done', 2), (first['status'], len(apps.requests)))
        self.lose()
        again, apps = self.run_folder(False, 'Beta')
        self.assertEqual('done', again['status'], again['error'])
        self.assertEqual((0, 2), (len(apps.requests), again['cached']))
        self.assertEqual('trace.jsonl', self.read_json(RECORD)['basis'])          # adopted before the trace went


class Pinned(Base):
    def test_execution_pins_carry_a_pinned_runs_identity(self):
        from symblic.kernel import execution_pins as X
        with mock.patch.object(X, 'prepare', lambda run: None):    # the pin checker itself is tested elsewhere
            pins = {'kernel_id': S.kernel_id()['id']}
            first, apps, _host = self.execute(answer='Alpha', execution_pins=pins)
            self.assertEqual(('done', 1), (first['status'], len(apps.requests)))
            self.assertFalse(os.path.exists(self.path(RECORD)))        # the caller's pins already record it
            again, apps, host = self.execute(answer='Beta', execution_pins=pins)
            self.assertEqual(('done', 0, 1, []), (again['status'], len(apps.requests), again['cached'], host.performed))
            before = snapshot(self.folder)
            report, apps, host = self.execute(answer='Beta', execution_pins={'kernel_id': OLD_ID})
        check, _message = self.assert_refused(report, apps, host, before, 'changed')
        self.assertIn({'source': 'execution_pins', 'id': OLD_ID, 'lang': None}, check['recorded'])


class Replay(Base):
    def test_a_lock_still_replays_with_no_model(self):
        from symblic.kernel import lockfile as K
        with open(self.path('program.sym'), 'w', encoding='utf-8') as stream:
            stream.write(ASKS)
        with open(self.path('meta.json'), 'w', encoding='utf-8') as stream:
            json.dump({'inputs': {}, 'options': {'by': 'fake:a'}}, stream)
        report = SR.Run(ASKS, {}, Apps('Alpha'), {'by': 'fake:a'}, folder=self.folder).execute()
        self.assertEqual('done', report['status'], report['error'])
        result = K.replay(K.make_lock(self.folder))
        self.assertTrue(result['ok'], result)
        self.assertEqual((0, 2, []), (result['calls'], result['cached'], result['refused']))


# ---------------------------------------------------------------------------------------------------------------
# Lineage: epistemic-1, -2, -3, -5 and language-2
# ---------------------------------------------------------------------------------------------------------------

class Answers:
    """Answers the i-th call with answers[i] (the last one repeats), from any thread; keeps every request."""

    def __init__(self, *answers):
        self.answers, self.requests, self.lock = answers or (2,), [], threading.Lock()

    def call(self, req):
        with self.lock:
            index = len(self.requests)
            self.requests.append(req)
        return {'ok': True, 'json': {'answer': self.answers[min(index, len(self.answers) - 1)]},
                'model': 'fake', 'node': 'isolated'}


def lineage_run(source, *answers, profile='legacy', apps=None, **options):
    apps = apps or Answers(*answers)
    run = SR.Run(source, applicators=apps, options={'by': 'fake:a', 'profile': profile, **options})
    return run, run.execute(), apps


def assessment(run, name):
    return run.kernel.env.lookup(name).meta['epistemic']['assessment']


def root_ids(run, name):
    return {row['ref']['id'] for row in assessment(run, name)['conditional_on']}


def origins(run, name):
    return {row['origin'] for row in assessment(run, name)['conditional_on']}


def prompt_provenance(request, name):
    """The provenance line the capsule printed under the context row of `name`."""
    lines = request['prompt'].splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f'- {name} :'):
            return json.loads(lines[i + 1].split('provenance: ', 1)[1])
    raise AssertionError(f'no context row for {name}')


class LineageCase(unittest.TestCase):
    def assert_done(self, report):
        self.assertEqual('done', report['status'], report.get('error'))

    def assert_no_assumption(self, report):
        """Nothing in these programs is an assumption: a value made by the kernel from what it read has that
        lineage, and a premise keeps its own origin."""
        self.assertEqual([], [c['content'] for c in report['epistemic']['claims'] if c['origin'] == 'assumption'])


class LoopLineage(LineageCase):
    """epistemic-1: a for statement's lists keep what each iteration's value was computed from."""

    def test_loop_collected_model_answers_keep_their_model_roots(self):
        source = ('given items: List of Int = [1, 2].\nfor item in items do\n'
                  'ask guess: Int "Give the population of city {item}" from item with effort=low\nend\n'
                  'let total = guess.\nask out: Int "Use total" from guess with effort=low\n')
        for profile in ('verified', 'legacy'):
            with self.subTest(profile=profile):
                run, report, apps = lineage_run(source, 7, 8, 9, profile=profile)
                self.assert_done(report)
                asked = {row['epistemic']['claim']['id'] for row in run.trace
                         if row['kind'] == 'ask' and row.get('name') == 'guess'}
                self.assertEqual(2, len(asked))
                for name in ('guess', 'total'):
                    self.assertLessEqual(asked, root_ids(run, name), name)       # every iteration's answer
                    self.assertEqual({'model_proposal', 'owner_premise'}, origins(run, name))
                provenance = prompt_provenance(apps.requests[-1], 'guess')     # what the next model is told
                self.assertIn('model_proposal', provenance['root_origins'])
                self.assertEqual(3, provenance['conditional_root_count'])
                self.assert_no_assumption(report)

    def test_contested_inner_ask_makes_the_list_unavailable_as_the_single_ask_does(self):
        single = 'ask guess: Int "Population?" with effort=low, votes=2\nlet total = guess.\n'
        looped = ('for item in [1] do\nask guess: Int "Population of {item}?" with effort=low, votes=2\nend\n'
                  'let total = guess.\n')
        run, report, _ = lineage_run(single, 1, 11)
        self.assert_done(report)
        expected = {k: assessment(run, 'total')[k] for k in ('status', 'admissible', 'support')}
        self.assertEqual({'status': 'unknown', 'admissible': False, 'support': 'unavailable'}, expected)
        run, report, _ = lineage_run(looped, 1, 11)
        self.assert_done(report)
        self.assertEqual(['contested'], [r['status'] for r in run.trace if r['kind'] == 'ask'])
        for name in ('guess', 'total'):
            view = assessment(run, name)
            self.assertEqual(expected, {k: view[k] for k in expected}, name)
            self.assertIn('unavailable_dependency', [issue['code'] for issue in view['issues']])
            self.assertEqual([('model_proposal', 'contested')],
                             [(r['origin'], r['status']) for r in view['conditional_on']])
        self.assert_no_assumption(report)

    def test_loop_variable_is_an_element_of_its_source_not_an_assumption(self):
        run, report, _ = lineage_run('given xs: List of Int = [1, 2].\nfor x in xs do\nlet y = x * 2.\nend\n')
        self.assert_done(report)
        self.assertEqual(root_ids(run, 'xs'), root_ids(run, 'y'))
        self.assert_no_assumption(report)
        run, report, _ = lineage_run('for x in 1..3 do\nlet y = x * 2.\nend\n')
        self.assert_done(report)
        self.assertEqual(([], True), (assessment(run, 'y')['conditional_on'], assessment(run, 'y')['admissible']))
        self.assert_no_assumption(report)
        # a context row needs the item's own claim: derived from the source, as `ask ... for each` derives its item
        run, report, apps = lineage_run('given xs: List of Int = [4].\nfor x in xs do\n'
                                        'ask y: Int "Halve {x}" from x with effort=low\nend\n', 2)
        self.assert_done(report)
        provenance = prompt_provenance(apps.requests[0], 'x')
        self.assertEqual(('derived', ['owner_premise']), (provenance['origin'], provenance['root_origins']))
        self.assert_no_assumption(report)

    def test_control_dependencies_reach_bindings_in_a_loop_body(self):
        source = ('ask flag: Bool "flag" with effort=low\nask n: Int "n" with effort=low\n'
                  'for x in 1..n do\nif flag then\nlet y = 1.\nelse\nlet y = 2.\nend\nend\n')
        run, report, _ = lineage_run(source, True, 3)
        self.assert_done(report)
        self.assertEqual((1, 1, 1), run.kernel.env.lookup('y').value)
        for name in ('flag', 'n'):
            self.assertIn(run.kernel.env.lookup(name).meta['epistemic']['claim']['id'], root_ids(run, 'y'), name)

    def test_graph_node_loop_output_keeps_model_roots_downstream(self):
        from symblic.graph import run as GR
        from symblic.js import check as JS
        from tests.graph.test_symblic_graph_run import FakeApps, graph, node
        tmp = tempfile.mkdtemp(prefix='symblic-core-repair-graph-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        a = node('A', source='for item in [1, 2] do\nask guess: Int "Return 2 for {item}" from item with effort=low, '
                             'retries=0\nend\nlet answer = sum(guess).')
        b = node('B', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 1.')
        with mock.patch.object(JS, 'node_version', return_value='test-no-node'):
            state = GR.GraphRun(graph(a, b), os.path.join(tmp, 'graph'), FakeApps()).execute()
        self.assertEqual('succeeded', state['status'], state)
        for row in state['states']:
            record = next(r for r in row['result']['evidence'] if r['scope'] == 'symblic_run')
            view = record['binding_epistemic']['assessment']
            self.assertEqual({'model_proposal'}, {r['origin'] for r in view['conditional_on']}, row['node'])
            self.assertEqual(2, len(view['conditional_on']), row['node'])


def counted_run(source):
    """Run without a model, counting the epistemic work (EP calls) and the kernel's steps."""
    counts = {}
    patches = [mock.patch.object(EP, name, wraps=getattr(EP, name))
               for name in ('reference', 'make_claim', 'validate_claim')]
    mocks = [p.start() for p in patches]
    try:
        run = SR.Run(source, applicators=None, options={})
        report = run.execute()
    finally:
        for p in patches:
            p.stop()
    for name, m in zip(('reference', 'make_claim', 'validate_claim'), mocks):
        counts[name] = m.call_count
    counts['steps'] = S.MAX_STEPS - run.kernel.budget.left
    return run, report, counts


class LoopCost(LineageCase):
    """language-2: an iteration's reads stay in it, and no claim is validated again per parent."""

    def counted(self, source):
        return counted_run(source)

    def test_two_thousand_iterations_do_linear_epistemic_work(self):
        loop = 'given a: Int = 1.\nfor x in 1..{n} do\nlet y = x * 2 + a.\nend\nshow 1.\n'
        sizes, counts = (500, 2000), []
        for n in sizes:
            run, report, used = self.counted(loop.format(n=n))
            self.assert_done(report)
            self.assertEqual(n, len(run.kernel.env.lookup('y').value))
            # the kernel's own work is what the step budget charges, as in 2.4 (7 steps per iteration here)
            self.assertEqual(7 * n + 5, used['steps'])
            # one claim per iteration's binding plus at most one grouping claim per 64 of them; a parent's
            # reference is never validated again (2.5 RC2: 81,738 EP.reference calls at only 400 iterations)
            self.assertLessEqual(used['make_claim'], n + n // 64 + 8, n)
            self.assertLessEqual(used['reference'], 8, n)
            self.assertLessEqual(used['validate_claim'], used['make_claim'] + used['reference'], n)
            counts.append(used)
        self.assertLessEqual(counts[1]['validate_claim'], 4.2 * counts[0]['validate_claim'])   # linear in n
        view = assessment(run, 'y')
        self.assertTrue(view['lineage_complete'])
        self.assertEqual([('owner_premise', 'unknown')], [(r['origin'], r['status']) for r in view['conditional_on']])

    def test_an_iteration_does_not_inherit_the_reads_of_earlier_iterations(self):
        run, report, _ = lineage_run('given a: Int = 1.\nfor x in 1..100 do\nlet y = x + a.\nend\n')
        self.assert_done(report)
        a = EP.reference(run.kernel.env.lookup('a').meta['epistemic']['claim'])
        rows = [row for row in run.trace if row['kind'] == 'let']
        self.assertEqual(100, len(rows))
        self.assertEqual({(a['id'],)}, {tuple(d['id'] for d in row['epistemic']['claim']['dependencies'])
                                        for row in rows})

    def test_comprehension_and_quantifier_items_are_elements_of_what_was_read(self):
        source = ('given xs: List of Int = [1, 2, 3].\nlet ys = [x * 2 for x in xs].\nlet ok = all x in xs: x > 0.\n'
                  'let big = [x for x in 1..3000 if x > 2].\n')
        run, report, counts = self.counted(source)
        self.assert_done(report)
        for name in ('ys', 'ok'):
            self.assertEqual(root_ids(run, 'xs'), root_ids(run, name), name)
        self.assertLessEqual(counts['make_claim'], 6)          # one per binding, none per item
        self.assert_no_assumption(report)

    def test_a_fact_loop_and_its_queries_stay_linear_and_keep_their_premises(self):
        source = ('ask x: Int "x" with effort=low\nfor i in 1..200 do\nfact node(i, x).\nend\n'
                  'let found = [i for i in 1..200 if holds node(i, x)].\n')
        run, report, _ = lineage_run(source, 5)
        self.assert_done(report)
        self.assertEqual(200, len(run.kernel.env.lookup('found').value))
        self.assertIn(run.kernel.env.lookup('x').meta['epistemic']['claim']['id'], root_ids(run, 'found'))
        self.assertEqual({'model_proposal', 'owner_premise'}, origins(run, 'found'))
        self.assertLessEqual(len(report['epistemic']['claims']), 8)
        self.assert_no_assumption(report)


class ContractLineage(LineageCase):
    """epistemic-2: the inputs of the checks that accept an answer stay its parents, whatever the checks call."""

    PROGRAM = ('ask limit: Int "limit" with effort=low{votes}\nfunction positive(v: Int) -> Bool = v > 0.\n'
               'function under(v: Int) -> Bool = v < limit.\n'
               'ask x: Int "x" with effort=low, retries=2\nensure {check} else retry.\nlet doubled = x * 2.\n')

    def test_contract_inputs_survive_user_functions(self):
        for check in ('x < limit', 'positive(x) and x < limit', 'under(x)', 'positive(x) and under(x)'):
            with self.subTest(check=check, profile='legacy'):
                run, report, apps = lineage_run(self.PROGRAM.format(votes=', votes=2', check=check), 10, 20, 3)
                self.assert_done(report)
                self.assertEqual((3, 3), (len(apps.requests), run.kernel.env.lookup('x').value))
                limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']
                x = run.kernel.env.lookup('x').meta['epistemic']['claim']
                self.assertIn(limit['id'], [d['id'] for d in x['dependencies']])
                for name in ('x', 'doubled'):
                    self.assertFalse(assessment(run, name)['admissible'], name)    # limit was contested
                    self.assertIn(limit['id'], root_ids(run, name), name)
            with self.subTest(check=check, profile='verified'):
                run, report, _ = lineage_run(self.PROGRAM.format(votes='', check=check), 10, 50, 3,
                                             profile='verified')
                self.assert_done(report)
                limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
                self.assertIn(limit, root_ids(run, 'x'))      # it rejected 50 and accepted 3
                self.assertTrue(assessment(run, 'x')['lineage_complete'])
                self.assert_no_assumption(report)

    def test_statements_between_the_ask_and_its_check_are_read_whatever_they_are(self):
        source = ('ask offset: Int "offset" with effort=low\nask limit: Int "limit" with effort=low\n'
                  'ask x: Int "x" with effort=low, retries=1\n'
                  'if x > 0 then\nlet y = x + offset.\nelse\nlet y = 0.\nend\n'
                  'ensure y < limit else retry.\n')
        run, report, _ = lineage_run(source, 1, 10, 3, profile='verified')
        self.assert_done(report)
        for name in ('offset', 'limit'):
            self.assertIn(run.kernel.env.lookup(name).meta['epistemic']['claim']['id'], root_ids(run, 'x'), name)
        self.assert_no_assumption(report)

    def test_contract_defaults_and_routine_options_are_read(self):
        # root's review: a default or a routine option is evaluated in the callable's own scope when the check runs,
        # after the ask is bound and outside its read frame
        cases = {'default': 'function under(v: Int, cap: Int = limit) -> Bool = v < cap.\n',
                 'default through a helper': ('function cap_of() -> Int = limit.\n'
                                              'function under(v: Int, cap: Int = cap_of()) -> Bool = v < cap.\n'),
                 'routine option': 'routine under(v: Int) -> Bool with weight=limit do\nreturn v < 10.\nend\n'}
        for label, definitions in cases.items():
            for profile, votes, answers in (('legacy', ', votes=2', (10, 20, 3)), ('verified', '', (10, 50, 3))):
                with self.subTest(case=label, profile=profile):
                    source = (f'ask limit: Int "limit" with effort=low{votes}\n' + definitions +
                              'ask x: Int "x" with effort=low, retries=2\nensure under(x) else retry.\n')
                    run, report, _ = lineage_run(source, *answers, profile=profile)
                    self.assert_done(report)
                    limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
                    x = run.kernel.env.lookup('x').meta['epistemic']['claim']
                    self.assertIn(limit, [d['id'] for d in x['dependencies']])
                    self.assertIn(limit, root_ids(run, 'x'))
                    self.assertEqual(profile == 'verified', assessment(run, 'x')['admissible'])

    def test_a_module_function_called_through_its_alias_is_followed(self):
        from symblic.lang import abstraction as SL
        module = 'let cap = 10.\nfunction under(v: Int, c: Int = cap) -> Bool = v < c.\n'
        source = 'import "limits" as m.\nask x: Int "x" with effort=low, retries=2\nensure m.under(x) else retry.\n'
        with mock.patch.object(SL, 'saved_source', side_effect=lambda name: module if name == 'limits' else None):
            run, report, apps = lineage_run(source, 20, 3)
        self.assert_done(report)
        self.assertEqual((2, 3), (len(apps.requests), run.kernel.env.lookup('x').value))
        claims = {claim['id']: claim for claim in report['epistemic']['claims']}
        x = run.kernel.env.lookup('x').meta['epistemic']['claim']
        # the module's default `cap` decided which answer was accepted (20 was rejected)
        self.assertIn('cap', [claims[d['id']]['content']['name'] for d in x['dependencies']])

    def test_a_function_or_imported_alias_that_queries_knowledge_keeps_its_premises(self):
        # root's review: a check that calls a helper which queries the knowledge base reads the declared facts
        from symblic.lang import abstraction as SL
        checks = {'function': ('function allowed_value(v: Int) -> Bool = holds allowed(v).\n', 'allowed_value(x)'),
                  'imported alias': ('import "Checker" as c.\n', 'c.seen(x)')}
        module = 'function seen(v: Int) -> Bool = holds allowed(v).\n'
        for label, (definition, check) in checks.items():
            with self.subTest(case=label):
                source = ('ask limit: Int "limit" with effort=low, votes=2\nfact allowed(limit).\n' + definition +
                          f'ask x: Int "x" with effort=low\nensure {check} else retry.\nlet doubled = x * 2.\n')
                with mock.patch.object(SL, 'saved_source', side_effect=lambda name: module if name == 'Checker'
                                       else None):
                    run, report, _ = lineage_run(source, 10, 20, 10)
                self.assert_done(report)
                limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
                for name in ('x', 'doubled'):
                    self.assertIn(limit, root_ids(run, name), name)
                    self.assertFalse(assessment(run, name)['admissible'], name)      # limit was contested

    def test_a_for_each_contract_input_is_a_parent_of_the_list(self):
        source = ('ask limit: Int "limit" with effort=low\ngiven items: List of Int = [1, 2].\n'
                  'ask xs: Int "x for {item}" for each item in items with effort=low, retries=1\n'
                  'ensure all v in xs: v < limit else retry.\n')
        run, report, _ = lineage_run(source, 10, 3, profile='verified')
        self.assert_done(report)
        self.assertIn(run.kernel.env.lookup('limit').meta['epistemic']['claim']['id'], root_ids(run, 'xs'))
        self.assert_no_assumption(report)


class MemoLineage(LineageCase):
    """Root review: a routine's memoized result keeps the lineage of the call that computed it (a snapshot)."""

    def test_a_memo_hit_keeps_the_lineage_of_the_call_that_filled_it(self):
        source = ('ask limit: Int "limit" with effort=low, votes=2\nfact allowed(limit).\n'
                  'routine allowed_value(v: Int) -> Bool do\nreturn holds allowed(v).\nend\n'
                  'let initial = allowed_value(10).\nlet cached = allowed_value(10).\n')
        run, report, apps = lineage_run(source, 10, 20)
        self.assert_done(report)
        self.assertEqual(2, len(apps.requests))
        self.assertIn('same call, recorded', [row.get('note', '') for row in run.trace if row['kind'] == 'call'][1])
        limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
        self.assertEqual(assessment(run, 'initial')['conditional_on'], assessment(run, 'cached')['conditional_on'])
        for name in ('initial', 'cached'):
            self.assertIn(limit, root_ids(run, name), name)
            self.assertFalse(assessment(run, name)['admissible'], name)          # limit was contested

    def test_a_memo_hit_is_a_snapshot_not_a_fresh_reading(self):
        # the cached value is what the first call computed; its lineage is that call's basis, not the facts
        # declared since (nothing is re-executed: a routine may have effects)
        source = ('fact allowed(0).\nroutine seen(v: Int) -> Bool do\nreturn holds allowed(v).\nend\n'
                  'let before = seen(1).\nfact allowed(1).\nlet after = seen(1).\nlet actual = holds allowed(1).\n')
        run, report, _ = lineage_run(source)
        self.assert_done(report)
        values = {name: run.kernel.env.lookup(name).value for name in ('before', 'after', 'actual')}
        self.assertEqual({'before': False, 'after': False, 'actual': True}, values)
        later = [row['epistemic']['claim']['id'] for row in run.trace if row['kind'] == 'fact'][1]
        self.assertEqual(root_ids(run, 'before'), root_ids(run, 'after'))
        self.assertNotIn(later, root_ids(run, 'after'))
        self.assertIn(later, root_ids(run, 'actual'))

    def test_a_rejected_attempt_leaves_no_lineage_index_behind(self):
        source = ('given root: Int = 2.\nroutine twice(v: Int) -> Int do\nreturn v * 2.\nend\n'
                  'ask x: Int "x" with effort=low, retries=1\nfor i in 1..70 do\nlet y = x + root + i.\nend\n'
                  'let t = twice(x).\nensure x < root else retry.\nlet final = y.\n')
        run, report, apps = lineage_run(source, 3, 1)
        self.assert_done(report)
        self.assertEqual(2, len(apps.requests))
        registry = run._epistemic_claims
        self.assertEqual(set(), set(run._epistemic_rootsets) - set(registry))
        self.assertEqual([], [d['id'] for claim in registry.values() for d in claim['dependencies']
                              if d['id'] not in registry])
        self.assertEqual(1, len(run._memo_bases))          # the rejected attempt's call is forgotten with its memo


class LineageBounds(LineageCase):
    """epistemic-3: past 64 parents or roots nothing becomes admissible and no root is relabelled."""

    def test_more_than_sixty_four_parents_keep_admissibility_and_origins(self):
        for givens in (3, 63, 64, 100):
            with self.subTest(parents=givens + 1):
                source = '\n'.join(f'given a{i}: Int = {i}.' for i in range(givens))
                source += '\nask guess: Int "Population?" with effort=low, votes=2\n'
                source += 'let total = guess + ' + ' + '.join(f'a{i}' for i in range(givens)) + '.\n'
                run, report, _ = lineage_run(source, 1, 11)
                self.assert_done(report)
                view = assessment(run, 'total')
                self.assertEqual(('unknown', False, 'unavailable'), (view['status'], view['admissible'],
                                                                      view['support']))
                self.assertIn('unavailable_dependency', [issue['code'] for issue in view['issues']])
                self.assertIn(('model_proposal', 'contested'),
                              [(r['origin'], r['status']) for r in view['conditional_on']])
                self.assertEqual({'model_proposal', 'owner_premise'}, origins(run, 'total'))
                claim = run.kernel.env.lookup('total').meta['epistemic']['claim']
                self.assertLessEqual(len(claim['dependencies']), EP.MAX_REFS)
                self.assert_no_assumption(report)

    def test_more_than_sixty_four_roots_are_counted_never_relabelled(self):
        source = '\n'.join(f'ask x{i}: Int "x{i}" with effort=low' for i in range(80)) + '\n'
        source += 'let d1 = ' + ' + '.join(f'x{i}' for i in range(40)) + '.\n'
        source += 'let d2 = ' + ' + '.join(f'x{i}' for i in range(40, 80)) + '.\n'
        source += 'let t = d1 + d2.\nask out: Int "Use t" from t with effort=low\n'
        run, report, apps = lineage_run(source, 1, profile='verified', max_asks=200)
        self.assert_done(report)
        view = assessment(run, 't')
        self.assertEqual(({'model_proposal'}, False), (origins(run, 't'), view['lineage_complete']))
        self.assertEqual(EP.MAX_REFS, len(view['conditional_on']))
        omitted = view['roots_omitted']
        self.assertEqual((80, 80 - EP.MAX_REFS), (omitted['total'], omitted['count']))
        self.assertEqual([{'origin': 'model_proposal', 'status': 'unknown', 'count': 80 - EP.MAX_REFS}],
                         omitted['by_origin_status'])
        provenance = prompt_provenance(apps.requests[-1], 't')
        self.assertEqual((['model_proposal'], 80, False), (provenance['root_origins'],
                                                          provenance['conditional_root_count'],
                                                          provenance['lineage_complete']))
        self.assert_no_assumption(report)

    def test_a_contested_root_is_listed_however_many_roots_there_are(self):
        source = '\n'.join(f'given a{i}: Int = {i}.' for i in range(100))
        source += '\nask guess: Int "Population?" with effort=low, votes=2\n'
        source += 'let total = guess + ' + ' + '.join(f'a{i}' for i in range(100)) + '.\n'
        run, report, _ = lineage_run(source, 1, 11)
        self.assert_done(report)
        view = assessment(run, 'total')
        guess = run.kernel.env.lookup('guess').meta['epistemic']['claim']['id']
        self.assertIn(guess, root_ids(run, 'total'))
        self.assertEqual(101, view['roots_omitted']['total'])

    def test_grouped_lineage_matches_the_pure_evaluator(self):
        source = 'given g: Int = 1.\ngiven h: Int = 2.\n'
        source += '\n'.join(f'let l{i} = g * {i} + h.' for i in range(100))
        source += '\nlet total = ' + ' + '.join(f'l{i}' for i in range(100)) + '.\n'
        run, report, _ = lineage_run(source)
        self.assert_done(report)
        claim = run.kernel.env.lookup('total').meta['epistemic']['claim']
        self.assertEqual(2, len(claim['dependencies']))              # two grouping claims: 64 + 36 parents
        groups = [c for c in report['epistemic']['claims'] if c['content'].get('kind') == 'bounded_lineage_summary']
        self.assertEqual({('derived', 'encoded_derivation')},
                         {(c['origin'], check['scope']) for c in groups for check in c['checks']})
        expected = EP.evaluate(report['epistemic']['claims'])
        for view in report['epistemic']['assessments']:
            self.assertEqual({k: view[k] for k in expected[view['id']]}, expected[view['id']])
        self.assertTrue(assessment(run, 'total')['lineage_complete'])


class ForEachLineage(LineageCase):
    """epistemic-5: what `ask ... for each` workers read is the statement's read."""

    def test_facts_shown_to_the_workers_stay_in_the_lineage(self):
        for each in (False, True):
            source = 'ask x: Int "x" with effort=low, votes=2\nfact reading(x).\ngiven items: List of Int = [1].\n'
            source += ('ask out: Int "Read the reading fact for {item}" for each item in items with context=facts, '
                       'effort=low\n' if each else
                       'ask out: Int "Read the reading fact" with context=facts, effort=low\n')
            with self.subTest(each=each):
                run, report, apps = lineage_run(source, 1, 11, 7)
                self.assert_done(report)
                self.assertIn('reading(', apps.requests[-1]['prompt'])
                self.assertIn(run.kernel.env.lookup('x').meta['epistemic']['claim']['id'], root_ids(run, 'out'))
                view = assessment(run, 'out')
                self.assertFalse(view['admissible'])                      # x was contested
                self.assertIn('unavailable_dependency', [issue['code'] for issue in view['issues']])

    def test_key_inputs_read_by_the_workers_stay_in_the_lineage(self):
        for each in (False, True):
            source = 'ask x: Int "x" with effort=low\ngiven items: List of Int = [1].\n'
            source += ('ask out: Int "pick for {item}" for each item in items with effort=low, key=it % (x + 1)\n'
                       if each else 'ask out: Int "pick" with effort=low, key=it % (x + 1)\n')
            with self.subTest(each=each):
                run, report, _ = lineage_run(source, 5, 7, profile='verified')
                self.assert_done(report)
                self.assertIn(run.kernel.env.lookup('x').meta['epistemic']['claim']['id'], root_ids(run, 'out'))

    def test_concurrent_workers_reads_are_all_merged(self):
        class Together(Answers):
            """The two item calls wait for each other: both workers are in flight at once."""
            def __init__(self):
                super().__init__(3, 4, 7)
                self.items = threading.Barrier(2)

            def call(self, req):
                reply = super().call(req)
                if 'pick for' in req['prompt']:
                    self.items.wait(timeout=10)
                return reply
        source = ('ask x1: Int "x1" with effort=low\nask x2: Int "x2" with effort=low\n'
                  'given items: List of Int = [1, 2].\n'
                  'ask out: Int "pick for {item}" for each item in items with effort=low, '
                  'key=it % (if item = 1 then x1 else x2)\n')
        run, report, apps = lineage_run(source, profile='verified', apps=Together(), parallel=2)
        self.assert_done(report)
        for name in ('x1', 'x2'):                       # each is read by one worker only, in that worker's thread
            self.assertIn(run.kernel.env.lookup(name).meta['epistemic']['claim']['id'], root_ids(run, 'out'), name)
        self.assertEqual(4, len(apps.requests))


# ---------------------------------------------------------------------------------------------------------------
# Review of lane A (2026-10-05): what decided a routine's loop, callables introduced between an ask and its check,
# the record's durability switch, the documented claim semantics, and the call-key tripwire
# ---------------------------------------------------------------------------------------------------------------

PREMISE = 'ask limit: Int "limit" with effort=low, votes=2\nfact allowed(limit).\n'


def premise_claim(run):
    """The claim of the program's first fact statement (the `allowed(limit)` premise)."""
    return [row['epistemic']['claim']['id'] for row in run.trace if row['kind'] == 'fact'][0]


class LoopExitLineage(LineageCase):
    """language-2 review (blocking): in a routine, a loop whose body can `return`. Whether an iteration returned, and
    so what the routine returns from inside the loop or after it, is decided by what every iteration so far read. No
    lifted binding carries those reads out of the iteration scopes, and a knowledge query leaves no static trace, so
    only the reads themselves carry its premise (RC2 kept them: every read reached every frame)."""

    ROUTINES = {
        'a query selects the returned element': (
            'routine pick(xs: List of Int) -> Int do\n  for v in xs do\n    if holds allowed(v) then\n'
            '      return v.\n    end\n  end\n  return 0.\nend\nlet r = pick([5, 1, 11]).\n'),
        'a query is returned from inside the loop': (
            'routine first_ok(xs: List of Int) -> Bool do\n  for v in xs do\n    return holds allowed(v).\n'
            '  end\n  return false.\nend\nlet r = first_ok([1, 5]).\n'),
        'the loop finishes and no iteration returned': (
            'routine any_allowed(xs: List of Int) -> Bool do\n  for v in xs do\n    if holds allowed(v) then\n'
            '      return true.\n    end\n  end\n  return false.\nend\nlet r = any_allowed([5, 7]).\n'),
        'an earlier iteration queried and went on': (
            'routine pick(xs: List of Int) -> Int do\n  for v in xs do\n    if v = 1 then\n'
            '      if holds allowed(5) then\n        return 5.\n      end\n    else\n      return v.\n    end\n'
            '  end\n  return 0.\nend\nlet r = pick([1, 2]).\n'),
        'an inner loop finished in an earlier outer iteration': (
            'routine pick(ws: List of Int) -> Int do\n  for w in ws do\n    if w = 2 then\n      return w.\n'
            '    end\n    for v in [5, 7] do\n      if holds allowed(v) then\n        return v.\n      end\n'
            '    end\n  end\n  return 0.\nend\nlet r = pick([1, 2]).\n'),
    }

    def test_what_decided_a_routines_loop_stays_in_its_result(self):
        for label, routine in self.ROUTINES.items():
            for profile in ('legacy', 'verified'):
                with self.subTest(case=label, profile=profile):
                    source = PREMISE + routine
                    if profile == 'verified':
                        source = source.replace(', votes=2', '')
                    run, report, _ = lineage_run(source, 1, 11, profile=profile)
                    self.assert_done(report)
                    limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
                    self.assertLessEqual({limit, premise_claim(run)}, root_ids(run, 'r'))
                    self.assertLessEqual({'model_proposal', 'owner_premise'}, origins(run, 'r'))
                    # legacy: limit's two votes disagree, so whatever the premise decided is unavailable
                    self.assertEqual(profile == 'verified', assessment(run, 'r')['admissible'])

    def test_a_memo_hit_of_such_a_routine_keeps_the_same_lineage(self):
        source = PREMISE + ('routine first_ok(xs: List of Int) -> Bool do\n  for v in xs do\n'
                            '    return holds allowed(v).\n  end\n  return false.\nend\n'
                            'let r = first_ok([1, 5]).\nlet r2 = first_ok([1, 5]).\n')
        run, report, apps = lineage_run(source, 1, 11)
        self.assert_done(report)
        self.assertEqual(2, len(apps.requests))
        self.assertIn('same call, recorded', [row.get('note', '') for row in run.trace if row['kind'] == 'call'][1])
        self.assertEqual(assessment(run, 'r')['conditional_on'], assessment(run, 'r2')['conditional_on'])
        for name in ('r', 'r2'):
            self.assertIn(run.kernel.env.lookup('limit').meta['epistemic']['claim']['id'], root_ids(run, name), name)
            self.assertFalse(assessment(run, name)['admissible'], name)

    def test_a_loop_that_can_return_stays_linear(self):
        # only a loop whose body can return keeps its iterations' reads, once, for what follows it: no iteration
        # inherits another's (language-2), so 2,000 iterations cost one claim each, as a loop without return does
        source = ('given a: Int = 1.\nroutine f(xs: List of Int) -> Int do\n  for v in xs do\n'
                  '    if v < 0 then\n      return v.\n    end\n    let y = v * 2 + a.\n  end\n'
                  '  return sum(y).\nend\nlet r = f(1..{n}).\n')
        run, report, counts = counted_run(source.format(n=2000))
        self.assert_done(report)
        self.assertEqual(2000 * 2001, run.kernel.env.lookup('r').value - 2000)
        self.assertLessEqual(counts['make_claim'], 2000 + 2000 // 64 + 16)
        self.assertLessEqual(counts['reference'], 8)
        self.assertIn(run.kernel.env.lookup('a').meta['epistemic']['claim']['id'], root_ids(run, 'r'))
        rows = [row for row in run.trace if row['kind'] == 'let' and row.get('name') == 'y']
        self.assertEqual(2000, len(rows))
        self.assertLessEqual(max(len(row['epistemic']['claim']['dependencies']) for row in rows), 2)


class BetweenCallables(LineageCase):
    """epistemic-2 review: the callable a check uses is introduced between the ask and its ensure. When the ask
    binds, it is not registered yet, so only the statements between can tell what it will read."""

    def test_an_option_of_a_routine_defined_between_the_ask_and_its_check(self):
        for profile, votes, answers in (('legacy', ', votes=2', (10, 20, 3)), ('verified', '', (10, 50, 3))):
            with self.subTest(profile=profile):
                source = (f'ask limit: Int "limit" with effort=low{votes}\nask x: Int "x" with effort=low, retries=2\n'
                          'routine under(v: Int) -> Bool with weight=limit do\n  return v < 10.\nend\n'
                          'ensure under(x) else retry.\nlet doubled = x * 2.\n')
                run, report, _ = lineage_run(source, *answers, profile=profile)
                self.assert_done(report)
                self.assertEqual(3, run.kernel.env.lookup('x').value)
                limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
                x = run.kernel.env.lookup('x').meta['epistemic']['claim']
                self.assertIn(limit, [d['id'] for d in x['dependencies']])
                for name in ('x', 'doubled'):
                    self.assertIn(limit, root_ids(run, name), name)
                    self.assertEqual(profile == 'verified', assessment(run, name)['admissible'], name)

    def test_a_module_imported_between_the_ask_and_its_check_that_queries_knowledge(self):
        from symblic.lang import abstraction as SL
        module = 'function seen(v: Int) -> Bool = holds allowed(v).\n'
        imports = {'alias': 'import "Checker" as c.\nensure c.seen(x) else retry.\n',
                   'names': 'import seen from "Checker".\nensure seen(x) else retry.\n'}
        for label, between in imports.items():
            with self.subTest(form=label):
                source = PREMISE + 'ask x: Int "x" with effort=low, retries=2\n' + between + 'let doubled = x * 2.\n'
                with mock.patch.object(SL, 'saved_source', side_effect=lambda name: module if name == 'Checker'
                                       else None):
                    run, report, _ = lineage_run(source, 10, 20, 10)
                self.assert_done(report)
                limit = run.kernel.env.lookup('limit').meta['epistemic']['claim']['id']
                for name in ('x', 'doubled'):
                    self.assertLessEqual({limit, premise_claim(run)}, root_ids(run, name), name)
                    self.assertFalse(assessment(run, name)['admissible'], name)          # limit was contested


class KernelRecordDurability(unittest.TestCase):
    """language-1 review: kernel.json is fsynced (file and folder) because the effect ledger is; a test that turns
    the ledger's durability off (symblic_effects.SYNC) or this module's (SYNC) does not pay for the record's."""

    def test_the_record_is_fsynced_unless_durability_is_turned_off(self):
        tmp = tempfile.mkdtemp(prefix='symblic-core-repair-sync-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for own, ledger, expected in ((True, True, 2), (False, True, 0), (True, False, 0)):
            with self.subTest(SYNC=own, effects_SYNC=ledger):
                with mock.patch.object(SR, 'SYNC', own), mock.patch.object(FX, 'SYNC', ledger), \
                        mock.patch.object(os, 'fsync', wraps=os.fsync) as fsync:
                    SR._write_kernel_record(tmp, 'first_execution')
                self.assertEqual(expected, fsync.call_count)
                with open(os.path.join(tmp, RECORD), encoding='utf-8') as stream:
                    record = json.load(stream)
                self.assertEqual((S.kernel_id()['id'], 'first_execution'), (record['id'], record['basis']))
                self.assertEqual(0o600, os.stat(os.path.join(tmp, RECORD)).st_mode & 0o777)


class ClaimSemantics(LineageCase):
    """epistemic-1 review (root's decision, 2026-10-05 04:30Z): a view's roots are distinct root claims, not model
    events; the call ledger counts those. Equal answers at one line with one lineage are one claim, and a contested
    answer never merges with an uncontested one, so admissibility stays exact."""

    def test_equal_answers_in_one_loop_are_one_claim_unless_one_is_contested(self):
        source = ('for i in 1..3 do\nask x: Int "Give the value for case {i}" with effort=low, votes=2\nend\n'
                  'let t = sum(x).\n')
        run, report, apps = lineage_run(source, 1, 1, 1, 1, 1, 2)
        self.assert_done(report)
        self.assertEqual(6, len(apps.requests))                    # three questions, two votes each
        claims = [row['epistemic']['claim'] for row in run.trace if row['kind'] == 'ask']
        self.assertEqual(['unknown', 'unknown', 'contested'], [claim['status'] for claim in claims])
        self.assertEqual(claims[0]['id'], claims[1]['id'])
        self.assertNotEqual(claims[0]['id'], claims[2]['id'])
        view = assessment(run, 't')
        self.assertFalse(view['admissible'])
        self.assertEqual([('model_proposal', 'contested'), ('model_proposal', 'unknown')],
                         sorted((row['origin'], row['status']) for row in view['conditional_on']))


class LargeLineage(LineageCase):
    """epistemic-3 review: EP.evaluate stops at MAX_CLAIMS, so a long run's bounded views are checked here against an
    independent walk of the report's claims: roots are the non-derived claims a claim depends on, and a claim is
    admissible when it is neither contested nor refuted, a derivation carries a checked derivation, and every
    dependency is present, pinned and admissible."""

    def test_large_lineage_matches_an_independent_walk_past_the_pure_evaluators_limit(self):
        from symblic.kernel import evidence as E
        source = '\n'.join(f'given a{i}: Int = {i}.' for i in range(70))
        source += '\nask g: Int "g" with effort=low, votes=2\n'
        source += 'let s = g + ' + ' + '.join(f'a{i}' for i in range(70)) + '.\n'
        source += 'for i in 1..1100 do\nlet y = i + s.\nend\nlet total = sum(y).\n'
        run, report, _ = lineage_run(source, 1, 11)
        self.assert_done(report)
        claims = {claim['id']: claim for claim in report['epistemic']['claims']}
        self.assertGreater(len(claims), EP.MAX_CLAIMS)
        with self.assertRaises(EP.EpistemicError):
            EP.evaluate(list(claims.values()))
        roots, admissible = {}, {}

        def walk(ident):
            if ident not in roots:
                claim = claims[ident]
                found, ok = set(), claim['status'] not in ('contested', 'refuted')
                if claim['origin'] == 'derived':
                    ok = ok and any(check['scope'] == 'encoded_derivation' for check in claim['checks'])
                else:
                    found.add(ident)
                for dep in claim['dependencies']:
                    if dep['id'] not in claims or claims[dep['id']]['sha256'] != dep['sha256']:
                        ok = False
                        continue
                    walk(dep['id'])
                    found |= roots[dep['id']]
                    ok = ok and admissible[dep['id']]
                roots[ident], admissible[ident] = found, ok
        views = report['epistemic']['assessments']
        for view in views:
            walk(view['id'])
            listed = {row['ref']['id'] for row in view['conditional_on']}
            self.assertLessEqual(listed, roots[view['id']])
            omitted = view.get('roots_omitted')
            self.assertEqual(len(roots[view['id']]), omitted['total'] if omitted else len(listed), view['id'])
            if omitted:
                pinned = [{k: claims[i][k] for k in ('id', 'revision', 'sha256')} for i in sorted(roots[view['id']])]
                self.assertEqual(E.digest(pinned), omitted['roots_sha256'])
            self.assertEqual(admissible[view['id']], view['admissible'], view['id'])
        total = assessment(run, 'total')
        self.assertEqual((False, 71), (total['admissible'], total['roots_omitted']['total']))    # g and 70 givens


# Call keys hash the exact prompt; the resume gate (language-1) compares kernel_id(). Typical programs, one per kind
# of prompt-shaping lineage, whose call keys are recorded per kernel identity below.
PROMPT_PROGRAMS = {
    'ensure_because_feedback': ('ask n: Int "Give an integer above 10." with effort=low, retries=1\n'
                               'ensure n > 10 else retry because "too small".\n', (3, 12)),
    'escalate_because_feedback': ('ask n: Int in 1..20 "Give an integer above 10." '
                                 'with effort=low, retries=1, route=escalate, determine=false\n'
                                 'ensure n > 10 else retry because "too small".\n', (3, 12)),
    'plain_asks': ('ask a: Text "First title?" with effort=low\n'
                   'ask b: Text "Second title for {a}?" from a with effort=low\nshow [a, b].\n', ('t1', 't2')),
    'given_and_context': ('given topic: Text = "rivers".\n'
                          'ask a: Text "A title about {topic}" from topic with effort=low\n', ('t1',)),
    'comprehension_feeds_context': ('given xs: List of Int = [1, 2, 3].\nlet ys = [x * 2 for x in xs].\n'
                                    'ask a: Int "Sum these" from ys with effort=low\n', (12,)),
    'loop_feeds_context': ('for x in 1..3 do\n  let y = x * 2.\nend\nask a: Int "Sum these" from y with effort=low\n',
                           (12,)),
    'loop_of_asks_feeds_context': ('given items: List of Int = [1, 2].\nfor item in items do\n'
                                   '  ask guess: Int "Value for {item}" from item with effort=low\nend\n'
                                   'ask total: Int "Add them" from guess with effort=low\n', (3, 4, 7)),
    'ensure_with_function': ('ask limit: Int "limit" with effort=low\nfunction under(v: Int) -> Bool = v < limit.\n'
                             'ask x: Int "x" with effort=low, retries=2\nensure under(x) else retry.\n'
                             'ask y: Int "Double it" from x with effort=low\n', (10, 3, 6)),
    'facts_context': ('ask x: Int "x" with effort=low\nfact reading(x).\n'
                      'ask out: Int "Read the reading fact" with context=facts, effort=low\n', (5, 7)),
    'for_each_facts_context': ('ask x: Int "x" with effort=low\nfact reading(x).\ngiven items: List of Int = [1, 2].\n'
                               'ask out: Int "Reading for {item}" for each item in items with context=facts, '
                               'effort=low\n', (5, 7)),
    'routine_loop_return_feeds_context': ('ask limit: Int "limit" with effort=low\nfact allowed(limit).\n'
                                          'routine pick(xs: List of Int) -> Int do\n  for v in xs do\n'
                                          '    if holds allowed(v) then\n      return v.\n    end\n  end\n'
                                          '  return 0.\nend\nlet r = pick([5, 3]).\n'
                                          'ask out: Int "Use r" from r with effort=low\n', (3, 9)),
    'many_roots_feed_context': ('\n'.join(f'ask x{i}: Int "x{i}" with effort=low' for i in range(66)) +
                                '\nlet t = ' + ' + '.join(f'x{i}' for i in range(66)) + '.\n'
                                'ask out: Int "Use t" from t with effort=low\n', (1,)),
}
RC2_KERNEL = '83fa056574158e28'         # 2.5 RC2, live since 2026-10-04 (symblic.py 6c0834f3, symblic_run.py ef68e6c1)
RECORDED_UNICODE = '15.0.0'             # kernel_id() includes it: another Python's identities are recorded elsewhere
# kernel_id() also includes the Node.js version the JavaScript adapter runs (another engine may give other results),
# so a machine with another Node (or none) has another identity: the keys below are recorded for this one.
RECORDED_NODE = '22.17.0'
# kernel id -> program -> digest of its sorted call keys (16 hex). A deployment whose identity is listed must give
# exactly these; an identity not listed fails until it is recorded here, on purpose, when the identity is new.
CALL_KEYS = {
    # publication fixes (2026-10-11, later): symblic/kernel/process_limits.py now runs the preview from
    # symblic/kernel/preview.py and names the missing file in a command-line error; the file is a JavaScript adapter
    # asset, so the kernel identity is new. The seven prompts without kernel-derived provenance keep their keys.
    '5eca5d64625006e4': {'comprehension_feeds_context': '56cd7b0b17fefde5',
     'ensure_because_feedback': '0e1229b75afa9749',
     'ensure_with_function': '910ce52c11ca9e05',
     'escalate_because_feedback': '53da82493f0b8a28',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': 'dd8c6729837afb6c',
     'loop_of_asks_feeds_context': 'b166d4ccda090a32',
     'many_roots_feed_context': 'fd315ddc7cc9d8b5',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': '18b4221b6df5974b'},
    # the public package layout (2026-10-11): the JavaScript adapter's asset hashes changed with their file paths and
    # documentation, so the kernel identity is new. The seven prompts that embed no kernel-derived provenance give
    # the same keys as the first nine identities listed below (051773a09f26ac1d through 57eb572dd1395767).
    '333a5eeb0af773e8': {'comprehension_feeds_context': 'f8999d9b4855cbd9',
     'ensure_because_feedback': '0e1229b75afa9749',
     'ensure_with_function': '910ce52c11ca9e05',
     'escalate_because_feedback': '53da82493f0b8a28',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': 'c048342eadcdd63b',
     'loop_of_asks_feeds_context': 'ea84117ceb469e52',
     'many_roots_feed_context': 'd2d769ba48bcb003',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': 'b493dfd05fc0d03d'},
    '051773a09f26ac1d': {'comprehension_feeds_context': 'f418f753c5f4a5a8',
                      'ensure_because_feedback': '0e1229b75afa9749',
                      'ensure_with_function': '910ce52c11ca9e05',
                      'escalate_because_feedback': '53da82493f0b8a28',
                      'facts_context': '0a264df5eb21b862',
                      'for_each_facts_context': '442a24a6221320f0',
                      'given_and_context': '19140c0d9dcb5be0',
                      'loop_feeds_context': 'e250955ab2e34f08',
                      'loop_of_asks_feeds_context': 'e60a1cf4aa67636e',
                      'many_roots_feed_context': '7c257c1b5d735509',
                      'plain_asks': 'cc92220124663a2f',
                      'routine_loop_return_feeds_context': '7a89c61ba159a312'},
    'a98acbe306cbc06e': {'comprehension_feeds_context': '91e48af3334e1514',
     'ensure_because_feedback': '0e1229b75afa9749',
     'ensure_with_function': '910ce52c11ca9e05',
     'escalate_because_feedback': '53da82493f0b8a28',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': '2f604b21d5e1331c',
     'loop_of_asks_feeds_context': '82ab7d08411b77d8',
     'many_roots_feed_context': '6c8851a600308b1b',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': '287d57689cbd53b5'},  # 2026-10-07 parser3: exact literal brace/backslash bytes
    'ff1c88f8276e85b1': {'comprehension_feeds_context': '28cde7194a37f10d',
     'ensure_because_feedback': '0e1229b75afa9749',
     'ensure_with_function': '910ce52c11ca9e05',
     'escalate_because_feedback': '53da82493f0b8a28',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': '98718c8cfee515e2',
     'loop_of_asks_feeds_context': 'a5f0fb6619d4cdfe',
     'many_roots_feed_context': 'a523bac68b7092f7',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': '75d9900ec499d222'},  # 2026-10-07 JS adapter9: pinned Acorn declaration preflight
    'c9a59302b28a9414': {'comprehension_feeds_context': '4e195857b265976b',
     'ensure_because_feedback': '0e1229b75afa9749',
     'ensure_with_function': '910ce52c11ca9e05',
     'escalate_because_feedback': '53da82493f0b8a28',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': 'd8f022b69c2457d0',
     'loop_of_asks_feeds_context': 'f2aeedb7c6e804e9',
     'many_roots_feed_context': '1d8bcdcafe08afb5',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': 'ea57ae119dabcdb2'},  # 2026-10-07 JS adapter9: pinned Acorn declaration preflight
    '829113376401e519': {  # 2026-10-07 explicit member profiles and durable team calls, agent_teams1
        'ensure_because_feedback': '0e1229b75afa9749',
        'escalate_because_feedback': '53da82493f0b8a28',
        'plain_asks': 'cc92220124663a2f',
        'given_and_context': '19140c0d9dcb5be0',
        'comprehension_feeds_context': '88f9ad837b4b38c4',
        'loop_feeds_context': '84f725818789842c',
        'loop_of_asks_feeds_context': '82ecac748dba9816',
        'ensure_with_function': '910ce52c11ca9e05',
        'facts_context': '0a264df5eb21b862',
        'for_each_facts_context': '442a24a6221320f0',
        'routine_loop_return_feeds_context': '9249da7ba3e59507',
        'many_roots_feed_context': '801cdff534388442',
    },
    '7bf8c94958d86fc7': {  # 2026-10-06 JS adapter8: required Landlock network-isolation capability
        'comprehension_feeds_context': '8e7b03c07e9d5135',
        'ensure_because_feedback': '0e1229b75afa9749',
        'ensure_with_function': '910ce52c11ca9e05',
        'escalate_because_feedback': '53da82493f0b8a28',
        'facts_context': '0a264df5eb21b862',
        'for_each_facts_context': '442a24a6221320f0',
        'given_and_context': '19140c0d9dcb5be0',
        'loop_feeds_context': 'f136e268d8a36e86',
        'loop_of_asks_feeds_context': '0fba8dfc02fc173a',
        'many_roots_feed_context': '0d1ece873c302300',
        'plain_asks': 'cc92220124663a2f',
        'routine_loop_return_feeds_context': 'b41b2b22676e784f',
    },
    '1e87549328ddcdb6': {'comprehension_feeds_context': '1c2a4b00a2b01b28',
     'ensure_because_feedback': '0e1229b75afa9749',
     'ensure_with_function': '910ce52c11ca9e05',
     'escalate_because_feedback': '53da82493f0b8a28',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': 'c04799a4c76e5e18',
     'loop_of_asks_feeds_context': 'da684c4f3c37f40b',
     'many_roots_feed_context': '823653244baf1c69',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': 'f62a0fbbbe6a7293'},  # bounded optional assessment, ask-policy2
    '2c517c7a2f94395e': {'ensure_because_feedback': '0e1229b75afa9749',
                          'escalate_because_feedback': '53da82493f0b8a28',
                          'plain_asks': 'cc92220124663a2f',
                          'given_and_context': '19140c0d9dcb5be0',
                          'comprehension_feeds_context': '86d11996fa5cce6d',
                          'loop_feeds_context': '2debe2404274a1d1',
                          'loop_of_asks_feeds_context': 'cd55426b17e2754f',
                          'ensure_with_function': '910ce52c11ca9e05',
                          'facts_context': '0a264df5eb21b862',
                          'for_each_facts_context': '442a24a6221320f0',
                          'routine_loop_return_feeds_context': '84a9d918780179ff',
                          'many_roots_feed_context': 'd57fdc7a2ae35237'},
    '57eb572dd1395767': {'comprehension_feeds_context': 'd723ea69f8c26928', 'ensure_because_feedback': '0e1229b75afa9749', 'ensure_with_function': '910ce52c11ca9e05', 'escalate_because_feedback': '53da82493f0b8a28', 'facts_context': '0a264df5eb21b862', 'for_each_facts_context': '442a24a6221320f0', 'given_and_context': '19140c0d9dcb5be0', 'loop_feeds_context': 'e78c7e5ad5e9283f', 'loop_of_asks_feeds_context': '6424eda2bd85a645', 'many_roots_feed_context': '2d55ea8c55857995', 'plain_asks': 'cc92220124663a2f', 'routine_loop_return_feeds_context': '368d485e80d5d8c2'},  # model-first assessment and bounded feedback revisions1
    'a26f3e0bee3c23d4': {'comprehension_feeds_context': 'eabfe617bd440ac7',
     'ensure_with_function': '910ce52c11ca9e05',
     'facts_context': '0a264df5eb21b862',
     'for_each_facts_context': '442a24a6221320f0',
     'given_and_context': '19140c0d9dcb5be0',
     'loop_feeds_context': 'fbb61b8968f7301c',
     'loop_of_asks_feeds_context': 'c19432f9b393d528',
     'many_roots_feed_context': 'dda6c221e1e01975',
     'plain_asks': 'cc92220124663a2f',
     'routine_loop_return_feeds_context': '06e43f21e377b7fd'},  # parser revision1, syntax60/AST128
    'f14447f814751f21': {  # 2026-10-05 combined reform: final C v2, compact5 and epistemic_runtime1
        'comprehension_feeds_context': 'd8c4cd524a1627d0',
        'ensure_with_function': '910ce52c11ca9e05',
        'facts_context': '0a264df5eb21b862',
        'for_each_facts_context': '442a24a6221320f0',
        'given_and_context': '19140c0d9dcb5be0',
        'loop_feeds_context': 'e076e474de3fc662',
        'loop_of_asks_feeds_context': 'a86c4c2cf38c1f2c',
        'many_roots_feed_context': '8479d47a228d7c89',
        'plain_asks': 'cc92220124663a2f',
        'routine_loop_return_feeds_context': 'a3fdfdac153eb039',
    },
    RC2_KERNEL: {                       # computed on the RC2 files themselves (the frozen preimages)
        'plain_asks': 'e03139e614216ae2',
        'given_and_context': '2ce6c813a02fcaf0',
        'comprehension_feeds_context': '77623193c4e0a4b1',
        'loop_feeds_context': '690fcb30576db2c1',
        'loop_of_asks_feeds_context': '6d7c185d4c2ec665',
        'ensure_with_function': '535ba919ac0e9602',
        'facts_context': '379b516a3c6719fc',
        'for_each_facts_context': '9c06ef3dd7e1073d',
        'routine_loop_return_feeds_context': 'ebaca918717cbe86',
        'many_roots_feed_context': '55d3a45c20b68481',
    },
}
# Historical unmerged lane-A keys, retained as a diagnostic for its isolated review snapshot.
# The combined release above has its own epistemic_runtime component and recorded keys;
# this historical snapshot must never be deployed under RC2 identity.
LANE_A_UNMERGED = {
    'plain_asks': 'e03139e614216ae2',
    'given_and_context': '2ce6c813a02fcaf0',
    'comprehension_feeds_context': 'd5132856961d03b0',
    'loop_feeds_context': 'ba2914db8ee9455e',
    'loop_of_asks_feeds_context': '20a5b73937d3c771',
    'ensure_with_function': '8a0a394a955c7b6b',
    'facts_context': '379b516a3c6719fc',
    'for_each_facts_context': '9c06ef3dd7e1073d',
    'routine_loop_return_feeds_context': '0d0169378b614c51',
    'many_roots_feed_context': '56b9549e5c550c91',
}


def prompt_call_keys():
    """{program: digest of the sorted call keys} for PROMPT_PROGRAMS, run in the verified profile with fakes."""
    out = {}
    for label, (source, answers) in PROMPT_PROGRAMS.items():
        run, report, apps = lineage_run(source, *answers, profile='verified', max_asks=200)
        if report['status'] != 'done':
            raise AssertionError(f'{label}: {report.get("error")}')
        keys = sorted(request['key'] for request in apps.requests)
        out[label] = hashlib.sha256(json.dumps(keys).encode()).hexdigest()[:16]
    return out


class PromptIdentity(unittest.TestCase):
    """language-1 review (major): the resume gate trusts kernel_id(), and call keys hash the exact prompt, so a
    change of what prompts say under an unchanged kernel_id() lets a resumed run ask again and repeat effects with
    new arguments. A tripwire: these programs' call keys are recorded per kernel identity."""

    def test_call_keys_change_only_with_the_kernel_identity(self):
        kernel = S.kernel_id()
        if kernel['unicode'] != RECORDED_UNICODE:
            self.skipTest(f'call keys are recorded for Unicode {RECORDED_UNICODE}; this Python has {kernel["unicode"]}')
        if f'+node{RECORDED_NODE}+' not in str(kernel.get('js')):
            self.skipTest(f'call keys are recorded for Node.js {RECORDED_NODE}; the JavaScript adapter here reports '
                          f'{kernel.get("js")!r}')
        current, keys = kernel['id'], prompt_call_keys()
        expected = CALL_KEYS.get(current)
        if expected is None:
            self.fail(f'kernel identity {current} has no recorded call keys. If it is a new identity on purpose, '
                      f'record it in CALL_KEYS: {current!r}: {keys!r}')
        if keys == expected:
            return
        if current == RC2_KERNEL and keys == LANE_A_UNMERGED:
            self.skipTest('lane A changes prompt provenance under RC2\'s kernel identity: it must land with the '
                          'kernel identity change root adds at merge, never as it is')
        changed = sorted(label for label in keys if keys[label] != expected.get(label))
        self.fail(f'prompts changed ({", ".join(changed)}) while kernel_id() stayed {current}: a resumed run would '
                  'ask those calls again. Change the kernel identity (symblic.kernel_id) and record the new keys; '
                  f'only an identity that was never deployed may be re-recorded: {current!r}: {keys!r}')


if __name__ == '__main__':
    unittest.main()

"""Native constructor integration with exact fake helper outcomes and temp stores.

No solver, model, worker machine, host configuration or real project ledger is used.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.constructor import core as C
from symblic.constructor import journal as J
from symblic.kernel import run as R

SOURCE = ('given base: Int = 10.\nask x: Int "Compute one more."\n'
          'ensure x = base + 1 else retry.\nlet doubled = x * 2.\nshow doubled.')
OPTIONS = {'by': 'fake:a', 'profile': 'verified', 'determine': False, 'constructor': 'linear',
           'effort': 'low', 'max_calls': 2}


def fake_runtime():
    """Structurally pinned only: these fake paths are never opened or executed."""
    return {'python': '/not/installed/python', 'python_sha256': 'c' * 64,
            'worker_sha256': C._implementation()['symblic/linear/worker.py'], 'z3_version': '4.15.4',
            'purelib': '/not/installed/site-packages', 'package': {'z3/__init__.py': 'd' * 64}}


class Apps:
    def __init__(self, answer=11):
        self.answer, self.requests = answer, []

    def call(self, req):
        self.requests.append(req)
        return {'ok': True, 'json': {'answer': self.answer}, 'model': 'fake', 'node': 'isolated'}


def helper(candidates=(11,), *, mutate=None):
    def assess(ask, ty, plan, constants, **kw):
        kw['check_stop']()
        tracker = kw['lifecycle']
        tracker.update(version=1, dispatched=True, reaped=True, request_sha256='a' * 64, request_bytes=10,
                       requested_milliseconds=100, requested_resource_limit=kw['resource_limit'],
                       requested_address_space_bytes=kw['address_space_bytes'], raw_sha256='b' * 64,
                       raw_bytes=5, capture_complete=True, stdout_observed_bytes=5,
                       stderr_observed_bytes=0, returncode=0)
        work = kw['resource_limit']
        first = work // 2 or 1
        root = kw['runtime']['purelib']
        limits = {'requested': {'milliseconds': 100, 'rlimit_total': work,
                                'address_space_bytes': kw['address_space_bytes']},
                  'effective_os': {'address_space_bytes': [kw['address_space_bytes']] * 2,
                                   'cpu_seconds': [2, 2], 'file_bytes': [0, 0],
                                   'core_bytes': [0, 0], 'open_files': [64, 64]},
                  'z3_applied': {'threads': 1, 'random_seed': 0,
                                 'allocated_check_rlimits': [first, work - first]},
                  'private_import_root': root, 'loaded_library': root + '/z3/lib/libz3.so'}
        report = {'status': 'sat', 'witnesses': [{'canonical': value} for value in candidates],
                  'solver': {'limits': limits, 'resource_used': 12}}
        if mutate:
            mutate(report, tracker)
        return report
    return assess


class ConstructorRun(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'run'
        runtime = patch.object(C, '_runtime', return_value=fake_runtime())
        self.runtime_reader = runtime.start()
        self.addCleanup(runtime.stop)

    def run_it(self, *, source=SOURCE, options=None, fake=None, apps=None):
        apps = apps or Apps()
        run = R.Run(source, applicators=apps, options={**OPTIONS, **(options or {})}, folder=str(self.folder))
        if fake is None:
            return run, run.execute(), apps
        with patch.object(C.L, 'assess_ask', side_effect=fake) as invoked:
            report = run.execute()
        return run, report, apps, invoked

    def assert_done(self, report):
        self.assertEqual(report['status'], 'done', report.get('error'))

    def test_native_checks_commit_then_replay_exact_origin_without_calls(self):
        run, report, apps, invoked = self.run_it(fake=helper())
        self.assert_done(report)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(apps.requests, [])
        self.assertEqual(report['calls'], 0)
        self.assertEqual(report['agreement_n'], 0)
        self.assertIsNone(report['agreement'])
        claim = run.kernel.env.lookup('x').meta['epistemic']['claim']
        self.assertEqual((claim['version'], claim['origin']), (2, 'solver_proposal'))
        snapshot = C.R.validate_journal(C.R.read_journal(str(self.folder)))
        self.assertEqual(C.R.validate_solver_claim(claim, snapshot), claim)
        downstream = run.kernel.env.lookup('doubled').meta['epistemic']['assessment']
        self.assertEqual(downstream['status'], 'conditional')
        self.assertIn('solver_proposal', [r['origin'] for r in downstream['conditional_on']])
        self.assertEqual(report['determinism_summary']['answered_by_constructor'], 1)
        journal = (self.folder / J.FILE).read_bytes()
        rerun, replay, _, called = self.run_it(options={'replay': True},
                                             fake=lambda *a, **k: self.fail('replay launched helper'))
        self.assert_done(replay)
        self.assertEqual(called.call_count, 0)
        self.assertEqual(replay['fingerprint'], report['fingerprint'])
        self.assertEqual(rerun.kernel.env.lookup('x').meta['epistemic']['claim'], claim)
        self.assertEqual((self.folder / J.FILE).read_bytes(), journal)

    def test_second_invalid_witness_blocks_all_adoption_and_model_fallback(self):
        run, report, apps, _ = self.run_it(fake=helper((11, 12)))
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(run.kernel.env.lookup('x'))
        self.assertEqual(apps.requests, [])
        state = C.R.validate_journal(C.R.read_journal(str(self.folder)))
        outcomes = [entry['outcome']['outcome'] for entry in state.attempts.values()]
        self.assertEqual(outcomes[0]['candidates'], [])
        self.assertNotEqual(outcomes[0]['disposition'], 'accepted')

    def test_diagnostic_candidates_are_not_model_context_or_solver_claims(self):
        run, report, apps, invoked = self.run_it(options={'constructor': 'linear_diagnose'}, fake=helper())
        self.assert_done(report)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(len(apps.requests), 1)
        visible = [{key: req.get(key) for key in ('system', 'prompt', 'schema')} for req in apps.requests]
        self.assertNotIn('solver_proposal', json.dumps(visible))
        self.assertEqual(run.kernel.env.lookup('x').meta['epistemic']['claim']['origin'], 'model_proposal')
        self.assertEqual(J.summary(str(self.folder))['dispositions'], {'diagnosed': 1})

    def test_missing_optional_runtime_records_one_fallback_and_resume_does_not_search(self):
        self.runtime_reader.return_value = None
        run, report, apps = self.run_it()
        self.assert_done(report)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(J.summary(str(self.folder))['dispositions'], {'unavailable': 1})
        rerun, rep, _, called = self.run_it(fake=lambda *a, **k: self.fail('fallback was re-searched'))
        self.assert_done(rep)
        self.assertEqual(called.call_count, 0)

    def test_hostile_policy_refuses_before_folder_creation(self):
        for options in ({'constructor': True}, {'constructor': ' linear'}, {'constructor_python': '/bin/false'},
                        {'determine': True}, {'constructor_limits': {'attempts': True}}):
            with self.subTest(options=options):
                run = R.Run(SOURCE, applicators=Apps(), options={**OPTIONS, **options}, folder=str(self.folder))
                rep = run.execute()
                self.assertEqual(rep['status'], 'failed')
                self.assertFalse(self.folder.exists())

    def test_unconfirmed_launch_keeps_intent_and_blocks_later_work(self):
        original = OSError('unknown fake launch')
        def launch(*args, **kw):
            kw['lifecycle'].update(dispatched=None, reaped=None)
            raise original
        run, report, apps, _ = self.run_it(fake=launch)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(J.summary(str(self.folder))['uncertain']), 1)
        _, rep, apps, called = self.run_it(fake=helper())
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'uncertain')
        self.assertEqual(called.call_count, 0)
        self.assertEqual(apps.requests, [])

    def test_boolean_returncode_cannot_certify_worker_completion(self):
        _, report, apps, _ = self.run_it(fake=helper(mutate=lambda _r, t: t.update(returncode=False)))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(apps.requests, [])

    def test_off_with_existing_constructor_work_refuses_without_changing_it(self):
        _, report, _, _ = self.run_it(fake=helper())
        self.assert_done(report)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.iterdir() if p.is_file()}
        run = R.Run(SOURCE, applicators=Apps(), options={**OPTIONS, 'constructor': 'off'}, folder=str(self.folder))
        self.assertEqual(run.execute()['status'], 'failed')
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.iterdir() if p.is_file()}
        self.assertEqual(after, before)

    def test_original_ask_defaults_are_not_stripped_to_force_constructor(self):
        source = 'use profile=verified.\n' + SOURCE
        _, report, apps, called = self.run_it(source=source, fake=helper())
        self.assert_done(report)
        self.assertEqual(called.call_count, 0)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(J.summary(str(self.folder))['dispositions'], {'unsupported': 1})

    def test_escaped_record_keys_and_rationals_decode_by_native_type(self):
        from fractions import Fraction
        ty = {'k': 'record', 'fields': [('#q', {'k': 'int'}), ('b', {'k': 'number'})]}
        value = {'##q': 3, 'b': {'#q': '1/2'}}
        self.assertEqual(C.decode(value, ty), {'#q': 3, 'b': Fraction(1, 2)})
        self.assertEqual(S.canon(C.decode(value, ty)), value)
        for bad in ({'#q': 3, 'b': {'#q': '1/2'}}, {'##q': True, 'b': {'#q': '1/2'}},
                    {'##q': 3, 'b': {'#q': '2/4'}}):
            with self.subTest(value=bad), self.assertRaises(S.SymblicError):
                C.decode(bad, ty)

    def test_resealed_boolean_validation_mutation_fails_type_sensitive_replay(self):
        _, report, _, _ = self.run_it(fake=helper())
        self.assert_done(report)
        path = self.folder / J.FILE
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]['outcome']['evidence']['native_validation']['passed'] = 1
        previous = J.GENESIS
        for row in rows:
            row['prev'] = previous
            row['sha256'] = J._sha('row', {k: v for k, v in row.items() if k != 'sha256'})
            previous = row['sha256']
        path.write_text(''.join(J.canonical(row) + '\n' for row in rows))
        _, replay, apps, called = self.run_it(options={'replay': True}, fake=helper())
        self.assertEqual(replay['status'], 'failed')
        self.assertEqual(called.call_count, 0)
        self.assertEqual(apps.requests, [])

    def test_resealed_inconsistent_full_worker_receipts_refuse_before_adoption(self):
        _, report, _, _ = self.run_it(fake=helper())
        self.assert_done(report)
        path = self.folder / J.FILE
        original = path.read_text()
        cases = {
            'requested_ms_over_allowance': lambda o: o['evidence']['lifecycle'].update(requested_milliseconds=6000),
            'requested_resource_bool': lambda o: o['evidence']['lifecycle'].update(requested_resource_limit=True),
            'capture_incomplete': lambda o: o['evidence']['lifecycle'].update(capture_complete=False),
            'nonzero_exit': lambda o: o['evidence']['lifecycle'].update(returncode=9),
            'request_sha_bool': lambda o: o['evidence']['lifecycle'].update(request_sha256=False),
            'raw_hash_mismatch': lambda o: o['evidence']['lifecycle'].update(raw_sha256='c' * 64),
            'worker_limit_bool': lambda o: o['effective_limits']['requested'].update(rlimit_total=True),
            'os_limit_drift': lambda o: o['effective_limits']['effective_os'].update(open_files=[65, 65]),
            'worker_import_root_drift': lambda o: o['effective_limits'].update(private_import_root='/other'),
            'solver_threads_drift': lambda o: o['effective_limits']['z3_applied'].update(threads=2),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                rows = [json.loads(line) for line in original.splitlines()]
                mutate(rows[-1]['outcome'])
                previous = J.GENESIS
                for row in rows:
                    row['prev'] = previous
                    row['sha256'] = J._sha('row', {k: v for k, v in row.items() if k != 'sha256'})
                    previous = row['sha256']
                path.write_text(''.join(J.canonical(row) + '\n' for row in rows))
                rerun, replay, apps, called = self.run_it(options={'replay': True}, fake=helper())
                self.assertEqual(replay['status'], 'failed')
                self.assertIsNone(rerun.kernel.env.lookup('x'))
                self.assertEqual(called.call_count, 0)
                self.assertEqual(apps.requests, [])
        path.write_text(original)

    def test_search_retains_its_route_and_reports_constructor_not_attempted(self):
        _, report, apps, called = self.run_it(options={'route': 'search', 'samples': 1, 'rounds': 1},
                                            fake=helper())
        self.assert_done(report)
        self.assertEqual(called.call_count, 0)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(report['determinacy']['asks'][0]['constructor']['reason'], 'unsupported_route')
        self.assertFalse((self.folder / J.FILE).exists())

    def test_source_native_determination_override_is_preserved_and_reported(self):
        source = 'use determine=true.\n' + SOURCE
        _, report, _, called = self.run_it(source=source, fake=helper())
        self.assert_done(report)
        self.assertEqual(called.call_count, 0)
        self.assertEqual(report['determinacy']['asks'][0]['constructor']['reason'],
                         'native_determination_enabled')

    def test_default_off_and_explicit_off_have_identical_model_requests(self):
        requests, summaries = [], []
        for explicit in (False, True):
            options = {key: value for key, value in OPTIONS.items() if key != 'constructor'}
            if explicit:
                options['constructor'] = 'off'
            apps = Apps()
            with patch.object(C, 'Bridge', side_effect=AssertionError('off imported constructor')):
                run = R.Run(SOURCE, applicators=apps, options=options)
                report = run.execute()
            self.assert_done(report)
            summaries.append(report['determinism_summary'])
            requests.append([{key: req.get(key) for key in ('system', 'prompt', 'schema', 'sample',
                                                           'temperature', 'seed', 'key')} for req in apps.requests])
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(summaries[0], summaries[1])
        self.assertNotIn('answered_by_constructor', summaries[0])

    def test_portable_lock_replays_native_constructor_with_exact_provenance(self):
        from symblic.kernel import lockfile as locks
        _, report, _, _ = self.run_it(fake=helper())
        self.assert_done(report)
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': OPTIONS}))
        frozen = locks.make_lock(str(self.folder))
        self.assertEqual(frozen['symblic_lock'], 3)
        with patch.object(C, '_runtime', side_effect=AssertionError('replay read runtime')) as runtime, \
                patch.object(C.L, 'assess_ask', side_effect=AssertionError('replay worker')) as worker:
            replay = locks.replay(frozen)
        self.assertTrue(replay['ok'], replay.get('error'))
        self.assertTrue(replay['constructor_match'])
        self.assertEqual(replay['refused'], [])
        self.assertEqual((runtime.call_count, worker.call_count, replay['calls']), (0, 0, 0))
        self.assertEqual(replay['report']['epistemic'], report['epistemic'])

    def test_real_witness_validation_reads_do_not_become_run_premises(self):
        from symblic.kernel import lockfile as locks

        def validate_real_witness(ask, ty, plan, constants, **kw):
            prepared = C.L.prepare_ask(ask, ty, plan, constants)
            assignment = {prepared.wire['variables'][0]['id']: C.L._rat(11)}
            witness = C.L.validate_witness(prepared, assignment, check_stop=kw['check_stop'])
            report = helper()(ask, ty, plan, constants, **kw)
            report['witnesses'] = [witness]
            return report

        run, report, apps, _ = self.run_it(fake=validate_real_witness)
        self.assert_done(report)
        self.assertEqual(apps.requests, [])
        claims = report['epistemic']['claims']
        self.assertEqual(len(claims), 3)  # actual given, selected proposal, derived output
        self.assertTrue(all(claim['content']['line'] > 0 for claim in claims))
        base = run.kernel.env.lookup('base').meta['epistemic']['claim']
        proposal = run.kernel.env.lookup('x').meta['epistemic']['claim']
        self.assertEqual([ref['id'] for ref in proposal['dependencies']], [base['id']])
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': OPTIONS}))
        locked = locks.make_lock(str(self.folder))
        with patch.object(C.L, 'assess_ask', side_effect=AssertionError('replay worker')):
            replay = locks.replay(locked)
        self.assertTrue(replay['ok'], replay.get('error'))
        self.assertEqual(replay['report']['epistemic'], report['epistemic'])


if __name__ == '__main__':
    unittest.main()

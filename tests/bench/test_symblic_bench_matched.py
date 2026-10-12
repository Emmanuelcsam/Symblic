"""Real runner paths, fake Applicators, synthetic cases and isolated files only."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.bench import bench as B
from symblic.bench import matched as M
from symblic.bench import eval_protocol as E


def manifest(*, cases=None, attempts=1, feedback='none', repetitions=1):
    return {'version': 1, 'cases': cases or [case()],
            'arms': [{'id': 'direct', 'treatment': 'direct'}, {'id': 'typed', 'treatment': 'typed'}],
            'model': {'primary': ['fake:small'], 'fallback': ['fake:large'], 'stronger_fallback': ['fake:large'],
                      'settings': {'temperature': 0, 'seed': 7, 'effort': 'low'}},
            'schedule': [{'model': 'fake:small', 'role': 'primary'}] +
                        [{'model': 'fake:large', 'role': 'fallback'}] * (attempts - 1),
            'feedback': feedback, 'split': 'heldout', 'repetitions': repetitions}


def case(ident='one', *, expected=8, type_text='Int', question='Compute the required quantity.', **changes):
    row = {'id': ident, 'family': 'family-' + ident, 'split': 'heldout',
           'input': {'question': question, 'type': type_text},
           'rubric': {'mode': 'typed_json', 'expected': expected}}
    row.update(changes)
    return row


def arm_of(req):
    return 'direct' if req['system'] == M.DIRECT_SYSTEM else 'typed'


class Apps:
    """Replies in dispatch order, or per treatment (arms=) whatever the frozen arm order."""
    def __init__(self, replies=(), *, arms=None):
        self.replies = list(replies)
        self.arms = {name: list(queue) for name, queue in (arms or {}).items()}
        self.requests = []

    def call(self, req):
        self.requests.append(req)
        queue = self.arms.get(arm_of(req), []) if self.arms else self.replies
        if not queue:
            raise AssertionError('Unexpected extra dispatch')
        value = queue.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def answer(value=8, **other):
    return {'ok': True, 'json': {'answer': value}, **other}


def cell(bench, arm_id, case_id='one', repeat=0):
    assignment = next(a for a in bench.plan['assignments']
                      if (a['arm_id'], a['case_id'], a['repeat']) == (arm_id, case_id, repeat))
    return Path(bench.out, 'matched-cells', assignment['id'])


class MatchedRunner(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='symblic-matched-test-')
        self.addCleanup(self.temp.cleanup)
        self.out = self.temp.name

    def bench(self, spec=None, replies=(), *, arms=None):
        apps = Apps(replies, arms=arms)
        return M.MatchedBench(self.out, spec or manifest(), apps=apps), apps

    def test_actual_direct_and_production_verified_runtime_share_controls(self):
        spec = manifest(cases=[case(expected=910247)])
        spec['cases'][0]['input']['context'] = {'length': 71, 'label': '{literal}'}
        bench, apps = self.bench(spec, [answer(910247), answer(910247)])
        original = M.SR.Run
        profiles = []
        def run_spy(*args, **kwargs):
            profiles.append(kwargs['options']['profile'])
            return original(*args, **kwargs)
        with patch.object(M.SR, 'Run', side_effect=run_spy):
            result = bench.run()
        self.assertEqual(profiles, ['verified'])
        self.assertTrue(result['comparability']['matched'])
        self.assertEqual(result['observed_protocol']['violating_assignments'], 0)
        self.assertEqual([g['correct'] for g in result['groups']], [1, 1])
        for req in apps.requests:
            self.assertNotIn('910247', req['prompt'] + req['system'])
            self.assertNotIn('rubric', req['prompt'])
            self.assertIn('{literal}', req['prompt'])
            self.assertEqual(req['temperature'], 0)
            self.assertEqual(req['seed'], 7)
            self.assertEqual(req['effort'], 'low')
            self.assertEqual(req['tools'], 'none')
        self.assertEqual(apps.requests[0]['schema'], apps.requests[1]['schema'])
        self.assertNotEqual(apps.requests[0]['prompt'], apps.requests[1]['prompt'])
        self.assertEqual(result['spec_labor']['known_minutes_total'], None)
        self.assertEqual(result['groups'][0]['cost']['usd']['observed_attempts'], 0)

    def test_wrong_valid_answer_is_false_acceptance_and_never_oracle_retried(self):
        bench, apps = self.bench(manifest(attempts=3, feedback='contract_only'), [answer(9), answer(9)])
        result = bench.run()
        self.assertEqual(len(apps.requests), 2)
        for g in result['groups']:
            self.assertEqual((g['assigned'], g['correct'], g['false_accept'], g['contract_accept']), (1, 0, 1, 1))
            self.assertEqual(g['fallback_calls'], 0)
            self.assertEqual(g['false_contract_accept'], 1)

    def test_all_failed_attempts_and_stronger_fallback_count_with_contract_only_feedback(self):
        spec = manifest(attempts=3, feedback='contract_only')
        replies = [{'ok': False, 'refused': True, 'error': 'No slot'}, answer('8'), answer(8)] * 2
        bench, apps = self.bench(spec, replies)
        result = bench.run()
        for g in result['groups']:
            self.assertEqual((g['correct'], g['attempts'], g['fresh_calls']), (1, 3, 3))
            self.assertEqual(g['attempt_states']['refused'], 1)
            self.assertEqual(g['attempt_grades']['incorrect'], 1)
            self.assertEqual(g['stronger_fallback_calls'], 2)
            self.assertEqual(g['stronger_fallback_correct'], 1)
            self.assertEqual(g['correct_without_fallback'], 0)
        for i in (0, 1, 3, 4):
            self.assertNotIn('CONTRACT FEEDBACK', apps.requests[i]['prompt'])
        for i in (2, 5):
            self.assertIn(M.FEEDBACK, apps.requests[i]['prompt'])
            self.assertNotIn('expected 8', apps.requests[i]['prompt'])
        self.assertEqual([a['feedback_exposed'] for a in result['outcomes'][0]['attempts']], [False, False, True])

    def test_exact_typed_scoring_rejects_negation_entity_and_last_number_heuristics(self):
        spec = manifest(attempts=2)
        replies = [{'ok': True, 'text': 'The answer is not 8; it is 9.'}, answer('8')] * 2
        bench, _ = self.bench(spec, replies)
        result = bench.run()
        for g in result['groups']:
            self.assertEqual(g['correct'], 0)
            self.assertEqual(g['failed'], 1)
            self.assertEqual(g['attempts'], 2)
            self.assertEqual(g['attempt_grades']['malformed'], 1)
            self.assertEqual(g['attempt_grades']['incorrect'], 1)

    def test_wrong_entity_association_does_not_pass(self):
        spec = manifest(cases=[case(expected={'entity': 'oxygen', 'count': 8},
                                    type_text='Record {entity: Text, count: Int}')])
        bench, _ = self.bench(spec, [answer({'entity': 'nitrogen', 'count': 8})] * 2)
        result = bench.run()
        self.assertEqual([g['false_accept'] for g in result['groups']], [1, 1])

    def test_duplicate_envelope_fields_are_malformed_even_with_parsed_correct_json(self):
        reply = {'ok': True, 'text': '{"answer":9,"answer":8}', 'json': {'answer': 8}}
        bench, _ = self.bench(replies=[reply, reply])
        result = bench.run()
        self.assertEqual([g['failed'] for g in result['groups']], [1, 1])
        self.assertEqual([g['attempt_grades']['malformed'] for g in result['groups']], [1, 1])

    def test_rounding_wrong_answer_into_gold_is_not_allowed(self):
        spec = manifest(cases=[case(expected=8, type_text='Number to 0 places')])
        bench, _ = self.bench(spec, [answer(8.1), answer(8.1)])
        result = bench.run()
        self.assertEqual([g['failed'] for g in result['groups']], [1, 1])
        self.assertEqual([g['correct'] for g in result['groups']], [0, 0])
        self.assertTrue(all(o['attempts'][0]['contract_accept'] is False for o in result['outcomes']))

    def test_exact_text_is_a_declared_protocol(self):
        spec = manifest(cases=[case(expected='Oxygen', type_text='Text',
                                    rubric={'mode': 'exact_text', 'expected': 'Oxygen'})])
        bench, _ = self.bench(spec, arms={'direct': [answer('Oxygen')], 'typed': [answer('not Oxygen')]})
        result = bench.run()
        self.assertEqual([g['correct'] for g in result['groups']], [1, 0])
        self.assertEqual(result['groups'][1]['false_accept'], 1)

    def test_abstention_is_complete_but_not_correct_or_contract_accepted(self):
        bench, apps = self.bench(manifest(attempts=3), [{'ok': True, 'json': {'abstain': True}}] * 2)
        result = bench.run()
        self.assertEqual(len(apps.requests), 2)
        for g in result['groups']:
            self.assertEqual((g['abstain'], g['correct'], g['contract_accept']), (1, 0, 0))
            self.assertEqual(g['rates_per_assigned']['abstain'], 1)

    def test_provider_exception_and_missing_response_count_as_failed_dispatches(self):
        bench, _ = self.bench(replies=[RuntimeError('Synthetic transport failure'), None])
        result = bench.run()
        for g in result['groups']:
            self.assertEqual((g['failed'], g['assigned'], g['attempts'], g['attempt_states']['error']), (1, 1, 1, 1))

    def test_known_cost_only_and_recorded_labor_once(self):
        spec = manifest(repetitions=2)
        spec['spec_labor'] = [{'id': 'stopwatch', 'arm_id': 'typed', 'minutes': 3.5,
                               'method': 'timed', 'scope': 'Writing the synthetic specification'}]
        bench, apps = self.bench(spec, arms={'direct': [answer(usage={'input_tokens': 17, 'usd': 0.02}), answer()],
                                             'typed': [answer(usage={'output_tokens': 4}), answer(usage={'usd': -7})]})
        result = bench.run()
        self.assertEqual(result['assigned'], 4)
        self.assertEqual(result['spec_labor']['known_minutes_total'], 3.5)
        self.assertEqual(result['groups'][0]['cost']['input_tokens'],
                         {'known_total': 17, 'observed_attempts': 1, 'unobserved_attempts': 1})
        self.assertEqual(result['groups'][1]['cost']['usd']['observed_attempts'], 0)
        for name in ('direct', 'typed'):
            self.assertEqual([r['seed'] for r in apps.requests if arm_of(r) == name], [7, 8])

    def test_provider_cached_results_do_not_count_as_fresh_or_rebill_old_usage(self):
        bench, _ = self.bench(replies=[answer(cached=True, usage={'input_tokens': 99, 'usd': 2}), answer()])
        result = bench.run()
        group = result['groups'][0]
        self.assertEqual((group['attempts'], group['cached_attempts'], group['fresh_calls']), (1, 1, 0))
        self.assertEqual(group['cost']['input_tokens']['observed_attempts'], 0)
        self.assertFalse(result['outcomes'][0]['agreement']['measured'])

    def test_receipt_cannot_omit_a_recorded_failed_dispatch(self):
        bench, _ = self.bench(manifest(attempts=2), [answer('8'), answer(), answer('8'), answer()])
        bench.run()
        path = cell(bench, 'direct') / 'receipt.json'
        row = json.loads(path.read_text())
        row['attempts'] = row['attempts'][1:]
        row['selected'], row['agreement_attempts'] = 1, [1]
        path.write_text(json.dumps(row))
        result = bench.report()
        self.assertEqual((result['groups'][0]['damaged'], result['groups'][0]['assigned']), (1, 1))
        self.assertEqual(result['groups'][1]['correct'], 1)

    def test_dry_freeze_preserves_all_assigned_denominators_without_provider(self):
        bench, apps = self.bench(manifest(cases=[case(), case('two')], repetitions=2))
        result = bench.report()
        self.assertEqual(len(apps.requests), 0)
        self.assertEqual(result['assigned'], 8)
        self.assertEqual([g['pending'] for g in result['groups']], [4, 4])
        self.assertEqual([g['rates_per_assigned']['correct'] for g in result['groups']], [0, 0])
        self.assertEqual([g['cost_unresolved_assignments'] for g in result['groups']], [4, 4])

    def test_resume_never_reasks_completed_or_failed_assignments(self):
        bench, apps = self.bench(replies=[answer(), {'ok': False, 'error': 'No answer'}])
        first = bench.run()
        never = Apps([])
        resumed = M.MatchedBench(self.out, apps=never, resume=True)
        second = resumed.run()
        self.assertEqual(never.requests, [])
        self.assertEqual(first['groups'], second['groups'])
        self.assertEqual(len(apps.requests), 2)

    def test_interruption_keeps_unknown_dispatch_and_runs_only_other_pending_assignment(self):
        for first in ('direct', 'typed'):
            with self.subTest(first=first), tempfile.TemporaryDirectory() as out:
                spec = manifest()
                spec['order_seed'] = next(seed for seed in range(64) if M.freeze(
                    {**spec, 'order_seed': seed})['plan']['assignments'][0]['arm_id'] == first)
                other = 'typed' if first == 'direct' else 'direct'
                bench = M.MatchedBench(out, spec, apps=Apps([KeyboardInterrupt('Synthetic interrupt')]))
                with self.assertRaises(KeyboardInterrupt):
                    bench.run()
                unknown = {g['arm_id']: g for g in bench.report()['groups']}
                self.assertEqual(unknown[first]['uncertain'], 1)
                self.assertEqual(unknown[first]['attempt_states']['unknown'], 1)
                self.assertEqual(unknown[other]['pending'], 1)
                next_apps = Apps([answer()])
                resumed = M.MatchedBench(out, apps=next_apps, resume=True).run()
                groups = {g['arm_id']: g for g in resumed['groups']}
                self.assertEqual(len(next_apps.requests), 1)
                self.assertEqual(arm_of(next_apps.requests[0]), other)
                self.assertEqual(groups[first]['uncertain'], 1)
                self.assertEqual(groups[other]['correct'], 1)
                self.assertEqual(groups[first]['assigned'], 1)
                pair = resumed['paired'][0]
                self.assertEqual((pair['resolved_pairs'], pair['unresolved_pairs']), (0, 1))
                self.assertEqual(pair['left_only_correct'] + pair['right_only_correct'], 0)

    def test_changed_manifest_or_implementation_cannot_resume_execution(self):
        bench, _ = self.bench()
        other = manifest()
        other['cases'][0]['rubric']['expected'] = 9
        with self.assertRaises(E.ProtocolError):
            M.MatchedBench(self.out, other, resume=True)
        with patch.object(M, '_implementation', return_value={'changed': True}):
            with self.assertRaises(E.ProtocolError):
                bench.run()
            result = bench.report()
            self.assertFalse(result['runner']['current_implementation_matches'])

    def test_corrupt_receipt_and_event_journal_remain_in_damaged_denominator(self):
        bench, _ = self.bench(replies=[answer(), answer()])
        bench.run()
        cell = Path(self.out, 'matched-cells', bench.plan['assignments'][0]['id'])
        (cell / 'receipt.json').write_text('{ broken')
        other = Path(self.out, 'matched-cells', bench.plan['assignments'][1]['id'])
        (other / 'receipt.json').unlink()
        (other / 'events.jsonl').write_text('{ broken')
        result = bench.report()
        for g in result['groups']:
            self.assertEqual((g['damaged'], g['assigned'], g['correct']), (1, 1, 0))

    def test_evidence_loader_is_read_only_and_labels_historical_implementation_drift(self):
        bench, _ = self.bench(replies=[answer(), answer()])
        bench.run()
        before = {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in Path(self.out).rglob('*') if p.is_file()}
        with patch.object(M, '_write', side_effect=AssertionError('No writes in Evidence reads')), \
                patch.object(Path, 'mkdir', side_effect=AssertionError('No mkdir in Evidence reads')), \
                patch.object(M, '_implementation', return_value={'different': True}):
            result = M.load_summary(self.out)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['summary']['runner']['current_implementation_matches'])
        self.assertEqual([g['correct'] for g in result['summary']['groups']], [1, 1])
        after = {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in Path(self.out).rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_evidence_loader_reports_torn_journal_and_missing_plan_without_creating_files(self):
        bench, _ = self.bench(replies=[KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            bench.run()
        cell = Path(self.out, 'matched-cells', bench.plan['assignments'][0]['id'])
        with (cell / 'events.jsonl').open('a') as handle:
            handle.write('{partial')
        result = M.load_summary(self.out)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['summary']['groups'][0]['damaged'], 1)
        self.assertEqual(len(result['summary']['receipt_integrity']['issues']), 1)
        self.assertIn('damaged', result['summary']['receipt_integrity']['policy'])
        absent = Path(self.out, 'absent-folder')
        failed = M.load_summary(absent)
        self.assertFalse(failed['ok'])
        self.assertFalse(absent.exists())

    def test_oversized_context_fails_before_provider_without_disappearing_assignment(self):
        spec = manifest(cases=[case(question='x' * 5000)])
        spec['max_prompt_characters'] = 1000
        bench, apps = self.bench(spec)
        result = bench.run()
        self.assertEqual(apps.requests, [])
        self.assertEqual([g['harness_failed'] for g in result['groups']], [1, 1])
        self.assertEqual([g['failed'] for g in result['groups']], [0, 0])
        self.assertEqual([g['attempts'] for g in result['groups']], [0, 0])
        self.assertEqual([g['cells']['unresolved']['harness'] for g in result['groups']], [1, 1])
        self.assertEqual(result['paired'][0]['unresolved']['both'], 1)
        for name in ('direct', 'typed'):
            self.assertTrue((cell(bench, name) / 'failure.json').exists())


class FrozenDeclarations(unittest.TestCase):
    def test_family_input_and_gold_feedback_leakage_refuse_before_freezing(self):
        specs = []
        overlap = manifest(cases=[case('dev', family='same', split='dev'), case(family='same')])
        specs.append(overlap)
        input_overlap = manifest(cases=[case('dev', split='dev'), case()])
        specs.append(input_overlap)
        exposure = manifest()
        exposure['exposures'] = [{'purpose': 'repair', 'content': 'answer', 'case_id': 'one'}]
        specs.append(exposure)
        for spec in specs:
            with self.subTest(spec=spec), self.assertRaises(E.ProtocolError):
                M.freeze(spec)

    def test_composite_applicator_cannot_hide_nested_dispatch_budget(self):
        spec = manifest()
        spec['model']['primary'] = ['council:panel']
        spec['schedule'][0]['model'] = 'council:panel'
        with self.assertRaisesRegex(E.ProtocolError, 'single-applicator'):
            M.freeze(spec)

    def test_train_split_data_never_enters_heldout_prompt(self):
        spec = manifest(cases=[case('train', split='train', expected=88, question='private train input'),
                               case(question='heldout input')])
        frozen = M.freeze(spec)
        self.assertEqual(len(frozen['plan']['assignments']), 2)
        self.assertEqual({a['case_id'] for a in frozen['plan']['assignments']}, {'one'})

    def test_undeclared_schedule_and_unsupported_output_types_fail(self):
        for change in ('model', 'role', 'type', 'extra_source', 'gold_contract'):
            spec = manifest()
            if change == 'model':
                spec['schedule'][0]['model'] = 'fake:secret'
            elif change == 'role':
                spec['schedule'][0]['role'] = 'fallback'
            elif change == 'type':
                spec['cases'][0]['input']['type'] = 'Code python'
            elif change == 'extra_source':
                spec['cases'][0]['input']['type'] = 'Int.\nask extra: Int "Oops"'
            else:
                spec['cases'][0]['input']['type'] = 'Bool'
            with self.subTest(change=change), self.assertRaises((E.ProtocolError, M.S.SymblicError)):
                M.freeze(spec)

    def test_cli_freezes_and_reports_without_constructing_applicators(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'spec.json')
            path.write_text(json.dumps(manifest()))
            out = str(Path(tmp, 'results'))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(['--suite', 'matched', '--matched-manifest', str(path),
                                         '--out', out, '--dry-run']), 0)
                self.assertEqual(B.main(['--suite', 'matched', '--out', out, '--report-only']), 0)
            result = json.loads(Path(out, 'matched-summary.json').read_text())
            self.assertEqual(result['assigned'], 2)
            self.assertEqual(result['groups'][0]['attempts'], 0)
            self.assertFalse(Path(out, 'results.jsonl').exists())

    def test_historical_report_labels_existing_semantics_without_mutating_rows(self):
        rows = [{'suite': 'identity', 'item': 'x', 'by': 'fake:a', 'condition': 'prose',
                 'ok': True, 'correct': True, 'value': 'not 8', 'hash': 'a', 'ms': 1}]
        previous = copy.deepcopy(rows)
        text = B.report(rows)
        self.assertIn('Historical suite/scorer semantics', text)
        self.assertIn('not matched', text)
        self.assertEqual(rows, previous)



HOSTILE = ('At 25 °C in café ≤ 3 µm, quote the set \\{a, b\\} and {x} # not a comment\r'
           'next \b "quoted" \\ backslash, trailing  ')


class EvaluationRepairs(unittest.TestCase):
    """Review findings evalclaims-1/2/6/7/8: fake Applicators and temporary folders only."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='symblic-matched-repair-')
        self.addCleanup(self.temp.cleanup)
        self.out = self.temp.name

    def bench(self, spec=None, replies=(), *, arms=None):
        apps = Apps(replies, arms=arms)
        return M.MatchedBench(self.out, spec or manifest(), apps=apps), apps

    # evalclaims-1 -----------------------------------------------------------------
    def test_both_arms_carry_byte_identical_task_text_through_inputs(self):
        spec = manifest(cases=[case(question=HOSTILE)], attempts=2, feedback='contract_only')
        spec['cases'][0]['input']['context'] = {'note': '°C ≤ {y} \\{z\\}', 'control': '\r\x01'}
        public = spec['cases'][0]['input']
        runs = []
        original = M.SR.Run

        def run_spy(source, *args, **kwargs):
            runs.append((source, kwargs['inputs']))
            return original(source, *args, **kwargs)
        bench, apps = self.bench(spec, [{'ok': True, 'json': {'answer': '8'}}, answer()] * 2)
        with patch.object(M.SR, 'Run', side_effect=run_spy):
            result = bench.run()
        self.assertEqual([g['correct'] for g in result['groups']], [1, 1])
        first, repaired = M._task_text(public, False), M._task_text(public, True)
        self.assertIn('°C', first)
        self.assertIn('\r', first)
        self.assertIn('é', first)
        for name in ('direct', 'typed'):
            prompts = [r['prompt'] for r in apps.requests if arm_of(r) == name]
            self.assertEqual(len(prompts), 2)
            self.assertIn(first, prompts[0])
            self.assertIn(repaired, prompts[1])
            self.assertNotIn('\\u00b0', prompts[0])
        typed = [r['prompt'] for r in apps.requests if arm_of(r) == 'typed']
        self.assertIn('ask answer : Int\n  "' + first + '"', typed[0])
        direct = [r['prompt'] for r in apps.requests if arm_of(r) == 'direct']
        self.assertEqual(direct[0], first + '\nOUTPUT TYPE: Int')
        self.assertEqual([source for source, _ in runs], [M._typed_source('Int')] * 2)
        self.assertNotIn('quote the set', runs[0][0])
        self.assertEqual([inputs for _, inputs in runs], [{'task': first}, {'task': repaired}])
        information = [o['attempts'][0]['information_sha256'] for o in result['outcomes']]
        self.assertEqual(information[0], information[1])
        self.assertEqual(result['paired'][0]['information'],
                         {**result['paired'][0]['information'], 'matched': 1, 'mismatched': 0, 'unrecorded': 0})

    def test_freeze_parses_the_type_in_the_actual_typed_source(self):
        for text in ('Int # whole number', 'Int "{task}" with votes=3 #', 'Int "x" #',
                     'Text "{task}" by "fake:x" #', 'Int "{task}" from task #', 'Int.\nask extra: Int "Oops"'):
            with self.subTest(type=text), self.assertRaises(E.ProtocolError):
                M.freeze(manifest(cases=[case(type_text=text)]))
        bench, apps = self.bench(manifest(cases=[case(type_text='((((Int))))')]), [answer(), answer()])
        bench.run()
        self.assertTrue(all('OUTPUT TYPE: Int' in r['prompt'] or 'ask answer : Int\n' in r['prompt']
                            for r in apps.requests))

    def test_runtime_that_alters_the_task_fails_in_the_harness_before_dispatch(self):
        original = M.SR.Run

        def altered(source, *args, **kwargs):
            return original(source, *args, **{**kwargs, 'inputs': {'task': kwargs['inputs']['task'] + ' extra'}})
        bench, apps = self.bench(replies=[answer()])
        with patch.object(M.SR, 'Run', side_effect=altered):
            result = bench.run()
        groups = {g['arm_id']: g for g in result['groups']}
        self.assertEqual([arm_of(r) for r in apps.requests], ['direct'])
        self.assertEqual((groups['typed']['harness_failed'], groups['typed']['attempts']), (1, 0))
        self.assertFalse((cell(bench, 'typed') / 'events.jsonl').exists())
        self.assertIn('exact task text', json.loads((cell(bench, 'typed') / 'failure.json').read_text())['message'])
        self.assertEqual(result['paired'][0]['unresolved_reasons']['right']['harness'], 1)

    def test_verified_runtime_refusing_before_dispatch_is_not_a_model_failure(self):
        refused = {'status': 'failed', 'error': {'message': 'synthetic runtime refusal'}, 'bindings': []}
        bench, apps = self.bench(replies=[answer()])
        with patch.object(M.SR.Run, 'execute', return_value=refused):
            result = bench.run()
        typed = next(o for o in result['outcomes'] if o['arm_id'] == 'typed')
        self.assertEqual((typed['status'], typed['resolution'], typed['attempts']), ('harness_failed', 'harness', []))
        self.assertEqual(result['paired'][0]['left_only_correct'], 0)
        self.assertEqual(result['paired'][0]['unresolved_pairs'], 1)

    # evalclaims-2 -----------------------------------------------------------------
    def test_pending_uncertain_and_infrastructure_cells_are_unresolved_pairs(self):
        spec = manifest(cases=[case('one'), case('two'), case('three')], attempts=2)
        no_slot = {'ok': False, 'refused': True, 'error': 'No slot'}
        bench, _ = self.bench(spec, arms={'direct': [answer()] * 3,
                                          'typed': [{'ok': True, 'text': 'not json'}, answer(9),
                                                    no_slot, {'ok': False, 'error': 'timeout'},
                                                    KeyboardInterrupt('stop')]})
        with self.assertRaises(KeyboardInterrupt):
            bench.run()
        result = bench.report()
        typed = {o['case_id']: o for o in result['outcomes'] if o['arm_id'] == 'typed'}
        self.assertEqual(typed['one']['resolution'], 'resolved')            # a model answered, wrongly
        self.assertEqual(typed['two']['resolution'], 'infrastructure')      # nothing reached a model
        self.assertIn(typed['three']['resolution'], ('uncertain', 'pending'))
        pair = result['paired'][0]
        self.assertEqual(pair['assigned_pairs'], 3)
        self.assertEqual((pair['resolved_pairs'], pair['left_only_correct'], pair['neither_correct']), (1, 1, 0))
        self.assertEqual(pair['unresolved_pairs'], 2)
        group = {g['arm_id']: g for g in result['groups']}['typed']
        self.assertEqual(group['attempt_states']['refused'], 1)
        self.assertEqual(group['attempt_states']['error'], 1)
        self.assertGreaterEqual(group['cost']['latency_ms']['observed_attempts'], 4)

    # evalclaims-6 -----------------------------------------------------------------
    def test_misfiled_or_malformed_receipt_damages_only_its_own_cell(self):
        cases = [case('one'), case('two')]
        for change in ('list', 'unassigned', 'other_cell', 'deep', 'not_object'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as out:
                bench = M.MatchedBench(out, manifest(cases=cases), apps=Apps([answer()] * 4))
                bench.run()
                target, other = cell(bench, 'direct', 'one'), cell(bench, 'direct', 'two')
                row = json.loads((target / 'receipt.json').read_text())
                if change == 'list':
                    row['assignment_id'] = [row['assignment_id']]
                elif change == 'unassigned':
                    row['assignment_id'] = 'f' * 64
                elif change == 'other_cell':
                    row['assignment_id'] = other.name
                text = json.dumps(row)
                if change == 'deep':
                    text = '[' * 100000 + ']' * 100000
                elif change == 'not_object':
                    text = json.dumps([row])
                (target / 'receipt.json').write_text(text)
                loaded = M.load_summary(out)
                self.assertTrue(loaded['ok'], loaded)
                summary = loaded['summary']
                outcomes = {o['assignment_id']: o for o in summary['outcomes']}
                self.assertEqual(outcomes[target.name]['status'], 'damaged')
                self.assertEqual(outcomes[other.name]['status'], 'complete')
                self.assertEqual(summary['groups'][0]['correct'], 1)
                self.assertEqual(summary['cells']['damaged'], 1)
                self.assertEqual([i['assignment_id'] for i in summary['receipt_integrity']['issues']], [target.name])
                self.assertEqual(summary['ignored_records'], [])

    def test_exact_cell_accounting_for_started_pending_and_damaged_cells(self):
        spec = manifest(cases=[case('one'), case('two'), case('three')], repetitions=2)
        bench, _ = self.bench(spec, [answer(), answer(), answer(), answer(), KeyboardInterrupt('stop')])
        with self.assertRaises(KeyboardInterrupt):
            bench.run()
        broken = cell(bench, bench.plan['assignments'][0]['arm_id'], 'one', 0)
        (broken / 'receipt.json').write_text('{ torn')
        summary = bench.report()
        cells = summary['cells']
        self.assertEqual((cells['assigned'], cells['attempted'], cells['pending']), (12, 5, 7))
        self.assertEqual((cells['damaged'], cells['attempted_with_dispatch'], cells['attempted_without_dispatch']),
                         (1, 4, 0))
        self.assertEqual(cells['by_status']['uncertain'], 1)
        self.assertEqual((cells['resolved'], cells['unresolved']['pending'], cells['unresolved']['damaged'],
                          cells['unresolved']['uncertain']), (3, 7, 1, 1))
        for group in summary['groups']:
            per = group['cells']
            self.assertEqual(per['assigned'], per['pending'] + per['attempted'])
            self.assertEqual(per['attempted'], per['damaged'] + per['attempted_with_dispatch'] +
                             per['attempted_without_dispatch'])
            self.assertEqual(per['assigned'], per['resolved'] + sum(per['unresolved'].values()))
        self.assertIn('12 assigned = 7 pending + 5 attempted', M.markdown(summary))

    # evalclaims-7 -----------------------------------------------------------------
    def test_envelope_violations_are_malformed_in_every_rubric_mode(self):
        text_case = case(expected='Oxygen', type_text='Text', rubric={'mode': 'exact_text', 'expected': 'Oxygen'})
        huge = '{"answer": "' + 'x' * (E.MAX_JSON_BYTES + 10) + '"}'
        variants = [
            (text_case, {'ok': True, 'text': '{"answer":"Oxygen","confidence":1}'}),
            (text_case, {'ok': True, 'text': 'Oxygen'}),
            (text_case, {'ok': True, 'json': ['Oxygen']}),
            (case(), {'ok': True, 'text': '{"answer":8,"confidence":1}'}),
            (case(), {'ok': True, 'text': '{"answer": 8'}),
            (case(), {'ok': True, 'json': {'answer': 8, 'reasoning': 7}}),
            (case(), {'ok': True, 'text': huge}),
            (case(), {'ok': True, 'text': '{"answer": 8} \ud800'}),
        ]
        for row, reply in variants:
            with self.subTest(reply=str(reply)[:60]), tempfile.TemporaryDirectory() as out:
                spec = manifest(cases=[row])
                spec['arms'] = spec['arms'][:1]
                summary = M.MatchedBench(out, spec, apps=Apps([reply])).run()
                group = summary['groups'][0]
                self.assertEqual(group['attempt_grades'], {'correct': 0, 'incorrect': 0, 'ungradable': 0, 'malformed': 1})
                self.assertEqual((group['failed'], group['cells']['resolved']), (1, 1))
                attempt = summary['outcomes'][0]['attempts'][0]
                self.assertEqual(attempt['contract_accept'], False)
                self.assertLessEqual(len(json.loads((Path(out, 'matched-cells', summary['outcomes'][0]['assignment_id'],
                                                         'receipt.json')).read_text())['attempts'][0]['answer']), M.SNIPPET)
        wrong_type = manifest(cases=[case()])
        wrong_type['arms'] = wrong_type['arms'][:1]
        with tempfile.TemporaryDirectory() as out:
            group = M.MatchedBench(out, wrong_type, apps=Apps([answer('8')])).run()['groups'][0]
            self.assertEqual(group['attempt_grades']['incorrect'], 1)   # well-formed envelope, wrong value

    # evalclaims-8 -----------------------------------------------------------------
    def test_arm_order_is_frozen_counterbalanced_reproducible_and_timestamped(self):
        spec = manifest(cases=[case('one'), case('two')], repetitions=2)
        frozen = M.freeze(spec)
        self.assertEqual(frozen['plan']['order'], {'design': 'balanced_latin_square', 'seed': 0, 'unit': 'case_repeat'})
        self.assertEqual(M.freeze(copy.deepcopy(spec))['plan'], frozen['plan'])
        firsts = [a['arm_id'] for a in frozen['plan']['assignments'] if a['position'] == 0]
        self.assertEqual(sorted(firsts), ['direct', 'direct', 'typed', 'typed'])
        orders = {tuple(a['arm_id'] for a in M.freeze({**spec, 'order_seed': seed})['plan']['assignments'][:2])
                  for seed in range(16)}
        self.assertEqual(orders, {('direct', 'typed'), ('typed', 'direct')})
        bench, apps = self.bench(spec, [answer()] * 8)
        result = bench.run()
        planned = [self_arm['arm_id'] for self_arm in bench.plan['assignments']]
        self.assertEqual([arm_of(r) for r in apps.requests], planned)
        self.assertEqual(result['order']['positions'], {'direct': [2, 2], 'typed': [2, 2]})
        stamps = [a['dispatched_at_ms'] for o in sorted(result['outcomes'], key=lambda o: o['attempts'][0]['dispatched_at_ms'])
                  for a in o['attempts']]
        self.assertEqual(stamps, sorted(stamps))
        self.assertIn('counterbalanced', M.markdown(result))
        for bad in (-1, 2**31, True, '1'):
            with self.subTest(order_seed=bad), self.assertRaises(E.ProtocolError):
                M.freeze({**spec, 'order_seed': bad})

    # versioning -------------------------------------------------------------------
    def test_version_1_experiment_still_reports_but_never_runs(self):
        spec = manifest()
        current = M.freeze(spec)
        arms = current['plan']['arms']
        exposures = current['plan']['exposures']
        plan = E._plan(spec['cases'], arms, 'heldout', 1, exposures, 1)
        body = {'version': 1, 'manifest': spec, 'plan': plan, 'implementation': {'kernel': 'historical', 'files': {}}}
        frozen = {'id': E.digest(body), **body}
        Path(self.out, 'matched-cells').mkdir()
        Path(self.out, 'matched-plan.json').write_text(json.dumps(frozen))
        for assignment in plan['assignments']:
            folder = Path(self.out, 'matched-cells', assignment['id'])
            folder.mkdir()
            (folder / 'started.json').write_text(json.dumps({'assignment': assignment, 'experiment_id': frozen['id']}))
            attempt = {'model': 'fake:small', 'role': 'primary', 'feedback_exposed': False, 'request_sha256': 'a' * 64,
                       'status': 'answered', 'answer': 8, 'encoding': 'json_value', 'contract_accept': True,
                       'usage': {'latency_ms': 1}}
            with (folder / 'events.jsonl').open('w') as handle:
                intent = {k: attempt[k] for k in ('model', 'role', 'feedback_exposed', 'request_sha256')}
                handle.write(json.dumps({'kind': 'dispatch_intent', 'ordinal': 1, **intent}) + '\n')
                handle.write(json.dumps({'kind': 'dispatch_result', 'ordinal': 1, 'attempt': attempt}) + '\n')
            receipt = {'version': 1, 'plan_id': plan['id'], 'assignment_id': assignment['id'],
                       'assignment_sha256': E.digest(assignment), 'status': 'complete', 'selected': 1,
                       'attempts': [attempt], 'agreement_attempts': [1]}
            (folder / 'receipt.json').write_text(json.dumps(receipt))
        loaded = M.load_summary(self.out)
        self.assertTrue(loaded['ok'], loaded)
        summary = loaded['summary']
        self.assertEqual((summary['runner']['version'], summary['plan_version']), (1, 1))
        self.assertFalse(summary['order']['counterbalanced'])
        self.assertEqual([g['correct'] for g in summary['groups']], [1, 1])
        self.assertTrue(any('matched protocol 1' in limit for limit in summary['limits']))
        with self.assertRaises(E.ProtocolError):
            M.MatchedBench(self.out, apps=Apps([]), resume=True).run()
        mixed = {**body, 'version': 2}
        Path(self.out, 'matched-plan.json').write_text(json.dumps({'id': E.digest(mixed), **mixed}))
        self.assertFalse(M.load_summary(self.out)['ok'])


if __name__ == '__main__':
    unittest.main()

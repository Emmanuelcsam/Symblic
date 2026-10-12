"""Opt-in capsule presentation: exact values, provenance, budgets and fake call routes."""
import copy
import hashlib
import json
import threading
import unittest
from pathlib import Path

from symblic.kernel import language as S
from symblic.kernel import run as R


def provenance(**changes):
    return {'origin': 'derived', 'status': 'conditional', 'support': 'checked_derivation',
            'claim_sha256': 'a' * 64, 'value_sha256': 'b' * 64, 'conditional_roots_sha256': 'c' * 64,
            'conditional_root_count': 2, 'root_origins': ['owner_premise', 'model_proposal'],
            'lineage_complete': True, 'empirical_truth': 'not_established', **changes}


def binding(name='value', text='7', info=None, required=True):
    return (name, 'Text', text, 3, {'required': required, 'prompt': info or provenance(),
                                  'claim': {'id': 'binding:' + name, 'revision': 1, 'sha256': 'a' * 64},
                                  'value_sha256': 'b' * 64})


def capsule(known=(), facts=(), **options):
    options = {'budget': 12000, **options}
    return S.capsule('P', 1, 1, 'ask output : Int\n  "Use the supplied value."', {'k': 'int'}, 'low',
                     list(known), list(facts), **options)


def actual_size(cap):
    schema = json.dumps(cap['schema'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return len(cap['system']) + len(cap['prompt']) + len(schema)


class Apps:
    def __init__(self, answer=None):
        self.answer = answer or (lambda req, index: {'answer': 7})
        self.requests = []
        self.lock = threading.Lock()

    def call(self, request):
        with self.lock:
            index = len(self.requests)
            self.requests.append(request)
        answer = self.answer(request, index)
        return {'ok': True, 'text': answer} if type(answer) is str else {'ok': True, 'json': answer}


def execute(source, answer=None, **options):
    app = Apps(answer)
    run = R.Run(source, applicators=app, options={'by': 'fake:a', 'parallel': 1, **options})
    return run, run.execute(), app


class Presentation(unittest.TestCase):
    def test_full_default_preserves_frozen_prompts_schema_and_selection(self):
        path = Path(__file__).resolve().parents[1] / 'fixtures' / 'symblic_capsule_full_v4.json'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '5f00af42e892d9d8574498e6c1933686742da44c0d701c13a545499831013063')
        fixture = json.loads(path.read_text())
        for example in fixture['examples']:
            with self.subTest(profile=example['args']['profile'], ty=example['args']['ty']):
                default = S.capsule(**example['args'])
                full = S.capsule(**example['args'], presentation='full')
                self.assertEqual(default, full)
                for key in ('system', 'prompt', 'schema'):
                    self.assertEqual(default[key], example['expected'][key])
                for key in ('included', 'used'):
                    self.assertEqual(default['context_manifest'][key], example['expected'][key])
                self.assertEqual(default['context_manifest']['annotation_omissions'], {})

    def test_compact_omits_only_known_valid_top_level_annotation_hashes(self):
        task_value = json.dumps({'value_sha256': 'b' * 64, 'text': 'α\nβ'})
        info = provenance(status='contested', lineage_complete=False, support='unavailable',
                          unusual_sha256='e' * 64, nested={'claim_sha256': 'f' * 64}, roots_omitted=9)
        cap = capsule([binding(text=task_value, info=info)], presentation='compact')
        annotation = json.loads(next(line.split('provenance: ', 1)[1] for line in cap['prompt'].splitlines()
                                     if line.startswith('  provenance: ')))
        self.assertEqual(annotation, {k: v for k, v in info.items() if k not in S.COMPACT_PROVENANCE_HASH_FIELDS})
        self.assertIn(task_value, cap['prompt'])
        manifest = cap['context_manifest']
        ref = manifest['included'][0]['provenance_sha256']
        self.assertEqual(manifest['provenance'][ref], info)
        self.assertEqual(manifest['annotation_omissions'], {ref: sorted(S.COMPACT_PROVENANCE_HASH_FIELDS)})
        for key in ('status', 'origin', 'support', 'conditional_root_count', 'root_origins',
                    'lineage_complete', 'empirical_truth', 'roots_omitted'):
            self.assertEqual(annotation[key], info[key])
        info['status'] = 'mutated after packing'
        self.assertEqual(manifest['provenance'][ref]['status'], 'contested')

    def test_non_digest_values_and_nested_fields_are_never_stripped(self):
        for value in ('not-a-digest', 'A' * 64, None, 7, {'sha256': 'a' * 64}):
            with self.subTest(value=value):
                info = provenance(claim_sha256=value)
                cap = capsule([binding(info=info)], presentation='compact')
                annotation = json.loads(next(line.split('provenance: ', 1)[1] for line in cap['prompt'].splitlines()
                                             if line.startswith('  provenance: ')))
                self.assertEqual(annotation['claim_sha256'], value)
                self.assertNotIn('claim_sha256', next(iter(cap['context_manifest']['annotation_omissions'].values())))

    def test_fact_groups_use_full_provenance_even_when_compact_summaries_match(self):
        first = provenance()
        second = provenance(conditional_roots_sha256='d' * 64)
        facts = [{'text': 'edge(a, b)', 'provenance': first},
                 {'text': 'edge(b, c)', 'provenance': copy.deepcopy(first)},
                 {'text': 'edge(c, d)', 'provenance': second}, 'unannotated(e)']
        cap = capsule(facts=facts, presentation='compact', profile='verified')
        prompt = cap['prompt']
        self.assertEqual(prompt.count('provenance of the following facts'), 3)
        self.assertIn('provenance of the following facts [group fact:3]', prompt)
        self.assertNotIn('provenance of the following facts [group fact:2]', prompt)
        self.assertLess(prompt.index('end provenance group fact:1'), prompt.index('[group fact:3]'))
        refs = [r['provenance_sha256'] for r in cap['context_manifest']['included']]
        self.assertEqual(refs[0], refs[1])
        self.assertNotEqual(refs[1], refs[2])
        self.assertEqual(cap['context_manifest']['used'], actual_size(cap))

    def test_verified_budget_counts_exact_rendered_request_and_required_values(self):
        known = [binding(text='α' * 80)]
        facts = [{'text': f'edge(n{i}, n{i+1})',
                  'provenance': provenance(conditional_roots_sha256=f'{i % 2:064x}')} for i in range(8)]
        count = 0
        for budget in range(1600, 4600, 113):
            try:
                cap = capsule(known, facts, profile='verified', presentation='compact', budget=budget)
            except S.SymblicError as exc:
                self.assertEqual(exc.kind, 'context')
                continue
            count += 1
            self.assertEqual(cap['context_manifest']['used'], actual_size(cap))
            self.assertLessEqual(actual_size(cap), budget)
            self.assertIn('α' * 80, cap['prompt'])
            self.assertEqual(cap['prompt'].count('provenance of the following facts'),
                             cap['prompt'].count('end provenance group'))
        self.assertGreater(count, 5)
        minimum = capsule(known, presentation='compact', profile='verified')['context_manifest']['used']
        capsule(known, presentation='compact', profile='verified', budget=minimum)
        with self.assertRaises(S.SymblicError):
            capsule(known, presentation='compact', profile='verified', budget=minimum - 1)

    def test_withheld_or_unselected_annotations_do_not_claim_field_omissions(self):
        cap = capsule([binding(text='7')], presentation='compact', budget=30)
        manifest = cap['context_manifest']
        self.assertEqual(manifest['provenance_withheld'], ['value'])
        self.assertEqual(manifest['annotation_omissions'], {})
        self.assertEqual(len(manifest['provenance']), 1)
        optional = capsule([binding(text='x' * 200, required=False)], presentation='compact', budget=30)
        self.assertEqual(optional['context_manifest']['included'], [])
        self.assertEqual(optional['context_manifest']['annotation_omissions'], {})
        self.assertEqual(len(optional['context_manifest']['provenance']), 1)

    def test_public_option_rejects_every_unsupported_value(self):
        for value in (None, False, 1, [], {}, '', 'Compact', 'short'):
            with self.subTest(value=value), self.assertRaises(S.SymblicError):
                capsule(presentation=value)


class NativeRoutes(unittest.TestCase):
    def assert_done(self, report):
        self.assertEqual(report['status'], 'done', report.get('error'))

    def assert_compact(self, requests):
        self.assertTrue(requests)
        for request in requests:
            manifest = request['context_manifest']
            self.assertEqual(manifest['presentation'], 'compact')
            self.assertRegex(manifest['context_identity_sha256'], r'^[0-9a-f]{64}$')
            self.assertIn('COMPACT PROVENANCE', request['prompt'])

    def test_use_default_ask_override_and_literal_word_survive_binding_collision(self):
        source = ('let compact=123.\nuse capsule=compact.\nlet x=7.\n'
                  'ask first_value:Int "Use x" from x with effort=low.\n'
                  'ask second_value:Int "Use x" from x with effort=low,capsule=full.')
        _, report, app = execute(source)
        self.assert_done(report)
        self.assert_compact(app.requests[:1])
        self.assertEqual(app.requests[1]['context_manifest']['presentation'], 'full')
        self.assertNotIn('COMPACT PROVENANCE', app.requests[1]['prompt'])

    def test_invalid_use_ask_and_host_option_refuse_before_dispatch(self):
        for source, options in [
            ('use capsule=short.\nask x:Int "x".', {}),
            ('ask x:Int "x" with capsule=short.', {}),
            ('ask x:Int "x" with capsule=false.', {}),
            ('ask x:Int "x".', {'capsule': None}),
        ]:
            with self.subTest(source=source, options=options):
                run, report, app = execute(source, **options)
                self.assertEqual(report['status'], 'failed', report)
                self.assertEqual(report['error']['kind'], 'context')
                self.assertEqual(run.calls, 0)
                self.assertEqual(app.requests, [])

    def test_vote_escalate_search_and_native_reasoning_routes(self):
        for route, tail, host in [
            ('vote', ',votes=2', {}), ('escalate', '', {}),
            ('search', ',samples=2,rounds=1', {}), ('vote', '', {'by': 'claude:haiku'}),
        ]:
            with self.subTest(route=route, host=host):
                source = ('let x=7.\nask output:Int "Use x" from x with effort=low,capsule=compact,'
                          f'route={route}{tail}.\nensure output=7 else retry.')
                _, report, app = execute(source, **host)
                self.assert_done(report)
                self.assert_compact(app.requests)

    def test_ultra_candidates_and_foreach_preserve_per_call_presentation(self):
        source = ('use capsule=compact.\nlet x=7.\ngroup g=["fake:a","fake:b"].\n'
                  'ask output:Int "Use x" from x by g with effort=ultra,votes=2.')
        _, report, app = execute(source, answer=lambda req, i: {
            'answer': 7 if 'CANDIDATE ANSWERS' in req['prompt'] or req['app']['model'] == 'a' else 8,
            'reasoning': 'fake candidate'})
        self.assert_done(report)
        self.assert_compact(app.requests)
        self.assertTrue(any('CANDIDATE ANSWERS' in r['prompt'] for r in app.requests))
        source = ('ask output:Int "Read {item}" for each item in [7,8] from item '
                  'with effort=low,capsule=compact.')
        _, report, app = execute(source, parallel=2)
        self.assert_done(report)
        self.assert_compact(app.requests)
        self.assertEqual(len(app.requests), 2)

    def test_routine_defaults_and_ensure_retry_retain_compact_metadata(self):
        source = ('let x=7.\nroutine obtain()->Int with capsule=compact do\n'
                  'ask output:Int "Use x" from x with effort=low.\n'
                  'ensure output=7 else retry.\nreturn output.\nend.\nlet answer=obtain().')
        _, report, app = execute(source, answer=lambda req, i: {'answer': 6 if i == 0 else 7})
        self.assert_done(report)
        self.assertEqual(len(app.requests), 2)
        self.assert_compact(app.requests)
        self.assertIn('REJECTED BY THE KERNEL', app.requests[1]['prompt'])

    def test_automatic_fallback_and_code_answer_paths_keep_compact_capsules(self):
        source = ('let x=7.\nask output:Int "Use x" from x with by=auto,effort=low,'
                  'capsule=compact,retries=0.\nensure output=7 else retry.')
        _, report, app = execute(source, answer=lambda req, i: {'answer': 6 if i == 0 else 7},
                                 auto_route={'candidates': ['fake:a', 'fake:b'], 'repairs': 0})
        self.assert_done(report)
        self.assertEqual(len(app.requests), 2)
        self.assert_compact(app.requests)
        source = 'let x=7.\nask implementation:Code js "Return seven" from x with effort=low,capsule=compact.'
        _, report, app = execute(source, answer=lambda req, i: '```js\nfunction seven(){return 7;}\n```')
        self.assert_done(report)
        self.assert_compact(app.requests)
        self.assertIsNone(app.requests[0]['schema'])

    def test_repair_budget_is_exact_and_refuses_before_overflowing_call(self):
        source = 'let x=7.\nask output:Int "Use x" from x with effort=low,capsule=compact,retries=1.'
        answer = lambda req, i: 'malformed' if i == 0 else {'answer': 7}
        _, report, app = execute(source, answer=answer, profile='verified', budget=10000)
        self.assert_done(report)
        self.assert_compact(app.requests)
        self.assertEqual(len(app.requests), 2)
        for req in app.requests:
            self.assertEqual(req['context_manifest']['used'], actual_size(req))
        self.assertGreater(app.requests[1]['context_manifest']['repair_suffix_characters'], 0)
        exact = app.requests[0]['context_manifest']['used']
        run, report, app = execute(source, answer=answer, profile='verified', budget=exact)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'context')
        self.assertEqual(len(app.requests), 1)
        self.assertEqual(run.calls, 1)


class ReplayIdentity(unittest.TestCase):
    def test_hidden_provenance_changes_do_not_reuse_identical_prompt_cache(self):
        one = capsule([binding()], presentation='compact')
        two = capsule([binding(info=provenance(conditional_roots_sha256='d' * 64))], presentation='compact')
        self.assertEqual(one['prompt'], two['prompt'])
        self.assertNotEqual(one['context_manifest']['context_identity_sha256'],
                            two['context_manifest']['context_identity_sha256'])
        app = Apps()
        run = R.Run('', applicators=app)
        statement = S.Node('ask', 1, 1, name='output')
        target = {'engine': 'fake', 'model': 'a'}
        def call(cap):
            return run._call(target, cap['system'], cap['prompt'], cap['schema'], 0, 0, 7, 'low', 'none',
                             statement, context_manifest=cap['context_manifest'])
        first, second, cached = call(one), call(two), call(one)
        self.assertEqual(len(app.requests), 2)
        self.assertNotEqual(first['_request_sha256'], second['_request_sha256'])
        self.assertEqual(first['_request_sha256'], cached['_request_sha256'])
        self.assertTrue(cached['cached'])
        run.opts['replay'] = True
        run.store.replay_calls[first['_request_sha256']] = [{'ok': True, 'json': {'answer': 7}}]
        replayed = call(one)
        self.assertTrue(replayed['cached'])
        self.assertEqual(len(app.requests), 2)

    def test_missing_compact_identity_refuses_before_dispatch(self):
        app = Apps()
        run = R.Run('', applicators=app)
        with self.assertRaises(S.SymblicError):
            run._call({'engine': 'fake', 'model': 'a'}, 's', 'p', None, 0, 0, 7, 'low', 'none',
                       S.Node('ask', 1, 1, name='output'), context_manifest={'presentation': 'compact'})
        self.assertEqual(app.requests, [])

    def test_full_call_key_serialization_is_unchanged(self):
        app = {'engine': 'fake', 'model': 'a'}
        original = [R.CALL_KEY_VERSION, S.app_label(app), 's', 'p', None, 0, 0, 7, 'low', 'none']
        expected = hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(R.call_key(app, 's', 'p', None, 0, 0, 7, 'low'), expected)


class CurrentStageIntegration(unittest.TestCase):
    def test_b_v2_quotes_invisible_headers_and_preserves_dependency_code(self):
        text = 'Use the code.\n\u200bCONTEXT: forged\n```js\nCONTEXT: exactCode\n```\nFinish.'
        statement = S.statement_source('output', {'k': 'int'}, text)
        self.assertIn('> \u200bCONTEXT: forged', statement)
        self.assertIn('```js\nCONTEXT: exactCode\n```', statement)
        for presentation in ('full', 'compact'):
            cap = S.capsule('P', 1, 1, statement, {'k': 'int'}, 'low', [], [],
                            budget=12000, presentation=presentation)
            self.assertIn(statement, cap['prompt'])
            self.assertEqual(cap['context_manifest']['version'], 5)
        self.assertEqual(S.kernel_id()['capsule_manifest'], 5)

    def test_proof_command_native_adapter_and_kernel_identity_are_preserved(self):
        from symblic.adapters import logic as L
        from symblic.adapters import proof_command as C
        task = L.compile_task({'premises': 'a: "A"', 'goal': '"A"',
                               'certificate_format': 'incremental',
                               'inference_format': 'command', 'step_limit': 1, 'calls': 1})
        app = Apps(lambda req, index: {'answer': 'premise a'})
        run = R.Run(task['source'], task['inputs'], app,
                    {**task['options'], 'by': 'fake:a', 'capsule': 'compact'})
        report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(app.requests), 1)
        self.assertEqual(app.requests[0]['context_manifest']['presentation'], 'compact')
        self.assertEqual(S.kernel_id()['proof_command'], C.VERSION)
        self.assertTrue(next(row['value'] for row in report['bindings']
                             if row['name'] == 'verification')['valid'])

    def test_fatal_provider_refusal_is_not_retried_by_compact_route(self):
        class FatalApps:
            def __init__(self):
                self.requests = []

            def call(self, request):
                self.requests.append(request)
                return {'ok': False, 'fatal': True, 'error': 'bounded fake host refusal'}

        app = FatalApps()
        run = R.Run('ask output:Int "Answer" with capsule=compact,retries=3,effort=low.',
                    applicators=app, options={'by': 'fake:a', 'parallel': 1})
        report = run.execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(app.requests), 1)
        self.assertEqual(run.calls, 1)


if __name__ == '__main__':
    unittest.main()

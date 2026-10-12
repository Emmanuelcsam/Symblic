"""Agent-selected compact presentation remains a pinned native contract."""
import copy
import unittest

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.delegate import run as DR
from symblic.kernel.run import Run
from tests.delegate.test_symblic_delegate import ARITHMETIC, TRANSFORM, Fake, execute


class DelegatedPresentation(unittest.TestCase):
    def test_default_and_explicit_full_are_identical_and_bad_choices_refuse(self):
        task = D.compile_task(TRANSFORM)
        self.assertEqual(task, D.compile_task({**TRANSFORM, 'capsule': 'full'}))
        for value in (None, False, 1, {}, [], 'Compact', 'compact. act unwanted'):
            with self.subTest(value=value):
                refused = D.inspect_task({**TRANSFORM, 'capsule': value})
                self.assertFalse(refused['ok'])
                self.assertEqual(refused['errors'][0]['code'], 'capsule')
                self.assertNotIn('source', refused)
        for schema in D.catalog()['request_schema']['oneOf']:
            self.assertEqual(schema['properties']['capsule']['enum'], ['full', 'compact'])

    def test_compact_preserves_inputs_acceptance_and_repairs(self):
        full = D.compile_task(TRANSFORM)
        compact = D.compile_task({**TRANSFORM, 'capsule': 'compact'})
        for key in ('inputs', 'output_schema', 'assurance', 'output_binding'):
            self.assertEqual(compact[key], full[key])
        self.assertNotEqual(compact['contract_id'], full['contract_id'])
        self.assertEqual(compact['source'].replace('use capsule=compact.\n', ''), full['source'])
        run, report, apps = execute(compact, [[3, 5], [1, 2]])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(S.canon(run.kernel.env.lookup('answer').value), [1, 2])
        self.assertEqual(len(apps.requests), 2)
        for request in apps.requests:
            manifest = request['context_manifest']
            self.assertEqual(manifest['presentation'], 'compact')
            self.assertEqual(len(manifest['context_identity_sha256']), 64)
            self.assertTrue(manifest['annotation_omissions'])
            self.assertTrue(manifest['provenance'])
            self.assertFalse(manifest['omitted'])

    def test_exported_source_retains_presentation_without_wrapper_options(self):
        task = D.compile_task({**TRANSFORM, 'capsule': 'compact'})
        apps = Fake([[1, 2]])
        native = Run(task['source'], task['inputs'], apps,
                     {'by': 'fake:child', 'max_calls': 1, 'side_effects': False}, folder=None)
        self.assertEqual(native.execute()['status'], 'done')
        self.assertEqual(apps.requests[0]['context_manifest']['presentation'], 'compact')

    def test_route_and_replay_declaration_refuse_presentation_drift(self):
        request = {**TRANSFORM, 'capsule': 'compact'}
        task = DR.prepare(request, by='fake:child')
        declaration = {key: task[key] for key in
                       ('contract_id', 'template_id', 'output_binding', 'assurance', 'routing', 'routing_id')}
        declaration['request'] = request
        checked = DR.verify_declaration(declaration, task['source'], task['inputs'], task['options'])
        self.assertEqual(checked['contract_id'], task['contract_id'])
        for change in ('option', 'request', 'source'):
            d, options, source = copy.deepcopy(declaration), dict(task['options']), task['source']
            if change == 'option':
                options['capsule'] = 'full'
            elif change == 'request':
                d['request']['capsule'] = 'full'
            else:
                source = source.replace('use capsule=compact.\n', '')
            with self.subTest(change=change), self.assertRaises(D.ContractError):
                DR.verify_declaration(d, source, task['inputs'], options)

    def test_arithmetic_remains_zero_call_and_input_contract_is_stable(self):
        task = D.compile_task({**ARITHMETIC, 'capsule': 'compact'})
        _, report, apps = execute(task)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(apps.requests, [])
        refused = D.inspect_task({**TRANSFORM, 'capsule': 'compact',
                                 'expected_contract_id': D.compile_task(TRANSFORM)['contract_id']})
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['errors'][0]['code'], 'contract_mismatch')

"""Owner API dispatch with isolated stores, fake launcher/models, local JS sandbox."""
import json
from pathlib import Path
from unittest.mock import patch

import unittest
try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_engine import Base
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.js import check as JS
from tests.spec.test_symblic_spec_build import SHEET, Replies


class TaskCardAPI(Base):
    def test_check_and_run_use_strict_plan_and_explicit_options(self):
        response = self.call('POST', 'spec/check', {'sheet': SHEET, 'mode': 'task-cards'})
        self.assertTrue(response.sent['ok'])
        self.assertEqual(len(response.sent['plan']['layers']), 2)
        invalid = self.call('POST', 'spec/check', {'sheet': SHEET.replace('Uses: `first`', 'Uses: `missing`'),
                                                  'mode': 'task-cards'})
        self.assertFalse(invalid.sent['ok'])
        with patch.object(E, 'start_run', lambda body: {'id': 'r1', 'body': body}):
            response = self.call('POST', 'spec/run', {'sheet': SHEET, 'mode': 'task-cards', 'by': ['fake:a'],
                                                      'samples': 1, 'rounds': 1, 'retries': 1, 'budget': 6000})
        self.assertEqual(response.status, 200, response.sent)
        self.assertEqual(response.sent['body']['options']['profile'], 'verified')
        self.assertIn('budget=6000', response.sent['body']['source'])
        self.assertEqual(response.sent['kept'], 0)
        for data in ({'mode': 'missing'}, {'mode': 'task-cards', 'budget': 0},
                     {'mode': 'task-cards', 'manifest': {}, 'keep': 'abcdef012345'}):
            self.assertEqual(self.call('POST', 'spec/run', {'sheet': SHEET, **data}).status, 400)

    def test_api_export_verify_import_and_recheck_kept_code(self):
        if not JS.available():
            self.skipTest('local sandboxed node is unavailable')
        self.apps = Replies()
        first = self.call('POST', 'spec/run', {'sheet': SHEET, 'mode': 'task-cards', 'by': ['fake:a'],
                                               'samples': 1, 'rounds': 1, 'retries': 1})
        self.assertEqual(first.status, 200, first.sent)
        view = self.call('GET', 'run', query={'id': first.sent['id']})
        self.assertEqual(view.sent['status'], 'done', view.sent['state'].get('error'))
        exported = self.call('POST', 'spec/manifest', {'id': first.sent['id']})
        self.assertEqual(exported.status, 200, exported.sent)
        manifest = exported.sent['manifest']
        self.assertTrue(self.call('POST', 'spec/verify', {'manifest': manifest}).sent['ok'])
        self.apps.requests.clear()
        second = self.call('POST', 'spec/run', {'sheet': SHEET, 'mode': 'task-cards', 'by': ['fake:a'],
                                                'manifest': manifest, 'samples': 1, 'rounds': 1, 'retries': 1})
        self.assertEqual(second.status, 200, second.sent)
        self.assertEqual(second.sent['kept'], 3)
        self.assertEqual(self.apps.requests, [])
        self.assertEqual(self.call('GET', 'run', query={'id': second.sent['id']}).sent['status'], 'done')
        bad = json.loads(json.dumps(manifest)); bad['output']['text'] += 'altered'
        self.assertEqual(self.call('POST', 'spec/verify', {'manifest': bad}).status, 400)
        meta = json.loads(Path(E.run_dir(second.sent['id']), 'meta.json').read_text())
        self.assertEqual(meta['options']['profile'], 'verified')


    def test_presentation_and_declaration_contracts_validate_before_start(self):
        checked = self.call('POST', 'spec/check', {'sheet': SHEET, 'mode': 'task-cards'})
        unit = checked.sent['plan']['units'][0]
        declarations = {unit['id']: {'version': 1, 'exports': {name: 'function' for name in unit['exports']}}}
        with patch.object(E, 'start_run', lambda body: {'id': 'r1', 'body': body}):
            response = self.call('POST', 'spec/run', {'sheet': SHEET, 'mode': 'task-cards', 'by': ['fake:a'],
                'presentation': 'full', 'declaration_contracts': declarations})
        self.assertEqual(response.status, 200, response.sent)
        self.assertIn('js_declarations_check', response.sent['body']['source'])
        for bad in ({'presentation': 'unknown'}, {'declaration_contracts': {'missing': {}}},
                    {'declaration_contracts': {unit['id']: {'version': 1, 'exports': {'wrong': 'function'}}}}):
            check = self.call('POST', 'spec/check', {'sheet': SHEET, 'mode': 'task-cards', **bad})
            self.assertFalse(check.sent['ok'], check.sent)
            with patch.object(E, 'start_run') as launch:
                response = self.call('POST', 'spec/run', {'sheet': SHEET, 'mode': 'task-cards', **bad})
                self.assertEqual(response.status, 400, response.sent)
                launch.assert_not_called()

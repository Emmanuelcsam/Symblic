"""Model-produced artifacts remain pinned data across shared agent readers."""
import hashlib
import json
from pathlib import Path
from unittest import mock

import unittest
try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import host_tools as bt
    from integration.host import symblic_example_artifacts as A
    from tests.tool_case import ToolCase
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None


class ExampleTools(ToolCase):
    MODULES = ('automation_engine',)
    ENV = {'AUTOMATION_DATA_DIR': '{tmp}/automation', 'ORCHESTRATOR_DATA_DIR': '{tmp}/orchestrator'}

    def setUp(self):
        super().setUp()
        self.root = Path(self.tmp) / 'repo'
        self.base = self.root / 'examples'
        (self.base / 'fixture-build').mkdir(parents=True)
        self.source = 'show "café 🐍".\n'
        self.files = {'example.sym': self.source.encode(), 'cup.stl': b'\x00\xffbinary', 'bad.txt': b'\xff'}
        entries = []
        for name, content in self.files.items():
            (self.base / 'fixture-build' / name).write_bytes(content)
            entries.append({'name': name, 'path': 'fixture-build/' + name, 'bytes': len(content),
                            'sha256': hashlib.sha256(content).hexdigest()})
        self.manifest = {'version': 1, 'bundles': [{'id': 'fixture-build', 'title': 'Synthetic checked build',
                                                 'examples': [], 'files': entries}]}
        (self.base / 'artifacts.json').write_text(json.dumps(self.manifest))
        patch = mock.patch.object(A, 'ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch('symblic.providers.applicators.Applicators.call', side_effect=AssertionError('No model in read'))
        patch.start()
        self.addCleanup(patch.stop)

    def args(self, name='example.sym', **changes):
        return {'bundle': 'fixture-build', 'name': name,
                'sha256': hashlib.sha256(self.files[name]).hexdigest(), **changes}

    def test_shared_catalogue_owner_policy_and_scoped_gateway_refusal(self):
        self.assertDeclarationsClean()
        tool = bt.get('automation.examples')
        self.assertEqual((tool['caller'], tool['effect'], tool['untrusted'], tool['mcp']),
                         ('owner', 'read', True, False))
        import personal_agent as pa
        with self.assertRaises(ValueError):
            pa.issue_token('operator', ['automation.examples'])
        self.assertIn('automation.examples', [r['name'] for r in pa.capabilities(probe={})])
        listed = self.ok('automation.examples', {}, caller_account='owner')['json']
        self.assertEqual(listed['bundles'][0]['file_count'], 3)
        self.assertNotIn('files', listed['bundles'][0])
        files = self.ok('automation.examples', {'bundle': 'fixture-build'}, caller_account='owner')['json']['files']
        self.assertEqual(len(files), 3)
        self.assertNotIn('path', files[0])

    def test_utf8_character_windows_reconstruct_exact_source(self):
        text, offset = '', 0
        while offset is not None:
            out = self.ok('automation.examples', self.args(offset=offset, limit=3), caller_account='owner')['json']
            self.assertLessEqual(len(out['text']), 3)
            self.assertEqual(out['characters'], len(self.source))
            self.assertTrue(out['untrusted'])
            text += out['text']
            offset = out['next_offset']
        self.assertEqual(text, self.source)

    def test_missing_stale_hash_and_changed_disk_bytes_refuse(self):
        args = self.args()
        del args['sha256']
        self.assertIn('SHA-256', self.err('automation.examples', args, caller_account='owner'))
        self.assertIn('SHA-256', self.err('automation.examples', self.args(sha256='0' * 64), caller_account='owner'))
        (self.base / 'fixture-build/example.sym').write_text('different bytes')
        self.assertIn('changed', self.err('automation.examples', self.args(), caller_account='owner'))

    def test_binary_and_invalid_utf8_remain_attachments(self):
        for name in ('cup.stl', 'bad.txt'):
            with self.subTest(name=name):
                out = self.ok('automation.examples', self.args(name), caller_account='owner')['json']
                self.assertFalse(out['text_available'])
                self.assertNotIn('text', out)
                self.assertEqual(out['sha256'], self.args(name)['sha256'])

    def test_invalid_selectors_and_window_bounds_refuse(self):
        bad = [{'name': 'example.sym'}, {'offset': 1}, {'bundle': 'fixture-build', 'limit': 2},
               self.args(offset=True), self.args(limit=12001), self.args(offset=-1),
               self.args(offset=len(self.source) + 1), {**self.args(), 'name': '../secret'},
               {**self.args(), 'name': 'bundle.zip'}, {'bundle': '../private'}]
        for args in bad:
            with self.subTest(args=args):
                self.err('automation.examples', args, caller_account='owner')

    def test_optional_module_absence_is_visible(self):
        with mock.patch.dict('sys.modules', {'symblic_example_artifacts': None}):
            self.assertIn('unavailable', self.err('automation.examples', {}, caller_account='owner'))

    def test_orchestrator_observation_replays_without_read_and_keeps_untrusted_flow(self):
        import host_site as H
        from symblic.kernel import effects as FX
        from symblic.kernel.run import Run
        calls = []

        def http(method, path, body=None, timeout=60):
            if path == '/api/personal-agent/capabilities':
                return 200, {'items': [bt.descriptor(bt.get('automation.examples'))]}
            if path == '/api/host/tools/try':
                calls.append(path)
                return 200, bt.call(body['name'], body['args'], {'caller_account': 'owner'})
            raise AssertionError('Unexpected side effect: ' + path)

        host = H.SiteHost('fixtureexamples', http=http)
        source = 'observe example = automation.examples().\nshow example.data.bundles.'
        rows = host.catalogue()
        self.assertTrue(FX.check(source, rows)['ok'])
        action = {'name': 'agents.start', 'effect': 'compute', 'policy': 'auto', 'instructs': True,
                  'params': {'type': 'object', 'properties': {'prompt': {'type': 'string'}}}}
        unsafe = FX.check(source + '\nact run = agents.start(prompt=example.text).', rows + [action])
        self.assertFalse(unsafe['ok'])
        self.assertTrue(any('untrusted' in e['message'] for e in unsafe['errors']))
        folder = str(Path(self.tmp) / 'observation')
        for _ in range(2):
            result = Run(source, folder=folder, options={'effects': host, 'side_effects': False}).execute()
            self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(len(calls), 1)

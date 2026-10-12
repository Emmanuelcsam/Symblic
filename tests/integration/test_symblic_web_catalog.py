"""Read-only installed protocol metadata; no browser/provider or remote calls.

HOST-ONLY: these cases check the original host's fleet probe (host_agents.PROBE_SH, parse_remote_probe) and its
agent hub, which are not part of this repository, so the module is skipped when host_agents cannot be imported.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

try:  # host-only: these modules belong to the private host system Symblic was built in
    import host_agents as B
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.providers import agent_teams as T


class TypedCatalog(unittest.TestCase):
    def test_metadata_fragment_reads_exact_files_without_importing_them(self):
        fragment = B.PROBE_SH.split('python3 - "$wa" <<\'TYPED_METADATA\'')[1].split('\nTYPED_METADATA')[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = b'throw new Error("must not execute source");\n'
            protocol = b'const VERSION = 1;\nthrow new Error("must not import");\n'
            (root / 'chatgpt.js').write_bytes(entry)
            (root / 'typed-requests.cjs').write_bytes(protocol)
            import sys
            result = subprocess.run([sys.executable, '-', str(root)], input=fragment, text=True,
                                    capture_output=True, check=True)
            expected = hashlib.sha256(entry + protocol).hexdigest()
            caps = B.parse_remote_probe(result.stdout, 'node-a')['web']['typed']
            self.assertEqual(caps, {'version': 1, 'source_sha256': expected})
            (root / 'typed-requests.cjs').unlink()
            missing = subprocess.run([sys.executable, '-', str(root)], input=fragment, text=True,
                                     capture_output=True, check=True)
            self.assertEqual(missing.stdout, '')
            self.assertEqual(B.parse_remote_probe(missing.stdout, 'node-a')['web']['typed'],
                             {'version': None, 'source_sha256': None})

    def test_malformed_probe_does_not_claim_protocol_identity(self):
        for version, digest in [('true', 'a' * 64), ('1', 'untrusted'), ('0', 'ABC' * 22)]:
            with self.subTest(version=version, digest=digest):
                row = B.parse_remote_probe(f'web.typed_version={version}\nweb.typed_source={digest}', 'node-b')['web']['typed']
                if version != '1':
                    self.assertIsNone(row['version'])
                if digest != 'a' * 64:
                    self.assertIsNone(row['source_sha256'])

    def test_protocol_readiness_is_separate_from_account_and_daemon(self):
        source = 'a' * 64
        nodes = [
            {'id': 'node-a', 'probed': True, 'web': {'installed': True, 'chatgpt': False,
                'typed': {'version': 1, 'source_sha256': source}}},
            {'id': 'node-b', 'probed': True, 'web': {'installed': True, 'chatgpt': True,
                'typed': {'version': 1, 'source_sha256': 'b' * 64}}},
            {'id': 'node-c', 'probed': False, 'web': {'installed': False}},
            {'id': 'host', 'online': True},
        ]
        import copy
        before = copy.deepcopy(nodes)
        with mock.patch('symblic_web.source_hash', return_value=source):
            result = T.capability_catalog({'specs': {'gpt': {'title': 'ChatGPT'}}, 'nodes': nodes})
        self.assertEqual(nodes, before, 'catalogue derivation must not rewrite its input')
        self.assertEqual(result['engines']['chatgpt']['typedNodes'], 'registered')
        observed = result['nodes']
        self.assertTrue(observed[0]['web']['typed']['installed_match'])
        self.assertFalse(observed[0]['web']['chatgpt'])
        self.assertNotIn('daemon_match', observed[0]['web']['typed'])
        self.assertFalse(observed[1]['web']['typed']['installed_match'])
        self.assertIsNone(observed[2]['web']['typed']['installed_match'])
        self.assertIsNone(observed[3]['web']['typed']['source_match'])
        with mock.patch('symblic_web.source_hash', side_effect=OSError('unreadable')):
            result = T.capability_catalog({'specs': {}, 'nodes': nodes})
        self.assertIsNone(result['browser_protocol']['source_sha256'])
        self.assertIsNone(result['nodes'][0]['web']['typed']['source_match'])

    def test_remote_browser_member_retains_selected_device_and_profile(self):
        member = {'id': 'critic', 'engine': 'gpt', 'model': 'gpt-test', 'node': 'node-f',
                  'role': 'Check exact types', 'instruction': 'Keep the owner task.'}
        for lane in ('checked', 'forge', 'project'):
            with self.subTest(lane=lane):
                selected = T.normalize({'version': 1, 'members': [member]}, lane=lane)['members'][0]
                self.assertEqual((selected['engine'], selected['node'], selected['model']),
                                 ('chatgpt', 'node-f', 'gpt-test'))
                self.assertEqual(selected['instruction'], member['instruction'])

    def test_fleet_projection_retains_protocol_beside_account_readiness(self):
        import host_agent_hub as hub
        web = {'installed': True, 'chatgpt': False, 'gemini': True,
               'typed': {'version': 1, 'source_sha256': 'c' * 64}}
        capabilities = mock.Mock(return_value={'web': web})
        modules = {'host_fleet': types.SimpleNamespace(nodes=lambda: [
            {'id': 'node-a', 'online': True, 'memavail': 4 * 2**30}]),
            'host_agents': types.SimpleNamespace(capabilities=capabilities)}
        with mock.patch.object(hub, '_import', side_effect=modules.get), \
                mock.patch.object(hub.eng, 'ollama_models', return_value=[]), \
                mock.patch.object(hub.eng, 'login_state', return_value={}), \
                mock.patch.object(hub.eng, 'mem_available', return_value=2**30), \
                mock.patch.object(hub.eng, 'gpu_free', return_value=None):
            rows = hub.fleet_nodes()
        remote = next(row for row in rows if row['id'] == 'node-a')
        self.assertEqual(remote['web']['typed'], web['typed'])
        self.assertFalse(remote['ready']['gpt'])
        self.assertTrue(remote['ready']['gemini'])
        capabilities.assert_called_once_with('node-a', cached_only=True)


if __name__ == '__main__':
    unittest.main()

"""Checked example publication: isolated fixtures, no models, stores or server."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from integration.host import symblic_example_artifacts as A
from tests.integration import fake_host_apps


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = mock.patch.object(A, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.base = self.root / 'docs/symblic/examples'
        self.bundle = self.base / 'checked-build'
        self.bundle.mkdir(parents=True)
        self.content = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
        (self.bundle / 'chart.svg').write_bytes(self.content)
        (self.base / '41-playback.sym').write_text('show 1.\n')
        self.raw = {'version': 1, 'bundles': [{'id': 'checked-build', 'title': 'Checked build',
                    'examples': ['41-playback'], 'files': [self.entry('checked-build/chart.svg'),
                                                        self.entry('41-playback.sym')]}]}
        self.write()

    def entry(self, path):
        value = (self.base / path).read_bytes()
        return {'name': Path(path).name, 'path': path, 'bytes': len(value),
                'sha256': hashlib.sha256(value).hexdigest()}

    def write(self):
        (self.base / 'artifacts.json').write_text(json.dumps(self.raw))

    def assert_refused(self, fn, status):
        with self.assertRaises(A.ArtifactError) as found:
            fn()
        self.assertEqual(found.exception.status, status)

    def test_catalogue_only_declared_downloads_without_local_paths(self):
        (self.bundle / 'unpublished.json').write_text('private fixture')
        row = A.catalogue()['bundles'][0]
        self.assertEqual([f['name'] for f in row['files']], ['chart.svg', '41-playback.sym'])
        self.assertTrue(row['download_url'].endswith('id=checked-build&name=bundle.zip'))
        self.assertNotIn('path', row['files'][0])

    def test_exact_binary_and_complete_zip_without_sibling_files(self):
        (self.bundle / 'unpublished.json').write_text('private fixture')
        self.assertEqual(A.download('checked-build', 'chart.svg'),
                         (self.content, 'chart.svg', 'application/octet-stream'))
        blob, filename, mime = A.download('checked-build', 'bundle.zip')
        self.assertEqual((filename, mime), ('checked-build.zip', 'application/zip'))
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            self.assertEqual(z.namelist(), ['chart.svg', '41-playback.sym'])
            self.assertEqual(z.read('chart.svg'), self.content)
            self.assertEqual(z.read('41-playback.sym'), b'show 1.\n')
        self.assertEqual(blob, A.download('checked-build', 'bundle.zip')[0])

    def test_query_traversal_and_undeclared_names_refused(self):
        for bid, name in [('..', 'chart.svg'), ('checked-build', '../chart.svg'),
                          ('checked-build', '/etc/passwd'), ('checked-build', 'unpublished.json'),
                          ('checked-build', 'chart.svg\r\nX-Test: yes'), ('other', 'chart.svg'),
                          ('checked-build', '%2e%2e%2fsecrets'), (None, 'chart.svg')]:
            with self.subTest(bid=bid, name=name):
                self.assert_refused(lambda: A.download(bid, name), 404)

    def test_changed_bytes_block_individual_and_whole_zip(self):
        (self.bundle / 'chart.svg').write_bytes(b'x' * len(self.content))
        for name in ['chart.svg', 'bundle.zip']:
            self.assert_refused(lambda: A.download('checked-build', name), 409)

    def test_file_symlink_refused_even_if_target_hash_matches(self):
        target = self.root / 'private.svg'
        target.write_bytes(self.content)
        (self.bundle / 'chart.svg').unlink()
        (self.bundle / 'chart.svg').symlink_to(target)
        self.assert_refused(lambda: A.download('checked-build', 'chart.svg'), 409)

    def test_directory_symlink_refused(self):
        target = self.root / 'moved'
        self.bundle.rename(target)
        self.bundle.symlink_to(target, target_is_directory=True)
        self.assert_refused(lambda: A.download('checked-build', 'chart.svg'), 409)

    def test_manifest_symlink_refused(self):
        path = self.base / 'artifacts.json'
        target = self.root / 'manifest.json'
        path.rename(target)
        path.symlink_to(target)
        self.assert_refused(A.catalogue, 503)

    def test_fifo_refused_without_blocking(self):
        path = self.bundle / 'chart.svg'
        path.unlink()
        os.mkfifo(path)
        self.assert_refused(lambda: A.download('checked-build', 'chart.svg'), 409)

    def test_invalid_manifest_paths_and_bounds_refuse_whole_catalogue(self):
        original = json.dumps(self.raw)
        changes = [('path', '../secret.svg'), ('path', 'other/chart.svg'),
                   ('path', '/etc/passwd'), ('bytes', True), ('bytes', A.MAX_FILE + 1),
                   ('sha256', 'invalid'), ('name', 'bundle.zip')]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.raw = json.loads(original)
                self.raw['bundles'][0]['files'][0][key] = value
                self.write()
                self.assert_refused(A.catalogue, 503)

    def test_duplicate_fields_and_filenames_refused(self):
        (self.base / 'artifacts.json').write_text('{"version":1,"version":1,"bundles":[]}')
        self.assert_refused(A.catalogue, 503)
        self.raw['bundles'][0]['files'].append(dict(self.raw['bundles'][0]['files'][0]))
        self.write()
        self.assert_refused(A.catalogue, 503)

    def test_oversized_actual_file_and_missing_file_refused(self):
        with mock.patch.object(A, 'MAX_FILE', len(self.content)):
            (self.bundle / 'chart.svg').write_bytes(self.content + b'x')
            self.assert_refused(lambda: A.download('checked-build', 'chart.svg'), 409)
        (self.bundle / 'chart.svg').unlink()
        self.assert_refused(lambda: A.download('checked-build', 'chart.svg'), 409)

    def test_http_attachment_headers_and_non_get_never_downloads(self):
        class Handler:
            def __init__(self):
                self.wfile, self.headers = io.BytesIO(), {}
            def get_query_param(self, name):
                return {'id': 'checked-build', 'name': 'chart.svg'}[name]
            def send_response(self, status): self.status = status
            def send_header(self, name, value): self.headers[name] = value
            def end_headers(self): pass
        h = Handler()
        self.assertTrue(A.handle(h, 'GET', 'examples/artifact', {}))
        self.assertEqual(h.status, 200)
        self.assertEqual(h.wfile.getvalue(), self.content)
        self.assertEqual(h.headers['Content-Disposition'], 'attachment; filename="chart.svg"')
        self.assertEqual(h.headers['Content-Type'], 'application/octet-stream')
        self.assertEqual(h.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(h.headers['Cache-Control'], 'private, no-store')
        with mock.patch.object(A, 'download', side_effect=AssertionError('must not read')):
            self.assertFalse(A.handle(h, 'POST', 'examples/artifact', {}))

    def test_engine_routes_existing_owner_prefix_and_optional_import_failure(self):
        from integration.host import symblic_engine as symblic_engine
        class Handler:
            def get_query_param(self, name): return None
            def send_json(self, data, status=200, extra_headers=None): self.sent = (data, status)
        h = Handler()
        self.assertTrue(symblic_engine.handle(h, 'GET', 'examples/artifacts', {}))
        self.assertEqual(h.sent[1], 200)
        import builtins
        real_import = builtins.__import__

        def missing(name, *args, **kwargs):
            fromlist = args[2] if len(args) > 2 else kwargs.get('fromlist') or ()
            if name == 'integration.host' and 'symblic_example_artifacts' in (fromlist or ()):
                raise ImportError('isolated missing module')
            return real_import(name, *args, **kwargs)
        with mock.patch('builtins.__import__', side_effect=missing):
            self.assertTrue(symblic_engine.handle(h, 'GET', 'examples/artifacts', {}))
            self.assertEqual(h.sent[1], 503)

    def test_non_owner_cannot_reach_catalogue_or_attachment(self):
        host_apps = fake_host_apps.router(self)
        class Handler:
            def require_owner(self, module):
                self.checked = module
                return False
        for route in ['artifacts', 'artifact?id=checked-build&name=chart.svg']:
            h = Handler()
            h.path = A.API + route
            with mock.patch.object(host_apps, '_module_for', side_effect=AssertionError('must not import')):
                self.assertTrue(host_apps.handle_get(h))
            self.assertEqual(h.checked, 'automation_engine')

    def test_bundle_total_size_limit_is_enforced(self):
        with mock.patch.object(A, 'MAX_BUNDLE', len(self.content)):
            self.assert_refused(A.catalogue, 503)


if __name__ == '__main__':
    unittest.main()

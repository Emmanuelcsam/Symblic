"""The host-only Academy source route: temporary catalogs, plus a read-only pass over the shipped catalog."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integration.host import symblic_academy_sources as reader
from integration.host import symblic_engine

REPOSITORY = Path(__file__).resolve().parents[2]


class SourceReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.object(reader, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = '/docs/reference/example.md'
        self.file = self.root / self.path[1:]
        self.file.parent.mkdir(parents=True)
        self.file.write_text('Original source <script>not executable</script>')
        self.catalog([self.path])

    def catalog(self, urls):
        data = {'levels': [], 'sources': [{'url': url, 'title': 'Fixture', 'sha256': 'old'} for url in urls]}
        target = self.root / reader.CATALOG
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('/* comment */\n' + reader.MARKER + json.dumps(data) + ';\n')

    def test_original_text_and_fresh_hash(self):
        result = reader.read_source(self.path)
        self.assertEqual(result['text'], self.file.read_text())
        self.assertEqual(len(result['sha256']), 64)
        self.assertTrue(result['changed_since_index'])

    def test_every_document_root_is_readable(self):
        urls = ['/docs/a.md', '/examples/b.sym', '/benchmarks/c.json', '/kits/d/e.symd']
        for url in urls:
            (self.root / url[1:]).parent.mkdir(parents=True, exist_ok=True)
            (self.root / url[1:]).write_text('text of ' + url)
        self.catalog(urls)
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(reader.read_source(url)['text'], 'text of ' + url)

    def test_catalog_paths_cannot_escape_or_select_private_files(self):
        private = ['/symblic/bench/data/listed.json', '/tests/fixture.sym', '/web/academy/symblic-academy-content.js',
                   '/README.md']
        for url in private:
            (self.root / url[1:]).parent.mkdir(parents=True, exist_ok=True)
            (self.root / url[1:]).write_text('outside the document roots')
        invalid = ['/docs/reference/../private.md', '/.env', '/docs//reference/example.md', '/docs/reference/example.py',
                   '/docs/reference/example.md?download=1', '/docs/.hidden/example.md', 'docs/reference/example.md',
                   *private]
        self.catalog(invalid)
        for url in invalid + [self.path, '']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                reader.read_source(url)

    def test_symlinks_and_oversize_text_are_refused(self):
        self.file.unlink()
        secret = self.root / 'private.md'
        secret.write_text('fixture secret')
        self.file.symlink_to(secret)
        with self.assertRaises(ValueError):
            reader.read_source(self.path)
        self.file.unlink()
        linked = self.root / 'docs' / 'linked'
        linked.symlink_to(self.root)
        self.catalog(['/docs/linked/private.md'])
        with self.assertRaises(ValueError):
            reader.read_source('/docs/linked/private.md')
        self.file.write_text('0123456789')
        self.catalog([self.path])
        with patch.object(reader, 'MAX_BYTES', 4), self.assertRaises(ValueError):
            reader.read_source(self.path)

    def test_route_checks_owner_before_read_and_is_get_only(self):
        responses = []
        handler = SimpleNamespace(identity=lambda: SimpleNamespace(is_owner=False),
                                  get_query_param=lambda _key: self.path,
                                  send_json=lambda data, status=200: responses.append((status, data)))
        with patch.object(reader, 'read_source', side_effect=AssertionError('must not read')):
            self.assertTrue(symblic_engine.handle(handler, 'GET', 'academy/source', {}))
            self.assertEqual(responses[-1][0], 403)
            handler.identity = lambda: SimpleNamespace(is_owner=True)
            symblic_engine.handle(handler, 'POST', 'academy/source', {})
            self.assertEqual(responses[-1][0], 405)
        symblic_engine.handle(handler, 'GET', 'academy/source', {})
        self.assertEqual(responses[-1][0], 200)
        self.assertEqual(responses[-1][1]['path'], self.path)
        handler.get_query_param = lambda _key: '/.env'
        symblic_engine.handle(handler, 'GET', 'academy/source', {})
        self.assertEqual(responses[-1][0], 404)


class ShippedCatalog(unittest.TestCase):
    """The reader against this repository's own catalog; reads files, writes nothing."""

    def test_reader_and_refresh_script_agree_on_the_document_rules(self):
        spec = importlib.util.spec_from_file_location(
            'symblic_refresh_catalog', REPOSITORY / 'tools/scripts/symblic_refresh_catalog.py')
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        self.assertEqual(reader.DOCUMENT_ROOTS, ('docs', 'examples', 'benchmarks', 'kits'))
        self.assertEqual(script.DOCUMENT_ROOTS, reader.DOCUMENT_ROOTS)
        self.assertEqual(script.SUFFIXES, set(reader.SUFFIXES))
        self.assertEqual((script.CATALOG, script.MAX_BYTES, script.MARKER), (str(reader.CATALOG), reader.MAX_BYTES, reader.MARKER))

    def test_rows_under_the_document_roots_are_served_and_the_others_refused(self):
        self.assertEqual(reader.ROOT, REPOSITORY)
        served = refused = 0
        for source in reader._catalog_sources():
            url = source['url']
            if url.startswith('https://'):
                continue
            with self.subTest(url=url):
                if url.split('/')[1] in reader.DOCUMENT_ROOTS:
                    result = reader.read_source(url)
                    self.assertEqual(result['text'].encode('utf-8'), (REPOSITORY / url[1:]).read_bytes())
                    served += 1
                else:
                    with self.assertRaises(ValueError):
                        reader.read_source(url)
                    refused += 1
        self.assertGreater(served, 200)
        self.assertLess(refused, 10)


if __name__ == '__main__':
    unittest.main()

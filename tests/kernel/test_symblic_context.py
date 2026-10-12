"""Fresh, bounded source navigation; no model calls or source-tree writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import io
import tarfile

from symblic.kernel import context_packs as context


class SourceContext(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = 'def move_snake(x):\n    return x + 1\n\ndef game():\n    return move_snake(1)\n'
        (self.root / 'game.py').write_text(self.source)

    def test_exact_selected_context_is_fresh_and_hash_bound(self):
        (self.root / 'unrelated.py').write_text('private_value = "DO NOT INCLUDE"')
        first = context.make_pack(self.root, ['game.py'], query='move_snake')
        self.assertEqual(first['files'][0]['sha256'], hashlib.sha256(self.source.encode()).hexdigest())
        self.assertNotIn('DO NOT INCLUDE', json.dumps(first))
        self.assertIn('move_snake', first['files'][0]['excerpt'])
        (self.root / 'game.py').write_text('def replacement():\n    return 2\n')
        second = context.make_pack(self.root, ['game.py'])
        self.assertNotEqual(first['files'][0]['sha256'], second['files'][0]['sha256'])
        self.assertNotIn('move_snake', json.dumps(second))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['game.py', 'unrelated.py'])

    def test_private_paths_traversal_symlinks_binary_and_limits_refuse(self):
        (self.root / 'alias.py').symlink_to(self.root / 'game.py')
        (self.root / 'private_data').mkdir()
        (self.root / 'private_data/session.py').write_text('token = 1')
        (self.root / 'binary.py').write_bytes(b'\0')
        (self.root / 'large.py').write_bytes(b'a' * (context.MAX_FILE_BYTES + 1))
        for name in ('../game.py', str(self.root / 'game.py'), 'alias.py',
                     'private_data/session.py', 'binary.py', 'large.py', '.env.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                context.make_pack(self.root, [name])
        for names in ([], ['game.py'] * (context.MAX_FILES + 1)):
            with self.assertRaises(ValueError):
                context.make_pack(self.root, names)

    def test_budget_and_omissions_are_explicit(self):
        (self.root / 'many.py').write_text('\n'.join(f'def function_{i}():\n    return {i}' for i in range(200)))
        data = context.make_pack(self.root, ['many.py', 'game.py'], query='function', max_chars=1000)
        self.assertLessEqual(data['content_characters'], 1000)
        self.assertTrue(data['files'][0]['symbols_omitted'])
        self.assertTrue(data['files'][0]['excerpt_truncated'])
        self.assertTrue(data['omitted_files'])

    def test_query_is_literal_and_input_changes_are_visible(self):
        data = context.make_pack(self.root, ['game.py'], query='(a+)+$')
        self.assertEqual(data['files'][0]['matches'], 0)
        with self.assertRaises(ValueError):
            context.make_pack(self.root, ['game.py'], query='x' * 241)

    def test_command_line_pack_uses_python_symbols_and_optional_grep_ast(self):
        repo = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, '-m', 'symblic.kernel.context_packs', 'pack', '--root', str(self.root),
                                 '--file', 'game.py', '--query', 'move_snake'],
                                cwd=repo, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['files'][0]['symbols_engine'], 'python-ast')
        self.assertIn(data['files'][0]['search_engine'], ('grep-ast', 'line-context'))
        self.assertIn('move_snake', data['files'][0]['symbols'][1]['calls'])

    def test_node_installer_extraction_refuses_links_and_traversal_before_writes(self):
        script = Path(__file__).resolve().parents[2] / 'tools/scripts/install_symblic_tools.py'
        if not script.is_file():
            self.skipTest('tools/scripts/install_symblic_tools.py is not present')
        spec = importlib.util.spec_from_file_location('install_symblic_tools_under_test', script)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        extract_source = installer.extract_source
        for bad in ('../escape.py', '/absolute.py', 'link.py'):
            archive = self.root / 'input.tar'
            with tarfile.open(archive, 'w') as stream:
                good = tarfile.TarInfo('good.py'); good.size = 1
                stream.addfile(good, io.BytesIO(b'x'))
                item = tarfile.TarInfo(bad)
                if bad == 'link.py':
                    item.type = tarfile.SYMTYPE
                    item.linkname = '/tmp/escape'
                stream.addfile(item)
            destination = self.root / 'extract'
            destination.mkdir(exist_ok=True)
            with self.assertRaises(ValueError):
                extract_source(archive, destination)
            self.assertEqual(list(destination.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

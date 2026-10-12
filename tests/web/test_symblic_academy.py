"""The Academy's catalog (web/academy/symblic-academy-content.js) against its own lessons, this repository's files
and the kernel. Read only: no model, network, browser or host, and nothing is written.

Ported from the original host's curriculum tests (the Symblic half; the cases for another course of the host were
left out). The refresh script has its own tests in tests/tools/test_symblic_refresh_catalog.py, the host-only
source route in tests/integration/test_symblic_academy_sources.py, and the page in tests/browser/symblic-academy.mjs.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import unittest

from symblic.kernel import run as SR

REPOSITORY = Path(__file__).resolve().parents[2]
CATALOG = REPOSITORY / 'web/academy/symblic-academy-content.js'
MARKER = 'window.SymblicAcademyContent = '
REFRESH = 'python3 tools/scripts/symblic_refresh_catalog.py'

_SPEC = importlib.util.spec_from_file_location('symblic_refresh_catalog',
                                               REPOSITORY / 'tools/scripts/symblic_refresh_catalog.py')
RULES = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(RULES)


def catalog():
    """The catalog as the page receives it: comments, then one assignment of JSON data, then ';'."""
    raw = CATALOG.read_text(encoding='utf-8')
    head, _, rest = raw.partition(MARKER)
    if MARKER in rest or re.sub(r'/\*.*?\*/', '', head, flags=re.S).strip():
        raise AssertionError('the catalog must be comments followed by one assignment of JSON data')
    data, end = json.JSONDecoder().raw_decode(rest)
    if rest[end:].strip() != ';':
        raise AssertionError('the catalog must end with the JSON data and ";"')
    return data


def repository_file(url):
    """The file a repository path ("/docs/reference/SPEC.md") names; refuses '..', '//' and other spellings."""
    relative = PurePosixPath(url[1:])
    if not url.startswith('/') or str(relative) != url[1:] or not relative.parts or '..' in relative.parts:
        raise AssertionError('not a normalized repository path: ' + repr(url))
    return REPOSITORY.joinpath(*relative.parts)


def bites(data):
    return [bite for level in data['levels'] for bite in level['bites']]


class Curriculum(unittest.TestCase):
    """The authored lessons (levels of bites)."""

    @classmethod
    def setUpClass(cls):
        cls.data = catalog()

    def test_levels_and_bites_keep_their_positions(self):
        # Sources link lessons by (level, bite) position, and saved progress uses the same positions.
        levels = self.data['levels']
        self.assertEqual(len(levels), 15)
        self.assertGreaterEqual(len(bites(self.data)), 61)
        self.assertEqual([len(level['bites']) for level in levels[:7]], [4, 4, 4, 4, 4, 5, 4])

    def test_every_lesson_teaches_and_tests_a_distinct_application(self):
        prompts = set()
        for bite in bites(self.data):
            with self.subTest(bite=bite['title']):
                self.assertGreaterEqual(len(bite['worked']['steps']), 3)
                self.assertTrue(bite['worked']['takeaway'])
                self.assertTrue(bite['reflection']['prompt'])
                self.assertTrue(bite['reflection']['model'])
                self.assertNotEqual(bite['reflection']['prompt'], bite['question'])
                self.assertNotIn(bite['question'], prompts)
                prompts.add(bite['question'])
                self.assertEqual(len(bite['feedback']), len(bite['options']))
                self.assertEqual(len(set(bite['feedback'])), len(bite['feedback']))
                self.assertTrue(0 <= bite['ans'] < len(bite['options']))
                # The host's other course attached private library links ('connections'); none may enter this catalog.
                self.assertNotIn('connections', bite)

    def test_every_reference_is_an_https_link_or_a_file_of_this_repository(self):
        for bite in bites(self.data):
            for ref in bite['references']:
                with self.subTest(bite=bite['title'], url=ref['url']):
                    self.assertTrue(ref['title'])
                    if not ref['url'].startswith('https://'):
                        self.assertTrue(repository_file(ref['url']).is_file(), ref['url'])


class Sources(unittest.TestCase):
    """The research map: one row per document, with the lessons that use it."""

    @classmethod
    def setUpClass(cls):
        cls.data = catalog()

    def test_every_source_is_a_file_of_this_repository_with_its_recorded_hash(self):
        urls = [row['url'] for row in self.data['sources']]
        self.assertEqual(len(urls), len(set(urls)))
        for row in self.data['sources']:
            if row['url'].startswith('https://'):
                continue
            with self.subTest(url=row['url']):
                path = repository_file(row['url'])
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['sha256'],
                                 'changed since the catalog was refreshed; run ' + REFRESH)
                self.assertEqual((row['provenance']['path'], row['provenance']['sha256']), (row['url'], row['sha256']))

    def test_every_lesson_link_names_an_existing_bite(self):
        levels = self.data['levels']
        for row in self.data['sources']:
            for lesson in row['lessons']:
                with self.subTest(url=row['url'], lesson=lesson):
                    self.assertEqual(levels[lesson['level']]['bites'][lesson['bite']]['title'], lesson['title'])

    def test_every_public_document_is_listed(self):
        # The refresh script's rules: its document roots and suffixes, without hidden or cache folders.
        listed = {row['url'] for row in self.data['sources']}
        found = 0
        for name in RULES.DOCUMENT_ROOTS:
            for folder, subfolders, files in os.walk(REPOSITORY / name):
                subfolders[:] = [f for f in subfolders if not f.startswith('.') and f not in RULES.SKIPPED_FOLDERS]
                for file in files:
                    if file.startswith('.') or Path(file).suffix not in RULES.SUFFIXES:
                        continue
                    url = '/' + (Path(folder) / file).relative_to(REPOSITORY).as_posix()
                    found += 1
                    with self.subTest(url=url):
                        self.assertIn(url, listed, 'not in the catalog; run ' + REFRESH)
        self.assertGreater(found, 200)


class TeachingExamples(unittest.TestCase):
    def test_all_executable_teaching_examples_run_without_model_calls(self):
        ran = 0
        for bite in bites(catalog()):
            if not bite.get('code'):
                continue
            with self.subTest(bite=bite['title']):
                # No applicators and the kernel route: an `ask` would fail the run instead of reaching a model.
                report = SR.Run(bite['code'], None, None, {'by': 'kernel', 'max_calls': 0}).execute()
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(report['calls'], 0)
            ran += 1
        self.assertGreater(ran, 0)


if __name__ == '__main__':
    unittest.main()

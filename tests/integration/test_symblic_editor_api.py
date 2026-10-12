"""Owner-module editor route: source diagnostics never launch a run."""
import builtins
import tempfile
import unittest
from unittest.mock import patch

from symblic.authoring import editor_diagnostics as D

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None


class Handler:
    def __init__(self):
        self.reply = None
        self.status = None

    def get_query_param(self, name):
        return ''

    def send_json(self, value, status=200):
        self.reply, self.status = value, status


class EditorRoute(unittest.TestCase):
    def call(self, body):
        handler = Handler()
        with tempfile.TemporaryDirectory() as folder, patch.object(E, 'root', return_value=folder), \
                patch.object(E, 'start_run', side_effect=AssertionError('editor launched a run')), \
                patch.object(E, 'preview', side_effect=AssertionError('editor invoked runtime preview')):
            self.assertTrue(E.handle(handler, 'POST', 'editor/check', body))
        return handler

    def test_native_error_is_a_successful_diagnostic_response_with_exact_source(self):
        source = 'use profile=verified.\nlet total = (2 + ).'
        h = self.call({'source': source, 'language': 'native'})
        self.assertEqual(h.status, 200)
        self.assertEqual(h.reply, D.check(source, language='native'))
        self.assertTrue(h.reply['available'])
        self.assertFalse(h.reply['ok'])
        self.assertEqual(h.reply['diagnostics'][0]['severity'], 'error')
        self.assertEqual(h.reply['scope']['provider_calls'], 0)

    def test_english_and_paper_keep_their_existing_check_shapes(self):
        for language, source in [('english', 'Remember count is 2.\nShow count.'),
                                 ('paper', '# My calculation\n\n```symblic\nlet value = 3.\nshow value.\n```')]:
            with self.subTest(language=language):
                h = self.call({'source': source, 'language': language})
                self.assertEqual(h.status, 200)
                self.assertTrue(h.reply['available'])
                self.assertTrue(h.reply['ok'], h.reply)
                self.assertTrue(h.reply['check'])

    def test_invalid_input_and_profile_are_visible_and_do_not_dispatch(self):
        for body in [{'source': []}, {'source': 'show 3.', 'language': 'python'},
                     {'source': 'show 3.', 'profile': 'stronger-than-verified'}]:
            with self.subTest(body=body):
                h = self.call(body)
                self.assertEqual(h.status, 200)
                self.assertFalse(h.reply['ok'])
                self.assertEqual(h.reply['diagnostics'][0]['position_kind'], 'none')

    def test_missing_optional_helper_requests_the_server_update(self):
        actual_import = builtins.__import__
        def optional(name, *args, **kwargs):
            fromlist = args[2] if len(args) > 2 else kwargs.get('fromlist') or ()
            if name == 'symblic.authoring' and 'editor_diagnostics' in (fromlist or ()):
                raise ImportError('isolated missing helper')
            return actual_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=optional):
            h = self.call({'source': 'show 3.'})
        self.assertEqual(h.status, 503)
        self.assertIn('restart', h.reply['error'])

    def test_checker_unavailable_never_reports_a_passing_document(self):
        with patch.object(D.S, 'check', side_effect=RuntimeError('isolated checker failure')):
            h = self.call({'source': 'show 3.'})
        self.assertEqual(h.status, 200)
        self.assertFalse(h.reply['available'])
        self.assertIsNone(h.reply['ok'])
        self.assertIsNone(h.reply['check'])


if __name__ == '__main__':
    unittest.main()

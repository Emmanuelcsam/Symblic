"""Source diagnostics use the actual parsers, exact buffers and no dispatch."""
import hashlib
import socket
import subprocess
import unittest
from unittest.mock import patch

from symblic.authoring import editor_diagnostics as D

from symblic.kernel import language as S
from symblic.english import compiler as EN
from symblic.authoring import paper as P
from symblic.kernel import run as RUN


def slice_utf16(source, start, end):
    return source.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')


class SourceDiagnostics(unittest.TestCase):
    def test_exact_source_identity_and_browser_offsets(self):
        source = 'let greeting = "😀 e\u0301".\r\nlet x = 1 + ).\r\n'
        reply = D.check(source)
        self.assertEqual(reply['source_sha256'], hashlib.sha256(source.encode('utf-8')).hexdigest())
        self.assertEqual(reply['source_length_utf16'], len(source.encode('utf-16-le')) // 2)
        self.assertFalse(reply['ok'])
        row = reply['diagnostics'][0]
        self.assertEqual((row['line'], row['col'], row['position_kind']), (2, 13, 'token'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')

    def test_static_name_warnings_are_line_scoped_and_all_retained(self):
        source = 'let x = missing.\nshow other.'
        reply = D.check(source)
        self.assertTrue(reply['available'] and reply['ok'])
        self.assertEqual(len(reply['diagnostics']), 2)
        self.assertTrue(all(row['severity'] == 'warning' and row['position_kind'] == 'line'
                            for row in reply['diagnostics']))
        self.assertEqual(slice_utf16(source, *[reply['diagnostics'][1][k] for k in ('start', 'end')]), 'show other.')

    def test_semantic_statement_anchor_is_not_falsely_an_offending_keyword(self):
        source = 'let x = 1.\nlet x = 2.'
        row = D.check(source)['diagnostics'][0]
        self.assertEqual(row['code'], 'SYM_NAME')
        self.assertEqual(row['position_kind'], 'line')
        self.assertEqual(slice_utf16(source, row['start'], row['end']), 'let x = 2.')

    def test_indented_semantic_statement_anchors_are_line_scoped(self):
        for indent in ('  ', '\t', ' \t '):
            with self.subTest(indent=repr(indent)):
                source = f'{indent}let x = 1.\n{indent}let x = 2.'
                row = D.check(source)['diagnostics'][0]
                self.assertEqual((row['code'], row['line'], row['position_kind']), ('SYM_NAME', 2, 'line'))
                self.assertEqual(slice_utf16(source, row['start'], row['end']), indent + 'let x = 2.')

    def test_indented_ask_option_statement_anchors_are_line_scoped(self):
        for indent in ('  ', '\t', ' \t '):
            with self.subTest(indent=repr(indent)):
                source = indent + 'ask x: Int "pick" with effort=impossible.'
                row = D.check(source)['diagnostics'][0]
                self.assertEqual((row['code'], row['position_kind']), ('SYM_SYNTAX', 'line'))
                self.assertEqual(slice_utf16(source, row['start'], row['end']), source)
                # A precise interior parse failure must retain its token range.
                source = indent + 'ask x: Int "pick" with effort=).'
                row = D.check(source)['diagnostics'][0]
                self.assertEqual(row['position_kind'], 'token')
                self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')

    def test_indented_paper_statement_anchor_remains_line_scoped(self):
        source = '# T\n```symblic\n    let x = 1.\n      let x = 2.\n```'
        row = D.check(source, 'paper')['diagnostics'][0]
        self.assertEqual((row['line'], row['position_kind']), (4, 'line'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), '      let x = 2.')

    def test_unplaced_native_diagnostic_stays_unplaced(self):
        checked = {'ok': False, 'errors': [{'line': 0, 'col': 0, 'message': 'whole-program issue'}],
                   'warnings': [], 'plan': []}
        with patch.object(S, 'check', return_value=checked):
            row = D.check('let x = 1.')['diagnostics'][0]
        self.assertEqual((row['line'], row['col'], row['start'], row['end'], row['position_kind']),
                         (0, 0, None, None, 'none'))

    def test_no_fake_token_end_when_lexer_refuses(self):
        source = 'let x = @.'
        row = D.check(source)['diagnostics'][0]
        self.assertEqual(row['position_kind'], 'point')
        self.assertEqual(row['start'], row['end'])
        self.assertEqual(source[row['start']], '@')

    def test_english_bom_crlf_and_token_span(self):
        source = '\ufeffRemember x is 1 plus .\r\n'
        row = D.check(source, 'english')['diagnostics'][0]
        self.assertEqual((row['line'], row['col'], row['position_kind']), (1, 18, 'token'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), 'plus')
        source = '\ufeffRemember greeting is "😀".\r\nRemember x is 1 plus .'
        row = D.check(source, 'english')['diagnostics'][0]
        self.assertEqual((row['line'], row['col']), (2, 17))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), 'plus')

    def test_english_mapped_native_errors_are_statement_ranges(self):
        source = '\ufeffRemember x is 1.\r\nShow x.'
        checked = {'ok': False, 'errors': [{'line': 2, 'col': 1, 'statement': 2,
                   'message': 'native check issue', 'code': 'ENG_NATIVE',
                   'native': {'line': 8, 'col': 9, 'message': 'native check issue'}}], 'warnings': []}
        with patch.object(EN, 'check_source', return_value=checked):
            row = D.check(source, 'english')['diagnostics'][0]
        self.assertEqual(row['position_kind'], 'line')
        self.assertEqual(slice_utf16(source, row['start'], row['end']), 'Show x.')

    def test_english_unmapped_native_error_does_not_underline_first_line(self):
        checked = {'ok': False, 'errors': [{'line': 1, 'col': 1, 'statement': None,
                   'message': 'native issue', 'native': {'line': 0, 'col': 0, 'message': 'native issue'}}],
                   'warnings': []}
        with patch.object(EN, 'check_source', return_value=checked):
            row = D.check('Remember x is 1.', 'english')['diagnostics'][0]
        self.assertEqual(row['position_kind'], 'none')

    def test_paper_dedented_code_maps_to_original_utf16(self):
        source = '# 😀\r\n```symblic\r\n    let x = 1.\r\n      let y = 1 + ).\r\n```'
        reply = D.check(source, 'paper')
        self.assertFalse(reply['ok'])
        row = reply['diagnostics'][0]
        self.assertEqual((row['line'], row['col'], row['position_kind']), (4, 19, 'token'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')

    def test_paper_unclosed_fence_is_line_scoped(self):
        source = '# Title\n```symblic\nlet x = 1.'
        row = D.check(source, 'paper')['diagnostics'][0]
        self.assertEqual((row['line'], row['position_kind']), (2, 'line'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), '```symblic')

    def test_paper_checker_matches_existing_authority(self):
        for source in ('# T\n```symblic\ngiven x: Int.\nshow x.\n```',
                       '# T\nMaybe this is good.\n```symblic\nshow missing.\n```',
                       '---\nunknown: one\n---\n# T\n```symblic\nlet x = 1 + ).\n```'):
            with self.subTest(source=source):
                self.assertEqual(D.check(source, 'paper')['check'], P.check_paper(source))

    def test_generated_paper_diagnostic_does_not_claim_native_column(self):
        source = '---\neffort: low\n---\n# Title\n```symblic\nshow 1.\n```'
        checked = {'ok': False, 'errors': [{'line': 1, 'col': 5, 'kind': 'check', 'message': 'front issue'}],
                   'warnings': [], 'plan': []}
        with patch.object(S, 'check', return_value=checked):
            row = D.check(source, 'paper')['diagnostics'][0]
        self.assertEqual((row['line'], row['position_kind']), (1, 'line'))

    def test_cr_only_native_source_maps_like_authoritative_parser(self):
        source = 'let x = "😀".\rlet y = 1 + ).'
        row = D.check(source)['diagnostics'][0]
        self.assertEqual(row['line'], 2)
        self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')

    def test_native_indentation_and_same_line_statement_refusal(self):
        source = '    let x = 1 + ).'
        row = D.check(source)['diagnostics'][0]
        self.assertEqual((row['col'], row['position_kind']), (17, 'token'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')
        source = 'let x=1. let y = @.'
        row = D.check(source)['diagnostics'][0]
        self.assertEqual((row['col'], row['position_kind']), (8, 'point'))
        self.assertEqual(source[row['start']], '.')

    def test_joined_native_continuation_preserves_original_line_after_gaps(self):
        source = 'ask x: Int "one"\r\n\r\n# comment\r\nwith effort=).'
        # The parser's joined statement reports synthetic line 2; the editor
        # must locate its exact original line 4 instead of marking the blank.
        self.assertEqual(S.check(source)['errors'][0]['line'], 2)
        row = D.check(source)['diagnostics'][0]
        self.assertEqual((row['line'], row['col'], row['position_kind']), (4, 13, 'token'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')

    def test_joined_paper_continuation_preserves_indent_and_skipped_lines(self):
        source = '# T\n```symblic\n    ask x: Int "one"\n\n    # comment\n    with effort=).\n```'
        row = D.check(source, 'paper')['diagnostics'][0]
        self.assertEqual((row['line'], row['col'], row['position_kind']), (6, 17, 'token'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), ')')

    def test_native_bom_is_not_silently_removed_or_reported_as_token_error(self):
        source = '\ufefflet x = 1 + ).'
        reply = D.check(source)
        self.assertEqual(reply['check'], S.check(source))
        row = reply['diagnostics'][0]
        self.assertEqual((row['code'], row['position_kind']), ('SYM_IMPLICIT_ASK', 'line'))
        self.assertEqual(slice_utf16(source, row['start'], row['end']), source)

    def test_paper_prose_lints_keep_honest_line_precision(self):
        source = '# T\nAdd some water quickly.'
        rows = D.check(source, 'paper')['diagnostics']
        self.assertTrue(rows)
        self.assertTrue(all(row['position_kind'] == 'line' for row in rows))

    def test_limits_refuse_without_calling_checker(self):
        with patch.object(S, 'check', side_effect=AssertionError('checker must not start')):
            for source, language, code in ((None, 'native', 'EDITOR_SOURCE_TYPE'),
                                          ('x' * (D.MAX_BYTES + 1), 'native', 'EDITOR_SOURCE_LIMIT'),
                                          ('😀' * 100001, 'native', 'EDITOR_SOURCE_LIMIT'),
                                          ('show 1.', 'unknown', 'EDITOR_LANGUAGE')):
                with self.subTest(code=code):
                    reply = D.check(source, language)
                    self.assertFalse(reply['ok'])
                    self.assertEqual(reply['diagnostics'][0]['code'], code)

    def test_bad_unicode_and_internal_failure_are_not_valid_documents(self):
        reply = D.check('show "\ud800".')
        self.assertFalse(reply['available'])
        self.assertIsNone(reply['ok'])
        with patch.object(S, 'check', side_effect=RuntimeError('private checker details')):
            reply = D.check('show 1.')
        self.assertFalse(reply['available'])
        self.assertIsNone(reply['ok'])
        self.assertEqual(reply['diagnostics'][0]['code'], 'EDITOR_UNAVAILABLE')
        self.assertNotIn('private', str(reply))

    def test_many_diagnostics_are_bounded_with_explicit_truncation(self):
        source = '\n'.join(f'show missing{i}.' for i in range(D.MAX_DIAGNOSTICS + 3))
        reply = D.check(source)
        self.assertTrue(reply['truncated'])
        self.assertEqual(len(reply['diagnostics']), D.MAX_DIAGNOSTICS)
        self.assertEqual(len(reply['check']['warnings']), D.MAX_DIAGNOSTICS)

    def test_existing_plan_and_profile_are_preserved(self):
        source = 'given price: Int.\nshow price.'
        reply = D.check(source, execution_profile='verified')
        self.assertEqual(reply['check'], S.check(source, execution_profile='verified'))
        self.assertTrue(any(row.get('binds') == 'price' and row.get('required') for row in reply['check']['plan']))
        self.assertEqual(D.check('do something', execution_profile='verified')['ok'], False)
        self.assertTrue(D.check('do something')['ok'])

    def test_paper_honors_optional_stronger_host_profile(self):
        source = '# T\n```symblic\nDo something.\n```'
        self.assertTrue(D.check(source, 'paper')['ok'])
        self.assertFalse(D.check(source, 'paper', execution_profile='verified')['ok'])

    def test_invalid_profile_is_refused_without_source_check(self):
        with patch.object(S, 'check', side_effect=AssertionError('not called')):
            for profile in (False, [], 'anything'):
                self.assertEqual(D.check('show 1.', execution_profile=profile)['diagnostics'][0]['code'],
                                 'EDITOR_PROFILE')

    def test_source_check_has_no_dispatch_or_side_effects(self):
        with patch.object(RUN.Run, '__init__', side_effect=AssertionError('no Run')) as run, \
                patch.object(socket, 'socket', side_effect=AssertionError('no network')) as network, \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')) as process:
            for language, source in (
                    ('native', 'ask x: Int "pick 1".\nensure x > 0 else retry.\n'),
                    ('native', 'let x = js_run("throw new Error()", "1").\nshow x.'),
                    ('native', 'assert false.\nshow 1 / 0.'),
                    ('english', 'Remember x is 1.\nShow x.'),
                    ('paper', '# T\n```symblic\nask x: Int "pick 1".\n```')):
                with self.subTest(language=language, source=source):
                    self.assertTrue(D.check(source, language)['available'])
            run.assert_not_called()
            network.assert_not_called()
            process.assert_not_called()

    def test_existing_bounded_pure_static_lint_is_explicit(self):
        source = 'ask text: Text "Write something".\nensure len(text) >= 0 else retry.'
        reply = D.check(source)
        self.assertEqual(reply['scope']['static_lint'], 'existing_bounded_pure_predicate_probes')
        self.assertEqual(reply['check'], S.check(source))
        self.assertTrue(any(row['code'] == 'SYM_VACUOUS' for row in reply['diagnostics']))


if __name__ == '__main__':
    unittest.main()

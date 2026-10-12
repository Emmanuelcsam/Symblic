"""Actual parser conformance and bounded source-only authoring interfaces."""
import contextlib
import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.authoring import helpers as A
from symblic.adapters import proof as P
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W

ROOT = Path(__file__).resolve().parents[2]          # the repository root
FIXTURES = json.loads((ROOT / 'symblic/authoring/grammar/conformance.json').read_text())


def session(name='two-lines'):
    fixture = FIXTURES['sessions'][name]
    state = R.start(fixture['premises'], fixture['goal'])
    for command in fixture['prefix']:
        result = C.append(fixture['premises'], fixture['goal'], state, command)
        if not result['valid']:
            raise AssertionError(result)
        state = result['state']
    return state


class Authoring(unittest.TestCase):
    def test_published_conformance_cases_use_actual_parser_authorities(self):
        for case in FIXTURES['cases']:
            with self.subTest(case=case['id']):
                result = A.check(case['text'], entry=case['entry'], profile=case.get('profile', 'verified'),
                                 session=session(case['session']) if 'session' in case else None)
                self.assertEqual(result['ok'], case['parser_accepts'], result)
                self.assertEqual(result['inference_validity'], 'not_checked')
                self.assertEqual(result['proof_completion'], 'not_checked')
                self.assertEqual(result['execution'], 'not_run')
                self.assertEqual(result['provider_calls'], 0)

    def test_catalog_derives_actual_options_and_versions_and_is_detached(self):
        first = A.catalog()
        self.assertEqual(first['core']['ask_options'], list(S.ASK_OPTIONS))
        self.assertIn('capsule', first['core']['ask_options'])
        self.assertEqual(first['core']['use_options'], list(S.USE_OPTIONS))
        self.assertEqual(first['versions']['language'], S.VERSION)
        self.assertEqual(first['versions']['canonical'], S.CANON_VERSION)
        self.assertEqual(first['core']['operator_aliases'], S.CANON_OP)
        original = first['contract_id']
        first['core']['ask_options'].append('invented')
        self.assertEqual(A.catalog()['contract_id'], original)
        self.assertTrue(A.check(first['examples']['program'])['ok'])
        self.assertEqual(A.export_grammar('program')['ebnf_scope'], 'portable_authoring_subset')
        for entry in A.GRAMMARS:
            exported = A.export_grammar(entry)
            self.assertEqual(exported['ebnf_sha256'], A._sha(exported['text'].encode()))
            self.assertEqual(exported['authority'], A.AUTHORITY[entry])

    def test_syntax_acceptance_does_not_resolve_names_execute_or_check_predicates(self):
        with patch.object(S.Kernel, 'eval', side_effect=AssertionError('No evaluation')):
            for source in ('assert false.\n', 'let x = missing_name + 1.\n',
                           'let x = js_run("throw new Error()", "1").\n'):
                result = A.check(source)
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['execution'], 'not_run')

    def test_three_text_syntaxes_remain_distinct_and_exact(self):
        core = S.parse('let raw = "\\u0061".\n', execution_profile='verified')
        self.assertEqual(core['statements'][0].value.parts, ['\\u0061'])
        self.assertEqual(A.check('"\\u0061"', entry='formula')['formula'], ['atom', 'a'])
        for text in ('é', 'e\u0301', 'α 😀'):
            parsed = A.check(json.dumps(text, ensure_ascii=False), entry='formula')
            self.assertEqual(parsed['formula'], ['atom', text])
        self.assertNotEqual(P.parse_formula('"é"'), P.parse_formula('"e\\u0301"'))
        quoted = next(case for case in FIXTURES['cases'] if case['id'] == 'quoted-data')
        node = S.parse(quoted['text'], execution_profile='verified')['statements'][0]
        self.assertEqual(node.value.parts, ['# literal {ask x: Any}\nassert false.'])
        # Empty record, empty set and opaque empty proposition are three distinct values/forms.
        nodes = S.parse('let a={:}.\nlet b={}.\n', execution_profile='verified')['statements']
        self.assertEqual([node.value.k for node in nodes], ['record', 'set'])
        self.assertEqual(A.check('""', entry='formula')['formula'], ['atom', ''])

    def test_formula_precedence_matches_actual_right_associative_implication(self):
        value = A.check('"A" implies "B" implies "C" or "D" and not "E"', entry='formula')['formula']
        self.assertEqual(value, ['implies', ['atom', 'A'], ['implies', ['atom', 'B'],
            ['or', ['atom', 'C'], ['and', ['atom', 'D'], ['implies', ['atom', 'E'], ['false']]]]]])
        self.assertEqual(P.parse_formula(P.render_formula(value)), value)

    def test_all_eleven_command_forms_parse_without_inventing_arguments(self):
        state = session()
        commands = {'premise': 'premise p', 'assume': 'assume :: "Q"',
                    'implies_intro': 'implies_intro s1 s2', 'implies_elim': 'implies_elim s2 s1',
                    'and_intro': 'and_intro s1 s2', 'and_left': 'and_left s1', 'and_right': 'and_right s1',
                    'or_left': 'or_left s1 :: "Q"', 'or_right': 'or_right s1 :: "Q"',
                    'or_elim': 'or_elim s1 s1 s1 s2 s2', 'false_elim': 'false_elim s1 :: "Q"'}
        self.assertEqual(set(commands), set(W.ARITIES))
        for rule, command in commands.items():
            with self.subTest(rule=rule):
                result = A.check(command, entry='proof-command', session=state)
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['candidate']['rule'], rule)
                self.assertEqual(len(result['candidate']['args']), W.ARITIES[rule])
                self.assertEqual(result['candidate']['formula'] is not None, rule in W.FORMULA_RULES)

    def test_menu_keeps_invalid_inference_visible_for_unchanged_checker_to_reject(self):
        state = session()
        before = copy.deepcopy(state)
        choices = ['and_left s1', 'implies_elim s2 s1']
        with patch.object(R, 'append', side_effect=AssertionError('No new inference checking')):
            result = A.command_menu(state, choices)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['schema'], {'type': 'string', 'enum': choices})
        self.assertEqual(result['native_answer_schema']['properties']['answer'], result['schema'])
        self.assertEqual(result['inference_validity'], 'not_checked')
        self.assertEqual(result['proof_completion'], 'not_checked')
        self.assertEqual(result['provider_schema_support'], 'not_established')
        self.assertEqual(state, before)
        invalid = C.append(state['premises'], state['goal'], state, choices[0])
        valid = C.append(state['premises'], state['goal'], state, choices[1])
        self.assertFalse(invalid['valid'])
        self.assertTrue(valid['valid'] and valid['complete'])
        self.assertEqual(result['menu_id'], A.command_menu(state, choices)['menu_id'])
        self.assertNotEqual(result['menu_id'], A.command_menu(state, choices[::-1])['menu_id'])

    def test_menu_uses_one_original_session_and_preserves_exact_order_and_text(self):
        state = R.start({'p': ['atom', 'A']}, ['atom', 'B'])
        result = A.command_menu(state, ['premise p', 'and_left s1'])
        self.assertFalse(result['ok'])
        self.assertNotIn('schema', result)
        # The first command was not applied to make s1 exist for the second.
        self.assertEqual(state['steps'], [])
        commands = ['premise "p"', '\t premise p  ']
        result = A.command_menu(state, commands)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['schema']['enum'], commands)
        result['schema']['enum'].append('changed')
        self.assertEqual(A.command_menu(state, commands)['choices'], commands)
        maximum = ['premise p' + ' ' * count for count in range(A.MAX_MENU)]
        bounded = A.command_menu(state, maximum)
        self.assertTrue(bounded['ok'], bounded)
        self.assertEqual(len(bounded['schema']['enum']), A.MAX_MENU)

    def test_unknown_stale_completed_and_forged_sessions_refuse(self):
        state = session()
        bad = copy.deepcopy(state); bad['goal'] = ['atom', 'Changed']
        complete = C.append(state['premises'], state['goal'], state, 'implies_elim s2 s1')['state']
        for original in (None, {}, bad, complete):
            with self.subTest(session=original):
                result = A.check('premise p', entry='proof-command', session=original)
                self.assertFalse(result['ok'])
                self.assertEqual(result['reference_status'], 'not_established')
        for command in ('premise "missing"', 'and_left s3', 'and_left "s1"', 'and_left s01',
                        's3 = premise p', 'premise p # comment', '```premise p```'):
            self.assertFalse(A.check(command, entry='proof-command', session=state)['ok'])

    def test_input_bounds_precede_native_parser_or_reference_work(self):
        cyclic = []; cyclic.append(cyclic)
        too_deep = None
        for _ in range(A.MAX_DEPTH + 2):
            too_deep = [too_deep]
        with patch.object(C, 'parse', side_effect=AssertionError('Must preflight first')):
            for choices in ([], ['x'] * 33, ['premise p'] * 2, [True], ['😀' * 66000],
                            ['x' * (A.MAX_BYTES + 1)]):
                result = A.command_menu({}, choices)
                self.assertFalse(result['ok'], choices[:1])
            for invalid in (cyclic, too_deep, [None] * (A.MAX_NODES + 1), {1: 'key'}, {'x': 1.5}):
                self.assertFalse(A.check('premise p', entry='proof-command', session=invalid)['ok'])
        with patch.object(S, 'parse', side_effect=AssertionError('Must preflight first')):
            for text in (None, 'x' * (A.MAX_BYTES + 1), '😀' * 66000, '\ud800'):
                self.assertFalse(A.check(text)['ok'])

    def test_work_and_exact_byte_boundary_fail_explicitly(self):
        # ASCII source exactly on this interface's byte ceiling still reaches the actual parser.
        source = '# ' + 'x' * (A.MAX_BYTES - 3) + '\n'
        self.assertEqual(len(source.encode()), A.MAX_BYTES)
        self.assertTrue(A.check(source)['ok'])
        self.assertFalse(A.check(source + ' ')['ok'])
        with patch.object(A, 'MAX_WORK', 1):
            result = A.command_menu(session(), ['premise p'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'work_limit')
        deep = '(' * (P.MAX_DEPTH + 5) + '"A"' + ')' * (P.MAX_DEPTH + 5)
        self.assertFalse(A.check(deep, entry='formula')['ok'])

    def test_profiles_and_wrong_entry_options_do_not_silently_change_authority(self):
        for kwargs in ({'entry': 'invented'}, {'entry': ['program']}, {'profile': 'invented'},
                       {'entry': 'formula', 'profile': 'legacy'}, {'session': {}},
                       {'entry': 'formula', 'session': {}}):
            result = A.check('false', **kwargs)
            self.assertFalse(result['ok'], result)
        self.assertFalse(A.check('Describe something.')['ok'])
        self.assertTrue(A.check('Describe something.', profile='legacy')['ok'])

    def test_cli_catalog_export_check_and_menu_are_machine_readable_without_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, state, choices = root / 'p.sym', root / 'session.json', root / 'choices.json'
            code.write_text('let x={:}.\n')
            state.write_text(json.dumps(session()))
            choices.write_text(json.dumps(['and_left s1', 'implies_elim s2 s1']))
            for args in (['catalog', '--agent-json'], ['export', '--entry', 'formula', '--agent-json'],
                         ['check', str(code), '--agent-json'],
                         ['menu', str(choices), '--session', str(state), '--agent-json']):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = A.main(args)
                result = json.loads(out.getvalue())
                self.assertEqual(rc, 0, result)
            code.write_text('ask x: Bool missing_quotes.\n')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = A.main(['check', str(code), '--agent-json'])
            self.assertEqual(rc, 1)
            self.assertFalse(json.loads(out.getvalue())['ok'])
            # tools/symblic is the repository's command-line entry point; `grammar` dispatches to this module
            env = {**os.environ, 'PYTHONPATH': str(ROOT)}
            proc = subprocess.run([str(ROOT / 'tools/symblic'), 'grammar', 'catalog', '--agent-json'],
                                  cwd=ROOT, env=env, capture_output=True, text=True, timeout=20, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['version'], A.VERSION)

    def test_cli_preparser_errors_name_the_effective_parser_and_menu_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            choices, state, missing = root / 'choices.json', root / 'session.json', root / 'missing'
            choices.write_text('[broken')
            state.write_text(json.dumps(session()))
            cases = [(['check', str(missing), '--agent-json'], 'program'),
                     (['menu', str(choices), '--session', str(state), '--agent-json'], 'proof-command'),
                     (['menu', str(choices), '--session', str(missing), '--agent-json'], 'proof-command')]
            with patch.object(A.C, 'parse', side_effect=AssertionError('No parser before valid input')):
                for args, entry in cases:
                    out = io.StringIO()
                    with self.subTest(args=args), contextlib.redirect_stdout(out):
                        self.assertEqual(A.main(args), 1)
                    result = json.loads(out.getvalue())
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['entry'], entry)
                    self.assertEqual(result['authority'], A.AUTHORITY[entry])
                    self.assertEqual(result['execution'], 'not_run')
                    if entry == 'proof-command':
                        self.assertEqual(result['operation'], 'caller_authored_command_menu')
                        self.assertEqual(result['reference_status'], 'not_established')

    def test_cli_json_duplicates_large_files_and_nonregular_files_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / 'bad.json'
            bad.write_text('{"steps":[],"steps":[]}')
            with self.assertRaisesRegex(A.AuthoringError, 'repeat'):
                A._load_json(bad)
            bad.write_bytes('{"x":1}'.encode('utf-16'))
            with self.assertRaises(UnicodeError):
                A._load_json(bad)
            bad.write_bytes(b'x' * (A.MAX_BYTES + 1))
            with patch.object(os, 'fdopen', side_effect=AssertionError('Must reject before reading')), self.assertRaises(A.AuthoringError):
                A._read(bad)
            fifo = root / 'pipe'
            os.mkfifo(fifo)
            with self.assertRaisesRegex(A.AuthoringError, 'regular'):
                A._read(fifo)


if __name__ == '__main__':
    unittest.main()

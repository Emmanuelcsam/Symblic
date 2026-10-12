"""Command wire and unchanged checker agreement; pure/fake work only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import logic as L
from symblic.adapters import proof as P
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W
from symblic.kernel.run import Run

A, B, Z = ['atom', 'A'], ['atom', 'B'], ['atom', 'Z']
MP = {'a': A, 'rule': ['implies', A, B]}
TASK = {'premises': 'a: "A"\nrule: "A" implies "B"', 'goal': '"B"',
        'certificate_format': 'incremental', 'step_limit': 3, 'calls': 6}
COMMANDS = ['premise rule', 'premise a', 'implies_elim s1 s2']


def candidate(rule, *args, formula=None):
    return {'rule': rule, 'args': list(args), 'formula': formula}


JSON_MP = [candidate('premise', 'rule'), candidate('premise', 'a'), candidate('implies_elim', 's1', 's2')]


class Pure(unittest.TestCase):
    def compare(self, premises, goal, pairs):
        state = R.start(premises, goal)
        for command, expected in pairs:
            before = copy.deepcopy(state)
            self.assertEqual(C.parse(state, command), expected)
            result = C.append(premises, goal, state, command)
            direct = R.append(premises, goal, state, expected)
            self.assertEqual(result, direct)
            self.assertTrue(result['valid'], result)
            self.assertEqual(state, before)
            state = result['state']
        return result

    def test_all_eleven_rules_translate_to_identical_checked_candidates(self):
        result = self.compare(MP, B, list(zip(COMMANDS, JSON_MP)))
        self.assertEqual(result['receipt'], W.verify(MP, B, result['certificate']))
        formulas = {**MP, 'b': B, 'bottom': ['false']}
        pairs = [('premise a', candidate('premise', 'a')), ('premise b', candidate('premise', 'b')),
                 ('and_intro s1 s2', candidate('and_intro', 's1', 's2')),
                 ('and_left s3', candidate('and_left', 's3')), ('and_right s3', candidate('and_right', 's3')),
                 ('or_left s1 :: "B"', candidate('or_left', 's1', formula=B)),
                 ('or_right s2 :: "A"', candidate('or_right', 's2', formula=A)),
                 ('assume :: "A"', candidate('assume', formula=A)),
                 ('implies_intro s8 s4', candidate('implies_intro', 's8', 's4')),
                 ('premise bottom', candidate('premise', 'bottom')),
                 ('false_elim s10 :: "Z"', candidate('false_elim', 's10', formula=Z))]
        self.assertTrue(self.compare(formulas, Z, pairs)['complete'])
        premises = {'cases': ['or', A, B], 'az': ['implies', A, Z], 'bz': ['implies', B, Z]}
        commands = ['premise cases', 'premise az', 'premise bz', 'assume :: "A"',
                    'implies_elim s2 s4', 'assume :: "B"', 'implies_elim s3 s6',
                    'or_elim s1 s4 s5 s6 s7']
        expected = [candidate('premise', 'cases'), candidate('premise', 'az'), candidate('premise', 'bz'),
                    candidate('assume', formula=A), candidate('implies_elim', 's2', 's4'),
                    candidate('assume', formula=B), candidate('implies_elim', 's3', 's6'),
                    candidate('or_elim', 's1', 's4', 's5', 's6', 's7')]
        self.assertTrue(self.compare(premises, Z, list(zip(commands, expected)))['complete'])

    def test_command_and_json_reject_identical_inference_and_crossbranch_errors(self):
        state = R.start(MP, Z)
        for command in COMMANDS[:2]:
            state = C.append(MP, Z, state, command)['state']
        self.assertEqual(C.append(MP, Z, state, 'implies_elim s2 s1'),
                         R.append(MP, Z, state, candidate('implies_elim', 's2', 's1')))
        premises = {'cases': ['or', A, A]}
        state = R.start(premises, Z)
        for command in ('premise cases', 'assume :: "A"', 'assume :: "A"'):
            state = C.append(premises, Z, state, command)['state']
        bad = C.append(premises, Z, state, 'or_elim s1 s2 s3 s3 s3')
        self.assertEqual(bad, R.append(premises, Z, state, candidate('or_elim', 's1', 's2', 's3', 's3', 's3')))
        self.assertEqual(bad['error'], 'branch_scope')
        self.assertEqual(bad['state'], state)

    def test_formula_text_preserves_precedence_quoted_false_and_unicode(self):
        state = R.start({}, Z)
        for formula in ('"A" or "B" implies not "Z"', '"false"', 'false',
                        '"é"', '"e\\u0301"', '"任意 :: ; premise invented"', '"line\\nnext"'):
            with self.subTest(formula=formula):
                parsed = C.parse(state, 'assume :: ' + formula)
                self.assertEqual(parsed['formula'], P.parse_formula(formula))
        self.assertNotEqual(C.parse(state, 'assume :: "é"'), C.parse(state, 'assume :: "e\\u0301"'))

    def test_quoted_exact_premise_names_have_no_alias_or_case_folding(self):
        names = {'任意 name::x': A, 's1': B, 'UPPER': Z}
        state = R.start(names, ['atom', 'other'])
        for name in names:
            command = 'premise ' + json.dumps(name, ensure_ascii=False)
            self.assertEqual(C.parse(state, command), candidate('premise', name))
        self.assertEqual(C.parse(state, 'premise s1'), candidate('premise', 's1'))
        self.assertEqual(C.append(names, Z, R.start(names, Z), 'premise upper')['error'], 'unknown_premise')

    def test_invalid_arity_reference_and_unsupported_syntax_never_edit_state(self):
        state = R.start(MP, B)
        rows = ['premise', 'premise a rule', 'implies_elim s1', 'assume "A"',
                'and_intro s1 s2 :: "A"', 'assume :: "A" premise a', 'assume :: A',
                'assume :: ["atom","A"]', 's1 = premise a', 'premise a # comment',
                'premise a; premise rule', 'premise a\npremise rule', 'premise a\n',
                '```premise a```', 'PREMISE a', 'and_left s01', 'and_left S1', 'and_left "s1"',
                'premise a\u2028', 'premise a\u0085', 'premise a\x00']
        for command in rows:
            with self.subTest(command=repr(command)):
                result = C.append(MP, B, state, command)
                self.assertFalse(result['valid'])
                self.assertEqual(result['rejected'], 'candidate')
                self.assertEqual(result['state'], state)
        self.assertEqual(C.append(MP, B, state, 'premise invented')['error'], 'unknown_premise')
        self.assertEqual(C.append(MP, B, state, 'and_left s1')['error'], 'unknown_or_forward_reference')

    def test_untrusted_objects_and_foreign_or_tampered_sessions_refuse(self):
        state = R.start(MP, B)
        for value in (None, True, 1, [], {'rule': 'premise', 'args': ['a'], 'formula': None},
                      {'state': state, 'goal': A}):
            self.assertEqual(C.append(MP, B, state, value)['error'], 'command_type')
        self.assertEqual(C.append(MP, Z, state, 'premise a')['error'], 'sequent_mismatch')
        self.assertEqual(C.append(MP, Z, state, '\n')['rejected'], 'state')
        forged = copy.deepcopy(state); forged['hashes']['goal'] = '0' * 64
        result = C.append(MP, B, forged, 'premise a')
        self.assertEqual(result['rejected'], 'state')
        self.assertIsNone(result['state'])

    def test_completion_and_open_assumptions_keep_existing_semantics(self):
        state = R.start({}, A)
        open_line = C.append({}, A, state, 'assume :: "A"')
        self.assertTrue(open_line['valid'])
        self.assertFalse(open_line['complete'])
        self.assertEqual(open_line['line']['free'], ['s1'])
        closed = C.append({'a': A}, A, R.start({'a': A}, A), 'premise a')
        refused = C.append({'a': A}, A, closed['state'], 'malformed command')
        self.assertEqual(refused['error'], 'session_complete')
        self.assertTrue(refused['complete'])
        with self.assertRaisesRegex(P.ProofError, 'session_complete'):
            C.parse(closed['state'], 'premise a')

    def test_frontier_is_equal_information_and_rendering_roundtrips_line_separators(self):
        atom = ['atom', 'é\u2028next\u0085line\u2029end']
        state = R.start({'p': atom}, Z)
        state = C.append({'p': atom}, Z, state, 'premise p')['state']
        ordinary, command = R.frontier(state), C.frontier(state)
        restored = copy.deepcopy(command)
        restored['goal'] = P.parse_formula(restored['goal'])
        restored['premises'] = {name: P.parse_formula(text) for name, text in restored['premises'].items()}
        for line in restored['lines']:
            line['formula'] = P.parse_formula(line['formula'])
        self.assertEqual(restored, ordinary)
        self.assertEqual(C.parse(state, 'assume :: ' + command['lines'][0]['formula'])['formula'], atom)
        self.assertNotIn('certificate', command)

    def test_finite_wire_bounds_unicode_depth_and_host_budget(self):
        state = R.start({'p': A}, Z)
        with patch.object(C, 'MAX_COMMAND_BYTES', len('premise p')):
            self.assertTrue(C.append({'p': A}, Z, state, 'premise p')['valid'])
            self.assertEqual(C.append({'p': A}, Z, state, 'premise p ')['error'], 'byte_limit')
        self.assertEqual(C.append({'p': A}, Z, state, '\ud800')['error'], 'unicode')
        deep = 'assume :: ' + '(' * 80 + '"A"' + ')' * 80
        self.assertEqual(C.append({'p': A}, Z, state, deep)['error'], 'depth_limit')
        self.assertEqual(C.append({'p': A}, Z, state, 'assume :: "' + 'x' * (P.MAX_TEXT + 1) + '"')['error'], 'text_limit')
        with patch.object(C, 'MAX_FRONTIER_BYTES', 1), self.assertRaisesRegex(P.ProofError, 'output_limit'):
            C.frontier(state)

        def stop():
            raise RuntimeError('host budget')
        for function, args in ((C.parse, (state, 'premise p')), (C.append, ({'p': A}, Z, state, 'premise p')),
                               (C.frontier, (state,))):
            with self.assertRaisesRegex(RuntimeError, 'host budget'):
                function(*args, tick=stop)


class Apps:
    def __init__(self, answers):
        self.answers, self.requests = copy.deepcopy(answers), []

    def call(self, request):
        self.requests.append(request)
        if not self.answers:
            raise AssertionError('unexpected extra provider call')
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}}


def value(report, name):
    return next(row['value'] for row in report['bindings'] if row['name'] == name)


class Native(unittest.TestCase):
    def run_task(self, answers, **updates):
        task = {**TASK, 'inference_format': 'command', **updates}
        compiled = L.compile_task(task); apps = Apps(answers)
        with patch.object(S.KB, 'derive', side_effect=AssertionError('no solver')):
            report = Run(compiled['source'], compiled['inputs'], apps,
                         {**compiled['options'], 'by': 'fake:constructor'}).execute()
        return compiled, apps, report

    def test_equal_information_json_and_command_construct_identical_certificate(self):
        json_task, _, json_report = self.run_task(JSON_MP, inference_format='json')
        command_task, apps, command_report = self.run_task(COMMANDS)
        self.assertEqual(command_report['status'], 'done', command_report.get('error'))
        self.assertEqual(json_report['status'], 'done', json_report.get('error'))
        self.assertEqual(value(command_report, 'certificate'), value(json_report, 'certificate'))
        self.assertEqual(value(command_report, 'verification'), value(json_report, 'verification'))
        self.assertEqual(command_task['inputs']['premises'], json_task['inputs']['premises'])
        self.assertEqual(command_task['inputs']['goal'], json_task['inputs']['goal'])
        for index, request in enumerate(apps.requests, 1):
            self.assertEqual(request['schema']['properties']['answer']['type'], 'string')
            self.assertIn('answer value', request['prompt'])
            self.assertNotIn('no JSON object', request['prompt'])
            self.assertIn(f'"next_id": "s{index}"', request['prompt'])
            self.assertNotIn('"steps":', request['prompt'])

    def test_rejected_command_only_appears_in_its_repair_then_fresh_context(self):
        _, apps, report = self.run_task(['premise REJECTED_MARKER'] + COMMANDS)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertIn('REJECTED_MARKER', apps.requests[1]['prompt'])
        for request in apps.requests[2:]:
            self.assertNotIn('REJECTED_MARKER', request['prompt'])
        self.assertEqual(len(value(report, 'certificate')['steps']), 3)

    def test_syntax_failure_repairs_through_same_native_ensure(self):
        _, apps, report = self.run_task(['assume :: A'] + COMMANDS)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertIn('syntax', apps.requests[1]['prompt'])
        self.assertIn('Quote propositions', apps.requests[1]['prompt'])

    def test_assumption_and_finite_command_journeys(self):
        _, _, report = self.run_task(['assume :: "A"', 'implies_intro s1 s1'], premises='',
                                    goal='"A" implies "A"', step_limit=2)
        self.assertEqual(report['status'], 'done', report.get('error'))
        compiled, _, finite = self.run_task(['premise all', 'and_left s1'],
            premises='all: forall x in People: Kind(x:People)', goal='Kind(People["Ada"])',
            domains={'People': ['Ada', 'Ben']})
        self.assertEqual(finite['status'], 'done', finite.get('error'))
        self.assertIn('finite_steps_check(domains, premises, goal, certificate)', compiled['source'])
        self.assertTrue(value(finite, 'verification')['conditional_on_domains'])

    def test_shared_budget_incomplete_and_required_context_refuse(self):
        _, apps, report = self.run_task(['premise absent'] + COMMANDS[:2], calls=3)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual((len(apps.requests), report['calls']), (3, 3))
        self.assertNotIn('verification', [row['name'] for row in report['bindings']])
        _, _, report = self.run_task(COMMANDS[:2], step_limit=2)
        self.assertEqual(report['status'], 'failed')
        rows = [{'name': f'p{i}', 'formula': '"' + str(i) + 'x' * 3000 + '"'} for i in range(8)]
        _, apps, report = self.run_task([], premises=rows, goal=rows[0]['formula'])
        self.assertEqual((len(apps.requests), report['error']['kind']), (0, 'context'))

    def test_unchanged_final_checker_cannot_be_bypassed_by_command_completion(self):
        original = C.append

        def corrupt(*args, **kwargs):
            result = original(*args, **kwargs)
            if result['complete']:
                result['certificate']['steps'][-1]['args'] = ['invented']
            return result

        with patch.object(C, 'append', side_effect=corrupt):
            _, _, report = self.run_task(['premise a'], goal='"A"')
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(value(report, 'verification')['valid'])

    def test_default_legacy_formats_option_validation_and_identity(self):
        default = L.compile_task(TASK)
        explicit = L.compile_task({**TASK, 'inference_format': 'json'})
        command = L.compile_task({**TASK, 'inference_format': 'command'})
        self.assertEqual(default, explicit)
        self.assertNotEqual(default['formalization']['sha256'], command['formalization']['sha256'])
        for bad in (False, None, {}, 'commands', 'COMMAND'):
            with self.assertRaises(ValueError):
                L.compile_task({**TASK, 'inference_format': bad})
        for lane in ('terms', 'steps'):
            for wire in ('json', 'command'):
                with self.assertRaises(ValueError):
                    L.compile_task({'premises': '', 'goal': '"A"', 'certificate_format': lane, 'inference_format': wire})
        with self.assertRaises(ValueError):
            L.compile_task({**TASK, 'inference_format': 'command', 'command_options': {}})

    def test_delegation_catalog_pins_cli_inspection_and_recorded_format(self):
        request = {'template': 'proof', 'calls': 6,
                   'params': {key: val for key, val in {**TASK, 'inference_format': 'command'}.items() if key != 'calls'}}
        fixture = json.loads((Path(__file__).resolve().parent/'fixtures/incremental-command.task.json').read_text())
        self.assertEqual(fixture, request)
        checked = D.inspect_task(request)
        self.assertTrue(checked['ok'], checked)
        self.assertEqual(checked['formalization']['inference_format'], 'command')
        self.assertEqual(S.kernel_id()['proof_command'], C.VERSION)
        # The `symblic delegate check` command line wraps D.inspect_task (checked above); its own test lives with
        # the command-line tools.
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'record'
            receipt = H.run_task(request, applicators=Apps(COMMANDS), by='fake:constructor', folder=str(folder))
            self.assertTrue(receipt['accepted'], receipt.get('error'))
            meta = json.loads((folder/'meta.json').read_text())
            self.assertEqual(meta['delegation']['request']['params']['inference_format'], 'command')
            self.assertIn('symblic/adapters/proof_command.py', meta['options']['execution_pins']['python_hashes'])
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        validator = Draft202012Validator(D.catalog()['request_schema'])
        self.assertTrue(validator.is_valid(request))
        for wrong in ('terms', 'steps'):
            bad = copy.deepcopy(request); bad['params'].pop('step_limit'); bad['params']['certificate_format'] = wrong
            self.assertFalse(validator.is_valid(bad))
            self.assertFalse(D.inspect_task(bad)['ok'])


if __name__ == '__main__':
    unittest.main()

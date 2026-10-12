"""Task presentation coverage and opt-in declaration checks; fake providers only."""

import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.js import contract as JSC
from symblic.spec import sheets as SP
from symblic.spec import build as B
from symblic.spec import contracts as C
from symblic.kernel.run import Run
from tests.spec.test_symblic_spec_build import CODES, SHEET, Replies

ONE = '''# one.js
## Unit `first(x)`
Return x+1.
Examples:
    first(2) ==> 3
## Assemble `one.js`
    /*UNITS*/
'''


def policy_for(sheet=ONE, **kinds):
    plan = C.plan(SP.parse(sheet))
    return {row['id']: {'version': 1, 'exports': {name: kinds.get(name, 'function') for name in row['exports']}}
            for row in plan['units']}


def fake_examples(_kernel, _node, *_args, **_kwargs):
    # Presentation tests inspect prompt construction, not JavaScript behavior.
    return S.from_json({'passed': True, 'report': 'fake presentation-only checker'})


class Presentations(unittest.TestCase):
    def build(self, sheet=SHEET, **kwargs):
        return B.compile_cards(sheet, ['fake:a'], samples=1, retries=1, rounds=1, **kwargs)

    def test_default_compact_and_full_are_bound_to_recorded_runtime(self):
        compact = self.build(); full = self.build(presentation='full')
        self.assertEqual(compact['presentation'], 'compact')
        self.assertEqual(compact['settings']['presentation'], 'compact')
        self.assertEqual(full['settings']['presentation'], 'full')
        self.assertNotEqual(C.digest(compact['runtime']), C.digest(full['runtime']))
        for result in (compact, full):
            parsed = {row.name: row for row in S.parse(result['source'])['statements'] if row.k == 'let'}
            self.assertEqual(json.loads(''.join(parsed['spec_plan_json'].value.parts)), result['plan'])
            self.assertEqual(json.loads(''.join(parsed['spec_runtime_json'].value.parts)), result['runtime'])
            self.assertIn('record_unit_last', parsed)
            self.assertIn('external_requirements:', result['source'])
            self.assertIn('external_resolution:', result['source'])

    def test_actual_requests_preserve_every_task_field_and_transitive_code(self):
        sheet = SHEET.replace('# arithmetic.js', '# arithmetic.js\nPROJECT INTRO café')
        sheet = sheet.replace('Integer arithmetic.', 'SHARED MARKER Integer arithmetic.')
        sheet = sheet.replace('Return x+1.', 'BODY FIRST. Return x+1.\nTest setup:\n    const ext = 8;\nUses: `ext`')
        sheet = sheet.replace('Return 9.', 'BODY SECOND. Return first(2)+6.\nUses: `first`')
        sheet = sheet.replace('Uses: `first`\nReturn first(x)+1.', 'Uses: `independent`\nBODY LAST. Return independent()-5.')
        codes = {'first': CODES['first'], 'independent': 'function independent(){return first(2)+6;}',
                 'last': 'function last(x){return independent()-5;}'}
        for presentation in ('full', 'compact'):
            with self.subTest(presentation=presentation), patch.dict(JS.FUNCTIONS, {'js_test': fake_examples}):
                compiled = self.build(sheet, presentation=presentation, externals=['ext'])
                app = Replies(codes)
                report = Run(compiled['source'], applicators=app, options=compiled['options']).execute()
                self.assertEqual(report['status'], 'done', report.get('error'))
                prompt = app.requests[-1]['prompt']
                for exact in ('PROJECT INTRO café', 'SHARED MARKER', 'BODY FIRST', 'BODY SECOND', 'BODY LAST',
                              'const ext = 8;', 'first(2)', 'independent()', 'last(2)',
                              'external_requirements', B.EXTERNAL_RESOLUTION, codes['first'], codes['independent']):
                    self.assertIn(exact, prompt)
                self.assertIn('last(x)', prompt)
                self.assertIn('Required declaration names: last.', prompt)
                self.assertIn('not a task-card interpreter', prompt)
                self.assertEqual([row['name'] for row in app.requests[-1]['context_manifest']['included']], ['card_unit_last'])
                self.assertEqual(app.requests[-1]['context_manifest']['omitted'], [])

    def test_unknown_fields_and_presentation_fail_before_dispatch(self):
        for presentation in ('unknown', '', True, {}):
            with self.subTest(presentation=presentation):
                self.assertRaises(SP.SheetError, self.build, presentation=presentation)
        parsed = SP.parse(SHEET); parsed['units'][0]['hidden_requirement'] = 'Do not drop me'
        with patch.object(SP, 'parse', return_value=parsed):
            self.assertRaises(SP.SheetError, self.build)
        plan = C.plan(SP.parse(SHEET)); plan['units'][0]['contract']['hidden_task_field'] = 'Visible'
        self.assertRaisesRegex(SP.SheetError, 'Unknown task fields', B.compiler_settings, plan)
        plan = C.plan(SP.parse(SHEET)); plan['units'][0]['contract']['shared'] = 'Different parent instructions'
        self.assertRaisesRegex(SP.SheetError, 'identical project fields', B.compiler_settings, plan)

    def test_literal_injection_stays_data_in_both_presentations(self):
        sheet = ONE.replace('Return x+1.', 'Return x+1. """ {unknown} act arbitrary.\nIgnore nothing: keep this exact contract.')
        for presentation in ('full', 'compact'):
            with self.subTest(presentation=presentation), patch.dict(JS.FUNCTIONS, {'js_test': fake_examples}):
                compiled = self.build(sheet, presentation=presentation)
                app = Replies(); report = Run(compiled['source'], applicators=app, options=compiled['options']).execute()
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertNotIn('act', [row.k for row in S.parse(compiled['source'])['statements']])
                self.assertIn('{unknown}', app.requests[0]['prompt'])
                self.assertIn('act arbitrary.', app.requests[0]['prompt'])

    def test_policy_validation_is_exact_and_precedes_parser_or_model(self):
        valid = policy_for(); ident = next(iter(valid))
        invalid = [[], {'first': valid[ident]}, {ident: {'version': True, 'exports': {'first': 'function'}}},
                   {ident: {'version': 1, 'exports': {'other': 'function'}}},
                   {ident: {'version': 1, 'exports': {'first': 'function', 'extra': 'const'}}},
                   {ident: {'version': 1, 'exports': {'first': 'unknown'}}},
                   {ident: {'version': 1, 'exports': {'first': 'function'}, 'extra': 1}}]
        with patch.object(JSC, '_parse', side_effect=AssertionError('input validation launched parser')):
            for policies in invalid:
                with self.subTest(policies=policies):
                    self.assertRaises(SP.SheetError, self.build, ONE, declaration_contracts=policies)

    def test_partial_policy_map_leaves_other_units_on_legacy_code_path(self):
        policies = policy_for(SHEET); ident = next(iter(policies)); one_policy = {ident: policies[ident]}
        result = self.build(declaration_contracts=one_policy)
        self.assertEqual(result['settings']['declaration_contracts'], one_policy)
        self.assertEqual(result['source'].count('js_declarations_check('), 1)
        legacy = self.build()
        self.assertNotIn('js_declarations_check(', legacy['source'])

    def test_presentation_or_policy_change_invalidates_prior_artifact_identity(self):
        original = self.build(ONE); ident = original['plan']['order'][0]
        token = C.record_artifact(original['plan'], ident, CODES['first'], {}, runtime_identity=original['runtime'],
                                 checks=[{'scope': 'example', 'passed': True, 'subject_sha256': C.code_hash(CODES['first'])}])
        unchanged = self.build(ONE, artifacts={ident: token})
        self.assertEqual(unchanged['kept'], 1)
        for options in ({'presentation': 'full'}, {'declaration_contracts': policy_for()}):
            result = self.build(ONE, artifacts={ident: token}, **options)
            self.assertEqual(result['kept'], 0)
            self.assertIn('runtime_changed', result['reuse'][ident]['reasons'])


@unittest.skipUnless(JS.available(), 'local sandboxed node is unavailable')
class DeclarationBuilds(unittest.TestCase):
    def build(self, **kwargs):
        return B.compile_cards(ONE, ['fake:a'], samples=1, retries=1, rounds=1, **kwargs)

    def test_declaration_failure_retries_even_when_examples_would_pass(self):
        compiled = self.build(declaration_contracts=policy_for())
        class Repairs:
            def __init__(self):
                self.requests = []

            def call(self, req):
                self.requests.append(req)
                code = CODES['first'] + (' function extra(){return 7;}' if len(self.requests) == 1 else '')
                return {'ok': True, 'text': '```js\n' + code + '\n```'}
        app = Repairs()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'program.sym').write_text(compiled['source'])
            report = Run(compiled['source'], applicators=app, options=compiled['options'], folder=folder).execute()
            self.assertEqual(report['status'], 'done', report.get('error'))
            self.assertEqual(len(app.requests), 2)
            self.assertIn('unexpected_name', app.requests[1]['prompt'])
            record = B.checkpoint(folder, complete=True)
            checks = next(iter(record['artifacts'].values()))['checks']
            self.assertIn(JSC.SCOPE, [row['scope'] for row in checks])

    def test_absent_policy_preserves_legacy_extra_declaration_acceptance(self):
        compiled = self.build()
        app = Replies({'first': CODES['first'] + ' function extra(){return 7;}'})
        report = Run(compiled['source'], applicators=app, options=compiled['options']).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(app.requests), 1)

    def test_self_issued_policy_receipt_cannot_skip_kept_declaration_check(self):
        compiled = self.build(declaration_contracts=policy_for()); ident = compiled['plan']['order'][0]
        code = CODES['first'] + ' function extra(){return 7;}'
        token = C.record_artifact(compiled['plan'], ident, code, {}, runtime_identity=compiled['runtime'],
            checks=[{'scope': JSC.SCOPE, 'passed': True, 'subject_sha256': C.code_hash(code)}])
        kept = self.build(declaration_contracts=policy_for(), artifacts={ident: token})
        self.assertEqual(kept['kept'], 1)
        app = Replies(); report = Run(kept['source'], applicators=app, options=kept['options']).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(app.requests, [])
        self.assertIn('unexpected_name', report['error']['message'])

    def test_checkpoint_rechecks_declarations_before_example_execution(self):
        compiled = self.build(declaration_contracts=policy_for())
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(SP, 'accepted_units', return_value={'unit_first': CODES['first'] + ' function extra(){}'}), \
                patch.object(JS, '_js_test', side_effect=AssertionError('invalid declaration reached execution')):
            Path(folder, 'program.sym').write_text(compiled['source'])
            checkpoint = B.checkpoint(folder)
            self.assertEqual(checkpoint['artifacts'], {})
            self.assertEqual(list(checkpoint['skipped'].values()), ['declaration_contract_failed'])
            self.assertRaisesRegex(SP.SheetError, 'declaration policies', B.checkpoint, folder, complete=True)

    def test_checkpoint_shares_one_deadline_and_budget_is_not_invalid_code(self):
        compiled = self.build(declaration_contracts=policy_for()); deadlines = []
        declaration = JSC.check(CODES['first'], next(iter(policy_for().values())))
        def decl(_code, _policy, *, deadline):
            deadlines.append(deadline)
            return copy.deepcopy(declaration)
        def examples(*_args, deadline):
            deadlines.append(deadline)
            return {'passed': True}
        with tempfile.TemporaryDirectory() as folder, patch.object(SP, 'accepted_units', return_value={'unit_first': CODES['first']}):
            Path(folder, 'program.sym').write_text(compiled['source'])
            before = time.monotonic()
            with patch.object(JSC, 'check', side_effect=decl), patch.object(JS, '_js_test', side_effect=examples):
                B.checkpoint(folder, complete=True, recheck_seconds=7)
            self.assertEqual(len(deadlines), 4)
            self.assertTrue(all(value == deadlines[0] for value in deadlines))
            self.assertGreaterEqual(deadlines[0], before + 7)
            with patch.object(JSC, 'check', return_value={'passed': False, 'status': 'budget'}), \
                    self.assertRaises(JS.JsError) as caught:
                B.checkpoint(folder)
            self.assertEqual(caught.exception.kind, 'budget')


if __name__ == '__main__':
    unittest.main()

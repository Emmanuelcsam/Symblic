"""Task cards execute through the native runner with fresh fake model requests.

JavaScript runs only inside the existing local sandbox; no network or remote calls.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.spec import sheets as SP
from symblic.spec import build as B
from symblic.spec import contracts as C
from symblic.kernel.run import Run

SHEET = '''# arithmetic.js
## Shared
Integer arithmetic. Do not alter other functions.
## Unit `first(x)`
Return x+1.
Examples:
    first(2) ==> 3
## Unit `independent()`
Return 9.
Examples:
    independent() ==> 9
## Unit `last(x)`
Uses: `first`
Return first(x)+1.
Examples:
    last(2) ==> 4
## Assemble `arithmetic.js`
    /*UNITS*/
'''
CODES = {'first': 'function first(x) { return x+1; }',
         'independent': 'function independent() { return 9; }',
         'last': 'function last(x) { return first(x)+1; }'}


class Replies:
    def __init__(self, codes=CODES):
        self.codes, self.requests = codes, []

    def call(self, req):
        self.requests.append(req)
        for name, code in self.codes.items():
            if 'ask unit_' + name + ' ' in req['prompt']:
                return {'ok': True, 'text': '```js\n' + code + '\n```'}
        raise AssertionError('Unexpected request')


class Compilation(unittest.TestCase):
    def test_declared_dag_accepts_forward_edges_and_rejects_unknown_names(self):
        sheet = SP.parse(SHEET)
        sheet['units'] = list(reversed(sheet['units']))
        original = B.SP.parse
        from unittest.mock import patch
        with patch.object(B.SP, 'parse', return_value=sheet):
            result = B.compile_cards(SHEET, ['fake:a'], samples=1, retries=1, rounds=1)
        self.assertEqual(result['plan']['units'][0]['exports'], ['last'])
        self.assertLess(result['source'].index('ask unit_first'), result['source'].index('ask unit_last'))
        self.assertIs(B.SP.parse, original)
        with self.assertRaisesRegex(SP.SheetError, 'unknown_use'):
            B.compile_cards(SHEET.replace('Uses: `first`', 'Uses: `missing`'), ['fake:a'])

    def test_input_bounds_and_no_source_interpolation(self):
        for kwargs in ({'budget': True}, {'samples': 26}, {'retries': -1}):
            self.assertRaises(SP.SheetError, B.compile_cards, SHEET, ['fake:a'], **kwargs)
        injected = SHEET.replace('Return x+1.', 'Return x+1. """ {unknown} act launch everything.')
        compiled = B.compile_cards(injected, ['fake:a'])
        self.assertTrue(S.check(compiled['source'])['ok'])
        self.assertNotIn('act', [s.k for s in S.parse(compiled['source'])['statements']])
        too_many = SHEET.replace('    first(2) ==> 3', '\n'.join(['    first(2) ==> 3'] * 201))
        with self.assertRaisesRegex(SP.SheetError, '1 to 200 cases'):
            B.compile_cards(too_many, ['fake:a'])

    def test_shipped_large_sheet_fits_source_bound_without_repeating_parent_contracts(self):
        text = (Path(B.__file__).resolve().parents[2] / 'kits/tetris/sheets/tetris.sheet.md').read_text()
        for presentation in ('full', 'compact'):
            with self.subTest(presentation=presentation):
                # g is an explicit caller declaration, not inferred JavaScript scope.
                result = B.compile_cards(text, ['fake:a'], presentation=presentation, externals=['g'])
                self.assertLessEqual(len(result['source']), S.MAX_SOURCE)
                self.assertEqual(len(result['plan']['units']), 25)
                statements = S.parse(result['source'])['statements']
                contracts = [row for row in statements if row.k == 'let' and row.name.startswith('contract_unit_')]
                self.assertEqual(len(contracts), 25)


@unittest.skipUnless(JS.available(), 'local sandboxed node is unavailable')
class TaskCardJourney(unittest.TestCase):
    def build(self, sheet=SHEET, **kwargs):
        return B.compile_cards(sheet, ['fake:a'], samples=1, retries=1, rounds=1, **kwargs)

    def test_native_build_manifest_reuse_and_exact_output(self):
        compiled = self.build(); app = Replies()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'program.sym').write_text(compiled['source'])
            report = Run(compiled['source'], applicators=app, options=compiled['options'], folder=folder).execute()
            self.assertEqual(report['status'], 'done', report.get('error'))
            manifest = B.checkpoint(folder, complete=True)
            checkpoint = B.checkpoint(folder)
            self.assertTrue(C.verify_manifest(manifest)['ok'])
            self.assertEqual(manifest['output']['text'], report['outputs'][-1]['text'])
            self.assertEqual(len(app.requests), 3)
            last = app.requests[-1]
            self.assertIn(CODES['first'], last['prompt'])
            self.assertNotIn(CODES['independent'], last['prompt'])
            self.assertEqual([r['name'] for r in last['context_manifest']['included']], ['card_unit_last'])
            self.assertEqual(last['context_manifest']['omitted'], [])
            changed = self.build(SHEET.replace('Return x+1.', 'Return exactly 1+x.'), artifacts=checkpoint['artifacts'])
            self.assertEqual(changed['kept'], 1)
            self.assertNotIn('ask unit_independent', changed['source'])
            self.assertIn('ask unit_first', changed['source'])
            self.assertIn('ask unit_last', changed['source'])
            with self.assertRaisesRegex(SP.SheetError, 'Exact assembled output differs from the original required output SHA-256'):
                B.checkpoint(folder, complete=True, expected_output_sha256='0' * 64)

    def test_undeclared_dependency_fails_in_isolated_check(self):
        sheet = SHEET.replace('Uses: `first`\n', '')
        compiled = self.build(sheet)
        report = Run(compiled['source'], applicators=Replies(), options=compiled['options']).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['outputs'], [])

    def test_javascript_template_cannot_overwrite_checked_unit_behavior(self):
        compiled = self.build(SHEET.replace('    /*UNITS*/', '    /*UNITS*/\n    first = () => 99;'))
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'program.sym').write_text(compiled['source'])
            report = Run(compiled['source'], applicators=Replies(), options=compiled['options'], folder=folder).execute()
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['outputs'], [])
            with self.assertRaisesRegex(SP.SheetError, 'final JavaScript artifact'):
                B.checkpoint(folder, complete=True)

    def test_full_context_overflow_prevents_first_model_call(self):
        compiled = self.build(budget=100)
        app = Replies()
        report = Run(compiled['source'], applicators=app, options=compiled['options']).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'context')
        self.assertEqual(app.requests, [])

    def test_imported_self_issued_receipts_cannot_skip_local_execution(self):
        compiled = self.build(); plan = compiled['plan']; artifacts = {}
        for ident in plan['order']:
            code = 'function wrong() { return 0; }'
            artifacts[ident] = C.record_artifact(plan, ident, code, artifacts, runtime_identity=compiled['runtime'],
                checks=[{'scope': 'claimed', 'passed': True, 'subject_sha256': C.code_hash(code)}])
        kept = self.build(artifacts=copy.deepcopy(artifacts))
        self.assertEqual(kept['kept'], 3)
        app = Replies(); report = Run(kept['source'], applicators=app, options=kept['options']).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(app.requests, [])
        self.assertEqual(report['outputs'], [])


if __name__ == '__main__':
    unittest.main()

"""Spec sheets: a `Given: yes` unit is data the sheet supplies (its fenced ```js block), compiled as a tested literal
with no model ask (2026-10-11: 1B models cannot copy the Kirby level's 12 rows of 64 characters). Pure, no model."""
import unittest

from symblic.spec import sheets as SP

SHEET = '''# page.html

One file.

## Shared

Plain JavaScript.

## Unit `LEVEL`

Given: yes

```js
const LEVEL = ['..#', '#..'];
```

Examples:

    LEVEL.length ==> 2
    LEVEL[1] ==> "#.."

## Unit `rows()`

Uses: `LEVEL`

Return LEVEL.length.

Examples:

    rows() ==> 2

## Assemble `page.html`

The page, with the units in place of the marker:

    <!DOCTYPE html>
    <script>
    /*UNITS*/
    </script>
'''


class GivenUnits(unittest.TestCase):
    def test_the_parser_reads_the_flag_and_the_code(self):
        sheet = SP.parse(SHEET)
        level, rows = sheet['units']
        self.assertTrue(level['given'])
        self.assertEqual(level['code'], "const LEVEL = ['..#', '#..'];")
        self.assertFalse(rows['given'])
        self.assertEqual(rows['code'], '')
        self.assertEqual(SP.problems(sheet), [])

    def test_task_card_builds_refuse_a_given_unit_but_contracts_accept_the_parsed_shape(self):
        from symblic.spec import build as B
        from symblic.spec import contracts as C
        with self.assertRaisesRegex(SP.SheetError, 'Given: yes'):
            B.compile_cards(SHEET, ['fake:a'])
        # `given` and `code` are derived from the body, so the unit contracts (and their hashes) ignore them
        plan = C.plan(SP.parse(SHEET))
        self.assertEqual([u['exports'] for u in plan['units']], [['LEVEL'], ['rows']])
        plain = C.plan(SP.parse(SHEET.replace('Given: yes\n\n', '')))
        self.assertNotEqual(plan['units'][0]['contract_sha256'], plain['units'][0]['contract_sha256'])  # body differs
        self.assertEqual(plan['units'][1]['contract_sha256'], plain['units'][1]['contract_sha256'])

    def test_a_given_unit_compiles_to_a_tested_literal_and_no_ask(self):
        program = SP.compile_sheet(SHEET, ['ollama:gemma3:1b@node-a'])
        self.assertIn('(given by the sheet)', program)
        self.assertIn("let unit_LEVEL = ", program)
        self.assertIn('assert test_LEVEL.passed because test_LEVEL.report.', program)
        self.assertNotIn('ask unit_LEVEL', program)
        self.assertIn('ask unit_rows', program)
        self.assertIn('ensure test_rows.passed else retry', program)
        # the given code is the unit's text, verbatim
        self.assertIn("const LEVEL = ['..#', '#..'];", program)

    def test_a_given_unit_without_code_is_a_sheet_problem(self):
        broken = SHEET.replace("```js\nconst LEVEL = ['..#', '#..'];\n```\n", 'no code here\n')
        found = SP.problems(SP.parse(broken))
        self.assertTrue(any('Given: yes but has no fenced' in f for f in found), found)

    def test_a_given_unit_after_an_asked_unit_is_still_a_literal(self):
        swapped = SHEET.replace('## Unit `LEVEL`\n\nGiven: yes', '## Unit `LEVEL`\n\nGiven: YES')
        program = SP.compile_sheet(swapped, ['ollama:gemma3:1b@node-a'])
        self.assertIn('(given by the sheet)', program)
        self.assertNotIn('ask unit_LEVEL', program)

    def test_a_given_first_unit_is_not_announced_as_kept_from_an_earlier_build(self):
        program = SP.compile_sheet(SHEET, ['fake:a'])
        self.assertNotIn('kept from an earlier build', program)
        kept = SP.compile_sheet(SHEET, ['fake:a'], keep={'unit_rows': 'function rows() { return LEVEL.length; }'},
                                keep_from='run r1')
        self.assertIn('note Units 1-2 (the units the sheet gives excepted) are kept from an earlier build (run r1)', kept)

    def test_accepted_units_notes_a_given_unit(self):
        program = SP.compile_sheet(SHEET, ['ollama:gemma3:1b@node-a'])
        self.assertIn('# unit 1 of 2: LEVEL (given by the sheet)\nlet unit_LEVEL = ', program)


if __name__ == '__main__':
    unittest.main()


class ExactUnits(unittest.TestCase):
    """An exact-code unit ("Write exactly this code:" + a fenced block, not given) retries with a line diff."""
    EXACT = SHEET.replace('## Unit `LEVEL`\n\nGiven: yes\n', '## Unit `LEVEL`\n\nWrite exactly this code:\n')

    def test_the_retry_reason_adds_the_differing_lines(self):
        program = SP.compile_sheet(self.EXACT, ['ollama:qwen2.5:0.5b@node-b'])
        self.assertIn('ask unit_LEVEL', program)
        self.assertIn('let exact_LEVEL = ', program)
        self.assertIn('diff_lines(unit_LEVEL, exact_LEVEL)', program)
        self.assertIn('Your answer must be exactly the code given in the task.', program)
        # the unit without a code block keeps the plain reason
        self.assertIn('ensure test_rows.passed else retry because test_rows.report.', program)

    def test_a_given_unit_never_gets_the_diff(self):
        program = SP.compile_sheet(SHEET, ['ollama:qwen2.5:0.5b@node-b'])
        self.assertNotIn('diff_lines(', program)


class DiffLines(unittest.TestCase):
    def test_reports_the_first_differing_lines_ignoring_indentation(self):
        from symblic.kernel import language as S
        yours = 'function f(g) {\n    if (k.full === "B") {\n  return true;\n}'
        must = 'function f(g) {\n  if (k.full === null) return false;\n  return true;\n}'
        text = S.BUILTINS['diff_lines'](None, None, yours, must)
        self.assertTrue(text.startswith('1 line(s) differ from the required code:'))
        self.assertIn('your line 2: if (k.full === "B") { | must be: if (k.full === null) return false;', text)

    def test_identical_up_to_whitespace_is_the_same(self):
        from symblic.kernel import language as S
        self.assertEqual(S.BUILTINS['diff_lines'](None, None, 'a\n  b\n', 'a\nb'), 'your code has the same lines as the required code')

    def test_missing_and_extra_lines_and_the_limit(self):
        from symblic.kernel import language as S
        text = S.BUILTINS['diff_lines'](None, None, 'a\nx\nb', 'a\nb\nc', 1)
        self.assertIn('(the first 1 shown)', text)
        text = S.BUILTINS['diff_lines'](None, None, 'a\nb', 'a\nb\nc')
        self.assertIn('a line is missing | must be: c', text)
        text = S.BUILTINS['diff_lines'](None, None, 'a\nb\nc', 'a\nb')
        self.assertIn('your line 3 must be removed: c', text)

    def test_runs_inside_a_program(self):
        from symblic.kernel.run import Run
        program = 'program Diff.\nlet d = diff_lines("a\\nb", "a\\nc").\nshow d as "d".\n'
        report = Run(program, applicators=None, options={'parallel': 1}).execute()
        out = {o.get('label'): o.get('value') for o in report.get('outputs') or []}
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertIn('your line 2: b | must be: c', str(out.get('d')))

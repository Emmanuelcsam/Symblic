"""`Used units shown as: signatures` names a unit's helpers in its prompt instead of pasting their code."""
import unittest

from symblic.spec import sheets as SP

SHEET = """# tiny.html

Used units shown as: signatures

## Shared

Plain JavaScript functions.

## Unit `strong(s)`

Return `s.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')`.

Examples:

    strong('a **b**') ==> "a <strong>b</strong>"

## Unit `strongEm(s)`

Uses: `strong`

Return `strong(s)`.

Examples:

    strongEm('**b**') ==> "<strong>b</strong>"

## Assemble `tiny.html`

    <script>
    /*UNITS*/
    </script>
"""


class UsesShown(unittest.TestCase):
    def test_signatures_mode_names_the_helpers_and_pastes_no_code(self):
        sheet = SP.parse(SHEET)
        self.assertEqual(sheet['uses_shown'], 'signatures')
        self.assertNotIn('Used units shown as', sheet['intro'] + sheet['shared'])
        prompt = SP.prompt_text(sheet, 1, {'sheet_shared': 'SHARED', 'unit_strong': 'function strong(s) { return s; }'})
        self.assertIn('The functions `strong(s)` already exist and work; call them.', prompt)
        self.assertNotIn('function strong', prompt)
        self.assertNotIn('```js', prompt)
        self.assertNotIn('must not', prompt)      # a prohibition reads as "do not call them" to a 1B model

    def test_the_default_still_pastes_the_tested_code(self):
        sheet = SP.parse(SHEET.replace('Used units shown as: signatures\n\n', ''))
        self.assertEqual(sheet.get('uses_shown', 'code'), 'code')
        prompt = SP.prompt_text(sheet, 1, {'sheet_shared': 'SHARED', 'unit_strong': 'function strong(s) { return s; }'})
        self.assertIn('Already in the file before your code', prompt)
        self.assertIn('function strong(s) { return s; }', prompt)

    def test_the_directive_is_refused_inside_a_unit(self):
        sheet = SP.parse(SHEET.replace('Used units shown as: signatures\n\n', '').replace('Uses: `strong`', 'Used units shown as: signatures\nUses: `strong`'))
        self.assertNotIn('uses_shown', sheet)      # inside a unit it is contract text, not a directive
        self.assertIn('Used units shown as', sheet['units'][1]['body'])

    def test_the_compiled_program_carries_the_mode(self):
        source = SP.compile_sheet(SHEET, ['ollama:gemma3:1b'], samples=1, retries=1, rounds=1)
        self.assertIn('The functions `strong(s)` already exist and work; call them.', source)
        self.assertNotIn('{unit_strong}\n```', source)
        self.assertIn('js_test([unit_strong, unit_strongEm]', source)   # the tests still run after the helper's code


if __name__ == '__main__':
    unittest.main()

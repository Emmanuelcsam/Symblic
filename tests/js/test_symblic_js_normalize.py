"""`Code js unit NAME reusing A, B`: a small model's answer is normalized by code before it is tested or assembled.

No model: the normalizer is pure text plus the pinned Acorn parser in a local node process. The three repairs are
the ones 0.5B-1B workers needed on 2026-10-10: the fenced block that declares the unit, a dropped `function`
keyword, and the candidate's own copies of helpers earlier units already declared."""
import unittest

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.js import normalize as N
from symblic.spec import sheets as SP
from symblic.spec import contracts as C

HAS_NODE = bool(JS.node_path())

SHEET = """# tiny.html

Answers normalized: yes

## Shared

Plain JavaScript functions.

## Unit `escapeHtml(s)`

Return `s.replace(/&/g, '&amp;')`.

Examples:

    escapeHtml('a&b') ==> "a&amp;b"

## Unit `renderCodeSpan(part)`

Uses: `escapeHtml`

Return `'<code>' + escapeHtml(part.slice(1, -1)) + '</code>'`.

Examples:

    renderCodeSpan('`a&b`') ==> "<code>a&amp;b</code>"

## Assemble `tiny.html`

    <script>
    /*UNITS*/
    </script>
"""

COPY = ("Here you go:\n```js\nfunction renderCodeSpan(part) {\n  return '<code>' + escapeHtml(part.slice(1, -1)) + '</code>';\n}\n\n"
        "function escapeHtml(s) {\n  return s.replace(/&/g, '&amp;');\n}\n```\n")


class TypeSyntax(unittest.TestCase):
    def test_the_unit_and_reusing_clauses_parse_and_label(self):
        src = 'ask x: Code js unit renderCodeSpan reusing escapeHtml, strong "write it".\nshow x.\n'
        self.assertTrue(S.check(src)['ok'], S.check(src).get('errors'))
        prog = S.parse(src)
        ty = next(st for st in prog['statements'] if st.k == 'ask').type
        self.assertEqual(ty['names'], ['renderCodeSpan'])
        self.assertEqual(ty['given'], ['escapeHtml', 'strong'])
        self.assertEqual(S.type_label(ty), 'Code js unit renderCodeSpan reusing escapeHtml, strong')

    def test_a_plain_code_answer_is_unchanged(self):
        src = 'ask x: Code js "write it".\nshow x.\n'
        self.assertTrue(S.check(src)['ok'])
        ty = next(st for st in S.parse(src)['statements'] if st.k == 'ask').type
        self.assertEqual(set(ty), {'k', 'lang'})


class Normalizer(unittest.TestCase):
    def test_the_block_that_declares_the_unit_wins_and_a_dropped_keyword_is_restored(self):
        reply = "```js\ninline(s) { return s.split(/(`[^`]+`)/).map(inlinePart).join(''); }\n```\n...\n```js\n``\n```"
        self.assertEqual(N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['inline'], 'given': ['inlinePart']}),
                         "function inline(s) { return s.split(/(`[^`]+`)/).map(inlinePart).join(''); }")

    def test_an_answer_that_only_calls_the_helpers_is_untouched(self):
        reply = "```js\nfunction strongEm(s) {\n  return em(strong(s));\n}\n```"
        self.assertEqual(N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['strongEm'], 'given': ['strong', 'em']}),
                         'function strongEm(s) {\n  return em(strong(s));\n}')

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_copies_of_reused_helpers_are_cut_and_nothing_else(self):
        out = N.normalize(COPY, {'k': 'code', 'lang': 'js', 'names': ['renderCodeSpan'], 'given': ['escapeHtml']})
        self.assertEqual(out, "function renderCodeSpan(part) {\n  return '<code>' + escapeHtml(part.slice(1, -1)) + '</code>';\n}")
        mixed = "```js\nconst a = 1, b = 2;\nconst escapeHtml = (s) => s;\nfunction f() { return a; }\n```"
        out = N.normalize(mixed, {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': ['a', 'escapeHtml']})
        self.assertEqual(out, 'const a = 1, b = 2;\nfunction f() { return a; }')   # a mixed declaration stays

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_a_unit_declared_twice_keeps_its_function_declaration(self):
        twice = "```js\nconst isUlBlock = (block) => block.every((l) => l.startsWith('- '));\n\nfunction isUlBlock(block) { return block.every((l) => l.startsWith('- ')); }\n```"
        out = N.normalize(twice, {'k': 'code', 'lang': 'js', 'names': ['isUlBlock'], 'given': ['isQuoteBlock']})
        self.assertEqual(out, "function isUlBlock(block) { return block.every((l) => l.startsWith('- ')); }")
        once = N.normalize("```js\nconst f = (x) => x;\n```", {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': []})
        self.assertEqual(once, 'const f = (x) => x;')

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_bare_assignments_become_declarations_and_reassigned_helpers_are_cut(self):
        reply = "```js\nrenderList = function(block, ordered) {\n  const tag = ordered ? 'ol' : 'ul';\n  return '<' + tag + '>\\n' + block.map(listItem).join('\\n') + '\\n</' + tag + '>';\n}\n\nlistItem = function(line) {\n  return line;\n}\n```"
        out = N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['renderList'], 'given': ['listItem', 'inline']})
        self.assertTrue(out.startswith('const renderList = function(block, ordered) {'), out)
        self.assertNotIn('listItem = function', out)
        both = N.normalize("```js\nfunction f(x) { return x; }\nf = (x) => 0;\n```", {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': []})
        self.assertEqual(both, 'function f(x) { return x; }')      # the declaration wins over a later reassignment

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_unparseable_code_is_left_for_the_tests_to_report(self):
        broken = "```js\nfunction renderCodeSpan(part) {\nfunction escapeHtml(s) { return s; }\n```"
        out = N.normalize(broken, {'k': 'code', 'lang': 'js', 'names': ['renderCodeSpan'], 'given': ['escapeHtml']})
        self.assertIn('function escapeHtml', out)

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_read_answer_applies_it_only_for_a_unit_type(self):
        unit = {'k': 'code', 'lang': 'js', 'names': ['renderCodeSpan'], 'given': ['escapeHtml']}
        value, _ = S.read_answer(COPY, unit)
        self.assertNotIn('function escapeHtml', value)
        plain, _ = S.read_answer(COPY, {'k': 'code', 'lang': 'js'})
        self.assertIn('function escapeHtml', plain)


class Compiler(unittest.TestCase):
    def test_the_directive_asks_every_unit_as_a_normalized_type_with_the_earlier_names(self):
        sheet = SP.parse(SHEET)
        self.assertTrue(sheet['normalize'])
        self.assertNotIn('Answers normalized', sheet['intro'] + sheet['shared'])
        source = SP.compile_sheet(SHEET, ['ollama:gemma3:1b'], samples=1, retries=1, rounds=1)
        self.assertIn('ask unit_escapeHtml: Code js unit escapeHtml """', source)
        self.assertIn('ask unit_renderCodeSpan: Code js unit renderCodeSpan reusing escapeHtml """', source)
        self.assertIn('js_test([unit_escapeHtml, unit_renderCodeSpan]', source)
        self.assertTrue(S.check(source)['ok'], S.check(source).get('errors'))

    def test_without_the_directive_nothing_changes(self):
        source = SP.compile_sheet(SHEET.replace('Answers normalized: yes\n\n', ''), ['ollama:gemma3:1b'], samples=1, retries=1, rounds=1)
        self.assertIn('ask unit_renderCodeSpan: Code js """', source)

    def test_the_contract_plan_accepts_and_records_the_directive(self):
        plan = C.plan(SP.parse(SHEET))
        self.assertTrue(plan)
        plain = C.plan(SP.parse(SHEET.replace('Answers normalized: yes\n\n', '')))
        self.assertNotEqual(str(plan), str(plain))


class ReviewFindings(unittest.TestCase):
    """What the 2026-10-10 adversarial review found and the fixes it led to."""

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_cuts_are_made_in_utf16_units_so_astral_characters_do_not_shift_them(self):
        reply = "```js\nconst A = '\U0001F600\U0001F600\U0001F600';\nfunction escapeHtml(s) { return s; }\nfunction renderCodeSpan(part) { return A + escapeHtml(part); }\n```"
        out = N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['renderCodeSpan'], 'given': ['escapeHtml']})
        self.assertEqual(out, "const A = '\U0001F600\U0001F600\U0001F600';\nfunction renderCodeSpan(part) { return A + escapeHtml(part); }")

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_a_cut_never_collapses_blank_lines_elsewhere_nor_glues_lines(self):
        reply = "```js\nfunction escapeHtml(s) { return s; }\nconst T = `a\n\n\n\nb`;\nfunction f(x) { return T + escapeHtml(x); }\n```"
        out = N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': ['escapeHtml']})
        self.assertEqual(out, "const T = `a\n\n\n\nb`;\nfunction f(x) { return T + escapeHtml(x); }")
        glued = "```js\nconst x = 1\nfunction escapeHtml(s) { return s; }\n[1].map(f)\nfunction f(v) { return v; }\n```"
        out = N.normalize(glued, {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': ['escapeHtml']})
        self.assertEqual(out, "const x = 1\n[1].map(f)\nfunction f(v) { return v; }")

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_a_lone_surrogate_in_a_reply_does_not_break_the_cut(self):
        reply = "```js\nconst S = '\ud83d';\nfunction escapeHtml(s) { return s; }\nfunction f(x) { return S + escapeHtml(x); }\n```"
        out = N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': ['escapeHtml']})
        self.assertEqual(out, "const S = '\ud83d';\nfunction f(x) { return S + escapeHtml(x); }")

    def test_a_json_answer_object_is_still_unwrapped(self):
        reply = '{"answer": "function f(x) { return x; }"}'
        self.assertEqual(N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': []}), 'function f(x) { return x; }')

    def test_a_usage_block_is_not_mistaken_for_the_declaration(self):
        reply = "```js\nfunction f(x) { return x; }\n```\nExample:\n```js\nf('a')\n```"
        self.assertEqual(N.normalize(reply, {'k': 'code', 'lang': 'js', 'names': ['f'], 'given': []}), 'function f(x) { return x; }')

    def test_the_prefilter_is_linear_on_long_blank_runs(self):
        import time
        code = 'x\n' + '\n' * 60000 + 'escapeHtml(1)'
        t0 = time.monotonic()
        N._declares(code, 'escapeHtml')
        self.assertLess(time.monotonic() - t0, 2.0)

    def test_reusing_without_unit_is_refused_and_a_record_field_ends_the_list(self):
        bad = S.check('ask x: Code js reusing a "write".\nshow x.\n')
        self.assertFalse(bad['ok'])
        src = 'ask x: Record {code: Code js unit a, note: Text} "write".\nshow x.\n'
        self.assertTrue(S.check(src)['ok'], S.check(src).get('errors'))
        ty = next(st for st in S.parse(src)['statements'] if st.k == 'ask').type
        self.assertEqual([f[0] for f in ty['fields']], ['code', 'note'])
        self.assertEqual(ty['fields'][0][1]['names'], ['a'])

    def test_plain_sheets_parse_to_the_historical_shape_and_bad_names_are_refused(self):
        plain = SP.parse(SHEET.replace('Answers normalized: yes\n\n', ''))
        self.assertEqual(set(plain), {'title', 'intro', 'shared', 'units', 'template'})
        dollar = SHEET.replace('escapeHtml', 'escape$Html')
        self.assertTrue(any('plain identifier' in p for p in SP.problems(SP.parse(dollar))))
        from symblic.spec import build as B
        with self.assertRaises(SP.SheetError) as got:
            B.compile_cards(SHEET, ['fake:a'], samples=1, retries=1, rounds=1)
        self.assertIn('Answers normalized', str(got.exception))

    def test_the_kernel_identity_names_the_normalizer(self):
        self.assertEqual(S.kernel_id().get('js_normalize'), N.VERSION)

    @unittest.skipUnless(HAS_NODE, 'node runtime')
    def test_incremental_keep_reads_the_normalized_code(self):
        import json, os, tempfile
        source = SP.compile_sheet(SHEET, ['fake:a'], samples=1, retries=1, rounds=1)
        normalized = N.normalize(COPY, {'k': 'code', 'lang': 'js', 'names': ['renderCodeSpan'], 'given': ['escapeHtml']})
        with tempfile.TemporaryDirectory(prefix='symblic-normalize-') as folder:
            with open(os.path.join(folder, 'program.sym'), 'w') as fh:
                fh.write(source)
            with open(os.path.join(folder, 'trace.jsonl'), 'w') as fh:
                fh.write(json.dumps({'kind': 'ask', 'name': 'unit_renderCodeSpan', 'status': 'ok', 'hash': S.fingerprint(normalized)}) + '\n')
            with open(os.path.join(folder, 'calls.jsonl'), 'w') as fh:
                fh.write(json.dumps({'stmt': 'unit_renderCodeSpan', 'reply': {'ok': True, 'text': COPY}}) + '\n')
            kept = SP.accepted_units(folder)
        self.assertEqual(kept.get('unit_renderCodeSpan'), normalized)
        self.assertNotIn('function escapeHtml', kept.get('unit_renderCodeSpan', ''))


if __name__ == '__main__':
    unittest.main()


class TrailingJunk(unittest.TestCase):
    """gemma3:1b (2026-10-11) answered a two-constant unit with the unit, then the same constants again, a renamed
    copy, helper functions and `function f()() {`: the valid prefix is the answer."""

    def test_a_broken_tail_is_cut_and_the_duplicate_declaration_goes_with_it(self):
        from symblic.js import normalize as N
        if not N._node() or not N.parser_ok():
            self.skipTest('node or the pinned parser is unavailable')
        reply = ('```js\nconst SHAPES = { I: { n: 4 } };\n\nconst COLORS = { I: "cyan" };\n\n'
                 'const SHAPES = { I: { n: 4 } };\n\nconst colors = { I: "cyan" };\n\n'
                 'function define_shapes() {\n  return SHAPES;\n}\n\nfunction define_shapes()() {\n  return 1;\n}\n'
                 'function define_shapes()() {\n```')
        ty = {'k': 'code', 'lang': 'js', 'names': ['SHAPES', 'COLORS']}
        out = N.normalize(reply, ty)
        names = [d.get('name') for d in (N.declarations(out) or [])]
        self.assertIn('SHAPES', names)
        self.assertIn('COLORS', names)
        self.assertEqual(1, names.count('SHAPES'))
        self.assertNotIn('()()', out)
        self.assertIsNotNone(N.declarations(out))                  # the result parses

    def test_a_block_that_parses_is_untouched_and_a_cut_that_loses_a_name_is_refused(self):
        from symblic.js import normalize as N
        if not N._node() or not N.parser_ok():
            self.skipTest('node or the pinned parser is unavailable')
        good = 'const A = 1;\nconst B = 2;'
        self.assertEqual(good, N.cut_trailing_junk(good, ['A', 'B']))
        broken = 'const A = 1;\nfunction f()() {\nconst B = 2;'
        self.assertEqual(broken, N.cut_trailing_junk(broken, ['A', 'B']))   # B would be lost: unchanged


class UnterminatedFence(unittest.TestCase):
    def test_an_unclosed_fence_still_yields_the_unit_and_its_junk_tail_is_cut(self):
        from symblic.js import normalize as N
        if not N._node() or not N.parser_ok():
            self.skipTest('node or the pinned parser is unavailable')
        reply = ('```js\nconst SHAPES = { I: { n: 4 } };\nconst COLORS = { I: "cyan" };\n\n'
                 'function SHAPES_I() {\n  return SHAPES.I;\n}\n\nfunction SHAPES_L() {\n  return SHAP')
        ty = {'k': 'code', 'lang': 'js', 'names': ['SHAPES', 'COLORS']}
        out = N.normalize(reply, ty)
        names = [d.get('name') for d in (N.declarations(out) or [])]
        self.assertIn('SHAPES', names)
        self.assertIn('COLORS', names)
        self.assertNotIn('```', out)
        self.assertIsNotNone(N.declarations(out))


class JunkAfterTheUnit(unittest.TestCase):
    def test_the_first_declarations_win_when_a_junk_tail_declares_the_unit_again(self):
        """qwen2.5:0.5b (2026-10-11): the exact unit, then helper junk, then `function SHAPES(...)` again, then an
        unterminated tail. The const table must survive; the function-form preference is for clean pairs only."""
        from symblic.js import normalize as N
        if not N._node() or not N.parser_ok():
            self.skipTest('node or the pinned parser is unavailable')
        reply = ('```js\nconst SHAPES = { I: { n: 4 } };\nconst COLORS = { I: "cyan" };\n\n'
                 'function SHAPES_I() {\n  return SHAPES.I;\n}\n\nfunction SHAPES(n) {\n  return n;\n}\n\n'
                 'function SHAPES_O(n) {\n  return SHAPES_O_n(n);\n}\n\nfunction SHAPES_O(n) {\n  return SHAPES_O_n(n')
        ty = {'k': 'code', 'lang': 'js', 'names': ['SHAPES', 'COLORS']}
        out = N.normalize(reply, ty)
        decls = N.declarations(out) or []
        shapes = [d for d in decls if d.get('name') == 'SHAPES']
        self.assertEqual(1, len(shapes))
        self.assertEqual('const', shapes[0].get('kind'), out[:200])
        self.assertIn('COLORS', [d.get('name') for d in decls])
        self.assertNotIn('SHAPES_O', out)

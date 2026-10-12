"""Picker v4 edits judged by the native parser (review picker-v3 findings 1-4).

The picker's own lexical functions (web/studio/symblic-picker.js) run in node (tests/kernel/picker_native_probe.mjs,
no browser or network); the live
parser is imported read-only. Every accepted edit must change exactly the intended thing in the AST: the target ask's
`by` (and the requested `with` options) with literal values, or one new top-level group whose name is bound nowhere
else. Every unsafe form must be refused with the source unchanged. No store, provider, model or network.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))                 # tests/kernel: picker_native_probe.mjs is here
NATIVE = os.environ.get('SYMBLIC_NATIVE', os.path.dirname(os.path.dirname(HERE)))   # the parser to judge with
sys.path.insert(0, NATIVE)
from symblic.kernel import language as S  # noqa: E402
from symblic.js import check as JS  # noqa: E402

NODE = JS.node_path()
NEW = 'by ["fake:new", "fake:second"]'
NEW_BY = {'k': 'list', 'items': [{'k': 'str', 'parts': ['fake:new']}, {'k': 'str', 'parts': ['fake:second']}]}
MEMBERS = ['fake:new', 'fake:second']
TRIPLE_SINGLE = "let memo = '''alpha\nask x: Int \"Pick.\"\nomega'''.\nshow memo."

# (id, source, cursor line, target ask, addition, expected with-options)
ASK_APPLY = [
    ('plain', 'ask x: Int "Pick."', 0, 'x', NEW, {}),
    ('plain_period', 'ask x: Int "Pick.".', 0, 'x', NEW, {}),
    ('single_quoted_prompt', "ask x: Int 'Pick it.'.", 0, 'x', NEW, {}),
    ('unicode_text', 'ask résumé: Text "Écris « bonjour » 中文 😀".', 0, 'résumé', NEW, {}),
    ('escaped_delimiters', 'ask x: Text "say \\"by\\" and \\\\ with".', 0, 'x', NEW, {}),
    ('triple_double_one_line', 'ask x: Text """He said "by" with care.""".', 0, 'x', NEW, {}),
    ('triple_single_one_line', "ask x: Text '''it's by me'''.", 0, 'x', NEW, {}),
    ('trailing_comment', 'ask x: Int "Pick.". # by hand, with care', 0, 'x', NEW, {}),
    ('no_period_trailing_comment', 'ask x: Int "Pick."  # by hand', 0, 'x', NEW, {}),
    ('for_each', 'let items = [1, 2].\nask y: Int "Double {item}." for each item in items.', 1, 'y', NEW, {}),
    ('name_containing_with', 'ask withdrawal: Int "Amount by month."', 0, 'withdrawal', NEW, {}),
    ('inside_block', 'let go = true.\nif go then\n  ask y: Int "Pick."\nend', 2, 'y', NEW, {}),
    ('after_triple_string', TRIPLE_SINGLE.replace('show memo.', 'ask z: Int "Real."'), 3, 'z', NEW, {}),
    ('after_apostrophes', "# it's fine\nDon't worry about it.\nask x: Int \"Pick.\"", 2, 'x', NEW, {}),
    ('vote', 'ask x: Int "Pick."', 0, 'x', NEW + ' with votes=3', {'votes': {'k': 'num', 'value': 3}}),
    ('search', 'ask x: Int "Pick."', 0, 'x', NEW + ' with route=search, samples=6, rounds=2',
     {'route': {'k': 'name', 'name': 'search'}, 'samples': {'k': 'num', 'value': 6},
      'rounds': {'k': 'num', 'value': 2}}),
]
# (id, source, cursor line)
ASK_REFUSE = [
    ('triple_single_string', TRIPLE_SINGLE, 1),
    ('triple_double_inner_quote', 'let memo = """alpha " quote\nask x: Int "Pick."\nomega""".\nshow memo.', 1),
    ('escaped_triple_delimiter', 'let memo = """a \\""" b\nask x: Int "Pick."\nc""".\nshow memo.', 1),
    ('uppercase_existing_by', 'ask x: Int "Pick." BY "fake:old".', 0),
    ('uppercase_existing_with', 'ask x: Int "Pick." WITH by="fake:old".', 0),
    ('mixed_case_with', 'ask x: Int "Pick." wItH votes=2.', 0),
    ('uppercase_continuation', 'ask x: Int "Pick."\nBY "fake:old".', 0),
    ('comment_before_continuation', 'ask x: Int "Pick."\n# middle\nby "fake:old".', 0),
    ('blank_before_continuation', 'ask x: Int "Pick."\n\nby "fake:old".', 0),
    ('slash_comment_then_with', 'ask x: Int "Pick."\n// middle\nWith votes=2.', 0),
    ('for_each_continuation', 'let items = [1].\nask y: Int "d"\nFOR EACH item in items.', 1),
    ('backslash_continuation', 'ask x: Int "Pick." \\\n  by "fake:old".', 0),
    ('multiline_prompt', 'ask x: Text """one\ntwo""".', 0),
    ('ambiguous_line_above', '[1,\n2] = [1, 2].\nask x: Int "Pick."', 2),
    ('loop_variable_named_by', 'let items = [1].\nask y: Int "d" for each by in items.', 1),
    ('not_an_ask', 'let x = 1.', 0),
    ('blank_line', 'ask x: Int "Pick."\n\nshow 1.', 1),
]
# (id, source, members, expected name)
GROUP_APPLY = [
    ('multiline_use', 'use budget=(\n200000\n).\nshow 1.', MEMBERS, 'crew'),
    ('headers', 'program Demo\nnote This is a note.\nuse profile=verified.\n\nask x: Int "Pick."', MEMBERS, 'crew'),
    ('no_headers', 'ask x: Int "Pick."', MEMBERS, 'crew'),
    ('comments_first', '# header comment\nprogram Demo\n# a comment\n\nask x: Int "Pick."', MEMBERS, 'crew'),
    ('name_collision_let', 'let crew = 1.\nshow crew.', MEMBERS, 'crew2'),
    ('every_binding_kind', 'let crew = 0.\ngiven crew2: Int = 1.\nask Crew3: Int "Pick {crew2}."\n'
     'define Crew4 as Int.\nlet items = [1, 2].\nask y: Int "Double {crew5}." for each crew5 in items.\n'
     'group crew6 = ["fake:a", "fake:b"].\nshow "crew7".', MEMBERS, 'crew8'),
]
# (id, source, members)
GROUP_REFUSE = [
    ('prose_then_continuation', 'note Hello.\nby "x".', MEMBERS),
    ('unsafe_member', 'ask x: Int "Pick."', ['fake:{x}', 'fake:b']),
]


def simple(v):
    if isinstance(v, S.Node):
        return {k: simple(x) for k, x in vars(v).items() if k not in ('line', 'col')}
    if isinstance(v, (list, tuple)):
        return [simple(x) for x in v]
    if isinstance(v, dict):
        return {k: simple(x) for k, x in v.items()}
    return v


def tree(source):
    return simple(S.parse(source)['statements'])


def asks(node, out=None):
    out = [] if out is None else out
    if isinstance(node, dict):
        if node.get('k') == 'ask':
            out.append(node)
        for value in node.values():
            asks(value, out)
    elif isinstance(node, list):
        for value in node:
            asks(value, out)
    return out


def checked(source):
    report = S.check(source)
    errors = report.get('errors') or []
    return bool(report.get('ok')), [e.get('message') if isinstance(e, dict) else str(e) for e in errors]


@unittest.skipUnless(NODE, 'Node.js is not installed')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = [{'id': c[0], 'kind': 'ask', 'source': c[1], 'line': c[2], 'addition': c[4]} for c in ASK_APPLY]
        cases += [{'id': c[0], 'kind': 'ask', 'source': c[1], 'line': c[2], 'addition': NEW} for c in ASK_REFUSE]
        cases += [{'id': c[0], 'kind': 'group', 'source': c[1], 'members': c[2]} for c in GROUP_APPLY + GROUP_REFUSE]
        with tempfile.NamedTemporaryFile('w', suffix='.json', dir=os.environ.get('TMPDIR'), delete=False) as stream:
            json.dump(cases, stream)
        try:
            done = subprocess.run([NODE, os.path.join(HERE, 'picker_native_probe.mjs'), stream.name],
                                  capture_output=True, text=True, timeout=60, check=True)
        finally:
            os.unlink(stream.name)
        cls.got = {row['id']: row for row in json.loads(done.stdout)}

    def test_every_source_is_native_valid_before_the_picker_touches_it(self):
        for case in ASK_APPLY + GROUP_APPLY:
            with self.subTest(case[0]):
                self.assertEqual(checked(case[1]), (True, []))

    def test_accepted_ask_edits_change_exactly_the_target_ask(self):
        for ident, source, _line, target, _addition, extra in ASK_APPLY:
            with self.subTest(ident):
                got = self.got[ident]
                self.assertTrue(got['ok'], got['reason'])
                before, after = tree(source), tree(got['text'])
                self.assertEqual(checked(got['text']), (True, []))
                mine = [a for a in asks(after) if a['name'] == target]
                self.assertEqual(len(mine), 1)
                self.assertEqual(mine[0]['options'].get('by'), NEW_BY)
                for key, value in extra.items():
                    self.assertEqual(mine[0]['options'].get(key), value)
                restored = copy.deepcopy(after)          # remove exactly what was added: the rest is the original
                for node in asks(restored):
                    if node['name'] == target:
                        for key in ['by', *extra]:
                            node['options'].pop(key)
                self.assertEqual(restored, before)

    def test_unsafe_or_uncertain_asks_are_refused_without_change(self):
        for ident, _source, _line in ASK_REFUSE:
            with self.subTest(ident):
                got = self.got[ident]
                self.assertFalse(got['ok'])
                self.assertIsNone(got['text'])
                self.assertTrue(got['reason'])

    def test_groups_go_between_whole_statements_with_an_unused_name(self):
        for ident, source, members, name in GROUP_APPLY:
            with self.subTest(ident):
                got = self.got[ident]
                self.assertTrue(got['ok'], got['reason'])
                self.assertEqual(got['name'], name)
                self.assertNotIn(name, source.lower())
                before, after = tree(source), tree(got['text'])
                self.assertEqual(checked(got['text']), (True, []))
                added = [i for i, s in enumerate(after) if s.get('k') == 'group' and s.get('name') == name]
                self.assertEqual(len(added), 1)
                group = after.pop(added[0])
                literal = {'k': 'list', 'items': [{'k': 'str', 'parts': [m]} for m in members]}
                self.assertEqual(group['members'], literal)
                self.assertEqual(after, before)

    def test_unsafe_groups_are_refused_without_change(self):
        for ident, _source, _members in GROUP_REFUSE:
            with self.subTest(ident):
                self.assertFalse(self.got[ident]['ok'])
                self.assertIsNone(self.got[ident]['text'])


if __name__ == '__main__':
    unittest.main()

"""symblic.english.compiler: near-English statements compiled to native Symblic.

Isolated: fake applicators, temporary run folders, no model, network, worker, account or private store.
Native modules come from SYMBLIC_NATIVE (another checkout of this repository) when set, else from this repository.
Run from the repository root: python3 -B -m unittest tests.english.test_symblic_english -v
"""
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[2]          # the repository root
NATIVE = Path(os.environ.get('SYMBLIC_NATIVE') or HERE)
for path in (str(NATIVE), str(HERE)):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)

from symblic.kernel import language as S  # noqa: E402
from symblic.english import compiler as E  # noqa: E402
from symblic.kernel import execution_pins as X  # noqa: E402
from symblic.kernel import lockfile as K  # noqa: E402
from symblic.kernel.run import Run  # noqa: E402

assert Path(E.__file__).resolve().parents[2] == HERE, E.__file__
FALLING = E.EXAMPLES['falling-number']['source']
CATEGORIZE = E.EXAMPLES['categorize']['source']
CONTEXT_ROW = re.compile(r'^- (\w+) : [^=]+ = (.*)$', re.M)


def context_section(prompt):
    if 'CONTEXT' not in prompt:
        return ''
    return prompt.split('CONTEXT', 1)[1].split('STATEMENT:', 1)[0]


def selected(prompt):
    return {m.group(1): m.group(2) for m in CONTEXT_ROW.finditer(context_section(prompt))}


class Worker:
    """A fake applicator that READS its selected input from the capsule and computes the answer.

    `rule(statement_text, selected_values, attempt)` returns the answer; nothing is pregenerated.
    """

    def __init__(self, rule):
        self.rule, self.requests, self.lock = rule, [], threading.Lock()

    def call(self, req):
        with self.lock:
            self.requests.append(copy.deepcopy({k: v for k, v in req.items() if k != 'stop'}))
            attempt = len(self.requests)
        statement = req['prompt'].split('STATEMENT:', 1)[1]
        answer = self.rule(statement, selected(req['prompt']), attempt)
        return {'ok': True, 'json': {'reasoning': 'fake', 'answer': answer}, 'model': 'fake-model',
                'node': 'fake-node'}


def falling_rule(statement, values, attempt):
    (name, value), = values.items()          # exactly one selected value
    return int(value) - 1


OPTIONS = {'by': 'fake:model', 'parallel': 1}


def run(compiled, worker, folder, extra=None):
    opts = {**compiled['options'], **OPTIONS, **(extra or {})}
    Path(folder, 'program.sym').write_text(compiled['source'])
    Path(folder, 'meta.json').write_text(json.dumps({'options': opts, 'inputs': compiled['inputs']}))
    return Run(compiled['source'], compiled['inputs'], worker, opts, folder=folder).execute()


class self_raises:
    def __enter__(self):
        return self

    def __exit__(self, kind, exc, tb):
        if not isinstance(exc, E.EnglishError):
            raise AssertionError(f'expected EnglishError, got {kind}: {exc}')
        self.error = exc
        return True


class Compilation(unittest.TestCase):
    def test_result_schema_and_defaults(self):
        out = E.compile_source(FALLING)
        self.assertEqual({'version', 'source_sha256', 'source', 'options', 'inputs', 'names', 'statements',
                          'warnings', 'source_map'}, set(out))
        self.assertEqual('symblic-english/1', out['version'])
        self.assertEqual(hashlib.sha256(FALLING.encode()).hexdigest(), out['source_sha256'])
        self.assertEqual({'profile': 'verified', 'context': 'none', 'determine': False, 'solve': False,
                          'constructor': 'off', 'max_calls': 64}, out['options'])
        self.assertEqual({}, out['inputs'])
        self.assertTrue(out['source'].startswith('use profile=verified.\n'))
        for stmt in out['statements']:
            self.assertEqual({'index', 'line', 'col', 'end_line', 'end_col', 'kind', 'text', 'native_lines'}
                             | ({'ask'} if stmt['kind'] in ('using', 'accept') else set()), set(stmt))

    def test_deterministic_and_independent_of_prior_calls(self):
        first = json.dumps(E.compile_source(FALLING), sort_keys=True)
        E.compile_source(CATEGORIZE, retries=5)
        self.assertEqual(first, json.dumps(E.compile_source(FALLING), sort_keys=True))

    def test_every_ask_carries_the_direct_step_contract(self):
        out = E.compile_source(FALLING, retries=4, budget=9000)
        asks = [l for l in out['source'].splitlines() if l.startswith('ask ')]
        self.assertEqual(6, len(asks))
        for line in asks:
            self.assertTrue(line.endswith(' with context=none, determine=false, solve=false, retries=4, '
                                          'budget=9000.'), line)
        prog = S.parse(out['source'])
        native_asks = [s for s in prog['statements'] if s.k == 'ask']
        self.assertEqual(6, len(native_asks))
        for s in native_asks:
            self.assertEqual(1, len(s.sources))
            self.assertEqual({'context', 'determine', 'solve', 'retries', 'budget'}, set(s.options))
        # no answer is precomputed: no native let binds an asked name
        self.assertFalse(re.search(r'^let row_[1-6]\b', out['source'], re.M))

    def test_type_mapping(self):
        text = ('Ask for a as a whole number: "a".\nAsk for b as whole number from 0 to 6: "b".\n'
                'Ask for c as a number: "c".\nAsk for d as a number from -1.5 to 2: "d".\n'
                'Ask for e as text: "e".\nAsk for f as yes or no: "f".\n'
                'Ask for g as one of "red", "pale-yellow" or "deep blue": "g".\n')
        src = E.compile_source(text)['source']
        for frag in ('ask a: Int "a"', 'ask b: Int in 0..6 "b"', 'ask c: Number "c"',
                     'ask d: Number in -1.5..2 "d"', 'ask e_value: Text "e"', 'ask f: Bool "f"',
                     'ask g: one of {"red", "pale-yellow", "deep blue"} "g"'):
            self.assertIn(frag, src)
        self.assertTrue(E.check_source(text)['ok'])

    def test_literals_are_exact(self):
        text = ('Remember a is 7.\nRemember b is -3.\nRemember c is 0.5.\nRemember d is 3/4.\n'
                'Remember e is yes.\nRemember f is false.\nRemember g is "say \\"hi\\"\\nnow {x} \\\\ end".\n'
                'Show a.\nShow b.\nShow c.\nShow d.\nShow e.\nShow f.\nShow g.\n')
        out = E.compile_source(text)
        report = Run(out['source'], {}, None, dict(out['options'])).execute()
        self.assertEqual('done', report['status'], report)
        values = [o['canonical'] for o in report['outputs']]
        self.assertEqual([7, -3, {'#q': '1/2'}, {'#q': '3/4'}, True, False, 'say "hi"\nnow {x} \\ end'], values)
        self.assertEqual(['Int', 'Int', 'Number', 'Number', 'Bool', 'Bool', 'Text'],
                         [o['type'] for o in report['outputs']])

    def test_readable_names_map_to_safe_unique_ids(self):
        text = ("Remember 'next y' is 1.\nRemember sum is 2.\nRemember '3 apples' is 3.\nRemember 'Café au lait' is 4.\n"
                "Show 'Next  Y'.\n")
        out = E.compile_source(text)
        self.assertEqual({'next y': 'next_y', 'sum': 'sum_value', '3 apples': 'n_3_apples',
                          'Café au lait': 'cafe_au_lait'}, out['names'])
        self.assertIn('show next_y.', out['source'])

    def test_multiline_statement_and_crlf_positions(self):
        text = 'Remember a is 1.\r\nAsk for b as a whole number:\r\n  "two\r\nlines".\r\nShow b.\r\n'
        out = E.compile_source(text)
        ask = out['statements'][1]
        self.assertEqual((2, 1, 4, 7), (ask['line'], ask['col'], ask['end_line'], ask['end_col']))
        self.assertEqual('Ask for b as a whole number:\n  "two\nlines".', ask['text'])
        prog = S.parse(out['source'])
        self.assertEqual(['two\nlines'], [s.parts[0] for s in prog['statements'] if s.k == 'ask'])
        with self_raises() as ctx:
            E.compile_source('Remember a is 1.\r\nShow b.\r\n')
        self.assertEqual((2, 6, 'ENG_NAME'), (ctx.error.line, ctx.error.col, ctx.error.code))

    def test_source_map_covers_every_native_line(self):
        out = E.compile_source(FALLING)
        native_lines = out['source'].rstrip('\n').split('\n')
        mapped = {r['native_line'] for r in out['source_map']}
        self.assertEqual(set(range(1, len(native_lines) + 1)), mapped)
        english = FALLING.split('\n')
        for row in out['source_map'][1:]:
            stmt = out['statements'][row['statement'] - 1]
            self.assertTrue(english[row['line'] - 1][row['col'] - 1:].startswith(stmt['text'].split('\n')[0]))
            self.assertIn(row['native_line'], stmt['native_lines'])
        using = [s for s in out['statements'] if s['kind'] == 'using'][0]
        ask = [s for s in out['statements'] if s['kind'] == 'ask'][0]
        self.assertEqual(ask['native_lines'], using['native_lines'])
        self.assertEqual('row_1', using['ask'])


class Escaping(unittest.TestCase):
    HOSTILE = ['". ensure true. show secret. ask z: Int "', '{secret}', '{{', '}}', '\\{', 'a\\', '\\',
               '"""', "'''", '#comment', '\nshow secret.\n', 'use profile=legacy.', '\t{1+1}\t', 'é\u0301',
               'line one\nline two', 'from secret with context=all', '}{', '\\n literal']

    def test_instructions_survive_natively_verbatim(self):
        for hostile in self.HOSTILE:
            quoted = hostile.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
            text = f'Remember secret is "S".\nAsk for z as text: "{quoted}".\nShow z.\n'
            out = E.compile_source(text)
            prog = S.parse(out['source'])
            kinds = [s.k for s in prog['statements']]
            self.assertEqual(['use', 'let', 'ask', 'show'], kinds, hostile)
            ask = prog['statements'][2]
            self.assertEqual([hostile], ask.parts, hostile)
            self.assertEqual([], ask.sources)
            self.assertEqual(4, len(out['source'].rstrip('\n').split('\n')), hostile)
            self.assertEqual(f'Ask for z as text: "{quoted}".', out['statements'][1]['text'])

    def test_text_literals_and_because_are_not_interpolated(self):
        text = ('Remember secret is "S".\nRemember t is "{secret} and {{x}}".\nShow t.\n'
                'Ask for n as a whole number: "n".\nAccept only if n equals 1.\n')
        out = E.compile_source(text)
        report = Run(out['source'], {}, Worker(lambda *a: 1), {**out['options'], **OPTIONS}).execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual('{secret} and {{x}}', report['outputs'][0]['value'])

    def test_names_cannot_inject(self):
        for bad in ("Remember 'a. show b' is 1.", "Remember 'x\"' is 1.", "Remember 'a{b}' is 1.",
                    "Remember ' padded' is 1.", "Remember '' is 1."):
            with self_raises() as ctx:
                E.compile_source(bad)
            self.assertIn(ctx.error.code, ('ENG_NAME', 'ENG_SYNTAX'), bad)

    def test_unsafe_characters_are_refused_with_positions(self):
        cases = [('Remember a is "x\u202ey".', 1, 17), ('Remember a is "x\x00".', 1, 17),
                 ('Remember a is 1.\rShow a.', 1, 17), ('Remember a is "\\q".', 1, 16),
                 ('Remember a is "open.\n', 1, 15), ('Remember a is 1 @.', 1, 17)]
        for text, line, col in cases:
            with self_raises() as ctx:
                E.compile_source(text)
            self.assertEqual((line, col), (ctx.error.line, ctx.error.col), (text, ctx.error))
            self.assertEqual('ENG_SYNTAX', ctx.error.code)


class Rejections(unittest.TestCase):
    def assertRefused(self, text, code, line, col, fragment=''):
        with self_raises() as ctx:
            E.compile_source(text)
        err = ctx.error
        self.assertEqual((code, line, col), (err.code, err.line, err.col), (text, err.message))
        self.assertIn(fragment, err.message)
        checked = E.check_source(text)
        self.assertFalse(checked['ok'])
        self.assertEqual([err.as_dict()], checked['errors'])
        self.assertIsNone(checked['compiled'])

    def test_unknown_and_malformed_grammar(self):
        self.assertRefused('Compute the answer.', 'ENG_SYNTAX', 1, 1, 'unknown statement')
        self.assertRefused('Remember a is 1', 'ENG_SYNTAX', 1, 1, 'period')
        self.assertRefused('Remember a is 1..', 'ENG_SYNTAX', 1, 17, 'empty statement')
        self.assertRefused('Remember a is 1e5.', 'ENG_SYNTAX', 1, 15, 'malformed number')
        self.assertRefused('Remember a is 1,000.', 'ENG_SYNTAX', 1, 16, "unexpected ','")
        self.assertRefused('Remember a is 5..5.', 'ENG_SYNTAX', 1, 17, 'empty statement')
        self.assertRefused('Remember a is .5.', 'ENG_SYNTAX', 1, 15, 'expected a value')
        self.assertRefused('Remember a is 1/0.', 'ENG_SYNTAX', 1, 15, 'fraction')
        self.assertRefused('Ask for a as a colour: "x".', 'ENG_SYNTAX', 1, 14, 'answer shape')
        self.assertRefused('Ask for a as text "x".', 'ENG_SYNTAX', 1, 19, '":"')
        self.assertRefused('Ask for a as text: "  ".', 'ENG_SYNTAX', 1, 20, 'empty')
        self.assertRefused('Ask for a as one of "x": "q".', 'ENG_TYPE', 1, 14, '2 to')
        self.assertRefused('Ask for a as one of "x", "X": "q".', 'ENG_TYPE', 1, 26, 'duplicate label')
        self.assertRefused('Ask for a as one of 1, 2: "q".', 'ENG_SYNTAX', 1, 21, 'label')
        self.assertRefused('Ask for a as whole number from 5 to 1: "q".', 'ENG_TYPE', 1, 32, 'empty')
        self.assertRefused('Ask for a as whole number from 0 to 1.5: "q".', 'ENG_TYPE', 1, 37, 'whole-number')
        self.assertRefused('Ask for a as text: "x".\nAccept only if a contains "y".', 'ENG_SYNTAX', 2, 18, 'equals')
        self.assertRefused('Ask for a as a whole number: "x".\nAccept only if a equals 1 plus 2 plus 3.',
                           'ENG_SYNTAX', 2, 34, 'one arithmetic step')
        self.assertRefused('Remember a is 1.\nShow a and more.', 'ENG_SYNTAX', 2, 8, 'unexpected')

    def test_structure(self):
        self.assertRefused('Remember a is 1.\nUsing only a.', 'ENG_STRUCTURE', 2, 1, 'belongs to')
        self.assertRefused('Ask for a as text: "x".\nShow a.\nAccept only if a equals "y".', 'ENG_STRUCTURE',
                           3, 1, 'directly after')
        self.assertRefused('Remember b is 1.\nRemember c is 2.\nAsk for a as text: "x".\nUsing only b.\nUsing only c.',
                           'ENG_STRUCTURE', 5, 1, 'already has')
        self.assertRefused('Remember b is 1.\nAsk for a as whole number: "x".\nAccept only if a equals 1.\n'
                           'Using only b.', 'ENG_STRUCTURE', 4, 1, 'before the Accept')
        self.assertRefused('Remember b is 1.\nAsk for a as whole number: "x".\nAccept only if b equals 1.',
                           'ENG_STRUCTURE', 3, 16, 'own Ask for')

    def test_a_source_of_comments_only_is_not_a_program(self):
        for text in ('# only a comment\n', '# one\n\n# two\n', '', '   \n'):
            with self.subTest(text=text):
                self.assertRefused(text, 'ENG_STRUCTURE', 1, 1, 'A program needs at least one statement.')
        checked = E.check_source('# a heading\nRemember a is 1.\nShow a.\n')
        self.assertTrue(checked['ok'], checked['errors'])

    def test_names(self):
        self.assertRefused('Remember a is 1.\nRemember A is 2.', 'ENG_NAME', 2, 10, 'already defined at line 1')
        self.assertRefused("Remember 'next y' is 1.\nRemember 'next-y' is 2.", 'ENG_NAME', 2, 10, 'next_y')
        self.assertRefused('Show later.\nRemember later is 1.', 'ENG_NAME', 1, 6, 'defined later, at line 2')
        self.assertRefused('Show nothing.', 'ENG_NAME', 1, 6, 'not defined')
        self.assertRefused('Ask for a as text: "x".\nUsing only a.', 'ENG_NAME', 2, 12, 'own answer')
        self.assertRefused('Remember b is 1.\nAsk for a as text: "x".\nUsing only b, b.', 'ENG_NAME', 3, 15, 'twice')
        self.assertRefused('Remember b is 1.\nAsk for a as text: "x".\nUsing only b c.', 'ENG_SYNTAX', 3, 14, 'commas')
        self.assertRefused('Remember yes is 1.', 'ENG_NAME', 1, 10, 'grammar word')
        self.assertRefused('Ask for a as text: "x".\nUsing only later.\nRemember later is 1.', 'ENG_NAME', 2, 12,
                           'defined later')

    def test_types_bool_number_text(self):
        self.assertRefused('Ask for a as yes or no: "x".\nAccept only if a is at least 1.', 'ENG_TYPE', 2, 18,
                           'compares numbers')
        self.assertRefused('Ask for a as a whole number: "x".\nAccept only if a equals yes.', 'ENG_TYPE', 2, 25,
                           'yes or no')
        self.assertRefused('Remember flag is true.\nAsk for a as a number: "x".\nAccept only if a equals flag.',
                           'ENG_TYPE', 3, 25, 'yes or no')
        self.assertRefused('Ask for a as yes or no: "x".\nAccept only if a equals 1.', 'ENG_TYPE', 2, 25,
                           'a whole number')
        self.assertRefused('Ask for a as a whole number: "x".\nAccept only if a equals 1/2.', 'ENG_TYPE', 2, 25,
                           'fractional')
        self.assertRefused('Ask for a as text: "x".\nAccept only if a is at most "z".', 'ENG_TYPE', 2, 18,
                           'compares numbers')
        self.assertRefused('Ask for a as one of "x", "y": "q".\nAccept only if a equals "z".', 'ENG_TYPE', 2, 25,
                           'not one of')
        self.assertRefused('Remember t is "x".\nAsk for a as a number: "q".\nAccept only if a equals 1 plus t.',
                           'ENG_TYPE', 3, 32, 'numbers on both sides')
        self.assertRefused('Ask for a as a number: "q".\nAccept only if a equals 1 divided by 0.', 'ENG_TYPE', 2, 38,
                           'division by zero')
        ok = E.compile_source('Remember h is 3/4.\nAsk for a as a number: "q".\nAccept only if a equals h times 2.\n'
                              'Accept only if a is less than 0.75 plus h.\nAsk for b as a whole number: "q".\n'
                              'Accept only if b equals 4/2.\nAsk for c as yes or no: "q".\nAccept only if c equals no.\n')
        self.assertIn('ensure a = (h * 2) else retry', ok['source'])
        self.assertIn('ensure b = (4/2) else retry', ok['source'])
        self.assertIn('ensure c = false else retry', ok['source'])

    def test_geometry(self):
        base = 'Remember w is 20.\nRemember h is 7.\n'
        self.assertRefused(base + 'Display 1 at column 20 and row 0 on a grid w columns by h rows.', 'ENG_GEOMETRY',
                           3, 21, 'outside')
        self.assertRefused(base + 'Display 1 at column 0 and row -1 on a grid w columns by h rows.',
                           'ENG_GEOMETRY', 3, 31, 'at least 0')
        self.assertRefused('Display 1 at column 0 and row 0 on a grid 0 columns by 3 rows.', 'ENG_GEOMETRY', 1, 43,
                           'width')
        self.assertRefused('Display 1 at column 0 and row 0 on a grid 3 columns by 501 rows.', 'ENG_GEOMETRY', 1,
                           56, 'height')
        self.assertRefused(base + 'Ask for c as a number: "q".\nDisplay 1 at column c and row 0 on a grid w columns '
                           'by h rows.', 'ENG_TYPE', 4, 21, 'whole number')
        self.assertRefused('Display 1 at column 0.5 and row 0 on a grid 3 columns by 3 rows.', 'ENG_TYPE', 1, 21,
                           'whole number')
        out = E.compile_source(base + 'Ask for c as a whole number: "q".\nDisplay "a{b}" at column c and row 0 on a '
                               'grid w columns by h rows.')
        lines = out['source'].splitlines()
        self.assertEqual('assert c >= 0 and c < w.', lines[-2])
        self.assertEqual('show {kind: "grid", value: "a\\{b\\}", x: c, y: 0, width: w, height: h}.', lines[-1])
        static = E.compile_source('Display yes at column 2 and row 1 on a grid 3 columns by 2 rows.')
        self.assertNotIn('assert', static['source'])

    def test_options(self):
        for kw in ({'retries': -1}, {'retries': 6}, {'retries': True}, {'retries': 2.0}, {'max_calls': -1},
                   {'max_calls': 10001}, {'budget': 999}, {'budget': 100001}, {'budget': '12000'}):
            with self_raises() as ctx:
                E.compile_source('Remember a is 1.', **kw)
            self.assertEqual('ENG_OPTION', ctx.error.code, kw)
            self.assertEqual('ENG_OPTION', E.check_source('Remember a is 1.', **kw)['errors'][0]['code'])
        with self.assertRaises(TypeError):
            E.compile_source('Remember a is 1.', 2)
        with self.assertRaises(TypeError):
            E.compile_source('Remember a is 1.', constructor='linear')
        with self.assertRaises(TypeError):
            E.compile_source('Remember a is 1.', folder='/tmp')
        out = E.compile_source('Remember a is 1.', retries=0, max_calls=2000, budget=100000)
        self.assertEqual(2000, out['options']['max_calls'])

    def test_limits(self):
        self.assertRefused('Remember a is "' + 'x' * (E.MAX_STRING + 1) + '".', 'ENG_LIMIT', 1, 15, 'longer')
        self.assertRefused("Remember '" + 'n' * (E.MAX_NAME + 1) + "' is 1.", 'ENG_LIMIT', 1, 10, 'at most')
        self.assertRefused('Remember a is ' + '9' * (E.MAX_DIGITS + 1) + '.', 'ENG_LIMIT', 1, 15, 'digits')
        self.assertRefused('#' + 'x' * E.MAX_TEXT, 'ENG_LIMIT', 1, 1, 'too long')
        many = ''.join(f'Remember v{i} is {i}.\n' for i in range(E.MAX_STATEMENTS + 1))
        self.assertRefused(many, 'ENG_LIMIT', 1, 1, 'too many statements')
        names = ''.join(f'Remember v{i} is {i}.\n' for i in range(E.MAX_SELECTED + 1))
        self.assertRefused(names + 'Ask for a as text: "x".\nUsing only ' +
                           ', '.join(f'v{i}' for i in range(E.MAX_SELECTED + 1)) + '.',
                           'ENG_LIMIT', E.MAX_SELECTED + 3, 1, 'at most')
        accepts = 'Ask for a as a whole number: "x".\n' + 'Accept only if a is at least 0.\n' * (E.MAX_ACCEPTS + 1)
        self.assertRefused(accepts, 'ENG_LIMIT', E.MAX_ACCEPTS + 2, 1, 'Accept only if')
        asks = ''.join(f'Ask for a{i} as text: "x".\n' for i in range(E.MAX_ASKS + 1))
        self.assertRefused(asks, 'ENG_LIMIT', 1, 1, 'too many asks')
        with self_raises() as ctx:
            E.compile_source(b'Remember a is 1.')
        self.assertEqual('ENG_SYNTAX', ctx.error.code)
        with self_raises() as ctx:
            E.compile_source('Remember a is "\ud800".')
        self.assertEqual('ENG_SYNTAX', ctx.error.code)

    def test_comments_and_blank_lines(self):
        ok = E.compile_source('# a note with "quotes" and {braces}\n\nRemember a is 1.\n  # another\nShow a.\n')
        self.assertEqual('use profile=verified.\nlet a = 1.\nshow a.\n', ok['source'])
        self.assertEqual('use profile=verified.\nlet a = 1.\n',
                         E.compile_source('Remember a is 1. # after a period a comment may follow\n')['source'])
        self.assertRefused('Remember a # x is 1.', 'ENG_SYNTAX', 1, 12, "'#'")


class NativeDiagnostics(unittest.TestCase):
    def test_native_warning_mapped_to_english_position(self):
        text = 'Remember a is 1.\n\nAsk for b as a whole number: "Probably about a, maybe."\n.\n'
        checked = E.check_source(text)
        self.assertTrue(checked['ok'], checked)
        vague = [w for w in checked['warnings'] if 'vague' in w['message']]
        self.assertEqual(1, len(vague), checked['warnings'])
        self.assertEqual((3, 1, 2, 'ENG_NATIVE_WARNING'),
                         (vague[0]['line'], vague[0]['col'], vague[0]['statement'], vague[0]['code']))
        self.assertEqual(3, vague[0]['native']['line'])

    def test_native_error_mapped_and_kept_verbatim(self):
        text = 'Remember a is 1.\nAsk for b as a whole number: "x".\nUsing only a.\nAccept only if b equals a.\n'
        real = S.check
        compiled = E.compile_source(text)
        ensure_line = compiled['statements'][3]['native_lines'][0]

        def fake_check(source, *, execution_profile=None):
            out = real(source, execution_profile=execution_profile)
            out['ok'] = False
            out['errors'] = [{'line': ensure_line, 'col': 1, 'kind': 'check', 'message': 'native says no',
                              'code': 'SYM_CHECK'}]
            return out
        with mock.patch.object(S, 'check', fake_check):
            checked = E.check_source(text)
        self.assertFalse(checked['ok'])
        self.assertEqual([{'line': 4, 'col': 1, 'statement': 4, 'code': 'ENG_NATIVE', 'message': 'native says no',
                           'native': {'line': ensure_line, 'col': 1, 'kind': 'check', 'message': 'native says no',
                                      'code': 'SYM_CHECK'}}], checked['errors'])
        self.assertEqual(compiled, checked['compiled'])

    def test_native_parser_refusal_is_positioned(self):
        real = S.parse

        def refuse(source, *, execution_profile=None):
            raise S.SymblicError('synthetic native refusal', 3, 5, 'syntax')
        with mock.patch.object(S, 'parse', refuse):
            with self_raises() as ctx:
                E.compile_source('Remember a is 1.\nAsk for b as text: "x".\n')
        self.assertEqual(('ENG_NATIVE', 2, 1), (ctx.error.code, ctx.error.line, ctx.error.col))
        self.assertEqual('SYM_SYNTAX', ctx.error.as_dict()['native']['code'])
        self.assertIs(S.parse, real)

    def test_unexpected_bugs_are_not_swallowed(self):
        with mock.patch.object(S, 'check', side_effect=ZeroDivisionError('bug')):
            with self.assertRaises(ZeroDivisionError):
                E.check_source('Remember a is 1.')


class AcceptReadability(unittest.TestCase):
    """E1: an accept line whose whole check reads the answer alone is a specification the model can read."""

    def test_an_answer_only_accept_line_warns_with_its_position(self):
        text = ('Ask for wrong as a whole number: "Give a number.".\n'
                'Accept only if wrong equals 5.\nShow wrong.\n')
        checked = E.check_source(text)
        self.assertTrue(checked['ok'], checked['errors'])
        notes = [w for w in checked['warnings'] if w['code'] == 'ENG_ACCEPT_READABLE']
        self.assertEqual(1, len(notes), checked['warnings'])
        self.assertEqual((2, 1, 2), (notes[0]['line'], notes[0]['col'], notes[0]['statement']))
        self.assertEqual({'line', 'col', 'statement', 'code', 'message'}, set(notes[0]))
        self.assertIn('specification the model can read, not a secret', notes[0]['message'])
        self.assertIn('retry', notes[0]['message'])

    def test_literal_arithmetic_on_the_answer_alone_also_warns(self):
        checked = E.check_source('Ask for a as a whole number: "x".\nAccept only if a is at least 2 plus 3.\n'
                                 'Show a.\n')
        self.assertTrue(checked['ok'], checked['errors'])
        self.assertIn('ENG_ACCEPT_READABLE', [w['code'] for w in checked['warnings']])

    def test_an_accept_line_reading_a_named_value_stays_quiet(self):
        text = ('Remember base is 2.\nAsk for result as a whole number: "Add one to base.".\n'
                'Using only base.\nAccept only if result equals base plus 1.\nShow result.\n')
        checked = E.check_source(text)
        self.assertTrue(checked['ok'], checked['errors'])
        self.assertNotIn('ENG_ACCEPT_READABLE', [w['code'] for w in checked['warnings']])


class ApiParity(unittest.TestCase):
    def test_check_source_embeds_compile_source(self):
        for name, ex in E.EXAMPLES.items():
            checked = E.check_source(ex['source'], retries=3)
            self.assertTrue(checked['ok'], (name, checked['errors']))
            self.assertEqual([], checked['errors'])
            self.assertEqual(E.compile_source(ex['source'], retries=3), checked['compiled'])
            self.assertEqual('verified', checked['native']['execution_profile'])

    def test_examples_shape_and_copy(self):
        ex = E.examples()
        self.assertEqual({'falling-number', 'categorize'}, set(ex))
        for item in ex.values():
            self.assertEqual({'title', 'source'}, set(item))
        ex['categorize']['source'] = 'mutated'
        self.assertNotEqual('mutated', E.EXAMPLES['categorize']['source'])

    def test_documented_example_files_match(self):
        folder = HERE / 'examples' / 'english'
        for name, ex in E.EXAMPLES.items():
            self.assertEqual(ex['source'], (folder / f'{name}.english.txt').read_text(encoding='utf-8'))
            self.assertEqual(E.compile_source(ex['source'])['source'],
                             (folder / f'{name}.compiled.sym').read_text(encoding='utf-8'))

    def test_error_dict_shape(self):
        err = E.check_source('Show x.')['errors'][0]
        self.assertEqual({'line', 'col', 'code', 'message'}, set(err))
        with self_raises() as ctx:
            E.compile_source('Show x.')
        self.assertIsInstance(ctx.error, ValueError)
        self.assertEqual((1, 6, 'ENG_NAME'), (ctx.error.line, ctx.error.col, ctx.error.code))
        self.assertIn('line 1, column 6', str(ctx.error))


class NativeJourneys(unittest.TestCase):
    def test_six_fresh_asks_in_order_with_only_selected_inputs(self):
        compiled = E.compile_source(FALLING)
        worker = Worker(falling_rule)
        with tempfile.TemporaryDirectory() as folder:
            report = run(compiled, worker, folder)
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(6, report['calls'])
        self.assertEqual(6, len(worker.requests))
        keys = [r['key'] for r in worker.requests]
        self.assertEqual(6, len(set(keys)))
        unselected_names = {'digit', 'width', 'height', 'x'}
        for k, req in enumerate(worker.requests, 1):
            prompt = req['prompt']
            self.assertIn(f'ask row_{k} : Int', prompt)
            self.assertEqual({f'row_{k - 1}': str(7 - k)}, selected(prompt))
            ctx = context_section(prompt)
            for name in unselected_names | {f'row_{j}' for j in range(7) if j != k - 1}:
                self.assertNotRegex(ctx, rf'\b{name}\b', (k, name))
            manifest = json.dumps(req['context_manifest'])
            for name in unselected_names:
                self.assertNotIn(f'"{name}"', manifest)
            self.assertNotIn('YOUR PREVIOUS ANSWER', prompt)          # every ask is a fresh first attempt
            self.assertEqual(0, req['sample'])
        grids = [o['value'] for o in report['outputs']]
        self.assertEqual([{'kind': 'grid', 'value': 7, 'x': 5, 'y': y, 'width': 20, 'height': 7}
                          for y in (6, 5, 4, 3, 2, 1, 0)], grids)

    def test_host_options_cannot_turn_on_solve_or_determination(self):
        compiled = E.compile_source(FALLING)
        worker = Worker(falling_rule)
        with tempfile.TemporaryDirectory() as folder:
            report = run(compiled, worker, folder, {'solve': True, 'determine': True, 'context': 'all'})
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(6, len(worker.requests))
        for k, req in enumerate(worker.requests, 1):
            self.assertEqual([f'row_{k - 1}'], list(selected(req['prompt'])))
        # a finite, uniquely determined ask would be answered by the kernel under host solve=true; the compiled
        # per-ask options keep it a model ask
        determined = E.compile_source('Ask for b as a whole number from 0 to 6: "Pick b.".\n'
                                      'Accept only if b equals 3.\nShow b.\n')
        worker = Worker(lambda *a: 3)
        with tempfile.TemporaryDirectory() as folder:
            report = run(determined, worker, folder, {'solve': True, 'determine': True})
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(1, len(worker.requests))
        self.assertEqual(1, report['calls'])

    def test_retry_feedback_reveals_no_unselected_value(self):
        compiled = E.compile_source(FALLING)

        def rule(statement, values, attempt):
            (name, value), = values.items()
            return 99 if attempt == 3 else int(value) - 1     # the third request (row 3) is wrong once
        worker = Worker(rule)
        with tempfile.TemporaryDirectory() as folder:
            report = run(compiled, worker, folder)
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(7, len(worker.requests))
        retry = worker.requests[3]['prompt']
        self.assertIn('YOUR PREVIOUS ANSWER WAS REJECTED', retry)
        self.assertIn("Accept only if 'row 3' equals 'row 2' minus 1.", retry)
        self.assertEqual({'row_2': '4'}, selected(retry))
        self.assertNotIn('height', context_section(retry))
        self.assertNotEqual(worker.requests[2]['key'], worker.requests[3]['key'])

    def test_exhausted_retries_fail_at_the_mapped_english_line(self):
        compiled = E.compile_source(FALLING, retries=1)
        worker = Worker(lambda statement, values, attempt: 99)
        with tempfile.TemporaryDirectory() as folder:
            report = run(compiled, worker, folder)
        self.assertEqual('failed', report['status'])
        self.assertEqual(2, len(worker.requests))           # one ask, one retry, nothing later dispatched
        line = report['error']['line']
        row = [r for r in compiled['source_map'] if r['native_line'] == line][0]
        stmt = compiled['statements'][row['statement'] - 1]
        self.assertEqual('accept', stmt['kind'])
        self.assertEqual("Accept only if 'row 1' equals 'row 0' minus 1.", stmt['text'])

    def test_model_produced_position_keeps_native_geometry_guard(self):
        text = ('Remember w is 4.\nAsk for col as a whole number: "Pick a column.".\n'
                'Display "*" at column col and row 0 on a grid w columns by 1 rows.\n')
        compiled = E.compile_source(text)
        for answer, status in ((3, 'done'), (4, 'failed'), (-1, 'failed')):
            with tempfile.TemporaryDirectory() as folder:
                report = run(compiled, Worker(lambda *a, v=answer: v), folder)
            self.assertEqual(status, report['status'], (answer, report.get('error')))
            if status == 'failed':
                self.assertEqual([], [o for o in report['outputs'] if isinstance(o['value'], dict)])

    def test_categorization_sees_only_the_message(self):
        compiled = E.compile_source(CATEGORIZE)

        def rule(statement, values, attempt):
            self.assertEqual(['message'], list(values))
            return 'complaint' if 'refund' in values['message'] else 'question'
        worker = Worker(rule)
        with tempfile.TemporaryDirectory() as folder:
            report = run(compiled, worker, folder)
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(1, len(worker.requests))
        prompt = worker.requests[0]['prompt']
        self.assertNotIn('Customer since 2019', prompt)
        self.assertNotIn('internal_note', prompt)
        self.assertEqual(['complaint'], [o['value'] for o in report['outputs']])
        schema = json.dumps(worker.requests[0]['schema'])
        for label in ('praise', 'complaint', 'question'):
            self.assertIn(label, schema)

    def test_categorization_label_outside_the_set_is_refused_natively(self):
        compiled = E.compile_source(CATEGORIZE, retries=1)
        worker = Worker(lambda *a: 'refund request')
        with tempfile.TemporaryDirectory() as folder:
            report = run(compiled, worker, folder)
        self.assertEqual('failed', report['status'])
        self.assertEqual([], report['outputs'])

    def test_bool_answers_are_not_numbers(self):
        compiled = E.compile_source('Ask for ok as yes or no: "Is it?".\nAccept only if ok equals yes.\nShow ok.\n',
                                    retries=0)
        for answer, status in ((True, 'done'), (1, 'failed'), ('yes', 'failed'), (False, 'failed')):
            with tempfile.TemporaryDirectory() as folder:
                report = run(compiled, Worker(lambda *a, v=answer: v), folder)
            self.assertEqual(status, report['status'], (answer, report.get('error')))

    def test_whole_number_answers_refuse_fractions(self):
        compiled = E.compile_source('Ask for n as a whole number: "n".\nShow n.\n', retries=0)
        for answer, status in ((3, 'done'), (2.5, 'failed'), (True, 'failed'), ('3.5', 'failed'), ('three', 'failed')):
            with tempfile.TemporaryDirectory() as folder:
                report = run(compiled, Worker(lambda *a, v=answer: v), folder)
            self.assertEqual(status, report['status'], (answer, report.get('error')))

    def test_replay_and_execution_pins_are_the_native_ones(self):
        compiled = E.compile_source(FALLING)
        with tempfile.TemporaryDirectory() as folder:
            first = run(compiled, Worker(falling_rule), folder)
            self.assertEqual('done', first['status'])
            locked = K.make_lock(folder)
            replayed = K.replay(locked)
        self.assertTrue(replayed['ok'], replayed)
        self.assertEqual(0, replayed['calls'])
        self.assertEqual(first['fingerprint'], replayed['fingerprint'])
        modules = {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest() for name in X.REQUIRED_FILES}
        pins = X.build(compiled['source'], compiled['inputs'], modules)
        worker = Worker(falling_rule)
        pinned = Run(compiled['source'], compiled['inputs'], worker,
                     {**compiled['options'], **OPTIONS, 'execution_pins': pins}).execute()
        self.assertEqual('done', pinned['status'], pinned.get('error'))
        self.assertEqual(first['fingerprint'], pinned['fingerprint'])
        drifted = Run(compiled['source'] + 'show 1.\n', {}, Worker(falling_rule),
                      {**compiled['options'], **OPTIONS, 'execution_pins': pins}).execute()
        self.assertEqual('failed', drifted['status'])
        self.assertEqual('SYM_VERSION', drifted['error']['code'])


if __name__ == '__main__':
    unittest.main()

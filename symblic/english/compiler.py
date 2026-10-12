"""Plain-English statements for Symblic: a bounded statement grammar compiled to an ordinary Symblic program.

What it is for: letting someone write a model-backed program as short English sentences instead of Symblic syntax,
while every model answer is still checked by code. Each English statement is one atomic instruction:

    Remember width is 20.                                   a value (no model)
    Ask for 'row 1' as a whole number: "Subtract 1 ...".   one model request, a fresh context per ask
    Using only 'row 0'.                                      the only values that request may see
    Accept only if 'row 1' equals 'row 0' minus 1.          a check; a failing answer is retried with the reason
    Display digit at column x and row 'row 1' on a grid ...  an output

`Ask for` becomes one native `ask` that sees only the names its `Using only` line selects (`from ...` with
`context=none`); each `Accept only if` becomes a native `ensure ... else retry`; `Display ... on a grid` becomes a
native `show` of a plain grid record. The result runs on the kernel's runner (symblic.kernel.run.Run: context
capsules, budgets, routing, retries, replay) unchanged. Two further grammars are recognized by their first words and
compiled by their own modules: "Build a character animation ..." (symblic.english.build) and labelled pixel documents
starting "STATEMENT ZERO ONE:" (symblic.english.pixels).

There is no model translator, no solver, no constructor and no precomputed answer: every `Ask for` remains a model
ask with `determine=false, solve=false`. The text is data. It is never evaluated, executed or passed to a shell.
Grammar and limits: docs/reference/ENGLISH-STATEMENTS.md.

Public functions: compile_source(text, retries=, max_calls=, budget=) -> the program, its options and a source map
from program lines back to English lines (raises EnglishError with the original line and column); check_source(text)
-> the same plus the kernel's static check, never raising for an author error; examples().
Depends on: symblic.kernel.language. Used by: symblic.english.authoring and .cli (the `english` command),
symblic.steps.construction, symblic.authoring.editor_diagnostics.
"""

from __future__ import annotations

# Pin the executing compiler, including stale-bytecode detection, before first-party imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import hashlib
import re
import unicodedata

from symblic.kernel import language as S

VERSION = 'symblic-english/1'

MAX_TEXT = 65_536              # characters of English input
MAX_STATEMENTS = 400
MAX_ASKS = 200
MAX_STRING = 4_000             # characters in one quoted text (instruction or literal)
MAX_NAME = 48
MAX_SELECTED = 16              # names in one Using only
MAX_ACCEPTS = 16               # Accept only if lines per ask
MAX_OPTIONS = 32
MAX_OPTION = 64
MAX_DIGITS = 30                # digits in one number literal part
MAX_GRID = 100                 # bounded browser renderer width/height
MAX_CELLS = 2500
MAX_NATIVE = 262_144           # characters of generated native source (native limit is 400 000)

RETRIES = (0, 5)               # native maximum is 5
MAX_CALLS = (0, 10_000)        # zero refuses model dispatch; matches native host bounds
BUDGET = (1_000, 100_000)      # native verified capsule characters (native accepts 0..16 MiB)

_BIDI = set('\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f')
# Bare one-word names that would read as a literal or an operator; quote a name to use one of these words.
_GRAMMAR_WORDS = frozenset(('yes', 'no', 'true', 'false', 'plus', 'minus', 'times', 'divided', 'by', 'and', 'or'))
_NATIVE_RESERVED = frozenset(
    set(S.BUILTINS) | set(S.CONSTANTS) | set(S.KEYWORDS) | set(S.WORD_OPS) | set(S.ASK_OPTIONS) |
    {'it', 'null', 'none', 'function', 'routine', 'import', 'test', 'observe', 'act', 'with', 'from', 'by',
     'where', 'each', 'then', 'to', 'up', 'words', 'length', 'places', 'kind', 'int', 'bool', 'record', 'list',
     'set', 'any', 'svg', 'drawing', 'object', 'else', 'retry', 'fail', 'warn', 'because', 'as', 'do'})
_NUM_RX = re.compile(r'-?(\d+)(?:\.(\d+))?(?:/(\d+))?')
_WORD_RX = re.compile(r'[^\W\d_]\w*')
_QNAME_RX = re.compile(r"[^\W_][\w \-]*")
_OPTION_RX = re.compile(r"[^\W_][\w '\-]*")


class EnglishError(ValueError):
    """An author error at a position in the ORIGINAL English text (1-based line and column)."""

    def __init__(self, code: str, message: str, line: int = 1, col: int = 1, native=None):
        super().__init__(message)
        self.code, self.message, self.line, self.col, self.native = code, message, line, col, native

    def as_dict(self) -> dict:
        out = {'line': self.line, 'col': self.col, 'code': self.code, 'message': self.message}
        if self.native is not None:
            out['native'] = copy.deepcopy(self.native)
        return out

    def __str__(self) -> str:
        return f'line {self.line}, column {self.col}: {self.message}'


def _err(code, message, tok=None, line=1, col=1):
    if tok is not None:
        line, col = tok.line, tok.col
    return EnglishError(code, message, line, col)


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

class Tok:
    __slots__ = ('col', 'kind', 'line', 'raw', 'value')

    def __init__(self, kind, value, line, col, raw=None):
        self.kind, self.value, self.line, self.col, self.raw = kind, value, line, col, raw

    def __repr__(self):
        return f'Tok({self.kind},{self.value!r},{self.line}:{self.col})'


def _check_char(ch, line, col):
    if ch in _BIDI:
        raise EnglishError('ENG_SYNTAX', f'bidirectional control character U+{ord(ch):04X} is not allowed', line, col)
    cat = unicodedata.category(ch)
    if (cat == 'Cc' and ch not in '\n\t') or cat in ('Cs', 'Co', 'Cn'):
        raise EnglishError('ENG_SYNTAX', f'control or unassigned character U+{ord(ch):04X} is not allowed', line, col)


def _normalize(text):
    if not isinstance(text, str):
        raise EnglishError('ENG_SYNTAX', 'the source must be text (str)')
    if len(text) > MAX_TEXT:
        raise EnglishError('ENG_LIMIT', f'the source is too long ({len(text)} characters; the limit is {MAX_TEXT})')
    text = text.removeprefix('﻿')
    text = text.replace('\r\n', '\n')
    if '\r' in text:
        before = text[:text.index('\r')]
        raise EnglishError('ENG_SYNTAX', 'a carriage return is only accepted as part of a CRLF line ending',
                           before.count('\n') + 1, len(before) - (before.rfind('\n') + 1) + 1)
    return text


def tokenize(text: str) -> list:
    toks, i, line, line_start, n = [], 0, 1, 0, len(text)
    statement_start = True
    while i < n:
        ch = text[i]
        col = i - line_start + 1
        if ch == '\n':
            line, line_start, i = line + 1, i + 1, i + 1
            continue
        if ch in ' \t':
            i += 1
            continue
        _check_char(ch, line, col)
        if ch == '#' and statement_start:
            while i < n and text[i] != '\n':
                _check_char(text[i], line, i - line_start + 1)
                i += 1
            continue
        statement_start = False
        if ch == '"':
            out, j, sl, sc = [], i + 1, line, col
            while True:
                if j >= n:
                    raise EnglishError('ENG_SYNTAX', 'unterminated quoted text (a closing " is missing)', sl, sc)
                c = text[j]
                if c == '"':
                    j += 1
                    break
                if c == '\\':
                    nxt = text[j + 1] if j + 1 < n else ''
                    mapped = {'"': '"', '\\': '\\', 'n': '\n', 't': '\t'}.get(nxt)
                    if mapped is None:
                        raise EnglishError('ENG_SYNTAX', 'unknown escape in quoted text (use \\" \\\\ \\n or \\t)',
                                           line, j - line_start + 1)
                    out.append(mapped)
                    if len(out) > MAX_STRING:
                        raise EnglishError('ENG_LIMIT', f'quoted text is longer than {MAX_STRING} characters', sl, sc)
                    j += 2
                    continue
                _check_char(c, line, j - line_start + 1)
                if c == '\n':
                    line, line_start = line + 1, j + 1
                out.append(c)
                j += 1
                if len(out) > MAX_STRING:
                    raise EnglishError('ENG_LIMIT', f'quoted text is longer than {MAX_STRING} characters', sl, sc)
            toks.append(Tok('str', ''.join(out), sl, sc))
            i = j
            continue
        if ch == "'":
            j = text.find("'", i + 1)
            k = text.find('\n', i + 1)
            if j < 0 or (0 <= k < j):
                raise EnglishError('ENG_SYNTAX', "unterminated quoted name (a closing ' is missing on this line)",
                                   line, col)
            raw = text[i + 1:j]
            for off, c in enumerate(raw):
                _check_char(c, line, col + 1 + off)
            if not _QNAME_RX.fullmatch(raw) or raw != raw.strip():
                raise EnglishError('ENG_NAME', "a quoted name has letters, digits, spaces, '-' and '_' only, and "
                                   'starts with a letter or digit', line, col)
            if len(raw) > MAX_NAME:
                raise EnglishError('ENG_LIMIT', f'a name is at most {MAX_NAME} characters', line, col)
            toks.append(Tok('qname', raw, line, col))
            i = j + 1
            continue
        if ch.isdigit() or (ch == '-' and i + 1 < n and text[i + 1].isdigit()):
            m = _NUM_RX.match(text, i)
            if m is None:
                raise EnglishError('ENG_SYNTAX', 'write numbers using decimal digits', line, col)
            end = m.end()
            if end < n and (text[end].isalnum() or text[end] in '_.') and not (
                    text[end] == '.' and (end + 1 >= n or not text[end + 1].isdigit())):
                raise EnglishError('ENG_SYNTAX', 'malformed number (write 7, -3, 0.5 or 3/4; no exponents, '
                                   'separators or trailing letters)', line, col)
            if any(part and len(part) > MAX_DIGITS for part in m.groups()):
                raise EnglishError('ENG_LIMIT', f'a number part has more than {MAX_DIGITS} digits', line, col)
            if m.group(3) is not None and (m.group(2) is not None or int(m.group(3)) == 0):
                raise EnglishError('ENG_SYNTAX', 'a fraction is two whole numbers with a non-zero denominator',
                                   line, col)
            toks.append(Tok('num', m.group(0), line, col))
            i = end
            continue
        m = _WORD_RX.match(text, i)
        if m:
            toks.append(Tok('word', m.group(0), line, col))
            i = m.end()
            continue
        if ch in ',:.':
            toks.append(Tok(ch, ch, line, col))
            i += 1
            if ch == '.':
                statement_start = True
            continue
        raise EnglishError('ENG_SYNTAX', f'unexpected character {ch!r}', line, col)
    return toks


def split_statements(toks: list, text: str) -> list:
    out, cur = [], []
    for t in toks:
        if t.kind == '.':
            if not cur:
                raise _err('ENG_SYNTAX', 'an empty statement (two periods in a row?)', t)
            out.append((cur, t))
            cur = []
        else:
            cur.append(t)
    if cur:
        raise _err('ENG_SYNTAX', 'this statement does not end with a period', cur[0])
    if len(out) > MAX_STATEMENTS:
        raise EnglishError('ENG_LIMIT', f'too many statements ({len(out)}; the limit is {MAX_STATEMENTS})')
    return out


# ---------------------------------------------------------------------------
# Statement parser (syntax only; names are resolved afterwards, in order)
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, toks, stop):
        self.toks, self.i, self.stop = toks, 0, stop

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def here(self):
        return self.peek() or self.stop

    def word(self, *words, k=0):
        t = self.peek(k)
        return t is not None and t.kind == 'word' and t.value.lower() in words

    def words(self, *seq):
        return all(self.word(w, k=j) for j, w in enumerate(seq))

    def expect_words(self, *seq, what=None):
        for w in seq:
            if not self.word(w):
                raise _err('ENG_SYNTAX', f'expected "{what or " ".join(seq)}"', self.here())
            self.i += 1

    def take(self):
        t = self.peek()
        if t is None:
            raise _err('ENG_SYNTAX', 'the statement ends too early', self.stop)
        self.i += 1
        return t

    def done(self):
        return self.i >= len(self.toks)

    def finish(self):
        if not self.done():
            raise _err('ENG_SYNTAX', f'unexpected {self.peek().value!r} before the period', self.peek())


def _name(c: _Cursor):
    t = c.peek()
    if t is None:
        raise _err('ENG_SYNTAX', 'expected a name', c.stop)
    if t.kind == 'qname':
        c.i += 1
        return {'name': t.value, 'tok': t}
    if t.kind == 'word':
        if t.value.lower() in _GRAMMAR_WORDS:
            raise _err('ENG_NAME', f'"{t.value}" is a grammar word; quote a name that uses it (\'{t.value} value\')',
                       t)
        if len(t.value) > MAX_NAME:
            raise _err('ENG_LIMIT', f'a name is at most {MAX_NAME} characters', t)
        c.i += 1
        return {'name': t.value, 'tok': t}
    raise _err('ENG_SYNTAX', 'expected a name (one word, or several words in single quotes)', t)


def _literal_at(c: _Cursor):
    t = c.peek()
    if t is None:
        return None
    if t.kind == 'num':
        c.i += 1
        return {'lit': _number(t), 'tok': t}
    if t.kind == 'str':
        c.i += 1
        return {'lit': ('text', t.value), 'tok': t}
    if t.kind == 'word' and t.value.lower() in ('yes', 'no', 'true', 'false'):
        c.i += 1
        return {'lit': ('bool', t.value.lower() in ('yes', 'true')), 'tok': t}
    return None


def _number(t):
    m = _NUM_RX.fullmatch(t.value)
    _whole, frac, den = m.groups()
    return ('whole' if frac is None and den is None else 'number', t.value)


def _term(c: _Cursor):
    lit = _literal_at(c)
    return lit if lit is not None else _name(c)


_OPS = {'plus': '+', 'minus': '-', 'times': '*', 'divided': '/'}
_COMPARE = (('does', 'not', 'equal'), ('equals',), ('is', 'at', 'least'), ('is', 'at', 'most'),
            ('is', 'more', 'than'), ('is', 'less', 'than'))
_COMPARE_NATIVE = {'does not equal': '!=', 'equals': '=', 'is at least': '>=', 'is at most': '<=',
                   'is more than': '>', 'is less than': '<'}


def _operand(c: _Cursor):
    left = _term(c)
    if c.word(*_OPS):
        op_tok = c.take()
        op = op_tok.value.lower()
        if op == 'divided':
            c.expect_words('by', what='divided by')
        right = _term(c)
        if c.word(*_OPS):
            raise _err('ENG_SYNTAX', 'only one arithmetic step (plus, minus, times or divided by) is allowed in one '
                       'operand; remember an intermediate value or ask for it instead', c.peek())
        return {'op': _OPS[op], 'word': op, 'left': left, 'right': right, 'tok': op_tok}
    return left


def _type(c: _Cursor):
    start = c.here()
    if c.word('a', 'an'):
        c.i += 1
    if c.words('whole', 'number'):
        c.i += 2
        return _ranged({'kind': 'whole'}, c)
    if c.word('number'):
        c.i += 1
        return _ranged({'kind': 'number'}, c)
    if c.word('text'):
        c.i += 1
        return {'kind': 'text'}
    if c.words('yes', 'or', 'no'):
        c.i += 3
        return {'kind': 'bool'}
    if c.words('one', 'of'):
        c.i += 2
        options = []
        while True:
            t = c.peek()
            if t is None or t.kind != 'str':
                raise _err('ENG_SYNTAX', 'expected an accepted label in double quotes', c.here())
            if not _OPTION_RX.fullmatch(t.value) or t.value != t.value.strip():
                raise _err('ENG_TYPE', "a label has letters, digits, spaces, ' - and _ only, and starts with a "
                           'letter or digit', t)
            if len(t.value) > MAX_OPTION:
                raise _err('ENG_LIMIT', f'a label is at most {MAX_OPTION} characters', t)
            if any(S._norm_option(t.value) == S._norm_option(o) for o in options):
                raise _err('ENG_TYPE', f'duplicate label "{t.value}" (labels differing only in case, spacing or '
                           'punctuation cannot be told apart)', t)
            if t.value.lower() in ('true', 'false'):
                raise _err('ENG_TYPE', 'true/false labels: ask "as yes or no" instead', t)
            options.append(t.value)
            c.i += 1
            if c.peek() is not None and (c.peek().kind == ',' or c.word('or')):
                c.i += 1
                if c.word('or'):
                    c.i += 1
                continue
            break
        if len(options) < 2 or len(options) > MAX_OPTIONS:
            raise _err('ENG_TYPE', f'one of needs 2 to {MAX_OPTIONS} labels', start)
        return {'kind': 'choice', 'options': options}
    raise _err('ENG_SYNTAX', 'expected an answer shape: a whole number, a number, text, yes or no, or one of "..."',
               start)


def _ranged(ty, c):
    if c.word('from'):
        c.i += 1
        lo = _literal_at(c)
        c.expect_words('to', what='from <number> to <number>')
        hi = _literal_at(c)
        for b, t in ((lo, c.here()), (hi, c.here())):
            if b is None or b['lit'][0] not in ('whole', 'number'):
                raise _err('ENG_TYPE', 'a range is "from <number> to <number>" with number literals',
                           (b or {}).get('tok') or t)
            if ty['kind'] == 'whole' and b['lit'][0] != 'whole':
                raise _err('ENG_TYPE', 'a whole-number range needs whole-number bounds', b['tok'])
            if '/' in b['lit'][1]:
                raise _err('ENG_TYPE', 'range bounds are written as whole or decimal numbers', b['tok'])
        if _value(lo['lit']) > _value(hi['lit']):
            raise _err('ENG_TYPE', 'the range is empty (from is larger than to)', lo['tok'])
        ty['range'] = (lo['lit'][1], hi['lit'][1])
    return ty


def parse_statement(toks, stop):
    c = _Cursor(toks, stop)
    head = toks[0]
    if c.word('remember'):
        c.i += 1
        name = _name(c)
        c.expect_words('is')
        lit = _literal_at(c)
        if lit is None:
            raise _err('ENG_SYNTAX', 'expected a value: a number, "quoted text", yes or no', c.here())
        c.finish()
        return {'kind': 'remember', 'name': name, 'lit': lit}
    if c.words('ask', 'for'):
        c.i += 2
        name = _name(c)
        c.expect_words('as')
        ty = _type(c)
        t = c.peek()
        if t is None or t.kind != ':':
            raise _err('ENG_SYNTAX', 'expected ":" and then the instruction in double quotes', c.here())
        c.i += 1
        instr = c.peek()
        if instr is None or instr.kind != 'str':
            raise _err('ENG_SYNTAX', 'expected the instruction in double quotes', c.here())
        if not instr.value.strip():
            raise _err('ENG_SYNTAX', 'the instruction is empty', instr)
        c.i += 1
        c.finish()
        return {'kind': 'ask', 'name': name, 'type': ty, 'instruction': instr.value, 'instr_tok': instr}
    if c.words('using', 'only'):
        c.i += 2
        names = [_name(c)]
        while not c.done():
            if c.peek().kind != ',' and not c.word('and'):
                raise _err('ENG_SYNTAX', 'separate selected names with commas or "and"', c.peek())
            if c.peek().kind == ',':
                c.i += 1
            if c.word('and'):
                c.i += 1
            names.append(_name(c))
        if len(names) > MAX_SELECTED:
            raise _err('ENG_LIMIT', f'Using only selects at most {MAX_SELECTED} names', head)
        return {'kind': 'using', 'names': names}
    if c.words('accept', 'only', 'if'):
        c.i += 3
        subject = _name(c)
        for seq in _COMPARE:
            if c.words(*seq):
                cmp_tok = c.peek()
                c.i += len(seq)
                break
        else:
            raise _err('ENG_SYNTAX', 'expected equals, does not equal, is at least, is at most, is more than or '
                       'is less than', c.here())
        right = _operand(c)
        c.finish()
        return {'kind': 'accept', 'subject': subject, 'cmp': ' '.join(seq), 'cmp_tok': cmp_tok, 'right': right}
    if c.word('show'):
        c.i += 1
        name = _name(c)
        c.finish()
        return {'kind': 'show', 'name': name}
    if c.word('display'):
        c.i += 1
        value = _term(c)
        c.expect_words('at', 'column')
        x = _term(c)
        c.expect_words('and', 'row')
        y = _term(c)
        c.expect_words('on', 'a', 'grid', what='on a grid')
        w = _term(c)
        c.expect_words('columns', what='columns')
        c.expect_words('by')
        h = _term(c)
        c.expect_words('rows', what='rows')
        c.finish()
        return {'kind': 'display', 'value': value, 'x': x, 'y': y, 'width': w, 'height': h}
    raise _err('ENG_SYNTAX', 'unknown statement: a statement starts with Remember, Ask for, Using only, '
               'Accept only if, Show or Display', head)


# ---------------------------------------------------------------------------
# Native rendering helpers
# ---------------------------------------------------------------------------

def native_string(text: str) -> str:
    """A native double-quoted string whose value (after interpolation parsing) is exactly `text`."""
    out = ['"']
    for ch in text:
        out.append({'\\': '\\\\', '"': '\\"', '\n': '\\n', '\t': '\\t', '{': '\\{', '}': '\\}'}.get(ch, ch))
    out.append('"')
    return ''.join(out)


def _value(lit):
    from fractions import Fraction
    kind, raw = lit
    if kind in ('whole', 'number'):
        if '/' in raw:
            a, b = raw.split('/')
            return Fraction(int(a), int(b))
        return Fraction(raw) if '.' in raw else int(raw)
    return raw


def _native_literal(lit) -> str:
    kind, raw = lit
    if kind == 'bool':
        return 'true' if raw else 'false'
    if kind == 'text':
        return native_string(raw)
    if '/' in raw or raw.startswith('-'):
        return f'({raw})'
    return raw


def native_id(name: str) -> str:
    slug = re.sub(r'[^0-9a-z]+', '_', unicodedata.normalize('NFKD', name).encode('ascii', 'ignore')
                  .decode('ascii').lower()).strip('_')
    if not slug:
        slug = 'name_' + hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]
    if slug[0].isdigit():
        slug = 'n_' + slug
    if slug in _NATIVE_RESERVED:
        slug += '_value'
    return slug


def _key(name: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', name).casefold().split())


_KIND_LABEL = {'whole': 'a whole number', 'number': 'a number', 'text': 'text', 'bool': 'yes or no',
               'choice': 'one of the labels'}


def _reads_answer_alone(operand) -> bool:
    """Whether an accept's comparison operand reads only literals: compared with the answer as its subject,
    the whole check is then a function of the answer alone (the case symblic.kernel.diagnose.answer_only sees)."""
    if 'lit' in operand:
        return True
    if 'name' in operand:
        return False
    return _reads_answer_alone(operand['left']) and _reads_answer_alone(operand['right'])


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class _Compiler:
    def __init__(self, text, retries, max_calls, budget):
        self.text, self.retries, self.max_calls, self.budget = text, retries, max_calls, budget
        self.lines: list = ['use profile=verified.']
        self.source_map: list = [{'native_line': 1, 'line': None, 'col': None, 'statement': None}]
        self.statements: list = []
        self.names: dict = {}          # key -> record
        self.ids: dict = {}            # native id -> key
        self.order: list = []
        self.definitions: dict = {}    # key -> (statement index, tok) of every definition, for "future" errors
        self.warnings: list = []      # author notes (an accept line the model can read on retry)
        self.open_ask = None
        self.asks = 0

    # -- names ----------------------------------------------------------
    def define(self, ref, kind, info, index, static=None):
        key = _key(ref['name'])
        if key in self.names:
            first = self.names[key]
            raise _err('ENG_NAME', f'"{ref["name"]}" is already defined at line {first["line"]}; a name is defined '
                       'once', ref['tok'])
        nid = native_id(ref['name'])
        if nid in self.ids:
            other = self.names[self.ids[nid]]
            raise _err('ENG_NAME', f'"{ref["name"]}" and "{other["readable"]}" (line {other["line"]}) both become '
                       f'the native name {nid}; rename one', ref['tok'])
        rec = {'readable': ref['name'], 'id': nid, 'kind': kind, 'line': ref['tok'].line, 'statement': index,
               'static': static}
        rec.update(info)
        self.names[key] = rec
        self.ids[nid] = key
        self.order.append(key)
        return rec

    def lookup(self, ref, index):
        key = _key(ref['name'])
        rec = self.names.get(key)
        if rec is None:
            later = self.definitions.get(key)
            if later is not None and later[0] >= index:
                raise _err('ENG_NAME', f'"{ref["name"]}" is not available yet: it is defined later, at line '
                           f'{later[1].line}', ref['tok'])
            raise _err('ENG_NAME', f'"{ref["name"]}" is not defined (define it first with Remember or Ask for)',
                       ref['tok'])
        return rec

    # -- typing ---------------------------------------------------------
    def operand_type(self, node, index):
        if 'lit' in node:
            kind = node['lit'][0]
            return {'kind': kind}, _native_literal(node['lit']), node['lit']
        if 'op' in node:
            parts = []
            for side in (node['left'], node['right']):
                ty, nat, _ = self.operand_type(side, index)
                if ty['kind'] not in ('whole', 'number'):
                    raise _err('ENG_TYPE', f'{node["word"]} needs numbers on both sides', side['tok'])
                parts.append((ty, nat))
            if node['op'] == '/' and 'lit' in node['right'] and _value(node['right']['lit']) == 0:
                raise _err('ENG_TYPE', 'division by zero', node['right']['tok'])
            kind = 'whole' if node['op'] != '/' and all(t['kind'] == 'whole' for t, _ in parts) else 'number'
            return {'kind': kind}, f'({parts[0][1]} {node["op"]} {parts[1][1]})', None
        rec = self.lookup(node, index)
        return rec['type'], rec['id'], rec.get('static')

    # -- emission -------------------------------------------------------
    def emit(self, native: str, stmt: dict, tok) -> int:
        self.lines.append(native)
        no = len(self.lines)
        self.source_map.append({'native_line': no, 'line': tok.line, 'col': tok.col, 'statement': stmt['index']})
        stmt['native_lines'].append(no)
        return no

    def close_ask(self):
        ask = self.open_ask
        if ask is None:
            return
        self.open_ask = None
        rec, stmt = ask['rec'], ask['stmt']
        ty = rec['type']
        native_ty = {'whole': 'Int', 'number': 'Number', 'text': 'Text', 'bool': 'Bool'}.get(ty['kind'])
        if ty['kind'] == 'choice':
            native_ty = 'one of {' + ', '.join('"' + o + '"' for o in ty['options']) + '}'
        elif 'range' in ty:
            lo, hi = ty['range']
            native_ty += f' in {lo}..{hi}'
        line = f'ask {rec["id"]}: {native_ty} {native_string(ask["instruction"])}'
        if ask['from']:
            line += ' from ' + ', '.join(r['id'] for r in ask['from'])
        line += (f' with context=none, determine=false, solve=false, retries={self.retries}, '
                 f'budget={self.budget}.')
        no = self.emit(line, stmt, ask['tok'])
        if ask['using'] is not None:
            ask['using']['native_lines'].append(no)
            self.source_map.append({'native_line': no, 'line': ask['using_tok'].line, 'col': ask['using_tok'].col,
                                    'statement': ask['using']['index']})
        for native, accept_stmt, tok in ask['ensures']:
            self.emit(native, accept_stmt, tok)
        rec.pop('pending', None)

    # -- statements -----------------------------------------------------
    def compile(self):
        toks = tokenize(self.text)
        parsed = []
        for index, (stoks, stop) in enumerate(split_statements(toks, self.text), 1):
            node = parse_statement(stoks, stop)
            node['tok'], node['stop'], node['index'] = stoks[0], stop, index
            parsed.append(node)
            if node['kind'] in ('remember', 'ask'):
                self.definitions.setdefault(_key(node['name']['name']), (index, node['name']['tok']))
        if not parsed:
            # comments and blank lines are not statements: a source of zero of them is not a program
            raise EnglishError('ENG_STRUCTURE', 'A program needs at least one statement.', 1, 1)
        for node in parsed:
            self.statement(node)
        self.close_ask()
        if self.asks > MAX_ASKS:
            raise EnglishError('ENG_LIMIT', f'too many asks ({self.asks}; the limit is {MAX_ASKS})')
        source = '\n'.join(self.lines) + '\n'
        if len(source) > MAX_NATIVE:
            raise EnglishError('ENG_LIMIT', f'the generated program is too long ({len(source)} characters; the limit '
                               f'is {MAX_NATIVE})')
        return source, parsed

    def statement(self, node):
        kind, tok = node['kind'], node['tok']
        start, stop = tok, node['stop']
        stmt = {'index': node['index'], 'line': start.line, 'col': start.col, 'end_line': stop.line,
                'end_col': stop.col, 'kind': kind, 'text': self._verbatim(start, stop), 'native_lines': []}
        self.statements.append(stmt)
        if kind in ('using', 'accept'):
            ask = self.open_ask
            if ask is None:
                raise _err('ENG_STRUCTURE', f'"{"Using only" if kind == "using" else "Accept only if"}" belongs to '
                           'an Ask for: write it directly after its Ask for statement', tok)
            stmt['ask'] = ask['rec']['id']
            return self.using(node, stmt, ask) if kind == 'using' else self.accept(node, stmt, ask)
        self.close_ask()
        getattr(self, kind)(node, stmt)

    def _verbatim(self, start, stop):
        lines = self.text.split('\n')
        if start.line == stop.line:
            return lines[start.line - 1][start.col - 1:stop.col]
        parts = [lines[start.line - 1][start.col - 1:]] + lines[start.line:stop.line - 1] + \
            [lines[stop.line - 1][:stop.col]]
        return '\n'.join(parts)

    def remember(self, node, stmt):
        lit = node['lit']['lit']
        rec = self.define(node['name'], 'remember', {'type': {'kind': lit[0]}}, node['index'], static=lit)
        self.emit(f'let {rec["id"]} = {_native_literal(lit)}.', stmt, node['tok'])

    def ask(self, node, stmt):
        self.asks += 1
        rec = self.define(node['name'], 'ask', {'type': node['type'], 'pending': True}, node['index'])
        self.open_ask = {'rec': rec, 'stmt': stmt, 'tok': node['tok'], 'instruction': node['instruction'],
                         'from': [], 'using': None, 'using_tok': None, 'ensures': []}

    def using(self, node, stmt, ask):
        if ask['using'] is not None:
            raise _err('ENG_STRUCTURE', 'this Ask for already has a Using only line; list every selected name in '
                       'one line', node['tok'])
        if ask['ensures']:
            raise _err('ENG_STRUCTURE', 'write Using only before the Accept only if lines of its Ask for',
                       node['tok'])
        seen = set()
        for ref in node['names']:
            rec = self.lookup(ref, node['index'])
            if rec is ask['rec']:
                raise _err('ENG_NAME', f'an ask cannot use its own answer "{ref["name"]}"', ref['tok'])
            if rec['id'] in seen:
                raise _err('ENG_NAME', f'"{ref["name"]}" is selected twice', ref['tok'])
            seen.add(rec['id'])
            ask['from'].append(rec)
        ask['using'], ask['using_tok'] = stmt, node['tok']

    def accept(self, node, stmt, ask):
        if len(ask['ensures']) >= MAX_ACCEPTS:
            raise _err('ENG_LIMIT', f'at most {MAX_ACCEPTS} Accept only if lines per ask', node['tok'])
        subject = self.lookup(node['subject'], node['index'])
        if subject is not ask['rec']:
            raise _err('ENG_STRUCTURE', f'Accept only if checks the answer of its own Ask for: expected '
                       f'"{ask["rec"]["readable"]}" here', node['subject']['tok'])
        sty = subject['type']
        rty, rnat, rstatic = self.operand_type(node['right'], node['index'])
        cmp = node['cmp']
        numeric = ('whole', 'number')
        right_tok = node['right']['tok']
        if cmp not in ('equals', 'does not equal') and (sty['kind'] not in numeric or rty['kind'] not in numeric):
            raise _err('ENG_TYPE', f'"{cmp}" compares numbers; {sty["kind"] if sty["kind"] in numeric else "this answer"}'
                       f' is {_KIND_LABEL[sty["kind"]]}', node['cmp_tok'])
        compatible = (sty['kind'] in numeric and rty['kind'] in numeric) or \
            (sty['kind'] in ('text', 'choice') and rty['kind'] in ('text', 'choice')) or \
            (sty['kind'] == rty['kind'] == 'bool')
        if not compatible:
            raise _err('ENG_TYPE', f'the answer is {_KIND_LABEL[sty["kind"]]} but this is '
                       f'{_KIND_LABEL[rty["kind"]]}', right_tok)
        if sty['kind'] == 'whole' and cmp in ('equals',) and rstatic is not None and rstatic[0] == 'number' \
                and _value(rstatic) != int(_value(rstatic)):
            raise _err('ENG_TYPE', 'a whole-number answer can never equal a fractional value', right_tok)
        if sty['kind'] == 'choice' and rstatic is not None and rstatic[0] == 'text' \
                and rstatic[1] not in sty['options']:
            raise _err('ENG_TYPE', f'"{rstatic[1]}" is not one of the accepted labels '
                       f'({", ".join(sty["options"])})', right_tok)
        native = (f'ensure {subject["id"]} {_COMPARE_NATIVE[cmp]} {rnat} else retry because '
                  f'{native_string(stmt["text"])}.')
        if _reads_answer_alone(node['right']):
            # with the answer as its subject, a check whose other side is all literals reads the answer
            # alone: retry feedback then carries its full text to the model
            self.warnings.append({
                'line': node['tok'].line, 'col': node['tok'].col, 'statement': stmt['index'],
                'code': 'ENG_ACCEPT_READABLE',
                'message': 'this accept line reads the answer alone, so on a retry the model is shown its '
                           'failed-check text (any value written here included); an accept line is a '
                           'specification the model can read, not a secret'})
        ask['ensures'].append((native, stmt, node['tok']))

    def show(self, node, stmt):
        rec = self.lookup(node['name'], node['index'])
        self.emit(f'show {rec["id"]}.', stmt, node['tok'])

    def display(self, node, stmt):
        index = node['index']
        _vty, vnat, _ = self.operand_type(node['value'], index)
        geo, guards = {}, []
        for field in ('width', 'height', 'x', 'y'):
            ref = node[field]
            ty, nat, static = self.operand_type(ref, index)
            if ty['kind'] != 'whole':
                raise _err('ENG_TYPE', f'the grid {field} must be a whole number, not {_KIND_LABEL[ty["kind"]]}',
                           ref['tok'])
            geo[field] = (nat, _value(static) if static is not None else None, ref['tok'])
        for field in ('width', 'height'):
            nat, val, t = geo[field]
            if val is not None and not 1 <= val <= MAX_GRID:
                raise _err('ENG_GEOMETRY', f'the grid {field} must be 1 to {MAX_GRID}, not {val}', t)
            if val is None:
                guards.append(f'{nat} >= 1 and {nat} <= {MAX_GRID}')
        for pos, size in (('x', 'width'), ('y', 'height')):
            nat, val, t = geo[pos]
            snat, sval, _ = geo[size]
            label = 'column' if pos == 'x' else 'row'
            if val is not None and val < 0:
                raise _err('ENG_GEOMETRY', f'the {label} must be at least 0, not {val}', t)
            if val is not None and sval is not None and val >= sval:
                raise _err('ENG_GEOMETRY', f'the {label} {val} is outside a grid {sval} {size} wide (positions '
                           f'count from 0 to {sval - 1})', t)
            if val is None or sval is None:
                guards.append(f'{nat} >= 0 and {nat} < {snat}')
        width, height = geo['width'], geo['height']
        if width[1] is not None and height[1] is not None:
            if width[1] * height[1] > MAX_CELLS:
                raise _err('ENG_GEOMETRY', f'the grid has more than {MAX_CELLS} cells', width[2])
        else:
            guards.append(f'{width[0]} * {height[0]} <= {MAX_CELLS}')
        if guards:
            self.emit(f'assert {" and ".join(guards)}.', stmt, node['tok'])
        record = (f'{{kind: "grid", value: {vnat}, x: {geo["x"][0]}, y: {geo["y"][0]}, '
                  f'width: {geo["width"][0]}, height: {geo["height"][0]}}}')
        self.emit(f'show {record}.', stmt, node['tok'])


def _int_option(name, value, bounds):
    lo, hi = bounds
    if type(value) is not int or not lo <= value <= hi:
        raise EnglishError('ENG_OPTION', f'{name} must be a whole number from {lo} to {hi}')
    return value


def _native_position(row_line, compiled):
    rows = [r for r in compiled['source_map'] if r['native_line'] == row_line and r['line'] is not None]
    if rows:
        return rows[0]['line'], rows[0]['col'], rows[0]['statement']
    return 1, 1, None


def _verify_roundtrip(source, compiled, parsed):
    """Natively parse the generated program; refuse unless every instruction and `because` text is intact."""
    try:
        prog = S.parse(source, execution_profile='verified')
    except S.SymblicError as exc:
        line, col, _ = _native_position(exc.line, compiled)
        raise EnglishError('ENG_NATIVE', f'the native parser refused the generated program: {exc.message}',
                           line, col, native=exc.as_dict()) from None
    asks = [s for s in prog['statements'] if s.k == 'ask']
    wanted = [n['instruction'] for n in parsed if n['kind'] == 'ask']
    got = [''.join(p for p in s.parts) if all(isinstance(p, str) for p in s.parts) else None for s in asks]
    if got != wanted:
        raise RuntimeError('symblic.english.compiler: an instruction did not survive native parsing verbatim')
    return prog


def is_construction_source(text):
    return isinstance(text, str) and text.removeprefix('\ufeff').lstrip().lower().startswith('build a character animation ')


# The files (paths from the repository root) whose bytes identify the compiler a pixel document was compiled with;
# symblic.english.authoring.compiler_digest hashes them into the run's authoring record.
PIXEL_COMPILER_FILES = ('symblic/english/pixels.py', 'symblic/english/pixel_checks.py',
                        'symblic/spec/sheets.py', 'symblic/spec/build.py', 'symblic/spec/contracts.py')
CONSTRUCTION_COMPILER_FILES = ('symblic/english/build.py',)


def is_pixel_source(text):
    """Recognize the labelled display grammar without importing an optional lane."""
    return (isinstance(text, str) and re.match(
        r'\A\s*STATEMENT\s+ZERO[ -]+ONE\s*:', text.removeprefix('\ufeff'), re.IGNORECASE) is not None)


def compiler_dependencies(text):
    """Pin the exact support bundle used by the selected English grammar."""
    if is_pixel_source(text):
        from symblic.kernel import execution_pins as execution
        return tuple(sorted(set(PIXEL_COMPILER_FILES) | execution.REQUIRED_FILES))
    return CONSTRUCTION_COMPILER_FILES if is_construction_source(text) else ()


def compile_source(text, *, retries=2, max_calls=64, budget=12000, artifacts=None) -> dict:
    """English statements -> {version, source_sha256, source, options, inputs, names, statements, warnings,
    source_map}. Raises EnglishError (with the original line/column) for any author error."""
    retries = _int_option('retries', retries, RETRIES)
    max_calls = _int_option('max_calls', max_calls, MAX_CALLS)
    budget = _int_option('budget', budget, BUDGET)
    normalized = _normalize(text)
    try:
        original_sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    except UnicodeEncodeError as exc:
        before = text[:exc.start]
        raise EnglishError('ENG_SYNTAX', 'the source contains an unpaired surrogate code point',
                           before.count('\n') + 1, len(before) - (before.rfind('\n') + 1) + 1) from None
    if is_pixel_source(normalized):
        try:
            from symblic.english import pixels as pixels
        except ImportError:
            raise EnglishError('ENG_UNAVAILABLE', 'English pixel programs need symblic.english.pixels, which did not import.') from None
        options = {'retries': retries, 'max_calls': max_calls, 'budget': budget}
        if artifacts is not None:
            options['artifacts'] = artifacts
        return pixels.compile_source(text, **options)
    if artifacts is not None:
        raise EnglishError('ENG_RECOVERY', 'Retained pixel work requires a labelled English pixel program.')
    if is_construction_source(normalized):
        try:
            from symblic.english import build as build
        except ImportError:
            raise EnglishError('ENG_UNAVAILABLE', 'English construction needs symblic.english.build, which did not import.') from None
        return build.compile_source(text, retries=retries, max_calls=max_calls, budget=budget)
    comp = _Compiler(normalized, retries, max_calls, budget)
    source, parsed = comp.compile()
    result = {
        'version': VERSION,
        'source_sha256': original_sha,
        'source': source,
        'options': {'profile': 'verified', 'context': 'none', 'determine': False, 'solve': False,
                    'constructor': 'off', 'max_calls': max_calls},
        'inputs': {},
        'names': {comp.names[k]['readable']: comp.names[k]['id'] for k in comp.order},
        'statements': comp.statements,
        'warnings': comp.warnings,
        'source_map': sorted(comp.source_map, key=lambda r: (r['native_line'], r['statement'] or 0)),
    }
    _verify_roundtrip(source, result, parsed)
    return result


def check_source(text, *, retries=2, max_calls=64, budget=12000) -> dict:
    """Compile, then run the native static check. Never raises for an author error."""
    try:
        compiled = compile_source(text, retries=retries, max_calls=max_calls, budget=budget)
    except EnglishError as exc:
        return {'ok': False, 'errors': [exc.as_dict()], 'warnings': [], 'compiled': None, 'native': None}
    native = S.check(compiled['source'], execution_profile='verified')
    errors, warnings = [], []
    for row in compiled.get('warnings') or []:
        warnings.append({'line': row['line'], 'col': row['col'], 'statement': row.get('statement'),
                         'code': row['code'], 'message': row['message']})
    for bucket, out in ((native.get('errors', []), errors), (native.get('warnings', []), warnings)):
        for row in bucket:
            line, col, statement = _native_position(row.get('line') or 0, compiled)
            out.append({'line': line, 'col': col, 'statement': statement,
                        'code': 'ENG_NATIVE' if out is errors else 'ENG_NATIVE_WARNING',
                        'message': row.get('message', ''), 'native': copy.deepcopy(row)})
    return {'ok': bool(native.get('ok')) and not errors, 'errors': errors, 'warnings': warnings,
            'compiled': compiled, 'native': native}


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

def _falling():
    rows = ['Remember digit is 7.', 'Remember width is 20.', 'Remember height is 7.', 'Remember x is 5.',
            "Remember 'row 0' is 6.",
            "Display digit at column x and row 'row 0' on a grid width columns by height rows."]
    for k in range(1, 7):
        rows += ['',
                 (f"Ask for 'row {k}' as a whole number: \"Subtract 1 from the numeric CONTEXT value "
                  f"named row_{k - 1}. Return the difference.\"."),
                 f"Using only 'row {k - 1}'.",
                 f"Accept only if 'row {k}' equals 'row {k - 1}' minus 1.",
                 f"Accept only if 'row {k}' is at least 0.",
                 f"Accept only if 'row {k}' is at most height minus 1.",
                 f"Display digit at column x and row 'row {k}' on a grid width columns by height rows."]
    return '\n'.join(rows) + '\n'


EXAMPLES = {
    'falling-number': {
        'title': 'Falling digit: six fresh model asks, each checked, each frame displayed',
        'source': _falling(),
    },
    'categorize': {
        'title': 'Categorize a remembered message into a fixed set of labels',
        'source': (
            'Remember message is "The package arrived crushed and two plates were broken. I would like a '
            'refund.".\n'
            'Remember \'internal note\' is "Customer since 2019; do not show this to the classifier.".\n'
            '\n'
            'Ask for category as one of "praise", "complaint", "question": "Classify the customer message into '
            'exactly one category.".\n'
            'Using only message.\n'
            'Show category.\n'),
    },
}


def examples() -> dict:
    return copy.deepcopy(EXAMPLES)

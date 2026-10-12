"""Editor diagnostics: line-and-column ranges for a source text, from Symblic's own checkers.

What it is for: an editor (the web studio's, or any other) that underlines problems as someone types. check(source,
language='native'|'english'|'paper') runs the matching checker (the kernel's static check, the English compiler, or
the paper checker of symblic.authoring.paper) and returns its errors and warnings as ranges in the exact original
source. Offsets use UTF-16 code units (the browser textarea convention); line and column coordinates count Unicode code
points. A line-only or unmapped diagnostic never acquires guessed token precision.

No run, model, capability, subprocess, network or store is used. The kernel's checker keeps its bounded pure static
lint, including empty-answer predicate probes. Acceptance is not execution or proof of the author's intent.

Depends on: symblic.kernel.language, symblic.english.compiler, symblic.lang.abstraction, symblic.authoring.paper.
Used by: an editor route of a host (the original host's web studio underlined problems with it, through
web/studio/symblic-editor-diagnostics.js).
"""
from __future__ import annotations

import hashlib
import re
from bisect import bisect_right

from symblic.kernel import language as S
from symblic.english import compiler as EN
from symblic.lang import abstraction as symblic_lang  # noqa: F401  (inert native extension registration)
from symblic.authoring import paper as PAPER

VERSION = 1
MAX_BYTES = 400_000
MAX_DIAGNOSTICS = 200
MAX_MESSAGE = 4000
LANGUAGES = ('native', 'english', 'paper')
SCOPE = {
    'execution': 'not_run', 'provider_calls': 0, 'effects': 'not_run',
    'authority': 'existing_source_checkers',
    'static_lint': 'existing_bounded_pure_predicate_probes',
    'meaning': 'Syntax, available static checks and authoring warnings; not runtime correctness or intent adequacy.',
}


class _Source:
    def __init__(self, source):
        self.text = source
        self.starts, self.ends, self.rows = [], [], []
        start = 0
        for match in re.finditer(r'\r\n|\r|\n', source):
            self.starts.append(start)
            self.ends.append(match.start())
            self.rows.append(source[start:match.start()])
            start = match.end()
        self.starts.append(start)
        self.ends.append(len(source))
        self.rows.append(source[start:])
        # One linear pass, so many diagnostics cannot repeatedly rescan the file.
        self.utf16 = [0]
        for ch in source:
            self.utf16.append(self.utf16[-1] + (2 if ord(ch) > 0xffff else 1))

    def position(self, line, col):
        if type(line) is not int or not 1 <= line <= len(self.rows):
            return None
        if type(col) is not int or not 1 <= col <= len(self.rows[line - 1]) + 1:
            return None
        return self.starts[line - 1] + col - 1

    def range(self, line, col, token_ends=None, *, line_only=False):
        empty = {'line': 0, 'col': 0, 'start': None, 'end': None, 'position_kind': 'none'}
        if type(line) is not int or not 1 <= line <= len(self.rows):
            return empty
        if line_only or not col:
            a, b = self.starts[line - 1], self.ends[line - 1]
            return {'line': line, 'col': 1, 'start': self.utf16[a], 'end': self.utf16[b],
                    'position_kind': 'line' if b > a else 'point'}
        a = self.position(line, col)
        if a is None:
            # Keep the reliable line when a producer's column cannot be mapped.
            return self.range(line, 0, line_only=True)
        b = (token_ends or {}).get(a, a)
        return {'line': line, 'col': col, 'start': self.utf16[a], 'end': self.utf16[b],
                'position_kind': 'token' if b > a else 'point'}


def _token_end(text, start, tok, english):
    """Only extend tokens the authoritative lexer identified at this position."""
    if start >= len(text):
        return start
    if tok.kind in ('name', 'word', 'num'):
        value = str(tok.value)
        return start + len(value) if text.startswith(value, start) else start
    if english and tok.kind == 'qname':
        raw = "'" + tok.value + "'"
        return start + len(raw) if text.startswith(raw, start) else start
    if tok.kind == 'str':
        if text[start] not in ('"', "'") or (english and text[start] != '"'):
            return start
        if english:
            i = start + 1
            while i < len(text):
                if text[i] == '\\':
                    i += 2
                elif text[i] == '"':
                    return i + 1
                else:
                    i += 1
            return start
        try:
            value, end, last_line = S._read_string(text, start, tok.line, tok.col)
        except S.SymblicError:
            return start
        # Native multiline string tokens currently report their ending line.
        # Such a coordinate is not a reliable token start, so never extend it.
        return end if value == tok.value and last_line == tok.line else start
    if tok.kind in ('.', ',', ':') and text.startswith(tok.kind, start):
        return start + 1
    if tok.kind in ('stop', 'attr') and text.startswith('.', start):
        return start + 1
    if tok.kind == 'op':
        for op in S.OPERATORS:
            if text.startswith(op, start) and S.CANON_OP.get(op, op) == tok.value:
                return start + len(op)
    return start


def _tokens(source, english=False, view=None):
    """Original code-point start -> end; lexer failures leave honest point marks."""
    view = view or _Source(source)
    normalized = source.replace('\r\n', '\n').replace('\r', '\n')
    bom = 1 if english and normalized.startswith('\ufeff') else 0
    if bom:
        normalized = normalized[1:]
    chunks, line_map = [], {}
    if english:
        try:
            chunks.append(EN.tokenize(normalized))
        except EN.EnglishError:
            return {}, {}
    else:
        try:
            statements = S.split_statements(source)
        except S.SymblicError:
            return {}, {}
        for text, line, kind in statements:
            if kind != 'formal':
                continue
            cursor = line - 1
            for offset, raw in enumerate(text.split('\n')):
                while cursor < len(view.rows) and view.rows[cursor] != raw:
                    cursor += 1
                if cursor >= len(view.rows):
                    break
                line_map[line + offset] = cursor + 1
                cursor += 1
            try:
                chunks.append(S.tokenize(text, line))
            except S.SymblicError:
                continue
    found = {}
    for chunk in chunks:
        for tok in chunk:
            actual_line = line_map.get(tok.line, tok.line)
            col = tok.col + (bom if actual_line == 1 else 0)
            start = view.position(actual_line, col)
            if start is None:
                continue
            end = _token_end(source, start, tok, english)
            if end > start:
                found[start] = end

    return found, line_map


def _paper_check(source, profile):
    """The existing paper compiler/lints and native checker, retaining its map."""
    try:
        compiled = PAPER.compile_paper(source)
    except PAPER.PaperError as exc:
        return {'ok': False, 'errors': [exc.as_dict()], 'warnings': [], 'plan': []}, None
    native = S.check(compiled['source'], execution_profile=profile)

    def move(row):
        row = dict(row)
        if row.get('line'):
            pos = PAPER.paper_line(compiled, row['line'])
            row['program_line'], row['line'] = row['line'], pos['paper_line']
            row['section'] = pos['section_title']
        return row

    plan = [move(row) for row in native.get('plan', []) if row.get('kind') not in ('use', 'let') or
            not str(row.get('label', '')).startswith(('let section_', f'let {PAPER.DEFINITIONS_BINDING}', 'use'))]
    reply = {'ok': native['ok'], 'title': compiled['title'], 'name': compiled['title'],
             'errors': [move(row) for row in native['errors']],
             'warnings': compiled['warnings'] + PAPER.lint(source) + [move(row) for row in native['warnings']],
             'plan': plan, 'terms': compiled['terms'], 'sections': compiled['sections'],
             'asks': native.get('asks', 0), 'asks_detail': [move(row) for row in native.get('asks_detail', [])],
             'predictability': native.get('predictability'), 'profile': native.get('profile')}
    return reply, compiled


def _diagnostic(row, severity, language, view, tokens, compiled=None, native_lines=None):
    line, col = row.get('line', 0), row.get('col', 0)
    line_only = not col or (language != 'english' and col == 1)
    if language == 'native':
        line = (native_lines or {}).get(line, line)
    if language == 'english':
        if 'native' in row:
            # Compiler rows identify original statements, not the token at the
            # generated native column. An unmapped native row is truly unplaced.
            if not row.get('statement'):
                line, col = 0, 0
            line_only = True
        elif line == 1 and view.text.startswith('\ufeff') and col:
            col += 1
    elif language == 'paper' and 'program_line' in row and compiled:
        program_line = compiled['_editor_position_lines'].get(row['program_line'], row['program_line'])
        mapping = compiled['map'][program_line - 1] if 0 < program_line <= len(compiled['map']) else {}
        line = mapping.get('paper_line', 0)
        if mapping.get('kind') == 'code' and col:
            native_row = compiled['_editor_rows'][program_line - 1]
            original = view.rows[line - 1] if type(line) is int and 1 <= line <= len(view.rows) else ''
            removed = len(original) - len(native_row)
            if removed >= 0 and original[removed:] == native_row:
                col += removed
            else:
                line_only = True
        else:
            line_only = True
    elif language == 'paper':
        # Paper quantity lint may normalize prose before reporting columns. Its
        # original line is reliable; do not claim exact character precision.
        line_only = True
    if language != 'english' and type(line) is int and 1 <= line <= len(view.rows):
        raw_line = view.rows[line - 1]
        first_token_col = len(raw_line) - len(raw_line.lstrip(' \t')) + 1
        # Native static errors often point at the statement's opening keyword,
        # including its indentation, rather than the offending name or option.
        # Keep that anchor line-scoped; an interior parser position stays exact.
        if col == first_token_col:
            line_only = True
    position = view.range(line, col, tokens, line_only=line_only)
    kind = str(row.get('kind') or ('warning' if severity == 'warning' else 'check'))
    return {'severity': severity, 'code': str(row.get('code') or 'SYM_' + kind.upper())[:160],
            'message': str(row.get('message', ''))[:MAX_MESSAGE], 'source': language, **position}


def check(source, language='native', *, execution_profile=None):
    """Check exact source for an editor; bad source is data, never an exception.

    ``available=False``/``ok=None`` means checking did not finish; it must not be
    shown as a passing document. ``check`` preserves the existing checker shape
    for plan/input rendering, with its diagnostic arrays bounded to the same cap.
    """
    reply = {'version': VERSION, 'language': language if type(language) is str else None,
             'source_sha256': None, 'source_length_utf16': None, 'offset_encoding': 'utf-16',
             'available': True, 'ok': False, 'diagnostics': [], 'check': None, 'truncated': False,
             'limits': {'source_bytes': MAX_BYTES, 'diagnostics': MAX_DIAGNOSTICS, 'message_chars': MAX_MESSAGE},
             'scope': dict(SCOPE)}

    def refuse(code, message, *, unavailable=False):
        reply['available'] = not unavailable
        reply['ok'] = None if unavailable else False
        reply['diagnostics'] = [{'severity': 'info' if unavailable else 'error', 'code': code,
                                 'message': message, 'source': reply['language'], 'line': 0, 'col': 0,
                                 'start': None, 'end': None, 'position_kind': 'none'}]
        return reply

    if type(source) is not str:
        return refuse('EDITOR_SOURCE_TYPE', 'Source must be exact Unicode text.')
    if len(source) > MAX_BYTES:
        return refuse('EDITOR_SOURCE_LIMIT', f'Editor checking is limited to {MAX_BYTES} UTF-8 bytes.')
    try:
        raw = source.encode('utf-8')
    except UnicodeError:
        return refuse('EDITOR_UNICODE', 'Source contains an unpaired Unicode surrogate; checking is unavailable.',
                      unavailable=True)
    reply['source_sha256'] = hashlib.sha256(raw).hexdigest()
    reply['source_length_utf16'] = len(source.encode('utf-16-le')) // 2
    if len(raw) > MAX_BYTES:
        return refuse('EDITOR_SOURCE_LIMIT', f'Editor checking is limited to {MAX_BYTES} UTF-8 bytes.')
    if language not in LANGUAGES or type(language) is not str:
        return refuse('EDITOR_LANGUAGE', 'Choose native, english or paper source.')
    if execution_profile is not None and (type(execution_profile) is not str or
                                          execution_profile not in ('legacy', 'explicit', 'verified')):
        return refuse('EDITOR_PROFILE', 'Choose legacy, explicit or verified profile.')
    try:
        view, compiled = _Source(source), None
        if language == 'english':
            checked = EN.check_source(source)
        elif language == 'paper':
            checked, compiled = _paper_check(source, execution_profile)
        else:
            checked = S.check(source, execution_profile=execution_profile)
        if type(checked) is not dict or type(checked.get('ok')) is not bool:
            raise ValueError('malformed checker reply')
        positioned = any(type(row) is dict and type(row.get('col')) is int and row['col'] > 1
                         for key in ('errors', 'warnings') for row in checked.get(key, [])[:MAX_DIAGNOSTICS])
        tokens, native_lines = (_tokens(source, english=language == 'english', view=view)
                                if positioned and language != 'paper' else ({}, {}))
        # Paper prose is not native syntax. Restrict token extents to mapped code
        # lines, applying the exact indentation removed by the paper compiler.
        if compiled:
            native_view = _Source(compiled['source'])
            native_tokens, position_lines = (_tokens(compiled['source'], view=native_view)
                                              if positioned else ({}, {}))
            compiled['_editor_rows'] = native_view.rows
            compiled['_editor_position_lines'] = position_lines
            for start, end in native_tokens.items():
                nl = bisect_right(native_view.starts, start)
                row = compiled['map'][nl - 1]
                if row['kind'] != 'code' or end > native_view.ends[nl - 1]:
                    continue
                pl = row['paper_line']
                original, native = view.rows[pl - 1], native_view.rows[nl - 1]
                removed = len(original) - len(native)
                if removed < 0 or original[removed:] != native:
                    continue
                base = view.starts[pl - 1] + removed
                a = native_view.starts[nl - 1]
                tokens[base + start - a] = base + end - a

        count = 0
        for bucket, severity in (('errors', 'error'), ('warnings', 'warning')):
            rows = checked.get(bucket, [])
            if type(rows) is not list:
                raise ValueError('malformed diagnostic bucket')
            for row in rows:
                if type(row) is not dict or type(row.get('message')) is not str:
                    raise ValueError('malformed diagnostic')
                if count < MAX_DIAGNOSTICS:
                    reply['diagnostics'].append(_diagnostic(row, severity, language, view, tokens, compiled, native_lines))
                count += 1
        reply['truncated'] = count > MAX_DIAGNOSTICS
        reply['available'], reply['ok'] = True, checked['ok']
        # Return detached top-level arrays, without pretending omitted warnings
        # were never generated. English nested native diagnostics are bounded too.
        checked = dict(checked)
        checked['errors'] = checked.get('errors', [])[:MAX_DIAGNOSTICS]
        checked['warnings'] = checked.get('warnings', [])[:MAX_DIAGNOSTICS]
        if type(checked.get('native')) is dict:
            checked['native'] = dict(checked['native'])
            for name in ('errors', 'warnings'):
                checked['native'][name] = checked['native'].get(name, [])[:MAX_DIAGNOSTICS]
        reply['check'] = checked
        return reply
    except Exception:  # noqa: BLE001  (API boundary: failed checking must remain visibly unavailable)
        # No traceback or source contents in a client error. A broken helper is
        # visibly unavailable, never a clean bill of health or a source error.
        return refuse('EDITOR_UNAVAILABLE', 'Source checking did not finish. Try Check again; the program was not run.',
                      unavailable=True)

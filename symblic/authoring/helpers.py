"""Authoring help around the kernel's own parsers: a grammar catalog, syntax and reference checks, and command menus.

What it is for: helping a person or an agent write Symblic text that the real parsers accept, before anything runs.
It never replaces those parsers; it asks them. It offers:

- catalog() / export_grammar(entry): scoped EBNF grammars for three entry points, `program` (a portable subset of the
  language), `formula` (logic formulas) and `proof-command` (one proof step), shipped in grammar/ with parser
  conformance examples (grammar/conformance.json). The EBNF is guidance for authors and agents, not an executable
  decoding grammar; AUTHORITY names the parser that decides.
- check(text, entry=..., session=None): run the authoritative parser for that entry (and the kernel's static check
  for programs) and return its diagnostics.
- command_menu(session, choices): check caller-authored proof commands against one unchanged proof session, so an
  agent can be offered a menu of exactly-checked options.

No provider, evaluator, proof append, store, grammar engine or kernel registration. Syntax and reference acceptance
never establishes that an inference is valid or that a program does what its author meant.

Command line: python3 -m symblic.authoring.helpers catalog | export --entry NAME [--format ebnf] |
check FILE [--entry NAME] | menu CHOICES.json --session SESSION.json   (also `tools/symblic grammar ...`).
Depends on: symblic.kernel (language, profiles), symblic.lang.abstraction and symblic.adapters (proof,
proof_command, proof_session, proof_steps). Used by: symblic.authoring.workcards, symblic.steps.construction,
symblic.delegate.contracts, symblic.english.cli.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from symblic.kernel import language as S
from symblic.lang import abstraction as L
from symblic.kernel import profiles as PROFILES
from symblic.adapters import proof as P
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W

VERSION = 1
MAX_BYTES = 262144
MAX_DEPTH = 64
MAX_NODES = 20000
MAX_MENU = 32
MAX_WORK = P.MAX_WORK
# The authoring grammars (scoped EBNF guidance) and their parser conformance examples ship with this package.
GRAMMAR_DIR = Path(__file__).resolve().parent / 'grammar'
GRAMMARS = {'program': 'program-subset.ebnf', 'formula': 'formula.ebnf', 'proof-command': 'proof-command.ebnf'}
# The parser that decides each entry, named by a stable identifier. These strings are hashed into menu and delegation
# contract identities (frozen in tests/fixtures/symblic_delegate_v*_parity.json), so they keep the parsers' original
# flat module names: 'symblic.parse' is symblic.kernel.language.parse, 'symblic_proof.parse_formula' is
# symblic.adapters.proof.parse_formula and 'symblic_proof_command.parse' is symblic.adapters.proof_command.parse.
AUTHORITY = {'program': 'symblic.parse', 'formula': 'symblic_proof.parse_formula',
             'proof-command': 'symblic_proof_command.parse'}


class AuthoringError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise AuthoringError(code, message)


def _raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(text):
    if type(text) is not str:
        _fail('text_type', 'Expected exact Unicode text.')
    if len(text) > MAX_BYTES:
        _fail('byte_limit', 'Input exceeds the authoring byte limit.')
    try:
        raw = text.encode('utf-8')
    except UnicodeError:
        _fail('unicode', 'Unpaired Unicode surrogate.')
    if len(raw) > MAX_BYTES:
        _fail('byte_limit', 'Input exceeds the authoring UTF-8 byte limit.')
    return raw


def _json_copy(value):
    """Bound exact JSON before calling a parser; iterator frames use O(depth) space."""
    remaining, text_bytes, active = MAX_NODES, 0, set()

    def children(item):
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    _fail('json_type', 'JSON object keys must be exact strings.')
                yield key
                yield child
        else:
            yield from item

    frames = [(iter((value,)), -1, None)]
    while frames:
        iterator, parent_depth, ident = frames[-1]
        try:
            item = next(iterator)
        except StopIteration:
            frames.pop()
            if ident is not None:
                active.remove(ident)
            continue
        depth = parent_depth + 1
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            _fail('structure_limit', 'JSON depth/node limit exceeded.')
        typ = type(item)
        if typ is str:
            text_bytes += len(_text(item))
            if text_bytes > MAX_BYTES:
                _fail('byte_limit', 'Aggregate JSON text exceeds the byte limit.')
        elif item is None or typ is bool:
            pass
        elif typ is int:
            if item.bit_length() > 4096:
                _fail('integer_limit', 'JSON integer exceeds the bit limit.')
        elif typ in (dict, list):
            if len(item) > remaining:
                _fail('structure_limit', 'JSON container exceeds the remaining node limit.')
            if id(item) in active:
                _fail('cycle', 'Cyclic input is not JSON.')
            active.add(id(item))
            frames.append((iter(children(item)), depth, id(item)))
        else:
            _fail('json_type', 'Use exact plain JSON values; no floats or custom containers.')
    raw = _raw(value)
    if len(raw) > MAX_BYTES:
        _fail('byte_limit', 'Encoded JSON exceeds the authoring byte limit.')
    return json.loads(raw)


def _entry(entry):
    if type(entry) is not str or entry not in GRAMMARS:
        _fail('entry', 'Choose program, formula or proof-command.')
    return entry


def _read(path, limit=MAX_BYTES):
    # O_NONBLOCK avoids waiting on a FIFO before its type can be inspected.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            _fail('file_type', 'Input must be a regular file.')
        if info.st_size > limit:
            _fail('byte_limit', 'File exceeds the byte limit before reading.')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            _fail('byte_limit', 'File grew beyond the byte limit.')
        return raw
    finally:
        os.close(fd)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _fail('duplicate_key', 'JSON objects must not repeat a key.')
        out[key] = value
    return out


def _load_json(path):
    try:
        value = json.loads(_read(path).decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail('json_type', 'Nonfinite JSON number.'))
    except RecursionError:
        _fail('structure_limit', 'JSON nesting exceeds the decoder limit.')
    return _json_copy(value)


def _grammar(entry):
    return _read(GRAMMAR_DIR / GRAMMARS[_entry(entry)]).decode('utf-8')


def _versions():
    return {'language': S.VERSION, 'canonical': S.CANON_VERSION, 'profiles': PROFILES.VERSION,
            'module_logic': L.MODULE_LOGIC_VERSION, 'proof': P.VERSION, 'proof_steps': W.VERSION,
            'proof_session': R.VERSION, 'proof_command': C.VERSION,
            'unicode_database': S.unicodedata.unidata_version}


def catalog():
    """Detached versioned syntax/limit catalogue; no parsing or execution of user code."""
    entries = {name: {'authority': AUTHORITY[name], 'ebnf_sha256': _sha(_grammar(name).encode('utf-8')),
                     'ebnf_scope': 'portable_authoring_subset' if name == 'program' else 'controlled_surface_with_side_conditions'}
               for name in GRAMMARS}
    body = {
        'version': VERSION,
        'versions': _versions(),
        'entries': entries,
        'core': {'keywords': list(S.KEYWORDS), 'registered_extensions': sorted(S.EXTENSIONS),
                 'ask_options': list(S.ASK_OPTIONS), 'use_options': list(S.USE_OPTIONS),
                 'operator_aliases': dict(sorted(S.CANON_OP.items())),
                 'reserved_expression_words': sorted(S.WORD_OPS),
                 'builtin_callable_name_exclusions': sorted(S.BUILTINS),
                 'profiles': ['legacy', 'explicit', 'verified'], 'default_authoring_profile': 'verified'},
        'proof_commands': C.rules(),
        'examples': {
            'program': 'use profile=verified, context=none, coercion=strict.\ngiven data: Text.\nask answer: Bool "Decide from {data}." from data.\nshow answer.\n',
            'formula': '"A" implies ("B" and "A")',
            'proof-command': 'premise NAME',
            'proof_command_requirement': 'Replace NAME with an exact premise key from the original current session.'},
        'conformance': {'file': 'symblic/authoring/grammar/conformance.json',
                        'sha256': _sha(_read(GRAMMAR_DIR / 'conformance.json')),
                        'scope': 'finite_examples_not_exhaustive_language_or_semantic_proof'},
        'bounds': {'input_utf8_bytes': MAX_BYTES, 'json_depth': MAX_DEPTH, 'json_nodes': MAX_NODES,
                   'menu_choices': MAX_MENU, 'shared_proof_work_units': MAX_WORK,
                   'core_source_characters': S.MAX_SOURCE, 'core_parser_depth': S.MAX_DEPTH,
                   'formula_depth': P.MAX_DEPTH, 'formula_atom_characters': P.MAX_TEXT,
                   'proof_session_lines': W.MAX_STEPS,
                   'command_utf8_bytes': min(MAX_BYTES, C.MAX_COMMAND_BYTES)},
        'assurance': {'ebnf': 'guidance_not_an_executable_decoding_grammar',
                      'parser': 'existing_implementation_is_authoritative',
                      'execution': 'not_run', 'inference_validity': 'not_checked',
                      'proof_completion': 'not_checked', 'intent_fidelity': 'not_checked',
                      'provider_schema_support': 'not_established'},
    }
    body['contract_id'] = _sha(_raw(body))
    return body


def export_grammar(entry='program'):
    entry = _entry(entry)
    cat = catalog()
    return {'version': VERSION, 'contract_id': cat['contract_id'], 'entry': entry,
            **cat['entries'][entry], 'format': 'ebnf', 'text': _grammar(entry),
            'assurance': cat['assurance']}


class _Work:
    def __init__(self):
        self.used = 0

    def __call__(self, amount=1):
        self.used += amount
        if self.used > MAX_WORK:
            _fail('work_limit', 'Shared proof-parser work budget exhausted.')


def _result(entry):
    return {'version': VERSION, 'versions': _versions(), 'ok': False, 'entry': entry, 'authority': AUTHORITY.get(entry),
            'parser_status': 'not_established', 'reference_status': 'not_applicable',
            'inference_validity': 'not_checked', 'proof_completion': 'not_checked',
            'execution': 'not_run', 'provider_calls': 0}


def _refusal(result, error):
    result['parser_status'] = 'refused'
    if result.get('entry') == 'proof-command':
        result['reference_status'] = 'not_established'
    if isinstance(error, S.SymblicError):
        result['error'] = error.as_dict()
    else:
        code = 'structure_limit' if isinstance(error, RecursionError) else getattr(error, 'code', str(error))
        result['error'] = {'code': code, 'message': str(error)[:1000]}
    return result


def check(text, *, entry='program', profile='verified', session=None):
    """Call the real bounded parser. No evaluator, proof append, search or model call."""
    result = _result(entry if type(entry) is str else None)
    try:
        entry = _entry(entry)
        raw = _text(text)
        result['text_sha256'] = _sha(raw)
        if type(profile) is not str or profile not in ('legacy', 'explicit', 'verified'):
            _fail('profile', 'Unknown execution profile.')
        if entry != 'program' and profile != 'verified':
            _fail('profile', 'Execution profiles apply only to program parsing.')
        if entry != 'proof-command' and session is not None:
            _fail('session', 'Only proof-command parsing accepts a session.')
        if entry == 'program':
            parsed = S.parse(text, execution_profile=profile)
            result.update(profile=parsed['execution_profile'], warnings=parsed['warnings'],
                          top_level_statements=len(parsed['statements']))
        elif entry == 'formula':
            result['formula'] = P.parse_formula(text)
        else:
            if session is None:
                _fail('session', 'Supply the original current proof session for reference checks.')
            bounded = _json_copy(session)
            work = _Work()
            result['candidate'] = C.parse(bounded, text, tick=work)
            result.update(reference_status='accepted', session_sha256=_sha(_raw(bounded)),
                          proof_work_units=work.used)
        result.update(ok=True, parser_status='accepted', text_sha256=_sha(raw))
    except (AuthoringError, S.SymblicError, P.ProofError, RecursionError) as error:
        return _refusal(result, error)
    return result


def command_menu(session, choices):
    """Export a finite caller-authored string enum; never enumerate rules or proof paths.

    All choices are checked against the same original session. A syntactically
    legal but invalid inference remains in the menu: append must still reject it.
    The schema does not assert that a provider supports or enforces it.
    """
    result = _result('proof-command')
    result['operation'] = 'caller_authored_command_menu'
    try:
        if type(choices) is not list or not 1 <= len(choices) <= MAX_MENU:
            _fail('menu_limit', 'Supply 1..32 exact caller-authored commands.')
        if any(type(command) is not str for command in choices):
            _fail('text_type', 'Every menu choice must be exact text.')
        for command in choices:
            _text(command)
        if len(set(choices)) != len(choices):
            _fail('duplicate_command', 'Do not repeat an exact command.')
        request = _json_copy({'session': session, 'choices': choices})
        original, commands = request['session'], request['choices']
        work = _Work()
        candidates = [C.parse(original, command, tick=work) for command in commands]
        schema = {'type': 'string', 'enum': list(commands)}
        result.update(ok=True, parser_status='accepted', reference_status='accepted',
                      session_sha256=_sha(_raw(original)), choices_sha256=_sha(_raw(commands)),
                      choices=list(commands), candidates=candidates, schema=schema,
                      native_answer_schema={'type': 'object', 'additionalProperties': False,
                                            'required': ['answer'], 'properties': {'answer': schema}},
                      schema_scope='exact_caller_authored_command_strings',
                      provider_schema_support='not_established', proof_work_units=work.used)
        result['menu_id'] = _sha(_raw(result))
    except (AuthoringError, S.SymblicError, P.ProofError, RecursionError) as error:
        return _refusal(result, error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('catalog', 'export', 'check', 'menu'))
    parser.add_argument('path', nargs='?', help='UTF-8 source for check; JSON command list for menu')
    parser.add_argument('--entry', choices=tuple(GRAMMARS), default=None)
    parser.add_argument('--profile', choices=('legacy', 'explicit', 'verified'), default='verified')
    parser.add_argument('--session', help='Original current proof-session JSON for command checking/menu')
    parser.add_argument('--format', choices=('json', 'ebnf'), default='json')
    parser.add_argument('--agent-json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command in ('catalog', 'export'):
            if args.path or args.session or args.profile != 'verified':
                _fail('arguments', 'catalog/export accept no source, session or profile overrides.')
            if args.command == 'catalog' and args.entry is not None:
                _fail('arguments', 'catalog contains all entries; do not select one.')
            if args.command == 'catalog' and args.format != 'json':
                _fail('arguments', 'catalog uses JSON; export can emit EBNF.')
            result = catalog() if args.command == 'catalog' else export_grammar(args.entry or 'program')
            if args.command == 'export' and args.format == 'ebnf' and not args.agent_json:
                print(result['text'], end='')
                return 0
        else:
            if not args.path or args.format != 'json':
                _fail('arguments', 'check/menu require a file and JSON output.')
            if args.command == 'menu':
                if not args.session or args.profile != 'verified' or args.entry not in (None, 'proof-command'):
                    _fail('arguments', 'menu requires --session and uses the proof-command entry.')
                result = command_menu(_load_json(args.session), _load_json(args.path))
            else:
                result = check(_read(args.path).decode('utf-8'), entry=args.entry or 'program', profile=args.profile,
                               session=_load_json(args.session) if args.session else None)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result.get('ok', True) else 1
    except (AuthoringError, OSError, ValueError, RecursionError) as error:
        entry = 'proof-command' if args.command == 'menu' else args.entry
        if entry is None and args.command in ('check', 'export'):
            entry = 'program'
        result = _refusal(_result(entry), error)
        if args.command == 'menu':
            result['operation'] = 'caller_authored_command_menu'
        print(json.dumps(result, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

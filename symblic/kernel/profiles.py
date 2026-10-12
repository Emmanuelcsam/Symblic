"""Execution profiles (legacy, explicit, verified) and auditable coercion of model answers.

A program may declare `use profile=verified.` (a host may strengthen the declared profile, never weaken it).
validate() checks a parsed program against its profile: explicit and verified programs refuse implicit model
calls, and in verified mode a function cannot invoke a routine (a model call), directly or through other
functions; effects() computes those call summaries without running anything. coerce() reads a model's answer
into its declared type and records every change it made (rounding a Number to N places, de-duplicating a
set); strict coercion refuses changes the type did not declare (extra fields, scalar retyping, fuzzy key or
choice matching).

Legacy programs keep their syntax and behaviour. These are execution contracts, not estimates of truth or
model reliability. No I/O on import.

Depends on: symblic.kernel.language. Used by: symblic.kernel.language (check and read_answer) and the
authoring helpers.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json

from symblic.kernel import language as S

VERSION = 2
PROFILES = ('legacy', 'explicit', 'verified')


def resolve(program, requested=None):
    """A host may strengthen the declared profile, never weaken it."""
    declared = []
    for statement in S.walk(program['statements']):
        if statement.k == 'use' and 'profile' in statement.options:
            value = statement.options['profile']
            if value.k not in ('name', 'lit', 'str'):
                raise S.SymblicError('profile must be a literal legacy, explicit or verified',
                                     statement.line, statement.col, 'profile')
            label = S._opt_text(value)
            if label not in PROFILES:
                raise S.SymblicError('profile must be legacy, explicit or verified',
                                     statement.line, statement.col, 'profile')
            if statement not in program['statements']:
                raise S.SymblicError('profile is a program declaration, not a block option',
                                     statement.line, statement.col, 'profile')
            declared.append(label)
    if len(set(declared)) > 1:
        raise S.SymblicError('a program cannot change its execution profile', kind='profile')
    if requested is not None and requested not in PROFILES:
        raise S.SymblicError('unknown execution profile', kind='profile')
    return max([declared[0] if declared else 'legacy', requested or 'legacy'], key=PROFILES.index)


def effects(program):
    """Conservative, fixed-point callable effect summaries; no callable executes."""
    definitions = {}
    for node in S.walk(program['statements']):
        if node.k in ('function', 'routine'):
            definitions.setdefault(node.name, []).append(node)
    direct, dependencies = {}, {}
    kinds = {'ask': 'model', 'observe': 'observe', 'act': 'act', 'delegate': 'delegate',
             'fact': 'state', 'rule': 'state', 'show': 'output', 'draw': 'output',
             'forget': 'state', 'pin': 'state'}
    for name, nodes in definitions.items():
        found, calls = set(), set()
        for definition in nodes:
            # Definitions in different lexical scopes are conservatively joined.
            if definition.k == 'routine':
                found.add('routine')
            body = definition.value if definition.k == 'function' else definition.body
            defaults = [p['default'] for p in getattr(definition, 'specs', []) if p['default'] is not None]
            for node in S.walk([body, defaults]):
                if node.k in kinds:
                    found.add(kinds[node.k])
                if node.k == 'call':
                    if node.fn in definitions:
                        calls.add(node.fn)
                    elif node.fn in S.SPECULATION_DENIED:
                        found.add('external_adapter')
                    elif node.fn not in S.BUILTINS:
                        found.add('unresolved')
        direct[name], dependencies[name] = found, calls
    for _ in range(len(direct) + 1):
        changed = False
        for name in sorted(direct):
            expanded = direct[name] | set().union(*(direct[d] for d in dependencies[name]))
            if expanded != direct[name]:
                direct[name] = expanded
                changed = True
        if not changed:
            break
    return {name: sorted(value) or ['pure'] for name, value in sorted(direct.items())}


def diagnostics(program, profile):
    errors, warnings = [], []
    summaries = effects(program)
    for node in S.walk(program['statements']):
        if node.k == 'ask' and getattr(node, 'prose', False):
            row = {'line': node.line, 'col': node.col, 'kind': 'profile', 'code': 'SYM_IMPLICIT_ASK',
                   'message': 'implicit prose executes a model call; write an explicit typed ask'}
            (warnings if profile == 'legacy' else errors).append(row)
        if node.k == 'function':
            found = set(summaries.get(node.name, [])) - {'pure'}
            if found:
                row = {'line': node.line, 'col': node.col, 'kind': 'effect', 'code': 'SYM_FUNCTION_EFFECT',
                       'message': f'function {node.name} has effects: {", ".join(sorted(found))}'}
                (errors if profile == 'verified' and found - {'unresolved'} else warnings).append(row)
        if node.k == 'show' and getattr(node, 'bare', False) and (node.value.k in ('cmp', 'and', 'or') or
                node.value.k == 'lit' and isinstance(node.value.value, bool)):
            warnings.append({'line': node.line, 'code': 'SYM_BOOLEAN_QUERY',
                             'message': 'this expression displays a value; use assert to require it to be true'})
    return errors, warnings, summaries


def validate(program, requested=None):
    profile = resolve(program, requested)
    errors, warnings, summaries = diagnostics(program, profile)
    if errors:
        first = errors[0]
        raise S.SymblicError(first['message'], first['line'], first.get('col', 1), first['kind'])
    return profile, warnings, summaries


def _digest(value):
    # Raw JSON identity preserves keys and scalar types that coercion can erase.
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':'))
    except (ValueError, TypeError, RecursionError):
        raise S.SymblicError('model answer is not bounded finite JSON', kind='type') from None
    if len(text) > S.MAX_CODE * 4:
        raise S.SymblicError('model answer exceeds the transformation receipt limit', kind='type')
    return hashlib.sha256(text.encode()).hexdigest()


def coerce(value, ty, *, policy='legacy', receipt=None):
    """Type-directed coercion with visible changes; strict refuses undeclared loss.

    Rounding requested by Number to N places and set deduplication are declared
    equivalences. Extra fields, scalar retyping and fuzzy key/enum matching are
    not declared by a type, so strict mode refuses them.
    """
    if policy not in ('legacy', 'strict'):
        raise S.SymblicError('coercion must be legacy or strict', kind='type')
    raw_hash = _digest(value)
    changes, dropped = [], []

    def record(path, rule, lossy=False):
        changes.append({'path': path, 'rule': rule, 'declared': not lossy})
        if policy == 'strict' and lossy:
            raise S.SymblicError(f'{path}: undeclared transformation {rule}; provide the exact declared shape',
                                 kind='type')

    def inspect(raw, schema, path, depth=0):
        if depth > S.MAX_DEPTH:
            raise S.SymblicError('model answer is nested too deeply', kind='type')
        kind = schema['k']
        if kind in ('list', 'set', 'record') and isinstance(raw, str):
            record(path, 'decode_json_container', True)
            try:
                raw = json.loads(raw)
            except ValueError:
                return
        if kind == 'record' and isinstance(raw, dict):
            expected = {name: child for name, child in schema['fields']}
            for key, item in raw.items():
                match = [name for name in expected if str(key).strip().casefold() == name.casefold()]
                if not match:
                    dropped.append(f'{path}.{key}')
                    record(f'{path}.{key}', 'drop_extra_field', True)
                elif key != match[0]:
                    record(f'{path}.{key}', 'normalize_field_name', True)
                if match:
                    inspect(item, expected[match[0]], f'{path}.{match[0]}', depth + 1)
        elif kind in ('list', 'set') and isinstance(raw, list):
            for index, item in enumerate(raw):
                inspect(item, schema['of'], f'{path}[{index}]', depth + 1)
        elif kind == 'bool' and type(raw) is not bool:
            record(path, 'coerce_boolean', True)
        elif kind == 'text' and not isinstance(raw, str):
            record(path, 'coerce_text', True)
        elif kind == 'enum' and (not isinstance(raw, str) or raw not in schema['options']):
            record(path, 'normalize_option', True)
        elif kind in ('number', 'int') and isinstance(raw, str):
            # Exact numeric strings are the rational wire format, not fuzzy prose.
            if not S._NUM_IN_TEXT.fullmatch(raw.strip()):
                record(path, 'extract_number_from_prose', True)

    inspect(value, ty, 'answer')
    canonical = S.coerce(value, ty)
    if S.canon_json(S.from_json(value)) != S.canon_json(canonical) and not changes:
        changes.append({'path': 'answer', 'rule': 'declared_type_canonicalization', 'declared': True})
    if receipt is not None:
        receipt.update({'version': VERSION, 'policy': policy, 'raw_sha256': raw_hash,
                        'canonical_sha256': S.fingerprint(canonical), 'changes': changes,
                        'dropped_paths': dropped})
    return canonical

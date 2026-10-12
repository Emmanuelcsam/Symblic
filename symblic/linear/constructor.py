"""Linear constructor: let an SMT solver propose the answer to an `ask` whose checks are linear arithmetic.

What it is for
    Some asks need no model. When every `ensure ... else retry` check anchored to an ask is a linear
    (in)equality or a Boolean combination of them over the answer's integer, rational and Boolean fields, an
    SMT solver can construct values that satisfy the checks. This module compiles exactly that fragment of a
    program into a small JSON form (never SMT-LIB text, never Python), sends it to a separate,
    resource-limited worker process (worker.py) that runs Z3, and accepts a proposed value only after the
    native kernel has re-evaluated the original checks on it: the report's disposition is then
    'validated_candidate'. At most two assignments are constructed. The solver's "unsat" and "unique" verdicts
    are reported as solver claims only ('independently_proved': False); they are never treated as the
    kernel's own exhaustive results. Anything outside the fragment is refused with a fixed code from REASONS.

    Entry points
        assess(source, inputs, enabled=True, runtime=...)   a whole small program: `given`s, one `ask`, then
                                                            untyped `let`/`ensure` statements
        assess_ask(ask, ty, plan, constants, bound=, defaults=, ...)   one ask inside a running program; this is
                                                            the seam symblic.constructor.core uses
        prepare_source / prepare_ask                        compile the fragment without solving
        validate_witness                                    re-check one value with the native kernel

    Command line: python3 -m symblic.linear.constructor PROGRAM.sym --enable --runtime runtime.json

The solver runtime (optional)
    Z3 is not a dependency of this repository. The worker loads exactly one pinned package (z3-solver
    4.15.4.0, hashes in symblic/linear/z3-requirements.lock) from a private virtual environment, and only if
    every file matches the runtime record you pass (runtime.json: python, python_sha256, worker_sha256,
    z3_version, the package's file hashes and its site-packages path). tools/scripts/symblic_linear_provision.py
    writes that record for an environment you installed yourself. Without a runtime the report says
    'solver_unavailable' and nothing runs. resources.py can additionally refuse to start the worker unless the
    process runs in a memory-capped cgroup (combined_memory=True).

History
    The development notes call this prototype "D10" (an item of the determinism plan), version 2 after a
    review of the first version: every native field of the accepted statements is gated before the worker
    starts, binding names follow the native rules, statuses come from the one REASONS table, the worker's
    bounds are enforced before dispatch, witness text is exact, only the anchored contract becomes solver
    constraints, and limits are compared without float conversion. Profile strings containing "d10" are kept
    because recorded journals contain them.

Depends on: symblic.kernel.language and symblic.kernel.evidence (and z3-solver inside the worker only).
Used by: symblic.constructor.core (journaled construction inside a Run). Status: prototype. The tests drive it
with fake runtimes and fake workers (tests/constructor); the real Z3 path was only exercised on the development
machine and is not part of the automated tests.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import argparse
import hashlib
import json
import math
import os
import re
import selectors
import stat
import subprocess
import tempfile
import time
import threading
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from symblic.kernel import language as S

VERSION = 2
WORKER_PROTOCOL = 3
DEFAULT_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024
MAX_ADDRESS_SPACE_BYTES = 320 * 1024 * 1024
REAP_SECONDS = 2
MAX_BYTES = 65536
MAX_NODES = 4096
MAX_DEPTH = 32
MAX_VARS = 16
MAX_CHECKS = 64
MAX_CHAIN = 64                    # worker: an 'all' list holds 1..64 formulas
MAX_BITS = 256
MAX_OUTPUT = 65536
MAX_SECONDS = 5
MAX_MILLISECONDS = 5000           # worker: requested milliseconds 1..5000
MAX_WORK = 1_000_000
MAX_PACKAGE_FILES = 256           # worker package_check: 1..256 pinned files
MAX_PACKAGE_FILE_BYTES = 40_000_000
MAX_PACKAGE_BYTES = 64_000_000
MAX_PATH_TEXT = 4096              # worker: purelib text length
MAX_NAME = 128
MAX_DETAIL = 256
PACKAGE_DIRS = ('z3', 'z3_solver-4.15.4.0.dist-info')
Z3_VERSION = '4.15.4'
PROFILE = 'verified'              # the execution profile the prototype parses and checks with
BASE = Path(__file__).resolve().parent
_WORKER_LOCK = threading.Lock()


class WorkerCleanupError(BaseException):
    """Owned worker could not be reaped: caller must stop, never fall back."""


class _CallbackRaised(BaseException):
    def __init__(self, cause):
        self.cause = cause


def _stop(check_stop):
    if check_stop is not None:
        result = check_stop()
        if result is not None:
            raise TypeError('check_stop must return None or raise')


def _lifecycle_begin(lifecycle):
    """Optional trusted-host facts, retained on exceptions; never caller-supplied authority or raw buffers."""
    if lifecycle is None:
        return None
    if type(lifecycle) is not dict or lifecycle:
        raise TypeError('lifecycle must be a fresh empty exact dict or None')
    lifecycle.update(version=1, dispatched=False, reaped=None, request_sha256=None, request_bytes=None,
                     requested_milliseconds=None, requested_resource_limit=None,
                     requested_address_space_bytes=None, raw_sha256=None, raw_bytes=None,
                     capture_complete=False, stdout_observed_bytes=0, stderr_observed_bytes=0, returncode=None)
    return lifecycle


def _launch_unknown(lifecycle):
    return lifecycle is not None and lifecycle['dispatched'] is None


def _address_space_ok(value):
    return type(value) is int and 64 * 1024 * 1024 <= value <= MAX_ADDRESS_SPACE_BYTES and value % (1024 * 1024) == 0


def _strict_json(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ValueError('duplicate JSON key')
            out[key] = value
        return out
    def constant(value):
        raise ValueError('nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)

# The one table that decides a status. A refusal or failure carries one of these codes; native or
# exception text only ever goes to the bounded `detail` field and never selects the status.
REASONS = {
    # host input, native front end and fragment gate (before any worker starts)
    'enabled_requires_bool': 'unsupported',
    'invalid_resource_limits': 'unsupported',
    'invalid_stop_callback': 'unsupported',
    'worker_busy': 'unavailable',
    'combined_memory_refused': 'unavailable',
    'native_error': 'unsupported',             # a native SymblicError; `native_kind` carries its kind
    'native_recursion': 'unsupported',
    'native_check_error': 'unsupported',       # an error diagnostic from native S.check
    'native_input_binding': 'unsupported',     # the native Run would bind a different given value
    'native_binding_name': 'unsupported',      # a name native S.check / Run._bind refuses
    'invalid_binding_name': 'unsupported',     # not a single native name token
    'duplicate_binding': 'unsupported',
    'shadowed_answer': 'unsupported',
    'source_budget': 'unsupported',
    'source_encoding': 'unsupported',
    'input_budget': 'unsupported',
    'input_or_ask_mapping': 'unsupported',
    'literal_host_inputs_required': 'unsupported',
    'given_default': 'unsupported',
    'source_outside_single_ask_fragment': 'unsupported',
    'single_anchored_ask_required': 'unsupported',
    'resolved_type_required': 'unsupported',
    'resolved_type_mismatch': 'unsupported',     # the host's resolved type is not native resolve_type(ask.type)
    'plan_shape': 'unsupported',
    'no_anchored_check': 'unsupported',
    'check_budget': 'unsupported',
    'between_budget': 'unsupported',
    'check_mapping': 'unsupported',
    'unanchored_hard_check': 'unsupported',
    'unsupported_between_statement': 'unsupported',
    'unsupported_node_field': 'unsupported',
    'unsupported_interpolation': 'unsupported',
    'unsupported_ask_option': 'unsupported',
    'unsupported_ask_source': 'unsupported',
    'unsupported_because': 'unsupported',
    'typed_or_weighted_intermediate': 'unsupported',
    'predicate_not_boolean': 'unsupported',
    'constant_budget': 'unsupported',
    'requires_exact_number': 'unsupported',
    'number_budget': 'unsupported',
    'unsupported_type': 'unsupported',
    'unsupported_type_modifier': 'unsupported',
    'unsupported_type_bound': 'unsupported',
    'unsupported_record': 'unsupported',
    'duplicate_or_invalid_field': 'unsupported',
    'native_record_field': 'unsupported',      # a field the native answer matcher can never return as declared
    'seam_context_required': 'unsupported',    # assess_ask without the host's binding table and ask defaults
    'seam_context': 'unsupported',             # a malformed or inconsistent binding table / defaults
    'native_rebinding': 'unsupported',         # the ask or a let rebinds a name bound before the ask
    'program_ask_defaults': 'unsupported',     # program `use` defaults that the native Run applies to this ask
    'variable_budget': 'unsupported',
    'ast_budget': 'unsupported',
    'ast_cycle': 'unsupported',
    'text_budget': 'unsupported',
    'unsupported_host_value': 'unsupported',
    'unsupported_ast_node': 'unsupported',
    'unbound_or_nonliteral_constant': 'unsupported',
    'unsupported_field': 'unsupported',
    'operator_type': 'unsupported',
    'nonlinear_product': 'unsupported',
    'variable_or_zero_divisor': 'unsupported',
    'unsupported_operator': 'unsupported',
    'comparison_type': 'unsupported',
    'comparison_chain_budget': 'unsupported',
    # request bounds the host enforces before dispatch (the worker's check_tree/main bounds)
    'structure_budget': 'unsupported',
    'wire_budget': 'unsupported',
    'non_json_key': 'unsupported',
    'non_json_value': 'unsupported',
    # missing or mismatched solver/runtime
    'solver_unavailable': 'unavailable',
    'runtime_configuration': 'unavailable',
    'solver_unavailable_or_version': 'unavailable',
    'runtime_unreadable': 'unavailable',
    'runtime_source_budget': 'unavailable',
    'runtime_package_budget': 'unavailable',
    'solver_source_drift': 'unavailable',
    'worker_launch_failed': 'unavailable',
    # deadline expiries
    'preflight_timeout': 'timeout',
    'worker_timeout': 'timeout',
    'validation_timeout': 'timeout',
    # worker failure or an invalid/unvalidated reply
    'worker_refused_or_failed': 'unknown',
    'worker_output_budget': 'unknown',
    'invalid_solver_response': 'unknown',
    'invalid_solver_limits': 'unknown',
    'duplicate_solver_witness': 'unknown',
    'witness_variables': 'unknown',
    'boolean_witness_type': 'unknown',
    'integer_witness_type': 'unknown',
    'invalid_rational_witness': 'unknown',
    'noncanonical_rational_witness': 'unknown',
    'witness_number_budget': 'unknown',
    'witness_failed_native_type': 'unknown',
    'witness_failed_native_predicate': 'unknown',
    'witness_native_error': 'unknown',
    'prepared_contract_drift': 'unknown',
    'internal_error': 'unknown',
}


def _detail(text):
    try:
        return str(text)[:MAX_DETAIL]
    except Exception:  # noqa: BLE001 - a detail must never replace the typed reason
        return ''


class Unsupported(ValueError):
    """A typed refusal or failure. `str(exc)` is its REASONS code; `detail` is bounded diagnostic text only."""

    def __init__(self, code, detail=None, native_kind=None):
        if code not in REASONS:
            code, detail = 'internal_error', 'unregistered reason ' + _detail(code)
        super().__init__(code)
        self.code = code
        self.detail = None if detail is None else _detail(detail)
        self.native_kind = None if native_kind is None else _detail(native_kind)


def _fail(code, detail=None, native_kind=None):
    raise Unsupported(code, detail, native_kind)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _bounded(value, *, code=None):
    """The worker's check_tree/main bounds, at least as strict: nodes (keys counted too), depth, text, ints, bytes.

    With `code`, any violation is reported under that context code (e.g. an invalid worker reply)."""
    if code is not None:
        try:
            return _bounded(value)
        except Unsupported as exc:
            raise Unsupported(code, exc.code) from None
    count, size, active = 0, 0, set()

    def visit(item, depth):
        nonlocal count, size
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _fail('structure_budget')
        typ = type(item)
        if typ is str:
            if len(item) > MAX_BYTES:
                _fail('text_budget')
            size += len(item.encode('utf-8'))
            if size > MAX_BYTES:
                _fail('text_budget')
        elif typ is int:
            if item.bit_length() > MAX_BITS:
                _fail('number_budget')
        elif typ in (bool, type(None)):
            pass
        elif typ in (dict, list):
            if len(item) > MAX_NODES or id(item) in active:
                _fail('structure_budget')
            active.add(id(item))
            if typ is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        _fail('non_json_key')
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        else:
            _fail('non_json_value')
    try:
        visit(value, 0)
        raw = _raw(value)
    except UnicodeEncodeError:
        _fail('text_budget', 'text is not encodable as UTF-8')
    if len(raw) > MAX_BYTES:
        _fail('wire_budget')
    return raw


def _q(value):
    if type(value) not in (int, Fraction):
        _fail('requires_exact_number')
    result = Fraction(value)
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > MAX_BITS:
        _fail('number_budget')
    return result


def _rat(value):
    value = _q(value)
    return [str(value.numerator), str(value.denominator)]


def _unrat(value):
    """A solver reply's exact rational: canonical decimal strings, at most 256 bits each."""
    if type(value) is not list or len(value) != 2 or any(type(x) is not str or len(x) > 80 for x in value):
        _fail('invalid_rational_witness')
    for text in value:
        if not text or text in ('-', '+') or (text.startswith('-') and not text[1:].isdigit()) or (
                not text.startswith('-') and not text.isdigit()) or not text.isascii():
            _fail('invalid_rational_witness')
    numerator, denominator = int(value[0]), int(value[1])
    if denominator <= 0:
        _fail('invalid_rational_witness')
    if max(numerator.bit_length(), denominator.bit_length()) > MAX_BITS:
        _fail('witness_number_budget')
    q = Fraction(numerator, denominator)
    if [str(q.numerator), str(q.denominator)] != value:
        _fail('noncanonical_rational_witness')
    return q


@dataclass
class Affine:
    const: Fraction
    terms: dict

    def wire(self):
        return {'constant': _rat(self.const), 'terms': [[k, _rat(v)] for k, v in sorted(self.terms.items())]}


def _affine(const=0, terms=None):
    return Affine(_q(const), {k: _q(v) for k, v in (terms or {}).items() if v})


def _add(a, b, scale=1):
    terms = dict(a.terms)
    for key, value in b.terms.items():
        terms[key] = _q(terms.get(key, 0) + value * scale)
    return _affine(_q(a.const + b.const * scale), terms)


def _scale(a, factor):
    return _affine(_q(a.const * factor), {k: _q(v * factor) for k, v in a.terms.items()})


# ---------------------------------------------------------------------------------------------------------------
# Native field gate: every attribute of every accepted node is listed here; anything else refuses.
# ---------------------------------------------------------------------------------------------------------------

NODE_BASE = frozenset({'k', 'line', 'col'})
EXPRESSION_FIELDS = {'num': {'value'}, 'lit': {'value'}, 'name': {'name'}, 'attr': {'obj', 'name'},
                     'un': {'op', 'a'}, 'bin': {'op', 'a', 'b'}, 'cmp': {'ops', 'parts'}}
STATEMENT_FIELDS = {'given': {'name', 'type', 'default'},
                    'ask': {'name', 'type', 'parts', 'each', 'sources', 'options'},
                    'let': {'name', 'type', 'value', 'weight'},
                    'ensure': {'cond', 'on_fail', 'because'}}
TEXT_FIELDS = {'parts'}            # a string literal node (`because "..."`)
COMPARISONS = ('=', '!=', '<', '<=', '>', '>=')
CONNECTIVES = ('and', 'or', '->', '<->', 'xor')


def _fields(node, allowed):
    """The node has exactly the native fields this gate understands, and integer coordinates."""
    names = set(vars(node))
    if names != NODE_BASE | allowed or type(node.line) is not int or type(node.col) is not int:
        _fail('unsupported_node_field', f'{node.k}: ' + ', '.join(sorted(map(str, names ^ (NODE_BASE | allowed)))))


def _binding_name(name):
    """The native binding rule (S.check and Run._bind refuse builtin names) plus the parser's name shape."""
    if type(name) is not str or not 1 <= len(name) <= MAX_NAME:
        _fail('invalid_binding_name')
    if name in S.BUILTINS:
        _fail('native_binding_name', f'{name} is a builtin function name')
    try:
        tokens = S.tokenize(name, 1)
    except (S.SymblicError, RecursionError):
        _fail('invalid_binding_name')
    if (len(tokens) != 1 or tokens[0].kind != 'name' or tokens[0].value != name
            or (name.lower() in S.WORD_OPS and name.lower() != 'none')):
        _fail('invalid_binding_name')


def _text_parts(parts, constant_names, code):
    """Instruction/`because` text: literal pieces and bare names of given constants only."""
    if type(parts) is not list:
        _fail(code)
    for part in parts:
        if type(part) is str:
            continue
        if type(part) is not S.Node or part.k != 'name':
            _fail(code, getattr(part, 'k', type(part).__name__))
        _fields(part, EXPRESSION_FIELDS['name'])
        if type(part.name) is not str or part.name not in constant_names:
            _fail(code, f'{part.name} is not a given constant')


class Compiler:
    def __init__(self, constants):
        self.names, self.fields, self.variables = {}, {}, []
        self.nodes = 0
        if type(constants) is not dict or len(constants) > MAX_VARS:
            _fail('constant_budget')
        for name, value in constants.items():
            _binding_name(name)
            self.names[name] = ['literal', value] if type(value) is bool else _affine(_q(value))
        self.constant_names = frozenset(self.names)

    def variable(self, ty, path):
        if type(ty) is not dict or ty.get('k') not in ('bool', 'int', 'number'):
            _fail('unsupported_type')
        if set(ty) - {'k', 'lo', 'hi'} or (('lo' in ty) != ('hi' in ty)):
            _fail('unsupported_type_modifier')
        if ty['k'] == 'bool' and set(ty) != {'k'}:
            _fail('unsupported_type_modifier')
        ident = 'v' + str(len(self.variables))
        row = {'id': ident, 'sort': ty['k'], 'path': path}
        if 'lo' in ty:
            # Resolved type bounds are parser-authored exact integers or 'p/q' strings.
            bounds = []
            for key in ('lo', 'hi'):
                value = ty[key]
                if type(value) is str:
                    if len(value) > 80:
                        _fail('number_budget')
                    pieces = value.split('/')
                    if not 1 <= len(pieces) <= 2 or any(not p.removeprefix('-').isascii() or not p.removeprefix('-').isdigit() for p in pieces):
                        _fail('unsupported_type_bound')
                    value = Fraction(value)
                bounds.append(_q(value))
            row.update(lo=_rat(bounds[0]), hi=_rat(bounds[1]))
        self.variables.append(row)
        if len(self.variables) > MAX_VARS:
            _fail('variable_budget')
        return ['variable', ident] if ty['k'] == 'bool' else _affine(0, {ident: Fraction(1)})

    def answer(self, name, ty):
        _binding_name(name)
        if name in self.names:
            _fail('shadowed_answer')
        if ty.get('k') == 'record':
            if set(ty) != {'k', 'fields'} or type(ty['fields']) is not list or not ty['fields']:
                _fail('unsupported_record')
            if len(ty['fields']) > MAX_VARS:
                _fail('variable_budget')
            for item in ty['fields']:
                if type(item) is not list or len(item) != 2 or type(item[0]) is not str:
                    _fail('unsupported_record')
            # The native answer matcher (symblic.kernel.profiles, strict transformations) maps each answer key to the FIRST
            # declared field whose name equals key.strip().casefold() under casefold; any other match is an
            # undeclared transformation. A field that is not its own first match can never be answered as declared
            # (fields equal under casefold such as a/A or ss/ß, or names with surrounding spaces), so no native Run
            # could accept a witness for it.
            declared = [item[0] for item in ty['fields']]
            for field_name in declared:
                match = [other for other in declared if field_name.strip().casefold() == other.casefold()]
                if not match or match[0] != field_name:
                    _fail('native_record_field', repr(field_name)[:80])
            for item in ty['fields']:
                field_name, subty = item
                if type(field_name) is not str or len(field_name) > MAX_NAME or (name, field_name) in self.fields:
                    _fail('duplicate_or_invalid_field')
                self.fields[name, field_name] = self.variable(subty, [field_name])
        else:
            self.names[name] = self.variable(ty, [])

    def bind(self, name, value):
        _binding_name(name)
        if name in self.names or any(answer == name for answer, _ in self.fields):
            _fail('duplicate_binding')
        self.names[name] = value

    def expression(self, node, depth=0):
        self.nodes += 1
        if self.nodes > MAX_NODES or depth > MAX_DEPTH or type(node) is not S.Node:
            _fail('ast_budget')
        kind = node.k
        if type(kind) is not str or kind not in EXPRESSION_FIELDS:
            _fail('unsupported_ast_node', kind if type(kind) is str else type(kind).__name__)
        _fields(node, EXPRESSION_FIELDS[kind])

        def sub(n):
            return self.expression(n, depth + 1)
        if kind == 'num':
            return _affine(_q(node.value))
        if kind == 'lit':
            if type(node.value) is bool:
                return ['literal', node.value]
            _fail('unsupported_ast_node', 'lit')
        if kind == 'name':
            if type(node.name) is not str or node.name not in self.names:
                _fail('unbound_or_nonliteral_constant')
            return self.names[node.name]
        if kind == 'attr':
            self.nodes += 1
            if type(node.obj) is not S.Node or node.obj.k != 'name':
                _fail('unsupported_field')
            _fields(node.obj, EXPRESSION_FIELDS['name'])
            if type(node.name) is not str or (node.obj.name, node.name) not in self.fields:
                _fail('unsupported_field')
            return self.fields[node.obj.name, node.name]
        if kind == 'un':
            a = sub(node.a)
            if node.op == 'not' and type(a) is list:
                return ['not', a]
            if node.op in ('+', '-') and type(a) is Affine:
                return _scale(a, -1 if node.op == '-' else 1)
            _fail('operator_type')
        if kind == 'bin':
            a, b = sub(node.a), sub(node.b)
            if node.op in CONNECTIVES and type(a) is list and type(b) is list:
                return [node.op, a, b]
            if type(a) is not Affine or type(b) is not Affine:
                _fail('operator_type')
            if node.op == '+':
                return _add(a, b)
            if node.op == '-':
                return _add(a, b, -1)
            if node.op == '*':
                if a.terms and b.terms:
                    _fail('nonlinear_product')
                return _scale(a, b.const) if not b.terms else _scale(b, a.const)
            if node.op == '/':
                if b.terms or not b.const:
                    _fail('variable_or_zero_divisor')
                return _scale(a, 1 / b.const)
            _fail('unsupported_operator', node.op if type(node.op) is str else None)
        # kind == 'cmp'
        if type(node.ops) is not list or type(node.parts) is not list or not node.ops or \
                len(node.parts) != len(node.ops) + 1:
            _fail('comparison_type')
        if len(node.ops) > MAX_CHAIN:
            _fail('comparison_chain_budget', f'{len(node.ops)} comparisons; the worker accepts at most {MAX_CHAIN}')
        parts = [sub(n) for n in node.parts]
        rows = []
        for op, a, b in zip(node.ops, parts, parts[1:]):
            if type(a) is Affine and type(b) is Affine and op in COMPARISONS:
                rows.append(['compare', op, a.wire(), b.wire()])
            elif type(a) is list and type(b) is list and op in ('=', '!='):
                rows.append(['<->' if op == '=' else 'xor', a, b])
            else:
                _fail('comparison_type')
        return ['all', rows]

    def because(self, node):
        """`because`: absent, literal text (bare given-constant interpolation only) or the narrow fragment."""
        if node is None:
            return
        if type(node) is S.Node and node.k == 'str':
            try:
                _fields(node, TEXT_FIELDS)
                _text_parts(node.parts, self.constant_names, 'unsupported_because')
            except Unsupported as exc:
                raise Unsupported('unsupported_because', exc.detail or exc.code) from None
            return
        try:
            self.expression(node)
        except Unsupported as exc:
            raise Unsupported('unsupported_because', exc.detail or exc.code) from None


@dataclass
class Prepared:
    ask: object
    ty: dict
    steps: list
    constants: dict
    wire: dict
    contract_id: str
    plan: dict = field(default_factory=dict)       # the native anchored plan: {'between': [...], 'ensures': [...]}
    after: list = field(default_factory=list)      # source path only: statements after the last anchored check
    check_ids: frozenset = frozenset()
    givens: tuple = ()                             # source path only: (name, resolved type or None) per given


def _native_bound(value):
    count, text, active = 0, 0, set()

    def visit(item, depth):
        nonlocal count, text
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _fail('ast_budget')
        typ = type(item)
        if typ is str:
            if len(item) > MAX_BYTES:
                _fail('text_budget')
            try:
                text += len(item.encode())
            except UnicodeEncodeError:
                _fail('text_budget', 'text is not encodable as UTF-8')
            if text > MAX_BYTES:
                _fail('text_budget')
        elif typ in (int, Fraction):
            _q(item)
        elif typ in (bool, type(None)):
            return
        elif typ in (S.Node, dict, list, tuple):
            if id(item) in active:
                _fail('ast_cycle')
            active.add(id(item))
            obj = vars(item) if typ is S.Node else item
            if len(obj) > MAX_NODES:
                _fail('ast_budget')
            if type(obj) is dict:
                for key, child in obj.items():
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in obj:
                    visit(child, depth + 1)
            active.remove(id(item))
        else:
            _fail('unsupported_host_value')
    visit(value, 0)


def prepare_ask(ask, ty, plan, constants, *, after=None):
    """Trusted host bridge: exact native ask/resolved type/anchored plan + scalar constants.

    Called with Run._contract(ask), never model-authored attestation. Does not read
    Run stores or evaluate anything. Only the plan's anchored ensures (`ensures`,
    all `else retry`) become solver constraints; `between` may also hold lets and
    `else warn` ensures, which are gated and later evaluated per witness. `after`
    (source path only) holds statements after the last anchored check, gated alike.
    """
    _native_bound([ask, ty, plan, constants, after])
    if type(ty) is not dict:
        _fail('resolved_type_required')
    if type(ask) is not S.Node or ask.k != 'ask':
        _fail('single_anchored_ask_required')
    _fields(ask, STATEMENT_FIELDS['ask'])
    if ask.each is not None:
        _fail('single_anchored_ask_required')
    if type(ask.type) is not dict:
        _fail('unsupported_node_field', 'ask: type')
    try:
        # The native Run resolves ask.type itself; a host type that differs would validate other answers.
        # Named (`define`) types need the program's type table and are outside this fragment.
        resolved = S.resolve_type(ask.type, {}, ask.line)
    except S.SymblicError as exc:
        _fail('resolved_type_mismatch', exc.message, exc.kind)
    if resolved != ty:
        _fail('resolved_type_mismatch')
    if type(plan) is not dict or set(plan) != {'between', 'ensures'}:
        _fail('plan_shape')
    checks, between = plan['ensures'], plan['between']
    after = [] if after is None else after
    if type(checks) is not list or type(between) is not list or type(after) is not list:
        _fail('plan_shape')
    if not checks:
        _fail('no_anchored_check')
    if len(checks) > MAX_CHECKS:
        _fail('check_budget')
    if len(between) > MAX_CHECKS or len(after) > MAX_CHECKS:
        _fail('between_budget')
    compiler = Compiler(constants)
    compiler.answer(ask.name, ty)
    _text_parts(ask.parts, compiler.constant_names, 'unsupported_interpolation')
    if type(ask.sources) is not list:
        _fail('unsupported_node_field', 'ask: sources')
    if ask.sources:
        _fail('unsupported_ask_source', ', '.join(map(str, ask.sources)))
    if type(ask.options) is not dict:
        _fail('unsupported_node_field', 'ask: options')
    if ask.options:
        _fail('unsupported_ask_option', ', '.join(sorted(map(str, ask.options))))
    check_ids = frozenset(id(e) for e in checks)
    if len(check_ids) != len(checks):
        _fail('check_mapping')
    steps = list(between)
    steps.extend(e for e in checks if not any(e is row for row in steps))
    if len({id(row) for row in steps + after}) != len(steps) + len(after):
        _fail('check_mapping')
    constraints = []
    for rows, contract in ((steps, True), (after, False)):
        for row in rows:
            if type(row) is not S.Node or row.k not in ('let', 'ensure'):
                _fail('unsupported_between_statement', getattr(row, 'k', type(row).__name__))
            _fields(row, STATEMENT_FIELDS[row.k])
            if row.k == 'let':
                if row.type is not None or row.weight is not None:
                    _fail('typed_or_weighted_intermediate')
                compiler.bind(row.name, compiler.expression(row.value))
                continue
            cond = compiler.expression(row.cond)
            if type(cond) is not list:
                _fail('predicate_not_boolean')
            compiler.because(row.because)
            if contract and id(row) in check_ids:
                if row.on_fail != 'retry':
                    _fail('check_mapping')       # native anchoring only ever anchors `else retry`
                constraints.append(cond)
            elif row.on_fail != 'warn':
                # `else fail` and an unanchored `else retry` end a native Run when false; they are not the
                # ask's contract, and a witness cannot be validated against them without changing their meaning.
                _fail('unanchored_hard_check', f'line {row.line}: else {row.on_fail}')
    if len(constraints) != len(checks):
        _fail('check_mapping')
    wire = {'version': VERSION, 'variables': compiler.variables, 'constraints': constraints}
    raw = _bounded(wire)
    # Scope/hash also bind source AST and caller constants, not only the simplified IR.
    from symblic.kernel import evidence as E
    identity = {'wire': wire, 'ask': E.syntax(ask), 'type': E.syntax(ty),
                'steps': E.syntax(steps), 'constants': E.syntax(constants)}
    if after:
        identity['after'] = E.syntax(after)
    identity_raw = _bounded(identity)
    return Prepared(ask, ty, steps, dict(constants), json.loads(raw), _sha(identity_raw),
                    plan={'between': list(between), 'ensures': list(checks)}, after=list(after), check_ids=check_ids)


def _native_plan(rows, ask_index):
    """Mirror of symblic.kernel.run.Run._anchors and the plan assembly in Run.exec_block, for this fragment.

    Only `ensure ... else retry` anchors, to the nearest earlier ask it reads directly or through the
    bindings between them. The fragment has no facts or rules, so knowledge-base reads add nothing.
    Returns (plan, statements after the last anchored ensure).
    """
    anchors = {}
    for i, s in enumerate(rows):
        if s.k != 'ensure' or s.on_fail != 'retry':
            continue
        need = set(S.free_names(s.cond))
        for j in range(i - 1, -1, -1):
            t = rows[j]
            binds = {t.name} if t.k in ('let', 'given', 'ask') else set()
            if binds & need:
                if t.k == 'ask':
                    anchors[i] = j
                    break
                need |= set(S.free_names(S._reads_of(t)))
    plan, last = {'between': [], 'ensures': []}, None
    for ei, ai in anchors.items():
        plan['between'] = rows[ai + 1:ei]
        plan['ensures'].append(rows[ei])
        last = ei
    return plan, rows[(ask_index if last is None else last) + 1:]


def prepare_source(source, inputs=None):
    """Small source-only convenience: given*; one ask; untyped let/ensure*.

    Names/types use the native parser and the native static checker (profile
    `verified`). No program execution, effects or imports. Host inputs are exact
    bool/int/Fraction values bound as given; JSON floats are refused. `assess`
    additionally requires the native Run to bind the same given values.
    """
    if type(source) is not str or len(source) > MAX_BYTES:
        _fail('source_budget')
    try:
        size = len(source.encode())
    except UnicodeEncodeError:
        _fail('source_encoding')
    if size > MAX_BYTES:
        _fail('source_budget')
    if inputs is None:
        inputs = {}
    if type(inputs) is not dict or len(inputs) > MAX_VARS:
        _fail('input_budget')
    rows = S.parse(source, execution_profile=PROFILE)['statements']
    constants, givens, ask_index = {}, [], None
    for index, row in enumerate(rows):
        if row.k == 'given' and ask_index is None:
            _fields(row, STATEMENT_FIELDS['given'])
            _binding_name(row.name)
            if row.name in constants:
                _fail('duplicate_binding')
            if row.default is not None:
                _fail('given_default')
            if row.name not in inputs:
                _fail('literal_host_inputs_required')
            value = inputs[row.name]
            if type(value) is not bool:
                _q(value)
            rty = None
            if row.type is not None:
                rty = S.resolve_type(row.type, {}, row.line)
                # No rounded/complex declarations even when an input happens to fit.
                Compiler({}).variable(rty, [])
                value = S.check_value(value, rty)
            constants[row.name] = value
            givens.append((row.name, rty))
        elif row.k == 'ask' and ask_index is None:
            ask_index = index
        elif ask_index is not None and row.k in ('let', 'ensure'):
            continue
        else:
            _fail('source_outside_single_ask_fragment', row.k)
    if ask_index is None or set(inputs) != set(constants):
        _fail('input_or_ask_mapping')
    ask = rows[ask_index]
    plan, after = _native_plan(rows, ask_index)
    prepared = prepare_ask(ask, S.resolve_type(ask.type, {}, ask.line), plan, constants, after=after)
    check = S.check(source, execution_profile=PROFILE)
    if check['errors']:
        first = check['errors'][0]
        _fail('native_check_error', first.get('message'), first.get('kind'))
    prepared.givens = tuple(givens)
    return prepared


def _native_json(value):
    """The JSON input a native Run needs for an exact host value: bool, int, or exact 'p/q' text."""
    if type(value) in (bool, int):
        return value
    return value.numerator if value.denominator == 1 else f'{value.numerator}/{value.denominator}'


def _same_scalar(native, value):
    if (type(native) is bool) != (type(value) is bool):
        return False
    if type(native) is bool:
        return native is value
    return type(native) in (int, Fraction) and type(value) in (int, Fraction) and native == value


def _native_inputs(prepared, inputs):
    """Refuse a given whose native binding (Run._given: S.coerce or S.from_json of the input) differs."""
    for name, rty in prepared.givens:
        raw = _native_json(inputs[name])
        try:
            native = S.coerce(raw, rty, name) if rty is not None else S.from_json(raw)
        except S.SymblicError as exc:
            _fail('native_input_binding', exc.message, exc.kind)
        if not _same_scalar(native, prepared.constants[name]):
            _fail('native_input_binding', f'{name}: the native Run binds {type(native).__name__} {S.show(native, 60)}')


_EXACT_NUMBER = re.compile(r'-?[0-9]+(?:\.[0-9]+|/[0-9]+)?\Z')


def _exact_scalar_text(value):
    if type(value) is bool:
        return 'true' if value else 'false'
    value = S.norm_num(value)
    shown = S.show(value)
    if _EXACT_NUMBER.match(shown) and Fraction(shown) == value:
        return shown                                 # the native display is already exact
    return f'{value.numerator}/{value.denominator}'  # e.g. native '1/3 (≈0.333333333333)' or '≈0.124999998861'


def exact_text(value, ty):
    """Exact witness text: the native display where it is exact, otherwise exact p/q (see README)."""
    if ty['k'] != 'record':
        return _exact_scalar_text(value)

    def label(name):
        return name if name.isidentifier() else json.dumps(name, ensure_ascii=False)
    return '{' + ', '.join(f'{label(name)}: {_exact_scalar_text(value[name])}' for name in sorted(value)) + '}'


def validate_witness(prepared, assignment, *, deadline=None, check_stop=None):
    """Decode exact values, then use native type and original predicate evaluation."""
    # Recheck the narrow AST gate before using the native evaluator, including
    # host mutation between preparation and validation. No candidate gets to
    # introduce a call or change its authoritative predicates.
    _stop(check_stop)
    current = prepare_ask(prepared.ask, prepared.ty, prepared.plan, prepared.constants, after=prepared.after)
    if current.contract_id != prepared.contract_id or current.wire != prepared.wire:
        _fail('prepared_contract_drift')
    if type(assignment) is not dict or set(assignment) != {v['id'] for v in current.wire['variables']}:
        _fail('witness_variables')
    value = {} if current.ty['k'] == 'record' else None
    for row in current.wire['variables']:
        _stop(check_stop)
        item = assignment[row['id']]
        if row['sort'] == 'bool':
            if type(item) is not bool:
                _fail('boolean_witness_type')
        else:
            item = _unrat(item)
            if row['sort'] == 'int' and item.denominator != 1:
                _fail('integer_witness_type')
        if row['path']:
            value[row['path'][0]] = item
        else:
            value = item
    try:
        value = S.check_value(value, current.ty)
    except S.SymblicError as exc:
        _fail('witness_failed_native_type', exc.message, exc.kind)
    env = S.Env()
    for name, item in {**current.constants, current.ask.name: value}.items():
        env.vars[name] = S.Binding(name, item)
    kernel = S.Kernel(env, budget=S.Budget(20000))
    checked, unanchored = [], []
    try:
        for rows, position in ((current.steps, 'between'), (current.after, 'after_contract')):
            for row in rows:
                _stop(check_stop)
                if deadline is not None and time.monotonic() >= deadline:
                    _fail('validation_timeout')
                if row.k == 'let':
                    env.vars[row.name] = S.Binding(row.name, kernel.eval(row.value))
                elif id(row) in current.check_ids:
                    if kernel.eval(row.cond) is not True:
                        _fail('witness_failed_native_predicate')
                    checked.append(row.line)
                else:
                    # An `else warn` ensure (the gate refused every other unanchored kind): never a solver
                    # constraint; natively a failing warn only adds a warning, so it is reported per witness.
                    unanchored.append({'line': row.line, 'on_fail': row.on_fail,
                                       'holds': kernel.eval(row.cond) is True, 'position': position})
    except S.SymblicError as exc:
        _fail('witness_native_error', exc.message, exc.kind)
    _stop(check_stop)
    return {'canonical': S.canon(value), 'text': exact_text(value, current.ty), 'fingerprint': S.fingerprint(value),
            'checks': checked, 'unanchored_checks': unanchored, 'validation': 'native_type_and_original_predicates'}


def _capture(command, raw, deadline, *, output_cap=MAX_OUTPUT, check_stop=None, lifecycle=None):
    """Fixed single worker; 50ms cooperative stop polling and bounded owned kill/reap.

    The fixed worker does not create descendants. This is a direct-child boundary,
    not a generic subprocess-tree supervisor. Cleanup has a separate 2s ceiling.
    An unreaped worker raises WorkerCleanupError outside typed fallback handling.
    """
    _stop(check_stop)
    launch_exception = None
    try:
        with tempfile.TemporaryFile() as request:
            request.write(raw)
            request.seek(0)
            _stop(check_stop)
            if time.monotonic() >= deadline:
                _fail('worker_timeout')
            if lifecycle is not None:
                # Popen may fail after beginning launch without returning the owned handle. Unknown is not proof
                # of no dispatch and cannot authorize a reservation refund or a second worker.
                lifecycle['dispatched'] = None
            try:
                proc = subprocess.Popen(command, stdin=request, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'OMP_NUM_THREADS': '1'})
            except BaseException as exc:
                if lifecycle is not None:
                    launch_exception = exc
                    raise
                if isinstance(exc, OSError):
                    _fail('worker_launch_failed', type(exc).__name__)
                raise
            if lifecycle is not None:
                lifecycle.update(dispatched=True, reaped=False)
            chunks = {'out': bytearray(), 'err': bytearray()}
            pending = None
            try:
                with selectors.DefaultSelector() as selector:
                    for stream, label in ((proc.stdout, 'out'), (proc.stderr, 'err')):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, label)
                    while selector.get_map() or proc.poll() is None:
                        _stop(check_stop)
                        left = deadline - time.monotonic()
                        if left <= 0:
                            _fail('worker_timeout')
                        for key, _ in selector.select(min(left, .05)):
                            piece = os.read(key.fd, 4096)
                            if not piece:
                                selector.unregister(key.fileobj)
                            else:
                                chunks[key.data].extend(piece)
                                if lifecycle is not None:
                                    lifecycle['stdout_observed_bytes' if key.data == 'out' else
                                              'stderr_observed_bytes'] += len(piece)
                                if sum(map(len, chunks.values())) > output_cap:
                                    _fail('worker_output_budget')
                response = None
                if lifecycle is not None:
                    # Complete bounded capture is independent of exit status, later stop and JSON/native validity.
                    response = bytes(chunks['out'])
                    lifecycle.update(raw_sha256=_sha(response), raw_bytes=len(response), capture_complete=True)
                _stop(check_stop)
                if time.monotonic() >= deadline:
                    _fail('worker_timeout')
                if proc.returncode:
                    _fail('worker_refused_or_failed')
                return bytes(chunks['out']) if response is None else response
            except BaseException as exc:
                pending = exc
                raise
            finally:
                reaped = False
                cleanup_error = None
                try:
                    if proc.poll() is None:
                        proc.kill()
                    returncode = proc.wait(timeout=REAP_SECONDS)
                    reaped = True
                    if lifecycle is not None:
                        lifecycle.update(reaped=True, returncode=returncode if type(returncode) is int else None)
                except BaseException as exc:
                    # An interrupt is not evidence that the owned child was reaped.
                    # Keep that failure fatal even if closing either pipe also fails.
                    cleanup_error = exc
                for stream in (proc.stdout, proc.stderr):
                    try:
                        stream.close()
                    except BaseException as exc:
                        if cleanup_error is None or (reaped and
                                isinstance(cleanup_error, Exception) and not isinstance(exc, Exception)):
                            cleanup_error = exc
                if not reaped:
                    message = ('owned worker not reaped within cleanup ceiling'
                               if isinstance(cleanup_error, subprocess.TimeoutExpired)
                               else 'owned worker cleanup failed: ' + type(cleanup_error).__name__)
                    raise WorkerCleanupError(message) from cleanup_error
                # Preserve the original guarded stop/control-flow exception after
                # confirmed reap. A new interrupt must still outrank an ordinary
                # solver refusal rather than becoming a typed fallback.
                if cleanup_error is not None and (pending is None or
                        (isinstance(pending, Exception) and not isinstance(cleanup_error, Exception))):
                    raise cleanup_error

    except BaseException:
        # Closing the request file cannot replace an unknown-launch cause or prove no worker exists.
        if launch_exception is not None:
            raise launch_exception
        raise


RUNTIME_KEYS = frozenset({'python', 'python_sha256', 'worker_sha256', 'z3_version', 'package', 'purelib'})


def _hex64(value):
    return type(value) is str and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def _check_runtime(runtime, *, check_stop=None):
    """The worker's runtime/package limits that need no hashing, checked before dispatch.

    Hashes, the package inventory and the loaded library identity remain worker checks: a failure
    there is a worker refusal (status unknown), which the host cannot predict without re-reading the
    46 MB payload."""
    if type(runtime) is not dict or set(runtime) != RUNTIME_KEYS:
        _fail('runtime_configuration', 'runtime keys')
    if type(runtime['python']) is not str or not 1 <= len(runtime['python']) <= MAX_PATH_TEXT:
        _fail('runtime_configuration', 'python')
    if not _hex64(runtime['python_sha256']) or not _hex64(runtime['worker_sha256']):
        _fail('runtime_configuration', 'sha256 pins')
    purelib, package = runtime['purelib'], runtime['package']
    if type(purelib) is not str or not 1 <= len(purelib) <= MAX_PATH_TEXT or '\x00' in purelib or \
            not Path(purelib).is_absolute():
        _fail('runtime_configuration', 'purelib')
    if type(package) is not dict or not 1 <= len(package) <= MAX_PACKAGE_FILES:
        _fail('runtime_configuration', 'package pins')
    for name, expected in package.items():
        _stop(check_stop)
        if type(name) is not str or len(name) > MAX_PATH_TEXT or '\x00' in name:
            _fail('runtime_configuration', 'package path')
        parts = Path(name).parts
        if not parts or Path(name).is_absolute() or '..' in parts or parts[0] not in PACKAGE_DIRS:
            _fail('runtime_configuration', 'package path')
        if not _hex64(expected):
            _fail('runtime_configuration', 'package sha256')
    try:
        base = Path(purelib).resolve()
        if not base.is_dir() or str(base) != purelib:
            _fail('runtime_configuration', 'purelib must be an existing resolved directory')
        total = 0
        for name in package:
            _stop(check_stop)
            try:
                info = (base / name).lstat()
            except FileNotFoundError:
                continue                    # the worker refuses a missing pinned file (package_pin)
            if not stat.S_ISREG(info.st_mode):
                _fail('runtime_configuration', 'package file is not a regular file')
            total += info.st_size
            if info.st_size > MAX_PACKAGE_FILE_BYTES or total > MAX_PACKAGE_BYTES:
                _fail('runtime_package_budget')
    except OSError as exc:
        _fail('runtime_unreadable', type(exc).__name__)


def _invoke(prepared, runtime, deadline, resource_limit, *, address_space_bytes=DEFAULT_ADDRESS_SPACE_BYTES, check_stop=None, before_spawn=None, lifecycle=None):
    if runtime is None:
        _fail('solver_unavailable')
    _stop(check_stop)
    _check_runtime(runtime, check_stop=check_stop)
    python = Path(runtime['python'])
    worker = BASE / 'worker.py'
    if not python.is_file() or runtime['z3_version'] != Z3_VERSION:
        _fail('solver_unavailable_or_version')

    def file_hash(path):
        _stop(check_stop)
        if path.stat().st_size > 64_000_000:
            _fail('runtime_source_budget')
        with path.open('rb') as stream:
            data = stream.read(64_000_001)
        if len(data) > 64_000_000:
            _fail('runtime_source_budget')
        _stop(check_stop)
        return _sha(data)
    try:
        hashes = file_hash(python), file_hash(worker)
    except OSError as exc:
        _fail('runtime_unreadable', type(exc).__name__)
    if hashes != (runtime['python_sha256'], runtime['worker_sha256']):
        _fail('solver_source_drift')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _fail('preflight_timeout')
    milliseconds = max(1, int(remaining * 1000))
    if milliseconds > MAX_MILLISECONDS:
        _fail('invalid_resource_limits')
    if not _address_space_ok(address_space_bytes):
        _fail('invalid_resource_limits')
    request = {'protocol': WORKER_PROTOCOL, 'address_space_bytes': address_space_bytes, 'contract': prepared.wire, 'package': runtime['package'], 'purelib': runtime['purelib'],
               'z3_version': Z3_VERSION, 'milliseconds': milliseconds, 'resource_limit': resource_limit}
    raw = _bounded(request)
    if lifecycle is not None:
        lifecycle.update(request_sha256=_sha(raw), request_bytes=len(raw), requested_milliseconds=milliseconds,
                         requested_resource_limit=resource_limit, requested_address_space_bytes=address_space_bytes)
    # A fresh cache prefix plus -B prevents accepted stale .pyc files in the
    # optional package from substituting code for its freshly checked source.
    if not _WORKER_LOCK.acquire(blocking=False):
        _fail('worker_busy')
    reaped = True
    launch_exception = None
    try:
        with tempfile.TemporaryDirectory(prefix='symblic-z3-cache-') as cache:
            if before_spawn is not None:
                before_spawn()
            _stop(check_stop)
            try:
                response = _capture([str(python), '-I', '-S', '-B', '-X', 'pycache_prefix=' + cache, str(worker)],
                                    raw, deadline, check_stop=check_stop,
                                    **({'lifecycle': lifecycle} if lifecycle is not None else {}))
            except BaseException as exc:
                if _launch_unknown(lifecycle):
                    launch_exception = exc
                raise
    except WorkerCleanupError:
        reaped = False
        if launch_exception is not None:
            raise launch_exception
        raise
    except BaseException:
        # A cache-directory cleanup failure must not replace the cause of an unconfirmed Popen launch.
        if launch_exception is not None:
            raise launch_exception
        raise
    finally:
        if reaped and not _launch_unknown(lifecycle):
            _WORKER_LOCK.release()
    _stop(check_stop)
    if len(response) > MAX_OUTPUT:
        _fail('worker_output_budget')
    try:
        result = _strict_json(response)
    except (ValueError, RecursionError):
        _fail('invalid_solver_response', 'reply is not bounded JSON')
    _bounded(result, code='invalid_solver_response')
    _check_reply(result, runtime, resource_limit, address_space_bytes=address_space_bytes)
    if result['limits']['requested']['milliseconds'] != milliseconds:
        _fail('invalid_solver_limits', 'milliseconds differs from dispatched request')
    _stop(check_stop)
    return result


def _same_typed_record(actual, expected):
    """Compare a fixed protocol record without Bool/int aliases or caller formatting.

    The trusted expected shape bounds traversal: lengths and exact builtin types
    must match before visiting children. This is not an arbitrary tree walker.
    """
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return (len(actual) == len(expected) and all(type(key) is str for key in actual)
                and actual.keys() == expected.keys()
                and all(_same_typed_record(actual[key], value) for key, value in expected.items()))
    if type(expected) is list:
        return (len(actual) == len(expected)
                and all(_same_typed_record(item, value) for item, value in zip(actual, expected)))
    return actual == expected


def _check_reply(result, runtime, resource_limit, *, address_space_bytes=DEFAULT_ADDRESS_SPACE_BYTES):
    if type(result) is not dict or set(result) != {'protocol', 'version', 'z3_version', 'checks', 'assignments', 'resource_used', 'limits'} or type(result['protocol']) is not int or result['protocol'] != WORKER_PROTOCOL or type(result['version']) is not int or result['version'] != VERSION or result['z3_version'] != Z3_VERSION:
        _fail('invalid_solver_response')
    assignments, checks = result['assignments'], result['checks']
    if type(assignments) is not list or len(assignments) > 2 or type(checks) is not list or not 1 <= len(checks) <= 2:
        _fail('invalid_solver_response')
    for row in checks:
        if type(row) is not dict or set(row) != {'status', 'reason'} or row['status'] not in ('sat', 'unsat', 'unknown', 'timeout') or type(row['reason']) is not str or len(row['reason']) > 256:
            _fail('invalid_solver_response')
    if sum(row['status'] == 'sat' for row in checks) != len(assignments) or (len(checks) == 2 and checks[0]['status'] != 'sat'):
        _fail('invalid_solver_response')
    limits = result['limits']
    if type(limits) is not dict or set(limits) != {'requested', 'effective_os', 'z3_applied', 'private_import_root', 'loaded_library'}:
        _fail('invalid_solver_limits')
    requested = limits['requested']
    if type(requested) is not dict or set(requested) != {'milliseconds', 'rlimit_total', 'address_space_bytes'} or type(requested['address_space_bytes']) is not int or requested['address_space_bytes'] != address_space_bytes or type(requested['milliseconds']) is not int or not 1 <= requested['milliseconds'] <= MAX_MILLISECONDS or type(requested['rlimit_total']) is not int or requested['rlimit_total'] != resource_limit:
        _fail('invalid_solver_limits')
    first_work = resource_limit // 2 or 1
    if not _same_typed_record(limits['z3_applied'], {'threads': 1, 'random_seed': 0, 'allocated_check_rlimits': [first_work, resource_limit-first_work]}):
        _fail('invalid_solver_limits')
    expected_os = {'address_space_bytes': [address_space_bytes]*2, 'cpu_seconds': [math.ceil(requested['milliseconds']/1000)+1]*2,
                   'file_bytes': [0, 0], 'core_bytes': [0, 0], 'open_files': [64, 64]}
    if not _same_typed_record(limits['effective_os'], expected_os) or limits['private_import_root'] != runtime['purelib'] or limits['loaded_library'] != str(Path(runtime['purelib']) / 'z3/lib/libz3.so'):
        _fail('invalid_solver_limits')
    if type(result['resource_used']) is not int or result['resource_used'] < 0:
        _fail('invalid_solver_response')
    return assignments, checks, limits


_MISSING = object()
MAX_BOUND = 4096


def assess_ask(ask, ty, plan, constants, *, bound=_MISSING, defaults=_MISSING, **options):
    """The host seam. Besides Run._contract(ask), the host passes what the native Run applies at this ask and
    the prototype cannot see: `bound`, every name bound before the ask (givens, lets, asks, functions, routines,
    imports), and `defaults`, the ask-option defaults the program's `use` statements set. Without them the seam
    refuses (seam_context_required): binding legality and program defaults are native semantics too."""
    return _assess(lambda: _prepare_seam(ask, ty, plan, constants, bound, defaults), **options)


def _prepare_seam(ask, ty, plan, constants, bound, defaults):
    if bound is _MISSING or defaults is _MISSING:
        _fail('seam_context_required')
    if type(bound) not in (set, frozenset, list, tuple) or len(bound) > MAX_BOUND \
            or any(type(name) is not str or not 1 <= len(name) <= MAX_NAME for name in bound):
        _fail('seam_context', 'bound must be a collection of names')
    if type(defaults) is not dict:
        _fail('seam_context', 'defaults must be a dict')
    if defaults:
        # every ask option is refused (over-refusal), so are the program defaults the native Run would apply
        # Refuse in constant work: keys/values need no traversal or caller-controlled formatting.
        _fail('program_ask_defaults', 'Nonempty program ask defaults are outside this fragment.')
    names = set(bound)
    # A valid subset cannot have more keys than the bounded name set. Refuse
    # cardinality first, then inspect at most MAX_BOUND exact builtin keys.
    if type(constants) is not dict or len(constants) > len(names) \
            or any(type(name) is not str or name not in names for name in constants):
        _fail('seam_context', 'every host constant must be a bound name')
    prepared = prepare_ask(ask, ty, plan, constants)
    rebound = sorted(({ask.name} | {row.name for row in plan['between'] if row.k == 'let'}) & names)
    if rebound:
        # the native S.check / Run refuse a second binding: "<name> is bound twice (Symblic names are immutable)"
        _fail('native_rebinding', ', '.join(rebound)[:200])
    return prepared


def assess(source, inputs=None, **options):
    return _assess(lambda: _prepare_source_native(source, inputs), **options)


def _prepare_source_native(source, inputs):
    prepared = prepare_source(source, inputs)
    _native_inputs(prepared, inputs or {})
    return prepared


def _valid_limits(deadline_seconds, resource_limit):
    """Exact comparisons only: an int beyond float range is refused, never converted (a review finding)."""
    if type(deadline_seconds) is int:
        deadline_ok = 0 < deadline_seconds <= MAX_SECONDS
    elif type(deadline_seconds) is float:
        deadline_ok = math.isfinite(deadline_seconds) and 0 < deadline_seconds <= MAX_SECONDS
    else:
        deadline_ok = False
    return deadline_ok and type(resource_limit) is int and 1 <= resource_limit <= MAX_WORK


def _refuse(report, code, detail=None, native_kind=None):
    report.update(status=REASONS[code], reason=code)
    if detail is not None:
        report['detail'] = _detail(detail)
    if native_kind is not None:
        report['native_kind'] = _detail(native_kind)


def _assess(prepare, *, enabled=False, runtime=None, deadline_seconds=2, resource_limit=100000,
            address_space_bytes=DEFAULT_ADDRESS_SPACE_BYTES, check_stop=None, combined_memory=False, lifecycle=None):
    lifecycle = _lifecycle_begin(lifecycle)
    report = {'version': VERSION, 'method': 'smt', 'status': 'not_attempted', 'disposition': 'fallback',
              'determination': 'unassessed', 'exhaustive': False, 'passing_count': None,
              'witnesses': [], 'witnesses_truncated': False, 'witnesses_scope': 'at_most_two_constructed_assignments',
              'solver_claims': {},
              'provider_calls': 0, 'scope': 'declared_type_and_encoded_predicates',
              'automatic_answer': False}
    started = time.monotonic()
    phase = 'preflight'
    def memory_guard():
        guarded_stop()
        from symblic.linear.resources import MemoryAdmissionRefused, admit
        try:
            report['combined_memory'] = admit()
        except MemoryAdmissionRefused as exc:
            _fail('combined_memory_refused', str(exc))
        guarded_stop()

    def guarded_stop():
        try:
            _stop(check_stop)
        except BaseException as exc:
            raise _CallbackRaised(exc) from exc
    try:
        if type(enabled) is not bool:
            _refuse(report, 'enabled_requires_bool')
            return report
        if not enabled:
            return report
        if check_stop is not None and not callable(check_stop):
            _refuse(report, 'invalid_stop_callback')
            return report
        guarded_stop()
        if not _valid_limits(deadline_seconds, resource_limit) or not _address_space_ok(address_space_bytes) or \
                type(combined_memory) is not bool or (combined_memory and address_space_bytes != DEFAULT_ADDRESS_SPACE_BYTES):
            _refuse(report, 'invalid_resource_limits')
            return report
        report['host_limits'] = {'deadline_seconds': deadline_seconds,
                                 'aggregate_output_bytes': MAX_OUTPUT,
                                 'output_scope': 'worker_stdout_plus_stderr',
                                 'configured_resource_limit': resource_limit,
                                 'worker_protocol': WORKER_PROTOCOL,
                                 'address_space_bytes': address_space_bytes,
                                 'owned_reap_seconds': REAP_SECONDS}
        deadline = started + deadline_seconds
        prepared = prepare()
        guarded_stop()
        if time.monotonic() >= deadline:
            _fail('preflight_timeout')
        report['contract_id'] = prepared.contract_id
        report['native_versions'] = {'language': S.VERSION, 'canonical': S.CANON_VERSION}
        if runtime is not None:
            report['runtime_sha256'] = _sha(_bounded(runtime, code='runtime_configuration'))
        phase = 'solver'
        result = _invoke(prepared, runtime, deadline, resource_limit,
                         address_space_bytes=address_space_bytes, check_stop=guarded_stop,
                         before_spawn=memory_guard if combined_memory else None,
                         **({'lifecycle': lifecycle} if lifecycle is not None else {}))
        guarded_stop()
        assignments, checks, limits = _check_reply(result, runtime, resource_limit, address_space_bytes=address_space_bytes)
        phase = 'validation'
        witnesses = [validate_witness(prepared, value, deadline=deadline, check_stop=guarded_stop) for value in assignments]
        if time.monotonic() >= deadline:
            _fail('validation_timeout')
        if len(witnesses) == 2 and _raw(witnesses[0]['canonical']) == _raw(witnesses[1]['canonical']):
            _fail('duplicate_solver_witness')
        report.update(witnesses=witnesses, solver_claims={'checks': checks, 'independently_proved': False},
                      solver={'version': Z3_VERSION, 'resource_used': result['resource_used'],
                              'resource_limit': resource_limit,
                              'resource_used_scope': 'cumulative_z3_rlimit_count_not_a_hard_cap',
                              'limits': limits},
                      status='sat' if witnesses else checks[0]['status'])
        if witnesses:
            report['disposition'] = 'validated_candidate'
        if len(witnesses) == 2:
            report['witnesses_truncated'] = True  # Collection stopped at its cap, not a complete domain.
            report['determination'] = 'underdetermined'
            report['determination_basis'] = 'two_distinct_native_validated_witnesses'
        if len(checks) == 2 and checks[1]['status'] == 'unsat':
            report['solver_claims']['uniqueness'] = 'solver_reported_only'
    except _CallbackRaised as exc:
        if _launch_unknown(lifecycle):
            raise
        raise exc.cause
    except Unsupported as exc:
        if _launch_unknown(lifecycle):
            raise
        _refuse(report, exc.code, exc.detail, exc.native_kind)
    except S.SymblicError as exc:
        if _launch_unknown(lifecycle):
            raise
        _refuse(report, 'native_error' if phase == 'preflight' else 'witness_native_error',
                getattr(exc, 'message', exc), getattr(exc, 'kind', None))
    except RecursionError:
        if _launch_unknown(lifecycle):
            raise
        _refuse(report, 'native_recursion', 'maximum recursion depth exceeded')
    except subprocess.TimeoutExpired:
        if _launch_unknown(lifecycle):
            raise
        _refuse(report, 'worker_timeout')
    except Exception as exc:  # noqa: BLE001 - documented typed fallback; BaseException still propagates
        if _launch_unknown(lifecycle):
            raise
        _refuse(report, 'internal_error', f'{type(exc).__name__}: {_detail(exc)}')
    _stop(check_stop)
    if report['status'] != 'not_attempted':
        report['host_elapsed_seconds'] = time.monotonic() - started
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python3 -m symblic.linear.constructor',
                                     description='Let the optional Z3 worker propose an answer for one linear ask.')
    parser.add_argument('source', type=Path, help='a program: givens, one ask, then untyped let/ensure lines')
    parser.add_argument('--enable', action='store_true', help='actually run the solver (default: report only)')
    parser.add_argument('--runtime', type=Path, help='runtime.json written by tools/scripts/symblic_linear_provision.py')
    args = parser.parse_args(argv)
    def read(path):
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise SystemExit('input file budget')
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise SystemExit('input file budget')
        return raw
    source = read(args.source)
    runtime = json.loads(read(args.runtime)) if args.runtime else None
    result = assess(source.decode(), enabled=args.enable, runtime=runtime)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['disposition'] == 'validated_candidate' else 1


if __name__ == '__main__':
    raise SystemExit(main())

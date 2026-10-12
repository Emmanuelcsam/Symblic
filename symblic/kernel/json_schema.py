"""JSON shape checks for a `Code json` answer: a closed, bounded subset of JSON Schema.

A program can ask a model for a JSON document of a declared shape (`ask config: Code json {...}`). This module
parses that declared schema (parse_schema), decides whether a type may use it (admit), validates a document
against it without losing information (validate: the original number text is kept, decoded numbers never
replace it), and describes the shape in words for the model's prompt (describe). It refuses inputs outside
its finite limits instead of guessing.

This is a closed schema subset, not a general JSON Schema implementation. No execution or provider access.

Depends on: the standard library only. Used by: symblic.kernel.language (types and capsules) and the mica
package.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from decimal import Decimal, InvalidOperation
import json

VERSION = 1
MAX_SCHEMA_BYTES = 32768
MAX_SCHEMA_DEPTH = 16
MAX_SCHEMA_NODES = 4096
MAX_TEXT_CHARS = 400000
MAX_TEXT_BYTES = 1600000
MAX_DATA_DEPTH = 32
MAX_DATA_NODES = 50000
MAX_STEPS = 250000
MAX_NUMBER_CHARS = 1236
_TYPES = {'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'}
_ANNOTATIONS = {'title', 'description'}


class SchemaError(ValueError):
    pass


class ValidationError(ValueError):
    pass


class ResourceError(RuntimeError):
    pass


def _utf8(text):
    try:
        return text.encode('utf-8')
    except UnicodeError:
        raise ValidationError('JSON text contains an invalid Unicode scalar.') from None


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValidationError('Duplicate JSON object key.')
        out[key] = value
    return out


def _number(token):
    if len(token) > MAX_NUMBER_CHARS:
        raise ResourceError('JSON numeric token exceeds the declared resource bound.')
    exponent = token.lower().partition('e')[2]
    if exponent and (len(exponent.lstrip('+-').lstrip('0')) > 4 or abs(int(exponent)) > 4096):
        raise ResourceError('JSON numeric exponent exceeds the declared resource bound.')
    try:
        value = Decimal(token)
    except InvalidOperation:
        raise ValidationError('Invalid JSON number.') from None
    if not value.is_finite():
        raise ValidationError('Nonfinite JSON numbers are not allowed.')
    if abs(value.as_tuple().exponent) > 4096:
        raise ResourceError('JSON numeric exponent exceeds the declared resource bound.')
    return value


def _constant(_token):
    raise ValidationError('Nonfinite JSON constants are not allowed.')


def _load(text, *, schema=False):
    if type(text) is not str:
        raise ValidationError('An original JSON text reply is required.')
    cap = MAX_SCHEMA_BYTES if schema else MAX_TEXT_BYTES
    if len(text) > (MAX_SCHEMA_BYTES if schema else MAX_TEXT_CHARS) or len(_utf8(text)) > cap:
        raise ResourceError('JSON text exceeds the declared size budget.')
    depth_limit = MAX_SCHEMA_DEPTH * 4 if schema else MAX_DATA_DEPTH
    # Refuse depth before the recursive decoder allocates deeply nested objects.
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > depth_limit:
                raise ResourceError('JSON nesting exceeds the declared depth budget.')
        elif char in ']}':
            depth -= 1
    try:
        value = json.loads(text, parse_int=_number, parse_float=_number,
                           parse_constant=_constant, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, RecursionError):
        raise ValidationError('Malformed JSON document.') from None
    remaining = MAX_SCHEMA_NODES * 8 if schema else MAX_DATA_NODES
    pending = [value]
    while pending:
        item = pending.pop()
        remaining -= 1
        if remaining < 0:
            raise ResourceError('JSON tree exceeds the declared item budget.')
        if type(item) is str:
            _utf8(item)
        elif type(item) is list:
            pending.extend(item)
        elif type(item) is dict:
            for key in item:
                _utf8(key)
            pending.extend(item.values())
    return value


def parse_schema(text):
    """Admit a schema literal and return a detached, JSON-serializable schema."""
    try:
        raw = _load(text, schema=True)
    except ValidationError as exc:
        raise SchemaError(str(exc)) from None
    steps = [MAX_SCHEMA_NODES]

    def integer(value, label, *, nonnegative=False):
        if type(value) is not Decimal or value != value.to_integral_value():
            raise SchemaError(label + ' must be an exact integer.')
        if value.copy_abs() > Decimal(1 << 4095) or (nonnegative and value < 0):
            raise SchemaError(label + ' is outside the admitted integer bounds.')
        return int(value)

    def scalar(value):
        if type(value) is Decimal:
            return integer(value, 'Schema scalar')
        if type(value) not in (str, bool, type(None)):
            raise SchemaError('Schema const/enum values must be bounded scalar literals.')
        return value

    def visit(node, depth=0):
        steps[0] -= 1
        if steps[0] < 0 or depth > MAX_SCHEMA_DEPTH:
            raise ResourceError('Schema exceeds the declared validation budget.')
        if type(node) is not dict:
            raise SchemaError('Every schema node must be an object.')
        out = {}
        for key in _ANNOTATIONS & node.keys():
            if type(node[key]) is not str:
                raise SchemaError('Schema annotation must be text.')
            out[key] = node[key]
        if 'anyOf' in node:
            if set(node) - _ANNOTATIONS - {'anyOf'}:
                raise SchemaError('anyOf must be a separate schema node.')
            variants = node['anyOf']
            if type(variants) is not list or not 1 <= len(variants) <= 8:
                raise SchemaError('anyOf requires one to eight complete variants.')
            out['anyOf'] = [visit(v, depth + 1) for v in variants]
            return out
        kind = node.get('type')
        if 'type' in node and (type(kind) is not str or kind not in _TYPES):
            raise SchemaError('Unsupported schema type.')
        allowed = _ANNOTATIONS | {'type', 'const', 'enum'}
        if kind == 'object':
            allowed |= {'properties', 'required', 'additionalProperties'}
            props, required = node.get('properties'), node.get('required')
            if (type(props) is not dict or type(required) is not list or
                    any(type(k) is not str for k in required) or len(set(required)) != len(required) or
                    not set(required) <= props.keys() or node.get('additionalProperties') is not False):
                raise SchemaError('Object schema requires declared properties, required names and additionalProperties=false.')
            out.update(properties={k: visit(v, depth + 1) for k, v in props.items()},
                       required=list(required), additionalProperties=False)
        elif kind == 'array':
            allowed |= {'items', 'minItems', 'maxItems'}
            if 'items' not in node:
                raise SchemaError('Array schema requires an items schema.')
            out['items'] = visit(node['items'], depth + 1)
        elif kind == 'string':
            allowed |= {'minLength', 'maxLength'}
        elif kind == 'integer':
            allowed |= {'minimum', 'maximum'}
        if set(node) - allowed:
            raise SchemaError('Unsupported JSON schema keyword for the declared type.')
        if kind is not None:
            out['type'] = kind
        if 'const' in node:
            out['const'] = scalar(node['const'])
        if 'enum' in node:
            if type(node['enum']) is not list or not 1 <= len(node['enum']) <= 128:
                raise SchemaError('Schema enum requires one to 128 scalar values.')
            out['enum'] = [scalar(v) for v in node['enum']]
        for lo, hi in (('minimum', 'maximum'), ('minLength', 'maxLength'), ('minItems', 'maxItems')):
            for key in (lo, hi):
                if key in node:
                    out[key] = integer(node[key], key, nonnegative=key != 'minimum' and key != 'maximum')
            if lo in out and hi in out and out[lo] > out[hi]:
                raise SchemaError('Contradictory schema bounds.')
        # Reject contradictory const/type/enum declarations before any provider call.
        for value in ([out['const']] if 'const' in out else out.get('enum', [])):
            trial = {k: v for k, v in out.items() if k not in ('const', 'enum')}
            val = Decimal(value) if type(value) is int else value
            if not _matches(val, trial, [MAX_STEPS]):
                raise SchemaError('Schema scalar contradicts its declared shape.')
        if 'const' in out and 'enum' in out and not any(_equal(out['const'], v) for v in out['enum']):
            raise SchemaError('Schema const contradicts its enum.')
        return out

    return visit(raw)


def admit(schema):
    """Validate trusted caller data too; never retain its mutable references."""
    try:
        text = json.dumps(schema, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError, RecursionError):
        raise SchemaError('Schema must be bounded JSON data.') from None
    return parse_schema(text)


def _equal(left, right):
    # JSON numeric equality, without treating booleans as numbers.
    if type(left) in (int, Decimal) and type(right) in (int, Decimal):
        return left == right
    return type(left) is type(right) and left == right


def _matches(value, schema, steps):
    steps[0] -= 1
    if steps[0] < 0:
        raise ResourceError('JSON shape validation exhausted its step budget.')
    if 'anyOf' in schema:
        return any(_matches(value, branch, steps) for branch in schema['anyOf'])
    kind = schema.get('type')
    good = {None: True, 'object': type(value) is dict, 'array': type(value) is list,
            'string': type(value) is str, 'number': type(value) is Decimal,
            'integer': type(value) is Decimal and value == value.to_integral_value(),
            'boolean': type(value) is bool, 'null': value is None}
    if not good[kind]:
        return False
    if 'const' in schema and not _equal(value, schema['const']):
        return False
    if 'enum' in schema:
        steps[0] -= len(schema['enum'])
        if steps[0] < 0:
            raise ResourceError('JSON shape validation exhausted its step budget.')
        if not any(_equal(value, choice) for choice in schema['enum']):
            return False
    if kind == 'object':
        if not set(schema['required']) <= value.keys() or set(value) - schema['properties'].keys():
            return False
        return all(_matches(item, schema['properties'][key], steps) for key, item in value.items())
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', MAX_DATA_NODES):
            return False
        return all(_matches(item, schema['items'], steps) for item in value)
    if kind == 'string':
        return schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', MAX_TEXT_CHARS)
    if kind == 'integer':
        return ('minimum' not in schema or value >= schema['minimum']) and ('maximum' not in schema or value <= schema['maximum'])
    return True


def validate(text, schema):
    """Return precisely text after a complete bounded shape check, or refuse."""
    declared = admit(schema)
    value = _load(text)
    if not _matches(value, declared, [MAX_STEPS]):
        raise ValidationError('JSON reply does not match its declared shape.')
    return text


def describe(schema):
    """Equivalent factored JSON Schema for prompt display only, never dispatch.

    The provider receives the complete admitted schema. References here merely
    avoid repeating identical explanatory subtrees in its separately budgeted
    prompt. All referenced definitions are present, local and acyclic.
    """
    declared = admit(schema)
    counts, nodes = {}, {}
    def key(node):
        return json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    def children(node):
        return [*node.get('anyOf', []), *node.get('properties', {}).values(),
                *([node['items']] if 'items' in node else [])]
    def count(node):
        encoded = key(node)
        counts[encoded] = counts.get(encoded, 0) + 1
        nodes[encoded] = node
        for child in children(node):
            count(child)
    count(declared)
    labels = {encoded: 'shape' + str(i) for i, encoded in enumerate(sorted(
        k for k, count in counts.items() if count > 1 and len(k) >= 40))}
    def build(node, *, definition=False):
        encoded = key(node)
        if not definition and encoded in labels:
            return {'$ref': '#/$defs/' + labels[encoded]}
        out = dict(node)
        if 'anyOf' in out:
            out['anyOf'] = [build(child) for child in out['anyOf']]
        if 'properties' in out:
            out['properties'] = {name: build(child) for name, child in out['properties'].items()}
        if 'items' in out:
            out['items'] = build(out['items'])
        return out
    described = build(declared)
    if labels:
        described['$defs'] = {label: build(nodes[encoded], definition=True) for encoded, label in labels.items()}
    return json.dumps(described, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

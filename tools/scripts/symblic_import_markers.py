#!/usr/bin/env python3
"""Mechanically mark the execution-pins registry, without importing any target.

Every module listed in symblic/kernel/execution_pins.py must start (after its docstring and __future__
imports) with the import-identity marker (see symblic/kernel/identity.py). This script adds missing markers
or, with --check, reports files that lack one:
  python3 tools/scripts/symblic_import_markers.py --root REPOSITORY_ROOT
  python3 tools/scripts/symblic_import_markers.py --root REPOSITORY_ROOT --check
Only registered first-party Python source files are touched. Existing module
code and import order are preserved. The marker documents why it
must precede dependency imports (including circular helper-first imports).
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

MARKER = ("# Import identity must precede first-party circular imports.\n"
          "_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')\n"
          "_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)\n")
STANDALONE_FILES = frozenset({'symblic/providers/ollama_call.py'})
IDENTITY_HELPER = 'symblic/kernel/identity.py'
REGISTRY_FILE = 'symblic/kernel/execution_pins.py'
REGISTRY_NAMES = frozenset({'PYTHON_FILES', 'REQUIRED_FILES', '_REFORM_FILES', '_CONSTRUCTOR_FILES'})
CONTROLLER_MARKER = ("# A copy run on its own (python3 -I -S ollama_call.py ...) stays stdlib-only; imported from the package it\n"
                     "# records its import identity like every other registered module (symblic.kernel.identity).\n"
                     "if __name__ != '__main__':\n"
                     "    try:\n"
                     "        _symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')\n"
                     "    except ModuleNotFoundError as _symblic_identity_missing:\n"
                     "        if _symblic_identity_missing.name not in ('symblic', 'symblic.kernel', 'symblic.kernel.identity'):\n"
                     "            raise\n"
                     "    else:\n"
                     "        _symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)\n")


def registry_values(root):
    """Interpret only the closed literal registry fragment; never import its module."""
    values = {}

    def evaluate(node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'frozenset'
                and len(node.args) == 1 and not node.keywords):
            return frozenset(evaluate(node.args[0]))
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            items = [evaluate(item) for item in node.elts]
            if any(type(item) is not str for item in items):
                raise ValueError('registry entries must be literal filenames')
            return frozenset(items)
        if isinstance(node, ast.Constant) and type(node.value) is str:
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left, right = evaluate(node.left), evaluate(node.right)
            if type(left) is not frozenset or type(right) is not frozenset:
                raise ValueError('registry union requires filename sets')
            return left | right
        raise ValueError('unsupported static registry expression')

    for statement in ast.parse((root / REGISTRY_FILE).read_bytes()).body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id in REGISTRY_NAMES:
                    value = evaluate(statement.value)
                    if type(value) is not frozenset:
                        raise ValueError('registry assignment requires a filename set')
                    values[target.id] = value
    names, required = values.get('PYTHON_FILES'), values.get('REQUIRED_FILES')
    if (not names or not required or len(names) > 256 or not required <= names
            or any(name.startswith('/') or '\\' in name or not name.endswith('.py')
                   or any(part in ('', '.', '..') for part in name.split('/')) for name in names)):
        raise ValueError('invalid registry')
    if IDENTITY_HELPER not in names or IDENTITY_HELPER not in required:
        raise ValueError('identity helper must be registered and required before installation')
    return values


def registry(root):
    return registry_values(root)['PYTHON_FILES']


def marked(raw, *, standalone=False):
    text = raw.decode('utf-8')
    marker = CONTROLLER_MARKER if standalone else MARKER
    tree = ast.parse(text)
    line = 0
    prefix_count = 0
    for index, statement in enumerate(tree.body):
        if (index == 0 and isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)) or (
                isinstance(statement, ast.ImportFrom) and statement.module == '__future__'):
            line = statement.end_lineno
            prefix_count += 1
        else:
            break
    expected = ast.parse(marker).body
    actual = tree.body[prefix_count:prefix_count + len(expected)]
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Name)
                   and isinstance(node.ctx, ast.Store) and node.id == '_symblic_import_identity']
    if [ast.dump(n) for n in actual] == [ast.dump(n) for n in expected]:
        if len(assignments) != 1:
            raise ValueError('duplicate import marker')
        # Existing semantically identical markers may omit the explanatory
        # comment or use different quotes. Preserve their exact source hashes.
        return raw
    if assignments or marker in text:
        raise ValueError('existing import marker is late or malformed; review manually')
    rows = text.splitlines(keepends=True)
    if line == 0:
        while line < len(rows) and (rows[line].startswith('#') or not rows[line].strip()):
            line += 1
    rows.insert(line, '\n' + marker)
    return ''.join(rows).encode('utf-8')


def check_helper(raw):
    text = raw.decode('utf-8')
    expected = '_symblic_import_identity = record(__file__, sys._getframe().f_code)'
    body = ast.parse(text).body
    if text.count(expected) != 1 or not body or ast.dump(body[-1]) != ast.dump(ast.parse(expected).body[0]):
        raise ValueError('identity helper lacks its final actual-frame self-record')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changes, hashes = [], {}
    for name in sorted(registry(args.root)):
        path = args.root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('source file unavailable: ' + name)
        before = path.read_bytes()
        after = check_helper(before) if name == IDENTITY_HELPER else marked(
            before, standalone=name in STANDALONE_FILES)
        if after != before:
            changes.append(name)
            if not args.check:
                path.write_bytes(after)
        hashes[name] = hashlib.sha256(after).hexdigest()
    print(json.dumps({'check': args.check, 'changed': changes, 'files': len(hashes), 'sha256': hashes}, sort_keys=True))
    return 1 if args.check and changes else 0


if __name__ == '__main__':
    raise SystemExit(main())

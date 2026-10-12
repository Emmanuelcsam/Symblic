"""The linear constructor's solver worker: one short-lived process that runs Z3 on a bounded JSON contract.

What it is for
    symblic.linear.constructor starts this file as `python -I -S -B -X pycache_prefix=TMP worker.py` with the
    interpreter named in the runtime record, writes one JSON request to its standard input and reads one JSON
    reply. The request holds the compiled contract (variables and linear constraints as JSON, never source
    text or SMT-LIB), the pinned package file hashes, the site-packages path, a time budget in milliseconds,
    a Z3 resource limit and an address-space limit. The worker verifies every package file against its pin,
    applies the OS limits, loads exactly the pinned libz3 and z3 package from that path, asks Z3 for up to two
    distinct satisfying assignments, and replies with the assignments, the solver statuses and the limits it
    applied. The caller re-checks every assignment with the native kernel; nothing here decides an answer.

    It imports only the standard library and, inside main(), the pinned z3 package; it never imports the
    symblic package, so it can run in an isolated interpreter.

Limits
    The resource bounds are operational limits, not a sandbox, and do not protect against a malicious local
    user or interpreter. "D10" in names is the prototype's name in the development notes.

Depends on: the standard library; z3-solver 4.15.4.0 at run time. Used by: symblic.linear.constructor (_invoke).
Status: prototype; not exercised by the automated tests (they use a fake worker).
"""
from __future__ import annotations

import builtins
import ctypes
import hashlib
import importlib.util
import json
import math
import resource
import sys
import time
from pathlib import Path

MAX_BYTES = 65536
MAX_BITS = 256
PROTOCOL = 3
MAX_ADDRESS_SPACE_BYTES = 320 * 1024 * 1024


def require(ok, message='worker_input'):
    if not ok:
        raise ValueError(message)


def check_tree(root):
    count = 0
    def visit(value, depth):
        nonlocal count
        count += 1
        require(count <= 4096 and depth <= 32)
        if type(value) in (bool, type(None)):
            return
        if type(value) is str:
            require(len(value) <= MAX_BYTES)
        elif type(value) is int:
            require(value.bit_length() <= MAX_BITS)
        elif type(value) is list:
            require(len(value) <= 4096)
            for child in value:
                visit(child, depth + 1)
        elif type(value) is dict:
            require(len(value) <= 4096 and all(type(key) is str for key in value))
            for child in value.values():
                visit(child, depth + 1)
        else:
            require(False)
    visit(root, 0)


def package_check(rows, purelib):
    require(type(rows) is dict and 1 <= len(rows) <= 256, 'package_pin')
    require(type(purelib) is str and len(purelib) <= 4096 and Path(purelib).is_absolute(), 'private_import_root')
    base = Path(purelib).resolve()
    require(base.is_dir() and str(base) == purelib, 'private_import_root')
    total = 0
    for name, expected in rows.items():
        parts = Path(name).parts
        require(parts and not Path(name).is_absolute() and '..' not in parts and
                (parts[0] == 'z3' or parts[0] == 'z3_solver-4.15.4.0.dist-info'), 'package_pin')
        require(type(expected) is str and len(expected) == 64, 'package_pin')
        path = base / name
        require(not path.is_symlink() and path.is_file(), 'package_pin')
        require(path.stat().st_size <= 40_000_000, 'package_budget')
        with path.open('rb') as stream:
            raw = stream.read(40_000_001)
        total += len(raw)
        require(total <= 64_000_000, 'package_budget')
        require(hashlib.sha256(raw).hexdigest() == expected, 'package_drift')
    # Host-held pin set must include every package payload, not an arbitrary subset.
    actual = {str(p.relative_to(base)) for dirname in ('z3', 'z3_solver-4.15.4.0.dist-info')
              for p in (base / dirname).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    require(actual == set(rows), 'package_inventory')
    return base


def solve(request):
    require(type(request) is dict and set(request) == {'protocol', 'address_space_bytes', 'contract', 'package', 'purelib', 'z3_version', 'milliseconds', 'resource_limit'})
    require(type(request['protocol']) is int and request['protocol'] == PROTOCOL, 'worker_protocol')
    address_space = request['address_space_bytes']
    require(type(address_space) is int and 64 * 1024 * 1024 <= address_space <= MAX_ADDRESS_SPACE_BYTES and
            address_space % (1024 * 1024) == 0, 'address_space_bytes')
    milliseconds, limit = request['milliseconds'], request['resource_limit']
    require(type(milliseconds) is int and 1 <= milliseconds <= 5000 and
            type(limit) is int and 1 <= limit <= 1_000_000)
    deadline = time.monotonic() + milliseconds / 1000
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    require(resource.getrlimit(resource.RLIMIT_AS) == (address_space, address_space), 'effective_address_space')
    resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(milliseconds / 1000) + 1,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    private_root = package_check(request['package'], request['purelib'])
    # -S skips site/.pth/sitecustomize; never use system purelib derived under
    # old-Python -S venv semantics. Only the explicit verified root is admitted.
    library = private_root / 'z3/lib/libz3.so'
    # The reviewed z3core searches cwd/system paths by default. Load exactly the
    # already hashed private library first; failure ends this worker.
    pinned_library = ctypes.CDLL(str(library))
    builtins.Z3_LIB_DIRS = [str(library.parent)]
    spec = importlib.util.spec_from_file_location('z3', private_root / 'z3/__init__.py')
    require(spec is not None and spec.loader is not None, 'private_package_spec')
    z3 = importlib.util.module_from_spec(spec)
    sys.modules['z3'] = z3
    spec.loader.exec_module(z3)
    # The pinned generated z3core deletes its _lib name after wrapping symbols.
    # Compare the actual wrapper symbol with our explicit library handle instead.
    wrapped = z3.z3core.Z3_get_version.__defaults__[0].f
    require(ctypes.cast(wrapped, ctypes.c_void_p).value ==
            ctypes.cast(pinned_library.Z3_get_version, ctypes.c_void_p).value, 'loaded_library_identity')
    require(request['z3_version'] == '4.15.4' and z3.get_version_string() == '4.15.4', 'solver_version')
    contract = request['contract']
    require(type(contract) is dict and set(contract) == {'version', 'variables', 'constraints'} and type(contract['version']) is int and contract['version'] == 2)
    rows, constraints = contract['variables'], contract['constraints']
    require(type(rows) is list and 1 <= len(rows) <= 16 and type(constraints) is list and 1 <= len(constraints) <= 64)
    variables = {}
    for index, row in enumerate(rows):
        require(type(row) is dict and set(row) in ({'id', 'sort', 'path'}, {'id', 'sort', 'path', 'lo', 'hi'}))
        require(row['id'] == 'v' + str(index) and row['sort'] in ('bool', 'int', 'number'))
        variables[row['id']] = {'bool': z3.Bool, 'int': z3.Int, 'number': z3.Real}[row['sort']](row['id'])

    def rational(raw):
        require(type(raw) is list and len(raw) == 2 and all(type(x) is str and len(x) <= 80 for x in raw))
        for text in raw:
            require(text.isascii() and bool(text) and (text.isdigit() or (text.startswith('-') and text[1:].isdigit())))
        n, d = map(int, raw)
        require(d > 0 and max(n.bit_length(), d.bit_length()) <= MAX_BITS)
        return z3.RealVal(f'{n}/{d}')

    def affine(raw):
        require(type(raw) is dict and set(raw) == {'constant', 'terms'})
        terms = raw['terms']
        require(type(terms) is list and len(terms) <= 16)
        seen, out = set(), rational(raw['constant'])
        for key, coeff in terms:
            require(key in variables and key not in seen and not z3.is_bool(variables[key]))
            seen.add(key)
            out = out + rational(coeff) * variables[key]
        return out

    def formula(raw):
        require(type(raw) is list and 2 <= len(raw) <= 4)
        op = raw[0]
        if op == 'literal':
            require(len(raw) == 2 and type(raw[1]) is bool)
            return z3.BoolVal(raw[1])
        if op == 'variable':
            require(len(raw) == 2 and raw[1] in variables and z3.is_bool(variables[raw[1]]))
            return variables[raw[1]]
        if op == 'all':
            require(len(raw) == 2 and type(raw[1]) is list and 1 <= len(raw[1]) <= 64)
            return z3.And([formula(item) for item in raw[1]])
        if op == 'not':
            require(len(raw) == 2)
            return z3.Not(formula(raw[1]))
        if op in ('and', 'or', '->', '<->', 'xor'):
            require(len(raw) == 3)
            a, b = formula(raw[1]), formula(raw[2])
            if op == '<->':
                return a == b
            return {'and': z3.And, 'or': z3.Or, '->': z3.Implies, 'xor': z3.Xor}[op](a, b)
        require(op == 'compare' and len(raw) == 4 and raw[1] in ('=', '!=', '<', '<=', '>', '>='))
        a, b = affine(raw[2]), affine(raw[3])
        return {'=': lambda: a == b, '!=': lambda: a != b, '<': lambda: a < b,
                '<=': lambda: a <= b, '>': lambda: a > b, '>=': lambda: a >= b}[raw[1]]()

    solver = z3.Solver()
    solver.set(threads=1, random_seed=0)
    solver.add([formula(item) for item in constraints])
    for row in rows:
        if 'lo' in row:
            require(row['sort'] != 'bool')
            solver.add(variables[row['id']] >= rational(row['lo']), variables[row['id']] <= rational(row['hi']))
    checks, assignments, used = [], [], 0
    # A fixed partition bounds requested solver work across both checks.
    budgets = (limit // 2 or 1, limit - (limit // 2 or 1))
    for iteration, work in enumerate(budgets):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0 or work <= 0:
            checks.append({'status': 'timeout' if remaining <= 0 else 'unknown', 'reason': 'aggregate_budget'})
            break
        solver.set(timeout=remaining, rlimit=work)
        verdict = solver.check()
        status = str(verdict)
        reason = solver.reason_unknown()[:256] if verdict == z3.unknown else ''
        checks.append({'status': 'timeout' if 'timeout' in reason else status, 'reason': reason})
        for key, value in solver.statistics():
            if key == 'rlimit count':
                used = int(value)
        if verdict != z3.sat:
            break
        model = solver.model()
        assignment, blocked = {}, []
        for row in rows:
            item = model.eval(variables[row['id']], model_completion=True)
            if row['sort'] == 'bool':
                require(z3.is_true(item) or z3.is_false(item), 'non_boolean_model')
                assignment[row['id']] = z3.is_true(item)
            else:
                if z3.is_int_value(item):
                    n, d = item.as_long(), 1
                else:
                    require(z3.is_rational_value(item), 'non_rational_model')
                    n, d = item.numerator_as_long(), item.denominator_as_long()
                require(max(n.bit_length(), d.bit_length()) <= MAX_BITS, 'model_number_budget')
                assignment[row['id']] = [str(n), str(d)]
            blocked.append(variables[row['id']] != item)
        assignments.append(assignment)
        if iteration == 0:
            solver.add(z3.Or(blocked))
    limits = {'requested': {'milliseconds': milliseconds, 'rlimit_total': limit, 'address_space_bytes': address_space},
              'effective_os': {name: list(resource.getrlimit(kind)) for name, kind in
                               (('address_space_bytes', resource.RLIMIT_AS), ('cpu_seconds', resource.RLIMIT_CPU),
                                ('file_bytes', resource.RLIMIT_FSIZE), ('core_bytes', resource.RLIMIT_CORE),
                                ('open_files', resource.RLIMIT_NOFILE))},
              'z3_applied': {'threads': 1, 'random_seed': 0, 'allocated_check_rlimits': list(budgets)},
              'private_import_root': str(private_root), 'loaded_library': str(library)}
    return {'protocol': PROTOCOL, 'version': 2, 'z3_version': z3.get_version_string(), 'checks': checks,
            'assignments': assignments, 'resource_used': used, 'limits': limits}


def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and sys.pycache_prefix, 'worker_mode')
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES)
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, 'duplicate_json_key')
            out[key] = value
        return out
    def constant(value):
        raise ValueError('nonfinite_json_constant')
    request = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    check_tree(request)
    result = solve(request)
    raw = json.dumps(result, separators=(',', ':'), allow_nan=False).encode()
    require(len(raw) <= MAX_BYTES, 'output_budget')
    sys.stdout.buffer.write(raw)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # noqa: BLE001 - final child boundary; parent treats every failure as unknown
        print(type(error).__name__ + ': ' + str(error)[:256], file=sys.stderr)
        raise SystemExit(1) from None

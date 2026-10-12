"""JavaScript declaration contracts: check which top-level names a script declares, by parsing it, never running it.

    js_declarations_check(source, {version: 1, exports: {renderBoard: "function", SIZE: "const"}})   # builtin

A program that assembles a page from model-written units can require that a unit declares exactly the names
and kinds it promised (function, class, const, let, var), with only passive initializers (literals, functions,
plain objects and arrays), so that loading the unit cannot run code. Acorn 8.8.1 (vendored as acorn.js, MIT
licence in acorn-LICENSE.txt) parses ECMAScript 2022 script syntax inside the same sandbox as js_test
(symblic/sandbox/landlock.py); contract_runner.js is the parse-only child.

It checks exact top-level names and kinds and passive declaration initializers, not function behaviour, the
project's intent, side effects on invocation or JavaScript purity. This loading policy is separate from
js_test and js_run.

Depends on: symblic.kernel.language, symblic.js.check (sandbox, node discovery, bounded pipes) and the assets
contract_runner.js and acorn.js. Used by: the js_declarations_check builtin and symblic.js.normalize (the pinned
parser hash).
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path

from symblic.kernel import language as S
from symblic.js import check as JS

ADAPTER = 4
PARSER_VERSION = '8.8.1'
PARSER_SHA256 = 'cb3b2d439857d6e4514d23a1219f6354c23498f5fa81fdf2691a5a9e53de43c0'
MAX_SOURCE_BYTES = 400000
MAX_REQUEST_BYTES = 500000
MAX_OUTPUT_BYTES = 65536
WALL_SECONDS = 5
HEAP_MB = 128
HERE = Path(__file__).resolve().parent
ASSETS = {'runner': 'contract_runner.js', 'parser': 'acorn.js', 'license': 'acorn-LICENSE.txt'}
_assets = {}
_NAME = re.compile(r'[$A-Za-z_][$A-Za-z_0-9]{0,127}\Z')
KINDS = frozenset({'function', 'class', 'const', 'let', 'var'})
SCOPE = 'exact_top_level_declarations_under_passive_loading_policy'
HINTS = {
    'unexpected_name': 'Remove the undeclared top-level binding or amend the caller contract explicitly.',
    'missing_name': 'Define the exact binding required by the caller contract.',
    'wrong_kind': 'Use the declaration kind specified by the caller contract.',
    'duplicate_name': 'Declare each top-level name exactly once.',
    'unsupported_identifier': 'This optional policy supports ASCII identifiers of at most 128 characters.',
    'top_level_statement': 'Only declarations, empty semicolons and the use-strict directive are allowed.',
    'active_initializer': 'Use a passive initializer; defer calls, reads and computed work to a function body.',
    'active_class_definition': 'This policy forbids inheritance, computed keys, static blocks and active static initializers.',
    'destructuring_declaration': 'Use separate simple identifier declarations for the specified names.',
    'syntax_error': 'The source must parse as an ECMAScript 2022 script, without top-level return/import/export.',
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def asset_snapshot():
    """Freeze fixed bounded assets per process; refuse disk drift before parsing."""
    current = {}
    for key, name in ASSETS.items():
        try:
            with (HERE / name).open('rb') as stream:
                raw = stream.read(1000001)
        except OSError:
            raise JS.JsError(f'JavaScript declaration {key} asset is unavailable', kind='unavailable') from None
        if len(raw) > 1000000:
            raise JS.JsError('JavaScript declaration asset exceeds its limit', kind='budget')
        current[key] = raw
    if _sha(current['parser']) != PARSER_SHA256:
        raise JS.JsError('JavaScript declaration parser differs from pinned Acorn 8.8.1', kind='version')
    current['sandbox'] = JS.asset_snapshot()['sandbox']
    if _assets and current != _assets:
        raise JS.JsError('JavaScript declaration assets changed; start a fresh worker', kind='version')
    if not _assets:
        _assets.update(current)
    return dict(_assets)


def asset_hashes():
    return {name: _sha(raw) for name, raw in asset_snapshot().items()}


def __getattr__(name):
    if name == 'VERSION':
        identity = json.dumps(asset_hashes(), sort_keys=True, separators=(',', ':')).encode()
        return f'{ADAPTER}+acorn{PARSER_VERSION}+node{JS.node_version() or "-none"}+assets{_sha(identity)}'
    raise AttributeError(name)


def _request(source, contract):
    if type(source) is not str:
        raise JS.JsError('Declaration source must be one JavaScript script as text', kind='type')
    try:
        raw = source.encode('utf-8')
    except UnicodeError:
        raise JS.JsError('Declaration source must be valid Unicode', kind='type') from None
    if len(raw) > MAX_SOURCE_BYTES:
        raise JS.JsError('Declaration source exceeds 400000 UTF-8 bytes', kind='budget')
    if (type(contract) is not dict or set(contract) != {'version', 'exports'}
            or type(contract['version']) is not int or contract['version'] != 1
            or type(contract['exports']) is not dict or len(contract['exports']) > 128):
        raise JS.JsError('Declaration contract requires version 1 and at most 128 exact exports', kind='type')
    for name, kind in contract['exports'].items():
        if type(name) is not str or not _NAME.fullmatch(name) or type(kind) is not str or kind not in KINDS:
            raise JS.JsError('Exports need ASCII JavaScript identifiers and function/class/const/let/var kinds', kind='type')
    contract_raw = json.dumps(contract, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    body = json.dumps({'source': source, 'exports': contract['exports']}, ensure_ascii=False).encode()
    if len(body) > MAX_REQUEST_BYTES:
        raise JS.JsError('Encoded declaration request exceeds 500000 bytes', kind='budget')
    return body, _sha(raw), _sha(contract_raw)


def _bounded_result(status, code):
    return {'passed': False, 'status': status, 'declarations': [], 'truncated': False,
            'diagnostics': [{'code': code, 'line': None, 'column': None, 'name': None}]}


def _parse(body, assets, *, deadline=None):
    """Launch only trusted parser assets under the same required isolation as js_test."""
    node = JS.node_path()
    if not node:
        raise JS.JsError('JavaScript declaration parser needs the native Node runtime', kind='unavailable')
    wall = WALL_SECONDS
    if deadline is not None:
        wall = min(wall, deadline - time.monotonic())
        if wall <= 0:
            return _bounded_result('budget', 'deadline')
    end = min(time.monotonic() + wall, deadline) if deadline is not None else time.monotonic() + wall
    with tempfile.TemporaryDirectory(prefix='symblic-js-declarations-') as scratch:
        for name, raw in (('runner.js', assets['runner']), ('acorn.js', assets['parser']),
                          ('sandbox.py', assets['sandbox'])):
            Path(scratch, name).write_bytes(raw)
        node_root = os.path.dirname(os.path.dirname(os.path.realpath(node)))
        argv = ['/usr/bin/python3', '-I', str(Path(scratch, 'sandbox.py')), '--require', '--no-unix',
                '--net-connect', '1', '--rx', node_root, '--cwd', scratch, '--', os.path.realpath(node),
                f'--max-old-space-size={HEAP_MB}', '--disallow-code-generation-from-strings',
                str(Path(scratch, 'runner.js'))]
        env = {'PATH': '/usr/bin:/bin', 'HOME': scratch, 'LANG': 'C.UTF-8', 'TMPDIR': scratch}
        try:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, cwd=scratch, env=env, start_new_session=True)
        except OSError:
            raise JS.JsError('JavaScript declaration sandbox could not start', kind='unavailable') from None
        try:
            output, error = JS._communicate_bounded(process, body, deadline=end,
                                                    max_output_bytes=MAX_OUTPUT_BYTES)
        except subprocess.TimeoutExpired:
            return _bounded_result('budget', 'timeout')
        except JS.JsError as exc:
            if exc.kind != 'budget':
                raise
            return _bounded_result('budget', 'output_limit')
    if process.returncode == 125:
        raise JS.JsError('JavaScript declaration sandbox refused required isolation', kind='unavailable')
    if len(output) > MAX_OUTPUT_BYTES:
        return _bounded_result('budget', 'output_limit')
    if process.returncode:
        if b'heap' in error.lower() or b'memory' in error.lower():
            return _bounded_result('budget', 'memory_limit')
        raise JS.JsError('JavaScript declaration parser process failed', kind='js')
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise JS.JsError('JavaScript declaration parser returned invalid data', kind='js') from None
    if (type(result) is not dict or set(result) != {'passed', 'status', 'declarations', 'diagnostics', 'truncated'}
            or type(result['passed']) is not bool or type(result['truncated']) is not bool
            or result['status'] not in ('accepted', 'invalid', 'budget', 'error')
            or type(result['declarations']) is not list or len(result['declarations']) > 128
            or type(result['diagnostics']) is not list or len(result['diagnostics']) > 32
            or result['passed'] != (result['status'] == 'accepted')
            or (result['passed'] and (result['diagnostics'] or result['truncated']))):
        raise JS.JsError('JavaScript declaration parser returned a malformed result', kind='js')
    for row in result['declarations']:
        if (type(row) is not dict or set(row) != {'name', 'kind', 'line', 'column'}
                or type(row['name']) is not str or not _NAME.fullmatch(row['name'])
                or type(row['kind']) is not str or row['kind'] not in KINDS
                or any(type(row[key]) is not int or not 1 <= row[key] <= MAX_SOURCE_BYTES + 1
                       for key in ('line', 'column'))):
            raise JS.JsError('JavaScript declaration parser returned a malformed declaration', kind='js')
    for row in result['diagnostics']:
        if (type(row) is not dict or set(row) != {'code', 'name', 'line', 'column'}
                or type(row['code']) is not str or not re.fullmatch(r'[a-z_]{1,48}', row['code'])
                or (row['name'] is not None and (type(row['name']) is not str or not _NAME.fullmatch(row['name'])))
                or any(row[key] is not None and (type(row[key]) is not int or not 1 <= row[key] <= MAX_SOURCE_BYTES + 1)
                       for key in ('line', 'column'))):
            raise JS.JsError('JavaScript declaration parser returned a malformed diagnostic', kind='js')
    return result


def check(source, contract, *, deadline=None):
    """Check one script's declaration surface; never execute the candidate.

    Invalid declarations yield status=invalid, resource exhaustion status=budget.
    Malformed caller contracts and unavailable/drifted runtimes raise JsError.
    The receipt binds exact source bytes, normalized contract and parser assets;
    it is not a signature or proof of the function bodies' behavior.
    """
    deadline = JS._effective_deadline(deadline)
    body, source_hash, contract_hash = _request(source, contract)
    assets = asset_snapshot()
    result = _parse(body, assets, deadline=deadline)
    if result['passed']:
        declared = {row['name']: row['kind'] for row in result['declarations']}
        if len(declared) != len(result['declarations']) or declared != json.loads(body)['exports']:
            raise JS.JsError('JavaScript declaration parser accepted an inconsistent export surface', kind='js')
    for row in result['diagnostics']:
        row['message'] = HINTS.get(row['code'], 'The parser did not complete within its declared limits or protocol.')
    details = ['- ' + row['code'] + (f' ({row["name"]})' if row['name'] is not None else '')
               + ': ' + row['message'] for row in result['diagnostics']]
    return {**result, 'version': ADAPTER, 'scope': SCOPE, 'source_sha256': source_hash,
            'contract_sha256': contract_hash,
            'parser': {'name': 'acorn', 'version': PARSER_VERSION, 'ecma_version': 2022, 'source_type': 'script'},
            'runtime': {'node': JS.node_version(), 'assets': {key: _sha(raw) for key, raw in assets.items()}},
            'report': ('Exact declared top-level surface accepted; function behavior is unassessed.'
                       if result['passed'] else 'Declaration contract ' + result['status'] + ':\n' + '\n'.join(details))}


_REQUIRE_COMPLETE = ContextVar('symblic_declaration_verdict_required', default=False)


@contextmanager
def require_complete_scope():
    """Trusted construction policy: resource limits cannot be candidate failures.

    Ordinary declaration-report calls retain their public status-valued interface.
    This scope applies only to the native helper, not the read-only Python checker.
    Worker threads must explicitly enter it, as they do for verification deadlines.
    """
    token = _REQUIRE_COMPLETE.set(True)
    try:
        yield
    finally:
        _REQUIRE_COMPLETE.reset(token)


def _js_declarations_check(kernel, node, source, contract):
    # Native exact integers are Fraction values. Convert only this known field;
    # do not loosely coerce caller contracts or serialize arbitrary values.
    if type(contract) is dict:
        contract = dict(contract)
        version = contract.get('version')
        if type(version) is Fraction and version.denominator == 1:
            contract['version'] = version.numerator
    JS._charge(kernel, 10, node)
    deadline = JS._effective_deadline()
    result = check(source, contract, **({'deadline': deadline} if deadline is not None else {}))
    if _REQUIRE_COMPLETE.get() and result.get('status') in ('budget', 'error'):
        raise JS.JsError('Declaration verification inconclusive: ' + result.get('report', result['status']),
                         kind='resource')
    return S.from_json(result)


FUNCTIONS = {'js_declarations_check': _js_declarations_check}

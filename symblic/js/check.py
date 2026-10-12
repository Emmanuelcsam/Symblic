"""The JavaScript adapter: run model-written JavaScript against examples, deterministically and sandboxed.

    js_test(source, cases)  ->  {passed: Bool, total: Int, failed: Int, report: Text}     # Symblic builtins
    js_run(source, call)    ->  the JSON value of one call

`source` is a text or a list of texts (pieces). Pieces run in order as separate classic scripts in one realm, like
consecutive <script> blocks, and a piece that replaces a function an earlier piece defined fails ("defines f
again"). `cases` is a list of `[call, expected]` pairs: `call` is a JavaScript expression evaluated after the source,
and `expected` is the JSON text of the value it must give. Values compare as JSON: objects by key regardless of
order, lists in order, numbers by value, `true` never equal to `1`. This is how a program checks a `Code js`
answer before accepting it.

What makes a result depend only on (source, cases):
  * every case runs in a fresh V8 context (node's vm) built from a null-prototype object. Nothing from the host
    realm is passed in and only JSON text comes back. Code generation from strings (eval, new Function) is off in
    the context, which closes the constructor-chain escape. Math.random throws, Date is fixed, console is a no-op.
  * the node process runs under symblic/sandbox/landlock.py: Landlock read-only system directories, node's own
    install read/exec, an empty private scratch directory as the only writable place (the runner script is copied
    there, so the repository is not visible), no TCP (connect allowed to port 1 only, bind denied), no unix
    sockets, no new privileges, a new session and a scrubbed environment.
  * limits: 3 s per case, 256 MiB of V8 heap, 2 GiB address space (symblic/kernel/process_limits.py), child CPU
    and whole-check wall limits, and finite I/O.

A timeout, exhausted memory or unavailable runtime leaves the check inconclusive. These observations cannot
reject a candidate or trigger model repair; another machine or load may complete the same check. A timed-out
case is observed again (REOBSERVE more times, each after a bounded wait for the machine's load to drop under
CALM_LOAD per CPU and its I/O pressure under CALM_IO): 3 s of wall time on a heavily loaded machine is a fraction
of a second of CPU, and a build must not lose a verdict to that. A case that still times out stays
inconclusive; the rows say `reobserved`. The adapter and Node versions are part of the kernel identity
(symblic.kernel.language.kernel_id), because another JavaScript engine may give other results. Model-written code
is not trusted by this module: it is a test oracle, not a sandbox for anything else.

Requirements: Linux with Landlock network rules (ABI 4, Linux 6.7 or newer) and Node.js (found as $SYMBLIC_NODE,
the newest ~/.nvm install, or `node` on PATH; tested with Node 22). Without them available() is false and every
check is inconclusive ("unavailable"), never passed.

Depends on: symblic.kernel.language; the assets runner.js, acorn.js and acorn-LICENSE.txt in this folder,
symblic/sandbox/landlock.py and symblic/kernel/process_limits.py, which are copied into the scratch directory.
Used by: the js_test and js_run builtins (symblic.kernel.language.ADAPTERS) and symblic.js.contract.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from contextlib import contextmanager
from contextvars import ContextVar
import decimal
import glob
import hashlib
import json
import math
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

from symblic.kernel import language as S

ADAPTER = 12                       # 12: thrown-path binding evidence and dual-realm wall accounting
CASE_MS = 3000
HEAP_MB = 256
MAX_SOURCE = 400_000
MAX_PIECES = 200
MAX_CASES = 200
MAX_CALL = 4_000
MAX_EXPECTED = 200_000
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024
REPORT_FAILURES = 6
STEPS_PER_CASE = 10
HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.dirname(HERE)            # the symblic package directory
RUNNER = os.path.join(HERE, 'runner.js')                                  # the node child (this package)
SANDBOX = os.path.join(PACKAGE, 'sandbox', 'landlock.py')                 # Landlock/seccomp launcher
LIMITER = os.path.join(PACKAGE, 'kernel', 'process_limits.py')           # CPU/address-space limiter
PARSER = os.path.join(HERE, 'acorn.js')                                   # pinned Acorn 8.8.1 (MIT)
PARSER_LICENSE = os.path.join(HERE, 'acorn-LICENSE.txt')
PARSER_SHA256 = 'cb3b2d439857d6e4514d23a1219f6354c23498f5fa81fdf2691a5a9e53de43c0'
INCONCLUSIVE = frozenset({'timeout', 'resource', 'unavailable', 'memory', 'oom'})
REOBSERVE = 2                      # further observations of a timed-out case, each once the host is calm
CALM_LOAD = 1.5                    # 1-minute load per CPU at or under which the host counts as calm
CALM_IO = 40.0                     # I/O pressure (PSI `some` avg10, percent) at or under which it counts as calm
CALM_WAIT_S = 90.0                 # the longest wait for a calm host before one re-observation
_found: dict = {}
_assets: dict = {}


class JsError(S.SymblicError):
    """An input outside the adapter's domain, an exceeded limit, or a JavaScript engine that is not available."""


_verification_deadline = ContextVar('symblic_js_verification_deadline', default=None)


def _effective_deadline(deadline=None):
    """Use the stricter trusted monotonic deadline without granting candidate authority."""
    if deadline is not None:
        try:
            valid = type(deadline) in (int, float) and math.isfinite(deadline)
        except OverflowError:
            valid = False
        if not valid:
            raise JsError('JavaScript verification deadline must be finite monotonic seconds or None', kind='type')
    inherited = _verification_deadline.get()
    if deadline is None:
        return inherited
    return min(deadline, inherited) if inherited is not None else deadline


@contextmanager
def verification_deadline_scope(deadline):
    """Bind a deadline to this evaluation context; nested scopes can only shorten it.

    A worker thread must enter its own scope. Reset in finally prevents one run's
    deadline from leaking into a later run on the same thread.
    """
    token = _verification_deadline.set(_effective_deadline(deadline))
    try:
        yield
    finally:
        _verification_deadline.reset(token)


def asset_snapshot():
    """Read bounded fixed first-party sources once; detect later disk drift.

    The exact same bytes are hashed for kernel identity and copied for execution.
    Nothing supplied by a candidate controls these paths or hashes.
    """
    current = {}
    for name, path in (('runner', RUNNER), ('sandbox', SANDBOX), ('limiter', LIMITER),
                       ('parser', PARSER), ('license', PARSER_LICENSE)):
        try:
            with open(path, 'rb') as source:
                raw = source.read(1_000_001)
        except OSError:
            raise JsError('the JavaScript ' + name + ' is unavailable', kind='unavailable') from None
        if len(raw) > 1_000_000:
            raise JsError('the JavaScript ' + name + ' exceeds the asset limit', kind='budget')
        current[name] = raw
    if hashlib.sha256(current['parser']).hexdigest() != PARSER_SHA256:
        raise JsError('the JavaScript parser differs from pinned Acorn 8.8.1', kind='version')
    if _assets and current != _assets:
        raise JsError('the JavaScript runtime assets changed; start a fresh worker', kind='version')
    if not _assets:
        _assets.update(current)
    return dict(_assets)


def asset_hashes():
    return {name: hashlib.sha256(raw).hexdigest() for name, raw in asset_snapshot().items()}


def node_path() -> str | None:
    """The node binary: $SYMBLIC_NODE, the newest nvm install, then PATH."""
    if 'path' not in _found:
        found = os.environ.get('SYMBLIC_NODE') or ''
        if not (found and os.access(found, os.X_OK)):
            versions = sorted(glob.glob(os.path.expanduser('~/.nvm/versions/node/v*/bin/node')),
                              key=lambda p: [int(x) for x in re.findall(r'\d+', p.split('/node/v')[-1])[:3]])
            found = versions[-1] if versions else (shutil.which('node') or '')
        _found['path'] = found if found and os.access(found, os.X_OK) else None
    return _found['path']


def node_version() -> str | None:
    """'22.17.0', read once per process (from an nvm path when it names one, else by asking node)."""
    if 'version' not in _found:
        path, version = node_path(), None
        if path:
            m = re.search(r'/node/v(\d+\.\d+\.\d+)/bin/node$', path)
            if m:
                version = m.group(1)
            else:
                try:
                    out = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=10).stdout
                    version = out.strip().lstrip('v') or None
                except (OSError, subprocess.SubprocessError):
                    version = None
        _found['version'] = version
    return _found['version']


def __getattr__(name):
    # The kernel identity reads VERSION; reading it must not run node at import time, so it is computed on first use.
    if name == 'VERSION':
        assets = hashlib.sha256(json.dumps(asset_hashes(), sort_keys=True).encode()).hexdigest()
        return f'{ADAPTER}+node{node_version() or "-none"}+assets{assets}'
    raise AttributeError(name)


def available() -> bool:
    """Necessary local runtime capabilities; the child still enforces every rule.

    Reading the kernel ABI does not restrict this process or execute a candidate.
    Merely finding Node cannot establish availability of --require --net-connect.
    """
    if not (node_path() and all(os.path.exists(path) for path in
                               (RUNNER, SANDBOX, LIMITER, PARSER, PARSER_LICENSE))):
        return False
    try:
        landlock = __import__('importlib').import_module('symblic.sandbox.landlock')
        return landlock.abi_version() >= landlock.NET_ABI
    except (ImportError, OSError, AttributeError, TypeError):
        return False


def _communicate_bounded(proc, body: bytes, *, deadline, max_output_bytes=MAX_OUTPUT_BYTES,
                         max_error_bytes=MAX_ERROR_BYTES):
    """Pump binary pipes without accumulating unbounded child output.

    The caller starts an isolated process group. On any failure we kill/reap
    that group and close pipes without an unbounded final communicate().
    """
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    limits = {'stdout': max_output_bytes, 'stderr': max_error_bytes}
    offset = 0
    complete = False
    with selectors.DefaultSelector() as ready:
        try:
            for name in ('stdin', 'stdout', 'stderr'):
                pipe = getattr(proc, name)
                os.set_blocking(pipe.fileno(), False)
                if name == 'stdin' and not body:
                    pipe.close()
                else:
                    ready.register(pipe, selectors.EVENT_WRITE if name == 'stdin' else selectors.EVENT_READ, name)
            while ready.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(proc.args, 0)
                for key, _ in ready.select(remaining):
                    pipe, name = key.fileobj, key.data
                    if name == 'stdin':
                        try:
                            offset += os.write(pipe.fileno(), body[offset:offset + 65536])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            offset = len(body)
                        if offset == len(body):
                            ready.unregister(pipe)
                            pipe.close()
                    else:
                        # Read at most one byte beyond the limit, even for huge writes.
                        try:
                            chunk = os.read(pipe.fileno(), min(65536, limits[name] - len(buffers[name]) + 1))
                        except BlockingIOError:
                            continue
                        if not chunk:
                            ready.unregister(pipe)
                            pipe.close()
                        elif len(buffers[name]) + len(chunk) > limits[name]:
                            raise JsError(f'the JavaScript {name} exceeds its output byte budget', kind='budget')
                        else:
                            buffers[name].extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(proc.args, 0)
            proc.wait(timeout=remaining)
            complete = True
            return bytes(buffers['stdout']), bytes(buffers['stderr'])
        finally:
            if not complete:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for name in ('stdin', 'stdout', 'stderr'):
                getattr(proc, name).close()
            if not complete:
                proc.wait()


def evaluate(source, calls: list[str], case_ms: int = CASE_MS, *, deadline=None,
             max_output_bytes=MAX_OUTPUT_BYTES) -> list[dict]:
    """Each call's outcome: {'ok': True, 'value': json text} or {'ok': False, 'kind', 'error', 'piece', 'line'}.
    `source` is a text or a list of texts run as separate scripts (pieces)."""
    deadline = _effective_deadline(deadline)
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise JsError('JavaScript output byte budget must be an integer from 1 to 8388608', kind='budget')
    if not available():
        raise JsError('the JavaScript adapter requires Node, its runtime assets and Landlock network isolation '
                      '(ABI 4 or newer) on this machine', kind='unavailable')
    if deadline is not None and time.monotonic() >= deadline:
        raise JsError('the aggregate JavaScript recheck time budget is exhausted', kind='budget')
    assets = asset_snapshot()
    node = node_path()
    with tempfile.TemporaryDirectory(prefix='symblic-js-') as scratch:
        runner = os.path.join(scratch, 'runner.js')
        sandbox = os.path.join(scratch, 'sandbox.py')
        limiter = os.path.join(scratch, 'limits.py')
        for path, data in ((runner, assets['runner']), (sandbox, assets['sandbox']), (limiter, assets['limiter']),
                           (os.path.join(scratch, 'acorn.js'), assets['parser']),
                           (os.path.join(scratch, 'acorn-LICENSE.txt'), assets['license'])):
            with open(path, 'wb') as stream:
                stream.write(data)
        node_root = os.path.dirname(os.path.dirname(os.path.realpath(node)))
        argv = ['/usr/bin/python3', '-I', sandbox, '--require', '--no-unix', '--net-connect', '1',
                '--rx', node_root, '--cwd', scratch, '--',
                os.path.realpath(node), f'--max-old-space-size={HEAP_MB}', '--disallow-code-generation-from-strings',
                runner]
        pieces = list(source) if isinstance(source, (list, tuple)) else [source]
        body = json.dumps({'pieces': pieces, 'cases': [{'call': c} for c in calls], 'timeout_ms': case_ms}).encode()
        # A reflective case may need both protected and ordinary artifact realms.
        # Both keep their own case timeout; the caller/context deadline remains final.
        wall = 15 + len(calls) * (2 * case_ms / 1000 + 1)
        limited_by_deadline = deadline is not None and deadline - time.monotonic() < wall
        if limited_by_deadline:
            wall = max(0.001, deadline - time.monotonic())
        end = min(time.monotonic() + wall, deadline) if deadline is not None else time.monotonic() + wall
        argv = ['/usr/bin/python3', '-I', limiter, 'js', str(min(816, max(1, math.ceil(wall)))),
                str(os.getpid()), '--'] + argv
        env = {'PATH': '/usr/bin:/bin', 'HOME': scratch, 'LANG': 'C.UTF-8', 'TMPDIR': scratch}
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=scratch, env=env, start_new_session=True)
        except OSError as exc:
            raise JsError('the bounded JavaScript child could not start: ' + type(exc).__name__,
                          kind='unavailable') from None
        try:
            out, err = _communicate_bounded(proc, body, deadline=end,
                                            max_output_bytes=max_output_bytes)
        except subprocess.TimeoutExpired:
            if limited_by_deadline:
                raise JsError('the aggregate JavaScript recheck time budget is exhausted', kind='budget') from None
            return [{'ok': False, 'kind': 'timeout', 'error': f'the whole check ran past {int(wall)} s', 'line': None}
                    for _ in calls]
    err = err.decode('utf-8', 'replace')
    if proc.returncode == 125:
        raise JsError('the JavaScript sandbox refused to start: ' + (err or '').strip()[-300:], kind='unavailable')
    if proc.returncode != 0:
        reason = ('memory allocation failed' if any(word in err.lower() for word in ('heap', 'memory'))
                  else f'child exited {proc.returncode} without a completed result')
        return [{'ok': False, 'kind': 'resource', 'error': reason, 'line': None} for _ in calls]
    try:
        data = json.loads(out or '')
    except ValueError:
        tail = (err or '').strip()[-300:]
        if 'heap' in err.lower() or 'memory' in err.lower():
            return [{'ok': False, 'kind': 'resource', 'error': 'memory allocation failed', 'line': None}
                    for _ in calls]
        raise JsError('the JavaScript runner gave no result' + (f': {tail}' if tail else ''), kind='unavailable') from None
    if (not isinstance(data, dict) or data.get('fatal') or not isinstance(data.get('results'), list)
            or len(data['results']) != len(calls) or any(not isinstance(row, dict) for row in data['results'])):
        raise JsError('the JavaScript runner returned an incomplete result', kind='unavailable')
    return data['results']


# ----------------------------------------------------------------------------------------------- comparing values

def _parse(text: str):
    return json.loads(text, parse_float=decimal.Decimal)


def same(a, b) -> bool:
    """JSON equality: objects by key, lists in order, numbers by value, booleans never equal to numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, decimal.Decimal)) and isinstance(b, (int, decimal.Decimal)):
        return decimal.Decimal(a) == decimal.Decimal(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def _safe(text: str) -> str:
    """A text without lone surrogates (JavaScript strings may hold them; a fingerprint cannot encode them)."""
    return str(text).encode('utf-8', 'replace').decode('utf-8')


def _short(text: str, limit: int = 400) -> str:
    text = _safe(text)
    return text if len(text) <= limit else text[:limit - 60] + ' … ' + text[-50:]


def _text(value, what: str, node) -> str:
    if not isinstance(value, str):
        raise JsError(f'{what} must be text', node.line if node else 0, node.col if node else 0, kind='type')
    return value


def _cases(cases, node) -> list[tuple[str, str]]:
    if not isinstance(cases, (tuple, list)):
        raise JsError('js_test cases must be a list of [call, expected] pairs', node.line if node else 0,
                      node.col if node else 0, kind='type')
    out = []
    for i, case in enumerate(cases, 1):
        if isinstance(case, dict):
            case = (case.get('call'), case.get('expect'))
        if not isinstance(case, (tuple, list)) or len(case) != 2 or not all(isinstance(x, str) for x in case):
            raise JsError(f'js_test case {i} must be a pair of texts [call, expected JSON]', node.line if node else 0,
                          node.col if node else 0, kind='type')
        call, expected = case
        if not call.strip() or len(call) > MAX_CALL or len(expected) > MAX_EXPECTED:
            raise JsError(f'js_test case {i} is empty or too long', node.line if node else 0, node.col if node else 0,
                          kind='limit')
        try:
            _parse(expected)
        except ValueError:
            raise JsError(f'js_test case {i}: the expected value is not JSON: {_short(expected, 120)}',
                          node.line if node else 0, node.col if node else 0, kind='type') from None
        out.append((call, expected))
    if not out or len(out) > MAX_CASES:
        raise JsError(f'js_test needs 1 to {MAX_CASES} cases', node.line if node else 0, node.col if node else 0,
                      kind='limit')
    return out


def _charge(kernel, n: int, node) -> None:
    budget = getattr(kernel, 'budget', None)
    if isinstance(budget, S.Budget):
        budget.tick(n, node)


def _where(source, r: dict) -> str:
    """Where an error happened, as the text of that line. The tested source is usually several pieces (test helpers,
    earlier units, the answer), so a line number means nothing to the model that wrote one of them; the line's own
    text does (2026-10-04: "line 228 of the code" sent 4B models looking in their 20-line answer)."""
    pieces = list(source) if isinstance(source, (list, tuple)) else [source]
    line, piece = r.get('line'), r.get('piece')
    if not isinstance(piece, int) or not 1 <= piece <= len(pieces):
        piece = len(pieces)
    if not isinstance(line, int) or line < 1:
        return ''
    lines = str(pieces[piece - 1]).split('\n')
    text = lines[line - 1].strip() if line <= len(lines) else ''
    if not text:
        return f' (line {line})'
    return f' (in this line{"" if piece == len(pieces) else " of the code run before it"}: {_short(text, 200)})'


def failures(source, cases: list[tuple[str, str]], *, deadline=None) -> tuple[list[tuple[str, str, str]], list[dict]]:
    """Run `cases` against `source`: the failing (call, expected, what happened) triples, in case order, and the raw
    results."""
    calls = [c for c, _ in cases]
    results = evaluate(source, calls, **({'deadline': deadline} if deadline is not None else {}))
    results = _reobserve(source, calls, results, deadline=deadline)
    _require_complete(results)
    failed = []
    for (call, expected), r in zip(cases, results):
        if r.get('ok'):
            try:
                got = _parse(r['value'])
            except ValueError:
                failed.append((call, expected, 'error: the result is not JSON'))
                continue
            if not same(got, _parse(expected)):
                failed.append((call, expected, 'got      ' + _short(r['value'])))
        else:
            where = _where(source, r)
            failed.append((call, expected, f'{r.get("kind", "error")}: {_short(r.get("error", ""), 300)}{where}'))
    return failed, results


def host_load() -> float | None:
    """The host's 1-minute load average per CPU; None when it cannot be read."""
    try:
        with open('/proc/loadavg', encoding='ascii') as stream:
            load1 = float(stream.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return load1 / max(1, os.cpu_count() or 1)


def host_io() -> float | None:
    """The host's I/O pressure: PSI `some avg10` in percent (/proc/pressure/io); None when it cannot be read. A disk at
    80 % pressure (nightly indexers, a sync, a model load) stalls the sandbox's start longer than a case may run."""
    try:
        with open('/proc/pressure/io', encoding='ascii') as stream:
            for line in stream:
                fields = line.split()
                if fields and fields[0] == 'some':
                    for field in fields[1:]:
                        if field.startswith('avg10='):
                            return float(field[6:])
    except (OSError, ValueError):
        return None
    return None


def _calm(deadline=None, *, wait_s=None, sleep=time.sleep, load=None, io=None, clock=time.monotonic) -> bool:
    """Wait, bounded by `wait_s` (CALM_WAIT_S) and the deadline, until the host is calm (CPU load per CPU at or under
    CALM_LOAD and I/O pressure at or under CALM_IO): True when it is. An unreadable reading never waits."""
    wait_s = CALM_WAIT_S if wait_s is None else wait_s
    load = host_load if load is None else load
    io = host_io if io is None else io
    end = clock() + max(0.0, float(wait_s))
    if deadline is not None:
        end = min(end, deadline)
    while True:
        cpu, disk = load(), io()
        if cpu is None and disk is None:
            return False
        if (cpu is None or cpu <= CALM_LOAD) and (disk is None or disk <= CALM_IO):
            return True
        now = clock()
        if now >= end:
            return False
        sleep(min(2.0, max(0.0, end - now)))


def _reobserve(source, calls: list[str], results: list[dict], *, deadline=None, rounds=None) -> list[dict]:
    """Timed-out observations run again, up to REOBSERVE rounds, each after a bounded wait for a calm host. The
    re-run rows carry `reobserved: round`; a case that still times out stays inconclusive. Nothing else changes."""
    rounds = REOBSERVE if rounds is None else rounds
    results = list(results)
    for round_no in range(1, max(0, int(rounds)) + 1):
        again = [i for i, r in enumerate(results) if not r.get('ok') and r.get('kind') == 'timeout']
        if not again or (deadline is not None and time.monotonic() >= deadline):
            break
        _calm(deadline)
        fresh = evaluate(source, [calls[i] for i in again], **({'deadline': deadline} if deadline is not None else {}))
        for i, row in zip(again, fresh):
            row = dict(row)
            row['reobserved'] = round_no
            results[i] = row
    return results


def _require_complete(results):
    unresolved = [r for r in results if not r.get('ok') and r.get('kind') in INCONCLUSIVE]
    if unresolved:
        first = unresolved[0]
        again = max((int(r.get('reobserved') or 0) for r in unresolved), default=0)
        note = f' after {again} re-observation(s) on a loaded host' if again else ''
        raise JsError(f'JavaScript check inconclusive: {len(unresolved)} observation(s) could not complete '
                      f'({first.get("kind")}: {_short(first.get("error", ""), 300)}){note}. '
                      'No candidate verdict; no repair request was made.', kind='resource')


def test(source, cases: list[tuple[str, str]], *, deadline=None) -> dict:
    """The report of running `cases` against `source` (plain Python values; js_test wraps it for the kernel)."""
    deadline = _effective_deadline(deadline)
    failed, results = failures(source, cases, **({'deadline': deadline} if deadline is not None else {}))
    lines = []
    unit_broken = [r for r in results if not r.get('ok') and r.get('kind') in ('syntax', 'redefine')]
    if unit_broken and len(unit_broken) == len(results):
        r = unit_broken[0]
        lines.append(f'The code does not run: {_short(r.get("error", ""), 300).rstrip(".")}{_where(source, r)}.')
    elif failed:
        lines.append(f'{len(failed)} of {len(cases)} examples failed:')
        for call, expected, got in failed[:REPORT_FAILURES]:
            lines.append(f'- {_short(call, 300)}\n  expected {_short(expected)}\n  {got}')
        if len(failed) > REPORT_FAILURES:
            lines.append(f'(and {len(failed) - REPORT_FAILURES} more)')
    else:
        lines.append(f'All {len(cases)} examples passed.')
    out = {'passed': not failed, 'total': len(cases), 'failed': len(failed), 'report': '\n'.join(lines)}
    again = sum(1 for r in results if r.get('reobserved'))
    if again:
        out['reobserved'] = again
    return out


def _pieces(value, what: str, node) -> list[str]:
    """A source: one text, or a list of texts run as separate scripts."""
    if isinstance(value, (tuple, list)):
        if not value or len(value) > MAX_PIECES or not all(isinstance(p, str) for p in value):
            raise JsError(f'{what} must be a text or a list of 1 to {MAX_PIECES} texts', node.line if node else 0,
                          node.col if node else 0, kind='type')
        pieces = list(value)
    else:
        pieces = [_text(value, what, node)]
    if sum(len(p) for p in pieces) > MAX_SOURCE:
        raise JsError(f'{what} is longer than {MAX_SOURCE} characters', node.line if node else 0,
                      node.col if node else 0, kind='limit')
    return pieces


def _js_test(kernel, node, source, cases, *, deadline=None):
    deadline = _effective_deadline(deadline)
    source = _pieces(source, 'js_test source', node)
    pairs = _cases(cases, node)
    # the JavaScript runs out of process under its own time and memory limits; the kernel's step budget is charged
    # only for handling the cases (a build with hundreds of retried checks must not exhaust a run's 200 000 steps)
    _charge(kernel, STEPS_PER_CASE * len(pairs), node)
    return test(source, pairs, **({'deadline': deadline} if deadline is not None else {}))


def _js_run(kernel, node, source, call):
    source, call = _pieces(source, 'js_run source', node), _text(call, 'js_run call', node)
    if len(call) > MAX_CALL:
        raise JsError('js_run call is too long', node.line if node else 0, node.col if node else 0, kind='limit')
    _charge(kernel, STEPS_PER_CASE, node)
    deadline = _effective_deadline()
    r = evaluate(source, [call], **({'deadline': deadline} if deadline is not None else {}))[0]
    _require_complete([r])
    if not r.get('ok'):
        raise JsError(f'js_run: {r.get("kind")}: {_short(r.get("error", ""), 300)}', node.line if node else 0,
                      node.col if node else 0, kind='js')
    return S.from_json(json.loads(_safe(r['value'])))


FUNCTIONS = {'js_test': _js_test, 'js_run': _js_run}

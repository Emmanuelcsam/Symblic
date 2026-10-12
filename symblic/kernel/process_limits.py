"""Resource limits for child processes: the bounded CLI, kernel-only tests, previews and the JavaScript sandbox.

Some Symblic work runs untrusted or unbounded input (a program's tests, a model-written JavaScript unit). It
runs in a child process that sets its own limits before doing anything else: an address-space ceiling
(ADDRESS_SPACE_BYTES), a CPU-time limit per kind of work (CPU_SECONDS) and a wall-clock bound enforced by the
parent (WALL_SECONDS). The child also asks the kernel to kill it if its parent dies.

    call_bounded('tests', {'source': ...})   # parent side: run a program's kernel-only tests in a child
    python3 -I process_limits.py js CPU PARENT_PID -- node ...   # child side, as symblic.js.check starts node
    python3 -I process_limits.py cli --file SCRIPT ARG...        # a command-line tool under the same limits

Importing this module never changes limits or starts work. Address space is an allocation ceiling, not a
measured RSS or cgroup cap. The `preview` action runs symblic.kernel.preview.run_preview (the first ask's
capsule, no model).

Depends on: the standard library; symblic.kernel.language and symblic.lang.abstraction inside the child;
symblic.js.check for the bounded pipe pump. The file is also copied, unchanged and self-contained, into the
JavaScript sandbox's scratch directory, and its bytes are part of the kernel identity through the
JavaScript adapter's asset hash.
"""
from __future__ import annotations

# The same file is also copied as a self-contained, frozen JS launcher asset.
if __name__ != '__main__':
    _symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
    _symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import os
import runpy
import signal
import subprocess
import sys
import time
from pathlib import Path

VERSION = 1
ADDRESS_SPACE_BYTES = 2 * 1024 * 1024 * 1024
CPU_SECONDS = {'cli': 120, 'preview': 10, 'tests': 30}
WALL_SECONDS = {'preview': 30, 'tests': 60}
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024


class BoundaryUnavailable(Exception):
    pass


def _parent_death(expected):
    """A killed request worker must not leave its separately sandboxed JS child."""
    try:
        import ctypes
        if not sys.platform.startswith('linux'):
            raise BoundaryUnavailable('parent-death cleanup is unavailable on this platform')
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG, before sandbox/exec
            raise OSError(ctypes.get_errno(), 'prctl')
        if os.getppid() != expected:
            raise BoundaryUnavailable('the owning process exited before child startup')
    except (ImportError, OSError) as exc:
        raise BoundaryUnavailable('parent-death cleanup could not be installed') from exc


def _apply_limits(profile, *, cpu_seconds=None):
    """Only the standalone child may call this; never a thread of a long-running parent (a web server)."""
    if __name__ != '__main__':
        raise BoundaryUnavailable('resource limits may only be set by the child entrypoint')
    try:
        import resource
        cpu = CPU_SECONDS[profile] if profile != 'js' else cpu_seconds
        if type(cpu) is not int or not 1 <= cpu <= 816:
            raise BoundaryUnavailable('invalid child CPU budget')
        for kind, soft, hard in ((resource.RLIMIT_AS, ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES),
                                 (resource.RLIMIT_CPU, cpu, cpu + 2)):
            old_soft, old_hard = resource.getrlimit(kind)
            # Never raise a pre-existing constraint inherited from a worker/unit.
            if old_hard != resource.RLIM_INFINITY:
                hard = min(hard, old_hard)
            if old_soft != resource.RLIM_INFINITY:
                soft = min(soft, old_soft)
            resource.setrlimit(kind, (min(soft, hard), hard))
    except (ImportError, OSError, ValueError) as exc:
        raise BoundaryUnavailable('child CPU/address-space limits are unavailable: ' + type(exc).__name__) from exc


def _resource_error(message, *, kind='resource'):
    return {'kind': kind, 'message': message, 'line': 0, 'col': 0}


def _inconclusive(action, message, *, kind='resource'):
    error = _resource_error('Check inconclusive: ' + message, kind=kind)
    if action == 'tests':
        return {'ok': False, 'status': 'failed', 'passed': 0, 'failed': 0, 'inconclusive': 0,
                'tests': [], 'error': error, 'asks': 0, 'calls': 0, 'cached': 0, 'incomplete': True}
    return {'status': 'failed', 'error': error, 'bindings': [], 'outputs': [], 'warnings': [],
            'facts': [], 'fingerprint': None}


def call_bounded(action, body):
    """Run an inert preview/kernel test request in an owned, finite subprocess."""
    if action not in WALL_SECONDS:
        raise ValueError('unsupported Symblic child action')
    payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(payload) > MAX_REQUEST_BYTES:
        return _inconclusive(action, 'the child request exceeds its byte budget')
    # Reuse the already bounded pump; it kills/reaps only this new process group
    # on timeout, output overflow or interruption, never a caller-owned process.
    from symblic.js import check as JS
    argv = [sys.executable, '-I', str(Path(__file__).resolve()), action, str(os.getpid())]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except OSError:
        return _inconclusive(action, 'the bounded child could not start', kind='unavailable')
    try:
        out, _err = JS._communicate_bounded(proc, payload, deadline=time.monotonic() + WALL_SECONDS[action],
                                           max_output_bytes=MAX_OUTPUT_BYTES, max_error_bytes=MAX_ERROR_BYTES)
    except subprocess.TimeoutExpired:
        return _inconclusive(action, 'the child exceeded its wall-time budget')
    except JS.JsError:
        return _inconclusive(action, 'the child exceeded its output byte budget')
    if proc.returncode != 0:
        return _inconclusive(action, 'the child stopped without a completed result '
                             f'(exit {proc.returncode}; resource exhaustion or interruption)')
    try:
        result = json.loads(out)
        if not isinstance(result, dict) or 'status' not in result:
            raise ValueError('missing result')
        return result
    except (ValueError, UnicodeError):
        return _inconclusive(action, 'the child did not return a complete result', kind='unavailable')


def _cancel_loaded_applicators():
    # No provider imports/launches for a deterministic job. A CLI that already
    # admitted calls releases its own in-flight jobs on exit/resource failure.
    loaded = sys.modules.get('symblic.providers.applicators')
    if loaded is not None:
        try:
            loaded.cancel_everything()
        except Exception as exc:  # noqa: BLE001 - preserve the original visible outcome on cleanup failure
            print('Symblic admitted-call cleanup incomplete: ' + type(exc).__name__, file=sys.stderr)


def _cpu_exhausted(_signum, _frame):
    from symblic.kernel import language as S
    raise S.SymblicError('Check inconclusive: child CPU budget exhausted; no candidate verdict.', kind='resource')


def _cli(argv):
    if not argv or argv[0] not in ('--file', '--module', '--stdin-script'):
        raise BoundaryUnavailable('CLI boundary needs --file, --module or --stdin-script')
    mode, rest = argv[0], argv[1:]
    if mode == '--stdin-script':
        source = sys.stdin.read(MAX_REQUEST_BYTES + 1)
        if len(source.encode('utf-8')) > MAX_REQUEST_BYTES:
            raise BoundaryUnavailable('CLI entrypoint exceeds its byte budget')
        sys.argv = ['-'] + rest
        # This is the fixed first-party tools/symblic entrypoint, never model/user Symblic source.
        exec(compile(source, '<symblic-cli>', 'exec'), {'__name__': '__main__', '__file__': '<symblic-cli>'})  # noqa: S102
    else:
        if not rest:
            raise BoundaryUnavailable('CLI entrypoint is missing')
        target, args = rest[0], rest[1:]
        sys.argv = [target] + args
        if mode == '--file':
            runpy.run_path(target, run_name='__main__')
        else:
            runpy.run_module(target, run_name='__main__', alter_sys=True)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    action = argv.pop(0) if argv else ''
    if action == 'js':
        try:
            cpu = int(argv.pop(0))
            parent = int(argv.pop(0))
            _parent_death(parent)
            if not argv or argv.pop(0) != '--' or not argv:
                raise BoundaryUnavailable('missing JavaScript child command')
            _apply_limits('js', cpu_seconds=cpu)
            os.execv(argv[0], argv)
        except (BoundaryUnavailable, ValueError, IndexError, OSError) as exc:
            print('Symblic child unavailable: ' + str(exc), file=sys.stderr)
            return 125
    if action not in ('cli', 'preview', 'tests'):
        print('unknown Symblic child action', file=sys.stderr)
        return 2
    try:
        if action != 'cli':
            _parent_death(int(argv.pop(0)))
        _apply_limits(action)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # the directory that holds the symblic package
        from symblic.kernel import language as S
        signal.signal(signal.SIGXCPU, _cpu_exhausted)
        signal.signal(signal.SIGTERM, lambda signum, _frame: sys.exit(128 + signum))
        if action == 'cli':
            return _cli(argv)
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise BoundaryUnavailable('child request exceeds its byte budget')
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise BoundaryUnavailable('child request must be an object')
        if action == 'preview':
            from symblic.kernel import preview as PV
            result = PV.run_preview(body)
        else:
            from symblic.lang import abstraction as L
            result = L.run_tests(body['source'], None, by='fake:none')
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except BoundaryUnavailable as exc:
        result = _inconclusive(action, str(exc), kind='unavailable')
    except MemoryError:
        result = _inconclusive(action, 'the child address-space budget was exhausted')
    except Exception as exc:  # noqa: BLE001 - child protocol returns a visible unavailable result
        # Resource and language errors retain their classifications; an adapter
        # protocol failure cannot certify or reject a candidate.
        if 'S' in locals() and isinstance(exc, S.SymblicError):
            result = _inconclusive(action, exc.message, kind=exc.kind)
            if exc.kind not in ('resource', 'unavailable', 'budget'):
                result['error'] = exc.as_dict()
        else:
            detail = type(exc).__name__
            if action == 'cli' and str(exc):
                detail += ': ' + str(exc)[:500]      # names the missing file or bad argument for the person at the terminal
            result = _inconclusive(action, 'the child could not complete: ' + detail, kind='unavailable')
    finally:
        _cancel_loaded_applicators()
    if action == 'cli':
        if '--json' in argv or '--agent-json' in argv:
            print(json.dumps(result))
        else:
            print(result['error']['message'], file=sys.stderr)
        return 75
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())

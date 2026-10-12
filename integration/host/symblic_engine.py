"""HOST-ONLY: the host web server's `symblic/` HTTP routes; needs the host's request handler, owner gate and store.

What it did in the original host: the routes check, preview, run, compare and keep Symblic programs for the
operator. The host's automation route table (`automation_engine`, a host module) handed every `symblic/...`
route here, so every route sat behind the host's owner check. A run is a folder under the host's data
directory, `<data>/symblic/runs/<id>/` (program.sym, meta.json, then the runner's state.json, trace.jsonl,
calls.jsonl, log.txt and artifacts/), executed by `python -m symblic.kernel.run --dir FOLDER` in its own
transient systemd user unit `symblic-<id>`: it survives a restart of the web server, an out-of-memory kill
takes only that unit, and stop/resume are `systemctl --user stop` + `--resume` (a resumed run replays every
answer it already has from calls.jsonl). A comparison ("determinism matrix") starts the same program once per
applicator and lines the statements up by fingerprint.

    GET  symblic/meta                 language facts, applicators and their state, examples
    POST symblic/check   {source}     diagnostics, plan, determinism profile (no model, nothing saved)
    POST symblic/preview {source, inputs, by}
                                      the kernel runs until the first ask and shows exactly what that ask
                                      would send (the capsule); nothing reaches a model
    POST symblic/run     {source, inputs, by, title, options}            -> {id}
    GET  symblic/runs | symblic/run?id= | symblic/artifact?id=&name=
    POST symblic/stop|resume|delete {id}
    POST symblic/compare {source, inputs, applicators: [...], title}    -> {id, runs}
    GET  symblic/compares | symblic/compare?id=
    GET  symblic/programs   POST symblic/programs/save {name, source} | symblic/programs/delete {name}
    library, module, tests, paper/*, lock, lock/replay, lang/*: symblic_lang_api.py (functions, routines,
    modules, tests, .symd papers and their reproduction, lockfiles, certify and crystallise jobs;
    docs/reference/LANGUAGE-3.md)

What works without the host: importing this module. The preview (`preview()`, `_preview_local`) and the request
checks (`_clean_source`, `_clean_inputs`, `_clean_by`, SymblicApiError) now live in symblic/kernel/preview.py
and are re-exported here for the host's routes; `tools/symblic preview` uses the kernel module. Every
route that saves or reads a run needs the host's store module (`host_apps`: save_json, load_json,
store_lock, data_dir) and the HTTP handler object the host passes to `handle_get`/`handle_post`.

Depends on: the `symblic` package; at call time the host modules `host_apps` (store) and, for runs,
`systemd-run`/`systemctl --user`.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

from symblic.kernel import language as S

# The repository root (this file is integration/host/symblic_engine.py).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ID_RX = re.compile(r'^[0-9a-f]{12}$')
NAME_RX = re.compile(r'^[\w .,()+-]{1,80}$')
MAX_RUNS_LISTED = 200
MAX_COMPARE = 12
MAX_PROGRAMS = 300
UNIT_MEMORY = '600M'           # the runner only orchestrates: models and agents run on other nodes
UNIT_CPU = '50%'
EXAMPLES_DIR = os.path.join(REPO_ROOT, 'examples')


# Request errors are shared with the kernel preview (symblic/kernel/preview.py), so a bad request raises the same
# class whether it reaches a host route or the preview.
from symblic.kernel.preview import RequestError as SymblicApiError  # noqa: E402


def _host_apps():
    """The host's store module: save_json, load_json, store_lock and data_dir (atomic JSON files under
    the host's data directory). It is not part of this repository; only the routes that save or read
    runs import it, so importing this module and preview() work without the host."""
    import host_apps
    return host_apps


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def root() -> str:
    path = os.path.join(_host_apps().data_dir('automation_data', 'AUTOMATION_DATA_DIR'), 'symblic')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def runs_dir() -> str:
    path = os.path.join(root(), 'runs')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def compares_dir() -> str:
    path = os.path.join(root(), 'compare')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def programs_path() -> str:
    return os.path.join(root(), 'programs.json')


def run_dir(run_id: str) -> str:
    if not ID_RX.match(str(run_id or '')):
        raise SymblicApiError('No such run.')
    path = os.path.join(runs_dir(), run_id)
    if not os.path.isdir(path):
        raise SymblicApiError('No such run.')
    return path


# ---------------------------------------------------------------------------
# Launching (a transient user unit per run; tests replace `launcher`)
# ---------------------------------------------------------------------------

def unit_name(run_id: str) -> str:
    return f'symblic-{run_id}'


def _python() -> str:
    venv = os.path.join(REPO_ROOT, '.venv', 'bin', 'python')
    return venv if os.access(venv, os.X_OK) else sys.executable


def _systemd_launch(run_id: str, folder: str, resume: bool) -> dict:
    tail = ['-m', 'symblic.kernel.run', '--dir', folder] + (['--resume'] if resume else [])
    return _launch_unit(unit_name(run_id), tail)


def _launch_tighten(job_id: str, folder: str) -> dict:
    return _launch_unit(f'symblic-tighten-{job_id}', ['-m', 'symblic.authoring.tighten', 'job', '--dir', folder])


def _launch_unit(unit: str, tail: list) -> dict:
    exe = shutil.which('systemd-run') or '/usr/bin/systemd-run'
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LANG', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS')
           if os.environ.get(k)}
    env.setdefault('HOME', os.path.expanduser('~'))
    env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    env['PATH'] = os.pathsep.join([os.path.join(env['HOME'], '.local', 'bin'), '/usr/local/bin', '/usr/bin', '/bin'])
    argv = [exe, '--user', '--collect', '--quiet', f'--unit={unit}', '--slice=symblic-work.slice',
            f'--property=MemoryMax={UNIT_MEMORY}', f'--property=CPUQuota={UNIT_CPU}', '--nice=10',
            '--property=IOSchedulingClass=idle',
            f'--working-directory={REPO_ROOT}']
    argv += [f'--setenv={k}={v}' for k, v in sorted(env.items())]
    argv += ['--', _python()] + list(tail)
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=30,
                             env={k: v for k, v in env.items()})
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'ok': False, 'error': f'could not start the run: {e}'}
    if res.returncode != 0:
        return {'ok': False, 'error': (res.stderr or res.stdout or 'systemd-run failed').strip()[:400]}
    return {'ok': True}


def _systemd_active(run_id: str, unit: str = '') -> bool:
    try:
        res = subprocess.run(['systemctl', '--user', 'is-active', (unit or unit_name(run_id)) + '.service'],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.stdout.strip() in ('active', 'activating', 'deactivating', 'reloading')


def _systemd_stop(run_id: str, unit: str = '') -> bool:
    try:
        res = subprocess.run(['systemctl', '--user', 'stop', (unit or unit_name(run_id)) + '.service'],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


launcher = {'launch': _systemd_launch, 'active': _systemd_active, 'stop': _systemd_stop, 'tighten': _launch_tighten}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

# Request checks shared with the kernel preview (symblic/kernel/preview.py).
from symblic.kernel.preview import clean_by as _clean_by  # noqa: E402
from symblic.kernel.preview import clean_inputs as _clean_inputs  # noqa: E402
from symblic.kernel.preview import clean_source as _clean_source  # noqa: E402


def start_run(body: dict, compare: str = '', *, delegation=None, authoring=None, run_id=None, forge_handoff=None) -> dict:
    source = _clean_source(body.get('source'))
    if authoring is not None:
        from integration.host.symblic_english_api import checked_authoring
        if not checked_authoring(authoring, source):
            raise SymblicApiError('English source and compiled program do not match.')
    raw_opts = body.get('options') if isinstance(body.get('options'), dict) else {}
    constructor = None
    if any(type(key) is str and (key == 'constructor' or key.startswith('constructor_')) for key in raw_opts):
        try:
            from symblic.kernel.run import validate_constructor_options
        except ImportError:
            raise SymblicApiError('Constructor policy needs the server update and restart; no run was started.') from None
        try:
            constructor = validate_constructor_options(raw_opts)
        except S.SymblicError as error:
            raise SymblicApiError(error.message) from None
    checked = S.check(source, execution_profile=raw_opts.get('profile'))
    if not checked['ok']:
        e = checked['errors'][0]
        raise SymblicApiError(f'line {e.get("line", 0)}: {e["message"]}')
    inputs = _clean_inputs(body.get('inputs'))
    by = _clean_by(body.get('by'))
    options = {'profile': checked.get('execution_profile', 'legacy')}
    if 'ollama_limits' in raw_opts:
        try:
            from symblic.kernel.run import validate_ollama_limits
            options['ollama_limits'] = validate_ollama_limits(raw_opts['ollama_limits'])
        except ImportError:
            raise SymblicApiError('Ollama request limits need the server update and restart.') from None
        except S.SymblicError as error:
            raise SymblicApiError(error.message) from None
    if 'determine' in raw_opts:
        if type(raw_opts['determine']) is not bool:
            raise SymblicApiError('determine must be true or false.')
        options['determine'] = raw_opts['determine']
    if constructor is not None:
        options.update(constructor=constructor['mode'], constructor_limits=constructor['limits'])
        if constructor['mode'] != 'off':
            options['solve'] = False
    if 'model_pins' in raw_opts:
        if type(raw_opts['model_pins']) is not str or raw_opts['model_pins'] != 'strict':
            raise SymblicApiError('model_pins must be strict when supplied; omit it for recorded observations.')
        if not strict_model_pins_available():
            raise SymblicApiError('Strict model identity enforcement needs the server update; no run was started.')
        options['model_pins'] = 'strict'
    if 'module_logic' in raw_opts:
        logic = raw_opts['module_logic']
        if (type(logic) is not dict or len(logic) > 256 or
                any(type(key) is not str or not re.fullmatch(r'(?:lib|saved):[^\x00-\x1f]{1,200}', key)
                    or mode not in ('shared', 'isolated') for key, mode in logic.items())):
            raise SymblicApiError('module_logic must map exact module keys to shared or isolated.')
        options['module_logic'] = dict(logic)
    if by is not None:
        options['by'] = by
    for key, lo, hi in (('max_asks', 1, 2000), ('max_calls', 0, 10000), ('parallel', 1, 8),
                       ('max_steps', 1000, 1000000)):
        if raw_opts.get(key) not in (None, ''):
            try:
                options[key] = max(lo, min(hi, int(raw_opts[key])))
            except (TypeError, ValueError):
                raise SymblicApiError(f'{key} must be a number.') from None
    if raw_opts.get('side_effects'):
        options['side_effects'] = True
    if 'progress_outputs' in raw_opts:
        if type(raw_opts['progress_outputs']) is not bool:
            raise SymblicApiError('progress_outputs must be true or false.')
        options['progress_outputs'] = raw_opts['progress_outputs']
    if raw_opts.get('execution_pins') is not None:
        from symblic.kernel import execution_pins as X
        try:
            options['execution_pins'] = X.validate(raw_opts['execution_pins'], source, inputs)
        except S.SymblicError as error:
            raise SymblicApiError(error.message) from None
    if delegation is not None:
        if type(delegation) is dict and 'routing' in delegation:
            _delegation_contract(delegation, source, inputs, raw_opts)
            from symblic.delegate import contracts as D
            from symblic.delegate import run as R
            options = D._copy(raw_opts)
            by = R.requested_by(delegation['routing'])
        else:
            _delegation_contract(delegation, source, inputs, options)
    if raw_opts.get('certificate') is not None:
        if not isinstance(raw_opts['certificate'], dict):
            raise SymblicApiError('certificate must be a version-pinned certificate object.')
        options['certificate'] = raw_opts['certificate']
    if run_id is not None and (forge_handoff is None or not ID_RX.fullmatch(str(run_id))):
        raise SymblicApiError('A reserved run identity requires its Forge handoff.')
    run_id = run_id or secrets.token_hex(6)
    folder = os.path.join(runs_dir(), run_id)
    os.makedirs(folder, mode=0o700)
    title = str(body.get('title') or checked.get('name') or 'Symblic program')[:120]
    meta = {'id': run_id, 'title': title, 'created': time.time(), 'inputs': inputs, 'options': options,
            'by': by, 'compare': compare, 'asks': checked.get('asks', 0), 'profile': checked.get('profile', {}),
            'by_label': f'operator (Symblic run {run_id})', 'version': S.VERSION}
    if forge_handoff is not None:
        from integration.host import symblic_forge_bridge as symblic_forge_bridge
        meta['forge_handoff'] = forge_handoff
        symblic_forge_bridge.validate_saved(source, meta)
    if delegation is not None:
        meta['delegation'] = delegation
    if authoring is not None:
        meta['authoring'] = authoring
        with open(os.path.join(folder, 'instructions.english'), 'w', encoding='utf-8') as f:
            f.write(authoring['document'])
        os.chmod(os.path.join(folder, 'instructions.english'), 0o600)
    with open(os.path.join(folder, 'program.sym'), 'w', encoding='utf-8') as f:
        f.write(source)
    os.chmod(os.path.join(folder, 'program.sym'), 0o600)
    _host_apps().save_json(os.path.join(folder, 'meta.json'), meta)
    os.chmod(os.path.join(folder, 'meta.json'), 0o600)
    if forge_handoff is not None:
        _host_apps().save_json(os.path.join(folder, 'forge-origin.json'), forge_handoff)
        os.chmod(os.path.join(folder, 'forge-origin.json'), 0o600)
        symblic_forge_bridge.sync_native(folder)
    started = launcher['launch'](run_id, folder, False)
    if not started.get('ok'):
        _host_apps().save_json(os.path.join(folder, 'state.json'), {'status': 'failed', 'error': {
            'message': started.get('error') or 'did not start', 'line': 0, 'col': 0, 'kind': 'launch'}})
        raise SymblicApiError(started.get('error') or 'The run did not start.')
    return {'id': run_id, 'title': title}


def _state(folder: str) -> dict:
    st = _host_apps().load_json(os.path.join(folder, 'state.json'), {})
    return st if isinstance(st, dict) else {}


def _status(run_id: str, folder: str, st: dict) -> str:
    status = st.get('status') or 'starting'
    if status in ('running', 'starting', 'new') and not launcher['active'](run_id):
        age = time.time() - float(st.get('updated') or os.path.getmtime(folder))
        return 'starting' if age < 30 else 'lost'
    return status


def list_runs() -> list:
    rows = []
    folders = sorted(glob.glob(os.path.join(runs_dir(), '*')), key=os.path.getmtime, reverse=True)
    for folder in folders[:MAX_RUNS_LISTED]:
        run_id = os.path.basename(folder)
        if not ID_RX.match(run_id):
            continue
        meta = _host_apps().load_json(os.path.join(folder, 'meta.json'), {})
        st = _state(folder)
        try:                                # a spec-sheet build (symblic.spec's note), which a rebuild can keep from
            with open(os.path.join(folder, 'program.sym'), encoding='utf-8', errors='replace') as f:
                spec = 'Compiled from the spec sheet' in f.read(600)
        except OSError:
            spec = False
        rows.append({'id': run_id, 'title': meta.get('title', ''), 'created': meta.get('created'), 'spec': spec,
                     'by': meta.get('by'), 'compare': meta.get('compare') or '',
                     'status': _status(run_id, folder, st), 'fingerprint': st.get('fingerprint'),
                     'asks': st.get('asks'), 'calls': st.get('calls'), 'agreement': st.get('agreement'),
                     'progress': st.get('progress'), 'seconds': st.get('seconds')})
    return rows


def _tail(path: str, limit: int = 12000) -> str:
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode('utf-8', 'replace')
    except OSError:
        return ''


def _jsonl(path: str, limit: int = 2000) -> list:
    out = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out[-limit:]


def run_view(run_id: str) -> dict:
    folder = run_dir(run_id)
    meta = _host_apps().load_json(os.path.join(folder, 'meta.json'), {})
    st = _state(folder)
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as f:
            source = f.read()
    except OSError:
        source = ''
    arts = sorted(os.path.basename(p) for p in glob.glob(os.path.join(folder, 'artifacts', '*.svg')))
    outputs = []
    for o in st.get('outputs') or []:
        o = dict(o)
        o.pop('svg', None)                     # drawings are fetched from symblic/artifact
        outputs.append(o)
    return {'id': run_id, 'meta': meta, 'status': _status(run_id, folder, st), 'state': {**st, 'outputs': outputs},
            'trace': _jsonl(os.path.join(folder, 'trace.jsonl')), 'log': _tail(os.path.join(folder, 'log.txt')),
            'artifacts': arts, 'source': source,
            'has_paper_map': os.path.lexists(os.path.join(folder, 'paper.json'))}


def recheck_models(run_id: str) -> dict:
    """Explicit, bounded inspection; normal run polling uses recorded evidence."""
    folder = run_dir(run_id)
    from symblic.kernel import run as SR
    inspect = getattr(SR, 'recheck_model_identities', None)
    if not callable(inspect):
        raise SymblicApiError('Model observation rechecking needs the server update and restart.')
    return {'id': run_id, 'model_identity': inspect(folder, max_rows=2000, max_bytes=4_000_000)}


def artifact(run_id: str, name: str) -> bytes:
    folder = run_dir(run_id)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,90}\.svg', str(name or '')):
        raise SymblicApiError('No such drawing.')
    path = os.path.join(folder, 'artifacts', name)
    if os.path.islink(path) or not os.path.isfile(path):
        raise SymblicApiError('No such drawing.')
    with open(path, 'rb') as f:
        return f.read(4_000_000)


def stop_run(run_id: str) -> dict:
    run_dir(run_id)
    return {'ok': launcher['stop'](run_id)}


def resume_run(run_id: str) -> dict:
    folder = run_dir(run_id)
    if launcher['active'](run_id):
        raise SymblicApiError('The run is still going.')
    from symblic.kernel import run as SR
    meta = _host_apps().load_json(os.path.join(folder, 'meta.json'), {})
    options = meta.get('options') if isinstance(meta, dict) and isinstance(meta.get('options'), dict) else {}
    if ((isinstance(meta, dict) and meta.get('forge_handoff') is not None) or
            os.path.lexists(os.path.join(folder, 'forge-origin.json'))):
        try:
            from integration.host import symblic_forge_bridge as symblic_forge_bridge
            with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as stream:
                symblic_forge_bridge.validate_saved(stream.read(S.MAX_SOURCE + 1), meta, folder=folder)
        except (OSError, ValueError) as error:
            raise SymblicApiError('Forge resume refused: ' + str(error)) from None
    if isinstance(meta, dict) and (meta.get('authoring') is not None or os.path.lexists(os.path.join(folder, 'instructions.english'))):
        try:
            from integration.host.symblic_english_api import validate_saved
            with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as stream:
                source = stream.read(S.MAX_SOURCE + 1)
            validate_saved(folder, source, meta)
        except (OSError, ImportError, S.SymblicError) as error:
            raise SymblicApiError('English resume refused: ' + str(error)) from None
    if isinstance(meta, dict) and meta.get('delegation') is not None:
        try:
            with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as stream:
                source = stream.read(S.MAX_SOURCE + 1)
        except (OSError, UnicodeError):
            raise SymblicApiError('The delegation source is missing or damaged.') from None
        _delegation_contract(meta['delegation'], source, meta.get('inputs'), options)
    try:
        constructor_policy = SR.validate_constructor_options(options)
        SR.constructor_records_gate(folder, mode=constructor_policy['mode'])
        limits = SR.validate_ollama_limits(options.get('ollama_limits'))
        if limits or os.path.lexists(os.path.join(folder, 'ollama-budget.json')):
            with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as stream:
                source_sha = __import__('hashlib').sha256(stream.read(S.MAX_SOURCE + 1).encode('utf-8')).hexdigest()
            SR._ollama_budget_read(folder, limits, source_sha)
    except S.SymblicError as error:
        raise SymblicApiError(error.message) from None
    except (OSError, UnicodeError):
        raise SymblicApiError('The Ollama budget source is missing or unreadable.') from None
    gate = SR.kernel_gate(folder, pins=options.get('execution_pins'))
    if gate['decision'] == 'refused':
        raise SymblicApiError(gate['message'])
    started = launcher['launch'](run_id, folder, True)
    if not started.get('ok'):
        raise SymblicApiError(started.get('error') or 'The run did not start.')
    return {'ok': True}


def delete_run(run_id: str) -> dict:
    folder = run_dir(run_id)
    if launcher['active'](run_id):
        raise SymblicApiError('Stop the run before deleting it.')
    shutil.rmtree(folder)
    return {'ok': True}


# ---------------------------------------------------------------------------
# Preview: the kernel up to the first ask, and that ask's exact capsule
# ---------------------------------------------------------------------------

# The preview moved to the kernel (symblic/kernel/preview.py); the host's `symblic/preview` route and its tests
# keep using these names.
from symblic.kernel.preview import _Capture, _PreviewApps, preview  # noqa: E402,F401
from symblic.kernel.preview import run_preview as _preview_local  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Compare: one program, several applicators, statements lined up by fingerprint
# ---------------------------------------------------------------------------

def start_compare(body: dict) -> dict:
    apps = body.get('applicators')
    if not isinstance(apps, list) or not (2 <= len(apps) <= MAX_COMPARE):
        raise SymblicApiError(f'Pick 2 to {MAX_COMPARE} applicators to compare.')
    specs = []
    for a in apps:
        try:
            specs.append(S.parse_applicator(a)['spec'])
        except S.SymblicError as e:
            raise SymblicApiError(e.message) from None
    if len(set(specs)) != len(specs):
        raise SymblicApiError('Each applicator once (add votes in the program to resample one).')
    cid = secrets.token_hex(6)
    runs = []
    for spec in specs:
        res = start_run({**body, 'by': spec, 'title': f'{body.get("title") or "compare"} · {spec}'}, compare=cid)
        runs.append({'id': res['id'], 'by': spec})
    _private_save(os.path.join(compares_dir(), f'{cid}.json'),
                        {'id': cid, 'title': str(body.get('title') or 'Comparison')[:120], 'created': time.time(),
                         'runs': runs})
    return {'id': cid, 'runs': runs}


def _private_save(path: str, data) -> None:
    _host_apps().save_json(path, data)
    os.chmod(path, 0o600)


def list_compares() -> list:
    out = []
    for path in sorted(glob.glob(os.path.join(compares_dir(), '*.json')), key=os.path.getmtime, reverse=True)[:100]:
        c = _host_apps().load_json(path, {})
        if c.get('id'):
            out.append({'id': c['id'], 'title': c.get('title'), 'created': c.get('created'),
                        'runs': len(c.get('runs') or [])})
    return out


def compare_view(cid: str) -> dict:
    if not ID_RX.match(str(cid or '')):
        raise SymblicApiError('No such comparison.')
    c = _host_apps().load_json(os.path.join(compares_dir(), f'{cid}.json'), None)
    if not c:
        raise SymblicApiError('No such comparison.')
    cols = []
    for r in c['runs']:
        try:
            folder = run_dir(r['id'])
        except SymblicApiError:
            cols.append({'id': r['id'], 'by': r['by'], 'status': 'deleted', 'rows': {}})
            continue
        st = _state(folder)
        rows = {}
        for t in _jsonl(os.path.join(folder, 'trace.jsonl')):
            if t.get('name') and t.get('hash') and t.get('status') in ('ok', 'contested'):
                rows[f'{t["line"]}:{t["name"]}'] = {'hash': t['hash'], 'value': t.get('value'), 'class': t.get('class'),
                                                    'agreement': (t.get('ask') or {}).get('agreement')}
        for o in st.get('outputs') or []:
            rows[f'{o["line"]}:{o["kind"]}'] = {'hash': o['hash'], 'value': o.get('text', '')[:400], 'class': 'output'}
        cols.append({'id': r['id'], 'by': r['by'], 'status': _status(r['id'], folder, st),
                     'fingerprint': st.get('fingerprint'), 'seconds': st.get('seconds'), 'rows': rows,
                     'error': (st.get('error') or {}).get('message')})
    return {'id': cid, 'title': c.get('title'), 'created': c.get('created'), 'columns': cols,
            'summary': agreement_table(cols)}


def agreement_table(cols: list) -> dict:
    """Per statement: how many applicators produced the modal fingerprint. Overall: the statements every
    applicator that answered agreed on (at least two answers), the share of agreeing applicator pairs, and
    whether whole runs are identical — only when every run finished and all fingerprints match."""
    keys = sorted({k for c in cols for k in c['rows']}, key=lambda k: (int(k.split(':')[0]), k))
    stmts = []
    unanimous = 0
    pair_ok = pair_n = 0
    for k in keys:
        hashes = [c['rows'][k]['hash'] for c in cols if k in c['rows']]
        if not hashes:
            continue
        counts = {}
        for h in hashes:
            counts[h] = counts.get(h, 0) + 1
        modal = max(counts.values())
        cls = next((c['rows'][k].get('class') for c in cols if k in c['rows']), '')
        stmts.append({'key': k, 'class': cls, 'answered': len(hashes), 'of': len(cols), 'modal': modal,
                      'distinct': len(counts), 'agreement': round(modal / len(hashes), 4)})
        if len(counts) == 1 and len(hashes) >= 2:
            unanimous += 1
        for i in range(len(hashes)):
            for j in range(i + 1, len(hashes)):
                pair_n += 1
                pair_ok += hashes[i] == hashes[j]
    done = [c for c in cols if c.get('status') == 'done']
    fps = [c.get('fingerprint') for c in done]
    same = max((fps.count(f) for f in set(fps)), default=0)
    return {'statements': stmts, 'unanimous': unanimous, 'total': len(stmts),
            'pairwise': round(pair_ok / pair_n, 4) if pair_n else None,
            'identical_runs': len(cols) > 1 and len(done) == len(cols) and len(set(fps)) == 1,
            'same_runs': same, 'runs': len(cols), 'finished': len(done)}


# ---------------------------------------------------------------------------
# Programs (saved) and examples (docs/symblic/examples/*.sym)
# ---------------------------------------------------------------------------

def examples() -> list:
    out = []
    for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, '*.sym'))):
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read(200_000)
        except OSError:
            continue
        m = re.search(r'^\s*program\s*:?\s*(.+?)\.?\s*$', text, re.M | re.I)
        blurb = re.search(r'^\s*note\s*:?\s*(.+)$', text, re.M | re.I)
        out.append({'id': os.path.splitext(os.path.basename(path))[0], 'name': m.group(1) if m else path,
                    'blurb': blurb.group(1).strip() if blurb else '', 'source': text})
    return out


def load_programs() -> list:
    data = _host_apps().load_json(programs_path(), [])
    return data if isinstance(data, list) else []


def save_program(body: dict) -> dict:
    name = str(body.get('name') or '').strip()
    if not NAME_RX.match(name):
        raise SymblicApiError('Give the program a short name (letters, numbers, spaces).')
    source = _clean_source(body.get('source'))
    path = programs_path()
    with _host_apps().store_lock(path):
        items = [p for p in load_programs() if p.get('name') != name]
        items.insert(0, {'name': name, 'source': source, 'saved': time.time()})
        _private_save(path, items[:MAX_PROGRAMS])
    return {'ok': True}


def delete_program(name: str) -> dict:
    path = programs_path()
    with _host_apps().store_lock(path):
        items = load_programs()
        keep = [p for p in items if p.get('name') != name]
        if len(keep) == len(items):
            raise SymblicApiError('No such program.')
        _private_save(path, keep)
    return {'ok': True}


KERNEL_IDENTITY = os.path.join(REPO_ROOT, 'docs', 'reference', 'kernel-identity.json')


def bench_dir() -> str:
    return os.path.join(root(), 'bench')


def evidence() -> dict:
    """The cross-machine kernel record (docs/reference/kernel-identity.json) and every benchmark folder's
    report, computed from its results.jsonl (symblic.bench.bench.report; pure)."""
    ki = _host_apps().load_json(KERNEL_IDENTITY, {}) or {}
    out = {'kernel': ki.get('rows') or [], 'kernelHow': ki.get('how', ''), 'benches': [], 'matched': []}
    try:
        from symblic.bench import bench as symblic_bench
    except Exception:  # noqa: BLE001
        return out
    try:
        from symblic.bench import matched as symblic_bench_matched
        matched = sorted(glob.glob(os.path.join(bench_dir(), '*', 'matched-plan.json')),
                         key=os.path.getmtime, reverse=True)
        for path in matched[:6]:
            report = symblic_bench_matched.load_summary(os.path.dirname(path))
            out['matched'].append({'name': os.path.basename(os.path.dirname(path)), **report})
    except ImportError:
        out['matched_unavailable'] = True
    folders = sorted(glob.glob(os.path.join(bench_dir(), '*', 'results.jsonl')), key=os.path.getmtime, reverse=True)
    for path in folders[:6]:
        rows = {}
        for row in _jsonl(path, 100_000):
            if row.get('cell'):
                rows[row['cell']] = row
        if not rows:
            continue
        name = os.path.basename(os.path.dirname(path))
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
        report = _REPORTS.get(path)
        if not report or report[0] != key:
            report = (key, symblic_bench.report(list(rows.values())))     # re-judging and bootstrap take seconds
            _REPORTS[path] = report
        out['benches'].append({'name': name, 'cells': len(rows), 'running': time.time() - st.st_mtime < 180,
                               'report': report[1]})
    return out


_REPORTS: dict = {}                # results.jsonl path -> ((path, mtime, size), report text)


def strict_model_pins_available() -> bool:
    from symblic.kernel import run as SR
    version = getattr(SR, 'MODEL_IDENTITY_VERSION', None)
    return type(version) is int and version == 1


def constructor_options_feature():
    """The API capability marker for options.constructor (read-only; GET meta). It reports that this route validates
    and forwards the exact constructor policy, not that a host solver is provisioned: nothing here loads or inventories
    solver packages. False when the runner lacks the validator, so a client never sends a policy an old route drops."""
    try:
        from symblic.kernel import run as SR
    except ImportError:
        return False
    if not callable(getattr(SR, 'validate_constructor_options', None)):
        return False
    return {'version': 1, 'modes': ['off', 'linear_diagnose', 'linear'], 'requires': {'determine': False, 'solve': False},
            'max_calls': [0, 10000]}


def meta() -> dict:
    from symblic.providers import agent_teams as teams
    try:
        from symblic.providers import applicators as symblic_apply
        engines = symblic_apply.engines_status()
    except Exception as e:  # noqa: BLE001
        engines = {'error': str(e)}
    return {'version': S.VERSION, 'engines': engines, 'titles': S.ENGINE_TITLES, 'efforts': list(S.EFFORTS),
            'features': {'strict_model_pins': strict_model_pins_available(),
                         'english_team': {'version': teams.VERSION, 'max_members': teams.MAX_MEMBERS},
                         'constructor_options': constructor_options_feature()},
            'votes': S.VOTES_FOR_EFFORT, 'builtins': S.BUILTIN_DOCS, 'askOptions': list(S.ASK_OPTIONS),
            'examples': [{k: v for k, v in e.items()} for e in examples()]}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tighten jobs: the convergence compiler on a panel of agents (symblic.authoring.tighten; on worker nodes in the original host)
# ---------------------------------------------------------------------------

TIGHTEN_PANEL = ('claude:haiku', 'codex', 'agy', 'ollama:qwen3:4b-instruct', 'ollama:llama3.2:1b')


def tighten_dir() -> str:
    path = os.path.join(root(), 'tighten')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _tighten_folder(job_id: str) -> str:
    if not ID_RX.match(str(job_id or '')):
        raise SymblicApiError('No such tightening.')
    path = os.path.join(tighten_dir(), job_id)
    if not os.path.isdir(path):
        raise SymblicApiError('No such tightening.')
    return path


def start_tighten(body: dict) -> dict:
    source = _clean_source(body.get('source'))
    checked = S.check(source)
    if not checked['ok']:
        e = checked['errors'][0]
        raise SymblicApiError(f'line {e.get("line", 0)}: {e["message"]}')
    if not checked.get('asks'):
        raise SymblicApiError('The program has no ask: there is nothing for agents to read differently.')
    raw = body.get('panel') if isinstance(body.get('panel'), list) else list(TIGHTEN_PANEL)
    panel = []
    for x in raw[:8]:
        try:
            panel.append(S.app_label(S.parse_applicator(str(x))))
        except S.SymblicError as e:
            raise SymblicApiError(f'{x}: {e.message}') from None
    if len(panel) < 2:
        raise SymblicApiError('Tightening needs at least two agents to compare.')
    clarifier = str(body.get('clarifier') or 'claude:sonnet')
    try:
        clarifier = S.app_label(S.parse_applicator(clarifier))
    except S.SymblicError as e:
        raise SymblicApiError(f'clarifier: {e.message}') from None
    try:
        rounds = max(1, min(3, int(body.get('rounds') or 2)))
    except (TypeError, ValueError):
        raise SymblicApiError('rounds must be 1, 2 or 3.') from None
    from symblic.authoring import tighten as T
    try:
        declarations = T._declarations(body.get('requirements'), body.get('fidelity_obligations'),
                                      body.get('requirement_map'), None, '')
        equivalent_policy = T._policy(body.get('equivalent_policy'), source)
        allow_changes = body.get('allow_meaning_changes', True)
        if type(allow_changes) is not bool:
            raise T.FidelityError('allow_meaning_changes must be Boolean')
    except (ValueError, TypeError) as error:
        raise SymblicApiError(str(error)) from None
    job_id = secrets.token_hex(6)
    folder = os.path.join(tighten_dir(), job_id)
    os.makedirs(folder, mode=0o700)
    title = str(body.get('title') or checked.get('name') or 'Symblic program')[:120]
    meta_ = {'id': job_id, 'title': title, 'created': time.time(), 'panel': panel, 'clarifier': clarifier,
             'rounds': rounds, 'inputs': _clean_inputs(body.get('inputs')), 'asks': checked.get('asks', 0),
             'version': S.VERSION, 'requirements': declarations[0], 'fidelity_obligations': declarations[1],
             'requirement_map': declarations[2], 'equivalent_policy': equivalent_policy,
             'allow_meaning_changes': allow_changes}
    for name, data in (('program.sym', source),):
        with open(os.path.join(folder, name), 'w', encoding='utf-8') as f:
            f.write(data)
        os.chmod(os.path.join(folder, name), 0o600)
    _private_save(os.path.join(folder, 'meta.json'), meta_)
    started = launcher['tighten'](job_id, folder)
    if not started.get('ok'):
        _private_save(os.path.join(folder, 'result.json'), {'status': 'failed', 'error': started.get('error')})
        raise SymblicApiError(started.get('error') or 'The tightening did not start.')
    return {'id': job_id, 'title': title}


def _tighten_status(job_id: str, folder: str) -> str:
    res = _host_apps().load_json(os.path.join(folder, 'result.json'), {})
    if res.get('status') in ('done', 'failed', 'stopped'):
        return res['status']
    return 'running' if launcher['active'](job_id, f'symblic-tighten-{job_id}') else 'stopped'


def list_tightens() -> list:
    out = []
    for job_id in sorted(os.listdir(tighten_dir()), reverse=True)[:100]:
        if not ID_RX.match(job_id):
            continue
        folder = os.path.join(tighten_dir(), job_id)
        m = _host_apps().load_json(os.path.join(folder, 'meta.json'), {})
        out.append({'id': job_id, 'title': m.get('title'), 'created': m.get('created'), 'panel': m.get('panel'),
                    'status': _tighten_status(job_id, folder)})
    out.sort(key=lambda r: -(r.get('created') or 0))
    return out


def tighten_view(job_id: str) -> dict:
    folder = _tighten_folder(job_id)
    m = _host_apps().load_json(os.path.join(folder, 'meta.json'), {})
    res = _host_apps().load_json(os.path.join(folder, 'result.json'), {})
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as f:
            source = f.read()
    except OSError:
        source = ''
    return {**m, 'status': _tighten_status(job_id, folder), 'source': source, 'result': res,
            'adoption': _host_apps().load_json(os.path.join(folder, 'adoption.json'), {}),
            'log': _tail(os.path.join(folder, 'log.txt'), 6000)}



def adopt_tighten(data: dict, identity) -> dict:
    """Persist an explicit owner choice of an exact reviewed candidate; no models."""
    if not getattr(identity, 'is_owner', False):
        raise SymblicApiError('Only the owner can adopt a tightening.')
    from symblic.authoring import tighten as T
    folder = _tighten_folder(data.get('id'))
    with _host_apps().store_lock(os.path.join(folder, 'adoption')):
        result = _host_apps().load_json(os.path.join(folder, 'result.json'), {})
        if result.get('status') != 'done' or result.get('version') != T.TIGHTEN_VERSION:
            raise SymblicApiError('Only a completed audited candidate can be adopted.')
        if any(data.get(key) != result.get(key) for key in ('original_sha256', 'candidate_sha256', 'audit_sha256')):
            raise SymblicApiError('The candidate changed; reload and review it again.')
        try:
            actor = getattr(identity, 'email', '') or 'authenticated-local-owner'
            adopted = T.adopt(result, T.adoption_token(result, actor))
        except (T.FidelityError, KeyError) as error:
            raise SymblicApiError(str(error)) from None
        if adopted['adoption']['status'] not in ('adopted', 'unchanged'):
            raise SymblicApiError('Adoption refused: ' + adopted['adoption'].get('reason', 'unassessed'))
        receipt = {key: adopted[key] for key in ('version', 'original_sha256', 'candidate_sha256',
                                                'audit_sha256', 'adoption', 'program')}
        _private_save(os.path.join(folder, 'adoption.json'), receipt)
        return receipt


def stop_tighten(job_id: str) -> dict:
    _tighten_folder(job_id)
    return {'ok': launcher['stop'](job_id, f'symblic-tighten-{job_id}')}


# ------------------------------------------------------------------------------------------------ spec sheets

SPEC_MAX = 400_000                     # characters of one spec sheet
# Spec sheets shipped with the repository: examples/ and each game kit's sheets/ folder (NAME.sheet.md).
SPEC_EXAMPLE_DIRS = (os.path.join(REPO_ROOT, 'examples'), os.path.join(REPO_ROOT, 'kits', 'tetris', 'sheets'),
                     os.path.join(REPO_ROOT, 'kits', 'kirby', 'sheets'))
SPEC_DEFAULT_BY = ['ollama:qwen3:4b-instruct', 'ollama:phi4-mini', 'ollama:gemma3:4b']


def _sheet(data: dict) -> str:
    sheet = str(data.get('sheet') or '')
    if not sheet.strip():
        raise SymblicApiError('Paste a spec sheet first.')
    if len(sheet) > SPEC_MAX:
        raise SymblicApiError(f'The spec sheet is longer than {SPEC_MAX} characters.')
    return sheet


def spec_check(data: dict) -> dict:
    """What a spec sheet holds and what keeps it from compiling (docs/symblic/SPEC-SHEETS.md). Nothing runs."""
    from symblic.spec import sheets as SP
    try:
        sheet = SP.parse(_sheet(data))
    except SP.SheetError as e:
        return {'ok': False, 'problems': [str(e)], 'units': []}
    mode = data.get('mode', 'legacy')
    if mode not in ('legacy', 'task-cards'):
        raise SymblicApiError('Build mode must be legacy or task-cards.')
    plan = None
    if mode == 'task-cards':
        from symblic.spec import contracts as C
        try:
            plan = C.plan(sheet, externals=data.get('externals', []))
            from symblic.spec import build as B
            B.compiler_settings(plan, presentation=data.get('presentation', 'compact'),
                                declaration_contracts=data.get('declaration_contracts'))
            problems = []
        except (C.ContractError, SP.SheetError, S.SymblicError) as error:
            problems = [f'{getattr(error, "code", "contract")}: {error}']
    else:
        problems = SP.problems(sheet)
    return {'ok': not problems, 'problems': problems, 'title': sheet['title'],
            'file': (sheet['template'] or {}).get('file', ''),
            'units': [{'heading': u['heading'], 'examples': len(u['examples']), 'uses': u['uses']}
                      for u in sheet['units']], **({'plan': plan, 'mode': mode} if mode == 'task-cards' else {})}


def spec_run(data: dict) -> dict:
    """Compile a spec sheet (deterministically, no model) and start the build. `by` lists the applicators that may
    write units (default: the local models on the worker nodes); samples, retries and rounds shape route=search."""
    from symblic.spec import sheets as SP
    sheet = _sheet(data)
    raw_by = data.get('by') if isinstance(data.get('by'), list) else SPEC_DEFAULT_BY
    by = [b for b in (_clean_by(x) for x in raw_by[:12]) if b]
    if not by:
        raise SymblicApiError('Choose at least one model to write the units.')

    def count(key, default, hi):
        try:
            value = int(data.get(key) if data.get(key) not in (None, '') else default)
        except (TypeError, ValueError):
            raise SymblicApiError(f'{key} must be a number.') from None
        if not 1 <= value <= hi:
            raise SymblicApiError(f'{key} must be from 1 to {hi}.')
        return value
    samples = count('samples', max(len(by), 3), 25)
    retries = count('retries', 3, 5)
    rounds = count('rounds', 3, 20)
    mode = data.get('mode', 'legacy')
    if mode not in ('legacy', 'task-cards'):
        raise SymblicApiError('Build mode must be legacy or task-cards.')
    if mode == 'task-cards':
        from symblic.spec import build as B
        from symblic.spec import contracts as C
        try:
            if data.get('manifest') is not None and data.get('keep'):
                raise SymblicApiError('Choose an earlier run or an imported manifest, not both.')
            artifacts = None
            if data.get('manifest') is not None:
                C.verify_manifest(data['manifest'], expected_manifest_sha256=data.get('manifest_sha256'))
                artifacts = data['manifest']['artifacts']
            elif data.get('keep'):
                artifacts = B.checkpoint(run_dir(str(data['keep'])))['artifacts']
            compiled = B.compile_cards(sheet, by, samples=samples, retries=retries, rounds=rounds,
                                       budget=count('budget', 24000, 262144), artifacts=artifacts,
                                       redo=data.get('redo', []), externals=data.get('externals', []),
                                       presentation=data.get('presentation', 'compact'),
                                       declaration_contracts=data.get('declaration_contracts'))
        except (SP.SheetError, C.ContractError, S.SymblicError, OSError, ValueError) as error:
            raise SymblicApiError(f'Task-card build: {error}') from None
        started = start_run({'source': compiled['source'], 'options': compiled['options'],
                             'title': str(data.get('title') or 'Task-card build: ' + SP.parse(sheet)['title'])[:120]})
        return {**started, 'mode': mode, 'kept': compiled['kept'], 'reuse': compiled['reuse'],
                'plan_sha256': compiled['plan']['sha256']}
    keep, keep_from = None, ''
    if data.get('keep'):                    # an incremental rebuild: the units that build accepted stay as they are
        folder = run_dir(str(data.get('keep')))
        keep, keep_from = SP.accepted_units(folder), 'run ' + os.path.basename(folder)
    try:
        source = SP.compile_sheet(sheet, by, samples=samples, retries=retries, rounds=rounds, keep=keep,
                                  keep_from=keep_from)
    except SP.SheetError as e:
        raise SymblicApiError(f'The spec sheet does not compile: {e}') from None
    units = len(SP.parse(sheet)['units'])
    kept = source.count(' (kept)\n')
    title = str(data.get('title') or f'Build {SP.parse(sheet)["title"]} from its spec sheet'
                + (f' (keeping {kept} units)' if kept else ''))[:120]
    options = {'parallel': min(8, samples), 'max_asks': min(2000, units + 10),
               'max_calls': min(10000, max(1, units - kept) * samples * (retries + 1) * rounds)}
    if any(b.startswith('ollama:') for b in by):
        # a unit is a few dozen lines: a small local model that loops otherwise runs to the nodes' 16k-token
        # default (2026-10-10: llama3.2:1b spent 17 minutes on one unit). Callers may widen or narrow the caps.
        options['ollama_limits'] = data.get('ollama_limits') if isinstance(data.get('ollama_limits'), dict) \
            else {'num_predict': 4096, 'timeout_seconds': 900}
    started = start_run({'source': source, 'title': title, 'options': options})
    return {**started, 'kept': kept}


def spec_manifest(data: dict) -> dict:
    """Explicit local revalidation/export, never part of polling a run."""
    from symblic.spec import sheets as SP
    from symblic.spec import build as B
    from symblic.spec import contracts as C
    try:
        result = B.checkpoint(run_dir(str(data.get('id', ''))), complete=True,
                              expected_output_sha256=data.get('output_sha256'))
        return {'manifest': result, 'verification': C.verify_manifest(result)}
    except (SP.SheetError, C.ContractError, S.SymblicError, OSError, ValueError) as error:
        raise SymblicApiError(f'Cannot export this build: {error}') from None


def spec_verify(data: dict) -> dict:
    from symblic.spec import contracts as C
    try:
        return C.verify_manifest(data.get('manifest'), expected_output_sha256=data.get('output_sha256'),
                                 expected_manifest_sha256=data.get('manifest_sha256'))
    except C.ContractError as error:
        raise SymblicApiError(f'Invalid build manifest: {error}') from None


def spec_compare(data: dict) -> dict:
    """Locally recheck supplied code and propose questions from differential probes."""
    try:
        from symblic.spec import compare as C
    except ImportError:
        raise SymblicApiError('The differential checker needs the server update and restart.') from None
    if type(data) is not dict or set(data) - {'sheet', 'candidates', 'probes', 'deadline_seconds', 'externals'}:
        raise SymblicApiError('Unknown differential comparison fields.')
    try:
        return C.compare(_sheet(data), data.get('candidates'), data.get('probes'),
                         deadline_seconds=data.get('deadline_seconds', 30), externals=data.get('externals', []))
    except (ValueError, S.SymblicError, OSError) as error:
        raise SymblicApiError(f'Differential comparison: {error}') from None


def _clean_delegate_by(raw):
    """Strict delegation route input: no truncation or singleton-list collapse."""
    if raw is None or raw == '':
        return None
    if type(raw) is str:
        items = [raw]
    elif type(raw) is list and 1 <= len(raw) <= 12:
        items = raw
    else:
        raise SymblicApiError('Delegation by must be one applicator or a list of 1–12 applicators.')
    if any(type(item) is not str or not item.strip() or len(item) > 300 for item in items):
        raise SymblicApiError('Every delegation applicator must be nonempty text of at most 300 characters.')
    try:
        clean = [S.parse_applicator(item)['spec'] for item in items]
    except S.SymblicError as error:
        raise SymblicApiError(error.message) from None
    if len(set(clean)) != len(clean):
        raise SymblicApiError('Each delegation route applicator must be distinct.')
    return clean[0] if type(raw) is str else clean


def delegate_run(data: dict) -> dict:
    from symblic.delegate import contracts as C
    from symblic.delegate import run as D
    if type(data) is not dict or set(data) - {'task', 'by', 'title'}:
        raise SymblicApiError('Unknown or malformed delegation run fields.')
    try:
        by = _clean_delegate_by(data.get('by'))
        task = D.prepare(data.get('task'), by=by)
        result = start_run({'source': task['source'], 'inputs': task['inputs'], 'options': task['options'],
                            'by': by, 'title': str(data.get('title') or task['template_id'])[:120]},
                           delegation={**{key: task[key] for key in ('contract_id', 'template_id', 'output_binding',
                                                                    'assurance', 'routing', 'routing_id')},
                                       'request': C._copy(data.get('task'))})
        return {**result, 'contract_id': task['contract_id'], 'routing_id': task['routing_id'],
                'routing': task['routing'], 'output_encoding': task['output_encoding']}
    except (ValueError, S.SymblicError) as error:
        raise SymblicApiError(f'Delegation: {error}') from None


def _delegation_contract(declaration, source, inputs, options):
    """Reconstruct exact template and route through the same pure worker gate."""
    from symblic.delegate import run as D
    try:
        return D.verify_declaration(declaration, source, inputs, options)
    except (ValueError, S.SymblicError, TypeError, KeyError) as error:
        raise SymblicApiError('Cannot verify delegation contract: ' + str(error)) from None


def delegate_result(run_id: str) -> dict:
    folder = run_dir(run_id)
    meta = _host_apps().load_json(os.path.join(folder, 'meta.json'), {})
    if type(meta) is not dict or type(meta.get('options')) is not dict:
        raise SymblicApiError('The delegation metadata is missing or damaged.')
    declaration = meta.get('delegation')
    if not declaration:
        raise SymblicApiError('This run has no delegation result contract.')
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as stream:
            source = stream.read(S.MAX_SOURCE + 1)
    except (OSError, UnicodeError):
        raise SymblicApiError('The delegation source is missing or damaged.') from None
    task = _delegation_contract(declaration, source, meta.get('inputs'), meta.get('options', {}))
    state = _state(folder); status = _status(run_id, folder, state)
    output = None
    if status == 'done':
        rows = state.get('outputs') or []
        if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict or 'canonical' not in rows[0]:
            raise SymblicApiError('The run worker did not record an exact canonical result; update the worker and rerun.')
        row = rows[0]
        final = S.parse(source, execution_profile='verified')['statements'][-1]
        if (state.get('error') or type(state.get('kernel')) is not dict
                or state['kernel'].get('id') != meta['options']['execution_pins']['kernel_id']
                or row.get('canonical_version') != S.CANON_VERSION
                or row.get('kind') != 'show' or row.get('line') != final.line
                or final.k != 'show' or final.value.k != 'name'
                or final.value.name != task['output_binding'] or row.get('binding') != task['output_binding']):
            raise SymblicApiError('The recorded output does not match the completed delegation contract.')
        output = row['canonical']
        from symblic.kernel import execution_pins as X
        try:
            output_hash = hashlib.sha256(X._json(output)).hexdigest()[:16]
        except S.SymblicError as error:
            raise SymblicApiError('The canonical result is damaged: ' + error.message) from None
        recorded = state.get('bindings')
        if type(recorded) is not list or any(type(b) is not dict for b in recorded):
            raise SymblicApiError('The delegation output bindings are damaged.')
        bindings = [b for b in recorded if b.get('name') == task['output_binding']]
        if row.get('hash') != output_hash or len(bindings) != 1 or bindings[0].get('hash') != output_hash:
            raise SymblicApiError('The canonical result differs from its recorded output binding.')
    routing = {}
    if 'routing' in task:
        routing = {'routing': {**task['routing'], 'routing_id': task['routing_id'],
                              'calls': state.get('calls'), 'model_budget': state.get('model_budget'),
                              'cached_requests': state.get('cached'),
                              'attempt_scope': 'native_trace_not_included_in_compact_result',
                              'semantic_correctness': 'not_established'}}
    return {**{key: value for key, value in declaration.items() if key != 'request'}, **routing,
            **({'determinism_summary': state['determinism_summary']}
               if type(state.get('determinism_summary')) is dict else {}),
            'id': run_id, 'status': status, 'accepted': status == 'done', 'result': output,
            'output_encoding': task['output_encoding'],
            'calls': state.get('calls'), 'error': state.get('error'), 'evidence': state.get('evidence')}


def delegate_catalog(handler):
    """Read one optional raw selector; the generic query helper drops blanks and duplicates."""
    from symblic.delegate import contracts as D
    from urllib.parse import parse_qsl

    path = getattr(handler, 'path', '')
    if type(path) is str and '?' in path:
        query = path.split('?', 1)[1]
        if not query:
            return D.catalog()
        if len(query) > 1024:
            raise SymblicApiError('Catalog query exceeds 1024 characters.')
        try:
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                              encoding='utf-8', errors='strict', max_num_fields=8)
        except (ValueError, UnicodeError):
            raise SymblicApiError('Malformed catalog query; use one template selector.') from None
        if len(pairs) != 1 or pairs[0][0] != 'template':
            raise SymblicApiError('Catalog accepts exactly one template selector and no other query fields.')
        selector = pairs[0][1]
    else:
        # Embedded handlers without a URL keep their existing query interface.
        selector = handler.get_query_param('template')
        if selector is None:
            return D.catalog()
    try:
        return D.catalog(selector)
    except D.ContractError as error:
        raise SymblicApiError(str(error)) from None


def spec_example(name: str) -> dict:
    """A spec sheet shipped with the repository (NAME.sheet.md in one of SPEC_EXAMPLE_DIRS)."""
    if not re.fullmatch(r'[a-z0-9-]{1,40}', str(name or '')):
        raise SymblicApiError('No such example.')
    path = next((os.path.join(folder, f'{name}.sheet.md') for folder in SPEC_EXAMPLE_DIRS
                 if os.path.isfile(os.path.join(folder, f'{name}.sheet.md'))), None)
    if path is None:
        raise SymblicApiError('No such example.')
    with open(path, encoding='utf-8') as f:
        return {'name': name, 'sheet': f.read()}


def handle(handler, method: str, route: str, data: dict) -> bool:
    """route is the part after /api/automation/symblic/."""
    q = handler.get_query_param
    if route.startswith('examples/'):
        try:
            from integration.host import symblic_example_artifacts as symblic_example_artifacts
        except ImportError:
            handler.send_json({'error': 'Checked example downloads need the server update and restart.'}, 503)
            return True
        return symblic_example_artifacts.handle(handler, method, route, data)
    if route.startswith('forge/'):
        try:
            from integration.host import symblic_forge_bridge as symblic_forge_bridge
        except ImportError:
            handler.send_json({'error': 'Frozen Forge imports need the server update and restart.'}, 503)
            return True
        return symblic_forge_bridge.handle(handler, method, route, data)
    if route.startswith('experiments/'):
        try:
            from integration.host import symblic_experiments_api as symblic_experiments_api
        except ImportError:
            handler.send_json({'error': 'Experiments need the server update and restart.'}, 503)
            return True
        return symblic_experiments_api.handle(handler, method, route, data)
    if route.startswith('inquiry/'):
        try:
            from integration.host import symblic_inquiry_api as symblic_inquiry_api
        except ImportError:
            handler.send_json({'error': 'Inquiry planning needs the server update and restart.'}, 503)
            return True
        return symblic_inquiry_api.handle(handler, method, route, data)
    if route.startswith('english/'):
        try:
            from symblic.english import compiler as symblic_english  # noqa: F401 -- capability must be present before accepting any request
            from integration.host import symblic_english_api as symblic_english_api
        except ImportError:
            handler.send_json({'error': 'English statements need the server update and restart.'}, 503)
            return True
        return symblic_english_api.handle(handler, method, route, data)
    if route.startswith('memory/'):
        try:
            from integration.host import symblic_memory_api as symblic_memory_api
        except ImportError:
            handler.send_json({'error': 'The notebook interface needs the server update and restart.'}, 503)
            return True
        return symblic_memory_api.handle(handler, method, route, data)
    if route == 'academy/source':
        try:
            from integration.host import symblic_academy_sources as symblic_academy_sources
        except ImportError:
            handler.send_json({'error': 'The Academy source reader is unavailable. Reload after the server update.'}, 503)
            return True
        return symblic_academy_sources.handle(handler, method)
    if route.startswith('mica/'):
        try:
            from integration.host import symblic_mica_api as symblic_mica_api
        except ImportError:
            handler.send_json({'error': 'MICA needs the server update and restart.'}, 503)
            return True
        return symblic_mica_api.handle(handler, method, route, data)
    if route.startswith(('graph/', 'policy/')):
        try:
            from integration.host import symblic_graph_api as symblic_graph_api
        except ImportError:
            handler.send_json({'error': 'The graph interface needs the server update and restart.'}, 503)
            return True
        return symblic_graph_api.handle(handler, method, route, data)
    if route.startswith('supervisor/'):
        try:
            from integration.host import symblic_supervisor_api as symblic_supervisor_api
        except ImportError:
            handler.send_json({'error': 'The Symblic supervisor needs its server modules installed and restarted.'}, 503)
            return True
        return symblic_supervisor_api.handle(handler, method, route, data)
    if route.startswith('intent/'):
        try:
            from integration.host import symblic_intent_api as symblic_intent_api
        except ImportError:
            handler.send_json({'error': 'The Symblic interpreter is unavailable; its server modules need to be installed and restarted.'}, 503)
            return True
        return symblic_intent_api.handle(handler, method, route, data)
    if route.startswith('workcards/'):
        try:
            from symblic.authoring import workcards as symblic_workcards
        except ImportError:
            handler.send_json({'error': 'The Symblic workcards need their server module installed and restarted.'}, 503)
            return True
        return symblic_workcards.handle(handler, method, route, data)
    if route in ('library', 'module', 'tests', 'lock') or route.startswith(('paper/', 'lock/', 'lang/')):
        from integration.host import symblic_lang_api as symblic_lang_api
        return symblic_lang_api.handle(handler, method, route, data)
    try:
        if method == 'GET':
            if route == 'meta':
                handler.send_json(meta())
            elif route == 'runs':
                handler.send_json({'runs': list_runs()})
            elif route == 'run':
                handler.send_json(run_view(q('id')))
            elif route == 'artifact':
                handler.send_bytes(artifact(q('id'), q('name')), 'image/svg+xml')
            elif route == 'compares':
                handler.send_json({'compares': list_compares()})
            elif route == 'compare':
                handler.send_json(compare_view(q('id')))
            elif route == 'programs':
                handler.send_json({'programs': load_programs()})
            elif route == 'evidence':
                handler.send_json(evidence())
            elif route == 'tightens':
                handler.send_json({'tightens': list_tightens()})
            elif route == 'tighten':
                handler.send_json(tighten_view(q('id')))
            elif route == 'spec/example':
                handler.send_json(spec_example(q('name')))
            elif route == 'delegate/catalog':
                handler.send_json(delegate_catalog(handler))
            elif route == 'delegate/result':
                handler.send_json(delegate_result(q('id')))
            else:
                return False
            return True
        if method != 'POST':
            return False
        data = data if isinstance(data, dict) else {}
        if route == 'check':
            handler.send_json(S.check(_clean_source(data.get('source')), execution_profile=data.get('profile')))
        elif route == 'editor/check':
            try:
                from symblic.authoring import editor_diagnostics as diagnostics
            except ImportError:
                handler.send_json({'error': 'Inline diagnostics need the server update and restart.'}, 503)
                return True
            handler.send_json(diagnostics.check(data.get('source'), language=data.get('language', 'native'),
                                                execution_profile=data.get('profile')))
        elif route == 'logic/compile':
            try:
                from symblic.adapters import logic as symblic_logic
            except ImportError:
                handler.send_json({'error': 'The logical construction compiler is unavailable until the server update.'}, 503)
                return True
            try:
                handler.send_json(symblic_logic.compile_task(data))
            except ValueError as error:
                handler.send_json({'error': str(error)}, 400)
        elif route == 'preview':
            handler.send_json(preview(data))
        elif route == 'run':
            handler.send_json(start_run(data))
        elif route == 'stop':
            handler.send_json(stop_run(data.get('id')))
        elif route == 'resume':
            handler.send_json(resume_run(data.get('id')))
        elif route == 'run/recheck-models':
            handler.send_json(recheck_models(data.get('id')))
        elif route == 'delete':
            handler.send_json(delete_run(data.get('id')))
        elif route == 'compare':
            handler.send_json(start_compare(data))
        elif route == 'programs/save':
            handler.send_json(save_program(data))
        elif route == 'programs/delete':
            handler.send_json(delete_program(str(data.get('name') or '')))
        elif route == 'tighten':
            handler.send_json(start_tighten(data))
        elif route == 'tighten/adopt':
            handler.send_json(adopt_tighten(data, handler.identity()))
        elif route == 'tighten/stop':
            handler.send_json(stop_tighten(data.get('id')))
        elif route == 'spec/check':
            handler.send_json(spec_check(data))
        elif route == 'spec/run':
            handler.send_json(spec_run(data))
        elif route == 'spec/manifest':
            handler.send_json(spec_manifest(data))
        elif route == 'spec/verify':
            handler.send_json(spec_verify(data))
        elif route == 'spec/compare':
            handler.send_json(spec_compare(data))
        elif route == 'delegate/compile':
            from symblic.delegate import contracts as D
            handler.send_json(D.inspect_task(data))
        elif route == 'delegate/run':
            handler.send_json(delegate_run(data))
        else:
            return False
        return True
    except SymblicApiError as e:
        handler.send_json({'error': str(e)}, 400)
        return True

"""Distillation worker: runs ONE prepared training or evaluation job directory with an explicit backend.

What it is for
    The last step of the distillation pipeline (see README.md in this package). It fine-tunes a local Hugging Face
    model with a LoRA adapter on the frozen training split (``run`` on a training job), evaluates the base model
    and one pinned trained checkpoint on the frozen test split (``run`` on an evaluation job), or answers one
    prompt with either arm (``infer``). The only backend is TorchLoraBackend (torch + transformers + peft, CPU).

Inert on import: stdlib imports only, no thread, process, model or network. torch/transformers/peft are imported
only inside TorchLoraBackend methods, on the worker path, after offline mode is forced. Launch is the caller's
job: ``launch_manifest()`` describes the exact argv/env the operator's runner should execute; nothing here
dispatches over SSH, Ollama, a cloud API or a shell string. Run it as::

    python3 symblic/distill/worker.py run --job-dir JOB --models-root MODELS --backend torch-lora

Job directory layout (created by `prepare_job`, owned by one worker at a time through `lock`):
  job.json        frozen job (training: train/validation rows only; evaluation: test prompts, no answers)
  state.json      atomic, fsynced state with the attempt history (never silently reset)
  checkpoints/step-NNNNNNNN/   files + MANIFEST.json (sha256 of every file, job/plan/model/backend identities)
  checkpoints/quarantine/      torn or unverifiable checkpoint directories, retained for inspection
  result.json     written once, when the job reaches a terminal state

Status: research tooling. One small CPU pilot ran it end to end (see docs/reference/DISTILLATION.md); no
claim is made that training on Symblic-accepted answers improves a model.

Depends on: ``symblic.distill.datasets`` (pure), and optionally ``symblic/distill/checkers.py`` for native
grading. Heavy packages are optional and pinned (datasets._PACKAGE_PINS).
"""

from __future__ import annotations

import copy
import errno
import fcntl
import hashlib
import os
import re
import stat
import sys
import time

if __package__ in (None, ''):        # run as a script: make the repository root importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from symblic.distill import datasets as D  # noqa: E402  (stdlib-only, inert)

STATE_VERSION = 1
MAX_HISTORY = 200
MAX_MODEL_FILES = 2_000
MAX_LOSSES = 2_000
TERMINAL = ('completed',)
_STEP_DIR = re.compile(r'step-(\d{8})\Z')
_WEIGHT_PICKLE = ('.bin', '.pt', '.pth', '.pkl', '.pickle', '.ckpt')
OFFLINE_ENV = {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
               'HF_HUB_DISABLE_TELEMETRY': '1', 'TOKENIZERS_PARALLELISM': 'false'}


class WorkerError(Exception):
    """A refused or failed job step; `code` is a stable identifier."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class BackendUnavailable(WorkerError):
    """Missing package, wrong version, missing hardware or unreadable model: visible failure, never trained."""


class Stopped(Exception):
    """Raised inside the training loop when a stop was requested."""


def _now():
    return int(time.time())


# ---------------------------------------------------------------------------
# Model snapshot manifest (the operator computes it when pinning; the worker re-verifies before loading)
# ---------------------------------------------------------------------------

def _hash_file(path):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise WorkerError('not_regular_file')
        while True:
            chunk = os.read(fd, 1 << 22)
            if not chunk:
                break
            h.update(chunk)
    finally:
        os.close(fd)
    return h.hexdigest()


def _walk_files(root, *, limit):
    """Every regular file under root (relative POSIX paths). Any symlink, device or FIFO refuses."""
    out, stack = [], ['']
    while stack:
        rel = stack.pop()
        here = os.path.join(root, rel) if rel else root
        try:
            names = sorted(os.listdir(here))
        except OSError:
            raise WorkerError('unreadable_directory') from None
        for name in names:
            child_rel = f'{rel}/{name}' if rel else name
            st = os.lstat(os.path.join(root, child_rel))
            if stat.S_ISLNK(st.st_mode):
                raise WorkerError('symlink_refused')
            if stat.S_ISDIR(st.st_mode):
                stack.append(child_rel)
            elif stat.S_ISREG(st.st_mode):
                out.append(child_rel)
                if len(out) > limit:
                    raise WorkerError('too_many_files')
            else:
                raise WorkerError('not_regular_file')
    return sorted(out)


def model_manifest(model_dir):
    """Pinned identity of a local Hugging Face snapshot: [[path, size, sha256], ...] and its digest.
    Refuses symlinks, pickle weight formats and custom code (trust_remote_code is never enabled)."""
    st = os.lstat(model_dir) if os.path.lexists(model_dir) else None
    if st is None:
        raise BackendUnavailable('model_unavailable')
    if not stat.S_ISDIR(st.st_mode):
        raise WorkerError('symlink_refused' if stat.S_ISLNK(st.st_mode) else 'model_unavailable')
    files = _walk_files(model_dir, limit=MAX_MODEL_FILES)
    if 'config.json' not in files or not any(f.endswith('.safetensors') for f in files):
        raise BackendUnavailable('model_format_unsupported')
    if any(f.lower().endswith(_WEIGHT_PICKLE) or f.endswith('.py') for f in files):
        raise BackendUnavailable('model_format_unsupported')
    rows = []
    for rel in files:
        path = os.path.join(model_dir, rel)
        rows.append([rel, os.lstat(path).st_size, _hash_file(path)])
    return {'files': rows, 'files_sha256': D.digest(rows)}


# ---------------------------------------------------------------------------
# Job preparation and the launch manifest (no execution)
# ---------------------------------------------------------------------------

def prepare_job(parent, name, job):
    """Create parent/name with job.json and an initial state. Refuses an existing directory (no overwrite)."""
    if type(job) is not dict or job.get('kind') not in ('train', 'eval') or 'job_sha256' not in job:
        raise WorkerError('job_schema')
    _verify_job(job)
    path = D.safe_child(parent, name)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        raise WorkerError('job_exists') from None
    os.mkdir(os.path.join(path, 'checkpoints'), 0o700)
    D.write_json(os.path.join(path, 'job.json'), job, exclusive=True)
    D.write_json(os.path.join(path, 'state.json'), {'version': STATE_VERSION, 'job_sha256': job['job_sha256'],
                                                     'status': 'prepared', 'history': [], 'step': 0,
                                                     'checkpoint': None, 'losses': [], 'outcomes': [],
                                                     'in_flight': None}, exclusive=True)
    return path


def eval_job(eval_plan, plan, *, adapter_manifest_sha256):
    """Evaluation job: test prompts and answer types (and reference hashes for the reference checker), never answers.
    The trained arm must use the exact checkpoint whose MANIFEST digest is pinned here."""
    D.verify_eval_plan(eval_plan)
    D.verify_plan(plan, expected_sha256=eval_plan['plan_sha256'])
    if type(adapter_manifest_sha256) is not str or not re.fullmatch(r'[0-9a-f]{64}', adapter_manifest_sha256):
        raise WorkerError('adapter_pin')
    body = {'version': D.VERSION, 'kind': 'eval', 'plan': plan, 'eval_plan': eval_plan,
            'adapter_manifest_sha256': adapter_manifest_sha256}
    return {**body, 'job_sha256': D.digest(body)}


def _verify_job(job):
    body = {k: v for k, v in job.items() if k != 'job_sha256'}
    if D.digest(body) != job['job_sha256']:
        raise WorkerError('job_changed')
    D.verify_plan(job['plan'])
    if job['kind'] == 'train':
        if set(job) != {'version', 'kind', 'plan', 'train', 'validation', 'test_ids_sha256', 'job_sha256'}:
            raise WorkerError('job_schema')
        if D.digest([r['item_id'] for r in job['train']]) != job['plan']['train_ids_sha256'] \
                or D.digest([r['item_id'] for r in job['validation']]) != job['plan']['validation_ids_sha256'] \
                or job['test_ids_sha256'] != job['plan']['test_ids_sha256']:
            raise WorkerError('job_changed')
        for row in job['train'] + job['validation']:
            if set(row) != {'item_id', 'system', 'user', 'target'}:
                raise WorkerError('job_schema')
    else:
        if set(job) != {'version', 'kind', 'plan', 'eval_plan', 'adapter_manifest_sha256', 'job_sha256'}:
            raise WorkerError('job_schema')
        D.verify_eval_plan(job['eval_plan'])
        if job['eval_plan']['plan_sha256'] != job['plan']['plan_sha256']:
            raise WorkerError('job_changed')
    return job['job_sha256']


def launch_manifest(job_dir, *, models_root, python, adapter_dir=None, backend='torch-lora'):
    """The exact command the operator's runner should execute (argv, env). Returned as data; runs nothing."""
    for value in (job_dir, models_root, python) + ((adapter_dir,) if adapter_dir else ()):
        if type(value) is not str or not os.path.isabs(value) or '\0' in value or '\n' in value:
            raise WorkerError('launch_paths_must_be_absolute')
    if backend != 'torch-lora':
        raise WorkerError('backend_unsupported')
    job = D.read_json(os.path.join(job_dir, 'job.json'))
    _verify_job(job)
    argv = [python, os.path.abspath(__file__), 'run', '--job-dir', job_dir, '--models-root', models_root,
            '--backend', backend]
    if adapter_dir:
        argv += ['--adapter-dir', adapter_dir]
    plan = job['plan']
    return {'version': D.VERSION, 'argv': argv, 'shell': False, 'env': dict(OFFLINE_ENV),
            'job_sha256': job['job_sha256'], 'plan_sha256': plan['plan_sha256'], 'kind': job['kind'],
            'requires': {'python': '>=3.10', 'packages': plan['packages'], 'device': plan['options']['device'],
                         'model_dir': plan['model']['dir'], 'model_files_sha256': plan['model']['files_sha256']},
            'admission': 'caller_owned_registered_path',
            'notes': ['run inside a resource-limited unit (a container or a systemd scope) on a machine chosen for training',
                      'single process; the job lock refuses a concurrent worker',
                      'the result is a LoRA adapter checkpoint; it is never promoted or deployed automatically']}


# ---------------------------------------------------------------------------
# Locking and state
# ---------------------------------------------------------------------------

class _JobLock:
    def __init__(self, job_dir):
        self.path = os.path.join(job_dir, 'lock')
        self.fd = None

    def __enter__(self):
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
        try:
            self.fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise WorkerError('symlink_refused' if exc.errno == errno.ELOOP else 'lock_unavailable') from None
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.fd)
            self.fd = None
            raise WorkerError('job_busy') from None
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
        return False


def _job_dir(job_dir):
    path = os.path.abspath(job_dir)
    st = os.lstat(path) if os.path.lexists(path) else None
    if st is None or not stat.S_ISDIR(st.st_mode):
        raise WorkerError('symlink_refused' if st is not None and stat.S_ISLNK(st.st_mode) else 'job_missing')
    if os.path.realpath(path) != path:
        raise WorkerError('symlink_refused')
    return path


def _read_state(job_dir, job):
    try:
        state = D.read_json(os.path.join(job_dir, 'state.json'))
    except D.DistillError as exc:
        raise WorkerError('torn_state' if exc.code in ('invalid_json', 'invalid_utf8') else exc.code) from None
    if type(state) is not dict or state.get('version') != STATE_VERSION:
        raise WorkerError('unknown_state')
    if state.get('job_sha256') != job['job_sha256']:
        raise WorkerError('state_job_mismatch')
    if state.get('status') not in ('prepared', 'running', 'failed', 'stopped', 'completed'):
        raise WorkerError('unknown_state')
    return state


def _save_state(job_dir, state):
    state['history'] = state['history'][-MAX_HISTORY:]
    state['losses'] = state['losses'][-MAX_LOSSES:]
    D.write_json(os.path.join(job_dir, 'state.json'), state)


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

def _checkpoint_identity(job, model_files_sha256, backend_identity):
    return {'job_sha256': job['job_sha256'], 'plan_sha256': job['plan']['plan_sha256'],
            'model_files_sha256': model_files_sha256, 'backend_sha256': D.digest(backend_identity)}


def _quarantine(job_dir, name, state, reason):
    qdir = os.path.join(job_dir, 'checkpoints', 'quarantine')
    os.makedirs(qdir, mode=0o700, exist_ok=True)
    target = os.path.join(qdir, f'{name}.{_now()}.{os.urandom(4).hex()}')
    os.rename(os.path.join(job_dir, 'checkpoints', name), target)
    D._fsync_dir(os.path.join(job_dir, 'checkpoints'))
    state['history'].append({'event': 'quarantined', 'checkpoint': name, 'reason': reason,
                             'kept_at': os.path.relpath(target, job_dir), 'at': _now()})


def verify_checkpoint(path, *, identity=None):
    """MANIFEST.json + every listed file's sha256; no extra files, no symlinks. Returns the manifest digest."""
    manifest = D.read_json(os.path.join(path, 'MANIFEST.json'))
    if type(manifest) is not dict or set(manifest) != {'version', 'step', 'identity', 'files', 'losses_sha256'}:
        raise WorkerError('checkpoint_manifest')
    files = _walk_files(path, limit=MAX_MODEL_FILES)
    if sorted(manifest['files']) != sorted(f for f in files if f != 'MANIFEST.json'):
        raise WorkerError('checkpoint_files')
    for rel, digest in manifest['files'].items():
        if _hash_file(os.path.join(path, rel)) != digest:
            raise WorkerError('checkpoint_hash_mismatch')
    if identity is not None and manifest['identity'] != identity:
        raise WorkerError('checkpoint_identity_mismatch')
    return D.digest(manifest), manifest


def _latest_checkpoint(job_dir, identity, state):
    root = os.path.join(job_dir, 'checkpoints')
    names = sorted(os.listdir(root))
    best = None
    for name in names:
        full = os.path.join(root, name)
        if name == 'quarantine':
            continue
        if os.path.islink(full):
            raise WorkerError('symlink_refused')
        if name.startswith('.tmp-'):
            _quarantine(job_dir, name, state, 'torn_temporary')
            continue
        m = _STEP_DIR.match(name)
        if not m:
            raise WorkerError('unknown_checkpoint_entry')
        try:
            digest, manifest = verify_checkpoint(full)
        except (WorkerError, D.DistillError) as exc:
            _quarantine(job_dir, name, state, getattr(exc, 'code', 'invalid'))
            continue
        if manifest['identity'] != identity:
            # Another job/model/backend's checkpoint: never resumed and never deleted.
            raise WorkerError('checkpoint_identity_mismatch')
        if manifest['step'] != int(m.group(1)):
            _quarantine(job_dir, name, state, 'step_mismatch')
            continue
        best = (manifest['step'], name, digest)
    return best


def _write_checkpoint(job_dir, step, identity, backend, losses):
    root = os.path.join(job_dir, 'checkpoints')
    name = f'step-{step:08d}'
    final = os.path.join(root, name)
    if os.path.lexists(final):
        raise WorkerError('checkpoint_exists')
    tmp = os.path.join(root, f'.tmp-{name}-{os.urandom(4).hex()}')
    os.mkdir(tmp, 0o700)
    backend.save(tmp)
    files = {}
    for rel in _walk_files(tmp, limit=MAX_MODEL_FILES):
        if rel == 'MANIFEST.json':
            raise WorkerError('backend_wrote_manifest')
        path = os.path.join(tmp, rel)
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        files[rel] = _hash_file(path)
    manifest = {'version': STATE_VERSION, 'step': step, 'identity': identity, 'files': files,
                'losses_sha256': D.digest(losses)}
    D.write_json(os.path.join(tmp, 'MANIFEST.json'), manifest, exclusive=True)
    D._fsync_dir(tmp)
    os.rename(tmp, final)
    D._fsync_dir(root)
    return name, D.digest(manifest)


# ---------------------------------------------------------------------------
# Deterministic schedule
# ---------------------------------------------------------------------------

def schedule(train_ids, options):
    """Micro-batch order per epoch from sha256(seed, epoch, id); one step = grad_accum micro-batches."""
    micro = []
    for epoch in range(options['epochs']):
        order = sorted(train_ids, key=lambda i: hashlib.sha256(f'{options["seed"]}:{epoch}:{i}'.encode()).hexdigest())
        for k in range(0, len(order) - options['batch_size'] + 1, options['batch_size']):
            micro.append(order[k:k + options['batch_size']])
    steps = min(options['max_steps'], len(micro) // options['grad_accum'])
    if steps < 1:
        raise WorkerError('too_few_examples')
    return micro, steps


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(job_dir, *, models_root, backend, adapter_dir=None, stop=None):
    """Run or resume one job. Returns the result dict; a terminal result is also written to result.json."""
    job_dir = _job_dir(job_dir)
    with _JobLock(job_dir):
        job = D.read_json(os.path.join(job_dir, 'job.json'))
        if type(job) is not dict or job.get('kind') not in ('train', 'eval') or 'job_sha256' not in job:
            raise WorkerError('job_schema')
        _verify_job(job)
        state = _read_state(job_dir, job)
        result_path = os.path.join(job_dir, 'result.json')
        if os.path.lexists(result_path):
            result = D.read_json(result_path)
            if type(result) is not dict or result.get('job_sha256') != job['job_sha256'] \
                    or result.get('status') != 'completed':
                raise WorkerError('result_mismatch')
            if state['status'] != 'completed':     # crashed after the result was durably written
                state['status'] = 'completed'
                state['history'].append({'event': 'completed_recovered_from_result', 'at': _now()})
                _save_state(job_dir, state)
            return result
        if state['status'] == 'completed':
            raise WorkerError('result_missing')
        if state['status'] == 'running':
            state['history'].append({'event': 'previous_attempt_interrupted', 'outcome': 'unknown', 'at': _now()})
        attempt = sum(1 for h in state['history'] if h.get('event') == 'attempt_started') + 1
        state['history'].append({'event': 'attempt_started', 'attempt': attempt, 'at': _now()})
        state['status'] = 'running'
        _save_state(job_dir, state)
        try:
            if job['kind'] == 'train':
                result = _train(job_dir, job, state, models_root, backend, stop)
            else:
                result = _evaluate(job_dir, job, state, models_root, backend, adapter_dir, stop)
        except Stopped:
            state['status'] = 'stopped'
            state['history'].append({'event': 'stopped', 'attempt': attempt, 'at': _now()})
            _save_state(job_dir, state)
            return {'status': 'stopped', 'job_sha256': job['job_sha256'], 'step': state['step']}
        except (WorkerError, D.DistillError, Exception) as exc:  # noqa: BLE001 - recorded, never 'completed'
            code = exc.code if isinstance(exc, (WorkerError, D.DistillError)) else f'exception:{type(exc).__name__}'
            exc.code = code
            state['status'] = 'failed'
            state['history'].append({'event': 'failed', 'attempt': attempt, 'code': code, 'at': _now()})
            _save_state(job_dir, state)
            return {'status': 'failed', 'code': exc.code, 'job_sha256': job['job_sha256'], 'kind': job['kind'],
                    'completed': False, 'steps_checkpointed': state['step'], 'retained': 'state.json and checkpoints'}
        finally:
            _close(backend)
        state['status'] = 'completed'
        state['history'].append({'event': 'completed', 'attempt': attempt, 'at': _now()})
        D.write_json(os.path.join(job_dir, 'result.json'), result, exclusive=True)
        _save_state(job_dir, state)
        return result


def _close(backend):
    close = getattr(backend, 'close', None)
    if close is not None:
        close()


def _model(models_root, plan):
    root = os.path.abspath(models_root)
    if os.path.realpath(root) != root:
        raise WorkerError('symlink_refused')
    try:
        model_dir = D.safe_child(root, plan['model']['dir'])
    except D.DistillError as exc:
        raise WorkerError(exc.code) from None
    manifest = model_manifest(model_dir)
    if manifest['files_sha256'] != plan['model']['files_sha256']:
        raise WorkerError('model_manifest_mismatch')
    return model_dir, manifest


def _identity(backend, plan):
    ident = backend.identity()
    if type(ident) is not dict or type(ident.get('name')) is not str:
        raise WorkerError('backend_identity')
    D._scan(ident)
    backend.preflight(plan)
    return ident


def _train(job_dir, job, state, models_root, backend, stop):
    plan = job['plan']
    opts = plan['options']
    ident = _identity(backend, plan)
    model_dir, model = _model(models_root, plan)
    identity = _checkpoint_identity(job, model['files_sha256'], ident)
    rows = {r['item_id']: r for r in job['train']}
    micro, steps = schedule(sorted(rows), opts)
    latest = _latest_checkpoint(job_dir, identity, state)
    start = 0
    resume_dir = None
    if latest is not None:
        start, name, _digest = latest
        resume_dir = os.path.join(job_dir, 'checkpoints', name)
        if state['step'] != start or state['checkpoint'] != name:
            state['history'].append({'event': 'resume_from_verified_checkpoint', 'checkpoint': name,
                                     'state_step': state['step'], 'at': _now()})
        state['losses'] = [l for l in state['losses'] if l['step'] <= start]
    elif state['step']:
        state['history'].append({'event': 'no_verified_checkpoint_restart', 'state_step': state['step'], 'at': _now()})
        state['losses'] = []
    state['step'], state['checkpoint'] = start, latest[1] if latest else None
    _save_state(job_dir, state)
    backend.begin(model_dir, plan, resume_dir=resume_dir, adapter_dir=None, trainable=True)
    final = None
    for step in range(start, steps):
        if stop is not None and stop.is_set():
            raise Stopped()
        batches = [[rows[i] for i in mb] for mb in micro[step * opts['grad_accum']:(step + 1) * opts['grad_accum']]]
        loss = backend.train_step(batches)
        D._decimal(loss, 'backend_loss', '0', '1000000')
        state['losses'].append({'step': step + 1, 'loss': loss})
        state['step'] = step + 1
        if (step + 1) % opts['checkpoint_every'] == 0 or step + 1 == steps:
            name, digest = _write_checkpoint(job_dir, step + 1, identity, backend, state['losses'])
            state['checkpoint'] = name
            final = (name, digest)
            _save_state(job_dir, state)
    if final is None:                     # resumed exactly at the end
        name = state['checkpoint']
        final = (name, verify_checkpoint(os.path.join(job_dir, 'checkpoints', name), identity=identity)[0])
    validation = backend.eval_loss([r for r in job['validation']]) if job['validation'] else None
    if validation is not None:
        D._decimal(validation, 'backend_loss', '0', '1000000')
    return {'status': 'completed', 'kind': 'train', 'job_sha256': job['job_sha256'],
            'plan_sha256': plan['plan_sha256'], 'backend': ident, 'model_files_sha256': model['files_sha256'],
            'steps': steps, 'checkpoint': final[0], 'checkpoint_manifest_sha256': final[1],
            'validation_loss': validation, 'losses_sha256': D.digest(state['losses']),
            'promotion': 'never_automatic',
            'claims': {'executed': f'{steps} optimizer steps by backend {ident["name"]}',
                       'quality': 'not_established', 'test_items_used': 0}}


def _evaluate(job_dir, job, state, models_root, backend, adapter_dir, stop):
    plan, eval_plan = job['plan'], job['eval_plan']
    ident = _identity(backend, plan)
    model_dir, model = _model(models_root, plan)
    adapter_dir, digest, _manifest = _pinned_adapter(adapter_dir, job['adapter_manifest_sha256'], plan, model)
    checker = load_native_checker(eval_plan['checker']['native']) if 'native' in eval_plan['checker'] else None
    done = {(o['arm'], o['item_id']): o for o in state['outcomes']}
    if state['in_flight'] is not None:
        state['history'].append({'event': 'in_flight_item_interrupted', 'item': state['in_flight'], 'at': _now()})
    budget = eval_plan['budget']['max_new_tokens']
    for arm in D.ARMS:
        pending = [it for it in eval_plan['items'] if (arm, it['item_id']) not in done]
        if not pending:
            continue
        try:
            backend.begin(model_dir, plan, resume_dir=None, adapter_dir=adapter_dir if arm == 'trained' else None,
                          trainable=False)
            available = True
        except BackendUnavailable as exc:
            available, reason = False, exc.code
        for item in pending:
            if stop is not None and stop.is_set():
                raise Stopped()
            key = [arm, item['item_id']]
            prior = state['in_flight']
            attempts = (prior['attempts'] + 1) if prior and [prior['arm'], prior['item_id']] == key else 1
            if not available:
                row = {'arm': arm, 'item_id': item['item_id'], 'status': 'unavailable', 'attempts': 0,
                       'output_sha256': None, 'check': {'reason': reason}}
            else:
                state['in_flight'] = {'arm': arm, 'item_id': item['item_id'], 'attempts': attempts}
                _save_state(job_dir, state)
                try:
                    text = backend.generate({'system': item['system'], 'user': item['user']}, budget)
                except BackendUnavailable as exc:
                    text, error = None, exc.code
                except Exception as exc:  # noqa: BLE001 - one item's generation failure is an outcome, not a crash
                    text, error = None, f'generation_error:{type(exc).__name__}'
                if text is None:
                    row = {'arm': arm, 'item_id': item['item_id'], 'status': 'error', 'attempts': attempts,
                           'output_sha256': None, 'check': {'reason': error}}
                else:
                    check = D.check_output(item, text)
                    value = check.pop('_value', None)
                    if checker is None:
                        status = D.score_outcome(item, check)
                    else:
                        status, check['native'] = _native_score(checker, eval_plan['checker']['native'], item,
                                                                check, value)
                    row = {'arm': arm, 'item_id': item['item_id'], 'status': status,
                           'attempts': attempts,
                           'output_sha256': hashlib.sha256(text.encode('utf-8', 'surrogatepass')).hexdigest(),
                           'check': check}
            state['outcomes'].append(row)
            state['in_flight'] = None
            _save_state(job_dir, state)
        _close(backend)
    comparison = D.compare(eval_plan, state['outcomes'])
    return {'status': 'completed', 'kind': 'eval', 'job_sha256': job['job_sha256'],
            'eval_sha256': eval_plan['eval_sha256'], 'backend': ident, 'adapter_manifest_sha256': digest,
            'outcomes': state['outcomes'], 'comparison': comparison}


def _pinned_adapter(adapter_dir, pin, plan, model):
    """A trained checkpoint is usable only if its MANIFEST digest equals the pin, every file verifies and it was
    trained under this plan on these exact model files."""
    if adapter_dir is None:
        raise WorkerError('adapter_required')
    adapter_dir = os.path.abspath(adapter_dir)
    if os.path.realpath(adapter_dir) != adapter_dir:
        raise WorkerError('symlink_refused')
    digest, manifest = verify_checkpoint(adapter_dir)
    if digest != pin:
        raise WorkerError('adapter_pin_mismatch')
    if manifest['identity']['plan_sha256'] != plan['plan_sha256'] \
            or manifest['identity']['model_files_sha256'] != model['files_sha256']:
        raise WorkerError('adapter_identity_mismatch')
    return adapter_dir, digest, manifest


# ---------------------------------------------------------------------------
# Native checker interface (trusted, root-registered, hash-pinned; never caller code or a caller path)
# ---------------------------------------------------------------------------
#
# The operator registers native checkers through ONE reviewed module, `checkers.py`, next to this
# worker. It defines `CHECKERS = {name: factory}`; `factory()` returns an object with
#   identity() -> {'id', 'version', 'kernel_id', 'contract_version', 'source_sha256'}
#   check(contract, answer) -> {'passed': bool, 'scope': 'encoded_predicate', 'kernel_id': str,
#                               'receipts': [sha256, ...]}
# `contract` is symblic.distill.datasets.native_contract(item): the original source/statement/kernel/checker and accepted
# predicate hashes, never the accepted answer. The checker resolves the original program from the operator's trusted
# storage and re-runs the native type coercion and predicates on `answer`. The evaluation plan pins the module's
# sha256 and the checker identity; any difference refuses. The registered native scalar checker requires
# a reviewed trusted private contract bundle; an absent or changed bundle refuses initialization.
# The path is fixed; no CLI/config option can name another file.

CHECKER_MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checkers.py')
MAX_CHECKER_BYTES = 2_000_000


def _checker_module():
    path = CHECKER_MODULE_PATH
    if not os.path.lexists(path):
        raise BackendUnavailable('checker_unavailable')
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise WorkerError('not_regular_file')
        raw = os.read(fd, MAX_CHECKER_BYTES + 1)
    except OSError as exc:
        raise WorkerError('symlink_refused' if exc.errno == errno.ELOOP else 'checker_unavailable') from None
    finally:
        if fd is not None:
            os.close(fd)
    if len(raw) > MAX_CHECKER_BYTES:
        raise WorkerError('checker_too_large')
    import types
    module = types.ModuleType('symblic_distill_trusted_checkers')
    module.__file__ = path
    module.__dict__['_SYMBLIC_CHECKER_SOURCE'] = raw
    # Executes exactly the hashed bytes of the fixed, root-reviewed module (same trust as importing repo code).
    exec(compile(raw, path, 'exec'), module.__dict__)  # noqa: S102
    registry = getattr(module, 'CHECKERS', None)
    if type(registry) is not dict:
        raise WorkerError('checker_registry')
    return hashlib.sha256(raw).hexdigest(), registry


def checker_identity(name):
    """For root, when freezing an evaluation plan: the pin of a registered checker (module hash + identity)."""
    module_sha, registry = _checker_module()
    if name not in registry:
        raise BackendUnavailable('checker_unavailable')
    try:
        identity = registry[name]().identity()
    except Exception as exc:  # a missing/stale private registration is a visible refusal
        raise BackendUnavailable('checker_initialization_refused') from exc
    pin = {'name': name, 'module_sha256': module_sha, 'identity': identity}
    try:
        return D.native_checker_pin(pin)
    except D.DistillError:
        raise WorkerError('checker_identity_invalid') from None


def load_native_checker(pin):
    """The registered native checker named by `pin`, refusing a changed module or identity."""
    module_sha, registry = _checker_module()
    if module_sha != pin['module_sha256']:
        raise BackendUnavailable('checker_source_mismatch')
    if pin['name'] not in registry:
        raise BackendUnavailable('checker_unavailable')
    try:
        checker = registry[pin['name']]()
        identity = checker.identity()
    except Exception as exc:
        raise BackendUnavailable('checker_initialization_refused') from exc
    if identity != pin['identity']:
        raise BackendUnavailable('checker_identity_mismatch')
    return checker


def _native_score(checker, pin, item, check, value):
    """Status from a native receipt. Schema failure -> failed (native not run). Kernel mismatch -> unavailable.
    A checker exception or malformed receipt -> error. Only an explicit passed=True receipt passes."""
    if not check['schema_valid']:
        return 'failed', {'ran': False, 'reason': 'schema_invalid'}
    contract = item['contract']
    if contract['kernel_id'] != pin['identity']['kernel_id']:
        return 'unavailable', {'ran': False, 'reason': 'checker_kernel_mismatch'}
    try:
        receipt = checker.check(copy.deepcopy(contract), copy.deepcopy(value))
    except Exception as exc:  # noqa: BLE001 - a checker failure is an outcome, never a pass
        return 'error', {'ran': True, 'reason': f'checker_error:{type(exc).__name__}'}
    if type(receipt) is not dict or set(receipt) != {'passed', 'scope', 'kernel_id', 'receipts'} \
            or type(receipt['passed']) is not bool or receipt['scope'] != 'encoded_predicate' \
            or receipt['kernel_id'] != pin['identity']['kernel_id'] or type(receipt['receipts']) is not list \
            or len(receipt['receipts']) > 64 \
            or any(type(r) is not str or not re.fullmatch(r'[0-9a-f]{64}', r) for r in receipt['receipts']):
        return 'error', {'ran': True, 'reason': 'checker_bad_receipt'}
    native = {'ran': True, 'passed': receipt['passed'], 'scope': 'encoded_predicate',
              'kernel_id': receipt['kernel_id'], 'receipts': list(receipt['receipts']),
              'checker_module_sha256': pin['module_sha256'], 'checker_id': pin['identity']['id']}
    return ('passed' if receipt['passed'] else 'failed'), native


# ---------------------------------------------------------------------------
# Explicit inference: exact base snapshot (+ pinned trained adapter) answering a caller-supplied prompt
# ---------------------------------------------------------------------------

def _prompt_file(prompt):
    if type(prompt) is not dict or not {'version', 'system', 'user'} <= set(prompt) \
            or set(prompt) - {'version', 'system', 'user', 'answer_type', 'labels'} or prompt['version'] != 1:
        raise WorkerError('prompt_schema')
    for key in ('system', 'user'):
        if type(prompt[key]) is not str or len(prompt[key]) > D.MAX_TEXT:
            raise WorkerError('prompt_schema')
    if not prompt['user'].strip():
        raise WorkerError('prompt_schema')
    if 'answer_type' in prompt and prompt['answer_type'] not in D.ANSWER_TYPES:
        raise WorkerError('prompt_schema')
    if 'labels' in prompt and (prompt.get('answer_type') != 'label' or type(prompt['labels']) is not list
                               or not 2 <= len(prompt['labels']) <= D.MAX_LABELS
                               or any(type(x) is not str or not x for x in prompt['labels'])):
        raise WorkerError('prompt_schema')
    return prompt


def _dataset_overlap(prompt, dataset, splits, plan):
    """Whether the caller prompt equals (exactly or after normalization) a dataset item, and which split it is in.
    No overlap is NOT novelty: the base model's pretraining data is unknown."""
    if dataset is None and splits is None:
        return {'checked': False, 'novelty': 'not_established'}
    if dataset is None or splits is None:
        raise WorkerError('overlap_needs_dataset_and_splits')
    D.verify_splits(dataset, splits, expected_sha256=plan['splits_sha256'])
    if dataset['dataset_sha256'] != plan['dataset_sha256']:
        raise WorkerError('plan_dataset_mismatch')
    sha = hashlib.sha256(D.canonical([prompt['system'], prompt['user']]).encode('utf-8')).hexdigest()
    norm = D.digest(D._norm(prompt['user']))
    matches = [{'item_id': it['item_id'], 'split': splits['assignments'][it['item_id']],
                'match': 'exact' if it['prompt']['sha256'] == sha else 'normalized_user'}
               for it in dataset['items']
               if it['prompt']['sha256'] == sha or it['grouping']['normalized_prompt'] == norm]
    return {'checked': True, 'dataset_sha256': dataset['dataset_sha256'], 'splits_sha256': splits['splits_sha256'],
            'matches': matches, 'novelty': 'not_established'}


def infer(*, plan, models_root, backend, prompt, out_path, arm='trained', adapter_dir=None,
          adapter_manifest_sha256=None, max_new_tokens=256, dataset=None, splits=None):
    """Answer ONE caller-supplied prompt with the exact pinned base snapshot, plus the pinned trained adapter for
    arm 'trained'. Greedy decoding. Writes an exclusive receipt binding model, checkpoint, options, prompt and output.
    Native verification is not performed here (no contract exists for a free prompt)."""
    D.verify_plan(plan)
    if arm not in D.ARMS:
        raise WorkerError('infer_arm')
    if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 4096:
        raise WorkerError('infer_budget')
    prompt = _prompt_file(prompt)
    if os.path.lexists(out_path):
        raise WorkerError('output_exists')
    ident = _identity(backend, plan)
    model_dir, model = _model(models_root, plan)
    adapter = None
    if arm == 'trained':
        if adapter_manifest_sha256 is None:
            raise WorkerError('adapter_pin_required')
        adapter_dir, digest, manifest = _pinned_adapter(adapter_dir, adapter_manifest_sha256, plan, model)
        adapter = {'manifest_sha256': digest, 'step': manifest['step'], 'identity': manifest['identity'],
                   'files': manifest['files']}
    elif adapter_dir is not None or adapter_manifest_sha256 is not None:
        raise WorkerError('baseline_takes_no_adapter')
    overlap = _dataset_overlap(prompt, dataset, splits, plan)
    try:
        backend.begin(model_dir, plan, resume_dir=None, adapter_dir=adapter_dir if arm == 'trained' else None,
                      trainable=False)
        text = backend.generate({'system': prompt['system'], 'user': prompt['user']}, max_new_tokens)
    finally:
        _close(backend)
    if type(text) is not str:
        raise WorkerError('backend_output')
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        raise WorkerError('backend_output') from None
    structural = 'not_requested'
    if 'answer_type' in prompt:
        item = {'answer_type': prompt['answer_type'], 'labels': prompt.get('labels', [])}
        structural = D.check_output(item, text)
        structural.pop('_value', None)
    opts = plan['options']
    body = {'version': D.VERSION, 'kind': 'inference', 'arm': arm, 'plan_sha256': plan['plan_sha256'],
            'model': {'repo_id': plan['model']['repo_id'], 'revision': plan['model']['revision'],
                      'files_sha256': model['files_sha256']},
            'adapter': adapter, 'backend': ident,
            'options': {'max_new_tokens': max_new_tokens, 'decoding': 'greedy', 'dtype': opts['dtype'],
                        'device': opts['device'], 'seed': opts['seed']},
            'prompt': {'system': prompt['system'], 'user': prompt['user'],
                       'sha256': hashlib.sha256(D.canonical([prompt['system'], prompt['user']])
                                                .encode('utf-8')).hexdigest()},
            'output': {'text': text, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()},
            'structural_check': structural, 'dataset_overlap': overlap,
            'claims': {'quality': 'not_established', 'native_verification': 'not_performed',
                       'promotion': 'never_automatic'}}
    receipt = {**body, 'receipt_sha256': D.digest(body)}
    D.write_json(out_path, receipt, exclusive=True)
    return receipt


def infer_manifest(*, plan_path, prompt_path, out_path, models_root, python, arm='trained', adapter_dir=None,
                   adapter_manifest_sha256=None, max_new_tokens=256, dataset_path=None, splits_path=None):
    """The exact inference command for the operator's runner, as data. Nothing is executed."""
    paths = [plan_path, prompt_path, out_path, models_root, python] + \
        [p for p in (adapter_dir, dataset_path, splits_path) if p is not None]
    for value in paths:
        if type(value) is not str or not os.path.isabs(value) or '\0' in value or '\n' in value:
            raise WorkerError('launch_paths_must_be_absolute')
    plan = D.read_json(plan_path)
    D.verify_plan(plan)
    if arm not in D.ARMS or (arm == 'trained') != (adapter_dir is not None and adapter_manifest_sha256 is not None):
        raise WorkerError('infer_arm')
    argv = [python, os.path.abspath(__file__), 'infer', '--plan', plan_path, '--models-root', models_root,
            '--backend', 'torch-lora', '--prompt', prompt_path, '--out', out_path, '--arm', arm,
            '--max-new-tokens', str(max_new_tokens)]
    if arm == 'trained':
        argv += ['--adapter-dir', adapter_dir, '--adapter-manifest-sha256', adapter_manifest_sha256]
    if dataset_path:
        argv += ['--dataset', dataset_path, '--splits', splits_path]
    return {'version': D.VERSION, 'argv': argv, 'shell': False, 'env': dict(OFFLINE_ENV),
            'plan_sha256': plan['plan_sha256'], 'kind': 'inference', 'admission': 'caller_owned_registered_path'}


# ---------------------------------------------------------------------------
# Real opt-in backend: SFT with a LoRA adapter (torch + transformers + peft), confined to this path
# ---------------------------------------------------------------------------

class TorchLoraBackend:
    """Plain PyTorch loop over a PEFT LoRA model. Local files only, no remote code, safetensors only.

    API verified against transformers 5.18.0 (`from_pretrained(local_files_only, revision, trust_remote_code,
    use_safetensors, dtype)`; `torch_dtype` is a deprecated alias), peft 0.21.2 (`LoraConfig`, `get_peft_model`,
    `PeftModel.from_pretrained(model, model_id, is_trainable=...)`, adapter files `adapter_model.safetensors` and
    `adapter_config.json`) and torch 2.14.1 (`torch.optim.AdamW`, `torch.load(weights_only=True)`).
    One CPU pilot executed four real optimizer steps, a held-out comparison, and baseline/trained
    inference with these pins; see docs/reference/DISTILLATION.md for its limits and measured failures.
    """

    name = 'torch-lora'

    def __init__(self):
        self.mods = None
        self.model = self.tokenizer = self.optimizer = None
        self.plan = None

    def _imports(self):
        if self.mods is not None:
            return self.mods
        os.environ.update(OFFLINE_ENV)
        try:
            import peft
            import safetensors
            import torch
            import transformers
        except ImportError as exc:
            raise BackendUnavailable('missing_package') from exc
        self.mods = {'torch': torch, 'transformers': transformers, 'peft': peft, 'safetensors': safetensors}
        return self.mods

    def versions(self):
        m = self._imports()
        out = {k: getattr(v, '__version__', '?').split('+')[0] for k, v in m.items()}
        try:
            import tokenizers
            out['tokenizers'] = tokenizers.__version__
        except ImportError:
            raise BackendUnavailable('missing_package') from None
        return out

    def identity(self):
        return {'name': self.name, 'version': 1, 'packages': self.versions(),
                'python': '.'.join(map(str, sys.version_info[:3]))}

    def preflight(self, plan):
        if self.versions() != plan['packages']:
            raise BackendUnavailable('package_version_mismatch')
        # V1 checkpoints preserve CPU RNG only; CUDA training/resume is not supported.
        if plan['options']['device'] != 'cpu':
            raise BackendUnavailable('device_unsupported')

    def begin(self, model_dir, plan, *, resume_dir, adapter_dir, trainable):
        from decimal import Decimal
        m = self._imports()
        torch, transformers, peft = m['torch'], m['transformers'], m['peft']
        opts = plan['options']
        self.plan, self.device = plan, opts['device']
        torch.manual_seed(opts['seed'])
        common = {'local_files_only': True, 'trust_remote_code': False}
        try:
            self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_dir, **common)
            base = transformers.AutoModelForCausalLM.from_pretrained(
                model_dir, use_safetensors=True, dtype=getattr(torch, opts['dtype']), **common)
        except Exception as exc:  # noqa: BLE001 - any loader failure is a visible refusal, never a trained result
            raise BackendUnavailable('model_load_failed') from exc
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        base.to(self.device)
        source = resume_dir or adapter_dir
        if source:
            self.model = peft.PeftModel.from_pretrained(base, source, is_trainable=trainable)
        else:
            config = peft.LoraConfig(task_type=peft.TaskType.CAUSAL_LM, r=opts['lora_r'], lora_alpha=opts['lora_alpha'],
                                     lora_dropout=float(Decimal(opts['lora_dropout'])),
                                     target_modules=list(opts['target_modules']), bias='none')
            self.model = peft.get_peft_model(base, config)
        if trainable:
            params = [p for p in self.model.parameters() if p.requires_grad]
            self.optimizer = torch.optim.AdamW(params, lr=float(Decimal(opts['learning_rate'])),
                                               weight_decay=float(Decimal(opts['weight_decay'])))
            if resume_dir:
                saved = torch.load(os.path.join(resume_dir, 'optimizer.pt'), map_location=self.device,
                                   weights_only=True)
                self.optimizer.load_state_dict(saved['optimizer'])
                torch.set_rng_state(saved['cpu_rng'])

    def _prompt(self, row):
        messages = ([{'role': 'system', 'content': row['system']}] if row['system'] else []) + \
            [{'role': 'user', 'content': row['user']}]
        if getattr(self.tokenizer, 'chat_template', None):
            return self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        return (row['system'] + '\n\n' if row['system'] else '') + row['user'] + '\n'

    def _encode(self, row):
        limit = self.plan['options']['max_seq_len']
        prompt = self.tokenizer(self._prompt(row), add_special_tokens=False)['input_ids']
        target = self.tokenizer(row['target'], add_special_tokens=False)['input_ids'] + [self.tokenizer.eos_token_id]
        if len(target) >= limit:
            raise WorkerError('target_exceeds_max_seq_len')
        prompt = prompt[-(limit - len(target)):]          # keep the end of the prompt and the whole target
        return prompt + target, [-100] * len(prompt) + target

    def _batch(self, rows):
        torch = self.mods['torch']
        encoded = [self._encode(r) for r in rows]
        width = max(len(ids) for ids, _ in encoded)
        pad = self.tokenizer.pad_token_id
        ids = [x + [pad] * (width - len(x)) for x, _ in encoded]
        labels = [y + [-100] * (width - len(y)) for _, y in encoded]
        mask = [[1] * len(x) + [0] * (width - len(x)) for x, _ in encoded]
        t = lambda v: torch.tensor(v, dtype=torch.long, device=self.device)  # noqa: E731
        return t(ids), t(mask), t(labels)

    def train_step(self, micro_batches):
        self.model.train()
        total = 0.0
        for rows in micro_batches:
            ids, mask, labels = self._batch(rows)
            loss = self.model(input_ids=ids, attention_mask=mask, labels=labels).loss / len(micro_batches)
            loss.backward()
            total += float(loss.detach())
        self.optimizer.step()
        self.optimizer.zero_grad(set_to_none=True)
        return f'{total:.6f}'

    def eval_loss(self, rows):
        torch = self.mods['torch']
        self.model.eval()
        total = 0.0
        with torch.no_grad():
            for row in rows:
                ids, mask, labels = self._batch([row])
                total += float(self.model(input_ids=ids, attention_mask=mask, labels=labels).loss)
        return f'{total / max(1, len(rows)):.6f}'

    def save(self, folder):
        torch = self.mods['torch']
        self.model.save_pretrained(folder)          # PEFT: adapter_model.safetensors + adapter_config.json
        torch.save({'optimizer': self.optimizer.state_dict(), 'cpu_rng': torch.get_rng_state()},
                   os.path.join(folder, 'optimizer.pt'))

    def generate(self, row, max_new_tokens):
        torch = self.mods['torch']
        self.model.eval()
        enc = self.tokenizer(self._prompt(row), add_special_tokens=False, return_tensors='pt').to(self.device)
        with torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                      pad_token_id=self.tokenizer.pad_token_id)
        return self.tokenizer.decode(out[0][enc['input_ids'].shape[1]:], skip_special_tokens=True)

    def close(self):
        self.model = self.optimizer = None


BACKENDS = {'torch-lora': TorchLoraBackend}


def main(argv=None):
    """Command line: run | infer | checker-identity. Prints canonical JSON; exit 2 on refusal."""
    import argparse
    import json
    parser = argparse.ArgumentParser(prog='symblic/distill/worker.py')
    sub = parser.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--job-dir', required=True)
    r.add_argument('--models-root', required=True)
    r.add_argument('--backend', required=True, choices=sorted(BACKENDS))
    r.add_argument('--adapter-dir')
    i = sub.add_parser('infer')
    for flag in ('--plan', '--models-root', '--prompt', '--out'):
        i.add_argument(flag, required=True)
    i.add_argument('--backend', required=True, choices=sorted(BACKENDS))
    i.add_argument('--arm', default='trained', choices=D.ARMS)
    i.add_argument('--adapter-dir')
    i.add_argument('--adapter-manifest-sha256')
    i.add_argument('--max-new-tokens', type=int, default=256)
    i.add_argument('--dataset')
    i.add_argument('--splits')
    c = sub.add_parser('checker-identity')
    c.add_argument('--name', required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'run':
            result = run(args.job_dir, models_root=args.models_root, backend=BACKENDS[args.backend](),
                         adapter_dir=args.adapter_dir)
        elif args.cmd == 'infer':
            result = infer(plan=D.read_json(args.plan), models_root=args.models_root,
                           backend=BACKENDS[args.backend](), prompt=D.read_json(args.prompt), out_path=args.out,
                           arm=args.arm, adapter_dir=args.adapter_dir,
                           adapter_manifest_sha256=args.adapter_manifest_sha256, max_new_tokens=args.max_new_tokens,
                           dataset=D.read_json(args.dataset) if args.dataset else None,
                           splits=D.read_json(args.splits) if args.splits else None)
            result = {'status': 'completed', **result}
        else:
            result = {'status': 'completed', **checker_identity(args.name)}
    except (WorkerError, D.DistillError) as exc:
        print(json.dumps({'status': 'refused', 'code': exc.code}))
        return 2
    print(D.canonical(result))
    return 0 if result.get('status') == 'completed' else 1


if __name__ == '__main__':
    sys.exit(main())

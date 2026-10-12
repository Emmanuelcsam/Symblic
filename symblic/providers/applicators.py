"""Applicators: the code that carries one Symblic `ask` to a model and brings the reply back.

The kernel never talks to a model itself. For every model call the runner (symblic.kernel.run.Run) hands an
*applicators object* one request dict and expects one reply dict back. Any object with a
``call(request) -> reply`` method works: the tests pass small fakes, and a program that embeds Symblic can pass
its own. This module ships one implementation, ``Applicators``, which needs nothing but this repository and the
Python standard library. It runs three kinds of applicator spec (the spec grammar is parsed by
symblic.kernel.language.parse_applicator: ``engine[:model][@node][+effort][*weight]``):

    ollama:MODEL[@HOST[:PORT]]   One POST /api/generate on an Ollama server over HTTP (https:// also works when
                                 the host entry says so). MODEL is the exact Ollama model name ("qwen3:4b").
                                 The answer's JSON Schema becomes Ollama's `format` (grammar-constrained
                                 decoding); temperature and seed are fixed per sample. Before and after the
                                 request the server's /api/tags is read, so the reply records which manifest
                                 digest the server listed for the model (symblic.providers.ollama_call). With
                                 no @HOST the call goes to a configured host that lists the model.
    command:NAME                 A local program the operator configured as SYMBLIC_COMMAND_<NAME>: the system
                                 text and the prompt go to its stdin, its stdout is the answer. Use it for CLI
                                 coding agents (for example a `claude -p` or `codex exec -` wrapper).
    fake[:LABEL]                 Scripted answers from a FakeApplicators passed as Applicators(fake=...); no
                                 model, no network, no process. Without one, every fake call fails.

Other engine names the language knows (claude, codex, gemini, ...) are refused with a hint: configure the CLI
as a command and write ``command:NAME``, or pass your own applicators object. ``kernel`` never answers an ask.

Configuration (environment variables, read when an Applicators object is made):

    SYMBLIC_OLLAMA_HOSTS     Comma-separated Ollama servers, each ``[name=][http(s)://]host[:port]``.
                             Default: ``127.0.0.1:11434``. Only listed servers are ever contacted: an @HOST in a
                             program must be one of them, by name or by host:port (port 11434 when omitted).
                             Example: ``SYMBLIC_OLLAMA_HOSTS="127.0.0.1:11434,gpu=192.0.2.10:11434"`` lets a
                             program say ``ollama:qwen3:4b@gpu``.
    SYMBLIC_COMMAND_<NAME>   The command line for ``command:<name>`` (NAME upper-cased, any character other than
                             a letter or digit replaced by ``_``). It is split like a shell would split it
                             (shlex) but never run through a shell. Example:
                             ``SYMBLIC_COMMAND_CLAUDE="claude -p --output-format text"``. A name with no such
                             variable is refused: a program can never pick an arbitrary executable.
    SYMBLIC_CALL_WALL_S      The longest one call may take, in seconds (default 1800).
    SYMBLIC_OLLAMA_MAX_CTX   The largest context window (num_ctx, tokens) a call may ask for (default 32768).
    SYMBLIC_OLLAMA_KEEP_ALIVE  Sent as Ollama's keep_alive when set ("0" unloads the model after each call).

What a command receives: stdin is ``SYSTEM`` text, a blank line, then the prompt (the prompt already ends with
the ANSWER FORMAT the kernel expects). The environment is the caller's, plus SYMBLIC_SCHEMA_FILE (a JSON file
holding the answer's JSON Schema), SYMBLIC_EFFORT (the requested effort word, possibly empty) and
SYMBLIC_COMMAND_NAME. The working directory is a fresh empty temporary directory, deleted afterwards. Exit status
0 means success; the reply is read from stdout (JSON is extracted from it by the kernel's own rule).

Request fields the runner sends: app (parsed spec), system, prompt, schema, sample, temperature, seed, effort,
tools, key, stop (a threading.Event), context_manifest, and optionally ollama_limits {num_predict, num_ctx,
timeout_seconds} and deadline (an absolute time.time() for the run's total Ollama budget).

Reply fields: ok, json, text, error, fatal (a retry cannot fix it), refused (no model saw the prompt, so the
call is given back to the run's budget), ms, node, model, usage (what Ollama reported: tokens and milliseconds;
nothing is estimated) and model_identity (symblic.providers.ollama_call's record; 'unavailable' with a reason
for every engine that reports no weight digest).

What this module does not do: it does not place work on a cluster, watch temperatures or memory, queue calls
for capacity, reach browser chat services, or run multi-agent councils. The private system Symblic grew up in
had those (they were part of that host, not of Symblic); they are not in this repository. Nothing runs on
import.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import http.client
import json
import math
import os
import re
import secrets
import shlex
import signal
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import weakref

from symblic.kernel import language as S

DEFAULT_OLLAMA_HOSTS = '127.0.0.1:11434'
OLLAMA_PORT = 11434
CALL_WALL_S = 1800                 # default bound of one call (SYMBLIC_CALL_WALL_S overrides it)
MAX_CTX = 32768                    # default largest num_ctx (SYMBLIC_OLLAMA_MAX_CTX overrides it)
CTX_BUCKETS = (4096, 8192, 16384, 32768, 65536, 131072)
REPLY_ROOM_TOKENS = 4096           # context kept free for the reply when the program sets no num_predict
REPLY_MAX = 32 << 20               # bytes of an HTTP reply or of a command's stdout that are read at most
STDERR_MAX = 64 << 10              # bytes of a command's stderr kept for its error message
REPLY_CHARS = 400_000              # characters of a reply's text kept for the kernel (a Code answer is read from it)
INVENTORY_TTL = 60.0               # seconds an /api/tags listing is reused for placement
CLI_KINDS = ('claude', 'codex', 'agy', 'mistral', 'copilot')     # agent CLIs the language can name
# Why a reply carries no observed weight digest: only an Ollama server lists one.
IDENTITY_REASONS = {'command': 'command_reports_no_weight_digest', 'fake': 'fake_applicator',
                    'kernel': 'kernel_has_no_model'}
_NAME_RX = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]{0,62}')
_HOST_RX = re.compile(r'(?:(?P<scheme>https?)://)?(?P<host>[A-Za-z0-9][A-Za-z0-9.-]{0,252}|\[[0-9A-Fa-f:.]{2,45}\])'
                      r'(?::(?P<port>[0-9]{1,5}))?/?')
_COMMAND_RX = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
_INSTANCES = weakref.WeakSet()     # every Applicators in this process (cancel_everything)
_inventory_lock = threading.Lock()
_inventory = {'key': None, 't': 0.0, 'rows': []}


class ConfigError(ValueError):
    """An environment setting this module cannot use (a malformed host list or command line)."""


# ---------------------------------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------------------------------

def ollama_hosts(text: str | None = None) -> dict:
    """{label: {'base': URL, 'hostport': 'host:port'}} from `text` (default: SYMBLIC_OLLAMA_HOSTS), in order.

    An entry is ``[name=][http(s)://]host[:port]``. Its label is the name, else ``host:port``. Raises ConfigError
    for a malformed entry or a repeated label, so a typo is visible instead of silently ignored."""
    raw = os.environ.get('SYMBLIC_OLLAMA_HOSTS', '') if text is None else text
    raw = raw.strip() or DEFAULT_OLLAMA_HOSTS
    out = {}
    for entry in (part.strip() for part in raw.split(',')):
        if not entry:
            continue
        name, _, address = entry.rpartition('=')
        if name and not _NAME_RX.fullmatch(name):
            raise ConfigError(f'SYMBLIC_OLLAMA_HOSTS: {name!r} is not a usable name (letters, digits, "." and "-")')
        m = _HOST_RX.fullmatch(address)
        port = int(m.group('port')) if m and m.group('port') else OLLAMA_PORT
        if not m or not 0 < port < 65536:
            raise ConfigError(f'SYMBLIC_OLLAMA_HOSTS: {entry!r} is not [name=][http(s)://]host[:port]')
        host = m.group('host').lower()
        hostport = f'{host}:{port}'
        label = name or hostport
        if label in out:
            raise ConfigError(f'SYMBLIC_OLLAMA_HOSTS lists {label!r} twice')
        out[label] = {'base': f'{m.group("scheme") or "http"}://{hostport}', 'hostport': hostport}
    return out


def command_variable(name: str) -> str:
    """The environment variable that configures ``command:<name>``."""
    return 'SYMBLIC_COMMAND_' + re.sub(r'[^A-Za-z0-9]', '_', name).upper()


def command_argv(name: str, environ=None) -> list | None:
    """The argv configured for ``command:<name>``, or None when the operator configured none."""
    if not isinstance(name, str) or not _COMMAND_RX.fullmatch(name):
        return None
    text = (os.environ if environ is None else environ).get(command_variable(name), '')
    if not text.strip():
        return None
    try:
        argv = shlex.split(text)
    except ValueError as e:
        raise ConfigError(f'{command_variable(name)}: {e}') from None
    return argv or None


def configured_commands(environ=None) -> list:
    """The command names configured in the environment (lower case), sorted."""
    env = os.environ if environ is None else environ
    return sorted(key[len('SYMBLIC_COMMAND_'):].lower() for key, value in env.items()
                  if key.startswith('SYMBLIC_COMMAND_') and key != 'SYMBLIC_COMMAND_NAME' and value.strip())


def _int_setting(name: str, default: int, low: int, high: int, environ=None) -> int:
    raw = (os.environ if environ is None else environ).get(name, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f'{name} must be a whole number, not {raw!r}') from None
    if not low <= value <= high:
        raise ConfigError(f'{name} must be from {low} to {high}, not {value}')
    return value


def call_timeout(kind: str = '', environ=None) -> int:
    """The bound of one call, in seconds: SYMBLIC_CALL_WALL_S, default CALL_WALL_S (the same for every kind)."""
    del kind
    return _int_setting('SYMBLIC_CALL_WALL_S', CALL_WALL_S, 1, 7 * 24 * 3600, environ)


# ---------------------------------------------------------------------------------------------------------------
# Records shared by every applicator
# ---------------------------------------------------------------------------------------------------------------

def model_unavailable(provider: str, model: str, reason: str, node=None) -> dict:
    """A model_identity record that observed nothing (symblic.providers.ollama_call's record, version 1)."""
    from symblic.providers import ollama_call as OC
    return OC.unavailable(provider, model, reason, node)


def ollama_format(schema) -> dict:
    """The `format` body of one Ollama request, from the answer's JSON Schema.

    Ollama turns `format` into a decoding grammar and accepts only part of JSON Schema (written against Ollama
    0.9; check newer releases). Local $defs/$ref are inlined, annotations are dropped, a `pattern` is anchored at
    its start (the grammar matches whole strings), and every listed property becomes required with no extra
    properties. Each change only narrows what the model may write; the kernel still checks the answer against
    the full type. Raises ValueError for a schema a grammar cannot express (never a silent fallback to none)."""
    if not isinstance(schema, dict):
        raise ValueError('a structured-output schema must be a JSON object')
    root = copy.deepcopy(schema)
    defs = {}
    for key in ('definitions', '$defs'):
        block = root.pop(key, None)
        if isinstance(block, dict):
            defs.update({'#/' + key + '/' + name: node for name, node in block.items()})

    def clean(value, stack):
        if isinstance(value, bool):
            if not value:
                raise ValueError('a false subschema cannot be expressed as a grammar')
            return {}
        if not isinstance(value, dict):
            raise ValueError('a structured-output schema must be made of JSON Schema objects')
        while isinstance(value.get('$ref'), str):
            ref = value['$ref']
            if ref not in defs or ref in stack:
                raise ValueError('the schema uses a $ref that cannot be inlined')
            value = {**copy.deepcopy(defs[ref]), **{k: v for k, v in value.items() if k != '$ref'}}
            stack = stack | {ref}
        out = {}
        for key, item in value.items():
            if key not in _OLLAMA_KEYWORDS:
                raise ValueError(f'the schema uses {key!r}, which Ollama cannot turn into a grammar')
            if key not in _OLLAMA_ANNOTATIONS:
                out[key] = item
        types = out.get('type')
        if isinstance(types, list):
            rest = {k: v for k, v in out.items() if k != 'type'}
            if not types or any(not isinstance(t, str) or t not in _OLLAMA_TYPES for t in types):
                raise ValueError('the schema has an unsupported type list')
            out = {**rest, 'type': types[0]} if len(types) == 1 else {'anyOf': [{**rest, 'type': t} for t in types]}
        elif types is not None and (not isinstance(types, str) or types not in _OLLAMA_TYPES):
            raise ValueError('the schema has an unsupported type')
        for key in ('anyOf', 'oneOf', 'allOf'):
            if key in out:
                if not isinstance(out[key], list) or not out[key]:
                    raise ValueError(key + ' must be a non-empty list of schemas')
                out[key] = [clean(item, stack) for item in out[key]]
        if 'enum' in out and (not isinstance(out['enum'], list) or
                              any(type(v) not in (str, int, float, bool, type(None)) for v in out['enum'])):
            raise ValueError('the schema has an enum value a grammar cannot express')
        if 'const' in out and type(out['const']) not in (str, int, float, bool, type(None)):
            raise ValueError('the schema has a const value a grammar cannot express')
        for key, kind in (('minLength', int), ('maxLength', int), ('minItems', int), ('maxItems', int),
                          ('minimum', (int, float)), ('maximum', (int, float))):
            if key in out and (isinstance(out[key], bool) or not isinstance(out[key], kind)):
                raise ValueError('the schema has a non-numeric ' + key)
        for key in ('exclusiveMinimum', 'exclusiveMaximum'):
            if key in out and isinstance(out[key], bool):
                raise ValueError('a draft-4 boolean ' + key + ' cannot be expressed as a grammar')
        if 'pattern' in out:
            if not isinstance(out['pattern'], str) or not out['pattern']:
                raise ValueError('the schema has a non-string pattern')
            if not out['pattern'].startswith('^'):
                out['pattern'] = '^' + out['pattern']
        if 'items' in out:
            out['items'] = clean(out['items'], stack)
        if 'required' in out and (not isinstance(out['required'], list) or
                                  any(not isinstance(name, str) for name in out['required'])):
            raise ValueError('required must list property names')
        if 'properties' in out:
            if not isinstance(out['properties'], dict):
                raise ValueError('properties must be a schema object')
            out['properties'] = {name: clean(item, stack) for name, item in out['properties'].items()}
            out['required'] = list(out['properties'])
            out['additionalProperties'] = False
        elif isinstance(out.get('additionalProperties'), dict):
            out['additionalProperties'] = clean(out['additionalProperties'], stack)
        return out

    return clean(root, frozenset())


_OLLAMA_TYPES = frozenset(('object', 'array', 'string', 'number', 'integer', 'boolean', 'null'))
_OLLAMA_ANNOTATIONS = frozenset(('$schema', '$id', '$anchor', '$comment', 'definitions', '$defs', 'title',
                                 'description', 'examples', 'default', 'format', 'deprecated', 'readOnly',
                                 'writeOnly'))
_OLLAMA_KEYWORDS = _OLLAMA_ANNOTATIONS | frozenset((
    '$ref', 'type', 'enum', 'const', 'pattern', 'properties', 'required', 'items', 'additionalProperties',
    'minLength', 'maxLength', 'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'minItems', 'maxItems',
    'allOf', 'anyOf', 'oneOf'))


def context_tokens(chars: int, num_predict=None, cap: int = MAX_CTX) -> int | None:
    """The num_ctx for a prompt of `chars` characters: the smallest bucket that holds about chars/3 tokens, a
    256-token margin and the reply allowance (num_predict, else REPLY_ROOM_TOKENS); None when even `cap` is too
    small. Ollama clips a prompt that does not fit its context without saying so, so a call that would not fit is
    refused instead."""
    need = chars // 3 + 256 + (num_predict if num_predict else REPLY_ROOM_TOKENS)
    sizes = sorted({c for c in CTX_BUCKETS if c < cap} | {cap})
    return next((c for c in sizes if c >= need), None)


# ---------------------------------------------------------------------------------------------------------------
# Fake applicators (tests and dry runs)
# ---------------------------------------------------------------------------------------------------------------

class FakeApplicators:
    """Scripted answers: no model, no network, no process. The tests' own fakes follow the same contract.

    `answer` is one constant answer for every call, or a function ``(label, prompt, request) -> answer``;
    `by_label` maps an applicator label (``fake:a``) to its own answer or function and wins over `answer`. A dict
    answer is returned as the reply's JSON, a text as the reply's text, ``{'__error__': message}`` as a failed
    call and None as "no answer" (a failed call). Every request is kept in ``requests`` (without its stop event),
    so a test can check exactly what the kernel sent."""

    def __init__(self, answer=None, *, by_label=None):
        self.answer = answer
        self.by_label = dict(by_label or {})
        self.requests = []
        self._lock = threading.Lock()

    def call(self, req: dict) -> dict:
        with self._lock:
            self.requests.append({k: v for k, v in req.items() if k != 'stop'})
        label = S.app_label(req['app'])
        out = self.by_label.get(label, self.answer)
        if callable(out):
            out = out(label, req.get('prompt', ''), req)
        if out is None:
            return {'ok': False, 'fatal': True, 'error': f'the fake applicators have no answer for {label}'}
        if isinstance(out, dict) and out.get('__error__'):
            return {'ok': False, 'error': str(out['__error__'])}
        identity = model_unavailable('fake', label, IDENTITY_REASONS['fake'], 'fake')
        if isinstance(out, str):
            return {'ok': True, 'text': out, 'node': 'fake', 'model': label, 'ms': 0, 'model_identity': identity}
        return {'ok': True, 'json': out, 'text': json.dumps(out, ensure_ascii=False, default=str), 'node': 'fake',
                'model': label, 'ms': 0, 'model_identity': identity}


# ---------------------------------------------------------------------------------------------------------------
# The shipped applicators
# ---------------------------------------------------------------------------------------------------------------

class _Cancelled(Exception):
    """A call stopped by its stop event, its deadline, or cancel_all()."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


class Applicators:
    """Runs ``ollama:``, ``command:`` and ``fake`` applicator specs; see the module docstring. Thread-safe: the
    runner may call it from several threads at once (parallel samples).

    owner_label and run_id only label this object (they appear in error messages). thermal, allow_web and avoid
    are accepted so older callers keep working; this implementation has no thermal placement, no web applicators
    and no node blocklist, so they change nothing."""

    def __init__(self, owner_label: str = 'operator', run_id: str = '', *, fake=None, environ=None,
                 thermal=None, allow_web=None, avoid=None):
        del thermal, allow_web, avoid
        self.owner = owner_label
        self.run_id = run_id or 'adhoc'
        # every setting is read once, here, from one environment (os.environ unless a test passes its own)
        self.environ = dict(os.environ if environ is None else environ)
        self.hosts = ollama_hosts(self.environ.get('SYMBLIC_OLLAMA_HOSTS', ''))
        self.call_wall = call_timeout(environ=self.environ)
        self.max_ctx = _int_setting('SYMBLIC_OLLAMA_MAX_CTX', MAX_CTX, 512, 1 << 21, self.environ)
        keep = self.environ.get('SYMBLIC_OLLAMA_KEEP_ALIVE', '').strip()
        self.keep_alive = (int(keep) if re.fullmatch(r'-?[0-9]+', keep) else keep) if keep else None
        self.fake = fake if fake is None or hasattr(fake, 'call') else FakeApplicators(fake)
        self._lock = threading.Lock()
        self._inflight = {}                 # host label -> calls this object has running there
        self._live = set()                  # open HTTP connections and running command processes
        _INSTANCES.add(self)

    # -- dispatch ---------------------------------------------------------------------------------------------
    def call(self, req: dict) -> dict:
        app = req['app']
        engine = app.get('engine')
        started = time.monotonic()
        t0 = time.time()
        try:
            if engine == 'ollama':
                out = self._ollama(req, started)
            elif engine == 'command':
                out = self._command(req, started)
            elif engine == 'fake':
                out = self.fake.call(req) if self.fake is not None else {
                    'ok': False, 'fatal': True,
                    'error': 'no fake answers were given (Applicators(fake=...)); fake calls fail on purpose'}
            elif engine == 'kernel':
                out = {'ok': False, 'fatal': True, 'error': 'the kernel does not answer asks'}
            else:
                out = {'ok': False, 'fatal': True, 'refused': True,
                       'error': (f'{engine} has no applicator in this package: configure its command line as '
                                 f'{command_variable(engine)} and write "command:{engine}", or pass your own '
                                 'applicators object (symblic/providers/README.md)')}
        except ConfigError as e:
            out = {'ok': False, 'fatal': True, 'refused': True, 'error': str(e)}
        except Exception as e:  # noqa: BLE001  (an applicator failing is reported, never raised)
            out = {'ok': False, 'error': f'{engine}: {type(e).__name__}: {e}'}
        out.setdefault('ms', int((time.time() - t0) * 1000))
        out.setdefault('usage', {})
        if 'model_identity' not in out:
            reason = IDENTITY_REASONS.get(engine, 'provider_reports_no_weight_digest') if out.get('ok') \
                else 'call_failed'
            out['model_identity'] = model_unavailable(engine or 'unknown', app.get('model') or engine or '', reason,
                                                      out.get('node'))
        return out

    def _seconds_left(self, req: dict, started: float) -> float:
        """The time this call may still take: the wall bound, the program's per-call Ollama limit and the run's
        total Ollama deadline, whichever ends first."""
        bounds = [self.call_wall]
        limits = req.get('ollama_limits') or {}
        if req['app'].get('engine') == 'ollama' and limits.get('timeout_seconds') is not None:
            bounds.append(float(limits['timeout_seconds']))
        if req.get('deadline') is not None:
            bounds.append(req['deadline'] - time.time() + (time.monotonic() - started))
        return min(bounds) - (time.monotonic() - started)

    @staticmethod
    def _out_of_time(req: dict) -> dict:
        total = req.get('deadline') is not None and req['deadline'] <= time.time()
        return {'ok': False, 'refused': True, 'fatal': total,
                'error': 'the call has no time left in its budget' + (' (the run\'s total Ollama time is spent)'
                                                                     if total else '')}

    # -- Ollama over HTTP -----------------------------------------------------------------------------------------
    def _ollama(self, req: dict, started: float) -> dict:
        from symblic.providers import ollama_call as OC
        app = req['app']
        model = (app.get('model') or '').strip()
        if not model:
            return {'ok': False, 'fatal': True, 'refused': True, 'error': 'ollama needs a model: "ollama:qwen3:4b"'}
        stop = req.get('stop')
        if stop is not None and stop.is_set():
            return {'ok': False, 'fatal': True, 'refused': True, 'error': 'stopped'}
        picked = self._ollama_host(app.get('node') or '', model)
        if 'error' in picked:
            return picked
        label, base = picked['label'], picked['base']
        left = self._seconds_left(req, started)
        if left < 1:
            return self._out_of_time(req)
        limits = req.get('ollama_limits') or {}
        try:
            fmt = ollama_format(req['schema']) if req.get('schema') is not None else None
        except ValueError as e:
            return {'ok': False, 'fatal': True, 'refused': True, 'node': label,
                    'error': f'ollama@{label}: the answer type cannot be sent as a grammar: {e}'}
        cap = min(self.max_ctx, limits['num_ctx']) if limits.get('num_ctx') else self.max_ctx
        chars = len(req.get('system') or '') + len(req.get('prompt') or '')
        num_ctx = context_tokens(chars, limits.get('num_predict'), cap)
        if num_ctx is None:
            return {'ok': False, 'fatal': True, 'refused': True, 'node': label,
                    'error': (f'ollama@{label}: the prompt (about {chars // 3} tokens) and its reply allowance do '
                              f'not fit a context of {cap} tokens; Ollama would cut the prompt silently')}
        options = {'temperature': _plain(req.get('temperature'), 0), 'seed': int(_plain(req.get('seed'), 7)),
                   'num_ctx': num_ctx}
        if limits.get('num_predict'):
            options['num_predict'] = int(limits['num_predict'])
        body = {'model': model, 'system': req.get('system') or '', 'prompt': req.get('prompt') or '',
                'stream': False, 'options': options}
        if fmt is not None:
            body['format'] = fmt
        if self.keep_alive is not None:
            body['keep_alive'] = self.keep_alive
        nonce = secrets.token_hex(16)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), OC._NoRedirect())
        before = OC.observe(opener, base, model, min(OC.TAGS_TIMEOUT, left / 10))
        if before['error'] == 'not_listed':
            return {'ok': False, 'fatal': True, 'refused': True, 'node': label,
                    'error': f'ollama@{label}: {model} is not installed there (ollama pull {model})'}
        if before['error'] in ('listing_unreachable', 'listing_timeout'):
            return {'ok': False, 'refused': True, 'node': label,
                    'error': f'ollama@{label}: the server did not answer ({before["error"]})'}
        self._hold(label, +1)
        try:
            status, raw = self._post(base, '/api/generate', body, self._seconds_left(req, started), stop)
        except _Cancelled as c:
            spent = req.get('deadline') is not None and req['deadline'] <= time.time()
            return {'ok': False, 'node': label, 'fatal': c.why == 'stopped' or spent,
                    'error': f'ollama@{label}: {c.why}'}
        except (OSError, http.client.HTTPException) as e:
            return {'ok': False, 'node': label, 'error': f'ollama@{label}: {type(e).__name__}: {e}'}
        finally:
            self._hold(label, -1)
        try:
            reply = json.loads(raw)
        except ValueError:
            reply = None
        if not 200 <= status < 300 or not isinstance(reply, dict):
            why = reply.get('error') if isinstance(reply, dict) else raw[:300].decode('utf-8', 'replace')
            return {'ok': False, 'node': label, 'fatal': status in (400, 404),
                    'error': f'ollama@{label}: HTTP {status}: {str(why)[:300]}'}
        after = OC.observe(opener, base, model, min(OC.TAGS_TIMEOUT, max(0.0, self._seconds_left(req, started))))
        observation = {'version': OC.VERSION, 'model': model, 'nonce': nonce, 'before': before, 'after': after,
                       'response_model': reply['model'][:200] if isinstance(reply.get('model'), str) else None}
        identity = OC.identity(observation, model, label, OC.observer_sha256(), nonce)
        text = reply.get('response') if isinstance(reply.get('response'), str) else ''
        meta = {'determinism': {'temperature': options['temperature'], 'seed': options['seed'], 'num_ctx': num_ctx},
                'done_reason': reply.get('done_reason'), 'usage_source': 'ollama_reply'}
        evidence = {'usage': OC.usage(reply), 'model_identity': identity, 'meta': meta, 'node': label,
                    'model': model}
        if not text.strip():
            return {'ok': False, 'error': f'ollama@{label}: empty answer', **evidence}
        return {'ok': True, 'json': S.extract_json(text), 'text': text[:REPLY_CHARS], **evidence}

    def _ollama_host(self, node: str, model: str) -> dict:
        """{'label', 'base'} of the configured server a call goes to, or a refusal reply."""
        if node:
            if node in self.hosts:
                return {'label': node, 'base': self.hosts[node]['base']}
            host, _, port = node.partition(':')
            wanted = f'{host.lower()}:{port or OLLAMA_PORT}'
            for label, row in self.hosts.items():
                if row['hostport'] == wanted:
                    return {'label': label, 'base': row['base']}
            return {'ok': False, 'fatal': True, 'refused': True,
                    'error': (f'ollama@{node}: that server is not in SYMBLIC_OLLAMA_HOSTS '
                              f'({", ".join(self.hosts)}); add it there to use it')}
        label = self.pick_node('ollama', model)
        return {'label': label, 'base': self.hosts[label]['base']}

    def pick_node(self, kind: str = 'ollama', model: str = '', avoid: str = '') -> str:
        """The configured Ollama host for a call that names none: among the hosts whose listing has `model` (all
        hosts when no listing could be read), the one with the fewest of this object's calls in flight, then the
        first in SYMBLIC_OLLAMA_HOSTS order. Only configured hosts are ever chosen."""
        del kind
        labels = list(self.hosts)
        if len(labels) > 1 and model:
            names = {model, model + ':latest'} if ':' not in model.rsplit('/', 1)[-1] else {model}
            have = {row['node'] for row in self.inventory(self.hosts) if row['model'] in names}
            labels = [label for label in labels if label in have] or labels
        if avoid and len(labels) > 1:
            labels = [label for label in labels if label != avoid] or labels
        with self._lock:
            return min(labels, key=lambda label: (self._inflight.get(label, 0), labels.index(label)))

    def _hold(self, label: str, delta: int) -> None:
        with self._lock:
            self._inflight[label] = max(0, self._inflight.get(label, 0) + delta)

    @staticmethod
    def inventory(hosts=None) -> list:
        """[{'node', 'model', 'bytes'}] from every configured Ollama host's /api/tags (cached INVENTORY_TTL
        seconds). A host that does not answer contributes nothing."""
        hosts = ollama_hosts() if hosts is None else hosts
        key = tuple((label, row['base']) for label, row in hosts.items())
        with _inventory_lock:
            if _inventory['key'] == key and time.monotonic() - _inventory['t'] < INVENTORY_TTL:
                return list(_inventory['rows'])
        from symblic.providers import ollama_call as OC
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), OC._NoRedirect())
        rows = []
        for label, row in hosts.items():
            try:
                with opener.open(urllib.request.Request(row['base'] + '/api/tags'), timeout=OC.TAGS_TIMEOUT) as r:
                    tags = json.loads(r.read(OC.TAGS_MAX + 1))
            except Exception:  # noqa: BLE001  (an unreachable host lists nothing)
                continue
            for item in (tags.get('models') or []) if isinstance(tags, dict) else []:
                if isinstance(item, dict) and isinstance(item.get('name'), str):
                    rows.append({'node': label, 'model': item['name'], 'bytes': item.get('size')})
        with _inventory_lock:
            _inventory.update(key=key, t=time.monotonic(), rows=rows)
        return list(rows)

    def _post(self, base: str, path: str, body: dict, seconds: float, stop) -> tuple:
        """(HTTP status, body bytes) of one POST. A stop, the deadline or cancel_all() closes the connection,
        which also tells Ollama to stop generating."""
        if seconds < 1:
            raise _Cancelled('no time left in the call budget')
        scheme, _, hostport = base.partition('://')
        maker = http.client.HTTPSConnection if scheme == 'https' else http.client.HTTPConnection
        conn = maker(hostport, timeout=seconds)
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        result = {}

        def work():
            try:
                conn.request('POST', path, body=data, headers={'Content-Type': 'application/json'})
                response = conn.getresponse()
                raw = response.read(REPLY_MAX + 1)
                if len(raw) > REPLY_MAX:
                    raise OSError(f'the reply exceeded {REPLY_MAX} bytes')
                result['status'], result['raw'] = response.status, raw
            except BaseException as e:  # noqa: BLE001  (re-raised in the caller's thread)
                result['error'] = e

        with self._lock:
            self._live.add(conn)
        worker = threading.Thread(target=work, name='symblic-ollama-call', daemon=True)
        end = time.monotonic() + seconds
        try:
            worker.start()
            while worker.is_alive():
                worker.join(0.2)
                why = ('stopped' if stop is not None and stop.is_set() else
                       f'timed out after {int(seconds)} s' if time.monotonic() > end else
                       'cancelled' if conn not in self._live else None)
                if why and worker.is_alive():
                    _close(conn)
                    worker.join(5)
                    raise _Cancelled(why)
            if conn not in self._live:          # cancel_all() closed it just as the reply ended
                raise _Cancelled('cancelled')
        finally:
            with self._lock:
                self._live.discard(conn)
            _close(conn)
        if 'error' in result:
            if isinstance(result['error'], TimeoutError):     # the socket's own timeout: the same as the deadline
                raise _Cancelled(f'timed out after {int(seconds)} s')
            if isinstance(result['error'], (OSError, http.client.HTTPException)):
                raise result['error']
            raise OSError(f'{type(result["error"]).__name__}: {result["error"]}')
        return result['status'], result['raw']

    # -- a configured local command -------------------------------------------------------------------------------
    def _command(self, req: dict, started: float) -> dict:
        app = req['app']
        name = (app.get('model') or '').strip()
        if app.get('node'):
            return {'ok': False, 'fatal': True, 'refused': True,
                    'error': f'command:{name} runs on this machine; remove "@{app["node"]}" from the spec'}
        argv = command_argv(name, self.environ)
        if argv is None:
            return {'ok': False, 'fatal': True, 'refused': True,
                    'error': (f'command:{name} is not configured: set {command_variable(name or "NAME")} to its '
                              'command line (symblic/providers/README.md)')}
        stop = req.get('stop')
        if stop is not None and stop.is_set():
            return {'ok': False, 'fatal': True, 'refused': True, 'error': 'stopped'}
        left = self._seconds_left(req, started)
        if left < 1:
            return self._out_of_time(req)
        text = (req.get('system') or '') + '\n\n' + (req.get('prompt') or '')
        with tempfile.TemporaryDirectory(prefix='symblic-command-', ignore_cleanup_errors=True) as work:
            schema_file = os.path.join(work, '.symblic-schema.json')
            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(req.get('schema'), f, ensure_ascii=False)
            env = {**self.environ, 'SYMBLIC_SCHEMA_FILE': schema_file, 'SYMBLIC_EFFORT': str(req.get('effort') or ''),
                   'SYMBLIC_COMMAND_NAME': name}
            try:
                code, out, err = self._run(argv, text.encode('utf-8'), work, env, left, stop)
            except _Cancelled as c:
                return {'ok': False, 'node': 'local', 'fatal': c.why == 'stopped', 'error': f'command:{name}: {c.why}'}
            except OSError as e:
                return {'ok': False, 'fatal': True, 'refused': True, 'node': 'local',
                        'error': f'command:{name} could not start: {e}'}
        reply = out.decode('utf-8', 'replace')
        if code != 0:
            tail = err.decode('utf-8', 'replace').strip()[-400:]
            return {'ok': False, 'node': 'local', 'error': f'command:{name} exited with status {code}: {tail}'}
        if not reply.strip():
            return {'ok': False, 'node': 'local', 'error': f'command:{name} printed no answer'}
        return {'ok': True, 'json': S.extract_json(reply), 'text': reply[:REPLY_CHARS], 'node': 'local',
                'model': name}

    def _run(self, argv: list, body: bytes, cwd: str, env: dict, seconds: float, stop) -> tuple:
        """(exit status, stdout, stderr tail) of one command in its own process group, bounded in time and
        output. A stop, the deadline or cancel_all() ends the whole group."""
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=cwd, env=env, start_new_session=True)
        chunks = {'out': [], 'err': []}
        sizes = {'out': 0, 'err': 0}
        overflow = []

        def feed():
            try:
                proc.stdin.write(body)
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except (OSError, ValueError):
                    pass

        def drain(stream, key, cap):
            while True:
                block = stream.read1(1 << 16) if hasattr(stream, 'read1') else stream.read(1 << 16)
                if not block:
                    return
                sizes[key] += len(block)
                chunks[key].append(block)
                if key == 'out' and sizes[key] > cap:
                    overflow.append(True)
                    return
                if key == 'err':                      # keep only the tail of stderr
                    joined = b''.join(chunks[key])[-cap:]
                    chunks[key] = [joined]

        threads = [threading.Thread(target=feed, daemon=True),
                   threading.Thread(target=drain, args=(proc.stdout, 'out', REPLY_MAX), daemon=True),
                   threading.Thread(target=drain, args=(proc.stderr, 'err', STDERR_MAX), daemon=True)]
        with self._lock:
            self._live.add(proc)
        end = time.monotonic() + seconds
        try:
            for t in threads:
                t.start()
            while True:
                try:
                    proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                why = ('stopped' if stop is not None and stop.is_set() else
                       f'timed out after {int(seconds)} s' if time.monotonic() > end else
                       f'printed more than {REPLY_MAX} bytes' if overflow else
                       'cancelled' if proc not in self._live else None)
                if why:
                    _kill_group(proc)
                    raise _Cancelled(why)
            if proc not in self._live:          # cancel_all() ended it: its exit status is not an answer
                raise _Cancelled('cancelled')
            if stop is not None and stop.is_set():
                raise _Cancelled('stopped')
            for t in threads[1:]:
                t.join(max(0.1, end - time.monotonic()))
            if overflow:
                raise _Cancelled(f'printed more than {REPLY_MAX} bytes')
            return proc.returncode, b''.join(chunks['out']), b''.join(chunks['err'])
        finally:
            with self._lock:
                self._live.discard(proc)
            if proc.poll() is None:
                _kill_group(proc)
            for stream in (proc.stdout, proc.stderr):
                try:
                    stream.close()
                except OSError:
                    pass

    # -- cancellation -----------------------------------------------------------------------------------------------
    def cancel_all(self) -> int:
        """End every call this object has in flight (open connections are closed, command groups killed); each
        such call returns a failed reply. Returns how many were ended."""
        with self._lock:
            live, self._live = list(self._live), set()
        for item in live:
            if isinstance(item, subprocess.Popen):
                _kill_group(item)
            else:
                _close(item)
        return len(live)


def _plain(value, default):
    """A finite JSON number for Ollama's options (an exact Fraction becomes a float)."""
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return int(number) if number == int(number) and not isinstance(value, float) else number


def _close(conn) -> None:
    """Close an HTTP connection from another thread: shutting the socket down first wakes a blocked read."""
    sock = getattr(conn, 'sock', None)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    try:
        conn.close()
    except OSError:
        pass


def _kill_group(proc) -> None:
    """End a command's whole process group: SIGTERM, then SIGKILL after two seconds."""
    for sig, wait in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def cancel_everything() -> int:
    """End the in-flight calls of every Applicators in this process (see Applicators.cancel_all)."""
    return sum(apps.cancel_all() for apps in list(_INSTANCES))


def install_sigterm() -> None:
    """For a long-lived process (a benchmark, a background job): on SIGTERM end this process's in-flight calls,
    then exit with status 128 + the signal number."""

    def on_term(signum, _frame):
        try:
            cancel_everything()
        finally:
            os._exit(128 + signum)
    signal.signal(signal.SIGTERM, on_term)


def engines_status(probe: bool = False) -> dict:
    """What the shipped applicators can reach, for a status page or a command line. Without `probe` nothing is
    contacted; with it every configured Ollama host's /api/tags is read once."""
    try:
        hosts = ollama_hosts()
        problem = ''
    except ConfigError as e:
        hosts, problem = {}, str(e)
    rows = Applicators.inventory(hosts) if probe and hosts else []
    out = {'ollama': {'title': S.ENGINE_TITLES.get('ollama', 'Ollama'), 'installed': bool(hosts),
                      'hosts': {label: row['base'] for label, row in hosts.items()},
                      'models': sorted({(r['node'], r['model']) for r in rows}), 'probed': bool(probe),
                      'note': problem},
           'command': {'title': S.ENGINE_TITLES.get('command', 'command'), 'installed': True,
                       'commands': configured_commands()},
           'fake': {'title': S.ENGINE_TITLES.get('fake', 'fake'), 'installed': True,
                    'note': 'answers only when given FakeApplicators'}}
    for kind in CLI_KINDS + ('chatgpt', 'gemini', 'council'):
        out[kind] = {'title': S.ENGINE_TITLES.get(kind, kind), 'installed': False,
                     'note': 'not shipped: run its CLI as a command (command:NAME)'}
    return out


def main(argv=None) -> int:
    """``python3 -m symblic.providers.applicators [--probe]``: print what the configuration reaches."""
    import argparse
    parser = argparse.ArgumentParser(prog='python3 -m symblic.providers.applicators',
                                     description='Show the Ollama hosts and commands Symblic is configured to use.')
    parser.add_argument('--probe', action='store_true', help='read each Ollama host\'s /api/tags once')
    args = parser.parse_args(argv)
    print(json.dumps(engines_status(probe=args.probe), indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

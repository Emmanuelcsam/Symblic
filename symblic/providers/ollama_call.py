"""Which model weights answered an Ollama call: an observation around the request, and its checked record.

Used by symblic.providers.applicators for every `ollama:` call, and by the kernel runner
(symblic.kernel.run) to re-check the records saved in a run folder. It answers one question
honestly: which manifest digest did the server list for the requested model name just before
and just after the /api/generate request? A model name is never a digest.

Two ways to observe a call:

* In process (what Applicators does): ``observe()`` reads the server's /api/tags, the request
  runs, ``observe()`` reads it again, and ``identity()`` turns the two reads into a record. The
  observer is this file, so the record carries its SHA-256 (``observer_sha256()``) and a fresh
  random nonce that never leaves this process.
* As a standalone wrapper around an existing curl command (``main``), for a launcher that runs
  the request in another process or on another machine::

      python3 -I -S ollama_call.py --model NAME --base URL --timeout SECONDS --nonce HEX -- /usr/bin/curl ...

  It reads /api/tags, runs that curl as a child, reads /api/tags again and prints curl's reply
  with one added field, FIELD, holding both reads and the nonce. The nonce exists only in the
  launcher's argv and plan, never in the request, so a field a server or model puts in a reply
  cannot pass for this observation. curl's stdout is read up to REPLY_MAX; anything else curl
  printed passes through untouched with curl's exit status. Stdlib only; loopback base URLs only;
  no proxies, no redirects; a listing counts only from a 2xx answer.

The record side (identity, unavailable, check, usage) is pure. Statuses: 'observed' (the same
exact listing and digest at both reads), 'drift' (the listing changed during the call) and
'unavailable' (not read, not listed, malformed, or another run's or another model's
observation). This is evidence, not attestation: the digests are what the server listed when
asked; a server that loads other blobs than it lists, or a change and change-back between the
two reads, would not be seen. ``usage()`` copies the token and time counters Ollama itself
reported; a counter it did not send stays absent.

Nothing runs on import.
"""

from __future__ import annotations

# A copy run on its own (python3 -I -S ollama_call.py ...) stays stdlib-only; imported from the package it
# records its import identity like every other registered module (symblic.kernel.identity).
if __name__ != '__main__':
    try:
        _symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
    except ModuleNotFoundError as _symblic_identity_missing:
        if _symblic_identity_missing.name not in ('symblic', 'symblic.kernel', 'symblic.kernel.identity'):
            raise
    else:
        _symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

VERSION = 1
FIELD = 'symblic_model_identity'         # the observation the standalone wrapper adds to the reply
SOURCE = 'ollama_api_tags_bracket'
SCOPE = ("Manifest digest that the Ollama server's /api/tags listed for this exact model name immediately "
         'before and after the /api/generate request, read by the observer that made the request. '
         'Server-reported evidence, not a cryptographic attestation: it does not prove which weight blobs '
         'the server loaded, and a change and change-back between the two reads would not be seen.')
STATUSES = ('observed', 'drift', 'unavailable')
KEYS = ('version', 'provider', 'model', 'digest', 'status', 'source', 'scope', 'resolved', 'node',
        'before', 'after', 'response_model', 'reason', 'observer_sha256')
CURL = '/usr/bin/curl'
TAGS_TIMEOUT = 5.0                       # a loopback listing answers in milliseconds
TAGS_MAX = 8 << 20
REPLY_MAX = 32 << 20                     # curl's stdout kept by the wrapper; more fails the run (63)
MARGIN = 3.0                             # finish before the unit's own `timeout` fires
USAGE_FIELDS = (('prompt_eval_count', 'input_tokens', 1), ('eval_count', 'output_tokens', 1),
                ('total_duration', 'duration_ms', 10**6), ('load_duration', 'load_ms', 10**6),
                ('prompt_eval_duration', 'prompt_ms', 10**6), ('eval_duration', 'eval_ms', 10**6))
_BASE = re.compile(r'http://(127\.0\.0\.1|localhost|\[::1\]):\d{2,5}')
_MODEL = re.compile(r'[A-Za-z0-9._:/@+-]{1,120}')
_DIGEST = re.compile(r'(?:sha256:)?([0-9a-f]{64})')
_HEX = re.compile(r'[0-9a-f]{64}')
_NONCE = re.compile(r'[0-9a-f]{32}')
_ERROR = re.compile(r'[a-z0-9_]{1,40}')
_REASON = re.compile(r'[a-z0-9_:. ]{1,200}')


# ---------------------------------------------------------------- shared rules (pure)

def candidates(model: str) -> list:
    """The listed names a request for `model` resolves to: itself, or itself plus ':latest' when
    its last path part has no tag (a registry port or namespace is not a tag)."""
    return [model] if ':' in model.rsplit('/', 1)[-1] else [model, model + ':latest']


def digest_of(raw) -> str | None:
    """'sha256:<64 hex>' from a listed digest, or None. Never derived from a name."""
    m = _DIGEST.fullmatch(raw) if isinstance(raw, str) else None
    return 'sha256:' + m.group(1) if m else None


def pick(tags, model: str) -> tuple:
    """(listed name, digest, error) for `model` in an /api/tags reply; exact names only."""
    rows = tags.get('models') if isinstance(tags, dict) else None
    if not isinstance(rows, list):
        return None, None, 'no_model_list'
    for name in candidates(model):
        hits = [r for r in rows if isinstance(r, dict) and name in (r.get('name'), r.get('model'))]
        if not hits:
            continue
        digests = {digest_of(r.get('digest')) for r in hits}
        if len(digests) != 1:
            return name, None, 'ambiguous_listing'
        found = digests.pop()
        return (name, found, None) if found else (name, None, 'no_valid_digest')
    return None, None, 'not_listed'


def _side(raw) -> dict | None:
    """One read, as printed: a listed name and digest, or an error code (and possibly the name)."""
    if not isinstance(raw, dict) or set(raw) != {'at_ms', 'name', 'digest', 'error'}:
        return None
    at, name, found, error = raw['at_ms'], raw['name'], raw['digest'], raw['error']
    if type(at) is not int or at < 0 or (found is None) == (error is None):
        return None
    if name is not None and not (isinstance(name, str) and _MODEL.fullmatch(name)):
        return None
    if found is not None and (digest_of(found) != found or name is None):
        return None
    if error is not None and not (isinstance(error, str) and _ERROR.fullmatch(error)):
        return None
    return {'at_ms': at, 'name': name, 'digest': found, 'error': error}


def _observation(raw) -> dict | None:
    if not isinstance(raw, dict) or set(raw) != {'version', 'model', 'nonce', 'before', 'after', 'response_model'}:
        return None
    if raw['version'] != VERSION or type(raw['version']) is not int:
        return None
    model, nonce, response = raw['model'], raw['nonce'], raw['response_model']
    before, after = _side(raw['before']), _side(raw['after'])
    if not (isinstance(model, str) and _MODEL.fullmatch(model)) or before is None or after is None:
        return None
    if not (isinstance(nonce, str) and _NONCE.fullmatch(nonce)):
        return None
    if response is not None and not (isinstance(response, str) and len(response) <= 200):
        return None
    return {'model': model, 'nonce': nonce, 'before': before, 'after': after, 'response_model': response}


def unavailable(provider: str, model: str, reason: str, node: str | None = None) -> dict:
    """The record for a call whose weights were not observed: no digest, the reason says why."""
    return {'version': VERSION, 'provider': str(provider or 'unknown')[:40], 'model': str(model or '')[:200],
            'digest': None, 'status': 'unavailable', 'source': 'none', 'scope': SCOPE, 'resolved': None,
            'node': node or None, 'before': None, 'after': None, 'response_model': None,
            'reason': str(reason)[:200], 'observer_sha256': None}


def identity(observation, model: str, node: str | None = None, observer_sha256: str | None = None,
             nonce: str | None = None) -> dict:
    """The model_identity record for one Ollama call, from its observation.

    observer_sha256 and nonce are what the caller fixed before the call (the observer's source
    hash and a fresh random nonce that never went into the request): without both, nothing in
    the observation is evidence. Then: observed (the same exact listing and digest before and
    after; digest set), drift (the listing changed; digest None, both reads kept), or
    unavailable (not read, not listed, malformed, another run's or another model's).
    """
    out = unavailable('ollama', model, 'observer_not_documented', node)
    if not (isinstance(observer_sha256, str) and _HEX.fullmatch(observer_sha256)
            and isinstance(nonce, str) and _NONCE.fullmatch(nonce)):
        return out
    out['observer_sha256'] = observer_sha256
    if observation is None:
        return {**out, 'reason': 'not_observed'}
    obs = _observation(observation)
    if obs is None:
        return {**out, 'reason': 'malformed_observation'}
    if obs['nonce'] != nonce:
        return {**out, 'reason': 'observation_not_from_this_run'}
    if obs['model'] != model:
        return {**out, 'reason': 'observation_names_another_model'}
    return _judge(obs['before'], obs['after'], obs['response_model'], model, node, observer_sha256)


def _judge(before: dict, after: dict, response_model, model: str, node, observer_sha256: str) -> dict:
    """The record two validated reads of this run's own observer make for `model` (deterministic)."""
    out = {**unavailable('ollama', model, 'malformed_observation', node), 'observer_sha256': observer_sha256}
    names = candidates(model)
    if any(read['name'] is not None and read['name'] not in names for read in (before, after)):
        return out                                   # the observer never lists another model's name
    out.update(source=SOURCE, before=before, after=after, response_model=response_model, reason=None)
    if before['digest'] is None or after['digest'] is None:
        side, read = ('before', before) if before['digest'] is None else ('after', after)
        return {**out, 'resolved': before['name'] or after['name'], 'reason': f"{side}: {read['error']}"}
    if before['name'] != after['name'] or before['digest'] != after['digest']:
        return {**out, 'status': 'drift',
                'reason': 'listed_name_changed' if before['name'] != after['name'] else 'digest_changed_during_call'}
    if response_model not in (None, model, before['name']):
        return {**out, 'resolved': before['name'], 'reason': 'reply_names_another_model'}
    return {**out, 'status': 'observed', 'digest': before['digest'], 'resolved': before['name']}


def check(record) -> dict | None:
    """A copy of a model_identity record this module would itself have made, else None.

    A record with an observation is rebuilt from its own reads (the observer's hash and an exact
    listing of its model at both reads are required) and must match exactly, so status, digest,
    reason and reads can never contradict each other. A record without one says unavailable and
    carries no digest, reads, listing or reply name.
    """
    if not isinstance(record, dict) or set(record) != set(KEYS) or type(record['version']) is not int \
            or record['version'] != VERSION or record['scope'] != SCOPE or record['status'] not in STATUSES:
        return None
    if not (isinstance(record['provider'], str) and 0 < len(record['provider']) <= 40
            and isinstance(record['model'], str) and len(record['model']) <= 200):
        return None
    if record['node'] is not None and not (isinstance(record['node'], str) and 0 < len(record['node']) <= 200):
        return None
    sha = record['observer_sha256']
    if sha is not None and not (isinstance(sha, str) and _HEX.fullmatch(sha)):
        return None
    if record['source'] == SOURCE:
        before, after = _side(record['before']), _side(record['after'])
        response = record['response_model']
        if record['provider'] != 'ollama' or sha is None or before is None or after is None \
                or not _MODEL.fullmatch(record['model']) \
                or response is not None and not (isinstance(response, str) and len(response) <= 200):
            return None
        rebuilt = _judge(before, after, response, record['model'], record['node'], sha)
        return json.loads(json.dumps(record)) if rebuilt == record else None
    if record['source'] != 'none' or record['status'] != 'unavailable':
        return None
    if any(record[key] is not None for key in ('digest', 'resolved', 'before', 'after', 'response_model')):
        return None
    if not (isinstance(record['reason'], str) and _REASON.fullmatch(record['reason'])):
        return None
    return json.loads(json.dumps(record))


def observer_sha256() -> str:
    """SHA-256 of this file's bytes, read once: the observer behind an in-process observation."""
    if 'sha256' not in _observer:
        import hashlib
        with open(__file__, 'rb') as source:
            _observer['sha256'] = hashlib.sha256(source.read()).hexdigest()
    return _observer['sha256']


_observer: dict = {}


def usage(reply) -> dict:
    """What Ollama itself reported for one call; a counter it did not send is left out, not zero."""
    out = {}
    for src, dst, scale in USAGE_FIELDS:
        value = reply.get(src) if isinstance(reply, dict) else None
        if type(value) is int and value >= 0:
            out[dst] = value // scale
    return out


# ---------------------------------------------------------------- the observer (in process or standalone)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):     # never follow a listing elsewhere
        return None


def observe(opener, base: str, model: str, timeout: float) -> dict:
    """One /api/tags read: {'at_ms','name','digest','error'}. Only a 2xx answer is a listing."""
    at = int(time.time() * 1000)
    if timeout <= 0.2:
        return {'at_ms': at, 'name': None, 'digest': None, 'error': 'no_time_left'}
    try:
        response = opener.open(urllib.request.Request(base + '/api/tags'), timeout=timeout)
        with response:
            status = getattr(response, 'status', None)
            if not isinstance(status, int) or not 200 <= status < 300:
                return {'at_ms': at, 'name': None, 'digest': None, 'error': 'listing_http_error'}
            raw = response.read(TAGS_MAX + 1)
        if len(raw) > TAGS_MAX:
            return {'at_ms': at, 'name': None, 'digest': None, 'error': 'listing_too_large'}
        tags = json.loads(raw)
    except urllib.error.HTTPError as e:                # an error status, whatever its body says
        e.close()
        code = e.code if isinstance(e.code, int) and 100 <= e.code <= 599 else None
        return {'at_ms': at, 'name': None, 'digest': None,
                'error': f'listing_http_{code}' if code else 'listing_http_error'}
    except ValueError:
        return {'at_ms': at, 'name': None, 'digest': None, 'error': 'listing_not_json'}
    except Exception as e:  # noqa: BLE001  (a failed read is recorded; it never stops the call)
        reason = getattr(e, 'reason', e)
        timed_out = isinstance(e, TimeoutError) or isinstance(reason, TimeoutError) or 'timed out' in str(e)
        return {'at_ms': at, 'name': None, 'digest': None,
                'error': 'listing_timeout' if timed_out else 'listing_unreachable'}
    name, found, error = pick(tags, model)
    return {'at_ms': at, 'name': name, 'digest': found, 'error': error}


def run_bounded(argv: list, timeout: float, cap: int | None = None) -> tuple:
    """(exit status, stdout, why) of argv; stderr passes through. Past `timeout` the child is killed
    and reaped: status 28 (curl's own time-out code), why 'timeout'. Past `cap` bytes of stdout, the
    same with 63 (curl's size-limit code) and 'too_large'. The output is then empty: a partial reply
    is no reply. why is None when the child ended by itself."""
    cap = REPLY_MAX if cap is None else cap
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    chunks, size, over = [], [0], [False]

    def pump():
        while True:
            block = child.stdout.read1(1 << 16)
            if not block:
                return
            size[0] += len(block)
            if size[0] > cap:
                over[0] = True
                return
            chunks.append(block)
    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    deadline = time.monotonic() + max(0.1, timeout)
    reader.join(max(0.0, deadline - time.monotonic()))
    if not reader.is_alive() and not over[0]:
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    if reader.is_alive() or over[0] or child.poll() is None:
        child.kill()
        child.wait()
        child.stdout.close()
        reader.join(5)
        return (63, b'', 'too_large') if over[0] else (28, b'', 'timeout')
    child.stdout.close()
    return child.returncode, b''.join(chunks), None


def _arguments(argv: list) -> dict | None:
    if '--' not in argv:
        return None
    head, curl = argv[:argv.index('--')], argv[argv.index('--') + 1:]
    if len(head) != 8 or head[0::2] != ['--model', '--base', '--timeout', '--nonce']:
        return None
    model, base, timeout, nonce = head[1], head[3], head[5], head[7]
    if not _MODEL.fullmatch(model) or not _BASE.fullmatch(base) or not timeout.isdigit() or int(timeout) < 1 \
            or not _NONCE.fullmatch(nonce):
        return None
    # only the generate request against the same loopback server, exactly as the launcher builds it
    if not curl or curl[0] != CURL or curl[-1] != base + '/api/generate':
        return None
    return {'model': model, 'base': base, 'timeout': int(timeout), 'nonce': nonce, 'curl': curl}


def main(argv=None) -> int:
    started = time.monotonic()
    args = _arguments(list(sys.argv[1:] if argv is None else argv))
    if args is None:
        sys.stderr.write('ollama_call: expected --model NAME --base LOOPBACK --timeout S --nonce HEX -- '
                         f'{CURL} ... BASE/api/generate\n')
        return 2
    deadline = started + max(1.0, args['timeout'] - MARGIN)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    before = observe(opener, args['base'], args['model'], min(TAGS_TIMEOUT, args['timeout'] / 10))
    try:
        code, out, why = run_bounded(args['curl'], deadline - time.monotonic())
    except OSError as e:
        sys.stderr.write(f'ollama_call: cannot start curl: {e}\n')
        return 2
    if why is not None:
        sys.stderr.write('ollama_call: ' + ('the generate request ran out of time\n' if why == 'timeout' else
                                                   f'the reply exceeded {REPLY_MAX} bytes; curl was stopped\n'))
        return code
    if code != 0:
        sys.stdout.buffer.write(out)
        return code
    try:
        reply = json.loads(out)
    except ValueError:
        reply = None
    if not isinstance(reply, dict):
        sys.stdout.buffer.write(out)                 # the run's parser decides, as with bare curl
        return 0
    after = observe(opener, args['base'], args['model'], min(TAGS_TIMEOUT, started + args['timeout'] - 1 -
                                                             time.monotonic()))
    reply[FIELD] = {'version': VERSION, 'model': args['model'], 'nonce': args['nonce'], 'before': before,
                    'after': after,
                    'response_model': reply['model'][:200] if isinstance(reply.get('model'), str) else None}
    sys.stdout.write(json.dumps(reply, ensure_ascii=True, separators=(',', ':')) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())

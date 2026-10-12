"""HOST-ONLY: typed requests to ChatGPT or Gemini web chat through the original host's browser agents.

What it did: the `chatgpt` and `gemini` applicators. A Symblic `ask` became one tool-free typed prompt that
the host's browser-automation runtime (integrations/chatgpt-browser/chatgpt.js plus typed-requests.cjs,
installed on a node under ~/.local/share/host-web-agents/) typed into a signed-in browser session, and the
reply came back as one JSON receipt. No account calls or workers on import. The node token/profile never
leaves its machine. A persisted dispatch may only be observed, never automatically replayed.

What a host must provide: the browser runtime on each node, `host_agent_hub` (runs a command on a node and
names the host's data folder), `host_browser_hub` (registered browser nodes and the per-node browser hold),
`host_council_run.member_env` (the environment for a local browser run) and `host_apps` (store locks). None of
these, nor the browser runtime, is part of this repository.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import threading
import time

VERSION = 1
TERMINAL = {'completed', 'refused', 'failed', 'cancelled', 'unknown'}
NODE_ENTRY = r'''const fs=require('fs');const path=require('path');
const raw=fs.readFileSync(0,'utf8');if(Buffer.byteLength(raw)>500000)throw new Error('Typed envelope too large');
const envelope=JSON.parse(raw),refused=envelope.operation==='start'?{accepted:false}:{};
const file=path.join(require('os').homedir(),'.local/share/host-web-agents/app/integrations/chatgpt-browser/chatgpt.js');
if(!fs.existsSync(file)){process.stdout.write(JSON.stringify({ok:false,...refused,error:'The selected node has no web runtime. Install it through Browser > Machine.'})+'\n');process.exit(0);}
const app=require(file);
if(app.TYPED_VERSION!==1||typeof app.typedCLI!=='function'){process.stdout.write(JSON.stringify({ok:false,...refused,error:'The installed runtime does not support typed-proposal v1. Update it through the admitted idle runtime installer.'})+'\n');process.exit(0);}
if(app.TYPED_SOURCE_SHA256!==envelope.source_sha256){process.stdout.write(JSON.stringify({ok:false,...refused,error:'The installed typed-browser source differs from this controller. Update only through the idle admitted installer.'})+'\n');process.exit(0);}
app.typedCLI(envelope).then(result=>process.stdout.write(JSON.stringify(result)+'\n')).catch(error=>{process.stdout.write(JSON.stringify({ok:false,error:String(error.message).slice(0,1600)})+'\n');process.exitCode=1;});'''
LOCAL_ENTRY = NODE_ENTRY.replace("path.join(require('os').homedir(),'.local/share/host-web-agents/app/integrations/chatgpt-browser/chatgpt.js')",
                               'process.argv[1]')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def source_hash():
    folder = Path(__file__).parent / 'integrations/chatgpt-browser'
    return hashlib.sha256((folder / 'chatgpt.js').read_bytes() + (folder / 'typed-requests.cjs').read_bytes()).hexdigest()


def _atomic(path, value):
    import secrets
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix('.' + secrets.token_hex(6) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(encode(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def transport(node, operation, request):
    """Fixed code and registered transport only; all owner text travels on stdin."""
    if os.environ.get('DASH_TEST') == '1':
        raise RuntimeError('Real browser transport is disabled in isolated tests; inject a fake transport.')
    body = encode({'operation': operation, 'request': request, 'source_sha256': source_hash()})
    timeout = 125 if operation == 'start' else 25
    if node == 'host':
        from host_council_run import member_env
        executable = shutil.which('node') or '/usr/bin/node'
        result = subprocess.run([executable, '-e', LOCAL_ENTRY,
                                 str(Path(__file__).parent / 'integrations/chatgpt-browser/chatgpt.js')],
                                input=body, text=True, capture_output=True, timeout=timeout, check=False, env=member_env())
    else:
        import host_agent_hub
        # This path is reached only after the durable browser hold/fence boundary.
        script = 'export XDG_RUNTIME_DIR="/run/user/$(id -u)"; node -e ' + shlex.quote(NODE_ENTRY)
        result = host_agent_hub._on_node(node, script, timeout=timeout, stdin=body)
    if len(result.stdout or '') > 4_000_000:
        raise ValueError('The browser transport exceeded its bounded reply size; delivery is unknown.')
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError('The browser transport did not return one protocol receipt; delivery is unknown.') from exc
    if not isinstance(value, dict):
        raise ValueError('The browser transport returned an invalid receipt; delivery is unknown.')
    return value


def admit(node):
    if node != 'host':
        import host_browser_hub
        if host_browser_hub.web_node(node) != node:
            raise ValueError('Select an exact registered browser node.')
        # Reuses the same persisted hold, install exclusion and admission epoch as
        # the sign-in path. Completion of one prompt cannot release the daemon.
        host_browser_hub._hold(node, 'browser')


def _body(req, run_id):
    app = req.get('app') or {}
    site, node = app.get('engine'), app.get('node') or 'host'
    if site not in ('chatgpt', 'gemini') or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', node) or node in ('auto', 'nodes'):
        raise ValueError('Choose ChatGPT/Gemini and one exact registered browser device.')
    model = app.get('model') or ''
    if type(model) is not str or model and not re.fullmatch(r'[\w.-]{1,60}', model):
        raise ValueError('Use an exact model identifier supported by the selected browser account.')
    if req.get('effort') or app.get('effort'):
        raise ValueError('The typed browser adapter cannot independently enforce reasoning effort; choose an actual account model/mode instead.')
    if type(req.get('system')) is not str or type(req.get('prompt')) is not str:
        raise ValueError('Explicit system and prompt text are required.')
    prompt = req['system'] + '\n\n' + req['prompt']
    if req.get('schema') is not None:
        prompt += '\n\nReturn exactly one JSON object matching this schema: ' + encode(req['schema'])
    prompt += '\nReply with the JSON object only. No project tools or command execution are available in this request.'
    if '\0' in prompt or len(prompt.encode('utf-16-le')) // 2 > 100000:
        raise ValueError('The complete typed browser prompt exceeds 100000 UTF-16 code units or contains NUL; it was not sent.')
    key = digest({'run_id': run_id, 'key': req.get('key'), 'site': site, 'node': node,
                  'model': model, 'prompt': prompt, 'sample': req.get('sample', 0)})[:32]
    return node, {'id': key, 'site': site, 'model': model, 'fullPrompt': prompt}


def call(req, *, run_id, root=None, send=None, admission=None, check_host=True, poll_seconds=2):
    """One stable identity. Reconnect observes its node receipt, never sends again."""
    import host_apps
    from symblic.kernel import language as S
    node, body = _body(req, run_id)
    if check_host:
        from symblic.autogen.runner import execution_fence as host_check
        host_check()
    if root is None:
        import host_agent_hub
        root = Path(host_agent_hub._data()) / 'typed-browser'
    root = Path(root)
    file = root / (body['id'] + '.json')
    send, admission = send or transport, admission or admit
    stop = req.get('stop') or threading.Event()
    reference = {'id': body['id'], 'sha256': digest(body)}
    expected_source = source_hash()
    def save(row, *, initial=False):
        row['updated'] = time.time()
        if initial:
            _atomic(file, row); return row
        with host_apps.store_lock(str(file)):
            current = json.loads(file.read_text())
            if current.get('reply') is not None and current.get('status') in TERMINAL - {'unknown'}:
                return current
            _atomic(file, row); return row
    with host_apps.store_lock(str(file)):
        if file.exists():
            row = json.loads(file.read_text())
            if row.get('version') != VERSION or row.get('sha256') != reference['sha256'] or row.get('node') != node:
                raise ValueError('The retained typed-browser request is invalid; nothing will be replayed.')
            fresh = False
            if row.get('reply') is not None and row.get('status') in TERMINAL - {'unknown'}:
                if row['status'] == 'completed' and row['reply'].get('meta', {}).get('protocol_source_sha256') != expected_source:
                    return {'ok': False, 'fatal': True, 'error': 'This retained answer used a different browser protocol source. Inspect it as historical evidence; it will not be replayed or adopted as a current result.', 'node': node}
                return row['reply']
        else:
            row = {'version': VERSION, **reference, 'node': node, 'site': body['site'], 'model': body['model'],
                   'status': 'prepared', 'created': time.time(), 'run_id': run_id}
            save(row, initial=True); fresh = True
    # A reconnect may resolve an earlier unknown observation. Do not carry that
    # old reply into a newly completed state before the final reply is recorded.
    row.pop('reply', None)
    def finish(reply, status):
        row.update(status=status, reply=reply); saved = save(row); return saved.get('reply', reply)
    try:
        if fresh:
            if stop.is_set():
                return finish({'ok': False, 'fatal': True, 'accepted': False, 'error': 'Stopped before browser admission.'}, 'cancelled')
            try:
                admission(node)
            except Exception as exc:
                return finish({'ok': False, 'fatal': True, 'accepted': False, 'error': str(exc)[:1600]}, 'refused')
            row['status'] = 'dispatching'; save(row)
            operation = 'start'
            envelope = send(node, 'start', body)
        else:
            operation = 'status'
            envelope = send(node, 'status', reference)
        while True:
            if envelope.get('ok') is not True:
                not_admitted = operation == 'start' and envelope.get('accepted') is False
                return finish({'ok': False, 'fatal': True, 'accepted': False if not_admitted else None,
                    'error': str(envelope.get('error') or 'Browser outcome is unknown.')[:1600],
                    'node': node, 'meta': {'typed_request': reference}},
                    'refused' if not_admitted else 'unknown')
            if envelope.get('protocol') != VERSION or envelope.get('source_sha256') != expected_source:
                raise ValueError('The typed browser protocol was not proven; delivery is unknown.')
            receipt = envelope.get('request')
            if (not isinstance(receipt, dict) or receipt.get('id') != reference['id'] or receipt.get('sha256') != reference['sha256']
                    or receipt.get('site') != body['site'] or receipt.get('model') != body['model']
                    or receipt.get('source_sha256') != expected_source):
                raise ValueError('The browser receipt did not match this exact request, site and model.')
            row['receipt'] = receipt; row['status'] = receipt.get('status'); save(row)
            if receipt.get('status') in TERMINAL:
                meta = {'typed_request': reference, 'status': receipt['status'], 'newChat': True, 'tools': 'none',
                        'protocol_source_sha256': receipt.get('source_sha256'),
                        'modelSelection': receipt.get('modelSelection'), 'providerCompletion': receipt.get('providerCompletion')}
                if receipt['status'] == 'completed':
                    text = receipt.get('response')
                    if type(text) is not str or len(text) > 1000000:
                        raise ValueError('The retained typed reply is invalid.')
                    return finish({'ok': True, 'text': text, 'json': S.extract_json(text), 'node': node,
                                   'model': body['model'] or body['site'], 'meta': meta}, 'completed')
                return finish({'ok': False, 'fatal': True, 'accepted': receipt.get('accepted'),
                               'error': receipt.get('error') or 'The browser request did not complete.', 'node': node, 'meta': meta}, receipt['status'])
            if receipt.get('status') not in ('queued', 'running', 'cancelling'):
                raise ValueError('The browser returned an unknown request state.')
            if stop.wait(poll_seconds):
                operation = 'cancel'
                envelope = send(node, 'cancel', reference)
            else:
                operation = 'status'
                envelope = send(node, 'status', reference)
    except Exception as exc:
        # The hold is intentionally untouched. Only existing browser reconciliation
        # can prove daemon/unit/cgroup termination, even if this process goes away.
        return finish({'ok': False, 'fatal': True, 'error': str(exc)[:1600], 'node': node,
                       'meta': {'typed_request': reference, 'status': 'unknown', 'hold_retained': node != 'host'}}, 'unknown')

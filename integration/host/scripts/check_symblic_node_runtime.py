#!/usr/bin/env python3
"""HOST-ONLY: probes the terminal agent installed on a worker node of the original host by install_symblic_node.py.

What it checks: that the node's installed agent command line (a third-party open-source terminal agent; its
real package name is replaced by the placeholder `agentcli` in this copy, including the `agentcli.hooks`
import below) still accepts the flags and tool protocol the host's implementer lane relied on. It is an
offline contract probe; no accounts or real model calls.

Runs the node's actual CLI with the native implementer flags against a temporary
loopback OpenAI fixture. XDG config/data/state, logs, workspace and cache are
isolated; HOME is unchanged. A Python startup audit guard rejects connections
except to that exact fixture port. The fixture requests one real save tool call
inside its temporary workspace and then the native complete tool. No shell tool
call is requested. This proves CLI/transport/tool compatibility, not model quality.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

MODEL = 'symblic-fixture-qwen'
CONTENT = 'Symblic installed-runtime fixture passed.\n'
PROMPT = 'Create symblic_runtime_fixture.txt with the exact fixture content. SYMBLIC_INTACT_PROMPT_20261006'
TOOLS = 'save,append,patch,shell,read'
DISCRETE_TOOLS = 'save,append,shell,read'
SOURCE_DIGEST = 'a' * 64
ALIAS_DIGEST = 'b' * 64
BLOB_DIGEST = 'c' * 64
ALIAS = 'symblic-ctx8192-' + SOURCE_DIGEST + ':latest'
LARGE_READ_CONTENT = ''.join(f'CONTEXT_PRESSURE_{index:04d} temporary fixture data for the native read tool.\n'
                             for index in range(1600)) + 'SYMBLIC_LARGE_READ_FINISHED\n'


def probe(executable: str, *, timeout: int = 90, system: str | None = None,
          local_wrapper: str | None = None, agentcli_python: str | None = None,
          overflow: bool = False, mutate_owner: bool = False,
          build_handoff: bool = False, prose_continue: bool = False,
          context_handoff: bool = False, discrete_budget: bool = False,
          complete_at_budget: bool = False, complete_after_elapsed: bool = False) -> dict:
    executable = shutil.which(executable) or executable
    if not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise ValueError('Installed agentcli executable is unavailable')
    if (overflow or mutate_owner or build_handoff or prose_continue or context_handoff or discrete_budget
            or complete_at_budget or complete_after_elapsed) and not local_wrapper:
        raise ValueError('Context and handoff probes require the managed local wrapper')
    if sum((overflow, mutate_owner, build_handoff, prose_continue, context_handoff,
            complete_at_budget, complete_after_elapsed)) > 1:
        raise ValueError('Exercise each refusal, handoff or completion-boundary probe separately')
    if discrete_budget and not (overflow or mutate_owner):
        raise ValueError('The explicit discrete budget option is for overflow or mutation refusal probes')
    if local_wrapper and (not Path(local_wrapper).is_file() or not agentcli_python
                          or not Path(agentcli_python).is_file() or not Path(agentcli_python).is_absolute()):
        raise ValueError('Managed probe requires the wrapper script and absolute installed Python path')
    expected_model = ALIAS if local_wrapper else MODEL
    completion_boundary = complete_at_budget or complete_after_elapsed
    discrete = build_handoff or prose_continue or context_handoff or discrete_budget or completion_boundary
    selected_tools = DISCRETE_TOOLS if discrete else TOOLS
    prompt = PROMPT + (' ' + 'bounded-context-fixture ' * 1800 if overflow else '')
    fixture = {'alias_created': False, 'resident': set()}
    requests: list[dict] = []
    errors: list[str] = []
    started = time.monotonic()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_json(self, payload, code=200):
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            requests.append({'method': 'GET', 'path': self.path})
            if local_wrapper and self.path == '/api/tags':
                models = [{'name': MODEL, 'model': MODEL, 'digest': SOURCE_DIGEST, 'size': 1048576}]
                if fixture['alias_created']:
                    models.append({'name': ALIAS, 'model': ALIAS, 'digest': ALIAS_DIGEST, 'size': 1048576})
                self.send_json({'models': models})
                return
            if local_wrapper and self.path == '/api/ps':
                self.send_json({'models': [{'name': name, 'model': name} for name in sorted(fixture['resident'])]})
                return
            if self.path != '/v1/models':
                errors.append('Unexpected GET route')
                self.send_json({'error': 'unexpected fixture route'}, 404)
                return
            self.send_json({'object': 'list', 'data': [{'id': MODEL, 'object': 'model',
                'owned_by': 'symblic-offline-fixture', 'context_length': 16384}]})

        def do_POST(self):
            count = int(self.headers.get('Content-Length', '0'))
            if not 0 < count <= 500000:
                self.send_json({'error': 'invalid fixture payload length'}, 413)
                return
            body = json.loads(self.rfile.read(count))
            if local_wrapper and self.path.startswith('/api/'):
                requests.append({'method': 'POST', 'path': self.path, 'body': body})
                if self.path == '/api/show' and body.get('model') in (MODEL, ALIAS):
                    alias = body['model'] == ALIAS
                    if alias and not fixture['alias_created']:
                        self.send_json({'error': 'model not found'}, 404)
                        return
                    context = 8192 if alias else 4096
                    self.send_json({'modelfile': f'FROM /models/blobs/sha256-{BLOB_DIGEST}\nPARAMETER num_ctx {context}\nPARAMETER temperature 0.6',
                        'parameters': f'num_ctx {context}\ntemperature 0.6', 'template': '{{ .Prompt }}',
                        'model_info': {'general.architecture': 'qwen3', 'qwen3.context_length': 32768},
                        'capabilities': ['completion', 'tools'], 'details': {'family': 'qwen3'}})
                    return
                if self.path == '/api/create' and body == {'model': ALIAS, 'from': MODEL, 'parameters': {'num_ctx': 8192}, 'stream': False}:
                    fixture['alias_created'] = True
                    # Treat both as resident so explicit unload is exercised, without any actual model.
                    fixture['resident'].update((MODEL, ALIAS))
                    self.send_json({'status': 'success'})
                    return
                if self.path == '/api/generate' and body.get('model') in (MODEL, ALIAS) and body.get('keep_alive') == 0 and set(body) <= {'model', 'keep_alive', 'stream'}:
                    fixture['resident'].discard(body['model'])
                    self.send_json({'model': body['model'], 'done': True, 'done_reason': 'unload'})
                    return
                errors.append('Unexpected Ollama metadata or unload payload')
                self.send_json({'error': 'fixture only permits metadata and explicit unload'}, 400)
                return
            row = {'method': 'POST', 'path': self.path, 'model': body.get('model'),
                   'stream': bool(body.get('stream')), 'max_tokens': body.get('max_tokens'),
                   'tools': [t.get('function', {}).get('name') for t in body.get('tools', [])],
                   'prompt_intact': any(prompt in str(m.get('content', ''))
                                        for m in body.get('messages', []) if m.get('role') == 'user'),
                   'message_roles': [m.get('role') for m in body.get('messages', [])]}
            if prose_continue or context_handoff or completion_boundary:
                owners = [str(m.get('content', '')) for m in body.get('messages', [])
                          if m.get('role') == 'user' and prompt in str(m.get('content', ''))]
                row['owner_sha256'] = hashlib.sha256(owners[0].encode()).hexdigest() if owners else None
                row['continuation_notes'] = [str(m.get('content', '')) for m in body.get('messages', [])
                                             if m.get('role') == 'user' and prompt not in str(m.get('content', ''))]
            requests.append(row)
            if self.path != '/v1/chat/completions' or body.get('model') != expected_model:
                errors.append('Wrong model or POST route')
                self.send_json({'error': 'unexpected fixture model or route'}, 400)
                return
            turn = sum(r['method'] == 'POST' and bool(r.get('tools')) for r in requests)
            if turn > (4 if prose_continue else 2) or sum(r['path'] == '/v1/chat/completions' for r in requests) > 6:
                errors.append('Unexpected extra model request')
                self.send_json({'error': 'fixture turn limit'}, 400)
                return
            function = ({'name': 'save', 'arguments': json.dumps({
                'path': 'symblic_runtime_fixture.txt', 'content': CONTENT})} if turn == (3 if prose_continue else 1)
                else {'name': 'complete', 'arguments': '{}'})
            if context_handoff and turn == 2:
                function = {'name': 'read', 'arguments': json.dumps({'path': 'context_pressure_fixture.txt'})}
            tool_call = {'id': f'fixture-tool-{turn}', 'type': 'function', 'function': function}
            agent_turn = bool(body.get('tools'))
            prose_turn = prose_continue and agent_turn and turn <= 2
            tool_turn = agent_turn and not prose_turn
            message = ({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]}
                       if tool_turn else {'role': 'assistant', 'content': (
                           'I will inspect the workspace and plan the requested change before editing.' if turn == 1
                           else 'The requested file is still missing. I need to create it and verify the exact contents.'
                       ) if prose_turn else 'Symblic fixture'})
            if prose_continue or context_handoff or completion_boundary:
                row['fixture_reply'] = 'prose' if prose_turn else function['name'] if tool_turn else 'helper'
            if complete_after_elapsed and tool_turn and function['name'] == 'complete':
                # The final provider call began within budget. Let its valid complete
                # response cross the deadline, as an actual slow generation can do.
                delay_started = time.monotonic()
                time.sleep(10.2)
                row['complete_reply_delay_seconds'] = round(time.monotonic() - delay_started, 3)
            finish = 'tool_calls' if tool_turn else 'stop'
            if body.get('stream'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                delta = dict(message)
                if tool_turn:
                    delta['tool_calls'] = [dict(tool_call, index=0)]
                chunks = [
                    {'id': 'fixture-chat', 'object': 'chat.completion.chunk', 'created': 1, 'model': expected_model,
                     'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                    {'id': 'fixture-chat', 'object': 'chat.completion.chunk', 'created': 1, 'model': expected_model,
                     'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}],
                     'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}},
                ]
                for chunk in chunks:
                    self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
            else:
                self.send_json({'id': 'fixture-chat', 'object': 'chat.completion', 'created': 1,
                    'model': expected_model, 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}})

    with tempfile.TemporaryDirectory(prefix='symblic-runtime-fixture-') as temp:
        root = Path(temp)
        workspace = root / 'workspace'
        workspace.mkdir()
        if context_handoff:
            (workspace / 'context_pressure_fixture.txt').write_text(LARGE_READ_CONTENT)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        port = server.server_address[1]
        guard_dir = root / 'guard'
        guard_dir.mkdir()
        # Runs inside the installed Python interpreter without replacing any agentcli code.
        (guard_dir / 'sitecustomize.py').write_text('''import os, sys
from pathlib import Path
root = Path(os.environ["SYMBLIC_FIXTURE_ROOT"]).resolve()
port = int(os.environ["SYMBLIC_FIXTURE_PORT"])
(root / "guard-loaded").write_text("yes")
def audit(event, args):
    if event == "socket.connect":
        addr = args[1]
        if not isinstance(addr, tuple) or addr[0] != "127.0.0.1" or addr[1] != port:
            with (root / "blocked-network").open("a") as handle:
                handle.write("blocked\\n")
            raise PermissionError("Offline Symblic fixture permits only its loopback provider")
    elif event == "socket.getaddrinfo" and args[0] not in ("127.0.0.1", b"127.0.0.1"):
        with (root / "blocked-network").open("a") as handle:
            handle.write("blocked DNS\\n")
        raise PermissionError("Offline Symblic fixture disables external DNS")
sys.addaudithook(audit)
if os.environ.get("SYMBLIC_FIXTURE_MUTATE_OWNER") == "1":
    from agentcli.hooks import HookType, register_hook
    def mutate_first_owner(manager):
        if not (root / "hook-mutated").exists():
            for i, msg in enumerate(manager.log.messages):
                if msg.role == "user":
                    manager.log.messages[i] = msg.replace(content="Changed objective from temporary test hook.")
                    (root / "hook-mutated").write_text("Native TURN_PRE changed the first user message")
                    break
        yield from ()
    register_hook("symblic_fixture_first_owner_mutation", HookType.TURN_PRE,
                  mutate_first_owner, priority=10000)
''')
        env = {key: os.environ[key] for key in ('HOME', 'USER', 'LOGNAME', 'PATH', 'LANG') if key in os.environ}
        env['PATH'] = str(Path(executable).parent) + os.pathsep + env.get('PATH', '/usr/bin:/bin')
        env.update({
            'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_DATA_HOME': str(root / 'data'),
            'XDG_STATE_HOME': str(root / 'state'), 'XDG_CACHE_HOME': str(root / 'cache'),
            'AGENTCLI_LOGS_HOME': str(root / 'logs'), 'AGENTCLI_WORKSPACE': str(workspace),
            'AGENTCLI_NO_LOCAL_DISCOVERY': '1', 'AGENTCLI_TELEMETRY_ENABLED': '0',
            'AGENTCLI_TIKTOKEN_TIMEOUT': '0', 'AGENTCLI_HOOK_ALLOWLIST': 'cwd_changed,cwd_awareness',
            'AGENTCLI_MAX_STEPS': '6' if discrete else '3', 'AGENTCLI_LLM_MAX_RETRIES': '1', 'AGENTCLI_TEST_MAX_RETRIES': '0',
            'AGENTCLI_OPENAI_RESPONSES_API': '0', 'OPENAI_API_KEY': 'ollama',
            'OPENAI_BASE_URL': f'http://127.0.0.1:{port}/v1',
            'OPENAI_API_BASE': f'http://127.0.0.1:{port}/v1',
            'PYTHONPATH': str(guard_dir), 'PYTHONDONTWRITEBYTECODE': '1',
            'SYMBLIC_FIXTURE_ROOT': temp, 'SYMBLIC_FIXTURE_PORT': str(port),
            'SYMBLIC_FIXTURE_MUTATE_OWNER': '1' if mutate_owner else '0',
            'TMPDIR': str(root / 'tmp'), 'NO_COLOR': '1', 'TERM': 'dumb',
        })
        if local_wrapper:
            env.update({'SYMBLIC_AGENTCLI_PYTHON': agentcli_python,
                        'SYMBLIC_AGENTCLI_ALIAS_ROOT': str(root / 'aliases'),
                        'TRIAD_OLLAMA_URL': f'http://127.0.0.1:{port}'})
        if discrete:
            env['SYMBLIC_AGENTCLI_BUILD_STEPS'] = '1' if build_handoff else '2' if complete_at_budget else '6'
            env['SYMBLIC_AGENTCLI_BUILD_SECONDS'] = '10' if complete_after_elapsed else '600'
        Path(env['TMPDIR']).mkdir()
        config = Path(env['XDG_CONFIG_HOME']) / 'agentcli'
        config.mkdir(parents=True)
        (config / 'config.toml').write_text('[env]\nAGENTCLI_DING = "false"\nAGENTCLI_TOOL_SOUNDS = "false"\n')
        argv = [executable, '-n', '--name', 'pipeline-symblic-runtime-fixture', '-w', str(workspace),
                '-m', 'local/' + MODEL, '-t', selected_tools, '--tool-format', 'tool',
                '--no-workspace', '--output-format', 'text']
        if system:
            argv += ['--system', system]
        argv.append(prompt)
        if local_wrapper:
            node = shutil.which('node')
            if not node:
                raise ValueError('Installed Node.js is unavailable')
            argv = [node, str(Path(local_wrapper).resolve()), *argv[1:]]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        result = None
        listing = None
        try:
            listing = subprocess.run([executable, 'models', 'list', '--provider', 'local', '--json'],
                cwd=workspace, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
            result = subprocess.run(argv, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            errors.append('Installed CLI timed out')
            output = exc.stdout or ''
            if isinstance(output, bytes):
                output = output.decode(errors='replace')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        if result is not None:
            output = result.stdout + ('\n' + result.stderr if result.stderr else '')
        artifact = workspace / 'symblic_runtime_fixture.txt'
        artifact_ok = artifact.is_file() and artifact.read_text() == CONTENT
        chats = [r for r in requests if r['method'] == 'POST' and r.get('tools')]
        helper_requests = sum(r['path'] == '/v1/chat/completions' and not r.get('tools') for r in requests)
        expected_tools = set(selected_tools.split(','))
        checks = {
            'cli_exit_zero': result is not None and result.returncode == 0,
            'startup_network_guard_loaded': (root / 'guard-loaded').is_file(),
            'no_other_network_attempts': not (root / 'blocked-network').exists(),
            'models_route_called': any(r['path'] == '/v1/models' for r in requests),
            'model_listing_exit_zero': listing is not None and listing.returncode == 0 and MODEL in listing.stdout,
            'two_agent_chat_completions': len(chats) == 2,
            'exact_selected_model': all(r.get('model') == expected_model for r in chats) and bool(chats),
            ('four_discrete_tools_exposed' if discrete else 'five_native_tools_exposed'):
                bool(chats) and all(expected_tools <= set(row['tools']) for row in chats),
            'original_prompt_intact': bool(chats) and chats[0]['prompt_intact'],
            'actual_save_tool_wrote_exact_file': artifact_ok,
            'tool_result_returned': len(chats) == 2 and 'tool' in chats[1]['message_roles'],
            'no_fixture_protocol_errors': not errors,
        }
        if discrete:
            checks['patch_absent_from_discrete_schemas'] = bool(chats) and all('patch' not in row['tools'] for row in chats)
        if local_wrapper:
            receipt_path = root / 'aliases' / (SOURCE_DIGEST + '.json')
            receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
            checks.update({
                'one_exact_derived_model_create': sum(r['path'] == '/api/create' for r in requests) == 1,
                'verified_8192_alias_receipt': receipt.get('phase') == 'ready' and receipt.get('context') == 8192
                    and receipt.get('sourceDigest') == SOURCE_DIGEST and receipt.get('aliasDigest') == ALIAS_DIGEST,
                'alias_and_original_unloaded': not fixture['resident'] and sum(r['path'] == '/api/generate' for r in requests) == 2,
                'alias_unload_verified_with_ps': sum(r['path'] == '/api/ps' for r in requests) >= 2,
                'no_auto_name_model_call': helper_requests == 0,
            })
            if overflow or mutate_owner:
                for key in ('cli_exit_zero', 'two_agent_chat_completions', 'exact_selected_model',
                            'four_discrete_tools_exposed' if discrete else 'five_native_tools_exposed', 'original_prompt_intact',
                            'actual_save_tool_wrote_exact_file', 'tool_result_returned'):
                    checks.pop(key)
                if discrete:
                    checks.pop('patch_absent_from_discrete_schemas')
                    checks['discrete_refusal_is_hard_failure'] = result is not None and result.returncode not in (0, 75) \
                        and 'SYMBLIC_BUILD_BUDGET_EXHAUSTED' not in result.stderr.splitlines()
                checks.update({
                    ('first_hook_mutation_refused' if mutate_owner else 'oversized_prompt_refused'):
                        result is not None and result.returncode != 0 and 'Symblic context refused' in output,
                    'no_generation_after_refusal': not any(r['path'] == '/v1/chat/completions' for r in requests),
                    'no_tool_file_after_refusal': not artifact.exists(),
                })
                if mutate_owner:
                    checks['native_first_turn_hook_really_mutated_owner'] = (root / 'hook-mutated').exists()
            else:
                checks['actual_output_token_cap'] = bool(chats) and all(r['max_tokens'] == 1024 for r in chats)
                if completion_boundary:
                    checks.update({
                        'save_then_native_complete_at_boundary': [r.get('fixture_reply') for r in chats] == ['save', 'complete'],
                        'no_third_generation_after_complete': sum(r['path'] == '/v1/chat/completions' for r in requests) == 2,
                        'original_prompt_intact_every_turn': bool(chats) and all(r['prompt_intact'] for r in chats),
                        'owner_text_unchanged_across_turns': bool(chats)
                            and bool(chats[0].get('owner_sha256'))
                            and len({r.get('owner_sha256') for r in chats}) == 1,
                        'native_complete_tool_really_executed': '@complete(' in output
                            and 'Task complete. Autonomous session finished.' in output,
                        'no_budget_handoff_after_completion': result is not None
                            and 'SYMBLIC_BUILD_BUDGET_EXHAUSTED' not in result.stderr.splitlines(),
                    })
                    if complete_at_budget:
                        checks['completed_at_exact_provider_call_limit'] = len(chats) == 2 \
                            and env['SYMBLIC_AGENTCLI_BUILD_STEPS'] == '2'
                    else:
                        checks['final_complete_reply_crossed_elapsed_limit'] = len(chats) == 2 \
                            and chats[-1].get('complete_reply_delay_seconds', 0) >= 10.2 \
                            and env['SYMBLIC_AGENTCLI_BUILD_SECONDS'] == '10'
                        checks['completion_before_provider_call_limit'] = len(chats) == 2 \
                            and env['SYMBLIC_AGENTCLI_BUILD_STEPS'] == '6'
                if build_handoff:
                    for key in ('cli_exit_zero', 'two_agent_chat_completions', 'tool_result_returned'):
                        checks.pop(key)
                    checks.update({
                        'build_handoff_exit_75': result is not None and result.returncode == 75,
                        'budget_marker_on_stderr': result is not None and 'SYMBLIC_BUILD_BUDGET_EXHAUSTED' in result.stderr.splitlines(),
                        'exactly_one_generation_before_handoff': len(chats) == 1
                            and sum(r['path'] == '/v1/chat/completions' for r in requests) == 1,
                        'no_completion_tool_after_handoff': '@complete(' not in output
                            and 'Task complete. Autonomous session finished.' not in output,
                    })
                if prose_continue:
                    checks.pop('two_agent_chat_completions')
                    checks['tool_result_returned'] = len(chats) == 4 and 'tool' in chats[-1]['message_roles']
                    checks.update({
                        'four_agent_chat_completions': len(chats) == 4,
                        'two_prose_replies_then_save_and_complete':
                            [r.get('fixture_reply') for r in chats] == ['prose', 'prose', 'save', 'complete'],
                        'prose_replies_prompt_unfinished_owner_work_and_tools': len(chats) >= 3
                            and all(r.get('continuation_notes')
                                    and all(term in r['continuation_notes'][-1].lower()
                                            for term in ('unfinished request', 'available tools', 'unfinished edits', 'requested checks'))
                                    for r in chats[1:3]),
                        'original_prompt_intact_every_turn': bool(chats) and all(r['prompt_intact'] for r in chats),
                        'owner_text_unchanged_across_turns': bool(chats)
                            and bool(chats[0].get('owner_sha256'))
                            and len({r.get('owner_sha256') for r in chats}) == 1,
                        'within_six_provider_calls': 4 <= sum(r['path'] == '/v1/chat/completions' for r in requests) <= 6,
                        'native_complete_tool_really_executed': '@complete(' in output
                            and 'Task complete. Autonomous session finished.' in output,
                        'no_budget_handoff_after_completion': result is not None
                            and 'SYMBLIC_BUILD_BUDGET_EXHAUSTED' not in result.stderr.splitlines(),
                    })
                if context_handoff:
                    checks.pop('cli_exit_zero')
                    checks.update({
                        'context_pressure_handoff_exit_75': result is not None and result.returncode == 75,
                        'context_handoff_marker_on_stderr': result is not None
                            and 'SYMBLIC_BUILD_BUDGET_EXHAUSTED' in result.stderr.splitlines(),
                        'no_third_generation_after_large_read': len(chats) == 2
                            and sum(r['path'] == '/v1/chat/completions' for r in requests) == 2
                            and [r.get('fixture_reply') for r in chats] == ['save', 'read'],
                        'native_read_tool_returned_large_seeded_text': '@read(' in output
                            and 'SYMBLIC_LARGE_READ_FINISHED' in output,
                        'large_seeded_file_unchanged': (workspace / 'context_pressure_fixture.txt').read_text() == LARGE_READ_CONTENT,
                        'original_prompt_intact_every_turn': bool(chats) and all(r['prompt_intact'] for r in chats),
                        'owner_text_unchanged_across_turns': bool(chats)
                            and bool(chats[0].get('owner_sha256'))
                            and len({r.get('owner_sha256') for r in chats}) == 1,
                        'handoff_before_call_and_time_limits': len(chats) == 2
                            and env['SYMBLIC_AGENTCLI_BUILD_STEPS'] == '6'
                            and time.monotonic() - started < 600,
                        'no_completion_tool_after_context_handoff': '@complete(' not in output
                            and 'Task complete. Autonomous session finished.' not in output,
                    })
        return {'ok': all(checks.values()), 'scope': 'installed CLI + loopback fixture + temporary save tool',
                'live_model': False, 'managed_wrapper': bool(local_wrapper), 'overflow_refusal': overflow,
                'first_hook_mutation_refusal': mutate_owner, 'build_budget_handoff': build_handoff,
                'prose_continuation': prose_continue,
                'context_pressure_handoff': context_handoff, 'discrete_budget': discrete,
                'complete_at_call_budget': complete_at_budget, 'complete_after_elapsed_budget': complete_after_elapsed,
                'system_prompt': system or ('managed short' if local_wrapper else 'default'), 'checks': checks,
                'elapsed_seconds': round(time.monotonic() - started, 3),
                'returncode': result.returncode if result else None, 'requests': requests,
                'auto_name_helper_requests': helper_requests,
                'model_listing_output': listing.stdout[-5000:] if listing else None,
                'errors': errors, 'stdout': output[-18000:],
                'stderr': result.stderr[-5000:] if result is not None else None,
                'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact_ok else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agentcli', default=str(Path.home() / '.local/bin/agentcli'))
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--system', choices=('short', 'full', 'full-noexamples'))
    parser.add_argument('--local-wrapper', help='Node agentcli-local.js script; uses only fixture Ollama metadata')
    parser.add_argument('--agentcli-python', help='Absolute isolated Python for the managed wrapper')
    parser.add_argument('--overflow', action='store_true', help='Verify managed wrapper refuses oversized owner text before inference')
    parser.add_argument('--mutate-owner', action='store_true', help='Verify native first TURN_PRE objective mutation is refused before inference')
    parser.add_argument('--build-handoff', action='store_true', help='Verify one real save then exit75 before a second generation')
    parser.add_argument('--prose-continue', action='store_true', help='Verify two prose replies continue to real save and complete tools within the build budget')
    parser.add_argument('--context-handoff', action='store_true', help='Verify save then large-file read yields75 before a third generation under context pressure')
    parser.add_argument('--discrete-budget', action='store_true', help='Opt overflow/mutation refusal probes into the bounded four-tool build contract')
    parser.add_argument('--complete-at-budget', action='store_true', help='Verify save then native complete exits0 at the exact two-call budget')
    parser.add_argument('--complete-after-elapsed', action='store_true', help='Verify a final complete reply crossing the elapsed budget exits0 without another generation')
    args = parser.parse_args()
    try:
        result = probe(args.agentcli, timeout=args.timeout, system=args.system, local_wrapper=args.local_wrapper,
                       agentcli_python=args.agentcli_python, overflow=args.overflow, mutate_owner=args.mutate_owner,
                       build_handoff=args.build_handoff, prose_continue=args.prose_continue,
                       context_handoff=args.context_handoff, discrete_budget=args.discrete_budget,
                       complete_at_budget=args.complete_at_budget, complete_after_elapsed=args.complete_after_elapsed)
    except (ValueError, OSError) as exc:
        result = {'ok': False, 'scope': 'installed runtime probe', 'error': str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

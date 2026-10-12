"""HOST-ONLY: the original host's HTTP routes under /api/symblicos/ (OS terminal, tasks, autogen).

Why this file is in integration/host/
    It is a route module of the original host's web server: `handle(handler, method, path, data)`
    is called by that server with its request handler (require_owner, send_json, get_query_param),
    and the task routes need the host's agent-hub object (set HUB at startup). Neither exists in
    this repository. It is kept because it shows how the pieces were wired together:

      GET  catalog, vitals, history, tasks, tasks/get, autogen, autogen/get, autogen/catalog, receipt
      POST tasks/start, tasks/control, workspace/create, autogen/start, autogen/control,
           submit (the bounded OS terminal: symblic/os/terminal_server.py)

    Tests: tests/integration/test_symblicos_tasks.py and test_symblicos_autogen_hub_lane.py drive it
    with a fake handler and a fake hub.
"""
from __future__ import annotations

import threading

from integration.host.symblicos_tasks import HubTaskRunner, TaskError, TaskManager, catalog
from symblic.autogen.runner import execution_fence as host_check
from symblic.os.receipts import get_receipt
from symblic.os.terminal_server import SymblicOSTerminalEngine

RELOADABLE = False  # Active task coordinators retain this module's engine.
HUB = None          # the host's agent-hub object; the host sets it when it loads this module
_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SymblicOSTerminalEngine()
        return _engine


def _autogen(engine, tasks):
    """The autogen coordinator shares the task manager (same ledger root, same hub)."""
    from symblic.autogen.coordinator import AutogenManager
    return AutogenManager(engine.paths['root'], task_runner=HubTaskRunner(tasks))


def handle(handler, method: str, path: str, data: dict) -> bool:
    if not handler.require_owner('Symblic terminal execution and files'):
        return True
    route = path.partition('?')[0].removeprefix('/api/symblicos/').strip('/')
    try:
        if method == 'GET' and route == 'catalog':
            handler.send_json(catalog(HUB, refresh=handler.get_query_param('refresh') == '1'))
            return True
        engine = get_engine()
        tasks = TaskManager(engine.paths['root'], hub=HUB)
        if method == 'GET':
            if route == 'vitals':
                result = {'hostname': engine.hostname, 'runtime_version': engine.runtime_version,
                          'profile': 'Hosted Linux workspace', 'status': 'online',
                          'filesystem_root': engine.paths['user_files'],
                          'capabilities': ['agent_tasks', 'fresh_lines', 'qwen_triad', 'durable_receipts',
                                           'parallel_lines', 'team_mode', 'workspace_create', 'auto_resume']}
            elif route in ('history', 'terminal/history'):
                result = {'history': engine.get_history()}
            elif route == 'tasks':
                result = {'tasks': tasks.listing()}
            elif route == 'tasks/get':
                result = {'task': tasks.get(handler.get_query_param('id'), include_screen=True)}
            elif route == 'autogen':
                result = {'runs': _autogen(engine, tasks).listing()}
            elif route == 'autogen/get':
                result = {'run': _autogen(engine, tasks).get(handler.get_query_param('id'),
                                                              include_tasks=handler.get_query_param('tasks') == '1')}
            elif route == 'autogen/catalog':
                from symblic.autogen import policy
                result = {'version': policy.VERSION, 'limits': policy.LIMITS,
                          'defaults': policy.DEFAULTS, 'strategies': list(policy.WIRED_STRATEGIES),
                          'all_strategies': list(policy.STRATEGIES),
                          'failure_classes': list(policy.FAILURE_CLASSES),
                          'handoff_file': policy.HANDOFF_FILE, 'checkpoint_file': policy.CHECKPOINT_FILE}
            elif route == 'receipt' or route.startswith('receipt/'):
                execution_id = route[8:] if route.startswith('receipt/') else handler.get_query_param('id')
                result = get_receipt(execution_id, engine.paths['receipts'])
                if result is None:
                    raise TaskError('Receipt not found.', 404)
            else:
                raise TaskError('Not found.', 404)
        elif method == 'POST':
            host_check()
            if not isinstance(data, dict):
                raise TaskError('Submit a JSON object.')
            if route == 'tasks/start':
                result = tasks.submit(data)
            elif route == 'workspace/create':
                from symblic.autogen.workspaces import create_workspace
                result = create_workspace(engine.paths['root'], data.get('name'))
            elif route == 'tasks/control':
                result = tasks.control(data.get('id'), data.get('action'))
            elif route == 'autogen/start':
                result = _autogen(engine, tasks).submit(data)
            elif route == 'autogen/control':
                result = _autogen(engine, tasks).control(data.get('id'), data.get('action'), extend=data.get('extend'))
            elif route in ('submit', 'terminal/submit'):
                result = engine.execute_instruction(data.get('instruction', ''),
                                                    data.get('client_request_id') or data.get('request_id'))
            else:
                raise TaskError('Not found.', 404)
        else:
            return False
        handler.send_json(result)
    except (TaskError, ValueError) as exc:  # AutogenError and the policy's AutogenError are ValueErrors
        handler.send_json({'error': str(exc)}, getattr(exc, 'status', 400))
    return True

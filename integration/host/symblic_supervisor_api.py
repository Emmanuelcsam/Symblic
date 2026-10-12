"""HOST-ONLY: the host's `supervisor/` HTTP routes and a local CLI for durable Symblic workflows.

Why it is host-only: the routes need the host's request handler and its owner and per-person gates
(`person`, a host module), and the workflows themselves run through integration/host/symblic_supervisor.py,
which needs the host's runner and scheduler. The CLI (`main`) talks to the same routes over loopback HTTP.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from integration.host import symblic_supervisor as W


def handle(handler, method, route, data):
    if not route.startswith('supervisor/'):
        return False
    if not handler.require_owner('Symblic supervisor'):
        return True
    import person
    if not person.require(handler, 'owner', 'Symblic supervisor'):
        return True
    name = route[len('supervisor/'):].strip('/')
    data = data if isinstance(data, dict) else {}
    try:
        if method == 'GET' and name in ('list', 'view'):
            result = W.listing() if name == 'list' else W.view(handler.get_query_param('id'))
        elif method == 'POST':
            if name == 'create':
                result = W.create(data.get('definition'), data.get('request_id'))
            elif name == 'start':
                result = W.start(data.get('id'), data.get('request_id'))
            elif name == 'tick':
                result = W.tick(data.get('id'))
            elif name in ('state', 'pause'):
                result = W.mutate(data.get('id'), data.get('revision'), data.get('request_id'), name,
                                  data.get('changes') if name == 'state' else data.get('paused'))
            elif name == 'schedule':
                result = W.schedule(data.get('id'), data.get('cron'), data.get('enabled'), data.get('revision'))
            elif name == 'bind':
                result = W.bind_trigger(data.get('id'), data.get('trigger'), data.get('revision'))
            elif name == 'reconcile':
                result = W.reconcile(data.get('id'), data.get('firing'), data.get('step'), data.get('native_id'))
            elif name == 'simulate':
                result = W.simulate(data.get('definition'), data.get('outcomes'))
            else:
                return False
        else:
            return False
        handler.send_json(result)
    except W.Conflict as exc:
        handler.send_json({'error': str(exc)}, 409)
    except (ValueError, OSError) as exc:
        handler.send_json({'error': str(exc)}, 400)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Symblic durable workflows through the host's owner-only loopback API")
    parser.add_argument('operation', choices=('list', 'view', 'create', 'start', 'tick', 'state', 'pause', 'schedule', 'bind', 'reconcile', 'simulate'))
    parser.add_argument('--id')
    parser.add_argument('--file', help='JSON definition for create/simulate; JSON request body for other writes')
    parser.add_argument('--request-id', help='Stable operation ID; reuse after lost replies')
    parser.add_argument('--port', type=int, default=8080, help='the host web server port (loopback only)')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    body = json.loads(Path(args.file).read_text()) if args.file else {}
    if args.operation in ('create', 'simulate'):
        body = {'definition': body}
    if args.id:
        body['id'] = args.id
    if args.request_id:
        body['request_id'] = args.request_id
    if args.operation in ('create', 'start', 'state', 'pause') and not body.get('request_id'):
        parser.error('Supply --request-id and reuse it after a lost reply.')
    base = f'http://127.0.0.1:{args.port}/api/automation/symblic/supervisor/{args.operation}'
    get = args.operation in ('list', 'view')
    request = urllib.request.Request(base + ('?' + urllib.parse.urlencode(body) if get and body else ''),
                                     data=None if get else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            sys.stdout.write(response.read().decode() + '\n')
        return 0
    except urllib.error.HTTPError as exc:
        sys.stderr.write(exc.read().decode() + '\n')
        return 1
    except (OSError, ValueError) as exc:
        sys.stderr.write(str(exc) + '\nReply unknown; refresh the workflow and reuse the same request ID.\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

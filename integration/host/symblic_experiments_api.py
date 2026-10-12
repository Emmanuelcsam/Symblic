"""HOST-ONLY: the host's `experiments/` routes; a thin HTTP wrapper over symblic/experiments/registry.py.

Why it is host-only: it needs the host's request handler (`send_json`) behind its owner gate. Without the
host, run the same experiments with `tools/symblic experiments list|example|run|verify`.
"""
from symblic.experiments import registry as E


def handle(handler, method, route, data):
    if not route.startswith('experiments/'):
        return False
    try:
        if method == 'GET' and route == 'experiments/catalog':
            result = E.catalog()
        elif method == 'POST' and route == 'experiments/run':
            if type(data) is not dict or set(data) != {'experiment', 'input_json'}:
                raise E.ExperimentError('request_schema')
            result = E.run(data['experiment'], E.loads(data['input_json']))
        elif method == 'POST' and route == 'experiments/verify':
            if type(data) is not dict or set(data) != {'receipt_json'}:
                raise E.ExperimentError('request_schema')
            result = E.verify(E.loads(data['receipt_json']))
        else:
            handler.send_json({'ok': False, 'error': 'Unknown experiment action.'}, 404)
            return True
        handler.send_json(result)
    except E.ExperimentError as error:
        handler.send_json({'ok': False, 'error': 'Experiment refused.', 'detail': {'code': str(error)}}, 400)
    return True

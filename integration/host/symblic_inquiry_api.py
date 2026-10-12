"""HOST-ONLY: the host's `inquiry/` routes; a thin HTTP wrapper over symblic/inquiry/selection.py.

Why it is host-only: it needs the host's request handler (`send_json`) behind its owner gate. Without the
host, use `tools/symblic inquiry example|plan FILE`.
"""
from symblic.inquiry import selection as I


def handle(handler, method, route, data):
    """Return a pure recommendation; never persist or dispatch a selected method."""
    if not route.startswith('inquiry/'):
        return False
    try:
        if method == 'GET' and route == 'inquiry/example':
            if data not in (None, {}):
                raise I.InquiryError('schema', 'request')
            result = {'version': I.VERSION, 'kind': 'synthetic_fixture', 'assessment': I.example()}
        elif method == 'POST' and route == 'inquiry/plan':
            if type(data) is not dict or set(data) not in ({'assessment'}, {'assessment_json'}):
                raise I.InquiryError('schema', 'request')
            if 'assessment_json' in data:
                if type(data['assessment_json']) is not str:
                    raise I.InquiryError('json_type', 'assessment_json')
                assessment = I.loads(data['assessment_json'])
            else:
                assessment = data['assessment']
            result = I.plan(assessment)
        else:
            handler.send_json({'ok': False, 'error': 'Unknown inquiry action.'}, 404)
            return True
        handler.send_json(result)
    except I.InquiryError as error:
        handler.send_json({'ok': False, 'error': 'Inquiry request refused.',
                           'detail': {'code': error.code, 'path': error.path}}, 400)
    return True

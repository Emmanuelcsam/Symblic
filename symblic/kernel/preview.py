"""Preview: run a program up to its first `ask` and show exactly what that ask would send, with no model.

    from symblic.kernel import preview
    report = preview.preview({'source': text, 'inputs': {}, 'by': 'ollama:qwen3:4b-instruct'})
    report['next']        # the first ask: applicator, system line, prompt, answer schema, temperature, seed

preview() checks the request (clean_source, clean_inputs, clean_by) and then runs the program in a bounded child
process (symblic/kernel/process_limits.py, action `preview`: CPU, address-space and wall-time limits). The child
calls run_preview(): the interpreter evaluates every formal statement exactly, and the first time the program
would call a model the capture records that call's capsule and stops the run. Nothing is sent to a model,
nothing is written to disk and side effects are off. The report has the bindings and outputs computed so far,
the warnings and facts, the fingerprint and, when the program reached an ask, `next` (that ask's capsule). A
program with no ask simply runs to the end (`status` done).

Used by: `tools/symblic preview` and, in the original host, its `symblic/preview` HTTP route
(integration/host/symblic_engine.py re-exports these names). Request errors raise RequestError (a ValueError)
before any child starts. Depends on: symblic.kernel.language, symblic.kernel.run and
symblic.kernel.process_limits; nothing runs on import.
"""
from __future__ import annotations

import json

from symblic.kernel import language as S

MAX_INPUT_JSON = 200_000            # characters of JSON a request's inputs may take
MAX_APPLICATORS = 16                # applicator specs a request may name


class RequestError(ValueError):
    """A request the preview (or a host route that shares these checks) refuses before running anything."""


def clean_inputs(raw) -> dict:
    """The program's inputs as a JSON object (a dict, or a JSON text of one); {} when none are given."""
    if raw in (None, ''):
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise RequestError('Inputs must be a JSON object.') from None
    if not isinstance(raw, dict):
        raise RequestError('Inputs must be a JSON object.')
    if len(json.dumps(raw)) > MAX_INPUT_JSON:
        raise RequestError('Inputs are too large.')
    return raw


def clean_by(raw) -> str | list | None:
    """One applicator spec, a list of up to 16, or None; each is checked by symblic.kernel.language."""
    if raw in (None, '', []):
        return None
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for item in items[:MAX_APPLICATORS]:
        try:
            out.append(S.parse_applicator(item)['spec'])
        except S.SymblicError as e:
            raise RequestError(e.message) from None
    return out[0] if len(out) == 1 else out


def clean_source(source) -> str:
    """The program text, refused when empty or longer than the language's MAX_SOURCE."""
    source = str(source or '')
    if not source.strip():
        raise RequestError('Write a program first.')
    if len(source) > S.MAX_SOURCE:
        raise RequestError('The program is too long.')
    return source


def _determine_option(options) -> dict:
    """The one run option a preview accepts: determine (true or false), which turns enumeration probes on/off."""
    options = options if isinstance(options, dict) else {}
    if 'determine' not in options:
        return {}
    if type(options['determine']) is not bool:
        raise RequestError('determine must be true or false.')
    return {'determine': options['determine']}


def preview(body: dict) -> dict:
    """Check the request, then run run_preview() in a bounded child process and return its report."""
    # Limits are set only inside the child, never in the calling process (a CLI or a web server thread).
    from symblic.kernel import process_limits as P
    clean = {'source': clean_source(body.get('source')), 'inputs': clean_inputs(body.get('inputs')),
             'by': clean_by(body.get('by'))}
    determine = _determine_option(body.get('options'))
    if determine:
        clean['options'] = determine
    return P.call_bounded('preview', clean)


class _Capture(Exception):
    def __init__(self, req):
        super().__init__('captured')
        self.req = req


class _PreviewApps:
    """An applicators object that never answers: a preview must not reach a provider."""
    def call(self, req):
        raise _Capture(req)


def run_preview(body: dict) -> dict:
    """The child side of preview(): no model, no file, no side effect. Public callers use preview()."""
    from symblic.kernel import run as SR
    source = clean_source(body.get('source'))
    inputs = clean_inputs(body.get('inputs'))
    by = clean_by(body.get('by'))
    opts = {'by': by or 'fake:preview', 'parallel': 1, 'max_steps': 200_000, 'preview': True,
            'side_effects': False, **_determine_option(body.get('options'))}
    run = SR.Run(source, inputs, _PreviewApps(), opts)
    captured = {}

    def capture(app, system, prompt, schema, sample, temperature, seed, effort, tools, s, context_manifest=None,
                **_extras):
        if not captured:
            captured.update({'app': S.app_label(app), 'system': system, 'prompt': prompt, 'schema': schema,
                             'line': s.line, 'name': s.name, 'temperature': temperature, 'seed': seed,
                             'context_manifest': context_manifest})
            if app.get('member'):
                captured.update(member=app['member'], effort=app['member']['effort'],
                                team_preview='First selected member only; the complete configured team applies at '
                                             'execution.')
        raise SR.Stopped()
    run._call = capture
    report = run.execute()
    out = {'status': 'paused' if captured else report['status'], 'error': report.get('error'),
           'bindings': report['bindings'], 'outputs': [{k: v for k, v in o.items() if k != 'svg'}
                                                       for o in report['outputs']],
           'warnings': report['warnings'], 'facts': report['facts'], 'fingerprint': report['fingerprint']}
    svgs = [o['svg'] for o in report['outputs'] if o.get('svg')]
    if svgs:
        out['drawing'] = svgs[-1]
    if captured:
        out['next'] = captured
    return out

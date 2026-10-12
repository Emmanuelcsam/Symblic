"""A small, version-pinned API for running Symblic inside another Python program.

    from symblic.kernel import embed
    embed.check(source)                                   # diagnostics, plus the kernel identity
    embed.run(source, inputs={...}, applicators=my_apps, options={...}, on_event=print, stop=event)

check() refuses when the caller pins a kernel_id that differs from this installation's; run() checks first and
then runs the program with symblic.kernel.run.Run. The embedding program supplies the applicators (any object
with call(request) -> reply; see symblic.providers.applicators), cancellation and an optional event observer.
No workers start on import; effects (observe/act) stay opt-in and are refused in replay. API_VERSION changes
when this surface does.

Depends on: symblic.kernel.language, symblic.kernel.run. Used by: programs that embed Symblic.
"""

from __future__ import annotations

from symblic.kernel import language as S
from symblic.kernel.run import Run

API_VERSION = 1


def check(source: str, *, kernel_id: str | None = None, execution_profile=None) -> dict:
    current = S.kernel_id()
    if kernel_id is not None and kernel_id != current['id']:
        return {'ok': False, 'errors': [S.SymblicError('the required kernel version is not available',
                                                      kind='version').as_dict()], 'warnings': [], 'plan': [],
                'kernel': current, 'api_version': API_VERSION}
    return {**S.check(source, execution_profile=execution_profile), 'kernel': current, 'api_version': API_VERSION}


def run(source: str, *, inputs=None, applicators=None, options=None, on_event=None, stop=None,
        kernel_id: str | None = None, folder=None) -> dict:
    checked = check(source, kernel_id=kernel_id, execution_profile=(options or {}).get('profile'))
    if not checked['ok']:
        return {'status': 'failed', 'error': checked['errors'][0], 'diagnostics': checked,
                'calls': 0, 'asks': 0, 'bindings': [], 'outputs': [], 'kernel': S.kernel_id(),
                'api_version': API_VERSION}
    opts = dict(options or {})
    if on_event is not None:
        opts['on_event'] = on_event
    if stop is not None:
        opts['stop'] = stop
    result = Run(source, inputs=inputs, applicators=applicators, options=opts, folder=folder).execute()
    return {**result, 'api_version': API_VERSION}

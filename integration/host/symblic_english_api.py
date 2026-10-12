"""HOST-ONLY: the host web server's `english/` routes (check, preview, run, retry); execution is the native runner.

Why it is host-only: runs are saved and launched through the host engine (integration/host/symblic_engine.py)
and its run store. Its pure half (compile a document, attach and check the authoring record) lives in
symblic/english/authoring.py, which `tools/symblic english` uses. This copy still names the original flat
module files (symblic_english.py, symblic_spec.py, automation-studio/...) in its compiler-identity pins,
exactly as the host computed them; see integration/host/README.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from symblic.kernel import language as S

VERSION = 1
FIELDS = {'source', 'by', 'team', 'retries', 'max_calls', 'budget', 'title'}
PIXEL_FILES = {'symblic_english_pixels.py', 'symblic_english_pixel_checks.py',
               'symblic_spec.py', 'symblic_spec_build.py', 'symblic_spec_contracts.py'}
PIXEL_ASSETS = {'automation-studio/symblic-pixel-vm.js',
                'automation-studio/symblic-pixel-program.js'}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _integer(body, key, default, low, high):
    value = body.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{key} must be a whole number from {low} to {high}.')
    return value


def compiler_digest(compiler, source=None):
    from symblic.kernel import execution_pins as execution
    from symblic.kernel import identity as identity
    path = Path(compiler.__file__)
    files = {'symblic_english.py'}
    dependencies = getattr(compiler, 'compiler_dependencies', lambda _text: ())(source)
    pixel_dependencies = tuple(sorted(PIXEL_FILES | execution.REQUIRED_FILES))
    if dependencies not in ((), ('symblic_english_build.py',), pixel_dependencies):
        raise ValueError('The English compiler dependency list is invalid.')
    files.update(dependencies)
    assets = (PIXEL_ASSETS | execution.ASSET_FILES) if dependencies == pixel_dependencies else set()
    try:
        hashes = {}
        for name in sorted(files | assets):
            item = path.parent / name
            if item.is_symlink() or item.parent.is_symlink() or not item.is_file():
                raise OSError('compiler dependency is not a regular source file')
            raw = item.read_bytes()
            if len(raw) > identity.MAX_SOURCE_BYTES:
                raise OSError('compiler dependency exceeds its source bound')
            hashes[name] = hashlib.sha256(raw).hexdigest()
    except OSError:
        raise ValueError('The English compiler source is unavailable. Restore it and restart the host web server.') from None
    problems = identity.audit(path.parent, files, hashes)
    if problems:
        raise ValueError('The loaded English compiler differs from its source. Restart the host web server before compiling.')
    return hashes['symblic_english.py'] if not dependencies else _digest(hashes)


def prepare(body, *, artifacts=None, reuse_from=None):
    from symblic.english import compiler as C
    if type(body) is not dict or set(body) - FIELDS:
        raise ValueError('Use source, by, team, retries, max_calls, budget and title only.')
    text = body.get('source')
    if type(text) is not str or not text.strip():
        raise ValueError('Write English statements first.')
    if len(text) > S.MAX_SOURCE:
        raise ValueError('The instructions are too long.')
    compiler_sha256 = compiler_digest(C, text)
    compile_options = {'retries': _integer(body, 'retries', 2, 0, 5),
        'max_calls': _integer(body, 'max_calls', 64, 0, 10000),
        'budget': _integer(body, 'budget', 12000, 1000, 100000)}
    if artifacts is not None and C.is_construction_source(text):
        # the construction lane re-enters its own compiler with retained steps; the shared compiler
        # gate reserves `artifacts` for the labelled pixel lane
        from symblic.english import build as build
        compiled = build.compile_source(text, artifacts=artifacts, **compile_options)
    else:
        if artifacts is not None:
            compile_options['artifacts'] = artifacts
        compiled = C.compile_source(text, **compile_options)
    if 'team' in body:
        from symblic.providers import agent_teams as teams
        from symblic.kernel import identity as identity
        team_path = Path(teams.__file__)
        team_hash = hashlib.sha256(team_path.read_bytes()).hexdigest()
        if identity.audit(team_path.parent, {team_path.name}, {team_path.name: team_hash}):
            raise ValueError('The loaded team compiler differs from its source. Restart before compiling.')
        compiled = teams.lower_checked(compiled, body['team'])
        if hashlib.sha256(team_path.read_bytes()).hexdigest() != team_hash:
            raise ValueError('The team compiler changed during compilation. Restart before compiling.')
    if compiler_digest(C, text) != compiler_sha256:
        raise ValueError('The English compiler changed during compilation. Restart and try again.')
    checked = S.check(compiled['source'], execution_profile='verified')
    if not checked['ok']:
        error = checked['errors'][0]
        raise ValueError(f'Generated program refused: {error["message"]}')
    options = dict(compiled['options'])
    # These are model tasks. Native validation still runs on every returned answer.
    options.update(profile='verified', determine=False, solve=False, constructor='off', side_effects=False,
                   progress_outputs=True)
    compiled = {**compiled, 'options': options, 'inputs': compiled.get('inputs', {}), 'check': checked}
    compiled['authoring'] = {'format': 'english', 'version': VERSION,
        'compiler_version': compiled.get('version', C.VERSION),
        'compiler_sha256': compiler_sha256,
        'document': text, 'document_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'native_sha256': hashlib.sha256(compiled['source'].encode()).hexdigest(),
        'source_map': compiled.get('source_map', {}), 'statements': compiled.get('statements', [])}
    if compiled.get('presentation') is not None:
        compiled['authoring']['presentation'] = compiled['presentation']
    if 'team' in compiled:
        compiled['authoring'].update(team=compiled['team'], team_sha256=compiled['team_sha256'],
            team_policy=compiled['team_policy'], team_compiler_sha256=team_hash)
    if reuse_from is not None:
        compiled['authoring']['reuse'] = {'from_run': reuse_from,
            'kept': (compiled.get('pixel_build', {}).get('kept', 0)
                     or compiled.get('construction', {}).get('kept', 0)),
            'scope': 'locally_rechecked_model_work'}
    compiled['authoring']['sha256'] = _digest(compiled['authoring'])
    return compiled


def prepare_retry(body):
    """Recheck accepted work from a terminal run; always start a separate run.

    Clients select a saved run, never provide trusted artifact receipts. The
    labelled pixel lane and the English construction lane both keep their
    locally rechecked accepted work; the original document, source and run stay
    intact. Syntax validation precedes any local JavaScript recheck and
    check/preview do not accept this option.
    """
    from integration.host import symblic_engine as engine
    from symblic.english import compiler as compiler
    from symblic.english import build as construction
    from symblic.spec import build as build
    run_id = body.get('keep')
    if type(run_id) is not str or not re.fullmatch('[0-9a-f]{12}', run_id):
        raise ValueError('Retry needs the exact saved run identifier.')
    request = {key: value for key, value in body.items() if key != 'keep'}
    prepared = prepare(request)
    is_construction = construction.recognizes(request['source'])
    if not is_construction and not compiler.is_pixel_source(request['source']):
        raise ValueError('Retry remaining tasks requires a labelled English pixel program or an English '
                         'construction program.')
    saved = engine.run_view(run_id)
    if (saved['status'] not in ('failed', 'done', 'stopped') or
            engine.launcher['active'](run_id)):
        raise ValueError('Retry requires a finished or stopped run; its current work must remain intact.')
    authoring = saved['meta'].get('authoring')
    if is_construction:
        valid_lane = (checked_authoring(authoring, saved['source'])
                      and construction.recognizes(authoring['document'])
                      and 'let constructed_frames = js_run(' in saved['source'])
        refusal = 'The saved run has no valid English construction authoring record.'
    else:
        valid_lane = (checked_authoring(authoring, saved['source'])
                     and authoring.get('presentation', {}).get('kind') == 'binary-pixel-program')
        refusal = 'The saved run has no valid English pixel authoring record.'
    if not valid_lane:
        raise ValueError(refusal)
    validate_saved(engine.run_dir(run_id), saved['source'], saved['meta'])
    if authoring['document'] != request['source']:
        raise ValueError('Retry must preserve the exact saved English document. Start a new run for edited instructions.')
    if authoring.get('team') != prepared['authoring'].get('team'):
        raise ValueError('Retry must preserve the exact selected team. Start a new run to change members or profiles.')
    checkpoint = (construction.checkpoint(engine.run_dir(run_id), recheck_seconds=30) if is_construction
                  else build.checkpoint(engine.run_dir(run_id), complete=False, recheck_seconds=30))
    current = engine.run_view(run_id)
    if (current['status'] not in ('failed', 'done', 'stopped') or engine.launcher['active'](run_id)
            or current['source'] != saved['source'] or current['meta'].get('authoring') != authoring):
        raise ValueError('The saved run changed during rechecking. Inspect it before retrying.')
    validate_saved(engine.run_dir(run_id), current['source'], current['meta'])
    compiled = prepare(request, artifacts=checkpoint['artifacts'], reuse_from=run_id)
    return compiled


def checked_authoring(authoring, source):
    """Check saved display metadata without treating its text as executable source."""
    if type(authoring) is not dict or authoring.get('format') != 'english':
        return False
    document = authoring.get('document')
    return (type(document) is str
        and type(authoring.get('version')) is int and authoring['version'] == VERSION
        and type(authoring.get('compiler_version')) is str
        and re.fullmatch('[0-9a-f]{64}', str(authoring.get('compiler_sha256', ''))) is not None
        and authoring.get('sha256') == _digest({k: v for k, v in authoring.items() if k != 'sha256'})
        and hashlib.sha256(document.encode()).hexdigest() == authoring.get('document_sha256')
        and hashlib.sha256(source.encode()).hexdigest() == authoring.get('native_sha256'))


def validate_saved(folder, source, meta):
    """Nondestructive read before resume/dispatch; old native-only runs retain their path."""
    from symblic.constructor.records import _regular_bytes
    path = Path(folder) / 'instructions.english'
    authoring = meta.get('authoring')
    if authoring is None and not os.path.lexists(path):
        return
    try:
        raw = _regular_bytes(str(path), S.MAX_SOURCE * 4)
        if not checked_authoring(authoring, source) or raw is None or raw.decode('utf-8') != authoring['document']:
            raise ValueError('instructions or compiled program differ from their saved hashes')
    except (OSError, ValueError, UnicodeError, S.SymblicError) as error:
        raise S.SymblicError('Saved English authoring refused: ' + str(error), kind='version') from None


def examples():
    from symblic.english import compiler as C
    examples = dict(C.EXAMPLES)
    try:
        from symblic.english import build as build
        examples['matrix-rain'] = {'title': 'Matrix rain: Qwen writes the implementation from English steps', 'source': build.EXAMPLE}
    except ImportError:
        pass
    try:
        from symblic.english import pixels as pixels
        examples['moving-dot'] = {'title': 'Moving white dot: thirty-four English statements', 'source': pixels.EXAMPLE}
    except ImportError:
        pass
    return examples


def handle(handler, method, route, data):
    from integration.host import symblic_engine as E
    try:
        if method == 'GET' and route == 'english/examples':
            from symblic.providers import agent_teams as teams
            handler.send_json({'version': VERSION, 'examples': examples(),
                'capabilities': {'team': {'version': teams.VERSION, 'max_members': teams.MAX_MEMBERS}}})
        elif method == 'POST' and route in ('english/check', 'english/preview', 'english/run'):
            compiled = (prepare_retry(data) if route == 'english/run' and
                        type(data) is dict and 'keep' in data else prepare(data))
            if route == 'english/check':
                handler.send_json({'ok': True, **compiled})
            else:
                body = {'source': compiled['source'], 'inputs': compiled['inputs'],
                    'options': compiled['options'], 'by': data.get('by') or 'ollama:qwen3:4b-instruct',
                    'title': data.get('title') or 'English statements'}
                if route == 'english/preview':
                    handler.send_json({'ok': True, 'compiled': compiled, 'preview': E.preview(body)})
                else:
                    from symblic.kernel import execution_pins as X
                    hashes = {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest()
                              for name in X.REQUIRED_FILES}
                    body['options']['execution_pins'] = X.build(body['source'], body['inputs'], hashes)
                    result = E.start_run(body, authoring=compiled['authoring'])
                    if 'reuse' in compiled['authoring']:
                        result = {**result, 'kept': compiled['authoring']['reuse']['kept'],
                                  'reuse': compiled['authoring']['reuse']}
                    handler.send_json(result)
        else:
            return False
    except (ValueError, S.SymblicError, E.SymblicApiError) as error:
        detail = error.as_dict() if isinstance(error, S.SymblicError) else {
            'message': str(error), 'line': getattr(error, 'line', 0),
            'col': getattr(error, 'col', 0), 'kind': getattr(error, 'code', 'english')}
        handler.send_json({'ok': False, 'error': detail['message'], 'errors': [detail]}, 400)
    return True

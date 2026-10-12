"""Prepare an English document for a run: compile it, check the generated program, and attach an authoring record.

What this is for: symblic.english.compiler turns a short document of English statements ("Ask for ...",
"Accept only if ...", "Display ...") into an ordinary Symblic program. Before such a program runs, `prepare` also
records *what was compiled with what*: the exact document, the hash of the compiler's own source files (and, for
the pixel and construction grammars, of every file they depend on), the hash of the generated program, the source
map from program lines back to English lines, and a hash over the whole record. A saved run keeps this record in
its meta.json and the document in instructions.english, so a later reader can check that the program in the folder
is the one the document produced (`checked_authoring`, `validate_saved`).

Public functions:

    prepare(body)                 {'source': English text, 'retries'?, 'max_calls'?, 'budget'?, 'team'?, 'by'?,
                                   'title'?} -> the compiled program, its options, inputs, native check and
                                   'authoring' record. Raises ValueError for an author error.
    compiler_digest(compiler, source)   the hash that identifies the compiler (and its dependencies) used.
    checked_authoring(record, program)  True when a saved authoring record is intact and matches the program.
    validate_saved(folder, program, meta)   refuse (SymblicError) a run folder whose instructions or program differ.
    examples()                    the built-in example documents, by name.

Depends on: symblic.kernel (language, identity, execution_pins), symblic.english (compiler, build, pixels),
symblic.constructor.records (a bounded regular-file reader) and, for teams, symblic.providers.agent_teams.
Used by: symblic.english.cli (the `english` command). Nothing here calls a model, starts a process or writes a file.

The compiler hashes detect a changed or stale compiler file (the kernel's import-identity check compares the loaded
code with the file on disk); they are a consistency check on one machine, not a signature. This module was the
pure half of the original host's English HTTP API; the HTTP route stays in integration/host/symblic_english_api.py.
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
# Registry names are paths from the repository root (the directory that holds the `symblic` package).
COMPILER_FILE = 'symblic/english/compiler.py'
CONSTRUCTION_FILES = ('symblic/english/build.py',)
PIXEL_FILES = {'symblic/english/pixels.py', 'symblic/english/pixel_checks.py',
               'symblic/spec/sheets.py', 'symblic/spec/build.py', 'symblic/spec/contracts.py'}
# The browser-side pixel interpreter the pixel grammar's checks run (pinned by hash in symblic.english.pixel_checks).
PIXEL_ASSETS = {'web/studio/symblic-pixel-vm.js', 'web/studio/symblic-pixel-program.js'}
TEAM_FILE = 'symblic/providers/agent_teams.py'


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _integer(body, key, default, low, high):
    value = body.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{key} must be a whole number from {low} to {high}.')
    return value


def _root(module):
    """The repository root for a module inside the `symblic` package (two levels above its folder)."""
    return Path(module.__file__).resolve().parents[2]


def compiler_digest(compiler, source=None):
    """sha256 of the compiler file, or of every file the selected grammar depends on (pixel, construction)."""
    from symblic.kernel import execution_pins as execution
    from symblic.kernel import identity as identity
    root = _root(compiler)
    files = {COMPILER_FILE}
    dependencies = getattr(compiler, 'compiler_dependencies', lambda _text: ())(source)
    pixel_dependencies = tuple(sorted(PIXEL_FILES | execution.REQUIRED_FILES))
    if dependencies not in ((), CONSTRUCTION_FILES, pixel_dependencies):
        raise ValueError('The English compiler dependency list is invalid.')
    files.update(dependencies)
    assets = (PIXEL_ASSETS | execution.ASSET_FILES) if dependencies == pixel_dependencies else set()
    try:
        hashes = {}
        for name in sorted(files | assets):
            item = root / name
            if item.is_symlink() or item.parent.is_symlink() or not item.is_file():
                raise OSError('compiler dependency is not a regular source file')
            raw = item.read_bytes()
            if len(raw) > identity.MAX_SOURCE_BYTES:
                raise OSError('compiler dependency exceeds its source bound')
            hashes[name] = hashlib.sha256(raw).hexdigest()
    except OSError:
        raise ValueError('The English compiler source is unavailable: restore the repository file '
                         '(and restart any long-running process that imported it).') from None
    problems = identity.audit(root, files, hashes)
    if problems:
        raise ValueError('The loaded English compiler differs from its source file. Restart this Python process '
                         'before compiling.')
    return hashes[COMPILER_FILE] if not dependencies else _digest(hashes)


def prepare(body, *, artifacts=None, reuse_from=None):
    """Compile an English document and attach its authoring record (see the module docstring)."""
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
        # the construction grammar re-enters its own compiler with retained steps; the shared compiler
        # entry reserves `artifacts` for the labelled pixel grammar
        from symblic.english import build as build
        compiled = build.compile_source(text, artifacts=artifacts, **compile_options)
    else:
        if artifacts is not None:
            compile_options['artifacts'] = artifacts
        compiled = C.compile_source(text, **compile_options)
    team_hash = None
    if 'team' in body:
        from symblic.providers import agent_teams as teams
        from symblic.kernel import identity as identity
        root = _root(teams)
        team_hash = hashlib.sha256((root / TEAM_FILE).read_bytes()).hexdigest()
        if identity.audit(root, {TEAM_FILE}, {TEAM_FILE: team_hash}):
            raise ValueError('The loaded team compiler differs from its source file. Restart this Python process.')
        compiled = teams.lower_checked(compiled, body['team'])
        if hashlib.sha256((root / TEAM_FILE).read_bytes()).hexdigest() != team_hash:
            raise ValueError('The team compiler changed during compilation. Restart this Python process.')
    if compiler_digest(C, text) != compiler_sha256:
        raise ValueError('The English compiler changed during compilation. Restart this Python process and try again.')
    checked = S.check(compiled['source'], execution_profile='verified')
    if not checked['ok']:
        error = checked['errors'][0]
        raise ValueError(f'Generated program refused: {error["message"]}')
    options = dict(compiled['options'])
    # These are model tasks. The kernel still checks every returned answer.
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
    """Nondestructive read before a saved English run resumes or replays; plain (non-English) runs pass through."""
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
    """The built-in example documents: {name: {'title', 'source'}}."""
    from symblic.english import compiler as C
    examples = dict(C.EXAMPLES)
    try:
        from symblic.english import build as build
        examples['matrix-rain'] = {'title': 'Matrix rain: a model writes the implementation from English steps',
                                   'source': build.EXAMPLE}
    except ImportError:
        pass
    try:
        from symblic.english import pixels as pixels
        examples['moving-dot'] = {'title': 'Moving white dot: thirty-four English statements', 'source': pixels.EXAMPLE}
    except ImportError:
        pass
    return examples

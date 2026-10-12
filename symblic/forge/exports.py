"""Forge exports: turn the accepted parts of a project into reviewable artifacts, checked by the real compiler.

What it is for
    From the accepted requirements and engineering records of a project this module builds: task_cards()
    (one card per accepted construction unit: objective, inputs, outputs, paths, dependencies, checks),
    construction_plan() (the human-readable build plan), native_source() (a Symblic program whose Text asks
    carry each task and its explicit dependency capsule), spec_sheet() and brief(), and artifact(project, kind)
    for any of them. validate(project, source) runs the native checker (symblic.authoring.editor_diagnostics)
    on the generated or supplied source and returns a receipt; prose verification steps stay observable
    checks, never fabricated executable predicates, and 'executed' is always false.

Source identity
    Every validation receipt names the exact compiler and Forge source files (SOURCE_FILES, hashed when this
    module was imported). If those files change on disk while the process runs, validation refuses with a
    'restart required' error instead of issuing a receipt for code that is not the code running.

Depends on: symblic.forge (core, store), symblic.kernel.language, symblic.spec.sheets and
symblic.authoring.editor_diagnostics (imported when used). Used by: the original host's Forge routes and its
handoff bridge (integration/host/symblic_forge.py, symblic_forge_bridge.py). Status: prototype; tested by
tests/forge/test_symblic_forge_exports.py. Nothing here runs a project or calls a model.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from types import MappingProxyType

from symblic.forge import core as C
from symblic.forge.store import encode, StoreError

VERSION = 'forge-export/1'
MAX_SOURCE_BYTES = 400_000
# The compiler and Forge source files an export's validation receipt binds, as POSIX paths relative to the folder
# that holds the symblic package (the same names symblic.kernel.execution_pins uses).
SOURCE_FILES = ('symblic/kernel/language.py', 'symblic/kernel/embed.py', 'symblic/spec/sheets.py',
                'symblic/authoring/editor_diagnostics.py', 'symblic/forge/core.py', 'symblic/forge/catalog.py',
                'symblic/forge/exports.py', 'symblic/forge/coach.py', 'symblic/providers/agent_teams.py',
                'symblic/kernel/json_schema.py')


def _read_source_hashes():
    """Read-only provenance inspection; never starts a compiler, worker or model."""
    base = Path(__file__).resolve().parents[2]
    hashes = {}
    for name in SOURCE_FILES:
        try:
            hashes[name] = hashlib.sha256((base / name).read_bytes()).hexdigest()
        except OSError:
            hashes[name] = None
    return hashes


# Pin the files this process loaded, before any later edit that would need a process restart.
# Neither returned metadata nor an API caller can replace this immutable baseline.
_LOADED_SOURCE_HASHES = MappingProxyType(_read_source_hashes())


def source_identity():
    current = _read_source_hashes()
    changed = [name for name in SOURCE_FILES if _LOADED_SOURCE_HASHES.get(name) is None
               or current.get(name) is None or current.get(name) != _LOADED_SOURCE_HASHES.get(name)]
    return {'source_hashes': dict(_LOADED_SOURCE_HASHES), 'disk_source_hashes': current,
            'restart_required': bool(changed), 'changed_sources': changed}


def _require_current_source():
    identity = source_identity()
    if identity['restart_required']:
        raise StoreError('Process restart required: loaded Forge/compiler source differs from disk ('
                         + ', '.join(identity['changed_sources']) + '). Validation was not issued.', 503)
    return identity


def accepted(rows):
    return [row for row in rows if row.get('status') == 'accepted']


def strings(value):
    if isinstance(value, list):
        return [str(x) if isinstance(x, str) else encode(x) for x in value]
    return [str(value)] if value not in (None, '') else []


def task_cards(project):
    project = C.validate_project(project)
    branch = C.active_branch(project)
    statements = {row['id']: row for row in accepted(branch['statements'])}
    entities = branch['entities']
    cards = []
    for unit in accepted(entities['units']):
        refs = unit.get('requirement_ids', [])
        cards.append({'id': unit['id'], 'component_id': unit.get('component_id'),
                      'objective': unit.get('objective') or unit['text'],
                      'inputs': unit.get('inputs', []), 'outputs': unit.get('outputs', []),
                      'paths': unit.get('paths', []),
                      'dependencies': unit.get('dependencies', []),
                      'verification': unit.get('checks', []),
                      'forbidden_assumptions': unit.get('forbidden_assumptions', []),
                      'requirements': [{'id': ident, 'text': statements[ident]['text'],
                                        **({'fact': deepcopy(statements[ident]['fact'])}
                                           if 'fact' in statements[ident] else {})}
                                       for ident in refs if ident in statements],
                      'missing_requirement_ids': [ident for ident in refs if ident not in statements],
                      'invariants': [{'id': row['id'], 'text': row['text'], 'criterion_ids': row.get('criterion_ids', [])}
                                     for row in accepted(entities['invariants']) if unit['id'] in row.get('unit_ids', [])],
                      'acceptance_criteria': [{key: row[key] for key in ('id', 'requirement_ids', 'observable', 'measurement', 'expected')}
                                              for row in accepted(entities['criteria']) if set(refs) & set(row.get('requirement_ids', []))],
                      'forbidden_behavior': [{key: row[key] for key in ('id', 'text', 'requirement_ids', 'negative_check') if key in row}
                                             for row in accepted(entities['forbidden']) if set(refs) & set(row.get('requirement_ids', []))],
                      'invariant_ids': [row['id'] for row in accepted(entities['invariants']) if unit['id'] in row.get('unit_ids', [])],
                      'defines': unit.get('defines', []), 'requires': unit.get('requires', [])})
    return cards


def construction_plan(project):
    blocks = []
    for card in task_cards(project):
        objective = card['objective']
        lines = [objective if objective.startswith('Ask the model to ') else 'Ask the model to make ' + objective.rstrip('.') + '.']
        lines.extend(C.requirement_text(row) for row in card['requirements'])
        lines += ['Input ' + value for value in strings(card['inputs'])]
        lines += ['Produce ' + value for value in strings(card['outputs'])]
        # Quote these literal contracts so embedded newlines/quotes remain data
        # in the human plan as well as in the native JSON instruction capsule.
        lines += ['Declared path ' + encode(value) for value in card['paths']]
        lines += ['Defines symbol ' + encode(value) for value in card['defines']]
        lines += ['Requires symbol ' + encode(value) for value in card['requires']]
        names = [row['id'] for row in card['requirements']] + strings(card['dependencies'])
        lines += ['Use only ' + (', '.join(names) if names else 'the explicit inputs in this unit') + '.']
        lines += ['Do not assume ' + value for value in strings(card['forbidden_assumptions'])]
        lines += ['Preserve invariant ' + row['text'] for row in card['invariants']]
        lines += ['Never ' + row['text'] for row in card['forbidden_behavior']]
        lines += ['Check ' + value for value in strings(card['verification'])]
        lines += ['Check ' + row['observable'] + ' using ' + row['measurement'] + '; expected: ' + row['expected']
                  for row in card['acceptance_criteria']]
        lines.append('Finish this step.')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def _name(prefix, ident):
    return prefix + hashlib.sha256(ident.encode()).hexdigest()[:16]


def native_source(project):
    from symblic.spec.sheets import literal
    branch = C.active_branch(project)
    statements = accepted(branch['statements'])
    entities = branch['entities']
    units = accepted(entities['units'])
    cards = {row['id']: row for row in task_cards(project)}
    req_names = {row['id']: _name('requirement_', row['id']) for row in statements}
    unit_names = {row['id']: _name('work_', row['id']) for row in units}
    # Only explicit unit dependencies determine order. Cycles/refused references
    # remain errors instead of silently receiving all earlier conversation.
    ordered, remaining = [], list(units)
    while remaining:
        done = {row['id'] for row in ordered}
        ready = [row for row in remaining if all(dep in done or dep in req_names
                 for dep in row.get('dependencies', []))]
        if not ready:
            raise StoreError('Native export requires acyclic, explicit accepted unit or requirement dependencies.')
        ready.sort(key=lambda row: row['id'])
        ordered.extend(ready)
        ids = {row['id'] for row in ready}
        remaining = [row for row in remaining if row['id'] not in ids]
    lines = ['program Forge specification.', 'use profile=verified, context=none, determine=false, solve=false.']
    mapping = []
    for row in sorted(statements, key=lambda item: item['id']):
        start = len(lines) + 1
        # Split physical lines so diagnostics map precisely even for pasted text.
        lines.extend(('let ' + req_names[row['id']] + ' = ' + literal(C.requirement_text(row)) + '.').splitlines())
        mapping.append({'id': row['id'], 'kind': 'requirement', 'start_line': start, 'end_line': len(lines)})
    for row in ordered:
        card = cards[row['id']]
        if card['missing_requirement_ids']:
            raise StoreError('A unit references requirements that are not accepted.')
        if not card['outputs'] or not card['verification']:
            raise StoreError('Every exported implementation unit needs explicit output and verification.')
        dependencies = list(dict.fromkeys([r['id'] for r in card['requirements']] + card['dependencies']))
        context = [req_names.get(ident) or unit_names.get(ident) for ident in dependencies]
        if any(value is None for value in context):
            raise StoreError('A native unit references an unsupported dependency.')
        prompt = encode({'objective': card['objective'], 'inputs': card['inputs'],
                         'outputs': card['outputs'], 'verification': card['verification'],
                         'paths': card['paths'], 'defines': card['defines'], 'requires': card['requires'],
                         'forbidden_assumptions': card['forbidden_assumptions'],
                         'invariants': card['invariants'], 'acceptance_criteria': card['acceptance_criteria'],
                         'forbidden_behavior': card['forbidden_behavior'],
                         'dependency_names': {ident: req_names.get(ident) or unit_names.get(ident)
                                              for ident in dependencies},
                         'scope': 'Return the bounded unit artifact as text. Use only the explicitly supplied context. '
                                  'Report verification evidence; prose instructions are not executable tests.'})
        start = len(lines) + 1
        source = f'ask {unit_names[row["id"]]}: Text {literal(prompt)}'
        if context:
            source += ' from ' + ', '.join(context)
        source += ' with context=none, determine=false, solve=false, retries=0.'
        lines.extend(source.splitlines())
        lines.append('show ' + unit_names[row['id']] + '.')
        mapping.append({'id': row['id'], 'kind': 'unit', 'start_line': start, 'end_line': len(lines)})
    if not units:
        for row in sorted(statements, key=lambda item: item['id']):
            lines.append('show ' + req_names[row['id']] + '.')
    if not statements and not units:
        raise StoreError('Accept at least one requirement before creating a Symblic export.')
    return '\n'.join(lines) + '\n', mapping


def compiler_identity():
    source = source_identity()
    if source['restart_required']:
        return {'kernel': None, 'exporter': VERSION, **source}
    from symblic.kernel import language as S
    return {'kernel': deepcopy(S.kernel_id()), 'exporter': VERSION, **source}


def _require_revision(project, revision):
    """Exports mint bytes against one exact revision; a caller that expected another
    revision gets the forge's revision conflict, never a silently stale artifact."""
    if revision is not None and revision != project['revision']:
        raise StoreError('This project changed in another operation. Reload its current revision.', 409)
    return project['revision']


def validate(project, source=None, revision=None):
    _require_current_source()
    _require_revision(project, revision)
    from symblic.authoring import editor_diagnostics as D
    project = C.validate_project(project)
    if source is None:
        exact, mapping = native_source(project)
    else:
        exact, mapping = source, []
    if not isinstance(exact, str):
        raise StoreError('Symblic source must be text.')
    if len(exact.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise StoreError('Native Symblic source is limited to 400,000 UTF-8 bytes; select a smaller explicit unit.', 413)
    result = D.check(exact, language='native', execution_profile='verified')
    identity = compiler_identity()
    if identity['restart_required']:
        raise StoreError('Source changed during validation. Restart the process and validate again; no receipt was issued.', 503)
    # Compiler functions are authoritative; never infer success from text labels.
    out = {'ok': result.get('ok') is True, 'source': exact,
           'source_sha256': hashlib.sha256(exact.encode()).hexdigest(),
           'fingerprint': C.fingerprint(project), 'source_revision': project['revision'],
           'generated': source is None, 'mapping': mapping,
           'compiler': identity, 'diagnostics': result,
           'scope': 'Existing native syntax/static checker only. No model, shell, project effect or unit verification ran.',
           'verification': {'executed': False, 'checks': 'Explicit observable unit instructions remain in task cards.'}}
    diagnostics = result.get('diagnostics', result.get('errors', []))
    out['lineage'] = [{'diagnostic': d, 'ids': [m['id'] for m in mapping
                      if isinstance(d.get('line'), int) and m['start_line'] <= d['line'] <= m['end_line']]}
                     for d in diagnostics]
    return out


def spec_sheet(project):
    branch = C.active_branch(project)
    return {'title': project['title'], 'fingerprint': C.fingerprint(project),
            'constants': [{'statement_id': r['id'], **r['fact']} for r in accepted(branch['statements'])
                          if isinstance(r.get('fact'), dict)],
            'requirements': [{'id': r['id'], 'text': r['text'], 'dimension': r['dimension']}
                             for r in accepted(branch['statements'])],
            'interfaces': accepted(branch['entities']['components']),
            'dimensions': [{'statement_id': r['id'], 'dimension': r['dimension'], **r['fact']}
                           for r in accepted(branch['statements']) if isinstance(r.get('fact'), dict) and r['fact'].get('unit')],
            'model_output_schemas': [{'id': r['id'], 'app': r['app'], 'output_schema': r['output_schema'],
                                     'requirement_ids': r.get('requirement_ids', [])}
                                    for r in accepted(branch['entities']['models']) if 'output_schema' in r],
            'examples': [{'id': r['id'], 'text': r['text'], 'result': r.get('result', ''),
                          'requirement_ids': r.get('requirement_ids', []),
                          **({'file_artifact_id': r['file_artifact_id']} if r.get('file_artifact_id') else {})}
                         for r in accepted(branch['entities']['evidence']) if r.get('evidence_type') == 'example'],
            'acceptance_tests': accepted(branch['entities']['criteria']),
            'forbidden_behavior': accepted(branch['entities']['forbidden']),
            'units': task_cards(project)}


def brief(project):
    branch = C.active_branch(project)
    analysis = C.analyze(project)
    sections = ['# ' + project['title'], '## Original intention', project['original_idea'],
                '## Accepted requirements', analysis['accepted_prompt']]
    for kind, label in [('objectives', 'Objectives'), ('architectures', 'Architecture'),
                        ('agents', 'Agent design'), ('cluster', 'Cluster design'), ('criteria', 'Acceptance criteria')]:
        sections += ['## ' + label] + ['- ' + r['text'] for r in accepted(branch['entities'][kind])]
    sections += ['## Scope', encode(branch['scope']), '## Unresolved questions']
    sections += ['- [' + q.get('severity', 'OPEN') + '] ' + q['text'] for q in analysis['questions']
                 if q.get('status') not in ('answered', 'dismissed')]
    return '\n\n'.join(sections) + '\n'


def artifact(project, kind, revision=None):
    _require_revision(project, revision)
    metadata = {'format': kind, 'project_id': project['id'], 'source_revision': project['revision'],
                'fingerprint': C.fingerprint(project), 'exporter': VERSION}
    if kind == 'manifest':
        content, mime, extension = C.export_manifest(project), 'application/json', 'json'
    elif kind == 'brief':
        content, mime, extension = brief(project), 'text/markdown', 'md'
    elif kind == 'prompt':
        content, mime, extension = C.analyze(project)['accepted_prompt'], 'text/plain', 'txt'
    elif kind == 'construction':
        content, mime, extension = construction_plan(project), 'text/plain', 'txt'
    elif kind == 'tasks':
        content, mime, extension = task_cards(project), 'application/json', 'json'
    elif kind == 'sheet':
        content, mime, extension = spec_sheet(project), 'application/json', 'json'
    elif kind == 'symblic':
        validation = validate(project, revision=revision)
        if not validation['ok']:
            raise StoreError('The current compiler rejected the generated native export. Inspect its validation diagnostics.')
        content, mime, extension = validation['source'], 'text/plain', 'sym'
        metadata['validation'] = validation
    else:
        raise StoreError('Unknown export format.')
    text = encode(content) if mime == 'application/json' else content
    return {**metadata, 'content': content, 'text': text, 'media_type': mime,
            'filename': 'forge-' + kind + '.' + extension, 'sha256': hashlib.sha256(text.encode()).hexdigest()}

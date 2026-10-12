"""Task-card builds: compile a spec sheet into a checked build with complete dependency cards and portable receipts.

What it is for: the newer of the two spec-sheet compilers. Where symblic.spec.sheets (the one the kits use) shows a
model a unit's contract and the tested code of the units it uses, this compiler gives every model request a *task
card*: the unit's exact contract plus the complete declared dependency closure (contracts and accepted code), within
a measured context budget that cannot silently drop a dependency. Accepted units are rechecked locally and sealed
into portable records (symblic.spec.contracts) so a later build, or another machine, can reuse them after an edit
without asking a model again, and the assembled output can be pinned to an exact SHA-256.

Commands (python3 -m symblic.spec.build ..., or `tools/symblic spec ...`):

    check SHEET.md                         plan the units and validate the settings; no model
    compile SHEET.md --by APP [...]        print the native program (or --json for the whole envelope); no model
    run SHEET.md --by APP --dir NEW_DIR    run it with the kernel's runner (asks the models named by --by)
    checkpoint RUN_DIR / manifest RUN_DIR  recheck a run's accepted units locally and export portable records
    verify MANIFEST.json                   check a manifest's integrity and optional output hash

Options include --samples, --retries, --rounds, --budget (context characters per card), --presentation
full|compact, --declaration-contracts FILE, --external NAME, --keep RUN_DIR / --manifest FILE (reuse), --redo NAME
and --output-sha256 HEX. Task-card builds do not support `Answers normalized: yes` or `Given: yes`; use
symblic.spec.sheets for sheets written for the smallest models.

The compiler emits ordinary statements. The complete declared dependency closure is a required context value; the
verified context budget cannot silently drop it. Checkpoints recheck recorded code locally before issuing portable
host receipts. Import, compilation and checkpoint inspection perform no model call. The run command uses the kernel's
runner and the applicators of symblic.providers; it adds no provider backend, scheduler or execution language.

Depends on: symblic.kernel (language, run, execution_pins), symblic.js (check, contract), symblic.lang.abstraction,
symblic.spec (sheets, contracts) and, for `run`, symblic.providers.applicators.
Status: implemented and tested with fake models in tests/spec/; the kits' recorded builds used symblic.spec.sheets.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import os
import time
from pathlib import Path

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.js import contract as JSC
from symblic.lang import abstraction as L
from symblic.spec import sheets as SP
from symblic.spec import contracts as C

VERSION = 2
PRESENTATIONS = ('full', 'compact')
EXTERNAL_RESOLUTION = 'declared_names_only_see_setup_and_runtime_contract'
CONTRACT_FIELDS = {'version', 'title', 'intro', 'shared', 'externals', 'unit'}
UNIT_FIELDS = {'names', 'heading', 'body', 'uses', 'setup', 'examples'}


# the compiler's own sources, as paths from the repository root; their bytes are part of a build's runtime identity
COMPILER_SOURCES = ('symblic/spec/sheets.py', 'symblic/spec/build.py', 'symblic/spec/contracts.py')
_ROOT = Path(__file__).resolve().parents[2]


def runtime_identity(*, presentation='compact', declaration_contracts=None):
    return {'kernel': S.kernel_id(), 'javascript': JS.VERSION, 'compiler_version': VERSION,
            'compiler_settings': {'version': 1, 'presentation': presentation,
                                  'declaration_contracts': declaration_contracts or {}},
            'declarations': JSC.VERSION if declaration_contracts else None,
            'compiler_sources': {name: hashlib.sha256((_ROOT / name).read_bytes()).hexdigest()
                                 for name in COMPILER_SOURCES}}


def _literal(value):
    return L.literal(S.from_json(value))


def compiler_settings(plan, presentation='compact', declaration_contracts=None):
    """Validate options for an existing C.plan result without dispatching a parser/model."""
    if type(presentation) is not str or presentation not in PRESENTATIONS:
        raise SP.SheetError('presentation must be full or compact.')
    policies = {} if declaration_contracts is None else declaration_contracts
    units = {row['id']: row for row in plan['units']}
    if type(policies) is not dict or set(policies) - set(units):
        raise SP.SheetError('Declaration policies must map exact plan unit IDs to contracts.')
    normalized = {}
    for ident, policy in policies.items():
        try:
            # Contract validation only: never parse or execute candidate code here.
            JSC._request('', policy)
        except S.SymblicError as error:
            raise SP.SheetError('Declaration contract: ' + error.message) from None
        if set(policy['exports']) != set(units[ident]['exports']):
            raise SP.SheetError('Declaration exports must exactly match the selected unit names.')
        normalized[ident] = {'version': 1, 'exports': dict(sorted(policy['exports'].items()))}
    project = None
    for row in units.values():
        if set(row['contract']) != CONTRACT_FIELDS or set(row['contract']['unit']) != UNIT_FIELDS:
            raise SP.SheetError('Unknown task fields cannot be omitted from the model presentation.')
        fields = {key: value for key, value in row['contract'].items() if key != 'unit'}
        if project is not None and fields != project:
            raise SP.SheetError('Task-card contracts must share identical project fields before deduplicating their presentation.')
        project = fields
    return {'version': 1, 'presentation': presentation, 'declaration_contracts': dict(sorted(normalized.items()))}


def _instruction(unit, policy):
    kinds = ('Exact declaration kinds: ' + json.dumps(policy['exports'], ensure_ascii=False) + '. '
             if policy else 'Use named top-level function or const declarations. ')
    return ('Write JavaScript source for ' + unit['heading'] + '. Required declaration names: '
            + ', '.join(unit['names']) + '. ' + kinds
            + 'Implement the stated behavior, not a task-card interpreter. A top-level return is invalid. '
            'Use the supplied dependency code without copying or redefining it. '
            'Setup and examples are checks, not additional output code. '
            'Return only one fenced js block containing this unit; no prose, wrapper, module or export.')


def _compact_parts(record, row, policy):
    """Lossless task-field projection; opaque IDs/hashes remain in the full record.

    Project-wide fields are identical in every contract by C.plan construction.
    Display them once, explicitly applying them to this unit and every dependency.
    A future additional task field is rejected by compiler_settings until mapped here.
    """
    parts = [('text', 'PROJECT CONTRACT (applies to this unit and each dependency):\n')]
    for key in ('version', 'title', 'intro', 'shared', 'externals'):
        parts += [('text', key + ': '), ('name', record + '.contract.' + key), ('text', '\n')]
    parts += [('text', '\nREQUESTED UNIT:\n'), ('name', 'spec_card_unit(' + record + '.contract.unit)')]
    for key in ('external_requirements', 'external_resolution'):
        parts += [('text', key + ': '), ('name', record + '.' + key), ('text', '\n')]
    if policy:
        parts += [('text', 'declaration_contract: '), ('name', record + '.declaration_contract'), ('text', '\n')]
    for index, _ in enumerate(row['closure'], 1):
        dep = record + f'.dependencies[{index}]'
        parts.append(('text', f'\nDEPENDENCY {index} (already supplied; do not redeclare):\n'))
        parts.append(('name', 'spec_card_unit(' + dep + '.contract.unit)'))
        parts += [('text', 'EXACT DEPENDENCY CODE:\n'), ('name', dep + '.code'), ('text', '\nEND DEPENDENCY CODE\n')]
    return parts


def _task_card_sheet(parsed):
    """Refuse the two directives only the legacy compiler (symblic.spec.sheets) implements."""
    if parsed.get('normalize'):
        raise SP.SheetError('`Answers normalized: yes` is a legacy-build directive; task-card builds do not normalize '
                            'answers (remove the line or build with symblic.spec.sheets)')
    given = [unit['heading'] for unit in parsed['units'] if unit.get('given')]
    if given:
        raise SP.SheetError('`Given: yes` is a legacy-build directive (unit ' + given[0] + '); task-card builds ask a '
                            'model for every unit (remove the line or build with symblic.spec.sheets)')


def compile_cards(text, applicators, *, samples=1, retries=3, rounds=3, budget=24000,
                  artifacts=None, redo=(), externals=(), presentation='compact', declaration_contracts=None,
                  required_output_sha256=None, inherit_applicators=False):
    """Return a native program and its inspectable dependency/reuse plan.

Only artifacts with unchanged contracts, dependencies and runtime are kept;
every kept unit is nevertheless executed against the current examples again.
Independent branches survive edits to another branch, regardless of sheet order.
"""
    if type(text) is not str or len(text) > S.MAX_SOURCE:
        raise SP.SheetError('The sheet must be bounded text.')
    if type(inherit_applicators) is not bool:
        raise SP.SheetError('inherit_applicators must be a Boolean.')
    if inherit_applicators:
        if applicators is not None:
            raise SP.SheetError('Inherited routing requires applicators=None; the host chooses the applicator.')
    elif (type(applicators) is not list or not 1 <= len(applicators) <= 12
            or any(type(a) is not str or not a.strip() or len(a) > 300 for a in applicators)):
        raise SP.SheetError('Supply 1..12 named applicators.')
    for name, value, high in (('samples', samples, 25), ('retries', retries, 5),
                               ('rounds', rounds, 20), ('budget', budget, 262144)):
        minimum = 0 if inherit_applicators and name == 'retries' else 1
        if type(value) is not int or not minimum <= value <= high:
            raise SP.SheetError(f'{name} must be an integer from {minimum} to {high}.')
    parsed = SP.parse(text)
    _task_card_sheet(parsed)
    try:
        plan = C.plan(parsed, externals=externals, required_output_sha256=required_output_sha256)
        settings = compiler_settings(plan, presentation, declaration_contracts)
        runtime = runtime_identity(presentation=presentation, declaration_contracts=settings['declaration_contracts'])
        artifacts = {} if artifacts is None else artifacts
        decisions = C.reuse_decisions(plan, artifacts, runtime_identity=runtime, redo=redo)
    except C.ContractError as error:
        raise SP.SheetError(f'{error.code}: {error}') from None
    units = {u['id']: u for u in plan['units']}
    # Refuse impossible exposed-check shapes before the first model is asked.
    for row in units.values():
        unit = row['contract']['unit']
        try:
            JS._cases(unit['examples'], None)
            JS._pieces([unit['setup']], 'test setup', None)
        except S.SymblicError as error:
            raise SP.SheetError(f'Unit {unit["heading"]}: {error.message}') from None
    kept = [ident for ident in plan['order'] if decisions[ident]['reusable']]
    out = ['program Build with task cards.',
           ('note Compiled from the spec sheet with complete declared dependency cards; '
            'each unit has fresh model context and checked examples.'),
           'use profile=verified, context=none' + ('' if inherit_applicators else ', by=' + _literal(applicators))
           + f', route=search, samples={samples}, retries={retries}, rounds={rounds}, budget={budget}.',
           'let spec_plan_json = ' + SP.literal(json.dumps(plan, ensure_ascii=False, separators=(',', ':'))) + '.',
           'let spec_runtime_json = ' + SP.literal(json.dumps(runtime, sort_keys=True, separators=(',', ':'))) + '.']
    if presentation == 'compact':
        fields = []
        for key in ('heading', 'names', 'body', 'uses', 'setup', 'examples'):
            fields += [('text', key + ': '), ('name', 'unit.' + key), ('text', '\n')]
        out.append('function spec_card_unit(unit) = ' + SP.literal_parts(fields) + '.')
    # Bind each exact contract once. Repeating its literal for every transitive
    # edge can exceed the native source bound before any model is dispatched.
    # Cards still carry full values; these are shared source references only.
    first_contract = units[plan['order'][0]]['contract']
    project = {key: value for key, value in first_contract.items() if key != 'unit'}
    out.append('let spec_project_contract = ' + _literal(project) + '.')
    for ident in plan['order']:
        row = units[ident]
        fields = [key + ': spec_project_contract.' + key for key in ('version', 'title', 'intro', 'shared', 'externals')]
        fields.append('unit: ' + _literal(row['contract']['unit']))
        out.append('let contract_' + row['binding'] + ' = {' + ', '.join(fields) + '}.')
    for index, ident in enumerate(plan['order'], 1):
        row = units[ident]; unit = row['contract']['unit']; var = row['binding']
        card_name = 'card_' + var
        record_name = 'record_' + var
        policy = settings['declaration_contracts'].get(ident)
        dependencies = []
        for dep in row['closure']:
            parent = units[dep]
            dependencies.append('{unit_id: ' + _literal(dep) + ', contract: '
                                + 'contract_' + parent['binding'] + ', code: ' + parent['binding'] + '}')
        external_requirements = sorted({name for dep in [ident, *row['closure']] for name in units[dep]['external_uses']})
        card = '{kind: "spec_task_card", version: 1, unit_id: ' + _literal(ident)
        card += ', contract_sha256: ' + _literal(row['contract_sha256'])
        card += ', contract: contract_' + var + ', dependencies: [' + ', '.join(dependencies) + ']'
        card += ', external_requirements: ' + _literal(external_requirements)
        card += ', external_resolution: ' + _literal(EXTERNAL_RESOLUTION)
        if policy:
            card += ', declaration_contract: ' + _literal(policy)
        card += '}'
        out += ['', f'# unit {index} of {len(units)}: {unit["heading"]}' + (' (kept)' if ident in kept else ''),
                'let ' + record_name + ' = ' + card + '.',
                'let ' + card_name + ' = ' + (record_name if presentation == 'full' else
                    SP.literal_parts(_compact_parts(record_name, row, policy))) + '.']
        if ident in kept:
            out.append('let ' + var + ' = ' + SP.literal(artifacts[ident]['code']) + '.')
        else:
            out.append(f'ask {var}: Code js ' + SP.literal(_instruction(unit, policy)) + f' from {card_name}.')
        if policy:
            declaration = 'declarations_' + var
            out.append(f'let {declaration} = js_declarations_check({var}, {_literal(policy)}).')
            out.append(f'assert {declaration}.passed because {declaration}.report.' if ident in kept else
                       f'ensure {declaration}.passed else retry because {declaration}.report.')
        pieces = ([SP.literal(unit['setup'])] if unit['setup'] else [])
        pieces += [units[dep]['binding'] for dep in row['closure']] + [var]
        test = 'test_' + var[5:]
        out.append(f'let {test} = js_test([{", ".join(pieces)}], {_literal(unit["examples"])}).')
        out.append(f'assert {test}.passed because {test}.report.' if ident in kept else
                   f'ensure {test}.passed else retry because {test}.report.')
        out.append('forget ' + card_name + '.')
        out.append('forget ' + record_name + '.')
    # Isolation checks dependency declarations; whole-assembly checks also catch
    # name replacement and a later piece interfering with an earlier contract.
    all_code = [units[ident]['binding'] for ident in plan['assembly_order']]
    for index, ident in enumerate(plan['order']):
        unit = units[ident]['contract']['unit']
        pieces = ([SP.literal(unit['setup'])] if unit['setup'] else []) + all_code
        out += [f'let assembly_check_{index} = js_test([{", ".join(pieces)}], {_literal(unit["examples"])}).',
                f'assert assembly_check_{index}.passed because assembly_check_{index}.report.']
    out += ['let spec_code = join([' + ', '.join(all_code) + '], "\\n\\n").',
            'let spec_output = replace(' + SP.literal(plan['sheet']['template']['text'])
            + ', ' + SP.literal(SP.PLACEHOLDER) + ', spec_code).']
    if plan['sheet']['template']['file'].lower().endswith('.js'):
        for index, ident in enumerate(plan['order']):
            unit = units[ident]['contract']['unit']
            pieces = ([SP.literal(unit['setup'])] if unit['setup'] else []) + ['spec_output']
            out += [f'let output_check_{index} = js_test([{", ".join(pieces)}], {_literal(unit["examples"])}).',
                    f'assert output_check_{index}.passed because output_check_{index}.report.']
    out.append('show spec_output as ' + _literal(plan['sheet']['template']['file']) + '.')
    source = '\n'.join(out) + '\n'
    if len(source) > S.MAX_SOURCE:
        raise SP.SheetError('Compiled task cards exceed the native source limit; split the sheet.')
    checked = S.check(source, execution_profile='verified')
    if not checked['ok']:
        raise SP.SheetError('Task-card compile: ' + checked['errors'][0]['message'])
    return {'source': source, 'plan': plan, 'runtime': runtime, 'settings': settings,
            'presentation': presentation, 'reuse': decisions, 'kept': len(kept),
            'options': {'profile': 'verified', 'parallel': min(samples, 8), 'max_asks': len(units) + 10,
                        'max_calls': min(10000, max(1, len(units) - len(kept)) * samples * (retries + 1) * rounds)}}


def _output_requirement(*requirements):
    """Combine caller/recorded requirements without weakening or replacing one."""
    values = []
    for value in requirements:
        if value is not None:
            if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise SP.SheetError('Expected output SHA-256 must be 64 lowercase hexadecimal characters.')
            values.append(value)
    if len(set(values)) > 1:
        raise SP.SheetError('Expected output SHA-256 conflicts with the original recorded requirement.')
    return values[0] if values else None


def _saved_output_requirement(folder):
    """Read only the bounded optional CLI envelope; old records need no meta file."""
    try:
        with (folder / 'meta.json').open('rb') as stream:
            raw = stream.read(C.MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(raw) > C.MAX_BYTES:
        raise SP.SheetError('Recorded task-card metadata exceeds its byte limit.')
    try:
        meta = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise SP.SheetError('Recorded task-card metadata is not valid JSON.') from None
    if type(meta) is not dict or ('task_cards' in meta and type(meta['task_cards']) is not dict):
        raise SP.SheetError('Recorded task-card metadata must be a record.')
    return _output_requirement(meta.get('task_cards', {}).get('expected_output_sha256'))


def checkpoint(folder, *, complete=False, expected_output_sha256=None, recheck_seconds=30):
    """Recheck a local run's accepted pieces and return portable dependency memory.

This is an explicit local validation operation, never background polling. A
partial run can recover accepted independent branches. No model is invoked.
"""
    if type(recheck_seconds) is not int or not 1 <= recheck_seconds <= 1800:
        raise SP.SheetError('Recheck time must be an integer from 1 to 1800 seconds.')
    deadline = time.monotonic() + recheck_seconds
    folder = Path(folder)
    source = (folder / 'program.sym').read_text(encoding='utf-8')
    if len(source) > S.MAX_SOURCE:
        raise SP.SheetError('Recorded source exceeds its limit.')
    declarations = {}
    for statement in S.parse(source)['statements']:
        if statement.k == 'let' and statement.name in ('spec_plan_json', 'spec_runtime_json'):
            value = statement.value
            if statement.name in declarations or value.k != 'str' or not all(type(p) is str for p in value.parts):
                raise SP.SheetError('Recorded task-card identities must be unique text literals.')
            declarations[statement.name] = json.loads(''.join(value.parts))
    if set(declarations) != {'spec_plan_json', 'spec_runtime_json'}:
        raise SP.SheetError('This run has no task-card plan; use legacy Keep for an older build.')
    plan = C._plan(declarations['spec_plan_json'])
    expected_output_sha256 = _output_requirement(plan['required_output_sha256'],
                                                  _saved_output_requirement(folder), expected_output_sha256)
    if expected_output_sha256 is not None and plan['required_output_sha256'] is None:
        # Older CLI runs stored the requirement in meta only. Bind it into the
        # exported plan so portable verification cannot silently forget it.
        # Unit contracts and code stay unchanged; this is an added byte identity
        # requirement on their assembly, not a claim about semantic correctness.
        plan = C.plan(plan['sheet'], externals=plan['externals'], required_output_sha256=expected_output_sha256)
    recorded = declarations['spec_runtime_json']
    settings = recorded.get('compiler_settings') if type(recorded) is dict else None
    if (type(settings) is not dict or set(settings) != {'version', 'presentation', 'declaration_contracts'}
            or type(settings['version']) is not int or settings['version'] != 1):
        raise SP.SheetError('Recorded task-card compiler settings are missing or unsupported.')
    settings = compiler_settings(plan, settings['presentation'], settings['declaration_contracts'])
    runtime = runtime_identity(presentation=settings['presentation'], declaration_contracts=settings['declaration_contracts'])
    if declarations['spec_runtime_json'] != runtime:
        raise SP.SheetError('Build runtime changed. Export/recheck with its recorded runtime before importing.')
    accepted = SP.accepted_units(str(folder))
    units = {u['id']: u for u in plan['units']}; artifacts = {}; skipped = {}
    for ident in plan['order']:
        row = units[ident]; unit = row['contract']['unit']; code = accepted.get(row['binding'])
        if code is None or any(dep not in artifacts for dep in row['closure']):
            skipped[ident] = 'missing_code_or_dependency'
            continue
        checks = []
        policy = settings['declaration_contracts'].get(ident)
        if policy:
            declaration = JSC.check(code, policy, deadline=deadline)
            if declaration['status'] == 'budget':
                raise JS.JsError('Task-card declaration recheck exceeded its aggregate budget.', kind='budget')
            if not declaration['passed']:
                skipped[ident] = 'declaration_contract_failed'
                continue
            checks.append({'scope': declaration['scope'], 'passed': True,
                           'subject_sha256': C.code_hash(code), 'contract_sha256': declaration['contract_sha256'],
                           'checker': JSC.VERSION, 'receipt': declaration})
        pieces = ([unit['setup']] if unit['setup'] else [])
        pieces += [artifacts[dep]['code'] for dep in row['closure']] + [code]
        result = JS._js_test(None, None, pieces, unit['examples'], deadline=deadline)
        if not result['passed']:
            skipped[ident] = 'examples_failed'
            continue
        checks += [{'scope': 'declared_dependency_examples', 'passed': True,
                   'subject_sha256': C.code_hash(code), 'examples_sha256': C.digest(unit['examples']),
                   'checker': JS.VERSION}]
        artifacts[ident] = C.record_artifact(plan, ident, code, artifacts,
                                            runtime_identity=runtime, checks=checks)
    output_check = {'required_sha256': expected_output_sha256, 'observed_sha256': None,
                    'status': 'pending_incomplete' if expected_output_sha256 else 'not_required'}
    if expected_output_sha256 is not None and not skipped:
        assembled = plan['sheet']['template']['text'].replace(
            SP.PLACEHOLDER, '\n\n'.join(artifacts[ident]['code'] for ident in plan['assembly_order']))
        output_check['observed_sha256'] = C.code_hash(assembled)
        if output_check['observed_sha256'] != expected_output_sha256:
            raise SP.SheetError('Exact assembled output differs from the original required output SHA-256.')
        output_check['status'] = 'matched'
    if not complete:
        return {'version': VERSION, 'kind': 'spec_build_checkpoint', 'plan': plan,
                'runtime': runtime, 'settings': settings, 'artifacts': artifacts, 'skipped': skipped,
                'output_hash_check': output_check,
                'scope': 'locally_rechecked_examples_and_declared_policies'}
    if skipped:
        raise SP.SheetError('Some units are missing or fail their declared examples or declaration policies.')
    all_code = [artifacts[ident]['code'] for ident in plan['assembly_order']]
    for ident in plan['order']:
        unit = units[ident]['contract']['unit']
        pieces = ([unit['setup']] if unit['setup'] else []) + all_code
        result = JS._js_test(None, None, pieces, unit['examples'], deadline=deadline)
        if not result['passed']:
            raise SP.SheetError('The assembled code fails examples for ' + unit['heading'])
    output = plan['sheet']['template']['text'].replace(SP.PLACEHOLDER, '\n\n'.join(all_code))
    final_js = plan['sheet']['template']['file'].lower().endswith('.js')
    if final_js:
        for ident in plan['order']:
            unit = units[ident]['contract']['unit']
            result = JS._js_test(None, None, ([unit['setup']] if unit['setup'] else []) + [output], unit['examples'],
                                 deadline=deadline)
            if not result['passed']:
                raise SP.SheetError('The final JavaScript artifact fails examples for ' + unit['heading'])
    receipts = {}
    for ident in plan['order']:
        token = artifacts[ident]
        checks = token['checks'] + [{'scope': 'whole_javascript_output_examples' if final_js else 'joined_units_examples',
                                   'passed': True, 'subject_sha256': token['code_sha256'], 'checker': JS.VERSION,
                                   'assembly_sha256': C.code_hash(output if final_js else '\n\n'.join(all_code))}]
        receipts[ident] = C.record_artifact(plan, ident, token['code'], receipts,
                                           runtime_identity=runtime, checks=checks)
    return C.artifact_manifest(plan, receipts, runtime_identity=runtime,
                               expected_output_sha256=expected_output_sha256)


def _run_cards(compiled, *, folder=None, expected_output_sha256=None):
    """CLI bridge: preserve the compiled envelope and use one owned native Run."""
    import signal
    import sys
    import threading

    from symblic.providers import applicators as symblic_apply
    from symblic.kernel import execution_pins as X
    from symblic.kernel.run import Run

    expected_output_sha256 = _output_requirement(compiled['plan']['required_output_sha256'], expected_output_sha256)
    options = json.loads(json.dumps(compiled['options']))
    options['side_effects'] = False
    names = set(X.REQUIRED_FILES)
    names.update(name for name in ('symblic/providers/applicators.py', 'symblic/providers/ollama_call.py')
                 if name in X.PYTHON_FILES and (X.BASE / name).is_file())
    options['execution_pins'] = X.build(compiled['source'], {}, {name: X._sha(X._read(name)) for name in names})
    directory = Path(folder).resolve() if folder else None
    if directory is not None:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise SP.SheetError('Use a new empty task-card run directory; use --keep or --manifest to retain prior work.')
        for name, text in (
                ('program.sym', compiled['source']),
                ('compiler.json', json.dumps(compiled, ensure_ascii=False)),
                ('meta.json', json.dumps({'inputs': {}, 'options': options,
                     'task_cards': {'plan_sha256': compiled['plan']['sha256'], 'runtime': compiled['runtime'],
                                    'settings': compiled['settings'],
                                    'expected_output_sha256': expected_output_sha256}}, ensure_ascii=False))):
            path = directory / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    apps = symblic_apply.Applicators(owner_label='operator (symblic spec run)',
                                     run_id=directory.name if directory else 'spec-cli')
    stop, previous = threading.Event(), {}

    def on_signal(*_args):
        stop.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                handler = signal.getsignal(signum)
                signal.signal(signum, on_signal)
                previous[signum] = handler
            except (ValueError, OSError):
                pass
        native = Run(compiled['source'], {}, apps, {**options, 'stop': stop},
                     folder=str(directory) if directory else None,
                     log=lambda text: print(text, file=sys.stderr, flush=True))
        report = native.execute()
        status, error, output = report['status'], report.get('error'), None
        observed = None
        if status == 'done':
            binding = native.kernel.env.lookup('spec_output')
            if binding is None or type(binding.value) is not str:
                raise SP.SheetError('Completed task-card program has no exact text output.')
            observed = C.code_hash(binding.value)
            if expected_output_sha256 is not None and observed != expected_output_sha256:
                status, error = 'failed', {'kind': 'output_hash', 'message': 'Accepted code differs from the expected output SHA-256.'}
            else:
                output = {'file': compiled['plan']['sheet']['template']['file'],
                          'text': binding.value, 'sha256': observed}
        result = {'status': status, 'accepted': status == 'done', 'output': output, 'error': error,
                  'native_status': report['status'], 'calls': report['calls'],
                  'observed_output_sha256': observed, 'expected_output_sha256': expected_output_sha256,
                  'plan_sha256': compiled['plan']['sha256'], 'runtime': compiled['runtime'],
                  'settings': compiled['settings'], 'options': options,
                  'kept': compiled['kept'], 'reuse': compiled['reuse'], 'report': report}
        if 'determinism_summary' in report:
            result['determinism_summary'] = report['determinism_summary']
        if directory is not None:
            native.store.save('spec-result.json', result)
        return result
    finally:
        stop.set()
        try:
            apps.cancel_all()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Symblic task-card compiler and portable build records.')
    parser.add_argument('command', choices=('check', 'compile', 'run', 'checkpoint', 'manifest', 'verify'))
    parser.add_argument('path')
    parser.add_argument('--by', action='append', default=[])
    parser.add_argument('--dir', help='New empty record directory for spec run; retains the complete compiler envelope')
    parser.add_argument('--samples', type=int, default=1)
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--budget', type=int, default=24000)
    parser.add_argument('--presentation', choices=PRESENTATIONS, default='compact')
    parser.add_argument('--declaration-contracts', help='JSON file mapping stable unit IDs to exact declaration contracts')
    parser.add_argument('--external', action='append', default=[])
    parser.add_argument('--redo', action='append', default=[])
    parser.add_argument('--keep', help='Earlier task-card run to recheck and keep accepted branches from')
    parser.add_argument('--manifest', help='Portable manifest to verify and reuse after local rechecks')
    parser.add_argument('--output-sha256')
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--recheck-seconds', type=int, default=30)
    parser.add_argument('--json', '--agent-json', action='store_true', dest='json')
    args = parser.parse_args(argv)
    try:
        if args.dir and args.command != 'run':
            raise SP.SheetError('--dir is available only for spec run.')
        if args.command in ('checkpoint', 'manifest'):
            result = checkpoint(args.path, complete=args.command == 'manifest',
                                expected_output_sha256=args.output_sha256, recheck_seconds=args.recheck_seconds)
        elif args.command == 'verify':
            result = C.verify_manifest(json.loads(Path(args.path).read_text()),
                                       expected_output_sha256=args.output_sha256,
                                       expected_manifest_sha256=args.manifest_sha256)
        elif args.command == 'check':
            parsed = SP.parse(Path(args.path).read_text())
            _task_card_sheet(parsed)
            plan = C.plan(parsed, externals=args.external)
            policies = json.loads(Path(args.declaration_contracts).read_text()) if args.declaration_contracts else None
            result = {'ok': True, 'plan': plan, 'settings': compiler_settings(plan, args.presentation, policies)}
        else:
            if args.keep and args.manifest:
                raise SP.SheetError('Choose --keep or --manifest, not both.')
            artifacts = None
            if args.keep:
                artifacts = checkpoint(args.keep, recheck_seconds=args.recheck_seconds)['artifacts']
            if args.manifest:
                previous = json.loads(Path(args.manifest).read_text())
                C.verify_manifest(previous, expected_manifest_sha256=args.manifest_sha256)
                artifacts = previous['artifacts']
            result = compile_cards(Path(args.path).read_text(), args.by, samples=args.samples,
                                   retries=args.retries, rounds=args.rounds, budget=args.budget,
                                   redo=args.redo, artifacts=artifacts, externals=args.external,
                                   presentation=args.presentation,
                                   declaration_contracts=json.loads(Path(args.declaration_contracts).read_text())
                                   if args.declaration_contracts else None,
                                   required_output_sha256=args.output_sha256)
            if args.command == 'run':
                result = _run_cards(result, folder=args.dir, expected_output_sha256=args.output_sha256)
            elif not args.json:
                print(result['source'], end='')
                return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('accepted') is False else 0
    except (SP.SheetError, C.ContractError, S.SymblicError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': {'kind': getattr(error, 'code', 'spec'), 'message': str(error)}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

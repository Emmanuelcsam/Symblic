"""Spec-sheet unit contracts: stable identities, dependency order and portable records for task-card builds.

What it is for: making the units of a spec sheet (symblic.spec.sheets) reusable across builds. A unit's contract is
its exact parsed text (names, heading, body, uses, test setup, examples) plus the sheet's shared text; its identity is
a hash of its exports. From the contracts this module derives the dependency order, decides which earlier results
may be reused after an edit, and seals accepted code into portable records. It runs nothing: no executor, provider
or store. symblic.spec.build is its user.

plan(parsed_sheet, externals=(), required_output_sha256=None) resolves declared Uses into stable unit IDs, full
source-contract pins, topological order and layers. Externally supplied helper names must be declared explicitly;
no JavaScript parser or semantic dependency-completeness claim is implied. The parser's derived fields `given` and
`code` are accepted and not hashed (they follow from the body, which is).

Artifacts are {unit_id: token}; record_artifact records exact code plus host-owned check receipts after the host runs
its checker. Each receipt must contain scope, passed=True and subject_sha256 of the code's exact UTF-8 bytes.
Additional bounded JSON receipt fields are retained. This helper checks association, not authenticity or that a
claimed check actually ran. Tokens contain code, not parent histories.

reuse_decisions returns per-unit reusable/recheck/rebuild decisions. context_card requires the complete transitive
artifact closure, serializes it as canonical JSON and budgets card + all fixed_parts in Unicode code points (not
tokens). Manifests carry full contracts/tokens and exact assembly output; optional expected hashes are caller
authority. Canonical JSON is not semantic normalization of code.

Example:
    p = plan(parsed); id = p['order'][0]
    a = record_artifact(p, id, code, {}, runtime_identity=runtime, checks=receipts)
    card = context_card(p, id, {}, runtime_identity=runtime, budget=20000, fixed_parts=(system, schema_text))
    manifest = artifact_manifest(p, {id: a}, runtime_identity=runtime)

Depends on: symblic.kernel.identity only (import-time source identity). Used by: symblic.spec.build,
symblic.spec.compare, symblic.english.pixels.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import math
import re

VERSION = 1
MAX_UNITS = 128
MAX_DEPTH = 32
MAX_NODES = 100000
MAX_BYTES = 8_000_000
MAX_TEXT_BYTES = 1_000_000
MAX_BUDGET = 16 * 1024 * 1024
PLACEHOLDER = '/*UNITS*/'
ASSURANCE = 'exact_bytes_and_host_recorded_checks_not_authenticity_or_semantic_equivalence'
_NAME = re.compile(r'[A-Za-z_$][\w$]*\Z')
_BASE_NAME = re.compile(r'[A-Za-z_$][\w$]*')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class ContractError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def _fail(code, message, **details):
    raise ContractError(code, message, details)


def _bytes(text):
    if type(text) is not str:
        _fail('text', 'Contract text must be an exact string.')
    try:
        value = text.encode('utf-8')
    except UnicodeError:
        _fail('unicode', 'Contract text must be valid UTF-8.')
    if len(value) > MAX_TEXT_BYTES:
        _fail('text_limit', 'A contract text exceeds its byte limit.')
    return value


def _json(value):
    remaining, text_bytes, active = MAX_NODES, 0, set()
    def visit(item, depth):
        nonlocal remaining, text_bytes
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            _fail('structure_limit', 'Contract JSON exceeds its structural limit.')
        kind = type(item)
        if kind is str:
            text_bytes += len(_bytes(item))
            if text_bytes > MAX_BYTES:
                _fail('byte_limit', 'Contract JSON exceeds its byte limit.')
        elif item is None or kind is bool:
            return
        elif kind is int:
            if item.bit_length() > 4096:
                _fail('integer_limit', 'Contract integer exceeds its limit.')
        elif kind in (dict, list):
            if id(item) in active:
                _fail('cycle', 'Cyclic contract JSON is refused.')
            if len(item) > remaining:
                _fail('structure_limit', 'Contract JSON exceeds its structural limit.')
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        _fail('json_type', 'Contract keys must be exact strings.')
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        else:
            _fail('json_type', 'Contracts contain exact JSON values, without floats or custom objects.')
    visit(value, 0)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_BYTES:
        _fail('byte_limit', 'Contract JSON exceeds its byte limit.')
    return raw


def digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def code_hash(code):
    return hashlib.sha256(_bytes(code)).hexdigest()


def _copy(value):
    return json.loads(_json(value))


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail('hash', 'Expected a lowercase SHA-256 identity.')
    return value


def _finite_float(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError('Nonfinite example number')
    return value


def _seal(body):
    return {**_copy(body), 'sha256': digest(body)}


def _unseal(value, kind):
    value = _copy(value)
    shapes = {
        'spec_plan': {'kind','version','sheet','externals','required_output_sha256','units','order','layers',
                      'assembly_order','scope','sha256'},
        'spec_unit_artifact': {'kind','version','unit_id','contract_sha256','exports','code','code_sha256',
                               'runtime_sha256','dependencies','checks','sha256'},
        'spec_artifact_manifest': {'kind','version','plan','runtime_sha256','artifacts','ordered_exports',
                                   'output','assurance','sha256'},
    }
    if (type(value) is not dict or set(value) != shapes[kind] or value.get('kind') != kind
            or type(value.get('version')) is not int or value['version'] != VERSION):
        _fail('schema', 'Unsupported contract record.')
    claimed = _sha(value.get('sha256'))
    body = {k: v for k, v in value.items() if k != 'sha256'}
    if digest(body) != claimed:
        _fail('integrity', 'Contract record hash differs.')
    return value


def plan(sheet, *, externals=(), required_output_sha256=None):
    sheet = _copy(sheet)
    # uses_shown (2026-10-10) is optional: 'code' is the historical prompt shape, 'signatures' names helpers only
    if (type(sheet) is not dict or set(sheet) - {'uses_shown', 'normalize'} != {'title', 'intro', 'shared', 'units', 'template'}
            or sheet.get('uses_shown', 'code') not in ('code', 'signatures') or type(sheet.get('normalize', False)) is not bool):
        _fail('sheet', 'Supply the parsed spec-sheet shape.')
    for key in ('title', 'intro', 'shared'):
        _bytes(sheet[key])
    if not sheet['title'] or type(sheet['units']) is not list or not 1 <= len(sheet['units']) <= MAX_UNITS:
        _fail('units', 'A titled sheet needs 1..128 units.')
    if (type(externals) not in (list, tuple) or len(externals) > MAX_UNITS
            or any(type(x) is not str or not _NAME.fullmatch(x) for x in externals)):
        _fail('externals', 'External helper names must be explicit identifiers.')
    if len(externals) != len(set(externals)) or len(externals) > MAX_UNITS:
        _fail('externals', 'External helper names must be unique and bounded.')
    external_names = sorted(externals)
    if required_output_sha256 is not None:
        _sha(required_output_sha256)
    template = sheet['template']
    if type(template) is not dict or set(template) - {'file', 'text', 'note', 'line'} or not {'file','text','note'} <= template.keys():
        _fail('template', 'A complete assembly template is required.')
    for key in ('file', 'text', 'note'):
        _bytes(template[key])
    if not template['file'] or template['text'].count(PLACEHOLDER) != 1:
        _fail('template', 'Task-card assembly needs one named file and exactly one units placeholder.')
    normalized, owners, bindings = [], {}, set()
    for index, original in enumerate(sheet['units']):
        required = {'names','heading','body','uses','setup','examples'}
        # `given` and `code` are derived by sheets.parse from the body (a `Given: yes` line and the first fenced
        # ```js block). The body is part of the contract, so they add nothing to it and are not hashed; keeping them
        # out keeps every earlier contract hash unchanged. They must still have the parser's types.
        derived = {'line', 'given', 'code'}
        if type(original) is not dict or set(original) - required - derived or not required <= original.keys():
            _fail('unit', 'A unit must retain its complete parsed contract.')
        if type(original.get('given', False)) is not bool or type(original.get('code', '')) is not str:
            _fail('unit', 'A unit\'s derived given/code fields must be a boolean and a string.')
        unit = {k: original[k] for k in sorted(required)}
        exports = unit['names']
        if type(exports) is not list or not exports or len(exports) > MAX_UNITS:
            _fail('exports', 'A unit needs bounded ordered exports.')
        for name in exports:
            if type(name) is not str or not _NAME.fullmatch(name) or name in owners or name in external_names:
                _fail('exports', 'Exports must be valid, unique and distinct from externals.')
            owners[name] = index
        binding = 'unit_' + re.sub(r'\W', '_', exports[0])
        if binding in bindings:
            _fail('binding_collision', 'Distinct exports collide in a generated Symblic binding.')
        bindings.add(binding)
        for key in ('heading','body','setup'):
            _bytes(unit[key])
        if type(unit['uses']) is not list or len(unit['uses']) > MAX_UNITS:
            _fail('uses', 'Uses must be a bounded list of declared names.')
        if type(unit['examples']) is not list or not 1 <= len(unit['examples']) <= 256:
            _fail('examples', 'Every unit needs bounded exposed examples.')
        for example in unit['examples']:
            if type(example) is not list or len(example) != 2:
                _fail('examples', 'Examples are exact call/expected-JSON text pairs.')
            _bytes(example[0]); _bytes(example[1])
            try:
                json.loads(example[1], parse_float=_finite_float,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, RecursionError):
                _fail('examples', 'Expected example output is not finite JSON.')
        ident = 'unit:' + digest(exports)
        contract = {'version': VERSION, 'title': sheet['title'], 'intro': sheet['intro'],
                    'shared': sheet['shared'], 'externals': external_names, 'unit': unit}
        if sheet.get('uses_shown') == 'signatures':      # a different prompt is a different contract; 'code' hashes as before
            contract['uses_shown'] = 'signatures'
        if sheet.get('normalize'):
            contract['normalize'] = True
        normalized.append({'id': ident, 'index': index, 'binding': binding, 'exports': exports,
                           'contract': contract, 'contract_sha256': digest(contract)})
    for unit in normalized:
        dependencies, external_uses = set(), set()
        for raw in unit['contract']['unit']['uses']:
            _bytes(raw)
            match = _BASE_NAME.match(raw)
            if match is None:
                _fail('unknown_use', 'Uses contains no declared identifier.')
            name = match.group(0)
            # Existing sheets may write a signature; preserve it in the contract.
            if name in external_names:
                external_uses.add(name)
            elif name in owners:
                dependencies.add(owners[name])
            else:
                _fail('unknown_use', 'Uses names an undeclared unit or external helper.', name=name)
        unit['dependencies'] = [normalized[i]['id'] for i in sorted(dependencies)]
        unit['external_uses'] = sorted(external_uses)
    pending = {u['id'] for u in normalized}; order, layers = [], []
    while pending:
        ready = [u['id'] for u in normalized if u['id'] in pending and not (set(u['dependencies']) & pending)]
        if not ready:
            _fail('dependency_cycle', 'Unit Uses contains a dependency cycle.')
        layers.append(ready); order.extend(ready); pending.difference_update(ready)
    by_id = {u['id']: u for u in normalized}
    for ident in order:
        closure = set(by_id[ident]['dependencies'])
        for dep in by_id[ident]['dependencies']:
            closure.update(by_id[dep]['closure'])
        by_id[ident]['closure'] = [dep for dep in order if dep in closure]
    normalized_sheet = {**sheet, 'units': [u['contract']['unit'] for u in normalized],
                        'template': {k: template[k] for k in ('file','text','note')}}
    return _seal({'kind': 'spec_plan', 'version': VERSION, 'sheet': normalized_sheet,
                  'externals': external_names, 'required_output_sha256': required_output_sha256,
                  'units': normalized, 'order': order, 'layers': layers,
                  'assembly_order': order, 'scope': 'declared_dependencies_and_exposed_examples'})


def _plan(value):
    checked = _unseal(value, 'spec_plan')
    expected = plan(checked['sheet'], externals=checked['externals'],
                    required_output_sha256=checked['required_output_sha256'])
    if expected != checked:
        _fail('plan_integrity', 'Plan differs from its declared contracts.')
    return checked


def _token(value):
    token = _unseal(value, 'spec_unit_artifact')
    fields = {'kind','version','unit_id','contract_sha256','exports','code','code_sha256',
              'runtime_sha256','dependencies','checks','sha256'}
    if set(token) != fields or code_hash(token['code']) != token['code_sha256']:
        _fail('artifact_integrity', 'Unit artifact bytes or shape differ.')
    for key in ('contract_sha256','runtime_sha256'):
        _sha(token[key])
    if type(token['checks']) is not list or not token['checks']:
        _fail('checks', 'A reusable artifact needs host-recorded accepted checks.')
    for check in token['checks']:
        if (type(check) is not dict or check.get('passed') is not True
                or type(check.get('scope')) is not str or not check['scope']
                or check.get('subject_sha256') != token['code_sha256']):
            _fail('checks', 'Host check receipts must cover these exact code bytes.')
    return token


def reuse_decisions(value, artifacts, *, runtime_identity, redo=()):
    p = _plan(value)
    artifacts = _copy(artifacts)
    if type(artifacts) is not dict:
        _fail('artifacts', 'Artifacts must map stable unit IDs to tokens.')
    runtime = digest(runtime_identity)
    if type(redo) not in (list, tuple, set, frozenset) or any(type(x) is not str for x in redo):
        _fail('redo', 'Redo contains stable unit IDs or declared export names.')
    known = {u['id'] for u in p['units']} | {x for u in p['units'] for x in u['exports']}
    if not set(redo) <= known:
        _fail('redo', 'Redo names an unknown unit.')
    units = {u['id']:u for u in p['units']}; decisions, valid = {}, {}
    for ident in p['order']:
        unit = units[ident]; reasons = []; token = None; state = 'recheck'
        if ident not in artifacts:
            reasons.append('missing_artifact'); state = 'rebuild'
        else:
            try:
                token = _token(artifacts[ident])
                if token['unit_id'] != ident or token['exports'] != unit['exports']:
                    _fail('artifact_identity', 'Artifact belongs to different ordered exports.')
            except ContractError as error:
                reasons.append(error.code); state = 'rebuild'; token = None
        if ident in redo or set(unit['exports']) & set(redo):
            reasons.append('explicit_redo'); state = 'rebuild'
        if token:
            valid[ident] = token
            if token['contract_sha256'] != unit['contract_sha256']:
                reasons.append('contract_changed')
            if token['runtime_sha256'] != runtime:
                reasons.append('runtime_changed')
            expected = [{'unit_id': dep, 'artifact_sha256': valid[dep]['sha256'],
                         'code_sha256': valid[dep]['code_sha256']} for dep in unit['dependencies'] if dep in valid]
            if token['dependencies'] != expected:
                reasons.append('dependency_artifact_changed')
        if any(decisions[dep]['state'] != 'reusable' for dep in unit['dependencies']):
            reasons.append('dependency_not_reusable')
        if not reasons:
            state = 'reusable'
        decisions[ident] = {'state': state, 'reusable': state == 'reusable', 'reasons': reasons,
                            'artifact_sha256': token['sha256'] if token else None}
    return decisions


def _required(p, ident, artifacts, runtime_identity):
    units = {u['id']: u for u in p['units']}
    if type(ident) is not str or ident not in units:
        _fail('unit_id', 'Unknown stable unit ID.')
    decisions = reuse_decisions(p, artifacts, runtime_identity=runtime_identity)
    missing = [dep for dep in units[ident]['closure'] if not decisions[dep]['reusable']]
    if missing:
        _fail('required_dependency', 'Required accepted dependency artifacts are unavailable.', ids=missing)
    return units[ident], units


def record_artifact(value, unit_id, code, artifacts, *, runtime_identity, checks):
    p = _plan(value); artifacts = _copy(artifacts)
    unit, _ = _required(p, unit_id, artifacts, runtime_identity)
    token = _seal({'kind': 'spec_unit_artifact', 'version': VERSION, 'unit_id': unit_id,
                   'contract_sha256': unit['contract_sha256'], 'exports': unit['exports'],
                   'code': code, 'code_sha256': code_hash(code), 'runtime_sha256': digest(runtime_identity),
                   'dependencies': [{'unit_id': dep, 'artifact_sha256': artifacts[dep]['sha256'],
                                     'code_sha256': artifacts[dep]['code_sha256']} for dep in unit['dependencies']],
                   'checks': checks})
    return _token(token)


def context_card(value, unit_id, artifacts, *, runtime_identity, budget, fixed_parts=()):
    p = _plan(value); artifacts = _copy(artifacts)
    unit, units = _required(p, unit_id, artifacts, runtime_identity)
    if type(budget) is not int or not 0 <= budget <= MAX_BUDGET:
        _fail('budget', 'Context budget must be an integer number of characters.')
    if type(fixed_parts) not in (list, tuple) or len(fixed_parts) > MAX_UNITS:
        _fail('fixed_parts', 'Supply every fixed prompt part as a string sequence.')
    for text in fixed_parts:
        _bytes(text)
    payload = {'kind': 'spec_task_card', 'version': VERSION, 'unit_id': unit_id,
               'contract': unit['contract'], 'contract_sha256': unit['contract_sha256'],
               'dependencies': [{'unit_id': dep, 'contract': units[dep]['contract'],
                                 'artifact_sha256': artifacts[dep]['sha256'],
                                 'code_sha256': artifacts[dep]['code_sha256'], 'code': artifacts[dep]['code']}
                                for dep in unit['closure']]}
    external_requirements = sorted({name for ident in [unit_id, *unit['closure']]
                                    for name in units[ident]['external_uses']})
    payload['external_requirements'] = external_requirements
    payload['external_resolution'] = 'declared_names_only_see_setup_and_runtime_contract'
    raw = _json(payload); serialized = raw.decode('utf-8')
    fixed = sum(len(part) for part in fixed_parts); used = fixed + len(serialized)
    if used > budget:
        _fail('context_budget', 'Complete task card and fixed overhead exceed the character budget.',
              required=used, budget=budget, required_ids=unit['closure'])
    return {'payload': payload, 'serialized': serialized, 'sha256': hashlib.sha256(raw).hexdigest(),
            'request_sha256': digest({'payload': payload, 'runtime': runtime_identity,
                                      'fixed_parts': list(fixed_parts), 'budget': budget}),
            'utf8_bytes': len(raw), 'characters': len(serialized), 'unit_count': 1 + len(unit['closure']),
            'manifest': {'unit': 'characters', 'used': used, 'budget': budget, 'fixed_characters': fixed,
                         'fixed_parts_sha256': [code_hash(part) for part in fixed_parts],
                         'included': [{'unit_id': dep, 'artifact_sha256': artifacts[dep]['sha256'],
                                       'code_sha256': artifacts[dep]['code_sha256'], 'required': True}
                                      for dep in unit['closure']], 'omitted': [],
                         'external_requirements': external_requirements,
                         'external_resolution': 'declared_names_only_see_setup_and_runtime_contract',
                         'scope': 'exact_declared_dependency_closure'}}


def artifact_manifest(value, artifacts, *, runtime_identity, expected_output_sha256=None):
    p = _plan(value); artifacts = _copy(artifacts)
    decisions = reuse_decisions(p, artifacts, runtime_identity=runtime_identity)
    if any(not row['reusable'] for row in decisions.values()):
        _fail('assembly_dependencies', 'Every assembled unit needs a current accepted artifact.', decisions=decisions)
    ordered = [artifacts[ident] for ident in p['assembly_order']]
    output = p['sheet']['template']['text'].replace(PLACEHOLDER, '\n\n'.join(a['code'] for a in ordered))
    actual = code_hash(output)
    for expected in (p['required_output_sha256'], expected_output_sha256):
        if expected is not None and _sha(expected) != actual:
            _fail('output_hash', 'Exact assembled output differs from the required output hash.')
    return _seal({'kind': 'spec_artifact_manifest', 'version': VERSION, 'plan': p,
                  'runtime_sha256': digest(runtime_identity), 'artifacts': {a['unit_id']: a for a in ordered},
                  'ordered_exports': [{'unit_id': a['unit_id'], 'exports': a['exports']} for a in ordered],
                  'output': {'file': p['sheet']['template']['file'], 'text': output,
                             'sha256': actual, 'utf8_bytes': len(_bytes(output))},
                  'assurance': ASSURANCE})


def verify_manifest(manifest, *, expected_output_sha256=None, runtime_identity=None, expected_manifest_sha256=None):
    m = _unseal(manifest, 'spec_artifact_manifest'); p = _plan(m['plan'])
    if m['assurance'] != ASSURANCE:
        _fail('assurance', 'Manifest assurance must retain its exact supported scope.')
    if expected_manifest_sha256 is not None and _sha(expected_manifest_sha256) != m['sha256']:
        _fail('manifest_identity', 'Manifest differs from the caller-pinned identity.')
    _sha(m['runtime_sha256'])
    if runtime_identity is not None and digest(runtime_identity) != m['runtime_sha256']:
        _fail('runtime_changed', 'Manifest runtime differs from the supplied current runtime.')
    # Rebuild without claiming the recorded runtime is the present runtime.
    artifacts = m['artifacts']; units = {u['id']: u for u in p['units']}
    if type(artifacts) is not dict or set(artifacts) != set(p['order']):
        _fail('artifacts', 'Manifest must contain exactly the plan artifacts.')
    tokens = {ident: _token(artifacts[ident]) for ident in p['order']}
    for ident, token in tokens.items():
        expected = [{'unit_id': dep, 'artifact_sha256': tokens[dep]['sha256'],
                     'code_sha256': tokens[dep]['code_sha256']} for dep in units[ident]['dependencies']]
        if (token['unit_id'] != ident or token['exports'] != units[ident]['exports']
                or token['contract_sha256'] != units[ident]['contract_sha256']
                or token['runtime_sha256'] != m['runtime_sha256'] or token['dependencies'] != expected):
            _fail('artifact_identity', 'Manifest artifact no longer matches its frozen inputs.')
    ordered = [tokens[ident] for ident in p['assembly_order']]
    output = p['sheet']['template']['text'].replace(PLACEHOLDER, '\n\n'.join(t['code'] for t in ordered))
    actual = code_hash(output)
    expected_output = {'file': p['sheet']['template']['file'], 'text': output, 'sha256': actual,
                       'utf8_bytes': len(_bytes(output))}
    if m['output'] != expected_output or m['ordered_exports'] != [
            {'unit_id':t['unit_id'],'exports':t['exports']} for t in ordered]:
        _fail('output_integrity', 'Manifest output or ordered exports differ from assembly.')
    for expected in (p['required_output_sha256'], expected_output_sha256):
        if expected is not None and _sha(expected) != actual:
            _fail('output_hash', 'Manifest output differs from the caller-required bytes.')
    return {'ok': True, 'manifest_sha256': m['sha256'], 'output_sha256': actual,
            'runtime_current': 'matched' if runtime_identity is not None else 'not_checked',
            'checks': 'host_recorded_not_independently_executed', 'authenticity': 'not_established',
            'semantic_equivalence': 'not_established'}

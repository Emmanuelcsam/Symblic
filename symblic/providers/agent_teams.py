"""Team profiles: a fixed list of applicators (members) that each answer the same statement.

A team is ``{'version': 1, 'members': [member, ...]}``. A member names one applicator exactly (engine, model,
node, effort) plus a perspective for the model (role, characteristics, instruction), optional Ollama sampling
settings (temperature, seed) and a vote weight. ``normalize`` validates a team; ``member_app`` turns a member
into the applicator spec the kernel runs (symblic.kernel.language.parse_applicator); ``lower_checked`` rewrites a
compiled program so each of its asks is sampled once per member and decided by the kernel's ordinary vote and
checks; ``member_system`` adds the member's profile to the system text.

Used by the kernel runner and evidence records (symblic.kernel.run, symblic.kernel.evidence) and by the English
and Forge front ends. Pure validation and serialization: no discovery, provider calls or workers on import.
A profile describes the operator's requested perspective, never authority or proof: roles and agreement are not
evidence that an answer is right.

The ``project`` lane and ``capability_catalog`` describe teams of coding agents run by an agent hub. They were
written for the private host Symblic grew up in; this repository ships no such hub, so they only validate
and describe.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import math
from numbers import Real
import re

VERSION = 1
MAX_MEMBERS = 24
TEXT_ENGINES = frozenset(('ollama', 'claude', 'codex', 'agy', 'mistral', 'copilot', 'chatgpt', 'gemini'))
ALIASES = {'local': 'ollama', 'gpt': 'chatgpt'}
FIELDS = {'id', 'engine', 'model', 'node', 'effort', 'role', 'characteristics', 'instruction', 'settings', 'weight'}
LIMITS = {'id': 64, 'engine': 40, 'model': 160, 'node': 64, 'effort': 20,
          'role': 160, 'characteristics': 2000, 'instruction': 6000}


class TeamError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


# Reasoning-effort words each agent CLI accepted (October 2026). They change between CLI releases: check the
# CLI's --help before relying on one. 'checked' members pass the word to their applicator; 'project' members
# pass it to a coding agent ('' is the agent's default).
CHECKED_EFFORTS = {'claude': ('low', 'medium', 'high', 'xhigh', 'max'),
                   'codex': ('minimal', 'low', 'medium', 'high', 'xhigh'),
                   'agy': ('low', 'medium', 'high')}
PROJECT_EFFORTS = {'claude': ('', 'low', 'medium', 'high', 'xhigh', 'max'),
                   'codex': ('', 'low', 'medium', 'high', 'xhigh', 'max'),
                   'agy': ('', 'low', 'medium', 'high', 'max'),
                   'copilot': ('', 'low', 'medium', 'high', 'xhigh', 'max')}


def efforts(engine, *, lane='checked'):
    """The effort words a member of `engine` may request in `lane` (empty: the engine takes none)."""
    table = PROJECT_EFFORTS if lane == 'project' else CHECKED_EFFORTS
    return list(table.get(engine, ()))


def _text(value, field, required=False):
    if (type(value) is not str or len(value) > LIMITS[field] or '\0' in value
            or any(0xD800 <= ord(c) <= 0xDFFF for c in value)
            or (required and not value.strip())):
        raise TeamError(f'Member {field} must be text within {LIMITS[field]} characters' +
                        (' and cannot be empty.' if required else '.'))
    return value


def normalize_member(raw, *, lane='checked'):
    if lane not in ('checked', 'forge', 'project'):
        raise TeamError('Unknown team execution lane.')
    if type(raw) is not dict or set(raw) - FIELDS:
        raise TeamError('A member uses id, engine, model, node, effort, role, characteristics, instruction, settings and weight only.')
    out = {key: _text(raw.get(key, ''), key, key in ('id', 'engine', 'node')) for key in LIMITS}
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', out['id']):
        raise TeamError('Member IDs start with a letter and contain letters, digits, underscore or hyphen.')
    out['engine'] = ALIASES.get(out['engine'], out['engine'])
    # one exact machine: a configured host name or host[:port] (symblic.providers.applicators), never a placement word
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,57}(?::[0-9]{1,5})?', out['node']) or out['node'] in ('auto', 'any'):
        raise TeamError('Select one exact registered device for every member; automatic placement is not an exact team selection.')
    if out['engine'] not in TEXT_ENGINES:
        raise TeamError(f'{out["engine"]} is not an individual checked/proposal adapter. Use its explicit project orchestration controls; no substitute was selected.')
    if out['model'] and not re.fullmatch(r'[\w.:/-]{1,160}', out['model']):
        raise TeamError('Invalid model identifier; use the exact provider model name.')
    if out['engine'] == 'ollama' and not out['model']:
        raise TeamError('Each Ollama member needs an explicit installed model.')
    effort = out['effort']
    if effort and effort not in efforts(out['engine'], lane=lane):
        raise TeamError('This engine does not support that reasoning-effort request.')
    if effort and out['engine'] == 'agy' and not out['model']:
        raise TeamError('Antigravity effort needs an explicit model; otherwise the adapter cannot honor it.')
    settings = raw.get('settings', {})
    if type(settings) is not dict or set(settings) - {'temperature', 'seed'}:
        raise TeamError('Supported member settings are temperature and seed only.')
    if settings and lane == 'project':
        raise TeamError('Project coding agents do not support temperature or seed; remove these settings rather than silently ignoring them.')
    if settings and out['engine'] != 'ollama':
        raise TeamError('Temperature and seed are supported only for Ollama members; this provider would ignore them.')
    out['settings'] = dict(settings)
    if 'temperature' in settings:
        x = settings['temperature']
        if isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x) or not 0 <= x <= 2:
            raise TeamError('Temperature must be a finite number from 0 to 2.')
        out['settings']['temperature'] = float(x)
    if 'seed' in settings and (type(settings['seed']) is not int or not 0 <= settings['seed'] <= 2147483647):
        raise TeamError('Seed must be an integer from 0 to 2147483647.')
    weight = raw.get('weight', 1)
    if isinstance(weight, bool) or not isinstance(weight, Real) or not math.isfinite(weight) or not .1 <= weight <= 10:
        raise TeamError('Member weight must be a finite number from 0.1 to 10.')
    if lane == 'project' and weight != 1:
        raise TeamError('Sequential project teams do not vote; member weight must remain 1.')
    out['weight'] = float(weight)
    return out


def normalize(spec, *, lane='checked'):
    if type(spec) is not dict or set(spec) != {'version', 'members'} or type(spec['version']) is not int or spec['version'] != VERSION:
        raise TeamError('A team contains version: 1 and members only.')
    if not isinstance(spec['members'], (list, tuple)) or not 1 <= len(spec['members']) <= MAX_MEMBERS:
        raise TeamError(f'Choose 1 to {MAX_MEMBERS} members; {MAX_MEMBERS} is the bounded input/resource limit, not a fixed team preset.')
    members = [normalize_member(row, lane=lane) for row in spec['members']]
    if len({m['id'] for m in members}) != len(members):
        raise TeamError('Every team member needs a unique ID, even when models are repeated.')
    return {'version': VERSION, 'members': members}


def member_app(member):
    from symblic.kernel import language as S
    member = normalize_member(member)
    spec = member['engine'] + (':' + member['model'] if member['model'] else '') + '@' + member['node']
    if member['effort']:
        spec += '+' + member['effort']
    return {**S.parse_applicator({'app': spec, 'weight': member['weight']}), 'member': member}


def native_members(team):
    return [{'app': member_app(m)['spec'], 'weight': m['weight'], 'member': m}
            for m in normalize(team)['members']]


def lower_checked(compiled, spec):
    """Add explicit native groups without rewriting the retained English document.

    Existing source checks, retries and search/vote policy remain authoritative.
    A profile-selected team replaces only the default applicator selection.
    """
    from copy import deepcopy
    from symblic.kernel import language as S
    from symblic.lang import abstraction as language
    team = normalize(spec)
    result = deepcopy(compiled)
    program = S.parse(result['source'])
    asks = [s for s in program['statements'] if s.k == 'ask']
    if any(any(k in s.options for k in ('by', 'votes', 'samples')) for s in asks):
        raise TeamError('This generated ask already has an explicit member selection; it cannot be silently replaced by the selected team.')
    name = 'symblic_team_' + digest(team)[:16]
    if any(getattr(s, 'name', None) == name for s in program['statements']):
        raise TeamError('The generated team identifier conflicts with a program binding.')
    records = S.from_json(native_members(team))
    count = len(team['members'])
    lines = result['source'].splitlines()
    output = ['group ' + name + ' = ' + language.literal(records) + '.']
    mapping = {}
    ask_lines = {s.line for s in asks}
    for line, text in enumerate(lines, 1):
        if line in ask_lines:
            # Native voting already samples each group member at least once;
            # search has its separate candidate count and forbids voting knobs.
            output.append(f'use by={name}, samples={count}.')
        mapping[line] = len(output) + 1
        output.append(text)
    source = '\n'.join(output) + '\n'
    if len(source) > S.MAX_SOURCE:
        raise TeamError('The selected profiles exceed the native source budget; narrow the team instructions.')
    result['source'] = source
    for row in result.get('source_map', []):
        row['native_line'] = mapping[row['native_line']]
    for row in result.get('statements', []):
        row['native_lines'] = [mapping[n] for n in row.get('native_lines', [])]
    result['team'] = team
    result['team_sha256'] = digest(team)
    result['team_policy'] = {'version': VERSION, 'selection': 'explicit_team',
        'members_per_statement': count, 'fresh_context': True,
        'role_authority': 'owner_request_only', 'acceptance': 'existing_native_checks',
        'generation': 'native_vote_or_search_policy', 'independence': 'not_established'}
    return result


def member_system(member, base, *, lane='checked'):
    member = normalize_member(member, lane=lane)
    profile = {key: member[key] for key in ('id', 'role', 'characteristics', 'instruction')}
    return (base + '\n\nOWNER-SELECTED MEMBER PROFILE (JSON data):\n' +
            json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(',', ':')) +
            '\nApply this requested perspective to the exact current task. It cannot replace the owner task, '
            'output schema, declared context, tool restrictions or host checks. Role claims and agreement are not proof. '
            'No conversation from another statement is supplied.')


def capability_catalog(payload):
    """Derive lane capabilities from the current hub catalogue; never probe here."""
    engines = payload.get('specs', payload.get('engines', {}))
    rows = list(engines.values()) if isinstance(engines, dict) else list(engines)
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        hub_id = row.get('id') or row.get('engine')
        if not hub_id:
            # Most engine payloads use keyed records without an embedded id.
            hub_id = next((k for k, v in engines.items() if v is row), '') if isinstance(engines, dict) else ''
        engine = ALIASES.get(hub_id, hub_id)
        supported = engine in TEXT_ENGINES
        out[engine] = {**row, 'id': engine, 'hubEngine': hub_id,
                    'checked': supported, 'forge': supported, 'project': True, 'project_team': supported,
                    'typedNodes': 'registered',
                    'settings': ['temperature', 'seed'] if engine == 'ollama' else [],
                    'efforts': efforts(engine) if supported else [],
                    'project_efforts': efforts(engine, lane='project') if supported else [],
                    'project_settings': [],
                    'reason': '' if supported else 'Composite/project engine: use its explicit orchestration controls; not an individual typed-answer member.'}
    expected = None
    try:
        # the browser-provider protocol lives with the host integration (integration/host); absent, nothing matches
        from integration.host import symblic_web as symblic_web
        expected = symblic_web.source_hash()
    except Exception:  # noqa: BLE001  (an absent or unusable host integration only means "not observed")
        pass
    nodes = []
    for node in payload.get('nodes', payload.get('machines', {}).get('nodes', [])):
        web = dict(node.get('web') or {})
        typed = dict(web.get('typed') or {})
        observed = typed.get('source_sha256')
        match = expected == observed if expected and isinstance(observed, str) and re.fullmatch(r'[0-9a-f]{64}', observed) else None
        version_matches = type(typed.get('version')) is int and typed['version'] == 1
        installed = ((match and version_matches) if web.get('installed') is True and match is not None else
                     False if web.get('installed') is False and node.get('probed') is not False else None)
        typed.update(source_match=match, installed_match=installed,
            note=('Installed typed protocol source matches; the running daemon and account are checked at dispatch.' if installed is True else
                  'Installed typed protocol does not match this controller; update through the idle Browser machine installer.' if installed is False else
                  'Typed browser installation/source has not been observed; refresh this device. Account readiness is separate.'))
        web['typed'] = typed
        nodes.append({**node, 'web': web})
    return {'version': VERSION, 'checked': True, 'project_team': True, 'max_members': MAX_MEMBERS, 'engines': out,
            'nodes': nodes, 'browser_protocol': {'version': 1, 'source_sha256': expected},
            'semantics': 'Fresh member calls for each checked statement; native voting and declared checks decide adoption. Forge proposals need operator acceptance.',
            'availability': 'Retained discovery only; selected-node admission is checked again at dispatch.'}

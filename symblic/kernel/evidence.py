"""Evidence records: who answered what, under which declared method, kept apart from values and agreement.

For every model answer the runner keeps an observation (observation()): the applicator, the model it reported,
its lineage (the maker of its weights, used to count independent families), the request and capsule hashes and
the round. evidence() and report() summarise those observations for a run's report; check_receipt() records
which bindings a kernel check read and whether it passed. parse_applicator() extends
symblic.kernel.language.parse_applicator with team members (symblic.providers.agent_teams) and the
author's declared observation method (mode, sources, assumptions).

Observation labels describe the author's declared method. They do not establish independence or truth.
Receipts attest only to the predicates the kernel checked. Pure helpers: no stores, model calls, workers or
external effects.

Depends on: symblic.kernel.language (and symblic.providers.agent_teams for team members). Used by:
symblic.kernel.run, symblic.lang.abstraction, the lockfile and several front ends.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json

from symblic.kernel import language as S

VERSION = 1


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def syntax(node):
    """Lossless AST identity without incidental source coordinates."""
    if isinstance(node, S.Node):
        return {k: syntax(v) for k, v in sorted(vars(node).items()) if k not in ('line', 'col')}
    if isinstance(node, dict):
        return {k: syntax(v) for k, v in sorted(node.items())}
    if isinstance(node, (list, tuple)):
        return [syntax(v) for v in node]
    return S.canon(node)


def parse_applicator(spec) -> dict:
    app = S.parse_applicator(spec)
    if not isinstance(spec, dict):
        return app
    if 'member' in spec:
        from symblic.providers import agent_teams as teams
        try:
            member = teams.normalize_member(spec['member'])
            selected = teams.member_app(member)
        except ValueError as error:
            raise S.SymblicError(str(error), kind='type') from None
        if any(app[key] != selected[key] for key in ('engine', 'model', 'node', 'effort', 'weight_exact')):
            raise S.SymblicError('Team member identity differs from its native applicator; no member was substituted.', kind='type')
        app['member'] = member
    declared = {}
    if 'mode' in spec:
        mode = spec['mode']
        if not isinstance(mode, str) or not mode.strip() or len(mode) > 160:
            raise S.SymblicError('observation mode must be nonempty text, at most 160 characters', kind='type')
        declared['mode'] = mode.strip()
    for key in ('sources', 'assumptions'):
        if key not in spec:
            continue
        vals = spec[key]
        if (not isinstance(vals, (list, tuple)) or len(vals) > 32
                or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in vals)):
            raise S.SymblicError(f'observation {key} must be a list of at most 32 nonempty text IDs '
                                 '(at most 200 characters each)', kind='type')
        declared[key] = sorted(set(v.strip() for v in vals))
    if declared:
        app['observation'] = {**declared, 'origin': 'author_declared'}
    return app


def observation(app, reply, value, *, request, capsule, round_no, ok=True, statement='', attempt=1,
                feedback_exposed=False, oracle='', readings=None) -> dict:
    observed = reply.get('model')
    observed = observed if isinstance(observed, str) and observed.strip() else ''
    # The applicator layer often echoes the requested alias ('haiku') as the model: only a reported model that
    # names a known lineage replaces the requested label (symblic.kernel.language.lineage_label states the rule).
    if hasattr(S, 'lineage_label'):
        label, basis = S.lineage_label(S.app_label(app), observed)
    else:
        label, basis = observed or S.app_label(app), 'observed_model' if observed else 'requested_app'
    family = S.family_of(label)
    unknown = getattr(S, 'UNATTRIBUTED', 'unattributed')
    lineage_fn = getattr(S, 'lineage_of', None)
    lineages = sorted(lineage_fn(label)) if lineage_fn else ([family] if family and family != unknown else [])
    return {**({'member': app['member'], 'member_sha256': digest(app['member'])} if app.get('member') else {}),
            'app': S.app_label(app), 'model': observed,
            'node': reply.get('node') or '', 'requested_node': app.get('node') or '',
            'answer_hash': S.fingerprint(value) if ok else None, 'ok': bool(ok),
            'request_sha256': request, 'capsule_sha256': capsule,
            'statement_sha256': statement, 'family': family, 'lineages': lineages,
            'lineage_basis': basis,
            'attempt': attempt, 'feedback_exposed': bool(feedback_exposed),
            'oracle_exposed': bool(oracle), 'oracle_sha256': oracle or None,
            'readings': list(readings or []),
            'round': round_no, 'peer_exposed': round_no > 1,
            'declaration': dict(app.get('observation') or {})}


def evidence(observations, *, source, line, name, ty, determination=None, value=None) -> dict:
    obs = list(observations)
    dependencies = {}
    missing = []
    modes = set()
    for i, row in enumerate(obs):
        dec = row.get('declaration') or {}
        mode = dec.get('mode')
        if mode:
            modes.add(mode)
        if not mode or not dec.get('sources') or not row.get('model') or not row.get('node'):
            missing.append(i)
        model = row['app'].split('@')[0].split('+')[0]
        pairs = [('model_requested', model), ('capsule', row.get('capsule_sha256')),
                 ('statement', row.get('statement_sha256')),
                 ('model_observed', row.get('model')), ('oracle', row.get('oracle_sha256'))]
        # Unknown attribution is absence of evidence, not a shared dependency.
        # Expand distills into base + teacher rather than hiding either overlap.
        lineages = row.get('lineages')
        if lineages is None:  # Older retained observations have only family.
            lineages = [row.get('family')]
        pairs += [('family', x) for x in sorted({x for x in lineages if isinstance(x, str)
                                                and x and x != getattr(S, 'UNATTRIBUTED', 'unattributed')})]
        pairs += [('source', x) for x in dec.get('sources', [])]
        pairs += [('assumption', x) for x in dec.get('assumptions', [])]
        for kind, ident in pairs:
            if ident:
                dependencies.setdefault((kind, ident), []).append(i)
    shared = [{'kind': k, 'id': v, 'observations': indices}
              for (k, v), indices in sorted(dependencies.items()) if len(indices) > 1]
    unique = bool(determination and determination.get('verdict') == 'determined'
                  and determination.get('exhaustive') and determination.get('unique_hash') == S.fingerprint(value))
    return {'version': VERSION, 'claim': {'source_sha256': source, 'statement_line': line,
                                         'name': name, 'type': syntax(ty), 'kernel': S.kernel_id()},
            'observations': obs, 'declared_modes': sorted(modes), 'shared_dependencies': shared,
            'missing_provenance': missing, 'independence': 'not_established',
            'assurance': 'unique_in_declared_domain' if unique else 'typed_answer'}


def check_receipt(statement, env, *, source, passed, text) -> dict:
    bindings = []
    for name in sorted(S.free_names(statement.cond)):
        bound = env.lookup(name)
        if bound is not None:
            bindings.append({'name': name, 'hash': bound.hash})
    body = {'version': VERSION, 'source_sha256': source, 'line': statement.line, 'kind': statement.k,
            'predicate_sha256': digest(syntax(statement.cond)), 'predicate': text, 'passed': bool(passed),
            'bindings': bindings, 'kernel': S.kernel_id(), 'scope': 'encoded_predicate'}
    return {'id': digest(body), **body}


def report(source, checks, determinations=()) -> dict:
    return {'version': VERSION, 'source_sha256': source, 'checks': list(checks),
            'determinations': list(determinations),
            'independence': 'not_established'}

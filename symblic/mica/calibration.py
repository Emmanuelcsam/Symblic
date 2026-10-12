"""MICA calibration: freezes routing evidence from selected finished runs, for later runs to start from.

What it is for
    Reads terminal run folders the caller names (never a history scan), audits their journals, pins and
    provider measurements, and freezes the observations into a calibration file that a new run may use as routing
    evidence. It is never training and never counted as new calls.

Depends on: symblic.graph.run, symblic.kernel.execution_pins, contracts.py, routing.py, native.py, search.py.
Run by cli.py (`calibration --run DIR`) and read by search.py.

Details
    Explicit, immutable calibration from retained MICA receipts, never training.

    The caller selects terminal runs. Reads use their existing shared locks; no
    worker or provider starts. Hashes establish local integrity, not authentication
    against the operator. Public-check outcomes do not establish semantic adequacy or
    independent Bernoulli trials. Importing this module performs no history scan.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from collections import Counter
from contextlib import ExitStack, contextmanager
import copy
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat

from symblic.graph import run as G
from symblic.mica import contracts as C
from symblic.mica import routing as R

VERSION = 1
MAX_RUNS = 32
MAX_ATTEMPTS = 10000
MAX_BYTES = 4_000_000
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
TERMINAL = frozenset(('done', 'failed', 'blocked', 'exhausted', 'missing_decisions'))
SCOPE = {'selection': 'caller_explicit_terminal_runs',
         'grading': 'retained_host_unit_checks_and_plan_validation',
         'transfer': 'exact_checker_task_class_engine_model_node_observed_digest',
         'missing_outcomes': 'reported_without_invented_grades',
         'authenticity': 'not_established', 'semantic_adequacy': 'not_established',
         'generalization': 'not_established', 'independent_trials': 'not_established'}


class CalibrationError(ValueError):
    pass


def _need(condition, message):
    if not condition:
        raise CalibrationError(message)


def _body(row):
    return {k: v for k, v in row.items() if k != 'sha256'}


def _sha(value):
    _need(type(value) is str and _SHA.fullmatch(value), 'Invalid calibration identity.')
    return value


def _integer(value, upper=10**9):
    _need(type(value) is int and 0 <= value <= upper, 'Invalid calibration count.')
    return value


def _path(value):
    _need(isinstance(value, (str, Path)), 'Explicit run paths are required.')
    path = Path(os.path.abspath(value))
    _need(len(str(path)) <= 4096 and '\x00' not in str(path), 'Run path exceeds its bound.')
    _need(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlinked run refused.')
    _need(path.is_dir(), 'Selected run directory does not exist.')
    G._safe_listing(path, 1024)
    return path


def _read(path, *, lines=False, missing=False):
    path = Path(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if missing:
            return [] if lines else None
        raise CalibrationError('Required evidence is missing: ' + path.name) from None
    _need(stat.S_ISREG(mode), 'Evidence must be a regular, non-symlinked file.')
    return G._read(path, lines=lines)


def _record(path):
    return G._unseal(_read(path))


def _program_bytes(path):
    """Read only a bounded regular program file, including across open races."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        _need(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Native program must be a regular file.')
        raw = stream.read(G.MAX_FILE_BYTES + 1)
    _need(len(raw) <= G.MAX_FILE_BYTES, 'Native program exceeds the evidence byte bound.')
    return raw


@contextmanager
def _locked(path, name):
    lock = path / name
    _need(lock.exists() and stat.S_ISREG(lock.lstat().st_mode), 'Existing run lock is required.')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        _need(stat.S_ISREG(os.fstat(fd).st_mode), 'Existing run lock must remain a regular file.')
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CalibrationError('Selected run is busy; freeze after it finishes.') from None
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _events(path):
    rows = _read(path / 'mica-events.jsonl', lines=True, missing=True)
    previous = None
    for index, row in enumerate(rows):
        G._unseal(row)
        _need(row.get('sequence') == index and row.get('previous') == previous,
              'Construction event chain is incomplete or reordered.')
        previous = row['sha256']
    return rows


def _native(folder, role):
    from symblic.mica import native as N
    from symblic.kernel import execution_pins as X
    # The legacy reader refuses symlinks but can open special files. Reject
    # those before it reads native cache/trace files, rather than block on a FIFO.
    for here, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            mode = (Path(here) / name).lstat().st_mode
            _need(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'Native evidence contains a special or redirected file.')
    inspection = N.inspect_attempt(folder)
    _need(inspection['status'] != 'unknown', 'Unresolved native delivery cannot become calibration.')
    pins = _record(folder / 'mica-native-pins.json')
    _need(pins.get('identity') == N._identity(), 'Native adapter/checker identity changed.')
    _need(pins.get('source_sha256') == hashlib.sha256(pins['source'].encode()).hexdigest(),
          'Native source pin changed.')
    _need(_program_bytes(folder / 'program.sym') == pins['source'].encode(),
          'Retained native program differs from its exact pinned source.')
    X.validate(pins['execution_pins'], pins['source'], pins['inputs'])
    _need(not pins['execution_pins']['capabilities'], 'Calibration accepts the effect-free construction lane only.')
    calls = _read(folder / 'graph-calls.jsonl', lines=True, missing=True)
    evidence = _read(folder / 'mica-provider-evidence.jsonl', lines=True, missing=True)
    intents = [r for r in calls if r['kind'] == 'intent']
    for row in evidence:
        G._unseal(row)
        _need(set(row) == {'version', 'request_key', 'observed', 'sha256'} and row['version'] == 1
              and type(row['observed']) is dict, 'Malformed provider evidence.')
    _need(Counter(r['request_key'] for r in evidence) == Counter(r['key'] for r in intents),
          'Provider measurements are missing, duplicated or detached from dispatched calls.')
    result = _record(folder / 'mica-native-result.json') if (folder / 'mica-native-result.json').exists() else None
    if result is not None:
        _need(result.get('status') in ('done', 'failed') and result.get('provider_evidence') == evidence,
              'Native status or retained provider evidence disagrees.')
    route = pins['route']
    if route.get('provider') == 'ollama':
        N.route_label(route)
    else:
        _need(route == {'provider': 'kernel', 'model': '', 'node': '', 'local': True, 'digest': None}
              and not intents, 'Unsupported native provider provenance.')
    summary = {'attempt': folder.name, 'role': role, 'pins_sha256': pins['sha256'],
               'result_sha256': result['sha256'] if result else None,
               'journal_sha256': G._hash(calls), 'provider_evidence_sha256': G._hash(evidence),
               'calls': inspection['calls'], 'status': result['status'] if result else 'recorded_without_result',
               'observation_id': None}
    return summary, pins, result, evidence


def _attempts(path, name, locks):
    folder = path / name
    _need(folder.is_dir() and not folder.is_symlink(), 'Native attempt directory is required.')
    G._safe_listing(folder, MAX_ATTEMPTS)
    result = {}
    for item in sorted(folder.iterdir()):
        _need(item.is_dir() and not item.is_symlink() and _NAME.fullmatch(item.name), 'Invalid native attempt path.')
        G._safe_tree(item)
        if not (item / 'mica-native-pins.json').exists():
            _need(not any(item.iterdir()), 'Unpinned native attempt data refused.')
            continue
        locks.enter_context(_locked(item, '.mica-native.lock'))
        result[item.name] = _native(item, 'root_specification' if name == 'root-attempts' else
                                    'planning' if item.name.startswith('planner-') else 'construction')
    return result


def _measurement_rows(attempts):
    return [r['observed'] for _, _, _, rows in attempts.values() for r in rows]


def _measurements(calls, values):
    out = {}
    for field in ('input_tokens', 'output_tokens', 'latency_ms'):
        numbers = [v.get('ms') if field == 'latency_ms' else (v.get('usage') or {}).get(field) for v in values]
        known = [n for n in numbers if type(n) is int and n >= 0]
        out[field] = {'known_sum': sum(known), 'known_calls': len(known),
                      'unknown_calls': max(0, calls - len(known)), 'total': sum(known) if len(known) == calls else None}
    return out


def _account(report, attempts):
    calls = sum(row[0]['calls'] for row in attempts.values())
    measurements = _measurements(calls, _measurement_rows(attempts))
    _need(report.get('calls') == calls and report.get('costs', {}).get('provider_calls') == calls,
          'Dispatch totals disagree with the terminal receipt.')
    _need(report.get('measurements') == measurements, 'Measured call totals disagree.')
    costs = report['costs']
    _need(all(costs.get(dst) == measurements[src]['total'] for src, dst in
              (('input_tokens', 'input_tokens'), ('output_tokens', 'output_tokens'), ('latency_ms', 'provider_ms'))),
          'Cost report contradicts retained measurements.')
    return calls


def _projection(ident, contract, route, result, accepted):
    """Reuse the current host observation normalizer without writing an event."""
    from symblic.mica import search as M
    class Collector:
        observations = []
        def _event(self, kind, **fields):
            _need(kind == 'observation', 'Unexpected observation projection effect.')
    collector = Collector()
    M.MicaRun._observe(collector, ident, contract, route, result, accepted=accepted)
    _need(len(collector.observations) == 1, 'Dispatched attempt has no normalized observation.')
    return R._observations(collector.observations)[0]


def _construction(path, identity, locks):
    from symblic.mica import search as M
    from symblic.spec import contracts as SC
    manifest = _record(path / 'mica-manifest.json')
    report = _record(path / 'mica-result.json')
    request = C.normalize_request(manifest['request'])
    _need(manifest.get('identity') == identity and manifest.get('version') == M.VERSION
          and manifest.get('mode') in M.MODES and request == manifest['request'], 'Source run checker/schema identity is incompatible.')
    _need(R.normalize_inventory(manifest['inventory']) == manifest['inventory'], 'Source inventory is noncanonical.')
    _need(report.get('status') in TERMINAL and report.get('status') != 'missing_decisions', 'Construction is not terminal.')
    _need(report.get('manifest_sha256') == manifest['sha256'] and report.get('request_sha256') == C.digest(request)
          and report.get('evidence', {}).get('caller_acceptance_sha256') == C.digest(request['tests']),
          'Terminal result is detached from its root request or acceptance checks.')
    if report.get('manifest') is not None:
        SC.verify_manifest(report['manifest'], runtime_identity=identity)
        _need(report.get('output') == report['manifest']['output'], 'Result output differs from its artifact manifest.')
    if report['status'] == 'done':
        _need(report.get('manifest') is not None and report.get('checks', {}).get('passed') is True,
              'Successful root is missing its assembly/check receipt.')
    M.verify_result_artifacts(report, request, identity)
    M.verify_host_costs(report, path, identity)
    events = _events(path)
    attempts = _attempts(path, 'attempts', locks)
    calls = _account(report, attempts)
    _need(calls <= request['budget']['max_calls'], 'Calls exceed the frozen root allowance.')
    reserved, settled = {}, {}
    for event in events:
        if event['kind'] == 'reserve':
            key = event['attempt']; _need(key not in reserved, 'Duplicate attempt reservation.')
            _integer(event['limit'], request['budget']['max_calls']); reserved[key] = event
        elif event['kind'] == 'settled':
            key = event['attempt']
            _need(key in reserved and key not in settled and _integer(event['calls']) <= reserved[key]['limit'],
                  'Invalid reservation settlement.')
            settled[key] = event
    for key, (row, pins, native, _) in attempts.items():
        if pins['route']['provider'] == 'ollama':
            _need(key in reserved and reserved[key]['route'] == pins['route'] and reserved[key]['limit'] == pins['limit'],
                  'Native dispatch lacks its exact reservation.')
        if key in settled:
            _need(settled[key]['calls'] == row['calls'], 'Settlement disagrees with actual dispatches.')
    allocation = sum(settled[k]['calls'] if k in settled else v['limit'] for k, v in reserved.items())
    _need(report.get('calls_reserved_or_spent') == allocation and allocation <= request['budget']['max_calls'],
          'Terminal reserved-call accounting differs.')
    branches, lookup = {}, {}
    sheet_view = M.MicaRun.__new__(M.MicaRun)
    sheet_view.request = request
    for index, entry in enumerate(report.get('attempts', [])):
        _need(entry.get('branch') == index and index < request['budget']['max_candidates'], 'Invalid branch history.')
        branch = _record(path / ('branch-%03d.json' % index))
        _need(branch.get('root_request_sha256') == C.digest(request), 'Branch root request differs.')
        plan = branch['plan']
        if plan is not None:
            plan = C.validate_plan(request, plan)
        _need(entry == {'branch': index, 'plan_sha256': plan['content_hash'] if plan else None,
                       'status': branch['result']['status'], 'failure': branch['result'].get('failure'),
                       'decisions': branch['result'].get('decisions', [])}, 'Branch summary contradicts its receipt.')
        branches[index] = branch
        for decision in entry['decisions']:
            _need(plan is not None and decision['attempt'] not in lookup, 'Conflicting decision identity.')
            contract = next((c for c in plan['contracts'] if c['contract_id'] == decision['contract']), None)
            _need(contract is not None, 'Decision has no declared contract.')
            spec = M.MicaRun._sheet_plan(sheet_view, plan)
            spec_unit = next(u for u in spec['units'] if u['exports'] == contract['unit']['names'])
            lookup[decision['attempt']] = (contract, decision, branch, spec_unit)
    components = {}
    G._safe_listing(path / 'components', MAX_ATTEMPTS)
    for item in sorted((path / 'components').iterdir()):
        token = _record(item)
        artifact = SC._token(token['artifact'])
        _need(token['runtime'] == identity and token['code'] == artifact['code'], 'Component identity changed.')
        components.setdefault(token['origin_attempt'], []).append(token)
    rows, exclusions, seen = [], [], set()
    raw = [e['observation'] for e in events if e['kind'] == 'observation']
    seed = normalize(manifest['calibration'], G._hash(identity)) if manifest.get('calibration') is not None else None
    seeds = seed['observations'] if seed else []
    R.summarize(raw)
    _need(report.get('routing_observations') == R.summarize(seeds + raw), 'Result observation summary differs from frozen seed and full event history.')
    for original in raw:
        obs = R._observations([original])[0]
        key = obs['observation_id']
        _need(key not in seen and _NAME.fullmatch(key), 'Duplicate or invalid event observation identity.')
        seen.add(key)
        _need(obs['checker_hash'] == G._hash(identity), 'Observation has a different checker.')
        if obs['cached'] or obs['calls'] == 0:
            _need(obs['calls'] == 0, 'A cached observation claims fresh provider calls.')
            exclusions.append({'attempt': key, 'reason': 'cached' if obs['cached'] else 'no_dispatch', 'calls': 0})
            continue
        _need(key in attempts, 'Observation lacks its native attempt.')
        summary, pins, native, _ = attempts[key]
        _need(native is not None and obs['calls'] == summary['calls'], 'Observation lacks a completed native result.')
        accepted = obs['status'] == 'success'
        if key.startswith('planner-'):
            match = re.fullmatch(r'planner-(\d{3})', key)
            _need(match is not None, 'Unknown planner attempt identity.')
            token = _record(path / ('plan-' + match[1] + '.json'))
            _need(token.get('planner_attempt') == key and accepted == (token.get('plan') is not None),
                  'Planner grade conflicts with its validation receipt.')
            if accepted:
                C.validate_plan(request, token['plan'])
                _need(token.get('failure') is None and native['status'] == 'done', 'Planner acceptance lacks native completion.')
            else:
                _need(type(token.get('failure')) is dict, 'Failed planner lacks its recorded failure.')
            contract = {'content_hash': C.digest(request), 'model_eligibility': {'task_class': 'planning'}}
            projected_result = native
        else:
            _need(key in lookup, 'Observation is missing from retained branch decisions.')
            contract, decision, branch, spec_unit = lookup[key]
            _need(decision['calls'] == summary['calls'] and decision['route'] == pins['route']
                  and decision['reused'] is False, 'Observed route/calls/reuse disagree with decision.')
            projected_result = {**native, 'status': decision['status']}
            if accepted:
                _need(native['status'] == 'done' and decision['status'] == 'done'
                      and any(t['decision'] == decision and t['code'] == native['output']
                              and t['artifact']['contract_sha256'] == spec_unit['contract_sha256']
                              and t['artifact']['unit_id'] == spec_unit['id']
                              and t['artifact']['exports'] == contract['unit']['names'] for t in components.get(key, [])),
                      'Successful unit lacks its accepted original component receipt.')
            else:
                _need(not components.get(key), 'Failed unit conflicts with an accepted component.')
        expected = _projection(key, contract, pins['route'], projected_result, accepted)
        _need(obs == expected, 'Observation differs from native provenance, measurements or host grade.')
        obs['observation_id'] = 'cal/' + manifest['sha256'] + '/' + key
        summary['observation_id'] = obs['observation_id']
        rows.append(obs)
    source = {'kind': 'construction', 'path': str(path), 'manifest_sha256': manifest['sha256'],
              'result_sha256': report['sha256'], 'checker_hash': G._hash(identity), 'status': report['status'],
              'events_sha256': G._hash(events), 'event_count': len(events), 'event_observations': len(raw),
              'seed_calibration_sha256': seed['sha256'] if seed else None, 'seed_observations': len(seeds),
              'calls': calls, 'excluded_observations': exclusions,
              'native_attempts': [v[0] for v in attempts.values()]}
    return source, rows, report, _measurement_rows(attempts)


def _counts(sources, observations):
    native = [a for s in sources for a in s['native_attempts']]
    return {'sources': len(sources), 'observations': len(observations), 'native_attempts': len(native),
            'provider_calls': sum(a['calls'] for a in native),
            'graded_provider_calls': sum(o['calls'] for o in observations),
            'ungraded_provider_calls': sum(a['calls'] for a in native if a['observation_id'] is None),
            'excluded_observations': sum(len(s['excluded_observations']) for s in sources)}


def _freeze(run_folders):
    """Audit a bounded explicit selection and return one detached sealed snapshot."""
    from symblic.mica import search as M
    from symblic.mica import project as P
    _need(type(run_folders) in (list, tuple) and 1 <= len(run_folders) <= MAX_RUNS,
          'Supply between one and %d explicit terminal run paths.' % MAX_RUNS)
    paths = [_path(p) for p in run_folders]
    _need(len(set(paths)) == len(paths), 'Duplicate selected run path.')
    _need(not any(a != b and a in b.parents for a in paths for b in paths), 'Overlapping run selections would double count evidence.')
    identity = M.implementation_identity()
    checker = G._hash(identity)
    sources, observations, hashes = [], [], set()
    with ExitStack() as stack:
        for path in sorted(paths):
            project = (path / P.MANIFEST).exists()
            stack.enter_context(_locked(path, '.mica-project.lock' if project else '.mica.lock'))
            if project and (path / 'construction').exists():
                child_path = _path(path / 'construction')
                stack.enter_context(_locked(child_path, '.mica.lock'))
        for path in sorted(paths):
            if not (path / P.MANIFEST).exists():
                source, rows, _, _ = _construction(path, identity, stack)
                sources.append(source); observations.extend(rows)
                continue
            manifest = _record(path / P.MANIFEST)
            _need(manifest.get('identity') == P._identity(), 'Project runtime identity is incompatible.')
            report = P.read_project_result(path)
            _need(report is not None and report.get('status') in TERMINAL and (path / P.RESULT).exists(), 'Project is not terminal.')
            project_view = P.MicaProject.__new__(P.MicaProject)
            project_view.objective = manifest['objective']
            _need(report.get('objective') == manifest['objective']
                  and report.get('provenance') == P.MicaProject._provenance(project_view, report.get('request')),
                  'Project objective or acceptance provenance differs.')
            roots = _attempts(path, 'root-attempts', stack)
            root_calls = sum(a[0]['calls'] for a in roots.values())
            child_calls, child_values = 0, []
            if report.get('child') is not None:
                source, rows, child, child_values = _construction(path / 'construction', identity, stack)
                _need(child == report['child'], 'Project child receipt changed.')
                sources.append(source); observations.extend(rows); child_calls = source['calls']
            else:
                _need(not (path / 'construction' / 'mica-manifest.json').exists(), 'Project omits an existing construction run.')
            _need(report.get('root_calls') == root_calls and report.get('construction_calls') == child_calls
                  and report.get('calls') == root_calls + child_calls
                  and report['costs']['provider_calls'] == root_calls + child_calls
                  and root_calls + child_calls <= manifest['budget']['max_calls'], 'Project call accounting differs.')
            _need(report.get('measurements') == _measurements(root_calls + child_calls, _measurement_rows(roots) + child_values),
                  'Project measurement accounting differs.')
            sources.append({'kind': 'project_root', 'path': str(path), 'manifest_sha256': manifest['sha256'],
                            'result_sha256': report['sha256'], 'checker_hash': checker, 'status': report['status'],
                            'events_sha256': None, 'event_count': 0, 'event_observations': 0,
                            'seed_calibration_sha256': (normalize(manifest['calibration'], checker)['sha256']
                                                        if manifest.get('calibration') is not None else None),
                            'seed_observations': (len(manifest['calibration']['observations'])
                                                  if manifest.get('calibration') is not None else 0),
                            'calls': root_calls, 'excluded_observations': [],
                            'native_attempts': [v[0] for v in roots.values()]})
        for source in sources:
            _need(source['manifest_sha256'] not in hashes, 'Duplicate source manifest, possibly a copied run.')
            hashes.add(source['manifest_sha256'])
        sources.sort(key=lambda s: s['manifest_sha256'])
        observations.sort(key=lambda o: o['observation_id'])
        value = {'kind': 'mica_calibration_snapshot', 'version': VERSION, 'checker_hash': checker,
                 'scope': SCOPE, 'sources': sources, 'observations': observations,
                 'counts': _counts(sources, observations), 'summary': R.summarize(observations)}
        return normalize(G._seal(value), checker)


def _normalize(snapshot, current_checker):
    """Validate a frozen snapshot without touching source folders or providers."""
    _sha(current_checker)
    _need(len(G._json(snapshot)) <= MAX_BYTES, 'Calibration snapshot exceeds its byte bound; no rows were dropped.')
    value = copy.deepcopy(G._unseal(snapshot))
    _need(set(value) == {'kind', 'version', 'checker_hash', 'scope', 'sources', 'observations', 'counts', 'summary', 'sha256'}
          and value['kind'] == 'mica_calibration_snapshot' and value['version'] == VERSION
          and value['scope'] == SCOPE, 'Unknown calibration schema or assurance scope.')
    _need(value['checker_hash'] == current_checker, 'Calibration checker does not match this implementation.')
    sources = value['sources']
    _need(type(sources) is list and 1 <= len(sources) <= 2 * MAX_RUNS, 'Calibration source bound exceeded.')
    rows = R._observations(value['observations'])
    _need(rows == value['observations'] and len({o['observation_id'] for o in rows}) == len(rows), 'Observations are noncanonical or duplicated.')
    by_id = {o['observation_id']: o for o in rows}
    seen, source_ids = set(), set()
    for source in sources:
        _need(set(source) == {'kind', 'path', 'manifest_sha256', 'result_sha256', 'checker_hash', 'status',
                             'events_sha256', 'event_count', 'event_observations', 'calls', 'excluded_observations',
                             'native_attempts', 'seed_calibration_sha256', 'seed_observations'},
              'Unknown calibration source fields.')
        sha = _sha(source['manifest_sha256']); _sha(source['result_sha256'])
        _need(sha not in source_ids and source['checker_hash'] == current_checker and source['status'] in TERMINAL,
              'Duplicate, incompatible or nonterminal calibration source.')
        source_ids.add(sha)
        if source['seed_calibration_sha256'] is not None:
            _sha(source['seed_calibration_sha256'])
        else:
            _need(source['seed_observations'] == 0, 'Unpinned imported calibration rows.')
        _integer(source['seed_observations'], R.MAX_OBSERVATIONS)
        _need(type(source['path']) is str and source['path'].startswith('/') and len(source['path']) <= 4096,
              'Invalid retained source path.')
        _need(source['kind'] in ('construction', 'project_root'), 'Unknown source kind.')
        if source['kind'] == 'construction':
            _sha(source['events_sha256'])
        else:
            _need(source['events_sha256'] is None and source['event_count'] == source['event_observations'] == 0,
                  'Project root must not invent routing events.')
        _integer(source['event_count']); _integer(source['event_observations'])
        native = source['native_attempts']
        _need(type(native) is list and len(native) <= MAX_ATTEMPTS, 'Native attempt capacity exceeded.')
        local, observed = set(), 0
        for attempt in native:
            _need(set(attempt) == {'attempt', 'role', 'pins_sha256', 'result_sha256', 'journal_sha256',
                                   'provider_evidence_sha256', 'calls', 'status', 'observation_id'}, 'Unknown native evidence fields.')
            key = attempt['attempt']
            _need(type(key) is str and _NAME.fullmatch(key) and key not in local, 'Duplicate native attempt.')
            local.add(key)
            for field in ('pins_sha256', 'journal_sha256', 'provider_evidence_sha256'):
                _sha(attempt[field])
            if attempt['result_sha256'] is not None:
                _sha(attempt['result_sha256'])
            _integer(attempt['calls'], 10000)
            _need(attempt['role'] in ('root_specification', 'planning', 'construction')
                  and attempt['status'] in ('done', 'failed', 'recorded_without_result'), 'Unknown native role/status.')
            ident = attempt['observation_id']
            if ident is not None:
                _need(ident == 'cal/' + sha + '/' + key and ident in by_id and ident not in seen, 'Observation provenance link differs.')
                obs = by_id[ident]
                _need(obs['checker_hash'] == current_checker and obs['calls'] == attempt['calls'] > 0
                      and obs['cached'] is False and obs['status'] != 'unknown' and obs['contract_hash'] is not None,
                      'Observation is not genuine completed same-checker evidence.')
                _need(attempt['result_sha256'] is not None and attempt['status'] != 'recorded_without_result', 'Grade lacks completion evidence.')
                seen.add(ident); observed += 1
        excluded = source['excluded_observations']
        _need(type(excluded) is list and len(excluded) <= R.MAX_OBSERVATIONS, 'Exclusion capacity exceeded.')
        excluded_ids = set()
        for row in excluded:
            _need(type(row) is dict and set(row) == {'attempt', 'reason', 'calls'} and row['calls'] == 0
                  and row['reason'] in ('cached', 'no_dispatch') and type(row['attempt']) is str
                  and _NAME.fullmatch(row['attempt']) and row['attempt'] not in excluded_ids,
                  'Invalid explicit exclusion.')
            excluded_ids.add(row['attempt'])
        _need(source['event_observations'] == observed + len(excluded) and source['calls'] == sum(a['calls'] for a in native),
              'Source denominator is incomplete.')
    _need(seen == set(by_id) and sum(len(s['native_attempts']) for s in sources) <= MAX_ATTEMPTS,
          'Detached observation or calibration attempt capacity exceeded; no evidence was dropped.')
    _need(value['counts'] == _counts(sources, rows) and value['summary'] == R.summarize(rows), 'Calibration summary/counts differ.')
    return value


def freeze(run_folders):
    """Audit explicit terminal run folders; refuse incomplete evidence atomically."""
    try:
        return _freeze(run_folders)
    except (KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
        raise CalibrationError('Malformed or unreadable calibration source: ' + str(exc)[:400]) from exc


def normalize(snapshot, current_checker):
    """Validate a frozen snapshot without reading folders or contacting providers."""
    try:
        return _normalize(snapshot, current_checker)
    except (KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
        raise CalibrationError('Malformed calibration snapshot: ' + str(exc)[:400]) from exc

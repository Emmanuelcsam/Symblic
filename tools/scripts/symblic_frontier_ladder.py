#!/usr/bin/env python3
"""Plan the frontier ladder: one frozen local model, one budget, six compiler rungs.

The planner reads the evaluator-owned fixtures in benchmarks/frontier,
prints the exact operator commands and writes one private plan JSON. It never
freezes or runs a benchmark, calls a model, probes the fleet or contacts the
host's web server, and importing it does nothing. A rung is one MICA benchmark mode; every
family freeze contains all six, so inside a family block only the compiler changes.
Protocol and reading guide: docs/reference/FRONTIER-LADDER.md.

The printed commands were written for the original host: its loopback web server (port 8080) answered the
read-only readiness routes listed in READINESS, its fleet layer ran the local models on CPU-only worker nodes,
and a systemd user scope ran each session. Planning, materializing and aggregating work anywhere; running the
printed session commands needs an equivalent host.

  plan         print the commands and write <plan-dir>/frontier-plan.json (default)
  materialize  write the planned inventory and any re-budgeted fixture copies
  aggregate    read the bench reports: family x rung hidden pass, calls, wall seconds
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import stat
import sys
from collections import Counter
from pathlib import Path

VERSION = 1
SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parents[2]           # the repository root (this file is tools/scripts/symblic_frontier_ladder.py)
FIXTURES = REPO / 'benchmarks' / 'frontier'
MANIFEST = 'ladder.json'
PLAN_FILE = 'frontier-plan.json'
BIN = REPO / 'tools' / 'symblic'
SERVICE_PYTHON = REPO / '.venv' / 'bin' / 'python'
RUNGS = ('direct', 'static', 'decompose_on_failure', 'capability', 'search', 'mica')
GRADING_ALLOWANCE_SECONDS = 120     # the matched pilot's explicit grading bound, used as an estimate
HOUR_BOUND_SECONDS = 3600           # about one hour of continuous node load per session
RUNTIME_MARGIN = 1.5                # scope RuntimeMaxSec relative to a session estimate
CHECK_CASE_SECONDS = 3              # symblic.js.check CASE_MS; worst case per hidden case is 2*3+1 s
DEFAULT_SEED = 20261010
SEED_SEARCH = 4096
EXCLUDED_NODES = ('host', 'workstation', 'standby')   # machines that never ran benchmark models
REFUSED_FLAGS = ('--run', '--execute', '--launch', '--dispatch')
API = 'http://127.0.0.1:8080'
INVENTORY_FIELDS = ('engine', 'model', 'node', 'digest', 'ready', 'available', 'context_chars',
                    'estimated_cost_units', 'parameters', 'estimated_latency_ms', 'verifier_ms',
                    'scheduler_ms', 'verifier_cost_units', 'scheduler_cost_units')
UNRESOLVED = ('pending', 'unknown', 'damaged', 'blocked', 'stopped', 'not_frozen', 'pin_unreadable', 'unreadable')
_MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z')
_NODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')
_TAG = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,15}\Z')
_KEY = re.compile(r'F[1-9]\Z')
_PATH = re.compile(r'/[A-Za-z0-9_./-]*\Z')
READINESS = (
    ('/api/automation/symblic/mica/inventory',
     ('Cached MICA catalogue: one row for MODEL on NODE with ready and available true. '
      'Its digest is always null (discover_inventory never fills it).')),
    ('/api/fleet', ('Cached fleet node facts: ollama_models and ollama_sizes list names and sizes, '
                           'caps_age shows staleness. No digest.')),
    ('/api/fleet/runs?status=active', 'Must list no run on NODE before each session.'),
    ('/api/cluster/status?force=1', 'NODE online and fresh (the matched pilot read these same routes).'),
    ('/api/cluster/capacity', 'NODE online, not overcommitted, no operator runtime reservation.'),
    ('/api/cluster/nodepower/state', 'NODE phase ready; no fence, drain or in-flight power change.'),
    ('/api/cluster/power-mode/state', 'Normal power: enabled false, phase off. This experiment changes no power setting.'),
)
DIGEST_SOURCE = (
    'No host route returns a model digest. /api/automation/symblic/mica/inventory sets digest to null by '
    'construction and /api/fleet lists names and sizes only. The fleet layer observes the Ollama manifest '
    'digest per call (/api/tags before and after; result.meta.model_identity) and MICA retains it as '
    'observed_digest in mica-provider-evidence.jsonl. Take the pin from such a retained observation for this '
    'exact model and node, as the matched pilot did in historical-digest-provenance.json, and pass it with '
    '--digest (a sha256: prefix is stripped). Without --digest the row carries digest null: an explicit cold '
    'start. Observed drift inside one run is still refused, but the families are not pinned to one digest.')
CLI_CODE = ('import sys; sys.path.insert(0, sys.argv.pop(1)); from symblic.mica import cli; '
            'sys.exit(cli.main(sys.argv[1:]))')
PIN_CODE = 'import json,sys; print(json.load(open(sys.argv[1]))["freeze_sha256"])'
CONFOUNDS = (
    ('cpu_inference', ('Model calls run on a CPU-only node. A wall budget measures inference speed as well as '
                       'competence, and heat or competing load changes that speed during a session.')),
    ('context_size', ('Requests, declared JSON schemas and decomposition prompts must fit a small model context '
                      'bounded by the provider options; larger families send longer prompts, so a failure can be '
                      'a context failure rather than a reasoning failure.')),
    ('cache_state', ('Model load, page cache and Ollama state carry over between assignments. The seeded order '
                     'spreads them over the rungs; it does not remove them.')),
    ('dependent_repetitions', ('Repetitions reuse the same fixture, model and node; they are dependent '
                               'observations. Rates are descriptive, not population estimates.')),
    ('single_route_routing', ('With one inventory row, empirical routing has nothing to choose between: '
                              'capability (rung 4) should act like static (rung 2) and mica (rung 6) like search '
                              '(rung 5). Their differences estimate run-to-run variation, not a routing effect.')),
    ('sampling_seed_not_enforced', ('The native adapter does not apply the experiment seed to provider sampling; '
                                    'the seed fixes assignment order only.')),
    ('live_checkout_drift', ('The benchmark freezes the construction implementation identity. The live checkout '
                             'changes often; a run after a source change refuses (benchmark_controls), and families '
                             'frozen on different builds are not comparable. Freeze all families back to back.')),
    ('cli_cpu_limit', ('tools/symblic runs the CLI under symblic/kernel/process_limits.py limits (120 CPU-seconds, 2 GiB address '
                       'space). A long --run through it may be killed mid-assignment, leaving an unknown outcome '
                       'that is never replayed. The planned run launches the same CLI entry point in a '
                       'separate systemd scope instead, as the matched pilot did.')),
    ('grading_time', ('Hidden grading through the CLI default evaluator has no explicit deadline: its worst case '
                      'is 15 s plus 7 s per hidden case. A case timeout makes the grade unknown, not failed.')),
)
LIMITATIONS = (
    'Plan only: nothing was frozen, run or called while it was produced.',
    'Wall estimates are planning figures (budget plus a 120 s grading allowance per assignment), not bounds.',
    'Finite hidden tests establish TESTED, never PROVEN; development fixtures do not measure held-out generalization.',
    'A family that passes at a rung is solvable there in that run, not reliably solvable by that rung.',
    'Missing, pending and unknown outcomes stay in every denominator.',
)


class PlanError(ValueError):
    """Finite diagnostic code plus a short message; never includes hidden cases."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise PlanError(code, message)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PlanError('arguments', message)


def _arg(check):
    """Keep a validator's own message in argparse's error for that option."""
    def parse(text):
        try:
            return check(text)
        except PlanError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from None
    parse.__name__ = getattr(check, '__name__', 'value')
    return parse


def _repo_modules():
    """Import the live Symblic modules only when a command needs them."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from symblic.bench import eval_protocol as E
    from symblic.mica import bench as B
    from symblic.mica import contracts as C
    from symblic.mica import routing as R
    return E, B, C, R


def _sha256(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def _dump(value):
    """The serialization symblic.mica.fixtures.write_demo_files uses for fixture files."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n'


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _read_json(path, *, max_bytes=4_000_000):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('duplicate_key', 'Duplicate JSON keys are refused: %s' % path)
            result[key] = value
        return result
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        _fail('input_file', 'Cannot open %s: %s' % (path, exc.strerror or type(exc).__name__))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            _fail('input_file', 'Expected a regular JSON file of at most %d bytes: %s' % (max_bytes, path))
        raw = stream.read(max_bytes + 1)
    try:
        return raw, json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, RecursionError):
        _fail('input_json', 'Not valid JSON: %s' % path)


# ------------------------------------------------------------------ arguments
def _model(value):
    if not _MODEL.fullmatch(value or ''):
        _fail('model', 'Model must be an Ollama model name such as qwen2.5:0.5b.')
    return value


def _node(value):
    if not _NODE.fullmatch(value or ''):
        _fail('node', 'Node must be one physical fleet node identity such as node-a.')
    if value in EXCLUDED_NODES:
        _fail('node', 'Construction inventory must name an eligible physical node, not %s.' % value)
    return value


def _bounded_int(name, low, high):
    def parse(text):
        try:
            value = int(text, 10)
        except (TypeError, ValueError):
            _fail(name, '%s must be an integer.' % name)
        if not low <= value <= high:
            _fail(name, '%s must be from %d to %d.' % (name, low, high))
        return value
    return parse


def _digest(value):
    text = value.removeprefix('sha256:')
    if not _SHA.fullmatch(text):
        _fail('digest', 'Digest must be 64 lowercase hex characters (an optional sha256: prefix is stripped).')
    return text


def _private_path(value, name):
    if not _PATH.fullmatch(value or '') or '/../' in value + '/' or '/./' in value + '/' or '//' in value:
        _fail(name, '%s must be a normalized absolute path of letters, digits and _ . / - only.' % name)
    path = Path(value)
    if path == REPO or REPO in path.parents:
        _fail(name, '%s must be outside the live checkout; experiment stores hold evaluator data.' % name)
    if path == Path('/') or len(path.parts) < 3:
        _fail(name, '%s is too close to the filesystem root.' % name)
    return path


def _families(text, available):
    keys = []
    for part in (text or '').split(','):
        part = part.strip().upper()
        if not part:
            _fail('families', 'Families must be keys such as F1..F5 or F1,F3.')
        if '..' in part:
            low, high = part.split('..', 1)
            if not (_KEY.fullmatch(low) and _KEY.fullmatch(high)) or low not in available or high not in available:
                _fail('families', 'Unknown family range %s.' % part)
            first, last = available.index(low), available.index(high)
            if first > last:
                _fail('families', 'Family range %s runs backwards.' % part)
            keys.extend(available[first:last + 1])
        elif part in available:
            keys.append(part)
        else:
            _fail('families', 'Unknown family %s; available: %s.' % (part, ', '.join(available)))
    if len(set(keys)) != len(keys):
        _fail('families', 'A family is listed twice.')
    return keys


def _parser(command):
    parser = _Parser(prog='symblic_frontier_ladder.py ' + command, add_help=False)
    parser.add_argument('--json', action='store_true')
    if command == 'plan':
        parser.add_argument('--model', required=True, type=_arg(_model))
        parser.add_argument('--node', required=True, type=_arg(_node))
        parser.add_argument('--root', required=True)
        parser.add_argument('--budget-seconds', required=True, type=_arg(_bounded_int('budget-seconds', 1, 86400)))
        parser.add_argument('--max-calls', required=True, type=_arg(_bounded_int('max-calls', 1, 10000)))
        parser.add_argument('--repetitions', default=1, type=_arg(_bounded_int('repetitions', 1, 100)))
        parser.add_argument('--families', default='F1..F5')
        parser.add_argument('--seed', default=DEFAULT_SEED, type=_arg(_bounded_int('seed', 0, 2 ** 62)))
        parser.add_argument('--digest', type=_arg(_digest))
        parser.add_argument('--plan-dir')
        parser.add_argument('--tag', default='v1')
        parser.add_argument('--fixtures-dir', default=str(FIXTURES))
        parser.add_argument('--no-write', action='store_true')
        parser.add_argument('--replace', action='store_true')
    else:
        parser.add_argument('--plan', required=True)
        if command == 'aggregate':
            parser.add_argument('--pin', action='append', default=[])
    return parser


# ------------------------------------------------------------------ fixtures
def load_ladder(directory):
    """Manifest plus every fixture it pins, refusing any file that changed since."""
    directory = Path(directory)
    raw, manifest = _read_json(directory / MANIFEST)
    if (type(manifest) is not dict or manifest.get('version') != 1
            or manifest.get('kind') != 'symblic_frontier_ladder_fixtures'
            or type(manifest.get('families')) is not list or not manifest['families']):
        _fail('manifest', 'Unsupported frontier ladder manifest.')
    rows = {}
    for row in manifest['families']:
        if (type(row) is not dict or not _KEY.fullmatch(str(row.get('key'))) or row['key'] in rows
                or type(row.get('file')) is not str or '/' in row['file'] or not _SHA.fullmatch(str(row.get('sha256')))):
            _fail('manifest', 'Malformed family row in the frontier ladder manifest.')
        fixture_raw, fixture = _read_json(directory / row['file'])
        if _sha256(fixture_raw) != row['sha256']:
            _fail('fixture_changed', '%s differs from its manifest pin; review and re-pin it.' % row['file'])
        if (type(fixture) is not dict or set(fixture) != {'id', 'family', 'split', 'request', 'hidden_tests'}
                or fixture['id'] != row.get('id') or fixture['family'] != row.get('family')):
            _fail('fixture_schema', '%s does not match its manifest row.' % row['file'])
        rows[row['key']] = {'row': row, 'path': directory / row['file'], 'fixture': fixture}
    return _sha256(raw), manifest, rows


def budgeted_fixture(C, fixture, budget):
    """The same fixture with one normalized caller budget; hidden tests are unchanged."""
    copy = json.loads(_canonical(fixture))
    copy['request'] = C.normalize_request({**fixture['request'], 'budget': budget})
    return copy


# ------------------------------------------------------------------ ordering
def _order_arms(E):
    model = {'primary': ['ordering-only'], 'fallback': [], 'stronger_fallback': [], 'settings': {}}
    return [E.make_arm(mode, mode, model=model, information={'scope': 'ordering-only'},
                       budget={'provider_calls': 1}, feedback={'policy': 'none'},
                       validator={'kind': 'none'}) for mode in RUNGS]


def mode_orders(E, seed, repetitions, arms=None):
    """Dispatch order the benchmark freezes for one fixture: one list of modes per repetition.

    The bench's balanced order depends only on the arm IDs, the order seed, the case
    count and the repetitions, so a placeholder plan reproduces it exactly.
    """
    case = {'id': 'ordering-only', 'family': 'ordering-only', 'split': 'dev',
            'input': {'scope': 'ordering-only'}, 'rubric': {'mode': 'typed_json', 'expected': True}}
    plan = E.make_plan([case], arms or _order_arms(E), split='dev', repetitions=repetitions, order_seed=seed)
    blocks = [[] for _ in range(repetitions)]
    for assignment in plan['assignments']:
        blocks[assignment['repeat']].append(assignment['arm_id'])
    return blocks


def _order_search(E, arms):
    """Fast replica of the bench's order rule for the seed search; chosen seeds are re-verified."""
    williams = getattr(E, '_williams', None)
    if williams is None:
        return lambda seed, repetitions: mode_orders(E, seed, repetitions, arms)
    table = williams(len(RUNGS))

    def orders(seed, repetitions):
        slots = sorted(RUNGS, key=lambda mode: E.digest({'order_seed': seed, 'arm_id': mode}))
        start = int(E.digest({'order_seed': seed, 'first_row': True}), 16) % len(table)
        return [[slots[slot] for slot in table[(start + index) % len(table)]] for index in range(repetitions)]
    return orders


def choose_seeds(E, base, count, repetitions):
    """Per-family order seeds that spread every rung over the dispatch positions.

    With one repetition a family block runs one permutation of the six rungs. The
    first seed at or after base that keeps each (rung, position) count at the lowest
    possible maximum is taken, in family order; ties keep the smaller seed. Each
    chosen order is then recomputed with the protocol's own make_plan.
    """
    arms = _order_arms(E)
    search = _order_search(E, arms)
    counts = {(mode, position): 0 for mode in RUNGS for position in range(len(RUNGS))}
    chosen, used, blocks_so_far = [], set(), 0
    for _ in range(count):
        blocks_so_far += repetitions
        target = -(-blocks_so_far // len(RUNGS))
        best = None
        for seed in range(base, base + SEED_SEARCH):
            if seed in used:
                continue
            blocks = search(seed, repetitions)
            trial = dict(counts)
            for block in blocks:
                for position, mode in enumerate(block):
                    trial[(mode, position)] += 1
            score = max(trial.values())
            if best is None or score < best[0]:
                best = (score, seed, blocks, trial)
            if score <= target:
                break
        _, seed, blocks, counts = best
        if mode_orders(E, seed, repetitions, arms) != blocks:
            _fail('order_drift', 'The protocol order rule changed; update the planner seed search.')
        used.add(seed)
        chosen.append((seed, blocks))
    matrix = {mode: [counts[(mode, position)] for position in range(len(RUNGS))] for mode in RUNGS}
    return chosen, matrix


# ------------------------------------------------------------------ plan
def _inventory_row(model, node, digest):
    return {'engine': 'ollama', 'model': model, 'node': node, 'digest': digest, 'ready': True,
            'available': True, 'context_chars': None, 'estimated_cost_units': None, 'parameters': None,
            'estimated_latency_ms': None, 'verifier_ms': None, 'scheduler_ms': None,
            'verifier_cost_units': None, 'scheduler_cost_units': None}


def experiment_id(key, model, node, budget, repetitions, seed, tag):
    slug = re.sub(r'[^A-Za-z0-9_.-]', '-', model)
    ident = 'frontier-%s-%s-%s-%ds-%dc-r%d-s%d-%s' % (key.lower(), slug, node, budget['wall_seconds'],
                                                       budget['max_calls'], repetitions, seed, tag)
    if not _ID.fullmatch(ident):
        _fail('experiment_id', 'Derived experiment ID is not a valid store identifier: %s' % ident)
    return ident


def _q(value):
    return shlex.quote(str(value))


def _join(argv):
    return ' '.join(_q(a) for a in argv)


def _pin_read(pin_file):
    return 'FREEZE=$(python3 -c %s %s)' % (_q(PIN_CODE), _q(pin_file))


def _check_cli(argv):
    """Parse an emitted benchmark/report command with the MICA CLI's own parser (no dispatch)."""
    from symblic.mica import cli as CLI
    try:
        CLI.parser().parse_args(argv)
    except CLI.CliError as exc:
        _fail('cli_drift', 'The MICA CLI no longer accepts the planned command: %s' % exc)


def build_plan(args):
    """Pure plan construction: reads fixtures and the ordering rules, writes nothing."""
    E, B, C, R = _repo_modules()
    if tuple(B.MODES) != RUNGS:
        _fail('mode_drift', 'symblic.mica.bench.MODES changed; review the rung ladder before planning.')
    if not _TAG.fullmatch(args.tag or ''):
        _fail('tag', 'Tag must be 1-16 letters, digits or _ . - characters.')
    root = _private_path(args.root, 'root')
    plan_dir = _private_path(args.plan_dir or str(root) + '-plan', 'plan-dir')
    if plan_dir == root or root in plan_dir.parents or plan_dir in root.parents:
        _fail('plan-dir', 'The plan directory and the experiment root must be separate; pins are retained outside the store.')
    fixtures_dir = Path(args.fixtures_dir).resolve()
    manifest_sha, manifest, ladder = load_ladder(fixtures_dir)
    available = [row['key'] for row in manifest['families']]
    keys = _families(args.families, available)
    starter = C._budget(manifest['budget'])
    try:
        budget = C._budget({**starter, 'wall_seconds': args.budget_seconds, 'max_calls': args.max_calls})
    except ValueError as exc:
        _fail('budget', str(exc))
    for key in available:
        if ladder[key]['fixture']['request']['budget'] != starter:
            _fail('fixture_budget', '%s does not carry the manifest budget.' % key)
    row = _inventory_row(args.model, args.node, args.digest)
    if R.normalize_inventory([row]) != [row]:
        _fail('inventory', 'The inventory row is not in normalized form.')
    copies = budget != starter
    inventory_path = plan_dir / 'inventory.json'
    plan_path = plan_dir / PLAN_FILE
    seeds, matrix = choose_seeds(E, args.seed, len(keys), args.repetitions)
    per_assignment = budget['wall_seconds'] + GRADING_ALLOWANCE_SECONDS
    per_family = len(RUNGS) * args.repetitions * per_assignment
    runtime_max = math.ceil(per_family * RUNTIME_MARGIN)
    families, freeze, run, status, sessions = [], [], [], [], []
    for index, key in enumerate(keys):
        entry = ladder[key]
        fixture = budgeted_fixture(C, entry['fixture'], budget) if copies else entry['fixture']
        fixture_text = _dump(fixture)
        fixture_path = (plan_dir / 'fixtures' / entry['row']['file']) if copies else entry['path']
        seed, blocks = seeds[index]
        ident = experiment_id(key, args.model, args.node, budget, args.repetitions, seed, args.tag)
        pin_file = plan_dir / 'pins' / (ident + '.freeze.json')
        runs = plan_dir / 'runs'
        hidden = len(entry['fixture']['hidden_tests'])
        families.append({
            'key': key, 'title': entry['row']['title'], 'structure': entry['row']['structure'],
            'exports': entry['row']['exports'], 'fixture_id': entry['fixture']['id'],
            'family': entry['fixture']['family'], 'public_tests': len(fixture['request']['tests']),
            'hidden_tests': hidden, 'source_fixture': str(entry['path']), 'source_sha256': entry['row']['sha256'],
            'fixture': str(fixture_path), 'fixture_copy': copies, 'fixture_sha256': _sha256(fixture_text),
            'request_sha256': E.digest(C.normalize_request(fixture['request'])),
            'experiment_id': ident, 'seed': seed, 'mode_order': blocks, 'pin_file': str(pin_file),
            'assignments': len(RUNGS) * args.repetitions, 'estimated_seconds': per_family,
            'grading_worst_case_seconds': 15 + hidden * (2 * CHECK_CASE_SECONDS + 1)})
        freeze_argv = [str(BIN), 'mica', 'benchmark', '--root', str(root), '--id', ident,
                       '--fixture', str(fixture_path), '--inventory', str(inventory_path),
                       '--repetitions', str(args.repetitions), '--seed', str(seed), '--split', 'dev']
        _check_cli(freeze_argv[2:])
        freeze.append({'family': key, 'experiment_id': ident, 'argv': freeze_argv, 'stdout': str(pin_file),
                       'shell': '(set -o noclobber; %s > %s)' % (_join(freeze_argv), _q(pin_file))})
        cli_args = ['benchmark', '--root', str(root), '--id', ident, '--inventory', str(inventory_path),
                    '--freeze', '$FREEZE', '--run']
        _check_cli(cli_args)
        launch = ['systemd-run', '--user', '--scope', '"--unit=symblic-frontier-%s-$STAMP"' % key.lower(),
                  '--slice=symblic-work.slice', '--property=CPUQuota=150%', '--property=MemoryMax=2G',
                  '--property=TasksMax=256', '--property=RuntimeMaxSec=%d' % runtime_max,
                  '--working-directory=%s' % REPO, 'env', 'DASHBOARD_DIR=%s' % REPO, 'nice', '-n', '10',
                  str(SERVICE_PYTHON), '-I', '-B', '-c', CLI_CODE, str(REPO)]
        quoted = [a if a.startswith('"--unit=') else _q(a) for a in launch]
        quoted += [_q(a) for a in cli_args[:-2]] + ['"$FREEZE"', '--run']
        out_stem = '%s/%s.run-$STAMP' % (runs, ident)
        run.append({
            'family': key, 'session': index + 1, 'experiment_id': ident, 'cli_argv': cli_args,
            'estimated_seconds': per_family, 'runtime_max_seconds': runtime_max,
            'over_hour_bound': per_family > HOUR_BOUND_SECONDS,
            'shell': '%s && STAMP=$(date -u +%%Y%%m%%dT%%H%%M%%SZ) && %s > "%s.json" 2> "%s.err"' % (
                _pin_read(pin_file), ' '.join(quoted), out_stem, out_stem),
            'documented_equivalent': '%s && %s --freeze "$FREEZE" --run' % (
                _pin_read(pin_file), _join([str(BIN), 'mica'] + cli_args[:-3]))})
        report_args = ['report', '--root', str(root), '--id', ident, '--freeze', '$FREEZE']
        _check_cli(report_args)
        status.append({'family': key, 'shell': '%s && %s --freeze "$FREEZE"' % (
            _pin_read(pin_file), _join([str(BIN), 'mica'] + report_args[:-2]))})
        sessions.append({'session': index + 1, 'family': key, 'assignments': len(RUNGS) * args.repetitions,
                         'estimated_seconds': per_family, 'over_hour_bound': per_family > HOUR_BOUND_SECONDS})
    rungs = [{'rung': index + 1, 'mode': mode, 'factors': B.MODE_FACTORS[mode],
              'frozen_in': [f['experiment_id'] for f in families],
              'assignments': len(keys) * args.repetitions} for index, mode in enumerate(RUNGS)]
    reproduce = ['python3', str(SCRIPT), 'plan', '--model', args.model, '--node', args.node, '--root', str(root),
                 '--budget-seconds', str(budget['wall_seconds']), '--max-calls', str(budget['max_calls']),
                 '--repetitions', str(args.repetitions), '--families', ','.join(keys), '--seed', str(args.seed),
                 '--plan-dir', str(plan_dir), '--tag', args.tag]
    if args.digest:
        reproduce += ['--digest', args.digest]
    if fixtures_dir != FIXTURES:
        reproduce += ['--fixtures-dir', str(fixtures_dir)]
    confounds = [{'id': name, 'text': text} for name, text in CONFOUNDS]
    if args.digest is None:
        confounds.append({'id': 'digest_unpinned', 'text': 'No digest pin: the inventory row is an explicit cold '
                          'start, so the families are not pinned to one set of weights. ' + DIGEST_SOURCE})
    if per_family > HOUR_BOUND_SECONDS:
        confounds.append({'id': 'session_exceeds_hour_bound', 'text': 'Each family session is estimated at '
                          '%d s, beyond about an hour of continuous node load. Ask the operator before launching, '
                          'or plan the 300 s / 8-call rung.' % per_family})
    if max(max(row) for row in matrix.values()) > math.ceil(len(keys) * args.repetitions / len(RUNGS)):
        confounds.append({'id': 'position_imbalance', 'text': 'No seed in the searched range balanced every rung '
                          'over the dispatch positions; see seeds.position_matrix.'})
    if copies:
        confounds.append({'id': 'rebudgeted_fixtures', 'text': 'The budget differs from the committed fixtures, so '
                          'materialize writes re-budgeted private copies; hidden tests are unchanged.'})
    plan = {
        'version': VERSION, 'kind': 'symblic_frontier_ladder_plan', 'scope': LIMITATIONS[0],
        'hypothesis': 'With the model, its weights, the node and the caller budget fixed, changing only the '
                      'compiler mode changes which task families reach an independent hidden pass.',
        'generator': {'script': str(SCRIPT), 'sha256': _sha256(SCRIPT.read_bytes())},
        'model': {'engine': 'ollama', 'model': args.model, 'node': args.node, 'digest': args.digest,
                  'digest_status': 'pinned' if args.digest else 'unpinned_cold_start'},
        'inventory': {'path': str(inventory_path), 'rows': [row], 'row_fields': list(INVENTORY_FIELDS),
                      'digest_source': DIGEST_SOURCE,
                      'readiness_routes': [{'route': route, 'url': API + route, 'check': check.replace('MODEL', args.model).replace('NODE', args.node)}
                                           for route, check in READINESS]},
        'budget': budget, 'starter_budget': starter, 'repetitions': args.repetitions, 'split': 'dev',
        'root': str(root), 'plan_dir': str(plan_dir), 'plan_file': str(plan_path),
        'fixtures': {'directory': str(fixtures_dir), 'manifest_sha256': manifest_sha},
        'seeds': {'base': args.seed, 'search': SEED_SEARCH, 'families': {f['key']: f['seed'] for f in families},
                  'position_matrix': matrix},
        'rungs': rungs, 'families': families,
        'estimate': {'per_assignment_seconds': per_assignment, 'grading_allowance_seconds': GRADING_ALLOWANCE_SECONDS,
                     'assignments': len(keys) * len(RUNGS) * args.repetitions,
                     'total_seconds': per_family * len(keys), 'total_hours': round(per_family * len(keys) / 3600, 2),
                     'hour_bound_seconds': HOUR_BOUND_SECONDS, 'sessions': sessions,
                     'formula': 'assignments x (wall_seconds + 120 s grading)'},
        'commands': {
            'plan': _join(reproduce),
            'readiness': ["curl -s '%s%s'" % (API, route) for route, _ in READINESS],
            'materialize': _join(['python3', str(SCRIPT), 'materialize', '--plan', str(plan_path)]),
            'freeze': freeze, 'run': run, 'status': status,
            'aggregate': _join(['python3', str(SCRIPT), 'aggregate', '--plan', str(plan_path)])},
        'confounds': confounds, 'limitations': list(LIMITATIONS)}
    plan['plan_sha256'] = _sha256(_canonical(plan))
    return plan


def render_plan(plan):
    m, b, e = plan['model'], plan['budget'], plan['estimate']
    lines = ['Frontier ladder plan (%s)' % plan['scope'],
             'Model     %s on %s, digest %s' % (m['model'], m['node'], m['digest'] or 'NOT PINNED (explicit cold start)'),
             'Budget    %d s wall, %d calls per assignment; candidates %d, depth %d, units %d, workers %d, retries %d, '
             'context %d chars. Identical for every family and rung.' % (
                 b['wall_seconds'], b['max_calls'], b['max_candidates'], b['max_depth'], b['max_units'],
                 b['max_workers'], b['retries'], b['context_chars']),
             'Ladder    ' + ', '.join('%d %s' % (r['rung'], r['mode']) for r in plan['rungs'])
             + '. Each family freeze holds all six rungs.',
             'Estimate  %d assignments x (%d s + %d s grading) = %d s (%.2f h); one session per family:' % (
                 e['assignments'], b['wall_seconds'], e['grading_allowance_seconds'], e['total_seconds'], e['total_hours'])]
    for f in plan['families']:
        lines.append('  %s %-32s %2d hidden, seed %d, %d s%s  order %s' % (
            f['key'], f['title'], f['hidden_tests'], f['seed'], f['estimated_seconds'],
            ' (OVER the 1 h bound: ask the operator)' if f['estimated_seconds'] > HOUR_BOUND_SECONDS else '',
            ' | '.join(' '.join(block) for block in f['mode_order'])))
    c = plan['commands']
    lines += ['', 'Step 0  Reproduce this plan:', '  ' + c['plan'],
              '', 'Step 1  Read-only checks before freezing and before every session (host API on loopback; read them yourself, this planner never calls them):']
    for item, command in zip(plan['inventory']['readiness_routes'], c['readiness']):
        lines += ['  ' + command, '      ' + item['check']]
    lines += ['  Digest: ' + plan['inventory']['digest_source'],
              '', 'Step 2  Write the reviewed inventory%s (refuses to change existing files):' % (
                  ' and re-budgeted fixture copies' if any(f['fixture_copy'] for f in plan['families']) else ''),
              '  ' + c['materialize'], '  Row: ' + _canonical(plan['inventory']['rows'][0]),
              '', 'Step 3  Freeze every family back to back, before any run; retain the pins (no overwrite):']
    lines += ['  ' + item['shell'] for item in c['freeze']]
    lines += ['', 'Step 4  Run serially: one family per session on %s, one assignment at a time. Re-check Step 1 '
              'first, wait for each to finish, rest the node between sessions:' % m['node']]
    for item in c['run']:
        lines += ['  # session %d, %s, about %d s, scope stops after %d s' % (
            item['session'], item['family'], item['estimated_seconds'], item['runtime_max_seconds']),
            '  ' + item['shell']]
    lines += ['  Documented tools/symblic form of the same CLI path (subject to its 120 CPU-second limit):',
              '  ' + c['run'][0]['documented_equivalent'],
              '', 'Step 5  Status any time (read-only):'] + ['  ' + item['shell'] for item in c['status']]
    lines += ['', 'Step 6  Aggregate (read-only; every pending or unknown assignment stays in the denominator):',
              '  ' + c['aggregate'], '', 'Confounds:'] + ['  - %s: %s' % (x['id'], x['text']) for x in plan['confounds']]
    lines += ['', 'Plan file: %s (sha256 %s)' % (plan['plan_file'], plan['plan_sha256'])]
    return '\n'.join(lines)


# ------------------------------------------------------------------ files
def _private_dir(path):
    path = Path(path)
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.lstat()
    except OSError as exc:
        _fail('private_directory', 'Cannot create %s: %s' % (path, exc.strerror or type(exc).__name__))
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        _fail('private_directory', '%s must be a directory owned by you with mode 0700.' % path)


def _publish(path, text, *, replace=False):
    """Write a 0600 file atomically. Equal content is a no-op; other content is refused unless replace."""
    path = Path(path)
    data = text.encode('utf-8')
    if path.is_symlink():
        _fail('existing_file', '%s is a symlink.' % path)
    if path.exists():
        if path.read_bytes() == data:
            return {'path': str(path), 'status': 'unchanged', 'sha256': _sha256(data)}
        if not replace:
            _fail('existing_file', '%s exists with different content; it may already be frozen. '
                                   'Keep it, or plan into a new directory.' % path)
    temporary = path.with_name('.%s.%d.tmp' % (path.name, os.getpid()))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'path': str(path), 'status': 'written', 'sha256': _sha256(data)}


def load_plan(path):
    _, plan = _read_json(Path(path))
    if type(plan) is not dict or plan.get('kind') != 'symblic_frontier_ladder_plan' or plan.get('version') != VERSION:
        _fail('plan', 'Not a frontier ladder plan.')
    body = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    if plan.get('plan_sha256') != _sha256(_canonical(body)):
        _fail('plan_pin', 'The plan file changed after it was written; re-plan instead of editing it.')
    return plan


def write_plan(plan, *, replace=False):
    _private_dir(plan['plan_dir'])
    return _publish(plan['plan_file'], json.dumps(plan, ensure_ascii=True, sort_keys=True, indent=2) + '\n',
                    replace=replace)


def materialize(plan_path):
    """Write the planned inventory and re-budgeted fixture copies. Nothing is frozen or run."""
    plan = load_plan(plan_path)
    _, _, C, R = _repo_modules()
    rows = plan['inventory']['rows']
    if R.normalize_inventory(rows) != rows:
        _fail('inventory', 'Planned inventory rows are not normalized.')
    plan_dir = Path(plan['plan_dir'])
    for sub in ('', 'pins', 'runs'):
        _private_dir(plan_dir / sub if sub else plan_dir)
    Path(plan['root']).parent.mkdir(parents=True, exist_ok=True)
    files = [_publish(plan['inventory']['path'], _dump(rows))]
    for family in plan['families']:
        if not family['fixture_copy']:
            continue
        raw, fixture = _read_json(Path(family['source_fixture']))
        if _sha256(raw) != family['source_sha256']:
            _fail('fixture_changed', '%s changed since planning.' % family['source_fixture'])
        text = _dump(budgeted_fixture(C, fixture, plan['budget']))
        if _sha256(text) != family['fixture_sha256']:
            _fail('fixture_copy', 'Re-budgeted %s does not match its planned digest.' % family['key'])
        _private_dir(Path(family['fixture']).parent)
        files.append(_publish(family['fixture'], text))
    return {'version': VERSION, 'status': 'materialized', 'plan_sha256': plan['plan_sha256'], 'files': files,
            'next': 'Freeze every family (plan commands.freeze), retaining each pin file.',
            'scope': 'Inputs only; nothing was frozen, run or called.'}


# ------------------------------------------------------------------ aggregate
def _pin_overrides(values):
    pins = {}
    for value in values:
        ident, _, sha = value.partition('=')
        if not _ID.fullmatch(ident) or not _SHA.fullmatch(sha) or ident in pins:
            _fail('pin', 'Use --pin EXPERIMENT_ID=FREEZE_SHA256 once per experiment.')
        pins[ident] = sha
    return pins


def _retained_pin(family, overrides):
    if family['experiment_id'] in overrides:
        return overrides[family['experiment_id']], 'argument', None
    path = Path(family['pin_file'])
    if not path.exists():
        return None, None, None
    try:
        _, receipt = _read_json(path)
    except PlanError as exc:
        return None, str(path), {'code': exc.code}
    sha = receipt.get('freeze_sha256') if type(receipt) is dict else None
    if type(sha) is not str or not _SHA.fullmatch(sha):
        code = receipt.get('error', {}).get('code') if type(receipt) is dict and type(receipt.get('error')) is dict else None
        return None, str(path), {'code': 'pin_missing', 'freeze_error': code}
    return sha, str(path), None


def _frozen_controls(E, bench, plan, family):
    """Read-only check that the frozen experiment is the planned one (same loader as the CLI)."""
    with bench._lock():
        _, frozen, _ = bench._load()
    arms = frozen['arms']
    controls = arms[0]['controls']
    settings = controls['model'].get('settings', {})
    implementation = settings.get('construction_implementation')
    checks = {'split': frozen['split'] == plan['split'],
              'repetitions': frozen['repetitions'] == plan['repetitions'],
              'order_seed': frozen.get('order', {}).get('seed') == family['seed'],
              'request': (len(frozen['cases']) == 1
                          and E.digest(frozen['cases'][0]['input']) == family['request_sha256']),
              'budget': controls['budget'].get('caller_budget') == plan['budget'],
              'inventory': settings.get('inventory') == plan['inventory']['rows'],
              'arms_share_controls': all(a['controls'] == controls for a in arms)}
    return {'checks': checks, 'matched': all(checks.values()),
            'implementation_sha256': E.digest(implementation) if implementation is not None else None}


def aggregate(plan_path, pins=()):
    """Family x rung table from the bench's own report reader; nothing is dispatched."""
    plan = load_plan(plan_path)
    E, B, _, _ = _repo_modules()
    overrides = _pin_overrides(pins)
    reps = plan['repetitions']
    families, cells, confounds = [], [], Counter()
    implementations = {}
    for family in plan['families']:
        sha, source, problem = _retained_pin(family, overrides)
        state, report, controls = ('pin_unreadable' if problem else 'not_frozen'), None, None
        if sha:
            try:
                bench = B.MicaBenchmark(plan['root'], family['experiment_id'], sha)
                report = bench.report()
                state = 'reported'
            except (ValueError, OSError, KeyError, TypeError) as exc:
                state, report = 'unreadable', None
                problem = {'code': getattr(exc, 'code', None) or type(exc).__name__, 'detail': str(exc)[:160]}
        if report:
            try:
                controls = _frozen_controls(E, bench, plan, family)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                controls = {'checks': {}, 'matched': False, 'implementation_sha256': None,
                            'error': type(exc).__name__}
            for item in report['confounds']:
                confounds[item['kind'] if item['kind'] != 'declared_control_difference'
                          else 'declared_control_difference:' + item['axis']] += 1
            if controls['implementation_sha256']:
                implementations[family['key']] = controls['implementation_sha256']
            if 'error' in controls:
                confounds['frozen_controls_unverified'] += 1
            elif not controls['matched']:
                confounds['frozen_controls_differ_from_plan'] += 1
        mode_of = {row['assignment_id']: row['mode'] for row in report['assignments']} if report else {}
        over_budget = Counter(mode_of.get(item.get('assignment_id')) for item in (report or {}).get('confounds', [])
                              if item['kind'] == 'budget_exceeded')
        families.append({'key': family['key'], 'title': family['title'], 'experiment_id': family['experiment_id'],
                         'state': state, 'freeze_sha256': sha, 'pin_source': source, 'problem': problem,
                         'assigned': report['assigned'] if report else len(RUNGS) * reps,
                         'completed_receipts': report['completed_receipts'] if report else 0,
                         'frozen_controls': controls})
        for rung, mode in enumerate(RUNGS, 1):
            group = report['modes'][mode] if report else None
            if group is None:
                assigned, passed = reps, 0
                statuses, grades = {state: reps}, {'missing': reps}
                calls = {'observed_total': None, 'observed_runs': 0, 'unobserved_runs': reps}
                wall = {'observed_total': None, 'observed_runs': 0, 'unobserved_runs': reps}
            else:
                assigned, passed = group['assigned'], group['successes']
                statuses, grades, calls = group['statuses'], group['grade_statuses'], group['calls']
                cost = group['costs']['wall_seconds']
                wall = {k: cost[k] for k in ('observed_total', 'observed_runs', 'unobserved_runs')}
                if assigned != reps:
                    confounds['assigned_differs_from_plan'] += 1
            cells.append({'family': family['key'], 'rung': rung, 'mode': mode, 'assigned': assigned,
                          'passed': passed, 'pass_rate': passed / assigned if assigned else None,
                          'unresolved': sum(v for k, v in statuses.items() if k in UNRESOLVED),
                          'statuses': statuses, 'grade_statuses': grades, 'budget_exceeded': over_budget[mode],
                          'calls': calls, 'wall_seconds': wall})
    if len(set(implementations.values())) > 1:
        confounds['construction_implementation_differs_across_families'] += 1
    by_rung = []
    for rung, mode in enumerate(RUNGS, 1):
        rows = [c for c in cells if c['mode'] == mode]
        assigned = sum(c['assigned'] for c in rows)
        passed = sum(c['passed'] for c in rows)
        by_rung.append({'rung': rung, 'mode': mode, 'assigned': assigned, 'passed': passed,
                        'pass_rate': passed / assigned if assigned else None,
                        'families_with_a_pass': [c['family'] for c in rows if c['passed']],
                        'families_always_passed': [c['family'] for c in rows if c['assigned'] and c['passed'] == c['assigned']]})
    by_family = []
    for family in plan['families']:
        rows = [c for c in cells if c['family'] == family['key']]
        passing = [c for c in rows if c['passed']]
        by_family.append({'family': family['key'], 'first_rung_with_a_pass': passing[0]['rung'] if passing else None,
                          'first_mode_with_a_pass': passing[0]['mode'] if passing else None,
                          'rungs_with_a_pass': [c['rung'] for c in passing],
                          'unresolved': sum(c['unresolved'] for c in rows)})
    return {'version': VERSION, 'kind': 'symblic_frontier_ladder_aggregate', 'plan_sha256': plan['plan_sha256'],
            'model': plan['model'], 'budget': plan['budget'], 'repetitions': reps,
            'success': 'done, every hidden case passed, no budget violation (symblic.mica.bench report success)',
            'denominator': 'every planned assignment, including pending, unknown, damaged and not yet frozen',
            'families': families, 'cells': cells, 'by_rung': by_rung, 'by_family': by_family,
            'confounds': dict(sorted(confounds.items())),
            'construction_implementations': implementations,
            'limitations': list(LIMITATIONS[2:]) + [('Repetition 1 gives one observation per cell; read a pass as '
                                                      'existence at that rung, not a rate.')]}


def _short(value, digits=1):
    return '-' if value is None else ('%.*f' % (digits, value) if isinstance(value, float) else str(value))


def _observed(cost, assigned):
    total = cost['observed_total'] if cost['observed_runs'] else None
    return '%s (%d/%d)' % (_short(total), cost['observed_runs'], assigned)


def _outcomes(cell):
    text = ', '.join('%s %d' % kv for kv in sorted(cell['statuses'].items()))
    grades = {k: v for k, v in cell['grade_statuses'].items() if k != 'missing'}
    if grades:
        text += '; grade ' + ', '.join('%s %d' % kv for kv in sorted(grades.items()))
    if cell['budget_exceeded']:
        text += '; over call budget %d' % cell['budget_exceeded']
    return text


def render_aggregate(result):
    m, b = result['model'], result['budget']
    lines = ['Frontier ladder: %s on %s, digest %s, budget %d s / %d calls, repetitions %d' % (
                 m['model'], m['node'], (m['digest'] or 'unpinned')[:12], b['wall_seconds'], b['max_calls'],
                 result['repetitions']),
             'Hidden pass = ' + result['success'] + '.',
             'Denominator = ' + result['denominator'] + '.', '',
             '%-6s %-4s %-21s %-7s %-6s %-14s %-16s %s' % ('Family', 'Rung', 'Mode', 'Pass', 'Rate',
                                                          'Calls(obs/n)', 'Wall s(obs/n)', 'Outcomes')]
    for c in result['cells']:
        lines.append('%-6s %-4d %-21s %-7s %-6s %-14s %-16s %s' % (
            c['family'], c['rung'], c['mode'], '%d/%d' % (c['passed'], c['assigned']),
            _short(c['pass_rate'], 2), _observed(c['calls'], c['assigned']),
            _observed(c['wall_seconds'], c['assigned']), _outcomes(c)))
    lines += ['', 'By rung over the planned families:']
    for row in result['by_rung']:
        lines.append('  %d %-21s %d/%d  families with a pass: %s' % (
            row['rung'], row['mode'], row['passed'], row['assigned'], ', '.join(row['families_with_a_pass']) or 'none'))
    lines += ['', 'First rung with a hidden pass: ' + '; '.join(
        '%s %s' % (row['family'], '%s (%d)' % (row['first_mode_with_a_pass'], row['first_rung_with_a_pass'])
                   if row['first_rung_with_a_pass'] else 'none') for row in result['by_family'])]
    lines += ['Experiments: ' + '; '.join('%s %s%s' % (f['key'], f['state'], (' (%s)' % f['freeze_sha256'][:12])
                                                       if f['freeze_sha256'] else '') for f in result['families'])]
    lines.append('Confounds: ' + ('; '.join('%s %d' % kv for kv in result['confounds'].items()) or 'none recorded'))
    return '\n'.join(lines)


# ------------------------------------------------------------------ entry
def main(argv=None, *, out=None, err=None):
    out, err = out or sys.stdout, err or sys.stderr
    raw = list(sys.argv[1:] if argv is None else argv)
    as_json = '--json' in raw
    try:
        refused = [flag for flag in raw if flag.split('=', 1)[0] in REFUSED_FLAGS]
        if refused:
            _fail('refused_execution', 'This planner never freezes, runs or calls anything (%s). Run the printed '
                                       'commands yourself, one at a time.' % ', '.join(refused))
        command, rest = (raw[0], raw[1:]) if raw and raw[0] in ('plan', 'materialize', 'aggregate') else ('plan', raw)
        if any(flag in rest for flag in ('-h', '--help')):
            print(__doc__.strip(), file=out)
            return 0
        args = _parser(command).parse_args(rest)
        if command == 'plan':
            result = build_plan(args)
            written = None if args.no_write else write_plan(result, replace=args.replace)
            if as_json:
                print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2), file=out)
            else:
                print(render_plan(result), file=out)
                print('Plan %s: %s' % (written['status'], written['path']) if written else 'Plan not written (--no-write).',
                      file=out)
        elif command == 'materialize':
            result = materialize(args.plan)
            print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) if as_json else '\n'.join(
                '%s %s' % (f['status'], f['path']) for f in result['files']) + '\n' + result['next'], file=out)
        else:
            result = aggregate(args.plan, args.pin)
            print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) if as_json
                  else render_aggregate(result), file=out)
        return 0
    except PlanError as exc:
        error = {'ok': False, 'error': {'code': exc.code, 'message': str(exc)[:1000]}}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        error = {'ok': False, 'error': {'code': getattr(exc, 'code', type(exc).__name__), 'message': str(exc)[:1000]}}
    if as_json:
        print(json.dumps(error, ensure_ascii=True, sort_keys=True), file=out)
    else:
        print('error (%s): %s' % (error['error']['code'], error['error']['message']), file=err)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

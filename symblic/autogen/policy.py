"""Autogen policy: the pure decision rules behind regenerating coding-agent attempts.

What autogen is
    A Symblic task is a list of precise statements, one per line, each carried out by a fresh
    agent and accepted only by code: the files it names exist, parse, and pass the operator's
    commands. Autogen adds regeneration on top of that: several independent candidates per
    statement, a new attempt with a different strategy when they fail, decomposition of a
    statement into smaller statements when regeneration stops helping, a checkpointed handoff
    when a worker runs out of context, and perpetual lanes for monitoring or indexing work that
    repeat generation after generation. Every decision is a function of durable evidence, every
    launch is bounded by one run-wide budget, and no agent's own claim ever changes state.

What this module does
    It has no I/O. It validates a policy (normalize), lints statements (lint), plans each
    statement's code checks (plan_checks), classifies what happened to an attempt (classify),
    measures code-verified progress (progress_metrics, is_progress), decides the next action for
    one statement node (decide) and writes the worker prompts (worker_suffix, split_prompt,
    designer_prompt, handoff_prompt, perpetual_prompt). There are two modes:

      bounded     the counts in LIMITS (regenerate, depth, generations, agents_max,
                  wall_seconds) are caps; a node that exhausts them fails.
      until_done  a node keeps going while it has an untried strategy or is making progress;
                  after novelty_limit attempts without progress it is split into smaller
                  statements; when nothing novel is left it ends "stuck" (resumable after a
                  change), never "failed".

Who uses it
    symblic/autogen/coordinator.py (AutogenManager) owns the records, runs the checks and launches
    attempts through a TaskRunner. The command line tools/symblic-task uses lint() when it can import
    this module and otherwise its own copy, and repeats CHECKOUT_LOCK; tests/autogen/test_policy.py
    checks that both agree, so the command line refuses the same statements the coordinator would.

Status
    Experimental. Every rule is unit-tested with fixed inputs (tests/autogen/test_policy.py).
    What real runs with real models showed is summarized in symblic/autogen/README.md.
"""
from __future__ import annotations

import hashlib
import json
import re

VERSION = 1

STRATEGIES = ('fresh', 'feedback', 'other_node', 'other_engine', 'stronger_model')
# stronger_model stays in the catalogue, but normalize() refuses it until a model ladder is wired:
# nothing fills node['stronger_models'], so the strategy could never be chosen.
WIRED_STRATEGIES = ('fresh', 'feedback', 'other_node', 'other_engine')
FAILURE_CLASSES = ('INFRASTRUCTURE', 'REFUSAL', 'NO_OUTPUT', 'SYNTAX', 'CHECK_FAILURE',
                   'CLAIM_MISMATCH', 'CONTEXT_EXHAUSTED', 'TIMEOUT', 'CANCELLED', 'UNKNOWN',
                   'CONFLICT', 'HIDDEN_FAILURE', 'FETCH_FAILURE')
# Not the statement's fault: never counted toward decomposition.
NON_SEMANTIC = ('INFRASTRUCTURE', 'REFUSAL', 'CANCELLED', 'CONFLICT', 'FETCH_FAILURE')
# Placement failures: the next attempt moves to another machine or engine.
PLACEMENT_FAILURES = ('INFRASTRUCTURE', 'REFUSAL', 'TIMEOUT', 'FETCH_FAILURE')
# Failures whose public check output helps a fresh attempt (HIDDEN_FAILURE never feeds back).
FEEDBACK_FAILURES = ('SYNTAX', 'CHECK_FAILURE', 'CLAIM_MISMATCH', 'NO_OUTPUT')
FEEDBACK_KINDS = ('exists', 'absent', 'syntax', 'command', 'change', 'claim', 'designed')
# Strategies exempt from the fingerprint cycle rule: feedback carries new evidence, fresh is the
# plain retry the regenerate count bounds.
CYCLE_EXEMPT = ('feedback', 'fresh')
ACTIONS = ('wait', 'launch', 'design', 'accept', 'regenerate', 'decompose', 'handoff', 'perpetual_next', 'fail', 'stuck', 'stop')
# Hard floors that hold even in until_done mode: a statement is never split below the lint minimum, the
# tree never nests deeper than this, and a worker never runs longer than attempt_seconds.
HARD_DEPTH = 12
MECHANISMS = ('regenerate', 'decompose', 'replan', 'handoff')

LIMITS = {
    'candidates': (1, 4),          # independent attempts launched together for one statement
    'regenerate': (0, 8),          # further attempts after the first wave fails
    'depth': (0, 3),               # how many times a statement may be split into smaller statements
    'children': (2, 8),            # statements a planner may split one statement into
    'generations': (1, 16),        # successor workers after a context handoff (or perpetual lanes)
    'agents_max': (1, 96),         # global launch cap for the whole run, every kind of attempt
    'attempt_seconds': (120, 14400),
    'wall_seconds': (300, 172800),
    'interval_seconds': (60, 86400),
    'feedback_chars': (200, 6000),
    'novelty_limit': (1, 8),       # consecutive attempts without novelty or progress before escalating
    'saturation': (0, 16),         # perpetual: generations in a row with no new item before the lane stops (0 = never)
}
DEFAULTS = {
    'candidates': 1, 'regenerate': 2, 'depth': 0, 'children': 4, 'generations': 3,
    'agents_max': 24, 'attempt_seconds': 3600, 'wall_seconds': 6 * 3600, 'interval_seconds': 900,
    'feedback_chars': 2000, 'strategies': ['fresh', 'feedback', 'other_node', 'other_engine'],
    'perpetual': False, 'checks': {}, 'final': [], 'hidden': [], 'syntax': True, 'require_change': True,
    # v2: regenerate until done. With until_done the counts above (regenerate, depth, generations) stop being
    # caps and agents_max / wall_seconds default to 0 (unlimited) unless given: a node keeps regenerating while
    # it still has something new to try or is making progress, is subdivided when it cannot be done in one
    # piece, and ends 'stuck' only when every novel action has been tried. An explicit agents_max or
    # wall_seconds with until_done is honoured as a safety cap (the run then ends stuck, never failed).
    'until_done': False, 'novelty_limit': 2, 'self_split': True, 'designer': False, 'saturation': 0,
}
HANDOFF_FILE = 'HANDOFF.md'
CHECKPOINT_FILE = 'AUTOGEN-CHECKPOINT.json'
SPLIT_FILE = 'AUTOGEN-SPLIT.txt'
DESIGN_FILE = 'AUTOGEN-TESTS.sh'
INDEX_FILE = 'AUTOGEN-INDEX.jsonl'
CONTROL_FILES = (HANDOFF_FILE, CHECKPOINT_FILE, SPLIT_FILE, DESIGN_FILE, INDEX_FILE)
DESIGN_MAX_CHARS = 8000
ITEM_KEY_MAX = 200

# Every attempt runs in its own git checkout (one beside the project, or one on a remote node),
# so no prompt may name the project folder: a literal-minded worker would write into the
# operator's copy. The coordinator localizes every attempt instruction (localize below).
WORKING_FOLDER = 'the current working folder (the git checkout you were started in; run pwd once)'
# the whole instruction a small local model (engine `local`) receives besides its statement: short on purpose
LOCAL_RULE = 'Write the named files in the current working folder, then stop. Only files on disk count.'
LOCAL_LOCK = 'Work only in the current working folder (run pwd once); write files there with their exact names.'
# Keep equal to CHECKOUT_LOCK in tools/symblic-task (tests/autogen/test_policy.py compares both).
CHECKOUT_LOCK = ('Your working folder is exactly the git checkout you were started in (run pwd once). Every file '
                 'your statement names is created or modified directly in that checkout, at the relative path '
                 'given. Do not explore other tests, modules or folders, do not investigate this machine or '
                 'your own environment, do not start background searches; read only the files your statement '
                 'names, execute your statement and finish. Keep every name, count and behavior exactly as your '
                 'statement fixes it.')

MAX_LINES, MAX_CHARS = 64, 60000
VERBS = ('create', 'extend', 'add', 'write', 'run', 'make', 'build', 'update', 'replace', 'remove', 'delete',
         'verify', 'check', 'implement', 'rename', 'move', 'copy', 'install', 'generate', 'produce', 'append',
         'record', 'fix', 'rewrite', 'convert', 'export', 'read', 'inspect', 'test', 'compile', 'document', 'split',
         'index', 'monitor', 'watch', 'collect', 'summarize', 'summarise', 'research', 'scan')
SYNTAX_CHECKS = {
    '.js': ['node', '--check', '{file}'], '.mjs': ['node', '--check', '{file}'], '.cjs': ['node', '--check', '{file}'],
    '.py': ['python3', '-c', 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1])', '{file}'],
    '.sh': ['bash', '-n', '{file}'], '.bash': ['bash', '-n', '{file}'],
    '.json': ['python3', '-c', 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))', '{file}'],
}
# Advisory only: this protects the operator from a slip in their own check commands, it is not a
# sandbox (`python3 -c "__import__('os')..."` and friends pass). The word boundary applies to the
# words only: `rm -rf /` ends in a non-word character, so a trailing \b never matched it at the end
# of the string. Quotes and backticks start a command too (bash -c "ssh ...", `sudo ...`).
# A line the sandbox launcher (symblic/sandbox/landlock.py) prints about itself, e.g. "<launcher>: unknown
# argument" or "<launcher>: refusing to run unsandboxed". The launcher exits 1 on a bad argument, which
# would otherwise look like a genuinely failing test script.
LAUNCHER_MESSAGE = re.compile(r'^[\w.-]*(?:sandbox|landlock)[\w.-]*: ', re.M | re.I)
UNSAFE_COMMAND = re.compile(r'''(?:^|[\s;&|(`'"])(?:(?:sudo|su|mkfs|shutdown|reboot|systemctl|ssh|scp|rsync|curl|wget|pip\s+install|git\s+push|docker|kill(?:all)?)\b|rm\s+-(?:rf|fr)\s+/|dd\s)''')


class AutogenError(ValueError):
    """A refused request or an unusable record; `status` follows HTTP (400 refused, 404 unknown run,
    409 conflicting request or unreadable record)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(value) -> str:
    """The sha256 of a value's canonical JSON (sorted keys, no spaces): equal values, equal digests."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


# ------------------------------------------------------------------------------ policy

def _int(spec, key):
    low, high = LIMITS[key]
    value = spec.get(key, DEFAULTS[key])
    if isinstance(value, bool) or not isinstance(value, int):
        raise AutogenError(f'{key} must be an integer from {low} to {high}.')
    if not low <= value <= high:
        raise AutogenError(f'{key} must be from {low} to {high}; {value} was given.')
    return value


def _command_list(value, label):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(c, str) or not c.strip() or len(c) > 2000 or '\0' in c for c in value):
        raise AutogenError(f'{label} must be a list of non-empty command strings under 2000 characters.')
    for command in value:
        if UNSAFE_COMMAND.search(command):
            raise AutogenError(f'{label} contains a command the autogen runner refuses: {command[:80]}')
    return [c.strip() for c in value]


def normalize(spec, *, engines=(), nodes=()):
    """Validate an autogen policy object; unknown keys and out-of-range values are refused.

    `engines` and `nodes` are the catalogue the coordinator admits; `other_engine` and
    `other_node` strategies are kept in the rotation only when an alternative exists.
    """
    if spec is None or spec is True:
        spec = {}
    if not isinstance(spec, dict):
        raise AutogenError('autogen must be an object of policy fields (or true for the defaults).')
    unknown = sorted(set(spec) - set(DEFAULTS) - {'version'})
    if unknown:
        raise AutogenError('Unknown autogen field' + ('s ' if len(unknown) > 1 else ' ') + ', '.join(unknown) + '.')
    policy = {'version': VERSION}
    for key in ('until_done', 'self_split', 'designer'):
        value = spec.get(key, DEFAULTS[key])
        if not isinstance(value, bool):
            raise AutogenError(f'{key} must be true or false.')
        policy[key] = value
    for key in ('candidates', 'regenerate', 'depth', 'children', 'generations', 'agents_max',
                'attempt_seconds', 'wall_seconds', 'interval_seconds', 'feedback_chars', 'novelty_limit', 'saturation'):
        value = spec.get(key, DEFAULTS[key])
        if key in ('agents_max', 'wall_seconds') and policy['until_done'] and key not in spec:
            value = 0                     # until_done: unlimited unless the operator gives an explicit cap
        if key in ('agents_max', 'wall_seconds') and value == 0 and not isinstance(value, bool):
            if not policy['until_done']:
                low, high = LIMITS[key]
                raise AutogenError(f'{key} must be from {low} to {high}; 0 was given (0 means unlimited and needs until_done true).')
            policy[key] = 0
            continue
        policy[key] = _int(spec, key)
    strategies = spec.get('strategies', DEFAULTS['strategies'])
    if not isinstance(strategies, list) or not strategies or any(s not in STRATEGIES for s in strategies):
        raise AutogenError('strategies is a non-empty list drawn from ' + ', '.join(WIRED_STRATEGIES) + '.')
    if 'stronger_model' in strategies:
        raise AutogenError('stronger_model is not available yet (no model ladder is wired); use '
                           + ', '.join(WIRED_STRATEGIES) + '.')
    policy['strategies'] = list(dict.fromkeys(strategies))
    for key in ('perpetual', 'syntax', 'require_change'):
        value = spec.get(key, DEFAULTS[key])
        if not isinstance(value, bool):
            raise AutogenError(f'{key} must be true or false.')
        policy[key] = value
    checks = spec.get('checks', {})
    if not isinstance(checks, dict):
        raise AutogenError('checks maps a statement index (as text) to a list of public acceptance commands.')
    policy['checks'] = {}
    for key, value in checks.items():
        if not isinstance(key, str) or not re.fullmatch(r'[0-9]{1,4}', key):
            raise AutogenError('checks keys are statement indexes written as text, like "0".')
        index = str(int(key))  # plan_checks looks up str(index): "01" would otherwise never run
        if index in policy['checks']:
            raise AutogenError(f'checks names statement {index} twice.')
        policy['checks'][index] = _command_list(value, f'checks["{key}"]')
    policy['final'] = _command_list(spec.get('final'), 'final')
    policy['hidden'] = _command_list(spec.get('hidden'), 'hidden')
    if policy['perpetual'] and (policy['depth'] or policy['candidates'] > 1):
        raise AutogenError('A perpetual lane runs one generation at a time: candidates 1 and depth 0.')
    if policy['agents_max'] and policy['candidates'] + policy['regenerate'] > policy['agents_max']:
        raise AutogenError('candidates plus regenerate cannot exceed agents_max.')
    policy['engines'] = [e for e in dict.fromkeys(engines) if isinstance(e, str)]
    policy['nodes'] = [n for n in dict.fromkeys(nodes) if isinstance(n, str)]
    policy['sha256'] = digest({k: v for k, v in policy.items() if k not in ('engines', 'nodes')})
    return policy


# ------------------------------------------------------------------------------ statements

def statements(text):
    """The nonblank lines of a task text, stripped: one statement per line."""
    return [line.strip() for line in (text or '').splitlines() if line.strip()]


def lint(lines, root=''):
    """Findings as (level, line_no, message); shared with tools/symblic-task. Errors stop a start."""
    out = []
    if not lines:
        return [('error', 0, 'no statements: the file has no nonblank line')]
    if len(lines) > MAX_LINES:
        out.append(('error', 0, f'{len(lines)} statements; the engine takes at most {MAX_LINES} per task'))
    if sum(len(x) + 1 for x in lines) > MAX_CHARS:
        out.append(('error', 0, f'the statements exceed {MAX_CHARS} characters in total'))
    names_folder = re.compile(r'(?:in|into|inside|under) the folder /[^\s,;]+|/home/[^\s,;]+')
    pronoun_only = re.compile(r'^(?:it|this|that|the (?:file|folder|project|previous|same) )', re.I)
    extend = re.compile(r'^(?:extend|update|modify|change|edit|rewrite|revise)\b', re.I)
    verify_line = any(re.search(r'\bverif', x, re.I) and re.search(r'\.txt\b', x) for x in lines)
    for n, line in enumerate(lines, 1):
        if len(line) < 20:
            out.append(('error', n, 'shorter than 20 characters: one full self-contained statement per line'))
        if len(line) > 1500:
            out.append(('warning', n, 'longer than 1500 characters: split it into one concern per line'))
        first = re.match(r'[A-Za-z]+', line)
        if not first or first.group(0).lower() not in VERBS:
            out.append(('warning', n, 'does not start with an action verb (Create the file X ..., Extend the file Y ...)'))
        if not names_folder.search(line) and not root:
            out.append(('warning', n, 'names no absolute folder; fresh agents cannot resolve "the current folder" (write "in the folder /home/.../NAME" or pass --root)'))
        if pronoun_only.match(line):
            out.append(('warning', n, 'starts with a pronoun or "the file": name the file and folder, every line is a fresh context'))
        if extend.match(line) and 'keeping every existing part' not in line:
            out.append(('warning', n, 'an edit statement without "keeping every existing part": fresh agents replace what they do not see'))
        if re.search(r'\b(?:the previous|the last|as before|like above|earlier)\b', line, re.I):
            out.append(('warning', n, 'refers to earlier lines; a fresh agent sees only this line and the context note'))
    if not verify_line:
        out.append(('warning', 0, 'no verify statement: end with one that runs a concrete check and writes verify.txt in an exact format'))
    return out


# List separators are a comma (optionally followed by "and") or a whole word "and": a bare `and`
# alternative split names such as handler.js into "h" and "ler.js".
LIST_SEP = r'(?:\s*,\s*(?:and\s+)?|\s+and\s+)'
FILE_RX = re.compile(r'\b(?:the\s+)?(?:file|files?|script|module|page|stylesheet|document)s?\s+'
                     r'((?:[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,8})(?:' + LIST_SEP +
                     r'[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,8})*)')
FOLDER_RX = re.compile(r'(?:in|into|inside|under)\s+the\s+folder\s+(/[^\s,;]+)')
# A bare name may carry relative directory components (src/app.py); it never starts inside an
# absolute path or after a dot or hyphen.
BARE_FILE_RX = re.compile(r'(?<![\w/.-])((?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*[A-Za-z0-9_][A-Za-z0-9_-]*'
                          r'\.(?:js|mjs|cjs|py|html|css|json|md|txt|sh|svg))\b')
# Runtime and library names that look like files in prose ("serves it with node.js"). A name in this
# list counts as a file only when a file noun introduces it ("the file three.js").
RUNTIME_NAMES = frozenset(('node.js', 'next.js', 'vue.js', 'three.js', 'd3.js', 'react.js', 'express.js',
                           'nuxt.js', 'angular.js', 'ember.js', 'backbone.js', 'chart.js', 'p5.js', 'deno.js',
                           'bun.js', 'svelte.js', 'jquery.js', 'moment.js'))
FILE_NOUN = r'(?:files?|scripts?|modules?|pages?|stylesheets?|documents?)'
DELETE_RX = re.compile(r'^(?:delete|remove)\s+(?:the\s+)?' + FILE_NOUN + r'\b', re.I)
RENAME_RX = re.compile(r'^(?:rename|move)\s+(?:the\s+)?' + FILE_NOUN + r'\b', re.I)
DESTINATION_RX = re.compile(r'\bto\s+(?:the\s+)?(?:(?:new\s+)?(?:file|name|path)\s+)?'
                            r'([A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,8})\b')
READ_ONLY_RX = re.compile(r'^(?:read|inspect|check|verify|test|run|monitor|watch|research|index|scan|summari[sz]e|collect)\b', re.I)
CREATES_RX = re.compile(r'\b(?:creat|writ|produc|generat|record|append)\w*', re.I)


def _clean(part):
    part = part.strip().strip('.').strip()
    # a parent-directory segment never names a workspace file
    return part if part and '..' not in part.split('/') else ''


def _named(statement):
    """Files a statement names, with the primary ones (introduced by a file noun, else the first bare
    name) that a writing statement must change."""
    names, primary = [], []
    for group in FILE_RX.findall(statement):
        for part in re.split(LIST_SEP, group):
            part = _clean(part)
            if part and part not in names:
                names.append(part)
                primary.append(part)
    for part in BARE_FILE_RX.findall(statement):
        part = _clean(part)
        if not part or part in names or part.lower() in RUNTIME_NAMES:
            continue
        names.append(part)
        if not primary:
            primary.append(part)
    return names, primary


def statement_files(statement):
    """Files and the absolute folder a statement names (a pure reading of the text, no disk)."""
    folder = ''
    match = FOLDER_RX.search(statement)
    if match:
        folder = match.group(1).rstrip('/.')
    return {'files': _named(statement)[0], 'folder': folder}


def plan_checks(statement, index, policy):
    """The code checks one statement must pass. Pure: returns check specs.

    - a writing statement: each named file exists (its primary files are also marked `changed`:
      this attempt must have added or modified them), syntax by extension;
    - Delete/Remove the file X: X is absent (no exists or syntax check);
    - Rename/Move the file X to Y: only the destination Y is checked;
    - a read-only verb (read, verify, run, ...): no existence check unless it also writes;
    - then the operator's public commands for this statement index (policy['checks']).
    """
    files, primary = _named(statement)
    named = statement_files(statement)
    read_only = bool(READ_ONLY_RX.match(statement))
    creates = bool(CREATES_RX.search(statement))
    checks = []
    if DELETE_RX.match(statement):
        for name in files:
            checks.append({'kind': 'absent', 'file': name, 'public': True})
    else:
        if RENAME_RX.match(statement):
            match = DESTINATION_RX.search(statement)
            destination = _clean(match.group(1)) if match else (files[-1] if files else '')
            files = primary = [destination] if destination else []
        for name in files:
            # inflected forms count ("... and writes verify.txt"): otherwise such a verify line had no check at all
            if not read_only or creates:
                check = {'kind': 'exists', 'file': name, 'public': True}
                if not read_only and name in primary:
                    check['changed'] = True
                checks.append(check)
            if policy.get('syntax', True):
                ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in SYNTAX_CHECKS:
                    checks.append({'kind': 'syntax', 'file': name, 'argv': [a.replace('{file}', name) for a in SYNTAX_CHECKS[ext]],
                                   'public': True})
    for command in policy.get('checks', {}).get(str(index), []):
        checks.append({'kind': 'command', 'command': command, 'public': True})
    return {'checks': checks, 'files': named['files'], 'folder': named['folder'], 'read_only': read_only}


# ------------------------------------------------------------------------------ localization

def localize(text, folder):
    """Rewrite an attempt instruction for a worker that runs in its own checkout: every mention of
    the project folder becomes the working-folder phrase, and an absolute path below it becomes the
    path relative to the checkout. One substitution pass; other folders are left alone."""
    base = (folder or '').rstrip('/')
    if not base or not text:
        return text
    rx = re.compile(r'(\bthe folder\s+)?' + re.escape(base) + r'''(/[^\s,;:"'`)]+)?(?![\w-]|\.\w)''')

    def swap(match):
        sub = (match.group(2) or '').lstrip('/')
        if not sub:
            return WORKING_FOLDER
        tail = sub[len(sub.rstrip('.')):]
        return (match.group(1) or '') + sub.rstrip('.') + tail
    return rx.sub(swap, text)


def delocalize(text, folder):
    """The inverse for planner output: lines that say "the current working folder" name the project
    folder again (stored statements stay lint-clean; every launch localizes them anew)."""
    base = (folder or '').rstrip('/')
    if not base or not text:
        return text
    return re.sub(r'(?:\bthe folder\s+)?\bthe current working folder(?:\s*\((?:the git checkout|your git checkout)[^)]*\))?',
                  'the folder ' + base, text, flags=re.I)


# ------------------------------------------------------------------------------ evidence

def classify(task_row, verdict, *, handoff=None, timeout_requested=False):
    """Normalize what happened to one attempt into a failure class (or None when it passed).

    `task_row` is the child task record (the coordinator passes status 'completed' for a step
    that ended with positive evidence); `verdict` the coordinator's code checks
    ({'passed': bool, 'checks': [...], 'files_changed': int|None}); `handoff` the validated
    checkpoint, when one exists; `timeout_requested` the coordinator's own durable timeout mark.
    A task that did not complete is never a pass, whatever its workspace shows.
    """
    status = (task_row or {}).get('status')
    error = str((task_row or {}).get('error') or '')
    if status == 'unknown':
        return 'UNKNOWN'
    if status == 'cancelled':
        return 'TIMEOUT' if timeout_requested else 'CANCELLED'
    if status == 'failed':
        if re.search(r'refus|admission|budget|not installed|Pick a|eligib', error, re.I):
            return 'REFUSAL' if re.search(r'refus', error, re.I) else 'INFRASTRUCTURE'
        return 'INFRASTRUCTURE'
    if verdict and verdict.get('passed'):
        return None
    # a checkpoint with nothing left is a worker's claim of completion, not a handoff
    if handoff and handoff.get('valid') and handoff.get('left'):
        return 'CONTEXT_EXHAUSTED'
    checks = (verdict or {}).get('checks') or []

    def failed(*kinds):
        return any(c.get('kind') in kinds and not c.get('passed') for c in checks)
    if failed('fetch'):
        return 'FETCH_FAILURE'
    steps = (task_row or {}).get('steps') or []
    evidence = (steps[-1].get('evidence') or {}) if steps else {}
    if evidence.get('warning'):
        return 'CLAIM_MISMATCH'
    if failed('exists', 'absent', 'change'):
        return 'NO_OUTPUT'
    if failed('syntax'):
        return 'SYNTAX'
    if failed('command', 'designed', 'design'):
        return 'CHECK_FAILURE'
    if failed('hidden'):
        return 'HIDDEN_FAILURE'
    if verdict and verdict.get('files_changed') == 0:
        return 'NO_OUTPUT'
    return 'UNKNOWN'


def fingerprint(node, strategy, failure, overrides=None):
    """A search-state fingerprint: the same statement, depth, strategy, placement overrides and
    failure class seen before is a cycle, not progress."""
    return digest({'statement': node.get('statement'), 'depth': node.get('depth', 0),
                   'strategy': strategy, 'failure': failure, 'overrides': dict(overrides or {})})


def next_strategy(node, policy, failures, exclude=()):
    """The rotated strategy for the next regeneration, conditioned on evidence:

    - INFRASTRUCTURE/REFUSAL/TIMEOUT/FETCH_FAILURE never consume a semantic strategy: move to
      another node or engine.
    - SYNTAX/CHECK_FAILURE/CLAIM_MISMATCH/NO_OUTPUT prefer feedback (public check output).
    - HIDDEN_FAILURE never uses feedback (there is nothing public to feed back).
    - CONTEXT_EXHAUSTED is a handoff, not a regeneration (decided elsewhere).
    - 'fresh' is the fallback once every other eligible name is used up or excluded.
    Returns (name, overrides) or None when no eligible strategy remains.
    """
    rotation = list(policy['strategies'])
    last = failures[-1] if failures else None
    fallback = 'fresh' in rotation
    if last in PLACEMENT_FAILURES:
        rotation = [s for s in ('other_node', 'other_engine') if s in policy['strategies']]
        fallback = True             # a placement failure may always retry plainly
    elif last in FEEDBACK_FAILURES and 'feedback' in rotation:
        rotation = ['feedback'] + [s for s in rotation if s != 'feedback']
    elif last == 'HIDDEN_FAILURE':
        rotation = [s for s in rotation if s != 'feedback']
    engines = [e for e in policy.get('engines', []) if e != node.get('engine')]
    nodes = [n for n in policy.get('nodes', []) if n != node.get('node')]
    used = {}
    for attempt in node.get('attempts', [])[node.get('rotation_start', 0):]:
        if attempt.get('placement_absent'):
            continue                          # it never ran: the model was not on that node
        used[attempt.get('strategy')] = used.get(attempt.get('strategy'), 0) + 1
    quota = max(1, (policy['regenerate'] + len(policy['strategies']) - 1) // len(policy['strategies']))
    for name in rotation:
        if name == 'fresh' or name in exclude:
            continue
        if name == 'other_engine' and not engines:
            continue
        if name == 'other_node' and not nodes:
            continue
        if name == 'stronger_model' and not node.get('stronger_models'):
            continue
        if name == 'feedback' and used.get('feedback', 0) >= 2:
            continue
        if used.get(name, 0) >= quota:
            continue
        overrides = {}
        if name == 'other_engine':
            overrides['engine'] = engines[used.get(name, 0) % len(engines)]
        elif name == 'other_node':
            overrides['node'] = nodes[used.get(name, 0) % len(nodes)]
        elif name == 'stronger_model':
            overrides['model'] = node['stronger_models'][used.get(name, 0) % len(node['stronger_models'])]
        return name, overrides
    if fallback and 'fresh' not in exclude:
        return 'fresh', {}
    return None


def _trailing_failures(attempts):
    out = []
    for attempt in reversed(attempts):
        if attempt.get('status') == 'generation_done':
            break
        if attempt.get('status') == 'failed':
            out.append(attempt.get('failure'))
    return out[::-1]


# ------------------------------------------------------------------------------ progress and novelty

def progress_metrics(verdict, checkpoint=None, named=None, units=None):
    """What one attempt measurably achieved: named files it created or changed, checks it passed,
    and the items its checkpoint lists as done. `named` (the statement's files) bounds which changed
    paths count: touching new junk files is activity, not progress, so it cannot postpone a stall
    forever. `units` (kernel-lane attempts only) is how many units of a spec sheet the build accepted,
    each one tested by the kernel against the sheet's examples. Pure; the coordinator keeps the node's
    best values."""
    checks = (verdict or {}).get('checks') or []
    files = set()
    for check in checks:
        if check.get('kind') in ('exists', 'syntax', 'designed') and check.get('passed') and check.get('file'):
            files.add(check['file'])
    for name in (verdict or {}).get('changed') or []:
        if named is None or name in named or name.split('/')[-1] in named:
            files.add(name)
    done = len((checkpoint or {}).get('done') or []) if (checkpoint or {}).get('valid') else 0
    out = {'files': sorted(files), 'checks': sum(1 for c in checks if c.get('passed')), 'done': done}
    if units is not None:
        out['units'] = int(units)
    return out


def is_progress(best, metrics):
    """True when the metrics beat the node's best so far on a CODE-VERIFIED axis: a new named file,
    more checks passing, or (kernel lane) more spec-sheet units accepted by the kernel. The
    checkpoint's done list is worker-authored free text, so a longer list alone is never progress (it
    would keep a stalled handoff chain alive forever); it is kept in the record for the operator."""
    best = best or {}
    if set(metrics.get('files') or []) - set(best.get('files') or []):
        return True
    if metrics.get('units', 0) > best.get('units', 0):
        return True
    return metrics.get('checks', 0) > best.get('checks', 0)


def unproductive_split(node) -> bool:
    """True for a split child whose best evidence never beat its parent's: no new named file, no more passing
    checks, no more accepted spec-sheet units than the parent already had when it was split. Such a node may
    regenerate but never split again: the decomposition is not where the difficulty is (2026-10-11: a 3B
    model split cellsOf four levels deep, each child accepting the same one unit its parent had, and until_done
    would have let it reach HARD_DEPTH). A root node, or a child whose parent had no progress record, is never
    unproductive by this rule."""
    parent = node.get('parent_progress')
    if not isinstance(parent, dict) or not parent:
        return False
    return not is_progress(parent, node.get('progress') or {})


def merge_progress(best, metrics):
    """The node's best evidence after an attempt that made progress: the union of named files and
    the maximum of every counter."""
    best = dict(best or {})
    best['files'] = sorted(set(best.get('files') or []) | set(metrics.get('files') or []))
    best['checks'] = max(best.get('checks', 0), metrics.get('checks', 0))
    best['done'] = max(best.get('done', 0), metrics.get('done', 0))
    if 'units' in best or 'units' in metrics:
        best['units'] = max(best.get('units', 0), metrics.get('units', 0))
    return best


WORK_KINDS = ('candidate', 'regen', 'handoff', 'integration')
STALL_FAILURES = ('TIMEOUT', 'CONTEXT_EXHAUSTED')   # count toward a stall although they are not check failures


def _work(node):
    # placement_absent: the coordinator found the model missing on that node, so the attempt never ran
    return [a for a in node.get('attempts', []) if a.get('kind') in WORK_KINDS and a.get('status') not in ('queued', 'running')
            and not a.get('placement_absent')]


def recent_progress(node):
    """True when the LAST finished work attempt measurably advanced the node. A launch that failed
    or timed out carries no progress record, so it ends the plain-retry exemption."""
    work = _work(node)
    return bool(work and (work[-1].get('progress') or {}).get('new'))


def stale_count(node):
    """Finished work attempts since the last progress that ended in a semantic failure, a timeout
    or a context handoff without progress. Placement failures (another machine's problem) never
    count; nor does an accepted attempt."""
    count = 0
    for attempt in reversed(_work(node)):
        if (attempt.get('progress') or {}).get('new'):
            break
        failure = attempt.get('failure')
        if attempt.get('status') == 'handoff' or failure in STALL_FAILURES or (
                attempt.get('status') == 'failed' and failure not in NON_SEMANTIC):
            count += 1
    return count


def handoff_stale(node):
    """Consecutive trailing handoffs (checkpointed context exhaustion) that added nothing to the
    predecessor's progress."""
    count = 0
    for attempt in reversed(_work(node)):
        if attempt.get('status') != 'handoff':
            break
        if (attempt.get('progress') or {}).get('new'):
            break
        count += 1
    return count


_ITEM_URL = re.compile(r'^(?:https?://)?(?:www\.)?', re.I)
_DOI = re.compile(r'\b(10\.\d{4,9}/[^\s"<>]+)', re.I)


def items_key(text):
    """A dedup key for a research item: a DOI when present, else a lowercased URL without scheme,
    www, trailing slash or fragment, else the lowercased, whitespace-collapsed text."""
    text = str(text or '').strip()
    doi = _DOI.search(text)
    if doi:
        return 'doi:' + doi.group(1).rstrip('.,;)').lower()[:ITEM_KEY_MAX]
    if re.match(r'^(?:https?://|www\.)', text, re.I):
        # the URL alone identifies the item: a title appended after it ("<url> | <title>") never changes the key
        key = _ITEM_URL.sub('', text).split()[0].split('#', 1)[0].rstrip('/').lower()
        return 'url:' + key[:ITEM_KEY_MAX]
    return 'text:' + re.sub(r'\s+', ' ', text).lower()[:ITEM_KEY_MAX]


def _novel_strategy(node, policy, failures, seen, until=False):
    """The first eligible strategy whose fingerprint the node has not tried. Cycle-exempt names
    (feedback carries new evidence, fresh is the plain retry) may repeat within the bounded regenerate
    count; in until_done they may repeat only while the node is still making progress, otherwise the
    stall rule escalates to a split."""
    excluded = []
    while True:
        chosen = next_strategy(node, policy, failures, exclude=excluded)
        if chosen is None:
            return None
        name, overrides = chosen
        fp = fingerprint(node, name, failures[-1] if failures else None, overrides)
        exempt = name in CYCLE_EXEMPT and (not until or recent_progress(node))
        if fp in seen and not exempt:
            excluded.append(name)
            continue
        return name, overrides, fp


def decide(node, policy, budget, now):
    """One deterministic decision for one statement node from its durable record.

    budget = {'agents_started': int, 'agents_max': int|0 (0 = unlimited), 'deadline': float|None}
    node = {'status', 'depth', 'attempts': [{'status': queued|running|accepted|failed|handoff|
            generation_done|superseded|unknown|promoting, 'failure', 'strategy', 'kind', 'generation',
            'from', 'finished'}], 'perpetual', 'generation', 'handoffs', 'fingerprints', 'split_refused',
            'planners', 'needs_design', 'designed', 'stale', 'progress_recent', 'handoff_progress',
            'stale_generations'}
    Returns {'action': ..., 'reason': ...} plus action-specific fields. Pure.

    Bounded mode: the counts (regenerate, depth, generations, agents_max, wall) are caps.
    until_done: a node keeps going while it has something new to try or is making progress; when it
    stalls (novelty_limit attempts without progress) it is subdivided; when nothing novel remains at
    the smallest subdivision it is 'stuck' (never failed by a clock or a count).
    """
    attempts = node.get('attempts', [])
    until = bool(policy.get('until_done'))
    cap = budget.get('agents_max') or 0
    deadline = budget.get('deadline')
    exhausted = (cap and budget['agents_started'] >= cap) or (deadline is not None and now >= deadline)
    terminal = 'stuck' if until else 'fail'
    if node.get('status') in ('accepted', 'failed', 'split', 'stuck'):
        return {'action': 'stop', 'reason': f'node is {node["status"]}'}
    perpetual = bool(node.get('perpetual'))
    accepted = [] if perpetual else sorted([a for a in attempts if a.get('status') == 'accepted'],
                                           key=lambda a: a.get('kind') == 'planner')
    if accepted:
        return {'action': 'accept', 'attempt': accepted[0]['id'], 'reason': 'an attempt passed every code check'}
    running = [a for a in attempts if a.get('status') in ('queued', 'running')]
    if running:
        if deadline is not None and now >= deadline:
            return {'action': 'wait', 'timeout': [a['id'] for a in running], 'reason': 'run deadline passed; cancel running attempts'}
        stale = [a for a in running if a.get('started') and now - a['started'] > policy['attempt_seconds']]
        if stale:
            return {'action': 'wait', 'timeout': [a['id'] for a in stale], 'reason': 'attempt exceeded attempt_seconds; cancel it'}
        return {'action': 'wait', 'reason': f'{len(running)} attempt(s) still running'}
    unknown = [a['id'] for a in attempts if a.get('status') in ('unknown', 'promoting')]
    if unknown:
        return {'action': 'wait', 'reason': 'attempt(s) in an unknown state: ' + ', '.join(unknown)}
    seen = set(node.get('fingerprints') or []) | ({node['last_fingerprint']} if node.get('last_fingerprint') else set())
    if perpetual:
        generation = node.get('generation', 0)
        if not until and generation >= policy['generations']:
            return {'action': 'accept', 'attempt': None, 'reason': 'perpetual lane reached its generation cap'}
        if policy.get('saturation') and node.get('stale_generations', 0) >= policy['saturation']:
            return {'action': 'accept', 'attempt': None,
                    'reason': f'perpetual lane saturated: {node["stale_generations"]} generation(s) in a row found nothing new'}
        trailing = _trailing_failures(attempts)
        if trailing:
            if not until and len(trailing) > policy['regenerate']:
                return {'action': 'fail', 'reason': f'perpetual lane failed {len(trailing)} generation(s) in a row: '
                                                    + ', '.join(str(f) for f in trailing)}
        if exhausted:
            return {'action': terminal, 'reason': 'budget or deadline exhausted before the next perpetual generation'}
        last = attempts[-1] if attempts else None
        due = (last.get('finished') or 0) + policy['interval_seconds'] if last else 0
        if now < due:
            return {'action': 'wait', 'until': due, 'reason': 'perpetual interval not elapsed'}
        decision = {'action': 'perpetual_next', 'generation': generation + 1, 'reason': 'next bounded generation'}
        if trailing:
            chosen = _novel_strategy(node, policy, trailing, seen, until=True) if until else None
            if chosen is None and not until:
                plain = next_strategy(node, policy, trailing)
                chosen = (plain[0], plain[1], fingerprint(node, plain[0], trailing[-1], plain[1])) if plain else None
            if chosen is None:
                return {'action': terminal, 'reason': 'perpetual lane keeps failing and no untried strategy remains: '
                                                      + ', '.join(str(f) for f in trailing[-4:])}
            decision.update(strategy=chosen[0], overrides=chosen[1], fingerprint=chosen[2],
                            reason=f'next generation after {trailing[-1]}')
        return decision
    # an attempt whose node lacked the model never ran (placement_absent): it is neither work nor a planner,
    # so it consumes no regeneration, no strategy quota and no re-plan placement
    work = [a for a in attempts if a.get('kind') not in ('planner', 'designer') and not a.get('placement_absent')]
    designers = [a for a in attempts if a.get('kind') == 'designer']
    if not work:
        if exhausted:
            return {'action': terminal, 'reason': 'budget or deadline exhausted before the first attempt'}
        if policy.get('designer') and node.get('needs_design') and not designers:
            return {'action': 'design', 'reason': 'write a discriminating test before any candidate (test designer)'}
        want = policy['candidates'] if not cap else min(policy['candidates'], cap - budget['agents_started'])
        return {'action': 'launch', 'count': max(1, want), 'reason': f'first wave of {max(1, want)} candidate(s)'}
    # A handoff is pending while the latest checkpointed attempt has no successor; any candidate may hand off.
    continued = {a.get('from') for a in attempts if a.get('from')}
    pending = [a for a in attempts if a.get('status') == 'handoff' and a['id'] not in continued]
    # split_impossible: the coordinator found nothing a split could address (a spec sheet whose every
    # unit already passes its examples); such a node is regenerated or ends, never decomposed
    depth_ok = node.get('depth', 0) < (HARD_DEPTH if until else policy['depth']) and not node.get('split_impossible')
    # a split child that never beat its parent's evidence is not split again (unproductive_split): the stall
    # is in the leaves, not in the size of the statement
    unproductive = unproductive_split(node)
    depth_ok = depth_ok and not unproductive
    if pending:
        used = node.get('handoffs', node.get('generation', 0))
        stalled = until and handoff_stale(node) >= 2
        over = (not until) and used >= policy['generations']
        if exhausted:
            return {'action': terminal, 'reason': 'budget or deadline exhausted at a handoff'}
        if stalled or over:
            # successors stopped making progress (or the bounded generations are spent): the
            # statement is too big for one worker; split what is left
            if depth_ok and not node.get('split_refused') and node.get('planners', 0) == 0:
                return {'action': 'decompose', 'remaining': True, 'from': pending[-1]['id'],
                        'reason': 'handoffs stopped making progress; split the remaining work'}
            return {'action': terminal, 'reason': 'handoff generations exhausted'}
        return {'action': 'handoff', 'generation': used + 1, 'from': pending[-1]['id'],
                'reason': 'worker checkpointed near its context limit; spawn its successor'}
    failed = [a for a in work if a.get('status') == 'failed']
    failures = [a.get('failure') for a in failed]
    semantic = [f for f in failures if f not in NON_SEMANTIC]
    if exhausted:
        return {'action': terminal, 'reason': 'budget or deadline exhausted'}
    last = failures[-1] if failures else None
    if last == 'CONFLICT':
        conflicts = []
        for attempt in reversed(failed):
            if attempt.get('failure') != 'CONFLICT':
                break
            conflicts.insert(0, attempt)
        if len(conflicts) >= 2:
            return {'action': terminal, 'reason': 'promotion conflicts with the project folder persist: '
                                                  + str(conflicts[-1].get('error') or 'apply conflicts')[:300]}
        source = conflicts[-1]
        overrides = {k: source[k] for k in ('engine', 'node') if source.get(k)}
        return {'action': 'regenerate', 'strategy': 'conflict_retry', 'overrides': overrides,
                'fingerprint': fingerprint(node, 'conflict_retry', last, overrides),
                'reason': 'promotion conflict; retry once on the same engine and node from the new base'}
    planners = [a for a in attempts if a.get('kind') == 'planner' and not a.get('placement_absent')]
    stalled = stale_count(node) >= policy.get('novelty_limit', 2)
    # until_done: an oversized statement is split as soon as it stalls (no progress for
    # novelty_limit attempts), before the strategy rotation is burnt on it
    if until and stalled and semantic and depth_ok and not planners:
        return {'action': 'decompose', 'reason': f'no progress in {stale_count(node)} attempts; split the statement'}
    waves_used = len([a for a in work if a.get('kind') != 'handoff'])
    if until or waves_used < policy['candidates'] + policy['regenerate']:
        chosen = _novel_strategy(node, policy, failures, seen, until=until)
        if chosen is not None:
            name, overrides, fp = chosen
            return {'action': 'regenerate', 'strategy': name, 'overrides': overrides, 'fingerprint': fp,
                    'reason': f'regeneration after {last or "no evidence"}'}
    # decomposition: one planner in bounded mode; in until_done a failed planner is re-planned on
    # another placement while one exists (replan), then the node is stuck
    if depth_ok and semantic:
        if not planners and not node.get('split_refused'):
            if until or len(semantic) >= 2 or semantic[-1] in ('CHECK_FAILURE', 'CLAIM_MISMATCH', 'NO_OUTPUT', 'HIDDEN_FAILURE'):
                return {'action': 'decompose', 'reason': 'regeneration exhausted on a semantic failure; split the statement'}
        elif until and planners:
            tried = {(a.get('engine'), a.get('node')) for a in planners}
            options = [(e, n) for e in ([node.get('engine')] + list(policy.get('engines') or []))
                       for n in ([node.get('node')] + list(policy.get('nodes') or [])) if e and n and (e, n) not in tried]
            if options:
                engine, target = options[0]
                return {'action': 'decompose', 'replan': True, 'overrides': {'engine': engine, 'node': target},
                        'reason': f'the split was refused; re-plan with {engine}@{target}'}
    reason = 'no eligible strategy remains: ' + ', '.join(str(f) for f in failures or ['no attempt evidence'])
    if node.get('split_refused'):
        reason += '; the split was refused'
    if unproductive:
        parent = node.get('parent_progress') or {}
        mine = node.get('progress') or {}
        reason += (f'; this split made no progress over its parent (units {mine.get("units", 0)} vs '
                   f'{parent.get("units", 0)}, checks {mine.get("checks", 0)} vs {parent.get("checks", 0)}), '
                   'so it is not split again')
    if until:
        reason += '; every novel action at this subdivision was tried (resume after changing the statement, the checks or the catalogue)'
    return {'action': terminal, 'reason': reason}


# ------------------------------------------------------------------------------ prompts

def worker_suffix(policy, statement_index, folder='', can_split=True):
    """Appended to every autogen worker's instruction: the handoff protocol and the rule that
    only files decide. Kept short: a fresh small agent copies long preambles. It names the
    working folder, never the project folder (`folder` is kept for callers and ignored).
    `can_split` is False where a split could never be accepted (the maximum depth, a perpetual
    lane), so the worker is not offered an answer the coordinator would refuse."""
    lines = [
        'Autogen rules: finish this one statement, then stop. Only files on disk count; '
        'do not describe work you did not write to disk.',
    ]
    if policy['generations'] > 1 or policy['perpetual']:
        lines.append(
            f'If you get near the end of your context window before finishing, write {HANDOFF_FILE} in '
            f'{WORKING_FOLDER} with three headings: Done, Left, Files (one line per file you touched, as a '
            f'path relative to that folder), and {CHECKPOINT_FILE} with the JSON object '
            '{"version": 1, "done": [..], "left": [..], "files": [..]}; then stop. A successor with a fresh '
            'context continues in the same folder from those two files.')
    if policy.get('self_split', True) and can_split and not policy['perpetual']:
        lines.append(
            f'If the statement is too big for one context, write {SPLIT_FILE} in {WORKING_FOLDER} instead of partial '
            f'work: 2 to {policy["children"]} smaller statements, one per line, each starting with a verb, naming its '
            'file relative to the working folder plus "in the current working folder", dropping nothing; then stop.')
    return '\n'.join(lines)


def feedback_note(statement, verdict, policy):
    """The public check output a regeneration may see: existence, syntax, the operator's public
    commands and the change/claim cross-checks, truncated. Hidden checks, fetch errors, planner
    splits and other candidates' code never appear."""
    parts = []
    for check in (verdict or {}).get('checks', []):
        if not check.get('public') or check.get('passed') or check.get('kind') not in FEEDBACK_KINDS:
            continue
        what = check.get('file') or check.get('command') or check.get('kind')
        out = str(check.get('output') or check.get('error') or 'failed')[:800]
        parts.append(f'- {check.get("kind")} {what}: {out}')
    if not parts:
        return ''
    text = ('A previous attempt at this exact statement failed these code checks; fix the cause in your own '
            'fresh implementation, do not patch around the check:\n' + '\n'.join(parts))
    return text[:policy['feedback_chars']]


def split_prompt(statement, folder, policy, depth):
    """The planner's instruction. It names the working folder only (`folder` is kept for callers
    and ignored); the coordinator maps "the current working folder" in the lines back to the
    project folder before parse_split."""
    n = policy['children']
    return (f'Split one statement into smaller statements. Write exactly one file, {SPLIT_FILE}, in '
            f'{WORKING_FOLDER}, containing between 2 and {n} lines, one statement per line, nothing else. Rules '
            'for every line: start with an action verb; name the exact file (a path relative to the working '
            'folder) and say "in the current working folder"; one file or one concern per line; repeat every '
            'count, name and interface the statement fixes; never refer to another line ("the previous file"); '
            'edits say "keeping every existing part". Together the lines must produce everything the original '
            'statement produces (every file it names, every behavior it fixes); drop nothing, add no new files. '
            f'Do not implement anything; only write {SPLIT_FILE}. The original statement (depth {depth}):\n'
            + statement)


def split_remaining_prompt(statement, checkpoint, folder, policy, depth):
    """The planner's instruction after handoffs stalled: split only what is LEFT. The checkpoint's
    done list is authority for what exists on disk; the lines must cover every item left."""
    n = policy['children']
    done = '; '.join(str(x) for x in (checkpoint or {}).get('done') or [])[:1500] or 'nothing recorded'
    left = '; '.join(str(x) for x in (checkpoint or {}).get('left') or [])[:1500] or 'everything not listed as done'
    return (f'Split the REMAINING work of one statement into smaller statements. Earlier workers already completed: {done}. '
            f'Still left: {left}. Write exactly one file, {SPLIT_FILE}, in {WORKING_FOLDER}, containing between 2 and {n} '
            'lines, one statement per line, nothing else, covering only what is left (every file the original statement '
            'names that is not finished, every behavior still missing). Rules for every line: start with an action verb; '
            'name the exact file (a path relative to the working folder) and say "in the current working folder"; one '
            'file or one concern per line; repeat every count, name and interface the statement fixes; edits of files '
            'that already exist say "keeping every existing part"; never refer to another line. Do not implement '
            f'anything; only write {SPLIT_FILE}. The original statement (depth {depth}):\n' + statement)


def designer_prompt(statement, folder, policy):
    """The test designer (the idea of CodeT and AgentCoder; see README.md for the papers): an
    independent attempt writes an executable check for the statement BEFORE any implementation
    exists. Code validates that it discriminates (it must fail on an empty folder) before it counts,
    and the designer never sees other candidates."""
    return (f'Write exactly one file, {DESIGN_FILE}, in {WORKING_FOLDER}: a bash script (first line #!/usr/bin/env bash, '
            'then set -e) that checks whether the statement below has been carried out in the current working folder, '
            'exiting 0 only when every named file exists and behaves as the statement fixes (run the real program or '
            'checks with node or python3; compare exact values; print one line per check in the format name: pass or '
            f'name: followed by the exact error) and exiting 1 otherwise. The script must be under {DESIGN_MAX_CHARS} '
            'characters, must not install anything, reach the network or write outside the working folder, and must '
            f'fail when the files do not exist yet. Do not implement the statement; only write {DESIGN_FILE}. '
            'The statement:\n' + statement)


def design_probe_ok(rc, output=''):
    """The empty-folder probe counts as discriminating only for a genuine failing exit (1..123):
    124 is the runner's timeout, 125 the sandbox launcher's refusal, 126/127 a missing or
    unrunnable interpreter, and a launcher message in the output means the script never ran."""
    return 1 <= int(rc) <= 123 and not LAUNCHER_MESSAGE.search(str(output or ''))


def design_valid(text):
    """The designer's script is admissible only when it is bounded bash with a shebang and set -e,
    no network/install/escape commands; discrimination is checked by running it (coordinator)."""
    if not isinstance(text, str) or not text.strip():
        return False, 'the designer wrote no script'
    if len(text) > DESIGN_MAX_CHARS:
        return False, f'the script exceeds {DESIGN_MAX_CHARS} characters'
    head = text.lstrip().splitlines()[0] if text.strip() else ''
    if not head.startswith('#!') or 'bash' not in head:
        return False, 'the script must start with a bash shebang'
    if UNSAFE_COMMAND.search(text) or re.search(r'\bcd\s+/|\.\./', text):
        return False, 'the script uses a refused command (network, install, escape or system control)'
    return True, ''


def parse_split(text, parent_statement, folder, policy, present=()):
    """Validate a planner's split: 2..children lines, lint-clean, every file the parent names
    is named by some child (except `present`: files an earlier worker already produced, promoted
    before the children run), the folder is named. Returns (lines, errors)."""
    lines = statements(text)
    errors = []
    if not 2 <= len(lines) <= policy['children']:
        errors.append(f'the split has {len(lines)} lines; it needs 2 to {policy["children"]}')
    findings = lint(lines, folder) if lines else []
    errors += [f'line {n}: {m}' for lv, n, m in findings if lv == 'error']
    parent_files = set(statement_files(parent_statement)['files'])
    child_files = set()
    for line in lines:
        child_files |= set(statement_files(line)['files'])
    missing = sorted(parent_files - child_files - set(present or ()))
    if missing:
        errors.append('the split drops files the statement names: ' + ', '.join(missing))
    # the workspace folder itself, not any folder: "in the folder /tmp/elsewhere" used to pass
    if folder and any(folder not in line or statement_files(line)['folder'] not in ('', folder.rstrip('/'))
                      for line in lines):
        errors.append('every split line must name the absolute folder')
    if any(line.strip().rstrip('.').lower() == parent_statement.strip().rstrip('.').lower() for line in lines):
        errors.append('a split line repeats the statement it should replace')
    return (lines if not errors else []), errors


def handoff_prompt(statement, checkpoint, generation):
    """The instruction of a successor worker: the predecessor's validated checkpoint (done, left,
    files), then the statement. The successor works in the predecessor's own checkout."""
    done = checkpoint.get('done') or []
    left = checkpoint.get('left') or []
    files = checkpoint.get('files') or []
    return ('You are generation ' + str(generation) + ' of a worker that ran out of context on this statement. '
            'Its validated checkpoint says.\nDone: ' + ('; '.join(str(x) for x in done)[:1500] or 'nothing recorded') +
            '\nLeft: ' + ('; '.join(str(x) for x in left)[:1500] or 'everything not listed as done') +
            '\nFiles it touched: ' + (', '.join(str(x) for x in files)[:800] or 'none recorded') +
            '\nContinue from the files on disk (read them first; do not redo listed work), finish what is left, '
            'then stop.\n\nThe statement:\n' + statement)


def checkpoint_valid(raw, workspace_files):
    """A checkpoint is authoritative only when it parses, has the three lists, and every file it
    claims to have touched exists in the workspace, matched by exact relative path (a basename
    match let `deep/dir/a.py` pass when any a.py existed). A checkpoint with nothing left is
    valid (a perpetual cursor may be empty) but is no handoff: classify() requires work left."""
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except ValueError:
        return {'valid': False, 'reason': 'checkpoint is not JSON'}
    if not isinstance(value, dict) or value.get('version') != 1:
        return {'valid': False, 'reason': 'checkpoint lacks version 1'}
    for key in ('done', 'left', 'files'):
        if not isinstance(value.get(key), list) or any(not isinstance(x, str) for x in value[key]):
            return {'valid': False, 'reason': f'checkpoint {key} must be a list of strings'}
    present = set(workspace_files or [])
    missing = [f for f in value['files'] if f not in present]
    if missing:
        return {'valid': False, 'reason': 'checkpoint names files absent from the workspace: ' + ', '.join(missing[:8])}
    if not value['left'] and not value['done']:
        return {'valid': False, 'reason': 'checkpoint records nothing done and nothing left'}
    out = {'valid': True, 'done': value['done'][:64], 'left': value['left'][:64], 'files': value['files'][:128]}
    if 'items' in value:
        items = value.get('items')
        if not isinstance(items, list):
            return {'valid': False, 'reason': 'checkpoint items must be a list'}
        texts = [item_text(x) for x in items]
        if any(t is None for t in texts):
            return {'valid': False, 'reason': 'checkpoint items must be strings or objects with doi, url or title'}
        out['items'] = [t for t in texts if t][:200]
    return out


ITEM_FIELDS = ('doi', 'url', 'link', 'href', 'title', 'name', 'text', 'source', 'id')


def item_text(item):
    """One research item as text: a string as given; an object (models naturally write
    {"title", "doi", "year"}) reduced to its most identifying field first (DOI, then URL, then
    title) so items_key finds the DOI or URL. None when the item is neither."""
    if isinstance(item, str):
        return item[:400]
    if isinstance(item, dict):
        parts = []
        for key in ITEM_FIELDS:
            value = item.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                parts.append(str(value).strip())
        return ' | '.join(parts)[:400] if parts else None
    return None


def perpetual_prompt(statement, checkpoint, generation, interval_seconds, index=None):
    """`index` = {'total': n, 'recent': [keys]} from the coordinator's dedup index (AUTOGEN-INDEX.jsonl):
    the generation lists only NEW items under "items"; code drops duplicates by key."""
    cursor = (checkpoint or {}).get('left') or []
    done = (checkpoint or {}).get('done') or []
    known = ''
    if index:
        recent = ', '.join(str(k)[:80] for k in (index.get('recent') or [])[:30])
        known = (f' The run already holds {index.get("total", 0)} indexed item(s) (sources, findings) in {INDEX_FILE}; '
                 f'list only NEW ones under "items" (URLs, DOIs or exact titles; duplicates are dropped by code).'
                 + (f' Most recent keys: {recent}.' if recent else ''))
    return (f'Perpetual generation {generation}: do one bounded batch of this standing statement, then write '
            f'{CHECKPOINT_FILE} ({{"version": 1, "done": [...], "left": [...], "files": [...], "items": [...]}}: done = what this '
            f'and earlier generations completed, left = the cursor for the next generation, items = new sources or '
            f'findings this generation added) and {HANDOFF_FILE}, then stop. '
            f'Never repeat work listed as done. Earlier done: {"; ".join(done)[:1500] or "none"}. '
            f'Cursor: {"; ".join(cursor)[:1500] or "start"}.' + known + '\n\nThe standing statement:\n' + statement)


def summary(run):
    """A compact view for command lines and pages: counts per node and the next thing the operator
    should do."""
    nodes = run.get('nodes', [])
    out = {'id': run.get('id'), 'status': run.get('status'), 'error': run.get('error') or '',
           'agents_started': run.get('budget', {}).get('agents_started', 0),
           'agents_max': run.get('budget', {}).get('agents_max', 0), 'nodes': []}
    for node in nodes:
        attempts = node.get('attempts', [])
        out['nodes'].append({'id': node['id'], 'depth': node.get('depth', 0), 'status': node['status'],
                             'statement': node['statement'][:100], 'attempts': len(attempts),
                             'accepted': sum(1 for a in attempts if a.get('status') == 'accepted'),
                             'failed': [a.get('failure') for a in attempts if a.get('status') == 'failed'],
                             'generation': node.get('generation', 0), 'children': node.get('children', []),
                             'winner': node.get('winner') or '', 'stale': stale_count(node),
                             'progress': node.get('progress') or {}, 'items_total': node.get('items_total', 0)})
    out['until_done'] = bool((run.get('policy') or {}).get('until_done'))
    return out

"""Autogen's kernel lane: an attempt of a `local` run is a spec-sheet build, not an agent task.

Why it exists
    Small local models (0.5B to 4B parameters, served by Ollama) cannot drive a CLI coding agent:
    the tool schemas of the agent harness that was tried alone exceeded its 7168-token input
    budget, and a 1B model answered by echoing a schema back. What works for such models is the
    kernel lane: a spec sheet (docs/reference/SPEC-SHEETS.md) is compiled by symblic.spec.sheets
    into one fresh-context `Code js` ask per unit, every answer is checked by the sandboxed
    JavaScript checker (symblic.js) against the sheet's examples, and the file is assembled from
    passing units only.

What this module provides (the coordinator calls these through `self.kernel`; tests inject a fake)
    is_sheet, sheet_problems, plan, plan_checks
        what a sheet statement is and how its output file is checked: the Assemble file exists,
        was changed by the attempt, has valid syntax and passes the operator's commands.
    applicator
        `ollama:<model>@<node>` for the attempt's model and node: never a hosted model, never the
        coordinating machine.
    compile
        symblic.spec.sheets.compile_sheet, incremental with `keep_folder` (the units an earlier
        build accepted become fixed text: tested again, never asked again), plus a per-attempt
        seed so a regeneration samples new answers instead of repeating seeded replies.
    run / status / alive / stop
        `tools/symblic run PROGRAM --dir RUN_DIR --ollama-limits JSON --json` as a detached process
        group (inside a systemd user scope when one is available). The process writes its own pid
        file before it execs, so a re-dispatch after a crash adopts it and one run folder never
        holds two builds. `status` reads the run folder's state.json and trace.jsonl; it never waits.
    split_program / split_sheet / examples_executable
        decomposition. A small kernel program asks the model for a TYPED answer (planner_type: 2 or
        3 objects {name, args, contract, examples}; its JSON schema becomes Ollama's `format`, so
        the decoder cannot leave that shape) and checks in the kernel that names are new
        identifiers and that examples call their own unit. Code then validates the rest and writes
        ONE refined sheet: the sub-units, then the stalled unit rewritten to call them with its own
        examples kept as the integration check, every other byte unchanged.
    model_nodes / absent_node
        which nodes hold the model (when an inventory can be read) and which node a kernel error
        says lacks it, so builds and re-plans go only where the model is.
    checkout / promote
        the attempt's own git checkout (symblic/autogen/git_checkouts.py; adopted again by its
        deterministic name after a crash) and promotion: a commit in that checkout, then a
        per-file 3-way apply into the project's working tree.

What runs without the original host
    Everything above except the model calls themselves. A build reaches its model through the
    kernel's `ollama:` applicator (symblic/providers). In this repository that applicator was
    wired to the original host's admission-checked launcher, so on another machine a build ends
    with an INFRASTRUCTURE failure (recorded with its log) until a provider route to your Ollama
    nodes exists.

Pure helpers have no I/O. Nothing here imports the kernel at module import.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time

from symblic.autogen import git_checkouts as GIT
from symblic.autogen import policy as POLICY
from symblic.spec import sheets as SP

REPO = Path(__file__).resolve().parents[2]            # the repository root (symblic/autogen/ is two below)
BIN_SYMBLIC = REPO / 'tools' / 'symblic'              # the Symblic command line
SHEET_MAX = 200_000                       # characters of one sheet statement (the Tetris sheet is 47 KB)
SEARCH = {'samples': 2, 'retries': 2, 'rounds': 1}        # per unit and attempt; autogen's regeneration is the outer loop
SPLIT_SEARCH = {'samples': 2, 'retries': 2, 'rounds': 1}
LIMITS = {'num_predict': 4096, 'timeout_seconds': 900}    # per local model call
SPLIT_LABEL = 'split'
PLACEHOLDER = 'smallName'                 # the answer format's example unit: an echo of it is refused
SPLIT_UNITS = (2, 3)
SPLIT_EXAMPLES = (2, 6)                   # examples per sub-unit in a typed split answer
FINAL = ('done', 'failed', 'stopped')     # run statuses the kernel writes with its final report
STOP_GRACE = 20                           # seconds between SIGTERM (admitted calls are released) and SIGKILL
SCOPE_SLICE = os.environ.get('SYMBLIC_SCOPE_SLICE') or 'symblic.slice'   # systemd user slice for builds
SCOPE_ENV = 'SYMBLIC_SCOPE'                # '0' turns the systemd scope off
SCOPE_PROPERTIES = ('MemoryMax=1G', 'CPUQuota=50%', 'TasksMax=128')
LOG_TAIL = 600
MODEL_RX = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$')
CLOUD_RX = re.compile(r'[-:]cloud$', re.I)                # Ollama's hosted models (gpt-oss:120b-cloud, glm-4.6:cloud)
NODE_RX = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
APP_RX = re.compile(r'^ollama:([^@+*\s]+)@([a-z0-9-]+)$')
FILE_RX = re.compile(r'^(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*[A-Za-z0-9_][A-Za-z0-9_.-]*\.[A-Za-z0-9]{1,8}$')
_UNIT_HEAD = re.compile(r'^#{1,4}\s*Unit\s*`([^`]+)`')      # a planner's heading, before normalization
_SHEET_TITLE = re.compile(r'^# \S', re.M)
_SHEET_UNIT = re.compile(r'^## Unit `[^`]+`[ \t]*$', re.M)
_SHEET_ASSEMBLE = re.compile(r'^## Assemble `[^`]+`[ \t]*$', re.M)


class KernelError(ValueError):
    """A refusal the coordinator records on the attempt as it is."""


# ------------------------------------------------------------------------------ sheets (pure)

def is_sheet(text) -> bool:
    """A spec sheet: a `# FILE` title, at least one `## Unit `name(...)`` and an `## Assemble `FILE``
    section (`## Shared` is optional, as for symblic.spec.sheets). Ordinary statements never match."""
    return isinstance(text, str) and all(rx.search(text) for rx in (_SHEET_TITLE, _SHEET_UNIT, _SHEET_ASSEMBLE))


def safe_file(name) -> bool:
    """A relative path with an extension that stays inside the checkout."""
    return (isinstance(name, str) and len(name) <= 200 and bool(FILE_RX.fullmatch(name))
            and '..' not in name.split('/'))


def sheet_problems(text) -> list[str]:
    """What keeps a sheet from being an autogen statement (empty when it is one): the problems
    symblic.spec.sheets finds, plus a bounded size and an output file that can be written into a
    checkout."""
    if not isinstance(text, str) or not text.strip():
        return ['the sheet is empty']
    if len(text) > SHEET_MAX:
        return [f'the sheet is longer than {SHEET_MAX} characters']
    if not is_sheet(text):
        return ['not a spec sheet: it needs a "# FILE" title, "## Unit `name(...)`" sections with Examples and an '
                '"## Assemble `FILE`" section (docs/reference/SPEC-SHEETS.md)']
    try:
        sheet = SP.parse(text)
    except SP.SheetError as exc:
        return [str(exc)]
    found = SP.problems(sheet)
    file = _file_of(sheet)
    if not safe_file(file):
        found.append(f'the Assemble file {file!r} must be a relative path with an extension inside the workspace')
    return found


def _file_of(sheet) -> str:
    return ((sheet.get('template') or {}).get('file') or sheet.get('title') or '').strip()


def plan(text) -> dict:
    """The file a sheet builds (its Assemble section, which labels the kernel's output; the title when
    there is none), its units in order (first names, kernel variables, headings) and example counts."""
    sheet = SP.parse(text)
    units = sheet['units']
    return {'title': sheet['title'], 'file': _file_of(sheet), 'units': [u['names'][0] for u in units],
            'vars': [SP._var(u['names'][0]) for u in units], 'headings': [u['heading'] for u in units],
            'names': [n for u in units for n in u['names']], 'examples': [len(u['examples']) for u in units],
            'normalize': bool(sheet.get('normalize'))}


def plan_checks(file, index, policy) -> dict:
    """policy.plan_checks for a sheet: the statement writes exactly one file, the Assemble file
    (exists and changed by the attempt, syntax by extension), then the operator's public commands for
    this statement index. The sheet's prose never becomes file checks."""
    checks = [{'kind': 'exists', 'file': file, 'public': True, 'changed': True}]
    ext = '.' + file.rsplit('.', 1)[-1].lower() if '.' in file else ''
    if policy.get('syntax', True) and ext in POLICY.SYNTAX_CHECKS:
        checks.append({'kind': 'syntax', 'file': file, 'public': True,
                       'argv': [a.replace('{file}', file) for a in POLICY.SYNTAX_CHECKS[ext]]})
    for command in policy.get('checks', {}).get(str(index), []):
        checks.append({'kind': 'command', 'command': command, 'public': True})
    return {'checks': checks, 'files': [file], 'folder': '', 'read_only': False}


def stalled_unit(text, accepted) -> dict | None:
    """The first unit (sheet order) whose kernel variable is not among `accepted`: where a build stopped.
    None when every unit was accepted."""
    spec = plan(text)
    done = set(accepted or ())
    for name, var, heading in zip(spec['units'], spec['vars'], spec['headings']):
        if var not in done:
            return {'name': name, 'var': var, 'heading': heading}
    return None


# ------------------------------------------------------------------------------ applicators and programs

def applicator(model, node, host='') -> str:
    """`ollama:<model>@<node>`: an installed Ollama model pinned to one node. Refused: a hosted
    (cloud) Ollama model, an engine prefix such as `claude:`, a malformed node name, and `host`, the
    machine that runs the coordinator ('' disables that rule)."""
    model, node = str(model or '').strip(), str(node or '').strip()
    if not MODEL_RX.fullmatch(model) or CLOUD_RX.search(model):
        raise KernelError(f'{model!r} is not a local Ollama model name (local attempts never use a hosted model)')
    if not NODE_RX.fullmatch(node):
        raise KernelError(f'{node!r} is not a node name (lowercase letters, digits and hyphens)')
    if host and node == host:
        raise KernelError(f'{node!r} is the coordinating machine: a local model runs on another node, '
                          f'{host} only coordinates')
    return f'ollama:{model}@{node}'


def check_applicators(applicators, host='') -> list[str]:
    """The applicators of a kernel build, each a valid `ollama:MODEL@NODE` (see applicator)."""
    apps = list(applicators or [])
    if not apps:
        raise KernelError('a kernel build needs one local applicator')
    for app in apps:
        m = APP_RX.fullmatch(str(app))
        if not m or applicator(m.group(1), m.group(2), host) != app:
            raise KernelError(f'{app!r} is not a local applicator (ollama:MODEL@NODE)')
    return apps


def seed(run_id, attempt_id) -> int:
    """A deterministic seed per attempt: two attempts never send the same seeded request."""
    return int(hashlib.sha256(f'{run_id}:{attempt_id}'.encode()).hexdigest()[:8], 16) % 1_000_000_000


def _with_seed(program, value) -> str:
    """Insert `seed=N` into the compiled program's `use` line (symblic.spec.sheets is left
    untouched: its source is part of other builds' recorded runtime identity)."""
    lines = program.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('use by=') and line.endswith(', context=none.'):
            lines[i] = line[:-len(', context=none.')] + f', seed={int(value)}, context=none.'
            return '\n'.join(lines)
    raise KernelError('the compiled program has no use line to seed (did symblic.spec.sheets change?)')


def _uses_only(program, applicators) -> bool:
    """Every `use by=` line of the program names exactly these applicators."""
    rows = [line for line in program.split('\n') if line.startswith('use by=')]
    want = 'use by=' + json.dumps(list(applicators))
    return bool(rows) and all(line.startswith(want + ',') for line in rows)


def compile(text, applicators, *, keep_folder=None, redo=(), samples=SEARCH['samples'], retries=SEARCH['retries'],
            rounds=SEARCH['rounds'], seed=None) -> str:   # noqa: A001 - the kernel's own verb
    """The build program for one attempt. `keep_folder` is an earlier build of the same sheet: the
    leading units it accepted become fixed text (symblic.spec.sheets keep), tested again, never
    asked again."""
    check_applicators(applicators)
    keep, keep_from = None, ''
    if keep_folder and os.path.isdir(keep_folder):
        keep = SP.accepted_units(keep_folder) or None
        keep_from = 'run ' + os.path.basename(str(keep_folder).rstrip('/')) if keep else ''
    program = SP.compile_sheet(text, list(applicators), samples=samples, retries=retries, rounds=rounds,
                               keep=keep, keep_from=keep_from, redo=tuple(redo or ()))
    return _with_seed(program, seed) if seed is not None else program


def _unit(sheet, unit):
    for index, u in enumerate(sheet['units']):
        if unit in u['names'] or u['heading'] == unit:
            return index, u
    raise KernelError(f'the unit {unit!r} is not in the sheet')


def planner_type(high=SPLIT_UNITS[1]) -> str:
    """The planner's answer type: a constrained list of unit objects. The kernel turns it into the JSON schema
    the local route sends as Ollama's `format`, so a small model's decoding cannot leave the shape. `expect` is
    Text (the value as JSON): `Any` would compile to the empty schema, which older llama.cpp grammar converters
    read as "any object"; code reads the text as JSON (`expect_json`)."""
    high = max(SPLIT_UNITS[0], min(SPLIT_UNITS[1], int(high)))
    return ('List of Record {name: Text, args: Text, contract: Text, examples: List of Record {call: Text, '
            f'expect: Text}} length {SPLIT_EXAMPLES[0]}..{SPLIT_EXAMPLES[1]}}} length {SPLIT_UNITS[0]}..{high}')


def split_prompt(text, unit, error='', children=SPLIT_UNITS[1]) -> str:
    """The planner's question: the shared section, the stalled unit's contract, examples and test
    setup, the stopped build's error, and the answer format (2 to `children` new smaller units)."""
    sheet = SP.parse(text)
    _, target = _unit(sheet, unit)
    shared = (sheet['intro'] + '\n\n' + sheet['shared']).strip()
    examples = ''.join(f'    {call} ==> {expect}\n' for call, expect in target['examples'])
    taken = ', '.join(n for u in sheet['units'] for n in u['names'])
    parts = [f'A small model could not write one unit of the JavaScript file {sheet["title"]}. Split that unit into '
             f'2 to {children} smaller units that are each easy, so that the unit can then be written by calling them.',
             '', 'What every unit of the file shares:', shared[:2500] or '(nothing)', '',
             f'THE UNIT: `{target["heading"]}`', target['body'], '',
             'Its examples (they stay; once the smaller units exist it must still give exactly these values):',
             examples.rstrip('\n')]
    if target['setup']:
        parts += ['', 'The tests define these helpers first:', '\n'.join('    ' + l for l in target['setup'].split('\n'))]
    if error:
        parts += ['', 'What went wrong when it was tried: ' + ' '.join(str(error).split())[:600]]
    parts += ['', f'Answer with 2 to {children} NEW smaller units. For each one give:',
              f'- name: a new JavaScript function name (letters, digits, _), not one of {taken};',
              '- args: its parameter names, for example "type, rot";',
              '- contract: one or two sentences saying exactly what it returns;',
              f'- examples: {SPLIT_EXAMPLES[0]} to {SPLIT_EXAMPLES[1]} examples, each a call of THIS unit by its name '
              '(for example "half(4)") and expect, the exact value that call returns written as JSON (for example '
              '2, [[0,1],[1,0]] or "ready").',
              'Do not repeat the examples above and do not write code: describe the smaller units.']
    return '\n'.join(parts)


SPLIT_CHECK = ('(all u in split_unit: matches(u.name, "^[A-Za-z_][A-Za-z0-9_]*$") and not contains(taken, u.name) '
               'and (all e in u.examples: contains(e.call, u.name + "("))) '
               'and (all a in split_unit: all b in split_unit: a = b or a.name != b.name)')


def split_program(text, unit, applicators, *, seed=None, error='', children=SPLIT_UNITS[1]) -> str:
    """The planner as a typed kernel ask (`planner_type`): the schema constrains the answer's shape, and the
    anchored ensure checks in the kernel, before any code sees it, that every name is a new identifier and
    every example calls its own unit (on 2026-10-11 a 3B model's free-text split restated the stalled
    unit and its examples instead). A failing answer is retried with that `because`; code then
    validates the rest (`split_sheet`)."""
    check_applicators(applicators)
    high = max(SPLIT_UNITS[0], min(SPLIT_UNITS[1], int(children)))
    sheet = SP.parse(text)
    taken = [n for u in sheet['units'] for n in u['names']] + [PLACEHOLDER]
    search = SPLIT_SEARCH
    use = ('use by=' + json.dumps(list(applicators)) + f', route=search, samples={search["samples"]}, '
           f'retries={search["retries"]}, rounds={search["rounds"]}'
           + (f', seed={int(seed)}' if seed is not None else '') + ', context=none.')
    because = ('Every unit needs a NEW name that is a JavaScript identifier (not a name already in the file), and every '
               'example must call its own unit by that name, for example "half(4)". Do not restate the unit above.')
    lines = [f'program Split {re.sub(r"[^A-Za-z0-9_]", "_", str(unit))[:60]}.',
             'note Autogen kernel planner: a typed split of one stalled unit of a spec sheet; code validates the answer.',
             use,
             f'ask split_unit: {planner_type(high)} {SP.literal(split_prompt(text, unit, error, high))}.',
             'let taken = ' + json.dumps(taken) + '.',
             f'ensure {SPLIT_CHECK} else retry because {SP.literal(because)}.',
             f'show split_unit as {json.dumps(SPLIT_LABEL)}.']
    return '\n'.join(lines) + '\n'


# ------------------------------------------------------------------------------ split validation

def _reply_sections(reply) -> list[str]:
    """The `## Unit` sections of a planner's reply, normalized by code: fences and prose around them
    dropped, `Examples` labels and example lines (bulleted, unindented or in backticks) put in the
    sheet's form. Content is never invented."""
    raw = str(reply or '').replace('\r\n', '\n').split('\n')
    inside, fenced, lines = False, [], []
    for line in raw:
        if line.strip().startswith('```'):
            inside = not inside
            continue
        lines.append(line.rstrip())
        if inside:
            fenced.append(line.rstrip())
    if any(_UNIT_HEAD.match(l.strip()) for l in fenced):
        lines = fenced                    # the units were fenced: the prose around them is not part of them
    sections, current, mode = [], None, ''
    for line in lines:
        stripped = line.strip()
        head = _UNIT_HEAD.match(stripped)
        if head:
            current = [f'## Unit `{head.group(1).strip()}`']
            sections.append(current)
            mode = 'body'
            continue
        if current is None:
            continue
        if stripped.startswith('#'):
            current, mode = None, ''
            continue
        label = re.sub(r'[*_]', '', stripped).rstrip(':').strip().lower()
        if label in ('examples', 'example'):
            current.append('Examples:')
            mode = 'examples'
            continue
        if label == 'test setup':
            current.append('Test setup:')
            mode = 'setup'
            continue
        if '==>' in stripped and mode in ('body', 'examples'):
            if mode == 'body':                # example lines without their label
                current.append('Examples:')
                mode = 'examples'
            item = re.sub(r'^(?:[-*]\s+|\d+[.)]\s+)', '', stripped).strip()
            if item.startswith('`') and item.endswith('`'):
                item = item[1:-1].strip()
            current.append('    ' + item)
            continue
        if mode == 'examples' and not stripped:
            continue
        if mode == 'examples':            # a unit ends with its examples: what follows is chatter
            current, mode = None, ''
            continue
        current.append(line)
    return ['\n'.join(s).strip() for s in sections]


def _typed_sections(answer, uses=()) -> tuple[list[str], list[str]]:
    """The typed planner answer (a list of {name, args, contract, examples: [{call, expect}]}) as `## Unit`
    sections in the sheet's own form. Each sub-unit inherits the stalled unit's `Uses:` (the earlier units it was
    allowed to call); `expect` is written as the JSON value given. Only the form is made here: whether the units
    make sense is split_sheet's validation."""
    if not isinstance(answer, (list, tuple)):
        return [], ['the answer is not a list of units']
    sections, errors = [], []
    for i, item in enumerate(answer, 1):
        if not isinstance(item, dict):
            errors.append(f'unit {i} is not an object with name, args, contract and examples')
            continue
        name = str(item.get('name') or '').strip()
        args = ' '.join(str(item.get('args') or '').split())
        if args.startswith('(') and args.endswith(')'):
            args = args[1:-1].strip()
        contract = ' '.join(str(item.get('contract') or '').split()).lstrip('#').strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            errors.append(f'unit {i}: {name[:40]!r} is not a JavaScript function name')
            continue
        if '`' in args or len(args) > 200:
            errors.append(f'{name}: its args must be plain parameter names')
            continue
        lines = [f'## Unit `{name}({args})`', '']
        if uses:
            lines += ['Uses: ' + ', '.join(f'`{u}`' for u in uses), '']
        lines += [contract, '', 'Examples:']
        for example in item.get('examples') or []:
            call = ' '.join(str((example or {}).get('call') or '').split()) if isinstance(example, dict) else ''
            if not call or '==>' in call or not isinstance(example, dict) or 'expect' not in example:
                errors.append(f'{name}: an example needs a call and the value it returns')
                continue
            try:
                expect = expect_json(example['expect'])
            except (TypeError, ValueError):
                errors.append(f'{name}: the expected value of `{call[:60]}` is not JSON')
                continue
            lines.append(f'    {call} ==> {expect}')
        sections.append('\n'.join(lines))
    return sections, errors


def _bounds(lines, sheet, index):
    """Line range [start, end) of unit `index` in the sheet text (from its heading to the next section)."""
    start = sheet['units'][index]['line'] - 1
    later = [u['line'] for u in sheet['units'][index + 1:]] + ([sheet['template']['line']] if sheet['template'] else [])
    return start, (min(later) - 1 if later else len(lines))


def _mentions(text, name) -> bool:
    return re.search(r'(?<![\w$])' + re.escape(name) + r'(?![\w$])', text) is not None


def split_sheet(text, unit, reply, *, children=SPLIT_UNITS[1], js=None) -> tuple[str | None, list[str]]:
    """Validate a planner's split of `unit` and return (refined sheet, []) or (None, reasons).

    The refined sheet is the parent sheet with the stalled unit's section replaced by the sub-units and
    then the stalled unit itself, its `Uses:` extended with the sub-units and one line asking it to call
    them; its examples stay as the integration check. Every other byte of the sheet is kept. Checked by
    code: symblic.spec.sheets parses the result with no problems, 2..children sub-units with new names, at least
    two examples each that call their own unit, `Uses:` naming only units above, and every example call
    runs as JavaScript (`examples_executable`, the sandboxed js adapter, against stubs)."""
    errors = []
    try:
        sheet = SP.parse(text)
        index, _ = _unit(sheet, unit)
    except (SP.SheetError, KernelError):
        return None, [f'the unit {unit!r} is not in the sheet']
    if isinstance(reply, str) and reply.lstrip().startswith('['):
        try:
            reply = json.loads(reply)              # a typed answer handed over as its JSON text
        except ValueError:
            pass
    if isinstance(reply, (list, tuple)):
        inherited = [u for u in sheet['units'][index]['uses']
                     if (re.match(r'[A-Za-z_$][\w$]*', u) or [None])[0] in {n for x in sheet['units'][:index] for n in x['names']}]
        sections, errors = _typed_sections(reply, inherited)
        if errors:
            return None, errors[:12]
    else:
        sections = _reply_sections(reply)          # a Text answer, from a planner compiled before the typed ask
    high = max(SPLIT_UNITS[0], min(SPLIT_UNITS[1], int(children)))
    if not SPLIT_UNITS[0] <= len(sections) <= high:
        return None, [f'the answer has {len(sections)} unit section(s); a split needs {SPLIT_UNITS[0]} to {high}']
    try:
        subs = SP.parse('# split\n\n' + '\n\n'.join(sections) + '\n')['units']
    except SP.SheetError as exc:
        return None, [f'the answer does not parse as sheet units: {exc}']
    taken = {n for u in sheet['units'] for n in u['names']}
    earlier = {n for u in sheet['units'][:index] for n in u['names']}
    seen = set()
    for sub in subs:
        head = sub['heading']
        for name in sub['names']:
            if name in taken or name in seen:
                errors.append(f'{head}: the name {name} is already defined')
            if name == PLACEHOLDER:
                errors.append(f'{head}: {PLACEHOLDER} is the answer format\'s example, not a unit of this file')
            seen.add(name)
        if not sub['body']:
            errors.append(f'{head}: no contract')
        if len(sub['examples']) < 2:
            errors.append(f'{head}: {len(sub["examples"])} example(s); at least 2 are needed')
        for call, _ in sub['examples']:
            if not any(_mentions(call, n) for n in sub['names']):
                errors.append(f'{head}: the example `{call[:80]}` does not call {", ".join(sub["names"])}')
        for used in sub['uses']:
            base = re.match(r'[A-Za-z_$][\w$]*', used)
            if not base or (base.group(0) not in earlier and base.group(0) not in seen - set(sub['names'])):
                errors.append(f'{head}: Uses names {used}, which no unit above it defines')
    if errors:
        return None, errors[:12]
    lines = str(text).replace('\r\n', '\n').split('\n')
    start, end = _bounds(lines, sheet, index)
    section = list(lines[start:end])
    while section and not section[-1].strip():
        section.pop()
    names = [s['names'][0] for s in subs]
    listed = ', '.join(f'`{n}`' for n in names)
    at = next((i for i, l in enumerate(section) if l.strip().startswith('Uses:')), None)
    if at is None:
        section[1:1] = ['Uses: ' + listed]
    else:
        section[at] = section[at].rstrip() + ', ' + listed
    hint = 'Build it by calling ' + ', '.join(f'`{s["heading"]}`' for s in subs) + ', which are already in the file above your code.'
    at = next((i for i, l in enumerate(section) if l.strip() in ('Test setup:', 'Examples:')), len(section))
    section[at:at] = ['', hint, '']
    refined = '\n'.join(lines[:start] + '\n\n'.join(sections).split('\n') + [''] + section + [''] + lines[end:])
    try:
        found = SP.problems(SP.parse(refined))
    except SP.SheetError as exc:
        found = [str(exc)]
    if found:
        return None, [f'the refined sheet does not compile: {p}' for p in found[:8]]
    found = examples_executable(refined, set(seen), js=js)
    if found:
        return None, found[:8]
    return refined, []


def examples_executable(text, names, js=None) -> list[str]:
    """Every example of the units defining `names` must run as JavaScript: its call is evaluated (in the
    sandboxed js adapter, after the unit's test setup) against stubs that declare every name of the sheet
    as a function returning null. A syntax error, or a name nothing declares, makes it not executable;
    a wrong value never does (no implementation exists yet). `js` replaces symblic.js.check.evaluate."""
    if js is None:
        from symblic.js import check as js_check
        js = js_check.evaluate
    sheet = SP.parse(text)
    stub = '\n'.join(f'function {n}() {{ return null; }}' for u in sheet['units'] for n in u['names'])
    out = []
    for unit in sheet['units']:
        if not set(unit['names']) & set(names):
            continue
        calls = [call for call, _ in unit['examples']]
        try:
            results = js(([unit['setup']] if unit['setup'] else []) + [stub], calls)
        except Exception as exc:  # noqa: BLE001 - an unavailable checker refuses the split visibly
            return [f'the examples could not be checked: {str(exc)[:200]}']
        for call, result in zip(calls, results):
            error = str(result.get('error') or '')
            if result.get('ok'):
                continue
            if result.get('kind') in ('syntax', 'redefine'):
                out.append(f'{unit["heading"]}: `{call[:80]}` does not run as JavaScript: {error[:160]}')
            elif 'ReferenceError' in error:
                out.append(f'{unit["heading"]}: `{call[:80]}` uses a name no unit or test setup defines: {error[:160]}')
    return out


# ------------------------------------------------------------------------------ run folders (read only)

_STATUS_CACHE: dict = {}
_STATUS_LOCK = threading.Lock()           # one coordinator thread per run polls its builds
STATUS_CACHE_MAX = 64


def _json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _signature(path):
    try:
        st = os.stat(path)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def accepted(rows) -> list[str]:
    """The unit variables a build accepted, in order, from its trace rows: an `ask unit_X` row with status
    ok (route=search writes it only after a candidate passed its examples), or a kept `let unit_X` row
    whose `assert` then passed. A later failed or retried ensure takes the ask back."""
    out, kept, last_ask = [], None, None
    for row in rows:
        kind, name, status = row.get('kind'), str(row.get('name') or ''), row.get('status')
        if kind in ('ask', 'let') and name.startswith('unit_'):
            kept, last_ask = None, None
            if status == 'ok' and kind == 'ask':
                if name not in out:
                    out.append(name)
                last_ask = name
            elif status == 'ok':
                kept = name
            continue
        if kind == 'assert' and kept:
            if status == 'ok' and kept not in out:
                out.append(kept)
            kept = None
        elif kind == 'ensure' and status in ('retry', 'failed') and last_ask in out:
            out.remove(last_ask)
            last_ask = None
    return out


def status(run_dir, label=None) -> dict:
    """{'done', 'status', 'accepted', 'units', 'outputs': {label: text}, 'page', 'calls', 'error'} of one
    build folder, read from state.json (the final report once the run ends) and trace.jsonl. `page` is the
    output labelled `label`. Never waits; cached by file size and mtime."""
    run_dir = str(run_dir)
    state_path, trace_path = os.path.join(run_dir, 'state.json'), os.path.join(run_dir, 'trace.jsonl')
    key = (_signature(state_path), _signature(trace_path), label)
    with _STATUS_LOCK:
        cached = _STATUS_CACHE.get(run_dir)
    if cached and cached[0] == key:
        return dict(cached[1])
    state = _json(state_path)
    rows = []
    try:
        with open(trace_path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    outputs = {}
    for out in state.get('outputs') or []:
        if not isinstance(out, dict) or not isinstance(out.get('label'), str):
            continue
        if isinstance(out.get('value'), str):
            outputs[out['label']] = out['value']
        elif 'canonical' in out:
            # a typed answer (the planner's list of units): `value` renders 0.5 as "0.5", the canonical form
            # keeps it a number ({"#q": "1/2"}), so expected values reach the sheet as the JSON the model gave
            try:
                outputs[out['label']] = decanon(out['canonical'])
            except (TypeError, ValueError, ZeroDivisionError):
                continue
    run_status = str(state.get('status') or ('starting' if not os.path.exists(state_path) else 'running'))
    units = accepted(rows)
    error = state.get('error') if isinstance(state.get('error'), dict) else None
    result = {'done': run_status in FINAL, 'status': run_status, 'accepted': units, 'units': len(units),
              'outputs': outputs, 'page': outputs.get(label) if label else None,
              'calls': state.get('calls') if isinstance(state.get('calls'), int) else 0, 'error': error}
    with _STATUS_LOCK:
        _STATUS_CACHE.pop(run_dir, None)
        _STATUS_CACHE[run_dir] = (key, dict(result))
        while len(_STATUS_CACHE) > STATUS_CACHE_MAX:
            _STATUS_CACHE.pop(next(iter(_STATUS_CACHE)))
    return result


def decanon(value):
    """A kernel value's canonical JSON form back to plain JSON with exact numbers: an integer
    stays an int, a tagged rational {"#q": "p/q"} becomes a Fraction, an escaped record key loses its extra '#'."""
    from fractions import Fraction
    if isinstance(value, list):
        return [decanon(x) for x in value]
    if isinstance(value, dict):
        if set(value) == {'#q'} and isinstance(value['#q'], str):
            return Fraction(value['#q'])
        if set(value) == {'#set'} and isinstance(value['#set'], list):
            return [decanon(x) for x in value['#set']]
        if len(value) == 1 and next(iter(value)) in ('#svg',):
            raise ValueError('not a JSON value')
        return {(k[1:] if k.startswith('##') else k): decanon(x) for k, x in value.items()}
    return value


def expect_json(raw) -> str:
    """A typed answer's `expect` as JSON text. Text is read as JSON (compacted); text that is not JSON is the
    string it spells ("ready" and 'ready' both mean the string ready). Any other value is written as JSON."""
    from decimal import Decimal
    if not isinstance(raw, str):
        return json_text(raw)
    text = raw.strip()
    try:
        return json_text(json.loads(text, parse_float=Decimal))
    except ValueError:
        if len(text) >= 2 and text[0] == text[-1] == "'":
            text = text[1:-1]
        return json.dumps(text, ensure_ascii=False)


def json_text(value) -> str:
    """Compact JSON text of a decoded value; a Fraction is written as its exact decimal (a JSON reply's
    numbers are decimals, so the expansion ends) or, if it would not end, as the nearest double."""
    from decimal import Decimal, localcontext
    from fractions import Fraction
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('not a JSON number')
        return str(value)
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return str(value.numerator)
        rest = value.denominator
        for factor in (2, 5):
            while rest % factor == 0:
                rest //= factor
        if rest != 1:
            return repr(float(value))
        with localcontext() as ctx:
            ctx.prec = 400
            text = format(Decimal(value.numerator) / Decimal(value.denominator), 'f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    if isinstance(value, list):
        return '[' + ','.join(json_text(x) for x in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(str(k), ensure_ascii=False) + ':' + json_text(x) for k, x in value.items()) + '}'
    return json.dumps(value, ensure_ascii=False)


def log_tail(run_dir, limit=LOG_TAIL) -> str:
    """The last `limit` characters of a build's log (RUN_DIR.log), or '' when there is none."""
    try:
        with open(str(run_dir) + '.log', 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode('utf-8', 'replace').strip()
    except OSError:
        return ''


def file_sha256(folder, name) -> str | None:
    """The content hash of a checkout's file before a build writes it (None when absent)."""
    try:
        with open(os.path.join(folder, name), 'rb') as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def install(folder, name, text) -> dict:
    """Write the assembled page into the attempt's own checkout (atomic, never outside it)."""
    if not safe_file(name):
        raise KernelError(f'refusing to write {name!r}')
    if not folder or not os.path.isdir(folder):
        raise KernelError(f'the attempt\'s checkout {folder!r} is gone')
    root = os.path.realpath(folder)
    path = os.path.realpath(os.path.join(root, name))
    if not path.startswith(root + os.sep):
        raise KernelError(f'refusing to write {name!r} outside the checkout')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.autogen-tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        handle.write(text)
    os.replace(tmp, path)
    return {'file': name, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


# ------------------------------------------------------------------------------ processes

_PROCS: dict = {}
_PROCS_LOCK = threading.Lock()
_SCOPE: dict = {}
BUS_VARS = ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS')


def _read_pid(run_dir):
    try:
        with open(str(run_dir) + '.pid', encoding='utf-8') as handle:
            value = int(handle.read(32).strip())
        return value if value > 1 else None
    except (OSError, ValueError):
        return None


def _scope(unit):
    """`systemd-run --user --scope` under SCOPE_SLICE: the build gets its own capped cgroup (memory,
    CPU share, task count), survives a restart of the coordinator's process, and an out-of-memory kill
    aimed at it never takes the coordinator with it. Probed once per process; empty under tests
    (DASH_TEST=1), when SYMBLIC_SCOPE=0, or without a user bus."""
    if os.environ.get('DASH_TEST') == '1' or os.environ.get(SCOPE_ENV, '1') == '0':
        return []
    exe = shutil.which('systemd-run') or ('/usr/bin/systemd-run' if os.path.exists('/usr/bin/systemd-run') else '')
    if not exe or not os.environ.get('XDG_RUNTIME_DIR'):
        return []
    if 'ok' not in _SCOPE:
        env = {'PATH': '/usr/bin:/bin', **{k: os.environ[k] for k in BUS_VARS if os.environ.get(k)}}
        try:
            _SCOPE['ok'] = subprocess.run([exe, '--user', '--scope', '--quiet', '--collect', '--slice', SCOPE_SLICE,
                                           '--', '/bin/true'], capture_output=True, timeout=20, env=env).returncode == 0
        except (OSError, subprocess.SubprocessError):
            _SCOPE['ok'] = False
    if not _SCOPE['ok']:
        return []
    argv = [exe, '--user', '--scope', '--quiet', '--collect', '--unit', unit, '--slice', SCOPE_SLICE]
    for prop in SCOPE_PROPERTIES:
        argv += ['-p', prop]
    return argv + ['--']


def unit_name(run_dir) -> str:
    """The scope unit of one build: autogen-kernel-<run hex>-<attempt id>."""
    run_dir = str(run_dir).rstrip('/')
    run = os.path.basename(os.path.dirname(run_dir)).removeprefix('autogen-')
    return re.sub(r'[^A-Za-z0-9:_.-]', '-', f'autogen-kernel-{run}-{os.path.basename(run_dir)}')[:200]


def run(program_text, run_dir, applicators, limits=None, log=None) -> int:
    """Start `tools/symblic run RUN_DIR.sym --dir RUN_DIR --ollama-limits JSON --json` and return its pid
    without waiting. The child writes its own pid to RUN_DIR.pid before it execs (sh -> systemd-run scope
    -> tools/symblic -> nice 10 python keep that pid), so a re-dispatch after a crash adopts the recorded
    process: one run folder never gets two builds. Its environment is PATH, HOME and LANG only; its own
    session makes it one process group for `stop`; stdout and stderr go to RUN_DIR.log."""
    apps = check_applicators(applicators)
    if not _uses_only(program_text, apps):
        raise KernelError('the program names applicators other than ' + ', '.join(apps))
    if os.environ.get('DASH_TEST') == '1' and Path(BIN_SYMBLIC).resolve() == (REPO / 'tools' / 'symblic').resolve():
        # a test never starts a real build: that would call a real model on a node
        raise KernelError('kernel builds are not started under tests (DASH_TEST=1); inject a fake kernel')
    run_dir = os.path.abspath(str(run_dir))
    os.makedirs(os.path.dirname(run_dir), mode=0o700, exist_ok=True)
    existing = _read_pid(run_dir)
    if existing:
        return existing
    program_path = run_dir + '.sym'
    try:
        with open(program_path, encoding='utf-8') as handle:
            if handle.read() != program_text:
                raise KernelError('a different program was already written for this run folder')
    except FileNotFoundError:
        tmp = program_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            handle.write(program_text)
        os.replace(tmp, program_path)
    limits = dict(LIMITS if limits is None else limits)
    argv = [str(BIN_SYMBLIC), 'run', program_path, '--dir', run_dir, '--ollama-limits',
            json.dumps(limits, sort_keys=True), '--json']
    env = {'PATH': os.environ.get('PATH') or '/usr/local/bin:/usr/bin:/bin', 'HOME': os.path.expanduser('~'),
           'LANG': 'C.UTF-8'}
    scope = _scope(unit_name(run_dir))
    if scope:
        bus = {k: os.environ[k] for k in BUS_VARS if os.environ.get(k)}
        env.update(bus)                   # for systemd-run only; the build itself gets them unset again
        argv = scope + ['/usr/bin/env'] + [x for k in bus for x in ('-u', k)] + argv
    wrapper = ['/bin/sh', '-c', 'echo $$ > "$0.tmp" && mv -f "$0.tmp" "$0" && exec "$@"', run_dir + '.pid'] + argv
    with open(log or (run_dir + '.log'), 'ab') as out:
        proc = subprocess.Popen(wrapper, cwd=str(REPO), env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
    with _PROCS_LOCK:
        _PROCS[proc.pid] = proc
    # the child wrote (or is about to write) the same pid; writing it here too closes the window in which a
    # second call could miss it
    tmp = run_dir + '.pid.parent'
    with open(tmp, 'w', encoding='utf-8') as handle:
        handle.write(str(proc.pid))
    os.replace(tmp, run_dir + '.pid')
    return proc.pid


def alive(pid, run_dir='') -> bool:
    """The build process still runs: our own child polled (and reaped), else a live, non-zombie process
    whose command line names the run folder (a reused pid never counts)."""
    if not pid:
        return False
    with _PROCS_LOCK:
        proc = _PROCS.get(pid)
    if proc is not None:
        if proc.poll() is None:
            return True
        with _PROCS_LOCK:
            _PROCS.pop(pid, None)
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        with open(f'/proc/{pid}/stat', 'rb') as handle:
            if handle.read().rsplit(b')', 1)[-1].split()[:1] == [b'Z']:
                return False
        with open(f'/proc/{pid}/cmdline', 'rb') as handle:
            command = handle.read()
    except OSError:
        return False
    return not run_dir or os.fsencode(str(run_dir)) in command


def stop(pid, run_dir='', grace=STOP_GRACE) -> bool:
    """Stop one build: SIGTERM to its process group (the CLI releases its admitted model calls on
    exit), SIGKILL after `grace` seconds, then its scope. True when nothing of it runs any more. A pid
    that is not this build's (dead, or reused) is never signalled."""
    pid = pid or _read_pid(run_dir)
    if not pid or not alive(pid, run_dir):
        return True
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5)):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if not alive(pid, run_dir):
                break
            time.sleep(0.25)
        if not alive(pid, run_dir):
            break
    if os.environ.get('DASH_TEST') != '1' and shutil.which('systemctl') and os.environ.get('XDG_RUNTIME_DIR') and run_dir:
        try:
            subprocess.run(['systemctl', '--user', 'stop', unit_name(run_dir) + '.scope'], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass
    return not alive(pid, run_dir)


# ------------------------------------------------------------------------------ where the model is

ABSENT_RX = re.compile(r'\bis not installed on ([a-z0-9][a-z0-9-]*)')


def absent_node(text) -> str:
    """The node a kernel error says lacks the model ("ollama@node-a: unavailable: M is not installed on node-a")."""
    match = ABSENT_RX.search(str(text or ''))
    return match.group(1) if match else ''


def model_nodes(model, host='', rows=None, fits=None) -> dict | None:
    """Where `model` can run: {'have': nodes (never `host`) whose inventory lists the model and where it
    fits the node's Ollama memory limit, 'answered': nodes that listed any model}. The inventory comes
    from symblic.providers.applicators (each node's Ollama /api/tags as that module reads it). None
    when it cannot be read, which includes every machine where that provider module cannot reach an
    inventory; then the caller keeps its own node list. Tests (DASH_TEST=1) never read a live
    inventory; they pass `rows`."""
    model = str(model or '').strip()
    if rows is None:
        if os.environ.get('DASH_TEST') == '1':
            return None
        try:
            from symblic.providers import applicators as providers
            rows = providers.Applicators.inventory()
            fits = fits or providers.Applicators()._fits
        except Exception:  # noqa: BLE001 - unknown: the caller keeps its own node list
            return None
    if not rows:
        return None
    fits = fits or (lambda row: True)
    names = {model, model + ':latest'} if ':' not in model else {model}
    answered = sorted({str(r.get('node')) for r in rows if r.get('node')})
    have = sorted({str(r['node']) for r in rows if r.get('model') in names and r.get('node')
                   and r.get('node') != host and fits(r)})
    return {'have': have, 'answered': answered}


# ------------------------------------------------------------------------------ checkout and promotion

def checkout(cwd, name) -> dict:
    """The attempt's own checkout of the project (git_checkouts.make_checkout): a worktree at
    <project>.autogen/<name>-<stamp> on branch autogen/<name>-<stamp>, with the operator's uncommitted
    work carried over as its baseline commit. A checkout this name already made (the coordinator died
    before recording it) is adopted, never made twice."""
    try:
        return GIT.make_checkout(cwd, name)
    except GIT.CheckoutError as exc:
        raise KernelError(str(exc)) from None


def promote(info, message) -> dict:
    """Bring an accepted build home: commit everything in the attempt's checkout, then apply that
    commit to the project's working tree file by file (git_checkouts.apply_to_project: a 3-way rule, no
    commit in the project). A clash raises "Nothing was applied: N file(s) clash with your checkout ...";
    the coordinator records it as CONFLICT."""
    GIT.commit_all(info, message)
    return GIT.apply_to_project(info)

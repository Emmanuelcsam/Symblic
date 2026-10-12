"""Autogen's kernel lane (symblic/autogen/kernel_lane.py): attempts of `local` runs are spec-sheet
builds, not agent tasks.

The coordinator journeys run over the standalone harness (tests/autogen/harness.py: temporary stores,
the documented FakeTaskRunner as the node catalogue, a fake check runner, an injected clock) with a
FakeKernel: the real pure helpers of kernel_lane.py (sheets, plans, compiled programs, split
validation, run-folder parsing) and fake effects (no process, no git, no model). A test plays the build
process by writing its run folder (state.json, trace.jsonl) the way `tools/symblic run` does. The module
tests at the end run the real process mechanics against a harmless stand-in for tools/symblic, the real
git checkout and 3-way apply (symblic/autogen/git_checkouts.py) on a temporary repository, and the
sandboxed JavaScript check when node and Landlock are available. No test starts a real build or calls a
model. Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from symblic.autogen import policy as POLICY
from symblic.spec import sheets as SP
from symblic.autogen import kernel_lane as K
from symblic.autogen.coordinator import AutogenError
from tests.autogen.harness import HOST, CoordinatorHarness, Crash

SHEET = '''# handoff.js
One small file of integer helpers.

## Shared

Integer arithmetic. Plain function declarations.

## Unit `double(x)`

Return twice the integer x.

Examples:
    double(3) ==> 6
    double(-2) ==> -4

## Unit `ready()`

Return the string "ready".

Examples:
    ready() ==> "ready"

## Unit `next(x)`

Uses: `double`

Return double(x) plus one.

Examples:
    next(3) ==> 7
    next(-2) ==> -3

## Assemble `handoff.js`

    /*UNITS*/
'''
PAGE = ('function double(x) { return 2 * x; }\n\nfunction ready() { return "ready"; }\n\n'
        'function next(x) { return double(x) + 1; }')
SPLIT_REPLY = '''Here is the split.

```
### Unit `plusOne(x)`
Return x plus one.

**Examples:**
- `plusOne(3) ==> 4`
- plusOne(-1) ==> 0

## Unit `twiceThenOne(x)`
Uses: `double`, `plusOne`
Return plusOne(double(x)).
twiceThenOne(3) ==> 7
twiceThenOne(0) ==> 1
```
Hope this helps.'''
TYPED_SPLIT = [                     # the typed planner answer (planner_type): a list of unit objects
    {'name': 'plusOne', 'args': 'x', 'contract': 'Return x plus one.',
     'examples': [{'call': 'plusOne(3)', 'expect': '4'}, {'call': 'plusOne(-1)', 'expect': '0'}]},
    {'name': 'twiceThenOne', 'args': '(x)', 'contract': 'Return plusOne(double(x)).',
     'examples': [{'call': 'twiceThenOne(3)', 'expect': '7'}, {'call': 'twiceThenOne(0)', 'expect': '1'}]},
]
RESTATED = [                        # what a 3B answered on 2026-10-11: the stalled unit and its own examples again
    {'name': 'nextPart', 'args': 'x', 'contract': 'Return double(x) plus one.',
     'examples': [{'call': 'next(3)', 'expect': '7'}, {'call': 'next(-2)', 'expect': '-3'}]},
    {'name': 'nextRest', 'args': 'x', 'contract': 'Return double(x) plus one.',
     'examples': [{'call': 'next(3)', 'expect': '7'}, {'call': 'next(-2)', 'expect': '-3'}]},
]
APP = 'ollama:qwen3:4b-instruct@node09'
STOPPED = 'unit_next: no search candidate passed its checks in 1 round(s) of 2: ollama:qwen3:4b-instruct@node09: 1 of 2 examples failed'


def ok_js(pieces, calls):
    return [{'ok': True, 'value': 'null'} for _ in calls]


class FakeKernel:
    """The kernel lane without processes: the module's pure helpers, fake effects. `run` adopts an earlier
    process of the same run folder exactly as the real pid file does; `promote` applies the files an attempt
    changed with the 3-way rule (written only where the project still holds the checkout's base)."""
    SEARCH, SPLIT_SEARCH, LIMITS, SPLIT_LABEL = K.SEARCH, K.SPLIT_SEARCH, K.LIMITS, K.SPLIT_LABEL
    is_sheet = staticmethod(K.is_sheet)
    sheet_problems = staticmethod(K.sheet_problems)
    plan = staticmethod(K.plan)
    plan_checks = staticmethod(K.plan_checks)
    stalled_unit = staticmethod(K.stalled_unit)
    applicator = staticmethod(K.applicator)
    absent_node = staticmethod(K.absent_node)
    seed = staticmethod(K.seed)
    log_tail = staticmethod(K.log_tail)
    file_sha256 = staticmethod(K.file_sha256)
    install = staticmethod(K.install)

    def __init__(self):
        self.checkouts = ''
        self.compiled, self.runs, self.stops, self.promoted = [], [], [], []
        self.pids, self.live, self.bases = {}, set(), {}
        self.next_pid = 4242
        self.stop_ok = True
        self.promote_error = None
        self.js = ok_js
        self.inventory = None              # model_nodes: unknown, as under DASH_TEST
        self.inventory_reads = []

    def model_nodes(self, model, host=''):
        self.inventory_reads.append(model)
        return self.inventory

    def status(self, run_dir, label=None):
        K._STATUS_CACHE.clear()            # a test rewrites run folders faster than mtimes move
        return K.status(run_dir, label)

    def compile(self, text, applicators, *, keep_folder=None, redo=(), samples=2, retries=2, rounds=1, seed=None):
        self.compiled.append({'mode': 'build', 'keep': keep_folder, 'seed': seed, 'applicators': list(applicators),
                              'sheet': text})
        return K.compile(text, applicators, samples=samples, retries=retries, rounds=rounds, seed=seed)

    def split_program(self, text, unit, applicators, *, seed=None, error='', children=3):
        self.compiled.append({'mode': 'split', 'unit': unit, 'error': error, 'seed': seed})
        return K.split_program(text, unit, applicators, seed=seed, error=error, children=children)

    def split_sheet(self, text, unit, reply, *, children=3):
        return K.split_sheet(text, unit, reply, children=children, js=self.js)

    def run(self, program, run_dir, applicators, limits=None, log=None):
        K.check_applicators(applicators)
        assert K._uses_only(program, applicators)
        if run_dir in self.pids:
            return self.pids[run_dir]      # the pid file: one run folder never gets two builds
        self.runs.append({'run_dir': run_dir, 'program': program, 'applicators': list(applicators), 'limits': limits})
        pid, self.next_pid = self.next_pid, self.next_pid + 1
        self.pids[run_dir] = pid
        self.live.add(pid)
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        return pid

    def alive(self, pid, run_dir=''):
        return pid in self.live

    def stop(self, pid, run_dir='', grace=0):
        self.stops.append((pid or self.pids.get(run_dir), run_dir))
        if not self.stop_ok:
            return False
        self.live.discard(pid or self.pids.get(run_dir))
        return True

    def checkout(self, cwd, name):
        wt = os.path.join(self.checkouts, name)
        if not os.path.isdir(wt):
            shutil.copytree(cwd, wt, ignore=shutil.ignore_patterns('.git'))
        self.bases.setdefault(wt, self._files(wt))
        return {'worktree': wt, 'cwd': wt, 'branch': 'autogen/' + name, 'base_sha': 'b' * 40, 'main_root': cwd}

    @staticmethod
    def _files(folder):
        out = {}
        for top, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d != '.git']
            for leaf in files:
                path = os.path.join(top, leaf)
                out[os.path.relpath(path, folder)] = Path(path).read_bytes()
        return out

    def promote(self, info, message):
        if self.promote_error:
            raise RuntimeError(self.promote_error)
        base, theirs = self.bases[info['worktree']], self._files(info['worktree'])
        plan, clash = [], []
        for rel, data in theirs.items():
            if data == base.get(rel):
                continue
            target = Path(info['main_root'], rel)
            ours = target.read_bytes() if target.exists() else None
            if ours == data:
                continue
            (plan if ours == base.get(rel) else clash).append((rel, data))
        if clash:
            raise RuntimeError(f'Nothing was applied: {len(clash)} file(s) clash with your checkout: '
                               + ', '.join(rel for rel, _ in clash))
        for rel, data in plan:
            Path(info['main_root'], rel).write_bytes(data)
        self.promoted.append({'worktree': info['worktree'], 'files': [rel for rel, _ in plan], 'message': message})
        return {'message': 'applied', 'files': [rel for rel, _ in plan]}


class KernelHarness(CoordinatorHarness):
    ENGINES = ('claude', 'agy', 'local')

    def setUp(self):
        self.kernel = FakeKernel()          # before the base setUp builds the manager: never the real kernel
        super().setUp()
        self.kernel.checkouts = str(Path(self.tmp.name) / 'project.autogen')

    def make_auto(self, task_runner=None, **extra):
        return super().make_auto(task_runner, kernel=self.kernel, **extra)

    def sheet_body(self, request='sheet-1', sheet=SHEET, **policy):
        return {'client_request_id': request, 'instruction': sheet, 'sheet': True, 'engine': 'local',
                'model': 'qwen3:4b-instruct', 'node': 'node09', 'cwd': self.cwd, 'autogen': policy}

    def start(self, **policy):
        return self.auto.submit(self.sheet_body(**policy))['run']['id']

    def build(self, attempt, units, page=None, error=None, alive=False, calls=4):
        """The attempt's build process writes its run folder: one trace row per accepted unit, then (unless it
        is still running) its final state: done with the assembled page, or failed with the kernel's error."""
        k = attempt['kernel']
        run_dir = Path(k['run_dir'])
        run_dir.mkdir(parents=True, exist_ok=True)
        rows = [{'kind': 'ask', 'status': 'ok', 'name': 'unit_' + u, 'line': 10 + i} for i, u in enumerate(units)]
        (run_dir / 'trace.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        if alive:
            (run_dir / 'state.json').write_text(json.dumps({'status': 'running', 'calls': calls}))
            return
        if page is not None:
            state = {'status': 'done', 'calls': calls,
                     'outputs': [{'kind': 'show', 'line': 40, 'label': k['label'], 'value': page}]}
        else:
            state = {'status': 'failed', 'calls': calls, 'outputs': [],
                     'error': error or {'kind': 'check', 'message': STOPPED, 'line': 30, 'col': 1}}
        (run_dir / 'state.json').write_text(json.dumps(state))
        self.kernel.live.discard(k['pid'])

    def answer(self, attempt, reply, canonical=None):
        """The planner's kernel run ends with its answer: a typed list of units (written as tools/symblic run writes a
        typed output: `value` plus its `canonical` form), or the Text answer of an earlier planner."""
        run_dir = Path(attempt['kernel']['run_dir'])
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / 'trace.jsonl').write_text(json.dumps({'kind': 'ask', 'status': 'ok', 'name': 'split_unit'}) + '\n')
        out = {'kind': 'show', 'label': 'split', 'value': reply}
        if not isinstance(reply, str):
            out['canonical'] = reply if canonical is None else canonical
        (run_dir / 'state.json').write_text(json.dumps({'status': 'done', 'calls': 2, 'outputs': [out]}))
        self.kernel.live.discard(attempt['kernel']['pid'])

    def absent(self, attempt, node, units=()):
        """The attempt's kernel run found the model missing on its node (the provider's refusal, as the run reports it)."""
        self.build(attempt, list(units), error={'kind': 'unavailable', 'line': 9, 'col': 1, 'message': (
            f'unit_next: no search candidate passed its checks in 1 round(s) of 2: ollama:qwen3:4b-instruct@{node}: '
            f'ollama@{node}: unavailable: qwen3:4b-instruct is not installed on {node}')})

    def stall(self, **policy):
        """until_done with novelty_limit 1: a build that accepts two units, then one that adds none, so the
        unit `next` is split."""
        run_id = self.start(until_done=True, novelty_limit=1, **policy)
        self.auto.advance(run_id)
        for _ in range(2):
            self.build(self.last(run_id), ['double', 'ready'])
            self.assertTrue(self.auto.advance(run_id))
        return run_id

    def last(self, run_id, node_id='n0'):
        return self.attempts(run_id, node_id)[-1]

    def running(self, run_id, node_id='n0'):
        return next((a for a in reversed(self.attempts(run_id, node_id)) if a['status'] == 'running'), None)


class SheetAdmission(KernelHarness):
    def test_a_sheet_is_one_statement_checked_by_the_sheet_parser_not_by_the_line_lint(self):
        result = self.auto.submit(self.sheet_body(designer=True))
        run = result['run']
        self.assertFalse(result['duplicate'])
        self.assertEqual([SHEET], run['lines'])                       # verbatim: 40 lines, many under 20 characters
        node = run['nodes'][0]
        self.assertEqual((True, False), (node['sheet'], node['needs_design']))   # its examples are its tests
        self.assertEqual((['local'], ['node09']), (run['policy']['engines'], run['policy']['nodes']))
        self.assertTrue(run['base']['sheet'])
        self.assertEqual([], self.tasks.submitted)
        self.assertTrue(self.auto.submit(self.sheet_body(designer=True))['duplicate'])
        # a local run recognises a sheet without the flag
        plain = {k: v for k, v in self.sheet_body('sheet-2').items() if k != 'sheet'}
        self.assertEqual([SHEET], self.auto.submit(plain)['run']['lines'])

    def test_refusals_name_what_is_wrong_before_any_record(self):
        no_examples = SHEET.replace('Examples:\n    ready() ==> "ready"\n', '')
        outside = SHEET.replace('## Assemble `handoff.js`', '## Assemble `../handoff.js`')
        cases = [
            ({**self.sheet_body(), 'instruction': 'Create the file app.js in the folder ' + self.cwd + ' with f.', 'sheet': False},
             'local attempts take a spec sheet; see docs/reference/SPEC-SHEETS.md'),
            ({**self.sheet_body(), 'engine': 'claude'}, 'A spec sheet runs on the local kernel lane'),
            ({**self.sheet_body(), 'sheet': 'yes'}, 'sheet must be true or false'),
            (self.sheet_body(sheet=no_examples), 'Spec sheet refused: unit ready() has no examples'),
            (self.sheet_body(sheet=outside), 'must be a relative path with an extension inside the workspace'),
            ({**self.sheet_body(), 'model': 'gpt-oss:120b-cloud'}, 'not a local Ollama model name'),
            ({**self.sheet_body(), 'node': HOST}, 'not on the coordinating machine'),
            (self.sheet_body(perpetual=True), 'a perpetual lane does not apply'),
        ]
        for body, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(AutogenError) as caught:
                    self.auto.submit(body)
                self.assertIn(message, str(caught.exception))
        self.assertFalse((self.root / 'state' / 'autogen').exists() and list((self.root / 'state' / 'autogen').glob('*.json')))


class KernelLaunch(KernelHarness):
    def test_an_attempt_is_a_kernel_build_in_its_own_checkout_not_a_task(self):
        run_id = self.start()
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(([], {}), (self.tasks.submitted, self.tasks.tasks))   # no agent, no task
        attempt = self.last(run_id)
        k = attempt['kernel']
        self.assertEqual(('candidate', 'running', 'build', [APP]), (attempt['kind'], attempt['status'], k['mode'], k['applicators']))
        self.assertEqual(str(self.root / 'state' / 'autogen' / 'kernel' / run_id / 'n0-a0'), k['run_dir'])
        self.assertEqual((4242, False, '', 3, 'handoff.js'), (k['pid'], k['pending'], k['keep_from'], k['units_total'], k['file']))
        self.assertEqual(k['checkout']['cwd'], attempt['workspace'])
        self.assertTrue(os.path.basename(attempt['workspace']).startswith('autogen-' + run_id[8:20] + '-n0-a0'))
        program = self.kernel.runs[0]['program']
        self.assertEqual(hashlib.sha256(program.encode()).hexdigest(), k['program_sha256'])
        self.assertIn(f'use by=["{APP}"], route=search, samples=2, retries=2, rounds=1, seed={k["seed"]}, context=none.', program)
        self.assertIn('ask unit_next: Code js', program)
        self.assertEqual(['submitted', 'decision', 'launch_intent', 'launched'], self.names(run_id))

    def test_a_crash_between_intent_and_dispatch_starts_the_build_once(self):
        run_id = self.start()
        with mock.patch.object(self.kernel, 'checkout', side_effect=Crash()):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        attempt = self.last(run_id)
        self.assertEqual(('queued', True, None), (attempt['status'], attempt['kernel']['pending'], attempt['kernel']['pid']))
        self.assertEqual(1, self.auto.get(run_id)['budget']['agents_started'])
        restarted = self.make_auto()
        self.assertTrue(restarted.advance(run_id))
        self.assertTrue(restarted.advance(run_id))
        attempt = self.last(run_id)
        self.assertEqual(('running', 4242), (attempt['status'], attempt['kernel']['pid']))
        self.assertEqual(1, len(self.kernel.runs))
        self.assertEqual(1, len(self.attempts(run_id, 'n0')))
        self.assertIn('launch_recovered', self.names(run_id))

    def test_a_crash_after_the_build_started_adopts_its_process(self):
        run_id = self.start()
        real = self.kernel.run

        def started_then_died(*args, **kwargs):
            real(*args, **kwargs)
            raise Crash()
        with mock.patch.object(self.kernel, 'run', side_effect=started_then_died):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        self.assertIsNone(self.last(run_id)['kernel']['pid'])
        restarted = self.make_auto()
        restarted.advance(run_id)
        attempt = self.last(run_id)
        self.assertEqual((4242, 'running'), (attempt['kernel']['pid'], attempt['status']))
        self.assertEqual(1, len(self.kernel.runs))                    # adopted, never a second build


    def test_a_local_run_recorded_before_the_kernel_lane_keeps_its_task_attempts(self):
        run_id = self.auto.submit({'client_request_id': 'old-1', 'instruction': self.statement('app.py'), 'engine': 'claude',
                                   'node': 'node09', 'cwd': self.cwd, 'autogen': {}})['run']['id']
        with self.auto._mutate(run_id) as row:                         # the shape such a run was recorded with
            row['base'].update(engine='local', model='qwen3:4b-instruct')
        self.assertTrue(self.auto.advance(run_id))
        attempt = self.last(run_id)
        self.assertNotIn('kernel', attempt)
        task = self.tasks.get(attempt['task_id'])
        self.assertEqual(self.loc(self.statement('app.py')) + '\n\n' + POLICY.LOCAL_RULE, task['instruction'])
        self.assertEqual([], self.kernel.runs)


class KernelVerdict(KernelHarness):
    CHECK = 'node -e "require(\'./handoff.js\')"'

    def test_a_finished_build_is_checked_in_its_checkout_then_promoted_into_the_project(self):
        run_id = self.start(checks={'0': [self.CHECK]})
        self.auto.advance(run_id)
        attempt = self.last(run_id)
        self.build(attempt, ['double', 'ready', 'next'], page=PAGE)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        attempt = run['nodes'][0]['attempts'][0]
        self.assertEqual(('accepted', 3, 3, 3), (attempt['status'], attempt['kernel']['units_accepted'],
                                                 attempt['kernel']['units_total'], attempt['verdict']['units_accepted']))
        checks = {c['kind']: c for c in attempt['verdict']['checks']}
        self.assertEqual({'exists', 'syntax', 'command', 'units'}, set(checks))
        self.assertTrue(all(c['passed'] for c in checks.values()))
        self.assertEqual(['handoff.js'], attempt['verdict']['changed'])
        commands = [r for r in self.runs if r['shell']]
        self.assertEqual([(self.CHECK, attempt['workspace'])], [(r['argv'], r['cwd']) for r in commands])
        self.assertEqual(PAGE, Path(attempt['workspace'], 'handoff.js').read_text())
        self.assertEqual(PAGE, (self.project / 'handoff.js').read_text())    # promoted by the 3-way apply rule
        self.assertEqual(1, len(self.kernel.promoted))
        self.assertEqual({'files': ['handoff.js'], 'checks': 4, 'done': 0, 'units': 3},
                         {k: v for k, v in run['nodes'][0]['progress'].items()})

    def test_the_operators_failing_check_regenerates_keeping_every_accepted_unit(self):
        run_id = self.start(checks={'0': [self.CHECK]})
        self.results[self.CHECK] = {'rc': 1, 'out': 'TypeError: next is not a function'}
        self.auto.advance(run_id)
        first = self.last(run_id)
        self.build(first, ['double', 'ready', 'next'], page=PAGE)
        self.assertTrue(self.auto.advance(run_id))
        first = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'CHECK_FAILURE'), (first['status'], first['failure']))
        self.assertFalse((self.project / 'handoff.js').exists())        # a failed attempt is never promoted
        second = self.last(run_id)
        self.assertEqual(('regen', 'feedback'), (second['kind'], second['strategy']))
        self.assertEqual(first['kernel']['run_dir'], second['kernel']['keep_from'])
        self.assertEqual(first['kernel']['run_dir'], self.kernel.compiled[-1]['keep'])
        self.assertNotEqual(first['kernel']['seed'], second['kernel']['seed'])
        del self.results[self.CHECK]
        self.build(second, ['double', 'ready', 'next'], page=PAGE)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])


class KernelRegeneration(KernelHarness):
    def test_a_build_that_stops_at_a_unit_regenerates_with_keep_from_its_run(self):
        run_id = self.start()
        self.auto.advance(run_id)
        first = self.last(run_id)
        self.build(first, ['double', 'ready'])
        self.assertTrue(self.auto.advance(run_id))
        first = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'NO_OUTPUT'), (first['status'], first['failure']))
        self.assertEqual(('next', 2, ['unit_double', 'unit_ready']),
                         (first['kernel']['stalled'], first['kernel']['units_accepted'], first['kernel']['accepted']))
        units = next(c for c in first['verdict']['checks'] if c['kind'] == 'units')
        self.assertFalse(units['passed'])
        self.assertIn('2/3 units accepted; the build stopped at next(x): unit_next: no search candidate', units['output'])
        self.assertTrue(first['progress']['new'])
        second = self.last(run_id)
        self.assertEqual(('regen', 'feedback', first['kernel']['run_dir']),
                         (second['kind'], second['strategy'], second['kernel']['keep_from']))
        self.assertEqual([None, first['kernel']['run_dir']], [c['keep'] for c in self.kernel.compiled])

    def test_progress_is_counted_in_accepted_units(self):
        run_id = self.start(until_done=True, novelty_limit=2)
        self.auto.advance(run_id)
        for units, new, stale in ((['double'], True, 0), (['double', 'ready'], True, 0), (['double', 'ready'], False, 1)):
            attempt = self.last(run_id)
            self.build(attempt, units)
            self.assertTrue(self.auto.advance(run_id))
            seen = next(a for a in self.attempts(run_id, 'n0') if a['id'] == attempt['id'])
            self.assertEqual((len(units), new), (seen['progress']['units'], seen['progress']['new']))
            self.assertEqual(stale, self.node(run_id, 'n0')['stale'])
        node = self.node(run_id, 'n0')
        self.assertEqual(2, node['progress']['units'])
        # one model on one node: feedback and fresh are spent once the last build added no unit, so the stalled
        # unit is split (the first one the best build did not accept)
        self.assertEqual(['fresh', 'feedback', 'fresh'], [a['strategy'] for a in node['attempts'][:3]])
        planner = self.last(run_id)
        self.assertEqual(('planner', 'split', 'next'), (planner['kind'], planner['kernel']['mode'], planner['kernel']['unit']))
        self.assertEqual(node['attempts'][2]['kernel']['run_dir'], planner['kernel']['from_run'])


class KernelStops(KernelHarness):
    def test_attempt_seconds_stops_the_build_and_keeps_the_units_it_accepted(self):
        run_id = self.start(attempt_seconds=120)
        self.auto.advance(run_id)
        attempt = self.last(run_id)
        self.build(attempt, ['double'], alive=True)
        self.assertTrue(self.auto.advance(run_id))
        live = self.last(run_id)
        self.assertEqual(('running', 1), (live['status'], live['kernel']['units_accepted']))   # live progress, no event
        self.assertEqual([], self.kernel.stops)
        self.clock.advance(121)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual([(attempt['kernel']['pid'], attempt['kernel']['run_dir'])], self.kernel.stops)
        timed = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'TIMEOUT', 1), (timed['status'], timed['failure'], timed['kernel']['units_accepted']))
        self.assertTrue(timed['progress']['new'])                     # a timed-out build that accepted units progressed
        self.assertIn('attempt_timeout', self.names(run_id))
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(timed['kernel']['run_dir'], self.last(run_id)['kernel']['keep_from'])

    def test_cancel_stops_the_build_group_and_ends_the_run(self):
        run_id = self.start()
        self.auto.advance(run_id)
        attempt = self.last(run_id)
        self.auto.control(run_id, 'cancel')
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual([(attempt['kernel']['pid'], attempt['kernel']['run_dir'])], self.kernel.stops)
        run = self.auto.get(run_id)
        self.assertEqual(('cancelled', 'failed', 'CANCELLED'),
                         (run['status'], run['nodes'][0]['attempts'][0]['status'], run['nodes'][0]['attempts'][0]['failure']))

    def test_a_build_that_does_not_stop_keeps_its_slot_until_it_does(self):
        run_id = self.start()
        self.auto.advance(run_id)
        self.kernel.stop_ok = False
        self.auto.control(run_id, 'cancel')
        self.assertTrue(self.auto.advance(run_id))
        attempt = self.last(run_id)
        self.assertEqual(('running', 'the kernel build did not stop'), (attempt['status'], attempt['cancel_failed']))
        self.kernel.stop_ok = True
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('cancelled', self.auto.get(run_id)['status'])

    def test_an_intent_cancelled_before_it_started_never_starts(self):
        run_id = self.start()
        with mock.patch.object(self.kernel, 'checkout', side_effect=Crash()):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        self.auto.control(run_id, 'cancel')
        self.assertFalse(self.make_auto().advance(run_id))
        self.assertEqual([], self.kernel.runs)
        self.assertEqual('cancelled', self.auto.get(run_id)['status'])


class KernelDecomposition(KernelHarness):
    def test_a_stalled_unit_is_split_into_a_refined_child_sheet_that_keeps_the_parents_units(self):
        run_id = self.stall()
        planner = self.last(run_id)
        builds = self.attempts(run_id, 'n0')[:2]
        self.assertEqual(('planner', 'split', 'next', 'next(x)', builds[1]['kernel']['run_dir']),
                         (planner['kind'], planner['kernel']['mode'], planner['kernel']['unit'], planner['kernel']['heading'],
                          planner['kernel']['from_run']))
        self.assertNotIn('checkout', planner['kernel'])                # a planner writes no file
        asked = self.kernel.compiled[-1]
        self.assertEqual(('split', 'next', STOPPED), (asked['mode'], asked['unit'], asked['error']))
        program = self.kernel.runs[-1]['program']
        self.assertIn('ask split_unit: ' + K.planner_type(3) + ' ', program)       # a typed answer, not free text
        self.assertIn('let taken = ["double", "ready", "next", "smallName"].', program)
        self.assertIn('ensure ' + K.SPLIT_CHECK + ' else retry because', program)
        self.answer(planner, TYPED_SPLIT)
        self.assertTrue(self.auto.advance(run_id))
        self.assertTrue(self.auto.advance(run_id))
        parent = self.node(run_id, 'n0')
        self.assertEqual(('split', ['n0.0'], planner['id']), (parent['status'], parent['children'], parent['winner']))
        child = self.node(run_id, 'n0.0')
        refined = SP.parse(child['statement'])
        self.assertEqual(['double', 'ready', 'plusOne', 'twiceThenOne', 'next'], [u['names'][0] for u in refined['units']])
        self.assertEqual(['double', 'plusOne', 'twiceThenOne'], refined['units'][4]['uses'])
        self.assertEqual((['double'], [['plusOne(3)', '4'], ['plusOne(-1)', '0']], 'twiceThenOne(x)'),
                         (refined['units'][2]['uses'], refined['units'][2]['examples'], refined['units'][3]['heading']))
        self.assertEqual([['next(3)', '7'], ['next(-2)', '-3']], refined['units'][4]['examples'])   # the integration check
        self.assertTrue(child['statement'].startswith(SHEET[:SHEET.index('## Unit `next(x)`')]))
        self.assertTrue(child['statement'].endswith(SHEET[SHEET.index('## Assemble'):]))
        self.assertEqual((True, 1, builds[1]['kernel']['run_dir']), (child['sheet'], child['depth'], child['keep_from']))
        build = self.last(run_id, 'n0.0')
        self.assertEqual((builds[1]['kernel']['run_dir'], 5), (build['kernel']['keep_from'], build['kernel']['units_total']))
        self.assertEqual(builds[1]['kernel']['run_dir'], self.kernel.compiled[-1]['keep'])
        self.assertEqual(child['statement'], self.kernel.compiled[-1]['sheet'])
        self.build(build, ['double', 'ready', 'plusOne', 'twiceThenOne', 'next'], page=PAGE)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('completed', 'accepted', 'children'), (run['status'], run['nodes'][0]['status'], run['nodes'][0]['winner']))
        self.assertTrue(run['nodes'][0]['parent_verdict']['passed'])
        self.assertEqual(PAGE, (self.project / 'handoff.js').read_text())

    def test_a_split_the_code_refuses_leaves_the_node_stuck(self):
        run_id = self.stall()
        planner = self.last(run_id)
        self.answer(planner, RESTATED)                                  # the stalled unit's own examples again
        self.assertTrue(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[2]
        self.assertEqual('failed', planner['status'])
        self.assertIn('the example `next(3)` does not call nextPart', planner['verdict']['checks'][0]['output'])
        node = self.node(run_id, 'n0')
        self.assertTrue(node['split_refused'])
        self.build(self.last(run_id), ['double', 'ready'])              # the last untried strategy: a fresh build
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('stuck', run['status'])
        self.assertIn('every novel action at this subdivision was tried', run['error'])
        self.assertEqual([], run['nodes'][0]['children'])

    def test_a_sheet_whose_units_all_pass_is_never_split(self):
        check = 'node test.js'
        run_id = self.start(until_done=True, novelty_limit=1, checks={'0': [check]})
        self.results[check] = {'rc': 1, 'out': 'expected 7'}
        self.auto.advance(run_id)
        for _ in range(8):
            if self.auto.get(run_id)['status'] != 'active':
                break
            attempt = self.running(run_id)
            if attempt is not None:
                self.build(attempt, ['double', 'ready', 'next'], page=PAGE)
            self.auto.advance(run_id)
        run = self.auto.get(run_id)
        self.assertEqual('stuck', run['status'])
        refused = [a for a in run['nodes'][0]['attempts'] if a['kind'] == 'planner']
        self.assertEqual(1, len(refused))
        self.assertEqual(('failed', 'REFUSAL'), (refused[0]['status'], refused[0]['failure']))
        self.assertIn('no unit is left to split', refused[0]['error'])
        self.assertTrue(run['nodes'][0]['split_impossible'])
        self.assertEqual(['build'] * 3, [c['mode'] for c in self.kernel.compiled])   # no split ask was compiled
        self.assertEqual(3, len(self.kernel.runs))                    # nor run

    def test_a_promotion_conflict_ends_the_node_instead_of_overwriting_the_operators_edit(self):
        run_id = self.start(until_done=True)
        self.auto.advance(run_id)
        attempt = self.last(run_id)
        (self.project / 'handoff.js').write_text('// the operator wrote this meanwhile\n')
        self.build(attempt, ['double', 'ready', 'next'], page=PAGE)
        self.assertTrue(self.auto.advance(run_id))                     # accepted, then the apply clashes
        self.assertEqual('CONFLICT', self.last(run_id)['failure'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('stuck', run['status'])
        self.assertEqual('CONFLICT', run['nodes'][0]['attempts'][0]['failure'])
        self.assertIn('the built file was not applied and stays in ' + attempt['kernel']['checkout']['worktree'], run['error'])
        self.assertEqual('// the operator wrote this meanwhile\n', (self.project / 'handoff.js').read_text())
        self.assertEqual(1, len(self.kernel.runs))                     # no conflict retry rebuilt it


class KernelPlacement(KernelHarness):
    """Builds and planners run only where the model is installed: the model inventory (kernel_lane.model_nodes)
    narrows the rotation after submit and at resume, and a node an attempt found without the model leaves the
    rotation without the attempt counting as a try."""
    FLEET = [HOST, 'node01', 'node04', 'node09']

    def setUp(self):
        super().setUp()
        self.fleet(*self.FLEET)

    def fleet(self, *names):
        self.tasks.set_nodes(*names)

    def test_the_rotation_holds_only_the_nodes_that_have_the_model(self):
        self.kernel.inventory = {'have': ['node01', 'node09'], 'answered': ['node01', 'node04', 'node09', 'nodepi']}
        run = self.auto.submit(self.sheet_body())['run']
        # the request never waits on the inventory: every node but the coordinating machine, narrowed later
        self.assertEqual((['node01', 'node04', 'node09'], []), (run['policy']['nodes'], self.kernel.inventory_reads))
        self.auto.advance(run['id'])
        self.assertEqual(['node01', 'node09'], self.auto.get(run['id'])['policy']['nodes'])   # node04 lacks the model
        self.assertIn('catalogue_refreshed', self.names(run['id']))
        self.auto.advance(run['id'])
        self.assertEqual(['qwen3:4b-instruct'], self.kernel.inventory_reads)               # once per run
        # a cached inventory never vetoes the operator's own node: the launch there is the fresh check
        other = self.auto.submit({**self.sheet_body('sheet-2'), 'node': 'node04'})['run']
        self.auto.advance(other['id'])
        self.assertEqual('node04', self.last(other['id'])['node'])
        self.kernel.inventory = None                                           # unreadable: every online node
        third = self.auto.submit(self.sheet_body('sheet-3'))['run']['id']
        self.auto.advance(third)
        self.assertEqual(['node01', 'node04', 'node09'], self.auto.get(third)['policy']['nodes'])

    def test_a_build_on_a_node_without_the_model_is_not_a_try_and_moves_the_statement(self):
        run_id = self.start()                                                  # bounded: one candidate, two regenerations
        self.auto.advance(run_id)
        first = self.last(run_id)
        self.absent(first, 'node09')
        self.assertTrue(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        absent = run['nodes'][0]['attempts'][0]
        self.assertEqual(('failed', 'INFRASTRUCTURE', True), (absent['status'], absent['failure'], absent['placement_absent']))
        self.assertNotIn('progress', absent)                                   # it never ran
        self.assertEqual((['node09'], ['node01', 'node04'], 'node01'),
                         (run['model_absent'], run['policy']['nodes'], run['nodes'][0]['node']))
        again = self.last(run_id)
        self.assertEqual(('candidate', 'fresh', 'node01', ['ollama:qwen3:4b-instruct@node01']),
                         (again['kind'], again['strategy'], again['node'], again['kernel']['applicators']))
        self.assertEqual(['submitted', 'decision', 'launch_intent', 'launched', 'model_absent', 'attempt_failed', 'decision',
                          'launch_intent', 'launched'], self.names(run_id))

    def test_a_planner_on_a_node_without_the_model_is_not_a_planner(self):
        run_id = self.stall()
        planner = self.last(run_id)
        self.assertEqual(('planner', 'split', 'node09'), (planner['kind'], planner['strategy'], planner['node']))
        self.absent(planner, 'node09')                         # the model was removed from node09 after the builds
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertTrue(node['attempts'][2]['placement_absent'])
        self.assertFalse(node.get('split_refused'))
        again = self.last(run_id)
        # still the first split (the stall rule), now where the model is; not a re-plan and not stuck
        self.assertEqual(('planner', 'split', 'node01', ['ollama:qwen3:4b-instruct@node01']),
                         (again['kind'], again['strategy'], again['node'], again['kernel']['applicators']))

    def test_with_no_node_left_the_statement_ends_and_a_resume_uses_the_inventory(self):
        self.fleet('orchestrator', 'node09')
        run_id = self.start(until_done=True)
        self.auto.advance(run_id)
        self.absent(self.last(run_id), 'node09')
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('stuck', run['status'])
        self.assertIn('qwen3:4b-instruct is not installed on any node this run may use (missing on node09)', run['error'])
        self.assertEqual(1, len(self.kernel.runs))                             # nothing started where it cannot run
        self.fleet('orchestrator', 'node01', 'node09')
        self.kernel.inventory = {'have': ['node01', 'node09'], 'answered': ['node01', 'node09']}   # node09: stale
        self.auto.control(run_id, 'resume')
        self.assertEqual(['node01'], self.auto.get(run_id)['policy']['nodes'])
        self.assertTrue(self.auto.advance(run_id))
        again = self.last(run_id)
        self.assertEqual(('candidate', 'node01'), (again['kind'], again['node']))


class RealKernel:
    """The real module with only its process functions replaced: real programs, keep through
    symblic.spec.sheets.accepted_units, the real git checkout, install and 3-way apply."""

    def __init__(self):
        self.runs, self.pids, self.live = [], {}, set()

    def __getattr__(self, name):
        return getattr(K, name)

    run = FakeKernel.run
    alive = FakeKernel.alive

    @property
    def next_pid(self):
        return 5000 + len(self.runs)

    @next_pid.setter
    def next_pid(self, value):
        pass

    def stop(self, pid, run_dir='', grace=0):
        self.live.discard(pid)
        return True


class KernelIntegration(KernelHarness):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.project / '.git')
        Path(self.project, 'README.md').write_text('project\n')
        for argv in (['git', 'init', '-q'], ['git', 'add', '-A'],
                     ['git', '-c', 'user.name=test', '-c', 'user.email=test@localhost', 'commit', '-q', '-m', 'base']):
            subprocess.run(argv, cwd=self.project, check=True, capture_output=True)
        self.kernel = RealKernel()
        self.auto = self.make_auto()

    def asked(self, attempt, codes, page=None):
        """A build that asked its units: trace rows carry each answer's fingerprint and calls.jsonl the replies,
        as tools/symblic run writes them, so symblic.spec.sheets.accepted_units can read the accepted code back."""
        from symblic.kernel import language as S
        run_dir = Path(attempt['kernel']['run_dir'])
        run_dir.mkdir(parents=True, exist_ok=True)
        rows, calls = [], []
        for i, (var, code) in enumerate(codes.items()):
            rows.append({'kind': 'ask', 'status': 'ok', 'name': var, 'line': 10 + i, 'hash': S.fingerprint(code)})
            calls.append({'key': f'k{i}', 'at': i, 'stmt': var, 'reply': {'ok': True, 'text': '```js\n' + code + '\n```'}})
        Path(run_dir, 'program.sym').write_text(self.kernel.runs[-1]['program'])
        Path(run_dir, 'trace.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        Path(run_dir, 'calls.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in calls))
        state = ({'status': 'done', 'calls': len(calls), 'outputs': [{'label': 'handoff.js', 'value': page}]} if page is not None
                 else {'status': 'failed', 'calls': len(calls), 'error': {'kind': 'check', 'message': STOPPED}})
        Path(run_dir, 'state.json').write_text(json.dumps(state))
        self.kernel.live.discard(attempt['kernel']['pid'])

    def test_keep_checkout_and_promotion_run_through_the_real_module(self):
        K._STATUS_CACHE.clear()
        run_id = self.start()
        self.auto.advance(run_id)
        first = self.last(run_id)
        wt = first['kernel']['checkout']['worktree']
        self.assertTrue(first['kernel']['checkout']['branch'].startswith('autogen/autogen-'))
        self.assertTrue(os.path.isdir(os.path.join(wt, '.git')) or os.path.isfile(os.path.join(wt, '.git')))
        double, ready = 'function double(x) { return 2 * x; }', 'function ready() { return "ready"; }'
        self.asked(first, {'unit_double': double, 'unit_ready': ready})
        self.assertTrue(self.auto.advance(run_id))
        second = self.last(run_id)
        self.assertEqual(first['kernel']['run_dir'], second['kernel']['keep_from'])
        program = self.kernel.runs[-1]['program']
        self.assertIn('let unit_double = """function double(x) {{ return 2 * x; }}""".', program)   # kept, re-tested
        self.assertIn('let unit_ready = ', program)
        self.assertIn('ask unit_next: Code js', program)                                            # asked again
        self.asked(second, {'unit_next': 'function next(x) { return double(x) + 1; }'}, page=PAGE)
        K._STATUS_CACHE.clear()
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(PAGE, (self.project / 'handoff.js').read_text())       # applied, not committed there
        log = subprocess.run(['git', 'log', '--format=%s', '-1'], cwd=second['kernel']['checkout']['worktree'],
                             capture_output=True, text=True).stdout.strip()
        self.assertIn('kernel build n0-a1', log)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=self.project, capture_output=True, text=True).stdout
        self.assertIn('handoff.js', status)


class KernelSurface(unittest.TestCase):
    def test_the_fake_and_the_module_offer_every_name_the_coordinator_uses(self):
        import re
        source = (Path(__file__).resolve().parents[2] / 'symblic' / 'autogen' / 'coordinator.py').read_text()
        used = set(re.findall(r'self\.kernel\.([A-Za-z_][A-Za-z0-9_]*)', source))
        self.assertGreater(len(used), 15)
        self.assertEqual(set(), {name for name in used if not hasattr(K, name)})
        self.assertEqual(set(), {name for name in used if not hasattr(FakeKernel, name)})


class KernelModule(unittest.TestCase):
    """The real module: pure helpers, the run-folder parser, compiled programs and split validation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autogen-kernel-')
        self.addCleanup(self.tmp.cleanup)
        K._STATUS_CACHE.clear()

    def test_applicators_are_local_models_on_a_cluster_node_only(self):
        self.assertEqual(APP, K.applicator('qwen3:4b-instruct', 'node09'))
        for model, node, why in (('gpt-oss:120b-cloud', 'node09', 'not a local Ollama model'),
                                 ('glm-4.6:cloud', 'node09', 'not a local Ollama model'),
                                 ('qwen3:4b@node01', 'node09', 'not a local Ollama model'),
                                 ('', 'node09', 'not a local Ollama model'),
                                 ('qwen3:4b-instruct', 'node 9', 'is not a node name'),
                                 ('qwen3:4b-instruct', 'Node9', 'is not a node name')):
            with self.subTest(model=model, node=node):
                with self.assertRaises(K.KernelError) as caught:
                    K.applicator(model, node)
                self.assertIn(why, str(caught.exception))
        with self.assertRaises(K.KernelError) as caught:
            K.applicator('qwen3:4b-instruct', HOST, HOST)               # the coordinating machine never runs a model
        self.assertIn('is the coordinating machine', str(caught.exception))
        self.assertEqual(f'ollama:qwen3:4b-instruct@{HOST}', K.applicator('qwen3:4b-instruct', HOST))   # no rule given
        with self.assertRaises(K.KernelError):
            K.check_applicators(['claude:haiku'])

    def test_status_reads_accepted_units_and_the_assembled_page(self):
        run_dir = Path(self.tmp.name, 'run')
        run_dir.mkdir()
        rows = [{'kind': 'let', 'status': 'ok', 'name': 'unit_double'}, {'kind': 'let', 'status': 'ok', 'name': 'test_double'},
                {'kind': 'assert', 'status': 'ok'},
                {'kind': 'let', 'status': 'ok', 'name': 'unit_ready'}, {'kind': 'assert', 'status': 'failed'},
                {'kind': 'ask', 'status': 'ok', 'name': 'unit_next'}, {'kind': 'ensure', 'status': 'retry'},
                {'kind': 'ask', 'status': 'ok', 'name': 'unit_next'}, {'kind': 'ensure', 'status': 'ok'},
                {'kind': 'route-attempt', 'status': 'rejected'}, {'kind': 'let', 'status': 'ok', 'name': 'page'}]
        (run_dir / 'trace.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows) + 'not json\n')
        self.assertEqual({'done': False, 'status': 'starting', 'units': 2}, {k: v for k, v in K.status(run_dir).items()
                                                                           if k in ('done', 'status', 'units')})
        (run_dir / 'state.json').write_text(json.dumps({'status': 'done', 'calls': 7, 'outputs': [
            {'label': 'handoff.js', 'value': PAGE}, {'label': 'other', 'value': 'x'}]}))
        st = K.status(run_dir, label='handoff.js')
        self.assertEqual((True, 'done', ['unit_double', 'unit_next'], PAGE, 7),
                         (st['done'], st['status'], st['accepted'], st['page'], st['calls']))
        self.assertEqual({'name': 'ready', 'var': 'unit_ready', 'heading': 'ready()'}, K.stalled_unit(SHEET, st['accepted']))
        self.assertIsNone(K.stalled_unit(SHEET, ['unit_double', 'unit_ready', 'unit_next']))

    def test_compile_keeps_what_an_earlier_build_accepted_and_seeds_each_attempt(self):
        from symblic.kernel import language as S
        earlier = Path(self.tmp.name, 'earlier')
        earlier.mkdir()
        program = SP.compile_sheet(SHEET, [APP], samples=2, retries=2, rounds=1,
                                   keep={'unit_double': 'function double(x) { return 2 * x; }'}, keep_from='run x')
        (earlier / 'program.sym').write_text(program)
        line = next(i for i, text in enumerate(program.split('\n'), 1) if text.startswith('assert test_double.passed'))
        (earlier / 'trace.jsonl').write_text(json.dumps({'kind': 'assert', 'status': 'ok', 'line': line}) + '\n')
        built = K.compile(SHEET, [APP], keep_folder=str(earlier), seed=42)
        self.assertIn('let unit_double = """function double(x) {{ return 2 * x; }}""".', built)   # braces escaped
        self.assertIn('ask unit_ready: Code js', built)
        self.assertIn(', seed=42, context=none.', built)
        self.assertIn('kept from an earlier build (run earlier)', built)
        self.assertTrue(S.check(built)['ok'])
        self.assertNotIn('seed=', K.compile(SHEET, [APP]))
        with self.assertRaises(K.KernelError):
            K.compile(SHEET, ['claude:haiku'])

    def test_the_split_program_is_one_typed_checked_ask(self):
        from symblic.kernel import language as S
        program = K.split_program(SHEET, 'next', [APP], seed=9, error=STOPPED)
        check = S.check(program)
        self.assertTrue(check['ok'], check['errors'])
        self.assertTrue(K._uses_only(program, [APP]))
        self.assertIn('THE UNIT: `next(x)`', program)
        self.assertIn('next(3) ==> 7', program)
        self.assertIn('What went wrong when it was tried: unit_next: no search candidate', program)
        self.assertIn('show split_unit as "split".', program)
        # the schema the local route sends as Ollama's `format`: the reply cannot leave this shape
        ask = next(st for st in S.parse(program)['statements'] if st.k == 'ask')
        answer = S.answer_schema(ask.type, True)['properties']['answer']
        unit = answer['items']
        self.assertEqual(('array', 2, 3), (answer['type'], answer['minItems'], answer['maxItems']))
        self.assertEqual((['name', 'args', 'contract', 'examples'], False), (unit['required'], unit['additionalProperties']))
        examples = unit['properties']['examples']
        self.assertEqual((2, 6, {'type': 'string'}), (examples['minItems'], examples['maxItems'],
                                                       examples['items']['properties']['expect']))   # never the empty schema
        self.assertIn('ensure ' + K.SPLIT_CHECK + ' else retry because', program)

    def test_the_typed_check_runs_in_the_kernel_before_any_code(self):
        from symblic.kernel import run as SR

        def unit(name, calls):
            return {'name': name, 'args': 'x', 'contract': 'Return one.', 'examples': [{'call': c, 'expect': 1} for c in calls]}
        cases = {'valid': ([unit('plusOne', ['plusOne(3)', 'plusOne(0)']), unit('half', ['half(2)', 'half(4)'])], 'done'),
                 'restated': ([unit('plusOne', ['next(3)', 'next(0)']), unit('half', ['half(2)', 'half(4)'])], 'failed'),
                 'taken': ([unit('double', ['double(3)', 'double(0)']), unit('half', ['half(2)', 'half(4)'])], 'failed'),
                 'twice': ([unit('half', ['half(2)', 'half(4)']), unit('half', ['half(1)', 'half(3)'])], 'failed'),
                 'not a name': ([unit('plus one', ['plus one(3)', 'plus one(0)']), unit('half', ['half(2)', 'half(4)'])], 'failed'),
                 'echo': ([unit('smallName', ['smallName(1)', 'smallName(0)']), unit('half', ['half(2)', 'half(4)'])], 'failed')}
        for label, (answer, want) in cases.items():
            with self.subTest(label=label):
                literal = json.dumps(answer).replace('"name":', 'name:').replace('"args":', 'args:') \
                    .replace('"contract":', 'contract:').replace('"examples":', 'examples:').replace('"call":', 'call:') \
                    .replace('"expect":', 'expect:')
                source = (f'program T.\nlet split_unit = {literal}.\nlet taken = ["double", "ready", "next", "smallName"].\n'
                          f'assert {K.SPLIT_CHECK} because "refused".\nshow 1.\n')
                self.assertEqual(want, SR.Run(source, {}, None, {}).execute()['status'])

    def test_a_typed_answer_becomes_sheet_units_with_exact_values(self):
        from fractions import Fraction
        answer = [{'name': 'plusOne', 'args': '(x)', 'contract': 'Return x plus one.\n## not a heading',
                   'examples': [{'call': 'plusOne(3)', 'expect': ' 4 '}, {'call': 'plusOne( -1 )', 'expect': '0.50'},
                                {'call': 'plusOne(1)', 'expect': Fraction(1, 2)}]},
                  {'name': 'label', 'args': 'n', 'contract': 'Return the label of n.',
                   'examples': [{'call': 'label(1)', 'expect': 'ready'}, {'call': 'label(2)', 'expect': '[[0, 1], {"a": null}]'},
                                {'call': 'label(3)', 'expect': '"set"'}, {'call': 'label(4)', 'expect': "'go'"}]}]
        refined, errors = K.split_sheet(SHEET, 'next', answer, js=ok_js)
        self.assertEqual([], errors)
        units = SP.parse(refined)['units']
        self.assertEqual(['plusOne(x)', 'label(n)'], [u['heading'] for u in units[2:4]])
        self.assertEqual([['plusOne(3)', '4'], ['plusOne( -1 )', '0.50'], ['plusOne(1)', '0.5']], units[2]['examples'])
        self.assertEqual([['label(1)', '"ready"'], ['label(2)', '[[0,1],{"a":null}]'], ['label(3)', '"set"'],
                          ['label(4)', '"go"']], units[3]['examples'])
        self.assertEqual('Return x plus one. ## not a heading', units[2]['body'])      # one line: no new section
        self.assertEqual(['double'], units[2]['uses'])                  # what the stalled unit could call
        as_text, errors = K.split_sheet(SHEET, 'next', json.dumps(TYPED_SPLIT), js=ok_js)   # the answer's JSON text
        self.assertEqual(([], K.split_sheet(SHEET, 'next', TYPED_SPLIT, js=ok_js)[0]), (errors, as_text))
        for bad, why in ((RESTATED, 'the example `next(3)` does not call nextPart'),
                         ([{**TYPED_SPLIT[0], 'name': 'plus one'}, TYPED_SPLIT[1]], "'plus one' is not a JavaScript function name"),
                         ([{**TYPED_SPLIT[0], 'examples': [{'call': 'plusOne(3)'}, {'call': 'plusOne(1)', 'expect': 2}]},
                           TYPED_SPLIT[1]], 'an example needs a call and the value it returns'),
                         ([{**TYPED_SPLIT[0], 'name': 'smallName'}, TYPED_SPLIT[1]], "smallName is the answer format's example"),
                         ('not a list', 'unit section'),
                         ([TYPED_SPLIT[0]], 'the answer has 1 unit section(s)')):
            with self.subTest(why=why):
                refined, errors = K.split_sheet(SHEET, 'next', bad, js=ok_js)
                self.assertIsNone(refined)
                self.assertTrue(any(why in e for e in errors), errors)

    def test_status_decodes_a_typed_answer_exactly(self):
        run_dir = Path(self.tmp.name, 'split')
        run_dir.mkdir()
        (run_dir / 'state.json').write_text(json.dumps({'status': 'done', 'outputs': [{
            'label': 'split', 'value': [{'expect': '0.5'}, {'expect': '0.5'}, {'##key': 1}],
            'canonical': [{'expect': {'#q': '1/2'}}, {'expect': '0.5'}, {'###key': 1}]}]}))
        answer = K.status(run_dir, label='split')['outputs']['split']
        self.assertEqual(['0.5', '"0.5"', '{"##key":1}'], [K.json_text(x.get('expect', x)) for x in answer])
        self.assertEqual('0.3333333333333333', K.json_text(__import__('fractions').Fraction(1, 3)))

    def test_model_nodes_lists_the_nodes_that_hold_the_model(self):
        rows = [{'node': 'node01', 'model': 'qwen3:4b-instruct'}, {'node': 'node04', 'model': 'phi4-mini:latest'},
                {'node': 'node09', 'model': 'qwen3:4b-instruct'}, {'node': 'nodepi', 'model': 'qwen3:4b-instruct'},
                {'node': 'orchestrator', 'model': 'qwen3:4b-instruct'}, {'node': 'node06', 'model': 'qwen3:4b-instruct'}]
        found = K.model_nodes('qwen3:4b-instruct', HOST, rows=rows, fits=lambda row: row['node'] != 'node06')
        self.assertEqual({'have': ['node01', 'node09', 'nodepi'], 'answered': ['node01', 'node04', 'node06', 'node09', 'nodepi', HOST]},
                         found)                                      # the coordinating machine and a model too big are not places
        self.assertEqual(['node04'], K.model_nodes('phi4-mini', rows=rows)['have'])       # an untagged name is :latest
        self.assertIsNone(K.model_nodes('qwen3:4b-instruct'))          # never the live cluster under tests
        self.assertIsNone(K.model_nodes('qwen3:4b-instruct', rows=[]))
        self.assertEqual('nodepi', K.absent_node('ollama@nodepi: unavailable: qwen2.5-coder:3b is not installed on nodepi; x'))
        self.assertEqual('', K.absent_node('ollama@node01: unavailable: no capacity'))

    def test_split_sheet_normalizes_the_answer_and_keeps_every_other_byte(self):
        refined, errors = K.split_sheet(SHEET, 'next', SPLIT_REPLY, js=ok_js)
        self.assertEqual([], errors)
        cut = SHEET.index('## Unit `next(x)`')
        self.assertTrue(refined.startswith(SHEET[:cut]))
        self.assertTrue(refined.endswith(SHEET[SHEET.index('## Assemble'):]))
        units = SP.parse(refined)['units']
        self.assertEqual([['plusOne(3)', '4'], ['plusOne(-1)', '0']], units[2]['examples'])
        self.assertEqual('Return plusOne(double(x)).', units[3]['body'])        # chatter after the fence is dropped
        self.assertIn('Build it by calling `plusOne(x)`, `twiceThenOne(x)`', units[4]['body'])
        self.assertTrue(units[4]['body'].startswith('Return double(x) plus one.'))   # its contract comes first
        self.assertEqual([], SP.problems(SP.parse(refined)))

    def test_split_sheet_refuses_what_code_cannot_check(self):
        one = '## Unit `plusOne(x)`\nReturn x plus one.\nExamples:\n    plusOne(3) ==> 4\n    plusOne(0) ==> 1\n'
        unit = '## Unit `{h}`\n{body}\nExamples:\n{ex}\n'

        def reply(*units):
            return '\n'.join(unit.format(h=h, body=b, ex='\n'.join('    ' + e for e in ex)) for h, b, ex in units)
        good = ('plusOne(x)', 'Return x plus one.', ['plusOne(3) ==> 4', 'plusOne(0) ==> 1'])
        cases = [
            (one, 'the answer has 1 unit section(s)'),
            (reply(good, ('double(x)', 'Again.', ['double(1) ==> 2', 'double(2) ==> 4'])), 'the name double is already defined'),
            (reply(good, ('smallName(a, b)', 'Adds.', ['smallName(1, 2) ==> 3', 'smallName(0, 0) ==> 0'])),
             "smallName is the answer format's example"),
            (reply(good, ('half(x)', 'Halves.', ['plusOne(2) ==> 3', 'half(2) ==> 1'])), 'does not call half'),
            (reply(good, ('half(x)', 'Halves.', ['half(2) ==> 1'])), 'at least 2 are needed'),
            (reply(good, ('half(x)', 'Uses: `next`\nHalves.', ['half(2) ==> 1', 'half(4) ==> 2'])),
             'Uses names next, which no unit above it defines'),
            (reply(good, ('half(x)', 'Halves.', ['half(2) ==> one', 'half(4) ==> 2'])), 'is not JSON'),
        ]
        for text, why in cases:
            with self.subTest(why=why):
                refined, errors = K.split_sheet(SHEET, 'next', text, js=ok_js)
                self.assertIsNone(refined)
                self.assertTrue(any(why in e for e in errors), errors)
        broken = lambda pieces, calls: [{'ok': False, 'kind': 'syntax', 'error': 'SyntaxError: Unexpected token'} for _ in calls]
        refined, errors = K.split_sheet(SHEET, 'next', reply(good, ('half(x)', 'Halves.', ['half(2) ==> 1', 'half(4) ==> 2'])),
                                        js=broken)
        self.assertIsNone(refined)
        self.assertIn('does not run as JavaScript', errors[0])

    @unittest.skipUnless(__import__('importlib').import_module('symblic.js.check').available(), 'needs node and Landlock for the sandboxed js check')
    def test_examples_run_as_javascript_in_the_sandbox(self):
        sheet = SHEET
        good = ('## Unit `plusOne(x)`\nReturn x plus one.\nExamples:\n    plusOne(3) ==> 4\n    plusOne(double(1)) ==> 3\n'
                '## Unit `half(x)`\nHalves.\nExamples:\n    half(2) ==> 1\n    half(4) ==> 2\n')
        refined, errors = K.split_sheet(sheet, 'next', good)
        self.assertEqual([], errors)
        bad = good.replace('half(4) ==> 2', 'half((4) ==> 2').replace('half(2) ==> 1', 'half(missing) ==> 1')
        refined, errors = K.split_sheet(sheet, 'next', bad)
        self.assertIsNone(refined)
        self.assertTrue(any('does not run as JavaScript' in e for e in errors), errors)
        self.assertTrue(any('uses a name no unit or test setup defines' in e for e in errors), errors)

    def test_a_test_never_starts_the_real_build(self):
        program = K.compile(SHEET, [APP])
        with self.assertRaises(K.KernelError) as caught:
            K.run(program, os.path.join(self.tmp.name, 'kernel', 'autogen-' + 'a' * 24, 'n0-a0'), [APP])
        self.assertIn('not started under tests', str(caught.exception))
        with self.assertRaises(K.KernelError):
            K.run(program.replace(APP, 'ollama:qwen3:4b-instruct@node01'), os.path.join(self.tmp.name, 'x'), [APP])


class KernelProcess(unittest.TestCase):
    """The real run/alive/stop against a harmless stand-in for tools/symblic (a shell script that sleeps)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autogen-kernel-proc-')
        self.addCleanup(self.tmp.cleanup)
        stand_in = Path(self.tmp.name, 'symblic')
        stand_in.write_text('#!/bin/sh\ndir=""\nwhile [ $# -gt 0 ]; do [ "$1" = "--dir" ] && dir="$2"; shift; done\n'
                            'mkdir -p "$dir"\nsleep 60 &\necho $! > "$dir/child.pid"\n'
                            'printf \'{"status": "running"}\' > "$dir/state.json"\nwait\n')
        stand_in.chmod(0o755)
        patcher = mock.patch.object(K, 'BIN_SYMBLIC', stand_in)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.run_dir = os.path.join(self.tmp.name, 'kernel', 'autogen-' + 'b' * 24, 'n0-a0')
        self.program = 'program P.\nuse by=["' + APP + '"], context=none.\nshow 1 as "x".\n'

    def wait_for(self, predicate, seconds=10):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.05)
        return predicate()

    def test_the_build_writes_its_pid_is_adopted_and_stops_as_a_group(self):
        pid = K.run(self.program, self.run_dir, [APP])
        self.addCleanup(lambda: K.stop(pid, self.run_dir, grace=1))
        child_file = Path(self.run_dir, 'child.pid')
        self.assertTrue(self.wait_for(child_file.exists))
        self.assertEqual(str(pid), Path(self.run_dir + '.pid').read_text().strip())   # written by the process itself
        self.assertEqual(self.program, Path(self.run_dir + '.sym').read_text())
        self.assertEqual(pid, K.run(self.program, self.run_dir, [APP]))   # adopted: never a second build
        self.assertTrue(K.alive(pid, self.run_dir))
        self.assertFalse(K.alive(os.getpid(), self.run_dir))          # a live process that is not this build
        self.assertEqual(('running', False), (K.status(self.run_dir)['status'], K.status(self.run_dir)['done']))
        child = int(child_file.read_text())
        self.assertTrue(K.stop(pid, self.run_dir, grace=3))
        self.assertFalse(K.alive(pid, self.run_dir))

        def gone():
            try:
                state = Path(f'/proc/{child}/stat').read_bytes().rsplit(b')', 1)[-1].split()[0]
                return state == b'Z'
            except OSError:
                return True
        self.assertTrue(self.wait_for(gone), 'the build\'s own child outlived the group stop')
        self.assertTrue(K.stop(pid, self.run_dir))                    # stopping a stopped build is a no-op

    def test_a_different_program_for_the_same_folder_is_refused(self):
        os.makedirs(os.path.dirname(self.run_dir), exist_ok=True)
        Path(self.run_dir + '.sym').write_text('program Other.\n')
        with self.assertRaises(K.KernelError) as caught:
            K.run(self.program, self.run_dir, [APP])
        self.assertIn('a different program was already written', str(caught.exception))


class KernelCheckout(unittest.TestCase):
    """The real checkout and 3-way apply (git_checkouts) through the kernel lane, on a temporary repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autogen-kernel-git-')
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name, 'project')
        self.repo.mkdir()
        Path(self.repo, 'README.md').write_text('project\n')
        for argv in (['git', 'init', '-q'], ['git', 'add', '-A'],
                     ['git', '-c', 'user.name=test', '-c', 'user.email=test@localhost', 'commit', '-q', '-m', 'base']):
            subprocess.run(argv, cwd=self.repo, check=True, capture_output=True)

    def test_a_build_checkout_is_adopted_by_name_and_promoted_by_the_3_way_apply(self):
        info = K.checkout(str(self.repo), 'autogen-0123456789ab-n0-a0')
        self.assertTrue(info['branch'].startswith('autogen/autogen-0123456789ab-n0-a0-'))
        self.assertTrue(info['worktree'].startswith(str(self.repo) + '.autogen/autogen-0123456789ab-n0-a0-'))
        again = K.checkout(str(self.repo), 'autogen-0123456789ab-n0-a0')    # a crash before the record: adopted
        self.assertEqual((info['worktree'], info['branch'], True), (again['worktree'], again['branch'], again['adopted']))
        self.assertIsNone(K.file_sha256(info['cwd'], 'handoff.js'))
        K.install(info['cwd'], 'handoff.js', PAGE)
        with self.assertRaises(K.KernelError):
            K.install(info['cwd'], '../escape.js', PAGE)
        applied = K.promote(again, 'autogen: kernel build n0-a0')
        self.assertEqual(['handoff.js'], applied['files'])
        self.assertEqual(PAGE, Path(self.repo, 'handoff.js').read_text())
        second = K.checkout(str(self.repo), 'autogen-0123456789ab-n0-a1')
        K.install(second['cwd'], 'handoff.js', PAGE + '\n// rebuilt\n')
        Path(self.repo, 'handoff.js').write_text('// the operator edited it meanwhile\n')
        with self.assertRaises(Exception) as caught:
            K.promote(second, 'autogen: kernel build n0-a1')
        self.assertIn('clash', str(caught.exception))
        self.assertEqual('// the operator edited it meanwhile\n', Path(self.repo, 'handoff.js').read_text())


class PolicyUnits(unittest.TestCase):
    def test_accepted_units_are_a_progress_axis_only_when_measured(self):
        self.assertNotIn('units', POLICY.progress_metrics(None))
        metrics = POLICY.progress_metrics(None, units=3)
        self.assertEqual({'files': [], 'checks': 0, 'done': 0, 'units': 3}, metrics)
        self.assertTrue(POLICY.is_progress({'units': 2}, metrics))
        self.assertFalse(POLICY.is_progress({'units': 3}, metrics))
        self.assertEqual(3, POLICY.merge_progress({'units': 2}, metrics)['units'])
        self.assertNotIn('units', POLICY.merge_progress({'files': ['a.js']}, {'files': [], 'checks': 1}))

    def test_an_attempt_whose_node_lacked_the_model_is_never_counted(self):
        policy = POLICY.normalize({'until_done': True, 'novelty_limit': 1, 'strategies': ['other_node'], 'regenerate': 0},
                                  engines=['local'], nodes=['node01', 'node04'])
        budget = {'agents_started': 2, 'agents_max': 0, 'deadline': None}
        failed = {'id': 'n0-a0', 'kind': 'candidate', 'strategy': 'fresh', 'status': 'failed', 'failure': 'NO_OUTPUT',
                  'progress': {'new': True}}
        moved = {'id': 'n0-a1', 'kind': 'regen', 'strategy': 'other_node', 'status': 'failed', 'failure': 'INFRASTRUCTURE',
                 'placement_absent': True, 'overrides': {'node': 'node01'}}
        node = {'id': 'n0', 'statement': SHEET, 'depth': 0, 'status': 'pending', 'engine': 'local', 'node': 'node09',
                'attempts': [failed, moved]}
        self.assertEqual(('other_node', {'node': 'node01'}), POLICY.next_strategy(node, policy, ['NO_OUTPUT']))  # quota kept
        self.assertEqual(0, POLICY.stale_count(node))
        self.assertTrue(POLICY.recent_progress(node))
        planner = {'id': 'n0-a2', 'kind': 'planner', 'strategy': 'split', 'status': 'failed', 'failure': 'INFRASTRUCTURE',
                   'placement_absent': True, 'engine': 'local', 'node': 'node04'}
        stalled = {'id': 'n0-a1', 'kind': 'regen', 'strategy': 'other_node', 'status': 'failed', 'failure': 'NO_OUTPUT',
                   'progress': {'new': False}}
        node['attempts'] = [failed, stalled, planner]
        decision = POLICY.decide(node, policy, budget, 0)
        self.assertEqual(('decompose', None), (decision['action'], decision.get('replan')))   # a first split again

    def test_a_node_with_nothing_to_split_is_never_decomposed(self):
        policy = POLICY.normalize({'until_done': True, 'novelty_limit': 1}, engines=['local'], nodes=['node09'])
        node = {'id': 'n0', 'statement': SHEET, 'depth': 0, 'status': 'pending', 'engine': 'local', 'node': 'node09',
                'attempts': [{'id': 'n0-a0', 'kind': 'candidate', 'strategy': 'fresh', 'status': 'failed',
                              'failure': 'CHECK_FAILURE', 'progress': {'new': False}}]}
        self.assertEqual('decompose', POLICY.decide(node, policy, {'agents_started': 1, 'agents_max': 0, 'deadline': None}, 0)['action'])
        node['split_impossible'] = True
        self.assertNotEqual('decompose', POLICY.decide(node, policy, {'agents_started': 1, 'agents_max': 0, 'deadline': None}, 0)['action'])


if __name__ == '__main__':
    unittest.main()

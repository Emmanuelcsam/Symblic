"""Autogen v2 over the original host's task engine (HOST-ONLY engine, fake hub): until_done (no clock or
count caps), stall-driven subdivision, worker self-splits, the test designer, split-remaining after
stalled handoffs, re-planning on another placement, the stuck state with resume, and the perpetual dedup
index with saturation. Every store is temporary; the hub, the check runner and the clock are fakes (see
tests/integration/test_symblicos_autogen_hub_lane.py). The sandboxed-check tests that need no hub are in
tests/autogen/test_sandboxed_checks.py.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .
"""
import json
import os
import unittest

from symblic.autogen import policy as POLICY
from symblic.autogen.coordinator import AutogenError
from tests.integration.test_symblicos_autogen_hub_lane import Harness
from tests.integration import test_symblicos_autogen_hub_lane as hub_lane


class UntilDone(Harness):
    NAMES = [f'part{i}.py' for i in range(1, 9)]

    def big(self):
        return 'Create the files ' + ', '.join(self.NAMES) + f' and app.py in the folder {self.cwd} with one function each.'

    def test_one_agent_per_line_regenerates_without_caps_while_it_makes_progress(self):
        run_id = self.submit([self.big()], until_done=True, candidates=1, strategies=['feedback', 'fresh'])
        row = self.auto._read(run_id)
        self.assertEqual({'agents_started': 0, 'agents_max': 0, 'deadline': None}, row['budget'])
        self.assertEqual(self.auto.POLL_SECONDS, self.auto._sleep_seconds(row))
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(1, len(self.attempts(run_id, 'n0')))          # one agent per line
        failing = len(self.NAMES)                                       # beyond candidates + regenerate (1 + 2)
        for k in range(failing):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.write(self.NAMES[k], 'def f():\n    return 1\n')     # one more named file: measurable progress
            self.write(f'scratch{k}.txt', 'junk\n')                      # unnamed files are activity, not progress
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
            node = self.node(run_id, 'n0')
            seen = node['attempts'][k]
            self.assertEqual(('failed', 'NO_OUTPUT'), (seen['status'], seen['failure']))
            self.assertEqual(self.NAMES[:k + 1], seen['progress']['files'])
            self.assertTrue(seen['progress']['new'])
            self.assertEqual((0, True), (node['stale'], node['progress_recent']))
            self.assertEqual(self.NAMES[:k + 1], node['progress']['files'])
            self.assertEqual('pending', node['status'])
            self.assertEqual('active', self.auto.get(run_id)['status'])
        attempts = self.attempts(run_id, 'n0')
        self.assertEqual(failing + 1, len(attempts))
        self.assertEqual(['fresh', 'feedback'] + ['fresh'] * (failing - 1), [a['strategy'] for a in attempts])
        self.assertEqual(['candidate'] + ['regen'] * failing, [a['kind'] for a in attempts])
        last = attempts[-1]
        self.launch(last)
        for name in self.NAMES:                                         # a fresh checkout holds nothing from failed rivals
            self.write(name, 'def f():\n    return 2\n')
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(last)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('completed', failing + 1), (run['status'], run['budget']['agents_started']))
        self.assertEqual(('accepted', last['id']), (run['nodes'][0]['status'], run['nodes'][0]['winner']))
        self.assertTrue(run['summary']['until_done'])
        self.assertEqual(0, run['summary']['nodes'][0]['stale'])

    def test_junk_files_are_not_progress_so_a_dead_end_still_stalls(self):
        run_id = self.submit([self.big()], until_done=True, candidates=1, novelty_limit=2, strategies=['feedback', 'fresh'])
        self.auto.advance(run_id)
        for k in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.write(f'notes{k}.txt', 'nothing named\n')
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
            self.assertEqual(k + 1, self.node(run_id, 'n0')['stale'])
        self.assertEqual('planner', self.attempts(run_id, 'n0')[-1]['kind'])

    def test_timeouts_and_failed_launches_count_toward_a_stall_and_never_loop_forever(self):
        run_id = self.submit([self.big()], until_done=True, candidates=1, novelty_limit=2, attempt_seconds=120,
                             strategies=['feedback', 'fresh'])
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.launch(first)
        self.write(self.NAMES[0], 'def f():\n    return 1\n')
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))                     # progress: the plain retry stays available
        self.assertTrue(self.node(run_id, 'n0')['progress_recent'])
        for k in range(2):                                              # two hung attempts: a stall
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.clock.advance(121)
            self.assertTrue(self.auto.advance(run_id))
            self.tasks.advance(attempt['task_id'])
            self.assertTrue(self.auto.advance(run_id))
            seen = self.attempts(run_id, 'n0')[k + 1]
            self.assertEqual(('failed', 'TIMEOUT'), (seen['status'], seen['failure']))
        node = self.node(run_id, 'n0')
        self.assertEqual('planner', node['attempts'][-1]['kind'])
        self.assertEqual(2, POLICY.stale_count(node))

        # a machine that refuses every launch: the run ends stuck after a bounded number of tries
        self.hub.error = RuntimeError('node down')
        for _ in range(40):
            if self.auto.get(run_id)['status'] != 'active':
                break
            for attempt in self.attempts(run_id, 'n0'):
                if attempt['status'] == 'running':
                    self.tasks.advance(attempt['task_id'])
            self.auto.advance(run_id)
        run = self.auto.get(run_id)
        self.assertEqual('stuck', run['status'])
        self.assertLess(len(run['nodes'][0]['attempts']), 16)
        self.assertFalse(run['nodes'][0]['progress_recent'])

    def test_zero_caps_need_until_done(self):
        for key in ('agents_max', 'wall_seconds'):
            with self.subTest(key=key):
                with self.assertRaises(AutogenError) as caught:
                    self.auto.submit(self.body([self.statement('app.py')], **{key: 0}))
                self.assertIn('0 means unlimited and needs until_done true', str(caught.exception))


class StallSplit(Harness):
    def parent(self):
        return f'Create the files alpha.py and beta.py in the folder {self.cwd} with one function each.'

    def children(self):
        return [f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.',
                f'Create the file beta.py in the folder {self.cwd} with a function named beta.']

    def test_no_progress_for_novelty_limit_attempts_splits_the_statement(self):
        run_id = self.submit([self.parent()], until_done=True, candidates=1, novelty_limit=2,
                             strategies=['feedback', 'fresh'])
        self.auto.advance(run_id)
        for k in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.finish(attempt)                                        # wrote nothing: no progress
            self.assertTrue(self.auto.advance(run_id))
            self.assertEqual(k + 1, self.node(run_id, 'n0')['stale'])
        node = self.node(run_id, 'n0')
        self.assertEqual(['fresh', 'feedback', 'split'], [a['strategy'] for a in node['attempts']])
        planner = node['attempts'][-1]
        self.assertEqual(('planner', 'running'), (planner['kind'], planner['status']))
        self.assertEqual('no progress in 2 attempts; split the statement', node['decisions'][-1]['reason'])
        self.assertEqual(1, node['planners'])
        policy = self.auto.get(run_id)['policy']
        self.assertEqual(self.loc(POLICY.split_prompt(self.parent(), self.cwd, policy, 0)),
                         self.tasks.get(planner['task_id'])['instruction'])
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('split', ['n0.0', 'n0.1']), (node['status'], node['children']))
        self.assertEqual([], self.hub.actions)
        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.assertTrue(self.auto.advance(run_id))
            attempt = self.attempts(run_id, child_id)[0]
            self.launch(attempt)
            self.write(name, 'def f():\n    return 1\n')
            self.finish(attempt)
            keep = self.auto.advance(run_id)
            self.assertEqual('accepted', self.node(run_id, child_id)['status'])
        self.assertFalse(keep)
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(('accepted', 'children'), (run['nodes'][0]['status'], run['nodes'][0]['winner']))

    def test_a_worker_may_answer_too_big_with_a_split_file(self):
        run_id = self.submit([self.parent()], candidates=1, depth=1)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        instruction = self.tasks.get(attempt['task_id'])['instruction']
        self.assertIn(f'write {POLICY.SPLIT_FILE}', instruction)
        self.launch(attempt)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')   # no partial work
        self.finish(attempt)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        seen = node['attempts'][0]
        self.assertEqual(('planner', 'self_split', 'accepted', True), (seen['kind'], seen['strategy'], seen['status'], seen['self_split']))
        self.assertEqual(self.children(), seen['split'])
        self.assertTrue(seen['verdict']['self_split'])
        self.assertFalse(seen['verdict']['passed'])                     # its own checks failed, as expected
        self.assertEqual(('split', ['n0.0', 'n0.1'], 'n0-a0', 1), (node['status'], node['children'], node['winner'], node['planners']))
        self.assertEqual([], self.hub.actions)                           # nothing promoted
        self.assertEqual(['attempt_self_split', 'attempt_accepted', 'decision', 'node_split'], self.names(run_id)[-4:])
        self.assertEqual([self.children()[0], self.children()[1]],
                         [n['statement'] for n in self.auto.get(run_id)['nodes'][1:]])

    def test_a_self_split_stops_a_running_rival_and_the_run_goes_on(self):
        run_id = self.submit([self.parent()], candidates=2, depth=1)
        self.auto.advance(run_id)
        a0, a1 = self.attempts(run_id, 'n0')
        self.launch(a0)
        agent1 = self.launch(a1)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')
        self.finish(a0)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual('split', node['status'])
        rival = node['attempts'][1]
        self.assertEqual(('failed', 'CANCELLED', 'another candidate was accepted first'), (rival['status'], rival['failure'], rival['error']))
        self.tasks.advance(a1['task_id'])
        self.assertIn(agent1, self.hub.stops)
        self.assertTrue(self.auto.advance(run_id))                     # the children launch; nothing hangs
        self.assertEqual(2, len(self.attempts(run_id, 'n0.0')))         # two candidates each, as the policy says

    def test_a_split_file_inherited_from_the_project_is_not_the_workers_answer(self):
        run_id = self.submit([self.parent()], candidates=1, depth=1)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n', at=self.clock() - 600)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.finish(attempt)                                            # wrote nothing of its own
        self.assertTrue(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('candidate', 'failed', 'NO_OUTPUT'), (seen['kind'], seen['status'], seen['failure']))
        self.assertNotIn('self_split', seen['verdict'])
        self.assertEqual([], self.node(run_id, 'n0')['children'])

    def test_until_done_reopens_a_parent_whose_assembled_result_fails_its_checks(self):
        run_id = self.submit([self.parent()], until_done=True, candidates=1, novelty_limit=2, regenerate=4,
                             strategies=['feedback', 'fresh'], checks={'0': ['grep -q integrated alpha.py']})
        self.results['grep -q integrated alpha.py'] = {'rc': 1, 'out': ''}
        self.auto.advance(run_id)
        for _ in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[-1]
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.assertTrue(self.auto.advance(run_id))
            attempt = self.attempts(run_id, child_id)[0]
            self.launch(attempt)
            self.write(name, 'def f():\n    return 1\n')
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('pending', 1), (node['status'], node['integrations']))
        integration = node['attempts'][-1]
        self.assertEqual(('integration', 'failed', 'CHECK_FAILURE'), (integration['kind'], integration['status'], integration['failure']))
        self.assertIn('parent_reopened', self.names(run_id))
        self.assertNotEqual('failed', self.auto.get(run_id)['status'])
        self.assertEqual('split_done', node['attempts'][2]['status'])   # the old split is history, not a winner
        self.assertTrue(self.auto.advance(run_id))
        regen = self.attempts(run_id, 'n0')[-1]
        self.assertEqual(('regen', 'feedback'), (regen['kind'], regen['strategy']))
        self.assertIn('grep -q integrated alpha.py', self.tasks.get(regen['task_id'])['context_note'])
        self.results['grep -q integrated alpha.py'] = {'rc': 0, 'out': ''}
        self.launch(regen)
        self.write('alpha.py', 'def f():\n    return "integrated"\n')
        self.finish(regen)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])

    def test_a_reopened_parent_split_again_gets_fresh_child_ids(self):
        run_id = self.submit([self.parent()], until_done=True, candidates=1, novelty_limit=2, regenerate=4,
                             strategies=['feedback', 'fresh'], checks={'0': ['grep -q integrated alpha.py']})
        self.results['grep -q integrated alpha.py'] = {'rc': 1, 'out': ''}
        self.auto.advance(run_id)
        for _ in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[-1]
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.assertTrue(self.auto.advance(run_id))
            attempt = self.attempts(run_id, child_id)[0]
            self.launch(attempt)
            self.write(name, 'def f():\n    return 1\n')
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('pending', self.node(run_id, 'n0')['status'])  # reopened: the assembled result failed
        self.assertTrue(self.auto.advance(run_id))
        regen = self.attempts(run_id, 'n0')[-1]
        self.launch(regen)
        self.write(POLICY.SPLIT_FILE, f'Rewrite the file alpha.py in the folder {self.cwd} so that it says integrated keeping every existing part.\n'
                                      f'Rewrite the file beta.py in the folder {self.cwd} so that it imports alpha keeping every existing part.\n')
        self.finish(regen)                                              # the worker answers with a second split
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('split', ['n0.2', 'n0.3']), (node['status'], node['children']))
        ids = [n['id'] for n in self.auto.get(run_id)['nodes']]
        self.assertEqual(len(ids), len(set(ids)))                       # never two nodes with one id
        self.assertTrue(self.auto.advance(run_id))                     # the new children launch
        self.assertEqual(1, len(self.attempts(run_id, 'n0.2')))
        self.assertEqual([], [a for a in self.attempts(run_id, 'n0.0') if a['status'] in ('queued', 'running')])

    def test_a_self_split_at_the_maximum_depth_is_refused(self):
        run_id = self.submit([self.parent()], candidates=1, depth=0)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')
        self.finish(attempt)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        seen = node['attempts'][0]
        self.assertEqual(('candidate', 'failed', 'NO_OUTPUT'), (seen['kind'], seen['status'], seen['failure']))
        self.assertNotIn('self_split', seen['verdict'])
        split = [c for c in seen['verdict']['checks'] if c['kind'] == 'split']
        self.assertEqual(1, len(split))
        self.assertIn('maximum depth', split[0]['output'])
        self.assertEqual(('pending', []), (node['status'], node['children']))

    def test_a_self_split_is_off_when_the_policy_says_so(self):
        run_id = self.submit([self.parent()], candidates=1, depth=1, self_split=False)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertNotIn(POLICY.SPLIT_FILE, self.tasks.get(attempt['task_id'])['instruction'])
        self.launch(attempt)
        self.write(POLICY.SPLIT_FILE, '\n'.join(self.children()) + '\n')
        self.finish(attempt)
        self.assertTrue(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('candidate', 'failed'), (seen['kind'], seen['status']))
        self.assertEqual([], self.node(run_id, 'n0')['children'])


class Designer(Harness):
    SCRIPT = '#!/usr/bin/env bash\nset -e\ntest -f app.py\npython3 -c "import app; assert app.main() == 1"\necho main: pass\n'

    def setUp(self):
        super().setUp()
        self.designed = {'rc': 1, 'out': 'main: expected 1 got 2'}
        self.probe = {'rc': 1, 'out': 'main: app.py missing'}          # discriminating on an empty folder
        self.auto._sandbox = lambda folder, home, extra_files=(): ('none', [], 'bash')   # the fake runner sees bare argv
        self.auto._scope = lambda unit: []
        self.auto._stop_scope = lambda unit: None
        base_runner = self.auto.check_runner

        def runner(argv, cwd, timeout=120, shell=False):
            if not shell and argv and argv[0] == 'bash':
                self.runs.append({'argv': argv, 'cwd': cwd, 'shell': shell, 'timeout': timeout})
                if argv[1] == '-n':
                    return dict(self.parse) if hasattr(self, 'parse') else {'rc': 0, 'out': ''}
                if argv[1].endswith('/' + POLICY.DESIGN_FILE):
                    # the designed check: a throwaway copy of the candidate's files, never its checkout
                    self.assertNotEqual(self.cwd, cwd)
                    self.assertEqual(os.path.dirname(argv[1]), cwd)
                    self.assertTrue(os.path.isfile(os.path.join(cwd, 'app.py')))
                    self.assertFalse(os.path.exists(os.path.join(cwd, '.git')))
                    return dict(self.designed)
                self.assertEqual([], os.listdir(cwd))                  # the probe folder is truly empty
                return dict(self.probe)
            return base_runner(argv, cwd, timeout, shell)
        self.auto.check_runner = runner

    def test_the_designed_test_gates_candidates_and_its_output_feeds_back(self):
        statement = self.statement('app.py')
        run_id = self.submit([statement], designer=True, candidates=1)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertTrue(node['needs_design'])
        designer = node['attempts'][0]
        self.assertEqual(('designer', 'design', 'running'), (designer['kind'], designer['strategy'], designer['status']))
        self.assertEqual('write a discriminating test before any candidate (test designer)', node['decisions'][-1]['reason'])
        policy = self.auto.get(run_id)['policy']
        task = self.tasks.get(designer['task_id'])
        self.assertEqual(self.loc(POLICY.designer_prompt(statement, self.cwd, policy)), task['instruction'])
        self.assertNotIn(POLICY.SPLIT_FILE, task['instruction'])          # no worker suffix
        self.launch(designer)
        self.write(POLICY.DESIGN_FILE, self.SCRIPT)
        self.finish(designer)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        designer = node['attempts'][0]
        self.assertEqual('design_done', designer['status'])
        self.assertEqual([('design', True)], [(c['kind'], c['passed']) for c in designer['verdict']['checks']])
        self.assertEqual((self.SCRIPT, False), (node['designed'], node['needs_design']))
        self.assertNotIn('progress', designer)
        self.assertIn('design_done', self.names(run_id))
        probes = [r for r in self.runs if r['argv'][0] == 'bash']
        self.assertEqual(['-n', None], [r['argv'][1] if r['argv'][1] == '-n' else None for r in probes])
        self.assertNotEqual(self.cwd, probes[1]['cwd'])                 # the probe ran in an empty folder
        self.assertFalse(os.path.exists(probes[1]['cwd']))              # which was removed afterwards

        candidate = node['attempts'][1]
        self.assertEqual(('candidate', 'fresh'), (candidate['kind'], candidate['strategy']))
        self.launch(candidate)
        self.write('app.py', 'def main():\n    return 2\n')
        self.finish(candidate)
        self.assertTrue(self.auto.advance(run_id))
        candidate = self.attempts(run_id, 'n0')[1]
        self.assertEqual(('failed', 'CHECK_FAILURE'), (candidate['status'], candidate['failure']))
        self.assertEqual([('exists', True), ('syntax', True), ('designed', False)],
                         [(c['kind'], c['passed']) for c in candidate['verdict']['checks']])
        self.assertEqual(POLICY.DESIGN_FILE, candidate['verdict']['checks'][-1]['file'])
        designed_runs = [r for r in self.runs if r['argv'][0] == 'bash' and r['argv'][1].endswith('/' + POLICY.DESIGN_FILE)]
        self.assertEqual(1, len(designed_runs))
        self.assertFalse(os.path.exists(designed_runs[0]['cwd']))       # the throwaway copy is removed
        regen = self.attempts(run_id, 'n0')[2]
        self.assertEqual(('regen', 'feedback'), (regen['kind'], regen['strategy']))
        self.assertIn('designed AUTOGEN-TESTS.sh: main: expected 1 got 2', self.tasks.get(regen['task_id'])['context_note'])

        self.designed = {'rc': 0, 'out': 'main: pass'}
        self.launch(regen)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(regen)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('completed', 'n0-a2'), (run['status'], run['nodes'][0]['winner']))
        self.assertEqual([('exists', True), ('syntax', True), ('designed', True)],
                         [(c['kind'], c['passed']) for c in run['nodes'][0]['attempts'][2]['verdict']['checks']])

    def test_a_script_that_passes_on_an_empty_folder_is_refused_and_candidates_proceed(self):
        run_id = self.submit([self.statement('app.py')], designer=True, candidates=1)
        self.auto.advance(run_id)
        designer = self.attempts(run_id, 'n0')[0]
        self.launch(designer)
        self.write(POLICY.DESIGN_FILE, '#!/usr/bin/env bash\nexit 0\n')
        self.finish(designer)
        empty_probe = self.auto.check_runner

        def passing_probe(argv, cwd, timeout=120, shell=False):
            if not shell and argv and argv[0] == 'bash' and argv[1] != '-n':
                return {'rc': 0, 'out': ''}
            return empty_probe(argv, cwd, timeout, shell)
        self.auto.check_runner = passing_probe
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        designer = node['attempts'][0]
        self.assertEqual(('failed', 'CHECK_FAILURE'), (designer['status'], designer['failure']))
        self.assertIn('passes on an empty folder', designer['error'])
        self.assertEqual(('', False), (node['designed'], node['needs_design']))
        self.assertIn('design_failed', self.names(run_id))
        candidate = node['attempts'][1]
        self.assertEqual(('candidate', 'running'), (candidate['kind'], candidate['status']))
        self.launch(candidate)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(candidate)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(['exists', 'syntax'], [c['kind'] for c in run['nodes'][0]['attempts'][1]['verdict']['checks']])

    def test_a_probe_that_times_out_or_cannot_run_is_not_discriminating(self):
        for rc, out, text in ((124, 'check timed out after 120s', 'did not run to a verdict'),
                              (127, 'bash: foo: not found', 'did not run to a verdict'),
                              (125, 'landlock: refusing to run unsandboxed', 'did not run to a verdict')):
            with self.subTest(rc=rc):
                self.probe = {'rc': rc, 'out': out}
                run_id = self.submit([self.statement('app.py')], f'probe-{rc}', designer=True, candidates=1)
                self.auto.advance(run_id)
                designer = self.attempts(run_id, 'n0')[0]
                self.launch(designer)
                self.write(POLICY.DESIGN_FILE, self.SCRIPT)
                self.finish(designer)
                self.assertTrue(self.auto.advance(run_id))
                designer = self.attempts(run_id, 'n0')[0]
                self.assertEqual('failed', designer['status'])
                self.assertIn(text, designer['error'])
                self.assertEqual('', self.node(run_id, 'n0')['designed'])

    def test_a_designed_test_that_alone_blocks_two_candidates_is_retired(self):
        run_id = self.submit([self.statement('app.py')], designer=True, candidates=1, regenerate=4, strategies=['feedback', 'fresh'])
        self.auto.advance(run_id)
        designer = self.attempts(run_id, 'n0')[0]
        self.launch(designer)
        self.write(POLICY.DESIGN_FILE, self.SCRIPT)
        self.finish(designer)
        self.assertTrue(self.auto.advance(run_id))
        for k in range(2):
            candidate = self.attempts(run_id, 'n0')[-1]
            self.launch(candidate)
            self.write('app.py', f'def main():\n    return {k + 2}\n')
            self.finish(candidate)
            self.assertTrue(self.auto.advance(run_id))
            seen = self.attempts(run_id, 'n0')[k + 1]
            self.assertEqual([('exists', True), ('syntax', True), ('designed', False)],
                             [(c['kind'], c['passed']) for c in seen['verdict']['checks']])
        node = self.node(run_id, 'n0')
        self.assertEqual(('', self.SCRIPT, 2), (node['designed'], node['designed_retired'], node['designed_only']))
        self.assertIn('design_retired', self.names(run_id))
        third = node['attempts'][-1]
        self.launch(third)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(third)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(['exists', 'syntax'], [c['kind'] for c in run['nodes'][0]['attempts'][-1]['verdict']['checks']])

    def test_a_sandbox_refusal_fails_the_designed_check_visibly(self):
        run_id = self.submit([self.statement('app.py')], designer=True, candidates=1)
        self.auto.advance(run_id)
        designer = self.attempts(run_id, 'n0')[0]
        self.launch(designer)
        self.write(POLICY.DESIGN_FILE, self.SCRIPT)
        self.finish(designer)
        self.assertTrue(self.auto.advance(run_id))
        self.auto._sandbox = lambda folder, home, extra_files=(): ('landlock', [], 'bash')
        self.designed = {'rc': 125, 'out': 'landlock: refusing to run unsandboxed: no landlock'}
        candidate = self.attempts(run_id, 'n0')[1]
        self.launch(candidate)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(candidate)
        self.assertTrue(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[1]
        designed = seen['verdict']['checks'][-1]
        self.assertEqual(('designed', False, 'landlock'), (designed['kind'], designed['passed'], designed['sandbox']))
        self.assertIn('the sandbox refused to run the designed test', designed['output'])
        self.assertEqual('failed', seen['status'])

    def test_an_unsafe_or_unparsable_script_is_refused(self):
        run_id = self.submit([self.statement('app.py')], designer=True, candidates=1)
        self.auto.advance(run_id)
        designer = self.attempts(run_id, 'n0')[0]
        self.launch(designer)
        self.write(POLICY.DESIGN_FILE, '#!/usr/bin/env bash\ncurl https://example.org\n')
        self.finish(designer)
        self.assertTrue(self.auto.advance(run_id))
        designer = self.attempts(run_id, 'n0')[0]
        self.assertEqual('failed', designer['status'])
        self.assertIn('refused command', designer['error'])
        self.assertEqual([], [r for r in self.runs if r['argv'][0] == 'bash'])   # never executed

        self.parse = {'rc': 2, 'out': 'syntax error near unexpected token'}
        run_id = self.submit([self.statement('app.py')], 'parse-1', designer=True, candidates=1)
        self.auto.advance(run_id)
        designer = self.attempts(run_id, 'n0')[0]
        self.launch(designer)
        self.write(POLICY.DESIGN_FILE, '#!/usr/bin/env bash\nif [ ; then\n')
        self.finish(designer)
        self.assertTrue(self.auto.advance(run_id))
        designer = self.attempts(run_id, 'n0')[0]
        self.assertIn('does not parse', designer['error'])
        self.assertEqual(['-n'], [r['argv'][1] for r in self.runs if r['argv'][0] == 'bash'])   # parsed, never run


class HandoffStall(Harness):
    def test_handoffs_without_progress_split_the_remaining_work(self):
        statement = self.statement('big.py', 'with ten numbered functions')
        run_id = self.submit([statement], until_done=True, candidates=1)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        for generation in range(3):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.assertEqual(generation, attempt['generation'])
            self.launch(attempt)
            self.write('big.py', 'def f1():\n' + f'    pass  # generation {generation}\n')
            self.checkpoint(['f1'], ['f2 to f10'], ['big.py'])          # the same cursor every time
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
            node = self.node(run_id, 'n0')
            seen = node['attempts'][generation]
            self.assertEqual('handoff', seen['status'])
            self.assertEqual(generation == 0, seen['progress']['new'])  # only the first generation adds anything
            self.assertEqual(generation == 0, node['handoff_progress'])
        node = self.node(run_id, 'n0')
        self.assertEqual((2, 0), (node['handoffs'], node['planners'] - 1))
        planner = node['attempts'][-1]
        self.assertEqual(('planner', 'split_remaining', 'n0-a2', 'running'),
                         (planner['kind'], planner['strategy'], planner['from'], planner['status']))
        self.assertEqual('handoffs stopped making progress; split the remaining work', node['decisions'][-1]['reason'])
        policy = self.auto.get(run_id)['policy']
        expected = POLICY.split_remaining_prompt(statement, node['attempts'][2]['checkpoint'], self.cwd, policy, 0)
        self.assertEqual(self.loc(expected), self.tasks.get(planner['task_id'])['instruction'])
        self.assertIn('Earlier workers already completed: f1.', self.tasks.get(planner['task_id'])['instruction'])
        self.launch(planner)
        children = [f'Extend the file big.py in the folder {self.cwd} with the functions f2 to f10 keeping every existing part.',
                    f'Create the file big_test.py in the folder {self.cwd} that imports big and calls f1 to f10.']
        self.write(POLICY.SPLIT_FILE, '\n'.join(children) + '\n')
        self.finish(planner)
        self.assertEqual([], self.hub.actions)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('split', ['n0.0', 'n0.1']), (node['status'], node['children']))
        self.assertEqual(children, [n['statement'] for n in self.auto.get(run_id)['nodes'][1:]])
        last_handoff = node['attempts'][2]                              # its files live in the chain's first checkout
        self.assertEqual([('commit', last_handoff['checkout_agent']), ('apply', last_handoff['checkout_agent'])], self.hub.actions)
        self.assertEqual(node['attempts'][0]['agent_id'], last_handoff['checkout_agent'])
        self.assertTrue(last_handoff['partial_promoted'])
        names = self.names(run_id)
        self.assertLess(names.index('partial_promoted'), names.index('node_split'))

    def test_a_split_of_the_remaining_work_without_an_agent_identity_ends_the_node(self):
        statement = self.statement('big.py', 'with ten numbered functions')
        run_id = self.submit([statement], until_done=True, candidates=1)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        for generation in range(3):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.write('big.py', 'def f1():\n' + f'    pass  # {generation}\n')
            self.checkpoint(['f1'], ['f2 to f10'], ['big.py'])
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[-1]
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE, f'Extend the file big.py in the folder {self.cwd} with the functions f2 to f6 keeping every existing part.\n'
                                      f'Extend the file big.py in the folder {self.cwd} with the functions f7 to f10 keeping every existing part.\n')
        self.finish(planner)
        with self.auto._mutate(run_id) as row:                          # the record lost the chain's identity
            for attempt in row['nodes'][0]['attempts'][:3]:
                attempt['agent_id'] = attempt['checkout_agent'] = ''
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('stuck', run['status'])
        self.assertIn('has no agent identity', run['error'])
        self.assertEqual([], run['nodes'][0]['children'])
        self.assertFalse(self.auto.advance(run_id))                    # no repeat every pass

    def test_a_split_of_the_remaining_work_may_leave_out_finished_files(self):
        statement = f'Create the files done.py and big.py in the folder {self.cwd} with ten numbered functions each.'
        run_id = self.submit([statement], until_done=True, candidates=1)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        for generation in range(3):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.write('done.py', 'def d1():\n    pass\n')
            self.write('big.py', f'def f1():\n    pass  # {generation}\n')
            self.checkpoint(['done.py complete', 'f1'], ['f2 to f10 in big.py'], ['done.py', 'big.py'])
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[-1]
        self.assertEqual('split_remaining', planner['strategy'])
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE, f'Extend the file big.py in the folder {self.cwd} with the functions f2 to f6 keeping every existing part.\n'
                                      f'Extend the file big.py in the folder {self.cwd} with the functions f7 to f10 keeping every existing part.\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual('split', node['status'])                      # done.py was not named: it is already there


class LocalEngine(Harness):
    """A `local` run is the kernel lane (docs/reference/LOCAL-AUTOGEN.md): its one statement is a spec sheet and
    every attempt is a kernel build. Submission only here; the builds are driven with a fake kernel in
    tests/autogen/test_kernel_lane.py (no test ever starts a real build or model)."""
    SHEET = ('# app.js\n\n## Shared\n\nPlain functions.\n\n## Unit `inc(x)`\n\nReturn x plus one.\n\nExamples:\n'
             '    inc(1) ==> 2\n\n## Assemble `app.js`\n\n    /*UNITS*/\n')

    def test_a_local_model_run_is_admitted_only_when_asked_for_and_needs_a_model(self):
        self.hub.ENGINES = ('claude', 'agy', 'local')
        plain = {**self.body([self.statement('app.py')]), 'engine': 'local', 'node': 'node09', 'model': 'qwen3:4b-instruct'}
        with self.assertRaises(AutogenError) as caught:
            self.auto.submit(plain)
        self.assertIn('local attempts take a spec sheet; see docs/reference/SPEC-SHEETS.md', str(caught.exception))
        body = {**plain, 'instruction': self.SHEET, 'sheet': True}
        with self.assertRaises(AutogenError) as caught:
            self.auto.submit({k: v for k, v in body.items() if k != 'model'})
        self.assertIn('needs a model', str(caught.exception))
        run = self.auto.submit(body)['run']
        self.assertEqual(['local'], run['policy']['engines'])           # a sheet never rotates onto a CLI agent
        self.assertEqual(['node09'], run['policy']['nodes'])
        self.assertEqual([self.SHEET], run['lines'])
        self.assertTrue(run['nodes'][0]['sheet'])
        # a CLI-agent run never rotates onto the local model
        other = self.auto.submit({**self.body([self.statement('lib.py')], 'cli-1'), 'engine': 'agy'})['run']
        self.assertNotIn('local', other['policy']['engines'])

    def test_a_local_model_run_never_runs_or_rotates_onto_the_host(self):
        self.hub.ENGINES = ('claude', 'agy', 'local')
        body = {**self.body([self.statement('app.py')]), 'instruction': self.SHEET, 'sheet': True, 'engine': 'local',
                'model': 'qwen3:4b-instruct'}
        with self.assertRaises(AutogenError) as caught:
            self.auto.submit(body)                                      # the default node is orchestrator
        self.assertIn('not on the coordinating machine (orchestrator)', str(caught.exception))
        run = self.auto.submit({**body, 'client_request_id': 'local-2', 'node': 'node09'})['run']
        self.assertEqual(['node09'], run['policy']['nodes'])            # orchestrator is not a rotation target
        self.assertEqual('node09', run['base']['node'])


class Budget(Harness):
    def test_a_spent_budget_at_a_stalled_handoff_ends_the_node_instead_of_looping(self):
        statement = self.statement('big.py', 'with ten numbered functions')
        run_id = self.submit([statement], generations=2, depth=1, agents_max=3, regenerate=0)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        for generation in range(3):                                     # three handoffs fill agents_max
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.write('big.py', 'def f1():\n' + f'    pass  # {generation}\n')
            self.checkpoint(['f1'], ['f2 to f10'], ['big.py'])
            self.finish(attempt)
            keep = self.auto.advance(run_id)
        self.assertFalse(keep)
        run = self.auto.get(run_id)
        self.assertEqual(('failed', 3), (run['status'], run['budget']['agents_started']))
        self.assertIn('budget or deadline exhausted at a handoff', run['error'])
        events = self.names(run_id)
        self.assertNotIn('launch_refused', events)
        for _ in range(3):                                              # idle passes change nothing
            self.assertFalse(self.auto.advance(run_id))
        self.assertEqual(len(events), len(self.names(run_id)))

    def test_a_wave_the_budget_refuses_ends_the_node(self):
        run_id = self.submit([self.statement('app.py'), self.statement('lib.py')], candidates=2, regenerate=0, agents_max=3)
        self.auto.advance(run_id)
        a0, a1 = self.attempts(run_id, 'n0')
        self.launch(a0)
        self.launch(a1)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(a0)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('accepted', self.node(run_id, 'n0')['status'])
        self.assertTrue(self.auto.advance(run_id))                     # n1 wants 2, the budget allows 1: that one runs
        n1 = self.attempts(run_id, 'n1')
        self.assertEqual(1, len(n1))
        self.launch(n1[0])
        self.finish(n1[0])                                              # wrote nothing: NO_OUTPUT, and no budget is left
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('failed', 3), (run['status'], run['budget']['agents_started']))
        self.assertIn('exhausted', run['error'])
        events = len(self.names(run_id))
        self.assertFalse(self.auto.advance(run_id))                    # no idle loop afterwards
        self.assertEqual(events, len(self.names(run_id)))


class Stuck(Harness):
    def exhaust(self, run_id):
        """Two no-output attempts (feedback is the only strategy), then a planner that writes nothing."""
        self.auto.advance(run_id)
        for _ in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[-1]
        self.assertEqual('planner', planner['kind'])
        self.launch(planner)
        self.finish(planner)
        return planner

    def test_nothing_novel_left_is_stuck_not_failed_and_resume_starts_a_new_rotation(self):
        self.hub.ENGINES = ('claude',)
        self.hub.fleet_nodes = lambda refresh=False: [{'id': 'orchestrator', 'label': 'orchestrator', 'online': True}]
        run_id = self.submit([self.statement('app.py')], until_done=True, candidates=1, strategies=['feedback'])
        self.exhaust(run_id)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        node = run['nodes'][0]
        self.assertEqual(('stuck', 'stuck'), (run['status'], node['status']))
        self.assertTrue(run['error'].startswith('Statement n0 is stuck: no eligible strategy remains: NO_OUTPUT, NO_OUTPUT; '
                                                'the split was refused; every novel action at this subdivision was tried'))
        self.assertIn('resume after changing the statement, the checks or the catalogue', run['error'])
        self.assertEqual(['attempt_failed', 'decision', 'node_stuck'], self.names(run_id)[-3:])
        self.assertEqual('stuck', run['summary']['status'])
        self.assertTrue(run['summary']['until_done'])
        self.assertTrue(node['split_refused'])
        self.assertEqual(1, len(node['fingerprints']))               # the feedback regeneration (launches carry none)
        self.assertFalse(self.auto.advance(run_id))                     # terminal until the operator resumes
        self.assertEqual(3, len(self.hub.calls))

        del self.hub.fleet_nodes                                        # a machine came online meanwhile
        result = self.auto.control(run_id, 'resume')
        run = result['run']
        node = run['nodes'][0]
        self.assertEqual(('queued', 'pending', 0, 1), (run['status'], node['status'], node['stale'], node['rotations']))
        self.assertEqual(([], 1), (node['fingerprints'], len(node['fingerprints_archive'])))
        self.assertEqual(['orchestrator', 'node09'], run['policy']['nodes'])
        self.assertEqual(['catalogue_refreshed', 'resumed'], self.names(run_id)[-2:])
        self.assertTrue(self.auto.advance(run_id))
        regen = self.attempts(run_id, 'n0')[-1]
        self.assertEqual(('regen', 'feedback', 'running'), (regen['kind'], regen['strategy'], regen['status']))
        self.assertEqual('active', self.auto.get(run_id)['status'])

    def test_a_refused_split_is_replanned_on_an_untried_placement(self):
        run_id = self.submit([self.statement('app.py')], until_done=True, candidates=1, strategies=['feedback'])
        self.exhaust(run_id)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        replan = node['attempts'][-1]
        self.assertEqual(('planner', 'replan', 'node09', 'claude'), (replan['kind'], replan['strategy'], replan['node'], replan['engine']))
        self.assertEqual({'engine': 'claude', 'node': 'node09'}, replan['overrides'])
        self.assertEqual('node09', self.tasks.get(replan['task_id'])['options']['node'])
        self.assertEqual('the split was refused; re-plan with claude@node09', node['decisions'][-1]['reason'])
        self.assertEqual(2, node['planners'])

    def test_a_spent_explicit_cap_needs_an_extension_to_resume(self):
        run_id = self.submit([self.statement('app.py')], until_done=True, candidates=1, regenerate=1, agents_max=2,
                             strategies=['feedback', 'fresh'])
        self.auto.advance(run_id)
        for _ in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.finish(attempt)
            self.auto.advance(run_id)
        run = self.auto.get(run_id)
        self.assertEqual(('stuck', 2), (run['status'], run['budget']['agents_started']))
        self.assertIn('budget or deadline exhausted', run['error'])
        with self.assertRaises(AutogenError) as caught:
            self.auto.control(run_id, 'resume')
        self.assertEqual(409, caught.exception.status)
        self.assertIn('agents_max cap you gave this run is spent', str(caught.exception))
        self.assertEqual('stuck', self.auto.get(run_id)['status'])
        with self.assertRaises(AutogenError):
            self.auto.control(run_id, 'resume', extend={'agents_max': 'many'})
        result = self.auto.control(run_id, 'resume', extend={'agents_max': 0})
        self.assertEqual(('queued', 0, 0), (result['run']['status'], result['run']['budget']['agents_max'], result['run']['policy']['agents_max']))
        self.assertIn('budget_extended', self.names(run_id))
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(3, len(self.attempts(run_id, 'n0')))

    def test_a_refused_extension_leaves_no_event_behind(self):
        run_id = self.submit([self.statement('app.py')], until_done=True, candidates=1, regenerate=1, agents_max=2,
                             strategies=['feedback', 'fresh'])
        self.auto.advance(run_id)
        for _ in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.launch(attempt)
            self.finish(attempt)
            self.auto.advance(run_id)
        self.assertEqual('stuck', self.auto.get(run_id)['status'])
        before = self.names(run_id)
        with self.assertRaises(AutogenError):
            self.auto.control(run_id, 'resume', extend={'wall_seconds': 7200})   # the agents cap is still spent
        self.assertEqual(before, self.names(run_id))
        self.assertEqual(2, self.auto.get(run_id)['budget']['agents_max'])
        self.assertIsNone(self.auto.get(run_id)['budget']['deadline'])     # until_done without a clock cap: unchanged

    def test_cancel_ends_a_stuck_run(self):
        self.hub.ENGINES = ('claude',)
        self.hub.fleet_nodes = lambda refresh=False: [{'id': 'orchestrator', 'label': 'orchestrator', 'online': True}]
        run_id = self.submit([self.statement('app.py')], until_done=True, candidates=1, strategies=['feedback'])
        self.exhaust(run_id)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('stuck', self.auto.get(run_id)['status'])
        self.auto.control(run_id, 'cancel')
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('cancelled', self.auto.get(run_id)['status'])


class DedupIndex(Harness):
    def checkpoint_items(self, done, left, files, items):
        self.write(POLICY.CHECKPOINT_FILE, json.dumps({'version': 1, 'done': done, 'left': left, 'files': files, 'items': items}))

    def index_lines(self):
        path = self.project / POLICY.INDEX_FILE
        rows = []
        for line in path.read_text(errors='replace').splitlines() if path.exists() else []:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get('key'), str) and row.get('run'):
                rows.append(row)
        return rows

    def test_items_are_indexed_once_and_a_saturated_lane_stops(self):
        statement = f'Research the sources about soil microbes in the folder {self.cwd} and append the findings to findings.md for each batch.'
        (self.project / POLICY.INDEX_FILE).write_bytes(b'{"key": []}\nnot json\n\xff\xfe{"key": "text:old"}\n')   # survives bad lines
        run_id = self.submit([statement], perpetual=True, generations=5, interval_seconds=60, saturation=2)
        self.assertTrue(self.auto.advance(run_id))
        first = self.attempts(run_id, 'n0')[0]
        self.assertNotIn('indexed item', self.tasks.get(first['task_id'])['instruction'])
        self.launch(first)
        self.write('findings.md', '# batch 1\n')
        self.checkpoint_items(['batch 1'], ['batch 2'], ['findings.md'],
                              ['https://www.example.org/paper/', 'see 10.1000/abc for details'])
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        first = node['attempts'][0]
        self.assertEqual(('generation_done', 2, 2), (first['status'], first['items_new'], first['items_listed']))
        self.assertEqual((2, 0), (node['items_total'], node['stale_generations']))
        self.assertEqual(['url:example.org/paper', 'doi:10.1000/abc'], node['recent_items'])
        rows = self.index_lines()
        self.assertEqual(['url:example.org/paper', 'doi:10.1000/abc'], [r['key'] for r in rows])
        self.assertEqual([], [e for e in self.events(run_id) if e['event'] in ('index_unreadable', 'index_write_failed')])
        self.assertEqual((run_id, 'n0-a0', 1), (rows[0]['run'], rows[0]['attempt'], rows[0]['generation']))
        indexed = [e for e in self.events(run_id) if e['event'] == 'items_indexed']
        self.assertEqual([(2, 2, 2)], [(e['new'], e['listed'], e['total']) for e in indexed])

        self.clock.advance(60)
        self.assertTrue(self.auto.advance(run_id))
        second = self.attempts(run_id, 'n0')[1]
        instruction = self.tasks.get(second['task_id'])['instruction']
        self.assertIn('already holds 2 indexed item(s)', instruction)
        self.assertIn('Most recent keys: url:example.org/paper, doi:10.1000/abc.', instruction)
        self.launch(second)
        self.write('findings.md', '# batch 1\n# batch 2\n')
        self.checkpoint_items(['batch 1', 'batch 2'], ['batch 3'], ['findings.md'],
                              ['https://example.org/paper#intro', 'DOI 10.1000/ABC'])   # the same two, spelled differently
        self.finish(second)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual((0, 2, 1), (node['attempts'][1]['items_new'], node['items_total'], node['stale_generations']))
        self.assertEqual(2, len(self.index_lines()))

        self.clock.advance(60)
        self.assertTrue(self.auto.advance(run_id))
        third = self.attempts(run_id, 'n0')[2]
        self.launch(third)
        self.write('findings.md', '# batch 1\n# batch 2\n# batch 3\n')
        self.checkpoint_items(['batch 1', 'batch 2', 'batch 3'], ['batch 4'], ['findings.md'], [])
        self.finish(third)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        node = run['nodes'][0]
        self.assertEqual(('completed', 'accepted', 'generations', 3), (run['status'], node['status'], node['winner'], node['generation']))
        self.assertEqual(2, node['stale_generations'])
        self.assertIn('saturated', node['decisions'][-1]['reason'])
        self.assertEqual(2, len(self.index_lines()))
        self.assertEqual(2, run['summary']['nodes'][0]['items_total'])
        self.assertEqual([], run['nodes'][0]['fingerprints'])          # a promoted generation resets the tried set






class GatedRemote(hub_lane.RemoteHarness):
    """A node agent has no native completion adapter: its task gates at once with the agent still
    running. The coordinator drives the task's observation itself, so a host-process restart that
    killed the task's own coordinator never leaves a finished agent unobserved."""

    def test_the_coordinator_observes_a_gated_remote_turn_without_the_task_thread(self):
        run_id = self.auto.submit(self.remote_body(regenerate=0))['run']['id']
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        # no native completion adapter for this placement: the task's own pass gates the line at once
        self.evidence[agent] = {'available': False, 'done': False, 'reason': 'no native completion adapter'}
        self.tasks.advance(attempt['task_id'])                         # the task's own pass: it gates the line and would keep polling
        task = self.tasks.get(attempt['task_id'])
        step = task['steps'][0]
        self.assertEqual(('awaiting_review', True, None), (step['status'], step.get('running'), step.get('evidence')))
        self.assertFalse(step['completion']['available'])
        self.assertTrue(self.auto.advance(run_id))                     # the agent still works: nothing to judge
        self.assertEqual('running', self.attempts(run_id, 'n0')[0]['status'])
        self.give_git(agent)
        self.produced = {'app.py': 'def main():\n    return 1\n'}
        self.diff = 'app.py\0'
        self.hub.turn = 'bash'                                          # the agent's process ended; a shell is left
        # no tasks.advance() here: only the autogen pass runs, as after a restart
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual('accepted', seen['status'])
        task = self.tasks.get(attempt['task_id'])
        self.assertEqual('completed', task['status'])
        self.assertIsNotNone(task['steps'][0].get('evidence'))
        self.assertEqual('completed', self.auto.get(run_id)['status'])


if __name__ == '__main__':
    unittest.main()

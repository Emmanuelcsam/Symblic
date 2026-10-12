"""Policy experiments over agent graphs: run one (policy, case) assignment as a graph and report what happened.

What it is for
    A routing policy (which applicator each graph node may use, symblic.graph.planner) is a natural candidate
    for symblic.policy.store experiments. GraphPolicyRunner(folder, applicators, stop) is the runner such an
    experiment injects: for one assignment it validates the request against its pins (validate_case: the case
    input is a graph plus an output node, effect-free, within the call budget), runs the graph durably with
    symblic.graph.run.GraphRun under the candidate policy, and returns the final output, one attempt row per
    started graph attempt (cost = provider calls) and the schema and predicate check receipts. The store, not
    this runner, compares the output with the expected value; nothing a model returns becomes a score.

    resolve(request) reads an existing assignment without dispatching anything; recover(request) continues an
    interrupted one, refusing whenever a model call or effect may have been issued without a recorded outcome;
    is_recoverable(request) answers that question read-only.

Depends on: symblic.graph (planner, run), symblic.policy (learning, store). Applicators are injected (a fake in
the tests). Used by: the original host's policy routes (integration/host/symblic_policy_api.py). Status:
prototype; tested with fake applicators only (tests/policy).
"""
from __future__ import annotations

import copy
import hashlib
import threading
from pathlib import Path

_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

from symblic.graph import planner as G
from symblic.graph import run as R
from symblic.graph.run import Interrupted
from symblic.policy import learning as P
from symblic.policy import store as E

VERSION = 1
COST_UNIT = 'provider_calls'


def validate_case(input_value, policy, *, budget=None):
    """Pure shape/policy/budget admission; actual runtime pins checked at execution."""
    P.digest(input_value)
    E._fields(input_value, 'graph output_node')
    G.identifier(input_value['output_node'])
    frozen = G.freeze_graph(input_value['graph'], policy)
    if input_value['output_node'] not in {node['id'] for node in frozen['graph']['nodes']}:
        raise E.PolicyStoreError('output_node')
    if any(node['effect_risk'] != 'none' for node in frozen['graph']['nodes']):
        raise E.PolicyStoreError('policy_graph_effects_unsupported')
    # Each started graph attempt reserves at least one call; keeping this cap
    # guarantees every attempt fits the selector's explicit receipt bound.
    if frozen['graph']['max_calls'] > P.MAX_ATTEMPTS:
        raise E.PolicyStoreError('policy_graph_attempt_limit')
    if budget is not None:
        E._fields(budget, 'max_calls max_cost_units')
        for value in budget.values():
            E._integer(value)
        if frozen['graph']['max_calls'] > min(budget.values()):
            raise E.PolicyStoreError('policy_graph_budget')
    return frozen


class GraphPolicyRunner:
    """Injected registered Apps only. resolve() validates journals without dispatch."""

    def __init__(self, folder, applicators, stop=None):
        self.folder = Path(folder)
        self.apps = applicators
        self.stop = threading.Event() if stop is None else stop
        if not callable(getattr(applicators, 'call', None)):
            raise E.PolicyStoreError('applicators')

    def _validate_request(self, request):
        P.digest(request)
        E._fields(request, 'version assignment_id experiment_sha256 stage candidate_sha256 case_hash policy input budget cost_unit')
        if type(request['version']) is not int or request['version'] != E.VERSION:
            raise E.PolicyStoreError('version')
        for key in ('assignment_id', 'experiment_sha256', 'candidate_sha256', 'case_hash'):
            E._sha(request[key])
        if request['stage'] not in ('training', 'heldout') or request['cost_unit'] != COST_UNIT:
            raise E.PolicyStoreError('policy_graph_contract')
        if P.digest(request['policy']) != request['candidate_sha256']:
            raise E.PolicyStoreError('candidate_pin')
        expected = P.digest([request['experiment_sha256'], request['stage'],
                             request['candidate_sha256'], request['case_hash']])
        if request['assignment_id'] != expected:
            raise E.PolicyStoreError('assignment_pin')
        frozen = validate_case(request['input'], request['policy'], budget=request['budget'])
        return frozen

    def _open(self, request, *, existing=False):
        frozen = self._validate_request(request)
        if self.folder.exists() or self.folder.is_symlink():
            E._directory(self.folder)
        root = self.folder / request['assignment_id']
        if existing:
            E._directory(root)
            if E._read(root / 'policy-request.json') != request or not (root / 'runtime' / 'graph-pins.json').is_file():
                raise E.PolicyStoreError('graph_recovery_pin')
        else:
            self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            E._directory(root, create=True)
            E._write_immutable(root / 'policy-request.json', request)
            E._sync_directory(self.folder)
        return R.GraphRun(frozen, root / 'runtime', self.apps, stop=self.stop), frozen

    def _preinitialization(self, request):
        """Only an empty, pre-dispatch prefix may initialize the original journal.

        Missing files do not excuse arbitrary work. Before graph pins exist the
        graph adapter cannot dispatch: only its private lock/artifacts directory
        and uncommitted atomic-write temps are allowed. Existing journals, call
        intents, results, symlinks or unexplained files refuse this recovery.
        """
        self._validate_request(request)
        if self.folder.exists() or self.folder.is_symlink():
            E._directory(self.folder)
        root = self.folder / request['assignment_id']
        if not root.exists() and not root.is_symlink():
            return True
        E._directory(root)
        R._safe_tree(root, R.ROOT_TREE_LIMIT, skip=('runtime',))
        request_path = root / 'policy-request.json'
        runtime = root / 'runtime'
        if request_path.exists() and E._read(request_path) != request:
            raise E.PolicyStoreError('graph_recovery_pin')
        for path in root.iterdir():
            if path.name in ('policy-request.json', 'runtime'):
                continue
            if not (path.is_file() and not path.is_symlink() and path.name.startswith('.pending-')):
                raise E.PolicyStoreError('graph_recovery_unexplained_work')
        if not runtime.exists():
            return True
        E._directory(runtime)
        if (runtime / 'graph-pins.json').exists():
            return False
        R._safe_tree(root, R.ATTEMPT_TREE_LIMIT)
        if not request_path.exists():
            raise E.PolicyStoreError('graph_recovery_pin')
        for path in runtime.iterdir():
            if path.name == '.graph.lock' and path.is_file() and not path.is_symlink():
                continue
            if path.name == 'artifacts' and path.is_dir() and not path.is_symlink():
                E._directory(path)
                if not any(path.iterdir()):
                    continue
            if R._uncommitted(path):
                continue
            raise E.PolicyStoreError('graph_recovery_unexplained_work')
        return True

    def __call__(self, request):
        runner, frozen = self._open(request)
        runner.execute()
        # Re-read and audit the completed journal under its native lock. Avoid
        # taking any accounting or correctness label from model-returned JSON.
        with runner._locked():
            state = runner._prepare()
            if state.get('status') == 'canceled':
                raise E.PolicyStoreError('canceled')
            if self.stop.is_set():
                raise Interrupted('stopped')
            return self._outcome(request, runner, frozen, state)

    def resolve(self, request):
        """Query only: unfinished graph work returns unresolved, with zero calls."""
        runner, frozen = self._open(request, existing=True)
        with runner._locked():
            state = runner._prepare()
            return self._outcome(request, runner, frozen, state)

    def recover(self, request):
        """Continue or safely recover an interrupted assignment on its existing journal."""
        if self._preinitialization(request):
            return self(request)
        runner, frozen = self._open(request, existing=True)
        with runner._locked():
            state = runner._prepare()
            outcome = self._outcome(request, runner, frozen, state)
            if outcome['complete']:
                return outcome
            if state['status'] == 'canceled':
                # Terminal canceled cannot auto reset.
                raise E.PolicyStoreError('canceled')
            states = {(row['iteration'], row['node']): row for row in state['states']}
            for row in runner.rows:
                if row['kind'] != 'started':
                    continue
                native = states.get((row['iteration'], row['node']))
                if not native:
                    continue
                node = runner.nodes[row['node']]
                action = {k: row[k] for k in ('node', 'iteration', 'attempt', 'route')}
                action.update(inputs=native['inputs'], call_limit=node['call_limit'], effect_risk=node['effect_risk'])
                _, _, _, _, calls, unknown_effect, _ = runner._attempt(action, existing=True)
                if calls.uncertain or unknown_effect:
                    raise E.PolicyStoreError('uncertain')
        runner.execute()
        with runner._locked():
            state = runner._prepare()
            if state.get('status') == 'canceled':
                raise E.PolicyStoreError('canceled')
            if self.stop.is_set():
                raise Interrupted('stopped')
            return self._outcome(request, runner, frozen, state)

    def is_recoverable(self, request):
        """Check if an inflight assignment can be safely continued/recovered."""
        try:
            if self._preinitialization(request):
                return True, None
            runner, frozen = self._open(request, existing=True)
            with runner._locked():
                state = runner._prepare()
                if state['status'] == 'canceled':
                    return False, 'graph was canceled'
                outcome = self._outcome(request, runner, frozen, state)
                if outcome['complete']:
                    return True, None
                states = {(row['iteration'], row['node']): row for row in state['states']}
                for row in runner.rows:
                    if row['kind'] != 'started':
                        continue
                    native = states.get((row['iteration'], row['node']))
                    if not native:
                        continue
                    node = runner.nodes[row['node']]
                    action = {k: row[k] for k in ('node', 'iteration', 'attempt', 'route')}
                    action.update(inputs=native['inputs'], call_limit=node['call_limit'], effect_risk=node['effect_risk'])
                    _, _, _, _, calls, unknown_effect, _ = runner._attempt(action, existing=True)
                    if calls.uncertain or unknown_effect:
                        return False, 'unfinished external intent; automatic redispatch refused'
                return True, None
        except Exception as exc:  # noqa: BLE001 - a read-only recovery diagnosis never dispatches
            return False, str(exc)

    def _outcome(self, request, runner, frozen, state):
        attempts = []
        complete = state['status'] in ('succeeded', 'unresolved')
        states = {(row['iteration'], row['node']): row for row in state['states']}
        for row in runner.rows:
            if row['kind'] != 'started':
                continue
            native = states[row['iteration'], row['node']]
            node = runner.nodes[row['node']]
            action = {key: row[key] for key in ('node', 'iteration', 'attempt', 'route')}
            action.update(inputs=native['inputs'], call_limit=node['call_limit'], effect_risk=node['effect_risk'])
            _, _, _, _, calls, effect_unknown, saved = runner._attempt(action, existing=True)
            settled = not calls.uncertain and not effect_unknown and saved is not None
            complete = complete and settled
            count = len(calls.intents)
            kind = saved['result']['kind'] if saved is not None else 'unknown'
            status = 'done' if settled and kind == 'succeeded' else 'failed' if settled else 'uncertain'
            attempts.append({'id': P.digest([request['assignment_id'], calls.context]),
                             'request_sha256': calls.context, 'calls': count, 'cost_units': count,
                             'status': status})
        if len(attempts) > P.MAX_ATTEMPTS:
            raise E.PolicyStoreError('attempts')
        last = frozen['graph']['iterations'] - 1
        final = states[last, request['input']['output_node']]
        envelope = final.get('result')
        output = copy.deepcopy(envelope['value']) if envelope is not None else None
        checks = []
        if envelope is not None:
            subject = P.digest(output)
            scope = next((item for item in envelope['evidence'] if item.get('scope') == 'node_contract'), None)
            if scope is not None:
                checks.append({'scope': 'schema', 'passed': final['status'] == 'succeeded',
                               'subject_sha256': subject, 'checker_sha256': P.digest(scope['schema'])})
                checks.extend({'scope': 'encoded_predicate', 'passed': receipt['passed'],
                               'subject_sha256': subject, 'checker_sha256': receipt['predicate_sha256']}
                              for receipt in scope['predicate_receipts'])
        succeeded = state['status'] == 'succeeded' and final['status'] == 'succeeded'
        return {'status': 'uncertain' if not complete else 'done' if succeeded else 'failed',
                'output': output, 'attempts': attempts, 'checks': checks,
                'complete': complete, 'effects': 'none'}

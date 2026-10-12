"""A parent program that builds a short proof by handing one step at a time to fresh child agents (template `proof_step_obligation`).

What it shows: delegation of proof work to small agents, the same hand-off where each step must discharge an exact obligation (a formula and its scope) that the parent states. The parent rechecks every step a child returns before
it extends the proof, so a wrong or forged answer can never enter it.

    python3 examples/proof_step_obligation_handoff.py        prints {"complete": true, "fake_only": true, "steps": 3}

Running this example makes fake calls only: the "children" are scripted fakes, it imports no model provider and
opens no network connection. To use real models, pass an applicators object (symblic.providers.applicators) to
symblic.delegate.run.run_task where the fake is passed here. Request shapes: examples/*.task.json; template
documentation: symblic/delegate/README.md and docs/reference/PROOF-*.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # the repository root

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W


def checked_child_state(request, result):
    """Recheck only the returned choice and its native receipt before adoption.

    This verifies integrity under the caller's request, not the remote agent's
    identity. Canonical receipt comparison also handles escaped record keys;
    the returned raw native state is safe to give to the next compile_task.
    """
    contract = D.compile_task(request)
    if contract['template'] != 'proof_step_obligation':
        raise ValueError('This helper requires a proof_step_obligation contract.')
    if type(result) is not dict:
        raise ValueError('Child result must be an exact JSON object.')
    # Bound the caller-visible result projection before reading nested fields.
    # D._json rejects cycles, nonfinite values, subclasses and oversized values.
    try:
        D._json({key: result.get(key) for key in
                 ('accepted', 'status', 'contract_id', 'output_encoding', 'result')})
    except D.ContractError as error:
        raise ValueError('Child result is not bounded exact JSON.') from error
    if (result.get('accepted') is not True or result.get('status') != 'done'
            or result.get('contract_id') != contract['contract_id']
            or result.get('output_encoding') != contract['output_encoding']):
        raise ValueError('Child did not return the accepted caller contract.')
    value = result.get('result')
    choice = value.get('choice') if type(value) is dict else None
    commands = contract['inputs']['commands']
    if type(choice) is not int or not 1 <= choice <= len(commands):
        raise ValueError('Child choice is outside the caller menu.')
    command = commands[choice - 1]
    original = contract['inputs']['session']
    obligation = contract['inputs']['obligation']
    receipt = C.append(original['premises'], original['goal'], original, command)
    if not receipt['valid'] or (contract['inputs']['require_complete'] and not receipt['complete']):
        raise ValueError('The selected command does not satisfy the caller contract.')
    if (receipt['line']['formula'] != obligation['formula']
            or receipt['line']['free'] != obligation['open_assumptions']):
        raise ValueError('The selected inference misses the caller formula or assumption scope.')
    if receipt['complete'] and not W.verify(original['premises'], original['goal'], receipt['certificate'])['ok']:
        raise ValueError('The closing certificate did not independently verify.')
    expected = {'choice': choice, 'command': command, 'menu_member': True,
                'inference': receipt, 'handoff': contract['handoff'], 'obligation_satisfied': True}
    # JSON identity is type-sensitive: Python container equality equates True
    # with 1 and False with 0, which cannot establish an unchanged receipt.
    if D._json(value) != D._json(S.canon(S.from_json(expected))):
        raise ValueError('Child command, binding or unchanged native receipt differs.')
    return receipt['state']


class FakeChild:
    def __init__(self, choice):
        self.choice = choice
        self.calls = 0

    def call(self, _request):
        self.calls += 1
        if self.calls > 1:
            raise AssertionError('Example expected exactly one fake call per child.')
        return {'ok': True, 'json': {'answer': self.choice}, 'model': 'fake', 'node': 'isolated'}


def main():
    premises = {'a': ['atom', 'A'], 'ab': ['implies', ['atom', 'A'], ['atom', 'B']]}
    state = R.start(premises, ['atom', 'B'])
    # The parent authored every menu in advance. No helper builds or ranks them.
    steps = [(['premise ab', 'premise a'], 2, '"A"', False),
             (['premise ab', 'and_left s1'], 1, '"A" implies "B"', False),
             (['and_left s1', 'premise a', 'implies_elim s2 s1'], 3, '"B"', True)]
    for commands, fake_choice, formula, require_complete in steps:
        task = {'template': 'proof_step_obligation', 'params': {'session': state, 'commands': commands,
                                                    'require_complete': require_complete,
                                                    'obligation': {'formula': formula}},
                'calls': 1, 'capsule': 'compact'}
        contract = D.compile_task(task)
        task['expected_contract_id'] = contract['contract_id']
        # Each call starts a new native child context; only the explicit state
        # and caller commands cross the handoff. The default route is unchanged.
        result = H.run_task(task, applicators=FakeChild(fake_choice))
        state = checked_child_state(task, result)
    print(json.dumps({'fake_only': True, 'steps': len(state['steps']),
                      'complete': R.frontier(state)['complete']}, sort_keys=True))


if __name__ == '__main__':
    main()

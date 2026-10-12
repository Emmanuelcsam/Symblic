"""Typed canonical child receipts, bounded before parent adoption; fake child only."""
import copy
import importlib.util
from pathlib import Path
import unittest

from symblic.delegate import contracts as D
from symblic.delegate import run as H
from tests.delegate.test_symblic_delegate_proof_step import Fake, request

EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/proof_step_handoff.py'
SPEC = importlib.util.spec_from_file_location('proof_step_handoff_integrity_example', EXAMPLE)
HANDOFF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HANDOFF)


class HandoffReceiptIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = request(calls=1)
        cls.result = H.run_task(cls.task, applicators=Fake([3]))
        if not cls.result['accepted']:
            raise AssertionError(cls.result['error'])

    def test_native_checked_receipt_remains_accepted(self):
        state = HANDOFF.checked_child_state(self.task, self.result)
        self.assertEqual(state, self.result['result']['inference']['state'])

    def test_bool_integer_substitutions_refuse_even_when_python_equates_them(self):
        mutations = [(('menu_member',), 1), (('inference', 'valid'), 1),
                     (('inference', 'complete'), 1), (('handoff', 'require_complete'), 0),
                     (('inference', 'version'), True)]
        for path, new in mutations:
            altered = copy.deepcopy(self.result)
            parent = altered['result']
            for key in path[:-1]:
                parent = parent[key]
            old = parent[path[-1]]
            self.assertEqual(old, new, 'Regression must exercise Python equality collision')
            self.assertIsNot(type(old), type(new))
            parent[path[-1]] = new
            with self.subTest(path=path), self.assertRaises(ValueError):
                HANDOFF.checked_child_state(self.task, altered)

    def test_malformed_nonfinite_cyclic_subclass_and_large_payloads_refuse(self):
        invalid = [None, [], 1, 'result', {}, dict(self.result, result=None),
                   dict(self.result, result=[]), dict(self.result, result={'choice': 3.0})]
        nonfinite = copy.deepcopy(self.result); nonfinite['result']['inference']['checks'] = float('nan')
        invalid.append(nonfinite)
        cyclic = copy.deepcopy(self.result); cyclic['result']['cycle'] = cyclic['result']; invalid.append(cyclic)
        large = copy.deepcopy(self.result); large['result']['extra'] = 'x' * (D.MAX_TEXT + 1); invalid.append(large)
        class ChangedInt(int):
            pass
        subclass = copy.deepcopy(self.result); subclass['result']['choice'] = ChangedInt(3); invalid.append(subclass)
        class ChangedDict(dict):
            def get(self, *_args):
                raise AssertionError('Do not invoke an untrusted subclass getter')
        invalid.append(ChangedDict(self.result))
        for value in invalid:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                HANDOFF.checked_child_state(self.task, value)


if __name__ == '__main__':
    unittest.main()

"""Parent CLI's lazy delegation preserves exact arguments and output stream."""
import io
import json
import unittest
from unittest import mock
from symblic.mica import cli as L
from symblic.mica import forge_cli as F


class ForgeCliDelegationTest(unittest.TestCase):
    def test_exact_delegation_with_no_parent_dispatch(self):
        stream = io.StringIO()
        args = ['forge', 'execute', 'prepared.json', '--dir', '/owner/run',
                '--inventory', 'inventory.json', '--request-id', 'original-request']
        with mock.patch.object(F, 'main', return_value=7) as child, \
             mock.patch.object(L, 'dispatch', side_effect=AssertionError('parent must not dispatch')):
            self.assertEqual(L.main(args, out=stream), 7)
        child.assert_called_once_with(args[1:], out=stream)
        self.assertEqual(stream.getvalue(), '')

    def test_help_exposes_forge_without_store_or_provider(self):
        stream = io.StringIO()
        with mock.patch.object(F, '_store', side_effect=AssertionError('help must be inert')):
            self.assertEqual(L.main(['forge', '--help'], out=stream), 0)
        self.assertIn('prepare', json.loads(stream.getvalue())['commands'])
        self.assertIn('forge', L.COMMANDS)
        self.assertIn('forge', L.parser().format_help())


if __name__ == '__main__':
    unittest.main()

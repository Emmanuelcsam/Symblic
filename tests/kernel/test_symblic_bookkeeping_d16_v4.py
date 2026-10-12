"""D16 v4: iterator exhaustion must never be confused with caller content.

Finite parity/resource regressions; no models, stores, or empirical truth claims.
"""
import unittest

from tests.kernel.test_symblic_bookkeeping_d16 import recursive_json, outcome, nested, traced_peak
from symblic.kernel import epistemic as EP


class IteratorContentParity(unittest.TestCase):
    def assert_parity(self, value):
        self.assertEqual(outcome(EP._json, value), outcome(recursive_json, value))

    def test_internal_sentinel_direct_is_an_unsupported_object(self):
        self.assertEqual(outcome(EP._json, EP._END), (
            'error', 'json', 'Content must be exact JSON (no floats, tuples or custom objects)'))

    def test_internal_sentinel_in_lists_and_dictionary_values(self):
        for value in ([EP._END], [None, EP._END], {'a': EP._END},
                      {'a': 1, 'b': [EP._END]}, [[{'a': EP._END}]]):
            with self.subTest(shape=repr(value)):
                self.assert_parity(value)

    def test_late_invalid_siblings_do_not_replace_the_first_error(self):
        for value in ([EP._END, 1.5], [EP._END, '\ud800'],
                      {'a': EP._END, 'b': '\ud800'}, [[EP._END], [None] * EP.MAX_NODES],
                      {'a': [EP._END], 'b': 'x' * (EP.MAX_BYTES + 1)}):
            with self.subTest(shape=type(value).__name__):
                self.assert_parity(value)
                self.assertEqual(outcome(EP._json, value)[1], 'json')

    def test_earlier_errors_and_limits_keep_their_original_order(self):
        for value in (['\ud800', EP._END], [2**4096, EP._END],
                      [None] * (EP.MAX_NODES - 1) + [EP._END],
                      nested(EP.MAX_DEPTH + 1, EP._END),
                      {'a': '\ud800', 0: EP._END}):
            with self.subTest(shape=type(value).__name__):
                self.assert_parity(value)
        self.assertEqual(outcome(EP._json, {'a': '\ud800', 0: EP._END})[2],
                         'Content must be exact JSON (no floats, tuples or custom objects)')

    def test_last_admissible_node_is_still_content_and_next_node_is_limit(self):
        for prefix in (EP.MAX_NODES - 2, EP.MAX_NODES - 1):
            value = [None] * prefix + [EP._END]
            self.assert_parity(value)
            self.assertEqual(outcome(EP._json, value)[1], 'json' if prefix == EP.MAX_NODES - 2 else 'limit')

    def test_wide_sentinel_inputs_use_depth_bounded_scratch_space(self):
        for value in ([EP._END] + [None] * 100_000,
                      {'first': EP._END, **{str(i): None for i in range(100_000)}},
                      [None] * 100_000 + [EP._END]):
            self.assert_parity(value)
            outcome(EP._json, value)
            self.assertLessEqual(traced_peak(EP._json, value), 16_384)

    def test_empty_containers_shared_aliases_and_subsequent_calls_preserved(self):
        shared = {'unicode': ['日本', 'é', None], 'empty': []}
        value = {'z': [shared, shared], 'a': {}}
        for _ in range(3):
            self.assert_parity(EP._END)
            self.assert_parity(value)
        self.assertIs(value['z'][0], value['z'][1])


if __name__ == '__main__':
    unittest.main()

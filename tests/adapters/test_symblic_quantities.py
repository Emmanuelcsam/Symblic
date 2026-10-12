"""Exact interval quantities: pure values, no stores, providers, workers or clocks."""
import copy
import importlib.util
import random
import unittest
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path

from symblic.adapters import quantities as Q

from symblic.kernel import language as S


def bounds(quantity):
    return quantity['lower'], quantity['upper']


def metadata(ident='ruler', version='reading-1', observed='2026-10-04T12:00:00Z', **fields):
    return {'sources': [{'id': ident, 'version': version, 'observed_at': observed}], **fields}


class Arithmetic(unittest.TestCase):
    def test_exact_conversion_round_trips_and_dimensions(self):
        for unit in ('m', 'cm', 'mm', 'inch', 'ft', 'km'):
            original = Q.quantity_exact(F(1, 3), unit)
            converted = Q.quantity_convert(Q.quantity_convert(original, 'mm'), unit)
            self.assertEqual(bounds(converted), (F(1, 3), F(1, 3)))
        self.assertEqual(bounds(Q.quantity_convert(Q.quantity_exact(1, 'inch'), 'cm')), (F(127, 50),) * 2)
        self.assertEqual(bounds(Q.quantity_convert(Q.quantity_exact(1, 'lb'), 'kg')), (F(45359237, 100000000),) * 2)
        self.assertEqual(Q.quantity_exact(2, 'm')['unit']['dimensions'], (1, 0, 0, 0, 0, 0, 0))

    def test_measurement_tolerance_survives_conversion_in_original_unit(self):
        length = Q.quantity_measure(F(6, 5), F(1, 20), 'm', metadata())
        converted = Q.quantity_convert(length, 'cm')
        self.assertEqual(bounds(converted), (115, 125))
        self.assertEqual(converted['kind'], 'measured_interval')
        self.assertEqual(converted['declared_tolerances'][0]['absolute'], F(1, 20))
        self.assertEqual(converted['declared_tolerances'][0]['unit']['symbol'], 'm')
        self.assertEqual(converted['sources'], length['sources'])

    def test_add_sub_with_distinct_scales(self):
        left, right = Q.quantity_interval(1, 2, 'm'), Q.quantity_interval(20, 30, 'cm')
        self.assertEqual(bounds(Q.quantity_add(left, right)), (F(6, 5), F(23, 10)))
        self.assertEqual(bounds(Q.quantity_sub(left, right)), (F(7, 10), F(9, 5)))
        exact = Q.quantity_add(Q.quantity_exact(2, 'm'), Q.quantity_exact(25, 'cm'))
        self.assertEqual(bounds(exact), (F(9, 4), F(9, 4)))
        self.assertEqual(exact['kind'], 'derived_exact')

    def test_length_plus_mass_and_conversion_are_refused(self):
        length, mass = Q.quantity_exact(1, 'm'), Q.quantity_exact(1, 'kg')
        for operation in (Q.quantity_add, Q.quantity_sub, Q.quantity_compare):
            with self.assertRaisesRegex(Q.QuantityError, 'dimensions'):
                operation(length, mass)
        with self.assertRaisesRegex(Q.QuantityError, 'dimensions'):
            Q.quantity_convert(length, 'kg')

    def test_dimensions_compose_and_cancel(self):
        speed = Q.quantity_div(Q.quantity_interval(90, 110, 'm'), Q.quantity_exact(10, 's'))
        self.assertEqual(bounds(speed), (9, 11))
        self.assertEqual(speed['unit']['dimensions'], (1, 0, -1, 0, 0, 0, 0))
        distance = Q.quantity_mul(speed, Q.quantity_exact(2, 's'))
        self.assertEqual(bounds(distance), (18, 22))
        self.assertEqual(distance['unit']['symbol'], 'm')
        ratio = Q.quantity_div(Q.quantity_exact(1, 'm'), Q.quantity_exact(10, 'cm'))
        self.assertEqual(bounds(ratio), (10, 10))
        self.assertEqual(ratio['unit']['dimensions'], Q.ZERO)

    def test_all_endpoint_sign_combinations_against_independent_reference(self):
        rng = random.Random(73044)
        for _ in range(100):
            al, ah = sorted(F(rng.randint(-20, 20), rng.randint(1, 7)) for _ in range(2))
            bl, bh = sorted(F(rng.randint(-20, 20), rng.randint(1, 7)) for _ in range(2))
            a, b = Q.quantity_interval(al, ah, '1'), Q.quantity_interval(bl, bh, '1')
            expected = [x * y for x in (al, ah) for y in (bl, bh)]
            self.assertEqual(bounds(Q.quantity_mul(a, b)), (min(expected), max(expected)))
            if bl <= 0 <= bh:
                with self.assertRaisesRegex(Q.QuantityError, 'contains zero'):
                    Q.quantity_div(a, b)
            else:
                expected = [x / y for x in (al, ah) for y in (bl, bh)]
                self.assertEqual(bounds(Q.quantity_div(a, b)), (min(expected), max(expected)))
                for x in (al, (al + ah) / 2, ah):
                    for y in (bl, (bl + bh) / 2, bh):
                        self.assertLessEqual(min(expected), x / y)
                        self.assertLessEqual(x / y, max(expected))

    def test_divisor_touching_zero_refused_including_zero_numerator(self):
        for lower, upper in ((-1, 1), (0, 1), (-1, 0), (0, 0)):
            with self.assertRaisesRegex(Q.QuantityError, 'contains zero'):
                Q.quantity_div(Q.quantity_exact(0, 'm'), Q.quantity_interval(lower, upper, 's'))

    def test_same_source_is_not_assumed_independent_or_cancelled(self):
        x = Q.quantity_measure(10, 1, 'm', metadata())
        difference = Q.quantity_sub(x, x)
        self.assertEqual(bounds(difference), (-2, 2))
        self.assertEqual(len(difference['sources']), 1)
        self.assertEqual(len(difference['declared_tolerances']), 1)
        self.assertEqual(difference['provenance']['independence'], 'not_assumed')
        self.assertEqual(Q.quantity_compare(x, x)['shared_sources'], ('ruler',))
        self.assertEqual(Q.quantity_compare(x, x, 'eq')['outcome'], 'indeterminate')
        self.assertEqual(bounds(Q.quantity_div(x, x)), (F(9, 11), F(11, 9)))

    def test_versions_are_retained_and_shared_source_is_detected(self):
        first = Q.quantity_interval(1, 2, 'm', metadata(version='a'))
        second = Q.quantity_interval(2, 3, 'm', metadata(version='b'))
        output = Q.quantity_add(first, second)
        self.assertEqual({r['version'] for r in output['sources']}, {'a', 'b'})
        self.assertEqual(Q.quantity_compare(first, second)['shared_sources'], ('ruler',))

    def test_measurement_with_zero_tolerance_does_not_become_exact_definition(self):
        measured = Q.quantity_measure(1, 0, 'm')
        result = Q.quantity_add(measured, Q.quantity_exact(0, 'm'))
        self.assertEqual(result['kind'], 'derived_interval')

    def test_corrupt_measured_metadata_cannot_be_promoted_to_exact(self):
        measured = Q.quantity_measure(1, 0, 'm')
        measured['kind'] = 'exact_definition'
        with self.assertRaisesRegex(Q.QuantityError, 'measurement tolerance'):
            Q.quantity_convert(measured, 'cm')


class Temperatures(unittest.TestCase):
    def test_exact_temperature_points_and_round_trip(self):
        for celsius in (-40, 0, F(43, 2), 100):
            q = Q.quantity_exact(celsius, 'degC')
            fahrenheit = Q.quantity_convert(q, 'degF')
            self.assertEqual(bounds(fahrenheit), (celsius * F(9, 5) + 32,) * 2)
            self.assertEqual(bounds(Q.quantity_convert(fahrenheit, 'degC')), (celsius,) * 2)
        self.assertEqual(bounds(Q.quantity_convert(Q.quantity_exact(0, 'degC'), 'K')), (F(27315, 100),) * 2)

    def test_point_minus_point_is_delta_without_offset(self):
        output = Q.quantity_sub(Q.quantity_exact(212, 'degF'), Q.quantity_exact(0, 'degC'))
        self.assertEqual(bounds(output), (180, 180))
        self.assertEqual(output['unit']['symbol'], 'delta_degF')
        self.assertEqual(bounds(Q.quantity_convert(output, 'delta_K')), (100, 100))

    def test_point_plus_minus_delta_and_delta_plus_point(self):
        point = Q.quantity_interval(19, 21, 'degC')
        delta = Q.quantity_interval(9, 18, 'delta_degF')
        for output in (Q.quantity_add(point, delta), Q.quantity_add(delta, point)):
            self.assertEqual(bounds(output), (24, 31))
            self.assertEqual(output['unit']['kind'], 'point')
        self.assertEqual(bounds(Q.quantity_sub(point, delta)), (9, 16))

    def test_point_delta_misuse_refused(self):
        point, delta = Q.quantity_exact(10, 'K'), Q.quantity_exact(2, 'delta_K')
        for operation, args in ((Q.quantity_add, (point, point)), (Q.quantity_sub, (delta, point)),
                                (Q.quantity_mul, (point, delta)), (Q.quantity_div, (point, delta)),
                                (Q.quantity_compare, (point, delta)), (Q.quantity_convert, (point, 'delta_K'))):
            with self.subTest(operation=operation.__name__), self.assertRaises(Q.QuantityError):
                operation(*args)

    def test_affine_non_temperature_refused_and_custom_temperature_works(self):
        with self.assertRaisesRegex(Q.QuantityError, 'temperature only'):
            Q.quantity_unit('offset_length', (1, 0, 0, 0, 0, 0, 0), offset=1, kind='point')
        with self.assertRaisesRegex(Q.QuantityError, 'cannot have an offset'):
            Q.quantity_unit('bad_delta', Q.TEMPERATURE, offset=1)
        custom = Q.quantity_unit('custom_temperature', Q.TEMPERATURE, scale=2, offset=5, kind='point')
        out = Q.quantity_sub(Q.quantity_exact(3, custom), Q.quantity_exact(1, custom))
        self.assertEqual(bounds(out), (2, 2))
        self.assertEqual(bounds(Q.quantity_convert(out, 'delta_K')), (4, 4))


class ComparisonAndTime(unittest.TestCase):
    def test_threshold_overlap_and_touching_bounds(self):
        interval = Q.quantity_interval(F(999, 100), F(1001, 100), 'kg')
        threshold = Q.quantity_exact(10, 'kg')
        for relation in ('lt', 'le', 'gt', 'ge', 'eq', 'ne'):
            self.assertEqual(Q.quantity_compare(interval, threshold, relation)['outcome'], 'indeterminate')
        left, right = Q.quantity_interval(1, 2, 'm'), Q.quantity_interval(2, 3, 'm')
        self.assertEqual(Q.quantity_compare(left, right, 'le')['outcome'], 'true')
        self.assertEqual(Q.quantity_compare(left, right, 'lt')['outcome'], 'indeterminate')
        self.assertEqual(Q.quantity_compare(right, left, 'lt')['outcome'], 'false')

    def test_no_rounding_near_threshold(self):
        below = Q.quantity_exact(F(999999999999999999, 10**18), 'm')
        threshold = Q.quantity_exact(100, 'cm')
        self.assertEqual(Q.quantity_compare(below, threshold, 'lt')['outcome'], 'true')
        self.assertEqual(Q.quantity_compare(below, threshold, 'eq')['outcome'], 'false')

    def test_all_relations_at_equal_singletons_and_disjoint_intervals(self):
        left, right = Q.quantity_exact(1, 'm'), Q.quantity_exact(100, 'cm')
        for relation, expected in {'lt': 'false', 'le': 'true', 'gt': 'false', 'ge': 'true', 'eq': 'true', 'ne': 'false'}.items():
            self.assertEqual(Q.quantity_compare(left, right, relation)['outcome'], expected)
        self.assertEqual(Q.quantity_compare(left, Q.quantity_interval(2, 3, 'm'), 'ne')['outcome'], 'true')

    def test_timestamp_boundaries_age_and_expiry_are_caller_supplied(self):
        q = Q.quantity_measure(10, 1, 'm', metadata(valid_from='2026-10-04T12:00:00Z',
                                                  valid_until='2026-10-04T13:00:00Z'))
        self.assertEqual(Q.quantity_status(q, '2026-10-04T11:59:59Z')['validity'], 'not_yet_valid')
        self.assertEqual(Q.quantity_status(q, '2026-10-04T11:59:59Z')['freshness'], 'not_yet_observed')
        end = Q.quantity_status(q, '2026-10-04T13:00:00Z', max_age_seconds=3600)
        self.assertEqual(end['validity'], 'within_declared_window')
        self.assertEqual(end['freshness'], 'within_max_age')
        self.assertEqual(end['observations'][0]['age_seconds'], 3600)
        expired = Q.quantity_status(q, '2026-10-04T13:00:01Z', max_age_seconds=3600)
        self.assertEqual(expired['validity'], 'expired')
        self.assertEqual(expired['freshness'], 'stale')

    def test_unstated_and_partial_observations_do_not_claim_freshness(self):
        no_source = Q.quantity_exact(1, 'm')
        report = Q.quantity_status(no_source, '2026-10-04T12:00:00Z')
        self.assertEqual(report['validity'], 'not_declared')
        self.assertEqual(report['freshness'], 'not_assessed')
        self.assertEqual(Q.quantity_status(no_source, '2026-10-04T12:00:00Z', 100)['freshness'], 'unknown')
        partial = Q.quantity_interval(1, 2, 'm', metadata(observed=None))
        self.assertEqual(Q.quantity_status(partial, '2026-10-04T12:00:00Z', 100)['freshness'], 'unknown')

    def test_validity_intersection_and_disjoint_refusal(self):
        a = Q.quantity_exact(1, 'm', {'valid_from': '2026-10-04T10:00:00Z', 'valid_until': '2026-10-04T12:00:00Z'})
        b = Q.quantity_exact(2, 'm', {'valid_from': '2026-10-04T11:00:00Z', 'valid_until': '2026-10-04T14:00:00Z'})
        combined = Q.quantity_add(a, b)
        self.assertEqual(combined['validity'], {'from': '2026-10-04T11:00:00Z', 'until': '2026-10-04T12:00:00Z'})
        b['validity']['from'] = '2026-10-04T13:00:00Z'
        with self.assertRaisesRegex(Q.QuantityError, 'validity interval is empty'):
            Q.quantity_add(a, b)

    def test_bad_timestamps_and_time_inputs_refused(self):
        for stamp in ('2026-02-30T00:00:00Z', '2026-10-04', '2026-10-04T12:00:00',
                      '2026-10-04T12:00:00+00:00', '2026-10-04T12:00:60Z', True, 42):
            with self.subTest(stamp=stamp), self.assertRaises(Q.QuantityError):
                Q.quantity_exact(1, 'm', {'valid_from': stamp})
        q = Q.quantity_exact(1, 'm')
        for age in (True, 1.0, F(1, 2), -1, 10**20):
            with self.assertRaises(Q.QuantityError):
                Q.quantity_status(q, '2026-10-04T12:00:00Z', age)
        with self.assertRaises(Q.QuantityError):
            Q.quantity_status(q, None)


class BoundsAndIntegration(unittest.TestCase):
    def test_nonexact_numbers_and_numeric_subclasses_refused(self):
        class CustomInt(int):
            pass
        for value in (True, False, 1.0, float('nan'), float('inf'), Decimal('0.1'), '1/3', CustomInt(3)):
            for function in (lambda v: Q.quantity_exact(v, 'm'),
                             lambda v: Q.quantity_interval(0, v, 'm'),
                             lambda v: Q.quantity_measure(1, v, 'm')):
                with self.subTest(value=value), self.assertRaises(Q.QuantityError):
                    function(value)

    def test_extreme_numbers_and_intermediates_refused(self):
        with self.assertRaisesRegex(Q.QuantityError, 'bit budget'):
            Q.quantity_exact(1 << 4096, 'm')
        with self.assertRaisesRegex(Q.QuantityError, 'bit budget'):
            Q.quantity_exact(F(1, 1 << 4096), 'm')
        a, b = Q.quantity_exact(200, '1'), Q.quantity_exact(2, '1')
        with self.assertRaisesRegex(Q.QuantityError, 'intermediate bit budget'):
            Q.quantity_mul(a, b, max_bits=8)
        for limit in (0, True, 1.5, 4097):
            with self.assertRaises(Q.QuantityError):
                Q.quantity_exact(1, 'm', max_bits=limit)

    def test_input_bounds_schema_and_symbol_validation(self):
        for dimensions in ((1,), (True,) + (0,) * 6, (33,) + (0,) * 6, (0.0,) + (0,) * 6):
            with self.assertRaises(Q.QuantityError):
                Q.quantity_unit('custom', dimensions)
        for unit in ('meters', 'ton', 'c', 'M'):
            with self.assertRaisesRegex(Q.QuantityError, 'unknown unit'):
                Q.quantity_exact(1, unit)
        with self.assertRaisesRegex(Q.QuantityError, 'redefined'):
            Q.quantity_unit('m', (0, 1, 0, 0, 0, 0, 0))
        with self.assertRaises(Q.QuantityError):
            Q.quantity_unit('bad', Q.ZERO, scale=0)
        with self.assertRaises(Q.QuantityError):
            Q.quantity_interval(2, 1, 'm')
        with self.assertRaises(Q.QuantityError):
            Q.quantity_measure(1, -1, 'm')
        for value in ('', 'x' * 257, '\ud800', 'unit\nname'):
            with self.assertRaises(Q.QuantityError):
                Q.quantity_unit(value, Q.ZERO)
        q = Q.quantity_exact(1, 'm')
        for field, value in (('extra', 'warning'), ('lower', True), ('kind', ['measured_interval']), ('schema', True)):
            damaged = copy.deepcopy(q)
            damaged[field] = value
            with self.assertRaises(Q.QuantityError):
                Q.quantity_convert(damaged, 'cm')

    def test_source_union_limits_and_detached_records(self):
        rows = [{'id': 'measurement-' + str(i), 'version': '1'} for i in range(Q.MAX_SOURCES)]
        source = {'sources': rows}
        q = Q.quantity_interval(1, 2, 'm', source)
        rows[0]['id'] = 'changed-after-call'
        self.assertNotIn('changed-after-call', {s['id'] for s in q['sources']})
        extra = Q.quantity_interval(1, 2, 'm', metadata('extra'))
        with self.assertRaisesRegex(Q.QuantityError, 'union exceeds'):
            Q.quantity_add(q, extra)
        with self.assertRaises(Q.QuantityError):
            Q.quantity_exact(1, 'm', {'sources': rows + rows[:1]})

    def test_dimension_overflow_refused_before_product(self):
        large = Q.quantity_unit('high_power', (32, 0, 0, 0, 0, 0, 0))
        with self.assertRaisesRegex(Q.QuantityError, 'bounded native integers'):
            Q.quantity_mul(Q.quantity_exact(1, large), Q.quantity_exact(1, 'm'))

    def test_local_and_kernel_budget_exhaustion(self):
        with self.assertRaisesRegex(Q.QuantityError, 'work budget'):
            Q.quantity_exact(1, 'm', max_work=1)
        budget = S.Budget(1)
        with self.assertRaises(S.SymblicError):
            Q.quantity_exact(1, 'm', budget=budget)

    def test_import_inert_registration_idempotent_and_collision_safe(self):
        before = dict(S.BUILTINS)
        spec = importlib.util.spec_from_file_location('isolated_quantity_import', Path(Q.__file__))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(before, S.BUILTINS)
        kernel = S.Kernel()
        self.assertIs(Q.register(kernel), kernel)
        self.assertIs(Q.register(kernel), kernel)
        kernel.functions['quantity_exact'] = lambda *_: 0
        with self.assertRaisesRegex(Q.QuantityError, 'already exists'):
            Q.register(kernel)

    def test_existing_language_kernel_uses_plain_records_and_shared_budget(self):
        kernel = Q.register(S.Kernel())
        expression = S.Parser(S.tokenize('quantity_compare(quantity_measure(1, 1/100, "m"), quantity_exact(100, "cm"), "lt")'), 1).expr()
        before = kernel.budget.left
        result = kernel.eval(expression)
        self.assertEqual(result['outcome'], 'indeterminate')
        self.assertLess(kernel.budget.left, before)

    def test_pending_core_lazy_wrapper_is_compatible_with_registration(self):
        name = 'quantity_exact'
        original = S.BUILTINS.get(name)
        try:
            S.BUILTINS[name] = S._adapter('symblic.adapters.quantities', 'interval quantity', name)
            kernel = Q.register(S.Kernel())
            node = S.Node('call', 1, 1)
            result = S.BUILTINS[name](kernel, node, 1, 'm')
            self.assertEqual(bounds(result), (1, 1))
        finally:
            if original is None:
                S.BUILTINS.pop(name, None)
            else:
                S.BUILTINS[name] = original


if __name__ == '__main__':
    unittest.main()

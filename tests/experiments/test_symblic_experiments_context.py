"""Independent exact reconstruction, budget and forged-scope checks; no services."""
import copy
import hashlib
import json
import unittest

from symblic.experiments import context as C


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(raw(value)).hexdigest()


def seal(envelope):
    envelope['sha256'] = digest({key: value for key, value in envelope.items() if key != 'sha256'})


def fixture(text, intervals, budget, query=()):
    return {'source': {'id': 'source', 'revision': 1,
                       'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'text': text},
            'spans': [{'id': 's' + str(i), 'start': start, 'end': end,
                       'required': required, 'priority': priority}
                      for i, (start, end, required, priority) in enumerate(intervals)],
            'budget_bytes': budget, 'query_terms': list(query), 'merge_fanout': 2}


class Compression(unittest.TestCase):
    def run_case(self, data):
        before = copy.deepcopy(data)
        answer = C.run('extractive-compression', data)
        self.assertEqual(before, data)
        self.assertEqual({'arithmetic', 'results', 'checks', 'limits', 'sources'}, set(answer))
        return answer

    def test_required_exception_survives_when_keyword_baseline_omits_it(self):
        data = C.catalog()[0]['example']
        answer = self.run_case(data)
        result = answer['results']
        self.assertEqual('ok', result['status'])
        self.assertIn('Do not pay until inspection passes.', result['compressed']['text'])
        self.assertNotIn('wall', result['compressed']['text'])
        self.assertEqual([], result['compressed']['missing_required_ids'])
        self.assertEqual(['span2'], result['comparisons']['simple_keyword_retrieval']['missing_required_ids'])
        self.assertLess(result['compressed']['bytes'], result['comparisons']['full_source']['bytes'])
        self.assertEqual('unmeasured', result['token_cost']['status'])
        self.assertTrue(all(answer['checks'].values()))

    def test_refuses_instead_of_dropping_a_mandatory_span(self):
        data = fixture('must keep', [(0, 9, True, 1)], 8)
        result = self.run_case(data)['results']
        self.assertEqual('refused', result['status'])
        self.assertEqual('required_budget', result['reason'])
        self.assertEqual(9, result['minimum_required_bytes'])
        self.assertIsNone(result['compressed'])
        self.assertEqual([], result['hierarchy'])

    def test_unicode_codepoint_spans_and_exact_utf8_cost(self):
        text = 'x🙂éz'
        data = fixture(text, [(1, 3, True, 0)], 6)
        compressed = self.run_case(data)['results']['compressed']
        self.assertEqual('🙂é', compressed['text'])
        self.assertEqual([[1, 3]], compressed['ranges'])
        self.assertEqual(6, compressed['bytes'])
        data['budget_bytes'] = 5
        self.assertEqual('refused', self.run_case(data)['results']['status'])

    def test_overlap_and_adjacency_are_exact_union_not_duplicate_text(self):
        data = fixture('0123456789', [(1, 4, True, 0), (3, 6, True, 0), (6, 8, False, 5)], 7)
        result = self.run_case(data)['results']
        self.assertEqual('1234567', result['compressed']['text'])
        self.assertEqual([[1, 8]], result['compressed']['ranges'])
        self.assertEqual(['s0', 's1', 's2'], result['compressed']['covered_span_ids'])

    def test_hierarchy_reconstructs_source_spans_at_every_level(self):
        data = fixture('A-x-B-y-C', [(0, 1, True, 0), (4, 5, True, 0), (8, 9, True, 0)], 13)
        result = self.run_case(data)['results']
        self.assertEqual([3, 2, 1], [len(level) for level in result['hierarchy']])
        for level in result['hierarchy']:
            for node in level:
                text = '\n…\n'.join(data['source']['text'][start:end] for start, end in node['ranges'])
                self.assertEqual(len(text.encode('utf-8')), node['bytes'])
                self.assertEqual(hashlib.sha256(text.encode('utf-8')).hexdigest(), node['sha256'])
                self.assertLessEqual(node['bytes'], data['budget_bytes'])
        self.assertEqual('A\n…\nB\n…\nC', result['compressed']['text'])

    def test_order_and_ties_are_deterministic(self):
        data = fixture('a---b---c', [(0, 1, False, 10), (4, 5, False, 10), (8, 9, False, 5)], 7)
        first = self.run_case(data)
        data['spans'].reverse()
        self.assertEqual(first, self.run_case(data))
        self.assertEqual('a\n…\nb', first['results']['compressed']['text'])

    def test_large_comparison_has_separate_bounded_response_limit(self):
        text = 'x' * 65000
        data = fixture(text, [(0, len(text), True, 1)], len(text), ['x'])
        answer = self.run_case(data)
        self.assertGreater(len(raw(answer)), C.MAX_ENVELOPE_BYTES)
        self.assertLessEqual(len(raw(answer)), C.MAX_RESULT_BYTES)
        self.assertEqual(65000, answer['results']['compressed']['bytes'])

    def test_stale_source_and_invalid_declared_contracts_refuse(self):
        original = fixture('hello', [(0, 5, True, 1)], 5)
        cases = [
            ('source_pin', lambda d: d['source'].update(text='jello')),
            ('integer_bound', lambda d: d.update(budget_bytes=True)),
            ('integer_bound', lambda d: d.update(budget_bytes=-1)),
            ('integer_bound', lambda d: d.update(budget_bytes=C.MAX_BYTES + 1)),
            ('json_type', lambda d: d.update(budget_bytes=5.0)),
            ('integer_bound', lambda d: d.update(merge_fanout=1)),
            ('duplicate_span', lambda d: d['spans'].append(copy.deepcopy(d['spans'][0]))),
            ('integer_bound', lambda d: d['spans'][0].update(start=True)),
            ('integer_bound', lambda d: d['spans'][0].update(end=6)),
            ('required_type', lambda d: d['spans'][0].update(required=1)),
            ('duplicate_query', lambda d: d.update(query_terms=['HELLO', 'hello'])),
            ('fields', lambda d: d.update(unknown='PRIVATE_SENTINEL')),
        ]
        for code, change in cases:
            with self.subTest(code=code):
                data = copy.deepcopy(original)
                change(data)
                with self.assertRaisesRegex(ValueError, '^' + code + '$'):
                    C.run('extractive-compression', data)


class Sidecar(unittest.TestCase):
    def encode(self, content=None):
        if content is None:
            data = C.catalog()[1]['example']
        else:
            data = {'operation': 'encode', 'card': {'id': 'card', 'revision': 7,
                                                   'sha256': digest(content), 'content': content}}
        before = copy.deepcopy(data)
        answer = C.run('pinned-hash-sidecar', data)
        self.assertEqual(before, data)
        return data, answer

    def decode(self, data, envelope):
        expected = {key: data['card'][key] for key in ('id', 'revision', 'sha256')}
        return C.run('pinned-hash-sidecar', {'operation': 'decode', 'expected': expected,
                                          'envelope': envelope})

    def test_exact_roundtrip_and_both_costs_are_reported(self):
        data, answer = self.encode()
        result = answer['results']
        envelope = result['envelope']
        self.assertEqual(data['card']['content'], self.decode(data, envelope)['results']['content'])
        self.assertEqual(len(raw(data['card']['content'])), result['bytes']['original_content'])
        self.assertEqual(len(raw(envelope['payload'])), result['bytes']['model_payload'])
        self.assertEqual(len(raw(envelope['sidecar'])), result['bytes']['sidecar'])
        self.assertEqual(len(raw(envelope)), result['bytes']['total_envelope'])
        self.assertGreater(result['bytes']['payload_saved'], 0)
        self.assertTrue(all(answer['checks'].values()))

    def test_literal_reference_collision_and_unicode_preserved(self):
        h = 'a' * 64
        content = {'@h1': [h, h, '@h1', '@@h1', '@', '@literal', 'é🙂', True, None, -3],
                   'original_ref_object': {'$ref': '@h1'}}
        data, answer = self.encode(content)
        envelope = answer['results']['envelope']
        self.assertIn('@h1', envelope['payload'])
        self.assertEqual(content, self.decode(data, envelope)['results']['content'])

    def test_single_hash_is_not_unnecessarily_replaced(self):
        data, answer = self.encode({'single': 'a' * 64})
        envelope = answer['results']['envelope']
        self.assertEqual([], envelope['sidecar'])
        self.assertEqual(data['card']['content'], envelope['payload'])

    def test_wrong_revision_cross_card_and_changed_content_pin_refuse(self):
        data, answer = self.encode()
        for field, value in [('id', 'another-card'), ('revision', 2), ('sha256', '0' * 64)]:
            with self.subTest(field=field):
                altered = copy.deepcopy(data)
                altered['card'][field] = value
                with self.assertRaisesRegex(ValueError, '^card_scope$'):
                    self.decode(altered, answer['results']['envelope'])

    def test_resealed_forged_sidecar_cannot_override_caller_pin(self):
        data, answer = self.encode()
        envelope = answer['results']['envelope']
        envelope['sidecar'][0]['value'] = '0' * 64
        seal(envelope)
        with self.assertRaisesRegex(ValueError, '^content_pin$'):
            self.decode(data, envelope)

    def test_unknown_unused_duplicate_and_unsealed_references_refuse(self):
        data, answer = self.encode()
        original = answer['results']['envelope']
        cases = [
            ('reference_missing', lambda e: e['payload'].update(claim='@h999'), True),
            ('unused_reference', lambda e: e['sidecar'].append({'id': '@h9', 'value': '0' * 64}), True),
            ('duplicate_reference', lambda e: e['sidecar'].append(copy.deepcopy(e['sidecar'][0])), True),
            ('envelope_pin', lambda e: e['payload'].update(value='changed'), False),
        ]
        for code, change, reseal in cases:
            with self.subTest(code=code):
                envelope = copy.deepcopy(original)
                change(envelope)
                if reseal:
                    seal(envelope)
                with self.assertRaisesRegex(ValueError, '^' + code + '$'):
                    self.decode(data, envelope)

    def test_encoding_requires_trusted_input_content_pin(self):
        data = C.catalog()[1]['example']
        data['card']['content']['value'] = 'changed'
        with self.assertRaisesRegex(ValueError, '^content_pin$'):
            C.run('pinned-hash-sidecar', data)

    def test_reference_limit_is_real(self):
        content = {str(i): [format(i, '064x')] * 2 for i in range(65)}
        with self.assertRaisesRegex(ValueError, '^reference_bound$'):
            self.encode(content)


class Bounds(unittest.TestCase):
    def test_non_json_numbers_cycles_depth_and_aggregate_bytes_refuse(self):
        cycle = []
        cycle.append(cycle)
        deep = 1
        for _ in range(18):
            deep = [deep]
        cases = [('json_type', float('nan')), ('json_type', 1.5),
                 ('structure_bound', cycle), ('structure_bound', deep),
                 ('byte_bound', ['x' * 60000] * 3), ('unicode', '\ud800')]
        for code, data in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, '^' + code + '$'):
                C.run('unknown', data)

    def test_catalog_is_fresh_and_unknown_operation_is_short(self):
        one = C.catalog()
        one[0]['example']['spans'][0]['required'] = False
        self.assertTrue(C.catalog()[0]['example']['spans'][0]['required'])
        with self.assertRaisesRegex(ValueError, '^experiment_id$'):
            C.run('PRIVATE_SENTINEL', {})
        with self.assertRaisesRegex(ValueError, '^operation$'):
            C.run('pinned-hash-sidecar', {'operation': 'PRIVATE_SENTINEL'})


if __name__ == '__main__':
    unittest.main()

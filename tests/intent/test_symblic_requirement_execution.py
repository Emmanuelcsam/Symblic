"""Requirement execution (symblic.intent.requirement_execution): exact linked-run observation.

Isolated native run fixtures in temporary folders; no live stores or model providers.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import evidence as E
from symblic.kernel import execution_pins as X
from symblic.intent import records as I
from symblic.intent import coverage as COV
from symblic.intent import requirement_execution as R
from symblic.kernel import run as SR


def seal(value, field='sha256', digest=E.digest):
    value[field] = digest({k: v for k, v in value.items() if k != field})


class NoProvider:
    def call(self, _request):
        raise AssertionError('No external model allowed')


def fixture(source='let total = 2.\nassert total = 2.\n', predicate='total = 2', inputs=None, app=None, options=None):
    inputs = inputs or {}
    state = I.new_intent('intent-fixture', 'Check the declared total.')
    state = I.apply_event(state, {'id': 'proposal', 'kind': 'proposal', 'actor': 'owner',
        'payload': {'goal': 'Check the total', 'requirements': [
            {'id': 'total', 'text': 'The total matches.', 'predicate': predicate}]}}, 0)
    coverage = COV.requirement_coverage(state, source, inputs)
    artifact = {'content_revision': state['content_revision'], 'intent_content_sha256': I.content_digest(state),
                'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'inputs': inputs, 'input_sha256': I.digest(inputs), 'coverage': coverage}
    envelope = copy.deepcopy(artifact); seal(envelope, 'key', I.digest)
    hashes = {name: hashlib.sha256((X.BASE/name).read_bytes()).hexdigest() for name in X.REQUIRED_FILES}
    pins = X.build(source, inputs, hashes)
    handoff = {'status': 'started', 'key': envelope['key'], 'run_id': 'abcdef123456',
               'content_revision': state['content_revision'], 'envelope': envelope, 'execution_pins': pins}
    run = SR.Run(source, inputs, app or NoProvider(), {'execution_pins': pins, 'max_calls': 0,
                 'parallel': 1, 'determine': False, 'solve': False, **(options or {})}, folder=None)
    report = run.execute()
    native = {'source': source, 'meta': {'inputs': inputs, 'inputs_source_sha256': artifact['source_sha256'],
              'prompt': '[Symblic intent '+envelope['key']+']\nfixture', 'options': {'execution_pins': pins}},
              'state': report, 'trace': run.trace}
    return state, artifact, handoff, coverage, native


class Join(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket', side_effect=AssertionError('No network'))
        self.network.start(); self.addCleanup(self.network.stop)

    def test_actual_native_pass_is_pinned_and_input_detached(self):
        data = fixture(); before = copy.deepcopy(data)
        result = R.derive(*data)
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['requirements'][0]['status'], 'observed_pass')
        self.assertEqual(result['requirements'][0]['passed_checks'], 1)
        self.assertEqual(result['binding']['execution_id'], data[-1]['state']['execution_id'])
        pins = data[2]['execution_pins']; body = {k:v for k,v in pins.items() if k != 'sha256'}
        self.assertEqual(pins['sha256'], E.digest(body))
        self.assertEqual(pins['sha256'], hashlib.sha256(X._json(body)).hexdigest())
        self.assertEqual(result['owner_acceptance'], 'not_established')
        self.assertEqual(data, before)

    def test_failed_run_retains_actual_failing_check(self):
        result = R.derive(*fixture('let total = 2.\nassert total = 3.\n', 'total = 3'))
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['run_status'], 'failed')
        self.assertEqual(result['requirements'][0]['status'], 'observed_fail')
        self.assertEqual(result['requirements'][0]['failed_checks'], 1)

    def test_dead_branch_present_but_unobserved(self):
        result = R.derive(*fixture('let total = 2.\nif false then\n assert total = 2.\nend.\n'))
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['requirements'][0]['mapping_status'], 'predicate_present')
        self.assertEqual(result['requirements'][0]['status'], 'unobserved')

    def test_trace_only_rolled_back_check_never_counts(self):
        # Native rollback leaves the trace and truncates retained check receipts.
        data = fixture(); data[-1]['state']['evidence']['checks'].clear()
        result = R.derive(*data)
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['trace_only_checks'], 1)
        self.assertEqual(result['requirements'][0]['status'], 'unobserved')

    def test_real_native_retry_removes_provisional_check_observation(self):
        class Fake:
            calls = 0
            def call(self, _request):
                self.calls += 1
                return {'ok': True, 'json': {'answer': self.calls}, 'model': 'synthetic-fixture'}
        app = Fake()
        data = fixture('ask value: Int "Synthetic." with retries=1.\nassert value >= 0.\n'
                       'ensure value = 2 else retry.\n', 'value >= 0', app=app,
                       options={'by': 'fake:fixture', 'max_calls': 2})
        result = R.derive(*data)
        self.assertEqual(app.calls, 2)
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['requirements'][0]['passed_checks'], 1)
        self.assertEqual(result['trace_only_checks'], 1)
        old = next(row['check']['id'] for row in data[-1]['trace'] if 'check' in row)
        self.assertNotIn(old, result['requirements'][0]['receipt_ids'])

    def test_malformed_mapping_and_resealed_predicate_text_are_unknown(self):
        for malformed in (None, [], {'requirements': None}, {'requirements': [{}]}):
            data = list(fixture()); data[3] = malformed
            self.assertEqual(R.derive(*data)['status'], 'unknown')
        data = fixture(); receipt = data[-1]['state']['evidence']['checks'][0]
        receipt['predicate'] = 'false'; seal(receipt, 'id')
        result = R.derive(*data)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['reason'], 'check_predicate_text_mismatch')

    def test_partial_run_cannot_reuse_earlier_final_evidence(self):
        data = fixture(); data[-1]['state']['status'] = 'running'
        result = R.derive(*data)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['requirements'][0]['status'], 'unobserved')

    def test_wrong_revision_source_inputs_and_pins_refuse(self):
        for change in ('revision', 'source', 'input', 'pins', 'handoff', 'artifact_bool'):
            data = fixture()
            if change == 'revision': data[0]['content_revision'] += 1
            if change == 'source': data[-1]['source'] += '# changed\n'
            if change == 'input': data[-1]['meta']['inputs'] = {'total': 3}
            if change == 'pins':
                data[-1]['meta']['options'] = copy.deepcopy(data[-1]['meta']['options'])
                data[-1]['meta']['options']['execution_pins']['kernel_id'] = '0'*16
            if change == 'handoff': data[-1]['meta']['prompt'] = '[Symblic intent other]\n'
            if change == 'artifact_bool': data[1]['content_revision'] = True
            with self.subTest(change=change):
                result = R.derive(*data)
                self.assertIn(result['status'], ('unknown', 'stale'), result)
                self.assertEqual(result['requirements'][0]['passed_checks'], 0)

    def test_typed_receipt_forgery_refuses_even_if_rehashed(self):
        for field, value in [('passed', 1), ('line', True), ('version', True)]:
            for rehash in (False, True):
                data = fixture(); receipt = data[-1]['state']['evidence']['checks'][0]
                # Native trace and evidence refer to the same original receipt.
                receipt[field] = value
                if rehash: seal(receipt, 'id')
                result = R.derive(*data)
                with self.subTest(field=field, rehash=rehash):
                    self.assertEqual(result['status'], 'unknown', result)

    def test_typed_and_duplicate_mapping_locations_refuse_even_if_resealed(self):
        for change in ('bool_line', 'bool_column', 'duplicate', 'wrong_predicate'):
            data = fixture()
            mapping = data[3]['requirements'][0]['locations']
            if change == 'bool_line': mapping[0]['line'] = True
            if change == 'bool_column': mapping[0]['col'] = True
            if change == 'duplicate': mapping.append(copy.deepcopy(mapping[0]))
            if change == 'wrong_predicate':
                # A valid source location with a different source predicate.
                data = fixture('let total = 2.\nassert total = 2.\nassert true.\n')
                mapping = data[3]['requirements'][0]['locations']; mapping[0]['line'] = 3
            seal(data[3], digest=I.digest)
            data[1]['coverage'] = copy.deepcopy(data[3])
            data[2]['envelope']['coverage'] = copy.deepcopy(data[3]); seal(data[2]['envelope'], 'key', I.digest)
            data[2]['key'] = data[2]['envelope']['key']
            data[-1]['meta']['prompt'] = '[Symblic intent '+data[2]['key']+']\nfixture'
            with self.subTest(change=change):
                result = R.derive(*data)
                self.assertEqual(result['status'], 'unknown', result)
                self.assertEqual(result['requirements'][0]['passed_checks'], 0)

    def test_missing_trace_and_conflicting_trace_status_are_unknown(self):
        for change in ('missing', 'status', 'line', 'sequence', 'kernel'):
            data = fixture()
            row = next(r for r in data[-1]['trace'] if 'check' in r)
            if change == 'missing': data[-1]['trace'].remove(row)
            if change == 'status': row['status'] = 'failed'
            if change == 'line': row['line'] += 1
            if change == 'sequence': row['sequence'] = True
            if change == 'kernel': row['kernel'] = {'id': '0'*16}
            with self.subTest(change=change):
                self.assertEqual(R.derive(*data)['status'], 'unknown')

    def test_ambiguous_same_line_ast_is_not_attributed(self):
        data = fixture(); parsed = S.parse(data[1]['source'])
        other = copy.deepcopy(parsed['statements'][-1]); other.col += 20
        parsed['statements'].append(other)
        # Represents an indistinguishable line/kind/AST receipt at two columns.
        original_parse = S.parse
        with patch.object(S, 'parse', side_effect=lambda src: parsed if src == data[1]['source'] else original_parse(src)):
            result = R.derive(*data)
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['requirements'][0]['status'], 'ambiguous')
        self.assertEqual(result['requirements'][0]['passed_checks'], 0)

    def test_multiple_locations_keep_dead_location_unobserved(self):
        source = 'let total = 2.\nassert total = 2.\nif false then\n assert total = 2.\nend.\n'
        result = R.derive(*fixture(source))
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['requirements'][0]['status'], 'partially_observed')
        self.assertEqual(result['requirements'][0]['passed_checks'], 1)

    def test_missing_handoff_and_stale_revision_never_read_native(self):
        data = fixture(); row = {'state': data[0], 'artifact': data[1], 'handoffs': []}
        forbidden = lambda _: self.fail('must not look up a run')
        self.assertEqual(R.view(row, data[3], forbidden)['reason'], 'linked_run_unavailable')
        row['handoffs'] = [data[2]]; row['state']['content_revision'] += 1
        self.assertEqual(R.view(row, data[3], forbidden)['status'], 'stale')

    def test_model_predicate_observation_does_not_change_mapping_origin(self):
        data = fixture(); data[0]['requirements'][0]['origin'] = 'model_proposed'
        state, artifact, handoff, _coverage, native = data
        coverage = COV.requirement_coverage(state, artifact['source'], artifact['inputs'])
        artifact.update(intent_content_sha256=I.content_digest(state), coverage=coverage)
        handoff['envelope'].update(intent_content_sha256=I.content_digest(state), coverage=copy.deepcopy(coverage))
        seal(handoff['envelope'], 'key', I.digest); handoff['key'] = handoff['envelope']['key']
        native['meta']['prompt'] = '[Symblic intent '+handoff['key']+']\nfixture'
        result = R.derive(state, artifact, handoff, coverage, native)
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(result['requirements'][0]['mapping_status'], 'proposed_predicate_present')
        self.assertEqual(result['requirements'][0]['predicate_origin'], 'model_proposed')


class Reader(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'abcdef123456'; self.folder.mkdir()
        self.data = fixture(); native = self.data[-1]
        (self.folder/'program.sym').write_text(native['source'])
        for name in ('meta', 'state'):
            (self.folder/(name+'.json')).write_text(json.dumps(native[name]))
        (self.folder/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in native['trace']))

    def test_bounded_reader_and_view_do_not_mutate_records(self):
        before = {p.name:p.read_bytes() for p in self.folder.iterdir()}
        state, artifact, handoff, coverage, _ = self.data
        row = {'state': state, 'artifact': artifact, 'handoffs': [handoff]}
        calls = []
        def lookup(run_id):
            calls.append(run_id)
            return str(self.folder)
        result = R.view(row, COV.requirement_coverage(state, artifact['source'], artifact['inputs']), lookup)
        self.assertEqual(result['status'], 'joined', result)
        self.assertEqual(calls, [handoff['run_id']])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.folder.iterdir()})
        self.assertEqual(R.read_snapshot(self.folder), self.data[-1])

    def test_symlink_partial_trace_and_oversize_are_unknown(self):
        row = {'state': self.data[0], 'artifact': self.data[1], 'handoffs': [self.data[2]]}
        path = self.folder/'trace.jsonl'; original = path.read_bytes()
        path.write_bytes(original.rstrip(b'\n'))
        self.assertEqual(R.view(row,self.data[3],lambda _:self.folder)['reason'], 'partial_trace')
        path.write_bytes(original)
        with patch.object(R,'MAX_TRACE_BYTES', 10):
            self.assertEqual(R.view(row,self.data[3],lambda _:self.folder)['reason'], 'native_file_bound')
        path.unlink(); path.symlink_to(self.folder/'state.json')
        self.assertEqual(R.view(row,self.data[3],lambda _:self.folder)['status'], 'unknown')

    def test_missing_run_folder_is_unknown_and_never_created(self):
        absent = Path(self.temp.name)/'absent'
        row = {'state': self.data[0], 'artifact': self.data[1], 'handoffs': [self.data[2]]}
        coverage = COV.requirement_coverage(self.data[0], self.data[1]['source'], self.data[1]['inputs'])
        self.assertEqual(R.view(row, coverage, lambda run_id: absent/'runs'/run_id)['status'], 'unknown')
        self.assertFalse(absent.exists())


if __name__ == '__main__':
    unittest.main()

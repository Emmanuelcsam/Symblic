"""Constructor journal: durable intent/outcome, strict reading, pins, allowance, stops and replay.

Temporary run folders only. No Run, provider, model, worker, solver, service or live store. Crashes and kills are
real child processes running this private module.
"""
import errno
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TREE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository root
sys.path.insert(0, TREE)
from symblic.constructor import journal as J  # noqa: E402

assert os.path.abspath(J.__file__) == os.path.join(TREE, 'symblic', 'constructor', 'journal.py'), J.__file__

CHILD = r'''
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from symblic.constructor import journal as J
folder, pins, request, action = sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4]), sys.argv[5]
journal = J.Journal(folder, pins)
try:
    attempt = journal.begin(request)
except J.JournalError as exc:
    print(exc.code, flush=True)
    sys.exit(0)
if action == 'begin_exit':
    os._exit(0)
if action == 'begin_sleep':
    print('ready', flush=True)
    time.sleep(60)
    os._exit(0)
if action == 'complete_exit':
    journal.complete(attempt, json.loads(sys.argv[6]))
    os._exit(0)
print('ok', flush=True)
'''


def pins(**over):
    out = {'source_sha256': 'a' * 64, 'input_sha256': 'b' * 64, 'kernel_id': '1e87549328ddcdb6',
           'kind': 'smt_linear', 'mode': 'linear', 'selection_policy': 'canonical_min_v1',
           'implementation_sha256': 'c' * 64, 'worker_sha256': 'd' * 64, 'configuration_sha256': 'e' * 64,
           'allowance': {'attempts': 8, 'milliseconds': 20000}}
    out.update(over)
    return out


def request(occurrence='ask:3', item=None, **over):
    out = {'occurrence': occurrence, 'item': item, 'contract_sha256': '1' * 64, 'constants_sha256': '2' * 64,
           'dependencies_sha256': '3' * 64,
           'limits': {'milliseconds': 1000, 'resource_limit': 100000, 'address_space_bytes': 268435456}}
    out.update(over)
    return out


def outcome(disposition='accepted', candidates=(7,), **over):
    worker = {'raw_sha256': 'f' * 64, 'effective_limits': {'milliseconds': 1000, 'address_space_bytes': 268435456}}
    out = {'disposition': disposition, 'dispatched': True, 'reaped': True, 'status': None, 'reason': None,
           'determination': None, 'candidates': [], 'raw_sha256': None, 'effective_limits': None,
           'costs': {'elapsed_ms': 120, 'solver_rlimit': 4321, 'validation_steps': 17}, 'evidence': None}
    if disposition in ('accepted', 'diagnosed'):
        out.update(status='sat', candidates=list(candidates),
                   determination='underdetermined' if len(candidates) == 2 else 'unassessed', **worker)
    elif disposition == 'no_candidate':
        out.update(status='unsat', determination='unassessed', **worker)
    elif disposition in ('unsupported', 'unavailable', 'timeout', 'unknown'):
        out.update(status=disposition, determination='unassessed', reason='fixture_reason')
    elif disposition == 'cleanup_failed':
        out.update(reaped=False)
    out.update(over)
    return out


def undispatched(disposition='stopped', **over):
    return outcome(disposition, dispatched=False, reaped=None, **over)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.folder = os.path.join(self.tmp.name, 'run')
        os.mkdir(self.folder, 0o700)
        self.path = os.path.join(self.folder, J.FILE)

    def tearDown(self):
        self.tmp.cleanup()

    def journal(self, **over):
        replay = over.pop('replay', False)
        return J.Journal(self.folder, pins(**over), replay=replay)

    def raw(self):
        with open(self.path, 'rb') as stream:
            return stream.read()

    def rows(self):
        return [json.loads(line) for line in self.raw().splitlines()]

    def write_rows(self, rows):
        with open(self.path, 'wb') as stream:
            stream.write(b''.join(J._dump(row).encode() + b'\n' for row in rows))

    def child(self, action, req=None, extra=(), p=None):
        return subprocess.run([sys.executable, '-c', CHILD, TREE, self.folder, json.dumps(p or pins()),
                               json.dumps(req or request()), action, *extra], capture_output=True, text=True,
                              timeout=60, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def code(self, call, *args, **kwargs):
        with self.assertRaises(J.JournalError) as caught:
            call(*args, **kwargs)
        return caught.exception.code


def reseal(rows):
    """Recompute every hash and derived identity (seq, prev, pins_sha256, keys, attempt ids) of adversarial rows: the
    reader must refuse them for what they say, not for a stale hash."""
    out, last, the_pins, keys = [], J.GENESIS, None, {}
    for seq, row in enumerate(rows, 1):
        row = {k: v for k, v in row.items() if k != 'sha256'}
        row.update(seq=seq, prev=last)
        if row.get('event') == 'open':
            the_pins = row['pins']
            row['pins_sha256'] = J._sha('pins', the_pins)
        elif row.get('event') == 'intent':
            row['key'] = J._sha('key', {'pins': the_pins, 'request': row['request']})
            keys[row['attempt']] = (seq, row['key'])
            row['attempt'] = seq
        elif row.get('event') in ('outcome', 'reconcile') and row.get('attempt') in keys:
            row['attempt'], key = keys[row['attempt']]
            if row['event'] == 'outcome':
                row['key'] = key
        row['sha256'] = J._sha('row', row)
        last = row['sha256']
        out.append(row)
    return out


class Inert(Base):
    def test_import_creates_no_state_or_workers_and_registers_source_identity(self):
        script = ('import sys, threading; sys.path.insert(0, sys.argv[1]); n = threading.active_count(); '
                  'from symblic.constructor import journal; assert threading.active_count() == n; '
                  "print(sorted(m for m in sys.modules if m.startswith(('symblic', 'subprocess'))))")
        empty = os.path.join(self.tmp.name, 'empty')
        os.mkdir(empty)
        done = subprocess.run([sys.executable, '-c', script, TREE], cwd=empty, capture_output=True, text=True,
                              timeout=60, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "['symblic', 'symblic.constructor', 'symblic.constructor.journal', "
                                              "'symblic.kernel', 'symblic.kernel.identity']")
        self.assertEqual(os.listdir(empty), [])

    def test_lookup_without_a_record_only_reads(self):
        self.assertEqual(self.journal().lookup(request())['kind'], 'fresh')
        decision = self.journal(replay=True).lookup(request())
        self.assertEqual((decision['kind'], decision['action']), ('missing', 'refuse'))
        self.assertEqual(os.listdir(self.folder), [])
        J.Journal(self.folder, pins())          # constructing touches nothing either
        self.assertEqual(os.listdir(self.folder), [])

    def test_the_journal_never_creates_the_run_folder(self):
        missing = os.path.join(self.tmp.name, 'absent')
        self.assertEqual(self.code(J.Journal(missing, pins()).begin, request()), 'no_folder')
        self.assertFalse(os.path.exists(missing))


class Durability(Base):
    def test_intent_is_synced_with_its_folder_before_begin_returns(self):
        synced, real = [], os.fsync

        def record(fd):
            synced.append(os.readlink(f'/proc/self/fd/{fd}'))
            return real(fd)
        with mock.patch.object(J.os, 'fsync', side_effect=record):
            attempt = self.journal().begin(request())
        self.assertEqual(synced, [os.path.realpath(self.path), os.path.realpath(self.folder)])
        rows = self.rows()
        self.assertEqual([r['event'] for r in rows], ['open', 'intent'])
        self.assertEqual(rows[1]['key'], J.attempt_key(pins(), request()))
        self.assertEqual(rows[1]['charged_before'], {'attempts': 0, 'milliseconds': 0})
        self.assertTrue(rows[1]['at_ms'] < rows[1]['deadline_at_ms'] <= rows[1]['at_ms'] + 1000)   # the time left
        self.assertEqual(attempt.attempt, 2)
        for name in (J.FILE, J.LOCK_FILE):
            self.assertEqual(os.stat(os.path.join(self.folder, name)).st_mode & 0o777, 0o600)

    def test_a_value_is_returned_only_after_its_outcome_is_synced(self):
        journal = self.journal()
        attempt = journal.begin(request())
        synced, real = [], os.fsync

        def record(fd):
            synced.append(os.readlink(f'/proc/self/fd/{fd}'))
            return real(fd)
        with mock.patch.object(J.os, 'fsync', side_effect=record):
            done = journal.complete(attempt, outcome(candidates=[9, 4]))
        self.assertEqual(synced, [os.path.realpath(self.path), os.path.realpath(self.folder)])   # v2: every write
        self.assertEqual((done['adoptable'], done['value'], done['record']['selected']), (True, 4, 1))
        self.assertEqual(self.journal().lookup(request())['value'], 4)

    def test_failed_sync_poisons_the_object_and_returns_no_attempt_or_value(self):
        journal = self.journal()
        with mock.patch.object(J.os, 'fsync', side_effect=OSError(errno.EIO, 'I/O error')):
            self.assertEqual(self.code(journal.begin, request()), 'durability')
        self.assertEqual(self.code(journal.lookup, request()), 'durability')
        # The unconfirmed intent may have reached the disk: a resumed run treats it as possibly dispatched.
        self.assertEqual(self.code(self.journal().lookup, request()), 'uncertain')
        other = J.Journal(os.path.join(self.tmp.name, 'run2'), pins())
        os.mkdir(other.folder)
        attempt = other.begin(request())
        with mock.patch.object(J.os, 'fsync', side_effect=OSError(errno.EIO, 'I/O error')):
            self.assertEqual(self.code(other.complete, attempt, outcome()), 'durability')
        self.assertEqual(self.code(other.lookup, request()), 'durability')

    def test_a_failed_write_leaves_no_partial_row(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome('no_candidate'))
        before, real, calls = self.raw(), os.write, []

        def flaky(fd, data):
            if not calls:
                calls.append(1)
                return real(fd, bytes(data[:len(data) // 2]))
            raise OSError(errno.ENOSPC, 'No space left on device')
        with mock.patch.object(J.os, 'write', side_effect=flaky):
            self.assertEqual(self.code(self.journal().begin, request('ask:9')), 'durability')
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.journal().lookup(request('ask:9'))['kind'], 'fresh')


class Crashes(Base):
    def test_a_crash_after_the_intent_is_uncertain_and_never_redispatched(self):
        self.assertEqual(self.child('begin_exit').returncode, 0)
        journal = self.journal()
        with self.assertRaises(J.JournalError) as caught:
            journal.lookup(request())
        self.assertEqual((caught.exception.code, caught.exception.details['owner_live']), ('uncertain', False))
        self.assertEqual(self.code(journal.begin, request()), 'uncertain')
        self.assertEqual(self.code(journal.begin, request(), continues=2), 'uncertain')
        self.assertEqual(J.summary(self.folder)['uncertain'], [2])
        self.assertEqual(self.child('begin').stdout.strip(), 'uncertain')

    def test_a_killed_owner_leaves_no_lock_and_only_the_owner_reconciles(self):
        proc = subprocess.Popen([sys.executable, '-c', CHILD, TREE, self.folder, json.dumps(pins()),
                                 json.dumps(request()), 'begin_sleep'], stdout=subprocess.PIPE, text=True,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'ready')
            with self.assertRaises(J.JournalError) as caught:
                self.journal().lookup(request())
            self.assertTrue(caught.exception.details['owner_live'])
            self.assertEqual(self.code(J.reconcile, self.folder, 2), 'owner_live')
        finally:
            proc.kill()
            proc.wait()
            proc.stdout.close()
        journal = self.journal()
        # The dead owner's lock went with it: this refusal is about the record (run-wide gate), not a lock wait.
        with self.assertRaises(J.JournalError) as caught:
            journal.begin(request('ask:9'))
        self.assertEqual((caught.exception.code, caught.exception.details), ('unresolved', {'attempts': [2]}))
        self.assertEqual(journal.lookup(request('ask:9'))['unresolved'], [2])
        with self.assertRaises(J.JournalError) as caught:
            journal.lookup(request())
        self.assertFalse(caught.exception.details['owner_live'])
        row = J.reconcile(self.folder, 2, note='worker host rebooted')
        self.assertEqual((row['event'], row['verdict'], row['forced']), ('reconcile', 'abandoned', False))
        decision = journal.lookup(request())
        self.assertEqual((decision['kind'], decision['action'], decision['continuable']), ('abandoned', 'refuse', True))
        self.assertEqual(self.code(journal.begin, request()), 'continuation')
        self.assertEqual(journal.begin(request(), continues=2).continues, 2)
        self.assertEqual(J.summary(self.folder)['charged'], {'attempts': 2, 'milliseconds': 2000})

    def test_a_crash_after_the_outcome_reuses_the_recorded_value(self):
        done = self.child('complete_exit', extra=[json.dumps(outcome(candidates=[12, 3]))])
        self.assertEqual(done.returncode, 0, done.stderr)
        for journal in (self.journal(), self.journal(replay=True)):
            decision = journal.lookup(request())
            # canonical_min_v1 orders canonical text: "12" < "3". A pinned rule, not a least solution.
            self.assertEqual((decision['kind'], decision['action'], decision['value']), ('accepted', 'adopt', 12))
        self.assertEqual(self.code(self.journal().begin, request()), 'recorded')

    def test_concurrent_duplicate_begins_admit_one_intent(self):
        barrier, results = threading.Barrier(2), []

        def race():
            journal = self.journal()
            barrier.wait()
            try:
                results.append(journal.begin(request()).attempt)
            except J.JournalError as exc:
                results.append(exc.code)
        threads = [threading.Thread(target=race) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(sorted(map(str, results)), ['2', 'uncertain'])
        second = os.path.join(self.tmp.name, 'run2')
        os.mkdir(second)
        procs = [subprocess.Popen([sys.executable, '-c', CHILD, TREE, second, json.dumps(pins()),
                                   json.dumps(request('ask:7')), 'race'], stdout=subprocess.PIPE, text=True,
                                  env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}) for _ in range(2)]
        outs = sorted(proc.communicate(timeout=60)[0].strip() for proc in procs)
        self.assertEqual(outs, ['ok', 'uncertain'])
        self.assertEqual((J.work_count(self.folder), J.work_count(second)), (1, 1))


class TornTail(Base):
    def make_torn(self, cut_event):
        journal = self.journal()
        attempt = journal.begin(request())
        if cut_event == 'outcome':
            journal.complete(attempt, outcome())
        whole = self.raw()
        torn = whole[:-25]
        with open(self.path, 'wb') as stream:
            stream.write(torn)
        return torn[torn.rfind(b'\n') + 1:]

    def test_a_torn_outcome_is_quarantined_and_leaves_its_attempt_uncertain(self):
        tail = self.make_torn('outcome')
        with self.assertRaises(J.JournalError) as caught:
            self.journal().lookup(request())
        self.assertEqual(caught.exception.code, 'torn_tail')
        sha = caught.exception.details['torn_sha256']
        self.assertEqual(sha, hashlib.sha256(tail).hexdigest())
        self.assertEqual(self.code(J.repair_torn_tail, self.folder, '0' * 64), 'state')
        row = J.repair_torn_tail(self.folder, sha)
        with open(os.path.join(self.folder, row['quarantine']), 'rb') as stream:
            self.assertEqual(stream.read(), tail)
        self.assertEqual([r['event'] for r in self.rows()], ['open', 'intent', 'repair'])
        self.assertEqual(self.code(self.journal().lookup, request()), 'uncertain')
        self.assertEqual(self.code(J.repair_torn_tail, self.folder, sha), 'state')     # nothing torn now

    def test_a_torn_intent_is_cut_and_the_slot_is_fresh_again(self):
        self.make_torn('intent')
        with self.assertRaises(J.JournalError) as caught:
            self.journal().begin(request())
        J.repair_torn_tail(self.folder, caught.exception.details['torn_sha256'])
        self.assertEqual(self.journal().lookup(request())['kind'], 'fresh')
        self.assertEqual(self.journal().begin(request()).attempt, 3)


class StrictReader(Base):
    def setUp(self):
        super().setUp()
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome(candidates=[5, 2]))
        journal.complete(journal.begin(request('ask:9')), undispatched('unsupported', reason='plan_shape'))
        self.good = self.rows()

    def refused(self, data):
        with open(self.path, 'wb') as stream:
            stream.write(data)
        codes = {self.code(self.journal().lookup, request()), J.summary(self.folder)['problem']['code']}
        self.assertEqual(len(codes), 1)
        self.assertEqual(J.work_count(self.folder), 1)
        return codes.pop()

    def lines(self, rows):
        return [J._dump(r).encode() for r in rows]

    def test_damaged_bytes_are_refused_never_skipped(self):
        lines = self.lines(self.good)
        join = b'\n'.join
        v = b'"v":%d' % J.VERSION
        self.assertEqual(lines[0].count(v), 1)
        cases = {
            'blank line': (join(lines[:2] + [b''] + lines[2:]) + b'\n', 'malformed'),
            'duplicate key': (join([b'{"v":%d,' % J.VERSION + lines[0][1:]] + lines[1:]) + b'\n', 'malformed'),
            'float': (join([lines[0].replace(v, v + b'.0')] + lines[1:]) + b'\n', 'malformed'),
            'nan': (join([lines[0].replace(v, b'"v":NaN')] + lines[1:]) + b'\n', 'malformed'),
            'non-ascii': (join([lines[0].replace(b'"open"', b'"op\xc3\xa9n"')] + lines[1:]) + b'\n', 'malformed'),
            'spacing': (join([json.dumps(self.good[0], sort_keys=True).encode()] + lines[1:]) + b'\n', 'noncanonical'),
            'edited field': (join([lines[0]] + [lines[1].replace(b'"milliseconds":1000', b'"milliseconds":999')]
                                  + lines[2:]) + b'\n', 'chain'),
            'deleted row': (join(lines[:1] + lines[2:]) + b'\n', 'sequence'),
            'swapped rows': (join([lines[1], lines[0]] + lines[2:]) + b'\n', 'sequence'),
            'oversized row': (join(lines + [b'{"x":"' + b'a' * J.MAX_ROW_BYTES + b'"}']) + b'\n', 'oversized_row'),
        }
        for name, (data, code) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.refused(data), code)

    def test_chain_valid_rows_with_wrong_meaning_are_refused(self):
        def tampered(index, change):
            rows = json.loads(json.dumps(self.good))
            change(rows[index])
            return b''.join(line + b'\n' for line in self.lines(reseal(rows)))
        second = dict(self.good[2])
        cases = {
            'unknown event': (tampered(0, lambda r: r.update(event='other')), 'schema'),
            'bool as int': (tampered(2, lambda r: r['outcome']['costs'].update(elapsed_ms=True)), 'schema'),
            'other selection': (tampered(2, lambda r: r.update(selected=0)), 'schema'),
            'other owner': (tampered(2, lambda r: r['owner'].update(token='9' * 32)), 'state'),
            'charges': (tampered(3, lambda r: r['charged_before'].update(attempts=0)), 'budget_record'),
            'accepted in diagnose mode': (tampered(0, lambda r: r['pins'].update(mode='linear_diagnose')), 'schema'),
            'slot request changed': (tampered(3, lambda r: r['request'].update(occurrence='ask:3',
                                                                                constants_sha256='7' * 64)), 'state'),
            'second attempt without continuing': (tampered(3, lambda r: r['request'].update(occurrence='ask:3')),
                                                  'state'),
            'continues another slot': (tampered(3, lambda r: r.update(continues=2)), 'state'),
            'reserve beyond allowance': (tampered(0, lambda r: r['pins']['allowance'].update(attempts=1)),
                                         'budget_record'),
        }
        rows = json.loads(json.dumps(self.good))
        cases['second terminal'] = (b''.join(line + b'\n' for line in self.lines(reseal(rows[:3] + [second]))), 'state')
        for name, (data, code) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.refused(data), code)

    def test_files_are_not_followed_through_links(self):
        target = os.path.join(self.tmp.name, 'elsewhere.jsonl')
        os.replace(self.path, target)
        os.symlink(target, self.path)
        self.assertEqual(self.code(self.journal().lookup, request()), 'unsafe_file')
        self.assertEqual(self.code(self.journal().begin, request('ask:5')), 'unsafe_file')


class Limits(Base):
    def test_an_oversized_journal_is_refused(self):
        with open(self.path, 'wb') as stream:
            stream.truncate(J.MAX_JOURNAL_BYTES + 1)
        self.assertEqual(self.code(self.journal().lookup, request()), 'oversized_journal')

    def test_a_full_journal_refuses_before_writing(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome())
        before = self.raw()
        with mock.patch.object(J, 'MAX_JOURNAL_BYTES', len(before) + 100):
            self.assertEqual(self.code(journal.begin, request('ask:9')), 'journal_full')
        self.assertEqual(self.raw(), before)

    def test_released_attempts_still_count_toward_the_journal_cap(self):
        journal = self.journal(allowance={'attempts': 2, 'milliseconds': 20000})
        with mock.patch.object(J, 'MAX_ATTEMPTS', 2):
            journal.complete(journal.begin(request()), undispatched())
            journal.complete(journal.begin(request(), continues=2), undispatched())
            self.assertEqual(J.summary(self.folder)['charged'], {'attempts': 0, 'milliseconds': 0})
            self.assertEqual(self.code(journal.begin, request(), continues=4), 'journal_full')


class Allowance(Base):
    def test_the_original_allowance_survives_resume_and_cannot_grow(self):
        small = {'attempts': 2, 'milliseconds': 3000}
        first = self.journal(allowance=small)
        first.complete(first.begin(request()), outcome('no_candidate'))
        resumed = self.journal(allowance=small)
        resumed.complete(resumed.begin(request('ask:9', limits={'milliseconds': 1500, 'resource_limit': 100000,
                                                                'address_space_bytes': 268435456})),
                         outcome('timeout'))
        with self.assertRaises(J.JournalError) as caught:
            self.journal(allowance=small).begin(request('ask:11'))
        self.assertEqual((caught.exception.code, caught.exception.details['charged']),
                         ('budget', {'attempts': 2, 'milliseconds': 2500}))
        before = self.raw()
        grown = self.journal(allowance={'attempts': 3, 'milliseconds': 9000})
        with self.assertRaises(J.JournalError) as caught:
            grown.begin(request('ask:11'))
        self.assertEqual((caught.exception.code, caught.exception.details['fields']), ('drift', ['allowance']))
        self.assertEqual(self.code(grown.lookup, request()), 'drift')
        self.assertEqual(self.raw(), before)

    def test_milliseconds_are_reserved_before_dispatch(self):
        journal = self.journal(allowance={'attempts': 5, 'milliseconds': 2000})
        slow = {'milliseconds': 1500, 'resource_limit': 100000, 'address_space_bytes': 268435456}
        journal.complete(journal.begin(request(limits=slow)), outcome('timeout'))
        self.assertEqual(self.code(journal.begin, request('ask:9')), 'budget')

    def test_one_deadline_covers_preflight_and_is_never_reset(self):
        journal = self.journal()
        attempt = journal.begin(request(), started=time.monotonic() - 0.4)
        self.assertLessEqual(attempt.remaining(), 0.6)
        intent = self.rows()[-1]
        self.assertTrue(1 <= intent['deadline_at_ms'] - intent['at_ms'] <= 600, intent)   # the time left, durably
        self.assertEqual(intent['reserve']['milliseconds'], 1000)                          # the whole reservation
        before = self.raw()
        self.assertEqual(self.code(journal.begin, request('ask:9'), started=time.monotonic() - 1.5), 'budget')
        self.assertEqual(self.code(journal.begin, request('ask:9'), started=time.monotonic() + 5), 'invalid_request')
        self.assertEqual(self.code(journal.begin, request('ask:9'), started=True), 'invalid_request')
        self.assertEqual(self.raw(), before)


class Stops(Base):
    def test_a_stop_before_dispatch_releases_and_needs_an_explicit_continuation(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), undispatched(reason='run_stop'))
        self.assertEqual(J.summary(self.folder)['charged'], {'attempts': 0, 'milliseconds': 0})
        decision = journal.lookup(request())
        self.assertEqual((decision['kind'], decision['action'], decision['continuable']), ('stopped', 'stop', True))
        replay = self.journal(replay=True)
        decision = replay.lookup(request())
        self.assertEqual((decision['kind'], decision['action'], decision['continuable']), ('stopped', 'stop', False))
        self.assertEqual(self.code(replay.begin, request(), continues=2), 'replay')
        self.assertEqual(self.code(journal.begin, request()), 'continuation')
        self.assertEqual(self.code(journal.begin, request(), continues=9), 'continuation')
        self.assertEqual(journal.begin(request(), continues=2).attempt, 4)

    def test_a_stop_after_launch_keeps_its_charge(self):
        journal = self.journal(allowance={'attempts': 1, 'milliseconds': 5000})
        journal.complete(journal.begin(request()), outcome('stopped'))
        self.assertEqual(J.summary(self.folder)['charged'], {'attempts': 1, 'milliseconds': 1000})
        self.assertEqual(self.code(journal.begin, request(), continues=2), 'budget')

    def test_an_unreaped_worker_blocks_its_slot_until_the_owner_reconciles(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome('cleanup_failed', reason='reap_timeout'))
        self.assertEqual(self.code(journal.lookup, request()), 'blocked')
        self.assertEqual(self.code(journal.begin, request(), continues=2), 'blocked')
        self.assertEqual(J.summary(self.folder)['blocked'], [2])
        J.reconcile(self.folder, 2, note='killed by hand')    # its own process ended it: no liveness wait
        self.assertEqual(journal.lookup(request())['kind'], 'abandoned')
        journal.begin(request(), continues=2)
        self.assertEqual(J.summary(self.folder)['charged'], {'attempts': 2, 'milliseconds': 2000})

    def test_reconcile_is_only_for_unknown_or_blocked_attempts(self):
        journal = self.journal()
        attempt = journal.begin(request())
        self.assertEqual(self.code(J.reconcile, self.folder, 2), 'owner_live')     # this very process owns it
        journal.complete(attempt, outcome())
        self.assertEqual(self.code(J.reconcile, self.folder, 2), 'state')
        self.assertEqual(self.code(J.reconcile, self.folder, 99), 'state')
        self.assertEqual(self.code(J.reconcile, self.folder, True), 'invalid_request')


class Replay(Base):
    def test_recorded_dispositions_are_replayed_never_searched_again(self):
        for index, disposition in enumerate(('no_candidate', 'unsupported', 'unavailable', 'timeout', 'unknown')):
            slot = request(f'ask:{index}')
            journal = self.journal()
            journal.complete(journal.begin(slot), outcome(disposition))
            for reader in (journal, self.journal(replay=True)):
                decision = reader.lookup(slot)
                self.assertEqual((decision['kind'], decision['action'], decision['disposition']),
                                 ('recorded', 'fallback', disposition))
            self.assertEqual(self.code(journal.begin, slot), 'recorded')

    def test_diagnose_mode_records_candidates_and_adopts_nothing(self):
        journal = self.journal(mode='linear_diagnose')
        done = journal.complete(journal.begin(request()), outcome('diagnosed', candidates=[1, 2]))
        self.assertEqual((done['adoptable'], done['value'], done['record']['selected']), (False, None, None))
        self.assertEqual(journal.lookup(request())['action'], 'fallback')
        self.assertEqual(self.code(journal.complete, journal.begin(request('ask:9')), outcome()), 'invalid_outcome')

    def test_replay_never_writes_launches_or_creates_a_file(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome(candidates=[{'b': 1, 'a': 2}]))

        def snapshot():
            return sorted((name, os.stat(os.path.join(self.folder, name)).st_mtime_ns,
                           os.path.getsize(os.path.join(self.folder, name))) for name in os.listdir(self.folder))
        before = snapshot()
        replay = self.journal(replay=True)
        self.assertEqual(replay.lookup(request())['value'], {'a': 2, 'b': 1})
        self.assertEqual(replay.lookup(request('ask:9'))['kind'], 'missing')
        self.assertEqual(self.code(replay.begin, request('ask:9')), 'replay')
        self.assertEqual(self.code(replay.complete, None, outcome()), 'replay')
        self.assertEqual(snapshot(), before)
        os.unlink(os.path.join(self.folder, J.LOCK_FILE))     # an exported folder may carry no lock file
        self.assertEqual(replay.lookup(request())['kind'], 'accepted')
        self.assertNotIn(J.LOCK_FILE, os.listdir(self.folder))


class Pins(Base):
    def test_invalid_pins_and_requests_are_refused_before_any_file(self):
        bad_pins = [pins(allowance={'attempts': True, 'milliseconds': 100}),
                    pins(allowance={'attempts': 1, 'milliseconds': 100.0}),
                    pins(source_sha256='A' * 64), pins(mode='solve'), pins(kernel_id=''),
                    {**pins(), 'extra': 1}, {k: v for k, v in pins().items() if k != 'kind'}]
        for value in bad_pins:
            with self.subTest(value=value):
                self.assertEqual(self.code(J.Journal, self.folder, value), 'invalid_pins')
        limits = request()['limits']
        bad_requests = [request(limits={**limits, 'milliseconds': True}), request(limits={**limits, 'milliseconds': 0}),
                        request(limits={**limits, 'milliseconds': 5001}), request(item=3),
                        request(occurrence=' ask:3'), {**request(), 'extra': None}]
        journal = self.journal()
        for value in bad_requests:
            with self.subTest(value=value):
                self.assertEqual(self.code(journal.begin, value), 'invalid_request')
                self.assertEqual(self.code(journal.lookup, value), 'invalid_request')
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_slot_attempted_under_another_request_is_drift(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome())
        limits = request()['limits']
        changes = {'contract_sha256': '4' * 64, 'constants_sha256': '5' * 64, 'dependencies_sha256': '6' * 64,
                   'limits': {**limits, 'resource_limit': 99}}
        for field, value in changes.items():
            with self.subTest(field=field):
                with self.assertRaises(J.JournalError) as caught:
                    journal.lookup(request(**{field: value}))
                self.assertEqual((caught.exception.code, caught.exception.details['fields']), ('drift', [field]))
        self.assertEqual(journal.lookup(request(item='row:1'))['kind'], 'fresh')
        for field in ('implementation_sha256', 'worker_sha256', 'configuration_sha256', 'source_sha256'):
            with self.subTest(field=field):
                self.assertEqual(self.code(self.journal(**{field: '9' * 64}).lookup, request()), 'drift')

    def test_the_attempt_key_is_exact_domain_separated_and_order_free(self):
        base = J.attempt_key(pins(), request())
        body = J._dump({'pins': pins(), 'request': request()}).encode()
        self.assertEqual(base, hashlib.sha256(b'symblic.constructor.key.v3\0' + body).hexdigest())
        self.assertNotEqual(base, hashlib.sha256(body).hexdigest())
        self.assertEqual(J.attempt_key(dict(reversed(list(pins().items()))), request()), base)
        variants = [pins(worker_sha256='9' * 64), pins(mode='linear_diagnose'), pins(kernel_id='a26f3e0b')]
        keys = {J.attempt_key(p, request()) for p in variants}
        keys |= {J.attempt_key(pins(), request(item='i')), J.attempt_key(pins(), request('ask:4'))}
        self.assertEqual(len(keys | {base}), 6)


class Outcomes(Base):
    def test_selection_is_the_pinned_canonical_order(self):
        for order in ([9, 4], [4, 9]):
            journal = J.Journal(os.path.join(self.tmp.name, f'run-{order[0]}'), pins())
            os.mkdir(journal.folder)
            self.assertEqual(journal.complete(journal.begin(request()), outcome(candidates=order))['value'], 4)

    def test_malformed_outcomes_are_refused_before_writing(self):
        journal = self.journal()
        attempt = journal.begin(request())
        before = self.raw()
        bad = [outcome(candidates=[3, 3]), outcome(candidates=[1, 2, 3]), outcome(candidates=[0.5]),
               outcome(determination='underdetermined'), {**outcome('no_candidate'), 'candidates': [1]},
               outcome('stopped', status='sat'), outcome(reaped=None), outcome('cleanup_failed', reaped=True),
               outcome('unsupported', status='sat'), outcome(raw_sha256=None), outcome('diagnosed'),
               outcome(evidence={'x': 1.5}), outcome(evidence={'x': 'a' * J.MAX_VALUE_BYTES}),
               {k: v for k, v in outcome().items() if k != 'evidence'}, outcome(costs={'elapsed_ms': -1,
                                                                                       'solver_rlimit': None,
                                                                                       'validation_steps': None})]
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(self.code(journal.complete, attempt, value), 'invalid_outcome')
        self.assertEqual(self.raw(), before)

    def test_only_the_beginning_execution_completes_once(self):
        journal = self.journal()
        attempt = journal.begin(request())
        self.assertEqual(self.code(self.journal().complete, attempt, outcome()), 'not_owner')
        forged = J.Attempt(**{name: getattr(attempt, name) for name in J.Attempt.__slots__})
        forged.token = '0' * 32
        self.assertEqual(self.code(journal.complete, forged, outcome()), 'not_owner')
        journal.complete(attempt, outcome())
        self.assertEqual(self.code(journal.complete, attempt, outcome()), 'conflict')

    def test_owner_liveness_is_a_diagnostic_that_sees_pid_reuse(self):
        me = {'host': J.socket.gethostname()[:255], 'pid': os.getpid(), 'start': J._proc_start('self'),
              'boot': J._boot_id(), 'token': '1' * 32}
        self.assertTrue(J.owner_live(me))
        self.assertFalse(J.owner_live({**me, 'start': me['start'] + 1}))
        self.assertFalse(J.owner_live({**me, 'boot': '0' * 36}))
        self.assertFalse(J.owner_live({**me, 'start': None}))


REPAIR_CHILD = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
from symblic.constructor import journal as J
folder, sha, point = sys.argv[2], sys.argv[3], sys.argv[4]
if point == 'before_cut':
    J.os.ftruncate = lambda *args: os._exit(0)
elif point == 'before_row':
    J._Stream._append = lambda *args, **kwargs: os._exit(0)
J.repair_torn_tail(folder, sha)
'''


class Stop(BaseException):
    """A stop raised into a write, as a Run's stop or a signal handler would."""


class Hardening(Base):
    def test_measured_size_is_exactly_the_canonical_length(self):
        values = [None, True, False, 0, -7, 2**200, -(2**255) + 1, '', 'plain', 'quote " back \\ slash',
                  'controls \x00\x01\x1f\b\f\n\r\t', 'del \x7f', 'é ü 中', '\U0001F600', '\ud800 lone', [], {},
                  [1], {'a': None}, [[], {}, [[]]], {'k': [1, 'two', {'three': [True, False, None]}], 'é': 'ü'},
                  {f'k{i}': i for i in range(50)}, ['x' * 1000, 'y' * 3]]
        for value in values:
            with self.subTest(value=repr(value)[:40]):
                self.assertEqual(J._measure(value, 10**6, 64, 10**8), len(J._dump(value)))

    def test_shared_or_repeated_values_are_refused_without_serializing_them(self):
        import tracemalloc
        huge = 'é' * (256 * 1024)
        hostile = [outcome(evidence={f'k{i}': huge for i in range(4000)}),
                   outcome(candidates=[[huge] * 4000]), outcome(evidence={'n': [None] * 10**6})]
        journal = self.journal()
        attempt = journal.begin(request())
        tracemalloc.start()
        try:
            started = time.monotonic()
            for value in hostile:
                self.assertEqual(self.code(journal.complete, attempt, value), 'invalid_outcome')
            self.assertEqual(self.code(J.canonical, {f'k{i}': huge for i in range(4000)}), 'invalid_value')
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertLess(peak, 4 * 1024 * 1024)

    def test_fifos_are_refused_never_waited_on(self):
        def guarded(call, *args):
            box = []
            worker = threading.Thread(target=lambda: box.append(self.code(call, *args)), daemon=True)
            worker.start()
            worker.join(10)
            self.assertFalse(worker.is_alive(), 'the call blocked on a FIFO')
            return box[0]
        os.mkfifo(self.path)
        self.assertEqual(guarded(self.journal().lookup, request()), 'unsafe_file')
        self.assertEqual(guarded(self.journal().begin, request()), 'unsafe_file')
        os.unlink(self.path)
        os.unlink(os.path.join(self.folder, J.LOCK_FILE))
        os.mkfifo(os.path.join(self.folder, J.LOCK_FILE))
        self.assertEqual(guarded(self.journal().lookup, request()), 'unsafe_file')
        self.assertEqual(guarded(self.journal().begin, request()), 'unsafe_file')
        self.assertFalse(os.path.lexists(self.path))

    def hold_lock(self):
        fd = os.open(os.path.join(self.folder, J.LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o600)
        J.fcntl.flock(fd, J.fcntl.LOCK_EX)
        self.addCleanup(os.close, fd)
        return fd

    def test_lock_waits_are_bounded_by_the_deadline_and_observe_stops(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome())
        before = self.raw()
        fd = self.hold_lock()
        short = {'milliseconds': 300, 'resource_limit': 100000, 'address_space_bytes': 268435456}
        started = time.monotonic()
        self.assertEqual(self.code(journal.begin, request('ask:9', limits=short)), 'budget')
        self.assertLess(time.monotonic() - started, 1.0)
        with mock.patch.object(J, 'LOCK_WAIT_SECONDS', 0.2):
            started = time.monotonic()
            self.assertEqual(self.code(journal.begin, request('ask:9')), 'busy')
            self.assertEqual(self.code(journal.lookup, request()), 'busy')
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(J.work_count(self.folder), 1)
            self.assertEqual(J.summary(self.folder)['problem']['code'], 'busy')
        stop = Stop('run stopped')
        calls = []

        def check_stop():
            calls.append(1)
            if len(calls) > 3:
                raise stop
        with self.assertRaises(Stop) as caught:
            journal.begin(request('ask:9'), check_stop=check_stop)
        self.assertIs(caught.exception, stop)
        J.fcntl.flock(fd, J.fcntl.LOCK_UN)
        self.assertEqual(self.raw(), before)

    def test_an_outcome_that_cannot_get_the_lock_records_and_returns_nothing(self):
        journal = self.journal()
        attempt = journal.begin(request())
        fd = self.hold_lock()
        with mock.patch.object(J, 'LOCK_WAIT_SECONDS', 0.2):
            self.assertEqual(self.code(journal.complete, attempt, outcome()), 'busy')
        J.fcntl.flock(fd, J.fcntl.LOCK_UN)
        self.assertEqual(self.code(self.journal().lookup, request()), 'uncertain')
        self.assertEqual(journal.complete(attempt, outcome())['value'], 7)       # nothing was written: retry is safe

    def test_the_deadline_is_checked_again_once_the_lock_is_held(self):
        real = J._read_bytes

        def slow(path):
            time.sleep(0.35)
            return real(path)
        short = {'milliseconds': 300, 'resource_limit': 100000, 'address_space_bytes': 268435456}
        with mock.patch.object(J, '_read_bytes', side_effect=slow):
            self.assertEqual(self.code(self.journal().begin, request(limits=short)), 'budget')
        self.assertFalse(os.path.lexists(self.path))

    def test_a_recorded_deadline_beyond_its_reservation_is_refused(self):
        self.journal().begin(request())
        good = self.rows()
        for deadline in (good[1]['at_ms'] + 1001, good[1]['at_ms']):
            with self.subTest(deadline=deadline):
                rows = json.loads(json.dumps(good))
                rows[1]['deadline_at_ms'] = deadline
                self.write_rows(reseal(rows))
                self.assertEqual(self.code(self.journal().lookup, request()), 'schema')

    def test_a_stop_inside_a_write_poisons_and_propagates_unchanged(self):
        stop, real = Stop('stop'), os.write

        def interrupted(fd, data):
            real(fd, bytes(data[:len(data) // 2]))
            raise stop
        journal = self.journal()
        with mock.patch.object(J.os, 'write', side_effect=interrupted):
            with self.assertRaises(Stop) as caught:
                journal.begin(request())
        self.assertIs(caught.exception, stop)
        self.assertEqual(self.raw(), b'')                                    # the half row was cut back
        self.assertEqual(self.code(journal.lookup, request()), 'durability')
        self.assertEqual(self.journal().lookup(request())['kind'], 'fresh')
        other = self.journal()
        with mock.patch.object(J.os, 'fsync', side_effect=stop):
            with self.assertRaises(Stop):
                other.begin(request())
        self.assertEqual(self.code(other.lookup, request()), 'durability')
        self.assertEqual(self.code(self.journal().lookup, request()), 'uncertain')   # whole, maybe unsynced: maybe ran

    def test_one_attempt_at_a_time_per_run(self):
        journal = self.journal()
        attempt = journal.begin(request())
        with self.assertRaises(J.JournalError) as caught:
            journal.begin(request('ask:9'))
        self.assertEqual((caught.exception.code, caught.exception.details), ('unresolved', {'attempts': [2]}))
        self.assertEqual(journal.lookup(request('ask:9'))['unresolved'], [2])
        journal.complete(attempt, outcome('cleanup_failed'))
        self.assertEqual(self.code(journal.begin, request('ask:9')), 'unresolved')
        J.reconcile(self.folder, 2)
        self.assertEqual(journal.begin(request('ask:9')).attempt, 5)

    def torn_journal(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome())
        whole = self.raw()
        with open(self.path, 'wb') as stream:
            stream.write(whole[:-25])
        with self.assertRaises(J.JournalError) as caught:
            self.journal().lookup(request())
        return caught.exception.details['torn_sha256'], whole[:-25]

    def repair_child(self, sha, point):
        done = subprocess.run([sys.executable, '-c', REPAIR_CHILD, TREE, self.folder, sha, point],
                              capture_output=True, text=True, timeout=60,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_quarantine_name_is_durable_before_the_cut(self):
        sha, _ = self.torn_journal()
        events, real_sync, real_cut = [], os.fsync, os.ftruncate

        def sync(fd):
            events.append(('fsync', os.path.basename(os.readlink(f'/proc/self/fd/{fd}'))))
            return real_sync(fd)

        def cut(fd, size):
            events.append(('cut', os.path.basename(os.readlink(f'/proc/self/fd/{fd}'))))
            return real_cut(fd, size)
        with mock.patch.object(J.os, 'fsync', side_effect=sync), mock.patch.object(J.os, 'ftruncate', side_effect=cut):
            row = J.repair_torn_tail(self.folder, sha)
        folder = os.path.basename(self.folder)
        self.assertEqual(events[:2], [('fsync', row['quarantine']), ('fsync', folder)])  # durable empty slot
        self.assertLess(events.index(('fsync', folder)), events.index(('cut', J.FILE)), events)
        self.assertEqual(events[-2:], [('fsync', J.FILE), ('fsync', folder)])          # the repair row, then its folder

    def test_a_repair_interrupted_before_the_cut_runs_again(self):
        sha, torn = self.torn_journal()
        self.repair_child(sha, 'before_cut')
        self.assertEqual(self.raw(), torn)                                   # still torn, quarantine kept
        names = [n for n in os.listdir(self.folder) if n.startswith('constructor-events.torn-')]
        self.assertEqual(len(names), 1)
        self.assertFalse([n for n in os.listdir(self.folder) if n.endswith('.tmp')])
        row = J.repair_torn_tail(self.folder, sha)
        self.assertEqual(row['quarantine'], names[0])
        self.assertEqual(self.code(self.journal().lookup, request()), 'uncertain')

    def test_a_repair_interrupted_before_its_row_is_completed_by_running_it_again(self):
        sha, _ = self.torn_journal()
        self.repair_child(sha, 'before_row')
        self.assertIsNone(J.summary(self.folder)['problem'])               # sound journal, no repair row yet
        self.assertEqual([r['event'] for r in self.rows()], ['open', 'intent'])
        row = J.repair_torn_tail(self.folder, sha)
        self.assertEqual([r['event'] for r in self.rows()], ['open', 'intent', 'repair'])
        with open(os.path.join(self.folder, row['quarantine']), 'rb') as stream:
            self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), sha)
        self.assertEqual(self.code(J.repair_torn_tail, self.folder, sha), 'state')    # recorded once


class ReviewV1(Base):
    """Root's final journal-v1 review, J1-J3, reproduced exactly as its BOUNDARY-PROBES, plus its bounded residuals."""

    def stop_during_object_lock(self, stop_at):
        journal, original, checks = self.journal(), Stop('stop token'), []
        started = time.monotonic()

        def check_stop():
            checks.append(time.monotonic() - started)
            if checks[-1] >= stop_at:
                raise original
        journal._lock.acquire()
        try:
            with mock.patch.object(J, 'LOCK_WAIT_SECONDS', 0.05):
                with self.assertRaises(Stop) as caught:
                    journal.begin(request(), check_stop=check_stop)
        finally:
            journal._lock.release()
        self.assertIs(caught.exception, original)
        self.assertGreater(len(checks), 1)                      # polled during the wait, not only before it
        self.assertEqual(os.listdir(self.folder), [])
        self.assertEqual(journal.begin(request()).attempt, 2)   # nothing was taken or announced

    def test_j1_a_stop_during_the_object_lock_wait_wins_over_busy(self):
        self.stop_during_object_lock(0.01)                      # well inside the wait

    def test_j1_a_stop_pending_at_the_timeout_still_wins(self):
        self.stop_during_object_lock(0.045)                     # just before the wait would time out

    def test_j1_without_a_stop_the_object_lock_wait_is_bounded(self):
        journal = self.journal()
        journal._lock.acquire()
        try:
            with mock.patch.object(J, 'LOCK_WAIT_SECONDS', 0.05):
                started = time.monotonic()
                self.assertEqual(self.code(journal.lookup, request()), 'busy')
                self.assertLess(time.monotonic() - started, 1.0)
        finally:
            journal._lock.release()

    def test_j2_an_interrupted_rollback_keeps_the_first_stop_and_the_poison(self):
        for secondary in (KeyboardInterrupt, SystemExit):
            with self.subTest(secondary=secondary.__name__):
                folder = os.path.join(self.tmp.name, secondary.__name__)
                os.mkdir(folder)
                journal, original = J.Journal(folder, pins()), Stop('first write stop')
                with mock.patch.object(J.os, 'write', side_effect=original), \
                        mock.patch.object(J.os, 'fsync', side_effect=secondary('rollback sync stop')):
                    with self.assertRaises(Stop) as caught:
                        journal.begin(request())
                self.assertIs(caught.exception, original)
                self.assertTrue(any('interrupted' in n for n in getattr(caught.exception, '__notes__', [])))
                self.assertTrue(journal._poisoned)
                self.assertEqual(self.code(journal.begin, request()), 'durability')   # never the same object again
                self.assertEqual(J.Journal(folder, pins()).lookup(request())['kind'], 'fresh')

    def test_j2_an_interruption_outranks_an_io_failure_and_still_poisons(self):
        journal = self.journal()
        with mock.patch.object(J.os, 'write', side_effect=OSError(errno.ENOSPC, 'No space left on device')), \
                mock.patch.object(J.os, 'fsync', side_effect=KeyboardInterrupt('second')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                journal.begin(request())
        self.assertIsInstance(caught.exception.__context__, OSError)
        self.assertEqual(self.code(journal.begin, request()), 'durability')

    def test_j2_the_latch_holds_before_the_first_byte(self):
        journal, stop = self.journal(), Stop('at the first byte')
        with mock.patch.object(J.os, 'write', side_effect=stop):
            with self.assertRaises(Stop):
                journal.begin(request())
        self.assertEqual(self.raw(), b'')
        self.assertEqual(self.code(journal.begin, request()), 'durability')

    def fsyncs(self):
        synced, real = [], os.fsync

        def record(fd):
            synced.append(os.readlink(f'/proc/self/fd/{fd}'))
            return real(fd)
        return synced, mock.patch.object(J.os, 'fsync', side_effect=record)

    def test_j3_after_a_failed_first_write_the_next_begin_syncs_the_folder(self):
        journal = self.journal()
        with mock.patch.object(J.os, 'write', side_effect=OSError(errno.ENOSPC, 'injected')):
            self.assertEqual(self.code(journal.begin, request()), 'durability')
        self.assertEqual(self.raw(), b'')                                     # the empty file was left in place
        self.assertEqual(self.code(journal.begin, request()), 'durability')   # the same object stays poisoned
        synced, patch = self.fsyncs()
        with patch:
            attempt = self.journal().begin(request())
        self.assertEqual(attempt.attempt, 2)
        self.assertEqual(synced, [os.path.realpath(self.path), os.path.realpath(self.folder)])

    def test_j3_a_resumed_run_finding_an_empty_journal_syncs_the_folder(self):
        with open(self.path, 'wb'):
            pass                                   # left by an interrupted creation, its directory entry unconfirmed
        synced, patch = self.fsyncs()
        with patch:
            self.journal().begin(request())
        self.assertEqual(synced, [os.path.realpath(self.path), os.path.realpath(self.folder)])

    def test_j3_no_attempt_is_returned_when_the_folder_cannot_be_synced(self):
        real = os.fsync

        def folder_fails(fd):
            if os.path.isdir(os.readlink(f'/proc/self/fd/{fd}')):
                raise OSError(errno.EIO, 'I/O error')
            return real(fd)
        journal = self.journal()
        with mock.patch.object(J.os, 'fsync', side_effect=folder_fails):
            self.assertEqual(self.code(journal.begin, request()), 'durability')
        self.assertEqual(self.code(journal.begin, request()), 'durability')
        self.assertEqual(self.code(self.journal().lookup, request()), 'uncertain')   # treated as possibly dispatched

    def test_repairs_are_bounded_and_recovery_never_scans_the_folder(self):
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome())
        whole = self.raw()
        with open(self.path, 'wb') as stream:
            stream.write(whole[:-25])
        with self.assertRaises(J.JournalError) as caught:
            self.journal().lookup(request())
        sha = caught.exception.details['torn_sha256']
        with mock.patch.object(J.os, 'listdir', side_effect=AssertionError('the run folder was scanned')):
            row = J.repair_torn_tail(self.folder, sha)
        self.assertEqual(row['quarantine'], 'constructor-events.torn-0.bin')
        with open(self.path, 'ab') as stream:
            stream.write(b'{"torn":')
        with self.assertRaises(J.JournalError) as caught:
            self.journal().lookup(request())
        with mock.patch.object(J, 'MAX_REPAIRS', 1):
            self.assertEqual(self.code(J.repair_torn_tail, self.folder, caught.exception.details['torn_sha256']),
                             'repair_limit')
        # a tail longer than any row this journal writes is not a torn row: it is not repaired
        with open(self.path, 'wb') as stream:
            stream.write(whole[:whole.rfind(b'\n', 0, len(whole) - 1) + 1] + b'{"x":"' + b'a' * J.MAX_ROW_BYTES)
        with self.assertRaises(J.JournalError) as caught:
            self.journal().lookup(request())
        self.assertEqual(self.code(J.repair_torn_tail, self.folder, caught.exception.details['torn_sha256']), 'state')


class Views(Base):
    def test_summary_and_work_count(self):
        self.assertEqual(J.work_count(self.folder), 0)
        journal = self.journal()
        journal.complete(journal.begin(request()), outcome())
        journal.begin(request('ask:9'))
        view = J.summary(self.folder)
        self.assertEqual((view['attempts'], view['events'], view['uncertain'], view['dispositions']),
                         (2, 4, [4], {'accepted': 1}))
        self.assertEqual(view['phases'], {'accepted': 1, 'open': 1})
        self.assertEqual(J.work_count(self.folder), 2)
        with open(self.path, 'ab') as stream:
            stream.write(b'{')
        self.assertEqual(J.summary(self.folder)['problem']['code'], 'torn_tail')
        self.assertEqual(J.work_count(self.folder), 1)

    def test_a_full_cycle_never_waits_on_its_own_lock(self):
        store_lock, errors = threading.Lock(), []

        def cycle():
            try:
                with store_lock:                # a caller may hold its own lock; the journal takes none of its
                    journal = self.journal()
                    attempt = journal.begin(request())
                    journal.complete(attempt, outcome('stopped'))
                    journal.lookup(request())
                    journal.complete(journal.begin(request(), continues=2), outcome())
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)
        worker = threading.Thread(target=cycle)
        worker.start()
        worker.join(20)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()

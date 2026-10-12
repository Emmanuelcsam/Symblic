"""symblic_effects: observe and act. A fake host and fake applicators only; ledgers live in temp folders.
Nothing here reaches a capability, a model, the network or a real store."""

import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import unittest.mock

from symblic.kernel import language as S
from symblic.kernel import effects as FX
from symblic.kernel.run import Run

OBJ = {'type': 'object', 'additionalProperties': False}
CAT = [
    {'name': 'calendar.free_busy', 'effect': 'read', 'policy': 'auto', 'sensitivity': 'personal',
     'params': {**OBJ, 'properties': {'days': {'type': 'integer', 'minimum': 1, 'maximum': 31}}}},
    {'name': 'calendar.add', 'effect': 'write-external', 'policy': 'confirm',
     'params': {**OBJ, 'properties': {'title': {'type': 'string', 'maxLength': 40}, 'start': {'type': 'string'}},
                'required': ['title']}},
    {'name': 'web.fetch', 'effect': 'read', 'policy': 'auto', 'untrusted': True,
     'params': {**OBJ, 'properties': {'url': {'type': 'string'}}, 'required': ['url']}},
    {'name': 'mail.send', 'effect': 'write-external', 'policy': 'confirm',
     'params': {**OBJ, 'properties': {'to': {'type': 'string'}, 'body': {'type': 'string'}}, 'required': ['to']}},
    {'name': 'notes.write', 'effect': 'write-local', 'policy': 'auto', 'idempotent': True,
     'params': {**OBJ, 'properties': {'text': {'type': 'string'}}, 'required': ['text']}},
    {'name': 'home.device', 'effect': 'device', 'policy': 'confirm',
     'params': {**OBJ, 'properties': {'device': {'enum': ['light', 'projector']}, 'action': {'enum': ['on', 'off']}},
                'required': ['device', 'action']}},
    {'name': 'vault.report', 'effect': 'write-local', 'policy': 'never', 'params': OBJ},
    {'name': 'web.search', 'effect': 'read', 'policy': 'auto', 'untrusted': True, 'egress': True,
     'params': {**OBJ, 'properties': {'query': {'type': 'string'}}, 'required': ['query']}},
]
CATALOGUE = FX.normalize_catalogue(CAT)


class Host:
    """results: {capability: value | callable(effect) | {'status': ...}}; every call is kept."""

    def __init__(self, results=None, cat=CAT):
        self.results, self.cat, self.calls = results or {}, cat, []

    def catalogue(self):
        return self.cat

    def perform(self, effect, stop):
        self.calls.append(effect)
        r = self.results.get(effect['capability'])
        if callable(r):
            r = r(effect)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, dict) and 'status' in r:
            return r
        return {'status': 'done', 'result': r, 'receipt': {'call': len(self.calls)}}


class Apps:
    def __init__(self, answers):
        self.answers, self.requests = answers, []

    def call(self, req):
        self.requests.append(req)
        r = self.answers[req['app']['model']]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        return {'ok': True, 'json': {'answer': r}, 'model': req['app']['model'], 'node': 'fake'}

    def delegate(self, target, task, options):
        return {'id': 'a1', 'engine': target, 'status': 'started'}


def run(source, host=None, apps=None, folder=None, **opts):
    options = {'effects': host, **opts}
    r = Run(source, applicators=apps, options=options, folder=folder)
    return r.execute(), r


def binding(rep, name):
    return next(b for b in rep['bindings'] if b['name'] == name)


def errors(source, cat=CATALOGUE):
    return [e['message'] for e in FX.check(source, cat)['errors']]


def acts_run_in_replay() -> bool:
    """True once the core lets this self-gating extension serve an act from its ledger during a replay."""
    d = tempfile.mkdtemp(prefix='fx-probe-')
    try:
        src = 'act n = notes.write(text="a").'
        run(src, Host({'notes.write': {'ok': True}}), folder=d, side_effects=True)
        rep, _ = run(src, None, folder=d, replay=True)
        return rep['status'] == 'done'
    finally:
        shutil.rmtree(d, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='fx-test-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        FX.set_catalogue(None)
        self.addCleanup(FX.set_catalogue, None)
        FX.SYNC = False                                         # durability is not what these tests measure
        self.addCleanup(setattr, FX, 'SYNC', True)

    def ledger(self):
        with open(os.path.join(self.dir, FX.LEDGER), encoding='utf-8') as f:
            return [json.loads(x) for x in f if x.strip()]


class Parsing(Base):
    def test_both_statements_and_their_parts(self):
        prog = S.parse('observe busy: List of Record {start: Text} = calendar.free_busy(days=2).\n'
                       'act booked = calendar.add(title="Review", start="x") with key="review", timeout=30.\n'
                       'act home.device(device="light", action="off").')
        o, a, bare = prog['statements']
        self.assertEqual((o.k, o.name, o.capability, sorted(o.args)), ('observe', 'busy', 'calendar.free_busy', ['days']))
        self.assertEqual(o.type['k'], 'list')
        self.assertEqual((a.k, a.name, sorted(a.options)), ('act', 'booked', ['key', 'timeout']))
        self.assertIsNone(bare.name)

    def test_a_sentence_that_starts_with_the_word_stays_prose(self):
        prog = S.parse('Observe the sky carefully.\nAct now (before it is too late).\nact mail.send(to="a@b.c").')
        self.assertEqual([s.k for s in prog['statements']], ['ask', 'ask', 'act'])

    def test_refused_forms(self):
        for src, part in (('observe calendar.free_busy(days=2).', 'needs a name'),
                          ('act x = calendar.add("Review").', 'are named'),
                          ('act x = calendar.add(title="a") with speed=3.', 'unknown act option'),
                          ('observe x = web.fetch(url="u") with allow_untrusted=["url"].', 'option of act'),
                          ('act x = Calendar.Add(title="a").', 'not a capability name')):
            with self.assertRaises(S.SymblicError) as cm:
                S.parse(src)
            self.assertIn(part, cm.exception.message, src)

    def test_plan_rows_show_the_class_and_the_label(self):
        rows = [r for r in S.check('observe b = calendar.free_busy(days=2).\nact calendar.add(title="x").')['plan']]
        self.assertEqual([r.get('class') for r in rows], ['observed', 'effect'])
        self.assertIn('calendar.free_busy(days)', rows[0]['label'])


class Schema(Base):
    def test_the_subset_capabilities_use(self):
        s = {**OBJ, 'properties': {'n': {'type': 'integer', 'minimum': 1, 'maximum': 3},
                                   'tags': {'type': 'array', 'maxItems': 2, 'items': {'type': 'string', 'pattern': '^[a-z]+$'}},
                                   'mode': {'enum': ['a', 'b']}}, 'required': ['n']}
        self.assertEqual(FX.schema_errors({'n': 2, 'tags': ['ab'], 'mode': 'a'}, s), [])
        bad = FX.schema_errors({'n': 9, 'tags': ['ab', 'C', 'x'], 'mode': 'z', 'extra': 1}, s)
        text = ' | '.join(bad)
        for part in ('n is above 3', 'more than 2 items', 'tags[2] does not match', 'mode must be one of',
                     'extra is not an argument'):
            self.assertIn(part, text)
        self.assertEqual(FX.schema_errors({}, s), ['n is required'])
        self.assertEqual(FX.schema_errors({'n': True}, s), ['n must be integer'])     # a bool is not an integer

    def test_every_element_is_checked_and_an_oversized_value_is_refused(self):
        ints = {'type': 'array', 'items': {'type': 'integer'}}
        self.assertEqual(FX.schema_errors([1] * 200 + ['bad'], ints), ['item 201 must be integer'])
        self.assertEqual(FX.schema_errors([1] * 5000, ints), [])
        huge = FX.schema_errors([1] * (FX.MAX_CHECKED_VALUES + 5), ints)
        self.assertEqual(len(huge), 1)
        self.assertIn('too large or too deeply nested', huge[0])
        deep = cur = []
        for _ in range(FX.MAX_ARGUMENT_DEPTH + 3):
            cur.append([])
            cur = cur[0]
        self.assertIn('too large or too deeply nested', FX.schema_errors(deep, {})[0])

    def test_json_equality_keeps_true_apart_from_one(self):
        self.assertTrue(FX.schema_errors(True, {'enum': [1]}))
        self.assertTrue(FX.schema_errors(1, {'const': True}))
        self.assertTrue(FX.schema_errors({'a': [True]}, {'enum': [{'a': [1]}]}))
        self.assertEqual(FX.schema_errors(1, {'enum': [1.0]}), [])                 # numbers compare by value
        self.assertEqual(FX.schema_errors({'a': [1, 'x']}, {'const': {'a': [1, 'x']}}), [])
        self.assertEqual(FX.schema_errors(False, {'enum': [True, False]}), [])

    def test_arguments_are_json(self):
        self.assertEqual(FX.to_argument((1, S.coerce('0.5', {'k': 'number'}), 'x', frozenset({2, 1}), {'b': None})),
                         [1, 0.5, 'x', [1, 2], {'b': None}])


class Static(Base):
    def test_typing_against_the_catalogue(self):
        self.assertEqual(errors('observe b = calendar.free_busy(days=2).\nact calendar.add(title="x").'), [])
        for src, part in (('observe b = calendar.busy(days=2).', 'no capability calendar.busy (calendar has: calendar.add'),
                          ('observe b = calendar.add(title="x").', 'is not a read'),
                          ('observe b = calendar.free_busy(weeks=2).', 'has no argument weeks'),
                          ('observe b = calendar.free_busy(days=99).', 'days is above 31'),
                          ('observe b = calendar.free_busy(days="two").', 'days must be integer'),
                          ('act calendar.add(start="x").', 'needs the argument title'),
                          ('act vault.report().', 'never available')):
            self.assertTrue(any(part in m for m in errors(src)), (src, errors(src)))

    def test_computed_arguments_wait_for_the_run(self):
        self.assertEqual(errors('let n = 40.\nobserve b = calendar.free_busy(days=n).'), [])
        rep, _ = run('let n = 40.\nobserve b = calendar.free_busy(days=n).', host := Host())
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('days is above 31', rep['error']['message'])
        self.assertEqual(host.calls, [])                       # refused before the host was asked

    def test_without_a_catalogue_the_statement_is_marked_unchecked(self):
        res = FX.check('observe b = calendar.free_busy(days=2).', None)
        self.assertTrue(res['ok'])
        self.assertTrue(any('unchecked' in w['message'] for w in res['warnings']))

    def test_an_act_on_a_read_is_a_warning_not_an_error(self):
        res = FX.check('act b = calendar.free_busy(days=2).', CATALOGUE)
        self.assertTrue(res['ok'])
        self.assertTrue(any('only reads' in w['message'] for w in res['warnings']))

    def test_not_inside_a_routine_or_a_retry_window(self):
        src = ('routine r(q: Text) -> Int do\n  observe b = calendar.free_busy(days=2).\n  ask g: Int "{q}"\n'
               '  return g.\nend.')
        self.assertTrue(any('cannot be used inside a routine' in m for m in errors(src)))
        src = ('ask n: Int in 1..9 "pick" by "fake:a"\nact calendar.add(title="x {n}").\nensure n = 3 else retry.')
        self.assertTrue(any('act at line 2 lies between the ask at line 1 and the ensure at line 3' in m
                            for m in errors(src)), errors(src))
        src = ('ask n: Int in 1..9 "pick" by "fake:a"\nobserve b = calendar.free_busy(days=n).\nensure n = 3 else retry.')
        self.assertEqual(errors(src), [])                      # reading again is harmless

    def test_effect_rows_and_catalogue_digest(self):
        res = FX.check('observe b = calendar.free_busy(days=2).\nact calendar.add(title="x").', CATALOGUE)
        self.assertEqual([(e['kind'], e['capability'], e['effect'], e['policy']) for e in res['effects']],
                         [('observe', 'calendar.free_busy', 'read', 'auto'), ('act', 'calendar.add', 'write-external', 'confirm')])
        self.assertEqual(res['catalogue'], FX.catalogue_digest(CATALOGUE))
        other = FX.normalize_catalogue(CAT[:-1])
        self.assertNotEqual(FX.catalogue_digest(other), res['catalogue'])


class Flow(Base):
    PAGE = 'observe page: Text = web.fetch(url="https://example.org").\n'

    def test_untrusted_text_cannot_become_an_argument_of_an_act(self):
        msgs = errors(self.PAGE + 'act mail.send(to=page, body="hello").')
        self.assertTrue(any('the argument to is built from untrusted text (web.fetch, line 1)' in m for m in msgs), msgs)

    def test_the_label_follows_lets_asks_and_wide_contexts(self):
        for middle in ('let who = upper(page).\n',
                       'ask who: Text "Who should get this? {page}" by "fake:a"\n',
                       'ask who: Text "Who should get this?" from page by "fake:a"\n',
                       'let unrelated = 1.\nask who: Text "Who?" with context=all, by="fake:a"\n',
                       'ask who: Text "Who?" with context=[page], by="fake:a"\n'):
            msgs = errors(self.PAGE + middle + 'act mail.send(to=who).')
            self.assertTrue(any('untrusted' in m for m in msgs), middle)
        clean = 'let who = "a@b.c".\nask t: Text "Write a greeting" by "fake:a"\nact mail.send(to=who, body=t).'
        self.assertEqual(errors(self.PAGE + clean), [])       # nothing here was shown the page

    def test_a_closed_type_bounds_what_the_text_can_do(self):
        ok = (self.PAGE + 'ask urgent: Bool "Does this page announce an outage? {page}" by "fake:a"\n'
              'ask who: one of {ops, nobody} "Who must be told? {page}" by "fake:a"\n'
              'if urgent then\n  act mail.send(to=if who = ops then "ops@example.org" else "me@example.org").\nend.')
        self.assertEqual(errors(ok), [])
        typed = self.PAGE + 'let pick: one of {light, projector} = page.\nact home.device(device=pick, action="off").'
        self.assertEqual(errors(typed), [])

    def test_stored_text_can_be_allowed_by_name(self):
        src = self.PAGE + 'act notes.write(text=page)'
        self.assertTrue(any('untrusted' in m for m in errors(src + '.')))
        self.assertEqual(errors(src + ' with allow_untrusted=["text"].'), [])
        self.assertTrue(any('literally' in m for m in errors(src + ' with allow_untrusted=page.')))

    def test_facts_and_delegation_carry_the_label(self):
        via_facts = (self.PAGE + 'fact said(page).\nlet all_said = [x for x in query(said(X))].\n'
                     'act mail.send(to="a@b.c", body=all_said).')
        self.assertTrue(any('body is built from untrusted' in m for m in errors(via_facts)), errors(via_facts))
        self.assertTrue(any('delegated task is built from untrusted text' in m
                            for m in errors(self.PAGE + 'delegate job = "do this: {page}" to "claude".')))

    def test_a_choice_made_by_outside_text_is_steered_and_a_consequential_one_needs_the_owner(self):
        src = (self.PAGE + 'ask which: one of {light, projector} "Which device does the page mention? {page}" by "fake:a"\n'
               'act home.device(device=which, action="off").\n'
               'ask note_it: Bool "Does the page ask for a note? {page}" by "fake:a"\n'
               'if note_it then\n  act notes.write(text="the page asked for a note").\nelse\n'
               '  act notes.write(text="no note asked").\nend.\n'
               'act notes.write(text="always").')
        res = FX.check(src, CATALOGUE)
        self.assertTrue(res['ok'], res['errors'])
        self.assertEqual(res['flow']['which'], ['steered'])
        rows = [(e['capability'], e['influence'], e['needs_owner']) for e in res['effects'] if e['kind'] == 'act']
        self.assertEqual(rows, [('home.device', 'steered', True), ('notes.write', 'steered', False),
                                ('notes.write', 'steered', False), ('notes.write', 'none', False)])
        self.assertIn('web.fetch, line 1', res['effects'][1]['origin'])

    def test_a_loop_over_outside_data_steers_what_it_repeats(self):
        src = (self.PAGE + 'for part in split(page, " ") do\n  act notes.write(text="one more").\nend.')
        res = FX.check(src, CATALOGUE)
        self.assertTrue(res['ok'], res['errors'])
        self.assertEqual([e['influence'] for e in res['effects'] if e['kind'] == 'act'], ['steered'])

    def test_personal_data_cannot_leave_through_a_capability_that_sends_its_arguments_out(self):
        src = ('observe busy: Text = calendar.free_busy(days=2).\nobserve hits = web.search(query="meetings {busy}").')
        self.assertTrue(any('carries personal data and web.search sends its arguments out' in m for m in errors(src)))
        self.assertEqual(errors('observe hits = web.search(query="bridge cable strength").'), [])

    def test_personal_data_shown_to_an_applicator_is_a_warning(self):
        res = FX.check('observe busy = calendar.free_busy(days=2).\n'
                       'ask best: Int in 1..3 "Which hour?" from busy by "claude:haiku"', CATALOGUE)
        self.assertTrue(res['ok'])
        self.assertTrue(any('personal data' in w['message'] for w in res['warnings']))
        self.assertEqual(res['flow'].get('busy'), ['personal'])


class Execution(Base):
    def test_observe_binds_a_typed_result_with_its_evidence(self):
        host = Host({'calendar.free_busy': [{'start': '09:00', 'end': '10:00', 'extra': 1}]})
        rep, _ = run('observe busy: List of Record {start: Text, end: Text} = calendar.free_busy(days=2).\n'
                     'show len(busy).', host, folder=self.dir)
        self.assertEqual(rep['status'], 'done', rep['error'])
        b = binding(rep, 'busy')
        self.assertEqual((b['class'], b['value']), ('observed', [{'end': '10:00', 'start': '09:00'}]))
        ev = b['meta']['evidence']
        self.assertEqual((ev['mechanism'], ev['capability'], ev['trusted_acquisition'], ev['independence']),
                         ('observation', 'calendar.free_busy', True, 'not_established'))
        self.assertEqual(ev['declaration'], {'mode': 'capability:calendar', 'sources': ['calendar.free_busy'],
                                             'origin': 'catalogue'})
        self.assertEqual([r['phase'] for r in self.ledger()], ['intent', 'done'])
        self.assertEqual(host.calls[0]['args'], {'days': 2})
        self.assertEqual(rep['classes'].get('observed'), 1)

    def test_an_act_needs_side_effects_and_a_host(self):
        src = 'act done = calendar.add(title="Review").'
        rep, _ = run(src, host := Host())
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'effect'))
        self.assertEqual(host.calls, [])
        rep, _ = run(src, None, side_effects=True)
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('no capability host', rep['error']['message'])
        rep, _ = run(src, host := Host({'calendar.add': {'id': 'e1'}}), side_effects=True)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual((binding(rep, 'done')['class'], binding(rep, 'done')['value']), ('effect', {'id': 'e1'}))
        self.assertEqual(len(host.calls), 1)

    def test_the_same_action_happens_once_in_a_run_unless_keyed_apart(self):
        host = Host({'notes.write': {'ok': True}})
        rep, _ = run('act a = notes.write(text="x").\nact b = notes.write(text="x").\n'
                     'act c = notes.write(text="x") with key="again".\n'
                     'for t in ["p", "p", "q"] do\n  act notes.write(text=t).\nend.', host, side_effects=True)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual([c['args']['text'] for c in host.calls], ['x', 'x', 'p', 'q'])
        self.assertEqual([c['key'] for c in host.calls], ['', 'again', '', ''])
        self.assertTrue(binding(rep, 'b')['meta']['replayed'])

    def test_a_second_pass_over_the_same_folder_calls_nothing(self):
        src = ('observe busy = calendar.free_busy(days=2).\nact made = calendar.add(title="Review").\n'
               'show made.id.')
        host = Host({'calendar.free_busy': [1], 'calendar.add': lambda e: {'id': f'e{len(host.calls)}'}})
        first, _ = run(src, host, folder=self.dir, side_effects=True)
        second, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((first['status'], second['status']), ('done', 'done'))
        self.assertEqual(len(host.calls), 2)                   # one observe, one act, both in the first pass
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(second['outputs'][0]['text'], first['outputs'][0]['text'])

    def test_preview_and_replay_never_call(self):
        src = 'observe busy = calendar.free_busy(days=2).'
        rep, _ = run(src, host := Host(), preview=True)
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'effect'))
        rep, _ = run(src, host, folder=self.dir, replay=True)
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('no recorded outcome', rep['error']['message'])
        self.assertEqual(host.calls, [])
        run(src, Host({'calendar.free_busy': [7]}), folder=self.dir)
        rep, _ = run(src, None, folder=self.dir, replay=True)     # no host at all: the ledger answers
        self.assertEqual((rep['status'], binding(rep, 'busy')['value']), ('done', [7]))

    def test_an_act_replays_from_its_ledger(self):
        if not acts_run_in_replay():
            self.skipTest('the core still refuses every effect-class extension in a replay')
        src = 'act made = calendar.add(title="Review").'
        run(src, Host({'calendar.add': {'id': 'e1'}}), folder=self.dir, side_effects=True)
        rep, _ = run(src, None, folder=self.dir, replay=True)
        self.assertEqual((rep['status'], binding(rep, 'made')['value']), ('done', {'id': 'e1'}))

    def test_an_unknown_outcome_blocks_until_the_owner_says(self):
        src = 'act sent = mail.send(to="a@b.c", body="hi").'
        host = Host({'mail.send': {'status': 'unknown', 'error': 'connection lost'}})
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'uncertain'))
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['error']['kind'], len(host.calls)), ('uncertain', 1))     # not called again
        eid = self.ledger()[-1]['id']
        FX.resolve(os.path.join(self.dir, FX.LEDGER), eid, True, {'id': 'm1'})
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], binding(rep, 'sent')['value'], len(host.calls)), ('done', {'id': 'm1'}, 1))
        with self.assertRaises(ValueError):
            FX.resolve(os.path.join(self.dir, FX.LEDGER), eid, False)

    def test_resolved_as_not_happened_it_runs_again(self):
        src = 'act sent = mail.send(to="a@b.c").'
        host = Host({'mail.send': RuntimeError('boom')})
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual(rep['error']['kind'], 'uncertain')    # a host that broke mid-call may have acted
        FX.resolve(os.path.join(self.dir, FX.LEDGER), self.ledger()[-1]['id'], False)
        host.results['mail.send'] = {'id': 'm2'}
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 2))
        self.assertEqual([r['phase'] for r in self.ledger()], ['intent', 'unknown', 'failed', 'intent', 'done'])
        self.assertEqual(self.ledger()[-1]['attempt'], 2)

    def test_an_interrupted_intent_is_unknown_for_an_act_and_retried_for_reads_and_idempotent_acts(self):
        class Crash(BaseException):
            """The process dies inside the call: the intent row is all that was written."""

        def crash(effect):
            raise Crash()
        dying = Host({'notes.write': crash, 'calendar.free_busy': crash, 'mail.send': crash})
        for src in ('observe b = calendar.free_busy(days=2).', 'act n = notes.write(text="x").', 'act s = mail.send(to="a@b.c").'):
            with self.assertRaises(Crash):
                run(src, dying, folder=self.dir, side_effects=True)
        self.assertEqual([r['phase'] for r in self.ledger()], ['intent', 'intent', 'intent'])
        host = Host({'notes.write': {'ok': True}, 'calendar.free_busy': [1], 'mail.send': {'id': 'm'}})
        # effects_wait=0: the "crashed" claimant is this very process, which a real claimant would wait for
        rep, _ = run('observe b = calendar.free_busy(days=2).\nact n = notes.write(text="x").', host, folder=self.dir,
                     side_effects=True, effects_wait=0)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 2))
        rep, _ = run('act s = mail.send(to="a@b.c").', host, folder=self.dir, side_effects=True, effects_wait=0)
        self.assertEqual((rep['error']['kind'], len(host.calls)), ('uncertain', 2))

    def test_a_bare_interrupted_row_is_retried_for_a_read_and_refused_for_any_action(self):
        # a row an older writer left: no contract, no labels. A read changes nothing and is asked again; an
        # action, even an idempotent one, cannot be vouched for by whatever program comes next
        led = FX.Ledger(os.path.join(self.dir, FX.LEDGER))
        for cap, args in (('notes.write', {'text': 'x'}), ('calendar.free_busy', {'days': 2})):
            kind = 'observe' if cap == 'calendar.free_busy' else 'act'
            led.append({'id': FX.effect_id(cap, args, '', kind), 'kind': kind, 'capability': cap, 'args': args,
                        'phase': 'intent', 'attempt': 1})
        host = Host({'notes.write': {'ok': True}, 'calendar.free_busy': [1]})
        rep, _ = run('observe b = calendar.free_busy(days=2).', host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 1))
        rep, _ = run('act n = notes.write(text="x").', host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['error']['kind'], len(host.calls)), ('uncertain', 1))
        self.assertIn('recorded without its full contract and approval labels', rep['error']['message'])
        self.assertEqual(self.ledger()[-1]['phase'], 'done')         # the read's; nothing was written for the act

    def test_a_failed_outcome_fails_the_run_and_may_be_tried_again(self):
        host = Host({'calendar.add': {'status': 'failed', 'error': 'refused: quota'}})
        src = 'act made = calendar.add(title="x").'
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'effect'))
        self.assertIn('refused: quota', rep['error']['message'])
        host.results['calendar.add'] = {'id': 'e9'}
        rep, _ = run(src, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 2))

    def test_an_observe_that_breaks_is_a_failure_not_an_unknown(self):
        rep, _ = run('observe b = calendar.free_busy(days=2).', Host({'calendar.free_busy': RuntimeError('down')}))
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'effect'))

    def test_the_result_must_fit_the_type(self):
        rep, _ = run('observe n: Int = calendar.free_busy(days=2).', Host({'calendar.free_busy': 'many'}))
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'type'))
        self.assertIn('returned something the type does not accept', rep['error']['message'])

    def test_an_act_in_a_retry_window_is_refused_at_run_time_too(self):
        host = Host({'calendar.add': {'id': 'e'}})
        rep, _ = run('ask n: Int in 1..9 "pick" by "fake:a"\nact calendar.add(title="x {n}").\n'
                     'ensure n = 3 else retry.', host, Apps({'a': [4, 5, 3]}), side_effects=True)
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(host.calls, [])
        self.assertIn('retry', rep['error']['message'])

    def test_an_observe_in_a_retry_window_reads_again_for_the_new_answer(self):
        # ask -> observe -> check -> re-ask is the search-and-reformulate loop: a read may repeat, an act may not
        host = Host({'calendar.free_busy': lambda e: list(range(e['args']['days']))})
        rep, _ = run('ask n: Int in 1..9 "How many days?" by "fake:a"\nobserve b = calendar.free_busy(days=n).\n'
                     'ensure len(b) >= 3 else retry.', host, Apps({'a': [1, 2, 3]}))
        if rep['status'] == 'failed' and 'retry window' in rep['error']['message']:
            self.skipTest('the core still refuses a read inside a retry window at run time')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual([c['args']['days'] for c in host.calls], [1, 2, 3])
        self.assertEqual(binding(rep, 'b')['value'], [0, 1, 2])

    def test_the_limit_on_observations_and_actions(self):
        host = Host({'notes.write': {'ok': True}})
        rep, _ = run('for i in 1..5 do\n  act notes.write(text="n{i}").\nend.', host, side_effects=True, max_effects=3)
        self.assertEqual((rep['status'], rep['error']['kind'], len(host.calls)), ('failed', 'budget', 3))

    def test_program_scope_holds_across_runs(self):
        shared = os.path.join(self.dir, 'program-effects.jsonl')
        src = 'act sent = mail.send(to="a@b.c", body="digest") with key="digest-2026-10-03", scope="program".'
        host = Host({'mail.send': {'id': 'm1'}})
        for sub in ('r1', 'r2'):
            folder = os.path.join(self.dir, sub)
            os.makedirs(folder)
            rep, _ = run(src, host, folder=folder, side_effects=True, effects_ledger=shared)
            self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(S.parse('act mail.send(to="x") with scope=program, key="k".')['statements'][0]
                         .options['scope'].parts, ['program'])
        rep, _ = run('act mail.send(to="a@b.c") with scope=program.', host, side_effects=True, effects_ledger=shared)
        self.assertIn('needs a key', rep['error']['message'])
        rep, _ = run(src, host, side_effects=True)
        self.assertIn('keeps a ledger for the program', rep['error']['message'])

    def test_a_replay_needs_only_the_run_folder(self):
        shared = os.path.join(self.dir, 'program-effects.jsonl')
        folder = os.path.join(self.dir, 'run')
        os.makedirs(folder)
        src = ('observe page: Text = web.fetch(url="https://example.org").\n'
               'act sent = mail.send(to="a@b.c", body="digest") with key="d1", scope="program".')
        host = Host({'web.fetch': 'hello', 'mail.send': {'id': 'm1'}})
        live, _ = run(src, host, folder=folder, side_effects=True, effects_ledger=shared)
        self.assertEqual(live['status'], 'done', live['error'])
        with open(os.path.join(folder, FX.CATALOGUE_FILE), encoding='utf-8') as f:
            frozen = json.load(f)
        self.assertEqual(sorted(frozen['capabilities']), ['mail.send', 'web.fetch'])     # only what the program names
        self.assertEqual(frozen['digest'], FX.catalogue_digest(CATALOGUE))
        os.unlink(shared)                                      # the program's ledger is gone: the run kept a copy
        os.unlink(shared + '.lock')
        again, _ = run(src, None, folder=folder, replay=True, effects_ledger=shared)
        self.assertEqual(again['status'], 'done', again['error'])
        self.assertFalse(os.path.exists(shared))               # a replay never opens anything outside its folder
        self.assertFalse(os.path.exists(shared + '.lock'))
        self.assertEqual(again['fingerprint'], live['fingerprint'])
        for name in ('page', 'sent'):
            a, b = binding(live, name)['meta']['evidence'], binding(again, name)['meta']['evidence']
            self.assertEqual({k: v for k, v in a.items() if k != 'replayed'},
                             {k: v for k, v in b.items() if k != 'replayed'})
        self.assertTrue(binding(again, 'page')['meta']['evidence']['untrusted'])

    def test_a_resume_survives_an_edit_but_a_replay_is_pinned_to_its_source(self):
        src = 'act sent = mail.send(to="a@b.c").'
        host = Host({'mail.send': {'id': 'm1'}})
        run(src, host, folder=self.dir, side_effects=True)
        edited = 'note reworded a comment.\n' + src + '\nshow sent.id.'
        rep, _ = run(edited, host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 1))        # the mail is not sent again
        rep, _ = run(edited, None, folder=self.dir, replay=True)
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('different program text', rep['error']['message'])
        rep, _ = run(src, None, folder=self.dir, replay=True)
        self.assertEqual(rep['status'], 'done', rep['error'])

    def test_a_run_is_pinned_to_the_capabilities_it_names(self):
        src = 'observe b = calendar.free_busy(days=2).\nobserve c = calendar.free_busy(days=3).'
        first = Host({'calendar.free_busy': {'status': 'failed', 'error': 'busy'}})
        run(src, first, folder=self.dir)                       # the run began and froze its capabilities
        grown = CAT + [{'name': 'calendar.other', 'effect': 'read', 'policy': 'auto', 'params': OBJ}]
        rep, _ = run(src, Host({'calendar.free_busy': [1]}, cat=grown), folder=self.dir)
        self.assertEqual(rep['status'], 'done', rep['error'])  # the catalogue may grow around it
        changed = [dict(c, effect='write-local') if c['name'] == 'calendar.free_busy' else c for c in CAT]
        host = Host({'calendar.free_busy': [1]}, cat=changed)
        rep, _ = run('observe d = calendar.free_busy(days=4).\n' + src, host, folder=self.dir)
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('calendar.free_busy changed since this run began', rep['error']['message'])
        self.assertEqual(host.calls, [])
        with open(os.path.join(self.dir, FX.CATALOGUE_FILE), 'w', encoding='utf-8') as f:
            f.write('{"version": 1, "capabil')
        rep, _ = run(src, Host({'calendar.free_busy': [1]}), folder=self.dir)
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'uncertain'))
        self.assertIn('cannot be read', rep['error']['message'])

    def test_two_runs_sharing_a_program_ledger_perform_the_action_once(self):
        shared = os.path.join(self.dir, 'program-effects.jsonl')
        src = 'act sent = mail.send(to="a@b.c", body="digest") with key="same", scope=program.'
        calls, inside, release = [], threading.Event(), threading.Event()

        def slow_send(effect):
            calls.append(effect['id'])
            inside.set()
            release.wait(10)
            return {'status': 'done', 'result': {'id': f'm{len(calls)}'}}
        reports = {}

        def go(name):
            folder = os.path.join(self.dir, name)
            os.makedirs(folder)
            reports[name], _ = run(src, Host({'mail.send': slow_send}), folder=folder, side_effects=True,
                                   effects_ledger=shared)
        a = threading.Thread(target=go, args=('a',))
        a.start()
        self.assertTrue(inside.wait(10))                       # run a holds the claim and is mid-call
        b = threading.Thread(target=go, args=('b',))
        b.start()
        time.sleep(0.6)                                        # run b finds the live claim and waits for its outcome
        release.set()
        a.join(20)
        b.join(20)
        self.assertEqual([reports[n]['status'] for n in 'ab'], ['done', 'done'], reports)
        self.assertEqual(len(calls), 1)
        self.assertEqual(binding(reports['a'], 'sent')['value'], binding(reports['b'], 'sent')['value'])
        self.assertTrue(binding(reports['b'], 'sent')['meta']['replayed'])

    def test_simultaneous_claims_have_one_winner(self):
        shared = os.path.join(self.dir, 'program-effects.jsonl')
        src = 'act n = home.device(device="light", action="on") with key="k", scope="program".'
        calls, gate, reports = [], threading.Barrier(4), {}

        def count(effect):
            calls.append(1)
            time.sleep(0.05)
            return {'status': 'done', 'result': {'ok': True}}

        def go(i):
            folder = os.path.join(self.dir, f'r{i}')
            os.makedirs(folder)
            gate.wait(10)
            reports[i], _ = run(src, Host({'home.device': count}), folder=folder, side_effects=True,
                                effects_ledger=shared)
        threads = [threading.Thread(target=go, args=(i,)) for i in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(30)
        self.assertEqual(len(calls), 1)
        self.assertEqual({r['status'] for r in reports.values()}, {'done'})

    def test_concurrent_reads_and_idempotent_actions_share_one_outcome(self):
        shared = os.path.join(self.dir, 'program-effects.jsonl')
        for kind, src, cap in (('observe', 'observe v = calendar.free_busy(days=2) with key="k", scope=program.',
                                'calendar.free_busy'),
                               ('act', 'act v = notes.write(text="x") with key="k", scope=program.', 'notes.write')):
            calls, gate, reports = [], threading.Barrier(3), {}

            def answer(effect, calls=calls):
                calls.append(1)
                time.sleep(0.3)
                return {'status': 'done', 'result': {'n': len(calls)}}

            def go(i, src=src, cap=cap, gate=gate, reports=reports, kind=kind, answer=answer):
                folder = os.path.join(self.dir, f'{kind}{i}')
                os.makedirs(folder)
                gate.wait(10)
                reports[i], _ = run(src, Host({cap: answer}), folder=folder, side_effects=True, effects_ledger=shared)
            threads = [threading.Thread(target=go, args=(i,)) for i in range(3)]
            for th in threads:
                th.start()
            for th in threads:
                th.join(30)
            self.assertEqual(len(calls), 1, kind)
            self.assertEqual({json.dumps(binding(r, 'v')['value']) for r in reports.values()}, {'{"n": 1}'}, kind)

    def test_an_altered_outcome_is_not_served(self):
        src = 'observe n: Int = calendar.free_busy(days=2).'
        run(src, Host({'calendar.free_busy': 7}), folder=self.dir)
        path = os.path.join(self.dir, FX.LEDGER)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('"result": 7', text)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text.replace('"result": 7', '"result": 99'))       # still valid JSON, the hash is the old one
        for opts in ({'replay': True}, {}):
            rep, _ = run(src, None if opts else Host({'calendar.free_busy': 7}), folder=self.dir, **opts)
            self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'uncertain'), opts)
            self.assertIn('was altered', rep['error']['message'])

    def test_the_owners_word_keeps_the_source_pin(self):
        src = 'act sent = mail.send(to="a@b.c").'
        run(src, Host({'mail.send': {'status': 'unknown', 'error': 'lost'}}), folder=self.dir, side_effects=True)
        path = os.path.join(self.dir, FX.LEDGER)
        row = FX.resolve(path, self.ledger()[-1]['id'], True, {'id': 'm1'})
        self.assertTrue(row['source_sha256'] and row['spec']['effect'] == 'write-external' and FX.intact(row))
        rep, _ = run('note edited.\n' + src, None, folder=self.dir, replay=True)
        self.assertIn('different program text', rep['error']['message'])
        rep, _ = run(src, None, folder=self.dir, replay=True)
        self.assertEqual((rep['status'], binding(rep, 'sent')['value']), ('done', {'id': 'm1'}))

    def test_nothing_is_performed_when_the_catalogue_cannot_be_pinned(self):
        host = Host({'calendar.free_busy': [1]})
        real = FX._freeze
        FX._freeze = lambda *a, **k: False
        try:
            rep, _ = run('observe b = calendar.free_busy(days=2).', host, folder=self.dir)
        finally:
            FX._freeze = real
        self.assertEqual((rep['status'], rep['error']['kind'], host.calls), ('failed', 'uncertain', []))

    def test_a_claim_left_by_a_dead_process_is_unknown_at_once(self):
        path = os.path.join(self.dir, FX.LEDGER)
        args = {'to': 'a@b.c'}
        FX.Ledger(path).append({'id': FX.effect_id('mail.send', args), 'kind': 'act', 'capability': 'mail.send',
                                'args': args, 'phase': 'intent', 'attempt': 1,
                                'owner': {'host': socket.gethostname(), 'pid': 2 ** 22 + 12345, 'token': 'gone'}})
        t0 = time.time()
        rep, _ = run('act s = mail.send(to="a@b.c").', host := Host({'mail.send': {'id': 'm'}}), folder=self.dir,
                     side_effects=True)
        self.assertEqual((rep['error']['kind'], host.calls), ('uncertain', []))
        self.assertLess(time.time() - t0, 5)

    def test_a_damaged_ledger_performs_nothing_new_and_an_unfinished_last_row_is_cut(self):
        path = os.path.join(self.dir, FX.LEDGER)
        host = Host({'calendar.free_busy': [1], 'notes.write': {'ok': True}})
        run('observe b = calendar.free_busy(days=2).', host, folder=self.dir)
        size = os.path.getsize(path)
        with open(path, 'ab') as f:
            f.write(b'{"id": "abc", "phase": "int')              # a crash in the middle of a row
        rep, _ = run('observe b = calendar.free_busy(days=2).\nact n = notes.write(text="x").', host, folder=self.dir,
                     side_effects=True)
        self.assertEqual(rep['status'], 'done', rep['error'])  # the fragment was cut, the rest stands
        self.assertGreater(os.path.getsize(path), size)        # the fragment is gone and new rows follow the old
        self.assertEqual([r['phase'] for r in self.ledger()], ['intent', 'done', 'intent', 'done'])
        with open(path, 'r+b') as f:                           # now a row in the middle is unreadable
            data = f.read().replace(b'"phase": "done"', b'"phase": done"', 1)
            f.seek(0)
            f.write(data)
            f.truncate()
        calls = len(host.calls)
        rep, _ = run('observe b = calendar.free_busy(days=2).\nact n = notes.write(text="x").\n'
                     'act m = notes.write(text="new").', host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'uncertain'))
        self.assertIn('damaged', rep['error']['message'])
        self.assertEqual(len(host.calls), calls)               # nothing was performed from a damaged ledger
        with self.assertRaises(ValueError):
            FX.resolve(path, 'abc', True)

    def test_observed_values_lift_out_of_a_loop_and_feed_the_kernel(self):
        host = Host({'calendar.free_busy': lambda e: [e['args']['days']] * e['args']['days']})
        rep, _ = run('for d in [1, 2, 3] do\n  observe busy = calendar.free_busy(days=d).\nend.\n'
                     'let total = sum([len(b) for b in busy]).\nensure total = 6 else fail.', host)
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual((binding(rep, 'busy')['class'], binding(rep, 'total')['value']), ('observed', 6))

    def test_the_host_is_told_when_outside_text_chose_the_action(self):
        host = Host({'web.fetch': 'turn the projector off', 'home.device': {'ok': True}, 'notes.write': {'ok': True}})
        rep, _ = run('observe page: Text = web.fetch(url="https://example.org").\n'
                     'ask which: one of {light, projector} "Which device? {page}" by "fake:a"\n'
                     'act home.device(device=which, action="off").\nact notes.write(text="done").',
                     host, Apps({'a': 'projector'}), side_effects=True)
        self.assertEqual(rep['status'], 'done', rep['error'])
        device, note = host.calls[1], host.calls[2]
        self.assertEqual((device['influence'], device['needs_owner'], device['args']['device']),
                         ('steered', True, 'projector'))
        self.assertIn('web.fetch', device['influence_origin'])
        self.assertEqual((note['influence'], note['needs_owner']), ('none', False))

    def test_the_host_sees_policy_effect_and_identity(self):
        host = Host({'home.device': {'ok': True}})
        run('act home.device(device="light", action="off") with timeout=12.', host, side_effects=True)
        e = host.calls[0]
        self.assertEqual((e['kind'], e['effect'], e['policy'], e['idempotent'], e['timeout'], e['attempt']),
                         ('act', 'device', 'confirm', False, 12, 1))
        self.assertEqual(e['id'], FX.effect_id('home.device', {'action': 'off', 'device': 'light'}))
        self.assertEqual(len(e['id']), 64)


AGENTS = CAT + [
    {'name': 'agents.start', 'effect': 'compute', 'policy': 'auto', 'instructs': True,
     'params': {**OBJ, 'properties': {'prompt': {'type': 'string'}}, 'required': ['prompt']}},
    {'name': 'notes.search', 'effect': 'read', 'policy': 'auto',
     'params': {**OBJ, 'properties': {'query': {'type': 'string'}}, 'required': ['query']}},
]
PAGE = 'observe page: Record {text: Text} = web.fetch(url="https://a.example").\n'


class Review(unittest.TestCase):
    """Defects an adversarial review found on 2026-10-03, each with the case that showed it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='fx-review-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        sync = unittest.mock.patch.object(FX, 'SYNC', False)
        sync.start()
        self.addCleanup(sync.stop)

    def plan(self, source, cat=AGENTS):
        res = FX.check(source, cat)
        return res, [(e['capability'], e['influence'], e['needs_owner']) for e in res['effects'] if e['kind'] == 'act']

    def test_outside_text_written_into_a_weighty_action_needs_the_owner(self):
        res, acts = self.plan(PAGE + 'act mail.send(to="me@example.org", body=page.text) with allow_untrusted=["body"].\n')
        self.assertTrue(res['ok'], res['errors'])
        self.assertEqual(acts, [('mail.send', 'untrusted', True)])
        # the same act under a steered condition: still untrusted, still the owner's
        res, acts = self.plan(PAGE + 'ask go: Bool "Send it? {page.text}" by "fake:a"\nif go then\n'
                              '  act mail.send(to="me@example.org", body=page.text) with allow_untrusted=["body"].\nend.\n')
        self.assertEqual(acts, [('mail.send', 'untrusted', True)])
        # stored locally, it is allowed and nobody is asked
        res, acts = self.plan(PAGE + 'act notes.write(text=page.text) with allow_untrusted=["text"].\n')
        self.assertEqual((res['ok'], acts), (True, [('notes.write', 'untrusted', False)]))
        # the host is told at run time as well
        host = Host({'web.fetch': {'text': 'hello'}, 'mail.send': {'ok': True}}, AGENTS)
        rep, _r = run(PAGE + 'act mail.send(to="me@example.org", body=page.text) with allow_untrusted=["body"].\n',
                      host, folder=self.dir, side_effects=True)
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual([(c['capability'], c['influence'], c['needs_owner']) for c in host.calls if c['kind'] == 'act'],
                         [('mail.send', 'untrusted', True)])
        self.assertNotIn('allow_untrusted', ' '.join(errors(PAGE + 'act mail.send(to="a@b.c", body=page.text).\n', AGENTS)),
                         'the refusal must not coach a planner into the escape hatch')

    def test_outside_text_never_instructs_an_agent_and_a_steered_start_needs_the_owner(self):
        for allow in ('', ' with allow_untrusted=["prompt"]'):
            msgs = errors(PAGE + f'act agents.start(prompt=page.text){allow}.\n', AGENTS)
            self.assertEqual(len(msgs), 1, msgs)
            self.assertIn('Outside text never instructs an agent or a program', msgs[0])
        res, acts = self.plan(PAGE + 'ask go: Bool "Worth a look? {page.text}" by "fake:a"\nif go then\n'
                              '  act agents.start(prompt="Summarise the saved report.").\nend.\n')
        self.assertEqual((res['ok'], acts), (True, [('agents.start', 'steered', True)]))
        res, acts = self.plan('act agents.start(prompt="Summarise the saved report.").\n')
        self.assertEqual(acts, [('agents.start', 'none', False)])
        self.assertTrue(FX.weighty(FX.normalize_catalogue(AGENTS)['agents.start']))
        self.assertFalse(FX.weighty(FX.normalize_catalogue(AGENTS)['notes.write']))

    def test_outside_text_is_not_washed_by_passing_it_to_a_read(self):
        src = PAGE + 'observe echo: Record {text: Text} = notes.search(query=page.text).\n'
        res = FX.check(src + 'show echo.text.\n', AGENTS)
        self.assertIn('untrusted', res['flow']['echo'])
        self.assertIn('built from untrusted text', errors(src + 'act notes.write(text=echo.text).\n', AGENTS)[0])
        self.assertIn('Outside text never instructs', errors(src + 'act agents.start(prompt=echo.text).\n', AGENTS)[0])
        # a read chosen by a closed answer is still only steered
        res = FX.check(PAGE + 'ask n: Int in 1..7 "How many days? {page.text}" by "fake:a"\n'
                       'observe busy = calendar.free_busy(days=n).\nshow busy.\n', AGENTS)
        self.assertEqual(sorted(res['flow']['busy']), ['personal', 'steered'])

    def test_a_keyed_action_is_its_key_whatever_its_arguments_say_later(self):
        ledger = os.path.join(self.dir, 'program.jsonl')
        host = Host({'notes.write': lambda e: {'saved': e['args']['text']}})
        src = 'given n: Int.\nact w = notes.write(text="count {n}") with key="daily-2026-10-03", scope=program.\nshow w.saved.\n'
        outs = []
        for i, n in enumerate((1, 2)):
            folder = os.path.join(self.dir, f'run{i}')
            os.makedirs(folder)
            r = Run(src, inputs={'n': n}, options={'effects': host, 'side_effects': True, 'effects_ledger': ledger}, folder=folder)
            rep = r.execute()
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            outs.append((rep['outputs'][0]['text'], [t.get('note') for t in r.trace if t['kind'] == 'act'][0]))
        self.assertEqual([c['args']['text'] for c in host.calls], ['count 1'])
        self.assertEqual(outs[0][0], outs[1][0])
        self.assertNotIn('other arguments', outs[0][1])
        self.assertIn('done earlier under this key with other arguments, and not done again', outs[1][1])
        self.assertEqual(FX.effect_id('notes.write', {'text': 'a'}, 'k', 'act'), FX.effect_id('notes.write', {'text': 'b'}, 'k', 'act'))
        self.assertNotEqual(FX.effect_id('notes.write', {'text': 'a'}, 'k', 'act'), FX.effect_id('notes.write', {'text': 'a'}, 'k2', 'act'))
        # a read is what it asks, key or no key; and an action without a key is its arguments
        self.assertNotEqual(FX.effect_id('web.fetch', {'url': 'a'}, 'k'), FX.effect_id('web.fetch', {'url': 'b'}, 'k'))
        self.assertNotEqual(FX.effect_id('notes.write', {'text': 'a'}, '', 'act'), FX.effect_id('notes.write', {'text': 'b'}, '', 'act'))
        self.assertNotEqual(FX.effect_id('notes.write', {'text': 'k'}, '', 'act'), FX.effect_id('notes.write', {}, 'k', 'act'))

    def test_an_interrupted_named_action_is_continued_with_the_arguments_it_began_with(self):
        ledger = os.path.join(self.dir, 'program.jsonl')
        src = 'given n: Int.\nact c = calendar.add(title="count {n}") with key="daily", scope=program.\n'

        class ById(Host):
            idempotent_by_id = True
        answers = [{'status': 'unknown', 'error': 'stopped'}, {'ok': True}, {'ok': True}]
        host = ById({'calendar.add': lambda e: answers.pop(0)})
        seen = []
        for i, n in enumerate((1, 2, 3)):
            folder = os.path.join(self.dir, f'r{i}')
            os.makedirs(folder)
            rep = Run(src, inputs={'n': n}, folder=folder,
                      options={'effects': host, 'side_effects': True, 'effects_ledger': ledger}).execute()
            seen.append(rep['status'])
        # the second run re-proposes the action the first one began: same id, the first run's arguments
        self.assertEqual(seen, ['failed', 'done', 'done'])
        self.assertEqual([(c['id'] == host.calls[0]['id'], c['args']['title'], c['attempt']) for c in host.calls],
                         [(True, 'count 1', 1), (True, 'count 1', 2)])
        done = FX.Ledger(ledger).get(host.calls[0]['id'])
        self.assertEqual((done['phase'], done['args']['title'], FX.intact(done)), ('done', 'count 1', True))
        # after a definite failure nothing is under way: a new attempt uses the arguments of its own run
        ledger2 = os.path.join(self.dir, 'program2.jsonl')
        answers2 = [{'status': 'failed', 'error': 'unavailable'}, {'ok': True}]
        host2 = ById({'calendar.add': lambda e: answers2.pop(0)})
        for i, n in enumerate((1, 2)):
            folder = os.path.join(self.dir, f's{i}')
            os.makedirs(folder)
            Run(src, inputs={'n': n}, folder=folder,
                options={'effects': host2, 'side_effects': True, 'effects_ledger': ledger2}).execute()
        self.assertEqual([(c['args']['title'], c['failures']) for c in host2.calls], [('count 1', 0), ('count 2', 1)])

    def test_recovery_never_lowers_what_the_first_attempt_needed(self):
        # Codex root, 2026-10-03: a keyed act left unknown is continued with its FIRST arguments. They were outside
        # text, so the continuing run's own clean labels must not be what the host is told.
        class ById(Host):
            idempotent_by_id = True
        cat = AGENTS
        first = PAGE + 'act sent = mail.send(to="me@example.org", body=page.text) with key="same", scope=program, allow_untrusted=["body"].\n'
        second = 'act sent = mail.send(to="me@example.org", body="program-authored safe text") with key="same", scope=program.\n'
        ledger = os.path.join(self.dir, 'shared.jsonl')
        answers = [{'status': 'unknown', 'error': 'lost outcome'}, {'ok': True}]
        host = ById({'web.fetch': {'text': 'outside-controlled text'}, 'mail.send': lambda e: answers.pop(0)}, cat)
        reps = []
        for name, src in (('a', first), ('b', second)):
            folder = os.path.join(self.dir, name)
            os.makedirs(folder)
            reps.append(Run(src, folder=folder, options={'effects': host, 'side_effects': True,
                                                         'effects_ledger': ledger}).execute())
        self.assertEqual([r['status'] for r in reps], ['failed', 'done'])
        acts = [c for c in host.calls if c['kind'] == 'act']
        self.assertEqual([(c['args']['body'], c['influence'], c['needs_owner'], c['attempt']) for c in acts],
                         [('outside-controlled text', 'untrusted', True, 1), ('outside-controlled text', 'untrusted', True, 2)])
        self.assertEqual(acts[0]['id'], acts[1]['id'])
        self.assertIn('web.fetch', acts[1]['influence_origin'])
        self.assertEqual((acts[1]['continues'], acts[1]['args_source_sha256']), (1, reps[0]['evidence']['source_sha256']))
        # every row of the action carries the labels, the unknown outcome and the final one included
        with open(ledger, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f if line.strip()]
        mine = [r for r in rows if r['id'] == acts[0]['id']]
        self.assertEqual([r['phase'] for r in mine], ['intent', 'unknown', 'intent', 'done'])
        self.assertEqual({(r['influence'], r['needs_owner']) for r in mine}, {('untrusted', True)})
        self.assertEqual({r['spec_sha256'] for r in mine}, {FX.contract_sha(FX.normalize_catalogue(cat)['mail.send'])})
        self.assertEqual({r.get('args_source_sha256') for r in mine[2:]}, {reps[0]['evidence']['source_sha256']})
        self.assertTrue(FX.intact(mine[-1]))

    def test_recovery_keeps_the_stricter_of_both_attempts_and_reads_a_bare_row_as_the_strictest(self):
        class ById(Host):
            idempotent_by_id = True
        steered = (PAGE + 'ask go: Bool "Switch it? {page.text}" by "fake:a"\nif go then\n'
                   '  act home.device(device="light", action="off") with key="light", scope=program.\nend.\n')
        clean = 'act home.device(device="light", action="off") with key="light", scope=program.\n'
        for order, want in (((steered, clean), [('steered', True), ('steered', True)]),
                            ((clean, steered), [('none', False), ('steered', True)])):
            ledger = os.path.join(self.dir, f'l{len(os.listdir(self.dir))}.jsonl')
            answers = [{'status': 'unknown', 'error': 'lost'}, {'ok': True}]
            host = ById({'web.fetch': {'text': 'x'}, 'home.device': lambda e, a=answers: a.pop(0)})
            for src in order:
                folder = tempfile.mkdtemp(dir=self.dir)
                Run(src, applicators=Apps({'a': True}), folder=folder,
                    options={'effects': host, 'side_effects': True, 'effects_ledger': ledger}).execute()
            self.assertEqual([(c['influence'], c['needs_owner']) for c in host.calls if c['kind'] == 'act'], want)
        # a row an older writer left without contract or labels: no host call at all, and the row still stands
        ledger = os.path.join(self.dir, 'legacy.jsonl')
        eid = FX.effect_id('home.device', {}, 'light', 'act')
        args = {'device': 'light', 'action': 'off'}
        bare = {'id': eid, 'phase': 'unknown', 'kind': 'act', 'capability': 'home.device', 'args': args,
                'args_sha256': FX._sha(args), 'key': 'light', 'attempt': 1, 'scope': 'program'}
        with open(ledger, 'w', encoding='utf-8') as f:
            f.write(json.dumps(bare) + '\n')
        host = ById({'home.device': {'ok': True}})
        folder = tempfile.mkdtemp(dir=self.dir)
        rep = Run(clean, folder=folder, options={'effects': host, 'side_effects': True, 'effects_ledger': ledger}).execute()
        self.assertEqual((rep['status'], rep['error']['kind'], host.calls), ('failed', 'uncertain', []))
        self.assertIn('recorded without its full contract and approval labels', rep['error']['message'])
        with open(ledger, encoding='utf-8') as f:
            self.assertEqual([json.loads(line)['phase'] for line in f if line.strip()], ['unknown'])
        # the run can show what blocks it, and the owner's word settles it
        self.assertEqual([r['phase'] for r in FX.Ledger(os.path.join(folder, FX.LEDGER)).all()], ['unknown'])
        FX.resolve(ledger, eid, False)
        rep = Run(clean, folder=tempfile.mkdtemp(dir=self.dir),
                  options={'effects': host, 'side_effects': True, 'effects_ledger': ledger}).execute()
        self.assertEqual((rep['status'], [(c['influence'], c['needs_owner'], c['failures']) for c in host.calls]),
                         ('done', [('none', False, 1)]))
        # continued() alone, given a bare row, still reads it as the strictest (defence in depth)
        strict = FX.continued(bare, {'influence': 'none', 'influence_origin': '', 'needs_owner': False})
        self.assertEqual((strict['influence'], strict['needs_owner'], strict['influence_origin']),
                         ('untrusted', True, 'an earlier attempt recorded without labels'))
        # continued() itself: requirements only rise
        base = {'influence': 'none', 'influence_origin': '', 'needs_owner': False, 'args': {'n': 2}, 'args_sha256': 'b'}
        was = {'influence': 'steered', 'influence_origin': 'web.fetch, line 1', 'needs_owner': True, 'args': {'n': 1},
               'args_sha256': 'a', 'attempt': 3, 'source_sha256': 's1'}
        out = FX.continued(was, base)
        self.assertEqual((out['args'], out['influence'], out['influence_origin'], out['needs_owner'], out['continues'],
                          out['args_source_sha256']), ({'n': 1}, 'steered', 'web.fetch, line 1', True, 3, 's1'))
        up = FX.continued({**was, 'influence': 'none', 'needs_owner': False}, {**base, 'influence': 'untrusted',
                                                                             'influence_origin': 'now', 'needs_owner': True})
        self.assertEqual((up['influence'], up['influence_origin'], up['needs_owner']), ('untrusted', 'now', True))

    def test_an_unknown_action_is_never_continued_under_a_changed_capability(self):
        # Codex root, 2026-10-03: two run folders share a keyed program ledger; the first attempt is unknown; the
        # capability changes; a second program proposes clean arguments that pass the NEW checks. The first
        # attempt's arguments were checked against the OLD capability, so they must not be sent under the new one.
        class Changing:
            idempotent_by_id = True

            def __init__(self, read, work):
                self.read, self.work, self.calls, self.acts = read, work, [], 0

            def catalogue(self):
                return {'demo.read': {'effect': 'read', 'policy': 'auto', **self.read},
                        'demo.work': {'effect': 'compute', 'policy': 'auto', **self.work}}

            def perform(self, e, stop):
                self.calls.append(e)
                if e['kind'] == 'observe':
                    return {'status': 'done', 'result': 'ORIGINAL PAYLOAD'}
                self.acts += 1
                return {'status': 'unknown', 'error': 'lost'} if self.acts == 1 else {'status': 'done', 'result': 'accepted'}
        text = {'type': 'object', 'properties': {'payload': {'type': 'string'}}}
        number = {'type': 'object', 'properties': {'payload': {'type': 'integer'}}}
        cases = (('instructs', {'untrusted': True}, {'instructs': False}, {'instructs': True}, ', allow_untrusted=["payload"]', '"safe literal"'),
                 ('egress', {'sensitivity': 'personal'}, {'egress': False}, {'egress': True}, '', '"safe literal"'),
                 ('schema', {}, {'params': text}, {'params': number}, '', '7'))
        for name, read, old, new, allow, proposed in cases:
            with self.subTest(name):
                d = tempfile.mkdtemp(dir=self.dir)
                host = Changing(read, old)
                ledger = os.path.join(d, 'shared.jsonl')
                first = f'observe page: Text = demo.read().\nact result = demo.work(payload=page) with key="one", scope=program{allow}.'
                second = f'act result = demo.work(payload={proposed}) with key="one", scope=program.'
                self.assertTrue(FX.check(first, FX.normalize_catalogue(host.catalogue()))['ok'])
                r1 = Run(first, folder=os.path.join(d, 'a'), options={'effects': host, 'side_effects': True,
                                                                     'effects_ledger': ledger}).execute()
                host.work = new
                self.assertTrue(FX.check(second, FX.normalize_catalogue(host.catalogue()))['ok'])     # each passes alone
                r2 = Run(second, folder=os.path.join(d, 'b'), options={'effects': host, 'side_effects': True,
                                                                      'effects_ledger': ledger}).execute()
                self.assertEqual((r1['error']['kind'], r2['status'], r2['error']['kind']), ('uncertain', 'failed', 'uncertain'))
                self.assertIn('no longer what it was when that attempt began', r2['error']['message'])
                self.assertEqual(len([c for c in host.calls if c['kind'] == 'act']), 1)     # no second host call
                with open(ledger, encoding='utf-8') as f:
                    rows = [json.loads(line) for line in f if line.strip()]
                self.assertEqual([r['phase'] for r in rows], ['intent', 'unknown'])     # still unknown, nothing new
                # the unknown receipt keeps the original request whole: arguments, contract, source, labels
                last = rows[-1]
                self.assertEqual(last['args'], {'payload': 'ORIGINAL PAYLOAD'})
                self.assertEqual((last['spec_sha256'], set(FX.CONTRACT_KEYS) <= set(last['spec'])),
                                 (FX.contract_sha(FX.normalize_spec('demo.work', {'effect': 'compute', 'policy': 'auto', **old})), True))
                self.assertEqual(last['source_sha256'], r1['evidence']['source_sha256'])
                self.assertIn('needs_owner', last)
                # the second run shows the standing row, and under the old capability again it would continue
                copy = FX.Ledger(os.path.join(d, 'b', FX.LEDGER)).get(last['id'])
                self.assertEqual((copy['phase'], copy['copied_from'], copy['spec_sha256']), ('unknown', 'program', last['spec_sha256']))
                host.work = old
                r3 = Run(first, folder=os.path.join(d, 'c'), options={'effects': host, 'side_effects': True,
                                                                     'effects_ledger': ledger}).execute()
                self.assertEqual(r3['status'], 'done', r3.get('error'))
                self.assertEqual([c['args'] for c in host.calls if c['kind'] == 'act'][-1], {'payload': 'ORIGINAL PAYLOAD'})

    def test_a_record_that_does_not_match_its_hashes_is_not_continued(self):
        class ById(Host):
            idempotent_by_id = True
        src = 'act c = calendar.add(title="Lab") with key="lab", scope=program.\n'
        ledger = os.path.join(self.dir, 'p.jsonl')
        host = ById({'calendar.add': {'status': 'unknown', 'error': 'lost'}})
        Run(src, folder=tempfile.mkdtemp(dir=self.dir), options={'effects': host, 'side_effects': True,
                                                                 'effects_ledger': ledger}).execute()
        with open(ledger, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f if line.strip()]
        for field, value in (('args', {'title': 'Something else'}), ('needs_owner', None)):
            tampered = [dict(r) for r in rows]
            tampered[-1][field] = value
            path = os.path.join(self.dir, f'tampered-{field}.jsonl')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(''.join(json.dumps(r) + '\n' for r in tampered))
            rep = Run(src, folder=tempfile.mkdtemp(dir=self.dir), options={'effects': host, 'side_effects': True,
                                                                           'effects_ledger': path}).execute()
            self.assertEqual((rep['error']['kind'], len(host.calls)), ('uncertain', 1), field)
        self.assertEqual(FX.recovery_block(rows[-1], {'spec_sha256': rows[-1]['spec_sha256']}), '')
        self.assertIn('no longer what it was', FX.recovery_block(rows[-1], {'spec_sha256': 'other'}))

    def test_a_run_that_performs_nothing_does_not_erase_an_earlier_uncertainty(self):
        class ById(Host):
            idempotent_by_id = True
        src = 'act c = calendar.add(title="Lab") with key="lab", scope=program.\n'
        ledger = os.path.join(self.dir, 'p.jsonl')
        host = ById({'calendar.add': {'status': 'unknown', 'error': 'lost'}})
        folder = tempfile.mkdtemp(dir=self.dir)
        Run(src, folder=folder, options={'effects': host, 'side_effects': True, 'effects_ledger': ledger}).execute()
        eid = host.calls[0]['id']
        # the next run reaches the same action but is over its limit: it performed nothing, and the action
        # that may have happened must still read as unknown, never as "nothing happened"
        host.results['notes.write'] = {'ok': True}
        folder = tempfile.mkdtemp(dir=self.dir)
        rep = Run('act n = notes.write(text="first").\n' + src, folder=folder,
                  options={'effects': host, 'side_effects': True, 'effects_ledger': ledger, 'max_effects': 1}).execute()
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'budget'))
        self.assertEqual([c['capability'] for c in host.calls], ['calendar.add', 'notes.write'])
        row = FX.Ledger(ledger).get(eid)
        self.assertEqual((row['phase'], row['error'], FX.Ledger(ledger).failures(eid)),
                         ('unknown', 'not performed: the run reached its limit', 0))
        # a first attempt that was never performed is a plain failure: nothing can have happened
        other = 'act n = notes.write(text="first").\nact c = calendar.add(title="Other").\n'
        folder = tempfile.mkdtemp(dir=self.dir)
        rep = Run(other, folder=folder, options={'effects': host, 'side_effects': True, 'max_effects': 1}).execute()
        self.assertEqual(sorted(r['phase'] for r in FX.Ledger(os.path.join(folder, FX.LEDGER)).all()), ['done', 'failed'])
        # and the owner's word keeps the whole record of the action it settles
        done = FX.resolve(ledger, eid, True, {'ok': True}, by='owner')
        self.assertEqual((done['phase'], done['influence'], done['needs_owner']), ('done', 'none', False))
        self.assertEqual((done['spec_sha256'], set(FX.CONTRACT_KEYS) <= set(done['spec']), done['source_sha256']),
                         (row['spec_sha256'], True, row['source_sha256']))

    def test_a_key_that_cannot_change_inside_a_loop_is_pointed_out(self):
        loop = 'for i in 1..3 do\n  act notes.write(text="row {i}") with key=%s.\nend.\n'
        warn = lambda key: [w['message'] for w in FX.check(loop % key, CATALOGUE)['warnings']]    # noqa: E731
        self.assertIn('happens once for the whole loop', warn('"rows"')[0])
        self.assertEqual(warn('"row-{i}"'), [])
        inner = 'for i in 1..3 do\n  let label = "r{i}".\n  if i > 1 then\n    act notes.write(text="x") with key=label.\n  end.\nend.\n'
        self.assertEqual([w['message'] for w in FX.check(inner, CATALOGUE)['warnings']], [])
        self.assertEqual([w['message'] for w in FX.check('act notes.write(text="x") with key="once".', CATALOGUE)['warnings']], [])
        host = Host({'notes.write': {'ok': True}})
        rep, _r = run(loop % '"rows"', host, folder=self.dir, side_effects=True)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 1))

    def test_the_limit_is_the_runs_across_resumes(self):
        host = Host({'notes.write': {'ok': True}})
        src = 'for i in 1..5 do\n  act notes.write(text="row {i}").\nend.\n'
        rep, _r = run(src, host, folder=self.dir, side_effects=True, max_effects=2)
        self.assertEqual((rep['status'], rep['error']['kind'], len(host.calls)), ('failed', 'budget', 2))
        for _ in range(3):                           # resuming does not hand out a fresh allowance
            rep, _r = run(src, host, folder=self.dir, side_effects=True, max_effects=2)
            self.assertEqual((rep['status'], len(host.calls)), ('failed', 2))
        rep, _r = run(src, host, folder=self.dir, side_effects=True, max_effects=10)
        self.assertEqual((rep['status'], len(host.calls)), ('done', 5))

    def test_a_host_learns_how_often_an_action_already_failed(self):
        answers = [{'status': 'failed', 'error': 'unavailable: busy'}, {'status': 'failed', 'error': 'unavailable: busy'},
                   {'ok': True}]
        host = Host({'calendar.add': lambda e: answers.pop(0)})
        src = 'act c = calendar.add(title="Lab").\n'
        seen = []
        for _ in range(3):
            rep, _r = run(src, host, folder=self.dir, side_effects=True)
            seen.append((rep['status'], host.calls[-1]['failures'], host.calls[-1]['attempt']))
        self.assertEqual(seen, [('failed', 0, 1), ('failed', 1, 2), ('done', 2, 3)])

    def test_an_unknown_outcome_in_the_programs_ledger_shows_in_the_run_and_a_stop_is_a_stop(self):
        ledger = os.path.join(self.dir, 'program.jsonl')
        src = 'act c = calendar.add(title="Lab") with key="lab", scope=program.\n'
        first, second = os.path.join(self.dir, 'a'), os.path.join(self.dir, 'b')
        os.makedirs(first)
        os.makedirs(second)
        host = Host({'calendar.add': {'status': 'unknown', 'error': 'connection lost'}})
        rep, _r = run(src, host, folder=first, side_effects=True, effects_ledger=ledger)
        self.assertEqual((rep['status'], rep['error']['kind']), ('failed', 'uncertain'))
        mine = FX.Ledger(os.path.join(first, FX.LEDGER)).all()
        self.assertEqual([(r['phase'], r['scope'], r['copied_from']) for r in mine], [('unknown', 'program', 'program')])
        # another run of the program meets the same unknown: it performs nothing and can show what blocks it
        rep, _r = run(src, host, folder=second, side_effects=True, effects_ledger=ledger)
        self.assertEqual((rep['error']['kind'], len(host.calls)), ('uncertain', 1))
        self.assertEqual([r['phase'] for r in FX.Ledger(os.path.join(second, FX.LEDGER)).all()], ['unknown'])
        # a stop while the host was busy ends the run as stopped
        stop = threading.Event()

        def interrupted(effect):
            stop.set()
            return {'status': 'unknown', 'error': 'stopped while the action was pending'}
        third = os.path.join(self.dir, 'c')
        os.makedirs(third)
        rep, _r = run('act c = calendar.add(title="Other").\n', Host({'calendar.add': interrupted}), folder=third,
                      side_effects=True, stop=stop)
        self.assertEqual(rep['status'], 'stopped')
        self.assertEqual([r['phase'] for r in FX.Ledger(os.path.join(third, FX.LEDGER)).all()], ['unknown'])


if __name__ == '__main__':
    unittest.main()

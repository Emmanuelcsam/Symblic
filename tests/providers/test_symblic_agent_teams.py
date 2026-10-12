"""Team profiles (symblic.providers.agent_teams): validation, applicator specs and native lowering.

Fake providers only. The English front end with teams is tested in
tests/integration/test_symblic_agent_teams_english.py."""
import copy
import unittest

from symblic.kernel import language as S
from symblic.providers import agent_teams as T
from symblic.kernel import evidence as E
from symblic.kernel import run as R

def team(n=5):
    engines = ['ollama', 'claude', 'codex', 'copilot', 'agy']
    return {'version': 1, 'members': [dict(id=f'seat{i}', engine=engines[i % 5],
        model='qwen3:4b-instruct' if i % 5 == 0 else '', node='node-a',
        role=f'Perspective {i}', characteristics='precise', instruction='Check the owner request.') for i in range(n)]}


class Fake:
    def __init__(self, answer=42, interrupt=False):
        self.requests, self.answer, self.interrupt = [], answer, interrupt

    def call(self, req):
        self.requests.append(copy.deepcopy({k: v for k, v in req.items() if k != 'stop'}))
        if self.interrupt:
            raise KeyboardInterrupt('uncertain fake provider')
        return {'ok': True, 'json': {'answer': self.answer}, 'node': req['app']['node'],
                'model': req['app']['model'] or req['app']['engine']}


class Schema(unittest.TestCase):
    def test_five_mixed_members_exact_profiles_and_aliases(self):
        spec = team()
        spec['members'][0].update(engine='local', settings={'temperature': .25, 'seed': 0}, weight=1.5)
        spec['members'][1]['effort'] = 'xhigh'
        parsed = T.normalize(spec)
        self.assertEqual(len(parsed['members']), 5)
        self.assertEqual(parsed['members'][0]['engine'], 'ollama')
        self.assertEqual(parsed['members'][0]['settings'], {'temperature': .25, 'seed': 0})
        self.assertEqual(T.member_app(parsed['members'][1])['effort'], 'xhigh')
        self.assertNotEqual(T.digest(parsed), T.digest(team()))

    def test_invalid_identity_or_ignored_options_refuse(self):
        variants = [{'id': 'seat1'}, {'settings': {'temperature': True}}, {'settings': {'seed': 1.2}},
                    {'settings': {'temperature': float('nan')}}, {'node': 'auto'}, {'effort': 'ultra'},
                    {'weight': True}, {'weight': float('inf')}, {'instruction': '\0'}, {'engine': 'triad'}]
        for patch in variants:
            with self.subTest(patch=patch):
                spec = team()
                spec['members'][0].update(patch)
                with self.assertRaises(T.TeamError):
                    T.normalize(spec)
        spec = team()
        spec['members'][1]['settings'] = {'seed': 7}
        with self.assertRaisesRegex(T.TeamError, 'ignore'):
            T.normalize(spec)
        for n in (0, 25):
            with self.assertRaises(T.TeamError):
                T.normalize(team(n))
        self.assertEqual(len(T.normalize(team(24))['members']), 24)

    def test_profile_identity_cannot_relabel_actual_app(self):
        member = T.normalize(team(1))['members'][0]
        raw = {'app': 'claude@node-a', 'member': member, 'weight': 1}
        with self.assertRaises(S.SymblicError):
            E.parse_applicator(raw)

    def test_catalog_preserves_unknown_engines_without_typed_dispatch_claim(self):
        result = T.capability_catalog({'specs': {'local': {'title': 'Local'}, 'future': {'title': 'Future'}},
                                       'nodes': [{'id': 'node-a', 'online': False}]})
        self.assertTrue(result['engines']['ollama']['checked'])
        self.assertFalse(result['engines']['future']['checked'])
        self.assertEqual(result['nodes'][0]['online'], False)


class NativeLowering(unittest.TestCase):
    SOURCE = ('ask legs: Int "Return forty two." with effort=low\nensure legs = 42 else retry.\nshow legs.\n'
              'ask arms: Int "Return forty two again." with effort=low\nshow arms.\n')

    def compiled(self):
        return {'source': self.SOURCE, 'options': {}, 'inputs': {}, 'source_map': [], 'statements': []}

    def test_each_ask_is_sampled_once_per_member_and_checked_natively(self):
        spec = team(3)
        lowered = T.lower_checked(self.compiled(), spec)
        lines = lowered['source'].splitlines()
        self.assertTrue(lines[0].startswith('group symblic_team_'))
        self.assertEqual(sum(1 for line in lines if line.startswith('use by=symblic_team_')), 2)
        self.assertEqual(lowered['team_sha256'], T.digest(T.normalize(spec)))
        self.assertEqual(lowered['team_policy']['independence'], 'not_established')
        fake = Fake()
        report = R.Run(lowered['source'], {}, fake, {'parallel': 1}).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(fake.requests), 6)
        self.assertEqual({r['app']['member']['id'] for r in fake.requests}, {'seat0', 'seat1', 'seat2'})
        for request in fake.requests:
            self.assertIn('"role":"Perspective', request['system'])

    def test_explicit_selection_is_never_replaced(self):
        compiled = self.compiled()
        compiled['source'] = compiled['source'].replace('with effort=low', 'by "fake:a" with effort=low', 1)
        with self.assertRaises(T.TeamError):
            T.lower_checked(compiled, team(2))

    def test_member_app_and_efforts_need_no_host(self):
        member = T.normalize(team(2))['members'][1]
        self.assertEqual(T.member_app({**member, 'effort': 'high'})['spec'], 'claude@node-a+high')
        self.assertEqual(T.efforts('codex'), ['minimal', 'low', 'medium', 'high', 'xhigh'])
        self.assertEqual(T.efforts('ollama'), [])
        member = T.normalize({'version': 1, 'members': [dict(id='m', engine='ollama', model='qwen3:4b',
                                                             node='127.0.0.1:11434')]})['members'][0]
        self.assertEqual(T.member_app(member)['spec'], 'ollama:qwen3:4b@127.0.0.1:11434')


if __name__ == '__main__':
    unittest.main()

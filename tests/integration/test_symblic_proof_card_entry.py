"""Target-first card via existing owner API and CLI, with isolated stores and fake models."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.providers import applicators as symblic_apply
from symblic.delegate import contracts as D
try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from tests.integration import test_symblic_proof_focus_entry as F
from tests.delegate import test_symblic_delegate_proof_card as Card


def request(capsule='full'):
    body = _focus_request(capsule)
    body['template'] = 'proof_step_card'
    return body


_focus_request = F.request


class CardCLI(unittest.TestCase):
    def test_focused_catalog_and_exact_compilation_without_provider(self):
        with patch.object(symblic_apply, 'Applicators', side_effect=AssertionError('Read-only CLI made provider')):
            code, text, _ = F.cli(['catalog', '--template', 'proof_step_card', '--agent-json'])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text), D.catalog('proof_step_card'))
            for capsule in ('full', 'compact'):
                body = request(capsule)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
                    code, text, _ = F.cli(['check', str(path), '--agent-json'])
                self.assertEqual(code, 0, text)
                compiled = json.loads(text)
                self.assertEqual(compiled, {'ok': True, **D.compile_task(body)})
                self.assertEqual(compiled['inputs']['task_card'][0][0], 'TARGET')
                self.assertEqual(compiled['handoff']['task_card'], compiled['task_card_manifest'])


class CardAPI(F.ProofFocusAPI):
    """Run the retained full-parent API journeys with the additive card contract."""
    def setUp(self):
        super().setUp()
        for target in (patch.object(F, 'request', request), patch.object(F, 'PARENT', Card.PARENT)):
            target.start(); self.addCleanup(target.stop)

    def test_saved_card_drift_refuses_result_and_resume_without_dispatch(self):
        body = request()
        started = self.routed('POST', 'delegate/run', {'task': body})
        self.assertEqual(started.status, 200, started.sent)
        ident = started.sent['id']
        result = self.routed('GET', 'delegate/result', query={'id': ident})
        self.assertTrue(result.sent['accepted'], result.sent)
        self.assertEqual(result.sent['result']['handoff']['task_card']['version'], 1)
        path = Path(E.run_dir(ident), 'meta.json')
        meta = json.loads(path.read_text())
        meta['inputs']['task_card'][0][1]['formula'] = '"a changed target"'
        path.write_text(json.dumps(meta))
        before = len(self.launches), len(self.apps.calls)
        for method, route, data, query in (('GET', 'delegate/result', None, {'id': ident}),
                                          ('POST', 'resume', {'id': ident}, None)):
            response = self.routed(method, route, data, query)
            self.assertEqual(response.status, 400, response.sent)
        self.assertEqual((len(self.launches), len(self.apps.calls)), before)


if __name__ == '__main__':
    unittest.main()

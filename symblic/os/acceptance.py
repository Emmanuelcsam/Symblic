"""An offline smoke suite of the OS terminal engine; never a release certification.

HostedAcceptanceSuite().run_all() runs 16 checks of symblic/os in a new private temporary root: the
engine answers in process, Symblic source is compiled (not run) and malformed source is refused, a whole
supported English sentence acts while one with extra words does nothing, the file effects create, find,
read, replace and fsync, receipts round-trip, a repeated request id returns its receipt instead of acting
twice (also from a new engine object), a request id is bound to its instruction, an interrupted receipt is
never replayed, files and receipts survive a new engine object, and traversal and symlink escapes are
refused. No model, provider, network endpoint, browser, service or executable is contacted.

The report states its scope ('isolated_fixture_smoke') and what it does NOT cover (NOT_COVERED). Model
registry and catalogue checks belonged to the original host and live with its integration
(tests/integration/). The legacy method names at the end exist so old callers get an explicit "Not
performed" instead of a pass.

Run: python3 -m symblic.os.acceptance [--json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time
from typing import Any
import uuid

from symblic.os.fs_boundary import FilesystemBoundaryError
from symblic.os.receipts import get_receipt, store_receipt, validate_receipt_fields
from symblic.os.terminal_server import SymblicOSTerminalEngine

NOT_COVERED = [
    'HTTP serving, authentication and browser interaction',
    'Service restart or live task recovery',
    'Installed model availability, model registries, model inference or provider sign-in',
    'Real process execution, node admission or remote placement',
    'Framework integration, virtual boot or physical installation',
]


class HostedAcceptanceSuite:
    """Offline fixture smoke with a fresh root and explicit evidence scope.

    ``dev_root`` is retained as a compatibility parameter, but is a *parent*
    for a new private temporary directory, never the existing OS data root.
    Use the context manager or close() to remove scratch files promptly.
    """

    def __init__(self, dev_root: str | None = None):
        self._temporary = tempfile.TemporaryDirectory(prefix='symblicos-acceptance-', dir=dev_root)
        self.dev_root = self._temporary.name
        self.engine = SymblicOSTerminalEngine(self.dev_root)
        self.results: dict[str, dict] = {}
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._temporary.cleanup()
        self._closed = True

    def _seed(self, name, content='initial content'):
        path = Path(self.engine.paths['user_files']) / name
        path.write_text(content, encoding='utf-8')
        return path

    def run_all(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError('This fixture suite is closed; create a new suite.')
        cases = [
            ('in_process_protocol_roundtrip', self.test_terminal_protocol_connection),
            ('native_source_compilation_only', self.test_symblic_compilation),
            ('invalid_source_rejection', self.test_invalid_symblic_rejection),
            ('whole_sentence_english_intake', self.test_imperative_english_intake),
            ('filesystem_creation', self.test_filesystem_creation),
            ('filesystem_discovery', self.test_filesystem_discovery),
            ('filesystem_reading', self.test_filesystem_reading),
            ('filesystem_replacement', self.test_filesystem_replacement),
            ('filesystem_fsync_call', self.test_filesystem_persistence),
            ('receipt_schema_roundtrip', self.test_receipt_generation),
            ('durable_duplicate_after_engine_recreation', self.test_duplicate_submission_handling),
            ('request_identity_payload_binding', self.test_request_binding),
            ('interrupted_receipt_refuses_replay', self.test_interrupted_receipt),
            ('engine_recreation_file_persistence', self.test_engine_recreation),
            ('receipt_lookup_after_engine_recreation', self.test_receipt_recovery),
            ('filesystem_traversal_and_symlink_refusal', self.test_unauthorized_filesystem_escape),
        ]
        self.results = {}
        for name, fn in cases:
            started = time.monotonic()
            try:
                passed, detail = fn()
                passed = passed is True
            except Exception as exc:
                passed, detail = False, f'{type(exc).__name__}: {exc}'
            self.results[name] = {'test': name, 'passed': passed, 'detail': detail,
                                  'duration_s': time.monotonic() - started,
                                  'scope': 'isolated_fixture_smoke'}
        rows = list(self.results.values())
        return {'schema': 'symblicos.acceptance/v2', 'scope': 'isolated_fixture_smoke',
                'live_validation': False, 'all_passed': bool(rows) and all(row['passed'] for row in rows),
                'total_tests': len(rows), 'passed_tests': sum(row['passed'] for row in rows),
                'failed_tests': sum(not row['passed'] for row in rows), 'tests': rows,
                'scratch_root': self.dev_root, 'scratch_lifetime': 'until close or object cleanup',
                'not_covered': list(NOT_COVERED)}

    def test_terminal_protocol_connection(self):
        result = self.engine.execute_instruction('inspect system')
        return result.get('type') == 'terminal_success' and bool(result.get('execution_id')), 'In-process engine returned a terminal event and durable receipt; no HTTP/WebSocket connection.'

    def test_symblic_compilation(self):
        result = self.engine.execute_instruction('program Fixture.\nlet x = 1 + 2.\nshow x.')
        receipt = result['receipt']
        ok = result.get('type') == 'terminal_success' and receipt['action_category'] == 'symblic_compiler' and 'compiled successfully' in receipt['stdout']
        return ok, 'Native source passed the compiler bridge. The OS submit route compiles this source; it does not execute it.'

    def test_invalid_symblic_rejection(self):
        result = self.engine.execute_instruction('program Bad.\nlet bad = "unterminated string')
        return result.get('type') == 'terminal_failure' and result.get('error_type') == 'validation_failure', 'Malformed native source refused by compiler diagnostics.'

    def test_imperative_english_intake(self):
        name = 'intake-' + uuid.uuid4().hex + '.txt'
        good = self.engine.execute_instruction(f'Create a text file named "{name}".')
        before = (Path(self.engine.paths['user_files']) / name).read_bytes()
        bad = self.engine.execute_instruction(f'Write "changed" to "{name}" and erase unrelated files.')
        ok = good.get('type') == 'terminal_success' and bad.get('type') == 'terminal_failure' and (Path(self.engine.paths['user_files']) / name).read_bytes() == before
        return ok, 'Complete supported command creates a scratch file; a command with an unknown suffix leaves it unchanged.'

    def test_filesystem_creation(self):
        name = 'created-' + uuid.uuid4().hex + '.txt'
        result = self.engine.file_effects.create_file(name, 'initial content')
        return Path(result['path']).read_text() == 'initial content' and result['size'] == 15, 'Scratch file created and exact bytes read back.'

    def test_filesystem_discovery(self):
        self._seed('discover.txt')
        result = self.engine.file_effects.locate_file('discover.txt')
        return bool(result and result['size'] == 15 and result['sha256']), 'Scratch file located with size and digest.'

    def test_filesystem_reading(self):
        self._seed('read.txt', 'exact Ω text')
        return self.engine.file_effects.read_file('read.txt')['content'] == 'exact Ω text', 'UTF-8 scratch content returned exactly.'

    def test_filesystem_replacement(self):
        path = self._seed('replace.txt')
        result = self.engine.file_effects.replace_file('replace.txt', 'updated content', verify=True)
        return result['before_sha256'] != result['after_sha256'] and path.read_text() == 'updated content', 'Replacement bytes and before/after digests agree in the scratch store.'

    def test_filesystem_persistence(self):
        self._seed('flush.txt')
        return self.engine.file_effects.flush_file('flush.txt').get('flushed') is True, 'Scratch file fsync adapter returned success; no power-loss durability experiment.'

    def test_receipt_generation(self):
        self._seed('receipt.txt')
        result = self.engine.execute_instruction('Read "receipt.txt".')
        receipt = get_receipt(result['execution_id'], self.engine.paths['receipts'])
        validate_receipt_fields(receipt)
        return receipt == result['receipt'] and receipt['result_status'] == 'success', 'Persisted receipt matches the emitted event and retains required fields.'

    def test_duplicate_submission_handling(self):
        path = self._seed('duplicate.txt', 'A')
        request_id = 'fixture-' + uuid.uuid4().hex
        first = self.engine.execute_instruction('Append "B" to "duplicate.txt".', request_id)
        other = SymblicOSTerminalEngine(self.dev_root)
        second = other.execute_instruction('Append "B" to "duplicate.txt".', request_id)
        return first['execution_id'] == second['execution_id'] and path.read_text() == 'AB', 'Same request after a new engine object returns its receipt and does not append twice.'

    def test_request_binding(self):
        self._seed('bound.txt')
        request_id = 'fixture-' + uuid.uuid4().hex
        self.engine.execute_instruction('Read "bound.txt".', request_id)
        try:
            self.engine.execute_instruction('Write "changed" to "bound.txt".', request_id)
        except ValueError:
            return True, 'A saved request identity refuses a different instruction.'
        return False, 'A request identity accepted different instructions.'

    def test_interrupted_receipt(self):
        path = self._seed('interrupted.txt', 'A')
        request_id = 'fixture-' + uuid.uuid4().hex
        result = self.engine.execute_instruction('Append "B" to "interrupted.txt".', request_id)
        receipt = result['receipt']
        receipt.update(result_status='in_progress', completion_timestamp=0, stderr='')
        store_receipt(receipt, self.engine.paths['receipts'])
        replay = SymblicOSTerminalEngine(self.dev_root).execute_instruction('Append "B" to "interrupted.txt".', request_id)
        return replay.get('type') == 'terminal_failure' and path.read_text() == 'AB', 'Fault-injected in-progress receipt refuses another performance of the scratch operation.'

    def test_engine_recreation(self):
        path = self._seed('recreate.txt', 'retained content')
        other = SymblicOSTerminalEngine(self.dev_root)
        result = other.file_effects.read_file(path.name)
        return result['content'] == 'retained content', 'New engine object reads retained scratch bytes. No process or service was restarted.'

    def test_receipt_recovery(self):
        result = self.engine.execute_instruction('List files.')
        other = SymblicOSTerminalEngine(self.dev_root)
        receipt = get_receipt(result['execution_id'], other.paths['receipts'])
        return receipt == result['receipt'] and any(row['execution_id'] == result['execution_id'] for row in other.get_history()), 'Receipt API helper and history recover the saved scratch record. No browser reconnection was performed.'

    def test_unauthorized_filesystem_escape(self):
        outside = Path(self.dev_root) / 'outside.txt'
        outside.write_text('untouched')
        link = Path(self.engine.paths['user_files']) / ('escape-' + uuid.uuid4().hex)
        link.symlink_to(outside)
        for path in ['../outside.txt', str(outside), str(link)]:
            try:
                self.engine.boundary.resolve_path(path)
            except FilesystemBoundaryError:
                continue
            return False, 'An out-of-root fixture path was admitted.'
        return outside.read_text() == 'untouched', 'Lexical traversal and a symlink to scratch data outside user_files were refused.'

    # Legacy names remain callable, but cannot manufacture a pass for an unrun boundary.
    def test_terminal_static_assets(self):
        return False, 'Not performed: the browser terminal page belonged to the original host and is not part of this repository.'

    def test_model_inventory_fixture(self):
        return False, 'Not performed: model registries live with the host integration (integration/host/symblicos_model_engine.py).'

    def test_terminal_http_loading(self):
        return False, 'Not performed: this offline suite does not test HTTP. Use test_terminal_static_assets for the disk check and the browser/HTTP suites for real transport.'

    def test_local_model_discovery(self):
        return False, 'Not performed: no live model discovery. test_model_inventory_fixture checks only synthetic mapping.'

    def test_one_local_model_invocation(self):
        return False, 'Not performed: no live inference. test_model_response_fixture checks only synthetic response parsing.'

    def test_service_restart(self):
        return False, 'Not performed: no service restart. test_engine_recreation checks only retained scratch state.'

    def test_browser_reconnection(self):
        return False, 'Not performed: no browser. test_receipt_recovery checks only retained receipt helpers.'

    def test_unauthorized_executable_launch(self):
        return False, 'Not performed: this suite never launches executables; process-boundary verification has separate isolated tests.'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-parent', help='Existing directory in which to create a new temporary fixture root')
    parser.add_argument('--json', action='store_true', help='Print the scoped report as JSON')
    args = parser.parse_args(argv)
    with HostedAcceptanceSuite(args.scratch_parent) as suite:
        report = suite.run_all()
    report['scratch_lifetime'] = 'removed after run'
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Isolated fixture smoke: {report['passed_tests']}/{report['total_tests']} passed.")
        print('No HTTP/browser, model inference, fleet launch, service restart or boot verification was performed.')
        for row in report['tests']:
            if not row['passed']:
                print(f"FAIL {row['test']}: {row['detail']}")
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

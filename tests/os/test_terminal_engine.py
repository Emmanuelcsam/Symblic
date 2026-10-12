"""The OS terminal engine (symblic/os/terminal_server.py), its wire protocol helper (protocol.py) and the
development listener's request guard: temporary roots only, no network and no model.

Covers receipts and restart deduplication, refusal to overwrite on create, whole-sentence intake (a
known command with extra words does nothing), the delete intent, request identity, failures that stay
failures, receipt ids that cannot escape the root, symlink escapes, no replay of an interrupted
operation, compile-only Symblic source, unicode and directory destinations, concurrent appends, the
optional model inventory, and the loopback/Host/Origin/tunnel checks of the listener.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/os -t .
"""
from pathlib import Path
import tempfile
import threading
import unittest


class OSReceipts(unittest.TestCase):
    def setUp(self):
        from symblic.os.terminal_server import SymblicOSTerminalEngine
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine_type = SymblicOSTerminalEngine
        self.engine = self.engine_type(self.tmp.name)

    def test_file_roundtrip_and_restart_deduplication(self):
        create = self.engine.execute_instruction('Create file "note.txt"', 'create')
        self.assertEqual('terminal_success', create['type'])
        self.engine.execute_instruction('Write "hello" to "note.txt"', 'write')
        append = self.engine.execute_instruction('Append " world" to "note.txt"', 'append')
        again = self.engine_type(self.tmp.name).execute_instruction('Append " world" to "note.txt"', 'append')
        self.assertEqual(append['execution_id'], again['execution_id'])
        self.assertEqual('hello world', (Path(self.tmp.name) / 'user_files/note.txt').read_text())
        self.assertEqual(3, len(self.engine.get_history()))

    def test_file_creation_never_overwrites_existing_content(self):
        self.engine.execute_instruction('Create file "note.txt"', 'create')
        self.engine.execute_instruction('Write "retain" to "note.txt"', 'write')
        result = self.engine.execute_instruction('Create file "note.txt"', 'create-again')
        self.assertEqual('terminal_failure', result['type'])
        self.assertEqual('retain', (Path(self.tmp.name) / 'user_files/note.txt').read_text())

    def test_partial_command_is_not_silently_executed(self):
        result = self.engine.execute_instruction('Create file "note.txt" and delete everything', 'ambiguous')
        self.assertEqual('terminal_failure', result['type'])
        self.assertFalse((Path(self.tmp.name) / 'user_files/note.txt').exists())

    def test_delete_intent_removes_only_the_named_file(self):
        from symblic.os.receipts import get_receipt
        self.engine.execute_instruction('Create file "gone.txt"', 'del-create')
        self.engine.execute_instruction('Write "data" to "gone.txt"', 'del-write')
        self.engine.execute_instruction('Create file "stays.txt"', 'del-other')
        result = self.engine.execute_instruction('Delete file "gone.txt"', 'del-remove')
        self.assertEqual('terminal_success', result['type'])
        self.assertFalse((Path(self.tmp.name) / 'user_files/gone.txt').exists())
        self.assertTrue((Path(self.tmp.name) / 'user_files/stays.txt').exists())
        receipt = get_receipt(result['execution_id'], self.engine.paths['receipts'])
        self.assertEqual('imperative_remove_file', receipt['action_category'])
        self.assertEqual([{'path': str(Path(self.tmp.name) / 'user_files/gone.txt'), 'removed': True}],
                         receipt['files_removed'])
        self.assertIn('sha256', receipt['stdout'])

    def test_delete_intent_refuses_missing_file_and_directories(self):
        missing = self.engine.execute_instruction('Delete file "absent.txt"', 'del-missing')
        self.assertEqual('terminal_failure', missing['type'])
        self.engine.execute_instruction('Make directory "sub"', 'del-dir')
        directory = self.engine.execute_instruction('Remove file "sub"', 'del-directory')
        self.assertEqual('terminal_failure', directory['type'])
        self.assertTrue((Path(self.tmp.name) / 'user_files/sub').exists())

    def test_same_id_different_instruction_refused(self):
        self.engine.execute_instruction('Inspect system', 'id')
        with self.assertRaisesRegex(ValueError, 'different'):
            self.engine.execute_instruction('Create file "other.txt"', 'id')

    def test_failure_remains_failure_on_restart(self):
        self.engine.execute_instruction('Unsupported command', 'id')
        result = self.engine_type(self.tmp.name).execute_instruction('Unsupported command', 'id')
        self.assertEqual('terminal_failure', result['type'])

    def test_receipt_id_cannot_escape_root(self):
        from symblic.os.receipts import get_receipt
        with self.assertRaises(ValueError):
            get_receipt('../../etc/passwd', self.engine.paths['receipts'])

    def test_dangling_symlink_escape_refused(self):
        root = Path(self.tmp.name)
        (root / 'user_files/link').symlink_to(root / 'outside')
        result = self.engine.execute_instruction('Write "bad" to "link/file.txt"', 'symlink')
        self.assertEqual('terminal_failure', result['type'])
        self.assertFalse((root / 'outside').exists())

    def test_in_progress_operation_is_not_replayed(self):
        from symblic.os.receipts import get_receipt, store_receipt
        result = self.engine.execute_instruction('Create file "one.txt"', 'id')
        receipt = get_receipt(result['execution_id'], self.engine.paths['receipts'])
        receipt['result_status'] = 'in_progress'
        store_receipt(receipt, self.engine.paths['receipts'])
        (Path(self.tmp.name) / 'user_files/one.txt').unlink()
        again = self.engine_type(self.tmp.name).execute_instruction('Create file "one.txt"', 'id')
        self.assertEqual('terminal_failure', again['type'])
        self.assertFalse((Path(self.tmp.name) / 'user_files/one.txt').exists())

    def test_native_source_is_labelled_compilation_only(self):
        result = self.engine.execute_instruction('program Test.\nlet x = 1 + 2.\nshow x.', 'native')
        self.assertEqual('terminal_success', result['type'])
        self.assertIn('compiled', result['summary'])

    def test_file_operations_retain_unicode_and_directory_destination(self):
        self.engine.execute_instruction('Create directory "games"', 'dir')
        self.engine.execute_instruction('Write "snake’s café" to "game.txt"', 'text')
        copied = self.engine.execute_instruction('Copy "game.txt" to "games"', 'copy')
        self.assertEqual('terminal_success', copied['type'])
        moved = self.engine.execute_instruction('Move "games/game.txt" to "games/renamed.txt"', 'move')
        self.assertEqual('terminal_success', moved['type'])
        self.assertFalse((Path(self.tmp.name) / 'user_files/games/game.txt').exists())
        self.assertEqual('snake’s café', (Path(self.tmp.name) / 'user_files/games/renamed.txt').read_text())
        self.assertEqual('terminal_success', self.engine.execute_instruction('Save file "games/renamed.txt"', 'save')['type'])

    def test_concurrent_append_requests_do_not_lose_updates(self):
        self.engine.execute_instruction('Write "" to "count.txt"', 'create')
        engines = [self.engine_type(self.tmp.name), self.engine_type(self.tmp.name)]
        errors = []
        def append(index):
            result = engines[index].execute_instruction('Append "x" to "count.txt"', f'append-{index}')
            if result['type'] != 'terminal_success':
                errors.append(result)
        threads = [threading.Thread(target=append, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        self.assertEqual('xx', (Path(self.tmp.name) / 'user_files/count.txt').read_text())


class Protocol(unittest.TestCase):
    def test_protocol_helper_binds_exact_instruction_and_mode(self):
        from symblic.os.protocol import ExecutionSessionManager, TerminalProtocolError
        manager = ExecutionSessionManager()
        request = {'client_request_id': 'one', 'instruction': 'first', 'mode': 'os'}
        first, duplicate = manager.register_submission(request)
        self.assertFalse(duplicate)
        self.assertEqual((first, True), manager.register_submission(request))
        for changed in ({'instruction': 'second'}, {'mode': 'agent'}):
            with self.assertRaises(TerminalProtocolError):
                manager.register_submission({**request, **changed})

    def test_protocol_sequences_are_unique_under_concurrent_events(self):
        from symblic.os.protocol import ExecutionSessionManager
        manager = ExecutionSessionManager()
        result = []
        threads = [threading.Thread(target=lambda: result.append(manager.next_sequence('one'))) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(list(range(1, 13)), sorted(result))


class StandaloneBoundary(unittest.TestCase):
    def test_loopback_host_origin_and_cf_ray_checked(self):
        from email.message import Message
        from symblic.os.terminal_server import SymblicOSTerminalHandler
        for host, origin, cf_ray, address, accepted in (
            ('localhost:8990', '', '', '127.0.0.1', True),
            ('attacker.example', '', '', '127.0.0.1', False),
            ('localhost:8990', 'https://attacker.example', '', '127.0.0.1', False),
            ('localhost:8990', '', 'through-tunnel', '127.0.0.1', False),
            ('localhost:8990', '', '', '192.0.2.1', False),
        ):
            handler = object.__new__(SymblicOSTerminalHandler)
            handler.headers = Message()
            handler.headers['Host'] = host
            if origin:
                handler.headers['Origin'] = origin
            if cf_ray:
                handler.headers['CF-RAY'] = cf_ray
            handler.client_address = (address, 1234)
            handler.send_error = lambda *_: None
            self.assertEqual(accepted, handler._local_request())


class ModelInventory(unittest.TestCase):
    def test_inspect_models_needs_an_inventory_and_reports_it_verbatim(self):
        from symblic.os.terminal_server import SymblicOSTerminalEngine
        with tempfile.TemporaryDirectory() as root:
            refused = SymblicOSTerminalEngine(root).execute_instruction('Inspect models', 'models-1')
            self.assertEqual('terminal_failure', refused['type'])
            self.assertIn('No model inventory is configured', refused['receipt']['stderr'])
            listed = [{'id': 'node-a', 'models': [{'name': 'qwen3:4b-instruct'}]}]
            engine = SymblicOSTerminalEngine(root, model_inventory=lambda: listed)
            result = engine.execute_instruction('Inspect models', 'models-2')
            self.assertEqual('terminal_success', result['type'])
            self.assertEqual({'nodes': listed, 'scope': 'Inventory; no health inference performed'},
                             result['receipt']['final_result'])


if __name__ == '__main__':
    unittest.main()

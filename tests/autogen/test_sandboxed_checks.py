"""Model-written test scripts run sandboxed (symblic/autogen/coordinator.py: sandbox_prefix and the
designed check), through the Landlock launcher symblic/sandbox/landlock.py.

The first test checks the command the coordinator builds. The other two run the real launcher on
temporary folders (no model, no store): a designed check that passes and one that fails, run on a
throwaway copy so the checked folder is never written; and a probe showing the script can write its
folder but cannot read $HOME or connect to a loopback port. Both skip where Landlock is unavailable
(an older kernel or a non-Linux system); where a systemd user bus answers, the check also runs in a
transient scope.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import os
import unittest


class Sandbox(unittest.TestCase):
    def test_model_written_scripts_run_through_the_landlock_launcher(self):
        from symblic.autogen import coordinator as AG
        kind, prefix, shell = AG.sandbox_prefix('/tmp/x', '/tmp/home', ('/tmp/s.sh',))
        self.assertEqual('landlock', kind)
        self.assertTrue(os.path.isabs(shell) and shell.endswith('bash'))
        self.assertEqual(['env', '-i'], prefix[:2])
        self.assertTrue(prefix[2].startswith('PATH=/usr/local/bin:/usr/bin:/bin'))
        self.assertIn('HOME=/tmp/home', prefix)
        self.assertNotIn(os.path.expanduser('~'), prefix[3])
        self.assertTrue(prefix[7].endswith(os.path.join('symblic', 'sandbox', 'landlock.py')) and os.path.isfile(prefix[7]))
        for flag in ('--require', '--no-unix'):
            self.assertIn(flag, prefix)
        self.assertEqual(['--net-connect', '1'], prefix[prefix.index('--net-connect'):prefix.index('--net-connect') + 2])
        self.assertEqual(['--cwd', '/tmp/x', '--rw', '/tmp/x', '--rw', '/tmp/home'], prefix[8:14])
        self.assertEqual(['--ro', '/tmp/s.sh', '--'], prefix[-3:])

    def test_a_designed_check_really_runs_in_a_copy_under_the_scope_and_landlock(self):
        """End to end with the real runner, the real Landlock launcher and (where the user bus
        answers) a real transient scope: no model, temporary folders only."""
        import shutil
        import tempfile
        from symblic.autogen import coordinator as AG
        work = tempfile.mkdtemp(prefix='autogen-designed-e2e-')
        try:
            os.makedirs(os.path.join(work, '.git'))
            with open(os.path.join(work, 'app.py'), 'w', encoding='utf-8') as handle:
                handle.write('def main():\n    return 1\n')
            root = tempfile.mkdtemp(prefix='autogen-root-')
            self.addCleanup(shutil.rmtree, root, True)
            auto = AG.AutogenManager(root, background=False, check_host=lambda: None)
            script = ('#!/usr/bin/env bash\nset -e\ntest -f app.py\ntest ! -e .git\n'
                      'python3 -c "import app; assert app.main() == 1"\necho touched > scratch.txt\necho main: pass\n')
            check = auto._designed_check(script, work, None)
            if 'refused' in (check.get('output') or '') and check.get('sandbox') != 'none':
                self.skipTest('sandbox unavailable here: ' + check['output'][-200:])
            self.assertTrue(check['passed'], check)
            self.assertIn(check['sandbox'], ('landlock', 'landlock+scope'))
            if shutil.which('systemd-run') and os.environ.get('XDG_RUNTIME_DIR') and AG._SCOPE.get('ok'):
                self.assertEqual('landlock+scope', check['sandbox'])
            self.assertFalse(os.path.exists(os.path.join(work, 'scratch.txt')))   # the copy took the write, not the checkout
            failing = '#!/usr/bin/env bash\nset -e\npython3 -c "import app; assert app.main() == 2"\n'
            check = auto._designed_check(failing, work, None)
            self.assertFalse(check['passed'])
            self.assertIn('AssertionError', check['output'])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_launcher_hides_home_and_blocks_the_network(self):
        """A real Landlock run (no model, no store): the script can write its folder, cannot read
        $HOME, cannot connect to loopback. Skipped where Landlock is unavailable."""
        import subprocess
        import tempfile
        from symblic.autogen import coordinator as AG
        work = tempfile.mkdtemp(prefix='autogen-sandbox-work-')
        home = tempfile.mkdtemp(prefix='autogen-sandbox-home-')
        script = os.path.join(home, 'probe.sh')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write('#!/usr/bin/env bash\necho ok > out.txt\n'
                         'if ls ' + os.path.expanduser('~') + ' >/dev/null 2>&1; then echo HOME-VISIBLE; else echo home-hidden; fi\n'
                         'python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect((\'127.0.0.1\', 8080))" '
                         '>/dev/null 2>&1 && echo NET-OPEN || echo net-blocked\n'
                         'test -f out.txt && echo wrote\n')
        kind, prefix, shell = AG.sandbox_prefix(work, home, (script,))
        try:
            proc = subprocess.run(prefix + [shell, script], cwd=work, capture_output=True, text=True, timeout=60)
        finally:
            for folder in (work, home):
                import shutil
                shutil.rmtree(folder, ignore_errors=True)
        if proc.returncode == AG.SANDBOX_REFUSED:
            self.skipTest('Landlock unavailable here: ' + proc.stderr.strip()[-200:])
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual(['home-hidden', 'net-blocked', 'wrote'], proc.stdout.split())


if __name__ == '__main__':
    unittest.main()

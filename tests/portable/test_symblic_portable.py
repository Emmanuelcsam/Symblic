"""Portable bundles: build, unpack and run real bundles in temporary folders; no providers, stores or uploads.

SYMBLIC_PORTABLE_TEST_ROOT may point at another checkout to export from (default: this repository).
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

from symblic.portable import export as P
from symblic.portable import runner as R

ROOT = Path(os.environ.get('SYMBLIC_PORTABLE_TEST_ROOT', Path(__file__).resolve().parents[2]))


def mutate(source, output, edit):
    with zipfile.ZipFile(source) as bundle:
        members = [(info,bundle.read(info)) for info in bundle.infolist()]
    members = edit(members)
    with zipfile.ZipFile(output,'w') as bundle:
        for info,data in members: bundle.writestr(info,data)


class RegistryDeclarations(unittest.TestCase):
    def registry(self, expression, extra=''):
        with tempfile.TemporaryDirectory(prefix='portable-registry-') as folder:
            root = Path(folder)
            source = "\n".join(name + " = frozenset({'" + name.lower() + "'})" for name in sorted(P.REGISTRY))
            pins = root / P.PINS_MODULE
            pins.parent.mkdir(parents=True)
            pins.write_text(source + '\n' + extra + '\nREQUIRED_FILES = ' + expression)
            return P.declared_registry(root)

    def test_literal_set_extension_preserves_all_finite_registry_members(self):
        registry = self.registry("REQUIRED_FILES | PYTHON_FILES | ASSET_FILES | {'symblic/providers/agent_teams.py'}")
        self.assertEqual(registry['required_python'],
                         ['asset_files', 'python_files', 'required_files', 'symblic/providers/agent_teams.py'])
        self.assertEqual(registry['packages'], ['symblic/__init__.py', 'symblic/providers/__init__.py'])

    def test_wrapped_unions_and_prior_names_are_finite_without_source_execution(self):
        registry = self.registry("frozenset(REQUIRED_FILES | {'extra.py'})",
                                 "raise AssertionError('registry parsing must not execute source')")
        self.assertEqual(registry['required_python'], ['extra.py', 'required_files'])

    def test_dynamic_or_non_string_registry_expressions_are_refused(self):
        expressions = ["{'ok.py', 1}", "{*REQUIRED_FILES}", "frozenset(['ok.py'])", "set()",
                       "frozenset(x for x in REQUIRED_FILES)", "{'ok.py' for _ in REQUIRED_FILES}",
                       "REQUIRED_FILES.union({'ok.py'})", "REQUIRED_FILES + {'ok.py'}", "UNKNOWN_FILES",
                       "__import__('os').system('false')", "frozenset({'ok.py'}, bad=True)"]
        for expression in expressions:
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, 'unsupported_registry_declaration'):
                self.registry(expression)


class EntropyBoundary(unittest.TestCase):
    def test_exact_read_only_linux_entropy_device(self):
        device = os.stat('/dev/urandom', follow_symlinks=False)
        self.assertTrue(stat.S_ISCHR(device.st_mode))
        self.assertTrue(R._entropy_read('/dev/urandom', 'r', os.O_RDONLY | os.O_CLOEXEC))
        self.assertTrue(R._entropy_read(b'/dev/urandom', None, os.O_RDONLY))
        for path in ('/dev/random', '/dev/../dev/urandom', '/proc/self/fd/3', '/etc/passwd', 3):
            with self.subTest(path=path):
                self.assertFalse(R._entropy_read(path, 'r', os.O_RDONLY))
        for flags in (os.O_WRONLY, os.O_RDWR, os.O_CREAT, os.O_TRUNC, os.O_APPEND):
            with self.subTest(flags=flags):
                self.assertFalse(R._entropy_read('/dev/urandom', 'r', flags))
        for mode in ('w', 'a', 'r+', 'x'):
            self.assertFalse(R._entropy_read('/dev/urandom', mode, os.O_RDONLY))
        for fake in (mock.Mock(st_mode=stat.S_IFREG, st_rdev=device.st_rdev),
                     mock.Mock(st_mode=stat.S_IFLNK, st_rdev=device.st_rdev),
                     mock.Mock(st_mode=stat.S_IFCHR, st_rdev=os.makedev(1, 8))):
            with mock.patch.object(R.os, 'stat', return_value=fake):
                self.assertFalse(R._entropy_read('/dev/urandom', 'r', os.O_RDONLY))
        with mock.patch.object(R.os, 'stat', side_effect=PermissionError('unavailable')):
            self.assertFalse(R._entropy_read('/dev/urandom', 'r', os.O_RDONLY))


class PortableExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='portable-test-')
        cls.root=Path(cls.temp.name)
        cls.archive=cls.root/'a.zip'
        cls.build=P.build(ROOT,cls.archive)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_build_is_reproducible_and_exports_exact_source_registry(self):
        other=self.root/'repro.zip';result=P.build(ROOT,other)
        self.assertEqual(result,self.build)
        self.assertEqual(self.archive.read_bytes(),other.read_bytes())
        with zipfile.ZipFile(other) as bundle:
            manifest=json.loads(bundle.read('manifest.json'))
            expected=set(sum(P.declared_registry(ROOT).values(),[]))
            self.assertEqual({name[4:] for name in manifest['files'] if name.startswith('src/')},expected)
            self.assertFalse(any('history' in name or '.env' in name or 'run.json' in name for name in bundle.namelist()))
            self.assertEqual({item.date_time for item in bundle.infolist()},{(1980,1,1,0,0,0)})
            self.assertIn(f'{len(json.loads(bundle.read("corpus.json")))}-case', manifest['subset'])

    def test_actual_unpack_execution_isolated_and_expected(self):
        report=P.verify(self.archive,self.build['manifest_sha256'])
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['cases']),16)
        self.assertEqual(report['external_source_imports'],[])
        self.assertGreater(len(report['source_imports']),20)
        self.assertEqual([report[k] for k in ['model_calls','stores','network_calls','subprocess_calls']],[0,0,0,0])
        self.assertIn('+node-none+',report['kernel']['js'])
        self.assertTrue(all(row['ok'] for row in report['cases']))

    def test_entropy_device_fallback_preserves_real_pure_execution(self):
        # Force CPython's alternative entropy path even on a getrandom build.
        # Re-pin only this trusted runner fixture; native source stays exact.
        target = self.root / 'entropy-fallback.zip'
        with zipfile.ZipFile(self.archive) as bundle:
            members = {info.filename: (info, bundle.read(info)) for info in bundle.infolist()}
        runner = members['portable_runner.py'][1].decode()
        needle = "if __name__ == '__main__':\n    main()"
        self.assertEqual(runner.count(needle), 1)
        fixture = """_entropy_calls = []
def _fixture_urandom(count):
    with open('/dev/urandom', 'rb', buffering=0) as stream:
        raw = stream.read(count)
    _entropy_calls.append(count)
    return raw
os.urandom = _fixture_urandom
if __name__ == '__main__':
    main()
    assert len(_entropy_calls) >= 17, 'fallback was not exercised'
"""
        raw = runner.replace(needle, fixture).encode()
        members['portable_runner.py'] = (members['portable_runner.py'][0], raw)
        manifest = json.loads(members['manifest.json'][1])
        manifest['files']['portable_runner.py'] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        raw = P.canonical(manifest)
        digest = hashlib.sha256(raw).hexdigest()
        members['manifest.json'] = (members['manifest.json'][0], raw)
        with zipfile.ZipFile(target, 'w') as bundle:
            for info, raw in members.values():
                bundle.writestr(info, raw)
        report = P.verify(target, digest, source='show 6 * 7.\n')
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['cases']), 16)
        self.assertEqual(report['program']['outputs'][0]['value'], 42)
        self.assertEqual([report[k] for k in ('model_calls', 'stores', 'network_calls', 'subprocess_calls')], [0, 0, 0, 0])

    def test_changed_manifest_or_source_refused_before_execution(self):
        for name in ('manifest.json','src/symblic/kernel/language.py'):
            target=self.root/('changed-'+name.replace('/','-')+'.zip')
            def edit(members):return [(info,raw+b' ' if info.filename==name else raw) for info,raw in members]
            mutate(self.archive,target,edit)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'manifest_mismatch|source_mismatch'):
                P.verify(target,self.build['manifest_sha256'])

    def test_traversal_symlink_duplicate_and_extra_member_refused(self):
        variants=['../escape','link.py','src/symblic/kernel/language.py','extra.txt']
        for index,name in enumerate(variants):
            target=self.root/f'bad-member-{index}.zip'
            def edit(members):
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3
                info.external_attr=((stat.S_IFLNK if name=='link.py' else stat.S_IFREG)|0o444)<<16
                return members+[(info,b'x')]
            mutate(self.archive,target,edit)
            with self.subTest(name=name),self.assertRaises(ValueError):P.verify(target,self.build['manifest_sha256'])

    def test_runtime_mismatch_and_unsupported_model_statement_refused(self):
        for mode in ('runtime','ask'):
            target=self.root/(mode+'.zip')
            with zipfile.ZipFile(self.archive) as bundle:
                members={info.filename:(info,bundle.read(info)) for info in bundle.infolist()}
            manifest=json.loads(members['manifest.json'][1])
            if mode=='runtime':manifest['runtime']['unicode']='unsupported'
            else:
                corpus=copy.deepcopy(P.CORPUS);corpus[0]['source']='ask value: Int "unavailable".\n'
                raw=P.canonical(corpus);members['corpus.json']=(members['corpus.json'][0],raw)
                manifest['files']['corpus.json']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            raw=P.canonical(manifest);digest=hashlib.sha256(raw).hexdigest();members['manifest.json']=(members['manifest.json'][0],raw)
            with zipfile.ZipFile(target,'w') as bundle:
                for info,data in members.values():bundle.writestr(info,data)
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'unsupported_runtime|unsupported_statement:ask'):
                P.verify(target,digest)

    def test_existing_output_not_overwritten(self):
        with self.assertRaises(FileExistsError):P.build(ROOT,self.archive)

    def test_user_program_runs_with_inputs_and_failed_assert_stays_failed(self):
        result=P.verify(self.archive,self.build['manifest_sha256'],
            source='given n: Int.\nfor i in 1..n do\n let sq = i*i.\nend.\nshow sq.\n',inputs={'n':3})
        self.assertEqual(result['program']['status'],'done')
        self.assertEqual(result['program']['outputs'][0]['value'],[1,4,9])
        self.assertEqual(result['program']['calls'],0)
        failed=P.verify(self.archive,self.build['manifest_sha256'],source='assert false.\n')
        self.assertEqual(failed['program']['status'],'failed')
        self.assertEqual(failed['program']['error']['code'],'SYM_CHECK')

    def test_nested_asks_and_implicit_prose_never_reach_a_provider(self):
        for source in ['if false then\n ask x: Int "answer".\nend.\n','Please contact a model.\n']:
            with self.subTest(source=source),self.assertRaisesRegex(ValueError,'unsupported_statement:ask|implicit prose'):
                P.verify(self.archive,self.build['manifest_sha256'],source=source)

    def test_foreign_runtime_is_explicit_and_refused_on_wrong_host(self):
        target=copy.deepcopy(P.runtime());target['machine']='aarch64' if target['machine']=='x86_64' else 'x86_64'
        archive=self.root/'foreign.zip';built=P.build(ROOT,archive,target)
        self.assertEqual(built['runtime'],target)
        self.assertIn('unmeasured',built['conformance'])
        with self.assertRaisesRegex(ValueError,'unsupported_runtime'):
            P.verify(archive,built['manifest_sha256'])
        for bad in [{},dict(target,implementation='pypy'),dict(target,system='Windows'),dict(target,profile='unknown')]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):P.build(ROOT,self.root/'invalid-runtime.zip',bad)

    def test_comparison_requires_same_sources_cases_and_no_external_activity(self):
        report=P.verify(self.archive,self.build['manifest_sha256'])
        second=copy.deepcopy(report);second['runtime']['machine']='aarch64'
        self.assertTrue(P.compare([report,second])['ok'])
        for key,value in [('source_suite_sha256','f'*64),('corpus_sha256','f'*64),('model_calls',1)]:
            bad=copy.deepcopy(second);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):P.compare([report,bad])
        bad=copy.deepcopy(second);bad['cases'][0]['ok']=False
        with self.assertRaisesRegex(ValueError,'report_cases_mismatch'):P.compare([report,bad])

    def test_user_request_bounds_checked_before_execution(self):
        for kwargs in [{'source':'x'*262145},{'source':'show 1.','inputs':[]},
                       {'source':'show 1.','inputs':{'large':'x'*524288}}]:
            with self.subTest(keys=list(kwargs)),self.assertRaisesRegex(ValueError,'request_schema|request_size'):
                P.verify(self.archive,self.build['manifest_sha256'],**kwargs)

    def test_user_output_count_and_byte_limits_fail_visibly(self):
        for source, limit in [('for n in 1..129 do\n show n.\nend.\n','count'),
                              ('show ["x" * 100000 for n in 1..6].\n','byte')]:
            result=P.verify(self.archive,self.build['manifest_sha256'],source=source)['program']
            with self.subTest(limit=limit):
                self.assertEqual(result['status'],'failed')
                self.assertIn('portable output '+limit+' limit',result['error']['message'])
                self.assertLessEqual(len(result['outputs']),128)


if __name__=='__main__':unittest.main()

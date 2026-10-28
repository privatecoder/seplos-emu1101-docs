"""Synthetic, standard-library-only checks for the frozen historical runner."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1]/'run_historical_tests.py'
LEGACY = ('Access-Control-Patch', 'Maintenance-Patch', 'Maintenance-Split-Patch', 'UART1-Identity-Patch', 'UART1-Parameter-Patch')


class HistoricalRunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.workspace = self.base/'archive/project'
        self.mod = self.workspace/'mod'
        for index, directory in enumerate(['tools/device/tests'] + ['tools/device/_compat/'+name+'/tests' for name in LEGACY]):
            tests = self.mod/directory
            tests.mkdir(parents=True)
            (tests/'support.py').write_text('VALUE = %d\n' % index)
            (tests/'test_offline.py').write_text('import unittest\nfrom support import VALUE\nclass Offline(unittest.TestCase):\n def test_fixture(self): self.assertEqual(VALUE, %d)\n' % index)
        patcher = self.mod/'firmware/patcher'
        (patcher/'tests').mkdir(parents=True)
        (patcher/'tests/test_offline.py').write_text('import unittest\nclass Offline(unittest.TestCase):\n def test_fixture(self): self.assertTrue(True)\n')
        (patcher/'run_tests.py').write_text("import argparse,json\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()\na.report.write_text(json.dumps(dict(passed=True,tests=1,failures=0,errors=0)))\na.report.with_suffix('.log').write_text('synthetic native test passed\\n')\n")
        self.inventory()
        self.output = self.base/'results'

    def inventory(self):
        rows = []
        for path in sorted(self.mod.rglob('*')):
            if path.is_symlink():
                rows.append(dict(path=str(path.relative_to(self.mod)), type='symlink', target=path.readlink().as_posix()))
            elif path.is_file():
                rows.append(dict(path=str(path.relative_to(self.mod)), type='file', sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.manifest = self.workspace.parent/'source-manifest.json'
        self.manifest.write_text(json.dumps(rows))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(RUNNER), *map(str,args)], cwd='/private/tmp', capture_output=True, text=True)

    def execute(self, suite='all'):
        return self.run_cli('--suite',suite,'--workspace',self.workspace,'--out',self.output)

    def test_list_requires_no_archive_and_does_not_run_tests(self):
        result = self.run_cli('--list', '--workspace', self.base/'absent')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('UART1-Parameter-Patch', result.stdout)
        self.assertFalse(self.output.exists())
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_suites_have_separate_positive_results(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        reports = [json.loads(path.read_text()) for path in self.output.glob('*.json') if '.native.' not in path.name and path.name != 'report.json']
        self.assertEqual(len(reports), 7)
        self.assertTrue(all(row['passed'] and row['tests'] == 1 for row in reports))
        self.assertEqual(len(list(self.output.glob('*.log'))), 8)

    def test_changed_source_fails_before_execution(self):
        (self.mod/'tools/device/tests/test_offline.py').write_text('raise RuntimeError("must not execute")\n')
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum', result.stderr.lower())
        self.assertFalse(self.output.exists())

    def test_missing_source_fails_before_execution(self):
        (self.mod/'tools/device/tests/test_offline.py').unlink()
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing', result.stderr.lower())

    def test_unlisted_source_fails_before_execution(self):
        (self.mod/'tools/device/tests/test_extra.py').write_text('raise RuntimeError("must not execute")\n')
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unlisted', result.stderr.lower())

    def test_zero_tests_fails_even_if_unittest_exits_zero(self):
        (self.mod/'tools/device/tests/test_offline.py').write_text('import unittest\n')
        self.inventory()
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.output/'device.json').is_file(), result.stderr)
        report = json.loads((self.output/'device.json').read_text())
        self.assertEqual(report['tests'], 0)
        self.assertFalse(report['passed'])

    def test_child_failure_is_recorded(self):
        (self.mod/'tools/device/tests/test_offline.py').write_text('import unittest\nclass Failure(unittest.TestCase):\n def test_failure(self): self.fail("expected failure")\n')
        self.inventory()
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.output/'device.json').is_file(), result.stderr)
        report = json.loads((self.output/'device.json').read_text())
        self.assertNotEqual(report['returncode'], 0)
        self.assertFalse(report['passed'])

    def test_changed_symlink_fails_before_execution(self):
        link = self.mod/'tools/device/tests/support_alias.py'
        link.symlink_to('support.py')
        self.inventory()
        link.unlink()
        link.symlink_to('test_offline.py')
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertFalse(self.output.exists())

    def test_missing_test_directory_is_rejected_after_inventory_validation(self):
        import shutil
        shutil.rmtree(self.mod/'tools/device/tests')
        self.inventory()
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('test directory', result.stderr.lower())

    def test_zero_native_report_count_is_a_failure(self):
        runner = self.mod/'firmware/patcher/run_tests.py'
        runner.write_text(runner.read_text().replace('tests=1', 'tests=0'))
        self.inventory()
        result = self.execute('patcher')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.output/'patcher.json').is_file(), result.stderr)
        self.assertFalse(json.loads((self.output/'patcher.json').read_text())['passed'])

    def test_existing_broken_output_symlink_is_not_a_fresh_directory(self):
        self.output.symlink_to(self.base/'target_not_created')
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base/'target_not_created').exists())

    def test_execution_requires_fresh_output_and_explicit_suite(self):
        self.output.mkdir()
        (self.output/'keep').write_text('preserved')
        result = self.execute('device')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.output/'keep').read_text(), 'preserved')
        self.assertNotEqual(self.run_cli('--out',self.base/'another').returncode, 0)
        self.assertNotEqual(self.run_cli('--suite','device').returncode, 0)


if __name__ == '__main__':
    unittest.main()

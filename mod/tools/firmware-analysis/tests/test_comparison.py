"""Offline subprocess regressions for nonempty, successful function comparisons."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def run_tool(self, name, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(HERE / name),
                               '--data-dir', str(self.data), *args],
                              capture_output=True, text=True, cwd='/private/tmp')

    def image(self, version, dis='  1000: 00 bf  \tnop\n  1002: 70 47  \tbx lr\n'):
        (self.data / f'v{version}.raw').write_bytes(bytes(0x1100))
        (self.data / f'v{version}.dis').write_text(dis)

    def test_missing_inputs_cannot_be_identical(self):
        result = self.run_tool('cmpfn.py', '13', '1000', '14', '1000')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('IDENTICAL', result.stdout)
        self.assertIn('v13.raw', result.stderr)

    def test_absent_start_is_error(self):
        self.image('13')
        result = self.run_tool('show.py', '13', '2000')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('0x2000', result.stderr)

    def test_empty_disassembly_is_error(self):
        self.image('13', 'no decoded instructions\n')
        result = self.run_tool('show.py', '13', '1000')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('decoded', result.stderr.lower())

    def test_empty_raw_is_error(self):
        self.image('13')
        (self.data / 'v13.raw').write_bytes(b'')
        result = self.run_tool('show.py', '13', '1000')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('empty', result.stderr.lower())

    def test_child_error_with_one_valid_body_is_error(self):
        self.image('13')
        result = self.run_tool('cmpfn.py', '13', '1000', '14', '1000')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('v14.raw', result.stderr)

    def test_equal_real_decoded_bodies(self):
        self.image('13')
        self.image('14')
        result = self.run_tool('cmpfn.py', '13', '1000', '14', '1000')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('(2)', result.stdout)
        self.assertIn('IDENTICAL', result.stdout)

    def test_different_real_decoded_bodies(self):
        self.image('13')
        self.image('14', '  1000: 01 20  \tmovs r0, #1\n  1002: 70 47  \tbx lr\n')
        result = self.run_tool('cmpfn.py', '13', '1000', '14', '1000', '0', 'diff')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('difflines', result.stdout)
        self.assertIn('movs', result.stdout)


if __name__ == '__main__':
    unittest.main()

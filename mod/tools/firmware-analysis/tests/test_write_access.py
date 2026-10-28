"""Current catalogue identity, semantic equality and historical independence."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE.parents[2]
PUBLIC = ('maint153-positive-power.json', 'maint163-configurable-hard-stop.json')


class CatalogueTests(unittest.TestCase):
    def command(self, source, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(source), *args],
                              capture_output=True, text=True, cwd='/private/tmp')

    def isolated_project(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        analysis = root / 'mod/tools/firmware-analysis'
        shutil.copytree(HERE, analysis, ignore=shutil.ignore_patterns('tests', '__pycache__', 'emulators', 'write_access_revision*', 'write_access_v16.py'))
        shutil.copy2(HERE.parent / '_paths.py', analysis.parent / '_paths.py')
        for name in PUBLIC:
            original = PROJECT / 'mod/firmware/releases' / name
            target = root / 'mod/firmware/releases' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            metadata = json.loads(original.read_text())
            image = root / 'local/releases' / metadata['name']
            image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / 'local/releases' / metadata['name'], image)
        vendor = root / 'vendor/firmware'
        vendor.mkdir(parents=True)
        shutil.copy2(PROJECT / 'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex', vendor)
        package = root / 'mod/firmware/patcher/seplos'
        package.mkdir(parents=True)
        for name in ('__init__.py', 'image.py'):
            shutil.copy2(PROJECT / 'mod/firmware/patcher/seplos' / name, package)
        return root, analysis / 'write_access.py'

    def test_catalogue_exactly_preserves_extracted_semantics(self):
        result = self.command(HERE / 'write_access.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), 'e18e15de8b5bc3be0badc3cb56b0964957f0f3f83f6641e8cf98e876df59ab7c')
        self.assertEqual((len(data['parameters']), len(data['function_bits']), len(data['matrix'])), (87, 64, 23))

    def test_current_verify_needs_no_historical_modules_or_build_reports(self):
        root, source = self.isolated_project()
        self.assertFalse((root / 'local/builds').exists())
        result = self.command(source, '--verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['passed'])
        self.assertEqual(report['verification'], 'current release hashes and MNT04 metadata; no native emulation')
        self.assertEqual(set(report['profiles']), {'1.5.3', '1.6.3'})
        result = self.command(source, '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('All 87 A1 parameters', result.stdout)

    def test_current_verify_rejects_mismatched_public_metadata(self):
        root, source = self.isolated_project()
        path = root / 'mod/firmware/releases' / PUBLIC[0]
        data = json.loads(path.read_text())
        data['build_id'] = '0000000000000000'
        path.write_text(json.dumps(data))
        result = self.command(source, '--verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('MNT04', result.stderr)

    def test_historical_probe_uses_only_extracted_fixed_model(self):
        source = (HERE / 'probe_write_access.py').read_text()
        self.assertNotIn("HERE/'write_access_v16.py'", source)
        self.assertIn("HERE/'historical_write_model.py'", source)
        data = json.loads((HERE / 'historical_write_model.json').read_text())
        encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), '270794ff992da3f02e0c1770afca8344c189bfa85bf598e45468ef1f41de9b0e')
        self.assertEqual(set(data['IMAGES']), {'OEM16.06.13', 'MAINT1.5', 'MAINT1.6'})

    def test_published_matrix_matches_current_renderer(self):
        result = self.command(HERE / 'write_access.py', '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        published = (PROJECT / 'mod/docs/firmware/uart-write-capabilities.md').read_text()
        self.assertTrue(result.stdout == published,
                        'Published capabilities must equal write_access.py --markdown; regenerate from the current template.')

    def test_markdown_displays_canonical_ports_without_changing_raw_catalogue(self):
        result = self.command(HERE / 'write_access.py', '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| UART0, UART1[W], UART2 |', result.stdout)
        self.assertNotRegex(result.stdout, r'\b[RCD](?:/[RCD])+\b')
        raw = self.command(HERE / 'write_access.py')
        data = json.loads(raw.stdout)
        self.assertIn('R', json.dumps(data['matrix']))

    def test_output_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'existing.json'
            output.write_text('retain me')
            result = self.command(HERE / 'write_access.py', '--out', str(output))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), 'retain me')


if __name__ == '__main__':
    unittest.main()

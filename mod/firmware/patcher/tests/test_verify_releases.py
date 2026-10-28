"""Release identity checking uses current public metadata and exact bytes."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import PROJECT_ROOT, RELEASES


class ReleaseVerification(unittest.TestCase):
    def verifier(self):
        path = ROOT / 'verify_releases.py'
        self.assertTrue(path.is_file(), 'reusable release verifier missing')
        spec = importlib.util.spec_from_file_location('release_verifier', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def metadata(self):
        return json.loads((PROJECT_ROOT / 'mod/firmware/releases/maint153-positive-power.json').read_text())

    def test_existing_release_matches_full_identity(self):
        module = self.verifier()
        metadata = self.metadata()
        result = module.verify_existing((RELEASES / metadata['name']).read_bytes(), metadata)
        self.assertEqual(result['build_id'], metadata['build_id'])
        self.assertEqual(result['info_hex'], metadata['info_hex'].lower())

    def test_wrong_hash_or_build_identity_is_rejected(self):
        module = self.verifier()
        metadata = self.metadata()
        raw = (RELEASES / metadata['name']).read_bytes()
        for field in ('ehex_sha256', 'app_sha256', 'build_id', 'info_hex'):
            with self.subTest(field=field):
                wrong = copy.deepcopy(metadata)
                wrong[field] = '0' * len(metadata[field])
                with self.assertRaisesRegex(ValueError, field):
                    module.verify_existing(raw, wrong)

    def test_rejects_wrong_version_flags_or_extent(self):
        module = self.verifier()
        metadata = self.metadata()
        raw = (RELEASES / metadata['name']).read_bytes()
        for field, value in [('patch_version', '1.6.3'), ('image_flags', 0), ('app_bytes', 0)]:
            with self.subTest(field=field):
                wrong = {**metadata, field: value}
                with self.assertRaisesRegex(ValueError, field):
                    module.verify_existing(raw, wrong)

    def test_retired_release_metadata_is_rejected(self):
        module = self.verifier()
        metadata = self.metadata()
        raw = (RELEASES / metadata['name']).read_bytes()
        for version in ('1.5', '1.6', '1.5.2', '1.6.2'):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'unsupported MAINT version'):
                module.verify_existing(raw, {**metadata, 'patch_version': version})

    def test_rebuild_source_must_match_pinned_OEM(self):
        module = self.verifier()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'wrong.ehex'
            source.write_bytes(b'wrong OEM')
            with self.assertRaisesRegex(ValueError, 'OEM source sha256'):
                module.verify_source(source)

    def test_isolated_cli_verifies_current_metadata_from_neutral_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'verification'
            result = subprocess.run(
                [sys.executable, '-I', '-B', str(ROOT / 'verify_releases.py'), '--out', str(out)],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out / 'results.json').read_text())
            self.assertTrue(report['passed'])
            self.assertFalse(report['rebuild'])
            self.assertEqual(report['profiles'], 2)
            self.assertEqual({row['existing']['patch_version'] for row in report['results']},
                             {'1.5.3', '1.6.3'})
            for row in report['results']:
                self.assertEqual(len(row['existing']['build_id']), 16)
                self.assertEqual(len(row['existing']['ehex_sha256']), 64)

    def test_existing_output_is_never_overwritten(self):
        self.verifier()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'existing'
            out.mkdir()
            marker = out / 'keep.txt'
            marker.write_text('preserved')
            result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'verify_releases.py'), '--out', str(out)],
                                    cwd=tmp, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('output already exists', result.stderr)
            self.assertEqual(marker.read_text(), 'preserved')


if __name__ == '__main__':
    unittest.main()

"""Immutable metadata and explicit binary prerequisite contracts."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import corpus


class FixtureBoundary(unittest.TestCase):
    def test_fixture_loader_is_explicit_and_integrity_checked(self):
        loader = getattr(corpus, 'fixture', None)
        self.assertTrue(callable(loader), 'missing maintained fixture loader')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b'{"facts": {"original_app_sha256": "test"}}\n'
            (root / 'sample.json').write_bytes(payload)
            (root / 'registry.json').write_text(json.dumps({'fixtures': {
                'sample': {'file': 'sample.json', 'sha256': hashlib.sha256(payload).hexdigest(),
                           'bytes': len(payload)}}}))
            self.assertEqual(loader('sample', root=root)['facts']['original_app_sha256'], 'test')
            (root / 'sample.json').unlink()
            with self.assertRaisesRegex(FileNotFoundError, 'required metadata fixture.*sample'):
                loader('sample', root=root)
            (root / 'sample.json').write_bytes(payload.replace(b'test', b'evil'))
            with self.assertRaisesRegex(ValueError, 'fixture integrity.*sample'):
                loader('sample', root=root)

    def test_current_tests_have_no_build_report_dependency(self):
        self.assertNotIn('builds', corpus.MANIFEST, 'disposable build directory remains in manifest')
        for path in (ROOT / 'tests').glob('test_*.py'):
            if path == Path(__file__):
                continue
            self.assertNotIn('BUILDS', path.read_text(), path.name)
        registry = ROOT / 'tests' / 'fixtures' / 'registry.json'
        self.assertTrue(registry.is_file(), 'fixture provenance registry missing')
        for name in json.loads(registry.read_text())['fixtures']:
            self.assertIsInstance(corpus.fixture(name), dict)

    def test_corpus_requires_exact_inputs_and_rejects_corruption(self):
        self.assertTrue(all(group.get('files') for group in corpus.MANIFEST['groups']),
                        'binary inputs must be listed explicitly')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = corpus.MANIFEST['groups'][0]
            directory = root / first['directory']
            directory.mkdir(parents=True)
            (directory / 'unrelated.ehex').write_bytes(b'unrelated')
            with self.assertRaisesRegex(FileNotFoundError, 'required corpus input'):
                corpus.corpus_groups(root)
            row = first['files'][0]
            (directory / row['name']).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'corpus input integrity'):
                corpus.corpus_groups(root)


if __name__ == '__main__':
    unittest.main()

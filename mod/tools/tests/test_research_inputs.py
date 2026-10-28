"""Offline bindings reject stale or missing analysis inputs before emulation."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('library_paths', TOOLS/'_paths.py')
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)


class ResearchInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root/'local/builds/example/report.json'
        self.input.parent.mkdir(parents=True)
        self.input.write_bytes(b'{"facts": {}}\n')
        self.registry = self.root/'inputs.json'
        raw = self.input.read_bytes()
        self.data = {'schema': 1, 'inputs': {'example': {
            'path': self.input.relative_to(self.root).as_posix(),
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}}
        self.save()

    def save(self):
        self.registry.write_text(json.dumps(self.data))

    def lookup(self, name='example'):
        return paths.research_input(name, root=self.root, registry=self.registry)

    def test_valid_source_returns_canonical_file(self):
        self.assertEqual(self.lookup(), self.input)

    def test_modified_source_is_rejected(self):
        self.input.write_bytes(b'{"facts": []}\n')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.lookup()

    def test_missing_source_is_explicit(self):
        self.input.unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'example'):
            self.lookup()

    def test_unknown_binding_does_not_fall_back_to_search(self):
        with self.assertRaisesRegex(KeyError, 'unknown research input'):
            self.lookup('different')

    def test_untrusted_registry_cannot_escape_root(self):
        for value in ('../report.json', '/private/tmp/report.json'):
            with self.subTest(value=value):
                self.data['inputs']['example']['path'] = value
                self.save()
                with self.assertRaisesRegex(ValueError, 'relative'):
                    self.lookup()

    def test_isolated_import_and_lookup_ignore_cwd(self):
        code = ('import sys; sys.path.insert(0, %r); '
                'from _paths import research_input; '
                'from pathlib import Path; '
                'print(research_input("example", root=Path(%r), registry=Path(%r)))') % (str(TOOLS), str(self.root), str(self.registry))
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd='/private/tmp', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.input))

    def test_all_installed_bindings_match_exact_sources(self):
        data = json.loads((TOOLS/'research-inputs.json').read_text())
        self.assertGreaterEqual(len(data['inputs']), 6)
        for name in data['inputs']:
            with self.subTest(name=name):
                self.assertTrue(paths.research_input(name).is_file())


if __name__ == '__main__':
    unittest.main()

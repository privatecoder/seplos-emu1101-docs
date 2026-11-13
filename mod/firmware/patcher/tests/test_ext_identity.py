"""EMU1101-EXT identity and public API boundaries use no legacy aliases."""
from pathlib import Path
import hashlib
import importlib.util
import inspect
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import ORIGINALS, fixture
from seplos.build import build
from seplos.cli import run_worker
from seplos.image import Image
from seplos.profiles import SUPPORTED_VERSIONS


class ExtendedIdentity(unittest.TestCase):
    def test_all_four_profiles_require_the_ext_cli_option(self):
        self.assertEqual(SUPPORTED_VERSIONS, ('1.5.4', '1.6.4', '1.5.5', '1.6.5'))
        result = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'seplos_patch.py'),
                                 'patch', '--help'], cwd='/private/tmp', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--ext-version {1.5.4,1.6.4,1.5.5,1.6.5}', result.stdout)
        self.assertNotIn('--maint-version', result.stdout)
        self.assertIn('Light 1.5.x; Full 1.6.x', result.stdout)
        self.assertIn('Full 1.6.4/1.6.5', result.stdout)
        self.assertIn('1=enabled and 0=denied permissions', ' '.join(result.stdout.split()))

    def test_python_apis_expose_only_ext_version(self):
        for api in (build, run_worker):
            with self.subTest(api=api.__name__):
                self.assertIn('ext_version', inspect.signature(api).parameters)
                self.assertNotIn('maint_version', inspect.signature(api).parameters)

    def test_legacy_option_and_api_keyword_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'output'
            result = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'seplos_patch.py'),
                                     'patch', 'missing.ehex', '--ext-version', '1.5.4',
                                     '--maint-version', '1.5.4', '--out', str(output)],
                                    cwd='/private/tmp', capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('unrecognized arguments: --maint-version', result.stderr)
            self.assertFalse(output.exists())
        with self.assertRaises(TypeError):
            build(None, None, maint_version='1.5.4')
        with self.assertRaises(TypeError):
            run_worker('missing.ehex', 'patch', maint_version='1.5.4')

    def test_verifier_accepts_ext_and_rejects_legacy_bytes_even_with_matching_hashes(self):
        spec = importlib.util.spec_from_file_location('ext_release_verifier', ROOT/'verify_releases.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        original = Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
        base_version = bytes(fixture('oem-16.06.13-facts')['facts']['oracle']['base_version'])
        for version in SUPPORTED_VERSIONS:
            for signature in (b'EXT', b'MNT'):
                with self.subTest(version=version, signature=signature):
                    template = signature + b'\x05\0\0\x0d' + bytes(map(int, version.split('.'))) + bytes.fromhex('0123456789abcdef') + bytes([0x3a if version.startswith('1.5.') else 0xfe]) + b'\0\x0f'
                    image = original.with_app(original.app + template + b'\0'*3)
                    raw = image.render().encode('ascii')
                    info = template[:4] + base_version + template[6:]
                    metadata = dict(name='synthetic.ehex', patch_version=version, info_format=5,
                                    info_bytes=21, ehex_sha256=hashlib.sha256(raw).hexdigest(),
                                    app_sha256=image.sha, app_bytes=len(image.app), info_hex=info.hex(),
                                    build_id='0123456789abcdef', image_flags=template[18], remote_capabilities=15)
                    if signature == b'EXT':
                        self.assertEqual(verifier.verify_existing(raw, metadata)['info_hex'], info.hex())
                    else:
                        with self.assertRaisesRegex(ValueError, 'info_hex'):
                            verifier.verify_existing(raw, metadata)


if __name__ == '__main__':
    unittest.main()

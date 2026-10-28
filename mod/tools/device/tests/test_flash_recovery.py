"""Offline checks for strict bootloader ACK validation; never open a device."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import importlib.util
from pathlib import Path
import unittest
import contextlib
import hashlib
import io
import sys
import tempfile
from unittest.mock import patch

fixture_spec = importlib.util.spec_from_file_location('flash_test_fixtures', Path(__file__).with_name('test_flash_gap.py'))
fixtures = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixtures)

path = Path(__file__).resolve().parents[1] / 'flash_recovery.py'
spec = importlib.util.spec_from_file_location('tested_recovery', path)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def test_measured_package_reply(self):
        raw = bytes.fromhex('3a3a3a3a524642000200000100ff230d0d0d0d')
        self.assertEqual(recovery.validate(raw, (b'RFB',)), b'\1\0')

    def test_write_ack_and_negative_ack(self):
        self.assertEqual(recovery.validate(recovery.codec.boot_frame(b'WFB'), (b'WFB',)), b'')
        with self.assertRaises(ValueError):
            recovery.validate(recovery.codec.boot_frame(b'RFN'), (b'WFB', b'RFB'))

    def test_corruption_truncation_extra_bytes_and_wrong_address(self):
        raw = recovery.codec.boot_frame(b'WFB')
        bad_checksum = raw[:-6] + b'\0\0' + raw[-4:]
        for invalid in (raw[:-1], raw+b'\0', bad_checksum, recovery.codec.boot_frame(b'WFB', 1)):
            with self.subTest(raw=invalid.hex()), self.assertRaises(ValueError):
                recovery.validate(invalid, (b'WFB',))

    def test_data_address_and_payload(self):
        payload = bytes(range(256))
        raw = recovery.codec.boot_frame(b'WFD', 16*222, payload)
        self.assertEqual(recovery.validate(raw, (b'WFD',), 16*222), payload)


class RecoveryFlowTests(unittest.TestCase):
    def test_matching_hash_does_not_allow_malformed_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'invalid.ehex'
            lines = fixtures.synthetic_image()[0]
            lines[16] = lines[16][:-2] + '00'
            image.write_text('\n'.join(lines) + '\n')
            log = Path(directory)/'new.log'
            args = ['flash_recovery.py', 'FAKE_PORT', str(image), hashlib.sha256(image.read_bytes()).hexdigest(), str(log)]
            with patch.object(sys, 'argv', args), patch.object(recovery.codec, 'Port') as port:
                with self.assertRaises(ValueError): recovery.main()
                port.assert_not_called()
            self.assertFalse(log.exists())

    def test_existing_log_prevents_recovery_device_open(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.ehex'
            image.write_text('\n'.join(fixtures.synthetic_image()[0]) + '\n')
            log = Path(directory)/'old.log'
            log.write_text('original')
            args = ['flash_recovery.py', 'FAKE_PORT', str(image), hashlib.sha256(image.read_bytes()).hexdigest(), str(log)]
            with patch.object(sys, 'argv', args), patch.object(recovery.codec, 'Port') as port:
                with self.assertRaises(FileExistsError): recovery.main()
                port.assert_not_called()
            self.assertEqual(log.read_text(), 'original')

    def test_rfb_cannot_acknowledge_erase_and_is_never_retried(self):
        sent = []
        class Port:
            def __init__(self, path, log): self.fd = 123
            def send(self, raw): sent.append(raw)
            def read_until(self, done, timeout):
                return recovery.codec.boot_frame(b'RFB', data=b'\1\0' if sent[-1][4:7] == b'RFL' else b'')
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.ehex'
            image.write_text('\n'.join(fixtures.synthetic_image()[0]) + '\n')
            args = ['flash_recovery.py', 'FAKE_PORT', str(image), hashlib.sha256(image.read_bytes()).hexdigest(), str(Path(directory)/'new.log')]
            with patch.object(sys, 'argv', args), patch.object(recovery.codec, 'Port', Port), patch('os.close') as close, patch.object(recovery.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError): recovery.main()
                close.assert_called_once_with(123)
        self.assertEqual([raw[4:7] for raw in sent], [b'RFL', b'WFE'])


if __name__ == '__main__':
    unittest.main()

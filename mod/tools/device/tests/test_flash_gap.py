"""Offline flash preflight and wire checks using a synthetic EMU1101 image."""
import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location('tested_' + name, Path(__file__).resolve().parents[1] / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(address, kind, data):
    raw = bytes([len(data)]) + address.to_bytes(2, 'big') + bytes([kind]) + data
    return ':' + (raw + bytes([-sum(raw) & 255])).hex().upper()


def synthetic_image():
    header = b'SWM181RCT6_64_M0EMU1101_10D_HW16RS485'.ljust(256, b'\0')
    app = struct.pack('<II', 0x20002000, 0xC1) + bytes(4096-8)
    lines = [':10000000' + header[i:i+16].hex().upper() + 'AA' for i in range(0, 256, 16)]
    lines += [record(i, 0, app[i:i+16]) for i in range(0, len(app), 16)]
    lines += [record(0, 5, b'\0\0\0\xC1'), record(0, 1, b'')]
    return lines, header + app + b'\0\0\0\xC1'


class FlashGapTests(unittest.TestCase):
    def setUp(self):
        self.module = load('flash_gap')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / 'synthetic.ehex'
        self.log = Path(self.directory.name) / 'flash.log'
        self.lines, self.stream = synthetic_image()
        self.image.write_text('\n'.join(self.lines) + '\n')

    def invoke(self, extra=()):
        args = ['flash_gap.py', 'FAKE_PORT', str(self.image), '0', str(self.log), *extra]
        with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
            self.module.main()

    def test_full_ff_blocks_checksum_wraps_at_and_above_65535(self):
        payload = b'\xff' * 256
        for address, total, checksum in ((0x0D10, 65535, b'\x00\x01'), (0x0D20, 65551, b'\xff\xf1')):
            with self.subTest(address=address):
                raw = self.module.boot_frame(b'WFD', address, payload)
                self.assertEqual(sum(raw[4:-6]), total)
                self.assertEqual(raw[-6:-4], checksum)
                self.assertEqual((sum(raw[4:-6]) + int.from_bytes(raw[-6:-4], 'big')) & 0xFFFF, 0)
                self.assertEqual(raw[11:-6], payload)

    def test_valid_ff_filled_application_can_complete_preflight_and_flash(self):
        app = struct.pack('<II', 0x20002000, 0xC1) + b'\xff'*(4096-8)
        lines = self.lines[:16] + [record(i, 0, app[i:i+16]) for i in range(0, len(app), 16)] + self.lines[-2:]
        self.image.write_text('\n'.join(lines) + '\n')
        fake, ports = self.fake_port(query_address=0)
        with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
            self.invoke()
        payload = b''.join(raw[11:-6] for raw in ports[0].sent if raw[4:7] == b'WFD')
        self.assertEqual(payload[256:256+len(app)], app)
        self.assertTrue(ports[0].closed)

    def test_valid_stream_keeps_pseudo_header_and_entry_payload(self):
        self.assertEqual(self.module.stream_of(self.image), self.stream)

    def test_rejects_invalid_containers_before_opening_a_port(self):
        changes = {
            'checksum': lambda lines: lines.__setitem__(16, lines[16][:-2] + '00'),
            'gap': lambda lines: lines.__setitem__(17, record(32, 0, bytes(16))),
            'family': lambda lines: lines.__setitem__(0, ':10000000' + '00'*16 + 'AA'),
            'missing EOF': lambda lines: lines.pop(),
            'unsupported type': lambda lines: lines.insert(17, record(0, 4, b'\0\0')),
            'trailing garbage': lambda lines: lines.append('not a record'),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                lines = self.lines.copy()
                change(lines)
                self.image.write_text('\n'.join(lines) + '\n')
                with patch.object(self.module, 'Port', side_effect=AssertionError('device opened before preflight completed')) as port:
                    with self.assertRaises(ValueError):
                        self.invoke()
                    port.assert_not_called()
                self.assertFalse(self.log.exists())

    def test_existing_log_is_preserved_before_port_open(self):
        self.log.write_text('original\n')
        with patch.object(self.module, 'Port', side_effect=AssertionError('device opened before preflight completed')) as port:
            with self.assertRaises(FileExistsError):
                self.invoke()
            port.assert_not_called()
        self.assertEqual(self.log.read_text(), 'original\n')

    def fake_port(self, query_address=7, bad_query=False, write_reply=b'WFB'):
        module = self.module
        ports = []
        class FakePort:
            def __init__(self, path, log):
                self.log = log
                self.sent = []
                self.closed = False
                ports.append(self)
            def send(self, raw, discard_pending=True):
                self.sent.append(raw)
            def read_until(self, done, timeout):
                raw = self.sent[-1]
                if raw.startswith(b'~') and raw[7:9] == b'51':
                    reply = module.ascii_frame(0x20, query_address, 0, bytes(range(12)).hex().upper())
                    return reply[:-5] + b'0000\r' if bad_query else reply
                if raw.startswith(b'~') or raw[4:7] == b'RFL':
                    return module.boot_frame(b'RFB', data=b'\1\0')
                return module.boot_frame(write_reply)
            def close(self):
                self.closed = True
        return FakePort, ports

    def test_address_used_for_query_reset_and_verification(self):
        fake, ports = self.fake_port()
        with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
            self.invoke(['--address', '7'])
        self.assertEqual(len(ports), 1)
        p = ports[0]
        ascii_packets = [raw for raw in p.sent if raw.startswith(b'~')]
        self.assertEqual(len(ascii_packets), 3)
        self.assertTrue(all(raw[3:5] == b'07' for raw in ascii_packets))
        self.assertTrue(p.closed)
        data_frames = [raw for raw in p.sent if raw[4:7] == b'WFD']
        payload = b''.join(raw[11:-6] for raw in data_frames)
        self.assertEqual(payload, self.stream.ljust(len(data_frames)*256, b'\0'))
        self.assertEqual([int.from_bytes(raw[9:11], 'big') for raw in data_frames], [16*i for i in range(len(data_frames))])

    def test_invalid_query_checksum_or_foreign_address_cannot_reset(self):
        for options in ({'bad_query': True}, {'query_address': 8}):
            with self.subTest(options=options):
                if self.log.exists():
                    self.log.unlink()
                fake, ports = self.fake_port(**options)
                with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
                    with self.assertRaises((ValueError, SystemExit)):
                        self.invoke(['--address', '7'])
                self.assertEqual(len(ports), 1)
                self.assertEqual(len(ports[0].sent), 1)
                self.assertTrue(ports[0].closed)

    def test_application_return_requires_valid_reply_from_same_pack(self):
        fake, ports = self.fake_port()
        read = fake.read_until
        def read_with_invalid_first_return(port, done, timeout):
            raw = read(port, done, timeout)
            query_count = sum(packet.startswith(b'~') and packet[7:9] == b'51' for packet in port.sent)
            return raw[:-5] + b'0000\r' if port.sent[-1][7:9] == b'51' and query_count == 2 else raw
        fake.read_until = read_with_invalid_first_return
        with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
            self.invoke(['--address', '7'])
        queries = [raw for raw in ports[0].sent if raw.startswith(b'~') and raw[7:9] == b'51']
        self.assertEqual(len(queries), 3)
        self.assertTrue(ports[0].closed)

    def test_unsupported_bootloader_package_cannot_erase(self):
        fake, ports = self.fake_port()
        read = fake.read_until
        def read_with_unsupported_package(port, done, timeout):
            raw = read(port, done, timeout)
            return self.module.boot_frame(b'RFB', data=b'\2\0') if raw.startswith(b'::::RFB') else raw
        fake.read_until = read_with_unsupported_package
        with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'unsupported bootloader ACK'):
                self.invoke(['--address', '7'])
        self.assertFalse(any(raw.startswith(b'::::W') for raw in ports[0].sent))
        self.assertTrue(ports[0].closed)

    def test_uncertain_write_ack_aborts_without_replay(self):
        fake, ports = self.fake_port(write_reply=b'RFB')
        with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
            with self.assertRaises((ValueError, SystemExit)):
                self.invoke(['--address', '7'])
        self.assertEqual(len(ports), 1)
        self.assertEqual([raw[4:7] for raw in ports[0].sent if raw.startswith(b'::::') and raw[4:5] == b'W'], [b'WFE'])
        self.assertTrue(ports[0].closed)

    def test_default_address_zero_keeps_original_positional_cli(self):
        fake, ports = self.fake_port(query_address=0)
        with patch.object(self.module, 'Port', fake), patch.object(self.module.time, 'sleep'):
            self.invoke()
        self.assertTrue(all(raw[3:5] == b'00' for raw in ports[0].sent if raw.startswith(b'~')))

    def test_address_range_rejected_before_port_open(self):
        for address in ('-1', '22', '0x07'):
            with self.subTest(address=address), patch.object(self.module, 'Port') as port, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.invoke(['--address', address])
                port.assert_not_called()
        self.assertFalse(self.log.exists())

    def test_port_configuration_failure_closes_open_descriptor(self):
        with patch.object(self.module.os, 'open', return_value=123), patch.object(self.module.termios, 'tcgetattr', side_effect=OSError('configuration failed')), patch.object(self.module.os, 'close') as close:
            with self.assertRaises(OSError):
                self.module.Port('FAKE_PORT', io.StringIO())
            close.assert_called_once_with(123)

    def test_negative_gap_rejected_before_port_open(self):
        args = ['flash_gap.py', 'FAKE_PORT', str(self.image), '-1', str(self.log)]
        with patch.object(sys, 'argv', args), patch.object(self.module, 'Port', side_effect=AssertionError('device opened before preflight completed')) as port, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.module.main()
            port.assert_not_called()


if __name__ == '__main__':
    unittest.main()

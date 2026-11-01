"""Offline contracts for MNT05 and the four addressed diagnostic reads."""
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

CLIENT = Path(__file__).resolve().parents[1] / 'maintenance_client.py'


def u16(value, endian='big'):
    return value.to_bytes(2, endian)


def u32(value, endian='big', signed=False):
    return value.to_bytes(4, endian, signed=signed)


def soc_record(remaining=12345, charged=70000):
    return (b'\xa0\x14' + u16(remaining, 'little') + u16(28000, 'little')
            + u32(charged, 'little') + u32(0xfedcba98, 'little')
            + u16(23, 'little') + u16(45, 'little') + u16(67, 'little') + b'\x12\x34')


def calibration_record():
    return (b'\xa0\x33\x14' + b''.join(u16(50000+i, 'little') for i in range(16))
            + u16(12400, 'little') + u16(38750, 'little') + u16(61000, 'little')
            + u32(-123456, 'little', True) + u16(54321, 'little')
            + u32(-765432, 'little', True) + b'\x12\x34')


def checkpoint_payload():
    return (bytes([1, 1, 1, 2, 3, 1]) + u16(29000) + u16(13000)
            + u32(65000) + u32(0xfedcba98) + u16(12345) + u16(28000)
            + u16(441) + soc_record() + soc_record(12000, 80000))


class RemoteDiagnosticsClient(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('remote_client', CLIENT)
        self.c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.c)

    def test_mnt05_preserves_field_positions_and_uses_explicit_capabilities(self):
        for version, flags in ((b'\1\5\4', 0x3a), (b'\1\6\4', 0xfe)):
            for caps in (0, 1, 2, 4, 8, 15):
                raw = b'MNT\5\x10\6\x0d' + version + bytes(range(8)) + bytes([flags]) + u16(caps)
                d = self.c.parse_info(raw)
                self.assertEqual(d['patch_version'], '.'.join(str(x) for x in version))
                self.assertEqual(d['build_id'], '0001020304050607')
                self.assertEqual(d['image_flags'], flags)
                self.assertEqual(d['capabilities'], caps)
                for name, bit in (('uart1_history', 1), ('calibration_pages', 2),
                                  ('persisted_soc_contents', 4), ('full_width_energy', 8)):
                    self.assertEqual(d[name], bool(caps & bit))
                self.assertEqual(d['configurable_hard_stop'], bool(flags & 128))
                if flags & 128:
                    self.assertIsNone(d['hard_stop'])
                    self.assertEqual(self.c.hard_stop_state(0x40, flags, 5)['enabled'], True)

    def test_historical_info_does_not_infer_new_capabilities_from_versions(self):
        for raw in (b'MNT\3\x10\6\x0d\1\6' + bytes(8) + b'\x0e',
                    b'MNT\4\x10\6\x0d\1\6\xff' + bytes(8) + b'\xfe'):
            d = self.c.parse_info(raw)
            self.assertNotIn('capabilities', d)
            for name in ('uart1_history', 'calibration_pages', 'persisted_soc_contents', 'full_width_energy'):
                self.assertFalse(d.get(name, False))

    def test_mnt05_rejects_malformed_lengths_formats_and_reserved_capabilities(self):
        good = b'MNT\5\x10\6\x0d\1\6\4' + bytes(8) + b'\xfe\0\x0f'
        for bad in (good[:-1], good+b'\0', b'MNT\6'+good[4:], good[:19]+b'\x80\0', good[:19]+b'\0\x10'):
            with self.subTest(raw=bad), self.assertRaises(ValueError):
                self.c.parse_info(bad)

    def test_read_requests_address_both_ports_and_never_emit_write_selectors(self):
        actions = {'history-oldest': (0x4b, b'\0\0'), 'history-next': (0x4b, b'\0\1'),
                   'calibration-active': (0x64, b'\5\0'), 'calibration-primary': (0x64, b'\5\1'),
                   'calibration-backup': (0x64, b'\5\2'), 'checkpoint-energy': (0x64, b'\6')}
        for address in range(22):
            for uart in ('UART0', 'UART1'):
                for action, (code, info) in actions.items():
                    with self.subTest(address=address, uart=uart, action=action):
                        self.assertEqual(self.c.request(action, address, uart), self.c.frame(code, info.hex().upper(), address))
        for address in (-1, 22, 255, True, '1'):
            with self.assertRaises(ValueError):
                self.c.request('checkpoint-energy', address)

    def test_history_single_record_or_empty_with_no_automatic_fetch(self):
        raw = b'\1\1' + u16(2026) + bytes(range(1, 94))
        d = self.c.parse_history(raw)
        self.assertEqual(d, {'format': 1, 'empty': False, 'last_record': True,
                             'year': 2026, 'record_tail_hex': bytes(range(1, 94)).hex()})
        self.assertEqual(self.c.parse_history(b''), {'empty': True})
        for bad in (raw[:-1], raw+b'\0', b'\2'+raw[1:], raw[:1]+b'\2'+raw[2:]):
            with self.assertRaises(ValueError):
                self.c.parse_history(bad)

    def test_active_calibration_big_endian_and_signed_currents(self):
        raw = (bytes([1, 0, 0x14, 16]) + b''.join(u16(50000+i) for i in range(16))
               + u16(12400) + u16(38750) + u16(61000) + u16(62000)
               + u32(-123456, signed=True) + u32(-765432, signed=True)
               + u16(61999) + u16(62001) + u32(-0x1234567, signed=True)
               + u32(0x1234567) + u32(-4600, signed=True) + u32(5000))
        d = self.c.parse_calibration(raw)
        self.assertEqual(d['page'], 'active')
        self.assertEqual(d['invalid_flags'], 0x14)
        self.assertEqual(d['cell_count'], 16)
        self.assertEqual(d['cell_gains'], list(range(50000, 50016)))
        self.assertEqual(d['voltage_gains'], [12400, 38750])
        self.assertEqual(d['current_gains'], [61000, 62000])
        self.assertEqual(d['zero_raw'], [-123456, -765432])
        self.assertEqual(d['references'], [61999, 62001])
        self.assertEqual(d['raw_currents'], [-0x1234567, 0x1234567])
        self.assertEqual(d['converted_currents_ma'], [-4600, 5000])

    def test_stored_calibration_native_endian_and_crc_not_physical_health(self):
        record = calibration_record()
        for page, label in ((1, 'primary'), (2, 'backup')):
            d = self.c.parse_calibration(bytes([1, page, 1, 1, 51])+record)
            self.assertEqual(d['page'], label)
            self.assertEqual(d['classification'], 'valid')
            self.assertTrue(d['native_crc_accepted'])
            self.assertEqual(d['raw_prefix_hex'], record.hex())
            self.assertEqual(d['fields']['cell_gains'], list(range(50000, 50016)))
            self.assertEqual(d['fields']['current_gains'], [61000, 54321])
            self.assertEqual(d['fields']['zero_raw'], [-123456, -765432])
        malformed = b'\xb0\x34'+record[2:]
        d = self.c.parse_calibration(bytes([1, 1, 2, 1, 52])+malformed)
        self.assertEqual(d['classification'], 'invalid')
        self.assertTrue(d['native_crc_accepted'])
        self.assertEqual(d['raw_prefix_hex'], malformed.hex())
        self.assertIsNone(d['fields'])
        self.assertNotIn('healthy', d)

    def test_checkpoint_separates_live_big_endian_from_stored_native_endian(self):
        d = self.c.parse_checkpoint_energy(checkpoint_payload())
        self.assertEqual(d['comparison'], 'different')
        self.assertEqual(d['boot_choice'], 'primary')
        self.assertEqual(d['live'], {'p58_full_cah': 29000, 'p59_remaining_cah': 13000,
                         'charged_energy_dkwh': 65000, 'discharged_energy_dkwh': 0xfedcba98,
                         'remaining_cah': 12345, 'full_cah': 28000, 'soc_tenths': 441})
        p, b = d['primary'], d['backup']
        self.assertEqual(p['raw_hex'], soc_record().hex())
        self.assertEqual(p['fields'], {'remaining_cah': 12345, 'full_cah': 28000,
                         'charged_energy_dkwh': 70000, 'discharged_energy_dkwh': 0xfedcba98,
                         'cycles': 23, 'soc_cycle_reference_tenths': 45,
                         'soc_decrease_tenths': 67, 'crc': 0x3412})
        self.assertEqual(b['fields']['remaining_cah'], 12000)
        self.assertNotIn('qmax', p['fields'])

    def test_checkpoint_crc_accepted_wrong_shape_is_visible_but_invalid(self):
        raw = bytearray(checkpoint_payload())
        raw[1] = 2
        raw[3] = 0
        raw[24] = 0xb0
        d = self.c.parse_checkpoint_energy(bytes(raw))
        self.assertEqual(d['primary']['classification'], 'invalid')
        self.assertTrue(d['primary']['native_crc_accepted'])
        self.assertEqual(d['primary']['raw_hex'], bytes(raw[24:46]).hex())
        self.assertIsNone(d['primary']['fields'])
        self.assertEqual(d['boot_choice'], 'primary')

    def test_new_decoders_reject_bad_format_length_page_and_status_codes(self):
        cal = bytes([1, 1, 1, 1, 51])+calibration_record()
        checkpoint = checkpoint_payload()
        for decoder, good, mutations in (
            (self.c.parse_calibration, cal, ((0, 2), (1, 3), (2, 3), (3, 2))),
            (self.c.parse_checkpoint_energy, checkpoint, ((0, 2), (1, 3), (2, 3), (3, 3), (4, 4), (5, 3))),
        ):
            for bad in (good[:-1], good+b'\0'):
                with self.assertRaises(ValueError):
                    decoder(bad)
            for index, value in mutations:
                raw = bytearray(good)
                raw[index] = value
                with self.subTest(decoder=decoder.__name__, index=index), self.assertRaises(ValueError):
                    decoder(bytes(raw))

    def test_read_reply_ignores_foreign_and_returns_one_history_frame(self):
        sent = self.c.request('history-next', 11)
        foreign = self.c.frame(0, '', 0)
        good = self.c.frame(0, '', 11)
        chunks = iter([sent+foreign+good])
        raw, result = self.c.read_reply(lambda wait: next(chunks, b''), sent, 0.2)
        self.assertEqual((raw, result), (good, (0, b'')))

    def test_erased_records_are_visible_and_not_decoded_as_expected_fields(self):
        d = self.c.parse_calibration(bytes([1, 2, 0, 0, 255])+b'\xff'*53)
        self.assertEqual(d['classification'], 'erased')
        self.assertFalse(d['native_crc_accepted'])
        self.assertIsNone(d['fields'])
        raw = bytearray(checkpoint_payload())
        raw[1:6] = bytes(5)
        raw[24:] = b'\xff'*44
        d = self.c.parse_checkpoint_energy(bytes(raw))
        self.assertEqual(d['boot_choice'], 'fallback')
        for name in ('primary', 'backup'):
            self.assertEqual(d[name]['classification'], 'erased')
            self.assertFalse(d[name]['native_crc_accepted'])
            self.assertIsNone(d[name]['fields'])
            self.assertEqual(d[name]['raw_hex'], 'ff'*22)

    def test_active_calibration_rejects_wrong_size_flags_and_cell_count(self):
        good = bytes([1, 0, 0, 16])+bytes(68)
        for bad in (good[:-1], good+b'\0', good[:2]+bytes([32, 16])+good[4:],
                    good[:3]+bytes([17])+good[4:]):
            with self.assertRaises(ValueError):
                self.c.parse_calibration(bad)

    def test_new_response_transport_rejects_bad_length_header_and_address(self):
        info = checkpoint_payload().hex()
        good = self.c.frame(0, info, 11)
        self.assertEqual(self.c.parse_response(good, 11), (0, checkpoint_payload()))
        for bad in (good[:-1], good[:1]+b'21'+good[3:], good[:9]+b'F'+good[10:]):
            with self.assertRaises(ValueError):
                self.c.parse_response(bad, 11)
        with self.assertRaises(ValueError):
            self.c.parse_response(good, 12)

    def test_cli_read_sends_exactly_one_request_without_write_or_status_poll(self):
        for action, info in (('history-next', b''),
                             ('calibration-primary', bytes([1, 1, 1, 1, 51])+calibration_record()),
                             ('checkpoint-energy', checkpoint_payload())):
            sent = self.c.request(action, 11)
            response = self.c.frame(0, info.hex(), 11)
            with patch.object(sys, 'argv', ['maintenance_client.py', action, '--address', '11',
                                           '--tcp', 'localhost:8899']), \
                 redirect_stdout(io.StringIO()), patch.object(self.c, 'exchange_serial') as serial, \
                 patch.object(self.c, 'exchange_tcp', return_value=(response, (0, info))) as tcp:
                self.c.main()
            serial.assert_not_called()
            tcp.assert_called_once_with('localhost:8899', sent, 3)

    def test_cli_new_reads_are_offline_unless_transport_is_selected(self):
        for action in ('history-oldest', 'history-next', 'calibration-active',
                       'calibration-primary', 'calibration-backup', 'checkpoint-energy'):
            out = io.StringIO()
            with patch.object(sys, 'argv', ['maintenance_client.py', action, '--address', '11']), \
                 redirect_stdout(out), patch.object(self.c, 'exchange_serial') as serial, \
                 patch.object(self.c, 'exchange_tcp') as tcp:
                self.c.main()
            self.assertIn('nothing sent', out.getvalue())
            serial.assert_not_called()
            tcp.assert_not_called()


if __name__ == '__main__':
    unittest.main()

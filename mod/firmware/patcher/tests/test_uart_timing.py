"""UART1 synthetic-time contracts and native receiver/parser counterexamples.

> Port notation: UART0 = RS485-1/RS485-2 (shared pack bus); UART1 = RS485
> pair in the CAN socket; UART2 = local display/Bluetooth port. UART1 carries
> RS485 traffic; the actual CAN interface uses separate pins in the same socket.
"""
from pathlib import Path
from fractions import Fraction
import copy
import importlib.util
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import ORIGINALS, fixture
from seplos.image import Image
from seplos.build import build


class UARTTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Image.read(next(ORIGINALS.glob('*16.06.13*ehex')))
        cls.facts = copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
        cls.image, cls.report = build(cls.original, cls.facts, 13, ext_version='1.5.4')

    def timing(self):
        self.assertIsNotNone(importlib.util.find_spec('seplos.uart_timing_tests'),
                             'permanent UART timing validator is missing')
        from seplos import uart_timing_tests
        return uart_timing_tests

    def test_native_contract_mandatory_for_both_profiles(self):
        timing = self.timing()
        for version in ('1.5.4', '1.6.4'):
            with self.subTest(version=version):
                facts = copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
                image, report = build(self.original, facts, 13, ext_version=version)
                rows = timing.validate_uart_timing(self.original, image, facts, report)
                self.assertEqual(tuple(r['name'] for r in rows), timing.REQUIRED)
                self.assertTrue(all(r['passed'] for r in rows))
                self.assertGreaterEqual(len(rows), 8)

    def test_exact_integer_divider_time_and_nonempty_fifo(self):
        timing = self.timing()
        m = timing.TimingMachine(self.image, self.facts)
        self.assertEqual(m.baud, Fraction(125000, 13))
        self.assertEqual(m.timeout_ticks, 4_992_000)
        self.assertEqual(m.timeout_seconds, Fraction(13, 125))
        m.advance(10 * m.timeout_ticks)
        self.assertFalse(m.timeout)
        self.assertEqual(m.rx_irqs, [])

    def test_depth_eight_rejects_ninth_without_silent_truncation(self):
        timing = self.timing()
        m = timing.TimingMachine(self.image, self.facts)
        for value in range(8):
            m.arrive(value, service=False)
        with self.assertRaisesRegex(AssertionError, 'FIFO overflow'):
            m.arrive(8, service=False)
        self.assertEqual(bytes(m.queue), bytes(range(8)))

    def test_RXTOIF_is_threshold_or_enabled_timeout_not_nonempty(self):
        timing = self.timing()
        from seplos.machine import UART
        for mode in ('gt', 'ge'):
            with self.subTest(mode=mode):
                m = timing.TimingMachine(self.image, self.facts, threshold_mode=mode)
                m.arrive(0x7e, service=False)
                # Invoke the memory hook explicitly, then observe its register.
                m._read(m.uc, 0, UART+8, 4, 0, None)
                self.assertEqual(m.num(UART+8, 4) & (1 << 16), 0)
                m._read(m.uc, 0, UART+12, 4, 0, None)
                self.assertEqual(m.num(UART+12, 4) & 255, 1)
                self.assertEqual((m.num(UART+12, 4) >> 16) & 7, 6)
                m._read(m.uc, 0, UART+4, 4, 0, None)
                self.assertEqual(m.num(UART+4, 4) & (1 << 3), 1 << 3)
                m.advance(m.timeout_ticks, service=False)
                m._read(m.uc, 0, UART+8, 4, 0, None)
                self.assertEqual(m.num(UART+8, 4) & ((1 << 21) | (1 << 16)), (1 << 21) | (1 << 16))
                m.put(UART+4, (m.num(UART+4, 4) & ~(1 << 14)).to_bytes(4, 'little'))
                m._read(m.uc, 0, UART+8, 4, 0, None)
                self.assertEqual(m.num(UART+8, 4) & (1 << 16), 0)
                count = 7 if mode == 'gt' else 6
                for _ in range(count - 1):
                    m.arrive(0x32, service=False)
                m._read(m.uc, 0, UART+8, 4, 0, None)
                self.assertEqual(m.num(UART+8, 4) & ((1 << 22) | (1 << 19) | (1 << 16)), (1 << 22) | (1 << 19) | (1 << 16))
                self.assertEqual(m.num(UART+8, 4) & 0x3fff, 311)
                m.put(UART+4, (m.num(UART+4, 4) & ~(1 << 4)).to_bytes(4, 'little'))
                m._read(m.uc, 0, UART+8, 4, 0, None)
                self.assertEqual(m.num(UART+8, 4) & ((1 << 22) | (1 << 16)), 0)
                self.assertEqual(m.num(UART+8, 4) & (1 << 19), 1 << 19)

    def test_mutated_actual_timeout_fails_intended_config_contract(self):
        timing = self.timing()
        self.assert_timeout_or_divider_mutant(timing, 'timeout')

    def test_mutated_actual_divider_fails_intended_config_contract(self):
        timing = self.timing()
        self.assert_timeout_or_divider_mutant(timing, 'divider')

    def assert_timeout_or_divider_mutant(self, timing, field):
        mutant = timing.configuration_mutant(self.image, self.facts, field)
        self.assertNotEqual(mutant.app, self.image.app)
        with self.assertRaisesRegex(AssertionError, 'uart-timing-native-config:.*' + field):
            timing.validate_uart_timing(self.original, mutant, self.facts, self.report)


if __name__ == '__main__':
    unittest.main()

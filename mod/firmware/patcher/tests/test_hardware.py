"""Source-derived native peripheral contracts and targeted binary counterexamples."""
from pathlib import Path
import copy
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import ORIGINALS, fixture
from seplos.image import Image
from seplos.build import build
from seplos.thumb import Code


class Hardware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Image.read(next(ORIGINALS.glob('*16.06.13*ehex')))
        cls.facts = copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
        cls.image, cls.report = build(cls.original, cls.facts, 13, ext_version='1.5.4')

    def test_native_contract_is_mandatory_and_executes(self):
        from seplos import hardware_tests as hw
        checks = hw.validate_hardware(self.original, self.image, self.facts, self.report)
        self.assertEqual(tuple(c['name'] for c in checks), hw.REQUIRED)
        self.assertTrue(all(c['passed'] for c in checks))
        self.assertGreaterEqual(len(checks), 18)

    def test_full_profile_native_initialization(self):
        from seplos.hardware_tests import validate_hardware, REQUIRED
        facts = copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
        image, report = build(self.original, facts, 13, ext_version='1.6.4')
        self.assertEqual(len(validate_hardware(self.original, image, facts, report)), len(REQUIRED))

    def test_missing_flexible_baud_enable_is_detected(self):
        from seplos.hardware_tests import discover_hardware, validate_hardware
        roles = discover_hardware(self.original, self.facts)
        code = Code(self.original.app)
        calls = [{i.target for i in code.body(roles['uart_init'][n]) if i.op == 'bl'}
                 for n in range(3)]
        candidates = []
        for target in set.intersection(*calls):
            body = code.body(target)
            for prev, ins, after in zip(body, body[1:], body[2:]):
                if ((prev.op, prev.args) == ('ldr', 'r0, [r4, #0x4]')
                        and (ins.op, ins.args) == ('orrs', 'r0, r3')
                        and (after.op, after.args) == ('str', 'r0, [r4, #0x4]')):
                    candidates.append(ins)
        self.assertEqual(len(candidates), 1)
        app = bytearray(self.image.app)
        app[candidates[0].at:candidates[0].at+2] = b'\x00\xbf'
        with self.assertRaisesRegex(AssertionError, 'hardware UART0 flexible baud enabled'):
            validate_hardware(self.original, self.image.with_app(app), self.facts, self.report)
        from seplos.uart_timing_tests import validate_uart_timing
        with self.assertRaisesRegex(AssertionError, 'uart-timing-native-config'):
            validate_uart_timing(self.original, self.image.with_app(app), self.facts, self.report)

    def test_native_parity_mutation_is_detected(self):
        from seplos.hardware_tests import discover_hardware, validate_hardware
        roles = discover_hardware(self.original, self.facts)
        code = Code(self.original.app)
        calls = [{i.target for i in code.body(roles['uart_init'][n]) if i.op == 'bl'}
                 for n in range(3)]
        loads = [i for target in set.intersection(*calls) for i in code.body(target)
                 if (i.op, i.args) == ('ldrb', 'r1, [r5, #0x5]')]
        self.assertEqual(len(loads), 1)
        app = bytearray(self.image.app)
        app[loads[0].at:loads[0].at+2] = b'\x01\x21'  # MOVS r1,#1: enable parity
        with self.assertRaisesRegex(AssertionError, 'hardware UART0 framing 8N1'):
            validate_hardware(self.original, self.image.with_app(app), self.facts, self.report)
        from seplos.uart_timing_tests import validate_uart_timing
        with self.assertRaisesRegex(AssertionError, 'uart-timing-native-config'):
            validate_uart_timing(self.original, self.image.with_app(app), self.facts, self.report)

    def test_meaningful_mutations_reach_intended_register_assertions(self):
        from seplos.hardware_tests import discover_hardware, validate_hardware
        roles = discover_hardware(self.original, self.facts)
        code = Code(self.original.app)
        uart_timeout = [i for i in code.body(roles['uart_init'][1])
                        if i.op == 'movs' and i.args == 'r2, #0x64']
        self.assertEqual(len(uart_timeout), 1)
        irq_call = [i for i in code.body(roles['uart_init'][1])
                    if i.op == 'bl' and i.target == roles['irq_route']]
        self.assertEqual(len(irq_call), 1)
        irq_source = code.ins[irq_call[0].at-2]
        self.assertEqual((irq_source.op, irq_source.args), ('movs', 'r0, #0x59'))
        start, end = roles['watchdog_window']
        load_shift = [i for i in code.ins.values() if start <= i.at < end
                      and i.op == 'lsls' and i.args == 'r1, r0, #0x3']
        self.assertEqual(len(load_shift), 1)
        changes = [
            ('UART1 timeout', uart_timeout[0].at, bytes((99, uart_timeout[0].raw[1])),
             'hardware UART1 timeout register'),
            ('watchdog LOAD', load_shift[0].at,
             (int.from_bytes(load_shift[0].raw, 'little') ^ (1 << 6)).to_bytes(2, 'little'),
             'hardware watchdog LOAD register'),
            ('IRQ4 route', irq_source.at, bytes((0x58, irq_source.raw[1])),
             'hardware IRQ4 route register'),
        ]
        for label, at, replacement, expected in changes:
            with self.subTest(label=label):
                app = bytearray(self.image.app)
                app[at:at+len(replacement)] = replacement
                mutated = self.image.with_app(app)
                self.assertNotEqual(mutated.app, self.image.app)
                with self.assertRaisesRegex(AssertionError, expected):
                    validate_hardware(self.original, mutated, self.facts, self.report)


if __name__ == '__main__':
    unittest.main()

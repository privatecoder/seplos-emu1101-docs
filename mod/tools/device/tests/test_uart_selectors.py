"""Canonical UART selectors preserve addressing, permissions and physical baud."""
import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'maintenance_client.py'
spec = importlib.util.spec_from_file_location('uart_selector_client', SOURCE)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class UartSelectorTests(unittest.TestCase):
    def test_canonical_selectors_emit_identical_addressed_frames(self):
        for canonical, legacy in (('UART0', 'R'), ('UART1', 'C')):
            for address in (0, 1, 11, 21):
                for action in ('info', 'diagnostics'):
                    with self.subTest(uart=canonical, address=address, action=action):
                        self.assertEqual(client.request(action, address, canonical),
                                         client.request(action, address, legacy))
        self.assertEqual(client.request('info', 11, 'UART0'), b'~200B4664E00203FD1E\r')

    def test_canonical_ports_keep_their_distinct_service_gates(self):
        with self.assertRaisesRegex(ValueError, 'UART1'):
            client.request('start', 0, 'UART0')
        for action in ('status', 'stop', 'start'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                client.request(action, 1, 'UART1')
        self.assertEqual(client.request('stop', 11, 'UART0'), client.request('stop', 11, 'R'))
        self.assertEqual(client.request('start', 0, 'UART1'), client.request('start', 0, 'C'))
        for unsupported in ('UART2', 'UART3', 'uart0', ''):
            with self.subTest(uart=unsupported), self.assertRaises(ValueError):
                client.request('info', 0, unsupported)

    def test_cli_canonical_selection_uses_correct_baud_and_one_request(self):
        payload = b'MNT\4\x10\6\x0d\1\5\3' + bytes(8) + b'\x3a'
        raw = client.frame(0, payload.hex(), 11)
        for uart, baud in (('UART0', 19200), ('UART1', 9600)):
            with self.subTest(uart=uart), patch.object(sys, 'argv', [str(SOURCE), 'info', '--uart', uart, '--address', '11', '--serial', 'synthetic']), redirect_stdout(io.StringIO()), patch.object(client, 'exchange_serial', return_value=(raw, (0, payload))) as exchange:
                client.main()
                exchange.assert_called_once()
                self.assertEqual(exchange.call_args.args[1], b'~200B4664E00203FD1E\r')
                self.assertEqual(exchange.call_args.kwargs.get('baud', 9600), baud)

    def test_cli_rejects_local_display_without_transport(self):
        with patch.object(sys, 'argv', [str(SOURCE), 'info', '--uart', 'UART2']), redirect_stderr(io.StringIO()), patch.object(client, 'exchange_serial') as serial, self.assertRaises(SystemExit) as outcome:
            client.main()
        self.assertEqual(outcome.exception.code, 2)
        serial.assert_not_called()


if __name__ == '__main__':
    unittest.main()

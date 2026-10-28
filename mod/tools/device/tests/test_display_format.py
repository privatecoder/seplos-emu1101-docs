"""Offline parameter-write safeguards; no serial devices are opened."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch


class DisplayFormatTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).resolve().parents[1]/'display_format.py'
        self.assertTrue(path.is_file(),'display format client not implemented')
        spec=importlib.util.spec_from_file_location('display_format_test',path)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

    def config(self):
        words=list(range(60));words[58]=28000
        return dict(format='seplos-uart1-parameters-v1',pack_address=7,
                    parameters_u16=words,parameters_u8=list(range(27)),
                    function_switches=[255,223,255,63,191,159,191,31],
                    device_name_hex=b'SYNTHETIC0'.hex())

    def telemetry(self,capacity=28000):
        raw=bytearray(75);raw[1]=7;raw[2]=16;raw[55:57]=capacity.to_bytes(2,'big');return bytes(raw)

    def test_default_backup_uses_private_devices_area_before_any_write(self):
        m=self.module()
        import sys
        serial=MagicMock()
        result=dict(format='kurz',after_group7=15,lcd_enabled=True,changed=False)
        with patch.dict(sys.modules,{'serial':serial}),patch.object(m,'set_format',return_value=result) as apply,patch('builtins.print'):
            self.assertEqual(m.main(['7','kurz','--port','synthetic-no-device']),0)
        self.assertEqual(apply.call_args.args[3],LOCAL_ROOT/'devices/backups/parameters')
        self.assertEqual(apply.call_count,1)

    def test_only_format_bit_changes_and_backup_precedes_single_write(self):
        m=self.module();before=self.config();after=copy.deepcopy(before);after['function_switches'][7]=15
        with tempfile.TemporaryDirectory() as tmp:
            def write(*args):
                backups=list(Path(tmp).glob('*.json'));self.assertEqual(len(backups),1)
                self.assertEqual(json.loads(backups[0].read_text())['parameters'],before)
                self.assertEqual(args[2],after)
            with patch.object(m,'read_config',side_effect=[before,before,after]),patch.object(m,'read_telemetry',return_value=self.telemetry()),patch.object(m,'write_config',side_effect=write) as send:
                result=m.set_format(Mock(),7,'kurz',Path(tmp))
            self.assertTrue(result['changed']);self.assertEqual(send.call_count,1)
            self.assertEqual(before['function_switches'][7],31)

    def test_already_correct_does_not_write(self):
        m=self.module()
        with patch.object(m,'read_config',return_value=self.config()),patch.object(m,'read_telemetry') as telemetry,patch.object(m,'write_config') as send:
            result=m.set_format(Mock(),7,'erweitert',Path('/must-not-be-created'))
        self.assertFalse(result['changed']);send.assert_not_called();telemetry.assert_not_called()

    def test_capacity_side_effect_is_blocked(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'read_config',return_value=self.config()),patch.object(m,'read_telemetry',return_value=self.telemetry(27000)),patch.object(m,'write_config') as send:
            with self.assertRaisesRegex(ValueError,'Capacity'):m.set_format(Mock(),7,'kurz',Path(tmp))
            send.assert_not_called()

    def test_concurrent_parameter_change_is_not_overwritten(self):
        m=self.module();changed=self.config();changed['parameters_u16'][0]+=1
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'read_config',side_effect=[self.config(),changed]),patch.object(m,'read_telemetry',return_value=self.telemetry()),patch.object(m,'write_config') as send:
            with self.assertRaisesRegex(RuntimeError,'concurrently'):m.set_format(Mock(),7,'kurz',Path(tmp))
            send.assert_not_called()

    def test_unconfirmed_write_is_never_replayed(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'read_config',side_effect=[self.config(),self.config()]),patch.object(m,'read_telemetry',return_value=self.telemetry()),patch.object(m,'write_config',side_effect=TimeoutError('lost ACK')) as send:
            with self.assertRaisesRegex(RuntimeError,'unknown'):m.set_format(Mock(),7,'kurz',Path(tmp))
            self.assertEqual(send.call_count,1)

    def test_foreign_or_malformed_telemetry_cannot_pass_guard(self):
        m=self.module()
        for raw in (self.telemetry()[:-1],bytes([0,8])+self.telemetry()[2:]):
            with self.subTest(raw=raw.hex()),self.assertRaises(ValueError):m.capacity_guard(raw,self.config(),7)

    def test_broadcast_rejected_before_io(self):
        m=self.module()
        with patch.object(m,'read_config') as read:
            with self.assertRaises(ValueError):m.set_format(Mock(),255,'kurz',Path('/unused'))
            read.assert_not_called()

    def test_uart0_a1_contains_own_address_full_parameters_and_name(self):
        m=self.module();config=self.config()
        with patch.object(m,'exchange_ascii',return_value=b'') as send:
            m.write_config(Mock(),7,config,False)
        info=send.call_args.args[3]
        self.assertEqual(len(info),169);self.assertEqual(info[0],7)
        self.assertEqual(info[1:],m.client.encode_parameters(config,7)+bytes.fromhex(config['device_name_hex']))

    def test_uart1_uses_binary_a1_and_preserves_protected_bits(self):
        m=self.module();config=self.config();config['function_switches'][7]=15
        with patch.object(m.client,'exchange',return_value=b'') as send:
            m.write_config(Mock(),7,config,True)
        args=send.call_args.args
        self.assertEqual(args[1:3],(7,0xA1));self.assertEqual(len(args[3]),158)
        self.assertEqual(args[3][150],255)
        self.assertEqual(args[3][157],15)

    def test_enabling_extended_format_does_not_enable_disabled_lcd(self):
        m=self.module();before=self.config();before['function_switches'][7]=7
        after=copy.deepcopy(before);after['function_switches'][7]=23
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'read_config',side_effect=[before,before,after]),patch.object(m,'read_telemetry',return_value=self.telemetry()),patch.object(m,'write_config'):
            result=m.set_format(Mock(),7,'erweitert',Path(tmp))
        self.assertFalse(result['lcd_enabled']);self.assertEqual(result['after_group7'],23)

    def test_readback_mismatch_is_reported_without_restore_write(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'read_config',side_effect=[self.config()]*3),patch.object(m,'read_telemetry',return_value=self.telemetry()),patch.object(m,'write_config') as send:
            with self.assertRaisesRegex(RuntimeError,'Readback differs'):m.set_format(Mock(),7,'kurz',Path(tmp))
            self.assertEqual(send.call_count,1)


if __name__=='__main__':unittest.main()

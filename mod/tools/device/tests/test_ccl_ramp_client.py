"""Offline Full1.6.7 CCL configuration wire contract."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('ccl_client',Path(__file__).resolve().parents[1]/'maintenance_client.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class CCLClient(unittest.TestCase):
 def test_addressed_reads_and_writes(self):
  for uart in ('UART0','UART1'):
   for address in (0,1,21):
    self.assertEqual(c.request('ccl-ramp',address,uart),c.frame(0x64,'07',address))
    for value in (1,10,20):
     self.assertEqual(c.request('set-ccl-ramp',address,uart,step=value),c.frame(0x64,'08%02X'%value,address))
 def test_invalid_values_are_refused_before_transport(self):
  for value in (None,0,21,-1,1.5,True,'10'):
   with self.assertRaises(ValueError):c.request('set-ccl-ramp',step=value)
  with self.assertRaises(ValueError):c.request('ccl-ramp',step=10)
 def test_reply_and_capability(self):
  self.assertEqual(c.parse_ccl_ramp(bytes([1,10,1,1,20]))['decrease_A_per_online_pack_per_update'],10)
  for payload in (bytes([1,0,1,1,20]),bytes([2,10,1,1,20]),bytes([1,10,2,1,20]),bytes([1,10,1,1,20,0])):
   with self.assertRaises(ValueError):c.parse_ccl_ramp(payload)
  data=b'EXT\5\x10\6\x0d\1\6\7'+bytes(8)+b'\xfe\0\x1f'
  self.assertTrue(c.parse_info(data)['configurable_ccl_decrease'])
if __name__=='__main__':unittest.main()

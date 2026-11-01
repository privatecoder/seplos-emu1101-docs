"""New remote read wire contracts exercised through actual Thumb dispatchers."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS,fixture
from seplos.image import Image
from seplos.build import build
from seplos.machine import Machine,ascii_frame
from seplos.selftest import ascii_payload
from seplos.marker_uart0_tests import uart0_exchange

class RemoteDiagnostics(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  cls.facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  cls.image,cls.report=build(cls.original,cls.facts,13,maint_version='1.5.4')
 def query(self,command,info,port='C'):
  m=Machine(self.image,self.facts);m.defaults(1);m.put(m.r['group0'],b'\0')
  packet=ascii_frame(1,command,info)
  raw=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
  return ascii_payload(raw,1) if raw else None
 def test_mandatory_feature_suite_both_profiles(self):
  from seplos.remote_diagnostics_tests import validate_remote,REQUIRED
  for profile in ('1.5.4','1.6.4'):
   with self.subTest(profile=profile):
    facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
    image,report=build(self.original,facts,13,maint_version=profile)
    rows=validate_remote(self.original,image,facts,report)
    self.assertEqual({r['name'] for r in rows},set(REQUIRED))
    self.assertTrue(all(r['passed'] for r in rows))
 def test_history_parseable_wrong_length_replies_05(self):
  for length in (0,1,3,6,30):
   with self.subTest(length=length):self.assertEqual(self.query(0x4b,b'\0'*length),(5,b''))
 def test_history_empty_ring_uart1(self):
  self.assertEqual(self.query(0x4b,b'\0\0'),(0,b''))
 def test_active_calibration_both_ports(self):
  for port in ('R','C'):
   with self.subTest(port=port):
    result=self.query(0x64,b'\5',port)
    self.assertIsNotNone(result);self.assertEqual(result[0],0)
    self.assertEqual((len(result[1]),result[1][:2]),(72,b'\1\0'))
 def test_checkpoint_energy_both_ports(self):
  for port in ('R','C'):
   with self.subTest(port=port):
    result=self.query(0x64,b'\6',port)
    self.assertIsNotNone(result);self.assertEqual(result[0],0)
    self.assertEqual((len(result[1]),result[1][0]),(68,1))
 def test_MNT05_remote_capabilities(self):
  result=self.query(0x64,b'\3')
  self.assertEqual((len(result[1]),result[1][:4],result[1][19:]),(21,b'MNT\5',b'\0\x0f'))

if __name__=='__main__':unittest.main()

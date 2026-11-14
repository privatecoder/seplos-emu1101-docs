"""Full-only configurable CCL decrease, actual Thumb and protocol regressions."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS,fixture
from seplos.image import Image
from seplos.build import build
from seplos.machine import Machine,ascii_frame
from seplos.selftest import ascii_payload

class ConfigurableCCL(unittest.TestCase):
 def test_full_profile_supports_persistent_step(self):
  from seplos.profiles import SUPPORTED_VERSIONS
  self.assertIn('1.6.7',SUPPORTED_VERSIONS)
  original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  image,report=build(original,facts,13,ext_version='1.6.7')
  m=Machine(image,facts);m.defaults(0)
  self.assertEqual(ascii_payload(m.transact(ascii_frame(0,0x64,b'\x07'),True)),(0,b'\x01\x01\x01\x01\x14'))
  self.assertEqual(ascii_payload(m.transact(ascii_frame(0,0x64,b'\x08\x0a'),True)),(0,b'\x01\x0a\x01\x01\x14'))
  m.put(facts['cutoff']['ram']+3,b'\0');m.run(report['entries']['hook_cut_loader'])
  self.assertEqual(m.num(facts['cutoff']['ram']+3),10)

 def test_mandatory_native_cases(self):
  from seplos.ccl_ramp_tests import validate_ccl_ramp,REQUIRED
  original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  image,report=build(original,facts,13,ext_version='1.6.7')
  rows=validate_ccl_ramp(original,image,facts,report)
  self.assertEqual({x['name'] for x in rows},set(REQUIRED))

if __name__=='__main__':unittest.main()

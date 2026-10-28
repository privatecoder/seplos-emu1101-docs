"""Persistent pack lock using native parameter and output-gate paths."""
from pathlib import Path
import inspect,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine,ascii_frame
from seplos.build import build
from seplos.selftest import ascii_payload


class PackLock(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')))
  cls.facts=probe(cls.original,discover(cls.original))
  cls.image,cls.report=build(cls.original,cls.facts,base_revision=13,maint_version='1.6.3')
 def test_version_and_capability(self):
  m=Machine(self.image,self.facts);m.defaults(1)
  rtn,raw=ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1)
  self.assertEqual((rtn,raw[:4],raw[7:9],raw[18]),(0,b'MNT\4',b'\1\6',254))
 def test_addressed_off_requires_a_persistent_write(self):
  m=Machine(self.image,self.facts);m.defaults(1)
  m.put(m.r['group0'],bytes([m.num(m.r['group0'])|0x18]))
  self.assertEqual(ascii_payload(m.transact(ascii_frame(1,0x45,b'\0\4\x1f'),True),1),(0,b''))
  self.assertTrue(m.saves,'1.6 Aus must persist; OEM/1.5 only changes RAM')
 def test_mandatory_cutoff_contract(self):
  from seplos.cutoff_tests import validate_cutoff
  checks=validate_cutoff(self.original,self.image,self.facts,self.report)
  self.assertGreaterEqual(len(checks),30)
  self.assertTrue(all(c['passed'] for c in checks))


if __name__=='__main__':unittest.main()

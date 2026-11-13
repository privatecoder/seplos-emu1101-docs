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
  cls.image,cls.report=build(cls.original,cls.facts,base_revision=13,ext_version='1.6.4')
 def test_version_and_capability(self):
  m=Machine(self.image,self.facts);m.defaults(1)
  rtn,raw=ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1)
  self.assertEqual((rtn,raw[:4],raw[7:9],raw[18]),(0,b'EXT\5',b'\1\6',254))
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

 def test_fast_current_handover_and_persistent_off_boundaries(self):
  from seplos.cutoff_tests import validate_fast_handover,FAST_REQUIRED
  rows=validate_fast_handover(self.original,self.image,self.facts,self.report)
  self.assertEqual({r['name'] for r in rows},set(FAST_REQUIRED))
  self.assertTrue(all(r['passed'] for r in rows))

 def test_fast_current_threshold_mutation_is_detected_at_handover(self):
  import re
  from seplos.cutoff_tests import validate_fast_handover
  from seplos.thumb import Code
  code=Code(self.original.app);candidates=[]
  for ins in code.body(self.facts['cutoff']['fast']):
   m=re.fullmatch(r'(r\d+), #(0x[0-9a-f]+|\d+)',ins.args)
   following=code.ins.get(ins.at+ins.size)
   if ins.op!='movs' or not m or not following or following.op!='lsls':continue
   shift=re.fullmatch(rf'{m[1]}, {m[1]}, #(0x[0-9a-f]+|\d+)',following.args)
   if shift and int(m[2],0)<<int(shift[1],0)==1000:candidates.append(ins)
  self.assertEqual(len(candidates),1,'source-bound current threshold construction')
  ins=candidates[0];data=bytearray(self.image.app)
  instruction=int.from_bytes(ins.raw,'little')
  data[ins.at:ins.at+2]=((instruction&0xff00)|((instruction+1)&255)).to_bytes(2,'little')
  with self.assertRaisesRegex(AssertionError,'cutoff-fast-current-signed-threshold'):
   validate_fast_handover(self.original,self.image.with_app(data),self.facts,self.report)


if __name__=='__main__':unittest.main()

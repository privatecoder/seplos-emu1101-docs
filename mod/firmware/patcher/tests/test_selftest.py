from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture

class Contract(unittest.TestCase):
 def test_mandatory_tests_exist(self):self.assertTrue((ROOT/'seplos'/'selftest.py').exists(),'mandatory firmware tests missing')
 def test_suite_detects_permission_bypass(self):
  from seplos.image import Image
  from seplos.analysis import discover
  from seplos.machine import probe
  from seplos.build import build
  from seplos.selftest import validate
  im=Image.read(next((ORIGINALS).glob('*16.06.13*ehex')));facts=probe(im,discover(im));patched,buildreport=build(im,facts,maint_version='1.5.3')
  result=validate(im,patched,facts,buildreport)
  self.assertGreaterEqual(len(result),60)
  self.assertTrue(all(x['passed'] for x in result))
  # NOP the real write permission branch in the emitted appendix.
  from seplos.thumb import Code
  c=Code(patched.app);data=bytearray(patched.app)
  candidates=[]
  for a,i in c.ins.items():
   if a<len(im.app) or i.op!='lsls' or i.args!='r1, r0, #0x1f':continue
   candidates.append(a+2)
  self.assertEqual(len(candidates),1)
  branch=int.from_bytes(data[candidates[0]:candidates[0]+2],'little')
  data[candidates[0]:candidates[0]+2]=(0xe000|(branch&255)).to_bytes(2,'little')
  import hashlib
  offset=buildreport['build_id_offset'];data[offset:offset+8]=b'UPID0000'
  identifier=hashlib.sha256(data).digest()[:8];data[offset:offset+8]=identifier
  changed_report=dict(buildreport,build_id=identifier.hex())
  with self.assertRaisesRegex(AssertionError,'write-self-disable'):
   validate(im,patched.with_app(data),facts,changed_report)

if __name__=='__main__':unittest.main()

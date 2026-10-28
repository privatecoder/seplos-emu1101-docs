from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine,frame,ascii_frame

class Payload(unittest.TestCase):
 def test_builder_implemented(self):self.assertTrue((ROOT/'seplos'/'build.py').exists(),'parametric builder missing')
 def test_all_compatible_oem_maints(self):
  from seplos.build import build
  for path in sorted((ORIGINALS).glob('*16.06.*.ehex')):
   with self.subTest(image=path.name):
    original=Image.read(path);facts=probe(original,discover(original))
    patched,report=build(original,facts,maint_version='1.5.3')
    changed={a for a,(x,y) in enumerate(zip(original.app,patched.app)) if x!=y}
    allowed={a for site in report['hooks'].values() for a in range(site,site+4)}
    self.assertLessEqual(changed,allowed)
    self.assertTrue(changed)
    self.assertGreater(len(patched.app),len(original.app))
    m=Machine(patched,facts);m.defaults(1)
    response=m.transact(frame(1,0x47),True)
    self.assertEqual(response,frame(1,0x47,m.payload()+m.read(m.r['name'],10)))
    self.assertEqual(m.transact(frame(1,0xA1,m.payload()),True),frame(1,0xA1))
    self.assertEqual(m.transact(frame(1,0xA4),True),frame(1,0xA4,m.read(m.r['string2'],30)))
    self.assertEqual(m.transact(frame(0,0x47),True),b'')
    m.put(m.r['address'],b'\0')
    info=m.transact(ascii_frame(0,0x64,b'\x03'),True)
    self.assertTrue(info.startswith(b'~20004600'),info)
    data=bytes.fromhex(info[13:-5].decode())
    self.assertEqual(len(data),19)
    self.assertEqual(data[:4],b'MNT\x04')
    self.assertEqual(data[18],58|int('SP80' in path.name))
    self.assertEqual(data[6:10],b'\xff\x01\x05\x03')

if __name__=='__main__':unittest.main()

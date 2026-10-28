from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.analysis import discover

class HardStop(unittest.TestCase):
 def test_tool_exists(self):self.assertTrue((ROOT/'seplos'/'hardstop.py').exists(),'automatic Hard-Stop tool missing')
 def test_all_oem_find_patch_and_real_code(self):
  from seplos.hardstop import locate,apply,validate_hardstop
  for p in sorted((ORIGINALS).glob('*.ehex')):
   with self.subTest(image=p.name):
    im=Image.read(p);facts=discover(im);found=locate(im,facts);patched,detail=apply(im,facts)
    differences=[a for a,(x,y) in enumerate(zip(im.app,patched.app)) if x!=y]
    self.assertEqual(differences,[] if found['enabled'] else [found['offset']])
    tests=validate_hardstop(im,patched,facts,detail);self.assertGreaterEqual(len(tests),257)
    if '16.06.04' in p.name:
     special=(ORIGINALS/'CAN1101[V16.06.05_PN01_230916_SP80].ehex').read_bytes()
     self.assertEqual(patched.app,Image.parse(special.decode()).app)

if __name__=='__main__':unittest.main()

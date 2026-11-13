"""Atomic scheduler profiles extend the retained reference profile boundary."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS,fixture
from seplos.image import Image
from seplos.build import build

class AtomicProfiles(unittest.TestCase):
 def test_new_profiles_are_explicit_and_references_remain_available(self):
  from seplos.profiles import SUPPORTED_VERSIONS
  self.assertEqual(set(SUPPORTED_VERSIONS),{'1.5.4','1.6.4','1.5.5','1.6.5'})
 def test_both_fixed_profiles_have_guarded_cleanup_and_distinct_identity(self):
  original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  for version,count,ram in (('1.5.5',6,0),('1.6.5',22,4)):
   with self.subTest(version=version):
    facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
    image,report=build(original,facts,13,ext_version=version)
    self.assertEqual(report['patch_version'],version)
    self.assertEqual(len(report['hooks']),count)
    self.assertEqual(report['ram_bytes'],ram)
    self.assertTrue(report['scheduler_atomic']['enabled'])
    self.assertNotEqual(image.sha,original.sha)
    self.assertIn('hook_scheduler_atomic',report['entries'])

if __name__=='__main__':unittest.main()

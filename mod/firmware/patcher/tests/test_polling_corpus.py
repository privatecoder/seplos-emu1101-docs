"""New polling source support is narrower than retained reference profiles."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_corpus import expected_outcome

class PollingCorpus(unittest.TestCase):
 def test_older_sources_refuse_polling_without_changing_reference_profiles(self):
  for group in ('Original Firmware','Hard-Stop'):
   for revision in ('16.06.11','16.06.12'):
    for version in ('1.5.6','1.6.6'):
     self.assertEqual(expected_outcome(group,revision,version),('refused','polling start role'))
    for version in ('1.5.4','1.5.5','1.6.4','1.6.5'):
     self.assertEqual(expected_outcome(group,revision,version),('passed',None))
 def test_reviewed_sources_and_existing_refusals(self):
  for version in ('1.5.6','1.6.6'):
   for group in ('Original Firmware','Hard-Stop'):
    self.assertEqual(expected_outcome(group,'16.06.13',version),('passed',None))
   self.assertEqual(expected_outcome('Maintenance-Patch','16.06.13',version),('refused',None))
   self.assertEqual(expected_outcome('Original Firmware','16.04.06',version),('refused','UART1 buffers too small'))
  self.assertEqual(expected_outcome('Original Firmware','16.06.03','1.5.6'),('refused','polling start role'))
  self.assertEqual(expected_outcome('Original Firmware','16.06.03','1.6.6'),('refused','unsupported EMU1101-EXT 1.6 gate ABI'))
if __name__=='__main__':unittest.main()

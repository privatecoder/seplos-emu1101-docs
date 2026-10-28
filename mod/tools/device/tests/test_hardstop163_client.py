"""No I/O: dynamic/default distinction and explicit two-bit parameter edit."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
from pathlib import Path
import importlib.util,unittest

class HardStopClient163(unittest.TestCase):
 def setUp(self):
  p=Path(__file__).resolve().parents[1]/'maintenance_client.py';s=importlib.util.spec_from_file_location('hs163_client',p)
  self.m=importlib.util.module_from_spec(s);s.loader.exec_module(self.m)
 def test_MNT04_dynamic_is_not_current_state(self):
  for flags in (254,255):
   d=self.m.parse_info(b'MNT\4\x10\6\x0d\1\6\3'+bytes(8)+bytes([flags]))
   self.assertTrue(d.get('configurable_hard_stop'));self.assertIsNone(d['hard_stop'])
   self.assertEqual(d['hard_stop_default'],bool(flags&1))
 def test_effective_state_all_values(self):
  for default in (False,True):
   flags=254|int(default)
   for group in range(256):
    d=self.m.hard_stop_state(group,flags)
    self.assertEqual(d['enabled'],default if group&128 else bool(group&64))
    self.assertEqual(d['initialized'],not bool(group&128))
 def test_edit_only_two_bits(self):
  for group in range(256):
   for enabled in (False,True):
    out=self.m.hard_stop_group0(group,enabled)
    self.assertEqual(out&0x3f,group&0x3f);self.assertFalse(out&128)
    self.assertEqual(bool(out&64),enabled)
 def test_legacy_images_stay_static(self):
  for flags in (50,51,126,127):
   d=self.m.hard_stop_state(255,flags)
   self.assertFalse(d['configurable']);self.assertEqual(d['enabled'],bool(flags&1))
 def test_invalid_values_rejected(self):
  for value in (-1,256,True,'FF',None):
   with self.assertRaises(ValueError):self.m.hard_stop_state(value,254)
   with self.assertRaises(ValueError):self.m.hard_stop_group0(value,True)
  with self.assertRaises(ValueError):self.m.hard_stop_group0(255,1)

if __name__=='__main__':unittest.main()

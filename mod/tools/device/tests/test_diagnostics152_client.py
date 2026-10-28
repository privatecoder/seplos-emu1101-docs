"""1.5.2 INFO and unavailable lock/cache decoding, entirely offline."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
from pathlib import Path
import importlib.util,unittest

class DiagnosticsClient152(unittest.TestCase):
 def setUp(self):
  p=Path(__file__).resolve().parents[1]/'maintenance_client.py'
  s=importlib.util.spec_from_file_location('diag152_client',p);self.m=importlib.util.module_from_spec(s);s.loader.exec_module(self.m)
 def test_info_only_diagnostic_flag(self):
  d=self.m.parse_info(b'MNT\4\x10\6\x0d\1\5\2'+bytes(8)+b'\x32')
  self.assertEqual(d['patch_version'],'1.5.2');self.assertTrue(d['extended_diagnostics'])
  self.assertFalse(d['checkpoint_before_reset']);self.assertFalse(d['positive_flags'])
 def test_no_cache_is_unavailable_not_unlocked(self):
  d=self.m.parse_diagnostics(bytes([1,1,1,1,1,1,1,255,255,0]))
  self.assertIsNone(d['parameters']['primary_lock']);self.assertIsNone(d['parameters']['backup_lock'])
  self.assertIsNone(d['runtime_lock']);self.assertIsNone(d['runtime_consistent'])
  self.assertFalse(d['runtime_magic_valid'])

if __name__=='__main__':unittest.main()

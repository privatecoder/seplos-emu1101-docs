"""Offline service decoder and addressed requests; no serial I/O."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
from pathlib import Path
import importlib.util, unittest

class ServiceClient(unittest.TestCase):
 def setUp(self):
  p=Path(__file__).resolve().parents[1]/'maintenance_client.py'
  s=importlib.util.spec_from_file_location('service_client',p)
  self.c=importlib.util.module_from_spec(s);s.loader.exec_module(self.c)
 def test_capabilities(self):
  for flags in (30,126,127):
   raw=b'MNT\4\x10\6\x0d\1\6\2'+bytes(8)+bytes([flags])
   d=self.c.parse_info(raw)
   self.assertEqual(d.get('extended_diagnostics'),bool(flags&32))
   self.assertEqual(d.get('checkpoint_before_reset'),bool(flags&64))
 def test_addressed_diagnostics_R_C(self):
  for port in ('R','C'):
   for address in (0,1,11,21):
    self.assertEqual(self.c.request('diagnostics',address,port),self.c.frame(0x64,'04',address))
 def test_decode(self):
  d=self.c.parse_diagnostics(bytes([1,1,2,0,1,1,2,0,255,5]))
  self.assertEqual(d['parameters'],dict(primary='valid',backup='invalid',comparison='not-comparable',primary_lock=False,backup_lock=None))
  self.assertEqual(d['soc'],dict(primary='valid',backup='valid',comparison='different'))
  self.assertEqual(d['runtime_lock'],True);self.assertFalse(d['runtime_consistent']);self.assertTrue(d['runtime_magic_valid'])
 def test_reject_unknown_shape_and_codes(self):
  good=bytearray([1,1,1,1,1,1,1,0,0,6])
  for raw in (good[:-1],good+b'\0',bytes([2])+good[1:]):
   with self.assertRaises(ValueError):self.c.parse_diagnostics(raw)
  for pos,val in ((1,3),(3,3),(7,2),(9,8)):
   bad=bytearray(good);bad[pos]=val
   with self.assertRaises(ValueError):self.c.parse_diagnostics(bad)

if __name__=='__main__':unittest.main()

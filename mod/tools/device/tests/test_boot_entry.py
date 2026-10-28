"""Only modeled wire traffic; a reset is sent once, RFL may be probed again."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import importlib.util
from pathlib import Path
import unittest

class BootEntry(unittest.TestCase):
 def module(self):
  path=Path(__file__).resolve().parents[1]/'boot_entry.py'
  s=importlib.util.spec_from_file_location('entry',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
 def test_fragmented_ACK_does_not_trigger_extra_probe(self):
  m=self.module();ack=m.boot_frame(b'RFB',data=b'\1\0')
  class Port:
   def __init__(self):self.clock=0;self.sent=[];self.chunks=[b'',ack[:-3],ack[-3:]]
   def send(self,frame,discard_pending=True):self.sent.append(frame)
   def read_until(self,done,timeout):self.clock+=timeout;return self.chunks.pop(0)
  p=Port();self.assertEqual(m.enter(p,7,now=lambda:p.clock),ack)
  self.assertEqual(sum(x[4:7]==b'RFL' for x in p.sent),1)
 def test_write_ACK_rejects_RFB_or_bad_checksum(self):
  m=self.module()
  for raw in (m.boot_frame(b'RFB',data=b'\1\0'),m.boot_frame(b'WFB')[:-6]+b'\0\0'+b'\r'*4):
   with self.assertRaises(ValueError):m.validate_write_ack(raw)
  self.assertEqual(m.validate_write_ack(m.boot_frame(b'WFB')),None)
 def test_every_ACK_and_reset_error_split(self):
  m=self.module()
  class Port:
   def __init__(self,chunks):self.clock=0;self.sent=[];self.chunks=[b'',*chunks]
   def send(self,frame,discard_pending=True):self.sent.append(frame)
   def read_until(self,done,timeout):self.clock+=timeout;return self.chunks.pop(0) if self.chunks else b''
  ack=m.boot_frame(b'RFB',data=b'\1\0')
  for split in range(1,len(ack)):
   p=Port([ack[:split],ack[split:]])
   self.assertEqual(m.enter(p,7,now=lambda:p.clock),ack)
   self.assertEqual(sum(x[4:7]==b'RFL' for x in p.sent),1)
  p=Port([bytes([x]) for x in ack]);self.assertEqual(m.enter(p,7,now=lambda:p.clock),ack)
  self.assertEqual(sum(x[4:7]==b'RFL' for x in p.sent),1)
  error=m.ascii.frame(8,'',7)
  for split in range(1,len(error)):
   p=Port([error[:split],error[split:]])
   with self.assertRaisesRegex(RuntimeError,'RTN08'):m.enter(p,7,now=lambda:p.clock)
   self.assertEqual(sum(x.startswith(b'~') for x in p.sent),1)
 def test_delayed_boot_and_reset_error(self):
  path=Path(__file__).resolve().parents[1]/'boot_entry.py'
  self.assertTrue(path.exists(),'new boot-entry helper is missing')
  s=importlib.util.spec_from_file_location('entry',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
  class Port:
   def __init__(self,error=False):self.sent=[];self.clock=0;self.error=error
   def send(self,frame,discard_pending=True):self.sent.append(frame)
   def read_until(self,done,timeout):
    self.clock+=timeout
    if self.error:return m.ascii.frame(8,'',7)
    return m.boot_frame(b'RFB',data=b'\1\0') if self.clock>.4 else b''
  p=Port();m.enter(p,7,now=lambda:p.clock)
  self.assertEqual(sum(x.startswith(b'~') for x in p.sent),1)
  self.assertGreater(sum(x[4:7]==b'RFL' for x in p.sent),1)
  self.assertFalse(any(x[4:7]==b'WFE' for x in p.sent))
  p=Port(True)
  with self.assertRaisesRegex(RuntimeError,'RTN08'):m.enter(p,7,now=lambda:p.clock)
  self.assertEqual(len(p.sent),1)

if __name__=='__main__':unittest.main()

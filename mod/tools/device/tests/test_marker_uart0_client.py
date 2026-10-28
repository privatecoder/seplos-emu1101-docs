"""Offline MNT04 and explicit R transport contract; no device I/O."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
from pathlib import Path
import importlib.util,io,sys,unittest
from unittest.mock import patch
from contextlib import redirect_stdout,redirect_stderr

class MarkerClient(unittest.TestCase):
 def setUp(self):
  p=Path(__file__).resolve().parents[1]/'maintenance_client.py'
  spec=importlib.util.spec_from_file_location('new_marker_client',p);self.c=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.c)
 def test_mnt04_three_components_flags_and_id(self):
  for minor,flags in ((5,18),(6,30)):
   raw=b'MNT\4\x10\6\x0d'+bytes([1,minor,1])+bytes(range(8))+bytes([flags])
   try:info=self.c.parse_info(raw)
   except ValueError:info={}
   self.assertEqual(info.get('patch_version'),f'1.{minor}.1');self.assertEqual(info['info_format'],4)
   self.assertEqual(info['build_id'],'0001020304050607');self.assertEqual(info['image_flags'],flags)
   self.assertTrue(info['uart0_marker']);self.assertEqual(info['positive_flags'],minor==6)
 def test_R_supports_addressed_status_stop_info(self):
  for a in (0,1,11,21):
   for action in ('status','stop','info'):
    try:request=self.c.request(action,a,uart='R')
    except TypeError:request=None
    self.assertIsNotNone(request);self.assertTrue(request.startswith(f'~20{a:02X}4664'.encode()))
 def test_R_start_is_refused(self):
  with self.assertRaises(ValueError):self.c.request('start',0,uart='R')
 def test_C_status_and_stop_remain_master_only(self):
  for action in ('status','stop','start'):
   with self.assertRaises(ValueError):self.c.request(action,1)
 def test_cli_R_offline_uses_no_port(self):
  out=io.StringIO()
  with patch.object(sys,'argv',['maintenance_client.py','stop','--uart','R','--address','11']),redirect_stdout(out),redirect_stderr(io.StringIO()),patch.object(self.c,'exchange_serial') as serial:
   try:self.c.main()
   except SystemExit as exc:self.fail(f'R option not implemented: {exc}')
   self.assertIn('~200B4664A00600C35A',out.getvalue());serial.assert_not_called()
 def test_serial_R_uses_19200_8N1(self):
  attrs=[0,0,0,0,0,0,[0]*32]
  sent=self.c.request('info',11,uart='R')
  with patch.object(self.c.os,'open',return_value=42),patch.object(self.c.os,'close'),patch.object(self.c.os,'write'),patch.object(self.c.termios,'tcgetattr',return_value=attrs),patch.object(self.c.termios,'tcsetattr') as configure,patch.object(self.c.termios,'tcflush'),patch.object(self.c.termios,'tcdrain'),patch.object(self.c,'read_reply',return_value=(b'',(0,b''))):
   self.c.exchange_serial('synthetic',sent,baud=19200)
   configured=configure.call_args.args[2];self.assertEqual(configured[4:6],[self.c.termios.B19200]*2)
 def test_cli_R_info_passes_baud_and_prints_MNT04(self):
  info=b'MNT\4\x10\6\x0d\1\5\1'+bytes(8)+b'\x12'
  raw=self.c.frame(0,info.hex(),11);out=io.StringIO()
  with patch.object(sys,'argv',['maintenance_client.py','info','--uart','R','--address','11','--serial','synthetic']),redirect_stdout(out),patch.object(self.c,'exchange_serial',return_value=(raw,(0,info))) as exchange:
   self.c.main();self.assertEqual(exchange.call_args.kwargs['baud'],19200)
   self.assertIn('patch=1.5.1',out.getvalue());self.assertIn('info-format=4',out.getvalue())
 def test_R_stop_does_not_wait_for_master_DIP_transition(self):
  payload=b'\xff'*4+b'\0';raw=self.c.frame(0,payload.hex(),11)
  with patch.object(sys,'argv',['maintenance_client.py','stop','--uart','R','--address','11','--serial','synthetic']),redirect_stdout(io.StringIO()),patch.object(self.c,'exchange_serial',return_value=(raw,(0,payload))) as exchange,patch.object(self.c,'wait_for_state') as wait:
   self.c.main();exchange.assert_called_once();wait.assert_not_called()
 def test_unknown_info_format_length_rejected(self):
  for raw in (b'MNT\4'+bytes(14),b'MNT\4'+bytes(16),b'MNT\5'+bytes(15)):
   with self.assertRaises(ValueError):self.c.parse_info(raw)

if __name__=='__main__':unittest.main()

"""No I/O: targeted info frames, response filtering and master-only actions."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
from pathlib import Path
import importlib.util,io,sys,unittest
from unittest.mock import patch
from contextlib import redirect_stdout,redirect_stderr
P=Path(__file__).resolve().parents[1]/'maintenance_client.py'

class AddressedInfoClient(unittest.TestCase):
 def setUp(self):
  spec=importlib.util.spec_from_file_location('addressed_maint_client',P);self.c=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.c)
 def test_addressed_info_and_matching_reply(self):
  for address in (0,1,11,21):
   request=self.c.request('info',address=address)
   self.assertTrue(request.startswith(f'~20{address:02X}4664E00203'.encode()))
   info=b'MNT\x03\x10\x06\x0d\x01\x05'+bytes(8)+b'\0'
   response=self.c.frame(0,info.hex(),address=address)
   self.assertEqual(self.c.parse_response(response,address=address),(0,info))
   with self.assertRaises(ValueError):self.c.parse_response(response,address=(address+1)%22)
 def test_positive_control_capability_is_decoded_without_changing_raw_flags(self):
  for flags in (6,7,14,15,142):
   raw=b'MNT\3\x10\x06\x0d\x01\x06'+bytes(8)+bytes([flags])
   parsed=self.c.parse_info(raw)
   self.assertEqual(parsed.get('positive_flags',False),bool(flags&8))
   self.assertEqual(parsed['image_flags'],flags)
   self.assertEqual(parsed['hard_stop'],bool(flags&1))
 def test_foreign_reply_ignored_for_addressed_request(self):
  sent=self.c.request('info',address=11);good=self.c.frame(0,'01',address=11);foreign=self.c.frame(0,'02',address=0)
  chunks=iter([sent+foreign+good]);raw,result=self.c.read_reply(lambda wait:next(chunks,b''),sent,0.2)
  self.assertEqual(raw,good);self.assertEqual(result,(0,b'\x01'))
 def test_invalid_targets_or_slave_actions_rejected_offline(self):
  for action,address in [('info',-1),('info',22),('info',255),('start',1),('stop',11),('status',21)]:
   with self.subTest(action=action,address=address),self.assertRaises(ValueError):self.c.request(action,address=address)
 def test_cli_info_target_and_forbidden_slave_action(self):
  for action,address,allowed in [('info',11,True),('status',1,False),('start',1,False),('stop',1,False)]:
   out=io.StringIO()
   with patch.object(sys,'argv',['maintenance_client.py',action,'--address',str(address)]),redirect_stdout(out),redirect_stderr(io.StringIO()),patch.object(self.c,'exchange_serial') as serial,patch.object(self.c,'exchange_tcp') as tcp:
    if allowed:
     self.c.main();self.assertIn('~200B4664E00203',out.getvalue())
    else:
     with self.assertRaises(SystemExit):self.c.main()
    serial.assert_not_called();tcp.assert_not_called()

"""Strict batch read framing and maintenance decisions without hardware."""
import collections,contextlib,importlib.util,io,sys,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1]

def load(test):
 p=HERE/'batch_transport.py';test.assertTrue(p.exists(),'batch transport missing');spec=importlib.util.spec_from_file_location('tested_batch_transport',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

class Wire:
 def __init__(self,chunks):self.chunks=collections.deque(chunks);self.sent=[];self.log=io.StringIO()
 def send(self,raw,discard_pending=True):self.sent.append((raw,discard_pending))
 def read_until(self,done,timeout):return self.chunks.popleft() if self.chunks else b''

class TransportTests(unittest.TestCase):
 def setUp(self):
  self.m=load(self);timer=patch.object(self.m.time,'sleep');self.sleep=timer.start();self.addCleanup(timer.stop)
 def frame(self,address=7,payload=b'X'*30,rtn=0):return self.m.codec.frame(rtn,payload.hex().upper(),address)
 def test_fragmented_exact_echo_and_reply_are_reassembled(self):
  req=self.m.codec.frame(0xa4,'',7);response=self.frame();w=Wire([req[:5],req[5:]+response[:9],response[9:20],response[20:]])
  self.assertEqual(self.m.query(w,7,0xa4),(0,b'X'*30));self.assertEqual(w.sent,[(req,False)])
 def test_trailing_foreign_or_extra_own_frame_or_noise_rejected(self):
  for chunks in ([self.frame()+self.frame(8)],[self.frame(),self.frame(8)],[self.frame(),b'noise'],[self.frame()+self.frame()]):
   with self.subTest(chunks=chunks),self.assertRaises(ValueError):self.m.query(Wire(chunks),7,0xa4)
 def test_foreign_bad_checksum_nonhex_and_nested_truncation_fail_closed(self):
  own=self.frame();badhex=bytearray(own);badhex[13:15]=b'GG';badhex[-5:-1]=f'{(-sum(badhex[1:-5]))&65535:04X}'.encode()
  for raw in (self.frame(8),own[:-5]+b'0000\r',bytes(badhex),own[:13]+self.frame()):
   with self.subTest(raw=raw),self.assertRaises((ValueError,TimeoutError)):self.m.query(Wire([raw]),7,0xa4)
 def test_existing_bootloader_probe_is_read_only_and_aborts(self):
  b=object.__new__(self.m.SerialBackend);b.port=Wire([self.m.flasher.boot_frame(b'RFB',data=b'\1\0')])
  with self.assertRaises(RuntimeError):b.no_bootloader()
  self.assertEqual([x[0][4:7] for x in b.port.sent],[b'RFL'])
 def test_echo_only_bootloader_probe_has_no_writes(self):
  b=object.__new__(self.m.SerialBackend);rfl=self.m.flasher.boot_frame(b'RFL');b.port=Wire([rfl]);b.no_bootloader();self.assertEqual(len(b.port.sent),1)
 def test_passive_bus_check_rejects_any_bytes(self):
  b=object.__new__(self.m.SerialBackend);b.port=Wire([b'~poll']);
  with self.assertRaises(RuntimeError):b.quiet()
  self.assertEqual(b.port.sent,[])
 def test_no_address_zero_response_allowed_in_external_mode(self):
  b=object.__new__(self.m.SerialBackend);b.port=Wire([self.frame(0)])
  with self.assertRaises(RuntimeError):b.no_pack_zero()
 def backend(self):
  b=object.__new__(self.m.SerialBackend);b.maintenance_port='SECOND';b.device='FIRST';b.log=io.StringIO();b.maintenance_started=False;b.port=Wire([]);return b
 def test_active_marker_never_started_or_cleared_again(self):
  b=self.backend();reply=(b'',(0,bytes(5)))
  with patch.object(self.m.codec,'exchange_serial',return_value=reply) as ex:b.prepare_master()
  self.assertEqual(ex.call_count,1);self.assertEqual(ex.call_args.args[1],self.m.codec.request('status'));self.assertFalse(b.maintenance_started)
 def test_inactive_marker_starts_once_and_confirms_fresh_zero_slaves(self):
  b=self.backend();replies=[(b'',(0,b'\xff'*4+b'\x0b')),(b'',(0,b'\0'*4+b'\x0b')),(b'',(0,bytes(5)))]
  with patch.object(self.m.codec,'exchange_serial',side_effect=replies) as ex,patch.object(self.m.codec,'wait_for_state',side_effect=lambda action,query,**kw:query(1)):
   b.prepare_master()
  self.assertEqual([c.args[1] for c in ex.call_args_list],[self.m.codec.request(a) for a in ('status','start','status')]);self.assertTrue(b.maintenance_started)
 def test_unknown_marker_or_start_rejection_never_retries(self):
  for replies in ([(b'',(0,b'\x01\0\0\0\0'))],[(b'',(0,b'\xff'*4+b'\x0b')),(b'',(5,b''))]):
   b=self.backend()
   with patch.object(self.m.codec,'exchange_serial',side_effect=replies) as ex,self.assertRaises((ValueError,RuntimeError)):b.prepare_master()
   self.assertLessEqual(ex.call_count,2)

 def test_partial_zero_response_or_partial_echo_is_not_absence(self):
  for raw in (self.frame(0)[:20],self.m.codec.frame(0x51,'',0)[:7]):
   b=object.__new__(self.m.SerialBackend);b.port=Wire([raw])
   with self.subTest(raw=raw),self.assertRaises(ValueError):b.no_pack_zero()
 def test_genuine_zero_silence_or_complete_echo_is_absence(self):
  for chunks in ([],[self.m.codec.frame(0x51,'',0)]):
   b=object.__new__(self.m.SerialBackend);b.port=Wire(chunks);b.no_pack_zero()

 def test_confirmed_master_pause_drains_old_inflight_poll_data(self):
  b=self.backend();b.port=Wire([b'old-poll-frame']);reply=(b'',(0,bytes(5)))
  with patch.object(self.m.codec,'exchange_serial',return_value=reply):b.prepare_master()
  self.assertEqual(list(b.port.chunks),[])
 def test_pause_drain_requires_a_complete_quiet_window_within_bound(self):
  self.assertTrue(hasattr(self.m,'drain_after_pause'),'pause drain is missing')
  clock=[0.0]
  class Busy(Wire):
   def read_until(self,done,timeout):clock[0]+=.5;return b'ongoing external traffic'
  with self.assertRaises(RuntimeError):self.m.drain_after_pause(Busy([]),timeout=2,idle=1.2,now=lambda:clock[0])

 def test_start_attempt_is_recorded_even_when_ack_is_missing(self):
  b=self.backend()
  with patch.object(self.m.codec,'exchange_serial',side_effect=[(b'',(0,b'\xff'*4+b'\x0b')),TimeoutError('ACK missing')]),self.assertRaises(TimeoutError):b.prepare_master()
  self.assertTrue(getattr(b,'maintenance_start_attempted',False));self.assertFalse(b.maintenance_started)

 def test_uart1_maintenance_requests_wait_practical_200ms_gap(self):
  b=self.backend()
  with patch.object(self.m.codec,'exchange_serial',return_value=(b'',(0,bytes(5)))):b.prepare_master()
  self.sleep.assert_called_once_with(.2)

if __name__=='__main__':unittest.main()

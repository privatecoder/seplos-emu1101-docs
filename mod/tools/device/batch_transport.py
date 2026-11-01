"""Exclusive local UART0 transport and strict batch-update readbacks.

No gateway support. UART1 may be used only for an explicitly selected master
maintenance adapter; UART0 remains the sole bootloader transport.
"""
import importlib.util
from pathlib import Path
import fcntl,os,select,termios,time


def load(name,filename):
 spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

flasher=load('batch_gap','flash_gap.py')
codec=flasher.entry.ascii
parameters=load('batch_parameter_codec','parameter_client.py')


class NoResponse(TimeoutError):
 """No response bytes after removing only a complete exact request echo."""
 pass


def query(port,address,command,info=b'',timeout=3):
 """One strict ASCII reply, including exact request echo/fragment handling.

 Never scan inside an incomplete outer frame. Reject extra bytes/replies,
 including foreign frames, rather than flushing them before the next query.
 """
 sent=codec.frame(command,info.hex().upper(),address)
 port.send(sent,discard_pending=False)
 deadline=time.monotonic()+timeout;buf=b''
 while time.monotonic()<deadline:
  chunk=port.read_until(lambda raw:bool(raw),max(.001,deadline-time.monotonic()))
  if not chunk:
   if buf:raise ValueError('Incomplete/ambiguous UART0 response; absence is not established')
   raise NoResponse(f'No reply from address {address}, command {command:02X}')
  buf+=chunk
  if len(buf)>2048:raise ValueError('Oversized/ambiguous UART0 reply')
  while buf.startswith(sent):buf=buf[len(sent):]
  if not buf or sent.startswith(buf):continue
  if not buf.startswith(b'~'):raise ValueError('Unexpected UART0 bytes before response')
  if len(buf)<13:continue
  if any(c not in b'0123456789ABCDEF' for c in buf[1:13]):raise ValueError('Invalid ASCII response header')
  n=int(buf[10:13],16)
  if n>512 or n%2:raise ValueError('Invalid ASCII response length')
  total=18+n
  if len(buf)<total:continue
  packet=buf[:total]
  if any(c not in b'0123456789ABCDEF' for c in packet[1:-1]):raise ValueError('Nonhex ASCII response')
  result=codec.parse_response(packet,address)
  tail=buf[total:]+port.read_until(lambda raw:bool(raw),.05)
  if tail:raise ValueError('Additional/foreign response or bus traffic; transaction ambiguous')
  return result
 if buf:raise ValueError('Incomplete UART0 response at deadline')
 raise NoResponse('ASCII response deadline expired without reply')


def drain_after_pause(port,timeout=5,idle=1.2,now=time.monotonic):
 """Collect prior polling only after confirmed UART1 pause; never flush it.

 Require a full continuous idle interval within the total bound. This is not
 used during flashing or before arbitrary commands, where any traffic aborts.
 """
 deadline=now()+timeout;received=0
 while deadline-now()>=idle:
  data=port.read_until(lambda raw:bool(raw),idle)
  if not data:return received
  received+=len(data)
 raise RuntimeError('UART0 did not become quiet after confirmed maintenance pause')


class ExclusivePort(flasher.Port):
 """Hold both advisory locking and TIOCEXCL for the entire bank operation."""
 def __init__(self,device,log):
  super().__init__(device,log)
  try:
   fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   fcntl.ioctl(self.fd,termios.TIOCEXCL)
  except BaseException:
   super().close();raise
 def send(self,data,discard_pending=True):
  if discard_pending and select.select([self.fd],[],[],0)[0]:
   raw=os.read(self.fd,4096);self.stamp('UNEXPECTED',raw)
   raise RuntimeError('Pending serial bytes would be discarded; refusing another command')
  super().send(data,discard_pending=False)


class SerialBackend:
 def __init__(self,device,log,maintenance_port=None):
  self.device=device;self.log=log;self.maintenance_port=maintenance_port;self.maintenance_started=False;self.maintenance_start_attempted=False;self.maintenance_pause_confirmed=False
 def __enter__(self):self.port=ExclusivePort(self.device,self.log);return self
 def __exit__(self,*args):self.port.close()
 def quiet(self):
  if self.port.read_until(lambda raw:bool(raw),1.2):raise RuntimeError('UART0 is busy; stop every other requester/polling master')
 def no_bootloader(self):
  sent=flasher.boot_frame(b'RFL');self.port.send(sent,discard_pending=False)
  raw=self.port.read_until(lambda data:bool(data),.5)
  if raw:
   # Collect the bounded remainder even when an adapter echo is fragmented.
   raw+=self.port.read_until(lambda data:False,.1)
   if raw!=sent:raise RuntimeError('Existing bootloader or unexpected UART0 response; no reset/flash allowed')
 def no_pack_zero(self):
  try:query(self.port,0,0x51,timeout=.5)
  except NoResponse:return
  raise RuntimeError('Address 0 responds: external mode must contain only slave addresses 1..N')
 def master_status(self):
  rtn,data=query(self.port,0,0x64,b'\2')
  if rtn==4 and not data:return None
  if rtn:raise RuntimeError(f'Master status rejected: RTN {rtn:02X}')
  return codec.parse_status(data)
 def prepare_master(self):
  if not self.maintenance_port:return
  def exchange(action,timeout=3):
   time.sleep(.2)  # Practical UART1 receive gap; other requesters must be stopped.
   raw,(rtn,data)=codec.exchange_serial(self.maintenance_port,codec.request(action),timeout,baud=9600)
   self.log.write(f'UART1 {action} RX {raw.hex()}\n');self.log.flush()
   if rtn:raise RuntimeError(f'UART1 {action} rejected: RTN {rtn:02X}')
   status=codec.parse_status(data)
   if status['flag'] is None:raise RuntimeError('Unknown master maintenance marker; no automatic erase or start')
   return status
  before=exchange('status')
  if before['flag']==0:
   self.maintenance_start_attempted=True
   exchange('start');self.maintenance_started=True
  def status(remaining):
   current=exchange('status',remaining);return current['flag'],current['effective_slaves']
  if before['flag']!=1 or before['effective_slaves']!=0:
   codec.wait_for_state('start',status,timeout=5)
  self.maintenance_pause_confirmed=True
  drained=drain_after_pause(self.port)
  self.log.write(f'UART0 drained {drained} prior bytes after confirmed pause; full idle observed\n')
  self.log.flush()
 def _read(self,address,command,size):
  rtn,data=query(self.port,address,command)
  if rtn:raise ValueError(f'Pack {address}: command {command:02X} RTN {rtn:02X}')
  if len(data)!=size:raise ValueError(f'Pack {address}: command {command:02X} requires {size} reply bytes')
  return data
 def snapshot(self,address):
  version=self._read(address,0x51,32)
  raw=self._read(address,0x47,169)
  if raw[0]!=address:raise ValueError('Parameter payload belongs to another address')
  config=parameters.decode_parameters(raw[1:],address)
  battery=self._read(address,0xa2,30);bms=self._read(address,0xa4,30)
  rtn,data=query(self.port,address,0x64,b'\3')
  if rtn==4 and not data:info=None;data=b''
  elif rtn:raise ValueError(f'Firmware identity rejected: RTN {rtn:02X}')
  else:info=codec.parse_info(data)
  diag=None
  if info and info.get('image_flags',0)&32:
   code,body=query(self.port,address,0x64,b'\4')
   if code:raise ValueError('Promised storage diagnostics unavailable')
   diag=codec.parse_diagnostics(body)
  telemetry=self._read(address,0x42,75)
  if telemetry[:3]!=bytes([0,address,16]):raise ValueError('Unexpected 16S telemetry layout/address')
  return dict(address=address,version_hex=version.hex(),parameters_hex=raw.hex(),
              battery_sn_hex=battery.hex(),bms_sn_hex=bms.hex(),info_hex=data.hex() if info else None,
              info=info,diagnostics=diag,telemetry_hex=telemetry.hex(),config=config)
 def settle(self):
  time.sleep(1.2)
 def flash(self,release,address,gap):
  return flasher.flash_session(self.port,release['prepared'],address=address,gap_ms=gap)

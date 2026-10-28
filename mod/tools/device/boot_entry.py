"""Bounded bootloader entry after one addressed reset, including MAINT1.6.2.

Only RFL probes are repeated; never reset, erase or program. A reset RTN08
aborts. No fixed bound on actual MCU erase time is claimed. Port must provide
send(data, discard_pending=...) and read_until(predicate, timeout).
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import importlib.util
from pathlib import Path
import time

spec=importlib.util.spec_from_file_location('boot_entry_ascii',Path(__file__).with_name('maintenance_client.py'))
ascii=importlib.util.module_from_spec(spec);spec.loader.exec_module(ascii)

def boot_frame(cmd,adr=0,data=b''):
 body=cmd+len(data).to_bytes(2,'big')+adr.to_bytes(2,'big')+data
 return b'::::'+body+((-sum(body))&65535).to_bytes(2,'big')+b'\r'*4

def validate_write_ack(raw):
 if len(raw)!=17 or raw[:7]!=b'::::WFB' or raw[7:11]!=bytes(4) or raw[-4:]!=b'\r'*4 or (sum(raw[4:-6])+int.from_bytes(raw[-6:-4],'big'))&65535:
  raise ValueError('Expected a complete empty WFB write acknowledgement')

def enter(port,address=0,timeout=3,now=time.monotonic):
 ascii.valid_address(address)
 if timeout<=0:raise ValueError('positive boot-entry timeout required')
 reset=bytearray(ascii.frame(0x45,'010600',address));reset[1:3]=b'26'
 reset[-5:-1]=f'{(-sum(reset[1:-5]))&65535:04X}'.encode();reset=bytes(reset)
 port.send(reset);deadline=now()+timeout;buffer=b'';first=True
 while now()<deadline:
  # Initially preserve the historical50ms probe; subsequent probes cover the
  # extra SOC save time. Never flush a pending reset-error response.
  buffer+=port.read_until(lambda raw:raw.endswith(b'\r'),min(.05 if first else .12,deadline-now()))
  first=False
  while b'~' in buffer and b'\r' in buffer[buffer.index(b'~'):]:
   start=buffer.index(b'~');end=buffer.index(b'\r',start)+1;packet=buffer[start:end];buffer=buffer[end:]
   if packet==reset:continue
   try:rtn,_=ascii.parse_response(packet,address)
   except ValueError:continue
   if rtn:raise RuntimeError(f'Reset rejected: RTN{rtn:02X}; no flash commands sent')
  start=buffer.find(b'::::')
  if start>=0 and len(buffer)-start>=11:
   buffer=buffer[start:];n=int.from_bytes(buffer[7:9],'big')
   if n>512:raise RuntimeError('Invalid bootloader ACK length')
   total=17+n
   if len(buffer)>=total:
    ack=buffer[:total]
    if ack[4:7]!=b'RFB' or ack[9:11]!=b'\0\0' or ack[-4:]!=b'\r'*4 or (sum(ack[4:-6])+int.from_bytes(ack[-6:-4],'big'))&65535 or ack[11:-6]!=b'\1\0':
     raise RuntimeError('Invalid/unsupported bootloader ACK; no flash commands sent')
    return ack
  if len(buffer)>4096:raise RuntimeError('Boot-entry response exceeds limit')
  # An ACK may be split after any byte, including the first trailer CR.
  # Once any possible boot-frame prefix has arrived, collect its remainder;
  # never create another response while one is still in flight.
  pending_boot=b'::::' in buffer or buffer.endswith((b':',b'::',b':::'))
  if now()<deadline and not pending_boot:port.send(boot_frame(b'RFL'),discard_pending=False)
 raise TimeoutError('Bootloader not confirmed; reset was not repeated, no flash commands sent')

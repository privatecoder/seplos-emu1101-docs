#!/usr/bin/env python3
"""Offline replay of the legacy UART0 FC03-like path, OEM04.06 vs06.03.

Existing patcher venv/Unicorn,Python -I,cwd /private/tmp. Only synthetic inputs;
no serial/network access,no image or NVM writes. Prints four checked responses.
Facts are frozen in the topology evidence folder and bound to the OEM digest.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
import sys,json,struct
from pathlib import Path
root=PROJECT_ROOT;sys.path.insert(0,str(PATCHER_ROOT))
import argparse
argparse.ArgumentParser(description=__doc__).parse_args()
from seplos.image import Image
import seplos.machine as mm
mm.UART=0x50010000
for version,dispatch,extra in (('16.04.06',0x10ca,0x1aee),('16.06.03',0x10b4,None)):
 im=Image.read(next((root/'vendor/firmware').glob('*'+version+'*')));facts=json.loads(research_input('uart0-fc03-'+version).read_text());facts['functions']['irq']=struct.unpack_from('<I',im.app,0x4c)[0]&~1
 for req in (bytes.fromhex('030300010001d428'),bytes.fromhex('030300010001d429')):
  assert im.sha==facts['original_app_sha256']
  m=mm.Machine(im,facts);m.run(m.f['loader']);m.put(0x20000027,b'\x03');m.feed(req);before=m.read(0x20000100,2).hex();m.run(dispatch)
  if extra is not None:m.run(extra)
  response=m.drain()
  print(version,'req',req.hex(),'stateafterIRQ',before,'reply',response.hex(),'responseCRC',mm.modbus_frame(response[:-2])==response if response else None)
  if version=='16.04.06' and req[-1]==0x28:assert response==bytes.fromhex('030300020000e5e8') and mm.modbus_frame(response[:-2])==response
  else:assert not response

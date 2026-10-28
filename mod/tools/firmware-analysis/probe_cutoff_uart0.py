#!/usr/bin/env python3
"""Real UART0 parser/dispatcher against a verified1.6 build; no physical I/O."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT
from pathlib import Path
import argparse,hashlib,json,sys
ROOT = PROJECT_ROOT
sys.path.insert(0,str(PATCHER_ROOT))
from seplos.image import Image
from seplos.machine import Machine,ascii_frame
from seplos.thumb import Code


def verify(build):
 report=json.loads((build/'report.json').read_text());facts=report['facts'];d=facts['cutoff'];r=facts['ram']
 raw=(build/'firmware.ehex').read_bytes();image=Image.parse(raw.decode('ascii'))
 assert report['status']=='passed' and report['build']['patch_version']=='1.6'
 assert hashlib.sha256(raw).hexdigest()==report['output_file_sha256']
 assert image.sha==report['build']['app_sha256']
 code=Code(image.app)
 # Derive the original metadata base and stop before physical UART0 TX.
 parser=code.body(d['uart0_parser'])
 bases={i.literal for i in parser if i.op=='ldr' and i.args.startswith('r6, [pc,')}
 assert len(bases)==1 and next(iter(bases))+0x32==d['uart0_meta']-6
 calls=[i for i in code.body(d['uart0_dispatch']) if i.op=='bl']
 before_response=calls[-2].at
 rows=[]
 for address in (0,1,11):
  for mode,value,locked,expected in (('unicast-off',31,False,1),('FF-on-locked',16,True,1),('FF-off-unlocked',31,False,0),('unicast-on-locked',16,True,0),('foreign-on',16,True,1),('nonhex-on',16,True,1)):
   m=Machine(image,facts);m.defaults(address)
   m.put(r['group0'],bytes([m.num(r['group0'])&~0x18]))
   if locked:
    m.put(d['ram'],b'\1');m.put(r['group0'],bytes([m.num(r['group0'])&~32]))
    m.run(d['entries']['hook_cut_serializer_0'])
   ops=len(m.nv_ops)
   target=255 if mode.startswith('FF') else (address+1 if mode=='foreign-on' else address)
   packet=bytearray(ascii_frame(target,0x45,bytes([0,4,value])))
   if mode=='nonhex-on':packet[3]=ord('G')
   m.put(d['uart0_rx'],packet);m.put(d['uart0_meta']-6,len(packet).to_bytes(2,'little'))
   m.put(d['uart0_state'],b'\4');m.pause=before_response
   m.run(d['uart0_dispatch'])
   latch=m.num(d['ram']);state=m.num(d['uart0_state']);rtn=m.num(d['uart0_rtn'])
   assert latch==expected,(mode,address,latch)
   if mode in ('FF-on-locked','foreign-on','nonhex-on'):
    assert state==0 and len(m.nv_ops)==ops,(mode,'must remain silent without writes')
   else:assert rtn==0,(mode,rtn)
   if mode in ('unicast-off','unicast-on-locked'):assert len(m.nv_ops)-ops==4
   if mode=='FF-off-unlocked':assert len(m.nv_ops)==ops and state==0
   rows.append(dict(name=mode,address=address,passed=True,latch=latch,uart0_state=state,rtn=rtn,nv_operations=len(m.nv_ops)-ops))
 return dict(passed=True,build_id=report['build']['build_id'],image_sha256=image.sha,tests=rows,hardware_access=False,scope='OEM parser+dispatcher through power hook; stops before physical UART0 TX; polling host accessibility unchanged')


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if not __debug__:p.error('Python -O is unsupported')
 if a.out.exists():p.error('output exists')
 result=verify(a.build.resolve())
 with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print(json.dumps({'passed':result['passed'],'tests':len(result['tests']),'build_id':result['build_id'],'hardware_access':False}))
if __name__=='__main__':main()

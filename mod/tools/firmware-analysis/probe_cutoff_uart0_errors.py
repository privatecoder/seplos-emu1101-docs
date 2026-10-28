#!/usr/bin/env python3
"""MAINT1.6 UART0 targeted power errors: real parser, handler and ASCII encoder.

Fault injection in emulator only. No hardware interfaces or firmware changes.
Stops before the original physical UART0 sender, checks the complete reply.
"""

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
from seplos.selftest import ascii_payload
from seplos.thumb import Code
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_R2


def verify(build):
 report=json.loads((build/'report.json').read_text());facts=report['facts'];d=facts['cutoff'];r=facts['ram']
 raw=(build/'firmware.ehex').read_bytes();image=Image.parse(raw.decode('ascii'))
 assert report['status']=='passed' and report['build']['patch_version']=='1.6'
 assert hashlib.sha256(raw).hexdigest()==report['output_file_sha256']
 assert image.sha==report['build']['app_sha256']
 code=Code(image.app);calls=[i for i in code.body(d['uart0_dispatch']) if i.op=='bl']
 stop=calls[-1].at
 sender_bases={i.literal for i in code.body(calls[-1].target) if i.op=='ldr' and i.args.startswith('r1, [pc,') and i.literal is not None and 0x20000000<=i.literal<0x20002000}
 assert len(sender_bases)==1 and next(iter(sender_bases))+0x36==d['uart0_rx']-6
 rows=[]
 for address in (0,1,11):
  for command in (0x10,0x1f):
   for fault in ('none','primary-program','backup-program','no-primary-erase-or-program','primary-final-CRC','backup-final-CRC'):
    m=Machine(image,facts);m.defaults(address)
    g=m.num(r['group0'])&~0x18
    if command==0x10:g&=~32;m.put(d['ram'],b'\1')
    m.put(r['group0'],bytes([g]));m.run(d['entries']['hook_cut_serializer_0'])
    initial_nv=m.read(0x25000,8192);m.nv_step=0;m.nv_ops.clear()
    if fault=='primary-program':m.nv_fail_at={2}
    elif fault=='backup-program':m.nv_fail_at={4}
    elif fault=='no-primary-erase-or-program':m.nv_fail_at={1,2}
    injected=[]
    if fault.endswith('final-CRC'):
     target=d['nv_primary'] if fault.startswith('primary') else d['nv_backup']
     def corrupt(board,pc,target=target):
      if pc==d['flash_read'] and board.nv_step==4 and board.uc.reg_read(UC_ARM_REG_R0)==target and board.uc.reg_read(UC_ARM_REG_R2)==64 and not injected:
       board.put(target+171,bytes([board.num(target+171)^1]));injected.append(target)
      return False
     m.callback=corrupt
    request=ascii_frame(address,0x45,bytes([0,4,command]))
    m.put(d['uart0_rx'],request);m.put(d['uart0_meta']-6,len(request).to_bytes(2,'little'));m.put(d['uart0_state'],b'\4')
    m.pause=stop;m.run(d['uart0_dispatch'])
    assert m.uc.reg_read(UC_ARM_REG_PC)==stop and m.num(d['uart0_state'])==4
    response=m.read(d['uart0_state']+1,m.num(d['uart0_rx']-6,2))
    rtn,info=ascii_payload(response,address)
    expected=0 if fault=='none' else 8
    assert (rtn,info)==(expected,b''),(address,command,fault,response)
    assert response==ascii_frame(address,expected)
    if fault.endswith('final-CRC'):assert len(injected)==1
    latch=m.num(d['ram']);visible_locked=not bool(m.num(r['group0'])&32)
    assert latch==visible_locked==int(fault!='none' or command==0x1f)
    if fault!='none':
     assert m.num(d['onoff'])&0x17==0
     assert m.num(0x50002000,4)&((1<<10)|(1<<12)|(1<<13)|(1<<15))==0
    n=Machine(image,facts);n.put(0x25000,m.read(0x25000,8192));n.defaults(address)
    reboot_latch=n.num(d['ram'])
    if fault=='no-primary-erase-or-program':
     assert m.read(0x25000,8192)==initial_nv
     assert reboot_latch==int(command==0x10)
    if fault=='none':assert reboot_latch==int(command==0x1f)
    rows.append(dict(address=address,command=f'{command:02X}',fault=fault,passed=True,rtn=f'{rtn:02X}',length=response[9:13].decode(),response_ascii=response.decode(),response_hex=response.hex(),RAM_latch=latch,readable_bit5_locked=visible_locked,reboot_latch=reboot_latch,nv_operations=m.nv_ops))
 return dict(passed=True,build_id=report['build']['build_id'],image_sha256=image.sha,tests=rows,hardware_access=False,physical_transmit=False,scope='real OEM UART0 parser+dispatcher+ASCII encoder, emulated flash faults, stop before physical sender')


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if not __debug__:p.error('Python -O is unsupported')
 if a.out.exists():p.error('output exists')
 result=verify(a.build.resolve())
 with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print(json.dumps(dict(passed=True,tests=len(result['tests']),build_id=result['build_id'],hardware_access=False)))
if __name__=='__main__':main()

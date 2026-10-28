#!/usr/bin/env python3
"""Offline, version-bound evidence for GPIO address chaining in OEM16.06.13.

Executes original Thumb with synthetic GPIO levels in the existing emulator.
No device/network access or image/parameter writes. Does not establish physical
RJ45-to-GPIO wiring, signal voltage, pullups, isolation or real timing.
Use patcher venv with Python -I from /private/tmp; --out refuses overwrite.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
from pathlib import Path
import argparse,hashlib,json,sys

ROOT = PROJECT_ROOT
sys.path.insert(0,str(PATCHER_ROOT))

PROFILE=dict(
 OEM_app_sha256='5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95',
 GPIO=0x50002000,pulse_input_bit=8,pulse_output_bit=7,successor_input_bit=9,
 flags=0x200000f6,counters=0x2000160c,group7=0x2000002f,
 address=0x20000027,slaves=0x20000026,
 receive_pulse=0x9334,debounce=0x93d0,send_pulse=0x9410,assign=0x944c,
 fast_callers=[0x6080,0x6084,0x6088],assign_caller=0x620e,
 physical_RJ45_mapping='unknown; RS485 socket pins4/5 are candidates',
 period='timer setup divides core clock by200: nominal5ms per fast-handler call; not measured')

def main():
 from seplos.image import Image
 from seplos.thumb import Code
 from seplos.machine import Machine
 im=Image.read(ROOT/'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex')
 assert im.sha==PROFILE['OEM_app_sha256'],'unsupported OEM image'
 facts=json.loads(research_input('hard-stop-1.6.3').read_text())['facts']
 c=Code(im.app);checks=[]
 def record(name,**observed):checks.append(dict(name=name,passed=True,**observed))
 def board():return Machine(im,facts)
 def port(m,value):m.put(PROFILE['GPIO'],value.to_bytes(4,'little'))
 def call(m,fn,count):
  for _ in range(count):m.run(PROFILE[fn])
 decoded=PROFILE['counters']+6
 # Bind the scheduler gate and native call targets to the hash-identified image.
 assert c.ins[0x6078].literal==PROFILE['group7']
 assert c.ins[0x607c].token()==['lsls','r0, r0, #0x1a']
 assert c.ins[0x607e].op=='bpl' and c.ins[0x607e].target==0x608c
 for site,name in zip(PROFILE['fast_callers'],('receive_pulse','debounce','send_pulse')):
  assert c.ins[site].target==PROFILE[name]
 assert c.ins[PROFILE['assign_caller']].target==PROFILE['assign']
 assert c.ins[0x5fc8].token()==['movs','r1, #0xc8']
 assert c.ins[0x5fcc].target==0xc9dc # unsigned division used by timer setup
 record('native-Group7-bit5-gate-and-callers')
 # Decode addresses1..21 from real instructions; input waveforms are synthetic.
 for address in range(1,22):
  m=board();port(m,1<<8);call(m,'receive_pulse',1)
  port(m,0);call(m,'receive_pulse',address*10)
  port(m,1<<8);call(m,'receive_pulse',1)
  actual=m.num(decoded);assert actual==address,(address,actual)
  record('receive-address-'+str(address),low_calls=address*10,decoded=actual)
 for level,expected in ((1<<8,0),(0,21)):
  m=board();m.put(decoded,b'\x0f');port(m,level);call(m,'receive_pulse',499)
  before=m.num(decoded);assert before==15
  call(m,'receive_pulse',1);actual=m.num(decoded);assert actual==expected
  record('stable-input-'+('high' if level else 'low'),calls=500,decoded=actual)
 # Native debounce tests counters before incrementing:11/201 calls from zero.
 m=board();port(m,0);call(m,'debounce',10);assert not m.num(PROFILE['flags'])&8
 call(m,'debounce',1);assert m.num(PROFILE['flags'])&8
 port(m,1<<9);call(m,'debounce',200);assert m.num(PROFILE['flags'])&8
 call(m,'debounce',1);assert not m.num(PROFILE['flags'])&8
 record('successor-debounce',assert_low_calls=11,clear_high_calls=201)
 # Full native assignment -> pulse output, including otherwise live GPIO bits.
 for address in range(22):
  m=board();m.put(PROFILE['group7'],b'\x20');m.put(decoded,bytes([address]))
  m.put(PROFILE['flags'],b'\x08');port(m,(1<<8)|(1<<9)|(1<<7))
  call(m,'assign',1);assert m.num(PROFILE['address'])==address
  target=(address+1)*10;assert m.num(PROFILE['counters']+14,2)==target
  for _ in range(target):
   call(m,'send_pulse',1);assert not m.num(PROFILE['GPIO'],4)&(1<<7)
   assert m.num(PROFILE['GPIO'],4)&0x300==0x300
  call(m,'send_pulse',1);assert m.num(PROFILE['GPIO'],4)&(1<<7)
  assert not m.num(PROFILE['flags'])&16
  record('assign-and-forward-'+str(address),address=address,output_low_calls=target)
 m=board();m.put(PROFILE['group7'],b'\x60');m.put(decoded,b'\0')
 call(m,'assign',1);assert m.num(PROFILE['address'])==1
 record('Group7-bit6-prevents-auto-master')
 # Reviewed fixed MAINT profiles leave these OEM routines unchanged.
 for version,suffix in [('1_5_2','DIAGNOSTICS'),('1_6_3','CUTOFF_POSITIVE')]:
  p=ROOT/'local/releases'/f'CAN1101[V16.06.13_PN01_250607_MAINT_V{version}_{suffix}].ehex'
  patch=Image.read(p);assert patch.app[0x9334:0x94d2]==im.app[0x9334:0x94d2]
  record('MAINT-'+version+'-native-address-code-identical',app_sha256=patch.sha)
 dependencies={rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() for rel in (
  'mod/firmware/patcher/seplos/machine.py','mod/firmware/patcher/seplos/thumb.py','mod/firmware/patcher/seplos/image.py',
  'local/builds/oem16.06.13/maint-1.6.3/baa01ecd5af4eb28/report.json')}
 result=dict(passed=True,profile=PROFILE,checks=checks,check_count=len(checks),
  emulator='existing Machine/Unicorn, actual OEM Thumb; synthetic GPIO input',
  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  dependencies_sha256=dependencies,
  OEM_file='vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex',
  hardware_access=False,flashed=False,
  limitations=['No RJ45 pin mapping from machine code alone','No electrical-level/isolation measurement',
   'Nominal timer period, no real bus/IRQ jitter measurement','Group7.bit5 gate checked statically; handler traces run directly'])
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);a=p.parse_args()
 result=main();data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
 if a.out:
  with a.out.open('x') as stream:stream.write(data)
  print(json.dumps(dict(passed=result['passed'],checks=result['check_count'],out=str(a.out))))
 else:print(data,end='')

#!/usr/bin/env python3
"""Read-only feasibility probe: real16.06.13 Thumb aggregation in modeled RAM.

No image patching, serial ports or network. Run Python-I from /private/tmp.
Requires the existing Patcher/Unicorn environment. Optional --out writes a NEW JSON.
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
from seplos.analysis import discover
from seplos.machine import Machine,probe


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);args=p.parse_args()
 image_path=ROOT/'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex'
 original=Image.read(image_path);facts=probe(original,discover(original))
 release=ROOT/'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V1_5_ACCESS].ehex'
 image=Image.read(release)
 # These reviewed original functions are unchanged in this fixed MAINT build.
 for start,end in ((0x870c,0x87da),(0x96ce,0x99ba)):
  assert image.app[start:end]==original.app[start:end]
 def board():
  m=Machine(image,facts);m.defaults(0);m.put(0x20000026,b'\x0b')
  m.put(0x2000002b,b'\0');m.put(0x2000002f,b'\0')
  m.put(0x20001300+50*2,(15000).to_bytes(2,'little'))
  m.put(0x20001300+52*2,(-15500).to_bytes(2,'little',signed=True))
  m.put(0x20001300+4*2,(3650).to_bytes(2,'little'))
  m.put(0x20000518,(0xfff).to_bytes(4,'little'))
  m.put(0x2000164c,bytes([12,12]));m.put(0x2000164c+0x20,(500).to_bytes(2,'little'))
  m.put(0x2000164c+0x24,(9000).to_bytes(2,'little'))
  m.put(0x20001634,(3300).to_bytes(2,'little')*2+(2981).to_bytes(2,'little')*2)
  for index in range(12):
   record=bytearray(30);record[10:12]=(5280).to_bytes(2,'little');record[26]=3;record[29]=0x10
   m.put(0x20000524+30*index,record)
  return m
 def aggregate(m):
  m.run(0x96ce);m.run(0x98a8)
  return {'charge_eligible':m.num(0x2000164c+3),'discharge_eligible':m.num(0x2000164c+4),'charge_blocked':m.num(0x2000164c+6),'discharge_blocked':m.num(0x2000164c+7),'ccl_A':m.num(0x2000164c+0x24,2)/10,'dcl_A':m.num(0x2000164c+0x28,2)/10,'flash_ops':m.flash_ops,'saves':m.saves}
 results={}
 m=board();results['twelve_normal']=aggregate(m)
 m=board();m.put(0x20000524+30*7+26,b'\x02');m.put(0x20000524+30*7+29,b'\x20');results['one_off_charge_path_still_on']=aggregate(m)
 m=board()
 for i in range(12):m.put(0x20000524+30*i+26,b'\x02');m.put(0x20000524+30*i+29,b'\x20')
 results['all_off_charge_paths_still_on']=aggregate(m)
 m=board();m.put(0x20000524+30*7+26,b'\0');m.put(0x20000524+30*7+29,b'\x20');results['hypothetical_one_fully_charge_blocked']=aggregate(m)
 m=board()
 for i in range(12):m.put(0x20000524+30*i+26,b'\0');m.put(0x20000524+30*i+29,b'\x20')
 m.put(0x2000002b,b'\x40');m.put(0x20001634+4,(2600).to_bytes(2,'little')*2)
 m.put(0x20001300+36*2,(2731).to_bytes(2,'little'));m.put(0x20001300+37*2,(2831).to_bytes(2,'little'))
 results['hypothetical_all_blocked_but_heating_enabled']=aggregate(m)
 m=board();m.put(0x200000ac,b'\x20');m.put(0x20000cd0,(100).to_bytes(2,'little',signed=True));m.run(0x870c);m.run(0x8a24)
 results['off_then_1A_charge_state_tick']={'system_status':m.num(0x200000ac),'off':bool(m.num(0x200000ac)&0x20)}
 assert results['twelve_normal']['ccl_A']==900 and results['twelve_normal']['dcl_A']==1740
 assert results['one_off_charge_path_still_on']['ccl_A']==900 and results['one_off_charge_path_still_on']['dcl_A']==1595
 assert results['all_off_charge_paths_still_on']['ccl_A']==900 and results['all_off_charge_paths_still_on']['dcl_A']==0
 assert results['hypothetical_one_fully_charge_blocked']['ccl_A']==888
 assert results['hypothetical_all_blocked_but_heating_enabled']['ccl_A']==120
 assert not results['off_then_1A_charge_state_tick']['off']
 result={'hardware_access':False,'firmware_modified':False,'release_sha256':hashlib.sha256(release.read_bytes()).hexdigest(),'oem_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),'scope':'actual unchanged16.06.13 aggregation/state functions; synthetic input records, not new patch implementation','results':results}
 if args.out:
  with args.out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

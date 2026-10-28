#!/usr/bin/env python3
"""Read-only OEM16.06.13 cutoff counterexamples; never patches or opens ports.

Run the Patcher venv with -I from /private/tmp. Optional --out must be new.
Addresses below are intentionally tied to the exact reviewed OEM file hash.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT
from pathlib import Path
import argparse, hashlib, json, sys
ROOT = PROJECT_ROOT
sys.path.insert(0,str(PATCHER_ROOT))
from seplos.image import Image
from seplos.analysis import discover
from seplos.machine import probe,Machine


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);args=p.parse_args()
 path=ROOT/'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex'
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if digest!='0ea75c9834cf19789a58f58db8cde1a2bbd722a8f5a7bde7f00106f59b91ccf6':raise ValueError('unreviewed OEM image for fixed-address probe')
 im=Image.read(path);facts=probe(im,discover(im))
 def board(status=0x20,current=0):
  m=Machine(im,facts);m.defaults(1)
  m.put(0x200000ac,bytes([status]));m.put(0x200000b5,b'\x03');m.put(0x200000b6,b'\x03')
  m.put(0x20000030,bytes(8));m.put(0x200000bb,b'\0')
  m.put(0x20000cd0,current.to_bytes(2,'little',signed=True))
  m.put(0x50002000,((1<<12)|(1<<13)).to_bytes(4,'little'))
  return m
 def state(m):
  return {'system_status':m.num(0x200000ac),'on_off':m.num(0x200000b5),'event8':m.num(0x20000005),
          'charge_gpio':bool(m.num(0x50002000,4)&(1<<12)),
          'discharge_gpio':bool(m.num(0x50002000,4)&(1<<13)),
          'limiter_gpio':bool(m.num(0x50002000,4)&(1<<10))}
 out={}
 m=board();m.run(0x7184);out['off_no_charging_discharge_gate']=state(m)
 m=board(0xa2,400);m.run(0x7184);out['off_4A_charging_discharge_override']=state(m)
 m=board();m.put(0x20000005,b'\x40');m.run(0x6ffa);out['preinjected_inhibit_is_overwritten']=state(m)
 m=board(current=-1100);m.put(0x20000035,b'\x01');m.put(0x200000c4,b'\x09')
 m.run(0x6ffa);out['synthetic_charger_alarm_after_10s_discharge']=state(m)
 m=board();m.put(0x200000f0,b'\x20');m.put(0x200000f1,b'\x10');m.put(0x200015da,b'\x1d')
 p15=m.num(facts['ram']['words']+30,2);m.put(0x20000cda,(p15+100).to_bytes(2,'little'))
 m.run(0x8a24);out['off_voltage_wakeup_after_30s']=state(m)
 assert not out['off_no_charging_discharge_gate']['discharge_gpio']
 assert out['off_4A_charging_discharge_override']['discharge_gpio']
 assert out['preinjected_inhibit_is_overwritten']['charge_gpio']
 assert out['synthetic_charger_alarm_after_10s_discharge']['charge_gpio']
 assert not out['off_voltage_wakeup_after_30s']['system_status']&0x20
 result={'oem_sha256':digest,'scope':'unchanged OEM Thumb, synthetic RAM/MMIO; not a MAINT1.6 implementation',
         'hardware_access':False,'firmware_modified':False,'results':out}
 if args.out:
  with args.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result,indent=2))


if __name__=='__main__':main()

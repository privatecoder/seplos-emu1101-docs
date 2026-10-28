#!/usr/bin/env python3
"""Compare actual OEM16.06.13/MAINT1.6 UART2 status builders and TX IRQ.

No physical interfaces. Takes saved UART0 telemetry (JSON key42) and parameter
backup (JSON key parameters). Only the fixed, verified release is supported.
Tests modeled UART2 bytes, not display electronics or electrical UART output.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
from pathlib import Path
import argparse
import binascii
import hashlib
import json
import struct
import sys

ROOT = PROJECT_ROOT
sys.path.insert(0,str(PATCHER_ROOT))
from seplos.image import Image
from seplos.machine import Machine

UART2=0x50012000


class DisplayMachine(Machine):
    def __init__(self,image,facts):
        self.display_output=bytearray()
        super().__init__(image,facts)

    def _read(self,uc,access,address,size,value,user):
        if address==UART2+8:
            self.put(address,((1<<27) if self.num(UART2+4,4)&0x40 else 0).to_bytes(4,'little'))
            return
        super()._read(uc,access,address,size,value,user)

    def _write(self,uc,access,address,size,value,user):
        if address==UART2:self.display_output.append(value&255)
        super()._write(uc,access,address,size,value,user)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--telemetry',type=Path,required=True)
    p.add_argument('--parameters',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if not __debug__:p.error('Python -O is unsupported')
    if args.out.exists():p.error('Choose a new report')
    original=Image.read(ROOT/'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex')
    manifest=json.loads((ROOT/'local/releases/MAINT1.6-Packsperre.json').read_text())
    path=ROOT/'local/releases'/manifest['name'];patched=Image.read(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['ehex_sha256']
    report=json.loads(research_input('pack-lock-1.6').read_text())
    facts=report['facts'];assert original.sha==facts['original_app_sha256']
    # Fixed reviewed functions plus their literal pools; LCD A1 wrapper is outside these.
    ranges=((0x74a6,0x761e),(0x761e,0x77dc),(0x77dc,0x7ea2),(0x820c,0x8288))
    for start,end in ranges:assert original.app[start:end]==patched.app[start:end]
    assert original.app[0x54:0x58]==patched.app[0x54:0x58]
    telemetry=bytes.fromhex(json.loads(args.telemetry.read_text())['42'])
    config=json.loads(args.parameters.read_text())['parameters']
    assert len(telemetry)==75 and telemetry[2]==16 and len(config['function_switches'])==8
    expected_cells=telemetry[3:35];cases=[]
    for address in (0,7):
        for extended in (False,True):
            outputs=[]
            for image in (original,patched):
                m=DisplayMachine(image,facts);m.defaults(address);r=m.r
                m.put(r['words'],b''.join(x.to_bytes(2,'little') for x in config['parameters_u16']))
                m.put(r['small'],bytes(config['parameters_u8']))
                groups=bytearray(config['function_switches']);groups[7]=(groups[7]|8|16) if extended else ((groups[7]|8)&~16)
                m.put(r['group0'],groups);m.put(r['name'],bytes.fromhex(config['device_name_hex']))
                m.put(r['slaves'],b'\0')
                for source,target,count in ((3,0x20000cc8+0x14,16),(36,0x20000cc8+0x34,6)):
                    m.put(target,b''.join(telemetry[i:i+2][::-1] for i in range(source,source+count*2,2)))
                m.put(0x200000ac,b'\2');m.put(0x200000e9,b'\2');m.put(0x200000b5,b'\3')
                m.run(0x8288)
                irq=struct.unpack_from('<I',image.app,0x54)[0]&~1
                for _ in range(50):
                    if not m.num(UART2+4,4)&0x40:break
                    m.run(irq)
                assert not m.num(UART2+4,4)&0x40,'UART2 TX did not finish'
                raw=bytes(m.display_output)
                assert raw[0]==0x55 and raw[-1]==0xaa
                assert binascii.crc_hqx(raw[1:-3],0)==int.from_bytes(raw[-3:-1],'big')
                prefix=4 if extended else 3
                assert len(raw)==raw[prefix-1]+prefix+3
                assert raw[2 if extended else 1]==0x46
                if extended:assert raw[1]==address
                assert raw[prefix]==16 and raw[prefix+1:prefix+33]==expected_cells
                outputs.append(raw)
            assert outputs[0]==outputs[1],'OEM and patched UART2 bytes differ'
            cases.append(dict(address=address,extended=extended,bytes=len(outputs[0]),
                              OEM_MAINT_identical=True,cells_equal_saved_telemetry=True,CRC_valid=True,
                              frame_hex=outputs[0].hex()))
    result=dict(passed=True,hardware_access=False,scope='actual UART2 status dispatcher, builder, CRC, sender and TX IRQ; modeled peripheral',
                build_id=manifest['build_id'],unchanged_code_ranges=[[hex(a),hex(b)] for a,b in ranges],
                unchanged_UART2_vector=True,cases=cases,
                limitations=['No physical UART2 trace','No display electronics or firmware model','Not a complete main-loop/timer execution'])
    with args.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))
    print('PASS: four OEM/MAINT UART2 frame and TX-IRQ comparisons')


if __name__=='__main__':main()

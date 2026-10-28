#!/usr/bin/env python3
"""Execute OEM16.06.13 and fixed MAINT1.6 SOC/capacity/checkpoint paths.

No physical I/O or firmware changes. IAP block6 acceptance/storage is modeled;
the real loader, saver, counters, calibration, UART0 parser/encoder and handlers
execute as Cortex-M0 code. Parameters are synthetic, not a live pack snapshot.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = PROJECT_ROOT
sys.path.insert(0,str(PATCHER_ROOT))
from seplos.image import Image
from seplos.machine import Machine,ascii_frame,frame
from seplos.selftest import ascii_payload
from seplos.thumb import Code
from unicorn.arm_const import UC_ARM_REG_R0

MEASURE=0x20000cc8
COUNTER=0x200015e0


def number(m,address,value,width=2,signed=False):
    m.put(address,int(value).to_bytes(width,'little',signed=signed))


def capacity(m,remaining=4956,full=28000):
    number(m,MEASURE+12,remaining);number(m,MEASURE+14,full)
    number(m,COUNTER,full*3600,4);number(m,COUNTER+12,remaining*3600,4)
    soc=remaining*1000//full
    number(m,MEASURE+16,soc);number(m,MEASURE+0x54,soc)
    number(m,MEASURE+0x56,(soc+5)//10)


def state(m):
    return dict(remaining_cAh=m.num(MEASURE+12,2),full_cAh=m.num(MEASURE+14,2),
                soc_tenths=m.num(MEASURE+16,2),charge_centiAs=m.num(COUNTER+12,4),
                full_centiAs=m.num(COUNTER,4),flags=m.num(0x200000f5),
                cycles=m.num(MEASURE+0x60,2),block6_saves=len(m.soc_saves))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if not __debug__:parser.error('Python -O is unsupported')
    if args.out.exists():parser.error('Choose a new report')
    report=json.loads(research_input('pack-lock-1.6').read_text())
    facts=report['facts'];d=facts['cutoff'];r=facts['ram'];f=facts['functions']
    oem=Image.read(ROOT/'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex')
    path=ROOT/'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V1_6_CUTOFF].ehex'
    patched=Image.read(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==report['output_file_sha256']
    assert oem.sha==facts['original_app_sha256']
    # A1's parameter serializer BL at08F8 is a known1.6 latch-preservation hook.
    # Exclude that call, not any SOC calculation or block6 routine.
    ranges=((0x7c4,0x8f8),(0x8fc,0xa22),(0x5564,0x5694),(0x8c08,0x92bc))
    for start,end in ranges:assert oem.app[start:end]==patched.app[start:end]
    code=Code(oem.app)
    stop=[i for i in code.body(d['uart0_dispatch']) if i.op=='bl'][-1].at
    rows=[]
    for label,image in (('OEM16.06.13',oem),('MAINT1.6',patched)):
        def board():
            m=Machine(image,facts);m.defaults(0);m.soc_record=None;m.soc_saves=[]
            def iap(board,pc):
                if board.uc.reg_read(UC_ARM_REG_R0)!=6:return False
                if pc==f['iap_read']:
                    if board.soc_record is not None:board.put(r['iap_buffer'],board.soc_record)
                    board.ret(int(board.soc_record is not None));return True
                if pc==f['iap_write']:
                    a=r['iap_buffer'];board.soc_record=board.read(a,board.num(a+1))
                    board.soc_saves.append(board.soc_record.hex());board.ret(1);return True
                return False
            m.callback=iap
            for index,value in ((0,3550),(1,3450),(2,3000),(3,3100),(58,28000),(59,7500)):
                number(m,r['words']+2*index,value)
            for index,value in ((5,16),(18,15),(19,5),(20,96),(21,80)):
                number(m,r['small']+index,value,1)
            m.put(r['group0'],bytes.fromhex('ffdfff3fbf9fbf1f'))
            number(m,MEASURE,3298);number(m,MEASURE+2,3296)
            number(m,MEASURE+8,0,signed=True);number(m,MEASURE+10,5275)
            number(m,MEASURE+0x46,5440)
            number(m,0x200000ac,16,1);number(m,0x20000031,0,1)
            number(m,0x20000005,0,1);number(m,0x200000f5,0,1)
            capacity(m);return m

        def check(name,fn):
            m=board()
            try:extra=fn(m) or {}
            except Exception as error:raise AssertionError(label+' / '+name+': '+str(error)) from error
            rows.append(dict(image=label,name=name,passed=True,**state(m),**extra))

        def tick(m,current,status,expected):
            number(m,MEASURE+8,current,signed=True);number(m,0x200000ac,status,1)
            before=m.num(COUNTER+12,4);m.run(0x9044)
            assert m.num(COUNTER+12,4)-before==expected
            return dict(delta_centiAs=expected)
        check('one-second-charge-1A',lambda m:tick(m,100,2,100))
        check('one-second-discharge-1A',lambda m:tick(m,-100,1,-100))
        check('one-second-idle-drain-0.03A',lambda m:tick(m,0,16,-3))
        def idle_high(m):
            capacity(m,27720);return tick(m,0,16,-20)
        check('one-second-idle-drain-above-P80-0.20A',idle_high)
        def upper(m):
            capacity(m,27496);return tick(m,100,2,0)
        check('charge-stops-counting-at98.2-below-P0',upper)
        def lower(m):
            capacity(m,1400);return tick(m,-100,1,0)
        check('discharge-stops-below-P79plus1-above-P2',lower)

        def calibrate(m,soc=177,voltage=5275,minimum=3296,maximum=3298,idle=1800,hold90=0,holdfull=0,p0=3550):
            capacity(m,28000*soc//1000)
            number(m,MEASURE,maximum);number(m,MEASURE+2,minimum);number(m,MEASURE+10,voltage)
            number(m,r['words'],p0)
            number(m,COUNTER+0x22,31);number(m,COUNTER+0x24,idle)
            number(m,COUNTER+0x26,hold90);number(m,COUNTER+0x28,holdfull)
            m.run(0x8e0c);m.run(0x8f56)

        def voltage_case(m,expected,**kwargs):
            calibrate(m,**kwargs);assert m.num(MEASURE+16,2)==expected
        check('52.75V-17.7-remains-below-first-voltage-rule',lambda m:voltage_case(m,177))
        check('23-percent-at52.80V-after1801-low-charge-seconds',lambda m:voltage_case(m,230,voltage=5280,minimum=3200))
        check('23-percent-not-at1800-low-charge-seconds',lambda m:voltage_case(m,177,voltage=5280,minimum=3200,idle=1799))
        check('70-percent-at53.92V-min3.320',lambda m:voltage_case(m,700,soc=500,voltage=5392,minimum=3320,maximum=3380))
        check('90-percent-P0-cell-after31-low-charge-seconds',lambda m:voltage_case(m,900,soc=500,voltage=5360,maximum=3550,idle=30))
        check('90-percent-after1801-voltage-hold-seconds',lambda m:voltage_case(m,900,soc=500,voltage=5440,minimum=3340,maximum=3405,idle=30,hold90=1800))
        check('98-percent-after31-full-voltage-hold-seconds',lambda m:voltage_case(m,980,soc=500,voltage=5600,minimum=3350,maximum=3550,idle=30,holdfull=30))
        check('100-percent-after1801-full-voltage-hold-seconds',lambda m:voltage_case(m,1000,soc=980,voltage=5600,minimum=3350,maximum=3550,idle=30,holdfull=1800))
        check('55.20V-insufficient-for-full-when-P0-is3.550',lambda m:voltage_case(m,980,soc=980,voltage=5520,minimum=3350,maximum=3550,idle=30,holdfull=1800))
        check('full-threshold-P0-floor3.450',lambda m:voltage_case(m,1000,soc=980,voltage=5520,minimum=3350,maximum=3450,idle=30,holdfull=1800,p0=3400))
        def not_calibrated(m):
            number(m,0x20000005,16,1)
            calibrate(m,voltage=5600,minimum=3350,maximum=3550,holdfull=1800)
            assert m.num(MEASURE+16,2)==177
        check('voltage-calibration-blocked-with-uncalibrated-current-zero',not_calibrated)
        def strong_charge(m):
            number(m,0x200000ac,0x82,1)
            calibrate(m,voltage=5600,minimum=3350,maximum=3550,holdfull=1800)
            assert m.num(COUNTER+0x24,2)==0 and m.num(MEASURE+16,2)==177
        check('voltage-calibration-blocked-while-3A-charge-status-active',strong_charge)
        def thirty_second_gate(m):
            number(m,MEASURE,3550);number(m,MEASURE+2,3350);number(m,MEASURE+10,5600)
            number(m,COUNTER+0x22,0);number(m,COUNTER+0x24,1800);number(m,COUNTER+0x28,1800)
            for _ in range(30):m.run(0x8e0c)
            assert m.num(COUNTER+12,4)==4956*3600
            m.run(0x8e0c);m.run(0x8f56)
            assert m.num(MEASURE+16,2)==980
        check('plausibility-gate-requires31-one-second-calls',thirty_second_gate)
        check('P2-low-voltage-reduces-to-mean-P78-P79',lambda m:voltage_case(m,100,soc=500,voltage=5000,minimum=3000,maximum=3300,idle=0))

        def protection(m,event,status,expected,uncalibrated=False,flags=0):
            number(m,0x20000031,event,1);number(m,0x200000ac,status,1)
            number(m,0x20000005,16 if uncalibrated else 0,1);number(m,0x200000f5,flags,1)
            m.run(0x8f56);assert m.num(MEASURE+16,2)==expected
        check('cell-OVP-with-charging-first-pass-100',lambda m:protection(m,2,2,1000))
        check('pack-OVP-with-charging-first-pass-100',lambda m:protection(m,32,2,1000))
        check('OVP-without-charging-no-full-reset',lambda m:protection(m,2,16,177))
        check('OVP-full-flag-is-one-shot',lambda m:protection(m,2,2,177,flags=2))
        check('UVP-calibrated-zero-first-pass',lambda m:protection(m,8,16,0))
        check('UVP-uncalibrated-zero-does-not-force-counter-zero',lambda m:protection(m,8,16,177,True))

        def checkpoint(m,status,difference,expected):
            number(m,0x200000ac,status,1);number(m,MEASURE+0x54,177+difference)
            m.run(0x8f56);assert len(m.soc_saves)==expected
        check('checkpoint-not-at-exactly5.0-percent-idle',lambda m:checkpoint(m,16,50,0))
        check('checkpoint-at5.1-percent-idle',lambda m:checkpoint(m,16,51,1))
        check('no-checkpoint-while-charging-even-large-SOC-change',lambda m:checkpoint(m,2,400,0))
        check('no-checkpoint-while-discharging-even-large-SOC-change',lambda m:checkpoint(m,1,400,0))
        check('checkpoint-also-allowed-Off-without-charge-or-discharge',lambda m:checkpoint(m,32,51,1))

        def restore(m,valid=True):
            if valid:
                m.soc_record=bytes([0xa0,20])+struct.pack('<HHIIHHH',11149,28000,11033,9843,81,0,0)
            m.run(0x55ce)
            assert m.num(MEASURE+12,2)==(11149 if valid else 7500)
            assert m.num(MEASURE+0x60,2)==(81 if valid else 0)
            assert m.num(MEASURE+16,2)==(398 if valid else 267)
            return dict(block6_accepted=valid)
        check('boot-restores-valid-old-checkpoint-not-P59',restore)
        check('boot-without-valid-block6-uses-P59-and-resets-cycles',lambda m:restore(m,False))

        def uart0(m,command,data):
            packet=ascii_frame(0,command,data)
            m.put(d['uart0_rx'],packet);number(m,d['uart0_meta']-6,len(packet));number(m,d['uart0_state'],4,1)
            m.pause=stop;m.run(d['uart0_dispatch']);m.pause=None
            response=m.read(d['uart0_state']+1,m.num(d['uart0_rx']-6,2))
            rtn,info=ascii_payload(response);assert info==b''
            return rtn
        def set_remaining(m,value,expected):
            before=m.num(COUNTER+12,4);rtn=uart0(m,0x49,b'\0\x3b'+value.to_bytes(2,'big'))
            assert rtn==expected and not m.soc_saves
            assert m.num(r['words']+118,2)==7500,'0x49 unexpectedly changed P59 metadata'
            assert m.num(COUNTER+12,4)==(value*3600 if rtn==0 else before)
            m.run(0x8f56)
            return dict(rtn=rtn,immediate_block6_saves=0)
        check('UART0-49-3B-writes118.44Ah-yields42.3-percent',lambda m:set_remaining(m,11844,0))
        check('UART0-49-3B-rejects-over-full-capacity',lambda m:set_remaining(m,28001,6))
        def change_full(m):
            assert uart0(m,0x49,b'\0\x3a'+(56000).to_bytes(2,'big'))==0
            assert m.num(r['words']+116,2)==28000,'P58 metadata unexpectedly changed'
            m.run(0x8f56);assert m.num(MEASURE+16,2)==88 and m.num(MEASURE+12,2)==4956
        check('UART0-49-3A-changes-denominator-not-P58-metadata',change_full)

        def a1(m,change59=False,full=28000):
            capacity(m,4956,full);before=m.num(COUNTER+12,4)
            payload=bytearray(m.payload())
            if change59:payload[119:121]=(12345).to_bytes(2,'big')
            assert uart0(m,0xa1,bytes([0])+payload+m.read(r['name'],10))==0
            assert m.num(COUNTER+12,4)==before
            assert len(m.soc_saves)==int(full!=28000)
            if change59:assert m.num(r['words']+118,2)==12345
            return dict(parameter_P59=m.num(r['words']+118,2),parameter_P58=m.num(r['words']+116,2))
        check('UART0-A1-changing-P59-metadata-does-not-set-SOC-or-save-block6',lambda m:a1(m,True))
        check('UART0-A1-ordinary-parameter-write-does-not-save-block6',a1)
        check('UART0-A1-10Ah-full-capacity-difference-saves-block6',lambda m:a1(m,full=27000))
        if label=='MAINT1.6':
            def unsupported(m):
                response=m.transact(ascii_frame(0,0x49,b'\0\x3b'+(11844).to_bytes(2,'big')),patched=True)
                rtn,info=ascii_payload(response);assert rtn==4 and info==b''
                assert m.num(COUNTER+12,4)==4956*3600
            check('UART1-49-remains-unsupported-RTN04',unsupported)
    result=dict(passed=True,hardware_access=False,firmware_modified=False,build_id=report['build']['build_id'],
                unchanged_ranges=[[hex(a),hex(b)] for a,b in ranges],tests=len(rows),results=rows,
                limitations=['Synthetic RAM and accepted/absent block6 IAP model; no physical NVM dump',
                             'Not a full bootloader/main-loop/electrical simulation',
                             'UART0 dispatcher tested directly; polling masters still require maintenance'])
    with args.out.open('x') as output:json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))


if __name__=='__main__':main()

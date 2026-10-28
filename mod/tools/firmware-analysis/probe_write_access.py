#!/usr/bin/env python3
"""Offline real-Thumb write matrix for OEM16.06.13/MAINT1.5/MAINT1.6.

Exhaustively changes every parameter and switch bit on implemented A1 paths.
Runs actual UART0/UART2 parsers and dispatchers through encoded response RAM;
UART1 also uses its real RX/TX IRQ. Other command counterexamples distinguish
dispatch reachability, modeled hardware effects, and unsupported commands.
No physical ports. Exact image hashes required. Firmware files are read only.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=PROJECT_ROOT


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    if not __debug__:ap.error('Python -O is unsupported')
    if args.out.exists():ap.error('Choose a new report')
    catalog=module('write_catalog',HERE/'historical_write_model.py')
    soc=module('soc_fixture',HERE/'soc_profile_v16.py');loaded=soc.load_images()
    from seplos.image import Image
    from seplos.machine import ascii_frame,frame
    from seplos.selftest import ascii_payload
    from seplos.thumb import Code
    from unicorn.arm_const import UC_ARM_REG_PC
    loaded['images']['MAINT1.5']=Image.read(ROOT/catalog.IMAGES['MAINT1.5']['path'])
    for label,image in loaded['images'].items():
        assert image.sha==catalog.IMAGES[label]['app_sha256'],label
    f=loaded['facts']['functions'];r=loaded['facts']['ram'];d=loaded['facts']['cutoff']
    ep=catalog.ENTRY_POINTS
    code=Code(loaded['images']['OEM16.06.13'].app)
    uart0_tx=next(i.at for i in reversed(code.body(ep['uart0_dispatch'])) if i.op=='bl')
    lcd_state=0x20001426;lcd_meta=r['lcd_meta']
    assert lcd_meta==lcd_state+0xc0
    rows=[]

    def board(label,address=1):
        m=soc.new_board(loaded,label);m.put(r['address'],bytes([address]))
        callback=m.callback
        def peripheral(board,pc):
            # Model EEPROM transfer acceptance, not the history-clear routine.
            if pc==0x574c and board.num(loaded['facts']['power_rtc']['rtc'])==0xa4:
                board.ret(1);return True
            return callback(board,pc)
        m.callback=peripheral
        return m

    def result(label,port,name,**fields):
        rows.append(dict(image=label,uart=port,name=name,passed=True,**fields))

    def uart0(m,cmd,data=b'',pause=None):
        raw=ascii_frame(m.num(r['address']),cmd,data)
        m.put(d['uart0_rx'],raw);m.put(d['uart0_meta']-6,len(raw).to_bytes(2,'little'))
        m.put(d['uart0_state'],b'\4');m.pause=pause or uart0_tx
        m.run(ep['uart0_dispatch'])
        if pause and m.uc.reg_read(UC_ARM_REG_PC)==pause:return None
        if m.num(d['uart0_state'])==0:return None
        raw=m.read(d['uart0_state']+1,m.num(d['uart0_rx']-6,2))
        return ascii_payload(raw,m.num(r['address']))[0]

    def uart2(m,cmd,data=b'',target=1):
        raw=frame(target,cmd,data)
        m.put(lcd_meta+14,raw);m.put(lcd_meta+0xd8,len(raw).to_bytes(2,'little'))
        m.put(lcd_state,b'\x08');m.pause=ep['uart2_send'];m.run(ep['uart2_dispatch'])
        if m.uc.reg_read(UC_ARM_REG_PC)!=ep['uart2_send']:return None
        raw=m.read(lcd_state+1,m.num(lcd_meta+10,2))
        import binascii
        assert raw[0]==0x55 and raw[-1]==0xaa
        assert binascii.crc_hqx(raw[1:-3],0)==int.from_bytes(raw[-3:-1],'big')
        return raw[2]

    def uart1(m,label,cmd,data=b'',binary=False):
        adr=m.num(r['address']);raw=frame(adr,cmd,data) if binary else ascii_frame(adr,cmd,data)
        out=m.transact(raw,patched=label!='OEM16.06.13')
        if not out:return None
        if binary:
            import binascii
            assert out[0]==0x55 and out[-1]==0xaa and out[1]==adr
            assert binascii.crc_hqx(out[1:-3],0)==int.from_bytes(out[-3:-1],'big')
            return out[2]
        return ascii_payload(out,adr)[0]

    def a1(m,label,port,payload,name=None):
        if port=='U0':return uart0(m,0xa1,b'\0'+payload+(name or m.read(r['name'],10)))
        if port=='U2':return uart2(m,0xa1,payload)
        return uart1(m,label,0xa1,payload,binary=True)

    def validator(m,payload):
        m.put(r['shadow_words'],b''.join(payload[i:i+2][::-1] for i in range(1,121,2)))
        m.put(r['shadow_small'],payload[122:149]);return m.run(f['validator'])

    # Find a valid independently editable neighbour for each field, using the
    # real OEM validator rather than duplicating its relational constraints.
    alternatives={}
    for parameter in catalog.PARAMETERS:
        m=board('OEM16.06.13');base=m.payload();off=parameter['binary_payload_offset']
        width=parameter['width'];old=int.from_bytes(base[off:off+width],'big')
        for delta in (1,-1,10,-10,100,-100):
            new=old+delta
            if not 0<=new<1<<(width*8):continue
            proposed=bytearray(base);proposed[off:off+width]=new.to_bytes(width,'big')
            if validator(m,proposed):alternatives[parameter['index']]=(off,width,new);break
        else:raise AssertionError(('no valid neighbour',parameter))

    for label in catalog.IMAGES:
        ports=('U0','U2') if label=='OEM16.06.13' else ('U0','U1','U2')
        for port in ports:
            for parameter in catalog.PARAMETERS:
                m=board(label);p=bytearray(m.payload());off,width,new=alternatives[parameter['index']]
                p[off:off+width]=new.to_bytes(width,'big')
                ack=a1(m,label,port,bytes(p))
                assert ack==(0 if port=='U0' else 0xa1),(label,port,parameter,ack)
                assert m.payload()==p,(label,port,parameter)
                assert any(block==0 for block,data in m.saves)
                result(label,port,'A1-P'+str(parameter['index']),parameter=parameter['index'],raw_value=new)
            for item in catalog.FUNCTION_BITS:
                m=board(label);before=m.payload();p=bytearray(before);g=item['group'];bit=item['bit']
                p[150+g]^=1<<bit
                denied=port=='U1' and g==0 and (bit in (2,3) or (label=='MAINT1.6' and bit==5))
                preserved=label=='MAINT1.6' and g==0 and bit==5
                ack=a1(m,label,port,bytes(p))
                if denied:
                    assert ack==0xe3 and m.payload()==before and not m.saves
                    effect='atomic E3'
                else:
                    assert ack==(0 if port=='U0' else 0xa1),(label,port,g,bit,ack)
                    expected=bytearray(p)
                    if preserved:expected[150+g]=before[150+g]
                    assert m.payload()==expected,(label,port,g,bit)
                    effect='preserved read-only status' if preserved else 'changed'
                result(label,port,f'A1-Group{g}.bit{bit}',effect=effect)

        for port in ports:
            m=board(label);m.put(r['group0'],bytes([m.num(r['group0'])&~1]))
            before=m.payload();p=bytearray(before);p[137]+=1  # P75, valid interval
            ack=a1(m,label,port,bytes(p))
            if port=='U1':assert ack==0xe3 and m.payload()==before
            else:assert ack==(0 if port=='U0' else 0xa1) and m.payload()==p
            result(label,port,'A1-Group0-bit0-off-only-blocks-UART1',response=ack)

        # The two live capacity commands are not equivalent to A1/P58/P59.
        for index,value in ((0x3a,30000),(0x3b,11844)):
            for port in ('U0','U1','U2'):
                m=board(label);params=m.payload();data=b'\0'+bytes([index])+value.to_bytes(2,'big')
                if port=='U0':ack=uart0(m,0x49,data)
                elif port=='U1':ack=uart1(m,label,0x49,data)
                else:ack=uart2(m,0x49,data)
                assert ack=={'U0':0,'U1':4,'U2':0x81}[port],(label,port,index,ack)
                assert m.payload()==params and not m.soc_saves
                field='charge_max' if index==0x3a else 'charge'
                if port=='U0':assert m.num(soc.RAM[field],4)==value*3600
                result(label,port,f'49-{index:02X}',response=ack)

        # Strings and device name are writable only over UART0.
        for command,key in ((0xa3,'string1'),(0xa5,'string2')):
            for port in ('U0','U1','U2'):
                m=board(label);name=b'SYNTHETIC-SERIAL-01';before=m.read(r[key],30)
                ack=uart0(m,command,name) if port=='U0' else (uart1(m,label,command,name) if port=='U1' else uart2(m,command,name))
                assert ack=={'U0':0,'U1':4,'U2':0x81}[port],(label,port,command,ack)
                assert m.read(r[key],30)==(name.ljust(30,b' ') if port=='U0' else before)
                result(label,port,f'serial-write-{command:02X}',response=ack)
        m=board(label);assert a1(m,label,'U0',m.payload(),b'NEW-NAME00')==0
        assert m.read(r['name'],10)==b'NEW-NAME00';result(label,'U0','A1-device-name')

        # CAN protocol uses a separate command / IAP block4.
        for port in ('U0','U1','U2'):
            m=board(label);old=m.num(0x20000024)
            ack=uart0(m,0xa6,b'\2') if port=='U0' else (uart1(m,label,0xa6,b'\2') if port=='U1' else uart2(m,0x63,b'\2'))
            assert ack=={'U0':0,'U1':4,'U2':0x63}[port],(label,port,ack)
            assert m.num(0x20000024)==(2 if port!='U1' else old)
            result(label,port,'CAN-protocol',response=ack)
        if label!='OEM16.06.13':
            for cmd,data in ((0x63,b'\2'),(0xa3,b'X'),(0xa5,b'X'),(0x49,b'\0\x3b\0\1'),(0xa0,b'\0\0\0'),
                             (0x45,b'\0\4\x1f'),(0x4e,bytes.fromhex('07EA0A15010203')),(0xa6,b'\2')):
                m=board(label);assert uart1(m,label,cmd,data,binary=True)==0x81
                result(label,'U1',f'unsupported-binary-{cmd:02X}')

        # RTC executes the original BCD driver with a modeled I2C transfer.
        clock=bytes.fromhex('07EA0A15123438')
        for port in ('U0','U1','U2'):
            m=board(label);m.put(r['group0'],bytes([m.num(r['group0'])&~8]))
            ack=uart0(m,0x4e,clock) if port=='U0' else (uart1(m,label,0x4e,clock) if port=='U1' else uart2(m,0x4e,clock))
            expect=0 if (port=='U0' or (port=='U1' and label!='OEM16.06.13')) else (4 if port=='U1' else 0x81)
            assert ack==expect,(label,port,ack)
            assert bool(m.rtc_transfers)==(expect==0),(label,port,ack,m.rtc_transfers)
            result(label,port,'RTC-set',response=ack)

        # The UART1 gate does not restrict original UART0 clock or power.
        for port in ('U0','U1'):
            m=board(label);m.put(r['group0'],bytes([m.num(r['group0'])|8]))
            ack=uart0(m,0x4e,clock) if port=='U0' else uart1(m,label,0x4e,clock)
            expected=0 if port=='U0' else (4 if label=='OEM16.06.13' else 5)
            assert ack==expected and bool(m.rtc_transfers)==(expected==0)
            result(label,port,'RTC-UART1-gate-closed',response=ack)

        for port in ('U0','U1','U2'):
            for gate_closed in (False,True):
                for value in (0x10,0x1f):
                    m=board(label);group=m.num(r['group0'])&~0x18
                    if gate_closed:group|=8
                    m.put(r['group0'],bytes([group]))
                    data=bytes([0,4,value])
                    ack=uart0(m,0x45,data) if port=='U0' else (uart1(m,label,0x45,data) if port=='U1' else uart2(m,0x45,data))
                    expected=0 if port=='U0' else ((4 if label=='OEM16.06.13' else (5 if gate_closed else 0)) if port=='U1' else 0x81)
                    assert ack==expected,(label,port,value,gate_closed,ack)
                    off=bool(m.num(soc.RAM['system_status'])&32)
                    assert off==(expected==0 and value==0x1f)
                    if label=='MAINT1.6':
                        assert bool(m.num(d['ram']))==off
                        assert bool(m.num(r['group0'])&32)!=off
                    result(label,port,f'power-{value:02X}-UART1-gate-{gate_closed}',response=ack,off=off)

        # Original U2-64 is a stub, not maintenance or RTC/power control.
        m=board(label);before=m.payload();assert uart2(m,0x64,b'\1')==0x64
        assert m.payload()==before and not m.saves and not m.rtc_transfers and m.num(0x23000,4)==0xffffffff
        result(label,'U2','64-stub-has-no-setting-effect')
        m=board(label);assert uart2(m,0xa1,m.payload(),target=15)==0xa1
        result(label,'U2','foreign-address-still-local-no-target-check')
        m=board(label);m.put(r['group0']+7,bytes([m.num(r['group0']+7)&~8]));before=m.payload()
        p=bytearray(before);p[157]|=8
        assert uart2(m,0xa1,p) is None and m.payload()==before and not m.saves
        result(label,'U2','disabled-LCD-cannot-enable-itself')

        # Heating and history clearing remain original UART0 operations.
        for subtype in (3,5):
            for port in ('U0','U1','U2'):
                m=board(label);m.put(r['group0'],bytes([m.num(r['group0'])&~8]))
                m.put(0x20000d20,(123).to_bytes(4,'little')*2+(7).to_bytes(2,'little'))
                data=bytes([0,subtype,0x10 if subtype==3 else 0])
                ack=uart0(m,0x45,data) if port=='U0' else (uart1(m,label,0x45,data) if port=='U1' else uart2(m,0x45,data))
                expected=0 if port=='U0' else ((4 if label=='OEM16.06.13' else 5) if port=='U1' else 0x81)
                assert ack==expected,(label,port,subtype,ack)
                if port=='U0':
                    if subtype==3:assert m.num(0x200000c8,2)==3600
                    else:assert m.read(0x20000d20,10)==bytes(10)
                result(label,port,f'45-type{subtype}',response=ack)

        # Calibration reachability: stop at the real OEM handler, before any
        # measurement calibration. Sensor-quality prerequisites are documented.
        for sub in (0,1,2):
            m=board(label);ack=uart0(m,0xa0,bytes([sub,0,0]),pause=ep['uart0_calibration'])
            assert ack is None and m.uc.reg_read(UC_ARM_REG_PC)==ep['uart0_calibration']
            result(label,'U0',f'A0-sub{sub}-handler-reachable',scope='dispatch only; no calibration claimed')
        for port in ('U1','U2'):
            m=board(label);ack=uart1(m,label,0xa0,b'\0\0\0') if port=='U1' else uart2(m,0xa0,b'\0\0\0')
            assert ack==(4 if port=='U1' else 0x81);result(label,port,'A0-unsupported',response=ack)

        # Local watchdog target, with no ACK, rather than running the watchdog.
        m=board(label);assert uart0(m,0x45,b'\0\6\0',pause=ep['watchdog_reset']) is None
        assert m.uc.reg_read(UC_ARM_REG_PC)==ep['watchdog_reset']
        result(label,'U0','reset-reaches-watchdog-no-ACK')
        if label!='OEM16.06.13':
            m=board(label);m.put(r['group0'],bytes([m.num(r['group0'])&~8]));m.pause=ep['watchdog_reset']
            m.feed(ascii_frame(1,0x45,b'\0\6\0'));site=loaded['facts']['hooks']['hook_dispatch'];m.execute(site,site+4)
            assert m.uc.reg_read(UC_ARM_REG_PC)==ep['watchdog_reset'] and not m.output
            result(label,'U1','reset-reaches-watchdog-no-ACK')
            m=board(label,0);assert uart1(m,label,0x64,bytes.fromhex('01C35A'))==0
            assert m.num(0x23000,4)==0
            m.put(r['group0'],bytes([m.num(r['group0'])&~4]))
            assert uart1(m,label,0x64,bytes.fromhex('00C35A'))==0 and m.num(0x23000,4)==0xffffffff
            result(label,'U1','maintenance-start-and-stop-with-start-gate-closed')

    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    output=dict(passed=True,hardware_access=False,firmware_modified=False,tests=len(rows),
        parameter_fields=87,function_bit_positions=64,
        A1_image_port_combinations=8,
        sources_sha256={p.name:sha(p) for p in (Path(__file__),HERE/'historical_write_model.py',HERE/'historical_write_model.json',HERE/'soc_profile_v16.py',ROOT/'mod/firmware/patcher/seplos/machine.py')},
        images={k:dict(app_sha256=v.sha,file_sha256=sha(ROOT/catalog.IMAGES[k]['path'])) for k,v in loaded['images'].items()},
        scope=['actual UART0 and UART2 parser/dispatcher, encoded response RAM; no TX IRQ model on those two ports',
               'actual UART1 RX/TX IRQ and dispatcher','all87 parameter fields and all64 bit positions on8 supported A1 paths',
               'IAP/EEPROM/RTC transfer modeled; calibration and reset stopped at documented handler/target',
               'bootloader flashing and electrical MOSFET behavior are outside this probe'],results=rows)
    with args.out.open('x') as stream:json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k!='results'},indent=2))


if __name__=='__main__':main()
